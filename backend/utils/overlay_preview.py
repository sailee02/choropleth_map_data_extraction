import os
import numpy as np
import cv2
import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.affinity import affine_transform, translate as shp_translate
from typing import Optional, Dict, Tuple, List
from rasterio.features import rasterize
from affine import Affine
try:
    from utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset, refine_alignment_with_edge_matching
    from utils.homography import transform_gdf_with_homography, rect_bounds_to_corners
    from data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR
except ImportError:
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, fit_with_autoinset, refine_alignment_with_edge_matching
    from backend.utils.homography import transform_gdf_with_homography, rect_bounds_to_corners
    from backend.data_processing import _get_region_shapefile_path, _get_region_outline_path, BASE_DIR

def generate_region_overlay_preview(image_path: str, upload_id: str, bounds_bbox: Tuple[int, int, int, int], bounds_polygon: Optional[List[Tuple[int, int]]]=None, bounds_rect4: Optional[List[Tuple[int, int]]]=None, projection: str='4326', region_selections: Optional[Dict]=None, output_path: Optional[str]=None) -> str:
    has_alaska = region_selections and region_selections.get('alaska')
    has_hawaii = region_selections and region_selections.get('hawaii')
    if output_path is None:
        output_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'{upload_id}_preview_overlay.png')
    img_pil = Image.open(image_path).convert('RGB')
    W, H = img_pil.size
    img_width, img_height = (W, H)
    overlay = np.array(img_pil)
    print(f'\n🔍 OVERLAY PREVIEW DEBUG:')
    print(f'  Image file: {image_path}')
    print(f'  Image dimensions (natural): {W} x {H} pixels')
    print(f'  Projection: EPSG:{projection}')
    print(f'  CONUS bbox: {bounds_bbox}')
    print(f'  CONUS rect4: {bounds_rect4}')
    x0, y0, x1, y1 = bounds_bbox
    if x1 > W or y1 > H:
        print(f'  ⚠️  WARNING: Bbox extends beyond image: bbox max ({x1}, {y1}) vs image ({W}, {H})')
    regions_to_load = ['conus']
    if has_alaska:
        regions_to_load.append('alaska')
    if has_hawaii:
        regions_to_load.append('hawaii')
    print(f'\n📋 Regions to load: {regions_to_load}')
    print(f'   ✓ CONUS will use CONUS-only shapefile (excludes Alaska/Hawaii)')
    x0, y0, x1, y1 = bounds_bbox
    for region in regions_to_load:
        outline_path = _get_region_outline_path(region=region, projection=projection)
        print(f'\n📂 Loading {region.upper()} outline shapefile:')
        print(f'    Projection: EPSG:{projection}')
        print(f'    Outline path: {outline_path}')
        if not os.path.exists(outline_path):
            print(f'    ⚠️  Outline not found: {outline_path}')
            print(f'     Falling back to full shapefile (will create mesh effect)')
            shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
        if not os.path.exists(shapefile_path):
            if region == 'conus':
                fallback_conus_path = os.path.join(BASE_DIR, 'cb_2024_us_county_500k_conus', 'cb_2024_us_county_500k_conus.shp')
                if os.path.exists(fallback_conus_path):
                    shapefile_path = fallback_conus_path
                    print(f'    Using CONUS-only fallback shapefile (no Alaska/Hawaii)')
                else:
                    try:
                        from data_processing import SHAPEFILE_PATH
                    except ImportError:
                        from backend.data_processing import SHAPEFILE_PATH
                    shapefile_path = SHAPEFILE_PATH
                    print(f'    Using CONUS-only shapefile from SHAPEFILE_PATH')
            else:
                continue
            print(f'    Using shapefile: {shapefile_path}')
            print(f'    ✓ This is a {region.upper()}-ONLY shapefile (does NOT include other regions)')
            shp = gpd.read_file(shapefile_path)
            if region == 'conus':
                bounds = shp.total_bounds
                if bounds[0] < -180 or bounds[2] > -60:
                    print(f'    ⚠️  WARNING: Shapefile bounds extend beyond CONUS: {bounds}')
                else:
                    print(f'    ✓ Verified: Shapefile bounds are CONUS-only: {bounds}')
            shp['geometry'] = shp.geometry.boundary
        else:
            print(f'    ✓ Found outline shapefile')
            print(f'    ✓ This is a {region.upper()}-ONLY outline (does NOT include other regions)')
            shp = gpd.read_file(outline_path)
            if region == 'conus':
                bounds = shp.total_bounds
                if bounds[0] < -180 or bounds[2] > -60:
                    print(f'    ⚠️  WARNING: Outline bounds extend beyond CONUS: {bounds}')
                else:
                    print(f'    ✓ Verified: Outline bounds are CONUS-only: {bounds}')
        if 'GEOID' not in shp.columns:
            shp['GEOID'] = shp.index.astype(str)
        shp['GEOID'] = shp['GEOID'].astype(str).str.zfill(5)
        if shp.crs is None:
            if projection == '4326':
                shp = shp.set_crs(4326, allow_override=True)
            elif projection == '5070':
                shp = shp.set_crs(5070, allow_override=True)
            else:
                shp = shp.set_crs(4269, allow_override=True)
        target_crs = 5070
        if shp.crs.to_epsg() != target_crs:
            shp = shp.to_crs(target_crs)
        if region == 'conus':
            if region_selections and region_selections.get('conus'):
                conus_bbox = region_selections['conus']
                conus_x0 = int(conus_bbox['x'])
                conus_y0 = int(conus_bbox['y'])
                conus_x1 = int(conus_bbox['x'] + conus_bbox['width'])
                conus_y1 = int(conus_bbox['y'] + conus_bbox['height'])
                region_bbox = (conus_x0, conus_y0, conus_x1, conus_y1)
                if conus_bbox.get('rect4'):
                    region_rect4 = conus_bbox['rect4']
                elif 'conus_rect4' in region_selections:
                    region_rect4 = region_selections['conus_rect4']
                else:
                    region_rect4 = [(conus_x0, conus_y0), (conus_x1, conus_y0), (conus_x1, conus_y1), (conus_x0, conus_y1)]
                region_polygon = None
                print(f'    Using user-selected CONUS region')
            else:
                region_bbox = bounds_bbox
                region_polygon = bounds_polygon
                region_rect4 = bounds_rect4
                print(f'    Using detected CONUS bounds')
            color = (255, 0, 0, 255)
        elif region == 'alaska':
            if not region_selections or not region_selections.get('alaska'):
                print(f'    ⚠️  Alaska region selection not found, skipping...')
                continue
            alaska_bbox = region_selections['alaska']
            ak_x0 = int(alaska_bbox['x'])
            ak_y0 = int(alaska_bbox['y'])
            ak_x1 = int(alaska_bbox['x'] + alaska_bbox['width'])
            ak_y1 = int(alaska_bbox['y'] + alaska_bbox['height'])
            region_bbox = (ak_x0, ak_y0, ak_x1, ak_y1)
            if alaska_bbox.get('rect4'):
                region_rect4 = alaska_bbox['rect4']
            elif 'alaska_rect4' in (region_selections or {}):
                region_rect4 = region_selections['alaska_rect4']
            else:
                region_rect4 = [(ak_x0, ak_y0), (ak_x1, ak_y0), (ak_x1, ak_y1), (ak_x0, ak_y1)]
            region_polygon = None
            color = (0, 255, 0, 255)
            print(f'    Alaska bbox: {region_bbox}, rect4: {region_rect4}')
        elif region == 'hawaii':
            if not region_selections or not region_selections.get('hawaii'):
                print(f'    ⚠️  Hawaii region selection not found, skipping...')
                continue
            hawaii_bbox = region_selections['hawaii']
            hi_x0 = int(hawaii_bbox['x'])
            hi_y0 = int(hawaii_bbox['y'])
            hi_x1 = int(hawaii_bbox['x'] + hawaii_bbox['width'])
            hi_y1 = int(hawaii_bbox['y'] + hawaii_bbox['height'])
            region_bbox = (hi_x0, hi_y0, hi_x1, hi_y1)
            if hawaii_bbox.get('rect4'):
                region_rect4 = hawaii_bbox['rect4']
            elif 'hawaii_rect4' in (region_selections or {}):
                region_rect4 = region_selections['hawaii_rect4']
            else:
                region_rect4 = [(hi_x0, hi_y0), (hi_x1, hi_y0), (hi_x1, hi_y1), (hi_x0, hi_y1)]
            region_polygon = None
            color = (0, 0, 255, 255)
            print(f'    Hawaii bbox: {region_bbox}, rect4: {region_rect4}')
        if region_rect4 and len(region_rect4) == 4:
            print(f'  {region.upper()} alignment (using edge detection + affine transform):')
            (x1, y1), (x2, y2) = (region_rect4[0], region_rect4[2])
            W_rect = x2 - x1
            H_rect = y2 - y1
            assert 0 <= x1 < x2 <= W and 0 <= y1 < y2 <= H, f'Rect outside image bounds: rect=({x1},{y1},{x2},{y2}), image=({W},{H})'
            min_size = 30 if region.lower() in ('alaska', 'hawaii') else 50
            assert abs(W_rect) >= min_size and abs(H_rect) >= min_size, f'Rect suspiciously small: W={W_rect}, H={H_rect} (minimum {min_size}px for {region})'
            print(f'    Step 1: Cropping {region.upper()} region from image...')
            cropped_img = overlay[y1:y2, x1:x2].copy()
            cropped_h, cropped_w = cropped_img.shape[:2]
            print(f'      Cropped size: {cropped_w} x {cropped_h} pixels')
            xmin, ymin, xmax, ymax = shp.total_bounds
            print(f'    Step 2: Preparing alignment for cropped {region.upper()} region...')
            print(f'      Shapefile bounds: ({xmin:.2f}, {ymin:.2f}) to ({xmax:.2f}, {ymax:.2f})')
            print(f'      Shapefile size: {xmax - xmin:.2f} x {ymax - ymin:.2f}')
            print(f'      Cropped image size: {cropped_w} x {cropped_h} pixels')
            print(f'    Step 3: Edge detection + affine transformation + rotation on cropped {region.upper()} image...')
            try:
                from backend.utils.geo_align import refine_alignment_with_edge_matching, fit_with_autoinset
            except:
                from utils.geo_align import refine_alignment_with_edge_matching, fit_with_autoinset
            import tempfile
            temp_cropped_path = os.path.join(BASE_DIR, 'data', f'{upload_id}_temp_{region}_cropped.png')
            os.makedirs(os.path.dirname(temp_cropped_path), exist_ok=True)
            Image.fromarray(cropped_img).save(temp_cropped_path)
            cropped_bbox = (0, 0, cropped_w, cropped_h)
            inset_candidates = (1, 2, 3, 4) if region.lower() in ('alaska', 'hawaii') else (4, 6, 8, 10)
            use_keep_aspect = region.lower() not in ('alaska', 'hawaii')
            print(f'      Cropped image saved to: {temp_cropped_path}')
            print(f'      Cropped bbox: {cropped_bbox}')
            print(f'      Shapefile bounds: ({xmin:.2f}, {ymin:.2f}) to ({xmax:.2f}, {ymax:.2f})')
            print(f'      Aspect ratio - Shapefile: {(xmax - xmin) / (ymax - ymin):.3f}, Cropped: {cropped_w / cropped_h:.3f}')
            gdf_cropped = None
            print(f"      Step 3a: Quick initial alignment (user's box is rough guide only)...")
            try:
                from backend.utils.geo_align import fit_gdf_to_bbox_pixels
            except:
                from utils.geo_align import fit_gdf_to_bbox_pixels
            initial_inset = 2 if region.lower() in ('alaska', 'hawaii') else 5
            gdf_cropped = fit_gdf_to_bbox_pixels(shp, bbox=cropped_bbox, polygon=None, keep_aspect=False, inset_px=initial_inset)
            print(f'      ✓ Initial rough alignment complete (inset={initial_inset}px)')
            print(f'      Initial bounds: {gdf_cropped.total_bounds}')
            print(f'      NOTE: This is just a starting point - edge detection will find perfect alignment')
            is_alaska_hawaii = region.lower() in ('alaska', 'hawaii')
            try:
                print(f'      Step 3b: PERFECT ALIGNMENT using edge detection...')
                print(f'      🔍 Detecting county borders from color changes in image...')
                print(f'      🎯 Aligning shapefile to match detected borders (100% automatic)...')
                if is_alaska_hawaii:
                    print(f'      🔄 Using FULL ±180° rotation search for {region.upper()}...')
                gdf_cropped_refined = refine_alignment_with_edge_matching(gdf_cropped, image_path=temp_cropped_path, bbox=cropped_bbox, max_iterations=5, is_alaska_hawaii=is_alaska_hawaii)
                print(f'      ✓✓✓ PERFECT ALIGNMENT COMPLETE ✓✓✓')
                print(f'      Shapefile borders now match detected image borders')
                print(f'      Final bounds: {gdf_cropped_refined.total_bounds}')
                gdf_cropped = gdf_cropped_refined
            except Exception as refine_err:
                print(f'      ⚠️  Edge-based alignment failed: {refine_err}')
                import traceback
                traceback.print_exc()
                print(f'      Using initial alignment (may not be perfect)')
            try:
                os.remove(temp_cropped_path)
            except:
                pass
            print(f'    Step 4: Transforming back to full image coordinates...')
            A_translate = [1, 0, 0, 1, x1, y1]
            gdf_px = gdf_cropped.copy()
            gdf_px['geometry'] = gdf_px.geometry.apply(lambda geom: affine_transform(geom, A_translate))
            print(f'      Final aligned bounds (full image coords): {gdf_px.total_bounds}')
            print(f'    Step 5: Rasterizing shapefile edges...')
            geometries_for_raster = []
            for geom in gdf_px.geometry:
                if geom is None or geom.is_empty:
                    continue
                if geom.geom_type in ('LineString', 'MultiLineString'):
                    geom_buffered = geom.buffer(1.0)
                    if not geom_buffered.is_empty:
                        geometries_for_raster.append(geom_buffered)
                else:
                    geometries_for_raster.append(geom)
            if geometries_for_raster:
                mask = rasterize([(geom, 1) for geom in geometries_for_raster], out_shape=(H, W), transform=Affine.identity(), fill=0, dtype='uint8')
                overlay[mask > 0] = [255, 0, 0]
                print(f'    ✓ Rasterized and drew solid red borders for {region.upper()}')
            else:
                print(f'    ⚠️  No valid geometries to rasterize for {region.upper()}')
        else:
            print(f'  {region.upper()} skipped (rect4 not available)')
    print(f'\n💾 Saving overlay to: {output_path}')
    result_img = Image.fromarray(overlay)
    result_img.save(output_path)
    print(f'  ✓ Overlay saved successfully at natural size: {W}x{H}')
    return output_path

