# RushLess frontend redesign

The existing Next.js app now uses a shared transport workspace: persistent sidebar on desktop, a keyboard-accessible drawer on mobile, a top language/support bar and an explicit source-status strip. The palette uses petrol teal `#174f4a`, ivory `#f6f7f2`, leaf `#d6ed9c`, and quiet blue/violet/amber service accents. It does not reuse the reference screenshot's red/pink treatment or official branding.

Manrope is the body face and Outfit is the display face. Both are bundled locally with their OFL licenses; no runtime Google Fonts request is needed. The bus/city illustration is an original code-native SVG.

## Pages and working behavior

| Route | What it does |
| --- | --- |
| `/` | Eight service shortcuts, quick stop-pair handoff, saved-journey previews, actual configured-source counts and a data-transparency link |
| `/planner` | Existing journey comparison, Fastest/Comfortable modes, uncertainty, map, occupancy forecasts, watch/report tools, pilot form and demo scenarios; accepts `origin` and `destination` query parameters |
| `/track-bus` | Search active vehicles by route/ID, inspect the next stop and current load, and show usable positions; accepts a `vehicle` query parameter |
| `/live-route` | Select a directional route pattern, inspect ordered stops, map active vehicles, and open a stop's arrival board |
| `/timetable` | Filter upcoming source-clock arrivals by stop and route, with scheduled/predicted times and boarding crowding shown separately; accepts a `stop` query parameter |
| `/facilities` | Search the supported stop directory, inspect public stop context/coordinates and route coverage, and open arrivals |
| `/fare-calculator` | Calculate a personal budget from editable base/per-km assumptions, travellers and a return-leg option; reject unsupported/equal stop pairs |
| `/feedback` | Save up to 20 suggestions locally with category/rating, reload them, export JSON, clear with an in-page undo option |
| `/guide` | Explain the planner, tracking, uncertainty, source modes and pilot collection; open the existing pilot observation form |
| `/saved` | View saved and recent stop pairs; reuse existing server-side anonymous profile management for rename/remove/preferences/reset |
| `/insights` | Existing corridor charts, source health, verified evidence and calibration readiness in the shared workspace |
| `/help` | Prototype support guidance and privacy/storage explanations |

Every service card opens a working route. No buttons claim to book tickets, contact an operator, retrieve a genuine live BMTC feed or verify amenities.

Help includes a user-initiated telephone link to the BMTC helpline listed in the [official Namma BMTC 2.0 app description](https://play.google.com/store/apps/details?id=com.bmtc.bmtcavls.two), checked on 5 November 2026. The source link remains visible; actual contact availability is not guaranteed. No call or message was placed during implementation. The direct BMTC contact webpage timed out during research, so its contents were not assumed.

## Data boundaries

No backend contract or schema was changed for this redesign. `TransitContext.tsx` supplies the existing `/api/vehicles`, `/api/routes`, `/api/stops/search`, `/api/system/status` and `/api/profile` data to the new screens. Route details and stop arrivals use the existing API. Five-second refreshes remain source-aware; failures show an error and identify cached information as potentially stale.

No provider was newly connected. Simulation is still the default. Vehicle current load is distinct from boarding forecasts. Stale/missing/low-confidence positions are not shown as fresh markers. Lines connect supported stops, not road geometry. The timetable is a scoped arrival board, not an official full-network timetable.

Facilities have not been surveyed: shelter, toilets, seating and accessibility remain unverified. The calculator's starting ₹10 base and ₹2/km are explicitly illustrative, editable assumptions. It adds straight stop-to-stop distances along a supported directional pattern and rounds each assumed per-person leg up to a rupee. It is not an official fare tariff; stages, classes and concessions are not modeled. A return estimate assumes the same leg cost and does not verify reverse-service availability.

Feedback never leaves the device automatically and is not sent to BMTC. `rushless-feedback-v1` is browser-local; the export states that provenance. Undo after clearing is available until leaving/reloading the page. An explicitly labelled frontend-QA note was used for the persistence/export check. Anonymous server profiles remain separate from feedback storage.

The English/Kannada selector persists `rushless-language-v1` locally. It translates navigation, dashboard service labels and core tool labels. Advanced forecast, evidence and guide text remains English; the User Guide states that limit. Stop names retain upstream spelling.

## Main files

Created `components/AppShell.tsx`, `TransitContext.tsx`, `Locale.tsx`, `BusScene.tsx`, `TransportTools.tsx`, `CommuterTools.tsx`, `GuidePages.tsx`, `app/redesign.css`, the new page routes and local font/license files. Moved the former root planner into `components/JourneyPlanner.tsx`; the root page is now the dashboard. Updated `app/layout.tsx`, `app/insights/page.tsx` and README links/demo instructions. Existing backend modules, forecast/watch/report components and stores are retained.

## Run on Windows

From the repository root in terminal 1:

```powershell
$env:RUSHLESS_DATA_MODE = 'simulation'
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

In terminal 2:

```powershell
cd frontend
npm run build
npm run start
```

Use `npm run dev` instead of build/start during editing. Stop this workspace's frontend before building. The frontend is at `http://127.0.0.1:3000`; its same-origin `/api` proxy targets port 8001 by default. No account, new service or provider key is needed for the demo.

## Demonstration and validation

1. Open the dashboard, keep Silk Board → Marathahalli, and use Find my journey to open the prefilled planner. Search and select a recommendation to inspect its map/forecast.
2. Track a Bus: search `SIM-20`. Open Track a Live Route, choose DEMO 04 and inspect the reversed stop sequence. Open Central Silk Board's timetable and filter DEMO 02.
3. Search Facilities for Bellanduru. Notice that amenities are unverified. Use Fare Calculator with two travellers plus a return journey and inspect the labelled estimate; equal stop pairs are rejected.
4. Save an explicitly synthetic feedback suggestion, reload, and export it. Check saved journeys without assuming a saved vehicle is still available.
5. Try the language selector and mobile menu. Visit Insights to inspect source and calibration status, and User Guide for the pilot form.

Regression result: 53 backend tests passed, with one upstream Starlette/AnyIO deprecation warning. Frontend ESLint and TypeScript checks passed. Browser checks exercised dashboard handoff/search, vehicle filtering, directional route changes, timetable filtering, the fare example (₹132 for two return travellers under the displayed illustrative assumptions), equal-stop validation, feedback reload/export, saved-journey display, pilot modal, Kannada-label reload and the mobile menu's Escape/focus behavior. The dashboard, planner and calculator had no horizontal overflow at 390 × 844. Final build and screenshot results are recorded below after the production pass.

Design references supplied by the user were treated as resources, not installation commands. The [frontend design guidance](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) and [web interface checklist](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md) informed typography, keyboard behavior, reduced motion and explicit data limits. No third-party skills were installed.
