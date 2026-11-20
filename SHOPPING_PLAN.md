# Implementation Plan: Should I Buy This? + Shop Your Gaps

Spec: *Fashionistas: Should I Buy This? + Shop Your Gaps* (Nov 20, 2026).
This plan maps that spec onto the current codebase and splits it into phases. Phases 0–6 fit the spec's 3-hour build; Phase 7 is post-hackathon.

---

## Branching

All of this work happens on **`feature/buy-check-shop-gaps`**, which was branched from `main`. Nothing goes straight to `main`.

- Commit each phase separately, with the phase number in the message (for example `Phase 2: buy-check API`), so a broken phase can be reverted on its own.
- Teammates working in parallel can branch off `feature/buy-check-shop-gaps` (for example `feature/buy-check-shop-gaps-ui`) and open PRs back into it.
- The feature branch merges into `main` through **one PR**, opened only after Phase 6 passes: `make test` is green and the demo has been run through end to end.
- Until then, `main` stays as it is now, so the existing Stylist and Scan demo is always one checkout away if the new features break on demo day.

---

## Decisions to read first

These change or sharpen the spec, based on what's already in the repo.

1. **Count outfits in code; use Claude for judgment.** The spec has one LLM call return everything, including `outfit_count`. We already have a deterministic outfit engine ([outfit_generator.py](backend/app/core/outfit_generator.py)). An LLM asked to count combinations will guess, and give a different number every run. So:
   - **Code computes:** outfit count, top-outfit candidates, duplicate candidates, the closet slots the item fills, calendar matches, and a baseline score.
   - **One Claude call** (through `decisions_client`, so live → replay → mock still applies) confirms which duplicates are real and why, writes the "gap filled" phrase, estimates wears per year, picks the top 3 outfits from the candidates, and can move the score by up to ±15 with a reason.
   - **The app** applies the verdict thresholds (70+ Great buy, 40–69 Maybe, under 40 Skip). The API response keeps the spec's JSON shape.
2. **Score the catalog without Claude.** Running 30–40 catalog items through an LLM on every page load would be slow and expensive. Shop Your Gaps uses the deterministic score only. Gap labels come from rules, so no call is needed to write "Fills: …".
3. **Split Scan into "analyze" and "save".** `POST /api/closet/scan` ([scan.py](backend/app/routers/scan.py)) saves the item right away. Move the Vision + classify steps into a service function, `analyze_photo()`, that both Scan and Should I Buy This? call. Should I Buy This? saves only when the user taps **I bought it**.
4. **Use the app's vocabulary, not the spec sample's.** Use `"smart casual"`, not `smart_casual`. Categories come from `models.CATEGORIES`, color family from `gen.color_family()`, and season is a comma string that `gen.parse_seasons()` reads. The catalog JSON follows these rules.
5. **The demo closet doesn't match the spec's examples.** The seed closet already has a *Stone Cotton Trench* and a *Grey Hooded Puffer* (neutral fall outerwear) and *White Canvas Sneakers*, so "Fills: neutral outerwear" and "no white sneakers" would never show. It also has only one black jacket (the blazer).
   - **Recommendation:** keep the seed closet, since the Stylist rain-gap demo depends on it. Build the demo around gaps that really are empty, such as **waterproof outerwear** (this ties into the Stylist rain story), **tailored dark trousers**, and **formal outerwear**. Add one seed item, a *Black Cropped Bomber*, so the demo jacket can trigger "you own 2 similar black jackets."
   - Confirm the final gaps in Phase 0 by running the gap detector against the real closet.
6. **The user types the price.** Price lookup is out of scope. The result screen has an optional price field, and cost per wear is `price / est_wears_per_year`, computed in the browser.
7. **Pro and the paywall are mocked.** Each check is stored as a row, so the monthly count is a `COUNT(*)`. Pro is a flag set by the "Start 7-day free trial" button. `make reset` clears both.

---

## Phase overview

| Phase | Goal | Workstream | Time box |
|---|---|---|---|
| 0 | Data and vocabulary: catalog JSON and images, demo closet tweak, gap check | Data | 0:00–1:00 |
| 1 | Compatibility engine: pure functions, unit tested | Backend | 0:00–0:50 |
| 2 | Should I Buy This? API | Backend | 0:50–1:30 |
| 3 | Should I Buy This? UI | Frontend | 0:15–1:45 |
| 4 | Shop Your Gaps API and UI | Backend + Frontend | 1:15–2:15 |
| 5 | Money surfaces: commission screen, paywall, Pro mock | Frontend (+ small backend) | 1:45–2:15 |
| 6 | Demo hardening: feature freeze at 2:15 | Everyone | 2:15–2:45 |
| 7 | After the hackathon | — | — |

