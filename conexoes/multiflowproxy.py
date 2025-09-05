#!/usr/bin/env python
# encoding: utf-8
# PAINEL DE GESTÃO PARA PROXY HÍBRIDO
# Unifica a funcionalidade de WebSocket (101) e HTTP/Socks (200 OK).
# ATUALIZADO PARA PYTHON 3
import socket, threading, select, sys, time, os, re

# --- Configurações ---
PASS = ''
LISTENING_ADDR = '0.0.0.0'
BUFLEN = 8196 * 8
TIMEOUT = 60
DEFAULT_HOST = "127.0.0.1:22"

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
                    break # Socket foi fechado

                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
        finally:
            self.close_all_connections()
            if self.soc:
                self.soc.close()

    def printLog(self, log):
        with self.logLock:
            # Garante que os logs não quebrem a interface do menu
            print("\r" + " " * 80 + "\r", end="")
            print(log)
            # Redesenha o prompt de input se o menu estiver ativo
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
                pass # Ignora se a conexão já foi removida
    
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
                pass # Ignora se o socket já foi fechado

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
        except:
            pass
        finally:
            self.clientClosed = True

        try:
            if not self.targetClosed:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
        except:
            pass
        finally:
            self.targetClosed = True

    def run(self):
        try:
            peek_buffer = self.client.recv(1024, socket.MSG_PEEK)
            if not peek_buffer:
                return # Cliente desconectou antes de enviar dados

            is_websocket = b'upgrade: websocket' in peek_buffer.lower()

            if is_websocket:
                self.client.sendall(RESPONSE_WS)
                self.client_buffer = self.client.recv(BUFLEN)
                self.process_request(is_websocket=True)
            else:
                self.client_buffer = self.client.recv(BUFLEN)
                if not self.client_buffer: return
                self.process_request(is_websocket=False)

        except Exception as e:
            self.server.printLog("Erro no handler para {}: {}".format(self.log, str(e)))
        finally:
            self.close()
            self.server.removeConn(self)
    
    def process_request(self, is_websocket):
        hostPort = self.findHeader(self.client_buffer, b'X-Real-Host')

        if hostPort == b'':
            hostPort = DEFAULT_HOST.encode('utf-8')

        split = self.findHeader(self.client_buffer, b'X-Split')
        if split != b'':
            self.client.recv(BUFLEN)

        if hostPort != b'':
            passwd = self.findHeader(self.client_buffer, b'X-Pass')
            
            hostPort_str = hostPort.decode('utf-8', errors='ignore')

            if len(PASS) != 0 and passwd.decode('utf-8', errors='ignore') == PASS:
                self.method_CONNECT(hostPort_str, not is_websocket)
            elif len(PASS) != 0 and passwd.decode('utf-8', errors='ignore') != PASS:
                self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
            elif hostPort_str.startswith('127.0.0.1') or hostPort_str.startswith('localhost'):
                self.method_CONNECT(hostPort_str, not is_websocket)
            else:
                self.client.send(b'HTTP/1.1 403 Forbidden!\r\n\r\n')
        else:
            self.server.printLog('- Sem X-Real-Host na conexão de {}'.format(self.log))
            self.client.send(b'HTTP/1.1 400 NoXRealHost!\r\n\r\n')

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
            if i != -1:
                port = int(host[i+1:])
                host = host[:i]
            else:
                port = 80
            
            (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]
            self.target = socket.socket(soc_family, soc_type, proto)
            self.targetClosed = False
            self.target.connect(address)
            return True
        except Exception as e:
            self.server.printLog("Erro ao conectar ao destino {} - {}".format(host, str(e)))
            return False

    def method_CONNECT(self, path, send_200_ok):
        self.server.printLog(self.log + ' - CONNECT ' + path)
        if self.connect_target(path):
            if send_200_ok:
                self.client.sendall(RESPONSE_HTTP)
            self.client_buffer = b''
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
                for in_ in recv:
                    try:
                        data = in_.recv(BUFLEN)
                        if data:
                            if in_ is self.target:
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

# --- Funções do Menu Interativo ---

