from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"

# 업로드 관련
class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    status: str

# 하이라이트 영상 관련
class HighlightVideoRequest(BaseModel):
    file_id: str
    total_duration: int = 15
    slow_factor: int = 4

class HighlightVideoResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: Optional[str] = None
    stream_url: Optional[str] = None
    estimated_time: int = 30  # 예상 처리 시간 (초)

# 스윙 시퀀스 이미지 관련
class SwingSequenceRequest(BaseModel):
    file_id: str

class SwingSequenceResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: Optional[str] = None
    stream_url: Optional[str] = None
    estimated_time: int = 20  # 예상 처리 시간 (초)

# 골프공 트래킹 관련
class BallTrackingRequest(BaseModel):
    file_id: str
    show_trajectory: bool = True
    show_speed: bool = True
    show_distance: bool = True

class BallTrackingResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: Optional[str] = None
    stream_url: Optional[str] = None
    estimated_time: int = 45  # 예상 처리 시간 (초)

# 골프공 분석 관련
class BallAnalysisRequest(BaseModel):
    file_id: str
    analysis_type: str = "full"  # full, speed, trajectory, distance

class BallAnalysisResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: Optional[str] = None
    stream_url: Optional[str] = None
    analysis_data: Optional[Dict[str, Any]] = None
    estimated_time: int = 60  # 예상 처리 시간 (초)

# 상태 확인 관련
class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    message: Optional[str] = None
    download_url: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

# Scorecard OCR 관련 (향후 확장)
class ScorecardRecognizeRequest(BaseModel):
    file_id: str
    ocr_language: str = "ko"  # ko, en, auto

class ScorecardRecognizeResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: Optional[str] = None
    ocr_data: Optional[Dict[str, Any]] = None
    estimated_time: int = 15  # 예상 처리 시간 (초)

# 에러 응답
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None 