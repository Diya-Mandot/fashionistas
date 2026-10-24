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

The first integration step is complete: Agents SDK and Decisions API adapters.
Weather, photo scanning, and outfit planning follow in that order.
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

## Ported from the capstone

| File here | Source |
|---|---|
| `frontend/src/theme/colors.ts` | `ecostylistfe/theme/colors.ts` (native glass fallback dropped) |
| `frontend/src/theme/typography.ts` + `src/index.css` | `ecostylistfe/theme/typography.ts` |
| `frontend/src/theme/glass.ts` | `ecostylistfe/theme/glass.ts` (web branch only) |
