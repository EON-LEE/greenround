import cv2
import mediapipe as mp
import numpy as np
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

@dataclass
class PoseLandmarks:
    """Data class for storing pose landmarks."""
    left_shoulder: np.ndarray
    right_shoulder: np.ndarray
    left_elbow: np.ndarray
    right_elbow: np.ndarray
    left_wrist: np.ndarray
    right_wrist: np.ndarray
    left_hip: np.ndarray
    right_hip: np.ndarray
    left_knee: np.ndarray
    right_knee: np.ndarray
    left_ankle: np.ndarray
    right_ankle: np.ndarray
    nose: np.ndarray

class PoseEstimator:
    """Handles pose estimation using MediaPipe."""
    
    def __init__(self, 
                 min_detection_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Optional[PoseLandmarks]]:
        """Process a single frame and return annotated frame with landmarks."""
        try:
            # Convert the BGR image to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process the frame and get pose landmarks
            results = self.pose.process(rgb_frame)
            
            # Debug information
            print(f"DEBUG process_frame - results type: {type(results)}")
            print(f"DEBUG process_frame - has pose_landmarks: {results.pose_landmarks is not None}")
            
            # Draw pose landmarks on the frame
            annotated_frame = frame.copy()
            if results.pose_landmarks:
                print(f"DEBUG process_frame - pose_landmarks type: {type(results.pose_landmarks)}")
                
                self.mp_drawing.draw_landmarks(
                    annotated_frame,
                    results.pose_landmarks,
                    self.mp_pose.POSE_CONNECTIONS
                )
                
                try:
                    landmarks = self._extract_landmarks(results.pose_landmarks)
                    return annotated_frame, landmarks
                except Exception as e:
                    print(f"ERROR extracting landmarks: {str(e)}")
                    print(f"Error type: {type(e)}")
                    print(f"Error args: {e.args}")
                    return annotated_frame, None
            else:
                return annotated_frame, None
                
        except Exception as e:
            print(f"ERROR in process_frame: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Error args: {e.args}")
            # Return original frame on error
            return frame, None
    
    def _extract_landmarks(self, landmarks) -> PoseLandmarks:
        """Extract relevant landmarks from MediaPipe results."""
        try:
            print(f"DEBUG _extract_landmarks - landmarks type: {type(landmarks)}")
            
            # Try to get one landmark first to test
            test_landmark = self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_SHOULDER)
            print(f"DEBUG _extract_landmarks - test landmark result: {test_landmark}")
            
            return PoseLandmarks(
                left_shoulder=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_SHOULDER),
                right_shoulder=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_SHOULDER),
                left_elbow=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_ELBOW),
                right_elbow=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_ELBOW),
                left_wrist=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_WRIST),
                right_wrist=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_WRIST),
                left_hip=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_HIP),
                right_hip=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_HIP),
                left_knee=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_KNEE),
                right_knee=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_KNEE),
                left_ankle=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.LEFT_ANKLE),
                right_ankle=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.RIGHT_ANKLE),
                nose=self._get_landmark_coords_debug(landmarks, self.mp_pose.PoseLandmark.NOSE)
            )
        except Exception as e:
            print(f"ERROR in _extract_landmarks: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Error args: {e.args}")
            # Create a dummy landmarks object with zeros to prevent pipeline failure
            zero_array = np.array([0.0, 0.0, 0.0])
            return PoseLandmarks(
                left_shoulder=zero_array,
                right_shoulder=zero_array,
                left_elbow=zero_array,
                right_elbow=zero_array,
                left_wrist=zero_array,
                right_wrist=zero_array,
                left_hip=zero_array,
                right_hip=zero_array,
                left_knee=zero_array,
                right_knee=zero_array,
                left_ankle=zero_array,
                right_ankle=zero_array,
                nose=zero_array
            )
    
    def _get_landmark_coords(self, landmarks, landmark_idx) -> np.ndarray:
        """Get coordinates of a specific landmark."""
        landmark = landmarks.landmark[landmark_idx]
        return np.array([landmark.x, landmark.y, landmark.z])
        
    def _get_landmark_coords_debug(self, landmarks, landmark_idx) -> np.ndarray:
        """Get coordinates of a specific landmark with debug info."""
        result = np.array([0.0, 0.0, 0.0]) # Default result
        try:
            # print(f"DEBUG _get_landmark_coords_debug - landmark_idx: {landmark_idx}")
            # print(f"DEBUG _get_landmark_coords_debug - landmarks.landmark type: {type(landmarks.landmark)}")
            landmark = landmarks.landmark[landmark_idx]
            # print(f"DEBUG _get_landmark_coords_debug - landmark type: {type(landmark)}")
            
            # Try attribute access first
            if hasattr(landmark, 'x') and hasattr(landmark, 'y') and hasattr(landmark, 'z'):
                try:
                    result = np.array([landmark.x, landmark.y, landmark.z], dtype=float)
                    # print(f"DEBUG _get_landmark_coords_debug - result (attr): {result}, type: {type(result)}")
                except Exception as e:
                    print(f"ERROR accessing landmark properties via attribute (.x, .y, .z): {e}")
            # Try index access if attribute access failed or attributes don't exist
            elif hasattr(landmark, '__getitem__'):
                try:
                    # print("Attempting access via index [0], [1], [2]")
                    result = np.array([landmark[0], landmark[1], landmark[2]], dtype=float)
                    # print(f"DEBUG _get_landmark_coords_debug (indexed) - result: {result}, type: {type(result)}")
                except Exception as ie:
                    print(f"ERROR accessing landmark properties via index: {ie}")
            else:
                 print(f"WARNING: Landmark object has neither attributes (.x) nor index access. Properties: {dir(landmark)}")
                
        except IndexError as ie:
            print(f"ERROR in _get_landmark_coords_debug (IndexError): Invalid landmark_idx {landmark_idx}? {ie}")
        except Exception as e:
            print(f"ERROR in _get_landmark_coords_debug (initial access): {str(e)}")
            print(f"Error type: {type(e)}")
            
        # *** Final type assertion before returning ***
        if not isinstance(result, np.ndarray):
            print(f"CRITICAL ERROR: _get_landmark_coords_debug is about to return non-ndarray! Type: {type(result)}. Forcing to zeros.")
            result = np.array([0.0, 0.0, 0.0])
            
        return result
    
    def calculate_angles(self, landmarks: PoseLandmarks) -> Dict[str, float]:
        """Calculate various angles from pose landmarks, including new notebook-based angles."""
        if landmarks is None:
            print("WARNING: landmarks is None in calculate_angles")
            return {}
            
        angles = {}
        try:
            # Existing Angles
            angles['left_arm'] = self._calculate_angle_safe(landmarks.left_shoulder, landmarks.left_elbow, landmarks.left_wrist)
            angles['right_arm'] = self._calculate_angle_safe(landmarks.right_shoulder, landmarks.right_elbow, landmarks.right_wrist)
            angles['left_leg'] = self._calculate_angle_safe(landmarks.left_hip, landmarks.left_knee, landmarks.left_ankle)
            angles['right_leg'] = self._calculate_angle_safe(landmarks.right_hip, landmarks.right_knee, landmarks.right_ankle)
            angles['shoulder_angle'] = self._calculate_angle_safe(landmarks.left_shoulder, landmarks.right_shoulder, landmarks.right_hip)

            # --- New Angles from Notebook --- 
            # Knee Angles
            angles['left_knee_angle'] = self._calculate_angle_safe(landmarks.left_hip, landmarks.left_knee, landmarks.left_ankle)
            angles['right_knee_angle'] = self._calculate_angle_safe(landmarks.right_hip, landmarks.right_knee, landmarks.right_ankle)
            
            # Shoulder Inclination (angle of the shoulder line relative to horizontal)
            angles['shoulders_inclination'] = self._calculate_inclination(landmarks.left_shoulder, landmarks.right_shoulder)
            
            # Hip Inclination (angle of the hip line relative to horizontal)
            angles['hips_inclination'] = self._calculate_inclination(landmarks.left_hip, landmarks.right_hip)

            # Pelvis Angle (e.g., relative to shoulders - check notebook logic if needed)
            # This might require more complex calculation, using hips and shoulders
            # For now, let's keep it simple or add based on a clearer definition
            # angles['pelvis_angle'] = ... 

            print(f"DEBUG calculate_angles - calculated angles: {angles}")
            return angles
            
        except Exception as e:
            print(f"ERROR in calculate_angles: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Error args: {e.args}")
            # Return empty dict or partial dict on error
            # Filling with 0.0 for safety, but consider logging which failed
            default_angles = {
                'left_arm': 0.0, 'right_arm': 0.0, 'left_leg': 0.0, 'right_leg': 0.0,
                'shoulder_angle': 0.0, 'left_knee_angle': 0.0, 'right_knee_angle': 0.0,
                'shoulders_inclination': 0.0, 'hips_inclination': 0.0
            }
            # Update with successfully calculated angles before the error
            default_angles.update(angles)
            return default_angles
    
    def _calculate_angle_safe(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        """Safely calculate angle between three points in 3D space."""
        try:
            # Check if points are valid (e.g., not [0,0,0] if that indicates missing data)
            if np.all(a == 0) or np.all(b == 0) or np.all(c == 0):
                 return 0.0 # Return 0 if any point is invalid
                 
            ba = a - b
            bc = c - b
            
            norm_ba = np.linalg.norm(ba)
            norm_bc = np.linalg.norm(bc)
            
            if norm_ba == 0 or norm_bc == 0:
                return 0.0 # Avoid division by zero
                
            cosine_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
            angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
            
            return np.degrees(angle)
        except Exception as e:
            print(f"ERROR in _calculate_angle_safe: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Error args: {e.args}")
            print(f"Point a: {a}, type: {type(a)}")
            print(f"Point b: {b}, type: {type(b)}")
            print(f"Point c: {c}, type: {type(c)}")
            return 0.0
            
    def _calculate_inclination(self, p1: np.ndarray, p2: np.ndarray) -> float:
        """Calculate the angle of the line between p1 and p2 relative to the horizontal plane (using x, y coordinates)."""
        try:
            if np.all(p1 == 0) or np.all(p2 == 0):
                 return 0.0
                 
            delta_y = p1[1] - p2[1]
            delta_x = p1[0] - p2[0]
            
            if delta_x == 0: # Vertical line
                 return 90.0 if delta_y > 0 else -90.0
            
            angle_radians = np.arctan2(delta_y, delta_x)
            angle_degrees = np.degrees(angle_radians)
            
            # Normalize angle to be between -90 and 90 or 0 and 180 depending on convention
            # The notebook might have a specific convention, adjust if needed
            return angle_degrees
        except Exception as e:
            print(f"ERROR in _calculate_inclination: {str(e)}")
            return 0.0 