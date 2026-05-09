import React, { useState, useEffect, useRef } from 'react';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";


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
  const [selectedCounties, setSelectedCounties] = useState([]); 
  const [currentStep, setCurrentStep] = useState(0); 
  
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);

  
  const getRGBAtNaturalCoords = (natX, natY) => {
    if (!imageRef.current || !canvasRef.current) return null;
    
    const img = imageRef.current;
    if (!img.complete || img.naturalWidth === 0) return null;
    
    const naturalWidth = img.naturalWidth;
    const naturalHeight = img.naturalHeight;
    
    
    const x = Math.round(Math.max(0, Math.min(natX, naturalWidth - 1)));
    const y = Math.round(Math.max(0, Math.min(natY, naturalHeight - 1)));
    
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    canvas.width = naturalWidth;
    canvas.height = naturalHeight;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0);
    const imageData = ctx.getImageData(x, y, 1, 1);
    const [r, g, b] = imageData.data;
    
    return { r, g, b };
  };

  
  const handleHawaiiClick = (e) => {
    if (!imageRef.current || !hawaiiSelection || !containerRef.current) return;
    if (!imageLoaded) return;
    
    
    if (selectedCounties.length >= 5) return;
    
    // Use the actual rendered <img> box to avoid container border/padding offsets.
    const imgRect = imageRef.current.getBoundingClientRect();
    if (!imgRect || imgRect.width <= 1 || imgRect.height <= 1) return;
    const clickX = e.clientX - imgRect.left;
    const clickY = e.clientY - imgRect.top;
    if (clickX < 0 || clickY < 0 || clickX > imgRect.width || clickY > imgRect.height) return;

    const natWidth = imageRef.current.naturalWidth;
    const natHeight = imageRef.current.naturalHeight;
    if (!natWidth || !natHeight) return;
    const natX = (clickX / imgRect.width) * natWidth;
    const natY = (clickY / imgRect.height) * natHeight;
    
    
    const hiX = hawaiiSelection.x;
    const hiY = hawaiiSelection.y;
    const hiWidth = hawaiiSelection.width;
    const hiHeight = hawaiiSelection.height;
    
    if (natX < hiX || natX > hiX + hiWidth || natY < hiY || natY > hiY + hiHeight) {
      return; 
    }
    
    
    const rgb = getRGBAtNaturalCoords(natX, natY);
    if (!rgb) {
      console.error('Failed to extract RGB at coordinates:', natX, natY);
      return;
    }
    
    const county = HAWAII_COUNTIES[selectedCounties.length]; 
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
    
    
    if (selectedCounties.length < 4) {
      setCurrentStep(selectedCounties.length + 1);
    }
  };

  
  const getHawaiiRectStyle = () => {
    if (!hawaiiSelection || !imageRef.current || !containerRef.current) return null;
    const imgRect = imageRef.current.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();
    const natWidth = imageRef.current.naturalWidth;
    const natHeight = imageRef.current.naturalHeight;
    if (!natWidth || !natHeight || imgRect.width <= 1 || imgRect.height <= 1) return null;

    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;

    return {
      position: 'absolute',
      left: offsetX + (hawaiiSelection.x / natWidth) * imgRect.width,
      top: offsetY + (hawaiiSelection.y / natHeight) * imgRect.height,
      width: (hawaiiSelection.width / natWidth) * imgRect.width,
      height: (hawaiiSelection.height / natHeight) * imgRect.height,
      border: '3px solid #10b981',
      backgroundColor: 'rgba(16, 185, 129, 0.1)',
      pointerEvents: 'none',
      zIndex: 5,
    };
  };

  const handleConfirm = () => {
    if (selectedCounties.length !== 5) {
      alert('Please select all 5 counties');
      return;
    }
    
    
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

        
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '1fr 1fr', 
          gap: '16px',
          marginBottom: '16px'
        }}>
          
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
                src={`${import.meta.env.BASE_URL}hawaii_colored_counties.png`}
                alt="Hawaii Counties Reference"
                style={{
                  maxWidth: '100%',
                  height: 'auto',
                  display: 'block'
                }}
                onError={(e) => {
                  
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

          
          <div>
            <p style={{ fontSize: '12px', color: '#666', marginBottom: '8px', fontWeight: '500' }}>
              Zoomed Hawaii Region: Click on counties in order
            </p>
            <div
              ref={containerRef}
              style={{
                position: 'relative',
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
                      
                      if (imageRef.current && hawaiiSelection && containerRef.current) {
                        const natWidth = imageRef.current.naturalWidth;
                        const natHeight = imageRef.current.naturalHeight;
                        const containerWidth = containerRef.current.clientWidth || 800;
                        const containerHeight = containerRef.current.clientHeight || 600;
                        
                        
                        const padding = 10;
                        const availableWidth = containerWidth - (padding * 2);
                        const availableHeight = containerHeight - (padding * 2);
                        
                        const scale = Math.min(
                          availableWidth / hawaiiSelection.width,
                          availableHeight / hawaiiSelection.height
                        );
                        
                        
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
                  
                  
                  {imageLoaded && selectedCounties.map((county, idx) => {
                    if (!imageRef.current || !hawaiiSelection || !containerRef.current) return null;
                    
                    const natWidth = imageRef.current.naturalWidth;
                    const natHeight = imageRef.current.naturalHeight;
                    if (!natWidth || !natHeight) return null;

                    const imgRect = imageRef.current.getBoundingClientRect();
                    const containerRect = containerRef.current.getBoundingClientRect();
                    if (!imgRect || imgRect.width <= 1 || imgRect.height <= 1) return null;

                    const offsetX = imgRect.left - containerRect.left;
                    const offsetY = imgRect.top - containerRect.top;

                    // Convert natural image coords -> displayed pixel coords (relative to container)
                    const displayX = offsetX + (county.countyClick.x / natWidth) * imgRect.width;
                    const displayY = offsetY + (county.countyClick.y / natHeight) * imgRect.height;
                    
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

