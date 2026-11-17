# Project Specification V2: KrishiSetu
**Hackathon:** IDEA//FORGE Online Hackathon (Challazo — `challazo.in`)  
**Track:** Track 2 — Climate, Resource Infrastructure & Global Supply Resilience  
**Problem Area:** Multilingual Agritech & Resource Advisory Assistant  
**Submission Window:** November 20, 2026 (6:00 PM IST) – November 22, 2026 (11:59 PM IST)  
**Status:** Architecture Synchronized (Post Phase 1–4, Audit Corrections & Verified Mandi Refinement)

---

## 1. Problem Statement & Target Users

### Who Experiences This Problem
Smallholder and marginal farmers across India—with initial high-density coverage focused on major horticultural and grain production clusters in Karnataka and Maharashtra—who cultivate weather-sensitive, price-volatile crops such as onions, tomatoes, potatoes, green chillies, soybeans, and maize.

### The Core Problem
Smallholder farmers lose 15%–30% of their potential seasonal income at the final mile—the harvest and post-harvest marketing window—due to two disconnected blind spots:
1. **Hyper-Local Weather & Spoilage Risk:** Coarse district-level forecasts fail to warn farmers of localized rainfall or high soil-moisture spikes at their exact village coordinates during the critical 72-hour pre-harvest window, leading to severe field rot, waterlogging, fungal damage, and mandatory market-yard distress discounts.
2. **Mandi Price Opacity & Arbitrage Loss:** Wholesale modal prices across neighboring APMC mandis within a 30–150 km radius frequently differ by ₹300–₹1,200 per quintal. Without transparent, road-adjusted transit distance math, haulage freight deductions, and crop-specific transit spoilage rates, farmers sell blindly at their nearest mandi or accept depressed bids from village middlemen.

### Why It Matters
For a smallholder farmer harvesting 20–100 quintals of produce, choosing the wrong harvest day ahead of unseasonal rain or travelling to a distant market whose price advantage is swallowed by transport costs can eliminate their entire seasonal net margin.

---

## 2. Proposed Solution & Value Proposition

**KrishiSetu** is a multilingual, voice-enabled agricultural decision-support web application that unifies hyper-local weather risk modeling, authentic daily APMC wholesale market quotations, and road-distance transport economics into an actionable harvest-and-marketing action plan.

### Core Capabilities
1. **Hyper-Local Weather & Soil Risk Modeling:** Fetches high-resolution 7-day precipitation volume, rain probability, temperature extremes, and topsoil layer volumetric moisture content (`0–7 cm`) for the farmer's exact geographic coordinates via Open-Meteo.
2. **Multi-Mandi Net Realizable Arbitrage Engine:** Evaluates candidate APMC mandis within a 150 km road-transit radius, deducts freight haulage and transit perishability losses, ranks markets by net realizable return, and strictly verifies price-data eligibility before declaring arbitrage opportunities.
3. **Where AI Genuinely Contributes:**
   - **Grounded Agricultural Reasoning:** Google Gemini (`gemini-3.5-flash-lite`) synthesizes computed weather risks, perishability constraints, and net-price spreads into plain-language harvest actions, target market rationales, and crop-preservation steps. The LLM is strictly constrained by system instructions to use provided mathematical figures without price hallucination.
   - **Multilingual Regional Voice & Text Interface:** Supports **English, Kannada (`kn`), Hindi (`hi`), and Marathi (`mr`)**. Farmers can interact through native browser speech recognition (STT) and synthesized voice output (dual Web Speech API + backend gTTS streaming), ensuring accessibility regardless of literacy level.
4. **Deterministic Fallback Layer:** Complete, localized deterministic advisory templates across all 4 languages ensure the application delivers reliable advice even during upstream AI service interruptions or missing API credentials.

---

## 3. Technology Stack (Implemented)

The implemented stack is locked to production-verified technologies:

### Frontend
- **Framework & Runtime:** React 19 (`react` 19.3.1, `react-dom` 19.3.1)
- **Tooling & Bundler:** Vite 8 (installed and locked: `vite` 8.3.8 with `@vitejs/plugin-react` 6.1.2)
- **Language:** TypeScript 7.0 (`typescript` 7.0.2)
- **Styling:** Tailwind CSS 3 (`tailwindcss` 3.4.19)
- **Iconography:** Lucide React (`lucide-react` 1.73.0)
- **Voice Input:** Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)

### Backend
- **Runtime:** Python 3.11+ / 3.13
- **Web Framework:** FastAPI 0.115+ (Asynchronous ASGI)
- **Data Validation & Settings:** Pydantic v2
- **ORM & Data Layer:** SQLAlchemy 2.0+
- **Database:** SQLite 3 (WAL mode, multi-threaded safe via `check_same_thread=False`)
- **HTTP Client:** HTTPX 0.28+ (Async HTTP with custom application headers)
- **Audio Synthesis Fallback:** gTTS (Google Text-to-Speech) streaming MP3 byte buffers

### External APIs
- **Open-Meteo Geocoding API:** Name-to-coordinate resolution (`https://geocoding-api.open-meteo.com/v1/search`)
- **Open-Meteo Forecast API:** High-resolution weather and topsoil moisture (`https://api.open-meteo.com/v1/forecast`)
- **Open Government Data (OGD) Platform India:** AGMARKNET daily wholesale market prices resource (`https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070`)
- **Google Gemini API:** `gemini-3.5-flash-lite` (via official `google-genai` SDK; backed by deterministic template fallback)

