# TODO

Work remaining against [PLAN.md](PLAN.md). Check items off as they land.
Legend: `[x]` done · `[ ]` to do · ★ = stop for review.

## API notes (from the OpenAI docs, 2026-10-24)

**Decisions API**: `client.decisions.create(model="gpt-6-luna", input=..., questions=[...])`
- `input`: a string or a list of messages. User content parts can be `input_text`, `input_image` (data URL or https) or `input_json`.
- `questions`: 1–400 per request, each with a unique `name`.
  - `predicate` returns `probability`.
  - `choice` returns `choice`, `probabilities` and `confidence`. Always include an `"other"` choice.
  - `score` takes 2–10 ordered `levels` and returns `score`, a float over the level indices from 0.
- `answers[]` matches questions by `name`. Any answer can have `type == "refusal"`.
- No rate limits are documented. We retry on 429/5xx.

**Agents API**: `client.beta.agents.sessions.create(agent=..., environment=..., input=..., stream=True)`
- Custom tools are `{"type": "function", "name", "description", "parameters"}` in `agent.tools`.
- When the agent wants a tool, the stream emits `agent.session.requires_action`, and `session.required_actions[]` holds
  `{type: "function_call", turn_id, call_id, name, arguments}`.
- Reply with `client.beta.agents.sessions.events.create(session_id, events=[{"type": "agent.session.input.tool_result",
  turn_id, call_id, success, output | error}])`. `output` is a string, so JSON objects go through `json.dumps`.
- The turn ends with `agent.session.turn.completed`, `.failed` or `.cancelled`. Read the final result from `output_text`.
  An idle session does not mean success.
- Recovery: `sessions.retrieve(id)` and `sessions.items.list(id)`. Streams don't replay missed events.
- Settled by the first live calls (2026-10-24):
  - `environment: {"type": "none"}` works with function tools.
  - Structured output exists: `agent.text.format = {"type": "json_schema", "schema": ...}`.
- The SDK runs the tool loop for us: `sessions.create(..., stream=True, tool_handlers={name: fn(args) -> dict})`.
- The SDK already retries 408/409/429/5xx with backoff and jitter and honors `Retry-After`, so we just set `max_retries=4`.

## M2: Data + ported core
- [x] SQLModel models (`WardrobeItem`, `AgentRunRecord`), SQLite `create_all`
- [x] Seed closet (28 items, no waterproof outerwear) and mock calendar
- [x] Ported `outfit_generator.py` and its tests
- [x] `/api/closet` CRUD, `/api/calendar`, `/api/dev/reset`
- [x] Closet page UI: item cards, category/formality chips, detail drawer, delete

## M3 ★: APIs
- [x] Add the `openai` SDK dependency
- [x] `integrations/openai_client.py`: shared client; the SDK handles retries and backoff (`API_MAX_RETRIES`, `API_TIMEOUT_S` in config)
- [x] `integrations/recorder.py`: `logs/api_calls.jsonl` call log (redacted) plus `recordings/<api>/<fingerprint>.json` for replay
- [x] `integrations/decisions_client.py` (typed Pydantic in/out, live → replay → mock)
  - [x] `score_outfits(OutfitScoringRequest)`: a score question per candidate × criterion; mock uses the generator's rules
  - [x] `classify_item(ItemSignals)`: choice and predicate questions, with the image
  - [x] `rate_gaps(gaps, context)`
- [x] `integrations/agents_client.py`
  - [x] `run_agent(goal, tools, context, instructions, output_schema, on_event, mock_planner)`
  - [x] Structured trace (tool calls, args, results, ms, source) streamed through `on_event`
  - [x] live → replay → mock fallback (the mock planner is supplied by the caller in M4)
- [x] `GET /api/health/apis`: one tiny real call per API with no fallback. The agents check round-trips a function tool.
- [x] `check_key.py` makes a real call to both APIs
- [x] Tests for the Agents adapter: fallback order, replay round-trip, tracing (`tests/test_agents_client.py`)
- [ ] Tests for the Decisions adapter
- [x] ★ Real calls to each API logged (decisions ~0.5–1.5s, agents ~14s with one tool call)

## M4: Agent + tools
- [ ] `tools/weather.py`: `get_weather_forecast` (Open-Meteo, 30 min cache, seasonal fallback)
- [ ] `tools/calendar.py`: `read_calendar`
- [ ] `tools/closet.py`: `query_closet` (compact payload)
- [ ] `tools/outfits.py`: `build_and_score_outfits` (generator → Decisions; index-only references)
- [ ] `tools/gaps.py`: `find_closet_gaps` (rules plus Decisions severity)
- [ ] `tools/secondhand.py`: `suggest_secondhand_item` (Depop / ThredUp / Poshmark search URLs)
- [ ] Tool registry (function + JSON schema each)
- [ ] `POST /api/stylist/plan`, `GET /api/stylist/runs/{id}`, persisted `AgentRunRecord`
- [ ] Plan validation: drop unknown item IDs and note them in the trace
- [ ] User text passed as quoted data, never as instructions

## M5 ★: Stylist UI + Agent Trace
- [ ] Wire the prompt box to `/api/stylist/plan`
- [ ] Day-by-day plan view with outfit cards
- [ ] Score breakdown per outfit (vibe, dress code, weather, color, freshness)
- [ ] Closet gap card with secondhand links
- [ ] Live Agent Trace (streamed or polled), with a source label per step
- [ ] API health / mode badge

## M6: Agentic Scan
- [ ] Port `GoogleVisionService` → `core/vision.py` (API key auth, local uploads)
- [ ] `POST /api/closet/scan`: upload → Vision → Decisions classify → auto-save
- [ ] Undo (`DELETE` of the new item)
- [ ] Scan page UI
- [ ] HEIC via `pillow-heif` (optional)

## M7: Demo hardening
- [ ] Warm-up script: 3 demo prompts and 2 scans live, so replay recordings exist
- [ ] Loud UI badge when replay or mock is in use
- [ ] README: Windows setup and demo script
- [ ] Polish at 1440px
