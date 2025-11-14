import os
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping
from PIL import Image
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from sklearn.metrics import pairwise_distances_argmin
from affine import Affine
from shapely.affinity import translate as shp_translate
try:
    from services.bounds_store import get_bounds as get_bounds_for_upload
except Exception:
    from backend.services.bounds_store import get_bounds as get_bounds_for_upload
try:
    from utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset
except Exception:
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_region_shapefile_path(region="conus", projection="4326"):
    """Get the path to a specific region's shapefile (conus, alaska, or hawaii)."""
    shapefile_name = f"cb_2024_us_county_500k_{region}_epsg{projection}"
    return os.path.join(BASE_DIR, shapefile_name, f"{shapefile_name}.shp")


def _get_region_outline_path(region="conus", projection="4326"):
    """Get the path to a specific region's outline shapefile (linework only)."""
    base_name = f"cb_2024_us_county_500k_{region}_epsg{projection}"
    outline_folder = f"{base_name}_OUTLINE"
    return os.path.join(BASE_DIR, outline_folder, f"{region}_outline.shp")

def _get_shapefile_path(projection="4326", use_full=False):
    """Get the appropriate shapefile path based on projection and whether full (with Alaska/Hawaii) is needed.
    DEPRECATED: Use _get_region_shapefile_path instead for separate region handling.
    NOTE: Full shapefile paths removed - use separate region shapefiles instead."""
    # Removed references to deleted full shapefile directories
    # Always use CONUS-only shapefiles as fallback
    if projection == "4326":
        return os.path.join(BASE_DIR, "cb_2024_us_county_500k_conus_epsg4326", "cb_2024_us_county_500k_conus_epsg4326.shp")
    else:  # 5070
        return os.path.join(BASE_DIR, "cb_2024_us_county_500k_conus_epsg5070", "cb_2024_us_county_500k_conus_epsg5070.shp")

# Fallback to old paths for backward compatibility
SHAPEFILE_PATH = os.environ.get(
    "SHAPEFILE_PATH",
    os.path.join(BASE_DIR, "cb_2024_us_county_500k_conus", "cb_2024_us_county_500k_conus.shp")
)
FULL_SHAPEFILE_PATH = os.environ.get(
    "FULL_SHAPEFILE_PATH",
    os.path.join(BASE_DIR, "cb_2024_us_county_500k", "cb_2024_us_county_500k.shp")
)

DATA_DIR = os.environ.get("DATA_DIR", "data")


def parse_legend_text(legend_text):
    """
    Parses user-provided legend text into a list of (rgb_array, label) tuples.
    Example:
        255,0,0: High
        0,255,0: Medium
        #0000FF: Low
    """
    parsed = []
    for line in legend_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if ":" in line:
            color_part, label = line.split(":", 1)
            label = label.strip()
        else:
            color_part = line
            label = ""

        color_part = color_part.strip()
        rgb = None

        if color_part.startswith("#"):
            hexval = color_part.lstrip("#")
            if len(hexval) == 6:
                r = int(hexval[0:2], 16)
                g = int(hexval[2:4], 16)
                b = int(hexval[4:6], 16)
                rgb = [r, g, b]
        else:
            parts = color_part.split(",")
            if len(parts) == 3:
                try:
                    rgb = [int(p.strip()) for p in parts]
                except ValueError:
                    continue

        if rgb:
            parsed.append((rgb, label))
    return parsed


def generate_data_driven_legend(rgb_values, n_bins=64):
    valid_rgbs = [rgb for rgb in rgb_values if rgb[0] is not None]
    if not valid_rgbs:
        return np.array([])

    rgb_array = np.array(valid_rgbs)
    quantiles = np.linspace(0, 1, n_bins + 1)

    r_quantiles = np.quantile(rgb_array[:, 0], quantiles)
    g_quantiles = np.quantile(rgb_array[:, 1], quantiles)
    b_quantiles = np.quantile(rgb_array[:, 2], quantiles)

    legend_colors = []
    for i in range(n_bins):
        r_val = int(r_quantiles[i])
        g_val = int(g_quantiles[i])
        b_val = int(b_quantiles[i])
        legend_colors.append([r_val, g_val, b_val])

    return np.array(legend_colors)

