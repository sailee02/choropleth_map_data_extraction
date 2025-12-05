import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

// Suggested counties for 4-point alignment (one in each corner region)
const SUGGESTED_COUNTIES = [
  { name: "Clallam County, Washington", geoid: "53009", region: "Northwest", description: "Click on Clallam County, WA (northwest corner of CONUS)" },
  { name: "Miami-Dade County, Florida", geoid: "12086", region: "Southeast", description: "Click on Miami-Dade County, FL (southeast corner)" },
  { name: "Cameron County, Texas", geoid: "48061", region: "Southwest", description: "Click on Cameron County, TX (southwest corner, near Mexico border)" },
  { name: "Aroostook County, Maine", geoid: "23003", region: "Northeast", description: "Click on Aroostook County, ME (northeast corner)" }
];

export default function ConusCountySelector({ 
  imageUrl, 
  uploadId, 
  projection = "4326",
  initialConusSelection = null,
  onConfirm, 
  onCancel 
}) {
  const [shapefileData, setShapefileData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [selectedPoints, setSelectedPoints] = useState([]); // Array of {x, y, countyName, geoid}
  const [previewOverlay, setPreviewOverlay] = useState(null); // Preview of aligned shapefile
  const [computing, setComputing] = useState(false);
  const [alignmentData, setAlignmentData] = useState(null);
  
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
        formData.append('region', 'conus');

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

  // Handle image click to select county
  const handleImageClick = (e) => {
    if (!imageRef.current || selectedPoints.length >= 4) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Convert to natural image coordinates
    const naturalWidth = imageRef.current.naturalWidth;
    const naturalHeight = imageRef.current.naturalHeight;
    const scaleX = naturalWidth / rect.width;
    const scaleY = naturalHeight / rect.height;
    
    const naturalX = x * scaleX;
    const naturalY = y * scaleY;
    
    const currentStep = selectedPoints.length;
    const county = SUGGESTED_COUNTIES[currentStep];
    const newPoint = {
      x: naturalX,
      y: naturalY,
      countyName: county.name,
      geoid: county.geoid,
      step: currentStep
    };
    
    setSelectedPoints(prev => [...prev, newPoint]);
  };

  // Compute alignment using backend
  const computeAlignment = async () => {
    if (selectedPoints.length !== 4 || !shapefileData) return;
    
    setComputing(true);
    setError(null);
    
    try {
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('projection', projection);
      formData.append('region', 'conus');
      formData.append('selected_points', JSON.stringify(selectedPoints.map(p => ({ x: p.x, y: p.y, geoid: p.geoid }))));
      
      const response = await fetch(`${API_ROOT}/api/compute-alignment-from-counties`, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Failed to compute alignment' }));
        throw new Error(errorData.error || 'Failed to compute alignment');
      }
      
      const data = await response.json();
      
      // Get preview overlay
      if (data.overlayUrl) {
        const fullUrl = `${API_ROOT}${data.overlayUrl}`;
        setPreviewOverlay(fullUrl);
      }
      
      // Store alignment data for confirmation
      setAlignmentData({
        rect4: data.rect4,
        bounds: shapefileData.bounds,
        alignmentParams: data
      });
    } catch (err) {
      console.error('Alignment computation error:', err);
      setError('Failed to compute alignment: ' + err.message);
    } finally {
      setComputing(false);
    }
  };

  // Draw shapefile preview and selected points
  useEffect(() => {
    if (!canvasRef.current || !imageRef.current || !imageLoaded) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = imageRef.current;
    
    const rect = img.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw selected points
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    const scaleX = rect.width / naturalWidth;
    const scaleY = rect.height / naturalHeight;
    
    selectedPoints.forEach((point, index) => {
      const x = point.x * scaleX;
      const y = point.y * scaleY;
      
      // Draw circle
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, 2 * Math.PI);
      ctx.fillStyle = index === selectedPoints.length - 1 ? '#10b981' : '#3b82f6';
      ctx.fill();
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Draw label
      ctx.fillStyle = 'white';
      ctx.font = 'bold 12px Arial';
      ctx.textAlign = 'center';
      ctx.fillText(`${index + 1}`, x, y - 12);
    });
  }, [selectedPoints, imageLoaded]);

  const handleReset = () => {
    setSelectedPoints([]);
    setPreviewOverlay(null);
    setComputing(false);
    setError(null);
  };

  const handleUndo = () => {
    if (selectedPoints.length > 0) {
      setSelectedPoints(prev => prev.slice(0, -1));
      setPreviewOverlay(null);
      setComputing(false);
      setError(null);
    }
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
        gap: '20px',
        overflow: 'auto'
      }}>
        <h3 style={{
          margin: 0,
          color: '#333',
          fontSize: '22px',
          fontWeight: '600'
        }}>
          Align CONUS Shapefile - Select 4 Counties
        </h3>

        {selectedPoints.length < 4 && (
          <div style={{
            backgroundColor: '#f0f9ff',
            border: '2px solid #3b82f6',
            borderRadius: '8px',
            padding: '16px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: '600', color: '#1e40af' }}>
              Step {selectedPoints.length + 1} of 4
            </p>
            <p style={{ margin: 0, fontSize: '14px', color: '#1e3a8a' }}>
              {SUGGESTED_COUNTIES[selectedPoints.length].description}
            </p>
            <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: '#64748b', fontStyle: 'italic' }}>
              {SUGGESTED_COUNTIES[selectedPoints.length].name}
            </p>
          </div>
        )}

        {selectedPoints.length === 4 && !computing && !previewOverlay && (
          <div style={{
            backgroundColor: '#f0fdf4',
            border: '2px solid #10b981',
            borderRadius: '8px',
            padding: '16px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            <p style={{ margin: 0, fontSize: '14px', color: '#065f46', fontWeight: '600' }}>
              ✓ All 4 counties selected! Click "Compute Alignment" to align the shapefile.
            </p>
          </div>
        )}

        {computing && (
          <div style={{
            backgroundColor: '#fef3c7',
            border: '2px solid #f59e0b',
            borderRadius: '8px',
            padding: '16px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            <p style={{ margin: 0, fontSize: '14px', color: '#92400e', fontWeight: '600' }}>
              Computing alignment...
            </p>
          </div>
        )}

        {previewOverlay && !computing && (
          <div style={{
            backgroundColor: '#d1fae5',
            border: '2px solid #10b981',
            borderRadius: '8px',
            padding: '16px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            <p style={{ margin: 0, fontSize: '14px', color: '#065f46', fontWeight: '600' }}>
              ✓ Alignment computed! Review the overlay preview below. If it looks good, click "Confirm Alignment".
            </p>
          </div>
        )}

        {loading && (
          <div style={{ display: 'none' }}>
            {/* Loading shapefile in background */}
          </div>
        )}

        {error && (
          <div style={{
            backgroundColor: '#fef2f2',
            border: '1px solid #ef4444',
            borderRadius: '8px',
            padding: '12px',
            color: '#dc2626',
            fontSize: '14px',
            maxWidth: '600px',
            textAlign: 'center'
          }}>
            Error: {error}
          </div>
        )}

        {/* Image with overlay */}
        <div 
          ref={containerRef}
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            border: '2px solid #e5e7eb',
            borderRadius: '8px',
            cursor: selectedPoints.length < 4 ? 'crosshair' : 'default'
          }}
          onClick={selectedPoints.length < 4 ? handleImageClick : undefined}
        >
          {imageUrl && (
            <>
              <img
                ref={imageRef}
                src={imageUrl}
                alt="Map"
                onLoad={() => setImageLoaded(true)}
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
              
              {previewOverlay && (
                <img
                  src={previewOverlay}
                  alt="Aligned overlay"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    opacity: 0.7,
                    pointerEvents: 'none',
                    zIndex: 4
                  }}
                />
              )}
            </>
          )}
        </div>

        {/* Selected counties list */}
        {selectedPoints.length > 0 && (
          <div style={{
            width: '100%',
            maxWidth: '600px',
            backgroundColor: '#f8fafc',
            borderRadius: '8px',
            padding: '12px'
          }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: '600', color: '#333' }}>
              Selected Counties:
            </p>
            {selectedPoints.map((point, index) => (
              <div key={index} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '4px 0',
                fontSize: '13px',
                color: '#666'
              }}>
                <span>{index + 1}. {point.countyName}</span>
                <span style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  backgroundColor: '#3b82f6',
                  display: 'inline-block'
                }} />
              </div>
            ))}
          </div>
        )}

        {/* Action Buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          {selectedPoints.length > 0 && (
            <button
              onClick={handleUndo}
              style={{
                backgroundColor: '#f59e0b',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer'
              }}
            >
              Undo Last
            </button>
          )}
          
          {selectedPoints.length === 4 && !computing && !previewOverlay && (
            <button
              onClick={computeAlignment}
              style={{
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer'
              }}
            >
              Compute Alignment
            </button>
          )}

          {previewOverlay && alignmentData && (
            <button
              onClick={() => onConfirm(alignmentData)}
              style={{
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer'
              }}
            >
              Confirm Alignment
            </button>
          )}
          
          {selectedPoints.length > 0 && (
            <button
              onClick={handleReset}
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
              Reset All
            </button>
          )}
          
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
        </div>
      </div>
    </div>
  );
}

