#!/usr/bin/env python
# encoding: utf-8
# PAINEL DE GESTÃO PARA PROXY HÍBRIDO
# Unifica WebSocket (101) e HTTP/Socks (200 OK) com autoinstalação de serviço.
# ATUALIZADO PARA PYTHON 3
import socket, threading, select, sys, time, os, re, json, shutil

# --- Configurações ---
PASS = ''
LISTENING_ADDR = '0.0.0.0'
BUFLEN = 8196 * 8
TIMEOUT = 60
DEFAULT_HOST = "127.0.0.1:22"

# --- Configurações do Serviço ---
# ATENÇÃO: Altere estes caminhos se desejar instalar o proxy noutro local.
INSTALL_DIR = "/opt/proxy"
SCRIPT_NAME = "wsproxy.py"
SERVICE_NAME = "proxy.service"
STATE_FILE = os.path.join(INSTALL_DIR, "proxy_state.json")

# --- Respostas Padrão do Protocolo HTTP ---
RESPONSE_WS = b'HTTP/1.1 101 Switching Protocols\r\n\r\n'
RESPONSE_HTTP = b'HTTP/1.1 200 Connection established\r\n\r\n'
RESPONSE_ERROR = b'HTTP/1.1 502 Bad Gateway\r\n\r\n'

# --- Gerenciador de Servidores Ativos ---
active_servers = {}

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.soc = None

    def run(self):
        try:
            self.soc = socket.socket(socket.AF_INET)
            self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.soc.settimeout(2)
            self.soc.bind((self.host, self.port))
            self.soc.listen(0)
            self.running = True
        except Exception as e:
            self.printLog("Erro ao iniciar o servidor na porta {}: {}".format(self.port, e))
            self.running = False
            return

        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                except socket.timeout:
                    continue
                except socket.error:
                    break

                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
        finally:
            self.close_all_connections()
            if self.soc:
                self.soc.close()

    def printLog(self, log):
        with self.logLock:
            if '--service' in sys.argv:
                print(log, flush=True)
            else:
                print("\r" + " " * 80 + "\r", end="")
                print(log)
                if main_loop_active.is_set():
                    print("\n\033[1;33mEscolha uma opção: \033[0m", end="", flush=True)

    def addConn(self, conn):
        with self.threadsLock:
            if self.running:
                self.threads.append(conn)

    def removeConn(self, conn):
        with self.threadsLock:
            try:
                self.threads.remove(conn)
            except ValueError:
                pass
    
    def close_all_connections(self):
        with self.threadsLock:
            threads = list(self.threads)
            for c in threads:
                c.close()

    def close(self):
        self.running = False
        self.close_all_connections()
        if self.soc:
            try:
                self.soc.shutdown(socket.SHUT_RDWR)
                self.soc.close()
            except socket.error:
                pass

