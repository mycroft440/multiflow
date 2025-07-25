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

# Dicionário para rastrear processos SOCKS5 por porta
socks5_processes = {}

# Status do OpenVPN
openvpn_status = {"active": False, "port": None, "proto": None}

def clear_screen():
    """Limpa a tela do console."""
    os.system("cls" if os.name == "nt" else "clear")

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
            return "\033[32m"  # Verde
        elif percent < 80:
            return "\033[33m"  # Amarelo
        else:
            return "\033[31m"  # Vermelho
    
    ram_color = get_color_code(info["ram_percent"])
    cpu_color = get_color_code(info["cpu_percent"])
    reset_color = "\033[0m"
    
    # Construir o painel
    print("╔════════════════════════════════════════════════════╗")
    print(f"║ OS: {info['os_name']:<42} ║")
    print(f"║ RAM: {ram_color}{info['ram_percent']:>3.1f}%{reset_color}  |  CPU: {cpu_color}{info['cpu_percent']:>3.1f}%{reset_color}                          ║")
    print("╚════════════════════════════════════════════════════╝")

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
    print("Instalando SOCKS5 e todas as dependências necessárias...")
    if not check_and_install_package("psutil"):
        print("Falha ao instalar dependências Python. Continue manualmente.")
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
            print(f"Erro ao instalar dependências do sistema: {e}")
            return False
    else:
        print(f"Instalação automática suportada apenas no Linux. Instale manualmente para {sys.platform}.")
        return False

    if not os.path.exists("src/socks5_server.cpp"):
        print("Erro: src/socks5_server.cpp não encontrado!")
        return False

    try:
        print("Compilando o servidor SOCKS5...")
        subprocess.check_call([
            "g++", "-o", "socks5_server", "src/socks5_server.cpp",
            "-lboost_system", "-lboost_log", "-lboost_thread", "-lpthread", "-lssh2", "-std=c++14"
        ])
        print("SOCKS5 instalado com sucesso!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro na compilação: {e}")
        return False

def add_port_socks5():
    port = input("Digite a porta desejada (1-65535): ")
    try:
        port = int(port)
        if port < 1 or port > 65535:
            print("Porta inválida!")
            return
    except ValueError:
        print("Entrada inválida!")
        return

    if port in socks5_processes:
        print(f"Porta {port} já em uso!")
        return

    if not os.path.exists("socks5_server"):
        print("Erro: Servidor não compilado!")
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
            print(f"SOCKS5 iniciado na porta {port}.")
        else:
            print(f"Erro ao iniciar na porta {port}.")
    except Exception as e:
        print(f"Erro: {e}")

def remove_port_socks5():
    port = input("Digite a porta a ser removida: ")
    try:
        port = int(port)
        if port not in socks5_processes:
            print(f"Nenhum SOCKS5 na porta {port}!")
            return
    except ValueError:
        print("Entrada inválida!")
        return

    process = socks5_processes[port]
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        del socks5_processes[port]
        print(f"SOCKS5 removido da porta {port}.")
    except Exception as e:
        print(f"Erro: {e}")

def remove_socks5():
    print("Removendo SOCKS5...")
    for port, process in list(socks5_processes.items()):
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
            print(f"Encerrado na porta {port}.")
        except Exception as e:
            print(f"Erro ao encerrar na porta {port}: {e}")
    socks5_processes.clear()

    if os.path.exists("socks5_server"):
        try:
            os.remove("socks5_server")
            print("Binário removido.")
        except Exception as e:
            print(f"Erro: {e}")
    else:
        print("Nenhum binário encontrado.")
    print("SOCKS5 removido com sucesso.")

def menu_socks5():
    while True:
        clear_screen()
        
        # Verificar status atual
        socks_status, _ = check_services_status()
        
        print("\n=== Gerenciar SOCKS5 ===")
        print(f"Status: {socks_status}")
        print("1. Instalar SOCKS5")
        print("2. Adicionar Porta")
        print("3. Remover Porta")
        print("4. Remover SOCKS5")
        print("0. Voltar")
        choice = input("\nEscolha uma opção: ")

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
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

