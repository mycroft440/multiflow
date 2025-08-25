#!/usr/bin/env python3
if True:
    # -*- coding: utf-8 -*-

    # Importações necessárias para o funcionamento do script
    import sys  # Para manipulação de caminhos e saída de erro
    import os  # Para operações com arquivos e diretórios
    import time  # Para delays e temporizações
    import re  # Para expressões regulares, usado em limpeza de texto
    import subprocess  # Para execução de comandos externos
    import psutil  # Para monitoramento de recursos do sistema (CPU, RAM)
    import shutil  # Para obter tamanho do terminal
    from datetime import datetime  # Para manipulação de datas e tempos
    import random  # Para escolhas aleatórias, como mensagens de boas-vindas
    import importlib  # Para importação dinâmica de módulos
    import importlib.util  # Para especificações de módulos a partir de arquivos

    # ==================== BOOTSTRAP DE IMPORTAÇÃO ====================
    # Esta seção localiza a raiz do projeto e importa módulos necessários 
    # dinamicamente.

    # Função para encontrar a raiz do projeto MultiFlow
    def _find_multiflow_root():
        candidates = []  # Lista de caminhos candidatos para a raiz
        # 1) Variável de ambiente
        env_home = os.environ.get("MULTIFLOW_HOME")  # Obtém variável de 
        # ambiente se definida
        if env_home:
            candidates.append(env_home)

        # 2) Caminho padrão
        candidates.append("/opt/multiflow")  # Adiciona caminho padrão

        # 3) Diretório do script e ascendentes
        try:
            script_dir = os.path.dirname(os.path.realpath(__file__))  # 
            # Diretório atual do script
            candidates.append(script_dir)
            # Subir níveis na hierarquia de diretórios
            parent = script_dir
            for _ in range(5):
                parent = os.path.dirname(parent)
                if parent and parent not in candidates:
                    candidates.append(parent)
        except Exception:
            pass  # Ignora erros ao obter caminho

        # 4) Alguns caminhos comuns alternativos
        for extra in ("/root/multiflow", "/usr/local/multiflow", 
        "/usr/share/multiflow"):
            candidates.append(extra)  # Adiciona caminhos alternativos

        # Normaliza e remove duplicados preservando ordem
        normalized = []  # Lista normalizada
        seen = set()  # Conjunto para rastrear caminhos vistos
        for c in candidates:
            if not c:
                continue
            nc = os.path.abspath(c)  # Normaliza para caminho absoluto
            if nc not in seen:
                normalized.append(nc)
                seen.add(nc)

        # Valida candidatos: precisam ter pastas 'menus', 'ferramentas' e 'conexoes'
        for root in normalized:
            if (
                os.path.isdir(os.path.join(root, "menus"))
                and os.path.isdir(os.path.join(root, "ferramentas"))
                and os.path.isdir(os.path.join(root, "conexoes"))
            ):
                return root  # Retorna a raiz válida encontrada
        return None  # Nenhuma raiz válida encontrada

    # Função para importar módulo por nome
    def _import_by_module_name(modname):
        try:
            return importlib.import_module(modname)  # Tenta importar o módulo
        except Exception:
            return None  # Retorna None em caso de erro

    # Função para importar módulo por caminho de arquivo
    def _import_by_file_path(alias, filepath):
        if not os.path.exists(filepath):
            return None  # Arquivo não existe
        try:
            spec = importlib.util.spec_from_file_location(alias, filepath)  # 
            # Cria especificação do módulo
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)  # Cria módulo a 
                # partir da spec
                spec.loader.exec_module(module)  # Executa o módulo
                return module
        except Exception:
            return None  # Retorna None em caso de erro
        return None

    # Função principal de bootstrap para importações
    def bootstrap_imports():
        # Tenta adicionar a raiz ao sys.path e importar como pacote
        root = _find_multiflow_root()  # Encontra raiz do projeto
        if root and root not in sys.path:
            sys.path.insert(0, root)  # Insere raiz no início do sys.path

        # Dicionário de módulos a importar
        targets = {
            "manusear_usuarios": "ferramentas.manusear_usuarios",
            "menu_badvpn": "menus.menu_badvpn",
            "menu_bloqueador": "menus.menu_bloqueador",
            "menu_servidor_download": "menus.menu_servidor_download",
            "menu_openvpn": "menus.menu_openvpn",
        }

        imported = {}  # Dicionário de módulos importados com sucesso
        # 1) Tenta importar por nome de módulo (requer __init__.py nas pastas)
        for alias, modname in targets.items():
            mod = _import_by_module_name(modname)
            if mod:
                imported[alias] = mod  # Adiciona se importado

        # 2) Fallback: importar por caminho de arquivo
        missing = [alias for alias in targets.keys() if alias not in imported]  
        # Módulos faltando
        if missing and root:
            for alias in missing:
                modname = targets[alias]
                rel = modname.replace(".", "/") + ".py"  # Caminho relativo do 
                # arquivo
                modpath = os.path.join(root, rel)  # Caminho completo
                mod = _import_by_file_path(alias, modpath)
                if mod:
                    imported[alias] = mod  # Adiciona se importado

        # 3) Se ainda faltam, mostra diagnóstico útil
        still_missing = [alias for alias in targets.keys() if alias not in 
        imported]  # Módulos ainda faltando
        if still_missing:
            red = "\033[91m"  # Cor vermelha para erro
            yel = "\033[93m"  # Cor amarela para dicas
            rst = "\033[0m"  # Reset de cor
            # Junta a mensagem de erro em uma linha para evitar quebra de linha não esperada
            sys.stderr.write(
                f"{red}[ERRO] Não foi possível carregar os módulos: {', '.join(still_missing)}{rst}\n"
            )
            # Mensagens de dica em múltiplas linhas utilizando concatenação implícita
            sys.stderr.write(
                f"{yel}Dicas:\n"
                f" - Verifique a estrutura: {root or '/opt/multiflow'}/menus e /ferramentas existem?\n"
                f" - Crie __init__.py dentro de 'menus' e 'ferramentas' para habilitar import como pacote.\n"
                f" - Confirme MULTIFLOW_HOME ou o caminho real do projeto.\n"
                f" - Você está rodando com o Python correto (sudo pode usar outro Python)?{rst}\n"
            )
            sys.stderr.write(f"\nCaminho detectado: {root or 'N/D'}\n")
            sys.stderr.write("sys.path atual:\n - " + "\n - ".join(sys.path) + 
            "\n")
            sys.exit(1)  # Sai com erro

        # Exporta para globals
        globals().update(imported)  # Atualiza o escopo global com módulos 
        # importados

    # Inicializa importações do projeto
    bootstrap_imports()  # Chama a função de bootstrap

    # Importando módulos do projeto (já resolvidos pelo bootstrap)
    from ferramentas import manusear_usuarios  # noqa: F401  (já no globals) - 
    # Ignora linting
    from menus import menu_badvpn, menu_bloqueador, menu_servidor_download, menu_openvpn  # noqa: F401 - Ignora linting

    # ==================== GERENCIAMENTO DE TERMINAL/RENDER ====================
    # Classe para gerenciar o terminal, incluindo tela alternativa e 
    # renderização.

    class TerminalManager:
        _in_alt = False  # Flag para indicar se está na tela alternativa
        USE_ALT = True  # Ativar tela alternativa (desative se houver problemas)

        @staticmethod
        def size():
            ts = shutil.get_terminal_size(fallback=(80, 24))  # Obtém tamanho do
            # terminal
            return ts.columns, ts.lines  # Retorna colunas e linhas

        @staticmethod
        def enter_alt_screen():
            if TerminalManager.USE_ALT and not TerminalManager._in_alt:
                sys.stdout.write("\033[?1049h")  # Entra na tela alternativa
                sys.stdout.flush()
                TerminalManager._in_alt = True  # Atualiza flag

        @staticmethod
        def leave_alt_screen():
            if TerminalManager._in_alt:
                sys.stdout.write("\033[?1049l")  # Sai da tela alternativa
                sys.stdout.flush()
                TerminalManager._in_alt = False  # Atualiza flag

        @staticmethod
        def _manual_clear_all_cells():
            cols, lines = TerminalManager.size()  # Obtém tamanho
            blank_line = " " * cols  # Linha em branco
            sys.stdout.write("\033[0m\033[?7l")  # Reset e desativa wrap
            for row in range(1, lines + 1):
                sys.stdout.write(f"\033[{row};1H{blank_line}")  # Limpa cada 
                # linha
            sys.stdout.write("\033[1;1H\033[?7h")  # Volta ao topo e ativa wrap
            sys.stdout.flush()

        @staticmethod
        def render(frame_str):
            sys.stdout.write("\033[?25l")  # Esconde cursor
            sys.stdout.flush()
            TerminalManager._manual_clear_all_cells()  # Limpa tela
            sys.stdout.write("\033[1;1H")  # Posiciona no topo
            sys.stdout.write(frame_str)  # Escreve o frame
            sys.stdout.flush()

        @staticmethod
        def before_input():
            sys.stdout.write("\033[?25h\033[2K\r")  # Mostra cursor e limpa 
            # linha
            sys.stdout.flush()

        @staticmethod
        def after_input():
            sys.stdout.write("\033[?25l")  # Esconde cursor
            sys.stdout.flush()

    # ==================== CORES E ÍCONES ====================
    # Classes para cores ANSI e ícones usados na UI.

    class MC:
        # Cores e estilos básicos
        RESET = '\033[0m'  # Reset de estilo
        BOLD = '\033[1m'  # Negrito
        DIM = '\033[2m'  # Fraco
        ITALIC = '\033[3m'  # Itálico
        UNDERLINE = '\033[4m'  # Sublinhado
        REVERSE = '\033[7m'  # Inverso

        # Gradientes e variações de cores
        PURPLE_GRADIENT = '\033[38;2;147;51;234m'
        PURPLE_LIGHT = '\033[38;2;196;181;253m'
        PURPLE_DARK = '\033[38;2;107;33;168m'
        CYAN_GRADIENT = '\033[38;2;6;182;212m'
        CYAN_LIGHT = '\033[38;2;165;243;252m'
        CYAN_DARK = '\033[38;2;14;116;144m'
        GREEN_GRADIENT = '\033[38;2;34;197;94m'
        GREEN_LIGHT = '\033[38;2;134;239;172m'
        GREEN_DARK = '\033[38;2;22;163;74m'
        ORANGE_GRADIENT = '\033[38;2;251;146;60m'
        ORANGE_LIGHT = '\033[38;2;254;215;170m'
        ORANGE_DARK = '\033[38;2;234;88;12m'
        RED_GRADIENT = '\033[38;2;239;68;68m'
        RED_LIGHT = '\033[38;2;254;202;202m'
        RED_DARK = '\033[38;2;185;28;28m'
        YELLOW_GRADIENT = '\033[38;2;250;204;21m'
        YELLOW_LIGHT = '\033[38;2;254;240;138m'
        YELLOW_DARK = '\033[38;2;202;138;4m'
        BLUE_GRADIENT = '\033[38;2;59;130;246m'
        BLUE_LIGHT = '\033[38;2;191;219;254m'
        BLUE_DARK = '\033[38;2;29;78;216m'
        PINK_GRADIENT = '\033[38;2;236;72;153m'
        PINK_LIGHT = '\033[38;2;251;207;232m'
        WHITE = '\033[97m'  # Branco
        GRAY = '\033[38;2;156;163;175m'  # Cinza
        LIGHT_GRAY = '\033[38;2;229;231;235m'  # Cinza claro
        DARK_GRAY = '\033[38;2;75;85;99m'  # Cinza escuro

    class Icons:
        # Ícones emoji para UI
        SERVER = "️ "
        USERS = " "
        NETWORK = " "
        TOOLS = " "
        SHIELD = "️ "
        CHART = " "
        CPU = "⚙️ "
        RAM = " "
        ACTIVE = ""
        INACTIVE = ""
        BACK = "◀ "
        EXIT = " "
        CLOCK = " "
        SYSTEM = " "
        UPDATE = " "  # Ícone de atualização (corrigido)
        DOWNLOAD = " "
        KEY = " "
        LOCK = " "
        UNLOCK = " "
        CHECK = "✅ "
        CROSS = "❌ "
        WARNING = "⚠️ "
        INFO = "ℹ️ "
        ROCKET = " "
        DIAMOND = " "

        # Ícones de caixa para bordas
        BOX_TOP_LEFT = "╭"
        BOX_TOP_RIGHT = "╮"
        BOX_BOTTOM_LEFT = "╰"
        BOX_BOTTOM_RIGHT = "╯"
        BOX_HORIZONTAL = "─"
        BOX_VERTICAL = "│"

    # ==================== HELPERS DE UI (RETORNAM STRING) ====================
    # Funções auxiliares para construir elementos da interface de usuário.

    # Função para criar linha gradiente
    def gradient_line(width=80, char='═', colors=(MC.PURPLE_GRADIENT, 
    MC.CYAN_GRADIENT, MC.BLUE_GRADIENT)):
        seg = max(1, width // len(colors))  # Segmento por cor
        out = []  # Lista de partes
        used = 0  # Largura usada
        for i, c in enumerate(colors):
            run = seg if i < len(colors) - 1 else (width - used)  # Calcula 
            # comprimento
            out.append(f"{c}{char * run}")
            used += run
        return "".join(out) + MC.RESET + "\n"  # Retorna linha com reset

    # Função para cabeçalho moderno com logo
    def modern_header():
        cols, _ = TerminalManager.size()  # Obtém largura
        width = max(60, min(cols - 2, 100))  # Ajusta largura
        s = []  # Lista de strings
        s.append(gradient_line(width))  # Adiciona linha gradiente
        # Linhas do logo colorido
        # Constrói as linhas do logo como strings únicas para evitar quebras indesejadas.
        logo_lines = [
            f"{MC.PURPLE_LIGHT}███╗   ███╗{MC.CYAN_LIGHT}██╗   ██╗{MC.BLUE_LIGHT}██╗  ████████╗{MC.GREEN_LIGHT}██╗███████╗{MC.ORANGE_LIGHT}██╗      {MC.PINK_LIGHT}██████╗ {MC.YELLOW_LIGHT}██╗    ██╗{MC.RESET}",
            f"{MC.PURPLE_GRADIENT}████╗ ████║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║  ╚══██╔══╝{MC.GREEN_GRADIENT}██║██╔════╝{MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██╔═══██╗{MC.YELLOW_GRADIENT}██║    ██║{MC.RESET}",
            f"{MC.PURPLE_GRADIENT}██╔████╔██║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║     ██║   {MC.GREEN_GRADIENT}██║█████╗  {MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██║   ██║{MC.YELLOW_GRADIENT}██║ █╗ ██║{MC.RESET}",
            f"{MC.PURPLE_DARK}██║╚██╔╝██║{MC.CYAN_DARK}██║   ██║{MC.BLUE_DARK}██║     ██║   {MC.GREEN_DARK}██║██╔══╝  {MC.ORANGE_DARK}██║     {MC.RED_GRADIENT}██║   ██║{MC.YELLOW_DARK}██║███╗██║{MC.RESET}",
            f"{MC.PURPLE_DARK}██║ ╚═╝ ██║{MC.CYAN_DARK}╚██████╔╝{MC.BLUE_DARK}███████╗██║   {MC.GREEN_DARK}██║██║     {MC.ORANGE_DARK}███████╗{MC.RED_DARK}╚██████╔╝{MC.YELLOW_DARK}╚███╔███╔╝{MC.RESET}",
            f"{MC.DARK_GRAY}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{MC.RESET}"
        ]
        s.extend(["  " + l + "\n" for l in logo_lines])  # Adiciona logo com 
        # indentação
        s.append(f"\n{MC.GRAY}{'═' * width}{MC.RESET}\n")  # Linha separadora
        # Título centralizado da aplicação
        s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}{'Sistema Avançado de Gerenciamento VPS'.center(width)}{MC.RESET}\n")
        # Outra linha separadora
        s.append(f"{MC.GRAY}{'═' * width}{MC.RESET}\n\n")
        return "".join(s)  # Retorna cabeçalho completo

    # Função para criar caixa moderna
    def modern_box(title, content_lines, icon="", primary=MC.CYAN_GRADIENT, 
    secondary=MC.CYAN_LIGHT):
        cols, _ = TerminalManager.size()  # Obtém largura
        width = max(54, min(cols - 6, 100))  # Ajusta largura da caixa
        title_text = f" {icon}{title} " if icon else f" {title} "  # Texto do 
        # título com ícone
        extra = -1 if icon else 0  # Ajuste para ícone
        # Cabeçalho da caixa
        header = (
            f"{primary}{Icons.BOX_TOP_LEFT}{Icons.BOX_HORIZONTAL * 10}"
            f"{secondary}┤{MC.BOLD}{MC.WHITE}{title_text}{MC.RESET}{secondary}├"
            f"{primary}{Icons.BOX_HORIZONTAL * (width - len(title_text) - 12 + extra)}"
            f"{Icons.BOX_TOP_RIGHT}{MC.RESET}\n"
        )
        body = ""  # Corpo da caixa
        for line in content_lines:
            clean = re.sub(r'\033\[[0-9;]*m', '', line)  # Remove códigos de cor
            # para cálculo de comprimento
            pad = width - len(clean) - 2  # Padding necessário
            if pad < 0:
                vis = clean[:width - 5] + "..."  # Trunca se muito longo
                line = line.replace(clean, vis)
                pad = width - len(vis) - 2
            # Adiciona cada linha com bordas em uma única expressão para evitar quebras de string
            body += f"{primary}{Icons.BOX_VERTICAL}{MC.RESET} {line}{' ' * pad} {primary}{Icons.BOX_VERTICAL}{MC.RESET}\n"
        # Rodapé da caixa
        # Rodapé da caixa
        footer = f"{primary}{Icons.BOX_BOTTOM_LEFT}{Icons.BOX_HORIZONTAL * width}{Icons.BOX_BOTTOM_RIGHT}{MC.RESET}\n"
        return header + body + footer  # Retorna caixa completa

    # Função para opção de menu
    def menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, badge=""):
        # Constrói a representação textual do número da opção
        num = (
            f"{color}{MC.BOLD}[{number}]{MC.RESET}"
            if number != "0"
            else f"{MC.RED_GRADIENT}{MC.BOLD}[0]{MC.RESET}"
        )
        # Constrói o badge opcional
        b = f" {MC.PURPLE_GRADIENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
        return f"  {num} {icon}{MC.WHITE}{text}{b}{MC.RESET}\n"

    # Função para barra de progresso
    def progress_bar(percent, width=18):
        filled = int(percent * width / 100)  # Parte preenchida
        empty = width - filled  # Parte vazia
        # Escolhe cor baseada na porcentagem
        if percent < 30: c = MC.GREEN_GRADIENT
        elif percent < 60: c = MC.YELLOW_GRADIENT
        elif percent < 80: c = MC.ORANGE_GRADIENT
        else: c = MC.RED_GRADIENT
        # Constrói a barra de progresso em uma única linha
        return f"[{c}{'█' * filled}{MC.DARK_GRAY}{'░' * empty}{MC.RESET}] {c}{percent:5.1f}%{MC.RESET}"

    # Função para linha de rodapé
    def footer_line(status_msg=""):
        cols, _ = TerminalManager.size()  # Obtém largura
        width = max(60, min(cols - 2, 100))  # Ajusta largura
        bar = f"\n{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"  # Barra separadora
        status = f"{MC.GRAY}MultiFlow{MC.RESET}"  # Texto base
        if status_msg:
            status += f"  {MC.YELLOW_GRADIENT}{status_msg}{MC.RESET}"  # 
            # Adiciona mensagem de status
        return bar + status + "\n" + f"{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"
    # Retorna rodapé

    # ==================== INFO DO SISTEMA ====================
    # Funções para obter informações do sistema.

    # Função para monitorar uso de recursos
    def monitorar_uso_recursos(intervalo_cpu=0.10):
        try:
            ram = psutil.virtual_memory()  # Obtém uso de RAM
            cpu_percent = psutil.cpu_percent(interval=intervalo_cpu)  # Obtém 
            # uso de CPU
            return {'ram_percent': ram.percent, 'cpu_percent': cpu_percent}  # 
            # Retorna dicionário
        except Exception:
            return {'ram_percent': 0, 'cpu_percent': 0}  # Retorna zeros em erro

    # Função para obter info do sistema
    def get_system_info():
        info = {"os_name": "Desconhecido", "ram_percent": 0, "cpu_percent": 0}  
        # Info padrão
        try:
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    pairs = [line.strip().split('=', 1) for line in f if '=' in 
                    line]  # Parseia arquivo
                os_info = dict(pairs)
                info["os_name"] = os_info.get('PRETTY_NAME', 'Linux').strip('"')
        # Nome do OS
            info.update(monitorar_uso_recursos())  # Atualiza com recursos
        except Exception:
            pass  # Ignora erros
        return info  # Retorna info

    # Função para obter uptime do sistema
    def get_system_uptime():
        try:
            with open('/proc/uptime', 'r') as f:
                up = float(f.readline().split()[0])  # Lê uptime em segundos
            d = int(up // 86400)  # Dias
            h = int((up % 86400) // 3600)  # Horas
            m = int((up % 3600) // 60)  # Minutos
            if d: return f"{d}d {h}h {m}m"
            if h: return f"{h}h {m}m"
            return f"{m}m"  # Retorna formato legível
        except Exception:
            return "N/A"  # Não disponível

    # Função para obter serviços ativos
    def get_active_services():
        services = []  # Lista de serviços
        def run_cmd(cmd):
            try:
                return subprocess.check_output(cmd, text=True, 
                stderr=subprocess.DEVNULL).strip()  # Executa comando
            except Exception:
                return ""  # Retorna vazio em erro
        swapon = run_cmd(['swapon', '--show'])  # Verifica swap
        if 'zram' in swapon:
            services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} ZRAM{MC.RESET}")
        if '/swapfile' in swapon or 'partition' in swapon:
            services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} SWAP{MC.RESET}")
        if os.path.exists('/etc/openvpn/server.conf'):
            # Indica que o serviço OpenVPN está ativo
            services.append(f"{MC.CYAN_GRADIENT}{Icons.ACTIVE} OpenVPN{MC.RESET}")
        try:
            r = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], 
            capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == "active":
                # Indica que o serviço BadVPN está ativo
                services.append(f"{MC.PURPLE_GRADIENT}{Icons.ACTIVE} BadVPN{MC.RESET}")
        except Exception:
            pass
        try:
            r = subprocess.run(["systemctl", "is-active", "ssh"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip() == "active":
                # Indica que o serviço SSH está ativo
                services.append(f"{MC.ORANGE_GRADIENT}{Icons.ACTIVE} SSH{MC.RESET}")
        except Exception:
            pass
        return services  # Retorna lista

    # Função para painel do sistema
    def system_panel_box():
        info = get_system_info()  # Obtém info
        uptime = get_system_uptime()  # Obtém uptime
        # Trunca o nome do sistema operacional se for muito longo
        os_name = (info['os_name'][:35] + '...') if len(info['os_name']) > 38 else info['os_name']
        ram_bar = progress_bar(info["ram_percent"])  # Barra de RAM
        cpu_bar = progress_bar(info["cpu_percent"])  # Barra de CPU
        services = get_active_services()  # Serviços ativos

        # Conteúdo do painel
        content = [
            f"{MC.CYAN_LIGHT}Sistema:{MC.RESET} {MC.WHITE}{os_name}{MC.RESET}",
            f"{MC.CYAN_LIGHT}RAM:{MC.RESET} {ram_bar}",
            f"{MC.CYAN_LIGHT}CPU:{MC.RESET} {cpu_bar}",
            f"{MC.CYAN_LIGHT}Uptime:{MC.RESET} {MC.WHITE}{uptime}{MC.RESET}",
        ]
        if services:
            line1 = f"{MC.CYAN_LIGHT}Serviços:{MC.RESET} " + " │ ".join(services[:4])  # Primeira linha de serviços
            content.append(line1)
            if len(services) > 4:
                content.append(" " * 13 + " │ ".join(services[4:8]))  # Segunda 
                # linha se necessário
        else:
            # Nenhum serviço ativo
            content.append(f"{MC.CYAN_LIGHT}Serviços:{MC.RESET} {MC.GRAY}Nenhum serviço ativo{MC.RESET}")

        return modern_box("PAINEL DO SISTEMA", content, Icons.CHART, 
        MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)  # Retorna caixa

    # Função para linha de boas-vindas aleatória
    def welcome_line():
        msgs = [  # Mensagens possíveis
            f"{Icons.ROCKET} Bem-vindo ao MultiFlow!",
            f"{Icons.DIAMOND} Experiência premium no seu terminal.",
            f"{Icons.CHECK} Sistema pronto para uso.",
        ]
        msg = random.choice(msgs)  # Escolhe aleatória
        cols, _ = TerminalManager.size()  # Obtém largura
        width = max(60, min(cols - 2, 100))  # Ajusta
        return f"\n{MC.CYAN_GRADIENT}{MC.BOLD}{msg.center(width)}{MC.RESET}\n\n"
    # Retorna centralizada

    # ==================== RENDER DE TELAS COMPLETAS ====================
    # Funções para construir frames completos de telas.

    # Frame do menu principal
    def build_main_frame(status_msg=""):
        s = []  # Lista de strings
        s.append(modern_header())  # Cabeçalho
        s.append(system_panel_box())  # Painel do sistema
        s.append(welcome_line())  # Boas-vindas
        s.append(modern_box("MENU PRINCIPAL", [], Icons.DIAMOND, 
        MC.BLUE_GRADIENT, MC.BLUE_LIGHT))  # Caixa do menu
        s.append("\n")
        # Opções do menu
        s.append(menu_option("1", "Gerenciar Usuários SSH", "", MC.GREEN_DARK))
        s.append(menu_option("2", "Monitor Online", "", MC.GREEN_DARK))
        s.append(menu_option("3", "Gerenciar Conexões", "", MC.GREEN_DARK))
        s.append(menu_option("4", "BadVPN", "", MC.GREEN_DARK))
        s.append(menu_option("5", "Ferramentas", "", MC.GREEN_DARK))
        s.append(menu_option("6", "Servidor de Download", "", MC.GREEN_DARK))
        s.append(menu_option("7", "Atualizar Multiflow", "", MC.ORANGE_GRADIENT,
        badge="v2"))
        s.append("\n")
        s.append(menu_option("0", "Sair", "", MC.RED_DARK))
        s.append(footer_line(status_msg))  # Rodapé
        return "".join(s)  # Retorna frame

    # Frame do menu de conexões
    def build_connections_frame(status_msg=""):
        s = []  # Lista de strings
        s.append(modern_header())  # Cabeçalho
        s.append(system_panel_box())  # Painel
        s.append("\n")
        s.append(modern_box("GERENCIAR CONEXÕES", [], Icons.NETWORK, 
        MC.CYAN_GRADIENT, MC.CYAN_LIGHT))  # Caixa
        s.append("\n")
        s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}Protocolos{MC.RESET}\n")  # Seção 
        # protocolos
        s.append(menu_option("1", "OpenVPN", "", MC.GREEN_GRADIENT))
        s.append(menu_option("2", "SlowDNS", "", MC.GREEN_GRADIENT))
        s.append(menu_option("3", "Hysteria", "", MC.GREEN_GRADIENT))
        s.append(menu_option("4", "V2ray", "", MC.GREEN_GRADIENT))
        s.append(menu_option("5", "Xray", "", MC.GREEN_GRADIENT))
        s.append("\n")
        # Seção de proxies multiprotocolo
        s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}Proxys Multiprotocolo{MC.RESET}\n")
        # As posições foram trocadas: opção 6 agora é Rusty Proxy e opção 7 é 
        # Multi-Flow Proxy
        s.append(menu_option("6", "Rusty Proxy", "", MC.PURPLE_GRADIENT))
        s.append(menu_option("7", "Multi-Flow Proxy", "", MC.BLUE_GRADIENT))
        # Removido: opção 8 (DragonCore Proxy)
        s.append("\n")
        s.append(menu_option("0", "Voltar ao Menu Principal", "", 
        MC.YELLOW_GRADIENT))
        s.append(footer_line(status_msg))  # Rodapé
        return "".join(s)  # Retorna frame

    # Frame do menu de ferramentas
    def build_tools_frame(status_msg=""):
        s = []  # Lista de strings
        s.append(modern_header())  # Cabeçalho
        s.append(system_panel_box())  # Painel
        s.append("\n")
        s.append(modern_box("FERRAMENTAS DE OTIMIZAÇÃO", [], Icons.TOOLS, 
        MC.ORANGE_GRADIENT, MC.ORANGE_LIGHT))  # Caixa
        s.append("\n")
        # Opções sem ícones, com badge para otimizador
        s.append(menu_option("1", "Otimizador de VPS", "", MC.GREEN_GRADIENT, 
        badge="TURBO"))
        s.append(menu_option("2", "Bloqueador de Sites", "", MC.RED_GRADIENT))
        s.append("\n")
        s.append(menu_option("0", "Voltar ao Menu Principal", "", 
        MC.YELLOW_GRADIENT))
        s.append(footer_line(status_msg))  # Rodapé
        return "".join(s)  # Retorna frame

    # Frame do atualizador
    def build_updater_frame():
        s = []  # Lista de strings
        s.append(modern_header())  # Cabeçalho
        s.append("\n")
        # Caixa com instruções de atualização
        s.append(modern_box(
            "ATUALIZADOR MULTIFLOW",
            [
                f"{MC.YELLOW_GRADIENT}{Icons.INFO} Baixar a versão mais recente do GitHub.{MC.RESET}",
                f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Serviços como BadVPN serão parados.{MC.RESET}",
                f"{MC.RED_GRADIENT}{Icons.WARNING} O programa encerra após a atualização.{MC.RESET}",
                f"{MC.WHITE}{Icons.INFO} Reinicie com 'multiflow' após concluir.{MC.RESET}"
            ],
            Icons.UPDATE,
            MC.PURPLE_GRADIENT,
            MC.PURPLE_LIGHT,
        ))
        s.append(footer_line())  # Rodapé
        return "".join(s)  # Retorna frame

    # ==================== CHECK ROOT ====================
    # Função para verificar se executado como root.

    def check_root():
        try:
            if os.geteuid() != 0:  # Não é root
                TerminalManager.enter_alt_screen()  # Entra em tela alt
                # Renderiza aviso
                TerminalManager.render(
                    modern_header()
                    + modern_box(
                        "AVISO DE SEGURANÇA",
                        [
                            f"{MC.RED_GRADIENT}{Icons.WARNING} Este script precisa ser executado como root!{MC.RESET}",
                            f"{MC.YELLOW_GRADIENT}Algumas operações podem falhar sem privilégios adequados.{MC.RESET}",
                        ],
                        Icons.SHIELD,
                        MC.RED_GRADIENT,
                        MC.RED_LIGHT,
                    )
                    + footer_line()
                )
                TerminalManager.before_input()  # Prepara input
                # Pergunta se o usuário deseja continuar sem privilégios de root
                resp = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar mesmo assim? (s/n): {MC.RESET}").strip().lower()
                TerminalManager.after_input()  # Após input
                if resp != 's':
                    TerminalManager.leave_alt_screen()  # Sai da tela
                    sys.exit(0)  # Sai
                return False  # Continua sem root
            return True  # É root
        except AttributeError:
            return True  # Plataforma sem geteuid

    # ==================== MENUS (COM RENDER ÚNICO POR FRAME) 
    # ====================
    # Funções para menus específicos.

    # Menu de gerenciamento de usuários SSH
    def ssh_users_main_menu():
        TerminalManager.leave_alt_screen()  # Sai da tela alt
        try:
            manusear_usuarios.main()  # Chama menu principal
        finally:
            TerminalManager.enter_alt_screen()  # Volta à tela alt

    # Menu de monitor online
    def monitor_online_menu():
        TerminalManager.leave_alt_screen()  # Sai da tela
        try:
            root = _find_multiflow_root()  # Encontra raiz
            usuarios_online_path = os.path.join(root, 'ferramentas', 
            'usuarios_online.py')  # Caminho do script
            subprocess.run([sys.executable, usuarios_online_path], check=True)  
            # Executa
        except Exception as e:
            print(f"Erro ao executar Monitor Online: {e}")  # Erro
        finally:
            TerminalManager.enter_alt_screen()  # Volta

    # Menu de conexões
    def conexoes_menu():
        status = ""  # Mensagem de status
        while True:
            TerminalManager.enter_alt_screen()  # Entra em tela
            TerminalManager.render(build_connections_frame(status))  # Renderiza
            TerminalManager.before_input()  # Prepara input
            # Lê a opção do usuário em uma única linha
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()  # Após input

            if choice == "1":
                TerminalManager.leave_alt_screen()  # Sai
                try:
                    menu_openvpn.main_menu()  # Chama OpenVPN
                finally:
                    TerminalManager.enter_alt_screen()  # Volta
                status = "OpenVPN: operação concluída."
            elif choice == "2":
                TerminalManager.leave_alt_screen()
                try:
                    root = _find_multiflow_root()
                    slowdns_path = os.path.join(root, 'conexoes', 'slowdns.py')
                    subprocess.run([sys.executable, slowdns_path], check=True)  
                    # Executa SlowDNS
                except Exception as e:
                    print(f"Erro ao executar SlowDNS: {e}")
                finally:
                    TerminalManager.enter_alt_screen()
                status = "SlowDNS: operação concluída."
            elif choice == "3":
                TerminalManager.leave_alt_screen()
                try:
                    root = _find_multiflow_root()
                    hysteria_path = os.path.join(root, 'conexoes', 
                    'hysteria.py')
                    subprocess.run([sys.executable, hysteria_path], check=True)
                    # Executa Hysteria
                except Exception as e:
                    print(f"Erro ao executar Hysteria: {e}")
                finally:
                    TerminalManager.enter_alt_screen()
                status = "Hysteria: operação concluída."
            elif choice == "4":
                TerminalManager.leave_alt_screen()
                try:
                    root = _find_multiflow_root()
                    v2ray_path = os.path.join(root, 'conexoes', 'v2ray.py')
                    subprocess.run([sys.executable, v2ray_path], check=True)  # 
                    # Executa V2ray
                except Exception as e:
                    print(f"Erro ao executar V2ray: {e}")
                finally:
                    TerminalManager.enter_alt_screen()
                status = "V2ray: operação concluída."
            elif choice == "5":
                TerminalManager.leave_alt_screen()
                try:
                    root = _find_multiflow_root()
                    xray_path = os.path.join(root, 'conexoes', 'xray.py')
                    subprocess.run([sys.executable, xray_path], check=True)  
                    # Executa Xray
                except Exception as e:
                    print(f"Erro ao executar Xray: {e}")
                finally:
                    TerminalManager.enter_alt_screen()
                status = "Xray: operação concluída."
            elif choice == "7":
                # Multi-Flow Proxy: chama o script Python com flag --menu para 
                # mostrar o menu interativo.
                TerminalManager.leave_alt_screen()
                try:
                    root = _find_multiflow_root()
                    multiflowproxy_path = os.path.join(root, 'conexoes', 
                    'multiflowproxy.py')
                    # Passa a flag --menu para exibir o menu do proxy.
                    subprocess.run([sys.executable, multiflowproxy_path, 
                    '--menu'], check=True)  # Executa Multi-Flow Proxy com menu
                except Exception as e:
                    print(f"Erro ao executar Multi-Flow Proxy: {e}")
                finally:
                    TerminalManager.enter_alt_screen()
                status = "Multi-Flow Proxy: operação concluída."
            elif choice == "6":
                # Rusty Proxy: tenta localizar o binário em vários locais, 
                # incluindo o diretório de conexões e o PATH do sistema.
                TerminalManager.leave_alt_screen()
                try:
                    # Encontra a raiz do projeto MultiFlow
                    root = _find_multiflow_root()
                    # Defina caminhos possíveis para o binário do RustyProxy.
                    # Em instalações antigas o binário é chamado "proxy",
                    # enquanto versões mais recentes usam "rustyproxy".
                    candidates = [
                        os.path.join(root, 'conexoes', 'rustyproxy'),
                        os.path.join(root, 'conexoes', 'proxy'),
                        shutil.which('rustyproxy'),
                        shutil.which('proxy'),
                    ]
                    # Selecione o primeiro executável existente
                    bin_path = None
                    for path in candidates:
                        if path and os.path.isfile(path) and os.access(path, os.X_OK):
                            bin_path = path
                            break
                    if not bin_path:
                        raise FileNotFoundError(
                            "Nenhum binário RustyProxy válido encontrado nas opções. "
                            "Certifique-se de que o arquivo exista e tenha permissão de execução."
                        )
                    # Executa o binário selecionado.
                    subprocess.run([bin_path], check=True)
                except Exception as e:
                    print(f"Erro ao executar Rusty Proxy: {e}")
                finally:
                    # Sempre retorna à tela alternativa independentemente do 
                    # sucesso da execução
                    TerminalManager.enter_alt_screen()
                status = "Rusty Proxy: operação concluída."
            elif choice == "0":
                return  # Volta ao menu anterior
            else:
                status = "Opção inválida. Tente novamente."  # Erro de escolha

    # Menu do otimizador VPS
    def otimizadorvps_menu():
        TerminalManager.leave_alt_screen()  # Sai da tela
        try:
            script_real_path = os.path.realpath(__file__)  # Caminho real do 
            # script
            script_dir = os.path.dirname(script_real_path)  # Diretório
            otimizador_path = os.path.join(script_dir, 'ferramentas', 
            'otimizadorvps.py')  # Caminho do otimizador
            subprocess.run([sys.executable, otimizador_path], check=True)  # 
            # Executa
        except Exception as e:
            print(f"\033[91mErro ao executar o otimizador: {e}\033[0m")  # Erro
        finally:
            input("Pressione Enter para continuar...")  # Pausa
            TerminalManager.enter_alt_screen()  # Volta

    # Menu de ferramentas
    def ferramentas_menu():
        status = ""  # Status
        while True:
            TerminalManager.enter_alt_screen()  # Entra
            TerminalManager.render(build_tools_frame(status))  # Renderiza
            TerminalManager.before_input()  # Prepara
            # Lê a opção do usuário
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()  # Após

            if choice == "1":
                otimizadorvps_menu()  # Chama otimizador
                status = "Otimizador executado."
            elif choice == "2":
                TerminalManager.leave_alt_screen()  # Sai
                try:
                    menu_bloqueador.main_menu()  # Chama bloqueador
                finally:
                    TerminalManager.enter_alt_screen()  # Volta
                status = "Bloqueador executado."
            elif choice == "0":
                return  # Volta
            else:
                status = "Opção inválida. Tente novamente."  # Erro

    # Função para atualizar MultiFlow
    def atualizar_multiflow():
        TerminalManager.enter_alt_screen()  # Entra
        TerminalManager.render(build_updater_frame())  # Renderiza
        TerminalManager.before_input()  # Prepara
        # Confirma se o usuário deseja prosseguir com a atualização
        confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar com a atualização? (s/n): {MC.RESET}").strip().lower()
        TerminalManager.after_input()  # Após

        if confirm == 's':
            try:
                script_dir = os.path.dirname(os.path.realpath(__file__))  # 
                # Diretório
                update_script_path = os.path.join(script_dir, 'update.py')  # 
                # Caminho antigo
                # Alterado para novo caminho
                update_script_path = os.path.join(script_dir, 'ferramentas', 
                'update.py')
                if not os.path.exists(update_script_path):
                    # Exibe mensagens de erro caso o script de update não seja encontrado
                    TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} 'update.py' não encontrado!{MC.RESET}\n")
                    TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} 'update.py' não encontrado em 'ferramentas'!{MC.RESET}\n")
                    time.sleep(2.0)
                    return
                TerminalManager.leave_alt_screen()  # Sai
                try:
                    subprocess.run(['sudo', sys.executable, update_script_path, 
                    '--update'], check=True)  # Executa atualização
                    print("\nAtualizado com sucesso. Reinicie com: multiflow\n")
                    # Sucesso
                    time.sleep(1.0)  # Pausa
                    sys.exit(0)  # Sai
                finally:
                    TerminalManager.enter_alt_screen()  # Volta
            except subprocess.CalledProcessError:
                TerminalManager.enter_alt_screen()
                TerminalManager.render(build_updater_frame() + 
                f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro durante a atualização.{MC.RESET}\n")  # 
                # Erro
                time.sleep(2.0)
            except Exception as e:
                TerminalManager.enter_alt_screen()
                TerminalManager.render(build_updater_frame() + 
                f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro inesperado: {e}{MC.RESET}\n")  # 
                # Erro
                time.sleep(2.0)
        else:
            TerminalManager.render(build_updater_frame() + 
            f"\n{MC.YELLOW_GRADIENT}{Icons.INFO} Atualização cancelada.{MC.RESET}\n")  # 
            # Cancelado
            time.sleep(1.2)  # Pausa

    # ==================== MENU PRINCIPAL ====================
    # Menu principal do aplicativo.

    def main_menu():
        check_root()  # Verifica root
        TerminalManager.enter_alt_screen()  # Entra em tela alt
        status = ""  # Status inicial

        while True:
            try:
                TerminalManager.render(build_main_frame(status))  # Renderiza 
                # menu
                TerminalManager.before_input()  # Prepara input
                # Lê a escolha no menu principal
                choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
                TerminalManager.after_input()  # Após

                if choice == "1":
                    ssh_users_main_menu()  # Usuários SSH
                    status = "Gerenciamento de usuários concluído."
                elif choice == "2":
                    monitor_online_menu()  # Monitor online
                    status = "Monitor Online concluído."
                elif choice == "3":
                    conexoes_menu()  # Conexões
                    status = "Conexões: operação concluída."
                elif choice == "4":
                    TerminalManager.leave_alt_screen()  # Sai
                    try:
                        menu_badvpn.main_menu()  # BadVPN
                    finally:
                        TerminalManager.enter_alt_screen()  # Volta
                    status = "BadVPN: operação concluída."
                elif choice == "5":
                    ferramentas_menu()  # Ferramentas
                    status = "Ferramentas: operação concluída."
                elif choice == "6":
                    TerminalManager.leave_alt_screen()  # Sai
                    try:
                        menu_servidor_download.main()  # Servidor download
                    finally:
                        TerminalManager.enter_alt_screen()  # Volta
                    status = "Servidor de download: operação concluída."
                elif choice == "7":
                    atualizar_multiflow()  # Atualizar
                    status = "Atualizador executado."
                elif choice == "0":
                    TerminalManager.render(build_main_frame("Saindo..."))  # 
                    # Renderiza saindo
                    time.sleep(0.4)  # Pausa
                    break  # Sai do loop
                else:
                    status = "Opção inválida. Pressione 1-7 ou 0 para sair."  # 
                    # Erro

            except KeyboardInterrupt:
                # Interrompido pelo usuário via Ctrl+C
                TerminalManager.render(build_main_frame("Interrompido pelo usuário."))
                time.sleep(0.5)
                break
            except Exception as e:
                TerminalManager.render(build_main_frame(f"Erro: {e}"))  # Erro 
                # geral
                time.sleep(1.0)
                break

        TerminalManager.leave_alt_screen()  # Sai da tela alt

    # ==================== EXECUÇÃO ====================
    # Ponto de entrada do script.

    if __name__ == "__main__":
        main_menu()  # Chama menu principal
