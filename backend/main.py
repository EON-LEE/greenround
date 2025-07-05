from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import threading
import logging

# 라우터들
from routers import common, swingclip
from core.common.utils import cleanup_temp_files, cleanup_old_files

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    logger.info("🚀 Golf 3D Analyzer API 시작 중...")
    
    # 시작 시 정리 작업
    cleanup_temp_files()
    
    # 백그라운드 정리 작업 시작
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    logger.info("✅ Greenround Backend API 시작 완료!")
    yield
    
    # 종료 시 정리 작업
    logger.info("🛑 Greenround Backend API 종료 중...")
    cleanup_temp_files()
    logger.info("✅ Greenround Backend API 종료 완료!")

def periodic_cleanup():
    """주기적인 파일 정리"""
    import time
    while True:
        try:
            time.sleep(3600)  # 1시간마다
            logger.info("🧹 주기적 파일 정리 시작...")
            cleanup_old_files(max_age_hours=24)
            logger.info("✅ 주기적 파일 정리 완료!")
        except Exception as e:
            logger.error(f"❌ 파일 정리 중 오류: {e}")

# FastAPI 앱 생성
app = FastAPI(
    title="Greenround Backend API",
    description="""
    ## 🏌️ Greenround Backend - Microservice Architecture v2.0
    
    골프 스윙 분석을 위한 마이크로서비스 API입니다.
    
    ### 🎯 주요 서비스
    
    #### 📤 공통 서비스 (Common)
    - **파일 업로드**: 비디오 파일 업로드 및 검증
    - **상태 조회**: 작업 진행 상황 실시간 모니터링
    - **결과 다운로드**: GCS 기반 파일 다운로드 및 스트리밍
    - **시스템 정보**: API 상태 및 서비스 정보 확인
    
    #### 🏌️ SwingClip 서비스
    - **하이라이트 영상**: 3단계 슬로우모션 하이라이트 생성
    - **스윙 시퀀스**: 7단계 스윙 분석 이미지 합성
    - **볼 트래킹**: 골프공 궤적 추적 및 시각화
    - **볼 분석**: 데이터 분석 (영상 생성 없이)
    
    #### 📄 Scorecard 서비스 (향후 확장)
    - **OCR 인식**: 스코어카드 텍스트 인식 (개발 예정)
    
    ### 🔧 기술 스택
    - **Backend**: FastAPI, Python 3.9+
    - **AI/ML**: MediaPipe, OpenCV, PIL
    - **Storage**: Google Cloud Storage
    - **Architecture**: Microservice with Router-based separation
    
    ### 📊 API 사용법
    1. **업로드**: `/api/upload`로 비디오 파일 업로드
    2. **분석 요청**: 각 서비스 엔드포인트로 분석 요청
    3. **상태 확인**: `/api/status/{task_id}`로 진행 상황 확인
    4. **결과 다운로드**: 완료 후 결과 파일 다운로드
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발용, 실제 배포시에는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(common.router, tags=["📤 Common"])
app.include_router(swingclip.router, tags=["🏌️ SwingClip"])

# 루트 엔드포인트
@app.get("/", tags=["🏠 Root"])
async def root():
    """API 루트 - 서비스 개요"""
    return {
        "service": "Greenround Backend API",
        "version": "2.0.0",
        "architecture": "microservice",
        "status": "healthy",
        "message": "🏌️ Welcome to Greenround Backend API v2.0!",
        "services": {
            "common": {
                "description": "파일 업로드, 상태 조회, 다운로드 등 공통 기능",
                "endpoints": ["/api/upload", "/api/status", "/api/health", "/api/info"]
            },
            "swingclip": {
                "description": "골프 스윙 분석 및 영상 생성 서비스",
                "endpoints": [
                    "/api/swingclip/highlight-video",
                    "/api/swingclip/swing-sequence", 
                    "/api/swingclip/ball-tracking",
                    "/api/swingclip/ball-analysis"
                ]
            },
            "scorecard": {
                "description": "스코어카드 OCR 서비스 (향후 확장 예정)",
                "status": "coming_soon"
            }
        },
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc"
        },
        "links": {
            "health_check": "/api/health",
            "system_info": "/api/info",
            "swingclip_health": "/api/swingclip/health",
            "swingclip_info": "/api/swingclip/info"
        }
    }

# 추가 메타데이터 엔드포인트
@app.get("/version", tags=["🏠 Root"])
async def get_version():
    """API 버전 정보"""
    return {
        "version": "2.0.0",
        "architecture": "microservice",
        "release_date": "2024-06-21",
        "features": {
            "microservice_architecture": True,
            "router_based_separation": True,
            "lazy_loading_engines": True,
            "gcs_integration": True,
            "real_time_progress": True
        },
        "changelog": {
            "v2.0.0": [
                "마이크로서비스 아키텍처로 리팩토링",
                "라우터 기반 서비스 분리",
                "싱글톤 패턴으로 엔진 최적화",
                "향상된 에러 처리 및 로깅",
                "API 문서 개선"
            ],
            "v1.1.0": [
                "GCS Signed URL 지원",
                "다운로드 기능 개선",
                "볼 분석 API 추가"
            ]
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info",
        access_log=True
    ) 