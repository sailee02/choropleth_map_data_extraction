import axios from "axios";
const API_ROOT = import.meta.env.VITE_API_ROOT || "http://localhost:5001";

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
export const downloadFile = (fname) => `${API_ROOT}/api/download/${fname}`;
