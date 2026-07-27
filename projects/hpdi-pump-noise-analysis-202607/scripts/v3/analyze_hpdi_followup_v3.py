from __future__ import annotations

import csv
import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

import build_hpdi_baseline_v2 as base


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\FRCloud\FRQ\04_Pump Development\66_泵研发制造中心_临时\原始数据")
BASE_OUT = ROOT / "outputs" / "hpdi_baseline_v2"
OUT = ROOT / "outputs" / "hpdi_followup_v3"
WAV_DIR = ROOT / "work" / "hpdi_followup_v3" / "wav"
PLOTS = OUT / "plots"
for path in (OUT, WAV_DIR, PLOTS):
    path.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


@dataclass(frozen=True)
class Test:
    series_id: str
    date: str
    condition: str
    short_label: str
    speed_rpm: int
    run: str
    video: Path
    has_meter: str
    subjective: str = ""


def tests() -> list[Test]:
    specs = [
        ("FR_0716_CYL_800", "2026-07-16", "换26号嵌套油缸 + 老控制器", "0716嵌套油缸", 800, "800rpm", "是", ""),
        ("FR_0716_CYL_900", "2026-07-16", "换26号嵌套油缸 + 老控制器", "0716嵌套油缸", 900, "900rpm", "是", ""),
        ("FR_0716_CYL_1000", "2026-07-16", "换26号嵌套油缸 + 老控制器", "0716嵌套油缸", 1000, "1000rpm", "是", ""),
        ("FR_0716_CYL_1125", "2026-07-16", "换26号嵌套油缸 + 老控制器", "0716嵌套油缸", 1125, "1125rpm", "是", ""),
        ("FR_0716_SHUTTLE_900_R1", "2026-07-16", "换26号嵌套油缸 + 西港梭阀 + 老控制器", "0716西港梭阀R1", 900, "900rpm-1", "否", ""),
        ("FR_0716_SHUTTLE_900_R2", "2026-07-16", "换26号嵌套油缸 + 西港梭阀 + 老控制器", "0716西港梭阀R2", 900, "900rpm-2", "否", ""),
        ("FR_0716_SHUTTLE_1000", "2026-07-16", "换26号嵌套油缸 + 西港梭阀 + 老控制器", "0716西港梭阀", 1000, "1000rpm", "否", ""),
        ("FR_0722_B_HEAT_900", "2026-07-22", "A样改B样 + 热处理活塞 + 嵌套油缸 + 老控制器", "0722热处理活塞+B样", 900, "900rpm", "否", ""),
        ("FR_0722_B_HEAT_1000", "2026-07-22", "A样改B样 + 热处理活塞 + 嵌套油缸 + 老控制器", "0722热处理活塞+B样", 1000, "1000rpm", "否", ""),
        ("FR_DELIVERY_0723_700", "2026-07-23", "交付泵", "0723交付泵", 700, "700rpm", "否", "用户主观感觉声音较好"),
    ]
    folders = {
        "FR_0716_CYL": "0716_换26号嵌套油缸_老控制器",
        "FR_0716_SHUTTLE": "0716_换26号嵌套油缸_西港梭阀_老控制器",
        "FR_0722_B_HEAT": "0722_A样改B样_为热处理活塞&嵌套油缸_老控制器",
        "FR_DELIVERY": "0723交付泵",
    }
    result = []
    for sid, date, condition, short, speed, run, meter, subjective in specs:
        folder = next(value for prefix, value in folders.items() if sid.startswith(prefix))
        video = SOURCE / folder / run / f"{run}.mp4"
        result.append(Test(sid, date, condition, short, speed, run, video, meter, subjective))
    return result


def extract_audio(test: Test) -> Path:
    output = WAV_DIR / f"{test.series_id}.wav"
    if output.exists() and output.stat().st_size > 44:
        return output
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(test.video), "-vn", "-ac", "1", "-ar", "44100", str(output)],
        check=True,
    )
    return output


