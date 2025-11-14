from typing import Optional, Tuple, List

import cv2
import numpy as np
import geopandas as gpd
from shapely.affinity import scale, translate, rotate
from shapely.geometry import Polygon, Point
from PIL import Image, ImageDraw


def fit_gdf_to_bbox_pixels(
    gdf: gpd.GeoDataFrame,
    bbox: Tuple[int, int, int, int],
    polygon: Optional[List[Tuple[int, int]]] = None,
    keep_aspect: bool = False,
    inset_px: int = 6,  # shave panel frame/padding
):
    """
    Map geometries from shapefile coords into image pixel coords of the given bbox.
    - Image pixel origin is top-left; Y grows downward => we flip Y.
    - keep_aspect=False lets X and Y scale independently (better for projected prints).
    - inset_px trims a tiny margin inside the bbox to avoid the panel's white/black frame.
    """
    x0, y0, x1, y1 = bbox
    if inset_px > 0:
        x0 += inset_px
        y0 += inset_px
        x1 -= inset_px
        y1 -= inset_px
    W = max(1, x1 - x0)
    H = max(1, y1 - y0)

    # shapefile bounds in its native CRS
    minx, miny, maxx, maxy = gdf.total_bounds
    w_src = max(maxx - minx, 1e-9)
    h_src = max(maxy - miny, 1e-9)

    sx = W / w_src
    sy = H / h_src
    if keep_aspect:
        s = min(sx, sy)
        sx = sy = s

    # After scaling
    scaled_w = w_src * sx
    scaled_h = h_src * sy

    # Translation to fill bbox exactly (edge-to-edge, not centered)
    # When keep_aspect=False and inset_px=0, we want exact fill of the bbox
    
    if keep_aspect:
        # Center when preserving aspect (may have padding)
        dx_final = x0 + (W - scaled_w) / 2.0 - (minx * sx)
        # Y translation: after flipping with -sy, center vertically
        dy_final = y0 + H / 2.0 + (maxy + miny) * sy / 2.0
    else:
        # When keep_aspect=False, fill bbox exactly (edge-to-edge)
        # Map shapefile bounds directly to bbox bounds:
        # minx -> x0, maxx -> x1, miny (south) -> y1 (bottom), maxy (north) -> y0 (top after flip)
        # After scale: minx * sx should map to x0
        dx_final = x0 - (minx * sx)
        # After Y-flip: maxy (north) becomes -maxy*sy, which should map to y0 (top)
        dy_final = y0 - (-maxy * sy)  # Simplify: y0 + (maxy * sy)

    def _affine(geom):
        g = scale(geom, xfact=sx, yfact=-sy, origin=(0, 0))  # flip Y
        g = translate(g, xoff=dx_final, yoff=dy_final)
        return g

    gdf_px = gdf.copy()
    gdf_px.geometry = gdf_px.geometry.apply(_affine)

    if polygon and len(polygon) >= 3:
        clip_poly = Polygon(polygon)
        gdf_px.geometry = gdf_px.geometry.intersection(clip_poly)

    return gdf_px


def _extract_shapefile_edge_points(gdf_px: gpd.GeoDataFrame, n_points: int = None) -> np.ndarray:
    """Extract ALL edge points from shapefile geometries - no sampling unless specified."""
    edge_points = []
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polygons:
            # Get all exterior coordinates
            coords = list(poly.exterior.coords)
            if len(coords) < 3:
                continue
            edge_points.extend(coords)
            
            # Also get interior boundaries (holes) if any
            if hasattr(poly, 'interiors'):
                for interior in poly.interiors:
                    interior_coords = list(interior.coords)
                    if len(interior_coords) >= 3:
                        edge_points.extend(interior_coords)
    
    if not edge_points:
        return np.array([])
    
    arr = np.array(edge_points)
    # Only sample if explicitly requested (for speed in refinement)
    if n_points and len(arr) > n_points:
        # Use uniform sampling along all edges, not random
        indices = np.linspace(0, len(arr) - 1, n_points, dtype=int)
        arr = arr[indices]
    return arr


