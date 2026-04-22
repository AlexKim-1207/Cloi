#!/usr/bin/env bash
# fashion-search 개발 환경 셋업 스크립트
# Usage: bash scripts/setup_env.sh

set -e

PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

echo "=== Fashion Search 환경 셋업 ==="

# 1. Python 버전 확인
echo "[1/5] Python 버전 확인..."
$PYTHON --version

# 2. 가상환경 생성
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/5] 가상환경 생성: $VENV_DIR"
    $PYTHON -m venv "$VENV_DIR"
else
    echo "[2/5] 가상환경 이미 존재: $VENV_DIR"
fi

# 3. 활성화 안내
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    ACTIVATE_CMD="$VENV_DIR/Scripts/activate"
else
    ACTIVATE_CMD="source $VENV_DIR/bin/activate"
fi
echo "[3/5] 가상환경 활성화: $ACTIVATE_CMD"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate" 2>/dev/null || source "$VENV_DIR/Scripts/activate"

# 4. 의존성 설치
echo "[4/5] 패키지 설치 (requirements.txt)..."
pip install --upgrade pip -q
pip install -r requirements.txt

# 5. .env 파일 생성
if [ ! -f ".env" ]; then
    echo "[5/5] .env 파일 생성..."
    cp .env.example .env
    echo "  .env 파일을 열어 GOOGLE_API_KEY를 입력하세요."
else
    echo "[5/5] .env 파일 이미 존재"
fi

echo ""
echo "=== 셋업 완료 ==="
echo "다음 명령으로 서버 실행:"
echo "  $ACTIVATE_CMD"
echo "  uvicorn apps.api.main:app --reload --port 8000"
