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

def align_image_using_markers(student_img, zones_map, template_img_shape):
    """High-precision alignment using 3 fiducial markers. Returns aligned image or None on failure."""
    print("  -> Attempting alignment using fiducial markers...")
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
        print(f"  -> Warning: Found {len(marker_contours)} markers instead of 3. Marker alignment failed.")
        return None
        
    centroids = []
    for cnt in marker_contours:
        M = cv2.moments(cnt)
        if M['m00'] == 0: continue
        centroids.append((int(M['m10']/M['m00']), int(M['m01']/M['m00'])))
        
    if len(centroids) != 3:
        print("  -> Warning: Failed to calculate centroids. Marker alignment failed.")
        return None
        
    centroids.sort(key=lambda p: p[0] + p[1])
    tl_found = centroids[0]
    if centroids[1][0] > centroids[2][0]:
        tr_found, bl_found = centroids[1], centroids[2]
    else:
        tr_found, bl_found = centroids[2], centroids[1]
        
    pts_src = np.float32([tl_found, tr_found, bl_found])
    h, w, _ = template_img_shape
    M = cv2.getAffineTransform(pts_src, pts_dst)
    aligned_img = cv2.warpAffine(student_img, M, (w, h))
    
    print("  -> Alignment by markers successful.")
    return aligned_img

def align_image(student_img, template_img, zones_map):
    """Orchestrator function: tries marker alignment first, then falls back to affine alignment."""
    if all(k in zones_map for k in ('marker_tl', 'marker_tr', 'marker_bl')):
        aligned_img = align_image_using_markers(student_img, zones_map, template_img.shape)
        if aligned_img is not None:
            return aligned_img
    
    return align_image_affine_fallback(template_img, student_img)