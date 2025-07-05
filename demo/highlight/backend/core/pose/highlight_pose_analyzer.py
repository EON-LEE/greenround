import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List
from scipy.signal import find_peaks
import logging

from .base_pose_analyzer import BasePoseAnalyzer

logger = logging.getLogger(__name__)

class HighlightPoseAnalyzer(BasePoseAnalyzer):
    """
    하이라이트 영상 생성에 특화된 포즈 분석기.
    3단계 하이라이트에 필요한 최적의 스윙 1개를 감지합니다.
    """
    
    def analyze_for_highlight(self, video_path: str, progress_callback=None) -> Dict:
        """
        하이라이트 생성을 위한 비디오 분석.
        
        Returns:
            Dict: {
                "video_info": {...},
                "best_swing": {...},  # 가장 좋은 스윙 1개
                "file_id": "..."
            }
        """
        video_path_obj = Path(video_path)
        file_id = video_path_obj.name
        
        try:
            logger.info(f"하이라이트용 비디오 분석 시작: {file_id}")
            
            # 프레임 추출
            frames, fps, width, height, _ = self._extract_frames_and_audio(video_path_obj)
            time_delta = 1 / fps if fps > 0 else 0
            total_frames = len(frames)
            
            # 프레임별 분석
            frames_data = []
            prev_pose_landmarks = None
            
            for i, frame in enumerate(frames):
                # Progress callback 호출
                if progress_callback and total_frames > 0:
                    progress = int((i / total_frames) * 100)
                    progress_callback(progress)
                
                # MediaPipe 처리
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.pose.process(rgb_frame)
                
                # 랜드마크 추출
                current_pose_landmarks = self._extract_landmarks(results)
                joint_speeds = self._calculate_joint_speeds(prev_pose_landmarks, current_pose_landmarks, time_delta)
                
                total_motion = sum(joint_speeds.values())
                pose_quality = self._calculate_pose_quality(current_pose_landmarks)
                
                frame_data = {
                    'frame_number': i,
                    'landmarks': current_pose_landmarks,
                    'total_motion': total_motion,
                    'pose_quality': pose_quality,
                    **joint_speeds
                }
                frames_data.append(frame_data)
                prev_pose_landmarks = current_pose_landmarks
            
            # 최적의 스윙 감지
            best_swing = self._detect_best_swing(frames_data, fps)
            
            # 비디오 정보
            video_info = {
                'total_frames': len(frames), 
                'fps': fps, 
                'duration': len(frames) / fps if fps > 0 else 0, 
                'width': width, 
                'height': height
            }
            
            return {
                "video_info": video_info, 
                "best_swing": best_swing, 
                "file_id": file_id
            }
            
        except Exception as e:
            logger.error(f"하이라이트용 비디오 분석 중 오류 ({file_id}): {e}", exc_info=True)
            raise
    
    def _detect_best_swing(self, frames_data: List[Dict], fps: float) -> Dict:
        """
        하이라이트에 가장 적합한 스윙 1개를 감지합니다.
        품질과 움직임을 종합적으로 고려합니다.
        """
        if len(frames_data) < 30:  # 최소 1초 분량
            logger.warning("영상이 너무 짧아 전체를 스윙으로 처리합니다.")
            return self._create_fallback_swing(frames_data)
        
        # 손목 움직임 분석
        wrist_motion = self._calculate_wrist_motion(frames_data)
        total_body_motion = self._calculate_total_body_motion(frames_data)
        smoothed_motion = self._smooth_motion_data(wrist_motion)
        
        # 스윙 후보 찾기
        swing_candidates = self._find_swing_candidates(smoothed_motion, total_body_motion, fps)
        
        if not swing_candidates:
            logger.warning("스윙 후보가 없어 전체를 스윙으로 처리합니다.")
            return self._create_fallback_swing(frames_data)
        
        # 최고 품질의 스윙 선택
        best_swing = self._select_best_swing_candidate(swing_candidates, frames_data)
        
        # 키 이벤트 추가
        best_swing['key_events'] = self._detect_key_events(
            frames_data, best_swing['start_frame'], best_swing['end_frame']
        )
        
        logger.info(f"최적의 스윙 선택: 프레임 {best_swing['start_frame']}-{best_swing['end_frame']} (품질: {best_swing['quality']:.2f})")
        return best_swing
    
    def _find_swing_candidates(self, smoothed_motion: List[float], total_body_motion: List[float], fps: float) -> List[Dict]:
        """스윙 후보들을 찾습니다."""
        # 피크 감지 (더 관대한 설정)
        motion_array = np.array(smoothed_motion)
        threshold = np.mean(motion_array) + np.std(motion_array) * 0.3  # 임계값 낮춤
        min_distance = int(fps * 0.8)  # 최소 간격
        
        peaks, _ = find_peaks(motion_array, height=threshold, distance=min_distance)
        
        candidates = []
        for peak_idx in peaks:
            start_frame, end_frame = self._find_swing_boundaries(
                peak_idx, smoothed_motion, total_body_motion, fps
            )
            
            # 최소 지속시간 확인 (0.5초 이상)
            if end_frame - start_frame >= fps * 0.5:
                candidates.append({
                    'start_frame': start_frame,
                    'end_frame': end_frame,
                    'peak_frame': peak_idx,
                    'duration': end_frame - start_frame
                })
        
        return candidates
    
    def _find_swing_boundaries(self, peak_idx: int, wrist_motion: List[float], 
                             total_body_motion: List[float], fps: float) -> tuple:
        """스윙의 시작과 끝 지점을 찾습니다."""
        # 시작점 찾기 (어드레스)
        peak_value = wrist_motion[peak_idx]
        start_threshold = max(peak_value * 0.15, 0.01)
        
        start_frame = 0
        for i in range(peak_idx - 1, -1, -1):
            if wrist_motion[i] < start_threshold:
                start_frame = max(0, i - int(fps * 0.5))  # 여유 추가
                break
        
        # 끝점 찾기 (피니시)
        end_frame = len(total_body_motion) - 1
        finish_threshold = np.mean(total_body_motion) * 0.3
        
        for i in range(peak_idx + int(fps * 0.2), len(total_body_motion)):
            if total_body_motion[i] < finish_threshold:
                end_frame = min(len(total_body_motion) - 1, i + int(fps * 0.5))  # 여유 추가
                break
        
        return start_frame, end_frame
    
    def _select_best_swing_candidate(self, candidates: List[Dict], frames_data: List[Dict]) -> Dict:
        """후보 중에서 가장 좋은 스윙을 선택합니다."""
        best_swing = None
        best_score = -1
        
        for i, candidate in enumerate(candidates):
            start_frame = candidate['start_frame']
            end_frame = candidate['end_frame']
            
            # 품질 계산
            swing_frames = frames_data[start_frame:end_frame + 1]
            avg_quality = np.mean([f['pose_quality'] for f in swing_frames])
            avg_motion = np.mean([f['total_motion'] for f in swing_frames])
            duration = candidate['duration']
            
            # 종합 점수 (품질 + 움직임 + 지속시간)
            score = (
                avg_quality * 0.4 +  # 포즈 품질
                min(avg_motion / 0.1, 1.0) * 0.4 +  # 움직임 정도 (정규화)
                min(duration / (30 * 3), 1.0) * 0.2  # 적절한 길이 (3초 정도가 이상적)
            )
            
            if score > best_score:
                best_score = score
                best_swing = {
                    'id': 0,
                    'start_frame': start_frame,
                    'end_frame': end_frame,
                    'peak_frame': candidate['peak_frame'],
                    'quality': avg_quality,
                    'score': score
                }
        
        return best_swing if best_swing else self._create_fallback_swing(frames_data)
    
    def _create_fallback_swing(self, frames_data: List[Dict]) -> Dict:
        """스윙 감지 실패 시 사용할 fallback 스윙을 생성합니다."""
        total_frames = len(frames_data)
        
        # 전체 영상을 스윙으로 처리하되, 너무 길면 중간 부분만 사용
        if total_frames > 150:  # 5초 이상이면
            start_frame = total_frames // 4
            end_frame = (total_frames * 3) // 4
        else:
            start_frame = 0
            end_frame = total_frames - 1
        
        avg_quality = np.mean([f['pose_quality'] for f in frames_data[start_frame:end_frame + 1]])
        
        return {
            'id': 0,
            'start_frame': start_frame,
            'end_frame': end_frame,
            'peak_frame': (start_frame + end_frame) // 2,
            'quality': avg_quality,
            'score': 0.5
        } 