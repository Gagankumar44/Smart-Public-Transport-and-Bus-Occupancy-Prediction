# Track a Bus availability fix

The previous page deliberately excluded every schedule-only entry from `/api/vehicles`. With no authorized live provider, this left an empty vehicle list even though published BMTC routes and timetables were available. Searching for `210` could therefore never show a route.

Track a Bus now opens on **Scheduled services**. It searches the imported network using `/api/routes?q=…&limit=50`, displays directional origin/destination patterns, and draws their published geometry and stops. Selecting a pattern loads its upcoming origin departures and destination arrivals. Search results are capped at 50 patterns; narrowing the search queries the full imported network.

The new `/api/routes/{pattern_id}/departures?limit=5` endpoint uses the actual trips, stop times and service calendar. It looks ahead seven days and includes previous-service-day trips with 24+ hour departure times. Invalid route patterns return 404 and invalid limits return 422. Times include the date and are displayed in IST. A route remains browsable when it has no upcoming origin departure in this window; missing service is never invented.

**Observed buses** is a separate view. It retains source-labelled observations, vehicle search and usable position markers. It continues to show zero observations because an authorized live BMTC feed is not connected. Scheduled route maps contain no fabricated bus location and crowding stays Unknown. Neither published trips nor the next-departure list confirms that an actual bus is operating.

Verification:

- 78 backend tests passed, including midnight rollover, next-week service, calendar exclusions, API limits and missing patterns.
- Frontend ESLint, TypeScript and optimized build passed. Non-blocking upstream Next.js ESLint-plugin advisory remains.
- Real active network search for `210` returned 50 directional patterns at the configured cap. The first result, 210-B KTNR-KMT-VSD, returned five published departures; the proxied departures request took 55 ms in this run.
- Browser verified route 210 results, Kothanuru Hari Nagara → Vidhana Soudha geometry, origin departures at 08:30 with destination arrival at 09:30, and the separately empty observed-bus view. These are published records from the unofficial archive and retain its timetable caveat.

Runtime remains schedule-only. No private endpoint, provider credentials, synthetic vehicle positions or live-data claims were introduced. Existing ODbL/source attribution is unchanged.
