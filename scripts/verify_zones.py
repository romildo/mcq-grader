# verify_zones.py
import cv2
import os
import json
import argparse
from PIL import Image
from PIL import features
import sys
import omr_utils

# --- CONFIGURATION ---
PADDING_DEFAULT = 10

# --- HELPER FUNCTIONS ---

def draw_zones(image, zones_map, padding):
    """Draws all mapped zones onto an image for visual verification."""
    P = padding
    
    # Draw header zones (student_id, student_name, etc.)
    for key in ['student_id', 'student_name', 'exam_type']:
        if key in zones_map:
            x, y, w, h = [int(v) for v in zones_map[key]]
            cv2.rectangle(image, (x - P, y - P), (x + w + P, y + h + P), (0, 0, 255), 4) # Red
            cv2.putText(image, key, (x, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 255), 4)

    # --- NEW: Dynamically draw answer bubbles for any number of columns ---
    if 'questions_per_column' in zones_map:
        for col_idx, num_questions in enumerate(zones_map['questions_per_column']):
            col_x = zones_map['col_start_x'] + (col_idx * zones_map['col_spacing_x'])
            
            for i in range(num_questions):
                y_start = zones_map['question_y_start'] + (i * zones_map['bubble_spacing_y'])
                for j in range(5):  # 5 options (A-E)
                    x_start = col_x + (j * zones_map['bubble_spacing_x'])
                    w, h = zones_map['bubble_w'], zones_map['bubble_h']
                    
                    pt1 = (int(x_start) - P, int(y_start) - P)
                    pt2 = (int(x_start + w) + P, int(y_start + h) + P)
                    cv2.rectangle(image, pt1, pt2, (255, 0, 0), 3) # Blue

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
    
    for image_path in student_image_paths:
        filename = os.path.basename(image_path)
        print(f"Processing and drawing zones on: {filename}...")
        student_sheet = cv2.imread(image_path)
        
        aligned_sheet = omr_utils.align_image(student_sheet, template_img, ZONES_MAP)
        zoned_sheet = draw_zones(aligned_sheet.copy(), ZONES_MAP, args.padding)
        
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
            verification_images_pil[0].save(args.output, "PDF", save_all=True, append_images=verification_images_pil[1:])
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
