import requests
import time
import numpy as np


while True:
    data = np.random.randn(1024).astype(np.float32)
    pcm = (data * 32767 / 32).astype(np.int16).tobytes()
    requests.post(
        "http://127.0.0.1:8000/audio/stream/",
        data=pcm,
        headers={"Content-Type": "application/octet-stream"},
    )
    time.sleep(10 / 1000)
