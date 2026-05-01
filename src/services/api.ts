import type {
  CategoryAnalysisResult,
  CategorySearchResult,
  SearchResponseV2,
  SearchResponseV3,
  SearchResult,
} from '../types';

// localhost이면 개발서버(3001), 그 외엔 Cloudflare Workers 직접 호출
function getApiBase() {
  if (typeof window === 'undefined') return '';

  const envBase = import.meta.env.VITE_API_BASE_URL?.trim();
  if (window.location.hostname === 'localhost') {
    return envBase || 'http://localhost:3001';
  }

  return envBase && envBase !== '__PRODUCTION__' ? envBase : '';
}

const API_BASE = getApiBase();

// ─── 분석 결과 캐시 (세션 내 동일 이미지/URL 재호출 방지) ──────────────────────
const analysisCache = new Map<string, CategoryAnalysisResult | SearchResponseV2 | SearchResponseV3>();

function imageCacheKey(base64: string): string {
  return `${base64.length}|${base64.slice(0, 64)}|${base64.slice(-64)}`;
}

export async function analyzeImage(
  imageBase64: string,
  mimeType: string,
): Promise<CategoryAnalysisResult | SearchResponseV2 | SearchResponseV3> {
  const cacheKey = `img:${imageCacheKey(imageBase64)}`;
  if (analysisCache.has(cacheKey)) {
    return analysisCache.get(cacheKey)!;
  }

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageBase64, mimeType }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.message || `분석 실패 (${res.status})`), { code: err.code });
  }

  const data: CategoryAnalysisResult | SearchResponseV2 | SearchResponseV3 = await res.json();
  analysisCache.set(cacheKey, data);
  return data;
}

export async function searchByImageFile(
  imageBase64: string,
  mimeType: string,
  sortBy: 'relevance' | 'price_asc' | 'price_desc' = 'relevance',
): Promise<SearchResponseV3> {
  const url = `${API_BASE}/api/search-image?sort_by=${sortBy}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imageBase64, mimeType }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.message || `검색 실패 (${res.status})`), { code: err.code });
  }

  const data = await res.json();
  // Worker adds _imageHash from the response or computes it
  return { ...data, _source: 'v3' as const, _imageHash: data.image_hash || data._imageHash || '' };
}

export async function recordClick(
  imageHash: string,
  productId: string,
  category?: string,
): Promise<void> {
  try {
    const qs = category ? `?category=${encodeURIComponent(category)}` : '';
    await fetch(`${API_BASE}/api/analyze/click/${imageHash}/${productId}${qs}`, { method: 'POST' });
  } catch {
    // non-critical
  }
}

export async function recordClickV3(
  imageHash: string,
  productId: string,
  category: string,
  rankPosition: number,
  matchScore: number,
  productTitle?: string,
  productPrice?: number,
  sessionId?: string,
): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_hash: imageHash,
        product_id: productId,
        category,
        rank_position: rankPosition,
        final_score: matchScore,
        product_title: productTitle || '',
        product_price: productPrice || 0,
        session_id: sessionId || '',
      }),
    });
  } catch {
    // non-critical
  }
}

// 카테고리별 병렬 검색
export async function searchByCategories(
  categories: CategoryAnalysisResult['categories'],
): Promise<CategorySearchResult[]> {
  const res = await fetch(`${API_BASE}/api/search/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ categories }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `카테고리 검색 실패 (${res.status})`);
  }

  const data: { results: CategorySearchResult[] } = await res.json();
  return data.results;
}

// 단일 검색 (더 보기용)
export async function searchProducts(query: string, keywords: string[], start = 1): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, keywords, start }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `검색 실패 (${res.status})`);
  }

  return res.json();
}
