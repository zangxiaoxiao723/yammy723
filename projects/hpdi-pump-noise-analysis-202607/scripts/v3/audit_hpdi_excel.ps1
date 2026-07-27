$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$xlsx = (Get-ChildItem (Join-Path $root 'outputs\hpdi_followup_v3') -Filter '*.xlsx' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$payloadPath = (Resolve-Path (Join-Path $root 'outputs\hpdi_baseline_v2\workbook_payload.json')).Path
$outputPath = Join-Path $root 'outputs\hpdi_followup_v3\release_audit\excel_com_audit.json'
$payload = Get-Content -Raw -Encoding UTF8 $payloadPath | ConvertFrom-Json

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    $wb = $excel.Workbooks.Open($xlsx, 0, $true)
    $excel.CalculateFull()
    $formulaErrors = @()
    foreach ($ws in $wb.Worksheets) {
        try {
            $bad = $ws.UsedRange.SpecialCells(16, 16)
            if ($bad) { $formulaErrors += "$($ws.Name):$($bad.Address())" }
        } catch {}
    }

    $baselineSheet = $wb.Worksheets.Item(2)
    $mismatches = @()
    for ($i = 0; $i -lt $payload.registry.Count; $i++) {
        $excelRow = 6 + $i
        $expected = $payload.registry[$i]
        $actualId = [string]$baselineSheet.Cells.Item($excelRow, 1).Value2
        $actualCommon = [double]$baselineSheet.Cells.Item($excelRow, 5).Value2
        $actualLoud = [double]$baselineSheet.Cells.Item($excelRow, 6).Value2
        $actualCommonText = [string]$baselineSheet.Cells.Item($excelRow, 7).Text
        $actualLoudText = [string]$baselineSheet.Cells.Item($excelRow, 8).Text
        if ($actualId -ne $expected.series_id) { $mismatches += "row=$excelRow id" }
        if ([math]::Abs($actualCommon - [double]$expected.common_thump_est_dba) -gt 1e-10) { $mismatches += "row=$excelRow common" }
        if ([math]::Abs($actualLoud - [double]$expected.loud_thump_est_dba) -gt 1e-10) { $mismatches += "row=$excelRow loud" }
        if ($actualCommonText -ne [string]$expected.common_comparison) { $mismatches += "row=$excelRow common_text" }
        if ($actualLoudText -ne [string]$expected.loud_comparison) { $mismatches += "row=$excelRow loud_text" }
    }

    $dash = $wb.Worksheets.Item(3)
    $result = [ordered]@{
        status = if ($formulaErrors.Count -eq 0 -and $mismatches.Count -eq 0 -and $dash.ChartObjects().Count -eq 3) { 'PASS' } else { 'FAIL' }
        workbook = $xlsx
        sheets = $wb.Worksheets.Count
        charts = $dash.ChartObjects().Count
        formula_errors = $formulaErrors
        baseline_row_mismatches = $mismatches
        validation_range = $dash.Range('B3').Validation.Formula1
        default_series_1 = $dash.Range('B3').Text
        default_series_2 = $dash.Range('C3').Text
        default_common_comparison = $dash.Range('E7').Text
        default_loud_comparison = $dash.Range('F7').Text
    }
    $result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $outputPath
    $result | Format-List
    $wb.Close($false)
    if ($result.status -ne 'PASS') { exit 1 }
} finally {
    $excel.Quit()
}
