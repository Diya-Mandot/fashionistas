import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.integrations.agents_client import AgentTool, AgentsClient
from app.integrations.common import AdapterError
from app.integrations.decisions_adapter import CRITERIA, TAXONOMIES, DecisionsClient, OutfitCandidate


def settings(tmp_path, **overrides):
    return Settings(_env_file=None, openai_api_key="test-secret-never-record", api_max_retries=0,
                    api_recordings_path=tmp_path / "calls.jsonl", **overrides)


def client(handler):
    return AsyncOpenAI(api_key="test-secret-never-record", max_retries=0,
                       http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


def decision(answers):
    return {"model": "gpt-6-luna", "answers": answers,
            "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1,
                      "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}}}


def test_classification_live_replay_and_private_request(tmp_path):
    async def run():
        calls = []

        def handler(request):
            body = json.loads(request.content)
            assert request.url.path == "/v1/decisions"
            assert len(body["questions"]) == len(TAXONOMIES)
            calls.append(body)
            return httpx2.Response(200, json=decision([
                {"type": "choice", "name": name, "choice": "cotton" if name == "material" else values[0],
                 "confidence": 0.2 if name == "material" else 0.95, "probabilities": []}
                for name, values in TAXONOMIES.items()
            ]))

        config = settings(tmp_path)
        async with client(handler) as api:
            result = await DecisionsClient(config, api).classify_item(
                "Private description", image_url="data:image/png;base64,private-image")
        assert result.source == "live"
        assert result.data.tags["material"].value == "unknown"
        assert result.data.needs_review
        recorded = config.api_recordings_path.read_text()
        assert "Private description" not in recorded
        assert "private-image" not in recorded
        assert config.openai_api_key not in recorded
        config.decisions_mode = "replay"
        replay = await DecisionsClient(config).classify_item(
            "Private description", image_url="data:image/png;base64,private-image")
        assert replay.data == result.data
        assert replay.recorded_at == result.recorded_at
        assert replay.source == "replay"
        assert len(calls) == 1
        with pytest.raises(AdapterError, match="No matching"):
            await DecisionsClient(config).classify_item("Different item")

    asyncio.run(run())


@pytest.mark.parametrize("bad_answer", ["refusal", "unknown_tag", "missing", "invalid_confidence"])
def test_invalid_classification_fails_without_recording(tmp_path, bad_answer):
    async def run():
        answers = [{"type": "choice", "name": n, "choice": v[0], "confidence": 0.9, "probabilities": []}
                   for n, v in TAXONOMIES.items()]
        if bad_answer == "refusal":
            answers[0] = {"type": "refusal", "name": "category"}
        elif bad_answer == "unknown_tag":
            answers[0]["choice"] = "invented"
        elif bad_answer == "missing":
            answers.pop()
        else:
            answers[0]["confidence"] = 2
        async with client(lambda request: httpx2.Response(200, json=decision(answers))) as api:
            with pytest.raises(AdapterError):
                await DecisionsClient(settings(tmp_path), api).classify_item("A shirt")
        assert not (tmp_path / "calls.jsonl").exists()
    asyncio.run(run())


def test_outfit_scoring_maps_original_ids(tmp_path):
    async def run():
        candidate = OutfitCandidate(item_ids=["itm_seed01", "itm_seed08"], items=[{"category": "tops"}, {"category": "bottoms"}])

        def handler(request):
            body = json.loads(request.content)
            assert len(body["questions"]) == 5
            assert all(len(q["levels"]) == 5 for q in body["questions"])
            return httpx2.Response(200, json=decision([
                {"type": "score", "name": q["name"], "score": 3.5, "confidence": 0.8, "probabilities": []}
                for q in body["questions"]
            ]))

        async with client(handler) as api:
            result = await DecisionsClient(settings(tmp_path), api).score_outfits([candidate], {"vibe": "conference"})
        assert result.data.outfits[0].item_ids == candidate.item_ids
        assert set(result.data.outfits[0].criteria) == set(CRITERIA)
        assert result.data.outfits[0].criteria["weather"].score == 3.5
        with pytest.raises(ValueError):
            await DecisionsClient(settings(tmp_path)).score_outfits([], {})
    asyncio.run(run())


class ClosetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str


def response(output):
    return {"id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-6-astra", "output": output,
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}


def final_message():
    return {"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps({"answer": "Use the blue shirt.", "questions": []}), "annotations": []}]}


def test_real_sdk_tool_loop_and_replay_without_tool_execution(tmp_path):
    async def run():
        invocations = []
        requests = []

        async def closet(args):
            invocations.append(args.category)
            return {"items": [{"id": "itm_seed01", "color": "blue"}]}

        tool = AgentTool("query_closet", "Read closet garments by category.", ClosetArgs, closet)

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            assert body["store"] is False
            if len(requests) == 1:
                return httpx2.Response(200, json=response([{
                    "type": "function_call", "id": "fc_test", "call_id": "call_test",
                    "name": "query_closet", "arguments": '{"category":"tops"}', "status": "completed"}]))
            assert any(item.get("type") == "function_call_output" and "itm_seed01" in item["output"] for item in body["input"])
            return httpx2.Response(200, json=response([final_message()]))

        config = settings(tmp_path)
        async with client(handler) as api:
            result = await AgentsClient(config, api).run_agent("Conference outfit", [tool], {"city": "Seattle"})
        assert result.source == "live"
        assert result.data.output["answer"] == "Use the blue shirt."
        assert result.data.trace[0].status == "completed"
        assert invocations == ["tops"]
        config.agents_mode = "replay"
        replay = await AgentsClient(config).run_agent("Conference outfit", [tool], {"city": "Seattle"})
        assert replay.data == result.data
        assert replay.source == "replay"
        assert invocations == ["tops"]
        assert len(requests) == 2
        changed_tool = AgentTool("query_closet", tool.description, ClosetArgs, closet, version="2")
        with pytest.raises(AdapterError, match="No matching"):
            await AgentsClient(config).run_agent("Conference outfit", [changed_tool], {"city": "Seattle"})
    asyncio.run(run())


def test_api_failure_does_not_silently_mock(tmp_path):
    async def run():
        async with client(lambda request: httpx2.Response(403, json={"error": {"message": "secret", "type": "permission_error"}})) as api:
            with pytest.raises(AdapterError, match="Decisions API call failed") as failure:
                await DecisionsClient(settings(tmp_path), api).classify_item("shirt")
            assert "secret" not in str(failure.value)
        assert not (tmp_path / "calls.jsonl").exists()
    asyncio.run(run())


def test_mock_modes_are_explicit_and_missing_key_fails_live(tmp_path):
    async def run():
        config = settings(tmp_path, agents_mode="mock", decisions_mode="mock")
        agent = await AgentsClient(config).run_agent("outfit", [], {})
        tags = await DecisionsClient(config).classify_item("shirt")
        assert agent.source == tags.source == "mock"
        assert agent.warnings and tags.warnings
        assert not agent.data.trace
        config.agents_mode = "live"
        config.openai_api_key = ""
        with pytest.raises(AdapterError, match="OPENAI_API_KEY"):
            await AgentsClient(config).run_agent("outfit", [], {})
    asyncio.run(run())


def test_sdk_rejects_invalid_tool_arguments_before_execution(tmp_path):
    async def run():
        invoked = []

        async def handler(args):
            invoked.append(args)

        def respond(request):
            return httpx2.Response(200, json=response([{
                "type": "function_call", "id": "fc_bad", "call_id": "call_bad", "name": "query_closet",
                "arguments": '{"category":"tops","unexpected":true}', "status": "completed"}]))

        async with client(respond) as api:
            with pytest.raises(AdapterError):
                await AgentsClient(settings(tmp_path), api).run_agent("outfit", [AgentTool("query_closet", "Read closet", ClosetArgs, handler)], {})
        assert invoked == []
        assert not (tmp_path / "calls.jsonl").exists()
    asyncio.run(run())


def test_sdk_turn_limit_stops_a_loop(tmp_path):
    async def run():
        async def handler(args):
            return []

        def respond(request):
            return httpx2.Response(200, json=response([{
                "type": "function_call", "id": "fc_loop", "call_id": "call_loop", "name": "query_closet",
                "arguments": '{"category":"tops"}', "status": "completed"}]))

        async with client(respond) as api:
            with pytest.raises(AdapterError):
                await AgentsClient(settings(tmp_path, agent_max_turns=1), api).run_agent(
                    "outfit", [AgentTool("query_closet", "Read closet", ClosetArgs, handler)], {})
        assert not (tmp_path / "calls.jsonl").exists()
    asyncio.run(run())


def test_agent_total_timeout(tmp_path):
    async def run():
        async def respond(request):
            await asyncio.sleep(1)
            return httpx2.Response(200, json=response([final_message()]))

        async with client(respond) as api:
            with pytest.raises(AdapterError, match="timed out"):
                await AgentsClient(settings(tmp_path, agent_timeout_seconds=0.01), api).run_agent("outfit", [], {})
    asyncio.run(run())


def test_rate_limit_retries_without_replaying_tools(tmp_path):
    async def run():
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx2.Response(429, headers={"retry-after": "0.001"},
                                      json={"error": {"message": "rate limited", "type": "rate_limit_error"}})
            return httpx2.Response(200, json=decision([{"type": "predicate", "name": "garment", "probability": 0.99}]))

        async with AsyncOpenAI(api_key="test", max_retries=1,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond))) as api:
            result = await DecisionsClient(settings(tmp_path), api).check_connection()
        assert result.data.passed
        assert result.source == "live"
        assert len(requests) == 2
    asyncio.run(run())


def test_failed_recording_does_not_discard_live_result(tmp_path):
    async def run():
        blocked_parent = tmp_path / "not-a-directory"
        blocked_parent.write_text("file")
        config = settings(tmp_path)
        config.api_recordings_path = blocked_parent / "calls.jsonl"
        async with client(lambda request: httpx2.Response(200, json=decision([
            {"type": "predicate", "name": "garment", "probability": 1}])) ) as api:
            result = await DecisionsClient(config, api).check_connection()
        assert result.source == "live" and result.data.passed
        assert result.warnings
        assert result.recorded_at is None
    asyncio.run(run())
