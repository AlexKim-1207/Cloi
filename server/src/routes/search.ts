import { Router, Request, Response } from 'express';
import { searchNaverShopping } from '../services/naverShopping';

const router = Router();

// POST /api/search — 키워드로 네이버 쇼핑 검색 (P0-5, 더 보기용)
router.post('/', async (req: Request, res: Response) => {
  try {
    const { query, keywords, start } = req.body;

    if (!query && (!keywords || !Array.isArray(keywords) || keywords.length === 0)) {
      return res.status(400).json({ message: '검색 키워드가 필요해요.' });
    }

    const startIndex = typeof start === 'number' && start > 0 ? start : 1;
    const result = await searchNaverShopping(query || '', keywords || [], 20, startIndex);
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

// POST /api/search/categories — 카테고리별 병렬 검색 (다중 쿼리 조합 → 결과 병합)
// body: { categories: { top: { keywords, searchQueries: string[] }, bottom: null, ... } }
// returns: { results: [{ category, keywords, products, total, query }, ...] }
router.post('/categories', async (req: Request, res: Response) => {
  try {
    const { categories } = req.body;

    if (!categories || typeof categories !== 'object') {
      return res.status(400).json({ message: '카테고리 데이터가 필요해요.' });
    }

    type CategoryEntry = {
      keywords: string[];
      searchQueries?: string[];   // 다중 쿼리 (신규)
      searchQuery?: string;       // 단일 쿼리 (하위 호환)
    };

    const entries = Object.entries(categories as Record<string, CategoryEntry | null>).filter(
      ([, info]) => info !== null && info !== undefined && typeof info === 'object',
    ) as [string, CategoryEntry][];

    if (entries.length === 0) {
      return res.status(400).json({ message: '검색할 카테고리가 없어요.' });
    }

    const results = await Promise.all(
      entries.map(async ([category, info]) => {
        // searchQueries 우선, 없으면 searchQuery 단일 배열로 변환
        const queries: string[] =
          Array.isArray(info.searchQueries) && info.searchQueries.length > 0
            ? info.searchQueries.slice(0, 3)
            : info.searchQuery
            ? [info.searchQuery]
            : [info.keywords.slice(0, 3).join(' ')];

        try {
          // 쿼리별 병렬 검색
          const searchResults = await Promise.all(
            queries.map((q) => searchNaverShopping(q, info.keywords, 20, 1).catch(() => null)),
          );

          // 상품 병합 + ID 기준 중복 제거 (첫 번째 쿼리 순서 우선)
          const seenIds = new Set<string>();
          const mergedProducts = searchResults
            .filter((r): r is NonNullable<typeof r> => r !== null)
            .flatMap((r) => r.products)
            .filter((p) => {
              if (seenIds.has(p.id)) return false;
              seenIds.add(p.id);
              return true;
            })
            .slice(0, 40); // 카테고리당 최대 40개

          const totalMax = Math.max(...searchResults.filter(Boolean).map((r) => r!.total), 0);

          return {
            category,
            keywords: info.keywords,
            products: mergedProducts,
            total: totalMax,
            query: queries[0],
          };
        } catch (err) {
          console.error(`[search/categories] ${category} 검색 실패:`, (err as Error).message);
          return { category, keywords: info.keywords, products: [], total: 0, query: queries[0] };
        }
      }),
    );

    const filtered = results.filter((r) => r.products.length > 0);
    return res.json({ results: filtered });
  } catch (err: unknown) {
    const error = err as Error & { code?: string };
    console.error('[search/categories]', error.message);
    return res.status(500).json({
      message: error.message || '카테고리별 상품 검색 중 오류가 발생했어요.',
      code: error.code,
    });
  }
});

export default router;
