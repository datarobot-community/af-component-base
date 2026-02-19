#!/usr/bin/env python3
# /// script
# dependencies = ["litellm", "python-dotenv"]
# ///
"""Generate, update, and evaluate AGENTS.md files via the DataRobot LLM Gateway.

Run from the project root via the Taskfile task:

    task agents-md                                    # generate/update root AGENTS.md
    task agents-md -- --dir mcp_server                # generate/update a sub-project
    task agents-md -- --dry-run                       # preview without writing
    task agents-md -- --dir agent --test              # evaluate the AGENTS.md on disk
    task agents-md -- --dir agent --revise            # apply/defend test feedback, rewrite AGENTS.md
    task agents-md -- --no-copilot                    # skip .github/copilot-instructions.md

Or invoke directly from the project root (uv auto-installs dependencies):

    uv run scripts/generate_agents_md.py [options]

Environment variables (all optional — set in .env to persist):

    DATAROBOT_API_TOKEN      Required. DataRobot API token.
    DATAROBOT_ENDPOINT       DataRobot endpoint URL. Default: https://app.datarobot.com/api/v2
    LLM_DEPLOYMENT_ID        If set, routes LLM calls through a specific deployed model.
    AGENTS_MD_MODEL          Generation model. Default: datarobot/anthropic/claude-opus-4-5-20251101
    AGENTS_MD_TEST_MODEL     Evaluation model. Default: datarobot/anthropic/claude-sonnet-4-5-20250929

Using separate models for generation and evaluation avoids the blind spot of a
model critiquing its own output. Override either with --model / --test-model flags.

On every run (unless --no-copilot) the script also aggregates all AGENTS.md files
in the repo into .github/copilot-instructions.md for GitHub Copilot support.

Generated content is wrapped in <!-- AGENTS:GENERATED:START/END --> markers so that
custom content added outside those markers is preserved on subsequent regenerations.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment, misc]

try:
    import litellm
except ImportError:
    litellm = None  # type: ignore[assignment]

MARKER_START = "<!-- AGENTS:GENERATED:START -->"
MARKER_END = "<!-- AGENTS:GENERATED:END -->"

DEFAULT_MODEL = "datarobot/anthropic/claude-opus-4-5-20251101"
DEFAULT_TEST_MODEL = "datarobot/anthropic/claude-sonnet-4-5-20250929"

# Files to read in full (capped at MAX_FILE_BYTES each)
PRIORITY_FILES = [
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "package.json",
    "Taskfile.yml",
    "Taskfile.yaml",
    "copier.yml",
    "copier.yaml",
]

# Directories to always exclude from file listings
EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "dist", "build",
    ".mypy_cache", ".ruff_cache", "htmlcov", ".data", "tmp",
}

MAX_TREE_FILES = 80
MAX_ANSWERS_FILES = 5



# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------

def _read_safe(path: Path) -> str:
    """Read a file, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _git_tracked_files(repo_root: Path) -> list[str]:
    """Return list of git-tracked file paths relative to repo_root."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        return [f for f in result.stdout.splitlines() if f]
    except Exception:
        return []


def _build_tree(files: list[str], target_subdir: str | None) -> str:
    """Build a compact directory tree string from a list of paths."""
    if target_subdir:
        prefix = target_subdir.rstrip("/") + "/"
        files = [f[len(prefix):] for f in files if f.startswith(prefix)]

    dirs: dict[str, list[str]] = {}
    for f in files:
        parts = f.split("/")
        top = parts[0] if len(parts) > 1 else ""
        dirs.setdefault(top, []).append(f)

    lines = []
    for d, members in sorted(dirs.items()):
        if d and d in EXCLUDE_DIRS:
            continue
        if d:
            lines.append(f"  {d}/")
            for m in sorted(members)[:8]:
                lines.append(f"    {m.split('/', 1)[-1]}")
            if len(members) > 8:
                lines.append(f"    ... ({len(members) - 8} more)")
        else:
            for m in sorted(members):
                lines.append(f"  {m}")

    return "\n".join(lines[:MAX_TREE_FILES])


def gather_context(target_dir: Path, repo_root: Path) -> dict:
    """Gather structured context about a directory for the prompt."""
    rel = str(target_dir.relative_to(repo_root)) if target_dir != repo_root else "."
    all_files = _git_tracked_files(repo_root)
    tree = _build_tree(all_files, None if rel == "." else rel)

    # Read priority files in full
    file_contents: dict[str, str] = {}
    search_dir = target_dir
    for name in PRIORITY_FILES:
        candidate = search_dir / name
        if candidate.exists():
            content = _read_safe(candidate)
            if content:
                file_contents[name] = content

    # Read .datarobot/answers/*.yml to understand component origins
    answers_dir = repo_root / ".datarobot" / "answers"
    answers: dict[str, str] = {}
    if answers_dir.exists():
        for yml in sorted(answers_dir.glob("*.yml"))[:MAX_ANSWERS_FILES]:
            content = _read_safe(yml)
            if content:
                answers[yml.name] = content

    # Check sibling sub-projects at root level if we're in a sub-dir
    sibling_agents_md: dict[str, str] = {}
    if rel != ".":
        for sibling in sorted(repo_root.iterdir()):
            if sibling.is_dir() and sibling != target_dir and sibling.name not in EXCLUDE_DIRS:
                agents = sibling / "AGENTS.md"
                if agents.exists():
                    sibling_agents_md[sibling.name] = _read_safe(agents)

    return {
        "target_dir": rel,
        "is_root": rel == ".",
        "tree": tree,
        "file_contents": file_contents,
        "copier_answers": answers,
        "sibling_agents_md": sibling_agents_md,
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_prompt(ctx: dict) -> str:
    parts = []

    if ctx["is_root"]:
        target_desc = "the ROOT of a monorepo"
        instruction = (
            "Generate a root-level AGENTS.md that:\n"
            "1. Maps the sub-project layout (what each directory is for)\n"
            "2. Lists cross-cutting commands (dev, test, lint, deploy)\n"
            "3. States where shell commands must be run from\n"
            "4. Describes the overall architecture / how services connect\n"
            "Do NOT repeat sub-project-specific details that belong in sub-directory AGENTS.md files."
        )
    else:
        target_desc = f"the `{ctx['target_dir']}/` sub-project"
        instruction = (
            "Generate a sub-project AGENTS.md that:\n"
            "1. States what this sub-project does in 1-2 sentences\n"
            "2. Lists the key directories/files to modify (and what NOT to touch)\n"
            "3. Explains the main conventions and patterns specific to this sub-project\n"
            "4. Lists the exact `dr task run` commands for install/test/lint/dev\n"
            "5. Notes any critical constraints (e.g. generated files, locked methods)\n"
            "Be specific and actionable. Avoid restating obvious things."
        )

    parts.append(
        f"You are an expert software engineer writing AGENTS.md files for AI coding assistants.\n"
        f"AGENTS.md files guide AI agents working in a codebase — what to modify, what patterns to follow, "
        f"and what commands to run.\n\n"
        f"IMPORTANT: This file will be loaded into the context window of many different AI coding tools, "
        f"including models with small context windows. Write it to be as dense and useful "
        f"as possible within a tight budget — every line must earn its place. Prefer bullet points over prose. "
        f"Do not pad, repeat, or over-explain. A smaller model reading only this file should be able to work "
        f"effectively in the codebase.\n\n"
        f"Target: {target_desc}\n\n"
        f"{instruction}\n\n"
        f"Output ONLY the markdown content. No preamble, no explanation."
    )

    parts.append(f"\n## Directory structure\n```\n{ctx['tree']}\n```")

    for fname, content in ctx["file_contents"].items():
        if fname == "AGENTS.md":
            parts.append(f"\n## Existing AGENTS.md (for reference / update)\n```markdown\n{content}\n```")
        else:
            parts.append(f"\n## {fname}\n```\n{content}\n```")

    if ctx["copier_answers"]:
        parts.append("\n## Component origins (.datarobot/answers/)")
        for name, content in ctx["copier_answers"].items():
            parts.append(f"### {name}\n```yaml\n{content}\n```")

    if ctx["sibling_agents_md"]:
        parts.append("\n## Sibling sub-project AGENTS.md files (for context/consistency)")
        for name, content in ctx["sibling_agents_md"].items():
            parts.append(f"### {name}/AGENTS.md\n```markdown\n{content}\n```")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Test / evaluation mode
# ---------------------------------------------------------------------------

def build_test_prompt(agents_md_content: str, ctx: dict, label: str) -> str:
    """
    Build a prompt that asks the LLM to roleplay as a fresh agent reading
    the AGENTS.md and then critique it based on what was and wasn't useful.
    """
    target = ctx["target_dir"] if not ctx["is_root"] else "the repository root"
    return f"""\
