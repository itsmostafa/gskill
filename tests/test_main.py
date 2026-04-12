"""CLI tests for the gskill entry point."""

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from main import app


class ReposCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_repos_command_lists_supported_repos(self) -> None:
        with patch(
            "src.tasks.list_supported_repos",
            return_value=["fastapi/fastapi", "pallets/jinja"],
        ):
            result = self.runner.invoke(app, ["repos", "--limit", "0"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("fastapi/fastapi", result.stdout)
        self.assertIn("pallets/jinja", result.stdout)
        self.assertIn("Listed 2 supported repos from SWE-smith.", result.stdout)

    def test_repos_command_passes_filter_and_limit(self) -> None:
        with patch(
            "src.tasks.list_supported_repos",
            return_value=["fastapi/fastapi", "fastmcp/fastmcp"],
        ) as mock_list_supported_repos:
            result = self.runner.invoke(
                app, ["repos", "--filter", "fast", "--limit", "1"]
            )

        self.assertEqual(result.exit_code, 0)
        mock_list_supported_repos.assert_called_once_with(query="fast")
        self.assertIn("fastapi/fastapi", result.stdout)
        self.assertIn("Listed 1 of 2 supported repos from SWE-smith.", result.stdout)


if __name__ == "__main__":
    unittest.main()
