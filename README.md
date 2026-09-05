# ORCA — Ocean Risk & Catch Advisor

> AI for Safer Seas, Better Catches

ORCA is a voice-first, multilingual, multi-agent AI platform for the Tamil Nadu marine ecosystem. It is designed to help fishermen, researchers, and coastal authorities make safer, evidence-based decisions using live marine, weather, and geospatial data.

This README tracks the implementation roadmap and the current status of the **Demo MVP**.

---

## 1. Demo MVP Goal

The first working demo is intentionally narrow.

A fisherman asks:

> **“Is it safe to fish tomorrow near Rameswaram?”**

The target end-to-end flow is:

```text
User Query
   ↓
Experience API
   ↓
ORCA Orchestrator
   ↓
Tool Selection
   ├── Marine Data Tool → Live Copernicus data
   └── Geospatial Tool → PostGIS EEZ / IMBL check
   ↓
Data Fusion
   ↓
Decision Engine
   ├── Safety Score
   └── Fishing Yield Score
   ↓
Synthesis
   ↓
Text Response
   ↓
Bare Web Page
```

The demo must use real tool calls and real data wherever the source is configured. Missing upstream sources must be represented as explicit `UNAVAILABLE` states. Fake values and fabricated safety answers are not allowed.

---

# 2. Current Implementation Status

## Foundation

| Area | Status |
|---|---|
| Repository scaffold | ✅ Done |
| FastAPI backend | ✅ Done |
| Health endpoint | ✅ Done |
| Experience query endpoint | ✅ Done |
| Golden Schema | ✅ Done |
| Tool layer interfaces | ✅ Done |
| Marine tool interface | ✅ Done |
| Weather tool interface | ✅ Done |
| Geospatial tool interface | ✅ Done |
| Live context layer | ✅ Done |
| Supabase DB connection configuration | ✅ Available |
| PostGIS extension | ❌ Missing |
| EEZ dataset downloaded | ✅ Done |
| EEZ imported into PostGIS | ❌ Not done |
| Real Rameswaram EEZ query | ❌ Blocked by PostGIS |
| Copernicus CLI | ✅ Installed |
| Copernicus live query | ⚠️ Not proven |
| Weather/SACHET live source | ❌ Not configured |
| Authoritative IMBL geometry | ❌ Not configured |

The current deterministic test suite has passed:

```text
6 passed, 1 warning
```

The system intentionally returns structured unavailable states instead of fabricating marine, weather, EEZ, or IMBL data.

---

# 3. Demo MVP — Remaining Stages

The Demo MVP is built in the following order.

## MVP-1 — Agentic Orchestrator Routing

**Priority: CRITICAL**

The orchestrator must demonstrate genuine agentic behavior rather than a fixed pipeline.

### Required

- LangGraph state
- Experience API → Orchestrator
- Interpret fishing-safety intent
- Dynamically select tools
- Route to at least:
  - Geospatial Tool
  - Marine Data Tool
- Execute selected tools
- Return structured tool results
- Maintain execution state
- Log selected tools for demo/debug proof
- Avoid a hardcoded sequence that always executes every tool

### Definition of Done

```text
User Query
   ↓
Orchestrator
   ↓
Chooses:
   ├── Geospatial
   └── Marine
   ↓
Results returned
```

Status: ⏳ **Not started — waiting for live Task 2 foundation**

---

# 4. MVP-2 — IMBL / EEZ Geofence

**Priority: CRITICAL**

This is the most important geospatial/human-stakes feature in the demo.

## EEZ

The real World EEZ v12 dataset has been downloaded.

Current files:

```text
data/
└── geospatial/
    └── World_EEZ_v12_20231025_gpkg/
        ├── eez_boundaries_v12.gpkg
        ├── eez_v12.gpkg
        └── LICENSE_EEZ_v12.txt
```

Source:

```text
Flanders Marine Institute
World EEZ v12
2023-10-25
```

### Required

- Enable PostGIS in Supabase
- Inspect the GeoPackage layers
- Import the correct EEZ layer
- Validate geometry
- Create spatial index
- Store source/version metadata
- Perform real point-in-polygon query
- Perform route-vs-EEZ intersection/proximity query

Demo reference location:

```text
Rameswaram
Latitude:  9.2876
Longitude: 79.3129
```

PostGIS coordinates must use:

```text
longitude latitude
79.3129 9.2876
```

### IMBL

The International Maritime Boundary Line must NOT be fabricated or approximated.

Until an authoritative geometry/source is available:

```text
IMBL = UNAVAILABLE
reason = authoritative_geometry_not_configured
```

Status: 🔴 **Blocked by missing PostGIS extension**

---

# 5. MVP-3 — Synthesis and Decision

**Priority: CRITICAL**

Once the orchestrator and live tools work, build the first complete text answer.

The synthesis layer must combine:

- Marine evidence
- Weather evidence, when available
- Geofence evidence
- Data quality/confidence
- Decision Engine outputs

## Two scores must always remain separate

### Safety Score

Based on safety-related evidence such as:

- Weather risk
- Waves/ocean conditions when available
- Warnings
- Geofencing
- Restricted/prohibited zones

