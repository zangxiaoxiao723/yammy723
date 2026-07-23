from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import build_hpdi_baseline_v2 as base
from validate_hpdi_800_methods import bootstrap_delta, event_energy


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "hpdi_baseline_v2"
NEW_EVENTS = OUT / "event_details.csv"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def event_times(product: str, speed: int) -> np.ndarray:
    with NEW_EVENTS.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["product"] == product and int(r["speed_rpm"]) == speed]
    return np.array([float(r["time_s"]) for r in rows])


def classification(lo: float, hi: float, delta: float) -> str:
    if lo > 0:
        return "富瑞较高"
    if hi < 0:
        return "富瑞较低"
    return "无法区分"


def main() -> None:
    rng = np.random.default_rng(20260723)
    methods = [
        ("全咚声频带（未计权）", 45, 650, False),
        ("全咚声频带（A计权）", 45, 650, True),
        ("低频 45-120 Hz", 45, 120, False),
        ("中低频 120-250 Hz", 120, 250, False),
        ("中频 250-650 Hz", 250, 650, False),
    ]
    rows = []
    source_paths: dict[str, Path] = {}
    for speed in [700, 800, 900, 1125]:
        paths = {
            "东德基准": next(p for p in base.WAV_DIR.glob("*.wav") if "东德" in p.name and f"{speed}rpm" in p.name),
            "富瑞初始": next(p for p in base.WAV_DIR.glob("*.wav") if "富瑞" in p.name and f"{speed}rpm" in p.name),
        }
        for product, path in paths.items():
            source_paths[f"{product}_{speed}"] = path
        audio = {name: base.read_wav(path) for name, path in paths.items()}
        times = {name: event_times(name, speed) for name in paths}
        for method, lo_hz, hi_hz, use_a in methods:
            values = {}
            for product, (fs, x) in audio.items():
                y = base.bandpass(fs, x, lo_hz, hi_hz)
                if use_a:
                    y = base.a_weight(fs, y)
                values[product], _ = event_energy(fs, y, times[product])
            for label, percentile in [("常见咚声", 50), ("较响咚声", 90)]:
                delta, ci_lo, ci_hi = bootstrap_delta(values["东德基准"], values["富瑞初始"], percentile, rng)
                rows.append({
                    "speed_rpm": speed,
                    "metric": label,
                    "method": method,
                    "difference_direction": "高于东德" if delta > 0 else "低于东德",
                    "difference_magnitude_db": abs(delta),
                    "signed_fu_minus_dd_db": delta,
                    "ci95_low_db": ci_lo,
                    "ci95_high_db": ci_hi,
                    "classification": classification(ci_lo, ci_hi, delta),
                    "dd_event_count": len(values["东德基准"]),
                    "fu_event_count": len(values["富瑞初始"]),
                })

    with (OUT / "all_speed_method_validation.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summaries = []
    for speed in [700, 800, 900, 1125]:
        for metric in ["常见咚声", "较响咚声"]:
            group = [r for r in rows if r["speed_rpm"] == speed and r["metric"] == metric]
            counts = {name: sum(r["classification"] == name for r in group) for name in ["富瑞较低", "富瑞较高", "无法区分"]}
            if counts["富瑞较高"] >= 3:
                overall = "多方法支持富瑞较高"
            elif counts["富瑞较低"] >= 3:
                overall = "多方法支持富瑞较低"
            else:
                overall = "方法间或统计区间不足，不能定论"
            summaries.append({"speed_rpm": speed, "metric": metric, **counts, "overall": overall})
    with (OUT / "method_consistency_summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    hash_rows = []
    for label, path in sorted(source_paths.items()):
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        hash_rows.append({"source_id": label, "path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    with (OUT / "source_file_hashes.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(hash_rows[0]))
        writer.writeheader()
        writer.writerows(hash_rows)

    fig, axes = plt.subplots(2, 4, figsize=(13, 6.6), sharex=True)
    for col, speed in enumerate([700, 800, 900, 1125]):
        for row_idx, metric in enumerate(["常见咚声", "较响咚声"]):
            ax = axes[row_idx, col]
            group = [r for r in rows if r["speed_rpm"] == speed and r["metric"] == metric]
            for i, item in enumerate(group):
                delta = float(item["signed_fu_minus_dd_db"])
                uncertain = item["classification"] == "无法区分"
                color = "#15803D" if delta < 0 else "#C2410C"
                ax.barh(i, abs(delta), color=color, alpha=0.3 if uncertain else 0.9)
            ax.set_yticks(range(len(group)), [r["method"].replace("全咚声频带", "全频带") for r in group] if col == 0 else [])
            ax.set_title(f"{speed} rpm  {metric}", fontsize=10)
            ax.grid(axis="x", alpha=0.2)
            ax.set_xlim(0, 18)
            if row_idx == 1:
                ax.set_xlabel("差值大小 dB")
    fig.suptitle("各转速多方法一致性：绿=富瑞较低，红=富瑞较高，浅色=无法区分", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "plots" / "06_全部转速多方法一致性.png", dpi=180)
    plt.close(fig)

    for row in summaries:
        print(row)


if __name__ == "__main__":
    main()
