import React, { useState, useEffect, useRef } from "react";
import MapView from "../components/MapView";
import ImageSelector from "../components/ImageSelector";
import RegionSelector from "../components/RegionSelector";
import { uploadImage, fetchGeoJSON, downloadFile, detectBounds, setBoundsManually, regenerateOverlay, generateOverlayPreview } from "../api";

export default function Upload({ onNavigateToHome }) {
  const [geojson, setGeojson] = useState(null);
  const [message, setMessage] = useState("");
  const [layer, setLayer] = useState("uploaded");
  const [nClusters, setNClusters] = useState(6);
  const [projection, setProjection] = useState("4326"); // Default to EPSG:4326
  const [uploadedImageUrl, setUploadedImageUrl] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showImageSelector, setShowImageSelector] = useState(false);
  const [showRegionSelector, setShowRegionSelector] = useState(false);
  const [legendSelection, setLegendSelection] = useState(null);
  const [regionSelections, setRegionSelections] = useState(null); // { conus: {...}, alaska: {...}, hawaii: {...} }
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadId, setUploadId] = useState(null);
  const [overlayUrl, setOverlayUrl] = useState(null);
  const [previewOverlayUrl, setPreviewOverlayUrl] = useState(null);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
  const [autoBounds, setAutoBounds] = useState(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [showManualBounds, setShowManualBounds] = useState(false);
  const [manualBoundsJson, setManualBoundsJson] = useState("");
  const imageDisplayRef = useRef(null);

  // Cleanup image URL on component unmount
  useEffect(() => {
    return () => {
      if (uploadedImageUrl) {
        URL.revokeObjectURL(uploadedImageUrl);
      }
    };
  }, [uploadedImageUrl]);

  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Cleanup previous image URL if exists
    if (uploadedImageUrl) {
      URL.revokeObjectURL(uploadedImageUrl);
    }

    setUploadedFile(file);
    setGeojson(null);
    setLegendSelection(null);
    setRegionSelections(null);
    setUploadId(null);
    setOverlayUrl(null);
    setAutoBounds(null);
    setMessage("Running edge detection to find the map panel...");
    setIsDetecting(true);

    // Create image URL for display
    const imageUrl = URL.createObjectURL(file);
    setUploadedImageUrl(imageUrl);

    // Scroll to image display section
    setTimeout(() => {
      if (imageDisplayRef.current) {
        imageDisplayRef.current.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }
    }, 100);

    try {
      const resp = await detectBounds(file);
      const data = resp.data || {};
      const detectedId = data.uploadId || null;
      setUploadId(detectedId);
      setAutoBounds(data.bounds || null);
      setOverlayUrl(null);  // Don't show overlay - user wants processed result instead
      setMessage("Bounds detected. Please select the legend area, then click 'Process Image'.");
    } catch (err) {
      console.error(err);
      setUploadId(null);
      setOverlayUrl(null);
      setAutoBounds(null);
      setMessage(
        "Bounds detection failed: " + (err.response?.data?.error || err.message)
      );
    } finally {
      setIsDetecting(false);
    }
  };

  const handleLegendSelection = (selection) => {
    setLegendSelection(selection);
    setShowImageSelector(false);
    setMessage("Legend area selected. Now mark the CONUS region (required) and optionally Alaska/Hawaii if present.");
    // Show region selector after legend selection
    setShowRegionSelector(true);
  };

  const handleRegionSelection = (regions) => {
    setRegionSelections(regions);
    setShowRegionSelector(false);
    const hasOptionalRegions = regions.alaska || regions.hawaii;
    setMessage(hasOptionalRegions 
      ? "CONUS and optional regions marked. Click 'Preview Overlay' to check alignment, then 'Process Image' to continue."
      : "CONUS marked. Click 'Preview Overlay' to check alignment, then 'Process Image' to continue.");
  };
  
  const handleGeneratePreview = async () => {
    if (!uploadId || !legendSelection) {
      setMessage("Please select legend area first.");
      return;
    }
    
    setIsGeneratingPreview(true);
    setMessage("Generating overlay preview...");
    
    try {
      const resp = await generateOverlayPreview(uploadId, projection, regionSelections);
      console.log("Overlay preview response:", resp.data);
      if (resp.data?.overlayUrl) {
        const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";
        const fullUrl = `${API_ROOT}${resp.data.overlayUrl}`;
        console.log("Setting overlay URL:", fullUrl);
        setPreviewOverlayUrl(fullUrl);
        setMessage("Overlay preview generated! Check the preview below.");
      } else {
        setMessage("Preview generation failed: " + (resp.data?.error || "Unknown error"));
        console.error("No overlayUrl in response:", resp.data);
      }
    } catch (err) {
      console.error("Preview generation error:", err);
      setMessage("Preview generation error: " + (err.response?.data?.error || err.message));
    } finally {
      setIsGeneratingPreview(false);
    }
  };

  const handleSkipRegions = () => {
    setRegionSelections({ alaska: null, hawaii: null });
    setShowRegionSelector(false);
    setMessage("Legend area selected. Click 'Preview Overlay' to check alignment, then 'Process Image' to continue.");
  };

  const handleProcessImage = async () => {
    if (!uploadedFile || !legendSelection) {
      setMessage("Please select a file and legend area first.");
      return;
    }
    if (!uploadId) {
      setMessage("Bounds not ready yet. Wait for edge detection to finish.");
      return;
    }
    if (isDetecting) {
      setMessage("Bounds detection still running. Please wait before processing.");
      return;
    }

    setIsLoading(true);
    setMessage("Processing image with legend...");

    try {
      const resp = await uploadImage(
        uploadedFile,
        layer,
        nClusters,
        legendSelection,
        uploadId,
        regionSelections,
        projection
      );
      if (resp.data?.error) {
        setMessage("Processing error: " + resp.data.error);
        setIsLoading(false);
        return;
      }
      if (resp.data?.uploadId) {
        setUploadId(resp.data.uploadId);
      }
      setMessage("Processing complete, loading layer...");
      const geo = await fetchGeoJSON(layer);
      setGeojson(geo.data);
      setMessage("Layer loaded.");
    } catch (err) {
      console.error(err);
      setMessage(
        "Processing failed: " + (err.response?.data?.error || err.message)
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleManualBoundsSubmit = async () => {
    if (!uploadId) {
      setMessage("Please upload a file first.");
      return;
    }
    if (!manualBoundsJson.trim()) {
      setMessage("Please paste the bounds JSON from ChatGPT.");
      return;
    }

    try {
      const boundsData = JSON.parse(manualBoundsJson);
      const resp = await setBoundsManually(uploadId, boundsData);
      setMessage("Manual bounds saved successfully! Now select the legend area and click 'Process Image'.");
      setAutoBounds(boundsData);
      setShowManualBounds(false);
      setManualBoundsJson("");
    } catch (err) {
      setMessage("Invalid JSON: " + (err.response?.data?.error || err.message));
    }
  };

  const handleCancel = () => {
    if (uploadedImageUrl) {
      URL.revokeObjectURL(uploadedImageUrl);
    }
    setUploadedImageUrl(null);
    setUploadedFile(null);
    setGeojson(null);
    setLegendSelection(null);
    setRegionSelections(null);
    setUploadId(null);
    setOverlayUrl(null);
    setAutoBounds(null);
    setShowImageSelector(false);
    setShowRegionSelector(false);
    setIsLoading(false);
    setIsDetecting(false);
    setShowManualBounds(false);
    setManualBoundsJson("");
    setMessage("");

    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.value = "";
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        fontFamily:
          "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        backgroundColor: "#fafafa",
        color: "#333",
      }}
    >
      {/* Upload Form Section */}
      <section
        style={{
          padding: "60px 0",
          textAlign: "center",
          maxWidth: "1200px",
          margin: "0 auto",
          paddingLeft: "24px",
          paddingRight: "24px",
        }}
      >
        <div
          style={{
            backgroundColor: "white",
            padding: "40px",
            borderRadius: "8px",
            border: "1px solid #e5e5e5",
            maxWidth: "600px",
            margin: "0 auto",
          }}
        >
          <h2
            style={{
              fontSize: "24px",
              fontWeight: "600",
              margin: "0 0 16px 0",
              color: "#333",
            }}
          >
            Upload your files
          </h2>
          <p
            style={{
              fontSize: "16px",
              color: "#666",
              margin: "0 0 24px 0",
              lineHeight: "1.5",
            }}
          >
            We'll extract county-level values from your choropleth.
          </p>


          {/* Projection Selection */}
          <div style={{ marginBottom: "24px", textAlign: "left" }}>
            <label
              style={{
                display: "block",
                fontSize: "16px",
                fontWeight: "600",
                marginBottom: "12px",
                color: "#333",
              }}
            >
              Projection (CRS)
            </label>
            <div style={{ display: "flex", gap: "16px", marginBottom: "8px" }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  cursor: "pointer",
                }}
              >
                <input
                  type="radio"
                  name="projection"
                  value="4326"
                  checked={projection === "4326"}
                  onChange={(e) => setProjection(e.target.value)}
                  style={{ margin: "0" }}
                />
                <span style={{ fontSize: "14px", color: "#666" }}>
                  EPSG:4326 (WGS84)
                </span>
              </label>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  cursor: "pointer",
                }}
              >
                <input
                  type="radio"
                  name="projection"
                  value="5070"
                  checked={projection === "5070"}
                  onChange={(e) => setProjection(e.target.value)}
                  style={{ margin: "0" }}
                />
                <span style={{ fontSize: "14px", color: "#666" }}>
                  EPSG:5070 (NAD83 / Conus Albers)
                </span>
              </label>
            </div>
            <p
              style={{
                fontSize: "12px",
                color: "#999",
                margin: "0",
                lineHeight: "1.4",
              }}
            >
              Select the projection that matches your map image. EPSG:4326 (WGS84) is common for web maps, 
              while EPSG:5070 (CONUS Albers) is typical for printed US maps.
            </p>
          </div>

          {/* File Upload */}
          <div style={{ marginBottom: "24px", textAlign: "left" }}>
            <label
              style={{
                display: "block",
                fontSize: "16px",
                fontWeight: "600",
                marginBottom: "12px",
                color: "#333",
              }}
            >
              Choropleth image (PNG/JPG)
            </label>
            <input
              type="file"
              accept="image/*"
              onChange={handleFileSelect}
              style={{
                width: "100%",
                padding: "12px",
                border: "1px solid #ddd",
                borderRadius: "6px",
                fontSize: "14px",
                backgroundColor: "white",
              }}
            />
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", gap: "16px", justifyContent: "center", flexWrap: "wrap" }}>
            <button
              onClick={() =>
                document.querySelector('input[type="file"]')?.click()
              }
              style={{
                backgroundColor: "#333",
                color: "white",
                border: "none",
                padding: "12px 24px",
                borderRadius: "6px",
                fontSize: "16px",
                fontWeight: "500",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              Select File
            </button>
            
            {uploadedFile && (
              <button
                onClick={() => {
                  if (isDetecting || !uploadId) {
                    setMessage("Wait for bounds detection before selecting the legend area.");
                    return;
                  }
                  setShowImageSelector(true);
                }}
                disabled={isDetecting || !uploadId}
                style={{
                  backgroundColor:
                    isDetecting || !uploadId ? "#94a3b8" : "#007bff",
                  color: "white",
                  border: "none",
                  padding: "12px 24px",
                  borderRadius: "6px",
                  fontSize: "16px",
                  fontWeight: "500",
                  cursor: isDetecting || !uploadId ? "not-allowed" : "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                Select Legend Area
              </button>
            )}
            
            {uploadedFile && legendSelection && (
              <button
                onClick={handleGeneratePreview}
                disabled={isGeneratingPreview || !uploadId}
                style={{
                  backgroundColor: isGeneratingPreview || !uploadId ? "#94a3b8" : "#28a745",
                  color: "white",
                  border: "none",
                  padding: "12px 24px",
                  borderRadius: "6px",
                  fontSize: "16px",
                  fontWeight: "500",
                  cursor: isGeneratingPreview || !uploadId ? "not-allowed" : "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                {isGeneratingPreview ? "Generating..." : "Preview Overlay"}
              </button>
            )}
            
            {uploadedFile && legendSelection && (
              <button
                onClick={handleProcessImage}
                disabled={isLoading || isDetecting || !uploadId}
                style={{
                  backgroundColor:
                    isLoading || isDetecting || !uploadId ? "#ccc" : "#28a745",
                  color: "white",
                  border: "none",
                  padding: "12px 24px",
                  borderRadius: "6px",
                  fontSize: "16px",
                  fontWeight: "500",
                  cursor:
                    isLoading || isDetecting || !uploadId ? "not-allowed" : "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                {isLoading
                  ? "Processing..."
                  : isDetecting
                  ? "Detecting Bounds..."
                  : !uploadId
                  ? "Awaiting Bounds"
                  : "Process Image"}
              </button>
            )}
            
            <button
              onClick={handleCancel}
              style={{
                backgroundColor: "#f5f5f5",
                color: "#333",
                border: "1px solid #ddd",
                padding: "12px 24px",
                borderRadius: "6px",
                fontSize: "16px",
                fontWeight: "500",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              Cancel
            </button>
          </div>

          {/* Status Message */}
          {message && (
            <div
              style={{
                marginTop: "24px",
                padding: "16px",
                backgroundColor:
                  message.includes("error") || message.includes("failed")
                    ? "#fef2f2"
                    : "#f0f9ff",
                color:
                  message.includes("error") || message.includes("failed")
                    ? "#dc2626"
                    : "#0369a1",
                borderRadius: "6px",
                fontSize: "14px",
                textAlign: "left",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "8px",
                }}
              >
                <span style={{ fontSize: "16px" }}>
                  {isLoading
                    ? "⏳"
                    : message.includes("error") || message.includes("failed")
                    ? "❌"
                    : "ℹ️"}
                </span>
                <strong>Status</strong>
              </div>
              <div>{message}</div>
            </div>
          )}

          {/* Bounds info (compact, hidden after processing) */}
          {autoBounds && autoBounds.canvases && autoBounds.canvases.length > 0 && !geojson && (
            <div
              style={{
                marginTop: "16px",
                padding: "12px",
                backgroundColor: "#f8fafc",
                borderRadius: "6px",
                fontSize: "12px",
                textAlign: "left",
                border: "1px solid #e2e8f0",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <strong style={{ color: "#475569" }}>Map Bounds Detected</strong>
                <button
                  onClick={() => setShowManualBounds(!showManualBounds)}
                  style={{
                    backgroundColor: "#3b82f6",
                    color: "white",
                    border: "none",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    cursor: "pointer",
                  }}
                >
                  {showManualBounds ? "Hide" : "Override"}
                </button>
              </div>
              <div style={{ color: "#64748b", fontSize: "11px" }}>
                Upload ID: {uploadId || "(not set)"} • BBox: [{autoBounds.canvases[0].bbox.join(", ")}]
              </div>
            </div>
          )}

          {uploadId && showManualBounds && (
            <div
              style={{
                marginTop: "16px",
                padding: "16px",
                backgroundColor: "#fef3c7",
                borderRadius: "6px",
                fontSize: "14px",
                textAlign: "left",
                border: "1px solid #fbbf24",
              }}
            >
              <strong style={{ display: "block", marginBottom: "8px", color: "#92400e" }}>
                Manual Bounds (from ChatGPT)
              </strong>
              <p style={{ fontSize: "12px", color: "#78350f", margin: "0 0 8px 0" }}>
                Paste the bounds JSON you got from ChatGPT here:
              </p>
              <textarea
                value={manualBoundsJson}
                onChange={(e) => setManualBoundsJson(e.target.value)}
                placeholder='{"type":"map_canvas_bounds","image_size":{"width":864,"height":527},"canvases":[{"name":"CONUS","bbox":[41,23,825,504],"polygon":null,"confidence":0.82}]}'
                style={{
                  width: "100%",
                  minHeight: "120px",
                  padding: "8px",
                  border: "1px solid #d1d5db",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontFamily: "monospace",
                  marginBottom: "8px",
                  boxSizing: "border-box",
                }}
              />
              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  onClick={handleManualBoundsSubmit}
                  style={{
                    backgroundColor: "#10b981",
                    color: "white",
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "4px",
                    fontSize: "14px",
                    cursor: "pointer",
                    fontWeight: "500",
                  }}
                >
                  Save Manual Bounds
                </button>
                <button
                  onClick={() => {
                    setShowManualBounds(false);
                    setManualBoundsJson("");
                  }}
                  style={{
                    backgroundColor: "#6b7280",
                    color: "white",
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "4px",
                    fontSize: "14px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Download Button */}
          {geojson && (
            <div style={{ marginTop: "24px" }}>
              <a
                href={downloadFile(`${layer}.csv`)}
                style={{
                  display: "inline-block",
                  backgroundColor: "#10b981",
                  color: "white",
                  textDecoration: "none",
                  padding: "12px 24px",
                  borderRadius: "6px",
                  fontSize: "16px",
                  fontWeight: "500",
                  transition: "all 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  e.target.style.backgroundColor = "#059669";
                }}
                onMouseLeave={(e) => {
                  e.target.style.backgroundColor = "#10b981";
                }}
              >
                📥 Download CSV Data
              </a>
            </div>
          )}
        </div>
      </section>

      {/* Overlay Preview Section */}
      {previewOverlayUrl && (
        <section
          style={{
            padding: "40px 0",
            maxWidth: "1200px",
            margin: "0 auto",
            paddingLeft: "24px",
            paddingRight: "24px",
          }}
        >
          <h3
            style={{
              fontSize: "28px",
              fontWeight: "700",
              margin: "0 0 24px 0",
              textAlign: "center",
              color: "#333",
            }}
          >
            Shapefile Overlay Preview
          </h3>
          <p
            style={{
              fontSize: "14px",
              color: "#666",
              textAlign: "center",
              marginBottom: "24px",
            }}
          >
            Red lines = CONUS, Green = Alaska, Blue = Hawaii
          </p>
          <div
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              border: "1px solid #e5e5e5",
              padding: "20px",
              boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
              textAlign: "center",
            }}
          >
            <img
              src={previewOverlayUrl}
              alt="Shapefile Overlay Preview"
              style={{
                width: "auto",
                height: "auto",
                maxWidth: "100%",
                borderRadius: "4px",
                imageRendering: "pixelated", // Prevent CSS scaling interpolation
              }}
              onError={(e) => {
                console.error("Failed to load overlay image:", previewOverlayUrl);
                e.target.alt = "Failed to load overlay. Check console for errors.";
              }}
            />
          </div>
        </section>
      )}

      {/* Image Display Section */}
      {(uploadedImageUrl || geojson) && (
        <section
          ref={imageDisplayRef}
          style={{
            padding: "60px 0",
            maxWidth: "1200px",
            margin: "0 auto",
            paddingLeft: "24px",
            paddingRight: "24px",
          }}
        >
          <h3
            style={{
              fontSize: "32px",
              fontWeight: "700",
              margin: "0 0 40px 0",
              textAlign: "center",
              color: "#333",
            }}
          >
            {geojson ? "Processed Choropleth Map" : "Original Image"}
          </h3>
          <div
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              border: "1px solid #e5e5e5",
              overflow: "hidden",
              height: "600px",
              position: "relative",
            }}
          >
            {geojson ? (
              <MapView
                geojson={geojson}
                uploadedImageUrl={uploadedImageUrl}
                isLoading={isLoading}
              />
            ) : (
              <div
                style={{
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  position: "relative",
                  padding: "16px",
                  boxSizing: "border-box",
                }}
              >
                {uploadedImageUrl && !geojson && (
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <figure
                      style={{
                        margin: 0,
                        width: "100%",
                        height: "100%",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        backgroundColor: "#f8fafc",
                        borderRadius: "6px",
                        padding: "12px",
                      }}
                    >
                      <img
                        src={uploadedImageUrl}
                        alt="Uploaded choropleth map"
                        style={{
                          maxWidth: "100%",
                          maxHeight: "100%",
                          objectFit: "contain",
                          borderRadius: "4px",
                        }}
                      />
                      <figcaption style={{ marginTop: "8px", color: "#64748b" }}>
                        Original Image
                      </figcaption>
                    </figure>
                  </div>
                )}
                {(isLoading || isDetecting) && (
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      backgroundColor: "rgba(255, 255, 255, 0.9)",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      zIndex: 10,
                    }}
                  >
                    <div
                      style={{
                        width: "50px",
                        height: "50px",
                        border: "4px solid #f3f3f3",
                        borderTop: "4px solid #333",
                        borderRadius: "50%",
                        animation: "spin 1s linear infinite",
                        marginBottom: "20px",
                      }}
                    ></div>
                    <p
                      style={{
                        fontSize: "18px",
                        fontWeight: "500",
                        color: "#333",
                        margin: "0",
                        textAlign: "center",
                      }}
                    >
                      {isLoading
                        ? "Processing your image..."
                        : "Detecting map bounds..."}
                    </p>
                    <p
                      style={{
                        fontSize: "14px",
                        color: "#666",
                        margin: "8px 0 0 0",
                        textAlign: "center",
                      }}
                    >
                      {isLoading
                        ? "This may take a few moments"
                        : "Sit tight while we outline the map panel"}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}
      
      {/* Image Selector Modal */}
      {showImageSelector && uploadedImageUrl && (
        <ImageSelector
          imageUrl={uploadedImageUrl}
          onSelectionComplete={handleLegendSelection}
          onCancel={() => setShowImageSelector(false)}
        />
      )}

      {/* Region Selector Modal */}
      {showRegionSelector && uploadedImageUrl && (
        <RegionSelector
          imageUrl={uploadedImageUrl}
          uploadId={uploadId}
          projection={projection}
          onSelectionComplete={handleRegionSelection}
          onSkip={handleSkipRegions}
          onCancel={handleSkipRegions}
        />
      )}
    </div>
  );
}
