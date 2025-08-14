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
        sys.stderr.write(f"{red}[ERRO] Não foi possível carregar os módulos: {', '.join(still_missing)}{rst}\n")
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