### Containerization & Deployment
- **Containerization:** Multi-stage `Dockerfile` (`node:20-alpine` builds `frontend/dist`, `python:3.11-slim` runs FastAPI backend and serves static SPA assets)
- **Static Asset Serving:** FastAPI mounts compiled `frontend/dist/assets` at `/assets` and serves `index.html` for all non-API SPA routes, eliminating cross-origin complexity
- **Hosting Target:** Render Web Service (`render.yaml`) with health check endpoint `/api/health`

---

## 4. Data Provenance & Security Architecture

### Data Source Classification
To prevent misleading farmers, KrishiSetu strictly separates market price quotations into three explicit categories:

1. **`live_api`:**
   - Authentic, daily wholesale market arrival returns queried live from the official OGD India AGMARKNET resource (`9ef84268-d588-465a-a308-a864a43d0070`).
   - Carries an official arrival date (e.g. `16/11/2026`) and the OGD dataset identifier.
   - Cached in SQLite with a 3-hour Time-To-Live (TTL).
2. **`verified_snapshot`:**
   - Independently verified historical AGMARKNET quotations with traceable provenance, specific commodity grades, authenticated arrival dates, and verified source evidence.
   - Used for resilient testing and fallback verification when upstream live APIs are temporarily unreachable.
3. **`estimated_benchmark`:**
   - Regional benchmark price models used for situational reference when a market has not filed an official arrival report for the requested crop.
   - **Reclassification Notice:** The original 25 development baseline records seeded in early prototypes were audited and explicitly reclassified as `estimated_benchmark`. They carry `dataset_id = NULL` and are never represented as authentic government quotes.
   - **Safety Boundary:** Estimated benchmarks are strictly excluded from claiming verified net arbitrage gains and cannot be recommended as verified profit winners over a local market.

### HTTP Gateway Standards & Secret Hygiene
- **User-Agent Requirement:** Live requests to `api.data.gov.in` must include explicit application headers (`User-Agent: KrishiSetu/1.0`, `Accept: application/json`). Testing proved that default generic HTTPX client headers suffer from severe upstream throttling and 10–14 second gateway timeouts, whereas identified requests complete in 0.5–1.2 seconds.
- **Secret Isolation:** `DATA_GOV_API_KEY` and `GEMINI_API_KEY` are loaded exclusively on the backend from local environment variables. They are never exposed to the frontend client, never emitted in HTTP responses, and never logged to stdout or task logs.

### Safe Manual Refresh & Anti-Throttling Architecture
To prevent upstream API rate-limiting or denial-of-service bans while enabling farmers to request on-demand updates, KrishiSetu implements a safe manual refresh protocol on `POST /api/analyze`:
- **Unified Request Parameter:** `force_refresh: bool = False` within `AnalyzeRequest`. No secondary or out-of-band endpoints are created.
- **Independent Cooldown Enforcement:**
  - **Mandi Quotations:** 60-second cooldown tracked per `commodity + candidate_geography` scope (e.g., `onion:Karnataka,Maharashtra`).
  - **Weather Forecasts:** 60-second cooldown tracked per rounded coordinate key (`{round(lat,2):.2f}_{round(lon,2):.2f}`).
- **Cooldown Persistence & Memory Architecture:**
  - *Successful Fetches:* Update `fetched_at` timestamps in SQLite (`mandi_prices_cache` and `weather_cache`), ensuring cooldowns persist across server reboots.
  - *Failed Attempts & In-Flight Locks:* Tracked via in-memory dictionaries (`_mandi_last_attempt`, `_weather_last_attempt`) and `asyncio.Lock` pools, tailored for the single-container deployment.
- **Concurrency Locking & Request Coalescing:** Simultaneous duplicate refresh requests share an `asyncio.Lock`; if another request completes a fetch within the last 5 seconds, duplicate calls coalesce without triggering duplicate upstream HTTP requests.
- **Non-Destructive Failure Preservation:**
  - Upstream network errors, timeouts, 5xx server errors, 4xx client errors, and empty returns (`0 records found`) **never delete or overwrite** existing verified SQLite cached quotations or weather rows.
  - The API responds with the preserved cache and reports the exact failure outcome via `refresh_status` (`upstream_unavailable`, `invalid_response`, or `no_matching_records`), keeping `freshness_status` honestly reported as `cached` or `stale`.
- **Strict Semantic Field Separation:**
  - `freshness_status`: Data age tier (`fresh`, `cached`, `stale`, `estimated`, `unavailable`).
  - `retrieval_status`: Provenance channel (`live_response`, `cache_hit`, `stale_cache_fallback`, `snapshot_fallback`, `benchmark`, `synthetic_fallback`).
  - `refresh_status`: Current forced refresh attempt outcome (`not_requested`, `refreshed`, `cooldown`, `upstream_unavailable`, `no_matching_records`, `invalid_response`).
  - `cooldown_remaining_seconds`: Integer countdown of remaining lock time (0 when not throttled).

---

## 5. Geographic Coverage & Mandi Network

### Physical APMC Mandi Network (24 Curated Markets Across 3 States)
KrishiSetu models 24 physical APMC wholesale market yards across 5 major agricultural clusters spanning **Karnataka (12 markets)**, **Maharashtra (11 markets)**, and **Andhra Pradesh (1 border market)**:

