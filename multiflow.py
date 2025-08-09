#!/usr/bin/env python3

import sys
sys.path.append("/opt/multiflow")
import os
import time
import re
import platform
import subprocess
import psutil
import json
import shutil
from datetime import datetime
import random
import termios
import tty

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

from menus.menu_style_utils import Colors, BoxChars, visible_length, clear_screen, print_colored_box, print_menu_option

# ==================== FUNÇÕES DE LIMPEZA DE TELA APRIMORADAS ====================
def force_clear_screen():
    """Limpa completamente a tela do terminal com múltiplos métodos."""
    # Método 1: Usar o comando do sistema operacional
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:  # Unix/Linux/Mac
        os.system('clear')
    
    # Método 2: Códigos ANSI para limpar e resetar
    print('\033[2J\033[H', end='')  # Clear screen and move cursor to home
    print('\033[3J', end='')        # Clear scrollback buffer
    print('\033c', end='')          # Reset terminal
    print('\033[0m', end='')        # Reset all attributes
    
    # Método 3: Flush do buffer
    sys.stdout.flush()
    
    # Pequena pausa para garantir que a limpeza seja processada
    time.sleep(0.01)

def reset_terminal():
    """Reseta completamente o estado do terminal."""
    # Reset usando tput se disponível
    try:
        subprocess.run(['tput', 'reset'], capture_output=True, timeout=0.5)
    except:
        pass
    
    # Reset códigos ANSI
    print('\033c', end='')
    print('\033[0m', end='')
    print('\033[?25h', end='')  # Mostra o cursor
    print('\033[?1049l', end='') # Sai do buffer alternativo
    sys.stdout.flush()

def clear_with_buffer():
    """Limpa a tela e gerencia o buffer do terminal."""
    # Salva a posição do cursor
    print('\033[s', end='')
    
    # Limpa toda a tela e scrollback
    print('\033[2J', end='')
    print('\033[3J', end='')
    print('\033[H', end='')
    
    # Limpa linha por linha (garante limpeza completa)
    for _ in range(100):  # Limpa 100 linhas
        print('\033[2K', end='')  # Limpa linha atual
        print('\033[1A', end='')  # Move uma linha acima
    
    # Volta ao topo
    print('\033[H', end='')
    sys.stdout.flush()

