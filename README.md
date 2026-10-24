# EcoStylist: Context-Aware Stylist

Hackathon **Track 1: Agents in Action**. Built on the OpenAI **Agents API** and **Decisions API**.

Type something messy like *"Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy."*

The **agent** decides for itself to check the weather, read your calendar and search your closet. It builds candidate outfits for each event and asks the **Decisions API** to score them on five criteria: vibe, dress code, weather, color harmony and freshness. It flags closet gaps, like a rainy forecast with no waterproof layer, and suggests secondhand fixes. You get back a day-by-day packing plan. A live **Agent Trace** shows every input, tool call, decision and result.

The **Scan** tab works the same way. Upload a photo, Google Vision reads it, the Decisions API classifies it, and it's saved to your closet with no typing.

See [PLAN.md](PLAN.md) for the full design.

## Setup (clean Mac)

Requires [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
uv python install 3.11                 # macOS system Python is too old
make install                           # backend deps (uv) + frontend deps (npm)
cp backend/.env.example backend/.env   # then paste OPENAI_API_KEY (see below)
make dev                               # backend :8000, frontend :5173
```

For the live demo, use **`make start`** instead: it builds the frontend and serves the whole app from http://localhost:8000 with no hot reload, which is more stable on stage.

Open http://localhost:5173.

```bash
make test        # backend tests
make preflight   # one tiny REAL call to each API (backend must be running)
make warmup      # run every demo path live once, saving replay recordings
make reset       # restore the demo closet and clear runs
```

### API key

One `OPENAI_API_KEY` covers both APIs. Create it at https://platform.openai.com/api-keys **in the project that holds the hackathon credits**. The Agents API needs `api.agents.read`, `api.agents.write` and `api.responses.write`. To check that the key loaded without printing it, run `cd backend && uv run python check_key.py`.

**Google Vision** (Scan) uses the first available of: `GOOGLE_VISION_API_KEY`, a service-account file in `GOOGLE_APPLICATION_CREDENTIALS`, or your gcloud login (`gcloud auth application-default login`, same as the capstone). With none of these, Scan uses the photo plus colors detected on your machine, and says so in the trace.

## Calendar and location

- **Calendar.** Set `CALENDAR_ICS_URL` in `backend/.env` to your calendar's private iCal address. In Google Calendar that's Settings → your calendar → *Integrate calendar* → **Secret address in iCal format**; Apple and Outlook ICS links work too. The agent's `read_calendar` tool then reads your real events, including recurring ones, and infers dress-code hints from titles or a "Dress code: …" line in the description. Without the URL, or if the feed fails, it uses the seeded demo calendar and says so in the trace. To show the demo trips alongside your events, set `CALENDAR_INCLUDE_DEMO=true`. Event titles and locations are sent to the Agents API as part of the plan.
- **Location.** Click **Use my location** under the prompt. The browser asks permission, and the backend turns the coordinates into a city using OpenStreetMap. When a message doesn't name a destination, the agent plans for that city, and the weather tool uses your exact coordinates. Without it, `HOME_CITY` is used.

## The demo closet

The closet is real product photos in `backend/seed_images/photos/`, labelled in `manifest.json`. **Photos are git-ignored and stay on your machine**: a fresh clone starts with an empty closet, and you add clothes in the **Scan** tab or with the importer. The local set deliberately has **no waterproof outerwear and no shoes**, so the agent flags both as closet gaps on a rainy trip.

```bash
make import-photos DIR=~/Desktop/more-clothes   # JPG/PNG/WEBP/HEIC
make reset                                      # reload the closet (deletes items scanned in the app!)
```

New photos are classified by the same Vision → Decisions pipeline as the Scan tab. Hand-labelled entries are never overwritten unless you pass `--include-manual`. The importer warns you if a waterproof jacket slips in, since that removes the rain-gap moment.

## Live, replay and mock (the APIs must work no matter what)

| Mode (`AGENTS_MODE` / `DECISIONS_MODE`) | Behavior |
|---|---|
| `live` (default) | Real API calls. The SDK retries 408/409/429/5xx with backoff and honors `Retry-After`. Every call is logged to `backend/logs/api_calls.jsonl` with keys redacted. Successful responses are saved to `backend/recordings/`. |
| `replay` | Reuses a **recorded real response** for the exact same request. Labelled "Replayed live call". |
| `mock` | Local stand-in, labelled **MOCK**. Only used if live and replay both fail. |

In `live` mode the fallback is automatic: live, then replay, then mock. Every trace step shows which source actually answered. The nav badge shows the mode; click it to run the preflight or reset the demo data. **Before demoing, run `make preflight`, then `make warmup`.**

## Architecture

```
backend/   FastAPI, SQLModel + SQLite (create_all, no migrations), Python 3.11 via uv
  app/integrations/agents_client.py    run_agent(): Agents API session, function tools, requires_action loop
  app/integrations/decisions_client.py score_outfits / classify_item / rate_gaps
  app/tools/                           the agent's tools (function + JSON schema each)
  app/agent/                           run orchestration (background thread, persisted trace), plan validation
  app/core/outfit_generator.py         ported candidate builder
  app/core/vision.py                   ported Vision + upload validation
frontend/  React + Vite + TypeScript (strict) + Tailwind; pages Stylist, Closet, Scan
```

**How a plan run works:** `POST /api/stylist/plan` starts a background run, and the UI polls `GET /api/stylist/runs/{id}` every 700 ms so steps animate in as they happen. The agent gets 7 function tools and chooses its own order:

| Tool | What it does |
|---|---|
| `get_weather_forecast` | Open-Meteo, cached 30 min. Beyond the forecast window it returns the furthest available days; on failure it uses a seasonal average. |
| `read_calendar` | Demo calendar seeded relative to today (no OAuth). |
| `query_closet` | Closet items with attributes and wear history. |
| `build_and_score_outfits` | Ported generator, then the Decisions API: 5 `score` questions per candidate, candidates sent **by index only**. |
| `find_closet_gaps` | Rules detect gaps; the Decisions API rates each must-have / nice-to-have. |
| `suggest_secondhand_item` | Depop, ThredUp, Poshmark and eBay search links. No scraping. |
| `submit_plan` | The server maps outfit refs to real item IDs and drops unknown refs/IDs with a warning. |

**Safety (from the capstone's `outfit_curator.py`):** the model never sees or produces closet IDs. It picks outfits by ref, and the server maps refs back to IDs. The user's text is passed as quoted data and the model is told to ignore any instructions in it. Decisions questions reference candidates only by index.

## Ported from the capstone

| File here | Source | Changes |
|---|---|---|
| `backend/app/core/outfit_generator.py` + `tests/test_outfit_generator.py` | `ecostylistbe/app/core/outfit_generator.py` | Verbatim (25 tests pass) |
| `backend/app/core/vision.py` | `ecostylistbe/app/core/closet_scan_service.py` | Kept `validate_upload`, HEIC→JPEG, `parse_label_suggestions`, the category guesser and a Vision adapter (now REST + API key). Dropped Cloudinary (uploads stored locally) and the SSRF downloader. |
| Safety pattern in `tools/outfits.py`, `agent/plan.py`, `decisions_client.py` | `ecostylistbe/app/core/outfit_curator.py` | Index/ref-only selection, user text treated as untrusted data |
| `backend/app/models.py` (`WardrobeItem`) | `ecostylistbe/app/models/wardrobe_item.py` | Field list only, plus `formality` and `waterproof` |
| `frontend/src/theme/colors.ts` | `ecostylistfe/theme/colors.ts` | Native glass fallback dropped; added `emeraldDeep` (derived, for score bars) |
| `frontend/src/theme/typography.ts` + `src/index.css` | `ecostylistfe/theme/typography.ts` | Same presets as CSS classes |
| `frontend/src/theme/glass.ts` | `ecostylistfe/theme/glass.ts` | Web branch only |

Demo closet photos are stored locally in `backend/seed_images/photos/` (git-ignored), so the demo never depends on image hosts.

## 2-minute demo script

1. *"Our capstone, EcoStylist, generated outfits from hardcoded rules. Watch what happens with a real request."* Paste the Seattle prompt (below) and click **Plan my outfits**.
2. **Point at the trace.** The agent chose to check the weather, read the calendar and query the closet. That's the API input and the agent's tasks, each with its exact request and response.
3. **Open a Decisions step.** The per-criterion scores show *why* the dinner outfit won for "professional but edgy". Open **Score breakdown** on the outfit card for the same view.
4. **Show the gap card.** Rain is forecast and there's no waterproof layer in the closet, so the agent pivoted and suggested a secondhand trench with links.
5. **Scan tab.** Upload a photo of a jacket. It's classified and saved with zero typing; Undo is there for 10 seconds.
6. **Close:** *"Rules can't parse vibes or weather. An agent that gathers context, plus a decision engine that scores it, can."*

**Prompts to paste:**
- *Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy.*
- *Pack my bag for NYC this weekend: networking brunch and a Broadway show*
- *First day at a new job Monday, rainy, want to look put-together but not stiff*

**Before going on stage:** `make reset` (note: it removes items scanned during rehearsal), `make preflight` (both APIs green), `make warmup`, and check that the nav badge says **Live APIs**.
