import type { Product } from '../types';

interface ProductCardProps {
  product: Product;
}

const PLATFORM_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  무신사: { label: '무신사', color: '#fff', bg: '#000' },
  에이블리: { label: '에이블리', color: '#fff', bg: '#FF5A5F' },
  지그재그: { label: '지그재그', color: '#fff', bg: '#FF4081' },
};

function stripHtml(html: string) {
  return html.replace(/<[^>]*>/g, '');
}

function getPlatformBadge(mallName: string) {
  for (const key of Object.keys(PLATFORM_BADGE)) {
    if (mallName.includes(key)) return PLATFORM_BADGE[key];
  }
  return null;
}

export default function ProductCard({ product }: ProductCardProps) {
  const badge = getPlatformBadge(product.mallName);
  const title = stripHtml(product.title);

  const handleClick = () => {
    // 외부 쇼핑몰로 이동 (P0-7)
    window.open(product.link, '_blank', 'noopener,noreferrer');
  };

  return (
    <button
      onClick={handleClick}
      style={{
        width: '100%',
        background: '#fff',
        borderRadius: 12,
        overflow: 'hidden',
        boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
        textAlign: 'left',
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-2px)';
        (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 6px 20px rgba(0,0,0,0.12)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)';
        (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 2px 12px rgba(0,0,0,0.08)';
      }}
    >
      {/* 상품 이미지 */}
      <div style={{ position: 'relative', paddingTop: '100%', background: '#F2F4F6' }}>
        <img
          src={product.image}
          alt={title}
          style={{
            position: 'absolute',
            top: 0, left: 0,
            width: '100%', height: '100%',
            objectFit: 'cover',
          }}
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect fill="%23F2F4F6" width="100" height="100"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23C5CDD4" font-size="30">👗</text></svg>';
          }}
        />
        {/* 플랫폼 배지 */}
        {badge && (
          <span style={{
            position: 'absolute',
            top: 8, left: 8,
            background: badge.bg,
            color: badge.color,
            fontSize: 10,
            fontWeight: 700,
            padding: '3px 7px',
            borderRadius: 6,
          }}>
            {badge.label}
          </span>
        )}
      </div>

      {/* 상품 정보 */}
      <div style={{ padding: '10px 12px 12px' }}>
        <p style={{
          fontSize: 13,
          color: '#191F28',
          fontWeight: 500,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          lineHeight: 1.4,
          marginBottom: 6,
        }}>
          {title}
        </p>
        <p style={{ fontSize: 15, fontWeight: 700, color: '#191F28' }}>
          {product.price.toLocaleString()}원
        </p>
        <p style={{ fontSize: 11, color: '#778088', marginTop: 2 }}>
          {product.mallName}
        </p>
      </div>
    </button>
  );
}