# Funções para OpenVPN
def install_openvpn():
    if sys.platform != "linux":
        print("Instalação suportada apenas no Linux.")
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

    print("OpenVPN instalado! Inicie com 'sudo openvpn server.conf'.")

def start_openvpn():
    """Inicia o serviço OpenVPN."""
    if openvpn_status["active"]:
        print(f"OpenVPN já está ativo na porta {openvpn_status['port']}.")
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
            
            print(f"OpenVPN iniciado na porta {port}.")
        except Exception as e:
            print(f"Erro ao iniciar OpenVPN: {e}")
    else:
        print("Arquivo de configuração server.conf não encontrado.")
        print("Execute a instalação do OpenVPN primeiro.")

def stop_openvpn():
    """Para o serviço OpenVPN."""
    if not openvpn_status["active"]:
        print("OpenVPN não está ativo.")
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
                    print(f"Erro ao encerrar processo OpenVPN (PID {proc.info['pid']}): {e}")
        
        # Resetar status
        openvpn_status["active"] = False
        openvpn_status["port"] = None
        
        print("OpenVPN parado.")
    except Exception as e:
        print(f"Erro ao parar OpenVPN: {e}")

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
        print("Certificados gerados em keys/.")
        return True
    except Exception as e:
        print(f"Erro: {e}")
        return False

def select_port_and_proto_openvpn():
    port = input("Porta desejada (default 1194): ") or "1194"
    proto = input("Protocolo (1 TCP, 2 UDP, default TCP): ") or "1"
    proto = "tcp" if proto == "1" else "udp"
    return port, proto

def select_dns_openvpn():
    print("DNS:")
    print("1. Google (8.8.8.8)")
    print("2. Cloudflare (1.1.1.1)")
    print("3. OpenDNS (208.67.222.222)")
    choice = input("Opção (default 1): ") or "1"
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
    print("Config gerada em server.conf.")

def remove_openvpn():
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
    
    print("OpenVPN removido.")

def menu_openvpn():
    while True:
        clear_screen()
        
        # Verificar status atual
        _, openvpn_status_text = check_services_status()
        
        print("\n=== Gerenciar OpenVPN ===")
        print(f"Status: {openvpn_status_text}")
        print("1. Instalar OpenVPN")
        print("2. Remover OpenVPN")
        if openvpn_status["active"]:
            print("3. Parar OpenVPN")
        else:
            print("3. Iniciar OpenVPN")
        print("0. Voltar")
        choice = input("\nEscolha uma opção: ")

        if choice == "1":
            install_openvpn()
        elif choice == "2":
            if openvpn_status["active"]:
                print("O OpenVPN está em execução. Pare o serviço antes de removê-lo.")
                input("Pressione Enter para continuar...")
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
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

def menu_conexoes():
    while True:
        clear_screen()
        
        # Verificar status dos serviços
        socks_status, openvpn_status_text = check_services_status()
        
        print("\n=== Gerenciar Conexões ===")
        print(f"1. Gerenciar SOCKS5 [ {socks_status} ]")
        print(f"2. Gerenciar OpenVPN [ {openvpn_status_text} ]")
        print("0. Voltar")
        choice = input("\nEscolha uma opção: ")

        if choice == "1":
            menu_socks5()
        elif choice == "2":
            menu_openvpn()
        elif choice == "0":
            break
        else:
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

def menu_usuarios():
    while True:
        clear_screen()
        print("\n=== Gerenciar Usuários ===")
        print("1. Criar Usuário")
        print("2. Remover Usuário")
        print("3. Alterar Senha")
        print("4. Alterar Data de Expiração")
        print("5. Alterar Limite de Conexões")
        print("0. Voltar")
        choice = input("\nEscolha uma opção: ")

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
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

