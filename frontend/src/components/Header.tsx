import React from 'react';
import { Sprout, Globe, CheckCircle2, Database, AlertTriangle, MapPinOff, CloudSun } from 'lucide-react';
import type { FreshnessMetadata, Language } from '../types';
import { formatRelativeTime, getFreshnessBadgeConfig } from '../utils/freshness';

interface HeaderProps {
  currentLanguage: string;
  languages: Language[];
  onLanguageChange: (langCode: string) => void;
  isLoading: boolean;
  freshnessMetadata?: FreshnessMetadata;
  dataSourceStatus?: 'live_api' | 'verified_snapshot' | 'estimated_benchmark' | 'insufficient_verified_price_data' | 'out_of_coverage';
  priceComparisonStatus?: 'verified_comparison_available' | 'local_baseline_missing' | 'insufficient_alternative_quotes' | 'no_verified_price_data' | 'out_of_coverage';
}

export const Header: React.FC<HeaderProps> = ({
  currentLanguage,
  languages,
  onLanguageChange,
  isLoading,
  freshnessMetadata,
  dataSourceStatus = 'verified_snapshot',
  priceComparisonStatus,
}) => {
  // Compute Mandi and Weather badges if metadata is provided
  const mandiRelative = freshnessMetadata?.mandi
    ? formatRelativeTime(freshnessMetadata.mandi.last_fetched_at)
    : undefined;
  const mandiBadge = freshnessMetadata?.mandi
    ? getFreshnessBadgeConfig(freshnessMetadata.mandi.freshness_status, 'mandi', mandiRelative)
    : null;

  const weatherRelative = freshnessMetadata?.weather
    ? formatRelativeTime(freshnessMetadata.weather.fetched_at)
    : undefined;
  const weatherBadge = freshnessMetadata?.weather
    ? getFreshnessBadgeConfig(freshnessMetadata.weather.freshness_status, 'weather', weatherRelative)
    : null;

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between">
        {/* Logo and Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-green-500 flex items-center justify-center text-white shadow-md shadow-emerald-200">
            <Sprout className="w-6 h-6 stroke-[2.2]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">
                KrishiSetu
              </h1>
              <span className="hidden sm:inline-block text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                ಕೃಷಿಸೇತು • कृषीसेतू
              </span>
            </div>
            <p className="text-xs text-slate-500 hidden lg:block">
              Multilingual Agritech & Harvest Arbitrage Advisory Assistant
            </p>
          </div>
        </div>

        {/* Right Controls: Independent Mandi & Weather Freshness & Language Switcher */}
        <div className="flex items-center gap-2.5">
          {/* Metadata-driven Independent Freshness Badges */}
          {freshnessMetadata ? (
            <div className="hidden lg:flex items-center gap-2">
              {/* Mandi Freshness Badge */}
              {mandiBadge && (
                <div
                  className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium ${mandiBadge.badgeClass}`}
                  title={`Mandi prices status: ${freshnessMetadata.mandi.freshness_status} (retrieval: ${freshnessMetadata.mandi.retrieval_status})`}
                >
                  <span className={`w-2 h-2 rounded-full ${mandiBadge.dotClass}`} />
                  <Database className="w-3.5 h-3.5" />
                  <span>{mandiBadge.label}</span>
                </div>
              )}

              {/* Weather Freshness Badge */}
              {weatherBadge && (
                <div
                  className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium ${weatherBadge.badgeClass}`}
                  title={`Weather forecast status: ${freshnessMetadata.weather.freshness_status} (source: ${freshnessMetadata.weather.data_source})`}
                >
                  <span className={`w-2 h-2 rounded-full ${weatherBadge.dotClass}`} />
                  <CloudSun className="w-3.5 h-3.5" />
                  <span>{weatherBadge.label}</span>
                </div>
              )}
            </div>
          ) : (
            /* Fallback heuristic badges if freshnessMetadata is not yet loaded */
            <>
              {priceComparisonStatus === 'verified_comparison_available' && (
                <div className="hidden lg:flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="font-semibold">
                    {dataSourceStatus === 'live_api' ? 'Live AGMARKNET (Verified Comparison)' : 'Verified Snapshot Comparison'}
                  </span>
                </div>
              )}
              {priceComparisonStatus === 'local_baseline_missing' && (
                <div className="hidden lg:flex items-center gap-1.5 text-xs text-amber-800 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-300">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  <span className="font-semibold">Local Baseline Missing</span>
                </div>
              )}
              {priceComparisonStatus === 'no_verified_price_data' && (
                <div className="hidden lg:flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  <span className="font-semibold">Estimated Benchmarks</span>
                </div>
              )}
              {(priceComparisonStatus === 'out_of_coverage' || (!priceComparisonStatus && dataSourceStatus === 'out_of_coverage')) && (
                <div className="hidden lg:flex items-center gap-1.5 text-xs text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-300">
                  <MapPinOff className="w-3.5 h-3.5 text-slate-500" />
                  <span className="font-medium">Outside Mandi Coverage</span>
                </div>
              )}
            </>
          )}

          {/* Language Toggle Pills */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <Globe className="w-4 h-4 text-slate-500 ml-2 mr-1 hidden sm:inline" />
            <div className="flex gap-1">
              {languages.map((lang) => {
                const isActive = currentLanguage === lang.code;
                return (
                  <button
                    key={lang.code}
                    onClick={() => onLanguageChange(lang.code)}
                    disabled={isLoading}
                    title={lang.label}
                    className={`px-2 sm:px-3 py-1 sm:py-1.5 text-[11px] sm:text-xs font-medium rounded-lg transition-all cursor-pointer ${
                      isActive
                        ? 'bg-emerald-600 text-white shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
                    } ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <span>{lang.native}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
