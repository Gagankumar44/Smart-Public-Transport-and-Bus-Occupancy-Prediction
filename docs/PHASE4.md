# Phase 4 — data adapters, verified evidence and commuter persistence

## Current outcome

The app was enhanced in place. Simulation remains the default, including Central Silk Board → Kalamandira Marathahalli Bridge. **No genuine external provider was connected, no genuine verified field dataset was collected, and no real-data calibration or trained model was activated.**

A local protobuf fixture was generated and ingested: two accepted synthetic observations and zero rejects. A static corridor registry was staged from the existing unofficial BMTC archive: one route, 114 scheduled trips and 73 upstream stops. Neither operation establishes a live BMTC connection or timetable reliability.

Before implementation, all 33 existing tests, frontend lint, TypeScript and production build passed. The implementation sequence covered adapter/storage contracts, normalization, collection/review, evaluation/calibration, anonymous profiles, frontend integration and regression checks.

## Adapter architecture

`feeds.py` uses `gtfs-realtime-bindings` to parse VehiclePosition and TripUpdate protobuf messages. ServiceAlerts are informational; they do not invent routing disruptions. Differential feeds are rejected until a provider-specific state adapter exists. The [official GTFS Realtime reference](https://gtfs.org/documentation/realtime/reference/) guided the contracts.

`RUSHLESS_DATA_MODE` supports `simulation`, `replay`, `authorized` and `schedule`. Existing snapshot/prediction functions select the adapter, so maps, journeys, ranking and watches consume the same state. Demo passenger-flow calculations are never applied to external vehicles. Provider current occupancy is kept separate from future crowding, which remains Unknown without valid forward evidence.

Normalized records preserve source/mode, vehicle/trip/route descriptors, service date, direction, position, observation/feed/ingestion timestamps, stop progression, trip updates and quality flags. Unknown trips remain unmatched. Invalid geography, off-corridor positions, route/direction/service mismatches, future timestamps, jumps, backwards progression and duplicate/out-of-order updates cannot replace accepted state. Stale observations use schedule fallback. Cancellations exclude boarding candidates. Missing vehicle identities never become invented observed vehicles.

Trip matching uses exact staged GTFS trip/service instances, calendars, exceptions and after-midnight times. Static trip information is cached. The spatial check uses supported stop-segment geometry with a conservative distance threshold; it is not a full road-shape/detour matcher. Serving remains limited to the supported corridor. Full-network, frequency and provider-specific detour handling remain future work.

### Provider security

There is no public URL-fetch, provider-configuration, import or verification endpoint. Fetching requires backend configuration explicitly confirming provider permission, an HTTPS URL, an approved hostname and public DNS addresses. Redirects are disabled. Responses are limited to five megabytes and a 15-second timeout. Persisted fetch attempts enforce polling intervals, including failed attempts. Credentials remain in backend environment variables; errors/health never expose tokens or configured URLs.

No private BMTC endpoint was scraped or reverse engineered. A real endpoint, permission/license and any required token must come from the authority or a licensed provider. Connectivity is only recently verified after accepted non-synthetic authorized observations and freshness checks. Replay and local fixtures are never live sources.

## Reproduce local replay

From repository root:

```powershell
Push-Location backend
.venv/Scripts/python.exe -m app.feeds fixture
$env:GTFS_DB_PATH = (Resolve-Path ../data/feed-fixtures/fixture-gtfs.db).Path
.venv/Scripts/python.exe -m app.feeds ingest ../data/feed-fixtures/synthetic-replay.pb --source-id local-engineering-fixture --provenance 'RushLess local synthetic engineering fixture' --license 'CC0 synthetic fixture' --synthetic
Pop-Location
```

To serve it, stop the backend with Ctrl+C, then set these in the backend terminal:

```powershell
$env:RUSHLESS_DATA_MODE = 'replay'
$env:RUSHLESS_SOURCE_ID = 'local-engineering-fixture'
$env:GTFS_DB_PATH = (Resolve-Path data/feed-fixtures/fixture-gtfs.db).Path
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Use **Agara Junction → Kalamandira Marathahalli Bridge**: the sample vehicle has passed the origin. Replay uses archived timestamps. Ingesting another archived frame advances it; motion is not invented between frames. The fixture and its registry are synthetic and cannot be relabeled as genuine sources.

For the usual demo, stop the backend and set `RUSHLESS_DATA_MODE=simulation` before restarting. Optional replay-specific source/registry environment settings can be cleared from that terminal. Keep the presentation app in simulation mode unless deliberately demonstrating replay.

### Static registry and future provider setup

The existing archive was inspected and this command was run successfully:

```powershell
backend/.venv/Scripts/python.exe backend/app/stage_registry.py data/bmtc.zip --output data/gtfs.db --route 500-F
```

It refuses to overwrite an existing database. Use another output path when restaging and set `GTFS_DB_PATH` explicitly. Attribution and caveats remain in `data/SOURCE.md`. The registry is unofficial schedule information, not live access. It enables scoped pilot collection without external credentials.

For a future licensed source, configure `TRANSIT_FEED_URL`, `TRANSIT_FEED_ALLOWED_HOSTS`, `TRANSIT_FEED_PROVENANCE`, `TRANSIT_FEED_LICENSE`, `RUSHLESS_SOURCE_ID`, `GTFS_DB_PATH` and any `TRANSIT_FEED_TOKEN` in the backend environment. Set `TRANSIT_FEED_AUTHORIZED=true` only after actual permission is obtained. Never place provider secrets in NEXT_PUBLIC variables or tracked files. Select `RUSHLESS_DATA_MODE=authorized` and disable demo mutations for public deployment.

From `backend/`, run `.venv/Scripts/python.exe -m app.feeds fetch`. Fetching is an explicit CLI action, not a background subscription. Repeat no faster than provider terms and `TRANSIT_POLL_SECONDS` (default 60, minimum 15). Missing/stale input falls back to actual matched GTFS schedules, without position markers or invented occupancy. A production rollout needs a managed ingestion worker and provider-specific matching.

## Observation collection and review

**Record a pilot observation** collects route/direction, stop, actual event time, service date, optional exact trip ID and arrival/category. It requests no passenger identity, phone, photo, number plate or continuous device location. The form advises recording after safely boarding/stopping. Demo routes create practice records only.

Registered GTFS routes support manual pilot records. Missing/unmatched trip information stays unresolved. Exact matching produces `matched`, never automatic independent verification. Implausible trip/time associations and conflicts require review. General Phase 2 reports retain their separate expiry/blending behavior. Subjective categories never become exact passenger counts. Authorized exact counts/capacity can be locally imported for review.

Manual submissions are limited to 20 per network address/hour using an ephemeral hashed rate-limit key. Cross-site mutation requests are rejected. Import, review, evaluation and activation are local CLI operations.

From `backend/`:

```powershell
.venv/Scripts/python.exe -m app.ground_truth list
.venv/Scripts/python.exe -m app.ground_truth review OBSERVATION_ID --status verified --evidence 'Independent evidence reference' --reviewer-role 'Pilot reviewer' --transport-source YOUR_PROVIDER_SOURCE_ID
```

The uppercase IDs/evidence are placeholders, not genuine reviews performed in this session. Verification rejects simulation and unresolved trip matches. A review audit is retained. Software cannot independently prove a human statement; use independently supported evidence. `--status rejected` excludes a record. A later reviewed label can supersede an earlier one with an audit entry.

Authorized actual-arrival/count CSVs can enter review using:

```powershell
.venv/Scripts/python.exe -m app.ground_truth import-labels ../data/private/actual-labels.csv --license 'Your authorized dataset license'
```

CSV fields: `kind` (arrival/occupancy), `route_id`, `stop_id`, `direction`, `service_date` (YYYYMMDD), `trip_id`, optional `vehicle_id`, timezone-aware `event_at`, `method` (authorized_arrival_record/authorized_passenger_count), `transport_source_id`, optional category, count/capacity and note. Omit unknown optional values. Imported records are not automatically verified. GTFS Realtime predicted stop times are never converted into observed arrivals.

## Forward-only evaluation and calibration

The external predictor appends genuine authorized forecasts with creation time, source, exact trip/service date/stop, predicted arrival, method/model version and crowd category. Schedule baselines are recorded at the same time, not reconstructed after the outcome. Logging is limited to one sample/event/method/minute.

Only reviewed genuine labels with matching service instances and forecasts created 2–30 minutes before the event enter evaluation. Later/retrospective forecasts, mismatched vehicles/sources, simulation and unverified labels are excluded. Methods are compared pairwise against schedule on the same eligible events. Coverage and sample counts remain visible; differing populations cannot support a headline improvement claim.

```powershell
Push-Location backend
.venv/Scripts/python.exe -m app.ground_truth evaluate
Pop-Location
```

Reports contain MAE, median/P90 error, route/source/local-hour coverage, sample counts, categorical precision/recall/F1/confusion matrix when eligible, and chronological trip/service partitions. Exact count evaluation stays separate and unavailable without a count forecast. Small samples are diagnostic/insufficient.

Calibration uses a finite-sample residual rank from held-out calibration data at target coverage .9. Test labels never set the radius. Eligibility requires at least 30 unique events per partition, sufficient chronological trips, adequate held-out coverage, one source/route/method scope and compatible model version. Candidates are saved, not automatically activated. The 30-sample floor cannot be lowered through configuration. Candidates expire after 30 days; heuristic bounds remain the fallback.

From `backend/`, `.venv/Scripts/python.exe -m app.ground_truth activate-calibration CALIBRATION_ID` explicitly activates an eligible candidate. Only matching real-observed predictions can use it. Simulation/replay never inherit real calibration. The API/UI distinguish empirical calibrated and heuristic ranges. No genuine candidate was activated here.

### Verified training exports

A CSV merely marked real_observed is insufficient for model training. Export reviewed arrivals paired with pre-existing feature-bearing forecasts:

```powershell
Push-Location backend
.venv/Scripts/python.exe -m app.ground_truth export-history ../data/private/verified-history.csv
Pop-Location
```

The exact file hash is privately registered. Phase 3 ingestion retains verification provenance; editing the bytes loses eligibility. The training path still needs sufficient genuine training labels, trip-separated evaluation and explicit later deployment validation. Without eligible labels, export creates no file and explains why. Imported, unverified historical diagnostics remain separate from verified real-world performance.

## Anonymous commuter state

The server stores up to 12 named saved journeys, five recent stop pairs, travel mode, alert preference and last stop-pair context. A random 256-bit first-party cookie is HttpOnly, SameSite=Strict and Secure on HTTPS (or `COOKIE_SECURE=true`). Unknown/expired cookie identities rotate. APIs reveal no token hashes and enforce profile ownership. No account, email, phone or fingerprint is required.

Saved journeys are accessible below the search form. Save, rename/remove pairs, restore preferences after reload, clear recent searches, or reset the anonymous data/identity. Retention defaults to 30 inactive days (`PROFILE_RETENTION_DAYS`). Mutations are serialized locally to avoid lost updates. Use the default `/api` proxy for first-party cookies.

Only a useful stop pair and preference are restored. An expired vehicle is never revived automatically; a fresh search revalidates departures. Watches remain open-page, in-memory monitoring. Persisted alert settings do not imply background push delivery.

This is a local pilot, not approved production data collection. Manual notes can still contain personal information despite the form guidance. Raw provider frames, pilot review evidence and evaluation records are retained locally without an automatic retention job; restrict access and define purpose-specific deletion periods before an external pilot. Before production processing involving people in India, obtain an appropriate privacy/legal and security review covering applicable Indian data-protection obligations, notices, permitted processing grounds, retention, deletion requests, incident handling and provider licensing. No claim of legal compliance is made by this prototype.

## Database, APIs and files

Additive `data/pilot.db` tables hold sources, raw feeds, normalized observations, polling attempts, raw/normalized pilot observations and reviews, forward snapshots, evaluations, calibration candidates, verified-export hashes and anonymous profiles. Earlier tables/history were not wiped. No public raw-trace or profile-identity listing endpoint exists.

New APIs:

- GET `/api/data-sources/status`, `/api/data-health`
- GET `/api/observations/catalog`, `/api/observations/coverage`
- POST `/api/observations/arrivals`, `/api/observations/occupancy`
- GET `/api/predictions/evaluation`, `/api/predictions/calibration-status`
- GET/PATCH/DELETE profile settings and POST/PATCH/DELETE saved journeys under `/api/profile`
- POST/DELETE `/api/profile/recent`

Shared vehicle/journey/forecast endpoints select the adapter. `/insights` adds Data Health and keeps synthetic and verified quality separate.

Created backend modules: `pilot_store.py`, `feeds.py`, `profiles.py`, `ground_truth.py`, `stage_registry.py`. Created UI components: `CommuterPanel.tsx`, `PilotObservation.tsx`, `DataHealth.tsx`. Added `tests/test_phase4.py` and the synthetic protobuf fixture. Modified shared backend/prediction/history services, existing pages/map/forecast/quality components, CSS/types, requirements, environment example and training-gate tests. Runtime databases are Git-ignored.

## Windows startup and checks

Stop only this workspace's servers with Ctrl+C before restarting them. Port 8000 was occupied by a separate RushLess backend and was left untouched; this workspace's proxy and API use 8001. From repository root, terminal 1:

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
$env:RUSHLESS_DATA_MODE = 'simulation'
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Terminal 2:

```powershell
cd frontend
npm ci
npm run build
npm run start
```

App: http://127.0.0.1:3000 · API docs: http://127.0.0.1:8001/docs · Insights: http://127.0.0.1:3000/insights . Use npm run dev for editing and stop it before a production build.

From repository root, run backend/.venv/Scripts/python.exe -m pytest tests -q. From frontend/, run npm run lint, npm run typecheck and npm run build.

## Validation and demonstration

Final validation on 5 November 2026:

- Backend: **53 tests passed**, including the original regression suite, protobuf normalization/replay, authorized-fetch mocks, forward-only evidence, calibration gates, profile ownership/retention and cross-site mutation checks. One upstream Starlette/AnyIO deprecation warning remains.
- Frontend: ESLint, TypeScript and optimized production build passed. Next.js reports an advisory that its optional ESLint plugin is absent; the configured ESLint check passes.
- Actual local fixture ingestion accepted two synthetic observations. Static registry staging produced one route, 114 trips and 73 stops. Authorized HTTP integration was tested with mocks, not a genuine provider connection.
- Browser: default-corridor search and selection, named save/rename/remove, reload persistence, recent-search clearing, preference/alert restoration, and practice-observation submission worked. A 390 by 844 viewport showed no horizontal overflow and a usable scrollable pilot form. Data Health showed simulation, zero verified labels, calibration unavailable and the synthetic source separately.
- API/proxy checks confirmed simulation mode, no live connection and zero verified labels. Profile deletion/identity reset and calibration activation safeguards were covered by isolated backend tests.

For a reproducible presentation:

1. Open the planner in simulation mode. Search Central Silk Board to Kalamandira Marathahalli Bridge and inspect the recommended bus, forecast and heuristic uncertainty range.
2. Save the pair below the search form. Open Saved journeys, rename it, change travel preference or alerts, reload, and reopen Saved journeys to see persistence. A browser QA example named **Hackathon demo** was retained in the tested anonymous profile; other browsers have separate profiles.
3. Open Record a pilot observation. Select a **Demo practice** route for a demonstration, submit an explicitly synthetic note, and observe the unverified practice confirmation. Do not submit invented events against a real GTFS route.
4. Open Insights and inspect Data Health: no live BMTC connection, zero verified labels, heuristic fallback and the separately tagged local fixture. Prediction Quality keeps simulation engineering checks separate from real-world evidence.
5. To demonstrate protobuf replay, follow the replay commands above, then restore simulation for the normal presentation. Real collection/import/review/evaluation requires actual authorized events and independent review evidence.

The browser QA practice record remains synthetic and unresolved. No genuine field verification, empirical calibration activation or model deployment occurred. Screenshot: [Phase 4 Data Health](phase4-health.png).

## Next phase

Obtain real provider permission/credentials, operate ingestion, collect independently verified pilot arrivals/counts, measure prospective coverage and review deployment eligibility. Public scale also needs pinned-host egress, fuller shape/frequency/detour handling, durable per-user watches, retention jobs, stronger abuse controls and shared multi-process state. None is represented as already connected or production-validated.
