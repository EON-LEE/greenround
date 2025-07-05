# Greenround - 신규 기능 개발 가이드 ✅

## 🚀 새로운 기능 추가 체크리스트

### 📋 개발 전 준비
- [ ] 기능 이름 정하기 (예: `swing_score`, `pose_analysis`)
- [ ] API 엔드포인트 설계 (예: `/api/roundreels/swing-score`)
- [ ] 필요한 입력/출력 데이터 정의

---

## 🔥 개발 단계 (순서대로 진행)

### 1️⃣ 스키마 정의
**📍 위치**: `backend/models/schemas.py`

```python
# 요청 스키마 추가(예시)
class SwingScoreRequest(BaseModel):
    file_id: str
    scoring_criteria: str = "professional"

# 응답 스키마 추가 (예시)
class SwingScoreResponse(BaseModel):
    task_id: str
    status: TaskStatus
    estimated_time: int = 30
```

**체크리스트**:
- [ ] Request 모델 정의
- [ ] Response 모델 정의
- [ ] 필요시 Enum 추가

---

### 2️⃣ 엔진 파일 생성
**📍 위치**: `backend/core/roundreels/{기능명}_engine.py`

```bash
# 파일 생성
touch backend/core/roundreels/swing_score_engine.py
```

```python
# 엔진 구현
import logging
from core.common.utils import update_task_status, get_file_path
from core.common.firestore_sync import get_firestore_client
from google.cloud import firestore

logger = logging.getLogger(__name__)

class SwingScoreEngine:
    def __init__(self):
        self.analyzer = None
    
    def calculate_swing_score(self, file_id: str, task_id: str, criteria: str):
        try:
            update_task_status(task_id, "processing", 10, "분석 시작")
            
            # 파일 검증
            file_path = get_file_path(file_id, "uploads")
            if not file_path.exists():
                raise FileNotFoundError(f"파일 없음: {file_id}")
            
            # Firestore에 초기 레코드 저장
            db = get_firestore_client()
            if db:
                db.collection('swing_scores').document(task_id).set({
                    'task_id': task_id,
                    'file_id': file_id,
                    'status': 'processing',
                    'created_at': firestore.SERVER_TIMESTAMP
                })
            
            # 실제 분석 로직 (여기에 AI/ML 코드 구현)
            result_data = {
                "total_score": 85.5,
                "details": {"technique": 90, "power": 80}
            }
            
            # 결과 저장
            if db:
                db.collection('swing_scores').document(task_id).update({
                    'total_score': result_data["total_score"],
                    'detailed_scores': result_data["details"],
                    'status': 'completed',
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
            
            update_task_status(task_id, "completed", 100, "분석 완료", result_data)
            
        except Exception as e:
            logger.error(f"분석 실패: {e}")
            update_task_status(task_id, "failed", 0, f"실패: {str(e)}")
```

**체크리스트**:
- [ ] 엔진 클래스 생성
- [ ] 메인 처리 함수 구현
- [ ] Firestore 데이터 저장 로직 추가
- [ ] 에러 처리 구현

---

### 3️⃣ 라우터에 API 추가
**📍 위치**: `backend/routers/roundreels.py`

```python
# 파일 상단에 임포트 추가
from models.schemas import SwingScoreRequest, SwingScoreResponse
from core.roundreels.swing_score_engine import SwingScoreEngine

# 싱글톤 인스턴스 추가
_swing_score_engine = None

def get_swing_score_engine():
    global _swing_score_engine
    if _swing_score_engine is None:
        _swing_score_engine = SwingScoreEngine()
    return _swing_score_engine

# API 엔드포인트 추가
@router.post("/swing-score", response_model=SwingScoreResponse)
async def calculate_swing_score(request: SwingScoreRequest, background_tasks: BackgroundTasks):
    """스윙 점수 계산"""
    try:
        # 파일 확인
        file_path = get_file_path(request.file_id, "uploads")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
        
        # 태스크 생성
        task_id = generate_task_id("swingscore")
        update_task_status(task_id, "pending", 0, "대기 중")
        
        # 백그라운드 실행
        engine = get_swing_score_engine()
        background_tasks.add_task(
            engine.calculate_swing_score,
            request.file_id, 
            task_id, 
            request.scoring_criteria
        )
        
        return SwingScoreResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            estimated_time=30
        )
        
    except Exception as e:
        logger.error(f"API 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**체크리스트**:
- [ ] 스키마 임포트 추가
- [ ] 엔진 임포트 추가
- [ ] 싱글톤 함수 추가
- [ ] API 엔드포인트 구현

---

### 4️⃣ 새 서비스인 경우 메인 앱 등록
**📍 위치**: `backend/main.py` (새 서비스인 경우만)

```python
# 라우터 임포트 추가
from routers import common, roundreels, new_service

