import { Router, Request, Response } from 'express';
import { analyzeImageWithGemini, analyzeImageUrlWithGemini } from '../services/gemini';

const router = Router();

// POST /api/analyze — 이미지 base64로 분석 (P0-1)
router.post('/', async (req: Request, res: Response) => {
  try {
    const { imageBase64, mimeType } = req.body;

    if (!imageBase64 || typeof imageBase64 !== 'string') {
      return res.status(400).json({ message: '이미지 데이터가 필요해요.' });
    }

    if (!mimeType || !['image/jpeg', 'image/png', 'image/webp'].includes(mimeType)) {
      return res.status(400).json({ message: '지원하지 않는 이미지 형식이에요.' });
    }

    // 이미지 크기 검증 (base64: 10MB → ~13.3MB base64)
    if (imageBase64.length > 14 * 1024 * 1024) {
      return res.status(400).json({ message: '이미지 파일이 너무 커요. 10MB 이하로 업로드해 주세요.' });
    }

    const result = await analyzeImageWithGemini(imageBase64, mimeType);
    return res.json(result);
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[analyze]', error.message);
    return res.status(500).json({
      message: error.message || '이미지 분석 중 오류가 발생했어요.',
      code: error.code,
    });
  }
});

export default router;
