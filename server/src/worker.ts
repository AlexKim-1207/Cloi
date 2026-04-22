/**
 * 웨어고(Cloi) — Cloudflare Workers 진입점
 * Hono 프레임워크 | 환경변수: Workers Secrets(c.env)
 */
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from '@google/generative-ai';

// ─── 환경변수 타입 ────────────────────────────────────────────────────────────
export interface Env {
  GEMINI_API_KEY: string;
  NAVER_CLIENT_ID: string;
  NAVER_CLIENT_SECRET: string;
}

// ─── 에러 직렬화 (Workers에서 Error 객체는 JSON.stringify가 {} 반환) ──────────
function serializeError(err: unknown): { message: string; name: string; code?: string; stack?: string } {
  if (err instanceof Error) {
    return {
      name: err.name,
      message: err.message,
      code: (err as Error & { code?: string }).code,
      stack: err.stack,
    };
  }
  return { name: 'UnknownError', message: String(err) };
}

// ─── 공통 유틸 ────────────────────────────────────────────────────────────────
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '');
}

// ─── Gemini 패션 분석 ─────────────────────────────────────────────────────────
const FASHION_PROMPT = `당신은 한국 패션 이커머스 전문 MD입니다. 이미지 속 착용된 패션 아이템을 카테고리별로 정밀 분석하세요.

다음 JSON 형식으로만 응답하세요 (예시):
{
  "categories": {
    "top": {
      "color": "아이보리",
      "fit": "오버핏",
      "material": "코튼",
      "design": "라운드넥, 민무늬",
      "style": "캐주얼",
      "keywords": ["아이보리", "오버핏", "코튼", "라운드넥", "캐주얼", "맨투맨"],
      "searchQueries": [
        "아이보리 오버핏 맨투맨",
        "코튼 라운드넥 스웨트셔츠",
        "캐주얼 루즈핏 맨투맨 티셔츠"
      ]
    },
    "bottom": null,
    "shoes": null,
    "outer": null,
    "bag": null,
    "accessory": null
  },
  "description": "아이보리 오버핏 맨투맨의 캐주얼 코디"
}

카테고리: top(상의) bottom(하의) shoes(신발) outer(아우터) bag(가방) accessory(액세서리)
규칙:
- 확인되지 않는 카테고리는 반드시 null (6개 키 모두 포함)
- color/fit/material/design/style 각각 구체적으로
- keywords 4~7개, searchQueries 반드시 3개 (각각 다른 조합)
- searchQueries: 한국어, 쇼핑몰 검색에 자연스러운 2~4단어
- 패션 아이템이 없거나 품질이 낮으면 {"error": "IMAGE_QUALITY"}`;

type FashionCategoryKey = 'top' | 'bottom' | 'shoes' | 'outer' | 'bag' | 'accessory';
interface CategoryInfo { keywords: string[]; searchQueries: string[] }
interface AnalysisResult {
  categories: Partial<Record<FashionCategoryKey, CategoryInfo | null>>;
  description: string;
}