### Fishing Yield Score

Based on fishing-related evidence such as:

- PFZ likelihood
- SST
- Chlorophyll
- Historical trends when available

**Safety and fishing yield must never be blended into one score.**

The final response should expose:

```text
Decision: GO / CAUTION / AVOID

Safety Score: XX/100
Fishing Yield Score: XX/100

Geofence:
    EEZ: ...
    IMBL: ...

Evidence:
    ...

Source:
    ...

Source Timestamp:
    ...

Confidence:
    ...
```

The decision math should be deterministic.

The LLM should explain the evidence rather than inventing the underlying decision.

Status: ⏳ **Not started**

---

# 6. MVP-4 — Bare Web Page

**Priority: CRITICAL**

Build the smallest possible real web interface.

It does NOT need to be visually polished yet.

The page should:

1. Accept/display the Rameswaram demo query
2. Call the FastAPI backend
3. Display the response
4. Display Safety Score
5. Display Fishing Yield Score
6. Display GO / CAUTION / AVOID
7. Display EEZ / IMBL geofence result
8. Display evidence
9. Display source
10. Display source timestamp
11. Display confidence
12. Display loading/error states

Target:

```text
Next.js
   ↓
FastAPI
   ↓
ORCA
```

Status: ⏳ **Not started**

---

# 7. Demo MVP Definition of Done

The Demo MVP is complete only when all of the following are true:

### Agentic

- [ ] Orchestrator receives the query
- [ ] Orchestrator dynamically selects tools
- [ ] At least Geospatial + Marine tools are routed
- [ ] Tool selection can be demonstrated/logged
- [ ] No fixed hardcoded final answer

### Live Data

- [ ] Real Supabase PostgreSQL connection
- [ ] PostGIS enabled
- [ ] Real EEZ data imported
- [ ] Real PostGIS spatial query
- [ ] Real Copernicus query OR truthful unavailable state
- [ ] No fabricated marine data
- [ ] No fabricated weather data
- [ ] No fabricated IMBL

### Decision

- [ ] Safety Score exists
- [ ] Fishing Yield Score exists
- [ ] Scores remain separate
- [ ] GO / CAUTION / AVOID decision exists
- [ ] Decision is deterministic
- [ ] LLM only explains evidence

### Response

- [ ] Source shown
- [ ] Timestamp shown
- [ ] Confidence shown
- [ ] Geofence result shown
- [ ] Evidence shown

### Frontend

- [ ] Bare web page works
- [ ] FastAPI is called for real
- [ ] Real result is displayed
- [ ] Loading state works
- [ ] Error state works

---

# 8. Work Completed So Far

## Task 1 — FastAPI Foundation

### Completed

- FastAPI application created
- `GET /api/v1/health`
- `POST /api/v1/experience/query`
- Demo fisherman/Rameswaram request contract
- Golden Schema models
- Initial tests

Status: ✅ **DONE**

---

## Task 2 — Tool Layer + Live Data Foundation

### Completed

Created:

```text
__init__.py
base.py
marine.py
weather.py
geospatial.py
live_context.py
test_tool_layer.py
import_geospatial_data.py
task-2.md
```

Modified:

```text
main.py
golden.py
pyproject.toml
README.md
.env.example
.gitignore
```

### Completed

- Tool interfaces established
- Marine tool created
- Weather tool created
- Geospatial tool created
- Live context layer created
- Structured unavailable states
- EEZ importer created
- EEZ dataset downloaded
- Copernicus CLI installed
- Existing deterministic tests pass

### Not Completed

- PostGIS extension
- EEZ import
- Real EEZ spatial query
- Proven Copernicus live fetch
- Official live weather source

Status: 🟡 **FOUNDATION DONE / LIVE INTEGRATION BLOCKED**

---

# 9. Immediate Next Step

Before implementing any new ORCA feature:

## Step 1 — Enable PostGIS in Supabase

Verify:

```sql
SELECT PostGIS_Version();
```

Expected:

```text
PostGIS version returned
```

Then:

## Step 2 — Import EEZ

Import:

```text
data/geospatial/World_EEZ_v12_20231025_gpkg/eez_boundaries_v12.gpkg
```

or the correct layer identified from:

```text
eez_v12.gpkg
```

Do not guess which layer is correct.

## Step 3 — Test Rameswaram

Run a real PostGIS query for:

```text
9.2876, 79.3129
```

## Step 4 — Re-run live context

```powershell
cd C:\Users\DEVANSH\Desktop\orca\backend
.\.venv\Scripts\Activate.ps1
python scripts/test_live_context.py
```

## Step 5 — Only after Task 2 passes

Move to:

```text
MVP-1 — Orchestrator Routing
```

---

# 10. Post-Demo Roadmap

These features are intentionally **not required before the first Demo MVP**.

## Phase 2 — Product Expansion

### 5. Ocean Analytics Agent

- Marine interpretation
- SST/chlorophyll/PFZ analysis
- Fishing opportunity assessment

Status: ⏳

### 6. Visualization + Conversation Agent

- Map output
- Human-readable explanation
- Conversation-aware responses

Status: ⏳

