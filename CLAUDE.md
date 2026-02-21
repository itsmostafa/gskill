# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`gskill` automatically learns repository-specific skills for coding agents via evolutionary search. It:
1. Loads SWE-smith tasks for a target GitHub repository
2. Optionally generates an initial `SKILL.md` via gpt-5.2
using the repo's README and config files
3. Uses GEPA (evolutionary prompt optimization) with mini-SWE-Agent to iteratively improve the skill
4. Saves the best-scoring `SKILL.md` to `.claude/skills/<repo>/SKILL.md`

## Project Management

This project uses **uv** for Python package and environment management (Python 3.13). Do not use `pip`, `python`, or manual venv activation directly.

```bash
uv run main.py <repo-url>   # Run the main pipeline
uv add <package>            # Add a dependency
uv remove <package>         # Remove a dependency
uv sync                     # Install dependencies from lockfile
uv run pytest               # Run tests
uv run ruff check .         # Lint
uv run ruff format .        # Format
```

## Entry Point & CLI

`main.py` is the CLI entry point (registered as the `gskill` script). It exposes two Typer commands:

- `gskill run <repo-url>` — run the full optimization pipeline
  - `--output-dir` / `-o`: where to write `SKILL.md` (default: `.claude/skills`)
  - `--max-evals` / `-n`: GEPA evaluation budget (default: 150)
  - `--no-initial-skill`: skip gpt-5.2 seed generation, start GEPA from empty
- `gskill tasks <owner/repo>` — list available SWE-smith tasks for a repo
  - `--limit` / `-l`: number of tasks to show (default: 10)
  - `--list`: list all tasks up to limit

## Project Structure

```
gskill/
├── main.py           # CLI entry point (Typer app, two commands: run + tasks)
├── gskill/
│   ├── __init__.py   # Empty package init
│   ├── pipeline.py   # Top-level orchestration: load tasks → generate seed → GEPA → save
│   ├── skill.py      # Initial skill generation (gpt-5.2 via OpenAI) + save_skill()
│   ├── tasks.py      # SWE-smith dataset loading and train/val/test splitting
│   └── evaluator.py  # GEPA-compatible evaluator: runs mini-SWE-Agent + Docker test verification
└── pyproject.toml    # Dependencies: typer, openai, datasets, mini-swe-agent, gepa (git)
```

## Key Dependencies

- **gepa** (git): evolutionary prompt optimization framework — `optimize_anything()` drives the search
- **mini-swe-agent**: runs the coding agent inside Docker SWE-bench containers
- **openai**: used in `skill.py` for gpt-5.2 initial skill generation (requires `OPENAI_API_KEY`)
- **datasets**: loads `SWE-bench/SWE-smith` from HuggingFace Hub
- **typer**: CLI framework

## External Requirements

- Docker must be running — `evaluator.py` spins up SWE-bench Docker containers to verify patches
- `OPENAI_API_KEY` env var for initial skill generation (skippable via `--no-initial-skill`)

## Module Responsibilities

- **`pipeline.py`**: Parses repo URL → loads tasks → calls `generate_initial_skill` → builds GEPA evaluator → runs `optimize_anything` → saves best skill
- **`skill.py`**: Fetches README + config files from GitHub API; calls gpt-5.2 to generate initial `SKILL.md`; `save_skill()` writes to `<output_dir>/<repo>/SKILL.md`
- **`tasks.py`**: Loads `SWE-bench/SWE-smith` dataset, filters by repo slug (`owner__repo`), splits 67/17/16% train/val/test
- **`evaluator.py`**: `make_evaluator()` returns a GEPA-compatible `(candidate, task) → (score, info)` function; runs mini-SWE-Agent with the candidate skill injected into the system prompt, applies the resulting patch in Docker, runs `FAIL_TO_PASS` tests (up to 10), returns 1.0 if all pass
