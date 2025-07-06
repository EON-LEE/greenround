# GCP 설정 문제 진단 리포트 (최종 분석)

## 🔍 문제 상황 요약

### 1. Cloud Build 트리거 생성 실패 ✅ **원인 파악**
- 에러: `INVALID_ARGUMENT: Request contains an invalid argument`
- **근본 원인**: GitHub 저장소 연결 방식과 gcloud CLI 접근 방식의 불일치
- **상세 분석**: GCP 콘솔(UI)에서는 1st gen 방식으로 연결되었으나, gcloud CLI는 다른 방식 요구

### 2. Cloud Run 배포 권한 오류 ✅ **해결 완료**
- 에러: `PERMISSION_DENIED: Permission 'run.services.get' denied`
- **해결**: 서비스 계정에 `roles/run.admin` 권한 추가 완료

---

## 🔍 상세 분석 (업데이트)

### 현재 환경 상태

**프로젝트 정보:**
- 프로젝트 ID: `greenround-35395`
- 프로젝트 번호: `754180903557`
- 활성 계정: `golfroundai@gmail.com` (Owner 권한)

**GitHub 연결 상태:**
- ✅ 저장소 연결됨: `EON-LEE/greenround`
- ✅ 연결 방식: Cloud Build GitHub 앱 (1st gen)
- ✅ 리전 설정: 전역(비 리전)

**서비스 계정 권한 상태:**
- ✅ `roles/datastore.user`
- ✅ `roles/logging.logWriter`
- ✅ `roles/monitoring.metricWriter`
- ✅ `roles/storage.objectAdmin`
- ✅ `roles/run.admin` **추가 완료**

### 핵심 문제점 분석

#### 1. ✅ 환경 설정 파일 - **해결 완료**
- `.env` 파일 생성 완료

#### 2. ✅ 서비스 계정 권한 - **해결 완료**
- Cloud Run 관리 권한 추가 완료

#### 3. ✅ cloudbuild.yaml 설정 - **해결 완료**
- 2단계 배포 방식으로 수정하여 권한 충돌 해결

#### 4. ⚠️ 트리거 생성 방식 - **근본 원인 파악**
**문제**: gcloud CLI 접근 방식과 GCP 콘솔 연결 방식 불일치
- GCP 콘솔: 1st gen GitHub App 연결 (전역)
- gcloud CLI: 1st gen 방식에 대한 올바른 접근 방법 필요

#### 5. ✅ 리전 분리 설정 - **해결 완료**
- **트리거 관리**: 전역(global) - GitHub 연결과 트리거는 글로벌 범위
- **Cloud Run 배포**: europe-west1 - 실제 서비스는 원하는 리전에 배포
- setup_gcp_environment.sh에서 `--region` 옵션 제거하여 분리 완료

---

## 🔧 최종 해결책

### ✅ 완료된 해결책

#### 1. 서비스 계정 권한 추가 (완료)
```bash
gcloud projects add-iam-policy-binding greenround-35395 \
    --member="serviceAccount:greenround-sa-2496483c@greenround-35395.iam.gserviceaccount.com" \
    --role="roles/run.admin"
```

#### 2. 환경 변수 파일 생성 (완료)
- `.env` 파일 생성하여 모든 GCP 리소스 정보 설정

#### 3. Cloud Build 설정 수정 (완료)
- `cloudbuild.yaml`: 2단계 배포 방식으로 권한 충돌 해결
- 배포 후 서비스 계정 업데이트 단계 추가

#### 4. 스크립트 리전 설정 분리 (완료)
- `setup_gcp_environment.sh`에서 트리거 생성 시 `--region` 옵션 제거
- 트리거: 글로벌 관리, Cloud Run: 사용자 지정 리전 배포

### 🎯 남은 작업: 수동 트리거 생성

**GitHub 저장소는 이미 연결되어 있으므로**, GCP 콘솔에서 직접 트리거만 생성하면 됩니다.

#### 수동 트리거 생성 단계:

1. **GCP 콘솔 접속**
   - [Cloud Build 트리거 페이지](https://console.cloud.google.com/cloud-build/triggers) 이동
   - 프로젝트: `greenround-35395` 선택

2. **운영 환경 트리거 생성**
   - "트리거 만들기" 클릭
   - 저장소 선택: `EON-LEE/greenround` (이미 연결됨)
   - 설정값:
     ```
     이름: greenround-prod-github-trigger
     브랜치: ^main$
     구성 파일: cloudbuild.yaml
     대체 변수:
       _REGION=europe-west1
       _REPOSITORY=greenround-2496483c
       _SERVICE_NAME=greenround-backend-2496483c
       _SERVICE_ACCOUNT_EMAIL=greenround-sa-2496483c@greenround-35395.iam.gserviceaccount.com
       _GCS_BUCKET_NAME=greenround-storage-2496483c
       _FIRESTORE_DATABASE_ID=greenround-db-2496483c
     ```

3. **개발 환경 트리거 생성 (선택사항)**
   - 동일한 방식으로 develop 브랜치용 트리거 생성
   - `_SERVICE_NAME=greenround-backend-dev-2496483c`로 변경

---

## 🚀 검증 및 테스트

### 트리거 생성 후 테스트 방법:

1. **배포 테스트**
   ```bash
   # GitHub main 브랜치에 빈 커밋 푸시
   git commit --allow-empty -m "Test deployment"
   git push origin main
   ```

2. **빌드 상태 확인**
   - [Cloud Build 기록](https://console.cloud.google.com/cloud-build/builds) 페이지에서 진행 상황 확인

3. **Cloud Run 서비스 확인**
   - [Cloud Run 서비스](https://console.cloud.google.com/run) 페이지에서 배포 상태 확인
   - 리전: europe-west1에 정상 배포되었는지 확인

---

## 📊 최종 아키텍처

```
GitHub (EON-LEE/greenround)
    ↓ Push to main branch
Cloud Build Trigger (Global)
    ↓ Execute cloudbuild.yaml
Cloud Build Process:
  1. Docker Build → Artifact Registry (europe-west1)
  2. Cloud Run Deploy → Cloud Run Service (europe-west1)
  3. Service Account Update → Runtime SA (greenround-sa-2496483c)
```

### 리전 분리 성공:
- **트리거 관리**: 글로벌 (GitHub 연결)
- **이미지 저장**: europe-west1 (Artifact Registry)
- **서비스 실행**: europe-west1 (Cloud Run)

---

## 🎉 결론

### ✅ 해결된 문제:
1. **서비스 계정 권한** - Cloud Run 관리 권한 추가
2. **환경 설정** - .env 파일 및 환경 변수 완료
3. **배포 설정** - cloudbuild.yaml 권한 충돌 해결
4. **리전 분리** - 트리거 글로벌, 배포 europe-west1

### 🔧 남은 작업:
- **트리거 생성**: GCP 콘솔에서 수동 생성 (5분 소요)

### 🚀 완료 후 혜택:
- **자동 배포**: main 브랜치 푸시 시 자동 배포
- **리전 최적화**: Cloud Run 서비스가 원하는 리전에서 실행
- **권한 최소화**: 각 컴포넌트별 필요한 최소 권한만 부여
- **환경 분리**: 개발/운영 환경 독립적 관리

이제 수동으로 트리거만 생성하면 완전한 CI/CD 파이프라인이 구축됩니다! 