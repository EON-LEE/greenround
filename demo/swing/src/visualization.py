# Visualization utilities for drawing analysis on frames
import cv2
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
import matplotlib.pyplot as plt
import io
import mediapipe as mp

# Define colors (BGR format)
COLOR_CORRECT = (0, 255, 0)  # Green
COLOR_INCORRECT = (0, 0, 255)  # Red
COLOR_NEUTRAL = (255, 255, 0) # Cyan
TEXT_COLOR = (255, 255, 255) # White

# Helper to get coordinates safely, converting normalized coords if needed
def _get_pixel_coords(frame_data: pd.Series, landmark_key_base: str, frame_width: int, frame_height: int) -> Optional[Tuple[int, int]]:
    """Gets landmark coordinates (x, y) from frame_data, assuming normalized coordinates initially."""
    x_key = f"{landmark_key_base}_x"
    y_key = f"{landmark_key_base}_y"
    if x_key in frame_data and y_key in frame_data:
        x_norm = frame_data[x_key]
        y_norm = frame_data[y_key]
        if pd.notna(x_norm) and pd.notna(y_norm):
            pixel_x = int(x_norm * frame_width)
            pixel_y = int(y_norm * frame_height)
            return pixel_x, pixel_y
    # print(f"Warning: Could not get pixel coords for {landmark_key_base}") # Reduce noise
    return None

