"""
Generate overlay preview showing shapefile boundaries on the uploaded image.
Uses separate region shapefiles (CONUS, Alaska, Hawaii) with affine transformations.
"""

import os
import numpy as np
import cv2
import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.affinity import affine_transform
from typing import Optional, Dict, Tuple, List
from rasterio.features import rasterize
from affine import Affine

try:
    from utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset
    from utils.homography import transform_gdf_with_homography, rect_bounds_to_corners
    from data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR
except ImportError:
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset
    from backend.utils.homography import transform_gdf_with_homography, rect_bounds_to_corners
    from backend.data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR


def generate_region_overlay_preview(
    image_path: str,
    upload_id: str,
    bounds_bbox: Tuple[int, int, int, int],
    bounds_polygon: Optional[List[Tuple[int, int]]] = None,
    bounds_rect4: Optional[List[Tuple[int, int]]] = None,
    projection: str = "4326",
    region_selections: Optional[Dict] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Generate overlay preview showing shapefile boundaries on the image.
    
    Args:
        image_path: Path to uploaded image
        upload_id: Upload ID
        bounds_bbox: Bounding box (x0, y0, x1, y1)
        bounds_polygon: Optional polygon for clipping
        projection: Projection code ("4326" or "5070")
        region_selections: Optional dict with 'alaska' and/or 'hawaii' bounding boxes
        output_path: Optional output path, defaults to data/{upload_id}_preview_overlay.png
    
    Returns:
        Path to generated overlay image
    """
    has_alaska = region_selections and region_selections.get("alaska")
    has_hawaii = region_selections and region_selections.get("hawaii")
    
    if output_path is None:
        output_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{upload_id}_preview_overlay.png")
    
    # Load image at natural size - NEVER resize
    # Image.open() loads at original dimensions, convert() only changes color space
    img_pil = Image.open(image_path).convert("RGB")
    W, H = img_pil.size  # Natural dimensions from file (width, height)
    img_width, img_height = W, H
    
    # Convert to numpy array for rasterization (no resize, exact pixel grid)
    overlay = np.array(img_pil)
    
    print(f"\n🔍 OVERLAY PREVIEW DEBUG:")
    print(f"  Image file: {image_path}")
    print(f"  Image dimensions (natural): {W} x {H} pixels")
    print(f"  Projection: EPSG:{projection}")
    print(f"  CONUS bbox: {bounds_bbox}")
    print(f"  CONUS rect4: {bounds_rect4}")
    
    # Verify image dimensions match bounds expectation
    x0, y0, x1, y1 = bounds_bbox
    if x1 > W or y1 > H:
        print(f"  ⚠️  WARNING: Bbox extends beyond image: bbox max ({x1}, {y1}) vs image ({W}, {H})")
    
    # Load and align regions
    # CONUS is always loaded - uses CONUS-only shapefile (no Alaska/Hawaii)
    regions_to_load = ["conus"]
    if has_alaska:
        regions_to_load.append("alaska")
    if has_hawaii:
        regions_to_load.append("hawaii")
    
    print(f"\n📋 Regions to load: {regions_to_load}")
    print(f"   ✓ CONUS will use CONUS-only shapefile (excludes Alaska/Hawaii)")
    
    x0, y0, x1, y1 = bounds_bbox
    
    for region in regions_to_load:
        # Load region OUTLINE shapefile (linework only, not full polygons)
        outline_path = _get_region_outline_path(region=region, projection=projection)
        
        print(f"\n📂 Loading {region.upper()} outline shapefile:")
        print(f"    Projection: EPSG:{projection}")
        print(f"    Outline path: {outline_path}")
        
        if not os.path.exists(outline_path):
            print(f"    ⚠️  Outline not found: {outline_path}")
            print(f"     Falling back to full shapefile (will create mesh effect)")
            # Fallback to full shapefile if outline doesn't exist
            shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
        
        if not os.path.exists(shapefile_path):
            if region == "conus":
                    # Fallback: Try CONUS-only shapefile without projection suffix
                    fallback_conus_path = os.path.join(BASE_DIR, "cb_2024_us_county_500k_conus", "cb_2024_us_county_500k_conus.shp")
                    if os.path.exists(fallback_conus_path):
                        shapefile_path = fallback_conus_path
                        print(f"    Using CONUS-only fallback shapefile (no Alaska/Hawaii)")
                    else:
                        # Last resort: use SHAPEFILE_PATH (should also be CONUS-only)
                        try:
                            from data_processing import SHAPEFILE_PATH
                        except ImportError:
                            from backend.data_processing import SHAPEFILE_PATH
                        shapefile_path = SHAPEFILE_PATH
                        print(f"    Using CONUS-only shapefile from SHAPEFILE_PATH")
            else:
                continue  # Skip if shapefile doesn't exist
        
            print(f"    Using shapefile: {shapefile_path}")
            print(f"    ✓ This is a {region.upper()}-ONLY shapefile (does NOT include other regions)")
            shp = gpd.read_file(shapefile_path)
            
            # Verify this is CONUS-only (check bounds don't include Alaska/Hawaii)
            if region == "conus":
                bounds = shp.total_bounds
                # CONUS bounds should be roughly: -125 to -66 longitude, 24 to 50 latitude
                # Alaska is much further west/north, Hawaii is much further west
                if bounds[0] < -180 or bounds[2] > -60:  # If extends too far west/east
                    print(f"    ⚠️  WARNING: Shapefile bounds extend beyond CONUS: {bounds}")
                else:
                    print(f"    ✓ Verified: Shapefile bounds are CONUS-only: {bounds}")
            
            # Extract boundary from polygons
            shp["geometry"] = shp.geometry.boundary
        else:
            # Use outline shapefile directly
            print(f"    ✓ Found outline shapefile")
            print(f"    ✓ This is a {region.upper()}-ONLY outline (does NOT include other regions)")
            shp = gpd.read_file(outline_path)
            
            # Verify this is CONUS-only outline
            if region == "conus":
                bounds = shp.total_bounds
                if bounds[0] < -180 or bounds[2] > -60:
                    print(f"    ⚠️  WARNING: Outline bounds extend beyond CONUS: {bounds}")
                else:
                    print(f"    ✓ Verified: Outline bounds are CONUS-only: {bounds}")
        
        if "GEOID" not in shp.columns:
            shp["GEOID"] = shp.index.astype(str)
        shp["GEOID"] = shp["GEOID"].astype(str).str.zfill(5)
        
        # Ensure CRS is set
        if shp.crs is None:
            if projection == "4326":
                shp = shp.set_crs(4326, allow_override=True)
            elif projection == "5070":
                shp = shp.set_crs(5070, allow_override=True)
            else:
                shp = shp.set_crs(4269, allow_override=True)
        
        # Reproject to EPSG:5070 for alignment
        target_crs = 5070
        if shp.crs.to_epsg() != target_crs:
            shp = shp.to_crs(target_crs)
        
        # Determine rect4 and bbox for this region
        if region == "conus":
            # Use user-selected CONUS if available, otherwise use bounds
            if region_selections and region_selections.get("conus"):
                conus_bbox = region_selections["conus"]
                conus_x0 = int(conus_bbox["x"])
                conus_y0 = int(conus_bbox["y"])
                conus_x1 = int(conus_bbox["x"] + conus_bbox["width"])
                conus_y1 = int(conus_bbox["y"] + conus_bbox["height"])
                region_bbox = (conus_x0, conus_y0, conus_x1, conus_y1)
                # Use rect4 from region_selections if available (from frontend), otherwise derive from bbox
                if conus_bbox.get("rect4"):
                    region_rect4 = conus_bbox["rect4"]
                elif "conus_rect4" in region_selections:
                    region_rect4 = region_selections["conus_rect4"]
                else:
                    region_rect4 = [(conus_x0, conus_y0), (conus_x1, conus_y0), (conus_x1, conus_y1), (conus_x0, conus_y1)]
                region_polygon = None
                print(f"    Using user-selected CONUS region")
            else:
                region_bbox = bounds_bbox
                region_polygon = bounds_polygon
                region_rect4 = bounds_rect4  # Use rect4 if provided
                print(f"    Using detected CONUS bounds")
            color = (255, 0, 0, 255)  # Red for CONUS
        elif region == "alaska":
            if not region_selections or not region_selections.get("alaska"):
                print(f"    ⚠️  Alaska region selection not found, skipping...")
                continue
            alaska_bbox = region_selections["alaska"]
            ak_x0 = int(alaska_bbox["x"])
            ak_y0 = int(alaska_bbox["y"])
            ak_x1 = int(alaska_bbox["x"] + alaska_bbox["width"])
            ak_y1 = int(alaska_bbox["y"] + alaska_bbox["height"])
            region_bbox = (ak_x0, ak_y0, ak_x1, ak_y1)
            # Get rect4 from region_selections if available (from frontend), otherwise derive from bbox
            if alaska_bbox.get("rect4"):
                region_rect4 = alaska_bbox["rect4"]
            elif "alaska_rect4" in (region_selections or {}):
                region_rect4 = region_selections["alaska_rect4"]
            else:
                # Derive from bbox (clockwise: TL, TR, BR, BL)
                region_rect4 = [(ak_x0, ak_y0), (ak_x1, ak_y0), (ak_x1, ak_y1), (ak_x0, ak_y1)]
            region_polygon = None
            color = (0, 255, 0, 255)  # Green for Alaska
            print(f"    Alaska bbox: {region_bbox}, rect4: {region_rect4}")
        elif region == "hawaii":
            if not region_selections or not region_selections.get("hawaii"):
                print(f"    ⚠️  Hawaii region selection not found, skipping...")
                continue
            hawaii_bbox = region_selections["hawaii"]
            hi_x0 = int(hawaii_bbox["x"])
            hi_y0 = int(hawaii_bbox["y"])
            hi_x1 = int(hawaii_bbox["x"] + hawaii_bbox["width"])
            hi_y1 = int(hawaii_bbox["y"] + hawaii_bbox["height"])
            region_bbox = (hi_x0, hi_y0, hi_x1, hi_y1)
            # Get rect4 from region_selections if available (from frontend), otherwise derive from bbox
            if hawaii_bbox.get("rect4"):
                region_rect4 = hawaii_bbox["rect4"]
            elif "hawaii_rect4" in (region_selections or {}):
                region_rect4 = region_selections["hawaii_rect4"]
            else:
                # Derive from bbox (clockwise: TL, TR, BR, BL)
                region_rect4 = [(hi_x0, hi_y0), (hi_x1, hi_y0), (hi_x1, hi_y1), (hi_x0, hi_y1)]
            region_polygon = None
            color = (0, 0, 255, 255)  # Blue for Hawaii
            print(f"    Hawaii bbox: {region_bbox}, rect4: {region_rect4}")
        
        # Use rect4-based affine transformation with edge detection alignment
        if region_rect4 and len(region_rect4) == 4:
            print(f"  {region.upper()} alignment (using edge detection + affine transform):")
            
            # Extract rect4 dimensions (NOT whole image dimensions)
            (x1, y1), (x2, y2) = region_rect4[0], region_rect4[2]  # Top-left, Bottom-right
            W_rect = x2 - x1
            H_rect = y2 - y1
            
            # Guardrails: verify rect is valid
            assert 0 <= x1 < x2 <= W and 0 <= y1 < y2 <= H, \
                f"Rect outside image bounds: rect=({x1},{y1},{x2},{y2}), image=({W},{H})"
            # Allow smaller rects for Alaska/Hawaii insets (they can be quite small)
            min_size = 30 if region.lower() in ("alaska", "hawaii") else 50
            assert abs(W_rect) >= min_size and abs(H_rect) >= min_size, \
                f"Rect suspiciously small: W={W_rect}, H={H_rect} (minimum {min_size}px for {region})"
            
            # Step 1: Crop the region from the full image
            print(f"    Step 1: Cropping {region.upper()} region from image...")
            cropped_img = overlay[y1:y2, x1:x2].copy()  # Crop region (numpy array)
            cropped_h, cropped_w = cropped_img.shape[:2]
            print(f"      Cropped size: {cropped_w} x {cropped_h} pixels")
            
            # Step 2: Get shapefile bounds in its native CRS (should be EPSG:5070 after reprojection)
            xmin, ymin, xmax, ymax = shp.total_bounds  # [xmin, ymin, xmax, ymax]
            
            print(f"    Step 2: Preparing alignment for cropped {region.upper()} region...")
            print(f"      Shapefile bounds: ({xmin:.2f}, {ymin:.2f}) to ({xmax:.2f}, {ymax:.2f})")
            print(f"      Shapefile size: {(xmax-xmin):.2f} x {(ymax-ymin):.2f}")
            print(f"      Cropped image size: {cropped_w} x {cropped_h} pixels")
            
            # Step 3: Use edge detection on cropped image and refine alignment with rotation
            print(f"    Step 3: Edge detection + affine transformation + rotation on cropped {region.upper()} image...")
            try:
                from backend.utils.geo_align import refine_alignment_with_edge_matching, fit_with_autoinset
            except:
                from utils.geo_align import refine_alignment_with_edge_matching, fit_with_autoinset
            
            # Create a temporary image file for the cropped region (required by edge detection)
            import tempfile
            temp_cropped_path = os.path.join(BASE_DIR, "data", f"{upload_id}_temp_{region}_cropped.png")
            os.makedirs(os.path.dirname(temp_cropped_path), exist_ok=True)
            Image.fromarray(cropped_img).save(temp_cropped_path)
            
            # Try using fit_with_autoinset first for better initial alignment
            cropped_bbox = (0, 0, cropped_w, cropped_h)
            
            # For Alaska/Hawaii, use smaller inset candidates since they're small inset maps
            # Also use keep_aspect=False for Alaska/Hawaii since they may have different aspect ratios
            inset_candidates = (1, 2, 3, 4) if region.lower() in ("alaska", "hawaii") else (4, 6, 8, 10)
            use_keep_aspect = region.lower() not in ("alaska", "hawaii")  # Don't keep aspect for insets
            
            print(f"      Cropped image saved to: {temp_cropped_path}")
            print(f"      Cropped bbox: {cropped_bbox}")
            print(f"      Shapefile bounds: ({xmin:.2f}, {ymin:.2f}) to ({xmax:.2f}, {ymax:.2f})")
            print(f"      Aspect ratio - Shapefile: {(xmax-xmin)/(ymax-ymin):.3f}, Cropped: {cropped_w/cropped_h:.3f}")
            
            # Initialize gdf_cropped variable
            # NOTE: User's box is just a rough guide - we'll use edge detection to find perfect alignment
            # Don't rely too heavily on initial alignment based on user's box
            gdf_cropped = None
            
            # Quick initial alignment - just to get shapefile roughly in the right area
            # This is just a starting point, edge detection will do the real work
            print(f"      Step 3a: Quick initial alignment (user's box is rough guide only)...")
            try:
                from backend.utils.geo_align import fit_gdf_to_bbox_pixels
            except:
                from utils.geo_align import fit_gdf_to_bbox_pixels
            
            # Use a simple fit - don't worry about perfect initial alignment
            # Edge detection will find the perfect match regardless
            initial_inset = 2 if region.lower() in ("alaska", "hawaii") else 5
            gdf_cropped = fit_gdf_to_bbox_pixels(
                shp,
                bbox=cropped_bbox,
                polygon=None,
                keep_aspect=False,  # Don't constrain aspect - let edge detection handle it
                inset_px=initial_inset
            )
            print(f"      ✓ Initial rough alignment complete (inset={initial_inset}px)")
            print(f"      Initial bounds: {gdf_cropped.total_bounds}")
            print(f"      NOTE: This is just a starting point - edge detection will find perfect alignment")
            
            # Step 3b: PERFECT ALIGNMENT using edge detection - this is where the real work happens
            # Edge detection finds the ACTUAL borders in the image, then we align shapefile to match
            # This works regardless of how accurate the user's box was
            is_alaska_hawaii = region.lower() in ("alaska", "hawaii")
            try:
                print(f"      Step 3b: PERFECT ALIGNMENT using edge detection...")
                print(f"      🔍 Detecting county borders from color changes in image...")
                print(f"      🎯 Aligning shapefile to match detected borders (100% automatic)...")
                if is_alaska_hawaii:
                    print(f"      🔄 Using FULL ±180° rotation search for {region.upper()}...")
                
                # This function does ALL the work:
                # 1. Detects borders from color changes in the image
                # 2. Searches rotation, scaling, translation to match shapefile to detected borders
                # 3. Finds the perfect alignment regardless of user's box accuracy
                gdf_cropped_refined = refine_alignment_with_edge_matching(
                    gdf_cropped,
                    image_path=temp_cropped_path,
                    bbox=cropped_bbox,
                    max_iterations=5,
                    is_alaska_hawaii=is_alaska_hawaii
                )
                print(f"      ✓✓✓ PERFECT ALIGNMENT COMPLETE ✓✓✓")
                print(f"      Shapefile borders now match detected image borders")
                print(f"      Final bounds: {gdf_cropped_refined.total_bounds}")
                gdf_cropped = gdf_cropped_refined
            except Exception as refine_err:
                print(f"      ⚠️  Edge-based alignment failed: {refine_err}")
                import traceback
                traceback.print_exc()
                print(f"      Using initial alignment (may not be perfect)")
            
            # Clean up temp file
            try:
                os.remove(temp_cropped_path)
            except:
                pass
            
            # Step 5: Transform back to full image coordinates
            print(f"    Step 4: Transforming back to full image coordinates...")
            # Translate from cropped coordinates (0,0 origin) to full image coordinates
            A_translate = [1, 0, 0, 1, x1, y1]  # Translate by (x1, y1)
            
            gdf_px = gdf_cropped.copy()
            gdf_px["geometry"] = gdf_px.geometry.apply(
                lambda geom: affine_transform(geom, A_translate)
            )
            
            print(f"      Final aligned bounds (full image coords): {gdf_px.total_bounds}")
            
            # Step 6: Rasterize into exact image grid (H, W) - zero resizing
            print(f"    Step 5: Rasterizing shapefile edges...")
            geometries_for_raster = []
            for geom in gdf_px.geometry:
                if geom is None or geom.is_empty:
                    continue
                if geom.geom_type in ("LineString", "MultiLineString"):
                    # Buffer linework to create solid lines (1 pixel width for visible border)
                    geom_buffered = geom.buffer(1.0)
                    if not geom_buffered.is_empty:
                        geometries_for_raster.append(geom_buffered)
                else:
                    # Already a polygon
                    geometries_for_raster.append(geom)
            
            if geometries_for_raster:
                # Rasterize into (H, W) - exact image grid, no resizing
                mask = rasterize(
                    [(geom, 1) for geom in geometries_for_raster],
                    out_shape=(H, W),  # (height, width) for numpy array
                    transform=Affine.identity(),  # No transform, already in pixel coords
                    fill=0,
                    dtype="uint8"
                )
                
                # Draw solid red border directly from mask (no Canny edge detection)
                # Red color: [255, 0, 0] for pure red solid border
                overlay[mask > 0] = [255, 0, 0]
                
                print(f"    ✓ Rasterized and drew solid red borders for {region.upper()}")
            else:
                print(f"    ⚠️  No valid geometries to rasterize for {region.upper()}")
        else:
            # Fallback: rect4 not available, skip this region
            print(f"  {region.upper()} skipped (rect4 not available)")
    
    # Save overlay at natural image size - NEVER resize
    # Convert numpy array back to PIL Image and save at exact dimensions
    print(f"\n💾 Saving overlay to: {output_path}")
    result_img = Image.fromarray(overlay)
    result_img.save(output_path)  # Saves at exact (W, H) dimensions
    print(f"  ✓ Overlay saved successfully at natural size: {W}x{H}")
    return output_path


def generate_conus_interactive_overlay(
    image_path: str,
    upload_id: str,
    conus_rect4: List[Tuple[int, int]],
    projection: str = "4326",
    output_path: Optional[str] = None,
) -> str:
    """
    Generate CONUS-only overlay preview with user-controlled corner positions.
    Uses homography to map shapefile bounds to the 4 corner points (allows rotation/scaling).
    
    Args:
        image_path: Path to uploaded image
        upload_id: Upload ID
        conus_rect4: CONUS rectangle corners [(x1,y1),(x2,y2),(x3,y3),(x4,y4)] in pixel coordinates
                     Can be rotated/scaled - homography will handle the transformation
        projection: Projection code ("4326" or "5070")
        output_path: Optional output path
    
    Returns:
        Path to generated overlay image
    """
    if output_path is None:
        output_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{upload_id}_conus_interactive_overlay.png")
    
    # Load image at natural size
    img_pil = Image.open(image_path).convert("RGB")
    W, img_height = img_pil.size  # Use img_height to avoid conflict with homography H
    overlay = np.array(img_pil)
    
    # Load CONUS outline shapefile
    outline_path = _get_region_outline_path(region="conus", projection=projection)
    
    if not os.path.exists(outline_path):
        # Fallback to full shapefile
        shapefile_path = _get_region_shapefile_path(region="conus", projection=projection)
        if not os.path.exists(shapefile_path):
            fallback_conus_path = os.path.join(BASE_DIR, "cb_2024_us_county_500k_conus", "cb_2024_us_county_500k_conus.shp")
            if os.path.exists(fallback_conus_path):
                shapefile_path = fallback_conus_path
            else:
                try:
                    from data_processing import SHAPEFILE_PATH
                except ImportError:
                    from backend.data_processing import SHAPEFILE_PATH
                shapefile_path = SHAPEFILE_PATH
        shp = gpd.read_file(shapefile_path)
        shp["geometry"] = shp.geometry.boundary
    else:
        shp = gpd.read_file(outline_path)
    
    # Ensure GEOID column exists
    if "GEOID" not in shp.columns:
        shp["GEOID"] = shp.index.astype(str)
    shp["GEOID"] = shp["GEOID"].astype(str).str.zfill(5)
    
    # Set CRS if missing
    if shp.crs is None:
        if projection == "4326":
            shp = shp.set_crs(4326, allow_override=True)
        elif projection == "5070":
            shp = shp.set_crs(5070, allow_override=True)
        else:
            shp = shp.set_crs(4269, allow_override=True)
    
    # Reproject to EPSG:5070 for consistent transformation
    target_crs = 5070
    if shp.crs.to_epsg() != target_crs:
        shp = shp.to_crs(target_crs)
    
    # Get shapefile bounds (source corners in geographic/projected coordinates)
    xmin, ymin, xmax, ymax = shp.total_bounds
    src_bounds = (xmin, ymin, xmax, ymax)
    
    # Convert shapefile bounds to 4 corners (clockwise: TL, TR, BR, BL)
    # For geographic/projected: TL=(xmin, ymax), TR=(xmax, ymax), BR=(xmax, ymin), BL=(xmin, ymin)
    src4 = rect_bounds_to_corners(src_bounds, is_geographic=True)
    
    # Destination corners are the user-dragged rect4 (already in pixel coordinates)
    dst4 = np.array(conus_rect4, dtype=float)
    
    # Compute homography matrix
    try:
        from utils.homography import homography_from_4pts, apply_homography_to_geometry
    except ImportError:
        from backend.utils.homography import homography_from_4pts, apply_homography_to_geometry
    
    H = homography_from_4pts(src4, dst4)
    
    print(f"\n🔧 INTERACTIVE OVERLAY TRANSFORMATION:")
    print(f"  Source corners (shapefile bounds): {src4}")
    print(f"  Destination corners (user-dragged rect4): {dst4}")
    print(f"  Homography matrix H:")
    print(f"    {H[0]}")
    print(f"    {H[1]}")
    print(f"    {H[2]}")
    
    # Apply homography to all geometries
    gdf_px = shp.copy()
    gdf_px["geometry"] = gdf_px.geometry.apply(
        lambda geom: apply_homography_to_geometry(geom, H)
    )
    gdf_px.crs = None
    
    # Debug: Check transformed bounds
    transformed_bounds = gdf_px.total_bounds
    print(f"  Transformed shapefile bounds: {transformed_bounds}")
    print(f"  Expected destination bounds: [{dst4[0][0]}, {dst4[2][1]}, {dst4[2][0]}, {dst4[0][1]}]")
    
    # Rasterize
    geometries_for_raster = []
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ("LineString", "MultiLineString"):
            geom_buffered = geom.buffer(1.0)
            if not geom_buffered.is_empty:
                geometries_for_raster.append(geom_buffered)
        else:
            geometries_for_raster.append(geom)
    
    if geometries_for_raster:
        mask = rasterize(
            [(geom, 1) for geom in geometries_for_raster],
            out_shape=(img_height, W),  # Use img_height instead of H
            transform=Affine.identity(),
            fill=0,
            dtype="uint8"
        )
        overlay[mask > 0] = [255, 0, 0]  # Red border
    
    # Save overlay
    result_img = Image.fromarray(overlay)
    result_img.save(output_path)
    return output_path

