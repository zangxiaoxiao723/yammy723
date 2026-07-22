from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
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
PLOTS = SRC / "plots"
PDF = SRC / "HPDI低温泵咚声响度量化对比报告_决策版.pdf"
MAIN_PLOT = PLOTS / "富瑞相对竞品_P90_P95主指标.png"


def register_font() -> tuple[str, str]:
    candidates = [
        (r"C:\Windows\Fonts\msyh.ttc", "MicrosoftYaHei"),
        (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),
        (r"C:\Windows\Fonts\NotoSansSC-VF.ttf", "NotoSansSC"),
    ]
    body = "Helvetica"
    for path, name in candidates:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont(name, path))
            body = name
            break
    bold = body
    if Path(r"C:\Windows\Fonts\simhei.ttf").exists():
        pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))
        bold = "SimHei"
    return body, bold


BODY, BOLD = register_font()
ST = getSampleStyleSheet()
ST.add(ParagraphStyle("TitleCN", fontName=BOLD, fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=8))
ST.add(ParagraphStyle("SubCN", fontName=BODY, fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"), spaceAfter=12))
ST.add(ParagraphStyle("H", fontName=BOLD, fontSize=14, leading=18, spaceBefore=6, spaceAfter=5))
ST.add(ParagraphStyle("B", fontName=BODY, fontSize=9, leading=12.5, spaceAfter=4))
ST.add(ParagraphStyle("Small", fontName=BODY, fontSize=7.5, leading=10, textColor=colors.HexColor("#4B5563"), spaceAfter=3))
ST.add(ParagraphStyle("Cap", fontName=BODY, fontSize=7.8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#374151"), spaceAfter=5))


def p(text: str, style: str = "B") -> Paragraph:
    return Paragraph(text, ST[style])


def load_csv(name: str) -> list[dict[str, str]]:
    with (SRC / name).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def make_table(rows: list[list[str]], widths: list[float], size: float = 7.6) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY),
                ("FONTNAME", (0, 0), (-1, 0), BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), size),
                ("LEADING", (0, 0), (-1, -1), size + 1.3),
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
    return table


def img(path: Path, max_w: float, max_h: float) -> Image:
    with PILImage.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    return Image(str(path), width=w * scale, height=h * scale)


def make_main_plot(comp: list[dict[str, str]]) -> None:
    speeds = [int(r["speed_rpm"]) for r in comp]
    p90 = [float(r["fu_minus_dd_p90_db"]) for r in comp]
    p95 = [float(r["fu_minus_dd_p95_db"]) for r in comp]
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(9.5, 4.4), dpi=180)
    ax.axhspan(-2, 0, color="#D1FAE5", alpha=0.55, label="可接受/接近竞品区间")
    ax.axhline(0, color="#111827", linewidth=1.0)
    ax.axhline(-2, color="#059669", linewidth=1.0, linestyle="--")
    ax.plot(speeds, p90, marker="o", linewidth=2.4, color="#E11D48", label="P90 较响咚声")
    ax.plot(speeds, p95, marker="s", linewidth=2.4, color="#7C3AED", label="P95 高响度咚声")
    for x, y in zip(speeds, p90):
        ax.annotate(f"{y:+.1f}", (x, y), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8)
    for x, y in zip(speeds, p95):
        ax.annotate(f"{y:+.1f}", (x, y), xytext=(0, -13), textcoords="offset points", ha="center", fontsize=8)
    ax.set_title("富瑞相对竞品咚声响度差值：主判定看 P90 / P95")
    ax.set_xlabel("转速 rpm")
    ax.set_ylabel("富瑞 - 竞品，dB；正值表示富瑞更响")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", frameon=True)
    ax.set_xticks(speeds)
    fig.tight_layout()
    MAIN_PLOT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(MAIN_PLOT)
    plt.close(fig)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(BODY, 7)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(doc.leftMargin, 0.55 * cm, "HPDI低温泵咚声响度量化对比报告")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.55 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def verdict(p90: float, p95: float) -> str:
    if p90 <= -2 and p95 <= -2:
        return "明显优于竞品"
    if p90 <= 0 and p95 <= 0:
        return "不比竞品响"
    if p90 > 1 or p95 > 1:
        return "偏响，需要优化"
    return "接近竞品"


def main() -> None:
    comp = load_csv("matched_speed_comparison.csv")
    summary = load_csv("thump_loudness_summary.csv")
    make_main_plot(comp)

    comp_rows = [["转速", "P50 典型咚声", "P90 较响咚声", "P95 高响度咚声", "当前判断"]]
    for r in comp:
        p90 = float(r["fu_minus_dd_p90_db"])
        p95 = float(r["fu_minus_dd_p95_db"])
        comp_rows.append(
            [
                f"{r['speed_rpm']} rpm",
                f"{float(r['fu_minus_dd_typical_db']):+.2f} dB",
                f"{p90:+.2f} dB",
                f"{p95:+.2f} dB",
                verdict(p90, p95),
            ]
        )

    summary_rows = [["产品", "转速", "事件数", "P50 dBFS", "P90 dBFS", "P95 dBFS", "突显量P50"]]
    for r in sorted(summary, key=lambda x: (x["product"], int(x["speed_rpm"]))):
        summary_rows.append(
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

    story = [
        p("HPDI低温泵咚声响度量化对比报告", "TitleCN"),
        p("目标：把“竞品听起来更小、我们后续要调得更小”转成可复跑的 dB 指标", "SubCN"),
        p("1. 本版结论", "H"),
        p("本版报告不再把重点放在“咚几声”或相位解释上，而是只回答一个工程问题：泵本体有节奏的咚声到底比竞品大多少。由于三组视频使用同一手机、同一位置和角度，报告采用相对 dBFS 差值作为后续调泵对比指标。"),
        p("主判定指标建议固定为 P90 和 P95：P50 代表典型咚声，但用户主观觉得“吵、突兀”的往往是较响的那一小部分冲击声，所以 P90/P95 更适合作为验收口径。"),
        p("当前初始状态下，富瑞自研泵在多个匹配转速的 P90/P95 指标上高于东德竞品，尤其 900 rpm：P90 高约 +5.83 dB，P95 高约 +3.39 dB。这可以量化支撑“竞品咚声更小、富瑞当前偏响”的主观判断。"),
        p("2. 后续调试判定口径", "H"),
        make_table(
            [
                ["指标", "判定含义"],
                ["富瑞 - 竞品 <= 0 dB", "不比竞品响，可认为达到竞品水平"],
                ["富瑞 - 竞品 <= -2 dB", "有比较明确的优势，建议作为优化目标"],
                ["P90/P95 降低但 P50 不变", "主观刺耳感可能已经改善，仍值得保留"],
                ["P50 降低但 P90/P95 仍高", "典型声变小了，但偶发重击仍会让人觉得吵"],
            ],
            [5 * cm, 17 * cm],
            8.2,
        ),
        Spacer(1, 0.25 * cm),
        p("3. 匹配转速下富瑞相对竞品差值", "H"),
        make_table(comp_rows, [3 * cm, 3.1 * cm, 3.1 * cm, 3.1 * cm, 5.6 * cm], 8),
        p("表中正值表示富瑞更响，负值表示富瑞更小。后续每次调整后，建议仍按同一口径复跑并覆盖此表。", "Cap"),
        PageBreak(),
        img(MAIN_PLOT, 24 * cm, 11 * cm),
        p("绿色区间表示已达到或接近竞品目标；0 dB 以上说明富瑞仍偏响。900 rpm 是当前最明确的优先优化点。", "Cap"),
        p("4. 干扰声排除方式", "H"),
        p("计算时没有直接拿全频总声压比较。算法先在 45-650 Hz 低中频冲击带内寻找泵往复运动咚声事件，再对每个事件用前后局部背景做扣除，从而削弱台架稳定嗡声影响。高频 1800-9000 Hz 的尖锐排气声只作为污染检查，不进入咚声响度主指标。"),
        p("因此，这组数据更接近“泵本体咚声有多大”，而不是“现场环境总噪声有多大”。但它仍是录音相对指标，不等同于声级计的绝对 dB(A) 认证值。"),
        PageBreak(),
        p("5. 当前基准数据", "H"),
        img(SRC / "plots" / "竞品_vs_富瑞_咚声响度绝对指标.png", 24 * cm, 11.2 * cm),
        p("绝对 dBFS 越低表示录音中咚声越小。不同视频之间建议优先看同转速、同工况的相对差值。", "Cap"),
        make_table(summary_rows, [3 * cm, 2.1 * cm, 1.8 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm], 6.8),
        p("该表作为初始状态基准。后续每轮改动后，若同位置、同手机、同转速复测，可直接与本表及匹配差值表比较。", "Cap"),
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
