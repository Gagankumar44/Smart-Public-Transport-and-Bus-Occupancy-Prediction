# RushLess

**Current app: real-data only.** Schedule mode is now the default. Demo controls, synthetic runtime feeds, practice observations and simulation scores have been removed from the running app. The validated published BMTC network is required at startup. Simulation fixtures are restricted to isolated automated tests. Earlier phase/demo instructions below are historical and no longer enable public demo operation.

Full published-network integration is available in schedule mode. See [real BMTC integration](docs/REAL_DATA.md) for actual counts, source caveats, safe updates, startup and authorized-provider requirements. No official live GPS provider is connected.

Journey monitoring now continues after boarding, updates destination ETAs, and suggests alternatives from a confirmed stop after a private breakdown/diversion report or matched provider disruption. See the [constraint audit](docs/CONSTRAINT_AUDIT.md) for behavior, 76 passing backend tests, fixture verification and live-data limitations.

The frontend now opens with a redesigned transport dashboard: Journey Planner, Track a Bus, Track a Live Route, Time Table, Facilities, Fare Calculator, Feedback and User Guide. The teal/ivory interface also includes saved journeys, insights, support, mobile navigation and partial Kannada labels. See [the frontend guide](docs/FRONTEND.md) for routes, behavior, limitations and validation. Existing prediction and pilot features remain available in the planner and insights pages.

Phase 4 now adds authorized-feed adapters, pilot collection/review, forward-only evaluation/calibration eligibility and anonymous saved commuter settings. Simulation remains the default; no genuine provider or calibrated real-world model was connected. See [the Phase 4 guide](docs/PHASE4.md) for APIs, changed files, exact startup/replay commands, verification and remaining external dependencies. A CSV merely labeled real no longer qualifies for training without a registered verified export.

**Predict the Crowd. Trust the Arrival. Choose the Better Journey.**

Working local hackathon prototype for DL-SJBIT-HK26-SSF005. Search a Bengaluru corridor, compare backend-computed journeys, choose Fastest or Comfortable, inspect the map and boarding crowd forecast, and replay traffic/demand/missing-GPS scenarios.

## Run on Windows

Prerequisites: Node.js 22+ with npm, Python 3.11+, PowerShell. Tested here with Node 26.11.1 and Python 3.11.2. Open PowerShell in this repository.

First-time setup (dependencies have already been installed in this workspace):

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend
npm ci
cd ..
```

Terminal 1, from the repository root:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Terminal 2, from the repository root:

```powershell
cd frontend
npm run dev
```

Frontend: http://127.0.0.1:3000 · API: http://127.0.0.1:8001 · Interactive API documentation: http://127.0.0.1:8001/docs

SQLite initializes automatically at `data/rushless.db`. No keys, login or manual database setup required. Stop either server with Ctrl+C.

## Demonstration

1. Choose **Central Silk Board → Kalamandira Marathahalli Bridge** (preselected).
2. Open Journey Planner (or use the dashboard's Find my journey button), then find a journey. Comfortable recommends DEMO 02; Fastest recommends DEMO 01 after a fresh Normal reset.
3. Select any card: the map highlights that pattern and the ordered stop timeline opens below.
4. Heavy traffic changes segment durations and can change the recommendation. Peak demand changes passenger flow. Missing GPS displays Scheduled estimate, Low confidence and Unknown crowding.
5. Restart resets the current scenario to 8:30 AM IST. The clock advances in real seconds, not the device's current travel time.

Other supported pairs include Agara → Bellandur and intermediate stops in either order. Reverse **demo** patterns are synthetic; they do not assert official reverse-platform service. Every card represents a distinct simulated trip. Completed/passed boarding opportunities are excluded. After all departures are exhausted, reset the demonstration.

## Structure and stack

```text
frontend/
  app/                 Next.js App Router, TypeScript, responsive Tailwind/CSS
  components/          Typed API client and client-only React Leaflet map
backend/
  app/main.py          FastAPI contracts, SQLite, routing, simulation and predictions
  app/import_gtfs.py   Local GTFS ZIP validation/import utility (Pandas)
  app/prepare_corridor.py  Reproducible corridor extraction
  requirements.txt
data/
  corridor.json        Attributed, inspectable GTFS-derived stop subset
  SOURCE.md            Upstream dataset README and notices
