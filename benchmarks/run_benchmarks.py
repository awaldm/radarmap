import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
TILE = (5, 16, 11)
SIZES = [256, 512, 1024, 2048]
RENDERERS = ["numpy", "numba"]
INTERPOLATIONS = ["nearest", "bilinear"]
PRODUCT = "RS"
SAMPLES = 5
WARMUP_REQUESTS = 2


def get_latest_timestamp():
    url = f"{BASE_URL}/api/radvor/timestamps?product={PRODUCT}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()[0]


def run_request(size, renderer, interp, ts, mode):
    z, x, y = TILE
    url = (
        f"{BASE_URL}/api/tiles/{z}/{x}/{y}.png"
        f"?timestamp={ts}&product={PRODUCT}&size={size}"
        f"&renderer={renderer}&interpolation={interp}&mode={mode}"
    )
    start = time.perf_counter()
    resp = requests.get(url)
    resp.raise_for_status()
    return time.perf_counter() - start


def warm_paths(ts):
    print("Warming renderer paths before timed sweep.")
    for renderer in RENDERERS:
        for interp in INTERPOLATIONS:
            for _ in range(WARMUP_REQUESTS):
                run_request(256, renderer, interp, ts, "benchmark_warmup")


def conduct_sweep():
    ts = get_latest_timestamp()
    print(f"Starting systematic sweep. Product: {PRODUCT} | Timestamp: {ts}")

    results = []
    warm_paths(ts)

    for renderer in RENDERERS:
        print(f"\n--- Benchmarking {renderer.upper()} Path ---")

        for size in SIZES:
            for interp in INTERPOLATIONS:
                latencies = []
                print(f"  Benchmarking Size={size} | Interp={interp}...", end=" ", flush=True)

                for _i in range(SAMPLES):
                    lat = run_request(size, renderer, interp, ts, "benchmark_sequential")
                    latencies.append(lat)

                avg_latency = sum(latencies) / len(latencies)
                print(f"{avg_latency * 1000:.2f}ms")

                results.append(
                    {
                        "size": size,
                        "renderer": renderer,
                        "interpolation": interp,
                        "latency_ms": round(avg_latency * 1000, 2),
                    }
                )

    # Save data
    results_path = REPO_ROOT / "benchmarks" / "benchmark_results.csv"
    pd.DataFrame(results).to_csv(results_path, index=False)
    return pd.DataFrame(results)


def plot_results(df):
    image_dir = REPO_ROOT / "docs" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    # 1. LATENCY SCALING
    plt.figure(figsize=(10, 6))
    for renderer in RENDERERS:
        for interp in INTERPOLATIONS:
            subset = df[(df["renderer"] == renderer) & (df["interpolation"] == interp)]
            lbl = f"{renderer} ({interp})"
            plt.plot(subset["size"], subset["latency_ms"], marker="o", label=lbl)

    plt.title("Scaling Performance: CPU vs GPU (Fully Warmed Up)")
    plt.xlabel("Tile Size (Pixels)")
    plt.ylabel("Latency (ms)")
    plt.yscale("log")
    plt.grid(True, which="both", ls="-", alpha=0.3)
    plt.legend()
    plt.savefig(image_dir / "bench_latency_scaling.png")

    # 2. SPEEDUP FACTOR (Nearest)
    plt.figure(figsize=(10, 6))
    nearest_df = df[df["interpolation"] == "nearest"]
    speedups = []
    for s in SIZES:
        cpu = nearest_df[(nearest_df["size"] == s) & (nearest_df["renderer"] == "numpy")][
            "latency_ms"
        ].values[0]
        gpu = nearest_df[(nearest_df["size"] == s) & (nearest_df["renderer"] == "numba")][
            "latency_ms"
        ].values[0]
        speedups.append(cpu / gpu)

    plt.bar([str(s) for s in SIZES], speedups, color="skyblue")
    plt.title("GPU Speedup Factor (Nearest Neighbor)")
    plt.ylabel("Speedup (x-fold)")
    plt.savefig(image_dir / "bench_gpu_speedup.png")

    print("\nGraphs updated in docs/images/")


if __name__ == "__main__":
    try:
        data = conduct_sweep()
        plot_results(data)
    except Exception as e:
        print(f"\nBenchmark Failed: {e}")
