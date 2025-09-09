#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Servidor de proxy híbrido com painel de gestão e auto-instalação de serviço.
"""

# --- Módulos Padrão ---
import socket
import threading
import select
import sys
import time
import os
import re
import json
import shutil
import signal

# --- Funções Auxiliares de Configuração ---
def _detect_local_ip():
    """Tenta detectar o IP local da máquina para um padrão mais inteligente."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# --- Configurações Globais do Proxy ---
PASS = ''  # Senha para autenticação. Deixe em branco para desativar.
LISTENING_ADDR = '0.0.0.0'  # Endereço de escuta para os servidores proxy.
BUFLEN = 8192  # Tamanho do buffer para leitura de sockets (8 KB).
TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "60")) # Configurável via variável de ambiente

# Padrão configurável via variável de ambiente ou detecta IP local
_env_default_host = os.environ.get("PROXY_DEFAULT_HOST")
DEFAULT_HOST = _env_default_host if _env_default_host else f"{_detect_local_ip()}:22"

# --- Configurações do Serviço Systemd ---
INSTALL_DIR = "/opt/proxy"
SCRIPT_NAME = "wsproxy.py"
SERVICE_NAME = "proxy.service"
STATE_FILE = os.path.join(INSTALL_DIR, "proxy_state.json")

# --- Respostas Padrão do Protocolo HTTP (em bytes) ---
RESPONSE_WS = b'HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n'
RESPONSE_HTTP = b'HTTP/1.1 200 Connection established\r\n\r\n'
RESPONSE_ERROR = b'HTTP/1.1 502 Bad Gateway\r\n\r\n'

# --- Variáveis de Estado de Execução ---
active_servers = {}
shutdown_requested = False
main_loop_active = threading.Event()

class Server(threading.Thread):
    """
    Gerencia um socket de escuta em uma porta específica.
    """
    def __init__(self, port):
        super().__init__(daemon=True)
        self.running = False
        self.host = LISTENING_ADDR
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.soc = None

    def print_log(self, log_message):
        """Imprime logs de forma segura."""
        with self.logLock:
            if '--service' in sys.argv:
                print(log_message, flush=True)
            else:
                sys.stdout.write("\r" + " " * 80 + "\r")
                print(log_message)
                if main_loop_active.is_set():
                    sys.stdout.write("\n\033[1;96m> \033[1;37mEscolha uma opção: \033[0m")
                    sys.stdout.flush()

    def run(self):
        """Inicia o servidor, escuta por conexões e cria handlers."""
        try:
            self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Adiciona TCP_NODELAY para baixa latência
            self.soc.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.soc.settimeout(2)
            self.soc.bind((self.host, self.port))
            self.soc.listen(0)
            self.running = True
            self.print_log(f"[OK] Proxy iniciado e escutando em {self.host}:{self.port}")
        except Exception as e:
            self.print_log(f"[ERRO] Erro ao iniciar o servidor na porta {self.port}: {e}")
            self.running = False
            return

        while self.running and not shutdown_requested:
            try:
                conn, addr = self.soc.accept()
                conn.setblocking(True)
                handler = ConnectionHandler(conn, self, addr)
                handler.start()
                self.add_conn(handler)
            except socket.timeout:
                continue
            except socket.error:
                self.print_log(f"[ERRO] socket.error na porta {self.port}, encerrando.")
                break
        
        self.close()

    def add_conn(self, conn):
        with self.threadsLock:
            if self.running:
                self.threads.append(conn)

    def remove_conn(self, conn):
        with self.threadsLock:
            try:
                self.threads.remove(conn)
            except ValueError:
                pass

    def close_all_connections(self):
        with self.threadsLock:
            for conn_thread in list(self.threads):
                conn_thread.close()

    def close(self):
        self.running = False
        self.close_all_connections()
        if self.soc:
            try:
                self.soc.shutdown(socket.SHUT_RDWR)
                self.soc.close()
            except socket.error:
                pass
        self.print_log(f"[INFO] Servidor na porta {self.port} foi encerrado.")