tests/test_api.py      Backend and prediction integration tests
docs/VALIDATION.md     Verification results and boundaries
```

The frontend uses Lucide icons, accessible Radix dialog primitives (the foundation used by shadcn/ui), CSS motion with reduced-motion support and OpenStreetMap tiles. One Python process owns simulation state; independent requests derive values from the same monotonic clock. SQLite persists stop records and scenario events. No trained ML or LLM is used.

## Data and attribution

The [unofficial BMTC GTFS dataset](https://github.com/Vonter/bmtc-gtfs) was downloaded and inspected. Its calendar covers 2026-09-07 through 2027-09-07. `data/corridor.json` contains the first 15 ordered stops of a 500-F outbound trip (upstream trip 2509), ending at Kalamandira Marathahalli Bridge. Original stop IDs and coordinates are retained; two application aliases support the demonstration. The database subset is offered under **ODbL-1.0**, as stated by the source. Some individual contents may be copyright BMTC; see `data/SOURCE.md` and the upstream notices. Upstream warns of incorrect schedules and incomplete route coverage. This prototype does not assert these services are currently operating.

**All DEMO route patterns, departure times, vehicles, traffic, passenger counts and predictions are synthetic.** Outbound stop order and geography come from the feed; reverse patterns are synthetic reversals. The five demo patterns are not five verified official BMTC routes. Geometry connects consecutive stop coordinates and does not follow road shapes. Leaflet displays © OpenStreetMap contributors attribution; no tile prefetch or bulk download is performed. Tiles require internet; search/routing/predictions work offline once servers are running. If tiles fail, the selected route still draws and the journey timeline provides directions.

Re-download and extract the corridor:

```powershell
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Vonter/bmtc-gtfs/main/gtfs/bmtc.zip' -OutFile data/bmtc.zip
backend/.venv/Scripts/python.exe backend/app/prepare_corridor.py
```

Restart the backend after extraction. A small synthetic geography fallback is included if `corridor.json` is absent. It is for offline resilience, not authentic BMTC observations.

Import an arbitrary GTFS ZIP into a **separate staging database**:

```powershell
backend/.venv/Scripts/python.exe backend/app/import_gtfs.py data/bmtc.zip --output data/gtfs.db
```

This validates required tables, Bengaluru coordinate bounds and time values (including hours beyond 24), preserving service calendars, exceptions, trips/directions and optional shapes. Importing does **not** automatically activate arbitrary feeds for routing: corridor extraction is a separate explicit step. The MVP routes on the bundled corridor and synthetic departure plan, not official timetable/calendar service. Production calendar filtering, frequency feeds, arbitrary-network transfer routing and shape matching remain future work.

## Prediction methods

**ETA:** departure offset + target stop index × scenario segment duration − elapsed simulation time. A base segment is 180 seconds, including assumed 15-second dwell. Traffic increases segment duration. Vehicle progress derives from exactly the same timings. Midnight-safe ISO 8601 timestamps use Asia/Kolkata. Schedule fallback uses the deterministic demo timetable; it is never called live BMTC data.

**Crowding:** begin with the vehicle's simulated observed load, project alighting then boarding through each upcoming stop, and clamp load to 0–60 passengers. The forecast includes boarding at the target stop. Low is below 40%, Moderate is 40–75%, High is above 75%. These are configurable project assumptions in `crowd()`, not BMTC standards. Missing observations produce Unknown, never seat guarantees. Capacity blocks excess boarding; unmet queue demand is not persisted in this MVP.

**Ranking:** first enforce correct stop ordering and future boarding. Keep the earliest eligible trip for each pattern, normalize duration against a fixed 60-minute scale, then minimize weighted duration plus crowd penalty. Fastest uses .95 duration/.02 crowd; Comfortable uses .40 duration/.50 crowd. Unknown crowding receives .8 penalty and Low confidence a .1 penalty. All routes are direct, with no invented walking distance. Weights are design assumptions. Explanations are templates based on the selected mode and available evidence.

**Trust:** Medium is a recent synthetic observation; missing GPS uses a 10-minute-old observation, Low confidence, schedule fallback and Unknown crowding. Qualitative labels describe evidence within the scenario, not measured real-world accuracy. There is no historical passenger dataset, authorized live feed or calibrated model evaluation.

## API

All paths begin `/api`. See `/docs` for interactive parameter contracts and response schemas.

| Method | Path | Purpose |
|---|---|---|
| GET | /health | API/database status |
| GET | /stops/search?q=bell | Local autocomplete |
| GET | /stops/nearby?lat=12.93&lon=77.65 | Nearest supported stops |
| GET | /routes, /routes/{id} | Patterns, stops, geometry |
| GET | /vehicles, /vehicles/{id} | Shared simulation state |
| GET | /stops/{id}/arrivals | Eligible arrivals |
| GET | /vehicles/{id}/occupancy?stop_id=silk | Boarding crowd forecast |
| GET | /journeys?origin=silk&destination=marathahalli&preference=comfortable | Ranked options |
| GET | /system/status | Source, clock, scenario |
| POST | /demo/scenario | JSON scenario: normal, traffic, peak, missing |

## Configuration and deployment boundaries

`.env.example` documents configuration. Set `API_PROXY_URL` in `frontend/.env.local` when changing API host; the default frontend client uses relative `/api` paths through Next.js rewrites. Optional `NEXT_PUBLIC_API_BASE_URL` overrides direct client requests. Use only known frontend origins in backend `FRONTEND_ORIGINS`. Backend variables must be set in PowerShell (`$env:ENABLE_DEMO_CONTROLS='false'`) before starting Python; the backend does not automatically load `.env` files.

Set `ENABLE_DEMO_CONTROLS=false` before any public deployment. Servers bind loopback locally. Use one Uvicorn worker: simulation state is intentionally process-local and shared between visitors. No public deployment was performed. A production rollout needs durable shared simulation/live adapters, permissions for actual data, request rate limits, server-side error logging, multi-user isolation and observation history.

## Checks

From the repository root:

```powershell
backend/.venv/Scripts/python.exe -m pytest tests -q
cd frontend
npm run typecheck
npm run build
```

Tests cover preferences, stop/direction validation, time progression, passed buses, traffic, missing data, capacity, thresholds, after-midnight parsing, API consistency and disabled mutation controls. Synthetic tests validate implementation behavior, not real-world predictive accuracy. See `docs/VALIDATION.md` for observed browser checks and remaining verification limits.

Future live integration should add an authorized observation adapter, service-date and direction-aware trip matching, stale-feed handling, genuine count history and evaluation against held-out trips before claiming accuracy.


## Phase 2 — interactive intelligence

New files: `backend/app/intelligence.py`, `frontend/components/JourneyIntelligence.tsx`, `frontend/app/insights/page.tsx`, `frontend/eslint.config.mjs`, `tests/test_intelligence.py`. Existing routing, metadata, scenario controls, journey selection and CSS have been extended in place.

### Try it

1. Reset **Normal**, search Central Silk Board → Kalamandira Marathahalli Bridge, then open the DEMO 02 card.
2. Select **Watch Journey**. The status strip stays visible when details close. Monitoring works only while the page is open; there are no background/push notifications.
3. Select **Report crowding**, then High. A confirmation appears; prediction evidence shows a recent demo report. One report may change utilization without crossing a category boundary.
4. Select **Heavy traffic**. DEMO 02's start moves six minutes later and segment time increases. Within the five-second refresh, the watch emits a delay alert and proposes a materially better eligible departure. Choose **Switch to this journey** or **Keep current journey**. No automatic replacement of the selected trip occurs.
5. **Peak demand** changes passenger-flow forecasts; **Missing GPS** makes forecasts Unknown and reduces confidence. **Close arrivals** moves the second DEMO 01 departure to seven minutes after the scenario epoch, two minutes behind the first, versus 25 minutes in the base timetable. The later bus has a lower synthetic initial load. Choose a DEMO 01 card for its headway notice.
6. Open **Corridor insights** at `/insights`. It refreshes every ten seconds with current vehicle counts, load comparisons, delay, endpoint headway warnings and fresh reports. Mobile users can navigate directly to `/insights`.

Scenario changes preserve the simulation clock, reports and watch snapshots so changes can be detected. **Normal** and the explicit restart control create a fresh generation, reset time to 8:30 AM, ignore old reports and reconcile watch baselines. All reports are labeled `demo_passenger_report`, not real observations.

### Reporting rules

SQLite stores report ID, generation, vehicle, trip, route, last/current stop, category, simulation timestamp, hashed anonymous cookie identifier and evidence type. The API validates matching vehicle/trip/route and rejects reporting a future stop as already observed. Reports from different vehicles never mix. Reports at earlier stops are projected forward with the same passenger-flow function before blending.

Freshness defaults to 900 seconds. Age linearly reduces weight. Influence starts at up to 25% for one fresh reporter and is capped at 45% for multiple reporters. Conflicting categories halve influence and lower confidence. The original model utilization, report count, conflict state and evidence label remain inspectable in metadata. Expired reports remain in SQLite but are excluded from forecasts and the recent summary. Cookie-based limits permit one report per 30 seconds; network limits permit 15 per minute. Exact same-trip/category duplicates within a minute are rejected after the initial cooldown. These are basic anonymous demo controls, not production anti-abuse or identity verification. Hashed network identifiers are held only in memory for rate limiting.

### Alerts and recommendations

Watches use random capability IDs and expire after 30 minutes of inactivity; state is in memory, capped at 200 watches. Selection context is independent of the currently ranked top three. The existing ranking engine supplies both watch comparisons and normal search. Alternatives require a score improvement of at least .08 plus at least three minutes saved or one lower crowd category in Comfortable mode. Keep-current suppresses that particular alternative until restart; switching explicitly updates the map and selected trip.

Approaching alerts cross five/two-minute thresholds once per generation. Delay alerts compare absolute predicted boarding timestamps, not countdowns, and require a three-minute increase. Crowd and freshness changes are recorded. Repeated delay/crowd/freshness alerts have a 30-second cooldown; only the last 12 alerts are retained. The better-option panel is the notification for improved alternatives. The page polls watches every five seconds and cleans up its timers and watch on unmount; server expiration handles abrupt closures.

Close-arrival detection groups trip ETAs strictly by demo route and direction at a stop. Gaps at or below three minutes receive **Close arrivals**, or **Potential bunching** only when the scheduled headway is at least six minutes and the predicted gap is less than half of it. Scheduled close spacing or absent schedule evidence never proves bunching. The scenario is explicitly synthetic.

### New endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /api/crowd-reports | Submit validated demo evidence; browser cookie deduplication |
| GET | /api/crowd-reports/summary | Fresh generation-scoped reports, excluding private client hash |
| POST | /api/watches | Watch a boardable trip with origin/destination/preference |
| GET | /api/watches/{id}?preference=comfortable | Current trip, alerts and material alternative |
| POST | /api/watches/{id}/decision | JSON action `accept` or `keep` |
| DELETE | /api/watches/{id} | Stop watching |
| GET | /api/stops/{id}/close-arrivals | Trip-level headway evidence |
| GET | /api/insights/summary | Shared-state corridor analytics |

Additional backend environment variables: `REPORT_FRESHNESS_SECONDS=900`, `CLOSE_ARRIVAL_MINUTES=3`, `APPROACH_THRESHOLDS=5,2`. Set valid positive values before starting the backend. Demo scenario requests additionally accept `restart: true`.

### Restart / validate

Stop the existing terminals with Ctrl+C. In the repository root:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run build
npm run start
```

