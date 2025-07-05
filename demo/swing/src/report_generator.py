import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Flowable
from reportlab.lib.units import inch
import matplotlib.pyplot as plt
import io
import pandas as pd # Keep pandas if it was used before
from typing import List, Dict, Optional, Tuple
import numpy as np # Keep numpy
import traceback # For debugging
import cv2 # Import OpenCV for image conversion
from PIL import Image as PilImage # Import PIL for image handling

# Helper class to handle image conversion for ReportLab
class ImageFlowable(Flowable):
    def __init__(self, img_data: np.ndarray, width=None, height=None):
        Flowable.__init__(self)
        self.img_width = width
        self.img_height = height
        self.img_data = img_data

    def draw(self):
        try:
            # Convert BGR (OpenCV) to RGB
            rgb_img = cv2.cvtColor(self.img_data, cv2.COLOR_BGR2RGB)
            # Create PIL Image
            pil_img = PilImage.fromarray(rgb_img)
            
            # Save PIL image to BytesIO buffer
            img_buffer = io.BytesIO()
            pil_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            # Create ReportLab Image from buffer
            rl_image = Image(img_buffer, width=self.img_width, height=self.img_height)
            rl_image.drawOn(self.canv, 0, 0)
        except Exception as e:
            print(f"ERROR drawing ImageFlowable: {e}")

