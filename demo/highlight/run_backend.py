#!/usr/bin/env python3
"""
Golf 3D Analyzer 백엔드 서버 실행 스크립트
"""

import sys
import os
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 환경 변수 설정
os.environ['PYTHONPATH'] = str(current_dir)

if __name__ == "__main__":
    import uvicorn
    from backend.main import app
    
    print("🚀 Golf 3D Analyzer 백엔드 서버 시작...")
    print("📍 API 문서: http://localhost:8000/docs")
    print("🔗 서버 주소: http://localhost:8000")
    print("⏹️  종료하려면 Ctrl+C를 누르세요")
    
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 서버가 종료되었습니다.")
    except Exception as e:
        print(f"❌ 서버 시작 실패: {str(e)}")
        sys.exit(1) 