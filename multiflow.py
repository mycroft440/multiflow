#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import re
import subprocess
import psutil
import shutil
from datetime import datetime
import random
import importlib
import importlib.util

# ==================== BOOTSTRAP DE IMPORTAÇÃO ====================
# Tenta localizar a raiz do projeto (contendo 'menus' e 'ferramentas'),
# ajusta sys.path e importa os módulos necessários.
def _find_multiflow_root():
    candidates = []
    # 1) Variável de ambiente
    env_home = os.environ.get("MULTIFLOW_HOME")
    if env_home:
        candidates.append(env_home)

    # 2) Caminho padrão
    candidates.append("/opt/multiflow")

    # 3) Diretório do script e ascendentes
    try:
        script_dir = os.path.dirname(os.path.realpath(__file__))
        candidates.append(script_dir)
        # Subir alguns níveis procurando 'menus' e 'ferramentas'
        parent = script_dir
        for _ in range(5):
            parent = os.path.dirname(parent)
            if parent and parent not in candidates:
                candidates.append(parent)
    except Exception:
        pass

    # 4) Alguns caminhos comuns alternativos
    for extra in ("/root/multiflow", "/usr/local/multiflow", "/usr/share/multiflow"):
        candidates.append(extra)

    # Normaliza e remove duplicados preservando ordem
    normalized = []
    seen = set()
    for c in candidates:
        if not c:
            continue
        nc = os.path.abspath(c)
        if nc not in seen:
            normalized.append(nc)
            seen.add(nc)

    # Valida candidatos: precisam ter 'menus' e 'ferramentas'
    for root in normalized:
        if os.path.isdir(os.path.join(root, "menus")) and os.path.isdir(os.path.join(root, "ferramentas")) and os.path.isdir(os.path.join(root, "conexoes")):
            return root
    return None

def _import_by_module_name(modname):
    try:
        return importlib.import_module(modname)
    except Exception:
        return None

def _import_by_file_path(alias, filepath):
    if not os.path.exists(filepath):
        return None
    try:
        spec = importlib.util.spec_from_file_location(alias, filepath)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        return None
    return None

def bootstrap_imports():
    # Tenta adicionar a raiz ao sys.path e importar como pacote
    root = _find_multiflow_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)

    targets = {
        "manusear_usuarios": "ferramentas.manusear_usuarios",
        "menu_badvpn": "menus.menu_badvpn",
        "menu_bloqueador": "menus.menu_bloqueador",
        "menu_servidor_download": "menus.menu_servidor_download",
        "menu_openvpn": "menus.menu_openvpn",
        "menu_dragonproxy": "menus.menu_dragonproxy",  # Adicionado para importar o novo menu
    }

    imported = {}
    # 1) Tenta importar por nome de módulo (requer __init__.py nas pastas)
    for alias, modname in targets.items():
        mod = _import_by_module_name(modname)
        if mod:
            imported[alias] = mod

    # 2) Fallback: importar por caminho de arquivo
    missing = [alias for alias in targets.keys() if alias not in imported]
    if missing and root:
        for alias in missing:
            modname = targets[alias]
            rel = modname.replace(".", "/") + ".py"
            modpath = os.path.join(root, rel)
            mod = _import_by_file_path(alias, modpath)
            if mod:
                imported[alias] = mod

    # 3) Se ainda faltam, mostra diagnóstico útil
    still_missing = [alias for alias in targets.keys() if alias not in imported]
    if still_missing:
        red = "\033[91m"
        yel = "\033[93m"
        rst = "\033[0m"
        sys.stderr.write(f"{red}[ERRO] Não foi possível carregar os módulos: {', '.join(still_missing)}{rst}\n")
        sys.stderr.write(f"{yel}Dicas:\n" +
                         f" - Verifique a estrutura: {root or '/opt/multiflow'}/menus e /ferramentas existem?\n" +
                         f" - Crie __init__.py dentro de 'menus' e 'ferramentas' para habilitar import como pacote.\n" +
                         f" - Confirme MULTIFLOW_HOME ou o caminho real do projeto.\n" +
                         f" - Você está rodando com o Python correto (sudo pode usar outro Python)?{rst}\n")
        sys.stderr.write(f"\nCaminho detectado: {root or 'N/D'}\n")
        sys.stderr.write("sys.path atual:\n - " + "\n - ".join(sys.path) + "\n")
        sys.exit(1)

    # Exporta para globals
    globals().update(imported)

