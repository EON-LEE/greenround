#!/bin/bash

# =============================================================================
# Greenround - Google Cloud 자동 배포 스크립트
# =============================================================================

set -e  # 에러 발생 시 스크립트 중단

# 색상 코드 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수들
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 설정 변수들 (.env 파일에서 자동 로드됨)
DEFAULT_PROJECT_ID="greenround-default"
DEFAULT_REGION="asia-northeast3"
DEFAULT_SERVICE_NAME="greenround-backend"
DEFAULT_REPOSITORY="greenround"
DEFAULT_GPU_TYPE="nvidia-l4"
DEFAULT_GPU_COUNT="1"
DEFAULT_USE_GPU="true"

# .env 파일에서 환경 변수 로드 (존재하는 경우)
load_env_file() {
    if [ -f ".env" ]; then
        log_info ".env 파일에서 환경 변수 로드 중..."
        export $(grep -v '^#' .env | xargs)
        log_success ".env 파일 로드 완료"
        cat .env
    else
        log_warning ".env 파일을 찾을 수 없습니다. 기본값을 사용합니다."
    fi
}

# 환경 변수 설정 (load_env_file 호출 후 사용)
set_environment_variables() {
    PROJECT_ID=${GCP_PROJECT_ID:-$DEFAULT_PROJECT_ID}
    REGION=${GCP_REGION:-$DEFAULT_REGION}
    SERVICE_NAME=${GCP_SERVICE_NAME:-$DEFAULT_SERVICE_NAME}
    REPOSITORY=${GCP_REPOSITORY:-$DEFAULT_REPOSITORY}
    GPU_TYPE=${GCP_GPU_TYPE:-$DEFAULT_GPU_TYPE}
    GPU_COUNT=${GCP_GPU_COUNT:-$DEFAULT_GPU_COUNT}
    USE_GPU=${GCP_USE_GPU:-$DEFAULT_USE_GPU}
    
    # Docker 이미지 경로 구성
    IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE_NAME"
    IMAGE_TAG=${1:-latest}
    FULL_IMAGE_NAME="$IMAGE_NAME:$IMAGE_TAG"
}

# 사용법 출력
usage() {
    echo "사용법: $0 [OPTIONS] [TAG]"
    echo ""
    echo "옵션:"
    echo "  --build-only     이미지 빌드만 수행"
    echo "  --deploy-only    배포만 수행 (빌드 스킵)"
    echo "  --setup          초기 설정 수행"
    echo "  --check          환경 확인"
    echo "  --logs           서비스 로그 확인"
    echo "  --status         서비스 상태 확인"
    echo "  --help           도움말 표시"
    echo ""
    echo "GPU 설정 (.env 파일에서 설정):"
    echo "  GCP_USE_GPU      GPU 사용 여부 (기본: true)"
    echo "  GCP_GPU_TYPE     GPU 타입 (기본: nvidia-t4)"
    echo "                   옵션: nvidia-t4, nvidia-l4, nvidia-v100"
    echo "  GCP_GPU_COUNT    GPU 개수 (기본: 1)"
    echo ""
    echo "예시:"
    echo "  $0                    # 전체 배포 (GPU 포함)"
    echo "  $0 v1.2.0            # 특정 태그로 배포"
    echo "  $0 --build-only      # 빌드만"
    echo "  $0 --deploy-only     # 배포만"
    echo ""
    echo ".env 파일 예시:"
    echo "  GCP_PROJECT_ID=your-project"
    echo "  GCP_USE_GPU=true"
    echo "  GCP_GPU_TYPE=nvidia-t4"
    echo "  GCP_GPU_COUNT=1"
    echo ""
    echo "CPU 전용 배포:"
    echo "  GCP_USE_GPU=false"
    exit 1
}

# 필수 도구 확인
check_requirements() {
    log_info "필수 도구 확인 중..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되지 않았습니다."
        exit 1
    fi
    
    if ! command -v gcloud &> /dev/null; then
        log_error "Google Cloud CLI가 설치되지 않았습니다."
        exit 1
    fi
    
    log_success "모든 필수 도구가 설치되어 있습니다."
}

