"""gskill CLI entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="gskill",
    help="Automatically learn repository-specific skills for coding agents.",
    add_completion=False,
)


@app.command()
def run(
    repo_url: str = typer.Argument(
        ..., help="GitHub repository URL, e.g. https://github.com/pallets/jinja"
    ),
    output_dir: str = typer.Option(
        ".claude/skills",
        "--output-dir",
        "-o",
        help="Directory to write the optimized SKILL.md.",
    ),
    max_evals: int = typer.Option(
        150,
        "--max-evals",
        "-n",
        help="GEPA evaluation budget (number of mini runs).",
    ),
    no_initial_skill: bool = typer.Option(
        False,
        "--no-initial-skill",
        help="Skip static analysis; start GEPA from an empty seed.",
    ),
    agent_model: str = typer.Option(
        "",
        "--agent-model",
        "-m",
        help="Model for mini-SWE-agent (e.g. openai/gpt-5.2). Env: GSKILL_AGENT_MODEL.",
    ),
    skill_model: str = typer.Option(
        "",
        "--skill-model",
        "-s",
        help="Model for initial skill generation (e.g. gpt-4o). Env: GSKILL_SKILL_MODEL.",
    ),
    base_url: str = typer.Option(
        "",
        "--base-url",
        "-u",
        help="OpenAI-compatible base URL for local models (e.g. http://localhost:11434/v1). Env: OPENAI_BASE_URL.",
    ),
) -> None:
    """Run the gskill pipeline: optimize a SKILL.md for the given repository."""
    from src.pipeline import run as _run

    _run(
        repo_url=repo_url,
        output_dir=output_dir,
        max_evals=max_evals,
        use_initial_skill=not no_initial_skill,
        agent_model=agent_model or None,
        skill_model=skill_model or None,
        base_url=base_url or None,
    )


@app.command()
def tasks(
    repo: str = typer.Argument(
        ...,
        help="Repository name in 'owner/repo' format, e.g. pallets/jinja",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Number of tasks to show.",
    ),
    list_all: bool = typer.Option(
        False,
        "--list",
        help="List all available tasks (up to --limit).",
    ),
) -> None:
    """List available SWE-smith tasks for a repository."""
    from src.tasks import load_tasks

    try:
        all_tasks = load_tasks(repo, n=300)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    shown = all_tasks[:limit]
    typer.echo(f"Found {len(all_tasks)} tasks for '{repo}' (showing {len(shown)}):\n")
    for t in shown:
        iid = t.get("instance_id", "?")
        stmt = t.get("problem_statement", "")[:120].replace("\n", " ")
        typer.echo(f"  {iid}")
        typer.echo(f"    {stmt}...")
        typer.echo()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
