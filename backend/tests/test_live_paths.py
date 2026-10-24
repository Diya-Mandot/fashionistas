"""Exercise the LIVE code paths against fake SDK clients that return the shapes
documented for the Agents API (requires_action -> tool_result) and Decisions API."""

from datetime import date
from types import SimpleNamespace

from app.config import get_settings
from app.integrations import agents_client, decisions_client, recorder


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self.events)


class FakeAgentsClient:
    def __init__(self):
        self.submitted = []
        self.created = None
        events = [
            {"type": "agent.session.created", "session": {"id": "sess_1"}},
            {
                "type": "agent.session.requires_action",
                "session": {
                    "id": "sess_1",
                    "required_actions": [
                        {"type": "function_call", "turn_id": "turn_1", "call_id": "call_1", "name": "read_calendar",
                         "arguments": {"start_date": "2026-10-27", "end_date": "2026-10-29"}},
                        {"type": "function_call", "turn_id": "turn_1", "call_id": "call_2", "name": "nope", "arguments": "{}"},
                    ],
                },
            },
            {"type": "agent.session.turn.output_text.done", "turn": {"subagent_id": None}, "text": "Planned 3 days."},
            {"type": "agent.session.turn.completed", "turn": {"subagent_id": None}},
        ]
        outer = self

        class Events:
            def create(self, session_id, events):
                outer.submitted.append((session_id, events))

        class Sessions:
            events = Events()

            def create(self, **kw):
                outer.created = kw
                return FakeStream(events)

        self.beta = SimpleNamespace(agents=SimpleNamespace(sessions=Sessions()))


def test_live_agent_loop_runs_tools_and_returns_results(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")
    fake = FakeAgentsClient()
    monkeypatch.setattr(agents_client, "get_client", lambda: fake)
    monkeypatch.setattr(get_settings(), "agents_mode", "live")
    executed, steps = [], []

    def execute(name, args):
        executed.append((name, args))
        return ({"events": [], "count": 0}, True) if name == "read_calendar" else ({"error": "Unknown tool"}, False)

    run = agents_client.run_agent(
        "goal", [{"type": "function", "name": "read_calendar"}],
        {"message": "Seattle trip", "today": date(2026, 10, 24), "home_city": "SF"},
        execute=execute, emit=steps.append,
    )
    assert run.source == "live" and run.final_text == "Planned 3 days."
    assert fake.created["environment"] == {"type": "none"}
    assert fake.created["stream"] is True
    assert executed[0] == ("read_calendar", {"start_date": "2026-10-27", "end_date": "2026-10-29"})
    session_id, results = fake.submitted[0]
    assert session_id == "sess_1"
    assert results[0] == {"type": "agent.session.input.tool_result", "turn_id": "turn_1", "call_id": "call_1",
                          "success": True, "output": '{"events": [], "count": 0}'}
    assert results[1]["success"] is False and "Unknown tool" in results[1]["error"]
    # A recording was saved so this exact request can be replayed honestly.
    assert recorder.recording_count("agents") == 1


def test_live_agent_failure_falls_back_to_mock(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")

    def boom():
        raise ConnectionError("wifi down")

    monkeypatch.setattr(agents_client, "get_client", boom)
    monkeypatch.setattr(get_settings(), "agents_mode", "live")
    monkeypatch.setattr(agents_client, "_run_mock", lambda ctx, ex, em: agents_client.AgentRun(source="mock"))
    steps = []
    run = agents_client.run_agent("g", [], {"message": "m", "today": date(2026, 10, 24), "home_city": "SF"},
                                  execute=lambda n, a: ({}, True), emit=steps.append)
    assert run.source == "mock"
    assert any("wifi down" in (s.detail or "") for s in steps)


def test_live_decisions_parse_and_record_then_replay(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(get_settings(), "decisions_mode", "live")
    calls = []

    def fake_create(body):
        calls.append(body)
        answers = [{"type": "score", "name": q["name"], "score": 3.0 if q["name"].startswith("c0") else 1.0,
                    "confidence": 0.8, "probabilities": []} for q in body["questions"]]
        return {"answers": answers}

    monkeypatch.setattr(decisions_client, "_create", fake_create)
    req = decisions_client.OutfitScoringRequest(
        vibe="edgy", event=decisions_client.EventIn(name="Dinner"), weather=decisions_client.WeatherIn(temp_f=50),
        candidates=[[decisions_client.CandidateItem(name="a", category="tops")], [decisions_client.CandidateItem(name="b", category="tops")]],
    )
    res = decisions_client.score_outfits(req)
    assert res.meta.source == "live"
    assert res.scores[0].scores.vibe == 0.75 and res.scores[1].scores.vibe == 0.25
    assert calls[0]["model"] == "gpt-6-luna" and len(calls[0]["questions"]) == 10

    # Network dies: the exact same request replays the recorded live answer.
    def down(body):
        raise ConnectionError("offline")

    monkeypatch.setattr(decisions_client, "_create", down)
    again = decisions_client.score_outfits(req)
    assert again.meta.source == "replay"
    assert again.scores[0].scores.overall == res.scores[0].scores.overall
    assert "Replayed a real Decisions response" in again.meta.note


def test_live_classify_parses_choice_and_predicate(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(get_settings(), "decisions_mode", "live")
    picks = {"category": "outerwear", "subcategory": "raincoat", "formality": "casual", "season": "spring, fall",
             "material": "nylon", "color": "navy", "style": "sporty"}

    def fake_create(body):
        assert any(p.get("type") == "input_image" for p in body["input"][0]["content"])
        answers = [{"type": "choice", "name": k, "choice": v, "confidence": 0.9, "probabilities": []} for k, v in picks.items()]
        answers.append({"type": "predicate", "name": "waterproof", "probability": 0.93})
        return {"answers": answers}

    monkeypatch.setattr(decisions_client, "_create", fake_create)
    c = decisions_client.classify_item(decisions_client.ItemSignals(best_guess="rain jacket", image_data_url="data:image/jpeg;base64,AAAA"))
    assert c.meta.source == "live"
    assert (c.category, c.subcategory, c.waterproof) == ("outerwear", "raincoat", True)
    assert c.name == "Rain Jacket" and c.confidence["waterproof"] == 0.93