For editing, use `npm run dev` instead of production build/start. Do not run a build against an active development server's `.next` directory.

```powershell
# From repository root
backend/.venv/Scripts/python.exe -m pytest tests -q
cd frontend
npm run typecheck
npm run lint
npm run build
```

Remaining boundaries: one process owns all demo state; scenario controls affect all visitors. Watch capability IDs and anonymous cookies are for a local demonstration. No push delivery, real passenger labels, actual BMTC feed, full-network routing or validated real-world accuracy. Operator load charts show model vehicle loads, distinct from passenger-report-adjusted boarding forecasts. Before a real pilot, add authorized feeds, shared watch storage, stronger abuse controls and evaluation against independent observations.


## Phase 3 — prediction and evaluation

The simulation remains the active serving source. No genuine historical GPS/count dataset was supplied, and no real-world model was trained or activated. Historical ingestion and an optional offline ridge-regression candidate training workflow now exist. A unit test exercises candidate training with mock observed labels in an isolated temporary database; it is not evidence of genuine data or a production model.

### Prediction behavior

- The shared ETA function selects fresh simulation progress, genuine vehicle progress/history-adjusted progress where an authorized adapter is supplied, historical remaining-time estimates when appropriate, or a scheduled baseline. The running demo always uses simulated observations. The history/ML pipeline does not silently alter demo predictions.
- Progress ETA explicitly combines departure wait, fractional current segment and remaining segment time. The base 180-second segment contains assumed 165-second travel and 15-second dwell. No road speed is inferred from straight-line distance. Geometry still connects GTFS stops.
- Missing GPS uses the unmodified demo scheduled baseline, not a traffic-adjusted estimate carrying a schedule label. Already-passed boarding opportunities are excluded. `backend/app/schedule.py` separately looks up genuine staged GTFS trip/stop schedules with service calendars, additions/removals, after-midnight times and Asia/Kolkata. The demo timetable is not presented as an official GTFS schedule.
- ETA responses include `uncertainty` with observation age, stop horizon and lower/upper minutes. Bounds are heuristic: at least 60 seconds or 12% of remaining time, plus eight seconds per stop and an age allowance; traffic multiplies the spread by 1.5 and conflicting reports by 1.3. They are not calibrated coverage intervals.
- Occupancy uses the same bounded flow model and recent trip-specific reports at every future stop. More than seven stops ahead, stale observations or conflicts increase uncertainty. Missing counts remain Unknown. Revised reports by the same anonymous reporter are one source, not independent votes.
- Four configurable synthetic demand profiles scale boarding demand: morning 1.0, afternoon .7, evening 1.2 and low .4. Select them in demo controls. They are design assumptions, not measured Bengaluru demand.
- In journey details, **Crowding along your journey** shows the first six future stops with a show-all control, forecast categories, expected arrival and uncertainty. Cards display a small heuristic ETA range while retaining the main countdown.
- **Fresh demo observation** advances that vehicle's shared trajectory by 60 simulated seconds, recording a simulation observation. Map progress, ETA, crowding, ranking and watch alerts then use that state. Controls respect `ENABLE_DEMO_CONTROLS`. Profile changes preserve the clock/watch context; explicit restart creates a new generation and reconciles forecasts.

