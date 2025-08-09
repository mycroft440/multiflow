#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
sys.path.append("/opt/multiflow")
import os
import time
import re
import subprocess
import psutil
import shutil
from datetime import datetime
import random

# Importando os módulos necessários no início
try:
    from ferramentas import manusear_usuarios
    from menus import menu_badvpn
    from menus import menu_proxysocks
    from menus import menu_bloqueador
    from menus import menu_servidor_download
except ImportError as e:
    print(f"\033[91mErro: Módulo '{e.name}' não encontrado.\033[0m")
    print(f"\033[93mCertifique-se de que todos os ficheiros .py estão no mesmo diretório que este script.\033[0m")
    sys.exit(1)

# Opcional: funções existentes no projeto (não usadas aqui, mas mantidas)
try:
    from menus.menu_style_utils import Colors, BoxChars, visible_length, clear_screen, print_colored_box, print_menu_option
except Exception:
    pass

# ==================== GERENCIAMENTO DO TERMINAL ====================

class TerminalManager:
    _in_alt = False

    @staticmethod
    def size():
        ts = shutil.get_terminal_size(fallback=(80, 24))
        return ts.columns, ts.lines

    @staticmethod
    def enter_alt_screen():
        if not TerminalManager._in_alt:
            # Entrar no buffer alternativo, ir para home e limpar
            sys.stdout.write("\033[?1049h\033[H\033[2J\033[3J")
            sys.stdout.write("\033[?25l")  # Oculta cursor
            sys.stdout.flush()
            TerminalManager._in_alt = True

    @staticmethod
    def leave_alt_screen():
        # Mostra cursor e sai do buffer alternativo
        if TerminalManager._in_alt:
            sys.stdout.write("\033[?25h")
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            TerminalManager._in_alt = False

    @staticmethod
    def hard_clear():
        """
        Limpa completamente a tela de forma agressiva, cobrindo casos onde 2J/3J
        não apagam o que já foi desenhado e o novo frame possui menos linhas.
        """
        cols, lines = TerminalManager.size()
        # Reset de atributos, home, limpar tela e scrollback
        sys.stdout.write("\033[0m\033[H\033[2J\033[3J")
        # Sobrescreve todo o viewport com espaços (garante remoção de resquícios)
        blank_line = " " * cols
        buf = []
        for _ in range(lines):
            buf.append(blank_line)
        sys.stdout.write("\n".join(buf))
        # Volta para o topo e limpa de novo para garantir
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()
        # Pequena pausa para terminais remotos (SSH/tmux) processarem
        time.sleep(0.01)

    @staticmethod
    def begin_frame():
        # Oculta cursor e limpa a tela agressivamente antes de redesenhar
        sys.stdout.write("\033[?25l")
        TerminalManager.hard_clear()

    @staticmethod
    def end_frame():
        # Garante atributos resetados e cursor visível após o frame, mas
        # mantemos o cursor oculto até input para evitar flicker de redesenho
        sys.stdout.write("\033[0m")
        sys.stdout.flush()

    @staticmethod
    def before_input():
        # Antes de pedir entrada ao usuário, garante cursor visível
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    @staticmethod
    def after_input():
        # Após entrada, podemos ocultar novamente para o redesenho
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

# ==================== CORES E ESTILOS MODERNOS ====================
class ModernColors:
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

MC = ModernColors()

# ==================== ÍCONES ====================
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

