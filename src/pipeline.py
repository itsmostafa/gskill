"""Top-level pipeline orchestration for gskill."""

from gepa.optimize_anything import EngineConfig, GEPAConfig, optimize_anything

from .evaluator import make_evaluator
from .skill import generate_initial_skill, save_skill
from .tasks import load_tasks, split_tasks


def _extract_repo_name(repo_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL or pass-through if already in that form."""
    url = repo_url.rstrip("/")
    if "github.com" in url:
        parts = url.split("github.com/")[-1].split("/")
        return f"{parts[0]}/{parts[1]}"
    # Assume already "owner/repo" or "repo"
    return url


def run(
    repo_url: str,
    output_dir: str = ".claude/skills",
    max_evals: int = 150,
    use_initial_skill: bool = True,
    agent_model: str | None = None,
) -> object:
    """Run the full gskill pipeline for a repository.

    Args:
        repo_url: GitHub repository URL (e.g., 'https://github.com/pallets/jinja').
        output_dir: Directory to write the optimized SKILL.md.
        max_evals: GEPA evaluation budget (number of mini runs).
        use_initial_skill: If True, generate an initial skill via Claude as the seed.
            If False, start GEPA from an empty seed.
        agent_model: LiteLLM model string for mini-SWE-agent. Falls back to
            ``GSKILL_AGENT_MODEL`` env var, then ``openai/gpt-5.2``.

    Returns:
        GEPA result object with ``best_candidate`` and ``best_score`` attributes.
    """
    repo_name = _extract_repo_name(repo_url)
    print(f"[gskill] Repo: {repo_name}")

    print("[gskill] Loading tasks from SWE-smith...")
    tasks = load_tasks(repo_name)
    train, val, test = split_tasks(tasks)
    print(f"[gskill] Tasks: {len(train)} train / {len(val)} val / {len(test)} test")

    seed_skill: str | None = None
    if use_initial_skill:
        print("[gskill] Generating initial skill via GPT-5.2...")
        seed_skill = generate_initial_skill(repo_url)
        print(f"[gskill] Initial skill ({len(seed_skill)} chars) generated.")

    else:
        print("[gskill] Skipping initial skill generation (--no-initial-skill).")

    evaluator = make_evaluator(agent_model=agent_model)

    print(f"[gskill] Starting GEPA optimization (max_evals={max_evals})...")
    result = optimize_anything(
        seed_candidate=seed_skill,
        evaluator=evaluator,
        dataset=train,
        valset=val,
        objective=(
            "Maximize the resolve rate on software engineering tasks "
            f"for the {repo_name} repository. "
            "The skill should help the coding agent understand the repo's test commands, "
            "code structure, and common patterns."
        ),
        config=GEPAConfig(
            engine=EngineConfig(
                max_metric_calls=max_evals,
                raise_on_exception=False,
            ),
        ),
    )

    best_score = result.val_aggregate_scores[result.best_idx]
    out_path = save_skill(result.best_candidate, repo_name, output_dir)
    print(f"[gskill] Best resolve rate: {best_score:.1%}")
    print(f"[gskill] Skill saved to: {out_path}")
    return result