def get_visible_length(s):
    """Calcula o comprimento visível de uma string, ignorando códigos de cor ANSI."""
    return len(re.sub(r'\033\[[0-9;]*m', '', s))

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def display_menu():
    clear_screen()
    
    # Linha de Status
    if not active_servers:
        status_line = "\033[1;37mStatus: \033[1;31mInativo\033[0m"
    else:
        ports = ", ".join(str(p) for p in sorted(active_servers.keys()))
        status_line = "\033[1;37mStatus: \033[1;32mAtivo\033[0m  \033[1;37mPortas: \033[1;33m{}\033[0m".format(ports)

    # Lógica de Centralização
    visible_len = get_visible_length(status_line)
    total_width = 50  # Largura interna do painel
    padding_left = (total_width - visible_len) // 2
    padding_right = total_width - visible_len - padding_left

    # Desenho do Painel
    print("\033[1;34m")
    print("  ╭" + "─" * total_width + "╮")
    print("  │" + " " * ((total_width - 32) // 2) + "\033[1;32mPAINEL MULTI-PROXY\033[1;34m" + " " * ((total_width - 32) // 2 + (total_width - 32) % 2) + "│")
    print("  ├" + "─" * total_width + "┤")
    print("  │" + " " * padding_left + status_line + " " * padding_right + "│")
    print("  ├" + "─" * total_width + "┤")
    print("  │" + " " * total_width + "│")
    print("  │   \033[1;36m[1]\033[0m \033[1;37mAbrir Porta\033[1;34m" + " " * (total_width - 30) + "│")
    print("  │   \033[1;36m[2]\033[0m \033[1;37mParar Porta\033[1;34m" + " " * (total_width - 28) + "│")
    print("  │" + " " * total_width + "│")
    print("  │   \033[1;31m[0]\033[0m \033[1;37mVoltar\033[1;34m" + " " * (total_width - 35) + "│")
    print("  │" + " " * total_width + "│")
    print("  ╰" + "─" * total_width + "╯")
    print("\033[0m")


def start_proxy():
    try:
        user_input = input("\n\033[1;33m  Digite a porta para abrir (ou 'voltar' para cancelar): \033[0m").lower()
        if user_input in ['voltar', 'v', 'cancelar', 'c']:
            return

        port = int(user_input)
        if port in active_servers:
            print("\n\033[1;31m  Erro: A porta {} já está em uso.\033[0m".format(port))
        elif not 0 < port < 65536:
            print("\n\033[1;31m  Erro: O número da porta deve estar entre 1 e 65535.\033[0m")
        else:
            server = Server(LISTENING_ADDR, port)
            server.start()
            time.sleep(0.1)
            if server.running:
                active_servers[port] = server
                print("\n\033[1;32m  Proxy iniciado com sucesso na porta {}.\033[0m".format(port))
            else:
                print("\n\033[1;31m  Falha ao iniciar o proxy. Verifique permissões ou se a porta já está ocupada.\033[0m")
    except ValueError:
        print("\n\033[1;31m  Erro: Por favor, digite um número de porta válido.\033[0m")
    
    if user_input not in ['voltar', 'v', 'cancelar', 'c']:
        input("\n\033[1;37m  Pressione Enter para voltar ao menu...\033[0m")

def stop_proxy():
    try:
        user_input = input("\n\033[1;33m  Digite a porta para fechar (ou 'voltar' para cancelar): \033[0m").lower()
        if user_input in ['voltar', 'v', 'cancelar', 'c']:
            return

        port = int(user_input)
        if port in active_servers:
            server = active_servers.pop(port)
            server.close()
            server.join()
            print("\n\033[1;32m  Proxy na porta {} fechado com sucesso.\033[0m".format(port))
        else:
            print("\n\033[1;31m  Erro: Não há nenhum proxy ativo na porta {}.\033[0m".format(port))
    except ValueError:
        print("\n\033[1;31m  Erro: Por favor, digite um número de porta válido.\033[0m")

    if user_input not in ['voltar', 'v', 'cancelar', 'c']:
        input("\n\033[1;37m  Pressione Enter para voltar ao menu...\033[0m")

main_loop_active = threading.Event()

def main():
    main_loop_active.set()
    while True:
        display_menu()
        choice = input("\n\033[1;33mEscolha uma opção: \033[0m")
        if choice == '1':
            start_proxy()
        elif choice == '2':
            stop_proxy()
        elif choice == '0':
            main_loop_active.clear()
            break
        else:
            print("\n\033[1;31mOpção inválida. Tente novamente.\033[0m")
            time.sleep(1)

    clear_screen()
    if active_servers:
        ports = ", ".join(str(p) for p in sorted(active_servers.keys()))
        print("\n\033[1;32m  Painel de controle minimizado.\033[0m")
        print("\033[1;37m  Os proxies continuam ativos nas portas: \033[1;33m{}\033[0m".format(ports))
        print("\n\033[1;31m  Pressione Ctrl+C a qualquer momento para PARAR TUDO e sair.\033[0m")
        
        while True:
            try:
                time.sleep(3600)
            except KeyboardInterrupt:
                break
    else:
        print("\n\033[1;32mSaindo do painel de controle. Nenhum proxy estava ativo.\033[0m")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass # A lógica de encerramento já está no loop principal
    finally:
        print("\n\033[1;31mSaindo... Fechando todas as conexões ativas...\033[0m")
        for port in list(active_servers.keys()):
            server = active_servers.pop(port)
            server.close()
        print("\033[1;32mTodos os proxies foram encerrados.\033[0m")

