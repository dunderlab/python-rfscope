"""Utilities to encode/decode SpectrumFrame payloads to/from base64 JSON.

Round-trip format:
- PSD -> .npy (binary, dtype configurable; defaults to float32) -> zlib -> base64
- Header JSON includes rbw_hz, f_start_hz, vbw_hz, window, averages,
  noise_floor_dbm_per_hz, metadata (JSON-safe), psd_dtype, codec, version.

Notes
-----
- `version` is set to 1 and `codec` is "zlib+npy". Decoding validates these.
- The PSD array is serialized with `numpy.save` and compressed via `zlib`.

Examples
--------
>>> from rfscope.common.models import SpectrumFrame
>>> import numpy as np
>>> sf = SpectrumFrame(
...     psd_dbm_per_hz=np.array([0, -10, -20], dtype=np.float64),
...     rbw_hz=1.0,
...     f_start_hz=100.0,
...     vbw_hz=None,
...     window=None,
...     averages=1,
...     noise_floor_dbm_per_hz=None,
...     metadata={"note": "example"},
... )
>>> s = spectrumframe_to_b64(sf)
>>> sf2 = b64_to_spectrumframe(s)
>>> np.allclose(sf2.psd_dbm_per_hz, sf.psd_dbm_per_hz.astype(sf2.psd_dbm_per_hz.dtype))
True
"""

from __future__ import annotations

import base64
import io
import json
import zlib
from typing import Any, Dict, Mapping, Optional

import numpy as np
from numpy.typing import NDArray

from rfscope.common.models import SpectrumFrame

__all__ = [
    "spectrumframe_to_b64",
    "b64_to_spectrumframe",
    "_metadata_json_safe",
    "_to_json_safe",
]

_CODEC_NAME = "zlib+npy"
_HEADER_VERSION = 1


