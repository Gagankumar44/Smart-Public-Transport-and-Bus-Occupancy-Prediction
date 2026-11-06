# Validation — 5 November 2026

Verified locally on Windows with Node 26.11.1, Python 3.11.2, Next.js 15.5.29 and FastAPI 0.115.12.

- Backend integration suite: **9 passed**. One upstream Starlette/AnyIO deprecation warning; no test failure.
- Next.js production build: passed, with TypeScript validation and static route generation.
- Standalone TypeScript check: passed.
- HTTP frontend request: 200. API health and routing requests: 200.
- Chrome browser: default GTFS-derived origin/destination populated; search returned three backend-generated journeys; Comfortable recommended DEMO 02; Fastest recommended DEMO 01.
- Missing GPS: cards changed to Unknown crowding, Low confidence and Scheduled estimate.
- Autocomplete: partial `Bell` returned two actual GTFS stops; Enter selected the first; swap exchanged endpoint names.
- Reverse subset search returned two demo alternatives.
- Phone screenshot inspected at 390 × 844. Cards stack above the map, inputs and search remain usable.
- DOM width checks at 360, 768, 1366 and 1920 pixels: no horizontal document overflow.
- Desktop screenshot inspected: source/destination, corridor, moving markers, legend, OSM attribution and persistent simulation label rendered.

These are controlled implementation tests, not evidence of real-world prediction accuracy. Automated browser regression tests are not bundled. Browser-disconnected and map-tile failure states are implemented but were not tested by deliberately blocking network access. Production multi-user hosting and official live transit feeds were not tested. Arbitrary GTFS imports are staging-only; full service-calendar routing is outside this prototype.

Data evidence: actual downloaded ZIP contained stops, routes, trips, stop_times, calendar and shapes. Extracted 15 ordered stops from outbound 500-F trip 2509. Only the attributed corridor subset is bundled in Git. The downloaded archive is ignored.
