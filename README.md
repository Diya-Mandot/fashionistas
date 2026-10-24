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

## Ported from the capstone

| File here | Source |
|---|---|
| `frontend/src/theme/colors.ts` | `ecostylistfe/theme/colors.ts` (native glass fallback dropped) |
| `frontend/src/theme/typography.ts` + `src/index.css` | `ecostylistfe/theme/typography.ts` |
| `frontend/src/theme/glass.ts` | `ecostylistfe/theme/glass.ts` (web branch only) |