class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = b''
        self.server = server
        self.log = 'Conexão: {} na porta {}'.format(str(addr), self.server.port)

    def close(self):
        try:
            if not self.clientClosed:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
        except: pass
        finally: self.clientClosed = True

        try:
            if not self.targetClosed:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
        except: pass
        finally: self.targetClosed = True

    def run(self):
        try:
            peek_buffer = self.client.recv(1024, socket.MSG_PEEK)
            if not peek_buffer: return

            is_websocket = b'upgrade: websocket' in peek_buffer.lower()

            if is_websocket:
                self.client.sendall(RESPONSE_WS)
                self.client_buffer = self.client.recv(BUFLEN)
            else:
                self.client_buffer = self.client.recv(BUFLEN)
            
            if self.client_buffer:
                self.process_request()

        except Exception as e:
            self.server.printLog("Erro no handler para {}: {}".format(self.log, str(e)))
        finally:
            self.close()
            self.server.removeConn(self)
    
    def process_request(self):
        hostPort = self.findHeader(self.client_buffer, b'X-Real-Host')
        if not hostPort:
            hostPort = DEFAULT_HOST.encode('utf-8')

        if self.findHeader(self.client_buffer, b'X-Split'):
            self.client.recv(BUFLEN)
        
        passwd = self.findHeader(self.client_buffer, b'X-Pass')
        hostPort_str = hostPort.decode('utf-8', errors='ignore')

        allow = False
        if len(PASS) == 0:
            allow = True
        elif passwd.decode('utf-8', errors='ignore') == PASS:
            allow = True
        
        if allow:
            self.method_CONNECT(hostPort_str, b'upgrade: websocket' not in self.client_buffer.lower())
        else:
            self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')

    def findHeader(self, head, header):
        aux = head.find(header + b': ')
        if aux == -1: return b''
        head = head[aux+len(header)+2:]
        aux = head.find(b'\r\n')
        if aux == -1: return b''
        return head[:aux]

    def connect_target(self, host):
        try:
            i = host.find(':')
            port = int(host[i+1:]) if i != -1 else 80
            host = host[:i] if i != -1 else host
            
            soc_family, _, _, _, address = socket.getaddrinfo(host, port)[0]
            self.target = socket.socket(soc_family)
            self.targetClosed = False
            self.target.connect(address)
            return True
        except Exception as e:
            self.server.printLog(f"Erro ao conectar ao destino {host}:{port} - {e}")
            return False

    def method_CONNECT(self, path, send_200_ok):
        self.server.printLog(f"{self.log} - CONNECT {path}")
        if self.connect_target(path):
            if send_200_ok:
                self.client.sendall(RESPONSE_HTTP)
            self.doCONNECT()
        else:
            self.client.sendall(RESPONSE_ERROR)

    def doCONNECT(self):
        socs = [self.client, self.target]
        count = 0
        error = False
        while not error:
            count += 1
            (recv, _, err) = select.select(socs, [], socs, 3)
            if err: error = True
            if recv:
                for sock in recv:
                    try:
                        data = sock.recv(BUFLEN)
                        if data:
                            if sock is self.target:
                                self.client.send(data)
                            else:
                                self.target.sendall(data)
                            count = 0
                        else:
                            error = True
                            break
                    except:
                        error = True
                        break
            if count > TIMEOUT: error = True

# --- Funções de Serviço e Persistência ---

def save_state():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(list(active_servers.keys()), f)

def load_state_and_start_proxies():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                ports = json.load(f)
            print("\033[1;32mRestaurando sessão anterior...\033[0m")
            for port in ports:
                if isinstance(port, int) and 0 < port < 65536:
                     server = Server(LISTENING_ADDR, port)
                     server.start()
                     if server.running:
                         active_servers[port] = server
                         print(f"\033[1;32m  -> Proxy reativado na porta {port}.\033[0m")
    except Exception:
        print("\033[1;31mFicheiro de estado corrompido ou ilegível.\033[0m")
    
    if '--service' not in sys.argv: time.sleep(2)

# --- Funções do Painel ---

