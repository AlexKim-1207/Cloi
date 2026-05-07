/**
 * 웨어고(Cloi) — Cloudflare Workers 진입점
 * Hono 프레임워크 | 환경변수: Workers Secrets(c.env)
 */
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from '@google/generative-ai';

// ─── 환경변수 타입 ────────────────────────────────────────────────────────────
// SESSION 16: Gemini-only로 전환. FASHION_SEARCH_URL (Cloud Run) 제거.
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
const FASHION_PROMPT = `당신은 한국 패션 이커머스 전문 MD입니다. 이미지를 부위별로 점검하고 모든 의류/액세서리/가방을 빠짐없이 추출하세요.

## 1단계: 부위별 점검 (보이는 모든 것 나열)
- 머리: 모자/헤어밴드
- 얼굴/눈: 선글라스/안경
- 목: 목걸이/스카프
- 손목: 시계/팔찌
- 손: 반지/장갑
- 상체: 외부(셔츠/카디건/재킷) + 내부(티셔츠/이너) — 레이어드 시 분리
- 허리: 벨트
- 하체: 바지/스커트/원피스
- 발: 신발
- 손에/어깨에: 가방/숄더백/토트백/쇼핑백/클러치 (있으면 반드시 bag)

## 2단계: 카테고리별 분류 — 다음 8개 키 모두 포함 (없으면 null)
top_outer  : 외부 상의 (셔츠/카디건/재킷)
top_inner  : 안쪽 상의 (티셔츠/이너/탱크탑/터틀넥)
outer      : 두꺼운 겉옷 (코트/패딩/점퍼)
bottom     : 하의 (바지/스커트/반바지)
dress      : 원피스/점프수트
shoes      : 신발
bag        : 가방/숄더백/토트백/쇼핑백 (들고 있어도 포함)
accessory  : 액세서리 (선글라스/모자/벨트/시계/목걸이/귀걸이/반지)

## 3단계: 각 카테고리 항목 형식
{
  "color": "구체적 색상명 (예: 라이트 베이지, 다크 그레이)",
  "fit": "오버핏/슬림핏/레귤러/와이드 등",
  "material": "코튼/울/캐시미어/가죽 등",
  "design": "디테일 (예: 와이드카라, H라인, 사각프레임)",
  "subtype": "세부 분류 (top_inner=터틀넥/크롭탑, bag=숄더백/토트백, accessory=선글라스/벨트)",
  "pattern": "의류 표면 무늬 — 단색 | 체크 | 스트라이프 | 플로럴 | 도트 | 카무 | 페이즐리 | 그래픽 | 기타 (색상 아님, 무늬만)",
  "length": "정확 길이 — 상의:크롭/숏/롱 | 하의:미니/숏/버뮤다/5부/7부/칠부/롱/풀렝스 | 원피스:미니/미디/맥시 | 아우터:크롭/하프/롱 (해당 없으면 null)",
  "alternative_subtypes": ["소매/길이 모호할 때만 대체 후보 — 예: ['반팔', '민소매'] 또는 ['미니', '버뮤다']. 명확하면 빈 배열 []"],
  "keywords": ["색상 토큰", "subtype", "fit", "material", "design"],
  "searchQueries": [
    "{color} {subtype}",
    "{color} {fit} {subtype}",
    "{material} {subtype}"
  ]
}

규칙:
- pattern: 무늬가 체크면 반드시 searchQueries 첫 번째에 "체크" 토큰 포함. 단색이면 패턴 토큰 미포함.
- length: 하의/원피스 특히 중요. 쇼츠=숏, 반바지=숏, 칠부=칠부, 7부=7부, 무릎아래롱=롱.
- alternative_subtypes: 소매(반팔 vs 민소매), 바지 길이(쇼츠 vs 버뮤다) 불분명 시 두 후보 명시. 명확하면 [].

## 4단계: outfit 전체 추론 (사용자 의도 매칭용)
다음 메타 정보를 응답 root에 함께 출력하세요:
- gender: 'female' | 'male' | 'unisex' | 'unknown' (눈에 띄는 단서로만 판단)
- gender_confidence: 0.0~1.0
- gender_signals: ["하이힐", "메이크업", "여성 특유 핏"] 등 판단 근거 2~5개
- price_tier: 'budget' | 'mid' | 'premium' | 'luxury'
  budget = 5만원 미만 평균 / mid = 5~30만원 / premium = 30~100만원 / luxury = 100만원+
- price_tier_confidence: 0.0~1.0
- price_signals: ["로고 명확", "모델컷", "럭셔리 패브릭"] 등 판단 근거 2~5개
- price_range_estimate: { "min": 30000, "max": 200000 } (1 아이템 평균 추정, 원 단위)
- season: 'spring' | 'summer' | 'fall' | 'winter' | 'all'
- vibe: ["시크", "캐주얼", "페미닌", "스트리트", "오피스", "스포티"] 중 1~3개

## 출력 규칙
- 8개 키 모두 응답에 포함 (없는 항목은 반드시 null)
- searchQueries 첫 번째는 반드시 색상 + subtype 조합 (예: "베이지 터틀넥")
- 작은 액세서리도 보이면 포함
- 가방을 손에 들고 있으면 무시하지 말 것
- 패션 아이템 0개거나 품질 낮으면 {"error": "IMAGE_QUALITY"}
- 사진이 cropped (얼굴+상의 일부만)이라도 — 보이는 것만 분석하고, 안 보이는 카테고리는 null 처리. 추측해서 거짓 응답 만들지 말 것.

## 5단계: few-shot 정답 패턴 (참고용 — 실제 이미지에 맞게 응답)

[예시 A] 단일 베이지 터틀넥 클로즈업:
- top_inner: {"color":"라이트 베이지","subtype":"터틀넥","fit":"슬림핏","material":"캐시미어","pattern":"단색","length":"롱","searchQueries":["라이트 베이지 터틀넥","베이지 슬림 캐시미어 터틀넥","베이지 캐시미어 니트"]}
- 다른 카테고리 모두 null
- gender=female, gender_confidence=0.7, price_tier=mid

[예시 B] 풀바디 룩북 (체크 셔츠 + 미니 쇼츠):
- top_outer: {"color":"네이비/화이트","subtype":"오버사이즈 셔츠","pattern":"체크","length":"롱","searchQueries":["네이비 체크 오버 셔츠","체크 빅 셔츠 여성","네이비 화이트 깅엄 셔츠"]}
- bottom: {"color":"베이지","subtype":"미니 쇼츠","pattern":"단색","length":"미니","searchQueries":["베이지 미니 쇼츠","베이지 데님 쇼츠","베이지 핫팬츠"]}
- 다른 카테고리 null
- gender=female, gender_confidence=0.95, price_tier=budget

[예시 C] cropped 셀카 (얼굴+이너만 보임, 외투/하의 안 보임):
- top_inner: {"color":"화이트","subtype":"라운드티","fit":"베이직","pattern":"단색","length":"숏","searchQueries":["화이트 라운드티","흰 반팔티","흰 베이직티"]}
- top_outer / outer / bottom / dress / shoes: null (안 보이는 항목 추측 금지)
- accessory: 보이면 — 안경/목걸이 등
- gender=female, gender_confidence=0.6, price_tier=budget

[예시 D] 단일 토트백 close-up:
- bag: {"color":"블랙","subtype":"토트백","fit":"라지","material":"가죽","pattern":"단색","searchQueries":["블랙 가죽 토트백","블랙 라지 토트백 여성","블랙 비즈니스 토트백"]}
- 다른 카테고리 모두 null
- gender=unisex, price_tier=premium (가죽 + 미니멀 디자인)

[예시 E] 럭셔리 모델 화보 (로고 명확):
- price_tier=luxury, price_tier_confidence=0.85, price_signals=["로고 명확","모델컷","고급 패브릭"]
- price_range_estimate: {"min":300000,"max":2000000}

★ 출력 강제: 반드시 JSON 객체 하나로만 응답한다. 마크다운 헤더(##), 설명 문장, 코드 블록 모두 금지. 응답 첫 글자는 '{', 마지막 글자는 '}'.

JSON 예시:
{
  "categories": {
    "top_outer": null,
    "top_inner": {"color": "라이트 베이지", "fit": "슬림핏", "material": "캐시미어 니트", "design": "기본 터틀넥", "subtype": "터틀넥", "pattern": "단색", "length": "롱", "alternative_subtypes": [], "keywords": ["라이트 베이지", "터틀넥", "슬림핏", "캐시미어 니트"], "searchQueries": ["라이트 베이지 터틀넥", "베이지 슬림핏 터틀넥", "캐시미어 터틀넥 니트"]},
    "outer": {"color": "버건디", "fit": "레귤러", "material": "울", "design": "와이드카라 지퍼 롱코트", "subtype": "롱코트", "pattern": "단색", "length": "롱", "alternative_subtypes": [], "keywords": ["버건디", "롱코트", "와이드카라", "울"], "searchQueries": ["버건디 롱코트", "버건디 와이드카라 코트", "울 롱코트 여성"]},
    "bottom": {"color": "다크 그레이", "fit": "H라인", "material": "울", "design": "미디 길이 H라인", "subtype": "미디스커트", "pattern": "단색", "length": "미디", "alternative_subtypes": [], "keywords": ["다크 그레이", "미디스커트", "H라인"], "searchQueries": ["다크 그레이 미디스커트", "그레이 H라인 스커트", "울 미디스커트 여성"]},
    "dress": null, "shoes": null,
    "bag": {"color": "다양", "fit": "다양", "material": "다양", "design": "쇼핑백 들고 있음", "subtype": "쇼핑백/핸드백", "keywords": ["여성 가방", "토트백"], "searchQueries": ["여성 토트백", "캐주얼 핸드백", "여성 데일리 가방"]},
    "accessory": {"color": "블랙", "fit": "오버사이즈", "material": "플라스틱", "design": "사각 프레임", "subtype": "선글라스", "keywords": ["블랙 선글라스", "사각", "오버사이즈"], "searchQueries": ["블랙 사각 선글라스", "오버사이즈 선글라스", "여성 선글라스"]}
  },
  "description": "버건디 코트 + 베이지 터틀넥 + 그레이 H라인 스커트의 시크한 가을 룩",
  "gender": "female",
  "gender_confidence": 0.9,
  "gender_signals": ["여성 핏 크롭탑", "하이힐", "여성형 액세서리"],
  "price_tier": "mid",
  "price_tier_confidence": 0.7,
  "price_signals": ["인디 K-fashion 스타일", "단순 프린트 없음", "신발 캐주얼"],
  "price_range_estimate": { "min": 30000, "max": 200000 },
  "season": "fall",
  "vibe": ["시크", "오피스"]
}`;

