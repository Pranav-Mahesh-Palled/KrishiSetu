"""Deterministic Arbitrage Engine for KrishiSetu.

Calculates road-adjusted distances, transport costs, perishability-based
transit spoilage deductions, net realizable prices, and net gains vs. local
mandi for agricultural markets.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Perishability transit spoilage rate multipliers per road kilometer
SPOILAGE_RATES_PER_KM = {
    "high": 0.0005,    # 0.05% loss per km (tomatoes, chillies, bananas)
    "medium": 0.0002,  # 0.02% loss per km (onions, potatoes)
    "low": 0.00005,    # 0.005% loss per km (soybean, maize, turmeric, cotton, paddy)
}

# Maximum transit spoilage cap (35%) to avoid unrealistic deductions on long-distance hauls
MAX_TRANSIT_SPOILAGE_RATE = 0.35

DEFAULT_BASE_TRANSPORT_PER_KM_QTL = 2.50  # ₹2.50 per km per quintal
ROAD_DISTANCE_FACTOR = 1.25  # Winding factor from great-circle to realistic Indian road distance


class MandiCandidate(BaseModel):
    """Input structure for an APMC Mandi price quote.

    Note on Produce Varieties: AGMARKNET quotes report modal prices for the commodity
    standard trading grade (e.g. FAQ - Fair Average Quality). This model preserves
    reported variety names where available, but price comparisons do not differentiate
    specialty sub-varieties (e.g., Jyoti vs Kufri for potato, or Nasik Red vs Bangalore Rose).
    """
    market: str
    district: str
    state: str
    latitude: float
    longitude: float
    modal_price: float
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    arrival_date: str = "2026-11-15"
    source: str = "verified_snapshot"  # 'live_api', 'verified_snapshot', or 'estimated_benchmark'
    variety: Optional[str] = "Standard"
    is_benchmark: bool = False
    dataset_id: Optional[str] = None
    fetched_at: Optional[datetime] = None
    freshness_status: Optional[str] = "cached"  # 'fresh', 'cached', 'stale', 'estimated', 'unavailable'
    retrieval_status: Optional[str] = "cache_hit"  # 'live_response', 'cache_hit', 'stale_cache_fallback', 'snapshot_fallback', 'benchmark', 'synthetic_fallback'
    data_age_seconds: Optional[float] = None


class MandiArbitrageResult(BaseModel):
    """Output structure representing distance and economics for a mandi."""
    market: str
    district: str
    state: str
    distance_km: float = Field(description="Road-adjusted transit distance in km")
    modal_price: float = Field(description="Wholesale modal price in ₹/qtl")
    transport_cost_per_qtl: float = Field(description="Total transport cost in ₹/qtl")
    spoilage_deduction_per_qtl: float = Field(description="Value loss during transit in ₹/qtl")
    net_price_per_qtl: float = Field(description="Net realizable price in ₹/qtl")
    net_gain_vs_local_total: float = Field(description="Total net gain or loss over local mandi in ₹ (0 for benchmarks)")
    is_local: bool = Field(default=False, description="Whether this is the local baseline market")
    arrival_date: str
    source: str
    variety: Optional[str] = "Standard"
    is_benchmark: bool = False
    dataset_id: Optional[str] = None
    fetched_at: Optional[datetime] = None
    freshness_status: Optional[str] = "cached"
    retrieval_status: Optional[str] = "cache_hit"
    data_age_seconds: Optional[float] = None


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two geographic coordinates using Haversine formula."""
    if abs(lat1 - lat2) < 1e-6 and abs(lon1 - lon2) < 1e-6:
        return 0.0

    R = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return R * c


