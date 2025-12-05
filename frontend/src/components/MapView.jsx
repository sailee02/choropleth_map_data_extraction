import React, { useEffect, useState } from "react";
import { MapContainer, GeoJSON, useMap } from "react-leaflet";

function FitBounds({ geojson }) {
  const map = useMap();
  useEffect(() => {
    if (geojson && geojson.features && geojson.features.length > 0) {
      const layer = new L.GeoJSON(geojson);
      map.fitBounds(layer.getBounds(), {
        padding: [50, 50],
        animate: true,
        duration: 1.0,
        maxZoom: 5
      });
    }
  }, [geojson, map]);
  return null;
}

function CustomZoomControl() {
  const map = useMap();
  
  const zoomIn = () => {
    const currentZoom = map.getZoom();
    if (currentZoom < 6) {
      map.setZoom(currentZoom + 0.01);
    }
  };
  
  const zoomOut = () => {
    const currentZoom = map.getZoom();
    if (currentZoom > 2) {
      map.setZoom(currentZoom - 0.01);
    }
  };
  
  return (
    <div style={{
      position: 'absolute',
      top: '10px',
      right: '10px',
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      gap: '5px'
    }}>
      <button
        onClick={zoomIn}
        style={{
          width: '40px',
          height: '40px',
          backgroundColor: 'white',
          border: '2px solid #ccc',
          borderRadius: '4px',
          fontSize: '18px',
          fontWeight: 'bold',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
        }}
        onMouseEnter={(e) => {
          e.target.style.backgroundColor = '#f0f0f0';
        }}
        onMouseLeave={(e) => {
          e.target.style.backgroundColor = 'white';
        }}
      >
        +
      </button>
      <button
        onClick={zoomOut}
        style={{
          width: '40px',
          height: '40px',
          backgroundColor: 'white',
          border: '2px solid #ccc',
          borderRadius: '4px',
          fontSize: '18px',
          fontWeight: 'bold',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
        }}
        onMouseEnter={(e) => {
          e.target.style.backgroundColor = '#f0f0f0';
        }}
        onMouseLeave={(e) => {
          e.target.style.backgroundColor = 'white';
        }}
      >
        −
      </button>
    </div>
  );
}

export default function MapView({ geojson, uploadedImageUrl, isLoading }) {

  const style = (feature) => {
    const rgb = feature.properties.rgb;
    if (rgb && rgb.length === 3) {
      return {
        fillColor: `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`,
        color: "#333",
        weight: 0.5,
        fillOpacity: 0.8,
      };
    }
    return {
      fillColor: "#ccc",
      color: "#333",
      weight: 0.5,
      fillOpacity: 0.8,
    };
  };

  const onEachFeature = (feature, layer) => {
    const props = feature.properties || {};
    const countyName = props.name || props.GEOID;
    const stateName = props.state_name || "";
    const stateAbbr = props.state_abbr || props.STUSPS || "";
    
    // Format: "County Name, State Abbreviation" on first line, value on second line
    let tooltipContent = "";
    
    // Use state abbreviation if available, otherwise use full state name
    const stateDisplay = stateAbbr || stateName;
    if (stateDisplay) {
      tooltipContent = `${countyName}, ${stateDisplay}`;
    } else {
      tooltipContent = countyName;
    }
    
    // Add value on second line (just the value, no "Value:" prefix)
    if (props.value !== null && props.value !== undefined) {
      // Format value to 2 decimal places
      const valueStr = typeof props.value === 'number' ? props.value.toFixed(2) : props.value;
      tooltipContent += `<br/>${valueStr}`;
    }
    
    layer.bindTooltip(tooltipContent, {
      permanent: false,
      direction: 'top',
      className: 'custom-tooltip'
    });
  };


  return (
    <div className="map-wrapper" style={{ 
      position: 'relative', 
      width: '100%', 
      height: '100%',
      borderRadius: '10px',
      overflow: 'hidden',
      boxShadow: '0 4px 20px rgba(0,0,0,0.1)'
    }}>
      <MapContainer 
        className="map-container" 
        zoom={4} 
        center={[37.8, -96]} 
        scrollWheelZoom={true}
        zoomAnimation={true}
        fadeAnimation={true}
        markerZoomAnimation={true}
        minZoom={2}
        maxZoom={6}
        zoomDelta={0.3}
        wheelPxPerZoomLevel={200}
        zoomControl={false}
        style={{ 
          height: '100%', 
          width: '100%',
          borderRadius: '10px'
        }}
      >
        {/* Remove TileLayer so the world map background disappears */}
        {geojson && <GeoJSON data={geojson} style={style} onEachFeature={onEachFeature} />}
        {geojson && <FitBounds geojson={geojson} />}
        <CustomZoomControl />
      </MapContainer>
      
      {/* Show uploaded image overlay when loading and no geojson available */}
      {isLoading && uploadedImageUrl && !geojson && (
        <div 
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            zIndex: 1000,
            borderRadius: '10px'
          }}
        >
          <div style={{ 
            textAlign: 'center',
            padding: '20px',
            backgroundColor: 'white',
            borderRadius: '15px',
            boxShadow: '0 10px 30px rgba(0,0,0,0.2)',
            maxWidth: '90%',
            maxHeight: '90%'
          }}>
            <div style={{
              fontSize: '48px',
              marginBottom: '15px',
              animation: 'pulse 2s infinite'
            }}>
              ⏳
            </div>
            <img 
              src={uploadedImageUrl} 
              alt="Processing uploaded image..." 
              style={{ 
                maxWidth: '100%', 
                maxHeight: '60vh', 
                objectFit: 'contain',
                border: '3px solid #667eea',
                borderRadius: '10px',
                boxShadow: '0 4px 15px rgba(0,0,0,0.1)'
              }} 
            />
            <p style={{ 
              marginTop: '15px', 
              fontSize: '18px', 
              fontWeight: '600',
              color: '#495057',
              marginBottom: '5px'
            }}>
              Processing your image...
            </p>
            <p style={{
              fontSize: '14px',
              color: '#6c757d',
              margin: '0'
            }}>
              Analyzing county data and generating choropleth map
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