# GCP 인증 확인
check_auth() {
    log_info "GCP 인증 상태 확인 중..."
    
    if ! gcloud auth list --filter="status:ACTIVE" --format="value(account)" | grep -q "@"; then
        log_error "GCP에 로그인되지 않았습니다. 'gcloud auth login' 실행 후 다시 시도하세요."
        exit 1
    fi
    
    # 프로젝트 설정 확인
    current_project=$(gcloud config get-value project 2>/dev/null || echo "")
    if [ "$current_project" != "$PROJECT_ID" ]; then
        log_warning "현재 프로젝트($current_project)와 설정된 프로젝트($PROJECT_ID)가 다릅니다."
        log_info "프로젝트를 $PROJECT_ID로 설정합니다..."
        gcloud config set project "$PROJECT_ID"
    fi
    
    log_success "GCP 인증이 확인되었습니다."
}

# Docker 인증 설정
setup_docker_auth() {
    log_info "Docker 인증 설정 중..."
    gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
    log_success "Docker 인증이 설정되었습니다."
}

# 필수 API 활성화
enable_apis() {
    log_info "필수 API 활성화 중..."
    
    apis=(
        "artifactregistry.googleapis.com"
        "run.googleapis.com"
        "cloudbuild.googleapis.com"
        "compute.googleapis.com"
    )
    
    for api in "${apis[@]}"; do
        log_info "API 활성화: $api"
        gcloud services enable "$api" --quiet
    done
    
    log_success "모든 필수 API가 활성화되었습니다."
}

# Artifact Registry 저장소 생성
setup_repository() {
    log_info "Artifact Registry 저장소 확인 중..."
    
    if ! gcloud artifacts repositories describe "$REPOSITORY" --location="$REGION" &> /dev/null; then
        log_info "Artifact Registry 저장소 생성 중..."
        gcloud artifacts repositories create "$REPOSITORY" \
            --repository-format=docker \
            --location="$REGION" \
            --description="Greenround Backend Repository" \
            --quiet
        log_success "Artifact Registry 저장소가 생성되었습니다."
    else
        log_success "Artifact Registry 저장소가 이미 존재합니다."
    fi
}

# Docker 이미지 빌드
build_image() {
    log_info "Docker 이미지 빌드 시작..."
    log_info "이미지 이름: $FULL_IMAGE_NAME"
    
    # GitHub Actions에서는 이미 buildx가 설정되어 있으므로 체크
    if command -v docker buildx &> /dev/null; then
        log_info "Docker Buildx 사용 가능"
        # GitHub Actions에서 실행 중인지 확인
        if [ -n "${GITHUB_ACTIONS:-}" ]; then
            log_info "GitHub Actions 환경에서 실행 중 - 기존 buildx 사용"
        else
            # 로컬 환경에서는 multiarch 빌더 설정
            if ! docker buildx ls | grep -q "multiarch"; then
                log_info "Docker Buildx 빌더 생성 중..."
                docker buildx create --name multiarch --use
            else
                docker buildx use multiarch
            fi
        fi
    else
        log_error "Docker Buildx를 사용할 수 없습니다."
        exit 1
    fi
    
    # AMD64 아키텍처로 빌드 및 푸시 (캐시 최적화)
    log_info "Linux/AMD64 플랫폼으로 빌드 및 푸시 중..."
    docker buildx build \
        --platform linux/amd64 \
        --tag "$FULL_IMAGE_NAME" \
        --cache-from type=gha \
        --cache-to type=gha,mode=max \
        --push \
        .
    
    log_success "Docker 이미지 빌드 및 푸시 완료!"
}

# Cloud Run 배포
deploy_service() {
    log_info "Cloud Run 서비스 배포 시작..."
    log_info "서비스 이름: $SERVICE_NAME"
    log_info "이미지: $FULL_IMAGE_NAME"
    
    # GPU 사용 여부에 따른 배포 설정
    if [ "$USE_GPU" == "true" ]; then
        log_info "GPU 모드: $GPU_COUNT개 $GPU_TYPE GPU 사용"
        DEPLOY_ARGS="--gpu=$GPU_COUNT --gpu-type=$GPU_TYPE --no-cpu-throttling --no-gpu-zonal-redundancy"
        ENV_VARS="DEPLOYED_FROM=docker,GPU_ENABLED=true"
    else
        log_info "CPU 전용 모드로 배포"
        DEPLOY_ARGS=""
        ENV_VARS="DEPLOYED_FROM=docker,GPU_ENABLED=false"
    fi
    
    gcloud run deploy "$SERVICE_NAME" \
        --image="$FULL_IMAGE_NAME" \
        --platform=managed \
        --region="$REGION" \
        --allow-unauthenticated \
        --port=8000 \
        --memory=16Gi \
        --cpu=4 \
        $DEPLOY_ARGS \
        --max-instances=3 \
        --timeout=3600 \
        --set-env-vars="$ENV_VARS" \
        --quiet
    
    # 서비스 URL 획득 및 출력
    SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
        --region="$REGION" \
        --format='value(status.url)')
    
    log_success "Cloud Run 배포 완료!"
    log_success "서비스 URL: $SERVICE_URL"
    log_info "API 문서: $SERVICE_URL/docs"
}