# Novas funções de ferramentas
def alterar_senha_root():
    print("\n=== Alterar Senha do Root ===")
    print("Esta operação irá alterar a senha do usuário root")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print("Esta operação precisa ser executada como root!")
        return
    
    import getpass
    
    # Solicitar nova senha
    nova_senha = getpass.getpass("Digite a nova senha para root: ")
    confirm_senha = getpass.getpass("Confirme a nova senha: ")
    
    if nova_senha != confirm_senha:
        print("As senhas não coincidem!")
        return
    
    if len(nova_senha) < 6:
        print("A senha deve ter pelo menos 6 caracteres!")
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
            print("Senha do root alterada com sucesso!")
        else:
            print("Erro ao alterar senha do root. Código de retorno:", process.returncode)
    except Exception as e:
        print(f"Erro ao alterar senha: {e}")

def otimizar_sistema():
    print("\n=== Otimizando Sistema ===")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print("Esta operação precisa ser executada como root!")
        return
    
    print("Iniciando otimização do sistema...")
    
    # 1. Atualizar o sistema
    print("\n1. Atualizando repositórios...")
    run_command(["apt", "update"], sudo=True)
    
    # 2. Remover pacotes desnecessários
    print("\n2. Removendo pacotes desnecessários...")
    run_command(["apt", "autoremove", "-y"], sudo=True)
    run_command(["apt", "clean"], sudo=True)
    
    # 3. Limpar o cache de pacotes
    print("\n3. Limpando cache de pacotes...")
    run_command(["apt-get", "clean"], sudo=True)
    
    # 4. Otimizar uso de memória
    print("\n4. Otimizando uso de memória...")
    
    # Ajustar swappiness - versão corrigida
    try:
        # Método seguro usando sysctl
        run_command(["sysctl", "-w", "vm.swappiness=10"], sudo=True)
    except Exception:
        try:
            # Método alternativo
            with open("/proc/sys/vm/swappiness", "w") as f:
                f.write("10")
        except Exception as e:
            print(f"Erro ao ajustar swappiness: {e}")
    
    # Configurar para persistir após reinicialização
    sysctl_file = "/etc/sysctl.conf"
    sysctl_content = ""
    
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
    
    # 5. Otimizar desempenho de rede
    print("\n5. Otimizando desempenho de rede...")
    
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
    
    # Adicionar configurações de rede se não existirem
    for line in net_config.strip().split('\n'):
        if line.startswith('#') or not line.strip():
            continue
        
        key = line.split('=')[0].strip()
        if key not in sysctl_content:
            sysctl_content += line + "\n"
    
    with open(sysctl_file, "w") as f:
        f.write(sysctl_content)
    
    # Aplicar configurações do sysctl
    run_command(["sysctl", "-p"], sudo=True)
    
    # 6. Desativar serviços desnecessários
    print("\n6. Verificando serviços desnecessários...")
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
    
    print("\nSistema otimizado com sucesso! Recomenda-se reiniciar para aplicar todas as mudanças.")

def gerar_memoria_swap():
    print("\n=== Gerar Memória Swap ===")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print("Esta operação precisa ser executada como root!")
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
        print(f"Erro ao verificar memória: {e}")
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
                print(f"Erro ao processar informações de swap: {e}")
        print(f"Swap existente: {current_swap:.0f} MB")
    except Exception as e:
        print(f"Erro ao verificar swap existente: {e}")
    
    if current_swap > 0:
        print("\nJá existe memória swap configurada no sistema.")
        choice = input("Deseja remover a swap existente e criar uma nova? (s/n): ")
        if choice.lower() != 's':
            return
        
        # Desativar swap existente
        run_command(["swapoff", "-a"], sudo=True)
        
        # Remover entradas do fstab
        fstab = "/etc/fstab"
        if os.path.exists(fstab):
            with open(fstab, "r") as f:
                lines = f.readlines()
            
            with open(fstab, "w") as f:
                for line in lines:
                    if "swap" not in line:
                        f.write(line)
    
    # Definir tamanho recomendado da swap
    if total_mem <= 2048:  # 2GB
        recommended_swap = total_mem * 2
    elif total_mem <= 8192:  # 8GB
        recommended_swap = total_mem
    else:
        recommended_swap = 8192  # 8GB máximo
    
    print(f"\nTamanho recomendado de swap: {recommended_swap:.0f} MB")
    
    # Perguntar o tamanho desejado
    while True:
        try:
            swap_size = input(f"Digite o tamanho de swap desejado em MB (padrão {recommended_swap:.0f}): ")
            swap_size = int(swap_size) if swap_size else int(recommended_swap)
            if swap_size < 256:
                print("O tamanho mínimo de swap é 256 MB")
            else:
                break
        except ValueError:
            print("Por favor, digite um número válido")
    
    # Criar arquivo de swap
    swap_file = "/swapfile"
    print(f"\nCriando arquivo de swap de {swap_size} MB em {swap_file}...")
    
    # Garantir que o arquivo não exista
    if os.path.exists(swap_file):
        os.remove(swap_file)
    
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
        with open("/etc/fstab", "a") as f:
            f.write(f"\n# Swap criado pelo Multiflow\n{swap_file} none swap sw 0 0\n")
        
        print("\nMemória swap criada e ativada com sucesso!")
    except Exception as e:
        print(f"Erro ao configurar swap: {e}")

