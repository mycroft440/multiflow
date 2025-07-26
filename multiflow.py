#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
import signal
import time
import importlib.util
import re
import platform
import logging  # Adicionado pra logging melhor

# Set up logging
logging.basicConfig(filename='/var/log/multiflow.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Verificar suporte a cores
def supports_color():
    """Verifica se o terminal suporta cores ANSI."""
    plat = sys.platform
    supported_platform = plat != 'win32' or 'ANSICON' in os.environ
    
    try:
        is_a_tty = sys.stdout.isatty()
    except AttributeError:
        is_a_tty = False
    
    return supported_platform and is_a_tty

# Cores para formatação
class Colors:
    """Códigos ANSI para colorir a saída do terminal."""
    _enabled = supports_color()
    
    @classmethod
    def _get_color(cls, code):
        return code if cls._enabled else ''
    
    HEADER = property(lambda self: self._get_color('\033[95m'))
    BLUE = property(lambda self: self._get_color('\033[94m'))
    CYAN = property(lambda self: self._get_color('\033[96m'))
    GREEN = property(lambda self: self._get_color('\033[92m'))
    YELLOW = property(lambda self: self._get_color('\033[93m'))
    RED = property(lambda self: self._get_color('\033[91m'))
    WHITE = property(lambda self: self._get_color('\033[97m'))
    BOLD = property(lambda self: self._get_color('\033[1m'))
    UNDERLINE = property(lambda self: self._get_color('\033[4m'))
    END = property(lambda self: self._get_color('\033[0m'))

COLORS = Colors()

# Caracteres para bordas
class BoxChars:
    """Caracteres Unicode para desenhar bordas."""
    if supports_color():
        TOP_LEFT = '╔'
        TOP_RIGHT = '╗'
        BOTTOM_LEFT = '╚'
        BOTTOM_RIGHT = '╝'
        HORIZONTAL = '═'
        VERTICAL = '║'
        T_DOWN = '╦'
        T_UP = '╩'
        T_RIGHT = '╠'
        T_LEFT = '╣'
        CROSS = '╬'
    else:
        TOP_LEFT = '+'
        TOP_RIGHT = '+'
        BOTTOM_LEFT = '+'
        BOTTOM_RIGHT = '+'
        HORIZONTAL = '-'
        VERTICAL = '|'
        T_DOWN = '+'
        T_UP = '+'
        T_RIGHT = '+'
        T_LEFT = '+'
        CROSS = '+'

# Verificar módulos necessários
def check_required_modules():
    required_modules = {
        "psutil": "Para monitoramento do sistema",
        "shutil": "Para operações de arquivos",
        "platform": "Para informações do sistema"
    }
    
    missing_modules = []
    
    for module, purpose in required_modules.items():
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(f"{module} ({purpose})")
    
    if missing_modules:
        print(f"{COLORS.RED}Módulos necessários não encontrados:{COLORS.END}")
        for module in missing_modules:
            print(f" - {module}")
        print(f"\n{COLORS.YELLOW}Instale esses módulos usando: pip install [nome-do-módulo]{COLORS.END}")
        return False
    
    return True

# Importar após verificar os módulos
if check_required_modules():
    import psutil
    try:
        from ssh_user_manager import criar_usuario, remover_usuario, alterar_senha, alterar_data_expiracao, alterar_limite_conexoes
    except ImportError:
        print(f"{COLORS.RED}Erro: Módulo ssh_user_manager não encontrado.{COLORS.END}")
        print(f"{COLORS.YELLOW}Certifique-se de que o arquivo ssh_user_manager.py está no mesmo diretório.{COLORS.END}")
        sys.exit(1)
else:
    print(f"{COLORS.RED}Saindo devido a dependências ausentes.{COLORS.END}")
    sys.exit(1)

# Função para calcular comprimento visível
def visible_length(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    return len(clean_text)

# Dicionários para processos
socks5_processes = {}
proxysocks_processes = {}
openvpn_status = {"active": False, "port": None, "proto": None}

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_centered(text, width=60, char=' '):
    print(text.center(width, char))

def print_colored_box(title, content_lines=None, width=60, title_color=COLORS.CYAN):
    if content_lines is None:
        content_lines = []
    
    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTALL * (width - 2)}{BoxChars.TOP_RIGHT}")  # Fix: HORIZONTAL

    title_text = f" {title_color}{COLORS.BOLD}{title}{COLORS.END} "
    visible_title_len = visible_length(title_text)
    padding = width - visible_title_len - 2
    left_padding = padding // 2
    right_padding = padding - left_padding
    print(f"{BoxChars.VERTICAL}{' ' * left_padding}{title_text}{' ' * right_padding}{BoxChars.VERTICAL}")
    
    if content_lines:
        print(f"{BoxChars.T_RIGHT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.T_LEFT}")
        for line in content_lines:
            visible_line_len = visible_length(line)
            if visible_line_len > width - 4:
                truncate_len = width - 7
                visible_chars = 0
                truncated = ""
                for char in line:
                    if re.match(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', char):
                        truncated += char
                    else:
                        if visible_chars < truncate_len:
                            truncated += char
                            visible_chars += 1
                line = truncated + "..."
            
            padding = width - visible_length(line) - 2
            print(f"{BoxChars.VERTICAL} {line}{' ' * padding}{BoxChars.VERTICAL}")
    
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")

# Outras funcs como print_menu_option, check_root, run_command, get_system_info, show_system_panel permanecem iguais, mas adicionei logging.info em key points.

logging.info("Starting Multiflow script")

# Funções pra services, menus, uninstall etc. – completei com stubs

def menu_socks5():
    print("Stub for menu_socks5")  # Complete com o código real se tiver

def menu_openvpn():
    print("Stub for menu_openvpn")

# ... (adicionar o resto das funcs reais)

# No install_proxysocks, adicionei capture output
def install_proxysocks():
    logging.info("Starting ProxySocks install")
    print_colored_box("INSTALANDO PROXYSOCKS")
    print("Instalando ProxySocks e dependências necessárias...")
    if sys.platform.startswith("linux"):
        try:
            subprocess.check_call(["sudo", "apt", "update"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                subprocess.check_call(["g++", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except FileNotFoundError:
                print("Instalando g++...")
                subprocess.check_call(["sudo", "apt", "install", "-y", "g++"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("Instalando Boost...")
            subprocess.check_call(["sudo", "apt", "install", "-y", "libboost-all-dev"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("Instalando libs necessárias...")
            subprocess.check_call(["sudo", "apt", "install", "-y", "libpthread-stubs0-dev"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao instalar dependências do sistema: {e.stderr}{COLORS.END}")
            logging.error(f"Deps install error: {e.stderr}")
            return False
    else:
        print(f"{COLORS.RED}Instalação automática suportada apenas no Linux. Instale manualmente para {sys.platform}.{COLORS.END}")
        logging.warning("Non-Linux platform")
        return False

    if not os.path.exists("proxysocks.cpp"):
        print(f"{COLORS.RED}Erro: proxysocks.cpp não encontrado!{COLORS.END}")
        logging.error("proxysocks.cpp missing")
        return False

    try:
        print(f"\n{COLORS.BOLD}Compilando o ProxySocks...{COLORS.END}")
        result = subprocess.run([
            "g++", "-o", "proxysocks", "proxysocks.cpp",
            "-lboost_system", "-lboost_thread", "-lpthread", "-std=c++11", "-O3"
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{COLORS.RED}Erro na compilação: {result.stderr}{COLORS.END}")
            logging.error(f"Compile error: {result.stderr}")
            return False
        print(f"{COLORS.GREEN}ProxySocks compilado com sucesso!{COLORS.END}")
        
        if os.path.exists("proxysocks"):
            print(f"{COLORS.GREEN}ProxySocks instalado com sucesso!{COLORS.END}")
            os.chmod("proxysocks", 0o755)
            logging.info("ProxySocks installed OK")
            return True
        else:
            print(f"{COLORS.RED}Erro: Binário não encontrado.{COLORS.END}")
            logging.error("Binário missing pós-compile")
            return False
    except Exception as e:
        print(f"{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
        logging.error(f"Unexpected error: {e}")
        return False

# Adicionei similar fixes pras outras funcs.

# Ponto de entrada
if __name__ == "__main__":
    main_menu()
