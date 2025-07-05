import os
import uuid
import shutil
import logging
import asyncio
from typing import Dict, Any, Optional
import cv2
from pathlib import Path
from google.cloud import storage
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .env 파일에서 환경 변수 로드
load_dotenv()

# 스토리지 경로 설정
BASE_DIR = Path(__file__).parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
HIGHLIGHTS_DIR = STORAGE_DIR / "highlights"
SEQUENCES_DIR = STORAGE_DIR / "sequences"
BALL_TRACKS_DIR = STORAGE_DIR / "ball_tracks"
TEMP_DIR = STORAGE_DIR / "temp"

# 디렉토리 생성
for dir_path in [UPLOADS_DIR, HIGHLIGHTS_DIR, SEQUENCES_DIR, BALL_TRACKS_DIR, TEMP_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 글로벌 태스크 상태 저장소
task_status: Dict[str, Dict[str, Any]] = {}

# --- GCS 설정 ---
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    logger.warning("GCS_BUCKET_NAME 환경 변수가 설정되지 않았습니다. GCS 업로드가 실패할 수 있습니다.")

def generate_file_id() -> str:
    """고유한 파일 ID 생성"""
    return str(uuid.uuid4())

def generate_task_id(prefix: str = "task") -> str:
    """고유한 태스크 ID 생성"""
    return f"{prefix}_{str(uuid.uuid4())[:8]}"

def get_service_base_url() -> str:
    """서비스 베이스 URL 반환 (환경에 따라 동적 설정)"""
    # 환경변수에서 BASE_URL을 가져오거나, 기본값 사용
    base_url = os.getenv("SERVICE_BASE_URL", "https://golf-analyzer-backend-984220723638.asia-northeast3.run.app")
    return base_url.rstrip('/')

def generate_predictable_urls(task_id: str, content_type: str) -> dict:
    """예측 가능한 URL들을 미리 생성"""
    base_url = get_service_base_url()
    
    # content_type: "highlights", "sequences", "ball_tracks"
    urls = {
        "download": f"{base_url}/api/results/{content_type}/{task_id}",
        "stream": f"{base_url}/api/results/{content_type}/{task_id}/stream",
        "status": f"{base_url}/api/status/{task_id}"
    }
    
    # 이미지 타입인 경우 확장자 추가
    if content_type == "sequences":
        urls["download"] += ".png"
        urls["stream"] = urls["download"]  # 이미지는 스트리밍과 다운로드가 동일
    else:
        urls["download"] += ".mp4"
    
    return urls

def get_file_path(file_id: str, directory: str = "uploads") -> Path:
    """파일 ID로 파일 경로 생성"""
    dir_map = {
        "uploads": UPLOADS_DIR,
        "highlights": HIGHLIGHTS_DIR,
        "sequences": SEQUENCES_DIR,
        "ball_tracks": BALL_TRACKS_DIR,
        "temp": TEMP_DIR
    }
    return dir_map.get(directory, UPLOADS_DIR) / file_id

def validate_video_file(file_path: Path) -> bool:
    """비디오 파일 유효성 검사"""
    try:
        if not file_path.exists():
            return False
            
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            return False
            
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        cap.release()
        
        # 최소 요구사항 확인
        if frame_count < 30 or fps < 10 or width < 100 or height < 100:
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Video validation error: {str(e)}")
        return False

def get_video_info(file_path: Path) -> Dict[str, Any]:
    """비디오 파일 정보 추출"""
    try:
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            raise ValueError("Cannot open video file")
            
        info = {
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration": 0
        }
        
        if info["fps"] > 0:
            info["duration"] = info["frame_count"] / info["fps"]
        
        cap.release()
        return info
        
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return {}

def update_task_status(task_id: str, status: str, progress: int = 0, 
                      message: str = None, result_data: dict = None):
    """태스크 상태 업데이트 (Firestore 동기화 포함)"""
    # 🔄 기존 메모리 저장 (100% 동일)
    task_status[task_id] = {
        "status": status,
        "progress": progress,
        "message": message,
        "result_data": result_data or {}
    }
    logger.info(f"Task {task_id} updated: {status} ({progress}%)")
    
    # 🆕 Firestore 동기화 (실패해도 기존 기능 정상 동작)
    try:
        from .firestore_sync import safe_sync_to_firestore
        safe_sync_to_firestore(task_id, task_status[task_id])
    except Exception as e:
        logger.warning(f"Firestore 동기화 실패 (기존 기능은 정상): {e}")

def get_task_status(task_id: str) -> Dict[str, Any]:
    """태스크 상태 조회 (Firestore 폴백 포함)"""
    # 🔄 기존 메모리 조회 (우선순위 1)
    if task_id in task_status:
        return task_status[task_id]
    
    # 🆕 Firestore에서 복구 시도 (Cloud Run 재시작 대응)
    try:
        from .firestore_sync import safe_get_from_firestore
        firestore_data = safe_get_from_firestore(task_id)
        if firestore_data:
            # 메모리에 복원
            task_status[task_id] = firestore_data
            logger.info(f"📥 Firestore에서 상태 복구: {task_id}")
            return firestore_data
    except Exception as e:
        logger.warning(f"Firestore 복구 실패 (기존 로직 사용): {e}")
    
    # 🔄 기존 기본값 반환 (100% 동일)
    return {
        "status": "not_found",
        "progress": 0,
        "message": "Task not found"
    }

def cleanup_temp_files():
    """임시 파일들 정리"""
    try:
        for file_path in TEMP_DIR.glob("*"):
            if file_path.is_file():
                file_path.unlink()
        logger.info("Temporary files cleaned up")
    except Exception as e:
        logger.error(f"Error cleaning temp files: {str(e)}")

def cleanup_old_files(max_age_hours: int = 24):
    """오래된 파일들 정리 (Firestore 정리 포함)"""
    import time
    
    try:
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for directory in [UPLOADS_DIR, HIGHLIGHTS_DIR, SEQUENCES_DIR, BALL_TRACKS_DIR]:
            for file_path in directory.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        logger.info(f"Cleaned old file: {file_path.name}")
                        
    except Exception as e:
        logger.error(f"Error cleaning old files: {str(e)}")
    
    # 🆕 Firestore 정리 (실패해도 기존 기능에 영향 없음)
    try:
        from .firestore_sync import cleanup_old_firestore_tasks
        cleanup_old_firestore_tasks(max_age_hours)
    except Exception as e:
        logger.warning(f"Firestore 정리 실패 (무시): {e}")

async def run_background_task(task_func, *args, **kwargs):
    """백그라운드 태스크 실행"""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, task_func, *args, **kwargs)
    except Exception as e:
        logger.error(f"Background task error: {str(e)}")
        raise 

