import React, { useState } from 'react';
import { Volume2, VolumeX, Sparkles, TrendingUp, ShieldCheck, CheckCircle, Store, AlertCircle } from 'lucide-react';
import type { AIAdvisory, MandiItem } from '../types';
import { speakText, stopSpeaking } from '../utils/speech';

interface HeroAdvisoryCardProps {
  advisory: AIAdvisory;
  topMandi?: MandiItem;
  quantity: number;
  language: string;
  priceComparisonStatus?: string;
  priceComparisonNotice?: string | null;
}

export const HeroAdvisoryCard: React.FC<HeroAdvisoryCardProps> = ({
  advisory,
  topMandi,
  quantity,
  language,
  priceComparisonStatus = 'verified_comparison_available',
  priceComparisonNotice,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  const handleToggleVoice = async () => {
    if (isPlaying) {
      stopSpeaking();
      setIsPlaying(false);
      return;
    }

    setAudioError(null);
    // Combine core advisory into spoken synthesis script
    const spokenScript = `${advisory.headline}. ${advisory.harvest_action}. ${advisory.price_justification}`;

    try {
      await speakText(spokenScript, language, {
        onStart: () => setIsPlaying(true),
        onEnd: () => setIsPlaying(false),
        onError: () => {
          setIsPlaying(false);
          setAudioError('Voice playback encountered an issue. Falling back to text.');
        },
      });
    } catch (e) {
      setIsPlaying(false);
      setAudioError('Voice playback unavailable.');
    }
  };

  return (
    <div className="bg-gradient-to-br from-emerald-900 via-emerald-800 to-slate-900 rounded-2xl text-white shadow-lg p-5 sm:p-7 mb-6 relative overflow-hidden">
      {/* Decorative Background Accents */}
      <div className="absolute -top-12 -right-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-64 h-64 bg-green-400/5 rounded-full blur-3xl pointer-events-none" />

      {/* Header Badge & Voice Button */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-semibold border border-emerald-400/30">
            <Sparkles className="w-3.5 h-3.5" />
            AI Harvest & Arbitrage Action Plan
          </span>

          {priceComparisonStatus === 'verified_comparison_available' && topMandi && !topMandi.is_benchmark && topMandi.net_gain_vs_local_total > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 text-xs font-semibold border border-amber-400/30">
              <TrendingUp className="w-3 h-3" />
              +₹{Math.round(topMandi.net_gain_vs_local_total).toLocaleString('en-IN')} Arbitrage Gain
            </span>
          )}

          {priceComparisonStatus === 'verified_comparison_available' && topMandi && topMandi.is_local && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-semibold border border-emerald-400/30">
              <CheckCircle className="w-3 h-3" />
              Local Mandi Highest Net Return
            </span>
          )}

          {priceComparisonStatus === 'local_baseline_missing' && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 text-xs font-semibold border border-amber-400/30">
              <AlertCircle className="w-3 h-3" />
              Local Baseline Missing (Reference Quotes)
            </span>
          )}

          {priceComparisonStatus === 'insufficient_alternative_quotes' && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-semibold border border-blue-400/30">
              <CheckCircle className="w-3 h-3" />
              Verified Local Sale Recommended
            </span>
          )}

          {priceComparisonStatus === 'no_verified_price_data' && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-300 text-xs font-semibold border border-amber-400/30">
              <AlertCircle className="w-3 h-3" />
              Estimated Benchmarks Only
            </span>
          )}
        </div>

        {/* Listen Voice Button */}
        <button
          onClick={handleToggleVoice}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-medium transition cursor-pointer border shrink-0 ${
            isPlaying
              ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-md animate-pulse font-bold'
              : 'bg-white/10 hover:bg-white/20 text-white border-white/20'
          }`}
          title="Listen to regional voice advisory"
        >
          {isPlaying ? (
            <>
              <VolumeX className="w-4 h-4" />
              <span>Stop Audio</span>
            </>
          ) : (
            <>
              <Volume2 className="w-4 h-4 text-emerald-300" />
              <span>Listen to Advisory</span>
            </>
          )}
        </button>
      </div>

      {audioError && (
        <div className="mb-3 text-xs text-amber-300 flex items-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{audioError}</span>
        </div>
      )}

      {/* Hero Headline */}
      <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-white mb-2 leading-snug">
        {advisory.headline}
      </h2>

      {/* Explicit Recommendation Integrity Notice */}
      {priceComparisonNotice && (
        <p className="text-xs text-emerald-200/90 mb-4 bg-white/5 rounded-lg px-3 py-1.5 border border-white/10">
          {priceComparisonNotice}
        </p>
      )}

      {/* Recommended Market Callout Box */}
      {topMandi && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-white/10 backdrop-blur-xs rounded-xl p-3.5 mb-5 border border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-300">
              <Store className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-emerald-200/80 font-medium">Recommended Market</p>
              <p className="text-base font-bold text-white">{advisory.recommended_mandi}</p>
            </div>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wider text-emerald-200/80 font-medium">Net Realizable Price</p>
            <p className="text-base font-bold text-white">
              ₹{Math.round(topMandi.net_price_per_qtl).toLocaleString('en-IN')}{' '}
              <span className="text-xs font-normal text-slate-300">/ quintal</span>
            </p>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wider text-emerald-200/80 font-medium">Total Net Gain vs Local</p>
            {priceComparisonStatus === 'verified_comparison_available' ? (
              <p className={`text-base font-bold ${topMandi.net_gain_vs_local_total > 0 ? 'text-amber-300' : 'text-slate-300'}`}>
                {topMandi.net_gain_vs_local_total > 0
                  ? `+₹${Math.round(topMandi.net_gain_vs_local_total).toLocaleString('en-IN')} (for ${quantity} qtl)`
                  : '₹0 (Local Best Net Return)'}
              </p>
            ) : priceComparisonStatus === 'local_baseline_missing' ? (
              <p className="text-xs font-semibold text-amber-300 mt-1">
                Local baseline unverified (Check spot rate)
              </p>
            ) : priceComparisonStatus === 'insufficient_alternative_quotes' ? (
              <p className="text-xs font-semibold text-emerald-300 mt-1">
                Local sale recommended (No alt quotes)
              </p>
            ) : (
              <p className="text-xs font-semibold text-slate-300 mt-1">
                Benchmark data only (No arbitrage)
              </p>
            )}
          </div>
        </div>
      )}

      {/* Two Column Layout: Harvest Timing + Price Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">
        {/* Harvest Urgency Action */}
        <div className="bg-black/20 rounded-xl p-4 border border-white/5">
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-400 mb-1.5 flex items-center gap-1.5">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            Harvest Timing & Urgency
          </p>
          <p className="text-sm text-slate-200 leading-relaxed">
            {advisory.harvest_action}
          </p>
        </div>

        {/* Transport & Net Price Justification */}
        <div className="bg-black/20 rounded-xl p-4 border border-white/5">
          <p className="text-xs font-bold uppercase tracking-wider text-amber-300 mb-1.5 flex items-center gap-1.5">
            <TrendingUp className="w-4 h-4 text-amber-300" />
            Transport & Spoilage Math Breakdown
          </p>
          <p className="text-sm text-slate-200 leading-relaxed">
            {advisory.price_justification}
          </p>
        </div>
      </div>

      {/* Protection Tips Checklist */}
      {advisory.protection_tips && advisory.protection_tips.length > 0 && (
        <div className="border-t border-white/10 pt-4">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2.5 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            Crop Quality & Transit Precautions
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            {advisory.protection_tips.map((tip, idx) => (
              <div key={idx} className="flex items-start gap-2 text-xs text-slate-200 bg-white/5 rounded-lg p-2.5">
                <span className="w-4 h-4 rounded-full bg-emerald-500/30 text-emerald-300 flex items-center justify-center text-[10px] shrink-0 font-bold mt-0.5">
                  {idx + 1}
                </span>
                <span className="leading-snug">{tip}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
