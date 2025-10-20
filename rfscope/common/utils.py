"""Utility helpers for FFT sizing and capture planning."""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional, TypedDict


ENBW: Dict[str, float] = {
    "rect": 1.00,
    "hann": 1.50,
    "hamming": 1.36,
    "blackman": 1.73,
}


class CapturePlan(TypedDict):
    """Return type for `plan_capture_parameters`."""
    sample_rate: float
    samples: int
    rbw_eff: float
    time: float


class FFTSizePlanner:
    """Helpers to choose FFT sizes.

    Notes
    -----
    - `next_pow2` returns the smallest power-of-two `>= n_min` (with a minimum of 2).
    - `next_5smooth` returns the smallest 5-smooth (a.k.a. Hamming number)
      `>= n_min`, where `n = 2**a * 3**b * 5**c`.
    """

    @classmethod
    def next_pow2(cls, n_min: float) -> int:
        """Return the next power-of-two size >= `n_min`.

        Parameters
        ----------
        n_min : float
            Minimum desired FFT size (must be positive).

        Returns
        -------
        int
            Power-of-two size, at least 2.

        Examples
        --------
        >>> FFTSizePlanner.next_pow2(1000)
        1024
        """
        if not (isinstance(n_min, (int, float)) and n_min > 0):
            raise ValueError("n_min must be a positive number")
        return 1 << math.ceil(math.log2(max(2.0, float(n_min))))

    @classmethod
    def next_5smooth(cls, n_min: float) -> int:
        """Return the smallest 5-smooth number (2**a * 3**b * 5**c) >= `n_min`.

        Parameters
        ----------
        n_min : float
            Minimum desired size. Will be ceiled to an integer and clamped to >= 1.

        Returns
        -------
        int
            A 5-smooth (Hamming) number.

        Notes
        -----
        This brute-force search is fast for practical sizes because the number
        of combinations is small. For extremely large `n_min`, consider a more
        specialized generator.

        Examples
        --------
        >>> FFTSizePlanner.next_5smooth(1000)
        1024
        >>> FFTSizePlanner.next_5smooth(4097)
        4320

        """
        # PSS: Broadened `n_min` to float and normalized via ceil+clamp so callers
        #      can pass non-integers (the module already passed a float).
        if not (isinstance(n_min, (int, float)) and n_min > 0):
            raise ValueError("n_min must be a positive number")

        n_target = max(1, int(math.ceil(float(n_min))))

        # Upper bounds for exponents (loose but safe).
        # Adding +2 headroom ensures we don't miss the next higher combination.
        max_exp2 = int(math.log(n_target, 2)) + 2
        max_exp3 = int(math.log(n_target, 3)) + 2
        max_exp5 = int(math.log(n_target, 5)) + 2

        best: Optional[int] = None
        for a in range(max_exp2 + 1):
            pow2 = 2**a
            if best is not None and pow2 > best:
                break
            for b in range(max_exp3 + 1):
                pow3 = pow2 * (3**b)
                if best is not None and pow3 > best:
                    break
                for c in range(max_exp5 + 1):
                    n = pow3 * (5**c)
                    if n >= n_target and (best is None or n < best):
                        best = n

        # This should never be None due to bounds; still assert to be safe.
        assert best is not None
        return best


def plan_capture_parameters(
    rbw_hz: float,
    fs_hz: float,
    bw_hz: float,
    window: str,
    overlap: float,
    K: int,
    size_planner: str = "next_5smooth",
) -> CapturePlan:
    """Plan PSD capture parameters for a Welch estimate.

    Parameters
    ----------
    rbw_hz : float
        Target resolution bandwidth in Hz.
    fs_hz : float
        Sample rate in Hz.
    bw_hz : float
        Total RF bandwidth to cover (via chunking if `bw_hz > fs_hz`).
    window : {'rect', 'hann', 'hamming', 'blackman'}
        Window type. Determines ENBW.
    overlap : float
        Fractional overlap in [0.0, 1.0).
    K : int
        Number of Welch segments (per chunk) to average.
    size_planner : {'next_pow2', 'next_5smooth'}, default='next_5smooth'
        Strategy to choose FFT size at or above the minimum required by RBW.

    Returns
    -------
    CapturePlan
        Dictionary-like structure with:
        - ``sample_rate`` : float
        - ``samples`` : int
        - ``rbw_eff`` : float
        - ``time`` : float

    Raises
    ------
    ValueError
        If inputs are invalid or `size_planner` is unknown.

    Notes
    -----
    - The minimum FFT size is computed from the target RBW as
      ``nfft_min = ENBW[window] * fs_hz / rbw_hz``.
    - Effective RBW is ``rbw_eff = ENBW[window] * fs_hz / nfft``.
    - Samples per chunk follow Welch with overlap:
      ``samples_per_chunk = nperseg + (K - 1) * (nperseg - noverlap)``.

    Examples
    --------
    >>> plan = plan_capture_parameters(
    ...     rbw_hz=1_000.0, fs_hz=2_000_000.0, bw_hz=20_000_000.0,
    ...     window='hann', overlap=0.5, K=8, size_planner='next_5smooth'
    ... )
    >>> round(plan['rbw_eff'], 2) >= 1000.0
    True
    """
    if window not in ENBW:
        raise ValueError(f"Unknown window: {window!r}. Options: {sorted(ENBW)}")
    if not (0.0 <= overlap < 1.0):
        raise ValueError("overlap must be in [0.0, 1.0)")
    if not (isinstance(K, int) and K >= 1):
        raise ValueError("K must be an integer >= 1")
    if min(rbw_hz, fs_hz, bw_hz) <= 0:
        raise ValueError("rbw_hz, fs_hz, and bw_hz must be > 0")

    # PSS: Validate `size_planner` early and require callable attribute on FFTSizePlanner.
    planner: Optional[Callable[[float], int]] = getattr(FFTSizePlanner, size_planner, None)
    if not callable(planner):
        raise ValueError(
            f"Unknown size_planner: {size_planner!r}. "
            f"Choose one of: 'next_pow2', 'next_5smooth'."
        )

    enbw = ENBW[window]

    # Segment sizing from target RBW (respect ENBW).
    nfft_min = enbw * fs_hz / rbw_hz

    nfft = int(planner(nfft_min))
    if nfft <= 0:
        # Defensive check—should not happen with our planners.
        raise ValueError("computed nfft must be positive")

    nperseg = nfft
    noverlap = int(overlap * nperseg)
    step = nperseg - noverlap
    if step <= 0:
        raise ValueError("nperseg - noverlap must be > 0; reduce overlap")

    # Effective RBW and segment duration
    rbw_eff = enbw * fs_hz / nfft

    # Welch sample requirement per chunk (K segments with overlap)
    samples_per_chunk = nperseg + (K - 1) * step
    time_per_chunk = samples_per_chunk / fs_hz

    # Chunks to cover BW with instantaneous fs (wideband if chunks==1)
    chunks = max(1, math.ceil(bw_hz / fs_hz))
    total_samples = int(chunks * samples_per_chunk)
    total_time = float(chunks * time_per_chunk)

    return {
        "sample_rate": float(fs_hz),
        "samples": total_samples,
        "rbw_eff": float(rbw_eff),
        "time": total_time,
    }