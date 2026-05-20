const backendUrl = "http://localhost:8000/convert";

const map = L.map("map").setView([39.5, -98.35], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);

const fileInput = document.getElementById("fileInput");
const outputFormat = document.getElementById("outputFormat");
const convertBtn = document.getElementById("convertBtn");
const downloadBtn = document.getElementById("downloadBtn");
const statusEl = document.getElementById("status");
const helpBtn = document.getElementById("HelpBtn");
const helpText = document.getElementById("helpText");

// Latest successful conversion, held in memory for the Download button to consume.
let lastCsvText = null;
let lastFilename = null;

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
  formData.append("output_format", outputFormat.value);

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      // Surface the backend's `detail` message when present.
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Status " + response.status);
    }

    const data = await response.json();
    renderPoints(data.points || []);
    lastCsvText = data.csv_text;
    lastFilename = data.filename;
    if (data.dropped_count > 0) {
      setStatus(
        `Converted ${data.row_count} row(s). ${data.dropped_count} row(s) couldn't be parsed and were dropped.`,
        "info"
      );
    } else {
      setStatus("Conversion complete.", "success");
    }
    downloadBtn.disabled = false;
  } catch (err) {
    markersLayer.clearLayers();
    lastCsvText = null;
    lastFilename = null;
    downloadBtn.disabled = true;
    setStatus(err.message, "error");
  } finally {
    convertBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  if (!lastCsvText) {
    setStatus("Convert a file first.", "error");
    return;
  }
  const blob = new Blob([lastCsvText], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = lastFilename || "coordclean.csv";
  a.click();
  URL.revokeObjectURL(url);
});

helpBtn.addEventListener("click", () => {
  helpText.classList.toggle("hidden");
});