1. **Belagavi Cluster (North Karnataka & South Maharashtra):**
   - **Belagavi APMC** — Belagavi District, Karnataka (`15.8500° N, 74.5000° E`)
   - **Bailhongal APMC** — Belagavi District, Karnataka (`15.8167° N, 74.8667° E`)
   - **Dharwad APMC** — Dharwad District, Karnataka (`15.4589° N, 75.0078° E`)
   - **Hubli APMC** — Dharwad District, Karnataka (`15.3647° N, 75.1240° E`)
   - **Kolhapur APMC** — Kolhapur District, Maharashtra (`16.7050° N, 74.2433° E`)
2. **Kolar Cluster (South-Eastern Karnataka & Andhra Pradesh Border):**
   - **Kolar APMC** — Kolar District, Karnataka (`13.1367° N, 78.1291° E`)
   - **Malur APMC** — Kolar District, Karnataka (`13.0039° N, 77.9400° E`)
   - **Chintamani APMC** — Chikkaballapura District, Karnataka (`13.4000° N, 78.0500° E`)
   - **Bengaluru (Yeshwanthpur) APMC** — Bengaluru Urban District, Karnataka (`13.0280° N, 77.5400° E`)
   - **Madanapalle APMC** — Annamayya District, Andhra Pradesh (`13.5500° N, 78.5000° E`)
   *(Resolution of Madanapalle Geographical Discrepancy: While primary coverage is Karnataka and Maharashtra, Madanapalle is physically located in Andhra Pradesh, 74 km from Kolar across the state border. It is intentionally included because it hosts one of Asia's largest tomato auction hubs and represents an authentic cross-border arbitrage alternative for Kolar farmers).*
3. **Nashik Cluster (North Maharashtra Onion & Vegetable Belt):**
   - **Nashik APMC** — Nashik District, Maharashtra (`19.9975° N, 73.7898° E`)
   - **Pimpalgaon APMC** — Nashik District, Maharashtra (`20.1700° N, 73.9800° E`)
   - **Lasalgaon APMC** — Nashik District, Maharashtra (`20.1472° N, 74.2267° E`)
   - **Yeola APMC** — Nashik District, Maharashtra (`20.0400° N, 74.4800° E`)
   - **Kalwan APMC** — Nashik District, Maharashtra (`20.4900° N, 74.0200° E`)
4. **Haveri Cluster (Central Karnataka Grain & Spice Belt):**
   - **Haveri APMC** — Haveri District, Karnataka (`14.7952° N, 75.3992° E`)
   - **Byadgi APMC** — Haveri District, Karnataka (`14.6800° N, 75.4800° E`)
   - **Ranebennur APMC** — Haveri District, Karnataka (`14.6200° N, 75.6200° E`)
   - **Davanagere APMC** — Davanagere District, Karnataka (`14.4644° N, 75.9218° E`)
5. **Pune Cluster (Western Maharashtra Horticultural Hub):**
   - **Pune APMC (Gultekdi)** — Pune District, Maharashtra (`18.5204° N, 73.8567° E`)
   - **Khed (Chakan) APMC** — Pune District, Maharashtra (`18.7600° N, 73.8500° E`)
   - **Shirur APMC** — Pune District, Maharashtra (`18.8260° N, 74.3780° E`)
   - **Manchar APMC** — Pune District, Maharashtra (`19.0000° N, 73.9400° E`)
   - **Junnar APMC** — Pune District, Maharashtra (`19.2000° N, 73.8800° E`)

### Geographic Boundaries & Separation of Capabilities
- **150 km Road Transit Boundary:** Candidate mandis are filtered by road distance ($\le 150.0\text{ km}$). Distant markets beyond 150 km are excluded to prevent excessive transit spoilage and driver fatigue for small commercial vehicles.
- **Separation of Capabilities:** Open-Meteo weather coverage is global (resolves any valid geographic coordinate in India), whereas APMC mandi arbitrage is bound by the curated 24-market network across Karnataka, Maharashtra, and the Andhra Pradesh border.
- **Out of Coverage Safety (`out_of_coverage`):** When a user enters a location where no curated APMC exists within 150 km road distance, the backend sets `coverage_status = "out_of_coverage"`, empties the mandi comparison list, and provides localized advice directing the farmer to regional state marketing boards. The application never invents or fabricates distant mandi recommendations.

---

## 6. Database Architecture & Migrations

### SQLite Schema (`krishisetu.db`)

#### 1. `mandi_prices_cache`
Stores cached wholesale market price quotes from AGMARKNET API or benchmark models:
| Column Name | SQL Type | Nullable | Description |
|---|---|---|---|
| `id` | `INTEGER` | No | Primary Key (Autoincrement) |
| `state` | `VARCHAR` | No | State name (e.g. "Karnataka", "Maharashtra") |
| `district` | `VARCHAR` | No | District name |
| `market` | `VARCHAR` | No | Canonical APMC market name |
| `commodity` | `VARCHAR` | No | Commodity name matching AGMARKNET taxonomy |
| `variety` | `VARCHAR` | Yes | Reported variety (e.g. "Local / Red", "FAQ") |
| `min_price` | `FLOAT` | No | Minimum wholesale price (₹/qtl) |
| `max_price` | `FLOAT` | No | Maximum wholesale price (₹/qtl) |
| `modal_price` | `FLOAT` | No | Modal settlement price (₹/qtl) |
| `arrival_date` | `VARCHAR` | No | Date of market return (e.g. "16/11/2026") |
| `source` | `VARCHAR` | No | `'live_api'`, `'verified_snapshot'`, or `'estimated_benchmark'` |
| `dataset_id` | `VARCHAR` | Yes | Official OGD resource UUID; `NULL` for benchmarks |
| `fetched_at` | `DATETIME` | No | Timestamp of cache insertion/update (UTC) |

#### 2. `weather_cache`
Stores raw Open-Meteo forecast payloads for 3-hour reuse:
| Column Name | SQL Type | Nullable | Description |
|---|---|---|---|
| `id` | `INTEGER` | No | Primary Key (Autoincrement) |
| `location_key` | `VARCHAR` | No | Unique coordinate key rounded to 2 decimals (`lat_lon`) |
| `payload_json` | `TEXT` | No | Complete JSON payload returned by Open-Meteo |
| `fetched_at` | `DATETIME` | No | Timestamp of cache insertion/update (UTC) |

#### 3. `crop_profiles` (Seeded Reference Table)
Stores agronomic and economic reference parameters for supported crops:
| Column Name | SQL Type | Nullable | Description |
|---|---|---|---|
| `crop_id` | `VARCHAR` | No | Unique identifier (Primary Key, e.g. `'onion'`) |
| `display_name_en` | `VARCHAR` | No | English display name ("Onion") |
| `display_name_kn` | `VARCHAR` | No | Kannada display name ("ಈರುಳ್ಳಿ") |
| `display_name_hi` | `VARCHAR` | No | Hindi display name ("प्याज") |
| `display_name_mr` | `VARCHAR` | No | Marathi display name ("कांदा") |
| `agmarknet_commodity` | `VARCHAR` | No | Exact string required for AGMARKNET query matching |
| `perishability_tier` | `VARCHAR` | No | Perishability classification: `'high'`, `'medium'`, `'low'` |
| `rain_sensitivity` | `FLOAT` | No | Spoilage sensitivity multiplier (`1.0` to `2.0`) |
| `base_transport_per_km_qtl`| `FLOAT` | No | Base transport freight rate (default ₹2.50/km/qtl) |

### Automated Database Migrations
On startup, `init_db()` in `database.py` executes idempotent schema migrations:
1. **Dynamic Column Addition:** Checks for the `dataset_id` column on `mandi_prices_cache` and applies `ALTER TABLE mandi_prices_cache ADD COLUMN dataset_id VARCHAR` if missing.
2. **Provenance Reclassification:** Idempotently reclassifies any unverified legacy snapshot records by executing:
   ```sql
   UPDATE mandi_prices_cache
   SET source = 'estimated_benchmark', dataset_id = NULL
   WHERE source = 'verified_snapshot' AND dataset_id IS NULL;
   ```

---

## 7. Financial & Arbitrage Calculation Engine

### Mathematical Formulations (`arbitrage_engine.py`)

#### 1. Great-Circle & Road Distance Adjustment
Great-circle distance is calculated using the spherical Haversine formula:
$$\Delta\phi = \text{radians}(\text{lat}_2 - \text{lat}_1), \quad \Delta\lambda = \text{radians}(\text{lon}_2 - \text{lon}_1)$$
$$a = \sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\text{radians}(\text{lat}_1)) \cos(\text{radians}(\text{lat}_2)) \sin^2\left(\frac{\Delta\lambda}{2}\right)$$
$$d_{\text{straight}} = 2 R \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1 - a}\right) \quad (R = 6371\text{ km})$$

