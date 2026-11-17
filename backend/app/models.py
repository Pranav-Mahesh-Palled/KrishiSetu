from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from backend.app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class MandiPricesCache(Base):
    """Cached wholesale market prices from AGMARKNET API or verified snapshots."""
    __tablename__ = "mandi_prices_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state = Column(String, nullable=False)
    district = Column(String, nullable=False)
    market = Column(String, nullable=False)
    commodity = Column(String, nullable=False)
    variety = Column(String, nullable=True)
    min_price = Column(Float, nullable=False)  # ₹ per quintal
    max_price = Column(Float, nullable=False)  # ₹ per quintal
    modal_price = Column(Float, nullable=False)  # ₹ per quintal
    arrival_date = Column(String, nullable=False)
    source = Column(String, nullable=False)  # 'live_api', 'verified_snapshot', or 'estimated_benchmark'
    dataset_id = Column(String, nullable=True)  # Official dataset identifier e.g. "9ef84268-d588-465a-a308-a864a43d0070"
    fetched_at = Column(DateTime, nullable=True, default=None)


class WeatherCache(Base):
    """Cached weather and soil moisture forecasts from Open-Meteo."""
    __tablename__ = "weather_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_key = Column(String, unique=True, nullable=False)  # rounded lat_lon e.g. "15.85_74.50"
    payload_json = Column(Text, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=utc_now)


class CropProfile(Base):
    """Agronomic and economic reference metadata for supported crops."""
    __tablename__ = "crop_profiles"

    crop_id = Column(String, primary_key=True)  # e.g., 'onion', 'tomato'
    display_name_en = Column(String, nullable=False)
    display_name_kn = Column(String, nullable=False)
    display_name_hi = Column(String, nullable=False)
    display_name_mr = Column(String, nullable=False)
    agmarknet_commodity = Column(String, nullable=False)
    perishability_tier = Column(String, nullable=False)  # 'high', 'medium', 'low'
    rain_sensitivity = Column(Float, nullable=False)  # 1.0 to 2.0 multiplier
    base_transport_per_km_qtl = Column(Float, nullable=False, default=2.50)  # default ₹2.50 / km / quintal
