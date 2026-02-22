# gskill

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude](https://img.shields.io/badge/Claude-D97757?logo=claude&logoColor=fff)](https://claude.ai/code)
![Last Commit](https://img.shields.io/github/last-commit/itsmostafa/gskill)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/itsmostafa/gskill/pulls)

Automatically learns repository-specific skills for coding agents using evolutionary search.

Given a GitHub repository, gskill produces a `.claude/skills/{repo}/SKILL.md` file containing optimized instructions that dramatically improve an agent's resolve rate on that repo's issues. It implements the pipeline described in the [GEPA blog post](https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/), which demonstrated improvements from 24% → 93% resolve rate on some repositories.

## How it works

1. Loads verifiable software engineering tasks from [SWE-smith](https://huggingface.co/datasets/SWE-bench/SWE-smith) for the target repository
2. Generates an initial skill via static analysis of the repo (README, config files) + gpt 5.2.
3. Uses [GEPA](https://github.com/gepa-ai/gepa)'s `optimize_anything` to iteratively refine the skill through evolutionary search
4. Each candidate skill is evaluated by running [mini-SWE-agent](https://mini-swe-agent.com) on training tasks inside Docker and checking whether the FAIL_TO_PASS tests pass
5. Writes the best-scoring skill to disk

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (for running SWE-smith task environments)
- `OPENAI_API_KEY` set in your environment (for initial skill generation and GEPA reflection)
- `GSKILL_AGENT_MODEL` (optional) — LiteLLM model string for mini-SWE-agent (default: `openai/gpt-5.2`)

## Installation

```bash
git clone https://github.com/your-org/gskill
cd gskill
uv sync
```

## Usage

### Run the full pipeline

```bash
uv run python main.py run https://github.com/pallets/jinja
```

This will:
- Load SWE-smith tasks for `pallets/jinja`
- Generate an initial skill
- Run up to 150 mini evaluations to optimize the skill
- Write the result to `.claude/skills/jinja/SKILL.md`

### Common options

```bash
# Custom evaluation budget (more evals = better skill, slower run)
uv run python main.py run https://github.com/pallets/jinja --max-evals 300

# Custom output directory
uv run python main.py run https://github.com/pallets/jinja --output-dir ~/skills

# Skip static analysis, start from an empty seed
uv run python main.py run https://github.com/pallets/jinja --no-initial-skill

# Use a different model for the coding agent
uv run python main.py run https://github.com/pallets/jinja --agent-model openai/gpt-5-mini

# Use a local model (e.g. qwen2.5-coder running on localhost:11434)
OPENAI_BASE_URL=http://localhost:11434/v1 \
  uv run python main.py run https://github.com/pallets/jinja --agent-model openai/gpt-oss-120b
```

You can also set the agent model via the `GSKILL_AGENT_MODEL` environment variable instead of passing `--agent-model` every time.

### Preview available tasks

```bash
# Show the first 10 SWE-smith tasks for a repo
uv run python main.py tasks pallets/jinja

# Show more
uv run python main.py tasks pallets/jinja --limit 25
```

### Help

```bash
uv run python main.py --help
uv run python main.py run --help
uv run python main.py tasks --help
```

## Output

The optimized skill is written to:

```
.claude/skills/{repo}/SKILL.md
```

To use it with Claude Code, add the skill path to your project's `.claude/settings.json` or reference it from your `CLAUDE.md`.

## Task runner

A [Taskfile.yml](Taskfile.yml) provides shortcuts for common operations (requires [Task](https://taskfile.dev)):

```bash
task sync                # uv sync
task lint                # ruff check
task format              # ruff format
task test                # pytest
task run -- owner/repo   # gskill run (pass args via CLI_ARGS)
task tasks               # gskill tasks (pass args via CLI_ARGS)
```

## Project structure

```
gskill/
├── main.py              # CLI entry point (typer)
├── src/
│   ├── pipeline.py      # Top-level orchestration
│   ├── tasks.py         # SWE-smith dataset loading & splitting
│   ├── evaluator.py     # mini runner + pass/fail evaluation
│   └── skill.py         # Initial skill generation (gpt-5.2) + file I/O
├── Taskfile.yml         # Task runner shortcuts
└── pyproject.toml
```
