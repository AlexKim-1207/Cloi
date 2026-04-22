const NAVER_API_URL = 'https://openapi.naver.com/v1/search/shop.json';

export interface NaverProduct {
  id: string;
  title: string;
  price: number;
  image: string;
  link: string;
  mallName: string;
  brand: string;
  category: string;
}

export interface NaverSearchResult {
  products: NaverProduct[];
  total: number;
  query: string;
}

// HTML 태그 제거
function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '');
}

export async function searchNaverShopping(
  query: string,
  keywords: string[],
  display = 20,
  start = 1,
): Promise<NaverSearchResult> {
  const fetch = (await import('node-fetch')).default;

  // 키워드 조합으로 검색어 최적화
  const searchQuery = query || keywords.slice(0, 3).join(' ');

  const params = new URLSearchParams({
    query: searchQuery,
    display: String(display),
    start: String(start),
    sort: 'sim', // 정확도순
  });

  const res = await fetch(`${NAVER_API_URL}?${params}`, {
    headers: {
      'X-Naver-Client-Id': process.env.NAVER_CLIENT_ID!,
      'X-Naver-Client-Secret': process.env.NAVER_CLIENT_SECRET!,
    },
    signal: AbortSignal.timeout(5000),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('네이버 쇼핑 API 인증에 실패했어요. API 키를 확인해 주세요.');
    }
    throw new Error(`상품 검색에 실패했어요 (${res.status})`);
  }

  const data = await res.json() as {
    total: number;
    items: Array<{
      productId: string;
      title: string;
      lprice: string;
      image: string;
      link: string;
      mallName: string;
      brand: string;
      category1: string;
    }>;
  };

  const products: NaverProduct[] = (data.items || []).map((item) => ({
    id: item.productId || String(Math.random()),
    title: stripHtml(item.title),
    price: parseInt(item.lprice, 10) || 0,
    image: item.image,
    link: item.link,
    mallName: item.mallName || '',
    brand: item.brand || '',
    category: item.category1 || '',
  }));

  return {
    products,
    total: data.total || 0,
    query: searchQuery,
  };
}
