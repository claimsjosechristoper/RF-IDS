/**
 * RF-IDS Frontend Application
 * Connects to the Flask-SocketIO backend, renders the spectrum analyser,
 * waterfall display, live alert feed, and event log table.
 */

/* ─── Config ──────────────────────────────────────────────────────────────── */
const API = "http://localhost:8765";
const SIGNAL_CLASSES = {
    UNKNOWN: { color: "#64748b", severity: "INFO", icon: "❓" },
    NORMAL: { color: "#22c55e", severity: "INFO", icon: "✅" },
    ASK_OOK: { color: "#3b82f6", severity: "LOW", icon: "📡" },
    FSK: { color: "#8b5cf6", severity: "LOW", icon: "📻" },
    WIDEBAND: { color: "#f59e0b", severity: "MEDIUM", icon: "⚡" },
    JAMMER: { color: "#ef4444", severity: "CRITICAL", icon: "🚨" },
    REPLAY_ATTACK: { color: "#f97316", severity: "HIGH", icon: "🔁" },
    ANOMALY: { color: "#ec4899", severity: "HIGH", icon: "⚠️" },
};
const SEV_COLORS = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    MEDIUM: "#eab308",
    LOW: "#3b82f6",
    INFO: "#64748b",
};

/* ─── State ───────────────────────────────────────────────────────────────── */
let socket = null;
let streaming = false;
let alertCount = 0;
const MAX_ALERTS = 50;
const MAX_LOG = 200;

// Canvases
let specCanvas, specCtx, wfCanvas, wfCtx;
let specWidth = 0, specHeight = 0;
let wfWidth = 0, wfHeight = 0;
let wfImageData = null;   // rolling waterfall pixel buffer

/* ─── Init ────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
    setupCanvases();
    setupLegend();
    startClock();
    loadBands();
    connectSocket();
});

/* ─── Clock ───────────────────────────────────────────────────────────────── */
function startClock() {
    const el = document.getElementById("clock");
    setInterval(() => {
        el.textContent = new Date().toLocaleTimeString();
    }, 500);
}

/* ─── Canvas Setup ────────────────────────────────────────────────────────── */
function setupCanvases() {
    specCanvas = document.getElementById("spectrum-canvas");
    specCtx = specCanvas.getContext("2d");
    wfCanvas = document.getElementById("waterfall-canvas");
    wfCtx = wfCanvas.getContext("2d");

    const dpr = window.devicePixelRatio || 1;

    function resizeCanvases() {
        const specRect = specCanvas.parentElement.getBoundingClientRect();
        specCanvas.width = specRect.width * dpr;
        specCanvas.height = 220 * dpr;
        specCanvas.style.width = specRect.width + "px";
        specCanvas.style.height = "220px";
        specCtx.scale(dpr, dpr);
        specWidth = specRect.width;
        specHeight = 220;

        wfCanvas.width = specRect.width * dpr;
        wfCanvas.height = 180 * dpr;
        wfCanvas.style.width = specRect.width + "px";
        wfCanvas.style.height = "180px";
        wfCtx.scale(dpr, dpr);
        wfWidth = specRect.width;
        wfHeight = 180;
        wfImageData = wfCtx.createImageData(specRect.width * dpr, wfHeight * dpr);
        wfImageData.data.fill(0);
    }

    resizeCanvases();
    window.addEventListener("resize", resizeCanvases);
    drawIdleSpectrum();
}

/* ─── Legend ──────────────────────────────────────────────────────────────── */
function setupLegend() {
    const grid = document.getElementById("legend-grid");
    for (const [name, info] of Object.entries(SIGNAL_CLASSES)) {
        const item = document.createElement("div");
        item.className = "legend-item";
        item.innerHTML = `
      <div class="legend-dot" style="background:${info.color}; box-shadow:0 0 6px ${info.color}55"></div>
      <div>
        <div class="legend-name" style="color:${info.color}">${name}</div>
        <div class="legend-sev">${info.severity}</div>
      </div>`;
        grid.appendChild(item);
    }
}

