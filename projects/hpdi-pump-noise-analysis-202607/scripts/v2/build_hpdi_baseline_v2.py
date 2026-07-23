from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile


ROOT = Path(__file__).resolve().parents[1]
WAV_DIR = ROOT / "work" / "hpdi_thump_loudness_quant" / "wav"
OUT = ROOT / "outputs" / "hpdi_baseline_v2"
PLOTS = OUT / "plots"
OUT.mkdir(parents=True, exist_ok=True)
PLOTS.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# Read manually from the visible AR824 display in the FuRui 1000 rpm video.
METER_OBSERVATIONS = [
    (5.0, 93.9),
    (15.0, 94.5),
    (30.0, 93.3),
    (45.0, 95.3),
    (60.0, 93.8),
    (70.0, 90.3),
]


@dataclass
class Recording:
    product: str
    speed_rpm: int
    path: Path


def db20(x: np.ndarray | float) -> np.ndarray | float:
    return 20.0 * np.log10(np.maximum(np.asarray(x), 1e-20))


def read_wav(path: Path) -> tuple[int, np.ndarray]:
    fs, x = wavfile.read(path)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    return fs, x - np.mean(x)


def bandpass(fs: int, x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sos = signal.butter(4, [lo, min(hi, fs * 0.48)], btype="bandpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x)


def a_weight(fs: int, x: np.ndarray) -> np.ndarray:
    # IEC 61672 analog A-weighting approximation transformed to the sampled domain.
    f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
    num = [(2 * np.pi * f4) ** 2 * 10 ** (1.9997 / 20), 0, 0, 0, 0]
    den = np.polymul([1, 4 * np.pi * f4, (2 * np.pi * f4) ** 2], [1, 4 * np.pi * f1, (2 * np.pi * f1) ** 2])
    den = np.polymul(np.polymul(den, [1, 2 * np.pi * f3]), [1, 2 * np.pi * f2])
    b, a = signal.bilinear(num, den, fs)
    return signal.lfilter(b, a, x)


def frame_rms(x: np.ndarray, fs: int, window_s: float = 0.080, hop_s: float = 0.020) -> tuple[np.ndarray, np.ndarray]:
    win = max(1, int(window_s * fs))
    hop = max(1, int(hop_s * fs))
    power = signal.convolve(x * x, np.ones(win) / win, mode="same", method="fft")
    idx = np.arange(win // 2, len(x) - win // 2, hop)
    return idx / fs, np.sqrt(np.maximum(power[idx], 1e-24))


def product_and_speed(path: Path) -> Recording:
    name = path.stem
    product = "东德基准" if "东德" in name else "富瑞初始"
    speed = int(name.split("rpm")[0].split("_")[-1])
    return Recording(product, speed, path)


def calibrate() -> dict[str, object]:
    target = next(p for p in WAV_DIR.glob("*.wav") if "富瑞" in p.name and "1000rpm" in p.name)
    fs, x = read_wav(target)
    xa = a_weight(fs, x)
    times = np.array([t for t, _ in METER_OBSERVATIONS])
    meter = np.array([v for _, v in METER_OBSERVATIONS])
    candidates = []
    for weighting, window_s in [("FAST候选", 0.125), ("SLOW候选", 1.0)]:
        phone = []
        for t in times:
            a = max(0, int((t - window_s) * fs))
            b = min(len(xa), int(t * fs))
            phone.append(float(db20(np.sqrt(np.mean(xa[a:b] ** 2)))))
        phone = np.array(phone)
        offsets = meter - phone
        candidates.append(
            {
                "weighting": weighting,
                "window_s": window_s,
                "phone_dbfs": phone.tolist(),
                "offsets_db": offsets.tolist(),
                "offset_db": float(np.median(offsets)),
                "residual_mae_db": float(np.median(np.abs(offsets - np.median(offsets)))),
                "correlation": float(np.corrcoef(phone, meter)[0, 1]),
            }
        )
    # Select by residual consistency; the absolute offset remains an engineering estimate.
    selected = min(candidates, key=lambda row: row["residual_mae_db"])
    return {
        "meter_unit": "dBA",
        "meter_model": "Smart Sensor AR824",
        "observations": [{"time_s": t, "meter_dba": v} for t, v in METER_OBSERVATIONS],
        "candidates": candidates,
        "selected": selected,
        "estimated_uncertainty_db": max(2.0, float(selected["residual_mae_db"]) + 1.0),
    }


def rolling_quantile(values: np.ndarray, width: int, q: float) -> np.ndarray:
    # scipy's order filter keeps this computation dependency-light and deterministic.
    width = max(3, width | 1)
    rank = int(round(q * (width - 1)))
    return signal.order_filter(values, np.ones(width), rank)


def analyze_recording(rec: Recording, offset_db: float) -> tuple[dict[str, object], list[dict[str, object]], dict[str, np.ndarray]]:
    fs, x = read_wav(rec.path)
    thump = a_weight(fs, bandpass(fs, x, 45, 650))
    hiss = bandpass(fs, x, 1800, 9000)
    t, thump_rms = frame_rms(thump, fs)
    _, hiss_rms = frame_rms(hiss, fs)
    env_dbfs = db20(thump_rms)
    hiss_dbfs = db20(hiss_rms)

    # Local 3 s low quantile represents steady bench/background energy.
    hop_s = float(np.median(np.diff(t)))
    bg = rolling_quantile(thump_rms, int(3.0 / hop_s), 0.20)
    excess_rms = np.sqrt(np.maximum(thump_rms**2 - bg**2, (10 ** (-90 / 20)) ** 2))
    clean_dba = db20(excess_rms) + offset_db

    # Hiss masks identify periods dominated by sharp exhaust noise. These samples are not used for event statistics.
    ratio_db = hiss_dbfs - env_dbfs
    hiss_threshold = max(float(np.percentile(ratio_db, 90)), 10.0)
    exhaust_mask = ratio_db >= hiss_threshold

    smooth = signal.savgol_filter(env_dbfs, min(21, len(env_dbfs) // 2 * 2 - 1), 3)
    min_distance = max(1, int(0.18 / hop_s))
    peaks, _ = signal.find_peaks(
        smooth,
        prominence=max(1.5, float(np.percentile(smooth, 75) - np.percentile(smooth, 45)) * 0.35),
        distance=min_distance,
        height=float(np.percentile(smooth, 55)),
    )
    peaks = peaks[~exhaust_mask[peaks]]

    series_id = ("DD_BASE_260707" if rec.product == "东德基准" else "FR_INIT_260709") + f"_{rec.speed_rpm}"
    events = []
    for i, p in enumerate(peaks):
        event_level = float(clean_dba[p])
        if event_level < 20:
            continue
        center = int(t[p] * fs)
        event_a = max(0, center - int(0.06 * fs))
        event_b = min(len(thump), center + int(0.18 * fs))
        bg_a1 = max(0, center - int(0.72 * fs))
        bg_b1 = max(0, center - int(0.25 * fs))
        bg_a2 = min(len(thump), center + int(0.25 * fs))
        bg_b2 = min(len(thump), center + int(0.72 * fs))
        event_power = float(np.mean(thump[event_a:event_b] ** 2))
        bg_parts = np.concatenate([thump[bg_a1:bg_b1], thump[bg_a2:bg_b2]])
        bg_power = float(np.mean(bg_parts**2)) if len(bg_parts) else 0.0
        source_energy = np.sqrt(max(event_power - bg_power, event_power * 0.03))
        events.append(
            {
                "product": rec.product,
                "series_id": series_id,
                "speed_rpm": rec.speed_rpm,
                "event_index": len(events) + 1,
                "time_s": float(t[p]),
                "thump_level_est_dba": event_level,
                "event_energy_est_dba": float(db20(source_energy) + offset_db),
                "raw_peak_est_dba": float(env_dbfs[p] + offset_db),
                "raw_low_band_dbfs": float(env_dbfs[p]),
                "local_background_est_dba": float(db20(bg[p]) + offset_db),
                "exhaust_ratio_db": float(ratio_db[p]),
                "wav": str(rec.path),
            }
        )

    levels = np.array([e["thump_level_est_dba"] for e in events])
    energies = np.array([e["event_energy_est_dba"] for e in events])
    summary = {
        "series_id": series_id,
        "test_id": "DD_BASELINE_260707" if rec.product == "东德基准" else "FR_INITIAL_260709",
        "product": rec.product,
        "speed_rpm": rec.speed_rpm,
        "duration_s": len(x) / fs,
        "event_count": len(events),
        "p50_est_dba": float(np.percentile(levels, 50)) if len(levels) else np.nan,
        "p90_est_dba": float(np.percentile(levels, 90)) if len(levels) else np.nan,
        "p95_est_dba": float(np.percentile(levels, 95)) if len(levels) else np.nan,
        "common_event_energy_est_dba": float(np.percentile(energies, 50)) if len(energies) else np.nan,
        "loud_event_energy_est_dba": float(np.percentile(energies, 90)) if len(energies) else np.nan,
        "exhaust_mask_share_pct": float(100 * np.mean(exhaust_mask)),
        "calibration_offset_db": offset_db,
        "wav": str(rec.path),
    }
    arrays = {
        "t": t,
        "clean_dba": clean_dba,
        "raw_dba": env_dbfs + offset_db,
        "background_dba": db20(bg) + offset_db,
        "exhaust_mask": exhaust_mask,
        "event_t": np.array([e["time_s"] for e in events]),
        "event_level": levels,
    }
    return summary, events, arrays


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def status(delta: float) -> str:
    if delta > 2:
        return "明显差于东德"
    if delta > 0:
        return "略差/接近"
    if delta >= -2:
        return "优于东德"
    return "明显优于东德"


def customer_delta(delta: float | None) -> tuple[str, float | None, str]:
    if delta is None:
        return "无同转速基准", None, "无同转速基准"
    if abs(delta) < 0.05:
        return "东德基准", 0.0, "基准"
    direction = "低于东德" if delta < 0 else "高于东德"
    return direction, abs(delta), f"{direction} {abs(delta):.1f} dB"


def confidence_label(primary_delta: float, peak_delta: float) -> str:
    if abs(primary_delta) <= 1.0 and abs(peak_delta) <= 1.0:
        return "接近基准"
    if np.sign(primary_delta) == np.sign(peak_delta):
        return "方向一致"
    return "两种算法方向不一致，建议复测"


def plot_calibration(cal: dict[str, object]) -> None:
    sel = cal["selected"]
    meter = np.array([v for _, v in METER_OBSERVATIONS])
    phone_est = np.array(sel["phone_dbfs"]) + float(sel["offset_db"])
    times = np.array([t for t, _ in METER_OBSERVATIONS])
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.plot(times, meter, "o-", color="#111827", label="分贝仪画面读数")
    ax.plot(times, phone_est, "s--", color="#007C91", label="手机录音校准后")
    ax.set(xlabel="视频时间 (s)", ylabel="声级 dB(A)", title="分贝仪与手机录音校准核对")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "01_分贝仪校准核对.png", dpi=180)
    plt.close(fig)


def plot_envelopes(results: dict[tuple[str, int], dict[str, np.ndarray]]) -> None:
    speeds = [700, 800, 900]
    fig, axes = plt.subplots(len(speeds), 2, figsize=(12, 8.5), sharey=True)
    for row, speed in enumerate(speeds):
        for col, product in enumerate(["东德基准", "富瑞初始"]):
            ax = axes[row, col]
            arr = results[(product, speed)]
            x = arr["event_t"]
            y = arr["event_level"]
            color = "#007C91" if product == "东德基准" else "#C2410C"
            ax.scatter(x, y, s=15, color=color, alpha=0.75, label="单次咚声")
            if len(y) >= 5:
                trend = np.convolve(y, np.ones(5) / 5, mode="valid")
                ax.plot(x[2:-2], trend, lw=2.0, color="#111827", label="连续5次趋势")
            ax.set_ylim(50, 95)
            ax.grid(alpha=0.2)
            ax.set_title(f"{speed} rpm  {product}", fontsize=10)
            if col == 0:
                ax.set_ylabel("泵咚声估算 dB(A)")
            if row == len(speeds) - 1:
                ax.set_xlabel("时间 (s)")
    axes[0, 0].legend(fontsize=8, loc="upper right")
    fig.suptitle("干扰抑制后的咚声趋势（每个点为一次咚声，黑线显示连续周期变化）", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(PLOTS / "02_同转速包络直观对比.png", dpi=180)
    plt.close(fig)


def representative_curve(arr: dict[str, np.ndarray], percentile: float) -> tuple[np.ndarray, np.ndarray]:
    target = float(np.percentile(arr["event_level"], percentile))
    i = int(np.argmin(np.abs(arr["event_level"] - target)))
    center = float(arr["event_t"][i])
    t = arr["t"]
    keep = (t >= center - 0.30) & (t <= center + 0.45)
    return t[keep] - center, arr["raw_dba"][keep]


def plot_representatives(results: dict[tuple[str, int], dict[str, np.ndarray]]) -> None:
    speeds = [700, 800, 900]
    fig, axes = plt.subplots(2, len(speeds), figsize=(12, 6.5), sharex=True, sharey=True)
    for col, speed in enumerate(speeds):
        for row, (pct, label) in enumerate([(50, "常见咚声"), (90, "较响咚声")]):
            ax = axes[row, col]
            for product, color in [("东德基准", "#007C91"), ("富瑞初始", "#C2410C")]:
                x, y = representative_curve(results[(product, speed)], pct)
                ax.plot(1000 * x, y, lw=1.5, color=color, label=product)
            ax.axvline(0, color="#64748B", lw=0.7)
            ax.grid(alpha=0.22)
            ax.set_title(f"{speed} rpm  {label}", fontsize=10)
            if col == 0:
                ax.set_ylabel("泵咚声估算 dB(A)")
            if row == 1:
                ax.set_xlabel("相对咚声峰值时间 (ms)")
    axes[0, 0].legend(loc="upper right")
    fig.suptitle("代表性单次咚声叠加对比（保留实际声级差异）", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(PLOTS / "03_大小咚代表事件叠加.png", dpi=180)
    plt.close(fig)


def plot_scorecard(comparisons: list[dict[str, object]]) -> None:
    speeds = [int(r["speed_rpm"]) for r in comparisons]
    p50_signed = [float(r["common_thump_delta_db"]) for r in comparisons]
    p90_signed = [float(r["loud_thump_delta_db"]) for r in comparisons]
    p50 = [abs(v) for v in p50_signed]
    p90 = [abs(v) for v in p90_signed]
    x = np.arange(len(speeds))
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    width = 0.36
    bars1 = axes[0].bar(x - width / 2, p50, width, color=["#15803D" if v < 0 else "#C2410C" for v in p50_signed], label="常见咚声")
    bars2 = axes[0].bar(x + width / 2, p90, width, color=["#4ADE80" if v < 0 else "#FB923C" for v in p90_signed], label="较响咚声")
    for bars, signed in [(bars1, p50_signed), (bars2, p90_signed)]:
        for bar, value in zip(bars, signed):
            axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.18, "低" if value < 0 else "高", ha="center", va="bottom", fontsize=8)
    axes[0].set_xticks(x, speeds)
    axes[0].set(xlabel="转速 (rpm)", ylabel="差值大小 (dB)", title="富瑞相对东德：绿=更低，橙=更高")
    axes[0].grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    share = [float(r["fu_events_above_dd_p90_pct"]) for r in comparisons]
    axes[1].bar(x, share, color=["#C2410C" if v > 15 else "#D97706" if v > 10 else "#15803D" for v in share])
    axes[1].axhline(10, color="#111827", lw=0.8, ls="--", label="东德基准约10%")
    axes[1].set_xticks(x, speeds)
    axes[1].set(xlabel="转速 (rpm)", ylabel="富瑞事件占比 (%)", title="超过东德大咚门槛的比例")
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / "04_一页式基准评分卡.png", dpi=180)
    plt.close(fig)


def main() -> None:
    calibration = calibrate()
    offset_db = float(calibration["selected"]["offset_db"])
    recordings = sorted((product_and_speed(p) for p in WAV_DIR.glob("*.wav")), key=lambda r: (r.speed_rpm, r.product))
    summaries: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    arrays: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    for rec in recordings:
        summary, event_rows, arr = analyze_recording(rec, offset_db)
        summaries.append(summary)
        events.extend(event_rows)
        arrays[(rec.product, rec.speed_rpm)] = arr

    by_key = {(str(r["product"]), int(r["speed_rpm"])): r for r in summaries}
    comparisons: list[dict[str, object]] = []
    for speed in sorted({r.speed_rpm for r in recordings}):
        dd = by_key.get(("东德基准", speed))
        fu = by_key.get(("富瑞初始", speed))
        if not dd or not fu:
            continue
        fu_levels = arrays[("富瑞初始", speed)]["event_level"]
        dd_p90 = float(dd["p90_est_dba"])
        d50 = float(fu["p50_est_dba"] - dd["p50_est_dba"])
        d90 = float(fu["p90_est_dba"] - dd["p90_est_dba"])
        common_energy_delta = float(fu["common_event_energy_est_dba"] - dd["common_event_energy_est_dba"])
        loud_energy_delta = float(fu["loud_event_energy_est_dba"] - dd["loud_event_energy_est_dba"])
        comparisons.append(
            {
                "speed_rpm": speed,
                "dd_p50_est_dba": dd["p50_est_dba"],
                "fu_p50_est_dba": fu["p50_est_dba"],
                "fu_minus_dd_p50_db": d50,
                "dd_p90_est_dba": dd_p90,
                "fu_p90_est_dba": fu["p90_est_dba"],
                "fu_minus_dd_p90_db": d90,
                "dd_common_event_energy_est_dba": dd["common_event_energy_est_dba"],
                "fu_common_event_energy_est_dba": fu["common_event_energy_est_dba"],
                "common_thump_delta_db": common_energy_delta,
                "dd_loud_event_energy_est_dba": dd["loud_event_energy_est_dba"],
                "fu_loud_event_energy_est_dba": fu["loud_event_energy_est_dba"],
                "loud_thump_delta_db": loud_energy_delta,
                "fu_events_above_dd_p90_pct": float(100 * np.mean(fu_levels > dd_p90)),
                "common_result": status(common_energy_delta),
                "loud_result": status(loud_energy_delta),
                "common_crosscheck": confidence_label(common_energy_delta, d50),
                "loud_crosscheck": confidence_label(loud_energy_delta, d90),
            }
        )

    comparison_by_speed = {int(row["speed_rpm"]): row for row in comparisons}
    registry = []
    for row in summaries:
        speed = int(row["speed_rpm"])
        comp = comparison_by_speed.get(speed) if row["product"] == "富瑞初始" else None
        if row["product"] == "东德基准":
            common_delta = loud_delta = 0.0
        elif comp:
            common_delta = float(comp["common_thump_delta_db"])
            loud_delta = float(comp["loud_thump_delta_db"])
        else:
            common_delta = loud_delta = None
        common_direction, common_magnitude, common_display = customer_delta(common_delta)
        loud_direction, loud_magnitude, loud_display = customer_delta(loud_delta)
        registry.append(
            {
                "series_id": row["series_id"],
                "test_date": "2026-07-07" if row["product"] == "东德基准" else "2026-07-09",
                "product": row["product"],
                "configuration": "东德基准状态" if row["product"] == "东德基准" else "富瑞初始状态",
                "speed_rpm": speed,
                "duration_s": row["duration_s"],
                "event_count": row["event_count"],
                "common_thump_est_dba": row["common_event_energy_est_dba"],
                "loud_thump_est_dba": row["loud_event_energy_est_dba"],
                "common_direction": common_direction,
                "common_difference_db": common_magnitude,
                "common_comparison": common_display,
                "loud_direction": loud_direction,
                "loud_difference_db": loud_magnitude,
                "loud_comparison": loud_display,
                "above_dd_loud_share_pct": comp["fu_events_above_dd_p90_pct"] if comp else (10.0 if row["product"] == "东德基准" else None),
                "result": comp["loud_result"] if comp else ("东德基准" if row["product"] == "东德基准" else "无同转速基准"),
                "has_meter": "是",
                "notes": "绝对dB(A)为手机录音经分贝仪画面校准后的估算值；相对差值更可靠。",
            }
        )

    write_csv(OUT / "baseline_summary.csv", summaries)
    write_csv(OUT / "event_details.csv", events)
    write_csv(OUT / "baseline_comparison.csv", comparisons)
    write_csv(OUT / "test_registry.csv", registry)
    with (OUT / "calibration.json").open("w", encoding="utf-8") as f:
        json.dump(calibration, f, ensure_ascii=False, indent=2)

    future_headers = [
        "test_id", "test_date", "configuration", "product", "speed_rpm", "video_path",
        "has_meter", "p50_est_dba", "p90_est_dba", "p95_est_dba", "event_count",
        "dd_p50_est_dba", "dd_p90_est_dba", "delta_p50_db", "delta_p90_db",
        "events_above_dd_p90_pct", "result", "notes",
    ]
    with (OUT / "future_test_registry.csv").open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(future_headers)

    max_duration = int(np.ceil(max(float(row["duration_s"]) for row in summaries)))
    envelope_time = np.arange(0.0, max_duration + 0.001, 0.1)
    envelope_columns: dict[str, list[float | None]] = {}
    rel_time = np.arange(-0.30, 0.451, 0.02)
    representative_columns: dict[str, list[float | None]] = {}
    for row in summaries:
        key = (str(row["product"]), int(row["speed_rpm"]))
        arr = arrays[key]
        # Peak-hold makes the overall envelope readable while retaining blocks of louder/quieter cycles.
        held = signal.order_filter(arr["clean_dba"], np.ones(9), 8)
        held = np.maximum(held, 50.0)
        valid = ~arr["exhaust_mask"]
        envelope_values = np.interp(
            envelope_time,
            arr["t"][valid],
            held[valid],
            left=np.nan,
            right=np.nan,
        )
        envelope_columns[str(row["series_id"])] = [float(v) if np.isfinite(v) else None for v in envelope_values]
        for percentile, suffix in [(50, "常见"), (90, "较响")]:
            rt, ry = representative_curve(arr, percentile)
            representative_columns[f"{row['series_id']}_{suffix}"] = np.interp(rel_time, rt, ry).tolist()

    payload = {
        "registry": registry,
        "envelope_time_s": envelope_time.tolist(),
        "envelope_columns": envelope_columns,
        "representative_time_ms": (rel_time * 1000).tolist(),
        "representative_columns": representative_columns,
        "calibration": calibration,
        "comparisons": comparisons,
    }
    with (OUT / "workbook_payload.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    plot_calibration(calibration)
    plot_envelopes(arrays)
    plot_representatives(arrays)
    plot_scorecard(comparisons)
    print(json.dumps({"calibration": calibration["selected"], "comparisons": comparisons}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
