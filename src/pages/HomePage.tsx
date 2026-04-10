import { useState } from 'react';
import ImageUploader from '../components/ImageUploader';
import ClipboardBanner from '../components/ClipboardBanner';
import { analyzeImage, analyzeImageUrl, searchProducts } from '../services/api';
import type { Product, LoadingStep, AppError } from '../types';

interface HomePageProps {
  onLoadingStart: (step: LoadingStep) => void;
  onResult: (products: Product[], keywords: string[]) => void;
  onError: (error: AppError) => void;
}

export default function HomePage({ onLoadingStart, onResult, onError }: HomePageProps) {
  const [instagramUrl, setInstagramUrl] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageData, setImageData] = useState<{ base64: string; mimeType: string } | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const handleImageSelected = (base64: string, mimeType: string, preview: string) => {
    setImagePreview(preview);
    setImageData({ base64, mimeType });
    setInstagramUrl(''); // 이미지 선택 시 URL 초기화
  };

  const runAnalysis = async (
    getKeywords: () => Promise<{ keywords: string[]; searchQuery: string }>,
  ) => {
    setIsAnalyzing(true);
    try {
      onLoadingStart('analyzing');
      const analysis = await getKeywords();

      onLoadingStart('searching');
      const result = await searchProducts(analysis.searchQuery, analysis.keywords);

      if (result.products.length === 0) {
        onError({
          message: '입력한 이미지와 비슷한 상품을 찾지 못했어요. 다른 이미지로 시도해 보세요.',
          code: 'NO_RESULTS',
          retryable: true,
        });
      } else {
        onResult(result.products, analysis.keywords);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '알 수 없는 오류가 발생했어요';
      onError({ message, retryable: true });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleImageAnalyze = () => {
    if (!imageData) return;
    runAnalysis(() => analyzeImage(imageData.base64, imageData.mimeType));
  };

  const handleUrlAnalyze = () => {
    const trimmed = instagramUrl.trim();
    if (!trimmed) return;

    if (!trimmed.includes('instagram.com')) {
      onError({
        message: 'Instagram 링크를 입력해 주세요. (예: https://www.instagram.com/p/...)',
        code: 'INVALID_URL',
        retryable: false,
      });
      return;
    }

    runAnalysis(() => analyzeImageUrl(trimmed));
  };

  const handleClipboardDetected = (url: string) => {
    setInstagramUrl(url);
  };

  const canAnalyzeImage = !!imageData && !isAnalyzing;
  const canAnalyzeUrl = instagramUrl.trim().length > 0 && !isAnalyzing;

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '24px 20px' }}>
      {/* 헤더 */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: '#191F28', letterSpacing: '-0.5px' }}>
          웨어고
        </h1>
        <p style={{ fontSize: 15, color: '#778088', marginTop: 6 }}>
          옷 사진을 올리면 비슷한 상품을 찾아드려요
        </p>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: 20 }}>
        {/* 클립보드 배너 (P0-3) */}
        <ClipboardBanner onDetected={handleClipboardDetected} />

        {/* 이미지 업로드 섹션 (P0-1) */}
        <section style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#191F28', marginBottom: 12 }}>
            📸 사진으로 찾기
          </h2>

          {imagePreview ? (
            <div style={{ position: 'relative', marginBottom: 14 }}>
              <img
                src={imagePreview}
                alt="선택된 이미지"
                style={{
                  width: '100%',
                  height: 220,
                  objectFit: 'cover',
                  borderRadius: 16,
                  border: '2px solid #0064FF',
                }}
              />
              <button
                onClick={() => { setImagePreview(null); setImageData(null); }}
                style={{
                  position: 'absolute',
                  top: 10, right: 10,
                  width: 28, height: 28,
                  borderRadius: '50%',
                  background: 'rgba(0,0,0,0.5)',
                  color: '#fff',
                  fontSize: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                ×
              </button>
            </div>
          ) : (
            <ImageUploader onImageSelected={handleImageSelected} />
          )}

          <button
            className="btn-primary"
            onClick={handleImageAnalyze}
            disabled={!canAnalyzeImage}
            style={{ marginTop: 12 }}
          >
            {isAnalyzing ? '분석 중...' : '이 옷 찾기'}
          </button>
        </section>

        {/* 구분선 */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 24,
          color: '#C5CDD4',
          fontSize: 13,
        }}>
          <div style={{ flex: 1, height: 1, background: '#F2F4F6' }} />
          <span>또는</span>
          <div style={{ flex: 1, height: 1, background: '#F2F4F6' }} />
        </div>

        {/* 인스타그램 링크 입력 (P0-2) */}
        <section>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: '#191F28', marginBottom: 12 }}>
            🔗 인스타그램 링크로 찾기
          </h2>
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            padding: '14px 16px',
            background: '#F9FAFB',
            borderRadius: 12,
            marginBottom: 12,
          }}>
            <p style={{ fontSize: 12, color: '#778088' }}>
              ⚠️ 공개 게시물 링크만 지원해요. 비공개 계정은 사진 업로드를 이용해 주세요.
            </p>
          </div>
          <input
            type="url"
            placeholder="https://www.instagram.com/p/..."
            value={instagramUrl}
            onChange={(e) => setInstagramUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && canAnalyzeUrl && handleUrlAnalyze()}
            style={{
              width: '100%',
              height: 50,
              padding: '0 16px',
              border: '1.5px solid #E5E8EB',
              borderRadius: 10,
              fontSize: 14,
              color: '#191F28',
              outline: 'none',
              marginBottom: 12,
              background: '#fff',
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = '#0064FF')}
            onBlur={(e) => (e.currentTarget.style.borderColor = '#E5E8EB')}
          />
          <button
            className="btn-primary"
            onClick={handleUrlAnalyze}
            disabled={!canAnalyzeUrl}
          >
            {isAnalyzing ? '분석 중...' : '링크로 찾기'}
          </button>
        </section>
      </div>
    </div>
  );
}
