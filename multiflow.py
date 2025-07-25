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
from ssh_user_manager import criar_usuario, remover_usuario, alterar_senha, alterar_data_expiracao, alterar_limite_conexoes

import psutil  # Importa após possível instalação

# Cores para formatação
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# Caracteres para bordas
class BoxChars:
    # Cantos
    TOP_LEFT = '╔'
    TOP_RIGHT = '╗'
    BOTTOM_LEFT = '╚'
    BOTTOM_RIGHT = '╝'
    
    # Linhas
    HORIZONTAL = '═'
    VERTICAL = '║'
    
    # T-junctions
    T_DOWN = '╦'
    T_UP = '╩'
    T_RIGHT = '╠'
    T_LEFT = '╣'
    
    # Cruzamento
    CROSS = '╬'

# Dicionário para rastrear processos SOCKS5 por porta
socks5_processes = {}

# Status do OpenVPN
openvpn_status = {"active": False, "port": None, "proto": None}

def clear_screen():
    """Limpa a tela do console."""
    os.system("cls" if os.name == "nt" else "clear")

def print_centered(text, width=60, char=' '):
    """Imprime texto centralizado com uma largura específica."""
    print(text.center(width, char))

def print_colored_box(title, content_lines=None, width=60, title_color=Colors.CYAN):
    """Imprime uma caixa colorida com título e conteúdo."""
    if content_lines is None:
        content_lines = []
    
    # Título da caixa
    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
    
    # Título centralizado
    title_text = f" {title_color}{Colors.BOLD}{title}{Colors.END} "
    padding = width - len(title) - 4
    left_padding = padding // 2
    right_padding = padding - left_padding
    print(f"{BoxChars.VERTICAL}{' ' * left_padding}{title_text}{' ' * right_padding}{BoxChars.VERTICAL}")
    
    if content_lines:
        # Linha separadora
        print(f"{BoxChars.T_RIGHT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.T_LEFT}")
        
        # Conteúdo
        for line in content_lines:
            # Garantir que a linha tenha exatamente o tamanho correto
            if len(line) > width - 4:
                line = line[:width - 7] + "..."
            
            padding = width - len(line) - 2
            print(f"{BoxChars.VERTICAL} {line}{' ' * padding}{BoxChars.VERTICAL}")
    
    # Base da caixa
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")

def print_menu_option(number, description, status=None, color=Colors.WHITE):
    """Formata uma opção de menu com possível status."""
    width = 58
    number_text = f"{Colors.BOLD}{color}[{number}]{Colors.END}"
    if status:
        status_text = f"{status}"
        # Calcular espaço disponível para descrição
        desc_space = width - len(number_text) - len(status_text) - 4  # -4 para espaços e colchetes
        if len(description) > desc_space:
            description = description[:desc_space-3] + "..."
        
        option_text = f" {number_text} {description}"
        padding = width - len(option_text) - len(status_text)
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{status_text} {BoxChars.VERTICAL}")
    else:
        option_text = f" {number_text} {description}"
        padding = width - len(option_text)
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{BoxChars.VERTICAL}")

def run_command(cmd, sudo=False):
    """Executa um comando via subprocess, com opção de sudo."""
    if sudo:
        cmd = ["sudo"] + cmd
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        print(result)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar {' '.join(cmd)}: {e.output}")
        return False
    except Exception as e:
        print(f"Exceção inesperada: {e}")
        return False