You are an AI coding assistant that has just been assigned to work in {target} of an unfamiliar codebase for the first time. You have no prior context beyond what is provided below.

You have been handed the following AGENTS.md file ({label}) which is supposed to orient you:

<agents_md>
{agents_md_content}
</agents_md>

The actual directory structure of {target} is:
```
{ctx["tree"]}
```

## Your task

Simulate being a first-time agent using this AGENTS.md to complete real work. Go through each of the following scenarios mentally and report what happens:

1. **Orient yourself** — After reading the AGENTS.md, do you know what this sub-project does, what its role is in the larger system, and which files you should look at first? What's still unclear?

2. **Make a change** — A user asks you to add a new feature to this sub-project. Do you know which files to modify? Which to avoid? Are there patterns or conventions you need to follow that are (or aren't) explained?

3. **Run the development loop** — Do you have enough information to install dependencies, run tests, and start the dev server? Would any command fail or be ambiguous?

4. **Avoid mistakes** — Are there footguns, generated files, locked methods, or "do not touch" areas that the AGENTS.md warns you about? Did you feel confident you wouldn't break something?

5. **Identify gaps** — What questions do you still have after reading the AGENTS.md that you'd have to go grep the codebase to answer?

## Output format

Respond with a structured critique report in markdown with these sections:

### What worked well
Specific things the AGENTS.md got right that would save a coding agent time.

### What was unclear or missing
Concrete gaps — things you had to guess at or would need to search the codebase for. For each gap, suggest exactly what text would fix it.

### Commands or instructions that need fixing
Any commands that look wrong, incomplete, or that would fail. Suggest the corrected version.

### Suggested additions
New sections or content that would meaningfully improve agent effectiveness. Be specific — write the actual text where possible.

### Overall verdict
One of: GOOD (minor tweaks only) / NEEDS WORK (several meaningful gaps) / INCOMPLETE (a new agent would be lost).
One sentence explaining why.
"""


def run_test(
    target_dir: Path,
    repo_root: Path,
    model: str,
    test_model: str,
    endpoint: str,
    api_key: str,
) -> None:
    """Evaluate the AGENTS.md on disk by asking the LLM to roleplay as a fresh agent."""
    ctx = gather_context(target_dir, repo_root)

    agents_md_path = target_dir / "AGENTS.md"
    if not agents_md_path.exists():
        print(f"❌ No AGENTS.md found at {agents_md_path}", file=sys.stderr)
        sys.exit(1)

    agents_md_content = _strip_markers(agents_md_path.read_text())

    print(f"🧪 Evaluating AGENTS.md for {ctx['target_dir']}")
    print(f"💬 Evaluating with [{test_model}]...")

    test_prompt = build_test_prompt(agents_md_content, ctx, "as it exists on disk")
    report = call_llm(test_prompt, test_model, endpoint, api_key)

    # Save report so --revise can read it
    report_path = _report_path(target_dir)
    report_path.write_text(report)

    print(f"\n{'='*60}")
    print(f"AGENTS.md TEST REPORT — {ctx['target_dir']}")
    print(f"{'='*60}\n")
    print(report)
    print(f"\n💾 Report saved to {report_path} — run with --revise to apply feedback.")


# ---------------------------------------------------------------------------
# Revise mode
# ---------------------------------------------------------------------------

def _report_path(target_dir: Path) -> Path:
    return target_dir / ".agents-md-report.md"


def _revision_notes_path(target_dir: Path) -> Path:
    return target_dir / ".agents-md-revision-notes.md"


def build_revise_prompt(agents_md_content: str, report: str, ctx: dict) -> str:
    target = ctx["target_dir"] if not ctx["is_root"] else "the repository root"
    return f"""\
You are an expert software engineer. You wrote the following AGENTS.md for {target}:

<agents_md>
{agents_md_content}
</agents_md>

A peer reviewer — acting as a first-time agent reading this file — gave the following critique:

<critique>
{report}
</critique>

Your task:
1. For each critique point that is **valid and actionable**, incorporate the fix into the AGENTS.md.
2. For each critique point that is **wrong, already covered, or not relevant**, note it in the revision notes (not in the AGENTS.md itself).
3. Output your response in exactly this format — two sections separated by the delimiter:

===AGENTS_MD===
<the complete, updated AGENTS.md — clean markdown only, no reviewer comments>
===REVISION_NOTES===
<a brief list of which critique points you rejected and why, in plain markdown>

Maintain the existing style and structure. Do not pad with unnecessary content.
"""


def run_revise(
    target_dir: Path,
    repo_root: Path,
    model: str,
    endpoint: str,
    api_key: str,
    dry_run: bool,
) -> str:
    """Read the saved test report and ask the model to update AGENTS.md or defend against each point."""
    report_path = _report_path(target_dir)
    if not report_path.exists():
        print(f"❌ No test report found at {report_path}. Run --test first.", file=sys.stderr)
        sys.exit(1)

    agents_md_path = target_dir / "AGENTS.md"
    if not agents_md_path.exists():
        print(f"❌ No AGENTS.md found at {agents_md_path}", file=sys.stderr)
        sys.exit(1)

    report = report_path.read_text()
    agents_md_content = _strip_markers(agents_md_path.read_text())
    ctx = gather_context(target_dir, repo_root)

    print(f"✏️  Revising AGENTS.md for {ctx['target_dir']} based on test report...")
    print(f"💬 Revising with [{model}]...")

    prompt = build_revise_prompt(agents_md_content, report, ctx)
    raw = call_llm(prompt, model, endpoint, api_key)

    # Split on delimiter
    if "===AGENTS_MD===" in raw and "===REVISION_NOTES===" in raw:
        agents_part = raw.split("===AGENTS_MD===")[1].split("===REVISION_NOTES===")[0].strip()
        notes_part = raw.split("===REVISION_NOTES===")[1].strip()
    else:
        # Model didn't follow format — treat entire response as the AGENTS.md
        agents_part = raw.strip()
        notes_part = "(Model did not produce separate revision notes.)"

    if notes_part and not dry_run:
        notes_path = _revision_notes_path(target_dir)
        notes_path.write_text(notes_part)
        print(f"📝 Revision notes saved to {notes_path}")

    return agents_part


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(prompt: str, model: str, endpoint: str, api_key: str) -> str:
    """Call the DataRobot LLM Gateway via litellm."""
    # Strip /api/v2 suffix — litellm's DataRobot provider constructs the full URL
    base_url = endpoint.rstrip("/")
    if base_url.endswith("/api/v2"):
        base_url = base_url[: -len("/api/v2")]

    deployment_id = os.environ.get("LLM_DEPLOYMENT_ID")
    if deployment_id:
        api_base = f"{base_url}/api/v2/deployments/{deployment_id}/chat/completions"
        call_model = "datarobot/datarobot-deployed-llm"
    else:
        api_base = f"{base_url}/"
        call_model = model

    response = litellm.completion(
        model=call_model,
        messages=[{"role": "user", "content": prompt}],
        api_base=api_base,
        api_key=api_key,
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            f"Model {call_model} returned an empty response. "
            "Try a different model via --model / --test-model or AGENTS_MD_MODEL / AGENTS_MD_TEST_MODEL."
        )
    return content.strip()


# ---------------------------------------------------------------------------
# Copilot instructions aggregation
# ---------------------------------------------------------------------------

_COPILOT_HEADER = """\
<!-- This file is auto-generated by scripts/generate_agents_md.py — do not edit manually.
     Re-run `task agents-md` to update. Source of truth is the per-directory AGENTS.md files. -->
"""

_COPILOT_PATH = Path(".github") / "copilot-instructions.md"


def _strip_markers(text: str) -> str:
    """Remove AGENTS:GENERATED marker comments from content."""
    text = text.replace(MARKER_START + "\n", "").replace(MARKER_START, "")
    text = text.replace("\n" + MARKER_END, "").replace(MARKER_END, "")
    # Strip the "add custom content" comment line
    lines = [
        ln for ln in text.splitlines()
        if not ln.strip().startswith("<!-- Add custom content below")
    ]
    return "\n".join(lines).strip()


def write_copilot_instructions(repo_root: Path, dry_run: bool) -> None:
    """Aggregate all AGENTS.md files into .github/copilot-instructions.md."""
    # Collect: root first, then sub-dirs alphabetically
    candidates: list[tuple[str, Path]] = []
    root_agents = repo_root / "AGENTS.md"
    if root_agents.exists():
        candidates.append(("Repository Overview", root_agents))

    for entry in sorted(repo_root.iterdir()):
        if not entry.is_dir() or entry.name in EXCLUDE_DIRS or entry.name.startswith("."):
            continue
        sub_agents = entry / "AGENTS.md"
        if sub_agents.exists():
            candidates.append((f"{entry.name}/", sub_agents))

    if not candidates:
        print("ℹ️  No AGENTS.md files found — skipping copilot-instructions.md")
        return

    sections = [_COPILOT_HEADER.rstrip()]
    for label, path in candidates:
        content = _strip_markers(path.read_text()).strip()
        if content:
            sections.append(f"\n---\n\n## {label}\n\n{content}")

    result = "\n".join(sections) + "\n"
    dest = repo_root / _COPILOT_PATH

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — would write to: {dest}")
        print(f"{'='*60}\n")
        print(result)
    else:
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(result)
        print(f"✅ Written: {dest}")


# ---------------------------------------------------------------------------
# File writing with marker-based update
# ---------------------------------------------------------------------------

def _clean_generated(text: str) -> str:
    """Strip markdown code fences and any AGENTS markers the LLM may have included."""
    text = text.strip()
    # Strip wrapping ```markdown ... ``` or ``` ... ``` fences
    for fence in ("```markdown", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            break
    # Strip any markers the LLM echoed back
    text = _strip_markers(text)
    return text.strip()


def apply_generated_content(existing: str, generated: str) -> str:
    """
    If the existing file has marker blocks, replace only the generated section.
    Otherwise wrap the generated content in markers.
    Uses rindex for MARKER_END to find the outermost closing marker.
    """
    if MARKER_START in existing and MARKER_END in existing:
        before = existing[: existing.index(MARKER_START)]
        after = existing[existing.rindex(MARKER_END) + len(MARKER_END):]
        return f"{before}{MARKER_START}\n{generated}\n{MARKER_END}{after}"

    # No markers — wrap the generated content; preserve any existing custom content below
    custom_note = (
        "\n\n<!-- Add custom content below this line. "
        "It will be preserved when AGENTS.md is regenerated. -->\n"
    )
    return f"{MARKER_START}\n{generated}\n{MARKER_END}{custom_note}"


def write_agents_md(target_dir: Path, generated: str, dry_run: bool) -> None:
    agents_md = target_dir / "AGENTS.md"
    existing = agents_md.read_text() if agents_md.exists() else ""
    result = apply_generated_content(existing, _clean_generated(generated))

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — would write to: {agents_md}")
        print(f"{'='*60}\n")
        print(result)
    else:
        agents_md.write_text(result)
        print(f"✅ Written: {agents_md}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or update AGENTS.md via DataRobot LLM")
    parser.add_argument(
        "--dir",
        default=".",
        help="Target directory (root or sub-project). Default: current directory.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"LiteLLM model name. Default: $AGENTS_MD_MODEL or {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated content without writing.",
    )
    parser.add_argument(
        "--no-copilot",
        action="store_true",
        help="Skip writing .github/copilot-instructions.md.",
    )
    parser.add_argument(
        "--test-model",
        default=None,
        help=(
            f"Model to use for --test evaluation. "
            f"Default: $AGENTS_MD_TEST_MODEL or {DEFAULT_TEST_MODEL}"
        ),
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Evaluate the AGENTS.md on disk by simulating a fresh agent reading it. "
            "Prints and saves a critique report. Does not write any files."
        ),
    )
    parser.add_argument(
        "--revise",
        action="store_true",
        help=(
            "Read the saved test report (from --test) and ask the model to update "
            "AGENTS.md based on valid feedback, or add inline comments defending against "
            "points it disagrees with. Requires --test to have been run first."
        ),
    )
    args = parser.parse_args()

    # litellm is required for all operations; fail early with guidance
    if litellm is None:
        print(
            "❌ litellm is not installed. Run:\n"
            "   uv run scripts/generate_agents_md.py [options]\n"
            "to auto-install (PEP 723), or:\n"
            "   pip install litellm python-dotenv",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load .env from CWD (script is run from project root via Taskfile)
    if load_dotenv:
        load_dotenv(dotenv_path=Path(".env"), override=False)

    api_key = os.environ.get("DATAROBOT_API_TOKEN")
    endpoint = os.environ.get("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2")
    model = args.model or os.environ.get("AGENTS_MD_MODEL", DEFAULT_MODEL)
    test_model = args.test_model or os.environ.get("AGENTS_MD_TEST_MODEL", DEFAULT_TEST_MODEL)

    if not api_key:
        print("❌ DATAROBOT_API_TOKEN not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    # Resolve paths
    cwd = Path.cwd()
    target_dir = (cwd / args.dir).resolve()
    # Repo root is wherever .git lives — walk up from cwd
    repo_root = cwd
    while not (repo_root / ".git").exists() and repo_root != repo_root.parent:
        repo_root = repo_root.parent

    if not target_dir.is_dir():
        print(f"❌ Not a directory: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 Target:     {target_dir.relative_to(repo_root)}")
    print(f"🏠 Repo root:  {repo_root}")
    print(f"🤖 Model:      {model}")

    if args.test:
        run_test(target_dir, repo_root, model, test_model, endpoint, api_key)
        return

    if args.revise:
        revised = run_revise(target_dir, repo_root, model, endpoint, api_key, dry_run=args.dry_run)
        write_agents_md(target_dir, revised, dry_run=args.dry_run)
        if not args.no_copilot and not args.dry_run:
            print("📋 Updating .github/copilot-instructions.md...")
            write_copilot_instructions(repo_root, dry_run=False)
        return

    print("⏳ Gathering context...")
    ctx = gather_context(target_dir, repo_root)

    print("💬 Calling LLM gateway...")
    prompt = build_prompt(ctx)
    generated = call_llm(prompt, model, endpoint, api_key)

    write_agents_md(target_dir, generated, dry_run=args.dry_run)

    if not args.no_copilot:
        print("📋 Updating .github/copilot-instructions.md...")
        write_copilot_instructions(repo_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
