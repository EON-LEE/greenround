import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List
from scipy.signal import find_peaks
import logging

from .base_pose_analyzer import BasePoseAnalyzer

logger = logging.getLogger(__name__)

class SequencePoseAnalyzer(BasePoseAnalyzer):
    """
    시퀀스 이미지 생성에 특화된 포즈 분석기.
    프레임 저장과 키프레임 추출에 최적화되어 있습니다.
    """
    
    def analyze_for_sequence(self, video_path: str, store_frames=True) -> Dict:
        """
        시퀀스 이미지 생성을 위한 비디오 분석.
        
        Returns:
            Dict: {
                "frames_data": [...],  # 프레임 데이터 포함
                "key_swing": {...},    # 키프레임용 스윙
                "file_id": "..."
            }
        """
        video_path_obj = Path(video_path)
        file_id = video_path_obj.name
        
        try:
            logger.info(f"시퀀스용 비디오 분석 시작: {file_id}")
            
            # 프레임 추출
            frames, fps, width, height, _ = self._extract_frames_and_audio(video_path_obj)
            time_delta = 1 / fps if fps > 0 else 0
            
            # 프레임별 분석 (시퀀스용은 모든 프레임 저장)
            frames_data = []
            prev_pose_landmarks = None
            
            for i, frame in enumerate(frames):
                # 프레임 크기 고정 (MediaPipe 오류 방지)
                resized_frame = cv2.resize(frame, (width, height))
                
                # MediaPipe 처리
                rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
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
                
                # 시퀀스 생성시 프레임 저장 필요
                if store_frames:
                    frame_data['frame'] = resized_frame  # 크기 조절된 프레임 저장
                    
                frames_data.append(frame_data)
                prev_pose_landmarks = current_pose_landmarks
            
            # 키프레임 추출에 적합한 스윙 감지
            key_swing = self._detect_key_swing(frames_data, fps)
            
            return {
                "frames_data": frames_data,
                "key_swing": key_swing,
                "file_id": file_id
            }
            
        except Exception as e:
            logger.error(f"시퀀스용 비디오 분석 중 오류 ({file_id}): {e}", exc_info=True)
            raise
    
    def _detect_key_swing(self, frames_data: List[Dict], fps: float) -> Dict:
        """
        키프레임 추출에 가장 적합한 스윙을 감지합니다.
        하이라이트와 동일한 손목 기반 감지 방식을 사용합니다.
        """
        if len(frames_data) < 30:  # 최소 1초 분량
            logger.warning("영상이 너무 짧아 전체를 스윙으로 처리합니다.")
            return self._create_full_swing(frames_data)
        
        # 하이라이트와 동일한 방식으로 손목 움직임 분석
        wrist_motion = self._calculate_wrist_motion(frames_data)
        total_body_motion = self._calculate_total_body_motion(frames_data)
        smoothed_motion = self._smooth_motion_data(wrist_motion)
        
        # 스윙 후보 찾기 (하이라이트와 동일한 로직)
        swing_candidates = self._find_swing_candidates_like_highlight(smoothed_motion, total_body_motion, fps)
        
        if not swing_candidates:
            logger.warning("스윙 후보가 없어 전체를 스윙으로 처리합니다.")
            return self._create_full_swing(frames_data)
        
        # 시퀀스에 가장 적합한 스윙 선택 (품질 우선)
        best_swing = self._select_best_sequence_swing(swing_candidates, frames_data)
        
        # 키 이벤트 추가
        best_swing['key_events'] = self._detect_key_events(
            frames_data, best_swing['start_frame'], best_swing['end_frame']
        )
        
        logger.info(f"시퀀스용 스윙 선택: 프레임 {best_swing['start_frame']}-{best_swing['end_frame']} (품질: {best_swing['quality']:.2f})")
        return best_swing
    
    def _find_good_quality_regions(self, quality_scores: List[float], fps: float) -> List[tuple]:
        """포즈 품질이 좋은 연속 구간들을 찾습니다."""
        quality_threshold = 0.6  # 시퀀스용은 높은 품질 요구
        min_duration_frames = int(fps * 1.0)  # 최소 1초
        
        regions = []
        region_start = None
        
        for i, quality in enumerate(quality_scores):
            if quality >= quality_threshold:
                if region_start is None:
                    region_start = i
            else:
                if region_start is not None:
                    # 구간 종료
                    if i - region_start >= min_duration_frames:
                        regions.append((region_start, i - 1))
                    region_start = None
        
        # 마지막 구간 처리
        if region_start is not None:
            if len(quality_scores) - region_start >= min_duration_frames:
                regions.append((region_start, len(quality_scores) - 1))
        
        return regions
    
    def _find_swing_in_region(self, frames_data: List[Dict], region_start: int, 
                            region_end: int, region_motion: List[float], fps: float) -> Dict:
        """특정 구간에서 핵심 스윙 패턴을 찾습니다."""
        motion_array = np.array(region_motion)
        
        if len(motion_array) < 10:
            return None
        
        # 움직임 패턴 분석
        motion_threshold = np.mean(motion_array) + np.std(motion_array) * 0.3
        peaks, _ = find_peaks(motion_array, height=motion_threshold, distance=int(fps * 0.3))
        
        if len(peaks) == 0:
            return None
        
        # 가장 큰 피크를 임팩트로 추정
        best_peak_idx = peaks[np.argmax([motion_array[p] for p in peaks])]
        impact_frame = region_start + best_peak_idx
        
        # 백스윙 시작점 찾기 (임팩트 이전의 조용한 구간)
        backswing_start = self._find_swing_start(motion_array, best_peak_idx, fps)
        swing_start = region_start + backswing_start
        
        # 피니시 끝점 찾기 (임팩트 이후의 안정화 구간)
        finish_end = self._find_swing_end(motion_array, best_peak_idx, fps)
        swing_end = region_start + finish_end
        
        # 스윙 길이 제한 (너무 길면 핵심 부분만)
        max_swing_duration = int(fps * 4)  # 최대 4초
        if swing_end - swing_start > max_swing_duration:
            # 임팩트 중심으로 균등하게 자르기
            half_duration = max_swing_duration // 2
            swing_start = max(swing_start, impact_frame - half_duration)
            swing_end = min(swing_end, impact_frame + half_duration)
        
        # 품질 점수 계산
        swing_frames = frames_data[swing_start:swing_end + 1]
        avg_quality = np.mean([f['pose_quality'] for f in swing_frames])
        avg_motion = np.mean([f['total_motion'] for f in swing_frames])
        duration = swing_end - swing_start
        
        # 시퀀스용 점수 (품질과 적절한 길이 우선)
        score = (
            avg_quality * 0.5 +  # 포즈 품질
            min(avg_motion / 0.1, 1.0) * 0.3 +  # 적당한 움직임
            (1.0 if fps * 1.5 <= duration <= fps * 4 else 0.5) * 0.2  # 적절한 길이 (1.5-4초)
        )
        
        return {
            'start_frame': swing_start,
            'end_frame': swing_end,
            'peak_frame': impact_frame,
            'quality': avg_quality,
            'score': score
        }
    
    def _find_swing_start(self, motion_array: np.ndarray, peak_idx: int, fps: float) -> int:
        """백스윙 시작점을 찾습니다."""
        # 피크 이전 1.5초 구간에서 검색
        search_start = max(0, peak_idx - int(fps * 1.5))
        
        # 낮은 움직임에서 증가하기 시작하는 지점 찾기
        baseline = np.mean(motion_array[search_start:search_start + int(fps * 0.5)])
        
        for i in range(peak_idx - 1, search_start, -1):
            if motion_array[i] <= baseline * 1.2:  # 베이스라인의 120% 이하
                return i
        
        return search_start
    
    def _find_swing_end(self, motion_array: np.ndarray, peak_idx: int, fps: float) -> int:
        """피니시 끝점을 찾습니다."""
        # 피크 이후 2초 구간에서 검색
        search_end = min(len(motion_array) - 1, peak_idx + int(fps * 2))
        
        # 움직임이 안정화되는 지점 찾기
        baseline = np.mean(motion_array[:int(fps * 0.5)]) if peak_idx > fps * 0.5 else np.min(motion_array)
        
        for i in range(peak_idx + int(fps * 0.5), search_end):  # 피크 후 0.5초부터 검색
            if motion_array[i] <= baseline * 1.5:  # 베이스라인의 150% 이하로 안정화
                return i
        
        return search_end
    
    def _create_full_swing(self, frames_data: List[Dict]) -> Dict:
        """전체 영상을 스윙으로 처리합니다."""
        total_frames = len(frames_data)
        
        # 너무 긴 영상은 중간 부분만 사용
        if total_frames > 300:  # 10초 이상이면
            start_frame = total_frames // 3
            end_frame = (total_frames * 2) // 3
        else:
            start_frame = 0
            end_frame = total_frames - 1
        
        avg_quality = np.mean([f['pose_quality'] for f in frames_data[start_frame:end_frame + 1]])
        
        swing = {
            'start_frame': start_frame,
            'end_frame': end_frame,
            'peak_frame': (start_frame + end_frame) // 2,
            'quality': avg_quality,
            'score': 0.5
        }
        
        # 키 이벤트 추가
        swing['key_events'] = self._detect_key_events(
            frames_data, start_frame, end_frame
        )
        
        return swing
    
    def _find_swing_candidates_like_highlight(self, smoothed_motion: List[float], total_body_motion: List[float], fps: float) -> List[Dict]:
        """하이라이트와 동일한 방식으로 스윙 후보들을 찾습니다."""
        # 피크 감지 (더 관대한 설정)
        motion_array = np.array(smoothed_motion)
        threshold = np.mean(motion_array) + np.std(motion_array) * 0.3  # 임계값 낮춤
        min_distance = int(fps * 0.8)  # 최소 간격
        
        peaks, _ = find_peaks(motion_array, height=threshold, distance=min_distance)
        
        candidates = []
        for peak_idx in peaks:
            start_frame, end_frame = self._find_swing_boundaries_like_highlight(
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
    
    def _find_swing_boundaries_like_highlight(self, peak_idx: int, wrist_motion: List[float], 
                                            total_body_motion: List[float], fps: float) -> tuple:
        """하이라이트와 동일한 방식으로 스윙의 시작과 끝 지점을 찾습니다."""
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
    
    def _select_best_sequence_swing(self, candidates: List[Dict], frames_data: List[Dict]) -> Dict:
        """시퀀스에 가장 적합한 스윙을 선택합니다. (품질 우선)"""
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
            
            # 시퀀스용 종합 점수 (품질을 더 중시)
            score = (
                avg_quality * 0.6 +  # 포즈 품질 (더 높은 비중)
                min(avg_motion / 0.1, 1.0) * 0.25 +  # 움직임 정도
                min(duration / (30 * 3), 1.0) * 0.15  # 적절한 길이
            )
            
            if score > best_score:
                best_score = score
                best_swing = {
                    'id': 0,
                    'start_frame': start_frame,
                    'end_frame': end_frame,
                    'peak_frame': candidate['peak_frame'],
                    'duration': duration,
                    'quality': avg_quality,
                    'score': score
                }
        
        return best_swing 