# ==================== UI HELPERS ====================
def print_gradient_line(width=80, char='═',
                        colors=(MC.PURPLE_GRADIENT, MC.CYAN_GRADIENT, MC.BLUE_GRADIENT)):
    seg = max(1, width // len(colors))
    out = []
    consumed = 0
    for i, c in enumerate(colors):
        if i == len(colors) - 1:
            run = width - consumed
        else:
            run = seg
        consumed += run
        out.append(f"{c}{char * run}")
    sys.stdout.write("".join(out) + MC.RESET + "\n")

def print_modern_header():
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    print_gradient_line(width)
    logo_lines = [
        f"{MC.PURPLE_LIGHT}███╗   ███╗{MC.CYAN_LIGHT}██╗   ██╗{MC.BLUE_LIGHT}██╗  ████████╗{MC.GREEN_LIGHT}██╗███████╗{MC.ORANGE_LIGHT}██╗      {MC.PINK_LIGHT}██████╗ {MC.YELLOW_LIGHT}██╗    ██╗",
        f"{MC.PURPLE_GRADIENT}████╗ ████║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║  ╚══██╔══╝{MC.GREEN_GRADIENT}██║██╔════╝{MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██╔═══██╗{MC.YELLOW_GRADIENT}██║    ██║",
        f"{MC.PURPLE_GRADIENT}██╔████╔██║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║     ██║   {MC.GREEN_GRADIENT}██║█████╗  {MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██║   ██║{MC.YELLOW_GRADIENT}██║ █╗ ██║",
        f"{MC.PURPLE_DARK}██║╚██╔╝██║{MC.CYAN_DARK}██║   ██║{MC.BLUE_DARK}██║     ██║   {MC.GREEN_DARK}██║██╔══╝  {MC.ORANGE_DARK}██║     {MC.RED_GRADIENT}██║   ██║{MC.YELLOW_DARK}██║███╗██║",
        f"{MC.PURPLE_DARK}██║ ╚═╝ ██║{MC.CYAN_DARK}╚██████╔╝{MC.BLUE_DARK}███████╗██║   {MC.GREEN_DARK}██║██║     {MC.ORANGE_DARK}███████╗{MC.RED_DARK}╚██████╔╝{MC.YELLOW_DARK}╚███╔███╔╝",
        f"{MC.DARK_GRAY}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{MC.RESET}"
    ]
    for line in logo_lines:
        sys.stdout.write("  " + line + "\n")
    sys.stdout.write(f"\n{MC.GRAY}{'═' * width}{MC.RESET}\n")
    sys.stdout.write(f"{MC.CYAN_GRADIENT}{MC.BOLD}{'Sistema Avançado de Gerenciamento VPS'.center(width)}{MC.RESET}\n")
    sys.stdout.write(f"{MC.GRAY}{'═' * width}{MC.RESET}\n\n")

def print_modern_box(title, content, icon="", primary_color=MC.CYAN_GRADIENT, secondary_color=MC.CYAN_LIGHT):
    cols, _ = TerminalManager.size()
    width = max(54, min(cols - 6, 100))
    title_text = f" {icon}{title} " if icon else f" {title} "
    header = (f"{primary_color}{Icons.BOX_TOP_LEFT}{Icons.BOX_HORIZONTAL * 10}"
              f"{secondary_color}┤{MC.BOLD}{MC.WHITE}{title_text}{MC.RESET}{secondary_color}├"
              f"{primary_color}{Icons.BOX_HORIZONTAL * (width - len(title_text) - 12)}"
              f"{Icons.BOX_TOP_RIGHT}{MC.RESET}")
    sys.stdout.write(header + "\n")

    if content:
        for line in content:
            clean = re.sub(r'\033\[[0-9;]*m', '', line)
            pad = width - len(clean) - 2
            if pad < 0:
                # Trunca visualmente se necessário
                visible = clean[:width - 5] + "..."
                line = line.replace(clean, visible)
                pad = width - len(visible) - 2
            sys.stdout.write(f"{primary_color}{Icons.BOX_VERTICAL}{MC.RESET} {line}{' ' * pad} {primary_color}{Icons.BOX_VERTICAL}{MC.RESET}\n")

    footer = f"{primary_color}{Icons.BOX_BOTTOM_LEFT}{Icons.BOX_HORIZONTAL * width}{Icons.BOX_BOTTOM_RIGHT}{MC.RESET}"
    sys.stdout.write(footer + "\n")

def print_modern_menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, badge=""):
    num_display = f"{color}{MC.BOLD}[{number}]{MC.RESET}" if number != "0" else f"{MC.RED_GRADIENT}{MC.BOLD}[0]{MC.RESET}"
    badge_text = f" {MC.PURPLE_GRADIENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
    sys.stdout.write(f"  {num_display} {icon}{MC.WHITE}{text}{badge_text}{MC.RESET}\n")

def create_progress_bar(percent, width=18):
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

