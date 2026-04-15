# RF-IDS — RTL-SDR RF Intrusion Detection System

A **real-time Software Defined Radio (SDR)** based Intrusion Detection System that
monitors the RF spectrum for anomalous signals, potential jammers, replay attacks,
and unauthorized transmissions.

## Features

| Feature | Description |
|---|---|
| **Live Spectrum Analyser** | Real-time FFT power spectral density with noise-floor overlay |
| **Waterfall Display** | Scrolling colour-coded waterfall (time × frequency × power) |
| **Intrusion Detection** | Energy threshold + z-score anomaly detection engines |
| **Signal Classification** | Heuristic classifier (OOK/ASK, FSK, Wideband, Jammer, Replay Attack, Anomaly) |
| **Live Alert Feed** | Colour-coded real-time alert panel with severity levels |
| **Event Log Table** | Persistent scrollable event history |
| **Band Scanner** | Pre-configured bands: 433 MHz, 315 MHz, 868 MHz, 915 MHz, FM, ELT |
| **Demo Mode** | Fully synthetic signal generator — works _without_ RTL-SDR hardware |

## Quick Start

### 1 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2 — Start the backend server
**Windows:** Double-click `start_server.bat`

**Manual:**
```bash
cd backend
python server.py
```

### 3 — Open the dashboard
Open `frontend/index.html` in your browser (Chrome / Edge recommended).

> **Note:** If you see CORS errors, serve the frontend via a local HTTP server:
> ```bash
> cd frontend
> python -m http.server 8080
> ```
> Then open http://localhost:8080

### 4 — Press ▶ Start in the dashboard

---

## Hardware Setup (RTL-SDR)

1. Plug in your RTL-SDR dongle
2. Install [Zadig drivers](https://zadig.akeo.ie/) (Windows: replace with WinUSB)
3. In `backend/config.py` set `DEMO_MODE = False`
4. Restart the server — it will auto-detect your device

---

## Architecture

```
rf-ids/
├── backend/
│   ├── config.py          # All tunable parameters
│   ├── sdr_manager.py     # RTL-SDR HAL + demo signal generator
│   ├── signal_processor.py# FFT / PSD / waterfall / noise-floor
│   ├── detector.py        # Energy + anomaly detection + classification
│   └── server.py          # Flask + SocketIO REST & WS API
├── frontend/
│   ├── index.html         # Dashboard layout
│   ├── style.css          # Dark-theme design system
│   └── app.js             # Canvas renderers + SocketIO client
├── requirements.txt
└── start_server.bat
```

## Detection Algorithms

### 1. Energy Threshold Detection
- Estimates noise floor using the **10th-percentile** of rolling PSD history
- Flags any spectral bin exceeding the noise floor by `ENERGY_THRESHOLD_DB` (default: 12 dB)
- Groups contiguous elevated bins into signal blobs

### 2. Z-Score Anomaly Detection
- Tracks rolling mean & std-dev of aggregate wideband power
- Raises `ANOMALY` alert when z-score exceeds `ANOMALY_ZSCORE_THRESH` (default: 3.5σ)

### 3. Signal Classification Rules
| Class | Criteria |
|---|---|
| `JAMMER` | BW > 5 MHz AND power > −40 dBm |
| `WIDEBAND` | BW > 2 MHz |
| `REPLAY_ATTACK` | Narrow OOK burst, 315/433 MHz band, high power |
| `ASK_OOK` | BW < 50 kHz, 315/433 MHz band |
| `FSK` | 50 kHz ≤ BW ≤ 500 kHz |
| `NORMAL` | Everything else above threshold |
| `ANOMALY` | Z-score trigger on aggregate power |

## Configuration (`backend/config.py`)

| Parameter | Default | Description |
|---|---|---|
| `SDR_CENTER_FREQ` | 433.92 MHz | Initial centre frequency |
| `SDR_SAMPLE_RATE` | 2.048 MSPS | RTL-SDR sample rate |
| `SDR_GAIN` | 30 dB | RF gain |
| `FFT_SIZE` | 1024 | FFT resolution |
| `ENERGY_THRESHOLD_DB` | 12 dB | Detection sensitivity |
| `ANOMALY_ZSCORE_THRESH` | 3.5 | Anomaly sensitivity |
| `DEMO_MODE` | `True` | Synthetic mode (no hardware needed) |

## REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | Server & device status |
| POST | `/api/start` | Start streaming |
| POST | `/api/stop` | Stop streaming |
| POST | `/api/tune` | Tune centre frequency `{freq_hz: float}` |
| POST | `/api/gain` | Set gain `{gain: float}` |
| GET | `/api/events` | Event log (query `?limit=N`) |
| GET | `/api/stats` | Detection statistics |
| GET | `/api/bands` | Preconfigured scan bands |

## WebSocket Events (SocketIO)

| Event | Direction | Payload |
|---|---|---|
| `spectrum` | Server→Client | freqs, psd, noise_floor, peak_freq/power, metadata |
| `waterfall_row` | Server→Client | Single PSD row for waterfall |
| `events` | Server→Client | List of new RFEvent objects |
| `stats` | Server→Client | Aggregate detection statistics |
