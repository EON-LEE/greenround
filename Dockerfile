# ==============================================================================
# Multi-stage build for optimized Greenround Backend
# ==============================================================================

# 1. 의존성 빌드 스테이지
FROM python:3.9-slim as deps

# 빌드 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt를 먼저 복사하여 캐시 활용
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --user -r /tmp/requirements.txt

# 2. 최종 런타임 스테이지
FROM python:3.9-slim

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 빌드된 Python 패키지들 복사
COPY --from=deps /root/.local /root/.local

# 소스 코드 복사 (새 백엔드 구조)
COPY backend/ backend/
# COPY demo/ demo/
COPY .env .env
COPY requirements.txt .
# Google Cloud 서비스 계정 키 파일 복사
COPY gcs-credentials.json /app/service-account-key.json

# 환경 변수 설정 (GCS 인증 및 Python Path)
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-key.json \
    PYTHONPATH=/app/backend

# 포트 노출
EXPOSE 8000

# 실행 명령어 (새 백엔드 main.py 사용)
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"] 