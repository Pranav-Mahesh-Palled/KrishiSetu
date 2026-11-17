# KrishiSetu (ಕೃಷಿಸೇತು / कृषीसेतू)

> **Multilingual Agritech & Harvest Arbitrage Advisory Assistant**  
> *Track 2 — Climate, Resource Infrastructure & Global Supply Resilience*  
> *Challazo IDEA//FORGE Hackathon 2026*

---

## 🌾 Overview

Smallholder farmers across India lose 15%–30% of their net seasonal income during harvest and sale due to two major blind spots:
1. **Hyper-Local Spoilage Risk:** Unseasonal rainfall and high soil moisture rot harvested produce before it reaches the market.
2. **Mandi Price Opacity:** Wholesale prices across nearby APMC mandis vary by ₹400–₹1,200/quintal, yet farmers lack distance-adjusted transport and spoilage calculations to identify the true highest-net-profit mandi.

**KrishiSetu** bridges this gap by unifying hyper-local weather risk analysis with a deterministic transport-and-spoilage arbitrage engine and multilingual voice advisory in **English, Kannada (`kn`), Hindi (`hi`), and Marathi (`mr`)**.

---

## 🏗️ Repository Architecture

```text
KrishiSetu/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── arbitrage_engine.py    # Haversine road-adjusted transport & spoilage engine
│   │   │   └── weather_risk.py        # 72h harvest risk classification engine
│   │   ├── __init__.py
│   │   ├── database.py                # SQLite database session & engine
│   │   ├── models.py                  # SQLAlchemy ORM schemas
│   │   ├── seed.py                    # Idempotent seed data for 10 crops & 5 demo presets
│   │   └── main.py                    # FastAPI application & endpoints
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_engines.py            # Unit tests for calculation engines & endpoints
│   ├── requirements.txt
│   └── .venv/
├── frontend/                          # React + Vite + Tailwind frontend (Phase 3)
│   └── README.md
├── spec.md                            # Comprehensive product specification
├── .env.example
├── .gitignore
└── README.md
```

---

## 🚀 Implementation Status

### Phase 1: Scaffolding, Database & Deterministic Engines (Complete)
- [x] **Monorepo Scaffolding:** Clean backend/frontend structure, virtual environment, and configuration.
- [x] **Database & Models:** SQLite (`krishisetu.db`) with exact schemas: `mandi_prices_cache`, `weather_cache`, `crop_profiles`.
- [x] **Seed Data:** 10 crops with multilingual names (EN, KN, HI, MR), AGMARKNET mappings, and 5 demo presets with verified snapshot records.
- [x] **Deterministic Calculation Engines:** Road-adjusted Haversine distance, transit perishability spoilage rates, net realizable prices, and 72-hour weather risk classification.
- [x] **Phase 1 Endpoints:** `GET /api/health` and `GET /api/presets`.

### Phase 2: External Data Integrations & Gemini AI Layer (Complete)
- [x] **Open-Meteo Integration:** Async geocoding and 7-day forecast + topsoil moisture (`soil_moisture_0_to_7cm`, `relative_humidity_2m`) with 3-hour SQLite caching and deterministic risk evaluation.
- [x] **AGMARKNET Integration:** Proximity selection (nearest 5 mandis within 150 km) querying OGD India (`data.gov.in`) with live 3-hour SQLite caching and graceful zero-error fallback to `verified_snapshot` records.
- [x] **Gemini AI Advisory:** Pydantic structured output with strict grounding rules preventing hallucinated prices, natural multilingual output (`en`, `kn`, `hi`, `mr`), and deterministic fallback templates.
- [x] **Conversational Q&A & Voice:** `POST /api/chat` grounded in analysis context, and `POST /api/tts` streaming regional MP3 audio via `gTTS`.
- [x] **Phase 2 Endpoints:** `POST /api/analyze`, `POST /api/chat`, and `POST /api/tts`.
- [x] **Test Verification:** 17 of 17 tests passing across `backend/tests/test_engines.py` and `backend/tests/test_phase2.py`.

