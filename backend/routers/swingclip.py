from fastapi import APIRouter, HTTPException, BackgroundTasks
import logging
from pathlib import Path

# 로컬 모듈들
from models.schemas import (
    HighlightVideoRequest, HighlightVideoResponse, 
    SwingSequenceRequest, SwingSequenceResponse,
    BallTrackingRequest, BallTrackingResponse,
    BallAnalysisRequest, BallAnalysisResponse,
    TaskStatus, ErrorResponse
)
from core.common.utils import (
    generate_task_id, get_file_path, update_task_status, generate_predictable_urls
)
from core.swingclip.highlight_engine import HighlightEngine
from core.swingclip.sequence_composer import SequenceComposer
from core.swingclip.ball_tracking_engine import BallTrackingEngine
from core.swingclip.pose.sequence_pose_analyzer import SequencePoseAnalyzer

logger = logging.getLogger(__name__)

# SwingClip 서비스 라우터 생성
router = APIRouter(
    prefix="/api/swingclip",
    tags=["swingclip"],
    responses={404: {"model": ErrorResponse}},
)

# 글로벌 인스턴스들 (싱글톤 패턴)
_highlight_engine = None
_sequence_analyzer = None
_sequence_composer = None
_ball_tracking_engine = None

def get_highlight_engine():
    """HighlightEngine 싱글톤 인스턴스 반환"""
    global _highlight_engine
    if _highlight_engine is None:
        _highlight_engine = HighlightEngine()
    return _highlight_engine

def get_sequence_analyzer():
    """SequencePoseAnalyzer 싱글톤 인스턴스 반환"""
    global _sequence_analyzer
    if _sequence_analyzer is None:
        _sequence_analyzer = SequencePoseAnalyzer()
    return _sequence_analyzer

def get_sequence_composer():
    """SequenceComposer 싱글톤 인스턴스 반환"""
    global _sequence_composer
    if _sequence_composer is None:
        _sequence_composer = SequenceComposer(get_sequence_analyzer())
    return _sequence_composer

def get_ball_tracking_engine():
    """BallTrackingEngine 싱글톤 인스턴스 반환"""
    global _ball_tracking_engine
    if _ball_tracking_engine is None:
        _ball_tracking_engine = BallTrackingEngine()
    return _ball_tracking_engine

