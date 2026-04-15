"""
Signal Processor — Core DSP Engine for RF-IDS
Handles FFT computation, power spectral density, waterfall data,
and noise-floor baseline estimation.
"""

import numpy as np
from collections import deque
import config


class SignalProcessor:
    """
    Wraps raw IQ samples → FFT → PSD → waterfall → noise baseline.
    Thread-safe for use with Flask-SocketIO background tasks.
    """

    def __init__(self):
        self.fft_size       = config.FFT_SIZE
        self.sample_rate    = config.SDR_SAMPLE_RATE
        self.center_freq    = config.SDR_CENTER_FREQ
        self.noise_window   = config.NOISE_FLOOR_WINDOW
        self.waterfall_hist = config.WATERFALL_HISTORY

        # Ring buffers
        self._psd_history:  deque = deque(maxlen=self.noise_window)
        self._waterfall:    deque = deque(maxlen=self.waterfall_hist)

        # Pre-compute Blackman-Harris window (good side-lobe suppression)
        self._window = np.blackman(self.fft_size)
        self._freq_bins = self._compute_freq_bins()

        # Noise-floor baseline (dBm)
        self._noise_floor: np.ndarray | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, iq_samples: np.ndarray) -> dict:
        """
        Main entry point.  Feed raw complex IQ samples;
        returns a dict ready for JSON serialization.
        """
        psd_db = self._compute_psd(iq_samples)
        self._update_noise_floor(psd_db)
        self._waterfall.appendleft(psd_db.tolist())

        excess_db   = self._excess_power(psd_db)
        peak_idx    = int(np.argmax(psd_db))
        peak_freq   = float(self._freq_bins[peak_idx])
        peak_power  = float(psd_db[peak_idx])
        avg_power   = float(np.mean(psd_db))

        return {
            "freqs":       self._freq_bins.tolist(),
            "psd":         psd_db.tolist(),
            "waterfall":   list(self._waterfall),
            "noise_floor": self._noise_floor.tolist() if self._noise_floor is not None else [],
            "excess_db":   excess_db.tolist(),
            "peak_freq":   peak_freq,
            "peak_power":  peak_power,
            "avg_power":   avg_power,
            "center_freq": self.center_freq,
            "sample_rate": self.sample_rate,
        }

    def update_center_freq(self, freq_hz: float):
        self.center_freq = freq_hz
        self._freq_bins  = self._compute_freq_bins()
        self._psd_history.clear()
        self._waterfall.clear()
        self._noise_floor = None

    # ── Private helpers ───────────────────────────────────────────────────────

    def _compute_psd(self, iq: np.ndarray) -> np.ndarray:
        """Welch-style averaged PSD over multiple FFT segments."""
        n = len(iq)
        hop = int(self.fft_size * (1 - config.OVERLAP_FACTOR))
        segments = []

        start = 0
        while start + self.fft_size <= n:
            chunk   = iq[start: start + self.fft_size] * self._window
            spectrum= np.fft.fftshift(np.fft.fft(chunk, n=self.fft_size))
            psd     = (np.abs(spectrum) ** 2) / (np.sum(self._window ** 2) * self.sample_rate)
            segments.append(psd)
            start  += hop

        if not segments:
            # Fallback: single shot
            chunk   = iq[: self.fft_size] * self._window
            spectrum= np.fft.fftshift(np.fft.fft(chunk, n=self.fft_size))
            psd     = (np.abs(spectrum) ** 2) / (np.sum(self._window ** 2) * self.sample_rate)
            segments = [psd]

        avg_psd = np.mean(segments, axis=0)
        # Convert to dBm (referenced to 50Ω, 1 mW)
        psd_db  = 10 * np.log10(avg_psd + 1e-20) + 30
        return psd_db

    def _compute_freq_bins(self) -> np.ndarray:
        half = self.sample_rate / 2
        return np.linspace(
            self.center_freq - half,
            self.center_freq + half,
            self.fft_size
        ) / 1e6  # Return in MHz for display

    def _update_noise_floor(self, psd_db: np.ndarray):
        self._psd_history.append(psd_db)
        stack = np.stack(self._psd_history, axis=0)
        # Use 10th-percentile as noise floor estimate (robust to transient signals)
        self._noise_floor = np.percentile(stack, 10, axis=0)

    def _excess_power(self, psd_db: np.ndarray) -> np.ndarray:
        if self._noise_floor is None:
            return np.zeros_like(psd_db)
        return np.maximum(psd_db - self._noise_floor, 0)
