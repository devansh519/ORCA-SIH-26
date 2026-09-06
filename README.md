# ORCA — Ocean Risk & Catch Advisor

> **Demo Prototype | Smart India Hackathon — PS 26176**

ORCA is a voice-first, multilingual AI platform designed to support fishermen, marine researchers, and coastal authorities with ocean-risk awareness, fishing guidance, geospatial boundary checks, and proactive safety alerts.

The prototype demonstrates a complete working flow using real geospatial data, Supabase/PostGIS, an ORCA orchestrator, and Groq LLM-based response synthesis.

---

## 1. Demo Goal

The prototype focuses on one concrete, human-stakes scenario:

> **A fisherman near Rameswaram wants to know whether it is safe to operate near the International Maritime Boundary / EEZ boundary.**

ORCA can:

1. Receive a fisherman query.
2. Understand the request and select the appropriate tool.
3. Query real geospatial boundary data.
4. Perform the boundary-distance calculation using PostGIS.
5. Keep safety and fishing-yield decisions separate.
6. Generate an explainable response.
7. Monitor a saved frequent fishing zone in the background.
8. Create a proactive Tamil safety alert when the zone is too close to the boundary.

---

## 2. What Is Working in This Prototype?

### Feature 1 — Proactive Geofence Alert

A background poller periodically checks saved `frequent_zones`.

Current demo flow:

```text
Saved Frequent Zone
       ↓
Background Poller
       ↓
Geofence Alert Service
       ↓
Geospatial Tool
       ↓
Supabase PostgreSQL + PostGIS
       ↓
Marine Regions World EEZ v12
       ↓
Distance / Boundary Check
       ↓
Deterministic Safety Rule
       ↓
RED / AMBER Alert
       ↓
Supabase proactive_alerts
```

The current demo zone is around Rameswaram.

The prototype uses a saved frequent zone rather than continuous GPS. This keeps the demo deterministic while preserving the architecture for future GPS/AIS integration.

### Feature 2 — Geospatial Boundary Query

A user can ask:

```text
Am I near the international maritime boundary?
```

ORCA routes the request to the geospatial tool, which checks the location against the imported EEZ geometry.

Example demo result:

```text
Location: Rameswaram
Distance to EEZ boundary: ~0.49 km
Status: Outside EEZ
Confidence: 1.0
Quality: GOOD
Source: Marine Regions World EEZ v12
```

### Feature 3 — ORCA Orchestrator

The experience API passes requests through the ORCA orchestration layer.

The orchestrator is responsible for:

- Intent classification
- Context handling
- Tool selection
- Workflow execution
- Golden Schema validation
- LLM-based synthesis
- Response construction

For the prototype, critical geospatial/safety calculations remain deterministic. The LLM explains the evidence rather than inventing safety decisions.

### Feature 4 — Groq LLM

Groq is the configured LLM provider for ORCA synthesis.

Current model:

```text
llama-3.3-70b-versatile
```

The existing implementation uses `GroqProvider` inside:

```text
backend/app/orchestrator/core.py
```

A separate `llm/` folder is not required for the current architecture.

### Feature 5 — Golden Schema

ORCA normalizes tool output into a common structure:

```text
Source
Timestamp
Location
Variables
Units
Quality
Confidence
```

This makes outputs from different data sources easier to validate, fuse, and explain.

---

# 3. Architecture

```text
                    ┌──────────────────────────┐
                    │        ORCA Users        │
                    │                          │
                    │ Fisherman | Researcher   │
                    │ Authority                │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │     Experience API       │
                    │      FastAPI / REST      │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │   ORCA Orchestrator      │
                    │                          │
                    │ Intent → Context →      │
                    │ Tool Selection → Flow    │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌────────────┐     ┌────────────┐     ┌────────────┐
       │ Geospatial │     │ Marine Data│     │  Weather   │
       │   Tool     │     │    Tool    │     │    Tool    │
       └─────┬──────┘     └────────────┘     └────────────┘
             │
             ▼
       ┌────────────────────────────┐
       │     Supabase PostgreSQL    │
       │          + PostGIS         │
       └────────────┬───────────────┘
                    │
                    ▼
       ┌────────────────────────────┐
       │ Marine Regions World EEZ   │
       │          v12               │
       └────────────────────────────┘

                    Query Response
                         │
                         ▼
              ┌─────────────────────┐
              │   Groq LLM          │
              │   Synthesis /       │
              │   Explanation       │
              └──────────┬──────────┘
                         │
                         ▼
              Text / Voice / Map / Alert


       ───────── PROACTIVE PATH ─────────

       Saved Frequent Zones
                │
                ▼
       Background Alert Poller
                │
                ▼
       Geofence Alert Service
                │
                ▼
       Geospatial Tool + PostGIS
                │
                ▼
       Safety Threshold
                │
                ▼
       Tamil Proactive Alert
                │
                ▼
       proactive_alerts
```

