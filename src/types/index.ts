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

export interface AnalysisKeywords {
  keywords: string[];    // Gemini가 추출한 패션 키워드
  searchQuery: string;   // 네이버 쇼핑 검색용 조합 쿼리
  description: string;   // 분석 결과 설명 (한국어)
}

export interface SearchResult {
  products: Product[];
  total: number;
  query: string;
}

export type AppState = 'home' | 'loading' | 'result' | 'error';
export type LoadingStep = 'analyzing' | 'searching';

export interface AppError {
  message: string;
  code?: string;
  retryable: boolean;
}
