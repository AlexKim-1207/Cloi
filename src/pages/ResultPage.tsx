import { useEffect, useMemo, useState } from 'react';
import ProductCard from '../components/ProductCard';
import { searchProducts } from '../services/api';
import type { CategorySearchResult, FashionCategory, Product } from '../types';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../types';

interface ResultPageProps {
  categoryResults: CategorySearchResult[];
  favoriteIds: Set<string>;
  onBack: () => void;
  onToggleFavorite: (product: Product) => void;
}

type SortType = 'sim' | 'price_asc' | 'price_desc';
type PlatformFilter = 'all' | '무신사' | '에이블리' | '지그재그';

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2c241f" strokeWidth="2">
      <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2c241f" strokeWidth="1.8">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="M8.59 13.51l6.83 3.98M15.41 6.51 8.59 10.49" strokeLinecap="round" />
    </svg>
  );
}

export default function ResultPage({
  categoryResults,
  favoriteIds,
  onBack,
  onToggleFavorite,
}: ResultPageProps) {
  const availableCategories = useMemo(
    () =>
      CATEGORY_ORDER.filter((category) =>
        categoryResults.some((result) => result.category === category && result.products.length > 0),
      ),
    [categoryResults],
  );

  const [activeTab, setActiveTab] = useState<FashionCategory>(availableCategories[0] ?? 'top');
  const [sortType, setSortType] = useState<SortType>('sim');
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>('all');
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const [showFilter, setShowFilter] = useState(false);
  const [showKeywordEdit, setShowKeywordEdit] = useState(false);
  const [isReSearching, setIsReSearching] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [localResults, setLocalResults] = useState<CategorySearchResult[]>(categoryResults);
  const [offsets, setOffsets] = useState<Partial<Record<FashionCategory, number>>>({});
  const activeResult = localResults.find((result) => result.category === activeTab);
  const [editedKeywords, setEditedKeywords] = useState<string[]>(activeResult?.keywords ?? []);

  useEffect(() => {
    setLocalResults(categoryResults);
    const firstCategory = CATEGORY_ORDER.find((category) =>
      categoryResults.some((result) => result.category === category && result.products.length > 0),
    );
    if (firstCategory) setActiveTab(firstCategory);
  }, [categoryResults]);

  useEffect(() => {
    const result = localResults.find((item) => item.category === activeTab);
    setEditedKeywords(result?.keywords ?? []);
  }, [activeTab, localResults]);

  const filteredProducts = useMemo(() => {
    const result = localResults.find((item) => item.category === activeTab);
    if (!result) return [];

    let list = [...result.products];
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
  }, [activeTab, localResults, maxPrice, platformFilter, sortType]);

  const handleLoadMore = async () => {
    if (!activeResult) return;
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
    if (!activeResult || editedKeywords.length === 0) return;
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

  const handleShare = async () => {
    const labels = availableCategories.map((category) => CATEGORY_LABELS[category]).join(', ');
    const total = categoryResults.reduce((sum, item) => sum + item.products.length, 0);
    const text = `Cloi 검색 결과\n카테고리: ${labels}\n총 ${total}개 상품`;

    if (navigator.share) {
      try {
        await navigator.share({ title: 'Cloi 검색 결과', text });
        return;
      } catch {
        return;
      }
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
          <div style={{ textAlign: 'center' }}>
            <div className="serif-brand" style={{ fontSize: 22, lineHeight: 1, fontWeight: 600 }}>
              Cloi
            </div>
            <p style={{ marginTop: 4, fontSize: 12, color: '#8c7c71' }}>검색 결과</p>
          </div>
          <button type="button" className="icon-button" onClick={handleShare}>
            <ShareIcon />
          </button>
        </div>

        <div className="section-card fade-rise" style={{ padding: 16, marginBottom: 14 }}>
          <p style={{ fontSize: 12, color: '#b6a89c', marginBottom: 6 }}>업로드한 이미지와 닮은 결과</p>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: '#2c241f' }}>
            {CATEGORY_LABELS[activeTab] ?? ''} 상품 {filteredProducts.length}개
          </h1>
          <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.6, color: '#8c7c71' }}>
            조건에 맞는 상품을 모았어요. 카드를 누르면 바로 쇼핑몰로 이동합니다.
          </p>
        </div>

        <div className="capsule-row" style={{ paddingBottom: 12 }}>
          {availableCategories.map((category) => {
            const count = localResults.find((result) => result.category === category)?.products.length ?? 0;
            const isActive = activeTab === category;

            return (
              <button
                key={category}
                type="button"
                onClick={() => {
                  setActiveTab(category);
                  setShowFilter(false);
                }}
                style={{
                  flexShrink: 0,
                  minWidth: 88,
                  padding: '12px 16px',
                  borderRadius: 18,
                  border: `1px solid ${isActive ? 'rgba(170, 109, 130, 0.28)' : 'rgba(229, 216, 202, 0.9)'}`,
                  background: isActive
                    ? 'linear-gradient(145deg, #c3849a 0%, #aa6d82 100%)'
                    : 'rgba(255, 250, 244, 0.88)',
                  color: isActive ? '#fff' : '#2c241f',
                  boxShadow: isActive ? '0 12px 24px rgba(170, 109, 130, 0.22)' : 'none',
                }}
              >
                <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{CATEGORY_LABELS[category]}</span>
                <span style={{ display: 'block', marginTop: 3, fontSize: 11, opacity: isActive ? 0.84 : 0.6 }}>
                  {count}개
                </span>
              </button>
            );
          })}
        </div>

        <div className="capsule-row" style={{ alignItems: 'center', paddingBottom: 4 }}>
          {(activeResult?.keywords ?? []).slice(0, 5).map((keyword) => (
            <span key={keyword} className="chip chip-active">
              #{keyword}
            </span>
          ))}
          <button
            type="button"
            className="chip"
            onClick={() => {
              setEditedKeywords(activeResult?.keywords ?? []);
              setShowKeywordEdit(true);
            }}
          >
            키워드 수정
          </button>
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
                <button
                  key={filter.value}
                  type="button"
                  className={`chip${platformFilter === filter.value ? ' chip-active' : ''}`}
                  onClick={() => setPlatformFilter(filter.value)}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <p style={{ fontSize: 12, fontWeight: 700, color: '#8c7c71', marginBottom: 8 }}>가격대</p>
            <div className="capsule-row" style={{ marginBottom: 16 }}>
              {priceOptions.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  className={`chip${maxPrice === option.value ? ' chip-active' : ''}`}
                  onClick={() => setMaxPrice(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <p style={{ fontSize: 12, fontWeight: 700, color: '#8c7c71', marginBottom: 8 }}>정렬</p>
            <div className="capsule-row">
              {sortOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`chip${sortType === option.value ? ' chip-active' : ''}`}
                  onClick={() => setSortType(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {showKeywordEdit && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(44, 36, 31, 0.28)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'flex-end',
          }}
        >
          <div
            className="fade-rise"
            style={{
              width: '100%',
              maxWidth: 480,
              margin: '0 auto',
              background: '#fff8f2',
              borderTopLeftRadius: 28,
              borderTopRightRadius: 28,
              padding: '24px 20px 32px',
              borderTop: '1px solid rgba(229, 216, 202, 0.9)',
            }}
          >
            <h3 style={{ fontSize: 18, fontWeight: 600, color: '#2c241f' }}>
              {CATEGORY_LABELS[activeTab]} 키워드 조정
            </h3>
            <p style={{ marginTop: 6, fontSize: 13, lineHeight: 1.6, color: '#8c7c71' }}>
              마음에 들지 않는 키워드는 제거하고, 다시 검색해서 결과를 새로 받아올 수 있어요.
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 18, marginBottom: 20 }}>
              {editedKeywords.map((keyword, index) => (
                <div
                  key={`${keyword}-${index}`}
                  className="chip chip-active"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <span>#{keyword}</span>
                  <button
                    type="button"
                    onClick={() => setEditedKeywords((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                    style={{ fontSize: 14, lineHeight: 1 }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 10 }}>
              <button type="button" className="btn-secondary" onClick={() => setShowKeywordEdit(false)} style={{ flex: 1 }}>
                닫기
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleReSearch}
                disabled={isReSearching || editedKeywords.length === 0}
                style={{ flex: 1.5 }}
              >
                {isReSearching ? '재검색 중...' : '다시 검색'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="screen-scroll" style={{ padding: '0 20px 20px' }}>
        {filteredProducts.length === 0 ? (
          <div
            className="section-card fade-rise"
            style={{
              minHeight: 220,
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
            }}
          >
            <p className="serif-brand" style={{ fontSize: 40, lineHeight: 1, color: '#c3849a' }}>
              No Match
            </p>
            <p style={{ marginTop: 10, fontSize: 14, lineHeight: 1.6, color: '#8c7c71' }}>
              현재 필터 조건과 맞는 상품이 없습니다. 필터를 완화하면 더 많은 결과를 볼 수 있어요.
            </p>
            <button
              type="button"
              className="chip"
              onClick={() => {
                setPlatformFilter('all');
                setMaxPrice(null);
                setSortType('sim');
              }}
              style={{ marginTop: 14 }}
            >
              필터 초기화
            </button>
          </div>
        ) : (
          <div
            className="fade-rise"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gap: 12,
              paddingBottom: 16,
            }}
          >
            {filteredProducts.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                isFavorite={favoriteIds.has(product.id)}
                onToggleFavorite={onToggleFavorite}
              />
            ))}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 8 }}>
          <button type="button" className="btn-secondary" onClick={handleLoadMore} disabled={isLoadingMore}>
            {isLoadingMore ? '더 불러오는 중...' : `${CATEGORY_LABELS[activeTab]} 더 보기`}
          </button>
          <button type="button" className="btn-primary" onClick={onBack}>
            다른 사진 찾기
          </button>
        </div>
      </div>
    </div>
  );
}