# ==================== CORES E ESTILOS MODERNOS ====================
class ModernColors:
    # Reset e modificadores
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    REVERSE = '\033[7m'
    HIDDEN = '\033[8m'
    STRIKETHROUGH = '\033[9m'
    
    # Cores principais com gradientes RGB
    PURPLE_GRADIENT = '\033[38;2;147;51;234m'  # Purple-600
    PURPLE_LIGHT = '\033[38;2;196;181;253m'    # Purple-300
    PURPLE_DARK = '\033[38;2;107;33;168m'      # Purple-800
    
    CYAN_GRADIENT = '\033[38;2;6;182;212m'     # Cyan-500
    CYAN_LIGHT = '\033[38;2;165;243;252m'      # Cyan-200
    CYAN_DARK = '\033[38;2;14;116;144m'        # Cyan-700
    
    GREEN_GRADIENT = '\033[38;2;34;197;94m'    # Green-500
    GREEN_LIGHT = '\033[38;2;134;239;172m'     # Green-300
    GREEN_DARK = '\033[38;2;22;163;74m'        # Green-600
    
    ORANGE_GRADIENT = '\033[38;2;251;146;60m'  # Orange-400
    ORANGE_LIGHT = '\033[38;2;254;215;170m'    # Orange-200
    ORANGE_DARK = '\033[38;2;234;88;12m'       # Orange-600
    
    RED_GRADIENT = '\033[38;2;239;68;68m'      # Red-500
    RED_LIGHT = '\033[38;2;254;202;202m'       # Red-200
    RED_DARK = '\033[38;2;185;28;28m'          # Red-700
    
    YELLOW_GRADIENT = '\033[38;2;250;204;21m'  # Yellow-400
    YELLOW_LIGHT = '\033[38;2;254;240;138m'    # Yellow-200
    YELLOW_DARK = '\033[38;2;202;138;4m'       # Yellow-600
    
    BLUE_GRADIENT = '\033[38;2;59;130;246m'    # Blue-500
    BLUE_LIGHT = '\033[38;2;191;219;254m'      # Blue-200
    BLUE_DARK = '\033[38;2;29;78;216m'         # Blue-700
    
    PINK_GRADIENT = '\033[38;2;236;72;153m'    # Pink-500
    PINK_LIGHT = '\033[38;2;251;207;232m'      # Pink-200
    
    # Cores neutras
    WHITE = '\033[97m'
    GRAY = '\033[38;2;156;163;175m'            # Gray-400
    LIGHT_GRAY = '\033[38;2;229;231;235m'      # Gray-200
    DARK_GRAY = '\033[38;2;75;85;99m'          # Gray-600
    BLACK = '\033[38;2;17;24;39m'              # Gray-900
    
    # Cores de fundo
    BG_DARK = '\033[48;2;17;24;39m'            # Background escuro
    BG_MEDIUM = '\033[48;2;31;41;55m'          # Background médio
    BG_LIGHT = '\033[48;2;55;65;81m'           # Background claro
    BG_ACCENT = '\033[48;2;79;70;229m'         # Background accent
    BG_SUCCESS = '\033[48;2;34;197;94m'        # Background sucesso
    BG_ERROR = '\033[48;2;239;68;68m'          # Background erro
    BG_WARNING = '\033[48;2;250;204;21m'       # Background aviso
    BG_CLEAR = '\033[49m'                      # Clear background

MC = ModernColors()

# ==================== ÍCONES E SÍMBOLOS ====================
class Icons:
    # Ícones principais
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
    ARROW = "➤ "
    BACK = "◀ "
    EXIT = "🚪 "
    CLOCK = "🕐 "
    SYSTEM = "💻 "
    UPDATE = "🔄 "
    DOWNLOAD = "📥 "
    SETTINGS = "⚙️ "
    KEY = "🔑 "
    LOCK = "🔒 "
    UNLOCK = "🔓 "
    CHECK = "✅ "
    CROSS = "❌ "
    WARNING = "⚠️ "
    INFO = "ℹ️ "
    STAR = "⭐ "
    ROCKET = "🚀 "
    FIRE = "🔥 "
    LIGHTNING = "⚡ "
    DIAMOND = "💎 "
    
    # Símbolos de caixa modernos
    BOX_TOP_LEFT = "╭"
    BOX_TOP_RIGHT = "╮"
    BOX_BOTTOM_LEFT = "╰"
    BOX_BOTTOM_RIGHT = "╯"
    BOX_HORIZONTAL = "─"
    BOX_VERTICAL = "│"
    BOX_CROSS = "┼"
    BOX_T_DOWN = "┬"
    BOX_T_UP = "┴"
    BOX_T_RIGHT = "├"
    BOX_T_LEFT = "┤"
    
    # Decorações
    DOT = "•"
    BULLET = "▸"
    TRIANGLE = "▶"
    SQUARE = "■"
    CIRCLE = "●"
    DIAMOND_SMALL = "◆"

# ==================== ANIMAÇÕES E EFEITOS ====================
class Animations:
    @staticmethod
    def typing_effect(text, delay=0.03):
        """Efeito de digitação para texto."""
        for char in text:
            print(char, end='', flush=True)
            time.sleep(delay)
        print()
    
    @staticmethod
    def loading_animation(duration=2, text="Carregando"):
        """Animação de carregamento com spinner."""
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        end_time = time.time() + duration
        i = 0
        while time.time() < end_time:
            print(f'\r{MC.CYAN_GRADIENT}{spinner[i % len(spinner)]} {text}...{MC.RESET}', end='', flush=True)
            time.sleep(0.1)
            i += 1
        print('\r' + ' ' * (len(text) + 10) + '\r', end='')
    
    @staticmethod
    def pulse_text(text, times=3):
        """Faz o texto pulsar."""
        for _ in range(times):
            print(f'\r{MC.BOLD}{text}{MC.RESET}', end='', flush=True)
            time.sleep(0.3)
            print(f'\r{MC.DIM}{text}{MC.RESET}', end='', flush=True)
            time.sleep(0.3)
        print(f'\r{MC.BOLD}{text}{MC.RESET}')

