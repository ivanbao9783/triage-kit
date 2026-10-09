"""Tests for GeneralHarness loop logging — observability at key points.

Uses pytest's caplog against the harness logger; no network access.
"""

import logging

from tests.test_general_harness import (
    SUBMIT_RESULT,
    FakeClient,
    response,
    tool_call,
)


class TestHarnessLogging:
    def test_tool_loop_logs_key_events(self, tmp_path, caplog):
        from triage_kit.backends.general.harness import GeneralHarness

        (tmp_path / "result.json").write_text('{"reward": 1}', encoding="utf-8")
        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
            response(tool_calls=[tool_call("c2", "submit_analysis",
                                           SUBMIT_RESULT)]),
        ])

        with caplog.at_level(
            logging.DEBUG, logger="triage_kit.backends.general.harness"
        ):
            GeneralHarness(client, default_model="m1").query_agent(
                "analyze", cwd=tmp_path, model="m1"
            )

        msgs = [r.getMessage() for r in caplog.records]

        # loop start: model + cwd + turn budget
        assert any("query_agent start" in m and "model=m1" in m for m in msgs)
        # each turn boundary
        assert any("turn 1" in m for m in msgs)
        assert any("turn 2" in m for m in msgs)
        # tool call + result size
        assert any("tool read_file" in m for m in msgs)
        assert any("read_file ->" in m for m in msgs)
        # submission
        assert any("submit_analysis" in m and "turns=2" in m for m in msgs)

    def test_forced_submission_is_logged(self, tmp_path, caplog):
        from triage_kit.backends.general.harness import GeneralHarness

        (tmp_path / "result.json").write_text('{"reward": 1}', encoding="utf-8")
        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
            response(tool_calls=[tool_call("c2", "submit_analysis",
                                           SUBMIT_RESULT)]),
        ])

        with caplog.at_level(
            logging.DEBUG, logger="triage_kit.backends.general.harness"
        ):
            GeneralHarness(client, default_model="m1").query_agent(
                "analyze", cwd=tmp_path, model="m1", max_turns=2
            )

        msgs = [r.getMessage() for r in caplog.records]
        assert any("forcing submit_analysis" in m for m in msgs)

    def test_no_submit_by_deadline_is_logged_as_error(self, tmp_path, caplog):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([
            response(tool_calls=[tool_call("c1", "read_file",
                                           {"path": "result.json"})]),
        ])

        with caplog.at_level(
            logging.DEBUG, logger="triage_kit.backends.general.harness"
        ):
            try:
                GeneralHarness(client, default_model="m1").query_agent(
                    "analyze", cwd=tmp_path, model="m1", max_turns=1
                )
            except ValueError:
                pass

        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_plain_query_is_logged(self, caplog):
        from triage_kit.backends.general.harness import GeneralHarness

        client = FakeClient([response(content="JOB SUMMARY")])
        with caplog.at_level(
            logging.DEBUG, logger="triage_kit.backends.general.harness"
        ):
            GeneralHarness(client, default_model="m1").query("agg", model="m1")

        msgs = [r.getMessage() for r in caplog.records]
        assert any("query" in m and "model=m1" in m for m in msgs)
