#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import shutil

# ====== Compatibilidade: classe Colors antiga (usada por scripts legados) ======
def _supports_color():
    plat = sys.platform
    supported_platform = plat != 'win32' or 'ANSICON' in os.environ
    try:
        is_a_tty = sys.stdout.isatty()
    except AttributeError:
        is_a_tty = False
    return supported_platform and is_a_tty

class Colors:
    _enabled = _supports_color()
    @classmethod
    def _get(cls, code): return code if cls._enabled else ''
    HEADER = property(lambda self: self._get('\033[95m'))
    BLUE = property(lambda self: self._get('\033[94m'))
    CYAN = property(lambda self: self._get('\033[96m'))
    GREEN = property(lambda self: self._get('\033[92m'))
    YELLOW = property(lambda self: self._get('\033[93m'))
    RED = property(lambda self: self._get('\033[91m'))
    WHITE = property(lambda self: self._get('\033[97m'))
    BOLD = property(lambda self: self._get('\033[1m'))
    UNDERLINE = property(lambda self: self._get('\033[4m'))
    END = property(lambda self: self._get('\033[0m'))

class BoxChars:
    if _supports_color():
        TOP_LEFT='╔'; TOP_RIGHT='╗'; BOTTOM_LEFT='╚'; BOTTOM_RIGHT='╝'
        HORIZONTAL='═'; VERTICAL='║'; T_DOWN='╦'; T_UP='╩'; T_RIGHT='╠'; T_LEFT='╣'; CROSS='╬'
    else:
        TOP_LEFT=TOP_RIGHT=BOTTOM_LEFT=BOTTOM_RIGHT='+'
        HORIZONTAL='-'; VERTICAL='|'; T_DOWN=T_UP=T_RIGHT=T_LEFT=CROSS='+'

def visible_length(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', text))

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_centered(text, width=60, char=' '):
    print(text.center(width, char))

def print_colored_box(title, content_lines=None, width=60, title_color=None):
    if content_lines is None: content_lines = []
    col = Colors()
    if title_color is None: title_color = col.CYAN
    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL*(width-2)}{BoxChars.TOP_RIGHT}")
    title_text = f" {title_color}{col.BOLD}{title}{col.END} "
    pad = width - visible_length(title_text) - 2
    lpad = pad//2; rpad = pad-lpad
    print(f"{BoxChars.VERTICAL}{' '*lpad}{title_text}{' '*rpad}{BoxChars.VERTICAL}")
    if content_lines:
        print(f"{BoxChars.T_RIGHT}{BoxChars.HORIZONTAL*(width-2)}{BoxChars.T_LEFT}")
        for line in content_lines:
            maxw = width-4
            vis = visible_length(line)
            if vis>maxw:
                line = line[:maxw-3] + "..."
            pad = width - visible_length(line) - 2
            print(f"{BoxChars.VERTICAL} {line}{' '*pad}{BoxChars.VERTICAL}")
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL*(width-2)}{BoxChars.BOTTOM_RIGHT}")

def print_menu_option(number, description, status=None, color=None, width=60):
    col = Colors()
    if color is None: color = col.WHITE
    number_text = f"{col.BOLD}{color}[{number}]{col.END}"
    option_text = f" {number_text} {description}"
    if status:
        padding = width - visible_length(option_text) - visible_length(status) - 2
        print(f"{BoxChars.VERTICAL}{option_text}{' '*padding}{status} {BoxChars.VERTICAL}")
    else:
        padding = width - visible_length(option_text) - 2
        print(f"{BoxChars.VERTICAL}{option_text}{' '*padding}{BoxChars.VERTICAL}")

# ====== Sistema moderno (estilo do multiflow.py) ======
class MC:
    RESET='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'; ITALIC='\033[3m'; UNDERLINE='\033[4m'; REVERSE='\033[7m'
    PURPLE_GRADIENT='\033[38;2;147;51;234m'; PURPLE_LIGHT='\033[38;2;196;181;253m'; PURPLE_DARK='\033[38;2;107;33;168m'
    CYAN_GRADIENT='\033[38;2;6;182;212m'; CYAN_LIGHT='\033[38;2;165;243;252m'; CYAN_DARK='\033[38;2;14;116;144m'
    GREEN_GRADIENT='\033[38;2;34;197;94m'; GREEN_LIGHT='\033[38;2;134;239;172m'; GREEN_DARK='\033[38;2;22;163;74m'
    ORANGE_GRADIENT='\033[38;2;251;146;60m'; ORANGE_LIGHT='\033[38;2;254;215;170m'; ORANGE_DARK='\033[38;2;234;88;12m'
    RED_GRADIENT='\033[38;2;239;68;68m'; RED_LIGHT='\033[38;2;254;202;202m'; RED_DARK='\033[38;2;185;28;28m'
    YELLOW_GRADIENT='\033[38;2;250;204;21m'; YELLOW_LIGHT='\033[38;2;254;240;138m'; YELLOW_DARK='\033[38;2;202;138;4m'
    BLUE_GRADIENT='\033[38;2;59;130;246m'; BLUE_LIGHT='\033[38;2;191;219;254m'; BLUE_DARK='\033[38;2;29;78;216m'
    PINK_GRADIENT='\033[38;2;236;72;153m'; PINK_LIGHT='\033[38;2;251;207;232m'
    # Aliases solicitados
    HEADER='\033[95m'           # para compatibilidade
    MAGENTA_GRADIENT=HEADER     # alias para corrigir uso de MC.MAGENTA_GRADIENT
    YELLOW='\033[93m'           # alias para corrigir uso de MC.YELLOW
    WHITE='\033[97m'; GRAY='\033[38;2;156;163;175m'; LIGHT_GRAY='\033[38;2;229;231;235m'; DARK_GRAY='\033[38;2;75;85;99m'