class ConnectionHandler(threading.Thread):
    """
    Gerencia uma única conexão de cliente.
    """
    # Headers para detecção de host/IP de destino e bypass de protocolo
    HOST_HEADERS = [
        b"x-forwarded-for",         # IP spoof
        b"x-real-ip",
        b"x-originating-ip",
        b"client-ip",
        b"true-client-ip",
        b"cf-connecting-ip",
        b"x-remote-ip",
        b"x-client-ip",
        b"x-forwarded",             # Forward variants
        b"forwarded-for",
        b"x-proxyuser-ip",
        b"wl-proxy-client-ip",
        b"x-cluster-client-ip",
        b"host",                    # Core host
        b"x-online-host",
        b"x-forwarded-host",
        b"x-original-url",
        b"x-forwarded-url",
        b"x-forwarded-path",
        b"x-host",
        b"x-original-host",
        b"x-gateway-host",
        b"x-http-method-override",  # Method overrides for protocol bypass
        b"x-forwarded-scheme",
        b"upgrade",                 # Upgrade to websocket/etc for tunneling
        b"x-real-host",             # Original script extras
        b"x-forward-host",
        b"x-remote-addr",
        b"forwarded",
    ]
    # Headers para descarte de payload dividido (evasão de inspeção de pacotes)
    SPLIT_HEADERS = [
        b"x-split",
        b"x-split-payload",
        b"split",
        b"x-split-extra",
    ]

    def __init__(self, client_socket: socket.socket, server, addr: tuple):
        super().__init__(daemon=True)
        self.client = client_socket
        self.server = server
        self.addr = addr
        self.client_buffer = b''
        self.target = None
        self.keepalive = True  # Assume keep-alive por padrão; será desativado se o cliente enviar 'Connection: close'
        self.keepalive_timeout = TIMEOUT
        self.log_prefix = f"Conexão de {addr[0]}:{addr[1]} na porta {server.port}"

    def find_header(self, data, name):
        """Procura por um cabeçalho de forma case-insensitive."""
        try:
            lower_data = data.lower()
            idx = lower_data.find(name + b":")
            if idx == -1: return b""
            
            start = idx + len(name) + 1
            while start < len(data) and data[start:start+1] in b" \t":
                start += 1
            
            end = lower_data.find(b"\r\n", start)
            if end == -1: end = len(data)
            
            return data[start:end].strip()
        except Exception:
            return b""

    def _close_target(self):
        """Fecha o socket de destino de forma segura."""
        if self.target:
            try:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
            except:
                pass
            self.target = None

    def connect_target(self, host_str):
        """Estabelece a conexão com o servidor de destino."""
        try:
            host, port_str = host_str.rsplit(":", 1)
            port = int(port_str)
        except (ValueError, TypeError):
            self.server.print_log(f"{self.log_prefix} - Host/porta inválido: '{host_str}'")
            return False

        try:
            soc_family, _, _, _, address = socket.getaddrinfo(host, port)[0]
            self.target = socket.socket(soc_family)
            # Adiciona TCP_NODELAY para baixa latência no túnel
            self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.target.connect(address)
            return True
        except Exception as e:
            self.server.print_log(f"{self.log_prefix} - Erro ao conectar em {host}:{port} - {e}")
            return False

    def run(self):
        """Lógica principal para manipular a conexão do cliente com suporte a keep-alive."""
        try:
            while self.keepalive:
                # Define um timeout para receber dados do cliente.
                self.client.settimeout(self.keepalive_timeout)
                try:
                    self.client_buffer = self.client.recv(BUFLEN)
                    if not self.client_buffer:
                        break  # Cliente fechou a conexão
                except socket.timeout:
                    self.server.print_log(f"{self.log_prefix} - Keep-alive timeout. Fechando conexão.")
                    break
                except ConnectionResetError:
                    self.server.print_log(f"{self.log_prefix} - Conexão reiniciada pelo cliente.")
                    break
                
                self.client.settimeout(None)

                # Verifica o header 'Connection'. Se 'close', desativa o keep-alive para a próxima iteração.
                connection_header = self.find_header(self.client_buffer, b'connection')
                if b'close' in connection_header.lower():
                    self.keepalive = False
                
                is_websocket = b'upgrade: websocket' in self.client_buffer.lower()
                if is_websocket:
                    self.keepalive = False

                host_port_str = DEFAULT_HOST
                for header in self.HOST_HEADERS:
                    found_host = self.find_header(self.client_buffer, header)
                    if found_host:
                        host_port_str = found_host.decode('utf-8', errors='ignore')
                        if ":" not in host_port_str:
                            host_port_str += ":80"
                        break

                for header in self.SPLIT_HEADERS:
                    if self.find_header(self.client_buffer, header):
                        self.client.recv(BUFLEN)
                        break
                
                if PASS:
                    passwd = self.find_header(self.client_buffer, b'x-pass').decode('utf-8', errors='ignore')
                    if passwd != PASS:
                        self.client.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                        self.keepalive = False  # Encerra após falha de autenticação
                        continue

                self.server.print_log(f"{self.log_prefix} - TÚNEL para {host_port_str}")
                if self.connect_target(host_port_str):
                    response = RESPONSE_WS if is_websocket else RESPONSE_HTTP
                    self.client.sendall(response)
                    self.do_tunnel()
                else:
                    self.client.sendall(RESPONSE_ERROR)
                    self.keepalive = False  # Encerra se a conexão de destino falhar

                # Fecha o socket de destino após cada túnel
                self._close_target()

        except Exception as e:
            self.server.print_log(f"{self.log_prefix} - Erro no handler: {e}")
        finally:
            self.close()
            self.server.remove_conn(self)

    def do_tunnel(self):
        """Inicia o encaminhamento de dados."""
        sockets = [self.client, self.target]
        count = 0
        error = False
        while not error and not shutdown_requested:
            count += 1
            readable, _, exceptional = select.select(sockets, [], sockets, 3)
            
            if exceptional:
                error = True
                break
            
            if not readable and count > (TIMEOUT / 3):
                error = True
                break
            
            for sock in readable:
                try:
                    data = sock.recv(BUFLEN)
                    if not data:
                        error = True
                        break
                    
                    if sock is self.client:
                        self.target.sendall(data)
                    else:
                        self.client.sendall(data)
                    count = 0
                except socket.error:
                    error = True
                    break

    def close(self):
        """Fecha os sockets de forma segura."""
        self._close_target()  # Garante que o alvo seja fechado
        try:
            self.client.shutdown(socket.SHUT_RDWR)
            self.client.close()
        except:
            pass

