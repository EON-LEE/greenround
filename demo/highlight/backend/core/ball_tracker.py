import cv2
import numpy as np
from typing import Dict, Optional, Tuple, List
from pathlib import Path
import logging
from .pose.ball_pose_analyzer import BallPoseAnalyzer

logger = logging.getLogger(__name__)

class BallTracker:
    """
    클래식 컴퓨터 비전 기술(OpenCV)만을 사용하여 골프공을 탐지하고 추적합니다.
    볼 트래킹 전용 포즈 분석기와 연동하여 작동합니다.
    """
    def __init__(self, video_path: str, pose_analyzer: Optional[BallPoseAnalyzer] = None):
        self.video_path = video_path
        self.video_capture = cv2.VideoCapture(video_path)
        if not self.video_capture.isOpened():
            raise ValueError(f"비디오 파일을 열 수 없습니다: {video_path}")
        self.video_width = int(self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        
        # 포즈 분석기 초기화
        self.pose_analyzer = pose_analyzer or BallPoseAnalyzer()
        self.analysis_result = None

    def __del__(self):
        if self.video_capture.isOpened():
            self.video_capture.release()
    
    def analyze_video(self) -> Dict:
        """
        비디오를 분석하여 임팩트와 어드레스 지점을 찾습니다.
        포즈 분석기를 사용하여 정확한 타이밍을 감지합니다.
        """
        if self.analysis_result is None:
            logger.info("포즈 분석 시작...")
            self.analysis_result = self.pose_analyzer.analyze_for_ball_tracking(Path(self.video_path))
        
        return self.analysis_result

    def find_stationary_ball(self, address_frame_idx: Optional[int] = None, check_frames: int = 5) -> Optional[Tuple[int, int, int, int]]:
        """
        어드레스 시점 근처에서 '정지된' 공을 찾습니다.

        Args:
            address_frame_idx: 어드레스 자세의 프레임 인덱스 (None이면 자동 탐지)
            check_frames: 위치 고정을 확인할 프레임 수

        Returns:
            안정적으로 탐지된 공의 Bounding Box (x, y, w, h). 없으면 None.
        """
        # 분석 결과가 없으면 먼저 분석 수행
        if self.analysis_result is None:
            self.analyze_video()
        
        # 어드레스 프레임이 지정되지 않았으면 분석 결과에서 가져오기
        if address_frame_idx is None:
            address_frame_idx = self.analysis_result['address_frame']
        
        landmarks = self.analysis_result['frames_data'][address_frame_idx].get('landmarks')
        if not landmarks:
            logger.warning("어드레스 프레임에서 랜드마크를 찾을 수 없어 ROI를 설정할 수 없습니다.")
            return None

        # 1. 지능형 ROI 설정 (발목 기준)
        left_ankle = landmarks.get('left_ankle')
        right_ankle = landmarks.get('right_ankle')
        if not left_ankle or not right_ankle:
            logger.warning("발목 랜드마크를 찾을 수 없습니다.")
            return None

        # 랜드마크 데이터 구조에 따라 좌표 추출
        left_ankle_point = None
        right_ankle_point = None
        
        if isinstance(left_ankle, dict) and 'point' in left_ankle:
            left_ankle_point = left_ankle['point']
        elif isinstance(left_ankle, (list, tuple)) and len(left_ankle) >= 2:
            left_ankle_point = left_ankle
            
        if isinstance(right_ankle, dict) and 'point' in right_ankle:
            right_ankle_point = right_ankle['point']
        elif isinstance(right_ankle, (list, tuple)) and len(right_ankle) >= 2:
            right_ankle_point = right_ankle
        
        if not left_ankle_point or not right_ankle_point:
            logger.warning("발목 랜드마크 좌표를 추출할 수 없습니다.")
            return None

        # ROI를 더 넓게 설정 (발목 중심에서 좌우로 확장)
        ankle_center_x = (left_ankle_point[0] + right_ankle_point[0]) / 2
        ankle_center_y = max(left_ankle_point[1], right_ankle_point[1])
        
        # 발목 중심에서 좌우로 넓게 확장 (골프공이 발 앞에 있을 수 있음)
        roi_width = int(self.video_width * 0.3)  # 화면 너비의 30%
        roi_height = int(self.video_height * 0.2)  # 화면 높이의 20%
        
        roi_x_start = max(0, int(ankle_center_x * self.video_width) - roi_width // 2)
        roi_x_end = min(self.video_width, roi_x_start + roi_width)
        roi_y_start = max(0, int(ankle_center_y * self.video_height) - 50)  # 발목보다 약간 위
        roi_y_end = min(self.video_height, roi_y_start + roi_height)
        
        roi = (roi_x_start, roi_y_start, roi_x_end - roi_x_start, roi_y_end - roi_y_start)
        logger.info(f"ROI 설정: {roi} (발목 중심: {ankle_center_x:.3f}, {ankle_center_y:.3f})")

        # 2. 시간적 일관성 검증 (정지 상태 확인)
        putative_balls = {}  # key: frame_idx, value: list of candidate circles
        for i in range(check_frames):
            frame_idx = address_frame_idx - i
            if frame_idx < 0:
                continue
            
            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self.video_capture.read()
            if not ret:
                continue
            
            candidates = self._find_ball_candidates_in_frame(frame, roi)
            if candidates:
                putative_balls[frame_idx] = candidates

        # 3. 여러 프레임에 걸쳐 가장 일관된 위치의 공을 최종 선택
        if not putative_balls:
            logger.info("어드레스 근처 프레임에서 공 후보를 전혀 찾지 못했습니다.")
            return None
        
        # 마지막 프레임(어드레스 시점)의 후보들을 기준으로 이전 프레임들과 비교
        last_frame_candidates = putative_balls.get(address_frame_idx, [])
        for ball1 in last_frame_candidates:
            is_stationary = True
            for i in range(1, check_frames):
                prev_frame_idx = address_frame_idx - i
                prev_candidates = putative_balls.get(prev_frame_idx, [])
                
                
                # 이전 프레임에서 현재 후보와 충분히 가까운 공이 있는지 확인
                is_found_in_prev = any(
                    np.linalg.norm(np.array(ball1[:2]) - np.array(b2[:2])) < ball1[2] * 2 # 반지름의 2배 이내
                    for b2 in prev_candidates
                    )
                if not is_found_in_prev:
                    is_stationary = False
                    break
            
            if is_stationary:
                x, y, r = ball1
                logger.info(f"정지된 공을 찾았습니다: ({x}, {y}), 반지름: {r}")
                # Bounding Box (x, y, w, h) 형태로 반환
                return (x - r, y - r, 2 * r, 2 * r)

        logger.warning("여러 프레임에 걸쳐 정지 상태를 유지하는 공을 찾지 못했습니다. Fallback 모드 시도...")
        
        # Fallback: 가장 많이 탐지된 후보를 선택
        if putative_balls:
            all_candidates = []
            for frame_candidates in putative_balls.values():
                all_candidates.extend(frame_candidates)
            
            if all_candidates:
                # 가장 아래쪽(지면에 가까운) 후보를 선택
                best_candidate = max(all_candidates, key=lambda c: c[1])  # y좌표가 큰 것
                x, y, r = best_candidate
                logger.info(f"Fallback으로 공을 선택했습니다: ({x}, {y}), 반지름: {r}")
                return (x - r, y - r, 2 * r, 2 * r)
        
        return None

    def _find_ball_candidates_in_frame(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> List[Tuple[int, int, int]]:
        """단일 프레임의 특정 ROI 내에서 공 후보들을 찾습니다."""
        x, y, w, h = roi
        frame_roi = frame[y:y+h, x:x+w]
        
        if frame_roi.size == 0:
            return []
        
        # 전처리
        gray = cv2.cvtColor(frame_roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        
        # Hough Circle Transform으로 원형 객체 탐지 (더 관대한 매개변수)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=1.5, minDist=20,
            param1=80, param2=12,  # 더 낮은 임계값으로 더 많은 후보 탐지
            minRadius=max(2, int(self.video_width * 0.003)),  # 더 작은 반지름부터
            maxRadius=int(self.video_width * 0.04)  # 더 큰 반지름까지
        )
        
        logger.info(f"프레임에서 탐지된 원형 객체 수: {len(circles[0]) if circles is not None else 0}")

        candidates = []
        if circles is not None:
            for c in circles[0, :]:
                # ROI 좌표를 전체 프레임 좌표로 변환
                candidates.append((int(c[0] + x), int(c[1] + y), int(c[2])))
        return candidates

    def _create_tracker(self):
        """다양한 OpenCV 버전에 호환되는 방식으로 트래커를 생성합니다."""
        try:
            # OpenCV 4.5.1 이상에서 사용되는 방식
            return cv2.TrackerCSRT_create()
        except AttributeError:
            try:
                # OpenCV 4.x 초기 버전에서 사용되는 방식
                return cv2.legacy.TrackerCSRT_create()
            except AttributeError:
                try:
                    # cv2.TrackerCSRT() 방식
                    return cv2.TrackerCSRT()
                except AttributeError:
                    try:
                        # 더 오래된 버전의 CSRT 트래커
                        return cv2.TrackerCSRT.create()
                    except AttributeError:
                        try:
                            # KCF 트래커로 폴백
                            logger.warning("CSRT 트래커를 사용할 수 없어 KCF 트래커를 사용합니다.")
                            return cv2.TrackerKCF_create()
                        except AttributeError:
                            try:
                                return cv2.legacy.TrackerKCF_create()
                            except AttributeError:
                                try:
                                    return cv2.TrackerKCF()
                                except AttributeError:
                                    # 최후의 수단
                                    logger.error("사용 가능한 트래커를 찾을 수 없습니다.")
                                    raise RuntimeError("OpenCV 트래커를 초기화할 수 없습니다.")

    def track_and_draw_trajectory(self, impact_frame_idx: Optional[int] = None, initial_ball_bbox: Optional[Tuple[int, int, int, int]] = None,
                                  output_path: Optional[Path] = None, update_callback: Optional[callable] = None) -> Dict:
        """
        임팩트부터 공을 추적하고, 포물선 궤적을 그려 비디오를 생성합니다.
        """
        # 분석 결과가 없으면 먼저 분석 수행
        if self.analysis_result is None:
            self.analyze_video()
        
        # 임팩트 프레임이 지정되지 않았으면 분석 결과에서 가져오기
        if impact_frame_idx is None:
            impact_frame_idx = self.analysis_result['impact_frame']
        
        # 초기 볼 위치가 없으면 어드레스에서 찾기
        if initial_ball_bbox is None:
            initial_ball_bbox = self.find_stationary_ball()
            if initial_ball_bbox is None:
                raise ValueError("골프공을 찾을 수 없습니다.")
        
        # 출력 경로가 없으면 기본 경로 설정
        if output_path is None:
            output_path = Path("ball_tracking_output.mp4")
        
        # 1. 비디오 라이터 준비
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*'mp4v'), self.fps, (self.video_width, self.video_height))
        if not writer.isOpened():
            raise RuntimeError("비디오 라이터를 생성할 수 없습니다.")
        
        # 2. 추적기 초기화 (여러 버전 호환 방식)
        tracker = self._create_tracker()
        self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, impact_frame_idx)
        ret, frame = self.video_capture.read()
        if not ret:
            raise ValueError("임팩트 프레임을 읽을 수 없습니다.")
        tracker.init(frame, initial_ball_bbox)

        tracked_points = []
        center_x = initial_ball_bbox[0] + initial_ball_bbox[2] // 2
        center_y = initial_ball_bbox[1] + initial_ball_bbox[3] // 2
        tracked_points.append((center_x, center_y))

        total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 3. 임팩트부터 영상 끝까지 프레임 단위 추적
        for i in range(impact_frame_idx, total_frames):
            ret, frame = self.video_capture.read()
            if not ret:
                logger.warning(f"프레임 {i}을 읽을 수 없습니다.")
                break
                
            success, bbox = tracker.update(frame)
            if success:
                center_x = int(bbox[0] + bbox[2] / 2)
                center_y = int(bbox[1] + bbox[3] / 2)
                tracked_points.append((center_x, center_y))
            else:
                logger.warning(f"프레임 {i}에서 공 추적 실패.")
                break
            
            final_frame = self._draw_trajectory_on_frame(frame, tracked_points)
            writer.write(final_frame)
            
            if i % 10 == 0 and update_callback:
                progress = int((i - impact_frame_idx) * 100 / (total_frames - impact_frame_idx))
                update_callback(progress)

        writer.release()
        
        metrics = self._calculate_metrics(tracked_points)
        logger.info(f"볼 트래킹 완료. 분석 결과: {metrics}")
        return {"status": "Success", "metrics": metrics}

    def _draw_trajectory_on_frame(self, frame: np.ndarray, points: List[Tuple[int, int]]) -> np.ndarray:
        """수집된 좌표를 바탕으로 포물선 궤적을 계산하고 프레임에 그립니다."""
        if len(points) < 3:
            return frame # 점이 충분하지 않으면 그리지 않음
        
        x = np.array([p[0] for p in points])
        y = np.array([p[1] for p in points])
        
        try:
            # 2차 다항식 (포물선) 피팅
            coeffs = np.polyfit(x, y, 2)
            poly = np.poly1d(coeffs)
            
            fit_x = np.linspace(x[0], x[-1], 100)
            fit_y = poly(fit_x)
            
            trajectory_points = np.array([fit_x, fit_y]).T.reshape((-1, 1, 2)).astype(np.int32)
            cv2.polylines(frame, [trajectory_points], isClosed=False, color=(50, 255, 255), thickness=3, lineType=cv2.LINE_AA)
        except np.linalg.LinAlgError:
            # 피팅 실패 시 (수직선 등), 점들을 직선으로 연결
            trajectory_points = np.array(points).reshape((-1, 1, 2)).astype(np.int32)
            cv2.polylines(frame, [trajectory_points], isClosed=False, color=(50, 255, 255), thickness=3, lineType=cv2.LINE_AA)
            
        return frame

    def _calculate_metrics(self, points: List[Tuple[int, int]]) -> Dict:
        """추적된 궤적으로 발사각, 최고 높이 등을 계산합니다."""
        if len(points) < 5 or self.fps == 0:
            return {}

        # 발사 각도 (처음 5개 프레임 사용)
        dx = points[4][0] - points[0][0]
        dy = points[4][1] - points[0][1] # y축이 아래로 향하므로, 실제 상승은 음수값
        launch_angle = np.degrees(np.arctan2(-dy, dx))

        # 최고 높이 (Apex) - y좌표가 가장 작은 지점
        apex_y = min(p[1] for p in points)
        initial_y = points[0][1]
        apex_height_px = initial_y - apex_y

        return {
            "launch_angle_deg": round(launch_angle, 1),
            "apex_height_px": round(apex_height_px, 1)
        } 