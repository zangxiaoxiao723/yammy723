from __future__ import annotations

import csv
import hashlib
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "hpdi_baseline_v2"
V3 = ROOT / "outputs" / "hpdi_followup_v3"
WAV = ROOT / "work" / "hpdi_followup_v3" / "wav"
AUDIT = V3 / "release_audit"
AUDIT.mkdir(parents=True, exist_ok=True)

BASELINE_JSON = BASE / "workbook_payload.json"
FIXED_JSON = V3 / "combined_fixed_baseline_payload.json"
WORKBOOK = V3 / "HPDI泵声音固定基准对比工具_内部复核_禁止外发.xlsx"
CORRECTION_DOC = V3 / "HPDI后续声音分析口径复核与修正说明_内部.docx"

GOLDEN_HASHES = {
    "workbook_payload.json": "cee9e5420ac7e9464a9bb64b5a8f68dca8be83dbda0445e32e1ac7ffb572c3df",
    "event_details.csv": "82f2b1dc85d2b285d70a89a336a01f0bcf555a427a2d8469b56dac12e852dd06",
    "baseline_comparison.csv": "4d719edfed208204afe641d0357134af1d56db721fdfeea024e30148d8321e01",
    "test_registry.csv": "a427cf00eb9dff139da9fb217a12d4e01c3cfbb90878f934e329660524d9e88e",
}


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
        return "".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def xlsx_xml_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return "\n".join(
            z.read(name).decode("utf-8", errors="replace")
            for name in z.namelist()
            if name.endswith(".xml")
        )