def upload_to_gcs_and_get_public_url(local_file_path: Path, destination_blob_name: str) -> str:
    """
    로컬 파일을 GCS에 업로드하고 Signed URL(1시간 유효)을 반환합니다.
    이 함수를 사용하려면 'GOOGLE_APPLICATION_CREDENTIALS' 환경 변수가 설정되어 있어야 합니다.
    """
    try:
        if not GCS_BUCKET_NAME:
            logger.error("GCS_BUCKET_NAME 환경 변수가 설정되지 않았습니다. 로컬 파일을 유지합니다.")
            # GCS 업로드 대신 로컬 파일 경로 반환 (개발/테스트용)
            return f"file://{local_file_path}"
        
        from datetime import datetime, timedelta
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)

        blob.upload_from_filename(str(local_file_path))

        # 로컬 임시 파일 삭제
        if local_file_path.exists():
            os.remove(local_file_path)

        # Signed URL 생성 (1시간 유효)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.utcnow() + timedelta(hours=1),
            method="GET"
        )

        logger.info(f"'{local_file_path}'를 GCS 버킷 '{GCS_BUCKET_NAME}'에 '{destination_blob_name}'(으)로 업로드했습니다.")
        logger.info(f"Signed URL 생성됨 (1시간 유효): {signed_url[:100]}...")
        return signed_url
        
    except Exception as e:
        logger.error(f"GCS 업로드 실패: {e}", exc_info=True)
        # 업로드 실패 시 로컬 파일 경로 반환 (fallback)
        logger.warning(f"GCS 업로드 실패로 로컬 파일 경로를 반환합니다: {local_file_path}")
        return f"file://{local_file_path}" 