from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np


def _ensure_np_array(x, dtype=None) -> np.ndarray:
    """Coerce input to a NumPy array (copy=False when safe).

    Parameters
    ----------
    x : array-like
        Input object to convert to a NumPy array.
    dtype : data-type, optional
        Desired data type of the returned array. If `None`, infers from `x`.

    Returns
    -------
    np.ndarray
        The coerced NumPy array.
    """
    if isinstance(x, np.ndarray):
        return x.astype(dtype) if (dtype is not None and x.dtype != dtype) else x
    return np.asarray(x, dtype=dtype)


@dataclass(frozen=True)
class IQFrame:
    """Raw complex-baseband capture from an SDR device.

    Semantics
    ---------
    - `samples` are complex64 IQ data at `fs_hz` sample rate.
    - `center_freq_hz` is the tuned RF center frequency during capture.
    - `impedance_ohm` is the reference system impedance used for power conversions (default 50 Ω).
    - `gain_db` is the RF/frontend gain as reported by the device (when applicable).

    Notes
    -----
    Immutability is enforced to prevent accidental mutation across processing stages.
    """

    samples: np.ndarray  # complex64, shape: (N,) or (K, N) for segmented blocks
    fs_hz: float
    center_freq_hz: float
    impedance_ohm: float = 50.0
    gain_db: Optional[float] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize fields."""
        object.__setattr__(
            self, "samples", _ensure_np_array(self.samples, np.complex64)
        )
        if self.samples.ndim not in (1, 2):
            raise ValueError("samples must be 1-D (N,) or 2-D (K, N)")
        if not np.isfinite(self.fs_hz) or self.fs_hz <= 0:
            raise ValueError("fs_hz must be a positive finite float")
        if not np.isfinite(self.center_freq_hz) or self.center_freq_hz <= 0:
            raise ValueError("center_freq_hz must be a positive finite float")
        if not np.isfinite(self.impedance_ohm) or self.impedance_ohm <= 0:
            raise ValueError(
                "impedance_ohm must be a positive finite float (e.g., 50.0)"
            )

    @property
    def n_channels(self) -> int:
        """Number of segmented blocks (1 if samples is 1-D)."""
        return 1 if self.samples.ndim == 1 else self.samples.shape[0]

    @property
    def n_samples(self) -> int:
        """Number of samples per block (N)."""
        return self.samples.shape[-1]

    @property
    def duration_s(self) -> float:
        """Capture duration in seconds for a single block."""
        return float(self.n_samples) / float(self.fs_hz)


@dataclass(frozen=True)
class SpectrumFrame:
    """Power Spectral Density (PSD) derived from IQ data.

    Parameters
    ----------
    psd_dbm_per_hz : np.ndarray
        Power spectral density in dBm/Hz (length M).
    rbw_hz : float
        Effective resolution bandwidth (bin spacing; ≈ Fs / N or ENBW-adjusted).
    f_start_hz : float
        Absolute start frequency of bin 0.
    vbw_hz : float, optional
        Video bandwidth (if applicable).
    window : str, optional
        Window type used in PSD computation.
    averages : int, default=1
        Number of averages applied during PSD estimation.
    noise_floor_dbm_per_hz : float, optional
        Noise floor estimate.
    metadata : dict, optional
        Additional metadata for downstream processing.

    Attributes
    ----------
    frequencies_hz : np.ndarray
        Frequency axis constructed as `f_start_hz + arange(M) * rbw_hz`.

    Notes
    -----
    - `f_center_hz` can be derived from the computed axis.
    - Bin spacing equals RBW by design.
    """

    psd_dbm_per_hz: np.ndarray  # float64, shape: (M,)
    rbw_hz: float
    f_start_hz: float

    vbw_hz: Optional[float] = None
    window: Optional[str] = None
    averages: int = 1
    noise_floor_dbm_per_hz: Optional[float] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    frequencies_hz: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate PSD data and compute frequency axis."""
        p = _ensure_np_array(self.psd_dbm_per_hz, np.float64)
        object.__setattr__(self, "psd_dbm_per_hz", p)

        if p.ndim != 1:
            raise ValueError("psd_dbm_per_hz must be a 1-D array")
        if p.size == 0:
            raise ValueError("psd_dbm_per_hz must not be empty")
        if not np.all(np.isfinite(p)):
            raise ValueError("psd_dbm_per_hz must be finite")

        if not np.isfinite(self.rbw_hz) or self.rbw_hz <= 0:
            raise ValueError("rbw_hz must be a positive finite float")
        if self.averages < 1:
            raise ValueError("averages must be >= 1")
        if self.vbw_hz is not None and (
            not np.isfinite(self.vbw_hz) or self.vbw_hz <= 0
        ):
            raise ValueError("vbw_hz, when provided, must be a positive finite float")
        if not np.isfinite(self.f_start_hz):
            raise ValueError("f_start_hz must be finite")

        df = self.rbw_hz
        f = self.f_start_hz + df * np.arange(p.size, dtype=np.float64)

        if not np.all(np.isfinite(f)):
            raise ValueError("Computed frequencies_hz contain non-finite values")
        if not np.all(np.diff(f) > 0):
            raise ValueError("Computed frequencies_hz must be strictly increasing")

        object.__setattr__(self, "frequencies_hz", f)

    @property
    def n_bins(self) -> int:
        """Number of frequency bins."""
        return self.frequencies_hz.size

    @property
    def bin_df_hz(self) -> float:
        """Actual bin spacing used to construct the frequency axis."""
        return float(self.rbw_hz)

    @property
    def f_stop_hz(self) -> float:
        """Stop frequency (last bin)."""
        return float(self.frequencies_hz[-1])

    @property
    def f_center_hz(self) -> float:
        """Spectral midpoint based on the computed frequency axis."""
        return 0.5 * (float(self.frequencies_hz[0]) + float(self.frequencies_hz[-1]))

    def slice_band(self, f_low_hz: float, f_high_hz: float) -> SpectrumFrame:
        """Return a band-limited view (copy) within [f_low_hz, f_high_hz].

        Parameters
        ----------
        f_low_hz : float
            Lower frequency bound.
        f_high_hz : float
            Upper frequency bound.

        Returns
        -------
        SpectrumFrame
            A new `SpectrumFrame` object limited to the specified frequency range.

        Raises
        ------
        ValueError
            If `f_low_hz` or `f_high_hz` are invalid or no bins fall within range.
        """
        if (
            not (np.isfinite(f_low_hz) and np.isfinite(f_high_hz))
            or f_low_hz >= f_high_hz
        ):
            raise ValueError("Invalid band limits")

        idx = np.nonzero(
            (self.frequencies_hz >= f_low_hz) & (self.frequencies_hz <= f_high_hz)
        )[0]

        if idx.size == 0:
            raise ValueError("Requested band has no bins in this SpectrumFrame")

        return SpectrumFrame(
            psd_dbm_per_hz=self.psd_dbm_per_hz[idx].copy(),
            rbw_hz=self.rbw_hz,
            f_start_hz=float(self.frequencies_hz[idx[0]]),
            vbw_hz=self.vbw_hz,
            window=self.window,
            averages=self.averages,
            noise_floor_dbm_per_hz=self.noise_floor_dbm_per_hz,
            metadata=dict(self.metadata),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SpectrumFrame):
            return NotImplemented
        return (
            np.allclose(self.psd_dbm_per_hz, other.psd_dbm_per_hz)
            and self.rbw_hz == other.rbw_hz
            and self.f_start_hz == other.f_start_hz
            and self.vbw_hz == other.vbw_hz
            and self.window == other.window
            and self.averages == other.averages
            and self.noise_floor_dbm_per_hz == other.noise_floor_dbm_per_hz
        )
