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
REGISTRATION_CONFIDENCE_RATIO_DEFAULT = 0.8
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
    """Returns the number of dark pixels for a single answer/registration bubble."""
    P = padding
    x_start, y_start = max(0, int(x - P)), max(0, int(y - P))
    x_end, y_end = int(x + w + P), int(y + h + P)
    bubble_roi = aligned_img[y_start:y_end, x_start:x_end]
    if bubble_roi.size == 0:
        return 0
    gray_roi = cv2.cvtColor(bubble_roi, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    return cv2.countNonZero(thresh)


def extract_text_zone(aligned_img, zones_map, zone_name, padding):
    """Extracts OCR text from a named rectangular zone, returning '' if absent."""
    if zone_name not in zones_map:
        return ""

    x, y, w, h = [int(v) for v in zones_map[zone_name]]
    roi = aligned_img[max(0, y-padding):y+h+padding, max(0, x-padding):x+w+padding]
    return extract_text_from_roi(roi)


def classify_bubble_scores(scores, labels, threshold, confidence_ratio):
    """Classifies one group of mutually-exclusive bubbles.

    Returns (value, confidence). The value is:
      - 'BLANK' when no bubble crosses the absolute threshold;
      - one label for a clear mark;
      - comma-joined labels when multiple bubbles look marked.
    """
    max_score = max(scores) if scores else 0

    if max_score < threshold:
        return 'BLANK', 1.0

    marked = [labels[k] for k, score in enumerate(scores) if score >= max_score * confidence_ratio]

    if len(marked) == 1:
        return marked[0], 0.99

    if len(marked) > 1:
        return ",".join(sorted(marked)), 0.90

    # Rare case where no bubble meets the confidence ratio despite a high score.
    return 'BLANK', 0.80


def cap_registration_padding(zones_map, requested_padding):
    """Caps registration padding so one digit ROI does not overlap neighbors."""
    bubble_columns = zones_map.get('registration_bubbles')
    if not bubble_columns:
        return requested_padding

    gaps = []

    # Vertical gaps between digit rows inside each registration position.
    for column in bubble_columns:
        rects = sorted(column, key=lambda rect: rect[1])
        for current, nxt in zip(rects, rects[1:]):
            gap = int(nxt[1]) - (int(current[1]) + int(current[3]))
            if gap >= 0:
                gaps.append(gap)

    # Horizontal gaps between registration positions for the same digit row.
    row_count = max((len(column) for column in bubble_columns), default=0)
    for row_idx in range(row_count):
        rects = [
            column[row_idx]
            for column in bubble_columns
            if row_idx < len(column)
        ]
        rects.sort(key=lambda rect: rect[0])
        for current, nxt in zip(rects, rects[1:]):
            gap = int(nxt[0]) - (int(current[0]) + int(current[2]))
            if gap >= 0:
                gaps.append(gap)

    if not gaps:
        return requested_padding

    safe_padding = max(0, min(gaps) // 2 - 1)
    if requested_padding > safe_padding:
        print(
            f"  -> Registration padding capped from {requested_padding}px "
            f"to {safe_padding}px to avoid neighboring bubble overlap."
        )
    return min(requested_padding, safe_padding)


def decode_registration_bubbles(aligned_img, zones_map, padding, threshold, confidence_ratio, page_number):
    """Reads a bubble-encoded student registration number.

    Expected zone-map format:
        registration_options: ["0", ..., "9"]
        registration_bubbles: [
            [[x, y, w, h], ... ten digit bubbles for position 1],
            ...
        ]

    Returns the decoded string. Ambiguous or blank positions are represented as '?'.
    """
    bubble_columns = zones_map.get('registration_bubbles')
    if not bubble_columns:
        return None

    labels = zones_map.get('registration_options') or [str(digit) for digit in range(10)]
    digits = []

    for digit_index, bubbles in enumerate(bubble_columns, start=1):
        if len(bubbles) != len(labels):
            print(
                f"Warning: Registration position {digit_index} has {len(bubbles)} bubbles "
                f"but {len(labels)} labels. Marking it as unknown.",
                file=sys.stderr,
            )
            digits.append('?')
            continue

        scores = [
            get_bubble_score(aligned_img, x, y, w, h, padding)
            for x, y, w, h in bubbles
        ]
        value, _confidence = classify_bubble_scores(scores, labels, threshold, confidence_ratio)

        if value == 'BLANK':
            print(
                f"Warning: Blank registration digit at page {page_number}, position {digit_index}.",
                file=sys.stderr,
            )
            digits.append('?')
        elif ',' in value:
            print(
                f"Warning: Ambiguous registration digit at page {page_number}, "
                f"position {digit_index}: {value}.",
                file=sys.stderr,
            )
            digits.append('?')
        else:
            digits.append(value)

    return ''.join(digits)


# --- MAIN SCRIPT ---


def main(args):
    print(f"Loading zones map from: {args.zones_file}")
    with open(args.zones_file, 'r') as f:
        ZONES_MAP = json.load(f)

    print("Managing image cache...")
    template_image_path = omr_utils.manage_image_cache(args.template_pdf, args.images_dir, is_template=True)[0]
    student_image_paths = omr_utils.manage_image_cache(args.student_sheets_pdf, args.images_dir, args.images_prefix)

    template = cv2.imread(template_image_path)
    all_results = []

    registration_padding = args.registration_padding
    if registration_padding is None:
        registration_padding = cap_registration_padding(ZONES_MAP, args.padding)

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

        # Prefer bubble-encoded registration when present. Fall back to OCR zones
        # for legacy sheets.
        student_id = decode_registration_bubbles(
            aligned,
            ZONES_MAP,
            registration_padding,
            args.threshold,
            args.registration_confidence_ratio,
            page_number,
        )

        if student_id is None:
            student_id = extract_text_zone(aligned, ZONES_MAP, 'student_id', args.padding)
            student_name = extract_text_zone(aligned, ZONES_MAP, 'student_name', args.padding)
        else:
            student_name = ""

        raw_exam_type = extract_text_zone(aligned, ZONES_MAP, 'exam_type', args.padding)
        exam_type = omr_utils.normalize_exam_type(raw_exam_type)
        if raw_exam_type.strip() and exam_type != raw_exam_type.strip():
            print(
                f"  -> Normalized exam type OCR '{raw_exam_type}' to '{exam_type}' "
                f"on page {page_number}."
            )

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

                answer, confidence = classify_bubble_scores(
                    scores,
                    options,
                    args.threshold,
                    args.confidence_ratio,
                )

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
    parser.add_argument("--registration-padding", type=int, help="Padding in pixels for registration bubbles. Defaults to --padding capped to avoid neighboring bubble overlap.")
    parser.add_argument("--threshold", type=int, default=PIXEL_THRESHOLD_DEFAULT, help=f"Pixel count to consider a bubble marked. Default: {PIXEL_THRESHOLD_DEFAULT}")
    parser.add_argument("--confidence-ratio", type=float, default=CONFIDENCE_RATIO_DEFAULT, help=f"Confidence ratio for answer bubbles. Default: {CONFIDENCE_RATIO_DEFAULT}")
    parser.add_argument("--registration-confidence-ratio", type=float, default=REGISTRATION_CONFIDENCE_RATIO_DEFAULT, help=f"Confidence ratio for registration digit bubbles. Default: {REGISTRATION_CONFIDENCE_RATIO_DEFAULT}")
    main(parser.parse_args())
