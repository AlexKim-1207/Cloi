import { build } from 'vite';
import react from '@vitejs/plugin-react';

console.log('Building for production...');
try {
  await build({
    configFile: false,
    plugins: [react()],
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') },
    build: {
      outDir: 'dist',
      sourcemap: false,
    }
  });
  console.log('BUILD SUCCESS');
} catch(e) {
  console.error('BUILD FAILED:', e.message?.slice(0, 500));
  process.exit(1);
}
