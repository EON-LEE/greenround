# Greenround - API 테스트 가이드 🧪

이 문서는 `test/test_cloudrun.py` 스크립트를 사용하여 배포된 API의 종단 간(E2E) 테스트를 수행하는 방법을 안내합니다. 또한 새로운 API를 개발했을 때 테스트를 추가하는 방법을 설명합니다.

## 📋 목차
1. [테스트 스크립트 개요](#1-테스트-스크립트-개요)
2. [테스트 환경 설정](#2-테스트-환경-설정)
3. [테스트 스크립트 상세 분석](#3-테스트-스크립트-상세-분석)
4. [신규 API 테스트 추가 가이드](#4-신규-api-테스트-추가-가이드)
5. [테스트 결과 확인](#5-테스트-결과-확인)

---

## 🚀 1. 테스트 스크립트 개요

### 목적
배포된 Cloud Run 서비스의 핵심 API들이 정상적으로 동작하는지, 비동기 작업이 완료되고 결과물이 생성되는지 **전체 흐름을 검증**합니다.

### 테스트 흐름
```mermaid
graph TD
    A[시작] --> B{헬스 체크};
    B -- 성공 --> C{파일 업로드};
    C -- 성공 --> D[API 요청 (병렬)];
    D --> E{작업 상태 폴링};
    E -- 완료 --> F{결과 다운로드};
    F --> G[종료];
    B -- 실패 --> G;
    C -- 실패 --> G;
```
1.  **헬스 체크**: API 서버가 살아있는지 확인합니다.
2.  **파일 업로드**: 테스트에 사용할 비디오 파일을 서버에 업로드하고 `file_id`를 받습니다.
3.  **API 요청**: 업로드된 `file_id`를 사용하여 분석 API들(하이라이트, 스윙 시퀀스 등)을 호출하고 `task_id`를 받습니다.
4.  **작업 상태 폴링**: 각 `task_id`의 상태를 주기적으로 조회하여 작업이 완료될 때까지 기다립니다.
5.  **결과 다운로드**: 작업이 성공적으로 완료되면, 결과 파일을 `downloads/` 폴더에 저장합니다.

### 실행 방법
프로젝트 루트 디렉토리에서 아래 명령어를 실행합니다.

```bash
python test/test_cloudrun.py
```

---

## ⚙️ 2. 테스트 환경 설정

### 필수 파일
테스트를 위해서는 분석할 비디오 파일이 필요합니다. `test/test_cloudrun.py` 스크립트 상단의 `VIDEO_FILE` 변수에 **로컬 비디오 파일의 절대 경로**를 설정하세요.

```python
# test/test_cloudrun.py

# ...
# ⚙️ 설정
SERVICE_URL = "https://greenround-backend-02db099e-sewc6pk6qa-ew.a.run.app"
# ❗여기에 실제 비디오 파일 경로를 입력하세요.
VIDEO_FILE = "/path/to/your/video.mp4"
# ...
```

### 환경 변수
-   `SERVICE_URL`: 테스트할 Cloud Run 서비스의 URL입니다. 필요시 이 값을 수정하여 다른 환경(e.g., 로컬, 스테이징)을 테스트할 수 있습니다.

---

## 🔬 3. 테스트 스크립트 상세 분석

-   `test_health()`: `/api/health` 엔드포인트를 호출하여 서비스의 기본 상태를 확인합니다.
-   `upload_file()`: `VIDEO_FILE`을 `/api/upload`로 전송하고, 후속 API 호출에 필요한 `file_id`를 반환합니다.
-   `test_api_endpoint()`: API의 이름, 엔드포인트 경로, 요청 본문(`payload`)을 받아 API를 호출하고 `task_id`를 반환합니다.
-   `poll_task_status()`: `/api/status/{task_id}`를 주기적으로 호출하여 작업이 `completed` 또는 `failed` 상태가 될 때까지 기다립니다.
-   `download_result()`: 작업 완료 후 받은 다운로드 URL을 통해 실제 결과 파일을 `downloads/` 폴더에 저장합니다.

---

## ✨ 4. 신규 API 테스트 추가 가이드

> **새로운 API를 개발했다면, 이 섹션만 따라해서 테스트를 쉽게 추가할 수 있습니다.**

### 1단계: `apis` 리스트에 새 API 정보 추가하기
`test/test_cloudrun.py` 파일의 `main` 함수 안에 있는 `apis` 리스트를 찾으세요. 이 리스트에 새로 개발한 API의 정보를 딕셔너리 형태로 추가합니다.

**예시**: "볼 트래킹" API를 새로 추가하는 경우

```python
# test/test_cloudrun.py

def main():
    # ... (생략) ...
    
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
            "payload": { "file_id": file_id }
        },
        # 👇 여기에 새로운 API 정보를 추가합니다.
        {
            "name": "볼 트래킹",
            "endpoint": "/api/swingclip/ball-tracking", # 👈 새 API의 엔드포인트
            "payload": {                              # 👈 새 API의 요청 본문
                "file_id": file_id,
                "show_trajectory": True
            }
        }
    ]
    
    # ... (이후 코드는 수정할 필요 없음) ...
```

-   **`"name"`**: 사람이 읽을 수 있는 테스트 이름입니다. 결과 요약에 표시됩니다.
-   **`"endpoint"`**: API의 경로입니다. (예: `/api/swingclip/new-feature`)
-   **`"payload"`**: API에 전송할 JSON 요청 본문입니다. `file_id`는 스크립트가 업로드 후 자동으로 채워주므로 그대로 사용하면 됩니다.

### 2단계: 페이로드(`payload`) 구성하기
새로운 API가 `file_id` 외에 추가적인 파라미터를 요구한다면, `"payload"` 딕셔너리에 해당 키와 값을 추가합니다. API의 Pydantic 모델을 참고하여 정확한 필드명을 사용하세요.

### 3단계: (선택) 결과 다운로드 로직 추가하기
새로운 API가 `.mp4` 또는 `.png`가 아닌 다른 형식의 결과물을 반환하는 경우, `download_result` 함수에 간단한 로직을 추가해야 합니다.

**예시**: 결과물이 `.json` 파일인 경우

```python
# test/test_cloudrun.py

def download_result(task_id, download_url, result_type):
    # ... (생략) ...
    
    # 파일 확장자 결정
    if "하이라이트" in result_type:
        file_ext = ".mp4"
    elif "시퀀스" in result_type:
        file_ext = ".png"
    # 👇 여기에 새 결과물 형식에 대한 조건을 추가합니다.
    elif "볼 트래킹" in result_type:
        file_ext = ".json"
    else:
        file_ext = ".mp4" # 기본값
        
    # ... (이후 코드는 수정할 필요 없음) ...
```

이것으로 끝입니다! 스크립트의 나머지 부분은 추가된 API를 자동으로 테스트하고, 상태를 폴링하며, 결과를 다운로드합니다.

---

## 🔍 5. 테스트 결과 확인

스크립트 실행이 완료되면 터미널에 최종 결과가 요약되어 출력됩니다.

### 성공/실패 로그
```bash
==================================================
📊 테스트 결과 요약
==================================================
   하이라이트 비디오: ✅ 성공
      Task ID: highlight_xxxxxxxx
   스윙 시퀀스: ✅ 성공
      Task ID: sequence_yyyyyyyy
   볼 트래킹: ❌ 실패
      Task ID: balltrack_zzzzzzzz

성공률: 2/3 (66.7%)
```

### 결과물 확인
테스트가 성공적으로 완료되면, 프로젝트 루트의 `downloads/` 폴더에 결과 파일들이 저장됩니다.

```
downloads/
├── highlight_xxxxxxxx_하이라이트_비디오.mp4
└── sequence_yyyyyyyy_스윙_시퀀스.png
``` 