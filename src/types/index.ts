export interface Product {
  id: string;
  title: string;       // 상품명 (HTML 태그 제거 필요)
  price: number;       // 최저가 (원)
  image: string;       // 상품 이미지 URL
  link: string;        // 상품 링크
  mallName: string;    // 쇼핑몰 이름 (무신사, 에이블리 등)
  brand?: string;      // 브랜드명
  category?: string;   // 카테고리
}

export type FashionCategory = 'top' | 'bottom' | 'shoes' | 'outer' | 'bag' | 'accessory';

export const CATEGORY_LABELS: Record<FashionCategory, string> = {
  top: '상의',
  bottom: '하의',
  shoes: '신발',
  outer: '아우터',
  bag: '가방',
  accessory: '액세서리',
};

export const CATEGORY_ORDER: FashionCategory[] = ['top', 'bottom', 'shoes', 'outer', 'bag', 'accessory'];

export interface CategoryInfo {
  keywords: string[];
  searchQuery: string;
}

export interface CategoryAnalysisResult {
  categories: Partial<Record<FashionCategory, CategoryInfo | null>>;
  description: string;
}

export interface CategorySearchResult {
  category: FashionCategory;
  keywords: string[];
  products: Product[];
  total: number;
  query: string;
}

// 하위 호환용 (analyzeImage 반환 타입으로 유지)
export interface AnalysisKeywords {
  keywords: string[];    // Gemini가 추출한 패션 키워드 (전체 카테고리 합산)
  searchQuery: string;   // 네이버 쇼핑 검색용 조합 쿼리
  description: string;   // 분석 결과 설명 (한국어)
}

export interface SearchResult {
  products: Product[];
  total: number;
  query: string;
}

export interface HistoryItem {
  id: string;
  timestamp: number;
  keywords: string[];
  searchQuery: string;
  products: Product[];          // 썸네일용 (카테고리 전체 합산 앞 6개)
  categoryResults?: CategorySearchResult[];
}

export type AppState = 'home' | 'loading' | 'result' | 'error' | 'favorites';
export type LoadingStep = 'analyzing' | 'searching';

export interface AppError {
  message: string;
  code?: string;
  retryable: boolean;
}
