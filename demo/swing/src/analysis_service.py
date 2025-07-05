import time
import json
import os
from typing import Dict, Optional
import logging
from datetime import datetime, timedelta
from pose_estimation import PoseEstimator
from swing_analyzer import SwingAnalyzer
import cv2

logger = logging.getLogger(__name__)

class SwingAnalysisService:
    def __init__(self):
        self.cache_dir = "cache"
        self.cache_duration = timedelta(minutes=30)  # Cache results for 30 minutes
        self.pose_estimator = PoseEstimator()
        self.swing_analyzer = SwingAnalyzer()
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get_cache_path(self, video_id: str) -> str:
        """Get the cache file path for a video ID."""
        return os.path.join(self.cache_dir, f"{video_id}_analysis.json")

    def get_analysis(self, video_id: str) -> Optional[Dict]:
        """Get analysis result from cache if available."""
        cache_path = self.get_cache_path(video_id)
        
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time <= self.cache_duration:
                    logger.info(f"Returning cached analysis for video {video_id}")
                    return cached_data['result']
                    
        except Exception as e:
            logger.error(f"Error reading cache for video {video_id}: {str(e)}")
            
        return None

    def save_analysis(self, video_id: str, result: Dict):
        """Save analysis result to cache."""
        cache_path = self.get_cache_path(video_id)
        
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'result': result
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
                
        except Exception as e:
            logger.error(f"Error saving cache for video {video_id}: {str(e)}")

    def analyze_swing(self, video_id: str, force_new: bool = False) -> Dict:
        """Analyze golf swing video."""
        # Check cache first if not forcing new analysis
        if not force_new:
            cached_result = self.get_analysis(video_id)
            if cached_result:
                return cached_result

        try:
            logger.info(f"Performing new analysis for video {video_id}")
            
            # Get video path
            video_path = os.path.join("uploads", video_id)
            if not os.path.exists(video_path):
                raise ValueError(f"Video file not found: {video_path}")
            
            # Perform pose estimation and analysis
            frames_data = []
            frame_angles = []
            key_frames = {}
            
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_count = 0
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Process frame
                processed_frame, landmarks = self.pose_estimator.process_frame(frame)
                if landmarks:
                    angles = self.pose_estimator.calculate_angles(landmarks)
                    frame_angles.append(angles)
                    frames_data.append({
                        'angles': angles,
                        'landmarks': landmarks.to_dict()
                    })
                    
                    # Detect key frames
                    if frame_count == 0:
                        key_frames['address'] = frame_count
                    elif frame_count == int(total_frames * 0.3):
                        key_frames['backswing'] = frame_count
                    elif frame_count == int(total_frames * 0.5):
                        key_frames['top'] = frame_count
                    elif frame_count == int(total_frames * 0.7):
                        key_frames['impact'] = frame_count
                    elif frame_count == int(total_frames * 0.85):
                        key_frames['follow_through'] = frame_count
                    elif frame_count == total_frames - 1:
                        key_frames['finish'] = frame_count
                        
                frame_count += 1
                
            cap.release()
            
            # Calculate metrics
            metrics = self.swing_analyzer.analyze(frame_angles)
            
            # Create result
            analysis_result = {
                'frames': frames_data,
                'metrics': metrics,
                'key_frames': key_frames
            }
            
            # Save to cache
            self.save_analysis(video_id, analysis_result)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing video {video_id}: {str(e)}")
            raise

    def clear_cache(self, video_id: Optional[str] = None):
        """Clear analysis cache for specific video or all videos."""
        try:
            if video_id:
                cache_path = self.get_cache_path(video_id)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                    logger.info(f"Cleared cache for video {video_id}")
            else:
                for file in os.listdir(self.cache_dir):
                    if file.endswith("_analysis.json"):
                        os.remove(os.path.join(self.cache_dir, file))
                logger.info("Cleared all analysis cache")
                
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}") 