def calculate_road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes realistic road distance using Haversine distance multiplied by 1.25 road adjustment factor."""
    straight_km = haversine_distance_km(lat1, lon1, lat2, lon2)
    if straight_km < 0.1:
        return 0.0
    return round(straight_km * ROAD_DISTANCE_FACTOR, 2)


def get_spoilage_rate_per_km(perishability_tier: str) -> float:
    """Returns transit spoilage rate per km according to crop perishability tier."""
    tier = (perishability_tier or "medium").strip().lower()
    return SPOILAGE_RATES_PER_KM.get(tier, SPOILAGE_RATES_PER_KM["medium"])


def calculate_mandi_arbitrage(
    origin_lat: float,
    origin_lon: float,
    quantity_quintals: float,
    mandis: List[MandiCandidate],
    perishability_tier: str = "medium",
    base_transport_per_km_qtl: float = DEFAULT_BASE_TRANSPORT_PER_KM_QTL,
) -> List[MandiArbitrageResult]:
    """Evaluates multi-mandi transport economics, ranks markets by net price, and computes gain vs local.

    Args:
        origin_lat: Farmer's origin latitude
        origin_lon: Farmer's origin longitude
        quantity_quintals: Batch size in quintals (qtl)
        mandis: List of MandiCandidate price observations
        perishability_tier: 'high', 'medium', or 'low'
        base_transport_per_km_qtl: Base cost ₹/km/quintal

    Returns:
        List of MandiArbitrageResult objects sorted descending by net_price_per_qtl
    """
    if not mandis:
        return []

    spoilage_rate_per_km = get_spoilage_rate_per_km(perishability_tier)

    # First pass: calculate road distance, transport cost, spoilage, and net price
    computed_items = []
    for m in mandis:
        road_km = calculate_road_distance_km(origin_lat, origin_lon, m.latitude, m.longitude)
        transport_cost = round(road_km * base_transport_per_km_qtl, 2)
        # Cap transit spoilage rate at MAX_TRANSIT_SPOILAGE_RATE (35%)
        spoilage_rate = min(MAX_TRANSIT_SPOILAGE_RATE, road_km * spoilage_rate_per_km)
        spoilage_deduction = round(m.modal_price * spoilage_rate, 2)
        net_price = round(m.modal_price - transport_cost - spoilage_deduction, 2)

        computed_items.append({
            "candidate": m,
            "distance_km": road_km,
            "transport_cost": transport_cost,
            "spoilage_deduction": spoilage_deduction,
            "net_price": net_price,
        })

    # Identify the local mandi baseline (closest by road distance)
    local_item = min(computed_items, key=lambda x: x["distance_km"])
    local_net_price = local_item["net_price"]
    local_market_name = local_item["candidate"].market
    local_is_benchmark = local_item["candidate"].is_benchmark

    # Second pass: compute net gain vs local mandi and build final result models
    results: List[MandiArbitrageResult] = []
    for item in computed_items:
        c = item["candidate"]
        is_local = (c.market == local_market_name)

        # Exclude unverified benchmark prices from claiming verified net-gain vs local
        if is_local or c.is_benchmark or local_is_benchmark:
            net_gain_total = 0.0
        else:
            net_gain_total = round((item["net_price"] - local_net_price) * quantity_quintals, 2)

        results.append(
            MandiArbitrageResult(
                market=c.market,
                district=c.district,
                state=c.state,
                distance_km=item["distance_km"],
                modal_price=c.modal_price,
                transport_cost_per_qtl=item["transport_cost"],
                spoilage_deduction_per_qtl=item["spoilage_deduction"],
                net_price_per_qtl=item["net_price"],
                net_gain_vs_local_total=net_gain_total,
                is_local=is_local,
                arrival_date=c.arrival_date,
                source=c.source,
                variety=c.variety,
                is_benchmark=c.is_benchmark,
                dataset_id=c.dataset_id,
                fetched_at=c.fetched_at,
                freshness_status=c.freshness_status,
                retrieval_status=c.retrieval_status,
                data_age_seconds=c.data_age_seconds,
            )
        )

    # Sort descending by net_price_per_qtl, prioritizing verified data over estimated benchmarks
    results.sort(key=lambda r: (not r.is_benchmark, r.net_price_per_qtl), reverse=True)
    return results


def determine_price_comparison_status(results: List[MandiArbitrageResult]) -> str:
    """Evaluates whether market quotations meet the criteria for a verified arbitrage recommendation.

    Criteria:
      1. Genuine live or verified local mandi quotation.
      2. At least one genuine live or verified alternative mandi quotation.
      3. Valid transport and spoilage calculations.

    Returns one of:
      - 'verified_comparison_available': Local baseline AND at least one alternative market have verified quotes.
      - 'local_baseline_missing': Alternative market(s) verified, but local baseline is missing or benchmark.
      - 'insufficient_alternative_quotes': Local baseline verified, but no alternative markets have verified quotes.
      - 'no_verified_price_data': Neither local nor any alternative markets have verified quotations.
    """
    if not results:
        return "no_verified_price_data"

    local_mandi = next((r for r in results if r.is_local), results[0])
    local_verified = (not local_mandi.is_benchmark) and (local_mandi.source in ["live_api", "verified_snapshot"])

    alternative_verified_count = sum(
        1 for r in results
        if not r.is_local and not r.is_benchmark and r.source in ["live_api", "verified_snapshot"]
    )

    if local_verified and alternative_verified_count > 0:
        return "verified_comparison_available"
    elif not local_verified and alternative_verified_count > 0:
        return "local_baseline_missing"
    elif local_verified and alternative_verified_count == 0:
        return "insufficient_alternative_quotes"
    else:
        return "no_verified_price_data"
