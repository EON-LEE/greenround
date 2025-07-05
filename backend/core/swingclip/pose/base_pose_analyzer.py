import mediapipe as mp
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
from scipy.signal import find_peaks
import logging
import time
import os

logger = logging.getLogger(__name__)



class BasePoseAnalyzer:
    """
    골프 스윙 포즈 분석의 기본 클래스.
    MediaPipe 초기화와 공통 유틸리티 메서드들을 제공합니다.
    """
    
    def __init__(self):
        """BasePoseAnalyzer 클래스의 생성자입니다."""
        start_time = time.time()
        
        self.mp_pose = mp.solutions.pose
        
        # OpenCV 멀티스레딩 최적화
        try:
            cpu_count = os.cpu_count() or 4
            cv2.setNumThreads(cpu_count)
            cv2.setUseOptimized(True)
        except Exception as e:
            logger.warning(f"OpenCV 최적화 설정 실패: {e}")
        
        # MediaPipe Pose 모델 초기화 - GPU 최적화 최고 정밀도 설정
        model_start = time.time()
        self.pose = self.mp_pose.Pose(
            static_image_mode=False, 
            model_complexity=1,  # GPU 환경에서 최고 정밀도 모델 사용 (0->2)
            min_detection_confidence=0.3,  # 높은 신뢰도 요구 (0.3->0.7)
            min_tracking_confidence=0.3,   # 안정적인 추적 (0.3->0.5)
            enable_segmentation=True)       # 세그멘테이션 활성화로 더 정확한 포즈 감지
        model_time = time.time() - model_start
        
        self.main_joints = [
            'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
            'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
            'left_knee', 'right_knee', 'left_ankle', 'right_ankle']
        

        
        init_time = time.time() - start_time
        logger.info(f"BasePoseAnalyzer 초기화 완료 - 총 시간: {init_time:.3f}s (모델 로드: {model_time:.3f}s)")
    
    def _extract_frames_and_audio(self, video_path: Path) -> Tuple[List[np.ndarray], float, int, int, None]:
        """비디오에서 프레임과 메타데이터를 추출합니다."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened(): 
            raise IOError(f"비디오 파일을 열 수 없습니다: {video_path}")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()
        
        return frames, fps, width, height, None

    def _extract_landmarks(self, results) -> Dict:
        """MediaPipe 결과에서 랜드마크를 추출합니다."""
        landmarks = {}
        if results.pose_landmarks:
            for i, landmark in enumerate(results.pose_landmarks.landmark):
                joint_name = self.mp_pose.PoseLandmark(i).name.lower()
                if joint_name in self.main_joints:
                    landmarks[joint_name] = {
                        'point': (landmark.x, landmark.y, landmark.z), 
                        'visibility': landmark.visibility
                    }
        return landmarks
    
    def _calculate_pose_quality(self, landmarks: Dict) -> float:
        """주요 관절의 평균 신뢰도(visibility)로 포즈 품질을 계산합니다."""
        if not landmarks:
            return 0.0
        
        visibilities = [
            landmarks[joint]['visibility'] for joint in self.main_joints 
            if joint in landmarks and 'visibility' in landmarks[joint]
        ]
        
        return np.mean(visibilities) if visibilities else 0.0
    
    def _calculate_joint_speeds(self, prev_pose, current_pose, time_delta) -> Dict:
        """두 프레임 간의 관절 속도를 계산합니다."""
        if not prev_pose or not current_pose or time_delta == 0: 
            return {}
        
        speeds = {}
        for joint, info in current_pose.items():
            if joint in prev_pose:
                dist = np.linalg.norm(
                    np.array(info['point']) - np.array(prev_pose[joint]['point'])
                )
                speeds[f"{joint}_speed"] = dist / time_delta
        return speeds

    def _calculate_wrist_motion(self, frames_data: List[Dict]) -> List[float]:
        """양쪽 손목의 평균 속도를 계산합니다."""
        motion_data = [0.0] * len(frames_data)
        for i in range(1, len(frames_data)):
            prev_lm = frames_data[i-1]['landmarks']
            curr_lm = frames_data[i]['landmarks']
            
            if ('left_wrist' in prev_lm and 'left_wrist' in curr_lm and 
                'right_wrist' in prev_lm and 'right_wrist' in curr_lm):
                
                dist_l = np.linalg.norm(
                    np.array(curr_lm['left_wrist']['point'][:2]) - 
                    np.array(prev_lm['left_wrist']['point'][:2])
                )
                dist_r = np.linalg.norm(
                    np.array(curr_lm['right_wrist']['point'][:2]) - 
                    np.array(prev_lm['right_wrist']['point'][:2])
                )
                motion_data[i] = (dist_l + dist_r) / 2
        return motion_data

    def _calculate_total_body_motion(self, frames_data: List[Dict]) -> List[float]:
        """모든 주요 관절의 평균 움직임을 계산합니다."""
        motion_data = [0.0] * len(frames_data)
        for i in range(1, len(frames_data)):
            prev_lm = frames_data[i-1]['landmarks']
            curr_lm = frames_data[i]['landmarks']
            
            total_dist = 0
            num_joints = 0
            for joint in self.main_joints:
                if joint in prev_lm and joint in curr_lm:
                    dist = np.linalg.norm(
                        np.array(curr_lm[joint]['point']) - 
                        np.array(prev_lm[joint]['point'])
                    )
                    total_dist += dist
                    num_joints += 1
            
            if num_joints > 0:
                motion_data[i] = total_dist / num_joints
        return motion_data
    
    def _smooth_motion_data(self, motion_data: List[float], window_size: int = 9) -> List[float]:
        """간단한 이동 평균으로 움직임 데이터를 부드럽게 만듭니다. GPU 환경에서 더 정밀한 스무딩."""
        if len(motion_data) < window_size:
            return motion_data
        
        # 가우시안 가중 스무딩으로 업그레이드 (더 정밀한 분석)
        sigma = window_size / 3.0
        x = np.arange(window_size) - window_size // 2
        weights = np.exp(-(x**2) / (2 * sigma**2))
        weights = weights / np.sum(weights)
        
        smoothed = np.convolve(motion_data, weights, mode='same')
        return smoothed.tolist()

    def _detect_key_events(self, frames_data: list, start_frame: int, end_frame: int) -> dict:
        """스윙 구간에서 키 이벤트를 감지합니다."""
        swing_frames = frames_data[start_frame:end_frame + 1]
        if not swing_frames: 
            return {}
        
        # 임팩트: 손목 속도가 가장 빠른 지점
        impact_idx = max(
            range(len(swing_frames)), 
            key=lambda i: swing_frames[i].get('left_wrist_speed', 0) + swing_frames[i].get('right_wrist_speed', 0), 
            default=-1
        )
        if impact_idx == -1: 
            impact_idx = len(swing_frames) // 2

        # 어드레스: 임팩트 이전 가장 정적인 지점
        address_idx = min(
            range(impact_idx), 
            key=lambda i: swing_frames[i].get('total_motion', float('inf')), 
            default=0
        )
        
        # 피니시: 임팩트 이후 가장 정적인 지점
        finish_search_start = min(impact_idx + int(0.1*len(swing_frames)), len(swing_frames)-1)
        finish_idx = min(
            range(finish_search_start, len(swing_frames)), 
            key=lambda i: swing_frames[i].get('total_motion', float('inf')), 
            default=len(swing_frames)-1
        )

        # 백스윙 탑: 어드레스와 임팩트 중간 지점
        backswing_top_idx = (address_idx + impact_idx) // 2
        
        return {
            "address": start_frame + address_idx,
            "backswing_top": start_frame + backswing_top_idx,
            "impact": start_frame + impact_idx,
            "finish": start_frame + finish_idx,
        } 