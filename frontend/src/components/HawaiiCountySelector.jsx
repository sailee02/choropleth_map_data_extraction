import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

// Hawaii counties from left to right (west to east)
const HAWAII_COUNTIES = [
  { name: "Kauai County, Hawaii", geoid: "15007", region: "West", description: "Kauai (leftmost island)" },
  { name: "Honolulu County, Hawaii", geoid: "15003", region: "Central-West", description: "Honolulu/Oahu (second from left)" },
  { name: "Kalawao County, Hawaii", geoid: "15005", region: "Central", description: "Kalawao (small island, third from left)" },
  { name: "Maui County, Hawaii", geoid: "15009", region: "Central-East", description: "Maui (fourth from left)" },
  { name: "Hawaii County, Hawaii", geoid: "15001", region: "East", description: "Hawaii/Big Island (rightmost, largest)" }
];

export default function HawaiiCountySelector({ 
  imageUrl, 
  uploadId, 
  hawaiiSelection = null,
  onConfirm, 
  onCancel 
}) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [selectedCounties, setSelectedCounties] = useState([]); // Array of {countyClick: {x, y, rgb}, countyName, geoid, step}
  const [currentStep, setCurrentStep] = useState(0); // 0-4: which county we're selecting (0 = first, 4 = last)
  
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);

  // Extract RGB from image at natural coordinates
  const getRGBAtNaturalCoords = (natX, natY) => {
    if (!imageRef.current || !canvasRef.current) return null;
    
    const img = imageRef.current;
    if (!img.complete || img.naturalWidth === 0) return null;
    
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    
    // Ensure coordinates are within bounds
    const x = Math.round(Math.max(0, Math.min(natX, naturalWidth - 1)));
    const y = Math.round(Math.max(0, Math.min(natY, naturalHeight - 1)));
    
    // Create canvas to read pixel
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    canvas.width = naturalWidth;
    canvas.height = naturalHeight;
    
    ctx.drawImage(img, 0, 0);
    const imageData = ctx.getImageData(x, y, 1, 1);
    const [r, g, b] = imageData.data;
    
    return { r, g, b };
  };

  // Handle click on Hawaii rectangle (selecting the actual county location)
  const handleHawaiiClick = (e) => {
    if (!imageRef.current || !hawaiiSelection || !containerRef.current) return;
    
    // Check if we've already selected all 5 counties
    if (selectedCounties.length >= 5) return;
    
    const containerRect = containerRef.current.getBoundingClientRect();
    const clickX = e.clientX - containerRect.left;
    const clickY = e.clientY - containerRect.top;
    
    // Calculate scale factor for zoomed view (same as in onLoad)
    const natWidth = imageRef.current.naturalWidth;
    const natHeight = imageRef.current.naturalHeight;
    const padding = 10;
    const availableWidth = containerRect.width - (padding * 2);
    const availableHeight = containerRect.height - (padding * 2);
    
    const scale = Math.min(
      availableWidth / hawaiiSelection.width,
      availableHeight / hawaiiSelection.height
    );
    
    // Convert click coordinates to natural image coordinates
    // Account for padding and the translation
    const natX = hawaiiSelection.x + ((clickX - padding) / scale);
    const natY = hawaiiSelection.y + ((clickY - padding) / scale);
    
    // Verify click is within Hawaii rectangle bounds
    const hiX = hawaiiSelection.x;
    const hiY = hawaiiSelection.y;
    const hiWidth = hawaiiSelection.width;
    const hiHeight = hawaiiSelection.height;
    
    if (natX < hiX || natX > hiX + hiWidth || natY < hiY || natY > hiY + hiHeight) {
      return; // Click outside Hawaii rectangle
    }
    
    // Get RGB at natural coordinates
    const rgb = getRGBAtNaturalCoords(natX, natY);
    if (!rgb) {
      console.error('Failed to extract RGB at coordinates:', natX, natY);
      return;
    }
    
    const county = HAWAII_COUNTIES[selectedCounties.length]; // Select in order: 0, 1, 2, 3, 4
    const newCounty = {
      countyClick: {
        x: natX,
        y: natY,
        rgb: rgb
      },
      countyName: county.name,
      geoid: county.geoid,
      step: selectedCounties.length
    };
    
    setSelectedCounties(prev => [...prev, newCounty]);
    
    // Move to next step if not done
    if (selectedCounties.length < 4) {
      setCurrentStep(selectedCounties.length + 1);
    }
  };

  // Calculate Hawaii rectangle bounds for zooming
  const getHawaiiRectStyle = () => {
    if (!hawaiiSelection || !imageRef.current) return null;
    
    const rect = imageRef.current.getBoundingClientRect();
    const natWidth = imageRef.current.naturalWidth;
    const natHeight = imageRef.current.naturalHeight;
    
    return {
      position: 'absolute',
      left: (hawaiiSelection.x / natWidth) * rect.width,
      top: (hawaiiSelection.y / natHeight) * rect.height,
      width: (hawaiiSelection.width / natWidth) * rect.width,
      height: (hawaiiSelection.height / natHeight) * rect.height,
      border: '3px solid #10b981',
      backgroundColor: 'rgba(16, 185, 129, 0.1)',
      pointerEvents: 'none',
      zIndex: 5
    };
  };

  const handleConfirm = () => {
    if (selectedCounties.length !== 5) {
      alert('Please select all 5 counties');
      return;
    }
    
    // Pass the selected counties with RGB values to parent
    onConfirm({
      hawaiiCounties: selectedCounties,
      hawaiiSelection: hawaiiSelection
    });
  };

  const allSelected = selectedCounties.length === 5;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '8px',
        padding: '24px',
        maxWidth: '90vw',
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
      }}>
        <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Select Hawaii Counties</h2>
        
        <div style={{ marginBottom: '16px' }}>
          <p style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: '500' }}>
            Step {selectedCounties.length + 1} of 5: Click on the {selectedCounties.length < 5 ? HAWAII_COUNTIES[selectedCounties.length].name.split(',')[0] : 'last'} county in the map below
          </p>
          <p style={{ margin: '0', fontSize: '12px', color: '#666' }}>
            Select counties from left to right (west to east) matching the reference image
          </p>
        </div>

        {/* Reference image and zoomed map side by side */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '1fr 1fr', 
          gap: '16px',
          marginBottom: '16px'
        }}>
          {/* Reference image */}
          <div>
            <p style={{ fontSize: '12px', color: '#666', marginBottom: '8px', fontWeight: '500' }}>
              Reference Image (Select in this order):
            </p>
            <div style={{
              border: '2px solid #ddd',
              borderRadius: '6px',
              padding: '8px',
              backgroundColor: '#f9fafb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '300px'
            }}>
              <img
                src="/hawaii_colored_counties.png"
                alt="Hawaii Counties Reference"
                style={{
                  maxWidth: '100%',
                  height: 'auto',
                  display: 'block'
                }}
                onError={(e) => {
                  // Fallback if image doesn't exist - show text guide
                  e.target.style.display = 'none';
                  const parent = e.target.parentElement;
                  if (parent && !parent.querySelector('.fallback-text')) {
                    const fallback = document.createElement('div');
                    fallback.className = 'fallback-text';
                    fallback.style.cssText = 'padding: 20px; text-align: center; color: #666;';
                    fallback.innerHTML = `
                      <div style="font-weight: bold; margin-bottom: 8px;">Select counties from left to right:</div>
                      <div>1. Kauai (leftmost)</div>
                      <div>2. Honolulu/Oahu</div>
                      <div>3. Kalawao</div>
                      <div>4. Maui</div>
                      <div>5. Hawaii/Big Island (rightmost)</div>
                    `;
                    parent.appendChild(fallback);
                  }
                }}
              />
            </div>
          </div>

          {/* Zoomed Hawaii map */}
          <div>
            <p style={{ fontSize: '12px', color: '#666', marginBottom: '8px', fontWeight: '500' }}>
              Zoomed Hawaii Region: Click on counties in order
            </p>
            <div
              ref={containerRef}
              style={{
                position: 'relative',
                display: 'inline-block',
                border: '3px solid #10b981',
                borderRadius: '6px',
                overflow: 'hidden',
                backgroundColor: '#f0fdf4',
                cursor: selectedCounties.length < 5 ? 'crosshair' : 'default',
                width: '100%',
                maxWidth: '800px',
                minHeight: '500px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              onClick={selectedCounties.length < 5 ? handleHawaiiClick : undefined}
            >
              {!hawaiiSelection ? (
                <div style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: '#666'
                }}>
                  Error: Hawaii selection not found. Please go back and select Hawaii rectangle first.
                </div>
              ) : !imageUrl ? (
                <div style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: '#666'
                }}>
                  Error: Image URL not provided.
                </div>
              ) : (
                <>
                  {/* Always render image so it can load */}
                  <img
                    ref={imageRef}
                    src={imageUrl}
                    alt="Hawaii Region (Zoomed)"
                    style={{
                      position: 'absolute',
                      display: imageLoaded ? 'block' : 'none',
                      top: 0,
                      left: 0
                    }}
                    onLoad={() => {
                      setImageLoaded(true);
                      // Adjust image to show only Hawaii region, zoomed in
                      if (imageRef.current && hawaiiSelection && containerRef.current) {
                        const natWidth = imageRef.current.naturalWidth;
                        const natHeight = imageRef.current.naturalHeight;
                        const containerWidth = containerRef.current.clientWidth || 800;
                        const containerHeight = containerRef.current.clientHeight || 600;
                        
                        // Calculate scale to fill container with Hawaii region (with some padding)
                        const padding = 10;
                        const availableWidth = containerWidth - (padding * 2);
                        const availableHeight = containerHeight - (padding * 2);
                        
                        const scale = Math.min(
                          availableWidth / hawaiiSelection.width,
                          availableHeight / hawaiiSelection.height
                        );
                        
                        // Set image size and position to show only Hawaii region
                        imageRef.current.style.width = `${natWidth * scale}px`;
                        imageRef.current.style.height = `${natHeight * scale}px`;
                        imageRef.current.style.left = `${padding - (hawaiiSelection.x * scale)}px`;
                        imageRef.current.style.top = `${padding - (hawaiiSelection.y * scale)}px`;
                      }
                    }}
                    onError={(e) => {
                      console.error('Failed to load image:', imageUrl);
                      setImageLoaded(false);
                    }}
                  />
                  <canvas ref={canvasRef} style={{ display: 'none' }} />
                  
                  {/* Show loading message while image loads */}
                  {!imageLoaded && (
                    <div style={{
                      padding: '40px',
                      textAlign: 'center',
                      color: '#666',
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)'
                    }}>
                      Loading Hawaii region...
                    </div>
                  )}
                  
                  {/* Mark selected county points - only show when image is loaded */}
                  {imageLoaded && selectedCounties.map((county, idx) => {
                    if (!imageRef.current || !hawaiiSelection || !containerRef.current) return null;
                    
                    const natWidth = imageRef.current.naturalWidth;
                    const natHeight = imageRef.current.naturalHeight;
                    const containerWidth = containerRef.current.clientWidth || 800;
                    const containerHeight = containerRef.current.clientHeight || 600;
                    
                    // Calculate scale (same as in onLoad)
                    const padding = 10;
                    const availableWidth = containerWidth - (padding * 2);
                    const availableHeight = containerHeight - (padding * 2);
                    
                    const scale = Math.min(
                      availableWidth / hawaiiSelection.width,
                      availableHeight / hawaiiSelection.height
                    );
                    
                    // Convert natural coordinates to display coordinates
                    const displayX = padding + (county.countyClick.x - hawaiiSelection.x) * scale;
                    const displayY = padding + (county.countyClick.y - hawaiiSelection.y) * scale;
                    
                    return (
                      <div
                        key={idx}
                        style={{
                          position: 'absolute',
                          left: `${displayX}px`,
                          top: `${displayY}px`,
                          transform: 'translate(-50%, -50%)',
                          width: '24px',
                          height: '24px',
                          borderRadius: '50%',
                          backgroundColor: '#10b981',
                          border: '3px solid white',
                          boxShadow: '0 2px 6px rgba(0,0,0,0.4)',
                          zIndex: 15,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'white',
                          fontSize: '12px',
                          fontWeight: 'bold'
                        }}
                        title={county.countyName}
                      >
                        {idx + 1}
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Selected counties summary */}
        {selectedCounties.length > 0 && (
          <div style={{ marginBottom: '16px', fontSize: '12px', padding: '12px', backgroundColor: '#f9fafb', borderRadius: '6px' }}>
            <strong>Selected Counties ({selectedCounties.length}/5):</strong>
            <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
              {selectedCounties.map((county, idx) => (
                <li key={idx}>
                  {idx + 1}. {county.countyName}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: '1px solid #ddd',
              backgroundColor: 'white',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!allSelected}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: allSelected ? '#10b981' : '#ccc',
              color: 'white',
              cursor: allSelected ? 'pointer' : 'not-allowed',
              fontSize: '14px',
              fontWeight: '500'
            }}
          >
            Confirm ({selectedCounties.length}/5)
          </button>
        </div>
      </div>
    </div>
  );
}

