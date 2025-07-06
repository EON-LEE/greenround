# Greenround Backend API

[![GCP Build & Deploy](https://github.com/EON-LEE/greenround/actions/workflows/gcp-deploy.yml/badge.svg)](https://github.com/EON-LEE/greenround/actions/workflows/gcp-deploy.yml)

## 🏌️ Golf 3D Analyzer - Microservice Architecture v2.0

골프 스윙 분석을 위한 마이크로서비스 API입니다. 3D 포즈 추정, 볼 궤적 추적, 하이라이트 영상 생성 등 다양한 기능을 제공합니다.

---

## 🚀 빠른 시작

### 1단계: 초기 환경 설정

1. **설정 파일 준비**
   ```bash
   cp setup.conf.example setup.conf
   # setup.conf를 편집하여 프로젝트 설정 수정
   ```

2. **GCP 인프라 생성** (처음 한 번만)
   ```bash
   ./setup_gcp_environment.sh init
   ```

3. **GitHub 저장소 수동 연결**
   - GCP 콘솔 > Cloud Build > 트리거 > '저장소 연결'
   - GitHub에서 해당 저장소 연결

4. **CI/CD 파이프라인 완성**
   ```bash
   ./setup_gcp_environment.sh connect-github
   ```

### 2단계: 재배포 및 업데이트

기존 프로젝트에 재배포하거나 설정을 업데이트할 때:

1. **setup.conf 수정**
   ```bash
   # 기존 프로젝트 사용으로 변경
   CREATE_NEW_PROJECT=false
   PROJECT_ID="your-existing-project-id"
   
   # 기존 리소스 서픽스 지정 (중요!)
   # .env 파일에서 확인 가능 (예: greenround-backend-abc123에서 "abc123" 부분)
   EXISTING_RESOURCE_SUFFIX="abc123"
   ```

2. **업데이트 실행**
   ```bash
   # 필요한 경우 인프라 업데이트
   ./setup_gcp_environment.sh init
   
   # 트리거 재설정
   ./setup_gcp_environment.sh connect-github
   ```

### 리소스 서픽스 확인 방법

기존 배포 후 생성된 `.env` 파일에서 리소스 이름을 확인:
```bash
cat .env | grep SERVICE_NAME
# 예: GCP_SERVICE_NAME=greenround-backend-abc123
# 여기서 "abc123"이 EXISTING_RESOURCE_SUFFIX에 입력할 값
```

---

## 🚀 개발 및 배포 워크플로우

이 프로젝트는 GCP(Google Cloud Platform) 기반의 완전 자동화된 CI/CD 파이프라인을 사용합니다.

### 1. 최초 환경 설정 (2단계 프로세스)

프로젝트를 처음 설정하는 경우, 아래 절차를 따르세요.

#### 1단계: GCP 인프라 초기화

1.  **설정 파일 준비**
    - `setup.conf.example` 파일을 `setup.conf`로 복사합니다.
      ```bash
      cp setup.conf.example setup.conf
      ```
    - `setup.conf` 파일을 열고, `GITHUB_REPO_NAME`, `PROJECT_USERS` 등 자신의 환경에 맞게 값을 수정합니다.

2.  **인프라 생성 스크립트 실행**
    - 아래 명령어를 실행하여 GCP 프로젝트, 서비스 계정, GCS 버킷 등 CI/CD를 제외한 모든 기본 리소스를 생성합니다.
      ```bash
      ./setup_gcp_environment.sh init
      ```

#### 2단계: CI/CD 파이프라인 연결

1.  **GCP 콘솔에서 GitHub 저장소 수동 연결**
    - `init` 단계가 완료되면 스크립트가 안내하는 메시지를 따릅니다.
    - GCP 콘솔에 접속하여 방금 생성된 **GCP 프로젝트**와 `setup.conf`에 지정한 **GitHub 저장소**를 수동으로 연결합니다.
      - *경로: Cloud Build > 트리거 > 저장소 연결 > GitHub 선택*

2.  **CI/CD 트리거 생성 스크립트 실행**
    - 수동 연결이 완료되었으면, 아래 명령어를 실행하여 CI/CD 파이프라인을 최종적으로 활성화합니다.
      ```bash
      ./setup_gcp_environment.sh connect-github
      ```

### 2. 기능 개발 및 테스트 (개발 환경)

1.  **`develop` 브랜치 생성 및 푸시**
    - 기능 개발을 위한 `develop` 브랜치를 생성하고 GitHub에 푸시합니다.
      ```bash
      git checkout -b develop
      git push origin develop
      ```

2.  **코드 개발 및 커밋**
    - 코드를 자유롭게 수정하고 커밋합니다.

3.  **개발 환경에 자동 배포**
    - `develop` 브랜치를 GitHub에 푸시하면, Cloud Build가 이를 감지하여 **개발용 Cloud Run 서비스**에 자동으로 배포합니다.
      ```bash
      git push origin develop
      ```
    - GCP 콘솔의 Cloud Build 페이지에서 배포 진행 상황을 확인할 수 있습니다.

### 3. 운영 환경 배포

1.  **`main` 브랜치로 병합**
    - `develop` 브랜치에서의 기능 개발과 테스트가 모두 완료되면, `main` 브랜치로 코드를 병합합니다.
      ```bash
      git checkout main
      git merge develop
      ```

2.  **운영 환경에 자동 배포**
    - `main` 브랜치를 GitHub에 푸시하면, Cloud Build가 이를 감지하여 **운영용 Cloud Run 서비스**에 자동으로 배포합니다.
      ```bash
      git push origin main
      ```

---

## 🔧 기술 스택

- **Backend**: FastAPI, Python 3.9+
- **CI/CD**: Google Cloud Build, GitHub
- **Infrastructure**: Google Cloud Run, Cloud Storage, Artifact Registry, Firestore
- **AI/ML**: MediaPipe, OpenCV, PIL

---

## API 문서

배포된 서비스의 URL 뒤에 `/docs`를 붙여 Swagger UI를 확인할 수 있습니다.

- **운영 API**: `https://<prod-service-url>/docs`
- **개발 API**: `https://<dev-service-url>/docs` 