import { useState } from 'react';
import HomePage from './pages/HomePage';
import LoadingPage from './pages/LoadingPage';
import ResultPage from './pages/ResultPage';
import ErrorScreen from './components/ErrorScreen';
import type { AppState, LoadingStep, Product, AppError } from './types';
import './styles/global.css';

export default function App() {
  const [appState, setAppState] = useState<AppState>('home');
  const [loadingStep, setLoadingStep] = useState<LoadingStep>('analyzing');
  const [products, setProducts] = useState<Product[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [error, setError] = useState<AppError | null>(null);

  // 마지막 분석 요청 저장 (재시도용)
  const [lastRetry, setLastRetry] = useState<(() => void) | null>(null);

  const handleLoadingStart = (step: LoadingStep) => {
    setLoadingStep(step);
    setAppState('loading');
  };

  const handleResult = (prods: Product[], kws: string[]) => {
    setProducts(prods);
    setKeywords(kws);
    setAppState('result');
  };

  const handleError = (err: AppError) => {
    setError(err);
    setAppState('error');
  };

  const handleBack = () => {
    setAppState('home');
    setError(null);
  };

  const handleRetry = () => {
    if (lastRetry) {
      lastRetry();
    } else {
      setAppState('home');
    }
  };

  const handleSearchMore = () => {
    // 현재 키워드로 재검색 (순서 섞어서 다양성 확보)
    const shuffled = [...keywords].sort(() => Math.random() - 0.5);
    setKeywords(shuffled);
    // 실제로는 offset 파라미터를 변경해 다음 페이지 로드
    // 현재는 홈으로 돌아가도록
    setAppState('home');
  };

  return (
    <div style={{ height: '100vh', overflow: 'hidden', background: '#fff' }}>
      {appState === 'home' && (
        <HomePage
          onLoadingStart={handleLoadingStart}
          onResult={handleResult}
          onError={handleError}
        />
      )}
      {appState === 'loading' && (
        <LoadingPage step={loadingStep} />
      )}
      {appState === 'result' && (
        <ResultPage
          products={products}
          keywords={keywords}
          onBack={handleBack}
          onSearchMore={handleSearchMore}
        />
      )}
      {appState === 'error' && error && (
        <ErrorScreen
          error={error}
          onRetry={handleRetry}
          onBack={handleBack}
        />
      )}
    </div>
  );
}