def add_check(checks, name, passed, detail):
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> None:
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    fixed = json.loads(FIXED_JSON.read_text(encoding="utf-8"))
    checks = []

    for name, expected_hash in GOLDEN_HASHES.items():
        actual_hash = sha256(BASE / name)
        add_check(checks, f"V2黄金文件哈希锁定:{name}", actual_hash == expected_hash, actual_hash)

    baseline_ids = [r["series_id"] for r in baseline["registry"]]
    fixed_by_id = {r["series_id"]: r for r in fixed["registry"]}
    baseline_fields = [
        "series_id", "test_date", "product", "configuration", "speed_rpm", "duration_s",
        "event_count", "common_thump_est_dba", "loud_thump_est_dba", "common_comparison",
        "loud_comparison", "common_difference_db", "loud_difference_db", "result",
    ]
    baseline_mismatches = []
    for old in baseline["registry"]:
        new = fixed_by_id.get(old["series_id"])
        if not new:
            baseline_mismatches.append(f"missing:{old['series_id']}")
            continue
        for field in baseline_fields:
            a, b = old.get(field), new.get(field)
            if isinstance(a, float) and isinstance(b, float):
                equal = abs(a - b) <= 1e-12
            else:
                equal = a == b
            if not equal:
                baseline_mismatches.append(f"{old['series_id']}:{field}:{a!r}!={b!r}")
    add_check(checks, "V2基准登记值逐字段锁定", not baseline_mismatches, baseline_mismatches or "10组基准全部一致")

    env_mismatch = [sid for sid in baseline["envelope_columns"] if baseline["envelope_columns"][sid] != fixed["envelope_columns"].get(sid)]
    rep_mismatch = [key for key in baseline["representative_columns"] if baseline["representative_columns"][key] != fixed["representative_columns"].get(key)]
    add_check(checks, "V2基准包络逐点锁定", not env_mismatch, env_mismatch or f"{len(baseline['envelope_columns'])}组逐点一致")
    add_check(checks, "V2代表咚声曲线逐点锁定", not rep_mismatch, rep_mismatch or f"{len(baseline['representative_columns'])}列逐点一致")

    baseline_events = list(csv.DictReader((BASE / "event_details.csv").open(encoding="utf-8-sig")))
    followup_events = list(csv.DictReader((V3 / "followup_event_details.csv").open(encoding="utf-8-sig")))
    grouped = defaultdict(list)
    for row in baseline_events + followup_events:
        grouped[row["series_id"]].append(float(row["event_energy_est_dba"]))

    event_mismatch = []
    for row in fixed["registry"]:
        sid = row["series_id"]
        values = grouped.get(sid, [])
        if not values:
            event_mismatch.append(f"missing-events:{sid}")
            continue
        common = percentile(values, 0.50)
        loud = percentile(values, 0.90)
        if abs(common - float(row["common_thump_est_dba"])) > 1e-9:
            event_mismatch.append(f"{sid}:common:{common}!={row['common_thump_est_dba']}")
        if abs(loud - float(row["loud_thump_est_dba"])) > 1e-9:
            event_mismatch.append(f"{sid}:loud:{loud}!={row['loud_thump_est_dba']}")
        if len(values) != int(row["event_count"]):
            event_mismatch.append(f"{sid}:count:{len(values)}!={row['event_count']}")
    add_check(checks, "20组指标由逐事件数据独立重算", not event_mismatch, event_mismatch or "常见声、较响声和事件数全部一致")

    dd_by_speed = {int(r["speed_rpm"]): r for r in fixed["registry"] if r["product"] == "东德基准"}
    delta_mismatch = []
    for row in fixed["registry"]:
        if row["product"] != "富瑞初始":
            continue
        dd = dd_by_speed.get(int(row["speed_rpm"]))
        if not dd:
            continue
        common = float(row["common_thump_est_dba"]) - float(dd["common_thump_est_dba"])
        loud = float(row["loud_thump_est_dba"]) - float(dd["loud_thump_est_dba"])
        if abs(abs(common) - float(row["common_difference_db"])) > 1e-9:
            delta_mismatch.append(f"{row['speed_rpm']}:common")
        if abs(abs(loud) - float(row["loud_difference_db"])) > 1e-9:
            delta_mismatch.append(f"{row['speed_rpm']}:loud")
    add_check(checks, "V2同转速差值独立复算", not delta_mismatch, delta_mismatch or "700/800/900/1125 rpm全部一致")

    ids = [r["series_id"] for r in fixed["registry"]]
    add_check(checks, "测试编号唯一", len(ids) == len(set(ids)) == 20, f"rows={len(ids)}, unique={len(set(ids))}")
    add_check(checks, "固定基准位于合并数据前10组", ids[:10] == baseline_ids, ids[:10])

    xlsx_text = xlsx_xml_text(WORKBOOK)
    add_check(checks, "Excel含基准复核与主对比工作表", all(x in xlsx_text for x in ["既定基准结果", "对比面板", "测试索引"]), "检查工作表名称")
    add_check(checks, "Excel未把背景归一化写成主声级", "背景归一化声级" not in xlsx_text, "禁用词扫描")
    add_check(checks, "Excel包含基准锁定警示", "禁止重新归一化" in xlsx_text and "手机自动增益" in xlsx_text, "警示文本存在")

    correction_text = docx_text(CORRECTION_DOC)
    required_correction = ["高于东德7.6 dB", "高于东德5.1 dB", "不足以量化证明", "永久锁定"]
    add_check(checks, "修正说明包含关键结论与边界", all(x in correction_text for x in required_correction), required_correction)
    forbidden_claims = ["交付泵声音好一点有依据", "重咚明显收敛", "较响咚声优于东德"]
    add_check(checks, "修正说明无已撤销改善表述", not any(x in correction_text for x in forbidden_claims), forbidden_claims)

    wav_rows = []
    for path in sorted(WAV.glob("*.wav")):
        wav_rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    add_check(checks, "后续10段WAV完整存在", len(wav_rows) == 10 and all(r["bytes"] > 44 for r in wav_rows), {"count": len(wav_rows), "min_bytes": min(r["bytes"] for r in wav_rows)})
    with (AUDIT / "followup_wav_hashes.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(wav_rows)

    result = {
        "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "checks_passed": sum(c["passed"] for c in checks),
        "checks_total": len(checks),
        "checks": checks,
        "file_hashes": {
            "baseline_payload": sha256(BASELINE_JSON),
            "fixed_payload": sha256(FIXED_JSON),
            "workbook": sha256(WORKBOOK),
            "correction_doc": sha256(CORRECTION_DOC),
        },
    }
    (AUDIT / "release_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# HPDI声音分析发布审计",
        "",
        f"- 状态：**{result['status']}**",
        f"- 通过：{result['checks_passed']}/{result['checks_total']}",
        "- 说明：技术审计通过不等于客户批准；后续无同步分贝仪的数据仍禁止作为客户绝对声级结论。",
        "",
        "## 检查项",
        "",
    ]
    for check in checks:
        lines.append(f"- [{'x' if check['passed'] else ' '}] {check['name']}：{check['detail']}")
    (AUDIT / "release_audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