---

# 4. Technology Stack

## Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy
- asyncpg
- httpx
- LangGraph
- pytest

## Database

- Supabase
- PostgreSQL
- PostGIS

## AI / LLM

- Groq API
- `llama-3.3-70b-versatile`

## Geospatial

- PostGIS
- Marine Regions World EEZ v12
- GeoPackage (`.gpkg`)

## Frontend

The architecture supports:

- Next.js
- TypeScript
- MapLibre GL JS
- deck.gl

The current demo primarily validates the backend/API and core prototype workflow.

---

# 5. Project Structure

```text
orca/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── context/
│   │   ├── decision/
│   │   ├── fusion/
│   │   ├── graph/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── tools/
│   │   ├── voice/
│   │   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── main.py
│   │
│   └── tests/
│
├── data/
│   └── geospatial/
│
├── docs/
│
├── frontend/
│
├── scripts/
│
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

# 6. Prerequisites

Install:

- Python 3.12+
- `uv`
- Git
- A Supabase project
- A Groq API key

The project uses a Python virtual environment located at:

```text
.venv/
```

---

# 7. Environment Configuration

Create a local `.env` file in the repository root.

Use `.env.example` as the template.

Required configuration:

```env
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# PostgreSQL
DATABASE_URL=

# LLM
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
```

## Important

Never commit `.env`.

The repository intentionally tracks:

```text
.env.example
```

but ignores:

```text
.env
```

---

# 8. Install Dependencies

From the repository root:

```powershell
uv sync
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then:

```powershell
cd backend
```

---

# 9. Supabase + PostGIS

ORCA requires PostgreSQL with PostGIS enabled.

The prototype uses:

```text
Supabase PostgreSQL
        +
PostGIS
```

The geospatial database contains:

```text
gis.eez_boundaries
```

The prototype also uses:

```text
public.frequent_zones
public.proactive_alerts
```

These tables support the proactive geofence demonstration.

Before running the application, ensure the required database tables and EEZ geometry have been imported.

---

# 10. EEZ Data

The prototype uses:

```text
Marine Regions World EEZ v12
```

The relevant source layer is:

```text
eez_v12
```

It contains polygon/multipolygon EEZ geometries in EPSG:4326.

The application imports these geometries into:

```text
gis.eez_boundaries
```

The imported dataset contains:

```text
285
```

EEZ features.

Large geospatial files are intentionally ignored by Git.

---

# 11. Start the Backend

From:

```text
orca/backend
```

run:

```powershell
uv run uvicorn app.main:app --reload
```

The API should start at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

---

# 12. Health Check

Open:

```text
GET /api/v1/health
```

Expected response should indicate that the API is running.

---

# 13. Demo — Geospatial Boundary Query

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

Find:

```text
POST /api/v1/experience/query
```

Use:

```json
{
  "user_id": "demo-fisherman",
  "language": "en",
  "voice_input": false,
  "location": {
    "name": "Rameswaram",
    "latitude": 9.2876,
    "longitude": 79.3129
  },
  "question": "Am I near the international maritime boundary?"
}
```

The response should contain:

- Orchestration information
- Selected geospatial tool
- EEZ result
- Distance
- Confidence
- Quality
- Source
- Timestamp
- Recommendation

Example:

```text
query_type: boundary_geofence_query
selected_tools: geospatial

inside: false
distance_km: ~0.49
confidence: 1.0
quality: GOOD
source: Marine Regions World EEZ v12

recommendation: OUTSIDE_EEZ
```

---

# 14. Demo — Proactive Alert

The proactive alert system monitors saved frequent zones.

Check configured zones:

