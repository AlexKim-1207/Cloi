import dotenv from 'dotenv';
import path from 'path';
// .env는 프로젝트 루트(server/의 상위)에 위치
dotenv.config({ path: path.resolve(__dirname, '../../.env') });
import express from 'express';
import cors from 'cors';
import analyzeRouter from './routes/analyze';
import analyzeUrlRouter from './routes/analyzeUrl';
import searchRouter from './routes/search';

const app = express();
const PORT = Number(process.env.PORT) || 3001;

// ─── API 키 시작 시 검증 ─────────────────────────────────────────────────────
const missingKeys: string[] = [];
if (!process.env.GEMINI_API_KEY || process.env.GEMINI_API_KEY === 'your_gemini_api_key_here') {
  missingKeys.push('GEMINI_API_KEY');
}
if (!process.env.NAVER_CLIENT_ID || process.env.NAVER_CLIENT_ID === 'your_naver_client_id_here') {
  missingKeys.push('NAVER_CLIENT_ID');
}
if (!process.env.NAVER_CLIENT_SECRET || process.env.NAVER_CLIENT_SECRET === 'your_naver_client_secret_here') {
  missingKeys.push('NAVER_CLIENT_SECRET');
}

// API 키 마스킹 로그 (값은 절대 노출하지 않음)
const maskedKey = (key: string | undefined) =>
  key && !key.startsWith('your_') ? `${key.slice(0, 4)}****${key.slice(-4)}` : '❌ 미설정';

console.log('');
console.log('🔐 API 키 상태:');
console.log(`  Gemini:       ${maskedKey(process.env.GEMINI_API_KEY)}`);
console.log(`  Naver ID:     ${maskedKey(process.env.NAVER_CLIENT_ID)}`);
console.log(`  Naver Secret: ${maskedKey(process.env.NAVER_CLIENT_SECRET)}`);
if (missingKeys.length > 0) {
  console.log(`\n⚠️  미설정 키: ${missingKeys.join(', ')}`);
  console.log('   .env.example을 복사해 .env를 만들고 실제 값을 입력하세요.\n');
}
console.log('');

// ─── 보안 미들웨어 ────────────────────────────────────────────────────────────
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

// ─── 간단한 Rate Limiting (외부 패키지 없이 인메모리) ──────────────────────────
const requestCounts = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 60;      // 분당 최대 요청 수
const RATE_WINDOW = 60000;  // 1분 (ms)

app.use('/api', (req, res, next) => {
  const ip = req.ip || req.socket.remoteAddress || 'unknown';
  const now = Date.now();
  const entry = requestCounts.get(ip);

  if (!entry || now > entry.resetAt) {
    requestCounts.set(ip, { count: 1, resetAt: now + RATE_WINDOW });
    return next();
  }

  entry.count += 1;
  if (entry.count > RATE_LIMIT) {
    return res.status(429).json({
      message: '요청이 너무 많아요. 잠시 후 다시 시도해 주세요.',
      code: 'RATE_LIMIT_EXCEEDED',
    });
  }
  return next();
});

// 인메모리 맵 주기적 정리 (메모리 누수 방지)
setInterval(() => {
  const now = Date.now();
  for (const [ip, entry] of requestCounts.entries()) {
    if (now > entry.resetAt) requestCounts.delete(ip);
  }
}, RATE_WINDOW);

// ─── 라우터 ──────────────────────────────────────────────────────────────────
app.use('/api/analyze', analyzeRouter);
app.use('/api/analyze-url', analyzeUrlRouter);
app.use('/api/search', searchRouter);

// 헬스체크 (env 필드 제거 - 불필요한 정보 노출 방지)
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    apis: {
      gemini: !!process.env.GEMINI_API_KEY && !process.env.GEMINI_API_KEY.startsWith('your_'),
      naver: !!(process.env.NAVER_CLIENT_ID && process.env.NAVER_CLIENT_SECRET)
        && !process.env.NAVER_CLIENT_ID.startsWith('your_'),
    },
  });
});

// 404 핸들러
app.use((_req, res) => {
  res.status(404).json({ message: '요청한 API를 찾을 수 없어요.' });
});

// 전역 에러 핸들러 (413, 400 등 HTTP 에러 코드 올바르게 전달)
app.use((err: Error & { status?: number; statusCode?: number; type?: string }, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  const status = err.status || err.statusCode || 500;

  // Payload Too Large
  if (status === 413 || err.type === 'entity.too.large') {
    return res.status(413).json({ message: '파일이 너무 커요. 15MB 이하로 업로드해 주세요.' });
  }

  // JSON 파싱 오류
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ message: '잘못된 요청 형식이에요.' });
  }

  console.error('[server error]', err.message);
  return res.status(500).json({ message: '서버 오류가 발생했어요.' });
});

app.listen(PORT, () => {
  console.log(`🚀 웨어고 서버 실행 중: http://localhost:${PORT}`);
  console.log('');
});
