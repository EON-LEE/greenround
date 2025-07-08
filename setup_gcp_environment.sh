#!/bin/bash

# =============================================================================
# Greenround - Google Cloud 환경 초기 설정 스크립트
# =============================================================================

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------------------------
# gcloud CLI 트랙 설정
# 2세대 GitHub Connection/Trigger는 현재 beta 트랙에서만 지원됩니다.
# -----------------------------------------------------------------------------
GCLOUD_BETA="gcloud beta"

# --- 기본 설정 변수 ---
# 이 변수들은 setup.conf 파일에서 오버라이드 됩니다.
CREATE_NEW_PROJECT=true
PROJECT_ID=""
REGION="asia-northeast3"
SERVICE_NAME_PREFIX="greenround-backend"
BUCKET_NAME_PREFIX="greenround-storage"
REPO_NAME_PREFIX="greenround"
SOURCE_REPO_NAME_PREFIX="greenround-source"
PROJECT_USERS=(
    "everydaystudy@gmail.com"
    "entjqvv@gmail.com"
)

# --- GitHub 연동 설정 ---
# Cloud Build 앱과 연동된 GitHub 저장소 이름
# (예: "your-github-username/your-repo-name")
GITHUB_REPO_NAME="EON-LEE/greenround"

# 2세대 Cloud Build Connection 이름 (콘솔에서 만든 이름과 동일)
# (예: "github-conn")
GITHUB_CONNECTION_NAME="github-conn"

# --- 권한 설정 (분리) ---
# 1. 'setup_gcp_environment.sh'를 실행하는 관리자에게 부여될 권한
# 프로젝트 생성, API 활성화, 서비스 계정 관리 등 강력한 권한이 필요합니다.
ADMIN_ROLES=(
    "roles/storage.admin"
    "roles/run.admin"
    "roles/artifactregistry.admin"
    "roles/datastore.user"
    "roles/serviceusage.serviceUsageAdmin"
    "roles/compute.admin"
    "roles/cloudbuild.builds.editor"
    "roles/iam.serviceAccountAdmin" # 서비스 계정 생성/관리 권한
    "roles/resourcemanager.projectIamAdmin" # 프로젝트 IAM 정책 관리 권한
    "roles/logging.admin"
    "roles/monitoring.admin"
)

# 2. Cloud Run 서비스가 런타임에 사용할 서비스 계정에게 부여될 최소 권한
# 애플리케이션 실행에 꼭 필요한 권한만 포함합니다. (최소 권한 원칙)
RUNTIME_SERVICE_ACCOUNT_ROLES=(
    "roles/storage.objectAdmin"       # GCS 버킷의 객체(파일)만 관리
    "roles/datastore.user"            # Firestore 데이터베이스 읽기/쓰기
    "roles/logging.logWriter"         # 로그 작성
    "roles/monitoring.metricWriter"   # 모니터링 메트릭 작성
    "roles/cloudbuild.builds.editor"  # Cloud Build 트리거 생성/수정 권한
    "roles/source.admin"              # Source Repository 관리 권한 (GitHub 연결용)
    "roles/secretmanager.admin"       # Secret Manager 접근 권한 (GitHub 토큰용)
    "roles/run.admin"                 # Cloud Run 서비스 배포/관리 권한
    "roles/artifactregistry.writer"   # Artifact Registry 이미지 푸시 권한
    "roles/iam.serviceAccountUser"    # 다른 서비스 계정 사용 권한 (actAs)
)

# 설정 파일 로드
load_config() {
    if [ -f "setup.conf" ]; then
        log_info "설정 파일(setup.conf)을 로드합니다..."
        source setup.conf
        log_success "설정 파일 로드 완료."
    else
        log_error "설정 파일(setup.conf)을 찾을 수 없습니다."
        log_info "setup.conf.example 파일을 setup.conf로 복사한 후, 내용을 수정하여 다시 실행해주세요."
        log_info "예: cp setup.conf.example setup.conf"
        exit 1
    fi
}

