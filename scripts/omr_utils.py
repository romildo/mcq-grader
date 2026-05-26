# omr_utils.py
import os
import sys
import subprocess
import cv2
import numpy as np

def manage_image_cache(pdf_path, image_dir, image_prefix, is_template=False):
    """
    Manages the conversion of a PDF to 300 DPI PNG images or uses images from a cache.
    If the PDF is provided, it converts only if the images do not already exist in the cache.
    Returns a list with the full paths of the images.
    """
    os.makedirs(image_dir, exist_ok=True)
    if not image_prefix and pdf_path:
        image_prefix = os.path.splitext(os.path.basename(pdf_path))[0]
    elif not image_prefix:
        raise ValueError("Image prefix is required when the PDF is not provided.")

    image_list = sorted([
        os.path.join(image_dir, f) for f in os.listdir(image_dir)
        if f.startswith(image_prefix) and f.endswith('.png')
    ])

    if pdf_path and not image_list:
        print(f"  -> No cached images found. Converting PDF to images with prefix '{image_prefix}'...")
        output_prefix_path = os.path.join(image_dir, image_prefix)
        cmd = ['pdftoppm', '-png', '-r', '300']
        if is_template:
            cmd.extend(['-f', '1', '-l', '1'])
        cmd.extend([pdf_path, output_prefix_path])
        subprocess.run(cmd, check=True)
        image_list = sorted([
            os.path.join(image_dir, f) for f in os.listdir(image_dir)
            if f.startswith(image_prefix) and f.endswith('.png')
        ])
    elif image_list:
         print(f"  -> Found images in cache. Skipping conversion.")

    if not image_list:
        print(f"ERROR: No images found in directory '{image_dir}' with prefix '{image_prefix}'.", file=sys.stderr)
        sys.exit(1)
    return image_list

def align_image_affine_fallback(template_img, student_img):
    """Fallback alignment method using features and a more robust affine transformation."""
    print("  -> Using affine feature-based alignment (fallback)...")
    try:
        template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
        student_gray = cv2.cvtColor(student_img, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(nfeatures=2000, scoreType=cv2.ORB_FAST_SCORE)
        kp1, des1 = orb.detectAndCompute(template_gray, None)
        kp2, des2 = orb.detectAndCompute(student_gray, None)

        if des1 is None or des2 is None or len(des1) < 50 or len(des2) < 50:
            print("Warning: Insufficient feature points. Skipping alignment.")
            return student_img

        bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = bf.knnMatch(des1, des2, k=2)
        
        good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]

        if len(good_matches) < 10:
            print("Warning: Insufficient matches. Skipping alignment.")
            return student_img
            
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 2)
        
        M, _ = cv2.estimateAffinePartial2D(dst_pts, src_pts, method=cv2.RANSAC)
        
        if M is None:
            print("Warning: Could not estimate affine transform. Skipping alignment.")
            return student_img

        h, w = template_img.shape[:2]
        return cv2.warpAffine(student_img, M, (w, h))

    except cv2.error as e:
        print(f"OpenCV error during affine fallback: {e}. Returning original image.")
        return student_img

def _corner_search_region(image_shape, corner, search_fraction=0.25):
    """Returns the ROI bounds used to look for one corner fiducial marker."""
    height, width = image_shape[:2]
    region_w = max(1, int(width * search_fraction))
    region_h = max(1, int(height * search_fraction))

    if corner == 'tl':
        return 0, 0, region_w, region_h
    if corner == 'tr':
        return width - region_w, 0, region_w, region_h
    if corner == 'bl':
        return 0, height - region_h, region_w, region_h

    raise ValueError(f"Unsupported fiducial corner: {corner}")


def _corner_reference_point(region_w, region_h, corner):
    """Returns the ideal point inside a corner ROI for distance scoring."""
    if corner == 'tl':
        return np.array([0.0, 0.0])
    if corner == 'tr':
        return np.array([float(region_w), 0.0])
    if corner == 'bl':
        return np.array([0.0, float(region_h)])

    raise ValueError(f"Unsupported fiducial corner: {corner}")


def detect_corner_fiducial(image, corner, search_fraction=0.25, threshold=100):
    """Detects one black square fiducial marker near a page corner.

    The answer sheet already prints large black squares near the top-left,
    top-right, and bottom-left corners. This detector intentionally looks only
    near the requested corner so ordinary text, filled answer bubbles, and the
    registration grid are unlikely to be selected as markers.
    """
    image_h, image_w = image.shape[:2]
    x0, y0, region_w, region_h = _corner_search_region(
        image.shape,
        corner,
        search_fraction=search_fraction,
    )

    roi = image[y0:y0 + region_h, x0:x0 + region_w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

    # Close tiny antialiasing gaps in the printed/scanned black square without
    # merging distant text into the marker candidate.
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_page_dim = min(image_w, image_h)
    min_marker_size = max(15, int(min_page_dim * 0.008))
    max_marker_size = max(80, int(min_page_dim * 0.08))
    expected = _corner_reference_point(region_w, region_h, corner)

    best_candidate = None
    best_score = None

    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)

        if w < min_marker_size or h < min_marker_size:
            continue
        if w > max_marker_size or h > max_marker_size:
            continue

        aspect_ratio = w / float(h)
        if not 0.65 <= aspect_ratio <= 1.35:
            continue

        fill_ratio = area / float(w * h)
        if fill_ratio < 0.55:
            continue

        center_local = np.array([x + w / 2.0, y + h / 2.0])
        distance_to_corner = np.linalg.norm(center_local - expected)

        # Prefer filled square-like components near the requested page corner.
        score = (area * fill_ratio) - (2.0 * distance_to_corner)

        if best_score is None or score > best_score:
            best_score = score
            best_candidate = {
                'center': (x0 + center_local[0], y0 + center_local[1]),
                'bbox': (x0 + x, y0 + y, w, h),
                'area': area,
                'fill_ratio': fill_ratio,
                'score': score,
            }

    return best_candidate


