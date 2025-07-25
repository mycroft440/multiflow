# Script PowerShell para criar planilha de controle de ponto
# Requer Microsoft Excel instalado

Write-Host "Criando planilha de controle de ponto..." -ForegroundColor Green

# Cria objeto Excel
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $true
$excel.DisplayAlerts = $false

# Cria novo workbook
$workbook = $excel.Workbooks.Add()

# Define variáveis do mês atual
$mes = (Get-Date).Month
$ano = (Get-Date).Year
$nomeMes = (Get-Date).ToString("MMM-yyyy")
$diasNoMes = [DateTime]::DaysInMonth($ano, $mes)

# Renomeia primeira planilha
$sheet = $workbook.Sheets.Item(1)
$sheet.Name = $nomeMes

# Configura título
$sheet.Range("A1:H1").Merge()
$sheet.Range("A1").Value = "CONTROLE DE PONTO - " + (Get-Date).ToString("MMMM/yyyy").ToUpper()
$sheet.Range("A1").Font.Size = 18
$sheet.Range("A1").Font.Bold = $true
$sheet.Range("A1").HorizontalAlignment = -4108 # xlCenter
$sheet.Range("A1").Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(45, 62, 80))
$sheet.Range("A1").Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
$sheet.Rows.Item(1).RowHeight = 30

# Adiciona cabeçalhos
$headers = @("Dia", "Data", "Entrada", "Saída", "Total Horas", "Hora Extra", "HE c/50%", "Total Final")
for ($i = 0; $i -lt $headers.Count; $i++) {
    $sheet.Cells.Item(3, $i + 1) = $headers[$i]
}

# Formata cabeçalhos
$headerRange = $sheet.Range("A3:H3")
$headerRange.Font.Bold = $true
$headerRange.Font.Size = 12
$headerRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(52, 73, 94))
$headerRange.Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
$headerRange.HorizontalAlignment = -4108
$headerRange.Borders.LineStyle = 1
$headerRange.Borders.Weight = 3