# O restante do código (painel de gestão, etc.) permanece idêntico
# --- Funções de Serviço e Persistência ---

def is_service_installed():
    return os.path.exists(f"/etc/systemd/system/{SERVICE_NAME}")

def get_ports_from_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    return []

def save_ports_to_state(ports):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(ports, f)

# --- Funções do Painel ---

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def display_menu():
    clear_screen()
    display_ports = sorted(get_ports_from_state())

    print("\033[1;36m" + "═" * 50)
    print(" PAINEL DE GESTÃO - PROXY HÍBRIDO")
    print("═" * 50)

    if display_ports:
        print("\033[1;37mStatus: \033[1;32mAtivo")
        print("\033[1;37mPortas: \033[1;33m" + " ".join(map(str, display_ports)))
    else:
        print("\033[1;37mStatus: \033[1;31mInativo")
        print("\033[1;37mPortas: \033[1;37mNenhuma porta ativa")
    
    print("\033[1;36m" + "─" * 50)
    print("\033[1;97mOPÇÕES:")
    print("  \033[1;92m[1]\033[1;37m Adicionar Nova Porta")
    print("  \033[1;91m[2]\033[1;37m Remover Porta")
    print("  \033[1;91m[3]\033[1;37m Desativar o Proxy")
    print("  \033[1;90m[0]\033[1;37m Sair do Painel")
    print("\033[1;36m" + "═" * 50 + "\033[0m")

