import streamlit as st
import logging
import logging.handlers
import os
import tempfile
from typing import Dict, Optional, Tuple, List
import uuid
import io
import time

import cv2
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import plotly.graph_objects as go
import streamlit as st

# Streamlit 페이지 설정
st.set_page_config(
    page_title="골프 스윙 분석기",
    page_icon="🏌️",
    layout="wide"
)

# 로깅 설정
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOG_DIR, "app.log"),
    maxBytes=10*1024*1024,
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)
logger = logging.getLogger(__name__)

# 임시 디렉토리 설정
TEMP_DIR = os.path.join(tempfile.gettempdir(), "golf_swing_analyzer")
os.makedirs(TEMP_DIR, exist_ok=True)

# 세션 상태 초기화
if 'models' not in st.session_state:
    st.session_state.models = None
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False

@st.cache_resource(ttl=None)
def load_models():
    """모델 로드 및 캐싱"""
    try:
        import importlib
        import pose_estimation
        import swing_analyzer
        import video_processor
        import analysis_service
        
        # 모듈 리로드
        importlib.reload(pose_estimation)
        importlib.reload(swing_analyzer)
        importlib.reload(video_processor)
        importlib.reload(analysis_service)
        
        # 클래스 임포트
        from pose_estimation import PoseEstimator
        from swing_analyzer import SwingAnalyzer
        from video_processor import VideoProcessor
        from analysis_service import SwingAnalysisService
        
        logger.debug("Initializing models...")
        pose_estimator = PoseEstimator()
        swing_analyzer = SwingAnalyzer()
        video_processor = VideoProcessor()
        analysis_service = SwingAnalysisService()
        
        # 모델 초기화 확인
        logger.debug(f"PoseEstimator methods: {dir(pose_estimator)}")
        logger.debug(f"SwingAnalyzer methods: {dir(swing_analyzer)}")
        logger.debug(f"VideoProcessor methods: {dir(video_processor)}")
        logger.debug(f"AnalysisService methods: {dir(analysis_service)}")
        
        return (
            pose_estimator,
            swing_analyzer,
            video_processor,
            analysis_service
        )
    except Exception as e:
        logger.error(f"모델 로딩 중 오류: {str(e)}", exc_info=True)
        st.error(f"모델 로딩 중 오류가 발생했습니다: {str(e)}")
        return None

def get_models() -> Optional[Tuple]:
    """세션에서 모델 가져오기"""
    try:
        if st.session_state.models is None:
            logger.debug("Loading models for the first time...")
            st.session_state.models = load_models()
            if st.session_state.models is not None:
                logger.debug("Models loaded successfully")
                pose_estimator, swing_analyzer, video_processor, analysis_service = st.session_state.models
                logger.debug(f"SwingAnalyzer methods after loading: {dir(swing_analyzer)}")
            else:
                logger.error("Failed to load models")
        return st.session_state.models
    except Exception as e:
        logger.error(f"Error in get_models: {str(e)}", exc_info=True)
        return None

def save_uploaded_file(uploaded_file) -> Optional[str]:
    """업로드된 파일을 저장하고 경로를 반환"""
    try:
        if uploaded_file is None:
            return None
            
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in ['.mp4', '.avi', '.mov']:
            st.error("지원하지 않는 파일 형식입니다. MP4, AVI, MOV 파일만 업로드 가능합니다.")
            return None
            
        video_id = f"output_video_{str(uuid.uuid4())[:8]}{file_ext}"
        temp_path = os.path.join(TEMP_DIR, video_id)
        
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getvalue())
            
        return temp_path
    except Exception as e:
        logger.error(f"파일 저장 중 오류: {str(e)}")
        st.error(f"파일 저장 중 오류가 발생했습니다: {str(e)}")
        return None

def analyze_swing(video_path: str, models: Tuple) -> Optional[Dict]:
    """골프 스윙 비디오 분석"""
    try:
        if not os.path.exists(video_path):
            st.error("비디오 파일을 찾을 수 없습니다.")
            return None
            
        if models is None:
            st.error("필요한 모델이 로드되지 않았습니다.")
            return None
            
        pose_estimator, swing_analyzer, _, _ = models

        logger.info(f"Starting analysis for video: {video_path}")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("비디오 분석 중...")
        
        # SwingAnalyzer의 analyze_video 메서드 사용 (세분화된 포즈 분석 포함)
        result = swing_analyzer.analyze_video(video_path)
        
        if not result:
            st.error("비디오 분석에 실패했습니다.")
            return None
        
        progress_bar.progress(50)
        status_text.text("시퀀스 이미지 생성 중...")
        
        # 연속 겹침 시퀀스 생성
        try:
            continuous_path = os.path.join(TEMP_DIR, "continuous_overlap_sequence.jpg")
            continuous_overlap_path = create_swing_sequence_local(
                video_path, 
                result['key_frames'], 
                continuous_path,
                overlap_mode="continuous"
            )
            if continuous_overlap_path:
                st.session_state.continuous_sequence_path = continuous_overlap_path
                logger.info(f"연속 겹침 시퀀스 생성 완료: {continuous_overlap_path}")
        except Exception as e:
            logger.warning(f"연속 겹침 시퀀스 생성 실패: {e}")
            st.session_state.continuous_sequence_path = None
        
        progress_bar.progress(100)
        status_text.text("분석 완료!")
        
        # UI 정리
        progress_bar.empty()
        status_text.empty()
        
        logger.info(f"분석 완료: {len(result.get('frames_data', []))} 프레임 처리됨")
        logger.info(f"감지된 키 프레임: {result.get('key_frames', {})}")
        
        return {
            "message": "분석이 완료되었습니다.",
            "frames": result.get('frames_data', []),
            "frames_data": result.get('frames_data', []),
            "metrics": result.get('metrics', {}),
            "key_frames": result.get('key_frames', {}),
            "evaluations": result.get('evaluations', {})
        }
    except Exception as e:
        logger.error(f"Error in analyze_swing: {str(e)}", exc_info=True)
        st.error(f"분석 중 오류가 발생했습니다: {str(e)}")
        return None

def create_sequence_image(video_path: str, key_frames: Dict[str, int], overlap_mode: bool = False, 
                         analysis_frames: List[Dict] = None) -> Optional[np.ndarray]:
    """스윙 시퀀스 이미지 생성 (오버랩 모드 지원 + 사람 영역 자동 크롭)"""
    try:
        if not os.path.exists(video_path):
            st.error("비디오 파일을 찾을 수 없습니다.")
            return None
            
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            st.error("비디오 파일을 열 수 없습니다.")
            return None
            
        frames = []
        frame_order = ['address', 'backswing', 'top', 'impact', 'follow_through']
        
        for phase in frame_order:
            frame_idx = key_frames.get(phase)
            if frame_idx is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    # 사람 영역 자동 크롭 (랜드마크 데이터가 있는 경우)
                    if analysis_frames and frame_idx < len(analysis_frames):
                        landmarks_data = analysis_frames[frame_idx]['landmarks']
                        frame = auto_crop_person_area(frame, landmarks_data)
                    
                    # 프레임 크기 조정
                    height, width = frame.shape[:2]
                    if width > 800:  # 너무 크면 리사이즈
                        scale = 800 / width
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))
                    
                    frames.append((phase, frame))
        
        cap.release()
        
        if not frames:
            st.error("시퀀스 이미지를 생성할 프레임이 없습니다.")
            return None
        
        if overlap_mode:
            return create_overlapped_sequence(frames)
        else:
            return create_side_by_side_sequence(frames)
        
    except Exception as e:
        logger.error(f"Error creating sequence image: {str(e)}")
        st.error(f"시퀀스 이미지 생성 중 오류가 발생했습니다: {str(e)}")
        return None