# 라우터 등록 추가
app.include_router(new_service.router, tags=["🆕 NewService"])
```

**체크리스트**:
- [ ] 새 라우터 파일 생성한 경우에만 추가
- [ ] 기존 서비스 확장시에는 건드리지 않음

---

## 🧪 테스트 및 확인

### 5️⃣ 로컬 테스트
```bash
# 서버 실행
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# API 테스트
curl -X POST "http://localhost:8001/api/roundreels/swing-score" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "test_file", "scoring_criteria": "professional"}'
```

**체크리스트**:
- [ ] 서버 정상 실행 확인
- [ ] API 호출 테스트
- [ ] Firestore 데이터 저장 확인
- [ ] 에러 케이스 테스트

---

## 📄 Firestore 컬렉션 설계

### 컬렉션 구조 예시
```javascript
// swing_scores 컬렉션
{
  "task_id": "swingscore_20241221_123456",  // 문서 ID
  "user_id": "user123",                     // 사용자 ID
  "file_id": "file_abc123",                 // 파일 ID
  "scoring_criteria": "professional",       // 채점 기준
  "total_score": 85.5,                     // 총 점수
  "detailed_scores": {                     // 상세 점수
    "technique": 90,
    "power": 80,
    "accuracy": 85
  },
  "status": "completed",                   // 상태
  "created_at": "2024-12-21T10:00:00Z",   // 생성일
  "updated_at": "2024-12-21T10:05:00Z"    // 수정일
}
```

---

## 🔧 자주 사용하는 코드 패턴

### Firestore 기본 사용법
```python
from core.common.firestore_sync import get_firestore_client
from google.cloud import firestore

# 클라이언트 가져오기
db = get_firestore_client()

# 문서 추가
db.collection('컬렉션명').document('문서ID').set(데이터)

# 문서 수정
db.collection('컬렉션명').document('문서ID').update(업데이트데이터)

# 문서 조회
doc = db.collection('컬렉션명').document('문서ID').get()
if doc.exists:
    data = doc.to_dict()

# 쿼리 조회
docs = db.collection('컬렉션명')\
        .where('필드명', '==', '값')\
        .limit(10)\
        .stream()
```

### 에러 처리 패턴
```python
try:
    # 작업 수행
    result = do_something()
    update_task_status(task_id, "completed", 100, "완료", result)
except FileNotFoundError as e:
    update_task_status(task_id, "failed", 0, f"파일 없음: {e}")
except Exception as e:
    logger.error(f"예상치 못한 오류: {e}")
    update_task_status(task_id, "failed", 0, f"실패: {str(e)}")
```

---

## 📚 참고 링크

- **API 문서**: http://localhost:8001/docs
- **Firestore 클라이언트**: `backend/core/common/firestore_sync.py`
- **기존 스키마**: `backend/models/schemas.py`
- **기존 라우터**: `backend/routers/roundreels.py`

---

**🎯 개발 완료 체크리스트**
- [ ] 스키마 정의 완료
- [ ] 엔진 구현 완료
- [ ] 라우터 등록 완료
- [ ] 로컬 테스트 통과
- [ ] Firestore 데이터 저장 확인
- [ ] API 문서 확인 (http://localhost:8001/docs)