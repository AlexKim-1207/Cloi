import { Router, Request, Response } from 'express';
import { createHash } from 'crypto';
import { analyzeImageWithGemini } from '../services/gemini';

const router = Router();

// POST / — 이미지 분석 (FASHION_API_URL 있으면 Python API 프록시, 없으면 Gemini fallback)
router.post('/', async (req: Request, res: Response) => {
  try {
    const { imageBase64, mimeType } = req.body;

    if (!imageBase64 || typeof imageBase64 !== 'string') {
      return res.status(400).json({ message: '이미지 데이터가 필요해요.' });
    }

    if (!mimeType || !['image/jpeg', 'image/png', 'image/webp'].includes(mimeType)) {
      return res.status(400).json({ message: '지원하지 않는 이미지 형식이에요.' });
    }

    if (imageBase64.length > 14 * 1024 * 1024) {
      return res.status(400).json({ message: '이미지 파일이 너무 커요. 10MB 이하로 업로드해 주세요.' });
    }

    const fashionApiUrl = process.env.FASHION_API_URL;
    if (fashionApiUrl) {
      try {
        const imageBuffer = Buffer.from(imageBase64, 'base64');
        const imageHash = createHash('sha256').update(imageBuffer).digest('hex');

        const form = new FormData();
        form.append('file', new Blob([imageBuffer], { type: mimeType }), 'image.jpg');

        const resp = await fetch(`${fashionApiUrl}/api/search`, {
          method: 'POST',
          body: form,
          signal: AbortSignal.timeout(30_000),
        });

        if (!resp.ok) {
          throw new Error(`Python API returned ${resp.status}`);
        }

        const data = await resp.json() as Record<string, unknown>;
        return res.json({ ...data, _source: 'v2', _imageHash: imageHash });
      } catch (proxyErr) {
        const msg = proxyErr instanceof Error ? proxyErr.message : String(proxyErr);
        console.warn('[analyze] Python API unavailable, falling back to Gemini:', msg);
        // fall through to Gemini fallback
      }
    }

    const result = await analyzeImageWithGemini(imageBase64, mimeType);
    return res.json(result);
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[analyze]', error.code ?? '', error.message);

    if (error.code === 'QUOTA_EXCEEDED') {
      return res.status(429).json({ message: error.message, code: error.code });
    }
    if (error.code === 'IMAGE_QUALITY') {
      return res.status(422).json({ message: error.message, code: error.code });
    }
    return res.status(500).json({ message: '이미지 분석 중 오류가 발생했어요.', code: error.code });
  }
});

// POST /click/:imageHash/:productId — 상품 클릭 이벤트를 Python API로 포워딩
router.post('/click/:imageHash/:productId', async (req: Request, res: Response) => {
  const { imageHash, productId } = req.params;
  const { category } = req.query;
  const fashionApiUrl = process.env.FASHION_API_URL || 'http://localhost:8000';

  try {
    const qs = category ? `?category=${encodeURIComponent(String(category))}` : '';
    const url = `${fashionApiUrl}/api/search/${imageHash}/click/${productId}${qs}`;

    const resp = await fetch(url, {
      method: 'POST',
      signal: AbortSignal.timeout(5_000),
    });

    const data = resp.ok ? await resp.json().catch(() => ({})) : {};
    return res.status(200).json(data);
  } catch {
    return res.status(200).json({});
  }
});

export default router;
