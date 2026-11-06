# Phase 3 implementation and verification

## Pipeline before changes

A monotonic clock generates vehicle progress from departure offset and a uniform scenario segment duration. ETA is departure + stop-index × segment time minus elapsed time. Dwell is implicit. Occupancy walks one bounded boarding/alighting function over future stops and blends generation-scoped, trip-specific passenger reports. Journey ranking uses the resulting boarding-stop crowd category and travel time; watches call the same ranking function. Medium/Low confidence reflects simulation/fallback/conflicting reports, without error-based calibration. SQLite stores stops, scenario events and crowd reports. There is no historical labeled observation store, evaluation report or trained model.

The Phase 2 baseline was rerun before modification: 16 backend tests passed and TypeScript passed.


## Implemented changes

Created backend/app/predictive.py (shared method selection, uncertainty, forecast/quality APIs), backend/app/history.py (private observation pipeline, evaluation, optional ridge candidate), backend/app/schedule.py (calendar-aware staged GTFS schedule lookup), frontend/components/CrowdForecast.tsx, frontend/components/PredictionQuality.tsx, tests/test_predictions.py and data/evaluation_demo.csv.

Modified backend/app/main.py, backend/app/intelligence.py, backend/requirements.txt, frontend/components/types.ts, frontend/app/page.tsx, frontend/app/insights/page.tsx, frontend/app/globals.css, tests/test_intelligence.py and README.md. Added docs/simulation-evaluation.json and docs/phase3-quality.png as observed results/preview artifacts.

New endpoints: GET /api/vehicles/{id}/forecast, GET /api/predictions/methods, GET /api/data/quality, GET /api/insights/prediction-quality, POST /api/demo/observation. Existing prediction metadata now includes method, generation, demand profile and heuristic uncertainty. No public import/training/trajectory endpoint was introduced.

## Observed validation

- Final backend suite: 33 passed, including all original Phase 1/2 tests. One upstream Starlette/AnyIO deprecation warning remains.
- Frontend ESLint, standalone TypeScript and production build passed. Next.js still notes the optional Next-specific ESLint plugin is absent; configured core/TypeScript/hook lint rules run.
- Browser default search returned three journeys. Cards showed labeled heuristic ETA bounds. Journey details rendered future-stop forecasts using the same boarding forecasts as the cards.
- Fresh demo observation changed DEMO 02 boarding from 8:39 to 8:38 AM and subsequent stop arrival times consistently. Watch Journey remained active.
- Missing GPS changed future categories to Unknown, high uncertainty and scheduled boarding at 8:39 AM. The watch logged a crowd/freshness change.
- Measured viewport widths 390 and 768 had no document horizontal overflow. A requested larger in-app viewport stayed constrained to 768; a full-width desktop browser check was not claimed for this phase. The existing wider layout was preserved.
- Prediction Quality rendered the explicit no-real-dataset message, disabled-model status and the actual saved synthetic comparison table. A full-page screenshot was saved.

## Synthetic evaluation only

72 deterministic fixture rows; 42 training, 12 calibration, 18 test observations across disjoint 7/2/3 dated trips. Test MAE: schedule 2.667 min; recorded progress examples 1.667 min; historical baseline 2.233 min. The fixture is intentionally constructed to exercise the pipeline, not an independent field evaluation of the serving engine. Occupancy classification matches 18 constructed labels (accuracy/F1 1.0); majority baseline accuracy .333. See simulation-evaluation.json for all metrics and the small-sample interval coverage.

No genuine dataset was supplied, no real-world accuracy was measured, and no genuine-data model artifact was trained or activated. The candidate training unit test uses mock observed labels only in a temporary database. Candidate serving stays disabled even when schema/evaluation gates pass; production activation requires an authorized real-data adapter and explicit deployment validation.

Remaining limits: single shared simulation process; heuristic live bounds; manually mapped corridor registry for historical imports; full-network GTFS serving, genuine observation adapters, durable per-user watches, real field evaluation and calibrated uncertainty remain future work. Raw observations stay private in the ignored SQLite file, separate from features/predictions/evaluations. Source authenticity is asserted by the importer, not independently established by software.