```text
GET /api/v1/alerts/zones
```

The demo zone is:

```text
Name: Rameswaram Demo Zone
Latitude: 9.2876
Longitude: 79.3129
Radius: 1.0 km
Language: Tamil
Active: true
```

Trigger a check manually:

```text
POST /api/v1/alerts/check
```

Request:

```json
{
  "user_id": "demo-fisherman",
  "force": true
}
```

The system performs:

```text
Frequent Zone
    ↓
Geofence Service
    ↓
GeospatialTool
    ↓
PostGIS
    ↓
EEZ Boundary
    ↓
Distance ≈ 0.49 km
    ↓
RED Alert
```

Example alert:

```text
Title:
கடல் எல்லைக்கு மிக அருகில்

Message:
சிவப்பு எச்சரிக்கை: நீங்கள் EEZ எல்லையிலிருந்து
சுமார் 0.49 km தொலைவில் உள்ளீர்கள்.
```

---

# 15. Check Active Alerts

Use:

```text
GET /api/v1/alerts/active?user_id=demo-fisherman
```

This returns alerts stored in:

```text
public.proactive_alerts
```

The current prototype's:

```text
delivery_status = created
```

means the alert has been generated and persisted by ORCA.

It does **not** mean that an external SMS/push notification has already been delivered.

---

# 16. Check the Background Poller

Use:

```text
GET /api/v1/alerts/poller/status
```

A healthy running poller should show:

```json
{
  "running": true,
  "interval_seconds": 10800,
  "last_run_at": "...",
  "last_result": {
    "status": "completed"
  },
  "last_error": null
}
```

The current prototype runs the alert check:

```text
Every 3 hours
```

and performs an initial check when the application starts.

---

# 17. Alert Deduplication

The proactive alert service prevents repeated alerts for the same condition within the configured deduplication window.

This avoids creating the same alert every time the poller runs.

A subsequent check can return:

```text
status: deduplicated
alerts_created: 0
```

when an equivalent active alert already exists.

---

# 18. Groq LLM Verification

Before testing ORCA's full LLM path, verify that the Groq SDK is installed:

```powershell
uv run python -c "from groq import Groq; print('GROQ SDK OK')"
```

Verify configuration without exposing the API key:

```powershell
uv run python -c "import os; from dotenv import load_dotenv; load_dotenv('../.env'); print('GROQ KEY:', 'SET' if os.getenv('GROQ_API_KEY') else 'MISSING'); print('GROQ MODEL:', os.getenv('GROQ_MODEL','MISSING'))"
```

Expected:

```text
GROQ KEY: SET
GROQ MODEL: llama-3.3-70b-versatile
```

The actual ORCA provider is implemented as:

```text
backend/app/orchestrator/core.py
```

with:

```text
GroqProvider
```

---

# 19. Safety vs Fishing Yield

ORCA deliberately keeps these two scores separate.

## Safety Score

Based on factors such as:

- Weather risk
- Waves
- Warnings
- Geospatial boundary risk
- Safety constraints

## Fishing Yield Score

Based on factors such as:

- PFZ likelihood
- SST
- Chlorophyll
- Historical trends

They are **never blended into one score**.

This prevents a potentially productive fishing location from being presented as safe when it is not.

---

# 20. Deterministic Safety + LLM Explanation

The prototype follows an important design principle:

```text
Real Data
   ↓
Deterministic Calculation
   ↓
Safety Decision
   ↓
LLM Explanation
```

The LLM should explain evidence and communicate the result naturally.

It should not override deterministic geospatial safety calculations.

This is particularly important for safety-critical scenarios.

---

# 21. Demo Flow for Presentation

Recommended SIH demo sequence:

### Step 1 — Show the fisherman scenario

Say:

> "A fisherman near Rameswaram wants to know whether he is close to the maritime boundary."

### Step 2 — Ask the API

Use:

```text
Am I near the international maritime boundary?
```

### Step 3 — Show real geospatial evidence

Point out:

```text
Distance ≈ 0.49 km
Source = Marine Regions World EEZ v12
Confidence = 1.0
```

### Step 4 — Show the proactive system

Explain:

> "The fisherman doesn't have to continuously ask ORCA. ORCA can monitor a saved frequent fishing zone in the background."

