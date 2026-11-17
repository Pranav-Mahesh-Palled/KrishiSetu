import React from 'react';
import { BarChart3, Award, Check, AlertTriangle, MapPinOff, Calendar, Clock } from 'lucide-react';
import type { MandiItem } from '../types';
import { formatRelativeTime } from '../utils/freshness';

interface MandiComparisonProps {
  mandis: MandiItem[];
  quantity: number;
  coverageWarning?: string | null;
  priceComparisonStatus?: string;
  priceComparisonNotice?: string | null;
}

export const MandiComparison: React.FC<MandiComparisonProps> = ({
  mandis,
  quantity,
  coverageWarning,
  priceComparisonStatus = 'verified_comparison_available',
  priceComparisonNotice,
}) => {
  if (!mandis || mandis.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 p-6 mb-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-700 shrink-0">
            <MapPinOff className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">
              No APMC Mandis Within 150 km Coverage Area
            </h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              {coverageWarning ||
                'Your location is beyond the 150 km road transit radius of our curated APMC hub network. KrishiSetu coverage currently spans major agricultural clusters in Karnataka, Maharashtra, and adjacent borders.'}
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Tip: For long-haul inter-state transport, verify local village procurement centers or your state agricultural marketing board portal.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Max price across all mandis to scale the horizontal comparison bars
  const maxPrice = Math.max(...mandis.map((m) => Math.max(m.modal_price, m.net_price_per_qtl)));

  return (
    <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 p-4 sm:p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-5">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-emerald-600" />
            Mandi Net-Profit Arbitrage Comparison
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            True net realizations ranked after distance transport costs and crop perishability spoilage deductions
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-slate-300 inline-block" />
            <span className="text-slate-600">Modal Price</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-emerald-500 inline-block" />
            <span className="text-slate-900 font-semibold">Net Realizable</span>
          </div>
        </div>
      </div>

      {/* Context-Aware Data Provenance & Recommendation Notice Banner */}
      {priceComparisonStatus === 'local_baseline_missing' ? (
        <div className="mb-4 p-3.5 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 flex items-start gap-2.5 text-xs shadow-xs">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Local Baseline Price Missing (Quotes Shown for Reference Only): </span>
            {priceComparisonNotice || 'Your local nearest market has no official government quotation reported today. While nearby alternative mandis report verified prices, no verified net-gain or arbitrage advantage can be guaranteed against an unverified baseline. Please verify your local spot auction rate before considering transit.'}
          </div>
        </div>
      ) : priceComparisonStatus === 'insufficient_alternative_quotes' ? (
        <div className="mb-4 p-3.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-900 flex items-start gap-2.5 text-xs shadow-xs">
          <Award className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Insufficient Alternative Quotes (Local Sale Recommended): </span>
            {priceComparisonNotice || 'Your local market has an authenticated government quotation. However, candidate alternative regional markets lack verified quotes today. Selling at your local market is recommended over speculating on distant benchmark estimates.'}
          </div>
        </div>
      ) : priceComparisonStatus === 'no_verified_price_data' ? (
        <div className="mb-4 p-3.5 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 flex items-start gap-2.5 text-xs shadow-xs">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">No Verified Government Price Data: </span>
            {priceComparisonNotice || 'No active official AGMARKNET quotations were recorded today for this crop across nearby APMC mandis. Displayed rates are estimated historical benchmarks for general situational awareness only, and cannot support verified arbitrage recommendations or net-gain claims.'}
          </div>
        </div>
      ) : (
        <div className="mb-4 p-3.5 rounded-xl bg-emerald-50 border border-emerald-200/80 text-emerald-900 flex items-start gap-2.5 text-xs shadow-xs">
          <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Verified Comparison Available: </span>
            {priceComparisonNotice || 'Authentic government AGMARKNET quotations are available for your local baseline market and alternative regional mandis. Net realizable prices reflect road-distance transport and perishability deductions.'}
          </div>
        </div>
      )}

      {/* Horizontal Visual Comparison Bars */}
      <div className="space-y-3.5 mb-6">
        {mandis.map((mandi, idx) => {
          const isTop = idx === 0;
          const modalWidth = `${Math.min(100, (mandi.modal_price / maxPrice) * 100)}%`;
          const netWidth = `${Math.min(100, (mandi.net_price_per_qtl / maxPrice) * 100)}%`;
          const relativeFetched = formatRelativeTime(mandi.fetched_at);

          return (
            <div
              key={mandi.market}
              className={`p-3 rounded-xl border transition ${
                isTop
                  ? 'bg-emerald-50/50 border-emerald-300 ring-2 ring-emerald-200/60 shadow-xs'
                  : 'bg-slate-50 border-slate-200/70'
              }`}
            >
              <div className="flex items-center justify-between text-xs mb-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  {isTop ? (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-600 text-white font-bold text-[10px]">
                      <Award className="w-3 h-3" />
                      #1 Best Net Profit
                    </span>
                  ) : (
                    <span className="text-slate-500 font-medium">#{idx + 1}</span>
                  )}
                  <span className="font-bold text-slate-900">{mandi.market}</span>
                  <span className="text-slate-500">
                    ({mandi.distance_km === 0 ? 'Local' : `${mandi.distance_km.toFixed(0)} km`})
                  </span>

                  {/* Provenance and Freshness Tag */}
                  {mandi.is_benchmark || mandi.data_source === 'estimated_benchmark' ? (
                    <span className="px-1.5 py-0.2 rounded-xs bg-amber-100 text-amber-800 text-[10px] font-semibold border border-amber-300" title="Estimated benchmark; reference only">
                      Estimated Benchmark
                    </span>
                  ) : mandi.freshness_status === 'stale' ? (
                    <span className="px-1.5 py-0.2 rounded-xs bg-amber-100 text-amber-800 text-[10px] font-semibold border border-amber-300" title="Quotation fetched >3 hours ago">
                      Stale Quote
                    </span>
                  ) : mandi.freshness_status === 'fresh' || mandi.data_source === 'live_api' ? (
                    <span className="px-1.5 py-0.2 rounded-xs bg-emerald-100 text-emerald-800 text-[10px] font-semibold border border-emerald-300">
                      Fresh AGMARKNET
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.2 rounded-xs bg-indigo-50 text-indigo-700 text-[10px] font-medium border border-indigo-200">
                      Cached Snapshot
                    </span>
                  )}

                  {/* Arrival Date and Relative Age */}
                  <span className="text-[10px] text-slate-400 flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    Trading: {mandi.arrival_date || 'N/A'}
                    {relativeFetched && (
                      <>
                        <span>•</span>
                        <Clock className="w-3 h-3" />
                        Fetched {relativeFetched}
                      </>
                    )}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-slate-500 line-through text-[11px]">
                    ₹{Math.round(mandi.modal_price).toLocaleString('en-IN')}
                  </span>
                  <span className="font-extrabold text-sm text-slate-900">
                    ₹{Math.round(mandi.net_price_per_qtl).toLocaleString('en-IN')}{' '}
                    <span className="text-[10px] font-normal text-slate-500">/qtl</span>
                  </span>
                </div>
              </div>

              {/* Dual Progress Bars */}
              <div className="space-y-1">
                {/* Modal Bar */}
                <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-slate-400 rounded-full transition-all duration-500"
                    style={{ width: modalWidth }}
                  />
                </div>
                {/* Net Realizable Bar */}
                <div className="h-2.5 w-full bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isTop ? 'bg-emerald-600' : 'bg-emerald-500'
                    }`}
                    style={{ width: netWidth }}
                  />
                </div>
              </div>

              {/* Total Gain vs Local Highlight */}
              <div className="flex items-center justify-between flex-wrap gap-1 text-[11px] mt-2 pt-1 border-t border-slate-200/60">
                <span className="text-slate-500">
                  Deduction: -₹
                  {Math.round(mandi.transport_cost_per_qtl + mandi.spoilage_deduction_per_qtl)}{' '}
                  (Transit ₹{Math.round(mandi.transport_cost_per_qtl)} + Spoilage ₹
                  {Math.round(mandi.spoilage_deduction_per_qtl)})
                </span>
                <span
                  className={`font-semibold ${
                    mandi.net_gain_vs_local_total > 0
                      ? 'text-emerald-700 font-bold'
                      : mandi.net_gain_vs_local_total < 0
                      ? 'text-rose-600'
                      : 'text-slate-600'
                  }`}
                >
                  {mandi.is_benchmark ? (
                    <span className="text-slate-400 italic">Gain unverified (Benchmark)</span>
                  ) : (
                    <>
                      {mandi.net_gain_vs_local_total > 0 ? '+' : ''}₹
                      {Math.round(mandi.net_gain_vs_local_total).toLocaleString('en-IN')}{' '}
                      vs Local
                    </>
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Detailed Data Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
            <tr>
              <th className="py-3 px-3">APMC Market</th>
              <th className="py-3 px-3 text-right">Distance</th>
              <th className="py-3 px-3 text-right">Modal Price</th>
              <th className="py-3 px-3 text-right">Transport</th>
              <th className="py-3 px-3 text-right">Spoilage</th>
              <th className="py-3 px-3 text-right font-bold text-slate-900">Net Realizable</th>
              <th className="py-3 px-3 text-right font-bold text-emerald-700">Net Gain ({quantity} qtl)</th>
              <th className="py-3 px-3 text-center">Arrival Date</th>
              <th className="py-3 px-3 text-center">Data Source & Freshness</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {mandis.map((m, idx) => {
              const relTime = formatRelativeTime(m.fetched_at);
              return (
                <tr
                  key={m.market}
                  className={`hover:bg-slate-50/80 transition ${
                    idx === 0 ? 'bg-emerald-50/30 font-medium' : ''
                  }`}
                >
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-1.5">
                      {idx === 0 && <Check className="w-3.5 h-3.5 text-emerald-600" />}
                      <div>
                        <span className="font-semibold text-slate-900">{m.market}</span>
                        <span className="text-slate-400 block text-[10px]">
                          {m.district}, {m.state}
                        </span>
                        {m.dataset_id ? (
                          <span className="text-[9px] text-slate-400 font-mono block">
                            AGMARKNET #{m.dataset_id.slice(0, 8)}
                          </span>
                        ) : (
                          <span className="text-[9px] text-amber-600 font-mono block">
                            Unverified Benchmark
                          </span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right text-slate-600">
                    {m.distance_km === 0 ? (
                      <span className="px-1.5 py-0.5 rounded-sm bg-slate-200 text-slate-700 text-[10px] font-bold">
                        0 km (Local)
                      </span>
                    ) : (
                      `${m.distance_km.toFixed(1)} km`
                    )}
                  </td>
                  <td className="py-3 px-3 text-right text-slate-700 font-medium">
                    ₹{Math.round(m.modal_price).toLocaleString('en-IN')}
                  </td>
                  <td className="py-3 px-3 text-right text-rose-600">
                    -₹{Math.round(m.transport_cost_per_qtl).toLocaleString('en-IN')}
                  </td>
                  <td className="py-3 px-3 text-right text-rose-600">
                    -₹{Math.round(m.spoilage_deduction_per_qtl).toLocaleString('en-IN')}
                  </td>
                  <td className="py-3 px-3 text-right font-extrabold text-slate-900">
                    ₹{Math.round(m.net_price_per_qtl).toLocaleString('en-IN')}
                  </td>
                  <td className="py-3 px-3 text-right">
                    {m.is_benchmark ? (
                      <span className="text-slate-400 italic text-[11px]">—</span>
                    ) : (
                      <span
                        className={`font-bold ${
                          m.net_gain_vs_local_total > 0
                            ? 'text-emerald-700'
                            : m.net_gain_vs_local_total < 0
                            ? 'text-rose-600'
                            : 'text-slate-500'
                        }`}
                      >
                        {m.net_gain_vs_local_total > 0 ? '+' : ''}₹
                        {Math.round(m.net_gain_vs_local_total).toLocaleString('en-IN')}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-center text-slate-600">
                    <span className="inline-flex items-center gap-1 text-[11px]">
                      <Calendar className="w-3 h-3 text-slate-400" />
                      {m.arrival_date || 'N/A'}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-center">
                    {m.is_benchmark || m.data_source === 'estimated_benchmark' ? (
                      <div>
                        <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-300" title="Estimated benchmark; reference only">
                          Estimated Benchmark
                        </span>
                        <span className="text-[9px] text-slate-400 block mt-0.5">Reference Only</span>
                      </div>
                    ) : m.freshness_status === 'stale' ? (
                      <div>
                        <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-300" title="Quotation fetched >3 hours ago">
                          Stale Quotation
                        </span>
                        {relTime && <span className="text-[9px] text-amber-700 block mt-0.5">Fetched {relTime}</span>}
                      </div>
                    ) : m.data_source === 'live_api' || m.freshness_status === 'fresh' ? (
                      <div>
                        <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Verified Live (AGMARKNET)
                        </span>
                        <span className="text-[9px] text-emerald-700 block mt-0.5">{relTime ? `Fetched ${relTime}` : 'Fresh'}</span>
                      </div>
                    ) : (
                      <div>
                        <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200" title="Historical verified AGMARKNET quotation">
                          Verified Cached Snapshot
                        </span>
                        {relTime && <span className="text-[9px] text-indigo-700 block mt-0.5">Fetched {relTime}</span>}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Variety Comparability Footnote */}
      <p className="text-[11px] text-slate-400 mt-3 italic">
        * Note on Produce Varieties: AGMARKNET quotes report modal prices for the commodity standard trading grade (FAQ - Fair Average Quality) and do not distinguish between specialty sub-varieties or local cultivars.
      </p>
    </div>
  );
};