class ReportGenerator:
    """Generates PDF report for golf swing analysis, including key position evaluation and images."""

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name='CustomTitle', parent=self.styles['Title'], fontSize=24, spaceAfter=15))
        self.styles.add(ParagraphStyle(name='CustomHeading1', parent=self.styles['h1'], fontSize=18, spaceAfter=12))
        self.styles.add(ParagraphStyle(name='CustomHeading2', parent=self.styles['h2'], fontSize=14, spaceAfter=10))
        self.styles.add(ParagraphStyle(name='EvaluationText', parent=self.styles['Normal'], spaceAfter=6))
        self.styles.add(ParagraphStyle(name='CorrectText', parent=self.styles['EvaluationText'], textColor=colors.darkgreen))
        self.styles.add(ParagraphStyle(name='IncorrectText', parent=self.styles['EvaluationText'], textColor=colors.red))
        self.styles.add(ParagraphStyle(name='ImageCaption', parent=self.styles['Normal'], alignment=1, spaceBefore=6, fontSize=8))

    # Updated generate_report to accept report_data dictionary
    def generate_report(self, report_data: Dict) -> str:
        """Generate PDF report using DataFrame, key frames, metrics, and evaluation."""
        doc = SimpleDocTemplate(self.output_path, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
        story = []

        # Extract data from report_data
        df = report_data.get("dataframe")
        key_frames = report_data.get("key_frames")
        metrics = report_data.get("metrics")
        evaluations = report_data.get("evaluations", {}) # Get evaluations generated in app.py
        key_frame_images = report_data.get("key_frame_images", {}) # Get images generated in app.py
        swing_graph_image_bytes = report_data.get("swing_graph_image") # Get graph bytes

        if df is None or key_frames is None or metrics is None:
            print("ERROR: Missing essential data (dataframe, key_frames, metrics) for report generation.")
            # Generate a minimal error report or raise error
            story.append(Paragraph("Error: Missing analysis data.", self.styles['Normal']))
            doc.build(story)
            return self.output_path

        # Title
        story.append(Paragraph("Golf Swing Analysis Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 0.1*inch))

        # --- Swing Visualization Section (Graph + Keyframes) --- 
        story.append(Paragraph("Swing Visualization", self.styles['CustomHeading1']))
        self._add_visualization_layout(story, swing_graph_image_bytes, key_frame_images, key_frames, is_sequence=False)
        story.append(Spacer(1, 0.2*inch))

        # --- Key Position Evaluation --- 
        story.append(Paragraph("Key Position Evaluation", self.styles['CustomHeading1']))
        sequence_order = ['address', 'top', 'contact', 'follow_through', 'finish']
        address_idx = key_frames.get('address', -1)
        try:
            valid_indices = {name: idx for name, idx in key_frames.items() if idx in df.index}
            if len(valid_indices) < len(sequence_order):
                story.append(Paragraph(f"Warning: Not all key frames have valid data ({len(valid_indices)}/{len(sequence_order)} found).", self.styles['Normal']))
            for name in sequence_order:
                idx = valid_indices.get(name)
                if idx is not None:
                    eval_result = evaluations.get(name, {})
                    # Re-evaluate if not found or marked as error, needed for direct calls too
                    if not eval_result or eval_result.get("Error") or eval_result.get("Evaluation Error"): 
                        print(f"Evaluating {name} frame {idx} for report...") # Debug log
                        eval_result = self._evaluate_correctness(df, name, idx, address_idx if name != 'address' and address_idx in df.index else None)
                    self._add_evaluation_section(story, f"{name.capitalize()} Position", eval_result, df.loc[idx])
                else:
                    story.append(Paragraph(f"{name.capitalize()} Position: Data unavailable.", self.styles['IncorrectText']))
                    story.append(Spacer(1, 0.1*inch))
        except Exception as e:
            print(f"ERROR during evaluation section generation: {e}")
            story.append(Paragraph(f"Error displaying evaluation: {e}", self.styles['IncorrectText']))
        
        story.append(Spacer(1, 0.2*inch))

        # --- Basic Metrics --- 
        story.append(Paragraph("Overall Swing Metrics", self.styles['CustomHeading1']))
        self._add_metrics_table(story, metrics)
        story.append(Spacer(1, 0.2*inch))

        # --- Recommendations based on Evaluation --- 
        story.append(Paragraph("Recommendations", self.styles['CustomHeading1']))
        address_eval = evaluations.get('address', {})
        top_eval = evaluations.get('top', {})
        contact_eval = evaluations.get('contact', {})
        # Add evals for follow_through and finish if recommendations are added for them
        # follow_through_eval = evaluations.get('follow_through', {})
        # finish_eval = evaluations.get('finish', {})
        recommendations = self._generate_recommendations_from_eval(address_eval, top_eval, contact_eval)
        if recommendations:
            for rec in recommendations:
                story.append(Paragraph(f"• {rec}", self.styles['Normal']))
                story.append(Spacer(1, 6))
        else:
             story.append(Paragraph("No specific recommendations based on evaluated criteria.", self.styles['Normal']))

        try:
            doc.build(story)
            print(f"SUCCESS: Report with evaluation and images generated at {self.output_path}")
            return self.output_path
        except Exception as e:
            print(f"ERROR: Failed to build PDF report: {e}")
            print(traceback.format_exc())
            # Optionally create minimal error report
            # doc = SimpleDocTemplate(self.output_path, pagesize=letter)
            # story = [Paragraph(f"Error generating report: {e}", self.styles['Normal'])]
            # doc.build(story)
            return self.output_path # Return path even on build error

    def _evaluate_correctness(self, data: pd.DataFrame, swing_part: str, swing_part_id: int, address_frame_id: Optional[int] = None) -> Dict[str, bool]:
        """Evaluate correctness of a swing position based on simple criteria."""
        results = {}
        required_cols = {
             'address': ['right_ankle_x', 'left_ankle_x', 'right_wrist_x', 'right_arm_angle'],
             'top': ['nose_x', 'nose_y', 'hips_inclination', 'right_arm_angle'],
             'contact': ['left_shoulder_x', 'left_ankle_x', 'right_knee_angle', 'right_arm_angle', 'nose_x', 'nose_y'],
             'follow_through': ['right_arm_angle', 'hips_inclination'], # Example cols
             'finish': ['right_arm_angle', 'left_knee_angle', 'right_knee_angle'] # Example cols
        }.get(swing_part, [])
        # Helper to get values safely
        def get_val(col_name, frame_id):
             if frame_id is None or col_name not in data.columns or frame_id not in data.index:
                 return np.nan
             try: return data.loc[frame_id, col_name] if pd.notna(data.loc[frame_id, col_name]) else np.nan
             except Exception: return np.nan
             
        # Check required columns exist
        if not all(col in data.columns for col in required_cols): 
             print(f"Warning: Missing required columns for {swing_part} evaluation.")
             # Don't return error, just evaluate what's possible
             # return {"Data Error": False} 

        try:
            # --- Address --- 
            if swing_part == 'address':
                midpoint_x = (get_val('right_ankle_x', swing_part_id) + get_val('left_ankle_x', swing_part_id)) / 2
                right_wrist_x = get_val('right_wrist_x', swing_part_id)
                arm_angle = get_val('right_arm_angle', swing_part_id)
                results["Wrist Behind Ball Line (Est.)"] = (midpoint_x - right_wrist_x < 0) if pd.notna(midpoint_x) and pd.notna(right_wrist_x) else False
                results["Arm Angle Straight (165-180 deg)"] = (165 <= arm_angle <= 180) if pd.notna(arm_angle) else False
            # --- Top --- 
            elif swing_part == 'top':
                if address_frame_id is None: return {"Address Frame Error": False} # Need address frame for comparison
                pelvis_angle = get_val('hips_inclination', swing_part_id)
                arm_angle = get_val('right_arm_angle', swing_part_id)
                nose_y_curr, nose_x_curr = get_val('nose_y', swing_part_id), get_val('nose_x', swing_part_id)
                nose_y_addr, nose_x_addr = get_val('nose_y', address_frame_id), get_val('nose_x', address_frame_id)
                results["Hip Tilt (~Vertical)"] = (abs(pelvis_angle) > 75) if pd.notna(pelvis_angle) else False # Slightly wider range? 
                results["Arm Angle (130-150 deg)"] = (130 <= arm_angle <= 150) if pd.notna(arm_angle) else False
                if pd.notna(nose_x_curr) and pd.notna(nose_y_curr) and pd.notna(nose_x_addr) and pd.notna(nose_y_addr):
                    head_dist = np.linalg.norm([nose_x_curr - nose_x_addr, nose_y_curr - nose_y_addr]); head_thr = 0.07 # Slightly more lenient threshold
                    results[f"Head Stable (<{head_thr:.2f} units)"] = (head_dist <= head_thr)
                else: results["Head Stable (N/A)"] = False
            # --- Contact --- 
            elif swing_part == 'contact':
                if address_frame_id is None: return {"Address Frame Error": False}
                l_sh_x, l_ank_x = get_val('left_shoulder_x', swing_part_id), get_val('left_ankle_x', swing_part_id)
                knee_ang, arm_ang = get_val('right_knee_angle', swing_part_id), get_val('right_arm_angle', swing_part_id)
                nose_y_curr, nose_x_curr = get_val('nose_y', swing_part_id), get_val('nose_x', swing_part_id)
                nose_y_addr, nose_x_addr = get_val('nose_y', address_frame_id), get_val('nose_x', address_frame_id)
                results["Shoulder Behind Ankle (Est.)"] = (l_ank_x - l_sh_x < 0) if pd.notna(l_ank_x) and pd.notna(l_sh_x) else False
                results["Knee Angle Straight (160-180 deg)"] = (160 <= knee_ang <= 180) if pd.notna(knee_ang) else False # Slightly wider range
                results["Arm Angle Straight (160-180 deg)"] = (160 <= arm_ang <= 180) if pd.notna(arm_ang) else False # Slightly wider range
                if pd.notna(nose_x_curr) and pd.notna(nose_y_curr) and pd.notna(nose_x_addr) and pd.notna(nose_y_addr):
                     head_dist = np.linalg.norm([nose_x_curr - nose_x_addr, nose_y_curr - nose_y_addr]); head_thr = 0.07
                     results[f"Head Stable (<{head_thr:.2f} units)"] = (head_dist <= head_thr)
                else: results["Head Stable (N/A)"] = False
            # --- Follow Through (Basic Checks) --- 
            elif swing_part == 'follow_through':
                 arm_angle = get_val('right_arm_angle', swing_part_id)
                 hip_angle = get_val('hips_inclination', swing_part_id)
                 results["Arm Extended (> 150 deg)"] = (arm_angle > 150) if pd.notna(arm_angle) else False
                 # Check if hips rotated significantly from address? Requires address hip angle.
                 # address_hip_angle = get_val('hips_inclination', address_frame_id)
                 # results["Hips Rotated"] = (abs(hip_angle - address_hip_angle) > 45) if pd.notna(hip_angle) and pd.notna(address_hip_angle) else False
                 results["Hips Rotated (Placeholder)"] = True # Placeholder
            # --- Finish (Basic Checks) --- 
            elif swing_part == 'finish':
                 arm_angle = get_val('right_arm_angle', swing_part_id)
                 left_knee_angle = get_val('left_knee_angle', swing_part_id)
                 right_knee_angle = get_val('right_knee_angle', swing_part_id)
                 results["Balanced Finish (Knees Bent)"] = (left_knee_angle < 160 and right_knee_angle < 160) if pd.notna(left_knee_angle) and pd.notna(right_knee_angle) else False
                 results["Arm Relaxed (< 120 deg)"] = (arm_angle < 120) if pd.notna(arm_angle) else False # Arm typically bent at finish

        except Exception as e:
            print(f"ERROR evaluating {swing_part} frame {swing_part_id}: {e}")
            # traceback.print_exc() # Uncomment for detailed traceback
            results = {"Evaluation Error": False}
        return results

    def _add_evaluation_section(self, story: List, title: str, evaluation: Dict[str, bool], frame_data: pd.Series):
        """Adds a section for a specific key position evaluation."""
        story.append(Paragraph(title, self.styles['CustomHeading2'])) # Use h2 style
        if not evaluation or "Error" in list(evaluation.keys())[0]:
            story.append(Paragraph(f"Evaluation data unavailable for {title}. ({list(evaluation.keys())[0]})", self.styles['IncorrectText']))
            return

        for criterion, is_correct in evaluation.items():
            value_str = ""
            try: # Safely try to get values for display
                if "Wrist Behind" in criterion:
                    # Requires recalculating midpoint or storing it
                    pass # Placeholder
                elif "Arm Angle" in criterion and "address" in title.lower():
                     angle = frame_data.get('right_arm_angle', np.nan)
                     value_str = f" (Value: {angle:.1f}°)" if pd.notna(angle) else " (Value: N/A)"
                elif "Arm Angle" in criterion and "top" in title.lower():
                     angle = frame_data.get('right_arm_angle', np.nan)
                     value_str = f" (Value: {angle:.1f}°)" if pd.notna(angle) else " (Value: N/A)"
                elif "Arm Angle" in criterion and "impact" in title.lower():
                     angle = frame_data.get('right_arm_angle', np.nan)
                     value_str = f" (Value: {angle:.1f}°)" if pd.notna(angle) else " (Value: N/A)"
                elif "Hip Tilt" in criterion:
                     tilt = frame_data.get('hips_inclination', np.nan)
                     value_str = f" (Value: {tilt:.1f}°)" if pd.notna(tilt) else " (Value: N/A)"
                elif "Head Stable" in criterion and "N/A" not in criterion:
                     # Requires address frame data passed here or recalculating dist
                     pass # Placeholder
                elif "Shoulder Behind" in criterion:
                     # Requires ankle/shoulder coords
                     pass # Placeholder
                elif "Knee Angle" in criterion:
                     angle = frame_data.get('right_knee_angle', np.nan)
                     value_str = f" (Value: {angle:.1f}°)" if pd.notna(angle) else " (Value: N/A)"
            except Exception as e:
                 print(f"Warn: Error getting value for criterion '{criterion}': {e}")
                 value_str = " (Value: Err)"

            text = f"• {criterion}{value_str}: "
            style = self.styles['CorrectText'] if is_correct else self.styles['IncorrectText']
            result_text = "Correct" if is_correct else "Needs Improvement"
            story.append(Paragraph(text + result_text, style))
            
        story.append(Spacer(1, 0.1*inch))

    def _add_metrics_table(self, story: List, metrics: Dict):
        """Adds the formatted table of swing metrics to the story (English)."""
        metrics_data = [
            ["Metric", "Value"],
            ["Backswing Angle (Arm, Max)", f"{metrics.get('backswing_angle', 0.0):.1f}°"],
            ["Impact Angle (Arm, Approx)", f"{metrics.get('impact_angle', 0.0):.1f}°"],
            ["Swing Speed (Est.)", f"{metrics.get('swing_speed', 0.0):.1f} °/s"],
            ["Shoulder Rotation (Max)", f"{metrics.get('shoulder_rotation', 0.0):.1f}°"],
            ["Hip Rotation (Max)", f"{metrics.get('hip_rotation', 0.0):.1f}°"]
        ]

        table = Table(metrics_data, colWidths=[2.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)

    def _add_angle_plot_from_df(self, story: List, df: pd.DataFrame):
        """(Placeholder) Adds angle plots using DataFrame columns."""
        if df is None or df.empty:
            story.append(Paragraph("Angle data unavailable, cannot generate graph.", self.styles['Normal']))
            return
        try:
            plt.figure(figsize=(7, 3))
            # Select columns to plot (use actual column names from app.py)
            cols_to_plot = [
                'right_arm_angle', 'shoulders_inclination', 'hips_inclination',
                'left_knee_angle', 'right_knee_angle' 
            ]
            available_cols = [col for col in cols_to_plot if col in df.columns]
            
            if not available_cols:
                story.append(Paragraph("Relevant angle columns not found in data.", self.styles['Normal']))
                plt.close()
                return
                
            for col in available_cols:
                plt.plot(df.index, df[col], label=col.replace('_', ' ').title())
                
            plt.title('Key Angles During Swing')
            plt.xlabel('Frame Number')
            plt.ylabel('Angle (degrees)')
            plt.legend(fontsize=7)
            plt.grid(True)
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150)
            plt.close()
            buf.seek(0)
            story.append(Image(buf, width=6*inch, height=2.5*inch))
        except Exception as e:
            print(f"ERROR generating angle plot from DataFrame: {e}")
            story.append(Paragraph(f"Error generating angle plot: {e}", self.styles['Normal']))

    def _generate_recommendations_from_eval(self, address_eval, top_eval, contact_eval, follow_through_eval={}, finish_eval={}) -> List[str]: # Added new args
        """Generate recommendations based on evaluation results for all phases."""
        recommendations = []
        # Address Phase
        if not address_eval.get("Wrist Behind Ball Line (Est.)", True):
            recommendations.append("Address: Hands slightly ahead of ball.")
        if not address_eval.get("Arm Angle Straight (165-180 deg)", True):
            recommendations.append("Address: Straighter lead arm.")
        # Top Phase
        if not top_eval.get("Hip Tilt (~Vertical)", True):
            recommendations.append("Top: Check hip tilt.")
        if not top_eval.get("Arm Angle (130-150 deg)", True):
            recommendations.append("Top: Check lead arm angle (130-150 deg).")
        head_stable_key_top = next((k for k in top_eval if "Head Position Stable" in k), None)
        if head_stable_key_top and not top_eval.get(head_stable_key_top, True):
            recommendations.append("Top: Minimize head movement.")
        # Contact Phase
        if not contact_eval.get("Shoulder Behind Ankle (Est.)", True):
             recommendations.append("Impact: Lead shoulder over/behind lead ankle.")
        if not contact_eval.get("Knee Angle Straight (160-180 deg)", True):
             recommendations.append("Impact: Straighter lead knee.")
        if not contact_eval.get("Arm Angle Straight (160-180 deg)", True):
            recommendations.append("Impact: Straighter lead arm.")
        head_stable_key_con = next((k for k in contact_eval if "Head Position Stable" in k), None)
        if head_stable_key_con and not contact_eval.get(head_stable_key_con, True):
            recommendations.append("Impact: Stable head position.")
            
        # --- Add Recommendations for Follow-Through and Finish --- 
        if not follow_through_eval.get("Arm Extended (> 150 deg)", True):
             recommendations.append("Follow-Through: Ensure arms are fully extended towards the target.")
        # if not follow_through_eval.get("Hips Rotated", True):
        #      recommendations.append("Follow-Through: Ensure hips have rotated fully.")
             
        if not finish_eval.get("Balanced Finish (Knees Bent)", True):
             recommendations.append("Finish: Hold a balanced finish position with weight forward and knees slightly bent.")
        if not finish_eval.get("Arm Relaxed (< 120 deg)", True):
             recommendations.append("Finish: Allow arms to relax and bend naturally after the swing.")
             
        return recommendations 

    def _add_visualization_layout(self, story: List, graph_bytes: Optional[bytes], 
                                images_data: Optional[Dict[str, np.ndarray]], # Can be sequence OR individuals
                                key_frames: Dict[str, int],
                                is_sequence: bool):
        """Adds the graph and swing images (sequence or individual) to the report."""
        
        # --- Prepare Left Column (Graph) --- 
        graph_flowable = Spacer(3*inch, 0.1*inch)
        graph_height = 2.5*inch # Default height if conversion fails
        if graph_bytes:
             try:
                  graph_pil = PilImage.open(io.BytesIO(graph_bytes))
                  graph_width = 3 * inch
                  aspect = graph_pil.height / graph_pil.width
                  graph_height = graph_width * aspect
                  graph_flowable = Image(io.BytesIO(graph_bytes), width=graph_width, height=graph_height)
             except Exception as e:
                  print(f"Error processing graph image for PDF: {e}")

        # --- Prepare Right Column (Sequence Image or Individual Key Frames) --- 
        right_column_content = []
        if is_sequence and images_data is not None:
             # --- Add Single Sequence Image --- 
             try:
                  seq_img_np = images_data # It's the numpy array directly if sequence
                  h, w, _ = seq_img_np.shape
                  seq_img_width = 4.5 * inch # Adjust width for sequence image
                  aspect = h / w
                  seq_img_height = seq_img_width * aspect
                  img_flowable = ImageFlowable(seq_img_np, width=seq_img_width, height=seq_img_height)
                  # Update caption for 5 frames
                  sequence_labels = ['address', 'top', 'contact', 'follow_through', 'finish']
                  caption_text = "Swing Sequence (" + "-".join(l.capitalize() for l in sequence_labels) + ")"
                  caption = Paragraph(caption_text, self.styles['ImageCaption'])
                  right_column_content = [img_flowable, caption]
             except Exception as e:
                  print(f"Error processing sequence image for PDF: {e}")
                  right_column_content = [Paragraph("Error displaying sequence image.", self.styles['IncorrectText'])]
        elif not is_sequence and images_data: 
             # --- Add Individual Annotated Key Frames (Fallback) --- 
             display_order = ['address', 'top', 'contact', 'follow_through', 'finish']
             img_width = 1.3 * inch
             for name in display_order:
                  if name in images_data and images_data[name] is not None:
                       img_np = images_data[name]
                       h, w, _ = img_np.shape
                       aspect = h / w
                       img_height = img_width * aspect
                       img_flowable = ImageFlowable(img_np, width=img_width, height=img_height)
                       caption = Paragraph(f"{name.capitalize()} (Frame {key_frames.get(name, '?')})", self.styles['ImageCaption'])
                       right_column_content.append(img_flowable)
                       right_column_content.append(caption)
                       right_column_content.append(Spacer(1, 0.05*inch))
                  else:
                       right_column_content.append(Paragraph(f"{name.capitalize()} (Image N/A)", self.styles['ImageCaption']))
                       right_column_content.append(Spacer(1, 0.1*inch))
        else:
             right_column_content = [Paragraph("Swing visualization images unavailable.", self.styles['Normal'])]

        # --- Create Table for Layout --- 
        # Adjust column widths to fit page (approx 7 inches available with 0.5 margins)
        left_col_width = 2.6 * inch 
        right_col_width = 4.7 * inch if is_sequence else 1.5 * inch # Wider if sequence
        
        table_data = [[graph_flowable, right_column_content]]
        # Ensure total width doesn't exceed page width
        total_width = left_col_width + right_col_width
        max_width = 7.0 * inch 
        if total_width > max_width:
             scale = max_width / total_width
             left_col_width *= scale
             right_col_width *= scale
             
        table = Table(table_data, colWidths=[left_col_width, right_col_width])
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0), 
            ('LEFTPADDING', (1, 0), (1, 0), 5), 
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        story.append(table) 