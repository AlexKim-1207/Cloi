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

export interface AnalysisKeywords {
  keywords: string[];
  searchQuery: string;
  description: string;
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
  products: Product[];
  categoryResults?: CategorySearchResult[];
}

export type AppState = 'home' | 'loading' | 'result' | 'error' | 'favorites';
export type LoadingStep = 'analyzing' | 'searching';

export interface AppError {
  message: string;
  code?: string;
  retryable: boolean;
}

// ─── Python Fashion API v2 types ─────────────────────────────────────────────

export interface ItemDetailV2 {
  category: string;
  color?: string;
  fit?: string;
  material?: string;
}

export interface StyleContext {
  overall_style: string;
  mood_tags: string[];
  items: ItemDetailV2[];
  confidence: number;
}

export interface ProductCardV2 {
  product_id: string;
  title: string;
  price: number;
  image_url: string;
  link: string;
  platform: string;
  category: string;
  similarity_score: number;
}

export interface SearchResponseV2 {
  style_context: StyleContext;
  results: Record<string, ProductCardV2[]>;
  cached: boolean;
  latency_ms: number;
  _source: 'v2';
  _imageHash: string;
}

// ─── Python Fashion API v3 types (멀티아이템 + 탭 + 무드랭킹) ─────────────────

export interface ProductCardV3 {
  id: string;
  title: string;
  image: string;
  price: number | null;
  link: string;
  mall_name: string | null;
  match_score: number;
  clip_similarity: number;
  mood_match: number;
  price_fit: number;
}

export interface TabSectionV3 {
  tab_id: string;
  label: string;
  description: string;
  items: ProductCardV3[];
}

export interface SearchResponseV3 {
  image_hash: string;
  overall_style: string;
  detected_attributes: {
    mood?: string;
    price_tier?: string;
    price_range?: number[];
    neckline?: string;
    fit?: string;
  };
  tabs: TabSectionV3[];
  total_latency_ms: number;
  cache_hit: boolean;
  _source: 'v3';
  _imageHash: string;
}
