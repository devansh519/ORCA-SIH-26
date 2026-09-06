# 🌊 ORCA — Ocean Risk & Catch Advisor

> **Smart India Hackathon · Problem Statement PS 26176**  
> **Demo Prototype · Live Data · Multilingual Marine Decision Support**

ORCA is a voice-first, multilingual marine decision-support platform for **fishermen, marine researchers, and coastal authorities**.

The current prototype demonstrates a working Rameswaram scenario using **live weather + marine data, PostGIS geospatial reasoning, deterministic safety decisions, proactive alerts, and a connected web dashboard**.

---

## 🎯 1. Current Objective

| Area | Current Focus |
|---|---|
| Primary user | Fisherman |
| Demo location | Rameswaram |
| Main scenario | Fishing safety + EEZ boundary awareness |
| Backend | FastAPI |
| Database | Supabase PostgreSQL + PostGIS |
| Live weather | Open-Meteo |
| Live marine | Open-Meteo Marine API |
| Geospatial data | Marine Regions World EEZ v12 |
| LLM | Groq · `openai/gpt-oss-120b` |
| Frontend | Static HTML dashboard |
| Alert system | Background geofence poller |

---

# ✅ 2. What Is Working

| Feature | Status | Notes |
|---|:---:|---|
| FastAPI backend | ✅ | Live REST API |
| Supabase PostgreSQL | ✅ | Connected |
| PostGIS | ✅ | Spatial queries working |
| EEZ dataset | ✅ | Marine Regions World EEZ v12 |
| EEZ distance check | ✅ | Real PostGIS calculation |
| EEZ containment | ✅ | Inside / outside check |
| ORCA orchestrator | ✅ | Intent → tool selection → execution |
| Weather tool | ✅ | Live Open-Meteo data |
| Marine tool | ✅ | Live Open-Meteo data |
| Dynamic location resolution | ✅ | Place name → coordinates |
| Safety Decision Engine | ✅ | Deterministic |
| Fishing Yield Score | ✅ | Kept separate from safety |
| Question-specific answers | ✅ | Wind / waves / safety / boundary |
| Source + timestamp | ✅ | Included in structured response |
| Quality + confidence | ✅ | Included in response |
| Proactive geofence alerts | ✅ | Saved frequent zones |
| Tamil alert generation | ✅ | RED alert flow |
| Alert persistence | ✅ | Supabase |
| Alert deduplication | ✅ | Prevents repeated alerts |
| Background poller | ✅ | 3-hour interval |
| Groq integration | ✅ | Synthesis / explanation |
| Web dashboard | ✅ | Connected to live API |
| Automated tests | ✅ | Core prototype coverage |

---

# 🧠 3. Live Reactive Query Flow

```text
User Question
      ↓
Experience API
      ↓
ORCA Orchestrator
      ↓
Intent + Context
      ↓
Dynamic Tool Selection
      ↓
┌────────────┬────────────┬─────────────┐
│  Weather   │   Marine   │ Geospatial  │
│ Open-Meteo │ Open-Meteo │  PostGIS    │
└────────────┴────────────┴─────────────┘
      ↓
Evidence Fusion
      ↓
Deterministic Decision Engine
      ↓
┌──────────────────┬──────────────────┐
│   Safety Score   │  Yield Score     │
│   Weather/Risk   │  Marine Factors  │
└──────────────────┴──────────────────┘
      ↓
Question-Specific Response
      ↓
Web Dashboard / Voice
```

### Dynamic routing

| User question | Tools selected |
|---|---|
| “What is the wind speed tomorrow?” | Weather |
| “What are the wave conditions?” | Marine |
| “Is it safe to go fishing tomorrow?” | Weather + Marine + Geospatial |
| “Am I inside the EEZ?” | Geospatial |
| “How far is the EEZ boundary?” | Geospatial |

> **Important:** Previous conversation context must not change the intent of the current question.

---

# ⚓ 4. Geospatial + PostGIS

### Current data

| Item | Value |
|---|---|
| Dataset | Marine Regions World EEZ v12 |
| Database | Supabase PostgreSQL |
| Spatial extension | PostGIS |
| Application table | `gis.eez_boundaries` |
| Geometry | Polygon / MultiPolygon |
| CRS | EPSG:4326 |
| Imported features | 285 |
| Demo location | Rameswaram |
| Demo coordinates | `9.2876, 79.3129` |

### Example operation

