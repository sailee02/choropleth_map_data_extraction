








export function extractVerticesFromGeometry(geometry) {
  const vertices = [];
  
  if (!geometry || !geometry.coordinates) return vertices;
  
  const coords = geometry.coordinates;
  
  switch (geometry.type) {
    case 'Point':
      vertices.push(coords);
      break;
    case 'LineString':
      vertices.push(...coords);
      break;
    case 'Polygon':
      
      if (coords[0]) {
        vertices.push(...coords[0]);
      }
      break;
    case 'MultiPoint':
      vertices.push(...coords);
      break;
    case 'MultiLineString':
      coords.forEach(line => {
        vertices.push(...line);
      });
      break;
    case 'MultiPolygon':
      coords.forEach(polygon => {
        if (polygon[0]) {
          vertices.push(...polygon[0]);
        }
      });
      break;
  }
  
  return vertices;
}


function normalizeBoundsArray(bounds) {
  if (!bounds) return null;
  if (Array.isArray(bounds) && bounds.length === 4) {
    return bounds.map(Number);
  }
  if (typeof bounds === "object") {
    const { xmin, ymin, xmax, ymax } = bounds;
    if (
      xmin != null &&
      ymin != null &&
      xmax != null &&
      ymax != null
    ) {
      return [Number(xmin), Number(ymin), Number(xmax), Number(ymax)];
    }
  }
  return null;
}


function boundsToCornersProjected(boundsArr) {
  const [xmin, ymin, xmax, ymax] = boundsArr;
  return [
    [xmin, ymax],
    [xmax, ymax],
    [xmax, ymin],
    [xmin, ymin],
  ];
}

function computeHomographyFrom4Points(src4, dst4) {
  const A = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src4[i];
    const [X, Y] = dst4[i];
    A.push([x, y, 1, 0, 0, 0, -X * x, -X * y, -X]);
    A.push([0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y]);
  }

  const AtA = Array(9)
    .fill(0)
    .map(() => Array(9).fill(0));
  for (let i = 0; i < 8; i++) {
    for (let j = 0; j < 9; j++) {
      for (let k = 0; k < 9; k++) {
        AtA[j][k] += A[i][j] * A[i][k];
      }
    }
  }

  let v = Array(9)
    .fill(0)
    .map(() => Math.random() - 0.5);
  let norm = Math.sqrt(v.reduce((sum, x) => sum + x * x, 0));
  v = v.map((x) => x / norm);

  const epsilon = 1e-6;
  const I = Array(9)
    .fill(0)
    .map((_, i) =>
      Array(9)
        .fill(0)
        .map((_, j) => (i === j ? epsilon : 0))
    );

  for (let iter = 0; iter < 50; iter++) {
    const alpha = 0.01;
    const vNew = Array(9).fill(0);
    for (let i = 0; i < 9; i++) {
      let atAvI = 0;
      for (let j = 0; j < 9; j++) {
        atAvI += AtA[i][j] * v[j];
      }
      vNew[i] = v[i] - alpha * atAvI;
    }
    norm = Math.sqrt(vNew.reduce((sum, x) => sum + x * x, 0));
    if (norm < 1e-10) break;
    v = vNew.map((x) => x / norm);
  }

  const H = [
    [v[0], v[1], v[2]],
    [v[3], v[4], v[5]],
    [v[6], v[7], v[8]],
  ];
  const scale = H[2][2];
  if (Math.abs(scale) < 1e-10) {
    return [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ];
  }
  return H.map((row) => row.map((x) => x / scale));
}

function applyHomographyToXY(x, y, H) {
  const w = H[2][0] * x + H[2][1] * y + H[2][2];
  if (Math.abs(w) < 1e-10) return { x: 0, y: 0 };
  return {
    x: (H[0][0] * x + H[0][1] * y + H[0][2]) / w,
    y: (H[1][0] * x + H[1][1] * y + H[1][2]) / w,
  };
}





export function transformGeoJSONToPixelSpace(feature, alignmentData) {
  if (!alignmentData || !alignmentData.rect4 || !alignmentData.bounds) {
    return null;
  }

  const rect4 = alignmentData.rect4;
  if (!Array.isArray(rect4) || rect4.length !== 4) return null;

  const bounds = normalizeBoundsArray(alignmentData.bounds);
  if (!bounds) return null;

  const [xmin, ymin, xmax, ymax] = bounds;
  if (xmax <= xmin || ymax <= ymin) return null;

  const src4 = boundsToCornersProjected(bounds);
  const dst4 = rect4.map((p) => [Number(p[0]), Number(p[1])]);

  let H;
  try {
    H = computeHomographyFrom4Points(src4, dst4);
  } catch {
    H = null;
  }
  if (!H) return null;

  const vertices = extractVerticesFromGeometry(feature.geometry);
  return vertices.map(([x, y]) => applyHomographyToXY(x, y, H));
}








export function applyOverlayTransform(x, y, transform) {
  let tx = x;
  let ty = y;
  
  const centerX = transform.centerX || 0;
  const centerY = transform.centerY || 0;
  const scaleX = transform.scaleX || 1.0;
  const scaleY = transform.scaleY || 1.0;
  
  
  tx = centerX + (tx - centerX) * scaleX;
  ty = centerY + (ty - centerY) * scaleY;
  
  
  tx += transform.translateX || 0;
  ty += transform.translateY || 0;
  
  return { x: tx, y: ty };
}












export function computeTightBBoxFromGeoJSON(shapefileData, alignmentData, overlayTransform = {}, imageTransform = null) {
  if (!shapefileData || !alignmentData || !alignmentData.rect4 || !alignmentData.bounds) {
    return null;
  }
  
  
  let features = [];
  if (shapefileData.geojson && shapefileData.geojson.features) {
    features = shapefileData.geojson.features;
  } else if (shapefileData.features) {
    features = shapefileData.features;
  } else {
    return null;
  }
  
  if (features.length === 0) return null;
  
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  
  
  for (const feature of features) {
    const pixelVertices = transformGeoJSONToPixelSpace(feature, alignmentData);
    if (!pixelVertices || pixelVertices.length === 0) continue;
    
    for (const vertex of pixelVertices) {
      
      const transformed = applyOverlayTransform(vertex.x, vertex.y, overlayTransform);
      
      
      let displayX = transformed.x;
      let displayY = transformed.y;
      
      if (imageTransform) {
        displayX = transformed.x * imageTransform.scale + imageTransform.offsetX;
        displayY = transformed.y * imageTransform.scale + imageTransform.offsetY;
      }
      
      
      minX = Math.min(minX, displayX);
      minY = Math.min(minY, displayY);
      maxX = Math.max(maxX, displayX);
      maxY = Math.max(maxY, displayY);
    }
  }
  
  if (minX === Infinity) return null;
  
  return {
    minX,
    minY,
    maxX,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2
  };
}

