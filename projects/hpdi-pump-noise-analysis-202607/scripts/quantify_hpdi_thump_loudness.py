from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile


ROOT = Path(r"C:\Users\admin\Documents\Codex\2026-07-13\yi-j")
BASE = Path(r"C:\FRCloud\FRQ\04_Pump Development\06_HPDI低温泵_加密\03_Testing\02_LNG测试\260709")
OUT = ROOT / "outputs" / "hpdi_thump_loudness_quant"
WORK = ROOT / "work" / "hpdi_thump_loudness_quant"
WAV = WORK / "wav"
PLOTS = OUT / "plots"
for path in (OUT, WORK, WAV, PLOTS):
    path.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def db20(value: np.ndarray | float) -> np.ndarray | float:
    return 20.0 * np.log10(np.asarray(value) + 1e-20)


def db10(value: np.ndarray | float) -> np.ndarray | float:
    return 10.0 * np.log10(np.asarray(value) + 1e-24)


def product_name(path: Path) -> str:
    text = str(path)
    if "东德" in text:
        return "东德竞品"
    if "富瑞" in text:
        return "富瑞自研"
    return "未知"


def speed_value(path: Path) -> int:
    return int(path.parent.name.replace("rpm", ""))


def extract_audio(video: Path) -> Path:
    wav = WAV / f"{product_name(video)}_{video.parent.name}_{video.stem}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "44100", str(wav)],
        check=True,
    )
    return wav


def read_audio(path: Path) -> tuple[int, np.ndarray]:
    fs, x = wavfile.read(path)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    return fs, x - np.mean(x)


