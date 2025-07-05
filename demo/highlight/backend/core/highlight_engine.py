import cv2
import numpy as np
import logging
from typing import Dict, List, Tuple, Callable, Optional
from pathlib import Path
from .pose.highlight_pose_analyzer import HighlightPoseAnalyzer
from .utils import update_task_status, get_file_path, upload_to_gcs_and_get_public_url, TEMP_DIR

logger = logging.getLogger(__name__)

class HighlightEngine:
    """하이라이트 영상 생성 전용 엔진"""
    def __init__(self):
        self.highlight_analyzer = HighlightPoseAnalyzer()
        self.supported_codecs = ['mp4v', 'H264', 'XVID']
    
    def create_highlight_video(self, file_id: str, task_id: str, total_duration: int = 15, slow_factor: int = 16):
        """하이라이트 영상 생성 (최적 스윙 선택)"""
        try:
            video_path = get_file_path(file_id, "uploads")
            if not video_path.exists():
                raise FileNotFoundError(f"업로드된 파일을 찾을 수 없습니다: {video_path}")

            update_task_status(task_id, "processing", 0, "하이라이트용 자세 분석 시작")
            
            # 하이라이트 전용 분석 수행
            analysis_result = self.highlight_analyzer.analyze_for_highlight(
                video_path=str(video_path),
                progress_callback=lambda p: update_task_status(task_id, "processing", int(p * 0.3), "포즈 분석 진행 중")
            )
            
            update_task_status(task_id, "processing", 30, "스윙 구간 탐색")
            best_swing = analysis_result.get('best_swing')
            
            # 로컬 임시 파일 경로 설정
            local_output_path = TEMP_DIR / f"{task_id}.mp4"
            
            if best_swing:
                # 3단계 하이라이트 생성
                self._generate_3stage_highlight(
                    video_path=video_path,
                    swing_range=(best_swing['start_frame'], best_swing['end_frame']),
                    video_info=analysis_result['video_info'],
                    output_path=local_output_path,
                    slow_factor=slow_factor,
                    task_id=task_id
                )
            else:
                raise ValueError("스윙을 감지할 수 없습니다.")
            
            # GCS에 업로드하고 공개 URL 받기
            gcs_destination_path = f"highlights/{task_id}.mp4"
            public_url = upload_to_gcs_and_get_public_url(local_output_path, gcs_destination_path)
            
            update_task_status(task_id, "completed", 100, "하이라이트 생성 완료", result_data={"download_url": public_url})
            
        except Exception as e:
            logger.error(f"하이라이트 영상 생성 중 오류 발생: {e}", exc_info=True)
            update_task_status(task_id, "failed", 0, f"오류: {e}")
    


    def _generate_3stage_highlight(self, video_path: Path, swing_range: tuple, video_info: dict, output_path: Path, slow_factor: int, task_id: str):
        """요청하신 3개의 클립(원본, 조합, 초슬로우)을 생성하고 합성합니다."""
        start_frame, end_frame = swing_range
        fps = video_info['fps']

        cap = cv2.VideoCapture(str(video_path))
        writer = self._get_video_writer(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (video_info['width'], video_info['height']))

        try:
            # 1. 모든 프레임 로드
            update_task_status(task_id, "processing", 20, "프레임 데이터 로딩")
            all_frames = [frame for ret, frame in iter(lambda: cap.read(), (False, None))]

            # 2. 3개의 클립 생성
            update_task_status(task_id, "processing", 40, "3단계 하이라이트 클립 생성")
            swing_frames = all_frames[start_frame : end_frame + 1]
            if not swing_frames: raise ValueError("스윙 프레임 추출 실패")

            # 클립 1: 원본 전체
            clip1 = all_frames

            # 클립 2: 조합 (컨텍스트 + 일반 슬로우)
            context_frames = int(fps * 1.5)
            pre_swing = all_frames[max(0, start_frame - context_frames) : start_frame]
            normal_slow_swing = self._interpolate_frames(swing_frames, max(1, slow_factor // 2))
            post_swing = all_frames[end_frame + 1 : min(len(all_frames), end_frame + 1 + context_frames)]
            clip2 = pre_swing + normal_slow_swing + post_swing

            # 클립 3: 초슬로우
            clip3 = self._interpolate_frames(swing_frames, slow_factor)

            # 3. 클립 합성 및 전환 효과 적용
            update_task_status(task_id, "processing", 70, "영상 합성 및 전환 효과 적용")
            clips_to_write = [c for c in [clip1, clip2, clip3] if c]
            transition_frames = int(fps * 0.5)

            for i, current_clip in enumerate(clips_to_write):
                if i == 0:
                    for frame in current_clip[:-transition_frames]: writer.write(frame)
                else:
                    prev_clip = clips_to_write[i-1]
                    if len(prev_clip) >= transition_frames and len(current_clip) >= transition_frames:
                        self._write_crossfade_transition(writer, prev_clip, current_clip, transition_frames)
                    for frame in current_clip[transition_frames:-transition_frames]: writer.write(frame)
            
            if clips_to_write:
                last_clip = clips_to_write[-1]
                for frame in last_clip[-transition_frames:]: writer.write(frame)
        finally:
            writer.release()
            cap.release()
        logger.info(f"3단계 하이라이트 영상 (전환 효과 포함) 저장 완료: {output_path}")

    def _generate_highlight_clip(self, video_path: Path, swing_range: tuple, video_info: dict, output_path: Path, slow_factor: int, task_id: str):
        """[컨텍스트 + 슬로우 스윙 + 컨텍스트] 조합 클립을 생성합니다. (스윙 감지 실패 시 사용)"""
        start_frame, end_frame = swing_range
        fps = video_info['fps']

        cap = cv2.VideoCapture(str(video_path))
        writer = self._get_video_writer(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (video_info['width'], video_info['height']))

        try:
            # 1. 비디오에서 모든 프레임 로드
            update_task_status(task_id, "processing", 40, "프레임 데이터 로딩")
            all_frames = [frame for ret, frame in iter(lambda: cap.read(), (False, None))]

            # 2. 조합 클립 생성
            update_task_status(task_id, "processing", 60, "클립 생성")
            clip_frames = all_frames[start_frame : end_frame + 1]
            if not clip_frames: raise ValueError("클립 프레임 추출 실패")
            
            # 스윙이 없으면 slow_factor=1 이므로 보간 안함
            final_clip = self._interpolate_frames(clip_frames, slow_factor)

            # 3. 생성된 클립을 영상에 쓰기
            update_task_status(task_id, "processing", 80, "최종 영상 합성")
            for frame in final_clip:
                writer.write(frame)
        finally:
            writer.release()
            cap.release()
        logger.info(f"단일 하이라이트 영상 저장 완료: {output_path}")
    
    def _write_crossfade_transition(self, writer, clip_from: list, clip_to: list, duration_frames: int):
        """두 클립 사이에 크로스페이드 전환 효과를 적용하여 씁니다."""
        for i in range(duration_frames):
            alpha = (i + 1) / (duration_frames + 1)
            from_frame = clip_from[len(clip_from) - duration_frames + i]
            to_frame = clip_to[i]
            if from_frame.shape != to_frame.shape:
                to_frame = cv2.resize(to_frame, (from_frame.shape[1], from_frame.shape[0]))
            blended_frame = cv2.addWeighted(from_frame, 1 - alpha, to_frame, alpha, 0)
            writer.write(blended_frame)

    def _interpolate_frames(self, frames: list, factor: int) -> list:
        """프레임 보간으로 부드러운 슬로우모션 생성"""
        if not frames or factor <= 1:
            return frames
            
        interpolated_frames = []
        for i in range(len(frames) - 1):
            interpolated_frames.append(frames[i])
            for j in range(1, factor):
                alpha = j / factor
                blended_frame = cv2.addWeighted(frames[i], 1 - alpha, frames[i+1], alpha, 0)
                interpolated_frames.append(blended_frame)
        
        interpolated_frames.append(frames[-1])
        return interpolated_frames


    def get_available_models(self):
        """현재 사용 중인 모델 정보를 반환합니다."""
        return {"pose_model": "MediaPipe Pose"}
        
    def health_check(self):
        """서비스 상태 확인용"""
        try:
            # PoseAnalyzer의 모델이 로드되었는지 확인
            if self.highlight_analyzer.pose is None:
                raise RuntimeError("Pose model is not loaded.")
            return {"status": "ok", "services": {"highlight_analyzer": "ok"}}
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "error", "reason": str(e)}

    def _get_video_writer(self, output_path: Path, fourcc: int, fps: float, frame_size: tuple) -> cv2.VideoWriter:
        """VideoWriter 객체를 생성하여 반환합니다."""
        # 파일이 아닌 경로(Path) 객체를 문자열로 변환하여 전달해야 합니다.
        return cv2.VideoWriter(str(output_path), fourcc, fps, frame_size)