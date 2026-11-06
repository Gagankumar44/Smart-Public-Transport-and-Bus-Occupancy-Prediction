# Phase 2 verification — 5 November 2026

Baseline: the original nine backend tests and TypeScript check passed before implementation.

Final backend suite: 16 tests passed (nine original, seven new grouped integration tests). Covers report validation/rate limiting, trip isolation, report influence and conflict, expiration, watch delay/crowd/freshness behavior, accept/keep, threshold crossings and deduplication, stopping and resets, headway classification, passed departures, small-change suppression and analytics totals. One upstream AnyIO deprecation warning remains.

Frontend: standalone TypeScript check and ESLint passed. Production build completed successfully with / and /insights. Next.js notes that the optional Next-specific ESLint plugin is not configured; TypeScript, core ESLint, typescript-eslint and React hook rules run. No ignored lint errors.

Browser evidence: Phase 2 default search returned three options. Selecting a card exposed Watch Journey and Report crowding. Submitting High returned an acceptance confirmation and one recent demo report in prediction evidence. Heavy traffic produced a six-minute delay alert and a feasible alternative. Explicit switch changed watched trip and route details from DEMO 02 to DEMO 03. Stop watching removed the panel after fixing empty-204 response parsing. Mobile report dialog at 390x844 had a 390px-wide fixed bottom sheet fully inside the viewport (top 283px, bottom 844px), with no horizontal document overflow.

Reporting adjusts the original passenger-flow model rather than replacing it. All observations, watches, headway events and insights remain labeled simulation/demo. No real passenger count dataset or predictive accuracy claim is introduced.

Production limitations: shared single-process demo state and anonymous best-effort rate limits; no background alerts or external push delivery. Reports persist in SQLite, watches expire in memory. Endpoint APIs and restart commands are documented in README.md. Backend tests are synthetic integration checks, not calibrated real-world evaluations.

Browser headway evidence: Close arrivals scenario produced a Potential bunching notice with a two-minute predicted gap and explicit synthetic explanation. The /insights page rendered ten simulated vehicles, route utilization/deviation meters and endpoint warnings from backend data.


Changed files: backend/app/main.py; backend/app/intelligence.py (new); frontend/components/JourneyIntelligence.tsx (new); frontend/components/types.ts; frontend/app/page.tsx; frontend/app/globals.css; frontend/app/insights/page.tsx (new); frontend/package.json and package-lock.json; frontend/eslint.config.mjs (new); tests/test_intelligence.py (new); README.md; .env.example; docs/PHASE2.md (new); docs/phase2.png (browser evidence). The original tests remain intact.

Insights responsive DOM-width checks at 390, 768 and 1366 pixels found no horizontal overflow. A final full-page insights screenshot request timed out; the commuter/headway screenshot was saved successfully. No claim is made that browser screenshots alone constitute automated browser regression coverage.
