import type { AnalysisResponse, PresetsResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export async function fetchPresets(): Promise<PresetsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/presets`);
  if (!res.ok) {
    throw new Error(`Failed to load demo presets (HTTP ${res.status})`);
  }
  return res.json();
}

export async function analyzeHarvestAndSale(params: {
  location_query: string;
  latitude?: number | null;
  longitude?: number | null;
  crop_id: string;
  quantity_quintals: number;
  language: string;
  force_refresh?: boolean;
}): Promise<AnalysisResponse> {
  const res = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Analysis request failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function sendChatMessage(
  analysis_context: Record<string, any>,
  question: string,
  language: string
): Promise<{ answer: string; language: string }> {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ analysis_context, question, language }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Chat query failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchTTSAudio(text: string, language: string): Promise<Blob> {
  const res = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  });
  if (!res.ok) {
    throw new Error(`TTS audio generation failed (HTTP ${res.status})`);
  }
  return res.blob();
}
