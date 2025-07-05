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
    download_url: str
    stream_url: str
    estimated_time: int = 30  # 예상 처리 시간 (초)

# 스윙 시퀀스 이미지 관련
class SwingSequenceRequest(BaseModel):
    file_id: str

class SwingSequenceResponse(BaseModel):
    task_id: str
    status: TaskStatus
    download_url: str
    stream_url: str
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
    download_url: str
    stream_url: str
    estimated_time: int = 45  # 예상 처리 시간 (초)

# 상태 확인 관련
class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    message: Optional[str] = None
    download_url: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True

# 에러 응답
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None 