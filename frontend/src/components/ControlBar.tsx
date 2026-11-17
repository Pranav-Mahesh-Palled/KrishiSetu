import React from 'react';
import { MapPin, Sparkles, Search, Layers, Loader2, RefreshCw, Clock } from 'lucide-react';
import type { CropProfile, Preset } from '../types';

interface ControlBarProps {
  presets: Preset[];
  crops: CropProfile[];
  currentLanguage: string;
  activePresetId: string | null;
  locationQuery: string;
  selectedCropId: string;
  quantity: number;
  isLoading: boolean;
  isRefreshing?: boolean;
  cooldownSeconds?: number;
  onSelectPreset: (preset: Preset) => void;
  onLocationChange: (val: string) => void;
  onCropChange: (cropId: string) => void;
  onQuantityChange: (qty: number) => void;
  onSubmit: () => void;
  onRefresh?: () => void;
}

export const ControlBar: React.FC<ControlBarProps> = ({
  presets,
  crops,
  currentLanguage,
  activePresetId,
  locationQuery,
  selectedCropId,
  quantity,
  isLoading,
  isRefreshing = false,
  cooldownSeconds = 0,
  onSelectPreset,
  onLocationChange,
  onCropChange,
  onQuantityChange,
  onSubmit,
  onRefresh,
}) => {
  const getLocalizedCropName = (crop: CropProfile): string => {
    switch (currentLanguage) {
      case 'kn':
        return `${crop.display_name_kn} (${crop.display_name_en})`;
      case 'hi':
        return `${crop.display_name_hi} (${crop.display_name_en})`;
      case 'mr':
        return `${crop.display_name_mr} (${crop.display_name_en})`;
      default:
        return crop.display_name_en;
    }
  };

  const getLocalizedPresetName = (preset: Preset): string => {
    if (preset.name_regional && preset.name_regional[currentLanguage]) {
      return preset.name_regional[currentLanguage];
    }
    return preset.name;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 p-4 sm:p-6 mb-6">
      {/* 1-Click Demo Presets Strip */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            <span>1-Click Hackathon Demo Presets</span>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">
            Curated regional clusters with verified wholesale snapshots
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => {
            const isSelected = activePresetId === preset.id;
            return (
              <button
                key={preset.id}
                onClick={() => onSelectPreset(preset)}
                disabled={isLoading || isRefreshing}
                className={`px-3.5 py-2 rounded-xl text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer border ${
                  isSelected
                    ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm font-semibold ring-2 ring-emerald-200'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100 hover:border-slate-300'
                }`}
              >
                <span>{getLocalizedPresetName(preset)}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-md ${
                  isSelected ? 'bg-emerald-700/60 text-emerald-100' : 'bg-slate-200 text-slate-600'
                }`}>
                  {preset.state}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Search & Control Form */}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
        {/* Location Input */}
        <div className="md:col-span-3">
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            Town, Taluk or District
          </label>
          <div className="relative">
            <MapPin className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={locationQuery}
              onChange={(e) => onLocationChange(e.target.value)}
              placeholder="e.g. Belagavi, Kolar, Nashik..."
              required
              className="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:bg-white text-slate-800 placeholder-slate-400 transition"
            />
          </div>
        </div>

        {/* Crop Selector */}
        <div className="md:col-span-3">
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            Agricultural Commodity
          </label>
          <div className="relative">
            <Layers className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <select
              value={selectedCropId}
              onChange={(e) => onCropChange(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:bg-white text-slate-800 transition appearance-none cursor-pointer"
            >
              {crops.map((c) => (
                <option key={c.crop_id} value={c.crop_id}>
                  {getLocalizedCropName(c)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Quantity Input */}
        <div className="md:col-span-2">
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            Quantity (Quintals)
          </label>
          <input
            type="number"
            min="1"
            max="1000"
            value={quantity}
            onChange={(e) => onQuantityChange(Number(e.target.value))}
            required
            className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-hidden focus:ring-2 focus:ring-emerald-500 focus:bg-white text-slate-800 transition"
          />
        </div>

        {/* Dual Action Buttons: Primary Analyze + Manual Refresh */}
        <div className="md:col-span-4 flex items-center gap-2">
          {/* Primary Submit Button */}
          <button
            type="submit"
            disabled={isLoading || isRefreshing}
            className="flex-1 py-2.5 px-3 bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-1.5 shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                <span className="truncate">Analyzing...</span>
              </>
            ) : (
              <>
                <Search className="w-4 h-4 shrink-0" />
                <span className="truncate">Analyze Mandi</span>
              </>
            )}
          </button>

          {/* Manual Refresh Button */}
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading || isRefreshing || cooldownSeconds > 0}
              title={
                cooldownSeconds > 0
                  ? `Refresh rate limit: ${cooldownSeconds}s cooldown remaining`
                  : 'Bypass cache to fetch latest AGMARKNET prices & Open-Meteo weather'
              }
              aria-label="Refresh Prices and Weather"
              className={`py-2.5 px-3 rounded-xl text-xs sm:text-sm font-medium transition flex items-center justify-center gap-1.5 border shadow-2xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                cooldownSeconds > 0
                  ? 'bg-slate-100 text-slate-400 border-slate-200'
                  : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-300 hover:border-slate-400'
              }`}
            >
              {isRefreshing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-emerald-600 shrink-0" />
                  <span className="truncate">Refreshing...</span>
                </>
              ) : cooldownSeconds > 0 ? (
                <>
                  <Clock className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>{cooldownSeconds}s</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span className="truncate">Refresh</span>
                </>
              )}
            </button>
          )}
        </div>
      </form>
    </div>
  );
};
