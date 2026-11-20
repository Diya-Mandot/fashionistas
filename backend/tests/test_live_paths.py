"""Exercise the LIVE code paths against fake Anthropic SDK clients that return the
shapes Claude's Messages API documents (tool_use -> tool_result, structured output)."""

import json
from datetime import date
from types import SimpleNamespace

from app.config import get_settings
from app.integrations import agents_client, decisions_client, recorder


def _usage():
    return SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.message


class FakeClaude:
    """Scripted Claude: each call to messages.stream/create returns the next response."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        outer = self

        class Messages:
            def stream(self, **kw):
                outer.requests.append({**kw, "messages": list(kw.get("messages", []))})
                return FakeStream(outer.responses.pop(0))

            def create(self, **kw):
                outer.requests.append(kw)
                return outer.responses.pop(0)

        self.beta = SimpleNamespace(messages=Messages())
        self.messages = Messages()


def test_live_agent_loop_runs_tools_and_returns_results(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")
    fake = FakeClaude([
        SimpleNamespace(stop_reason="tool_use", usage=_usage(), content=[
            _text("Checking your calendar."),
            _tool_use("toolu_1", "read_calendar", {"start_date": "2026-10-27", "end_date": "2026-10-29"}),
            _tool_use("toolu_2", "nope", {}),
        ]),
        SimpleNamespace(stop_reason="end_turn", usage=_usage(), content=[_text("Planned 3 days.")]),
    ])
    monkeypatch.setattr(agents_client, "get_client", lambda: fake)
    monkeypatch.setattr(get_settings(), "agents_mode", "live")
    executed, steps = [], []

    def execute(name, args):
        executed.append((name, args))
        return ({"events": [], "count": 0}, True) if name == "read_calendar" else ({"error": "Unknown tool"}, False)

    tools = [{"type": "function", "name": "read_calendar", "description": "cal",
              "parameters": {"type": "object", "properties": {}}}]
    run = agents_client.run_agent(
        "goal", tools,
        {"message": "Seattle trip", "today": date(2026, 10, 24), "home_city": "SF"},
        execute=execute, emit=steps.append,
    )
    assert run.source == "live" and run.final_text == "Planned 3 days."
    first = fake.requests[0]
    assert first["system"] == "goal" and first["model"] == get_settings().agents_model
    assert first["tools"][0]["name"] == "read_calendar" and "input_schema" in first["tools"][0]
    assert first["fallbacks"] == "default"
    assert executed[0] == ("read_calendar", {"start_date": "2026-10-27", "end_date": "2026-10-29"})
    # Second request carries the assistant turn plus ONE user message with both tool results.
    results = fake.requests[1]["messages"][-1]["content"]
    assert results[0] == {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"events": [], "count": 0}'}
    assert results[1]["is_error"] is True and "Unknown tool" in results[1]["content"]
    # A recording was saved so this exact request can be replayed honestly.
    assert recorder.recording_count("agents") == 1


def test_live_agent_refusal_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(recorder, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(recorder, "LOG_PATH", tmp_path / "log.jsonl")
    fake = FakeClaude([SimpleNamespace(stop_reason="refusal", usage=_usage(), content=[])])
    monkeypatch.setattr(agents_client, "get_client", lambda: fake)
    monkeypatch.setattr(get_settings(), "agents_mode", "live")
    monkeypatch.setattr(agents_client, "_run_mock", lambda ctx, ex, em: agents_client.AgentRun(source="mock"))
    steps = []
    run = agents_client.run_agent("g", [], {"message": "m", "today": date(2026, 10, 24), "home_city": "SF"},
                                  execute=lambda n, a: ({}, True), emit=steps.append)
    assert run.source == "mock"
    assert any("refusal" in (s.detail or "") for s in steps)


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
    assert calls[0]["model"] == get_settings().decisions_model and len(calls[0]["questions"]) == 10

    # Network dies: the exact same request replays the recorded live answer.
    def down(body):
        raise ConnectionError("offline")

    monkeypatch.setattr(decisions_client, "_create", down)
    again = decisions_client.score_outfits(req)
    assert again.meta.source == "replay"
    assert again.scores[0].scores.overall == res.scores[0].scores.overall
    assert "Replayed a real Claude response" in again.meta.note


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


def test_create_translates_questions_to_structured_output(monkeypatch):
    answer = {"c0_vibe": {"level": 3, "confidence": 0.9}, "category": {"choice": "outerwear", "confidence": 0.8},
              "waterproof": {"answer": False, "confidence": 0.7}}
    fake = FakeClaude([SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", usage=_usage(),
                                       content=[_text(json.dumps(answer))])])
    monkeypatch.setattr(decisions_client, "get_client", lambda: fake)
    body = {
        "model": "claude-opus-5-5",
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": "Be careful."}]},
            {"role": "user", "content": [{"type": "input_json", "data": {"a": 1}},
                                         {"type": "input_image", "image_url": "data:image/jpeg;base64,AAAA"}]},
        ],
        "questions": [
            {"type": "score", "name": "c0_vibe", "instructions": "Vibe?", "levels": [{"label": str(n), "description": "d"} for n in range(5)]},
            {"type": "choice", "name": "category", "instructions": "Cat?", "choices": [{"value": "tops", "description": "t"}, {"value": "outerwear", "description": "o"}]},
            {"type": "predicate", "name": "waterproof", "instructions": "Waterproof?"},
        ],
    }
    out = decisions_client._create(body)
    req = fake.requests[0]
    assert req["system"] == "Be careful."
    content = req["messages"][0]["content"]
    assert content[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}
    schema = req["output_config"]["format"]["schema"]
    assert schema["properties"]["c0_vibe"]["properties"]["level"]["enum"] == [0, 1, 2, 3, 4]
    assert schema["properties"]["category"]["properties"]["choice"]["enum"] == ["tops", "outerwear"]
    by = {a["name"]: a for a in out["answers"]}
    assert by["c0_vibe"] == {"type": "score", "name": "c0_vibe", "score": 3.0, "confidence": 0.9}
    assert by["category"]["choice"] == "outerwear"
    assert by["waterproof"]["probability"] == 0.3
