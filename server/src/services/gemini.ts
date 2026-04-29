import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

const model = genAI.getGenerativeModel({
  model: process.env.GEMINI_MODEL || 'gemini-2.5-flash',
  generationConfig: {
    temperature: 0.2,  // 일관된 키워드 추출을 위해 낮게 설정
  },
  safetySettings: [
    { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
    { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
  ],
});

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// 요청 사이 1초 딜레이 + 429 시 3초 후 재시도 (최대 3회)
async function generateWithRetry(
  ...args: Parameters<typeof model.generateContent>
): Promise<ReturnType<typeof model.generateContent>> {
  const MAX_RETRIES = 3;
  const RETRY_DELAY_MS = 3000;
  const REQUEST_DELAY_MS = 1000;

  await sleep(REQUEST_DELAY_MS);

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await model.generateContent(...args);
    } catch (err: unknown) {
      const error = err as Error & { status?: number; statusCode?: number; message?: string };
      const is429 =
        error.status === 429 ||
        error.statusCode === 429 ||
        (error.message ?? '').includes('429') ||
        (error.message ?? '').toLowerCase().includes('resource_exhausted');

      if (is429 && attempt < MAX_RETRIES) {
        console.warn(`[gemini] 429 rate limit — ${RETRY_DELAY_MS / 1000}초 후 재시도 (${attempt}/${MAX_RETRIES - 1})`);
        await sleep(RETRY_DELAY_MS);
        continue;
      }
      if (is429) {
        throw Object.assign(
          new Error('AI 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.'),
          { code: 'QUOTA_EXCEEDED' },
        );
      }
      throw err;
    }
  }
  throw Object.assign(
    new Error('AI 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.'),
    { code: 'QUOTA_EXCEEDED' },
  );
}

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
    "bottom": {
      "color": "블랙",
      "fit": "와이드",
      "material": "데님",
      "design": "일자핏",
      "style": "캐주얼",
      "keywords": ["블랙", "와이드", "데님", "일자핏", "청바지"],
      "searchQueries": [
        "블랙 와이드 청바지",
        "데님 일자핏 팬츠",
        "블랙 와이드 데님 바지"
      ]
    },
    "shoes": null,
    "outer": null,
    "bag": null,
    "accessory": null
  },
  "description": "아이보리 오버핏 맨투맨과 블랙 와이드 데님의 캐주얼 코디"
}

카테고리 정의:
- top: 상의 (티셔츠, 블라우스, 니트, 맨투맨, 후드티, 셔츠 등)
- bottom: 하의 (청바지, 슬랙스, 치마, 반바지, 레깅스 등)
- shoes: 신발 (스니커즈, 부츠, 슬리퍼, 구두, 샌들 등)
- outer: 아우터 (코트, 자켓, 패딩, 가디건, 점퍼 등)
- bag: 가방 (백팩, 숄더백, 크로스백, 토트백, 클러치 등)
- accessory: 액세서리 (모자, 스카프, 벨트, 선글라스, 귀걸이 등)

필드별 추출 규칙:
- color: 주요 색상 1가지 (예: 아이보리, 차콜그레이, 네이비블루)
- fit: 실루엣/핏 (예: 오버핏, 슬림핏, 와이드, A라인, 크롭)
- material: 소재 추정 (예: 코튼, 린넨, 니트, 데님, 폴리에스터, 울)
- design: 디자인 특징 1~2가지 (예: 라운드넥, 브이넥, 후드, 집업, 스트라이프)
- style: 전체 스타일 (예: 캐주얼, 미니멀, 빈티지, 스트릿, 오피스룩, 페미닌)
- keywords: 위 5가지에서 핵심어 추출 + 아이템 종류 포함 (4~7개)
- searchQueries: 반드시 3개, 각각 다른 조합으로 (색상+핏+아이템 / 소재+아이템+스타일 / 디자인+아이템)

