import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // 프로덕션 빌드 시 API_BASE를 빈 문자열로 고정 (동일 도메인 Pages Functions)
  define: mode === 'production'
    ? { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') }
    : {},
  server: {
    port: 5173,
    proxy: {
      // 개발 환경에서 API 요청을 백엔드로 프록시 (CORS 우회 + 키 보호)
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
}));
