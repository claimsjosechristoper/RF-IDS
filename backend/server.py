"""
Flask + SocketIO Server — RF-IDS Backend API
Streams real-time spectrum data, events, and stats to the web dashboard.
"""

import threading
import time
import json
import numpy as np

from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

import config
from sdr_manager import SDRManager
from signal_processor import SignalProcessor
from detector import Detector

# ─── App Setup ────────────────────────────────────────────────────────────────
app     = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio= SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                   logger=False, engineio_logger=False)

# ─── Shared State ─────────────────────────────────────────────────────────────
sdr_mgr   = SDRManager()
processor = SignalProcessor()
detector  = Detector()

_streaming     = False
_stream_thread = None
_stream_lock   = threading.Lock()

# Current tuning parameters (mutable via API)
_current_freq  = config.SDR_CENTER_FREQ
_current_gain  = config.SDR_GAIN


# ─── Background Streaming Worker ──────────────────────────────────────────────

def _stream_worker():
    """Runs in a background greenlet: SDR → DSP → Detect → emit."""
    global _streaming
    print("[Server] Stream worker started.")
    sdr_mgr.open()

    while _streaming:
        try:
            samples    = sdr_mgr.read_samples()
            proc_data  = processor.process(samples)
            new_events = detector.analyse(proc_data)

            # Build slim spectrum payload (avoid sending full waterfall every tick)
            payload = {
                "freqs":       proc_data["freqs"],
                "psd":         proc_data["psd"],
                "noise_floor": proc_data["noise_floor"],
                "peak_freq":   proc_data["peak_freq"],
                "peak_power":  proc_data["peak_power"],
                "avg_power":   proc_data["avg_power"],
                "center_freq": proc_data["center_freq"],
                "sample_rate": proc_data["sample_rate"],
                "is_demo":     sdr_mgr.is_demo,
                "timestamp":   time.strftime("%H:%M:%S"),
            }
            socketio.emit("spectrum", payload)

            # Emit waterfall row
            if proc_data["psd"]:
                socketio.emit("waterfall_row", {"row": proc_data["psd"]})

            # Emit new events
            if new_events:
                socketio.emit("events", new_events)
                socketio.emit("stats", detector.get_stats())

            # ~10 FPS target
            time.sleep(0.1)

        except Exception as e:
            print(f"[Stream Worker] Error: {e}")
            time.sleep(0.5)

    sdr_mgr.close()
    print("[Server] Stream worker stopped.")


# ─── REST Endpoints ──────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify({
        "streaming":   _streaming,
        "demo_mode":   sdr_mgr.is_demo,
        "center_freq": _current_freq,
        "gain":        _current_gain,
        "sample_rate": config.SDR_SAMPLE_RATE,
        "fft_size":    config.FFT_SIZE,
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    global _streaming, _stream_thread
    with _stream_lock:
        if _streaming:
            return jsonify({"status": "already_running"})
        _streaming     = True
        _stream_thread = socketio.start_background_task(_stream_worker)
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global _streaming
    _streaming = False
    return jsonify({"status": "stopped"})


@app.route("/api/tune", methods=["POST"])
def api_tune():
    global _current_freq
    data = request.get_json(force=True)
    freq = float(data.get("freq_hz", _current_freq))
    _current_freq = freq
    sdr_mgr.set_center_freq(freq)
    processor.update_center_freq(freq)
    return jsonify({"status": "tuned", "freq_hz": freq})


@app.route("/api/gain", methods=["POST"])
def api_gain():
    global _current_gain
    data = request.get_json(force=True)
    gain = float(data.get("gain", _current_gain))
    _current_gain = gain
    sdr_mgr.set_gain(gain)
    return jsonify({"status": "ok", "gain": gain})


@app.route("/api/events")
def api_events():
    limit = int(request.args.get("limit", 100))
    return jsonify(detector.get_event_log(limit=limit))


@app.route("/api/stats")
def api_stats():
    return jsonify(detector.get_stats())


@app.route("/api/bands")
def api_bands():
    bands = [
        {"freq_hz": f, "label": l, "desc": d}
        for f, l, d in config.SCAN_BANDS
    ]
    return jsonify(bands)


# ─── SocketIO Events ──────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    print(f"[WS] Client connected.")
    socketio.emit("stats", detector.get_stats())


@socketio.on("disconnect")
def on_disconnect():
    print("[WS] Client disconnected.")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  RF-IDS Backend  |  http://localhost:5000")
    print("=" * 60)
    socketio.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT,
                 debug=config.DEBUG_MODE, use_reloader=False, allow_unsafe_werkzeug=True)