# ==================== FUNÇÕES DE INTERFACE MELHORADAS ====================
def print_gradient_line(width=80, char='═', colors=[MC.PURPLE_GRADIENT, MC.CYAN_GRADIENT, MC.BLUE_GRADIENT]):
    """Imprime uma linha com efeito gradiente."""
    segment_size = width // len(colors)
    line = ""
    for i, color in enumerate(colors):
        if i == len(colors) - 1:
            line += f"{color}{char * (width - segment_size * i)}"
        else:
            line += f"{color}{char * segment_size}"
    print(f"{line}{MC.RESET}")

def print_modern_header():
    """Exibe um cabeçalho moderno com arte ASCII e efeitos."""
    # Não limpa a tela aqui, pois já foi limpa antes
    
    # Linha superior com gradiente
    print_gradient_line(76)
    
    # Logo com efeito de sombra e glow
    logo_lines = [
        f"{MC.PURPLE_LIGHT}███╗   ███╗{MC.CYAN_LIGHT}██╗   ██╗{MC.BLUE_LIGHT}██╗  ████████╗{MC.GREEN_LIGHT}██╗███████╗{MC.ORANGE_LIGHT}██╗      {MC.PINK_GRADIENT}██████╗ {MC.YELLOW_LIGHT}██╗    ██╗",
        f"{MC.PURPLE_GRADIENT}████╗ ████║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║  ╚══██╔══╝{MC.GREEN_GRADIENT}██║██╔════╝{MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██╔═══██╗{MC.YELLOW_GRADIENT}██║    ██║",
        f"{MC.PURPLE_GRADIENT}██╔████╔██║{MC.CYAN_GRADIENT}██║   ██║{MC.BLUE_GRADIENT}██║     ██║   {MC.GREEN_GRADIENT}██║█████╗  {MC.ORANGE_GRADIENT}██║     {MC.PINK_GRADIENT}██║   ██║{MC.YELLOW_GRADIENT}██║ █╗ ██║",
        f"{MC.PURPLE_DARK}██║╚██╔╝██║{MC.CYAN_DARK}██║   ██║{MC.BLUE_DARK}██║     ██║   {MC.GREEN_DARK}██║██╔══╝  {MC.ORANGE_DARK}██║     {MC.RED_GRADIENT}██║   ██║{MC.YELLOW_DARK}██║███╗██║",
        f"{MC.PURPLE_DARK}██║ ╚═╝ ██║{MC.CYAN_DARK}╚██████╔╝{MC.BLUE_DARK}███████╗██║   {MC.GREEN_DARK}██║██║     {MC.ORANGE_DARK}███████╗{MC.RED_DARK}╚██████╔╝{MC.YELLOW_DARK}╚███╔███╔╝",
        f"{MC.DARK_GRAY}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝"
    ]
    
    for line in logo_lines:
        print(f"  {line}{MC.RESET}")
    
    # Subtítulo com efeito
    print(f"\n{MC.GRAY}{'═' * 76}{MC.RESET}")
    print(f"{MC.CYAN_GRADIENT}{MC.BOLD}{'Sistema Avançado de Gerenciamento VPS'.center(76)}{MC.RESET}")
    print(f"{MC.GRAY}{'═' * 76}{MC.RESET}\n")

