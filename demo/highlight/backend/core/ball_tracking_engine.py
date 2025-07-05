import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging
from .ball_tracker import BallTracker
from .pose.ball_pose_analyzer import BallPoseAnalyzer
from .utils import (
    update_task_status,
    get_file_path,
    upload_to_gcs_and_get_public_url,
    TEMP_DIR
)

logger = logging.getLogger(__name__)

class BallTrackingEngine:
    """
    볼 트래킹 영상 생성 엔진.
    포즈 분석과 볼 트래킹을 통합하여 궤적이 그려진 영상을 생성합니다.
    """
    
    def __init__(self):
        self.pose_analyzer = BallPoseAnalyzer()
    
    def create_ball_tracking_video(self, file_id: str, task_id: str) -> Dict:
        """
        볼 트래킹 영상을 생성합니다.
        
        Args:
            file_id: 업로드된 비디오 파일 ID
            task_id: 작업 추적 ID
        
        Returns:
            Dict: 작업 결과 정보
        """
        try:
            update_task_status(task_id, "processing", 0, "볼 트래킹 분석 시작")
            
            # 1. 입력 파일 확인
            video_path = get_file_path(file_id, "uploads")
            if not video_path.exists():
                raise FileNotFoundError(f"업로드된 파일을 찾을 수 없습니다: {video_path}")
            
            # 2. BallTracker 초기화 및 분석
            update_task_status(task_id, "processing", 10, "포즈 분석 및 임팩트 지점 탐지")
            ball_tracker = BallTracker(str(video_path), self.pose_analyzer)
            
            # 3. 비디오 분석 (임팩트, 어드레스 지점 찾기)
            analysis_result = ball_tracker.analyze_video()
            
            update_task_status(task_id, "processing", 30, "어드레스에서 골프공 탐지")
            
            # 4. 어드레스에서 골프공 찾기
            ball_bbox = ball_tracker.find_stationary_ball()
            if ball_bbox is None:
                # 최종 fallback: 발목 중심 근처에 가상의 공 위치 설정
                logger.warning("골프공을 찾을 수 없어 추정 위치를 사용합니다.")
                analysis_result = ball_tracker.analysis_result
                address_frame = analysis_result['address_frame']
                landmarks = analysis_result['frames_data'][address_frame].get('landmarks', {})
                
                if landmarks.get('left_ankle') and landmarks.get('right_ankle'):
                    left_ankle = landmarks['left_ankle']
                    right_ankle = landmarks['right_ankle']
                    
                    # 발목 좌표 추출
                    if isinstance(left_ankle, dict) and 'point' in left_ankle:
                        left_point = left_ankle['point']
                    else:
                        left_point = left_ankle
                        
                    if isinstance(right_ankle, dict) and 'point' in right_ankle:
                        right_point = right_ankle['point']
                    else:
                        right_point = right_ankle
                    
                    # 발 중앙 앞쪽에 공 위치 추정
                    center_x = int((left_point[0] + right_point[0]) / 2 * ball_tracker.video_width)
                    center_y = int(max(left_point[1], right_point[1]) * ball_tracker.video_height + 20)
                    
                    # 기본 공 크기 (화면 크기의 1%)
                    ball_radius = max(10, int(ball_tracker.video_width * 0.01))
                    ball_bbox = (center_x - ball_radius, center_y - ball_radius, 
                               ball_radius * 2, ball_radius * 2)
                    
                    logger.info(f"추정된 공 위치: {ball_bbox}")
                else:
                    raise ValueError("어드레스에서 골프공을 찾을 수 없고, 발목 랜드마크도 없습니다.")
            
            update_task_status(task_id, "processing", 50, "볼 궤적 추적 및 영상 생성")
            
            # 5. 출력 파일 경로 설정
            local_output_path = TEMP_DIR / f"{task_id}.mp4"
            
            # 6. 볼 트래킹 및 궤적 영상 생성
            def progress_callback(progress):
                update_task_status(task_id, "processing", 50 + int(progress * 0.4), f"볼 트래킹 진행: {progress}%")
            
            tracking_result = ball_tracker.track_and_draw_trajectory(
                output_path=local_output_path,
                update_callback=progress_callback
            )
            
            update_task_status(task_id, "processing", 95, "GCS 업로드 중")
            
            # 7. GCS 업로드
            gcs_destination_path = f"ball_tracks/{task_id}.mp4"
            public_url = upload_to_gcs_and_get_public_url(local_output_path, gcs_destination_path)
            
            # 8. 결과 데이터 준비
            result_data = {
                "download_url": public_url,
                "analysis_summary": {
                    "impact_frame": analysis_result['impact_frame'],
                    "address_frame": analysis_result['address_frame'],
                    "swing_range": analysis_result['swing_range'],
                    "ball_initial_position": ball_bbox,
                    "tracking_metrics": tracking_result.get('metrics', {})
                }
            }
            
            update_task_status(task_id, "completed", 100, "볼 트래킹 영상 생성 완료", result_data=result_data)
            
            return result_data
            
        except Exception as e:
            logger.error(f"볼 트래킹 영상 생성 중 오류: {e}", exc_info=True)
            update_task_status(task_id, "failed", 0, f"오류: {e}")
            raise e
    
    def get_ball_analysis_only(self, file_id: str, task_id: str) -> Dict:
        """
        볼 분석만 수행하고 결과를 반환합니다 (영상 생성 없이).
        
        Args:
            file_id: 업로드된 비디오 파일 ID
            task_id: 작업 추적 ID
        
        Returns:
            Dict: 분석 결과
        """
        try:
            update_task_status(task_id, "processing", 0, "볼 분석 시작")
            
            video_path = get_file_path(file_id, "uploads")
            if not video_path.exists():
                raise FileNotFoundError(f"업로드된 파일을 찾을 수 없습니다: {video_path}")
            
            # BallTracker 초기화 및 분석
            ball_tracker = BallTracker(str(video_path), self.pose_analyzer)
            
            update_task_status(task_id, "processing", 30, "포즈 분석 수행")
            analysis_result = ball_tracker.analyze_video()
            
            update_task_status(task_id, "processing", 60, "골프공 위치 탐지")
            ball_bbox = ball_tracker.find_stationary_ball()
            
            # 결과 데이터 준비
            result_data = {
                "impact_frame": analysis_result['impact_frame'],
                "address_frame": analysis_result['address_frame'],
                "swing_range": analysis_result['swing_range'],
                "ball_position": ball_bbox,
                "video_info": analysis_result['video_info']
            }
            
            update_task_status(task_id, "completed", 100, "볼 분석 완료", result_data=result_data)
            
            return result_data
            
        except Exception as e:
            logger.error(f"볼 분석 중 오류: {e}", exc_info=True)
            update_task_status(task_id, "failed", 0, f"오류: {e}")
            raise e 