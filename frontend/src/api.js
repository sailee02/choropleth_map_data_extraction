import axios from "axios";
const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

export const previewLegend = (uploadId, legendSelection, legendTypeInfo = null) => {
  const form = new FormData();
  form.append("upload_id", uploadId);
  form.append("legend_selection", JSON.stringify(legendSelection));
  if (legendTypeInfo) {
    form.append("legend_type_info", JSON.stringify(legendTypeInfo));
  }
  return axios.post(`${API_ROOT}/api/preview-legend`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const detectBounds = (file, uploadId = null) => {
  const form = new FormData();
  form.append("file", file);
  if (uploadId) {
    form.append("upload_id", uploadId);
  }
  return axios.post(`${API_ROOT}/api/detect-bounds`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const uploadImage = (
  file,
  layer = "uploaded",
  n_clusters = 6,
  legendSelection = null,
  uploadId = null,
  regionSelections = null,
  projection = "4326",
  legendTypeInfo = null
) => {
  const form = new FormData();
  form.append("file", file);
  form.append("layer", layer);
  form.append("n_clusters", String(n_clusters));
  form.append("projection", String(projection));
  
  if (legendSelection) {
    form.append("legend_selection", JSON.stringify(legendSelection));
  }
  if (uploadId) {
    form.append("upload_id", uploadId);
  }
  if (regionSelections) {
    console.log("🔍 DEBUG: Sending regionSelections to backend:", JSON.stringify(regionSelections, null, 2));
    form.append("region_selections", JSON.stringify(regionSelections));
  }
  if (legendTypeInfo) {
    form.append("legend_type_info", JSON.stringify(legendTypeInfo));
  }
  
  return axios.post(`${API_ROOT}/api/process`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const setBoundsManually = (uploadId, boundsJson) => {
  return axios.post(`${API_ROOT}/api/bounds/${uploadId}`, boundsJson, {
    headers: { "Content-Type": "application/json" },
  });
};

export const regenerateOverlay = (uploadId) => {
  return axios.post(`${API_ROOT}/api/bounds/${uploadId}/regenerate-overlay`);
};

export const generateOverlayPreview = (uploadId, projection = "4326", regionSelections = null) => {
  const form = new FormData();
  form.append("upload_id", uploadId);
  form.append("projection", String(projection));
  if (regionSelections) {
    form.append("region_selections", JSON.stringify(regionSelections));
  }
  return axios.post(`${API_ROOT}/api/generate-overlay-preview`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const fetchGeoJSON = (layer = "uploaded") => axios.get(`${API_ROOT}/api/choropleth/${layer}`);
export const downloadFile = (fname) =>
  `${API_ROOT}/api/download/${encodeURIComponent(fname)}`;

/** Match server-side CSV names: only safe path characters for Windows / “Open” handlers. */
function sanitizeCsvDownloadName(name) {
  let base = String(name || "").trim() || "export.csv";
  if (!base.toLowerCase().endsWith(".csv")) base = `${base}.csv`;
  const stem = base.slice(0, -4);
  const safeStem = stem.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  return `${safeStem || "export"}.csv`;
}

/**
 * Download a file from /api/download via fetch + blob so the browser saves it reliably.
 * Plain <a href="other-origin" download> ignores `download` cross-origin and can confuse
 * some environments; this always triggers a real save with the given filename.
 */
export async function downloadCsvBlob(fname) {
  const serverName = String(fname || "").trim() || "export.csv";
  const url = downloadFile(serverName);
  const res = await fetch(url);
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      if (j && j.error) detail = String(j.error);
    } catch {
      try {
        detail = (await res.text()).slice(0, 200);
      } catch {
        /* ignore */
      }
    }
    throw new Error(detail || `Download failed (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const localName = sanitizeCsvDownloadName(serverName);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = localName;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking the blob URL immediately breaks some browsers: the copy to Downloads is
  // async, so “Open” can point at a path that was never finished or was cleaned up.
  setTimeout(() => URL.revokeObjectURL(blobUrl), 120_000);
}
