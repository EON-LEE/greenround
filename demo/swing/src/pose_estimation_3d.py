import numpy as np
import cv2
import mediapipe as mp
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class PoseEstimator3D:
    def __init__(self):
        """3D 포즈 추정을 위한 초기화"""
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=2,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Optional[Dict]]:
        """프레임에서 3D 랜드마크 추출"""
        try:
            # BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 포즈 추정
            results = self.pose.process(frame_rgb)
            
            if results.pose_world_landmarks:
                # 3D 랜드마크 추출
                landmarks_3d = self._extract_landmarks_3d(results.pose_world_landmarks)
                
                # 시각화
                annotated_frame = self._visualize_landmarks(frame.copy(), results.pose_landmarks)
                
                return annotated_frame, landmarks_3d
            
            return frame, None
            
        except Exception as e:
            logger.error(f"Error in process_frame: {str(e)}")
            return frame, None
            
    def _extract_landmarks_3d(self, pose_world_landmarks) -> Dict:
        """MediaPipe 3D 랜드마크를 딕셔너리로 변환"""
        landmarks = {}
        
        # 주요 관절점 매핑
        landmark_mapping = {
            'nose': 0,
            'left_shoulder': 11,
            'right_shoulder': 12,
            'left_elbow': 13,
            'right_elbow': 14,
            'left_wrist': 15,
            'right_wrist': 16,
            'left_hip': 23,
            'right_hip': 24,
            'left_knee': 25,
            'right_knee': 26,
            'left_ankle': 27,
            'right_ankle': 28
        }
        
        for name, idx in landmark_mapping.items():
            landmark = pose_world_landmarks.landmark[idx]
            landmarks[name] = [landmark.x, landmark.y, landmark.z]
            
        return landmarks
        
    def _visualize_landmarks(self, frame: np.ndarray, pose_landmarks) -> np.ndarray:
        """2D 랜드마크 시각화"""
        if pose_landmarks is None:
            return frame
            
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
        
        # 랜드마크 그리기
        mp_drawing.draw_landmarks(
            frame,
            pose_landmarks,
            self.mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
        )
        
        return frame
        
    def calculate_3d_angles(self, landmarks: Dict) -> Dict[str, float]:
        """3D 각도 계산"""
        try:
            angles = {}
            
            # 척추 각도 계산
            hip_center = np.mean([landmarks['left_hip'], landmarks['right_hip']], axis=0)
            shoulder_center = np.mean([landmarks['left_shoulder'], landmarks['right_shoulder']], axis=0)
            vertical = hip_center + np.array([0, 1, 0])
            angles['spine_angle'] = self._calculate_angle_3d(vertical, hip_center, shoulder_center)
            
            # 어깨 회전 각도
            shoulder_vector = np.array(landmarks['right_shoulder']) - np.array(landmarks['left_shoulder'])
            forward = np.array([0, 0, 1])
            angles['shoulder_rotation'] = np.degrees(np.arctan2(shoulder_vector[0], shoulder_vector[2]))
            
            # 힙 회전 각도
            hip_vector = np.array(landmarks['right_hip']) - np.array(landmarks['left_hip'])
            angles['hip_rotation'] = np.degrees(np.arctan2(hip_vector[0], hip_vector[2]))
            
            # 팔 각도 (양쪽)
            angles['right_arm'] = self._calculate_angle_3d(
                landmarks['right_shoulder'],
                landmarks['right_elbow'],
                landmarks['right_wrist']
            )
            angles['left_arm'] = self._calculate_angle_3d(
                landmarks['left_shoulder'],
                landmarks['left_elbow'],
                landmarks['left_wrist']
            )
            
            # 무릎 각도 (양쪽)
            angles['right_knee'] = self._calculate_angle_3d(
                landmarks['right_hip'],
                landmarks['right_knee'],
                landmarks['right_ankle']
            )
            angles['left_knee'] = self._calculate_angle_3d(
                landmarks['left_hip'],
                landmarks['left_knee'],
                landmarks['left_ankle']
            )
            
            return angles
            
        except Exception as e:
            logger.error(f"Error calculating 3D angles: {str(e)}")
            return {}
            
    def _calculate_angle_3d(self, p1: List[float], p2: List[float], p3: List[float]) -> float:
        """세 점 사이의 3D 각도 계산"""
        v1 = np.array(p1) - np.array(p2)
        v2 = np.array(p3) - np.array(p2)
        
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        angle = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
        
        return angle 