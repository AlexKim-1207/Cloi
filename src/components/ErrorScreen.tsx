import type { AppError } from '../types';

interface ErrorScreenProps {
  error: AppError;
  onRetry: () => void;
  onBack: () => void;
}

export default function ErrorScreen({ error, onRetry, onBack }: ErrorScreenProps) {
  const title =
    error.code === 'IMAGE_QUALITY'
      ? '이미지를 선명하게 읽지 못했어요'
      : error.code === 'NO_RESULTS'
        ? '비슷한 상품을 찾지 못했어요'
        : error.code === 'PRIVATE_ACCOUNT'
          ? '접근할 수 없는 계정이에요'
          : '일시적인 오류가 발생했어요';

  return (
    <div
      className="app-shell"
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div className="section-card fade-rise" style={{ width: '100%', padding: '32px 24px', textAlign: 'center' }}>
        <div
          style={{
            width: 76,
            height: 76,
            margin: '0 auto 18px',
            borderRadius: '50%',
            background: '#f5d7dc',
            color: '#c55b63',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 30,
            fontWeight: 700,
          }}
        >
          !
        </div>

        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#2c241f' }}>{title}</h2>
        <p style={{ marginTop: 10, fontSize: 14, lineHeight: 1.7, color: '#8c7c71' }}>{error.message}</p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 24 }}>
          {error.retryable && (
            <button type="button" className="btn-primary" onClick={onRetry}>
              다시 시도하기
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={onBack}>
            처음으로 돌아가기
          </button>
        </div>
      </div>
    </div>
  );
}
