"""FastAPI application entry point for KrishiSetu.

Phase 1 Endpoints:
- GET /api/health: Deployment and database connectivity check.
- GET /api/presets: Demo presets, supported crops, and regional languages.

Phase 2 Endpoints:
- POST /api/analyze: Unified weather, mandi arbitrage, and AI advisory analysis.
- POST /api/chat: Multilingual conversational Q&A grounded in analysis context.
- POST /api/tts: Regional Text-to-Speech audio streaming via gTTS.
"""

import io
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from gtts import gTTS
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.database import get_db, init_db, SessionLocal
from backend.app.models import CropProfile, MandiPricesCache
from backend.app.seed import (
    CROP_PROFILES_DATA,
    DEMO_PRESETS,
    MANDI_COORDINATES,
    SUPPORTED_LANGUAGES,
    seed_all,
)
from backend.app.services.ai_service import generate_ai_advisory, generate_chat_reply
from backend.app.services.arbitrage_engine import determine_price_comparison_status
from backend.app.services.mandi_service import get_mandi_arbitrage_analysis
from backend.app.services.weather_service import geocode_location, get_weather_forecast

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes tables and seeds reference data on server startup."""
    init_db()
    with SessionLocal() as db:
        seed_all(db)
    yield


app = FastAPI(
    title="KrishiSetu API",
    description="Multilingual Agritech & Harvest Arbitrage Advisory Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend clients (Vite dev server, localhost, and production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Request & Response Schemas
# ==============================================================================

class AnalyzeRequest(BaseModel):
    location_query: str = Field(..., description="Village, town, or district name", json_schema_extra={"example": "Belagavi, Karnataka"})
    latitude: Optional[float] = Field(None, description="Exact latitude if known", json_schema_extra={"example": 15.8497})
    longitude: Optional[float] = Field(None, description="Exact longitude if known", json_schema_extra={"example": 74.4977})
    crop_id: str = Field(..., description="Crop identifier", json_schema_extra={"example": "onion"})
    quantity_quintals: float = Field(30.0, ge=1.0, description="Produce quantity in quintals", json_schema_extra={"example": 30.0})
    language: str = Field("en", description="Target advisory language (en, kn, hi, mr)", json_schema_extra={"example": "kn"})
    force_refresh: bool = Field(False, description="Bypass standard 3h cache to request fresh AGMARKNET and Open-Meteo data if cooldown allows", json_schema_extra={"example": False})


class ChatRequest(BaseModel):
    analysis_context: Dict[str, Any] = Field(..., description="Current analysis context payload")
    question: str = Field(..., description="Farmer's query")
    language: str = Field("en", description="Target response language (en, kn, hi, mr)")


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize to speech")
    language: str = Field("en", description="Language code: en, kn, hi, mr")


# ==============================================================================
# Phase 1 Endpoints
# ==============================================================================

@app.get(
    "/api/health",
    summary="Service Health Check",
    tags=["Health"],
    response_model=Dict[str, Any],
)
def get_health(db: Session = Depends(get_db)):
    """Verifies service health, database connectivity, and timestamp."""
    try:
        # Check SQLite connectivity
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {str(exc)}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "db": db_status},
        )

    return {
        "status": "ok",
        "db": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/api/presets",
    summary="Get Demo Presets, Crops & Languages",
    tags=["Reference Data"],
    response_model=Dict[str, Any],
)
def get_presets(db: Session = Depends(get_db)):
    """Returns curated demo presets, supported crops, and regional languages."""
    db_crops = db.query(CropProfile).all()
    if db_crops:
        crops_list = [
            {
                "crop_id": c.crop_id,
                "display_name_en": c.display_name_en,
                "display_name_kn": c.display_name_kn,
                "display_name_hi": c.display_name_hi,
                "display_name_mr": c.display_name_mr,
                "agmarknet_commodity": c.agmarknet_commodity,
                "perishability_tier": c.perishability_tier,
                "rain_sensitivity": c.rain_sensitivity,
                "base_transport_per_km_qtl": c.base_transport_per_km_qtl,
            }
            for c in db_crops
        ]
    else:
        crops_list = CROP_PROFILES_DATA

    enriched_presets = []
    for preset in DEMO_PRESETS:
        mandi_details = []
        for m_name in preset["mandis"]:
            coords = MANDI_COORDINATES.get(m_name, {"latitude": preset["latitude"], "longitude": preset["longitude"]})
            mandi_details.append({
                "market": m_name,
                "latitude": coords["latitude"],
                "longitude": coords["longitude"],
            })

        enriched_presets.append({
            **preset,
            "mandis_count": len(preset["mandis"]),
            "mandi_details": mandi_details,
        })

    return {
        "presets": enriched_presets,
        "crops": crops_list,
        "languages": SUPPORTED_LANGUAGES,
    }


# ==============================================================================
# Phase 2 Endpoints
# ==============================================================================

@app.post(
    "/api/analyze",
    summary="Unified Weather, Mandi Arbitrage & Advisory Analysis",
    tags=["Analysis"],
    response_model=Dict[str, Any],
)
async def analyze_harvest_and_sale(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
):
    """Executes end-to-end analysis: geocoding, weather risk, multi-mandi arbitrage, and AI advisory."""
    # 1. Fetch Crop Profile
    crop = db.query(CropProfile).filter(CropProfile.crop_id == request.crop_id).first()
    if not crop:
        supported = [c.crop_id for c in db.query(CropProfile).all()]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crop '{request.crop_id}' not found. Supported crops: {supported}",
        )

    # 2. Determine Coordinates (Geocoding if lat/lon omitted)
    if request.latitude is not None and request.longitude is not None:
        lat = float(request.latitude)
        lon = float(request.longitude)
        location_data = {
            "name": request.location_query.split(",")[0].strip(),
            "state": "India",
            "lat": lat,
            "lon": lon,
        }
    else:
        try:
            geocoded = await geocode_location(request.location_query)
            lat = geocoded["lat"]
            lon = geocoded["lon"]
            location_data = geocoded
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to resolve geographic coordinates for location '{request.location_query}'. Please provide a valid town or district.",
            )

    # 3. Weather & 72-Hour Risk Analysis
    weather_data = await get_weather_forecast(
        lat, lon, crop.perishability_tier, db, force_refresh=request.force_refresh
    )

    # 4. Multi-Mandi Price Fetching & Arbitrage Ranking
    arbitrage_results, mandi_refresh_meta = await get_mandi_arbitrage_analysis(
        origin_lat=lat,
        origin_lon=lon,
        crop=crop,
        quantity_quintals=request.quantity_quintals,
        db=db,
        force_refresh=request.force_refresh,
        return_meta=True,
    )

    is_out_of_coverage = len(arbitrage_results) == 0

    if is_out_of_coverage:
        coverage_status = "out_of_coverage"
        coverage_warning = (
            f"No APMC mandis found within 150 km road distance of {location_data.get('name')}. "
            "KrishiSetu active mandi coverage currently spans Karnataka, Maharashtra, and adjacent borders."
        )
        price_comparison_status = "out_of_coverage"
        price_comparison_notice = (
            "Origin location is outside active 150 km APMC mandi coverage zone."
        )
    else:
        coverage_status = "covered"
        coverage_warning = None
        price_comparison_status = determine_price_comparison_status(arbitrage_results)
        if price_comparison_status == "verified_comparison_available":
            price_comparison_notice = (
                "Verified comparison available: Authentic government AGMARKNET quotations exist for both your local baseline market and alternative regional mandis."
            )
        elif price_comparison_status == "local_baseline_missing":
            price_comparison_notice = (
                "Local baseline missing: Nearby alternative mandis report verified quotes, but your nearest local market has no verified record today. Regional quotes are shown for reference only; no additional profit can be claimed."
            )
        elif price_comparison_status == "insufficient_alternative_quotes":
            price_comparison_notice = (
                "Insufficient alternative quotes: Your local mandi has a verified quotation, but alternative markets lack authenticated government prices today. Recommending local sale."
            )
        else:  # no_verified_price_data
            price_comparison_notice = (
                "No verified price data: No authentic government AGMARKNET quotations were recorded today for this crop in nearby markets. Displayed rates are estimated benchmarks and cannot support arbitrage recommendations."
            )

    mandi_comparison = [
        {
            "market": r.market,
            "district": r.district,
            "state": r.state,
            "distance_km": r.distance_km,
            "modal_price": r.modal_price,
            "transport_cost_per_qtl": r.transport_cost_per_qtl,
            "spoilage_deduction_per_qtl": r.spoilage_deduction_per_qtl,
            "net_price_per_qtl": r.net_price_per_qtl,
            "net_gain_vs_local_total": r.net_gain_vs_local_total,
            "is_local": r.is_local,
            "arrival_date": r.arrival_date,
            "data_source": r.source,
            "variety": r.variety,
            "is_benchmark": r.is_benchmark,
            "dataset_id": r.dataset_id,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at is not None else None,
            "freshness_status": r.freshness_status,
            "retrieval_status": r.retrieval_status,
            "data_age_seconds": r.data_age_seconds,
        }
        for r in arbitrage_results
    ]

    # 5. Top-Level Additive Freshness Metadata
    if is_out_of_coverage:
        mandi_freshness = {
            "freshness_status": "unavailable",
            "retrieval_status": "out_of_coverage",
            "refresh_status": mandi_refresh_meta.get("refresh_status", "not_requested"),
            "cooldown_remaining_seconds": mandi_refresh_meta.get("cooldown_remaining_seconds", 0),
            "last_fetched_at": None,
            "oldest_fetched_at": None,
            "live_quotes_count": 0,
            "cached_quotes_count": 0,
            "stale_quotes_count": 0,
            "benchmark_quotes_count": 0,
            "total_mandis": 0,
        }
    else:
        relevant_quotes = [r for r in arbitrage_results if not r.is_benchmark]
        fetched_times = [r.fetched_at for r in relevant_quotes if r.fetched_at is not None]
        live_count = sum(1 for r in arbitrage_results if r.retrieval_status == "live_response")
        cached_count = sum(1 for r in arbitrage_results if r.retrieval_status == "cache_hit")
        stale_count = sum(1 for r in arbitrage_results if (r.freshness_status == "stale" or r.retrieval_status == "stale_cache_fallback"))
        bench_count = sum(1 for r in arbitrage_results if r.is_benchmark)

        last_fetched_iso = max(fetched_times).isoformat() if fetched_times else None
        oldest_fetched_iso = min(fetched_times).isoformat() if fetched_times else None

        if bench_count == len(arbitrage_results):
            overall_mandi_freshness = "estimated"
            overall_mandi_retrieval = "benchmark"
        elif stale_count > 0:
            # Conservative: If any relevant quotation is stale, the aggregate reflects that stale data is present
            overall_mandi_freshness = "stale"
            overall_mandi_retrieval = "stale_cache_fallback"
        elif cached_count > 0:
            # All quotes are valid within TTL (<3h), but some/all are from cache
            overall_mandi_freshness = "cached"
            overall_mandi_retrieval = "cache_hit" if live_count == 0 else "live_response"
        else:
            # All relevant verified quotations are fresh live responses
            overall_mandi_freshness = "fresh"
            overall_mandi_retrieval = "live_response"

        mandi_freshness = {
            "freshness_status": overall_mandi_freshness,
            "retrieval_status": overall_mandi_retrieval,
            "refresh_status": mandi_refresh_meta.get("refresh_status", "not_requested"),
            "cooldown_remaining_seconds": mandi_refresh_meta.get("cooldown_remaining_seconds", 0),
            "last_fetched_at": last_fetched_iso,
            "oldest_fetched_at": oldest_fetched_iso,
            "live_quotes_count": live_count,
            "cached_quotes_count": cached_count,
            "stale_quotes_count": stale_count,
            "benchmark_quotes_count": bench_count,
            "total_mandis": len(arbitrage_results),
        }

    weather_freshness = {
        "freshness_status": weather_data.get("freshness_status", "estimated"),
        "retrieval_status": weather_data.get("retrieval_status", "synthetic_fallback"),
        "refresh_status": weather_data.get("refresh_status", "not_requested"),
        "cooldown_remaining_seconds": weather_data.get("cooldown_remaining_seconds", 0),
        "data_source": weather_data.get("data_source", "synthetic_baseline"),
        "fetched_at": weather_data.get("fetched_at"),
        "data_age_seconds": weather_data.get("data_age_seconds"),
    }

    freshness_metadata = {
        "mandi": mandi_freshness,
        "weather": weather_freshness,
    }

    # 6. Multilingual AI Advisory Generation
    crop_info = {
        "crop_id": crop.crop_id,
        "display_name_en": crop.display_name_en,
        "display_name_kn": crop.display_name_kn,
        "display_name_hi": crop.display_name_hi,
        "display_name_mr": crop.display_name_mr,
        "perishability_tier": crop.perishability_tier,
    }

    advisory = await generate_ai_advisory(
        crop_info=crop_info,
        weather_info=weather_data,
        mandi_comparison=mandi_comparison,
        quantity=request.quantity_quintals,
        language=request.language,
        price_comparison_status=price_comparison_status,
    )

    return {
        "location": location_data,
        "weather": weather_data,
        "mandi_comparison": mandi_comparison,
        "ai_advisory": advisory.model_dump(),
        "coverage_status": coverage_status,
        "coverage_warning": coverage_warning,
        "price_comparison_status": price_comparison_status,
        "price_comparison_notice": price_comparison_notice,
        "freshness_metadata": freshness_metadata,
    }


@app.post(
    "/api/chat",
    summary="Multilingual Conversational Q&A",
    tags=["Chat"],
    response_model=Dict[str, Any],
)
async def post_chat(request: ChatRequest):
    """Answers farmer questions grounded in the current analysis context."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    answer = await generate_chat_reply(
        analysis_context=request.analysis_context,
        question=request.question,
        language=request.language,
    )

    return {
        "answer": answer,
        "language": request.language,
    }


