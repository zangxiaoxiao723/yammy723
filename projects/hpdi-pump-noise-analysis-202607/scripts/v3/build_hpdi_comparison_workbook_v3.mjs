import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/admin/Documents/Codex/2026-07-13/yi-j";
const payload = JSON.parse(await fs.readFile(`${root}/outputs/hpdi_followup_v3/combined_fixed_baseline_payload.json`, "utf8"));
const baselinePayload = JSON.parse(await fs.readFile(`${root}/outputs/hpdi_baseline_v2/workbook_payload.json`, "utf8"));
const outputDir = `${root}/outputs/hpdi_followup_v3`;
const previewDir = `${root}/work/hpdi_excel_v2/previews`;
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const wb = Workbook.create();
const guide = wb.worksheets.add("使用说明");
const baselineReview = wb.worksheets.add("既定基准结果");
const dashboard = wb.worksheets.add("对比面板");
const registry = wb.worksheets.add("测试索引");
const envelope = wb.worksheets.add("包络曲线数据");
const reps = wb.worksheets.add("代表咚声数据");
const calc = wb.worksheets.add("图表计算");
console.log("stage:sheets");

const C = {
  ink: "#172033",
  teal: "#007C91",
  orange: "#C2410C",
  green: "#15803D",
  paleGreen: "#DCFCE7",
  paleGold: "#FEF3C7",
  paleRed: "#FEE2E2",
  paleBlue: "#E6F3F5",
  gray: "#64748B",
  line: "#D8DEE8",
  white: "#FFFFFF",
};

function title(sheet, range, text) {
  sheet.mergeCells(range);
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[text]];
  cell.format = {
    fill: C.ink,
    font: { bold: true, color: C.white, size: 18 },
    verticalAlignment: "center",
    horizontalAlignment: "left",
  };
  sheet.getRange(range).format.rowHeight = 34;
}

function sectionHeader(range) {
  range.format = {
    fill: C.paleBlue,
    font: { bold: true, color: C.ink },
    borders: { preset: "outside", style: "thin", color: C.line },
    verticalAlignment: "center",
  };
}

function excelCol(index) {
  let n = index + 1;
  let result = "";
  while (n > 0) {
    n -= 1;
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26);
  }
  return result;
}

for (const sheet of [guide, baselineReview, dashboard, registry, envelope, reps, calc]) {
  sheet.showGridLines = false;
}

// Usage guide.
title(guide, "A1:H1", "HPDI 泵声音固定基准对比工具");
console.log("stage:guide-title");
guide.getRange("A3:H3").merge();
guide.getRange("A3").values = [["用途：东德和富瑞初始基准数值、算法及校准偏移全部保持V2不变；后续测试只按同一固定算法追加。"]];
guide.getRange("A3").format = { font: { bold: true, color: C.teal, size: 12 }, wrapText: true };
console.log("stage:guide-intro");
guide.getRange("A5:B10").values = [
  ["操作", "说明"],
  ["1. 复核旧基准", "先看“既定基准结果”。东德与富瑞初始的结果完全沿用V2，不受后续算法调整影响。"],
  ["2. 选择测试", "在“对比面板”顶部选择最多6组。选择东德900和富瑞初始900时，结果必须与V2一致。"],
  ["3. 看常见咚声", "表示大多数正常周期的典型冲击，不要求客户理解统计术语。"],
  ["4. 看较响咚声", "表示一段测试中偏响的那部分周期，是调泵时优先压低的对象。"],
  ["5. 追加新测试", "由分析脚本把新测试追加到“测试索引”和两个曲线数据页，原有东德基准保持不变。"],
];
console.log("stage:guide-values");
sectionHeader(guide.getRange("A5:B5"));
console.log("stage:guide-header");
guide.getRange("A6:B10").format = { wrapText: true, verticalAlignment: "center" };
guide.getRange("A5:B10").format.borders = { preset: "all", style: "thin", color: C.line };
console.log("stage:guide-table-format");
guide.getRange("A12:H14").merge();
guide.getRange("A12").values = [["重要：本工具不再对既定基准做逐段背景平移。无分贝仪的跨日期视频虽然按相同固定算法计算，但可能受手机自动增益影响，后续结果属于工程估算；出现明显改善或恶化时必须用同步分贝仪复测确认。"]];
guide.getRange("A12").format = { fill: C.paleGold, font: { color: C.ink }, wrapText: true, verticalAlignment: "center" };
console.log("stage:guide-note");
guide.getRange("A1:A15").format.columnWidth = 18;
guide.getRange("B1:B15").format.columnWidth = 72;
guide.getRange("C1:H15").format.columnWidth = 11;
guide.getRange("A5:B10").format.rowHeight = 34;
console.log("stage:guide");

