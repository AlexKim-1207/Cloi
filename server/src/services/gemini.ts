import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

const model = genAI.getGenerativeModel({
  model: 'gemini-2.0-flash',
  safetySettings: [
    { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
    { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
  ],
});

const FASHION_PROMPT = `당신은 패션 전문가입니다. 이미지에서 옷을 분석하고 한국 쇼핑몰에서 검색하기 좋은 키워드를 추출해 주세요.

다음 JSON 형식으로만 응답해 주세요:
{
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
  "searchQuery": "네이버 쇼핑 검색용 최적화된 키워드 (2~4개 단어)",
  "description": "이 옷에 대한 한 줄 설명 (한국어)"
}

keywords 규칙:
- 색상 (예: "아이보리", "블랙", "네이비 블루")
- 실루엣/핏 (예: "오버핏", "슬림핏", "A라인")
- 소재 (예: "코튼", "린넨", "니트")
- 스타일 (예: "미니멀", "캐주얼", "빈티지")
- 아이템 종류 (예: "후드티", "와이드팬츠", "미디 스커트")
- 최소 5개, 최대 8개 키워드

searchQuery 규칙:
- 한국어로 작성
- 쇼핑몰에서 실제로 검색할 법한 자연스러운 형태
- 예시: "아이보리 오버핏 맨투맨", "블랙 와이드 슬랙스"

이미지에 옷이 명확하지 않거나 품질이 낮으면 {"error": "IMAGE_QUALITY"} 를 반환하세요.`;

export interface GeminiAnalysisResult {
  keywords: string[];
  searchQuery: string;
  description: string;
}

export async function analyzeImageWithGemini(
  imageBase64: string,
  mimeType: string,
): Promise<GeminiAnalysisResult> {
  const result = await model.generateContent([
    {
      inlineData: {
        data: imageBase64,
        mimeType: mimeType as 'image/jpeg' | 'image/png' | 'image/webp',
      },
    },
    FASHION_PROMPT,
  ]);

  const text = result.response.text().trim();

  // JSON 파싱 (마크다운 코드블록 제거)
  const jsonText = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
  const parsed = JSON.parse(jsonText);

  if (parsed.error === 'IMAGE_QUALITY') {
    throw Object.assign(new Error('이미지에서 옷을 명확하게 인식하기 어려워요. 옷이 잘 보이는 사진으로 다시 시도해 주세요.'), { code: 'IMAGE_QUALITY' });
  }

  if (!parsed.keywords || !Array.isArray(parsed.keywords)) {
    throw new Error('분석 결과를 처리하는 중 오류가 발생했어요.');
  }

  return {
    keywords: parsed.keywords,
    searchQuery: parsed.searchQuery || parsed.keywords.slice(0, 3).join(' '),
    description: parsed.description || '',
  };
}

export async function analyzeImageUrlWithGemini(imageUrl: string): Promise<GeminiAnalysisResult> {
  // URL로 이미지 가져오기 (Instagram 공개 게시물)
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
