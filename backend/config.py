"""
RF-IDS Configuration
Centralized settings for the RTL-SDR based RF Intrusion Detection System.
"""

# ─── RTL-SDR Hardware Settings ────────────────────────────────────────────────
SDR_SAMPLE_RATE    = 2.048e6     # Samples per second (2.048 MSPS)
SDR_CENTER_FREQ    = 433.92e6   # Default center frequency in Hz (433.92 MHz - IoT band)
SDR_GAIN           = 30         # Gain in dB (0 = auto)
SDR_PPM_CORRECTION = 0          # Frequency correction in PPM
SDR_DEVICE_INDEX   = 0          # RTL-SDR device index

# ─── Signal Acquisition ──────────────────────────────────────────────────────
FFT_SIZE           = 1024       # Number of FFT bins
SAMPLES_PER_READ   = 1024 * 256 # Samples to read per capture
OVERLAP_FACTOR     = 0.5        # FFT overlap factor (0-1)
WATERFALL_HISTORY  = 100        # Number of waterfall rows to keep

# ─── Detection Settings ───────────────────────────────────────────────────────
# Energy detection threshold (dB above noise floor)
ENERGY_THRESHOLD_DB   = 12.0
# Anomaly detection sensitivity (z-score)
ANOMALY_ZSCORE_THRESH = 3.5
# Minimum signal duration (seconds) to classify as an event
MIN_SIGNAL_DURATION   = 0.05
# Cooldown between repeated alerts (seconds)
ALERT_COOLDOWN_SEC    = 2.0
# Baseline noise estimation window (number of FFT frames)
NOISE_FLOOR_WINDOW    = 50

# ─── Frequency Scan Bands ─────────────────────────────────────────────────────
# Each band: (center_freq_hz, label, description)
SCAN_BANDS = [
    (433.92e6, "ISM 433MHz",     "EU/Asia IoT, Remote controls, Temperature sensors"),
    (315.0e6,  "ISM 315MHz",     "US Car key fobs, Remote controls"),
    (868.0e6,  "ISM 868MHz",     "LoRa, ZigBee, Z-Wave (EU)"),
    (915.0e6,  "ISM 915MHz",     "LoRa, ZigBee, Z-Wave (US)"),
    (2400.0e6, "2.4GHz",         "WiFi, Bluetooth, ZigBee (requires HW upconverter)"),
    (88.0e6,   "FM Broadcast",   "Commercial FM radio (reference/test)"),
    (121.5e6,  "Aviation ELT",   "Emergency Locator Transmitters"),
    (406.0e6,  "Cospas-Sarsat",  "Search and Rescue beacons"),
]

# ─── Signal Classification Labels ────────────────────────────────────────────
SIGNAL_CLASSES = {
    "UNKNOWN":       {"color": "#64748b", "severity": "INFO",     "icon": "❓"},
    "NORMAL":        {"color": "#22c55e", "severity": "INFO",     "icon": "✅"},
    "ASK_OOK":       {"color": "#3b82f6", "severity": "LOW",      "icon": "📡"},
    "FSK":           {"color": "#8b5cf6", "severity": "LOW",      "icon": "📻"},
    "WIDEBAND":      {"color": "#f59e0b", "severity": "MEDIUM",   "icon": "⚡"},
    "JAMMER":        {"color": "#ef4444", "severity": "CRITICAL", "icon": "🚨"},
    "REPLAY_ATTACK": {"color": "#f97316", "severity": "HIGH",     "icon": "🔁"},
    "ANOMALY":       {"color": "#ec4899", "severity": "HIGH",     "icon": "⚠️"},
}

# ─── Web Server Settings ──────────────────────────────────────────────────────
SERVER_HOST        = "0.0.0.0"
SERVER_PORT        = 8765
DEBUG_MODE         = False

# ─── Data Storage ────────────────────────────────────────────────────────────
LOG_FILE           = "rf_ids_events.log"
MAX_LOG_ENTRIES    = 10000
DEMO_MODE          = True   # Set to False when RTL-SDR hardware is connected
