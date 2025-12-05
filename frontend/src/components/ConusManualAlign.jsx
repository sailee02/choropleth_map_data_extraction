import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

export default function ConusManualAlign({ 
  imageUrl, 
  uploadId, 
  projection = "4326",
  initialConusSelection = null, // {x, y, width, height, rect4} in natural image coordinates
  onConfirm, 
  onCancel 
}) {
  const [shapefileData, setShapefileData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  
  const [rect, setRect] = useState(null); // {x, y, width, height} in display coords
  const [rotation, setRotation] = useState(0); // Rotation angle in degrees
  const [draggingCorner, setDraggingCorner] = useState(null); // 'tl','tr','br','bl'
  const [draggingRotationHandle, setDraggingRotationHandle] = useState(false);
  const [isDraggingShapefile, setIsDraggingShapefile] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  // Fetch shapefile GeoJSON
  useEffect(() => {
    if (!uploadId) return;

    const fetchShapefile = async () => {
      setLoading(true);
      setError(null);
      try {
        const formData = new FormData();
        formData.append('upload_id', uploadId);
        formData.append('projection', projection);
        formData.append('region', 'conus'); // Request CONUS shapefile

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
        setError(err.message);
        console.error('Failed to fetch shapefile:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchShapefile();
  }, [uploadId, projection]);

  // Helper function to compute rotated corners from rect and rotation
  const MIN_SIZE = 40;

  const getRectCenter = (r) => ({
    x: r.x + r.width / 2,
    y: r.y + r.height / 2,
  });

  const getRotatedCorners = (r, angleDeg) => {
    if (!r) return [];
    const angle = (angleDeg * Math.PI) / 180;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    
    // Center of rectangle
    const cx = r.x + r.width / 2;
    const cy = r.y + r.height / 2;
    
    // Four corners relative to center
    const corners = [
      [-r.width / 2, -r.height / 2], // TL
      [r.width / 2, -r.height / 2],  // TR
      [r.width / 2, r.height / 2],   // BR
      [-r.width / 2, r.height / 2],  // BL
    ];
    
    // Rotate and translate
    return corners.map(([x, y]) => {
      const xRot = x * cos - y * sin;
      const yRot = x * sin + y * cos;
      return [cx + xRot, cy + yRot];
    });
  };

  // Initialize rectangle based on user's selection or shapefile bounds
  useEffect(() => {
    if (imageLoaded && imageRef.current && shapefileData && !rect) {
      const imgRect = imageRef.current.getBoundingClientRect();
      const naturalWidth = imageRef.current.naturalWidth;
      const naturalHeight = imageRef.current.naturalHeight;
      
      if (initialConusSelection && initialConusSelection.x !== undefined) {
        // Use user's drawn rectangle
        const scaleX = imgRect.width / naturalWidth;
        const scaleY = imgRect.height / naturalHeight;
        
        setRect({
          x: initialConusSelection.x * scaleX,
          y: initialConusSelection.y * scaleY,
          width: initialConusSelection.width * scaleX,
          height: initialConusSelection.height * scaleY,
        });
      } else {
        // Fallback: Initialize based on shapefile bounds
        const { bounds } = shapefileData;
        const boundsWidth = bounds.xmax - bounds.xmin;
        const boundsHeight = bounds.ymax - bounds.ymin;
        
        // Calculate initial scale to fit shapefile reasonably
        const baseScale = Math.min(imgRect.width / boundsWidth, imgRect.height / boundsHeight) * 0.4;
        
        // Center of image
        const centerX = imgRect.width / 2;
        const centerY = imgRect.height / 2;
        
        const rectWidth = boundsWidth * baseScale;
        const rectHeight = boundsHeight * baseScale;
        
        // Initialize as axis-aligned rectangle
        setRect({
          x: centerX - rectWidth / 2,
          y: centerY - rectHeight / 2,
          width: rectWidth,
          height: rectHeight,
        });
      }
    }
  }, [imageLoaded, shapefileData, rect, initialConusSelection]);

  // Draw shapefile overlay
  useEffect(() => {
    if (!canvasRef.current || !imageRef.current || !shapefileData || !imageLoaded || !rect) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;

    const imgRect = img.getBoundingClientRect();
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    
    if (!naturalWidth || !naturalHeight) return;

    canvas.width = imgRect.width;
    canvas.height = imgRect.height;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const { bounds } = shapefileData;
    const boundsWidth = bounds.xmax - bounds.xmin || 1;
    const boundsHeight = bounds.ymax - bounds.ymin || 1;
    
    // Get rotated corners from rect + rotation
    const rotatedCorners = getRotatedCorners(rect, rotation);
    if (rotatedCorners.length !== 4) return;
    
    // Use affine transform (rotation, scale, translation)
    // Compute center and dimensions
    const srcCenterX = (bounds.xmin + bounds.xmax) / 2;
    const srcCenterY = (bounds.ymin + bounds.ymax) / 2;
    const dstCenterX = (rotatedCorners[0][0] + rotatedCorners[1][0] + rotatedCorners[2][0] + rotatedCorners[3][0]) / 4;
    const dstCenterY = (rotatedCorners[0][1] + rotatedCorners[1][1] + rotatedCorners[2][1] + rotatedCorners[3][1]) / 4;
    
    // Compute rotation angle from first edge (TL to TR)
    const edge0X = rotatedCorners[1][0] - rotatedCorners[0][0];
    const edge0Y = rotatedCorners[1][1] - rotatedCorners[0][1];
    const angle = Math.atan2(edge0Y, edge0X);
    
    // Compute scale from edge lengths
    const srcEdge0Length = boundsWidth;
    const dstEdge0Length = Math.sqrt(edge0X * edge0X + edge0Y * edge0Y);
    const scaleX = dstEdge0Length / srcEdge0Length;
    
    const edge1X = rotatedCorners[3][0] - rotatedCorners[0][0];
    const edge1Y = rotatedCorners[3][1] - rotatedCorners[0][1];
    const srcEdge1Length = boundsHeight;
    const dstEdge1Length = Math.sqrt(edge1X * edge1X + edge1Y * edge1Y);
    const scaleY = dstEdge1Length / srcEdge1Length;
    
    const projectPoint = (x, y) => {
      // Transform from geographic coords to pixel coords
      // Step 1: Translate to source center
      let px = x - srcCenterX;
      let py = y - srcCenterY;
      
      // Step 2: Flip Y (geographic Y increases north, we want it to increase down for rotation)
      py = -py;
      
      // Step 3: Rotate
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      const pxRot = px * cosA - py * sinA;
      const pyRot = px * sinA + py * cosA;
      
      // Step 4: Scale
      px = pxRot * scaleX;
      py = pyRot * scaleY;
      
      // Step 5: Translate to destination center
      px += dstCenterX;
      py += dstCenterY;
      
      return { x: px, y: py };
    };
    
    // Draw shapefile features
    ctx.strokeStyle = '#ff0000';
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    const features = shapefileData.geojson.features || [];
    for (const feature of features) {
      const geom = feature.geometry;
      if (geom.type === 'LineString') {
        const coords = geom.coordinates;
        for (let i = 0; i < coords.length; i++) {
          const [x, y] = coords[i];
          const pixel = projectPoint(x, y);
          
          if (i === 0) {
            ctx.moveTo(pixel.x, pixel.y);
          } else {
            ctx.lineTo(pixel.x, pixel.y);
          }
        }
      } else if (geom.type === 'MultiLineString') {
        for (const line of geom.coordinates) {
          for (let i = 0; i < line.length; i++) {
            const [x, y] = line[i];
            const pixel = projectPoint(x, y);
            
            if (i === 0) {
              ctx.moveTo(pixel.x, pixel.y);
            } else {
              ctx.lineTo(pixel.x, pixel.y);
            }
          }
        }
      }
    }
    
    ctx.stroke();
  }, [shapefileData, imageLoaded, rect, rotation]);

  const getCorners = () => {
    if (!rect) return [];
    return getRotatedCorners(rect, rotation);
  };

  const globalToLocal = (px, py, r, angleDeg) => {
    const { x: cx, y: cy } = getRectCenter(r);
    const dx = px - cx;
    const dy = py - cy;
    const angleRad = (-angleDeg * Math.PI) / 180;
    return {
      x: dx * Math.cos(angleRad) - dy * Math.sin(angleRad),
      y: dx * Math.sin(angleRad) + dy * Math.cos(angleRad),
    };
  };

  // Handle corner dragging (works with rotation)
  useEffect(() => {
    if (!draggingCorner || !imageRef.current || !rect) return;

    const handleMouseMove = (e) => {
      const bounds = imageRef.current.getBoundingClientRect();
      let x = e.clientX - bounds.left;
      let y = e.clientY - bounds.top;

      x = Math.max(0, Math.min(bounds.width, x));
      y = Math.max(0, Math.min(bounds.height, y));

      setRect((prev) => {
        if (!prev) return prev;

        const local = globalToLocal(x, y, prev, rotation);
        let minX = -prev.width / 2;
        let maxX = prev.width / 2;
        let minY = -prev.height / 2;
        let maxY = prev.height / 2;

        switch (draggingCorner) {
          case 'tl':
            minX = Math.min(local.x, maxX - MIN_SIZE);
            minY = Math.min(local.y, maxY - MIN_SIZE);
            break;
          case 'tr':
            maxX = Math.max(local.x, minX + MIN_SIZE);
            minY = Math.min(local.y, maxY - MIN_SIZE);
            break;
          case 'br':
            maxX = Math.max(local.x, minX + MIN_SIZE);
            maxY = Math.max(local.y, minY + MIN_SIZE);
            break;
          case 'bl':
            minX = Math.min(local.x, maxX - MIN_SIZE);
            maxY = Math.max(local.y, minY + MIN_SIZE);
            break;
          default:
            return prev;
        }

        const newWidth = Math.max(MIN_SIZE, maxX - minX);
        const newHeight = Math.max(MIN_SIZE, maxY - minY);
        const newCenterLocalX = (minX + maxX) / 2;
        const newCenterLocalY = (minY + maxY) / 2;

        const angleRad = (rotation * Math.PI) / 180;
        const offsetX =
          newCenterLocalX * Math.cos(angleRad) -
          newCenterLocalY * Math.sin(angleRad);
        const offsetY =
          newCenterLocalX * Math.sin(angleRad) +
          newCenterLocalY * Math.cos(angleRad);
        const { x: cx, y: cy } = getRectCenter(prev);
        const newCenterX = cx + offsetX;
        const newCenterY = cy + offsetY;

        return {
          x: newCenterX - newWidth / 2,
          y: newCenterY - newHeight / 2,
          width: newWidth,
          height: newHeight,
        };
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
  }, [draggingCorner, rect, rotation]);

  const handleCornerMouseDown = (cornerKey, e) => {
    e.stopPropagation();
    setDraggingCorner(cornerKey);
  };

  // Handle rotation handle dragging
  useEffect(() => {
    if (!draggingRotationHandle || !imageRef.current || !rect) return;

    const handleMouseMove = (e) => {
      const bounds = imageRef.current.getBoundingClientRect();
      const cursorX = e.clientX - bounds.left;
      const cursorY = e.clientY - bounds.top;

      // Calculate center of rectangle
      const centerX = rect.x + rect.width / 2;
      const centerY = rect.y + rect.height / 2;

      // Calculate angle from center to cursor
      const dx = cursorX - centerX;
      const dy = cursorY - centerY;
      const angle = Math.atan2(dy, dx) * (180 / Math.PI);

      setRotation(angle);
    };

    const handleMouseUp = () => {
      setDraggingRotationHandle(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [draggingRotationHandle, rect]);

  const handleRotationHandleMouseDown = (e) => {
    e.stopPropagation();
    setDraggingRotationHandle(true);
  };

  // Check if point is inside the rotated rectangle
  const isPointInRect = (px, py) => {
    if (!rect) return false;
    const corners = getRotatedCorners(rect, rotation);
    if (corners.length !== 4) return false;
    
    // Use ray casting algorithm
    let inside = false;
    for (let i = 0, j = corners.length - 1; i < corners.length; j = i++) {
      const [xi, yi] = corners[i];
      const [xj, yj] = corners[j];
      const intersect = ((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  };

  // Handle dragging entire shapefile (translates rect)
  const handleShapefileMouseDown = (e) => {
    if (!imageRef.current || !rect) return;
    if (draggingCorner) return;
    if (draggingRotationHandle) return;

    const bounds = imageRef.current.getBoundingClientRect();
    const cursorX = e.clientX - bounds.left;
    const cursorY = e.clientY - bounds.top;

    // Check if click is inside the rotated rectangle
    if (isPointInRect(cursorX, cursorY)) {
      const { x: cx, y: cy } = getRectCenter(rect);
      setIsDraggingShapefile(true);
      setDragStart({
        offsetX: cursorX - cx,
        offsetY: cursorY - cy,
      });
    }
  };

  useEffect(() => {
    if (!isDraggingShapefile || !dragStart || !rect) return;

    const handleMouseMove = (e) => {
      if (!imageRef.current) return;
      const bounds = imageRef.current.getBoundingClientRect();
      const cursorX = e.clientX - bounds.left;
      const cursorY = e.clientY - bounds.top;

      const newCenterX = cursorX - dragStart.offsetX;
      const newCenterY = cursorY - dragStart.offsetY;

      setRect((prev) =>
        prev
          ? {
              ...prev,
              x: newCenterX - prev.width / 2,
              y: newCenterY - prev.height / 2,
            }
          : prev
      );
    };

    const handleMouseUp = () => {
      setIsDraggingShapefile(false);
      setDragStart(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingShapefile, dragStart, rect]);

  const handleConfirm = () => {
    if (!imageRef.current || !rect || !shapefileData) return;
    
    const bounds = imageRef.current.getBoundingClientRect();
    const naturalWidth = imageRef.current.naturalWidth;
    const naturalHeight = imageRef.current.naturalHeight;
    const scaleX = naturalWidth / bounds.width;
    const scaleY = naturalHeight / bounds.height;
    
    // Get rotated corners and convert to natural image coordinates
    const displayCorners = getCorners();
    const naturalCorners = displayCorners.map(([x, y]) => [
      Math.round(x * scaleX),
      Math.round(y * scaleY),
    ]);
    
    onConfirm({
      rect4: naturalCorners,
      bounds: shapefileData.bounds,
    });
  };

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
          Align CONUS Shapefile
        </h3>

        <p style={{
          margin: 0,
          color: '#666',
          fontSize: '14px',
          textAlign: 'center'
        }}>
          Drag the corner handles to resize the red outline rectangle.
          <br />
          Drag the rotation handle (circle at top) left/right to rotate.
          <br />
          Drag anywhere inside the rectangle to move it.
        </p>

        {/* Reset Button */}
        <button
          onClick={() => {
            if (imageRef.current && shapefileData) {
              const imgRect = imageRef.current.getBoundingClientRect();
              const { bounds } = shapefileData;
              const boundsWidth = bounds.xmax - bounds.xmin;
              const boundsHeight = bounds.ymax - bounds.ymin;
              const baseScale = Math.min(imgRect.width / boundsWidth, imgRect.height / boundsHeight) * 0.4;
              const rectWidth = boundsWidth * baseScale;
              const rectHeight = boundsHeight * baseScale;
              const centerX = imgRect.width / 2;
              const centerY = imgRect.height / 2;
              
              // Reset to axis-aligned rectangle with no rotation
              setRect({
                x: centerX - rectWidth / 2,
                y: centerY - rectHeight / 2,
                width: rectWidth,
                height: rectHeight,
              });
              setRotation(0);
            }
          }}
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
          Reset
        </button>

        {/* Preview Image */}
        <div 
          ref={containerRef}
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            border: '2px solid #e5e7eb',
            borderRadius: '8px',
            overflow: 'visible',
            cursor: rect ? (isDraggingShapefile ? 'grabbing' : 'grab') : 'default'
          }}
          onMouseDown={handleShapefileMouseDown}
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
              <div style={{ fontSize: '16px', color: '#666' }}>
                Loading shapefile...
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
              <div style={{ fontSize: '14px', color: '#ef4444', textAlign: 'center' }}>
                Error: {error}
              </div>
            </div>
          )}
          
          {imageUrl && (
            <>
              <img
                ref={imageRef}
                src={imageUrl}
                alt="Map"
                onLoad={() => setImageLoaded(true)}
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
              
              <canvas
                ref={canvasRef}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  zIndex: 5,
                }}
              />
              
              {/* Draggable Corner Handles */}
              {getCorners().length === 4 && getCorners().map((corner, index) => {
                const cornerKeys = ['tl', 'tr', 'br', 'bl'];
                return (
                  <div
                    key={index}
                    onMouseDown={(e) => handleCornerMouseDown(cornerKeys[index], e)}
                    style={{
                      position: 'absolute',
                      left: corner[0] - 8,
                      top: corner[1] - 8,
                      width: '16px',
                      height: '16px',
                      backgroundColor: '#3b82f6',
                      border: '2px solid white',
                      borderRadius: '50%',
                      cursor: 'grab',
                      zIndex: 20,
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                      transform: draggingCorner === cornerKeys[index] ? 'scale(1.2)' : 'scale(1)',
                      transition: draggingCorner === cornerKeys[index] ? 'none' : 'transform 0.1s'
                    }}
                  />
                );
              })}
              
              {/* Rotation Handle - small circle at top middle */}
              {getCorners().length === 4 && rect && (() => {
                const corners = getCorners();
                // Top middle point (between TL and TR)
                const topMiddleX = (corners[0][0] + corners[1][0]) / 2;
                const topMiddleY = (corners[0][1] + corners[1][1]) / 2;
                // Offset upward by 30px
                const angle = (rotation * Math.PI) / 180;
                const offsetX = -30 * Math.sin(angle);
                const offsetY = -30 * Math.cos(angle);
                const handleX = topMiddleX + offsetX;
                const handleY = topMiddleY + offsetY;
                
                return (
                  <div
                    onMouseDown={handleRotationHandleMouseDown}
                    style={{
                      position: 'absolute',
                      left: handleX - 8,
                      top: handleY - 8,
                      width: '16px',
                      height: '16px',
                      backgroundColor: '#10b981',
                      border: '2px solid white',
                      borderRadius: '50%',
                      cursor: 'grab',
                      zIndex: 21,
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                      transform: draggingRotationHandle ? 'scale(1.2)' : 'scale(1)',
                      transition: draggingRotationHandle ? 'none' : 'transform 0.1s'
                    }}
                  />
                );
              })()}
              
              {/* Rectangle outline connecting corners */}
              {getCorners().length === 4 && (
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
                    points={getCorners().map(c => `${c[0]},${c[1]}`).join(' ')}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    strokeDasharray="5,5"
                  />
                </svg>
              )}
            </>
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
            disabled={loading || error || !shapefileData || !rect}
            style={{
              backgroundColor: (loading || error || !shapefileData || !rect) ? '#9ca3af' : '#28a745',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: (loading || error || !shapefileData || !rect) ? 'not-allowed' : 'pointer',
              opacity: (loading || error || !shapefileData || !rect) ? 0.6 : 1
            }}
          >
            Confirm Alignment
          </button>
        </div>
      </div>
    </div>
  );
}

