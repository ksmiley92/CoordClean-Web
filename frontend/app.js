const BACKEND_URL = "http://localhost:8000/convert";

const map = L.map("map").setView([39.5, -98.35], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);

const fileInput = document.getElementById("fileInput");
const inputCrs = document.getElementById("inputCrs");
const outputCrs = document.getElementById("outputCrs");
const convertBtn = document.getElementById("convertBtn");
const downloadBtn = document.getElementById("downloadBtn");
const statusEl = document.getElementById("status");

const MOCK_POINTS = [
  { lat: 40.7128, lon: -74.006, label: "New York" },
  { lat: 34.0522, lon: -118.2437, label: "Los Angeles" },
  { lat: 41.8781, lon: -87.6298, label: "Chicago" },
  { lat: 29.7604, lon: -95.3698, label: "Houston" },
  { lat: 47.6062, lon: -122.3321, label: "Seattle" },
];

function setStatus(message, kind) {
  statusEl.textContent = message;
  statusEl.className = kind || "";
}

function renderPoints(points) {
  markersLayer.clearLayers();

  if (!points || points.length === 0) {
    setStatus("No points to display.", "info");
    return;
  }

  const latLngs = [];
  points.forEach((p, i) => {
    const marker = L.marker([p.lat, p.lon]);
    marker.bindPopup(p.label ? p.label : "Row " + (i + 1));
    marker.addTo(markersLayer);
    latLngs.push([p.lat, p.lon]);
  });

  map.fitBounds(latLngs, { padding: [30, 30] });
}

convertBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    setStatus("Please choose a CSV or XLSX file first.", "error");
    return;
  }

  setStatus("Converting...", "info");
  convertBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("input_crs", inputCrs.value);
  formData.append("output_crs", outputCrs.value);

  try {
    const response = await fetch(BACKEND_URL, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Backend responded with status " + response.status);
    }

    const data = await response.json();
    renderPoints(data.points || []);
    setStatus("Conversion complete.", "success");
    downloadBtn.disabled = false;
  } catch (err) {
    renderPoints(MOCK_POINTS);
    setStatus(
      "Backend not available - showing mock preview. (" + err.message + ")",
      "info"
    );
    downloadBtn.disabled = false;
  } finally {
    convertBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  setStatus("Download will be wired to the backend response.", "info");
});