// The original V2 baseline is immutable. This sheet is the authoritative old-result reference.
title(baselineReview, "A1:K1", "既定基准结果（V2原口径，不随后续算法变化）");
baselineReview.getRange("A3:K3").merge();
baselineReview.getRange("A3").values = [["固定偏移来自富瑞初始1000 rpm视频中的分贝仪画面。以下结果与上一版工具完全一致；其中900 rpm富瑞初始常见咚声高于东德7.6 dB，较响咚声高于东德5.1 dB。"]];
baselineReview.getRange("A3").format = { fill: C.paleGold, font: { bold: true, color: C.ink }, wrapText: true, verticalAlignment: "center" };
const baselineHeaders = ["测试编号", "日期", "产品", "转速 rpm", "常见咚声 估算dB(A)", "较响咚声 估算dB(A)", "常见声相对东德", "较响声相对东德", "常见差值 dB", "较响差值 dB", "结论"];
const baselineRows = baselinePayload.registry.map((r) => [
  r.series_id, r.test_date, r.product, r.speed_rpm, r.common_thump_est_dba, r.loud_thump_est_dba,
  r.common_comparison, r.loud_comparison, r.common_difference_db, r.loud_difference_db, r.result,
]);
baselineReview.getRangeByIndexes(4, 0, 1, baselineHeaders.length).values = [baselineHeaders];
baselineReview.getRangeByIndexes(5, 0, baselineRows.length, baselineHeaders.length).values = baselineRows;
sectionHeader(baselineReview.getRange("A5:K5"));
baselineReview.getRange(`A5:K${baselineRows.length + 5}`).format.borders = { preset: "inside", style: "thin", color: C.line };
baselineReview.getRange(`D6:D${baselineRows.length + 5}`).format.numberFormat = "0";
baselineReview.getRange(`E6:F${baselineRows.length + 5}`).format.numberFormat = "0.0";
baselineReview.getRange(`I6:J${baselineRows.length + 5}`).format.numberFormat = "0.0";
baselineReview.getRange(`A1:A${baselineRows.length + 5}`).format.columnWidth = 25;
baselineReview.getRange(`B1:D${baselineRows.length + 5}`).format.columnWidth = 14;
baselineReview.getRange(`E1:J${baselineRows.length + 5}`).format.columnWidth = 20;
baselineReview.getRange(`K1:K${baselineRows.length + 5}`).format.columnWidth = 20;
baselineReview.freezePanes.freezeRows(5);
console.log("stage:baseline-review");