def get_system_info():
    """Obtém informações do sistema para o painel."""
    system_info = {
        "os_name": "Desconhecido",
        "ram_percent": 0,
        "cpu_percent": 0
    }
    
    # Obter nome e versão do sistema operacional
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_info = {}
                for line in f:
                    if '=' in line:
                        key, value = line.rstrip('\n').split('=', 1)
                        os_info[key] = value.strip('"').strip("'")
                
                if 'PRETTY_NAME' in os_info:
                    system_info["os_name"] = os_info['PRETTY_NAME']
                elif 'NAME' in os_info and 'VERSION_ID' in os_info:
                    system_info["os_name"] = f"{os_info['NAME']} {os_info['VERSION_ID']}"
        
        if system_info["os_name"] == "Desconhecido" and sys.platform == 'darwin':
            mac_ver = platform.mac_ver()[0]
            system_info["os_name"] = f"macOS {mac_ver}"
        elif system_info["os_name"] == "Desconhecido" and sys.platform == 'win32':
            system_info["os_name"] = platform.win32_ver()[0]
    except Exception:
        pass
    
    # Obter uso de RAM
    try:
        virtual_memory = psutil.virtual_memory()
        system_info["ram_percent"] = virtual_memory.percent
    except Exception:
        pass
    
    # Obter uso de CPU
    try:
        system_info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    except Exception:
        pass
    
    return system_info

def show_system_panel():
    """Exibe o painel com informações do sistema."""
    info = get_system_info()
    
    # Definir cores para os percentuais
    def get_color_code(percent):
        if percent < 50:
            return Colors.GREEN
        elif percent < 80:
            return Colors.YELLOW
        else:
            return Colors.RED
    
    ram_color = get_color_code(info["ram_percent"])
    cpu_color = get_color_code(info["cpu_percent"])
    
    # Construir o painel
    content_lines = [
        f"{Colors.BOLD}OS:{Colors.END} {Colors.WHITE}{info['os_name']}{Colors.END}",
        f"{Colors.BOLD}RAM:{Colors.END} {ram_color}{info['ram_percent']:>5.1f}%{Colors.END}  |  {Colors.BOLD}CPU:{Colors.END} {cpu_color}{info['cpu_percent']:>5.1f}%{Colors.END}"
    ]
    
    print_colored_box("INFORMAÇÕES DO SISTEMA", content_lines)

# Funções para verificar status dos serviços
def check_services_status():
    """Verifica o status dos serviços SOCKS5 e OpenVPN."""
    socks_status = "Ativo - Portas " + ", ".join([str(porta) for porta in socks5_processes.keys()]) if socks5_processes else "Desativado"
    
    # Verificar status do OpenVPN
    openvpn_running = False
    openvpn_port = None
    
    try:
        # Procurar processo OpenVPN
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'openvpn' in proc.info['name'].lower() or any('openvpn' in cmd.lower() for cmd in proc.info['cmdline'] if cmd):
                openvpn_running = True
                
                # Tentar encontrar a porta nos argumentos de linha de comando
                for i, arg in enumerate(proc.info['cmdline']):
                    if arg == '--port' and i + 1 < len(proc.info['cmdline']):
                        openvpn_port = proc.info['cmdline'][i + 1]
                        break
                
                # Se não encontrou pelo argumento, tenta buscar no arquivo de configuração
                if not openvpn_port and os.path.exists('/etc/openvpn/server.conf'):
                    with open('/etc/openvpn/server.conf', 'r') as f:
                        for line in f:
                            if line.strip().startswith('port '):
                                openvpn_port = line.strip().split()[1]
                                break
                
                # Caso ainda não tenha encontrado, verifica nosso arquivo local
                if not openvpn_port and os.path.exists('server.conf'):
                    with open('server.conf', 'r') as f:
                        for line in f:
                            if line.strip().startswith('port '):
                                openvpn_port = line.strip().split()[1]
                                break
                
                break
    except Exception as e:
        print(f"Erro ao verificar status do OpenVPN: {e}")
    
    # Atualizar status global do OpenVPN
    openvpn_status["active"] = openvpn_running
    if openvpn_running and openvpn_port:
        openvpn_status["port"] = openvpn_port
    
    openvpn_status_text = f"Ativo - Porta {openvpn_status['port']}" if openvpn_running and openvpn_status["port"] else "Desativado"
    
    return socks_status, openvpn_status_text