type FashionCategoryKey =
  | 'top_outer' | 'top_inner' | 'outer' | 'bottom' | 'dress'
  | 'shoes' | 'bag' | 'accessory';
interface CategoryInfo {
  keywords: string[];
  searchQueries: string[];
  color?: string;
  fit?: string;
  material?: string;
  design?: string;
  subtype?: string;
  pattern?: '단색' | '체크' | '스트라이프' | '플로럴' | '도트' | '카무' | '페이즐리' | '그래픽' | '기타';
  length?: string;
  alternative_subtypes?: string[];
}
interface OutfitMeta {
  gender?: 'female' | 'male' | 'unisex' | 'unknown';
  gender_confidence?: number;
  gender_signals?: string[];
  price_tier?: 'budget' | 'mid' | 'premium' | 'luxury';
  price_tier_confidence?: number;
  price_signals?: string[];
  price_range_estimate?: { min: number; max: number };
  season?: string;
  vibe?: string[];
}

interface AnalysisResult {
  categories: Partial<Record<FashionCategoryKey, CategoryInfo | null>>;
  description: string;
}
type FullAnalysisResult = AnalysisResult & OutfitMeta;

async function analyzeImage(apiKey: string, imageBase64: string, mimeType: string): Promise<FullAnalysisResult> {
  console.log('[analyzeImage] start, mimeType:', mimeType, 'base64 length:', imageBase64.length);

  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel(
    {
      model: process.env.GEMINI_MODEL || 'gemini-2.5-flash',
      generationConfig: {
        temperature: 0.2,
        responseMimeType: "application/json",  // SESSION 14 hotfix: 마크다운 응답 차단, JSON 강제
      },
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
          color: typeof info.color === 'string' ? info.color : undefined,
          fit: typeof info.fit === 'string' ? info.fit : undefined,
          material: typeof info.material === 'string' ? info.material : undefined,
          design: typeof info.design === 'string' ? info.design : undefined,
          subtype: typeof info.subtype === 'string' ? info.subtype : undefined,
          pattern: typeof info.pattern === 'string' ? info.pattern as CategoryInfo['pattern'] : undefined,
          length: typeof info.length === 'string' ? info.length : undefined,
          alternative_subtypes: Array.isArray(info.alternative_subtypes) ? info.alternative_subtypes as string[] : undefined,
        };
      }

      if (Object.values(normalized).every((v) => v === null)) {
        throw Object.assign(new Error('이미지에서 옷을 인식하기 어려워요.'), { code: 'IMAGE_QUALITY' });
      }

      const meta: OutfitMeta = {};
      if (typeof parsed.gender === 'string') meta.gender = parsed.gender as OutfitMeta['gender'];
      if (typeof parsed.gender_confidence === 'number') meta.gender_confidence = parsed.gender_confidence;
      if (Array.isArray(parsed.gender_signals)) meta.gender_signals = parsed.gender_signals as string[];
      if (typeof parsed.price_tier === 'string') meta.price_tier = parsed.price_tier as OutfitMeta['price_tier'];
      if (typeof parsed.price_tier_confidence === 'number') meta.price_tier_confidence = parsed.price_tier_confidence;
      if (Array.isArray(parsed.price_signals)) meta.price_signals = parsed.price_signals as string[];
      if (parsed.price_range_estimate && typeof parsed.price_range_estimate === 'object') {
        const pr = parsed.price_range_estimate as Record<string, unknown>;
        if (typeof pr.min === 'number' && typeof pr.max === 'number')
          meta.price_range_estimate = { min: pr.min, max: pr.max };
      }
      if (typeof parsed.season === 'string') meta.season = parsed.season;
      if (Array.isArray(parsed.vibe)) meta.vibe = parsed.vibe as string[];

      console.log('[analyzeImage] success, categories:', Object.keys(normalized).filter((k) => normalized[k as FashionCategoryKey] !== null), 'gender:', meta.gender, 'price_tier:', meta.price_tier);
      return { categories: normalized, description: (parsed.description as string) || '', ...meta };

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

// ─── Gemini 2-pass rerank (SESSION 16: 정확도 끌어올리기) ──────────────────
// 목적: Naver 1차 검색 결과 중 attributes에 가장 일치하는 top N을 Gemini가 골라냄.
// 입력: 카테고리 attributes(color/subtype/pattern/length 등) + 후보 N개 (title/price/brand)
// 출력: top K 인덱스 배열. 실패 시 원본 순서 유지 (graceful fallback).
async function geminiRerank(
  apiKey: string,
  categoryName: string,
  attributes: Record<string, unknown>,
  candidates: Array<{ title: string; price: number; brand?: string; mallName?: string }>,
  topK = 10,
): Promise<number[]> {
  if (candidates.length <= topK) return candidates.map((_, i) => i);

  const candidateList = candidates
    .slice(0, 30) // 비용 제한: 상위 30개만
    .map((c, i) => `${i}: "${c.title.slice(0, 80)}" / ${c.price.toLocaleString()}원${c.brand ? ` / ${c.brand}` : ''}`)
    .join('\n');

  const attrSummary = Object.entries(attributes)
    .filter(([_, v]) => v != null && v !== '' && (Array.isArray(v) ? v.length > 0 : true))
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
    .join(' / ');

  const prompt = `한국 패션 검색 결과 재순위. 사용자가 찾는 ${categoryName} 속성과 가장 일치하는 ${topK}개를 골라라.

[목표 속성]
${attrSummary}

[후보 ${candidates.slice(0, 30).length}개]
${candidateList}

규칙:
- 색상/subtype/pattern/length 일치도가 가장 높은 순으로
- 가격이 price_range_estimate 안이면 가산점
- 광고성 키워드(최저가/100%정품/역대급)는 동점 시 후순위
- 정확히 ${topK}개 인덱스만 JSON 배열로 응답: [3, 7, 0, 12, ...]

★ 출력: 인덱스 배열 하나만. 다른 텍스트 절대 금지.`;

  try {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({
      model: 'gemini-2.5-flash',
      generationConfig: { temperature: 0.1, responseMimeType: 'application/json' },
    });
    const result = await model.generateContent(prompt);
    const text = result.response.text().trim();
    const arr = JSON.parse(text);
    if (!Array.isArray(arr)) throw new Error('not array');
    const valid = arr
      .map((n) => Number(n))
      .filter((n) => Number.isInteger(n) && n >= 0 && n < candidates.length)
      .slice(0, topK);
    console.log(`[geminiRerank] ${categoryName}: ${valid.length}/${topK} 인덱스 반환`);
    return valid.length > 0 ? valid : candidates.slice(0, topK).map((_, i) => i);
  } catch (err) {
    console.warn(`[geminiRerank] ${categoryName} 실패, 원본 순서 유지:`, serializeError(err).message);
    return candidates.slice(0, topK).map((_, i) => i);
  }
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
  return c.json({ message: serialized.message, name: serialized.name, code: serialized.code }, 500);
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

    // SESSION 16: Cloud Run v3 path 제거. Gemini-only로 단순화.
    if (!c.env.GEMINI_API_KEY) {
      console.error('[/api/analyze] GEMINI_API_KEY is missing');
      return c.json({ message: 'GEMINI_API_KEY 환경변수가 설정되지 않았어요.' }, 500);
    }

    const result = await analyzeImage(c.env.GEMINI_API_KEY, imageBase64, mimeType);
    return c.json({ ...result, _source: 'worker_gemini' });

  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    const serialized = serializeError(err);
    console.error('[/api/analyze] error:', serialized);

    if (error.code === 'QUOTA_EXCEEDED') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 429);
    if (error.code === 'IMAGE_QUALITY') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 422);
    if (error.code === 'SERVICE_UNAVAILABLE') return c.json({ message: serialized.message, name: serialized.name, code: error.code }, 503);
    return c.json({ message: serialized.message, name: serialized.name, code: serialized.code }, 500);
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
    return c.json({ message: serialized.message || '상품 검색 중 오류가 발생했어요.' }, 500);
  }
});

