"""Initial skill generation via Claude and skill file I/O."""

import base64
import json
import urllib.request
from pathlib import Path

import openai


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


def generate_initial_skill(repo_url: str) -> str:
    """Generate an initial SKILL.md for the repo via static analysis + Claude.

    Fetches the README and common config files, then asks Claude to synthesize
    repo-specific guidance for a coding agent.

    Args:
        repo_url: Full GitHub URL, e.g. 'https://github.com/pallets/jinja'.

    Returns:
        Skill content as a string (plain text / markdown).
    """
    # Parse owner/repo from URL
    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]

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

    client = openai.OpenAI()
    message = client.chat.completions.create(
        model="gpt-5.2",
        max_completion_tokens=2000,
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

Write a concise SKILL.md (400-800 words) that covers:

1. **Test commands**: The exact command(s) to run the test suite (e.g., `pytest`, `tox`, `make test`).
   If there are relevant flags or test file patterns, include them.
2. **Code structure**: Key directories and files an agent should know about.
3. **Conventions**: Code style, naming patterns, or idioms specific to this project.
4. **Common pitfalls**: Mistakes an agent typically makes on this repo and how to avoid them.
5. **Workflow**: Recommended steps to diagnose and fix an issue (reproduce, patch, verify).

Be specific and actionable. Write for an AI agent, not a human developer.
Do NOT include generic advice that applies to all Python projects.
Focus on what is distinctive about {repo}.""",
            }
        ],
    )
    return message.choices[0].message.content


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