Because rural road networks in India involve terrain curvature and state highway detours, great-circle distance is adjusted by a winding road factor of 1.25:
$$d_{\text{road}} = \text{round}(d_{\text{straight}} \times 1.25, 2)$$
*(If $d_{\text{straight}} < 0.1\text{ km}$, $d_{\text{road}} = 0.0\text{ km}$, indicating the local baseline market).*

#### 2. Transport Freight Calculation
Freight haulage per quintal is calculated based on vehicle operating costs:
$$\text{Transport Cost/Qtl (₹)} = \text{round}(d_{\text{road}} \times \text{base\_transport\_per\_km\_qtl}, 2)$$
*(Default $\text{base\_transport\_per\_km\_qtl} = ₹2.50/\text{km}/\text{qtl}$).*

#### 3. Crop Perishability Transit Spoilage Rates
Transit vibration, ambient heat, and moisture during open-truck transport degrade produce value. Spoilage rates per road kilometer are tiered by crop physiology:
- **High Perishability** (Tomatoes, Green Chillies, Bananas): $0.05\% / \text{km}$ ($0.0005$)
- **Medium Perishability** (Onions, Potatoes): $0.02\% / \text{km}$ ($0.0002$)
- **Low Perishability** (Soybean, Maize, Turmeric, Cotton, Paddy): $0.005\% / \text{km}$ ($0.00005$)

To prevent unrealistic deductions on long hauls, transit spoilage is capped at **35%**:
$$\text{Spoilage Rate} = \min\left(0.35, d_{\text{road}} \times \text{Rate}_{\text{tier}}\right)$$
$$\text{Spoilage Deduction/Qtl (₹)} = \text{round}(\text{Modal Price} \times \text{Spoilage Rate}, 2)$$

