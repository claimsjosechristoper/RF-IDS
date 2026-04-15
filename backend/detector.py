"""
Detector — RF Intrusion Detection Engine
Analyses processed spectrum data and classifies signals as
normal, suspicious, or hostile events.

Detection pipeline:
  1. Energy Threshold Detection – spots signals above noise floor
  2. Signal Characterisation – estimates BW, centre, duration, modulation
  3. Anomaly Detection – z-score against a rolling baseline
  4. Rule-based Classification – maps features → threat class
"""

import time
import numpy as np
from collections import deque
import config


class RFEvent:
    """Represents a single detected RF event."""

    def __init__(self, freq_mhz: float, power_db: float, bandwidth_mhz: float,
                 signal_class: str, confidence: float, description: str):
        self.id          = int(time.time() * 1000)
        self.timestamp   = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.freq_mhz    = round(freq_mhz, 4)
        self.power_db    = round(power_db, 2)
        self.bandwidth_mhz = round(bandwidth_mhz, 4)
        self.signal_class = signal_class
        self.confidence  = round(confidence, 2)
        self.description = description
        meta             = config.SIGNAL_CLASSES.get(signal_class, config.SIGNAL_CLASSES["UNKNOWN"])
        self.severity    = meta["severity"]
        self.color       = meta["color"]
        self.icon        = meta["icon"]

    def to_dict(self) -> dict:
        return self.__dict__


class Detector:
    """
    Stateful detector that consumes SignalProcessor output and emits RFEvents.
    """

    def __init__(self):
        self._last_alert_time: dict[str, float] = {}
        self._power_history: deque = deque(maxlen=200)
        self._event_log: list[RFEvent] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def analyse(self, proc_data: dict) -> list[dict]:
        """
        Main entry point.
        Returns list of new RFEvent dicts (may be empty).
        """
        freqs      = np.array(proc_data["freqs"])
        psd        = np.array(proc_data["psd"])
        excess     = np.array(proc_data["excess_db"])
        avg_power  = proc_data["avg_power"]

        self._power_history.append(avg_power)

        events = []

        # Step 1 – Energy threshold scan
        new_events = self._energy_scan(freqs, psd, excess)

        # Step 2 – Anomaly detection on aggregate power
        anomaly_evt = self._anomaly_detect(avg_power, freqs, psd)
        if anomaly_evt:
            new_events.append(anomaly_evt)

        # Step 3 – Cooldown filter + log
        for evt in new_events:
            if self._cooldown_ok(evt.signal_class, evt.freq_mhz):
                self._event_log.append(evt)
                self._last_alert_time[f"{evt.signal_class}_{evt.freq_mhz:.1f}"] = time.time()
                events.append(evt.to_dict())

        return events

    def get_event_log(self, limit: int = 200) -> list[dict]:
        return [e.to_dict() for e in self._event_log[-limit:]]

    def get_stats(self) -> dict:
        total      = len(self._event_log)
        by_sev     = {}
        by_class   = {}
        for e in self._event_log:
            by_sev[e.severity]      = by_sev.get(e.severity, 0) + 1
            by_class[e.signal_class]= by_class.get(e.signal_class, 0) + 1
        return {
            "total_events":    total,
            "by_severity":     by_sev,
            "by_class":        by_class,
            "critical_count":  by_sev.get("CRITICAL", 0),
            "high_count":      by_sev.get("HIGH", 0),
        }

    # ── Detection methods ────────────────────────────────────────────────────

    def _energy_scan(self, freqs: np.ndarray, psd: np.ndarray,
                     excess: np.ndarray) -> list[RFEvent]:
        """Find contiguous frequency blocks above threshold and classify them."""
        threshold = config.ENERGY_THRESHOLD_DB
        above     = excess > threshold
        events    = []

        if not np.any(above):
            return events

        # Find contiguous blobs
        transitions = np.diff(above.astype(int), prepend=0, append=0)
        starts = np.where(transitions == 1)[0]
        ends   = np.where(transitions == -1)[0]

        for s, e in zip(starts, ends):
            blob_freqs  = freqs[s:e]
            blob_psd    = psd[s:e]
            blob_excess = excess[s:e]

            center_freq  = float(blob_freqs[np.argmax(blob_psd)])
            peak_power   = float(np.max(blob_psd))
            bandwidth    = float(blob_freqs[-1] - blob_freqs[0]) if len(blob_freqs) > 1 else 0.001
            avg_excess   = float(np.mean(blob_excess))
            confidence   = min(1.0, avg_excess / (threshold * 3))

            signal_class, desc = self._classify(center_freq, peak_power, bandwidth)
            events.append(RFEvent(center_freq, peak_power, bandwidth,
                                  signal_class, confidence, desc))

        return events

    def _anomaly_detect(self, avg_power: float, freqs: np.ndarray,
                        psd: np.ndarray) -> RFEvent | None:
        """Z-score anomaly on rolling aggregate power."""
        if len(self._power_history) < 20:
            return None
        history = np.array(self._power_history)
        mu, sigma = np.mean(history[:-1]), np.std(history[:-1])
        if sigma < 0.5:
            return None
        z = abs((avg_power - mu) / sigma)
        if z > config.ANOMALY_ZSCORE_THRESH:
            cx = float(freqs[len(freqs)//2])
            conf = min(1.0, (z - config.ANOMALY_ZSCORE_THRESH) / 5.0)
            return RFEvent(cx, avg_power, float(freqs[-1] - freqs[0]),
                           "ANOMALY", conf,
                           f"Wideband power anomaly detected (z={z:.1f})")
        return None

    def _classify(self, freq_mhz: float, power_db: float,
                  bw_mhz: float) -> tuple[str, str]:
        """
        Rule-based heuristic classifier.
        Returns (signal_class, description).
        """
        freq_hz = freq_mhz * 1e6

        # Jamming: very wide, high power
        if bw_mhz > 5.0 and power_db > -40:
            return "JAMMER", f"Potential jammer @ {freq_mhz:.3f} MHz, BW={bw_mhz:.2f} MHz"

        # Wideband burst (could be frequency hopping / spread-spectrum attack)
        if bw_mhz > 2.0:
            return "WIDEBAND", f"Wideband signal @ {freq_mhz:.3f} MHz, BW={bw_mhz:.2f} MHz"

        # Narrow OOK/ASK — typical of 433/315 MHz remote controls & sensors
        if bw_mhz < 0.05 and (400e6 < freq_hz < 440e6 or 310e6 < freq_hz < 320e6):
            if power_db > -50:
                return "REPLAY_ATTACK", f"Suspicious OOK burst @ {freq_mhz:.3f} MHz (replay?)"
            return "ASK_OOK", f"OOK/ASK signal @ {freq_mhz:.3f} MHz"

        # FSK — typical of LoRa/ZigBee/Z-Wave
        if 0.05 <= bw_mhz <= 0.5:
            return "FSK", f"FSK signal @ {freq_mhz:.3f} MHz, BW={bw_mhz*1000:.0f} kHz"

        # Normal signal (known profile, nothing suspicious)
        return "NORMAL", f"Signal @ {freq_mhz:.3f} MHz, BW={bw_mhz*1000:.0f} kHz"

    def _cooldown_ok(self, signal_class: str, freq_mhz: float) -> bool:
        key      = f"{signal_class}_{freq_mhz:.1f}"
        last     = self._last_alert_time.get(key, 0)
        return (time.time() - last) >= config.ALERT_COOLDOWN_SEC
