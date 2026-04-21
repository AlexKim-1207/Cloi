import { useState } from 'react';
import HomePage from './pages/HomePage';
import LoadingPage from './pages/LoadingPage';
import ResultPage from './pages/ResultPage';
import FavoritesPage from './pages/FavoritesPage';
import ErrorScreen from './components/ErrorScreen';
import type { AppState, LoadingStep, Product, AppError, HistoryItem, CategorySearchResult } from './types';
import { CATEGORY_LABELS as CAT_LABELS } from './types';
import { useLocalStorage } from './hooks/useLocalStorage';
import './styles/global.css';

export default function App() {
  const [appState, setAppState] = useState<AppState>('home');
  const [loadingStep, setLoadingStep] = useState<LoadingStep>('analyzing');
  const [categoryResults, setCategoryResults] = useState<CategorySearchResult[]>([]);
  const [error, setError] = useState<AppError | null>(null);
  const [lastRetry, setLastRetry] = useState<(() => void) | null>(null);

  const [favorites, setFavorites] = useLocalStorage<Product[]>('wherego_favorites', []);
  const [history, setHistory] = useLocalStorage<HistoryItem[]>('wherego_history', []);

  const handleLoadingStart = (step: LoadingStep) => {
    setLoadingStep(step);
    setAppState('loading');
  };

  const handleSetRetry = (fn: () => void) => {
    setLastRetry(() => fn);
  };

  const handleResult = (catResults: CategorySearchResult[], description: string) => {
    setCategoryResults(catResults);

    // 히스토리용 데이터: 카테고리 레이블을 키워드로, 첫 상품들을 썸네일로 사용
    const allProducts = catResults.flatMap((r) => r.products.slice(0, 2));
    const displayKeywords = catResults.map((r) => CAT_LABELS[r.category]).filter(Boolean);
    const firstQuery = catResults[0]?.query || '';

    const newItem: HistoryItem = {
      id: Date.now().toString(),
      timestamp: Date.now(),
      keywords: displayKeywords,
      searchQuery: firstQuery,
      products: allProducts.slice(0, 6),
      categoryResults: catResults,
    };
    setHistory((prev) =>
      [newItem, ...prev.filter((h) => h.searchQuery !== firstQuery)].slice(0, 5),
    );

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

  const handleToggleFavorite = (product: Product) => {
    setFavorites((prev) => {
      const exists = prev.some((p) => p.id === product.id);
      return exists ? prev.filter((p) => p.id !== product.id) : [...prev, product];
    });
  };

  const handleHistorySelect = (item: HistoryItem) => {
    if (item.categoryResults && item.categoryResults.length > 0) {
      setCategoryResults(item.categoryResults);
    } else {
      // 구형 히스토리 (categoryResults 없음): 상품을 첫 카테고리로 래핑
      setCategoryResults([{
        category: 'top',
        keywords: item.keywords,
        products: item.products,
        total: item.products.length,
        query: item.searchQuery,
      }]);
    }
    setAppState('result');
  };

  const favoriteIds = new Set(favorites.map((p) => p.id));

  return (
    <div style={{ height: '100vh', overflow: 'hidden' }}>
      {appState === 'home' && (
        <HomePage
          onLoadingStart={handleLoadingStart}
          onResult={handleResult}
          onError={handleError}
          onSetRetry={handleSetRetry}
          history={history}
          onHistorySelect={handleHistorySelect}
          onNavigateFavorites={() => setAppState('favorites')}
          favoritesCount={favorites.length}
        />
      )}
      {appState === 'loading' && <LoadingPage step={loadingStep} />}
      {appState === 'result' && (
        <ResultPage
          categoryResults={categoryResults}
          favoriteIds={favoriteIds}
          onBack={handleBack}
          onToggleFavorite={handleToggleFavorite}
        />
      )}
      {appState === 'error' && error && (
        <ErrorScreen error={error} onRetry={handleRetry} onBack={handleBack} />
      )}
      {appState === 'favorites' && (
        <FavoritesPage
          favorites={favorites}
          onBack={handleBack}
          onToggleFavorite={handleToggleFavorite}
        />
      )}
    </div>
  );
}