async function analyzeImage(apiKey: string, imageBase64: string, mimeType: string): Promise<AnalysisResult> {
  console.log('[analyzeImage] start, mimeType:', mimeType, 'base64 length:', imageBase64.length);

  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel(
    {
      model: 'gemini-2.5-flash',
      generationConfig: { temperature: 0.2 },
      safetySettings: [
        { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
        { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
      ],
    },
    { apiVersion: 'v1beta' },
  );

  const MAX_RETRIES = 3;
  await sleep(1000);

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      console.log(`[analyzeImage] attempt ${attempt}/${MAX_RETRIES}`);
      const result = await model.generateContent([
        { inlineData: { data: imageBase64, mimeType: mimeType as 'image/jpeg' | 'image/png' | 'image/webp' } },
        FASHION_PROMPT,
      ]);

      const text = result.response.text().trim();
      console.log('[analyzeImage] raw response length:', text.length);
      const usage = result.response.usageMetadata;
      if (usage) {
        console.log('[gemini] tokens — input:', usage.promptTokenCount, '/ output:', usage.candidatesTokenCount, '/ total:', usage.totalTokenCount);
      }

      const jsonText = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(jsonText);
      } catch (parseErr) {
        console.error('[analyzeImage] JSON parse failed. raw text:', text.slice(0, 500));
        throw new Error(`Gemini 응답 파싱 실패: ${String(parseErr)}`);
      }

      if (parsed.error === 'IMAGE_QUALITY') {
        throw Object.assign(new Error('이미지에서 옷을 명확하게 인식하기 어려워요.'), { code: 'IMAGE_QUALITY' });
      }
      if (!parsed.categories || typeof parsed.categories !== 'object') {
        console.error('[analyzeImage] unexpected structure:', JSON.stringify(parsed).slice(0, 300));
        throw new Error('Gemini가 예상치 못한 형식으로 응답했어요.');
      }

      // searchQueries 정규화
      const normalized: Partial<Record<FashionCategoryKey, CategoryInfo | null>> = {};
      for (const [key, val] of Object.entries(parsed.categories as Record<string, unknown>)) {
        if (!val || typeof val !== 'object') { normalized[key as FashionCategoryKey] = null; continue; }
        const info = val as Record<string, unknown>;
        const queries = Array.isArray(info.searchQueries) && info.searchQueries.length > 0
          ? (info.searchQueries as string[]).slice(0, 3)
          : typeof info.searchQuery === 'string' ? [info.searchQuery]
          : Array.isArray(info.keywords) ? [(info.keywords as string[]).slice(0, 3).join(' ')] : [];
        if (queries.length === 0) continue;
        normalized[key as FashionCategoryKey] = {
          keywords: Array.isArray(info.keywords) ? info.keywords as string[] : [],
          searchQueries: queries,
        };
      }

      if (Object.values(normalized).every((v) => v === null)) {
        throw Object.assign(new Error('이미지에서 옷을 인식하기 어려워요.'), { code: 'IMAGE_QUALITY' });
      }

      console.log('[analyzeImage] success, categories:', Object.keys(normalized).filter((k) => normalized[k as FashionCategoryKey] !== null));
      return { categories: normalized, description: (parsed.description as string) || '' };

    } catch (err: unknown) {
      const error = err as Error & { status?: number; code?: string };
      if (error.code === 'IMAGE_QUALITY') throw err;

      const errMsg = error.message ?? '';
      const is429 = error.status === 429 || errMsg.toLowerCase().includes('resource_exhausted') || errMsg.includes('429');
      const is503 = error.status === 503 || errMsg.includes('503') || errMsg.toLowerCase().includes('service unavailable') || errMsg.toLowerCase().includes('high demand');

      console.error(`[analyzeImage] attempt ${attempt} failed:`, serializeError(err));

      if (is429 && attempt < MAX_RETRIES) {
        console.warn(`[analyzeImage] rate limited, waiting 3s before retry...`);
        await sleep(3000);
        continue;
      }
      if (is429) throw Object.assign(new Error('AI 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.'), { code: 'QUOTA_EXCEEDED' });

      if (is503 && attempt < MAX_RETRIES) {
        console.warn(`[analyzeImage] service unavailable (503), waiting ${attempt * 2}s before retry...`);
        await sleep(attempt * 2000);
        continue;
      }
      if (is503) throw Object.assign(new Error('AI 서버가 일시적으로 과부하 상태예요. 잠시 후 다시 시도해 주세요.'), { code: 'SERVICE_UNAVAILABLE' });

      throw err;
    }
  }
  throw Object.assign(new Error('AI 분석 재시도 횟수를 초과했어요.'), { code: 'QUOTA_EXCEEDED' });
}

// ─── 네이버 쇼핑 검색 ─────────────────────────────────────────────────────────
interface NaverProduct {
  id: string; title: string; price: number; image: string;
  link: string; mallName: string; brand: string; category: string;
}

