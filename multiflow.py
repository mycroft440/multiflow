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

INSTALL_SCRIPT = "/opt/multiflow/install.sh"

def execute_install_function(func_name):
    try:
        subprocess.run(["sudo", "bash", "-c", f"source {INSTALL_SCRIPT} && {func_name}"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar a função de instalação {func_name}: {e}")
        return False

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
        "menu_proxysocks": "menus.menu_proxysocks",
        "menu_bloqueador": "menus.menu_bloqueador",
        "menu_servidor_download": "menus.menu_servidor_download",
        "menu_openvpn": "menus.menu_openvpn",
        "multiprotocolo": "conexoes.multiprotocolo",
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
        sys.stderr.write(f"{red}[ERRO] Não foi possível carregar os módulos: {", ".join(still_missing)}{rst}\n")
        sys.stderr.write(f"{yel}Dicas:\n"
                         f" - Verifique a estrutura: {root or '/opt/multiflow'}/menus e /ferramentas existem?\n"
                         f" - Crie __init__.py dentro de 'menus' e 'ferramentas' para habilitar import como pacote.\n"
                         f" - Confirme MULTIFLOW_HOME ou o caminho real do projeto.\n"
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
from menus import menu_badvpn, menu_proxysocks, menu_bloqueador, menu_servidor_download, menu_openvpn  # noqa: F401
from conexoes import multiprotocolo  # noqa: F401

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
    UPDATE = "🔄 "
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
    header = (f"{primary}{Icons.BOX_TOP_LEFT}{Icons.BOX_HORIZONTAL * 10}"
              f"{secondary}┤{MC.BOLD}{MC.WHITE}{title_text}{MC.RESET}{secondary}├"
              f"{primary}{Icons.BOX_HORIZONTAL * (width - len(title_text) - 12)}"
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
    status = f"{MC.GRAY}MultiFlow │ github.com/seu-repo{MC.RESET}"
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
    try:
        if os.path.exists(menu_proxysocks.STATE_FILE):
            with open(menu_proxysocks.STATE_FILE, 'r') as f:
                pid, port = f.read().strip().split(':')
            if psutil.pid_exists(int(pid)):
                services.append(f"{MC.BLUE_GRADIENT}{Icons.ACTIVE} Proxy:{port}{MC.RESET}")
    except Exception:
        pass
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
    now = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")
    os_name = (info['os_name'][:35] + '...') if len(info['os_name']) > 38 else info['os_name']
    ram_bar = progress_bar(info["ram_percent"])
    cpu_bar = progress_bar(info["cpu_percent"])
    services = get_active_services()

    content = [
        f"{MC.CYAN_LIGHT}{Icons.SYSTEM} Sistema:{MC.RESET} {MC.WHITE}{os_name}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.CLOCK} Uptime:{MC.RESET} {MC.WHITE}{uptime}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.RAM} RAM:{MC.RESET} {ram_bar}",
        f"{MC.CYAN_LIGHT}{Icons.CPU} CPU:{MC.RESET} {cpu_bar}",
    ]
    if services:
        line1 = f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços Ativos:{MC.RESET} "
        # Divide os serviços em linhas para caber na caixa
        current_line_len = len(re.sub(r'\033\[[0-9;]*m', '', line1))
        for i, svc in enumerate(services):
            clean_svc = re.sub(r'\033\[[0-9;]*m', '', svc)
            if current_line_len + len(clean_svc) + 2 > 50 and i > 0: # 50 é um valor aproximado para a largura da caixa
                content.append(line1)
                line1 = " " * (len(re.sub(r'\033\[[0-9;]*m', '', f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços Ativos:{MC.RESET} ")))
                current_line_len = len(re.sub(r'\033\[[0-9;]*m', '', line1))
            line1 += f"{svc}  "
            current_line_len += len(clean_svc) + 2
        content.append(line1)

    return modern_box("STATUS DO SISTEMA", content, Icons.SERVER, MC.GREEN_GRADIENT, MC.GREEN_LIGHT)

# ==================== MENUS ====================
def build_main_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append("\n")
    s.append(modern_box("MENU PRINCIPAL", [], Icons.TOOLS, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    s.append(menu_option("1", "Gerenciar Usuários", Icons.USERS, MC.CYAN_GRADIENT))
    s.append(menu_option("2", "Gerenciar Conexões", Icons.NETWORK, MC.GREEN_GRADIENT))
    s.append(menu_option("3", "Ferramentas", Icons.TOOLS, MC.ORANGE_GRADIENT))
    s.append(menu_option("4", "Atualizar Sistema", Icons.UPDATE, MC.BLUE_GRADIENT))
    s.append(menu_option("0", "Sair", Icons.EXIT, MC.RED_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_connections_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append("\n")
    s.append(modern_box("GERENCIAR CONEXÕES", [], Icons.NETWORK, MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    s.append("\n")
    s.append(menu_option("1", "OpenVPN", Icons.LOCK, MC.GREEN_GRADIENT))
    s.append(menu_option("2", "RustyProxy", Icons.SHIELD, MC.RED_GRADIENT))
    s.append(menu_option("3", "Dtunnel Proxy", Icons.UNLOCK, MC.BLUE_GRADIENT))
    s.append(menu_option("4", "SlowDNS", Icons.NETWORK, MC.YELLOW_GRADIENT))
    s.append(menu_option("5", "ProxySocks", Icons.UNLOCK, MC.BLUE_GRADIENT))
    s.append(menu_option("6", "Multiprotocolo", Icons.NETWORK, MC.ORANGE_GRADIENT))
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_tools_frame(status_msg=""):
    s = []
    s.append(modern_header())
    s.append(system_panel_box())
    s.append("\n")
    s.append(modern_box("FERRAMENTAS", [], Icons.TOOLS, MC.ORANGE_GRADIENT, MC.ORANGE_LIGHT))
    s.append("\n")
    s.append(menu_option("1", "Gerenciar BadVPN", Icons.SHIELD, MC.PURPLE_GRADIENT))
    s.append(menu_option("2", "Bloqueador de Sites", Icons.LOCK, MC.RED_GRADIENT))
    s.append(menu_option("3", "Servidor de Download", Icons.DOWNLOAD, MC.BLUE_GRADIENT))
    s.append(menu_option("4", "Otimizador de VPS", Icons.ROCKET, MC.GREEN_GRADIENT))
    s.append(menu_option("5", "Gerenciar ZRAM", Icons.RAM, MC.CYAN_GRADIENT))
    s.append(menu_option("6", "Gerenciar SWAP", Icons.RAM, MC.CYAN_GRADIENT))
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

# ==================== LÓGICA DOS MENUS ====================
def main_menu():
    status = ""
    while True:
        TerminalManager.render(build_main_frame(status))
        TerminalManager.before_input()
        choice = input(f"{MC.WHITE}{MC.BOLD}Escolha uma opção: {MC.RESET}")
        TerminalManager.after_input()

        if choice == "1":
            manusear_usuarios.gerenciar_usuarios_menu()
            status = "Gerenciamento de Usuários: operação concluída."
        elif choice == "2":
            conexoes_menu()
            status = "Gerenciamento de Conexões: operação concluída."
        elif choice == "3":
            ferramentas_menu()
            status = "Ferramentas: operação concluída."
        elif choice == "4":
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(["bash", "/opt/multiflow/ferramentas/update.py"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "Atualização do Sistema: operação concluída."
        elif choice == "0":
            break
        else:
            status = f"{MC.RED_GRADIENT}Opção inválida: {choice}. Tente novamente.{MC.RESET}"
        time.sleep(0.5)
    TerminalManager.leave_alt_screen()

def conexoes_menu():
    status = ""
    while True:
        TerminalManager.render(build_connections_frame(status))
        TerminalManager.before_input()
        choice = input(f"{MC.WHITE}{MC.BOLD}Escolha uma opção: {MC.RESET}")
        TerminalManager.after_input()

        if choice == "1":
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(["bash", "/opt/multiflow/conexoes/openvpn.sh"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "OpenVPN: operação concluída."
        elif choice == "2":
            TerminalManager.leave_alt_screen()
            try:
                # Check if RustyProxy is installed
                if not os.path.exists("/opt/rustyproxy/proxy"):
                    print(f"{MC.YELLOW_GRADIENT}Instalando RustyProxy...{MC.RESET}")
                    # This part needs to be implemented as a function
                    # For now, we'll simulate the installation
                    subprocess.run(["bash", "/opt/multiflow/install_rustyproxy.sh"], check=True)
                    print(f"{MC.GREEN_GRADIENT}RustyProxy instalado com sucesso!{MC.RESET}")
                    time.sleep(2)
                subprocess.run(["bash", "/opt/rustyproxy/menu"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "RustyProxy: operação concluída."
        elif choice == "3":
            TerminalManager.leave_alt_screen()
            try:
                # Check if DtunnelProxy is installed
                if not os.path.exists("/opt/multiflow/DtunnelProxy/dtmenu"):
                    print(f"{MC.YELLOW_GRADIENT}Instalando Dtunnel Proxy...{MC.RESET}")
                    # This part needs to be implemented as a function
                    # For now, we'll simulate the installation
                    subprocess.run(["bash", "/opt/multiflow/install_dtunnelproxy.sh"], check=True)
                    print(f"{MC.GREEN_GRADIENT}Dtunnel Proxy instalado com sucesso!{MC.RESET}")
                    time.sleep(2)
                subprocess.run(["bash", "/opt/multiflow/DtunnelProxy/dtmenu"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "Dtunnel Proxy: operação concluída."
        elif choice == "4":
            TerminalManager.leave_alt_screen()
            try:
                # Check if SlowDNS is installed
                if not os.path.exists("/opt/multiflow/Slowdns/slowdns"):
                    print(f"{MC.YELLOW_GRADIENT}Instalando SlowDNS...{MC.RESET}")
                    # This part needs to be implemented as a function
                    # For now, we'll simulate the installation
                    subprocess.run(["bash", "/opt/multiflow/install_slowdns.sh"], check=True)
                    elif choice == "2":
            # RustyProxy
            if not os.path.exists("/opt/rustyproxy/menu"):
                print(f"{MC.YELLOW_GRADIENT}Instalando RustyProxy...{MC.RESET}")
                if execute_install_function("install_rustyproxy"):
                    print(f"{MC.GREEN_GRADIENT}RustyProxy instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do RustyProxy.{MC.RESET}")
                    input("Pressione Enter para continuar...")
              elif choice == "2":
            # RustyProxy
            if not os.path.exists("/opt/rustyproxy/menu"):
                print(f"{MC.YELLOW_GRADIENT}Instalando RustyProxy...{MC.RESET}")
                if execute_install_function("install_rustyproxy"):
                    print(f"{MC.GREEN_GRADIENT}RustyProxy instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do RustyProxy.{MC.RESET}")
                    input("Pressione Enter para continuar...")
                    continue
            subprocess.run(["sudo", "bash", "/opt/rustyproxy/menu"])    elif choice == "3":
            # Dtunnel Proxy
            if not os.path.exists("/opt/multiflow/DtunnelProxy/dtmenu"):
                print(f"{MC.YELLOW_GRADIENT}Instalando Dtunnel Proxy...{MC.RESET}")
                if execute_install_function("install_dtunnelproxy"):
                    print(f"{MC.GREEN_GRADIENT}Dtunnel Proxy instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do Dtunnel Proxy.{MC.RESET}")
                    input("Pressione Enter para continuar...")
                 elif choice == "3":
            # Dtunnel Proxy
            if not os.path.exists("/opt/multiflow/DtunnelProxy/dtmenu"):
                print(f"{MC.YELLOW_GRADIENT}Instalando Dtunnel Proxy...{MC.RESET}")
                if execute_install_function("install_dtunnelproxy"):
                    print(f"{MC.GREEN_GRADIENT}Dtunnel Proxy instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do Dtunnel Proxy.{MC.RESET}")
                    input("Pressione Enter para continuar...")
                    continue
            subprocess.run(["sudo", "bash", "/opt/multiflow/DtunnelProxy/dtmenu"]) elif choice == "4":
            # SlowDNS
            if not os.path.exists("/opt/multiflow/Slowdns/dnstt-installer.sh"):
                print(f"{MC.YELLOW_GRADIENT}Instalando SlowDNS...{MC.RESET}")
                if execute_install_function("install_slowdns"):
                    print(f"{MC.GREEN_GRADIENT}SlowDNS instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do SlowDNS.{MC.RESET}")
                    input("Pressione Enter para continuar...")
             elif choice == "4":
            # SlowDNS
            if not os.path.exists("/opt/multiflow/Slowdns/dnstt-installer.sh"):
                print(f"{MC.YELLOW_GRADIENT}Instalando SlowDNS...{MC.RESET}")
                if execute_install_function("install_slowdns"):
                    print(f"{MC.GREEN_GRADIENT}SlowDNS instalado com sucesso!{MC.RESET}")
                else:
                    print(f"{MC.RED_GRADIENT}Falha na instalação do SlowDNS.{MC.RESET}")
                    input("Pressione Enter para continuar...")
                    continue
            subprocess.run(["sudo", "bash", "/opt/multiflow/Slowdns/dnstt-installer.sh"])     elif choice == "5":
            menu_proxysocks.proxysocks_menu()
            status = "ProxySocks: operação concluída."
        elif choice == "6":
            multiprotocolo.multiprotocolo_menu()
            status = "Multiprotocolo: operação concluída."      elif choice == "0":
            return
        else:
            status = f"{MC.RED_GRADIENT}Opção inválida: {choice}. Tente novamente.{MC.RESET}"
        time.sleep(0.5)

def ferramentas_menu():
    status = ""
    while True:
        TerminalManager.render(build_tools_frame(status))
        TerminalManager.before_input()
        choice = input(f"{MC.WHITE}{MC.BOLD}Escolha uma opção: {MC.RESET}")
        TerminalManager.after_input()

        if choice == "1":
            menu_badvpn.badvpn_menu()
            status = "Gerenciamento de BadVPN: operação concluída."
        elif choice == "2":
            menu_bloqueador.bloqueador_menu()
            status = "Bloqueador de Sites: operação concluída."
        elif choice == "3":
            menu_servidor_download.servidor_download_menu()
            status = "Servidor de Download: operação concluída."
        elif choice == "4":
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(["python3", "/opt/multiflow/ferramentas/otimizadorvps.py"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "Otimizador de VPS: operação concluída."
        elif choice == "5":
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(["python3", "/opt/multiflow/ferramentas/zram.py"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "Gerenciamento de ZRAM: operação concluída."
        elif choice == "6":
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(["python3", "/opt/multiflow/ferramentas/swap.py"], check=True)
            finally:
                TerminalManager.enter_alt_screen()
            status = "Gerenciamento de SWAP: operação concluída."
        elif choice == "0":
            return
        else:
            status = f"{MC.RED_GRADIENT}Opção inválida: {choice}. Tente novamente.{MC.RESET}"
        time.sleep(0.5)

# ==================== INÍCIO DA APLICAÇÃO ====================
if __name__ == "__main__":
    # Verifica se o script está sendo executado como root
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este script precisa ser executado como root. Use 'sudo python3 {sys.argv[0]}'.{MC.RESET}")
        sys.exit(1)

    TerminalManager.enter_alt_screen()
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{MC.YELLOW_GRADIENT}Saindo...{MC.RESET}")
    finally:
        TerminalManager.leave_alt_screen()