# 변수 초기화 및 구성
initialize_variables() {
    log_info "설정 변수를 기반으로 리소스 이름을 구성합니다..."
    
    # 새 프로젝트 생성 시
    if [ "$CREATE_NEW_PROJECT" = "true" ]; then
        PROJECT_SUFFIX=$(date +%s | tail -c 6)
        PROJECT_ID="greenround-${PROJECT_SUFFIX}"
        log_info "새 프로젝트 ID 자동 생성: $PROJECT_ID"
        
        # 새 프로젝트이므로 새로운 리소스 서픽스 생성
        RESOURCE_SUFFIX=$(openssl rand -hex 4 2>/dev/null || echo $(date +%s | tail -c 8))
        log_info "새 리소스 서픽스 생성: $RESOURCE_SUFFIX"
    else
        if [ -z "$PROJECT_ID" ]; then
            log_error "CREATE_NEW_PROJECT=false로 설정한 경우, PROJECT_ID를 반드시 지정해야 합니다."
            exit 1
        fi
        log_info "기존 프로젝트 ID 사용: $PROJECT_ID"
        
        # 기존 프로젝트이므로 기존 리소스 서픽스 사용
        if [ -n "$EXISTING_RESOURCE_SUFFIX" ]; then
            RESOURCE_SUFFIX="$EXISTING_RESOURCE_SUFFIX"
            log_info "기존 리소스 서픽스 사용: $RESOURCE_SUFFIX"
        else
            log_warning "EXISTING_RESOURCE_SUFFIX가 설정되지 않았습니다. 새로운 서픽스를 생성합니다."
            RESOURCE_SUFFIX=$(openssl rand -hex 4 2>/dev/null || echo $(date +%s | tail -c 8))
            log_info "새 리소스 서픽스 생성: $RESOURCE_SUFFIX"
        fi
    fi
    
    # 전체 리소스 이름 구성
    SERVICE_NAME="${SERVICE_NAME_PREFIX}-${RESOURCE_SUFFIX}"
    DEV_SERVICE_NAME="${SERVICE_NAME_PREFIX}-dev-${RESOURCE_SUFFIX}" # 개발 환경용 서비스 이름
    BUCKET_NAME="${BUCKET_NAME_PREFIX}-${RESOURCE_SUFFIX}"
    REPO_NAME="${REPO_NAME_PREFIX}-${RESOURCE_SUFFIX}"
    SOURCE_REPO_NAME="${SOURCE_REPO_NAME_PREFIX}-${RESOURCE_SUFFIX}"
    FIRESTORE_DATABASE_ID="greenround-db-${RESOURCE_SUFFIX}"
    SA_NAME="greenround-sa-${RESOURCE_SUFFIX}"
    SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
    
    log_success "리소스 이름 구성 완료."
    log_info "서비스 이름: $SERVICE_NAME"
    log_info "개발 서비스 이름: $DEV_SERVICE_NAME"
    log_info "버킷 이름: $BUCKET_NAME"
    log_info "서비스 계정: $SA_EMAIL"
}

# 새 프로젝트 생성 (선택적)
create_new_project() {
    if [ "$CREATE_NEW_PROJECT" = "true" ]; then
        log_info "새 GCP 프로젝트 생성 중: $PROJECT_ID"
        
        # 프로젝트 생성
        if gcloud projects create "$PROJECT_ID" --name="Greenround Backend" 2>/dev/null; then
            log_success "새 프로젝트가 생성되었습니다: $PROJECT_ID"
        else
            log_warning "프로젝트 생성 실패 또는 이미 존재함. 기존 프로젝트 사용을 시도합니다."
        fi
        
        # 결제 계정 자동 연결
        log_info "프로젝트에 결제 계정을 연결합니다..."
        
        # 사용 가능한 결제 계정 조회
        BILLING_ACCOUNTS=$(gcloud billing accounts list --format="value(name)" --filter="open=true" 2>/dev/null || echo "")
        
        if [ -z "$BILLING_ACCOUNTS" ]; then
            log_warning "사용 가능한 결제 계정을 찾을 수 없습니다."
            log_info "Google Cloud Console에서 결제 계정을 연결하거나, 다음 명령어를 사용하세요:"
            log_info "gcloud billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID"
            echo ""
            read -p "결제 계정 연결을 완료했다면 Enter를 눌러 계속하세요..."
        else
            # 결제 계정이 하나만 있는 경우 자동 연결
            BILLING_COUNT=$(echo "$BILLING_ACCOUNTS" | wc -l)
            
            if [ "$BILLING_COUNT" -eq 1 ]; then
                BILLING_ACCOUNT_ID=$(echo "$BILLING_ACCOUNTS" | head -1)
                log_info "결제 계정 자동 연결 중: $BILLING_ACCOUNT_ID"
                
                if gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID" 2>/dev/null; then
                    log_success "결제 계정이 자동으로 연결되었습니다: $BILLING_ACCOUNT_ID"
                else
                    log_warning "자동 연결 실패. 수동으로 연결해주세요."
                    echo ""
                    read -p "결제 계정 연결을 완료했다면 Enter를 눌러 계속하세요..."
                fi
            else
                # 여러 결제 계정이 있는 경우 선택
                log_info "사용 가능한 결제 계정들:"
                echo "$BILLING_ACCOUNTS" | nl -w2 -s'. '
                echo ""
                read -p "사용할 결제 계정 번호를 선택하세요 (1-$BILLING_COUNT): " BILLING_CHOICE
                
                if [[ "$BILLING_CHOICE" =~ ^[0-9]+$ ]] && [ "$BILLING_CHOICE" -ge 1 ] && [ "$BILLING_CHOICE" -le "$BILLING_COUNT" ]; then
                    SELECTED_BILLING_ACCOUNT=$(echo "$BILLING_ACCOUNTS" | sed -n "${BILLING_CHOICE}p")
                    log_info "선택된 결제 계정으로 연결 중: $SELECTED_BILLING_ACCOUNT"
                    
                    if gcloud billing projects link "$PROJECT_ID" --billing-account="$SELECTED_BILLING_ACCOUNT" 2>/dev/null; then
                        log_success "결제 계정이 연결되었습니다: $SELECTED_BILLING_ACCOUNT"
                    else
                        log_error "결제 계정 연결에 실패했습니다."
                        exit 1
                    fi
                else
                    log_error "잘못된 선택입니다."
                    exit 1
                fi
            fi
        fi
    fi
}

