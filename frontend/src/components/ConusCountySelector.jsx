import React, { useState, useEffect, useRef } from 'react';
import { computeTightBBoxFromGeoJSON, transformGeoJSONToPixelSpace, applyOverlayTransform, extractVerticesFromGeometry } from '../utils/geoJSONUtils';

const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";


const CONUS_COUNTIES = [
  { name: "Clallam County, Washington", geoid: "53009", region: "Northwest", description: "Click on Clallam County, WA (northwest corner of CONUS)" },
  { name: "Aroostook County, Maine", geoid: "23003", region: "Northeast", description: "Click on Aroostook County, ME (northeast corner)" },
  { name: "Cameron County, Texas", geoid: "48061", region: "Southwest", description: "Click on Cameron County, TX (southwest corner, near Mexico border)" },
  { name: "Miami-Dade County, Florida", geoid: "12086", region: "Southeast", description: "Click on Miami-Dade County, FL (southeast corner)" }
];

export default function ConusCountySelector({ 
  imageUrl, 
  uploadId, 
  projection = "4326",
  conusSelection = null,
  onConfirm, 
  onCancel 
}) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [selectedPoints, setSelectedPoints] = useState([]); 
  const [shapefileData, setShapefileData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [previewOverlay, setPreviewOverlay] = useState(null);
  const [computing, setComputing] = useState(false);
  const [alignmentData, setAlignmentData] = useState(null);
  const [imageScale, setImageScale] = useState(null);
  const [imageOffset, setImageOffset] = useState({ x: 0, y: 0 });
  
  
  const [overlayAdjustments, setOverlayAdjustments] = useState({
    translateX: 0,
    translateY: 0,
    scaleX: 1.0,
    scaleY: 1.0,
    centerX: 0,
    centerY: 0
  });
  const [isDragging, setIsDragging] = useState(false);
  const [isResizeHandleDragging, setIsResizeHandleDragging] = useState(false);
  const [activeResizeHandle, setActiveResizeHandle] = useState(null);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [resizeHandleStart, setResizeHandleStart] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);
  const [cornerPoints, setCornerPoints] = useState(null);
  const [originalCornerPoints, setOriginalCornerPoints] = useState(null);
  
  const imageRef = useRef(null);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const overlayRef = useRef(null);
  const dragHandleRef = useRef(null);

  
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
        
        if (data.geojson && data.geojson.features) {
          setShapefileData({
            ...data,
            features: data.geojson.features
          });
        } else if (data.features) {
          setShapefileData(data);
        } else {
          setShapefileData({
            ...data,
            features: []
          });
        }
      } catch (err) {
        setError(err.message);
        console.error('Failed to fetch shapefile:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchShapefile();
  }, [uploadId, projection]);

  
  const handleConusClick = (e) => {
    if (!imageRef.current || !conusSelection || !containerRef.current) return;
    
    
    if (selectedPoints.length >= 4) return;
    
    const containerRect = containerRef.current.getBoundingClientRect();
    const clickX = e.clientX - containerRect.left;
    const clickY = e.clientY - containerRect.top;
    
    
    const natWidth = imageRef.current.naturalWidth;
    const natHeight = imageRef.current.naturalHeight;
    const padding = 10;
    const availableWidth = containerRect.width - (padding * 2);
    const availableHeight = containerRect.height - (padding * 2);
    
    const scale = Math.min(
      availableWidth / conusSelection.width,
      availableHeight / conusSelection.height
    );
    
    
    const natX = conusSelection.x + ((clickX - padding) / scale);
    const natY = conusSelection.y + ((clickY - padding) / scale);
    
    
    const conusX = conusSelection.x;
    const conusY = conusSelection.y;
    const conusWidth = conusSelection.width;
    const conusHeight = conusSelection.height;
    
    if (natX < conusX || natX > conusX + conusWidth || natY < conusY || natY > conusY + conusHeight) {
      return; 
    }
    
    
    const currentCounty = CONUS_COUNTIES[selectedPoints.length];
    
    const newPoint = {
      x: natX,
      y: natY,
      countyName: currentCounty.name,
      geoid: currentCounty.geoid
    };
    
    setSelectedPoints(prev => [...prev, newPoint]);
  };

  
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
      console.log('Alignment response:', data);
      
      
      if (data.overlayUrl) {
        const fullUrl = `${API_ROOT}${data.overlayUrl}`;
        console.log('Setting preview overlay:', fullUrl);
        setPreviewOverlay(fullUrl);
      } else {
        console.warn('No overlayUrl in response:', data);
      }
      
      
      
      let bounds = shapefileData?.bounds;
      if (!bounds && shapefileData?.geojson?.features && shapefileData.geojson.features.length > 0) {
        let xmin = Infinity, ymin = Infinity, xmax = -Infinity, ymax = -Infinity;
        for (const feature of shapefileData.geojson.features) {
          const vertices = extractVerticesFromGeometry(feature.geometry);
          for (const [x, y] of vertices) {
            xmin = Math.min(xmin, x);
            ymin = Math.min(ymin, y);
            xmax = Math.max(xmax, x);
            ymax = Math.max(ymax, y);
          }
        }
        if (xmin !== Infinity) {
          bounds = [xmin, ymin, xmax, ymax];
        }
      }
      
      setAlignmentData({
        rect4: data.rect4,
        bounds: bounds,
        alignmentParams: data
      });
    } catch (err) {
      console.error('Alignment computation error:', err);
      setError('Failed to compute alignment: ' + err.message);
    } finally {
      setComputing(false);
    }
  };

  
  useEffect(() => {
    if (!imageRef.current || !conusSelection || !containerRef.current || !imageLoaded) return;
    
    const updateZoom = () => {
      if (imageRef.current && conusSelection && containerRef.current) {
        const containerRect = containerRef.current.getBoundingClientRect();
        const containerWidth = containerRect.width || 800;
        const containerHeight = containerRect.height || 600;
        
        const padding = 10;
        const availableWidth = containerWidth - (padding * 2);
        const availableHeight = containerHeight - (padding * 2);
        
        const scale = Math.min(
          availableWidth / conusSelection.width,
          availableHeight / conusSelection.height
        );
        
        const natWidth = imageRef.current.naturalWidth;
        const natHeight = imageRef.current.naturalHeight;
        
        const imgWidth = natWidth * scale;
        const imgHeight = natHeight * scale;
        const imgLeft = padding - (conusSelection.x * scale);
        const imgTop = padding - (conusSelection.y * scale);
        
        
        imageRef.current.style.width = `${imgWidth}px`;
        imageRef.current.style.height = `${imgHeight}px`;
        imageRef.current.style.left = `${imgLeft}px`;
        imageRef.current.style.top = `${imgTop}px`;
        imageRef.current.style.position = 'absolute';
        imageRef.current.style.transform = 'none';
        imageRef.current.style.pointerEvents = 'none';
        
        setImageScale(scale);
        setImageOffset({ x: imgLeft, y: imgTop });
      }
    };
    
    
    updateZoom();
    
    
    window.addEventListener('resize', updateZoom);
    return () => window.removeEventListener('resize', updateZoom);
  }, [conusSelection, imageLoaded]);

  
  useEffect(() => {
    if (!shapefileData || !alignmentData || !alignmentData.rect4 || !alignmentData.bounds || !imageScale || !imageOffset) {
      setBoundingBox(null);
      setCornerPoints(null);
      return;
    }
    
    const computeBBox = () => {
      const features = shapefileData.geojson?.features || shapefileData.features || [];
      
      if (features.length === 0) {
        setBoundingBox(null);
        return;
      }
      
      
      let centerXPixel = 0;
      let centerYPixel = 0;
      let vertexCount = 0;
      
      for (const feature of features) {
        const pixelVertices = transformGeoJSONToPixelSpace(feature, alignmentData);
        if (!pixelVertices || pixelVertices.length === 0) continue;
        
        for (const vertex of pixelVertices) {
          centerXPixel += vertex.x;
          centerYPixel += vertex.y;
          vertexCount++;
        }
      }
      
      if (vertexCount === 0) {
        setBoundingBox(null);
        return;
      }
      
      centerXPixel /= vertexCount;
      centerYPixel /= vertexCount;
      
      
      if (!overlayAdjustments.centerX || !overlayAdjustments.centerY) {
        setOverlayAdjustments(prev => ({
          ...prev,
          centerX: centerXPixel,
          centerY: centerYPixel
        }));
      }
      
      
      const currentCenterXPixel = overlayAdjustments.centerX || centerXPixel;
      const currentCenterYPixel = overlayAdjustments.centerY || centerYPixel;
      
      
      const centerXDisplay = currentCenterXPixel * imageScale + imageOffset.x;
      const centerYDisplay = currentCenterYPixel * imageScale + imageOffset.y;
      
      const transform = {
        ...overlayAdjustments,
        centerX: centerXDisplay,
        centerY: centerYDisplay
      };
      
      
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      
      for (const feature of features) {
        const pixelVertices = transformGeoJSONToPixelSpace(feature, alignmentData);
        if (!pixelVertices || pixelVertices.length === 0) continue;
        
        for (const vertex of pixelVertices) {
          
          const displayXBase = vertex.x * imageScale + imageOffset.x;
          const displayYBase = vertex.y * imageScale + imageOffset.y;
          
          
          const transformed = applyOverlayTransform(displayXBase, displayYBase, transform);
          
          minX = Math.min(minX, transformed.x);
          minY = Math.min(minY, transformed.y);
          maxX = Math.max(maxX, transformed.x);
          maxY = Math.max(maxY, transformed.y);
        }
      }
      
      if (minX !== Infinity) {
        const bbox = {
          minX, minY, maxX, maxY,
          width: maxX - minX,
          height: maxY - minY,
          centerX: (minX + maxX) / 2,
          centerY: (minY + maxY) / 2
        };
        
        setBoundingBox(bbox);
        
        
        if (!cornerPoints || !originalCornerPoints) {
          const corners = [
            [bbox.minX, bbox.minY], 
            [bbox.maxX, bbox.minY], 
            [bbox.maxX, bbox.maxY], 
            [bbox.minX, bbox.maxY]  
          ];
          setCornerPoints(corners);
          setOriginalCornerPoints(corners.map(c => [...c]));
        } else if (!isResizeHandleDragging) {
          setCornerPoints([
            [bbox.minX, bbox.minY],
            [bbox.maxX, bbox.minY],
            [bbox.maxX, bbox.maxY],
            [bbox.minX, bbox.maxY]
          ]);
        }
      }
    };
    
    const timeoutId = setTimeout(computeBBox, 50);
    return () => clearTimeout(timeoutId);
  }, [shapefileData, alignmentData, imageScale, imageOffset, overlayAdjustments, isResizeHandleDragging]);

  
  const handleDragHandleMouseDown = (e) => {
    if (!previewOverlay) return;
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  
  const handleResizeHandleMouseDown = (e, handleType) => {
    if (!previewOverlay || !boundingBox) return;
    e.preventDefault();
    e.stopPropagation();
    setIsResizeHandleDragging(true);
    setActiveResizeHandle(handleType);
    setDragStart({ x: e.clientX, y: e.clientY });
    setResizeHandleStart({
      startBBox: { ...boundingBox },
      startTransform: { ...overlayAdjustments }
    });
  };

  
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (isDragging && dragStart) {
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        
        setOverlayAdjustments(prev => ({
          ...prev,
          translateX: prev.translateX + dx,
          translateY: prev.translateY + dy
        }));
        
        
        if (imageRef.current && imageScale && imageOffset) {
          const imgLeft = imageOffset.x;
          const imgTop = imageOffset.y;
          
          imageRef.current.style.left = `${imgLeft}px`;
          imageRef.current.style.top = `${imgTop}px`;
          imageRef.current.style.transform = 'none';
          imageRef.current.style.position = 'absolute';
          imageRef.current.style.margin = '0';
          imageRef.current.style.padding = '0';
          imageRef.current.style.transition = 'none';
          imageRef.current.style.animation = 'none';
          imageRef.current.style.willChange = 'auto';
          
          imageRef.current.setAttribute('draggable', 'false');
          
          imageRef.current.offsetHeight;
        }
        
        setDragStart({ x: e.clientX, y: e.clientY });
      } else if (isResizeHandleDragging && resizeHandleStart && activeResizeHandle && boundingBox) {
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        
        const { startBBox, startTransform } = resizeHandleStart;
        if (!startBBox || !startTransform) return;
        
        const isCorner = ['nw', 'ne', 'se', 'sw'].includes(activeResizeHandle);
        const isSide = ['n', 'e', 's', 'w'].includes(activeResizeHandle);
        
        let newScaleX = startTransform.scaleX || 1.0;
        let newScaleY = startTransform.scaleY || 1.0;
        
        const anchorCorner = {
          'nw': { x: startBBox.maxX, y: startBBox.maxY },
          'ne': { x: startBBox.minX, y: startBBox.maxY },
          'se': { x: startBBox.minX, y: startBBox.minY },
          'sw': { x: startBBox.maxX, y: startBBox.minY },
          'n': { x: startBBox.centerX, y: startBBox.maxY },
          's': { x: startBBox.centerX, y: startBBox.minY },
          'e': { x: startBBox.minX, y: startBBox.centerY },
          'w': { x: startBBox.maxX, y: startBBox.centerY }
        }[activeResizeHandle];
        
        if (!anchorCorner) return;
        
        const currentHandlePos = {
          'nw': { x: startBBox.minX + dx, y: startBBox.minY + dy },
          'ne': { x: startBBox.maxX + dx, y: startBBox.minY + dy },
          'se': { x: startBBox.maxX + dx, y: startBBox.maxY + dy },
          'sw': { x: startBBox.minX + dx, y: startBBox.maxY + dy },
          'n': { x: startBBox.centerX, y: startBBox.minY + dy },
          's': { x: startBBox.centerX, y: startBBox.maxY + dy },
          'e': { x: startBBox.maxX + dx, y: startBBox.centerY },
          'w': { x: startBBox.minX + dx, y: startBBox.centerY }
        }[activeResizeHandle];
        
        const startWidth = startBBox.width;
        const startHeight = startBBox.height;
        
        if (isCorner) {
          const newWidth = Math.abs(currentHandlePos.x - anchorCorner.x);
          const newHeight = Math.abs(currentHandlePos.y - anchorCorner.y);
          newScaleX = (newWidth / startWidth) * (startTransform.scaleX || 1.0);
          newScaleY = (newHeight / startHeight) * (startTransform.scaleY || 1.0);
        } else if (isSide) {
          if (activeResizeHandle === 'n' || activeResizeHandle === 's') {
            const newHeight = Math.abs(currentHandlePos.y - anchorCorner.y);
            newScaleY = (newHeight / startHeight) * (startTransform.scaleY || 1.0);
          } else {
            const newWidth = Math.abs(currentHandlePos.x - anchorCorner.x);
            newScaleX = (newWidth / startWidth) * (startTransform.scaleX || 1.0);
          }
        }
        
        newScaleX = Math.max(0.1, Math.min(10.0, newScaleX));
        newScaleY = Math.max(0.1, Math.min(10.0, newScaleY));
        
        setOverlayAdjustments(prev => ({
          ...prev,
          scaleX: newScaleX,
          scaleY: newScaleY
        }));
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizeHandleDragging(false);
      setActiveResizeHandle(null);
      setDragStart({ x: 0, y: 0 });
      setResizeHandleStart(null);
    };

    if (isDragging || isResizeHandleDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizeHandleDragging, dragStart, resizeHandleStart, activeResizeHandle, boundingBox]);

  

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

  const allSelected = selectedPoints.length === 4;

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
        <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Select CONUS Counties</h2>
        
        <div style={{ marginBottom: '16px' }}>
          <p style={{ margin: '0 0 8px 0', fontSize: '14px', fontWeight: '500' }}>
            Step {selectedPoints.length + 1} of 5: Click on the {selectedPoints.length < 4 ? CONUS_COUNTIES[selectedPoints.length].name.split(',')[0] : 'last'} county in the map below
          </p>
          <p style={{ margin: '0', fontSize: '12px', color: '#666' }}>
            Select counties matching the reference image (1: Clallam, 2: Aroostook, 3: Cameron, 4: Miami-Dade)
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
                src={`${import.meta.env.BASE_URL}conus_borders.png`}
                alt="CONUS Counties Reference"
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
                      <div style="font-weight: bold; margin-bottom: 8px;">Select counties in this order:</div>
                      <div>1. Clallam County, WA (northwest)</div>
                      <div>2. Aroostook County, ME (northeast)</div>
                      <div>3. Cameron County, TX (southwest)</div>
                      <div>4. Miami-Dade County, FL (southeast)</div>
                    `;
                    parent.appendChild(fallback);
                  }
                }}
              />
            </div>
          </div>

          
          <div>
            <p style={{ fontSize: '12px', color: '#666', marginBottom: '8px', fontWeight: '500' }}>
              Zoomed CONUS Region: Click on counties in order
            </p>
            <div
              ref={containerRef}
              style={{
                position: 'relative',
                display: 'block',
                border: '3px solid #10b981',
                borderRadius: '6px',
                overflow: 'hidden',
                backgroundColor: '#f0fdf4',
                cursor: selectedPoints.length < 4 ? 'crosshair' : 'default',
                width: '100%',
                aspectRatio: '16/10',
                minHeight: '400px',
                maxHeight: '600px'
              }}
              onClick={selectedPoints.length < 4 ? handleConusClick : undefined}
            >
              {!conusSelection ? (
                <div style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: '#666'
                }}>
                  Error: CONUS selection not found. Please go back and select CONUS rectangle first.
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
                    alt="CONUS Region (Zoomed)"
                    style={{
                      position: 'absolute',
                      display: imageLoaded ? 'block' : 'none',
                      top: 0,
                      left: 0,
                      userSelect: 'none',
                      pointerEvents: 'none',
                      touchAction: 'none'
                    }}
                    draggable={false}
                    onDragStart={(e) => e.preventDefault()}
                    onLoad={() => {
                      console.log('Image loaded, conusSelection:', conusSelection);
                      setImageLoaded(true);
                      
                      
                      setTimeout(() => {
                        if (imageRef.current && conusSelection && containerRef.current) {
                          const containerRect = containerRef.current.getBoundingClientRect();
                          const containerWidth = containerRect.width || 800;
                          const containerHeight = containerRect.height || 600;
                          
                          console.log('Container size:', containerWidth, containerHeight);
                          console.log('CONUS selection:', conusSelection);
                          
                          const padding = 10;
                          const availableWidth = containerWidth - (padding * 2);
                          const availableHeight = containerHeight - (padding * 2);
                          
                          
                          const scale = Math.min(
                            availableWidth / conusSelection.width,
                            availableHeight / conusSelection.height
                          );
                          
                          console.log('Calculated scale:', scale);
                          
                          
                          const natWidth = imageRef.current.naturalWidth;
                          const natHeight = imageRef.current.naturalHeight;
                          
                          const imgWidth = natWidth * scale;
                          const imgHeight = natHeight * scale;
                          const imgLeft = padding - (conusSelection.x * scale);
                          const imgTop = padding - (conusSelection.y * scale);
                          
                          console.log('Image dimensions:', imgWidth, imgHeight, 'Position:', imgLeft, imgTop);
                          
                          
                          imageRef.current.style.width = `${imgWidth}px`;
                          imageRef.current.style.height = `${imgHeight}px`;
                          imageRef.current.style.left = `${imgLeft}px`;
                          imageRef.current.style.top = `${imgTop}px`;
                          imageRef.current.style.position = 'absolute';
                          imageRef.current.style.transform = 'none';
                          imageRef.current.style.pointerEvents = 'none';
                          imageRef.current.style.margin = '0';
                          imageRef.current.style.padding = '0';
                          imageRef.current.style.transition = 'none';
                          imageRef.current.style.animation = 'none';
                          imageRef.current.style.willChange = 'auto';
                          imageRef.current.setAttribute('draggable', 'false');
                          
                          
                          setImageScale(scale);
                          setImageOffset({ x: imgLeft, y: imgTop });
                        } else {
                          console.warn('Missing refs:', {
                            imageRef: !!imageRef.current,
                            conusSelection: !!conusSelection,
                            containerRef: !!containerRef.current
                          });
                        }
                      }, 100);
                    }}
                    onError={(e) => {
                      console.error('Failed to load image:', imageUrl);
                      setImageLoaded(false);
                    }}
                  />
                  
                  {imageLoaded && selectedPoints.map((point, idx) => {
                    if (!imageRef.current || !conusSelection || !containerRef.current) return null;
                    
                    const containerRect = containerRef.current.getBoundingClientRect();
                    const padding = 10;
                    const availableWidth = containerRect.width - (padding * 2);
                    const availableHeight = containerRect.height - (padding * 2);
                    
                    const scale = Math.min(
                      availableWidth / conusSelection.width,
                      availableHeight / conusSelection.height
                    );
                    
                    
                    const displayX = padding + (point.x - conusSelection.x) * scale;
                    const displayY = padding + (point.y - conusSelection.y) * scale;
                    
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
                          backgroundColor: idx === selectedPoints.length - 1 ? '#10b981' : '#3b82f6',
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
                        title={point.countyName}
                      >
                        {idx + 1}
                      </div>
                    );
                  })}
                  
                  
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
                      Loading CONUS region...
                    </div>
                  )}
                  
                  
                  {previewOverlay && imageLoaded && imageScale && imageRef.current && (() => {
                    
                    const overlayBaseWidth = overlayRef.current?.complete && overlayRef.current?.naturalWidth 
                      ? overlayRef.current.naturalWidth 
                      : imageRef.current.naturalWidth;
                    const overlayBaseHeight = overlayRef.current?.complete && overlayRef.current?.naturalHeight 
                      ? overlayRef.current.naturalHeight 
                      : imageRef.current.naturalHeight;
                    const scaledWidth = overlayBaseWidth * imageScale * (overlayAdjustments.scaleX || 1.0);
                    const scaledHeight = overlayBaseHeight * imageScale * (overlayAdjustments.scaleY || 1.0);
                    const overlayLeft = imageOffset.x + (overlayAdjustments.translateX || 0);
                    const overlayTop = imageOffset.y + (overlayAdjustments.translateY || 0);
                    
                    
                    const overlayCenterX = overlayLeft + scaledWidth / 2;
                    const overlayCenterY = overlayTop + scaledHeight / 2;
                    
                    const centerXPixel = overlayAdjustments.centerX || 0;
                    const centerYPixel = overlayAdjustments.centerY || 0;
                    const centerXDisplay = centerXPixel * imageScale + imageOffset.x;
                    const centerYDisplay = centerYPixel * imageScale + imageOffset.y;
                    const transformOriginX = centerXDisplay - overlayLeft;
                    const transformOriginY = centerYDisplay - overlayTop;
                    
                    return (
                      <>
                        <img
                          ref={overlayRef}
                          src={previewOverlay + '?t=' + Date.now()}
                          alt="Aligned overlay"
                          style={{
                            position: 'absolute',
                            top: `${overlayTop}px`,
                            left: `${overlayLeft}px`,
                            width: `${scaledWidth}px`,
                            height: `${scaledHeight}px`,
                            pointerEvents: 'none',
                            zIndex: 4,
                            transformOrigin: `${transformOriginX}px ${transformOriginY}px`,
                            opacity: 1,
                            mixBlendMode: 'normal'
                          }}
                          onError={(e) => {
                            console.error('Failed to load overlay image:', previewOverlay);
                          }}
                        />
                        
                        
                        <div
                          ref={dragHandleRef}
                          style={{
                            position: 'absolute',
                            left: `${overlayCenterX}px`,
                            top: `${overlayCenterY}px`,
                            width: '50px',
                            height: '50px',
                            borderRadius: '50%',
                            backgroundColor: 'white',
                            border: '2px solid #3b82f6',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            cursor: 'move',
                            zIndex: 20,
                            transform: 'translate(-50%, -50%)',
                            pointerEvents: 'auto',
                            userSelect: 'none',
                            boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
                          }}
                          onMouseDown={handleDragHandleMouseDown}
                        >
                          <span style={{ fontSize: '10px', color: '#3b82f6', fontWeight: '700', letterSpacing: '0.5px' }}>DRAG</span>
                        </div>
                        
                        
                        {boundingBox && cornerPoints && (
                          <>
                            
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
                                points={`${cornerPoints[0][0]},${cornerPoints[0][1]} ${cornerPoints[1][0]},${cornerPoints[1][1]} ${cornerPoints[2][0]},${cornerPoints[2][1]} ${cornerPoints[3][0]},${cornerPoints[3][1]}`}
                                fill="none"
                                stroke="#3b82f6"
                                strokeWidth="3"
                                strokeDasharray="8,4"
                              />
                            </svg>
                            
                            
                            {['nw', 'ne', 'se', 'sw'].map((handleType, idx) => (
                              <div
                                key={handleType}
                                style={{
                                  position: 'absolute',
                                  left: `${cornerPoints[idx][0]}px`,
                                  top: `${cornerPoints[idx][1]}px`,
                                  width: '16px',
                                  height: '16px',
                                  backgroundColor: '#3b82f6',
                                  border: '4px solid white',
                                  borderRadius: '50%',
                                  cursor: 'move',
                                  zIndex: 30,
                                  transform: 'translate(-50%, -50%)',
                                  pointerEvents: 'auto',
                                  boxShadow: '0 3px 10px rgba(0,0,0,0.6)',
                                  transition: 'none'
                                }}
                                onMouseDown={(e) => handleResizeHandleMouseDown(e, handleType)}
                              />
                            ))}
                            
                            
                            {[
                              { type: 'n', x: boundingBox.centerX, y: boundingBox.minY },
                              { type: 'e', x: boundingBox.maxX, y: boundingBox.centerY },
                              { type: 's', x: boundingBox.centerX, y: boundingBox.maxY },
                              { type: 'w', x: boundingBox.minX, y: boundingBox.centerY }
                            ].map(({ type, x, y }) => (
                              <div
                                key={type}
                                style={{
                                  position: 'absolute',
                                  left: `${x}px`,
                                  top: `${y}px`,
                                  width: '16px',
                                  height: '16px',
                                  backgroundColor: '#3b82f6',
                                  border: '4px solid white',
                                  borderRadius: '50%',
                                  cursor: type === 'n' || type === 's' ? 'ns-resize' : 'ew-resize',
                                  zIndex: 30,
                                  transform: 'translate(-50%, -50%)',
                                  pointerEvents: 'auto',
                                  boxShadow: '0 3px 10px rgba(0,0,0,0.6)',
                                  transition: 'none'
                                }}
                                onMouseDown={(e) => handleResizeHandleMouseDown(e, type)}
                              />
                            ))}
                          </>
                        )}
                      </>
                    );
                  })()}
                </>
              )}
            </div>
          </div>
        </div>

        
        {computing && (
          <div style={{
            backgroundColor: '#fef3c7',
            border: '2px solid #f59e0b',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '16px',
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
            marginBottom: '16px',
            textAlign: 'center'
          }}>
            <p style={{ margin: 0, fontSize: '14px', color: '#065f46', fontWeight: '600' }}>
              ✓ Alignment computed! Review the overlay preview. If it looks good, click "Confirm Alignment".
            </p>
          </div>
        )}

        {error && (
          <div style={{
            backgroundColor: '#fef2f2',
            border: '1px solid #ef4444',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px',
            color: '#dc2626',
            fontSize: '14px',
            textAlign: 'center'
          }}>
            Error: {error}
          </div>
        )}

        
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          flexWrap: 'wrap',
          justifyContent: 'center'
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
              onClick={() => onConfirm({
                ...alignmentData,
                overlayAdjustments: overlayAdjustments
              })}
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
        </div>
      </div>
    </div>
  );
}