def manage_port(action):
    if os.geteuid() != 0:
        print("\n\033[1;31m[ERRO] Esta operação requer privilégios de root. Use 'sudo'.\033[0m")
        input("\n\033[1;90mPressione Enter para voltar...\033[0m")
        return
        
    if action == 'add' and not is_service_installed():
        print("\n\033[1;33m[INFO] Serviço não instalado. Instalando automaticamente...\033[0m")
        time.sleep(1)
        install_service()
        if not is_service_installed():
            print("\n\033[1;31m[ERRO] A instalação do serviço falhou. Não é possível adicionar a porta.\033[0m")
            input("\n\033[1;90mPressione Enter para voltar...\033[0m")
            return

    clear_screen()
    ports = get_ports_from_state()
    
    if action == 'add':
        print("\033[1;92m--- Adicionar Nova Porta ---\033[0m")
        prompt = "Digite a porta a ser adicionada"
    else:
        print("\033[1;91m--- Remover Porta Existente ---\033[0m")
        if not ports:
            print("\n\033[1;33m[INFO] Nenhuma porta está configurada no serviço.\033[0m")
            input("\n\033[1;90mPressione Enter para voltar...\033[0m")
            return
        print(f"Portas ativas: {', '.join(map(str, sorted(ports)))}")
        prompt = "Digite a porta a ser removida"

    try:
        user_input = input(f"\n\033[1;37m{prompt} \033[1;90m(ou 'v' para voltar)\033[1;37m: \033[1;33m").lower()
        if user_input.startswith('v'): return

        port = int(user_input)
        if not (0 < port < 65536): raise ValueError("Porta fora do intervalo válido")

        if action == 'add':
            if port in ports:
                print(f"\n\033[1;31m[ERRO] A porta {port} já está ativa.\033[0m")
            else:
                ports.append(port)
                save_ports_to_state(ports)
                print(f"\n\033[1;93m[INFO] Reiniciando serviço para adicionar a porta {port}...\033[0m")
                os.system(f"systemctl restart {SERVICE_NAME}")
                print(f"\n\033[1;32m[OK] Porta {port} adicionada com sucesso!\033[0m")
        else:
            if port not in ports:
                print(f"\n\033[1;31m[ERRO] A porta {port} não está na lista de portas ativas.\033[0m")
            else:
                ports.remove(port)
                save_ports_to_state(ports)
                
                if not ports:
                    print(f"\n\033[1;33m[INFO] Última porta removida. Desinstalando o serviço...\033[0m")
                    time.sleep(1)
                    uninstall_service(feedback=True)
                else:
                    print(f"\n\033[1;93m[INFO] Reiniciando serviço para remover a porta {port}...\033[0m")
                    os.system(f"systemctl restart {SERVICE_NAME}")
                    print(f"\n\033[1;32m[OK] Porta {port} removida com sucesso!\033[0m")

    except ValueError:
        print("\n\033[1;31m[ERRO] Entrada inválida. Por favor, digite um número de porta válido.\033[0m")
    
    input("\n\033[1;90mPressione Enter para voltar ao menu...\033[0m")

def deactivate_proxy():
    clear_screen()
    print("\033[1;91m--- Desativar e Desinstalar o Proxy ---\033[0m")
    if not is_service_installed():
        print("\n\033[1;33m[INFO] O serviço do proxy não está instalado.\033[0m")
        input("\n\033[1;90mPressione Enter para voltar...\033[0m")
        return
    
    choice = input("\n\033[1;91mIsto irá parar o serviço e remover todos os arquivos. Deseja continuar? (s/N): \033[0m").lower().strip()
    if choice == 's':
        uninstall_service(feedback=True)
    else:
        print("\n\033[1;37mOperação cancelada.\033[0m")

    input("\n\033[1;90mPressione Enter para voltar ao menu...\033[0m")

