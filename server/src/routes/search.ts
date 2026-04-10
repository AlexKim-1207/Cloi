import { Router, Request, Response } from 'express';
import { searchNaverShopping } from '../services/naverShopping';

const router = Router();

// POST /api/search — 키워드로 네이버 쇼핑 검색 (P0-5)
router.post('/', async (req: Request, res: Response) => {
  try {
    const { query, keywords } = req.body;

    if (!query && (!keywords || !Array.isArray(keywords) || keywords.length === 0)) {
      return res.status(400).json({ message: '검색 키워드가 필요해요.' });
    }

    const result = await searchNaverShopping(query || '', keywords || []);
    return res.json(result);
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[search]', error.message);
    return res.status(500).json({
      message: error.message || '상품 검색 중 오류가 발생했어요.',
      code: error.code,
    });
  }
});

export default router;