// Registry data.
const registryHeaders = ["测试编号", "测试日期", "产品", "状态/配置", "简称", "转速 rpm", "分组", "时长 s", "咚声数", "常见咚声 估算dB(A)", "较响咚声 估算dB(A)", "常见声相对东德", "较响声相对东德", "常见差值大小 dB", "较响差值大小 dB", "常见声相对富瑞初始", "较响声相对富瑞初始", "常见差值/初始 dB", "较响差值/初始 dB", "超过东德较响门槛 %", "声级判断", "有分贝仪", "主观备注", "备注"];
const registryRows = payload.registry.map((r) => [
  r.series_id, r.test_date, r.product, r.configuration, r.short_label || r.product, r.speed_rpm, r.run || `${r.speed_rpm}rpm`, r.duration_s, r.event_count,
  r.common_thump_est_dba, r.loud_thump_est_dba, r.common_comparison, r.loud_comparison,
  r.common_difference_db, r.loud_difference_db, r.initial_common_comparison || "不适用", r.initial_loud_comparison || "不适用",
  r.initial_common_difference_db, r.initial_loud_difference_db, r.above_dd_loud_share_pct, r.result, r.has_meter, r.subjective || "", r.notes,
]);
registry.getRangeByIndexes(0, 0, 1, registryHeaders.length).values = [registryHeaders];
registry.getRangeByIndexes(1, 0, registryRows.length, registryHeaders.length).values = registryRows;
sectionHeader(registry.getRange(`A1:X1`));
registry.getRange(`F2:F${registryRows.length + 1}`).format.numberFormat = "0";
registry.getRange(`H2:H${registryRows.length + 1}`).format.numberFormat = "0.0";
registry.getRange(`I2:I${registryRows.length + 1}`).format.numberFormat = "0";
registry.getRange(`J2:K${registryRows.length + 1}`).format.numberFormat = "0.0";
registry.getRange(`N2:T${registryRows.length + 1}`).format.numberFormat = "0.0";
registry.getRange(`A1:X${registryRows.length + 1}`).format.borders = { preset: "inside", style: "thin", color: C.line };
registry.getRange(`A1:X${registryRows.length + 1}`).format.verticalAlignment = "center";
registry.getRange(`A1:A${registryRows.length + 1}`).format.columnWidth = 24;
registry.getRange(`B1:E${registryRows.length + 1}`).format.columnWidth = 18;
registry.getRange(`F1:I${registryRows.length + 1}`).format.columnWidth = 11;
registry.getRange(`J1:T${registryRows.length + 1}`).format.columnWidth = 19;
registry.getRange(`U1:W${registryRows.length + 1}`).format.columnWidth = 18;
registry.getRange(`X1:X${registryRows.length + 1}`).format.columnWidth = 55;
registry.getRange(`W2:X${registryRows.length + 1}`).format.wrapText = true;
registry.freezePanes.freezeRows(1);
console.log("stage:registry");

// Raw curve sheets.
const seriesIds = payload.registry.map((r) => r.series_id);
const envMatrix = [["时间 s", ...seriesIds]];
for (let i = 0; i < payload.envelope_time_s.length; i++) {
  envMatrix.push([payload.envelope_time_s[i], ...seriesIds.map((id) => {
    const value = payload.envelope_columns[id][i];
    return Number.isFinite(value) ? value : null;
  })]);
}
envelope.getRangeByIndexes(0, 0, envMatrix.length, envMatrix[0].length).values = envMatrix;
sectionHeader(envelope.getRangeByIndexes(0, 0, 1, envMatrix[0].length));
envelope.getRangeByIndexes(1, 0, envMatrix.length - 1, envMatrix[0].length).format.numberFormat = "0.0";
envelope.getRange(`A1:A${envMatrix.length}`).format.columnWidth = 11;
envelope.getRangeByIndexes(0, 1, envMatrix.length, envMatrix[0].length - 1).format.columnWidth = 22;
envelope.freezePanes.freezeRows(1);

const repHeaders = ["相对峰值时间 ms"];
for (const id of seriesIds) repHeaders.push(`${id}_常见`, `${id}_较响`);
const repMatrix = [repHeaders];
for (let i = 0; i < payload.representative_time_ms.length; i++) {
  const row = [payload.representative_time_ms[i]];
  for (const id of seriesIds) {
    row.push(payload.representative_columns[`${id}_常见`][i], payload.representative_columns[`${id}_较响`][i]);
  }
  repMatrix.push(row);
}
reps.getRangeByIndexes(0, 0, repMatrix.length, repMatrix[0].length).values = repMatrix;
sectionHeader(reps.getRangeByIndexes(0, 0, 1, repMatrix[0].length));
reps.getRangeByIndexes(1, 0, repMatrix.length - 1, repMatrix[0].length).format.numberFormat = "0.0";
reps.getRange(`A1:A${repMatrix.length}`).format.columnWidth = 18;
reps.getRangeByIndexes(0, 1, repMatrix.length, repMatrix[0].length - 1).format.columnWidth = 24;
reps.freezePanes.freezeRows(1);
console.log("stage:raw-data");

