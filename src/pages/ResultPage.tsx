import ProductCard from '../components/ProductCard';
import type { Product } from '../types';

interface ResultPageProps {
  products: Product[];
  keywords: string[];
  onBack: () => void;
  onSearchMore: () => void;
}

export default function ResultPage({ products, keywords, onBack, onSearchMore }: ResultPageProps) {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 헤더 */}
      <div style={{
        padding: '20px 20px 16px',
        borderBottom: '1px solid #F2F4F6',
        background: '#fff',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <button
            onClick={onBack}
            style={{
              width: 36, height: 36,
              borderRadius: '50%',
              background: '#F2F4F6',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16,
            }}
          >
            ←
          </button>
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: '#191F28' }}>
              비슷한 상품 {products.length}개
            </h1>
            <p style={{ fontSize: 12, color: '#778088', marginTop: 2 }}>
              탭하면 쇼핑몰로 이동해요
            </p>
          </div>
        </div>

        {/* 키워드 태그 */}
        {keywords.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {keywords.slice(0, 6).map((kw) => (
              <span key={kw} style={{
                fontSize: 12,
                color: '#0064FF',
                background: '#E8F0FF',
                padding: '4px 10px',
                borderRadius: 20,
                fontWeight: 500,
              }}>
                #{kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 상품 그리드 */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px 16px',
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 12,
          marginBottom: 16,
        }}>
          {products.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>

        {/* 더 찾기 버튼 (P0: "비슷한 옷 더 보기") */}
        <button
          className="btn-secondary"
          onClick={onSearchMore}
          style={{ marginBottom: 8 }}
        >
          🔄 이 옷과 비슷한 옷 더 보기
        </button>

        <button
          className="btn-primary"
          onClick={onBack}
        >
          다른 옷 찾기
        </button>
      </div>
    </div>
  );
}
