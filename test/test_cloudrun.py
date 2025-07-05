#!/usr/bin/env python3
"""
간단한 Greenround API 테스트 - 각 API별 폴링 테스트

사용법: python test/test_cloudrun.py
"""

import requests
import json
import time
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 설정
# SERVICE_URL = "http://localhost:8000"  # 로컬 테스트용
SERVICE_URL = "https://greenround-backend-a25b4dc3-576367655531.europe-west1.run.app"
VIDEO_FILE = "/Users/eonlee/Documents/Projects/golf-3d-analyzer/test/KakaoTalk_Video_2025-05-31-20-46-31.mp4"
# VIDEO_FILE = "/Users/eonlee/Documents/Projects/golf-3d-analyzer/test/output_video_dWiFxa67RYE.mp4"

def test_health():
    """헬스 체크 테스트"""
    print("\n🔍 헬스 체크 테스트")
    try:
        response = requests.get(f"{SERVICE_URL}/api/health", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ {data.get('message', 'OK')}")
            return True
        else:
            print(f"   ❌ 실패: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return False

def upload_file():
    """파일 업로드 테스트"""
    print("\n📤 파일 업로드 테스트")
    
    if not Path(VIDEO_FILE).exists():
        print(f"   ❌ 파일을 찾을 수 없습니다: {VIDEO_FILE}")
        return None
    
    file_size = Path(VIDEO_FILE).stat().st_size
    print(f"   파일 크기: {file_size / 1024 / 1024:.1f} MB")
    
    try:
        with open(VIDEO_FILE, "rb") as f:
            files = {"file": (Path(VIDEO_FILE).name, f, "video/quicktime")}
            headers = {'accept': 'application/json'}
            
            response = requests.post(
                f"{SERVICE_URL}/api/upload",
                files=files,
                headers=headers,
                timeout=60
            )
            
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                file_id = data["file_id"]
                print(f"   ✅ 업로드 성공: {file_id}")
                return file_id
            else:
                print(f"   ❌ 업로드 실패: {response.text}")
                return None
                
    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return None

def test_api_endpoint(name, endpoint, payload):
    """API 엔드포인트 테스트"""
    print(f"\n🎬 {name} API 테스트")
    
    try:
        response = requests.post(
            f"{SERVICE_URL}{endpoint}",
            json=payload,
            headers={'accept': 'application/json', 'Content-Type': 'application/json'},
            timeout=30
        )
        
        print(f"   Status: {response.status_code}")
        if response.status_code in [200, 202]:
            data = response.json()
            task_id = data.get("task_id")
            print(f"   ✅ 요청 성공: {task_id}")
            return task_id
        else:
            print(f"   ❌ 요청 실패: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return None

def poll_status(task_id: str, timeout: int = 1200):
    """작업 상태를 폴링하고 완료 또는 실패 시 결과를 반환합니다."""
    start_time = time.time()
    last_message = ""
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"{SERVICE_URL}/api/status/{task_id}",
                headers={'accept': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                progress = data.get("progress", 0)
                message = data.get("message", "")
                
                print(f"   📊 {status} ({progress}%) - {message}")
                
                if status == "completed":
                    print(f"   ✅ 완료!")
                    download_url = data.get("download_url")
                    if download_url:
                        print(f"   🔗 다운로드 URL: {download_url}")
                    return True, download_url
                elif status == "failed":
                    print(f"   ❌ 실패: {message}")
                    return False, None
                    
            elif response.status_code == 404:
                print(f"   ❌ 작업을 찾을 수 없음")
                return False, None
            else:
                print(f"   ⚠️  상태 확인 실패: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ 폴링 오류: {e}")
        
        # 10초 대기
        time.sleep(10)
    
    print(f"   ⏰ 타임아웃 ({timeout}초)")
    return False, None

def download_result(task_id, download_url, result_type):
    """결과 파일 다운로드"""
    print(f"\n📥 {result_type} 결과 다운로드 중...")
    
    try:
        # 다운로드 디렉토리 생성
        download_dir = Path("downloads")
        download_dir.mkdir(exist_ok=True)
        
        # 파일 확장자 결정
        if "하이라이트" in result_type:
            file_ext = ".mp4"
        elif "시퀀스" in result_type:
            file_ext = ".png"
        else:
            file_ext = ".mp4"
        
        # 파일명 생성
        filename = f"{task_id}_{result_type.replace(' ', '_')}{file_ext}"
        file_path = download_dir / filename
        
        # 다운로드 실행
        response = requests.get(download_url, timeout=60)
        
        if response.status_code == 200:
            with open(file_path, "wb") as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"   ✅ 다운로드 성공!")
            print(f"   📁 파일 경로: {file_path.absolute()}")
            print(f"   📊 파일 크기: {file_size / 1024 / 1024:.2f} MB")
            return True
        else:
            print(f"   ❌ 다운로드 실패: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ 다운로드 오류: {e}")
        return False

def main():
    print("🏌️ Greenround API 테스트 시작")
    print("=" * 50)
    
    # 1. 헬스 체크
    if not test_health():
        print("❌ 헬스 체크 실패 - 테스트 중단")
        return
    
    # 2. 파일 업로드
    file_id = upload_file()
    if not file_id:
        print("❌ 파일 업로드 실패 - 테스트 중단")
        return
    
    # 각 테스트를 독립적으로 실행
    # 3. API 테스트 목록
    apis = [
        {
            "name": "하이라이트 비디오",
            "endpoint": "/api/swingclip/highlight-video",
            "payload": {
                "file_id": file_id,
                "total_duration": 15,
                "slow_factor": 2
            }
        },
        {
            "name": "스윙 시퀀스",
            "endpoint": "/api/swingclip/swing-sequence",
            "payload": {"file_id": file_id},
        },
    ]

    results = []
    success_count = 0
    
    # 4. 각 API 테스트 및 폴링
    for api in apis:
        task_id = test_api_endpoint(api["name"], api["endpoint"], api["payload"])
        if task_id:
            success, download_url = poll_status(task_id)
            results.append((api["name"], task_id, success, download_url))
            if success:
                success_count += 1
        else:
            results.append((api["name"], None, False, None))
    
    # 5. 결과 요약
    print("\n" + "=" * 50)
    print("📊 테스트 결과 요약")
    print("=" * 50)
    
    for name, task_id, success, download_url in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"   {name}: {status}")
        if task_id:
            print(f"      Task ID: {task_id}")
    
    print(f"\n성공률: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")

    # 6. 결과 파일 다운로드
    for name, task_id, success, download_url in results:
        if success and download_url:
            download_result(task_id, download_url, name)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}") 