def configurar_zram():
    print("\n=== Configurar ZRAM ===")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print("Esta operação precisa ser executada como root!")
        return
    
    # Verificar se o módulo zram já está carregado
    loaded = False
    try:
        lsmod_output = subprocess.check_output(["lsmod"], text=True)
        if "zram" in lsmod_output:
            loaded = True
            print("O módulo ZRAM já está carregado.")
    except Exception:
        pass
    
    if not loaded:
        print("Instalando e configurando ZRAM...")
        
        # Instalar o pacote zram-tools se disponível
        try:
            run_command(["apt", "install", "-y", "zram-tools"], sudo=True)
        except Exception:
            print("Pacote zram-tools não encontrado. Configurando manualmente...")
            
            # Carregar o módulo zram
            run_command(["modprobe", "zram"], sudo=True)
            
            # Garantir que o módulo seja carregado na inicialização
            with open("/etc/modules-load.d/zram.conf", "w") as f:
                f.write("zram\n")
    
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
        print(f"Erro ao verificar memória: {e}")
        total_mem = 1024  # Valor padrão de 1GB
    
    # Definir tamanho da ZRAM (50% da RAM total)
    zram_size = int(total_mem * 0.5)
    print(f"Tamanho recomendado de ZRAM: {zram_size} MB (50% da RAM)")
    
    # Perguntar o tamanho desejado
    while True:
        try:
            custom_size = input(f"Digite o tamanho de ZRAM desejado em MB (padrão {zram_size}): ")
            zram_size = int(custom_size) if custom_size else zram_size
            if zram_size < 256:
                print("O tamanho mínimo recomendado é 256 MB")
            elif zram_size > total_mem:
                print("O tamanho não deve exceder a RAM total")
            else:
                break
        except ValueError:
            print("Por favor, digite um número válido")
    
    # Configurar ZRAM
    if os.path.exists("/etc/default/zramswap"):
        # Método para distribuições baseadas em Debian que usam zram-tools
        with open("/etc/default/zramswap", "w") as f:
            f.write(f"PERCENT={int((zram_size / total_mem) * 100)}\n")
            f.write("PRIORITY=100\n")
        
        print("Reiniciando serviço zramswap...")
        run_command(["service", "zramswap", "restart"], sudo=True)
    else:
        # Método manual para outras distribuições
        # Primeiro, remover qualquer configuração existente
        try:
            if os.path.exists("/sys/block/zram0"):
                run_command(["swapoff", "/dev/zram0"], sudo=True)
                with open("/sys/class/zram-control/reset", "w") as f:
                    f.write("1\n")
        except Exception:
            pass
        
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
        except Exception as e:
            print(f"Erro ao configurar dispositivo ZRAM: {e}")
    
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
    
    with open("/etc/rc.local", "w") as f:
        f.write(rc_script)
    
    os.chmod("/etc/rc.local", 0o755)
    
    print("\nZRAM configurado com sucesso! Recomenda-se reiniciar o sistema para verificar se a configuração persiste.")

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
    hosts_file = "/etc/hosts"
    
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
        print("Erro: O arquivo /etc/hosts parece estar corrompido ou inacessível.")
        return
    
    try:
        with open(hosts_file, "r") as f:
            current_hosts = f.read()
        
        # Verificar se o bloqueio já existe
        if "Bloqueio de sites pornográficos pelo Multiflow" in current_hosts:
            print("Os bloqueios de pornografia já estão configurados.")
            
            # Perguntar se quer atualizar
            choice = input("Deseja atualizar a lista de bloqueios? (s/n): ")
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
        
        # Adicionar novos bloqueios
        with open(hosts_file, "w") as f:
            f.write(current_hosts.rstrip() + "\n" + porn_sites)
        
        print("Sites de pornografia bloqueados com sucesso!")
    except Exception as e:
        print(f"Erro ao configurar bloqueios: {e}")

