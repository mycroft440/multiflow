#!/usr/bin/env python3
# encoding: utf-8
import socket, threading, select, sys, time
import os
import json
import subprocess
from os import system
# Arquivo de configuração
CONFIG_FILE = '/etc/proxy_config.json'
SERVICE_FILE = '/etc/systemd/system/proxy-multiflow.service'
PROXY_SCRIPT = '/usr/local/bin/proxy_multiflow.py'
# Configuração padrão
DEFAULT_CONFIG = {
    'installed': False,
    'active': False,
    'ports': [80],
    'ip': '0.0.0.0',
    'password': '',
    'default_host': '0.0.0.0:22'
}
#conexao
IP = '0.0.0.0'
try:
   PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
except:
   PORT = 80
PASS = ''
BUFLEN = 8196 * 8
TIMEOUT = 60  # Mantido para compatibilidade, mas não usado para fechamento rígido
MSG = 'Connection Established'
COR = '<font color="null">'
FTAG = '</font>'
DEFAULT_HOST = '0.0.0.0:22'
RESPONSE = "HTTP/1.1 200 " + COR + MSG + FTAG + "\r\n\r\n"
HEARTBEAT_INTERVAL = 30  # Segundos para heartbeat se idle
SELECT_TIMEOUT = 10  # Aumentado para reduzir overhead em idle