# 1. 하이라이트 영상 생성 API
@router.post("/highlight-video", response_model=HighlightVideoResponse)
async def create_highlight_video(request: HighlightVideoRequest, background_tasks: BackgroundTasks):
    """3단계 하이라이트 영상 생성"""
    try:
        # 입력 파일 확인
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        # 태스크 생성
        task_id = generate_task_id("highlight")
        update_task_status(task_id, "pending", 0, "하이라이트 생성 대기 중")
        
        # 예측 가능한 URL들 생성
        urls = generate_predictable_urls(task_id, "highlights")
        
        # 백그라운드 태스크 실행
        highlight_engine = get_highlight_engine()
        background_tasks.add_task(
            highlight_engine.create_highlight_video,
            request.file_id, task_id, request.total_duration, request.slow_factor
        )
        
        return HighlightVideoResponse(
            task_id=task_id, 
            status=TaskStatus.PENDING,
            download_url=urls["download"],
            stream_url=urls["stream"],
            estimated_time=30
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"하이라이트 생성 실패: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"하이라이트 생성 실패: {str(e)}")

# 2. 스윙 시퀀스 이미지 생성 API
@router.post("/swing-sequence", response_model=SwingSequenceResponse)
async def create_swing_sequence(request: SwingSequenceRequest, background_tasks: BackgroundTasks):
    """7단계 스윙 시퀀스 이미지 생성 (심플 버전)"""
    try:
        # 입력 파일 확인
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        # 태스크 생성
        task_id = generate_task_id("sequence")
        update_task_status(task_id, "pending", 0, "시퀀스 이미지 생성 대기 중")
        
        # 예측 가능한 URL들 생성
        urls = generate_predictable_urls(task_id, "sequences")
        
        # 백그라운드 태스크 실행 - SequenceComposer 사용
        composer = get_sequence_composer()
        background_tasks.add_task(
            composer.create_sequence_image,
            request.file_id, task_id
        )
        
        return SwingSequenceResponse(
            task_id=task_id, 
            status=TaskStatus.PENDING,
            download_url=urls["download"],
            stream_url=urls["stream"],
            estimated_time=20
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"시퀀스 이미지 생성 실패: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"시퀀스 이미지 생성 실패: {str(e)}")

# 3. 볼 트래킹 영상 생성 API
@router.post("/ball-tracking", response_model=BallTrackingResponse)
async def create_ball_tracking_video(request: BallTrackingRequest, background_tasks: BackgroundTasks):
    """골프공 트래킹 영상 생성 (스윙 분석 연동)"""
    try:
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        task_id = generate_task_id("balltrack")
        update_task_status(task_id, "pending", 0, "볼 트래킹 생성 대기 중")
        
        # BallTrackingEngine의 전용 함수를 백그라운드 태스크로 실행
        ball_tracking_engine = get_ball_tracking_engine()
        background_tasks.add_task(
            ball_tracking_engine.create_ball_tracking_video,
            request.file_id, task_id
        )
        
        return BallTrackingResponse(
            task_id=task_id, 
            status=TaskStatus.PENDING,
            estimated_time=45
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"볼 트래킹 생성 실패: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"볼 트래킹 생성 실패: {str(e)}")

# 4. 볼 분석 API (영상 생성 없이 분석만)
@router.post("/ball-analysis", response_model=BallAnalysisResponse)
async def create_ball_analysis(request: BallAnalysisRequest, background_tasks: BackgroundTasks):
    """골프공 분석 (영상 생성 없이 분석 결과만 반환)"""
    try:
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        task_id = generate_task_id("ballanalysis")
        update_task_status(task_id, "pending", 0, "볼 분석 대기 중")
        
        # BallTrackingEngine의 분석 전용 함수를 백그라운드 태스크로 실행
        ball_tracking_engine = get_ball_tracking_engine()
        background_tasks.add_task(
            ball_tracking_engine.get_ball_analysis_only,
            request.file_id, task_id
        )
        
        return BallAnalysisResponse(
            task_id=task_id, 
            status=TaskStatus.PENDING,
            estimated_time=60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"볼 분석 실패: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"볼 분석 실패: {str(e)}")

# 5. SwingClip 서비스 상태 확인
@router.get("/health")
async def swingclip_health_check():
    """SwingClip 서비스 상태 확인"""
    try:
        highlight_engine = get_highlight_engine()
        sequence_analyzer = get_sequence_analyzer()
        
        return {
            "service": "swingclip",
            "status": "healthy",
            "version": "2.0.0",
            "features": {
                "highlight_video": highlight_engine.highlight_analyzer.pose is not None,
                "swing_sequence": sequence_analyzer.pose is not None,
                "ball_tracking": True,
                "ball_analysis": True
            },
            "engines": {
                "highlight_engine": "loaded" if _highlight_engine else "lazy",
                "sequence_analyzer": "loaded" if _sequence_analyzer else "lazy",
                "ball_tracking_engine": "loaded" if _ball_tracking_engine else "lazy"
            }
        }
    except Exception as e:
        logger.error(f"SwingClip 헬스체크 실패: {str(e)}", exc_info=True)
        return {
            "service": "swingclip",
            "status": "unhealthy",
            "error": str(e)
        }

# 6. SwingClip 서비스 정보
@router.get("/info")
async def swingclip_info():
    """SwingClip 서비스 정보"""
    return {
        "service": "swingclip",
        "version": "2.0.0",
        "description": "Golf swing analysis service with highlight generation, sequence composition, and ball tracking",
        "features": {
            "highlight_video": {
                "description": "Generate highlight videos with slow motion effects",
                "endpoint": "/api/swingclip/highlight-video",
                "estimated_time": "30 seconds",
                "parameters": ["file_id", "total_duration", "slow_factor"]
            },
            "swing_sequence": {
                "description": "Create 7-step swing sequence images",
                "endpoint": "/api/swingclip/swing-sequence", 
                "estimated_time": "20 seconds",
                "parameters": ["file_id"]
            },
            "ball_tracking": {
                "description": "Track golf ball with trajectory visualization",
                "endpoint": "/api/swingclip/ball-tracking",
                "estimated_time": "45 seconds",
                "parameters": ["file_id", "show_trajectory", "show_speed", "show_distance"]
            },
            "ball_analysis": {
                "description": "Analyze ball data without video generation",
                "endpoint": "/api/swingclip/ball-analysis",
                "estimated_time": "60 seconds",
                "parameters": ["file_id", "analysis_type"]
            }
        }
    } 