"""Mini-SWE-Agent evaluator for GEPA multi-task search."""

import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Callable

import yaml

import gepa.optimize_anything as oa
from minisweagent.agents import get_agent
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.models import get_model
from minisweagent.run.benchmarks.swebench import get_sb_environment, get_swebench_docker_image_name
from minisweagent.utils.serialize import recursive_merge

_SWEBENCH_CONFIG = builtin_config_dir / "benchmarks" / "swebench.yaml"

# Base system prompt that frames the skill content
_SYSTEM_PREFIX = (
    "You are a helpful assistant that can interact with a computer shell "
    "to solve programming tasks.\n\n"
    "# Repository-Specific Knowledge\n\n"
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
        oa.log("No FAIL_TO_PASS tests found, skipping test run")
        return False, "no_fail_to_pass_tests"

    image_name = get_swebench_docker_image_name(instance)
    oa.log(f"Test container image: {image_name}")

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
        oa.log(f"Test stdout tail: {stdout_tail}")
        if not passed:
            oa.log(
                f"Tests failed (exit {result.returncode}) for image={image_name}; "
                f"stderr: {result.stderr[-200:] if result.stderr else '(none)'}"
            )
        return passed, "tests_passed" if passed else "tests_failed"
    except subprocess.TimeoutExpired:
        oa.log(f"Test run timed out (180s) for image={image_name}")
        return False, "test_timeout"
    except FileNotFoundError:
        oa.log(
            "Docker executable not found; ensure Docker is installed and running. "
            "All evaluations will score 0.0 until Docker is available."
        )
        return False, "docker_not_found"
    finally:
        os.unlink(patch_file)


def make_evaluator() -> Callable[[str, dict], tuple[float, dict]]:
    """Create a GEPA-compatible evaluator that runs mini-SWE-Agent on a SWE-smith task.

    The returned evaluator:
      1. Writes the candidate skill into a temporary mini config YAML.
      2. Runs mini's Python API (swebench mode) on the task in Docker.
      3. Extracts the submitted patch from the agent's trajectory.
      4. Verifies the patch by running FAIL_TO_PASS tests in a fresh container.
      5. Returns (score, side_info) for GEPA reflection.

    Returns:
        Callable suitable for passing to ``optimize_anything(evaluator=...)``.
    """

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

        try:
            configs = [
                get_config_from_spec(str(_SWEBENCH_CONFIG)),
                get_config_from_spec(str(skill_config_path)),
                {
                    "agent": {
                        "mode": "yolo",
                        "output_path": traj_tmp.name,
                        "confirm_exit": False,
                    }
                },
            ]
            config = recursive_merge(*configs)

            env = get_sb_environment(config, task)
            model = get_model(config=config.get("model", {}))
            agent = get_agent(
                model, env, config.get("agent", {}), default_type="interactive"
            )

            result = agent.run(task["problem_statement"])
            patch = result.get("submission", "") or ""

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            oa.log(f"Mini run error: {error_msg}")
        finally:
            try:
                os.unlink(skill_config_path)
            except OSError:
                pass

        if patch.strip():
            passed, test_reason = _run_tests(task, patch)
            score = 1.0 if passed else 0.0
            oa.log(
                f"instance={task.get('instance_id')} patch={len(patch)}chars "
                f"tests={'passed' if passed else 'failed'} reason={test_reason} score={score}"
            )
        else:
            test_reason = "no_patch_submitted"
            oa.log(
                f"instance={task.get('instance_id')} no patch submitted score=0.0"
                + (f"; agent error: {error_msg}" if error_msg else "")
            )

        return score, {
            "instance_id": task.get("instance_id", "unknown"),
            "patch_chars": len(patch),
            "score": score,
            "error": error_msg,
            "test_failure_reason": test_reason,
        }

    return evaluate