공통 규칙:
- 이미지에서 확인되지 않는 카테고리는 반드시 null (6개 키 모두 포함)
- searchQueries는 한국어, 실제 쇼핑몰 검색처럼 자연스럽게, 각 2~4단어
- 이미지 품질이 낮거나 패션 아이템이 없으면 {"error": "IMAGE_QUALITY"} 반환`;

export type FashionCategoryKey = 'top' | 'bottom' | 'shoes' | 'outer' | 'bag' | 'accessory';

export interface GeminiCategoryInfo {
  keywords: string[];
  searchQueries: string[];  // 2~3가지 키워드 조합 쿼리
}

export interface GeminiAnalysisResult {
  categories: Partial<Record<FashionCategoryKey, GeminiCategoryInfo | null>>;
  description: string;
}

export async function analyzeImageWithGemini(
  imageBase64: string,
  mimeType: string,
): Promise<GeminiAnalysisResult> {
  const result = await generateWithRetry([
    {
      inlineData: {
        data: imageBase64,
        mimeType: mimeType as 'image/jpeg' | 'image/png' | 'image/webp',
      },
    },
    FASHION_PROMPT,
  ]);

  const usage = result.response.usageMetadata;
  if (usage) {
    console.log('[gemini] tokens — input:', usage.promptTokenCount, '/ output:', usage.candidatesTokenCount, '/ total:', usage.totalTokenCount);
  }

  const text = result.response.text().trim();

  // JSON 파싱 (마크다운 코드블록 제거)
  const jsonText = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
  const parsed = JSON.parse(jsonText);

  if (parsed.error === 'IMAGE_QUALITY') {
    throw Object.assign(new Error('이미지에서 옷을 명확하게 인식하기 어려워요. 옷이 잘 보이는 사진으로 다시 시도해 주세요.'), { code: 'IMAGE_QUALITY' });
  }

  if (!parsed.categories || typeof parsed.categories !== 'object') {
    throw new Error('분석 결과를 처리하는 중 오류가 발생했어요.');
  }

  // 카테고리별 searchQueries 정규화 (searchQuery 단일 문자열도 허용)
  const normalizedCategories: Partial<Record<FashionCategoryKey, GeminiCategoryInfo | null>> = {};
  for (const [key, val] of Object.entries(parsed.categories)) {
    if (val === null || val === undefined) {
      normalizedCategories[key as FashionCategoryKey] = null;
      continue;
    }
    if (typeof val !== 'object') continue;

    const info = val as Record<string, unknown>;
    let searchQueries: string[] = [];

    if (Array.isArray(info.searchQueries) && info.searchQueries.length > 0) {
      searchQueries = (info.searchQueries as string[]).slice(0, 3);
    } else if (typeof info.searchQuery === 'string' && info.searchQuery) {
      // 하위 호환: 단일 searchQuery를 배열로 변환
      searchQueries = [info.searchQuery];
    } else if (Array.isArray(info.keywords)) {
      searchQueries = [(info.keywords as string[]).slice(0, 3).join(' ')];
    }

    if (searchQueries.length === 0) continue;

    normalizedCategories[key as FashionCategoryKey] = {
      keywords: Array.isArray(info.keywords) ? info.keywords as string[] : [],
      searchQueries,
    };
  }

  // 유효한 카테고리가 하나도 없으면 에러
  const validCategories = Object.values(normalizedCategories).filter((v) => v !== null);
  if (validCategories.length === 0) {
    throw Object.assign(
      new Error('이미지에서 옷을 명확하게 인식하기 어려워요. 옷이 잘 보이는 사진으로 다시 시도해 주세요.'),
      { code: 'IMAGE_QUALITY' },
    );
  }

  return {
    categories: normalizedCategories,
    description: parsed.description || '',
  };
}

export async function analyzeImageUrlWithGemini(imageUrl: string): Promise<GeminiAnalysisResult> {
  const fetch = (await import('node-fetch')).default;

  const imgRes = await fetch(imageUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; WhereGo/1.0)',
    },
    signal: AbortSignal.timeout(8000),
  });

  if (!imgRes.ok) {
    if (imgRes.status === 403 || imgRes.status === 401) {
      throw Object.assign(
        new Error('비공개 계정이거나 이미지에 접근할 수 없어요. 사진을 직접 저장한 후 업로드해 주세요.'),
        { code: 'PRIVATE_ACCOUNT' },
      );
    }
    throw new Error(`이미지를 불러올 수 없어요 (${imgRes.status})`);
  }

  const contentType = imgRes.headers.get('content-type') || 'image/jpeg';
  const buffer = await imgRes.arrayBuffer();
  const base64 = Buffer.from(buffer).toString('base64');

  return analyzeImageWithGemini(base64, contentType.split(';')[0]);
}
