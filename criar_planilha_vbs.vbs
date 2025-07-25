' Script VBScript para criar planilha de controle de ponto
Option Explicit

Dim objExcel, objWorkbook, objSheet
Dim mes, ano, nomeMes, diasNoMes
Dim i, linha

' Cria aplicação Excel
Set objExcel = CreateObject("Excel.Application")
objExcel.Visible = True
objExcel.DisplayAlerts = False

' Cria novo workbook
Set objWorkbook = objExcel.Workbooks.Add()

' Define mês e ano atual
mes = Month(Date)
ano = Year(Date)
nomeMes = MonthName(mes, True) & "-" & ano

' Renomeia a primeira planilha
Set objSheet = objWorkbook.Sheets(1)
objSheet.Name = nomeMes

' Calcula dias no mês
diasNoMes = Day(DateSerial(ano, mes + 1, 0))

' Configura título
objSheet.Range("A1:H1").Merge
objSheet.Range("A1").Value = "CONTROLE DE PONTO - " & UCase(MonthName(mes)) & "/" & ano
objSheet.Range("A1").Font.Size = 18
objSheet.Range("A1").Font.Bold = True
objSheet.Range("A1").HorizontalAlignment = -4108 ' xlCenter
objSheet.Range("A1").Interior.Color = RGB(45, 62, 80)
objSheet.Range("A1").Font.Color = RGB(255, 255, 255)
objSheet.Rows(1).RowHeight = 30

' Adiciona cabeçalhos
objSheet.Range("A3").Value = "Dia"
objSheet.Range("B3").Value = "Data"
objSheet.Range("C3").Value = "Entrada"
objSheet.Range("D3").Value = "Saída"
objSheet.Range("E3").Value = "Total Horas"
objSheet.Range("F3").Value = "Hora Extra"
objSheet.Range("G3").Value = "HE c/50%"
objSheet.Range("H3").Value = "Total Final"

' Formata cabeçalhos
With objSheet.Range("A3:H3")
    .Font.Bold = True
    .Font.Size = 12
    .Interior.Color = RGB(52, 73, 94)
    .Font.Color = RGB(255, 255, 255)
    .HorizontalAlignment = -4108 ' xlCenter
    .Borders.LineStyle = 1 ' xlContinuous
    .Borders.Weight = 3 ' xlMedium
End With

