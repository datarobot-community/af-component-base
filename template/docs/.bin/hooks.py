"""properdocs hook: generate docs/README.md with LLM-friendly TOC on every build."""

import re
from pathlib import Path

EXCLUDED_NAMES = {"README.md", "Taskfile.yaml", "Taskfile.yml"}


def _get_doc_files(docs_dir: Path) -> list[Path]:
    doc_files = []
    for item in sorted(docs_dir.iterdir()):
        if item.name in EXCLUDED_NAMES or item.name.startswith("."):
            continue
        if item.is_file() and item.suffix == ".md":
            doc_files.append(item)
        elif item.is_dir():
            readme = item / "README.md"
            if readme.exists():
                doc_files.append(readme)
            for subfile in sorted(item.iterdir()):
                if subfile.is_file() and subfile.suffix == ".md" and subfile != readme:
                    doc_files.append(subfile)
    return doc_files


def _extract_title(content: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _extract_description(content: str) -> str:
    """Return the first non-heading, non-empty paragraph line."""
    in_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        return stripped
    return ""


def _build_readme(doc_files: list[Path], docs_dir: Path) -> str:
    toc_lines: list[str] = []
    docs_yaml: list[str] = []

    for doc_file in doc_files:
        content = doc_file.read_text(encoding="utf-8").strip()
        relative = doc_file.relative_to(docs_dir)
        fallback = relative.stem if relative.stem != "README" else relative.parent.name
        title = _extract_title(content, fallback)
        description = _extract_description(content)

        toc_lines.append(f"- [{title}]({relative})")
        if description:
            toc_lines.append(f"  {description}")

        docs_yaml.append(f"  - {relative}")

    toc = "\n".join(toc_lines)
    docs_list = "\n".join(docs_yaml)

    return f"""\
---
source: docs/
docs:
{docs_list}
---

# Documentation

## Table of Contents

{toc}
"""


def on_pre_build(config) -> None:
    """Generate docs/README.md before each build."""
    docs_dir = Path(config["docs_dir"])
    output_file = docs_dir / "README.md"

    doc_files = _get_doc_files(docs_dir)
    if not doc_files:
        return

    content = _build_readme(doc_files, docs_dir)

    # Skip write if content unchanged — prevents serve-mode rebuild loop
    if output_file.exists() and output_file.read_text(encoding="utf-8") == content:
        return

    output_file.write_text(content, encoding="utf-8")
    print(f"properdocs hook: generated README.md from {len(doc_files)} doc(s)")  # noqa: T201
