# EcoStylist: Context-Aware Stylist (Hackathon Plan)

Track 1: **Agents in Action**. We use both the hackathon **Agents API** and **Decisions API**.

Judges must see three things: **API input → the agent's task or decision → the result in our app.**

## The pitch

> "Our capstone EcoStylist generated outfits from hardcoded rules. Rules can't parse
> 'professional but edgy' or account for a Seattle drizzle. Now an agent gathers context
> and the Decisions API makes the judgment calls."

- **Context-Aware Stylist**: the user types a messy trip or occasion request. The agent chooses its own tools: weather, calendar, closet. It builds candidate outfits per event and asks the Decisions API to score them. It flags closet gaps (for example, no rain jacket) and suggests secondhand items. It returns a day-by-day packing plan.
- **Agentic Closet Scanner**: the user uploads a photo. Google Vision extracts signals, the Decisions API classifies the item, and the item is auto-saved with an undo option.

## Hard requirement: the Decisions and Agents APIs must work, no matter what

The demo depends on real API calls. The reliability design:

1. **Live is the default.** Synthetic mock data is never served silently.
2. **Preflight check.** `GET /api/health/apis` runs on startup and from the UI. It checks keys, base URL, auth and one tiny real call to each API, and shows green or red per API. We run it before going on stage.
3. **Resilient client.** Every call has a timeout, retries with exponential backoff and jitter on 429/5xx/network errors, and honors any `Retry-After` header. If the docs list request limits, we enforce them in our client before the API does.
4. **Record and replay real responses.** Every successful live request and response is written to `backend/logs/api_calls.jsonl` with keys redacted. If the network dies mid-demo, the adapter can replay a **previously recorded real response** for the same request fingerprint. The trace labels it "replayed from live call at HH:MM", never as fake.
5. **Synthetic mock is the last resort.** It's only used when there is no recording. A loud badge in the UI says so. `AGENTS_MODE` / `DECISIONS_MODE` = `live | replay | mock`, default `live`. The auto-fallback order is live → replay → mock, and the trace shows the actual source for every step.
6. **Warm-up.** Before the demo, run the 3 example prompts and 2 scans live so replay recordings exist for every demo path.
7. **Persisted runs.** Each stylist run is stored, so `GET /api/stylist/runs/{id}` can re-show a real past run instantly.

Both APIs sit behind adapters, so their shapes never leak into the rest of the app:
- `backend/app/integrations/agents_client.py`: `run_agent(goal, tools, context) -> AgentRun`, which returns the answer and a structured trace.
- `backend/app/integrations/decisions_client.py`: `score_outfits(...)` and `classify_item(...)`.

**Blocked on:** the Agents API and Decisions API docs links from the hackathon page.

## Architecture

```
backend/   Python 3.11 (via uv), FastAPI, SQLModel + SQLite (create_all, no migrations)
  app/core/outfit_generator.py   ported from ecostylistbe, used as the candidate builder (≤20 combos)
  app/core/vision.py             ported GoogleVisionService (no Cloudinary, local uploads/)
  app/integrations/              agents_client.py, decisions_client.py
  app/tools/                     6 agent tools (function + JSON schema each)
  app/routers/                   stylist, closet, calendar, health, dev
frontend/  React + Vite + TypeScript (strict) + Tailwind, web only
  src/theme/                     tokens ported from ecostylistfe/theme
  src/pages/                     Stylist, Closet, Scan
```

`make dev` starts the backend on :8000 and the frontend on :5173.

## Agent tools

| Tool | Source | Notes |
|---|---|---|
| `get_weather_forecast(city, start, end)` | Open-Meteo (free, no key) | 30 min cache. Beyond the forecast window, returns the furthest available days plus a note. On timeout, uses the seasonal average and says so in the trace. |
| `read_calendar(start, end)` | Mock, from `seed.py` | Events are relative to today: a Seattle conference trip and an NYC weekend. |
| `query_closet(filters)` | SQLite | Compact payload. |
| `build_and_score_outfits(event, weather, vibe)` | Generator + **Decisions API** | Candidates are referenced by index only and mapped back to item IDs server-side. Scores per criterion: vibe, dress code, weather, color, freshness. |
| `find_closet_gaps(plan, weather)` | Rules + **Decisions API** severity | Falls back to a simple rule (stated in the trace) if Decisions can't express it. |
| `suggest_secondhand_item(desc, size)` | Search links only | Depop, ThredUp and Poshmark search URLs. No scraping. |

The agent picks the tool order itself; it is not hardcoded in Python. In mock mode, a deterministic keyword planner reads the message, so even the fallback isn't a fixed script.

**Safety (from the capstone `outfit_curator.py` pattern):** the model picks candidates by index and never invents IDs. User text is passed in as quoted data, never as instructions. Item IDs in the output are checked against the closet, and unknown ones are dropped and noted in the trace.

## Design system

Ported exactly from `ecostylistfe/theme`: Paper `#FAF9F6`, Deep Forest `#1A3226`, Warm Sand `#D4A373`, Eco Emerald `#34D399`, Ocean `#5B8DB8`, plus glass panels (`rgba(255,255,255,0.30)`, 20px blur, white 48% border). Fonts: Syne for display, Manrope for body, Playfair Display for the wordmark only.

## Milestones (★ = stop for review)

1. ★ **Scaffold**: FastAPI and Vite running, theme and fonts, styled Stylist hero with the glass prompt box.
2. **Data + ported core**: models, seed closet (~25 items, no waterproof outerwear) and calendar, generator tests, Closet page.
3. ★ **APIs**: read the docs, implement adapters (live / replay / mock), preflight health check. Show one real call to each API in the logs.
4. **Agent + tools**: all 6 tools, `/api/stylist/plan` end to end, plan validation.
5. ★ **Stylist UI + Agent Trace**: plan view, score breakdowns, gap card, streamed or polled trace.
6. **Agentic Scan**: upload → Vision → Decisions classify → auto-save with undo.
7. **Demo hardening**: reset endpoint, fallbacks, mode badge, README demo script, polish at 1440px.

## Known risks

- System Python is 3.9, so we use `uv` to pin Python 3.11.
- Open-Meteo forecasts only about 16 days out, so demo trips are seeded 3–10 days from today.
- Seed photos are stored locally in `backend/seed_images/`, not hotlinked.
- HEIC support needs `pillow-heif`. If it won't install, HEIC is disabled and nothing else breaks.
- A live plan can take 20–40 seconds. The streamed trace covers the wait.

## Non-goals

No marketplace scraping, no SMS, no Calendar OAuth, no auth, no social/Rack/moderation, no Pinecone, Cloudinary or Groq, no Expo.
