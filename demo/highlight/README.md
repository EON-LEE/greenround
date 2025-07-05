# ⛳ Golf 3D Analyzer

골프 스윙 분석을 위한 FastAPI + Streamlit 기반 웹 애플리케이션

## 🔥 주요 기능

### 1. 🎬 3단계 하이라이트 영상
- **정상속도 → 슬로우모션 → 초슬로우** 3단계 속도 패턴
- MediaPipe 기반 포즈 분석으로 스윙 구간 자동 감지
- 사용자 정의 가능한 영상 길이 및 슬로우 배율

### 2. 📸 7단계 스윙 시퀀스 이미지
- **Address → Takeaway → Backswing → Top → Downswing → Impact → Follow Through**
- 7단계 스윙 동작을 하나의 이미지에 오버레이 합성
- 단계별 투명도 조절 가능
- 고해상도 출력 지원 (최대 2560x1440)

### 3. ⚽ 골프공 트래킹 영상
- **YOLO v8** 기반 실시간 골프공 감지
- 궤적 시각화 및 스무딩 처리
- 속도, 거리 통계 정보 표시
- 트래킹 옵션 커스터마이징

## 🏗️ 시스템 구조

```
demo/highlight/
├── backend/                 # FastAPI 백엔드
│   ├── main.py             # 메인 API 서버
│   ├── models/
│   │   └── schemas.py      # Pydantic 스키마
│   └── core/
│       ├── utils.py        # 공통 유틸리티
│       ├── pose_analyzer.py # MediaPipe 포즈 분석
│       ├── highlight_engine.py # 하이라이트 영상 생성
│       ├── sequence_composer.py # 시퀀스 이미지 합성
│       └── ball_tracker.py # YOLO 볼 트래킹
├── frontend/
│   └── app.py              # Streamlit 웹 인터페이스
├── storage/                # 파일 저장소
│   ├── uploads/           # 업로드된 원본 영상
│   ├── highlights/        # 생성된 하이라이트 영상
│   ├── sequences/         # 생성된 시퀀스 이미지
│   └── ball_tracks/       # 생성된 트래킹 영상
├── run_backend.py         # 백엔드 실행 스크립트
├── run_frontend.py        # 프론트엔드 실행 스크립트
└── requirements.txt       # 의존성 패키지
```

## 🚀 설치 및 실행

### 1. 의존성 설치
```bash
# 가상환경 활성화 (권장)
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate     # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 백엔드 서버 실행
```bash
python run_backend.py
```
- 서버 주소: http://localhost:8000
- API 문서: http://localhost:8000/docs

### 3. 프론트엔드 실행 (새 터미널)
```bash
python run_frontend.py
```
- 웹 인터페이스: http://localhost:8501

## 📋 사용법

### 1. 비디오 업로드
- 사이드바에서 골프 스윙 비디오 업로드 (MP4, AVI, MOV 지원)
- 최대 파일 크기: 100MB

### 2. 기능 선택
각 탭에서 원하는 기능을 선택하고 설정을 조정한 후 생성 버튼 클릭

#### 🎬 하이라이트 영상
- **총 영상 길이**: 10-30초 (기본값: 15초)
- **슬로우 배율**: 2-8배 (기본값: 4배)

#### 📸 스윙 시퀀스
- **이미지 해상도**: 1280x720, 1920x1080, 2560x1440
- **단계별 투명도**: 각 스윙 단계별로 10-100% 조절

#### ⚽ 볼 트래킹
- **궤적 표시**: 골프공 이동 경로 시각화
- **속도 표시**: 실시간 속도 정보
- **거리 표시**: 총 이동 거리

### 3. 결과 다운로드
- 생성 완료 후 다운로드 버튼으로 결과 파일 저장
- 진행 상황은 실시간으로 표시됨

## 🔧 API 엔드포인트

### 파일 관리
- `POST /api/upload` - 비디오 파일 업로드
- `GET /api/download/{filename}` - 생성된 파일 다운로드

### 분석 기능
- `POST /api/highlight-video` - 하이라이트 영상 생성
- `POST /api/swing-sequence` - 스윙 시퀀스 이미지 생성
- `POST /api/ball-tracking` - 볼 트래킹 영상 생성

### 상태 관리
- `GET /api/status/{task_id}` - 태스크 진행 상태 확인
- `GET /api/health` - 서버 상태 확인
- `GET /api/info` - 시스템 정보 조회

## 🛠️ 기술 스택

### 백엔드
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **MediaPipe**: 구글의 포즈 감지 라이브러리
- **YOLO v8**: 최신 객체 감지 모델
- **OpenCV**: 컴퓨터 비전 처리
- **PIL/Pillow**: 이미지 처리 및 합성

### 프론트엔드
- **Streamlit**: 빠른 웹 앱 개발 프레임워크
- **Requests**: HTTP 클라이언트

### 데이터 처리
- **NumPy**: 수치 연산
- **Pydantic**: 데이터 검증 및 직렬화

## ⚙️ 설정 옵션

### 파일 제한
- 지원 형식: MP4, AVI, MOV
- 최대 크기: 100MB
- 최소 요구사항: 30프레임, 10fps, 100x100 해상도

### 저장소 관리
- 자동 정리: 24시간 후 파일 삭제
- 임시 파일: 1시간마다 정리

## 🐛 문제 해결

### 백엔드 서버 연결 실패
```bash
# 서버 상태 확인
curl http://localhost:8000/api/health

# 포트 사용 확인
lsof -i :8000
```

### YOLO 모델 다운로드 실패
- 인터넷 연결 확인
- 첫 실행 시 모델 자동 다운로드 (약 6MB)

### 메모리 부족 오류
- 비디오 해상도 및 길이 확인
- 시스템 메모리 최소 4GB 권장

## 📊 성능 최적화

### 처리 속도 향상
- GPU 사용 가능 시 CUDA 설정
- 비디오 해상도 조정 (1080p 권장)
- 배치 처리 크기 조정

### 메모리 사용량 최적화
- 프레임별 순차 처리
- 임시 파일 자동 정리
- 메모리 효율적인 비디오 인코딩

## 📝 라이선스

MIT License - 자유롭게 사용, 수정, 배포 가능

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

---

**개발자**: Golf 3D Analyzer Team  
**버전**: 1.0.0  
**최종 업데이트**: 2024년 6월 