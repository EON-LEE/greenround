"""
Firestore 동기화 - 기존 메모리 상태 관리와 병행하는 안전한 구현
기존 코드가 절대 망가지지 않도록 설계됨
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Firestore 클라이언트 (지연 로딩)
_db = None
_firestore_enabled = None

def is_firestore_enabled() -> bool:
    """Firestore 사용 가능 여부 확인 (환경 변수 기반)"""
    global _firestore_enabled
    if _firestore_enabled is None:
        # 환경 변수로 Firestore 사용 여부 제어
        _firestore_enabled = os.getenv("ENABLE_FIRESTORE_SYNC", "false").lower() == "true"
        logger.info(f"Firestore 동기화: {'활성화' if _firestore_enabled else '비활성화'}")
    return _firestore_enabled

def get_firestore_client():
    """Firestore 클라이언트 가져오기 (안전한 싱글톤)"""
    global _db
    
    if not is_firestore_enabled():
        return None
        
    if _db is None:
        try:
            from google.cloud import firestore
            
            # 환경 변수에서 데이터베이스 ID 가져오기
            database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
            project_id = os.getenv("FIRESTORE_PROJECT_ID")
            
            if database_id != "(default)":
                # 커스텀 데이터베이스 ID 사용
                _db = firestore.Client(project=project_id, database=database_id)
                logger.info(f"✅ Firestore 클라이언트 연결 성공 (DB: {database_id})")
            else:
                # 기본 데이터베이스 사용
                _db = firestore.Client(project=project_id)
                logger.info("✅ Firestore 클라이언트 연결 성공 (기본 DB)")
                
        except ImportError:
            logger.warning("⚠️ google-cloud-firestore 패키지가 설치되지 않음")
            _db = None
        except Exception as e:
            logger.warning(f"⚠️ Firestore 연결 실패: {e}")
            _db = None
    return _db

def get_collection_name_by_task_id(task_id: str) -> str:
    """task_id에서 기능별 컬렉션명 추출"""
    if task_id.startswith('highlight_'):
        return 'highlight_tasks'
    elif task_id.startswith('sequence_'):
        return 'sequence_tasks'
    elif task_id.startswith('balltrack_'):
        return 'balltracking_tasks'
    elif task_id.startswith('ballanalysis_'):
        return 'ballanalysis_tasks'
    else:
        # 기본 컬렉션 (하위 호환성)
        return 'tasks'

def safe_sync_to_firestore(task_id: str, data: Dict[str, Any]):
    """
    Firestore에 안전하게 동기화 (기능별 컬렉션 사용)
    """
    if not is_firestore_enabled():
        return
        
    try:
        db = get_firestore_client()
        if db is None:
            return
            
        # 기능별 컬렉션명 결정
        collection_name = get_collection_name_by_task_id(task_id)
        
        # 현재 시간 추가
        sync_data = {
            'task_id': task_id,
            'status': data.get('status'),
            'progress': data.get('progress', 0),
            'message': data.get('message'),
            'result_data': data.get('result_data', {}),
            'feature_type': task_id.split('_')[0] if '_' in task_id else 'unknown',
            'created_at': data.get('created_at', datetime.utcnow()),
            'updated_at': datetime.utcnow(),
            'sync_timestamp': datetime.utcnow().isoformat()
        }
        
        # 기능별 컬렉션에 저장
        doc_ref = db.collection(collection_name).document(task_id)
        doc_ref.set(sync_data, merge=True)
        
        # 하위 호환성을 위해 기존 'tasks' 컬렉션에도 저장
        legacy_doc_ref = db.collection('tasks').document(task_id)
        legacy_doc_ref.set(sync_data, merge=True)
        
        logger.debug(f"📤 Firestore 동기화 완료: {collection_name}/{task_id} ({data.get('status')})")
        
    except Exception as e:
        # 모든 예외를 조용히 처리 (기존 기능 보호)
        logger.warning(f"⚠️ Firestore 동기화 실패 (기존 기능은 정상): {task_id} - {e}")

def safe_get_from_firestore(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Firestore에서 안전하게 조회 (기능별 컬렉션 우선, 폴백으로 기존 컬렉션)
    """
    if not is_firestore_enabled():
        return None
        
    try:
        db = get_firestore_client()
        if db is None:
            return None
        
        # 1순위: 기능별 컬렉션에서 조회
        collection_name = get_collection_name_by_task_id(task_id)
        doc_ref = db.collection(collection_name).document(task_id)
        doc = doc_ref.get()
        
        # 2순위: 기존 tasks 컬렉션에서 조회 (하위 호환성)
        if not doc.exists and collection_name != 'tasks':
            doc_ref = db.collection('tasks').document(task_id)
            doc = doc_ref.get()
            collection_name = 'tasks'
        
        if doc.exists:
            data = doc.to_dict()
            logger.debug(f"📥 Firestore에서 복구: {collection_name}/{task_id}")
            
            # 기존 형식으로 변환
            return {
                'status': data.get('status'),
                'progress': data.get('progress', 0),
                'message': data.get('message'),
                'result_data': data.get('result_data', {})
            }
            
    except Exception as e:
        logger.warning(f"⚠️ Firestore 조회 실패 (기존 로직 사용): {task_id} - {e}")
        
    return None

