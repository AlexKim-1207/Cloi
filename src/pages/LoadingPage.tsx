import { useEffect, useState } from 'react';
import type { LoadingStep } from '../types';

interface LoadingPageProps {
  step: LoadingStep;
}

const STEPS: { key: LoadingStep; label: string; emoji: string }[] = [
  { key: 'analyzing', label: '옷 분석 중...', emoji: '🔍' },
  { key: 'searching', label: '상품 찾는 중...', emoji: '🛍️' },
];

export default function LoadingPage({ step }: LoadingPageProps) {
  const [dots, setDots] = useState('');

  useEffect(() => {
    const timer = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
    }, 400);
    return () => clearInterval(timer);
  }, []);

  const currentIndex = STEPS.findIndex((s) => s.key === step);
  const current = STEPS[currentIndex];

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '0 24px',
    }}>
      {/* 메인 애니메이션 */}
      <div style={{
        width: 100,
        height: 100,
        borderRadius: '50%',
        background: '#E8F0FF',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 48,
        marginBottom: 32,
        animation: 'pulse 1.5s ease-in-out infinite',
      }}>
        {current.emoji}
      </div>

      <h2 style={{ fontSize: 22, fontWeight: 700, color: '#191F28', marginBottom: 8 }}>
        {current.label}{dots}
      </h2>
      <p style={{ fontSize: 15, color: '#778088' }}>
        잠깐만요, 금방 찾아드릴게요
      </p>

      {/* 스텝 인디케이터 */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginTop: 48,
        alignItems: 'center',
      }}>
        {STEPS.map((s, i) => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: i <= currentIndex ? 24 : 8,
              height: 8,
              borderRadius: 4,
              background: i <= currentIndex ? '#0064FF' : '#E5E8EB',
              transition: 'all 0.3s ease',
            }} />
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 16 }}>
        {STEPS.map((s, i) => (
          <p key={s.key} style={{
            fontSize: 12,
            color: i <= currentIndex ? '#0064FF' : '#C5CDD4',
            fontWeight: i === currentIndex ? 700 : 400,
          }}>
            {s.label.replace('...', '')}
          </p>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.08); }
        }
      `}</style>
    </div>
  );
}
