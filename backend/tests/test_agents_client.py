"""Offline tests for the Agents adapter: fallback order, replay, mock, tracing."""

import pytest

from app.config import get_settings
from app.integrations import agents_client, recorder
from app.integrations.agents_client import AgentTool, AgentsUnavailable, run_agent


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "api_calls.jsonl")
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path / "recordings")
    settings = get_settings()
    monkeypatch.setattr(settings, "agents_mode", "live")
    return settings


def _boom(*_args, **_kwargs):
    raise ConnectionError("network down")


def _weather_tool(calls):
    def handler(args):
        calls.append(args)
        return {"city": args["city"], "high_c": 12}

    return AgentTool("get_weather", "weather", {"type": "object"}, handler)


def _planner(goal, context, call_tool):
    return {"weather": call_tool("get_weather", {"city": "Seattle"})}


def test_live_failure_without_recording_uses_mock_planner(monkeypatch):
    monkeypatch.setattr(agents_client, "_run_live", _boom)
    calls: list = []
    events: list = []
    run = run_agent("trip", [_weather_tool(calls)], {}, instructions="i", mock_planner=_planner, on_event=events.append)

    assert run.meta.source == "mock"
    assert "network down" in run.meta.note
    assert run.output == {"weather": {"city": "Seattle", "high_c": 12}}
    assert calls == [{"city": "Seattle"}]
    assert [s["type"] for s in run.trace] == ["fallback", "tool_call"]
    assert run.trace[1]["source"] == "mock" and run.trace[1]["ok"] is True
    assert run.meta.tool_calls == 1
    assert events == run.trace


def test_live_run_is_recorded_then_replayed(monkeypatch, isolated):
    calls: list = []
    tool = _weather_tool(calls)

    def fake_live(request, tools, tracer):
        tracer.wrap(tools[0])({"city": "Seattle"})
        return '{"ok": true}', "sess_1"

    monkeypatch.setattr(agents_client, "_run_live", fake_live)
    live = run_agent("trip", [tool], {"d": 1}, instructions="i", output_schema={"type": "object"})
    assert live.meta.source == "live" and live.output == {"ok": True} and live.meta.session_id == "sess_1"

    isolated.agents_mode = "replay"
    replay = run_agent("trip", [tool], {"d": 1}, instructions="i", output_schema={"type": "object"})
    assert replay.meta.source == "replay" and replay.output == {"ok": True}
    assert replay.meta.session_id == "sess_1" and "Replayed a real Agents run" in replay.meta.note
    assert replay.trace[0]["source"] == "replay" and replay.trace[0]["tool"] == "get_weather"
    assert len(calls) == 1  # replay never re-runs tools


def test_replay_mode_ignores_recordings_for_other_requests(monkeypatch, isolated):
    monkeypatch.setattr(agents_client, "_run_live", lambda request, tools, tracer: ("hi", "sess_1"))
    run_agent("trip A", [], {}, instructions="i")
    isolated.agents_mode = "replay"
    run = run_agent("trip B", [], {}, instructions="i", mock_planner=lambda g, c, t: "mocked")
    assert run.meta.source == "mock" and run.output == "mocked"
    assert "No recording" in run.meta.note


def test_mock_mode_never_goes_live(monkeypatch, isolated):
    isolated.agents_mode = "mock"
    monkeypatch.setattr(agents_client, "_run_live", pytest.fail)
    assert run_agent("trip", [], {}, instructions="i", mock_planner=lambda g, c, t: "ok").meta.source == "mock"


def test_tool_error_is_reported_to_the_agent_not_raised():
    def bad(_args):
        raise KeyError("city")

    tracer = agents_client._Tracer(None)
    result = tracer.wrap(AgentTool("t", "d", {}, bad))({})
    assert "KeyError" in result["error"]
    assert tracer.steps[0]["ok"] is False


def test_non_dict_tool_results_are_wrapped():
    tracer = agents_client._Tracer(None)
    assert tracer.wrap(AgentTool("t", "d", {}, lambda _a: [1, 2]))({}) == {"result": [1, 2]}


def test_no_planner_and_no_live_raises(monkeypatch):
    monkeypatch.setattr(agents_client, "_run_live", _boom)
    with pytest.raises(AgentsUnavailable):
        run_agent("trip", [], {}, instructions="i")