def cleanup_old_firestore_tasks(max_age_hours: int = 24):
    """
    오래된 Firestore 작업 정리 (모든 컬렉션에서 정리)
    """
    if not is_firestore_enabled():
        return
        
    try:
        db = get_firestore_client()
        if db is None:
            return
            
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        # 정리할 컬렉션 목록
        collections_to_clean = [
            'tasks',  # 기존 컬렉션 (하위 호환성)
            'highlight_tasks',
            'sequence_tasks', 
            'balltracking_tasks',
            'ballanalysis_tasks'
        ]
        
        total_deleted = 0
        
        for collection_name in collections_to_clean:
            try:
                # 각 컬렉션에서 오래된 문서 조회 및 삭제
                old_docs = db.collection(collection_name).where('updated_at', '<', cutoff_time).limit(50).stream()
                
                collection_deleted = 0
                for doc in old_docs:
                    doc.reference.delete()
                    collection_deleted += 1
                    
                if collection_deleted > 0:
                    logger.info(f"🧹 {collection_name}에서 {collection_deleted}개 오래된 작업 정리")
                    total_deleted += collection_deleted
                    
            except Exception as e:
                logger.warning(f"⚠️ {collection_name} 정리 실패: {e}")
                
        if total_deleted > 0:
            logger.info(f"🧹 Firestore 전체 정리 완료: {total_deleted}개 작업 삭제")
            
    except Exception as e:
        logger.warning(f"⚠️ Firestore 정리 실패 (무시): {e}")

def get_firestore_collections_info():
    """기능별 컬렉션 정보 조회"""
    if not is_firestore_enabled():
        return {"status": "disabled", "collections": {}}
        
    try:
        db = get_firestore_client()
        if db is None:
            return {"status": "failed", "collections": {}}
        
        collections_info = {}
        collections_to_check = [
            'tasks',  # 기존 컬렉션
            'highlight_tasks',
            'sequence_tasks',
            'balltracking_tasks', 
            'ballanalysis_tasks'
        ]
        
        for collection_name in collections_to_check:
            try:
                # 각 컬렉션의 문서 수 및 최신 업데이트 시간 확인
                docs = db.collection(collection_name).limit(1000).stream()
                doc_count = 0
                latest_update = None
                status_counts = {'completed': 0, 'processing': 0, 'failed': 0, 'pending': 0}
                
                for doc in docs:
                    doc_count += 1
                    data = doc.to_dict()
                    
                    # 상태별 카운트
                    status = data.get('status', 'unknown')
                    if status in status_counts:
                        status_counts[status] += 1
                    
                    # 최신 업데이트 시간
                    updated_at = data.get('updated_at')
                    if updated_at and (latest_update is None or updated_at > latest_update):
                        latest_update = updated_at
                
                collections_info[collection_name] = {
                    'document_count': doc_count,
                    'latest_update': latest_update.isoformat() if latest_update else None,
                    'status_counts': status_counts
                }
                
            except Exception as e:
                collections_info[collection_name] = {
                    'error': str(e),
                    'document_count': 0
                }
        
        return {
            "status": "success", 
            "collections": collections_info,
            "feature_mapping": {
                "highlight_": "highlight_tasks",
                "sequence_": "sequence_tasks", 
                "balltrack_": "balltracking_tasks",
                "ballanalysis_": "ballanalysis_tasks"
            }
        }
        
    except Exception as e:
        return {"status": "error", "message": f"컬렉션 정보 조회 실패: {e}"}

# 테스트용 함수
def test_firestore_connection():
    """Firestore 연결 테스트"""
    try:
        if not is_firestore_enabled():
            return {"status": "disabled", "message": "Firestore가 비활성화됨"}
            
        db = get_firestore_client()
        if db is None:
            return {"status": "failed", "message": "Firestore 클라이언트 생성 실패"}
            
        # 테스트 문서 작성/읽기
        test_doc = db.collection('_test').document('connection_test')
        test_data = {"test": True, "timestamp": datetime.utcnow()}
        test_doc.set(test_data)
        
        # 읽기 테스트
        read_doc = test_doc.get()
        if read_doc.exists:
            # 테스트 문서 삭제
            test_doc.delete()
            return {"status": "success", "message": "Firestore 연결 및 읽기/쓰기 성공"}
        else:
            return {"status": "failed", "message": "Firestore 쓰기는 성공했지만 읽기 실패"}
            
    except Exception as e:
        return {"status": "error", "message": f"Firestore 테스트 실패: {e}"} 