Frontend can start Phase 3 against a hard-coded copy of the response JSON (contracts below) before the backend is ready.

---

## Phase 0: Data and vocabulary

**Goal:** a catalog and demo closet that make the ranking look smart on stage.

- [ ] Add `backend/catalog/catalog.json` with **30 items** across 6–8 fictional stores (Northline Apparel, Urban Thread, …). Fields:
  ```json
  {
    "id": "p_001", "name": "Oat Wool Overshirt", "store": "Northline Apparel",
    "price": 68, "image": "/media/catalog/p_001.jpg",
    "category": "outerwear", "subcategory": "jacket", "color": "oatmeal",
    "formality": "smart casual", "season": "fall, winter",
    "material": "wool", "waterproof": false, "sponsored": false
  }
  ```
- [ ] Stack the catalog. About 8 items fill the 2–3 chosen gaps (for example 3 waterproof shells, 3 dark tailored trousers, 2 formal coats). About 15 are neutral items that work with the closet but fill no gap. About 7 are duplicates or poor fits that should score low.
- [ ] Mark **2 items sponsored**: one that scores 70+ (shown with the "Sponsored" label) and one that scores under 70 (hidden; this proves the trust rule).
- [ ] Get images for `backend/catalog/images/`. Use openly licensed Wikimedia Commons photos, like the seed set, and credit them in `backend/catalog/CREDITS.md`. If time runs short, the product card falls back to a color swatch, so missing images never block the build.
- [ ] Mount `/media/catalog` in [main.py](backend/app/main.py), next to `/media/seed`.
- [ ] Add the *Black Cropped Bomber* to the seed [manifest.json](backend/seed_images/photos/manifest.json) with a photo and credit.
- [ ] Pick the demo jacket: a real jacket a teammate will scan on stage. Its verdict should come out **Maybe** (good outfit count, but it duplicates the black jackets).

**Done when:** a test loads the catalog, checks that every field uses valid vocabulary and every image path exists, and checks that there are 25–40 items and at least one sponsored item on each side of 70.

---

## Phase 1: Compatibility engine (backend, pure functions)

**New file:** `backend/app/core/compatibility.py`. No database or network calls, so it's easy to unit test, like `outfit_generator`.

| Function | What it does |
|---|---|
| `count_outfits(new, closet) -> (count, candidates)` | Enumerates the generator's templates (top + bottom + shoes, dress + shoes, optional outerwear) where `new` fills one slot. Other slots must have formality within one step on the `FORMALITIES` ladder, overlapping seasons, and `color_harmony >= 0`. Reuses `item_slots`, `color_harmony` and `parse_seasons`. Returns the count (displayed as "50+" above 50) and the 10 best combos by `score_combo`. |
| `find_duplicates(new, closet)` | Closet items with the same category, the same `color_family`, and the same subcategory (as a stand-in for silhouette). |
| `closet_slots(closet)` / `find_gaps(closet)` | Groups the closet by category × color family × formality × season. Returns slots that are empty (0 items) or thin (1 item) in the core categories (tops, bottoms, outerwear, shoes), plus the rule-based gaps already found in [gaps.py](backend/app/tools/gaps.py), such as waterproof outerwear. Each gap gets a readable label, for example "waterproof outerwear" or "dark tailored trousers." |
| `gaps_filled(new, gaps)` | The gap labels this item closes. |
| `calendar_matches(new, events)` | Events in the next 30 days where the event's dress-code hint fits the item's formality (reuse `_dress_target` from `decisions_client`) and the season fits. |
| `baseline_score(...)` | Starts at 20. Adds 3 per outfit (capped at 40), 25 if it fills a gap, and 5 per calendar match (capped at 15). Subtracts 20 per duplicate (capped at −40). Clamped to 0–100. |
| `verdict(score)` | `great_buy` / `maybe` / `skip`, using the spec's thresholds. |

- [ ] `backend/tests/test_compatibility.py`: outfit counting on a tiny in-memory closet, duplicate detection, a gap filled versus not filled, verdict boundaries at 39/40/69/70, and the score clamp.

**Done when:** tests pass, and running the engine against the seed closet lists the 2–3 gaps chosen in Phase 0.

---

## Phase 2: Should I Buy This? API