@app.post(
    "/api/tts",
    summary="Regional Text to Speech Audio Stream",
    tags=["Voice"],
)
def post_tts(request: TTSRequest):
    """Streams synthesized audio MP3 for regional text."""
    clean_text = request.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    lang_map = {
        "kn": "kn",
        "hi": "hi",
        "mr": "mr",
        "en": "en",
    }
    target_lang = lang_map.get(request.language.lower().strip(), "en")

    try:
        fp = io.BytesIO()
        tts = gTTS(text=clean_text, lang=target_lang, slow=False)
        tts.write_to_fp(fp)
        fp.seek(0)
        return StreamingResponse(fp, media_type="audio/mpeg")
    except Exception as exc:
        logger.error(f"TTS generation error: {exc}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(exc)}")


# ==============================================================================
# Unified Single-URL Frontend Static & SPA Serving
# ==============================================================================

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Check for production frontend build in monorepo layout or Docker container
dist_candidates = [
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
    Path.cwd() / "frontend" / "dist",
    Path.cwd() / "dist",
]
frontend_dist_dir = next((p for p in dist_candidates if p.exists() and (p / "index.html").exists()), None)

if frontend_dist_dir:
    logger.info(f"Mounting unified static frontend from: {frontend_dist_dir}")
    assets_dir = frontend_dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_root():
        """Serves the React frontend index.html at root."""
        return FileResponse(str(frontend_dist_dir / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_or_static(full_path: str):
        """Serves static assets or falls back to index.html for SPA routes.

        Strictly enforces that any unknown /api/* path returns JSON 404 rather than HTML.
        """
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API endpoint '/{full_path}' not found.",
            )

        # Check for static file directly inside dist/ (e.g. vite.svg, favicon.ico, etc.)
        candidate_file = frontend_dist_dir / full_path
        if candidate_file.is_file() and candidate_file.exists():
            return FileResponse(str(candidate_file))

        # Client-side SPA routing fallback
        index_file = frontend_dist_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

