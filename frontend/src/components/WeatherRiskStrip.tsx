import React from 'react';
import { CloudRain, Sun, Droplets, AlertTriangle, ShieldCheck, Clock, Thermometer } from 'lucide-react';
import type { WeatherData } from '../types';
import { formatRelativeTime } from '../utils/freshness';

interface WeatherRiskStripProps {
  weather: WeatherData;
  locationName: string;
}

export const WeatherRiskStrip: React.FC<WeatherRiskStripProps> = ({ weather, locationName }) => {
  const getBadgeConfig = () => {
    switch (weather.risk_level) {
      case 'HIGH_SPOILAGE_ALERT':
        return {
          bg: 'bg-rose-50 border-rose-200 text-rose-800',
          badgeBg: 'bg-rose-600 text-white',
          icon: <AlertTriangle className="w-5 h-5 text-rose-600" />,
          label: 'High Spoilage Alert',
        };
      case 'HARVEST_WITHIN_48H':
        return {
          bg: 'bg-amber-50 border-amber-200 text-amber-800',
          badgeBg: 'bg-amber-500 text-slate-950 font-bold',
          icon: <Clock className="w-5 h-5 text-amber-600" />,
          label: 'Harvest Within 48 Hours',
        };
      case 'SAFE_WINDOW':
      default:
        return {
          bg: 'bg-emerald-50 border-emerald-200 text-emerald-800',
          badgeBg: 'bg-emerald-600 text-white',
          icon: <ShieldCheck className="w-5 h-5 text-emerald-600" />,
          label: 'Safe Harvest Window',
        };
    }
  };

  const badge = getBadgeConfig();
  const relativeTime = formatRelativeTime(weather.fetched_at);
  const isSynthetic =
    weather.retrieval_status === 'synthetic_fallback' ||
    weather.data_source === 'synthetic_baseline' ||
    weather.freshness_status === 'estimated';

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 p-4 sm:p-6 mb-6">
      {/* 72-Hour Risk Banner */}
      <div className={`rounded-xl p-4 border ${badge.bg} mb-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4`}>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-white rounded-lg shadow-2xs mt-0.5">{badge.icon}</div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold ${badge.badgeBg}`}>
                {badge.label}
              </span>
              <span className="text-xs text-slate-500 font-medium">{locationName} Coordinates</span>

              {/* Weather Data Freshness / Provenance Pill */}
              {weather.freshness_status === 'fresh' ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                  Open-Meteo Live {relativeTime ? `(${relativeTime})` : ''}
                </span>
              ) : weather.freshness_status === 'cached' ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                  Open-Meteo Cached {relativeTime ? `(${relativeTime})` : ''}
                </span>
              ) : weather.freshness_status === 'stale' ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-300">
                  Stale Forecast {relativeTime ? `(${relativeTime})` : '(>3h)'}
                </span>
              ) : isSynthetic ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-200 text-slate-700 border border-slate-300" title="Historical synthetic baseline (Live forecast unavailable)">
                  Synthetic Baseline
                </span>
              ) : null}
            </div>

            <h3 className="text-base font-bold mt-1 text-slate-900">{weather.headline}</h3>
            <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{weather.description}</p>

            {/* If synthetic baseline, surface honest fallback disclosure */}
            {isSynthetic && (
              <p className="text-[11px] text-amber-800 bg-amber-50/90 border border-amber-200 rounded-lg px-2.5 py-1.5 mt-2">
                <span className="font-semibold">Baseline Notice:</span> Live meteorological station unreachable. Using historical synthetic baseline for {locationName}. Spot precipitation should be verified locally.
              </p>
            )}
          </div>
        </div>

        {/* 3 Metric Pills */}
        <div className="grid grid-cols-3 gap-2 w-full md:w-auto shrink-0">
          <div className="bg-white/80 rounded-lg p-2.5 text-center border border-slate-200/60 shadow-2xs">
            <div className="flex items-center justify-center gap-1 text-slate-500 text-[11px] font-medium">
              <CloudRain className="w-3.5 h-3.5 text-blue-500" />
              <span>72h Rain</span>
            </div>
            <p className="text-sm font-bold text-slate-900 mt-0.5">
              {weather.rain_72h_mm.toFixed(1)} <span className="text-[10px] text-slate-500 font-normal">mm</span>
            </p>
          </div>

          <div className="bg-white/80 rounded-lg p-2.5 text-center border border-slate-200/60 shadow-2xs">
            <div className="flex items-center justify-center gap-1 text-slate-500 text-[11px] font-medium">
              <Sun className="w-3.5 h-3.5 text-amber-500" />
              <span>Max Prob</span>
            </div>
            <p className="text-sm font-bold text-slate-900 mt-0.5">
              {weather.max_rain_prob_pct.toFixed(0)} <span className="text-[10px] text-slate-500 font-normal">%</span>
            </p>
          </div>

          <div className="bg-white/80 rounded-lg p-2.5 text-center border border-slate-200/60 shadow-2xs">
            <div className="flex items-center justify-center gap-1 text-slate-500 text-[11px] font-medium">
              <Droplets className="w-3.5 h-3.5 text-cyan-600" />
              <span>Topsoil</span>
            </div>
            <p className="text-sm font-bold text-slate-900 mt-0.5">
              {weather.soil_moisture_avg != null ? (
                <>
                  {weather.soil_moisture_avg.toFixed(2)}{' '}
                  <span className="text-[9px] text-slate-500 font-normal">m³/m³</span>
                </>
              ) : (
                <span className="text-xs text-slate-400 font-normal" title="Soil moisture sensor measurement unavailable for grid cell">
                  N/A <span className="text-[9px] text-slate-400">(unmeasured)</span>
                </span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* 7-Day Forecast Mini Cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Thermometer className="w-3.5 h-3.5 text-emerald-600" />
            7-Day Weather & Precipitation Outlook (Open-Meteo)
          </p>
          {relativeTime && (
            <span className="text-[11px] font-normal text-slate-400">
              Fetched {relativeTime}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
          {weather.daily_forecast.map((day, idx) => (
            <div
              key={idx}
              className={`p-2.5 rounded-xl border text-center transition ${
                idx === 0
                  ? 'bg-emerald-50/60 border-emerald-300 ring-1 ring-emerald-200'
                  : 'bg-slate-50 border-slate-200/80'
              }`}
            >
              <p className="text-[11px] font-bold text-slate-700">
                {idx === 0 ? 'Today' : formatDate(day.date)}
              </p>
              <div className="my-1.5 flex items-center justify-center">
                {day.precipitation_mm > 5 ? (
                  <CloudRain className="w-5 h-5 text-blue-500" />
                ) : day.precipitation_mm > 0 ? (
                  <CloudRain className="w-5 h-5 text-slate-400" />
                ) : (
                  <Sun className="w-5 h-5 text-amber-500" />
                )}
              </div>
              <p className="text-xs font-bold text-slate-900">
                {Math.round(day.temp_max)}° / {Math.round(day.temp_min)}°
              </p>
              <div className="mt-1 text-[10px] text-slate-500 flex items-center justify-center gap-1">
                <span>{day.precipitation_mm.toFixed(1)}mm</span>
                <span>•</span>
                <span className={day.rain_prob_pct > 50 ? 'text-rose-600 font-semibold' : ''}>
                  {Math.round(day.rain_prob_pct)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
