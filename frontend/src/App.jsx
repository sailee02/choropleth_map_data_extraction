import React, { useState } from "react";
import Home from "./pages/Home";
import Upload from "./pages/Upload";

export default function App(){
  const [currentPage, setCurrentPage] = useState("home");

  const navigateToHome = () => {
    setCurrentPage("home");
  };

  const navigateToUpload = () => {
    setCurrentPage("upload");
  };

  return (
    <div className="app" style={{
      minHeight: "100vh",
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      backgroundColor: "#fafafa",
      color: "#333"
    }}>
      {/* Header */}
      <header style={{
        backgroundColor: "#fff",
        borderBottom: "1px solid #e5e5e5",
        padding: "16px 24px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center"
      }}>
        <h1 style={{
          margin: "0",
          fontSize: "20px",
          fontWeight: "600",
          color: "#333",
          cursor: "pointer"
        }}
        onClick={navigateToHome}
        >
          GeoData Extractor
        </h1>
        <nav style={{ display: "flex", gap: "24px" }}>
          <button
            onClick={navigateToHome}
            style={{
              background: "none",
              border: "none",
              color: currentPage === "home" ? "#333" : "#666",
              fontSize: "14px",
              fontWeight: currentPage === "home" ? "500" : "400",
              cursor: "pointer",
              textDecoration: "none",
              padding: "8px 0"
            }}
          >
            Home
          </button>
          <button
            onClick={navigateToUpload}
            style={{
              background: "none",
              border: "none",
              color: currentPage === "upload" ? "#333" : "#666",
              fontSize: "14px",
              fontWeight: currentPage === "upload" ? "500" : "400",
              cursor: "pointer",
              textDecoration: "none",
              padding: "8px 0"
            }}
          >
            Upload
          </button>
        </nav>
      </header>

      {/* Main Content */}
      <main>
        {currentPage === "home" && <Home onNavigateToUpload={navigateToUpload} />}
        {currentPage === "upload" && <Upload onNavigateToHome={navigateToHome} />}
      </main>

      {/* Footer */}
      <footer style={{
        backgroundColor: "#f5f5f5",
        padding: "24px",
        textAlign: "center",
        fontSize: "14px",
        color: "#666",
        borderTop: "1px solid #e5e5e5"
      }}>
        2025 Choropleth Map Data Extractor by Sailee Shirodkar and Dheeraj Reddy
      </footer>
    </div>
  );
}