# Inicializa importações do projeto
bootstrap_imports()

# Importando módulos do projeto (já resolvidos pelo bootstrap)
from ferramentas import manusear_usuarios  # noqa: F401  (já no globals)
from menus import menu_badvpn, menu_bloqueador, menu_servidor_download, menu_openvpn, menu_dragonproxy  # noqa: F401  # Adicionado menu_dragonproxy

# ==================== GERENCIAMENTO DE TERMINAL/RENDER ====================
class TerminalManager:
    _in_alt = False
    USE_ALT = True  # Deixe False se perceber flicker ou comportamento estranho.

    @staticmethod
    def size():
        ts = shutil.get_terminal_size(fallback=(80, 24))
        return ts.columns, ts.lines

    @staticmethod
    def enter_alt_screen():
        if TerminalManager.USE_ALT and not TerminalManager._in_alt:
            sys.stdout.write("\033[?1049h")
            sys.stdout.flush()
            TerminalManager._in_alt = True

    @staticmethod
    def leave_alt_screen():
        if TerminalManager._in_alt:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            TerminalManager._in_alt = False

    @staticmethod
    def _manual_clear_all_cells():
        cols, lines = TerminalManager.size()
        blank_line = " " * cols
        sys.stdout.write("\033[0m\033[?7l")
        for row in range(1, lines + 1):
            sys.stdout.write(f"\033[{row};1H{blank_line}")
        sys.stdout.write("\033[1;1H\033[?7h")
        sys.stdout.flush()

    @staticmethod
    def render(frame_str):
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        TerminalManager._manual_clear_all_cells()
        sys.stdout.write("\033[1;1H")
        sys.stdout.write(frame_str)
        sys.stdout.flush()

    @staticmethod
    def before_input():
        sys.stdout.write("\033[?25h\033[2K\r")
        sys.stdout.flush()

    @staticmethod
    def after_input():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

# ==================== CORES E ÍCONES ====================
class MC:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    REVERSE = '\033[7m'

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
    WHITE = '\033[97m'
    GRAY = '\033[38;2;156;163;175m'
    LIGHT_GRAY = '\033[38;2;229;231;235m'
    DARK_GRAY = '\033[38;2;75;85;99m'

class Icons:
    SERVER = "🖥️ "
    USERS = "👥 "
    NETWORK = "🌐 "
    TOOLS = "🔧 "
    SHIELD = "🛡️ "
    CHART = "📊 "
    CPU = "⚙️ "
    RAM = "💾 "
    ACTIVE = "🟢"
    INACTIVE = "🔴"
    BACK = "◀ "
    EXIT = "🚪 "
    CLOCK = "🕐 "
    SYSTEM = "💻 "
    UPDATE = "� "
    DOWNLOAD = "📥 "
    KEY = "🔑 "
    LOCK = "🔒 "
    UNLOCK = "🔓 "
    CHECK = "✅ "
    CROSS = "❌ "
    WARNING = "⚠️ "
    INFO = "ℹ️ "
    ROCKET = "🚀 "
    DIAMOND = "💎 "

    BOX_TOP_LEFT = "╭"
    BOX_TOP_RIGHT = "╮"
    BOX_BOTTOM_LEFT = "╰"
    BOX_BOTTOM_RIGHT = "╯"
    BOX_HORIZONTAL = "─"
    BOX_VERTICAL = "│"

