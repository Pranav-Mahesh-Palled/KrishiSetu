# KrishiSetu (ಕೃಷಿಸೇತು / कृषीसेतू)

> **Multilingual Agritech Decision-Support & Harvest Arbitrage Engine**<br>
> *Track 2 — Climate, Resource Infrastructure & Global Supply Resilience*<br>
> *Challazo IDEA//FORGE Hackathon 2026*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4+-38B2AC?logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Tests](https://img.shields.io/badge/Tests-132%20Passing-success?logo=pytest)](backend/tests)
[![Network Isolation](https://img.shields.io/badge/pytest--socket-Active-blue)](pytest.ini)

---

## 🌾 1. Overview & Problem Statement

Smallholder and marginal farmers across India cultivate price-volatile, weather-sensitive crops such as onions, tomatoes, potatoes, green chillies, and maize. At harvest, they routinely lose **15%–30% of potential seasonal revenue** (consistent with ICAR-CIPHET post-harvest loss benchmarks and regional market volatility studies) due to two disconnected blind spots:

1. **Hyper-Local Spoilage Risk:** Regional forecasts rarely account for micro-climate precipitation spikes and volumetric topsoil moisture at the farmer's exact village coordinates during the critical 72-hour harvest window. Harvested produce left in waterlogged fields suffers fungal decay, post-harvest rot, and severe market-yard distress discounts.
2. **Mandi Price Opacity & Arbitrage Deficit:** Wholesale modal prices across neighboring APMC mandis within a 30–150 km radius frequently differ by ₹300–₹1,200 per quintal. Without transparent, road-adjusted transit distance math, haulage freight deductions, and crop-specific transit spoilage deductions, farmers sell blindly at their nearest market or accept depressed village-middleman offers.

**KrishiSetu** bridges this gap by unifying hyper-local weather risk modeling, authentic daily APMC market quotations, distance-adjusted transport economics, and grounded AI decision advisory in **English, Kannada (`kn`), Hindi (`hi`), and Marathi (`mr`)**.

---

## 🎯 2. Core Capabilities

### 🌦️ Hyper-Local Weather & Soil Risk Modeling
- **High-Resolution Geocoding & Meteorology:** Fetches 7-day precipitation volume, rain probability, temperature extremes, relative humidity, and volumetric topsoil moisture (`0–7 cm`) from Open-Meteo for the farm's exact coordinates.
- **72-Hour Harvest Window Classification:** Deterministic rules classify risk into three actionable statuses:
  - `SAFE_WINDOW` (Green): Low rain probability, low soil moisture. Favorable for immediate harvesting and drying.
  - `HARVEST_WITHIN_48H` (Amber): Impending rain window. Accelerate harvesting, clear drainage, and prepare tarpaulins.
  - `HIGH_SPOILAGE_ALERT` (Red): Heavy rain or saturated topsoil (>0.35 m³/m³). Halt open harvesting; risk of waterlogging and mold decay.

### 🚛 Net Realizable Price (Arbitrage) Engine
- **Road-Adjusted Transit Distance:** Computes geodesic Haversine distance adjusted by a standard Indian rural road winding factor of **1.30×**.
- **Haulage Freight Deductions:** Subtracts haulage freight at **₹2.50 per km per quintal** (reflecting regional commercial pickup and mini-truck rates).
- **Perishability Degradation:** Applies crop-specific transit perishability loss factors (e.g., higher for tomatoes and green chillies, moderate for onions and potatoes, low for maize) based on transit duration.
- **Net Price Ranking:** Ranks candidate APMC markets by **Net Realizable Price = Modal Price − Transport Cost − Spoilage Loss**.
- **Arbitrage Integrity Protection:** Arbitrage gain is only declared between legitimate market quotations. If comparison markets lack verified quotations or only contain estimated benchmark references, the engine marks them accordingly and suppresses speculative gain figures.

### 📊 Data Freshness & Provenance Hierarchy
KrishiSetu enforces transparency regarding data authenticity:
- **`live_api`:** Fresh quotation retrieved directly from AGMARKNET / OGD India for today's trading session.
- **`cached`:** Verified quotation cached within the 3-hour operational TTL.
- **`estimated_benchmark`:** Baseline offline reference data. Clearly labeled as an estimated benchmark in the UI. Benchmark rows are seeded with `fetched_at = NULL` to prevent misleading freshness claims and are explicitly excluded from live arbitrage calculations.
- **Safe Manual Refresh & Dual Cooldown Evaluation:** Farmers can trigger on-demand data updates with an independent 60-second server-side rate limit per provider (mandi vs. weather). Cooldown evaluation combines remaining process-local elapsed time (`time.monotonic()`) with remaining cooldown calculated from persisted SQLite timestamps (`fetched_at`). Successful refreshes retain their remaining cooldown across process restarts through persisted SQLite timestamps, while failed-attempt cooldowns (e.g. timeouts or 503s) are process-local and reset when the process restarts.

### 🧠 Grounded Multilingual AI Advisory & Deterministic Fallback
- **Deterministic Math & Grounded Gemini Advisory:** All agricultural calculations—including haulage transport deductions, transit perishability decay, and net realizable prices—are computed directly by deterministic Python logic. The frontend displays these precomputed figures directly in the UI. Google Gemini (`gemini-3.5-flash-lite`) is constrained via Pydantic structured schemas (`AIAdvisory`) to synthesize qualitative narrative advisories grounded on these metrics. This architecture mitigates numerical hallucinations, though it does not guarantee that all generated natural-language prose is entirely error-free.
- **Robust Deterministic Fallback:** If Gemini API credentials are absent, quota is exceeded, or network access is restricted, the application seamlessly activates deterministic multilingual advisory templates across English, Kannada (`kn`), Hindi (`hi`), and Marathi (`mr`) without user disruption.
- **Voice-Enabled Interface:** Regional text-to-speech synthesis (browser Web Speech API + streaming backend `gTTS` MP3 audio) and speech-to-text input in native regional dialects (`kn-IN`, `hi-IN`, `mr-IN`, `en-IN`).

---

## 🏗️ Monorepo Architecture

```text
KrishiSetu/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── ai_service.py          # Gemini 3.5 Flash-Lite advisory & deterministic templates
│   │   │   ├── arbitrage_engine.py    # Haversine distance, freight & perishability calculations
│   │   │   ├── mandi_service.py       # AGMARKNET integration, SQLite cache & refresh cooldowns
│   │   │   ├── weather_risk.py        # 72h harvest risk classification logic
│   │   │   └── weather_service.py     # Open-Meteo integration & soil moisture telemetry
│   │   ├── config.py                  # Environment configuration & demo keys
│   │   ├── database.py                # SQLite engine, sessions & table migrations
│   │   ├── main.py                    # FastAPI application, lifespan & REST endpoints
│   │   ├── models.py                  # SQLAlchemy ORM models (CropProfile, MandiCache, WeatherCache)
│   │   └── seed.py                    # Database initialization & 10 crop profiles
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                # Isolated SQLite test fixtures & harness
│   │   ├── test_audit_corrections.py  # Preset regressions & external API error resilience
│   │   ├── test_database_safety.py    # Production database read-only protection & seeder safety
│   │   ├── test_engines.py            # Road distance, haulage freight & perishability calculations
│   │   ├── test_freshness_metadata.py # Data provenance, arrival-date sorting & metadata validation
│   │   ├── test_manual_refresh.py     # 60s monotonic cooldowns & cache-bypass lifecycle
│   │   ├── test_phase2.py             # Open-Meteo, AGMARKNET, Gemini & voice test suite
│   │   ├── test_production_smoke.py   # Standalone single-URL static asset smoke test script
│   │   └── test_sqlite_migration.py   # Table-recreation migration & AUTOINCREMENT preservation
│   ├── requirements.txt               # Production backend dependencies
│   └── requirements-dev.txt           # Test dependencies (pytest, pytest-socket)
├── frontend/
│   ├── public/                        # Static SVG icons and favicon
│   ├── src/
│   │   ├── assets/                    # Static branding imagery
│   │   ├── components/
│   │   │   ├── ChatDrawer.tsx         # Multilingual grounded Q&A drawer with STT voice input
│   │   │   ├── ControlBar.tsx         # 5 preset buttons, custom query controls & refresh countdown
│   │   │   ├── Header.tsx             # Language switcher, audio playback & accessibility
│   │   │   ├── HeroAdvisoryCard.tsx   # Top recommendation, net profit spread & voice triggers
│   │   │   ├── MandiComparison.tsx    # Multi-mandi comparison table, charts & freshness badges
│   │   │   └── WeatherRiskStrip.tsx   # 72h harvest alert banner, soil moisture & 7-day forecast
│   │   ├── utils/
│   │   │   ├── freshness.ts           # Client-side freshness badge rendering utilities
│   │   │   └── speech.ts              # Web Speech API wrapper & TTS audio player
│   │   ├── api.ts                     # API client with same-origin production defaults
│   │   ├── App.tsx                    # Main dashboard container & state coordination
│   │   ├── main.tsx                   # React root entry point
│   │   └── types.ts                   # Unified TypeScript interfaces
│   ├── package.json                   # Frontend dependencies (React 19, Lucide, Tailwind)
│   ├── tsconfig.json                  # TypeScript compiler configuration
│   └── vite.config.ts                 # Vite bundler & development proxy configuration
├── .dockerignore                      # Build context exclusions
├── .env.example                       # Clean environment variable template
├── .gitignore                         # Repository hygiene definitions
├── Dockerfile                         # Multi-stage production container build
├── pytest.ini                         # Offline test configuration (--disable-socket)
├── README.md                          # Project documentation
├── render.yaml                        # Render deployment specification
├── requirements-dev.txt               # Root wrapper for development dependencies
└── spec.md                            # Complete engineering & architectural specification
```

---

## ⚡ 3. Pre-Configured Demonstration Presets

Judges can evaluate KrishiSetu instantly across 5 agricultural production zones in Karnataka and Maharashtra:

| Preset Key | Location | Crop | State | Focus Evaluation |
|---|---|---|---|---|
| `belagavi-onion` | Belagavi | Onion | Karnataka | Cross-market price spread vs. transit to Hubballi/Kolhapur |
| `kolar-tomato` | Kolar | Tomato | Karnataka | High-perishability transit loss vs. Bengaluru APMC price |
| `nashik-onion` | Nashik | Onion | Maharashtra | Major onion trading hub comparison (Lasalgaon, Pimpalgaon, Yeola) |
| `haveri-maize` | Haveri | Maize | Karnataka | Bulk grain haulage economics and low perishability decay |
| `pune-potato` | Pune | Potato | Maharashtra | Topsoil moisture sensitivity and regional mandi spreads |

---

## 🔌 4. API Endpoints

FastAPI provides an interactive OpenAPI interface at `/docs`.

| Method | Path | Description | Key Parameters |
|---|---|---|---|
| `GET` | `/api/health` | Health check & system status | None |
| `GET` | `/api/presets` | Retrieve all 5 pre-configured demo presets | None |
| `GET` | `/api/crops` | List available crop profiles and harvest thresholds | None |
| `POST` | `/api/analyze` | Run full weather risk & mandi arbitrage analysis | `location`, `crop`, `language`, `quantity_quintals`, `force_refresh` |
| `POST` | `/api/chat` | Grounded conversational Q&A on current analysis | `query`, `context`, `language` |
| `POST` | `/api/tts` | Stream synthesized audio (MP3) for regional text | `text`, `language` |

---

## 💻 5. Local Setup & Execution

### Prerequisites
- **Python:** 3.11 or higher
- **Node.js:** 20.x or higher
- **npm:** 10.x or higher

### Option A: Development Mode (Separate Frontend & Backend)

#### 1. Backend Setup
```bash
# Navigate to repository root
cd KrishiSetu

# Create and activate Python virtual environment
python -m venv backend/.venv

# Windows (PowerShell):
backend\.venv\Scripts\Activate.ps1
# Linux / macOS:
source backend/.venv/bin/activate

# Install development and testing dependencies
pip install -r backend/requirements-dev.txt

# Create local environment file from example template
cp .env.example .env
```

#### 2. Start Backend Server
```bash
# Run FastAPI with auto-reload (bound to http://localhost:8000)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 3. Frontend Setup
```bash
# In a separate terminal, navigate to frontend/
cd frontend

# Install Node modules
npm install

# Start Vite development server (proxies /api requests to :8000)
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

### Option B: Standalone Production Mode (Single-URL Unified Build)

FastAPI can serve both the compiled React single-page application and the REST API from a single port (`8000`):

```bash
# 1. Compile frontend production assets
cd frontend
npm install
npm run build
cd ..

# 2. Run backend (serves frontend/dist at root / and API at /api)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser.

---

## ⚙️ 6. Environment Variables

KrishiSetu is configured via environment variables. See [`.env.example`](.env.example) for exact variable names:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATA_GOV_API_KEY` | Optional | Public demo key | OGD India API key for live AGMARKNET mandi quotations. (Falls back to sample key and benchmark records if omitted). |
| `GEMINI_API_KEY` | Optional | `""` | Google Gemini API key for AI advisory. (Falls back to deterministic localized templates if omitted). |
| `DATABASE_URL` | Optional | `sqlite:///./krishisetu.db` | SQLAlchemy database URL. |
| `PORT` | Optional | `8000` | Server listen port. |
| `HOST` | Optional | `0.0.0.0` | Server listen host. |

> **Security Note:** Never commit actual `.env` files or API credentials to version control. The repository's `.gitignore` excludes all `.env` files, databases, and temporary artifacts.

---

## 🐳 7. Docker & Production Deployment

### Docker Multi-Stage Build
The project includes a production-ready, multi-stage [Dockerfile](Dockerfile):
- **Stage 1 (`node:20-alpine`):** Installs frontend dependencies and compiles static assets into `frontend/dist`.
- **Stage 2 (`python:3.11-slim`):** Installs Python packages, copies backend application code and compiled frontend assets, and starts Uvicorn.

```bash
# Build the unified container
docker build -t krishisetu .

# Run the container (bound to host port 8000)
docker run -p 8000:8000 \
  -e GEMINI_API_KEY="your_gemini_key" \
  -e DATA_GOV_API_KEY="your_ogd_key" \
  krishisetu
```

### Render Deployment Blueprint
The repository includes a validated [`render.yaml`](render.yaml) specification configuring Render as a native Python Web Service (`runtime: python`):
- **Runtime Environment:** Native Python (`runtime: python`, Python 3.11.9) with Node.js (20.18.0) automatically available in the environment to build the React frontend bundle during deployment. (The multi-stage [Dockerfile](Dockerfile) is provided separately for containerized hosting on Docker Desktop, Cloud Run, or Kubernetes).
- **Build Command:** `pip install -r backend/requirements.txt && cd frontend && npm install && npm run build && cd ..`
- **Start Command:** `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/api/health`
- **Port:** Dynamically binds to `$PORT` (`10000` on Render)
- **Database Persistence on Free Tier:** Free-tier Render instances run on ephemeral containers. On container cold boot or restart, FastAPI's application lifespan automatically invokes `init_db()` and `seed_all()`, idempotently provisioning the database with 10 crop profiles and 25 baseline benchmark snapshots. The application remains fully functional out of the box.

---

## 🧪 8. Automated Testing & Verification

The automated test suite is structured for strict deterministic execution with zero external network access:

```bash
# Run complete test suite with network access blocked
python -m pytest backend/tests -v
```

### Test Suite Status
- **Passing Tests:** **132 passing pytest tests** (0 failures, 0 errors)
- **Discovered Test Modules:** **7 pytest-discovered test modules**
- **Network Isolation:** Enforced via `pytest-socket` (`--disable-socket` in `pytest.ini`). Zero external API calls during testing.
- **Database Isolation:** All tests run on temporary in-memory or isolated SQLite databases, guaranteeing the production database remains untouched.
- **Standalone Smoke Verification:** `test_production_smoke.py` is a separate standalone executable smoke-test script (verifying single-URL static asset serving and SPA routing) and contains zero pytest-discovered tests.

| Pytest Module | Coverage Area | Tests | Status |
|---|---|---|---|
| `test_audit_corrections.py` | Preset regressions, error handling & upstream API resilience | 37 | ✅ Passed |
| `test_database_safety.py` | Production database read-only protection & seeder safety | 9 | ✅ Passed |
| `test_engines.py` | Haversine distance, haulage rates & perishability decay math | 11 | ✅ Passed |
| `test_freshness_metadata.py` | Data provenance, arrival dates, trading-date validations | 22 | ✅ Passed |
| `test_manual_refresh.py` | Server-side 60s monotonic cooldowns & state transitions | 32 | ✅ Passed |
| `test_phase2.py` | External API parsing, Open-Meteo & AGMARKNET mocks | 6 | ✅ Passed |
| `test_sqlite_migration.py` | Table-recreation migration & AUTOINCREMENT preservation | 15 | ✅ Passed |
| **Total** | **All 7 Pytest-Discovered Test Modules** | **132** | **✅ 100% Passed** |

*Note: In addition to the 7 pytest modules above, `backend/tests/test_production_smoke.py` is executed standalone via `python backend/tests/test_production_smoke.py`.*

---

## 🧭 9. Judge Demonstration Walkthrough

To review the project during competition judging:

1. **Preset Selection:** On the dashboard, click any of the 5 quick presets (e.g., **"Kolar Tomato"**).
2. **Review Harvest Risk:** Observe the **72h Harvest Risk** banner. Note the volumetric topsoil moisture percentage and 7-day rainfall forecast indicating whether harvesting today is safe.
3. **Analyze Mandi Comparison:** Inspect the market comparison table:
   - Notice the difference between **Sticker (Modal) Price** and **Net Realizable Price**.
   - Check the **Data Source & Freshness Badge** (`Live API`, `Cached`, or `Estimated Benchmark`).
   - Observe how freight charges and transit perishability affect the final market ranking.
4. **Trigger Manual Refresh:** Click the **Refresh** button in the control bar. Observe:
   - The button shows `Refreshing...`.
   - On response, an immediate **60-second cooldown timer** starts (`59s`, `58s`, ...).
   - Duplicate clicks during cooldown are safely prevented.
5. **Switch Language & Listen to Voice:**
   - Switch language to **ಕನ್ನಡ (Kannada)** or **हिन्दी (Hindi)**.
   - Click the audio speaker button on the **Decision Plan Card** to hear the regional language harvest advisory.

---

## 📄 10. License & Submission Credits

- **Project:** KrishiSetu
- **Track:** Track 2 — Climate, Resource Infrastructure & Global Supply Resilience
- **Competition:** Challazo IDEA//FORGE Online Hackathon 2026
- **Developer:** Pranav Mahesh Palled ([GitHub Profile](https://github.com/Pranav-Mahesh-Palled))
