import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SwingAnalyzer3D:
    def __init__(self):
        """3D 스윙 분석을 위한 초기화"""
        self.key_frame_ratios = {
            'address': 0.0,
            'backswing': 0.3,
            'top': 0.5,
            'impact': 0.7,
            'follow_through': 0.85,
            'finish': 1.0
        }
        
    def analyze_swing(self, frames_data: List[Dict]) -> Dict:
        """전체 스윙 분석 수행"""
        try:
            # 키 프레임 인덱스 계산
            total_frames = len(frames_data)
            key_frames = {
                phase: min(int(ratio * total_frames), total_frames - 1)
                for phase, ratio in self.key_frame_ratios.items()
            }
            
            # 각 단계별 메트릭스 계산
            metrics = self._calculate_metrics(frames_data, key_frames)
            
            # 스윙 평가
            evaluations = self._evaluate_swing(frames_data, key_frames, metrics)
            
            return {
                'key_frames': key_frames,
                'metrics': metrics,
                'evaluations': evaluations
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_swing: {str(e)}")
            return {}
            
    def _calculate_metrics(self, frames_data: List[Dict], key_frames: Dict) -> Dict:
        """스윙 메트릭스 계산"""
        try:
            metrics = {}
            
            # 어드레스 자세 분석
            address_frame = frames_data[key_frames['address']]
            metrics['address_spine_angle'] = address_frame['angles']['spine_angle']
            metrics['address_knee_flex'] = address_frame['angles']['right_knee']
            
            # 백스윙 분석
            backswing_frame = frames_data[key_frames['backswing']]
            metrics['backswing_shoulder_turn'] = backswing_frame['angles']['shoulder_rotation']
            metrics['backswing_hip_turn'] = backswing_frame['angles']['hip_rotation']
            
            # 탑 자세 분석
            top_frame = frames_data[key_frames['top']]
            metrics['top_shoulder_turn'] = top_frame['angles']['shoulder_rotation']
            metrics['top_arm_angle'] = top_frame['angles']['right_arm']
            
            # 임팩트 자세 분석
            impact_frame = frames_data[key_frames['impact']]
            metrics['impact_spine_angle'] = impact_frame['angles']['spine_angle']
            metrics['impact_hip_rotation'] = impact_frame['angles']['hip_rotation']
            
            # 팔로우 스루 분석
            follow_frame = frames_data[key_frames['follow_through']]
            metrics['follow_shoulder_rotation'] = follow_frame['angles']['shoulder_rotation']
            metrics['follow_hip_rotation'] = follow_frame['angles']['hip_rotation']
            
            # 피니시 자세 분석
            finish_frame = frames_data[key_frames['finish']]
            metrics['finish_balance'] = finish_frame['angles']['right_knee']
            metrics['finish_rotation'] = finish_frame['angles']['shoulder_rotation']
            
            # 전체 스윙 분석
            metrics['swing_tempo'] = self._calculate_swing_tempo(frames_data, key_frames)
            metrics['swing_plane'] = self._calculate_swing_plane(frames_data, key_frames)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {str(e)}")
            return {}
            
    def _evaluate_swing(self, frames_data: List[Dict], key_frames: Dict, metrics: Dict) -> Dict:
        """스윙 평가 수행"""
        try:
            evaluations = {}
            
            # 어드레스 평가
            evaluations['address'] = {
                'Posture': metrics['address_spine_angle'] >= 30,
                'Knee Flex': 20 <= metrics['address_knee_flex'] <= 30,
                'Setup Balance': self._check_balance(frames_data[key_frames['address']])
            }
            
            # 백스윙 평가
            evaluations['backswing'] = {
                'Shoulder Turn': metrics['backswing_shoulder_turn'] >= 60,
                'Hip Resistance': metrics['backswing_hip_turn'] <= 45,
                'Spine Angle': self._check_spine_angle_maintenance(
                    frames_data[key_frames['address']],
                    frames_data[key_frames['backswing']]
                )
            }
            
            # 탑 자세 평가
            evaluations['top'] = {
                'Shoulder Turn': metrics['top_shoulder_turn'] >= 90,
                'Arm Position': 80 <= metrics['top_arm_angle'] <= 100,
                'Wrist Hinge': self._check_wrist_hinge(frames_data[key_frames['top']])
            }
            
            # 임팩트 평가
            evaluations['impact'] = {
                'Hip Rotation': metrics['impact_hip_rotation'] >= 45,
                'Spine Angle': metrics['impact_spine_angle'] >= 30,
                'Weight Transfer': self._check_weight_transfer(frames_data[key_frames['impact']])
            }
            
            # 팔로우 스루 평가
            evaluations['follow_through'] = {
                'Body Rotation': metrics['follow_shoulder_rotation'] >= 90,
                'Hip Clearance': metrics['follow_hip_rotation'] >= 90,
                'Extension': self._check_arm_extension(frames_data[key_frames['follow_through']])
            }
            
            # 피니시 평가
            evaluations['finish'] = {
                'Balance': metrics['finish_balance'] >= 160,
                'Full Rotation': metrics['finish_rotation'] >= 270,
                'Posture': self._check_finish_posture(frames_data[key_frames['finish']])
            }
            
            return evaluations
            
        except Exception as e:
            logger.error(f"Error evaluating swing: {str(e)}")
            return {}
            
    def _calculate_swing_tempo(self, frames_data: List[Dict], key_frames: Dict) -> float:
        """스윙 템포 계산 (백스윙:다운스윙 비율)"""
        try:
            backswing_frames = key_frames['top'] - key_frames['address']
            downswing_frames = key_frames['impact'] - key_frames['top']
            
            return backswing_frames / downswing_frames if downswing_frames > 0 else 0
            
        except Exception as e:
            logger.error(f"Error calculating swing tempo: {str(e)}")
            return 0
            
    def _calculate_swing_plane(self, frames_data: List[Dict], key_frames: Dict) -> float:
        """스윙 플레인 일관성 계산"""
        try:
            # 백스윙과 다운스윙의 플레인 각도 비교
            backswing_plane = self._get_swing_plane_angle(
                frames_data[key_frames['address']]['landmarks'],
                frames_data[key_frames['top']]['landmarks']
            )
            
            downswing_plane = self._get_swing_plane_angle(
                frames_data[key_frames['top']]['landmarks'],
                frames_data[key_frames['impact']]['landmarks']
            )
            
            # 두 플레인 각도의 차이 반환 (작을수록 일관성 높음)
            return abs(backswing_plane - downswing_plane)
            
        except Exception as e:
            logger.error(f"Error calculating swing plane: {str(e)}")
            return 0
            
    def _get_swing_plane_angle(self, start_landmarks: Dict, end_landmarks: Dict) -> float:
        """두 시점 사이의 스윙 플레인 각도 계산"""
        try:
            # 클럽 경로를 나타내는 벡터 계산
            start_point = np.array(start_landmarks['right_wrist'])
            end_point = np.array(end_landmarks['right_wrist'])
            path_vector = end_point - start_point
            
            # 지면에 대한 각도 계산
            ground_normal = np.array([0, 1, 0])
            cos_angle = np.dot(path_vector, ground_normal) / (np.linalg.norm(path_vector) * np.linalg.norm(ground_normal))
            angle = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
            
            return angle
            
        except Exception as e:
            logger.error(f"Error calculating swing plane angle: {str(e)}")
            return 0
            
    def _check_balance(self, frame_data: Dict) -> bool:
        """밸런스 체크"""
        try:
            hip_center = np.mean([
                frame_data['landmarks']['left_hip'],
                frame_data['landmarks']['right_hip']
            ], axis=0)
            
            ankle_center = np.mean([
                frame_data['landmarks']['left_ankle'],
                frame_data['landmarks']['right_ankle']
            ], axis=0)
            
            # 수직 축에서의 편차 계산
            deviation = abs(hip_center[0] - ankle_center[0])
            
            return deviation < 0.1  # 10cm 이내의 편차 허용
            
        except Exception as e:
            logger.error(f"Error checking balance: {str(e)}")
            return False
            
    def _check_spine_angle_maintenance(self, start_frame: Dict, end_frame: Dict) -> bool:
        """척추 각도 유지 여부 체크"""
        try:
            start_angle = start_frame['angles']['spine_angle']
            end_angle = end_frame['angles']['spine_angle']
            
            return abs(end_angle - start_angle) < 10  # 10도 이내 변화 허용
            
        except Exception as e:
            logger.error(f"Error checking spine angle maintenance: {str(e)}")
            return False
            
    def _check_wrist_hinge(self, frame_data: Dict) -> bool:
        """손목 힌지 각도 체크"""
        try:
            # 팔과 손목의 각도 계산
            elbow_wrist = np.array(frame_data['landmarks']['right_wrist']) - np.array(frame_data['landmarks']['right_elbow'])
            wrist_club = np.array([0, -1, 0])  # 가상의 클럽 방향
            
            cos_angle = np.dot(elbow_wrist, wrist_club) / (np.linalg.norm(elbow_wrist) * np.linalg.norm(wrist_club))
            angle = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
            
            return 80 <= angle <= 100  # 이상적인 손목 힌지 각도 범위
            
        except Exception as e:
            logger.error(f"Error checking wrist hinge: {str(e)}")
            return False
            
    def _check_weight_transfer(self, frame_data: Dict) -> bool:
        """체중 이동 체크"""
        try:
            left_pressure = frame_data['angles']['left_knee']
            right_pressure = frame_data['angles']['right_knee']
            
            # 임팩트 시 왼발에 더 많은 체중이 실려있어야 함
            return left_pressure > right_pressure
            
        except Exception as e:
            logger.error(f"Error checking weight transfer: {str(e)}")
            return False
            
    def _check_arm_extension(self, frame_data: Dict) -> bool:
        """팔 뻗음 체크"""
        try:
            right_arm_angle = frame_data['angles']['right_arm']
            return right_arm_angle >= 160  # 160도 이상 펴짐 필요
            
        except Exception as e:
            logger.error(f"Error checking arm extension: {str(e)}")
            return False
            
    def _check_finish_posture(self, frame_data: Dict) -> bool:
        """피니시 자세 체크"""
        try:
            # 척추 각도와 어깨 회전 체크
            spine_angle = frame_data['angles']['spine_angle']
            shoulder_rotation = frame_data['angles']['shoulder_rotation']
            
            return spine_angle >= 30 and shoulder_rotation >= 270
            
        except Exception as e:
            logger.error(f"Error checking finish posture: {str(e)}")
            return False 