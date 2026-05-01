import { useEffect, useMemo, useState } from 'react';
import ProductCard from '../components/ProductCard';
import { recordClick, recordClickV3, searchProducts } from '../services/api';
import type {
  CategorySearchResult,
  FashionCategory,
  Product,
  ProductCardV2,
  ProductCardV3,
  SearchResponseV2,
  SearchResponseV3,
  TabSectionV3,
} from '../types';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../types';

interface ResultPageProps {
  categoryResults: CategorySearchResult[];
  favoriteIds: Set<string>;
  onBack: () => void;
  onToggleFavorite: (product: Product) => void;
  v2Response?: SearchResponseV2;
  v3Response?: SearchResponseV3;
}

type SortType = 'sim' | 'price_asc' | 'price_desc';
type PlatformFilter = 'all' | '무신사' | '에이블리' | '지그재그';

function v2ToProduct(p: ProductCardV2): Product {
  return {
    id: p.product_id,
    title: p.title,
    price: p.price,
    image: p.image_url,
    link: p.link,
    mallName: p.platform,
    category: p.category,
  };
}

function v3ToProduct(p: ProductCardV3): Product {
  return {
    id: p.id,
    title: p.title,
    price: p.price ?? 0,
    image: p.image,
    link: p.link,
    mallName: p.mall_name ?? '',
    category: '',
    cluster_size: p.cluster_size,
    min_price: p.min_price,
    max_price: p.max_price,
    other_sellers: p.other_sellers,
  };
}

function getCategoryLabel(cat: string): string {
  if (cat in CATEGORY_LABELS) return CATEGORY_LABELS[cat as FashionCategory];
  return cat;
}

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2c241f" strokeWidth="2">
      <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2c241f" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
    </svg>
  );
}

