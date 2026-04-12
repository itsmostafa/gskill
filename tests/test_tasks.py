"""Tests for SWE-smith task loading helpers."""

import unittest
from unittest.mock import patch

from src.pipeline import _extract_repo_name
from src.tasks import _dataset_repo_name, list_supported_repos, load_tasks


class DatasetRepoNameTests(unittest.TestCase):
    def test_dataset_repo_name_normalizes_swesmith_slug(self) -> None:
        self.assertEqual(
            _dataset_repo_name("swesmith/oauthlib__oauthlib.1fd52536"),
            "oauthlib/oauthlib",
        )


class LoadTasksTests(unittest.TestCase):
    def test_load_tasks_returns_matching_rows(self) -> None:
        fake_rows = iter(
            [
                {"repo": "swesmith/pallets__jinja.aaaa", "instance_id": "1"},
                {"repo": "swesmith/pallets__jinja.bbbb", "instance_id": "2"},
                {"repo": "swesmith/fastapi__fastapi.cccc", "instance_id": "3"},
            ]
        )

        with patch("src.tasks.load_dataset", return_value=fake_rows):
            tasks = load_tasks("pallets/jinja", n=10)

        self.assertEqual([task["instance_id"] for task in tasks], ["1", "2"])

    def test_load_tasks_rejects_malformed_repo_names(self) -> None:
        with patch("src.tasks.load_dataset") as mock_load_dataset:
            with self.assertRaisesRegex(
                ValueError,
                "Invalid repo 'fastapi'. Use the full 'owner/repo' format",
            ):
                load_tasks("fastapi")

        mock_load_dataset.assert_not_called()

    def test_load_tasks_reports_unsupported_repos(self) -> None:
        fake_rows = iter([{"repo": "swesmith/pallets__jinja.aaaa", "instance_id": "1"}])

        with patch("src.tasks.load_dataset", return_value=fake_rows):
            with self.assertRaisesRegex(
                ValueError,
                "Repository 'fastapi/fastapi' has no tasks in SWE-bench/SWE-smith",
            ):
                load_tasks("fastapi/fastapi")


class ListSupportedReposTests(unittest.TestCase):
    def test_list_supported_repos_returns_unique_sorted_values(self) -> None:
        fake_rows = iter(
            [
                {"repo": "swesmith/pallets__jinja.aaaa"},
                {"repo": "swesmith/fastapi__fastapi.bbbb"},
                {"repo": "swesmith/pallets__jinja.cccc"},
            ]
        )

        with patch("src.tasks.load_dataset", return_value=fake_rows):
            repos = list_supported_repos()

        self.assertEqual(repos, ["fastapi/fastapi", "pallets/jinja"])

    def test_list_supported_repos_filters_matches(self) -> None:
        fake_rows = iter(
            [
                {"repo": "swesmith/pallets__jinja.aaaa"},
                {"repo": "swesmith/fastapi__fastapi.bbbb"},
            ]
        )

        with patch("src.tasks.load_dataset", return_value=fake_rows):
            repos = list_supported_repos("fast")

        self.assertEqual(repos, ["fastapi/fastapi"])


class ExtractRepoNameTests(unittest.TestCase):
    def test_extract_repo_name_normalizes_github_urls(self) -> None:
        self.assertEqual(
            _extract_repo_name("https://github.com/fastapi/fastapi"),
            "fastapi/fastapi",
        )


if __name__ == "__main__":
    unittest.main()