# ==================== HELPERS DE UI (RETORNAM STRING) ====================
def gradient_line(width=80, char='═', colors=(MC.PURPLE_GRADIENT, MC.CYAN_GRADIENT, MC.BLUE_GRADIENT)):
    seg = max(1, width // len(colors))
    out = []
    used = 0
    for i, c in enumerate(colors):
        run = seg if i < len(colors) - 1 else (width - used)
        out.append(f"{c}{char * run}")
        used += run
    return "".join(out) + MC.RESET + "\n"

def modern_header():
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    s = []
    s.append(gradient_line(width))
    logo_lines = [
        f"{MC.PURPLE_LIGHT}███╗   ███╗{MC.CYAN_LIGHT}██╗   ██╗{MC.BLUE_LIGHT}██╗  ████████╗{MC.GREEN_LIGHT}██╗███████╗{MC.ORANGE_LIGHT}██╗      {MC.PINK_LIGHT}██████╗ {MC.YELLOW_LIGHT}██╗    ██╗{MC.RESET}",
        f"{MC.PURPLE_GRADIENT}████╗ ████║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║  ╚══██╔══╝{MC.GREEN_GRADIENT}██║██╔════╝{MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██╔═══██╗{MC.YELLOW_GRADIENT}██║    ██║{MC.RESET}",
        f"{MC.PURPLE_GRADIENT}██╔████╔██║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║     ██║   {MC.GREEN_GRADIENT}██║█████╗  {MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██║   ██║{MC.YELLOW_GRADIENT}██║ █╗ ██║{MC.RESET}",
        f"{MC.PURPLE_DARK}██║╚██╔╝██║{MC.CYAN_DARK}██║   ██║{MC.BLUE_DARK}██║     ██║   {MC.GREEN_DARK}██║██╔══╝  {MC.ORANGE_DARK}██║     {MC.RED_GRADIENT}██║   ██║{MC.YELLOW_DARK}██║███╗██║{MC.RESET}",
        f"{MC.PURPLE_DARK}██║ ╚═╝ ██║{MC.CYAN_DARK}╚██████╔╝{MC.BLUE_DARK}███████╗██║   {MC.GREEN_DARK}██║██║     {MC.ORANGE_DARK}███████╗{MC.RED_DARK}╚██████╔╝{MC.YELLOW_DARK}╚███╔███╔╝{MC.RESET}",
        f"{MC.DARK_GRAY}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{MC.RESET}"
    ]
    s.extend(["  " + l + "\n" for l in logo_lines])
    s.append(f"\n{MC.GRAY}{'═' * width}{MC.RESET}\n")
    s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}{'Sistema Avançado de Gerenciamento VPS'.center(width)}{MC.RESET}\n")
    s.append(f"{MC.GRAY}{'═' * width}{MC.RESET}\n\n")
    return "".join(s)

def modern_box(title, content_lines, icon="", primary=MC.CYAN_GRADIENT, secondary=MC.CYAN_LIGHT):
    cols, _ = TerminalManager.size()
    width = max(54, min(cols - 6, 100))
    title_text = f" {icon}{title} " if icon else f" {title} "
    extra = -1 if icon else 0
    header = (f"{primary}{Icons.BOX_TOP_LEFT}{Icons.BOX_HORIZONTAL * 10}"
              f"{secondary}┤{MC.BOLD}{MC.WHITE}{title_text}{MC.RESET}{secondary}├"
              f"{primary}{Icons.BOX_HORIZONTAL * (width - len(title_text) - 12 + extra)}"
              f"{Icons.BOX_TOP_RIGHT}{MC.RESET}\n")
    body = ""
    for line in content_lines:
        clean = re.sub(r'\033\[[0-9;]*m', '', line)
        pad = width - len(clean) - 2
        if pad < 0:
            vis = clean[:width - 5] + "..."
            line = line.replace(clean, vis)
            pad = width - len(vis) - 2
        body += f"{primary}{Icons.BOX_VERTICAL}{MC.RESET} {line}{' ' * pad} {primary}{Icons.BOX_VERTICAL}{MC.RESET}\n"
    footer = f"{primary}{Icons.BOX_BOTTOM_LEFT}{Icons.BOX_HORIZONTAL * width}{Icons.BOX_BOTTOM_RIGHT}{MC.RESET}\n"
    return header + body + footer

def menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, badge=""):
    num = f"{color}{MC.BOLD}[{number}]{MC.RESET}" if number != "0" else f"{MC.RED_GRADIENT}{MC.BOLD}[0]{MC.RESET}"
    b = f" {MC.PURPLE_GRADIENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
    return f"  {num} {icon}{MC.WHITE}{text}{b}{MC.RESET}\n"

def progress_bar(percent, width=18):
    filled = int(percent * width / 100)
    empty = width - filled
    if percent < 30: c = MC.GREEN_GRADIENT
    elif percent < 60: c = MC.YELLOW_GRADIENT
    elif percent < 80: c = MC.ORANGE_GRADIENT
    else: c = MC.RED_GRADIENT
    return f"[{c}{'█' * filled}{MC.DARK_GRAY}{'░' * empty}{MC.RESET}] {c}{percent:5.1f}%{MC.RESET}"

