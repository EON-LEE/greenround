import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
import cv2
from pose_estimation import PoseEstimator
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class SwingAnalyzer:
    """골프 스윙을 분석하는 클래스"""

    def __init__(self):
        self.pose_estimator = PoseEstimator()

    def analyze_video(self, video_path: str) -> Dict:
        """비디오를 분석하고 결과를 반환합니다."""
        logger.info("Starting video analysis")
        
        # 비디오 캡처 초기화
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("비디오를 열 수 없습니다.")
        
        try:
            # 프레임 데이터 수집
            frames_data = self._collect_frames(cap)
            if not frames_data:
                raise ValueError("유효한 프레임을 찾을 수 없습니다.")
            
            # 키 프레임 감지
            key_frames = self._detect_key_frames(frames_data)
            logger.debug(f"Detected key frames: {key_frames}")
            
            # 스윙 분석 수행
            analysis_result = self._analyze_swing(frames_data, key_frames)
            logger.debug(f"Analysis result: {analysis_result}")
            
            # 스윙 시퀀스 이미지 생성
            try:
                # 오버랩 방식 시퀀스 생성
                overlap_sequence_path = self.create_swing_sequence(
                    video_path, key_frames, 
                    output_path="swing_sequence_overlap.jpg", 
                    overlap_mode=True
                )
                
                # 나란히 배치 방식 시퀀스 생성
                side_by_side_sequence_path = self.create_swing_sequence(
                    video_path, key_frames, 
                    output_path="swing_sequence_side_by_side.jpg", 
                    overlap_mode=False
                )
                
                analysis_result['sequence_images'] = {
                    'overlap': overlap_sequence_path,
                    'side_by_side': side_by_side_sequence_path
                }
                logger.info("Swing sequence images generated successfully")
                
            except Exception as e:
                logger.warning(f"Failed to generate swing sequence images: {str(e)}")
                analysis_result['sequence_images'] = None
            
            return analysis_result
            
        finally:
            cap.release()

    def _collect_frames(self, cap) -> List[Dict]:
        """비디오에서 프레임 데이터를 수집합니다."""
        frames_data = []
        frame_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # 프레임 처리
            processed_frame, landmarks = self.pose_estimator.process_frame(frame)
            if landmarks:
                # 각도 계산
                angles = self.pose_estimator.calculate_angles(landmarks)
                
                # 프레임 데이터 저장
                frame_data = {
                    'frame_number': frame_count,
                    'angles': angles,
                    'landmarks': self._landmarks_to_dict(landmarks)
                }
                frames_data.append(frame_data)
            
            frame_count += 1
            
        logger.info(f"Collected {len(frames_data)} valid frames")
        return frames_data

    def _detect_address_frame(self, frames_data: List[Dict]) -> Optional[int]:
        """어드레스 프레임을 감지합니다 (마지막 어드레스 반환)."""
        STABLE_FRAMES_REQUIRED = 5  # 안정된 자세로 판단하기 위한 연속 프레임 수
        ANGLE_THRESHOLD = 5  # 각도 변화 허용 범위 (도)
        POSITION_THRESHOLD = 0.05  # 위치 변화 허용 범위
        
        address_candidates = []  # 모든 address 후보를 저장
        stable_frame_count = 0
        last_angles = None
        last_positions = None
        
        for i, frame in enumerate(frames_data):
            current_angles = frame['angles']
            current_positions = {
                'right_shoulder': np.array(frame['landmarks']['right_shoulder']),
                'left_shoulder': np.array(frame['landmarks']['left_shoulder']),
                'right_hip': np.array(frame['landmarks']['right_hip']),
                'left_hip': np.array(frame['landmarks']['left_hip'])
            }
            
            # 첫 프레임이면 기준값으로 설정
            if last_angles is None:
                last_angles = current_angles
                last_positions = current_positions
                continue
            
            # 자세 안정성 체크
            is_stable = True
            
            # 각도 안정성 체크
            for angle_key in ['right_arm', 'left_arm', 'spine_angle']:
                if abs(current_angles.get(angle_key, 0) - last_angles.get(angle_key, 0)) > ANGLE_THRESHOLD:
                    is_stable = False
                    break
            
            # 위치 안정성 체크
            if is_stable:
                for pos_key in current_positions:
                    if np.linalg.norm(current_positions[pos_key] - last_positions[pos_key]) > POSITION_THRESHOLD:
                        is_stable = False
                        break
            
            # 어드레스 조건 체크
            if is_stable:
                right_arm_angle = current_angles.get('right_arm', 0)
                spine_angle = current_angles.get('spine_angle', 0)
                
                # 어드레스 자세 조건
                if (160 <= right_arm_angle <= 180 and  # 팔이 거의 펴진 상태
                    20 <= spine_angle <= 45):          # 적절한 척추 각도
                    stable_frame_count += 1
                else:
                    stable_frame_count = 0
            else:
                stable_frame_count = 0
            
            # 충분한 시간 동안 안정된 자세가 유지되면 어드레스 후보로 추가
            if stable_frame_count >= STABLE_FRAMES_REQUIRED:
                address_frame = i - STABLE_FRAMES_REQUIRED + 1
                # 중복 방지: 이전 address와 너무 가까우면 무시
                if not address_candidates or address_frame - address_candidates[-1] > 30:
                    address_candidates.append(address_frame)
                stable_frame_count = 0  # 리셋해서 다음 address 찾기
            
            last_angles = current_angles
            last_positions = current_positions
        
        logger.info(f"Found {len(address_candidates)} address candidates: {address_candidates}")
        
        # 마지막 address 반환 (가장 최근의 본스윙)
        return address_candidates[-1] if address_candidates else None

    def _detect_key_frames(self, frames_data: List[Dict]) -> Dict[str, int]:
        """주요 스윙 단계의 프레임을 감지합니다 (세분화된 단계 분석)."""
        if not frames_data:
            return {}
            
        # 세분화된 키 프레임 정의
        key_frames = {
            'address': None,
            'takeaway': None,           # 테이크어웨이
            'backswing_start': None,    # 백스윙 시작
            'backswing_mid': None,      # 백스윙 중간
            'top': None,                # 탑
            'transition': None,         # 트랜지션
            'downswing_start': None,    # 다운스윙 시작
            'downswing_mid': None,      # 다운스윙 중간
            'impact': None,             # 임팩트
            'follow_start': None,       # 팔로우 스루 시작
            'follow_mid': None,         # 팔로우 스루 중간
            'finish': None              # 피니시
        }
        
        # 마지막 address 프레임 감지
        address_frame = self._detect_address_frame(frames_data)
        key_frames['address'] = address_frame if address_frame is not None else 0
        
        logger.info(f"Starting detailed swing analysis from address frame: {key_frames['address']}")
        
        # 어드레스 이후 프레임들만 분석
        analysis_start = key_frames['address']
        analysis_frames = frames_data[analysis_start:]
        
        if len(analysis_frames) < 20:  # 분석하기에 충분하지 않은 프레임
            logger.warning(f"Not enough frames after address for detailed analysis: {len(analysis_frames)}")
            return self._fallback_to_basic_detection(frames_data, analysis_start)
        
        # 각도 및 위치 변화 분석
        angle_data = self._extract_angle_sequence(analysis_frames)
        motion_data = self._extract_motion_sequence(analysis_frames)
        
        # 세분화된 키 프레임 감지
        detailed_frames = self._detect_detailed_phases(analysis_frames, angle_data, motion_data, analysis_start)
        
        # 기본 키 프레임 업데이트
        key_frames.update(detailed_frames)
        
        logger.info(f"Detected detailed key frames: {key_frames}")
        return key_frames

    def _extract_angle_sequence(self, frames: List[Dict]) -> Dict[str, List[float]]:
        """프레임 시퀀스에서 각도 변화 데이터를 추출합니다."""
        sequences = {
            'shoulder_rotation': [],
            'right_arm_angle': [],
            'left_arm_angle': [],
            'spine_angle': [],
            'hip_rotation': [],
            'right_elbow_angle': [],
            'left_elbow_angle': [],
            'wrist_cock': []
        }
        
        for frame in frames:
            angles = frame['angles']
            sequences['shoulder_rotation'].append(angles.get('shoulder_angle', 0))
            sequences['right_arm_angle'].append(angles.get('right_arm', 0))
            sequences['left_arm_angle'].append(angles.get('left_arm', 0))
            sequences['spine_angle'].append(angles.get('spine_angle', 0))
            sequences['hip_rotation'].append(angles.get('hip_angle', 0))
            sequences['right_elbow_angle'].append(angles.get('right_elbow_angle', 0))
            sequences['left_elbow_angle'].append(angles.get('left_elbow_angle', 0))
            sequences['wrist_cock'].append(angles.get('wrist_cock_angle', 0))
        
        return sequences

    def _extract_motion_sequence(self, frames: List[Dict]) -> Dict[str, List[float]]:
        """프레임 시퀀스에서 모션 데이터를 추출합니다."""
        sequences = {
            'club_head_speed': [],
            'hand_speed': [],
            'shoulder_movement': [],
            'hip_movement': []
        }
        
        prev_frame = None
        for frame in frames:
            landmarks = frame['landmarks']
            
            if prev_frame:
                # 손목 속도 (클럽헤드 대신)
                prev_wrist = np.array(prev_frame['landmarks'].get('right_wrist', [0, 0, 0]))
                curr_wrist = np.array(landmarks.get('right_wrist', [0, 0, 0]))
                hand_speed = np.linalg.norm(curr_wrist - prev_wrist)
                sequences['hand_speed'].append(hand_speed)
                
                # 어깨 움직임
                prev_shoulder = np.array(prev_frame['landmarks'].get('right_shoulder', [0, 0, 0]))
                curr_shoulder = np.array(landmarks.get('right_shoulder', [0, 0, 0]))
                shoulder_movement = np.linalg.norm(curr_shoulder - prev_shoulder)
                sequences['shoulder_movement'].append(shoulder_movement)
                
                # 힙 움직임
                prev_hip = np.array(prev_frame['landmarks'].get('right_hip', [0, 0, 0]))
                curr_hip = np.array(landmarks.get('right_hip', [0, 0, 0]))
                hip_movement = np.linalg.norm(curr_hip - prev_hip)
                sequences['hip_movement'].append(hip_movement)
            else:
                sequences['hand_speed'].append(0)
                sequences['shoulder_movement'].append(0)
                sequences['hip_movement'].append(0)
            
            prev_frame = frame
        
        return sequences

    def _detect_detailed_phases(self, frames: List[Dict], angle_data: Dict, motion_data: Dict, start_idx: int) -> Dict[str, int]:
        """세분화된 스윙 단계를 감지합니다."""
        detailed_frames = {}
        frame_count = len(frames)
        
        # 1. 테이크어웨이 감지 (클럽이 움직이기 시작)
        takeaway_idx = self._detect_takeaway(angle_data, motion_data)
        if takeaway_idx is not None:
            detailed_frames['takeaway'] = start_idx + takeaway_idx
        
        # 2. 백스윙 시작 (어깨 회전 시작)
        backswing_start_idx = self._detect_backswing_start(angle_data)
        if backswing_start_idx is not None:
            detailed_frames['backswing_start'] = start_idx + backswing_start_idx
        
        # 3. 백스윙 중간 (어깨 회전 50%)
        backswing_mid_idx = self._detect_backswing_mid(angle_data)
        if backswing_mid_idx is not None:
            detailed_frames['backswing_mid'] = start_idx + backswing_mid_idx
        
        # 4. 탑 (최대 백스윙)
        top_idx = self._detect_top_position(angle_data, motion_data)
        if top_idx is not None:
            detailed_frames['top'] = start_idx + top_idx
        
        # 5. 트랜지션 (다운스윙 전환)
        if top_idx is not None:
            transition_idx = self._detect_transition(angle_data, motion_data, top_idx)
            if transition_idx is not None:
                detailed_frames['transition'] = start_idx + transition_idx
        
        # 6. 다운스윙 시작
        downswing_start_idx = self._detect_downswing_start(angle_data, motion_data)
        if downswing_start_idx is not None:
            detailed_frames['downswing_start'] = start_idx + downswing_start_idx
        
        # 7. 다운스윙 중간
        downswing_mid_idx = self._detect_downswing_mid(angle_data, motion_data)
        if downswing_mid_idx is not None:
            detailed_frames['downswing_mid'] = start_idx + downswing_mid_idx
        
        # 8. 임팩트 (최대 손 속도 지점)
        impact_idx = self._detect_impact_position(motion_data, angle_data)
        if impact_idx is not None:
            detailed_frames['impact'] = start_idx + impact_idx
        
        # 9. 팔로우 스루 시작
        if impact_idx is not None:
            follow_start_idx = self._detect_follow_start(angle_data, impact_idx)
            if follow_start_idx is not None:
                detailed_frames['follow_start'] = start_idx + follow_start_idx
        
        # 10. 팔로우 스루 중간
        follow_mid_idx = self._detect_follow_mid(angle_data)
        if follow_mid_idx is not None:
            detailed_frames['follow_mid'] = start_idx + follow_mid_idx
        
        # 11. 피니시
        detailed_frames['finish'] = start_idx + frame_count - 1
        
        # 기존 호환성을 위한 별칭 설정
        detailed_frames['backswing'] = detailed_frames.get('backswing_mid') or detailed_frames.get('backswing_start')
        detailed_frames['follow_through'] = detailed_frames.get('follow_start') or detailed_frames.get('follow_mid')
        
        return detailed_frames

    def _detect_takeaway(self, angle_data: Dict, motion_data: Dict) -> Optional[int]:
        """테이크어웨이 시점 감지 (클럽이 움직이기 시작)"""
        hand_speeds = motion_data['hand_speed']
        shoulder_rotations = angle_data['shoulder_rotation']
        
        # 손 움직임이 처음으로 임계값을 넘는 지점
        speed_threshold = np.mean(hand_speeds[:10]) + 2 * np.std(hand_speeds[:10]) if len(hand_speeds) > 10 else 0.01
        
        for i in range(min(len(hand_speeds), len(shoulder_rotations))):
            if hand_speeds[i] > speed_threshold and shoulder_rotations[i] > shoulder_rotations[0] + 5:
                return i
        
        return None

    def _detect_backswing_start(self, angle_data: Dict) -> Optional[int]:
        """백스윙 시작 감지 (어깨 회전 시작)"""
        shoulder_rotations = angle_data['shoulder_rotation']
        initial_shoulder = shoulder_rotations[0] if shoulder_rotations else 0
        
        for i, rotation in enumerate(shoulder_rotations):
            if rotation > initial_shoulder + 15:  # 15도 이상 회전
                return i
        
        return None

    def _detect_backswing_mid(self, angle_data: Dict) -> Optional[int]:
        """백스윙 중간 감지 (최대 회전의 50% 지점)"""
        shoulder_rotations = angle_data['shoulder_rotation']
        if not shoulder_rotations:
            return None
        
        max_rotation = max(shoulder_rotations)
        initial_rotation = shoulder_rotations[0]
        target_rotation = initial_rotation + (max_rotation - initial_rotation) * 0.5
        
        for i, rotation in enumerate(shoulder_rotations):
            if rotation >= target_rotation:
                return i
        
        return None

    def _detect_top_position(self, angle_data: Dict, motion_data: Dict) -> Optional[int]:
        """탑 포지션 감지 (최대 백스윙)"""
        shoulder_rotations = angle_data['shoulder_rotation']
        hand_speeds = motion_data['hand_speed']
        
        if not shoulder_rotations or not hand_speeds:
            return None
        
        # 어깨 회전이 최대이면서 손 속도가 최소인 지점
        max_rotation_idx = np.argmax(shoulder_rotations)
        
        # 최대 회전 근처에서 속도가 가장 낮은 지점 찾기
        search_range = range(max(0, max_rotation_idx - 5), min(len(hand_speeds), max_rotation_idx + 6))
        if search_range:
            local_speeds = [hand_speeds[i] for i in search_range]
            min_speed_local_idx = np.argmin(local_speeds)
            return max_rotation_idx - 5 + min_speed_local_idx
        
        return max_rotation_idx

    def _detect_transition(self, angle_data: Dict, motion_data: Dict, top_idx: int) -> Optional[int]:
        """트랜지션 감지 (다운스윙 전환점)"""
        hand_speeds = motion_data['hand_speed']
        
        # 탑 이후 손 속도가 증가하기 시작하는 지점
        for i in range(top_idx + 1, min(len(hand_speeds), top_idx + 10)):
            if hand_speeds[i] > hand_speeds[top_idx] * 1.5:
                return i
        
        return top_idx + 2 if top_idx + 2 < len(hand_speeds) else None

    def _detect_downswing_start(self, angle_data: Dict, motion_data: Dict) -> Optional[int]:
        """다운스윙 시작 감지"""
        shoulder_rotations = angle_data['shoulder_rotation']
        hand_speeds = motion_data['hand_speed']
        
        # 어깨 회전이 감소하기 시작하면서 손 속도가 증가하는 지점
        max_rotation = max(shoulder_rotations) if shoulder_rotations else 0
        max_rotation_idx = shoulder_rotations.index(max_rotation) if shoulder_rotations else 0
        
        for i in range(max_rotation_idx, len(shoulder_rotations) - 1):
            if (shoulder_rotations[i] < max_rotation * 0.9 and 
                i < len(hand_speeds) and hand_speeds[i] > np.mean(hand_speeds[:10])):
                return i
        
        return None

    def _detect_downswing_mid(self, angle_data: Dict, motion_data: Dict) -> Optional[int]:
        """다운스윙 중간 감지"""
        hand_speeds = motion_data['hand_speed']
        
        if not hand_speeds:
            return None
        
        # 손 속도가 최대의 70% 정도인 지점
        max_speed = max(hand_speeds)
        target_speed = max_speed * 0.7
        
        for i, speed in enumerate(hand_speeds):
            if speed >= target_speed:
                return i
        
        return None

    def _detect_impact_position(self, motion_data: Dict, angle_data: Dict) -> Optional[int]:
        """임팩트 감지 (최대 손 속도)"""
        hand_speeds = motion_data['hand_speed']
        
        if not hand_speeds:
            return None
        
        # 최대 손 속도 지점
        max_speed_idx = np.argmax(hand_speeds)
        
        # 임팩트 근처에서 팔이 가장 펴진 지점도 고려
        right_arm_angles = angle_data['right_arm_angle']
        if right_arm_angles and max_speed_idx < len(right_arm_angles):
            search_range = range(max(0, max_speed_idx - 3), min(len(right_arm_angles), max_speed_idx + 4))
            if search_range:
                local_arm_angles = [right_arm_angles[i] for i in search_range]
                max_arm_extension_local_idx = np.argmax(local_arm_angles)
                return max_speed_idx - 3 + max_arm_extension_local_idx
        
        return max_speed_idx

    def _detect_follow_start(self, angle_data: Dict, impact_idx: int) -> Optional[int]:
        """팔로우 스루 시작 감지"""
        right_arm_angles = angle_data['right_arm_angle']
        
        # 임팩트 이후 팔 각도가 감소하기 시작하는 지점
        if impact_idx < len(right_arm_angles) - 5:
            impact_arm_angle = right_arm_angles[impact_idx]
            
            for i in range(impact_idx + 1, min(len(right_arm_angles), impact_idx + 10)):
                if right_arm_angles[i] < impact_arm_angle * 0.9:
                    return i
        
        return impact_idx + 3 if impact_idx + 3 < len(right_arm_angles) else None

    def _detect_follow_mid(self, angle_data: Dict) -> Optional[int]:
        """팔로우 스루 중간 감지"""
        right_arm_angles = angle_data['right_arm_angle']
        
        if not right_arm_angles:
            return None
        
        # 팔 각도가 120도 이하인 지점들 중 중간
        follow_points = [i for i, angle in enumerate(right_arm_angles) if angle <= 120]
        
        if follow_points:
            return follow_points[len(follow_points) // 2]
        
        return None

    def _fallback_to_basic_detection(self, frames_data: List[Dict], analysis_start: int) -> Dict[str, int]:
        """기본 키 프레임 감지로 폴백"""
        logger.warning("Falling back to basic key frame detection")
        
        total_valid_frames = len(frames_data)
        return {
            'address': analysis_start,
            'takeaway': min(int(analysis_start + total_valid_frames * 0.1), total_valid_frames - 1),
            'backswing_start': min(int(analysis_start + total_valid_frames * 0.2), total_valid_frames - 1),
            'backswing_mid': min(int(analysis_start + total_valid_frames * 0.35), total_valid_frames - 1),
            'top': min(int(analysis_start + total_valid_frames * 0.5), total_valid_frames - 1),
            'transition': min(int(analysis_start + total_valid_frames * 0.55), total_valid_frames - 1),
            'downswing_start': min(int(analysis_start + total_valid_frames * 0.6), total_valid_frames - 1),
            'downswing_mid': min(int(analysis_start + total_valid_frames * 0.7), total_valid_frames - 1),
            'impact': min(int(analysis_start + total_valid_frames * 0.75), total_valid_frames - 1),
            'follow_start': min(int(analysis_start + total_valid_frames * 0.8), total_valid_frames - 1),
            'follow_mid': min(int(analysis_start + total_valid_frames * 0.9), total_valid_frames - 1),
            'finish': total_valid_frames - 1
        }

    def _analyze_swing(self, frames_data: List[Dict], key_frames: Dict[str, int]) -> Dict:
        """스윙을 분석하고 메트릭스와 평가를 생성합니다."""
        # 메트릭스 계산
        metrics = self._calculate_metrics(frames_data, key_frames)
        
        # 평가 생성
        evaluations = self._evaluate_swing(frames_data, key_frames, metrics)
        
        return {
            'frames': frames_data,
            'key_frames': key_frames,
            'metrics': metrics,
            'evaluations': evaluations
        }

    def _calculate_metrics(self, frames_data: List[Dict], key_frames: Dict[str, int]) -> Dict[str, float]:
        """스윙 메트릭스를 계산합니다."""
        logger.debug("Starting metrics calculation...")
        
        # 기본 메트릭스 초기화
        metrics = {
            'shoulder_rotation': 0.0,
            'hip_rotation': 0.0,
            'head_movement': 0.0,
            'backswing_angle': 0.0,
            'impact_angle': 0.0,
            'follow_through_angle': 0.0
        }
        
        if not frames_data:
            logger.warning("No frames data available for metrics calculation")
            return metrics
            
        logger.debug(f"Processing {len(frames_data)} frames for metrics")
        
        # 최대 회전 각도 계산
        for frame in frames_data:
            angles = frame['angles']
            metrics['shoulder_rotation'] = max(metrics['shoulder_rotation'], angles.get('shoulder_angle', 0))
            metrics['hip_rotation'] = max(metrics['hip_rotation'], angles.get('hip_angle', 0))
        
        logger.debug(f"Rotation metrics: shoulder={metrics['shoulder_rotation']}, hip={metrics['hip_rotation']}")
        
        # 헤드 무브먼트 계산
        try:
            initial_frame = frames_data[0]
            if 'landmarks' in initial_frame and 'nose' in initial_frame['landmarks'] and initial_frame['landmarks']['nose'] is not None:
                initial_head_pos = np.array(initial_frame['landmarks']['nose'])
                max_movement = 0.0
                
                for frame in frames_data[1:]:
                    if 'landmarks' in frame and 'nose' in frame['landmarks'] and frame['landmarks']['nose'] is not None:
                        current_head_pos = np.array(frame['landmarks']['nose'])
                        movement = np.linalg.norm(current_head_pos - initial_head_pos)
                        max_movement = max(max_movement, movement)
                
                metrics['head_movement'] = float(max_movement)
                logger.debug(f"Calculated head movement: {metrics['head_movement']}")
            else:
                logger.warning("Initial frame missing nose landmark, setting head_movement to 0.0")
        except Exception as e:
            logger.error(f"Error calculating head movement: {str(e)}")
            metrics['head_movement'] = 0.0
        
        # 주요 각도 계산 - None 값 처리 추가
        try:
            if key_frames.get('top') is not None and 0 <= key_frames['top'] < len(frames_data):
                metrics['backswing_angle'] = frames_data[key_frames['top']]['angles'].get('right_arm', 0)
            if key_frames.get('impact') is not None and 0 <= key_frames['impact'] < len(frames_data):
                metrics['impact_angle'] = frames_data[key_frames['impact']]['angles'].get('right_arm', 0)
            if key_frames.get('finish') is not None and 0 <= key_frames['finish'] < len(frames_data):
                metrics['follow_through_angle'] = frames_data[key_frames['finish']]['angles'].get('right_arm', 0)
        except Exception as e:
            logger.error(f"Error calculating swing angles: {str(e)}")
        
        logger.debug(f"Final calculated metrics: {metrics}")
        return metrics

    def _evaluate_swing(self, frames_data: List[Dict], key_frames: Dict[str, int], metrics: Dict[str, float]) -> Dict[str, Dict[str, bool]]:
        """스윙을 평가합니다."""
        logger.debug("Starting swing evaluation...")
        logger.debug(f"Input metrics: {metrics}")
        
        evaluations = {}
        
        # 어드레스 평가
        address_idx = key_frames.get('address')
        if address_idx is not None and 0 <= address_idx < len(frames_data):
            address_frame = frames_data[address_idx]
            evaluations['address'] = {
                'Arm Angle Straight': 165 <= address_frame['angles'].get('right_arm', 0) <= 180,
                'Posture Stable': address_frame['angles'].get('spine_angle', 0) >= 30
            }
        
        # 탑 평가
        top_idx = key_frames.get('top')
        if top_idx is not None and 0 <= top_idx < len(frames_data):
            evaluations['top'] = {
                'Shoulder Rotation Good': metrics.get('shoulder_rotation', 0) >= 80,
                'Head Stable': metrics.get('head_movement', 0) <= 0.1
            }
        
        # 임팩트 평가
        impact_idx = key_frames.get('impact')
        if impact_idx is not None and 0 <= impact_idx < len(frames_data):
            impact_frame = frames_data[impact_idx]
            evaluations['impact'] = {
                'Arm Straight': 165 <= impact_frame['angles'].get('right_arm', 0) <= 180,
                'Hip Rotation Good': metrics.get('hip_rotation', 0) >= 45
            }
        
        # 팔로우 스루 평가
        follow_through_idx = key_frames.get('follow_through')
        if follow_through_idx is not None and 0 <= follow_through_idx < len(frames_data):
            follow_frame = frames_data[follow_through_idx]
            evaluations['follow_through'] = {
                'Follow Through Complete': follow_frame['angles'].get('right_arm', 0) <= 120,
                'Balance Maintained': follow_frame['angles'].get('right_leg', 0) <= 160
            }
        
        # 피니시 평가
        finish_idx = key_frames.get('finish')
        if finish_idx is not None and 0 <= finish_idx < len(frames_data):
            finish_frame = frames_data[finish_idx]
            evaluations['finish'] = {
                'Follow Through Complete': finish_frame['angles'].get('right_arm', 0) <= 120,
                'Balance Maintained': finish_frame['angles'].get('right_leg', 0) <= 160
            }
        
        logger.debug(f"Final evaluations: {evaluations}")
        return evaluations

    def _landmarks_to_dict(self, landmarks) -> Dict[str, List[float]]:
        """랜드마크를 딕셔너리로 변환합니다."""
        return {
            'nose': landmarks.nose.tolist() if hasattr(landmarks, 'nose') else None,
            'left_shoulder': landmarks.left_shoulder.tolist(),
            'right_shoulder': landmarks.right_shoulder.tolist(),
            'left_elbow': landmarks.left_elbow.tolist(),
            'right_elbow': landmarks.right_elbow.tolist(),
            'left_wrist': landmarks.left_wrist.tolist(),
            'right_wrist': landmarks.right_wrist.tolist(),
            'left_hip': landmarks.left_hip.tolist(),
            'right_hip': landmarks.right_hip.tolist(),
            'left_knee': landmarks.left_knee.tolist(),
            'right_knee': landmarks.right_knee.tolist(),
            'left_ankle': landmarks.left_ankle.tolist(),
            'right_ankle': landmarks.right_ankle.tolist()
        }

    def create_swing_sequence(self, video_path: str, key_frames: Dict[str, int], 
                            output_path: str = "swing_sequence.jpg", 
                            overlap_mode: bool = True) -> str:
        """스윙 시퀀스 이미지를 생성합니다.
        
        Args:
            video_path: 원본 비디오 경로
            key_frames: 키 프레임 딕셔너리
            output_path: 출력 이미지 경로
            overlap_mode: True면 오버랩, False면 나란히 배치
            
        Returns:
            생성된 이미지 파일 경로
        """
        logger.info(f"Creating swing sequence image: {output_path}")
        
        # 비디오 캡처 초기화
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("비디오를 열 수 없습니다.")
        
        try:
            # 키 프레임 순서 정의
            frame_sequence = ['address', 'backswing', 'top', 'impact', 'follow_through']
            extracted_frames = []
            
            # 각 키 프레임에서 이미지 추출
            for phase in frame_sequence:
                frame_num = key_frames.get(phase)
                if frame_num is not None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                    ret, frame = cap.read()
                    if ret:
                        # 프레임 크기 조정 (선택사항)
                        height, width = frame.shape[:2]
                        if width > 800:  # 너무 크면 리사이즈
                            scale = 800 / width
                            new_width = int(width * scale)
                            new_height = int(height * scale)
                            frame = cv2.resize(frame, (new_width, new_height))
                        
                        extracted_frames.append((phase, frame))
                        logger.debug(f"Extracted frame for {phase}: frame {frame_num}")
            
            if not extracted_frames:
                raise ValueError("키 프레임을 추출할 수 없습니다.")
            
            if overlap_mode:
                result_image = self._create_overlapped_sequence(extracted_frames)
            else:
                result_image = self._create_side_by_side_sequence(extracted_frames)
            
            # 이미지 저장
            cv2.imwrite(output_path, result_image)
            logger.info(f"Swing sequence saved: {output_path}")
            
            return output_path
            
        finally:
            cap.release()

    def _create_overlapped_sequence(self, frames: List[Tuple[str, np.ndarray]]) -> np.ndarray:
        """오버랩 방식으로 스윙 시퀀스 생성"""
        if not frames:
            raise ValueError("프레임이 없습니다.")
        
        # 기준 프레임 (첫 번째 프레임)
        base_frame = frames[0][1].copy()
        height, width = base_frame.shape[:2]
        
        # 결과 이미지 초기화 (알파 채널 포함)
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
            frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA).astype(np.float32)
            
            # 색상 틴트 적용 (선택사항)
            if i > 0:  # 첫 번째 프레임은 원본 색상 유지
                tint_color = colors[i] if i < len(colors) else colors[-1]
                frame_rgba[:, :, :3] = frame_rgba[:, :, :3] * 0.7 + np.array(tint_color) * 0.3
            
            # 알파 값 설정
            frame_rgba[:, :, 3] = alpha * 255
            
            # 블렌딩
            if i == 0:
                result = frame_rgba
            else:
                # 알파 블렌딩
                alpha_norm = frame_rgba[:, :, 3:4] / 255.0
                result[:, :, :3] = result[:, :, :3] * (1 - alpha_norm) + frame_rgba[:, :, :3] * alpha_norm
                result[:, :, 3:4] = np.maximum(result[:, :, 3:4], frame_rgba[:, :, 3:4])
        
        # BGR로 변환하여 반환
        result_bgr = cv2.cvtColor(result[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2BGR)
        
        # 단계 라벨 추가
        self._add_phase_labels(result_bgr, frames)
        
        return result_bgr

    def _create_side_by_side_sequence(self, frames: List[Tuple[str, np.ndarray]]) -> np.ndarray:
        """나란히 배치 방식으로 스윙 시퀀스 생성"""
        if not frames:
            raise ValueError("프레임이 없습니다.")
        
        # 모든 프레임을 같은 높이로 리사이즈
        target_height = 400
        resized_frames = []
        
        for phase, frame in frames:
            height, width = frame.shape[:2]
            scale = target_height / height
            new_width = int(width * scale)
            resized_frame = cv2.resize(frame, (new_width, target_height))
            resized_frames.append((phase, resized_frame))
        
        # 전체 너비 계산
        total_width = sum([frame.shape[1] for _, frame in resized_frames])
        
        # 결과 이미지 생성
        result = np.zeros((target_height, total_width, 3), dtype=np.uint8)
        
        # 프레임들을 나란히 배치
        x_offset = 0
        for phase, frame in resized_frames:
            width = frame.shape[1]
            result[:, x_offset:x_offset + width] = frame
            
            # 단계 라벨 추가
            cv2.putText(result, phase.upper(), 
                       (x_offset + 10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            x_offset += width
        
        return result

    def _add_phase_labels(self, image: np.ndarray, frames: List[Tuple[str, np.ndarray]]) -> None:
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

    def create_detailed_phase_analysis(self, video_path: str, output_path: str = "detailed_swing_phases.jpg") -> str:
        """세분화된 스윙 단계별 포즈 분석 이미지를 생성합니다."""
        try:
            # 비디오 분석
            result = self.analyze_video(video_path)
            key_frames = result.get('key_frames', {})
            
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
                        # 프레임 크롭 및 리사이즈
                        cropped_frame = self.auto_crop_person_area(frame, frame_idx, result.get('frames_data', []))
                        if cropped_frame is not None:
                            frame = cropped_frame
                        
                        # 프레임 크기 표준화
                        target_height = 300
                        aspect_ratio = frame.shape[1] / frame.shape[0]
                        target_width = int(target_height * aspect_ratio)
                        frame = cv2.resize(frame, (target_width, target_height))
                        
                        # 포즈 랜드마크 그리기
                        frame_data = result.get('frames_data', [])
                        if frame_idx < len(frame_data):
                            frame = self._draw_pose_landmarks(frame, frame_data[frame_idx], color)
                        
                        frames.append((phase_name, frame))
            
            cap.release()
            
            if not frames:
                logger.error("No frames extracted for phase analysis")
                return None
            
            # 그리드 레이아웃으로 배치 (4x3)
            rows = 3
            cols = 4
            
            # 프레임 크기 통일
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
            logger.info(f"Detailed phase analysis saved to: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating detailed phase analysis: {e}")
            return None

    def _draw_pose_landmarks(self, frame: np.ndarray, frame_data: Dict, color: tuple) -> np.ndarray:
        """프레임에 포즈 랜드마크를 그립니다."""
        landmarks = frame_data.get('landmarks', {})
        h, w = frame.shape[:2]
        
        # 주요 관절점들
        key_points = [
            'nose', 'left_shoulder', 'right_shoulder',
            'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
            'left_hip', 'right_hip', 'left_knee', 'right_knee',
            'left_ankle', 'right_ankle'
        ]
        
        # 관절점 그리기
        for point_name in key_points:
            if point_name in landmarks:
                point = landmarks[point_name]
                # 정규화된 좌표를 픽셀 좌표로 변환
                if point[0] <= 1.0 and point[1] <= 1.0:  # 정규화된 좌표
                    x, y = int(point[0] * w), int(point[1] * h)
                else:  # 이미 픽셀 좌표
                    x, y = int(point[0]), int(point[1])
                
                cv2.circle(frame, (x, y), 5, color, -1)
        
        # 연결선 그리기
        connections = [
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
        
        for start_point, end_point in connections:
            if start_point in landmarks and end_point in landmarks:
                start = landmarks[start_point]
                end = landmarks[end_point]
                
                # 정규화된 좌표를 픽셀 좌표로 변환
                if start[0] <= 1.0 and start[1] <= 1.0:
                    start_x, start_y = int(start[0] * w), int(start[1] * h)
                else:
                    start_x, start_y = int(start[0]), int(start[1])
                
                if end[0] <= 1.0 and end[1] <= 1.0:
                    end_x, end_y = int(end[0] * w), int(end[1] * h)
                else:
                    end_x, end_y = int(end[0]), int(end[1])
                
                cv2.line(frame, (start_x, start_y), (end_x, end_y), color, 2)
        
        return frame 