# Funções para SOCKS5
def check_and_install_package(package_name):
    if importlib.util.find_spec(package_name) is None:
        print(f"Instalando {package_name} via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"{package_name} instalado com sucesso!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Erro ao instalar {package_name}: {e}")
            return False
    return True

def install_socks5():
    print_colored_box("INSTALANDO SOCKS5")
    print("Instalando SOCKS5 e todas as dependências necessárias...")
    if not check_and_install_package("psutil"):
        print(f"{Colors.RED}Falha ao instalar dependências Python. Continue manualmente.{Colors.END}")
        return False

    if sys.platform.startswith("linux"):
        try:
            subprocess.check_call(["sudo", "apt", "update"])
            try:
                subprocess.check_call(["g++", "--version"])
            except FileNotFoundError:
                print("Instalando g++...")
                subprocess.check_call(["sudo", "apt", "install", "-y", "g++"])
            print("Instalando Boost...")
            subprocess.check_call(["sudo", "apt", "install", "-y", "libboost-all-dev"])
            print("Instalando libssh2...")
            subprocess.check_call(["sudo", "apt", "install", "-y", "libssh2-1-dev"])
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED}Erro ao instalar dependências do sistema: {e}{Colors.END}")
            return False
    else:
        print(f"{Colors.RED}Instalação automática suportada apenas no Linux. Instale manualmente para {sys.platform}.{Colors.END}")
        return False

    if not os.path.exists("src/socks5_server.cpp"):
        print(f"{Colors.RED}Erro: src/socks5_server.cpp não encontrado!{Colors.END}")
        return False

    try:
        print("Compilando o servidor SOCKS5...")
        subprocess.check_call([
            "g++", "-o", "socks5_server", "src/socks5_server.cpp",
            "-lboost_system", "-lboost_log", "-lboost_thread", "-lpthread", "-lssh2", "-std=c++14"
        ])
        print(f"{Colors.GREEN}SOCKS5 instalado com sucesso!{Colors.END}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}Erro na compilação: {e}{Colors.END}")
        return False

