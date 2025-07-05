# 🏌️ Golf 3D Analyzer 백엔드 구조 설명서

> **새로운 개발자가 30분만에 백엔드 전체 구조를 파악할 수 있도록 작성된 문서**

---

## 🎯 1. 아키텍처 개요

### 설계 철학: 마이크로서비스 + 레이어 분리

```
사용자 요청 → FastAPI Router → Core Engine → 결과 반환
           ↓
        GCS 파일 저장 ← Firestore 메타데이터
```

**왜 이렇게 설계했나?**
- **확장성**: 새로운 분석 서비스 쉽게 추가
- **성능**: 싱글톤 패턴으로 AI 모델 재사용  
- **분리**: 비즈니스 로직과 API 레이어 독립

### 폴더 구조 한눈에 보기

```
backend/
├── main.py              # FastAPI 앱 + 라우터 등록
├── routers/             # API 엔드포인트 레이어
│   ├── common.py        # 공통 기능 (업로드, 상태, 다운로드)
│   └── roundreels.py    # 골프 분석 전용 API
├── core/                # 비즈니스 로직 레이어
│   ├── common/          # 공통 유틸리티
│   └── roundreels/      # 골프 분석 엔진들
│       ├── pose/        # 포즈 분석 파이프라인
│       ├── highlight_engine.py
│       ├── sequence_composer.py
│       └── ball_tracking_engine.py
├── models/              # 데이터 스키마
│   └── schemas.py       # Pydantic 모델들
└── storage/             # 로컬 임시 파일
```

### 데이터 플로우

```mermaid
graph TD
    A[클라이언트] --> B[/api/upload]
    B --> C[로컬 임시 저장]
    C --> D[/api/roundreels/*]
    D --> E[Core Engine 분석]
    E --> F[GCS 업로드]
    F --> G[Firestore 메타데이터]
    G --> H[/api/status 완료]
    H --> I[클라이언트 다운로드]
```

---

## 🛤️ 2. 라우터 분리 구조

### Router 역할 분담

**`common.py` - 모든 서비스가 공유하는 기능**
```python
router = APIRouter(prefix="/api")

@router.post("/upload")           # 파일 업로드
@router.get("/status/{task_id}")  # 작업 상태 조회  
@router.get("/health")            # 헬스체크
@router.get("/info")              # 시스템 정보
```

**`roundreels.py` - 골프 분석 전용 API**
```python
router = APIRouter(prefix="/api/roundreels")

@router.post("/highlight-video")  # 3단계 슬로우모션
@router.post("/swing-sequence")   # 7단계 스윙 분석
@router.post("/ball-tracking")    # 볼 궤적 추적
@router.post("/ball-analysis")    # 볼 데이터만 분석
```

### 라우터 등록 방식

```python
# main.py
app = FastAPI(title="Golf 3D Analyzer API")

# 라우터 등록 - 태그로 API 문서 그룹화
app.include_router(common.router, tags=["📤 Common"])
app.include_router(roundreels.router, tags=["🏌️ RoundReels"])
```

### 새 서비스 추가하는 방법

**1단계**: `routers/새서비스.py` 생성
```python
from fastapi import APIRouter
router = APIRouter(prefix="/api/새서비스")

@router.post("/분석기능")
async def 분석_기능():
    return {"result": "완료"}
```

**2단계**: `core/새서비스/` 폴더에 엔진 구현

**3단계**: `main.py`에 라우터 등록
```python
from routers import 새서비스
app.include_router(새서비스.router, tags=["🎯 새서비스"])
```

---

## 🧠 3. 코어 엔진 구조

### 비즈니스 로직 레이어 설계

```python
# backend/core/ - 실제 분석 로직이 여기에
core/
├── common/
│   ├── utils.py          # 파일 관리, 정리 유틸
│   └── firestore_sync.py # DB 동기화
└── roundreels/
    ├── highlight_engine.py    # 하이라이트 영상 생성
    ├── sequence_composer.py   # 스윙 시퀀스 합성  
    ├── ball_tracking_engine.py # 볼 추적
    └── pose/                  # 포즈 분석 파이프라인
        ├── base_pose_analyzer.py
        ├── highlight_pose_analyzer.py
        └── sequence_pose_analyzer.py
```

