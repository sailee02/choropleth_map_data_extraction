import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

export default function ConusManualAlign({ 
  imageUrl, 
  uploadId, 
  projection = "4326",
  onConfirm, 
  onCancel 
}) {
  const [shapefileData, setShapefileData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  
  const [rect, setRect] = useState(null); // {x, y, width, height} in display coords
  const [draggingCorner, setDraggingCorner] = useState(null); // 'tl','tr','br','bl'
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

  // Initialize rectangle based on shapefile bounds
  useEffect(() => {
    if (imageLoaded && imageRef.current && shapefileData && !rect) {
      const rect = imageRef.current.getBoundingClientRect();
      
      const { bounds } = shapefileData;
      const boundsWidth = bounds.xmax - bounds.xmin;
      const boundsHeight = bounds.ymax - bounds.ymin;
      
      // Calculate initial scale to fit shapefile reasonably
      const baseScale = Math.min(rect.width / boundsWidth, rect.height / boundsHeight) * 0.4;
      
      // Center of image
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      
      const rectWidth = boundsWidth * baseScale;
      const rectHeight = boundsHeight * baseScale;
      
      setRect({
        x: centerX - rectWidth / 2,
        y: centerY - rectHeight / 2,
        width: rectWidth,
        height: rectHeight,
      });
    }
  }, [imageLoaded, shapefileData, rect]);

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
    
    // Map shapefile bounds to the rectangle (rect) coordinates
    const scaleX = rect.width / boundsWidth;
    const scaleY = rect.height / boundsHeight;

    const projectPoint = (x, y) => {
      // Transform from shapefile geographic coords to rectangle pixel coords
      const px = rect.x + (x - bounds.xmin) * scaleX;
      // Y-axis is flipped: geographic Y increases north, pixel Y increases down
      const py = rect.y + rect.height - (y - bounds.ymin) * scaleY;
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
  }, [shapefileData, imageLoaded, rect]);

  const getCorners = () => {
    if (!rect) return [];
    return [
      [rect.x, rect.y], // TL
      [rect.x + rect.width, rect.y], // TR
      [rect.x + rect.width, rect.y + rect.height], // BR
      [rect.x, rect.y + rect.height], // BL
    ];
  };

  const MIN_SIZE = 40;

  // Handle corner dragging (axis-aligned rectangle)
  useEffect(() => {
    if (!draggingCorner || !imageRef.current || !rect) return;

    const handleMouseMove = (e) => {
      const bounds = imageRef.current.getBoundingClientRect();
      let x = e.clientX - bounds.left;
      let y = e.clientY - bounds.top;

      x = Math.max(0, Math.min(bounds.width, x));
      y = Math.max(0, Math.min(bounds.height, y));

      setRect(prev => {
        if (!prev) return prev;
        let { x: px, y: py, width, height } = prev;
        const right = px + width;
        const bottom = py + height;

        switch (draggingCorner) {
          case 'tl': {
            const newX = Math.min(right - MIN_SIZE, x);
            const newY = Math.min(bottom - MIN_SIZE, y);
            return {
              x: newX,
              y: newY,
              width: right - newX,
              height: bottom - newY,
            };
          }
          case 'tr': {
            const newX = Math.max(px + MIN_SIZE, x);
            const newY = Math.min(bottom - MIN_SIZE, y);
            return {
              x: px,
              y: newY,
              width: newX - px,
              height: bottom - newY,
            };
          }
          case 'br': {
            const newX = Math.max(px + MIN_SIZE, x);
            const newY = Math.max(py + MIN_SIZE, y);
            return {
              x: px,
              y: py,
              width: newX - px,
              height: newY - py,
            };
          }
          case 'bl': {
            const newX = Math.min(right - MIN_SIZE, x);
            const newY = Math.max(py + MIN_SIZE, y);
            return {
              x: newX,
              y: py,
              width: right - newX,
              height: newY - py,
            };
          }
          default:
            return prev;
        }
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
  }, [draggingCorner, rect]);

  const handleCornerMouseDown = (cornerKey, e) => {
    e.stopPropagation();
    setDraggingCorner(cornerKey);
  };

  // Handle dragging entire shapefile
  const handleShapefileMouseDown = (e) => {
    if (!imageRef.current || !rect) return;
    if (draggingCorner) return;

    const bounds = imageRef.current.getBoundingClientRect();
    const cursorX = e.clientX - bounds.left;
    const cursorY = e.clientY - bounds.top;

    if (
      cursorX >= rect.x &&
      cursorX <= rect.x + rect.width &&
      cursorY >= rect.y &&
      cursorY <= rect.y + rect.height
    ) {
      setIsDraggingShapefile(true);
      setDragStart({
        x: cursorX - rect.x,
        y: cursorY - rect.y,
      });
    }
  };

  useEffect(() => {
    if (!isDraggingShapefile || !dragStart || !rect) return;

    const handleMouseMove = (e) => {
      if (!imageRef.current) return;
      const bounds = imageRef.current.getBoundingClientRect();
      let newX = e.clientX - bounds.left - dragStart.x;
      let newY = e.clientY - bounds.top - dragStart.y;

      newX = Math.max(0, Math.min(bounds.width - rect.width, newX));
      newY = Math.max(0, Math.min(bounds.height - rect.height, newY));

      setRect(prev => prev ? { ...prev, x: newX, y: newY } : prev);
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
          Drag anywhere inside the rectangle to move it.
        </p>

        {/* Reset Button */}
        <button
          onClick={() => {
            if (imageRef.current && shapefileData) {
              const rect = imageRef.current.getBoundingClientRect();
              const { bounds } = shapefileData;
              const boundsWidth = bounds.xmax - bounds.xmin;
              const boundsHeight = bounds.ymax - bounds.ymin;
              const baseScale = Math.min(rect.width / boundsWidth, rect.height / boundsHeight) * 0.4;
              const rectWidth = boundsWidth * baseScale;
              const rectHeight = boundsHeight * baseScale;
              const centerX = rect.width / 2;
              const centerY = rect.height / 2;
              
              setRect({
                x: centerX - rectWidth / 2,
                y: centerY - rectHeight / 2,
                width: rectWidth,
                height: rectHeight,
              });
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
              {getCorners().length === 4 && getCorners().map((corner, index) => (
                <div
                  key={index}
                  onMouseDown={(e) => handleCornerMouseDown(['tl','tr','br','bl'][index], e)}
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
                    transform: draggingCorner === index ? 'scale(1.2)' : 'scale(1)',
                    transition: draggingCorner === index ? 'none' : 'transform 0.1s'
                  }}
                />
              ))}
              
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

