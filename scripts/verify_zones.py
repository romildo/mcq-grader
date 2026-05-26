# verify_zones.py
import cv2
import os
import json
import argparse
from PIL import Image, features
import sys
import omr_utils

# --- CONFIGURATION ---
PADDING_DEFAULT = 10

# --- HELPER FUNCTIONS ---


def draw_rect(image, rect, padding, color, thickness=3, label=None):
    """Draws one padded rectangle with an optional label."""
    x, y, w, h = [int(v) for v in rect]
    pt1 = (int(x) - padding, int(y) - padding)
    pt2 = (int(x + w) + padding, int(y + h) + padding)
    cv2.rectangle(image, pt1, pt2, color, thickness)
    if label:
        cv2.putText(
            image,
            label,
            (int(x), max(0, int(y) - 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            color,
            3,
        )


def cap_registration_padding(zones_map, requested_padding):
    """Caps registration padding so one digit rectangle does not overlap neighbors."""
    bubble_columns = zones_map.get('registration_bubbles')
    if not bubble_columns:
        return requested_padding

    gaps = []

    for column in bubble_columns:
        rects = sorted(column, key=lambda rect: rect[1])
        for current, nxt in zip(rects, rects[1:]):
            gap = int(nxt[1]) - (int(current[1]) + int(current[3]))
            if gap >= 0:
                gaps.append(gap)

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
            f"  -> Registration verification padding capped from {requested_padding}px "
            f"to {safe_padding}px to avoid neighboring bubble overlap."
        )
    return min(requested_padding, safe_padding)


def draw_zones(image, zones_map, padding, registration_padding=None):
    """Draws all mapped zones onto an image for visual verification."""
    P = padding
    if registration_padding is None:
        registration_padding = cap_registration_padding(zones_map, P)

    # Draw header zones (student_id, student_name, etc.)
    for key in ['student_id', 'student_name', 'exam_type']:
        if key in zones_map:
            draw_rect(image, zones_map[key], P, (0, 0, 255), thickness=4, label=key)  # Red

    # Draw bubble-encoded registration number zones, when present.
    if 'registration_bubbles' in zones_map:
        for digit_index, digit_bubbles in enumerate(zones_map['registration_bubbles'], start=1):
            for digit, rect in enumerate(digit_bubbles):
                draw_rect(image, rect, registration_padding, (0, 128, 0), thickness=3)  # Green
            first_rect = digit_bubbles[0] if digit_bubbles else None
            if first_rect:
                x, y, _w, _h = [int(v) for v in first_rect]
                cv2.putText(
                    image,
                    f'id_{digit_index}',
                    (x, max(0, y - 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 128, 0),
                    2,
                )

    # Dynamically draw answer bubbles for any number of columns.
    if 'questions_per_column' in zones_map:
        for col_idx, num_questions in enumerate(zones_map['questions_per_column']):
            col_x = zones_map['col_start_x'] + (col_idx * zones_map['col_spacing_x'])

            for i in range(num_questions):
                y_start = zones_map['question_y_start'] + (i * zones_map['bubble_spacing_y'])
                for j in range(5):  # 5 options (A-E)
                    x_start = col_x + (j * zones_map['bubble_spacing_x'])
                    w, h = zones_map['bubble_w'], zones_map['bubble_h']
                    draw_rect(image, [x_start, y_start, w, h], P, (255, 0, 0), thickness=3)  # Blue

    return image

# --- MAIN SCRIPT ---


def main(args):
    print(f"Loading zones map from '{args.zones_file}'...")
    with open(args.zones_file, 'r') as f:
        ZONES_MAP = json.load(f)

    print("Managing image cache...")
    template_image_path = omr_utils.manage_image_cache(args.template_pdf, args.images_dir, "template", is_template=True)[0]
    student_image_paths = omr_utils.manage_image_cache(args.student_sheets_pdf, args.images_dir, args.images_prefix)

    template_img = cv2.imread(template_image_path)
    verification_images_pil = []
    registration_padding = cap_registration_padding(ZONES_MAP, args.padding)

    for image_path in student_image_paths:
        filename = os.path.basename(image_path)
        print(f"Processing and drawing zones on: {filename}...")
        student_sheet = cv2.imread(image_path)

        aligned_sheet = omr_utils.align_image(student_sheet, template_img, ZONES_MAP)
        zoned_sheet = draw_zones(aligned_sheet.copy(), ZONES_MAP, args.padding, registration_padding)

        img_rgb = cv2.cvtColor(zoned_sheet, cv2.COLOR_BGR2RGB)
        verification_images_pil.append(Image.fromarray(img_rgb))

    if args.output.lower().endswith('.pdf'):
        print(f"\nCreating output PDF at '{args.output}'...")
        if verification_images_pil:
            # Pillow's PDF writer delegates RGB images to the JPEG save
            # handler. In some environments, notably minimal/Nix Python
            # closures, the JPEG plugin may not be registered yet.
            Image.init()
            if "JPEG" not in Image.SAVE or not features.check("jpg"):
                raise RuntimeError(
                    "Pillow JPEG support is unavailable. Rebuild/install Pillow "
                    "with libjpeg support, or save verification output as images."
                )
            verification_images_pil[0].save(
                args.output,
                "PDF",
                save_all=True,
                append_images=verification_images_pil[1:],
            )
        print("PDF created successfully.")
    else:
        print(f"\nSaving verification images to directory '{args.output}'...")
        os.makedirs(args.output, exist_ok=True)
        for i, pil_img in enumerate(verification_images_pil):
            base_name = os.path.basename(student_image_paths[i])
            output_filename = os.path.join(args.output, f"verification_{os.path.splitext(base_name)[0]}.jpg")
            pil_img.save(output_filename, "JPEG")
        print("Images saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visually verifies the zone mapping on answer sheets.")
    parser.add_argument("--zones-file", required=True, help="Path to the .json file with the zones map.")
    parser.add_argument("--images-dir", required=True, help="Directory to cache/read sheet images.")
    parser.add_argument("--output", required=True, help="Output path. If it ends with .pdf, a consolidated PDF is created. Otherwise, saves images to a directory of this name.")
    parser.add_argument("--template-pdf", help="[Optional] PDF of the blank answer sheet template.")
    parser.add_argument("--student-sheets-pdf", help="[Optional] PDF containing all student answer sheets.")
    parser.add_argument("--images-prefix", help="Prefix for the image files in the cache. Defaults to the PDF name.")
    parser.add_argument("--padding", type=int, default=PADDING_DEFAULT, help=f"Safety margin (padding) in pixels to draw around zones. Default: {PADDING_DEFAULT}")

    main(parser.parse_args())
