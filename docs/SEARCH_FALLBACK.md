# Search results and demo fallback

The active real network contains 9,799 stop locations and 7,406 directional patterns. Local API checks returned real Silk Board to Marathahalli results in both planner and Explorer. This does not establish a supported direct/one-transfer connection for every possible stop pair.

The Journey Planner and Best Route Explorer now request `allow_demo=true`. They search the real timetable first; if it returns no supported journeys, three explicitly labeled demo connections are supplied between the chosen locations. Backend callers default to `allow_demo=false` and continue receiving honest empty results unless they request the fallback.

Demo connections are **not published BMTC services**. They use straight-line geometry, synthetic departures and estimated durations at illustrative speeds. There is no claim of road alignment, real bus operation, seats or GPS. Crowding remains Unknown. Their source is `demo_journey`, they carry a demo badge, and production watches and forecasts are disabled for them. No demo vehicle is inserted into the observed fleet. This supports examples across all selectable imported stop locations without inventing real routes.

Track a Bus keeps real route searches and scheduled arrival estimates. Empty observed results now offer **Show moving demo bus**; an empty route-arrival panel offers the existing labeled corridor preview. That preview continues to reuse the isolated simulator, with pause/resume/restart and no change to production data mode.

The Overview hero no longer displays the Silk Board / Marathahalli corridor preview. Those locations remain searchable; the Overview From/To fields remain empty until chosen.

Validation: 26 targeted Explorer, route-monitor and demo-preview tests passed. The added regression verifies empty real searches, labeled demo fallback, planner serialization, Unknown crowding and real-results priority. TypeScript and focused ESLint checks passed. No full-app regression suite was run.