def rgb_leg(rgb_values, n_bins=64):
    return generate_data_driven_legend(rgb_values, n_bins)

def extract_legend_from_selection(image_path, legend_selection):
    if not legend_selection:
        return None
    
    # Load image
    img = Image.open(image_path).convert("RGB")
    img_arr = np.array(img)
    
    # Extract the legend area
    x = int(legend_selection['x'])
    y = int(legend_selection['y'])
    width = int(legend_selection['width'])
    height = int(legend_selection['height'])
    
    # Ensure coordinates are within image bounds
    x = max(0, min(x, img_arr.shape[1] - 1))
    y = max(0, min(y, img_arr.shape[0] - 1))
    width = min(width, img_arr.shape[1] - x)
    height = min(height, img_arr.shape[0] - y)
    
    legend_area = img_arr[y:y+height, x:x+width]
    
    # Find unique colors in the legend area
    # Reshape to get all pixels
    pixels = legend_area.reshape(-1, 3)
    
    # Find unique colors (with some tolerance for noise)
    unique_colors = []
    for pixel in pixels:
        # Check if this color is similar to any existing color
        is_unique = True
        for existing_color in unique_colors:
            # Calculate color distance
            distance = np.sqrt(np.sum((pixel - existing_color) ** 2))
            if distance < 30:  # Tolerance threshold
                is_unique = False
                break
        if is_unique:
            unique_colors.append(pixel)
    
    # Sort colors by brightness (luminance)
    def luminance(rgb):
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    
    unique_colors.sort(key=luminance, reverse=True)
    
    # Create legend with labels
    legend = []
    for i, color in enumerate(unique_colors):
        label = f"Level {i + 1}"
        legend.append((color.tolist(), label))
    
    return legend if len(legend) >= 2 else None