### Historical CSV ingestion (local CLI only)

Raw CSV bytes and dataset provenance are preserved in the private `data/observations.db`, separate from cleaned observation records, derived feature vectors, prediction outputs and evaluation results. Rejected files retain validation errors and raw bytes; partially cleaned rows are not admitted. There are no public raw-trace, import or training endpoints.

Required CSV fields:

```text
vehicle_id,trip_id,route_id,stop_id,direction,service_date,segment_index,stops_remaining,observed_at,actual_arrival_at,scheduled_arrival_at
```

Optional fields:

```text
progress_arrival_at,recent_segment_seconds,passenger_count,capacity,predicted_utilization,latitude,longitude,source_type
```

Use ISO 8601 timestamps with explicit offsets, e.g. `2026-11-05T08:30:00+05:30`. `service_date` is `YYYY-MM-DD` and groups trips across midnight. Segment index is zero-based; target stop index minus segment index must equal `stops_remaining`. Direction must match the configured route. Existing route/stop registry IDs are required; map any newly collected official IDs explicitly before importing and preserve original identifiers in extra CSV columns. Arbitrary imported GTFS networks do not automatically become serving networks.

The importer checks required fields, identifiers, direction, index/order, timezone offsets, duplicate records, timestamp horizons, chronological progress, consistent actual arrival labels, GPS bounds and passenger-count capacity constraints. It records collection date, source, license, routes and missing-value counts. Source type is either `real_observed` or `simulation`, declared by the importer and checked against row-level source types when present; this declaration does not independently verify authenticity. No missing actual labels/counts are replaced with synthetic measurements. For the optional ML feature vector, a missing recent segment duration uses a zero sentinel plus an explicit missing indicator; raw measurements remain missing.