- [ ] **Refactor:** move Vision + classify out of [scan.py](backend/app/routers/scan.py) into `backend/app/services/item_analysis.py::analyze_photo(file) -> (ItemClassification, ValidatedImage, trace)`. `/api/closet/scan` keeps its current behavior by calling `analyze_photo` and then saving. The existing `test_scan.py` must still pass.
- [ ] **Claude call:** add `judge_purchase(item, compact_closet, candidates, duplicates, gaps, events, baseline)` to [decisions_client.py](backend/app/integrations/decisions_client.py), using the same `_run` / live → replay → mock / recorder pattern as `rate_gaps`. Send the closet as a compact list (id, category, color, formality, season), never images, as the spec suggests. Treat item names as quoted data, the same injection rule the file already uses. Add a `_mock_purchase` that returns the baseline unchanged.
- [ ] **Table:** add `BuyCheck` to [models.py](backend/app/models.py) with these fields: `id`, `created_at`, `attrs` (JSON), `result` (JSON), `image_path`, `kept` (bool). Store the image under `uploads/pending/` until the user keeps the item.
- [ ] **Router:** add `backend/app/routers/buy_check.py`:

  | Endpoint | Behavior |
  |---|---|
  | `POST /api/buy-check` (multipart `file`) | If the user isn't Pro and has made 3 or more checks this month, return **402** `{paywall: "buy_check", used, limit}` *before* any API call. Otherwise: analyze → engine → `judge_purchase` → verdict → save `BuyCheck` → respond. |
  | `POST /api/buy-check/{id}/keep` | **I bought it.** Moves the image into uploads and creates a `WardrobeItem` (`source="buy_check"`) with the attributes already filled in. |
  | `GET /api/buy-check/{id}` | Fetches a past result again (also a demo safety net). |

  Response:
  ```json
  {
    "check_id": "chk_…",
    "item": { "name": "Black Cropped Jacket", "category": "outerwear", "color": "black", "formality": "smart casual", "season": "fall, winter", "image_url": "…" },
    "result": {
      "score": 58, "verdict": "maybe", "outfit_count": 12,
      "duplicates": [{ "item_id": "itm_…", "name": "Black Cropped Bomber", "reason": "similar black cropped jacket" }],
      "gap_filled": null,
      "calendar_matches": [{ "event": "Team dinner", "date": "2026-11-27" }],
      "est_wears_per_year": 30,
      "top_outfits": [{ "items": [ "<WardrobeItem>", "…" ], "includes_new": true }],
      "score_reason": "Pairs with most of your bottoms, but overlaps two jackets you own"
    },
    "trace": [ "<TraceStep>", "…" ],
    "usage": { "checks_used": 2, "limit": 3, "pro": false }
  }
  ```
- [ ] Register the router in [main.py](backend/app/main.py). Make the dev reset in [seed.py](backend/app/seed.py) also clear `BuyCheck` rows and the Pro flag.
- [ ] `backend/tests/test_buy_check.py` (mock mode): the response shape, nothing saved until `/keep` is called, `/keep` creates a closet item, and the 4th check returns 402 without calling Vision or Claude.

---

## Phase 3: Should I Buy This? UI

- [ ] Add a `/buy` route and `frontend/src/pages/BuyCheck.tsx`. Register it as a tab in [App.tsx](frontend/src/App.tsx) (the tabs stay mounted).
- [ ] Entry points: a **Should I Buy This?** button on the Scan page and a call-to-action on the home/Stylist page, as in step 1 of the spec. Keep the nav at 3 tabs plus **Shop**; five tabs crowd mobile.
- [ ] Upload step: reuse the Scan page's uploader. Extract it into a component if needed. Show progress with the existing `AgentTrace`.
- [ ] Result screen, in the spec's order:
  - `VerdictBadge` (new): Great buy / Maybe / Skip, using colors from `theme/colors.ts`
  - The headline: **"Unlocks 12 new outfits"**
  - Duplicate warning (links to the matching closet items)
  - "Fills: …" gap line
  - Calendar line: "Works for 3 events this month, including Friday's dinner"
  - Optional price input → "$49 / about 30 wears = $1.63 per wear"
  - 3 outfit previews (reuse `OutfitCard`, with the new item highlighted)
- [ ] Actions:
  - **I bought it** → `POST /keep`, show a toast, refresh the closet
  - **Save for later** → wishlist in `localStorage` only (the spec skips wishlist persistence)
  - **Find something better** → `/shop?category=<item.category>&from=buy`
- [ ] Add the types and `api.buyCheck()`, `api.keepBuyCheck()` to [types.ts](frontend/src/lib/types.ts) and [api.ts](frontend/src/lib/api.ts).

---

## Phase 4: Shop Your Gaps

**Backend**
- [ ] Add `backend/app/services/catalog.py`. It loads `catalog.json` once and converts entries into the engine's item type.
- [ ] Add `backend/app/routers/shop.py`:
  - `GET /api/shop?category=` → `{ gaps: [...], products: [...], hidden_by_trust_rule: n }`
  - For each product: `outfit_count`, `fills` (gap labels), `score`, `verdict`, `sponsored`.
  - Calendar needs (step 2 of the spec): gaps from events, such as a black-tie event with no formal outfit, are merged into the gap list using the existing rules in `gaps.py`.
  - **Trust rule:** drop every product with a score under 70, sponsored or not.
  - **Ranking:** outfit count first, then fills a gap, then price. Budget is a simple optional `max_price` parameter.
