# backend/app.py
import os
import re
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from data_processing import (
    process_uploaded_image,
    load_or_generate_geojson,
    parse_legend_text,
    SHAPEFILE_PATH,
)
try:
    from schemas.bounds import MapCanvasBounds
except Exception:
    from backend.schemas.bounds import MapCanvasBounds
try:
    from services.bounds_store import save_bounds, get_bounds
except Exception:
    from backend.services.bounds_store import save_bounds, get_bounds
try:
    from utils.panel_detect import detect_panel_bounds, generate_bounds_overlay
except Exception:
    from backend.utils.panel_detect import detect_panel_bounds, generate_bounds_overlay

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)


def _sanitize_upload_id(value: str) -> str:
    if not value:
        return "upload"
    cleaned = "".join(c for c in value if (c.isalnum() or c in ("_", "-")))
    cleaned = cleaned.strip().lower()
    return cleaned or "upload"


@app.route("/api/process", methods=["POST"])
def process_image_endpoint():
    """
    Accept multipart/form-data with 'file' (image), optional 'layer', 'n_clusters', and optional 'legend_text'.
    Returns JSON with csv and geojson filenames and layer name.
    """
    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    f = request.files["file"]
    layer = request.form.get("layer", "uploaded").strip() or "uploaded"
    # sanitize layer: keep alnum, underscore, hyphen
    layer = "".join(c for c in layer if (c.isalnum() or c in ("_", "-"))).lower()

    try:
        n_clusters = int(request.form.get("n_clusters", 6))
    except Exception:
        n_clusters = 6

    # 🆕 Read legend selection if provided
    legend_selection = None
    legend_selection_str = request.form.get("legend_selection", "").strip()
    if legend_selection_str:
        try:
            legend_selection = json.loads(legend_selection_str)
        except Exception as e:
            return jsonify({"error": f"Failed to parse legend selection: {str(e)}"}), 400

    # 🆕 Read region selections (Alaska/Hawaii) if provided
    region_selections = None
    region_selections_str = request.form.get("region_selections", "").strip()
    if region_selections_str:
        try:
            region_selections = json.loads(region_selections_str)
        except Exception as e:
            return jsonify({"error": f"Failed to parse region selections: {str(e)}"}), 400

    # 🆕 Read projection selection (4326 or 5070)
    projection = request.form.get("projection", "4326").strip()
    if projection not in ("4326", "5070"):
        projection = "4326"  # Default to 4326

    # 🆕 Read legend type info if provided
    legend_type_info = None
    legend_type_info_str = request.form.get("legend_type_info", "").strip()
    if legend_type_info_str:
        try:
            legend_type_info = json.loads(legend_type_info_str)
        except Exception as e:
            return jsonify({"error": f"Failed to parse legend type info: {str(e)}"}), 400

    upload_id_raw = request.form.get("upload_id") or os.path.splitext(f.filename)[0]
    upload_id = _sanitize_upload_id(upload_id_raw)
    ext = os.path.splitext(f.filename)[1].lower() or ".png"
    saved_img = os.path.join(DATA_DIR, f"{upload_id}{ext}")
    f.save(saved_img)

    try:
        # 🆕 Pass legend_selection, region_selections, projection, and legend_type_info to processing function
        csv_path, geojson_path = process_uploaded_image(
            image_path=saved_img,
            layer_name=layer,
            out_dir=DATA_DIR,
            legend_selection=legend_selection,
            n_bins=n_clusters,
            upload_id=upload_id,
            region_selections=region_selections,
            projection=projection,
            legend_type_info=legend_type_info
        )

        return jsonify({
            "status": "ok",
            "csv": os.path.basename(csv_path),
            "geojson": os.path.basename(geojson_path),
            "layer": layer,
            "uploadId": upload_id
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/choropleth/<layer>", methods=["GET"])
def get_choropleth(layer):
    """
    Return the generated GeoJSON for a layer (data/{layer}.geojson).
    """
    path = os.path.join(DATA_DIR, f"{layer}.geojson")
    if not os.path.exists(path):
        # attempt to generate if CSV exists
        try:
            path = load_or_generate_geojson(layer, out_dir=DATA_DIR)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/legend/<layer>", methods=["GET"])
def get_legend(layer):
    """
    Return the RGB legend for a layer (data/{layer}_legend.json).
    """
    path = os.path.join(DATA_DIR, f"{layer}_legend.json")
    if not os.path.exists(path):
        return jsonify({"error": "Legend not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/download/<path:fname>", methods=["GET"])
def download_file(fname):
    full = os.path.join(DATA_DIR, fname)
    if not os.path.exists(full):
        return jsonify({"error": "not found"}), 404
    return send_file(full, as_attachment=True)


# 5) Serve preview overlays as images (not downloads)
@app.route("/data/<path:fname>", methods=["GET"])
def serve_data_file(fname):
    """Serve files from DATA_DIR (for overlays, images, etc.)"""
    full = os.path.join(DATA_DIR, fname)
    if not os.path.exists(full):
        return jsonify({"error": "not found"}), 404
    # Determine mimetype based on extension
    if fname.lower().endswith('.png'):
        return send_file(full, mimetype='image/png')
    elif fname.lower().endswith('.jpg') or fname.lower().endswith('.jpeg'):
        return send_file(full, mimetype='image/jpeg')
    elif fname.lower().endswith('.geojson'):
        return send_file(full, mimetype='application/json')
    elif fname.lower().endswith('.csv'):
        return send_file(full, mimetype='text/csv')
    return send_file(full)


@app.route("/api/bounds/<upload_id>", methods=["POST"])
def set_bounds(upload_id: str):
    safe_id = _sanitize_upload_id(upload_id)
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    # Handle corner format: convert to bbox format if needed
    # Support both formats:
    # 1. Full MapCanvasBounds with corners in canvases
    # 2. Simplified format with width/height/corners at top level
    
    # Check if simplified format (width/height/corners at top level)
    if "width" in payload and "height" in payload and "corners" in payload:
        corners = payload["corners"]
        top_left = corners.get("top_left", [])
        bottom_right = corners.get("bottom_right", [])
        
        # Convert to MapCanvasBounds format
        payload["type"] = "map_canvas_bounds"
        payload["image_size"] = {
            "width": payload["width"],
            "height": payload["height"]
        }
        # Build polygon from corners (use provided corners or compute from bbox)
        top_right = corners.get("top_right")
        bottom_left = corners.get("bottom_left")
        if not top_right:
            top_right = [bottom_right[0], top_left[1]]
        if not bottom_left:
            bottom_left = [top_left[0], bottom_right[1]]
        
        payload["canvases"] = [{
            "name": "CONUS",
            "bbox": [top_left[0], top_left[1], bottom_right[0], bottom_right[1]],
            "polygon": [
                list(top_left),
                list(top_right),
                list(bottom_right),
                list(bottom_left)
            ],
            "confidence": 0.95
        }]
        # Clean up old keys
        del payload["width"]
        del payload["height"]
        del payload["corners"]
    elif "canvases" in payload and payload["canvases"]:
        # Handle corners in existing canvases
        for canvas in payload["canvases"]:
            if "corners" in canvas and "bbox" not in canvas:
                # Convert corners to bbox
                corners = canvas["corners"]
                top_left = corners.get("top_left", [])
                bottom_right = corners.get("bottom_right", [])
                if len(top_left) >= 2 and len(bottom_right) >= 2:
                    canvas["bbox"] = [top_left[0], top_left[1], bottom_right[0], bottom_right[1]]
                    # Also create polygon from corners
                    if "polygon" not in canvas:
                        canvas["polygon"] = [
                            list(corners.get("top_left", [])),
                            list(corners.get("top_right", [bottom_right[0], top_left[1]])),
                            list(corners.get("bottom_right", [])),
                            list(corners.get("bottom_left", [top_left[0], bottom_right[1]]))
                        ]
                del canvas["corners"]  # Remove corners after conversion

    try:
        bounds = MapCanvasBounds(**payload)
    except Exception as e:
        return jsonify({"error": f"Schema validation failed: {str(e)}"}), 400

    if not bounds.canvases:
        return jsonify({"error": "No canvases provided"}), 400

    try:
        save_bounds(safe_id, bounds)
    except Exception as e:
        return jsonify({"error": f"Failed to save bounds: {str(e)}"}), 500

    return jsonify({"ok": True, "uploadId": safe_id, "panels": [c.name for c in bounds.canvases]})


@app.route("/api/bounds/<upload_id>", methods=["GET"])
def read_bounds(upload_id: str):
    safe_id = _sanitize_upload_id(upload_id)
    b = get_bounds(safe_id)
    if not b:
        return jsonify({"error": "Bounds not found"}), 404
    return jsonify(b.model_dump())

@app.route("/api/detect-bounds", methods=["POST"])
def detect_bounds_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "filename is required"}), 400

    upload_id = _sanitize_upload_id(
        request.form.get("upload_id") or os.path.splitext(file.filename)[0]
    )
    ext = os.path.splitext(file.filename)[1].lower() or ".png"
    saved_img = os.path.join(DATA_DIR, f"{upload_id}{ext}")
    file.save(saved_img)

    # Check if manual bounds already exist (confidence > 0.8 typically means manual)
    existing_bounds = get_bounds(upload_id)
    if existing_bounds and existing_bounds.canvases:
        # Use existing bounds if confidence suggests manual input
        if existing_bounds.canvases[0].confidence >= 0.75:
            bounds = existing_bounds
        else:
            # Run detection but only use it if no manual bounds
            try:
                bounds = detect_panel_bounds(saved_img)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                return jsonify({"error": f"Bounds detection failed: {str(e)}"}), 500
    else:
        # No existing bounds, run detection
        try:
            bounds = detect_panel_bounds(saved_img)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Bounds detection failed: {str(e)}"}), 500

    try:
        save_bounds(upload_id, bounds)
    except Exception as e:
        return jsonify({"error": f"Failed to save bounds: {str(e)}"}), 500

    overlay_filename = None
    overlay_error = None
    try:
        overlay_filename = f"{upload_id}_overlay.png"
        overlay_path = os.path.join(DATA_DIR, overlay_filename)
        generate_bounds_overlay(saved_img, bounds, SHAPEFILE_PATH, overlay_path)
    except Exception as e:
        overlay_error = str(e)
        overlay_filename = None

    response = {
        "uploadId": upload_id,
        "bounds": bounds.model_dump(),
    }

    if overlay_filename:
        response["overlayFilename"] = overlay_filename
        response["overlayUrl"] = f"/api/download/{overlay_filename}"
    if overlay_error:
        response["overlayError"] = overlay_error

    return jsonify(response)


@app.route("/api/bounds/<upload_id>/regenerate-overlay", methods=["POST"])
def regenerate_overlay_endpoint(upload_id: str):
    safe_id = _sanitize_upload_id(upload_id)
    bounds = get_bounds(safe_id)
    if not bounds:
        return jsonify({"error": "No bounds found for this upload_id"}), 404

    # Find the image file
    for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]:
        img_path = os.path.join(DATA_DIR, f"{safe_id}{ext}")
        if os.path.exists(img_path):
            break
    else:
        return jsonify({"error": "Image file not found"}), 404

    overlay_filename = None
    overlay_error = None
    try:
        overlay_filename = f"{safe_id}_overlay.png"
        overlay_path = os.path.join(DATA_DIR, overlay_filename)
        generate_bounds_overlay(img_path, bounds, SHAPEFILE_PATH, overlay_path)
    except Exception as e:
        overlay_error = str(e)
        overlay_filename = None

    response = {"uploadId": safe_id}
    if overlay_filename:
        response["overlayFilename"] = overlay_filename
        response["overlayUrl"] = f"/api/download/{overlay_filename}"
    if overlay_error:
        response["overlayError"] = overlay_error

    return jsonify(response)


