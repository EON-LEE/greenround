# Golf 3D Analyzer - Google Cloud 초기 환경 설정 가이드 ☁️

## 📋 목차
1. [개요](#개요)
2. [사전 준비사항](#사전-준비사항)
3. [자동 설정 (권장)](#자동-설정-권장)
4. [수동 설정](#수동-설정)
5. [설정 확인](#설정-확인)
6. [문제 해결](#문제-해결)

---

## 📖 개요

Golf 3D Analyzer를 Google Cloud Platform에 배포하기 위한 **최초 1회** 환경 설정 가이드입니다.

### 🎯 설정 목표
- Google Cloud 프로젝트 준비
- 필수 API 활성화
- 서비스 계정 생성 및 권한 설정
- Docker 이미지 저장소 생성
- 파일 저장용 GCS 버킷 생성
- 로컬 환경 설정 파일 생성

### ⏰ 소요 시간
- **자동 설정**: 약 5-10분
- **수동 설정**: 약 15-20분

---

## 🔧 사전 준비사항

### 1. 필수 도구 설치

#### Google Cloud CLI 설치
```bash
# macOS (Homebrew)
brew install google-cloud-sdk

# Ubuntu/Debian
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Windows
# https://cloud.google.com/sdk/docs/install 에서 설치 프로그램 다운로드
```

#### Docker Desktop 설치
- [Docker Desktop 다운로드](https://www.docker.com/products/docker-desktop/)

### 2. Google Cloud 계정 준비

#### GCP 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. **프로젝트 ID 기록** (예: `my-golf-analyzer-project`)

#### 청구 계정 연결
- 프로젝트에 청구 계정이 연결되어 있는지 확인
- 무료 크레딧 또는 결제 정보 설정

### 3. 로컬 환경 설정

#### Google Cloud CLI 로그인
```bash
# Google 계정으로 로그인
gcloud auth login

# 프로젝트 설정 (선택사항)
gcloud config set project YOUR_PROJECT_ID

# 로그인 상태 확인
gcloud auth list
```

#### 설치 확인
```bash
# 버전 확인
gcloud --version
docker --version

# 정상 출력 예시:
# Google Cloud SDK 450.0.0
# Docker version 24.0.6
```

---

## 🚀 자동 설정 (권장)

### 1단계: 설정 스크립트 실행
```bash
# 스크립트 실행 권한 부여
chmod +x setup_gcp_environment.sh

# 대화형 설정 시작
./setup_gcp_environment.sh
```

### 2단계: 설정 정보 입력

#### 프로젝트 ID 입력
```
GCP 프로젝트 ID를 입력하세요: my-golf-analyzer-project
```

#### 리전 선택
```
사용 가능한 리전:
1. asia-northeast3 (서울)     ← 권장
2. asia-northeast1 (도쿄)
3. us-central1 (아이오와)
4. europe-west1 (벨기에)

리전을 선택하세요 (1-4, 기본값: 1): 1
```

#### 서비스 이름 설정
```
서비스 이름을 입력하세요 (기본값: golf-analyzer-backend): 
# Enter 키를 눌러 기본값 사용 권장
```

#### GCS 버킷 이름 설정
```
GCS 버킷 이름을 입력하세요 (기본값: my-golf-analyzer-project-golf-storage): 
# Enter 키를 눌러 기본값 사용 권장
```

### 3단계: 자동 설정 진행
스크립트가 자동으로 다음 작업들을 수행합니다:

1. ✅ **프로젝트 설정 확인**
2. ✅ **필수 API 활성화**
   - Artifact Registry API
   - Cloud Run API
   - Cloud Build API
   - Cloud Storage API
   - IAM API
3. ✅ **서비스 계정 생성**
   - 이름: `golf-analyzer-sa`
   - 권한: Storage Admin, Run Developer, Artifact Registry Writer
4. ✅ **서비스 계정 키 생성**
   - 파일: `gcs-credentials.json`
5. ✅ **Artifact Registry 저장소 생성**
   - 이름: `golf-analyzer`
   - 형식: Docker
6. ✅ **GCS 버킷 생성**
   - 파일 저장용 버킷
7. ✅ **환경 변수 파일 생성**
   - 파일: `.env`
8. ✅ **Docker 인증 설정**

### 4단계: 설정 완료 확인
```
==========================================
          설정 완료 요약
==========================================
프로젝트 ID: my-golf-analyzer-project
리전: asia-northeast3
서비스 이름: golf-analyzer-backend
GCS 버킷: my-golf-analyzer-project-golf-storage
서비스 계정: golf-analyzer-sa@my-golf-analyzer-project.iam.gserviceaccount.com
Artifact Registry: asia-northeast3-docker.pkg.dev/my-golf-analyzer-project/golf-analyzer

생성된 파일:
- .env (환경 변수 설정)
- gcs-credentials.json (서비스 계정 키)

다음 단계:
1. 배포 스크립트 실행: ./deploy_to_gcp.sh
2. 서비스 상태 확인: ./deploy_to_gcp.sh --status
==========================================
```

---

## ⚙️ 수동 설정

> **자동 설정이 실패했거나 세부 제어가 필요한 경우에만 사용**

### 1단계: 프로젝트 설정
```bash
# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID

# 프로젝트 확인
gcloud projects describe YOUR_PROJECT_ID
```

### 2단계: 필수 API 활성화
```bash
# 필수 API들 한 번에 활성화
gcloud services enable \
    artifactregistry.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com
```

### 3단계: 서비스 계정 생성
```bash
# 서비스 계정 생성
gcloud iam service-accounts create golf-analyzer-sa \
    --display-name="Golf Analyzer Service Account" \
    --description="Golf 3D Analyzer를 위한 서비스 계정"

# 권한 부여
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.developer"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.writer"

# 서비스 계정 키 생성
gcloud iam service-accounts keys create gcs-credentials.json \
    --iam-account=golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### 4단계: Artifact Registry 저장소 생성
```bash
# Docker 저장소 생성
gcloud artifacts repositories create golf-analyzer \
    --repository-format=docker \
    --location=asia-northeast3 \
    --description="Golf Analyzer Docker Repository"
```

### 5단계: GCS 버킷 생성
```bash
# 버킷 생성
gsutil mb -l asia-northeast3 gs://YOUR_PROJECT_ID-golf-storage

# 서비스 계정에 버킷 권한 부여
gsutil iam ch serviceAccount:golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com:objectAdmin gs://YOUR_PROJECT_ID-golf-storage
```

### 6단계: 환경 변수 파일 생성
`.env` 파일을 생성하고 다음 내용을 입력:

```bash
# Google Cloud 설정
GCP_PROJECT_ID=YOUR_PROJECT_ID
GCP_REGION=asia-northeast3
GCP_SERVICE_NAME=golf-analyzer-backend
GCP_REPOSITORY=golf-analyzer
GCS_BUCKET_NAME=YOUR_PROJECT_ID-golf-storage
GOOGLE_APPLICATION_CREDENTIALS=gcs-credentials.json

# 애플리케이션 설정
ENVIRONMENT=production
```

### 7단계: Docker 인증 설정
```bash
# Docker를 Artifact Registry에 인증
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
```

---

## ✅ 설정 확인

### 파일 확인
```bash
# 생성된 파일들 확인
ls -la .env gcs-credentials.json

# .env 파일 내용 확인
cat .env
```

### GCP 리소스 확인
```bash
# 활성화된 API 확인
gcloud services list --enabled --filter="name:(artifactregistry.googleapis.com OR run.googleapis.com OR storage.googleapis.com)"

# 서비스 계정 확인
gcloud iam service-accounts list --filter="email:golf-analyzer-sa@*"

# Artifact Registry 확인
gcloud artifacts repositories list --location=asia-northeast3

# GCS 버킷 확인
gsutil ls

# Docker 인증 확인
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin asia-northeast3-docker.pkg.dev
```

### 권한 테스트
```bash
# GCS 접근 테스트
echo "test" | gsutil cp - gs://YOUR_BUCKET_NAME/test.txt
gsutil rm gs://YOUR_BUCKET_NAME/test.txt

# Artifact Registry 접근 테스트
docker pull hello-world
docker tag hello-world asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/golf-analyzer/test
docker push asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/golf-analyzer/test
```

---

## 🔍 문제 해결

### 자주 발생하는 오류들

#### 1. "프로젝트를 찾을 수 없습니다"
```bash
# 해결 방법
gcloud projects list
gcloud config set project CORRECT_PROJECT_ID
```

#### 2. "청구 계정이 연결되지 않음"
- Google Cloud Console에서 청구 계정 연결
- 무료 크레딧 활성화 또는 결제 정보 등록

#### 3. "API가 활성화되지 않음"
```bash
# 수동으로 API 활성화
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
```

#### 4. "권한이 부족합니다"
```bash
# 계정 권한 확인
gcloud projects get-iam-policy YOUR_PROJECT_ID

# 필요시 프로젝트 소유자 권한 요청
```

#### 5. "서비스 계정 키 생성 실패"
```bash
# 기존 키 삭제 후 재생성
gcloud iam service-accounts keys list --iam-account=golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
gcloud iam service-accounts keys delete KEY_ID --iam-account=golf-analyzer-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

#### 6. "Docker 인증 실패"
```bash
# 인증 재설정
gcloud auth configure-docker asia-northeast3-docker.pkg.dev --quiet

# 또는 수동 로그인
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin asia-northeast3-docker.pkg.dev
```

### 설정 초기화
```bash
# 전체 설정 초기화 (필요시)
rm -f .env gcs-credentials.json
gcloud config unset project
```

---

## 💰 비용 관리

### 예상 비용 (월간)
- **Cloud Run**: 무료 할당량 내 사용 시 $0
- **Artifact Registry**: 0.5GB 이하 시 $0.10
- **Cloud Storage**: 5GB 이하 시 $0.10
- **총 예상 비용**: 월 $1 이하

### 비용 절약 팁
1. **Cloud Run 자동 스케일링**: 사용하지 않을 때 0개 인스턴스
2. **이미지 정리**: 오래된 Docker 이미지 주기적 삭제
3. **파일 정리**: GCS에서 오래된 파일 자동 삭제 설정
4. **청구 알람**: 예산 초과 시 알림 설정

### 청구 알람 설정
```bash
# Google Cloud Console에서 설정
# 1. 청구 → 예산 및 알림
# 2. 예산 만들기
# 3. 월 $10 예산 설정 권장
```

---

## 🔗 다음 단계

### 1. 배포 준비
설정이 완료되면 바로 배포할 수 있습니다:
```bash
# 배포 스크립트 실행
./deploy_to_gcp.sh
```

### 2. 추가 설정 (선택사항)
- **커스텀 도메인**: Cloud Run에 사용자 도메인 연결
- **HTTPS 인증서**: 자동 SSL 인증서 설정
- **모니터링**: Cloud Monitoring 알림 설정

### 3. 개발 환경 설정
- 로컬 개발: `BACKEND_DEVELOPMENT_GUIDE.md` 참조
- API 테스트: Postman, curl 등 사용

---

## 📚 참고 자료

### Google Cloud 문서
- [Cloud Run 문서](https://cloud.google.com/run/docs)
- [Artifact Registry 문서](https://cloud.google.com/artifact-registry/docs)
- [Cloud Storage 문서](https://cloud.google.com/storage/docs)
- [IAM 문서](https://cloud.google.com/iam/docs)

### 유용한 명령어
```bash
# 현재 설정 확인
gcloud config list

# 프로젝트 정보 확인
gcloud projects describe $(gcloud config get-value project)

# 청구 계정 확인
gcloud billing accounts list

# 할당량 확인
gcloud compute project-info describe --project=$(gcloud config get-value project)
```

---

**🎉 축하합니다!**

Google Cloud 환경 설정이 완료되었습니다. 이제 `./deploy_to_gcp.sh`를 실행하여 Golf 3D Analyzer를 배포할 수 있습니다!

**⚠️ 보안 주의사항**
- `gcs-credentials.json` 파일을 안전하게 보관하세요
- Git에 서비스 계정 키를 커밋하지 마세요
- 정기적으로 서비스 계정 키를 교체하세요 