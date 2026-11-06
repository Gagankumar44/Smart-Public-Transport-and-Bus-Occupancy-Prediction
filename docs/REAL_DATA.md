# Published BMTC integration

Source: https://github.com/Vonter/bmtc-gtfs . Imported the existing published archive, not scraping scripts or private endpoints. Feed version 20260907; advertised calendar 20260907–20270907. SHA256: b5fe4a8e05495f719e4c8f16452dc6c4820f342b5414c3fb51e19687b5ea3333.

Actual import: 4,434 route records, 9,799 stops, 57,445 valid trips, 7,406 directional stop/shape patterns and 1,537,259 stop-time records. Excluded 161 invalid stops and 391 invalid trips; quarantined 67 whole shapes. Missing shapes use labelled stop-segment fallback. Route records can exist without eligible trips. These are dataset counts, not a live fleet census.

ODbL-1.0 attribution/share-alike applies; underlying BMTC content copyright remains. Preserve the original archive, license and attribution when distributing adapted databases. See data/SOURCE.md. The source warns of missing routes and incorrect timetables. No official endorsement, complete coverage or timetable accuracy is claimed.

## Safe update and startup

From repository root, import a newly approved published ZIP:

```powershell
backend/.venv/Scripts/python.exe -m backend.app.network data/bmtc.zip --activate
```

Imports create immutable content-addressed SQLite versions and JSON validation reports in data/network-versions. Duplicate versions refuse overwrite. Invalid versions leave the active pointer unchanged. Only successful validation atomically updates data/network-active.json; previous databases remain. Restart the backend to load a newly activated stop catalog. Existing demo/pilot databases are preserved.

Backend terminal, from root:

```powershell
$env:RUSHLESS_DATA_MODE='schedule'
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Frontend terminal:

```powershell
cd frontend
npm run build
npm run start
```

Open http://127.0.0.1:3000 . Verified pair: Central Silk Board (20707; compatible alias silk) to Kalamandira Marathahalli Bridge (22670; alias marathahalli). Three schedule journeys were returned during verification, including a 138-point dataset shape. Availability varies with the clock. To restore the original demo, restart the backend with RUSHLESS_DATA_MODE=simulation. Simulation remains the default when unset.

## Implementation

Added backend/app/network.py, feed_worker.py and tests/test_network.py. Modified feeds.py/main.py, home stop autocomplete, shared stop catalog, map geometry, route search, bus-position filtering and DataHealth. The existing design, simulation, watches, reports, forecasts and persistent profiles are retained.

Agency, stops, routes, trips, stop_times, shapes, service calendars/exceptions, feed_info and attribution tables are retained where present. Invalid geography, trip references, duplicate identifiers, duplicate trip sequences and backward times are rejected or quarantined. GTFS times above 24 hours retain their service day and Asia/Kolkata conversion. This is local validation, not certification by an external GTFS validator.

New GET /api/network/status reports counts, hash, source, feed version, import time and exclusions. Existing stop search supports q and limit; route search supports q and returns a bounded list of static patterns. Route detail returns geometry_source and dataset shapes where available. Pattern IDs retain original gtfs_route_id, direction and exact trip identities; variants do not collapse into a single route-direction pattern.

Journeys and arrivals discover directional scheduled trips at the requested stop, with service/calendar filtering and a two-hour lookahead. Candidate scans are bounded to 200; direct journeys only, no invented transfers. Preview lists are bounded, not total-network counts. Scheduled entries have no coordinates or passenger counts; Track a Bus excludes them. Unusable observed markers are hidden. GPS does not establish future crowding: Unknown remains Unknown, and uncertainty remains heuristic.

Insights adds Real BMTC Data Status with imported counts and validation metadata. Synthetic fixtures and pilot evidence stay separate. No real calibration or model was activated. Saved pairs retain compatibility; upstream IDs are also exposed in gtfs_stop_id.

## Authorized live data

No genuine provider endpoint, credentials or authorization were supplied. Official live GPS was not accessed; full live tracking remains an external dependency. Phase 4 protobuf fixtures, strict trip matching, geography/jump/age checks, unmatched quarantine, source separation and authorized HTTP safeguards are reused. Service alerts retain supplied text but do not infer detours. Full shape-based matching, frequencies and provider-specific detours remain limitations.

Configure RUSHLESS_SOURCE_ID, TRANSIT_FEED_URL, TRANSIT_FEED_ALLOWED_HOSTS, TRANSIT_FEED_PROVENANCE, TRANSIT_FEED_LICENSE and any TRANSIT_FEED_TOKEN on the server. Set TRANSIT_FEED_AUTHORIZED=true only after permission. GTFS_DB_PATH optionally overrides the active registry. Select authorized mode and restart. HTTPS/public hosts only, no redirects, 15-second timeout, 5MB limit; polling defaults to 60 seconds with a 15-second floor. Secrets never enter the browser.

Optional local polling worker, from backend/:

```powershell
.venv/Scripts/python.exe -m app.feed_worker
```

Ctrl+C stops it; --cycles bounds runs. Failures back off exponentially to 15 minutes without printing provider errors/secrets. Only injected fetches were used to test the worker. No volunteer device-GPS feature was added; existing explicit pilot arrival/category collection remains available.

## Validation

Backend checks cover the previous regression suite, protobuf fixtures, immutable update/rollback, midnight times, original IDs/directions, geometry and polling backoff. One upstream Starlette/AnyIO deprecation warning remains. Frontend lint, TypeScript and the optimized production build pass (Next.js emits an advisory about its optional ESLint plugin).

Final full backend run: **58 tests passed**. Proxy smoke check confirmed schedule mode, live_connected=false and zero matched fresh observed vehicles.

Browser verification confirmed three scheduled Silk Board → Marathahalli results with real route names, Scheduled estimate / heuristic badges and Unknown crowding. The production Insights screen showed 4,434 routes, 9,799 stops, 57,445 trips, the import version/exclusions, schedule mode, zero verified pilot labels, calibration unavailable, and BMTC live tracking disconnected. The synthetic fixture remained separately labelled. Screenshot: [real data status](real-bmtc-status.png). The existing responsive layout is retained; a new complete mobile flow audit was not performed for this milestone.
