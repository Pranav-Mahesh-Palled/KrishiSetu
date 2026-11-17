"""Integration & Unit Tests for KrishiSetu Phase 2.

Covers:
- POST /api/analyze end-to-end structure, formulas, and ranking consistency
- Geocoding resolution when latitude/longitude are omitted
- Graceful fallback resilience when external APIs (Open-Meteo, data.gov.in) timeout/fail
- POST /api/chat in Kannada (kn) and Hindi (hi)
- POST /api/tts streaming valid audio/mpeg bytes across regional languages
"""

import pytest
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.seed import seed_all


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensures database is initialized and seeded before tests run."""
    init_db()
    with SessionLocal() as db:
        seed_all(db)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# /api/analyze Tests
# ==============================================================================

def test_analyze_end_to_end_structure_and_numbers(client: TestClient, canned_belagavi_onion_records):
    """Verifies end-to-end analysis structure, math consistency, and Kannada advisory."""
    payload = {
        "location_query": "Belagavi, Karnataka",
        "latitude": 15.8497,
        "longitude": 74.4977,
        "crop_id": "onion",
        "quantity_quintals": 30.0,
        "language": "kn",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_belagavi_onion_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Location schema
    assert "location" in data
    assert data["location"]["name"] == "Belagavi"
    assert abs(data["location"]["lat"] - 15.8497) < 0.01

    # Weather schema
    assert "weather" in data
    w = data["weather"]
    assert w["risk_level"] in ["SAFE_WINDOW", "HARVEST_WITHIN_48H", "HIGH_SPOILAGE_ALERT"]
    assert "rain_72h_mm" in w
    assert "max_rain_prob_pct" in w
    assert "soil_moisture_avg" in w
    assert "daily_forecast" in w
    assert len(w["daily_forecast"]) >= 5

    # Mandi comparison schema & math
    assert "mandi_comparison" in data
    mandis = data["mandi_comparison"]
    assert len(mandis) >= 3

    # Ranking validation: sorted descending by net_price_per_qtl
    for i in range(len(mandis) - 1):
        assert mandis[i]["net_price_per_qtl"] >= mandis[i + 1]["net_price_per_qtl"]

    # Formula consistency check
    for m in mandis:
        expected_net = round(m["modal_price"] - m["transport_cost_per_qtl"] - m["spoilage_deduction_per_qtl"], 2)
        assert abs(m["net_price_per_qtl"] - expected_net) <= 0.05
        assert m["data_source"] in ["live_api", "verified_snapshot", "estimated_benchmark"]

    # AI Advisory validation
    assert "ai_advisory" in data
    adv = data["ai_advisory"]
    assert adv["language"] == "kn"
    assert mandis[0]["market"] in adv["recommended_mandi"]
    assert len(adv["protection_tips"]) >= 2
    assert len(adv["headline"]) > 5
    assert len(adv["harvest_action"]) > 5


def test_analyze_geocoding_when_coordinates_omitted(client: TestClient, canned_kolar_tomato_records):
    """Verifies automatic geocoding fallback when latitude/longitude are omitted."""
    payload = {
        "location_query": "Kolar, Karnataka",
        "crop_id": "tomato",
        "quantity_quintals": 25.0,
        "language": "en",
    }
    with patch("backend.app.services.mandi_service.fetch_live_agmarknet_records", return_value=canned_kolar_tomato_records):
        response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Geocoded coordinates should approximate Kolar (~13.13, ~78.12)
    assert "location" in data
    assert abs(data["location"]["lat"] - 13.13) < 0.5
    assert abs(data["location"]["lon"] - 78.12) < 0.5

    assert len(data["mandi_comparison"]) >= 3
    assert data["ai_advisory"]["language"] == "en"


def test_analyze_graceful_fallback_when_external_apis_timeout(client: TestClient):
    """Verifies that /api/analyze never fails when external APIs raise timeouts."""
    payload = {
        "location_query": "Nashik, Maharashtra",
        "latitude": 19.9975,
        "longitude": 73.7898,
        "crop_id": "onion",
        "quantity_quintals": 40.0,
        "language": "mr",
    }

    # Simulate network timeout on all external httpx calls
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Connection timed out")):
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Should fall back to verified snapshots and synthetic weather
        assert len(data["mandi_comparison"]) >= 3
        # Check that fallback estimated_benchmark was used
        assert any(m["data_source"] in ["estimated_benchmark", "verified_snapshot"] for m in data["mandi_comparison"])
        assert data["weather"]["risk_level"] in ["SAFE_WINDOW", "HARVEST_WITHIN_48H", "HIGH_SPOILAGE_ALERT"]
        assert data["ai_advisory"]["language"] == "mr"


def test_analyze_invalid_crop_returns_404(client: TestClient):
    """Verifies 404 response when an unsupported crop_id is provided."""
    payload = {
        "location_query": "Pune, Maharashtra",
        "crop_id": "unknown_crop_xyz",
        "quantity_quintals": 10.0,
    }
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ==============================================================================
# /api/chat Tests
# ==============================================================================

def test_chat_multilingual_kannada_and_hindi(
    client: TestClient,
    canned_kannada_chat_response: str,
    canned_hindi_chat_response: str,
):
    """Verifies regional Q&A responses in Kannada and Hindi."""
    context = {
        "weather": {"risk_level": "SAFE_WINDOW", "rain_72h_mm": 2.0},
        "mandi_comparison": [
            {
                "market": "Hubli APMC",
                "modal_price": 2520.0,
                "net_price_per_qtl": 2215.0,
                "net_gain_vs_local_total": 11550.0,
            }
        ],
    }

    # 1. Kannada Query
    kn_resp = client.post(
        "/api/chat",
        json={
            "analysis_context": context,
            "question": "ಈರುಳ್ಳಿ ಮಾರಾಟಕ್ಕೆ ಯಾವ ಮಾರುಕಟ್ಟೆ ಉತ್ತಮ ಮತ್ತು ಬೆಲೆ ಎಷ್ಟು?",
            "language": "kn",
        },
    )
    assert kn_resp.status_code == 200
    kn_data = kn_resp.json()
    assert kn_data["language"] == "kn"
    assert kn_data["answer"] == canned_kannada_chat_response
    assert "ಹುಬ್ಬಳ್ಳಿ" in kn_data["answer"]
    assert "ಲಾಭ" in kn_data["answer"]

    # 2. Hindi Query
    hi_resp = client.post(
        "/api/chat",
        json={
            "analysis_context": context,
            "question": "क्या मुझे बारिश से अपनी फसल को बचाना चाहिए?",
            "language": "hi",
        },
    )
    assert hi_resp.status_code == 200
    hi_data = hi_resp.json()
    assert hi_data["language"] == "hi"
    assert hi_data["answer"] == canned_hindi_chat_response
    assert "हुबली" in hi_data["answer"]
    assert "लाभ" in hi_data["answer"]


# ==============================================================================
# /api/tts Tests
# ==============================================================================

def test_tts_returns_valid_mp3_bytes(client: TestClient, canned_tts_mp3_bytes: bytes):
    """Verifies that /api/tts returns audio/mpeg stream for regional languages."""
    # Test Kannada voice synthesis
    kn_resp = client.post(
        "/api/tts",
        json={
            "text": "ಹುಬ್ಬಳ್ಳಿ ಎಪಿಎಂಸಿ ಮಾರುಕಟ್ಟೆಗೆ ಸಾಗಾಟ ಸೂಕ್ತವಾಗಿದೆ.",
            "language": "kn",
        },
    )
    assert kn_resp.status_code == 200
    assert kn_resp.headers["content-type"] == "audio/mpeg"
    assert kn_resp.content == canned_tts_mp3_bytes
    assert len(kn_resp.content) > 1000  # Non-trivial MP3 audio data

    # Test Hindi voice synthesis
    hi_resp = client.post(
        "/api/tts",
        json={
            "text": "हुबली मंडी में बेचना सबसे ज्यादा लाभदायक है।",
            "language": "hi",
        },
    )
    assert hi_resp.status_code == 200
    assert hi_resp.headers["content-type"] == "audio/mpeg"
    assert hi_resp.content == canned_tts_mp3_bytes
    assert len(hi_resp.content) > 1000

    # Test empty text error
    bad_resp = client.post("/api/tts", json={"text": "   ", "language": "en"})
    assert bad_resp.status_code == 400