@app.route("/api/generate-overlay-preview", methods=["POST"])
def generate_overlay_preview_endpoint():
    """Generate overlay preview with separate region shapefiles."""
    try:
        upload_id = request.form.get("upload_id")
        if not upload_id:
            return jsonify({"error": "upload_id required"}), 400
        
        safe_id = _sanitize_upload_id(upload_id)
        
        # Get bounds
        bounds = get_bounds(safe_id)
        if not bounds or not getattr(bounds, "canvases", None):
            return jsonify({"error": "No bounds found for this upload_id"}), 404
        
        conus = next((c for c in bounds.canvases if c.name.upper() == "CONUS"), bounds.canvases[0])
        x0, y0, x1, y1 = map(int, conus.bbox)
        # Ensure polygon is set - use bbox rectangle if not provided
        if conus.polygon and len(conus.polygon) >= 3:
            poly = conus.polygon
        else:
            poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bbox = (x0, y0, x1, y1)
        
        # Extract rect4 if available (new format), otherwise derive from bbox
        rect4 = None
        if hasattr(conus, 'rect4') and conus.rect4 and len(conus.rect4) == 4:
            rect4 = conus.rect4
        else:
            # Derive rect4 from bbox (clockwise: TL, TR, BR, BL)
            rect4 = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        
        # Get projection and region selections from form
        projection = request.form.get("projection", "4326").strip()
        if projection not in ("4326", "5070"):
            projection = "4326"
        
        region_selections = None
        region_selections_str = request.form.get("region_selections", "").strip()
        if region_selections_str:
            try:
                region_selections = json.loads(region_selections_str)
            except Exception as e:
                return jsonify({"error": f"Failed to parse region selections: {str(e)}"}), 400
        
        # Extract Alaska and Hawaii rect4 from bounds if available
        if not region_selections:
            region_selections = {}
        
        alaska_canvas = next((c for c in bounds.canvases if c.name.upper() in ("ALASKA", "AK")), None)
        hawaii_canvas = next((c for c in bounds.canvases if c.name.upper() in ("HAWAII", "HI")), None)
        
        if alaska_canvas and not region_selections.get("alaska"):
            # Use rect4 if available, otherwise derive from bbox
            if hasattr(alaska_canvas, 'rect4') and alaska_canvas.rect4 and len(alaska_canvas.rect4) == 4:
                alaska_rect4 = alaska_canvas.rect4
                ak_x0, ak_y0 = alaska_rect4[0]
                ak_x1, ak_y1 = alaska_rect4[2]
                region_selections["alaska_rect4"] = alaska_rect4
            else:
                ak_x0, ak_y0, ak_x1, ak_y1 = map(int, alaska_canvas.bbox)
            region_selections["alaska"] = {
                "x": ak_x0,
                "y": ak_y0,
                "width": ak_x1 - ak_x0,
                "height": ak_y1 - ak_y0
            }
        
        if hawaii_canvas and not region_selections.get("hawaii"):
            # Use rect4 if available, otherwise derive from bbox
            if hasattr(hawaii_canvas, 'rect4') and hawaii_canvas.rect4 and len(hawaii_canvas.rect4) == 4:
                hawaii_rect4 = hawaii_canvas.rect4
                hi_x0, hi_y0 = hawaii_rect4[0]
                hi_x1, hi_y1 = hawaii_rect4[2]
                region_selections["hawaii_rect4"] = hawaii_rect4
            else:
                hi_x0, hi_y0, hi_x1, hi_y1 = map(int, hawaii_canvas.bbox)
            region_selections["hawaii"] = {
                "x": hi_x0,
                "y": hi_y0,
                "width": hi_x1 - hi_x0,
                "height": hi_y1 - hi_y0
            }
        
        # Find the image file
        for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]:
            img_path = os.path.join(DATA_DIR, f"{safe_id}{ext}")
            if os.path.exists(img_path):
                break
        else:
            return jsonify({"error": "Image file not found"}), 404
        
        # Generate overlay preview
        try:
            from utils.overlay_preview import generate_region_overlay_preview
        except Exception:
            from backend.utils.overlay_preview import generate_region_overlay_preview
        
        overlay_filename = f"{safe_id}_preview_overlay.png"
        overlay_path = os.path.join(DATA_DIR, overlay_filename)
        
        # Verify image dimensions match bounds expectation
        from PIL import Image
        # Load image at natural size - NEVER resize
        test_img = Image.open(img_path)  # Loads at original dimensions
        img_w, img_h = test_img.size  # Natural dimensions from file
        expected_w = bounds.image_size.width
        expected_h = bounds.image_size.height
        
        print(f"\n🔍 OVERLAY PREVIEW REQUEST:")
        print(f"  Upload ID: {safe_id}")
        print(f"  Image file: {img_path}")
        print(f"  Image dimensions (natural): {img_w} x {img_h} pixels")
        print(f"  Expected dimensions (from bounds): {expected_w} x {expected_h} pixels")
        print(f"  Projection: EPSG:{projection}")
        print(f"  CONUS bbox: {bbox}")
        print(f"  CONUS rect4: {rect4}")
        print(f"  Region selections: {region_selections}")
        
        if img_w != expected_w or img_h != expected_h:
            print(f"  ⚠️  WARNING: Image size mismatch!")
            print(f"     Actual: {img_w}x{img_h}, Expected: {expected_w}x{expected_h}")
            print(f"     Using actual image size {img_w}x{img_h}")
        
        generate_region_overlay_preview(
            image_path=img_path,
            upload_id=safe_id,
            bounds_bbox=bbox,
            bounds_polygon=poly,
            bounds_rect4=rect4,
            projection=projection,
            region_selections=region_selections,
            output_path=overlay_path,
        )
        
        return jsonify({
            "status": "ok",
            "overlayFilename": overlay_filename,
            "overlayUrl": f"/data/{overlay_filename}"
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to generate overlay: {str(e)}"}), 500


@app.route("/api/shapefile-geojson", methods=["POST"])
def get_shapefile_geojson_endpoint():
    """Get shapefile coordinates as GeoJSON for client-side rendering."""
    try:
        upload_id = request.form.get("upload_id")
        if not upload_id:
            return jsonify({"error": "upload_id required"}), 400
        
        safe_id = _sanitize_upload_id(upload_id)
        projection = request.form.get("projection", "4326").strip()
        if projection not in ("4326", "5070"):
            projection = "4326"
        
        # Get region parameter (conus, alaska, or hawaii)
        region = request.form.get("region", "conus").strip().lower()
        if region not in ("conus", "alaska", "hawaii"):
            region = "conus"
        
        try:
            from utils.overlay_preview import _get_region_outline_path, _get_region_shapefile_path
            from data_processing import BASE_DIR
        except ImportError:
            from backend.utils.overlay_preview import _get_region_outline_path, _get_region_shapefile_path
            from backend.data_processing import BASE_DIR
        
        import geopandas as gpd
        
        # Load region outline shapefile
        outline_path = _get_region_outline_path(region=region, projection=projection)
        
        if not os.path.exists(outline_path):
            shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
            if not os.path.exists(shapefile_path):
                # Try fallback path for the specific region
                fallback_path = os.path.join(BASE_DIR, f"cb_2024_us_county_500k_{region}", f"cb_2024_us_county_500k_{region}.shp")
                if os.path.exists(fallback_path):
                    shapefile_path = fallback_path
                else:
                    # Last resort: use CONUS shapefile
                    try:
                        from data_processing import SHAPEFILE_PATH
                    except ImportError:
                        from backend.data_processing import SHAPEFILE_PATH
                    shapefile_path = SHAPEFILE_PATH
            shp = gpd.read_file(shapefile_path)
            shp["geometry"] = shp.geometry.boundary
        else:
            shp = gpd.read_file(outline_path)
        
        # Reproject to EPSG:5070
        target_crs = 5070
        if shp.crs is None:
            if projection == "4326":
                shp = shp.set_crs(4326, allow_override=True)
            elif projection == "5070":
                shp = shp.set_crs(5070, allow_override=True)
            else:
                shp = shp.set_crs(4269, allow_override=True)
        
        if shp.crs.to_epsg() != target_crs:
            shp = shp.to_crs(target_crs)
        
        # Get bounds for transformation reference
        xmin, ymin, xmax, ymax = shp.total_bounds
        bounds = {"xmin": float(xmin), "ymin": float(ymin), "xmax": float(xmax), "ymax": float(ymax)}
        
        # Convert to GeoJSON (simplified for performance)
        geojson = shp.to_json()
        
        return jsonify({
            "status": "ok",
            "geojson": json.loads(geojson),
            "bounds": bounds
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ ERROR in get-shapefile-geojson:")
        print(error_trace)
        return jsonify({"error": f"Failed to get shapefile GeoJSON: {str(e)}"}), 500

@app.route("/api/preview-overlay-interactive", methods=["POST"])
def preview_overlay_interactive_endpoint():
    """Generate interactive CONUS overlay with user-controlled rotation and scale."""
    try:
        upload_id = request.form.get("upload_id")
        if not upload_id:
            return jsonify({"error": "upload_id required"}), 400
        
        safe_id = _sanitize_upload_id(upload_id)
        
        # Get CONUS rect4 from form
        conus_rect4_str = request.form.get("conus_rect4", "").strip()
        if not conus_rect4_str:
            return jsonify({"error": "conus_rect4 required"}), 400
        
        try:
            conus_rect4 = json.loads(conus_rect4_str)
            if not isinstance(conus_rect4, list) or len(conus_rect4) != 4:
                return jsonify({"error": "conus_rect4 must be a list of 4 points"}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to parse conus_rect4: {str(e)}"}), 400
        
        # Get projection
        projection = request.form.get("projection", "4326").strip()
        if projection not in ("4326", "5070"):
            projection = "4326"
        
        # Find the image file
        for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]:
            img_path = os.path.join(DATA_DIR, f"{safe_id}{ext}")
            if os.path.exists(img_path):
                break
        else:
            return jsonify({"error": "Image file not found"}), 404
        
        # Generate interactive overlay using homography with 4 corner points
        try:
            from utils.overlay_preview import generate_conus_interactive_overlay
        except Exception:
            from backend.utils.overlay_preview import generate_conus_interactive_overlay
        
        overlay_filename = f"{safe_id}_conus_interactive_overlay.png"
        overlay_path = os.path.join(DATA_DIR, overlay_filename)
        
        generate_conus_interactive_overlay(
            image_path=img_path,
            upload_id=safe_id,
            conus_rect4=[tuple(p) for p in conus_rect4],
            projection=projection,
            output_path=overlay_path,
        )
        
        return jsonify({
            "status": "ok",
            "overlayFilename": overlay_filename,
            "overlayUrl": f"/data/{overlay_filename}"
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ ERROR in preview-overlay-interactive:")
        print(error_trace)
        print(f"Error message: {str(e)}\n")
        return jsonify({"error": f"Failed to generate interactive overlay: {str(e)}"}), 500


@app.route("/api/compute-alignment-from-counties", methods=["POST"])
def compute_alignment_from_counties_endpoint():
    """Compute alignment from 4 county selections using homography."""
    try:
        upload_id = request.form.get("upload_id")
        if not upload_id:
            return jsonify({"error": "upload_id required"}), 400
        
        safe_id = _sanitize_upload_id(upload_id)
        
        # Get selected points
        selected_points_str = request.form.get("selected_points", "").strip()
        if not selected_points_str:
            return jsonify({"error": "selected_points required"}), 400
        
        try:
            selected_points = json.loads(selected_points_str)
            # Both CONUS and Alaska use 4 points
            if not isinstance(selected_points, list) or len(selected_points) != 4:
                return jsonify({"error": "selected_points must be a list of 4 points"}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to parse selected_points: {str(e)}"}), 400
        
        # Get projection
        projection = request.form.get("projection", "4326").strip()
        if projection not in ("4326", "5070"):
            projection = "4326"
        
        # Find the image file
        for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"]:
            img_path = os.path.join(DATA_DIR, f"{safe_id}{ext}")
            if os.path.exists(img_path):
                break
        else:
            return jsonify({"error": "Image file not found"}), 404
        
        # Get region
        region = request.form.get("region", "conus").strip()
        if region not in ("conus", "alaska"):
            region = "conus"
        
        # Load shapefile
        try:
            from data_processing import _get_region_shapefile_path
        except Exception:
            from backend.data_processing import _get_region_shapefile_path
        
        shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
        if not os.path.exists(shapefile_path):
            # Fallback
            try:
                from data_processing import SHAPEFILE_PATH
            except Exception:
                from backend.data_processing import SHAPEFILE_PATH
            shapefile_path = SHAPEFILE_PATH
        
        import geopandas as gpd
        import numpy as np
        from shapely.geometry import Point
        
        shp = gpd.read_file(shapefile_path)
        
        # Handle different possible GEOID column names (for compatibility)
        if "GEOID" in shp.columns:
            shp["GEOID"] = shp["GEOID"].astype(str).str.zfill(5)
        elif "GEO_ID" in shp.columns:
            shp["GEOID"] = shp["GEO_ID"].astype(str).str.zfill(5)
        elif "COUNTYFP" in shp.columns and "STATEFP" in shp.columns:
            # Construct GEOID from STATEFP + COUNTYFP
            shp["GEOID"] = shp["STATEFP"].astype(str).str.zfill(2) + shp["COUNTYFP"].astype(str).str.zfill(3)
        else:
            # Create GEOID from index if no standard columns exist
            shp["GEOID"] = shp.index.astype(str).str.zfill(5)
        
        # Debug: Print available GEOIDs for troubleshooting
        print(f"  Loaded shapefile with {len(shp)} counties")
        print(f"  GEOID column sample: {shp['GEOID'].head(10).tolist()}")
        
        # Reproject to EPSG:5070 for calculations
        target_crs = 5070
        if shp.crs is None:
            if projection == "4326":
                shp = shp.set_crs(4326, allow_override=True)
            elif projection == "5070":
                shp = shp.set_crs(5070, allow_override=True)
        
        if shp.crs.to_epsg() != target_crs:
            shp = shp.to_crs(target_crs)
        
        # Get centroids of selected counties (source points in geographic/projected coords)
        src_points = []
        dst_points = []
        county_names = []
        
        for point in selected_points:
            geoid = str(point.get("geoid", "")).zfill(5)
            county = shp[shp["GEOID"] == geoid]
            
            if len(county) == 0:
                # Try to find similar GEOIDs for debugging
                similar_geoids = shp[shp["GEOID"].str.startswith(geoid[:2])]["GEOID"].head(5).tolist()
                error_msg = f"County with GEOID {geoid} not found in shapefile"
                if similar_geoids:
                    error_msg += f". Similar GEOIDs in same state: {similar_geoids}"
                return jsonify({"error": error_msg}), 400
            
            # Get centroid
            centroid = county.iloc[0].geometry.centroid
            src_points.append([centroid.x, centroid.y])
            
            # Destination point in pixel coordinates
            dst_points.append([float(point["x"]), float(point["y"])])
            
            # Store county name for debugging
            county_name = county.iloc[0].get("NAME", geoid)
            county_names.append(county_name)
        
        num_points = len(selected_points)
        
        # Validate we have points
        if num_points == 0:
            return jsonify({"error": "No points provided"}), 400
        if len(src_points) != num_points or len(dst_points) != num_points:
            return jsonify({"error": f"Mismatch: {num_points} selected points but {len(src_points)} src points and {len(dst_points)} dst points"}), 400
        
        # Convert to numpy arrays and validate shapes
        src_points_array = np.array(src_points, dtype=float)
        dst_points_array = np.array(dst_points, dtype=float)
        
        # Ensure 2D arrays (Nx2)
        if src_points_array.ndim == 1:
            src_points_array = src_points_array.reshape(-1, 2)
        if dst_points_array.ndim == 1:
            dst_points_array = dst_points_array.reshape(-1, 2)
        
        # Validate final shapes
        if src_points_array.shape != (num_points, 2):
            return jsonify({"error": f"src_points_array has wrong shape: {src_points_array.shape}, expected ({num_points}, 2)"}), 400
        if dst_points_array.shape != (num_points, 2):
            return jsonify({"error": f"dst_points_array has wrong shape: {dst_points_array.shape}, expected ({num_points}, 2)"}), 400
        
        # Debug: Print point correspondences and array info
        print(f"\n  Alignment point correspondences ({num_points} points):")
        print(f"  Array shapes: src_points_array={src_points_array.shape}, dst_points_array={dst_points_array.shape}")
        for i, (src, dst, name) in enumerate(zip(src_points_array, dst_points_array, county_names)):
            print(f"    Point {i+1} ({name}):")
            print(f"      Shapefile (EPSG:5070): ({src[0]:.2f}, {src[1]:.2f})")
            print(f"      Image (pixels): ({dst[0]:.2f}, {dst[1]:.2f})")
        
        # Additional validation: check for any invalid values
        if np.any(np.isnan(src_points_array)) or np.any(np.isinf(src_points_array)):
            return jsonify({"error": "src_points_array contains NaN or Inf values"}), 400
        if np.any(np.isnan(dst_points_array)) or np.any(np.isinf(dst_points_array)):
            return jsonify({"error": "dst_points_array contains NaN or Inf values"}), 400
        
        # Compute transformation - use TPS (Thin-Plate Spline) for better non-linear warping
        if num_points == 4:
            # Use TPS for 4 points (better for non-linear distortions)
            try:
                from utils.tps import tps_transform_from_points, apply_tps_to_geometry, verify_tps_accuracy
            except Exception:
                from backend.utils.tps import tps_transform_from_points, apply_tps_to_geometry, verify_tps_accuracy
            
            print(f"\n  Using Thin-Plate Spline (TPS) transformation for non-linear warping")
            print(f"  Shapefile is already in EPSG:5070 (flat projection) - good for TPS")
            
            # Create TPS transformation function
            tps_func = tps_transform_from_points(src_points_array, dst_points_array)
            transform_type = "tps"
            
            # Debug: Verify TPS by transforming source points back
            print(f"\n  TPS verification (transforming source points back):")
            max_error = verify_tps_accuracy(tps_func, src_points_array, dst_points_array)
            
            for i, (src, dst, name) in enumerate(zip(src_points_array, dst_points_array, county_names)):
                x_transformed, y_transformed = tps_func(src[0], src[1])
                error_x = abs(x_transformed - dst[0])
                error_y = abs(y_transformed - dst[1])
                error_total = np.sqrt(error_x**2 + error_y**2)
                print(f"    Point {i+1} ({name}):")
                print(f"      Expected: ({dst[0]:.2f}, {dst[1]:.2f})")
                print(f"      Got: ({x_transformed:.2f}, {y_transformed:.2f})")
                print(f"      Error: ({error_x:.2f}, {error_y:.2f}), Total: {error_total:.2f}px")
            
            if max_error > 50:
                print(f"  ⚠️  WARNING: Large TPS errors detected (max: {max_error:.2f}px)")
                print(f"     This may indicate misalignment. Check that:")
                print(f"     1. County points were clicked in the correct locations")
                print(f"     2. The clicked points match the county centroids")
                print(f"     3. The image coordinates are correct")
            else:
                print(f"  ✓ TPS accuracy is good (max error: {max_error:.2f}px)")
            
            # Get shapefile bounds and compute rect4 using TPS
            xmin, ymin, xmax, ymax = shp.total_bounds
            bounds_corners = np.array([
                [xmin, ymax],  # TL
                [xmax, ymax],  # TR
                [xmax, ymin],  # BR
                [xmin, ymin],  # BL
            ], dtype=float)
            
            print(f"\n  Shapefile bounds (EPSG:5070): xmin={xmin:.2f}, ymin={ymin:.2f}, xmax={xmax:.2f}, ymax={ymax:.2f}")
            
            # Transform bounds corners to pixel coordinates using TPS
            rect4 = []
            for i, corner in enumerate(bounds_corners):
                x, y = corner
                px, py = tps_func(x, y)
                rect4.append([int(round(px)), int(round(py))])
                corner_names = ["TL", "TR", "BR", "BL"]
                print(f"    Bounds corner {corner_names[i]}: ({x:.2f}, {y:.2f}) -> ({px:.2f}, {py:.2f})")
            
            print(f"  Computed rect4: {rect4}")
            
            # Store TPS function for later use in overlay generation
            H = tps_func  # Store as H for compatibility with existing code
        else:
            return jsonify({"error": f"Expected 4 points, got {num_points}"}), 400
        
        # Generate preview overlay
        if region == "conus":
            try:
                from utils.overlay_preview import generate_conus_interactive_overlay
            except Exception:
                from backend.utils.overlay_preview import generate_conus_interactive_overlay
            
            overlay_filename = f"{safe_id}_conus_aligned_preview.png"
            overlay_path = os.path.join(DATA_DIR, overlay_filename)
            
            generate_conus_interactive_overlay(
                image_path=img_path,
                upload_id=safe_id,
                conus_rect4=[tuple(p) for p in rect4],
                projection=projection,
                output_path=overlay_path,
            )
        else:
            # For Alaska, use interactive overlay generation (similar to CONUS)
            try:
                from utils.overlay_preview import generate_alaska_interactive_overlay
            except Exception:
                from backend.utils.overlay_preview import generate_alaska_interactive_overlay
            
            overlay_filename = f"{safe_id}_alaska_aligned_preview.png"
            overlay_path = os.path.join(DATA_DIR, overlay_filename)
            
            # Pass TPS function if using TPS, otherwise pass homography matrix
            if transform_type == "tps":
                generate_alaska_interactive_overlay(
                    image_path=img_path,
                    upload_id=safe_id,
                    alaska_rect4=[tuple(p) for p in rect4],
                    projection=projection,
                    output_path=overlay_path,
                    tps_func=tps_func,  # Pass TPS function for TPS transformation
                )
            else:
                generate_alaska_interactive_overlay(
                    image_path=img_path,
                    upload_id=safe_id,
                    alaska_rect4=[tuple(p) for p in rect4],
                    projection=projection,
                    output_path=overlay_path,
                    homography_matrix=H,  # Pass homography matrix for homography transformation
                )
        
        result = {
            "status": "ok",
            "rect4": rect4,
            "overlayUrl": f"/data/{overlay_filename}",
            "transform_type": transform_type,
            "src_points": src_points_array.tolist(),
            "dst_points": dst_points_array.tolist()
        }
        
        # Include transformation info (TPS function can't be serialized, but we have src/dst points)
        if transform_type == "tps":
            # Store source and destination points so TPS can be recomputed in data_processing
            result["tps_src_points"] = src_points_array.tolist()
            result["tps_dst_points"] = dst_points_array.tolist()
        elif H is not None:
            result["homography"] = H.tolist()
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ ERROR in compute-alignment-from-counties:")
        print(error_trace)
        print(f"Error message: {str(e)}\n")
        return jsonify({"error": f"Failed to compute alignment: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