def display_menu():
    clear_screen()
    status_line = "\033[1;37mStatus: \033[1;31mInativo\033[0m"
    if active_servers:
        ports = ", ".join(str(p) for p in sorted(active_servers.keys()))
        status_line = f"\033[1;37mStatus: \033[1;32mAtivo\033[0m  \033[1;37mPortas: \033[1;33m{ports}\033[0m"
    
    total_width = 50
    visible_len = len(re.sub(r'\033\[[0-9;]*m', '', status_line))
    padding = " " * ((total_width - visible_len) // 2)
    
    print("\033[1;34m  ╭" + "─" * total_width + "╮")
    print(f"  │\033[1;32m{'PAINEL DE GESTÃO DO PROXY HÍBRIDO'.center(total_width)}\033[1;34m│")
    print("  ├" + "─" * total_width + "┤")
    print(f"  │{padding}{status_line}{padding}{' ' if (total_width - visible_len) % 2 != 0 else ''}│")
    print("  ├" + "─" * total_width + "┤")
    print("  │" + " " * total_width + "│")
    print("  │   \033[1;36m[1]\033[0m \033[1;37mIniciar Proxy numa Porta" + " " * (total_width - 30) + "│")
    print("  │   \033[1;36m[2]\033[0m \033[1;37mParar Proxy numa Porta" + " " * (total_width - 28) + "│")
    print("  │" + " " * total_width + "│")
    print("  │   \033[1;31m[0]\033[0m \033[1;37mMinimizar Painel (Manter Ativo)" + " " * (total_width - 35) + "│")
    print("  │" + " " * total_width + "│")
    print("  ╰" + "─" * total_width + "╯\033[0m")

def start_proxy_port():
    try:
        user_input = input("\n\033[1;33m  Digite a porta para abrir (ou 'voltar'): \033[0m").lower()
        if user_input.startswith('v'): return

        port = int(user_input)
        if port in active_servers:
            print(f"\n\033[1;31m  Erro: A porta {port} já está em uso.\033[0m")
        elif not 0 < port < 65536:
            print("\n\033[1;31m  Erro: Porta inválida.\033[0m")
        else:
            server = Server(LISTENING_ADDR, port)
            server.start()
            if server.running:
                active_servers[port] = server
                save_state()
                print(f"\n\033[1;32m  Proxy iniciado com sucesso na porta {port}.\033[0m")
    except ValueError:
        print("\n\033[1;31m  Erro: Entrada inválida.\033[0m")
    
    if not user_input.startswith('v'):
        input("\n\033[1;37m  Pressione Enter para voltar...\033[0m")

def stop_proxy_port():
    try:
        user_input = input("\n\033[1;33m  Digite a porta para fechar (ou 'voltar'): \033[0m").lower()
        if user_input.startswith('v'): return

        port = int(user_input)
        if port in active_servers:
            active_servers.pop(port).close()
            save_state()
            print(f"\n\033[1;32m  Proxy na porta {port} fechado com sucesso.\033[0m")
        else:
            print(f"\n\033[1;31m  Erro: Não há proxy ativo na porta {port}.\033[0m")
    except ValueError:
        print("\n\033[1;31m  Erro: Entrada inválida.\033[0m")

    if not user_input.startswith('v'):
        input("\n\033[1;37m  Pressione Enter para voltar...\033[0m")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# --- Lógica Principal e Gestão do Serviço ---

def display_help():
    print("\033[1;32mProxy Híbrido com Gestão de Serviço\033[0m")
    print("Uso: python3 wsproxy.py [opção]")
    print("\nOpções:")
    print("  (nenhuma)            Inicia o painel de controlo interativo.")
    print("  --install-service    Instala o proxy como um serviço systemd (requer sudo).")
    print("  --uninstall-service  Remove o serviço systemd do sistema (requer sudo).")
    print("  --service            (Uso interno) Executa o script como um serviço.")
    print("  --help               Mostra esta mensagem de ajuda.")

def install_service():
    if os.geteuid() != 0:
        print("\033[1;31mErro: A instalação do serviço requer privilégios de root. Use 'sudo'.\033[0m")
        sys.exit(1)
    
    print("\033[1;33mIniciando a instalação do serviço...\033[0m")
    
    script_path = os.path.abspath(__file__)
    install_path = os.path.join(INSTALL_DIR, SCRIPT_NAME)
    service_path = f"/etc/systemd/system/{SERVICE_NAME}"
    
    service_content = f"""[Unit]
Description=Serviço de Proxy Híbrido (Python)
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
        print(f" -> Criando diretório de instalação: {INSTALL_DIR}")
        os.makedirs(INSTALL_DIR, exist_ok=True)
        
        print(f" -> Copiando script para {install_path}")
        shutil.copy(script_path, install_path)
        
        print(f" -> Criando ficheiro de serviço: {service_path}")
        with open(service_path, "w") as f:
            f.write(service_content)
            
        print(" -> Recarregando o daemon do systemd...")
        os.system("systemctl daemon-reload")
        
        print(" -> Habilitando o serviço para iniciar no boot...")
        os.system(f"systemctl enable {SERVICE_NAME}")
        
        print(" -> Iniciando o serviço agora...")
        os.system(f"systemctl start {SERVICE_NAME}")
        
        print("\n\033[1;32mServiço instalado e iniciado com sucesso!\033[0m")
        print(f"Use 'sudo systemctl status {SERVICE_NAME}' para verificar.")
        
    except Exception as e:
        print(f"\n\033[1;31mOcorreu um erro durante a instalação: {e}\033[0m")
        uninstall_service(feedback=False) # Tenta reverter
        sys.exit(1)

def uninstall_service(feedback=True):
    if os.geteuid() != 0:
        print("\033[1;31mErro: A desinstalação do serviço requer privilégios de root. Use 'sudo'.\033[0m")
        sys.exit(1)

    if feedback: print("\033[1;33mIniciando a desinstalação do serviço...\033[0m")
    
    service_path = f"/etc/systemd/system/{SERVICE_NAME}"
    
    try:
        print(" -> Parando o serviço...")
        os.system(f"systemctl stop {SERVICE_NAME}")
        
        print(" -> Desabilitando o serviço...")
        os.system(f"systemctl disable {SERVICE_NAME}")
        
        if os.path.exists(service_path):
            print(f" -> Removendo ficheiro de serviço: {service_path}")
            os.remove(service_path)
            
        print(" -> Recarregando o daemon do systemd...")
        os.system("systemctl daemon-reload")
        
        if os.path.isdir(INSTALL_DIR):
            print(f" -> Removendo diretório de instalação: {INSTALL_DIR}")
            shutil.rmtree(INSTALL_DIR)
        
        if feedback: print("\n\033[1;32mServiço desinstalado com sucesso!\033[0m")
        
    except Exception as e:
        if feedback: print(f"\n\033[1;31mOcorreu um erro durante a desinstalação: {e}\033[0m")
        sys.exit(1)

main_loop_active = threading.Event()

def main_panel():
    main_loop_active.set()
    load_state_and_start_proxies()

    while True:
        display_menu()
        choice = input("\n\033[1;33mEscolha uma opção: \033[0m")
        if choice == '1': start_proxy_port()
        elif choice == '2': stop_proxy_port()
        elif choice == '0':
            main_loop_active.clear()
            break
        else:
            print("\n\033[1;31mOpção inválida.\033[0m"); time.sleep(1)

    clear_screen()
    if active_servers:
        ports = ", ".join(str(p) for p in sorted(active_servers.keys()))
        print(f"\n\033[1;32m  Painel minimizado.\033[0m\n\033[1;37m  Proxies ativos em: \033[1;33m{ports}\033[0m")
        print("\n\033[1;31m  Pressione Ctrl+C para PARAR TUDO.\033[0m")
    else:
        print("\n\033[1;32mSaindo do painel. Nenhum proxy ativo.\033[0m")

def main_service():
    print("Iniciando proxy em modo de serviço...")
    load_state_and_start_proxies()
    if not active_servers:
        print("Nenhuma porta configurada. A sair.")
        return
    print(f"Proxy ativo em: {', '.join(str(p) for p in sorted(active_servers.keys()))}")
    while True: time.sleep(3600)

if __name__ == '__main__':
    if '--install-service' in sys.argv:
        install_service()
    elif '--uninstall-service' in sys.argv:
        uninstall_service()
    elif '--help' in sys.argv:
        display_help()
    else:
        try:
            if '--service' in sys.argv:
                main_service()
            else:
                main_panel()
        except KeyboardInterrupt:
            print("\n\033[1;31mSinal de interrupção recebido.\033[0m")
        finally:
            print("\n\033[1;31mFechando todas as conexões ativas...\033[0m")
            for port in list(active_servers.keys()):
                active_servers.pop(port).close()
            print("\033[1;32mTodos os proxies foram encerrados.\033[0m")

