"""Sandboxed file tools for the general harness: read_file / glob / grep.

Mirrors the Read/Glob/Grep semantics that the analyze/check prompts already
assume: relative paths resolve against cwd; absolute paths are allowed only
inside cwd or one of add_dirs. Errors are returned as "Error: ..." strings
(so the LLM loop can self-correct) instead of raising.
"""

import fnmatch
import re
from pathlib import Path


class PathSandbox:
    """Whitelist-based path resolver: cwd + add_dirs."""

    def __init__(self, cwd: Path, add_dirs: list[Path] | None = None):
        self.cwd = Path(cwd).resolve()
        self.roots = [self.cwd] + [Path(d).resolve() for d in (add_dirs or [])]

    def resolve(self, path: str) -> Path:
        """Resolve a path against cwd; raise PermissionError outside roots."""
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else self.cwd / candidate
        absolute = absolute.resolve()
        if not any(absolute == r or absolute.is_relative_to(r) for r in self.roots):
            raise PermissionError(f"path outside allowed roots: {path}")
        return absolute


class GeneralTools:
    """The three file tools exposed to the agent, all sandboxed."""

    def __init__(self, cwd: Path, add_dirs: list[Path] | None = None):
        self.sandbox = PathSandbox(cwd=cwd, add_dirs=add_dirs)
        self.cwd = self.sandbox.cwd

    # Claude Code Read parity: trajectory.json is often a single-line
    # multi-MB JSON where the line-count limit is a no-op, so overlong
    # lines must also be truncated (visibly).
    MAX_LINE_CHARS = 2000
    _TRUNCATION_MARKER = "... [line truncated]"
    # Refuse to slurp huge files into memory / the LLM context at all.
    MAX_FILE_BYTES = 10 * 1024 * 1024
    # Cap match output; truncation is annotated (never silent) so the
    # model knows to narrow the pattern instead of assuming completeness.
    MAX_GREP_MATCHES = 200

    def read_file(self, path: str, *, offset: int = 0, limit: int = 2000) -> str:
        try:
            absolute = self.sandbox.resolve(path)
        except PermissionError as e:
            return f"Error: {e}"
        try:
            if absolute.stat().st_size > self.MAX_FILE_BYTES:
                return (
                    f"Error: file too large to read ({path}, "
                    f"{absolute.stat().st_size} bytes > {self.MAX_FILE_BYTES}); "
                    f"use grep to locate specific content instead"
                )
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error: {e}"
        lines = text.splitlines()[offset : offset + limit]
        truncated = [
            line if len(line) <= self.MAX_LINE_CHARS
            else line[: self.MAX_LINE_CHARS] + self._TRUNCATION_MARKER
            for line in lines
        ]
        return "\n".join(truncated)

    def glob(self, pattern: str) -> str:
        matches = [
            str(p.relative_to(self.cwd))
            for r in self.sandbox.roots
            for p in r.glob(pattern)
            if p.is_file()
        ]
        seen: list[str] = []
        for m in matches:
            normalized = m.replace("\\", "/")
            if normalized not in seen:
                seen.append(normalized)
        if not seen:
            return "No files found."
        return "\n".join(sorted(seen))

    def grep(self, pattern: str, path: str = ".", glob: str | None = None) -> str:
        try:
            absolute = self.sandbox.resolve(path)
        except PermissionError as e:
            return f"Error: {e}"
        if not absolute.exists():
            return f"Error: path not found: {path}"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex: {e}"

        files = (
            [absolute]
            if absolute.is_file()
            else sorted(
                p for p in absolute.rglob("*") if p.is_file()
                and (glob is None or fnmatch.fnmatch(p.name, glob))
            )
        )
        results: list[str] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = self._display(f)
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    results.append(f"{rel}:{lineno}:{line}")
        if not results:
            return "No matches found."
        if len(results) > self.MAX_GREP_MATCHES:
            omitted = len(results) - self.MAX_GREP_MATCHES
            return "\n".join(
                results[: self.MAX_GREP_MATCHES]
                + [f"... ({omitted} more matches omitted)"]
            )
        return "\n".join(results)

    def _display(self, absolute: Path) -> str:
        """Relative to cwd when inside it; always '/'-separated."""
        try:
            rel = absolute.relative_to(self.cwd)
        except ValueError:
            return str(absolute)
        return "/".join(rel.parts)