Example from repository root, replacing the example file and provenance with your own authorized data:

```powershell
Push-Location backend
$rushlessDatasetId = .venv/Scripts/python.exe -m app.history import ../data/my_observations.csv --source 'Authorized pilot dataset' --license 'Your dataset license' --collected-on 2026-11-05 --mode real_observed
.venv/Scripts/python.exe -m app.history evaluate $rushlessDatasetId
Pop-Location
```

### Reproducible simulation-only evaluation

```powershell
Push-Location backend
.venv/Scripts/python.exe -m app.history demo
Pop-Location
```

This writes `data/evaluation_demo.csv`, imports it with explicit synthetic provenance and stores a report. The deterministic fixture supplies known outcomes and recorded forecast examples to exercise evaluation plumbing; its scores do not estimate the real-world accuracy of the live demo engine.

The current fixture has 72 observations across 12 dated trips. Chronological train/calibration/test partitions contain 42/12/18 observations across 7/2/3 trips. Overlapping labels are purged at partition boundaries. Test labels never fit baselines, models or interval widths.

On this synthetic fixture, computed ETA MAE is **2.667 min scheduled**, **1.667 min recorded progress forecast**, and **2.233 min historical baseline**, on 18 held-out labels. Median/P90 errors, per-route results and sample counts are also stored. Occupancy fixture classification accuracy and macro F1 are 1.0 on 18 constructed labels versus majority-baseline accuracy .333. These perfect synthetic category matches are engineering checks, not field accuracy.

