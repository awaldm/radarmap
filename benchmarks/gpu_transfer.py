import time

import cupy as cp
import numpy as np


def benchmark_transfer():
    data_cpu = np.random.random((900, 900)).astype(np.float32)
    _ = cp.array([1, 2, 3])

    print("--- GPU Transfer Benchmark ---")

    start = time.perf_counter()
    cp.array(data_cpu)
    cp.cuda.Stream.null.synchronize()
    upload_time = time.perf_counter() - start
    print(f"Upload (900x900 float32): {upload_time * 1000:.4f} ms")

    image_gpu = cp.zeros((1024, 1024, 4), dtype=cp.uint8)
    start = time.perf_counter()
    cp.asnumpy(image_gpu)
    cp.cuda.Stream.null.synchronize()
    download_time = time.perf_counter() - start
    print(f"Download (1024x1024 RGBA): {download_time * 1000:.4f} ms")

    print(f"\nTotal Memory Tax: {(upload_time + download_time) * 1000:.4f} ms")


if __name__ == "__main__":
    benchmark_transfer()
