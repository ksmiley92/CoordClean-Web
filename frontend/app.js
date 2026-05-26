const backendUrl = "https://coordly-api.onrender.com/convert";
const backendDownloadUrl = "https://coordly-api.onrender.com/download";
const freeRowLimit = 10;

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
const paywall = document.getElementById("paywall");
const stripePayBtn = document.getElementById("stripePayBtn");

let lastCsvText = null;
let lastFilename = null;
let lastJobId = null;
let lastCheckoutUrl = null;
let paymentComplete = false;

function setStatus(message, kind) {
  statusEl.textContent = message;
  statusEl.className = kind || "";
}

function updatePaywall(needsPayment) {
  if (needsPayment && !paymentComplete) {
    paywall.classList.remove("hidden");
    downloadBtn.disabled = true;
  } else {
    paywall.classList.add("hidden");
    downloadBtn.disabled = !lastCsvText;
  }
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

async function handlePaymentReturn() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session_id");
  const jobId = params.get("job_id");

  if (params.get("cancelled") === "1") {
    history.replaceState(null, "", window.location.pathname);
    setStatus("Payment cancelled. Convert again when you're ready.", "info");
    return;
  }

  if (!sessionId || !jobId) {
    return;
  }

  setStatus("Verifying payment...", "info");

  try {
    const url =
      backendDownloadUrl +
      "?job_id=" +
      encodeURIComponent(jobId) +
      "&session_id=" +
      encodeURIComponent(sessionId);
    const response = await fetch(url);

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Status " + response.status);
    }

    const data = await response.json();
    lastCsvText = data.csv_text;
    lastFilename = data.filename;
    lastJobId = jobId;
    paymentComplete = true;
    updatePaywall(false);
    setStatus("Payment received. You can download your file.", "success");
    history.replaceState(null, "", window.location.pathname);
  } catch (err) {
    setStatus(err.message, "error");
    history.replaceState(null, "", window.location.pathname);
  }
}

convertBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    setStatus("Please choose a CSV or XLSX file first.", "error");
    return;
  }

  setStatus("Converting...", "info");
  convertBtn.disabled = true;
  paymentComplete = false;
  lastJobId = null;
  lastCheckoutUrl = null;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("output_format", outputFormat.value);

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || "Status " + response.status);
    }

    const data = await response.json();
    renderPoints(data.points || []);

    if (data.needs_payment) {
      lastCsvText = null;
      lastFilename = null;
      lastJobId = data.job_id;
      lastCheckoutUrl = data.checkout_url;
      updatePaywall(true);
    } else {
      lastCsvText = data.csv_text;
      lastFilename = data.filename;
      updatePaywall(false);
    }

    if (data.dropped_count > 0) {
      setStatus(
        `Converted ${data.row_count} row(s). ${data.dropped_count} row(s) couldn't be parsed and were dropped.`,
        "info"
      );
    } else if (!data.needs_payment) {
      setStatus("Conversion complete.", "success");
    } else {
      setStatus(
        `Converted ${data.row_count} row(s). Pay to download the cleaned file.`,
        "info"
      );
    }
  } catch (err) {
    markersLayer.clearLayers();
    lastCsvText = null;
    lastFilename = null;
    lastJobId = null;
    lastCheckoutUrl = null;
    paymentComplete = false;
    paywall.classList.add("hidden");
    downloadBtn.disabled = true;
    setStatus(err.message, "error");
  } finally {
    convertBtn.disabled = false;
  }
});

stripePayBtn.addEventListener("click", () => {
  if (lastCheckoutUrl) {
    window.location.href = lastCheckoutUrl;
  } else {
    setStatus("Convert a file first.", "error");
  }
});

downloadBtn.addEventListener("click", () => {
  if (!lastCsvText) {
    setStatus("Convert a file first.", "error");
    return;
  }
  if (!paywall.classList.contains("hidden") && !paymentComplete) {
    setStatus("Payment required for files over 10 rows.", "error");
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

handlePaymentReturn();