#### 4. Net Realizable Price & Arbitrage Gain
$$\text{Net Realizable Price/Qtl} = \text{Modal Price} - \text{Transport Cost/Qtl} - \text{Spoilage Deduction/Qtl}$$

The local baseline market is identified as the nearest candidate ($d_{\text{road}} = 0.0\text{ km}$). For any alternative market $i$:
$$\text{Net Gain vs Local Total (₹)} = \text{round}\left((\text{Net Price}_i - \text{Local Net Price}) \times \text{Quantity (qtl)}, 2\right)$$

### Arbitrage Recommendation Eligibility Rules
A non-zero net gain claim is strictly permitted **only when**:
1. The local baseline market has an authentic quotation (`source in ['live_api', 'verified_snapshot']` and `is_benchmark=False`).
2. The target alternative market has an authentic quotation (`source in ['live_api', 'verified_snapshot']` and `is_benchmark=False`).
3. If either the local market or the target alternative is an estimated benchmark, `net_gain_vs_local_total` is forced to **₹0.00**.

*Economic Clarification: Net gain values represent estimated model projections based on prevailing modal wholesale prices and standard transport costs. They are not guaranteed financial realizations.*

---

## 8. Weather & Agronomic Risk Engine

### Open-Meteo Integration (`weather_service.py`)
- **Query Parameters:**
  - `daily`: `temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code`
  - `hourly`: `precipitation,soil_moisture_0_to_7cm,relative_humidity_2m`
- **Rolling 72-Hour Precipitation:** Evaluates the first 72 hourly precipitation observations (`hourly.precipitation[:72]`). Null values are safely filtered. If hourly data is missing, the engine sums the first 3 daily sums (`daily.precipitation_sum[:3]`).
- **Soil Moisture Missing-Data Integrity:** Topsoil moisture (`0–7 cm`) is averaged across valid non-null hourly readings. If all readings are null or unmeasured, the service sets `soil_moisture_avg = None` and `soil_moisture_available = False`. The engine **never substitutes artificial default numbers** (such as 0.25).

### Risk Classification Thresholds (`weather_risk.py`)
Harvest risk windows over the next 72 hours are evaluated deterministically:

1. **`HIGH_SPOILAGE_ALERT`:**
   - Cumulative 72-hour rainfall $\ge 15.0\text{ mm}$, OR
   - Maximum rain probability $\ge 70.0\%$ for `high` or `medium` perishability crops.
   - *Action:* Postpone harvest or immediately shelter standing heaps with waterproof tarpaulins to prevent fungal rot.
2. **`HARVEST_WITHIN_48H`:**
   - Cumulative 72-hour rainfall between $5.0\text{ mm}$ and $15.0\text{ mm}$ ($5.0 \le \text{rain} < 15.0$), OR
   - Valid topsoil moisture $> 0.35\text{ m}^3/\text{m}^3$ (soil saturation threshold).
   - *(If soil moisture is unavailable, the decision is made safely using rainfall and rain probability without false saturation triggers).*
   - *Action:* Complete harvest within 24 to 48 hours before impending rainfall makes fields unworkable.
3. **`SAFE_WINDOW`:**
   - 72-hour rainfall $< 5.0\text{ mm}$, rain probability $< 70.0\%$, and soil moisture $\le 0.35\text{ m}^3/\text{m}^3$.
   - *Action:* Favorable dry harvest and transit conditions.

---

## 9. Recommendation Eligibility & Response States

To ensure transparency, KrishiSetu decouples geographical accessibility from price-data sufficiency:

```text
                       [Candidate Mandis within 150 km?]
                                ├── NO  ──► coverage_status: 'out_of_coverage'
                                └── YES ──► coverage_status: 'covered'
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
     [Local Baseline Verified?]                                    [Local Baseline Benchmark?]
         ├── YES                                                       ├── YES
         │    ├── Alternative(s) Verified?                             │    ├── Alternative(s) Verified?
         │    │    ├── YES ──► 'verified_comparison_available'         │    │    ├── YES ──► 'local_baseline_missing'
         │    │    └── NO  ──► 'insufficient_alternative_quotes'       │    │    └── NO  ──► 'no_verified_price_data'
         │    │                                                        │    │
```

### Recommendation Status Definitions (`price_comparison_status`)

1. **`verified_comparison_available`:**
   - Both the local baseline market and at least one alternative regional mandi possess authentic government quotations (`live_api` or verified snapshot).
   - If an alternative market offers a superior net return after transport deductions, a verified net gain is declared.
   - *Important:* Having a verified comparison available does not imply an alternative market is more profitable. If the local market yields the highest net realization (e.g. Belagavi APMC Onion), the system advises selling locally with net gain of ₹0.00.
2. **`local_baseline_missing`:**
   - Nearby regional markets report verified AGMARKNET prices, but the farmer's nearest local market has no verified record for the day (e.g. Nashik APMC Onion).
   - Regional quotes are displayed strictly as reference points. Net gain is locked to ₹0.00, and the advisory explicitly instructs the farmer to verify their local spot auction rate before travelling.
3. **`insufficient_alternative_quotes`:**
   - The local market possesses an authentic government quotation, but neighboring alternative mandis lack verified daily returns (e.g. Pune Potato).
   - The system advises local sale at the verified price rather than speculating on unverified benchmark estimates.
