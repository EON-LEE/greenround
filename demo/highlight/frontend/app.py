import streamlit as st
import requests
import time
import json
from typing import Optional, Dict, Any
import io
from pathlib import Path

# 페이지 설정
st.set_page_config(
    page_title="Golf 3D Analyzer",
    page_icon="⛳",
    layout="wide"
)

# 백엔드 API URL 설정
API_BASE_URL = "http://localhost:8000"

class APIClient:
    """백엔드 API 클라이언트"""
    
    @staticmethod
    def upload_video(video_file) -> Optional[Dict]:
        """비디오 파일 업로드"""
        try:
            files = {"file": (video_file.name, video_file, video_file.type)}
            response = requests.post(f"{API_BASE_URL}/api/upload", files=files)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"업로드 실패: {str(e)}")
            return None
    
    @staticmethod
    def create_highlight_video(file_id: str, duration: int, slow_factor: int) -> Optional[Dict]:
        """하이라이트 영상 생성 요청"""
        try:
            data = {
                "file_id": file_id,
                "total_duration": duration,
                "slow_factor": slow_factor
            }
            response = requests.post(f"{API_BASE_URL}/api/highlight-video", json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"하이라이트 영상 생성 실패: {str(e)}")
            return None
    
    @staticmethod
    def create_swing_sequence(file_id: str) -> Optional[Dict]:
        """스윙 시퀀스 이미지 생성 요청 (심플)"""
        try:
            data = {
                "file_id": file_id
            }
            response = requests.post(f"{API_BASE_URL}/api/swing-sequence", json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"스윙 시퀀스 생성 실패: {str(e)}")
            return None
    
    @staticmethod
    def create_ball_tracking(file_id: str, show_trajectory: bool, show_speed: bool, show_distance: bool) -> Optional[Dict]:
        """볼 트래킹 영상 생성 요청"""
        try:
            data = {
                "file_id": file_id,
                "show_trajectory": show_trajectory,
                "show_speed": show_speed,
                "show_distance": show_distance
            }
            response = requests.post(f"{API_BASE_URL}/api/ball-tracking", json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"볼 트래킹 생성 실패: {str(e)}")
            return None
    
    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict]:
        """태스크 상태 확인"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/status/{task_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"상태 확인 실패: {str(e)}")
            return None
    
    @staticmethod
    def download_file(filename: str) -> Optional[bytes]:
        """파일 다운로드"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/download/{filename}")
            response.raise_for_status()
            return response.content
        except Exception as e:
            st.error(f"다운로드 실패: {str(e)}")
            return None
    
    @staticmethod
    def check_health() -> bool:
        """API 서버 상태 확인"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
            return response.status_code == 200
        except:
            return False

def display_task_progress(task_id: str, task_type: str) -> Optional[Dict]:
    """태스크 진행 상황 표시"""
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    while True:
        status_data = APIClient.get_task_status(task_id)
        if not status_data:
            st.error("상태 확인 실패")
            return None
        
        status = status_data.get("status")
        progress = status_data.get("progress", 0)
        message = status_data.get("message", "")
        
        # 진행률 표시
        progress_placeholder.progress(progress / 100)
        status_placeholder.info(f"상태: {message} ({progress}%)")
        
        if status == "completed":
            st.success(f"{task_type} 완료!")
            return status_data
        elif status == "failed":
            st.error(f"{task_type} 실패: {message}")
            return None
        
        time.sleep(2)  # 2초마다 상태 확인

def main():
    """메인 애플리케이션"""
    
    # 헤더
    st.title("⛳ Golf 3D Analyzer")
    st.markdown("**골프 스윙 분석 도구** - 하이라이트 영상, 시퀀스 이미지, 볼 트래킹")
    
    # API 서버 상태 확인
    if not APIClient.check_health():
        st.error("❌ 백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
        st.info("터미널에서 `python run_backend.py` 명령으로 서버를 시작하세요.")
        return
    
    st.success("✅ 백엔드 서버 연결됨")
    
    # 사이드바
    st.sidebar.title("📋 메뉴")
    
    # 파일 업로드
    st.sidebar.subheader("1. 비디오 업로드")
    uploaded_file = st.sidebar.file_uploader(
        "골프 스윙 비디오를 업로드하세요",
        type=['mp4', 'avi', 'mov'],
        help="최대 100MB까지 업로드 가능합니다"
    )
    
    # 세션 상태 초기화
    if 'file_id' not in st.session_state:
        st.session_state.file_id = None
    if 'filename' not in st.session_state:
        st.session_state.filename = None
    
    # 파일 업로드 처리
    if uploaded_file is not None:
        if st.sidebar.button("📤 업로드"):
            with st.spinner("파일 업로드 중..."):
                upload_result = APIClient.upload_video(uploaded_file)
                if upload_result:
                    st.session_state.file_id = upload_result["file_id"]
                    st.session_state.filename = upload_result["filename"]
                    st.sidebar.success(f"✅ 업로드 완료: {upload_result['filename']}")
    
    # 업로드된 파일이 있을 때만 기능 표시
    if st.session_state.file_id:
        st.sidebar.success(f"📁 업로드된 파일: {st.session_state.filename}")
        
        # 탭으로 기능 구분
        tab1, tab2, tab3 = st.tabs(["🎬 하이라이트 영상", "📸 스윙 시퀀스", "⚽ 볼 트래킹"])
        
        # 1. 하이라이트 영상 탭
        with tab1:
            st.header("🎬 3단계 하이라이트 영상 생성")
            st.markdown("**정상속도 → 슬로우모션 → 초슬로우** 3단계로 구성된 하이라이트 영상을 생성합니다.")
            
            col1, col2 = st.columns(2)
            with col1:
                total_duration = st.slider("총 영상 길이 (초)", 10, 30, 15)
            with col2:
                slow_factor = st.slider("슬로우 배율", 2, 8, 4)
            
            if st.button("🎬 하이라이트 영상 생성", key="highlight_btn"):
                result = APIClient.create_highlight_video(
                    st.session_state.file_id, total_duration, slow_factor
                )
                if result:
                    task_id = result["task_id"]
                    st.info(f"태스크 ID: {task_id}")
                    
                    # 진행 상황 모니터링
                    status_data = display_task_progress(task_id, "하이라이트 영상 생성")
                    if status_data and status_data.get("result_data"):
                        download_url = status_data["result_data"].get("download_url")
                        if download_url:
                            filename = download_url.split("/")[-1]
                            file_data = APIClient.download_file(filename)
                            if file_data:
                                st.download_button(
                                    label="📥 하이라이트 영상 다운로드",
                                    data=file_data,
                                    file_name=filename,
                                    mime="video/mp4"
                                )
        
        # 2. 스윙 시퀀스 탭
        with tab2:
            st.header("📸 7단계 스윙 시퀀스 이미지")
            st.markdown("7장의 스윙 주요 프레임을 단순히 이어붙인 합성 이미지를 생성합니다.")
            if st.button("📸 시퀀스 이미지 생성", key="sequence_btn"):
                result = APIClient.create_swing_sequence(st.session_state.file_id)
                if result:
                    task_id = result["task_id"]
                    st.info(f"태스크 ID: {task_id}")
                    # 진행 상황 모니터링
                    status_data = display_task_progress(task_id, "스윙 시퀀스 생성")
                    if status_data and status_data.get("result_data"):
                        download_url = status_data["result_data"].get("download_url")
                        if download_url:
                            filename = download_url.split("/")[-1]
                            file_data = APIClient.download_file(filename)
                            if file_data:
                                st.image(file_data, caption="생성된 스윙 시퀀스", use_column_width=True)
                                st.download_button(
                                    label="📥 시퀀스 이미지 다운로드",
                                    data=file_data,
                                    file_name=filename,
                                    mime="image/png"
                                )
        
        # 3. 볼 트래킹 탭
        with tab3:
            st.header("⚽ 골프공 트래킹 영상")
            st.markdown("**YOLO 기반 골프공 감지**로 공의 궤적, 속도, 거리를 시각화한 영상을 생성합니다.")
            
            st.subheader("표시 옵션")
            col1, col2, col3 = st.columns(3)
            with col1:
                show_trajectory = st.checkbox("궤적 표시", value=True)
            with col2:
                show_speed = st.checkbox("속도 표시", value=True)
            with col3:
                show_distance = st.checkbox("거리 표시", value=True)
            
            st.info("ℹ️ YOLO 모델이 처음 실행될 때 다운로드가 필요할 수 있습니다.")
            
            if st.button("⚽ 볼 트래킹 영상 생성", key="tracking_btn"):
                result = APIClient.create_ball_tracking(
                    st.session_state.file_id, show_trajectory, show_speed, show_distance
                )
                if result:
                    task_id = result["task_id"]
                    st.info(f"태스크 ID: {task_id}")
                    
                    # 진행 상황 모니터링
                    status_data = display_task_progress(task_id, "볼 트래킹 생성")
                    if status_data and status_data.get("result_data"):
                        result_data = status_data["result_data"]
                        
                        # 트래킹 결과 정보 표시
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("볼 감지됨", "예" if result_data.get("ball_detected") else "아니오")
                        with col2:
                            st.metric("궤적 포인트", result_data.get("trajectory_points", 0))
                        with col3:
                            st.metric("이동 거리", f"{result_data.get('distance', 0):.1f} px")
                        
                        download_url = result_data.get("download_url")
                        if download_url:
                            filename = download_url.split("/")[-1]
                            file_data = APIClient.download_file(filename)
                            if file_data:
                                st.download_button(
                                    label="📥 트래킹 영상 다운로드",
                                    data=file_data,
                                    file_name=filename,
                                    mime="video/mp4"
                                )
    
    else:
        # 업로드된 파일이 없을 때 안내 메시지
        st.info("👈 먼저 사이드바에서 골프 스윙 비디오를 업로드해주세요.")
        
        # 기능 소개
        st.subheader("🔥 주요 기능")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 🎬 하이라이트 영상
            - 3단계 속도 패턴
            - 정상속도 → 슬로우 → 초슬로우
            - 포즈 분석 기반 스윙 구간 자동 감지
            """)
        
        with col2:
            st.markdown("""
            ### 📸 스윙 시퀀스
            - 7단계 스윙 주요 프레임 이어붙이기
            """)
        
        with col3:
            st.markdown("""
            ### ⚽ 볼 트래킹
            - YOLO 기반 골프공 감지
            - 실시간 궤적 시각화
            - 속도/거리 통계 표시
            """)

if __name__ == "__main__":
    main() 