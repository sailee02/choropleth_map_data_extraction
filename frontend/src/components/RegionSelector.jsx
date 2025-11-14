import React, { useState, useRef } from 'react';

export default function RegionSelector({ imageUrl, onSelectionComplete, onCancel, onSkip }) {
  const [regions, setRegions] = useState({ alaska: null, hawaii: null });
  const [currentRegion, setCurrentRegion] = useState(null); // 'alaska' or 'hawaii'
  const [isSelecting, setIsSelecting] = useState(false);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const imageRef = useRef(null);

  const handleMouseDown = (e) => {
    if (!imageRef.current || !currentRegion) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    if (x >= 0 && x <= rect.width && y >= 0 && y <= rect.height) {
      setIsSelecting(true);
      setStartPoint({ x, y });
      setEndPoint({ x, y });
    }
  };

  const handleMouseMove = (e) => {
    if (!isSelecting || !imageRef.current) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const constrainedX = Math.max(0, Math.min(x, rect.width));
    const constrainedY = Math.max(0, Math.min(y, rect.height));
    
    setEndPoint({ x: constrainedX, y: constrainedY });
  };

  const handleMouseUp = () => {
    if (!isSelecting || !startPoint || !endPoint || !currentRegion) return;
    
    setIsSelecting(false);
    
    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);
    
    if (width > 10 && height > 10 && imageRef.current) {
      const rect = imageRef.current.getBoundingClientRect();
      const imageWidth = imageRef.current.naturalWidth;
      const imageHeight = imageRef.current.naturalHeight;
      
      const imageSelection = {
        x: (left / rect.width) * imageWidth,
        y: (top / rect.height) * imageHeight,
        width: (width / rect.width) * imageWidth,
        height: (height / rect.height) * imageHeight
      };
      
      setRegions(prev => ({
        ...prev,
        [currentRegion]: imageSelection
      }));
      
      setStartPoint(null);
      setEndPoint(null);
      setCurrentRegion(null);
    } else {
      setStartPoint(null);
      setEndPoint(null);
    }
  };

  const handleConfirmAll = () => {
    if (imageRef.current) {
      onSelectionComplete(regions);
    }
  };

  const handleClearRegion = (region) => {
    setRegions(prev => ({
      ...prev,
      [region]: null
    }));
  };

  const getSelectionStyle = (region) => {
    if (!startPoint || !endPoint || currentRegion !== region) return null;
    
    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);
    
    return {
      position: 'absolute',
      left: left,
      top: top,
      width: width,
      height: height,
      border: '2px solid #ff6b00',
      backgroundColor: 'rgba(255, 107, 0, 0.1)',
      pointerEvents: 'none',
      zIndex: 10
    };
  };

  const getConfirmedStyle = (region) => {
    const selection = regions[region];
    if (!selection || !imageRef.current) return null;
    
    const rect = imageRef.current.getBoundingClientRect();
    const imageWidth = imageRef.current.naturalWidth;
    const imageHeight = imageRef.current.naturalHeight;
    
    return {
      position: 'absolute',
      left: (selection.x / imageWidth) * rect.width,
      top: (selection.y / imageHeight) * rect.height,
      width: (selection.width / imageWidth) * rect.width,
      height: (selection.height / imageHeight) * rect.height,
      border: `2px solid ${region === 'alaska' ? '#3b82f6' : '#10b981'}`,
      backgroundColor: region === 'alaska' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(16, 185, 129, 0.1)',
      pointerEvents: 'none',
      zIndex: 10
    };
  };

  const hasAnySelection = regions.alaska || regions.hawaii;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100vw',
      height: '100vh',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      zIndex: 9999,
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
        maxWidth: '90vw',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center'
      }}>
        <h3 style={{
          margin: '0 0 8px 0',
          color: '#333',
          fontSize: '20px',
          fontWeight: '600'
        }}>
          Optional: Mark Alaska/Hawaii Regions
        </h3>
        
        <p style={{
          margin: '0 0 20px 0',
          color: '#666',
          fontSize: '14px',
          textAlign: 'center',
          maxWidth: '500px'
        }}>
          If your map includes Alaska or Hawaii, mark their approximate bounding boxes.
          <br />
          <strong>This step is optional</strong> - skip if your map is CONUS-only.
        </p>

        {/* Region buttons */}
        <div style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '16px',
          flexWrap: 'wrap',
          justifyContent: 'center'
        }}>
          <button
            onClick={() => setCurrentRegion(currentRegion === 'alaska' ? null : 'alaska')}
            style={{
              backgroundColor: currentRegion === 'alaska' ? '#3b82f6' : regions.alaska ? '#93c5fd' : '#e5e7eb',
              color: currentRegion === 'alaska' || regions.alaska ? 'white' : '#666',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            {regions.alaska ? '✓' : ''} Mark Alaska
          </button>
          
          <button
            onClick={() => setCurrentRegion(currentRegion === 'hawaii' ? null : 'hawaii')}
            style={{
              backgroundColor: currentRegion === 'hawaii' ? '#10b981' : regions.hawaii ? '#6ee7b7' : '#e5e7eb',
              color: currentRegion === 'hawaii' || regions.hawaii ? 'white' : '#666',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            {regions.hawaii ? '✓' : ''} Mark Hawaii
          </button>
        </div>

        {currentRegion && (
          <p style={{
            margin: '0 0 12px 0',
            color: '#3b82f6',
            fontSize: '13px',
            fontWeight: '500'
          }}>
            Click and drag to mark {currentRegion === 'alaska' ? 'Alaska' : 'Hawaii'} region
          </p>
        )}
        
        <div 
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            cursor: currentRegion && isSelecting ? 'crosshair' : currentRegion ? 'crosshair' : 'default'
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Select Alaska/Hawaii regions"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              display: 'block',
              userSelect: 'none'
            }}
            draggable={false}
          />
          
          {/* Alaska selection */}
          {getSelectionStyle('alaska') && (
            <div style={getSelectionStyle('alaska')} />
          )}
          {getConfirmedStyle('alaska') && (
            <div style={getConfirmedStyle('alaska')}>
              <div style={{
                position: 'absolute',
                top: '-20px',
                left: 0,
                backgroundColor: '#3b82f6',
                color: 'white',
                padding: '2px 6px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                Alaska
              </div>
            </div>
          )}
          
          {/* Hawaii selection */}
          {getSelectionStyle('hawaii') && (
            <div style={getSelectionStyle('hawaii')} />
          )}
          {getConfirmedStyle('hawaii') && (
            <div style={getConfirmedStyle('hawaii')}>
              <div style={{
                position: 'absolute',
                top: '-20px',
                left: 0,
                backgroundColor: '#10b981',
                color: 'white',
                padding: '2px 6px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                Hawaii
              </div>
            </div>
          )}
        </div>

        {/* Clear buttons for regions */}
        {(regions.alaska || regions.hawaii) && (
          <div style={{
            marginTop: '12px',
            display: 'flex',
            gap: '8px',
            fontSize: '12px'
          }}>
            {regions.alaska && (
              <button
                onClick={() => handleClearRegion('alaska')}
                style={{
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer'
                }}
              >
                Clear Alaska
              </button>
            )}
            {regions.hawaii && (
              <button
                onClick={() => handleClearRegion('hawaii')}
                style={{
                  backgroundColor: '#ef4444',
                  color: 'white',
                  border: 'none',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer'
                }}
              >
                Clear Hawaii
              </button>
            )}
          </div>
        )}
        
        <div style={{
          marginTop: '20px',
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          flexWrap: 'wrap',
          justifyContent: 'center'
        }}>
          <button
            onClick={handleConfirmAll}
            style={{
              backgroundColor: '#28a745',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            {hasAnySelection ? 'Confirm & Continue' : 'Skip (CONUS Only)'}
          </button>
          
          <button
            onClick={onSkip}
            style={{
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}

