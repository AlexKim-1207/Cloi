import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import analyzeRouter from './routes/analyze';
import analyzeUrlRouter from './routes/analyzeUrl';
import searchRouter from './routes/search';

const app = express();
const PORT = Number(process.env.PORT) || 3001;

// ─── 보안 미들웨어 ────────────────────────────────────────────────────────────
// 개발 환경에서만 CORS 허용 (프로덕션: 같은 오리진에서 Vite 프록시로 처리)
const allowedOrigins = process.env.NODE_ENV === 'production'
  ? [] // 프로덕션: 동일 오리진(Vite 빌드 배포) → CORS 불필요
  : ['http://localhost:5173', 'http://localhost:3000'];

app.use(cors({
  origin: allowedOrigins,
  credentials: false,
}));

// 요청 크기 제한 (이미지 base64: 최대 15MB)
app.use(express.json({ limit: '15mb' }));
app.use(express.urlencoded({ extended: true, limit: '15mb' }));

// API 키 존재 여부만 로그 (값은 절대 노출하지 않음)
const maskedKey = (key: string | undefined) =>
  key ? `${key.slice(0, 4)}****${key.slice(-4)}` : '❌ 미설정';

console.log('');
console.log('🔐 API 키 상태:');
console.log(`  Gemini:      ${maskedKey(process.env.GEMINI_API_KEY)}`);
console.log(`  Naver ID:    ${maskedKey(process.env.NAVER_CLIENT_ID)}`);
console.log(`  Naver Secret:${maskedKey(process.env.NAVER_CLIENT_SECRET)}`);
console.log('');

// ─── 라우터 ──────────────────────────────────────────────────────────────────
app.use('/api/analyze', analyzeRouter);
app.use('/api/analyze-url', analyzeUrlRouter);
app.use('/api/search', searchRouter);

// 헬스체크
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    env: process.env.NODE_ENV,
    apis: {
      gemini: !!process.env.GEMINI_API_KEY,
      naver: !!(process.env.NAVER_CLIENT_ID && process.env.NAVER_CLIENT_SECRET),
    },
  });
});

// 404 핸들러
app.use((_req, res) => {
  res.status(404).json({ message: '요청한 API를 찾을 수 없어요.' });
});

// 전역 에러 핸들러
app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('[server error]', err.message);
  res.status(500).json({ message: '서버 오류가 발생했어요.' });
});

app.listen(PORT, () => {
  console.log(`🚀 웨어고 서버 실행 중: http://localhost:${PORT}`);
  console.log(`   환경: ${process.env.NODE_ENV || 'development'}`);
  console.log('');
});
