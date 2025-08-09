#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import shutil

# ==================== SISTEMA DE CORES MODERNO ====================
class MC:
    """Modern Colors - Sistema de cores gradiente do Multiflow"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    REVERSE = '\033[7m'

    # Gradientes de cores
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

# ==================== SISTEMA DE ÍCONES ====================
class Icons:
    """Ícones Unicode para interface moderna"""
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
    UPLOAD = "📤 "
    KEY = "🔑 "
    LOCK = "🔒 "
    UNLOCK = "🔓 "
    CHECK = "✅ "
    CROSS = "❌ "
    WARNING = "⚠️ "
    INFO = "ℹ️ "
    ROCKET = "🚀 "
    DIAMOND = "💎 "
    FOLDER = "📁 "
    FILE = "📄 "
    SETTINGS = "⚙️ "
    TRASH = "🗑️ "
    PLUS = "➕ "
    MINUS = "➖ "
    EDIT = "✏️ "
    SAVE = "💾 "
    
    # Box drawing
    BOX_TOP_LEFT = "╭"
    BOX_TOP_RIGHT = "╮"
    BOX_BOTTOM_LEFT = "╰"
    BOX_BOTTOM_RIGHT = "╯"
    BOX_HORIZONTAL = "─"
    BOX_VERTICAL = "│"

# ==================== TERMINAL MANAGER ====================
class TerminalManager:
    """Gerenciador de renderização do terminal"""
    _in_alt = False
    USE_ALT = True
    
    @staticmethod
    def size():
        ts = shutil.get_terminal_size(fallback=(80, 24))
        return ts.columns, ts.lines
    
    @staticmethod
    def clear():
        os.system('cls' if os.name == 'nt' else 'clear')
    
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
    def render(frame_str):
        """Renderiza um frame completo"""
        sys.stdout.write("\033[?25l")  # Hide cursor
        TerminalManager.clear()
        sys.stdout.write("\033[1;1H")
        sys.stdout.write(frame_str)
        sys.stdout.flush()
    
    @staticmethod
    def before_input():
        """Prepara terminal para input"""
        sys.stdout.write("\033[?25h\033[2K\r")  # Show cursor
        sys.stdout.flush()
    
    @staticmethod
    def after_input():
        """Restaura estado após input"""
        sys.stdout.write("\033[?25l")  # Hide cursor
        sys.stdout.flush()

# ==================== HELPERS DE UI ====================
def gradient_line(width=80, char='═', colors=(MC.PURPLE_GRADIENT, MC.CYAN_GRADIENT, MC.BLUE_GRADIENT)):
    """Cria uma linha com gradiente de cores"""
    seg = max(1, width // len(colors))
    out = []
    used = 0
    for i, c in enumerate(colors):
        run = seg if i < len(colors) - 1 else (width - used)
        out.append(f"{c}{char * run}")
        used += run
    return "".join(out) + MC.RESET + "\n"

def modern_box(title, content_lines, icon="", primary=MC.CYAN_GRADIENT, secondary=MC.CYAN_LIGHT):
    """Cria uma caixa moderna com título e conteúdo"""
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
    """Formata uma opção de menu"""
    num = f"{color}{MC.BOLD}[{number}]{MC.RESET}" if number != "0" else f"{MC.RED_GRADIENT}{MC.BOLD}[0]{MC.RESET}"
    b = f" {MC.PURPLE_GRADIENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
    return f"  {num} {icon}{MC.WHITE}{text}{b}{MC.RESET}\n"

def progress_bar(percent, width=18):
    """Cria uma barra de progresso colorida"""
    filled = int(percent * width / 100)
    empty = width - filled
    if percent < 30: 
        c = MC.GREEN_GRADIENT
    elif percent < 60: 
        c = MC.YELLOW_GRADIENT
    elif percent < 80: 
        c = MC.ORANGE_GRADIENT
    else: 
        c = MC.RED_GRADIENT
    return f"[{c}{'█' * filled}{MC.DARK_GRAY}{'░' * empty}{MC.RESET}] {c}{percent:5.1f}%{MC.RESET}"

def footer_line(status_msg=""):
    """Cria linha de rodapé"""
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    bar = f"\n{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"
    status = f"{MC.GRAY}MultiFlow │ Sistema Avançado de Gerenciamento VPS{MC.RESET}"
    if status_msg:
        status += f"  {MC.YELLOW_GRADIENT}{status_msg}{MC.RESET}"
    return bar + status + "\n" + f"{MC.DARK_GRAY}{'─' * width}{MC.RESET}\n"

def simple_header(title):
    """Header simplificado para submenus"""
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    s = []
    s.append(gradient_line(width))
    s.append(f"{MC.CYAN_GRADIENT}{MC.BOLD}{title.center(width)}{MC.RESET}\n")
    s.append(f"{MC.GRAY}{'═' * width}{MC.RESET}\n\n")
    return "".join(s)

# ==================== COMPATIBILIDADE LEGACY ====================
# Mantém compatibilidade com código antigo
Colors = MC  # Alias para compatibilidade

class BoxChars:
    """Compatibilidade com código antigo"""
    TOP_LEFT = Icons.BOX_TOP_LEFT
    TOP_RIGHT = Icons.BOX_TOP_RIGHT
    BOTTOM_LEFT = Icons.BOX_BOTTOM_LEFT
    BOTTOM_RIGHT = Icons.BOX_BOTTOM_RIGHT
    HORIZONTAL = Icons.BOX_HORIZONTAL
    VERTICAL = Icons.BOX_VERTICAL

def clear_screen():
    """Compatibilidade"""
    TerminalManager.clear()

def print_colored_box(title, content_lines=None):
    """Compatibilidade - imprime diretamente"""
    if content_lines is None:
        content_lines = []
    print(modern_box(title, content_lines, primary=MC.CYAN_GRADIENT))

def print_menu_option(number, description, color=None):
    """Compatibilidade - imprime diretamente"""
    if color is None:
        color = MC.CYAN_GRADIENT
    print(menu_option(number, description, color=color), end='')