def draw_key_frame_analysis(frame: np.ndarray,
                            frame_data: pd.Series,
                            evaluation: Dict[str, bool],
                            swing_part: str,
                            address_frame_data: Optional[pd.Series] = None) -> np.ndarray:
    """Draws analysis visualizations on the frame based on evaluation results."""
    
    annotated_frame = frame.copy()
    height, width, _ = frame.shape
    
    # --- Common drawing function --- 
    def draw_line(pt1_key, pt2_key, color, thickness=2):
        pt1 = _get_pixel_coords(frame_data, pt1_key, width, height)
        pt2 = _get_pixel_coords(frame_data, pt2_key, width, height)
        if pt1 and pt2:
            cv2.line(annotated_frame, pt1, pt2, color, thickness)
            
    def draw_circle(pt_key, radius, color, thickness=-1):
        pt = _get_pixel_coords(frame_data, pt_key, width, height)
        if pt:
            cv2.circle(annotated_frame, pt, radius, color, thickness)
            
    def draw_text(text, position, color, scale=0.7, thickness=2):
        cv2.putText(annotated_frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)

    # --- Visualization based on Swing Part and Evaluation --- 
    
    text_y_offset = 30
    
    if swing_part == 'address':
        eval_wrist = evaluation.get("Wrist Behind Ball Line (Est.)", False)
        eval_arm_angle = evaluation.get("Arm Angle Straight (165-180 deg)", False)
        arm_angle_val = frame_data.get('right_arm_angle', np.nan)
        
        # Midpoint visualization (between ankles)
        ankle_r = _get_pixel_coords(frame_data, 'right_ankle', width, height)
        ankle_l = _get_pixel_coords(frame_data, 'left_ankle', width, height)
        wrist_r = _get_pixel_coords(frame_data, 'right_wrist', width, height)
        
        if ankle_r and ankle_l and wrist_r:
            mid_x = (ankle_r[0] + ankle_l[0]) // 2
            mid_y = (ankle_r[1] + ankle_l[1]) // 2
            cv2.circle(annotated_frame, (mid_x, mid_y), 6, COLOR_NEUTRAL, -1)
            cv2.line(annotated_frame, (mid_x, mid_y), (wrist_r[0], wrist_r[1]), COLOR_CORRECT if eval_wrist else COLOR_INCORRECT, 2) # Line from midpoint to wrist
            # Vertical line from midpoint (representing ball line estimate)
            cv2.line(annotated_frame, (mid_x, mid_y - 50), (mid_x, mid_y + 50), COLOR_NEUTRAL, 1) 

        # Arm angle visualization
        arm_color = COLOR_CORRECT if eval_arm_angle else COLOR_INCORRECT
        draw_line('right_shoulder', 'right_elbow', arm_color)
        draw_line('right_elbow', 'right_wrist', arm_color)
        if pd.notna(arm_angle_val):
             draw_text(f'Arm Angle: {arm_angle_val:.1f} deg', (10, text_y_offset), arm_color); text_y_offset += 30
        # Add wrist text
        draw_text(f'Wrist/Ball: {"Ahead" if eval_wrist else "Behind"}', (10, text_y_offset), COLOR_CORRECT if eval_wrist else COLOR_INCORRECT); text_y_offset += 30
             
    elif swing_part == 'top':
        eval_hip_tilt = evaluation.get("Hip Tilt (~Vertical)", False)
        eval_arm_angle = evaluation.get("Arm Angle (130-150 deg)", False)
        eval_head_stable_key = next((k for k in evaluation if "Head Position Stable" in k), None)
        eval_head_stable = evaluation.get(eval_head_stable_key, False) if eval_head_stable_key else False
        
        arm_angle_val = frame_data.get('right_arm_angle', np.nan)
        hip_tilt_val = frame_data.get('hips_inclination', np.nan)
        
        # Arm Angle
        arm_color = COLOR_CORRECT if eval_arm_angle else COLOR_INCORRECT
        draw_line('right_shoulder', 'right_elbow', arm_color)
        draw_line('right_elbow', 'right_wrist', arm_color)
        if pd.notna(arm_angle_val):
             draw_text(f'Arm Angle: {arm_angle_val:.1f} deg', (10, text_y_offset), arm_color); text_y_offset += 30

        # Hip Tilt
        hip_color = COLOR_CORRECT if eval_hip_tilt else COLOR_INCORRECT
        draw_line('left_hip', 'right_hip', hip_color)
        if pd.notna(hip_tilt_val):
             draw_text(f'Hip Tilt: {hip_tilt_val:.1f} deg', (10, text_y_offset), hip_color); text_y_offset += 30
             
        # Head Stability
        if address_frame_data is not None:
            nose_addr = _get_pixel_coords(address_frame_data, 'nose', width, height)
            nose_curr = _get_pixel_coords(frame_data, 'nose', width, height)
            if nose_addr and nose_curr:
                 head_color = COLOR_CORRECT if eval_head_stable else COLOR_INCORRECT
                 # Draw circle around address position and line to current position
                 cv2.circle(annotated_frame, nose_addr, 15, head_color, 1) # Radius 15px as threshold estimate
                 cv2.circle(annotated_frame, nose_addr, 3, head_color, -1)
                 cv2.circle(annotated_frame, nose_curr, 3, head_color, -1)
                 cv2.line(annotated_frame, nose_addr, nose_curr, head_color, 1)
                 draw_text(f'Head Stable: {eval_head_stable}', (10, text_y_offset), head_color); text_y_offset += 30
                 
    elif swing_part == 'contact':
        eval_shoulder_ankle = evaluation.get("Shoulder Behind Ankle (Est.)", False)
        eval_knee_angle = evaluation.get("Knee Angle Straight (165-180 deg)", False)
        eval_arm_angle = evaluation.get("Arm Angle Straight (165-180 deg)", False)
        eval_head_stable_key = next((k for k in evaluation if "Head Position Stable" in k), None)
        eval_head_stable = evaluation.get(eval_head_stable_key, False) if eval_head_stable_key else False

        arm_angle_val = frame_data.get('right_arm_angle', np.nan)
        knee_angle_val = frame_data.get('right_knee_angle', np.nan)

        # Shoulder/Ankle Line
        shoulder_ankle_color = COLOR_CORRECT if eval_shoulder_ankle else COLOR_INCORRECT
        shoulder_l = _get_pixel_coords(frame_data, 'left_shoulder', width, height)
        ankle_l = _get_pixel_coords(frame_data, 'left_ankle', width, height)
        if shoulder_l and ankle_l:
             # Draw vertical line from ankle for reference
             cv2.line(annotated_frame, (ankle_l[0], ankle_l[1] - 50), (ankle_l[0], ankle_l[1] + 50), shoulder_ankle_color, 1)
             # Draw circle at shoulder position
             cv2.circle(annotated_frame, shoulder_l, 5, shoulder_ankle_color, -1)
             draw_text(f'Shoulder/Ankle: {eval_shoulder_ankle}', (10, text_y_offset), shoulder_ankle_color); text_y_offset += 30
             
        # Knee Angle
        knee_color = COLOR_CORRECT if eval_knee_angle else COLOR_INCORRECT
        draw_line('right_hip', 'right_knee', knee_color)
        draw_line('right_knee', 'right_ankle', knee_color)
        if pd.notna(knee_angle_val):
             draw_text(f'Knee Angle: {knee_angle_val:.1f} deg', (10, text_y_offset), knee_color); text_y_offset += 30

        # Arm Angle
        arm_color = COLOR_CORRECT if eval_arm_angle else COLOR_INCORRECT
        draw_line('right_shoulder', 'right_elbow', arm_color)
        draw_line('right_elbow', 'right_wrist', arm_color)
        if pd.notna(arm_angle_val):
             draw_text(f'Arm Angle: {arm_angle_val:.1f} deg', (10, text_y_offset), arm_color); text_y_offset += 30
             
        # Head Stability
        if address_frame_data is not None:
            nose_addr = _get_pixel_coords(address_frame_data, 'nose', width, height)
            nose_curr = _get_pixel_coords(frame_data, 'nose', width, height)
            if nose_addr and nose_curr:
                 head_color = COLOR_CORRECT if eval_head_stable else COLOR_INCORRECT
                 cv2.circle(annotated_frame, nose_addr, 15, head_color, 1)
                 cv2.circle(annotated_frame, nose_addr, 3, head_color, -1)
                 cv2.circle(annotated_frame, nose_curr, 3, head_color, -1)
                 cv2.line(annotated_frame, nose_addr, nose_curr, head_color, 1)
                 draw_text(f'Head Stable: {eval_head_stable}', (10, text_y_offset), head_color); text_y_offset += 30

    elif swing_part == 'follow_through':
        eval_arm_extended = evaluation.get("Arm Extended (> 150 deg)", False)
        eval_hips_rotated = evaluation.get("Hips Rotated (Placeholder)", False) # Placeholder check
        arm_angle_val = frame_data.get('right_arm_angle', np.nan)
        
        # Arm Extension
        arm_color = COLOR_CORRECT if eval_arm_extended else COLOR_INCORRECT
        draw_line('right_shoulder', 'right_elbow', arm_color)
        draw_line('right_elbow', 'right_wrist', arm_color)
        if pd.notna(arm_angle_val):
             draw_text(f'Arm Extended: {eval_arm_extended}', (10, text_y_offset), arm_color); text_y_offset += 30
             draw_text(f'(Angle: {arm_angle_val:.1f} deg)', (10, text_y_offset), arm_color); text_y_offset += 30
             
        # Hips Rotated (Placeholder text)
        hip_color = COLOR_CORRECT if eval_hips_rotated else COLOR_INCORRECT
        draw_line('left_hip', 'right_hip', hip_color)
        draw_text(f'Hips Rotated: {eval_hips_rotated}', (10, text_y_offset), hip_color); text_y_offset += 30
        
    elif swing_part == 'finish':
        eval_balanced = evaluation.get("Balanced Finish (Knees Bent)", False)
        eval_arm_relaxed = evaluation.get("Arm Relaxed (< 120 deg)", False)
        left_knee_angle_val = frame_data.get('left_knee_angle', np.nan)
        right_knee_angle_val = frame_data.get('right_knee_angle', np.nan)
        arm_angle_val = frame_data.get('right_arm_angle', np.nan)

        # Balance (Knee Angles)
        balance_color = COLOR_CORRECT if eval_balanced else COLOR_INCORRECT
        draw_line('left_hip', 'left_knee', balance_color)
        draw_line('left_knee', 'left_ankle', balance_color)
        draw_line('right_hip', 'right_knee', balance_color)
        draw_line('right_knee', 'right_ankle', balance_color)
        draw_text(f'Balanced: {eval_balanced}', (10, text_y_offset), balance_color); text_y_offset += 30
        # Optionally add knee angle values
        # if pd.notna(left_knee_angle_val) and pd.notna(right_knee_angle_val):
        #     draw_text(f'(Knees: {left_knee_angle_val:.0f}, {right_knee_angle_val:.0f} deg)', (10, text_y_offset), balance_color); text_y_offset += 30

        # Arm Relaxed
        arm_color = COLOR_CORRECT if eval_arm_relaxed else COLOR_INCORRECT
        draw_line('right_shoulder', 'right_elbow', arm_color)
        draw_line('right_elbow', 'right_wrist', arm_color)
        draw_text(f'Arm Relaxed: {eval_arm_relaxed}', (10, text_y_offset), arm_color); text_y_offset += 30
        if pd.notna(arm_angle_val):
             draw_text(f'(Angle: {arm_angle_val:.1f} deg)', (10, text_y_offset), arm_color); text_y_offset += 30

    return annotated_frame