def spectrumframe_to_b64(
    sf: SpectrumFrame,
    *,
    level: int = 6,
    dtype: np.dtype | type = np.float32,
) -> str:
    """Serialize a ``SpectrumFrame`` to a compact base64 JSON string.

    Parameters
    ----------
    sf
        The input ``SpectrumFrame`` to serialize.
    level
        zlib compression level (0–9). Higher means smaller but slower.
    dtype
        Numpy dtype used to store the PSD in the npy payload. Defaults to
        ``numpy.float32`` to reduce size.

    Returns
    -------
    str
        A JSON string with fields:
        ``{"header": {...}, "data": "<base64-zlib-of-npy>"}``.

    Raises
    ------
    TypeError
        If inputs are not of the expected type or `dtype` is not a floating dtype.
    ValueError
        If `level` is out of range or PSD data cannot be converted to the given dtype.

    Examples
    --------
    >>> s = spectrumframe_to_b64(sf)  # doctest: +SKIP
    >>> isinstance(s, str)
    True

    Unit tests (pytest-style)
    -------------------------
    >>> import json as _json
    >>> _payload = _json.loads(spectrumframe_to_b64(sf))
    >>> assert _payload["header"]["codec"] == "zlib+npy"
    >>> assert _payload["header"]["version"] == 1
    """
    _validate_zlib_level(level)
    np_dtype = np.dtype(dtype)
    _validate_float_dtype(np_dtype)

    psd_array = np.asarray(sf.psd_dbm_per_hz)
    if not np.issubdtype(psd_array.dtype, np.number):
        raise TypeError("sf.psd_dbm_per_hz must be numeric.")

    # Convert PSD to chosen dtype
    try:
        psd_to_store: NDArray[np.floating[Any]] = psd_array.astype(np_dtype, copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cannot cast PSD array to dtype {np_dtype!r}.") from exc

    # 1) PSD -> .npy in-memory
    buf = io.BytesIO()
    np.save(buf, psd_to_store, allow_pickle=False)

    # 2) Compress and base64-encode
    comp = zlib.compress(buf.getvalue(), level)
    b64_psd = base64.b64encode(comp).decode("ascii")

    # 3) Header (JSON-safe)
    header: Dict[str, Any] = {
        "rbw_hz": float(sf.rbw_hz),
        "f_start_hz": float(sf.f_start_hz),
        "vbw_hz": (None if sf.vbw_hz is None else float(sf.vbw_hz)),
        "window": (None if sf.window is None else str(sf.window)),
        "averages": int(sf.averages),
        "noise_floor_dbm_per_hz": (
            None
            if sf.noise_floor_dbm_per_hz is None
            else float(sf.noise_floor_dbm_per_hz)
        ),
        "metadata": _metadata_json_safe(sf.metadata),
        "psd_dtype": str(np_dtype),
        "codec": _CODEC_NAME,
        "version": _HEADER_VERSION,
    }

    payload = {"header": header, "data": b64_psd}
    return json.dumps(payload, separators=(",", ":"))


def b64_to_spectrumframe(s: str) -> SpectrumFrame:
    """Deserialize a base64 JSON string into a new ``SpectrumFrame``.

    Notes
    -----
    The PSD is loaded from the npy payload (stored dtype, often float32).
    Your ``SpectrumFrame`` implementation may normalize to float64 in
    its ``__post_init__`` or validation hooks.

    Parameters
    ----------
    s
        The serialized JSON string produced by :func:`spectrumframe_to_b64`.

    Returns
    -------
    SpectrumFrame
        A new instance reconstructed from the payload.

    Raises
    ------
    ValueError
        If the JSON structure is invalid, the codec or version mismatches,
        or the binary payload cannot be decoded/decompressed/loaded.
    TypeError
        If `s` is not a string.

    Examples
    --------
    >>> s = spectrumframe_to_b64(sf)  # doctest: +SKIP
    >>> sf2 = b64_to_spectrumframe(s)  # doctest: +SKIP
    """
    if not isinstance(s, str):
        raise TypeError("Input `s` must be a JSON string.")

    try:
        payload = json.loads(s)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON; cannot parse SpectrumFrame payload.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid payload; expected JSON object.")

    try:
        header = payload["header"]
        data_b64 = payload["data"]
    except KeyError as exc:
        raise ValueError(
            f"Missing required field in payload: {exc.args[0]!r}."
        ) from exc

    if not isinstance(header, dict):
        raise ValueError("Invalid header; expected object.")
    _validate_header(header)

    # Decode PSD: base64 -> zlib -> npy
    try:
        comp = base64.b64decode(data_b64)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid base64 PSD payload.") from exc

    try:
        raw = zlib.decompress(comp)
    except zlib.error as exc:
        raise ValueError("Invalid zlib-compressed PSD payload.") from exc

    try:
        psd = np.load(io.BytesIO(raw), allow_pickle=False)
    except Exception as exc:  # numpy can raise several errors depending on corruption
        raise ValueError("Invalid npy payload for PSD data.") from exc

    # Reconstruct SpectrumFrame
    return SpectrumFrame(
        psd_dbm_per_hz=psd,
        rbw_hz=header["rbw_hz"],
        f_start_hz=header["f_start_hz"],
        vbw_hz=header.get("vbw_hz"),
        window=header.get("window"),
        averages=header["averages"],
        noise_floor_dbm_per_hz=header.get("noise_floor_dbm_per_hz"),
        metadata=header.get("metadata", {}),
    )


def _metadata_json_safe(md: Mapping[str, Any] | Dict[str, Any]) -> Dict[str, Any]:
    """Ensure ``metadata`` is JSON-safe.

    Attempts a direct ``json.dumps``. If it fails, converts keys to strings
    and values to JSON-safe representations via :func:`_to_json_safe`.

    Parameters
    ----------
    md
        Metadata mapping.

    Returns
    -------
    dict
        JSON-safe dictionary.

    Raises
    ------
    TypeError
        If `md` is not a mapping.
    """
    if not isinstance(md, Mapping):
        raise TypeError("metadata must be a mapping (dict-like).")

    try:
        json.dumps(md)
        # If dumps succeeds, return a plain dict (defensive copy for safety).
        return dict(md)
    except (TypeError, ValueError):
        return {str(k): _to_json_safe(v) for k, v in md.items()}


def _to_json_safe(value: Any) -> Any:
    """Convert arbitrary value to a JSON-safe representation.

    Handles common non-JSON types such as numpy scalars, Paths, datetimes,
    and arbitrary objects by converting to a best-effort representation.

    Parameters
    ----------
    value
        Any value.

    Returns
    -------
    Any
        A JSON-serializable value (str, int, float, bool, None, list, dict).
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # Typical cases: numpy types, Path, datetime, custom objects
        if isinstance(value, np.generic):
            return value.item()
        return str(value)


def _validate_zlib_level(level: int) -> None:
    """Validate zlib compression level."""
    if not isinstance(level, int):
        raise TypeError("Compression level must be an int in [0, 9].")
    if not (0 <= level <= 9):
        raise ValueError("Compression level must be in [0, 9].")


def _validate_float_dtype(dtype: np.dtype) -> None:
    """Validate that dtype is a floating dtype for PSD data."""
    if not np.issubdtype(dtype, np.floating):
        raise TypeError(f"dtype must be a floating dtype; got {dtype!r}.")


def _validate_header(header: Mapping[str, Any]) -> None:
    """Validate header structure, codec, and version."""
    # Required fields and basic types
    required_fields = ("rbw_hz", "f_start_hz", "averages")
    for key in required_fields:
        if key not in header:
            raise ValueError(f"Header missing required field: {key!r}.")

    # Codec and version checks for forward-compat
    codec = header.get("codec")
    version = header.get("version")
    if codec != _CODEC_NAME:
        raise ValueError(f"Unsupported codec {codec!r}; expected {_CODEC_NAME!r}.")
    if version != _HEADER_VERSION:
        raise ValueError(
            f"Unsupported header version {version!r}; expected {_HEADER_VERSION!r}."
        )

    # Optional sanity: types (best-effort; actual model may re-validate)
    _must_be_number(header["rbw_hz"], "rbw_hz")
    _must_be_number(header["f_start_hz"], "f_start_hz")
    _must_be_int_like(header["averages"], "averages")
    for opt_key in ("vbw_hz", "noise_floor_dbm_per_hz"):
        if header.get(opt_key) is not None:
            _must_be_number(header[opt_key], opt_key)


def _must_be_number(v: Any, name: str) -> None:
    if not isinstance(v, (int, float)):
        raise ValueError(f"Header field {name!r} must be a number.")


def _must_be_int_like(v: Any, name: str) -> None:
    if not isinstance(v, (int, np.integer)):
        raise ValueError(f"Header field {name!r} must be an integer.")
