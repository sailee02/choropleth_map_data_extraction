from typing import Optional, Tuple, List
import cv2
import numpy as np
import geopandas as gpd
from shapely.affinity import scale, translate, rotate
from shapely.geometry import Polygon, Point
from PIL import Image, ImageDraw

def fit_gdf_to_bbox_pixels(gdf: gpd.GeoDataFrame, bbox: Tuple[int, int, int, int], polygon: Optional[List[Tuple[int, int]]]=None, keep_aspect: bool=False, inset_px: int=6):
    x0, y0, x1, y1 = bbox
    if inset_px > 0:
        x0 += inset_px
        y0 += inset_px
        x1 -= inset_px
        y1 -= inset_px
    W = max(1, x1 - x0)
    H = max(1, y1 - y0)
    minx, miny, maxx, maxy = gdf.total_bounds
    w_src = max(maxx - minx, 1e-09)
    h_src = max(maxy - miny, 1e-09)
    sx = W / w_src
    sy = H / h_src
    if keep_aspect:
        s = min(sx, sy)
        sx = sy = s
    scaled_w = w_src * sx
    scaled_h = h_src * sy
    if keep_aspect:
        dx_final = x0 + (W - scaled_w) / 2.0 - minx * sx
        dy_final = y0 + H / 2.0 + (maxy + miny) * sy / 2.0
    else:
        dx_final = x0 - minx * sx
        dy_final = y0 - -maxy * sy

    def _affine(geom):
        g = scale(geom, xfact=sx, yfact=-sy, origin=(0, 0))
        g = translate(g, xoff=dx_final, yoff=dy_final)
        return g
    gdf_px = gdf.copy()
    gdf_px.geometry = gdf_px.geometry.apply(_affine)
    if polygon and len(polygon) >= 3:
        clip_poly = Polygon(polygon)
        gdf_px.geometry = gdf_px.geometry.intersection(clip_poly)
    return gdf_px

def _extract_shapefile_edge_points(gdf_px: gpd.GeoDataFrame, n_points: int=None) -> np.ndarray:
    edge_points = []
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('LineString', 'MultiLineString'):
            if geom.geom_type == 'LineString':
                edge_points.extend(list(geom.coords))
            else:
                for line in geom.geoms:
                    edge_points.extend(list(line.coords))
            continue
        polygons = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
        for poly in polygons:
            coords = list(poly.exterior.coords)
            if len(coords) < 3:
                continue
            edge_points.extend(coords)
            if hasattr(poly, 'interiors'):
                for interior in poly.interiors:
                    interior_coords = list(interior.coords)
                    if len(interior_coords) >= 3:
                        edge_points.extend(interior_coords)
    if not edge_points:
        return np.array([])
    arr = np.array(edge_points)
    if n_points and len(arr) > n_points:
        indices = np.linspace(0, len(arr) - 1, n_points, dtype=int)
        arr = arr[indices]
    return arr