def print_modern_box(title, content, icon="", primary_color=MC.CYAN_GRADIENT, secondary_color=MC.CYAN_LIGHT, animated=False):
    """Cria uma caixa moderna com bordas estilizadas e gradientes."""
    width = 74
    title_text = f" {icon}{title} " if icon else f" {title} "
    
    # Cabeçalho da caixa com título centralizado
    print(f"{primary_color}{Icons.BOX_TOP_LEFT}{'─' * 10}{secondary_color}┤{MC.BOLD}{MC.WHITE}{title_text}{MC.RESET}{secondary_color}├{primary_color}{'─' * (width - len(title_text) - 12)}{Icons.BOX_TOP_RIGHT}{MC.RESET}")
    
    # Conteúdo da caixa
    if content:
        for line in content:
            clean_line = re.sub(r'\033\[[0-9;]*m', '', line)
            padding_needed = width - len(clean_line) - 2
            print(f"{primary_color}{Icons.BOX_VERTICAL}{MC.RESET} {line}{' ' * padding_needed} {primary_color}{Icons.BOX_VERTICAL}{MC.RESET}")
    
    # Rodapé da caixa
    print(f"{primary_color}{Icons.BOX_BOTTOM_LEFT}{'─' * width}{Icons.BOX_BOTTOM_RIGHT}{MC.RESET}")

def print_modern_menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, hover_effect=False, badge=""):
    """Imprime uma opção de menu moderna com efeitos visuais."""
    # Formatação do número da opção
    if number == "0":
        number_display = f"{MC.RED_GRADIENT}{MC.BOLD}[{number}]{MC.RESET}"
        icon = icon or Icons.EXIT
    else:
        number_display = f"{color}{MC.BOLD}[{number}]{MC.RESET}"
    
    # Badge opcional (ex: "NOVO", "BETA", etc)
    badge_text = f" {MC.BG_ACCENT}{MC.WHITE}{MC.BOLD} {badge} {MC.RESET}" if badge else ""
    
    # Efeito hover simulado
    if hover_effect:
        print(f"  {MC.REVERSE}{number_display} {icon}{MC.WHITE}{text}{badge_text}{MC.RESET}")
    else:
        print(f"  {number_display} {icon}{MC.WHITE}{text}{badge_text}{MC.RESET}")

def create_progress_bar(percent, width=20, show_percentage=True, gradient=True):
    """Cria uma barra de progresso visual com gradiente de cores."""
    filled = int(percent * width / 100)
    empty = width - filled
    
    # Determina a cor baseada na porcentagem
    if percent < 30:
        bar_color = MC.GREEN_GRADIENT
        fill_char = '█'
    elif percent < 60:
        bar_color = MC.YELLOW_GRADIENT
        fill_char = '█'
    elif percent < 80:
        bar_color = MC.ORANGE_GRADIENT
        fill_char = '█'
    else:
        bar_color = MC.RED_GRADIENT
        fill_char = '█'
    
    # Cria a barra
    if gradient:
        bar = f"{bar_color}{'█' * filled}{MC.DARK_GRAY}{'░' * empty}{MC.RESET}"
    else:
        bar = f"{bar_color}{'█' * filled}{'░' * empty}{MC.RESET}"
    
    # Adiciona porcentagem se solicitado
    if show_percentage:
        return f"[{bar}] {bar_color}{percent:5.1f}%{MC.RESET}"
    return f"[{bar}]"