def analyze(test: Test, offset_db: float) -> tuple[dict[str, object], list[dict[str, object]], dict[str, np.ndarray]]:
    wav = extract_audio(test)
    fs, x = base.read_wav(wav)
    thump = base.a_weight(fs, base.bandpass(fs, x, 45, 650))
    hiss = base.bandpass(fs, x, 1800, 9000)
    t, thump_rms = base.frame_rms(thump, fs)
    _, hiss_rms = base.frame_rms(hiss, fs)
    env_dbfs = base.db20(thump_rms)
    hiss_dbfs = base.db20(hiss_rms)
    hop_s = float(np.median(np.diff(t)))
    bg = base.rolling_quantile(thump_rms, int(3.0 / hop_s), 0.20)
    excess_rms = np.sqrt(np.maximum(thump_rms**2 - bg**2, (10 ** (-90 / 20)) ** 2))
    clean_dba = base.db20(excess_rms) + offset_db
    ratio_db = hiss_dbfs - env_dbfs
    exhaust_mask = ratio_db >= max(float(np.percentile(ratio_db, 90)), 10.0)

    smooth = signal.savgol_filter(env_dbfs, min(21, len(env_dbfs) // 2 * 2 - 1), 3)
    peaks, _ = signal.find_peaks(
        smooth,
        prominence=max(1.5, float(np.percentile(smooth, 75) - np.percentile(smooth, 45)) * 0.35),
        distance=max(1, int(0.18 / hop_s)),
        height=float(np.percentile(smooth, 55)),
    )
    peaks = peaks[~exhaust_mask[peaks]]
    events = []
    for p in peaks:
        source_peak = float(clean_dba[p])
        if source_peak < 20:
            continue
        center = int(t[p] * fs)
        ea, eb = max(0, center - int(0.06 * fs)), min(len(thump), center + int(0.18 * fs))
        b1a, b1b = max(0, center - int(0.72 * fs)), max(0, center - int(0.25 * fs))
        b2a, b2b = min(len(thump), center + int(0.25 * fs)), min(len(thump), center + int(0.72 * fs))
        event_power = float(np.mean(thump[ea:eb] ** 2))
        bg_parts = np.concatenate([thump[b1a:b1b], thump[b2a:b2b]])
        bg_power = float(np.mean(bg_parts**2)) if len(bg_parts) else 0.0
        energy = np.sqrt(max(event_power - bg_power, event_power * 0.03))
        events.append({
            "series_id": test.series_id,
            "date": test.date,
            "condition": test.condition,
            "short_label": test.short_label,
            "speed_rpm": test.speed_rpm,
            "run": test.run,
            "event_index": len(events) + 1,
            "time_s": float(t[p]),
            "thump_level_est_dba": source_peak,
            "event_energy_est_dba": float(base.db20(energy) + offset_db),
            "raw_peak_est_dba": float(env_dbfs[p] + offset_db),
            "background_est_dba": float(base.db20(bg[p]) + offset_db),
            "exhaust_ratio_db": float(ratio_db[p]),
            "wav": str(wav),
        })
    raw_peak_levels = np.array([e["thump_level_est_dba"] for e in events])
    raw_energies = np.array([e["event_energy_est_dba"] for e in events])
    median_background = float(np.median([e["background_est_dba"] for e in events]))
    gain_shift = 65.0 - median_background
    peak_levels = raw_peak_levels + gain_shift
    energies = raw_energies + gain_shift
    for event, peak, energy in zip(events, peak_levels, energies):
        event["normalized_thump_peak_db"] = float(peak)
        event["normalized_event_energy_db"] = float(energy)
    summary = {
        "series_id": test.series_id,
        "test_date": test.date,
        "product": "富瑞后续",
        "configuration": test.condition,
        "short_label": test.short_label,
        "speed_rpm": test.speed_rpm,
        "run": test.run,
        "duration_s": len(x) / fs,
        "event_count": len(events),
        "common_thump_est_dba": float(np.percentile(energies, 50)),
        "loud_thump_est_dba": float(np.percentile(energies, 90)),
        "peak_p50_est_dba": float(np.percentile(peak_levels, 50)),
        "peak_p90_est_dba": float(np.percentile(peak_levels, 90)),
        "raw_common_thump_est_dba": float(np.percentile(raw_energies, 50)),
        "raw_loud_thump_est_dba": float(np.percentile(raw_energies, 90)),
        "median_background_est_dba": median_background,
        "gain_normalization_shift_db": gain_shift,
        "exhaust_mask_share_pct": float(100 * np.mean(exhaust_mask)),
        "has_meter": test.has_meter,
        "subjective": test.subjective,
        "video": str(test.video),
        "wav": str(wav),
    }
    arrays = {
        "t": t,
        "clean_dba": clean_dba + gain_shift,
        "raw_dba": env_dbfs + offset_db + gain_shift,
        "background_dba": base.db20(bg) + offset_db + gain_shift,
        "clean_dba_fixed": clean_dba,
        "raw_dba_fixed": env_dbfs + offset_db,
        "background_dba_fixed": base.db20(bg) + offset_db,
        "exhaust_mask": exhaust_mask,
        "event_t": np.array([e["time_s"] for e in events]),
        "event_level": peak_levels,
        "event_energy": energies,
        "event_level_fixed": raw_peak_levels,
        "event_energy_fixed": raw_energies,
    }
    return summary, events, arrays


def delta_parts(delta: float | None) -> tuple[str, float | None, str]:
    if delta is None:
        return "无同转速基准", None, "无同转速基准"
    if abs(delta) < 0.05:
        return "接近", 0.0, "接近 0.0 dB"
    direction = "低于" if delta < 0 else "高于"
    return direction, abs(delta), f"{direction} {abs(delta):.1f} dB"


def result_text(loud_delta: float | None) -> str:
    if loud_delta is None:
        return "无东德同转速基准"
    if loud_delta > 2:
        return "明显高于东德"
    if loud_delta > 0:
        return "略高于东德"
    if loud_delta <= -2:
        return "明显低于东德"
    return "略低于/接近东德"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalize_baseline_payload(payload: dict[str, object]) -> tuple[dict[str, object], dict[str, float]]:
    """Move every baseline recording to the same 65 dB local-background reference."""
    with (BASE_OUT / "event_details.csv").open(encoding="utf-8-sig") as f:
        event_rows = list(csv.DictReader(f))

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in event_rows:
        grouped.setdefault(row["series_id"], []).append(row)

    normalized = copy.deepcopy(payload)
    shifts: dict[str, float] = {}
    peak_p90: dict[str, float] = {}
    for row in normalized["registry"]:
        sid = str(row["series_id"])
        series_events = grouped[sid]
        background = np.array([float(e["local_background_est_dba"]) for e in series_events])
        shift = 65.0 - float(np.median(background))
        energy = np.array([float(e["event_energy_est_dba"]) for e in series_events]) + shift
        peaks = np.array([float(e["thump_level_est_dba"]) for e in series_events]) + shift
        shifts[sid] = shift
        peak_p90[sid] = float(np.percentile(peaks, 90))
        row["raw_common_thump_est_dba"] = row["common_thump_est_dba"]
        row["raw_loud_thump_est_dba"] = row["loud_thump_est_dba"]
        row["median_background_est_dba"] = float(np.median(background))
        row["gain_normalization_shift_db"] = shift
        row["common_thump_est_dba"] = float(np.percentile(energy, 50))
        row["loud_thump_est_dba"] = float(np.percentile(energy, 90))

    for sid, values in normalized["envelope_columns"].items():
        shift = shifts[sid]
        normalized["envelope_columns"][sid] = [None if value is None else float(value) + shift for value in values]
    for key, values in normalized["representative_columns"].items():
        sid = key.rsplit("_", 1)[0]
        shift = shifts[sid]
        normalized["representative_columns"][key] = [None if value is None else float(value) + shift for value in values]

    dd_by_speed = {
        int(row["speed_rpm"]): row for row in normalized["registry"] if row["product"] == "\u4e1c\u5fb7\u57fa\u51c6"
    }
    for row in normalized["registry"]:
        speed = int(row["speed_rpm"])
        dd = dd_by_speed.get(speed)
        if row["product"] == "\u4e1c\u5fb7\u57fa\u51c6":
            row.update({
                "common_direction": "\u4e1c\u5fb7\u57fa\u51c6", "common_difference_db": 0.0, "common_comparison": "\u57fa\u51c6",
                "loud_direction": "\u4e1c\u5fb7\u57fa\u51c6", "loud_difference_db": 0.0, "loud_comparison": "\u57fa\u51c6",
                "above_dd_loud_share_pct": 10.0, "result": "\u4e1c\u5fb7\u57fa\u51c6",
            })
        elif dd:
            common_delta = float(row["common_thump_est_dba"]) - float(dd["common_thump_est_dba"])
            loud_delta = float(row["loud_thump_est_dba"]) - float(dd["loud_thump_est_dba"])
            common_direction, common_magnitude, common_text = delta_parts(common_delta)
            loud_direction, loud_magnitude, loud_text = delta_parts(loud_delta)
            sid = str(row["series_id"])
            series_peaks = np.array([float(e["thump_level_est_dba"]) for e in grouped[sid]]) + shifts[sid]
            row.update({
                "common_direction": common_direction, "common_difference_db": common_magnitude, "common_comparison": common_text,
                "loud_direction": loud_direction, "loud_difference_db": loud_magnitude, "loud_comparison": loud_text,
                "above_dd_loud_share_pct": float(100 * np.mean(series_peaks > peak_p90[str(dd["series_id"])])),
                "result": result_text(loud_delta),
            })
        row["notes"] = "\u6307\u6807\u4e3a\u80cc\u666f\u5f52\u4e00\u5316\u58f0\u7ea7\uff1b\u6bcf\u6bb5\u5f55\u97f3\u7684\u5c40\u90e8\u80cc\u666f\u7edf\u4e00\u523065 dB\u53c2\u8003\u7ebf\u3002"
    return normalized, peak_p90


def representative(
    arr: dict[str, np.ndarray],
    percentile: float,
    rel_time: np.ndarray,
    energy_key: str = "event_energy",
    curve_key: str = "raw_dba",
) -> np.ndarray:
    target = float(np.percentile(arr[energy_key], percentile))
    idx = int(np.argmin(np.abs(arr[energy_key] - target)))
    center = float(arr["event_t"][idx])
    keep = (arr["t"] >= center - 0.30) & (arr["t"] <= center + 0.45)
    return np.interp(rel_time, arr["t"][keep] - center, arr[curve_key][keep])


def plot_trends(summaries: list[dict[str, object]], arrays: dict[str, dict[str, np.ndarray]]) -> None:
    fig, axes = plt.subplots(5, 2, figsize=(12, 13), sharey=True)
    for ax, summary in zip(axes.ravel(), summaries):
        arr = arrays[str(summary["series_id"])]
        x, y = arr["event_t"], arr["event_energy"]
        ax.scatter(x, y, s=13, color="#C2410C", alpha=0.75)
        if len(y) >= 5:
            ax.plot(x[2:-2], np.convolve(y, np.ones(5) / 5, mode="valid"), color="#172033", lw=1.8)
        ax.set_title(f"{summary['short_label']} | {summary['run']}", fontsize=10)
        ax.set_xlabel("视频时间 (s)")
        ax.set_ylabel("背景归一化声级 (dB)")
        ax.set_ylim(45, 100)
        ax.grid(alpha=0.2)
    fig.suptitle("后续测试整体咚声趋势（每个点为一次有效咚声）", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(PLOTS / "01_后续测试整体咚声趋势.png", dpi=180)
    plt.close(fig)


def plot_comparison(comparisons: list[dict[str, object]], key: str, title: str, output: str) -> None:
    rows = [r for r in comparisons if r[f"{key}_common_delta_db"] is not None]
    labels = [f"{r['short_label']}\n{r['run']}" for r in rows]
    common_signed = np.array([float(r[f"{key}_common_delta_db"]) for r in rows])
    loud_signed = np.array([float(r[f"{key}_loud_delta_db"]) for r in rows])
    x = np.arange(len(rows))
    width = 0.36
    fig, ax = plt.subplots(figsize=(12, 5.2))
    b1 = ax.bar(x - width / 2, np.abs(common_signed), width, color=["#15803D" if v < 0 else "#C2410C" for v in common_signed], label="常见咚声")
    b2 = ax.bar(x + width / 2, np.abs(loud_signed), width, color=["#4ADE80" if v < 0 else "#FB923C" for v in loud_signed], label="较响咚声")
    for bars, values in [(b1, common_signed), (b2, loud_signed)]:
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, "低" if value < 0 else "高", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, labels, rotation=24, ha="right")
    ax.set_ylabel("差值大小 (dB)")
    ax.set_title(title + "（绿=更低，橙=更高）")
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / output, dpi=180)
    plt.close(fig)


def plot_delivery_detail(all_arrays: dict[str, dict[str, np.ndarray]], combined_payload: dict[str, object]) -> None:
    ids = ["DD_BASE_260707_700", "FR_INIT_260709_700", "FR_DELIVERY_0723_700"]
    labels = ["东德基准", "富瑞初始", "0723交付泵"]
    colors = ["#007C91", "#64748B", "#C2410C"]
    rel = np.arange(-0.30, 0.451, 0.02)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    rep_cols = combined_payload["representative_columns"]
    for ax, pct, suffix, title in [(axes[0], 50, "常见", "常见咚声"), (axes[1], 90, "较响", "较响咚声")]:
        for sid, label, color in zip(ids, labels, colors):
            if sid == "FR_DELIVERY_0723_700":
                y = representative(all_arrays[sid], pct, rel)
            else:
                y = np.array(rep_cols[f"{sid}_{suffix}"])
            ax.plot(rel * 1000, y, color=color, lw=1.6, label=label)
        ax.axvline(0, color="#94A3B8", lw=0.7)
        ax.set_title(title)
        ax.set_xlabel("相对峰值时间 (ms)")
        ax.set_ylabel("背景归一化声级 (dB)")
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("700 rpm：东德、富瑞初始与交付泵单次咚声对比", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(PLOTS / "04_交付泵700rpm详细对比.png", dpi=180)
    plt.close(fig)


def plot_900_levels(registry: list[dict[str, object]]) -> None:
    rows = [r for r in registry if int(r["speed_rpm"]) == 900]
    labels = [str(r.get("short_label") or r["product"]) + (f"\n{r.get('run')}" if r.get("run") else "") for r in rows]
    common = [float(r["common_thump_est_dba"]) for r in rows]
    loud = [float(r["loud_thump_est_dba"]) for r in rows]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.bar(x - 0.18, common, 0.36, label="常见咚声", color="#007C91")
    ax.bar(x + 0.18, loud, 0.36, label="较响咚声", color="#C2410C")
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylabel("背景归一化声级 (dB)")
    ax.set_title("900 rpm 各配置对比（背景统一为65 dB参考线）")
    ax.set_ylim(45, 100)
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "05_900rpm各配置对比.png", dpi=180)
    plt.close(fig)


def main() -> None:
    with (BASE_OUT / "calibration.json").open(encoding="utf-8") as f:
        calibration = json.load(f)
    offset_db = float(calibration["selected"]["offset_db"])
    with (BASE_OUT / "workbook_payload.json").open(encoding="utf-8") as f:
        raw_baseline_payload = json.load(f)
    baseline_payload, baseline_peak_p90 = normalize_baseline_payload(raw_baseline_payload)

    summaries, events = [], []
    arrays: dict[str, dict[str, np.ndarray]] = {}
    for test in tests():
        summary, event_rows, arr = analyze(test, offset_db)
        summaries.append(summary)
        events.extend(event_rows)
        arrays[test.series_id] = arr

    baseline_registry = baseline_payload["registry"]
    baseline_by = {(str(r["product"]), int(r["speed_rpm"])): r for r in baseline_registry}
    comparisons = []
    new_registry = []
    for summary in summaries:
        speed = int(summary["speed_rpm"])
        dd = baseline_by.get(("东德基准", speed))
        initial = baseline_by.get(("富瑞初始", speed))
        dd_common = float(summary["common_thump_est_dba"] - dd["common_thump_est_dba"]) if dd else None
        dd_loud = float(summary["loud_thump_est_dba"] - dd["loud_thump_est_dba"]) if dd else None
        init_common = float(summary["common_thump_est_dba"] - initial["common_thump_est_dba"]) if initial else None
        init_loud = float(summary["loud_thump_est_dba"] - initial["loud_thump_est_dba"]) if initial else None
        dd_cd, dd_cm, dd_ct = delta_parts(dd_common)
        dd_ld, dd_lm, dd_lt = delta_parts(dd_loud)
        in_cd, in_cm, in_ct = delta_parts(init_common)
        in_ld, in_lm, in_lt = delta_parts(init_loud)
        if dd:
            dd_peak_p90 = baseline_peak_p90[str(dd["series_id"])]
            above_share = float(100 * np.mean(arrays[str(summary["series_id"])]["event_level"] > dd_peak_p90))
        else:
            above_share = None
        row = {
            **summary,
            "dd_common_delta_db": dd_common,
            "dd_loud_delta_db": dd_loud,
            "vs_dd_common": dd_ct,
            "vs_dd_loud": dd_lt,
            "initial_common_delta_db": init_common,
            "initial_loud_delta_db": init_loud,
            "vs_initial_common": in_ct,
            "vs_initial_loud": in_lt,
            "above_dd_loud_share_pct": above_share,
            "result": result_text(dd_loud),
        }
        comparisons.append(row)
        new_registry.append({
            "series_id": summary["series_id"],
            "test_date": summary["test_date"],
            "product": summary["product"],
            "configuration": summary["configuration"],
            "short_label": summary["short_label"],
            "speed_rpm": speed,
            "run": summary["run"],
            "duration_s": summary["duration_s"],
            "event_count": summary["event_count"],
            "common_thump_est_dba": summary["common_thump_est_dba"],
            "loud_thump_est_dba": summary["loud_thump_est_dba"],
            "common_comparison": dd_ct,
            "loud_comparison": dd_lt,
            "common_difference_db": dd_cm,
            "loud_difference_db": dd_lm,
            "initial_common_comparison": in_ct,
            "initial_loud_comparison": in_lt,
            "initial_common_difference_db": in_cm,
            "initial_loud_difference_db": in_lm,
            "above_dd_loud_share_pct": above_share,
            "result": result_text(dd_loud),
            "has_meter": summary["has_meter"],
            "subjective": summary["subjective"],
            "notes": "绝对dB(A)为工程估算；同转速相对差值优先。" + (f" {summary['subjective']}。" if summary["subjective"] else ""),
        })

    write_csv(OUT / "followup_summary.csv", summaries)
    write_csv(OUT / "followup_event_details.csv", events)
    write_csv(OUT / "followup_comparison.csv", comparisons)
    write_csv(OUT / "followup_registry.csv", new_registry)

    combined_registry = []
    for r in baseline_registry:
        combined_registry.append({
            **r,
            "short_label": r["product"],
            "run": f"{r['speed_rpm']}rpm",
            "initial_common_comparison": "初始状态" if r["product"] == "富瑞初始" else "不适用",
            "initial_loud_comparison": "初始状态" if r["product"] == "富瑞初始" else "不适用",
            "initial_common_difference_db": 0.0 if r["product"] == "富瑞初始" else None,
            "initial_loud_difference_db": 0.0 if r["product"] == "富瑞初始" else None,
            "subjective": "",
        })
    combined_registry.extend(new_registry)

    max_duration = int(np.ceil(max([float(r["duration_s"]) for r in combined_registry])))
    env_time = np.arange(0, max_duration + 0.001, 0.1)
    env_cols = {k: v for k, v in baseline_payload["envelope_columns"].items()}
    rel_time = np.array(baseline_payload["representative_time_ms"]) / 1000.0
    rep_cols = {k: v for k, v in baseline_payload["representative_columns"].items()}
    for summary in summaries:
        sid = str(summary["series_id"])
        arr = arrays[sid]
        held = signal.order_filter(arr["clean_dba"], np.ones(9), 8)
        held = np.maximum(held, 50.0)
        valid = ~arr["exhaust_mask"]
        vals = np.interp(env_time, arr["t"][valid], held[valid], left=np.nan, right=np.nan)
        env_cols[sid] = [float(v) if np.isfinite(v) else None for v in vals]
        rep_cols[f"{sid}_常见"] = representative(arr, 50, rel_time).tolist()
        rep_cols[f"{sid}_较响"] = representative(arr, 90, rel_time).tolist()

    combined_payload = {
        "registry": combined_registry,
        "envelope_time_s": env_time.tolist(),
        "envelope_columns": env_cols,
        "representative_time_ms": (rel_time * 1000).tolist(),
        "representative_columns": rep_cols,
        "calibration": calibration,
        "comparisons": comparisons,
    }
    with (OUT / "combined_workbook_payload.json").open("w", encoding="utf-8") as f:
        json.dump(combined_payload, f, ensure_ascii=False)

    # Primary comparison payload: keep the V2 baseline and calibration method immutable.
    fixed_baseline_registry = copy.deepcopy(raw_baseline_payload["registry"])
    fixed_baseline_by = {(str(r["product"]), int(r["speed_rpm"])): r for r in fixed_baseline_registry}
    baseline_peak_p90_fixed = {}
    with (BASE_OUT / "baseline_summary.csv").open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            baseline_peak_p90_fixed[(row["product"], int(row["speed_rpm"]))] = float(row["p90_est_dba"])

    fixed_comparisons = []
    fixed_new_registry = []
    for summary in summaries:
        speed = int(summary["speed_rpm"])
        dd = fixed_baseline_by.get(("东德基准", speed))
        initial = fixed_baseline_by.get(("富瑞初始", speed))
        common = float(summary["raw_common_thump_est_dba"])
        loud = float(summary["raw_loud_thump_est_dba"])
        dd_common = common - float(dd["common_thump_est_dba"]) if dd else None
        dd_loud = loud - float(dd["loud_thump_est_dba"]) if dd else None
        init_common = common - float(initial["common_thump_est_dba"]) if initial else None
        init_loud = loud - float(initial["loud_thump_est_dba"]) if initial else None
        _, dd_cm, dd_ct = delta_parts(dd_common)
        _, dd_lm, dd_lt = delta_parts(dd_loud)
        _, in_cm, in_ct = delta_parts(init_common)
        _, in_lm, in_lt = delta_parts(init_loud)
        if dd:
            threshold = baseline_peak_p90_fixed[("东德基准", speed)]
            above_share = float(100 * np.mean(arrays[str(summary["series_id"])]["event_level_fixed"] > threshold))
        else:
            above_share = None
        row = {
            **summary,
            "common_thump_est_dba": common,
            "loud_thump_est_dba": loud,
            "dd_common_delta_db": dd_common,
            "dd_loud_delta_db": dd_loud,
            "vs_dd_common": dd_ct,
            "vs_dd_loud": dd_lt,
            "initial_common_delta_db": init_common,
            "initial_loud_delta_db": init_loud,
            "vs_initial_common": in_ct,
            "vs_initial_loud": in_lt,
            "above_dd_loud_share_pct": above_share,
            "result": result_text(dd_loud),
            "comparison_method": "V2固定基准口径",
        }
        fixed_comparisons.append(row)
        fixed_new_registry.append({
            "series_id": summary["series_id"],
            "test_date": summary["test_date"],
            "product": summary["product"],
            "configuration": summary["configuration"],
            "short_label": summary["short_label"],
            "speed_rpm": speed,
            "run": summary["run"],
            "duration_s": summary["duration_s"],
            "event_count": summary["event_count"],
            "common_thump_est_dba": common,
            "loud_thump_est_dba": loud,
            "common_comparison": dd_ct,
            "loud_comparison": dd_lt,
            "common_difference_db": dd_cm,
            "loud_difference_db": dd_lm,
            "initial_common_comparison": in_ct,
            "initial_loud_comparison": in_lt,
            "initial_common_difference_db": in_cm,
            "initial_loud_difference_db": in_lm,
            "above_dd_loud_share_pct": above_share,
            "result": result_text(dd_loud),
            "has_meter": summary["has_meter"],
            "subjective": summary["subjective"],
            "notes": "沿用V2固定基准算法；无分贝仪的跨日期视频受手机自动增益影响，结论需复测确认。",
        })

    fixed_registry = []
    for row in fixed_baseline_registry:
        fixed_registry.append({
            **row,
            "short_label": row["product"],
            "run": f"{row['speed_rpm']}rpm",
            "initial_common_comparison": "初始状态" if row["product"] == "富瑞初始" else "不适用",
            "initial_loud_comparison": "初始状态" if row["product"] == "富瑞初始" else "不适用",
            "initial_common_difference_db": 0.0 if row["product"] == "富瑞初始" else None,
            "initial_loud_difference_db": 0.0 if row["product"] == "富瑞初始" else None,
            "subjective": "",
        })
    fixed_registry.extend(fixed_new_registry)

    fixed_env_cols = copy.deepcopy(raw_baseline_payload["envelope_columns"])
    fixed_rep_cols = copy.deepcopy(raw_baseline_payload["representative_columns"])
    for summary in summaries:
        sid = str(summary["series_id"])
        arr = arrays[sid]
        held = signal.order_filter(arr["clean_dba_fixed"], np.ones(9), 8)
        held = np.maximum(held, 50.0)
        valid = ~arr["exhaust_mask"]
        vals = np.interp(env_time, arr["t"][valid], held[valid], left=np.nan, right=np.nan)
        fixed_env_cols[sid] = [float(v) if np.isfinite(v) else None for v in vals]
        fixed_rep_cols[f"{sid}_常见"] = representative(
            arr, 50, rel_time, energy_key="event_energy_fixed", curve_key="raw_dba_fixed"
        ).tolist()
        fixed_rep_cols[f"{sid}_较响"] = representative(
            arr, 90, rel_time, energy_key="event_energy_fixed", curve_key="raw_dba_fixed"
        ).tolist()

    fixed_payload = {
        "registry": fixed_registry,
        "envelope_time_s": env_time.tolist(),
        "envelope_columns": fixed_env_cols,
        "representative_time_ms": (rel_time * 1000).tolist(),
        "representative_columns": fixed_rep_cols,
        "calibration": calibration,
        "comparisons": fixed_comparisons,
        "method": "V2固定基准口径",
    }
    with (OUT / "combined_fixed_baseline_payload.json").open("w", encoding="utf-8") as f:
        json.dump(fixed_payload, f, ensure_ascii=False)
    write_csv(OUT / "followup_fixed_baseline_comparison.csv", fixed_comparisons)

    plot_trends(summaries, arrays)
    plot_comparison(comparisons, "dd", "后续状态相对同转速东德基准", "02_后续状态相对东德.png")
    plot_comparison(comparisons, "initial", "后续状态相对富瑞初始", "03_后续状态相对富瑞初始.png")
    plot_delivery_detail(arrays, combined_payload)
    plot_900_levels(combined_registry)

    print(json.dumps(comparisons, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
