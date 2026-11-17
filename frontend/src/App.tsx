import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw, CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';
import type { AnalysisResponse, CropProfile, Language, Preset } from './types';
import { fetchPresets, analyzeHarvestAndSale } from './api';
import { Header } from './components/Header';
import { ControlBar } from './components/ControlBar';
import { HeroAdvisoryCard } from './components/HeroAdvisoryCard';
import { WeatherRiskStrip } from './components/WeatherRiskStrip';
import { MandiComparison } from './components/MandiComparison';
import { ChatDrawer } from './components/ChatDrawer';

interface RefreshNotification {
  type: 'success' | 'warning' | 'info';
  title: string;
  message: string;
}

export const App: React.FC = () => {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [crops, setCrops] = useState<CropProfile[]>([]);
  const [languages, setLanguages] = useState<Language[]>([
    { code: 'en', label: 'English', native: 'English' },
    { code: 'kn', label: 'Kannada', native: 'ಕನ್ನಡ' },
    { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
    { code: 'mr', label: 'Marathi', native: 'मराठी' },
  ]);

  const [currentLanguage, setCurrentLanguage] = useState<string>('en');
  const [activePresetId, setActivePresetId] = useState<string | null>(null);

  const [locationQuery, setLocationQuery] = useState<string>('Belagavi, Karnataka');
  const [latitude, setLatitude] = useState<number | null>(15.8497);
  const [longitude, setLongitude] = useState<number | null>(74.4977);
  const [selectedCropId, setSelectedCropId] = useState<string>('onion');
  const [quantity, setQuantity] = useState<number>(30);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [cooldownSeconds, setCooldownSeconds] = useState<number>(0);
  const [refreshNotification, setRefreshNotification] = useState<RefreshNotification | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Active cooldown countdown timer
  useEffect(() => {
    if (cooldownSeconds <= 0) return;
    const interval = setInterval(() => {
      setCooldownSeconds((prev) => (prev > 1 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldownSeconds]);

  // Auto-dismiss refresh notification after 8 seconds
  useEffect(() => {
    if (!refreshNotification) return;
    const timer = setTimeout(() => {
      setRefreshNotification(null);
    }, 8000);
    return () => clearTimeout(timer);
  }, [refreshNotification]);

  // Executes standard harvest and mandi arbitrage analysis
  const runAnalysis = useCallback(
    async (params: {
      location_query: string;
      latitude?: number | null;
      longitude?: number | null;
      crop_id: string;
      quantity_quintals: number;
      language: string;
    }) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await analyzeHarvestAndSale(params);
        setAnalysis(data);
      } catch (err: any) {
        setError(err.message || 'Failed to complete analysis. Please verify your connection.');
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Executes safe manual refresh bypassing standard cache TTL
  const handleManualRefresh = async () => {
    if (isLoading || isRefreshing || cooldownSeconds > 0) return;

    setIsRefreshing(true);
    try {
      const data = await analyzeHarvestAndSale({
        location_query: locationQuery,
        latitude,
        longitude,
        crop_id: selectedCropId,
        quantity_quintals: quantity,
        language: currentLanguage,
        force_refresh: true,
      });

      // Update active analysis without destroying dashboard layout
      setAnalysis(data);

      const mandiMeta = data.freshness_metadata?.mandi;
      const weatherMeta = data.freshness_metadata?.weather;

      // Extract cooldown seconds if any returned by backend
      const mandiCooldown = mandiMeta?.cooldown_remaining_seconds || 0;
      const weatherCooldown = weatherMeta?.cooldown_remaining_seconds || 0;
      const maxCooldown = Math.max(mandiCooldown, weatherCooldown);
      if (maxCooldown > 0) {
        setCooldownSeconds(maxCooldown);
      }

      // Contextual notification based on independent refresh outcomes
      const mandiStatus = mandiMeta?.refresh_status;
      const weatherStatus = weatherMeta?.refresh_status;
      const isBenchmarkOnly =
        data.coverage_status === 'benchmark_estimates_only' ||
        (data.mandi_comparison?.length > 0 && data.mandi_comparison.every((m: any) => m.is_benchmark));

      if (mandiStatus === 'refreshed' && weatherStatus === 'refreshed') {
        setRefreshNotification({
          type: 'success',
          title: 'Prices & Weather Refreshed',
          message: 'Fetched latest official AGMARKNET quotations and Open-Meteo 7-day outlook.',
        });
      } else if (mandiStatus === 'refreshed' && weatherStatus === 'cooldown') {
        setRefreshNotification({
          type: 'info',
          title: 'Mandi Prices Refreshed',
          message: `Updated mandi prices with live AGMARKNET quotes. Weather is in cooldown (${weatherCooldown}s remaining).`,
        });
      } else if (weatherStatus === 'refreshed' && mandiStatus === 'cooldown') {
        setRefreshNotification({
          type: 'info',
          title: 'Weather Forecast Refreshed',
          message: `Updated Open-Meteo forecast. Mandi prices in cooldown (${mandiCooldown}s remaining).`,
        });
      } else if (mandiStatus === 'refreshed') {
        setRefreshNotification({
          type: 'info',
          title: 'Mandi Prices Refreshed',
          message: 'Updated mandi quotations with latest AGMARKNET returns.',
        });
      } else if (weatherStatus === 'refreshed') {
        setRefreshNotification({
          type: 'info',
          title: 'Weather Forecast Refreshed',
          message: 'Updated Open-Meteo forecast with latest 7-day outlook.',
        });
      } else if (mandiStatus === 'cooldown' || weatherStatus === 'cooldown') {
        setRefreshNotification({
          type: 'info',
          title: 'Cooldown Active',
          message: `Rate limit active to protect upstream servers. Please wait ${maxCooldown}s before refreshing again.`,
        });
      } else if (mandiStatus === 'upstream_unavailable' || weatherStatus === 'upstream_unavailable') {
        const retainedType = isBenchmarkOnly ? 'benchmark estimates' : 'cached records';
        setRefreshNotification({
          type: 'warning',
          title: 'Upstream Service Unavailable',
          message: `Upstream service did not respond. Retained existing ${retainedType}.`,
        });
      } else if (mandiStatus === 'no_matching_records') {
        setRefreshNotification({
          type: 'info',
          title: 'No Matching Quotations',
          message: 'Upstream AGMARKNET portal responded, but returned no matching quotations for this crop in nearby markets today.',
        });
      } else if (mandiStatus === 'invalid_response') {
        setRefreshNotification({
          type: 'warning',
          title: 'Invalid Upstream Response',
          message: 'Upstream returned invalid data format. Existing records preserved.',
        });
      } else {
        setRefreshNotification({
          type: 'info',
          title: 'Refresh Evaluated',
          message: 'Evaluated market and weather data. Existing cached records are current.',
        });
      }
    } catch (err: any) {
      setRefreshNotification({
        type: 'warning',
        title: 'Refresh Request Failed',
        message: err.message || 'Could not complete refresh request. Please verify server connection.',
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  // Initial load: Fetch presets & auto-run Preset 1 (Belagavi - Onion)
  useEffect(() => {
    let isMounted = true;
    async function init() {
      try {
        const presetsData = await fetchPresets();
        if (!isMounted) return;

        setPresets(presetsData.presets || []);
        setCrops(presetsData.crops || []);
        if (presetsData.languages?.length > 0) {
          setLanguages(presetsData.languages);
        }

        // Auto-select first preset
        if (presetsData.presets && presetsData.presets.length > 0) {
          const firstPreset = presetsData.presets[0];
          setActivePresetId(firstPreset.id);
          setLocationQuery(firstPreset.location_query);
          setLatitude(firstPreset.latitude);
          setLongitude(firstPreset.longitude);
          setSelectedCropId(firstPreset.crop_id);
          setQuantity(firstPreset.quantity_quintals);

          await runAnalysis({
            location_query: firstPreset.location_query,
            latitude: firstPreset.latitude,
            longitude: firstPreset.longitude,
            crop_id: firstPreset.crop_id,
            quantity_quintals: firstPreset.quantity_quintals,
            language: currentLanguage,
          });
        }
      } catch (err: any) {
        if (!isMounted) return;
        setError(err.message || 'Could not connect to backend server. Please verify FastAPI is running on port 8000.');
        setIsLoading(false);
      }
    }

    init();
    return () => {
      isMounted = false;
    };
  }, [runAnalysis, currentLanguage]);

  // When language changes, immediately re-run analysis in the new language
  const handleLanguageChange = (langCode: string) => {
    setCurrentLanguage(langCode);
    runAnalysis({
      location_query: locationQuery,
      latitude,
      longitude,
      crop_id: selectedCropId,
      quantity_quintals: quantity,
      language: langCode,
    });
  };

  // When user clicks a 1-click preset pill
  const handleSelectPreset = (preset: Preset) => {
    setActivePresetId(preset.id);
    setLocationQuery(preset.location_query);
    setLatitude(preset.latitude);
    setLongitude(preset.longitude);
    setSelectedCropId(preset.crop_id);
    setQuantity(preset.quantity_quintals);

    runAnalysis({
      location_query: preset.location_query,
      latitude: preset.latitude,
      longitude: preset.longitude,
      crop_id: preset.crop_id,
      quantity_quintals: preset.quantity_quintals,
      language: currentLanguage,
    });
  };

  // When user submits custom location/crop form
  const handleCustomSubmit = () => {
    setActivePresetId(null);
    runAnalysis({
      location_query: locationQuery,
      latitude: null, // Clear lat/lon to trigger Open-Meteo geocoding for custom query
      longitude: null,
      crop_id: selectedCropId,
      quantity_quintals: quantity,
      language: currentLanguage,
    });
  };

  // Determine fallback data provenance status for header badge
  const dataSourceStatus = React.useMemo(() => {
    if (!analysis) return 'verified_snapshot';
    if (analysis.coverage_status === 'out_of_coverage' || analysis.mandi_comparison.length === 0) {
      return 'out_of_coverage';
    }
    if (analysis.coverage_status === 'insufficient_verified_price_data') {
      return 'insufficient_verified_price_data';
    }
    if (analysis.mandi_comparison.some((m) => m.data_source === 'live_api')) {
      return 'live_api';
    }
    if (analysis.mandi_comparison.every((m) => m.is_benchmark || m.data_source === 'estimated_benchmark')) {
      return 'insufficient_verified_price_data';
    }
    return 'verified_snapshot';
  }, [analysis]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* Top Navigation & Language Switcher */}
      <Header
        currentLanguage={currentLanguage}
        languages={languages}
        onLanguageChange={handleLanguageChange}
        isLoading={isLoading}
        freshnessMetadata={analysis?.freshness_metadata}
        dataSourceStatus={dataSourceStatus}
        priceComparisonStatus={analysis?.price_comparison_status}
      />

      {/* Main Dashboard Container */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
        {/* Search & 1-Click Demo Presets Bar */}
        <ControlBar
          presets={presets}
          crops={crops}
          currentLanguage={currentLanguage}
          activePresetId={activePresetId}
          locationQuery={locationQuery}
          selectedCropId={selectedCropId}
          quantity={quantity}
          isLoading={isLoading}
          isRefreshing={isRefreshing}
          cooldownSeconds={cooldownSeconds}
          onSelectPreset={handleSelectPreset}
          onLocationChange={setLocationQuery}
          onCropChange={setSelectedCropId}
          onQuantityChange={setQuantity}
          onSubmit={handleCustomSubmit}
          onRefresh={handleManualRefresh}
        />

        {/* Refresh Toast / Notification Banner */}
        {refreshNotification && (
          <div
            role="status"
            aria-live="polite"
            className={`rounded-2xl p-4 mb-6 flex items-start gap-3 shadow-xs border transition-all ${
              refreshNotification.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                : refreshNotification.type === 'warning'
                ? 'bg-amber-50 border-amber-200 text-amber-900'
                : 'bg-indigo-50 border-indigo-200 text-indigo-900'
            }`}
          >
            {refreshNotification.type === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            ) : refreshNotification.type === 'warning' ? (
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            ) : (
              <Info className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <p className="text-sm font-bold">{refreshNotification.title}</p>
              <p className="text-xs mt-0.5 leading-relaxed">{refreshNotification.message}</p>
            </div>
            <button
              onClick={() => setRefreshNotification(null)}
              className="text-xs p-1 text-slate-400 hover:text-slate-600 cursor-pointer rounded-lg hover:bg-black/5"
              aria-label="Dismiss notification"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Error Alert Box */}
        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-2xl p-4 mb-6 flex items-start gap-3 shadow-xs">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-bold text-rose-900">Analysis Error</p>
              <p className="text-xs text-rose-700 mt-0.5">{error}</p>
            </div>
            <button
              onClick={handleCustomSubmit}
              className="text-xs font-semibold text-rose-800 hover:text-rose-900 bg-white px-3 py-1.5 rounded-lg border border-rose-300 flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
          </div>
        )}

        {/* Loading Spinner Skeleton */}
        {isLoading && !analysis && (
          <div className="flex flex-col items-center justify-center py-20 bg-white rounded-2xl border border-slate-200/80 shadow-xs">
            <Loader2 className="w-10 h-10 animate-spin text-emerald-600 mb-4" />
            <p className="text-base font-bold text-slate-800">
              Synthesizing Hyper-Local Weather & Mandi Arbitrage...
            </p>
            <p className="text-xs text-slate-500 max-w-md text-center mt-1">
              Calculating road-adjusted distances, 72-hour precipitation risks, and transit spoilage across nearby APMC markets
            </p>
          </div>
        )}

        {/* Main Content Dashboard */}
        {analysis && (
          <div className="space-y-6">
            {/* Hero AI Decision Action Plan */}
            <HeroAdvisoryCard
              advisory={analysis.ai_advisory}
              topMandi={analysis.mandi_comparison[0]}
              quantity={quantity}
              language={currentLanguage}
              priceComparisonStatus={analysis.price_comparison_status}
              priceComparisonNotice={analysis.price_comparison_notice}
            />

            {/* Weather & Soil Moisture Risk Strip */}
            <WeatherRiskStrip
              weather={analysis.weather}
              locationName={analysis.location?.name || locationQuery}
            />

            {/* Mandi Profit Arbitrage Comparison Table & Chart */}
            <MandiComparison
              mandis={analysis.mandi_comparison}
              quantity={quantity}
              coverageWarning={analysis.coverage_warning}
              priceComparisonStatus={analysis.price_comparison_status}
              priceComparisonNotice={analysis.price_comparison_notice}
            />

            {/* Multilingual Regional Voice & Text Q&A Panel */}
            <ChatDrawer
              analysisContext={analysis as any}
              language={currentLanguage}
            />
          </div>
        )}
      </main>

      {/* Footer & Hackathon Attribution */}
      <footer className="bg-white border-t border-slate-200 py-6 mt-12 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-800">KrishiSetu</span>
            <span>•</span>
            <span>IDEA//FORGE Hackathon 2026 (Track 2: Climate & Global Supply Resilience)</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-4 text-slate-600">
            <span>
              Weather & Topsoil:{' '}
              <a
                href="https://open-meteo.com/"
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-emerald-700"
              >
                Open-Meteo
              </a>
            </span>
            <span>•</span>
            <span>
              Mandi Prices:{' '}
              <a
                href="https://data.gov.in/"
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-emerald-700"
              >
                data.gov.in AGMARKNET
              </a>
            </span>
            <span>•</span>
            <span>
              AI Reasoning:{' '}
              <a
                href="https://ai.google.dev/"
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-emerald-700"
              >
                Google Gemini
              </a>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
