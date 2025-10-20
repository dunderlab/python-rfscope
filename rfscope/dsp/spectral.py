from __future__ import annotations

from typing import Callable, Dict, Optional, TypedDict

from rfscope.common.models import IQFrame
from rfscope.common.utils import FFTSizePlanner, ENBW


class WelchParams(TypedDict):
    """Return type for `plan_welch_parameters`."""
    window: str
    nperseg: int
    noverlap: int
    nfft: int
    scaling: str
    average: str


def plan_welch_parameters(
    rbw_hz: float,
    fs_hz: float,
    bw_hz: float,
    window: str,
    overlap: float,
    K: int,
    size_planner: str = "next_5smooth",
) -> WelchParams:
    """Planifica parámetros de Welch a partir de una RBW objetivo.

    Parameters
    ----------
    rbw_hz : float
        Resolución de banda deseada (Hz).
    fs_hz : float
        Frecuencia de muestreo (Hz).
    bw_hz : float
        Ancho de banda total a cubrir (Hz). Se usa para dimensionar chunking externamente.
    window : {'rect', 'hann', 'hamming', 'blackman'}
        Ventana a emplear. Determina la ENBW.
    overlap : float
        Solapamiento fraccional en [0.0, 1.0).
    K : int
        Número de segmentos (por chunk) en el promedio de Welch.
    size_planner : {'next_pow2', 'next_5smooth'}, default='next_5smooth'
        Estrategia para escoger el tamaño de FFT igual o superior al mínimo.

    Returns
    -------
    WelchParams
        Diccionario con parámetros para `scipy.signal.welch`/equivalente:
        - ``window`` : str
        - ``nperseg`` : int
        - ``noverlap`` : int
        - ``nfft`` : int
        - ``scaling`` : 'density'
        - ``average`` : 'mean'

    Raises
    ------
    ValueError
        Si los parámetros son inválidos o `size_planner` es desconocido.

    Notes
    -----
    El tamaño mínimo de FFT se calcula como::

        nfft_min = ENBW[window] * fs_hz / rbw_hz

    La RBW efectiva resultante será::

        rbw_eff = ENBW[window] * fs_hz / nfft
    """
    if window not in ENBW:
        raise ValueError(f"Unknown window: {window!r}. Options: {sorted(ENBW)}")
    if not (0.0 <= overlap < 1.0):
        raise ValueError("overlap must be in [0.0, 1.0)")
    if not (isinstance(K, int) and K >= 1):
        raise ValueError("K must be an integer >= 1")
    if min(rbw_hz, fs_hz, bw_hz) <= 0:
        raise ValueError("rbw_hz, fs_hz, and bw_hz must be > 0")

    enbw = ENBW[window]

    # Segment sizing from RBW target (respect ENBW)
    nfft_min = enbw * fs_hz / rbw_hz

    # PSS: validamos que el size_planner exista y sea invocable.
    planner: Optional[Callable[[float], int]] = getattr(FFTSizePlanner, size_planner, None)
    if not callable(planner):
        raise ValueError(
            f"Unknown size_planner: {size_planner!r}. "
            f"Choose one of: 'next_pow2', 'next_5smooth'."
        )

    nfft = int(planner(nfft_min))
    nperseg = nfft
    noverlap = int(overlap * nperseg)
    step = nperseg - noverlap
    if step <= 0:
        raise ValueError("nperseg - noverlap must be > 0; reduce overlap")

    return {
        "window": window,
        "nperseg": nperseg,
        "noverlap": noverlap,
        "nfft": nfft,
        "scaling": "density",
        "average": "mean",
    }


def welch_psd(iq: IQFrame) -> None:
    """"""