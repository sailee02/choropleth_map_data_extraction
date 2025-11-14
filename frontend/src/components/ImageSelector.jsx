import React, { useState, useRef, useEffect } from 'react';

export default function ImageSelector({ imageUrl, onSelectionComplete, onCancel }) {
  const [isSelecting, setIsSelecting] = useState(false);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [selection, setSelection] = useState(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);

  const handleMouseDown = (e) => {
    if (!imageRef.current) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Check if click is within image bounds
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
    
    // Constrain to image bounds
    const constrainedX = Math.max(0, Math.min(x, rect.width));
    const constrainedY = Math.max(0, Math.min(y, rect.height));
    
    setEndPoint({ x: constrainedX, y: constrainedY });
  };

  const handleMouseUp = () => {
    if (!isSelecting || !startPoint || !endPoint) return;
    
    setIsSelecting(false);
    
    // Calculate selection rectangle
    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);
    
    // Only create selection if it's large enough
    if (width > 10 && height > 10) {
      const newSelection = { left, top, width, height };
      setSelection(newSelection);
    } else {
      setStartPoint(null);
      setEndPoint(null);
    }
  };

  const handleConfirmSelection = () => {
    if (selection && imageRef.current) {
      const rect = imageRef.current.getBoundingClientRect();
      const imageWidth = imageRef.current.naturalWidth;
      const imageHeight = imageRef.current.naturalHeight;
      
      // Convert screen coordinates to image coordinates
      const imageSelection = {
        x: (selection.left / rect.width) * imageWidth,
        y: (selection.top / rect.height) * imageHeight,
        width: (selection.width / rect.width) * imageWidth,
        height: (selection.height / rect.height) * imageHeight
      };
      
      onSelectionComplete(imageSelection);
    }
  };

  const handleClearSelection = () => {
    setSelection(null);
    setStartPoint(null);
    setEndPoint(null);
  };

  const getSelectionStyle = () => {
    if (!startPoint || !endPoint) return null;
    
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
      border: '2px solid #007bff',
      backgroundColor: 'rgba(0, 123, 255, 0.1)',
      pointerEvents: 'none',
      zIndex: 10
    };
  };

  const getConfirmedSelectionStyle = () => {
    if (!selection) return null;
    
    return {
      position: 'absolute',
      left: selection.left,
      top: selection.top,
      width: selection.width,
      height: selection.height,
      border: '2px solid #28a745',
      backgroundColor: 'rgba(40, 167, 69, 0.1)',
      pointerEvents: 'none',
      zIndex: 10
    };
  };

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
          margin: '0 0 16px 0',
          color: '#333',
          fontSize: '20px',
          fontWeight: '600'
        }}>
          Select Legend Area
        </h3>
        
        <p style={{
          margin: '0 0 20px 0',
          color: '#666',
          fontSize: '14px',
          textAlign: 'center',
          maxWidth: '400px'
        }}>
          Click and drag to draw a rectangle around the legend area in your image.
        </p>
        
        <div 
          ref={containerRef}
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            cursor: isSelecting ? 'crosshair' : 'default'
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Select legend area"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              display: 'block',
              userSelect: 'none'
            }}
            draggable={false}
          />
          
          {/* Selection rectangle while dragging */}
          {isSelecting && getSelectionStyle() && (
            <div style={getSelectionStyle()} />
          )}
          
          {/* Confirmed selection rectangle */}
          {!isSelecting && getConfirmedSelectionStyle() && (
            <div style={getConfirmedSelectionStyle()} />
          )}
        </div>
        
        <div style={{
          marginTop: '20px',
          display: 'flex',
          gap: '12px',
          alignItems: 'center'
        }}>
          <button
            onClick={handleConfirmSelection}
            disabled={!selection}
            style={{
              backgroundColor: selection ? '#28a745' : '#ccc',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: selection ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s ease'
            }}
          >
            Confirm Selection
          </button>
          
          <button
            onClick={handleClearSelection}
            disabled={!selection}
            style={{
              backgroundColor: selection ? '#6c757d' : '#ccc',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: selection ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s ease'
            }}
          >
            Clear
          </button>
          
          <button
            onClick={onCancel}
            style={{
              backgroundColor: '#dc3545',
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
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