// ─── 색상 인식 헬퍼 ───────────────────────────────────────────────────────────
function expandQueriesWithAlternatives(
  primary: string[],
  color: string | undefined,
  alts: string[] | undefined,
): string[] {
  if (!alts || alts.length === 0) return primary;
  const colorPrefix = color ? `${color} ` : '';
  const altQueries = alts.map((alt) => `${colorPrefix}${alt}`);
  return [...primary.slice(0, 2), ...altQueries.slice(0, 2)];
}

function ensureColorPrefix(queries: string[], color?: string): string[] {
  if (!color) return queries;
  const colorTokens = color.split(/\s+/).filter((t) => t.length > 0);
  return queries.map((q) => {
    const hasColor = colorTokens.some((t) => q.includes(t));
    return hasColor ? q : `${color} ${q}`;
  });
}

function colorAwareRerank(products: NaverProduct[], color?: string): NaverProduct[] {
  if (!color) return products;
  const colorTokens = color.split(/\s+/).filter((t) => t.length >= 2);
  if (colorTokens.length === 0) return products;
  const titleHasColor = (p: NaverProduct) =>
    colorTokens.some((t) => (p.title || '').toLowerCase().includes(t.toLowerCase()));
  return [...products.filter(titleHasColor), ...products.filter((p) => !titleHasColor(p))];
}