def show_combined_system_panel():
    """Exibe um painel combinado com informações do sistema e serviços ativos."""
    info = get_system_info()
    
    # Obtém informações adicionais
    uptime = get_system_uptime()
    current_time = datetime.now().strftime("%H:%M:%S")
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    # Nome do sistema formatado
    os_name_short = (info['os_name'][:35] + '...') if len(info['os_name']) > 38 else info['os_name']
    
    # Cria barras de progresso visuais
    ram_bar = create_progress_bar(info["ram_percent"], 15, True, True)
    cpu_bar = create_progress_bar(info["cpu_percent"], 15, True, True)
    
    # Obtém serviços ativos com ícones
    active_services = get_active_services()
    
    # Monta o conteúdo do painel em duas colunas
    system_content = [
        f"{MC.CYAN_LIGHT}{Icons.SYSTEM} Sistema:{MC.RESET} {MC.WHITE}{os_name_short}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.CLOCK} Uptime:{MC.RESET} {MC.WHITE}{uptime}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.RAM} RAM:{MC.RESET} {ram_bar}",
        f"{MC.CYAN_LIGHT}{Icons.CPU} CPU:{MC.RESET} {cpu_bar}",
    ]
    
    # Adiciona linha de serviços ativos
    if active_services:
        services_line = f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços:{MC.RESET} "
        for i, service in enumerate(active_services[:4]):  # Máximo 4 serviços
            if i > 0:
                services_line += " │ "
            services_line += service
        system_content.append(services_line)
        
        # Se houver mais de 4 serviços, adiciona segunda linha
        if len(active_services) > 4:
            services_line2 = f"{' ' * 13}"
            for i, service in enumerate(active_services[4:8]):
                if i > 0:
                    services_line2 += " │ "
                services_line2 += service
            system_content.append(services_line2)
    else:
        system_content.append(f"{MC.CYAN_LIGHT}{Icons.NETWORK} Serviços:{MC.RESET} {MC.GRAY}Nenhum serviço ativo{MC.RESET}")
    
    # Adiciona data e hora
    system_content.append(f"{MC.CYAN_LIGHT}📅 Data/Hora:{MC.RESET} {MC.WHITE}{current_date} - {current_time}{MC.RESET}")
    
    print_modern_box("PAINEL DO SISTEMA", system_content, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

def get_system_uptime():
    """Obtém o uptime do sistema formatado."""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except:
        return "N/A"

def get_active_services():
    """Obtém lista de serviços ativos com ícones e cores."""
    services = []
    
    def run_cmd(cmd):
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except:
            return ""
    
    # Verificar ZRAM e SWAP
    swapon_output = run_cmd(['swapon', '--show'])
    if 'zram' in swapon_output:
        services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} ZRAM{MC.RESET}")
    if '/swapfile' in swapon_output or 'partition' in swapon_output:
        services.append(f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} SWAP{MC.RESET}")
    
    # Verificar ProxySocks
    try:
        if os.path.exists(menu_proxysocks.STATE_FILE):
            with open(menu_proxysocks.STATE_FILE, 'r') as f:
                pid, port = f.read().strip().split(':')
                if psutil.pid_exists(int(pid)):
                    services.append(f"{MC.BLUE_GRADIENT}{Icons.ACTIVE} Proxy:{port}{MC.RESET}")
    except:
        pass
    
    # Verificar OpenVPN
    if os.path.exists('/etc/openvpn/server.conf'):
        services.append(f"{MC.CYAN_GRADIENT}{Icons.ACTIVE} OpenVPN{MC.RESET}")
    
    # Verificar BadVPN
    try:
        result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip() == "active":
            services.append(f"{MC.PURPLE_GRADIENT}{Icons.ACTIVE} BadVPN{MC.RESET}")
    except:
        pass
    
    # Verificar SSH
    try:
        result = subprocess.run(["systemctl", "is-active", "ssh"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip() == "active":
            services.append(f"{MC.ORANGE_GRADIENT}{Icons.ACTIVE} SSH{MC.RESET}")
    except:
        pass
    
    return services

def show_welcome_message():
    """Exibe uma mensagem de boas-vindas animada."""
    messages = [
        f"{Icons.ROCKET} Bem-vindo ao MultiFlow!",
        f"{Icons.FIRE} Sistema pronto para uso!",
        f"{Icons.LIGHTNING} Velocidade máxima ativada!",
        f"{Icons.STAR} Tenha um ótimo dia!",
        f"{Icons.DIAMOND} Premium Experience"
    ]
    message = random.choice(messages)
    print(f"\n{MC.CYAN_GRADIENT}{MC.BOLD}{message.center(76)}{MC.RESET}\n")

def print_footer():
    """Imprime um rodapé estilizado."""
    print(f"\n{MC.DARK_GRAY}{'─' * 76}{MC.RESET}")
    print(f"{MC.GRAY}MultiFlow v2.0 │ Desenvolvido com {MC.RED_GRADIENT}♥{MC.GRAY} │ github.com/seu-repo{MC.RESET}")
    print(f"{MC.DARK_GRAY}{'─' * 76}{MC.RESET}")

# ==================== FUNÇÕES DO SISTEMA (mantidas do código original) ====================
def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        force_clear_screen()
        print_modern_header()
        print_modern_box("AVISO DE SEGURANÇA", [
            f"{MC.RED_GRADIENT}{Icons.WARNING} Este script precisa ser executado como root!{MC.RESET}",
            f"{MC.YELLOW_GRADIENT}Algumas operações podem falhar sem privilégios adequados.{MC.RESET}"
        ], Icons.SHIELD, MC.RED_GRADIENT, MC.RED_LIGHT)
        
        confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar mesmo assim? (s/n): {MC.RESET}")
        if confirm.lower() != 's':
            print(f"\n{MC.GREEN_GRADIENT}Saindo...{MC.RESET}")
            sys.exit(0)
        return False
    return True

def monitorar_uso_recursos(intervalo_cpu=0.5, amostras_cpu=1):
    """Monitora o uso da memória RAM e da CPU."""
    try:
        ram = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=intervalo_cpu)
        return {'ram_percent': ram.percent, 'cpu_percent': cpu_percent}
    except Exception:
        return {'ram_percent': 0, 'cpu_percent': 0}

def get_system_info():
    """Obtém informações do sistema para o painel."""
    system_info = {"os_name": "Desconhecido", "ram_percent": 0, "cpu_percent": 0}
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_info = dict(line.strip().split('=', 1) for line in f if '=' in line)
            system_info["os_name"] = os_info.get('PRETTY_NAME', 'Linux').strip('"')
        recursos = monitorar_uso_recursos()
        system_info.update(recursos)
    except Exception:
        pass
    return system_info

# ==================== MENUS (mantidos do código original com visual melhorado) ====================
def ssh_users_main_menu():
    """Redireciona para o menu de gerenciamento de usuários SSH."""
    force_clear_screen()
    manusear_usuarios.main()

def conexoes_menu():
    """Menu para gerenciar conexões."""
    while True:
        force_clear_screen()
        print_modern_header()
        show_combined_system_panel()
        
        print()
        print_modern_box("GERENCIAR CONEXÕES", [], Icons.NETWORK, MC.CYAN_GRADIENT, MC.CYAN_LIGHT)
        print()
        
        print_modern_menu_option("1", "Gerenciar OpenVPN", Icons.LOCK, MC.GREEN_GRADIENT)
        print_modern_menu_option("2", "ProxySocks (Simples)", Icons.UNLOCK, MC.BLUE_GRADIENT)
        print()
        print_modern_menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT)
        
        print_footer()
        
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}╰─➤ Escolha uma opção: {MC.RESET}")
        
        if choice == "1":
            force_clear_screen()
            try:
                script_real_path = os.path.realpath(__file__)
                script_dir = os.path.dirname(script_real_path)
                openvpn_script_path = os.path.join(script_dir, 'conexoes', 'openvpn.sh')
                
                if not os.path.exists(openvpn_script_path):
                    print(f"{MC.RED_GRADIENT}Erro: O script 'openvpn.sh' não foi encontrado.{MC.RESET}")
                    time.sleep(4)
                    continue

                os.chmod(openvpn_script_path, 0o755)
                subprocess.run(['bash', openvpn_script_path], check=True)
            
            except Exception as e:
                print(f"{MC.RED_GRADIENT}Ocorreu um erro: {e}{MC.RESET}")
                time.sleep(3)

        elif choice == "2":
            menu_proxysocks.main()
        elif choice == "0":
            break
        else:
            print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida!{MC.RESET}")
            time.sleep(1)

