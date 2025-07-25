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

# Novas funções de ferramentas
def alterar_senha_root():
    print_colored_box("ALTERAR SENHA DO ROOT")
    print("Esta operação irá alterar a senha do usuário root")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    import getpass
    
    # Solicitar nova senha
    nova_senha = getpass.getpass(f"{COLORS.CYAN}Digite a nova senha para root: {COLORS.END}")
    confirm_senha = getpass.getpass(f"{COLORS.CYAN}Confirme a nova senha: {COLORS.END}")
    
    if nova_senha != confirm_senha:
        print(f"{COLORS.RED}As senhas não coincidem!{COLORS.END}")
        return
    
    if len(nova_senha) < 6:
        print(f"{COLORS.RED}A senha deve ter pelo menos 6 caracteres!{COLORS.END}")
        return
    
    # Alterar a senha
    try:
        process = subprocess.Popen(
            ["passwd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process.stdin.write(f"{nova_senha}\n{nova_senha}\n")
        process.stdin.flush()
        process.wait()
        
        if process.returncode == 0:
            print(f"{COLORS.GREEN}Senha do root alterada com sucesso!{COLORS.END}")
        else:
            print(f"{COLORS.RED}Erro ao alterar senha do root. Código de retorno: {process.returncode}{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao alterar senha: {e}{COLORS.END}")

def otimizar_sistema():
    print_colored_box("OTIMIZANDO SISTEMA")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    print("Iniciando otimização do sistema...")
    
    # 1. Atualizar o sistema
    print(f"\n{COLORS.BOLD}1. Atualizando repositórios...{COLORS.END}")
    run_command(["apt", "update"], sudo=True)
    
    # 2. Remover pacotes desnecessários
    print(f"\n{COLORS.BOLD}2. Removendo pacotes desnecessários...{COLORS.END}")
    run_command(["apt", "autoremove", "-y"], sudo=True)
    run_command(["apt", "clean"], sudo=True)
    
    # 3. Limpar o cache de pacotes
    print(f"\n{COLORS.BOLD}3. Limpando cache de pacotes...{COLORS.END}")
    run_command(["apt-get", "clean"], sudo=True)
    
    # 4. Otimizar uso de memória
    print(f"\n{COLORS.BOLD}4. Otimizando uso de memória...{COLORS.END}")
    
    # Ajustar swappiness - versão corrigida com melhor tratamento de erros
    try:
        # Método seguro usando sysctl
        run_command(["sysctl", "-w", "vm.swappiness=10"], sudo=True)
    except Exception:
        try:
            # Método alternativo
            with open("/proc/sys/vm/swappiness", "w") as f:
                f.write("10")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao ajustar swappiness: {e}{COLORS.END}")
    
    # Configurar para persistir após reinicialização
    sysctl_file = "/etc/sysctl.conf"
    sysctl_content = ""
    
    try:
        if os.path.exists(sysctl_file):
            with open(sysctl_file, "r") as f:
                sysctl_content = f.read()
        
        if "vm.swappiness" in sysctl_content:
            # Substitui o valor existente
            sysctl_content = re.sub(r'vm\.swappiness\s*=\s*\d+', 'vm.swappiness = 10', sysctl_content)
        else:
            # Adiciona nova configuração
            sysctl_content += "\n# Otimizado pelo Multiflow\nvm.swappiness = 10\n"
        
        with open(sysctl_file, "w") as f:
            f.write(sysctl_content)
    except Exception as e:
        print(f"{COLORS.RED}Erro ao atualizar arquivo sysctl.conf: {e}{COLORS.END}")
    
    # 5. Otimizar desempenho de rede
    print(f"\n{COLORS.BOLD}5. Otimizando desempenho de rede...{COLORS.END}")
    
    net_config = """
# Otimizado pelo Multiflow
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_congestion_control = cubic
net.ipv4.tcp_mtu_probing = 1
net.ipv4.tcp_fastopen = 3
net.core.netdev_max_backlog = 5000
"""
    
    try:
        # Adicionar configurações de rede se não existirem
        for line in net_config.strip().split('\n'):
            if line.startswith('#') or not line.strip():
                continue
            
            key = line.split('=')[0].strip()
            if key not in sysctl_content:
                sysctl_content += line + "\n"
        
        with open(sysctl_file, "w") as f:
            f.write(sysctl_content)
    except Exception as e:
        print(f"{COLORS.RED}Erro ao atualizar configurações de rede: {e}{COLORS.END}")
    
    # Aplicar configurações do sysctl
    run_command(["sysctl", "-p"], sudo=True)
    
    # 6. Desativar serviços desnecessários
    print(f"\n{COLORS.BOLD}6. Verificando serviços desnecessários...{COLORS.END}")
    unnecessary_services = ["cups", "bluetooth", "avahi-daemon"]
    for service in unnecessary_services:
        try:
            # Verificar se o serviço existe
            result = subprocess.run(
                ["systemctl", "status", service],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 4:  # 4 = serviço não encontrado
                print(f"Desativando serviço {service}...")
                run_command(["systemctl", "stop", service], sudo=True)
                run_command(["systemctl", "disable", service], sudo=True)
        except Exception:
            pass
    
    print(f"\n{COLORS.GREEN}Sistema otimizado com sucesso! Recomenda-se reiniciar para aplicar todas as mudanças.{COLORS.END}")

def gerar_memoria_swap():
    print_colored_box("GERAR MEMÓRIA SWAP")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    # Verificar memória RAM disponível
    try:
        mem_info = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if ":" in line:
                    key, value = line.split(':', 1)
                    mem_info[key.strip()] = int(value.strip().split()[0])  # em KB
        
        total_mem = mem_info.get('MemTotal', 0) / 1024  # Converter para MB
        print(f"Memória RAM total: {total_mem:.0f} MB")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao verificar memória: {e}{COLORS.END}")
        total_mem = 1024  # Valor padrão de 1GB
    
    # Verificar swap existente - versão corrigida com melhor tratamento de erros
    current_swap = 0
    try:
        swap_info = subprocess.check_output(["swapon", "--show=SIZE", "--bytes"], text=True)
        if swap_info.strip():
            try:
                # Processa apenas se houver linhas após o cabeçalho
                lines = swap_info.strip().split('\n')[1:]
                if lines:
                    current_swap = sum(int(size.strip()) for size in lines) / (1024**2)
            except (ValueError, IndexError) as e:
                print(f"{COLORS.RED}Erro ao processar informações de swap: {e}{COLORS.END}")
        print(f"Swap existente: {current_swap:.0f} MB")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao verificar swap existente: {e}{COLORS.END}")
    
    if current_swap > 0:
        print(f"\n{COLORS.YELLOW}Já existe memória swap configurada no sistema.{COLORS.END}")
        choice = input(f"{COLORS.BOLD}Deseja remover a swap existente e criar uma nova? (s/n): {COLORS.END}")
        if choice.lower() != 's':
            return
        
        # Desativar swap existente
        try:
            run_command(["swapoff", "-a"], sudo=True)
        except Exception as e:
            print(f"{COLORS.RED}Erro ao desativar swap existente: {e}{COLORS.END}")
            return
        
        # Remover entradas do fstab
        fstab = "/etc/fstab"
        if os.path.exists(fstab):
            try:
                with open(fstab, "r") as f:
                    lines = f.readlines()
                
                with open(fstab, "w") as f:
                    for line in lines:
                        if "swap" not in line:
                            f.write(line)
                print("Entradas de swap removidas do fstab.")
            except Exception as e:
                print(f"{COLORS.RED}Erro ao modificar fstab: {e}{COLORS.END}")
                return
    
    # Definir tamanho recomendado da swap
    if total_mem <= 2048:  # 2GB
        recommended_swap = total_mem * 2
    elif total_mem <= 8192:  # 8GB
        recommended_swap = total_mem
    else:
        recommended_swap = 8192  # 8GB máximo
    
    print(f"\n{COLORS.GREEN}Tamanho recomendado de swap: {recommended_swap:.0f} MB{COLORS.END}")
    
    # Perguntar o tamanho desejado
    while True:
        try:
            swap_size = input(f"{COLORS.CYAN}Digite o tamanho de swap desejado em MB (padrão {recommended_swap:.0f}): {COLORS.END}")
            swap_size = int(swap_size) if swap_size else int(recommended_swap)
            if swap_size < 256:
                print(f"{COLORS.RED}O tamanho mínimo de swap é 256 MB{COLORS.END}")
            else:
                break
        except ValueError:
            print(f"{COLORS.RED}Por favor, digite um número válido{COLORS.END}")
    
    # Criar arquivo de swap
    swap_file = "/swapfile"
    print(f"\nCriando arquivo de swap de {swap_size} MB em {swap_file}...")
    
    # Garantir que o arquivo não exista
    if os.path.exists(swap_file):
        try:
            os.remove(swap_file)
        except Exception as e:
            print(f"{COLORS.RED}Erro ao remover arquivo swap existente: {e}{COLORS.END}")
            return
    
    # Criar e configurar arquivo de swap
    try:
        # Criar arquivo (dd é mais rápido para arquivos grandes)
        run_command(["dd", "if=/dev/zero", f"of={swap_file}", f"bs=1M", f"count={swap_size}"], sudo=True)
        
        # Definir permissões
        run_command(["chmod", "600", swap_file], sudo=True)
        
        # Formatar como swap
        run_command(["mkswap", swap_file], sudo=True)
        
        # Ativar swap
        run_command(["swapon", swap_file], sudo=True)
        
        # Adicionar ao fstab para persistir após reinicialização
        try:
            with open("/etc/fstab", "a") as f:
                f.write(f"\n# Swap criado pelo Multiflow\n{swap_file} none swap sw 0 0\n")
            print("Configuração adicionada ao fstab para persistência.")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao atualizar fstab: {e}{COLORS.END}")
        
        print(f"\n{COLORS.GREEN}Memória swap criada e ativada com sucesso!{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao configurar swap: {e}{COLORS.END}")

def configurar_zram():
    print_colored_box("CONFIGURAR ZRAM")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    # Verificar se o módulo zram já está carregado
    loaded = False
    try:
        lsmod_output = subprocess.check_output(["lsmod"], text=True)
        if "zram" in lsmod_output:
            loaded = True
            print(f"{COLORS.GREEN}O módulo ZRAM já está carregado.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao verificar módulos do kernel: {e}{COLORS.END}")
    
    if not loaded:
        print("Instalando e configurando ZRAM...")
        
        # Instalar o pacote zram-tools se disponível
        try:
            run_command(["apt", "install", "-y", "zram-tools"], sudo=True)
            print(f"{COLORS.GREEN}zram-tools instalado com sucesso.{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.YELLOW}Pacote zram-tools não encontrado: {e}. Configurando manualmente...{COLORS.END}")
            
            # Carregar o módulo zram
            try:
                run_command(["modprobe", "zram"], sudo=True)
                print(f"{COLORS.GREEN}Módulo zram carregado com sucesso.{COLORS.END}")
            except Exception as e:
                print(f"{COLORS.RED}Erro ao carregar módulo zram: {e}{COLORS.END}")
                return
            
            # Garantir que o módulo seja carregado na inicialização
            try:
                os.makedirs("/etc/modules-load.d", exist_ok=True)
                with open("/etc/modules-load.d/zram.conf", "w") as f:
                    f.write("zram\n")
                print("Módulo zram configurado para carregar na inicialização.")
            except Exception as e:
                print(f"{COLORS.RED}Erro ao configurar carregamento automático: {e}{COLORS.END}")
    
    # Configurar o tamanho da ZRAM
    # Verificar memória RAM disponível
    try:
        mem_info = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if ":" in line:
                    key, value = line.split(':', 1)
                    mem_info[key.strip()] = int(value.strip().split()[0])  # em KB
        
        total_mem = mem_info.get('MemTotal', 0) / 1024  # Converter para MB
        print(f"Memória RAM total: {total_mem:.0f} MB")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao verificar memória: {e}{COLORS.END}")
        total_mem = 1024  # Valor padrão de 1GB
    
    # Definir tamanho da ZRAM (50% da RAM total)
    zram_size = int(total_mem * 0.5)
    print(f"{COLORS.GREEN}Tamanho recomendado de ZRAM: {zram_size} MB (50% da RAM){COLORS.END}")
    
    # Perguntar o tamanho desejado
    while True:
        try:
            custom_size = input(f"{COLORS.CYAN}Digite o tamanho de ZRAM desejado em MB (padrão {zram_size}): {COLORS.END}")
            zram_size = int(custom_size) if custom_size else zram_size
            if zram_size < 256:
                print(f"{COLORS.RED}O tamanho mínimo recomendado é 256 MB{COLORS.END}")
            elif zram_size > total_mem:
                print(f"{COLORS.RED}O tamanho não deve exceder a RAM total{COLORS.END}")
            else:
                break
        except ValueError:
            print(f"{COLORS.RED}Por favor, digite um número válido{COLORS.END}")
    
    # Configurar ZRAM
    if os.path.exists("/etc/default/zramswap"):
        # Método para distribuições baseadas em Debian que usam zram-tools
        try:
            with open("/etc/default/zramswap", "w") as f:
                f.write(f"PERCENT={int((zram_size / total_mem) * 100)}\n")
                f.write("PRIORITY=100\n")
            
            print("Reiniciando serviço zramswap...")
            run_command(["service", "zramswap", "restart"], sudo=True)
            print(f"{COLORS.GREEN}ZRAM configurado através de zram-tools.{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao configurar zramswap: {e}{COLORS.END}")
    else:
        # Método manual para outras distribuições
        # Primeiro, remover qualquer configuração existente
        try:
            if os.path.exists("/sys/block/zram0"):
                run_command(["swapoff", "/dev/zram0"], sudo=True)
                with open("/sys/class/zram-control/reset", "w") as f:
                    f.write("1\n")
                print("Configuração ZRAM existente removida.")
        except Exception as e:
            print(f"{COLORS.YELLOW}Aviso ao resetar ZRAM: {e}{COLORS.END}")
        
        # Criar novo dispositivo zram
        try:
            with open("/sys/class/zram-control/hot_add", "w") as f:
                f.write("\n")
            
            # Configurar tamanho
            zram_bytes = zram_size * 1024 * 1024
            with open("/sys/block/zram0/disksize", "w") as f:
                f.write(str(zram_bytes) + "\n")
            
            # Formatar e ativar
            run_command(["mkswap", "/dev/zram0"], sudo=True)
            run_command(["swapon", "-p", "100", "/dev/zram0"], sudo=True)
            
            print(f"{COLORS.GREEN}Dispositivo ZRAM configurado manualmente.{COLORS.END}")
            
            # Adicionar ao /etc/fstab para persistir após reinicialização
            # Primeiro remover entradas anteriores
            if os.path.exists("/etc/fstab"):
                with open("/etc/fstab", "r") as f:
                    lines = f.readlines()
                
                with open("/etc/fstab", "w") as f:
                    for line in lines:
                        if "zram" not in line:
                            f.write(line)
                    
                    # Adicionar nova entrada
                    f.write("\n# ZRAM configurado pelo Multiflow\n/dev/zram0 none swap defaults,pri=100 0 0\n")
                print("Configuração adicionada ao fstab para persistência.")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao configurar dispositivo ZRAM: {e}{COLORS.END}")
    
    # Criar script de inicialização para garantir que ZRAM seja carregado corretamente
    rc_script = """#!/bin/bash
# ZRAM setup script created by Multiflow

# Load zram module if not loaded
if ! lsmod | grep -q zram; then
    modprobe zram
    
    # If using zram-control, set up the device
    if [ -e /sys/class/zram-control/hot_add ]; then
        cat /sys/class/zram-control/hot_add > /dev/null
        echo "%s" > /sys/block/zram0/disksize
        mkswap /dev/zram0
        swapon -p 100 /dev/zram0
    fi
fi

# If zram-tools is installed, make sure the service is running
if [ -f /etc/default/zramswap ]; then
    service zramswap restart
fi
""" % (zram_size * 1024 * 1024)
    
    try:
        with open("/etc/rc.local", "w") as f:
            f.write(rc_script)
        
        os.chmod("/etc/rc.local", 0o755)
        print("Script de inicialização criado para garantir persistência.")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao criar script de inicialização: {e}{COLORS.END}")
    
    print(f"\n{COLORS.GREEN}ZRAM configurado com sucesso! Recomenda-se reiniciar o sistema para verificar se a configuração persiste.{COLORS.END}")

def verificar_hosts_file():
    """Verifica se o arquivo hosts está no formato esperado."""
    hosts_file = "/etc/hosts"
    if not os.path.exists(hosts_file):
        return False
    
    try:
        with open(hosts_file, "r") as f:
            content = f.read()
        
        # Verificar se contém pelo menos uma entrada padrão
        return "localhost" in content and "127.0.0.1" in content
    except Exception:
        return False

def bloquear_site_pornografia():
    """Bloqueia sites de pornografia."""
    print_colored_box("BLOQUEAR SITES DE PORNOGRAFIA")
    
    hosts_file = "/etc/hosts"
    
    # Verificar permissões
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    # Lista de sites a bloquear
    porn_sites = """
# Bloqueio de sites pornográficos pelo Multiflow
127.0.0.1 pornhub.com www.pornhub.com
127.0.0.1 xvideos.com www.xvideos.com
127.0.0.1 xnxx.com www.xnxx.com
127.0.0.1 youporn.com www.youporn.com
127.0.0.1 redtube.com www.redtube.com
127.0.0.1 tube8.com www.tube8.com
127.0.0.1 spankbang.com www.spankbang.com
127.0.0.1 xhamster.com www.xhamster.com
127.0.0.1 beeg.com www.beeg.com
127.0.0.1 youjizz.com www.youjizz.com
127.0.0.1 motherless.com www.motherless.com
127.0.0.1 drtuber.com www.drtuber.com
127.0.0.1 nuvid.com www.nuvid.com
127.0.0.1 pornhd.com www.pornhd.com
127.0.0.1 porn.com www.porn.com
127.0.0.1 tnaflix.com www.tnaflix.com
127.0.0.1 4tube.com www.4tube.com
127.0.0.1 hclips.com www.hclips.com
127.0.0.1 nudevista.com www.nudevista.com
127.0.0.1 alohatube.com www.alohatube.com
127.0.0.1 pornhat.com www.pornhat.com
127.0.0.1 sunporno.com www.sunporno.com
127.0.0.1 xxxbunker.com www.xxxbunker.com
"""
    
    # Verificar se o hosts file está íntegro
    if not verificar_hosts_file():
        print(f"{COLORS.RED}Erro: O arquivo /etc/hosts parece estar corrompido ou inacessível.{COLORS.END}")
        return
    
    try:
        with open(hosts_file, "r") as f:
            current_hosts = f.read()
        
        # Verificar se o bloqueio já existe
        if "Bloqueio de sites pornográficos pelo Multiflow" in current_hosts:
            print(f"{COLORS.YELLOW}Os bloqueios de pornografia já estão configurados.{COLORS.END}")
            
            # Perguntar se quer atualizar
            choice = input(f"{COLORS.BOLD}Deseja atualizar a lista de bloqueios? (s/n): {COLORS.END}")
            if choice.lower() != "s":
                return
            
            # Remover bloqueios existentes
            lines = current_hosts.split("\n")
            new_lines = []
            skip = False
            
            for line in lines:
                if "Bloqueio de sites pornográficos pelo Multiflow" in line:
                    skip = True
                    continue
                
                if skip and line.strip() and not line.startswith("#") and not line.startswith("127.0.0.1"):
                    skip = False
                
                if not skip:
                    new_lines.append(line)
            
            current_hosts = "\n".join(new_lines)
            print("Bloqueios anteriores removidos.")
        
        # Adicionar novos bloqueios
        with open(hosts_file, "w") as f:
            f.write(current_hosts.rstrip() + "\n" + porn_sites)
        
        print(f"{COLORS.GREEN}Sites de pornografia bloqueados com sucesso!{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao configurar bloqueios: {e}{COLORS.END}")

def bloquear_site_personalizado():
    """Bloqueia um site específico por domínio."""
    print_colored_box("BLOQUEAR SITE ESPECÍFICO")
    
    hosts_file = "/etc/hosts"
    
    # Verificar permissões
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    # Verificar se o hosts file está íntegro
    if not verificar_hosts_file():
        print(f"{COLORS.RED}Erro: O arquivo /etc/hosts parece estar corrompido ou inacessível.{COLORS.END}")
        return
    
    # Solicitar o domínio a ser bloqueado
    domain = input(f"{COLORS.CYAN}Digite o domínio a ser bloqueado (ex: example.com): {COLORS.END}")
    if not domain:
        print(f"{COLORS.RED}Nenhum domínio informado.{COLORS.END}")
        return
    
    # Validar o domínio
    if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$', domain):
        print(f"{COLORS.RED}Domínio inválido. Use o formato example.com{COLORS.END}")
        return
    
    try:
        with open(hosts_file, "r") as f:
            current_hosts = f.read()
        
        # Verificar se o domínio já está bloqueado
        domain_pattern = re.compile(r'127\.0\.0\.1\s+' + re.escape(domain))
        www_pattern = re.compile(r'127\.0\.0\.1\s+www\.' + re.escape(domain))
        
        if domain_pattern.search(current_hosts) and www_pattern.search(current_hosts):
            print(f"{COLORS.YELLOW}O domínio {domain} já está bloqueado.{COLORS.END}")
            return
        
        # Adicionar bloqueio
        block_entry = f"\n# Bloqueio personalizado pelo Multiflow\n127.0.0.1 {domain} www.{domain}\n"
        
        with open(hosts_file, "a") as f:
            f.write(block_entry)
        
        print(f"{COLORS.GREEN}Domínio {domain} bloqueado com sucesso!{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao bloquear domínio: {e}{COLORS.END}")

def bloquear_ddos():
    """Configura proteções contra ataques DDoS sem interferir em conexões legítimas."""
    print_colored_box("CONFIGURAÇÃO ANTI-DDOS")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Esta operação precisa ser executada como root!{COLORS.END}")
        return
    
    print("Instalando ferramentas necessárias...")
    
    # Instalar pacotes necessários
    try:
        run_command(["apt", "update"], sudo=True)
        run_command(["apt", "install", "-y", "iptables", "ipset", "fail2ban", "conntrack"], sudo=True)
    except Exception as e:
        print(f"{COLORS.RED}Erro ao instalar dependências: {e}{COLORS.END}")
        return
    
    print(f"\n{COLORS.BOLD}Configurando proteção anti-DDoS...{COLORS.END}")
    
    # Verificar se ipset está instalado
    try:
        subprocess.check_output(["ipset", "-v"])
    except Exception as e:
        print(f"{COLORS.RED}Erro: ipset não está instalado corretamente: {e}{COLORS.END}")
        return
    
    # Limpar regras existentes com tratamento de erros melhorado
    try:
        print("Limpando regras existentes...")
        
        # Limpar regras de ipset com melhor tratamento de erros
        try:
            subprocess.run(["ipset", "list", "blacklist"], stderr=subprocess.DEVNULL, check=True)
            print("Removendo blacklist existente...")
            subprocess.run(["ipset", "destroy", "blacklist"], stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # A blacklist provavelmente não existe, o que é esperado em primeira execução
            pass
        
        # Criar lista de bloqueio
        try:
            subprocess.run(["ipset", "create", "blacklist", "hash:ip", "timeout", "3600"], check=True)
            print(f"{COLORS.GREEN}Lista de bloqueio criada com sucesso.{COLORS.END}")
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao criar lista de bloqueio: {e}{COLORS.END}")
            return
        
        # Verificar se foi criada
        try:
            ipset_list = subprocess.check_output(["ipset", "list"], text=True)
            if "blacklist" not in ipset_list:
                print(f"{COLORS.RED}Erro ao criar blacklist com ipset.{COLORS.END}")
                return
        except Exception as e:
            print(f"{COLORS.RED}Erro ao verificar ipset: {e}{COLORS.END}")
            return
    except Exception as e:
        print(f"{COLORS.RED}Erro ao configurar ipset: {e}{COLORS.END}")
        return
    
    # Configurar regras de iptables
    print(f"\n{COLORS.BOLD}Configurando regras de firewall...{COLORS.END}")
    
    try:
        # Salvar regras atuais
        print("Salvando regras atuais...")
        try:
            # Correção: usar string única com shell=True
            subprocess.run("iptables-save > /etc/iptables.backup", shell=True)
            print("Backup das regras de firewall salvo em /etc/iptables.backup")
        except Exception as e:
            print(f"{COLORS.YELLOW}Aviso: Não foi possível salvar backup das regras atuais: {e}{COLORS.END}")
        
        # Configurar regras anti-DDoS
        iptables_rules = [
            # Regra básica para bloquear IPs da blacklist
            ["iptables", "-A", "INPUT", "-m", "set", "--match-set", "blacklist", "src", "-j", "DROP"],
            
            # Proteção contra ataques SYN flood
            ["iptables", "-A", "INPUT", "-p", "tcp", "--syn", "-m", "limit", "--limit", "1/s", "--limit-burst", "3", "-j", "ACCEPT"],
            ["iptables", "-A", "INPUT", "-p", "tcp", "--syn", "-j", "DROP"],
            
            # Limitar conexões ICMP (ping)
            ["iptables", "-A", "INPUT", "-p", "icmp", "-m", "limit", "--limit", "1/s", "--limit-burst", "1", "-j", "ACCEPT"],
            ["iptables", "-A", "INPUT", "-p", "icmp", "-j", "DROP"],
            
            # Limitar novas conexões por IP
            ["iptables", "-A", "INPUT", "-p", "tcp", "-m", "conntrack", "--ctstate", "NEW", "-m", "limit", "--limit", "60/s", "--limit-burst", "20", "-j", "ACCEPT"],
            ["iptables", "-A", "INPUT", "-p", "tcp", "-m", "conntrack", "--ctstate", "NEW", "-j", "DROP"],
            
            # Bloquear pacotes inválidos
            ["iptables", "-A", "INPUT", "-m", "conntrack", "--ctstate", "INVALID", "-j", "DROP"],
        ]
        
        # Aplicar as regras com melhor tratamento de erros
        success_count = 0
        total_rules = len(iptables_rules)
        
        for rule in iptables_rules:
            try:
                subprocess.run(rule, check=True)
                success_count += 1
            except Exception as e:
                print(f"{COLORS.RED}Erro ao aplicar regra {' '.join(rule)}: {e}{COLORS.END}")
        
        if success_count == total_rules:
            print(f"{COLORS.GREEN}Todas as regras de proteção anti-DDoS aplicadas com sucesso.{COLORS.END}")
        else:
            print(f"{COLORS.YELLOW}Aplicadas {success_count} de {total_rules} regras de proteção.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao configurar regras de firewall: {e}{COLORS.END}")
    
    # Configurar script de persistência
    print(f"\n{COLORS.BOLD}Configurando persistência das regras...{COLORS.END}")
    
    startup_script = """#!/bin/bash
# Anti-DDoS protection script by Multiflow

# Restaurar ipset
ipset create blacklist hash:ip timeout 3600 -exist

# Aplicar regras de proteção
iptables -A INPUT -m set --match-set blacklist src -j DROP
iptables -A INPUT -p tcp --syn -m limit --limit 1/s --limit-burst 3 -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP
iptables -A INPUT -p icmp -m limit --limit 1/s --limit-burst 1 -j ACCEPT
iptables -A INPUT -p icmp -j DROP
iptables -A INPUT -p tcp -m conntrack --ctstate NEW -m limit --limit 60/s --limit-burst 20 -j ACCEPT
iptables -A INPUT -p tcp -m conntrack --ctstate NEW -j DROP
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# Log
echo "Anti-DDoS rules loaded at $(date)" >> /var/log/antiddos.log
"""
    
    try:
        # Criar diretório se não existir
        os.makedirs("/etc/network/if-pre-up.d", exist_ok=True)
        
        script_path = "/etc/network/if-pre-up.d/antiddos"
        with open(script_path, "w") as f:
            f.write(startup_script)
        
        # Tornar executável
        os.chmod(script_path, 0o755)
        print(f"{COLORS.GREEN}Script de inicialização criado em {script_path}{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao criar script de persistência: {e}{COLORS.END}")
    
    # Configurar fail2ban para proteção adicional
    print(f"\n{COLORS.BOLD}Configurando Fail2ban...{COLORS.END}")
    
    fail2ban_config = """
[DEFAULT]
# Ban hosts for 10 hours
bantime = 36000
findtime = 600
maxretry = 5

# Custom settings for SSH brute force protection
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3

# Protection against HTTP DoS attacks
[http-dos]
enabled = true
port = http,https
filter = http-dos
logpath = /var/log/apache2/access.log
maxretry = 300
findtime = 300
bantime = 600

# Custom filter for HTTP DoS
"""
    
    http_dos_filter = """
[Definition]
failregex = ^<HOST> -.*"(GET|POST).*
ignoreregex =
"""
    
    try:
        # Criar diretório se não existir
        os.makedirs("/etc/fail2ban", exist_ok=True)
        
        if not os.path.exists("/etc/fail2ban/jail.local"):
            with open("/etc/fail2ban/jail.local", "w") as f:
                f.write(fail2ban_config)
            print(f"{COLORS.GREEN}Configuração do Fail2ban criada.{COLORS.END}")
        
        # Criar filtro personalizado para HTTP DoS
        filter_dir = "/etc/fail2ban/filter.d"
        os.makedirs(filter_dir, exist_ok=True)
        
        with open(os.path.join(filter_dir, "http-dos.conf"), "w") as f:
            f.write(http_dos_filter)
        
        # Reiniciar fail2ban
        try:
            run_command(["systemctl", "restart", "fail2ban"], sudo=True)
            print(f"{COLORS.GREEN}Fail2ban configurado e reiniciado.{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.YELLOW}Aviso ao reiniciar fail2ban: {e}{COLORS.END}")
            print("Tentando iniciar fail2ban...")
            run_command(["systemctl", "start", "fail2ban"], sudo=True)
    except Exception as e:
        print(f"{COLORS.RED}Erro ao configurar Fail2ban: {e}{COLORS.END}")
    
    # Verificar e ajustar parâmetros do kernel para proteção
    print(f"\n{COLORS.BOLD}Ajustando parâmetros do kernel...{COLORS.END}")
    
    sysctl_config = """
# Otimizações contra DDoS - Multiflow
# SYN flood protection
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_syn_retries = 5
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_max_syn_backlog = 4096

# Proteção contra port scanning e outros ataques
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Desabilitar redirecionamento ICMP
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# Desabilitar source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# Aumentar tamanho das filas
net.core.netdev_max_backlog = 16384
net.ipv4.tcp_max_syn_backlog = 8192
net.core.somaxconn = 16384

# Proteção contra ataques de tempo
net.ipv4.tcp_rfc1337 = 1

# Limitar transferência de rotas ICMP
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
"""
    
    try:
        os.makedirs("/etc/sysctl.d", exist_ok=True)
        sysctl_file = "/etc/sysctl.d/90-antiddos.conf"
        with open(sysctl_file, "w") as f:
            f.write(sysctl_config)
        
        # Aplicar configurações
        run_command(["sysctl", "-p", sysctl_file], sudo=True)
        print(f"{COLORS.GREEN}Parâmetros do kernel ajustados para proteção contra DDoS.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao ajustar parâmetros do kernel: {e}{COLORS.END}")
    
    print(f"\n{COLORS.GREEN}Configuração anti-DDoS concluída com sucesso!{COLORS.END}")
    print(f"\n{COLORS.BOLD}Importante:{COLORS.END} Esta configuração foi projetada para bloquear ataques DDoS comuns")
    print("enquanto mantém conexões legítimas funcionando. Monitore o sistema após a")
    print("implementação para garantir que serviços importantes continuem funcionando.")
    print(f"\n{COLORS.BOLD}As proteções ativadas incluem:{COLORS.END}")
    print(f" - {COLORS.CYAN}Limitação de taxa para pacotes SYN (proteção contra SYN flood){COLORS.END}")
    print(f" - {COLORS.CYAN}Limitação de ICMP (proteção contra ataques ping){COLORS.END}")
    print(f" - {COLORS.CYAN}Blacklist automática para IPs suspeitos{COLORS.END}")
    print(f" - {COLORS.CYAN}Proteção contra pacotes inválidos{COLORS.END}")
    print(f" - {COLORS.CYAN}Optimização de parâmetros do kernel{COLORS.END}")
    print(f" - {COLORS.CYAN}Configuração do Fail2ban para proteção adicional{COLORS.END}")

def menu_bloqueio_sites():
    while True:
        clear_screen()
        
        print_colored_box("BLOQUEIO DE SITES")
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Bloquear Sites de Pornografia", color=COLORS.CYAN)
        print_menu_option("2", "Bloquear Site Específico (por domínio)", color=COLORS.CYAN)
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")
        
        if choice == "1":
            bloquear_site_pornografia()
        elif choice == "2":
            bloquear_site_personalizado()
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

def uninstall_multiflow():
    """Remove completamente o multiflow e todas as alterações feitas."""
    clear_screen()
    
    print_colored_box("REMOVER COMPLETAMENTE MULTIFLOW", title_color=COLORS.RED)
    
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
    
    confirmation = input(f"\n{COLORS.BOLD}{COLORS.RED}Esta ação é irreversível. Digite 'REMOVER' para confirmar: {COLORS.END}")
    
    if confirmation != "REMOVER":
        print(f"{COLORS.GREEN}Operação cancelada.{COLORS.END}")
        return
    
    print(f"\n{COLORS.BOLD}Iniciando remoção completa...{COLORS.END}")
    
    # 1. Parar e remover todos os serviços SOCKS5
    print(f"\n{COLORS.BOLD}1. Removendo serviços SOCKS5...{COLORS.END}")
    remove_socks5()
    
    # 2. Parar e remover OpenVPN
    print(f"\n{COLORS.BOLD}2. Removendo OpenVPN...{COLORS.END}")
    if openvpn_status["active"]:
        stop_openvpn()
    remove_openvpn()
    
    # 3. Remover link simbólico
    print(f"\n{COLORS.BOLD}3. Removendo links simbólicos...{COLORS.END}")
    try:
        if os.path.exists("/usr/local/bin/multiflow"):
            os.remove("/usr/local/bin/multiflow")
            print("Link simbólico /usr/local/bin/multiflow removido.")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao remover link simbólico: {e}{COLORS.END}")
    
    # 4. Remover diretório de instalação
    print(f"\n{COLORS.BOLD}4. Removendo diretório de instalação...{COLORS.END}")
    try:
        install_dir = "/opt/multiflow"
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
            print(f"Diretório {install_dir} removido.")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao remover diretório de instalação: {e}{COLORS.END}")
    
    # 5. Limpar arquivos temporários
    print(f"\n{COLORS.BOLD}5. Limpando arquivos temporários...{COLORS.END}")
    temp_files = ["server.conf", "openvpn_source", "keys", "socks5_server"]
    for file in temp_files:
        if os.path.exists(file):
            try:
                if os.path.isdir(file):
                    shutil.rmtree(file)
                else:
                    os.remove(file)
                print(f"{file} removido.")
            except Exception as e:
                print(f"{COLORS.RED}Erro ao remover {file}: {e}{COLORS.END}")
    
    # 6. Verificar e remover backups
    print(f"\n{COLORS.BOLD}6. Verificando backups...{COLORS.END}")
    try:
        backup_dirs = [d for d in os.listdir("/opt") if d.startswith("multiflow.bak")]
        if backup_dirs:
            print(f"Encontrados {len(backup_dirs)} backups.")
            remove_backups = input(f"{COLORS.BOLD}Deseja remover também os backups? (s/n): {COLORS.END}")
            if remove_backups.lower() == "s":
                for backup in backup_dirs:
                    backup_path = os.path.join("/opt", backup)
                    shutil.rmtree(backup_path)
                    print(f"Backup {backup} removido.")
    except Exception as e:
        print(f"{COLORS.RED}Erro ao verificar backups: {e}{COLORS.END}")
    
    print(f"\n{COLORS.GREEN}Multiflow foi completamente removido do sistema.{COLORS.END}")
    print(f"{COLORS.CYAN}Obrigado por usar o Multiflow!{COLORS.END}")
    
    input(f"\n{COLORS.BOLD}Pressione Enter para voltar ao menu principal...{COLORS.END}")

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
        
        # Menu principal
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Gerenciar Usuários", color=COLORS.CYAN)
        print_menu_option("2", "Gerenciar Conexões", color=COLORS.CYAN)
        print_menu_option("3", "Remover Completamente Multiflow", color=COLORS.RED)
        print_menu_option("4", "Ferramentas", color=COLORS.CYAN)
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
            uninstall_multiflow()
        elif choice == "4":
            menu_ferramentas()
        elif choice == "0":
            clear_screen()
            print(f"\n{COLORS.GREEN}Obrigado por usar o Multiflow!{COLORS.END}")
            print(f"{COLORS.CYAN}Saindo...{COLORS.END}")
            break
        else:
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