def add_port_socks5():
    print_colored_box("ADICIONAR PORTA SOCKS5")
    port = input(f"{Colors.CYAN}Digite a porta desejada (1-65535): {Colors.END}")
    try:
        port = int(port)
        if port < 1 or port > 65535:
            print(f"{Colors.RED}Porta inválida!{Colors.END}")
            return
    except ValueError:
        print(f"{Colors.RED}Entrada inválida!{Colors.END}")
        return

    if port in socks5_processes:
        print(f"{Colors.RED}Porta {port} já em uso!{Colors.END}")
        return

    if not os.path.exists("socks5_server"):
        print(f"{Colors.RED}Erro: Servidor não compilado!{Colors.END}")
        return

    try:
        process = subprocess.Popen(
            ["./socks5_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process.stdin.write(f"{port}\n")
        process.stdin.flush()
        time.sleep(1)
        if process.poll() is None:
            socks5_processes[port] = process
            print(f"{Colors.GREEN}SOCKS5 iniciado na porta {port}.{Colors.END}")
        else:
            print(f"{Colors.RED}Erro ao iniciar na porta {port}.{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Erro: {e}{Colors.END}")

def remove_port_socks5():
    print_colored_box("REMOVER PORTA SOCKS5")
    port = input(f"{Colors.CYAN}Digite a porta a ser removida: {Colors.END}")
    try:
        port = int(port)
        if port not in socks5_processes:
            print(f"{Colors.RED}Nenhum SOCKS5 na porta {port}!{Colors.END}")
            return
    except ValueError:
        print(f"{Colors.RED}Entrada inválida!{Colors.END}")
        return

    process = socks5_processes[port]
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        del socks5_processes[port]
        print(f"{Colors.GREEN}SOCKS5 removido da porta {port}.{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Erro: {e}{Colors.END}")

def remove_socks5():
    print_colored_box("REMOVER SOCKS5")
    print("Removendo SOCKS5...")
    for port, process in list(socks5_processes.items()):
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
            print(f"Encerrado na porta {port}.")
        except Exception as e:
            print(f"{Colors.RED}Erro ao encerrar na porta {port}: {e}{Colors.END}")
    socks5_processes.clear()

    if os.path.exists("socks5_server"):
        try:
            os.remove("socks5_server")
            print("Binário removido.")
        except Exception as e:
            print(f"{Colors.RED}Erro: {e}{Colors.END}")
    else:
        print("Nenhum binário encontrado.")
    print(f"{Colors.GREEN}SOCKS5 removido com sucesso.{Colors.END}")

def menu_socks5():
    while True:
        clear_screen()
        
        # Verificar status atual
        socks_status, _ = check_services_status()
        
        # Título e status
        status_color = Colors.GREEN if "Ativo" in socks_status else Colors.RED
        content_lines = [f"{Colors.BOLD}Status:{Colors.END} {status_color}{socks_status}{Colors.END}"]
        print_colored_box("GERENCIAR SOCKS5", content_lines)
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Instalar SOCKS5", color=Colors.CYAN)
        print_menu_option("2", "Adicionar Porta", color=Colors.CYAN)
        print_menu_option("3", "Remover Porta", color=Colors.CYAN)
        print_menu_option("4", "Remover SOCKS5", color=Colors.CYAN)
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")

        if choice == "1":
            install_socks5()
        elif choice == "2":
            add_port_socks5()
        elif choice == "3":
            remove_port_socks5()
        elif choice == "4":
            remove_socks5()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

# O resto das funções continua igual, vamos apenas atualizar os menus principais

def menu_openvpn():
    while True:
        clear_screen()
        
        # Verificar status atual
        _, openvpn_status_text = check_services_status()
        
        # Título e status
        status_color = Colors.GREEN if "Ativo" in openvpn_status_text else Colors.RED
        content_lines = [f"{Colors.BOLD}Status:{Colors.END} {status_color}{openvpn_status_text}{Colors.END}"]
        print_colored_box("GERENCIAR OPENVPN", content_lines)
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Instalar OpenVPN", color=Colors.CYAN)
        print_menu_option("2", "Remover OpenVPN", color=Colors.CYAN)
        
        if openvpn_status["active"]:
            print_menu_option("3", "Parar OpenVPN", color=Colors.CYAN)
        else:
            print_menu_option("3", "Iniciar OpenVPN", color=Colors.CYAN)
        
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")

        if choice == "1":
            install_openvpn()
        elif choice == "2":
            if openvpn_status["active"]:
                print(f"{Colors.RED}O OpenVPN está em execução. Pare o serviço antes de removê-lo.{Colors.END}")
                input(f"{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")
                continue
            remove_openvpn()
        elif choice == "3":
            if openvpn_status["active"]:
                stop_openvpn()
            else:
                start_openvpn()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

def menu_conexoes():
    while True:
        clear_screen()
        
        # Verificar status dos serviços
        socks_status, openvpn_status_text = check_services_status()
        
        print_colored_box("GERENCIAR CONEXÕES")
        
        # Opções do menu com status
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        
        # Status colorido para SOCKS5
        socks_status_color = f"{Colors.GREEN}{socks_status}{Colors.END}" if "Ativo" in socks_status else f"{Colors.RED}{socks_status}{Colors.END}"
        print_menu_option("1", "Gerenciar SOCKS5", f"[ {socks_status_color} ]", Colors.CYAN)
        
        # Status colorido para OpenVPN
        vpn_status_color = f"{Colors.GREEN}{openvpn_status_text}{Colors.END}" if "Ativo" in openvpn_status_text else f"{Colors.RED}{openvpn_status_text}{Colors.END}"
        print_menu_option("2", "Gerenciar OpenVPN", f"[ {vpn_status_color} ]", Colors.CYAN)
        
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")

        if choice == "1":
            menu_socks5()
        elif choice == "2":
            menu_openvpn()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

def menu_usuarios():
    while True:
        clear_screen()
        
        print_colored_box("GERENCIAR USUÁRIOS")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Criar Usuário", color=Colors.CYAN)
        print_menu_option("2", "Remover Usuário", color=Colors.CYAN)
        print_menu_option("3", "Alterar Senha", color=Colors.CYAN)
        print_menu_option("4", "Alterar Data de Expiração", color=Colors.CYAN)
        print_menu_option("5", "Alterar Limite de Conexões", color=Colors.CYAN)
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")

        if choice == "1":
            criar_usuario()
        elif choice == "2":
            remover_usuario()
        elif choice == "3":
            alterar_senha()
        elif choice == "4":
            alterar_data_expiracao()
        elif choice == "5":
            alterar_limite_conexoes()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

def menu_bloqueio_sites():
    while True:
        clear_screen()
        
        print_colored_box("BLOQUEIO DE SITES")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Bloquear Sites de Pornografia", color=Colors.CYAN)
        print_menu_option("2", "Bloquear Site Específico (por domínio)", color=Colors.CYAN)
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")
        
        if choice == "1":
            bloquear_site_pornografia()
        elif choice == "2":
            bloquear_site_personalizado()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")
        
        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

def menu_ferramentas():
    while True:
        clear_screen()
        
        print_colored_box("FERRAMENTAS")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Alterar senha root", color=Colors.CYAN)
        print_menu_option("2", "Otimizar sistema", color=Colors.CYAN)
        print_menu_option("3", "Gerar Memoria Swap", color=Colors.CYAN)
        print_menu_option("4", "Configurar Zram", color=Colors.CYAN)
        print_menu_option("5", "Bloquear sites", color=Colors.CYAN)
        print_menu_option("6", "Proteção Anti-DDoS", color=Colors.CYAN)
        print_menu_option("0", "Voltar", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")
        
        if choice == "1":
            alterar_senha_root()
        elif choice == "2":
            otimizar_sistema()
        elif choice == "3":
            gerar_memoria_swap()
        elif choice == "4":
            configurar_zram()
        elif choice == "5":
            menu_bloqueio_sites()
        elif choice == "6":
            bloquear_ddos()
        elif choice == "0":
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")
        
        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

def main_menu():
    while True:
        clear_screen()
        
        # Banner do MULTIFLOW
        banner = f"""
{Colors.BOLD}{Colors.CYAN}███╗   ███╗██╗   ██╗██╗  ████████╗██╗███████╗██╗      ██████╗ ██╗    ██╗
████╗ ████║██║   ██║██║  ╚══██╔══╝██║██╔════╝██║     ██╔═══██╗██║    ██║
██╔████╔██║██║   ██║██║     ██║   ██║█████╗  ██║     ██║   ██║██║ █╗ ██║
██║╚██╔╝██║██║   ██║██║     ██║   ██║██╔══╝  ██║     ██║   ██║██║███╗██║
██║ ╚═╝ ██║╚██████╔╝███████╗██║   ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{Colors.END}
        """
        print(banner)
        
        # Exibir o painel de informações do sistema
        show_system_panel()
        
        # Menu principal
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Gerenciar Usuários", color=Colors.CYAN)
        print_menu_option("2", "Gerenciar Conexões", color=Colors.CYAN)
        print_menu_option("3", "Remover Completamente Multiflow", color=Colors.RED)
        print_menu_option("4", "Ferramentas", color=Colors.CYAN)
        print_menu_option("0", "Sair", color=Colors.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{Colors.BOLD}Escolha uma opção: {Colors.END}")

        if choice == "1":
            menu_usuarios()
        elif choice == "2":
            menu_conexoes()
        elif choice == "3":
            uninstall_multiflow()
        elif choice == "4":
            menu_ferramentas()
        elif choice == "0":
            clear_screen()
            print(f"\n{Colors.GREEN}Obrigado por usar o Multiflow!{Colors.END}")
            print(f"{Colors.CYAN}Saindo...{Colors.END}")
            break
        else:
            print(f"{Colors.RED}Opção inválida!{Colors.END}")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.END}")

if __name__ == "__main__":
    main_menu()
