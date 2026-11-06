# Journey Planner, Best Route Explorer and tracking preview

Implemented 6 November 2026 in the existing Next.js / FastAPI application.

## Changes

- Added **Best Route Explorer** to the existing sidebar. It uses the imported BMTC GTFS network for direct and feasible one-transfer journeys, backend sorting, eight-result pages, selected route geometry, removable map comparison, and per-leg stop timelines.
- The existing Journey Planner reuses that engine through `max_transfers=1`. Existing API clients default to direct-only behavior. The planner has compact controls, **Find buses**, explicit loading, separate date/time inputs, future-only presets, a clickable Fastest / Comfortable control, and useful unsupported-search actions.
- Dates and displayed arrival times use Asia/Kolkata. A chosen local value is converted with an explicit +05:30 offset before submission. Calendar round-trip validation rejects invalid dates; past searches explain how to use Leave now. Valid departure and preference values survive navigation through URL/session/profile state.
- Selecting another journey changes its map geometry and transfer marker. Mobile has separate Journey list / Route map views. The existing watch and crowd forecast remain available where their data applies; a multi-leg journey explicitly monitors one bus leg at a time.
- Track a Bus retains published route search, stop selection and scheduled arrivals. A separate **Preview demo tracking** tab displays one synthetic bus using an isolated instance of the existing `Simulation` and vehicle model. Pause / resume / restart operate on this preview alone.
- Demo positions are projected onto the published 500-F corridor shape (144 points in the checked feed). The shared SVG bus marker interpolates only between successive supplied simulation positions, cancels when paused/reset, and respects reduced motion. Fresh real observations snap to their supported positions; schedule-only trips never receive location markers.

## Why Jayanagara → AECS returned no journeys

The previous planner searched direct services only. In addition, similarly named stops are separate directional platforms:

| ID | Published stop / direction | Checked graph result |
| --- | --- | --- |
| 21446 | 3rd Block Jayanagara, towards South End Circle | Tested origin |
| 21447 | 3rd Block Jayanagara, towards Jayanagara 4th Block | Other origin platform |
| 20595 | AECS Layout Cross, towards Kundalahalli Gate | No supported direct or one-transfer template from either tested origin |
| 20596 | AECS Layout Cross, towards ITPL | Feasible one-transfer templates from both tested origins |

For 21446 → 20596 at 7 November 2026, 08:30 IST, the browser returned one-transfer results such as 13 → KBS-1I via St Joseph College and KIA-5 → KBS-1I via Richmond Circle, around 102 minutes in the published timetable. These are schedule estimates, not confirmed operating buses. The empty state offers the other directional platform as an explicit choice; it never silently substitutes a stop or infers a walk across the road.

Central Silk Board (`silk`, raw 20707) → Kalamandira Marathahalli Bridge (`marathahalli`, raw 22670) also returned actual published departures. In the checked search, V-500D was the shortest measured option while V-MF1C arrived sooner. Exact departures and available candidate counts change with time and bounded search coverage.

## Routing and ranking

The graph contains 7,406 ordered route patterns from the active imported dataset. A two-round stop-pattern expansion considers direct and one-transfer templates. Timetable matching uses actual service dates, ordered boarding/alighting indices, after-midnight 24+ hour GTFS times, pickup/drop-off restrictions where present, and supported cancellation/skip/disruption filters.

Transfers require the **same exact stop ID**, with a three-minute planning buffer. Imported same-stop `transfers.txt` restrictions can prohibit a transfer or increase that buffer. There are no inferred pedestrian edges or invented walking durations.

Distances follow ordered, aligned GTFS shape segments. Missing/misaligned shapes are explicitly marked stop-segment estimates; those results do not receive the shortest-measured badge. Fastest ranks total elapsed time from the requested departure, including all waiting and transfer time. Comfortable reuses the existing recommendation weights with a transfer penalty and source confidence; unknown crowding stays Unknown. The UI explains why both modes can legitimately choose the same journey.

Search limits are explicit: at most 240 templates, 1,000 evaluated trip instances, 80 retained results, two simultaneous graph searches, and a six-second evaluation budget after graph loading. Search scope is **best among bounded searched candidates**, not every possible Bengaluru journey. Overload receives an actionable retry response rather than an unbounded queue. Trip caching was expanded and schedule-only exploration avoids an unnecessary global fleet lookup.

`GET /api/journeys/explore` accepts origin, destination, sort, max_transfers (0/1), window_minutes (30–240), duration_minutes (30–360), limit (1–20), offset, optional timezone-aware depart_at, and optional search_id. A two-minute bounded snapshot supports consistent paging/sorting; expired snapshots return 409 and the frontend retries a fresh first page.

## Source boundaries and limitations