async function searchNaver(
  clientId: string,
  clientSecret: string,
  query: string,
  display = 20,
  start = 1,
): Promise<{ products: NaverProduct[]; total: number; query: string }> {
  console.log('[searchNaver] query:', query);
  const params = new URLSearchParams({ query, display: String(display), start: String(start), sort: 'sim' });

  let res: Response;
  try {
    res = await fetch(`https://openapi.naver.com/v1/search/shop.json?${params}`, {
      headers: { 'X-Naver-Client-Id': clientId, 'X-Naver-Client-Secret': clientSecret },
      signal: AbortSignal.timeout(5000),
    });
  } catch (fetchErr) {
    console.error('[searchNaver] fetch failed:', serializeError(fetchErr));
    throw new Error(`네이버 API 연결 실패: ${String(fetchErr)}`);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    console.error(`[searchNaver] HTTP ${res.status}:`, body.slice(0, 200));
    if (res.status === 401) throw new Error('네이버 쇼핑 API 인증 실패 (401) — Client ID/Secret을 확인해 주세요.');
    throw new Error(`네이버 쇼핑 API 오류 (${res.status}): ${body.slice(0, 100)}`);
  }

  let data: { total: number; items: Array<{ productId: string; title: string; lprice: string; image: string; link: string; mallName: string; brand: string; category1: string }> };
  try {
    data = await res.json() as typeof data;
  } catch (jsonErr) {
    console.error('[searchNaver] JSON parse error:', jsonErr);
    throw new Error('네이버 API 응답 파싱 실패');
  }

  const products = (data.items || []).map((item) => ({
    id: item.productId || String(Math.random()),
    title: stripHtml(item.title),
    price: parseInt(item.lprice, 10) || 0,
    image: item.image,
    link: item.link,
    mallName: item.mallName || '',
    brand: item.brand || '',
    category: item.category1 || '',
  }));

  console.log(`[searchNaver] "${query}" → ${products.length}개 상품 (total: ${data.total})`);
  return { products, total: data.total || 0, query };
}

// ─── Hono 앱 ──────────────────────────────────────────────────────────────────
const app = new Hono<{ Bindings: Env }>();

const ALLOWED_ORIGINS = [
  'https://cloi.pages.dev',
  'http://localhost:5173',
  'http://localhost:3000',
];

app.use('*', cors({
  origin: (origin) => ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
  allowMethods: ['GET', 'POST', 'OPTIONS'],
  allowHeaders: ['Content-Type'],
}));

// 전역 에러 핸들러
app.onError((err, c) => {
  const serialized = serializeError(err);
  console.error('[global error handler]', serialized);
  return c.json({ message: serialized.message, name: serialized.name, code: serialized.code, stack: serialized.stack }, 500);
});

// ─── 헬스체크 ─────────────────────────────────────────────────────────────────
app.get('/api/health', (c) => c.json({
  status: 'ok',
  apis: {
    gemini: {
      present: !!c.env.GEMINI_API_KEY,
      keyLength: c.env.GEMINI_API_KEY?.length ?? 0,
    },
    naver: {
      present: !!c.env.NAVER_CLIENT_ID,
    },
  },
}));

// ─── POST /api/analyze — 이미지 base64 분석 ──────────────────────────────────
app.post('/api/analyze', async (c) => {
  console.log('[POST /api/analyze] request received');
  try {
    let body: { imageBase64: string; mimeType: string };
    try {
      body = await c.req.json();
    } catch (jsonErr) {
      console.error('[/api/analyze] body parse error:', jsonErr);
      return c.json({ message: '요청 본문 파싱 실패 — JSON 형식인지 확인해 주세요.', detail: String(jsonErr) }, 400);
    }

    const { imageBase64, mimeType } = body;
    if (!imageBase64) return c.json({ message: '이미지 데이터가 필요해요.' }, 400);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(mimeType))
      return c.json({ message: `지원하지 않는 이미지 형식: ${mimeType}` }, 400);
    if (imageBase64.length > 14 * 1024 * 1024)
      return c.json({ message: '이미지가 너무 커요. 10MB 이하로 업로드해 주세요.' }, 400);

    if (!c.env.GEMINI_API_KEY) {
      console.error('[/api/analyze] GEMINI_API_KEY is missing');
      return c.json({ message: 'GEMINI_API_KEY 환경변수가 설정되지 않았어요.' }, 500);
    }

    const result = await analyzeImage(c.env.GEMINI_API_KEY, imageBase64, mimeType);
    return c.json(result);

  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    const serialized = serializeError(err);
    console.error('[/api/analyze] error:', serialized);

    if (error.code === 'QUOTA_EXCEEDED') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 429);
    if (error.code === 'IMAGE_QUALITY') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 422);
    if (error.code === 'SERVICE_UNAVAILABLE') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 503);
    return c.json({ message: serialized.message, name: serialized.name, code: serialized.code, stack: serialized.stack }, 500);
  }
});

