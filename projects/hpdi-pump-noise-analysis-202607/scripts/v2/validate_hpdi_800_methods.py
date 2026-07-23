from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

import build_hpdi_baseline_v2 as base


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "hpdi_baseline_v2"
OLD_EVENTS = ROOT / "outputs" / "hpdi_thump_loudness_quant" / "thump_event_details.csv"
NEW_EVENTS = OUT / "event_details.csv"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def load_event_times(product: str) -> np.ndarray:
    with NEW_EVENTS.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["product"] == product and int(r["speed_rpm"]) == 800]
    return np.array([float(r["time_s"]) for r in rows])


def event_energy(fs: int, x: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = []
    backgrounds = []
    for time_s in times:
        p = int(time_s * fs)
        event = x[max(0, p - int(0.06 * fs)): min(len(x), p + int(0.18 * fs))]
        bg = np.concatenate([
            x[max(0, p - int(0.72 * fs)): max(0, p - int(0.25 * fs))],
            x[min(len(x), p + int(0.25 * fs)): min(len(x), p + int(0.72 * fs))],
        ])
        ep = float(np.mean(event**2))
        bp = float(np.mean(bg**2)) if len(bg) else 0.0
        values.append(10 * np.log10(max(ep - bp, ep * 0.03, 1e-24)))
        backgrounds.append(10 * np.log10(max(bp, 1e-24)))
    return np.array(values), np.array(backgrounds)


def bootstrap_delta(dd: np.ndarray, fu: np.ndarray, percentile: float, rng: np.random.Generator) -> tuple[float, float, float]:
    observed = float(np.percentile(fu, percentile) - np.percentile(dd, percentile))
    draws = np.empty(4000)
    for i in range(len(draws)):
        a = rng.choice(dd, len(dd), replace=True)
        b = rng.choice(fu, len(fu), replace=True)
        draws[i] = np.percentile(b, percentile) - np.percentile(a, percentile)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return observed, float(lo), float(hi)


def main() -> None:
    rng = np.random.default_rng(20260723)
    paths = {
        "东德基准": next(p for p in base.WAV_DIR.glob("*.wav") if "东德" in p.name and "800rpm" in p.name),
        "富瑞初始": next(p for p in base.WAV_DIR.glob("*.wav") if "富瑞" in p.name and "800rpm" in p.name),
    }
    audio = {name: base.read_wav(path) for name, path in paths.items()}
    times = {name: load_event_times(name) for name in paths}

    methods = [
        ("45-650 Hz 未计权冲击能量", 45, 650, False),
        ("45-650 Hz A计权冲击能量", 45, 650, True),
        ("45-120 Hz 低频冲击", 45, 120, False),
        ("120-250 Hz 中低频冲击", 120, 250, False),
        ("250-650 Hz 中频冲击", 250, 650, False),
    ]
    rows = []
    background_rows = []
    for method, lo, hi, use_a in methods:
        values = {}
        backgrounds = {}
        for product, (fs, x) in audio.items():
            y = base.bandpass(fs, x, lo, hi)
            if use_a:
                y = base.a_weight(fs, y)
            values[product], backgrounds[product] = event_energy(fs, y, times[product])
        d50, d50_lo, d50_hi = bootstrap_delta(values["东德基准"], values["富瑞初始"], 50, rng)
        d90, d90_lo, d90_hi = bootstrap_delta(values["东德基准"], values["富瑞初始"], 90, rng)
        rows.append({
            "method": method,
            "dd_common_db": float(np.percentile(values["东德基准"], 50)),
            "fu_common_db": float(np.percentile(values["富瑞初始"], 50)),
            "fu_minus_dd_common_db": d50,
            "common_95ci_low_db": d50_lo,
            "common_95ci_high_db": d50_hi,
            "dd_loud_db": float(np.percentile(values["东德基准"], 90)),
            "fu_loud_db": float(np.percentile(values["富瑞初始"], 90)),
            "fu_minus_dd_loud_db": d90,
            "loud_95ci_low_db": d90_lo,
            "loud_95ci_high_db": d90_hi,
        })
        background_rows.append({
            "method": method,
            "dd_background_dbfs": float(np.median(backgrounds["东德基准"])),
            "fu_background_dbfs": float(np.median(backgrounds["富瑞初始"])),
            "fu_minus_dd_background_db": float(np.median(backgrounds["富瑞初始"]) - np.median(backgrounds["东德基准"])),
        })

    with OLD_EVENTS.open(encoding="utf-8-sig") as f:
        old = list(csv.DictReader(f))
    old_dd = np.array([float(r["excess_dbfs"]) for r in old if r["product"] == "东德竞品" and int(r["speed_rpm"]) == 800])
    old_fu = np.array([float(r["excess_dbfs"]) for r in old if r["product"] == "富瑞自研" and int(r["speed_rpm"]) == 800])
    d50, d50_lo, d50_hi = bootstrap_delta(old_dd, old_fu, 50, rng)
    d90, d90_lo, d90_hi = bootstrap_delta(old_dd, old_fu, 90, rng)
    rows.append({
        "method": "旧版独立事件检测（复核）",
        "dd_common_db": float(np.percentile(old_dd, 50)),
        "fu_common_db": float(np.percentile(old_fu, 50)),
        "fu_minus_dd_common_db": d50,
        "common_95ci_low_db": d50_lo,
        "common_95ci_high_db": d50_hi,
        "dd_loud_db": float(np.percentile(old_dd, 90)),
        "fu_loud_db": float(np.percentile(old_fu, 90)),
        "fu_minus_dd_loud_db": d90,
        "loud_95ci_low_db": d90_lo,
        "loud_95ci_high_db": d90_hi,
    })

    with (OUT / "800rpm_method_validation.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / "800rpm_background_validation.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(background_rows[0]))
        writer.writeheader()
        writer.writerows(background_rows)

    labels = [r["method"].replace("冲击能量", "").replace("（复核）", "") for r in rows]
    common = np.array([r["fu_minus_dd_common_db"] for r in rows])
    loud = np.array([r["fu_minus_dd_loud_db"] for r in rows])
    y = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), sharey=True)
    for ax, values, lo_key, hi_key, title in [
        (axes[0], common, "common_95ci_low_db", "common_95ci_high_db", "常见咚声"),
        (axes[1], loud, "loud_95ci_low_db", "loud_95ci_high_db", "较响咚声"),
    ]:
        for i, (value, row) in enumerate(zip(values, rows)):
            uncertain = float(row[lo_key]) <= 0 <= float(row[hi_key])
            color = "#15803D" if value < 0 else "#C2410C"
            ax.barh(i, abs(value), color=color, alpha=0.35 if uncertain else 0.9)
            label = f"{'低' if value < 0 else '高'} {abs(value):.1f} dB" + ("（不确定）" if uncertain else "")
            ax.text(abs(value) + 0.18, i, label, va="center", fontsize=8)
        ax.set_yticks(y, labels)
        ax.set_xlabel("差值大小 dB（绿=富瑞较低，红=富瑞较高）")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.2)
        ax.set_xlim(0, max(10, float(np.max(np.abs(values))) + 2.5))
    fig.suptitle("800 rpm 多方法一致性验证（浅色表示95%区间跨过无差异）", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "plots" / "05_800rpm多方法一致性验证.png", dpi=180)
    plt.close(fig)

    hash_rows = []
    for product, path in paths.items():
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        hash_rows.append({"product": product, "speed_rpm": 800, "wav": str(path), "sha256": digest.hexdigest()})
    with (OUT / "source_file_hashes.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(hash_rows[0]))
        writer.writeheader()
        writer.writerows(hash_rows)

    for row in rows:
        print(row)
    for row in background_rows:
        print(row)


if __name__ == "__main__":
    main()
