# Greenround - 로컬 개발 및 수동 배포 가이드 🛠️

이 문서는 로컬 환경에서 개발하고 테스트하거나, 긴급 상황 시 수동으로 배포하는 방법을 안내합니다.

## 📋 목차
1. [로컬 개발 환경 설정](#1-로컬-개발-환경-설정)
2. [로컬 서버 실행 및 테스트](#2-로컬-서버-실행-및-테스트)
3. [수동 배포 방법 (긴급 시)](#3-수동-배포-방법-긴급-시)

---

## 🏠 1. 로컬 개발 환경 설정

### 환경 변수 설정
로컬 개발을 위해 프로젝트 루트에 `.env` 파일이 필요합니다. `setup_gcp_environment.sh`를 실행했다면 자동으로 생성됩니다. 없다면 아래 내용을 참고하여 만드세요.

```bash
# .env
# Google Cloud 설정 (로컬에서는 일부만 사용됨)
GCP_PROJECT_ID=your-project-id
GCP_REGION=your-region
GCP_SERVICE_NAME=your-service-name
GCS_BUCKET_NAME=your-bucket-name
# 로컬 개발 시 GCS 연동을 위해 gcs-credentials.json 경로가 필요합니다.
GOOGLE_APPLICATION_CREDENTIALS=gcs-credentials.json

# 애플리케이션 설정
ENVIRONMENT=development
ENABLE_FIRESTORE_SYNC=true # Firestore 연동 여부
```

### Python 가상 환경 및 의존성 설치
```bash
# 가상 환경 생성 (최초 1회)
python3 -m venv venv

# 가상 환경 활성화
source venv/bin/activate

# 필수 패키지 설치
pip install -r requirements.txt
```

---

## 🚀 2. 로컬 서버 실행 및 테스트

### 스크립트로 서버 실행
프로젝트 루트에 있는 `run_backend.sh` 스크립트를 사용하여 개발 서버를 쉽게 시작할 수 있습니다. 이 스크립트는 가상 환경 활성화, 의존성 확인, 서버 실행을 자동으로 처리합니다.

```bash
# 스크립트에 실행 권한 부여 (최초 1회)
chmod +x run_backend.sh

# 스크립트 실행
./run_backend.sh
```
스크립트 내에서 `--reload` 옵션이 활성화되어 있어, 코드 변경 시 서버가 자동으로 재시작됩니다.

### 로컬 API 테스트
서버가 실행된 후, 새 터미널에서 API를 테스트할 수 있습니다.

```bash
# 헬스체크
curl http://localhost:8000/api/health

# API 문서 확인 (웹 브라우저에서 열기)
open http://localhost:8000/docs
```

---

## 🚨 3. 수동 배포 방법 (긴급 시)

GitHub Actions 자동 배포가 실패하거나 즉시 배포해야 할 때 로컬 환경에서 직접 스크립트를 실행할 수 있습니다.

### 사전 요구사항
-   Google Cloud SDK (`gcloud`) 설치 및 로그인
-   Docker 설치 및 실행
-   프로젝트 루트에 `deploy_to_gcp.sh` 스크립트 존재

### 수동 배포 절차
```bash
# 1. GCP 인증 확인
gcloud auth login
gcloud config set project your-project-id

# 2. Docker 인증
gcloud auth configure-docker your-region-docker.pkg.dev

# 3. 배포 스크립트 실행 권한 부여
chmod +x deploy_to_gcp.sh

# 4. 스크립트 실행
# 태그 없이 실행하면 latest 태그로 배포됩니다.
./deploy_to_gcp.sh

# 특정 버전 태그로 배포하려면
# ./deploy_to_gcp.sh v1.0.1
```

스크립트가 실행되면 GitHub Actions에서 수행하는 것과 동일한 절차(빌드 → 푸시 → 배포)가 로컬 컴퓨터에서 진행됩니다. 