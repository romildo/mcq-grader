# process_sheets.py
import cv2
import os
import pytesseract
import pandas as pd
import re
import argparse
import json
import sys
import omr_utils

# --- LOGIC CONSTANTS ---
# Default values for command-line arguments
PIXEL_THRESHOLD_DEFAULT = 1000
CONFIDENCE_RATIO_DEFAULT = 0.7
PADDING_DEFAULT = 10

# --- HELPER FUNCTIONS ---

def extract_text_from_roi(roi):
    """Applies preprocessing and extracts text from a Region of Interest (ROI)."""
    if roi.size == 0:
        return ""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    config = "--psm 7"
    return pytesseract.image_to_string(binary, config=config).strip()

def get_bubble_score(aligned_img, x, y, w, h, padding):
    """Returns the number of dark pixels for a single answer bubble."""
    P = padding
    x_start, y_start = max(0, int(x - P)), max(0, int(y - P))
    x_end, y_end = int(x + w + P), int(y + h + P)
    bubble_roi = aligned_img[y_start:y_end, x_start:x_end]
    if bubble_roi.size == 0:
        return 0
    gray_roi = cv2.cvtColor(bubble_roi, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    return cv2.countNonZero(thresh)

# --- MAIN SCRIPT ---

def main(args):
    print(f"Loading zones map from: {args.zones_file}")
    with open(args.zones_file, 'r') as f:
        ZONES_MAP = json.load(f)

    print("Managing image cache...")
    template_image_path = omr_utils.manage_image_cache(args.template_pdf, args.images_dir, "template", is_template=True)[0]
    student_image_paths = omr_utils.manage_image_cache(args.student_sheets_pdf, args.images_dir, args.images_prefix)
    
    template = cv2.imread(template_image_path)
    all_results = []

    for image_path in student_image_paths:
        filename = os.path.basename(image_path)
        print(f"Processing: {filename}...")
        student_sheet = cv2.imread(image_path)
        
        aligned = omr_utils.align_image(student_sheet, template, ZONES_MAP)
        
        # Find all numbers in the filename (without extension) and take the last one.
        numbers_in_filename = re.findall(r'\d+', os.path.splitext(filename)[0])
        if not numbers_in_filename:
            print(f"Warning: Could not determine page number from filename '{filename}'. Defaulting to 0.", file=sys.stderr)
            page_number = 0
        else:
            page_number = int(numbers_in_filename[-1])
        
        P = args.padding
        
        # Extract header info with padding
        x, y, w, h = [int(v) for v in ZONES_MAP['student_id']]
        id_roi = aligned[max(0, y-P):y+h+P, max(0, x-P):x+w+P]
        student_id = extract_text_from_roi(id_roi)
        
        x, y, w, h = [int(v) for v in ZONES_MAP['student_name']]
        name_roi = aligned[max(0, y-P):y+h+P, max(0, x-P):x+w+P]
        student_name = extract_text_from_roi(name_roi)

        x, y, w, h = [int(v) for v in ZONES_MAP['exam_type']]
        type_roi = aligned[max(0, y-P):y+h+P, max(0, x-P):x+w+P]
        exam_type = extract_text_from_roi(type_roi)
        
        answers, q_num, options = {}, 1, ['A', 'B', 'C', 'D', 'E']
        
        # Dynamically process any number of columns
        for col_idx, num_questions in enumerate(ZONES_MAP['questions_per_column']):
            col_x = ZONES_MAP['col_start_x'] + (col_idx * ZONES_MAP['col_spacing_x'])
            
            for i in range(num_questions):
                y = ZONES_MAP['question_y_start'] + (i * ZONES_MAP['bubble_spacing_y'])
                scores = []
                for j, option in enumerate(options):
                    x = col_x + (j * ZONES_MAP['bubble_spacing_x'])
                    w, h = ZONES_MAP['bubble_w'], ZONES_MAP['bubble_h']
                    scores.append(get_bubble_score(aligned, x, y, w, h, args.padding))
                
                max_score = max(scores) if scores else 0
                
                if max_score < args.threshold:
                    answer, confidence = 'BLANK', 1.0
                else:
                    marked_options = [options[k] for k, s in enumerate(scores) if s >= max_score * args.confidence_ratio]
                    if len(marked_options) == 1:
                        answer, confidence = marked_options[0], 0.99
                    elif len(marked_options) > 1:
                        answer, confidence = ",".join(sorted(marked_options)), 0.90
                    else: # Rare case where no bubble meets the confidence ratio despite a high score
                        answer, confidence = 'BLANK', 0.80

                answers[f'Q{q_num}'], answers[f'Confidence_Q{q_num}'] = answer, confidence
                q_num += 1
                
        result = {
            'PDF_Page': page_number, 
            'Student_ID': student_id, 
            'Student_Name': student_name, 
            'Exam_Type': exam_type, 
            **answers
        }
        all_results.append(result)

    pd.DataFrame(all_results).to_csv(args.output_csv, index=False)
    print(f"\nProcessing complete! Output saved to '{args.output_csv}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Processes scanned multiple-choice answer sheets.")
    parser.add_argument("--zones-file", required=True, help="Path to the .json file containing the zones map.")
    parser.add_argument("--output-csv", required=True, help="Path for the output CSV file.")
    parser.add_argument("--images-dir", required=True, help="Directory to cache/read sheet images.")
    parser.add_argument("--template-pdf", help="[Optional] PDF of the blank answer sheet template.")
    parser.add_argument("--student-sheets-pdf", help="[Optional] PDF containing all student answer sheets.")
    parser.add_argument("--images-prefix", help="Prefix for the image files in the cache. Defaults to the PDF name.")
    parser.add_argument("--padding", type=int, default=PADDING_DEFAULT, help=f"Safety margin (padding) in pixels for zones. Default: {PADDING_DEFAULT}")
    parser.add_argument("--threshold", type=int, default=PIXEL_THRESHOLD_DEFAULT, help=f"Pixel count to consider a bubble marked. Default: {PIXEL_THRESHOLD_DEFAULT}")
    parser.add_argument("--confidence-ratio", type=float, default=CONFIDENCE_RATIO_DEFAULT, help=f"Confidence ratio for multiple marks. Default: {CONFIDENCE_RATIO_DEFAULT}")
    main(parser.parse_args())