def plot_swing_metric_graph(df: pd.DataFrame, 
                           key_frames: Dict[str, int], 
                           metric_col: str = 'right_wrist_y', 
                           y_label: str = 'Right Wrist Y Position') -> Optional[bytes]:
    """Plots a swing metric over time, marking key frames, and returns image bytes."""
    if df is None or df.empty or metric_col not in df.columns:
        print(f"Warning: Cannot generate metric graph. DataFrame empty or missing column '{metric_col}'.")
        return None
        
    plt.style.use('seaborn-v0_8-darkgrid') # Use a visually appealing style
    fig, ax = plt.subplots(figsize=(6, 4))
    
    # Plot the metric
    ax.plot(df.index, df[metric_col], label=y_label, color='#1f77b4')
    
    # Mark key frames
    colors = {'address': '#2ca02c', 'top': '#ff7f0e', 'contact': '#d62728', 'follow_through': '#9467bd', 'finish': '#8c564b'} # Green, Orange, Red, Purple/Brown
    for name, frame_idx in key_frames.items():
        if frame_idx in df.index: # Check if frame exists
            y_val = df.loc[frame_idx, metric_col]
            ax.axvline(x=frame_idx, color=colors.get(name, 'gray'), linestyle='--', linewidth=1.5, label=f'_{name}') # Underscore prevents legend entry
            ax.plot(frame_idx, y_val, marker='o', markersize=8, color=colors.get(name, 'black'))
            ax.text(frame_idx + 0.01 * len(df), y_val, f' {name.capitalize()}\n (Frame {frame_idx})', 
                     verticalalignment='center', color=colors.get(name, 'black'), fontsize=9)
                     
    # Invert Y axis if plotting Y coordinate (lower Y is higher on screen)
    if 'y' in metric_col.lower():
         ax.invert_yaxis()
         
    ax.set_title('Swing Analysis Timeline', fontsize=14)
    ax.set_xlabel('Frame Number', fontsize=10)
    ax.set_ylabel(y_label, fontsize=10)
    ax.tick_params(axis='both', which='major', labelsize=8)
    # ax.legend(fontsize=8)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    
    # Save to buffer
    try:
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close(fig) # Close the figure to free memory
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        print(f"Error generating plot image: {e}")
        plt.close(fig)
        return None