def install_service():
    if os.geteuid() != 0:
        print("\n\033[1;31m[ERRO] A instalação requer privilégios de root. Use 'sudo'.\033[0m")
        return
    
    print("\033[1;96m[INFO] Iniciando a instalação do serviço...\033[0m")
    script_path = os.path.abspath(__file__)
    install_path = os.path.join(INSTALL_DIR, SCRIPT_NAME)
    service_path = f"/etc/systemd/system/{SERVICE_NAME}"

    service_content = f"""[Unit]
Description=Servico de Proxy Hibrido (Python)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={INSTALL_DIR}
ExecStart=/usr/bin/python3 {install_path} --service
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    try:
        os.makedirs(INSTALL_DIR, exist_ok=True)
        shutil.copy(script_path, install_path)
        with open(service_path, "w") as f: f.write(service_content)
        os.system("systemctl daemon-reload")
        os.system(f"systemctl enable {SERVICE_NAME}")
        print(f"\n\033[1;32m[OK] Serviço instalado com sucesso!\033[0m")
        print("\033[1;37mUse 'sudo systemctl start/status/stop' para controlar.\033[0m")
    except Exception as e:
        print(f"\n\033[1;31m[ERRO] Erro durante a instalação: {e}\033[0m")
        uninstall_service(feedback=False)

def uninstall_service(feedback=True):
    if os.geteuid() != 0:
        if feedback: print("\n\033[1;31m[ERRO] A desinstalação requer privilégios de root. Use 'sudo'.\033[0m")
        return
    
    if feedback: print("\033[1;91m[INFO] Iniciando a desinstalação do serviço...\033[0m")
    service_path = f"/etc/systemd/system/{SERVICE_NAME}"
    
    try:
        os.system(f"systemctl stop {SERVICE_NAME} >/dev/null 2>&1")
        os.system(f"systemctl disable {SERVICE_NAME} >/dev/null 2>&1")
        if os.path.exists(service_path): os.remove(service_path)
        os.system("systemctl daemon-reload")
        if os.path.isdir(INSTALL_DIR): shutil.rmtree(INSTALL_DIR)
        if feedback: print("\n\033[1;32m[OK] Serviço desinstalado com sucesso!\033[0m")
    except Exception as e:
        if feedback: print(f"\n\033[1;31m[ERRO] Erro durante a desinstalação: {e}\033[0m")

# --- Lógica de Execução Principal ---

def signal_handler(signum, frame):
    global shutdown_requested
    if not shutdown_requested:
        print("\n\033[1;31m[AVISO] Sinal de encerramento recebido...\033[0m")
        shutdown_requested = True
        cleanup_and_exit()

def cleanup_and_exit():
    print("\n\033[1;93m[INFO] Fechando todas as conexões e servidores ativos...\033[0m")
    for port in list(active_servers.keys()):
        server = active_servers.pop(port)
        server.close()
    print("\033[1;32m[OK] Todos os processos foram encerrados com sucesso!\033[0m")
    sys.exit(0)

def main_panel():
    main_loop_active.set()
    while True:
        display_menu()
        choice = input("\033[1;96m> \033[1;37mEscolha uma opção: \033[1;33m").lower().strip()
        
        if choice == '1':
            manage_port('add')
        elif choice == '2':
            manage_port('remove')
        elif choice == '3':
            deactivate_proxy()
        elif choice == '0':
            main_loop_active.clear()
            break
        else:
            print("\n\033[1;31m[ERRO] Opção inválida. Tente novamente.\033[0m")
            time.sleep(1)
            
    clear_screen()
    print("\n\033[1;32mPainel encerrado.\033[0m")
    if is_service_installed():
        print("\033[1;37mO serviço permanente continua a funcionar em segundo plano.\033[0m")

def main_service():
    print("[INFO] Iniciando proxy em modo de serviço...")
    ports = get_ports_from_state()
    if not ports:
        print("[AVISO] Nenhuma porta configurada no ficheiro de estado. Serviço em espera.")
    
    for port in ports:
        if isinstance(port, int) and 0 < port < 65536:
            server = Server(port)
            server.start()
            if server.running:
                active_servers[port] = server
    
    if active_servers:
        print(f"[OK] Serviço ativo nas portas: {', '.join(map(str, sorted(active_servers.keys())))}")
    
    try:
        while not shutdown_requested:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        if not shutdown_requested:
             signal_handler(signal.SIGINT, None)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if '--service' in sys.argv:
        main_service()
    else:
        try:
            main_panel()
        except SystemExit:
            pass
        except Exception as e:
            print(f"\n\033[1;31m[ERRO] Erro inesperado no painel: {e}\033[0m")

