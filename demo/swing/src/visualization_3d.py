import numpy as np
import plotly.graph_objects as go
from typing import Dict, List, Optional
import logging
from scipy.interpolate import interp1d

logger = logging.getLogger(__name__)

class SwingVisualizer3D:
    def __init__(self):
        """3D 시각화를 위한 초기화 - MediaPipe 33개 포인트 모두 활용"""
        # MediaPipe 33개 포즈 랜드마크 인덱스
        self.mp_pose_landmarks = {
            'nose': 0, 'left_eye_inner': 1, 'left_eye': 2, 'left_eye_outer': 3,
            'right_eye_inner': 4, 'right_eye': 5, 'right_eye_outer': 6,
            'left_ear': 7, 'right_ear': 8, 'mouth_left': 9, 'mouth_right': 10,
            'left_shoulder': 11, 'right_shoulder': 12, 'left_elbow': 13, 'right_elbow': 14,
            'left_wrist': 15, 'right_wrist': 16, 'left_pinky': 17, 'right_pinky': 18,
            'left_index': 19, 'right_index': 20, 'left_thumb': 21, 'right_thumb': 22,
            'left_hip': 23, 'right_hip': 24, 'left_knee': 25, 'right_knee': 26,
            'left_ankle': 27, 'right_ankle': 28, 'left_heel': 29, 'right_heel': 30,
            'left_foot_index': 31, 'right_foot_index': 32
        }
        
        # 기본 스켈레톤 연결 (주요 구조)
        self.basic_connections = [
            ('left_shoulder', 'right_shoulder'),
            ('left_shoulder', 'left_elbow'),
            ('left_elbow', 'left_wrist'),
            ('right_shoulder', 'right_elbow'),
            ('right_elbow', 'right_wrist'),
            ('left_shoulder', 'left_hip'),
            ('right_shoulder', 'right_hip'),
            ('left_hip', 'right_hip'),
            ('left_hip', 'left_knee'),
            ('left_knee', 'left_ankle'),
            ('right_hip', 'right_knee'),
            ('right_knee', 'right_ankle')
        ]
        
        # 얼굴 연결
        self.face_connections = [
            ('nose', 'left_eye'),
            ('nose', 'right_eye'),
            ('left_eye', 'left_ear'),
            ('right_eye', 'right_ear'),
            ('mouth_left', 'mouth_right')
        ]
        
        # 손 연결
        self.hand_connections = [
            ('left_wrist', 'left_pinky'),
            ('left_wrist', 'left_index'),
            ('left_wrist', 'left_thumb'),
            ('right_wrist', 'right_pinky'),
            ('right_wrist', 'right_index'),
            ('right_wrist', 'right_thumb')
        ]
        
        # 발 연결
        self.foot_connections = [
            ('left_ankle', 'left_heel'),
            ('left_heel', 'left_foot_index'),
            ('right_ankle', 'right_heel'),
            ('right_heel', 'right_foot_index')
        ]
        
        # 전체 연결 (선택적으로 사용)
        self.all_connections = (self.basic_connections + 
                               self.face_connections + 
                               self.hand_connections + 
                               self.foot_connections)
        
        self.colors = {
            'markers': '#2E86C1',
            'basic_skeleton': '#3498DB',
            'face': '#E67E22',
            'hands': '#9B59B6',
            'feet': '#1ABC9C',
            'trajectory': '#E74C3C',
            'plane': '#2ECC71'
        }
        
    def create_pose_plot(self, frame_data: Dict, show_trajectory: bool = False,
                        trajectory_data: Optional[List[Dict]] = None, 
                        detail_level: str = 'full') -> go.Figure:
        """3D 포즈 플롯 생성 - detail_level: 'basic', 'medium', 'full'"""
        try:
            fig = go.Figure()
            
            # 좌표계 변환: MediaPipe의 좌표계를 골프 자세에 맞게 변환
            landmarks_transformed = self._transform_coordinates(frame_data['landmarks'])
            
            # 궤적 데이터도 변환
            trajectory_transformed = None
            if show_trajectory and trajectory_data:
                trajectory_transformed = self._transform_trajectory_data(trajectory_data)
            
            # 세부 수준에 따라 다른 연결 사용
            if detail_level == 'basic':
                connections_to_use = self.basic_connections
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, connections_to_use, self.colors['basic_skeleton'])
            elif detail_level == 'medium':
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.basic_connections, self.colors['basic_skeleton'])
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.hand_connections, self.colors['hands'])
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.foot_connections, self.colors['feet'])
            else:  # full
                # 모든 세부사항 추가
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.basic_connections, self.colors['basic_skeleton'])
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.face_connections, self.colors['face'])
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.hand_connections, self.colors['hands'])
                self._add_skeleton_with_smooth_curves(fig, landmarks_transformed, self.foot_connections, self.colors['feet'])
            
            # 랜드마크 점 추가 (크기를 세부 수준에 따라 조정)
            marker_size = 6 if detail_level == 'full' else 8
            self._add_landmarks(fig, landmarks_transformed, marker_size)
            
            # 궤적 추가 (옵션)
            if show_trajectory and trajectory_transformed:
                self._add_smooth_trajectory(fig, trajectory_transformed)
            
            # 스윙 플레인 추가 (basic 이상일 때만)
            if detail_level != 'basic':
                self._add_swing_plane(fig, landmarks_transformed)
            
            # 레이아웃 설정
            self._set_layout(fig)
            
            return fig
            
        except Exception as e:
            logger.error(f"Error creating pose plot: {str(e)}")
            return go.Figure()
    
    def _transform_coordinates(self, landmarks: Dict) -> Dict:
        """좌표계 변환"""
        landmarks_transformed = {}
        for name, point in landmarks.items():
            landmarks_transformed[name] = [
                point[0],     # x -> x (right/left)
                -point[1],    # y -> -y (up/down, MediaPipe Y축 반전)
                point[2]      # z -> z (forward/backward)
            ]
        return landmarks_transformed
    
    def _transform_trajectory_data(self, trajectory_data: List[Dict]) -> List[Dict]:
        """궤적 데이터 변환"""
        trajectory_transformed = []
        for frame in trajectory_data:
            frame_transformed = {'landmarks': {}}
            for name, point in frame['landmarks'].items():
                frame_transformed['landmarks'][name] = [
                    point[0],
                    -point[1],
                    point[2]
                ]
            trajectory_transformed.append(frame_transformed)
        return trajectory_transformed
    
    def _add_skeleton_with_smooth_curves(self, fig: go.Figure, landmarks: Dict, 
                                       connections: List, color: str):
        """부드러운 곡선으로 스켈레톤 연결선 추가"""
        try:
            for start, end in connections:
                if start in landmarks and end in landmarks:
                    start_point = landmarks[start]
                    end_point = landmarks[end]
                    
                    # 직선 연결 (단순한 경우)
                    if np.linalg.norm(np.array(end_point) - np.array(start_point)) < 0.1:
                        # 너무 가까운 점들은 직선으로 연결
                        x_coords = [start_point[0], end_point[0]]
                        y_coords = [start_point[1], end_point[1]]
                        z_coords = [start_point[2], end_point[2]]
                    else:
                        # 부드러운 곡선 생성 (3차 스플라인)
                        t = np.linspace(0, 1, 10)  # 10개 점으로 보간
                        
                        # 제어점을 추가하여 자연스러운 곡선 생성
                        control_point = [
                            (start_point[0] + end_point[0]) / 2,
                            (start_point[1] + end_point[1]) / 2 + 0.02,  # 약간 위로 볼록
                            (start_point[2] + end_point[2]) / 2
                        ]
                        
                        # 베지어 곡선 근사
                        x_coords = []
                        y_coords = []
                        z_coords = []
                        
                        for t_val in t:
                            # 2차 베지어 곡선: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
                            point = [
                                (1-t_val)**2 * start_point[0] + 2*(1-t_val)*t_val * control_point[0] + t_val**2 * end_point[0],
                                (1-t_val)**2 * start_point[1] + 2*(1-t_val)*t_val * control_point[1] + t_val**2 * end_point[1],
                                (1-t_val)**2 * start_point[2] + 2*(1-t_val)*t_val * control_point[2] + t_val**2 * end_point[2]
                            ]
                            x_coords.append(point[0])
                            y_coords.append(point[1])
                            z_coords.append(point[2])
                    
                    fig.add_trace(go.Scatter3d(
                        x=x_coords,
                        y=y_coords,
                        z=z_coords,
                        mode='lines',
                        line=dict(
                            color=color,
                            width=4
                        ),
                        showlegend=False
                    ))
                    
        except Exception as e:
            logger.error(f"Error adding smooth skeleton: {str(e)}")
            
    def _add_landmarks(self, fig: go.Figure, landmarks: Dict, marker_size: int = 8):
        """랜드마크 점 추가"""
        try:
            for name, point in landmarks.items():
                # 포인트 타입에 따라 색상 구분
                if 'eye' in name or 'ear' in name or 'nose' in name or 'mouth' in name:
                    color = self.colors['face']
                elif 'wrist' in name or 'pinky' in name or 'index' in name or 'thumb' in name:
                    color = self.colors['hands']
                elif 'ankle' in name or 'heel' in name or 'foot' in name:
                    color = self.colors['feet']
                else:
                    color = self.colors['markers']
                
                fig.add_trace(go.Scatter3d(
                    x=[point[0]], y=[point[1]], z=[point[2]],
                    mode='markers+text',
                    name=name,
                    text=[name],
                    textposition='top center',
                    marker=dict(
                        size=marker_size,
                        color=color,
                        symbol='circle'
                    ),
                    hoverinfo='name+text',
                    textfont=dict(size=8),
                    showlegend=False
                ))
                
        except Exception as e:
            logger.error(f"Error adding landmarks: {str(e)}")
            
    def _add_smooth_trajectory(self, fig: go.Figure, trajectory_data: List[Dict]):
        """부드러운 스윙 궤적 추가"""
        try:
            # 클럽 헤드(오른쪽 손목) 궤적
            x_coords = [frame['landmarks']['right_wrist'][0] for frame in trajectory_data]
            y_coords = [frame['landmarks']['right_wrist'][1] for frame in trajectory_data]
            z_coords = [frame['landmarks']['right_wrist'][2] for frame in trajectory_data]
            
            # 궤적을 부드럽게 보간
            if len(x_coords) > 3:  # 스플라인 보간을 위해 최소 4개 점 필요
                t_original = np.linspace(0, 1, len(x_coords))
                t_smooth = np.linspace(0, 1, len(x_coords) * 3)  # 3배 더 부드럽게
                
                try:
                    # 1차원 스플라인 보간
                    fx = interp1d(t_original, x_coords, kind='cubic', bounds_error=False, fill_value='extrapolate')
                    fy = interp1d(t_original, y_coords, kind='cubic', bounds_error=False, fill_value='extrapolate')
                    fz = interp1d(t_original, z_coords, kind='cubic', bounds_error=False, fill_value='extrapolate')
                    
                    x_smooth = fx(t_smooth)
                    y_smooth = fy(t_smooth)
                    z_smooth = fz(t_smooth)
                except:
                    # 스플라인 보간 실패 시 원본 사용
                    x_smooth, y_smooth, z_smooth = x_coords, y_coords, z_coords
            else:
                x_smooth, y_smooth, z_smooth = x_coords, y_coords, z_coords
                
            fig.add_trace(go.Scatter3d(
                x=x_smooth,
                y=y_smooth,
                z=z_smooth,
                mode='lines',
                name='Swing Path',
                line=dict(
                    color=self.colors['trajectory'],
                    width=6
                ),
                opacity=0.8
            ))
            
        except Exception as e:
            logger.error(f"Error adding smooth trajectory: {str(e)}")
            
    def _add_swing_plane(self, fig: go.Figure, landmarks: Dict):
        """스윙 플레인 추가"""
        try:
            # 어깨 선과 힙 선을 이용하여 스윙 플레인 계산
            shoulder_vector = np.array(landmarks['right_shoulder']) - np.array(landmarks['left_shoulder'])
            hip_vector = np.array(landmarks['right_hip']) - np.array(landmarks['left_hip'])
            
            # 플레인의 법선 벡터 계산
            normal = np.cross(shoulder_vector, hip_vector)
            normal = normal / np.linalg.norm(normal)
            
            # 플레인 생성을 위한 그리드 포인트 생성
            center = np.mean([
                landmarks['right_shoulder'],
                landmarks['left_shoulder'],
                landmarks['right_hip'],
                landmarks['left_hip']
            ], axis=0)
            
            grid_size = 1.0
            xx, zz = np.meshgrid(
                np.linspace(center[0] - grid_size, center[0] + grid_size, 10),
                np.linspace(center[2] - grid_size, center[2] + grid_size, 10)
            )
            
            # 평면 방정식을 이용하여 y 좌표 계산
            yy = (-normal[0] * (xx - center[0]) - normal[2] * (zz - center[2])) / normal[1] + center[1]
            
            # 플레인 추가
            fig.add_trace(go.Surface(
                x=xx,
                y=yy,
                z=zz,
                opacity=0.3,
                showscale=False,
                colorscale=[[0, self.colors['plane']], [1, self.colors['plane']]],
                name='Swing Plane'
            ))
            
        except Exception as e:
            logger.error(f"Error adding swing plane: {str(e)}")
            
    def _set_layout(self, fig: go.Figure):
        """플롯 레이아웃 설정"""
        try:
            fig.update_layout(
                scene=dict(
                    aspectmode='data',
                    camera=dict(
                        up=dict(x=0, y=1, z=0),  # Y축이 위쪽 (머리 방향)
                        center=dict(x=0, y=0, z=0),
                        eye=dict(x=1.5, y=1.5, z=1.5)  # 대각선에서 바라보기
                    ),
                    xaxis=dict(title='X (좌우)', range=[-1, 1]),
                    yaxis=dict(title='Y (상하)', range=[-2, 0]),  # Y축 범위 조정 (서있는 자세에 맞게)
                    zaxis=dict(title='Z (앞뒤)', range=[-1, 1])
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=True,
                legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01
                )
            )
            
        except Exception as e:
            logger.error(f"Error setting layout: {str(e)}")
            
    def create_trajectory_animation(self, frames_data: List[Dict]) -> go.Figure:
        """스윙 궤적 애니메이션 생성"""
        try:
            fig = go.Figure()
            
            # 프레임 데이터 준비
            frames = []
            for i, frame_data in enumerate(frames_data):
                frame = go.Frame(
                    data=self._create_frame_data(frame_data, frames_data[:i+1]),
                    name=f'frame_{i}'
                )
                frames.append(frame)
            
            # 초기 프레임 설정
            initial_data = self._create_frame_data(frames_data[0], [frames_data[0]])
            for trace in initial_data:
                fig.add_trace(trace)
            
            # 프레임 추가
            fig.frames = frames
            
            # 애니메이션 컨트롤 추가
            self._add_animation_controls(fig, len(frames))
            
            # 레이아웃 설정
            self._set_layout(fig)
            
            return fig
            
        except Exception as e:
            logger.error(f"Error creating trajectory animation: {str(e)}")
            return go.Figure()
            
    def _create_frame_data(self, frame_data: Dict, trajectory_data: List[Dict]) -> List[go.Scatter3d]:
        """각 프레임의 데이터 생성"""
        try:
            frame_traces = []
            
            # 좌표계 변환 적용
            landmarks = {}
            for name, point in frame_data['landmarks'].items():
                landmarks[name] = [
                    point[0],     # x -> x (right/left)
                    -point[1],    # y -> -y (up/down, MediaPipe Y축 반전)
                    point[2]      # z -> z (forward/backward)
                ]
            
            # 랜드마크 점
            for name, point in landmarks.items():
                frame_traces.append(go.Scatter3d(
                    x=[point[0]], y=[point[1]], z=[point[2]],
                    mode='markers',
                    name=name,
                    marker=dict(
                        size=8,
                        color=self.colors['markers'],
                        symbol='circle'
                    )
                ))
            
            # 연결선
            for start, end in self.connections:
                if start in landmarks and end in landmarks:
                    start_point = landmarks[start]
                    end_point = landmarks[end]
                    frame_traces.append(go.Scatter3d(
                        x=[start_point[0], end_point[0]],
                        y=[start_point[1], end_point[1]],
                        z=[start_point[2], end_point[2]],
                        mode='lines',
                        line=dict(
                            color=self.colors['connections'],
                            width=5
                        ),
                        showlegend=False
                    ))
            
            # 궤적 추가 (좌표계 변환 적용)
            x_coords = [frame['landmarks']['right_wrist'][0] for frame in trajectory_data]
            y_coords = [-frame['landmarks']['right_wrist'][1] for frame in trajectory_data]  # Y축 반전
            z_coords = [frame['landmarks']['right_wrist'][2] for frame in trajectory_data]
            
            frame_traces.append(go.Scatter3d(
                x=x_coords,
                y=y_coords,
                z=z_coords,
                mode='lines',
                name='Swing Path',
                line=dict(
                    color=self.colors['trajectory'],
                    width=3
                ),
                opacity=0.7
            ))
            
            return frame_traces
            
        except Exception as e:
            logger.error(f"Error creating frame data: {str(e)}")
            return []
            
    def _add_animation_controls(self, fig: go.Figure, n_frames: int):
        """애니메이션 컨트롤 추가"""
        try:
            fig.update_layout(
                updatemenus=[
                    dict(
                        type='buttons',
                        showactive=False,
                        buttons=[
                            dict(
                                label='Play',
                                method='animate',
                                args=[None, dict(
                                    frame=dict(duration=50, redraw=True),
                                    fromcurrent=True,
                                    mode='immediate'
                                )]
                            ),
                            dict(
                                label='Pause',
                                method='animate',
                                args=[[None], dict(
                                    frame=dict(duration=0, redraw=False),
                                    mode='immediate',
                                    transition=dict(duration=0)
                                )]
                            )
                        ],
                        direction='left',
                        pad=dict(r=10, t=10),
                        x=0.1,
                        y=0,
                        xanchor='right',
                        yanchor='top'
                    )
                ],
                sliders=[
                    dict(
                        active=0,
                        yanchor='top',
                        xanchor='left',
                        currentvalue=dict(
                            font=dict(size=20),
                            prefix='Frame: ',
                            visible=True,
                            xanchor='right'
                        ),
                        pad=dict(b=10, t=50),
                        len=0.9,
                        x=0.1,
                        y=0,
                        steps=[
                            dict(
                                method='animate',
                                args=[[f'frame_{i}'], dict(
                                    frame=dict(duration=50, redraw=True),
                                    mode='immediate',
                                    transition=dict(duration=0)
                                )],
                                label=str(i)
                            )
                            for i in range(n_frames)
                        ]
                    )
                ]
            )
            
        except Exception as e:
            logger.error(f"Error adding animation controls: {str(e)}") 