// ─── POST /api/search — 단일 쿼리 검색 ──────────────────────────────────────
app.post('/api/search', async (c) => {
  console.log('[POST /api/search] request received');
  try {
    const { query, keywords, start } = await c.req.json<{ query?: string; keywords?: string[]; start?: number }>();
    if (!query && (!keywords || keywords.length === 0))
      return c.json({ message: '검색 키워드가 필요해요.' }, 400);

    if (!c.env.NAVER_CLIENT_ID || !c.env.NAVER_CLIENT_SECRET) {
      console.error('[/api/search] Naver credentials missing');
      return c.json({ message: 'Naver API 환경변수가 설정되지 않았어요.' }, 500);
    }

    const startIndex = typeof start === 'number' && start > 0 ? start : 1;
    const searchQuery = query || (keywords ?? []).slice(0, 3).join(' ');
    const result = await searchNaver(c.env.NAVER_CLIENT_ID, c.env.NAVER_CLIENT_SECRET, searchQuery, 20, startIndex);
    return c.json(result);

  } catch (err: unknown) {
    const serialized = serializeError(err);
    console.error('[/api/search] error:', serialized);
    return c.json({ message: serialized.message || '상품 검색 중 오류가 발생했어요.', detail: serialized.stack }, 500);
  }
});

// ─── POST /api/search/categories — 카테고리별 다중 쿼리 병렬 검색 ────────────
app.post('/api/search/categories', async (c) => {
  console.log('[POST /api/search/categories] request received');
  try {
    let categories: Record<string, { keywords: string[]; searchQueries?: string[]; searchQuery?: string } | null>;
    try {
      ({ categories } = await c.req.json());
    } catch (jsonErr) {
      return c.json({ message: '요청 본문 파싱 실패', detail: String(jsonErr) }, 400);
    }

    if (!categories) return c.json({ message: '카테고리 데이터가 필요해요.' }, 400);

    const entries = Object.entries(categories).filter(([, v]) => v !== null && typeof v === 'object') as [string, NonNullable<(typeof categories)[string]>][];
    if (entries.length === 0) return c.json({ message: '검색할 카테고리가 없어요.' }, 400);

    console.log('[/api/search/categories] searching categories:', entries.map(([k]) => k));

    const results = await Promise.all(
      entries.map(async ([category, info]) => {
        const queries = Array.isArray(info.searchQueries) && info.searchQueries.length > 0
          ? info.searchQueries.slice(0, 3)
          : info.searchQuery ? [info.searchQuery]
          : [info.keywords.slice(0, 3).join(' ')];

        try {
          const searchResults = await Promise.all(
            queries.map((q) =>
              searchNaver(c.env.NAVER_CLIENT_ID, c.env.NAVER_CLIENT_SECRET, q, 20, 1)
                .catch((e) => { console.error(`[/categories] query "${q}" failed:`, serializeError(e)); return null; }),
            ),
          );
          const seenIds = new Set<string>();
          const merged = searchResults
            .filter((r): r is NonNullable<typeof r> => r !== null)
            .flatMap((r) => r.products)
            .filter((p) => { if (seenIds.has(p.id)) return false; seenIds.add(p.id); return true; })
            .slice(0, 40);
          const totalMax = Math.max(...searchResults.filter(Boolean).map((r) => r!.total), 0);
          console.log(`[/categories] ${category}: ${merged.length}개 병합`);
          return { category, keywords: info.keywords, products: merged, total: totalMax, query: queries[0] };
        } catch (catErr) {
          console.error(`[/categories] ${category} 전체 실패:`, serializeError(catErr));
          return { category, keywords: info.keywords, products: [], total: 0, query: queries[0] };
        }
      }),
    );

    const filtered = results.filter((r) => r.products.length > 0);
    console.log(`[/categories] 응답 카테고리 수: ${filtered.length}`);
    return c.json({ results: filtered });

  } catch (err: unknown) {
    const serialized = serializeError(err);
    console.error('[/api/search/categories] error:', serialized);
    return c.json({ message: serialized.message || '카테고리별 검색 중 오류가 발생했어요.', detail: serialized.stack }, 500);
  }
});

// 404
app.notFound((c) => c.json({ message: '요청한 API를 찾을 수 없어요.' }, 404));

export default app;
