"""Mini-SWE-Agent evaluator for GEPA multi-task search."""

import os
import subprocess
import tempfile
import textwrap
import warnings
from pathlib import Path
from typing import Callable

import gepa.optimize_anything as oa
import yaml
from minisweagent.agents import get_agent
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.models import get_model
from minisweagent.run.benchmarks.swebench import (
    get_sb_environment,
    get_swebench_docker_image_name,
)
from minisweagent.utils.serialize import recursive_merge

_SWEBENCH_CONFIG = builtin_config_dir / "benchmarks" / "swebench.yaml"

# Base system prompt that frames the skill content
_SYSTEM_PREFIX = (
    "You are a helpful assistant that can interact with a computer shell "
    "to solve programming tasks.\n\n"
    "# Repository-Specific Knowledge\n\n"
)
_DEFAULT_DOCKER_PULL_TIMEOUT = 900
_DOCKER_INSPECT_TIMEOUT = 15
_READY_IMAGES: set[str] = set()


def _resolve_docker_pull_timeout(timeout: int | None = None) -> int:
    """Return the Docker pull timeout in seconds."""
    if timeout is not None:
        return max(timeout, 1)

    raw_timeout = os.environ.get("GSKILL_DOCKER_PULL_TIMEOUT", "").strip()
    if raw_timeout:
        try:
            parsed = int(raw_timeout)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    return _DEFAULT_DOCKER_PULL_TIMEOUT