```text
Rameswaram
    ↓
PostGIS spatial query
    ↓
EEZ geometry
    ↓
Distance / containment
    ↓
Structured geospatial evidence
```

The geospatial result includes **status, distance, confidence, quality, source, and timestamp**.

---

# 🚨 5. Proactive Geofence Alert

ORCA does not require the fisherman to continuously ask questions.

```text
Saved Frequent Zone
        ↓
Background Alert Poller
        ↓
Geofence Alert Service
        ↓
PostGIS / EEZ Check
        ↓
Safety Threshold
        ↓
Tamil RED Alert
        ↓
Supabase proactive_alerts
```

### Demo zone

| Property | Value |
|---|---|
| Name | Rameswaram Demo Zone |
| Latitude | `9.2876` |
| Longitude | `79.3129` |
| Radius | `1.0 km` |
| Language | Tamil |
| Active | `true` |
| Polling interval | 3 hours |

### Useful endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/alerts/zones` | Saved frequent zones |
| `POST` | `/api/v1/alerts/check` | Run alert check |
| `GET` | `/api/v1/alerts/active?user_id=demo-fisherman` | Active alerts |
| `GET` | `/api/v1/alerts/poller/status` | Poller status |

`delivery_status = created` means the alert was **generated and persisted**. External SMS/push delivery is not connected yet.

---

# 🛡️ 6. Safety vs Fishing Yield

ORCA deliberately keeps these decisions separate.

| Safety | Fishing Yield |
|---|---|
| Wind risk | SST |
| Wave conditions | Chlorophyll |
| Weather warnings | PFZ likelihood |
| Boundary proximity | Historical indicators |
| Safety constraints | Marine productivity |

### Design rule

> **A productive fishing location must never make an unsafe trip appear safe.**

---

# 🤖 7. Intelligence Architecture

| Layer | Responsibility |
|---|---|
| **Orchestrator** | Intent, context, tool selection, workflow |
| **Data Tools** | Weather, marine, geospatial evidence |
| **Fusion** | Normalize and combine evidence |
| **Decision Engine** | Deterministic safety + yield assessment |
| **Groq LLM** | Natural-language synthesis / explanation |
| **Response Layer** | Structured + user-facing response |
| **Alert System** | Background hazard detection |

### Core principle

```text
Real Data
   ↓
Deterministic Calculation
   ↓
Safety Decision
   ↓
LLM Explanation
```

The LLM does **not** override deterministic geospatial safety calculations.

---

# 🏗️ 8. Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI + Uvicorn |
| Validation | Pydantic |
| Database | PostgreSQL |
| Managed DB | Supabase |
| Spatial | PostGIS |
| HTTP | httpx |
| Orchestration | LangGraph + ORCA workflow |
| LLM | Groq |
| Weather | Open-Meteo |
| Marine | Open-Meteo Marine API |
| Geospatial | Marine Regions World EEZ v12 |
| Testing | pytest |
| Frontend | HTML + React UMD + Tailwind CDN |

---

# 📁 9. Project Structure

```text
orca/
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
│   │   └── main.py
│   └── tests/
├── data/
├── docs/
├── frontend/
├── scripts/
├── .env
├── .env.example
├── pyproject.toml
└── README.md
```

---

# ⚙️ 10. Environment

Create `.env` in the repository root:

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=

GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

WEATHER_PROVIDER=open_meteo
MARINE_PROVIDER=open_meteo

OPEN_METEO_WEATHER_URL=https://api.open-meteo.com/v1/forecast
OPEN_METEO_MARINE_URL=https://marine-api.open-meteo.com/v1/marine
```

> 🔒 **Never commit `.env`.** Use `.env.example` for shared configuration.

---

# ▶️ 11. Start ORCA

## Step 1 — Install dependencies

From the repository root:

```powershell
uv sync
```

Optional Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## Step 2 — Start Backend

### Terminal 1

```powershell
cd C:\Users\DEVANSH\Desktop\orca\backend

$env:PYTHONPATH="."
$env:WEATHER_PROVIDER="open_meteo"
$env:MARINE_PROVIDER="open_meteo"

uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Backend URLs

| Service | URL |
|---|---|
| API | `http://127.0.0.1:8000` |
| Swagger | `http://127.0.0.1:8000/docs` |
| Health | `http://127.0.0.1:8000/api/v1/health` |

---

## Step 3 — Start Frontend

### Terminal 2

