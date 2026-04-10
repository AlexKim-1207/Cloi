import { useEffect, useState } from 'react';

interface ClipboardBannerProps {
  onDetected: (url: string) => void;
}

export default function ClipboardBanner({ onDetected }: ClipboardBannerProps) {
  const [detectedUrl, setDetectedUrl] = useState<string | null>(null);

  useEffect(() => {
    const checkClipboard = async () => {
      try {
        if (!navigator.clipboard?.readText) return;
        const text = await navigator.clipboard.readText();
        if (text && text.includes('instagram.com')) {
          setDetectedUrl(text.trim());
        }
      } catch {
        // 클립보드 권한 거부 시 무시
      }
    };

    // 앱 포그라운드 진입 시 클립보드 감지 (P0-3)
    checkClipboard();
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') checkClipboard();
    });
  }, []);

  if (!detectedUrl) return null;

  return (
    <div style={{
      margin: '0 0 16px',
      padding: '14px 16px',
      background: '#E8F0FF',
      borderRadius: 12,
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }}>
      <span style={{ fontSize: 20 }}>📋</span>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: '#0064FF', marginBottom: 2 }}>
          인스타그램 링크 감지됨
        </p>
        <p style={{
          fontSize: 12,
          color: '#778088',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: 180,
        }}>
          {detectedUrl}
        </p>
      </div>
      <button
        onClick={() => { onDetected(detectedUrl); setDetectedUrl(null); }}
        style={{
          background: '#0064FF',
          color: '#fff',
          fontSize: 13,
          fontWeight: 600,
          padding: '8px 14px',
          borderRadius: 8,
          whiteSpace: 'nowrap',
        }}
      >
        분석하기
      </button>
    </div>
  );
}
