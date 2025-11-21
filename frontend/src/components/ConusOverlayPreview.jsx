import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

export default function ConusOverlayPreview({ 
  imageUrl, 
  uploadId, 
  conusSelection, 
  projection = "4326",
  onConfirm, 
  onCancel 
}) {
  const [transformedRect4, setTransformedRect4] = useState(null);
  const [draggingCorner, setDraggingCorner] = useState(null);
  const [overlayUrl, setOverlayUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [shapefileData, setShapefileData] = useState(null); // GeoJSON + bounds
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);

  // Initialize transformedRect4 from conusSelection
  useEffect(() => {
    if (conusSelection && conusSelection.rect4 && !transformedRect4) {
      setTransformedRect4([...conusSelection.rect4]);
    }
  }, [conusSelection]);

  // Fetch shapefile GeoJSON for real-time preview
  useEffect(() => {
    if (!uploadId || shapefileData) return;

    const fetchShapefile = async () => {
      try {
        const formData = new FormData();
        formData.append('upload_id', uploadId);
        formData.append('projection', projection);

        const response = await fetch(`${API_ROOT}/api/shapefile-geojson`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error('Failed to fetch shapefile data');
        }

        const data = await response.json();
        setShapefileData(data);
      } catch (err) {
        console.error('Failed to fetch shapefile:', err);
      }
    };

    fetchShapefile();
  }, [uploadId, projection, shapefileData]);

  // Generate initial overlay when component mounts
  useEffect(() => {
    if (!conusSelection || !conusSelection.rect4 || !transformedRect4 || !uploadId) return;
    
    // Only generate initial overlay, not on every rect4 change
    const generateInitialOverlay = async () => {
      setLoading(true);
      setError(null);

      try {
        const formData = new FormData();
        formData.append('upload_id', uploadId);
        formData.append('conus_rect4', JSON.stringify(transformedRect4));
        formData.append('projection', projection);

        const response = await fetch(`${API_ROOT}/api/preview-overlay-interactive`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const errorText = await response.text();
          let errorData;
          try {
            errorData = JSON.parse(errorText);
          } catch {
            throw new Error(errorText || 'Failed to generate overlay');
          }
          throw new Error(errorData.error || 'Failed to generate overlay');
        }

        const data = await response.json();
        const baseUrl = data.overlayUrl.startsWith('http') 
          ? data.overlayUrl 
          : `${API_ROOT}${data.overlayUrl}`;
        const url = `${baseUrl}?t=${Date.now()}`;
        setOverlayUrl(url);
        setImageLoaded(false);
      } catch (err) {
        setError(err.message);
        console.error('Overlay generation error:', err);
      } finally {
        setLoading(false);
      }
    };

    // Only generate on initial mount
    if (!overlayUrl) {
      generateInitialOverlay();
    }
  }, [uploadId, projection, conusSelection]); // Removed transformedRect4 from dependencies

  // Manual overlay generation function
  const handleGenerateOverlay = async () => {
    if (!conusSelection || !conusSelection.rect4 || !transformedRect4 || !uploadId) return;

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('conus_rect4', JSON.stringify(transformedRect4));
      formData.append('projection', projection);

      const response = await fetch(`${API_ROOT}/api/preview-overlay-interactive`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorData;
        try {
          errorData = JSON.parse(errorText);
        } catch {
          throw new Error(errorText || 'Failed to generate overlay');
        }
        throw new Error(errorData.error || 'Failed to generate overlay');
      }

      const data = await response.json();
      const baseUrl = data.overlayUrl.startsWith('http') 
        ? data.overlayUrl 
        : `${API_ROOT}${data.overlayUrl}`;
      const url = `${baseUrl}?t=${Date.now()}`;
      setOverlayUrl(url);
      setImageLoaded(false);
    } catch (err) {
      setError(err.message);
      console.error('Overlay generation error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Handle corner dragging
  useEffect(() => {
    if (!draggingCorner || !imageRef.current) return;

    const handleMouseMove = (e) => {
      const rect = imageRef.current.getBoundingClientRect();
      const scaleX = imageRef.current.naturalWidth / rect.width;
      const scaleY = imageRef.current.naturalHeight / rect.height;
      
      const x = (e.clientX - rect.left) * scaleX;
      const y = (e.clientY - rect.top) * scaleY;
      
      setTransformedRect4(prev => {
        const newRect4 = [...prev];
        newRect4[draggingCorner] = [Math.round(x), Math.round(y)];
        return newRect4;
      });
    };

    const handleMouseUp = () => {
      setDraggingCorner(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [draggingCorner]);

  const handleCornerMouseDown = (cornerIndex, e) => {
    e.stopPropagation();
    setDraggingCorner(cornerIndex);
  };

  const handleReset = () => {
    if (conusSelection && conusSelection.rect4) {
      setTransformedRect4([...conusSelection.rect4]);
    }
  };

  const handleConfirm = () => {
    onConfirm({
      rect4: transformedRect4
    });
  };

  // Compute homography matrix using direct least squares (more reliable)
  const computeHomography = (src4, dst4) => {
    // Build A matrix (8x9) for homography (Ah = 0)
    const A = [];
    for (let i = 0; i < 4; i++) {
      const [x, y] = src4[i];
      const [X, Y] = dst4[i];
      A.push([x, y, 1, 0, 0, 0, -X*x, -X*y, -X]);
      A.push([0, 0, 0, x, y, 1, -Y*x, -Y*y, -Y]);
    }
    
    // Compute A^T * A (9x9)
    const AtA = Array(9).fill(0).map(() => Array(9).fill(0));
    for (let i = 0; i < 8; i++) {
      for (let j = 0; j < 9; j++) {
        for (let k = 0; k < 9; k++) {
          AtA[j][k] += A[i][j] * A[i][k];
        }
      }
    }
    
    // Find null space using inverse power iteration (find smallest eigenvector)
    // Start with random vector
    let v = Array(9).fill(0).map(() => Math.random() - 0.5);
    let norm = Math.sqrt(v.reduce((sum, x) => sum + x*x, 0));
    v = v.map(x => x / norm);
    
    // Use inverse iteration: solve AtA * v = lambda * v for smallest lambda
    // Approximate by: v = (AtA + epsilon*I)^(-1) * v, then normalize
    const epsilon = 1e-6;
    const I = Array(9).fill(0).map((_, i) => Array(9).fill(0).map((_, j) => i === j ? epsilon : 0));
    
    // Simple iterative refinement (Gauss-Seidel style)
    for (let iter = 0; iter < 50; iter++) {
      // Compute (AtA + epsilon*I) * v
      let Av = Array(9).fill(0);
      for (let i = 0; i < 9; i++) {
        for (let j = 0; j < 9; j++) {
          Av[i] += (AtA[i][j] + I[i][j]) * v[j];
        }
      }
      
      // Simple inverse approximation: v_new = v_old - alpha * (AtA * v_old)
      // Use gradient descent to minimize ||AtA * v||
      const alpha = 0.01;
      let vNew = Array(9).fill(0);
      for (let i = 0; i < 9; i++) {
        let AtAv_i = 0;
        for (let j = 0; j < 9; j++) {
          AtAv_i += AtA[i][j] * v[j];
        }
        vNew[i] = v[i] - alpha * AtAv_i;
      }
      
      norm = Math.sqrt(vNew.reduce((sum, x) => sum + x*x, 0));
      if (norm < 1e-10) break;
      v = vNew.map(x => x / norm);
    }
    
    // Reshape to 3x3 matrix
    const H = [
      [v[0], v[1], v[2]],
      [v[3], v[4], v[5]],
      [v[6], v[7], v[8]]
    ];
    
    // Normalize so H[2][2] = 1
    const scale = H[2][2];
    if (Math.abs(scale) < 1e-10) {
      return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    }
    return H.map(row => row.map(x => x / scale));
  };

  // Apply homography to a point
  const applyHomography = (x, y, H) => {
    const w = H[2][0] * x + H[2][1] * y + H[2][2];
    if (Math.abs(w) < 1e-10) return { x: 0, y: 0 };
    return {
      x: (H[0][0] * x + H[0][1] * y + H[0][2]) / w,
      y: (H[1][0] * x + H[1][1] * y + H[1][2]) / w
    };
  };

  // Draw shapefile overlay on canvas
  useEffect(() => {
    if (!canvasRef.current || !imageRef.current || !shapefileData || !transformedRect4 || !imageLoaded) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;
    
    const rect = img.getBoundingClientRect();
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    
    if (!naturalWidth || !naturalHeight) return;
    
    // Set canvas size to match image display size
    canvas.width = rect.width;
    canvas.height = rect.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Get shapefile bounds
    const { bounds } = shapefileData;
    const src4 = [
      [bounds.xmin, bounds.ymax], // TL (geographic: north is +Y)
      [bounds.xmax, bounds.ymax], // TR
      [bounds.xmax, bounds.ymin], // BR
      [bounds.xmin, bounds.ymin]  // BL
    ];
    
    // Destination is transformedRect4 (already in natural pixel coordinates)
    const dst4 = transformedRect4;
    
    // Compute homography matrix
    const H = computeHomography(src4, dst4);
    
    // Scale from natural image coords to display coords
    const displayScaleX = rect.width / naturalWidth;
    const displayScaleY = rect.height / naturalHeight;
    
    // Draw shapefile features
    ctx.strokeStyle = '#ff0000';
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    const features = shapefileData.geojson.features || [];
    let hasPath = false;
    
    for (const feature of features) {
      const geom = feature.geometry;
      if (geom.type === 'LineString') {
        const coords = geom.coordinates;
        for (let i = 0; i < coords.length; i++) {
          const [x, y] = coords[i];
          // Apply homography to get pixel coordinates in natural image space
          const pixel = applyHomography(x, y, H);
          // Scale to display coordinates
          const px = pixel.x * displayScaleX;
          const py = pixel.y * displayScaleY;
          
          if (i === 0) {
            ctx.moveTo(px, py);
            hasPath = true;
          } else {
            ctx.lineTo(px, py);
          }
        }
      } else if (geom.type === 'MultiLineString') {
        for (const line of geom.coordinates) {
          for (let i = 0; i < line.length; i++) {
            const [x, y] = line[i];
            const pixel = applyHomography(x, y, H);
            const px = pixel.x * displayScaleX;
            const py = pixel.y * displayScaleY;
            
            if (i === 0) {
              ctx.moveTo(px, py);
              hasPath = true;
            } else {
              ctx.lineTo(px, py);
            }
          }
        }
      }
    }
    
    if (hasPath) {
      ctx.stroke();
    }
  }, [transformedRect4, shapefileData, imageLoaded, imageRef]);

  // Get corner positions in display coordinates
  const getCornerPositions = () => {
    if (!imageRef.current || !transformedRect4 || !imageLoaded) return null;
    
    const rect = imageRef.current.getBoundingClientRect();
    const naturalWidth = imageRef.current.naturalWidth;
    const naturalHeight = imageRef.current.naturalHeight;
    
    if (!naturalWidth || !naturalHeight || naturalWidth === 0 || naturalHeight === 0) {
      return null;
    }
    
    const scaleX = rect.width / naturalWidth;
    const scaleY = rect.height / naturalHeight;
    
    if (!isFinite(scaleX) || !isFinite(scaleY) || scaleX === 0 || scaleY === 0) {
      return null;
    }
    
    const positions = transformedRect4.map(([x, y]) => {
      const px = x * scaleX;
      const py = y * scaleY;
      if (!isFinite(px) || !isFinite(py)) {
        return null;
      }
      return { x: px, y: py };
    }).filter(pos => pos !== null);
    
    return positions.length === 4 ? positions : null;
  };

  const cornerPositions = getCornerPositions();

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100vw',
      height: '100vh',
      backgroundColor: 'rgba(0, 0, 0, 0.9)',
      zIndex: 10000,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '12px',
        padding: '24px',
        maxWidth: '95vw',
        maxHeight: '95vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '20px'
      }}>
        <h3 style={{
          margin: 0,
          color: '#333',
          fontSize: '22px',
          fontWeight: '600'
        }}>
          Adjust CONUS Overlay
        </h3>

        <p style={{
          margin: 0,
          color: '#666',
          fontSize: '14px',
          textAlign: 'center'
        }}>
          Drag the corner handles to adjust the rectangle.
          <br />
          The shapefile overlay updates in real-time as you drag.
          <br />
          Click "Generate Overlay" for final high-quality preview.
        </p>

        {/* Control Buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <button
            onClick={handleReset}
            style={{
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer'
            }}
          >
            Reset to Original
          </button>
          <button
            onClick={handleGenerateOverlay}
            disabled={loading || !transformedRect4}
            style={{
              backgroundColor: loading || !transformedRect4 ? '#9ca3af' : '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: loading || !transformedRect4 ? 'not-allowed' : 'pointer',
              opacity: loading || !transformedRect4 ? 0.6 : 1
            }}
          >
            {loading ? 'Generating...' : 'Generate Overlay'}
          </button>
        </div>

        {/* Preview Image with Draggable Corners */}
        <div 
          ref={containerRef}
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            border: '2px solid #e5e7eb',
            borderRadius: '8px',
            overflow: 'visible'
          }}
        >
          {loading && (
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              borderRadius: '8px'
            }}>
              <div style={{
                fontSize: '16px',
                color: '#666'
              }}>
                Generating overlay...
              </div>
            </div>
          )}
          {error && (
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.9)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              borderRadius: '8px',
              padding: '20px'
            }}>
              <div style={{
                fontSize: '14px',
                color: '#ef4444',
                textAlign: 'center'
              }}>
                Error: {error}
              </div>
            </div>
          )}
          {imageUrl ? (
            <>
              <div style={{ position: 'relative', display: 'inline-block', width: '100%', height: '100%' }}>
                <img
                  ref={imageRef}
                  src={imageUrl}
                  alt="CONUS map"
                  onLoad={() => {
                    setImageLoaded(true);
                  }}
                  onError={() => {
                    setImageLoaded(false);
                    setError('Failed to load image');
                  }}
                  style={{
                    maxWidth: '100%',
                    maxHeight: '60vh',
                    objectFit: 'contain',
                    display: 'block',
                    userSelect: 'none'
                  }}
                  draggable={false}
                />
                {/* Canvas overlay for real-time shapefile preview */}
                <canvas
                  ref={canvasRef}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    pointerEvents: 'none',
                    zIndex: 5
                  }}
                />
              </div>
              
              {/* Draggable Corner Handles */}
              {cornerPositions && cornerPositions.length === 4 && cornerPositions.every(p => p && isFinite(p.x) && isFinite(p.y)) && cornerPositions.map((pos, index) => (
                <div
                  key={index}
                  onMouseDown={(e) => handleCornerMouseDown(index, e)}
                  style={{
                    position: 'absolute',
                    left: pos.x - 8,
                    top: pos.y - 8,
                    width: '16px',
                    height: '16px',
                    backgroundColor: '#3b82f6',
                    border: '2px solid white',
                    borderRadius: '50%',
                    cursor: 'grab',
                    zIndex: 20,
                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                    transform: draggingCorner === index ? 'scale(1.2)' : 'scale(1)',
                    transition: draggingCorner === index ? 'none' : 'transform 0.1s'
                  }}
                />
              ))}
              
              {/* Rectangle outline connecting corners */}
              {cornerPositions && cornerPositions.length === 4 && cornerPositions.every(p => p && isFinite(p.x) && isFinite(p.y)) && (
                <svg
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    pointerEvents: 'none',
                    zIndex: 15
                  }}
                >
                  <polygon
                    points={cornerPositions.map(p => `${p.x},${p.y}`).join(' ')}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    strokeDasharray="5,5"
                  />
                </svg>
              )}
            </>
          ) : (
            <div style={{
              width: '600px',
              height: '400px',
              backgroundColor: '#f3f4f6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#9ca3af',
              fontSize: '14px',
              borderRadius: '8px'
            }}>
              Loading preview...
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center'
        }}>
          <button
            onClick={onCancel}
            style={{
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading || error || !transformedRect4}
            style={{
              backgroundColor: loading || error || !transformedRect4 ? '#9ca3af' : '#28a745',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: loading || error || !transformedRect4 ? 'not-allowed' : 'pointer',
              opacity: loading || error || !transformedRect4 ? 0.6 : 1
            }}
          >
            Confirm Alignment
          </button>
        </div>
      </div>
    </div>
  );
}
