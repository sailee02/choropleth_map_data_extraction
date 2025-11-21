import React from "react";

export default function Home({ onNavigateToUpload }) {
  return (
    <div style={{
      minHeight: "100vh",
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      backgroundColor: "#fafafa",
      color: "#333"
    }}>
      {/* Hero Section */}
      <section style={{
        padding: "120px 0 80px",
        textAlign: "center",
        maxWidth: "1200px",
        margin: "0 auto",
        paddingLeft: "24px",
        paddingRight: "24px"
      }}>
        <div style={{
          fontSize: "12px",
          color: "#666",
          textTransform: "uppercase",
          letterSpacing: "1px",
          marginBottom: "16px"
        }}>
          CHOROPLETH MAP EXTRACTOR
        </div>
        <h1 style={{
          fontSize: "48px",
          fontWeight: "700",
          margin: "0 0 24px 0",
          lineHeight: "1.1",
          color: "#333"
        }}>
          Turn static choropleth images into{" "}
          <span style={{ color: "#666" }}>usable data</span>
        </h1>
        <p style={{
          fontSize: "18px",
          color: "#666",
          margin: "0 0 32px 0",
          maxWidth: "600px",
          marginLeft: "auto",
          marginRight: "auto",
          lineHeight: "1.5"
        }}>
          Upload your map image. We'll align with the shapefile, create the legend and return county-level values.
        </p>
        <div style={{ display: "flex", gap: "16px", justifyContent: "center" }}>
          <button
            onClick={onNavigateToUpload}
            style={{
              backgroundColor: "#333",
              color: "white",
              border: "none",
              padding: "12px 24px",
              borderRadius: "6px",
              fontSize: "16px",
              fontWeight: "500",
              cursor: "pointer",
              transition: "all 0.2s ease"
            }}
            onMouseEnter={(e) => {
              e.target.style.backgroundColor = "#555";
            }}
            onMouseLeave={(e) => {
              e.target.style.backgroundColor = "#333";
            }}
          >
            Get started
          </button>
          <button style={{
            backgroundColor: "white",
            color: "#333",
            border: "1px solid #ddd",
            padding: "12px 24px",
            borderRadius: "6px",
            fontSize: "16px",
            fontWeight: "500",
            cursor: "pointer",
            transition: "all 0.2s ease"
          }}>
            Read the guide
          </button>
        </div>
      </section>

      {/* What to upload section */}
      <section style={{
        padding: "60px 0",
        maxWidth: "1200px",
        margin: "0 auto",
        paddingLeft: "24px",
        paddingRight: "24px"
      }}>
        <h2 style={{
          fontSize: "32px",
          fontWeight: "700",
          margin: "0 0 40px 0",
          textAlign: "center",
          color: "#333"
        }}>
          What to upload
        </h2>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          gap: "24px"
        }}>
          {/* Projection Card */}
          <div style={{
            backgroundColor: "white",
            padding: "32px",
            borderRadius: "8px",
            border: "1px solid #e5e5e5",
            transition: "all 0.2s ease"
          }}
          onMouseEnter={(e) => {
            e.target.style.transform = "translateY(-2px)";
            e.target.style.boxShadow = "0 8px 25px rgba(0,0,0,0.1)";
          }}
          onMouseLeave={(e) => {
            e.target.style.transform = "translateY(0)";
            e.target.style.boxShadow = "none";
          }}
          >
            <h3 style={{
              fontSize: "20px",
              fontWeight: "600",
              margin: "0 0 16px 0",
              color: "#333"
            }}>
              Projection
            </h3>
            <p style={{
              fontSize: "16px",
              color: "#666",
              margin: "0 0 12px 0",
              lineHeight: "1.5"
            }}>
              We support EPSG:4326 (WGS84) and EPSG:5070 (NAD83).
            </p>
            <a href="#" style={{
              color: "#0066cc",
              textDecoration: "none",
              fontSize: "14px",
              display: "block",
              marginBottom: "8px"
            }}>
              Check your map's projection.
            </a>
            <p style={{
              fontSize: "14px",
              color: "#666",
              margin: "0",
              lineHeight: "1.4"
            }}>
              Please reproject if needed before upload.
            </p>
          </div>

          {/* Map image Card */}
          <div style={{
            backgroundColor: "white",
            padding: "32px",
            borderRadius: "8px",
            border: "1px solid #e5e5e5",
            transition: "all 0.2s ease"
          }}
          onMouseEnter={(e) => {
            e.target.style.transform = "translateY(-2px)";
            e.target.style.boxShadow = "0 8px 25px rgba(0,0,0,0.1)";
          }}
          onMouseLeave={(e) => {
            e.target.style.transform = "translateY(0)";
            e.target.style.boxShadow = "none";
          }}
          >
            <h3 style={{
              fontSize: "20px",
              fontWeight: "600",
              margin: "0 0 16px 0",
              color: "#333"
            }}>
              Map image
            </h3>
            <p style={{
              fontSize: "16px",
              color: "#666",
              margin: "0 0 12px 0",
              lineHeight: "1.5"
            }}>
              PNG or JPG of the choropleth. Use the highest resolution available.
            </p>
            <p style={{
              fontSize: "14px",
              color: "#666",
              margin: "0",
              lineHeight: "1.4"
            }}>
              Crop to the map if possible.
            </p>
          </div>

          {/* Legend Card */}
          <div style={{
            backgroundColor: "white",
            padding: "32px",
            borderRadius: "8px",
            border: "1px solid #e5e5e5",
            transition: "all 0.2s ease"
          }}
          onMouseEnter={(e) => {
            e.target.style.transform = "translateY(-2px)";
            e.target.style.boxShadow = "0 8px 25px rgba(0,0,0,0.1)";
          }}
          onMouseLeave={(e) => {
            e.target.style.transform = "translateY(0)";
            e.target.style.boxShadow = "none";
          }}
          >
            <h3 style={{
              fontSize: "20px",
              fontWeight: "600",
              margin: "0 0 16px 0",
              color: "#333"
            }}>
              Legend
            </h3>
            <p style={{
              fontSize: "16px",
              color: "#666",
              margin: "0 0 12px 0",
              lineHeight: "1.5"
            }}>
              We will create the legend for the image.
            </p>
            <p style={{
              fontSize: "14px",
              color: "#666",
              margin: "0",
              lineHeight: "1.4"
            }}>
              Binned legends are supported.
            </p>
          </div>
        </div>
      </section>

      {/* How it works section */}
      <section style={{
        padding: "60px 0",
        maxWidth: "1200px",
        margin: "0 auto",
        paddingLeft: "24px",
        paddingRight: "24px"
      }}>
        <h2 style={{
          fontSize: "32px",
          fontWeight: "700",
          margin: "0 0 40px 0",
          textAlign: "center",
          color: "#333"
        }}>
          How it works after upload
        </h2>
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: "16px",
          maxWidth: "800px",
          margin: "0 auto"
        }}>
          {[
            "Align boundaries using edge + shape matching; we auto-detect and warp as needed.",
            "Read legend and match colors to values.",
            "Extract county-level metrics and download CSV."
          ].map((step, index) => (
            <div key={index} style={{
              backgroundColor: "white",
              padding: "24px",
              borderRadius: "8px",
              border: "1px solid #e5e5e5",
              display: "flex",
              alignItems: "flex-start",
              gap: "16px",
              transition: "all 0.2s ease"
            }}
            onMouseEnter={(e) => {
              e.target.style.transform = "translateY(-2px)";
              e.target.style.boxShadow = "0 8px 25px rgba(0,0,0,0.1)";
            }}
            onMouseLeave={(e) => {
              e.target.style.transform = "translateY(0)";
              e.target.style.boxShadow = "none";
            }}
            >
              <div style={{
                backgroundColor: "#f5f5f5",
                color: "#333",
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "16px",
                fontWeight: "600",
                flexShrink: 0
              }}>
                {index + 1}
              </div>
              <p style={{
                margin: "0",
                fontSize: "16px",
                color: "#666",
                lineHeight: "1.5"
              }}>
                {step}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section style={{
        padding: "80px 0",
        textAlign: "center",
        maxWidth: "1200px",
        margin: "0 auto",
        paddingLeft: "24px",
        paddingRight: "24px"
      }}>
        <h2 style={{
          fontSize: "32px",
          fontWeight: "700",
          margin: "0 0 16px 0",
          color: "#333"
        }}>
          Ready to get started?
        </h2>
        <p style={{
          fontSize: "18px",
          color: "#666",
          margin: "0 0 32px 0",
          lineHeight: "1.5"
        }}>
          Upload your choropleth map and extract county-level data in minutes.
        </p>
        <button
          onClick={onNavigateToUpload}
          style={{
            backgroundColor: "#333",
            color: "white",
            border: "none",
            padding: "16px 32px",
            borderRadius: "6px",
            fontSize: "18px",
            fontWeight: "500",
            cursor: "pointer",
            transition: "all 0.2s ease"
          }}
          onMouseEnter={(e) => {
            e.target.style.backgroundColor = "#555";
            e.target.style.transform = "translateY(-2px)";
          }}
          onMouseLeave={(e) => {
            e.target.style.backgroundColor = "#333";
            e.target.style.transform = "translateY(0)";
          }}
        >
          Upload file
        </button>
      </section>
    </div>
  );
}