def bloquear_site_personalizado():
    """Bloqueia um site específico por domínio."""
    hosts_file = "/etc/hosts"
    
    # Verificar se o hosts file está íntegro
    if not verificar_hosts_file():
        print("Erro: O arquivo /etc/hosts parece estar corrompido ou inacessível.")
        return
    
    # Solicitar o domínio a ser bloqueado
    domain = input("Digite o domínio a ser bloqueado (ex: example.com): ")
    if not domain:
        print("Nenhum domínio informado.")
        return
    
    # Validar o domínio
    if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$', domain):
        print("Domínio inválido. Use o formato example.com")
        return
    
    try:
        with open(hosts_file, "r") as f:
            current_hosts = f.read()
        
        # Verificar se o domínio já está bloqueado
        domain_pattern = re.compile(r'127\.0\.0\.1\s+' + re.escape(domain))
        www_pattern = re.compile(r'127\.0\.0\.1\s+www\.' + re.escape(domain))
        
        if domain_pattern.search(current_hosts) and www_pattern.search(current_hosts):
            print(f"O domínio {domain} já está bloqueado.")
            return
        
        # Adicionar bloqueio
        block_entry = f"\n# Bloqueio personalizado pelo Multiflow\n127.0.0.1 {domain} www.{domain}\n"
        
        with open(hosts_file, "a") as f:
            f.write(block_entry)
        
        print(f"Domínio {domain} bloqueado com sucesso!")
    except Exception as e:
        print(f"Erro ao bloquear domínio: {e}")