def footer_line(status_msg=""):
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    bar = f"\n{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"
    status = f"{MC.GRAY}MultiFlow{MC.RESET}"
    if status_msg:
        status += f"  {MC.YELLOW_GRADIENT}{status_msg}{MC.RESET}"
    return bar + status + "\n" + f"{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"

# ==================== INFO DO SISTEMA ====================
def monitorar_uso_recursos(intervalo_cpu=0.10):
    try:
        ram = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=intervalo_cpu)
        return {'ram_percent': ram.percent, 'cpu_percent': cpu_percent}
    except Exception:
        return {'ram_percent': 0, 'cpu_percent': 0}

def get_system_info():
    info = {"os_name": "Desconhecido", "ram_percent": 0, "cpu_percent": 0}
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                pairs = [line.strip().split('=', 1) for line in f if '=' in line]
            os_info = dict(pairs)
            info["os_name"] = os_info.get('PRETTY_NAME', 'Linux').strip('"')
        info.update(monitorar_uso_recursos())
    except Exception:
        pass
    return info

def get_system_uptime():
    try:
        with open('/proc/uptime', 'r') as f:
            up = float(f.readline().split()[0])
        d = int(up // 86400)
        h = int((up % 86400) // 3600)
        m = int((up % 3600) // 60)
        if d: return f"{d}d {h}h {m}m"
        if h: return f"{h}h {m}m"
        return f"{m}m"
    except Exception:
        return "N/A"

def get_active_services():
    services = []
    def run_cmd(cmd):
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""
    swapon = run_cmd(['swapon', '--show'])
    if 'zram' in swapon:
        services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} ZRAM{MC.RESET}")
    if '/swapfile' in swapon or 'partition' in swapon:
        services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} SWAP{MC.RESET}")
    if os.path.exists('/etc/openvpn/server.conf'):
        services.append(f"{MC.CYAN_GRADIENT}{Icons.ACTIVE} OpenVPN{MC.RESET}")
    try:
        r = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "active":
            services.append(f"{MC.PURPLE_GRADIENT}{Icons.ACTIVE} BadVPN{MC.RESET}")
    except Exception:
        pass
    try:
        r = subprocess.run(["systemctl", "is-active", "ssh"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "active":
            services.append(f"{MC.ORANGE_GRADIENT}{Icons.ACTIVE} SSH{MC.RESET}")
    except Exception:
        pass
    return services

def system_panel_box():
    info = get_system_info()
    uptime = get_system_uptime()
    os_name = (info['os_name'][:35] + '...') if len(info['os_name']) > 38 else info['os_name']
    ram_bar = progress_bar(info["ram_percent"])
    cpu_bar = progress_bar(info["cpu_percent"])
    services = get_active_services()

    content = [
        f"{MC.CYAN_LIGHT}Sistema:{MC.RESET} {MC.WHITE}{os_name}{MC.RESET}",
        f"{MC.CYAN_LIGHT}RAM:{MC.RESET} {ram_bar}",
        f"{MC.CYAN_LIGHT}CPU:{MC.RESET} {cpu_bar}",
        f"{MC.CYAN_LIGHT}Uptime:{MC.RESET} {MC.WHITE}{uptime}{MC.RESET}",
    ]
    if services:
        line1 = f"{MC.CYAN_LIGHT}Serviços:{MC.RESET} " + " │ ".join(services[:4])
        content.append(line1)
        if len(services) > 4:
            content.append(" " * 13 + " │ ".join(services[4:8]))
    else:
        content.append(f"{MC.CYAN_LIGHT}Serviços:{MC.RESET} {MC.GRAY}Nenhum serviço ativo{MC.RESET}")

    return modern_box("PAINEL DO SISTEMA", content, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

def welcome_line():
    msgs = [
        f"{Icons.ROCKET} Bem-vindo ao MultiFlow!",
        f"{Icons.DIAMOND} Experiência premium no seu terminal.",
        f"{Icons.CHECK} Sistema pronto para uso.",
    ]
    msg = random.choice(msgs)
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    return f"\n{MC.CYAN_GRADIENT}{MC.BOLD}{msg.center(width)}{MC.RESET}\n\n"

# ==================== RENDER DE TELAS COMPLETAS ====================
def build_main_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append(welcome_line())
    s.append(modern_box("MENU PRINCIPAL", [], Icons.DIAMOND, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    s.append(menu_option("1", "Gerenciar Usuários SSH", "", MC.GREEN_DARK))
    s.append(menu_option("2", "Monitor Online", "", MC.GREEN_DARK))
    s.append(menu_option("3", "Gerenciar Conexões", "", MC.GREEN_DARK))
    s.append(menu_option("4", "BadVPN", "", MC.GREEN_DARK))
    s.append(menu_option("5", "Ferramentas", "", MC.GREEN_DARK))
    s.append(menu_option("6", "Servidor de Download", "", MC.GREEN_DARK))
    s.append(menu_option("7", "Atualizar Multiflow", "", MC.ORANGE_GRADIENT, badge="v2"))
    s.append("\n")
    s.append(menu_option("0", "Sair", "", MC.RED_DARK))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_connections_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append("\n")
    s.append(modern_box("GERENCIAR CONEXÕES", [], Icons.NETWORK, MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    s.append("\n")
    s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}Protocolos{MC.RESET}\n")
    s.append(menu_option("1", "OpenVPN", "", MC.GREEN_GRADIENT))
    s.append(menu_option("2", "SlowDNS", "", MC.GREEN_GRADIENT))
    s.append(menu_option("3", "Hysteria", "", MC.GREEN_GRADIENT))
    s.append(menu_option("4", "V2ray", "", MC.GREEN_GRADIENT))
    s.append(menu_option("5", "Xray", "", MC.GREEN_GRADIENT))
    s.append("\n")
    s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}Proxys Multiprotocolo{MC.RESET}\n")
    s.append(menu_option("6", "Multi-Flow Proxy", "", MC.BLUE_GRADIENT))
    s.append(menu_option("7", "Rusty Proxy", "", MC.PURPLE_GRADIENT))
    s.append(menu_option("8", "DragonCore Proxy", "", MC.PURPLE_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_tools_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append("\n")
    s.append(modern_box("FERRAMENTAS DE OTIMIZAÇÃO", [], Icons.TOOLS, MC.ORANGE_GRADIENT, MC.ORANGE_LIGHT))
    s.append("\n")
    # Remover ícones de todas as opções do submenu de ferramentas. O badge
    # "TURBO" permanece para destacar o otimizador.
    s.append(menu_option("1", "Otimizador de VPS", "", MC.GREEN_GRADIENT, badge="TURBO"))
    s.append(menu_option("2", "Bloqueador de Sites", "", MC.RED_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_updater_frame():
    s = []
    s.append(modern_header())
    s.append("\n")
    s.append(modern_box("ATUALIZADOR MULTIFLOW", [
        f"{MC.YELLOW_GRADIENT}{Icons.INFO} Baixar a versão mais recente do GitHub.{MC.RESET}",
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Serviços como BadVPN serão parados.{MC.RESET}",
        f"{MC.RED_GRADIENT}{Icons.WARNING} O programa encerra após a atualização.{MC.RESET}",
        f"{MC.WHITE}{Icons.INFO} Reinicie com 'multiflow' após concluir.{MC.RESET}"
    ], Icons.UPDATE, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append(footer_line())
    return "".join(s)

# ==================== CHECK ROOT ====================
def check_root():
    try:
        if os.geteuid() != 0:
            TerminalManager.enter_alt_screen()
            TerminalManager.render(
                modern_header() +
                modern_box("AVISO DE SEGURANÇA", [
                    f"{MC.RED_GRADIENT}{Icons.WARNING} Este script precisa ser executado como root!{MC.RESET}",
                    f"{MC.YELLOW_GRADIENT}Algumas operações podem falhar sem privilégios adequados.{MC.RESET}"
                ], Icons.SHIELD, MC.RED_GRADIENT, MC.RED_LIGHT) +
                footer_line()
            )
            TerminalManager.before_input()
            resp = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar mesmo assim? (s/n): {MC.RESET}").strip().lower()
            TerminalManager.after_input()
            if resp != 's':
                TerminalManager.leave_alt_screen()
                sys.exit(0)
            return False
        return True
    except AttributeError:
        return True

# ==================== MENUS (COM RENDER ÚNICO POR FRAME) ====================
def ssh_users_main_menu():
    TerminalManager.leave_alt_screen()
    try:
        manusear_usuarios.main()
    finally:
        TerminalManager.enter_alt_screen()

def monitor_online_menu():
    TerminalManager.leave_alt_screen()
    try:
        root = _find_multiflow_root()
        usuarios_online_path = os.path.join(root, 'ferramentas', 'usuarios_online.py')
        subprocess.run([sys.executable, usuarios_online_path], check=True)
    except Exception as e:
        print(f"Erro ao executar Monitor Online: {e}")
    finally:
        TerminalManager.enter_alt_screen()

def conexoes_menu():
    status = ""
    while True:
        TerminalManager.enter_alt_screen()
        TerminalManager.render(build_connections_frame(status))
        TerminalManager.before_input()
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
        TerminalManager.after_input()

        if choice == "1":
            TerminalManager.leave_alt_screen()
            try:
                menu_openvpn.main_menu()
            finally:
                TerminalManager.enter_alt_screen()
            status = "OpenVPN: operação concluída."
        elif choice == "2":
            TerminalManager.leave_alt_screen()
            try:
                root = _find_multiflow_root()
                slowdns_path = os.path.join(root, 'conexoes', 'slowdns.py')
                subprocess.run([sys.executable, slowdns_path], check=True)
            except Exception as e:
                print(f"Erro ao executar SlowDNS: {e}")
            finally:
                TerminalManager.enter_alt_screen()
            status = "SlowDNS: operação concluída."
        elif choice == "3":
            TerminalManager.leave_alt_screen()
            try:
                root = _find_multiflow_root()
                hysteria_path = os.path.join(root, 'conexoes', 'hysteria.py')
                subprocess.run([sys.executable, hysteria_path], check=True)
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
                subprocess.run([sys.executable, v2ray_path], check=True)
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
            except Exception as e:
                print(f"Erro ao executar Xray: {e}")
            finally:
                TerminalManager.enter_alt_screen()
            status = "Xray: operação concluída."
        elif choice == "6":
            TerminalManager.leave_alt_screen()
            try:
                root = _find_multiflow_root()
                multiflowproxy_path = os.path.join(root, 'conexoes', 'multiflowproxy.py')
                subprocess.run([sys.executable, multiflowproxy_path], check=True)
            except Exception as e:
                print(f"Erro ao executar Multi-Flow Proxy: {e}")
            finally:
                TerminalManager.enter_alt_screen()
            status = "Multi-Flow Proxy: operação concluída."
        elif choice == "7":
            TerminalManager.leave_alt_screen()
            try:
                root = _find_multiflow_root()
                proxy_path = os.path.join(root, 'conexoes', 'proxy')
                subprocess.run([proxy_path], check=True)
            except Exception as e:
                print(f"Erro ao executar Rusty Proxy: {e}")
            finally:
                TerminalManager.enter_alt_screen()
            status = "Rusty Proxy: operação concluída."
        elif choice == "8":
            # Correção: Alterado para executar via subprocess o arquivo em /menus/menu_dragonproxy.py,
            # para consistência com outras opções de conexões e evitar dependência de import direto.
            # Isso permite isolamento e execução independente do script.
            TerminalManager.leave_alt_screen()
            try:
                root = _find_multiflow_root()
                dragonproxy_path = os.path.join(root, 'menus', 'menu_dragonproxy.py')
                subprocess.run([sys.executable, dragonproxy_path], check=True)
            except Exception as e:
                print(f"Erro ao executar DragonCore Proxy: {e}")
            finally:
                TerminalManager.enter_alt_screen()
            status = "DragonCore Proxy: operação concluída."
        elif choice == "0":
            return
        else:
            status = "Opção inválida. Tente novamente."

def otimizadorvps_menu():
    TerminalManager.leave_alt_screen()
    try:
        script_real_path = os.path.realpath(__file__)
        script_dir = os.path.dirname(script_real_path)
        otimizador_path = os.path.join(script_dir, 'ferramentas', 'otimizadorvps.py')
        subprocess.run([sys.executable, otimizador_path], check=True)
    except Exception as e:
        print(f"\033[91mErro ao executar o otimizador: {e}\033[0m")
    finally:
        input("Pressione Enter para continuar...")
        TerminalManager.enter_alt_screen()

def ferramentas_menu():
    status = ""
    while True:
        TerminalManager.enter_alt_screen()
        TerminalManager.render(build_tools_frame(status))
        TerminalManager.before_input()
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
        TerminalManager.after_input()

        if choice == "1":
            otimizadorvps_menu()
            status = "Otimizador executado."
        elif choice == "2":
            TerminalManager.leave_alt_screen()
            try:
                menu_bloqueador.main_menu()
            finally:
                TerminalManager.enter_alt_screen()
            status = "Bloqueador executado."
        elif choice == "0":
            return
        else:
            status = "Opção inválida. Tente novamente."

def atualizar_multiflow():
    TerminalManager.enter_alt_screen()
    TerminalManager.render(build_updater_frame())
    TerminalManager.before_input()
    confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar com a atualização? (s/n): {MC.RESET}").strip().lower()
    TerminalManager.after_input()

    if confirm == 's':
        try:
            script_dir = os.path.dirname(os.path.realpath(__file__))
            update_script_path = os.path.join(script_dir, 'update.py')
            # Alterado para o novo caminho do script de atualização
            update_script_path = os.path.join(script_dir, 'ferramentas', 'update.py')
            if not os.path.exists(update_script_path):
                TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} 'update.py' não encontrado!{MC.RESET}\n")
                TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} 'update.py' não encontrado em 'ferramentas'!{MC.RESET}\n")
                time.sleep(2.0)
                return
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(['sudo', sys.executable, update_script_path], check=True)
                print("\nAtualizado com sucesso. Reinicie com: multiflow\n")
                time.sleep(1.0)
                sys.exit(0)
            finally:
                TerminalManager.enter_alt_screen()
        except subprocess.CalledProcessError:
            TerminalManager.enter_alt_screen()
            TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro durante a atualização.{MC.RESET}\n")
            time.sleep(2.0)
        except Exception as e:
            TerminalManager.enter_alt_screen()
            TerminalManager.render(build_updater_frame() + f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro inesperado: {e}{MC.RESET}\n")
            time.sleep(2.0)
    else:
        TerminalManager.render(build_updater_frame() + f"\n{MC.YELLOW_GRADIENT}{Icons.INFO} Atualização cancelada.{MC.RESET}\n")
        time.sleep(1.2)

# ==================== MENU PRINCIPAL ====================
def main_menu():
    check_root()
    TerminalManager.enter_alt_screen()
    status = ""

    while True:
        try:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()

            if choice == "1":
                ssh_users_main_menu()
                status = "Gerenciamento de usuários concluído."
            elif choice == "2":
                monitor_online_menu()
                status = "Monitor Online concluído."
            elif choice == "3":
                conexoes_menu()
                status = "Conexões: operação concluída."
            elif choice == "4":
                TerminalManager.leave_alt_screen()
                try:
                    menu_badvpn.main_menu()
                finally:
                    TerminalManager.enter_alt_screen()
                status = "BadVPN: operação concluída."
            elif choice == "5":
                ferramentas_menu()
                status = "Ferramentas: operação concluída."
            elif choice == "6":
                TerminalManager.leave_alt_screen()
                try:
                    menu_servidor_download.main()
                finally:
                    TerminalManager.enter_alt_screen()
                status = "Servidor de download: operação concluída."
            elif choice == "7":
                atualizar_multiflow()
                status = "Atualizador executado."
            elif choice == "0":
                TerminalManager.render(build_main_frame("Saindo..."))
                time.sleep(0.4)
                break
            else:
                status = "Opção inválida. Pressione 1-7 ou 0 para sair."

        except KeyboardInterrupt:
            TerminalManager.render(build_main_frame("Interrompido pelo usuário."))
            time.sleep(0.5)
            break
        except Exception as e:
            TerminalManager.render(build_main_frame(f"Erro: {e}"))
            time.sleep(1.0)
            break

    TerminalManager.leave_alt_screen()

# ==================== EXECUÇÃO ====================
if __name__ == "__main__":
    main_menu()
