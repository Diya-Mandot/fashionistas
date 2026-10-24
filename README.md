# EcoStylist: Context-Aware Stylist

Hackathon Track 1 (Agents in Action). An agent gathers trip context (weather, calendar, closet)
and the Decisions API scores outfits against your vibe. See [PLAN.md](PLAN.md).

## Setup (clean Mac)

Requires [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
uv python install 3.11          # system Python on macOS is too old
make install                    # backend deps (uv) + frontend deps (npm)
cp backend/.env.example backend/.env   # then fill in API keys
make dev                        # backend :8000, frontend :5173
make test
```

## Backend progress

Agents SDK adapters, async Decisions adapters, and weather integration are implemented.
Photo scanning comes next, followed by outfit planning.
The frontend does not call these adapters yet.
The new async Decisions adapter lives in `backend/app/integrations/decisions_adapter.py`.
Main's synchronous `decisions_client.py` remains available. Consolidating these interfaces remains integration work.

- `AgentsClient.run_agent(goal, tools, context)` runs the SDK tool loop.
- `DecisionsClient.classify_item(description, image_url=...)` returns tags and confidence values.
- `DecisionsClient.score_outfits(candidates, context)` returns five scores per outfit.
- Scores range from zero to four. The server preserves the original garment IDs.
- Low confidence tags become `unknown`. Material needs explicit evidence.
- Live mode uses bounded retries and timeouts. Failures never silently become mock results.

Both adapters return `data`, `source`, `recorded_at`, and `warnings`.
Set `AGENTS_MODE` and `DECISIONS_MODE` to `live`, `replay`, or `mock`.
Live mode is the default. Replay requires the same request and a successful recording.
Replay does not execute tools. Mock mode does not classify garments or produce real outfit scores.

Successful async adapter calls save validated results in `backend/logs/api_calls.jsonl`.
These recordings exclude request bodies, keys, and image bytes.
The existing synchronous adapter uses its original recording format and behavior.
Results can contain personal information, including tool results. Keep this ignored file local.
Delete it to clear saved results. File permissions restrict access to the current user.

Read configuration without calling either API:

```bash
curl http://localhost:8000/api/health/apis
```

Explicitly test both configured adapters:

```bash
curl -X POST http://localhost:8000/api/health/apis/check
```

This POST makes paid calls in live mode. Only `live_verified: true` confirms current API access.
Tests use simulated API responses, including the real SDK tool loop.
Live account access remains untested until the explicit check succeeds.

The adapters use the [Agents SDK](https://openai.github.io/openai-agents-python/)
and [Decisions API](https://developers.openai.com/api/docs/guides/decisions).
The hosted Agents API is not used in this implementation.

## Existing work and reuse

Compare new work against [WIP commit 9c6108b](https://github.com/Diya-Mandot/fashionistas/commit/9c6108bcefc78347224ab4cc260165bf6df1e058).
Current main also includes commit `886b1b4`.

| Existing component | Original commit | Integration approach |
|---|---|---|
| Closet models, SQLite, seed data, and CRUD | `9c6108b` | Reuse the existing data layer. |
| Mock calendar and event routes | `9c6108b` | Reuse for event context. |
| Outfit candidate generator and weather rules | `9c6108b` | Supply weather to existing rules during planning. |
| Closet page and shared frontend types | `886b1b4` | Connect future features to the existing page. |
| Synchronous Decisions adapter | `886b1b4` | Preserve callers; consolidate with the async adapter during integration. |

The weather integration adds the missing provider lookup. It does not replace the generator's weather rules.

## Weather integration

`GET /api/weather` accepts `city`, inclusive `start` and `end` dates, and optional `country_code` and `location_id`.
Use ISO dates, uppercase country codes, and a maximum range of 31 days.

```bash
curl --get http://localhost:8000/api/weather \
  --data-urlencode 'city=Seattle, WA' \
  --data-urlencode 'country_code=US' \
  --data-urlencode "start=$(date +%F)" \
  --data-urlencode "end=$(date +%F)"
```

The service uses [Open-Meteo forecasts](https://open-meteo.com/en/docs)
and [city search](https://open-meteo.com/en/docs/geocoding-api).
Exact city names take precedence over nearby prefix matches. Multiple exact matches require a location selection.
Use a returned `location_id` with the same city query to select a city.
Dates use the selected city's timezone. Temperatures use Fahrenheit; precipitation values are probabilities in percent.
Daily fields match the existing frontend weather fields: `high_f`, `low_f`, and `precip_pct`.
Responses include status, missing dates, warnings, retrieval time, and cache information.

Forecasts use a bounded, 30-minute memory cache. This cache is separate from model replay recordings.
Out-of-range dates and provider failures stay unavailable. Missing values remain null.
The service does not substitute nearby dates, seasonal averages, or dry weather.
The `weather_tool(client)` factory supplies the existing `AgentTool` contract for later planner integration.

Verification: 70 backend tests pass. A live Seattle lookup returned three days without missing data.
The repeat request used the cache. Complete scanning and planning flows remain untested.

## Ported from the capstone

| File here | Source |
|---|---|
| `frontend/src/theme/colors.ts` | `ecostylistfe/theme/colors.ts` (native glass fallback dropped) |
| `frontend/src/theme/typography.ts` + `src/index.css` | `ecostylistfe/theme/typography.ts` |
| `frontend/src/theme/glass.ts` | `ecostylistfe/theme/glass.ts` (web branch only) |