class Icons:
    SERVER="🖥️ "; USERS="👥 "; NETWORK="🌐 "; TOOLS="🔧 "; SHIELD="🛡️ "; CHART="📊 "; CPU="⚙️ "; RAM="💾 "
    ACTIVE="🟢"; INACTIVE="🔴"; BACK="◀ "; EXIT="🚪 "; CLOCK="🕐 "; SYSTEM="💻 "; UPDATE="🔄 "; DOWNLOAD="📥 "; UPLOAD="📤 "
    KEY="🔑 "; LOCK="🔒 "; UNLOCK="🔓 "; CHECK="✅ "; CROSS="❌ "; WARNING="⚠️ "; INFO="ℹ️ "; ROCKET="🚀 "; DIAMOND="💎 "
    FOLDER="📁 "; FILE="📄 "; SETTINGS="⚙️ "; TRASH="🗑️ "; PLUS="➕ "; MINUS="➖ "; EDIT="✏️ "; SAVE="💾 "
    BOX_TOP_LEFT="╭"; BOX_TOP_RIGHT="╮"; BOX_BOTTOM_LEFT="╰"; BOX_BOTTOM_RIGHT="╯"; BOX_HORIZONTAL="─"; BOX_VERTICAL="│"

class TerminalManager:
    _in_alt = False; USE_ALT = True
    @staticmethod
    def size():
        ts = shutil.get_terminal_size(fallback=(80, 24)); return ts.columns, ts.lines
    @staticmethod
    def clear():
        sys.stdout.write("\033[2J\033[H"); sys.stdout.flush()
    @staticmethod
    def enter_alt_screen():
        if TerminalManager.USE_ALT and not TerminalManager._in_alt:
            sys.stdout.write("\033[?1049h"); sys.stdout.flush(); TerminalManager._in_alt = True
    @staticmethod
    def leave_alt_screen():
        if TerminalManager._in_alt:
            sys.stdout.write("\033[?1049l"); sys.stdout.flush(); TerminalManager._in_alt = False
    @staticmethod
    def render(frame_str):
        sys.stdout.write("\033[?25l"); TerminalManager.clear(); sys.stdout.write(frame_str); sys.stdout.flush()
    @staticmethod
    def before_input():
        sys.stdout.write("\033[?25h\033[2K\r"); sys.stdout.flush()
    @staticmethod
    def after_input():
        sys.stdout.write("\033[?25l"); sys.stdout.flush()

def gradient_line(width=80, char='═', colors=(MC.PURPLE_GRADIENT, MC.CYAN_GRADIENT, MC.BLUE_GRADIENT)):
    seg = max(1, width // len(colors)); out=[]; used=0
    for i,c in enumerate(colors):
        run = seg if i < len(colors)-1 else (width - used)
        out.append(f"{c}{char*run}"); used += run
    return "".join(out) + MC.RESET + "\n"

def modern_box(title, content_lines, icon="", primary=MC.CYAN_GRADIENT, secondary=MC.CYAN_LIGHT):
    cols,_ = TerminalManager.size(); width = max(54, min(cols-6, 100))
    t = f" {icon}{title} " if icon else f" {title} "
    header = (f"{primary}{Icons.BOX_TOP_LEFT}{Icons.BOX_HORIZONTAL*10}"
              f"{secondary}┤{MC.BOLD}{MC.WHITE}{t}{MC.RESET}{secondary}├"
              f"{primary}{Icons.BOX_HORIZONTAL*(width-len(t)-12)}{Icons.BOX_TOP_RIGHT}{MC.RESET}\n")
    body=""
    for line in (content_lines or []):
        clean = re.sub(r'\033\[[0-9;]*m','',line)
        pad = width - len(clean) - 2
        if pad < 0:
            vis = clean[:width-5] + "..."
            line = line.replace(clean, vis)
            pad = width - len(vis) - 2
        body += f"{primary}{Icons.BOX_VERTICAL}{MC.RESET} {line}{' '*pad} {primary}{Icons.BOX_VERTICAL}{MC.RESET}\n"
    footer = f"{primary}{Icons.BOX_BOTTOM_LEFT}{Icons.BOX_HORIZONTAL*width}{Icons.BOX_BOTTOM_RIGHT}{MC.RESET}\n"
    return header+body+footer

def menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, badge=""):
    num = f"{color}{MC.BOLD}[{number}]{MC.RESET}" if number!="0" else f"{MC.RED_GRADIENT}{MC.BOLD}[0]{MC.RESET}"
    b = f" {MC.PURPLE_GRADIENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
    return f"  {num} {icon}{MC.WHITE}{text}{b}{MC.RESET}\n"

def footer_line(status_msg=""):
    cols,_ = TerminalManager.size(); width = max(60, min(cols-2, 100))
    bar = f"\n{MC.DARK_GRAY}{'─'*width}{MC.RESET}\n"
    status = f"{MC.GRAY}MultiFlow │ Sistema Avançado de Gerenciamento VPS{MC.RESET}"
    if status_msg: status += f"  {MC.YELLOW_GRADIENT}{status_msg}{MC.RESET}"
    return bar + status + "\n" + f"{MC.DARK_GRAY}{'─'*width}{MC.RESET}\n"

def simple_header(title):
    cols,_ = TerminalManager.size(); width = max(60, min(cols-2, 100))
    return "".join([gradient_line(width), f"{MC.CYAN_GRADIENT}{MC.BOLD}{title.center(width)}{MC.RESET}\n", f"{MC.GRAY}{'═'*width}{MC.RESET}\n\n"])
