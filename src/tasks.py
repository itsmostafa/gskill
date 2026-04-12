"""SWE-smith dataset loading and splitting."""

import re

from datasets import load_dataset

DATASET_NAME = "SWE-bench/SWE-smith"
REPO_NAME_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _is_valid_repo_name(repo_name: str) -> bool:
    """Return whether the input is a syntactically valid ``owner/repo`` slug."""
    return bool(REPO_NAME_RE.fullmatch(repo_name))


def _dataset_repo_name(raw_repo: str) -> str:
    """Normalize a dataset repo identifier to ``owner/repo``.

    SWE-smith stores repo ids like ``swesmith/oauthlib__oauthlib.1fd52536``.
    """
    if "/" not in raw_repo:
        return raw_repo
    _, slug = raw_repo.split("/", 1)
    return slug.split(".", 1)[0].replace("__", "/")


def list_supported_repos(query: str | None = None) -> list[str]:
    """Return the unique repository slugs available in SWE-smith."""
    ds = load_dataset(DATASET_NAME, split="train", streaming=True)
    filter_text = query.lower() if query else None
    repos: set[str] = set()
    for task in ds:
        repo_name = _dataset_repo_name(task["repo"])
        if filter_text and filter_text not in repo_name.lower():
            continue
        repos.add(repo_name)
    return sorted(repos)


def load_tasks(repo_name: str, n: int = 300) -> list[dict]:
    """Load SWE-smith tasks filtered by repo_name (e.g., 'pallets/jinja').

    Args:
        repo_name: Repository in 'owner/repo' format.
        n: Maximum number of tasks to return.

    Returns:
        List of task dicts with fields like instance_id, repo, problem_statement,
        image_name, FAIL_TO_PASS, PASS_TO_PASS, etc.
    """
    if not _is_valid_repo_name(repo_name):
        raise ValueError(
            f"Invalid repo '{repo_name}'. Use the full 'owner/repo' format, "
            "e.g., 'pallets/jinja'."
        )

    # Stream from the Hub so we don't materialize the full dataset locally.
    ds = load_dataset(DATASET_NAME, split="train", streaming=True)
    tasks: list[dict] = []
    for task in ds:
        if _dataset_repo_name(task["repo"]) != repo_name:
            continue
        tasks.append(dict(task))
        if len(tasks) >= n:
            break
    if not tasks:
        raise ValueError(
            f"Repository '{repo_name}' has no tasks in {DATASET_NAME}. "
            "gskill can only optimize skills for repositories included in that "
            "dataset. Run `gskill repos` (or `python main.py repos`) to inspect "
            "supported repos."
        )
    return tasks


def split_tasks(
    tasks: list[dict], train: float = 0.67, val: float = 0.17
) -> tuple[list[dict], list[dict], list[dict]]:
    """Deterministic split into train/val/test sets.

    Args:
        tasks: Full task list (already filtered by repo).
        train: Fraction for training (~67%).
        val: Fraction for validation (~17%).

    Returns:
        Tuple of (train_tasks, val_tasks, test_tasks).
    """
    n = len(tasks)
    n_train = int(n * train)
    n_val = int(n * val)
    return (
        tasks[:n_train],
        tasks[n_train : n_train + n_val],
        tasks[n_train + n_val :],
    )
