#!/usr/bin/env python3
"""
Golf 3D Analyzer 프론트엔드 실행 스크립트
"""

import sys
import os
import subprocess
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 환경 변수 설정
os.environ['PYTHONPATH'] = str(current_dir)

if __name__ == "__main__":
    frontend_app = current_dir / "frontend" / "app.py"
    
    if not frontend_app.exists():
        print(f"❌ 프론트엔드 앱을 찾을 수 없습니다: {frontend_app}")
        sys.exit(1)
    
    print("🎯 Golf 3D Analyzer 프론트엔드 시작...")
    print("🌐 웹 주소: http://localhost:8501")
    print("⚠️  백엔드 서버가 먼저 실행되어야 합니다 (python run_backend.py)")
    print("⏹️  종료하려면 Ctrl+C를 누르세요")
    
    try:
        # Streamlit 앱 실행
        cmd = [
            sys.executable, "-m", "streamlit", "run", 
            str(frontend_app),
            "--server.port=8501",
            "--server.address=0.0.0.0",
            "--browser.gatherUsageStats=false"
        ]
        
        subprocess.run(cmd, cwd=str(current_dir))
        
    except KeyboardInterrupt:
        print("\n👋 프론트엔드가 종료되었습니다.")
    except Exception as e:
        print(f"❌ 프론트엔드 시작 실패: {str(e)}")
        print("💡 Streamlit이 설치되어 있는지 확인하세요: pip install streamlit")
        sys.exit(1) 