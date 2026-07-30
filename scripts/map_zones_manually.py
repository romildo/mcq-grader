# map_zones_manually.py
import cv2
import os
import argparse
import sys
import omr_utils

# --- Global variables for the mouse callback function ---
ref_point = []
cropping = False
image_for_drawing = None

def click_and_crop(event, x, y, flags, param):
    """
    Mouse callback function. Captures clicks to draw a rectangle
    and prints the coordinates (x, y, w, h) to the terminal.
    """
    global ref_point, cropping, image_for_drawing

    if event == cv2.EVENT_LBUTTONDOWN:
        ref_point = [(x, y)]
        cropping = True

    elif event == cv2.EVENT_LBUTTONUP:
        ref_point.append((x, y))
        cropping = False

        # Draw the rectangle on the image
        cv2.rectangle(image_for_drawing, ref_point[0], ref_point[1], (0, 255, 0), 3)
        cv2.imshow("Zone Mapper", image_for_drawing)
        
        # Calculate coordinates in (x, y, w, h) format
        x1, y1 = ref_point[0]
        x2, y2 = ref_point[1]
        
        start_x = min(x1, x2)
        start_y = min(y1, y2)
        width = abs(x1 - x2)
        height = abs(y1 - y2)
        
        # Print in a JSON-friendly format
        print(f"\"ZONE_NAME\": [{start_x}, {start_y}, {width}, {height}],")

def main(args):
    global image_for_drawing
    
    # Use the utility function to get the path to the template image
    # Note: We can also point it to the student sheets PDF to map on a real example
    pdf_to_map = args.student_sheets_pdf if args.student_sheets_pdf else args.template_pdf
    if not pdf_to_map:
        print("Error: You must provide either --template-pdf or --student-sheets-pdf.", file=sys.stderr)
        sys.exit(1)

    image_path = omr_utils.manage_image_cache(pdf_to_map, args.images_dir, is_template=True)[0]
    
    print(f"Loading image for mapping: {image_path}")
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not load image {image_path}", file=sys.stderr)
        sys.exit(1)

    clone = image.copy()
    image_for_drawing = image

    window_name = "Zone Mapper"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, click_and_crop)

    print("\n--- Zone Mapper ---")
    print("Instructions:")
    print("1. Click and drag to select a zone. Coordinates will be printed to the terminal.")
    print("2. Press 'r' to reset the drawn rectangles.")
    print("3. Press 'q' to quit.")
    print("---------------------\n")

    while True:
        cv2.imshow(window_name, image_for_drawing)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("r"):
            image_for_drawing = clone.copy()
        elif key == ord("q"):
            break
    
    cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Displays an image of a sheet for manual zone mapping.")
    parser.add_argument("--images-dir", required=True, help="Directory to cache/read the sheet image.")
    # Allow mapping on either the template or a student's sheet
    parser.add_argument("--template-pdf", help="[Optional] PDF of the template. Used if no student sheet is provided.")
    parser.add_argument("--student-sheets-pdf", help="[Optional] PDF of student sheets. Use this to map zones on a filled-out example.")
    
    args = parser.parse_args()
    main(args)