def _log(message: str) -> None:
    """Log through GEPA when available without warning during local debugging."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        oa.log(message)


def _ensure_swebench_image(image_name: str, pull_timeout: int) -> tuple[bool, str]:
    """Make sure the SWE-smith Docker image is present locally before evaluation."""
    if image_name in _READY_IMAGES:
        return True, "cached"

    try:
        inspect_result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            capture_output=True,
            text=True,
            timeout=_DOCKER_INSPECT_TIMEOUT,
        )
    except FileNotFoundError:
        return False, "Docker executable not found while checking benchmark image."
    except subprocess.TimeoutExpired:
        inspect_result = None
    else:
        if inspect_result.returncode == 0:
            _READY_IMAGES.add(image_name)
            return True, "present_locally"

    try:
        _log(f"Pulling benchmark image {image_name} (timeout={pull_timeout}s)")
        subprocess.run(
            ["docker", "pull", image_name],
            capture_output=True,
            text=True,
            timeout=pull_timeout,
            check=True,
        )
        _READY_IMAGES.add(image_name)
        return True, "pulled"
    except FileNotFoundError:
        return False, "Docker executable not found while pulling benchmark image."
    except subprocess.TimeoutExpired:
        return (
            False,
            f"Docker pull timed out after {pull_timeout}s for benchmark image {image_name}.",
        )
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "").strip()[-300:]
        return (
            False,
            "Docker pull failed for benchmark image "
            f"{image_name}: {stderr_tail or f'exit {exc.returncode}'}",
        )


def _write_skill_config(skill: str) -> Path:
    """Write a mini config YAML that overrides agent.system_template with the skill."""
    system_template = _SYSTEM_PREFIX + skill
    config = {"agent": {"system_template": system_template}}
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, prefix="gskill_skill_"
    )
    yaml.dump(config, tmp, default_flow_style=False, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


def _run_tests(instance: dict, patch: str) -> tuple[bool, str]:
    """Apply the agent's patch and run FAIL_TO_PASS tests in a fresh Docker container.

    Args:
        instance: SWE-smith task dict (must have FAIL_TO_PASS; image resolved via
            get_swebench_docker_image_name, which checks image_name / docker_image
            and falls back to constructing from instance_id).
        patch: Git diff patch string produced by the agent.

    Returns:
        Tuple of (passed, reason) where reason describes the outcome.
    """
    fail_to_pass: list[str] = instance.get("FAIL_TO_PASS", [])
    if not fail_to_pass:
        _log("No FAIL_TO_PASS tests found, skipping test run")
        return False, "no_fail_to_pass_tests"

    image_name = get_swebench_docker_image_name(instance)
    _log(f"Test container image: {image_name}")

    # Limit to 10 tests to keep evaluation fast
    test_ids = fail_to_pass[:10]
    test_args = " ".join(f'"{t}"' for t in test_ids)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(patch)
        patch_file = f.name

    test_cmd = textwrap.dedent(f"""\
        cd /testbed
        git apply /tmp/solution.patch 2>/dev/null || patch -p1 < /tmp/solution.patch 2>/dev/null
        python -m pytest {test_args} -x --tb=no -q 2>&1
    """)

    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{patch_file}:/tmp/solution.patch:ro",
                image_name,
                "bash",
                "-c",
                test_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        passed = result.returncode == 0
        stdout_tail = result.stdout[-500:] if result.stdout else ""
        _log(f"Test stdout tail: {stdout_tail}")
        if not passed:
            _log(
                f"Tests failed (exit {result.returncode}) for image={image_name}; "
                f"stderr: {result.stderr[-200:] if result.stderr else '(none)'}"
            )
        return passed, "tests_passed" if passed else "tests_failed"
    except subprocess.TimeoutExpired:
        _log(f"Test run timed out (180s) for image={image_name}")
        return False, "test_timeout"
    except FileNotFoundError:
        _log(
            "Docker executable not found; ensure Docker is installed and running. "
            "All evaluations will score 0.0 until Docker is available."
        )
        return False, "docker_not_found"
    finally:
        os.unlink(patch_file)


def make_evaluator(
    agent_model: str | None = None,
    docker_pull_timeout: int | None = None,
) -> Callable[[str, dict], tuple[float, dict]]:
    """Create a GEPA-compatible evaluator that runs mini-SWE-Agent on a SWE-smith task.

    The returned evaluator:
      1. Writes the candidate skill into a temporary mini config YAML.
      2. Runs mini's Python API (swebench mode) on the task in Docker.
      3. Extracts the submitted patch from the agent's trajectory.
      4. Verifies the patch by running FAIL_TO_PASS tests in a fresh container.
      5. Returns (score, side_info) for GEPA reflection.

    Args:
        agent_model: LiteLLM model string for mini-SWE-agent (e.g. ``openai/gpt-5.2``).
            Falls back to the ``GSKILL_AGENT_MODEL`` env var, then ``openai/gpt-5.2``.

    Returns:
        Callable suitable for passing to ``optimize_anything(evaluator=...)``.
    """
    resolved_model = agent_model or os.environ.get(
        "GSKILL_AGENT_MODEL", "openai/gpt-5.2"
    )
    resolved_pull_timeout = _resolve_docker_pull_timeout(docker_pull_timeout)

    def evaluate(candidate_skill: str, task: dict) -> tuple[float, dict]:
        skill_config_path = _write_skill_config(candidate_skill)
        traj_tmp = tempfile.NamedTemporaryFile(
            suffix=".traj.json", delete=False, prefix="gskill_traj_"
        )
        traj_tmp.close()

        patch = ""
        score = 0.0
        error_msg = ""
        test_reason = ""
        env = None
        image_name = get_swebench_docker_image_name(task)
        image_status = ""

        try:
            image_ready, image_status = _ensure_swebench_image(
                image_name, resolved_pull_timeout
            )
            if not image_ready:
                error_msg = image_status
                test_reason = "image_unavailable"
                return score, {
                    "instance_id": task.get("instance_id", "unknown"),
                    "patch_chars": 0,
                    "score": score,
                    "error": error_msg,
                    "test_failure_reason": test_reason,
                    "image_name": image_name,
                    "image_status": image_status,
                }

            configs = [
                get_config_from_spec(str(_SWEBENCH_CONFIG)),
                get_config_from_spec(str(skill_config_path)),
                {"agent": {"output_path": traj_tmp.name}},
                {"environment": {"pull_timeout": resolved_pull_timeout}},
                {"model": {"model_name": resolved_model}},
            ]
            config = recursive_merge(*configs)

            env = get_sb_environment(config, task)
            model = get_model(config=config.get("model", {}))
            agent = get_agent(
                model, env, config.get("agent", {}), default_type="default"
            )

            result = agent.run(task["problem_statement"])
            patch = result.get("submission", "") or ""

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"Mini run error: {error_msg}")
        finally:
            if env is not None:
                env.cleanup()
            for path in (skill_config_path, traj_tmp.name):
                try:
                    os.unlink(path)
                except OSError:
                    pass

        if patch.strip():
            passed, test_reason = _run_tests(task, patch)
            score = 1.0 if passed else 0.0
            _log(
                f"instance={task.get('instance_id')} patch={len(patch)}chars "
                f"tests={'passed' if passed else 'failed'} reason={test_reason} score={score}"
            )
        else:
            test_reason = "no_patch_submitted"
            _log(
                f"instance={task.get('instance_id')} no patch submitted score=0.0"
                + (f"; agent error: {error_msg}" if error_msg else "")
            )

        return score, {
            "instance_id": task.get("instance_id", "unknown"),
            "patch_chars": len(patch),
            "score": score,
            "error": error_msg,
            "test_failure_reason": test_reason,
            "image_name": image_name,
            "image_status": image_status,
        }

    return evaluate
