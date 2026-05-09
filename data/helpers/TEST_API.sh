#!/bin/bash
# Test script to verify bbox loading and processing
# Usage: ./TEST_API.sh <image_path>

IMAGE_PATH="${1:-/path/to/map1.png}"

echo "=== Step 1: Save bounds for map1 ==="
curl -X POST http://localhost:5001/api/bounds/map1 \
  -H "Content-Type: application/json" \
  -d '{
    "type": "map_canvas_bounds",
    "image_size": {"width": 864, "height": 527},
    "canvases": [{
      "name":"CONUS",
      "bbox":[41,23,825,504],
      "polygon":[[41,23],[825,23],[825,504],[41,504]],
      "confidence": 0.95
    }]
  }'

echo -e "\n\n=== Step 2: Process with SAME uploadId ==="
curl -X POST http://localhost:5001/api/process \
  -F "file=@${IMAGE_PATH}" \
  -F "layer=uploaded" \
  -F "upload_id=map1"

echo -e "\n\n=== Watch server logs for: ==="
echo "UPLOAD_ID: map1"
echo "USING BBOX: (41, 23, 825, 504)"
echo "Processing: Auto-tuned inset: ..."
echo "✓ Sanity check passed: ..."

