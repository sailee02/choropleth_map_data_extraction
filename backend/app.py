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

    upload_id_raw = request.form.get("upload_id") or os.path.splitext(f.filename)[0]
    upload_id = _sanitize_upload_id(upload_id_raw)
    ext = os.path.splitext(f.filename)[1].lower() or ".png"
    saved_img = os.path.join(DATA_DIR, f"{upload_id}{ext}")
    f.save(saved_img)

    try:
        # 🆕 Pass legend_selection, region_selections, and projection to processing function
        csv_path, geojson_path = process_uploaded_image(
            image_path=saved_img,
            layer_name=layer,
            out_dir=DATA_DIR,
            legend_selection=legend_selection,
            n_bins=n_clusters,
            upload_id=upload_id,
            region_selections=region_selections,
            projection=projection
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
