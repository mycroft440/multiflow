#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
import signal
import time
import importlib.util
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

def main_menu():
    while True:
        clear_screen()
        print("\n=== MULTIFLOW ===")
        print("1. Gerenciar Usuários")
        print("2. Gerenciar Conexões")
        print("0. Sair")
        choice = input("\nEscolha uma opção: ")

        if choice == "1":
            menu_usuarios()
        elif choice == "2":
            menu_conexoes()
        elif choice == "0":
            print("Saindo...")
            break
        else:
            print("Opção inválida!")

        input("\nPressione Enter para continuar...")

if __name__ == "__main__":
    main_menu()
