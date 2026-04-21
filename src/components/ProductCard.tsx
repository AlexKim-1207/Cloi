import type { Product } from '../types';

interface ProductCardProps {
  product: Product;
  isFavorite?: boolean;
  onToggleFavorite?: (product: Product) => void;
}

const PLATFORM_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  무신사: { label: 'MUSINSA', color: '#fff', bg: '#1f1916' },
  에이블리: { label: 'ABLY', color: '#fff', bg: '#d26c90' },
  지그재그: { label: 'ZIGZAG', color: '#fff', bg: '#c3849a' },
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

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill={filled ? '#c3849a' : 'none'}
      stroke={filled ? '#c3849a' : '#b6a89c'}
      strokeWidth="1.8"
    >
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

export default function ProductCard({
  product,
  isFavorite = false,
  onToggleFavorite,
}: ProductCardProps) {
  const badge = getPlatformBadge(product.mallName);
  const title = stripHtml(product.title);

  const handleClick = () => {
    window.open(product.link, '_blank', 'noopener,noreferrer');
  };

  const handleFavorite = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onToggleFavorite?.(product);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="fade-rise"
      style={{
        width: '100%',
        textAlign: 'left',
        background: 'rgba(255, 250, 244, 0.92)',
        borderRadius: 20,
        overflow: 'hidden',
        border: '1px solid rgba(229, 216, 202, 0.9)',
        boxShadow: '0 12px 28px rgba(92, 68, 55, 0.08)',
      }}
    >
      <div style={{ position: 'relative', aspectRatio: '3 / 4', background: '#efe5d8' }}>
        <img
          src={product.image}
          alt={title}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={(event) => {
            event.currentTarget.style.display = 'none';
          }}
        />

        {badge && (
          <span
            style={{
              position: 'absolute',
              top: 12,
              left: 12,
              padding: '5px 8px',
              borderRadius: 999,
              background: badge.bg,
              color: badge.color,
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.06em',
            }}
          >
            {badge.label}
          </span>
        )}

        {onToggleFavorite && (
          <button
            type="button"
            onClick={handleFavorite}
            title={isFavorite ? '찜 해제' : '찜 추가'}
            style={{
              position: 'absolute',
              top: 10,
              right: 10,
              width: 34,
              height: 34,
              borderRadius: '50%',
              background: 'rgba(255, 250, 244, 0.9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 18px rgba(71, 53, 45, 0.12)',
            }}
          >
            <HeartIcon filled={isFavorite} />
          </button>
        )}
      </div>

      <div style={{ padding: '12px 13px 14px' }}>
        <p
          style={{
            fontSize: 12,
            color: '#8c7c71',
            marginBottom: 4,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {product.mallName}
        </p>
        <p
          style={{
            minHeight: 40,
            fontSize: 13,
            lineHeight: 1.45,
            color: '#2c241f',
            fontWeight: 500,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {title}
        </p>
        <p style={{ marginTop: 8, fontSize: 16, fontWeight: 700, color: '#2c241f' }}>
          {product.price.toLocaleString()}원
        </p>
      </div>
    </button>
  );
}