4. **`no_verified_price_data`:**
   - Neither the local market nor any candidate alternative has filed official returns for the crop today (e.g. Haveri Maize).
   - Displayed rates are tagged as benchmarks for general context only; no arbitrage gain is claimed.
5. **`out_of_coverage`:**
   - The origin location has no curated APMC markets within 150 km road distance.

---

## 10. Actual API Specifications

### 1. `GET /api/health`
- **Description:** Verifies service uptime, database connectivity, and deployment status.
- **Response Model:**
  ```json
  {
    "status": "ok",
    "db": "connected",
    "timestamp": "2026-11-16T10:30:00Z"
  }
  ```

### 2. `GET /api/presets`
- **Description:** Supplies curated 1-click demo presets, 10 supported crop profiles, and supported languages.
- **Response Model:**
  ```json
  {
    "presets": [
      {
        "id": "belagavi-onion",
        "title": "Belagavi – Onion",
        "location_query": "Belagavi, Karnataka",
        "latitude": 15.8497,
        "longitude": 74.4977,
        "crop_id": "onion",
        "default_quantity": 50.0,
        "mandis": ["Belagavi APMC", "Bailhongal APMC", "Dharwad APMC", "Hubli APMC", "Kolhapur APMC"],
        "mandis_count": 5,
        "mandi_details": [...]
      },
      ...
    ],
    "crops": [
      {
        "crop_id": "onion",
        "display_name_en": "Onion",
        "display_name_kn": "ಈರುಳ್ಳಿ",
        "display_name_hi": "प्याज",
        "display_name_mr": "कांदा",
        "perishability_tier": "medium",
        "rain_sensitivity": 1.5,
        "base_transport_per_km_qtl": 2.5
      },
      ...
    ],
    "languages": [
      {"code": "en", "label": "English"},
      {"code": "kn", "label": "ಕನ್ನಡ"},
      {"code": "hi", "label": "हिन्दी"},
      {"code": "mr", "label": "मराठी"}
    ]
  }
  ```

### 3. `POST /api/analyze`
- **Description:** Executes end-to-end analysis: geocoding, 72-hour weather risk modeling, multi-mandi arbitrage ranking, and localized AI advisory generation.
- **Request Body (`AnalyzeRequest`):**
  ```json
  {
    "location_query": "Belagavi, Karnataka",
    "latitude": 15.8497,
    "longitude": 74.4977,
    "crop_id": "onion",
    "quantity_quintals": 50.0,
    "language": "kn",
    "force_refresh": false
  }
  ```
- **Response Body (`AnalysisResponse`):**
  ```json
  {
    "location": {
      "name": "Belagavi",
      "state": "Karnataka",
      "lat": 15.8497,
      "lon": 74.4977
    },
    "weather": {
      "risk_level": "SAFE_WINDOW",
      "rain_72h_mm": 0.0,
      "max_rain_prob_pct": 10.0,
      "soil_moisture_avg": 0.26,
      "soil_moisture_available": true,
      "headline": "Safe Harvest Window: Favorable Field Conditions",
      "description": "Dry conditions forecast over the next 72 hours...",
      "recommended_action": "Ideal window for harvesting, field curing, and mandi transit.",
      "daily_forecast": [
        {
          "date": "2026-11-16",
          "temp_max": 31.5,
          "temp_min": 19.2,
          "precipitation_mm": 0.0,
          "rain_prob_pct": 10.0,
          "weather_code": 0
        }
      ],
      "fetched_at": "2026-11-17T03:26:45+00:00",
      "data_source": "open_meteo",
      "freshness_status": "cached",
      "retrieval_status": "cache_hit",
      "data_age_seconds": 1824.5
    },
    "mandi_comparison": [
      {
        "market": "Belagavi APMC",
        "district": "Belagavi",
        "state": "Karnataka",
        "distance_km": 0.0,
        "modal_price": 4500.0,
        "transport_cost_per_qtl": 0.0,
        "spoilage_deduction_per_qtl": 0.0,
        "net_price_per_qtl": 4500.0,
        "net_gain_vs_local_total": 0.0,
        "is_local": true,
        "arrival_date": "16/11/2026",
        "data_source": "live_api",
        "variety": "Local / Red",
        "is_benchmark": false,
        "dataset_id": "9ef84268-d588-465a-a308-a864a43d0070",
        "fetched_at": "2026-11-17T03:26:45+00:00",
        "freshness_status": "fresh",
        "retrieval_status": "live_response",
        "data_age_seconds": 0.0
      }
    ],
    "ai_advisory": {
      "headline": "ಈರುಳ್ಳಿ ಬೆಳೆಯನ್ನು ಸ್ಥಳೀಯ ಮಂಡಿಯಲ್ಲೇ ಮಾರಾಟ ಮಾಡಿ (Belagavi APMC) — ಅತ್ಯುತ್ತಮ ನಿವ್ವಳ ಆದಾಯ",
      "harvest_action": "ಹವಾಮಾನ ಸಂಪೂರ್ಣ ಅನುಕೂಲಕರ ಮತ್ತು ಒಣದಾಗಿದೆ...",
      "recommended_mandi": "Belagavi APMC (ಸ್ಥಳೀಯ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿ ಅತ್ಯುತ್ತಮ ನಿವ್ವಳ ಲಾಭ)",
      "price_justification": "ಸ್ಥಳೀಯ Belagavi APMC ಮಂಡಿಯಲ್ಲಿ ನಿವ್ವಳ ಬೆಲೆ ಕ್ವಿಂಟಾಲ್‌ಗೆ ₹4,500 ಆಗಿದೆ...",
      "protection_tips": [
        "ಈರುಳ್ಳಿಯನ್ನು ಗಾಳಿಯಾಡುವ ಸೆಣಬಿನ ಗೋಣಿಚೀಲಗಳಲ್ಲಿ ತುಂಬಿಸಿ.",
        "ಸಾಗಾಣಿಕೆ ವಾಹನದ ಮೇಲೆ ಜಲನಿರೋಧಕ ತಾಡಪತ್ರಿ ಹೊದಿಸಿ."
      ],
      "language": "kn"
    },
    "coverage_status": "covered",
    "coverage_warning": null,
    "price_comparison_status": "verified_comparison_available",
    "price_comparison_notice": "Verified comparison available: Authentic government AGMARKNET quotations exist for both your local baseline market and alternative regional mandis.",
    "freshness_metadata": {
      "mandi": {
        "freshness_status": "fresh",
        "retrieval_status": "live_response",
        "refresh_status": "not_requested",
        "cooldown_remaining_seconds": 0,
        "last_fetched_at": "2026-11-17T03:26:45+00:00",
        "oldest_fetched_at": "2026-11-17T03:26:45+00:00",
        "live_quotes_count": 2,
        "cached_quotes_count": 0,
        "stale_quotes_count": 0,
        "benchmark_quotes_count": 0,
        "total_mandis": 2
      },
      "weather": {
        "freshness_status": "cached",
        "retrieval_status": "cache_hit",
        "refresh_status": "not_requested",
        "cooldown_remaining_seconds": 0,
        "data_source": "open_meteo",
        "fetched_at": "2026-11-17T03:26:45+00:00",
        "data_age_seconds": 1824.5
      }
    }
  }
  ```

