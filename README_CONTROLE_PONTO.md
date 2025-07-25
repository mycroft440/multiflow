# Planilha de Controle de Ponto com VBA

## 📋 Descrição

Sistema completo de controle de ponto desenvolvido em Excel com VBA, específico para jornadas de plantão 24h x 72h. Inclui cálculo automático de horas extras, relatórios mensais e interface moderna.

## 🚀 Funcionalidades

### 1. Registro de Ponto
- Entrada e saída com data e hora
- Suporte para plantões que atravessam dias
- Validação automática de horários

### 2. Cálculos Automáticos
- Total de horas trabalhadas
- Identificação de horas extras (acima de 24h)
- Aplicação de 50% sobre horas extras
- Total final com horas normais + HE c/50%

### 3. Visual Moderno
- Interface profissional com cores sóbrias
- Destaque automático para:
  - **Sábados**: Azul claro
  - **Domingos**: Vermelho claro
  - **Feriados**: Cinza claro com tooltip

### 4. Automação
- Botão "Gerar Próximo Mês" - cria nova aba automaticamente
- Botão "Gerar Relatório Mensal" - totaliza o mês
- Proteção por senha das fórmulas

### 5. Adaptabilidade
- Ajuste automático para meses de 30 ou 31 dias
- Formato [hh]:mm para todos os campos de duração

## 📁 Arquivos Incluídos

1. **ControlePonto.bas** - Código VBA principal com todas as funcionalidades
2. **criar_planilha_vbs.vbs** - Script para criar a planilha automaticamente (Windows)
3. **criar_controle_ponto.py** - Script Python alternativo
4. **README_CONTROLE_PONTO.md** - Este arquivo

## 🛠️ Como Usar

### Opção 1: Usando o Script VBS (Recomendado para Windows)

1. Execute o arquivo `criar_planilha_vbs.vbs` (duplo clique)
2. O Excel será aberto automaticamente
3. A planilha será criada com todas as configurações

⚠️ **Nota**: Este método requer Microsoft Excel instalado no Windows.

### Opção 2: Criação Manual

1. Abra o Microsoft Excel
2. Crie um novo arquivo
3. Salve como "ControlePonto.xlsm" (Pasta de Trabalho Habilitada para Macro)
4. Pressione `Alt + F11` para abrir o Editor VBA
5. No menu, clique em `Inserir > Módulo`
6. Copie todo o código do arquivo `ControlePonto.bas`
7. Cole no módulo criado
8. Salve e feche o Editor VBA
9. Execute a macro `CriarNovaPlanilhaMes` para configurar a primeira planilha

## 📊 Estrutura da Planilha

| Coluna | Descrição | Formato |
|--------|-----------|---------|
| A | Dia da semana | Texto |
| B | Data | dd/mm/aaaa |
| C | Entrada | [hh]:mm |
| D | Saída | [hh]:mm |
| E | Total Horas | [hh]:mm (calculado) |
| F | Hora Extra | [hh]:mm (calculado) |
| G | HE c/50% | [hh]:mm (calculado) |
| H | Total Final | [hh]:mm (calculado) |

## 💡 Exemplo de Uso

**Plantão 24h iniciando dia 01 às 07:00 e terminando dia 02 às 08:45:**

- Dia 01: Entrada = 07:00, Saída = (vazio)
- Dia 02: Entrada = (vazio), Saída = 08:45

**Resultado na linha do dia 02:**
- Total Horas: 25:45
- Hora Extra: 1:45 (excedente de 24h)
- HE c/50%: 2:37 (1:45 + 50%)
- Total Final: 26:37 (24:00 + 2:37)

## 🔒 Segurança

- **Senha de proteção**: `ponto2025`
- Apenas células de entrada/saída são editáveis
- Fórmulas protegidas contra alteração

## 📈 Relatórios

O botão "Gerar Relatório Mensal" exibe:
- Total de horas normais trabalhadas
- Total de horas extras (com 50%)
- Total geral do mês

## 🎯 Dicas de Uso

1. **Plantões noturnos**: A saída pode ser menor que a entrada (sistema entende que atravessou o dia)
2. **Correções**: Delete o conteúdo da célula e digite novamente
3. **Novo mês**: Use o botão "Gerar Próximo Mês" ao invés de copiar abas
4. **Backup**: Salve regularmente e mantenha cópias de segurança

## ⚠️ Requisitos

- Microsoft Excel 2013 ou superior
- Macros habilitadas
- Windows (para script VBS)

## 🐛 Resolução de Problemas

### "Macros desabilitadas"
1. Vá em Arquivo > Opções > Central de Confiabilidade
2. Clique em "Configurações da Central de Confiabilidade"
3. Selecione "Configurações de Macro"
4. Escolha "Habilitar todas as macros"

### "Erro ao criar nova planilha"
- Verifique se não existe uma aba com o mesmo nome
- Certifique-se de que as macros estão habilitadas

### "Fórmulas não calculam"
- Verifique se o cálculo automático está ativado
- Pressione F9 para forçar recálculo

## 📞 Suporte

Para dúvidas ou sugestões sobre a planilha, verifique:
1. Se as macros estão habilitadas
2. Se está usando a versão correta do Excel
3. Se seguiu corretamente as instruções de instalação

---

**Versão**: 1.0  
**Data**: Janeiro 2025  
**Desenvolvido para**: Controle de plantões 24h x 72h