def create_overlapped_sequence(frames: List[Tuple[str, np.ndarray]]) -> np.ndarray:
    """오버랩 방식으로 스윙 시퀀스 생성"""
    if not frames:
        raise ValueError("프레임이 없습니다.")
    
    # 기준 프레임 (첫 번째 프레임)
    base_frame = frames[0][1].copy()
    height, width = base_frame.shape[:2]
    
    # 결과 이미지 초기화 (알파 채너리 포함)
    result = np.zeros((height, width, 4), dtype=np.float32)
    
    # 각 프레임을 투명도를 조절하여 겹치기
    alpha_values = [0.8, 0.6, 0.5, 0.4, 0.3]  # 각 단계별 투명도
    colors = [
        (255, 255, 255),  # 흰색 (address)
        (255, 200, 100),  # 연한 주황 (backswing)
        (255, 150, 50),   # 주황 (top)
        (255, 100, 100),  # 연한 빨강 (impact)
        (200, 100, 255)   # 연한 보라 (follow_through)
    ]
    
    for i, (phase, frame) in enumerate(frames):
        alpha = alpha_values[i] if i < len(alpha_values) else 0.3
        
        # 프레임을 RGBA로 변환
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA).astype(np.float32)
        elif len(frame.shape) == 3 and frame.shape[2] == 4:
            frame_rgba = frame.astype(np.float32)
        else:
            # 그레이스케일이나 다른 형식인 경우 3채널로 변환
            if len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA).astype(np.float32)
        
        # 크기가 다른 경우 기준 프레임 크기에 맞춤
        if frame_rgba.shape[:2] != (height, width):
            frame_rgba = cv2.resize(frame_rgba, (width, height))
        
        # 색상 틴트 적용 (선택사항)
        if i > 0:  # 첫 번째 프레임은 원본 색상 유지
            tint_color = colors[i] if i < len(colors) else colors[-1]
            frame_rgba[:, :, :3] = frame_rgba[:, :, :3] * 0.7 + np.array(tint_color) * 0.3
        
        # 알파 값 설정
        frame_rgba[:, :, 3] = alpha * 255
        
        # 블렌딩
        if i == 0:
            result = frame_rgba.copy()
        else:
            try:
                # 알파 블렌딩
                alpha_norm = frame_rgba[:, :, 3:4] / 255.0
                result[:, :, :3] = result[:, :, :3] * (1 - alpha_norm) + frame_rgba[:, :, :3] * alpha_norm
                result[:, :, 3:4] = np.maximum(result[:, :, 3:4], frame_rgba[:, :, 3:4])
            except Exception as e:
                logger.warning(f"Alpha blending failed: {str(e)}, using simple overlay")
                # 블렌딩 실패 시 단순 오버레이
                mask = frame_rgba[:, :, 3] > 0
                result[mask] = frame_rgba[mask]
    
    # BGR로 변환하여 반환
    result_bgr = cv2.cvtColor(result[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2BGR)
    
    # 단계 라벨 추가
    add_phase_labels(result_bgr, frames)
    
    return result_bgr

def create_side_by_side_sequence(frames: List[Tuple[str, np.ndarray]]) -> np.ndarray:
    """나란히 배치 방식으로 스윙 시퀀스 생성"""
    if not frames:
        raise ValueError("프레임이 없습니다.")
    
    # 모든 프레임을 같은 높이로 리사이즈
    target_height = 400
    resized_frames = []
    
    for phase, frame in frames:
        try:
            # 프레임이 유효한지 확인
            if frame is None or frame.size == 0:
                logger.warning(f"Invalid frame for phase {phase}")
                continue
                
            # 채널 수 확인 및 변환
            if len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif len(frame.shape) == 3 and frame.shape[2] == 1:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            
            height, width = frame.shape[:2]
            if height == 0 or width == 0:
                logger.warning(f"Zero dimension frame for phase {phase}")
                continue
                
            scale = target_height / height
            new_width = int(width * scale)
            
            if new_width <= 0:
                logger.warning(f"Invalid new width for phase {phase}")
                continue
                
            resized_frame = cv2.resize(frame, (new_width, target_height))
            resized_frames.append((phase, resized_frame))
            
        except Exception as e:
            logger.error(f"Error resizing frame for phase {phase}: {str(e)}")
            continue
    
    if not resized_frames:
        raise ValueError("유효한 리사이즈된 프레임이 없습니다.")
    
    # 전체 너비 계산
    total_width = sum([frame.shape[1] for _, frame in resized_frames])
    
    # 결과 이미지 생성
    result = np.zeros((target_height, total_width, 3), dtype=np.uint8)
    
    # 프레임들을 나란히 배치
    x_offset = 0
    for phase, frame in resized_frames:
        try:
            width = frame.shape[1]
            
            # 안전한 범위 확인
            if x_offset + width <= total_width and frame.shape[0] <= target_height:
                # 채널 수 확인
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    result[:frame.shape[0], x_offset:x_offset + width] = frame
                else:
                    logger.warning(f"Unexpected frame shape for phase {phase}: {frame.shape}")
                    continue
                    
                # 단계 라벨 추가
                cv2.putText(result, phase.upper(), 
                           (x_offset + 10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                
                x_offset += width
            else:
                logger.warning(f"Frame for phase {phase} exceeds boundaries")
                
        except Exception as e:
            logger.error(f"Error placing frame for phase {phase}: {str(e)}")
            continue
    
    return result

def add_phase_labels(image: np.ndarray, frames: List[Tuple[str, np.ndarray]]) -> None:
    """이미지에 단계별 라벨을 추가합니다."""
    height, width = image.shape[:2]
    
    # 라벨 위치 계산 (우상단)
    label_x = width - 200
    label_y = 50
    
    # 배경 박스 그리기
    cv2.rectangle(image, (label_x - 10, label_y - 30), 
                 (label_x + 180, label_y + len(frames) * 25), 
                 (0, 0, 0), -1)
    cv2.rectangle(image, (label_x - 10, label_y - 30), 
                 (label_x + 180, label_y + len(frames) * 25), 
                 (255, 255, 255), 2)
    
    # 제목 추가
    cv2.putText(image, "Swing Sequence", 
               (label_x, label_y - 10), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # 각 단계 라벨 추가
    colors = [(255, 255, 255), (100, 200, 255), (50, 150, 255), 
             (100, 100, 255), (255, 100, 255)]
    
    for i, (phase, _) in enumerate(frames):
        color = colors[i] if i < len(colors) else (255, 255, 255)
        cv2.putText(image, f"{i+1}. {phase.replace('_', ' ').title()}", 
                   (label_x, label_y + 20 + i * 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def create_angle_graph(analysis_data: Dict) -> Optional[bytes]:
    """각도 변화 그래프 생성"""
    try:
        plt.figure(figsize=(12, 6))
        frames = analysis_data.get('frames', [])
        if not frames:
            st.error("그래프를 생성할 데이터가 없습니다.")
            return None
            
        frame_indices = range(len(frames))
        angles = {
            'Right Arm': [frame['angles'].get('right_arm', 0) for frame in frames],
            'Left Arm': [frame['angles'].get('left_arm', 0) for frame in frames],
            'Shoulders': [frame['angles'].get('shoulder_angle', 0) for frame in frames],
            'Hips': [frame['angles'].get('hips_inclination', 0) for frame in frames]
        }
        
        for label, values in angles.items():
            plt.plot(frame_indices, values, label=label)
            
        key_frames = analysis_data.get('key_frames', {})
        for phase, frame_idx in key_frames.items():
            if frame_idx < len(frames):
                plt.axvline(x=frame_idx, color='r', linestyle='--', alpha=0.3)
                plt.text(frame_idx, plt.ylim()[1], phase.upper(), 
                        rotation=45, ha='right')
        
        plt.title('Angle Changes During Swing')
        plt.xlabel('Frame')
        plt.ylabel('Angle (degrees)')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close()
        buf.seek(0)
        return buf.getvalue()
        
    except Exception as e:
        logger.error(f"Error creating angle graph: {str(e)}")
        st.error(f"각도 그래프 생성 중 오류가 발생했습니다: {str(e)}")
        return None

def main():
    """메인 애플리케이션"""
    st.title("골프 스윙 분석기 🏌️")
    st.write("골프 스윙 영상을 업로드하여 자세를 분석해보세요!")

    # 모델 로드
    models = get_models()
    if models is None:
        st.error("필요한 모델을 로드할 수 없습니다. 관리자에게 문의하세요.")
        return

    # 세션 상태 초기화
    if 'current_tab' not in st.session_state:
        st.session_state.current_tab = 0
    if 'analysis_result' not in st.session_state:
        st.session_state.analysis_result = None
    if 'temp_path' not in st.session_state:
        st.session_state.temp_path = None

    uploaded_file = st.file_uploader("골프 스윙 영상 업로드", type=['mp4', 'avi', 'mov'])
    
    if uploaded_file is not None:
        temp_path = save_uploaded_file(uploaded_file)
        st.session_state.temp_path = temp_path
        
        if temp_path:
            st.video(temp_path)
            
            if st.button("스윙 분석 시작"):
                with st.spinner("스윙을 분석하고 있습니다..."):
                    analysis_result = analyze_swing(temp_path, models)
                    
                    if analysis_result:
                        st.session_state.analysis_result = analysis_result
                        st.session_state.analysis_complete = True
                        st.success("분석이 완료되었습니다!")

    # 분석 결과가 있을 때만 탭 표시
    if st.session_state.get('analysis_complete', False) and st.session_state.analysis_result:
        tab_names = ["스윙 시퀀스", "각도 그래프", "3D 분석", "상세 메트릭스", "스윙 평가"]
        tabs = st.tabs(tab_names)

        with tabs[0]:
            show_swing_sequence_with_state(st.session_state.temp_path, st.session_state.analysis_result)
        
        with tabs[1]:
            show_angle_graph(st.session_state.analysis_result)
            
        with tabs[2]:
            show_3d_analysis_with_state(st.session_state.analysis_result)
            
        with tabs[3]:
            show_detailed_metrics(st.session_state.analysis_result)
        
        with tabs[4]:
            show_swing_evaluation(st.session_state.analysis_result)

def show_swing_sequence_with_state(temp_path, analysis_result):
    """스윙 시퀀스 표시 (상태 관리 포함)"""
    st.subheader("스윙 시퀀스")
    
    # 모델 가져오기
    models = get_models()
    if models is None:
        st.error("모델을 로드할 수 없습니다.")
        return
    
    _, swing_analyzer, _, _ = models
    
    # 프레임 데이터 일치성 확인
    frames_data = analysis_result.get('frames_data', analysis_result.get('frames', []))
    
    # 탭으로 세 가지 시퀀스 방식 분리
    tab1, tab2, tab3, tab4 = st.tabs([
        "🎭 오버랩 시퀀스", 
        "📋 나란히 배치", 
        "🏃‍♂️ 연속 겹침",
        "🎯 2D 모션"
    ])
    
    with tab1:
        st.markdown("### 🎭 오버랩 스윙 시퀀스")
        st.markdown("각 스윙 단계가 투명도를 조절하여 겹쳐서 표시됩니다. 사람 영역을 자동 크롭하여 더욱 선명하게 볼 수 있습니다.")
        
        try:
            # 오버랩 시퀀스 생성
            overlap_img = create_sequence_image(
                temp_path, 
                analysis_result['key_frames'], 
                overlap_mode=True, 
                analysis_frames=frames_data
            )
            
            if overlap_img is not None:
                overlap_img_rgb = cv2.cvtColor(overlap_img, cv2.COLOR_BGR2RGB)
                st.image(overlap_img_rgb, use_column_width=True)
                
                # 이미지를 파일로 저장하고 다운로드 버튼 제공
                overlap_path = os.path.join(TEMP_DIR, "overlap_sequence.jpg")
                cv2.imwrite(overlap_path, overlap_img)
                
                if os.path.exists(overlap_path):
                    with open(overlap_path, "rb") as file:
                        st.download_button(
                            label="💾 오버랩 시퀀스 다운로드",
                            data=file.read(),
                            file_name="golf_swing_overlap_sequence.jpg",
                            mime="image/jpeg"
                        )
            else:
                st.error("오버랩 시퀀스 이미지를 생성할 수 없습니다.")
                
        except Exception as e:
            logger.error(f"Error creating overlap sequence: {str(e)}")
            st.error(f"오버랩 시퀀스 생성 중 오류: {str(e)}")
    
    with tab2:
        st.markdown("### 📋 나란히 배치 스윙 시퀀스")
        st.markdown("각 스윙 단계가 순서대로 나란히 배치되어 표시됩니다. 사람 영역을 자동 크롭하여 각 단계를 더욱 명확하게 비교할 수 있습니다.")
        
        try:
            # 나란히 배치 시퀀스 생성
            side_img = create_sequence_image(
                temp_path, 
                analysis_result['key_frames'], 
                overlap_mode=False, 
                analysis_frames=frames_data
            )
            
            if side_img is not None:
                side_img_rgb = cv2.cvtColor(side_img, cv2.COLOR_BGR2RGB)
                st.image(side_img_rgb, use_column_width=True)
                
                # 이미지를 파일로 저장하고 다운로드 버튼 제공
                side_path = os.path.join(TEMP_DIR, "side_by_side_sequence.jpg")
                cv2.imwrite(side_path, side_img)
                
                if os.path.exists(side_path):
                    with open(side_path, "rb") as file:
                        st.download_button(
                            label="💾 나란히 배치 시퀀스 다운로드",
                            data=file.read(),
                            file_name="golf_swing_side_by_side_sequence.jpg",
                            mime="image/jpeg"
                        )
            else:
                st.error("나란히 배치 시퀀스 이미지를 생성할 수 없습니다.")
                
        except Exception as e:
            logger.error(f"Error creating side-by-side sequence: {str(e)}")
            st.error(f"나란히 배치 시퀀스 생성 중 오류: {str(e)}")
    
    with tab3:
        st.markdown("### 🏃‍♂️ 연속 겹침 시퀀스")
        st.markdown("**30% 겹침으로 연속적인 스윙 모션을 보여주는 시퀀스**")
        
        if 'continuous_sequence_path' in st.session_state and st.session_state.continuous_sequence_path:
          st.image(st.session_state.continuous_sequence_path, caption="연속 겹침 시퀀스")
          
          # 다운로드 버튼
          if os.path.exists(st.session_state.continuous_sequence_path):
            with open(st.session_state.continuous_sequence_path, "rb") as file:
              st.download_button(
                label="📥 연속 겹침 시퀀스 다운로드",
                data=file.read(),
                file_name="continuous_overlap_sequence.jpg",
                mime="image/jpeg"
              )
        else:
          st.info("비디오를 업로드하고 분석을 완료하면 연속 겹침 시퀀스가 표시됩니다.")

    with tab4:
        st.markdown("### 🎯 2D 모션 시각화")
        st.markdown("**프레임별 2D 포즈를 시각화하고 스윙 모션을 분석합니다.**")
        
        # 세션 상태 초기화
        if 'motion_2d_frame_idx' not in st.session_state:
            st.session_state.motion_2d_frame_idx = 0
        if 'motion_2d_is_playing' not in st.session_state:
            st.session_state.motion_2d_is_playing = False
        
        # 프레임 데이터 확인
        if not frames_data:
            st.warning("분석된 프레임 데이터가 없습니다.")
            return
        
        # 인덱스 범위 확인
        if st.session_state.motion_2d_frame_idx >= len(frames_data):
            st.session_state.motion_2d_frame_idx = len(frames_data) - 1
        
        # 컨트롤 섹션
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 프레임 슬라이더
            st.session_state.motion_2d_frame_idx = st.slider(
                "프레임 선택", 
                0, 
                len(frames_data) - 1, 
                st.session_state.motion_2d_frame_idx,
                key="motion_2d_slider"
            )
            
            # 재생 컨트롤
            cols = st.columns(4)
            if cols[0].button("⏮️ 처음으로", key="motion_2d_first"):
                st.session_state.motion_2d_frame_idx = 0
                st.session_state.motion_2d_is_playing = False
            if cols[1].button("▶️ 재생" if not st.session_state.motion_2d_is_playing else "⏸️ 일시정지", key="motion_2d_play"):
                st.session_state.motion_2d_is_playing = not st.session_state.motion_2d_is_playing
            if cols[2].button("⏭️ 끝으로", key="motion_2d_last"):
                st.session_state.motion_2d_frame_idx = len(frames_data) - 1
                st.session_state.motion_2d_is_playing = False
            if cols[3].button("🔄 리셋", key="motion_2d_reset"):
                st.session_state.motion_2d_frame_idx = 0
                st.session_state.motion_2d_is_playing = False
        
        with col2:
            # 현재 프레임 정보
            current_frame_data = frames_data[st.session_state.motion_2d_frame_idx]
            st.markdown("### 현재 프레임 정보")
            st.metric("프레임 번호", st.session_state.motion_2d_frame_idx)
            
            # 주요 각도 표시
            angles = current_frame_data.get('angles', {})
            if angles:
                st.metric("어깨 회전", f"{angles.get('shoulder_angle', 0):.1f}°")
                st.metric("오른팔 각도", f"{angles.get('right_arm', 0):.1f}°")
                st.metric("왼팔 각도", f"{angles.get('left_arm', 0):.1f}°")
        
        # 2D 포즈 시각화
        st.markdown("### 2D 포즈 시각화")
        try:
            # Plotly를 사용한 2D 포즈 시각화
            fig = create_pose_visualization(current_frame_data)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"2D 포즈 시각화 중 오류: {str(e)}")
        
        # 키 프레임 표시
        key_frames = analysis_result.get('key_frames', {})
        if key_frames:
            st.markdown("### 주요 프레임")
            for phase, frame_idx in key_frames.items():
                if frame_idx == st.session_state.motion_2d_frame_idx:
                    st.success(f"현재 프레임은 '{phase}' 단계입니다.")
        
        # 자동 재생 로직
        if st.session_state.motion_2d_is_playing:
            if st.session_state.motion_2d_frame_idx < len(frames_data) - 1:
                st.session_state.motion_2d_frame_idx += 1
                time.sleep(0.1)  # 프레임 간 딜레이
                st.rerun()
            else:
                st.session_state.motion_2d_is_playing = False
                st.rerun()

def show_3d_analysis_with_state(analysis_result):
    """3D 분석 결과 표시 (상태 관리 포함)"""
    st.subheader("3D 스윙 분석")
    
    # 프레임 데이터 키 일치성 확인
    frames_data = analysis_result.get('frames_data', analysis_result.get('frames', []))
    if not frames_data:
        st.error("분석된 프레임 데이터가 없습니다.")
        return
    
    # 세션 상태 초기화
    if 'three_d_frame_idx' not in st.session_state:
        st.session_state.three_d_frame_idx = 0
    if 'three_d_is_playing' not in st.session_state:
        st.session_state.three_d_is_playing = False
    
    # 인덱스 범위 확인 및 수정
    if st.session_state.three_d_frame_idx >= len(frames_data):
        st.session_state.three_d_frame_idx = len(frames_data) - 1
    
    # 3D 포즈 시각화
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("3D 포즈 뷰어")
        
        # 세부 수준 선택
        detail_level = st.selectbox(
            "🎨 세부 수준 선택",
            options=['basic', 'medium', 'full'],
            index=2,  # 기본값: full
            help="basic: 기본 골격만, medium: 손발 추가, full: 모든 세부사항"
        )
        
        # 세부 수준 설명
        if detail_level == 'basic':
            st.info("💡 기본 골격: 어깨, 팔, 몸통, 다리의 주요 뼈대만 표시")
        elif detail_level == 'medium':
            st.info("💡 중간 세부: 기본 골격 + 손과 발의 세부 구조 표시")
        else:
            st.info("💡 모든 세부사항: 얼굴, 손, 발을 포함한 33개 모든 포인트와 부드러운 곡선 표시")
        
        # 궤적 표시 옵션
        show_trajectory = st.checkbox("🏌️ 스윙 궤적 표시", value=False, help="클럽(손목)의 스윙 궤적을 표시합니다")
        
        st.session_state.three_d_frame_idx = st.slider(
            "프레임 선택", 
            0, 
            len(frames_data) - 1, 
            st.session_state.three_d_frame_idx,
            key="3d_frame_slider"
        )
        
        # Plotly를 사용한 3D 시각화
        current_frame = frames_data[st.session_state.three_d_frame_idx]
        trajectory_data = frames_data if show_trajectory else None
        fig = create_3d_pose_plot(current_frame, detail_level, show_trajectory, trajectory_data)
        st.plotly_chart(fig, use_container_width=True)
        
        # 재생 컨트롤
        cols = st.columns(3)
        if cols[0].button("⏮️ 처음으로", key="3d_first"):
            st.session_state.three_d_frame_idx = 0
            st.session_state.three_d_is_playing = False
        if cols[1].button("▶️ 재생" if not st.session_state.three_d_is_playing else "⏸️ 일시정지", key="3d_play"):
            st.session_state.three_d_is_playing = not st.session_state.three_d_is_playing
        if cols[2].button("⏭️ 끝으로", key="3d_last"):
            st.session_state.three_d_frame_idx = len(frames_data) - 1
            st.session_state.three_d_is_playing = False
    
    with col2:
        st.subheader("3D 메트릭스")
        show_3d_metrics(analysis_result, st.session_state.three_d_frame_idx)
    
    # 자동 재생 로직
    if st.session_state.three_d_is_playing:
        if st.session_state.three_d_frame_idx < len(frames_data) - 1:
            st.session_state.three_d_frame_idx += 1
            time.sleep(0.1)  # 프레임 간 딜레이
            st.rerun()
        else:
            st.session_state.three_d_is_playing = False
            st.rerun()

def create_pose_visualization(frame_data: Dict) -> go.Figure:
    """프레임 데이터를 사용하여 2D 포즈 시각화 생성 - 개선된 버전 (더 많은 점, 검은 배경)"""
    # Plotly 피겨 생성
    fig = go.Figure()
    
    # 확장된 랜드마크 연결 정의 (더 많은 연결선)
    basic_connections = [
        ('left_shoulder', 'right_shoulder'),
        ('left_shoulder', 'left_elbow'),
        ('left_elbow', 'left_wrist'),
        ('right_shoulder', 'right_elbow'),
        ('right_elbow', 'right_wrist'),
        ('left_shoulder', 'left_hip'),
        ('right_shoulder', 'right_hip'),
        ('left_hip', 'right_hip'),
        ('left_hip', 'left_knee'),
        ('left_knee', 'left_ankle'),
        ('right_hip', 'right_knee'),
        ('right_knee', 'right_ankle')
    ]
    
    # 얼굴 연결 (있는 경우)
    face_connections = [
        ('nose', 'left_eye'), ('nose', 'right_eye'),
        ('left_eye', 'left_ear'), ('right_eye', 'right_ear'),
        ('mouth_left', 'mouth_right')
    ]
    
    # 손 연결 (있는 경우)
    hand_connections = [
        ('left_wrist', 'left_pinky'), ('left_wrist', 'left_index'), ('left_wrist', 'left_thumb'),
        ('right_wrist', 'right_pinky'), ('right_wrist', 'right_index'), ('right_wrist', 'right_thumb')
    ]
    
    # 발 연결 (있는 경우)
    foot_connections = [
        ('left_ankle', 'left_heel'), ('left_heel', 'left_foot_index'),
        ('right_ankle', 'right_heel'), ('right_heel', 'right_foot_index')
    ]
    
    landmarks = frame_data['landmarks']
    
    # 모든 랜드마크 점 추가 (색상별로 구분)
    for name, point in landmarks.items():
        # 포인트 타입에 따라 색상과 크기 구분
        if 'eye' in name or 'ear' in name or 'nose' in name or 'mouth' in name:
            color = '#FFD700'  # 골드 (얼굴)
            size = 8
        elif 'wrist' in name or 'pinky' in name or 'index' in name or 'thumb' in name:
            color = '#FF69B4'  # 핫 핑크 (손)
            size = 10
        elif 'ankle' in name or 'heel' in name or 'foot' in name:
            color = '#00FF7F'  # 스프링 그린 (발)
            size = 10
        else:
            color = '#FFFFFF'  # 흰색 (기본 골격)
            size = 12
        
        fig.add_trace(go.Scatter(
            x=[point[0]], 
            y=[point[1]],
            mode='markers+text',
            name=name,
            text=[name],
            textposition='top center',
            marker=dict(
                size=size, 
                color=color,
                line=dict(color='black', width=1)  # 테두리 추가
            ),
            textfont=dict(
                size=8,
                color='white'  # 텍스트를 흰색으로
            ),
            showlegend=False,
            hovertemplate=f'<b>{name}</b><br>x: %{{x:.3f}}<br>y: %{{y:.3f}}<extra></extra>'
        ))
    
    # 연결선 추가 함수
    def add_connections(connections, color, width=3):
        for start, end in connections:
            if start in landmarks and end in landmarks:
                start_point = landmarks[start]
                end_point = landmarks[end]
                fig.add_trace(go.Scatter(
                    x=[start_point[0], end_point[0]],
                    y=[start_point[1], end_point[1]],
                    mode='lines',
                    line=dict(width=width, color=color),
                    showlegend=False,
                    hoverinfo='skip'
                ))
    
    # 각 부위별로 다른 색상의 연결선 추가
    add_connections(basic_connections, '#00D4FF', 4)      # 시아노 블루 (기본 골격)
    add_connections(face_connections, '#FFB347', 2)       # 피치 (얼굴)
    add_connections(hand_connections, '#DA70D6', 2)       # 오키드 (손)
    add_connections(foot_connections, '#32CD32', 3)       # 라임 그린 (발)
    
    # 데이터 범위 계산 (오토 스케일을 위해)
    x_coords = [point[0] for point in landmarks.values()]
    y_coords = [point[1] for point in landmarks.values()]
    
    # 여백을 위한 패딩 계산
    x_range = max(x_coords) - min(x_coords)
    y_range = max(y_coords) - min(y_coords)
    padding = max(x_range, y_range) * 0.1  # 10% 패딩
    
    x_min, x_max = min(x_coords) - padding, max(x_coords) + padding
    y_min, y_max = min(y_coords) - padding, max(y_coords) + padding
    
    # 레이아웃 설정 (검은 배경, 오토 스케일)
    fig.update_layout(
        showlegend=False,
        xaxis=dict(
            title='X (좌우)',
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.3)',  # 회색 반투명 그리드
            color='white',
            zeroline=False,
            range=[x_min, x_max]  # 데이터에 맞춘 범위
        ),
        yaxis=dict(
            title='Y (상하)',
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.3)',  # 회색 반투명 그리드
            color='white',
            zeroline=False,
            range=[y_max, y_min],  # y축 반전 (위쪽이 0에 가깝게)
            scaleanchor="x",
            scaleratio=1
        ),
        margin=dict(l=50, r=50, t=50, b=50),
        plot_bgcolor='black',      # 플롯 배경을 검은색으로
        paper_bgcolor='black',     # 전체 배경을 검은색으로
        font=dict(color='white'),  # 텍스트 색상을 흰색으로
        width=600,
        height=600
    )
    
    return fig

def create_3d_pose_plot(frame_data: Dict, detail_level: str = 'full', 
                       show_trajectory: bool = False, trajectory_data: Optional[List[Dict]] = None) -> go.Figure:
    """프레임 데이터를 사용하여 3D 포즈 플롯 생성 - 개선된 버전"""
    try:
        # 3D 시각화 클래스 사용
        from visualization_3d import SwingVisualizer3D
        visualizer = SwingVisualizer3D()
        
        # 세부 수준에 따라 3D 플롯 생성
        fig = visualizer.create_pose_plot(frame_data, show_trajectory=show_trajectory, 
                                        trajectory_data=trajectory_data, detail_level=detail_level)
        
        # 좌표축과 그리드 추가
        axis_length = 0.5
        origin = [0, 0, 0]
        
        # X축 (빨간색) - 좌우
        fig.add_trace(go.Scatter3d(
            x=[origin[0], origin[0] + axis_length],
            y=[origin[1], origin[1]],
            z=[origin[2], origin[2]],
            mode='lines+text',
            line=dict(color='red', width=3),
            text=['', 'X'],
            showlegend=False
        ))
        
        # Y축 (초록색) - 상하
        fig.add_trace(go.Scatter3d(
            x=[origin[0], origin[0]],
            y=[origin[1], origin[1] + axis_length],
            z=[origin[2], origin[2]],
            mode='lines+text',
            line=dict(color='green', width=3),
            text=['', 'Y'],
            showlegend=False
        ))
        
        # Z축 (파란색) - 앞뒤
        fig.add_trace(go.Scatter3d(
            x=[origin[0], origin[0]],
            y=[origin[1], origin[1]],
            z=[origin[2], origin[2] + axis_length],
            mode='lines+text',
            line=dict(color='blue', width=3),
            text=['', 'Z'],
            showlegend=False
        ))
        
        # 바닥 그리드 추가 (X-Z 평면)
        grid_size = 1.0
        grid_points = np.linspace(-grid_size/2, grid_size/2, 10)
        for x in grid_points:
            fig.add_trace(go.Scatter3d(
                x=[x, x],
                y=[0, 0],
                z=[-grid_size/2, grid_size/2],
                mode='lines',
                line=dict(color='gray', width=1),
                showlegend=False
            ))
        for z in grid_points:
            fig.add_trace(go.Scatter3d(
                x=[-grid_size/2, grid_size/2],
                y=[0, 0],
                z=[z, z],
                mode='lines',
                line=dict(color='gray', width=1),
                showlegend=False
            ))
        
        # 레이아웃 업데이트 (크기 조정)
        fig.update_layout(
            width=800,
            height=600
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating 3D pose plot: {str(e)}")
        return go.Figure()

def show_3d_metrics(analysis_result, frame_idx):
    """3D 메트릭스 표시"""
    frame_data = analysis_result['frames'][frame_idx]
    
    # 현재 프레임의 3D 각도 계산
    angles_3d = calculate_3d_angles(frame_data['landmarks'])
    
    # 메트릭스 표시
    st.metric("척추 각도", f"{angles_3d['spine_angle']:.1f}°")
    st.metric("어깨 회전", f"{angles_3d['shoulder_rotation']:.1f}°")
    st.metric("힙 회전", f"{angles_3d['hip_rotation']:.1f}°")
    st.metric("팔 각도 (오른쪽)", f"{angles_3d['right_arm_angle']:.1f}°")
    st.metric("무릎 각도 (오른쪽)", f"{angles_3d['right_knee_angle']:.1f}°")

def calculate_3d_angles(landmarks):
    """3D 각도 계산"""
    import numpy as np
    
    def calculate_angle(p1, p2, p3):
        """세 점 사이의 3D 각도 계산"""
        v1 = np.array(p1) - np.array(p2)
        v2 = np.array(p3) - np.array(p2)
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        return np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
    
    # 척추 각도
    hip_center = np.mean([landmarks['left_hip'], landmarks['right_hip']], axis=0)
    shoulder_center = np.mean([landmarks['left_shoulder'], landmarks['right_shoulder']], axis=0)
    vertical = hip_center + np.array([0, 1, 0])
    spine_angle = calculate_angle(vertical, hip_center, shoulder_center)
    
    # 어깨 회전
    shoulder_vector = np.array(landmarks['right_shoulder']) - np.array(landmarks['left_shoulder'])
    forward = np.array([0, 0, 1])
    shoulder_rotation = np.degrees(np.arctan2(shoulder_vector[0], shoulder_vector[2]))
    
    # 힙 회전
    hip_vector = np.array(landmarks['right_hip']) - np.array(landmarks['left_hip'])
    hip_rotation = np.degrees(np.arctan2(hip_vector[0], hip_vector[2]))
    
    # 오른팔 각도
    right_arm_angle = calculate_angle(
        landmarks['right_shoulder'],
        landmarks['right_elbow'],
        landmarks['right_wrist']
    )
    
    # 오른쪽 무릎 각도
    right_knee_angle = calculate_angle(
        landmarks['right_hip'],
        landmarks['right_knee'],
        landmarks['right_ankle']
    )
    
    return {
        'spine_angle': spine_angle,
        'shoulder_rotation': shoulder_rotation,
        'hip_rotation': hip_rotation,
        'right_arm_angle': right_arm_angle,
        'right_knee_angle': right_knee_angle
    }

def show_angle_graph(analysis_result):
    """각도 그래프 표시"""
    st.subheader("각도 변화 그래프")
    graph_bytes = create_angle_graph(analysis_result)
    if graph_bytes:
        st.image(graph_bytes)
        
        # 그래프 해석 추가
        st.markdown("### 📊 그래프 해석")
        metrics = analysis_result.get('metrics', {})
        
        st.markdown("""
        #### 주요 지표 설명:
        - **어깨 회전 (Shoulders)**: 백스윙에서 어깨의 회전 각도를 보여줍니다. 이상적인 최대 회전은 80도 이상입니다.
        - **팔 각도 (Right/Left Arm)**: 팔의 펴짐 정도를 나타냅니다. 어드레스와 임팩트에서 165-180도가 이상적입니다.
        - **힙 회전 (Hips)**: 골반의 회전 각도입니다. 임팩트 시점에서 45도 이상이 권장됩니다.
        """)
        
        # 현재 스윙의 특징 분석
        st.markdown("#### 🎯 현재 스윙 분석")
        shoulder_rotation = metrics.get('shoulder_rotation', 0)
        impact_angle = metrics.get('impact_angle', 0)
        hip_rotation = metrics.get('hip_rotation', 0)
        
        analysis_text = []
        if shoulder_rotation >= 80:
            analysis_text.append("✅ 어깨 회전이 충분합니다 ({}도)".format(round(shoulder_rotation, 1)))
        else:
            analysis_text.append("❌ 어깨 회전이 부족합니다 ({}도, 목표: 80도 이상)".format(round(shoulder_rotation, 1)))
            
        if 165 <= impact_angle <= 180:
            analysis_text.append("✅ 임팩트 시 팔 각도가 이상적입니다 ({}도)".format(round(impact_angle, 1)))
        else:
            analysis_text.append("❌ 임팩트 시 팔 각도 개선이 필요합니다 ({}도, 목표: 165-180도)".format(round(impact_angle, 1)))
            
        if hip_rotation >= 45:
            analysis_text.append("✅ 힙 회전이 충분합니다 ({}도)".format(round(hip_rotation, 1)))
        else:
            analysis_text.append("❌ 힙 회전이 부족합니다 ({}도, 목표: 45도 이상)".format(round(hip_rotation, 1)))
        
        for text in analysis_text:
            st.markdown(text)

def show_detailed_metrics(analysis_result):
    """상세 메트릭스 표시"""
    st.subheader("상세 메트릭스")
    metrics = analysis_result['metrics']
    cols = st.columns(3)
    for idx, (metric_name, value) in enumerate(metrics.items()):
        with cols[idx % 3]:
            st.metric(
                label=metric_name,
                value=f"{value:.2f}°" if isinstance(value, (int, float)) else value
            )

def show_swing_evaluation(analysis_result):
    """스윙 평가 표시"""
    st.subheader("스윙 평가")
    
    # 평가 기준 표 생성
    st.markdown("### ⚖️ 평가 기준")
    
    criteria_data = {
        "스윙 단계": ["어드레스 자세", "어드레스 자세", 
                    "탑 자세", "탑 자세",
                    "임팩트 자세", "임팩트 자세",
                    "팔로우 스루", "팔로우 스루",
                    "피니시 자세", "피니시 자세"],
        "평가 항목": ["팔 각도", "자세 안정성",
                    "어깨 회전", "머리 안정성",
                    "팔 각도", "힙 회전",
                    "팔로우 스루 완성도", "균형",
                    "마무리 동작", "균형"],
        "기준값": ["165-180도", "척추 각도 30도 이상",
                 "최소 80도 이상", "초기 위치에서 움직임 0.1 이하",
                 "165-180도", "45도 이상",
                 "팔 각도 120도 이하", "오른쪽 무릎 각도 160도 이하",
                 "팔 각도 120도 이하", "오른쪽 무릎 각도 160도 이하"],
        "중요도": ["⭐⭐⭐", "⭐⭐",
                 "⭐⭐⭐", "⭐⭐",
                 "⭐⭐⭐", "⭐⭐⭐",
                 "⭐⭐", "⭐⭐",
                 "⭐⭐", "⭐⭐"]
    }
    
    import pandas as pd
    criteria_df = pd.DataFrame(criteria_data)
    
    # 표 스타일링을 위한 CSS
    st.markdown("""
    <style>
    table {
        width: 100%;
        border-collapse: collapse;
    }
    th {
        background-color: #1E1E1E;
        color: white;
        text-align: center !important;
    }
    td {
        text-align: center !important;
    }
    tr:nth-child(odd) {
        background-color: #2E2E2E;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 표 출력
    st.table(criteria_df)
    
    # 중요도 설명
    st.markdown("""
    #### 📝 중요도 설명
    - ⭐⭐⭐ : 스윙의 핵심 요소
    - ⭐⭐ : 보조적 중요 요소
    """)
    
    st.markdown("---")
    
    if 'evaluations' in analysis_result:
        evaluations = analysis_result['evaluations']
        frames_data = analysis_result['frames']
        key_frames = analysis_result['key_frames']
        
        # 각 스윙 단계별 평가 표시
        phase_names = {
            'address': '어드레스 자세',
            'top': '탑 자세',
            'impact': '임팩트 자세',
            'follow_through': '팔로우 스루',
            'finish': '피니시 자세'
        }
        
        check_names = {
            'Arm Angle Straight': '팔이 곧게 뻗어있나요? (165-180도)',
            'Posture Stable': '자세가 안정적인가요? (척추 각도 30도 이상)',
            'Shoulder Rotation Good': '어깨 회전이 충분한가요? (80도 이상)',
            'Head Stable': '머리가 안정적인가요? (움직임 0.1 이하)',
            'Hip Rotation Good': '힙 회전이 충분한가요? (45도 이상)',
            'Follow Through Complete': '팔로우 스루가 완성되었나요? (120도 이하)',
            'Balance Maintained': '균형이 잘 잡혔나요? (무릎 각도 160도 이하)',
            'Arm Straight': '팔이 곧게 뻗어있나요? (165-180도)'
        }
        
        for phase, phase_evaluations in evaluations.items():
            st.markdown(f"### {phase_names.get(phase, phase)}")
            
            # 현재 프레임의 각도 데이터 가져오기
            frame_idx = key_frames.get(phase, 0)
            current_frame = frames_data[frame_idx] if frame_idx < len(frames_data) else None
            
            # 평가 결과를 표 형식으로 표시
            results = []
            for check_name, is_passed in phase_evaluations.items():
                current_value = None
                if current_frame:
                    if check_name in ['Arm Angle Straight', 'Arm Straight']:
                        current_value = current_frame['angles'].get('right_arm', 0)
                    elif check_name == 'Posture Stable':
                        current_value = current_frame['angles'].get('spine_angle', 0)
                    elif check_name == 'Shoulder Rotation Good':
                        current_value = current_frame['angles'].get('shoulder_angle', 0)
                    elif check_name == 'Hip Rotation Good':
                        current_value = current_frame['angles'].get('hip_angle', 0)
                    elif check_name == 'Balance Maintained':
                        current_value = current_frame['angles'].get('right_leg', 0)
                    elif check_name == 'Head Stable':
                        current_value = analysis_result['metrics'].get('head_movement', 0)
                
                result_text = "✅ 좋습니다" if is_passed else "❌ 개선이 필요합니다"
                if current_value is not None:
                    result_text += f" (현재: {current_value:.1f}°)"
                
                results.append({
                    "체크 항목": check_names.get(check_name, check_name),
                    "결과": result_text
                })
            
            # 데이터프레임으로 변환하여 표시
            df = pd.DataFrame(results)
            st.table(df)
            
            # 단계별 조언 추가
            if not all(phase_evaluations.values()):
                st.markdown("#### 💡 조언")
                for check_name, is_passed in phase_evaluations.items():
                    if not is_passed:
                        current_value = None
                        if current_frame:
                            if check_name in ['Arm Angle Straight', 'Arm Straight']:
                                current_value = current_frame['angles'].get('right_arm', 0)
                            elif check_name == 'Posture Stable':
                                current_value = current_frame['angles'].get('spine_angle', 0)
                            elif check_name == 'Shoulder Rotation Good':
                                current_value = current_frame['angles'].get('shoulder_angle', 0)
                            elif check_name == 'Hip Rotation Good':
                                current_value = current_frame['angles'].get('hip_angle', 0)
                            elif check_name == 'Balance Maintained':
                                current_value = current_frame['angles'].get('right_leg', 0)
                            elif check_name == 'Head Stable':
                                current_value = analysis_result['metrics'].get('head_movement', 0)
                        
                        advice = get_swing_advice(phase, check_name)
                        if current_value is not None:
                            advice += f" (현재: {current_value:.1f}°)"
                        st.info(advice)
            
            # 구분선 추가
            st.markdown("---")
    else:
        st.warning("평가 데이터가 없습니다.")

def get_swing_advice(phase: str, check_name: str) -> str:
    """스윙 단계와 체크 항목에 따른 조언을 반환합니다."""
    advice_dict = {
        'address': {
            'Arm Angle Straight': "팔을 더 곧게 펴보세요. 이상적인 각도는 165-180도 입니다.",
            'Posture Stable': "상체를 약간 숙이고, 무게 중심을 발 중앙에 두어 안정적인 자세를 만드세요."
        },
        'top': {
            'Shoulder Rotation Good': "백스윙 시 어깨 회전을 더 크게 해보세요. 파워를 위해서는 최소 80도 이상이 필요합니다.",
            'Head Stable': "백스윙 중에도 머리 위치를 최대한 고정하세요. 일관된 스윙을 위해 중요합니다."
        },
        'impact': {
            'Arm Straight': "임팩트 시점에서 팔을 더 곧게 펴보세요. 이상적인 각도는 165-180도 입니다.",
            'Hip Rotation Good': "임팩트 시 힙 회전을 더 적극적으로 해보세요. 최소 45도 이상 회전이 필요합니다."
        },
        'follow_through': {
            'Follow Through Complete': "팔로우 스루 동작을 더 크게 해보세요. 자연스러운 마무리가 중요합니다.",
            'Balance Maintained': "팔로우 스루 시 균형을 잘 잡아주세요. 체중 이동이 자연스러워야 합니다."
        },
        'finish': {
            'Follow Through Complete': "피니시 동작을 완성도 있게 마무리해주세요. 상체를 목표 방향으로 회전시키세요.",
            'Balance Maintained': "피니시 자세에서 균형을 잘 잡아주세요. 오른발 안쪽으로 체중을 이동하세요."
        }
    }
    
    return advice_dict.get(phase, {}).get(check_name, "자세를 전반적으로 점검해보세요.")

def create_continuous_overlap_sequence(frames: List[Tuple[str, np.ndarray]]) -> np.ndarray:
    """연속 겹침 방식으로 스윙 시퀀스 생성 (사람 영역 크롭 + 겹침)"""
    if not frames:
        raise ValueError("프레임이 없습니다.")
    
    # 각 프레임은 이미 크롭된 상태로 전달됨
    target_height = 500  # 목표 높이
    
    # 모든 프레임을 동일한 높이로 리사이즈
    resized_frames = []
    for phase, frame in frames:
        h, w = frame.shape[:2]
        scale = target_height / h
        new_width = int(w * scale)
        resized = cv2.resize(frame, (new_width, target_height))
        resized_frames.append((phase, resized))
    
    if not resized_frames:
        raise ValueError("리사이즈된 프레임이 없습니다.")
    
    # 겹침 비율 (각 프레임이 다음 프레임과 얼마나 겹칠지)
    overlap_ratio = 0.3  # 30% 겹침
    
    # 전체 너비 계산
    total_width = 0
    frame_widths = [frame.shape[1] for _, frame in resized_frames]
    
    # 첫 번째 프레임은 전체 너비
    total_width += frame_widths[0]
    
    # 나머지 프레임들은 겹침을 고려한 너비
    for i in range(1, len(frame_widths)):
        total_width += int(frame_widths[i] * (1 - overlap_ratio))
    
    # 결과 이미지 생성
    result = np.zeros((target_height, total_width, 3), dtype=np.uint8)
    
    # 첫 번째 프레임 배치
    x_offset = 0
    phase, first_frame = resized_frames[0]
    result[:, x_offset:x_offset + first_frame.shape[1]] = first_frame
    
    # 단계 라벨 추가 (첫 번째 프레임)
    cv2.putText(result, phase.upper(), 
               (x_offset + 10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(result, phase.upper(), 
               (x_offset + 10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
    
    # 나머지 프레임들을 겹쳐서 배치
    for i in range(1, len(resized_frames)):
        phase, frame = resized_frames[i]
        
        # 이전 프레임과 겹치도록 x_offset 계산
        prev_width = resized_frames[i-1][1].shape[1]
        x_offset += int(prev_width * (1 - overlap_ratio))
        
        # 겹치는 영역 계산
        frame_end = x_offset + frame.shape[1]
        if frame_end > total_width:
            frame_end = total_width
            frame = frame[:, :total_width - x_offset]
        
        # 알파 블렌딩으로 자연스러운 겹침 효과
        alpha = 0.7  # 투명도
        
        # 현재 프레임 영역
        current_region = result[:, x_offset:frame_end]
        
        if current_region.shape[1] > 0 and frame.shape[1] > 0:
            # 겹치는 부분만 블렌딩
            overlap_width = min(current_region.shape[1], frame.shape[1])
            
            if overlap_width > 0:
                # 안전한 영역 추출
                safe_current = current_region[:, :overlap_width]
                safe_frame = frame[:, :overlap_width]
                
                # 높이가 다른 경우 맞춤
                if safe_current.shape[0] != safe_frame.shape[0]:
                    min_height = min(safe_current.shape[0], safe_frame.shape[0])
                    safe_current = safe_current[:min_height, :]
                    safe_frame = safe_frame[:min_height, :]
                
                # 채널 수 확인 및 맞춤
                if len(safe_current.shape) == 3 and len(safe_frame.shape) == 3:
                    if safe_current.shape[2] == safe_frame.shape[2]:
                        # 동일한 채널 수인 경우 블렌딩
                        try:
                            blended = cv2.addWeighted(
                                safe_current.astype(np.uint8), 
                                1 - alpha, 
                                safe_frame.astype(np.uint8), 
                                alpha, 
                                0
                            )
                            result[:blended.shape[0], x_offset:x_offset + overlap_width] = blended
                        except Exception as e:
                            logger.warning(f"Blending failed, using overlay: {str(e)}")
                            # 블렌딩 실패 시 단순 오버레이
                            result[:safe_frame.shape[0], x_offset:x_offset + overlap_width] = safe_frame
                    else:
                        # 채널 수가 다른 경우 단순 오버레이
                        result[:safe_frame.shape[0], x_offset:x_offset + overlap_width] = safe_frame
                else:
                    # 차원이 다른 경우 단순 오버레이
                    result[:safe_frame.shape[0], x_offset:x_offset + overlap_width] = safe_frame
                
                # 겹치지 않는 부분은 그대로 추가
                if frame.shape[1] > overlap_width:
                    remaining_width = min(frame.shape[1] - overlap_width, total_width - x_offset - overlap_width)
                    if remaining_width > 0:
                        start_col = x_offset + overlap_width
                        end_col = start_col + remaining_width
                        frame_start_col = overlap_width
                        frame_end_col = overlap_width + remaining_width
                        
                        # 안전한 범위 내에서만 복사
                        if (end_col <= total_width and 
                            frame_end_col <= frame.shape[1] and 
                            frame.shape[0] <= target_height):
                            result[:frame.shape[0], start_col:end_col] = frame[:, frame_start_col:frame_end_col]
        
        # 단계 라벨 추가
        label_x = x_offset + frame.shape[1] // 2 - 30
        cv2.putText(result, phase.upper(), 
                   (max(0, label_x), 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(result, phase.upper(), 
                   (max(0, label_x), 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
    
    return result

def auto_crop_person_area(frame: np.ndarray, landmarks_data: Dict) -> np.ndarray:
    """랜드마크 데이터를 이용해 사람 영역을 자동으로 크롭합니다."""
    try:
        h, w = frame.shape[:2]
        
        # 주요 랜드마크만 사용 (신뢰성 높은 포인트들)
        key_landmarks = [
            'left_shoulder', 'right_shoulder',
            'left_elbow', 'right_elbow', 
            'left_wrist', 'right_wrist',
            'left_hip', 'right_hip',
            'left_knee', 'right_knee',
            'left_ankle', 'right_ankle'
        ]
        
        valid_points = []
        for landmark_name in key_landmarks:
            if landmark_name in landmarks_data and landmarks_data[landmark_name]:
                point = landmarks_data[landmark_name]
                if len(point) >= 2:
                    # 좌표가 0-1 사이의 정규화된 값인지 확인
                    x, y = point[0], point[1]
                    
                    # 정규화된 좌표를 픽셀 좌표로 변환
                    if 0 <= x <= 1 and 0 <= y <= 1:
                        pixel_x = int(x * w)
                        pixel_y = int(y * h)
                    else:
                        # 이미 픽셀 좌표인 경우
                        pixel_x = int(x)
                        pixel_y = int(y)
                    
                    # 유효한 범위 내의 좌표만 추가
                    if 0 <= pixel_x < w and 0 <= pixel_y < h:
                        valid_points.append([pixel_x, pixel_y])
        
        if len(valid_points) < 4:  # 최소 4개의 유효한 포인트가 필요
            logger.warning(f"Not enough valid landmarks: {len(valid_points)}")
            # 엣지 감지 방법으로 대체
            return crop_using_edge_detection(frame)
        
        # 바운딩 박스 계산
        points = np.array(valid_points)
        min_x, min_y = np.min(points, axis=0)
        max_x, max_y = np.max(points, axis=0)
        
        # 바운딩 박스 크기 계산
        bbox_width = max_x - min_x
        bbox_height = max_y - min_y
        
        # 여유 공간 추가 (바운딩 박스 크기의 10%)
        padding_x = max(int(bbox_width * 0.1), 20)  # 최소 20픽셀
        padding_y = max(int(bbox_height * 0.1), 20)  # 최소 20픽셀
        
        # 최종 크롭 영역 계산
        x1 = max(0, min_x - padding_x)
        y1 = max(0, min_y - padding_y)
        x2 = min(w, max_x + padding_x)
        y2 = min(h, max_y + padding_y)
        
        # 최소 크기 보장 (너무 작으면 확장)
        min_width = 150
        min_height = 200
        
        if x2 - x1 < min_width:
            center_x = (x1 + x2) // 2
            half_width = min_width // 2
            x1 = max(0, center_x - half_width)
            x2 = min(w, center_x + half_width)
        
        if y2 - y1 < min_height:
            center_y = (y1 + y2) // 2
            half_height = min_height // 2
            y1 = max(0, center_y - half_height)
            y2 = min(h, center_y + half_height)
        
        logger.debug(f"Crop area: ({x1}, {y1}) to ({x2}, {y2}) from frame size ({w}, {h})")
        
        # 크롭 실행
        cropped = frame[y1:y2, x1:x2]
        
        # 크롭된 이미지가 너무 작으면 원본 반환
        if cropped.shape[0] < 50 or cropped.shape[1] < 50:
            logger.warning("Cropped image too small, returning original")
            return frame
        
        return cropped
        
    except Exception as e:
        logger.error(f"Error in auto_crop_person_area: {str(e)}")
        # 에러 발생 시 엣지 감지 방법으로 대체
        return crop_using_edge_detection(frame)

def crop_using_edge_detection(frame: np.ndarray) -> np.ndarray:
    """엣지 감지를 이용한 사람 영역 크롭 (대체 방법)"""
    try:
        h, w = frame.shape[:2]
        
        # 그레이스케일 변환
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 가우시안 블러로 노이즈 제거
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 엣지 감지
        edges = cv2.Canny(blurred, 50, 150)
        
        # 모폴로지 연산으로 엣지 연결
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        
        # 컨투어 찾기
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # 가장 큰 컨투어들 중에서 중앙에 가까운 것 선택
            large_contours = [c for c in contours if cv2.contourArea(c) > 1000]
            
            if large_contours:
                # 중앙에 가장 가까운 큰 컨투어 선택
                center_x, center_y = w // 2, h // 2
                best_contour = min(large_contours, 
                                 key=lambda c: np.linalg.norm(
                                     np.array(cv2.boundingRect(c)[:2]) + 
                                     np.array(cv2.boundingRect(c)[2:]) // 2 - 
                                     np.array([center_x, center_y])
                                 ))
                
                x, y, cw, ch = cv2.boundingRect(best_contour)
                
                # 여유 공간 추가
                padding = 30
                x = max(0, x - padding)
                y = max(0, y - padding)
                cw = min(w - x, cw + 2 * padding)
                ch = min(h - y, ch + 2 * padding)
                
                logger.debug(f"Edge detection crop: ({x}, {y}) size ({cw}, {ch})")
                return frame[y:y+ch, x:x+cw]
        
        # 컨투어를 찾지 못한 경우 중앙 부분 크롭
        logger.warning("No suitable contours found, using center crop")
        crop_w = int(w * 0.7)  # 70% 너비
        crop_h = int(h * 0.9)  # 90% 높이
        start_x = (w - crop_w) // 2
        start_y = (h - crop_h) // 2
        
        return frame[start_y:start_y+crop_h, start_x:start_x+crop_w]
        
    except Exception as e:
        logger.error(f"Error in crop_using_edge_detection: {str(e)}")
        # 최후의 수단으로 중앙 크롭
        h, w = frame.shape[:2]
        crop_w = int(w * 0.8)
        crop_h = int(h * 0.9)
        start_x = (w - crop_w) // 2
        start_y = (h - crop_h) // 2
        return frame[start_y:start_y+crop_h, start_x:start_x+crop_w]

def create_swing_sequence_local(video_path: str, key_frames: Dict[str, int], 
                               output_path: str = "swing_sequence.jpg", 
                               overlap_mode: str = "overlap") -> str:
    """로컬 스윙 시퀀스 생성 함수"""
    try:
        cap = cv2.VideoCapture(video_path)
        
        # 키 프레임 순서 정의
        if overlap_mode == "continuous":
            # 연속 겹침용 - 더 많은 프레임 사용
            frame_keys = ['address', 'takeaway', 'backswing_start', 'backswing_mid', 'top', 
                         'transition', 'downswing_start', 'downswing_mid', 'impact', 
                         'follow_start', 'follow_mid', 'finish']
        else:
            # 기본 5단계
            frame_keys = ['address', 'backswing', 'top', 'impact', 'follow_through']
        
        frames = []
        
        for phase in frame_keys:
            frame_idx = key_frames.get(phase)
            if frame_idx is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if ret:
                    # 프레임 크기 조정
                    height, width = frame.shape[:2]
                    if width > 600:
                        scale = 600 / width
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        frame = cv2.resize(frame, (new_width, new_height))
                    
                    frames.append((phase, frame))
        
        cap.release()
        
        if not frames:
            return None
        
        if overlap_mode == "continuous":
            result_img = create_continuous_overlap_sequence(frames)
        else:
            result_img = create_overlapped_sequence(frames)
        
        if result_img is not None:
            cv2.imwrite(output_path, result_img)
            return output_path
        
        return None
        
    except Exception as e:
        logger.error(f"Error creating swing sequence: {e}")
        return None

def create_detailed_phase_analysis_local(video_path: str, key_frames: Dict[str, int], 
                                       output_path: str = "detailed_swing_phases.jpg") -> str:
    """로컬 세분화 포즈 분석 생성 함수"""
    try:
        cap = cv2.VideoCapture(video_path)
        
        # 모든 세분화된 단계 정의
        phases = [
            ('address', '어드레스', (0, 255, 0)),
            ('takeaway', '테이크어웨이', (255, 255, 0)),
            ('backswing_start', '백스윙 시작', (255, 200, 0)),
            ('backswing_mid', '백스윙 중간', (255, 150, 0)),
            ('top', '탑', (255, 0, 0)),
            ('transition', '트랜지션', (255, 0, 100)),
            ('downswing_start', '다운스윙 시작', (255, 0, 200)),
            ('downswing_mid', '다운스윙 중간', (200, 0, 255)),
            ('impact', '임팩트', (100, 0, 255)),
            ('follow_start', '팔로우 시작', (0, 100, 255)),
            ('follow_mid', '팔로우 중간', (0, 200, 255)),
            ('finish', '피니시', (0, 255, 255))
        ]
        
        frames = []
        
        for phase_key, phase_name, color in phases:
            frame_idx = key_frames.get(phase_key)
            if frame_idx is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if ret:
                    # 프레임 크기 표준화
                    target_height = 300
                    aspect_ratio = frame.shape[1] / frame.shape[0]
                    target_width = int(target_height * aspect_ratio)
                    frame = cv2.resize(frame, (target_width, target_height))
                    
                    frames.append((phase_name, frame))
        
        cap.release()
        
        if not frames:
            return None
        
        # 그리드 레이아웃으로 배치 (4x3)
        rows = 3
        cols = 4
        
        # 프레임 크기 통일
        if frames:
            max_height = max(frame.shape[0] for _, frame in frames)
            max_width = max(frame.shape[1] for _, frame in frames)
            
            normalized_frames = []
            for phase_name, frame in frames:
                # 패딩 추가하여 크기 통일
                padded = np.zeros((max_height, max_width, 3), dtype=np.uint8)
                h, w = frame.shape[:2]
                y_offset = (max_height - h) // 2
                x_offset = (max_width - w) // 2
                padded[y_offset:y_offset+h, x_offset:x_offset+w] = frame
                
                # 단계명 추가
                cv2.putText(padded, phase_name, (10, 30), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                
                normalized_frames.append(padded)
            
            # 빈 프레임으로 패딩
            while len(normalized_frames) < rows * cols:
                empty_frame = np.zeros((max_height, max_width, 3), dtype=np.uint8)
                normalized_frames.append(empty_frame)
            
            # 그리드 생성
            grid_rows = []
            for i in range(rows):
                row_frames = normalized_frames[i*cols:(i+1)*cols]
                grid_row = np.hstack(row_frames)
                grid_rows.append(grid_row)
            
            final_grid = np.vstack(grid_rows)
            
            # 제목 추가
            title_height = 60
            title_img = np.zeros((title_height, final_grid.shape[1], 3), dtype=np.uint8)
            cv2.putText(title_img, "Detailed Swing Phase Analysis", 
                       (final_grid.shape[1]//2 - 250, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
            
            final_result = np.vstack([title_img, final_grid])
            
            # 이미지 저장
            cv2.imwrite(output_path, final_result)
            return output_path
        
        return None
        
    except Exception as e:
        logger.error(f"Error creating detailed phase analysis: {e}")
        return None

if __name__ == "__main__":
    main() 