def bandpass(fs: int, x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sos = signal.butter(4, [lo, min(hi, fs * 0.49)], btype="bandpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x)


def lowpass(fs: int, x: np.ndarray, hi: float) -> np.ndarray:
    sos = signal.butter(4, hi, btype="lowpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)))


def robust_env(fs: int, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Low/mid impact band: keep mechanical-hydraulic thumps, reject most exhaust hiss.
    thump = bandpass(fs, x, 45, 650)
    # High band used only as contamination indicator, not for loudness.
    hiss = bandpass(fs, x, 1800, 9000)
    env = lowpass(fs, np.abs(signal.hilbert(thump)), 18)
    henv = lowpass(fs, np.abs(signal.hilbert(hiss)), 18)
    t = np.arange(len(x)) / fs
    return t, thump, env, henv


def detect_events(fs: int, env: np.ndarray, henv: np.ndarray) -> np.ndarray:
    env_norm = env / (np.percentile(env, 96) + 1e-20)
    peaks, props = signal.find_peaks(
        env_norm,
        height=max(0.26, np.percentile(env_norm, 70)),
        prominence=0.14,
        distance=int(fs * 0.18),
        width=(int(fs * 0.012), int(fs * 0.55)),
    )
    # Remove obvious broadband exhaust spikes: high-frequency envelope dominates low/mid envelope.
    if len(peaks):
        ratio = henv[peaks] / (env[peaks] + 1e-20)
        keep = ratio < np.percentile(ratio, 85) + 1e-20
        peaks = peaks[keep]
    return peaks


def event_metrics(fs: int, thump: np.ndarray, env: np.ndarray, peaks: np.ndarray) -> list[dict[str, float]]:
    rows = []
    n = len(thump)
    for p in peaks:
        event_a = max(0, p - int(0.06 * fs))
        event_b = min(n, p + int(0.18 * fs))
        # Local background before and after the impulse. This cancels steady bench hum.
        bg1_a = max(0, p - int(0.72 * fs))
        bg1_b = max(0, p - int(0.25 * fs))
        bg2_a = min(n, p + int(0.25 * fs))
        bg2_b = min(n, p + int(0.72 * fs))
        event = thump[event_a:event_b]
        bg = np.concatenate([thump[bg1_a:bg1_b], thump[bg2_a:bg2_b]])
        if len(event) < int(0.04 * fs) or len(bg) < int(0.08 * fs):
            continue
        event_rms = rms(event)
        bg_rms = rms(bg)
        event_power = event_rms * event_rms
        bg_power = bg_rms * bg_rms
        excess_power = max(event_power - bg_power, event_power * 0.03)
        rows.append(
            {
                "time_s": p / fs,
                "event_rms_dbfs": float(db20(event_rms)),
                "bg_rms_dbfs": float(db20(bg_rms)),
                "excess_dbfs": float(db10(excess_power)),
                "prominence_db": float(db10((event_power + 1e-24) / (bg_power + 1e-24))),
                "env_peak_db": float(db20(env[p])),
            }
        )
    return rows


def summarize(events: list[dict[str, float]]) -> dict[str, float | int]:
    if not events:
        return {
            "event_count": 0,
            "typical_p50_dbfs": np.nan,
            "loud_p90_dbfs": np.nan,
            "loud_p95_dbfs": np.nan,
            "max_dbfs": np.nan,
            "typical_prominence_db": np.nan,
            "loud_prominence_p90_db": np.nan,
        }
    vals = np.array([e["excess_dbfs"] for e in events], dtype=float)
    prom = np.array([e["prominence_db"] for e in events], dtype=float)
    return {
        "event_count": int(len(events)),
        "typical_p50_dbfs": float(np.percentile(vals, 50)),
        "loud_p90_dbfs": float(np.percentile(vals, 90)),
        "loud_p95_dbfs": float(np.percentile(vals, 95)),
        "max_dbfs": float(np.max(vals)),
        "typical_prominence_db": float(np.percentile(prom, 50)),
        "loud_prominence_p90_db": float(np.percentile(prom, 90)),
    }


def analyze_video(video: Path) -> tuple[dict[str, object], list[dict[str, float]]]:
    wav = extract_audio(video)
    fs, x = read_audio(wav)
    t, thump, env, henv = robust_env(fs, x)
    peaks = detect_events(fs, env, henv)
    events = event_metrics(fs, thump, env, peaks)
    summary = summarize(events)
    summary.update(
        {
            "product": product_name(video),
            "speed_rpm": speed_value(video),
            "video": str(video),
            "duration_s": len(x) / fs,
            "overall_low_mid_rms_dbfs": float(db20(rms(thump))),
            "overall_hiss_rms_dbfs": float(db20(rms(bandpass(fs, x, 1800, 9000)))),
        }
    )
    # Per-video QC plot.
    env_rs_t = t[:: max(1, fs // 300)]
    env_rs = env[:: max(1, fs // 300)]
    fig, axes = plt.subplots(2, 1, figsize=(13, 5), sharex=True)
    axes[0].plot(t, thump, linewidth=0.22, color="#64748B")
    axes[0].scatter([e["time_s"] for e in events], np.interp([e["time_s"] for e in events], t, thump), s=8, color="#DC2626")
    axes[0].set_ylabel("45-650Hz")
    axes[0].set_title(f"{summary['product']} {summary['speed_rpm']}rpm 咚声响度事件检测")
    axes[1].plot(env_rs_t, db20(env_rs), linewidth=0.6, color="#059669")
    axes[1].scatter([e["time_s"] for e in events], [e["env_peak_db"] for e in events], s=8, color="#DC2626")
    axes[1].set_ylabel("包络 dBFS")
    axes[1].set_xlabel("时间 (s)")
    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(PLOTS / f"{summary['product']}_{summary['speed_rpm']}rpm_咚声响度检测.png", dpi=160)
    plt.close(fig)
    return summary, events


def main() -> None:
    videos = sorted(BASE.glob("*/*rpm/*.mp4"), key=lambda p: (product_name(p), speed_value(p)))
    summaries = []
    all_events = []
    for video in videos:
        summary, events = analyze_video(video)
        summaries.append(summary)
        for e in events:
            row = {
                "product": summary["product"],
                "speed_rpm": summary["speed_rpm"],
                "video": str(video),
                **e,
            }
            all_events.append(row)

    # Matched-speed comparison: positive delta means FuRui is louder than competitor.
    by_speed: dict[int, dict[str, dict[str, object]]] = {}
    for s in summaries:
        by_speed.setdefault(int(s["speed_rpm"]), {})[str(s["product"])] = s
    comparisons = []
    for speed, group in sorted(by_speed.items()):
        if "富瑞自研" not in group or "东德竞品" not in group:
            continue
        fr = group["富瑞自研"]
        dd = group["东德竞品"]
        comparisons.append(
            {
                "speed_rpm": speed,
                "fu_typical_p50_dbfs": fr["typical_p50_dbfs"],
                "dd_typical_p50_dbfs": dd["typical_p50_dbfs"],
                "fu_minus_dd_typical_db": float(fr["typical_p50_dbfs"] - dd["typical_p50_dbfs"]),
                "fu_loud_p90_dbfs": fr["loud_p90_dbfs"],
                "dd_loud_p90_dbfs": dd["loud_p90_dbfs"],
                "fu_minus_dd_p90_db": float(fr["loud_p90_dbfs"] - dd["loud_p90_dbfs"]),
                "fu_p95_dbfs": fr["loud_p95_dbfs"],
                "dd_p95_dbfs": dd["loud_p95_dbfs"],
                "fu_minus_dd_p95_db": float(fr["loud_p95_dbfs"] - dd["loud_p95_dbfs"]),
            }
        )

    def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        keys = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(OUT / "thump_loudness_summary.csv", summaries)
    write_csv(OUT / "thump_event_details.csv", all_events)
    write_csv(OUT / "matched_speed_comparison.csv", comparisons)

    # Plot: absolute thump loudness and FuRui-minus-competitor deltas.
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for product, marker in [("东德竞品", "s"), ("富瑞自研", "o")]:
        rows = sorted([s for s in summaries if s["product"] == product], key=lambda r: int(r["speed_rpm"]))
        x = [int(r["speed_rpm"]) for r in rows]
        axes[0, 0].plot(x, [r["typical_p50_dbfs"] for r in rows], marker=marker, label=product)
        axes[0, 1].plot(x, [r["loud_p90_dbfs"] for r in rows], marker=marker, label=product)
        axes[1, 0].plot(x, [r["loud_p95_dbfs"] for r in rows], marker=marker, label=product)
        axes[1, 1].plot(x, [r["typical_prominence_db"] for r in rows], marker=marker, label=product)
    axes[0, 0].set_title("典型咚声响度 P50 (越低越好)")
    axes[0, 1].set_title("较响咚声响度 P90 (越低越好)")
    axes[1, 0].set_title("高响度咚声 P95 (越低越好)")
    axes[1, 1].set_title("相对背景突出量 P50 (越低越不突兀)")
    for ax in axes.ravel():
        ax.set_xlabel("转速 rpm")
        ax.set_ylabel("dB")
        ax.grid(True, alpha=0.25)
        ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "竞品_vs_富瑞_咚声响度绝对指标.png", dpi=180)
    plt.close(fig)

    if comparisons:
        speeds = [c["speed_rpm"] for c in comparisons]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.axhline(0, color="#111827", linewidth=0.8)
        ax.plot(speeds, [c["fu_minus_dd_typical_db"] for c in comparisons], marker="o", label="P50 差值")
        ax.plot(speeds, [c["fu_minus_dd_p90_db"] for c in comparisons], marker="o", label="P90 差值")
        ax.plot(speeds, [c["fu_minus_dd_p95_db"] for c in comparisons], marker="o", label="P95 差值")
        ax.set_title("富瑞 - 东德 咚声响度差值（>0 表示富瑞更响）")
        ax.set_xlabel("转速 rpm")
        ax.set_ylabel("dB")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(PLOTS / "富瑞相对竞品咚声响度差值.png", dpi=180)
        plt.close(fig)

    # Text summary for quick reading.
    lines = [
        "# HPDI咚声响度量化说明",
        "",
        "指标口径：45-650 Hz低中频冲击带，事件窗口扣除前后局部背景，尽量排除台架稳态嗡声；高频排气尖声仅作为污染筛选，不参与咚声响度计算。",
        "同一手机、同一位置下，dBFS可用于相对比较。数值越低代表咚声越小；富瑞-东德差值大于0代表富瑞更响。",
        "",
        "## 匹配转速差值",
    ]
    for c in comparisons:
        lines.append(
            f"- {c['speed_rpm']} rpm: P50差值 {c['fu_minus_dd_typical_db']:.2f} dB, "
            f"P90差值 {c['fu_minus_dd_p90_db']:.2f} dB, P95差值 {c['fu_minus_dd_p95_db']:.2f} dB"
        )
    (OUT / "analysis_notes.md").write_text("\n".join(lines), encoding="utf-8")

    print(OUT / "thump_loudness_summary.csv")
    print(OUT / "matched_speed_comparison.csv")


if __name__ == "__main__":
    main()
