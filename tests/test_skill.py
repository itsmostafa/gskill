"""Tests for skill-generation helpers."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.skill import _completion_token_kwargs, generate_initial_skill


class CompletionTokenKwargsTests(unittest.TestCase):
    def test_gpt5_uses_max_completion_tokens(self) -> None:
        self.assertEqual(
            _completion_token_kwargs("gpt-5.2", 2000),
            {"max_completion_tokens": 2000},
        )

    def test_legacy_models_keep_max_tokens(self) -> None:
        self.assertEqual(
            _completion_token_kwargs("gpt-4o", 2000),
            {"max_tokens": 2000},
        )

    def test_o1_uses_max_completion_tokens(self) -> None:
        self.assertEqual(
            _completion_token_kwargs("o1-mini", 2000),
            {"max_completion_tokens": 2000},
        )


class GenerateInitialSkillTests(unittest.TestCase):
    def test_gpt5_request_uses_max_completion_tokens(self) -> None:
        captured_kwargs: dict[str, object] = {}

        def fake_create(**kwargs: object) -> object:
            captured_kwargs.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="---\nname: jinja\n---\nbody")
                    )
                ]
            )

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )

        with (
            patch("src.skill._fetch_readme", return_value="readme"),
            patch("src.skill._fetch_file", return_value=""),
            patch("src.skill.openai.OpenAI", return_value=fake_client),
        ):
            generate_initial_skill("https://github.com/pallets/jinja", model="gpt-5.2")

        self.assertEqual(captured_kwargs["model"], "gpt-5.2")
        self.assertEqual(captured_kwargs["max_completion_tokens"], 2000)
        self.assertNotIn("max_tokens", captured_kwargs)


if __name__ == "__main__":
    unittest.main()
