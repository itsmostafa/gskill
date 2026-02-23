"""Initial skill generation skill file I/O."""

import base64
import json
import os
import re
import urllib.request
from pathlib import Path

import openai


def _make_skill_name(repo: str) -> str:
    """Sanitize a repo short name into a valid skill name.

    Rules: lowercase, only [a-z0-9-], collapse/strip hyphens, max 64 chars.
    """
    name = repo.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name[:64]


def _fetch_readme(owner: str, repo: str, max_chars: int = 3000) -> str:
    """Fetch the README from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gskill/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            content = base64.b64decode(data["content"]).decode(
                "utf-8", errors="replace"
            )
            return content[:max_chars]
    except Exception:
        return ""


def _fetch_file(owner: str, repo: str, path: str, max_chars: int = 2000) -> str:
    """Fetch a specific file from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gskill/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode(
                    "utf-8", errors="replace"
                )
                return content[:max_chars]
    except Exception:
        pass
    return ""


def generate_initial_skill(
    repo_url: str,
    model: str | None = None,
    base_url: str | None = None,
) -> str:
    """Generate an initial SKILL.md for the repo via static analysis.

    Fetches the README and common config files, then asks a model to synthesize
    repo-specific guidance for a coding agent.

    Args:
        repo_url: Full GitHub URL, e.g. 'https://github.com/pallets/jinja'.
        model: Model to use. Defaults to GSKILL_SKILL_MODEL env var, then 'gpt-5.2'.
        base_url: OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL env var.

    Returns:
        Skill content as a string (YAML frontmatter + markdown body).
    """
    # Parse owner/repo from URL
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    skill_name = _make_skill_name(repo)

    readme = _fetch_readme(owner, repo)

    # Try to grab common config files for test/build info
    extra_context = ""
    for candidate in [
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        "Makefile",
        "pytest.ini",
    ]:
        content = _fetch_file(owner, repo, candidate, max_chars=1500)
        if content:
            extra_context += f"\n\n### {candidate}\n```\n{content}\n```"
            break  # one is enough

    resolved_base_url = base_url or os.environ.get("OPENAI_BASE_URL")
    resolved_model = model or os.environ.get("GSKILL_SKILL_MODEL")

    if resolved_base_url and not resolved_model:
        raise ValueError(
            "A custom base URL is set but no skill model was specified. "
            "Use --skill-model or set GSKILL_SKILL_MODEL to the model name your local backend serves."
        )

    resolved_model = resolved_model or "gpt-5.2"

    # Strip LiteLLM-style provider prefix (e.g. "openai/gpt-5.2" -> "gpt-5.2").
    # The OpenAI client talks to the endpoint directly, so the prefix is meaningless
    # and confuses non-OpenAI backends like Ollama.
    if "/" in resolved_model:
        resolved_model = resolved_model.split("/", 1)[1]

    client_kwargs: dict = {}
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url
    if not os.environ.get("OPENAI_API_KEY") and resolved_base_url:
        client_kwargs["api_key"] = "none"

    client = openai.OpenAI(**client_kwargs)
    try:
        message = client.chat.completions.create(
            model=resolved_model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""You are generating a SKILL.md for the '{repo}' repository.
This skill file will be injected into the system prompt of a coding agent that must
solve GitHub issues by modifying source files in a Docker container at /testbed.

Repository URL: {repo_url}

README (may be truncated):
{readme}
{extra_context}

Output a complete SKILL.md starting with YAML frontmatter, then the body. Use exactly this structure:

---
name: {skill_name}
description: <one-sentence description, max 1024 characters, no angle-bracket XML tags, stating what the skill covers and when to use it>
---

<body: 400-800 words covering the five sections below>

The body must cover:

1. **Test commands**: The exact command(s) to run the test suite (e.g., `pytest`, `tox`, `make test`).
   If there are relevant flags or test file patterns, include them.
2. **Code structure**: Key directories and files an agent should know about.
3. **Conventions**: Code style, naming patterns, or idioms specific to this project.
4. **Common pitfalls**: Mistakes an agent typically makes on this repo and how to avoid them.
5. **Workflow**: Recommended steps to diagnose and fix an issue (reproduce, patch, verify).

Constraints:
- The `name` field must be exactly: {skill_name}
- The `description` must be non-empty, at most 1024 characters, and must not contain angle-bracket XML tags.
- Be specific and actionable. Write for an AI agent, not a human developer.
- Do NOT include generic advice that applies to all Python projects.
- Focus on what is distinctive about {repo}.""",
                }
            ],
        )
    except openai.APIStatusError as exc:
        endpoint = resolved_base_url or "https://api.openai.com"
        raise RuntimeError(
            f"Skill generation failed — HTTP {exc.status_code} from {endpoint!r} "
            f"with model {resolved_model!r}: {exc.message}"
        ) from exc
    except openai.APIConnectionError as exc:
        endpoint = resolved_base_url or "https://api.openai.com"
        raise RuntimeError(
            f"Skill generation failed — could not connect to {endpoint!r}: {exc}"
        ) from exc

    content = message.choices[0].message.content
    if not content:
        raise RuntimeError(
            f"Skill generation failed — model {resolved_model!r} returned an empty response "
            "(the model may have invoked a tool instead of generating text, or the response was filtered)"
        )
    return content


def save_skill(skill: str, repo_name: str, output_dir: str = ".claude/skills") -> Path:
    """Write skill to {output_dir}/{short_repo_name}/SKILL.md.

    Args:
        skill: Skill content string.
        repo_name: 'owner/repo' or plain 'repo' name.
        output_dir: Base directory for skills (default: .claude/skills).

    Returns:
        Path to the written file.
    """
    short_name = repo_name.split("/")[-1]
    path = Path(output_dir) / short_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill)
    return path
