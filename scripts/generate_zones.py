# generate_zones.py
import re
import argparse
import math
import sys
import os
import json

# --- CONSTANTS ---
DPI = 300
SP_PER_INCH = 72.27 * 65536  # TeX scaled points per inch

def sp_to_pixels(sp_val, page_height_px=None):
    """Converts coordinates from TeX's 'sp' unit to pixels."""
    inches = sp_val / SP_PER_INCH
    px = inches * DPI
    if page_height_px is not None:
        # Invert Y-axis for image coordinates (top-left origin)
        return page_height_px - px
    return px

def main(args):
    # --- (File reading and initial parsing are unchanged) ---
    print(f"Parsing position file: {args.aux_file}")
    print(f"Parsing dimension file: {args.zones_file}")

    try:
        with open(args.aux_file, 'r') as f: aux_content = f.read()
        with open(args.zones_file, 'r') as f: zones_content = f.read()
    except FileNotFoundError as e:
        print(f"Error: File not found - {e.filename}", file=sys.stderr)
        sys.exit(1)

    # Regex for positions from the .aux file
    main_regex = re.compile(r"\\zref@newlabel\{([^}]+)\}\{(\\posx\{\d+\}\\posy\{\d+\})\}")
    pos_x_regex_inner = re.compile(r"\\posx\{(\d+)\}")
    pos_y_regex_inner = re.compile(r"\\posy\{(\d+)\}")

    # Regex for dimensions and layout properties from the custom .zones file
    prop_regex_dim = re.compile(r"zoneprop\{([^}]+)\}\{([^}]+)\}\{([\d.-]+)pt\}")
    prop_regex_val = re.compile(r"zoneprop\{([^}]+)\}\{value\}\{([\d.-]+)pt\}")

    positions_sp = {}
    properties = {}

    def ensure_label(label):
        if label not in positions_sp:
            positions_sp[label] = {}

    # Extract X, Y positions from .aux file
    for match in main_regex.finditer(aux_content):
        label, content = match.groups()
        ensure_label(label)
        x_match = pos_x_regex_inner.search(content)
        y_match = pos_y_regex_inner.search(content)
        if x_match: positions_sp[label]['x'] = int(x_match.group(1))
        if y_match: positions_sp[label]['y'] = int(y_match.group(1))

    # Extract width, height dimensions from .zones file
    for match in prop_regex_dim.finditer(zones_content):
        label, prop, val_pt = match.groups()
        ensure_label(label)
        positions_sp[label][prop] = float(val_pt) * 65536  # Convert pt to sp

    # Extract generic layout properties (total questions, etc.)
    for match in prop_regex_val.finditer(zones_content):
        label, value = match.groups()
        properties[label] = int(float(value))

    # --- PAGE HEIGHT DETECTION LOGIC (with fallback) ---
    page_height_sp = positions_sp.get('page-1.height', {}).get('y')

    if not page_height_sp:
        print("Warning: 'page-1.height' not found in .aux file. Attempting to get height from .log file...")
        log_file_path = os.path.splitext(args.aux_file)[0] + '.log'
        try:
            with open(log_file_path, 'r', errors='ignore') as f:
                log_content = f.read()
            match = re.search(r"\\paperheight=([\d.]+)pt", log_content)
            if match:
                paper_height_pt = float(match.group(1))
                page_height_sp = paper_height_pt * 65536
                print(f"  -> Found page height in .log: {paper_height_pt}pt")
        except FileNotFoundError:
            print(f"  -> Warning: .log file not found at '{log_file_path}'.")

    if not page_height_sp:
        print("\nCRITICAL ERROR: Could not determine page height from .aux or .log files.", file=sys.stderr)
        sys.exit(1)

    page_height_px = sp_to_pixels(page_height_sp)

    # Convert all properties from sp to pixels
    positions_px = {}
    for label, props in positions_sp.items():
        px_props = {}
        if 'x' in props: px_props['x'] = sp_to_pixels(props['x'])
        if 'y' in props: px_props['y'] = sp_to_pixels(props['y'], page_height_px)
        # --- THIS IS THE CORRECTED BLOCK ---
        if 'width' in props: px_props['w'] = sp_to_pixels(props['width'])
        if 'height' in props: px_props['h'] = sp_to_pixels(props['height'])
        # --- END OF CORRECTION ---
        if px_props: positions_px[label] = px_props

    # --- VERIFY THAT ESSENTIAL LABELS AND PROPERTIES WERE FOUND ---
    required_labels = ['student_id', 'student_name', 'exam_type', 'q1A', 'q1B', 'q2A']
    required_props = ['total_questions', 'max_questions_per_column']
    
    total_q = properties.get('total_questions', 0)
    max_per_col = properties.get('max_questions_per_column', 0)

    # Dynamically determine the label for the start of the second column
    q_col2_label = None
    if total_q > max_per_col > 0:
        q_col2_label = f"q{max_per_col + 1}A"
        required_labels.append(q_col2_label)

    missing_labels = [label for label in required_labels if label not in positions_px]
    missing_props = [prop for prop in required_props if prop not in properties]

    if missing_labels or missing_props:
        print("\nERROR: Could not find the following essential items:", file=sys.stderr)
        for label in missing_labels: print(f"  - Label '{label}' missing from .aux/.zones files.", file=sys.stderr)
        for prop in missing_props: print(f"  - Property '{prop}' missing from .zones file.", file=sys.stderr)
        print("\nPlease check your .tex and .sty files.", file=sys.stderr)
        sys.exit(1)

    # --- GENERATE THE GENERALIZED ZONES MAP DICTIONARY ---
    questions_per_column = []
    remaining_q = total_q
    while remaining_q > 0:
        q_in_this_col = min(remaining_q, max_per_col)
        questions_per_column.append(q_in_this_col)
        remaining_q -= q_in_this_col

    student_id, student_name, exam_type = positions_px['student_id'], positions_px['student_name'], positions_px['exam_type']
    q1_A, q1_B, q2_A = positions_px['q1A'], positions_px['q1B'], positions_px['q2A']

    bubble_spacing_x = q1_B['x'] - q1_A['x']
    bubble_spacing_y = q2_A['y'] - q1_A['y']
    bubble_w, bubble_h = q1_A['w'], q1_A['h']
    
    col_start_x = q1_A['x']
    col_spacing_x = 0
    if len(questions_per_column) > 1:
        q_col2_A = positions_px[q_col2_label]
        col_spacing_x = q_col2_A['x'] - q1_A['x']

    zones_map = {
        'student_id': [math.ceil(v) for v in (student_id['x'], student_id['y'] - student_id['h'], student_id['w'], student_id['h'])],
        'student_name': [math.ceil(v) for v in (student_name['x'], student_name['y'] - student_name['h'], student_name['w'], student_name['h'])],
        'exam_type': [math.ceil(v) for v in (exam_type['x'], exam_type['y'] - exam_type['h'], exam_type['w'], exam_type['h'])],
        'col_start_x': math.ceil(col_start_x),
        'col_spacing_x': round(col_spacing_x, 2),
        'question_y_start': math.ceil(q1_A['y'] - bubble_h),
        'bubble_spacing_y': round(bubble_spacing_y, 2),
        'questions_per_column': questions_per_column,
        'bubble_w': math.ceil(bubble_w),
        'bubble_h': math.ceil(bubble_h),
        'bubble_spacing_x': round(bubble_spacing_x, 2),
    }

    if args.output_file:
        print(f"Saving zones map to: {args.output_file}")
        with open(args.output_file, 'w') as f:
            json.dump(zones_map, f, indent=4)
        print("File saved successfully.")
    else:
        print("\n--- Automatically Generated ZONES_MAP ---\n")
        print(json.dumps(zones_map, indent=4))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generates a JSON zones map from LaTeX auxiliary files.")
    parser.add_argument("aux_file", help="Path to the .aux file generated by LaTeX.")
    parser.add_argument("zones_file", help="Path to the custom .zones file for dimensions.")
    parser.add_argument("--output-file", help="(Optional) Path to the output .json file to save the zones map.")
    main(parser.parse_args())
