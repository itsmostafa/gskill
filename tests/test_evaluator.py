"""Tests for evaluator image-prefetch behavior."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.evaluator import (
    _DEFAULT_DOCKER_PULL_TIMEOUT,
    _READY_IMAGES,
    _ensure_swebench_image,
    _resolve_docker_pull_timeout,
    make_evaluator,
)


class ResolveDockerPullTimeoutTests(unittest.TestCase):
    def test_explicit_timeout_wins(self) -> None:
        with patch.dict("os.environ", {"GSKILL_DOCKER_PULL_TIMEOUT": "123"}, clear=False):
            self.assertEqual(_resolve_docker_pull_timeout(456), 456)

    def test_env_timeout_is_used_when_valid(self) -> None:
        with patch.dict("os.environ", {"GSKILL_DOCKER_PULL_TIMEOUT": "321"}, clear=False):
            self.assertEqual(_resolve_docker_pull_timeout(), 321)

    def test_invalid_env_timeout_falls_back_to_default(self) -> None:
        with patch.dict("os.environ", {"GSKILL_DOCKER_PULL_TIMEOUT": "oops"}, clear=False):
            self.assertEqual(_resolve_docker_pull_timeout(), _DEFAULT_DOCKER_PULL_TIMEOUT)


class EnsureSWEbenchImageTests(unittest.TestCase):
    def setUp(self) -> None:
        _READY_IMAGES.clear()

    def test_existing_local_image_skips_pull(self) -> None:
        inspect_result = SimpleNamespace(returncode=0)

        with patch("src.evaluator.subprocess.run", return_value=inspect_result) as mock_run:
            ok, status = _ensure_swebench_image("example/image", pull_timeout=600)

        self.assertTrue(ok)
        self.assertEqual(status, "present_locally")
        mock_run.assert_called_once()

    def test_missing_image_is_pulled_and_cached(self) -> None:
        inspect_result = SimpleNamespace(returncode=1)
        pull_result = SimpleNamespace(returncode=0)

        with patch(
            "src.evaluator.subprocess.run",
            side_effect=[inspect_result, pull_result],
        ) as mock_run:
            ok, status = _ensure_swebench_image("example/image", pull_timeout=600)

        self.assertTrue(ok)
        self.assertEqual(status, "pulled")
        self.assertEqual(mock_run.call_count, 2)


class MakeEvaluatorTests(unittest.TestCase):
    def test_prefetch_failure_short_circuits_evaluation(self) -> None:
        evaluator = make_evaluator(docker_pull_timeout=777)

        with (
            patch("src.evaluator._write_skill_config", return_value=Path("/tmp/skill.yaml")),
            patch(
                "src.evaluator.tempfile.NamedTemporaryFile",
                return_value=SimpleNamespace(name="/tmp/traj.json", close=lambda: None),
            ),
            patch("src.evaluator.get_swebench_docker_image_name", return_value="example/image"),
            patch(
                "src.evaluator._ensure_swebench_image",
                return_value=(False, "Docker pull timed out"),
            ) as mock_ensure,
            patch("src.evaluator.os.unlink"),
        ):
            score, info = evaluator("skill", {"instance_id": "task-1"})

        self.assertEqual(score, 0.0)
        self.assertEqual(info["test_failure_reason"], "image_unavailable")
        self.assertEqual(info["error"], "Docker pull timed out")
        mock_ensure.assert_called_once_with("example/image", 777)

    def test_evaluator_passes_timeout_into_environment_config(self) -> None:
        evaluator = make_evaluator(docker_pull_timeout=777)
        env = SimpleNamespace(cleanup=lambda: None)
        agent = SimpleNamespace(run=lambda _: {"submission": "diff --git a/x b/x"})

        with (
            patch("src.evaluator._write_skill_config", return_value=Path("/tmp/skill.yaml")),
            patch(
                "src.evaluator.tempfile.NamedTemporaryFile",
                return_value=SimpleNamespace(name="/tmp/traj.json", close=lambda: None),
            ),
            patch("src.evaluator.get_config_from_spec", return_value={}),
            patch("src.evaluator.get_swebench_docker_image_name", return_value="example/image"),
            patch(
                "src.evaluator._ensure_swebench_image",
                return_value=(True, "pulled"),
            ) as mock_ensure,
            patch("src.evaluator.get_sb_environment", return_value=env) as mock_get_env,
            patch("src.evaluator.get_model", return_value=object()),
            patch("src.evaluator.get_agent", return_value=agent),
            patch("src.evaluator._run_tests", return_value=(True, "tests_passed")),
            patch("src.evaluator.os.unlink"),
        ):
            score, info = evaluator(
                "skill",
                {"instance_id": "task-1", "problem_statement": "fix it"},
            )

        self.assertEqual(score, 1.0)
        self.assertEqual(info["image_status"], "pulled")
        mock_ensure.assert_called_once_with("example/image", 777)
        config = mock_get_env.call_args.args[0]
        self.assertEqual(config["environment"]["pull_timeout"], 777)


if __name__ == "__main__":
    unittest.main()
