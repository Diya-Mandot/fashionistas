# EcoStylist: Context-Aware Stylist (Hackathon Plan)

Track 1: **Agents in Action**. We use the **Agents SDK** and **Decisions API**.
The SDK is the current choice. A separate adapter permits a later hosted API migration.

Current sequence: adapters, weather, scanning, then outfit planning.
The adapters, weather, and backend scanning are implemented. Live OpenAI access and real-photo accuracy remain unverified.
WIP commit `9c6108b` already supplies closet CRUD, calendar data, and candidate generation.
Commit `886b1b4` supplies the Closet page and synchronous Decisions adapter. Reuse these components.

Judges must see three things: **API input → the agent's task or decision → the result in our app.**

## The pitch

> "Our capstone EcoStylist generated outfits from hardcoded rules. Rules can't parse
> 'professional but edgy' or account for a Seattle drizzle. Now an agent gathers context
> and the Decisions API makes the judgment calls."

- **Context-Aware Stylist**: the user types a messy trip or occasion request. The agent chooses its own tools: weather, calendar, closet. It builds candidate outfits per event and asks the Decisions API to score them. It flags closet gaps (for example, no rain jacket). It returns a day-by-day packing plan. Shopping is excluded.
- **Agentic Closet Scanner**: the user uploads a photo. OpenAI image understanding identifies garment regions. Decisions classifies each crop. Recognized items are saved with review flags and batch undo.

## Adapter reliability

The demo depends on real API calls. The reliability design:

1. **Live is the default.** Synthetic mock data is never served silently.
2. **Preflight check.** `GET /api/health/apis` reports configuration without paid calls. Explicit `POST /api/health/apis/check` tests each configured adapter. Only a successful live check confirms current access. Replay and mock checks retain their source labels. Startup never makes paid calls.
3. **Resilient client.** Every call has a timeout, retries with exponential backoff and jitter on 429/5xx/network errors, and honors any `Retry-After` header. If the docs list request limits, we enforce them in our client before the API does.
4. **Record and replay validated results.** Successful live results enter `backend/logs/api_calls.jsonl`. Requests become hashes, so raw prompts and images are excluded. Results can contain personal information and must stay local. Replay requires the same request fingerprint, output schema, and tool versions. Replay never executes tool handlers.
5. **Explicit modes.** `AGENTS_MODE` / `DECISIONS_MODE` = `live | replay | mock`, default `live`. Failures remain visible. Changing mode is explicit. Mock classifications return unknown tags. Mock scoring returns zero scores with zero confidence. Mock mode cannot fabricate structured plans. The future UI must show each result's source.
6. **Warm-up.** Before the demo, run the 3 example prompts and 2 scans live so replay recordings exist for every demo path.
7. **Persisted runs.** Each stylist run is stored, so `GET /api/stylist/runs/{id}` can re-show a real past run instantly.

Both APIs sit behind adapters, so their shapes never leak into the rest of the app:
- `backend/app/integrations/agents_client.py`: `run_agent(goal, tools, context) -> AgentRun`, which returns the answer and a structured trace.
- `backend/app/integrations/decisions_adapter.py`: async `DecisionsClient` classification and scoring.
- `backend/app/integrations/decisions_client.py`: existing synchronous adapter from main. Keep its callers compatible during integration.

Adapters follow the official Agents SDK and Decisions API documentation.
Weather and backend scanning are implemented. Planner validation and frontend integration remain separate steps.

## Architecture

```
backend/   Python 3.11 (via uv), FastAPI, SQLModel + SQLite (create_all, no migrations)
  app/core/outfit_generator.py   ported from ecostylistbe, used as the candidate builder (≤20 combos)
  app/core/vision.py             photo validation, orientation, metadata removal, garment crops
  app/integrations/vision_client.py  structured image understanding with live / replay / mock modes
  app/services/scanning.py       Decisions tags, atomic closet saves, idempotency, and undo
  app/integrations/              agents_client.py, decisions_client.py
  app/tools/                     5 planned agent tools (function + JSON schema each)
  app/routers/                   stylist, closet, calendar, health, dev
frontend/  React + Vite + TypeScript (strict) + Tailwind, web only
  src/theme/                     tokens ported from ecostylistfe/theme
  src/pages/                     Stylist, Closet, Scan
```

`make dev` starts the backend on :8000 and the frontend on :5173.

## Agent tools

| Tool | Source | Notes |
|---|---|---|
| `get_weather_forecast(city, start, end)` | Open-Meteo (free, no key) | Implemented: city selection, 30 min cache, local dates, and explicit missing days. Available as an SDK tool and `/api/weather`. |
| `read_calendar(start, end)` | Mock, from `seed.py` | Events are relative to today: a Seattle conference trip and an NYC weekend. |
| `query_closet(filters)` | SQLite | Compact payload. |
| `build_and_score_outfits(event, weather, vibe)` | Generator + **Decisions API** | Candidates are referenced by index only and mapped back to item IDs server-side. Scores per criterion: vibe, dress code, weather, color, freshness. |
| `find_closet_gaps(plan, weather)` | Rules + **Decisions API** severity | Falls back to a simple rule (stated in the trace) if Decisions can't express it. |

The live agent picks the tool order itself. Python does not prescribe that order.
Mock mode returns a labeled preview without running tools or inventing a plan.

**Safety (from the capstone `outfit_curator.py` pattern):** the model picks candidates by index and never invents IDs. User text is passed in as quoted data, never as instructions. Item IDs in the output are checked against the closet, and unknown ones are dropped and noted in the trace.

## Design system

Ported exactly from `ecostylistfe/theme`: Paper `#FAF9F6`, Deep Forest `#1A3226`, Warm Sand `#D4A373`, Eco Emerald `#34D399`, Ocean `#5B8DB8`, plus glass panels (`rgba(255,255,255,0.30)`, 20px blur, white 48% border). Fonts: Syne for display, Manrope for body, Playfair Display for the wordmark only.

## Milestones (★ = stop for review)

1. ★ **Scaffold**: FastAPI and Vite running, theme and fonts, styled Stylist hero with the glass prompt box.
2. **Data + ported core**: models, seed closet (~25 items, no waterproof outerwear) and calendar, generator tests, Closet page.
3. ★ **Adapters**: implemented live / replay / mock modes and explicit preflight health check. Real account access remains untested.
4. **Weather integration**: implemented city lookup, dated forecasts, caching, and explicit missing-data handling. Live Seattle check passed.
5. **Agentic Scan**: backend implemented: upload → image understanding → Decisions classification → save with undo. Live photo accuracy and frontend integration remain unverified.
6. ★ **Outfit planning + UI**: implement all 5 tools, `/api/stylist/plan`, and plan validation. Add plan views, scores, gaps, and traces.
7. **Demo hardening**: reset endpoint, fallbacks, mode badge, README demo script, polish at 1440px.

## Known risks

- System Python is 3.9, so we use `uv` to pin Python 3.11.
- Open-Meteo forecasts only about 16 days out, so demo trips are seeded 3–10 days from today.
- Seed photos are stored locally in `backend/seed_images/`, not hotlinked.
- HEIC support needs `pillow-heif`. If it won't install, HEIC is disabled and nothing else breaks.
- A live plan can take 20–40 seconds. The streamed trace covers the wait.

## Non-goals

No marketplace scraping, no SMS, no Calendar OAuth, no auth, no social/Rack/moderation, no Pinecone, Cloudinary or Groq, no Expo.
