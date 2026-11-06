# RushLess problem and constraint audit

## Outcome

The application supports monitoring after boarding, updated destination estimates, scoped disruption handling, and alternative direct departures from a commuter-confirmed stop. The production application continues to use published BMTC schedules. An authorized live BMTC feed has **not** been connected.

## Requested data constraints

| Constraint | Implemented behavior and evidence |
| --- | --- |
| Public BMTC GTFS and licensing | Imported the published unofficial Vonter archive, version 20260907: 4,434 route records, 9,799 valid stops, 57,445 valid trips, 7,406 patterns and 1,537,259 stop-time rows. ODbL-1.0 attribution and underlying BMTC copyright are retained. Local checks excluded 161 stops and 391 trips and quarantined 67 shapes. Upstream warns of inaccurate timetables and missing routes; these checks are not official feed certification. |
| Standards-based realtime adapter | Local protobuf tests cover VehiclePosition, TripUpdate and scoped ServiceAlert entities. Cancellation without a vehicle identifier or optional TripUpdate timestamp is supported. Departure-only events and upstream delay propagation are supported. NO_DATA falls back to schedules; it does not mean the stop is skipped. |
| Secure future configuration | Backend-only environment configuration requires explicit permission, provenance, license, HTTPS and an allowlisted public provider hostname. Tokens are not returned to the browser; redirects are disabled, response sizes and polling are bounded. See `.env.example` and `REAL_DATA.md`. No provider fetch was made during this audit. |
| Real network in search/maps/ETA | Journeys, timetables, stop search, shapes and published fare records use the active imported registry. Fixed planner initialization so all real stop IDs, including links beyond the first 100 stops, resolve correctly. The previously open pair resolves to Thyagaraja Nagara → AMC College. |
| Synthetic/real separation | Production remains schedule-only with zero observed GPS positions and `live_connected=false`. Synthetic protobuf/flow examples remain isolated tests. Replay data cannot leak into schedule mode. Future crowding remains Unknown without evidence. |
| Existing features | Backend regression suite: 76 passed. Frontend ESLint, TypeScript and optimized production build passed. Browser checks verified search, watching, boarding, remaining ETA, confirmed stop selection, personal diversion reporting and a real scheduled alternative. Schedule-only arrivals no longer trigger legacy demo/bunching notices. |

## Handling disruption after a journey starts

1. Find a departure and select **Watch Journey**. This action is available without opening Details.
2. Confirm the current stop and choose **I've boarded — start monitoring**. The watch predicts the destination; passing the original boarding stop does not end monitoring.
3. Confirm progress along the remaining stop sequence. Progress cannot move backward or jump to an unknown stop. Confirming the destination finishes monitoring and stops suggestions.
4. The watch refreshes every five seconds while the tab is visible. It flags cumulative ETA deterioration of at least three minutes and compares eligible alternatives under the selected Fastest/Comfortable preference.
5. A private **Bus stopped / breakdown** or **Route diverted** report marks the selected journey unusable for that watch and searches from the confirmed stop. It is not published as an operator incident, GPS observation or ground truth.
6. Alternative cards show boarding stop, boarding time, destination time and source. Accepting an alternative requires the commuter to confirm they are at that stop; the watch returns to waiting for the new departure. Keeping the current journey dismisses that suggestion until progress is updated.

An authorized source, when configured later, can supply matched cancellations, skipped stops, delay predictions and service alerts. Selector fields are matched together, different selectors are alternatives, and validity intervals and direction/service instance are respected. Route detours or moved stops are conservatively withheld when the replacement path is unknown; no detour geometry is invented.

Each FULL_DATASET replaces the currently served entities. Raw history is retained privately, but removed alerts and cancellations no longer affect journeys. Older full snapshots are rejected. Stale observations revert to a low-confidence schedule estimate rather than indefinitely preserving an old cancellation or position. Empty replay snapshots retain their source clock.

## Scope and remaining dependencies

- Automatic detection of actual BMTC delays, breakdowns, diversions and occupancy is blocked by the absence of an authorized provider and genuine observations. The interface states this explicitly.
- Current recovery suggestions are **direct departures from a confirmed stop on the selected journey**, within a two-hour bounded search. A diversion to a stop outside that sequence requires a new planner search. Verified multi-transfer routing, off-route recovery and provider-supplied replacement geometry are not implemented.
- No alternate departure is invented when the search returns none. Scheduled times and the unofficial archive do not guarantee that a bus will operate.
- Watches are temporary capabilities held in server memory, refreshed while the page is open; they expire after 30 minutes without access and are lost on server restart. Background push notifications are not implemented.
- Genuine crowd forecasting/calibration requires verified observations. GPS alone does not supply passenger counts. The existing simulation model is engineering-only.

## Verification

`backend/.venv/Scripts/python.exe -m pytest tests -q`: **76 passed**, one upstream Starlette/AnyIO deprecation warning. New tests cover boarding-stop passage, destination delays, cumulative delays, personal incident isolation, alternatives/acceptance, invalid and backward progress, completion, cancellation recovery, scoped/expired/withdrawn alerts, NO_DATA versus SKIPPED, departure-only propagation, source-mode separation and suppression of simulated headway warnings for schedule-only arrivals.

`npm run lint`, `npm run typecheck`, `npm run build`: passed. The build retains a non-blocking Next.js ESLint plugin advisory.

Production runtime: API on 8001, frontend on 3000, active mode schedule, `live_connected=false`, zero matched observed vehicles. Existing fares and network counts are unchanged.

Browser evidence: `journey-monitoring.jpg`, showing the running schedule-only onboard monitor and explicit live-feed limitation. Personal incident reports used for UI verification are temporary watch state, not published observations.

Specification references: [GTFS Realtime reference](https://gtfs.org/documentation/realtime/reference/) and [service alert selector semantics](https://gtfs.org/documentation/realtime/feed-entities/service-alerts/). Data source: [Vonter BMTC GTFS](https://github.com/Vonter/bmtc-gtfs).
