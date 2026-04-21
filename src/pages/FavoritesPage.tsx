import ProductCard from '../components/ProductCard';
import type { Product } from '../types';

interface FavoritesPageProps {
  favorites: Product[];
  onBack: () => void;
  onToggleFavorite: (product: Product) => void;
}

function BackIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2c241f" strokeWidth="2">
      <path d="M19 12H5M12 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function FavoritesPage({ favorites, onBack, onToggleFavorite }: FavoritesPageProps) {
  const favoriteIds = new Set(favorites.map((product) => product.id));

  return (
    <div className="app-shell" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '24px 20px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <button type="button" className="icon-button" onClick={onBack}>
            <BackIcon />
          </button>
          <div>
            <div className="serif-brand" style={{ fontSize: 24, lineHeight: 1, fontWeight: 600 }}>
              Favorites
            </div>
            <p style={{ marginTop: 4, fontSize: 13, color: '#8c7c71' }}>마음에 담아둔 상품 {favorites.length}개</p>
          </div>
        </div>
      </div>

      <div className="screen-scroll" style={{ padding: '0 20px 20px' }}>
        {favorites.length === 0 ? (
          <div
            className="section-card fade-rise"
            style={{
              minHeight: '62vh',
              padding: 28,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: 78,
                height: 78,
                borderRadius: '50%',
                background: '#f1d9e3',
                color: '#aa6d82',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 34,
              }}
            >
              ♡
            </div>
            <h2 style={{ marginTop: 18, fontSize: 20, fontWeight: 600, color: '#2c241f' }}>아직 찜한 상품이 없어요</h2>
            <p style={{ marginTop: 8, fontSize: 14, lineHeight: 1.7, color: '#8c7c71' }}>
              결과 화면에서 하트를 누르면 여기에서 다시 모아볼 수 있습니다.
            </p>
            <button type="button" className="btn-primary" onClick={onBack} style={{ width: 180, marginTop: 18 }}>
              상품 찾으러 가기
            </button>
          </div>
        ) : (
          <div
            className="fade-rise"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gap: 12,
            }}
          >
            {favorites.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                isFavorite={favoriteIds.has(product.id)}
                onToggleFavorite={onToggleFavorite}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
