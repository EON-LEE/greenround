from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import threading
from pathlib import Path

# 로컬 모듈들
from .models.schemas import *
from .core.utils import (
    generate_file_id, generate_task_id, get_file_path, 
    validate_video_file, update_task_status, get_task_status,
    cleanup_temp_files, cleanup_old_files, UPLOADS_DIR,
    generate_predictable_urls
)
from .core.highlight_engine import HighlightEngine
from .core.sequence_composer import SequenceComposer
from .core.ball_tracking_engine import BallTrackingEngine
from .core.pose.sequence_pose_analyzer import SequencePoseAnalyzer
import logging

logger = logging.getLogger(__name__)

# 글로벌 인스턴스들
highlight_engine = HighlightEngine()
sequence_analyzer = SequencePoseAnalyzer()
ball_tracking_engine = BallTrackingEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작 시 정리 작업
    cleanup_temp_files()
    
    # 백그라운드 정리 작업 시작
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    yield
    
    # 종료 시 정리 작업
    cleanup_temp_files()

def periodic_cleanup():
    """주기적인 파일 정리"""
    import time
    while True:
        time.sleep(3600)  # 1시간마다
        cleanup_old_files(max_age_hours=24)

# FastAPI 앱 생성
app = FastAPI(
    title="Golf 3D Analyzer API",
    description="골프 스윙 분석을 위한 API - 하이라이트 영상, 시퀀스 이미지, 볼 트래킹 (분리된 전용 엔진)",
    version="1.1.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발용, 실제 배포시에는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 파일 업로드 API
@app.post("/api/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """비디오 파일 업로드"""
    try:
        # 파일 형식 검증
        if not file.content_type or not file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="비디오 파일만 업로드 가능합니다")
        
        # 파일 크기 제한 (100MB)
        file_size = 0
        file_id = generate_file_id()
        file_path = get_file_path(f"{file_id}.{file.filename.split('.')[-1]}", "uploads")
        
        # 파일 저장
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):  # 8KB씩 읽기
                file_size += len(chunk)
                if file_size > 100 * 1024 * 1024:  # 100MB 제한
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="파일 크기가 100MB를 초과합니다")
                buffer.write(chunk)
        
        # 비디오 파일 유효성 검사
        if not validate_video_file(file_path):
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="유효하지 않은 비디오 파일입니다")
        
        return UploadResponse(
            file_id=f"{file_id}.{file.filename.split('.')[-1]}",  # 확장자 포함된 전체 파일 ID 반환
            filename=file.filename,
            size=file_size,
            status="uploaded"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")

# 2. 하이라이트 영상 생성 API
@app.post("/api/highlight-video", response_model=HighlightVideoResponse)
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
        raise HTTPException(status_code=500, detail=f"하이라이트 생성 실패: {str(e)}")

# 3. 스윙 시퀀스 이미지 생성 API
@app.post("/api/swing-sequence", response_model=SwingSequenceResponse)
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
        
        # 백그라운드 태스크 실행 - SequenceComposer 직접 사용
        composer = SequenceComposer(sequence_analyzer)
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
        raise HTTPException(status_code=500, detail=f"시퀀스 이미지 생성 실패: {str(e)}")

# 4. 볼 트래킹 영상 생성 API
@app.post("/api/ball-tracking", response_model=BallTrackingResponse)
async def create_ball_tracking_video_endpoint(request: BallTrackingRequest, background_tasks: BackgroundTasks):
    """골프공 트래킹 영상 생성 (스윙 분석 연동)"""
    try:
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        task_id = generate_task_id("balltrack")
        update_task_status(task_id, "pending", 0, "볼 트래킹 생성 대기 중")
        
        # BallTrackingEngine의 전용 함수를 백그라운드 태스크로 실행
        background_tasks.add_task(
            ball_tracking_engine.create_ball_tracking_video,
            request.file_id, task_id
        )
        
        return BallTrackingResponse(task_id=task_id, status=TaskStatus.PENDING)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"볼 트래킹 생성 실패: {str(e)}")

# 4.5. 볼 분석 API (영상 생성 없이 분석만)
@app.post("/api/ball-analysis", response_model=BallTrackingResponse)
async def create_ball_analysis_endpoint(request: BallTrackingRequest, background_tasks: BackgroundTasks):
    """골프공 분석 (영상 생성 없이 분석 결과만 반환)"""
    try:
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="업로드된 파일을 찾을 수 없습니다")
        
        task_id = generate_task_id("ballanalysis")
        update_task_status(task_id, "pending", 0, "볼 분석 대기 중")
        
        # BallTrackingEngine의 분석 전용 함수를 백그라운드 태스크로 실행
        background_tasks.add_task(
            ball_tracking_engine.get_ball_analysis_only,
            request.file_id, task_id
        )
        
        return BallTrackingResponse(task_id=task_id, status=TaskStatus.PENDING)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"볼 분석 실패: {str(e)}")

# 5. 태스크 상태 확인 API
@app.get("/api/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status_api(task_id: str):
    """태스크의 현재 상태, 진행률, GCS 다운로드 URL 등을 포함한 결과를 조회합니다."""
    try:
        status_data = get_task_status(task_id)
        if not status_data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # GCS URL은 result_data 안에 포함되어 있음
        download_url = status_data.get("result_data", {}).get("download_url")

        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatus(status_data.get("status", "not_found")),
            progress=status_data.get("progress", 0),
            message=status_data.get("message"),
            download_url=download_url,
            result_data=status_data.get("result_data")
        )
        
    except Exception as e:
        logger.error(f"상태 확인 중 오류 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")

# 6. 헬스 체크 API
@app.get("/api/health")
async def health_check():
    """API 상태 확인"""
    return {
        "status": "healthy",
        "message": "Golf 3D Analyzer API is running",
        "features": {
            "highlight_video": highlight_engine.highlight_analyzer.pose is not None,
            "swing_sequence": sequence_analyzer.pose is not None,
            "ball_tracking": True
        }
    }

# 7. 시스템 정보 API
@app.get("/api/info")
async def system_info():
    """시스템 정보 확인"""
    from .core.utils import UPLOADS_DIR, HIGHLIGHTS_DIR, SEQUENCES_DIR, BALL_TRACKS_DIR
    
    return {
        "api_version": "1.0.0",
        "supported_formats": ["mp4", "avi", "mov"],
        "max_file_size": "100MB",
        "storage_info": {
            "uploads": len(list(UPLOADS_DIR.glob("*"))),
            "highlights": len(list(HIGHLIGHTS_DIR.glob("*"))),
            "sequences": len(list(SEQUENCES_DIR.glob("*"))),
            "ball_tracks": len(list(BALL_TRACKS_DIR.glob("*")))
        }
    }

# 10. 예측 가능한 결과 다운로드 엔드포인트들
@app.get("/api/results/highlights/{task_id}.mp4")
async def get_highlight_result(task_id: str, download: bool = Query(False)):
    """하이라이트 영상 다운로드/스트리밍"""
    return await _get_video_result(task_id, "highlights", download)

@app.get("/api/results/sequences/{task_id}.png") 
async def get_sequence_result(task_id: str):
    """시퀀스 이미지 다운로드"""
    return await _get_image_result(task_id, "sequences")

@app.get("/api/results/highlights/{task_id}/stream")
async def stream_highlight(task_id: str):
    """하이라이트 영상 스트리밍 (별도 엔드포인트)"""
    return await _get_video_result(task_id, "highlights", download=False)

@app.get("/api/results/sequences/{task_id}/stream")
async def stream_sequence(task_id: str):
    """시퀀스 이미지 스트리밍 (이미지는 다운로드와 동일)"""
    return await get_sequence_result(task_id)

async def _get_video_result(task_id: str, content_type: str, download: bool = False):
    """비디오 결과 파일 반환 (공통 로직)"""
    try:
        # 태스크 상태 확인
        status_data = get_task_status(task_id)
        
        if not status_data or status_data.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="Task not found")
        
        status = status_data.get("status")
        
        if status == "processing" or status == "pending":
            # 처리 중이면 202 응답과 진행상황 반환
            return JSONResponse({
                "status": status,
                "progress": status_data.get("progress", 0),
                "message": status_data.get("message", "Processing..."),
                "retry_after": 5
            }, status_code=202)
            
        elif status == "failed":
            raise HTTPException(status_code=500, detail=f"Processing failed: {status_data.get('message', 'Unknown error')}")
            
        elif status == "completed":
            # 완료된 경우 파일 반환
            result_data = status_data.get("result_data", {})
            
            # GCS URL이 있으면 리다이렉트
            if "download_url" in result_data and result_data["download_url"].startswith("http"):
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=result_data["download_url"])
            
            # 로컬 파일이 있으면 직접 서빙
            local_file_path = get_file_path(f"{task_id}.mp4", content_type)
            if local_file_path.exists():
                if download:
                    return FileResponse(
                        local_file_path,
                        filename=f"{content_type}_{task_id}.mp4",
                        media_type="video/mp4"
                    )
                else:
                    return FileResponse(local_file_path, media_type="video/mp4")
            
            raise HTTPException(status_code=404, detail="Result file not found")
        
        else:
            raise HTTPException(status_code=500, detail=f"Unknown status: {status}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def _get_image_result(task_id: str, content_type: str):
    """이미지 결과 파일 반환 (공통 로직)"""
    try:
        # 태스크 상태 확인  
        status_data = get_task_status(task_id)
        
        if not status_data or status_data.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="Task not found")
        
        status = status_data.get("status")
        
        if status == "processing" or status == "pending":
            return JSONResponse({
                "status": status,
                "progress": status_data.get("progress", 0),
                "message": status_data.get("message", "Processing..."),
                "retry_after": 3
            }, status_code=202)
            
        elif status == "failed":
            raise HTTPException(status_code=500, detail=f"Processing failed: {status_data.get('message', 'Unknown error')}")
            
        elif status == "completed":
            result_data = status_data.get("result_data", {})
            
            # GCS URL이 있으면 리다이렉트
            if "download_url" in result_data and result_data["download_url"].startswith("http"):
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=result_data["download_url"])
            
            # 로컬 파일이 있으면 직접 서빙
            local_file_path = get_file_path(f"{task_id}.png", content_type)
            if local_file_path.exists():
                return FileResponse(local_file_path, media_type="image/png")
            
            raise HTTPException(status_code=404, detail="Result file not found")
        
        else:
            raise HTTPException(status_code=500, detail=f"Unknown status: {status}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 