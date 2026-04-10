import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
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
    sourcemap: false, // 프로덕션에서 소스맵 비활성화 (보안)
  },
});