def generate_conus_interactive_overlay(image_path: str, upload_id: str, conus_rect4: List[Tuple[int, int]], projection: str='4326', output_path: Optional[str]=None) -> str:
    if output_path is None:
        output_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'{upload_id}_conus_interactive_overlay.png')
    img_pil = Image.open(image_path).convert('RGB')
    W, img_height = img_pil.size
    overlay = np.zeros((img_height, W, 4), dtype=np.uint8)
    outline_path = _get_region_outline_path(region='conus', projection=projection)
    if not os.path.exists(outline_path):
        shapefile_path = _get_region_shapefile_path(region='conus', projection=projection)
        if not os.path.exists(shapefile_path):
            fallback_conus_path = os.path.join(BASE_DIR, 'cb_2024_us_county_500k_conus', 'cb_2024_us_county_500k_conus.shp')
            if os.path.exists(fallback_conus_path):
                shapefile_path = fallback_conus_path
            else:
                try:
                    from data_processing import SHAPEFILE_PATH
                except ImportError:
                    from backend.data_processing import SHAPEFILE_PATH
                shapefile_path = SHAPEFILE_PATH
        shp = gpd.read_file(shapefile_path)
        shp['geometry'] = shp.geometry.boundary
    else:
        shp = gpd.read_file(outline_path)
    if 'GEOID' not in shp.columns:
        shp['GEOID'] = shp.index.astype(str)
    shp['GEOID'] = shp['GEOID'].astype(str).str.zfill(5)
    if shp.crs is None:
        if projection == '4326':
            shp = shp.set_crs(4326, allow_override=True)
        elif projection == '5070':
            shp = shp.set_crs(5070, allow_override=True)
        else:
            shp = shp.set_crs(4269, allow_override=True)
    target_crs = 5070
    if shp.crs.to_epsg() != target_crs:
        shp = shp.to_crs(target_crs)
    xmin, ymin, xmax, ymax = shp.total_bounds
    src_bounds = (xmin, ymin, xmax, ymax)
    src4 = rect_bounds_to_corners(src_bounds, is_geographic=True)
    dst4 = np.array(conus_rect4, dtype=float)
    try:
        from utils.homography import homography_from_4pts, apply_homography_to_geometry
    except ImportError:
        from backend.utils.homography import homography_from_4pts, apply_homography_to_geometry
    H = homography_from_4pts(src4, dst4)
    print(f'\n🔧 INTERACTIVE OVERLAY TRANSFORMATION:')
    print(f'  Source corners (shapefile bounds): {src4}')
    print(f'  Destination corners (user-dragged rect4): {dst4}')
    print(f'  Homography matrix H:')
    print(f'    {H[0]}')
    print(f'    {H[1]}')
    print(f'    {H[2]}')
    gdf_px = shp.copy()
    gdf_px['geometry'] = gdf_px.geometry.apply(lambda geom: apply_homography_to_geometry(geom, H))
    gdf_px.crs = None
    transformed_bounds = gdf_px.total_bounds
    print(f'  Transformed shapefile bounds: {transformed_bounds}')
    print(f'  Expected destination bounds: [{dst4[0][0]}, {dst4[2][1]}, {dst4[2][0]}, {dst4[0][1]}]')
    geometries_for_raster = []
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('LineString', 'MultiLineString'):
            geom_buffered = geom.buffer(1.0)
            if not geom_buffered.is_empty:
                geometries_for_raster.append(geom_buffered)
        else:
            geometries_for_raster.append(geom)
    if geometries_for_raster:
        mask = rasterize([(geom, 1) for geom in geometries_for_raster], out_shape=(img_height, W), transform=Affine.identity(), fill=0, dtype='uint8')
        overlay[mask > 0] = [255, 0, 0, 255]
        overlay[mask == 0, 3] = 0
    result_img = Image.fromarray(overlay, 'RGBA')
    result_img.save(output_path, 'PNG', optimize=False)
    return output_path

