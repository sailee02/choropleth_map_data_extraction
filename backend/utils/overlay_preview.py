"""
Generate overlay preview showing shapefile boundaries on the uploaded image.
Uses separate region shapefiles (CONUS, Alaska, Hawaii) with affine transformations.
"""

import os
import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from typing import Optional, Dict, Tuple, List

try:
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset
    from backend.utils.homography import transform_gdf_with_homography
    from backend.data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR
except Exception:
    from utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset
    from utils.homography import transform_gdf_with_homography
    from data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR


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
    
    # Load image and verify dimensions
    base = Image.open(image_path).convert("RGBA")
    img_width, img_height = base.size
    
    # Assert image size matches expected dimensions
    expected_size = bounds_bbox  # This will be checked against image_size from bounds
    print(f"\n🔍 OVERLAY PREVIEW DEBUG:")
    print(f"  Image file: {image_path}")
    print(f"  Image dimensions: {img_width} x {img_height} pixels")
    print(f"  CONUS bbox: {bounds_bbox}")
    
    # Verify image dimensions match bounds expectation
    if hasattr(bounds_bbox, '__len__') and len(bounds_bbox) == 4:
        x0, y0, x1, y1 = bounds_bbox
        if x1 > img_width or y1 > img_height:
            print(f"  ⚠️  WARNING: Bbox extends beyond image: bbox max ({x1}, {y1}) vs image ({img_width}, {img_height})")
    
    draw = ImageDraw.Draw(base)
    
    # Draw bounding boxes for debugging (optional - helps verify bbox positions)
    # Draw CONUS bbox outline
    x0, y0, x1, y1 = bounds_bbox
    draw.rectangle([x0, y0, x1, y1], outline=(255, 255, 0, 255), width=3)  # Yellow outline
    print(f"  ✓ Drew CONUS bbox outline (yellow): ({x0}, {y0}) to ({x1}, {y1})")
    
    # Load and align regions
    regions_to_load = ["conus"]
    if has_alaska:
        regions_to_load.append("alaska")
    if has_hawaii:
        regions_to_load.append("hawaii")
    
    x0, y0, x1, y1 = bounds_bbox
    
    for region in regions_to_load:
        # Load region OUTLINE shapefile (linework only, not full polygons)
        outline_path = _get_region_outline_path(region=region, projection=projection)
        
        if not os.path.exists(outline_path):
            print(f"  ⚠️  Outline not found: {outline_path}")
            print(f"     Falling back to full shapefile (will create mesh effect)")
            # Fallback to full shapefile if outline doesn't exist
            shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
            if not os.path.exists(shapefile_path):
                if region == "conus":
                    try:
                        from backend.data_processing import SHAPEFILE_PATH
                    except:
                        from data_processing import SHAPEFILE_PATH
                    shapefile_path = SHAPEFILE_PATH
                else:
                    continue  # Skip if shapefile doesn't exist
            shp = gpd.read_file(shapefile_path)
            # Extract boundary from polygons
            shp["geometry"] = shp.geometry.boundary
        else:
            # Use outline shapefile directly
            shp = gpd.read_file(outline_path)
        
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
            region_bbox = bounds_bbox
            region_polygon = bounds_polygon
            region_rect4 = bounds_rect4  # Use rect4 if provided
            color = (255, 0, 0, 255)  # Red for CONUS
        elif region == "alaska":
            alaska_bbox = region_selections["alaska"]
            ak_x0 = int(alaska_bbox["x"])
            ak_y0 = int(alaska_bbox["y"])
            ak_x1 = int(alaska_bbox["x"] + alaska_bbox["width"])
            ak_y1 = int(alaska_bbox["y"] + alaska_bbox["height"])
            region_bbox = (ak_x0, ak_y0, ak_x1, ak_y1)
            # Convert bbox to rect4 (clockwise: TL, TR, BR, BL)
            region_rect4 = [(ak_x0, ak_y0), (ak_x1, ak_y0), (ak_x1, ak_y1), (ak_x0, ak_y1)]
            region_polygon = None
            color = (0, 255, 0, 255)  # Green for Alaska
        elif region == "hawaii":
            hawaii_bbox = region_selections["hawaii"]
            hi_x0 = int(hawaii_bbox["x"])
            hi_y0 = int(hawaii_bbox["y"])
            hi_x1 = int(hawaii_bbox["x"] + hawaii_bbox["width"])
            hi_y1 = int(hawaii_bbox["y"] + hawaii_bbox["height"])
            region_bbox = (hi_x0, hi_y0, hi_x1, hi_y1)
            # Convert bbox to rect4 (clockwise: TL, TR, BR, BL)
            region_rect4 = [(hi_x0, hi_y0), (hi_x1, hi_y0), (hi_x1, hi_y1), (hi_x0, hi_y1)]
            region_polygon = None
            color = (0, 0, 255, 255)  # Blue for Hawaii
        
        # Use homography transformation with rect4 if available
        if region_rect4 and len(region_rect4) == 4:
            print(f"  {region.upper()} alignment (using homography with rect4):")
            print(f"    Rect4: {region_rect4}")
            
            # Get shapefile bounds in its native CRS
            src_bounds = shp.total_bounds  # [xmin, ymin, xmax, ymax]
            print(f"    Shapefile bounds: {src_bounds}")
            
            # Transform using homography
            gdf_px = transform_gdf_with_homography(shp, src_bounds, region_rect4)
            print(f"    ✓ Homography transformation applied")
            print(f"    Aligned bounds: {gdf_px.total_bounds}")
        else:
            # Fallback to affine transformation (legacy)
            print(f"  {region.upper()} alignment (using affine, rect4 not available):")
            x0, y0, x1, y1 = region_bbox
            print(f"    Bbox: ({x0}, {y0}) to ({x1}, {y1})")
            
            if region == "conus":
                try:
                    gdf_px, edge_score, chosen_inset = fit_with_autoinset(
                        shp,
                        image_path=image_path,
                        bbox=region_bbox,
                        polygon=region_polygon,
                        keep_aspect=True,
                        inset_candidates=(4, 6, 8, 10),
                    )
                    print(f"    ✓ Auto-inset alignment: inset={chosen_inset}px, score={edge_score:.3f}")
                    if region_polygon and len(region_polygon) >= 3:
                        clip_poly = Polygon(region_polygon)
                    else:
                        clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
                    gdf_px = gdf_px.copy()
                    gdf_px["geometry"] = gdf_px.geometry.intersection(clip_poly)
                    gdf_px = gdf_px[~gdf_px.geometry.is_empty]
                except Exception as e:
                    print(f"    ⚠️  Auto-inset failed: {e}, using manual fit")
                    gdf_px = fit_gdf_to_bbox_pixels(
                        shp,
                        bbox=region_bbox,
                        polygon=None,
                        keep_aspect=True,
                        inset_px=6,
                    )
                    if region_polygon and len(region_polygon) >= 3:
                        clip_poly = Polygon(region_polygon)
                    else:
                        clip_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
                    gdf_px = gdf_px.copy()
                    gdf_px["geometry"] = gdf_px.geometry.intersection(clip_poly)
                    gdf_px = gdf_px[~gdf_px.geometry.is_empty]
            else:
                # Alaska/Hawaii: simpler affine alignment
                draw.rectangle([x0, y0, x1, y1], outline=(255, 255, 0, 255), width=2)
                gdf_px = fit_gdf_to_bbox_pixels(
                    shp,
                    bbox=region_bbox,
                    polygon=None,
                    keep_aspect=True,
                    inset_px=2,
                )
                print(f"    ✓ Fitted to bbox")
        
        # Draw boundaries (for outlines, these are LineStrings/MultiLineStrings)
        drawn_count = 0
        for geom in gdf_px.geometry:
            if geom is None or geom.is_empty:
                continue
            
            # Handle LineString/MultiLineString (from outline shapefiles)
            if geom.geom_type == "LineString":
                coords = list(geom.coords)
                if len(coords) >= 2:
                    draw.line(coords, fill=color, width=2)
                    drawn_count += 1
            elif geom.geom_type == "MultiLineString":
                for line in geom.geoms:
                    coords = list(line.coords)
                    if len(coords) >= 2:
                        draw.line(coords, fill=color, width=2)
                        drawn_count += 1
            else:
                # Fallback for Polygon/MultiPolygon (if using full shapefile)
                polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
                for poly in polys:
                    coords = list(poly.exterior.coords)
                    if len(coords) >= 2:
                        draw.line(coords, fill=color, width=2)
                        drawn_count += 1
        
        print(f"    ✓ Drew {drawn_count} line segments for {region.upper()}")
    
    # Save overlay
    print(f"\n💾 Saving overlay to: {output_path}")
    base.save(output_path)
    print(f"  ✓ Overlay saved successfully")
    return output_path