export default function ResultPage({
  categoryResults,
  favoriteIds,
  onBack,
  onToggleFavorite,
  v2Response,
  v3Response,
}: ResultPageProps) {
  const isV3 = Boolean(v3Response);
  const isV2 = Boolean(v2Response) && !isV3;

  const availableCategories = useMemo(() => {
    if (isV3 && v3Response) {
      return v3Response.tabs.filter((t) => t.items.length > 0).map((t) => t.tab_id);
    }
    if (isV2 && v2Response) {
      return Object.keys(v2Response.results).filter(
        (cat) => (v2Response.results[cat]?.length ?? 0) > 0,
      );
    }
    return CATEGORY_ORDER.filter((category) =>
      categoryResults.some((result) => result.category === category && result.products.length > 0),
    );
  }, [categoryResults, v2Response, v3Response, isV2, isV3]);

  const [activeTab, setActiveTab] = useState<string>(availableCategories[0] ?? 'top');
  const [sortType, setSortType] = useState<SortType>('sim');
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>('all');
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const [showFilter, setShowFilter] = useState(false);
  const [showKeywordEdit, setShowKeywordEdit] = useState(false);
  const [isReSearching, setIsReSearching] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [localResults, setLocalResults] = useState<CategorySearchResult[]>(categoryResults);
  const [offsets, setOffsets] = useState<Record<string, number>>({});

  const activeResult = !isV2 && !isV3 ? localResults.find((result) => result.category === activeTab) : null;
  const [editedKeywords, setEditedKeywords] = useState<string[]>(activeResult?.keywords ?? []);

  const activeV3Tab: TabSectionV3 | null = isV3 && v3Response
    ? v3Response.tabs.find((t) => t.tab_id === activeTab) ?? null
    : null;

  useEffect(() => {
    if (isV3 && v3Response) {
      const firstTab = v3Response.tabs.find((t) => t.items.length > 0);
      if (firstTab) setActiveTab(firstTab.tab_id);
      return;
    }
    if (isV2 && v2Response) {
      const firstCat = Object.keys(v2Response.results).find(
        (cat) => (v2Response.results[cat]?.length ?? 0) > 0,
      );
      if (firstCat) setActiveTab(firstCat);
      return;
    }
    setLocalResults(categoryResults);
    const firstCategory = CATEGORY_ORDER.find((category) =>
      categoryResults.some((result) => result.category === category && result.products.length > 0),
    );
    if (firstCategory) setActiveTab(firstCategory);
  }, [categoryResults, v2Response, v3Response, isV2, isV3]);

  useEffect(() => {
    const result = localResults.find((item) => item.category === activeTab);
    setEditedKeywords(result?.keywords ?? []);
  }, [activeTab, localResults]);

  const baseProducts = useMemo(() => {
    if (isV3 && v3Response) {
      const tab = v3Response.tabs.find((t) => t.tab_id === activeTab);
      return (tab?.items ?? []).map(v3ToProduct);
    }
    if (isV2 && v2Response) {
      return (v2Response.results[activeTab] ?? []).map(v2ToProduct);
    }
    return localResults.find((item) => item.category === activeTab)?.products ?? [];
  }, [activeTab, localResults, v2Response, v3Response, isV2, isV3]);

  const filteredProducts = useMemo(() => {
    let list = [...baseProducts];
    if (platformFilter !== 'all') {
      list = list.filter((product) => product.mallName.includes(platformFilter));
    }
    if (maxPrice !== null) {
      list = list.filter((product) => product.price <= maxPrice);
    }
    if (sortType === 'price_asc') {
      list.sort((a, b) => a.price - b.price);
    } else if (sortType === 'price_desc') {
      list.sort((a, b) => b.price - a.price);
    }
    return list;
  }, [baseProducts, platformFilter, maxPrice, sortType]);

  const totalCount = isV3 && v3Response
    ? v3Response.tabs.reduce((sum, t) => sum + t.items.length, 0)
    : isV2 && v2Response
    ? Object.values(v2Response.results).reduce((sum, items) => sum + items.length, 0)
    : localResults.reduce((sum, r) => sum + r.products.length, 0);

  const getTabCount = (cat: string): number => {
    if (isV3 && v3Response) return v3Response.tabs.find((t) => t.tab_id === cat)?.items.length ?? 0;
    if (isV2 && v2Response) return v2Response.results[cat]?.length ?? 0;
    return localResults.find((r) => r.category === cat)?.products.length ?? 0;
  };

  const getTabLabel = (cat: string): string => {
    if (isV3 && v3Response) {
      return v3Response.tabs.find((t) => t.tab_id === cat)?.label ?? getCategoryLabel(cat);
    }
    return getCategoryLabel(cat);
  };

  const handleLoadMore = async () => {
    if (!activeResult || isV2 || isV3) return;
    setIsLoadingMore(true);
    try {
      const nextOffset = offsets[activeTab] ?? 21;
      const result = await searchProducts(activeResult.query, [], nextOffset);
      if (result.products.length > 0) {
        setLocalResults((prev) =>
          prev.map((item) =>
            item.category === activeTab
              ? { ...item, products: [...item.products, ...result.products] }
              : item,
          ),
        );
        setOffsets((prev) => ({ ...prev, [activeTab]: nextOffset + 20 }));
      }
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleReSearch = async () => {
    if (!activeResult || editedKeywords.length === 0 || isV2 || isV3) return;
    setIsReSearching(true);
    try {
      const query = editedKeywords.slice(0, 3).join(' ');
      const result = await searchProducts(query, editedKeywords);
      setLocalResults((prev) =>
        prev.map((item) =>
          item.category === activeTab
            ? { ...item, keywords: editedKeywords, products: result.products, query }
            : item,
        ),
      );
      setOffsets((prev) => ({ ...prev, [activeTab]: 21 }));
      setShowKeywordEdit(false);
    } finally {
      setIsReSearching(false);
    }
  };

  const displayKeywords = isV3 && v3Response
    ? [v3Response.detected_attributes.mood ?? '', v3Response.detected_attributes.price_tier ?? ''].filter(Boolean)
    : isV2 && v2Response
    ? v2Response.style_context.mood_tags
    : (activeResult?.keywords ?? []);

  const handleShare = async () => {
    const labels = availableCategories.map(getTabLabel).join(', ');
    const text = `Cloi 검색 결과\n카테고리: ${labels}\n총 ${totalCount}개 상품`;
    if (navigator.share) {
      try { await navigator.share({ title: 'Cloi 검색 결과', text }); return; } catch { return; }
    }
    try {
      await navigator.clipboard.writeText(text);
      alert('검색 결과를 클립보드에 복사했어요.');
    } catch {
      alert('공유 가능한 환경이 아니에요.');
    }
  };

  const platformFilters: { value: PlatformFilter; label: string }[] = [
    { value: 'all', label: '전체' },
    { value: '무신사', label: '무신사' },
    { value: '에이블리', label: '에이블리' },
    { value: '지그재그', label: '지그재그' },
  ];

  const priceOptions = [
    { label: '전체 가격', value: null },
    { label: '3만원 이하', value: 30000 },
    { label: '5만원 이하', value: 50000 },
    { label: '10만원 이하', value: 100000 },
    { label: '20만원 이하', value: 200000 },
  ];

  const sortOptions: { value: SortType; label: string }[] = [
    { value: 'sim', label: '정확도순' },
    { value: 'price_asc', label: '낮은 가격순' },
    { value: 'price_desc', label: '높은 가격순' },
  ];

  return (
    <div className="app-shell" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '24px 20px 14px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <button type="button" className="icon-button" onClick={onBack}>
            <BackIcon />
          </button>
          <div className="serif-brand" style={{ fontSize: 22, fontWeight: 600, color: '#2c241f', letterSpacing: '-0.3px' }}>
            검색 결과
          </div>
          <button type="button" className="icon-button" onClick={handleShare}>
            <CartIcon />
          </button>
        </div>

        <div className="section-card fade-rise" style={{ padding: '10px 14px', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 38, height: 38, borderRadius: 8, background: '#ede5d8', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="22" viewBox="0 0 60 72" fill="none">
              <path d="M22 4C22 4 18 8 12 10L4 14L8 26L16 22V68H44V22L52 26L56 14L48 10C42 8 38 4 38 4C36 8 33 10 30 10C27 10 24 8 22 4Z" fill="#b6a89c" />
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 12, color: '#b6a89c' }}>업로드한 사진과 비슷한 상품</p>
            {isV3 && v3Response && (
              <p style={{ fontSize: 12, color: '#aa6d82', fontWeight: 500, marginTop: 1 }}>
                {v3Response.overall_style}
              </p>
            )}
            {isV2 && v2Response && (
              <p style={{ fontSize: 12, color: '#aa6d82', fontWeight: 500, marginTop: 1 }}>
                {v2Response.style_context.overall_style}
              </p>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <p style={{ fontSize: 13, color: '#8c7c71', fontWeight: 500 }}>
                총 {totalCount}개 발견
              </p>
              {isV3 && v3Response && (
                <>
                  <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: '#ede5d8', color: '#8c7c71' }}>
                    {v3Response.total_latency_ms}ms
                  </span>
                  {v3Response.cache_hit && (
                    <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: 'rgba(195, 132, 154, 0.15)', color: '#aa6d82' }}>
                      캐시
                    </span>
                  )}
                </>
              )}
              {isV2 && v2Response && (
                <>
                  <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: '#ede5d8', color: '#8c7c71' }}>
                    {v2Response.latency_ms}ms
                  </span>
                  {v2Response.cached && (
                    <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 999, background: 'rgba(195, 132, 154, 0.15)', color: '#aa6d82' }}>
                      캐시
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* 탭 네비게이션 */}
        <div className="capsule-row" style={{ paddingBottom: 12 }}>
          {availableCategories.map((category) => {
            const count = getTabCount(category);
            const isActive = activeTab === category;
            return (
              <button
                key={category}
                type="button"
                onClick={() => { setActiveTab(category); setShowFilter(false); }}
                style={{
                  flexShrink: 0,
                  minWidth: 80,
                  padding: '10px 14px',
                  borderRadius: 18,
                  border: `1px solid ${isActive ? 'rgba(170, 109, 130, 0.28)' : 'rgba(229, 216, 202, 0.9)'}`,
                  background: isActive
                    ? 'linear-gradient(145deg, #c3849a 0%, #aa6d82 100%)'
                    : 'rgba(255, 250, 244, 0.88)',
                  color: isActive ? '#fff' : '#2c241f',
                  boxShadow: isActive ? '0 12px 24px rgba(170, 109, 130, 0.22)' : 'none',
                }}
              >
                <span style={{ display: 'block', fontSize: 13, fontWeight: 600 }}>{getTabLabel(category)}</span>
                <span style={{ display: 'block', marginTop: 2, fontSize: 10, opacity: isActive ? 0.84 : 0.6 }}>
                  {count}개
                </span>
              </button>
            );
          })}
        </div>

        {/* 아이템 설명 (v3) */}
        {isV3 && activeV3Tab && (
          <p style={{ fontSize: 11, color: '#8c7c71', marginBottom: 8, padding: '0 2px', lineHeight: 1.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeV3Tab.description}
          </p>
        )}

        {/* 키워드/무드 태그 + 소팅 */}
        <div className="capsule-row" style={{ alignItems: 'center', paddingBottom: 4 }}>
          {displayKeywords.slice(0, 4).map((keyword) => (
            <span key={keyword} className="chip chip-active">#{keyword}</span>
          ))}
          {!isV2 && !isV3 && (
            <button
              type="button"
              className="chip"
              onClick={() => { setEditedKeywords(activeResult?.keywords ?? []); setShowKeywordEdit(true); }}
            >
              키워드 수정
            </button>
          )}
          <button
            type="button"
            className={`chip${showFilter ? ' chip-active' : ''}`}
            onClick={() => setShowFilter((prev) => !prev)}
          >
            필터 {showFilter ? '닫기' : '열기'}
          </button>
        </div>

        {showFilter && (
          <div className="section-card fade-rise" style={{ padding: 16, marginTop: 12 }}>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#8c7c71', marginBottom: 8 }}>쇼핑몰</p>
            <div className="capsule-row" style={{ marginBottom: 16 }}>
              {platformFilters.map((filter) => (
                <button key={filter.value} type="button" className={`chip${platformFilter === filter.value ? ' chip-active' : ''}`} onClick={() => setPlatformFilter(filter.value)}>
                  {filter.label}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#8c7c71', marginBottom: 8 }}>가격대</p>
            <div className="capsule-row" style={{ marginBottom: 16 }}>
              {priceOptions.map((option) => (
                <button key={option.label} type="button" className={`chip${maxPrice === option.value ? ' chip-active' : ''}`} onClick={() => setMaxPrice(option.value)}>
                  {option.label}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 12, fontWeight: 700, color: '#8c7c71', marginBottom: 8 }}>정렬</p>
            <div className="capsule-row">
              {sortOptions.map((option) => (
                <button key={option.value} type="button" className={`chip${sortType === option.value ? ' chip-active' : ''}`} onClick={() => setSortType(option.value)}>
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {showKeywordEdit && !isV2 && !isV3 && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(44, 36, 31, 0.28)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}>
          <div className="fade-rise" style={{ width: '100%', maxWidth: 480, margin: '0 auto', background: '#fff8f2', borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: '24px 20px 32px', borderTop: '1px solid rgba(229, 216, 202, 0.9)' }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, color: '#2c241f' }}>
              {getCategoryLabel(activeTab)} 키워드 조정
            </h3>
            <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.6, color: '#8c7c71' }}>
              마음에 들지 않는 키워드는 제거하고, 다시 검색해서 결과를 새로 받아올 수 있어요.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 18, marginBottom: 20 }}>
              {editedKeywords.map((keyword, index) => (
                <div key={`${keyword}-${index}`} className="chip chip-active" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span>#{keyword}</span>
                  <button type="button" onClick={() => setEditedKeywords((prev) => prev.filter((_, i) => i !== index))} style={{ fontSize: 14, lineHeight: 1 }}>×</button>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button type="button" className="btn-secondary" onClick={() => setShowKeywordEdit(false)} style={{ flex: 1 }}>닫기</button>
              <button type="button" className="btn-primary" onClick={handleReSearch} disabled={isReSearching || editedKeywords.length === 0} style={{ flex: 1.5 }}>
                {isReSearching ? '재검색 중...' : '다시 검색'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="screen-scroll" style={{ padding: '0 20px 20px' }}>
        {filteredProducts.length === 0 ? (
          <div className="section-card fade-rise" style={{ minHeight: 220, padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
            <p className="serif-brand" style={{ fontSize: 40, lineHeight: 1, color: '#c3849a' }}>No Match</p>
            <p style={{ marginTop: 10, fontSize: 14, lineHeight: 1.6, color: '#8c7c71' }}>
              현재 필터 조건과 맞는 상품이 없습니다. 필터를 완화하면 더 많은 결과를 볼 수 있어요.
            </p>
            <button type="button" className="chip" onClick={() => { setPlatformFilter('all'); setMaxPrice(null); setSortType('sim'); }} style={{ marginTop: 14 }}>
              필터 초기화
            </button>
          </div>
        ) : (
          <div className="fade-rise" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, paddingBottom: 16 }}>
            {filteredProducts.map((product, idx) => {
              const v3Item = isV3 && activeV3Tab
                ? activeV3Tab.items.find((p) => p.id === product.id)
                : null;

              const handleCardClick = () => {
                if (isV3 && v3Response) {
                  void recordClickV3(
                    v3Response.image_hash,
                    product.id,
                    activeTab,
                    idx,
                    v3Item?.match_score ?? 0,
                    product.title,
                    product.price,
                  );
                } else if (isV2 && v2Response) {
                  void recordClick(v2Response._imageHash, product.id, activeTab);
                }
              };

              const isFirst = idx === 0;

              return (
                <div
                  key={product.id}
                  onClick={handleCardClick}
                  style={{
                    position: 'relative',
                    borderRadius: isFirst ? 16 : undefined,
                    boxShadow: isFirst ? '0 0 0 2px #aa6d82' : undefined,
                  }}
                >
                  {/* 매칭 뱃지 (v3 only) */}
                  {v3Item && (
                    <div style={{
                      position: 'absolute',
                      top: 8,
                      left: 8,
                      zIndex: 2,
                      background: isFirst ? '#aa6d82' : 'rgba(44, 36, 31, 0.56)',
                      color: '#fff',
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: 8,
                    }}>
                      매칭 {Math.round(v3Item.match_score * 100)}%
                    </div>
                  )}
                  <ProductCard
                    product={product}
                    isFavorite={favoriteIds.has(product.id)}
                    onToggleFavorite={!isV2 && !isV3 ? onToggleFavorite : undefined}
                  />
                </div>
              );
            })}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 8 }}>
          {!isV2 && !isV3 && (
            <button type="button" className="btn-secondary" onClick={handleLoadMore} disabled={isLoadingMore}>
              {isLoadingMore ? '더 불러오는 중...' : `${getCategoryLabel(activeTab)} 더 보기`}
            </button>
          )}
          <button type="button" className="btn-primary" onClick={onBack}>
            다른 사진 찾기
          </button>
        </div>
      </div>
    </div>
  );
}
