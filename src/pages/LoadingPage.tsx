import { useEffect, useState } from 'react';
import type { LoadingStep } from '../types';

interface LoadingPageProps {
  step: LoadingStep;
}

const STEPS: { key: LoadingStep; label: string; detail: string }[] = [
  { key: 'analyzing', label: '사진 분위기 분석 중', detail: '실루엣과 카테고리를 정리하고 있어요.' },
  { key: 'searching', label: '비슷한 상품을 찾는 중', detail: '쇼핑몰 결과를 모아서 정렬하고 있어요.' },
];

export default function LoadingPage({ step }: LoadingPageProps) {
  const [dots, setDots] = useState('');

  useEffect(() => {
    const timer = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : `${prev}.`));
    }, 420);
    return () => clearInterval(timer);
  }, []);

  const currentIndex = STEPS.findIndex((item) => item.key === step);
  const current = STEPS[currentIndex];

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
      <div
        className="section-card fade-rise"
        style={{
          width: '100%',
          padding: '34px 26px',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            width: 104,
            height: 104,
            margin: '0 auto 24px',
            borderRadius: '50%',
            background: 'radial-gradient(circle at 30% 30%, #f7e6ec 0%, #f1d9e3 58%, #edcfdc 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 18px 32px rgba(170, 109, 130, 0.18)',
            animation: 'cloiPulse 1.6s ease-in-out infinite',
          }}
        >
          <div className="serif-brand" style={{ fontSize: 34, color: '#aa6d82', fontWeight: 600 }}>
            C
          </div>
        </div>

        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#2c241f' }}>
          {current.label}
          {dots}
        </h2>
        <p style={{ marginTop: 10, fontSize: 14, lineHeight: 1.7, color: '#8c7c71' }}>{current.detail}</p>

        <div style={{ display: 'flex', justifyContent: 'center', gap: 10, marginTop: 26 }}>
          {STEPS.map((item, index) => (
            <div
              key={item.key}
              style={{
                width: index <= currentIndex ? 28 : 10,
                height: 10,
                borderRadius: 999,
                background: index <= currentIndex ? '#c3849a' : '#eadfd4',
                transition: 'all 0.28s ease',
              }}
            />
          ))}
        </div>

        <style>{`
          @keyframes cloiPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.06); }
          }
        `}</style>
      </div>
    </div>
  );
}