/* ─── Band Selector ───────────────────────────────────────────────────────── */
async function loadBands() {
    try {
        const res = await fetch(`${API}/api/bands`);
        const bands = await res.json();
        const sel = document.getElementById("band-select");
        bands.forEach(b => {
            const opt = document.createElement("option");
            opt.value = b.freq_hz;
            opt.textContent = `${b.label} – ${(b.freq_hz / 1e6).toFixed(2)} MHz`;
            sel.appendChild(opt);
        });
    } catch (_) { }
}

function quickBand() {
    const val = parseFloat(document.getElementById("band-select").value);
    if (!val) return;
    document.getElementById("input-freq").value = (val / 1e6).toFixed(3);
    tuneFreq();
}

/* ─── Socket.IO ───────────────────────────────────────────────────────────── */
function connectSocket() {
    socket = io(API, { transports: ["websocket"], reconnection: true });

    socket.on("connect", () => {
        setConnected(true);
        console.log("[WS] Connected");
    });
    socket.on("disconnect", () => {
        setConnected(false);
        console.log("[WS] Disconnected");
    });

    socket.on("spectrum", onSpectrum);
    socket.on("waterfall_row", onWaterfallRow);
    socket.on("events", onEvents);
    socket.on("stats", onStats);
}

function setConnected(yes) {
    const dot = document.getElementById("conn-dot");
    const label = document.getElementById("conn-label");
    dot.className = `status-dot ${yes ? "connected" : "disconnected"}`;
    label.textContent = yes ? "Connected" : "Disconnected";
}

/* ─── Stream Controls ─────────────────────────────────────────────────────── */
async function startStream() {
    await fetch(`${API}/api/start`, { method: "POST" });
    streaming = true;
    document.getElementById("btn-start").disabled = true;
    document.getElementById("btn-stop").disabled = false;
    showToast("Streaming started", "info");
}

async function stopStream() {
    await fetch(`${API}/api/stop`, { method: "POST" });
    streaming = false;
    document.getElementById("btn-start").disabled = false;
    document.getElementById("btn-stop").disabled = true;
    showToast("Streaming stopped", "info");
}

async function tuneFreq() {
    const mhz = parseFloat(document.getElementById("input-freq").value);
    if (isNaN(mhz)) return;
    await fetch(`${API}/api/tune`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ freq_hz: mhz * 1e6 }),
    });
    document.getElementById("spectrum-center-label").textContent = mhz.toFixed(3) + " MHz";
    showToast(`Tuned to ${mhz.toFixed(3)} MHz`, "info");
}