- Public GTFS is the existing unofficial Vonter BMTC dataset, under the repository's recorded ODbL attribution/licensing caveats. No new private or undocumented endpoints were accessed.
- Authorized live GPS is **not connected**. Schedule estimates cannot account for unobserved actual breakdowns, delays or diversions. Existing authorized GTFS-RT adapters and journey monitoring remain the path for such observations when access is obtained.
- Occupancy is Unknown unless evidence supports a value. GPS does not generate passenger counts. Synthetic preview positions/counts never enter the observed fleet, production simulation, real observations, or existing watches.
- Preview controls are shared by preview viewers on this local prototype server. Leaving the demo stops that component's polling; it does not change production mode.
- Walking transfers, two-or-more-transfer paths, surveyed interchange guarantees and complete citywide optimality remain unsupported. Crowding/reliability scores are heuristics, not measured guarantees.
- Future searches use schedules. Current-page journey monitoring is not a background push-notification service. Multi-leg watches require explicit progress and transfer confirmation.

## Focused validation

As requested, no final regression run of every RushLess feature was performed.

- `backend/.venv/Scripts/python.exe -m pytest tests/test_explorer.py tests/test_demo_preview.py -q`: initially 12 passed, covering distinct distance/time paths, feasible/forbidden transfers, service/direction restrictions, pagination/snapshot expiry, controlled synthetic delay, planner API compatibility, comfort ranking, after-midnight service dates, preview controls and production-source isolation.
- After adding the overload guard and related optimization, the focused routing/preview/intelligence selection passed **18 tests, 3 deselected**. Command: `backend/.venv/Scripts/python.exe -m pytest tests/test_explorer.py tests/test_demo_preview.py tests/test_intelligence.py -k 'not reports and not report and not gate and not profile and not correction and not intelligence_snapshot' -q`.
- A follow-up selected-trip check exposed the bounded preview-fleet limitation in the forecast endpoint. Scheduled trip lookup now resolves the selected trip by its real GTFS trip ID and service date, without adding a GPS position. The updated Explorer/preview test files passed **14 tests**.
- Final targeted routing / preview / route-monitor run: **25 passed**, using `backend/.venv/Scripts/python.exe -m pytest tests/test_monitoring.py tests/test_explorer.py tests/test_demo_preview.py -q`. The citywide multi-join departure query was replaced with version-keyed selected-trip lookups; real 500D stop 0 / stop 8 departure queries completed in 0.109 / 0.094 seconds locally.
- Separate existing watch selection: **1 passed, 7 deselected** with `tests/test_intelligence.py -k watch`.
- TypeScript check passed. Focused ESLint passed for changed components. The production Next.js build passed, generating 17 pages. Existing warnings: Next.js ESLint plugin detection and Starlette/AnyIO deprecation; neither caused a failure.
- IST conversion checks passed with device timezones UTC, America/Los_Angeles and Asia/Tokyo, including midnight rollover and invalid calendar dates.
- Actual API preview check confirmed movement between samples, identical paused clock/position, real GTFS shape geometry, and production mode remaining schedule.
- Browser checks covered the unsupported directional search, explicit alternate platform, real transfer results, departure persistence/submission, Comfortable state, selected map geometry, Explorer sorting/comparison, 8-to-16 result pagination, and mobile list/map switching at 390px without horizontal overflow. Demo pause held the rendered marker transform unchanged; resume and restart controls worked, and observed count stayed zero. After the query fix, selecting V-500D showed actual upcoming GTFS trips 19844–19848 in the stop-arrival table. Screenshots are stored beside this report.

## Files changed

Backend: `backend/app/explorer.py` (new), `demo_preview.py` (new), `main.py`, `feeds.py`, `network.py`, `intelligence.py`, `predictive.py`.

Frontend: `frontend/app/route-explorer/page.tsx` (new), `frontend/components/RouteExplorer.tsx` (new), `DemoTracking.tsx` (new), `DeparturePicker.tsx` (new), `departureTime.ts` (new), `JourneyPlanner.tsx`, `RouteMap.tsx`, `TransportTools.tsx`, `JourneyIntelligence.tsx`, `AppShell.tsx`, `Locale.tsx`, `types.ts`, and `frontend/app/redesign.css`.

Tests: `tests/test_explorer.py` and `tests/test_demo_preview.py` (new). Documentation: this report.

## Windows PowerShell startup

From the workspace root, after the existing dependencies are installed:

```powershell
Set-Location 'C:\Users\gagan\Documents\ChatGPT\Smart Public Transport and Bus Occupancy Prediction 2'
.\Start-RushLess.ps1
```

Open http://127.0.0.1:3000. API health is http://127.0.0.1:8001/api/health. The launcher starts hidden workspace processes and writes logs to `data/private/server-logs`.

After frontend source changes, stop only this workspace's frontend listener before rebuilding, then:

```powershell
Set-Location 'C:\Users\gagan\Documents\ChatGPT\Smart Public Transport and Bus Occupancy Prediction 2\frontend'
npm run build
Set-Location ..
.\Start-RushLess.ps1
```

After backend changes, restart only this workspace's API process before running the launcher. It intentionally reuses healthy listeners and never kills another application's port.