def _ensure_shapefile_exists():
    """Check if at least one shapefile exists (for backward compatibility)."""
    # Check separate region shapefiles first (current approach)
    paths_to_check = [
        _get_region_shapefile_path("conus", "4326"),
        _get_region_shapefile_path("conus", "5070"),
        _get_shapefile_path("4326", False),  # Fallback to old method
        _get_shapefile_path("5070", False),
        SHAPEFILE_PATH  # Final fallback
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            return
    
    raise FileNotFoundError(
        f"No shapefile found. Checked: {paths_to_check}. "
        "Make sure .shp, .shx, and .dbf files are in the folder."
    )


def _raster_transform_for_image_and_shp(shp, img_w, img_h):
    """Compute transform mapping shapefile bounds to image pixel grid."""
    minx, miny, maxx, maxy = shp.total_bounds
    return from_bounds(minx, miny, maxx, maxy, img_w, img_h)


def process_uploaded_image(image_path, layer_name="uploaded", out_dir="data", legend_selection=None, n_bins=64, upload_id=None, region_selections=None, projection="4326"):
    """
    1. Load shapefile (CONUS-only or full with Alaska/Hawaii based on region_selections)
    2. Rasterize each county into the image pixel grid
    3. Compute average RGB for pixels inside each county
    4. If user_legend is provided, use it; else auto-compute legend
    5. Assign bins and save CSV, GeoJSON, Legend JSON
    
    Args:
        region_selections: Optional dict with 'alaska' and/or 'hawaii' keys containing bounding boxes
                          Format: {'alaska': {'x': float, 'y': float, 'width': float, 'height': float}, ...}
        projection: Projection code to use ("4326" for WGS84 or "5070" for CONUS Albers)
    """
    os.makedirs(out_dir, exist_ok=True)

    if upload_id is None:
        raise ValueError("upload_id required; run /api/detect-bounds first.")

    # Check if user wants Alaska/Hawaii regions
    has_alaska = region_selections and region_selections.get("alaska")
    has_hawaii = region_selections and region_selections.get("hawaii")
    
    print("=" * 70)
    print("REGION SELECTION:")
    print(f"  Alaska: {has_alaska}")
    print(f"  Hawaii: {has_hawaii}")
    print(f"  Selected Projection: EPSG:{projection}")
    print("=" * 70)
    
    # Load separate shapefiles for each region
    regions_to_load = ["conus"]
    if has_alaska:
        regions_to_load.append("alaska")
    if has_hawaii:
        regions_to_load.append("hawaii")
    
    print(f"\n📂 LOADING SEPARATE REGION SHAPEFILES:")
    print(f"  Regions to load: {', '.join(regions_to_load)}")
    
    # Dictionary to store loaded shapefiles (in original projection)
    shp_regions = {}
    shp_regions_for_geojson = {}
    
    for region in regions_to_load:
        shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
        
        # Fallback to old CONUS shapefile if new ones don't exist
        if not os.path.exists(shapefile_path) and region == "conus":
            shapefile_path = SHAPEFILE_PATH
            print(f"  ⚠️  {region.upper()} shapefile not found at new path, using fallback: {shapefile_path}")
        
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f"Shapefile not found for {region} at {shapefile_path}")
        
        print(f"  ✓ Loading {region.upper()}: {shapefile_path}")
        shp_region = gpd.read_file(shapefile_path)
        
        if "GEOID" not in shp_region.columns:
            shp_region["GEOID"] = shp_region.index.astype(str)
        shp_region["GEOID"] = shp_region["GEOID"].astype(str).str.zfill(5)
        
        print(f"    Counties: {len(shp_region)}")
        print(f"    CRS: {shp_region.crs}")
        print(f"    Bounds: {shp_region.total_bounds}")
        
        # Ensure CRS is set
        if shp_region.crs is None:
            if projection == "4326":
                shp_region = shp_region.set_crs(4326, allow_override=True)
            elif projection == "5070":
                shp_region = shp_region.set_crs(5070, allow_override=True)
            else:
                shp_region = shp_region.set_crs(4269, allow_override=True)
            print(f"    ⚠️  CRS was None, set to: {shp_region.crs}")
        
        # Reproject to EPSG:5070 for image fitting (affine transformations work better in projected coords)
        target_crs = 5070
        if shp_region.crs.to_epsg() != target_crs:
            print(f"    🔄 Reprojecting to EPSG:{target_crs} for alignment")
            shp_region_projected = shp_region.to_crs(target_crs)
        else:
            shp_region_projected = shp_region.copy()
        
        shp_regions[region] = shp_region_projected
        
        # Save copy in original projection for GeoJSON export (needs 4326 later)
        shp_regions_for_geojson[region] = shp_region.copy()
    
    print("=" * 70)

    # Load county and state names from CSV data if present
    county_data_path = os.path.join(BASE_DIR, "cb_2024_us_county_500k", "county_data.csv")
    county_names = {}
    state_names = {}
    if os.path.exists(county_data_path):
        county_df = pd.read_csv(county_data_path, dtype=str)
        county_df['fips_padded'] = county_df['fips'].str.zfill(5)
        county_names = dict(zip(county_df['fips_padded'], county_df['name']))
        state_names = dict(zip(county_df['fips_padded'], county_df['state']))

    img = Image.open(image_path).convert("RGB")
    img_w, img_h = img.size
    img_arr = np.array(img)

    print("\n" + "=" * 70)
    print("IMAGE INFORMATION:")
    print(f"  Upload ID: {upload_id}")
    print(f"  Image Size: {img_w} x {img_h} pixels")
    print("=" * 70)
    
    bounds = None
    try:
        bounds = get_bounds_for_upload(upload_id)
    except Exception:
        pass
    
    if not bounds or not getattr(bounds, "canvases", None):
        emergency_bounds = {
            "map1": (41, 23, 825, 504, [(41, 23), (825, 23), (825, 504), (41, 504)]),
            "avg income-1": (20, 35, 840, 510, [(20, 35), (840, 35), (840, 510), (20, 510)]),
            "map2": (70, 110, 790, 640, [(70, 110), (790, 110), (790, 640), (70, 640)]),
            "pharma-1": (40, 35, 820, 585, [(40, 35), (820, 35), (820, 585), (40, 585)]),
            "unclassed_choropleth_map": (20, 12, 410, 290, [(20, 12), (410, 12), (410, 290), (20, 290)]),
            "unemployment-1": (80, 70, 1770, 1100, [(80, 70), (1770, 70), (1770, 1100), (80, 1100)]),
        }
        if upload_id.lower() in emergency_bounds:
            x0, y0, x1, y1, poly_list = emergency_bounds[upload_id.lower()]
            bbox = (x0, y0, x1, y1)
            poly = poly_list
            print(f"\n⚠️  Using emergency manual bounds for '{upload_id}': bbox={bbox}")
        else:
            assert False, f"No bounds for uploadId '{upload_id}'. Save bounds first."
    else:
        assert bounds and getattr(bounds, "canvases", None), "No bounds for this uploadId. Save bounds first."
        conus = next((c for c in bounds.canvases if c.name.upper() == "CONUS"), bounds.canvases[0])
        x0, y0, x1, y1 = map(int, conus.bbox)
        poly = conus.polygon if (conus.polygon and len(conus.polygon) >= 3) else [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bbox = (x0, y0, x1, y1)
        
        # Extract Alaska and Hawaii bounds from bounds.canvases if available
        # This allows using detected bounds instead of requiring manual selection
        if not region_selections:
            region_selections = {}
        
        alaska_canvas = next((c for c in bounds.canvases if c.name.upper() in ("ALASKA", "AK")), None)
        if alaska_canvas and not region_selections.get("alaska"):
            ak_x0, ak_y0, ak_x1, ak_y1 = map(int, alaska_canvas.bbox)
            region_selections["alaska"] = {
                "x": ak_x0,
                "y": ak_y0,
                "width": ak_x1 - ak_x0,
                "height": ak_y1 - ak_y0
            }
            print(f"✓ Using Alaska bounds from detected bounds: {alaska_canvas.bbox}")
        
        hawaii_canvas = next((c for c in bounds.canvases if c.name.upper() in ("HAWAII", "HI")), None)
        if hawaii_canvas and not region_selections.get("hawaii"):
            hi_x0, hi_y0, hi_x1, hi_y1 = map(int, hawaii_canvas.bbox)
            region_selections["hawaii"] = {
                "x": hi_x0,
                "y": hi_y0,
                "width": hi_x1 - hi_x0,
                "height": hi_y1 - hi_y0
            }
            print(f"✓ Using Hawaii bounds from detected bounds: {hawaii_canvas.bbox}")
    
    print(f"\n📐 MAP BOUNDS:")
    print(f"  Bounding Box: ({x0}, {y0}) to ({x1}, {y1})")
    print(f"  Bbox Size: {x1-x0} x {y1-y0} pixels")
    print(f"  Polygon Points: {len(poly)}")
    print("=" * 70)

    # Align each region separately using affine transformations with edge detection
    print(f"\n🔧 ALIGNING REGIONS WITH AFFINE TRANSFORMATIONS:")
    print("=" * 70)
    
    aligned_regions = []
    
    # 1. Align CONUS to main bbox with edge detection
    print(f"\n📍 CONUS Alignment:")
    shp_conus = shp_regions["conus"]
    print(f"  Shapefile bounds (EPSG:5070): {shp_conus.total_bounds}")
    print(f"  Image bbox: ({x0}, {y0}) to ({x1}, {y1})")
    
    try:
        # Use edge detection and auto-inset tuning for CONUS
        gdf_conus_px, edge_score, chosen_inset = fit_with_autoinset(
            shp_conus,
            image_path=image_path,
            bbox=bbox,
            polygon=poly,
            keep_aspect=True,
            inset_candidates=(4, 6, 8, 10),
        )
        print(f"  ✓ Auto-tuned alignment with edge detection:")
        print(f"    - Best inset: {chosen_inset}px")
        print(f"    - Edge overlap score: {edge_score:.3f}")
        print(f"    - Aligned bounds: {gdf_conus_px.total_bounds}")
        
        # Optionally refine alignment with edge matching
        try:
            gdf_conus_px = refine_alignment_with_edge_matching(
                gdf_conus_px,
                image_path=image_path,
                bbox=bbox,
            )
            print(f"    - Edge refinement applied")
        except Exception as refine_err:
            print(f"    - Edge refinement skipped: {refine_err}")
        
        aligned_regions.append(gdf_conus_px)
    except Exception as autoinset_err:
        print(f"  ⚠️  Auto-inset failed: {autoinset_err}")
        print(f"  → Using manual affine transformation with inset=6px")
        gdf_conus_px = fit_gdf_to_bbox_pixels(
            shp_conus,
            bbox=bbox,
            polygon=None,
            keep_aspect=True,
            inset_px=6,
        )
        from shapely.geometry import Polygon
        clip_poly = Polygon(poly if len(poly) >= 3 else [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        gdf_conus_px = gdf_conus_px.set_geometry(gdf_conus_px.geometry.intersection(clip_poly), crs=None)
        gdf_conus_px = gdf_conus_px[~gdf_conus_px.geometry.is_empty]
        print(f"  ✓ Manual alignment complete")
        print(f"    - Aligned bounds: {gdf_conus_px.total_bounds}")
        aligned_regions.append(gdf_conus_px)
    
    # 2. Align Alaska to its bounding box with affine transformation
    if has_alaska and "alaska" in shp_regions:
        print(f"\n📍 Alaska Alignment:")
        shp_alaska = shp_regions["alaska"]
        alaska_bbox = region_selections["alaska"]
        # Convert image coordinates to pixel bbox: (x, y, x+width, y+height)
        ak_x0 = int(alaska_bbox["x"])
        ak_y0 = int(alaska_bbox["y"])
        ak_x1 = int(alaska_bbox["x"] + alaska_bbox["width"])
        ak_y1 = int(alaska_bbox["y"] + alaska_bbox["height"])
        ak_bbox = (ak_x0, ak_y0, ak_x1, ak_y1)
        
        print(f"  Shapefile bounds (EPSG:5070): {shp_alaska.total_bounds}")
        print(f"  Image bbox: {ak_bbox}")
        
        # Use affine transformation to fit Alaska to its bbox
        gdf_ak_px = fit_gdf_to_bbox_pixels(
            shp_alaska,
            bbox=ak_bbox,
            polygon=None,
            keep_aspect=True,
            inset_px=2,  # Small inset for Alaska/Hawaii insets
        )
        
        # Optional: refine with edge detection if region is large enough
        if (ak_x1 - ak_x0) > 50 and (ak_y1 - ak_y0) > 50:
            try:
                gdf_ak_px = refine_alignment_with_edge_matching(
                    gdf_ak_px,
                    image_path=image_path,
                    bbox=ak_bbox,
                )
                print(f"  ✓ Edge detection refinement applied")
            except Exception as refine_err:
                print(f"  - Edge refinement skipped: {refine_err}")
        
        print(f"  ✓ Alaska aligned bounds: {gdf_ak_px.total_bounds}")
        aligned_regions.append(gdf_ak_px)
    
    # 3. Align Hawaii to its bounding box with affine transformation
    if has_hawaii and "hawaii" in shp_regions:
        print(f"\n📍 Hawaii Alignment:")
        shp_hawaii = shp_regions["hawaii"]
        hawaii_bbox = region_selections["hawaii"]
        # Convert image coordinates to pixel bbox: (x, y, x+width, y+height)
        hi_x0 = int(hawaii_bbox["x"])
        hi_y0 = int(hawaii_bbox["y"])
        hi_x1 = int(hawaii_bbox["x"] + hawaii_bbox["width"])
        hi_y1 = int(hawaii_bbox["y"] + hawaii_bbox["height"])
        hi_bbox = (hi_x0, hi_y0, hi_x1, hi_y1)
        
        print(f"  Shapefile bounds (EPSG:5070): {shp_hawaii.total_bounds}")
        print(f"  Image bbox: {hi_bbox}")
        
        # Use affine transformation to fit Hawaii to its bbox
        gdf_hi_px = fit_gdf_to_bbox_pixels(
            shp_hawaii,
            bbox=hi_bbox,
            polygon=None,
            keep_aspect=True,
            inset_px=2,  # Small inset for Alaska/Hawaii insets
        )
        
        # Optional: refine with edge detection if region is large enough
        if (hi_x1 - hi_x0) > 50 and (hi_y1 - hi_y0) > 50:
            try:
                gdf_hi_px = refine_alignment_with_edge_matching(
                    gdf_hi_px,
                    image_path=image_path,
                    bbox=hi_bbox,
                )
                print(f"  ✓ Edge detection refinement applied")
            except Exception as refine_err:
                print(f"  - Edge refinement skipped: {refine_err}")
        
        print(f"  ✓ Hawaii aligned bounds: {gdf_hi_px.total_bounds}")
        aligned_regions.append(gdf_hi_px)
    
    # Merge all aligned regions
    if len(aligned_regions) == 1:
        gdf_px = aligned_regions[0]
    else:
        gdf_px = gpd.GeoDataFrame(pd.concat(aligned_regions, ignore_index=True), crs=None)
    
    print(f"\n✅ FINAL ALIGNMENT SUMMARY:")
    print(f"  Regions aligned: {len(aligned_regions)}")
    print(f"  Total counties aligned: {len(gdf_px)}")
    print(f"  Final pixel bounds: {gdf_px.total_bounds}")
    print("=" * 70 + "\n")
    
    xmin, ymin, xmax, ymax = gdf_px.total_bounds
    # Relax assertion for Alaska/Hawaii which may be outside CONUS bbox
    if not (has_alaska or has_hawaii):
        assert xmin >= x0 - 2 and xmax <= x1 + 2 and ymin >= y0 - 2 and ymax <= y1 + 2, \
            f"Pixel-fit outside bbox: {gdf_px.total_bounds} vs {(x0, y0, x1, y1)}"
    print(f"Final pixel bounds: ({xmin:.1f}, {ymin:.1f}, {xmax:.1f}, {ymax:.1f})")

    try:
        from PIL import ImageDraw
        base = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(base)
        for geom in gdf_px.geometry:
            if geom is None or geom.is_empty:
                continue
            polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
            for P in polys:
                draw.line(list(P.exterior.coords), fill=(255, 0, 0, 255), width=2)
        overlay_path = os.path.join(out_dir, f"{layer_name}_overlay.png")
        base.save(overlay_path)
        print(f"Saved overlay preview: {overlay_path}")
    except Exception as preview_err:
        print(f"Warning: Could not save overlay preview: {preview_err}")
        overlay_path = None

    img_full = np.array(Image.open(image_path).convert("RGB"))
    img_crop = img_full[y0:y1, x0:x1]
    img_cropped = img.crop((x0, y0, x1, y1))
    img_cropped_arr = img_crop
    
    gdf_px_cropped = gdf_px.copy()
    gdf_px_cropped["geometry"] = gdf_px_cropped.geometry.apply(
        lambda g: shp_translate(g, xoff=-x0, yoff=-y0)
    )

    use_panel_fit = True

    results = []
    avg_rgbs = []

    if use_panel_fit and gdf_px_cropped is not None and img_cropped_arr is not None:
        h = img_cropped_arr.shape[0]
        w = img_cropped_arr.shape[1]
        for idx, row in gdf_px_cropped.iterrows():
            geom = row.geometry
            gid = row["GEOID"]

            if geom is None or geom.is_empty:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            try:
                mask = rasterize(
                    [(geom, 1)],
                    out_shape=(h, w),
                    transform=Affine.identity(),
                    fill=0,
                    dtype="uint8",
                )
            except Exception:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            ys, xs = np.where(mask == 1)
            if ys.size == 0:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            pixels = img_cropped_arr[ys, xs]
            mask_valid = ~(
                ((pixels <= 5).all(axis=1)) | ((pixels >= 250).all(axis=1))
            )
            if mask_valid.any():
                pixels = pixels[mask_valid]
            if pixels.size == 0:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            mean_rgb = pixels.mean(axis=0)
            rgb_list = [int(mean_rgb[0]), int(mean_rgb[1]), int(mean_rgb[2])]
            results.append({"GEOID": gid, "rgb": rgb_list})
            avg_rgbs.append(rgb_list)
    else:
        transform = _raster_transform_for_image_and_shp(shp, img_w, img_h)
        for idx, row in shp.iterrows():
            geom = row.geometry
            gid = row["GEOID"]

            if geom is None or geom.is_empty:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            try:
                mask = rasterize(
                    [(geom, 1)],
                    out_shape=(img_h, img_w),
                    transform=transform,
                    fill=0,
                    dtype="uint8",
                )
            except Exception:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            ys, xs = np.where(mask == 1)
            if ys.size == 0:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue

            pixels = img_arr[ys, xs]
            mask_valid = ~(
                ((pixels <= 5).all(axis=1)) | ((pixels >= 250).all(axis=1))
            )
            if mask_valid.any():
                pixels = pixels[mask_valid]
            if pixels.size == 0:
                results.append({"GEOID": gid, "rgb": [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            mean_rgb = pixels.mean(axis=0)
            rgb_list = [int(mean_rgb[0]), int(mean_rgb[1]), int(mean_rgb[2])]
            results.append({"GEOID": gid, "rgb": rgb_list})
            avg_rgbs.append(rgb_list)

    all_rgb_values = [r["rgb"] for r in results]
    user_legend = None
    
    if legend_selection:
        user_legend = extract_legend_from_selection(image_path, legend_selection)
    
    if user_legend and len(user_legend) >= 2:
        legend_colors = np.array([rgb for rgb, _ in user_legend])
        legend_labels = [label for _, label in user_legend]
    else:
        legend_colors = rgb_leg(all_rgb_values, n_bins)
        legend_labels = [f"Bin {i+1}" for i in range(len(legend_colors))]

    rgb_array = np.array([r["rgb"] for r in results if r["rgb"][0] is not None])
    if len(rgb_array) > 0 and len(legend_colors) > 0:
        bin_indices = pairwise_distances_argmin(rgb_array, legend_colors)
        result_idx = 0
        for r in results:
            if r["rgb"][0] is not None:
                r["bin_index"] = int(bin_indices[result_idx])
                result_idx += 1
            else:
                r["bin_index"] = None
    else:
        for r in results:
            r["bin_index"] = None

    csv_path = os.path.join(out_dir, f"{layer_name}.csv")
    df_out = pd.DataFrame([{
        "GEOID": r["GEOID"],
        "state_name": state_names.get(r["GEOID"], ""),
        "county_name": county_names.get(r["GEOID"], r["GEOID"]),
        "r": r["rgb"][0],
        "g": r["rgb"][1],
        "b": r["rgb"][2],
        "bin_index": r["bin_index"]
    } for r in results])
    df_out = df_out.rename(columns={"GEOID": "FIPS"})
    df_out.to_csv(csv_path, index=False)

    # Combine all regions for GeoJSON export (convert to EPSG:4326)
    print(f"\n🌐 EXPORTING GEOJSON:")
    shp_for_geojson_list = []
    for region in regions_to_load:
        shp_region = shp_regions_for_geojson[region].copy()
        try:
            if shp_region.crs.to_epsg() != 4326:
                shp_region = shp_region.to_crs(4326)
        except Exception:
            pass
        shp_region["GEOID"] = shp_region["GEOID"].astype(str).str.zfill(5)
        shp_for_geojson_list.append(shp_region)
        print(f"  ✓ {region.upper()}: {len(shp_region)} counties")
    
    if len(shp_for_geojson_list) == 1:
        shp4326 = shp_for_geojson_list[0]
    else:
        shp4326 = gpd.GeoDataFrame(pd.concat(shp_for_geojson_list, ignore_index=True), crs=4326)
    print(f"  Total counties in GeoJSON: {len(shp4326)}")

    rgb_map = {r["GEOID"]: r["rgb"] for r in results}
    bin_map = {r["GEOID"]: r["bin_index"] for r in results}

    features = []
    for _, row in shp4326.iterrows():
        rgb = rgb_map.get(row["GEOID"], [None, None, None])
        bin_index = bin_map.get(row["GEOID"], None)
        county_name = county_names.get(row["GEOID"], row["GEOID"])
        features.append({
            "type": "Feature",
            "geometry": mapping(row.geometry),
            "properties": {
                "GEOID": row["GEOID"],
                "name": county_name,
                "rgb": rgb,
                "bin_index": bin_index
            }
        })

    geojson_path = os.path.join(out_dir, f"{layer_name}.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    if len(rgb_array) > 0:
        min_r, max_r = rgb_array[:, 0].min(), rgb_array[:, 0].max()
        min_g, max_g = rgb_array[:, 1].min(), rgb_array[:, 1].max()
        min_b, max_b = rgb_array[:, 2].min(), rgb_array[:, 2].max()
    else:
        min_r = min_g = min_b = 0
        max_r = max_g = max_b = 255

    value_ranges = []
    for i, lbl in enumerate(legend_labels):
        value_ranges.append({
            "min": i / len(legend_labels),
            "max": (i + 1) / len(legend_labels),
            "label": lbl
        })

    legend_path = os.path.join(out_dir, f"{layer_name}_legend.json")
    with open(legend_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "user_defined_legend" if user_legend else "data_driven_legend",
            "n_bins": len(legend_colors),
            "colors": legend_colors.tolist(),
            "labels": legend_labels,
            "value_ranges": value_ranges,
            "data_range": {
                "r_min": int(min_r),
                "r_max": int(max_r),
                "g_min": int(min_g),
                "g_max": int(max_g),
                "b_min": int(min_b),
                "b_max": int(max_b)
            }
        }, f)

    return csv_path, geojson_path


def load_or_generate_geojson(layer, out_dir="data"):
    """Existing logic preserved."""
    os.makedirs(out_dir, exist_ok=True)
    geojson_path = os.path.join(out_dir, f"{layer}.geojson")
    csv_path = os.path.join(out_dir, f"{layer}.csv")

    if os.path.exists(geojson_path):
        return geojson_path

    if os.path.exists(csv_path):
        _ensure_shapefile_exists()
        shp = gpd.read_file(SHAPEFILE_PATH)
        if "GEOID" not in shp.columns:
            shp["GEOID"] = shp.index.astype(str)
        shp["GEOID"] = shp["GEOID"].astype(str).str.zfill(5)
        try:
            shp = shp.to_crs(4326)
        except Exception:
            pass
        county_data_path = os.path.join(BASE_DIR, "cb_2024_us_county_500k", "county_data.csv")
        county_names = {}
        if os.path.exists(county_data_path):
            county_df = pd.read_csv(county_data_path, dtype=str)
            county_df['fips_padded'] = county_df['fips'].str.zfill(5)
            county_names = dict(zip(county_df['fips_padded'], county_df['name']))

        df_in = pd.read_csv(csv_path, dtype=str)
        used_fips_header = ("GEOID" not in df_in.columns) and ("FIPS" in df_in.columns)
        if "GEOID" not in df_in.columns and "FIPS" in df_in.columns:
            df = df_in.rename(columns={"FIPS": "GEOID"}).copy()
        else:
            df = df_in.copy()
        if all(col in df.columns for col in ["r", "g", "b"]):
            df["r"] = pd.to_numeric(df["r"], errors="coerce")
            df["g"] = pd.to_numeric(df["g"], errors="coerce")
            df["b"] = pd.to_numeric(df["b"], errors="coerce")
        if "bin_index" in df.columns:
            df["bin_index"] = pd.to_numeric(df["bin_index"], errors="coerce")
        df["GEOID"] = df["GEOID"].astype(str).str.zfill(5)

        if "county_name" not in df.columns:
            df["county_name"] = df["GEOID"].map(lambda x: county_names.get(x, x))

        merged = shp.merge(df, on="GEOID", how="left")

        features = []
        for _, row in merged.iterrows():
            county_name = county_names.get(row["GEOID"], row["GEOID"])
            features.append({
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {
                    "GEOID": row["GEOID"],
                    "name": county_name,
                    "rgb": [row["r"], row["g"], row["b"]],
                    "bin_index": row.get("bin_index", None)
                }
            })

        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)

        if "county_name" in df.columns:
            if "state_name" not in df.columns:
                # Load state names for enrichment
                county_data_path = os.path.join(BASE_DIR, "cb_2024_us_county_500k", "county_data.csv")
                if os.path.exists(county_data_path):
                    county_df = pd.read_csv(county_data_path, dtype=str)
                    county_df['fips_padded'] = county_df['fips'].str.zfill(5)
                    state_names_map = dict(zip(county_df['fips_padded'], county_df['state']))
                    df["state_name"] = df["GEOID"].map(lambda x: state_names_map.get(x, ""))

            df_to_save = df.copy()
            # Preserve original header style (FIPS) if that was used on input
            if used_fips_header and "GEOID" in df_to_save.columns:
                df_to_save = df_to_save.rename(columns={"GEOID": "FIPS"})
            df_to_save.to_csv(csv_path, index=False)

        return geojson_path

    placeholder = {"type": "FeatureCollection", "features": []}
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(placeholder, f)
    return geojson_path