async function setGain() {
    const gain = parseFloat(document.getElementById("gain-range").value);
    await fetch(`${API}/api/gain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gain }),
    });
}

document.getElementById("gain-range").addEventListener("input", e => {
    document.getElementById("gain-label").textContent = e.target.value;
});

/* ─── Spectrum Renderer ───────────────────────────────────────────────────── */
let _lastSpec = null;

function onSpectrum(data) {
    _lastSpec = data;
    drawSpectrum(data);

    // Stats bar
    document.getElementById("stat-freq").textContent = data.peak_freq.toFixed(3);
    document.getElementById("stat-power").textContent = data.peak_power.toFixed(1);

    // Demo badge
    document.getElementById("demo-badge").style.display = data.is_demo ? "flex" : "none";
}

function drawSpectrum(data) {
    if (!specCtx || !data.freqs || !data.psd) return;
    const W = specWidth, H = specHeight;
    const freqs = data.freqs;
    const psd = data.psd;
    const nf = data.noise_floor;
    const N = freqs.length;

    // Y scale: dBm range -120 to -20
    const Y_MIN = -120, Y_MAX = -20;
    const yScale = v => H - ((v - Y_MIN) / (Y_MAX - Y_MIN)) * (H - 30) - 10;
    const xScale = i => (i / (N - 1)) * W;

    // Clear
    specCtx.clearRect(0, 0, W, H);

    // Grid
    specCtx.strokeStyle = "rgba(99,179,244,0.08)";
    specCtx.lineWidth = 1;
    for (let db = Y_MIN; db <= Y_MAX; db += 20) {
        const y = yScale(db);
        specCtx.beginPath();
        specCtx.moveTo(0, y);
        specCtx.lineTo(W, y);
        specCtx.stroke();
        specCtx.fillStyle = "rgba(148,163,184,0.4)";
        specCtx.font = "10px JetBrains Mono";
        specCtx.fillText(`${db}`, 3, y - 2);
    }

    // Noise floor
    if (nf && nf.length === N) {
        specCtx.beginPath();
        specCtx.strokeStyle = "rgba(239,68,68,0.4)";
        specCtx.lineWidth = 1;
        specCtx.setLineDash([4, 4]);
        for (let i = 0; i < N; i++) {
            const x = xScale(i), y = yScale(nf[i]);
            i === 0 ? specCtx.moveTo(x, y) : specCtx.lineTo(x, y);
        }
        specCtx.stroke();
        specCtx.setLineDash([]);
    }

    // PSD fill gradient
    const grad = specCtx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, "rgba(0,229,255,0.5)");
    grad.addColorStop(0.5, "rgba(0,229,255,0.15)");
    grad.addColorStop(1, "rgba(0,229,255,0.02)");

    specCtx.beginPath();
    specCtx.moveTo(0, H);
    for (let i = 0; i < N; i++) {
        specCtx.lineTo(xScale(i), yScale(psd[i]));
    }
    specCtx.lineTo(W, H);
    specCtx.closePath();
    specCtx.fillStyle = grad;
    specCtx.fill();

    // PSD line
    specCtx.beginPath();
    specCtx.strokeStyle = "#00e5ff";
    specCtx.lineWidth = 1.5;
    for (let i = 0; i < N; i++) {
        const x = xScale(i), y = yScale(psd[i]);
        i === 0 ? specCtx.moveTo(x, y) : specCtx.lineTo(x, y);
    }
    specCtx.stroke();

    // Freq axis labels
    specCtx.fillStyle = "rgba(148,163,184,0.6)";
    specCtx.font = "10px JetBrains Mono";
    const labelCount = 7;
    for (let k = 0; k <= labelCount; k++) {
        const idx = Math.round((k / labelCount) * (N - 1));
        const freq = freqs[idx];
        const x = xScale(idx);
        specCtx.fillText(freq ? freq.toFixed(2) : "", x - 18, H - 2);
    }
}

function drawIdleSpectrum() {
    specCtx.fillStyle = "rgba(148,163,184,0.15)";
    specCtx.font = "13px Inter";
    specCtx.textAlign = "center";
    specCtx.fillText("→ Press Start to begin spectrum monitoring", specWidth / 2, specHeight / 2);
    specCtx.textAlign = "left";
}

/* ─── Waterfall Renderer ──────────────────────────────────────────────────── */
function onWaterfallRow({ row }) {
    if (!wfCtx || !row) return;
    const dpr = window.devicePixelRatio || 1;
    const W = wfWidth * dpr;
    const H = wfHeight * dpr;

    if (!wfImageData || wfImageData.width !== W || wfImageData.height !== H) {
        wfImageData = wfCtx.createImageData(W, H);
        wfImageData.data.fill(0);
    }

    // Scroll down by 1 row
    wfImageData.data.copyWithin(W * 4, 0);

    // Write new top row
    const N = row.length;
    const MIN = -120, MAX = -20;
    for (let i = 0; i < W; i++) {
        const srcIdx = Math.floor((i / W) * N);
        const val = row[srcIdx] || MIN;
        const t = Math.max(0, Math.min(1, (val - MIN) / (MAX - MIN)));
        const [r, g, b] = heatmapColor(t);
        const px = i * 4;
        wfImageData.data[px] = r;
        wfImageData.data[px + 1] = g;
        wfImageData.data[px + 2] = b;
        wfImageData.data[px + 3] = 255;
    }

    wfCtx.putImageData(wfImageData, 0, 0);
}

/** Maps t∈[0,1] → RGB using a cyan/blue heatmap (cold=dark → hot=cyan/white) */
function heatmapColor(t) {
    // stops: black → deep-blue → cyan → white
    const stops = [
        [0, 0, 0],     // 0.0 – black
        [0, 20, 80],     // 0.2 – deep blue
        [0, 80, 160],     // 0.45
        [0, 200, 240],     // 0.7 – cyan
        [255, 255, 255],     // 1.0 – white
    ];
    const n = stops.length - 1;
    const s = t * n;
    const lo = Math.min(Math.floor(s), n - 1);
    const hi = lo + 1;
    const f = s - lo;
    return stops[lo].map((c, i) => Math.round(c + (stops[hi][i] - c) * f));
}

/* ─── Alert Feed ──────────────────────────────────────────────────────────── */
function onEvents(events) {
    events.forEach(evt => {
        addAlert(evt);
        addLogRow(evt);
        if (["CRITICAL", "HIGH"].includes(evt.severity)) {
            showToast(`${evt.icon} ${evt.signal_class} @ ${evt.freq_mhz} MHz`, evt.severity.toLowerCase());
        }
    });
}

function addAlert(evt) {
    const feed = document.getElementById("alert-feed");
    // Remove empty state
    const empty = feed.querySelector(".empty-state");
    if (empty) empty.remove();

    const info = SIGNAL_CLASSES[evt.signal_class] || SIGNAL_CLASSES["UNKNOWN"];
    const item = document.createElement("div");
    item.className = `alert-item sev-${evt.severity}`;
    item.innerHTML = `
    <div class="alert-icon">${evt.icon}</div>
    <div class="alert-body">
      <div class="alert-class" style="color:${info.color}">${evt.signal_class}</div>
      <div class="alert-desc">${evt.description}</div>
      <div class="alert-meta">
        <span>📡 ${evt.freq_mhz} MHz</span>
        <span>💪 ${evt.power_db} dBm</span>
        <span>🕒 ${evt.timestamp.slice(11)}</span>
      </div>
    </div>`;

    feed.insertBefore(item, feed.firstChild);

    // Trim
    alertCount++;
    while (feed.children.length > MAX_ALERTS) feed.removeChild(feed.lastChild);
}

function clearAlerts() {
    const feed = document.getElementById("alert-feed");
    feed.innerHTML = `<div class="empty-state">
    <div class="empty-icon">📡</div>
    <p>No alerts yet — start streaming to monitor RF activity</p>
  </div>`;
    alertCount = 0;
}

/* ─── Event Log ───────────────────────────────────────────────────────────── */
function addLogRow(evt) {
    const tbody = document.getElementById("log-tbody");
    document.getElementById("log-empty").style.display = "none";

    const info = SIGNAL_CLASSES[evt.signal_class] || SIGNAL_CLASSES["UNKNOWN"];
    const sevColor = SEV_COLORS[evt.severity] || "#64748b";
    const row = document.createElement("tr");
    row.innerHTML = `
    <td>${evt.timestamp.slice(11)}</td>
    <td>${evt.freq_mhz}</td>
    <td style="color:${info.color}">${evt.signal_class}</td>
    <td>${evt.power_db} dBm</td>
    <td><span class="sev-chip" style="background:${sevColor}22;color:${sevColor}">${evt.severity}</span></td>`;

    tbody.insertBefore(row, tbody.firstChild);

    // Trim
    while (tbody.rows.length > MAX_LOG) tbody.deleteRow(tbody.rows.length - 1);
}

function clearLog() {
    document.getElementById("log-tbody").innerHTML = "";
    document.getElementById("log-empty").style.display = "flex";
}

/* ─── Stats ───────────────────────────────────────────────────────────────── */
function onStats(stats) {
    document.getElementById("stat-critical").textContent = stats.critical_count ?? 0;
    document.getElementById("stat-high").textContent = stats.high_count ?? 0;
    document.getElementById("stat-total").textContent = stats.total_events ?? 0;
}

/* ─── Toast Notifications ─────────────────────────────────────────────────── */
function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
