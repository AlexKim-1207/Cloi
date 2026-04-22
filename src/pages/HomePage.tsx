import { useRef, useState } from 'react';
import ImageUploader from '../components/ImageUploader';
import { analyzeImage, searchByCategories } from '../services/api';
import type {
  AppError,
  CategoryAnalysisResult,
  CategorySearchResult,
  HistoryItem,
  LoadingStep,
} from '../types';

interface HomePageProps {
  onLoadingStart: (step: LoadingStep) => void;
  onResult: (categoryResults: CategorySearchResult[], description: string) => void;
  onError: (error: AppError) => void;
  onSetRetry: (fn: () => void) => void;
  history: HistoryItem[];
  onHistorySelect: (item: HistoryItem) => void;
  onNavigateFavorites: () => void;
  favoritesCount: number;
}

function HeartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#c3849a" strokeWidth="1.8">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="8" height="12" viewBox="0 0 8 12" fill="none" stroke="#b6a89c" strokeWidth="1.8">
      <path d="M1 1l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function HomePage({
  onLoadingStart,
  onResult,
  onError,
  onSetRetry,
  history,
  onHistorySelect,
  onNavigateFavorites,
  favoritesCount,
}: HomePageProps) {
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageData, setImageData] = useState<{ base64: string; mimeType: string } | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const isAnalyzingRef = useRef(false);

  const handleImageSelected = (base64: string, mimeType: string, preview: string) => {
    setImagePreview(preview);
    setImageData({ base64, mimeType });
  };

  const runAnalysis = async (getAnalysis: () => Promise<CategoryAnalysisResult>) => {
    if (isAnalyzingRef.current) return;
    isAnalyzingRef.current = true;
    onSetRetry(() => runAnalysis(getAnalysis));

    setIsAnalyzing(true);
    try {
      onLoadingStart('analyzing');
      const analysis = await getAnalysis();

      onLoadingStart('searching');
      const categoryResults = await searchByCategories(analysis.categories);

      if (categoryResults.length === 0) {
        onError({
          message: '입력한 이미지와 비슷한 상품을 찾지 못했어요. 다른 이미지를 다시 시도해 주세요.',
          code: 'NO_RESULTS',
          retryable: true,
        });
      } else {
        onResult(categoryResults, analysis.description);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '알 수 없는 오류가 발생했어요.';
      onError({ message, retryable: true });
    } finally {
      isAnalyzingRef.current = false;
      setIsAnalyzing(false);
    }
  };

  const handleImageAnalyze = () => {
    if (!imageData) return;
    runAnalysis(() => analyzeImage(imageData.base64, imageData.mimeType));
  };

  const canAnalyzeImage = Boolean(imageData) && !isAnalyzing;

  return (
    <div
      className="app-shell"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '28px 20px 20px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 className="serif-brand" style={{ fontSize: 40, lineHeight: 1, fontWeight: 600, letterSpacing: '-0.03em' }}>
            Cloi
          </h1>
          <p style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6, color: '#8c7c71' }}>
            나에게 딱맞는 최저가 옷 찾기
          </p>
        </div>

        <button type="button" className="icon-button" onClick={onNavigateFavorites} style={{ position: 'relative' }}>
          <HeartIcon />
          {favoritesCount > 0 && (
            <span
              style={{
                position: 'absolute',
                top: -4,
                right: -4,
                minWidth: 18,
                height: 18,
                borderRadius: 999,
                background: '#aa6d82',
                color: '#fff',
                padding: '0 5px',
                fontSize: 10,
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {favoritesCount > 9 ? '9+' : favoritesCount}
            </span>
          )}
        </button>
      </div>

      <div className="screen-scroll">
        <section className="section-card fade-rise" style={{ padding: 18, marginBottom: 22 }}>
          <div style={{ marginBottom: 14 }}>
            <p style={{ fontSize: 12, color: '#aa6d82', fontWeight: 700, letterSpacing: '0.08em' }}>PHOTO SEARCH</p>
          </div>

          {imagePreview ? (
            <div className="fade-rise">
              <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 22, marginBottom: 14 }}>
                <img
                  src={imagePreview}
                  alt="선택한 이미지"
                  style={{ width: '100%', height: 256, objectFit: 'cover' }}
                />
                <button
                  type="button"
                  onClick={() => {
                    setImagePreview(null);
                    setImageData(null);
                  }}
                  style={{
                    position: 'absolute',
                    top: 12,
                    right: 12,
                    width: 34,
                    height: 34,
                    borderRadius: '50%',
                    background: 'rgba(44, 36, 31, 0.46)',
                    color: '#fff',
                    fontSize: 18,
                  }}
                >
                  ×
                </button>
              </div>
              <div
                style={{
                  marginBottom: 14,
                  padding: '12px 14px',
                  borderRadius: 18,
                  background: 'rgba(241, 217, 227, 0.55)',
                  color: '#8c5e71',
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              >
                이미지가 준비됐어요.
              </div>
            </div>
          ) : (
            <ImageUploader onImageSelected={handleImageSelected} />
          )}

          <button
            type="button"
            className="btn-primary"
            onClick={handleImageAnalyze}
            disabled={!canAnalyzeImage}
            style={{ marginTop: 14 }}
          >
            {isAnalyzing ? '분석 중...' : '이 옷 찾기'}
          </button>
        </section>

        {history.length > 0 && (
          <section className="fade-rise">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div>
                <p style={{ fontSize: 12, color: '#aa6d82', fontWeight: 700, letterSpacing: '0.08em' }}>RECENT</p>
                <h2 style={{ marginTop: 4, fontSize: 17, fontWeight: 600 }}>최근 탐색</h2>
              </div>
              <span style={{ fontSize: 12, color: '#8c7c71' }}>{history.length}개</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 8 }}>
              {history.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onHistorySelect(item)}
                  className="section-card"
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: 12,
                    textAlign: 'left',
                  }}
                >
                  <div
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: 16,
                      overflow: 'hidden',
                      background: '#efe5d8',
                      flexShrink: 0,
                    }}
                  >
                    {item.products[0]?.image ? (
                      <img
                        src={item.products[0].image}
                        alt="검색 기록 썸네일"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : null}
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p
                      style={{
                        fontSize: 14,
                        fontWeight: 500,
                        color: '#2c241f',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.keywords.slice(0, 4).join(' · ')}
                    </p>
                    <p style={{ marginTop: 4, fontSize: 12, color: '#8c7c71' }}>
                      상품 {item.products.length}개 · {formatTime(item.timestamp)}
                    </p>
                  </div>

                  <ArrowIcon />
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function formatTime(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const min = Math.floor(diff / 60000);

  if (min < 1) return '방금 전';
  if (min < 60) return `${min}분 전`;

  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;

  return `${Math.floor(hour / 24)}일 전`;
}
