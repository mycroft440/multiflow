Option Explicit

' Constantes globais
Public Const SENHA_PROTECAO As String = "ponto2025"
Public Const HORAS_NORMAIS As Integer = 24
Public Const PERCENTUAL_HE As Double = 0.5

' Variáveis globais para feriados
Public FeriadosNacionais As Collection

' Inicializa a coleção de feriados
Sub InicializarFeriados()
    Set FeriadosNacionais = New Collection
    
    ' Feriados fixos 2025
    FeriadosNacionais.Add Array(#1/1/2025#, "Ano Novo")
    FeriadosNacionais.Add Array(#3/4/2025#, "Carnaval")
    FeriadosNacionais.Add Array(#3/5/2025#, "Quarta de Cinzas")
    FeriadosNacionais.Add Array(#4/18/2025#, "Sexta-feira Santa")
    FeriadosNacionais.Add Array(#4/21/2025#, "Tiradentes")
    FeriadosNacionais.Add Array(#5/1/2025#, "Dia do Trabalho")
    FeriadosNacionais.Add Array(#6/19/2025#, "Corpus Christi")
    FeriadosNacionais.Add Array(#9/7/2025#, "Independência")
    FeriadosNacionais.Add Array(#10/12/2025#, "Nossa Senhora Aparecida")
    FeriadosNacionais.Add Array(#11/2/2025#, "Finados")
    FeriadosNacionais.Add Array(#11/15/2025#, "Proclamação da República")
    FeriadosNacionais.Add Array(#12/25/2025#, "Natal")
End Sub

' Função para criar nova planilha do mês
Sub CriarNovaPlanilhaMes()
    Dim ws As Worksheet
    Dim nomeMes As String
    Dim mes As Integer, ano As Integer
    Dim dataInicio As Date
    Dim diasNoMes As Integer
    Dim i As Integer
    
    ' Pega o mês e ano atual
    mes = Month(Date)
    ano = Year(Date)
    
    ' Cria nome da planilha (MMM-AAAA)
    nomeMes = Format(DateSerial(ano, mes, 1), "mmm-yyyy")
    
    ' Verifica se já existe
    On Error Resume Next
    Set ws = Worksheets(nomeMes)
    On Error GoTo 0
    
    If Not ws Is Nothing Then
        MsgBox "A planilha para " & nomeMes & " já existe!", vbExclamation
        Exit Sub
    End If
    
    ' Cria nova planilha
    Set ws = Worksheets.Add(After:=Worksheets(Worksheets.Count))
    ws.Name = nomeMes
    
    ' Chama rotina para configurar a planilha
    ConfigurarPlanilhaMes ws, mes, ano
    
    MsgBox "Planilha " & nomeMes & " criada com sucesso!", vbInformation
End Sub

' Função para gerar próximo mês
Sub GerarProximoMes()
    Dim ws As Worksheet
    Dim ultimaPlanilha As String
    Dim mes As Integer, ano As Integer
    Dim dataRef As Date
    
    ' Pega a última planilha
    Set ws = Worksheets(Worksheets.Count)
    ultimaPlanilha = ws.Name
    
    ' Tenta extrair mês e ano do nome
    On Error Resume Next
    dataRef = DateValue("01-" & ultimaPlanilha)
    On Error GoTo 0
    
    If dataRef = 0 Then
        ' Se não conseguir, usa o mês atual
        mes = Month(Date)
        ano = Year(Date)
    Else
        ' Adiciona um mês
        dataRef = DateAdd("m", 1, dataRef)
        mes = Month(dataRef)
        ano = Year(dataRef)
    End If
    
    ' Cria nome da nova planilha
    Dim nomeMes As String
    nomeMes = Format(DateSerial(ano, mes, 1), "mmm-yyyy")
    
    ' Verifica se já existe
    On Error Resume Next
    Set ws = Nothing
    Set ws = Worksheets(nomeMes)
    On Error GoTo 0
    
    If Not ws Is Nothing Then
        MsgBox "A planilha para " & nomeMes & " já existe!", vbExclamation
        Exit Sub
    End If
    
    ' Cria nova planilha
    Set ws = Worksheets.Add(After:=Worksheets(Worksheets.Count))
    ws.Name = nomeMes
    
    ' Configura a planilha
    ConfigurarPlanilhaMes ws, mes, ano
    
    MsgBox "Planilha " & nomeMes & " criada com sucesso!", vbInformation
End Sub

' Configura a planilha do mês
Sub ConfigurarPlanilhaMes(ws As Worksheet, mes As Integer, ano As Integer)
    Dim dataInicio As Date
    Dim diasNoMes As Integer
    Dim i As Integer
    Dim linha As Integer
    
    Application.ScreenUpdating = False
    
    ' Inicializa feriados
    InicializarFeriados
    
    ' Desprotege temporariamente
    ws.Unprotect Password:=SENHA_PROTECAO
    
    ' Define data inicial e dias no mês
    dataInicio = DateSerial(ano, mes, 1)
    diasNoMes = Day(DateSerial(ano, mes + 1, 0))
    
    ' Configura cabeçalho
    With ws
        ' Título
        .Range("A1:H1").Merge
        .Range("A1").Value = "CONTROLE DE PONTO - " & UCase(Format(dataInicio, "mmmm/yyyy"))
        .Range("A1").Font.Size = 18
        .Range("A1").Font.Bold = True
        .Range("A1").HorizontalAlignment = xlCenter
        .Range("A1").Interior.Color = RGB(45, 62, 80)
        .Range("A1").Font.Color = RGB(255, 255, 255)
        
        ' Cabeçalhos das colunas
        .Range("A3").Value = "Dia"
        .Range("B3").Value = "Data"
        .Range("C3").Value = "Entrada"
        .Range("D3").Value = "Saída"
        .Range("E3").Value = "Total Horas"
        .Range("F3").Value = "Hora Extra"
        .Range("G3").Value = "HE c/50%"
        .Range("H3").Value = "Total Final"
        
        ' Formata cabeçalhos
        With .Range("A3:H3")
            .Font.Bold = True
            .Font.Size = 12
            .Interior.Color = RGB(52, 73, 94)
            .Font.Color = RGB(255, 255, 255)
            .HorizontalAlignment = xlCenter
            .Borders.LineStyle = xlContinuous
            .Borders.Weight = xlMedium
        End With
        
        ' Preenche os dias
        linha = 4
        For i = 1 To diasNoMes
            Dim dataAtual As Date
            dataAtual = DateSerial(ano, mes, i)
            
            .Cells(linha, 1).Value = Format(dataAtual, "ddd")
            .Cells(linha, 2).Value = dataAtual
            .Cells(linha, 2).NumberFormat = "dd/mm/yyyy"
            
            ' Formata fins de semana e feriados
            If Weekday(dataAtual) = 1 Then ' Domingo
                .Range("A" & linha & ":H" & linha).Interior.Color = RGB(255, 230, 230)
            ElseIf Weekday(dataAtual) = 7 Then ' Sábado
                .Range("A" & linha & ":H" & linha).Interior.Color = RGB(230, 240, 255)
            End If
            
            ' Verifica feriados
            Dim feriado As Variant
            For Each feriado In FeriadosNacionais
                If dataAtual = feriado(0) Then
                    .Range("A" & linha & ":H" & linha).Interior.Color = RGB(240, 240, 240)
                    .Cells(linha, 2).AddComment "Feriado: " & feriado(1)
                    Exit For
                End If
            Next
            
            linha = linha + 1
        Next i
        
        ' Adiciona fórmulas
        For i = 4 To linha - 1
            ' Total de Horas (E)
            .Cells(i, 5).Formula = "=IF(AND(C" & i & "<>"""",D" & i & "<>""""),IF(D" & i & "<C" & i & ",D" & i & "+1-C" & i & ",D" & i & "-C" & i & "),"""")"
            
            ' Hora Extra (F)
            .Cells(i, 6).Formula = "=IF(E" & i & "<>"""",MAX(0,E" & i & "-TIME(24,0,0)),"""")"
            
            ' HE c/50% (G)
            .Cells(i, 7).Formula = "=IF(F" & i & "<>"""",F" & i & "*1.5,"""")"
            
            ' Total Final (H)
            .Cells(i, 8).Formula = "=IF(E" & i & "<>"""",MIN(E" & i & ",TIME(24,0,0))+G" & i & ","""")"
        Next i
        
        ' Formata colunas de tempo
        .Range("C4:H" & (linha - 1)).NumberFormat = "[hh]:mm"
        
        ' Formata células de entrada/saída
        .Range("C4:D" & (linha - 1)).Interior.Color = RGB(248, 249, 250)
        .Range("C4:D" & (linha - 1)).Borders.LineStyle = xlContinuous
        
        ' Adiciona linha de totais
        linha = linha + 1
        .Range("A" & linha & ":B" & linha).Merge
        .Cells(linha, 1).Value = "TOTAIS DO MÊS"
        .Cells(linha, 1).Font.Bold = True
        .Cells(linha, 1).HorizontalAlignment = xlRight
        
        ' Fórmulas de totais
        .Cells(linha, 5).Formula = "=SUM(E4:E" & (linha - 2) & ")"
        .Cells(linha, 6).Formula = "=SUM(F4:F" & (linha - 2) & ")"
        .Cells(linha, 7).Formula = "=SUM(G4:G" & (linha - 2) & ")"
        .Cells(linha, 8).Formula = "=SUM(H4:H" & (linha - 2) & ")"
        
        ' Formata linha de totais
        With .Range("A" & linha & ":H" & linha)
            .Interior.Color = RGB(52, 73, 94)
            .Font.Color = RGB(255, 255, 255)
            .Font.Bold = True
            .Borders.LineStyle = xlContinuous
            .Borders.Weight = xlMedium
        End With
        
        ' Adiciona botões
        Dim btn As Object
        
        ' Botão Gerar Relatório Mensal
        Set btn = .Buttons.Add(Left:=.Range("J4").Left, Top:=.Range("J4").Top, Width:=150, Height:=30)
        btn.Caption = "Gerar Relatório Mensal"
        btn.OnAction = "GerarRelatorioMensal"
        
        ' Botão Gerar Próximo Mês
        Set btn = .Buttons.Add(Left:=.Range("J7").Left, Top:=.Range("J7").Top, Width:=150, Height:=30)
        btn.Caption = "Gerar Próximo Mês"
        btn.OnAction = "GerarProximoMes"
        
        ' Ajusta largura das colunas
        .Columns("A").ColumnWidth = 8
        .Columns("B").ColumnWidth = 12
        .Columns("C:H").ColumnWidth = 15
        
        ' Adiciona validação de dados para horários
        With .Range("C4:D" & (linha - 2)).Validation
            .Delete
            .Add Type:=xlValidateTime, AlertStyle:=xlValidAlertStop, _
                 Operator:=xlBetween, Formula1:="0:00", Formula2:="23:59"
            .ErrorTitle = "Horário Inválido"
            .ErrorMessage = "Digite um horário válido no formato HH:MM"
        End With
        
        ' Protege a planilha
        .Protect Password:=SENHA_PROTECAO, DrawingObjects:=True, Contents:=True, _
                 Scenarios:=True, AllowFormattingCells:=False
        
        ' Permite edição apenas nas células de entrada/saída
        .Range("C4:D" & (linha - 2)).Locked = False
    End With
    
    Application.ScreenUpdating = True
End Sub

' Gera relatório mensal
Sub GerarRelatorioMensal()
    Dim ws As Worksheet
    Dim ultimaLinha As Integer
    Dim totalHoras As String
    Dim totalHE As String
    Dim totalFinal As String
    
    Set ws = ActiveSheet
    
    ' Encontra a linha de totais
    ultimaLinha = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    
    ' Pega os valores
    totalHoras = Format(ws.Cells(ultimaLinha, 5).Value, "[hh]:mm")
    totalHE = Format(ws.Cells(ultimaLinha, 7).Value, "[hh]:mm")
    totalFinal = Format(ws.Cells(ultimaLinha, 8).Value, "[hh]:mm")
    
    ' Monta o relatório
    Dim relatorio As String
    relatorio = "RELATÓRIO MENSAL - " & ws.Name & vbCrLf & vbCrLf
    relatorio = relatorio & "Total de Horas Normais: " & totalHoras & vbCrLf
    relatorio = relatorio & "Total de Horas Extras (c/ 50%): " & totalHE & vbCrLf
    relatorio = relatorio & "Total Final Trabalhado: " & totalFinal & vbCrLf & vbCrLf
    relatorio = relatorio & "Gerado em: " & Format(Now, "dd/mm/yyyy hh:mm")
    
    MsgBox relatorio, vbInformation, "Relatório Mensal"
End Sub

' Validação ao alterar células
Private Sub Worksheet_Change(ByVal Target As Range)
    Dim linha As Integer
    Dim entrada As Variant
    Dim saida As Variant
    
    ' Verifica se a alteração foi nas colunas C ou D
    If Target.Column = 3 Or Target.Column = 4 Then
        linha = Target.Row
        
        ' Pega valores de entrada e saída
        entrada = Cells(linha, 3).Value
        saida = Cells(linha, 4).Value
        
        ' Validação: entrada não pode ser maior que saída no mesmo dia
        If entrada <> "" And saida <> "" Then
            If entrada > saida And Target.Column = 4 Then
                ' Permite saída menor que entrada (plantão atravessa o dia)
                Exit Sub
            ElseIf entrada > saida And Target.Column = 3 Then
                MsgBox "A entrada não pode ser maior que a saída no mesmo dia!", vbExclamation
                Application.EnableEvents = False
                Target.Value = ""
                Application.EnableEvents = True
            End If
        End If
    End If
End Sub