// Dashboard controls and metric summary.
title(dashboard, "A1:N1", "固定基准口径：HPDI泵声音对比");
dashboard.getRange("A3").values = [["选择测试"]];
dashboard.getRange("A3").format = { font: { bold: true, color: C.ink }, fill: C.paleBlue };
dashboard.getRange("B3:G3").values = [[seriesIds.find((x) => x.includes("DD_BASE") && x.endsWith("_900")), seriesIds.find((x) => x.includes("FR_INIT") && x.endsWith("_900")), "", "", "", ""]];
dashboard.getRange("B3:G3").format = { fill: "#FFF7ED", font: { bold: true, color: C.orange }, borders: { preset: "all", style: "thin", color: C.line }, horizontalAlignment: "center" };
dashboard.getRange("B3:G3").dataValidation = { rule: { type: "list", formula1: `'测试索引'!$A$2:$A$${registryRows.length + 1}` } };
dashboard.getRange("A5:J5").values = [["测试编号", "转速 rpm", "常见咚声", "较响咚声", "常见/东德", "较响/东德", "常见/初始", "较响/初始", "超门槛占比", "声级判断"]];
sectionHeader(dashboard.getRange("A5:J5"));
for (let i = 0; i < 6; i++) {
  const row = 6 + i;
  const controlCol = excelCol(1 + i);
  dashboard.getRange(`A${row}`).formulas = [[`=IF(${controlCol}$3="","",${controlCol}$3)`]];
  const sourceCols = ["F", "J", "K", "L", "M", "P", "Q", "T", "U"];
  for (let j = 0; j < sourceCols.length; j++) {
    const outCol = excelCol(1 + j);
    dashboard.getRange(`${outCol}${row}`).formulas = [[`=IFERROR(INDEX('测试索引'!$${sourceCols[j]}$2:$${sourceCols[j]}$${registryRows.length + 1},MATCH($A${row},'测试索引'!$A$2:$A$${registryRows.length + 1},0)),"")`]];
  }
}
dashboard.getRange("A6:J11").format = { borders: { preset: "inside", style: "thin", color: C.line }, verticalAlignment: "center" };
dashboard.getRange("B6:B11").format.numberFormat = "0";
dashboard.getRange("C6:I11").format.numberFormat = "0.0";
dashboard.getRange("A1:A59").format.columnWidth = 25;
dashboard.getRange("B1:G59").format.columnWidth = 18;
dashboard.getRange("H1:H59").format.columnWidth = 20;
dashboard.getRange("I1:N59").format.columnWidth = 12;
dashboard.getRange("A12:N12").merge();
dashboard.getRange("A12").formulas = [[`=IF(COUNT(B6:B11)<=1,"请选择至少两组测试",IF(COUNTIF(B6:B11,B6)=COUNT(B6:B11),"转速一致：可直接比较产品声音","警告：所选测试转速不一致，只能观察趋势，不能直接判断产品优劣"))`]];
dashboard.getRange("A12").format = { fill: C.paleGold, font: { bold: true, color: C.ink }, horizontalAlignment: "center", verticalAlignment: "center" };
dashboard.freezePanes.freezeRows(3);
console.log("stage:dashboard");

// Formula-backed chart helper ranges.
const envRows = payload.envelope_time_s.length + 1;
calc.getRangeByIndexes(0, 0, envRows, 7).values = Array.from({ length: envRows }, (_, i) => [i === 0 ? "时间 s" : payload.envelope_time_s[i - 1], null, null, null, null, null, null]);
for (let slot = 0; slot < 6; slot++) {
  const col = excelCol(1 + slot);
  calc.getRange(`${col}1`).formulas = [[`='对比面板'!${col}$3`]];
  calc.getRange(`${col}2`).formulas = [[`=IF(${col}$1="","",IFERROR(INDEX('包络曲线数据'!$B$2:$${excelCol(seriesIds.length)}$${envRows},ROW()-1,MATCH(${col}$1,'包络曲线数据'!$B$1:$${excelCol(seriesIds.length)}$1,0)),""))`]];
  calc.getRange(`${col}2:${col}${envRows}`).fillDown();
}
console.log("stage:calc");

const repRows = payload.representative_time_ms.length + 1;
for (const [startCol, suffix] of [[8, "常见"], [16, "较响"]]) {
  calc.getRangeByIndexes(0, startCol, repRows, 7).values = Array.from({ length: repRows }, (_, i) => [i === 0 ? "相对时间 ms" : payload.representative_time_ms[i - 1], null, null, null, null, null, null]);
  for (let slot = 0; slot < 6; slot++) {
    const helperColIndex = startCol + 1 + slot;
    const helperCol = excelCol(helperColIndex);
    const dashboardCol = excelCol(1 + slot);
    calc.getRange(`${helperCol}1`).formulas = [[`='对比面板'!${dashboardCol}$3`]];
    calc.getRange(`${helperCol}2`).formulas = [[`=IF(${helperCol}$1="","",IFERROR(INDEX('代表咚声数据'!$B$2:$${excelCol(seriesIds.length * 2)}$${repRows},ROW()-1,MATCH(${helperCol}$1&"_${suffix}",'代表咚声数据'!$B$1:$${excelCol(seriesIds.length * 2)}$1,0)),""))`]];
    calc.getRange(`${helperCol}2:${helperCol}${repRows}`).fillDown();
  }
}