```powershell
cd C:\Users\DEVANSH\Desktop\orca\frontend

python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500/orca_dashboard.html
```

The dashboard connects to the FastAPI backend on port `8000`.

---

# 🧪 12. Quick Demo

After starting both servers:

### 1. Weather

```text
What is the wind speed tomorrow near Rameswaram?
```

### 2. Marine

```text
What are the wave conditions tomorrow near Rameswaram?
```

### 3. Safety

```text
Is it safe to go fishing tomorrow near Rameswaram?
```

### 4. Boundary

```text
Am I inside the EEZ near Rameswaram?
```

### 5. Tamil

```text
நாளைக்கு ராமேஸ்வரத்தில் மீன்பிடிக்க போகலாமா?
```

---

# 🔌 13. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | API health |
| `POST` | `/api/v1/experience/query` | Main ORCA query |
| `POST` | `/api/v1/alerts/check` | Trigger geofence check |
| `GET` | `/api/v1/alerts/active` | Active alerts |
| `GET` | `/api/v1/alerts/zones` | Frequent zones |
| `GET` | `/api/v1/alerts/poller/status` | Poller status |

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

# 🧪 14. Testing

From repository root:

```powershell
uv run pytest backend/tests -v
```

Live Open-Meteo provider tests:

```powershell
uv run pytest backend/tests/test_open_meteo_provider.py -v -s
```

Live decision integration:

```powershell
cd backend
$env:PYTHONPATH="."
uv run python tests/test_live_decision_integration.py
```

---

# ⚠️ 15. Current Limitations

| Area | Current State |
|---|---|
| IMBL authoritative geometry | Not yet configured; EEZ data used for current demo |
| SMS / Push | Not connected |
| Tamil STT/TTS | Not primary validated path yet |
| Authority dashboard | Lighter implementation |
| Researcher dashboard | Lighter implementation |
| RAG / learning | Future phase |
| GPS / AIS | Future phase |
| IMD / INCOIS / Copernicus | Future integrations |
| Production infrastructure | Not yet required |

> This is a **demo decision-support prototype**, not a production maritime safety authority.

---

# 🚀 16. Next Priorities

| Priority | Work |
|:---:|---|
| **1** | Validate all reactive + boundary question types |
| **2** | Reduce response latency |
| **3** | Complete Tamil STT → ORCA → TTS |
| **4** | Add IMD / INCOIS / Copernicus sources |
| **5** | Complete authority dashboard |
| **6** | Complete researcher analysis |
| **7** | Add SMS / Push / IVRS |
| **8** | Add RAG + feedback learning |
| **9** | Add GPS / AIS + expanded geofencing |

### Performance direction

```text
Current
Weather ─┐
Marine ──┼→ Decision → Response
Geo ─────┘

Next
Weather ─┐
Marine ──┼→ Parallel Execution → Fast Decision
Geo ─────┘                         ↓
                            Optional LLM
```

Focus: **parallel tool execution, connection reuse, short-lived caching, and selective LLM usage** without adding unnecessary infrastructure.

---

# 🏆 17. Demo Readiness

| Capability | Status |
|---|:---:|
| Live backend | 🟢 |
| Live weather | 🟢 |
| Live marine | 🟢 |
| PostGIS geospatial reasoning | 🟢 |
| Dynamic tool routing | 🟢 |
| Separate safety / yield scores | 🟢 |
| Question-specific answers | 🟢 |
| Proactive alert flow | 🟢 |
| Web dashboard | 🟢 |
| Tamil proactive alerts | 🟢 |
| Full voice journey | 🟡 |
| External notifications | 🟡 |
| Authority / researcher experiences | 🟡 |
| RAG / learning | 🔵 |
| GPS / AIS | 🔵 |

**Legend:** 🟢 Working · 🟡 In progress · 🔵 Future

---

# 💡 Core Design Principles

1. **Real data over fake demo data**
2. **Deterministic safety decisions**
3. **LLM for synthesis and explanation**
4. **Safety and fishing yield remain separate**
5. **Dynamic tool-driven orchestration**
6. **Source and timestamp visibility**
7. **Multilingual by design**
8. **Proactive alerts without requiring a query**
9. **Simple MVP infrastructure**
10. **Production-ready architecture without unnecessary complexity**

---

## 🌊 ORCA

**Ocean Risk & Catch Advisor**

> **Safer seas. Smarter decisions. Multilingual access.**