def _detect_image_edges(image_path: str, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    img = cv2.imread(str(image_path))
    if img is None:
        return np.array([])
    x0, y0, x1, y1 = bbox
    cropped = img[y0:y1, x0:x1]
    if cropped.size == 0:
        return np.array([])
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges_low = cv2.Canny(blur, 10, 30)
    edges_mid = cv2.Canny(blur, 30, 80)
    edges_high = cv2.Canny(blur, 50, 150)
    edges_canny = cv2.bitwise_or(edges_low, cv2.bitwise_or(edges_mid, edges_high))
    lab = cv2.cvtColor(cropped, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    a_channel = lab[:, :, 1]
    b_channel = lab[:, :, 2]
    sobel_l_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_l_y = cv2.Sobel(l_channel, cv2.CV_64F, 0, 1, ksize=3)
    sobel_a_x = cv2.Sobel(a_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_a_y = cv2.Sobel(a_channel, cv2.CV_64F, 0, 1, ksize=3)
    sobel_b_x = cv2.Sobel(b_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_b_y = cv2.Sobel(b_channel, cv2.CV_64F, 0, 1, ksize=3)
    gradient_l = np.sqrt(sobel_l_x ** 2 + sobel_l_y ** 2)
    gradient_a = np.sqrt(sobel_a_x ** 2 + sobel_a_y ** 2)
    gradient_b = np.sqrt(sobel_b_x ** 2 + sobel_b_y ** 2)
    gradient_magnitude = gradient_l + gradient_a + gradient_b
    if gradient_magnitude.max() > 0:
        gradient_norm = np.uint8(255 * gradient_magnitude / gradient_magnitude.max())
        _, gradient_edges_high = cv2.threshold(gradient_norm, 20, 255, cv2.THRESH_BINARY)
        _, gradient_edges_low = cv2.threshold(gradient_norm, 10, 255, cv2.THRESH_BINARY)
        gradient_edges = cv2.bitwise_or(gradient_edges_high, gradient_edges_low)
    else:
        gradient_edges = np.zeros_like(gray, dtype=np.uint8)
    b, g, r = cv2.split(cropped)
    color_diff_x = np.abs(np.diff(cropped.astype(np.int16), axis=1, prepend=cropped[:, 0:1, :]))
    color_diff_y = np.abs(np.diff(cropped.astype(np.int16), axis=0, prepend=cropped[0:1, :, :]))
    color_boundary = np.sum(color_diff_x, axis=2) + np.sum(color_diff_y, axis=2)
    color_boundary_norm = np.uint8(255 * np.clip(color_boundary / (color_boundary.max() + 1), 0, 1))
    _, color_boundary_edges = cv2.threshold(color_boundary_norm, 30, 255, cv2.THRESH_BINARY)
    gradient_edges = cv2.bitwise_or(gradient_edges, color_boundary_edges)
    inverted = 255 - gray
    adaptive = cv2.adaptiveThreshold(inverted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    dark_lines = cv2.Canny(adaptive, 50, 150)
    edges = cv2.bitwise_or(edges_canny, gradient_edges)
    edges = cv2.bitwise_or(edges, dark_lines)
    kernel_gradient = np.ones((2, 2), np.uint8)
    gradient_edges_dilated = cv2.dilate(gradient_edges, kernel_gradient, iterations=1)
    edges = cv2.bitwise_or(edges, gradient_edges_dilated)
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    edges = cv2.dilate(edges, kernel, iterations=1)
    y_coords, x_coords = np.where(edges > 0)
    if len(x_coords) == 0:
        return np.array([])
    edge_points = np.column_stack([x_coords + x0, y_coords + y0])
    if len(edge_points) > 20000:
        indices = np.linspace(0, len(edge_points) - 1, 20000, dtype=int)
        edge_points = edge_points[indices]
    return edge_points

def refine_alignment_with_edge_matching(gdf_px: gpd.GeoDataFrame, image_path: str, bbox: Tuple[int, int, int, int], max_iterations: int=5, is_alaska_hawaii: bool=False) -> gpd.GeoDataFrame:
    from scipy.spatial import cKDTree
    from shapely.affinity import translate, rotate
    shapefile_edges = _extract_shapefile_edge_points(gdf_px, n_points=None)
    if len(shapefile_edges) == 0:
        print('WARNING: No shapefile edges extracted!')
        return gdf_px
    print(f'Extracted {len(shapefile_edges)} shapefile edge points')
    image_edges = _detect_image_edges(image_path, bbox)
    if len(image_edges) == 0:
        print('WARNING: No image edges detected!')
        return gdf_px
    print(f'Detected {len(image_edges)} image edge points (county borders from color changes)')
    image_tree = cKDTree(image_edges)
    base_gdf = gdf_px.copy()
    best_gdf = base_gdf.copy()
    best_score = float('inf')
    base_sample = _extract_shapefile_edge_points(base_gdf, n_points=min(1000, len(shapefile_edges)))
    if len(base_sample) > 0:
        base_distances, _ = image_tree.query(base_sample, k=1)
        base_valid = base_distances[base_distances < 30]
        if len(base_valid) > len(base_sample) * 0.05:
            base_score_val = np.mean(base_valid)
            base_match_ratio = len(base_valid) / len(base_sample)
            baseline_score = base_score_val / (base_match_ratio + 0.1)
            print(f'  Baseline alignment score (no rotation): {baseline_score:.2f}')
        else:
            baseline_score = float('inf')
    else:
        baseline_score = float('inf')
    x0, y0, x1, y1 = bbox
    w, h = (x1 - x0, y1 - y0)
    center_x, center_y = (x0 + w / 2, y0 + h / 2)
    dx_range = np.linspace(-w * 0.3, w * 0.3, 11)
    dy_range = np.linspace(-h * 0.3, h * 0.3, 11)
    sx_range = np.linspace(0.7, 1.3, 11)
    sy_range = np.linspace(0.7, 1.3, 11)
    if len(shapefile_edges) > 2000:
        sample_indices = np.linspace(0, len(shapefile_edges) - 1, 2000, dtype=int)
        shapefile_sample = shapefile_edges[sample_indices]
    else:
        shapefile_sample = shapefile_edges
    print(f'Using {len(shapefile_sample)} shapefile points for matching')
    early_exit = False
    iteration_count = 0
    print(f'  🔄 Starting iterative rotation search...')
    print(f'  Algorithm: Rotate → Check alignment → Repeat until perfect')
    if is_alaska_hawaii:
        print(f'  ALASKA/HAWAII: Searching ±180° rotation with FINE steps')
        print(f'  Alaska/Hawaii often need stretching/shrinking AND rotation - checking EVERYTHING')
        rotation_angles = np.linspace(-180.0, 180.0, 361)
    else:
        print(f'  CONUS: Searching ±180° rotation')
        rotation_angles = np.linspace(-180.0, 180.0, 73)
    if is_alaska_hawaii:
        print(f'  Alaska/Hawaii: Allowing ±50% stretching/shrinking (independent X/Y scaling)')
        dx_range = np.linspace(-w * 0.5, w * 0.5, 15)
        dy_range = np.linspace(-h * 0.5, h * 0.5, 15)
        sx_range = np.linspace(0.5, 1.5, 15)
        sy_range = np.linspace(0.5, 1.5, 15)
    else:
        dx_range = np.linspace(-w * 0.3, w * 0.3, 11)
        dy_range = np.linspace(-h * 0.3, h * 0.3, 11)
        sx_range = np.linspace(0.7, 1.3, 11)
        sy_range = np.linspace(0.7, 1.3, 11)
    best_score = float('inf')
    best_gdf = base_gdf.copy()
    best_angle = 0.0
    print(f'\n  Iterating through {len(rotation_angles)} rotation angles...')
    print(f'  For each angle: Try rotation → Check alignment with edge detection → Keep if better')
    total_iterations = len(rotation_angles) * len(sx_range) * len(sy_range) * len(dx_range) * len(dy_range)
    print(f'  Total iterations: {total_iterations}')
    iteration_count = 0
    for angle_idx, angle in enumerate(rotation_angles):
        if early_exit:
            break
        if is_alaska_hawaii:
            if angle_idx % 30 == 0:
                print(f'    Testing rotation {angle:.1f}° ({angle_idx + 1}/{len(rotation_angles)})...')
        elif angle_idx % 10 == 0:
            print(f'    Testing rotation {angle:.1f}° ({angle_idx + 1}/{len(rotation_angles)})...')
        cos_a = np.cos(np.radians(angle))
        sin_a = np.sin(np.radians(angle))
        for sx in sx_range:
            if early_exit:
                break
            for sy in sy_range:
                if early_exit:
                    break
                for dx in dx_range:
                    if early_exit:
                        break
                    for dy in dy_range:
                        iteration_count += 1
                        transformed_sample = shapefile_sample.copy().astype(float)
                        x_rel = transformed_sample[:, 0] - center_x
                        y_rel = transformed_sample[:, 1] - center_y
                        transformed_sample[:, 0] = x_rel * cos_a - y_rel * sin_a + center_x
                        transformed_sample[:, 1] = x_rel * sin_a + y_rel * cos_a + center_y
                        transformed_sample[:, 0] = (transformed_sample[:, 0] - center_x) * sx + center_x
                        transformed_sample[:, 1] = (transformed_sample[:, 1] - center_y) * sy + center_y
                        transformed_sample[:, 0] += dx
                        transformed_sample[:, 1] += dy
                        distances, _ = image_tree.query(transformed_sample, k=1)
                        match_tolerance = 50 if is_alaska_hawaii else 40
                        valid_matches = distances[distances < match_tolerance]
                        match_threshold = 0.01 if is_alaska_hawaii else 0.02
                        if len(valid_matches) > len(shapefile_sample) * match_threshold:
                            score = np.mean(valid_matches)
                            match_ratio = len(valid_matches) / len(shapefile_sample)
                            combined_score = score / (match_ratio + 0.1)
                            should_accept = combined_score < best_score or (best_score == float('inf') and combined_score < baseline_score * 2.0) or (best_score == float('inf') and baseline_score == float('inf') and (len(valid_matches) > len(shapefile_sample) * 0.05))
                            if should_accept:
                                best_score = combined_score
                                test_gdf = base_gdf.copy()
                                test_gdf['geometry'] = test_gdf.geometry.apply(lambda g: translate(scale(rotate(g, angle=angle, origin=(center_x, center_y)), xfact=sx, yfact=sy, origin=(center_x, center_y)), xoff=dx, yoff=dy))
                                best_gdf = test_gdf
                                best_angle = angle
                                stretch_info = ''
                                if abs(sx - sy) > 0.05:
                                    stretch_info = f' [STRETCHED: X={sx:.3f}, Y={sy:.3f}]'
                                print(f'      ✓ Better alignment found: angle={angle:.1f}°, score={combined_score:.2f}, matches={match_ratio:.1%}, scale=({sx:.3f},{sy:.3f}), trans=({dx:.1f},{dy:.1f}){stretch_info}')
                                perfect_threshold = 1.5 if is_alaska_hawaii else 2.0
                                perfect_match_ratio = 0.5 if is_alaska_hawaii else 0.4
                                if combined_score < perfect_threshold and match_ratio > perfect_match_ratio:
                                    print(f'      ✓✓✓ PERFECT ALIGNMENT FOUND! ✓✓✓')
                                    print(f'      Score: {combined_score:.2f}, Match ratio: {match_ratio:.1%}, Angle: {angle:.1f}°')
                                    print(f'      Scale: X={sx:.3f}, Y={sy:.3f} (stretching/shrinking applied)')
                                    early_exit = True
                                    break
                        if early_exit:
                            break
                    if early_exit:
                        break
                if early_exit:
                    break
            if early_exit:
                break
    print(f'\n  Iteration complete: Tested {iteration_count} combinations')
    if best_score < float('inf'):
        print(f'  Best alignment: score={best_score:.2f}, angle={best_angle:.1f}°')
    else:
        print(f'  ⚠️  No valid alignment found in iteration')
    if best_score < float('inf'):
        print(f'\n  Stage 2: Fine-tuning around best rotation ({best_angle:.1f}°)...')
        print(f'  Refining scale (stretching/shrinking) and position until perfect...')
        if best_score < 15.0:
            stage2_base = best_gdf.copy()
            stage2_sample = _extract_shapefile_edge_points(stage2_base, n_points=2000)
            if is_alaska_hawaii:
                fine_dx_range = np.linspace(-w * 0.05, w * 0.05, 7)
                fine_dy_range = np.linspace(-h * 0.05, h * 0.05, 7)
                fine_sx_range = np.linspace(0.95, 1.05, 7)
                fine_sy_range = np.linspace(0.95, 1.05, 7)
                fine_rotation_range = np.linspace(best_angle - 3.0, best_angle + 3.0, 7)
            else:
                fine_dx_range = np.linspace(-w * 0.02, w * 0.02, 5)
                fine_dy_range = np.linspace(-h * 0.02, h * 0.02, 5)
                fine_sx_range = np.linspace(0.98, 1.02, 5)
                fine_sy_range = np.linspace(0.98, 1.02, 5)
                fine_rotation_range = np.linspace(best_angle - 2.0, best_angle + 2.0, 5)
            for angle in fine_rotation_range:
                cos_a = np.cos(np.radians(angle))
                sin_a = np.sin(np.radians(angle))
                for sx in fine_sx_range:
                    for sy in fine_sy_range:
                        for dx in fine_dx_range:
                            for dy in fine_dy_range:
                                fine_sample = stage2_sample.copy().astype(float)
                                x_rel = fine_sample[:, 0] - center_x
                                y_rel = fine_sample[:, 1] - center_y
                                fine_sample[:, 0] = x_rel * cos_a - y_rel * sin_a + center_x
                                fine_sample[:, 1] = x_rel * sin_a + y_rel * cos_a + center_y
                                fine_sample[:, 0] = (fine_sample[:, 0] - center_x) * sx + center_x
                                fine_sample[:, 1] = (fine_sample[:, 1] - center_y) * sy + center_y
                                fine_sample[:, 0] += dx
                                fine_sample[:, 1] += dy
                                distances, _ = image_tree.query(fine_sample, k=1)
                                fine_match_tolerance = 50 if is_alaska_hawaii else 30
                                valid_matches = distances[distances < fine_match_tolerance]
                                fine_match_threshold = 0.02 if is_alaska_hawaii else 0.05
                                if len(valid_matches) > len(fine_sample) * fine_match_threshold:
                                    score = np.mean(valid_matches)
                                    match_ratio = len(valid_matches) / len(fine_sample)
                                    combined_score = score / (match_ratio + 0.1)
                                    if combined_score < best_score:
                                        best_score = combined_score
                                        test_gdf = stage2_base.copy()
                                        test_gdf['geometry'] = test_gdf.geometry.apply(lambda g: translate(scale(rotate(g, angle=angle, origin=(center_x, center_y)), xfact=sx, yfact=sy, origin=(center_x, center_y)), xoff=dx, yoff=dy))
                                        best_gdf = test_gdf
                                        print(f'  Fine-tune improved: score={combined_score:.2f}, matches={match_ratio:.1%}, angle={angle:.1f}°')
    if best_score < float('inf'):
        rotation_applied = best_gdf is not base_gdf
        if rotation_applied:
            print(f'\n  ✓✓✓ ROTATION APPLIED ✓✓✓')
        else:
            print(f'\n  ⚠️  WARNING: No rotation was applied - best match found without rotation')
            print(f"  This might mean the map doesn't need rotation, OR rotation search didn't find a match")
            print(f'  Consider checking if the map is actually rotated')
        print(f'  Final alignment score: {best_score:.2f}')
        if baseline_score < float('inf'):
            if best_score < baseline_score:
                improvement = (baseline_score - best_score) / baseline_score * 100 if baseline_score > 0 else 0
                print(f'  ✓ Alignment improved by {improvement:.1f}% (baseline: {baseline_score:.2f})')
            else:
                print(f'  ⚠️  Final score ({best_score:.2f}) vs baseline ({baseline_score:.2f})')
        else:
            print(f'  ✓ Using best alignment found')
        return best_gdf
    if baseline_score < float('inf'):
        print(f'\n  No rotation found in grid search, trying simple rotations with wider tolerance...')
        fallback_best = None
        fallback_best_score = baseline_score
        for test_angle in [-20, -15, -10, -5, 5, 10, 15, 20]:
            test_gdf = base_gdf.copy()
            test_gdf['geometry'] = test_gdf.geometry.apply(lambda g: rotate(g, angle=test_angle, origin=(center_x, center_y)))
            test_sample = _extract_shapefile_edge_points(test_gdf, n_points=500)
            if len(test_sample) > 0:
                test_distances, _ = image_tree.query(test_sample, k=1)
                test_valid = test_distances[test_distances < 50]
                if len(test_valid) > len(test_sample) * 0.03:
                    test_score = np.mean(test_valid)
                    test_ratio = len(test_valid) / len(test_sample)
                    test_combined = test_score / (test_ratio + 0.1)
                    if test_combined < fallback_best_score * 1.2:
                        print(f'    ✓ Found rotation at {test_angle}°: score={test_combined:.2f} (baseline: {baseline_score:.2f})')
                        fallback_best = test_gdf
                        fallback_best_score = test_combined
        if fallback_best is not None:
            print(f'  ✓✓✓ FALLBACK ROTATION APPLIED ✓✓✓')
            print(f'  Applied rotation with score: {fallback_best_score:.2f}')
            return fallback_best
    if is_alaska_hawaii:
        print(f'\n  ⚠️  Edge-based rotation search found no matches, forcing FULL ±180° rotation attempt...')
        print(f'  Trying rotation angles: ±180° in 5° steps...')
        rotation_range_full = np.linspace(-180, 180, 73)
    else:
        print(f'\n  ⚠️  Edge-based rotation search found no matches, forcing rotation attempt...')
        print(f'  Trying rotation angles: ±45° in 5° steps...')
        rotation_range_full = np.linspace(-45, 45, 19)
    force_best_gdf = None
    force_best_score = float('inf')
    force_best_angle = 0
    for test_angle in rotation_range_full:
        test_gdf = base_gdf.copy()
        test_gdf['geometry'] = test_gdf.geometry.apply(lambda g: rotate(g, angle=test_angle, origin=(center_x, center_y)))
        test_sample = _extract_shapefile_edge_points(test_gdf, n_points=min(1000, len(shapefile_edges)))
        if len(test_sample) > 0:
            test_distances, _ = image_tree.query(test_sample, k=1)
            test_valid = test_distances[test_distances < 100]
            if len(test_valid) > len(test_sample) * 0.01:
                test_score = np.mean(test_valid)
                test_ratio = len(test_valid) / len(test_sample)
                test_combined = test_score / (test_ratio + 0.1)
                if test_combined < force_best_score:
                    force_best_score = test_combined
                    force_best_gdf = test_gdf
                    force_best_angle = test_angle
    if force_best_gdf is not None:
        print(f'  ✓✓✓ FORCED ROTATION APPLIED ✓✓✓')
        print(f'  Applied rotation of {force_best_angle:.1f}° (score: {force_best_score:.2f})')
        return force_best_gdf
    print(f'\n  ❌ No rotation could be applied - edge detection completely failed')
    print(f"  Baseline score: {baseline_score:.2f if baseline_score < float(\'inf\') else \'N/A\'}")
    print(f'  Returning original geometry (unrotated)')
    return gdf_px

def _edge_overlap_score(image_path: str, gdf_px: gpd.GeoDataFrame) -> float:
    img = cv2.imread(str(image_path))
    if img is None:
        return 0.0
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges_low = cv2.Canny(blur, 10, 30)
    edges_mid = cv2.Canny(blur, 30, 80)
    edges_high = cv2.Canny(blur, 50, 150)
    edges_canny = cv2.bitwise_or(edges_low, cv2.bitwise_or(edges_mid, edges_high))
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    sobel_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(l_channel, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
    if gradient_magnitude.max() > 0:
        gradient_norm = np.uint8(255 * gradient_magnitude / gradient_magnitude.max())
        _, gradient_edges = cv2.threshold(gradient_norm, 15, 255, cv2.THRESH_BINARY)
    else:
        gradient_edges = np.zeros_like(gray, dtype=np.uint8)
    inverted = 255 - gray
    adaptive = cv2.adaptiveThreshold(inverted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    dark_lines = cv2.Canny(adaptive, 50, 150)
    edges = cv2.bitwise_or(edges_canny, gradient_edges)
    edges = cv2.bitwise_or(edges, dark_lines)
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    edges = cv2.dilate(edges, kernel, iterations=1)
    line = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(line)
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
        for poly in polys:
            coords = list(poly.exterior.coords)
            if len(coords) >= 2:
                draw.line(coords, fill=255, width=1)
    line_arr = np.array(line)
    overlap = (line_arr > 0) & (edges > 0)
    denom = max(1, (line_arr > 0).sum())
    return float(overlap.sum()) / float(denom)

def fit_with_autoinset(shp: gpd.GeoDataFrame, image_path: str, bbox: Tuple[int, int, int, int], polygon: Optional[List[Tuple[int, int]]]=None, keep_aspect: bool=True, inset_candidates: Tuple[int, ...]=(4, 6, 8, 10)) -> Tuple[gpd.GeoDataFrame, float, int]:
    best = (None, -1.0, None)
    for inset in inset_candidates:
        gdf_px = fit_gdf_to_bbox_pixels(shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=inset)
        if polygon and len(polygon) >= 3:
            clip_poly = Polygon(polygon)
        else:
            x0, y0, x1, y1 = bbox
            clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        gdf_px_clip = gdf_px.copy()
        gdf_px_clip['geometry'] = gdf_px_clip.geometry.intersection(clip_poly)
        gdf_px_clip = gdf_px_clip[~gdf_px_clip.geometry.is_empty]
        if len(gdf_px_clip) == 0:
            continue
        s = _edge_overlap_score(image_path, gdf_px_clip)
        if s > best[1]:
            best = (gdf_px_clip, s, inset)
    if best[0] is None:
        default_inset = inset_candidates[len(inset_candidates) // 2]
        gdf_px = fit_gdf_to_bbox_pixels(shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=default_inset)
        if polygon and len(polygon) >= 3:
            clip_poly = Polygon(polygon)
        else:
            x0, y0, x1, y1 = bbox
            clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        gdf_px_clip = gdf_px.copy()
        gdf_px_clip['geometry'] = gdf_px_clip.geometry.intersection(clip_poly)
        return (gdf_px_clip, 0.0, default_inset)
    return best

def render_overlay_full_image(image_path: str, shp: gpd.GeoDataFrame, bbox: Tuple[int, int, int, int], polygon: Optional[List[Tuple[int, int]]]=None, inset_px: int=6, keep_aspect: bool=True, out_path: str='overlay.png') -> str:
    try:
        if shp.crs is None:
            shp = shp.set_crs(4269, allow_override=True)
        shp = shp.to_crs(5070)
    except Exception:
        pass
    gdf_px = fit_gdf_to_bbox_pixels(shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=inset_px)
    if polygon and len(polygon) >= 3:
        clip_poly = Polygon(polygon)
    else:
        x0, y0, x1, y1 = bbox
        clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    gdf_px = gdf_px.copy()
    gdf_px['geometry'] = gdf_px.geometry.intersection(clip_poly)
    gdf_px = gdf_px[~gdf_px.geometry.is_empty]
    base = Image.open(image_path).convert('RGBA')
    draw = ImageDraw.Draw(base)
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
        for poly in polys:
            coords = list(poly.exterior.coords)
            if len(coords) >= 2:
                draw.line(coords, fill=(255, 0, 0, 255), width=2)
    base.save(out_path)
    return out_path