### 7. Voice / Language Interface

Target flow:

```text
Tamil Speech
    ↓
Groq Whisper Large v3 Turbo
    ↓
Language Detection
    ↓
Normalization / Translation
    ↓
ORCA
    ↓
Response Translation
    ↓
Tamil TTS
```

Target languages:

- Tamil
- Hindi
- English
- Malayalam-ready
- Telugu-ready

Status: ⏳

### 8. Proactive Alerts

Background process:

```text
Scheduled Alert Poller
        ↓
Fetch Latest Data
        ↓
Hazard Check
        ↓
Decision / Threshold
        ↓
Push Alert
```

Possible channels:

- Mobile notification
- SMS/WhatsApp
- In-app alert

The system must be user-independent: a fisherman should receive a warning even without asking a question.

Status: ⏳

### 9. Feedback

- Next-day feedback
- Explicit user feedback
- Implicit return visits
- Accuracy tracking

Status: ⏳

---

# 11. Authority Journey

After the core fisherman demo:

```text
Authority Dashboard
        ↓
District
        ↓
Harbours
        ↓
Active Warnings
        ↓
Risk / Geofence Status
```

Status: ⏳

---

# 12. Researcher Journey

After the core demo:

```text
Researcher
    ↓
Region Selection
    ↓
SST / Chlorophyll
    ↓
Trend Map
    ↓
Analysis
```

Target technology:

- Next.js
- TypeScript
- deck.gl
- MapLibre GL JS

Status: ⏳

---

# 13. Advanced Roadmap

After the Demo MVP and core product journeys:

- What-if analysis
- Route safety expansion
- Historical data
- pgvector RAG
- Accuracy tracking
- Learning/analytics loop
- Strategy optimizer
- Crowd sensing
- Domain-specific agents
- SMS / IVRS
- Native mobile app
- Malayalam
- Telugu
- Wider geographic coverage
- Advanced ML predictions
- Continuous optimization

---

# 14. Production Roadmap

Production-scale infrastructure is intentionally deferred until the demo proves the core architecture.

Future options include:

- Domain agents
- Strategy optimizer
- Scalable background processing
- SMS/IVRS
- Native mobile
- Expanded multilingual support
- Advanced ML
- Wider geographic coverage
- Continuous optimization

Do NOT introduce Kubernetes, Kafka, Redis, Celery, Airflow, microservices, or a separate vector database merely for the Demo MVP.

For the current MVP:

```text
FastAPI
PostgreSQL + PostGIS
Supabase
Next.js
LangGraph
Copernicus Marine
APScheduler
```

is sufficient.

---

# 15. Data Integrity Rules

ORCA follows these rules throughout development:

### Never fabricate live data

If a source is unavailable:

```text
status = UNAVAILABLE
```

with an explicit reason.

### Never fabricate IMBL

An approximate boundary must never be presented as an authoritative IMBL.

### Preserve provenance

Every data result should expose, where applicable:

```text
Source
Timestamp
Location
Variables
Units
Quality
Confidence
```

### Track freshness

Live data should retain source and fetch timestamps.

### Safety and yield remain separate

Never collapse:

```text
Safety Score
```

and:

```text
Fishing Yield Score
```

into one blended number.

---

# 16. Demo Scenario

Primary demonstration:

```text
User:
"Is it safe to fish tomorrow near Rameswaram?"
```

Location:

```text
Latitude:  9.2876
Longitude: 79.3129
```

The system should eventually demonstrate:

```text
User
 ↓
FastAPI
 ↓
ORCA Orchestrator
 ↓
Marine Tool ─────────────→ Copernicus
 ↓
Geospatial Tool ─────────→ PostGIS / EEZ
 ↓
Data Fusion
 ↓
Decision Engine
 ├── Safety Score
 └── Fishing Yield Score
 ↓
Synthesis
 ↓
Web Response
```

The final demo should be repeatable, explainable, and based on real tool execution.

---

# 17. Current Status Summary

```text
ORCA DEMO MVP
══════════════════════════════════════════════

Foundation
████████████████████████████████  DONE

FastAPI
████████████████████████████████  DONE

Golden Schema
████████████████████████████████  DONE

Tool Layer
████████████████████████████████  DONE

Supabase connection
████████████████████████████████  AVAILABLE

PostGIS
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BLOCKED

EEZ import
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BLOCKED

Rameswaram geofence
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BLOCKED

Copernicus live query
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  NOT PROVEN

Orchestrator routing
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  NEXT

Synthesis
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  NEXT

Bare Web
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  NEXT
```

---

## Immediate execution order

```text
1. Enable PostGIS
        ↓
2. Import World EEZ v12
        ↓
3. Verify Rameswaram spatial query
        ↓
4. Verify Copernicus live data
        ↓
5. Complete Task 2
        ↓
6. MVP-1 Orchestrator Routing
        ↓
7. MVP-2 Geofence
        ↓
8. MVP-3 Synthesis
        ↓
9. MVP-4 Bare Web
        ↓
10. DEMO MVP COMPLETE
```

**Current stop point:** Task 2 live infrastructure validation.

Do not proceed to the next stage until the current stage has been verified with real data.