# 서비스 상태 확인
check_service_status() {
    log_info "서비스 상태 확인 중..."
    
    if gcloud run services describe "$SERVICE_NAME" --region="$REGION" &> /dev/null; then
        SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
            --region="$REGION" \
            --format='value(status.url)')
        
        log_success "서비스가 실행 중입니다."
        log_info "서비스 URL: $SERVICE_URL"
        
        # API 응답 테스트
        log_info "API 응답 테스트 중..."
        if curl -s --max-time 10 "$SERVICE_URL/docs" > /dev/null; then
            log_success "API 서비스가 정상적으로 응답합니다."
        else
            log_warning "API 서비스 응답을 확인할 수 없습니다."
        fi
    else
        log_error "서비스를 찾을 수 없습니다."
        exit 1
    fi
}

# 서비스 로그 확인
show_logs() {
    log_info "서비스 로그를 표시합니다..."
    gcloud logs tail --follow \
        --resource-labels=service_name="$SERVICE_NAME" \
        --resource-labels=location="$REGION"
}

# 초기 설정 수행
initial_setup() {
    log_info "초기 설정을 시작합니다..."
    load_env_file
    set_environment_variables
    check_requirements
    check_auth
    enable_apis
    setup_repository
    setup_docker_auth
    log_success "초기 설정이 완료되었습니다!"
}

# 환경 확인
check_environment() {
    log_info "=== 환경 설정 확인 ==="
    echo "프로젝트 ID: $PROJECT_ID"
    echo "리전: $REGION"
    echo "서비스 이름: $SERVICE_NAME"
    echo "저장소: $REPOSITORY"
    echo "이미지 이름: $FULL_IMAGE_NAME"
    if [ "$USE_GPU" == "true" ]; then
        echo "GPU 설정: $GPU_COUNT개 $GPU_TYPE (활성화)"
    else
        echo "GPU 설정: 비활성화 (CPU 전용)"
    fi
    echo ""
    
    check_requirements
    check_auth
    
    log_info "Docker 인증 상태 확인..."
    if docker system info | grep -q "Registry: $REGION-docker.pkg.dev"; then
        log_success "Docker 인증이 설정되어 있습니다."
    else
        log_warning "Docker 인증이 설정되지 않았을 수 있습니다."
    fi
}

# 메인 함수
main() {
    echo "=========================================="
    echo "  Greenround - GCP 배포 스크립트"
    echo "=========================================="
    echo ""
    
    # 명령줄 인자 처리
    case "${1:-}" in
        --help|-h)
            usage
            ;;
        --setup)
            initial_setup
            ;;
        --check)
            load_env_file
            set_environment_variables
            check_environment
            ;;
        --build-only)
            load_env_file
            set_environment_variables
            check_requirements
            check_auth
            setup_docker_auth
            build_image
            ;;
        --deploy-only)
            load_env_file
            set_environment_variables
            check_requirements
            check_auth
            deploy_service
            check_service_status
            ;;
        --status)
            load_env_file
            set_environment_variables
            check_requirements
            check_auth
            check_service_status
            ;;
        --logs)
            load_env_file
            set_environment_variables
            check_requirements
            check_auth
            show_logs
            ;;
        "")
            # 전체 배포 프로세스
            load_env_file
            set_environment_variables
            check_requirements
            check_auth
            setup_docker_auth
            build_image
            deploy_service
            check_service_status
            ;;
        --*)
            log_error "알 수 없는 옵션: $1"
            usage
            ;;
        *)
            # 태그가 지정된 경우
            load_env_file
            set_environment_variables "$1"  # 태그를 인수로 전달
            log_info "태그 '$IMAGE_TAG'로 배포합니다."
            
            check_requirements
            check_auth
            setup_docker_auth
            build_image
            deploy_service
            check_service_status
            ;;
    esac
}

# 스크립트 실행
main "$@" 