' Preenche os dias
linha = 4
For i = 1 To diasNoMes
    Dim dataAtual
    dataAtual = DateSerial(ano, mes, i)
    
    objSheet.Cells(linha, 1).Value = WeekdayName(Weekday(dataAtual), True)
    objSheet.Cells(linha, 2).Value = dataAtual
    objSheet.Cells(linha, 2).NumberFormat = "dd/mm/yyyy"
    
    ' Formata fins de semana
    If Weekday(dataAtual) = 1 Then ' Domingo
        objSheet.Range("A" & linha & ":H" & linha).Interior.Color = RGB(255, 230, 230)
    ElseIf Weekday(dataAtual) = 7 Then ' Sábado
        objSheet.Range("A" & linha & ":H" & linha).Interior.Color = RGB(230, 240, 255)
    End If
    
    ' Adiciona fórmulas
    ' Total de Horas
    objSheet.Cells(linha, 5).Formula = "=IF(AND(C" & linha & "<>"""",D" & linha & "<>""""),IF(D" & linha & "<C" & linha & ",D" & linha & "+1-C" & linha & ",D" & linha & "-C" & linha & "),"""")"
    
    ' Hora Extra
    objSheet.Cells(linha, 6).Formula = "=IF(E" & linha & "<>"""",MAX(0,E" & linha & "-TIME(24,0,0)),"""")"
    
    ' HE c/50%
    objSheet.Cells(linha, 7).Formula = "=IF(F" & linha & "<>"""",F" & linha & "*1.5,"""")"
    
    ' Total Final
    objSheet.Cells(linha, 8).Formula = "=IF(E" & linha & "<>"""",MIN(E" & linha & ",TIME(24,0,0))+G" & linha & ","""")"
    
    linha = linha + 1
Next

' Formata colunas de tempo
objSheet.Range("C4:H" & (linha - 1)).NumberFormat = "[hh]:mm"

' Formata células de entrada/saída
With objSheet.Range("C4:D" & (linha - 1))
    .Interior.Color = RGB(248, 249, 250)
    .Borders.LineStyle = 1
End With

' Adiciona linha de totais
linha = linha + 1
objSheet.Range("A" & linha & ":B" & linha).Merge
objSheet.Cells(linha, 1).Value = "TOTAIS DO MÊS"
objSheet.Cells(linha, 1).Font.Bold = True
objSheet.Cells(linha, 1).HorizontalAlignment = -4152 ' xlRight

' Fórmulas de totais
objSheet.Cells(linha, 5).Formula = "=SUM(E4:E" & (linha - 2) & ")"
objSheet.Cells(linha, 6).Formula = "=SUM(F4:F" & (linha - 2) & ")"
objSheet.Cells(linha, 7).Formula = "=SUM(G4:G" & (linha - 2) & ")"
objSheet.Cells(linha, 8).Formula = "=SUM(H4:H" & (linha - 2) & ")"

' Formata linha de totais
With objSheet.Range("A" & linha & ":H" & linha)
    .Interior.Color = RGB(52, 73, 94)
    .Font.Color = RGB(255, 255, 255)
    .Font.Bold = True
    .Borders.LineStyle = 1
    .Borders.Weight = 3
End With

' Ajusta largura das colunas
objSheet.Columns("A").ColumnWidth = 8
objSheet.Columns("B").ColumnWidth = 12
objSheet.Columns("C:H").ColumnWidth = 15

' Adiciona validação de horários
With objSheet.Range("C4:D" & (linha - 2)).Validation
    .Delete
    .Add Type:=6, AlertStyle:=1, Operator:=1, Formula1:="0:00", Formula2:="23:59"
    .ErrorTitle = "Horário Inválido"
    .ErrorMessage = "Digite um horário válido no formato HH:MM"
End With

' Adiciona módulo VBA
Dim objModule
Set objModule = objWorkbook.VBProject.VBComponents.Add(1) ' vbext_ct_StdModule

' Adiciona o código VBA
Dim vbaCode
vbaCode = ReadVBACode()
objModule.CodeModule.AddFromString vbaCode

' Salva o arquivo
objWorkbook.SaveAs "ControlePonto.xlsm", 52 ' xlOpenXMLWorkbookMacroEnabled

MsgBox "Planilha de controle de ponto criada com sucesso!" & vbCrLf & _
       "Arquivo: ControlePonto.xlsm" & vbCrLf & vbCrLf & _
       "Senha de proteção: ponto2025", vbInformation, "Sucesso"

' Limpa objetos
Set objSheet = Nothing
Set objWorkbook = Nothing
Set objExcel = Nothing

Function ReadVBACode()
    ' Retorna o código VBA como string
    ReadVBACode = "Option Explicit" & vbCrLf & _
    "Public Const SENHA_PROTECAO As String = ""ponto2025""" & vbCrLf & _
    "Public Const HORAS_NORMAIS As Integer = 24" & vbCrLf & _
    "Public Const PERCENTUAL_HE As Double = 0.5" & vbCrLf & vbCrLf & _
    "Sub GerarProximoMes()" & vbCrLf & _
    "    Dim ws As Worksheet" & vbCrLf & _
    "    Dim nomeMes As String" & vbCrLf & _
    "    Dim mes As Integer, ano As Integer" & vbCrLf & _
    "    mes = Month(Date)" & vbCrLf & _
    "    ano = Year(Date)" & vbCrLf & _
    "    If mes = 12 Then" & vbCrLf & _
    "        mes = 1" & vbCrLf & _
    "        ano = ano + 1" & vbCrLf & _
    "    Else" & vbCrLf & _
    "        mes = mes + 1" & vbCrLf & _
    "    End If" & vbCrLf & _
    "    nomeMes = Format(DateSerial(ano, mes, 1), ""mmm-yyyy"")" & vbCrLf & _
    "    On Error Resume Next" & vbCrLf & _
    "    Set ws = Worksheets(nomeMes)" & vbCrLf & _
    "    On Error GoTo 0" & vbCrLf & _
    "    If Not ws Is Nothing Then" & vbCrLf & _
    "        MsgBox ""A planilha para "" & nomeMes & "" já existe!"", vbExclamation" & vbCrLf & _
    "        Exit Sub" & vbCrLf & _
    "    End If" & vbCrLf & _
    "    Set ws = Worksheets.Add(After:=Worksheets(Worksheets.Count))" & vbCrLf & _
    "    ws.Name = nomeMes" & vbCrLf & _
    "    MsgBox ""Planilha "" & nomeMes & "" criada! Configure manualmente."", vbInformation" & vbCrLf & _
    "End Sub" & vbCrLf & vbCrLf & _
    "Sub GerarRelatorioMensal()" & vbCrLf & _
    "    Dim ws As Worksheet" & vbCrLf & _
    "    Dim ultimaLinha As Integer" & vbCrLf & _
    "    Set ws = ActiveSheet" & vbCrLf & _
    "    ultimaLinha = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row" & vbCrLf & _
    "    Dim relatorio As String" & vbCrLf & _
    "    relatorio = ""RELATÓRIO MENSAL - "" & ws.Name & vbCrLf & vbCrLf" & vbCrLf & _
    "    relatorio = relatorio & ""Total de Horas Normais: "" & Format(ws.Cells(ultimaLinha, 5).Value, ""[hh]:mm"") & vbCrLf" & vbCrLf & _
    "    relatorio = relatorio & ""Total de Horas Extras (c/ 50%): "" & Format(ws.Cells(ultimaLinha, 7).Value, ""[hh]:mm"") & vbCrLf" & vbCrLf & _
    "    relatorio = relatorio & ""Total Final Trabalhado: "" & Format(ws.Cells(ultimaLinha, 8).Value, ""[hh]:mm"")" & vbCrLf & _
    "    MsgBox relatorio, vbInformation, ""Relatório Mensal""" & vbCrLf & _
    "End Sub"
End Function