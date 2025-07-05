#!/bin/bash

# =============================================================================
# Greenround v2.0 - 새 백엔드 실행 스크립트
# =============================================================================

set -e

# 색상 코드 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# 기본 설정
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8000"
DEFAULT_WORKERS="1"

HOST=${1:-$DEFAULT_HOST}
PORT=${2:-$DEFAULT_PORT}
WORKERS=${3:-$DEFAULT_WORKERS}

echo "🏌️ Greenround API v2.0 - Microservice Architecture"
echo "============================================================"

# 환경 확인
log_info "환경 확인 중..."

if [ ! -d "venv" ]; then
    log_warning "가상환경이 없습니다. 생성하시겠습니까? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        python -m venv venv
        log_success "가상환경이 생성되었습니다."
    fi
fi

# 가상환경 활성화
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    log_success "가상환경이 활성화되었습니다."
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
    log_success "가상환경이 활성화되었습니다. (Windows)"
else
    log_warning "가상환경을 찾을 수 없습니다. 시스템 Python을 사용합니다."
fi

# 의존성 설치 확인
log_info "의존성 확인 중..."
if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
    log_info "필요한 패키지를 설치합니다..."
    pip install -r requirements.txt
    log_success "의존성 설치 완료!"
fi

# 백엔드 폴더 확인
if [ ! -d "backend" ]; then
    log_error "backend 폴더를 찾을 수 없습니다!"
    exit 1
fi

# 환경 변수 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# GCS 인증 파일 확인
if [ -f "gcs-credentials.json" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/gcs-credentials.json"
    log_success "GCS 인증 파일이 설정되었습니다."
else
    log_warning "GCS 인증 파일(gcs-credentials.json)이 없습니다. 로컬 파일 시스템을 사용합니다."
fi

# 서버 실행
log_info "새 백엔드 서버 시작 중..."
log_info "주소: http://$HOST:$PORT"
log_info "워커 수: $WORKERS"
log_info "API 문서: http://$HOST:$PORT/docs"
log_info ""
log_success "🚀 서버가 시작되었습니다!"

cd backend && python -m uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --reload \
    --log-level info \
    --access-log 