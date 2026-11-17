import type { FreshnessStatus } from '../types';

/**
 * Safely format an ISO timestamp into a human-readable relative time string.
 * Returns empty string for null, undefined, or unparseable timestamps.
 */
export function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return '';
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return '';

  const now = Date.now();
  const diffSeconds = Math.max(0, Math.floor((now - date.getTime()) / 1000));

  if (diffSeconds < 60) {
    return 'Just now';
  }
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

/**
 * Format relative time from raw age in seconds.
 */
export function formatAgeSeconds(seconds: number | null | undefined): string {
  if (seconds == null || isNaN(seconds) || seconds < 0) return '';
  if (seconds < 60) return 'Just now';
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export interface FreshnessBadgeConfig {
  label: string;
  badgeClass: string;
  dotClass: string;
  isLive: boolean;
}

/**
 * Returns UI badge styling and label for mandi or weather freshness status.
 */
export function getFreshnessBadgeConfig(
  status: FreshnessStatus | undefined,
  kind: 'mandi' | 'weather',
  relativeTime?: string
): FreshnessBadgeConfig {
  const timeSuffix = relativeTime ? ` (${relativeTime})` : '';

  if (kind === 'mandi') {
    switch (status) {
      case 'fresh':
        return {
          label: `Mandi: Fresh${timeSuffix}`,
          badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
          dotClass: 'bg-emerald-500 animate-pulse',
          isLive: true,
        };
      case 'cached':
        return {
          label: `Mandi: Cached${timeSuffix}`,
          badgeClass: 'bg-indigo-50 text-indigo-800 border-indigo-200',
          dotClass: 'bg-indigo-500',
          isLive: false,
        };
      case 'stale':
        return {
          label: `Mandi: Stale (>3h)${timeSuffix}`,
          badgeClass: 'bg-amber-50 text-amber-800 border-amber-300',
          dotClass: 'bg-amber-500',
          isLive: false,
        };
      case 'estimated':
        return {
          label: 'Mandi: Estimated Benchmarks',
          badgeClass: 'bg-amber-50 text-amber-900 border-amber-300',
          dotClass: 'bg-amber-400',
          isLive: false,
        };
      case 'unavailable':
      default:
        return {
          label: 'Mandi: Unavailable',
          badgeClass: 'bg-slate-100 text-slate-700 border-slate-300',
          dotClass: 'bg-slate-400',
          isLive: false,
        };
    }
  } else {
    // Weather
    switch (status) {
      case 'fresh':
        return {
          label: `Weather: Fresh${timeSuffix}`,
          badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
          dotClass: 'bg-emerald-500 animate-pulse',
          isLive: true,
        };
      case 'cached':
        return {
          label: `Weather: Cached${timeSuffix}`,
          badgeClass: 'bg-indigo-50 text-indigo-800 border-indigo-200',
          dotClass: 'bg-indigo-500',
          isLive: false,
        };
      case 'stale':
        return {
          label: `Weather: Stale (>3h)${timeSuffix}`,
          badgeClass: 'bg-amber-50 text-amber-800 border-amber-300',
          dotClass: 'bg-amber-500',
          isLive: false,
        };
      case 'estimated':
        return {
          label: 'Weather: Synthetic Baseline',
          badgeClass: 'bg-slate-100 text-slate-700 border-slate-300',
          dotClass: 'bg-slate-400',
          isLive: false,
        };
      case 'unavailable':
      default:
        return {
          label: 'Weather: Unavailable',
          badgeClass: 'bg-slate-100 text-slate-700 border-slate-300',
          dotClass: 'bg-slate-400',
          isLive: false,
        };
    }
  }
}
