# Fashionistas: Context-Aware Stylist

Hackathon **Track 1: Agents in Action**. Built on **Claude** (Anthropic Messages API): a tool-use agent loop plus structured-output scoring and classification.

Type something messy like *"Packing for a tech conference in Seattle Tue–Thu. There's a fancy dinner Tuesday night and I want to look professional but a little edgy."*

The **agent** decides for itself to check the weather, read your calendar and search your closet. It builds candidate outfits for each event and asks **Claude** to score them on five criteria: vibe, dress code, weather, color harmony and freshness. It flags closet gaps, like a rainy forecast with no waterproof layer, and suggests secondhand fixes. You get back a day-by-day packing plan. A live **Agent Trace** shows every input, tool call, decision and result.

The **Scan** tab works the same way. Upload a photo, Google Vision reads it, Claude classifies it, and it's saved to your closet with no typing.

See [PLAN.md](PLAN.md) for the full design.

## Setup (clean Mac)

Requires [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
uv python install 3.11                 # macOS system Python is too old
make install                           # backend deps (uv) + frontend deps (npm)
cp backend/.env.example backend/.env   # then paste ANTHROPIC_API_KEY (see below)
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

One `ANTHROPIC_API_KEY` covers both the agent and the scoring calls. Create it at https://platform.claude.com/settings/keys. Both default to `claude-opus-5-5` at `low` effort; override with `AGENTS_MODEL` / `DECISIONS_MODEL` and `AGENTS_EFFORT` / `DECISIONS_EFFORT`. To check that the key loaded without printing it, run `cd backend && uv run python check_key.py`.

**Google Vision** (Scan) uses the first available of: `GOOGLE_VISION_API_KEY`, a service-account file in `GOOGLE_APPLICATION_CREDENTIALS`, or your gcloud login (`gcloud auth application-default login`, same as the capstone). With none of these, Scan uses the photo plus colors detected on your machine, and says so in the trace.

### Personal colors

Open **Colors that suit me** in the stylist. Enter colors you like near your face, then run a plan. The stylist gives a small ranking boost to outfits with a matching top, dress, or jacket. The outfit card shows the matching shades. Your browser saves the list, and each new plan sends it to the backend for ranking.

Color harmony measures how garments work together. Your preferred colors are a separate input. The ranker uses the closet's color labels, so accurate labels matter.

The **Personal colors** row shows the share of labeled tops, dresses, and jackets that match the palette. The ranker adds up to 0.08 to an outfit's ranking score. It uses this addition alongside the existing score and repeat penalty. The Agent Trace shows the exact addition.

You can also select a **Profile photo** under **Colors that suit me**. Use a clear photo in daylight. When you start a plan, Fashionistas sends the resized photo, your preferred colors, closet color labels, and research summaries to Claude. The photo stays selected until you remove it or reload the page. Fashionistas saves the color assessment in the **Agent Trace** and does not save the photo. This option needs an Anthropic API key and `DECISIONS_MODE=live`. If Claude cannot assess the photo with moderate confidence, the stylist uses your manually entered colors.

- [Clothing Aesthetics](https://journals.sagepub.com/doi/10.1177/20416695211053361) tested simulated clothing colors against 12 faces of White women. It supports testing color near the face and has limited coverage of skin tones.
- The photo prompt uses two CC BY 4.0 data summaries. It counts the cool-hue column by face group for Experiment 1 in [Perrett and Sprengelmeyer's trial data](https://doi.org/10.6084/m9.figshare.14596905.v1). It also averages the Experiment 2 warmth columns by eye-color group, across participants, tasks, and hair conditions, in [Perrett's participant means](https://doi.org/10.6084/m9.figshare.20795986.v1).
- [Outfits for You (O4U)](https://github.com/AemikaChow/AiDLab-fAshIon-Data) provides 29,352 outfits with expert annotations that include skin color. The authors restrict the data to academic use without further permission.
- [Polyvore Outfits](https://github.com/mvasil/fashion-compatibility) provides outfit compatibility benchmarks. [Learning Color Compatibility in Fashion Outfits](https://arxiv.org/abs/2007.02388) uses this benchmark to study outfit colors.
- [Color Compatibility From Large Datasets](https://www.dgp.toronto.edu/~donovan/color/) provides human-rated five-color themes under CC BY-NC-SA. The themes represent general palette preferences.

**LlamaPress research source.** Copy [the versioned research file](backend/app/data/palette-evidence.json) to `public/fashionistas/palette-evidence.json` in your LlamaPress Rails app. Verify that the app-only URL serves the JSON at that path. Set `LLAMAPRESS_PALETTE_URL` in `backend/.env` to the HTTPS URL of that file, then restart Fashionistas.

Fashionistas downloads the research with a GET request. It sends no portrait or closet information with that request. Claude uses the research and profile photo to suggest colors. If the LlamaPress file is unavailable or invalid, Fashionistas uses the bundled evidence and records the source in the trace.

## Deploy (Railway)

One Railway service runs everything: the [Dockerfile](Dockerfile) builds the frontend and serves it and the API from uvicorn, the same as `make start`. Every push to the connected branch redeploys.

1. In Railway: **New Project → Deploy from GitHub repo**, then pick this repo. Railway reads [railway.json](railway.json) and builds the Dockerfile. In the service's **Settings → Source**, set the branch to `main`.
2. **Add a volume** (right-click the service → Attach volume) mounted at `/data`. Without it, the closet, scans and recordings are wiped on every deploy.
3. **Variables:** `DATA_DIR=/data`, `ANTHROPIC_API_KEY`, `DEV_ENDPOINTS=false` (otherwise anyone can reset the closet), and optionally `GOOGLE_VISION_API_KEY`, `CALENDAR_ICS_URL` and `HOME_CITY`. For Google Calendar sync, also set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `GOOGLE_OAUTH_REDIRECT_URI=https://<your-domain>/api/calendar/google/callback`, and add that same URI to the OAuth client in Google Cloud Console. The token is saved under `/data/private_calendar/`.
4. **Settings → Networking → Generate Domain** to get a public `*.up.railway.app` URL.

Keep it to one replica, since SQLite and in-progress plan runs live on that one machine. There's no login, so anyone with the URL can run plans on your Anthropic credits. Replay recordings are gitignored, so the deployed app starts with none; replay only works for calls it has made live itself.

## Calendar and location

- **Google Calendar sync.** Put an OAuth client ID and secret in `backend/.env` (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`; setup below), restart the backend, and click **Connect Google Calendar** on the home page. Google asks for read-only calendar access. The refresh token is saved to `backend/private_calendar/google_token.json` (git-ignored), and events are read live from the Calendar API, cached for 2 minutes. The ↻ button forces a sync. Cancelled events, events you declined, and working-location, out-of-office and focus-time blocks are skipped. `GOOGLE_CALENDAR_IDS=all` reads every calendar ticked in your Google Calendar sidebar instead of only the primary one. If access is revoked or expires, the card says so, offers to reconnect, and the agent plans from your message alone in the meantime.
  - *Getting the keys:* in [Google Cloud Console](https://console.cloud.google.com/), create or pick a project. Then: (1) **APIs & Services → Library**, enable **Google Calendar API**. (2) **Google Auth Platform / OAuth consent screen**, choose *External*, fill in the app name and emails, add the scope `.../auth/calendar.readonly`, and under **Audience → Test users** add every Google account that will connect. (3) **Credentials → Create credentials → OAuth client ID → Web application**, and under *Authorized redirect URIs* add exactly `http://localhost:8000/api/calendar/google/callback`. Copy the client ID and secret into `backend/.env`. While the app is in *Testing*, Google shows an "unverified app" warning (click *Continue*), and refresh tokens expire after 7 days, so you'll need to reconnect weekly. Publishing the app removes that limit.
- **Calendar via iCal link (no OAuth).** Set `CALENDAR_ICS_URL` in `backend/.env` to your calendar's private iCal address, or to a folder holding an unzipped Google Calendar export (`backend/private_calendar/`, which is git-ignored; exports are a snapshot that doesn't update). In Google Calendar that's Settings → your calendar → *Integrate calendar* → **Secret address in iCal format**; Apple and Outlook ICS links work too. The agent's `read_calendar` tool then reads your real events, including recurring ones, and infers dress-code hints from titles or a "Dress code: …" line in the description. Without a connected calendar the agent plans from your message alone; if the feed fails it says so in the trace. Event titles and locations are sent to Claude as part of the plan.
- **Location.** Click **Use my location** under the prompt. The browser asks permission, and the backend turns the coordinates into a city using OpenStreetMap. When a message doesn't name a destination, the agent plans for that city, and the weather tool uses your exact coordinates. Without it, `HOME_CITY` is used.

## The demo closet

The closet is 41 real product photos in `backend/seed_images/photos/` (tops, bottoms, dresses, outerwear, shoes, activewear, accessories and bags), labelled in `manifest.json` (no wear history yet: every piece starts as never worn). The photos are openly licensed from Wikimedia Commons; see `CREDITS.md` in the same folder. A fresh clone starts with this closet; add more in the **Scan** tab or with the importer. The local set deliberately has **no waterproof outerwear**, so the agent flags it as a closet gap on a rainy trip.

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
  app/integrations/agents_client.py    run_agent(): Claude tool-use loop (tool_use -> local tool -> tool_result)
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
| `read_calendar` | Your connected Google Calendar (OAuth) or iCal feed; otherwise no events. |
| `query_closet` | Closet items with attributes and wear history. |
| `build_and_score_outfits` | Ported generator, then Claude: 5 `score` questions per candidate, candidates sent **by index only**. |
| `find_closet_gaps` | Rules detect gaps; Claude rates each must-have / nice-to-have. |
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

Demo closet photos are stored in the repo under `backend/seed_images/photos/`, so the demo never depends on image hosts.

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
