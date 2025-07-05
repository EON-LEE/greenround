from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
import os
import logging
from pathlib import Path

# 로컬 모듈들 (절대 import로 수정)
from models.schemas import UploadResponse, TaskStatusResponse, TaskStatus, ErrorResponse
from core.common.utils import (
    generate_file_id, get_file_path, validate_video_file,
    get_task_status, UPLOADS_DIR, HIGHLIGHTS_DIR, SEQUENCES_DIR, BALL_TRACKS_DIR
)
from core.common.firestore_sync import test_firestore_connection

logger = logging.getLogger(__name__)

# 공통 API 라우터 생성
router = APIRouter(
    prefix="/api",
    tags=["common"],
    responses={404: {"model": ErrorResponse}},
)

# 1. 파일 업로드 API
@router.post("/upload", response_model=UploadResponse)
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

# 2. 태스크 상태 확인 API
@router.get("/status/{task_id}", response_model=TaskStatusResponse)
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

# 3. 헬스 체크 API
@router.get("/health")
async def health_check():
    """API 상태 확인"""
    return {
        "status": "healthy",
        "message": "Golf 3D Analyzer API is running",
        "version": "2.0.0",
        "architecture": "microservice"
    }

# 4. 시스템 정보 API
@router.get("/info")
async def system_info():
    """시스템 정보 확인"""
    # Firestore 연결 테스트
    firestore_status = test_firestore_connection()
    
    return {
        "api_version": "2.0.0",
        "architecture": "microservice",
        "supported_formats": ["mp4", "avi", "mov"],
        "max_file_size": "100MB",
        "storage_info": {
            "uploads": len(list(UPLOADS_DIR.glob("*"))),
            "highlights": len(list(HIGHLIGHTS_DIR.glob("*"))),
            "sequences": len(list(SEQUENCES_DIR.glob("*"))),
            "ball_tracks": len(list(BALL_TRACKS_DIR.glob("*")))
        },
        "services": {
            "swingclip": {
                "highlight_video": True,
                "swing_sequence": True,
                "ball_tracking": True,
                "ball_analysis": True
            },
            "scorecard": {
                "ocr_recognition": False  # 향후 구현 예정
            }
        },
        "firestore": {
            "status": firestore_status.get("status"),
            "message": firestore_status.get("message")
        }
    }

# 4-1. Firestore 상태 전용 API (새로 추가)
@router.get("/firestore/status")
async def firestore_status():
    """Firestore 연결 상태 확인"""
    return test_firestore_connection()

# 4-2. Firestore 컬렉션 정보 API (새로 추가)
@router.get("/firestore/collections")
async def firestore_collections_info():
    """기능별 Firestore 컬렉션 정보 조회"""
    from core.common.firestore_sync import get_firestore_collections_info
    return get_firestore_collections_info()

# 5. 예측 가능한 결과 다운로드 엔드포인트들
@router.get("/results/highlights/{task_id}.mp4")
async def get_highlight_result(task_id: str, download: bool = Query(False)):
    """하이라이트 영상 다운로드/스트리밍"""
    return await _get_video_result(task_id, "highlights", download)

@router.get("/results/sequences/{task_id}.png") 
async def get_sequence_result(task_id: str):
    """시퀀스 이미지 다운로드"""
    return await _get_image_result(task_id, "sequences")

@router.get("/results/highlights/{task_id}/stream")
async def stream_highlight(task_id: str):
    """하이라이트 영상 스트리밍 (별도 엔드포인트)"""
    return await _get_video_result(task_id, "highlights", download=False)

@router.get("/results/sequences/{task_id}/stream")
async def stream_sequence(task_id: str):
    """시퀀스 이미지 스트리밍 (이미지는 다운로드와 동일)"""
    return await get_sequence_result(task_id)

# 6. 공통 헬퍼 함수들
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