// Native charts remain editable in Excel and update with the dropdown choices.
const chartEnvelope = dashboard.charts.add("line", calc.getRange(`A1:G${envRows}`));
chartEnvelope.title = "整体咚声包络对比 - V2固定基准口径";
chartEnvelope.hasLegend = true;
chartEnvelope.xAxis = { axisType: "textAxis", title: { text: "视频时间 (s)" }, textStyle: { fontSize: 9 } };
chartEnvelope.yAxis = { title: { text: "泵咚声估算dB(A)" }, numberFormatCode: "0", min: 50, max: 110 };
chartEnvelope.setPosition("A14", "N34");

const chartCommon = dashboard.charts.add("line", calc.getRange(`I1:O${repRows}`));
chartCommon.title = "常见咚声 - 单次曲线";
chartCommon.hasLegend = true;
chartCommon.xAxis = { axisType: "textAxis", title: { text: "相对峰值时间 (ms)" }, textStyle: { fontSize: 9 } };
chartCommon.yAxis = { title: { text: "估算dB(A)" }, numberFormatCode: "0", min: 55, max: 110 };
chartCommon.setPosition("A36", "G55");

const chartLoud = dashboard.charts.add("line", calc.getRange(`Q1:W${repRows}`));
chartLoud.title = "较响咚声 - 单次曲线";
chartLoud.hasLegend = true;
chartLoud.xAxis = { axisType: "textAxis", title: { text: "相对峰值时间 (ms)" }, textStyle: { fontSize: 9 } };
chartLoud.yAxis = { title: { text: "估算dB(A)" }, numberFormatCode: "0", min: 55, max: 110 };
chartLoud.setPosition("H36", "N55");
console.log("stage:charts");

dashboard.getRange("A57:N59").merge();
dashboard.getRange("A57").values = [["基准锁定：东德和富瑞初始沿用V2原值，禁止重新归一化。后续无分贝仪视频按同一算法追加，但受手机自动增益影响，跨日期差值必须经同步分贝仪复测后才能作为对外结论。"]];
dashboard.getRange("A57").format = { fill: C.paleGold, wrapText: true, verticalAlignment: "center", font: { color: C.ink } };

// Lightweight formatting for helper sheet; keep it visible for audit and manual repair.
calc.getRange("A1:W1").format = { fill: "#F1F5F9", font: { bold: true, color: C.gray } };
calc.getRange(`A1:W${Math.max(envRows, repRows)}`).format.columnWidth = 15;
calc.freezePanes.freezeRows(1);

await wb.inspect({ kind: "table", range: "对比面板!A1:H11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 8 });

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(`${outputDir}/HPDI泵声音固定基准对比工具_内部复核_禁止外发.xlsx`);
console.log("stage:export");

// Artifact-tool's renderer currently crashes on this workbook's formula-driven charts.
// Visual QA is performed through read-only Microsoft Excel PDF export after generation.
for (const [sheetName, fileName, range] of [] /* [
  ["使用说明", "guide.png", "A1:H15"],
  ["对比面板", "dashboard.png", "A1:N59"],
  ["测试索引", "registry.png", `A1:Q${registryRows.length + 1}`],
  ["包络曲线数据", "envelope.png", "A1:F24"],
  ["代表咚声数据", "representatives.png", "A1:G20"],
  ["图表计算", "calc.png", "A1:W18"],
] */) {
  console.log(`stage:render-start:${sheetName}`);
  const image = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${previewDir}/${fileName}`, new Uint8Array(await image.arrayBuffer()));
  console.log(`stage:render-done:${sheetName}`);
}

const summary = await wb.inspect({ kind: "table", range: "对比面板!A1:H11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 8 });
console.log(summary.ndjson);
const drawings = await wb.inspect({ kind: "drawing", sheetId: "对比面板", maxChars: 4000 });
console.log(drawings.ndjson);