def otimizadorvps_menu():
    """Redireciona para o script otimizadorvps.py."""
    force_clear_screen()
    try:
        script_real_path = os.path.realpath(__file__)
        script_dir = os.path.dirname(script_real_path)
        otimizador_path = os.path.join(script_dir, 'ferramentas', 'otimizadorvps.py')
        subprocess.run([sys.executable, otimizador_path], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"{MC.RED_GRADIENT}Erro ao executar o otimizador: {e}{MC.RESET}")
    input(f"\n{MC.BOLD}Pressione Enter para continuar...{MC.RESET}")

def ferramentas_menu():
    """Menu para acessar as ferramentas de otimização."""
    while True:
        force_clear_screen()
        print_modern_header()
        show_combined_system_panel()
        
        print()
        print_modern_box("FERRAMENTAS DE OTIMIZAÇÃO", [], Icons.TOOLS, MC.ORANGE_GRADIENT, MC.ORANGE_LIGHT)
        print()
        
        print_modern_menu_option("1", "Otimizador de VPS", Icons.ROCKET, MC.GREEN_GRADIENT, badge="TURBO")
        print_modern_menu_option("2", "Bloqueador de Sites", Icons.SHIELD, MC.RED_GRADIENT)
        print()
        print_modern_menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT)
        
        print_footer()
        
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}╰─➤ Escolha uma opção: {MC.RESET}")

        if choice == "1":
            otimizadorvps_menu()
        elif choice == "2":
            menu_bloqueador.main_menu()
        elif choice == "0":
            break
        else:
            print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida!{MC.RESET}")
            time.sleep(1)