- [ ] `backend/tests/test_shop.py`: the trust rule (the sponsored item under 70 never appears), ranking order, and the category filter.

**Frontend**
- [ ] Add a `/shop` route, `frontend/src/pages/ShopGaps.tsx`, and a nav link.
- [ ] Gap summary at the top (reuse `GapCard`), plus category filter chips that are preselected when the user arrives from Should I Buy This?.
- [ ] `ProductCard` (new): photo (or color-swatch fallback), name, store, price, **"Unlocks 9 outfits"** in the most prominent spot, "Fills: neutral outerwear", and a "Sponsored" label.
- [ ] A small footer line: "N items hidden because they don't fit your closet." This puts the trust rule on screen.

---

## Phase 5: Money surfaces (mocked)

- [ ] `CommissionModal`: tapping **Buy** opens "You're going to *{store}*. Fashionistas earns a commission at no cost to you." with **Continue** (shows a "Demo: no real checkout" toast) and **Cancel**. Optionally log the outbound click with `POST /api/shop/{id}/click`.
- [ ] `PaywallModal`: shown when `/api/buy-check` returns 402. Copy: "You've used your 3 free checks this month." The modal shows $4.99/mo and $39.99/yr, plus a **Start 7-day free trial** button. That button calls `POST /api/pro/trial`, which sets the mock Pro flag, then retries the check automatically.
- [ ] `GET /api/pro` returns `{pro, checks_used, limit}` and shows on the result screen as "2 of 3 free checks used".
- [ ] Out of scope today: the 75-item closet cap and the 3-day calendar limit. They're in the tier table but not on the demo path.

---

## Phase 6: Demo hardening (feature freeze at 2:15)

- [ ] **Safety net:** run `make warmup` on the demo device with the actual demo-jacket photo. The recorder keys replays on the image hash, so the replay only works for that exact photo. Add the buy-check path to [warmup.py](backend/scripts/warmup.py). Also save a known-good `check_id` so `GET /api/buy-check/{id}` can show it instantly if everything else fails.
- [ ] Make sure `make reset` restores the closet (including the bomber), clears checks, and resets Pro, so the 4th-check paywall fires the same way on every run.
- [ ] Run through the demo script twice in order: Problem → scan the jacket (Maybe, 12 outfits, 2 black jackets, calendar line) → Find something better → top card fills a gap → Buy → commission screen → 4th check → paywall.
- [ ] After 2:15, fix only bugs on the demo path.

---

## Phase 7: After the hackathon

- Real product feeds from affiliate networks (Impact, CJ) replace `catalog.json`. Catalog scoring moves to a background job and is cached per user.
- Wishlist persistence, product link parsing, and price lookup.
- Enforce the remaining Free/Pro limits (75 items, 3 outfits a day, 3-day calendar) and add real billing.
- Outbound click and conversion tracking, so pilots can measure return rates.
- Sponsored placement controls, and opt-in anonymized closet insights.

---

## Files at a glance

**New:** `backend/app/core/compatibility.py`, `backend/app/services/item_analysis.py`, `backend/app/services/catalog.py`, `backend/app/routers/buy_check.py`, `backend/app/routers/shop.py`, `backend/catalog/{catalog.json,images/,CREDITS.md}`, `backend/tests/test_{compatibility,buy_check,shop,catalog}.py`, `frontend/src/pages/{BuyCheck,ShopGaps}.tsx`, `frontend/src/components/{VerdictBadge,ProductCard,CommissionModal,PaywallModal}.tsx`

**Changed:** `scan.py` (calls `analyze_photo`), `decisions_client.py` (`judge_purchase`), `models.py` (`BuyCheck`), `main.py` (routers, `/media/catalog`), `seed.py` (reset), `manifest.json` (bomber), `warmup.py`, `App.tsx`, `NavBar.tsx`, `Scan.tsx`, `Stylist.tsx`, `api.ts`, `types.ts`

## Risks

| Risk | Mitigation |
|---|---|
| The demo jacket's verdict differs from the script on stage | Tune the catalog and seed against the actual jacket in Phase 0; the warmup recording fixes the Claude output |
| Finding catalog images eats the Data hour | Color-swatch fallback on cards; images are a "should," not a blocker |
| The outfit count looks inflated (hundreds) | Strict formality and season rules; cap the display at "50+" |
| The scan refactor breaks the existing Scan demo | Keep `test_scan.py` green; do the refactor first, in its own commit |
