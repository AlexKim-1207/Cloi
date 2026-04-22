import { Router, Request, Response } from 'express';
import { analyzeImageUrlWithGemini } from '../services/gemini';

const router = Router();

// POST /api/analyze-url — Instagram URL로 분석 (P0-2)
// 주의: Instagram ToS 검토 필요 (OQ-1). 현재는 공개 이미지 URL만 지원.
router.post('/', async (req: Request, res: Response) => {
  try {
    console.log('[analyze-url] Content-Type:', req.headers['content-type']);
    console.log('[analyze-url] req.body:', JSON.stringify(req.body));

    // imageUrl 또는 url 필드 모두 허용 (클라이언트 필드명 혼용 방어)
    const imageUrl: string | undefined = req.body?.imageUrl ?? req.body?.url;

    if (!imageUrl || typeof imageUrl !== 'string') {
      console.log('[analyze-url] 400 — imageUrl 없음. body keys:', Object.keys(req.body ?? {}));
      return res.status(400).json({ message: '이미지 URL이 필요해요. { imageUrl: "..." } 형식으로 보내주세요.' });
    }

    // URL 유효성 검증
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(imageUrl);
    } catch {
      return res.status(400).json({ message: '올바른 URL 형식이 아니에요.' });
    }

    // instagram.com/p/... 형태는 게시물 페이지 URL로 직접 이미지 URL이 아님
    if (parsedUrl.hostname.includes('instagram.com') && !imageUrl.includes('/media/')) {
      return res.status(400).json({
        message: '인스타그램 게시물 링크는 지원하지 않아요. 이미지를 직접 저장한 후 업로드하거나, 직접 이미지 URL(.jpg/.png)을 입력해 주세요.',
        code: 'INSTAGRAM_POST_URL_NOT_SUPPORTED',
      });
    }

    const result = await analyzeImageUrlWithGemini(imageUrl);
    return res.json(result);
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[analyze-url]', error.code ?? '', error.message);

    if (error.code === 'QUOTA_EXCEEDED') {
      return res.status(429).json({ message: error.message, code: error.code });
    }
    if (error.code === 'IMAGE_QUALITY') {
      return res.status(422).json({ message: error.message, code: error.code });
    }
    if (error.code === 'PRIVATE_ACCOUNT') {
      return res.status(403).json({ message: error.message, code: error.code });
    }
    return res.status(500).json({ message: 'URL 분석 중 오류가 발생했어요.', code: error.code });
  }
});

export default router;
