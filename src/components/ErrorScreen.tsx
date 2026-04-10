import type { AppError } from '../types';

interface ErrorScreenProps {
  error: AppError;
  onRetry: () => void;
  onBack: () => void;
}

export default function ErrorScreen({ error, onRetry, onBack }: ErrorScreenProps) {
  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '0 24px',
      textAlign: 'center',
    }}>
      <span style={{ fontSize: 64, marginBottom: 24 }}>😢</span>

      <h2 style={{ fontSize: 20, fontWeight: 700, color: '#191F28', marginBottom: 8 }}>
        {error.code === 'IMAGE_QUALITY' ? '이미지를 분석하기 어려워요'
          : error.code === 'NO_RESULTS' ? '비슷한 상품을 찾지 못했어요'
          : error.code === 'PRIVATE_ACCOUNT' ? '비공개 계정이에요'
          : '일시적인 오류가 발생했어요'}
      </h2>

      <p style={{ fontSize: 15, color: '#778088', lineHeight: 1.6, marginBottom: 32 }}>
        {error.message}
      </p>

      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {error.retryable && (
          <button className="btn-primary" onClick={onRetry}>
            다시 시도하기
          </button>
        )}
        <button className="btn-secondary" onClick={onBack}>
          처음으로 돌아가기
        </button>
      </div>
    </div>
  );
}