### 4. `POST /api/chat`
- **Description:** Grounded conversational Q&A answering farmer follow-ups in regional languages using current analysis context.
- **Request Body (`ChatRequest`):**
  ```json
  {
    "analysis_context": { ... },
    "question": "ಮಳೆಗೆ ಈರುಳ್ಳಿ ಕೊಳೆಯದಂತೆ ಏನು ಮಾಡಬೇಕು?",
    "language": "kn"
  }
  ```
- **Response Body:**
  ```json
  {
    "answer": "ಮುಂದಿನ 72 ಗಂಟೆಗಳಲ್ಲಿ ಯಾವುದೇ ಮಳೆಯ ಮುನ್ಸೂಚನೆ ಇಲ್ಲ (0.0 ಮಿಮೀ ಮಳೆ). ಈರುಳ್ಳಿ ಸುರಕ್ಷಿತವಾಗಿ ಕೊಯ್ಲು ಮಾಡಿ ಚೆನ್ನಾಗಿ ಒಣಗಿಸಿ ಸೆಣಬಿನ ಚೀಲಗಳಲ್ಲಿ ಸಂಗ್ರಹಿಸಿ.",
    "language": "kn"
  }
  ```

### 5. `POST /api/tts`
- **Description:** Regional audio synthesis fallback streaming MP3 audio when client browser lacks regional speech synthesis packs.
- **Request Body (`TTSRequest`):**
  ```json
  {
    "text": "ಈರುಳ್ಳಿ ಬೆಳೆಯನ್ನು ಸ್ಥಳೀಯ ಮಂಡಿಯಲ್ಲೇ ಮಾರಾಟ ಮಾಡಿ.",
    "language": "kn"
  }
  ```
- **Response:** `StreamingResponse` with `Content-Type: audio/mpeg`.

---

## 11. AI & Voice Architecture

### LLM Integration (`ai_service.py`)
- **Primary Operational Model:** `gemini-3.5-flash-lite` via official `google-genai` SDK with strict JSON schema outputs (`response_schema=AIAdvisory`, temperature=0.2).
- **Secondary Model Fallback:** None. To preserve sub-2-second responsiveness and avoid cascading upstream delays, KrishiSetu does not cascade to a secondary LLM.
- **Production Fallback Engine:** The true, verified operational fallback is the deterministic multilingual template engine (`build_template_advisory`), which deterministically delivers grounded, localized advisories across English, Kannada, Hindi, and Marathi whenever the Gemini API is unreachable, unauthenticated (401), rate-limited (429), or experiencing upstream load (503/504).
- **Strict Grounding:** Gemini system instructions mandate that the model must strictly reuse numerical prices, distances, and weather figures supplied in the input prompt. Numerical fabrication is forbidden.

### Voice Interface Architecture
- **Speech-to-Text (STT):** Browser-native `SpeechRecognition` configured with language BCP-47 codes (`kn-IN`, `hi-IN`, `mr-IN`, `en-IN`).
- **Text-to-Speech (TTS):** Dual-layer audio pipeline:
  1. *Primary:* Browser `window.speechSynthesis` for instant client-side playback.
  2. *Fallback:* If the client OS lacks regional voice packs (common on desktop Linux or Windows for Kannada/Marathi), audio is fetched from the backend `/api/tts` endpoint (powered by `gTTS`) and played via HTML5 Audio element.

---

## 12. Known Limitations & Latency Profile