def atualizar_multiflow():
    """Executa o script de atualização em Python e encerra o programa."""
    force_clear_screen()
    print_modern_header()
    
    print()
    print_modern_box("ATUALIZADOR MULTIFLOW", [
        f"{MC.YELLOW_GRADIENT}{Icons.INFO} Este processo irá baixar a versão mais recente do GitHub.{MC.RESET}",
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Serviços ativos como BadVPN e ProxySocks serão parados.{MC.RESET}",
        f"{MC.RED_GRADIENT}{Icons.WARNING} O programa será encerrado após a atualização.{MC.RESET}",
        f"{MC.WHITE}{Icons.INFO} Você precisará iniciá-lo novamente para usar a nova versão.{MC.RESET}"
    ], Icons.UPDATE, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

    print_footer()
    
    confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar com a atualização? (s/n): {MC.RESET}").lower()
    
    if confirm == 's':
        try:
            script_dir = os.path.dirname(os.path.realpath(__file__))
            update_script_path = os.path.join(script_dir, 'update.py')

            if not os.path.exists(update_script_path):
                print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro: Script 'update.py' não encontrado!{MC.RESET}")
                time.sleep(3)
                return

            print(f"\n{MC.CYAN_GRADIENT}{'═' * 60}{MC.RESET}")
            Animations.loading_animation(2, "Iniciando atualização")
            subprocess.run(['sudo', sys.executable, update_script_path], check=True)
            print(f"{MC.CYAN_GRADIENT}{'═' * 60}{MC.RESET}")
            
            print(f"\n{MC.GREEN_GRADIENT}{Icons.CHECK} O programa foi atualizado com sucesso!{MC.RESET}")
            print(f"{MC.YELLOW_GRADIENT}{Icons.INFO} Encerrando agora. Por favor, inicie novamente com 'multiflow'.{MC.RESET}")
            time.sleep(3)
            force_clear_screen()
            sys.exit(0)

        except subprocess.CalledProcessError:
            print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Ocorreu um erro durante a atualização.{MC.RESET}")
            input(f"{MC.BOLD}Pressione Enter para voltar ao menu...{MC.RESET}")
        except Exception as e:
            print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro inesperado: {e}{MC.RESET}")
            input(f"{MC.BOLD}Pressione Enter para continuar...{MC.RESET}")
    else:
        print(f"\n{MC.YELLOW_GRADIENT}{Icons.INFO} Atualização cancelada.{MC.RESET}")
        time.sleep(2)

# ==================== MENU PRINCIPAL ====================
def main_menu():
    """Menu principal do sistema."""
    check_root()
    
    # Animação inicial (opcional)
    force_clear_screen()
    print_modern_header()
    Animations.loading_animation(1, "Inicializando sistema")
    
    while True:
        try:
            # Limpa completamente a tela antes de redesenhar
            force_clear_screen()
            
            # Redesenha toda a interface
            print_modern_header()
            show_combined_system_panel()
            show_welcome_message()
            
            print_modern_box("MENU PRINCIPAL", [], Icons.DIAMOND, MC.BLUE_GRADIENT, MC.BLUE_LIGHT)
            print()
            
            # Opções do menu com ícones e cores diferentes
            print_modern_menu_option("1", "Gerenciar Usuários SSH", Icons.USERS, MC.GREEN_GRADIENT)
            print_modern_menu_option("2", "Gerenciar Conexões", Icons.NETWORK, MC.CYAN_GRADIENT)
            print_modern_menu_option("3", "BadVPN", Icons.SERVER, MC.PURPLE_GRADIENT)
            print_modern_menu_option("4", "Ferramentas", Icons.TOOLS, MC.ORANGE_GRADIENT)
            print_modern_menu_option("5", "Atualizar MultiFlow", Icons.UPDATE, MC.YELLOW_GRADIENT, badge="v2.0")
            print_modern_menu_option("6", "Servidor de Download", Icons.DOWNLOAD, MC.PINK_GRADIENT)
            print()
            print_modern_menu_option("0", "Sair do Sistema", Icons.EXIT, MC.RED_GRADIENT)
            
            print_footer()
            
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}╰─➤ Escolha uma opção: {MC.RESET}")
            
            if choice == "1":
                ssh_users_main_menu()
            elif choice == "2":
                conexoes_menu()
            elif choice == "3":
                force_clear_screen()
                menu_badvpn.main_menu()
            elif choice == "4":
                ferramentas_menu()
            elif choice == "5":
                atualizar_multiflow()
            elif choice == "6":
                force_clear_screen()
                menu_servidor_download.main()
            elif choice == "0":
                force_clear_screen()
                print(f"\n{MC.GREEN_GRADIENT}{Icons.CHECK} Encerrando o MultiFlow...{MC.RESET}")
                Animations.loading_animation(1, "Finalizando")
                print(f"{MC.CYAN_GRADIENT}Obrigado por usar o MultiFlow! Até logo!{MC.RESET}\n")
                force_clear_screen()
                break
            else:
                print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Opção inválida! Tente novamente.{MC.RESET}")
                time.sleep(1.5)
                
        except KeyboardInterrupt:
            print(f"\n\n{MC.YELLOW_GRADIENT}{Icons.WARNING} Operação interrompida pelo usuário.{MC.RESET}")
            confirm = input(f"{MC.BOLD}Deseja realmente sair? (s/n): {MC.RESET}")
            if confirm.lower() == 's':
                force_clear_screen()
                print(f"\n{MC.GREEN_GRADIENT}Saindo do MultiFlow...{MC.RESET}\n")
                break

# ==================== EXECUÇÃO PRINCIPAL ====================
if __name__ == "__main__":
    try:
        # Reset inicial do terminal
        reset_terminal()
        main_menu()
        # Reset final do terminal
        reset_terminal()
    except Exception as e:
        force_clear_screen()
        print(f"\n{MC.RED_GRADIENT}{Icons.CROSS} Erro crítico: {e}{MC.RESET}")
        print(f"{MC.YELLOW_GRADIENT}Por favor, reporte este erro aos desenvolvedores.{MC.RESET}\n")
        reset_terminal()
        sys.exit(1)