# Preenche os dias
$linha = 4
for ($dia = 1; $dia -le $diasNoMes; $dia++) {
    $data = Get-Date -Year $ano -Month $mes -Day $dia
    
    # Dia da semana
    $sheet.Cells.Item($linha, 1) = $data.ToString("ddd")
    
    # Data
    $sheet.Cells.Item($linha, 2) = $data
    $sheet.Cells.Item($linha, 2).NumberFormat = "dd/mm/yyyy"
    
    # Formata fins de semana
    if ($data.DayOfWeek -eq "Sunday") {
        $sheet.Range("A$linha`:H$linha").Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(255, 230, 230))
    }
    elseif ($data.DayOfWeek -eq "Saturday") {
        $sheet.Range("A$linha`:H$linha").Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(230, 240, 255))
    }
    
    # Adiciona fórmulas
    # Total de Horas
    $sheet.Cells.Item($linha, 5).Formula = "=IF(AND(C$linha<>"""",D$linha<>""""),IF(D$linha<C$linha,D$linha+1-C$linha,D$linha-C$linha),"""")"
    
    # Hora Extra
    $sheet.Cells.Item($linha, 6).Formula = "=IF(E$linha<>"""",MAX(0,E$linha-TIME(24,0,0)),"""")"
    
    # HE c/50%
    $sheet.Cells.Item($linha, 7).Formula = "=IF(F$linha<>"""",F$linha*1.5,"""")"
    
    # Total Final
    $sheet.Cells.Item($linha, 8).Formula = "=IF(E$linha<>"""",MIN(E$linha,TIME(24,0,0))+G$linha,"""")"
    
    $linha++
}

# Formata colunas de tempo
$sheet.Range("C4:H$($linha-1)").NumberFormat = "[hh]:mm"

# Formata células de entrada/saída
$entradaSaidaRange = $sheet.Range("C4:D$($linha-1)")
$entradaSaidaRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(248, 249, 250))
$entradaSaidaRange.Borders.LineStyle = 1

# Adiciona linha de totais
$linha++
$sheet.Range("A$linha`:B$linha").Merge()
$sheet.Cells.Item($linha, 1) = "TOTAIS DO MÊS"
$sheet.Cells.Item($linha, 1).Font.Bold = $true
$sheet.Cells.Item($linha, 1).HorizontalAlignment = -4152 # xlRight

# Fórmulas de totais
$sheet.Cells.Item($linha, 5).Formula = "=SUM(E4:E$($linha-2))"
$sheet.Cells.Item($linha, 6).Formula = "=SUM(F4:F$($linha-2))"
$sheet.Cells.Item($linha, 7).Formula = "=SUM(G4:G$($linha-2))"
$sheet.Cells.Item($linha, 8).Formula = "=SUM(H4:H$($linha-2))"

# Formata linha de totais
$totalRange = $sheet.Range("A$linha`:H$linha")
$totalRange.Interior.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::FromArgb(52, 73, 94))
$totalRange.Font.Color = [System.Drawing.ColorTranslator]::ToOle([System.Drawing.Color]::White)
$totalRange.Font.Bold = $true
$totalRange.Borders.LineStyle = 1
$totalRange.Borders.Weight = 3

# Ajusta largura das colunas
$sheet.Columns.Item("A").ColumnWidth = 8
$sheet.Columns.Item("B").ColumnWidth = 12
$sheet.Columns.Item("C:H").ColumnWidth = 15

# Adiciona validação de horários
$validationRange = $sheet.Range("C4:D$($linha-2)")
$validationRange.Validation.Delete()
$validationRange.Validation.Add(
    6, # xlValidateTime
    1, # xlValidAlertStop
    1, # xlBetween
    "0:00",
    "23:59"
)
$validationRange.Validation.ErrorTitle = "Horário Inválido"
$validationRange.Validation.ErrorMessage = "Digite um horário válido no formato HH:MM"

# Adiciona botões
$btn1 = $sheet.Buttons().Add(
    $sheet.Range("J4").Left,
    $sheet.Range("J4").Top,
    150,
    30
)
$btn1.Caption = "Gerar Relatório Mensal"
$btn1.OnAction = "GerarRelatorioMensal"

$btn2 = $sheet.Buttons().Add(
    $sheet.Range("J7").Left,
    $sheet.Range("J7").Top,
    150,
    30
)
$btn2.Caption = "Gerar Próximo Mês"
$btn2.OnAction = "GerarProximoMes"

# Adiciona instruções
$sheet.Range("A37:H38").Merge()
$sheet.Range("A37").Value = @"
INSTRUÇÕES:
1. Digite os horários de entrada e saída no formato HH:MM
2. Para plantões que atravessam o dia, a saída pode ser menor que a entrada
3. Horas extras são calculadas automaticamente acima de 24h
4. Use os botões à direita para gerar relatórios e criar novos meses
5. Senha de proteção: ponto2025
"@
$sheet.Range("A37").WrapText = $true
$sheet.Range("A37").VerticalAlignment = -4160 # xlTop

# Protege a planilha
$sheet.Protect("ponto2025", $true, $true, $true)

# Desbloqueia apenas células de entrada/saída
$sheet.Range("C4:D$($linha-2)").Locked = $false

Write-Host "Adicionando código VBA..." -ForegroundColor Yellow

# Adiciona módulo VBA
try {
    $vbModule = $workbook.VBProject.VBComponents.Add(1)
    
    # Código VBA
    $vbaCode = @'
Option Explicit

Public Const SENHA_PROTECAO As String = "ponto2025"

Sub GerarProximoMes()
    Dim ws As Worksheet
    Dim nomeMes As String
    Dim mes As Integer, ano As Integer
    
    mes = Month(Date)
    ano = Year(Date)
    
    If mes = 12 Then
        mes = 1
        ano = ano + 1
    Else
        mes = mes + 1
    End If
    
    nomeMes = Format(DateSerial(ano, mes, 1), "mmm-yyyy")
    
    On Error Resume Next
    Set ws = Worksheets(nomeMes)
    On Error GoTo 0
    
    If Not ws Is Nothing Then
        MsgBox "A planilha para " & nomeMes & " já existe!", vbExclamation
        Exit Sub
    End If
    
    Set ws = Worksheets.Add(After:=Worksheets(Worksheets.Count))
    ws.Name = nomeMes
    
    MsgBox "Planilha " & nomeMes & " criada! Configure manualmente.", vbInformation
End Sub

Sub GerarRelatorioMensal()
    Dim ws As Worksheet
    Dim ultimaLinha As Integer
    Dim totalHoras As String
    Dim totalHE As String
    Dim totalFinal As String
    
    Set ws = ActiveSheet
    ultimaLinha = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    
    totalHoras = Format(ws.Cells(ultimaLinha, 5).Value, "[hh]:mm")
    totalHE = Format(ws.Cells(ultimaLinha, 7).Value, "[hh]:mm")
    totalFinal = Format(ws.Cells(ultimaLinha, 8).Value, "[hh]:mm")
    
    Dim relatorio As String
    relatorio = "RELATÓRIO MENSAL - " & ws.Name & vbCrLf & vbCrLf
    relatorio = relatorio & "Total de Horas Normais: " & totalHoras & vbCrLf
    relatorio = relatorio & "Total de Horas Extras (c/ 50%): " & totalHE & vbCrLf
    relatorio = relatorio & "Total Final Trabalhado: " & totalFinal & vbCrLf & vbCrLf
    relatorio = relatorio & "Gerado em: " & Format(Now, "dd/mm/yyyy hh:mm")
    
    MsgBox relatorio, vbInformation, "Relatório Mensal"
End Sub
'@
    
    $vbModule.CodeModule.AddFromString($vbaCode)
    Write-Host "Código VBA adicionado com sucesso!" -ForegroundColor Green
}
catch {
    Write-Host "Aviso: Não foi possível adicionar o código VBA automaticamente." -ForegroundColor Yellow
    Write-Host "Você precisará adicionar manualmente através do Editor VBA (Alt+F11)" -ForegroundColor Yellow
}

# Salva o arquivo
$filename = Join-Path $PWD "ControlePonto.xlsm"
$workbook.SaveAs($filename, 52) # xlOpenXMLWorkbookMacroEnabled

Write-Host "`nPlanilha criada com sucesso!" -ForegroundColor Green
Write-Host "Arquivo: $filename" -ForegroundColor Cyan
Write-Host "`nSenha de proteção: ponto2025" -ForegroundColor Yellow

# Fecha Excel se necessário
# $excel.Quit()

# Libera objetos COM
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($sheet) | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()