def detect_fiducial_markers(image, image_label="image"):
    """Detects the TL, TR, and BL page fiducials directly from an image."""
    markers = {}

    for corner in ('tl', 'tr', 'bl'):
        marker = detect_corner_fiducial(image, corner)
        if marker is None:
            print(f"  -> Warning: Could not detect {corner.upper()} fiducial marker in {image_label}.")
            return None
        markers[corner] = marker['center']

    return markers


def align_image_using_detected_markers(student_img, template_img):
    """Aligns a scanned sheet to the template using directly detected fiducials."""
    print("  -> Attempting alignment using detected fiducial markers...")

    template_markers = detect_fiducial_markers(template_img, "template image")
    if template_markers is None:
        print("  -> Warning: Template fiducial detection failed.")
        return None

    student_markers = detect_fiducial_markers(student_img, "student image")
    if student_markers is None:
        print("  -> Warning: Student fiducial detection failed.")
        return None

    pts_src = np.float32([
        student_markers['tl'],
        student_markers['tr'],
        student_markers['bl'],
    ])
    pts_dst = np.float32([
        template_markers['tl'],
        template_markers['tr'],
        template_markers['bl'],
    ])

    transform = cv2.getAffineTransform(pts_src, pts_dst)
    height, width = template_img.shape[:2]
    aligned_img = cv2.warpAffine(student_img, transform, (width, height))

    print("  -> Alignment by detected fiducial markers successful.")
    return aligned_img


def _has_valid_marker_zones(zones_map):
    """Returns True only when legacy marker zones have non-zero dimensions."""
    try:
        for key in ('marker_tl', 'marker_tr', 'marker_bl'):
            zone = zones_map[key]
            if len(zone) != 4 or zone[2] <= 0 or zone[3] <= 0:
                return False
        return True
    except (KeyError, TypeError):
        return False


def align_image_using_markers(student_img, zones_map, template_img_shape):
    """Legacy marker alignment using marker coordinates from the zone map.

    Newer sheets are aligned by detecting printed markers directly from the
    template and scanned images. This legacy path is kept for compatibility with
    zone maps that already contain valid marker rectangles.
    """
    print("  -> Attempting alignment using fiducial marker zones...")
    try:
        tl_ideal = zones_map['marker_tl']
        tr_ideal = zones_map['marker_tr']
        bl_ideal = zones_map['marker_bl']
        pts_dst = np.float32([
            [tl_ideal[0] + tl_ideal[2]/2, tl_ideal[1] + tl_ideal[3]/2],
            [tr_ideal[0] + tr_ideal[2]/2, tr_ideal[1] + tr_ideal[3]/2],
            [bl_ideal[0] + bl_ideal[2]/2, bl_ideal[1] + bl_ideal[3]/2]
        ])
    except KeyError:
        return None

    gray = cv2.cvtColor(student_img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    marker_contours = []
    min_area = (tl_ideal[2] * tl_ideal[3]) * 0.5
    max_area = (tl_ideal[2] * tl_ideal[3]) * 1.5
    for cnt in contours:
        if min_area < cv2.contourArea(cnt) < max_area:
            marker_contours.append(cnt)

    if len(marker_contours) != 3:
        print(f"  -> Warning: Found {len(marker_contours)} markers instead of 3. Marker-zone alignment failed.")
        return None

    centroids = []
    for cnt in marker_contours:
        M = cv2.moments(cnt)
        if M['m00'] == 0:
            continue
        centroids.append((int(M['m10']/M['m00']), int(M['m01']/M['m00'])))

    if len(centroids) != 3:
        print("  -> Warning: Failed to calculate centroids. Marker-zone alignment failed.")
        return None

    centroids.sort(key=lambda p: p[0] + p[1])
    tl_found = centroids[0]
    if centroids[1][0] > centroids[2][0]:
        tr_found, bl_found = centroids[1], centroids[2]
    else:
        tr_found, bl_found = centroids[2], centroids[1]

    pts_src = np.float32([tl_found, tr_found, bl_found])
    h, w, _ = template_img_shape
    transform = cv2.getAffineTransform(pts_src, pts_dst)
    aligned_img = cv2.warpAffine(student_img, transform, (w, h))

    print("  -> Alignment by marker zones successful.")
    return aligned_img


def align_image(student_img, template_img, zones_map):
    """Aligns a scanned answer sheet to the template image.

    The primary path detects the three printed corner fiducials directly in both
    the template and scanned sheet, then computes a full affine transform. This
    corrects translation, rotation, independent X/Y scaling, and shear from the
    scanner. If direct marker detection fails, legacy marker-zone alignment and
    feature-based alignment remain available as fallbacks.
    """
    aligned_img = align_image_using_detected_markers(student_img, template_img)
    if aligned_img is not None:
        return aligned_img

    if _has_valid_marker_zones(zones_map):
        aligned_img = align_image_using_markers(student_img, zones_map, template_img.shape)
        if aligned_img is not None:
            return aligned_img

    return align_image_affine_fallback(template_img, student_img)
