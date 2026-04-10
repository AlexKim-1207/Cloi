import type { AnalysisKeywords, SearchResult } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

// Vite 프록시를 통해 /api로 요청 → 백엔드에서 처리 (API 키는 서버에만 존재)

export async function analyzeImage(imageBase64: string, mimeType: string): Promise<AnalysisKeywords> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageBase64, mimeType }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `분석 실패 (${res.status})`);
  }

  return res.json();
}

export async function analyzeImageUrl(imageUrl: string): Promise<AnalysisKeywords> {
  const res = await fetch(`${API_BASE}/api/analyze-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageUrl }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `분석 실패 (${res.status})`);
  }

  return res.json();
}

export async function searchProducts(query: string, keywords: string[]): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, keywords }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `검색 실패 (${res.status})`);
  }

  return res.json();
}