def bloquear_ddos():
    """Configura proteções contra ataques DDoS sem interferir em conexões legítimas."""
    print("\n=== Configuração Anti-DDoS ===")
    
    # Verificar se estamos rodando como root
    if os.geteuid() != 0:
        print("Esta operação precisa ser executada como root!")
        return
    
    print("Instalando ferramentas necessárias...")
    
    # Instalar pacotes necessários
    try:
        run_command(["apt", "update"], sudo=True)
        run_command(["apt", "install", "-y", "iptables", "ipset", "fail2ban", "conntrack"], sudo=True)
    except Exception as e:
        print(f"Erro ao instalar dependências: {e}")
        return
    
    print("\nConfigurando proteção anti-DDoS...")
    
    # Verificar se ipset está instalado
    try:
        subprocess.check_output(["ipset", "-v"])
    except:
        print("Erro: ipset não está instalado corretamente.")
        return
    
    # Limpar regras existentes
    try:
        print("Limpando regras existentes...")
        
        # Limpar regras de ipset
        try:
            subprocess.run(["ipset", "destroy", "blacklist"], stderr=subprocess.DEVNULL)
        except:
            pass
        
        # Criar lista de bloqueio
        subprocess.run(["ipset", "create", "blacklist", "hash:ip", "timeout", "3600"])
        
        # Verificar se foi criada
        ipset_list = subprocess.check_output(["ipset", "list"], text=True)
        if "blacklist" not in ipset_list:
            print("Erro ao criar blacklist com ipset.")
            return
    except Exception as e:
        print(f"Erro ao configurar ipset: {e}")
        return
    
    # Configurar regras de iptables
    print("\nConfigurando regras de firewall...")
    
    try:
        # Salvar regras atuais
        print("Salvando regras atuais...")
        try:
            # Correção: usar string única com shell=True
            subprocess.run("iptables-save > /etc/iptables.backup", shell=True)
            print("Backup das regras de firewall salvo em /etc/iptables.backup")
        except:
            print("Aviso: Não foi possível salvar backup das regras atuais.")
        
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
        
        # Aplicar as regras
        for rule in iptables_rules:
            try:
                subprocess.run(rule)
            except Exception as e:
                print(f"Erro ao aplicar regra {' '.join(rule)}: {e}")
        
        print("Regras de proteção anti-DDoS aplicadas com sucesso.")
    except Exception as e:
        print(f"Erro ao configurar regras de firewall: {e}")
    
    # Configurar script de persistência
    print("\nConfigurando persistência das regras...")
    
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
        script_path = "/etc/network/if-pre-up.d/antiddos"
        with open(script_path, "w") as f:
            f.write(startup_script)
        
        # Tornar executável
        os.chmod(script_path, 0o755)
        print(f"Script de inicialização criado em {script_path}")
    except Exception as e:
        print(f"Erro ao criar script de persistência: {e}")
    
    # Configurar fail2ban para proteção adicional
    print("\nConfigurando Fail2ban...")
    
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
        if not os.path.exists("/etc/fail2ban/jail.local"):
            with open("/etc/fail2ban/jail.local", "w") as f:
                f.write(fail2ban_config)
            print("Configuração do Fail2ban criada.")
        
        # Criar filtro personalizado para HTTP DoS
        filter_dir = "/etc/fail2ban/filter.d"
        if not os.path.exists(filter_dir):
            os.makedirs(filter_dir)
        
        with open(os.path.join(filter_dir, "http-dos.conf"), "w") as f:
            f.write(http_dos_filter)
        
        # Reiniciar fail2ban
        run_command(["systemctl", "restart", "fail2ban"], sudo=True)
        print("Fail2ban configurado e reiniciado.")
    except Exception as e:
        print(f"Erro ao configurar Fail2ban: {e}")
    
    # Verificar e ajustar parâmetros do kernel para proteção
    print("\nAjustando parâmetros do kernel...")
    
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
        sysctl_file = "/etc/sysctl.d/90-antiddos.conf"
        with open(sysctl_file, "w") as f:
            f.write(sysctl_config)
        
        # Aplicar configurações
        run_command(["sysctl", "-p", sysctl_file], sudo=True)
        print("Parâmetros do kernel ajustados para proteção contra DDoS.")
    except Exception as e:
        print(f"Erro ao ajustar parâmetros do kernel: {e}")
    
    print("\nConfiguração anti-DDoS concluída com sucesso!")
    print("\nImportante: Esta configuração foi projetada para bloquear ataques DDoS comuns")
    print("enquanto mantém conexões legítimas funcionando. Monitore o sistema após a")
    print("implementação para garantir que serviços importantes continuem funcionando.")
    print("\nAs proteções ativadas incluem:")
    print(" - Limitação de taxa para pacotes SYN (proteção contra SYN flood)")
    print(" - Limitação de ICMP (proteção contra ataques ping)")
    print(" - Blacklist automática para IPs suspeitos")
    print(" - Proteção contra pacotes inválidos")
    print(" - Optimização de parâmetros do kernel")
    print(" - Configuração do Fail2ban para proteção adicional")

def menu_bloqueio_sites():
    while True:
        clear_screen()
        print("\n=== Bloqueio de Sites ===")
        print("1. Bloquear Sites de Pornografia")
        print("2. Bloquear Site Específico (por domínio)")
        print("0. Voltar")
        
        choice = input("\nEscolha uma opção: ")
        
        if choice == "1":
            bloquear_site_pornografia()
        elif choice == "2":
            bloquear_site_personalizado()
        elif choice == "0":
            break
        else:
            print("Opção inválida!")
        
        input("\nPressione Enter para continuar...")