def _detect_image_edges(image_path: str, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Detect ALL county/state boundary edges in the map image within the bbox.
    Optimized to capture thin dark lines that separate colored county regions.
    Uses multiple techniques to ensure we catch all visible boundaries.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return np.array([])
    
    x0, y0, x1, y1 = bbox
    # Crop to bbox
    cropped = img[y0:y1, x0:x1]
    if cropped.size == 0:
        return np.array([])
    
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    
    # Method 1: Very sensitive Canny edge detection for thin dark boundary lines
    # Use lower thresholds to catch subtle county boundaries
    # Apply minimal blur to preserve thin lines
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # Multiple Canny thresholds to catch boundaries at different contrast levels
    # Lower thresholds catch faint lines, higher catch strong lines
    edges_low = cv2.Canny(blur, 10, 30)      # Very sensitive for faint lines
    edges_mid = cv2.Canny(blur, 30, 80)     # Medium sensitivity
    edges_high = cv2.Canny(blur, 50, 150)   # Standard sensitivity
    edges_canny = cv2.bitwise_or(edges_low, cv2.bitwise_or(edges_mid, edges_high))
    
    # Method 2: Detect boundaries by color changes (critical for choropleth maps)
    # Convert to LAB color space for perceptually uniform color boundaries
    lab = cv2.cvtColor(cropped, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    
    # Use Sobel operators to detect gradients (where counties meet)
    sobel_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(l_channel, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
    
    # Normalize and threshold - lower threshold to catch subtle color boundaries
    if gradient_magnitude.max() > 0:
        gradient_norm = np.uint8(255 * gradient_magnitude / gradient_magnitude.max())
        _, gradient_edges = cv2.threshold(gradient_norm, 15, 255, cv2.THRESH_BINARY)  # Lower threshold
    else:
        gradient_edges = np.zeros_like(gray, dtype=np.uint8)
    
    # Method 3: Detect dark lines directly (county boundaries are often dark)
    # Invert so dark lines become bright, then detect
    inverted = 255 - gray
    # Use adaptive thresholding to catch dark lines regardless of local brightness
    adaptive = cv2.adaptiveThreshold(
        inverted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    # Find edges in the thresholded inverted image
    dark_lines = cv2.Canny(adaptive, 50, 150)
    
    # Combine all methods - union of all detected edges
    edges = cv2.bitwise_or(edges_canny, gradient_edges)
    edges = cv2.bitwise_or(edges, dark_lines)
    
    # Clean up: connect nearby edge fragments (but preserve thin lines)
    kernel = np.ones((2, 2), np.uint8)
    # Gentle closing to connect fragments without losing detail
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    # Very light dilation (1 iteration) to make edges slightly thicker for matching
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    # Find ALL edge pixels (convert to absolute coordinates)
    y_coords, x_coords = np.where(edges > 0)
    if len(x_coords) == 0:
        return np.array([])
    
    # Convert back to full-image coordinates
    edge_points = np.column_stack([x_coords + x0, y_coords + y0])
    
    # For comprehensive matching, keep all edge points up to a reasonable limit
    # Only sample if truly excessive
    if len(edge_points) > 20000:  # Increased limit for better coverage
        # Use uniform sampling to preserve spatial distribution
        indices = np.linspace(0, len(edge_points) - 1, 20000, dtype=int)
        edge_points = edge_points[indices]
    
    return edge_points


def refine_alignment_with_edge_matching(
    gdf_px: gpd.GeoDataFrame,
    image_path: str,
    bbox: Tuple[int, int, int, int],
    max_iterations: int = 5,
) -> gpd.GeoDataFrame:
    """
    Refine alignment by detecting ALL edges in the map image and matching them to ALL shapefile edges.
    Uses optimized grid search with KDTree for fast nearest neighbor lookup.
    Matches the COMPLETE shapefile to ALL detected county boundaries.
    """
    from scipy.spatial import cKDTree
    from shapely.affinity import translate, rotate
    
    # Extract ALL shapefile edge points - no sampling for comprehensive matching
    shapefile_edges = _extract_shapefile_edge_points(gdf_px, n_points=None)
    if len(shapefile_edges) == 0:
        print("WARNING: No shapefile edges extracted!")
        return gdf_px
    
    print(f"Extracted {len(shapefile_edges)} shapefile edge points")
    
    # Detect ALL image edges - comprehensive edge detection
    image_edges = _detect_image_edges(image_path, bbox)
    if len(image_edges) == 0:
        print("WARNING: No image edges detected!")
        return gdf_px
    
    print(f"Detected {len(image_edges)} image edge points")
    
    # Build KDTree for fast nearest neighbor search (much faster than cdist)
    image_tree = cKDTree(image_edges)
    
    # Start with current alignment
    base_gdf = gdf_px.copy()
    best_gdf = base_gdf.copy()
    best_score = float('inf')
    
    # Calculate bbox center for transformations
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    center_x, center_y = x0 + w / 2, y0 + h / 2
    
    # Expanded grid search to find better alignment (larger range to catch misalignments)
    # Use more steps but sample shapefile edges for speed
    dx_range = np.linspace(-w * 0.05, w * 0.05, 5)  # ±5% horizontal translation
    dy_range = np.linspace(-h * 0.05, h * 0.05, 5)  # ±5% vertical translation
    sx_range = np.linspace(0.95, 1.05, 5)  # ±5% X scaling
    sy_range = np.linspace(0.95, 1.05, 5)  # ±5% Y scaling
    
    # For speed, sample shapefile edges (but use ALL image edges)
    # Sample uniformly to preserve spatial distribution
    if len(shapefile_edges) > 2000:
        sample_indices = np.linspace(0, len(shapefile_edges) - 1, 2000, dtype=int)
        shapefile_sample = shapefile_edges[sample_indices]
    else:
        shapefile_sample = shapefile_edges
    
    print(f"Using {len(shapefile_sample)} shapefile points for matching")
    
    # Stage 1: Try translation + scaling
    early_exit = False
    iteration_count = 0
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
                    if iteration_count % 50 == 0:
                        print(f"  Testing iteration {iteration_count}/625...")
                    
                    # Apply affine transformation: Scale + Translate
                    # Transform the sample points directly (faster than transforming all geometries)
                    transformed_sample = shapefile_sample.copy().astype(float)
                    # Scale around center
                    transformed_sample[:, 0] = (transformed_sample[:, 0] - center_x) * sx + center_x
                    transformed_sample[:, 1] = (transformed_sample[:, 1] - center_y) * sy + center_y
                    # Translate
                    transformed_sample[:, 0] += dx
                    transformed_sample[:, 1] += dy
                    
                    # Fast nearest neighbor search using KDTree (O(n log m) instead of O(n*m))
                    distances, _ = image_tree.query(transformed_sample, k=1)
                    # Score: mean of distances to nearest image edge
                    # Use a threshold to filter out obviously wrong matches
                    valid_matches = distances[distances < 20]  # Within 20px
                    
                    if len(valid_matches) > len(shapefile_sample) * 0.1:  # At least 10% of points match
                        score = np.mean(valid_matches)
                        match_ratio = len(valid_matches) / len(shapefile_sample)
                        
                        # Combined score: prefer matches with both low distance and high coverage
                        combined_score = score / (match_ratio + 0.1)  # Lower is better
                        
                        if combined_score < best_score:
                            best_score = combined_score
                            # Apply transformation to full geometries
                            test_gdf = base_gdf.copy()
                            test_gdf["geometry"] = test_gdf.geometry.apply(
                                lambda g: translate(
                                    scale(g, xfact=sx, yfact=sy, origin=(center_x, center_y)),
                                    xoff=dx, yoff=dy
                                )
                            )
                            best_gdf = test_gdf
                            print(f"  Found better alignment: score={combined_score:.2f}, matches={match_ratio:.1%}")
                            
                            # Early termination if we found a very good match
                            if combined_score < 3.0 and match_ratio > 0.3:
                                print(f"  Excellent match found! Stopping early.")
                                early_exit = True
                                break
    
    # Stage 2: If stage 1 found a decent match, try adding small rotation (only if needed)
    if best_score < float('inf'):
        print(f"Stage 1 best score: {best_score:.2f}")
        
        if best_score < 8.0:  # If we have a reasonable match, refine with rotation
            print("Stage 2: Refining with rotation...")
            stage2_base = best_gdf.copy()
            stage2_sample = _extract_shapefile_edge_points(stage2_base, n_points=2000)
            
            rotation_range = np.linspace(-2.0, 2.0, 5)  # ±2 degrees, 5 steps
            
            for angle in rotation_range:
                # Transform sample points
                rotated_sample = stage2_sample.copy().astype(float)
                cos_a = np.cos(np.radians(angle))
                sin_a = np.sin(np.radians(angle))
                # Rotate around center
                x_rel = rotated_sample[:, 0] - center_x
                y_rel = rotated_sample[:, 1] - center_y
                rotated_sample[:, 0] = x_rel * cos_a - y_rel * sin_a + center_x
                rotated_sample[:, 1] = x_rel * sin_a + y_rel * cos_a + center_y
                
                distances, _ = image_tree.query(rotated_sample, k=1)
                valid_matches = distances[distances < 20]
                
                if len(valid_matches) > len(rotated_sample) * 0.1:
                    score = np.mean(valid_matches)
                    match_ratio = len(valid_matches) / len(rotated_sample)
                    combined_score = score / (match_ratio + 0.1)
                    
                    if combined_score < best_score:
                        best_score = combined_score
                        test_gdf = stage2_base.copy()
                        test_gdf["geometry"] = test_gdf.geometry.apply(
                            lambda g: rotate(g, angle=angle, origin=(center_x, center_y))
                        )
                        best_gdf = test_gdf
                        print(f"  Rotation {angle:.1f}° improved: score={combined_score:.2f}, matches={match_ratio:.1%}")
    
    # Return the best alignment found
    if best_score < float('inf'):
        print(f"Final alignment score: {best_score:.2f}")
        # Always return refined alignment if we found any improvement
        # (even if score is > 5.0, it might still be better than initial)
        return best_gdf
    
    print("No valid alignment found, returning original")
    return gdf_px


def _edge_overlap_score(image_path: str, gdf_px: gpd.GeoDataFrame) -> float:
    """
    Rasterize county boundaries as 1-pixel lines and score overlap with detected edges.
    Uses the same multi-method edge detection as _detect_image_edges for consistency.
    Returns score between 0 and 1, where 1 is perfect overlap.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return 0.0
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Use same multi-method edge detection as _detect_image_edges
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # Multi-scale Canny
    edges_low = cv2.Canny(blur, 10, 30)
    edges_mid = cv2.Canny(blur, 30, 80)
    edges_high = cv2.Canny(blur, 50, 150)
    edges_canny = cv2.bitwise_or(edges_low, cv2.bitwise_or(edges_mid, edges_high))
    
    # Color gradient edges
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]
    sobel_x = cv2.Sobel(l_channel, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(l_channel, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
    if gradient_magnitude.max() > 0:
        gradient_norm = np.uint8(255 * gradient_magnitude / gradient_magnitude.max())
        _, gradient_edges = cv2.threshold(gradient_norm, 15, 255, cv2.THRESH_BINARY)
    else:
        gradient_edges = np.zeros_like(gray, dtype=np.uint8)
    
    # Dark line detection
    inverted = 255 - gray
    adaptive = cv2.adaptiveThreshold(
        inverted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    dark_lines = cv2.Canny(adaptive, 50, 150)
    
    # Combine all methods
    edges = cv2.bitwise_or(edges_canny, gradient_edges)
    edges = cv2.bitwise_or(edges, dark_lines)
    
    # Light cleanup
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    # Rasterize borders
    line = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(line)
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            coords = list(poly.exterior.coords)
            if len(coords) >= 2:
                draw.line(coords, fill=255, width=1)
    
    line_arr = np.array(line)
    
    # Overlap score: percentage of rasterized borders that overlap with Canny edges
    overlap = (line_arr > 0) & (edges > 0)
    denom = max(1, (line_arr > 0).sum())
    return float(overlap.sum()) / float(denom)


def fit_with_autoinset(
    shp: gpd.GeoDataFrame,
    image_path: str,
    bbox: Tuple[int, int, int, int],
    polygon: Optional[List[Tuple[int, int]]] = None,
    keep_aspect: bool = True,
    inset_candidates: Tuple[int, ...] = (4, 6, 8, 10),
) -> Tuple[gpd.GeoDataFrame, float, int]:
    """
    Automatically tune the inset by scoring edge overlap for each candidate.
    Returns: (best_gdf_px, best_score, chosen_inset)
    """
    best = (None, -1.0, None)  # (gdf_px, score, inset)
    
    for inset in inset_candidates:
        gdf_px = fit_gdf_to_bbox_pixels(
            shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=inset
        )
        
        # Clip before scoring to avoid legend lines biasing the score
        if polygon and len(polygon) >= 3:
            clip_poly = Polygon(polygon)
        else:
            x0, y0, x1, y1 = bbox
            clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        
        gdf_px_clip = gdf_px.copy()
        gdf_px_clip["geometry"] = gdf_px_clip.geometry.intersection(clip_poly)
        gdf_px_clip = gdf_px_clip[~gdf_px_clip.geometry.is_empty]
        
        if len(gdf_px_clip) == 0:
            continue
            
        s = _edge_overlap_score(image_path, gdf_px_clip)
        if s > best[1]:
            best = (gdf_px_clip, s, inset)
    
    if best[0] is None:
        # Fallback: use middle inset
        default_inset = inset_candidates[len(inset_candidates) // 2]
        gdf_px = fit_gdf_to_bbox_pixels(
            shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=default_inset
        )
        if polygon and len(polygon) >= 3:
            clip_poly = Polygon(polygon)
        else:
            x0, y0, x1, y1 = bbox
            clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        gdf_px_clip = gdf_px.copy()
        gdf_px_clip["geometry"] = gdf_px_clip.geometry.intersection(clip_poly)
        return (gdf_px_clip, 0.0, default_inset)
    
    return best


def render_overlay_full_image(
    image_path: str,
    shp: gpd.GeoDataFrame,
    bbox: Tuple[int, int, int, int],
    polygon: Optional[List[Tuple[int, int]]] = None,
    inset_px: int = 6,
    keep_aspect: bool = True,
    out_path: str = "overlay.png",
) -> str:
    """
    Robust overlay rendering: Project → Fit (aspect-locked) → Clip → Draw
    Draws on full image coordinates (no crop shift).
    """
    # 1) Reproject for printed US maps
    try:
        if shp.crs is None:
            shp = shp.set_crs(4269, allow_override=True)  # NAD83 default for census
        shp = shp.to_crs(5070)  # CONUS Albers
    except Exception:
        pass
    
    # 2) Fit into FULL-IMAGE pixel coords (no crop shift here)
    gdf_px = fit_gdf_to_bbox_pixels(
        shp, bbox=bbox, polygon=None, keep_aspect=keep_aspect, inset_px=inset_px
    )
    
    # 3) Clip to panel polygon/rect to avoid legend bleed
    if polygon and len(polygon) >= 3:
        clip_poly = Polygon(polygon)
    else:
        x0, y0, x1, y1 = bbox
        clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    
    gdf_px = gdf_px.copy()
    gdf_px["geometry"] = gdf_px.geometry.intersection(clip_poly)
    gdf_px = gdf_px[~gdf_px.geometry.is_empty]
    
    # 4) Draw over FULL image (no translate)
    base = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(base)
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            coords = list(poly.exterior.coords)
            if len(coords) >= 2:
                draw.line(coords, fill=(255, 0, 0, 255), width=2)
    
    base.save(out_path)
    return out_path


