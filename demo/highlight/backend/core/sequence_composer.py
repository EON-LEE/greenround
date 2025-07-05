import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import logging
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from .pose.sequence_pose_analyzer import SequencePoseAnalyzer
from .utils import (
    update_task_status,
    get_file_path,
    upload_to_gcs_and_get_public_url,
    TEMP_DIR
)

logger = logging.getLogger(__name__)

class SequenceComposer:
    """스윙 시퀀스 합성 이미지 생성 엔진"""
    
    def __init__(self, pose_analyzer: SequencePoseAnalyzer):
        self.pose_analyzer = pose_analyzer
        
    def create_sequence_image(self, file_id: str, task_id: str):
        """
        스윙 시퀀스 이미지를 생성하고 GCS에 업로드합니다.
        1. 포즈 분석을 실행합니다.
        2. 주요 스윙 이벤트를 기반으로 프레임을 추출합니다.
        3. 시퀀스 이미지를 합성합니다.
        4. GCS에 업로드하고 URL을 반환합니다.
        """
        try:
            update_task_status(task_id, "processing", 0, "포즈 분석 시작")
            
            video_path = get_file_path(file_id, "uploads")
            if not video_path.exists():
                raise FileNotFoundError(f"업로드된 파일을 찾을 수 없습니다: {video_path}")

            analysis_result = self.pose_analyzer.analyze_for_sequence(video_path)
            
            update_task_status(task_id, "processing", 50, "주요 스윙 탐색")

            if not analysis_result.get('key_swing'):
                raise ValueError("분석된 스윙이 없습니다.")
            
            # 키 스윙을 사용
            swing_to_use = analysis_result['key_swing']
            
            update_task_status(task_id, "processing", 80, "시퀀스 이미지 생성")

            local_output_path = TEMP_DIR / f"{task_id}.png"
            # 균등 분할 방식으로 시퀀스 이미지 생성
            swing_range = (swing_to_use['start_frame'], swing_to_use['end_frame'])
            self._create_swing_sequence_image_equally_spaced(
                frames_data=analysis_result['frames_data'],
                swing_range=swing_range,
                output_path=local_output_path,
                num_frames=9
            )
            
            # GCS에 업로드하고 공개 URL 받기
            gcs_destination_path = f"sequences/{task_id}.png"
            public_url = upload_to_gcs_and_get_public_url(local_output_path, gcs_destination_path)
            
            update_task_status(task_id, "completed", 100, "스윙 시퀀스 생성 완료", result_data={"download_url": public_url})
            
        except Exception as e:
            logger.error(f"시퀀스 생성 중 오류: {e}", exc_info=True)
            update_task_status(task_id, "failed", 0, f"오류: {e}")

    def _create_swing_sequence_image(self, frames_data: List[Dict], key_events: Dict, output_path: Path):
        """키 이벤트를 기반으로 스윙 시퀀스 이미지를 생성합니다."""
        key_frames_indices = {
            "Address": key_events.get("address", -1),
            "Backswing Top": key_events.get("backswing_top", -1),
            "Impact": key_events.get("impact", -1),
            "Finish": key_events.get("finish", -1),
        }
        
        images_to_stitch = []
        labels = []
        
        for label, frame_idx in key_frames_indices.items():
            if frame_idx != -1 and frame_idx < len(frames_data):
                # SequencePoseAnalyzer는 'frame' 키를 사용
                frame_bgr = frames_data[frame_idx]['frame']
                images_to_stitch.append(frame_bgr)
                labels.append(label)

        if not images_to_stitch:
            raise ValueError("시퀀스를 생성할 키 프레임이 부족합니다.")

        # 이미지 스티칭
        stitched_image = self._stitch_images_with_labels(images_to_stitch, labels)
        
        # 결과 저장
        cv2.imwrite(str(output_path), stitched_image)
        logger.info(f"스윙 시퀀스 이미지를 임시 저장했습니다: {output_path}")

    def _create_swing_sequence_image_equally_spaced(self, frames_data: List[Dict], swing_range: tuple, output_path: Path, num_frames: int = 9):
        """스윙을 3분할(어드레스-탑-피니시)하고 A3개, T5개, F3개로 총 11개 프레임 시퀀스를 생성합니다."""
        start_frame, end_frame = swing_range
        
        if end_frame <= start_frame:
            raise ValueError("유효하지 않은 스윙 범위입니다.")
        
        # 키 이벤트 감지 (어드레스, 탑, 피니시)
        key_events = self._detect_swing_key_points(frames_data, start_frame, end_frame)
        
        # 3구간으로 분할: 어드레스→탑, 탑→임팩트, 임팩트→피니시
        address_frame = key_events['address']
        top_frame = key_events['top']
        impact_frame = key_events['impact']
        finish_frame = key_events['finish']
        
        # 각 구간을 3등분하여 프레임 선택 (구간 경계 중복 제거)
        frame_indices = []
        labels = []
        
        # 구간 1: 어드레스 → 탑 직전 (3프레임)
        # A3가 top_frame과 겹치지 않도록 top_frame-1을 끝점으로 사용
        for i in range(3):
            if i == 2:  # A3는 top_frame 직전
                frame_idx = top_frame - 1
            else:
                frame_idx = address_frame + int((top_frame - 1 - address_frame) * i / 2)
            frame_indices.append(frame_idx)
            labels.append(f"A{i+1}")  # A1, A2, A3
        
        # 구간 2: 탑 → 임팩트 직전 (5프레임, 속도 기반 분할)
        # T1은 top_frame부터, T5는 impact_frame 직전까지
        t_frames = self._get_dynamic_t_frames(frames_data, top_frame, impact_frame - 1)
        for i, frame_idx in enumerate(t_frames):
            frame_indices.append(frame_idx)
            labels.append(f"T{i+1}")  # T1, T2, T3, T4, T5
        
        # 구간 3: 임팩트 → 피니시 (3프레임)
        # F1은 impact_frame부터 시작
        for i in range(3):
            frame_idx = impact_frame + int((finish_frame - impact_frame) * i / 2)
            frame_indices.append(frame_idx)
            labels.append(f"F{i+1}")  # F1, F2, F3
        
        # 유사한 프레임 미세조정
        adjusted_frame_indices = self._adjust_similar_frames(frame_indices, frames_data, start_frame, end_frame)
        
        # 선택된 프레임들의 데이터 수집
        selected_frames = []
        for i, frame_idx in enumerate(adjusted_frame_indices):
            if frame_idx < len(frames_data):
                selected_frames.append({
                    'frame': frames_data[frame_idx]['frame'],
                    'landmarks': frames_data[frame_idx].get('landmarks', {}),
                    'label': labels[i]
                })
        
        if not selected_frames:
            raise ValueError("시퀀스를 생성할 프레임이 부족합니다.")

        # 모든 프레임의 랜드마크를 기반으로 통합 크롭 박스 계산
        all_landmarks = [frame_data['landmarks'] for frame_data in selected_frames if frame_data['landmarks']]
        crop_box = self._get_tight_crop_box(all_landmarks)  # 더 타이트한 크롭 함수 사용
        
        # 각 프레임을 동일한 크롭 박스로 크롭하고 리사이즈
        cropped_images = []
        final_labels = []
        
        target_height = 600
        target_width = int(target_height * 0.5625)  # 9:16 비율 (세로가 더 긴 자연스러운 비율)
        
        for frame_data in selected_frames:
            # 사람 중심으로 타이트하게 크롭
            cropped_img = self._crop_image(frame_data['frame'], crop_box)
            
            # 동일한 크기로 리사이즈
            resized_img = cv2.resize(cropped_img, (target_width, target_height))
            
            cropped_images.append(resized_img)
            final_labels.append(frame_data['label'])

        # 라벨과 함께 이미지 스티칭
        stitched_image = self._stitch_images_with_labels(cropped_images, final_labels)
        
        # 결과 저장
        cv2.imwrite(str(output_path), stitched_image)
        logger.info(f"3분할 스윙 시퀀스 이미지 (11프레임)를 저장했습니다: {output_path}")
    
    def _detect_swing_key_points(self, frames_data: List[Dict], start_frame: int, end_frame: int) -> Dict:
        """스윙의 핵심 포인트들을 감지합니다: 어드레스, 탑, 임팩트, 피니시"""
        swing_frames = frames_data[start_frame:end_frame + 1]
        
        # 디버깅: 랜드마크 구조 확인
        if swing_frames and swing_frames[0].get('landmarks'):
            sample_landmarks = swing_frames[0]['landmarks']
            logger.info(f"랜드마크 구조 확인: {list(sample_landmarks.keys()) if sample_landmarks else 'None'}")
            if 'left_wrist' in sample_landmarks:
                logger.info(f"left_wrist 타입: {type(sample_landmarks['left_wrist'])}, 값: {sample_landmarks['left_wrist']}")
        
        if len(swing_frames) < 4:
            # 너무 짧으면 균등 분할
            quarter = len(swing_frames) // 4
            return {
                'address': start_frame,
                'top': start_frame + quarter,
                'impact': start_frame + quarter * 2,
                'finish': start_frame + quarter * 3
            }
        
        # 움직임 데이터 추출
        motion_data = [f['total_motion'] for f in swing_frames]
        
        # 임팩트 찾기 (최대 움직임)
        impact_idx = np.argmax(motion_data)
        impact_frame = start_frame + impact_idx
        
        # 어드레스 찾기 (시작 부분의 낮은 움직임)
        address_frame = start_frame
        
        # 탑 찾기 (어드레스와 임팩트 사이의 특정 지점)
        # 손목 높이가 최고점에 도달하는 지점 찾기
        try:
            top_frame = self._find_backswing_top(swing_frames, start_frame, impact_frame)
        except Exception as e:
            logger.warning(f"백스윙 탑 감지 실패, 기본 분할 사용: {e}")
            # 기본값: 어드레스와 임팩트 사이의 1/3 지점
            top_frame = start_frame + (impact_frame - start_frame) // 3
        
        # 피니시 찾기 (임팩트 이후 움직임이 안정화되는 지점)
        finish_frame = min(end_frame, impact_frame + len(swing_frames) // 3)
        
        return {
            'address': address_frame,
            'top': top_frame,
            'impact': impact_frame,
            'finish': finish_frame
        }
    
    def _find_backswing_top(self, swing_frames: List[Dict], start_frame: int, impact_frame: int) -> int:
        """백스윙 탑 지점을 찾습니다."""
        # 어드레스와 임팩트 사이에서 손목이 가장 높은 지점 찾기
        max_wrist_height = -1
        top_frame = start_frame + (impact_frame - start_frame) // 3  # 기본값
        
        for i, frame_data in enumerate(swing_frames):
            frame_idx = start_frame + i
            if frame_idx >= impact_frame:
                break
                
            landmarks = frame_data.get('landmarks', {})
            try:
                # 손목 랜드마크 안전하게 접근
                left_wrist = landmarks.get('left_wrist')
                right_wrist = landmarks.get('right_wrist')
                
                if left_wrist and right_wrist:
                    # 랜드마크 데이터 구조에 따라 처리
                    if isinstance(left_wrist, dict) and isinstance(right_wrist, dict):
                        # dict 형태: {'point': (x, y, z), 'visibility': value}
                        left_point = left_wrist.get('point')
                        right_point = right_wrist.get('point')
                        if left_point and right_point and len(left_point) >= 2 and len(right_point) >= 2:
                            avg_wrist_y = (left_point[1] + right_point[1]) / 2
                    elif isinstance(left_wrist, (list, tuple)) and len(left_wrist) >= 2 and \
                         isinstance(right_wrist, (list, tuple)) and len(right_wrist) >= 2:
                        # 리스트/튜플 형태: (x, y, z)
                                                 avg_wrist_y = (left_wrist[1] + right_wrist[1]) / 2
                    else:
                        continue  # 지원하지 않는 데이터 형태
                    
                    if max_wrist_height == -1 or avg_wrist_y < max_wrist_height:
                        max_wrist_height = avg_wrist_y
                        top_frame = frame_idx
            except (KeyError, IndexError, TypeError) as e:
                # 랜드마크 접근 오류 시 무시하고 계속
                continue
        
        return top_frame
    
    def _get_dynamic_t_frames(self, frames_data: List[Dict], top_frame: int, impact_frame: int) -> List[int]:
        """백스윙 탑에서 임팩트까지 스윙 속도에 따라 동적으로 5개 프레임을 선택합니다."""
        if impact_frame <= top_frame:
            # 예외 상황: 단순 등분할
            return [top_frame + int((impact_frame - top_frame) * i / 4) for i in range(5)]
        
        # 탑-임팩트 구간의 움직임 데이터 수집
        t_section_frames = frames_data[top_frame:impact_frame + 1]
        motion_values = []
        
        for frame_data in t_section_frames:
            # 손목 움직임을 우선으로 하되, 전신 움직임도 고려
            wrist_motion = 0
            total_motion = frame_data.get('total_motion', 0)
            
            # 손목 속도가 있으면 우선 사용
            left_wrist_speed = frame_data.get('left_wrist_speed', 0)
            right_wrist_speed = frame_data.get('right_wrist_speed', 0)
            if left_wrist_speed > 0 or right_wrist_speed > 0:
                wrist_motion = (left_wrist_speed + right_wrist_speed) / 2
            
            # 손목 움직임(70%) + 전신 움직임(30%) 조합
            combined_motion = wrist_motion * 0.7 + total_motion * 0.3
            motion_values.append(combined_motion)
        
        # 누적 움직임으로 "움직임 거리" 계산
        cumulative_motion = np.cumsum(motion_values)
        total_motion_distance = cumulative_motion[-1] if len(cumulative_motion) > 0 else 1
        
        # 5개 구간으로 나누기 위한 타겟 지점들 (0%, 25%, 50%, 75%, 100%)
        target_ratios = [0.0, 0.25, 0.5, 0.75, 1.0]
        selected_frames = []
        
        for ratio in target_ratios:
            target_motion = total_motion_distance * ratio
            
            # 누적 움직임에서 타겟에 가장 가까운 프레임 찾기
            if ratio == 0.0:
                selected_idx = 0
            elif ratio == 1.0:
                selected_idx = len(cumulative_motion) - 1
            else:
                # 타겟 움직임량에 가장 가까운 인덱스 찾기
                selected_idx = np.argmin(np.abs(cumulative_motion - target_motion))
            
            actual_frame = top_frame + selected_idx
            selected_frames.append(actual_frame)
        
        # 중복 제거 및 정렬
        selected_frames = sorted(list(set(selected_frames)))
        
        # 정확히 5개가 되도록 조정
        while len(selected_frames) < 5:
            # 간격이 가장 큰 구간에 프레임 추가
            max_gap = 0
            insert_pos = 0
            for i in range(len(selected_frames) - 1):
                gap = selected_frames[i+1] - selected_frames[i]
                if gap > max_gap:
                    max_gap = gap
                    insert_pos = i + 1
            
            new_frame = (selected_frames[insert_pos-1] + selected_frames[insert_pos]) // 2
            selected_frames.insert(insert_pos, new_frame)
        
        # 5개 초과면 가장 중요한 5개만 선택
        if len(selected_frames) > 5:
            # 탑, 마지막 프레임은 반드시 포함하고 나머지 3개 선택
            last_frame = selected_frames[-1]  # impact_frame이 아니라 실제 마지막 프레임
            must_include = [top_frame, last_frame]
            candidates = [f for f in selected_frames if f not in must_include]
            
            # 움직임이 큰 순서로 3개 선택
            candidate_motions = []
            for frame_idx in candidates:
                if top_frame <= frame_idx <= impact_frame:
                    relative_idx = frame_idx - top_frame
                    if relative_idx < len(motion_values):
                        candidate_motions.append((motion_values[relative_idx], frame_idx))
            
            candidate_motions.sort(reverse=True)  # 움직임 큰 순
            selected_middle = [frame for _, frame in candidate_motions[:3]]
            
            selected_frames = sorted(must_include + selected_middle)
        
        logger.info(f"T 구간 동적 분할: {selected_frames} (탑: {top_frame}, 종료: {impact_frame})")
        return selected_frames[:5]  # 안전장치
    
    def _adjust_similar_frames(self, frame_indices: List[int], frames_data: List[Dict], 
                             start_frame: int, end_frame: int) -> List[int]:
        """유사한 프레임들을 미세조정하여 다양성을 확보합니다."""
        adjusted_indices = frame_indices.copy()
        similarity_threshold = 0.05  # 5% 미만 차이면 유사한 것으로 판단
        
        logger.info(f"원본 프레임 인덱스: {frame_indices}")
        
        # 구간 경계 정의 (A3-T5-F3 구조)
        section_boundaries = self._get_section_boundaries(adjusted_indices)
        
        # 연속된 프레임들 간의 유사도 체크 및 조정
        for i in range(len(adjusted_indices) - 1):
            current_frame = adjusted_indices[i]
            next_frame = adjusted_indices[i + 1]
            
            # 프레임 범위 체크
            if current_frame >= len(frames_data) or next_frame >= len(frames_data):
                continue
            
            # 구간 경계 프레임은 조정하지 않음
            if self._is_section_boundary_frame(i + 1, section_boundaries):
                continue
                
            # 포즈 유사도 계산
            similarity = self._calculate_pose_similarity(
                frames_data[current_frame], frames_data[next_frame]
            )
            
            # 너무 유사하면 조정
            if similarity > (1.0 - similarity_threshold):  # 95% 이상 유사
                # 구간별 제한 범위 내에서 조정
                adjustment_range = self._get_section_adjustment_range(i + 1, adjusted_indices, section_boundaries)
                adjustment = self._get_frame_adjustment(
                    i, adjusted_indices, start_frame, end_frame, frames_data
                )
                
                old_frame = adjusted_indices[i + 1]
                new_frame = old_frame + adjustment
                
                # 구간 경계를 넘지 않도록 제한
                new_frame = max(adjustment_range[0], min(adjustment_range[1], new_frame))
                
                if new_frame != old_frame:
                    adjusted_indices[i + 1] = new_frame
                    logger.info(f"유사도 {similarity:.3f} 감지: {old_frame} → {new_frame} (조정: {new_frame - old_frame}, 범위: {adjustment_range})")
        
        logger.info(f"조정된 프레임 인덱스: {adjusted_indices}")
        return adjusted_indices
    
    def _calculate_pose_similarity(self, frame1: Dict, frame2: Dict) -> float:
        """두 프레임 간의 포즈 유사도를 계산합니다 (0~1, 1이 완전히 같음)."""
        landmarks1 = frame1.get('landmarks', {})
        landmarks2 = frame2.get('landmarks', {})
        
        if not landmarks1 or not landmarks2:
            return 0.0
        
        # 공통 랜드마크만 비교
        common_joints = set(landmarks1.keys()) & set(landmarks2.keys())
        if not common_joints:
            return 0.0
        
        total_distance = 0.0
        joint_count = 0
        
        for joint in common_joints:
            lm1 = landmarks1[joint]
            lm2 = landmarks2[joint]
            
            # 랜드마크 데이터 구조에 따라 처리
            point1 = None
            point2 = None
            
            if isinstance(lm1, dict) and 'point' in lm1:
                point1 = lm1['point']
            elif isinstance(lm1, (list, tuple)):
                point1 = lm1
                
            if isinstance(lm2, dict) and 'point' in lm2:
                point2 = lm2['point']
            elif isinstance(lm2, (list, tuple)):
                point2 = lm2
            
            if point1 and point2 and len(point1) >= 2 and len(point2) >= 2:
                # 2D 거리 계산 (x, y 좌표만 사용)
                distance = np.linalg.norm([point1[0] - point2[0], point1[1] - point2[1]])
                total_distance += distance
                joint_count += 1
        
        if joint_count == 0:
            return 0.0
        
        # 평균 거리를 유사도로 변환 (거리가 클수록 유사도 낮음)
        avg_distance = total_distance / joint_count
        # 거리가 0.1 이상이면 유사도 0으로, 0이면 유사도 1로 스케일링
        similarity = max(0.0, 1.0 - (avg_distance / 0.1))
        
        return similarity
    
    def _get_frame_adjustment(self, position: int, frame_indices: List[int], 
                            start_frame: int, end_frame: int, frames_data: List[Dict]) -> int:
        """프레임 위치에 따른 조정 방향과 거리를 결정합니다."""
        total_frames = len(frame_indices)
        current_frame = frame_indices[position + 1]
        
        # 기본 조정 거리 (3-5 프레임)
        base_adjustment = 4
        
        # 위치별 조정 전략
        if position < 3:  # A 구간 (0, 1, 2)
            # A2, A3는 뒤로 밀어서 백스윙 쪽으로
            return base_adjustment
        elif position < 8:  # T 구간 (3, 4, 5, 6, 7)
            # T 구간은 상황에 따라 조정
            if position < 6:  # T1-T3는 뒤로
                return base_adjustment
            else:  # T4-T5는 앞으로 (임팩트 쪽)
                return -base_adjustment // 2
        else:  # F 구간 (8, 9, 10)
            # F 구간은 뒤로 밀어서 피니시 완성 쪽으로
            return base_adjustment
        
        return base_adjustment
    
    def _get_section_boundaries(self, frame_indices: List[int]) -> Dict:
        """구간 경계 프레임 인덱스를 반환합니다 (A3-T5-F3 구조)."""
        return {
            'a_start': 0,     # A1 (첫 번째)
            'a_end': 2,       # A3 (A구간 마지막)
            't_start': 3,     # T1 (T구간 첫 번째)
            't_end': 7,       # T5 (T구간 마지막)
            'f_start': 8,     # F1 (F구간 첫 번째)
            'f_end': 10       # F3 (마지막)
        }
    
    def _is_section_boundary_frame(self, position: int, boundaries: Dict) -> bool:
        """해당 위치가 구간 경계 프레임인지 확인합니다."""
        boundary_positions = [
            boundaries['a_start'],  # A1
            boundaries['a_end'],    # A3
            boundaries['t_start'],  # T1
            boundaries['t_end'],    # T5
            boundaries['f_start'],  # F1
            boundaries['f_end']     # F3
        ]
        return position in boundary_positions
    
    def _get_section_adjustment_range(self, position: int, frame_indices: List[int], 
                                    boundaries: Dict) -> tuple:
        """해당 위치 프레임의 조정 가능 범위를 반환합니다."""
        current_frame = frame_indices[position]
        
        # A구간 중간 프레임들 (A2)
        if boundaries['a_start'] < position < boundaries['a_end']:
            min_frame = frame_indices[boundaries['a_start']] + 1
            max_frame = frame_indices[boundaries['a_end']] - 1
            
        # T구간 중간 프레임들 (T2, T3, T4)
        elif boundaries['t_start'] < position < boundaries['t_end']:
            min_frame = frame_indices[boundaries['t_start']] + 1
            max_frame = frame_indices[boundaries['t_end']] - 1
            
        # F구간 중간 프레임들 (F2)
        elif boundaries['f_start'] < position < boundaries['f_end']:
            min_frame = frame_indices[boundaries['f_start']] + 1
            max_frame = frame_indices[boundaries['f_end']] - 1
            
        else:
            # 경계 프레임이거나 예외 상황
            min_frame = current_frame
            max_frame = current_frame
        
        return (min_frame, max_frame)

    def _stitch_images_with_labels(self, images: List[np.ndarray], labels: List[str]) -> np.ndarray:
        """이미지 리스트를 받아 라벨과 함께 수평으로 연결합니다."""
        if not images:
            return np.array([])

        target_height = 480
        processed_images = []

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        font_color = (255, 255, 255)
        text_bg_color = (0, 0, 0)
        line_type = 2
        
        for img, label in zip(images, labels):
            h, w, _ = img.shape
            scale = target_height / h
            new_w, new_h = int(w * scale), target_height
            resized_img = cv2.resize(img, (new_w, new_h))

            # 라벨 텍스트 크기 계산 및 배경 추가
            text_size, _ = cv2.getTextSize(label, font, font_scale, line_type)
            text_w, text_h = text_size
            
            # 라벨 위치 (상단 중앙)
            text_x = (new_w - text_w) // 2
            text_y = text_h + 10
            
            # 텍스트 배경 그리기
            cv2.rectangle(resized_img, (text_x - 5, text_y - text_h - 5), (text_x + text_w + 5, text_y + 5), text_bg_color, -1)
            # 텍스트 그리기
            cv2.putText(resized_img, label, (text_x, text_y), font, font_scale, font_color, line_type)

            processed_images.append(resized_img)

        return cv2.hconcat(processed_images)

    def _extract_key_frames(self, analysis_result: Dict) -> Dict[str, Dict]:
        """
        분석 결과에서 키프레임 인덱스를 사용하여 실제 프레임 데이터를 추출합니다.
        """
        key_frames_indices = analysis_result.get('key_frames', {})
        frames_data = analysis_result.get('frames_data', [])
        
        if not key_frames_indices:
            raise ValueError("키프레임 정보가 분석 결과에 없습니다.")
        if not frames_data:
            raise ValueError("프레임 데이터가 분석 결과에 없습니다.")
        
        key_frames_data = {}
        for name, frame_idx in key_frames_indices.items():
            if 0 <= frame_idx < len(frames_data):
                # 'frame' 키 존재 여부 확인
                if 'frame' not in frames_data[frame_idx]:
                    raise KeyError(f"'frame' 키를 프레임 데이터(인덱스 {frame_idx})에서 찾을 수 없습니다.")
                key_frames_data[name] = frames_data[frame_idx]
            else:
                logger.warning(f"잘못된 키프레임 인덱스({frame_idx})는 건너뜁니다.")
        
        return key_frames_data
    
    def _compose_sequence_image(self, key_frames_data: Dict[str, Dict], 
                              output_path: Path, task_id: str):
        """
        추출된 키프레임 데이터로 시퀀스 이미지를 합성하고 저장합니다.
        """
        update_task_status(task_id, "processing", 60, "선수 영역 크롭")

        # 이름 순으로 정렬하여 P01, P02... 순서 보장
        sorted_frames = sorted(key_frames_data.items())
        images = [frame_data['frame'] for name, frame_data in sorted_frames]
        
        if not images:
            raise ValueError("합성할 이미지가 없습니다.")
        
        # 모든 키프레임을 포함하는 크롭 박스 계산
        all_landmarks = [frame_data['landmarks'] for name, frame_data in sorted_frames]
        crop_box = self._get_dynamic_crop_box(all_landmarks)
        
        update_task_status(task_id, "processing", 80, "이미지 수평 합성")
        
        cropped_images = [self._crop_image(img, crop_box) for img in images]
        sequence_image = self._hconcat_images(cropped_images)
        
        cv2.imwrite(str(output_path), sequence_image)
        logger.info(f"Sequence image saved to {output_path}")

    def _get_dynamic_crop_box(self, all_landmarks: List[Dict]) -> tuple:
        """
        주어진 모든 랜드마크를 포함하는 동적 크롭 박스를 계산합니다.
        사람을 중심으로 하고 충분한 여백을 확보합니다.
        """
        if not all_landmarks:
            return 0, 0, 1, 1
            
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        # 모든 랜드마크의 경계 계산
        for landmarks in all_landmarks:
            if not landmarks: 
                continue
            for lm in landmarks.values():
                # 랜드마크 데이터 구조에 따라 처리
                if isinstance(lm, dict) and 'point' in lm:
                    # dict 형태: {'point': (x, y, z), 'visibility': value}
                    point = lm['point']
                    if point and len(point) >= 2:
                        min_x = min(min_x, point[0])
                        max_x = max(max_x, point[0])
                        min_y = min(min_y, point[1])
                        max_y = max(max_y, point[1])
                elif isinstance(lm, (list, tuple)) and len(lm) >= 2:
                    # 리스트/튜플 형태: (x, y, z)
                    min_x = min(min_x, lm[0])
                    max_x = max(max_x, lm[0])
                    min_y = min(min_y, lm[1])
                    max_y = max(max_y, lm[1])

        if any(v == float('inf') or v == float('-inf') for v in [min_x, max_x, min_y, max_y]):
            return 0, 0, 1, 1

        # 사람의 폭과 높이 계산
        person_width = max_x - min_x
        person_height = max_y - min_y
        person_center_x = (min_x + max_x) / 2
        person_center_y = (min_y + max_y) / 2
        
        # 사람을 크게 보이도록 최소 여백만 추가 (15% 여백)
        padding_x = person_width * 0.15
        padding_y = person_height * 0.15
        
        # 크롭 박스 크기 결정 (사람 크기 + 여백)
        crop_width = person_width + 2 * padding_x
        crop_height = person_height + 2 * padding_y
        
        # 종횡비 조정 (세로가 더 길게 - 골프 스윙에 적합)
        aspect_ratio = 3.0 / 4.0  # 가로:세로 = 3:4
        
        if crop_width / crop_height > aspect_ratio:
            # 너무 넓으면 높이를 늘림
            crop_height = crop_width / aspect_ratio
        else:
            # 너무 높으면 폭을 늘림
            crop_width = crop_height * aspect_ratio
        
        # 크롭 박스 중심을 사람 중심에 맞춤
        box_x = person_center_x - crop_width / 2
        box_y = person_center_y - crop_height / 2
        
        # 이미지 경계 내로 조정
        if box_x < 0:
            box_x = 0
        elif box_x + crop_width > 1.0:
            box_x = 1.0 - crop_width
            
        if box_y < 0:
            box_y = 0
        elif box_y + crop_height > 1.0:
            box_y = 1.0 - crop_height
        
        # 크기가 이미지를 초과하면 조정
        box_w = min(crop_width, 1.0)
        box_h = min(crop_height, 1.0)
        
        # 최소 크기 보장 (전체 이미지의 40% 이상으로 증가)
        min_size = 0.4
        if box_w < min_size:
            box_w = min_size
            box_x = max(0, person_center_x - box_w / 2)
            box_x = min(box_x, 1.0 - box_w)
            
        if box_h < min_size:
            box_h = min_size
            box_y = max(0, person_center_y - box_h / 2)
            box_y = min(box_y, 1.0 - box_h)

        return box_x, box_y, box_w, box_h
    
    def _get_tight_crop_box(self, all_landmarks: List[Dict]) -> tuple:
        """
        사람을 더 크게 보이도록 매우 타이트한 크롭 박스를 계산합니다.
        """
        if not all_landmarks:
            return 0, 0, 1, 1
            
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        # 모든 랜드마크의 경계 계산
        for landmarks in all_landmarks:
            if not landmarks: 
                continue
            for lm in landmarks.values():
                # 랜드마크 데이터 구조에 따라 처리
                if isinstance(lm, dict) and 'point' in lm:
                    # dict 형태: {'point': (x, y, z), 'visibility': value}
                    point = lm['point']
                    if point and len(point) >= 2:
                        min_x = min(min_x, point[0])
                        max_x = max(max_x, point[0])
                        min_y = min(min_y, point[1])
                        max_y = max(max_y, point[1])
                elif isinstance(lm, (list, tuple)) and len(lm) >= 2:
                    # 리스트/튜플 형태: (x, y, z)
                    min_x = min(min_x, lm[0])
                    max_x = max(max_x, lm[0])
                    min_y = min(min_y, lm[1])
                    max_y = max(max_y, lm[1])

        if any(v == float('inf') or v == float('-inf') for v in [min_x, max_x, min_y, max_y]):
            return 0, 0, 1, 1

        # 사람의 폭과 높이 계산
        person_width = max_x - min_x
        person_height = max_y - min_y
        person_center_x = (min_x + max_x) / 2
        person_center_y = (min_y + max_y) / 2
        
        # 매우 최소한의 여백만 추가 (5% 여백)
        padding_x = person_width * 0.05
        padding_y = person_height * 0.05
        
        # 크롭 박스 크기 결정 (사람 크기 + 최소 여백)
        crop_width = person_width + 2 * padding_x
        crop_height = person_height + 2 * padding_y
        
        # 종횡비 조정 (골프 스윙에 최적화된 비율)
        aspect_ratio = 2.5 / 4.0  # 가로:세로 = 2.5:4 (더 세로로 긴 비율)
        
        if crop_width / crop_height > aspect_ratio:
            # 너무 넓으면 높이를 늘림
            crop_height = crop_width / aspect_ratio
        else:
            # 너무 높으면 폭을 늘림  
            crop_width = crop_height * aspect_ratio
        
        # 크롭 박스 중심을 사람 중심에 맞춤
        box_x = person_center_x - crop_width / 2
        box_y = person_center_y - crop_height / 2
        
        # 이미지 경계 내로 조정
        if box_x < 0:
            box_x = 0
        elif box_x + crop_width > 1.0:
            box_x = 1.0 - crop_width
            
        if box_y < 0:
            box_y = 0
        elif box_y + crop_height > 1.0:
            box_y = 1.0 - crop_height
        
        # 크기가 이미지를 초과하면 조정
        box_w = min(crop_width, 1.0)
        box_h = min(crop_height, 1.0)
        
        # 최소 크기 보장 (전체 이미지의 50% 이상으로 더 크게)
        min_size = 0.5
        if box_w < min_size:
            box_w = min_size
            box_x = max(0, person_center_x - box_w / 2)
            box_x = min(box_x, 1.0 - box_w)
            
        if box_h < min_size:
            box_h = min_size
            box_y = max(0, person_center_y - box_h / 2)
            box_y = min(box_y, 1.0 - box_h)

        return box_x, box_y, box_w, box_h

    def _crop_image(self, image: np.ndarray, crop_box: tuple) -> np.ndarray:
        """주어진 비율의 크롭 박스로 이미지를 자릅니다."""
        h, w, _ = image.shape
        x_norm, y_norm, w_norm, h_norm = crop_box
        x, y = int(x_norm * w), int(y_norm * h)
        width, height = int(w_norm * w), int(h_norm * h)
        return image[y:y+height, x:x+width]

    def _hconcat_images(self, images: List[np.ndarray]) -> np.ndarray:
        """
        높이가 다른 이미지들을 가장 작은 높이에 맞춰 리사이즈한 후 수평으로 연결합니다.
        """
        if not images:
            raise ValueError("합성할 이미지가 없습니다.")
            
        min_height = min(img.shape[0] for img in images)
        resized_images = []
        for img in images:
            if img.shape[0] == min_height:
                resized_images.append(img)
            else:
                ratio = min_height / img.shape[0]
                new_width = int(img.shape[1] * ratio)
                resized = cv2.resize(img, (new_width, min_height), interpolation=cv2.INTER_AREA)
                resized_images.append(resized)
            
        return cv2.hconcat(resized_images)
    
    def _remove_background_simple(self, image: Image.Image) -> Image.Image:
        """간단한 배경 제거 (에지 기반)"""
        try:
            # RGBA 모드로 변환
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # 에지 검출을 위해 그레이스케일로 변환
            gray = image.convert('L')
            
            # 에지 검출
            edges = gray.filter(ImageFilter.FIND_EDGES)
            
            # 에지를 기반으로 마스크 생성 (간단한 방법)
            # 실제로는 더 정교한 세그멘테이션이 필요하지만, 여기서는 기본적인 처리만
            
            return image
            
        except Exception as e:
            logger.error(f"Error removing background: {str(e)}")
            return image
    
    def _place_person_image(self, canvas: Image.Image, person_image: Image.Image, 
                          x_pos: int, y_pos: int, index: int, total_count: int):
        """사람 이미지를 캔버스에 배치"""
        try:
            # 이미지 크기 확인
            person_width, person_height = person_image.size
            canvas_width, canvas_height = canvas.size
            
            # Y 위치 중앙 정렬
            y_centered = (canvas_height - person_height) // 2
            
            # 겹침 영역에 그라데이션 마스크 적용
            if index > 0:  # 첫 번째가 아닌 경우
                person_image = self._apply_fade_mask(person_image, 'left')
            
            if index < total_count - 1:  # 마지막이 아닌 경우
                person_image = self._apply_fade_mask(person_image, 'right')
            
            # 이미지 붙여넣기
            if person_image.mode == 'RGBA':
                canvas.paste(person_image, (x_pos, y_centered), person_image)
            else:
                canvas.paste(person_image, (x_pos, y_centered))
                
        except Exception as e:
            logger.error(f"Error placing person image: {str(e)}")
    
    def _apply_fade_mask(self, image: Image.Image, direction: str) -> Image.Image:
        """이미지에 페이드 마스크 적용"""
        try:
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            width, height = image.size
            fade_width = int(width * 0.1)  # 10% 영역에 페이드 적용
            
            # 알파 채널 생성
            alpha = Image.new('L', (width, height), 255)
            
            if direction == 'left':
                # 왼쪽 페이드
                for x in range(fade_width):
                    alpha_value = int(255 * (x / fade_width))
                    for y in range(height):
                        alpha.putpixel((x, y), alpha_value)
            elif direction == 'right':
                # 오른쪽 페이드
                for x in range(width - fade_width, width):
                    alpha_value = int(255 * ((width - x) / fade_width))
                    for y in range(height):
                        alpha.putpixel((x, y), alpha_value)
            
            # 기존 알파 채널과 합성
            if image.mode == 'RGBA':
                existing_alpha = image.split()[3]
                combined_alpha = Image.blend(existing_alpha, alpha, 0.5)
                image.putalpha(combined_alpha)
            else:
                image.putalpha(alpha)
            
            return image
            
        except Exception as e:
            logger.error(f"Error applying fade mask: {str(e)}")
            return image
    
    def _add_horizontal_stage_labels(self, image: Image.Image, stages: List[str]) -> Image.Image:
        """수평 배치용 스테이지 레이블 추가"""
        try:
            draw = ImageDraw.Draw(image)
            
            # 기본 폰트 사용
            try:
                font = ImageFont.truetype("arial.ttf", 32)
            except:
                font = ImageFont.load_default()
            
            width, height = image.size
            
            # 스테이지 레이블 매핑
            stage_labels = {
                'address': 'Address',
                'takeaway': 'Takeaway', 
                'backswing': 'Backswing',
                'top': 'Top',
                'downswing': 'Downswing',
                'impact': 'Impact',
                'follow_through': 'Follow Through'
            }
            
            # 색상 정의
            colors = [(255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), 
                     (0, 255, 255), (0, 0, 255), (127, 0, 255)]
            
            # 겹침을 고려한 X 위치 계산
            overlap_ratio = 0.15
            individual_width = int(width / (len(stages) - (len(stages) - 1) * overlap_ratio))
            
            # 각 스테이지별 레이블 배치
            for i, stage in enumerate(stages):
                if stage in stage_labels:
                    label = stage_labels[stage]
                    color = colors[i % len(colors)]
                    
                    # X 위치 (각 이미지의 중앙)
                    x_pos = int(i * individual_width * (1 - overlap_ratio) + individual_width // 2)
                    
                    # Y 위치 (하단에서 80px 위)
                    label_y = height - 80
                    
                    # 텍스트 크기 측정
                    bbox = draw.textbbox((0, 0), label, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    # 중앙 정렬을 위한 X 조정
                    centered_x = x_pos - text_width // 2
                    
                    # 텍스트 배경 (반투명 검은색)
                    padding = 8
                    bg_bbox = [
                        centered_x - padding,
                        label_y - padding,
                        centered_x + text_width + padding,
                        label_y + text_height + padding
                    ]
                    draw.rectangle(bg_bbox, fill=(0, 0, 0, 180))
                    
                    # 텍스트 그리기
                    draw.text((centered_x, label_y), label, font=font, fill=color)
                    
                    # 단계 번호 추가 (상단)
                    number_y = 20
                    number_text = f"{i+1}"
                    number_bbox = draw.textbbox((0, 0), number_text, font=font)
                    number_width = number_bbox[2] - number_bbox[0]
                    number_x = x_pos - number_width // 2
                    
                    # 번호 배경
                    circle_radius = 25
                    draw.ellipse([
                        number_x - circle_radius,
                        number_y - circle_radius,
                        number_x + circle_radius,
                        number_y + circle_radius
                    ], fill=color, outline=(255, 255, 255), width=3)
                    
                    # 번호 텍스트
                    draw.text((number_x - number_width // 2, number_y - 15), 
                             number_text, font=font, fill=(255, 255, 255))
            
            return image
            
        except Exception as e:
            logger.error(f"Error adding horizontal stage labels: {str(e)}")
            return image
    
    def _add_stage_labels(self, image: Image.Image, stages: List[str]) -> Image.Image:
        """기존 스테이지 레이블 추가 (호환성 유지)"""
        return self._add_horizontal_stage_labels(image, stages)
    
    def _create_gradient_overlay(self, width: int, height: int, 
                               start_color: Tuple[int, int, int],
                               end_color: Tuple[int, int, int]) -> Image.Image:
        """그라데이션 오버레이 생성"""
        try:
            gradient = Image.new('RGB', (width, height))
            draw = ImageDraw.Draw(gradient)
            
            # 수직 그라데이션
            for y in range(height):
                ratio = y / height
                r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
                g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
                b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
                
                draw.line([(0, y), (width, y)], fill=(r, g, b))
            
            return gradient
            
        except Exception as e:
            logger.error(f"Error creating gradient: {str(e)}")
            return Image.new('RGB', (width, height), (255, 255, 255)) 