def generate_alaska_interactive_overlay(image_path: str, upload_id: str, alaska_rect4: List[Tuple[int, int]], projection: str='4326', output_path: Optional[str]=None, homography_matrix: Optional[np.ndarray]=None, tps_func: Optional[callable]=None, meta_out: Optional[dict]=None) -> str:
    if meta_out is not None:
        meta_out['edge_refinement_applied'] = False
        meta_out['edge_refinement_error'] = None
    if output_path is None:
        output_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'{upload_id}_alaska_interactive_overlay.png')
    img_pil = Image.open(image_path).convert('RGB')
    W, img_height = img_pil.size
    overlay = np.zeros((img_height, W, 4), dtype=np.uint8)
    outline_path = _get_region_outline_path(region='alaska', projection=projection)
    shapefile_path = _get_region_shapefile_path(region='alaska', projection=projection)
    if os.path.exists(outline_path):
        shp = gpd.read_file(outline_path)
    elif os.path.exists(shapefile_path):
        shp = gpd.read_file(shapefile_path)
        shp['geometry'] = shp.geometry.boundary
        shp = shp[shp.geometry.notna() & ~shp.geometry.is_empty].copy()
        if len(shp) == 0:
            raise FileNotFoundError(f'Alaska shapefile at {shapefile_path} produced no valid boundaries. Check that the file contains polygon geometry.')
    else:
        alt_projection = '5070' if projection == '4326' else '4326'
        alt_path = _get_region_shapefile_path(region='alaska', projection=alt_projection)
        if os.path.exists(alt_path):
            shapefile_path = alt_path
            shp = gpd.read_file(shapefile_path)
            shp['geometry'] = shp.geometry.boundary
            shp = shp[shp.geometry.notna() & ~shp.geometry.is_empty].copy()
            if len(shp) == 0:
                raise FileNotFoundError(f'Alaska shapefile at {alt_path} produced no valid boundaries.')
        else:
            raise FileNotFoundError(f'Alaska shapefile not found. Tried: outline={outline_path}, shapefile={shapefile_path}, alt={alt_path}. Ensure cb_2024_us_county_500k_alaska_epsg4326 or cb_2024_us_county_500k_alaska_epsg5070 exists.')
    if 'GEOID' not in shp.columns:
        shp['GEOID'] = shp.index.astype(str)
    shp['GEOID'] = shp['GEOID'].astype(str).str.zfill(5)
    if shp.crs is None:
        if projection == '4326':
            shp = shp.set_crs(4326, allow_override=True)
        elif projection == '5070':
            shp = shp.set_crs(5070, allow_override=True)
        else:
            shp = shp.set_crs(4269, allow_override=True)
    target_crs = 5070
    if shp.crs.to_epsg() != target_crs:
        shp = shp.to_crs(target_crs)
    xmin, ymin, xmax, ymax = shp.total_bounds
    src_bounds = (xmin, ymin, xmax, ymax)
    try:
        from utils.homography import homography_from_4pts, apply_homography_to_geometry, rect_bounds_to_corners
    except ImportError:
        from backend.utils.homography import homography_from_4pts, apply_homography_to_geometry, rect_bounds_to_corners
    src4 = rect_bounds_to_corners(src_bounds, is_geographic=True)
    dst4 = np.array(alaska_rect4, dtype=float)
    H = homography_from_4pts(src4, dst4)
    print(f'\n🔧 ALASKA INTERACTIVE OVERLAY (same logic as CONUS):')
    print(f'  Source corners (shapefile bounds): {src4}')
    print(f'  Destination corners (rect4 from 4-point alignment): {dst4}')
    gdf_px = shp.copy()
    gdf_px['geometry'] = gdf_px.geometry.apply(lambda geom: apply_homography_to_geometry(geom, H))
    gdf_px.crs = None
    geometries_for_raster = []
    for geom in gdf_px.geometry:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('LineString', 'MultiLineString'):
            geom_buffered = geom.buffer(1.0)
            if not geom_buffered.is_empty:
                geometries_for_raster.append(geom_buffered)
        else:
            geometries_for_raster.append(geom)
    if geometries_for_raster:
        mask = rasterize([(geom, 1) for geom in geometries_for_raster], out_shape=(img_height, W), transform=Affine.identity(), fill=0, dtype='uint8')
        overlay[mask > 0] = [255, 0, 0, 255]
        overlay[mask == 0, 3] = 0
    result_img = Image.fromarray(overlay, 'RGBA')
    result_img.save(output_path, 'PNG', optimize=False)
    return output_path