class ConfigManager:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.load_config()
   
    def load_config(self):
        """Carrega configuração do arquivo"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            else:
                self.config = DEFAULT_CONFIG.copy()
                self.save_config()
        except:
            self.config = DEFAULT_CONFIG.copy()
   
    def save_config(self):
        """Salva configuração no arquivo"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"\033[1;31mErro ao salvar configuração: {e}\033[0m")
            return False
   
    def is_installed(self):
        """Verifica se o proxy está instalado"""
        return self.config.get('installed', False) and os.path.exists(SERVICE_FILE)
   
    def is_active(self):
        """Verifica se o proxy está ativo"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'proxy-multiflow'],
                                  capture_output=True, text=True)
            return result.stdout.strip() == 'active'
        except:
            return False
   
    def get_ports(self):
        """Retorna lista de portas configuradas"""
        return self.config.get('ports', [80])
   
    def add_port(self, port):
        """Adiciona uma porta"""
        if port not in self.config['ports']:
            self.config['ports'].append(port)
            self.save_config()
            return True
        return False
   
    def remove_port(self, port):
        """Remove uma porta"""
        if port in self.config['ports'] and len(self.config['ports']) > 1:
            self.config['ports'].remove(port)
            self.save_config()
            return True
        return False
class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
    def run(self):
        self.soc = socket.socket(socket.AF_INET)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        self.soc.bind((self.host, self.port))
        self.soc.listen(0)
        self.running = True
        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                    # Configura TCP Keep-Alive no client socket
                    c.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
                except socket.timeout:
                    continue
               
                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
        finally:
            self.running = False
            self.soc.close()
           
    def printLog(self, log):
        self.logLock.acquire()
        print(log)
        self.logLock.release()
   
    def addConn(self, conn):
        try:
            self.threadsLock.acquire()
            if self.running:
                self.threads.append(conn)
        finally:
            self.threadsLock.release()
                   
    def removeConn(self, conn):
        try:
            self.threadsLock.acquire()
            self.threads.remove(conn)
        finally:
            self.threadsLock.release()
               
    def close(self):
        try:
            self.running = False
            self.threadsLock.acquire()
           
            threads = list(self.threads)
            for c in threads:
                c.close()
        finally:
            self.threadsLock.release()
class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = ''
        self.server = server
        self.log = 'Conexao: ' + str(addr)
        self.keep_alive = False  # Flag para conexões persistentes
        self.last_activity = time.time()  # Para heartbeats

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
        while True:  # Loop para suportar conexões persistentes
            try:
                self.client_buffer = self.client.recv(BUFLEN).decode('utf-8')
                if not self.client_buffer:
                    break  # Fecha se recv vazio (conexão fechada)

                # Verifica se é keep-alive para persistência
                if 'Connection: keep-alive' in self.client_buffer:
                    self.keep_alive = True

                hostPort = self.findHeader(self.client_buffer, 'X-Real-Host')
               
                if hostPort == '':
                    hostPort = DEFAULT_HOST
                split = self.findHeader(self.client_buffer, 'X-Split')
                if split != '':
                    self.client.recv(BUFLEN)
               
                if hostPort != '':
                    passwd = self.findHeader(self.client_buffer, 'X-Pass')
                   
                    if len(PASS) != 0 and passwd == PASS:
                        self.method_CONNECT(hostPort)
                    elif len(PASS) != 0 and passwd != PASS:
                        self.client.send('HTTP/1.1 400 WrongPass!\r\n\r\n'.encode('utf-8'))
                        break
                    elif hostPort.startswith(IP):
                        self.method_CONNECT(hostPort)
                    else:
                        self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n'.encode('utf-8'))
                        break
                else:
                    print('- No X-Real-Host!')
                    self.client.send('HTTP/1.1 400 NoXRealHost!\r\n\r\n'.encode('utf-8'))
                    break

                # Se não keep-alive, sai do loop após handling
                if not self.keep_alive:
                    break

            except Exception as e:
                if 'timeout' in str(e).lower() or 'broken pipe' in str(e).lower():  # Recuperação suave em erros transitórios
                    self.server.printLog(self.log + ' - transient error, retrying: ' + str(e))
                    time.sleep(1)  # Pequeno delay antes de retry
                    continue
                else:
                    self.log += ' - error: ' + str(e)
                    self.server.printLog(self.log)
                    break
        self.close()
        self.server.removeConn(self)

    def findHeader(self, head, header):
        aux = head.find(header + ': ')
   
        if aux == -1:
            return ''
        aux = head.find(':', aux)
        head = head[aux+2:]
        aux = head.find('\r\n')
        if aux == -1:
            return ''
        return head[:aux]

    def connect_target(self, host):
        i = host.find(':')
        if i != -1:
            port = int(host[i+1:])
            host = host[:i]
        else:
            if self.method=='CONNECT':
                port = 443
            else:
                port = 22
        (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]
        self.target = socket.socket(soc_family, soc_type, proto)
        self.targetClosed = False
        self.target.connect(address)
        # Configura TCP Keep-Alive no target socket
        self.target.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)

    def method_CONNECT(self, path):
        self.method = 'CONNECT'
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall(RESPONSE.encode('utf-8'))
        self.client_buffer = ''
        self.server.printLog(self.log)
        self.doCONNECT()

    def doCONNECT(self):
        socs = [self.client, self.target]
        error = False
        poller = select.poll()
        poller.register(self.client, select.POLLIN | select.POLLHUP | select.POLLERR)
        poller.register(self.target, select.POLLIN | select.POLLHUP | select.POLLERR)
        self.last_activity = time.time()

        while not error:
            try:
                events = poller.poll(SELECT_TIMEOUT * 1000)  # Em ms
                if not events:
                    # Sem eventos: verifica heartbeat se idle
                    if time.time() - self.last_activity > HEARTBEAT_INTERVAL:
                        # Envia heartbeat (byte nulo para manter vivo sem interferir)
                        self.target.send(b'\x00')
                        self.client.send(b'\x00')
                        self.last_activity = time.time()
                    continue

                for fd, flag in events:
                    sock = self.client if fd == self.client.fileno() else self.target
                    if flag & (select.POLLHUP | select.POLLERR):
                        error = True
                        self.server.printLog(self.log + ' - detected HUP/ERR, closing softly')
                        break
                    if flag & select.POLLIN:
                        data = sock.recv(BUFLEN)
                        if data:
                            if sock is self.target:
                                self.client.send(data)
                            else:
                                sent = 0
                                while sent < len(data):
                                    sent += self.target.send(data[sent:])
                            self.last_activity = time.time()  # Reset atividade
                        else:
                            error = True
                            break
            except Exception as e:
                self.server.printLog(self.log + ' - loop error: ' + str(e))
                error = True

class ProxyManager:
    def __init__(self):
        self.config_manager = ConfigManager()
       
    def install_proxy(self):
        """Instala o proxy como serviço do sistema"""
        try:
            # Cria o script do proxy
            print("\033[1;33mInstalando proxy...\033[0m")
           
            # Copia o script atual para /usr/local/bin
            current_script = os.path.abspath(__file__)
            os.system(f'sudo cp {current_script} {PROXY_SCRIPT}')
            os.system(f'sudo chmod +x {PROXY_SCRIPT}')
           
            # Cria arquivo de serviço systemd
            service_content = f"""[Unit]
Description=Proxy Multiflow Service
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/usr/local/bin
ExecStart=/usr/bin/python3 {PROXY_SCRIPT} --daemon
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
"""
           
            with open('/tmp/proxy-multiflow.service', 'w') as f:
                f.write(service_content)
           
            os.system('sudo mv /tmp/proxy-multiflow.service ' + SERVICE_FILE)
            os.system('sudo systemctl daemon-reload')
            os.system('sudo systemctl enable proxy-multiflow')
           
            self.config_manager.config['installed'] = True
            self.config_manager.save_config()
           
            print("\033[1;32mProxy instalado com sucesso!\033[0m")
            return True
           
        except Exception as e:
            print(f"\033[1;31mErro ao instalar: {e}\033[0m")
            return False
   
    def uninstall_proxy(self):
        """Remove o proxy do sistema"""
        try:
            print("\033[1;33mRemovendo proxy...\033[0m")
           
            # Para o serviço
            os.system('sudo systemctl stop proxy-multiflow 2>/dev/null')
            os.system('sudo systemctl disable proxy-multiflow 2>/dev/null')
           
            # Remove arquivos
            if os.path.exists(SERVICE_FILE):
                os.system(f'sudo rm {SERVICE_FILE}')
            if os.path.exists(PROXY_SCRIPT):
                os.system(f'sudo rm {PROXY_SCRIPT}')
           
            os.system('sudo systemctl daemon-reload')
           
            self.config_manager.config['installed'] = False
            self.config_manager.config['active'] = False
            self.config_manager.save_config()
           
            print("\033[1;32mProxy removido com sucesso!\033[0m")
            return True
           
        except Exception as e:
            print(f"\033[1;31mErro ao remover: {e}\033[0m")
            return False
   
    def start_proxy(self):
        """Inicia o serviço do proxy"""
        os.system('sudo systemctl start proxy-multiflow')
        time.sleep(2)
        return self.config_manager.is_active()
   
    def stop_proxy(self):
        """Para o serviço do proxy"""
        os.system('sudo systemctl stop proxy-multiflow')
        time.sleep(2)
        return not self.config_manager.is_active()
   
    def restart_proxy(self):
        """Reinicia o serviço do proxy"""
        os.system('sudo systemctl restart proxy-multiflow')
        time.sleep(2)
        return self.config_manager.is_active()
def show_menu():
    """Exibe o menu interativo"""
    manager = ProxyManager()
   
    while True:
        system("clear")
        print("\033[0;34m" + "="*50 + "\033[0m")
        print("\033[1;32m PROXY MULTIFLOW - MENU PRINCIPAL\033[0m")
        print("\033[0;34m" + "="*50 + "\033[0m")
       
        # Status
        is_installed = manager.config_manager.is_installed()
        is_active = manager.config_manager.is_active()
        ports = manager.config_manager.get_ports()
       
        status_color = "\033[1;32m" if is_active else "\033[1;31m"
        status_text = "ATIVO" if is_active else "INATIVO"
       
        print(f"\n\033[1;33mStatus:\033[0m {status_color}{status_text}\033[0m")
        print(f"\033[1;33mInstalado:\033[0m {'Sim' if is_installed else 'Não'}")
        print(f"\033[1;33mPortas:\033[0m {', '.join(map(str, ports))}")
       
        print("\n\033[0;34m" + "-"*50 + "\033[0m")
       
        if not is_installed:
            print("\033[1;36m1.\033[0m Instalar Proxy")
        else:
            print("\033[1;36m1.\033[0m \033[1;30mInstalar Proxy (já instalado)\033[0m")
           
        if is_installed:
            print("\033[1;36m2.\033[0m Remover Proxy")
            print("\033[1;36m3.\033[0m Adicionar Porta")
            print("\033[1;36m4.\033[0m Remover Porta")
           
            if is_active:
                print("\033[1;36m5.\033[0m Parar Proxy")
                print("\033[1;36m6.\033[0m Reiniciar Proxy")
            else:
                print("\033[1;36m5.\033[0m Iniciar Proxy")
        else:
            print("\033[1;36m2.\033[0m \033[1;30mRemover Proxy (não instalado)\033[0m")
            print("\033[1;36m3.\033[0m \033[1;30mAdicionar Porta (instale primeiro)\033[0m")
            print("\033[1;36m4.\033[0m \033[1;30mRemover Porta (instale primeiro)\033[0m")
       
        print("\033[1;36m0.\033[0m Sair")
        print("\033[0;34m" + "-"*50 + "\033[0m")
       
        try:
            choice = input("\n\033[1;33mEscolha uma opção: \033[0m")
           
            if choice == '0':
                print("\n\033[1;32mSaindo...\033[0m")
                break
               
            elif choice == '1' and not is_installed:
                manager.install_proxy()
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            elif choice == '2' and is_installed:
                confirm = input("\n\033[1;31mTem certeza que deseja remover o proxy? (s/n): \033[0m")
                if confirm.lower() == 's':
                    manager.uninstall_proxy()
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            elif choice == '3' and is_installed:
                try:
                    port = int(input("\n\033[1;33mDigite a porta a adicionar: \033[0m"))
                    if 1 <= port <= 65535:
                        if manager.config_manager.add_port(port):
                            print(f"\033[1;32mPorta {port} adicionada com sucesso!\033[0m")
                            if is_active:
                                print("\033[1;33mReiniciando proxy...\033[0m")
                                manager.restart_proxy()
                        else:
                            print(f"\033[1;31mPorta {port} já existe!\033[0m")
                    else:
                        print("\033[1;31mPorta inválida!\033[0m")
                except ValueError:
                    print("\033[1;31mPorta inválida!\033[0m")
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            elif choice == '4' and is_installed:
                if len(ports) > 1:
                    print(f"\n\033[1;33mPortas atuais: {', '.join(map(str, ports))}\033[0m")
                    try:
                        port = int(input("\033[1;33mDigite a porta a remover: \033[0m"))
                        if manager.config_manager.remove_port(port):
                            print(f"\033[1;32mPorta {port} removida com sucesso!\033[0m")
                            if is_active:
                                print("\033[1;33mReiniciando proxy...\033[0m")
                                manager.restart_proxy()
                        else:
                            print(f"\033[1;31mNão foi possível remover a porta {port}!\033[0m")
                    except ValueError:
                        print("\033[1;31mPorta inválida!\033[0m")
                else:
                    print("\033[1;31mDeve manter pelo menos uma porta!\033[0m")
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            elif choice == '5' and is_installed:
                if is_active:
                    print("\n\033[1;33mParando proxy...\033[0m")
                    if manager.stop_proxy():
                        print("\033[1;32mProxy parado com sucesso!\033[0m")
                    else:
                        print("\033[1;31mErro ao parar o proxy!\033[0m")
                else:
                    print("\n\033[1;33mIniciando proxy...\033[0m")
                    if manager.start_proxy():
                        print("\033[1;32mProxy iniciado com sucesso!\033[0m")
                    else:
                        print("\033[1;31mErro ao iniciar o proxy!\033[0m")
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            elif choice == '6' and is_installed and is_active:
                print("\n\033[1;33mReiniciando proxy...\033[0m")
                if manager.restart_proxy():
                    print("\033[1;32mProxy reiniciado com sucesso!\033[0m")
                else:
                    print("\033[1;31mErro ao reiniciar o proxy!\033[0m")
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
               
            else:
                print("\n\033[1;31mOpção inválida!\033[0m")
                time.sleep(1)
               
        except KeyboardInterrupt:
            print("\n\n\033[1;31mInterrompido pelo usuário!\033[0m")
            break
        except Exception as e:
            print(f"\n\033[1;31mErro: {e}\033[0m")
            input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
def run_daemon():
    """Executa o proxy em modo daemon"""
    config_manager = ConfigManager()
    servers = []
   
    for port in config_manager.get_ports():
        server = Server(IP, port)
        server.start()
        servers.append(server)
        print(f"Proxy iniciado na porta {port}")
   
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print('\nParando servidores...')
        for server in servers:
            server.close()
def main():
    """Função principal"""
    if '--daemon' in sys.argv:
        # Modo daemon (executado pelo systemd)
        run_daemon()
    elif len(sys.argv) > 1 and sys.argv[1].isdigit():
        # Modo standalone com porta específica
        print("\033[0;34m"*8 + "\033[1;32m PROXY SOCKS" + "\033[0;34m"*8 + "\n")
        print("\033[1;33mIP:\033[1;32m " + IP)
        print("\033[1;33mPORTA:\033[1;32m " + str(PORT) + "\n")
        print("\033[0;34m"*10 + "\033[1;32m Multiflow" + "\033[0;34m\033[1;37m"*11 + "\n")
       
        server = Server(IP, PORT)
        server.start()
       
        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            print('\nParando...')
            server.close()
    else:
        # Modo menu interativo
        show_menu()
if __name__ == '__main__':
    main()