1. **Curated Mandi Geography:** Active mandi price optimization is currently scoped to 24 curated APMC markets across Karnataka (12), Maharashtra (11), and Andhra Pradesh (1 border market). Outside this 150 km perimeter, the system reports `out_of_coverage` rather than estimating arbitrary mandis.
2. **AGMARKNET Filing Frequency:** APMC markets report returns to the central OGD portal on a daily or intermittent schedule. Mandis frequently omit reporting on Sundays or holidays. In such cases, the system correctly falls back to estimated benchmarks or signals `insufficient_alternative_quotes`.
3. **API Performance & Upstream Latency Profile:**
   - *Warm / Cached Requests:* **0.5s – 2.0s** total response time when weather and mandi quotations are served from local SQLite cache (3-hour TTL) or deterministic templates.
   - *Normal Live API Execution:* **3.0s – 6.0s** total response time on cold cache misses during normal upstream network conditions (Open-Meteo ~0.3s, OGD India ~0.8s, Gemini reasoning ~2.0s).
   - *Degraded Upstream & Timeout Handling:* During upstream NIC `api.data.gov.in` server load, gateway delays can spike up to 10–14 seconds. The backend sets client timeouts (6.0s for Open-Meteo, 10.0s for OGD India) and catches `httpx.ReadTimeout`, falling back gracefully to SQLite cache or estimated benchmarks. Therefore, worst-case cold queries under severe upstream degradation may require **up to 10–12 seconds** before fallback completes, guaranteeing the application never hangs indefinitely. An unconditional 4-second latency cannot be guaranteed during upstream government network stalls.
4. **Transport & Spoilage Simplifications:** Transport freight is modeled at a linear ₹2.50/km/qtl and transit spoilage is modeled via physiological perishability coefficients. Actual spot market truck freights vary with fuel price fluctuations and driver availability.
5. **Quality Grade Granularity:** AGMARKNET reports modal prices for standard Fair Average Quality (FAQ) grades and does not distinguish specialty culinary sub-varieties (e.g. Bangalore Rose onion or Jyoti potato).

---

## 13. Development Roadmap

### Completed Milestones
- [x] **Phase 1: Database & Deterministic Engines:** SQLite schema, crop profiles, Haversine road-distance calculation, transit spoilage formulas, and unit test suite.
- [x] **Phase 2: External Data & AI Layer:** Open-Meteo weather integration, OGD India AGMARKNET fetcher with 3-hour caching, Gemini 3.5 Flash Lite advisory synthesizer, and gTTS streaming.
- [x] **Phase 3: Frontend Dashboard & Voice:** React 19 + Vite + Tailwind CSS dashboard, 1-click demo presets, visual comparison bar charts, and Web Speech API voice drawer.
- [x] **Phase 4: Single-URL Production Packaging:** Multi-stage Dockerfile, FastAPI static React serving, Render deployment manifest (`render.yaml`), and `.dockerignore`.
- [x] **Audit Corrections Pass:** Elimination of artificial soil moisture defaults (`None` handling), AGMARKNET multi-page pagination, extreme distance spoilage cap (35%), mandi alias fuzzy matching, and geocoding validation.
- [x] **Data Provenance Corrections:** Audit and reclassification of 25 legacy development records to `estimated_benchmark`, SQLite column migrations, explicit HTTP request headers (`User-Agent: KrishiSetu/1.0`), and API key masking.
- [x] **Verified Mandi Recommendation Refinements:** Implementation of `price_comparison_status` recommendation eligibility rules, decoupling of geographical coverage from price availability, 5 demo presets aligned to verified data realities, and frontend transparency banners.
- [x] **Data Freshness Phase A (Backend Metadata & Contract Extensions):** Accurate quotation and weather freshness exposure (`fetched_at`, `freshness_status`, `retrieval_status`, `data_age_seconds`), cache selection ordering by arrival date and retrieval timestamp, and top-level aggregate `freshness_metadata` in `/api/analyze`.
- [x] **Data Freshness Phase B (Safe Manual Refresh Mechanism):** Safe client-triggered refresh with server-side anti-throttling cooldown and non-blocking upstream fallbacks.

### Pending Milestones (Final Hackathon Push)
- [ ] **Data Freshness Phase C (Frontend Freshness Indicators & UI Controls):** Relative age labels, weather freshness badges, and responsive manual refresh controls.
- [ ] **Final Cross-Browser Testing:** Verification across mobile Chrome, iOS Safari, and Firefox.
- [ ] **Public Deployment:** Provisioning live instance on Render and verifying Challazo incognito check criteria.
- [ ] **Demo Video & Hackathon Submission:** Recording 2-minute walkthrough video and completing Challazo submission before November 22, 2026.

---

## 14. External Resources & Credits

- **Weather & Geocoding Data:** [Open-Meteo](https://open-meteo.com/) (Forecast & Geocoding APIs, CC BY 4.0).
- **Agricultural Market Quotations:** [Open Government Data (OGD) Platform India — data.gov.in](https://data.gov.in/) (AGMARKNET Daily Wholesale Market Prices Resource).
- **AI Synthesis & Reasoning:** Google Gemini API (`gemini-3.5-flash-lite` via `google-genai`).
- **Core Open-Source Libraries:** FastAPI 0.115+, SQLAlchemy 2.0+, SQLite 3, Pydantic v2, HTTPX 0.28+, gTTS 2.5+, React 19.3.1, Vite 8.3.8, Tailwind CSS 3.4.19, Lucide React 1.73.0.
