"""Deterministic Weather Risk & Spoilage Classification Engine for KrishiSetu.

Classifies 72-hour harvest risk windows into:
- HIGH_SPOILAGE_ALERT
- HARVEST_WITHIN_48H
- SAFE_WINDOW

Based on cumulative rainfall, maximum rain probability, topsoil moisture,
and crop perishability tiers.
"""

from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field

RiskLevel = Literal["HIGH_SPOILAGE_ALERT", "HARVEST_WITHIN_48H", "SAFE_WINDOW"]


class WeatherRiskAssessment(BaseModel):
    """Structured assessment of harvest weather risks."""
    risk_level: RiskLevel
    rain_72h_mm: float = Field(description="Cumulative 72-hour precipitation volume in mm")
    max_rain_prob_pct: float = Field(description="Maximum precipitation probability in %")
    soil_moisture: Optional[float] = Field(
        default=None,
        description="Topsoil layer (0-7cm) volumetric moisture content in m³/m³"
    )
    perishability_tier: str = Field(description="Crop perishability tier (high, medium, low)")
    headline: str = Field(description="Short summary headline of harvest conditions")
    description: str = Field(description="Detailed reason for the assigned risk level")
    recommended_action: str = Field(description="Immediate actionable advice for the farmer")


def classify_weather_risk(
    rain_72h_mm: float,
    max_rain_prob_pct: float,
    soil_moisture: Optional[float] = None,
    perishability_tier: str = "medium",
    max_humidity_pct: Optional[float] = None,
) -> WeatherRiskAssessment:
    """Evaluates 72-hour weather window and topsoil moisture against agronomic thresholds.

    Rules as defined in Section 5:
    1. HIGH_SPOILAGE_ALERT:
       - Cumulative 72h rainfall >= 15 mm, OR
       - Max rain probability >= 70% for 'high' or 'medium' perishability crops.
    2. HARVEST_WITHIN_48H:
       - Cumulative 72h rainfall between 5 mm and 15 mm (5.0 <= rain < 15.0), OR
       - Topsoil moisture > 0.35 m³/m³.
    3. SAFE_WINDOW:
       - Rainfall < 5 mm, soil moisture <= 0.35, and stable humidity over next 72 hours.
    """
    tier = (perishability_tier or "medium").strip().lower()

    # Rule 1: High Spoilage Alert
    is_heavy_rain = rain_72h_mm >= 15.0
    is_high_prob_vulnerable = (max_rain_prob_pct >= 70.0) and (tier in ["high", "medium"])

    if is_heavy_rain or is_high_prob_vulnerable:
        reasons = []
        if is_heavy_rain:
            reasons.append(f"cumulative 72h rainfall of {rain_72h_mm:.1f} mm exceeds 15 mm threshold")
        if is_high_prob_vulnerable:
            reasons.append(f"imminent rain probability of {max_rain_prob_pct:.0f}% poses acute rot danger to {tier}-perishability produce")

        return WeatherRiskAssessment(
            risk_level="HIGH_SPOILAGE_ALERT",
            rain_72h_mm=round(rain_72h_mm, 2),
            max_rain_prob_pct=round(max_rain_prob_pct, 1),
            soil_moisture=round(soil_moisture, 3) if soil_moisture is not None else None,
            perishability_tier=tier,
            headline="High Spoilage Alert: Imminent Weather Threat",
            description=f"Severe risk detected: {'; '.join(reasons)}.",
            recommended_action="Postpone harvest if standing, or immediately cover harvested heaps with tarpaulins to prevent fungal rot and modal price discount.",
        )

    # Rule 2: Harvest Within 48h
    is_moderate_rain = 5.0 <= rain_72h_mm < 15.0
    is_saturated_soil = (soil_moisture is not None) and (soil_moisture > 0.35)

    if is_moderate_rain or is_saturated_soil:
        reasons = []
        if is_moderate_rain:
            reasons.append(f"expected 72h rainfall of {rain_72h_mm:.1f} mm (5–15 mm range)")
        if is_saturated_soil:
            reasons.append(f"topsoil moisture at {soil_moisture:.2f} m³/m³ exceeds safe harvesting limit of 0.35")

        return WeatherRiskAssessment(
            risk_level="HARVEST_WITHIN_48H",
            rain_72h_mm=round(rain_72h_mm, 2),
            max_rain_prob_pct=round(max_rain_prob_pct, 1),
            soil_moisture=round(soil_moisture, 3) if soil_moisture is not None else None,
            perishability_tier=tier,
            headline="Harvest Window Closing: Action Required Within 48h",
            description=f"Caution advised: {'; '.join(reasons)}.",
            recommended_action="Harvest mature crop within the next 24 to 48 hours before rainfall or saturated soil impedes field machinery and increases moisture deductions.",
        )

    # Rule 3: Safe Window
    soil_desc = (
        f"with soil moisture ({soil_moisture:.2f} m³/m³) within optimal threshold"
        if soil_moisture is not None
        else "with soil moisture measurement unavailable (field verification recommended)"
    )
    return WeatherRiskAssessment(
        risk_level="SAFE_WINDOW",
        rain_72h_mm=round(rain_72h_mm, 2),
        max_rain_prob_pct=round(max_rain_prob_pct, 1),
        soil_moisture=round(soil_moisture, 3) if soil_moisture is not None else None,
        perishability_tier=tier,
        headline="Safe Harvest Window: Favorable Weather",
        description=f"Dry conditions projected ({rain_72h_mm:.1f} mm rain, {max_rain_prob_pct:.0f}% max probability) {soil_desc}.",
        recommended_action="Optimal conditions for harvest, open-field sun curing, sorting, and dispatch to high-net-profit mandis.",
    )
