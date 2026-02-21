# gskill

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
- `ANTHROPIC_API_KEY` set in your environment (for initial skill generation and GEPA reflection)

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
- Generate an initial skill via Claude
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
```

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

## Project structure

```
gskill/
├── main.py              # CLI entry point (typer)
├── gskill/
│   ├── pipeline.py      # Top-level orchestration
│   ├── tasks.py         # SWE-smith dataset loading & splitting
│   ├── evaluator.py     # mini runner + pass/fail evaluation
│   └── skill.py         # Initial skill generation (Claude) + file I/O
└── pyproject.toml
```
