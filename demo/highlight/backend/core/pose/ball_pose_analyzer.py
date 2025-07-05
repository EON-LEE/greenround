import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging
from .base_pose_analyzer import BasePoseAnalyzer

logger = logging.getLogger(__name__)

class BallPoseAnalyzer(BasePoseAnalyzer):
    """
    볼 트래킹에 특화된 포즈 분석기.
    임팩트 지점 감지와 어드레스 자세 분석에 최적화되어 있습니다.
    """
    
    def __init__(self):
        super().__init__()
        # 볼 트래킹 특화 설정
        self.impact_detection_window = 30  # 임팩트 감지를 위한 윈도우 크기
        self.address_search_window = 60    # 어드레스 감지를 위한 윈도우 크기
    
    def analyze_for_ball_tracking(self, video_path: Path) -> Dict:
        """
        볼 트래킹을 위한 포즈 분석을 수행합니다.
        임팩트 지점과 어드레스 자세에 집중하여 분석합니다.
        
        Returns:
            Dict: {
                'frames_data': List[Dict],  # 모든 프레임의 포즈 데이터
                'impact_frame': int,        # 임팩트 프레임 인덱스
                'address_frame': int,       # 어드레스 프레임 인덱스
                'swing_range': Tuple[int, int]  # 스윙 시작-끝 범위
            }
        """
        logger.info(f"볼 트래킹용 포즈 분석 시작: {video_path}")
        
        # 1. 프레임 추출 및 기본 포즈 분석
        frames, fps, width, height, _ = self._extract_frames_and_audio(video_path)
        frames_data = self._analyze_all_frames(frames, fps)
        
        # 2. 스윙 구간 탐지 (움직임 기반)
        swing_range = self._detect_swing_range(frames_data)
        
        # 3. 임팩트 지점 정밀 탐지
        impact_frame = self._detect_impact_frame(frames_data, swing_range)
        
        # 4. 어드레스 자세 탐지 (임팩트 이전)
        address_frame = self._detect_address_frame(frames_data, impact_frame)
        
        logger.info(f"볼 트래킹 분석 완료 - 어드레스: {address_frame}, 임팩트: {impact_frame}, 스윙범위: {swing_range}")
        
        return {
            'frames_data': frames_data,
            'impact_frame': impact_frame,
            'address_frame': address_frame,
            'swing_range': swing_range,
            'video_info': {
                'fps': fps,
                'width': width,
                'height': height,
                'total_frames': len(frames)
            }
        }
    
    def _analyze_all_frames(self, frames: List[np.ndarray], fps: float) -> List[Dict]:
        """모든 프레임에 대해 포즈 분석을 수행합니다."""
        frames_data = []
        prev_landmarks = None
        time_delta = 1.0 / fps
        
        logger.info(f"총 {len(frames)}개 프레임 분석 시작")
        
        for i, frame in enumerate(frames):
            # MediaPipe 포즈 추정
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_frame)
            
            # 랜드마크 추출
            landmarks = self._extract_landmarks(results)
            
            # 포즈 품질 계산
            pose_quality = self._calculate_pose_quality(landmarks)
            
            # 관절 속도 계산
            joint_speeds = self._calculate_joint_speeds(prev_landmarks, landmarks, time_delta)
            
            # 프레임 데이터 구성
            frame_data = {
                'frame_idx': i,
                'frame': frame,
                'landmarks': landmarks,
                'pose_quality': pose_quality,
                'timestamp': i / fps,
                **joint_speeds  # 관절 속도들 추가
            }
            
            frames_data.append(frame_data)
            prev_landmarks = landmarks
            
            if i % 30 == 0:  # 30프레임마다 로그
                logger.info(f"프레임 분석 진행: {i+1}/{len(frames)} ({(i+1)/len(frames)*100:.1f}%)")
        
        # 전체 움직임 데이터 계산
        self._calculate_motion_metrics(frames_data)
        
        return frames_data
    
    def _calculate_motion_metrics(self, frames_data: List[Dict]):
        """전체 프레임에 대한 움직임 메트릭을 계산하고 추가합니다."""
        # 손목 움직임 계산
        wrist_motion = self._calculate_wrist_motion(frames_data)
        
        # 전신 움직임 계산
        total_motion = self._calculate_total_body_motion(frames_data)
        
        # 부드럽게 처리
        wrist_motion = self._smooth_motion_data(wrist_motion)
        total_motion = self._smooth_motion_data(total_motion)
        
        # 각 프레임에 움직임 데이터 추가
        for i, frame_data in enumerate(frames_data):
            frame_data['wrist_motion'] = wrist_motion[i]
            frame_data['total_motion'] = total_motion[i]
            
            # 손목 속도 개별 계산 (좌우 구분)
            if i > 0:
                prev_lm = frames_data[i-1]['landmarks']
                curr_lm = frame_data['landmarks']
                
                if 'left_wrist' in prev_lm and 'left_wrist' in curr_lm:
                    left_dist = np.linalg.norm(
                        np.array(curr_lm['left_wrist']['point'][:2]) - 
                        np.array(prev_lm['left_wrist']['point'][:2])
                    )
                    frame_data['left_wrist_speed'] = left_dist
                
                if 'right_wrist' in prev_lm and 'right_wrist' in curr_lm:
                    right_dist = np.linalg.norm(
                        np.array(curr_lm['right_wrist']['point'][:2]) - 
                        np.array(prev_lm['right_wrist']['point'][:2])
                    )
                    frame_data['right_wrist_speed'] = right_dist
    
    def _detect_swing_range(self, frames_data: List[Dict]) -> Tuple[int, int]:
        """전체 영상에서 주요 스윙 구간을 탐지합니다."""
        if len(frames_data) < 60:  # 2초 미만이면 전체 구간
            return (0, len(frames_data) - 1)
        
        # 전체 움직임 데이터 추출
        motion_values = [frame.get('total_motion', 0) for frame in frames_data]
        
        # 움직임 임계값 설정 (평균의 20%)
        motion_threshold = np.mean(motion_values) * 0.2
        
        # 연속된 움직임 구간 찾기
        active_frames = [i for i, motion in enumerate(motion_values) if motion > motion_threshold]
        
        if not active_frames:
            return (0, len(frames_data) - 1)
        
        # 스윙 시작과 끝 결정 (여유분 추가)
        start_frame = max(0, active_frames[0] - 30)  # 1초 여유
        end_frame = min(len(frames_data) - 1, active_frames[-1] + 60)  # 2초 여유
        
        logger.info(f"스윙 구간 탐지: {start_frame} ~ {end_frame} (총 {end_frame - start_frame + 1}프레임)")
        
        return (start_frame, end_frame)
    
    def _detect_impact_frame(self, frames_data: List[Dict], swing_range: Tuple[int, int]) -> int:
        """임팩트 지점을 정밀하게 탐지합니다."""
        start_frame, end_frame = swing_range
        swing_frames = frames_data[start_frame:end_frame + 1]
        
        if not swing_frames:
            return len(frames_data) // 2
        
        # 손목 속도의 최대값을 임팩트로 간주
        max_speed = 0
        impact_idx = 0
        
        for i, frame in enumerate(swing_frames):
            left_speed = frame.get('left_wrist_speed', 0)
            right_speed = frame.get('right_wrist_speed', 0)
            combined_speed = left_speed + right_speed
            
            if combined_speed > max_speed:
                max_speed = combined_speed
                impact_idx = i
        
        impact_frame = start_frame + impact_idx
        logger.info(f"임팩트 프레임 탐지: {impact_frame} (속도: {max_speed:.4f})")
        
        return impact_frame
    
    def _detect_address_frame(self, frames_data: List[Dict], impact_frame: int) -> int:
        """어드레스 자세를 탐지합니다 (임팩트 이전의 정적인 구간)."""
        # 임팩트 이전 60프레임(2초) 내에서 검색
        search_start = max(0, impact_frame - self.address_search_window)
        search_end = impact_frame
        
        if search_start >= search_end:
            return max(0, impact_frame - 30)  # 기본값: 임팩트 1초 전
        
        # 가장 움직임이 적은 구간 찾기
        min_motion = float('inf')
        address_idx = search_start
        
        for i in range(search_start, search_end):
            if i < len(frames_data):
                total_motion = frames_data[i].get('total_motion', 0)
                if total_motion < min_motion:
                    min_motion = total_motion
                    address_idx = i
        
        logger.info(f"어드레스 프레임 탐지: {address_idx} (움직임: {min_motion:.4f})")
        
        return address_idx 