### Phase 3: Mobile-First Frontend Dashboard & Voice Interface (Complete)
- [x] **React + Vite + TypeScript:** Modern, responsive frontend scaffolded inside `frontend/` with Tailwind CSS and Lucide Icons.
- [x] **Agrarian Header & Language Switcher:** Instant toggle between English, ಕನ್ನಡ, हिन्दी, and मराठी with instant re-analysis.
- [x] **1-Click Hackathon Presets & Control Bar:** Instant evaluation of all 5 demo presets (Belagavi, Kolar, Nashik, Haveri, Pune) with auto-load on first launch, plus custom location and crop search.
- [x] **Hero AI Decision Action Plan Card:** Highlights top target mandi, net price realization, total profit spread, and transit quality precautions.
- [x] **Dual Voice Audio Engine:** Browser-native `SpeechSynthesis` with automatic seamless fallback to backend `/api/tts` MP3 audio stream for regional Indian languages.
- [x] **Harvest Risk Banner & 7-Day Weather Strip:** Color-coded 72h risk alert (`SAFE_WINDOW`, `HARVEST_WITHIN_48H`, `HIGH_SPOILAGE_ALERT`) with soil moisture and daily forecast strip.
- [x] **Mandi Net-Profit Comparison Table & Visual Bar Chart:** Horizontal bar comparison contrasting modal sticker price vs. net realizable price across neighboring markets.
- [x] **Interactive Voice & Text Q&A Drawer:** Grounded Q&A connected to `/api/chat` with browser `SpeechRecognition` voice input in `kn-IN`, `hi-IN`, `mr-IN`, and `en-IN`.
- [x] **Zero Bundling Errors:** Clean `npm run build` production bundling and full end-to-end live proxy verification.

### Phase 4: Production Single-URL Packaging & Deployment Prep (Complete)
- [x] **Unified Static Frontend Serving:** FastAPI mounts `frontend/dist/assets` at `/assets` and serves `frontend/dist/index.html` at `/` and client SPA routes.
- [x] **Strict API Path Protection:** Non-matching `/api/*` routes strictly return JSON 404 responses rather than falling back to HTML.
- [x] **Multi-Stage Dockerfile:** Stage 1 builds React Vite app on `node:20-alpine`; Stage 2 packages FastAPI backend on `python:3.11-slim` with unified static assets.
- [x] **Render Deployment Blueprint:** `render.yaml` configured for zero-downtime deployment with `/api/health` health check.
- [x] **Clean Container Context:** Comprehensive `.dockerignore` excluding `.env`, `.venv`, `node_modules`, `__pycache__`, and SQLite files.
- [x] **Production Smoke Test:** Verified end-to-end standalone serving of React HTML, CSS/JS bundles, `/api/health`, `/api/analyze`, and JSON 404 handling.

---

## 🛠️ Quickstart

### Development Mode (Separate Backend & Frontend Servers)

1. **Start Backend Server:**
   ```bash
   python -m uvicorn backend.app.main:app --port 8000 --reload
   ```
2. **Start Frontend Dev Server:**
   ```bash
   cd frontend
   npm run dev
   ```
   Open `http://localhost:5173` (proxies `/api/*` to `http://localhost:8000`).

### Production Mode (Single-URL Unified Build)

1. **Build Frontend Bundle:**
   ```bash
   cd frontend
   npm run build
   cd ..
   ```
2. **Run Standalone FastAPI (Serves both API and UI on a single URL):**
   ```bash
   python -m uvicorn backend.app.main:app --port 8000
   ```
   Open `http://localhost:8000` to access the full application on a single origin.

### Docker Container Build & Run

```bash
# Build the production image
docker build -t krishisetu .

# Run the unified container
docker run -p 8000:8000 \
  -e GEMINI_API_KEY="your_api_key" \
  -e DATA_GOV_API_KEY="your_data_gov_key" \
  krishisetu
```

---

## 🛠️ Quickstart (Backend)

### 1. Set Up Environment
```bash
# Clone the repository
cd KrishiSetu

# Create and activate virtual environment
python -m venv backend/.venv
# Windows:
backend\.venv\Scripts\activate
# Linux/macOS:
source backend/.venv/bin/activate

# Install development & test dependencies (includes pytest-socket):
pip install -r backend/requirements-dev.txt

# Or for production runtime only (used in Docker builds):
# pip install -r backend/requirements.txt
```

### 2. Run Database Migrations & Seeds
On startup, FastAPI automatically initializes `krishisetu.db` and idempotently seeds the crop profiles and mandi snapshot records.

### 3. Start Development Server
```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```
Open [http://localhost:8000/docs](http://localhost:8000/docs) to access interactive Swagger API documentation.

### 4. Run Pytest Suite
The automated test suite runs completely offline, deterministically, and with full external network protection via `pytest-socket` and temporary isolated SQLite databases:
```bash
python -m pytest backend/tests -v
```

### 5. Production Smoke Testing (Separate)
To verify end-to-end integration against a running deployment or live APIs, execute the separate standalone production smoke script:
```bash
python backend/tests/test_production_smoke.py
```