function dedupeBySku(products: NaverProduct[]): NaverProduct[] {
  const seen = new Set<string>();
  const out: NaverProduct[] = [];
  for (const p of products) {
    const pidKey = p.id || '';
    const titleKey = (p.title || '')
      .replace(/<[^>]+>/g, '')
      .toLowerCase()
      .split(/\s+/)
      .slice(0, 6)
      .sort()
      .join(' ');
    const key = pidKey || titleKey;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}

// ─── Soft Score (검열 아닌 추론 — hard reject 절대 금지) ─────────────────────
const PATTERN_REGEX: Record<string, RegExp> = {
  '체크': /체크|타탄|플레이드|gingham|check|tartan|plaid/i,
  '스트라이프': /스트라이프|줄무늬|stripe|striped/i,
  '플로럴': /플로럴|꽃무늬|꽃|floral|flower/i,
  '도트': /도트|땡땡이|폴카|dot|polka/i,
  '카무': /카무|밀리터리|군복|camo|camouflage/i,
  '페이즐리': /페이즐리|paisley/i,
  '그래픽': /그래픽|로고|프린트|graphic|logo|print/i,
};
const SHORT_REGEX = /숏|미니|반바지|short|mini|3부|5부|버뮤다|크롭/i;
const LONG_REGEX = /롱|긴|long|7부|칠부|9부|구부|10부|풀렝스|카프리|capri|맥시/i;

interface SoftScoreContext {
  color?: string;
  gender?: string;
  gender_confidence?: number;
  price_range?: { min: number; max: number };
  price_tier?: string;
  pattern?: string;
  length?: string;
  category: string;
}

function softScoreProducts(
  products: NaverProduct[],
  ctx: SoftScoreContext,
): (NaverProduct & { _soft_score?: number })[] {
  return products
    .map((p) => {
      let score = 1.0;
      const title = (p.title || '').replace(/<[^>]+>/g, '').toLowerCase();

      // 1. 성별 신호 (soft — 반대 성별 토큰 시 신뢰도 비례 페널티)
      if (ctx.gender && (ctx.gender_confidence ?? 0) > 0.6) {
        const oppositeTokens =
          ctx.gender === 'female' ? /남성|남자|맨즈|men['']s|man['']s/i :
          ctx.gender === 'male'   ? /여성|여자|woman|girl|wife|와이프/i : null;
        if (oppositeTokens && oppositeTokens.test(title)) {
          score *= 0.3 + 0.1 * Math.min(1, ctx.gender_confidence!);
        }
        const sameTokens =
          ctx.gender === 'female' ? /여성|여자|woman/i :
          ctx.gender === 'male'   ? /남성|남자|men['']s/i : null;
        if (sameTokens && sameTokens.test(title)) score *= 1.1;
      }

      // 2. 가격 신호 (soft — 범위 대비 과도하게 벗어날 때만 감점)
      if (ctx.price_range && p.price && p.price > 0) {
        const { min: lo, max: hi } = ctx.price_range;
        if (p.price < lo / 5) score *= 0.7;
        else if (p.price < lo / 2) score *= 0.85;
        else if (p.price > hi * 5) score *= 0.5;
        else if (p.price > hi * 2) score *= 0.7;
        else if (p.price > hi) score *= 0.9;
      }

      // 3. 색상 신호 (soft — 색상 토큰 미매칭 시 감점)
      if (ctx.color) {
        const tokens = ctx.color.split(/\s+/).filter((t) => t.length >= 2);
        const matched = tokens.some((t) => title.includes(t.toLowerCase()));
        if (!matched) score *= 0.75;
      }

      // 4. 광고성 키워드 (미약한 페널티)
      if (/100%\s*정품|최저가|역대급|행사가|당일출고/i.test(title)) score *= 0.92;

      // 5. 패턴 신호 — Gemini 인식 패턴이 단색 아닌데 title에 패턴 토큰 없으면 강한 페널티
      if (ctx.pattern && ctx.pattern !== '단색' && ctx.pattern !== '기타') {
        const re = PATTERN_REGEX[ctx.pattern];
        if (re && !re.test(title)) score *= 0.4;
      }

      // 6. 길이 신호 — 짧은 의류 추정인데 긴 결과 (역도 동일) 강한 페널티
      if (ctx.length) {
        const intendedShort = SHORT_REGEX.test(ctx.length);
        const intendedLong = LONG_REGEX.test(ctx.length);
        const titleHasLong = LONG_REGEX.test(title);
        const titleHasShort = SHORT_REGEX.test(title);
        if (intendedShort && titleHasLong && !titleHasShort) score *= 0.3;
        if (intendedLong && titleHasShort && !titleHasLong) score *= 0.3;
      }

      // 7. 최솟값 보장 (완전 제거 방지)
      const final = 0.05 + score * 0.95;
      return { ...p, _soft_score: final };
    })
    .sort((a, b) => (b._soft_score ?? 0) - (a._soft_score ?? 0));
}

// ─── POST /api/search/categories — 카테고리별 다중 쿼리 병렬 검색 ────────────
app.post('/api/search/categories', async (c) => {
  console.log('[POST /api/search/categories] request received');
  try {
    let categories: Record<string, { keywords: string[]; searchQueries?: string[]; searchQuery?: string; color?: string; pattern?: string; length?: string; alternative_subtypes?: string[] } | null>;
    let outfit_meta: OutfitMeta | undefined;
    try {
      const body = await c.req.json();
      categories = body.categories;
      outfit_meta = body.outfit_meta as OutfitMeta | undefined;
    } catch (jsonErr) {
      return c.json({ message: '요청 본문 파싱 실패', detail: String(jsonErr) }, 400);
    }

    if (!categories) return c.json({ message: '카테고리 데이터가 필요해요.' }, 400);

    const entries = Object.entries(categories).filter(([, v]) => v !== null && typeof v === 'object') as [string, NonNullable<(typeof categories)[string]>][];
    if (entries.length === 0) return c.json({ message: '검색할 카테고리가 없어요.' }, 400);

    console.log('[/api/search/categories] searching categories:', entries.map(([k]) => k));

    const results = await Promise.all(
      entries.map(async ([category, info]) => {
        const rawQueries = Array.isArray(info.searchQueries) && info.searchQueries.length > 0
          ? info.searchQueries.slice(0, 3)
          : info.searchQuery ? [info.searchQuery]
          : [info.keywords.slice(0, 3).join(' ')];

        const expandedQueries = expandQueriesWithAlternatives(rawQueries, info.color, info.alternative_subtypes);
        const colorEnforcedQueries = ensureColorPrefix(expandedQueries, info.color);

        try {
          const searchResults = await Promise.all(
            colorEnforcedQueries.map((q) =>
              searchNaver(c.env.NAVER_CLIENT_ID, c.env.NAVER_CLIENT_SECRET, q, 20, 1)
                .catch((e) => { console.error(`[/categories] query "${q}" failed:`, serializeError(e)); return null; }),
            ),
          );

          let merged = searchResults
            .filter((r): r is NonNullable<typeof r> => r !== null)
            .flatMap((r) => r.products);

          // 0건이면 원본 쿼리로 재시도
          if (merged.length === 0 && colorEnforcedQueries[0] !== rawQueries[0]) {
            const fallbackResults = await Promise.all(
              rawQueries.map((q) =>
                searchNaver(c.env.NAVER_CLIENT_ID, c.env.NAVER_CLIENT_SECRET, q, 20, 1)
                  .catch(() => null),
              ),
            );
            merged = fallbackResults.filter(Boolean).flatMap((r) => r!.products);
          }

          const deduped = dedupeBySku(merged);
          const ctx: SoftScoreContext = {
            color: info.color,
            gender: outfit_meta?.gender,
            gender_confidence: outfit_meta?.gender_confidence,
            price_range: outfit_meta?.price_range_estimate,
            price_tier: outfit_meta?.price_tier,
            pattern: info.pattern,
            length: info.length,
            category,
          };
          const softScored = softScoreProducts(deduped, ctx).slice(0, 40);
          const totalMax = Math.max(...searchResults.filter(Boolean).map((r) => r!.total), 0);

          // SESSION 16: 2-pass Gemini rerank (정확도 끌어올리기)
          // softScore로 휴리스틱 정렬 → Gemini가 최종 top 10 골라냄
          let finalProducts = softScored;
          if (softScored.length > 10 && c.env.GEMINI_API_KEY) {
            const attributes = {
              color: info.color, subtype: info.keywords?.[1], pattern: info.pattern,
              length: info.length, gender: outfit_meta?.gender, price_tier: outfit_meta?.price_tier,
              price_range: outfit_meta?.price_range_estimate, keywords: info.keywords,
            };
            const rerankIdx = await geminiRerank(c.env.GEMINI_API_KEY, category, attributes, softScored, 10)
              .catch(() => softScored.slice(0, 10).map((_, i) => i));
            const picked = rerankIdx.map((i) => softScored[i]).filter(Boolean);
            const pickedIds = new Set(picked.map((p) => p.id));
            const rest = softScored.filter((p) => !pickedIds.has(p.id));
            finalProducts = [...picked, ...rest].slice(0, 40);
          }

          console.log(`[/categories] ${category}: color="${info.color}" pattern="${info.pattern}" length="${info.length}" gender="${ctx.gender}" → ${finalProducts.length}개 (rerank: ${softScored.length > 10 ? 'ON' : 'OFF'})`);
          return { category, keywords: info.keywords, products: finalProducts, total: totalMax, query: colorEnforcedQueries[0] };
        } catch (catErr) {
          console.error(`[/categories] ${category} 전체 실패:`, serializeError(catErr));
          return { category, keywords: info.keywords, products: [], total: 0, query: colorEnforcedQueries[0] };
        }
      }),
    );

    const filtered = results.filter((r) => r.products.length > 0);
    const missing_categories = Object.entries(categories)
      .filter(([, v]) => v === null)
      .map(([k]) => k);
    console.log(`[/categories] 응답 카테고리 수: ${filtered.length}, 누락: ${missing_categories}`);
    return c.json({ results: filtered, missing_categories });

  } catch (err: unknown) {
    const serialized = serializeError(err);
    console.error('[/api/search/categories] error:', serialized);
    return c.json({ message: serialized.message || '카테고리별 검색 중 오류가 발생했어요.' }, 500);
  }
});

// ─── POST /api/search-image — Naver fallback (SESSION 16: Cloud Run 제거) ────
app.post('/api/search-image', async (c) => {
  console.log('[POST /api/search-image] request received');
  let fallbackQuery: string;
  try {
    const body = await c.req.json<{ query?: string }>();
    fallbackQuery = body.query || '';
  } catch {
    return c.json({ message: '요청 본문 파싱 실패' }, 400);
  }

  if (!fallbackQuery) return c.json({ message: '검색어가 필요해요.' }, 400);

  try {
    const result = await searchNaver(c.env.NAVER_CLIENT_ID, c.env.NAVER_CLIENT_SECRET, fallbackQuery);
    return c.json(result);
  } catch (err) {
    const s = serializeError(err);
    return c.json({ message: s.message }, 500);
  }
});

// ─── POST /api/click — 클릭 이벤트 (SESSION 16: no-op, Cloud Run 제거) ─────
app.post('/api/click', async () => {
  // 클릭 로깅 endpoint는 유지하되 forwarding 제거. 추후 Cloudflare D1/R2로 자체 저장 가능.
  return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } });
});

// 404
app.notFound((c) => c.json({ message: '요청한 API를 찾을 수 없어요.' }, 404));

export default app;
