from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
import geopandas as gpd
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

try:
    from schemas.bounds import ImageSize, CanvasEntry, MapCanvasBounds
except ImportError:  # pragma: no cover
    from backend.schemas.bounds import ImageSize, CanvasEntry, MapCanvasBounds

try:
    from utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset, render_overlay_full_image
except ImportError:  # pragma: no cover
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset, render_overlay_full_image


# ---------- helpers ----------

def _rectangularity(contour) -> float:
    area = cv2.contourArea(contour)
    if area <= 0:
        return 0.0
    (cx, cy), (w, h), _ = cv2.minAreaRect(contour)
    rect_area = max(1.0, w * h)
    return float(area) / rect_area  # 0..1


def _approx(contour, eps_frac=0.01) -> np.ndarray:
    peri = cv2.arcLength(contour, True)
    eps = max(1.0, eps_frac * peri)
    return cv2.approxPolyDP(contour, eps, True)


def _smooth(v: np.ndarray, k: int = 15) -> np.ndarray:
    k = max(3, int(k) | 1)  # odd
    return cv2.GaussianBlur(v.astype(np.float32), (k, 1), 0).squeeze()


# ---------- main detector ----------

def detect_map_panel_like_screenshot(image_path: str) -> Dict:
    """
    Finds a tight rectangle around the main printed panel (CONUS incl. AK inset),
    *excluding* the right legend and most of the title band—like the screenshot you showed.
    Returns: {"bbox":[x0,y0,x1,y1], "polygon":[[x,y]...], "confidence":0..1}
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(image_path)
    H, W = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1) Build a "non-white" mask to analyze text/title/legend bands
    #    (printed maps have pure-ish white backgrounds)
    nonwhite = (gray < 245).astype(np.uint8)  # 1 where ink exists
    # small blur to unify thin lines
    nonwhite = cv2.medianBlur(nonwhite * 255, 3) // 255

    # 2) Drop the right legend by finding a sharp rise in column ink density near the right
    col = nonwhite.sum(axis=0)  # per-column ink
    col_s = _smooth(col, k=max(15, W // 128))
    # find a cut position: last big negative gradient (i.e., left edge of legend block)
    grad = np.gradient(col_s)
    # search on the right third
    right_start = int(0.60 * W)
    cut_candidates = np.argsort(grad[right_start:])[:10] + right_start  # most negative
    cut_x = None
    for x in sorted(cut_candidates):
        # ensure there is a sustained low-ink region to the right (legend gap/margin)
        right_mean = col_s[min(W-1, x+10):].mean() if x+10 < W else 0
        left_mean = col_s[max(0, x-40):x].mean()
        if right_mean < 0.6 * left_mean:
            cut_x = x
            break
    if cut_x is None:
        cut_x = int(0.92 * W)  # conservative fallback

    # 3) Create a working image without the legend area
    work = img[:, :cut_x].copy()
    Hw, Ww = work.shape[:2]
    gray_w = gray[:, :cut_x]

    # 4) Trim the top title band using row ink density
    row = (gray_w < 245).sum(axis=1)
    row_s = _smooth(row.reshape(-1,1), k=max(15, H // 128))
    # find first row from top where ink density exceeds 1.5% of width -> start of map frame/content
    thresh = 0.015 * Ww
    top_y = 0
    for i in range(min(Hw - 1, int(0.25 * H))):
        if row_s[i] > thresh:
            top_y = i
            break
    # small nudge down to skip the printed title line
    top_y = min(Hw - 2, top_y + 6)

    # 5) Edge map for panel frame
    g = cv2.GaussianBlur(gray_w[top_y:], (5,5), 0)
    med = np.median(g)
    lo, hi = int(max(0, 0.66*med)), int(min(255, 1.33*med))
    edges = cv2.Canny(g, lo, hi)

    # connect broken frame edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 6) Contours and scoring (prefer big, rectangular, centered)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    IMG_AREA = float(Ww * (Hw - top_y))
    cands: List[Tuple[float, List[int], List[List[int]]]] = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.10 * IMG_AREA:  # skip small
            continue
        x,y,w,h = cv2.boundingRect(c)
        w = max(w,1); h = max(h,1)
        # aspect of CONUS incl. AK inset (roughly 1.2..2.4)
        ar = w / float(h)
        if ar < 1.15 or ar > 2.5:
            continue
        rect_score = _rectangularity(c)  # 0..1
        cx, cy = x + w/2, y + h/2
        cx_n = abs(cx - Ww/2) / (Ww/2)
        cy_n = abs(cy - (Hw-top_y)/2) / ((Hw-top_y)/2)
        center_score = 1.0 - min(1.0, 0.6*cx_n + 0.4*cy_n)
        score = 0.65*rect_score + 0.35*center_score

        poly = _approx(c, eps_frac=0.01).reshape(-1,2)
        # shift poly back up by top_y offset
        poly[:,1] = poly[:,1] + top_y
        poly = poly.tolist()

        # bbox in FULL image coords
        bbox = [int(x), int(y+top_y), int(x+w), int(y+h+top_y)]
        cands.append((score, bbox, poly))

    if not cands:
        # fallback: use the nonwhite bbox we computed, limited by cut_x and top_y
        ys, xs = np.where(nonwhite[:, :cut_x] > 0)
        if len(xs) == 0:
            return {"bbox":[0,0,W-1,H-1],"polygon":[[0,0],[W-1,0],[W-1,H-1],[0,H-1]],"confidence":0.25}
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(max(0, ys.min()+6)), int(ys.max())
        return {
            "bbox":[x0, y0, x1, y1],
            "polygon":[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
            "confidence":0.45
        }

    best = max(cands, key=lambda t: t[0])
    score, bbox, poly = best
    # tiny inward inset to avoid drawing on the black frame line itself
    x0,y0,x1,y1 = bbox
    inset = max(2, int(0.004 * max(W,H)))
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    x0 = max(0, min(x0, x1-2)); y0 = max(0, min(y0, y1-2))
    poly = [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]  # use a clean rectangle polygon for sampling/clip

    return {"bbox":[int(x0),int(y0),int(x1),int(y1)],
            "polygon":poly,
            "confidence":round(float(min(1.0, score)),3)}


def detect_panel_bounds(
    image_path: str | Path,
    min_area_ratio: float = 0.15,
    max_area_ratio: float = 0.85,
    canny_thresholds: tuple[int, int] = (50, 150),
    use_color_variance: bool = True,
) -> MapCanvasBounds:
    """
    Wrapper to maintain API compatibility.
    Uses the new detect_map_panel_like_screenshot function.
    """
    image_path = Path(image_path)
    result = detect_map_panel_like_screenshot(str(image_path))
    
    # Get actual image size
    img = cv2.imread(str(image_path))
    if img is not None:
        height, width = img.shape[:2]
    else:
        # Fallback if image can't be read
        x0, y0, x1, y1 = result["bbox"]
        width = x1
        height = y1
    
    canvas = CanvasEntry(
        name="CONUS",
        bbox=tuple(result["bbox"]),
        polygon=result["polygon"] if result.get("polygon") else None,
        confidence=result["confidence"],
    )
    
    return MapCanvasBounds(
        image_size=ImageSize(width=width, height=height),
        canvases=[canvas],
    )


def generate_bounds_overlay(
    image_path: str | Path,
    bounds: MapCanvasBounds,
    shapefile_path: str | Path,
    output_path: str | Path,
    inset_px: int = 6,
) -> Path:
    """
    Generate overlay showing detected bounds and shapefile alignment.
    Uses the robust fit + clip approach.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)
    shapefile_path = Path(shapefile_path)

    if not bounds.canvases:
        raise ValueError("No canvases in bounds")

    canvas = bounds.canvases[0]
    bbox = tuple(canvas.bbox)
    polygon = canvas.polygon if hasattr(canvas, 'polygon') and canvas.polygon else None

    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Draw bbox
    x0, y0, x1, y1 = bbox
    draw.rectangle([x0, y0, x1, y1], outline=(0, 255, 0, 255), width=3)

    # Draw polygon if provided
    if polygon and len(polygon) >= 3:
        draw.polygon(polygon, outline=(0, 255, 0, 200), width=2)

    # Load and overlay shapefile - CONUS ONLY
    # Note: Shapefile is already CONUS-only (excludes Alaska, Hawaii, and territories)
    if shapefile_path.exists():
        try:
            gdf = gpd.read_file(shapefile_path)
            
            # Handle different possible GEOID column names (for compatibility)
            if "GEOID" in gdf.columns:
                gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
            elif "GEO_ID" in gdf.columns:
                gdf["GEOID"] = gdf["GEO_ID"].astype(str).str.zfill(5)
            elif "COUNTYFP" in gdf.columns and "STATEFP" in gdf.columns:
                # Construct GEOID from STATEFP + COUNTYFP
                gdf["GEOID"] = gdf["STATEFP"].astype(str).str.zfill(2) + gdf["COUNTYFP"].astype(str).str.zfill(3)
            else:
                # Create GEOID from index if no standard columns exist
                gdf["GEOID"] = gdf.index.astype(str).str.zfill(5)
            
            print(f"Loaded {len(gdf)} CONUS counties")

            # For overlay visualization: fit shapefile to EXACTLY match the green rectangle (inset=0)
            # The auto-inset tuning is for data processing, but for visual overlay we want exact match
            try:
                # 1) Reproject for printed US maps
                try:
                    if gdf.crs is None:
                        gdf = gdf.set_crs(4269, allow_override=True)
                    gdf = gdf.to_crs(5070)
                except Exception:
                    pass
                
                # 2) Fit to EXACT bbox (inset=0) to match green rectangle
                # For overlay visualization, use keep_aspect=False to force exact fill of green rectangle
                # (Actual data processing will still use keep_aspect=True with auto-inset)
                gdf_px = fit_gdf_to_bbox_pixels(
                    gdf,
                    bbox=bbox,
                    polygon=None,
                    keep_aspect=False,  # Force exact fill for visualization
                    inset_px=0,  # NO inset - fill green rectangle exactly
                )
                
                # 3) Clip to panel polygon/rect to avoid legend bleed
                if polygon and len(polygon) >= 3:
                    clip_poly = Polygon(polygon)
                else:
                    clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
                
                gdf_px_clip = gdf_px.copy()
                gdf_px_clip["geometry"] = gdf_px_clip.geometry.intersection(clip_poly)
                gdf_px_clip = gdf_px_clip[~gdf_px_clip.geometry.is_empty]
                
                # Sanity check: pixel-fit bounds should sit within bbox (with small tolerance)
                px_bounds = gdf_px_clip.total_bounds
                assert px_bounds[0] >= x0 - 5 and px_bounds[2] <= x1 + 5, \
                    f"Overlay: Pixel-fit bounds {px_bounds} don't sit within bbox {(x0, y0, x1, y1)}"
                assert px_bounds[1] >= y0 - 5 and px_bounds[3] <= y1 + 5, \
                    f"Overlay: Pixel-fit bounds {px_bounds} don't sit within bbox {(x0, y0, x1, y1)}"
                print(f"✓ Overlay sanity check: pixel bounds {px_bounds} within bbox {bbox}")
                
                # 4) Draw directly on full image (no translate - drawing on full image)
                # DO NOT shift by (-x0, -y0) - geometries are already in full-image coords
                for geom in gdf_px_clip.geometry:
                    if geom is None or geom.is_empty:
                        continue
                    polygons = (
                        list(geom.geoms)
                        if geom.geom_type == "MultiPolygon"
                        else [geom]
                    )
                    for poly in polygons:
                        coords = list(poly.exterior.coords)
                        if len(coords) >= 2:
                            draw.line(coords, fill=(255, 0, 0), width=2)
            except Exception as overlay_err:
                # Fallback to simple rendering if auto-inset fails
                print(f"Auto-inset failed: {overlay_err}, using fallback")
                # 1) Reproject for printed US maps
                try:
                    if gdf.crs is None:
                        gdf = gdf.set_crs(4269, allow_override=True)
                    gdf = gdf.to_crs(5070)
                except Exception:
                    pass
                
                # 2) Fit into FULL-IMAGE pixel coords
                gdf_px = fit_gdf_to_bbox_pixels(
                    gdf,
                    bbox=bbox,
                    polygon=None,
                    keep_aspect=True,
                    inset_px=6,
                )
                
                # 3) Clip to panel polygon/rect to avoid legend bleed
                if polygon and len(polygon) >= 3:
                    clip_poly = Polygon(polygon)
                else:
                    clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
                
                gdf_px = gdf_px.copy()
                gdf_px["geometry"] = gdf_px.geometry.intersection(clip_poly)
                gdf_px = gdf_px[~gdf_px.geometry.is_empty]
                
                # Sanity check
                px_bounds = gdf_px.total_bounds
                assert px_bounds[0] >= x0 - 5 and px_bounds[2] <= x1 + 5, \
                    f"Fallback overlay: Pixel bounds {px_bounds} outside bbox {(x0, y0, x1, y1)}"
                
                # 4) Draw on full image (no translate - geometries are in full-image coords)
                # DO NOT shift by (-x0, -y0) when drawing on full image
                for geom in gdf_px.geometry:
                    if geom is None or geom.is_empty:
                        continue
                    polygons = (
                        list(geom.geoms)
                        if geom.geom_type == "MultiPolygon"
                        else [geom]
                    )
                    for poly in polygons:
                        coords = list(poly.exterior.coords)
                        if len(coords) >= 2:
                            draw.line(coords, fill=(255, 0, 0), width=2)
        except Exception:
            # If shapefile overlay fails, continue with bbox visualization only
            pass

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)

    return output_path
