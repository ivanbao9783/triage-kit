"""Task directory validation, multi-step detection and file-tree rendering."""

from pathlib import Path


def _is_multi_step(task_dir: Path) -> bool:
    return (task_dir / "steps").is_dir()


def validate_task_dir(path: Path) -> list[str]:
    """Harbor TaskPaths.is_valid equivalent. Empty list = valid."""
    path = Path(path)
    errors: list[str] = []
    if not (path / "task.toml").is_file():
        errors.append(f"missing task.toml in {path}")

    if _is_multi_step(path):
        steps = detect_steps(path)
        if not steps:
            errors.append("steps/ exists but contains no valid step directories")
    elif not (path / "environment").is_dir():
        errors.append(f"missing environment/ in {path}")
    return errors


def detect_steps(path: Path) -> list[Path]:
    """Step sub-directories under steps/, each holding an instruction.md."""
    steps_dir = Path(path) / "steps"
    if not steps_dir.is_dir():
        return []
    return sorted(
        d for d in steps_dir.iterdir() if d.is_dir() and (d / "instruction.md").is_file()
    )


def render_file_tree(path: Path, *, max_depth: int | None = None,
                     max_entries: int | None = None) -> str:
    """Render a directory tree as indented text (uses '/' separators).

    max_depth caps directory nesting (directories cut by it get a
    "... (deeper entries omitted)" marker under them); max_entries caps
    the total number of listed entries (the remainder is summarized as a
    final "... N more entries omitted" line). Truncation is always
    annotated, never silent — the model must know the tree was cut and
    explore with tools instead.
    """
    root = Path(path)
    if not root.exists():
        return ""

    all_entries: list[tuple[Path, int]] = []

    def collect(dir_path: Path, depth: int) -> None:
        for entry in sorted(
            dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        ):
            all_entries.append((entry, depth))
            if entry.is_dir():
                collect(entry, depth + 1)

    collect(root, 1)

    depth_ok = [
        (entry, depth) for entry, depth in all_entries
        if max_depth is None or depth <= max_depth
    ]
    if max_entries is None or len(depth_ok) <= max_entries:
        kept, hidden = depth_ok, 0
    else:
        kept, hidden = depth_ok[:max_entries], len(depth_ok) - max_entries

    lines: list[str] = []
    for entry, depth in kept:
        lines.append("  " * (depth - 1) + entry.name)
        if (
            max_depth is not None
            and entry.is_dir()
            and depth == max_depth
            and any(entry.iterdir())
        ):
            lines.append("  " * depth + "... (deeper entries omitted)")
    if hidden:
        lines.append(f"... ({hidden} more entries omitted)")
    return "\n".join(lines)
