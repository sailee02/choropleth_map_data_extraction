import React, { useState, useRef, useEffect } from 'react';
import ConusOverlayPreview from './ConusOverlayPreview';
import ConusManualAlign from './ConusManualAlign';
import AlaskaManualAlign from './AlaskaManualAlign';

export default function RegionSelector({ imageUrl, uploadId, projection, onSelectionComplete, onCancel, onSkip }) {
  const [regions, setRegions] = useState({ conus: null, alaska: null, hawaii: null });
  const [currentRegion, setCurrentRegion] = useState(null); // 'conus', 'alaska', or 'hawaii'
  const [isSelecting, setIsSelecting] = useState(false);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [cursorPos, setCursorPos] = useState(null); // For crosshair guides
  const [showConusPreview, setShowConusPreview] = useState(false);
  const [showConusManualAlign, setShowConusManualAlign] = useState(false);
  const [showAlaskaManualAlign, setShowAlaskaManualAlign] = useState(false);
  const [conusOverlayParams, setConusOverlayParams] = useState(null);
  const imageRef = useRef(null);
  const containerRef = useRef(null);

  // Global mouse handlers to continue selection even when cursor goes outside
  useEffect(() => {
    const handleGlobalMouseMove = (e) => {
      if (isSelecting && imageRef.current && containerRef.current) {
        const rect = imageRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        // Constrain to image bounds
        const constrainedX = Math.max(0, Math.min(x, rect.width));
        const constrainedY = Math.max(0, Math.min(y, rect.height));
        
        // Update end point (always update, even if outside - will be constrained)
        setEndPoint({ x: constrainedX, y: constrainedY });
        
        // Update crosshairs only when inside image
        const isInside = x >= 0 && x <= rect.width && y >= 0 && y <= rect.height;
        if (isInside) {
          setCursorPos({ x: constrainedX, y: constrainedY });
        } else {
          setCursorPos(null);
        }
      }
    };

    const handleGlobalMouseUp = () => {
      if (isSelecting && startPoint && endPoint && currentRegion && imageRef.current) {
        const rect = imageRef.current.getBoundingClientRect();
        const left = Math.min(startPoint.x, endPoint.x);
        const top = Math.min(startPoint.y, endPoint.y);
        const width = Math.abs(endPoint.x - startPoint.x);
        const height = Math.abs(endPoint.y - startPoint.y);
        
        // Constrain to image bounds
        const constrainedLeft = Math.max(0, Math.min(left, rect.width));
        const constrainedTop = Math.max(0, Math.min(top, rect.height));
        const constrainedWidth = Math.min(width, rect.width - constrainedLeft);
        const constrainedHeight = Math.min(height, rect.height - constrainedTop);
        
        if (constrainedWidth > 10 && constrainedHeight > 10) {
          const imageWidth = imageRef.current.naturalWidth;
          const imageHeight = imageRef.current.naturalHeight;
          
          // Convert to natural image coordinates
          const natLeft = (constrainedLeft / rect.width) * imageWidth;
          const natTop = (constrainedTop / rect.height) * imageHeight;
          const natWidth = (constrainedWidth / rect.width) * imageWidth;
          const natHeight = (constrainedHeight / rect.height) * imageHeight;
          
          // Compute rect4 coordinates (clockwise: TL, TR, BR, BL)
          const natRight = natLeft + natWidth;
          const natBottom = natTop + natHeight;
          const rect4 = [
            [Math.round(natLeft), Math.round(natTop)],      // Top-left
            [Math.round(natRight), Math.round(natTop)],    // Top-right
            [Math.round(natRight), Math.round(natBottom)], // Bottom-right
            [Math.round(natLeft), Math.round(natBottom)]   // Bottom-left
          ];
          
          const imageSelection = {
            x: natLeft,
            y: natTop,
            width: natWidth,
            height: natHeight,
            rect4: rect4
          };
          
          setRegions(prev => ({
            ...prev,
            [currentRegion]: imageSelection
          }));
          
          // If CONUS was just selected, show manual alignment
          if (currentRegion === 'conus') {
            setShowConusManualAlign(true);
          }
          // If Alaska was just selected, show manual alignment
          if (currentRegion === 'alaska') {
            setShowAlaskaManualAlign(true);
          }
        }
        
        setIsSelecting(false);
        setStartPoint(null);
        setEndPoint(null);
        setCurrentRegion(null);
        setCursorPos(null);
      }
    };

    if (isSelecting) {
      window.addEventListener('mousemove', handleGlobalMouseMove);
      window.addEventListener('mouseup', handleGlobalMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleGlobalMouseMove);
        window.removeEventListener('mouseup', handleGlobalMouseUp);
      };
    }
  }, [isSelecting, startPoint, endPoint, currentRegion]);

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
    if (!imageRef.current || !containerRef.current) return;
    
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // Check if cursor is within image bounds
    const isInside = x >= 0 && x <= rect.width && y >= 0 && y <= rect.height;
    
    const constrainedX = Math.max(0, Math.min(x, rect.width));
    const constrainedY = Math.max(0, Math.min(y, rect.height));
    
    // Update cursor position for crosshairs (only when inside image)
    if (currentRegion && isInside) {
      setCursorPos({ x: constrainedX, y: constrainedY });
    } else if (currentRegion && !isInside) {
      // Hide crosshairs when outside
      setCursorPos(null);
    }
    
    // Update end point if selecting (always update, even if outside - will be constrained)
    if (isSelecting) {
      setEndPoint({ x: constrainedX, y: constrainedY });
    }
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
        
        // Convert to natural image coordinates
        const natLeft = (left / rect.width) * imageWidth;
        const natTop = (top / rect.height) * imageHeight;
        const natWidth = (width / rect.width) * imageWidth;
        const natHeight = (height / rect.height) * imageHeight;
        
        // Compute rect4 coordinates (clockwise: TL, TR, BR, BL)
        const natRight = natLeft + natWidth;
        const natBottom = natTop + natHeight;
        const rect4 = [
          [Math.round(natLeft), Math.round(natTop)],      // Top-left
          [Math.round(natRight), Math.round(natTop)],    // Top-right
          [Math.round(natRight), Math.round(natBottom)], // Bottom-right
          [Math.round(natLeft), Math.round(natBottom)]   // Bottom-left
        ];
        
        const imageSelection = {
          x: natLeft,
          y: natTop,
          width: natWidth,
          height: natHeight,
          rect4: rect4
        };
        
        setRegions(prev => ({
          ...prev,
          [currentRegion]: imageSelection
        }));
        
        // If CONUS was just selected, show overlay preview
        if (currentRegion === 'conus') {
          setShowConusPreview(true);
        }
      
      setStartPoint(null);
      setEndPoint(null);
      setCurrentRegion(null);
      setCursorPos(null);
    } else {
      setStartPoint(null);
      setEndPoint(null);
    }
  };

  const handleMouseLeave = () => {
    // Don't cancel selection, just hide crosshairs when mouse leaves
    // Selection will resume when mouse comes back
    setCursorPos(null);
  };

  const handleConfirmAll = () => {
    if (imageRef.current) {
      // Include overlay parameters if CONUS was adjusted
      const finalRegions = { ...regions };
      if (conusOverlayParams && finalRegions.conus) {
        finalRegions.conus.overlayParams = conusOverlayParams;
      }
      onSelectionComplete(finalRegions);
    }
  };

  const handleConusPreviewConfirm = (overlayParams) => {
    setConusOverlayParams(overlayParams);
    setShowConusPreview(false);
    // Update CONUS selection with overlay params
    setRegions(prev => ({
      ...prev,
      conus: {
        ...prev.conus,
        overlayParams: overlayParams
      }
    }));
  };

  const handleConusPreviewCancel = () => {
    setShowConusPreview(false);
  };

  const handleConusManualAlignConfirm = (alignmentParams) => {
    // Store alignment parameters
    setConusOverlayParams(alignmentParams);
    setShowConusManualAlign(false);
    
    // Extract rect4 from alignment params (user's manually aligned rectangle)
    const userRect4 = alignmentParams.rect4 || null;
    
    // Calculate x, y, width, height from rect4
    let x = 0, y = 0, width = 0, height = 0;
    if (userRect4 && userRect4.length === 4) {
      const [tl, tr, br, bl] = userRect4;
      x = Math.min(tl[0], bl[0]);
      y = Math.min(tl[1], tr[1]);
      const right = Math.max(tr[0], br[0]);
      const bottom = Math.max(br[1], bl[1]);
      width = right - x;
      height = bottom - y;
    }
    
    // Create a CONUS region entry with the user's manually aligned rect4
    setRegions(prev => ({
      ...prev,
      conus: {
        x: x,
        y: y,
        width: width,
        height: height,
        rect4: userRect4, // User's manually aligned rectangle
        alignmentParams: alignmentParams // Store full alignment params for backend
      }
    }));
  };

  const handleConusManualAlignCancel = () => {
    setShowConusManualAlign(false);
  };

  const handleAlaskaManualAlignConfirm = (alignmentParams) => {
    // Store alignment parameters
    setShowAlaskaManualAlign(false);
    
    // Extract rect4 from alignment params (user's manually aligned rectangle)
    const userRect4 = alignmentParams.rect4 || null;
    
    // Calculate x, y, width, height from rect4
    let x = 0, y = 0, width = 0, height = 0;
    if (userRect4 && userRect4.length === 4) {
      const [tl, tr, br, bl] = userRect4;
      x = Math.min(tl[0], bl[0]);
      y = Math.min(tl[1], tr[1]);
      const right = Math.max(tr[0], br[0]);
      const bottom = Math.max(br[1], bl[1]);
      width = right - x;
      height = bottom - y;
    }
    
    // Create an Alaska region entry with the user's manually aligned rect4
    setRegions(prev => ({
      ...prev,
      alaska: {
        x: x,
        y: y,
        width: width,
        height: height,
        rect4: userRect4, // User's manually aligned rectangle
        alignmentParams: alignmentParams // Store full alignment params for backend
      }
    }));
  };

  const handleAlaskaManualAlignCancel = () => {
    setShowAlaskaManualAlign(false);
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
    
    const regionColors = {
      conus: { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)' },
      alaska: { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)' },
      hawaii: { border: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' }
    };
    
    const colors = regionColors[region] || regionColors.alaska;
    
    return {
      position: 'absolute',
      left: (selection.x / imageWidth) * rect.width,
      top: (selection.y / imageHeight) * rect.height,
      width: (selection.width / imageWidth) * rect.width,
      height: (selection.height / imageHeight) * rect.height,
      border: `2px solid ${colors.border}`,
      backgroundColor: colors.bg,
      pointerEvents: 'none',
      zIndex: 10
    };
  };

  const hasAnySelection = regions.conus || regions.alaska || regions.hawaii;

  // Show CONUS manual alignment if requested
  if (showConusManualAlign && uploadId) {
    return (
      <ConusManualAlign
        imageUrl={imageUrl}
        uploadId={uploadId}
        projection={projection || "4326"}
        onConfirm={handleConusManualAlignConfirm}
        onCancel={handleConusManualAlignCancel}
      />
    );
  }

  // Show Alaska manual alignment if requested
  if (showAlaskaManualAlign && uploadId) {
    return (
      <AlaskaManualAlign
        imageUrl={imageUrl}
        uploadId={uploadId}
        projection={projection || "4326"}
        onConfirm={handleAlaskaManualAlignConfirm}
        onCancel={handleAlaskaManualAlignCancel}
      />
    );
  }

  // Show CONUS overlay preview if CONUS is selected (legacy, for backward compatibility)
  if (showConusPreview && regions.conus && uploadId) {
    return (
      <ConusOverlayPreview
        imageUrl={imageUrl}
        uploadId={uploadId}
        conusSelection={regions.conus}
        projection={projection || "4326"}
        onConfirm={handleConusPreviewConfirm}
        onCancel={handleConusPreviewCancel}
      />
    );
  }

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
          Mark Map Regions
        </h3>
        
        <p style={{
          margin: '0 0 20px 0',
          color: '#666',
          fontSize: '14px',
          textAlign: 'center',
          maxWidth: '500px'
        }}>
          Click "Mark CONUS" to align the shapefile overlay manually.
          <br />
          Click "Mark Alaska" to align Alaska shapefile manually.
          <br />
          Optionally mark Hawaii region using the crosshair guides.
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
            onClick={() => {
              if (currentRegion === 'conus') {
                setCurrentRegion(null);
                setCursorPos(null);
              } else {
                // Show manual alignment for CONUS
                setShowConusManualAlign(true);
              }
            }}
            style={{
              backgroundColor: currentRegion === 'conus' ? '#ef4444' : regions.conus ? '#fca5a5' : '#e5e7eb',
              color: currentRegion === 'conus' || regions.conus ? 'white' : '#666',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            {regions.conus ? '✓' : ''} Mark CONUS
          </button>
          
          <button
            onClick={() => {
              if (currentRegion === 'alaska') {
                setCurrentRegion(null);
                setCursorPos(null);
              } else {
                // Show manual alignment for Alaska
                setShowAlaskaManualAlign(true);
              }
            }}
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
            onClick={() => {
              const newRegion = currentRegion === 'hawaii' ? null : 'hawaii';
              setCurrentRegion(newRegion);
              if (!newRegion) setCursorPos(null);
            }}
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
            color: currentRegion === 'conus' ? '#ef4444' : currentRegion === 'alaska' ? '#3b82f6' : '#10b981',
            fontSize: '13px',
            fontWeight: '500'
          }}>
            Click and drag to mark {currentRegion === 'conus' ? 'CONUS' : currentRegion === 'alaska' ? 'Alaska' : 'Hawaii'} region
            <br />
            <span style={{ fontSize: '11px', fontWeight: '400' }}>Crosshair guides will help you align precisely</span>
          </p>
        )}
        
        <div 
          ref={containerRef}
          style={{
            position: 'relative',
            display: 'inline-block',
            maxWidth: '100%',
            maxHeight: '60vh',
            cursor: currentRegion ? 'crosshair' : 'default'
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Select map regions"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              display: 'block',
              userSelect: 'none'
            }}
            draggable={false}
          />
          
          {/* Crosshair guides */}
          {currentRegion && cursorPos && imageRef.current && (
            <>
              {/* Vertical line */}
              <div style={{
                position: 'absolute',
                left: cursorPos.x,
                top: 0,
                width: '0px',
                height: imageRef.current.getBoundingClientRect().height,
                borderLeft: '1px dashed rgba(0, 0, 0, 0.5)',
                pointerEvents: 'none',
                zIndex: 5
              }} />
              {/* Horizontal line */}
              <div style={{
                position: 'absolute',
                left: 0,
                top: cursorPos.y,
                width: imageRef.current.getBoundingClientRect().width,
                height: '0px',
                borderTop: '1px dashed rgba(0, 0, 0, 0.5)',
                pointerEvents: 'none',
                zIndex: 5
              }} />
            </>
          )}
          
          {/* CONUS selection */}
          {getSelectionStyle('conus') && (
            <div style={getSelectionStyle('conus')} />
          )}
          {getConfirmedStyle('conus') && (
            <div style={getConfirmedStyle('conus')}>
              <div style={{
                position: 'absolute',
                top: '-20px',
                left: 0,
                backgroundColor: '#ef4444',
                color: 'white',
                padding: '2px 6px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                CONUS
              </div>
            </div>
          )}
          
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
        {(regions.conus || regions.alaska || regions.hawaii) && (
          <div style={{
            marginTop: '12px',
            display: 'flex',
            gap: '8px',
            fontSize: '12px',
            flexWrap: 'wrap',
            justifyContent: 'center'
          }}>
            {regions.conus && (
              <button
                onClick={() => handleClearRegion('conus')}
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
                Clear CONUS
              </button>
            )}
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
            disabled={!regions.conus}
            style={{
              backgroundColor: regions.conus ? '#28a745' : '#9ca3af',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: '500',
              cursor: regions.conus ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s ease',
              opacity: regions.conus ? 1 : 0.6
            }}
          >
            {regions.conus ? 'Confirm & Continue' : 'Mark CONUS to Continue'}
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