def menu_ferramentas():
    while True:
        clear_screen()
        print("\n=== Ferramentas ===")
        print("1. Alterar senha root")
        print("2. Otimizar sistema")
        print("3. Gerar Memoria Swap")
        print("4. Configurar Zram")
        print("5. Bloquear sites")
        print("6. Proteção Anti-DDoS") # Nova opção
        print("0. Voltar")
        
        choice = input("\nEscolha uma opção: ")
        
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
        elif choice == "6":   # Nova opção
            bloquear_ddos()
        elif choice == "0":
            break
        else:
            print("Opção inválida!")
        
        input("\nPressione Enter para continuar...")

def uninstall_multiflow():
    """Remove completamente o multiflow e todas as alterações feitas."""
    clear_screen()
    print("\n=== Remover Completamente Multiflow ===")
    print("Esta operação irá remover TODAS as alterações feitas pelo Multiflow:")
    print(" - Remover todos os serviços SOCKS5 e OpenVPN")
    print(" - Excluir todos os arquivos de instalação")
    print(" - Remover links simbólicos e scripts")
    print(" - Remover o diretório de instalação (/opt/multiflow)")
    
    confirmation = input("\nEsta ação é irreversível. Digite 'REMOVER' para confirmar: ")
    
    if confirmation != "REMOVER":
        print("Operação cancelada.")
        return
    
    print("\nIniciando remoção completa...")
    
    # 1. Parar e remover todos os serviços SOCKS5
    print("Removendo serviços SOCKS5...")
    remove_socks5()
    
    # 2. Parar e remover OpenVPN
    print("Removendo OpenVPN...")
    if openvpn_status["active"]:
        stop_openvpn()
    remove_openvpn()
    
    # 3. Remover link simbólico
    print("Removendo links simbólicos...")
    try:
        if os.path.exists("/usr/local/bin/multiflow"):
            os.remove("/usr/local/bin/multiflow")
            print("Link simbólico /usr/local/bin/multiflow removido.")
    except Exception as e:
        print(f"Erro ao remover link simbólico: {e}")
    
    # 4. Remover diretório de instalação
    print("Removendo diretório de instalação...")
    try:
        install_dir = "/opt/multiflow"
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
            print(f"Diretório {install_dir} removido.")
    except Exception as e:
        print(f"Erro ao remover diretório de instalação: {e}")
    
    # 5. Limpar arquivos temporários
    print("Limpando arquivos temporários...")
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
                print(f"Erro ao remover {file}: {e}")
    
    # 6. Verificar e remover backups
    print("Verificando backups...")
    try:
        backup_dirs = [d for d in os.listdir("/opt") if d.startswith("multiflow.bak")]
        if backup_dirs:
            print(f"Encontrados {len(backup_dirs)} backups.")
            remove_backups = input("Deseja remover também os backups? (s/n): ")
            if remove_backups.lower() == "s":
                for backup in backup_dirs:
                    backup_path = os.path.join("/opt", backup)
                    shutil.rmtree(backup_path)
                    print(f"Backup {backup} removido.")
    except Exception as e:
        print(f"Erro ao verificar backups: {e}")
    
    print("\nMultiflow foi completamente removido do sistema.")
    print("Obrigado por usar o Multiflow!")
    
    input("\nPressione Enter para voltar ao menu principal...")

def main_menu():
    while True:
        clear_screen()
        print("\n=== MULTIFLOW ===")
        
        # Exibir o painel de informações do sistema
        show_system_panel()
        
        print("1. Gerenciar Usuários")
        print("2. Gerenciar Conexões")
        print("3. Remover Completamente Multiflow")
        print("4. Ferramentas")
        print("0. Sair")
        choice = input("\nEscolha uma opção: ")

        if choice == "1":
            menu_usuarios()
        elif choice == "2":
            menu_conexoes()
        elif choice == "3":
            uninstall_multiflow()
        elif choice == "4":
            menu_ferramentas()
        elif choice == "0":
            print("Saindo...")
            break
        else:
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

if __name__ == "__main__":
    main_menu()
