"""Tests for backends/general/tools.py — path sandbox + read/glob/grep.

Contract (mirrors the Claude SDK Read/Glob/Grep semantics the analyze
prompts already assume): relative paths resolve against cwd; absolute
paths are allowed only inside cwd or one of add_dirs.
"""

import pytest


@pytest.fixture
def env(tmp_path):
    cwd = tmp_path / "trial"
    (cwd / "agent").mkdir(parents=True)
    (cwd / "result.json").write_text('{"reward": 1}', encoding="utf-8")
    (cwd / "agent" / "trajectory.json").write_text(
        '[{"action": "edit"}]', encoding="utf-8"
    )

    extra = tmp_path / "task"
    extra.mkdir()
    (extra / "instruction.md").write_text("Do the thing.", encoding="utf-8")
    return cwd, extra


def make_tools(env, add_dirs=None):
    from triage_kit.backends.general.tools import GeneralTools

    cwd, extra = env
    return GeneralTools(cwd=cwd, add_dirs=add_dirs)


class TestReadFileLimits:
    """#5: Claude Code Read parity — line truncation + file size cap.

    trajectory.json in the Harbor ecosystem is often a single-line multi-MB
    JSON, which makes the 2000-line limit a no-op; char truncation is the
    actual defense."""

    def test_overlong_line_is_truncated_with_marker(self, env):
        tools = make_tools(env)
        cwd, _ = env
        giant = cwd / "oneline.json"
        giant.write_text("x" * 5000, encoding="utf-8")

        result = tools.read_file("oneline.json")

        assert len(result) < 2500                       # hard cap ~2000 chars
        assert result.endswith("[line truncated]")       # visible truncation

    def test_normal_lines_are_not_truncated(self, env):
        tools = make_tools(env)
        result = tools.read_file("agent/trajectory.json")
        assert result == '[{"action": "edit"}]'

    def test_multi_line_file_truncates_each_long_line(self, env):
        tools = make_tools(env)
        cwd, _ = env
        f = cwd / "wide.txt"
        f.write_text("short\n" + "y" * 4000 + "\n", encoding="utf-8")

        result = tools.read_file("wide.txt")

        lines = result.splitlines()
        assert len(lines) == 2
        assert lines[0] == "short"
        assert lines[1].endswith("[line truncated]")
        assert len(lines[1]) < 2500

    def test_oversize_file_is_rejected_with_grep_hint(self, env):
        tools = make_tools(env)
        cwd, _ = env
        huge = cwd / "huge.json"
        huge.write_text("[" + '{"a": "' + "z" * (11 * 1024 * 1024) + '"}]',
                        encoding="utf-8")

        result = tools.read_file("huge.json")

        assert result.startswith("Error:")
        assert "grep" in result.lower()


class TestPathSandbox:
    def test_relative_resolves_against_cwd(self, env):
        from triage_kit.backends.general.tools import PathSandbox

        cwd, _ = env
        sandbox = PathSandbox(cwd=cwd, add_dirs=None)
        assert sandbox.resolve("result.json") == cwd / "result.json"

    def test_absolute_inside_add_dir_is_allowed(self, env):
        from triage_kit.backends.general.tools import PathSandbox

        cwd, extra = env
        sandbox = PathSandbox(cwd=cwd, add_dirs=[extra])
        assert sandbox.resolve(str(extra / "instruction.md")) == (
            extra / "instruction.md"
        )

    def test_absolute_outside_roots_is_rejected(self, env, tmp_path):
        from triage_kit.backends.general.tools import PathSandbox

        cwd, _ = env
        secret = tmp_path / "secret.txt"
        secret.write_text("x", encoding="utf-8")
        sandbox = PathSandbox(cwd=cwd, add_dirs=None)
        with pytest.raises(PermissionError):
            sandbox.resolve(str(secret))

    def test_dotdot_traversal_is_rejected(self, env, tmp_path):
        from triage_kit.backends.general.tools import PathSandbox

        cwd, _ = env
        (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
        sandbox = PathSandbox(cwd=cwd, add_dirs=None)
        with pytest.raises(PermissionError):
            sandbox.resolve("agent/../../../secret.txt")


class TestReadFile:
    def test_returns_file_content(self, env):
        tools = make_tools(env)
        assert '"reward": 1' in tools.read_file("result.json")

    def test_absolute_path_in_add_dir(self, env):
        cwd, extra = env
        tools = make_tools(env, add_dirs=[extra])
        assert tools.read_file(str(extra / "instruction.md")) == "Do the thing."

    def test_outside_path_returns_error_string_not_raise(self, env, tmp_path):
        (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
        tools = make_tools(env)
        result = tools.read_file("../secret.txt")
        assert result.startswith("Error")

    def test_missing_file_returns_error_string(self, env):
        tools = make_tools(env)
        assert tools.read_file("nope.json").startswith("Error")


class TestGlob:
    def test_finds_files_by_pattern(self, env):
        tools = make_tools(env)
        out = tools.glob("**/*.json")
        assert "result.json" in out
        assert "agent/trajectory.json" in out

    def test_no_match_reports_it(self, env):
        tools = make_tools(env)
        assert "No files" in tools.glob("**/*.toml")

    def test_entry_cap_is_annotated_not_silent(self, env):
        """M3: glob 超上限必须显式标注（与 grep/file_tree 截断哲学一致）。"""
        tools = make_tools(env)
        cwd, _ = env
        for i in range(250):
            (cwd / f"f{i}.txt").write_text("x", encoding="utf-8")

        out = tools.glob("**/*.txt")
        lines = out.splitlines()
        assert len(lines) == 201  # 200 entries + 1 annotation
        assert lines[-1] == "... (50 more entries omitted)"


class TestReadFilePagination:
    """M4: offset/limit 是模型分页读大文件的唯一通道。"""

    def test_offset_skips_lines(self, env):
        tools = make_tools(env)
        cwd, _ = env
        f = cwd / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(10)),
                     encoding="utf-8")

        assert tools.read_file("lines.txt", offset=8) == "line8\nline9"

    def test_limit_caps_lines(self, env):
        tools = make_tools(env)
        cwd, _ = env
        f = cwd / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(10)),
                     encoding="utf-8")

        assert tools.read_file("lines.txt", limit=3) == "line0\nline1\nline2"

    def test_offset_and_limit_combine(self, env):
        tools = make_tools(env)
        cwd, _ = env
        f = cwd / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(10)),
                     encoding="utf-8")

        assert tools.read_file("lines.txt", offset=2, limit=3) == \
            "line2\nline3\nline4"


class TestGrep:
    def test_returns_matching_lines_with_location(self, env):
        tools = make_tools(env)
        out = tools.grep("reward")
        assert "result.json" in out
        assert "reward" in out

    def test_no_match_reports_it(self, env):
        tools = make_tools(env)
        assert "No matches" in tools.grep("nothing-matches-this")

    def test_match_cap_is_annotated_not_silent(self, env):
        """#E: 超出上限的匹配被截断时必须有显式标注（截断不静默）。"""
        tools = make_tools(env)
        cwd, _ = env
        big = cwd / "big.log"
        big.write_text(
            "\n".join(f"hit number {i}" for i in range(250)),
            encoding="utf-8",
        )

        out = tools.grep("hit number")
        lines = out.splitlines()
        assert len(lines) == 201  # 200 matches + 1 annotation
        assert lines[-1] == "... (50 more matches omitted)"
