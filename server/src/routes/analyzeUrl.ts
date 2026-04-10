import { Router, Request, Response } from 'express';
import { analyzeImageUrlWithGemini } from '../services/gemini';

const router = Router();

// POST /api/analyze-url — Instagram URL로 분석 (P0-2)
// 주의: Instagram ToS 검토 필요 (OQ-1). 현재는 공개 이미지 URL만 지원.
router.post('/', async (req: Request, res: Response) => {
  try {
    const { imageUrl } = req.body;

    if (!imageUrl || typeof imageUrl !== 'string') {
      return res.status(400).json({ message: '이미지 URL이 필요해요.' });
    }

    // URL 유효성 검증
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(imageUrl);
    } catch {
      return res.status(400).json({ message: '올바른 URL 형식이 아니에요.' });
    }

    // Instagram 링크인 경우 직접 이미지 URL이 아닐 수 있음
    // instagram.com/p/... 형태는 실제 이미지 URL이 아니므로 안내
    if (parsedUrl.hostname.includes('instagram.com') && !imageUrl.includes('/media/')) {
      return res.status(422).json({
        message: '인스타그램 게시물 링크에서 이미지를 자동으로 가져오는 기능은 준비 중이에요. 이미지를 직접 저장한 후 업로드해 주세요.',
        code: 'INSTAGRAM_SCRAPING_PENDING',
      });
    }

    const result = await analyzeImageUrlWithGemini(imageUrl);
    return res.json(result);
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[analyze-url]', error.message);
    return res.status(500).json({
      message: error.message || 'URL 분석 중 오류가 발생했어요.',
      code: error.code,
    });
  }
});

export default router;