# 프로젝트 설정
setup_project() {
    log_info "프로젝트 설정 중..."
    
    # 프로젝트 존재 확인
    if ! gcloud projects describe "$PROJECT_ID" &> /dev/null; then
        log_error "프로젝트 '$PROJECT_ID'를 찾을 수 없습니다."
        if [ "$CREATE_NEW_PROJECT" = "true" ]; then
            log_error "새 프로젝트 생성에 실패했습니다."
        else
            log_info "올바른 프로젝트 ID를 입력했는지 확인하세요."
        fi
        exit 1
    fi
    
    # 프로젝트 설정
    gcloud config set project "$PROJECT_ID"
    log_success "프로젝트가 설정되었습니다: $PROJECT_ID"
}

# 필수 API 활성화
enable_required_apis() {
    log_info "필수 API 활성화 중..."
    
    apis=(
        "artifactregistry.googleapis.com"
        "run.googleapis.com"
        "cloudbuild.googleapis.com"
        "storage.googleapis.com"
        "iam.googleapis.com"
        "firestore.googleapis.com"
        "compute.googleapis.com"
        "secretmanager.googleapis.com"
    )
    
    for api in "${apis[@]}"; do
        log_info "API 활성화: $api"
        gcloud services enable "$api" --project="$PROJECT_ID"
    done
    
    log_success "모든 API가 활성화되었습니다."
}

