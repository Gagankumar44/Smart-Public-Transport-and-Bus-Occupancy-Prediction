# Real-data-only app

The public app now defaults to schedule mode and ignores a request to enable simulation unless the explicit engineering test flag is enabled. Startup requires the imported BMTC network. The source is the published unofficial Vonter/BMTC GTFS archive: 4,434 routes, 9,799 stops and 57,445 valid trips. Original dataset caveats and ODbL attribution remain applicable.

Removed from active storage: one synthetic source and its raw/normalized protobuf frames, one practice pilot record, two synthetic history/evaluation datasets, one demo-named saved pair, demo crowd reports and scenario events. Ordinary saved real stop pairs remain. Private recovery snapshots are under ignored data/private; they are not served by any public API. Synthetic CSV/protobuf input files were moved out of app data into tests/fixtures.

Removed demo controls and simulation evaluation sections from the frontend, replaced demo report headings with real-observation availability, restricted the pilot catalog to real routes, and removed the known frontend-QA feedback sample on browser load. API demo mutations are denied in normal operation. Automated tests use temporary runtime/profile/history databases; engineering fixtures cannot repopulate the public app's data.

No live provider or real occupancy measurements were fabricated. The app uses actual published schedules and route geometry. Live tracking is disconnected; crowding remains Unknown when genuine evidence is missing. No synthetic accuracy score is presented as real performance.

Start from the repository root:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

In another terminal:

```powershell
cd frontend
npm run build
npm run start
```

Earlier phase documents describe historical demo workflows and are superseded by this guide. Current verification: 59 backend tests passed; ESLint and TypeScript passed. Production build and runtime source checks are recorded in the task result.