### 싱글톤 패턴으로 엔진 관리

**왜 싱글톤을 사용하나?**
- MediaPipe 모델 로딩 시간: ~2-3초
- GPU 메모리 효율성
- 동시 요청 시 성능 최적화

```python
class HighlightEngine:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.pose_analyzer = HighlightPoseAnalyzer()  # 한 번만 초기화
            self._initialized = True
```

### 포즈 분석 파이프라인

**3단계 분석 구조**
```python
# 1. 베이스 - 공통 MediaPipe 설정
class BasePoseAnalyzer:
    def __init__(self):
        self.pose = mp.solutions.pose.Pose(
            model_complexity=2,           # GPU 최고 정밀도
            min_detection_confidence=0.7  # 높은 신뢰도
        )

# 2. 하이라이트용 - 최고 품질 1개 스윙 선택
class HighlightPoseAnalyzer(BasePoseAnalyzer):
    def _detect_best_swing(self):
        # 품질 + 움직임 + 시간 순서 고려
        
# 3. 시퀀스용 - 키프레임 추출 최적화
class SequencePoseAnalyzer(BasePoseAnalyzer):
    def _detect_key_swing(self):
        # 품질 우선 + 안정적인 키프레임
```

**스윙 감지 로직**
```python
# 두 번 스윙 시 나중 스윙(본스윙) 선택 로직
def _select_best_swing_candidate(self, candidates):
    for candidate in candidates:
        # 시간적 위치 가산점 (나중 스윙 우대)
        time_bonus = candidate['start_frame'] / total_frames * 0.3
        
        score = (
            quality * 0.4 +      # 포즈 품질
            movement * 0.4 +     # 움직임 강도  
            time_bonus * 0.2     # 시간 순서 (본스윙 우대)
        )
```

---

## ☁️ 4. 클라우드 통합

### GCS + Firestore 역할 분담

**Google Cloud Storage**: 파일 저장소
```python
# 업로드된 파일 → GCS 영구 저장
def upload_to_gcs(local_file, gcs_path):
    bucket = storage_client.bucket("greenround-storage")
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_file)
    
    # Signed URL 생성 (24시간 유효)
    return blob.generate_signed_url(expiration=timedelta(hours=24))
```

**Firestore**: 메타데이터 & 상태 관리
```python
# 작업 상태 실시간 업데이트
def update_task_status(task_id, status, progress=None):
    doc_ref = db.collection("tasks").document(task_id)
    doc_ref.set({
        "status": status,           # "processing" | "completed" | "failed"
        "progress": progress,       # 0-100%
        "updated_at": datetime.now(),
        "result_urls": {...}        # 완료 시 다운로드 링크
    })
```

### 파일 관리 전략

**임시 → 영구 저장 플로우**
```python
# 1. 업로드: 로컬 임시 저장
uploaded_file → backend/storage/uploads/

# 2. 분석: 임시 결과 생성  
analysis_result → backend/storage/temp/

# 3. 완료: GCS 영구 저장
gcs_upload → gs://greenround-storage/results/

# 4. 정리: 로컬 파일 삭제 (1시간 후)
cleanup_old_files(max_age_hours=1)
```

**정리 시스템**
```python
# main.py - 앱 시작 시 백그라운드 정리 작업
def periodic_cleanup():
    while True:
        time.sleep(3600)  # 1시간마다
        cleanup_old_files(max_age_hours=24)
        cleanup_temp_files()
```

---

## 🎯 핵심 설계 포인트

### ✅ 확장성
- 새로운 분석 서비스 = 새 라우터 + 새 코어 엔진
- 기존 코드 수정 없이 기능 추가 가능

### ✅ 성능  
- 싱글톤 패턴으로 AI 모델 재사용
- 비동기 처리 + 백그라운드 작업
- GPU 최적화 설정

### ✅ 유지보수성
- 레이어별 책임 분리 (Router → Core → Models)
- 공통 기능 모듈화 (`core/common/`)
- 타입 힌트 + Pydantic 검증

---

**이 구조를 이해했다면, 이제 새로운 골프 분석 기능을 쉽게 추가할 수 있습니다! 🚀** 