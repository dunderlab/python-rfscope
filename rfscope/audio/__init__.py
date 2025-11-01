import time
import numpy as np
import logging

from anyio import sleep

from rfscope.crypto.api_requests import signed_request
import base64


def validate_data(data: bytes) -> bool:
    """Validate that the PCM byte buffer is valid before streaming."""
    # Must be bytes or bytearray
    if not isinstance(data, (bytes, bytearray)):
        logging.warning("[validate_data] Invalid type: expected bytes or bytearray")
        return False

    # Must not be empty
    if len(data) == 0:
        logging.warning("[validate_data] Empty payload")
        return False

    # PCM16 must have even length (2 bytes per sample)
    if len(data) % 2 != 0:
        logging.warning(
            f"[validate_data] Invalid PCM length: {len(data)} (must be multiple of 2)"
        )
        return False

    # Optional sanity check: avoid absurdly large payloads
    if len(data) > 10_000_000:  # 10 MB
        logging.warning(f"[validate_data] Payload too large: {len(data)} bytes")
        return False

    return True


def stream(data):
    """Stream PCM16 audio data to backend endpoint."""
    if not validate_data(data):
        return  # invalid data, skip

    response = signed_request(
        "http://127.0.0.1:8000/audio/",
        json_body={"pcm": base64.b64encode(pcm).decode("utf-8")},
        priv_path="~/.ssh/id_ed25519",
        verify_tls=True,
        method="POST",
    )


def generate_tone(freq=443.0, periods=20, sample_rate=44100, amplitude=0.9):
    """Generate a sine wave tone (PCM16) for given frequency and number of periods."""
    duration_s = periods / freq  # tiempo total en segundos
    t = np.arange(0, duration_s, 1 / sample_rate)
    wave = amplitude * np.sin(2 * np.pi * freq * t)
    pcm = (wave * 32767).astype(np.int16).tobytes()
    return pcm


if __name__ == "__main__":

    while True:
        pcm = generate_tone(443.0 / 3)
        try:
            stream(pcm)
        except Exception as e:
            print(e)
            time.sleep(1)
        time.sleep((20 / 443.0) * 1.5)
