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

# Instanciando cores
COLORS = Colors()

# Caracteres para bordas
class BoxChars:
    """Caracteres Unicode para desenhar bordas."""
    if supports_color():
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
    else:
        # Fallback para terminais que não suportam caracteres Unicode
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
    """Verifica se todos os módulos necessários estão instalados."""
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
    # Importando o módulo personalizado ssh_user_manager
    try:
        from ssh_user_manager import criar_usuario, remover_usuario, alterar_senha, alterar_data_expiracao, alterar_limite_conexoes
    except ImportError:
        print(f"{COLORS.RED}Erro: Módulo ssh_user_manager não encontrado.{COLORS.END}")
        print(f"{COLORS.YELLOW}Certifique-se de que o arquivo ssh_user_manager.py está no mesmo diretório.{COLORS.END}")
        sys.exit(1)
else:
    print(f"{COLORS.RED}Saindo devido a dependências ausentes.{COLORS.END}")
    sys.exit(1)

# Função para calcular o comprimento visível (ignorando códigos ANSI)
def visible_length(text):
    """Calcula o comprimento visível de uma string, ignorando códigos ANSI."""
    # Remove códigos ANSI de cor
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    return len(clean_text)

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

def print_colored_box(title, content_lines=None, width=60, title_color=COLORS.CYAN):
    """Imprime uma caixa colorida com título e conteúdo."""
    if content_lines is None:
        content_lines = []
    
    # Título da caixa
    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
    
    # Título centralizado
    title_text = f" {title_color}{COLORS.BOLD}{title}{COLORS.END} "
    visible_title_len = visible_length(title_text)
    padding = width - visible_title_len - 2
    left_padding = padding // 2
    right_padding = padding - left_padding
    print(f"{BoxChars.VERTICAL}{' ' * left_padding}{title_text}{' ' * right_padding}{BoxChars.VERTICAL}")
    
    if content_lines:
        # Linha separadora
        print(f"{BoxChars.T_RIGHT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.T_LEFT}")
        
        # Conteúdo
        for line in content_lines:
            # Garantir que a linha tenha exatamente o tamanho correto
            visible_line_len = visible_length(line)
            if visible_line_len > width - 4:
                # Truncar o texto visível, não os códigos ANSI
                truncate_len = width - 7  # -7 para espaço, reticências e margens
                visible_chars = 0
                truncated = ""
                for char in line:
                    if re.match(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', char):
                        truncated += char  # Manter códigos ANSI
                    else:
                        if visible_chars < truncate_len:
                            truncated += char
                            visible_chars += 1
                line = truncated + "..."
            
            padding = width - visible_length(line) - 2
            print(f"{BoxChars.VERTICAL} {line}{' ' * padding}{BoxChars.VERTICAL}")
    
    # Base da caixa
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")

def print_menu_option(number, description, status=None, color=COLORS.WHITE):
    """Formata uma opção de menu com possível status."""
    width = 58
    number_text = f"{COLORS.BOLD}{color}[{number}]{COLORS.END}"
    
    if status:
        status_text = f"{status}"
        # Calcular espaço para descrição usando comprimento visível
        desc_space = width - visible_length(f" {number_text} ") - visible_length(status_text) - 2
        
        # Truncar descrição se necessário
        if visible_length(description) > desc_space:
            visible_chars = 0
            truncated = ""
            for char in description:
                if visible_chars < desc_space - 3:
                    truncated += char
                    if not re.match(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', char):
                        visible_chars += 1
            description = truncated + "..."
        
        option_text = f" {number_text} {description}"
        padding = width - visible_length(option_text) - visible_length(status_text)
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{status_text} {BoxChars.VERTICAL}")
    else:
        option_text = f" {number_text} {description}"
        padding = width - visible_length(option_text)
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{BoxChars.VERTICAL}")

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_colored_box("AVISO", [
            f"{COLORS.RED}Este script precisa ser executado como root para a maioria das funcionalidades.{COLORS.END}",
            f"{COLORS.YELLOW}Algumas operações podem falhar sem privilégios adequados.{COLORS.END}"
        ])
        
        confirm = input(f"{COLORS.BOLD}Deseja continuar mesmo assim? (s/n): {COLORS.END}")
        if confirm.lower() != 's':
            print(f"{COLORS.GREEN}Saindo...{COLORS.END}")
            sys.exit(0)
        return False
    return True

def run_command(cmd, sudo=False):
    """Executa um comando via subprocess, com opção de sudo."""
    if sudo:
        cmd = ["sudo"] + cmd
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        print(result)
        return True
    except subprocess.CalledProcessError as e:
        print(f"{COLORS.RED}Erro ao executar {' '.join(cmd)}: {e.output}{COLORS.END}")
        return False
    except Exception as e:
        print(f"{COLORS.RED}Exceção inesperada: {e}{COLORS.END}")
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
            return COLORS.GREEN
        elif percent < 80:
            return COLORS.YELLOW
        else:
            return COLORS.RED
    
    ram_color = get_color_code(info["ram_percent"])
    cpu_color = get_color_code(info["cpu_percent"])
    
    # Construir o painel
    content_lines = [
        f"{COLORS.BOLD}OS:{COLORS.END} {COLORS.WHITE}{info['os_name']}{COLORS.END}",
        f"{COLORS.BOLD}RAM:{COLORS.END} {ram_color}{info['ram_percent']:>5.1f}%{COLORS.END}  |  {COLORS.BOLD}CPU:{COLORS.END} {cpu_color}{info['cpu_percent']:>5.1f}%{COLORS.END}"
    ]
    
    print_colored_box("INFORMAÇÕES DO SISTEMA", content_lines)

# Função principal com menu modificado - ALTERAÇÃO 1
def main_menu():
    # Verificar se o script está sendo executado como root
    is_root = check_root()
    
    while True:
        clear_screen()
        
        # Banner do MULTIFLOW
        banner = f"""
{COLORS.BOLD}{COLORS.CYAN}███╗   ███╗██╗   ██╗██╗  ████████╗██╗███████╗██╗      ██████╗ ██╗    ██╗
████╗ ████║██║   ██║██║  ╚══██╔══╝██║██╔════╝██║     ██╔═══██╗██║    ██║
██╔████╔██║██║   ██║██║     ██║   ██║█████╗  ██║     ██║   ██║██║ █╗ ██║
██║╚██╔╝██║██║   ██║██║     ██║   ██║██╔══╝  ██║     ██║   ██║██║███╗██║
██║ ╚═╝ ██║╚██████╔╝███████╗██║   ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{COLORS.END}
        """
        print(banner)
        
        # Exibir o painel de informações do sistema
        show_system_panel()
        
        # Menu principal com opções 3 e 4 invertidas
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Gerenciar Usuários", color=COLORS.CYAN)
        print_menu_option("2", "Gerenciar Conexões", color=COLORS.CYAN)
        print_menu_option("3", "Ferramentas", color=COLORS.CYAN)  # Modificado: era opção 4
        print_menu_option("4", "Remover Completamente Multiflow", color=COLORS.RED)  # Modificado: era opção 3
        print_menu_option("0", "Sair", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        # Adicionar aviso se não está executando como root
        if not is_root:
            print(f"\n{COLORS.YELLOW}⚠️  Aviso: Executando sem privilégios de root. Algumas funções podem não funcionar.{COLORS.END}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        if choice == "1":
            menu_usuarios()
        elif choice == "2":
            menu_conexoes()
        elif choice == "3":
            menu_ferramentas()  # Modificado: era opção 4
        elif choice == "4":
            uninstall_multiflow()  # Modificado: era opção 3
        elif choice == "0":
            clear_screen()
            print(f"\n{COLORS.GREEN}Obrigado por usar o Multiflow!{COLORS.END}")
            print(f"{COLORS.CYAN}Saindo...{COLORS.END}")
            break
        else:
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

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
        print(f"{COLORS.RED}Erro ao verificar status do OpenVPN: {e}{COLORS.END}")
    
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
            print(f"{COLORS.GREEN}{package_name} instalado com sucesso!{COLORS.END}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao instalar {package_name}: {e}{COLORS.END}")
            return False
    return True

def install_socks5():
    print_colored_box("INSTALANDO SOCKS5")
    print("Instalando SOCKS5 e todas as dependências necessárias...")
    if not check_and_install_package("psutil"):
        print(f"{COLORS.RED}Falha ao instalar dependências Python. Continue manualmente.{COLORS.END}")
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
            print(f"{COLORS.RED}Erro ao instalar dependências do sistema: {e}{COLORS.END}")
            return False
    else:
        print(f"{COLORS.RED}Instalação automática suportada apenas no Linux. Instale manualmente para {sys.platform}.{COLORS.END}")
        return False

    if not os.path.exists("src/socks5_server.cpp"):
        print(f"{COLORS.RED}Erro: src/socks5_server.cpp não encontrado!{COLORS.END}")
        return False

    try:
        print("Compilando o servidor SOCKS5...")
        subprocess.check_call([
            "g++", "-o", "socks5_server", "src/socks5_server.cpp",
            "-lboost_system", "-lboost_log", "-lboost_thread", "-lpthread", "-lssh2", "-std=c++14"
        ])
        print(f"{COLORS.GREEN}SOCKS5 instalado com sucesso!{COLORS.END}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{COLORS.RED}Erro na compilação: {e}{COLORS.END}")
        return False

def add_port_socks5():
    print_colored_box("ADICIONAR PORTA SOCKS5")
    port = input(f"{COLORS.CYAN}Digite a porta desejada (1-65535): {COLORS.END}")
    try:
        port = int(port)
        if port < 1 or port > 65535:
            print(f"{COLORS.RED}Porta inválida!{COLORS.END}")
            return
    except ValueError:
        print(f"{COLORS.RED}Entrada inválida!{COLORS.END}")
        return

    if port in socks5_processes:
        print(f"{COLORS.RED}Porta {port} já em uso!{COLORS.END}")
        return

    if not os.path.exists("socks5_server"):
        print(f"{COLORS.RED}Erro: Servidor não compilado!{COLORS.END}")
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
            print(f"{COLORS.GREEN}SOCKS5 iniciado na porta {port}.{COLORS.END}")
        else:
            print(f"{COLORS.RED}Erro ao iniciar na porta {port}.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro: {e}{COLORS.END}")

def remove_port_socks5():
    print_colored_box("REMOVER PORTA SOCKS5")
    port = input(f"{COLORS.CYAN}Digite a porta a ser removida: {COLORS.END}")
    try:
        port = int(port)
        if port not in socks5_processes:
            print(f"{COLORS.RED}Nenhum SOCKS5 na porta {port}!{COLORS.END}")
            return
    except ValueError:
        print(f"{COLORS.RED}Entrada inválida!{COLORS.END}")
        return

    process = socks5_processes[port]
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        del socks5_processes[port]
        print(f"{COLORS.GREEN}SOCKS5 removido da porta {port}.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro: {e}{COLORS.END}")

def remove_socks5():
    print_colored_box("REMOVER SOCKS5")
    print("Removendo SOCKS5...")
    for port, process in list(socks5_processes.items()):
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
            print(f"Encerrado na porta {port}.")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao encerrar na porta {port}: {e}{COLORS.END}")
    socks5_processes.clear()

    if os.path.exists("socks5_server"):
        try:
            os.remove("socks5_server")
            print("Binário removido.")
        except Exception as e:
            print(f"{COLORS.RED}Erro: {e}{COLORS.END}")
    else:
        print("Nenhum binário encontrado.")
    print(f"{COLORS.GREEN}SOCKS5 removido com sucesso.{COLORS.END}")

def menu_socks5():
    while True:
        clear_screen()
        
        # Verificar status atual
        socks_status, _ = check_services_status()
        
        # Título e status
        status_color = COLORS.GREEN if "Ativo" in socks_status else COLORS.RED
        content_lines = [f"{COLORS.BOLD}Status:{COLORS.END} {status_color}{socks_status}{COLORS.END}"]
        print_colored_box("GERENCIAR SOCKS5", content_lines)
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Instalar SOCKS5", color=COLORS.CYAN)
        print_menu_option("2", "Adicionar Porta", color=COLORS.CYAN)
        print_menu_option("3", "Remover Porta", color=COLORS.CYAN)
        print_menu_option("4", "Remover SOCKS5", color=COLORS.CYAN)
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

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
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

# Funções para OpenVPN
def install_openvpn():
    print_colored_box("INSTALANDO OPENVPN")
    
    if sys.platform != "linux":
        print(f"{COLORS.RED}Instalação suportada apenas no Linux.{COLORS.END}")
        return

    if not install_dependencies_openvpn():
        return

    if not clone_repo_openvpn():
        return

    if not build_and_install_openvpn():
        return

    if not generate_certificates_openvpn():
        return

    port, proto = select_port_and_proto_openvpn()
    dns = select_dns_openvpn()
    generate_config_openvpn(port, proto, dns)
    
    # Atualizar status global
    openvpn_status["port"] = port
    openvpn_status["proto"] = proto

    print(f"{COLORS.GREEN}OpenVPN instalado! Inicie com 'sudo openvpn server.conf'.{COLORS.END}")

def start_openvpn():
    """Inicia o serviço OpenVPN."""
    print_colored_box("INICIANDO OPENVPN")
    
    if openvpn_status["active"]:
        print(f"{COLORS.YELLOW}OpenVPN já está ativo na porta {openvpn_status['port']}.{COLORS.END}")
        return

    print("Iniciando OpenVPN...")
    if os.path.exists("server.conf"):
        try:
            # Ler a porta do arquivo de configuração
            port = None
            with open("server.conf", "r") as f:
                for line in f:
                    if line.strip().startswith("port "):
                        port = line.strip().split()[1]
                        break
            
            # Iniciar o OpenVPN em background
            subprocess.Popen(["sudo", "openvpn", "--config", "server.conf", "--daemon"], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
            
            # Atualizar status
            openvpn_status["active"] = True
            openvpn_status["port"] = port
            
            print(f"{COLORS.GREEN}OpenVPN iniciado na porta {port}.{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao iniciar OpenVPN: {e}{COLORS.END}")
    else:
        print(f"{COLORS.RED}Arquivo de configuração server.conf não encontrado.{COLORS.END}")
        print(f"{COLORS.YELLOW}Execute a instalação do OpenVPN primeiro.{COLORS.END}")

def stop_openvpn():
    """Para o serviço OpenVPN."""
    print_colored_box("PARANDO OPENVPN")
    
    if not openvpn_status["active"]:
        print(f"{COLORS.YELLOW}OpenVPN não está ativo.{COLORS.END}")
        return

    print("Parando OpenVPN...")
    try:
        # Encontrar e matar processos OpenVPN
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'openvpn' in proc.info['name'].lower() or any('openvpn' in cmd.lower() for cmd in proc.info['cmdline'] if cmd):
                try:
                    os.kill(proc.info['pid'], signal.SIGTERM)
                    print(f"Processo OpenVPN (PID {proc.info['pid']}) encerrado.")
                except Exception as e:
                    print(f"{COLORS.RED}Erro ao encerrar processo OpenVPN (PID {proc.info['pid']}): {e}{COLORS.END}")
        
        # Resetar status
        openvpn_status["active"] = False
        openvpn_status["port"] = None
        
        print(f"{COLORS.GREEN}OpenVPN parado.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao parar OpenVPN: {e}{COLORS.END}")

def install_dependencies_openvpn():
    print("Instalando dependências para OpenVPN...")
    deps = [
        "git", "build-essential", "autoconf", "automake", "libtool", "pkg-config",
        "libssl-dev", "liblz4-dev", "liblzo2-dev", "libpam0g-dev", "libcap-ng-dev",
        "easy-rsa"
    ]
    if not run_command(["apt", "update"], sudo=True):
        return False
    for dep in deps:
        if not run_command(["apt", "install", "-y", dep], sudo=True):
            return False
    return True

def clone_repo_openvpn():
    repo_url = "https://github.com/OpenVPN/openvpn.git"
    clone_dir = "openvpn_source"
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)
    if not run_command(["git", "clone", repo_url, clone_dir]):
        return False
    os.chdir(clone_dir)
    return True

def build_and_install_openvpn():
    if not run_command(["autoreconf", "-i", "-v", "-f"]):
        return False
    if not run_command(["./configure"]):
        return False
    if not run_command(["make"]):
        return False
    if not run_command(["make", "install"], sudo=True):
        return False
    os.chdir("..")
    return True

def generate_certificates_openvpn():
    keys_dir = "keys"
    if os.path.exists(keys_dir):
        shutil.rmtree(keys_dir)
    os.mkdir(keys_dir)

    try:
        easy_rsa_dir = "/usr/share/easy-rsa"
        local_easy_rsa = os.path.join(keys_dir, "easy-rsa")
        shutil.copytree(easy_rsa_dir, local_easy_rsa)
        os.chdir(local_easy_rsa)
        run_command(["./easyrsa", "init-pki"])
        run_command(["./easyrsa", "build-ca", "nopass"])
        run_command(["./easyrsa", "build-server-full", "server", "nopass"])
        run_command(["./easyrsa", "build-client-full", "client", "nopass"])
        run_command(["./easyrsa", "gen-dh"])
        files_to_copy = ["pki/ca.crt", "pki/issued/server.crt", "pki/private/server.key",
                         "pki/issued/client.crt", "pki/private/client.key", "pki/dh.pem"]
        for file in files_to_copy:
            shutil.copy(file, os.path.join("..", ".."))
        os.chdir("../..")
        print(f"{COLORS.GREEN}Certificados gerados em keys/.{COLORS.END}")
        return True
    except Exception as e:
        print(f"{COLORS.RED}Erro: {e}{COLORS.END}")
        return False

def select_port_and_proto_openvpn():
    port = input(f"{COLORS.CYAN}Porta desejada (default 1194): {COLORS.END}") or "1194"
    proto = input(f"{COLORS.CYAN}Protocolo (1 TCP, 2 UDP, default TCP): {COLORS.END}") or "1"
    proto = "tcp" if proto == "1" else "udp"
    return port, proto

def select_dns_openvpn():
    print(f"{COLORS.BOLD}DNS:{COLORS.END}")
    print(f"1. Google (8.8.8.8)")
    print(f"2. Cloudflare (1.1.1.1)")
    print(f"3. OpenDNS (208.67.222.222)")
    choice = input(f"{COLORS.CYAN}Opção (default 1): {COLORS.END}") or "1"
    if choice == "1":
        return "8.8.8.8"
    elif choice == "2":
        return "1.1.1.1"
    elif choice == "3":
        return "208.67.222.222"
    return "8.8.8.8"

def generate_config_openvpn(port, proto, dns):
    config_content = f"""
port {port}
proto {proto}
dev tun
ca keys/ca.crt
cert keys/server.crt
key keys/server.key
dh keys/dh.pem
server 10.8.0.0 255.255.255.0
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS {dns}"
keepalive 10 120
cipher AES-256-CBC
persist-key
persist-tun
status openvpn-status.log
verb 3
"""
    with open("server.conf", "w") as f:
        f.write(config_content)
    print(f"{COLORS.GREEN}Config gerada em server.conf.{COLORS.END}")

def remove_openvpn():
    print_colored_box("REMOVENDO OPENVPN")
    print("Removendo OpenVPN...")
    run_command(["apt", "purge", "-y", "openvpn"], sudo=True)
    run_command(["rm", "-rf", "/etc/openvpn"], sudo=True)
    run_command(["rm", "-f", "/usr/local/sbin/openvpn"], sudo=True)
    if os.path.exists("openvpn_source"):
        shutil.rmtree("openvpn_source")
    if os.path.exists("keys"):
        shutil.rmtree("keys")
    if os.path.exists("server.conf"):
        os.remove("server.conf")
    
    # Resetar status
    openvpn_status["active"] = False
    openvpn_status["port"] = None
    
    print(f"{COLORS.GREEN}OpenVPN removido.{COLORS.END}")

def menu_openvpn():
    while True:
        clear_screen()
        
        # Verificar status atual
        _, openvpn_status_text = check_services_status()
        
        # Título e status
        status_color = COLORS.GREEN if "Ativo" in openvpn_status_text else COLORS.RED
        content_lines = [f"{COLORS.BOLD}Status:{COLORS.END} {status_color}{openvpn_status_text}{COLORS.END}"]
        print_colored_box("GERENCIAR OPENVPN", content_lines)
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Instalar OpenVPN", color=COLORS.CYAN)
        print_menu_option("2", "Remover OpenVPN", color=COLORS.CYAN)
        
        if openvpn_status["active"]:
            print_menu_option("3", "Parar OpenVPN", color=COLORS.CYAN)
        else:
            print_menu_option("3", "Iniciar OpenVPN", color=COLORS.CYAN)
        
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        if choice == "1":
            install_openvpn()
        elif choice == "2":
            if openvpn_status["active"]:
                print(f"{COLORS.RED}O OpenVPN está em execução. Pare o serviço antes de removê-lo.{COLORS.END}")
                input(f"{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
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
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

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
        socks_status_color = f"{COLORS.GREEN}{socks_status}{COLORS.END}" if "Ativo" in socks_status else f"{COLORS.RED}{socks_status}{COLORS.END}"
        print_menu_option("1", "Gerenciar SOCKS5", f"[ {socks_status_color} ]", COLORS.CYAN)
        
        # Status colorido para OpenVPN
        vpn_status_color = f"{COLORS.GREEN}{openvpn_status_text}{COLORS.END}" if "Ativo" in openvpn_status_text else f"{COLORS.RED}{openvpn_status_text}{COLORS.END}"
        print_menu_option("2", "Gerenciar OpenVPN", f"[ {vpn_status_color} ]", COLORS.CYAN)
        
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        if choice == "1":
            menu_socks5()
        elif choice == "2":
            menu_openvpn()
        elif choice == "0":
            break
        else:
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

def menu_usuarios():
    while True:
        clear_screen()
        
        print_colored_box("GERENCIAR USUÁRIOS")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Criar Usuário", color=COLORS.CYAN)
        print_menu_option("2", "Remover Usuário", color=COLORS.CYAN)
        print_menu_option("3", "Alterar Senha", color=COLORS.CYAN)
        print_menu_option("4", "Alterar Data de Expiração", color=COLORS.CYAN)
        print_menu_option("5", "Alterar Limite de Conexões", color=COLORS.CYAN)
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

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
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

def menu_ferramentas():
    while True:
        clear_screen()
        
        print_colored_box("FERRAMENTAS")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Alterar senha root", color=COLORS.CYAN)
        print_menu_option("2", "Otimizar sistema", color=COLORS.CYAN)
        print_menu_option("3", "Gerar Memoria Swap", color=COLORS.CYAN)
        print_menu_option("4", "Configurar Zram", color=COLORS.CYAN)
        print_menu_option("5", "Bloquear sites", color=COLORS.CYAN)
        print_menu_option("6", "Proteção Anti-DDoS", color=COLORS.CYAN)
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")
        
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
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

# Função de desinstalação revisada - ALTERAÇÃO 2
def uninstall_multiflow():
    """Remove completamente o multiflow e todas as alterações feitas."""
    clear_screen()
    
    print_colored_box("REMOVER COMPLETAMENTE MULTIFLOW", title_color=COLORS.RED)
    
    # Verificar permissões de root (adicionado)
    if os.geteuid() != 0:
        print_colored_box("ERRO", [
            f"{COLORS.RED}Esta operação precisa ser executada como root/sudo.{COLORS.END}",
            f"{COLORS.YELLOW}Execute novamente com privilégios de administrador.{COLORS.END}"
        ], title_color=COLORS.RED)
        input(f"\n{COLORS.BOLD}Pressione Enter para voltar ao menu principal...{COLORS.END}")
        return
    
    # Verificar processos em execução (adicionado)
    processes_running = False
    if socks5_processes:
        processes_running = True
        print(f"{COLORS.YELLOW}⚠️  Serviços SOCKS5 ainda em execução nas portas: {', '.join(str(porta) for porta in socks5_processes.keys())}{COLORS.END}")
    
    if openvpn_status["active"]:
        processes_running = True
        print(f"{COLORS.YELLOW}⚠️  Serviço OpenVPN ainda em execução na porta {openvpn_status['port']}{COLORS.END}")
    
    if processes_running:
        print(f"\n{COLORS.YELLOW}Serviços serão automaticamente encerrados durante o processo de remoção.{COLORS.END}")
    
    content_lines = [
        f"{COLORS.YELLOW}Esta operação irá remover TODAS as alterações feitas pelo Multiflow:{COLORS.END}",
        f"- Remover todos os serviços SOCKS5 e OpenVPN",
        f"- Excluir todos os arquivos de instalação",
        f"- Remover links simbólicos e scripts",
        f"- Remover o diretório de instalação (/opt/multiflow)"
    ]
    
    # Imprimir aviso
    width = 60
    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
    for line in content_lines:
        line_visible_length = visible_length(line)
        padding = width - line_visible_length - 2
        print(f"{BoxChars.VERTICAL} {line}{' ' * padding}{BoxChars.VERTICAL}")
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
    
    # Opção de criar backup final (adicionado)
    backup_criado = False
    install_dir = "/opt/multiflow"
    if os.path.exists(install_dir):
        backup_choice = input(f"\n{COLORS.BOLD}Deseja criar um backup final antes de remover? (s/n): {COLORS.END}")
        if backup_choice.lower() == 's':
            backup_time = time.strftime("%Y%m%d%H%M%S")
            backup_dir = f"/opt/multiflow.bak.{backup_time}"
            try:
                shutil.copytree(install_dir, backup_dir)
                print(f"{COLORS.GREEN}✓ Backup criado em {backup_dir}{COLORS.END}")
                backup_criado = True
            except Exception as e:
                print(f"{COLORS.RED}Erro ao criar backup: {e}{COLORS.END}")
                proceed = input(f"{COLORS.BOLD}Continuar mesmo assim? (s/n): {COLORS.END}")
                if proceed.lower() != 's':
                    print(f"{COLORS.GREEN}Operação cancelada.{COLORS.END}")
                    return
    
    confirmation = input(f"\n{COLORS.BOLD}{COLORS.RED}Esta ação é irreversível. Digite 'REMOVER' para confirmar: {COLORS.END}")
    
    if confirmation != "REMOVER":
        print(f"{COLORS.GREEN}Operação cancelada.{COLORS.END}")
        return
    
    print(f"\n{COLORS.BOLD}Iniciando remoção completa...{COLORS.END}")
    
    # Criar arquivo de log (adicionado)
    log_file = f"/tmp/multiflow_uninstall_{time.strftime('%Y%m%d%H%M%S')}.log"
    try:
        with open(log_file, "w") as f:
            f.write(f"Log de desinstalação do Multiflow - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            if backup_criado:
                f.write(f"Backup criado em: {backup_dir}\n")
            f.write("----------------------------------------\n\n")
    except Exception as e:
        print(f"{COLORS.YELLOW}Não foi possível criar arquivo de log: {e}{COLORS.END}")
    
    def log_action(message, success=True):
        """Registra ações no log e exibe feedback visual."""
        if success:
            status = f"{COLORS.GREEN}✓{COLORS.END}"
        else:
            status = f"{COLORS.RED}✗{COLORS.END}"
        
        print(f"{status} {message}")
        
        try:
            with open(log_file, "a") as f:
                result = "SUCESSO" if success else "FALHA"
                f.write(f"[{result}] {message}\n")
        except:
            pass
    
    # 1. Parar e remover todos os serviços SOCKS5 (aprimorado)
    print(f"\n{COLORS.BOLD}1. Removendo serviços SOCKS5...{COLORS.END}")
    try:
        if socks5_processes:
            ports = list(socks5_processes.keys())
            remove_socks5()
            log_action(f"Serviços SOCKS5 nas portas {', '.join(str(p) for p in ports)} removidos")
        else:
            log_action("Nenhum serviço SOCKS5 encontrado em execução")
    except Exception as e:
        log_action(f"Erro ao remover serviços SOCKS5: {e}", success=False)
    
    # 2. Parar e remover OpenVPN (aprimorado)
    print(f"\n{COLORS.BOLD}2. Removendo OpenVPN...{COLORS.END}")
    try:
        if openvpn_status["active"]:
            port = openvpn_status["port"]
            stop_openvpn()
            log_action(f"Serviço OpenVPN na porta {port} parado")
        else:
            log_action("OpenVPN não está em execução")
        
        remove_openvpn()
        log_action("Arquivos e configurações do OpenVPN removidos")
    except Exception as e:
        log_action(f"Erro ao remover OpenVPN: {e}", success=False)
    
    # 3. Remover link simbólico (aprimorado)
    print(f"\n{COLORS.BOLD}3. Removendo links simbólicos...{COLORS.END}")
    symlinks = ["/usr/local/bin/multiflow", "/usr/bin/multiflow"]
    for link in symlinks:
        try:
            if os.path.exists(link) or os.path.islink(link):
                os.remove(link)
                log_action(f"Link simbólico {link} removido")
            else:
                log_action(f"Link simbólico {link} não encontrado")
        except Exception as e:
            log_action(f"Erro ao remover link simbólico {link}: {e}", success=False)
    
    # 4. Remover diretório de instalação (aprimorado)
    print(f"\n{COLORS.BOLD}4. Removendo diretório de instalação...{COLORS.END}")
    try:
        install_dir = "/opt/multiflow"
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
            log_action(f"Diretório {install_dir} removido com sucesso")
        else:
            log_action(f"Diretório {install_dir} não encontrado")
    except Exception as e:
        log_action(f"Erro ao remover diretório de instalação: {e}", success=False)
    
    # 5. Limpar arquivos temporários (aprimorado)
    print(f"\n{COLORS.BOLD}5. Limpando arquivos temporários...{COLORS.END}")
    temp_files = ["server.conf", "openvpn_source", "keys", "socks5_server", "multiflow_wrapper.sh"]
    for file in temp_files:
        try:
            if os.path.exists(file):
                if os.path.isdir(file):
                    shutil.rmtree(file)
                    log_action(f"Diretório {file} removido")
                else:
                    os.remove(file)
                    log_action(f"Arquivo {file} removido")
        except Exception as e:
            log_action(f"Erro ao remover {file}: {e}", success=False)
    
    # 6. Verificar e remover backups (aprimorado)
    print(f"\n{COLORS.BOLD}6. Verificando backups...{COLORS.END}")
    try:
        backup_dirs = [d for d in os.listdir("/opt") if d.startswith("multiflow.bak")]
        if backup_dirs:
            print(f"Encontrados {len(backup_dirs)} backups:")
            for i, backup in enumerate(backup_dirs, 1):
                backup_path = os.path.join("/opt", backup)
                backup_time = backup.split(".")[-1] if len(backup.split(".")) > 2 else "Desconhecida"
                try:
                    size = sum(os.path.getsize(os.path.join(dirpath, filename)) 
                               for dirpath, _, filenames in os.walk(backup_path) 
                               for filename in filenames)
                    size_mb = size / (1024 * 1024)
                    print(f"  {i}. {backup} (Data: {backup_time}, Tamanho: {size_mb:.2f} MB)")
                except:
                    print(f"  {i}. {backup} (Data: {backup_time})")
            
            remove_backups = input(f"\n{COLORS.BOLD}Deseja remover os backups? (s/n/selecionar): {COLORS.END}")
            
            if remove_backups.lower() == 's':
                for backup in backup_dirs:
                    backup_path = os.path.join("/opt", backup)
                    try:
                        shutil.rmtree(backup_path)
                        log_action(f"Backup {backup} removido")
                    except Exception as e:
                        log_action(f"Erro ao remover backup {backup}: {e}", success=False)
            
            elif remove_backups.lower() == 'selecionar':
                indices = input(f"{COLORS.BOLD}Digite os números dos backups a remover (separados por vírgula): {COLORS.END}")
                try:
                    selected = [int(i.strip()) for i in indices.split(",") if i.strip()]
                    for idx in selected:
                        if 1 <= idx <= len(backup_dirs):
                            backup = backup_dirs[idx-1]
                            backup_path = os.path.join("/opt", backup)
                            try:
                                shutil.rmtree(backup_path)
                                log_action(f"Backup {backup} removido")
                            except Exception as e:
                                log_action(f"Erro ao remover backup {backup}: {e}", success=False)
                except Exception as e:
                    log_action(f"Erro ao processar seleção de backups: {e}", success=False)
        else:
            log_action("Nenhum backup encontrado")
    except Exception as e:
        log_action(f"Erro ao verificar backups: {e}", success=False)
    
    # Exibir informações finais (aprimorado)
    print(f"\n{COLORS.GREEN}✅ Multiflow foi completamente removido do sistema.{COLORS.END}")
    if os.path.exists(log_file):
        print(f"{COLORS.CYAN}Log detalhado da desinstalação salvo em: {log_file}{COLORS.END}")
    
    print(f"\n{COLORS.YELLOW}Para remover completamente todos os arquivos de configuração residuais,{COLORS.END}")
    print(f"{COLORS.YELLOW}você pode executar: sudo apt autoremove && sudo apt clean{COLORS.END}")
    
    print(f"\n{COLORS.CYAN}Obrigado por usar o Multiflow!{COLORS.END}")
    
    input(f"\n{COLORS.BOLD}Pressione Enter para voltar ao menu principal...{COLORS.END}")

# O restante do script permanece inalterado...

if __name__ == "__main__":
    main_menu()
