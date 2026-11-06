# Tracking and mid-journey disruption update

## Behavior

Selecting a bus route now opens a visible selected-service panel and scrolls it into view. It shows the direction, available source positions, confirmed moving count and next arrival at a chosen stop. A new `/api/routes/{pattern_id}/monitor?stop_index=…` API refreshes every ten seconds in visible tabs. Stop selection uses an ordinal so repeated stop names/IDs on loops remain distinguishable. Published origin departures remain available in a collapsed section.

The map uses a solid blue route line, smaller stop dots, A/B endpoints, a fit-route control and distinct bus icons. A stop dot opens its name and selects its arrival board. Bus icons require finite fresh source coordinates; scheduled trips are never turned into moving markers. Map refreshes do not continuously reset a commuter's pan/zoom when the geometry is unchanged.

The monitor shows arrivals at the selected stop, including scheduled trips that have already left their origin. Static estimates look ahead seven days and respect the service calendar and 24+ hour times. Current provider updates take precedence; cancelled trips and skipped stops do not reappear through the schedule fallback. Stale GPS disappears and stale updates revert to explicitly labelled timetable estimates.

Provider speed/status is retained and validated. A speed above 0.5 m/s counts as confirmed moving; stationary and unknown movement remain distinct. Without a fresh authorized source, moving count is `null`/Unavailable, rather than an invented zero. Counts cover the selected directional pattern, not all BMTC buses. Unknown occupancy remains Unknown.

Route-number search now accepts punctuation variants such as 600F/600-F and 210N/210-N. An unmatched query no longer substitutes unrelated active preview routes.

## Unexpected disruption after boarding

Journey Planner → Watch Journey → confirm boarding continues to monitor the destination after the boarding stop has passed. Provider changes update the destination ETA; cumulative deterioration of three minutes triggers an alert. A materially faster alternative is offered from the confirmed stop. A confidence penalty no longer hides an otherwise clear saving of at least five minutes; its timetable/provider source remains visible for the commuter to assess.

Private breakdown/stopped-bus or diversion reports disable the selected journey for that watch and search for recovery departures. Matched cancellation, skipped-stop and service-alert handling remains active. Accepting an alternative returns the watch to waiting for the replacement departure; keeping a journey dismisses the suggestion. Destination confirmation completes the watch. Reports are not broadcast as operator events.

Recovery remains limited to direct departures from a confirmed stop on the selected journey. Off-route diversion recovery, verified transfers and background push are not implemented. Watches are in-memory, expire after inactivity and are lost on server restart.

## Validation and limits

- **89 backend tests passed**, with one upstream Starlette/AnyIO deprecation warning. Frontend lint, TypeScript and optimized build passed; the existing Next.js ESLint-plugin advisory is non-blocking.
- New isolated mock-provider tests verify fresh moving/stationary/unknown movement, invalid speeds, stale GPS, downstream arrivals, cancellation exclusion, post-boarding ETA deterioration and acceptance of a faster replacement. No provider network access occurs in these tests.
- Browser checks verify real 600-F direction changes, selected Electronic City arrivals, stop-dot popup, fit-route control, boarding, private breakdown recovery and accepting an alternate departure. The temporary recovery watch was stopped after verification. The shared map remains usable in Journey Planner.
- Added regression coverage for repeated stop occurrences and delayed geometry loading. Stop lookup is indexed, shared shape points are cached by dataset version, and map geometry is loaded after ranking candidates. This removes a peak-hour timeout found in browser verification; the tested 20-result Electronic City → Banashankari search returned in 249 ms after the fix.
- Runtime remains schedule-only with `live_connected=false`. There is no authorized live BMTC source, so actual live locations and automatic real-world incident detection remain blocked. The public application has no synthetic GPS injected into it.

The existing published-data licensing and timetable caveats remain in force. Leaflet marker/tooltip implementation follows the [official Leaflet reference](https://leafletjs.com/reference).
