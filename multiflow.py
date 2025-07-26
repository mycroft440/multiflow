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
    """Verifica se os módulos necessários estão instalados."""
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

# Dicionários para rastrear processos
socks5_processes = {}
proxysocks_processes = {}  # Novo para ProxySocks
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
{COLORS.BOLD}{COLORS.CYAN}███╗   ███╗██╗   ██║██║  ████████╗██╗███████╗██╗      ██████╗ ██╗    ██╗
████╗ ████║██║   ██║██║  ╚════██╔══╝██║██╔════╝██║     ██╔═══██╗██║    ██║
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
    """Verifica o status dos serviços SOCKS5, OpenVPN e ProxySocks."""
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
    
    # Status do ProxySocks
    proxysocks_status = "Ativo - Portas " + ", ".join([str(porta) for porta in proxysocks_processes.keys()]) if proxysocks_processes else "Desativado"
    
    return socks_status, openvpn_status_text, proxysocks_status

# Funções para SOCKS5 (mantidas como estavam)

# ... (o código de SOCKS5 permanece o mesmo, pulei pra brevidade)

# Funções para ProxySocks (nova seção)
def install_proxysocks():
    print_colored_box("INSTALANDO PROXYSOCKS")
    print("Instalando ProxySocks e dependências necessárias...")
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
            print("Instalando libs necessárias...")
            subprocess.check_call(["sudo", "apt", "install", "-y", "libpthread-stubs0-dev"])
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao instalar dependências do sistema: {e}{COLORS.END}")
            return False
    else:
        print(f"{COLORS.RED}Instalação automática suportada apenas no Linux. Instale manualmente para {sys.platform}.{COLORS.END}")
        return False

    # Verificar se o arquivo proxysocks.cpp existe
    if not os.path.exists("proxysocks.cpp"):
        print(f"{COLORS.RED}Erro: proxysocks.cpp não encontrado! Certifique-se de que o arquivo existe.{COLORS.END}")
        return False

    # Compilar o ProxySocks
    try:
        print(f"\n{COLORS.BOLD}Compilando o ProxySocks...{COLORS.END}")
        subprocess.check_call([
            "g++", "-o", "proxysocks", "proxysocks.cpp",
            "-lboost_system", "-lboost_thread", "-lpthread", "-std=c++11", "-O3"  # Otimização nível 3
        ])
        print(f"{COLORS.GREEN}ProxySocks compilado com sucesso!{COLORS.END}")
        
        # Verificar se o binário foi criado
        if os.path.exists("proxysocks"):
            print(f"{COLORS.GREEN}ProxySocks instalado com sucesso!{COLORS.END}")
            # Definir permissões de execução
            os.chmod("proxysocks", 0o755)
            return True
        else:
            print(f"{COLORS.RED}Erro: Binário proxysocks não encontrado após compilação.{COLORS.END}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"{COLORS.RED}Erro na compilação: {e}{COLORS.END}")
        return False
    except Exception as e:
        print(f"{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
        return False

def add_port_proxysocks():
    print_colored_box("ADICIONAR PORTA PROXYSOCKS")
    port = input(f"{COLORS.CYAN}Digite a porta desejada (1-65535): {COLORS.END}")
    try:
        port = int(port)
        if port < 1 or port > 65535:
            print(f"{COLORS.RED}Porta inválida!{COLORS.END}")
            return
    except ValueError:
        print(f"{COLORS.RED}Entrada inválida!{COLORS.END}")
        return

    if port in proxysocks_processes:
        print(f"{COLORS.RED}Porta {port} já em uso!{COLORS.END}")
        return

    if not os.path.exists("proxysocks"):
        print(f"{COLORS.RED}Erro: Binário não compilado!{COLORS.END}")
        return

    try:
        process = subprocess.Popen(
            ["./proxysocks", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(1)
        if process.poll() is None:
            proxysocks_processes[port] = process
            print(f"{COLORS.GREEN}ProxySocks iniciado na porta {port}.{COLORS.END}")
        else:
            print(f"{COLORS.RED}Erro ao iniciar na porta {port}.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro: {e}{COLORS.END}")

def remove_port_proxysocks():
    print_colored_box("REMOVER PORTA PROXYSOCKS")
    port = input(f"{COLORS.CYAN}Digite a porta a ser removida: {COLORS.END}")
    try:
        port = int(port)
        if port not in proxysocks_processes:
            print(f"{COLORS.RED}Nenhum ProxySocks na porta {port}!{COLORS.END}")
            return
    except ValueError:
        print(f"{COLORS.RED}Entrada inválida!{COLORS.END}")
        return

    process = proxysocks_processes[port]
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        del proxysocks_processes[port]
        print(f"{COLORS.GREEN}ProxySocks removido da porta {port}.{COLORS.END}")
    except Exception as e:
        print(f"{COLORS.RED}Erro: {e}{COLORS.END}")

def remove_proxysocks():
    print_colored_box("REMOVER PROXYSOCKS")
    print("Removendo ProxySocks...")
    for port, process in list(proxysocks_processes.items()):
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
            print(f"Encerrado na porta {port}.")
        except Exception as e:
            print(f"{COLORS.RED}Erro ao encerrar na porta {port}: {e}{COLORS.END}")
    proxysocks_processes.clear()

    if os.path.exists("proxysocks"):
        try:
            os.remove("proxysocks")
            print("Binário removido.")
        except Exception as e:
            print(f"{COLORS.RED}Erro: {e}{COLORS.END}")
    else:
        print("Nenhum binário encontrado.")
    print(f"{COLORS.GREEN}ProxySocks removido com sucesso.{COLORS.END}")

def menu_proxysocks():
    while True:
        clear_screen()
        
        # Verificar status atual
        _, _, proxysocks_status = check_services_status()
        
        # Título e status
        status_color = COLORS.GREEN if "Ativo" in proxysocks_status else COLORS.RED
        content_lines = [f"{COLORS.BOLD}Status:{COLORS.END} {status_color}{proxysocks_status}{COLORS.END}"]
        print_colored_box("GERENCIAR PROXYSOCKS", content_lines)
        
        # Opções do menu
        width = 60
        print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
        print_menu_option("1", "Instalar ProxySocks", color=COLORS.CYAN)
        print_menu_option("2", "Adicionar Porta", color=COLORS.CYAN)
        print_menu_option("3", "Remover Porta", color=COLORS.CYAN)
        print_menu_option("4", "Remover ProxySocks", color=COLORS.CYAN)
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        if choice == "1":
            install_proxysocks()
        elif choice == "2":
            add_port_proxysocks()
        elif choice == "3":
            remove_port_proxysocks()
        elif choice == "4":
            remove_proxysocks()
        elif choice == "0":
            break
        else:
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

# Funções para OpenVPN (mantidas)

# ... (código de OpenVPN permanece o mesmo)

def menu_conexoes():
    while True:
        clear_screen()
        
        # Verificar status dos serviços
        socks_status, openvpn_status_text, proxysocks_status = check_services_status()
        
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
        
        # Status colorido para ProxySocks
        proxysocks_status_color = f"{COLORS.GREEN}{proxysocks_status}{COLORS.END}" if "Ativo" in proxysocks_status else f"{COLORS.RED}{proxysocks_status}{COLORS.END}"
        print_menu_option("3", "Gerenciar ProxySocks", f"[ {proxysocks_status_color} ]", COLORS.CYAN)
        
        print_menu_option("0", "Voltar", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        if choice == "1":
            menu_socks5()
        elif choice == "2":
            menu_openvpn()
        elif choice == "3":
            menu_proxysocks()
        elif choice == "0":
            break
        else:
            print(f"{COLORS.RED}Opção inválida!{COLORS.END}")

        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

# Menu usuários (mantido)

# ... (resto do código permanece, incluindo uninstall_multiflow atualizado abaixo)

def uninstall_multiflow():
    """Remove completamente o multiflow e todas as alterações feitas."""
    # ... (código existente)
    
    # Adicionar remoção de ProxySocks
    print(f"\n{COLORS.BOLD}Removendo serviços ProxySocks...{COLORS.END}")
    try:
        if proxysocks_processes:
            ports = list(proxysocks_processes.keys())
            remove_proxysocks()
            log_action(f"Serviços ProxySocks nas portas {', '.join(str(p) for p in ports)} removidos")
        else:
            log_action("Nenhum serviço ProxySocks encontrado em execução")
    except Exception as e:
        log_action(f"Erro ao remover serviços ProxySocks: {e}", success=False)
    
    # Remover binário proxysocks se existir
    if os.path.exists("proxysocks"):
        try:
            os.remove("proxysocks")
            log_action("Binário proxysocks removido")
        except Exception as e:
            log_action(f"Erro ao remover binário proxysocks: {e}", success=False)
    
    # ... (resto do uninstall)

# Ponto de entrada
if __name__ == "__main__":
    main_menu()
