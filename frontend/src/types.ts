export interface Language {
  code: string;
  label: string;
  native: string;
}

export interface CropProfile {
  crop_id: string;
  display_name_en: string;
  display_name_kn: string;
  display_name_hi: string;
  display_name_mr: string;
  agmarknet_commodity: string;
  perishability_tier: string;
  rain_sensitivity: number;
  base_transport_per_km_qtl: number;
}

export interface Preset {
  id: string;
  name: string;
  name_regional?: { [lang: string]: string };
  location_query: string;
  latitude: number;
  longitude: number;
  crop_id: string;
  quantity_quintals: number;
  state: string;
  mandis_count: number;
  mandi_details?: Array<{ market: string; latitude: number; longitude: number }>;
}

export interface PresetsResponse {
  presets: Preset[];
  crops: CropProfile[];
  languages: Language[];
}

export type FreshnessStatus = 'fresh' | 'cached' | 'stale' | 'estimated' | 'unavailable';
export type RetrievalStatus = 'live_response' | 'cache_hit' | 'stale_cache_fallback' | 'snapshot_fallback' | 'benchmark' | 'synthetic_fallback';
export type RefreshStatus = 'not_requested' | 'refreshed' | 'cooldown' | 'upstream_unavailable' | 'no_matching_records' | 'invalid_response';

export interface MandiFreshnessMetadata {
  freshness_status: FreshnessStatus;
  retrieval_status: RetrievalStatus;
  refresh_status?: RefreshStatus;
  cooldown_remaining_seconds?: number;
  last_fetched_at: string | null;
  oldest_fetched_at: string | null;
  live_quotes_count: number;
  cached_quotes_count: number;
  stale_quotes_count?: number;
  benchmark_quotes_count: number;
  total_mandis: number;
}

export interface WeatherFreshnessMetadata {
  freshness_status: FreshnessStatus;
  retrieval_status: RetrievalStatus;
  refresh_status?: RefreshStatus;
  cooldown_remaining_seconds?: number;
  data_source: string;
  fetched_at: string | null;
  data_age_seconds: number | null;
}

export interface FreshnessMetadata {
  mandi: MandiFreshnessMetadata;
  weather: WeatherFreshnessMetadata;
}

export interface DailyForecast {
  date: string;
  temp_max: number;
  temp_min: number;
  precipitation_mm: number;
  rain_prob_pct: number;
  weather_code: number;
}

export interface WeatherData {
  risk_level: 'SAFE_WINDOW' | 'HARVEST_WITHIN_48H' | 'HIGH_SPOILAGE_ALERT';
  rain_72h_mm: number;
  max_rain_prob_pct: number;
  soil_moisture_avg: number | null;
  soil_moisture_available?: boolean;
  headline: string;
  description: string;
  recommended_action: string;
  daily_forecast: DailyForecast[];
  fetched_at?: string | null;
  freshness_status?: FreshnessStatus;
  retrieval_status?: RetrievalStatus | string;
  data_age_seconds?: number | null;
  data_source?: string;
  refresh_status?: RefreshStatus;
  cooldown_remaining_seconds?: number;
}

export interface MandiItem {
  market: string;
  district: string;
  state: string;
  distance_km: number;
  modal_price: number;
  transport_cost_per_qtl: number;
  spoilage_deduction_per_qtl: number;
  net_price_per_qtl: number;
  net_gain_vs_local_total: number;
  is_local: boolean;
  arrival_date: string;
  data_source: string;
  variety?: string;
  is_benchmark?: boolean;
  dataset_id?: string | null;
  fetched_at?: string | null;
  freshness_status?: FreshnessStatus;
  retrieval_status?: RetrievalStatus | string;
  data_age_seconds?: number | null;
}

export interface AIAdvisory {
  headline: string;
  harvest_action: string;
  recommended_mandi: string;
  price_justification: string;
  protection_tips: string[];
  language: string;
}

export interface AnalysisResponse {
  location: {
    name: string;
    state: string;
    lat: number;
    lon: number;
  };
  weather: WeatherData;
  mandi_comparison: MandiItem[];
  ai_advisory: AIAdvisory;
  freshness_metadata?: FreshnessMetadata;
  coverage_status?: 'covered' | 'out_of_coverage' | 'insufficient_verified_price_data' | 'benchmark_estimates_only';
  coverage_warning?: string | null;
  price_comparison_status?: 'verified_comparison_available' | 'local_baseline_missing' | 'insufficient_alternative_quotes' | 'no_verified_price_data' | 'out_of_coverage';
  price_comparison_notice?: string | null;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
}