def create_swing_sequence_image(frames: Dict[str, np.ndarray],
                                key_frame_labels: List[str] = ['address', 'top', 'contact', 'finish'],
                                label_font_scale: float = 1.0,
                                label_thickness: int = 2) -> Optional[np.ndarray]:
    """Creates a combined image showing the swing sequence with pose landmarks.
    
    Args:
        frames: Dictionary of frames for each key position
        key_frame_labels: List of labels for each frame
        label_font_scale: Font scale for labels
        label_thickness: Thickness of label text
        
    Returns:
        Combined image with all frames side by side
    """
    if not frames or not key_frame_labels:
        return None
        
    # Initialize MediaPipe pose
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=True,
        min_detection_confidence=0.5
    )
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    
    # Process each frame with MediaPipe
    processed_frames = {}
    for label, frame in frames.items():
        # Convert to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        
        # Draw pose landmarks on frame
        annotated_frame = frame.copy()
        if results.pose_landmarks:
            # Draw the pose landmarks
            mp_drawing.draw_landmarks(
                annotated_frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
                connection_drawing_spec=mp_drawing_styles.get_default_pose_connections_style()
            )
        processed_frames[label] = annotated_frame
    
    # Get dimensions
    frame_height, frame_width = next(iter(frames.values())).shape[:2]
    n_frames = len(key_frame_labels)
    
    # Create combined image
    combined_width = frame_width * n_frames
    combined_height = frame_height
    combined_image = np.zeros((combined_height, combined_width, 3), dtype=np.uint8)
    
    # Add frames and labels
    for i, label in enumerate(key_frame_labels):
        if label in processed_frames:
            # Calculate position
            x_offset = i * frame_width
            
            # Add frame
            combined_image[:, x_offset:x_offset + frame_width] = processed_frames[label]
            
            # Add label
            label_position = (x_offset + 10, 30)
            cv2.putText(combined_image, label.upper(),
                       label_position,
                       cv2.FONT_HERSHEY_SIMPLEX,
                       label_font_scale,
                       (255, 255, 255),  # White color
                       label_thickness)
    
    return combined_image 