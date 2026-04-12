"""SWE-smith dataset loading and splitting."""

from datasets import load_dataset

DATASET_NAME = "SWE-bench/SWE-smith"


def load_tasks(repo_name: str, n: int = 300) -> list[dict]:
    """Load SWE-smith tasks filtered by repo_name (e.g., 'pallets/jinja').

    Args:
        repo_name: Repository in 'owner/repo' format.
        n: Maximum number of tasks to return.

    Returns:
        List of task dicts with fields like instance_id, repo, problem_statement,
        image_name, FAIL_TO_PASS, PASS_TO_PASS, etc.
    """
    # Stream from the Hub so we don't materialize the full dataset locally.
    ds = load_dataset(DATASET_NAME, split="train", streaming=True)
    # The dataset uses 'swesmith/owner__repo.commithash' format, so match by
    # converting 'owner/repo' → 'owner__repo' and doing a substring check.
    slug = repo_name.replace("/", "__")
    tasks: list[dict] = []
    for task in ds:
        if slug not in task["repo"]:
            continue
        tasks.append(dict(task))
        if len(tasks) >= n:
            break
    if not tasks:
        raise ValueError(
            f"No tasks found for repo '{repo_name}' in {DATASET_NAME}. "
            f"Use the full 'owner/repo' format, e.g., 'pallets/jinja'."
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