# ==================== SISTEMA ====================
def monitorar_uso_recursos(intervalo_cpu=0.45):
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
        d = int(up // 86400); h = int((up % 86400) // 3600); m = int((up % 3600) // 60)
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

    # ProxySocks
    try:
        if os.path.exists(menu_proxysocks.STATE_FILE):
            with open(menu_proxysocks.STATE_FILE, 'r') as f:
                pid, port = f.read().strip().split(':')
            if psutil.pid_exists(int(pid)):
                services.append(f"{MC.BLUE_GRADIENT}{Icons.ACTIVE} Proxy:{port}{MC.RESET}")
    except Exception:
        pass

    # OpenVPN
    if os.path.exists('/etc/openvpn/server.conf'):
        services.append(f"{MC.CYAN_GRADIENT}{Icons.ACTIVE} OpenVPN{MC.RESET}")

    # BadVPN
    try:
        r = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "active":
            services.append(f"{MC.PURPLE_GRADIENT}{Icons.ACTIVE} BadVPN{MC.RESET}")
    except Exception:
        pass

    # SSH
    try:
        r = subprocess.run(["systemctl", "is-active", "ssh"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "active":
            services.append(f"{MC.ORANGE_GRADIENT}{Icons.ACTIVE} SSH{MC.RESET}")
    except Exception:
        pass

    return services

def show_combined_system_panel():
    info = get_system_info()
    uptime = get_system_uptime()
    now = datetime.now()
    dt = f"{now:%d/%m/%Y} - {now:%H:%M:%S}"
    os_name = (info['os_name'][:35] + '...') if len(info['os_name']) > 38 else info['os_name']
    ram_bar = create_progress_bar(info["ram_percent"])
    cpu_bar = create_progress_bar(info["cpu_percent"])
    services = get_active_services()

    content = [
        f"{MC.CYAN_LIGHT}{Icons.SYSTEM} Sistema:{MC.RESET} {MC.White if hasattr(MC,'White') else MC.WHITE}{os_name}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.CLOCK} Uptime:{MC.RESET} {MC.WHITE}{uptime}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.RAM} RAM:{MC.RESET} {ram_bar}",
        f"{MC.CYAN_LIGHT}{Icons.CPU} CPU:{MC.RESET} {cpu_bar}",
    ]
    if services:
        line1 = f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços:{MC.RESET} " + " │ ".join(services[:4])
        content.append(line1)
        if len(services) > 4:
            content.append(" " * 13 + " │ ".join(services[4:8]))
    else:
        content.append(f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços:{MC.RESET} {MC.GRAY}Nenhum serviço ativo{MC.RESET}")

    content.append(f"{MC.CYAN_LIGHT}📅 Data/Hora:{MC.RESET} {MC.WHITE}{dt}{MC.RESET}")
    print_modern_box("PAINEL DO SISTEMA", content, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

def show_welcome_message():
    msgs = [
        f"{Icons.ROCKET} Bem-vindo ao MultiFlow!",
        f"{Icons.DIAMOND} Experiência premium no seu terminal.",
        f"{Icons.CHECK} Sistema pronto para uso.",
    ]
    msg = random.choice(msgs)
    cols, _ = TerminalManager.size()
    width = max(60, min(cols - 2, 100))
    sys.stdout.write(f"\n{MC.CYAN_GRADIENT}{MC.BOLD}{msg.center(width)}{MC.RESET}\n\n")

def check_root():
    try:
        if os.geteuid() != 0:
            TerminalManager.begin_frame()
            print_modern_header()
            print_modern_box("AVISO DE SEGURANÇA", [
                f"{MC.RED_GRADIENT}{Icons.WARNING} Este script precisa ser executado como root!{MC.RESET}",
                f"{MC.YELLOW_GRADIENT}Algumas operações podem falhar sem privilégios adequados.{MC.RESET}"
            ], Icons.SHIELD, MC.RED_GRADIENT, MC.RED_LIGHT)
            TerminalManager.before_input()
            resp = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar mesmo assim? (s/n): {MC.RESET}").strip().lower()
            TerminalManager.after_input()
            if resp != 's':
                TerminalManager.begin_frame()
                sys.stdout.write(f"\n{MC.GREEN_GRADIENT}Saindo...{MC.RESET}\n")
                TerminalManager.end_frame()
                time.sleep(0.6)
                TerminalManager.leave_alt_screen()
                sys.exit(0)
            return False
        return True
    except AttributeError:
        # alguns ambientes não possuem os.geteuid (Windows)
        return True

# ==================== MENUS ====================
def ssh_users_main_menu():
    TerminalManager.begin_frame()
    # Delega ao módulo, que pode usar seu próprio desenho
    TerminalManager.end_frame()
    menu_return = None
    try:
        menu_return = manusear_usuarios.main()
    finally:
        # Ao voltar, garantimos limpeza completa
        TerminalManager.begin_frame()
        TerminalManager.end_frame()
    return menu_return

def conexoes_menu():
    while True:
        TerminalManager.begin_frame()
        print_modern_header()
        show_combined_system_panel()
        sys.stdout.write("\n")
        print_modern_box("GERENCIAR CONEXÕES", [], Icons.NETWORK, MC.CYAN_GRADIENT, MC.CYAN_LIGHT)
        sys.stdout.write("\n")
        print_modern_menu_option("1", "Gerenciar OpenVPN", Icons.LOCK, MC.GREEN_GRADIENT)
        print_modern_menu_option("2", "ProxySocks (Simples)", Icons.UNLOCK, MC.BLUE_GRADIENT)
        sys.stdout.write("\n")
        print_modern_menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT)

        TerminalManager.end_frame()
        TerminalManager.before_input()
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
        TerminalManager.after_input()

        if choice == "1":
            TerminalManager.begin_frame()
            try:
                script_real_path = os.path.realpath(__file__)
                script_dir = os.path.dirname(script_real_path)
                openvpn_script_path = os.path.join(script_dir, 'conexoes', 'openvpn.sh')
                if not os.path.exists(openvpn_script_path):
                    sys.stdout.write(f"{MC.RED_GRADIENT}Erro: 'conexoes/openvpn.sh' não encontrado.{MC.RESET}\n")
                    TerminalManager.end_frame()
                    time.sleep(2.2)
                else:
                    os.chmod(openvpn_script_path, 0o755)
                    TerminalManager.end_frame()
                    # Sai do alt screen temporariamente para rodar o shell script de forma limpa
                    TerminalManager.leave_alt_screen()
                    try:
                        subprocess.run(['bash', openvpn_script_path], check=True)
                    finally:
                        TerminalManager.enter_alt_screen()
            except Exception as e:
                TerminalManager.enter_alt_screen()
                TerminalManager.begin_frame()
                sys.stdout.write(f"{MC.RED_GRADIENT}Erro: {e}{MC.RESET}\n")
                TerminalManager.end_frame()
                time.sleep(2.0)

        elif choice == "2":
            TerminalManager.leave_alt_screen()
            try:
                menu_proxysocks.main()
            finally:
                TerminalManager.enter_alt_screen()

        elif choice == "0":
            break
        else:
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida!{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(1.0)

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
    while True:
        TerminalManager.begin_frame()
        print_modern_header()
        show_combined_system_panel()
        sys.stdout.write("\n")
        print_modern_box("FERRAMENTAS DE OTIMIZAÇÃO", [], Icons.TOOLS, MC.ORANGE_GRADIENT, MC.ORANGE_LIGHT)
        sys.stdout.write("\n")
        print_modern_menu_option("1", "Otimizador de VPS", Icons.ROCKET, MC.GREEN_GRADIENT, badge="TURBO")
        print_modern_menu_option("2", "Bloqueador de Sites", Icons.SHIELD, MC.RED_GRADIENT)
        sys.stdout.write("\n")
        print_modern_menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT)
        TerminalManager.end_frame()

        TerminalManager.before_input()
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
        TerminalManager.after_input()

        if choice == "1":
            otimizadorvps_menu()
        elif choice == "2":
            TerminalManager.leave_alt_screen()
            try:
                menu_bloqueador.main_menu()
            finally:
                TerminalManager.enter_alt_screen()
        elif choice == "0":
            break
        else:
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida!{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(1.0)

def atualizar_multiflow():
    TerminalManager.begin_frame()
    print_modern_header()
    sys.stdout.write("\n")
    print_modern_box("ATUALIZADOR MULTIFLOW", [
        f"{MC.YELLOW_GRADIENT}{Icons.INFO} Este processo irá baixar a versão mais recente do GitHub.{MC.RESET}",
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Serviços ativos como BadVPN e ProxySocks serão parados.{MC.RESET}",
        f"{MC.RED_GRADIENT}{Icons.WARNING} O programa será encerrado após a atualização.{MC.RESET}",
        f"{MC.WHITE}{Icons.INFO} Você precisará iniciá-lo novamente com 'multiflow'.{MC.RESET}"
    ], Icons.UPDATE, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)
    TerminalManager.end_frame()

    TerminalManager.before_input()
    confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar com a atualização? (s/n): {MC.RESET}").strip().lower()
    TerminalManager.after_input()

    if confirm == 's':
        try:
            script_dir = os.path.dirname(os.path.realpath(__file__))
            update_script_path = os.path.join(script_dir, 'update.py')
            if not os.path.exists(update_script_path):
                TerminalManager.begin_frame()
                sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro: 'update.py' não encontrado!{MC.RESET}\n")
                TerminalManager.end_frame()
                time.sleep(2.5)
                return

            # Sair do alt screen para rodar atualização com I/O limpo
            TerminalManager.leave_alt_screen()
            try:
                subprocess.run(['sudo', sys.executable, update_script_path], check=True)
                print("\nAtualizado com sucesso. Reinicie com: multiflow\n")
                time.sleep(1.0)
                sys.exit(0)
            finally:
                # Caso update.py retorne sem sair, reentra (se ainda aqui)
                try:
                    TerminalManager.enter_alt_screen()
                except Exception:
                    pass

        except subprocess.CalledProcessError:
            TerminalManager.enter_alt_screen()
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Ocorreu um erro durante a atualização.{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(2.0)
        except Exception as e:
            TerminalManager.enter_alt_screen()
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro inesperado: {e}{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(2.5)
    else:
        TerminalManager.begin_frame()
        sys.stdout.write(f"\n{MC.YELLOW_GRADIENT}{Icons.INFO} Atualização cancelada.{MC.RESET}\n")
        TerminalManager.end_frame()
        time.sleep(1.2)

# ==================== MENU PRINCIPAL ====================
def main_menu():
    check_root()
    TerminalManager.enter_alt_screen()

    while True:
        try:
            TerminalManager.begin_frame()
            print_modern_header()
            show_combined_system_panel()
            show_welcome_message()

            print_modern_box("MENU PRINCIPAL", [], Icons.DIAMOND, MC.BLUE_GRADIENT, MC.BLUE_LIGHT)
            sys.stdout.write("\n")
            print_modern_menu_option("1", "Gerenciar Usuários SSH", Icons.USERS, MC.GREEN_GRADIENT)
            print_modern_menu_option("2", "Gerenciar Conexões", Icons.NETWORK, MC.CYAN_GRADIENT)
            print_modern_menu_option("3", "BadVPN", Icons.SERVER, MC.PURPLE_GRADIENT)
            print_modern_menu_option("4", "Ferramentas", Icons.TOOLS, MC.ORANGE_GRADIENT)
            print_modern_menu_option("5", "Atualizar Multiflow", Icons.UPDATE, MC.YELLOW_GRADIENT, badge="v2")
            print_modern_menu_option("6", "Servidor de Download", Icons.DOWNLOAD, MC.PINK_LIGHT if hasattr(MC, 'PINK_LIGHT') else MC.CYAN_LIGHT)
            sys.stdout.write("\n")
            print_modern_menu_option("0", "Sair", Icons.EXIT, MC.RED_GRADIENT)
            TerminalManager.end_frame()

            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()

            if choice == "1":
                ssh_users_main_menu()
            elif choice == "2":
                conexoes_menu()
            elif choice == "3":
                TerminalManager.leave_alt_screen()
                try:
                    menu_badvpn.main_menu()
                finally:
                    TerminalManager.enter_alt_screen()
            elif choice == "4":
                ferramentas_menu()
            elif choice == "5":
                atualizar_multiflow()
            elif choice == "6":
                TerminalManager.leave_alt_screen()
                try:
                    menu_servidor_download.main()
                finally:
                    TerminalManager.enter_alt_screen()
            elif choice == "0":
                TerminalManager.begin_frame()
                sys.stdout.write(f"\n{MC.GREEN_GRADIENT}{Icons.CHECK} Saindo do Multiflow...{MC.RESET}\n")
                TerminalManager.end_frame()
                time.sleep(0.6)
                break
            else:
                TerminalManager.begin_frame()
                sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida. Tente novamente.{MC.RESET}\n")
                TerminalManager.end_frame()
                time.sleep(0.9)

        except KeyboardInterrupt:
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.YELLOW_GRADIENT}{Icons.WARNING} Interrompido pelo usuário. Saindo...{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(0.6)
            break
        except Exception as e:
            TerminalManager.begin_frame()
            sys.stdout.write(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro: {e}{MC.RESET}\n")
            TerminalManager.end_frame()
            time.sleep(1.2)
            break

    TerminalManager.leave_alt_screen()

# ==================== EXECUÇÃO ====================
if __name__ == "__main__":
    main_menu()