# 서비스 계정 생성
create_service_account() {
    log_info "서비스 계정 생성 중..."
    
    # 서비스 계정이 이미 존재하는지 확인
    if gcloud iam service-accounts describe "$SA_EMAIL" &> /dev/null; then
        log_warning "서비스 계정이 이미 존재합니다: $SA_EMAIL"
    else
        gcloud iam service-accounts create "$SA_NAME" \
            --display-name="greenround Service Account" \
            --description="greenround를 위한 서비스 계정"
        log_success "서비스 계정이 생성되었습니다: $SA_EMAIL"
    fi
    
    # 권한 부여 (런타임 서비스 계정에게는 최소 권한 부여)
    log_info "서비스 계정에 최소 실행 권한 부여 중..."
    for role in "${RUNTIME_SERVICE_ACCOUNT_ROLES[@]}"; do
        log_info "권한 부여: $role"
        # 기존 바인딩 확인 후 추가
        if ! gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:serviceAccount:$SA_EMAIL AND bindings.role:$role" | grep -q "$role"; then
            gcloud projects add-iam-policy-binding "$PROJECT_ID" \
                --member="serviceAccount:$SA_EMAIL" \
                --role="$role"
            log_success "권한 부여 완료: $role"
        else
            log_warning "권한이 이미 존재함: $role"
        fi
    done
    
    # 서비스 계정 키 생성 (로컬 개발용)
    if [ -f "gcs-credentials.json" ]; then
        log_warning "기존 서비스 계정 키 파일이 존재합니다."
        echo "기존 파일: $(grep -o '"project_id": "[^"]*"' gcs-credentials.json 2>/dev/null || echo '정보 없음')"
        echo "새 프로젝트: $PROJECT_ID"
        echo ""
        read -p "새 서비스 계정 키를 생성하시겠습니까? 기존 파일은 백업됩니다. (y/N): " replace_key
        
        if [[ "$replace_key" =~ ^[Yy]$ ]]; then
            mv gcs-credentials.json "gcs-credentials.json.backup.$(date +%Y%m%d_%H%M%S)"
            log_info "기존 파일을 백업했습니다."
        else
            log_warning "기존 서비스 계정 키를 유지합니다. 프로젝트가 다를 경우 인증 오류가 발생할 수 있습니다."
            return
        fi
    fi
    
    log_info "새 서비스 계정 키 생성 중..."
    gcloud iam service-accounts keys create gcs-credentials.json \
        --iam-account="$SA_EMAIL"
    log_success "서비스 계정 키가 생성되었습니다: gcs-credentials.json"

    # Cloud Build 서비스 계정에 이 서비스 계정을 사용할 수 있는 권한 부여
    log_info "Cloud Build 서비스 계정에 방금 만든 서비스 계정을 사용할 권한을 부여합니다..."
    # API 활성화 후 서비스 계정 생성까지 시간이 걸릴 수 있어 잠시 대기
    sleep 10
    PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
    CB_SA_EMAIL="$PROJECT_NUMBER@cloudbuild.gserviceaccount.com"
    
    # Cloud Build 서비스 계정에 필요한 권한들 부여
    log_info "Cloud Build 서비스 계정에 필요한 권한들을 부여합니다..."
    
    # 1. 우리가 생성한 서비스 계정을 사용할 수 있는 권한
    gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
        --member="serviceAccount:$CB_SA_EMAIL" \
        --role="roles/iam.serviceAccountUser" \
        --project="$PROJECT_ID" > /dev/null 2>&1 || log_warning "Cloud Build 서비스 계정에 serviceAccountUser 권한 부여를 실패했을 수 있습니다."
    
    # 2. Cloud Build 서비스 계정에 Cloud Run 배포 권한 부여
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$CB_SA_EMAIL" \
        --role="roles/run.admin" > /dev/null 2>&1 || log_warning "Cloud Build 서비스 계정에 run.admin 권한 부여를 실패했을 수 있습니다."
    
    # 3. Cloud Build 서비스 계정에 서비스 계정 사용 권한 부여
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$CB_SA_EMAIL" \
        --role="roles/iam.serviceAccountUser" > /dev/null 2>&1 || log_warning "Cloud Build 서비스 계정에 프로젝트 레벨 serviceAccountUser 권한 부여를 실패했을 수 있습니다."
    
    # 4. Cloud Build 서비스 계정에 Artifact Registry Writer 권한 부여 (Docker 이미지 푸시용)
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$CB_SA_EMAIL" \
        --role="roles/artifactregistry.writer" > /dev/null 2>&1 || log_warning "Cloud Build 서비스 계정에 artifactregistry.writer 권한 부여를 실패했을 수 있습니다."
    
    log_success "Cloud Build 서비스 계정에 필요한 권한들이 부여되었습니다."
}

# Artifact Registry 저장소 생성
create_artifact_repository() {
    log_info "Artifact Registry 저장소 생성 중..."
    
    if gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" &> /dev/null; then
        log_warning "Artifact Registry 저장소가 이미 존재합니다."
    else
        gcloud artifacts repositories create "$REPO_NAME" \
            --repository-format=docker \
            --location="$REGION" \
            --description="Greenround Docker Repository"
        log_success "Artifact Registry 저장소가 생성되었습니다."
    fi
}

# Cloud Build Triggers 생성 (운영/개발 for GitHub) - 1세대 방식 사용
create_cloud_build_triggers() {
    log_info "Cloud Build Trigger 생성 중 (GitHub 연동 - 1세대 방식)..."
    
    # GitHub 레포지토리 이름 분리
    GITHUB_REPO_OWNER=$(echo "$GITHUB_REPO_NAME" | cut -d'/' -f1)
    GITHUB_REPO_NAME_ONLY=$(echo "$GITHUB_REPO_NAME" | cut -d'/' -f2)
    
    log_info "GitHub 저장소: $GITHUB_REPO_OWNER/$GITHUB_REPO_NAME_ONLY"

    if [ -z "$GITHUB_REPO_OWNER" ] || [ -z "$GITHUB_REPO_NAME_ONLY" ]; then
        log_error "GITHUB_REPO_NAME 형식이 잘못되었습니다. 'owner/repo-name' 형식이어야 합니다."
        exit 1
    fi

    # 1. 운영(Production) 트리거 for 'main' branch - 1세대 방식
    PROD_TRIGGER_NAME="greenround-prod-github-trigger"
    if $GCLOUD_BETA builds triggers describe "$PROD_TRIGGER_NAME" --region="$REGION" &> /dev/null; then
        log_warning "운영 트리거 '$PROD_TRIGGER_NAME'가 이미 존재합니다."
    else
        log_info "운영(main 브랜치) 트리거 생성 중 (1세대 방식)..."
        
        log_info "실행할 명령어:"
        log_info "gcloud beta builds triggers create github \\"
        log_info "  --name=\"$PROD_TRIGGER_NAME\" \\"
        log_info "  --region=\"$REGION\" \\"
        log_info "  --repo-name=\"$GITHUB_REPO_NAME_ONLY\" \\"
        log_info "  --repo-owner=\"$GITHUB_REPO_OWNER\" \\"
        log_info "  --branch-pattern=\"^main$\" \\"
        log_info "  --build-config=\"cloudbuild.yaml\" \\"
        log_info "  --service-account=\"projects/$PROJECT_ID/serviceAccounts/$SA_EMAIL\" \\"
        log_info "  --substitutions=\"_REGION=$REGION,_REPOSITORY=$REPO_NAME,_SERVICE_NAME=$SERVICE_NAME,_SERVICE_ACCOUNT_EMAIL=$SA_EMAIL,_GCS_BUCKET_NAME=$BUCKET_NAME,_FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID\""
        
        $GCLOUD_BETA builds triggers create github \
            --name="$PROD_TRIGGER_NAME" \
            --region="$REGION" \
            --repo-name="$GITHUB_REPO_NAME_ONLY" \
            --repo-owner="$GITHUB_REPO_OWNER" \
            --branch-pattern="^main$" \
            --build-config="cloudbuild.yaml" \
            --service-account="projects/$PROJECT_ID/serviceAccounts/$SA_EMAIL" \
            --substitutions="_REGION=$REGION,_REPOSITORY=$REPO_NAME,_SERVICE_NAME=$SERVICE_NAME,_SERVICE_ACCOUNT_EMAIL=$SA_EMAIL,_GCS_BUCKET_NAME=$BUCKET_NAME,_FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID" \
            --description="Deploy main branch using 1st gen trigger"
        log_success "운영 트리거가 생성되었습니다 (1세대 방식). GitHub의 'main' 브랜치에 push하면 운영 환경에 배포됩니다."
    fi

    # 2. 개발(Development) 트리거 for 'develop' branch - 1세대 방식
    DEV_TRIGGER_NAME="greenround-dev-github-trigger"
    if $GCLOUD_BETA builds triggers describe "$DEV_TRIGGER_NAME" --region="$REGION" &> /dev/null; then
        log_warning "개발 트리거 '$DEV_TRIGGER_NAME'가 이미 존재합니다."
    else
        log_info "개발(develop 브랜치) 트리거 생성 중 (1세대 방식)..."
        $GCLOUD_BETA builds triggers create github \
            --name="$DEV_TRIGGER_NAME" \
            --region="$REGION" \
            --repo-name="$GITHUB_REPO_NAME_ONLY" \
            --repo-owner="$GITHUB_REPO_OWNER" \
            --branch-pattern="^develop$" \
            --build-config="cloudbuild.yaml" \
            --service-account="projects/$PROJECT_ID/serviceAccounts/$SA_EMAIL" \
            --substitutions="_REGION=$REGION,_REPOSITORY=$REPO_NAME,_SERVICE_NAME=$DEV_SERVICE_NAME,_SERVICE_ACCOUNT_EMAIL=$SA_EMAIL,_GCS_BUCKET_NAME=$BUCKET_NAME,_FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID" \
            --description="Deploy develop branch using 1st gen trigger"
        log_success "개발 트리거가 생성되었습니다 (1세대 방식). GitHub의 'develop' 브랜치에 push하면 개발 환경에 배포됩니다."
    fi
}

# GCS 버킷 생성
create_storage_bucket() {
    log_info "Google Cloud Storage 버킷 생성 중..."
    
    if gsutil ls "gs://$BUCKET_NAME" &> /dev/null; then
        log_warning "GCS 버킷이 이미 존재합니다: $BUCKET_NAME"
    else
        gsutil mb -l "$REGION" "gs://$BUCKET_NAME"
        log_success "GCS 버킷이 생성되었습니다: $BUCKET_NAME"
    fi
    
    # 버킷 권한 설정
    gsutil iam ch "serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com:objectAdmin" "gs://$BUCKET_NAME"
}

# 환경 변수 파일 생성
create_env_file() {
    log_info "환경 변수 파일 생성 중..."
    
    cat > .env << EOF
# =============================================================================
# Greenround 환경 변수 설정 파일
# =============================================================================
# 이 파일은 로컬 개발용이며, CI/CD 파이프라인에도 일부 변수가 사용됩니다.
# setup_gcp_environment.sh 스크립트에 의해 자동으로 생성됩니다.

# --- GCP 리소스 정보 ---
GCP_PROJECT_ID=$PROJECT_ID
GCP_REGION=$REGION
GCP_SA_EMAIL=$SA_EMAIL

# 운영(Production) 환경
GCP_SERVICE_NAME=$SERVICE_NAME

# 개발(Development) 환경
GCP_DEV_SERVICE_NAME=$DEV_SERVICE_NAME

# 공용 리소스
GCP_REPOSITORY=$REPO_NAME
GCS_BUCKET_NAME=$BUCKET_NAME
FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID

# --- 로컬 개발용 ---
# 이 파일은 로컬에서만 사용되며, Git에 포함되어서는 안 됩니다.
GOOGLE_APPLICATION_CREDENTIALS=gcs-credentials.json
EOF
    
    log_success "환경 변수 파일이 생성되었습니다: .env"
}

# Firestore 데이터베이스 설정
setup_firestore() {
    log_info "Firestore 데이터베이스 설정 중..."
    
    # Firestore 데이터베이스 생성 (Native 모드, 고유 ID 지정)
    if ! gcloud firestore databases describe --database="$FIRESTORE_DATABASE_ID" --location="$REGION" &> /dev/null; then
        log_info "Firestore 데이터베이스 생성 중: $FIRESTORE_DATABASE_ID"
        gcloud firestore databases create \
            --database="$FIRESTORE_DATABASE_ID" \
            --location="$REGION" \
            --type=firestore-native
        log_success "Firestore 데이터베이스가 생성되었습니다: $FIRESTORE_DATABASE_ID"
    else
        log_success "Firestore 데이터베이스가 이미 존재합니다: $FIRESTORE_DATABASE_ID"
    fi
}

# Docker 인증 설정
setup_docker_auth() {
    log_info "Docker 인증 설정 중..."
    gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
    log_success "Docker 인증이 설정되었습니다."
}

#
# 사용자 추가 함수 (입력 없이 배열 순회)
add_users_to_project() {
    log_info "GCP 프로젝트에 여러 사용자 추가 중..."
    if [ ${#PROJECT_USERS[@]} -eq 0 ]; then
        log_warning "추가할 사용자가 없습니다."
        return
    fi

    # 사용자에게는 관리자급 권한 부여
    for NEW_USER_EMAIL in "${PROJECT_USERS[@]}"; do
        log_info "사용자 추가: $NEW_USER_EMAIL"
        for role in "${ADMIN_ROLES[@]}"; do
            log_info "  권한 부여: $role"
            if ! gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --format="table(bindings.role)" --filter="bindings.members:user:$NEW_USER_EMAIL AND bindings.role:$role" | grep -q "$role"; then
                gcloud projects add-iam-policy-binding "$PROJECT_ID" \
                    --member="user:$NEW_USER_EMAIL" \
                    --role="$role" \
                    --condition=None 2>/dev/null || \
                gcloud projects add-iam-policy-binding "$PROJECT_ID" \
                    --member="user:$NEW_USER_EMAIL" \
                    --role="$role"
                log_success "  권한 부여 완료: $role"
            else
                log_warning "  이미 권한이 존재함: $role"
            fi
        done
        log_success "사용자 추가 및 권한 부여 완료: $NEW_USER_EMAIL"
    done
}

# 설정 요약 출력 (1단계: init)
print_init_summary() {
    echo ""
    echo "=========================================="
    echo "  ✅ 1단계: GCP 인프라 초기화 완료"
    echo "=========================================="
    echo "프로젝트 ID: $PROJECT_ID"
    echo "리전: $REGION"
    echo "운영 서비스 이름: $SERVICE_NAME"
    echo "개발 서비스 이름: $DEV_SERVICE_NAME"
    echo "GCS 버킷: $BUCKET_NAME"
    echo "서비스 계정: $SA_EMAIL"
    echo "Artifact Registry: $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME"
    echo ""
    echo "생성된 파일:"
    echo "- .env (자동 생성된 환경 변수)"
    echo "- gcs-credentials.json (로컬 개발용 서비스 계정 키)"
    echo ""
    echo "------------------------------------------"
    echo "  下一步: 手动操作"
    echo "------------------------------------------"
    echo "이제 GCP 콘솔에서 GitHub 저장소를 수동으로 연결해야 합니다."
    echo ""
    echo "1. GCP 콘솔에 접속하여 '$PROJECT_ID' 프로젝트를 선택하세요."
    echo "2. 'Cloud Build' > '트리거' 메뉴로 이동하세요."
    echo "3. 상단의 '저장소 연결'을 클릭하고 'GitHub'를 선택하여,"
    echo "   '$GITHUB_REPO_NAME' 저장소를 이 프로젝트에 연결하세요."
    echo ""
    echo "------------------------------------------"
    echo "  最終段階: CI/CD トリガーの接続"
    echo "------------------------------------------"
    echo "수동 연결이 완료되었으면, 아래 명령어를 실행하여 CI/CD 파이프라인을 최종 완성하세요."
    echo ""
    echo "  ./setup_gcp_environment.sh connect-github"
    echo ""
    echo "=========================================="
}

# 리소스 정리 함수
cleanup_resources() {
    log_warning "⚠️  리소스 정리를 시작합니다. 이 작업은 되돌릴 수 없습니다!"
    echo ""
    echo "정리될 리소스들:"
    echo "- Cloud Build 트리거"
    echo "- Cloud Run 서비스"
    echo "- Artifact Registry 저장소"
    echo "- GCS 버킷 (모든 파일 포함)"
    echo "- 서비스 계정"
    echo "- 로컬 인증 파일들"
    echo ""
    echo "⚠️  주의: Firestore 데이터베이스는 콘솔에서 수동으로 삭제해야 합니다."
    echo ""
    read -p "정말로 모든 리소스를 삭제하시겠습니까? (DELETE 입력): " confirm
    
    if [ "$confirm" != "DELETE" ]; then
        log_info "리소스 정리가 취소되었습니다."
        return
    fi
    
    log_info "리소스 정리 시작..."
    
    # Cloud Build 트리거 삭제
    log_info "Cloud Build 트리거 삭제 중..."
    PROD_TRIGGER_NAME="greenround-prod-github-trigger"
    DEV_TRIGGER_NAME="greenround-dev-github-trigger"
    
    if $GCLOUD_BETA builds triggers describe "$PROD_TRIGGER_NAME" --region="$REGION" &> /dev/null; then
        $GCLOUD_BETA builds triggers delete "$PROD_TRIGGER_NAME" --region="$REGION" --quiet
        log_success "운영 트리거 삭제 완료: $PROD_TRIGGER_NAME"
    fi
    
    if $GCLOUD_BETA builds triggers describe "$DEV_TRIGGER_NAME" --region="$REGION" &> /dev/null; then
        $GCLOUD_BETA builds triggers delete "$DEV_TRIGGER_NAME" --region="$REGION" --quiet
        log_success "개발 트리거 삭제 완료: $DEV_TRIGGER_NAME"
    fi
    
    # Cloud Run 서비스 삭제
    log_info "Cloud Run 서비스 삭제 중..."
    if gcloud run services describe "$SERVICE_NAME" --region="$REGION" &> /dev/null; then
        gcloud run services delete "$SERVICE_NAME" --region="$REGION" --quiet
        log_success "운영 서비스 삭제 완료: $SERVICE_NAME"
    fi
    
    if gcloud run services describe "$DEV_SERVICE_NAME" --region="$REGION" &> /dev/null; then
        gcloud run services delete "$DEV_SERVICE_NAME" --region="$REGION" --quiet
        log_success "개발 서비스 삭제 완료: $DEV_SERVICE_NAME"
    fi
    
    # Artifact Registry 저장소 삭제
    log_info "Artifact Registry 저장소 삭제 중..."
    if gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" &> /dev/null; then
        gcloud artifacts repositories delete "$REPO_NAME" --location="$REGION" --quiet
        log_success "Artifact Registry 삭제 완료: $REPO_NAME"
    fi
    
    # GCS 버킷 삭제
    log_info "GCS 버킷 삭제 중..."
    if gsutil ls "gs://$BUCKET_NAME" &> /dev/null; then
        gsutil rm -r "gs://$BUCKET_NAME"
        log_success "GCS 버킷 삭제 완료: $BUCKET_NAME"
    fi
    
    # 서비스 계정 삭제
    log_info "서비스 계정 삭제 중..."
    if gcloud iam service-accounts describe "$SA_EMAIL" &> /dev/null; then
        gcloud iam service-accounts delete "$SA_EMAIL" --quiet
        log_success "서비스 계정 삭제 완료: $SA_EMAIL"
    fi
    
    # 로컬 파일 정리
    log_info "로컬 인증 파일 정리 중..."
    if [ -f ".env" ]; then
        rm .env
        log_success ".env 파일 삭제 완료"
    fi
    
    if [ -f "gcs-credentials.json" ]; then
        rm gcs-credentials.json
        log_success "gcs-credentials.json 파일 삭제 완료"
    fi
    
    # 백업 파일들도 정리
    if ls gcs-credentials.json.backup.* &> /dev/null; then
        rm gcs-credentials.json.backup.*
        log_success "백업 파일들 정리 완료"
    fi
    
    log_success "🎉 모든 리소스가 정리되었습니다!"
    echo ""
    echo "=========================================="
    echo "  정리 완료 - 다음 단계"
    echo "=========================================="
    echo "1. Firestore 데이터베이스는 GCP 콘솔에서 수동으로 삭제하세요:"
    echo "   https://console.cloud.google.com/firestore/databases?project=$PROJECT_ID"
    echo ""
    echo "2. 새로운 환경을 생성하려면 아래 명령을 실행하세요:"
    echo "   ./setup_gcp_environment.sh init"
    echo "=========================================="
}

# 최종 요약 출력 (2단계: connect-github)
print_final_summary() {
    echo ""
    echo "=========================================="
    echo "    🎉 모든 환경 설정 완료! 🎉"
    echo "=========================================="
    echo "프로젝트 '$GCP_PROJECT_ID'에 CI/CD 파이프라인 구성이 완료되었습니다."
    echo ""
    echo "이제부터 아래 워크플로우로 개발 및 배포를 진행하세요."
    echo ""
    echo "1. GitHub 'develop' 브랜치에서 기능 개발을 진행하고 푸시하여 개발 환경에 배포/테스트합니다."
    echo "   (git checkout -b develop && git push origin develop)"
    echo "2. 개발이 완료되면 'main' 브랜치에 머지하고 푸시하여 운영 환경에 배포합니다."
    echo "   (git checkout main && git merge develop && git push origin main)"
    echo "3. GCP 콘솔의 Cloud Build 페이지에서 각 환경의 배포 진행 상황을 확인하세요."
    echo "=========================================="
}

# 메인 함수
main() {
    COMMAND=$1
    shift || true # $1을 제거하여 나머지 인자를 사용 가능하게 함

    case "$COMMAND" in
        init|"")
            # 1단계: 인프라 초기화
            log_info "=== 1단계: GCP 인프라 초기화 시작 ==="
            load_config
            initialize_variables
            
            create_new_project
            setup_project
            enable_required_apis
            create_service_account
            create_artifact_repository
            create_storage_bucket
            setup_firestore
            create_env_file
            setup_docker_auth
            add_users_to_project

            print_init_summary
            log_success "1단계가 성공적으로 완료되었습니다."
            ;;

        connect-github)
            # 2단계: GitHub 트리거 연결
            log_info "=== 2단계: GitHub 트리거 연결 시작 ==="
            
            # .env와 setup.conf 파일에서 변수 로드
            if [ ! -f ".env" ] || [ ! -f "setup.conf" ]; then
                log_error ".env 또는 setup.conf 파일을 찾을 수 없습니다."
                log_error "'./setup_gcp_environment.sh init'을 먼저 실행하여 환경을 초기화하세요."
                exit 1
            fi
            source .env
            source setup.conf
            
            # 로드된 변수들을 스크립트 내부 변수로 재할당
            PROJECT_ID=$GCP_PROJECT_ID
            REGION=$GCP_REGION
            SA_EMAIL=$GCP_SA_EMAIL
            SERVICE_NAME=$GCP_SERVICE_NAME
            DEV_SERVICE_NAME=$GCP_DEV_SERVICE_NAME
            REPO_NAME=$GCP_REPOSITORY
            BUCKET_NAME=$GCS_BUCKET_NAME
            FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID
            
            setup_project # gcloud config set project
            create_cloud_build_triggers
            
            print_final_summary
            log_success "2단계가 성공적으로 완료되었습니다. 이제 자동 배포가 활성화되었습니다."
            ;;

        cleanup)
            # 3단계: 리소스 정리
            log_info "=== 리소스 정리 시작 ==="
            
            # .env와 setup.conf 파일에서 변수 로드
            if [ ! -f ".env" ] || [ ! -f "setup.conf" ]; then
                log_error ".env 또는 setup.conf 파일을 찾을 수 없습니다."
                log_error "정리할 리소스 정보를 찾을 수 없습니다."
                exit 1
            fi
            source .env
            source setup.conf
            
            # 로드된 변수들을 스크립트 내부 변수로 재할당
            PROJECT_ID=$GCP_PROJECT_ID
            REGION=$GCP_REGION
            SA_EMAIL=$GCP_SA_EMAIL
            SERVICE_NAME=$GCP_SERVICE_NAME
            DEV_SERVICE_NAME=$GCP_DEV_SERVICE_NAME
            REPO_NAME=$GCP_REPOSITORY
            BUCKET_NAME=$GCS_BUCKET_NAME
            FIRESTORE_DATABASE_ID=$FIRESTORE_DATABASE_ID
            
            setup_project # gcloud config set project
            cleanup_resources
            ;;

        *)
            log_error "알 수 없는 명령어: $COMMAND"
            echo "사용법:"
            echo "  ./setup_gcp_environment.sh init           # 1단계: GCP 리소스 생성"
            echo "  ./setup_gcp_environment.sh connect-github # 2단계: GitHub 트리거 연결"
            echo "  ./setup_gcp_environment.sh cleanup        # 리소스 정리"
            exit 1
            ;;
    esac
}

# 스크립트 실행
main "$@" 