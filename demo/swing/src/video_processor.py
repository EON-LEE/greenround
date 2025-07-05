import cv2
import numpy as np
from typing import Optional, Tuple, Generator, Dict
from pytube import YouTube
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles video processing from various sources (YouTube, local file, webcam)."""
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def process_youtube_url(self, url: str) -> str:
        """Download video from YouTube URL and return local path."""
        try:
            yt = YouTube(url)
            video = yt.streams.filter(progressive=True, file_extension='mp4').first()
            if not video:
                raise ValueError("No suitable video stream found")
            
            output_path = os.path.join(self.temp_dir, f"{yt.video_id}_{video.resolution}.mp4")
            video.download(output_path=os.path.dirname(output_path), filename=os.path.basename(output_path))
            return output_path
        except Exception as e:
            raise ValueError(f"Error processing YouTube URL: {str(e)}")
    
    def process_local_file(self, file_path: str) -> str:
        """Process local video file and return path."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        return file_path
    
    def get_video_properties(self, video_path: str) -> Dict[str, int]:
        """Get video properties (width, height, fps, total_frames) as a dictionary."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        cap.release()
        return {
            'width': width,
            'height': height,
            'fps': fps,
            'total_frames': total_frames
        }
    
    def extract_frames(self, video_path: str, 
                      start_frame: int = 0, 
                      end_frame: Optional[int] = None) -> Generator[np.ndarray, None, None]:
        """Extract frames from video as a generator."""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {video_path}")
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if end_frame is None:
                end_frame = total_frames
            
            # Set start position
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            logger.info(f"Starting frame extraction: {start_frame} to {end_frame}")
            frame_count = start_frame
            while frame_count < end_frame:
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame {frame_count}")
                    break
                    
                yield frame
                frame_count += 1
                if frame_count % 30 == 0:  # Log every 30 frames
                    logger.info(f"Processed {frame_count}/{end_frame} frames")
            
            logger.info(f"Completed frame extraction: {frame_count} frames processed")
        except Exception as e:
            logger.error(f"Error during frame extraction: {str(e)}")
            raise
        finally:
            cap.release()
    
    def get_frame_at_index(self, video_path: str, index: int) -> Optional[np.ndarray]:
        """Reads and returns a single frame at the specified index."""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.warning(f"Could not open video {video_path} to get frame at index {index}")
                return None
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if index < 0 or index >= total_frames:
                logger.warning(f"Frame index {index} is out of bounds (0-{total_frames-1}).")
                cap.release()
                return None
                
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ret, frame = cap.read()
            
            if not ret:
                logger.warning(f"Failed to read frame at index {index} from {video_path}.")
                return None
                
            return frame
        except Exception as e:
            logger.error(f"Error reading frame at index {index}: {str(e)}")
            return None
        finally:
            cap.release()
    
    def cleanup(self):
        """Clean up temporary files."""
        try:
            for file in os.listdir(self.temp_dir):
                try:
                    os.remove(os.path.join(self.temp_dir, file))
                except Exception as e:
                    logger.warning(f"Could not remove temp file {file}: {e}")
            os.rmdir(self.temp_dir)
            logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error during cleanup of {self.temp_dir}: {e}") 