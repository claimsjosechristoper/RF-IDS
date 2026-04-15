"""
SDR Manager — RTL-SDR Hardware Abstraction Layer
Handles device open/close, tuning, and sample streaming.
Provides a DEMO mode that synthesizes realistic IQ samples
when no hardware is attached.
"""

import time
import threading
import numpy as np
import config

# Try importing rtlsdr – optional (demo mode works without it)
try:
    from rtlsdr import RtlSdr
    RTLSDR_AVAILABLE = True
except ImportError:
    RTLSDR_AVAILABLE = False


class SDRManager:
    """Thread-safe wrapper around the RTL-SDR device."""

    def __init__(self):
        self._sdr        = None
        self._lock       = threading.Lock()
        self._demo_mode  = config.DEMO_MODE or not RTLSDR_AVAILABLE
        self._center_freq= config.SDR_CENTER_FREQ
        self._running    = False
        self._demo_t     = 0.0  # synthetic time for demo signal generation

    # ── Device Lifecycle ──────────────────────────────────────────────────────

    def open(self) -> bool:
        if self._demo_mode:
            print("[SDR] Demo mode – synthetic IQ samples will be used.")
            return True
        try:
            with self._lock:
                self._sdr = RtlSdr(config.SDR_DEVICE_INDEX)
                self._sdr.sample_rate   = config.SDR_SAMPLE_RATE
                self._sdr.center_freq   = self._center_freq
                self._sdr.gain          = config.SDR_GAIN
                self._sdr.freq_correction= config.SDR_PPM_CORRECTION
            print(f"[SDR] Device opened @ {self._center_freq/1e6:.3f} MHz")
            return True
        except Exception as e:
            print(f"[SDR] Failed to open device: {e} – switching to demo mode.")
            self._demo_mode = True
            return True   # graceful fallback

    def close(self):
        if self._sdr:
            with self._lock:
                try:
                    self._sdr.close()
                except Exception:
                    pass
                self._sdr = None

    # ── Tuning ────────────────────────────────────────────────────────────────

    def set_center_freq(self, freq_hz: float):
        self._center_freq = freq_hz
        if not self._demo_mode and self._sdr:
            with self._lock:
                self._sdr.center_freq = freq_hz

    def set_gain(self, gain: float):
        if not self._demo_mode and self._sdr:
            with self._lock:
                self._sdr.gain = gain

    # ── Sample Acquisition ────────────────────────────────────────────────────

    def read_samples(self, count: int = config.SAMPLES_PER_READ) -> np.ndarray:
        if self._demo_mode:
            return self._generate_demo_samples(count)
        with self._lock:
            try:
                return self._sdr.read_samples(count)
            except Exception as e:
                print(f"[SDR] Read error: {e}")
                return self._generate_demo_samples(count)

    @property
    def is_demo(self) -> bool:
        return self._demo_mode

    @property
    def center_freq(self) -> float:
        return self._center_freq

    # ── Demo Signal Generator ─────────────────────────────────────────────────

    def _generate_demo_samples(self, count: int) -> np.ndarray:
        """
        Synthesises realistic IQ samples containing:
        - Gaussian noise floor
        - Periodic narrowband tones (simulating sensors)
        - Random bursts (simulating intruder transmissions)
        - Occasional wideband chirp (simulating jammer)
        """
        sr   = config.SDR_SAMPLE_RATE
        fc   = self._center_freq
        t    = np.arange(count) / sr + self._demo_t
        self._demo_t += count / sr

        # Base noise
        noise = (np.random.randn(count) + 1j * np.random.randn(count)) * 0.02

        # Always-on narrow CW tones (sensors)
        for offset_khz in [-250, 125, 380]:
            amp = np.random.uniform(0.04, 0.08)
            noise += amp * np.exp(2j * np.pi * offset_khz * 1e3 * t)

        # Periodic burst (every ~3 s)
        if int(self._demo_t * 10) % 30 < 5:
            noise += 0.15 * np.exp(2j * np.pi * (-100e3) * t) * \
                     np.hanning(count)

        # Random rare wideband chirp (jammer sim, ~1% probability)
        if np.random.rand() < 0.01:
            chirp_bw = 1.5e6
            chirp    = 0.25 * np.exp(1j * np.pi * (chirp_bw / count) * t**2)
            noise   += chirp

        # Random OOK burst (replay attack sim, ~3% probability)
        if np.random.rand() < 0.03:
            burst_freq = np.random.choice([-350e3, 200e3])
            noise += 0.2 * np.exp(2j * np.pi * burst_freq * t) * \
                     (np.random.rand(count) > 0.5).astype(float)

        return noise.astype(np.complex64)
