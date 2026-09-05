# Task 2

## What was implemented

- Deterministic tool layer foundation for marine, weather, and geospatial data
- Structured unavailable responses instead of fake values
- Temporary `LiveContextService` integration layer for the Rameswaram demo
- Reuse of the existing Golden Schema contract
- Environment variable placeholders for upstream data configuration

## Data sources

- Copernicus Marine: configurable future live source
- INCOIS: source capability exists but requires official access configuration
- SACHET / NDMA CAP: alert integration structure exists but is not enabled by default
- PostGIS / EEZ / MPA / IMBL: geospatial interface exists and is ready for authoritative datasets

## Environment variables

See [.env.example](../.env.example) for placeholders.

## How to run

```powershell
cd C:\Users\DEVANSH\Desktop\orca\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## How to run live test

The repo does not yet have a live upstream configuration, so the live test will report structured unavailable states unless the environment is configured.

## What currently works

- FastAPI server starts
- Task 1 health endpoint works
- Task 1 experience endpoint works
- Tool interfaces exist and return structured results
- Unavailable sources are explicit and not fabricated

## What is unavailable

- Live Copernicus data without configured credentials and dataset IDs
- Live INCOIS data without approved access workflow
- Live SACHET alerts without official feed access
- PostGIS boundary datasets without local database imports

## Known limitations

- This is a tool-layer foundation only; no orchestrator, voice, TTS, or frontend is implemented yet.
- No safety or fishing yield score is calculated in this task.
- No fake data is inserted under any source.

## Next task

Task 3: Golden Schema + Data Fusion + Decision Engine