### Step 5 — Show the poller

Open:

```text
GET /api/v1/alerts/poller/status
```

Show:

```text
running: true
interval: 10800 seconds
last_run_at: ...
last_error: null
```

### Step 6 — Show the alert

Open:

```text
GET /api/v1/alerts/active
```

Show the Tamil RED alert.

### Step 7 — Explain the architecture

Emphasize:

```text
Orchestrator
+
Real Data Tools
+
PostGIS
+
Deterministic Safety
+
Groq LLM
+
Proactive Alerts
```

---

# 22. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | API health |
| POST | `/api/v1/experience/query` | Main ORCA experience query |
| POST | `/api/v1/alerts/check` | Run geofence alert check |
| GET | `/api/v1/alerts/active` | Retrieve active alerts |
| GET | `/api/v1/alerts/zones` | Retrieve frequent zones |
| GET | `/api/v1/alerts/poller/status` | Background poller status |

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

# 23. Testing

Run the backend tests:

```powershell
uv run pytest backend/tests -v
```

The test suite covers the prototype's core geofence and API behavior.

---

# 24. Current Prototype Boundaries

This is a **demo prototype**, not a production maritime safety system.

Current limitations include:

- Frequent zones are stored explicitly rather than continuously receiving GPS.
- External SMS/push delivery is not yet connected.
- Voice STT/TTS integration is not the primary validated demo path yet.
- Authority and researcher experiences are lighter than the fisherman journey.
- The proactive poller uses a simple application-level background loop.
- Advanced learning/RAG is planned for a later phase.
- Production infrastructure such as Kubernetes, Kafka, Redis, and Celery is intentionally not required for this prototype.

---

# 25. Roadmap

Future phases can add:

### Voice

- Tamil STT
- Tamil TTS
- Hindi
- Telugu
- Malayalam

### Data

- INCOIS PFZ
- Copernicus SST
- Chlorophyll
- IMD weather
- Tide and wave information

### Intelligence

- RAG with pgvector
- Feedback learning
- Strategy optimization
- Historical fishing patterns
- Domain-specific agents

### Location

- Live GPS
- AIS
- Dynamic geofencing
- Expanded IMBL/EEZ/MPA boundaries

### Alerts

- Push notifications
- SMS
- IVRS
- Mobile application

### Interfaces

- Fisherman mobile/voice interface
- Authority district dashboard
- Researcher analysis dashboard

---

# 26. Core Design Principles

ORCA follows these principles:

1. **Real data over fake demo data**
2. **Deterministic safety decisions**
3. **LLM for synthesis and explanation**
4. **Safety and fishing yield remain separate**
5. **Tool-driven orchestration**
6. **Source and timestamp visibility**
7. **Multilingual by design**
8. **Proactive alerts without requiring a user query**
9. **Simple MVP infrastructure**
10. **Production-ready architecture without unnecessary production complexity**

---

# 27. Demo Status

### Current working prototype

```text
✅ FastAPI backend
✅ Supabase PostgreSQL
✅ PostGIS
✅ Marine Regions EEZ data
✅ EEZ geospatial query
✅ Real PostGIS distance calculation
✅ Frequent fishing zones
✅ Proactive geofence service
✅ Background alert poller
✅ Tamil proactive alert generation
✅ Alert persistence
✅ Alert deduplication
✅ ORCA orchestrator
✅ Groq provider integration
✅ Golden Schema
✅ Automated tests
```

### In progress / future

```text
🔄 Full Tamil voice journey
🔄 External SMS / push delivery
🔄 Complete researcher dashboard
🔄 Complete authority dashboard
🔄 Additional marine/weather live sources
🔄 RAG + learning loop
🔄 GPS/AIS integration
```

---

# 28. License / Data Attribution

The Marine Regions World EEZ dataset is distributed under its applicable data license.

Keep the original EEZ dataset license file with the project:

```text
LICENSE_EEZ_v12.txt
```

Check the dataset's license terms before redistributing the source geospatial data.

---

## ORCA

**Ocean Risk & Catch Advisor**

A demo prototype for safer, smarter, multilingual decision support for India's marine ecosystem.

# 29. Final Architecture

The following is the final ORCA architecture for the demo prototype...

![ORCA Final Architecture](docs/architecture-final.png)