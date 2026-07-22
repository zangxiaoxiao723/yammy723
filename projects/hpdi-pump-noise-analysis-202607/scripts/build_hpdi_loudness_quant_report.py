from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(r"C:\Users\admin\Documents\Codex\2026-07-13\yi-j")
SRC = ROOT / "outputs" / "hpdi_thump_loudness_quant"
OUT = ROOT / "outputs" / "hpdi_thump_loudness_quant"
PDF = OUT / "HPDI低温泵咚声响度量化对比报告.pdf"


def register_font() -> tuple[str, str]:
    body, bold = "NotoSansSC", "SimHei"
    try:
        pdfmetrics.registerFont(TTFont(body, r"C:\Windows\Fonts\NotoSansSC-VF.ttf"))
    except Exception:
        body = "SimSun"
        pdfmetrics.registerFont(TTFont(body, r"C:\Windows\Fonts\simsun.ttc"))
    try:
        pdfmetrics.registerFont(TTFont(bold, r"C:\Windows\Fonts\simhei.ttf"))
    except Exception:
        bold = body
    return body, bold


BODY, BOLD = register_font()
ST = getSampleStyleSheet()
ST.add(ParagraphStyle("TitleCN", fontName=BOLD, fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=10))
ST.add(ParagraphStyle("SubCN", fontName=BODY, fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"), spaceAfter=12))
ST.add(ParagraphStyle("H", fontName=BOLD, fontSize=14, leading=18, spaceBefore=7, spaceAfter=5))
ST.add(ParagraphStyle("B", fontName=BODY, fontSize=8.8, leading=12.2, spaceAfter=4))
ST.add(ParagraphStyle("Note", fontName=BODY, fontSize=7.6, leading=10.4, textColor=colors.HexColor("#4B5563"), spaceAfter=3))
ST.add(ParagraphStyle("Cap", fontName=BODY, fontSize=7.8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#374151"), spaceAfter=5))


def p(text: str, style: str = "B") -> Paragraph:
    return Paragraph(text, ST[style])


def load_csv(name: str) -> list[dict[str, str]]:
    with (SRC / name).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def table(rows: list[list[str]], widths: list[float], size: float = 7.2) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY),
                ("FONTNAME", (0, 0), (-1, 0), BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), size),
                ("LEADING", (0, 0), (-1, -1), size + 1.2),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def img(path: Path, max_w: float, max_h: float) -> Image:
    with PILImage.open(path) as im:
        w, h = im.size
    s = min(max_w / w, max_h / h)
    return Image(str(path), width=w * s, height=h * s)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(BODY, 7)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(doc.leftMargin, 0.55 * cm, "HPDI低温泵咚声响度量化对比报告")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.55 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def main() -> None:
    summary = load_csv("thump_loudness_summary.csv")
    comp = load_csv("matched_speed_comparison.csv")

    story = [
        p("HPDI低温泵咚声响度量化对比报告", "TitleCN"),
        p("目标：量化富瑞自研泵与东德竞品的泵本体“咚声”大小，用于后续标定优化前后对比", "SubCN"),
        p("1. 量化口径", "H"),
        p("本版报告只关注“声音大不大”。算法不使用全频总声压直接评价泵本体，而是在 45-650 Hz 低中频冲击带内检测泵往复咚声事件，并对每个事件扣除前后局部背景。这样可以尽量排除台架稳态嗡声；高频排气尖声只作为污染筛选，不参与咚声响度计算。"),
        p("同一手机、同一位置、同一录音方式下，dBFS 可用于相对比较。数值越低代表咚声越小；在匹配转速下，“富瑞-东德”差值大于 0 表示富瑞更响。", "Note"),
        p("推荐后续验收主看 P90 和 P95：P50 是典型咚声，P90/P95 更接近人耳觉得突兀、吵的较响咚声。", "B"),
    ]

    comp_rows = [["转速", "P50差值", "P90差值", "P95差值", "当前判断"]]
    for r in comp:
        p90 = float(r["fu_minus_dd_p90_db"])
        p95 = float(r["fu_minus_dd_p95_db"])
        if p90 > 1.0 or p95 > 1.0:
            verdict = "富瑞偏响，需要优化"
        elif p90 < -1.0 and p95 < -1.0:
            verdict = "富瑞更小"
        else:
            verdict = "基本接近"
        comp_rows.append(
            [
                f"{r['speed_rpm']} rpm",
                f"{float(r['fu_minus_dd_typical_db']):+.2f} dB",
                f"{p90:+.2f} dB",
                f"{p95:+.2f} dB",
                verdict,
            ]
        )
    story += [
        p("2. 匹配转速下富瑞相对竞品差值", "H"),
        table(comp_rows, [3 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 6 * cm], 8),
        p("表 1 富瑞-东德咚声响度差值。正值表示富瑞更响，负值表示富瑞更小。", "Cap"),
        img(SRC / "plots" / "富瑞相对竞品咚声响度差值.png", 23.5 * cm, 10 * cm),
        p("图 1 富瑞相对竞品的咚声响度差值。后续标定目标是让 P90/P95 差值降到 0 dB 以下，最好低于 -2 dB。", "Cap"),
    ]

    abs_rows = [["产品", "转速", "事件数", "P50 dBFS", "P90 dBFS", "P95 dBFS", "相对背景P50"]]
    for r in sorted(summary, key=lambda x: (x["product"], int(x["speed_rpm"]))):
        abs_rows.append(
            [
                r["product"],
                f"{r['speed_rpm']} rpm",
                r["event_count"],
                f"{float(r['typical_p50_dbfs']):.2f}",
                f"{float(r['loud_p90_dbfs']):.2f}",
                f"{float(r['loud_p95_dbfs']):.2f}",
                f"{float(r['typical_prominence_db']):.2f}",
            ]
        )
    story += [
        PageBreak(),
        p("3. 各样本咚声响度绝对指标", "H"),
        img(SRC / "plots" / "竞品_vs_富瑞_咚声响度绝对指标.png", 24 * cm, 11.8 * cm),
        p("图 2 各转速咚声响度绝对指标。曲线越低代表咚声越小；P90/P95 更能反映较响咚声。", "Cap"),
        table(abs_rows, [3 * cm, 2.1 * cm, 1.8 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3.0 * cm], 6.8),
        p("表 2 当前初始状态咚声响度基准表。后续每轮标定后，按同一口径重跑并与本表对比。", "Cap"),
    ]

    story += [
        PageBreak(),
        p("4. 当前结论与后续判定方法", "H"),
        p("当前初始状态下，富瑞自研泵在多个匹配转速的较响咚声指标上高于东德竞品，尤其 900 rpm：P90 高约 +5.83 dB，P95 高约 +3.39 dB。这与主观听感“竞品咚声更小、富瑞更响”一致。"),
        p("700 rpm：富瑞典型咚声 P50 比竞品低约 -3.19 dB，但较响咚声 P90/P95 分别高约 +2.82 / +3.94 dB，说明普通咚声不一定大，但偶发较响冲击更突出。"),
        p("800 rpm：富瑞与竞品基本持平，P90 约 +0.04 dB，P95 约 -0.36 dB，可作为接近竞品水平的参考点。"),
        p("900 rpm：富瑞明显偏响，是优先优化点。"),
        p("1125 rpm：富瑞 P90/P95 约高 +2.2 dB，但 P50 差值异常大，说明该段事件分布或工况可能不同，建议作为提示项，不单独作为定论。"),
        p("建议后续每次调整标定后，固定同一录音位置和工况，重跑本指标。判定目标：P90/P95 差值小于 0 dB 表示不比竞品响；小于 -2 dB 表示有明显优势；若只降低 P50 但 P90/P95 仍高，主观听感仍可能觉得冲击大。"),
    ]

    doc = SimpleDocTemplate(
        str(PDF),
        pagesize=landscape(A4),
        leftMargin=1.3 * cm,
        rightMargin=1.3 * cm,
        topMargin=1.1 * cm,
        bottomMargin=1.0 * cm,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(PDF)


if __name__ == "__main__":
    main()