Empirical interval radii use at least ten calibration residuals; interval coverage is measured on held-out test records. The fixture reports schedule/progress/historical coverage .667/1.0/.278, with mean widths 6.0/4.0/3.4 minutes. Such a small, constructed sample does not establish statistical calibration. Live commuter ETA bounds remain separately labeled heuristic and never use these synthetic residuals as real-world uncertainty.

### Optional model candidate workflow

```powershell
Push-Location backend
.venv/Scripts/python.exe -m app.history evaluate $rushlessDatasetId --train --artifact ../data/models/eta-candidate.json
Pop-Location
```

Training rejects simulation datasets and requires at least 60 observed training labels across six distinct training trips after splitting/purging. A simple ridge regression uses scheduled remaining minutes, remaining stops, hour, weekday, recent segment duration and its missing indicator. The artifact records feature schema, version, source provenance, training time, coefficients and held-out comparisons. Coefficients and schema are validated. A candidate is marked eligible only if its held-out MAE beats schedule; **serving remains disabled**. A future authorized real-data adapter and deployment/validation step are required before activation. The current simulation remains independent of artifacts.

### Prediction APIs

| Method | Path | Purpose |
|---|---|---|
| GET | /api/vehicles/{id}/forecast | Upcoming stop forecasts using the existing prediction function |
| GET | /api/predictions/methods | Method selection, demand assumptions and disabled ML status |
| GET | /api/data/quality | Aggregate dataset provenance and missing-data statistics; no traces |
| GET | /api/insights/prediction-quality | Real evaluations and simulation evaluations in separate fields |
| POST | /api/demo/observation | Controlled, simulation-only fresh observation |

Existing arrivals, journeys and occupancy endpoints retain their fields and gain method/uncertainty metadata. `/insights` adds **Prediction Quality**, displaying **No real-world evaluation dataset connected yet** alongside separately labeled synthetic results.

### Start and check

From repository root, terminal 1:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Terminal 2:

```powershell
cd frontend
npm run build
npm run start
```

Stop existing servers with Ctrl+C first. Use `npm run dev` for editing, and stop it before a production build. Frontend remains http://127.0.0.1:3000; API documentation remains http://127.0.0.1:8001/docs.

```powershell
backend/.venv/Scripts/python.exe -m pytest tests -q
cd frontend
npm run lint
npm run typecheck
npm run build
```

See `docs/PHASE3.md` for the inspected baseline, changed files, observed results and limitations. Phase 4 should focus on an authorized observation adapter, real field labels, out-of-sample validation/calibration and durable per-user state before expanding model complexity.

Latest planner and tracking update: the sidebar now includes **Best Route Explorer** with real GTFS direct/one-transfer searches, distance/time sorting, route comparison and timelines. Journey Planner has IST departure controls and **Find buses**. Track a Bus offers an explicitly labeled simulation preview alongside published schedules; official live GPS remains unconnected. See [implementation, focused checks and Windows startup](docs/PLANNER_EXPLORER_TRACKING.md). From the workspace root, `.\Start-RushLess.ps1` starts the built app.
