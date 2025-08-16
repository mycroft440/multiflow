#!/usr/bin/env python3
# encoding: utf-8
import socket
import threading
import select
import sys
import time
import os
import json
import subprocess
import signal
import errno
import hashlib
import random
from os import system
from concurrent.futures import ThreadPoolExecutor

# Arquivo de configuração
CONFIG_FILE = '/etc/proxy_config.json'
SERVICE_FILE = '/etc/systemd/system/proxy.service'
PROXY_SCRIPT = '/usr/local/bin/proxy.py'

# Configuração padrão
DEFAULT_CONFIG = {
    'installed': False,
    'active': False,
    'ports': [80],
    'ip': '0.0.0.0',
    'password': '',
    'default_host': '0.0.0.0:22',
    'obfuscation': {
        'enabled': False,
        'type': 'scramblesuit',
        'shared_secret': ''  # Chave compartilhada para ofuscação (deve ser a mesma no client)
    },
    'mimic_protocol': {
        'enabled': False,
        'type': 'dns'  # Pode ser 'dns' ou 'http2'; expanda para mais
    },
    'traffic_shaping': {
        'enabled': False,
        'max_padding': 32,  # Máximo de bytes randômicos para padding
        'max_delay': 0.001  # Máximo delay em segundos (ex.: 1ms)
    }
}

# Conexão
IP = '0.0.0.0'
try:
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80
except:
    PORT = 80
PASS = ''
BUFLEN = 8196 * 8
TIMEOUT = 60  # Mantido, mas não usado para fechamento forçado
DEFAULT_HOST = '0.0.0.0:22'
RESPONSE = "HTTP/1.1 200 Connection Established\r\nConnection: keep-alive\r\n\r\n"  # Adicionado keep-alive header

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
            result = subprocess.run(['systemctl', 'is-active', 'proxy'],
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

    def toggle_obfuscation(self):
        """Alterna a ativação da ofuscação"""
        self.config['obfuscation']['enabled'] = not self.config['obfuscation']['enabled']
        self.save_config()
        return self.config['obfuscation']['enabled']

    def toggle_mimic_protocol(self):
        """Alterna a ativação da imitação de protocolo"""
        self.config['mimic_protocol']['enabled'] = not self.config['mimic_protocol']['enabled']
        self.save_config()
        return self.config['mimic_protocol']['enabled']

    def toggle_traffic_shaping(self):
        """Alterna a ativação do traffic shaping"""
        self.config['traffic_shaping']['enabled'] = not self.config['traffic_shaping']['enabled']
        self.save_config()
        return self.config['traffic_shaping']['enabled']

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=200)  # Limite de threads para estabilidade

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
                    # Ativar TCP_NODELAY para reduzir latência
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    # Ativar TCP Keep-Alive com valores ajustados para bypassar timeouts de firewall (~30s)
                    c.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)  # Iniciar probes após 15s idle
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)  # Intervalo de 5s entre probes
                    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)    # 5 probes antes de fechar
                except socket.timeout:
                    continue
                
                conn = ConnectionHandler(c, self, addr)
                self.executor.submit(conn.run)  # Usar thread pool para limite de conexões
                self.addConn(conn)
        finally:
            self.running = False
            self.soc.close()
            self.executor.shutdown(wait=True)  # Shutdown gracioso do executor
            
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
        self.method = None  # Adicionado para compatibilidade
        self.obfuscation_enabled = ConfigManager().config.get('obfuscation', {}).get('enabled', False)
        self.shared_secret = ConfigManager().config.get('obfuscation', {}).get('shared_secret', '')
        self.send_count = 0  # Contador para chave rotativa
        self.recv_count = 0
        self.mimic_enabled = ConfigManager().config.get('mimic_protocol', {}).get('enabled', False)
        self.mimic_type = ConfigManager().config.get('mimic_protocol', {}).get('type', 'dns')
        self.mimic_sent = False  # Flag para enviar mimic prefix apenas uma vez
        self.shaping_enabled = ConfigManager().config.get('traffic_shaping', {}).get('enabled', False)
        self.max_padding = ConfigManager().config.get('traffic_shaping', {}).get('max_padding', 32)
        self.max_delay = ConfigManager().config.get('traffic_shaping', {}).get('max_delay', 0.001)
        self.handshake_done = False  # Flag para pular ofuscações durante handshake

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
            self.client_buffer = self.client.recv(BUFLEN).decode('utf-8')
            if not self.client_buffer:
                raise Exception("No buffer")

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
                elif hostPort.startswith(IP):
                    self.method_CONNECT(hostPort)
                else:
                    self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n'.encode('utf-8'))
            else:
                print('- No X-Real-Host!')
                self.client.send('HTTP/1.1 400 NoXRealHost!\r\n\r\n'.encode('utf-8'))
        except socket.error as e:
            if e.errno in [errno.ECONNRESET, errno.EPIPE]:
                self.log += f' - Connection reset: {e}'
            else:
                self.log += ' - error: ' + str(e)
                raise
            self.server.printLog(self.log)
        except Exception as e:
            self.log += ' - error: ' + str(e)
            self.server.printLog(self.log)
        finally:
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
            if self.method == 'CONNECT':
                port = 443
            else:
                port = 22
        (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]
        self.target = socket.socket(soc_family, soc_type, proto)
        self.target.settimeout(10)  # Timeout para connect
        # Ativar TCP_NODELAY para reduzir latência
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Ativar TCP Keep-Alive com valores ajustados para bypassar timeouts de firewall (~30s)
        self.target.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)  # Iniciar probes após 15s idle
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)   # Intervalo de 5s entre probes
        self.target.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)     # 5 probes antes de fechar
        try:
            self.target.connect(address)
        except socket.timeout:
            self.log += ' - Connect timeout'
            raise
        self.targetClosed = False

    def obfuscate_data(self, data, is_send=True):
        """Ofuscação inspirada em ScrambleSuit: XOR com chave rotativa baseada no shared_secret"""
        if not self.obfuscation_enabled or not self.shared_secret:
            return data
        count = self.send_count if is_send else self.recv_count
        key = hashlib.sha256(self.shared_secret.encode() + str(count).encode()).digest()
        obfuscated = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        if is_send:
            self.send_count += 1
        else:
            self.recv_count += 1
        return obfuscated

    def mimic_prefix(self):
        """Gera prefixo para imitação de protocolo"""
        if self.mimic_type == 'dns':
            # Simples DNS query header para google.com A record
            return b'\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01'
        elif self.mimic_type == 'http2':
            # HTTP/2 magic prefix
            return b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
        return b''

    def apply_shaping(self, data):
        """Aplica traffic shaping: padding randômico e delay mínimo"""
        if self.shaping_enabled:
            # Adicionar padding randômico (0 a max_padding bytes)
            padding_size = random.randint(0, self.max_padding)
            data += os.urandom(padding_size)
            # Adicionar delay randômico (0 a max_delay segundos)
            delay = random.uniform(0, self.max_delay)
            time.sleep(delay)
        return data

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
        count = 0
        error = False
        while True:
            count += 1
            (recv, _, err) = select.select(socs, [], socs, 1)  # Reduzido para 1s para menor latência
            if err:
                error = True
            if recv:
                for in_ in recv:
                    try:
                        data = in_.recv(BUFLEN)
                        if data:
                            # Desofuscar dados recebidos
                            data = self.obfuscate_data(data, is_send=False)
                            if in_ is self.target:
                                obfuscated_data = self.obfuscate_data(data, is_send=True)
                                # Adicionar mimic prefix se ativado e não enviado ainda e handshake done
                                if self.mimic_enabled and not self.mimic_sent and self.handshake_done:
                                    obfuscated_data = self.mimic_prefix() + obfuscated_data
                                    self.mimic_sent = True
                                # Aplicar traffic shaping se handshake done
                                if self.handshake_done:
                                    obfuscated_data = self.apply_shaping(obfuscated_data)
                                self.client.sendall(obfuscated_data)
                            else:
                                obfuscated_data = self.obfuscate_data(data, is_send=True)
                                # Adicionar mimic prefix se ativado e não enviado ainda e handshake done
                                if self.mimic_enabled and not self.mimic_sent and self.handshake_done:
                                    obfuscated_data = self.mimic_prefix() + obfuscated_data
                                    self.mimic_sent = True
                                # Aplicar traffic shaping se handshake done
                                if self.handshake_done:
                                    obfuscated_data = self.apply_shaping(obfuscated_data)
                                self.target.sendall(obfuscated_data)
                            count = 0
                            self.handshake_done = True  # Setar após primeiro recv/send
                        else:
                            error = True
                            break
                    except socket.error as e:
                        if e.errno in [errno.ECONNRESET, errno.EPIPE]:
                            self.log += f' - Connection reset in doCONNECT: {e}'
                            error = True
                        else:
                            raise
                    except Exception as e:
                        self.log += ' - error in doCONNECT: ' + str(e)
                        error = True
                        break
            # Removido: if count == TIMEOUT: error = True  # Não fechar conexões idle, depender de keep-alive
            if error:
                break

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
            service_content = f'''[Unit]
Description=Proxy Service
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
'''
            
            with open('/tmp/proxy.service', 'w') as f:
                f.write(service_content)
            
            os.system('sudo mv /tmp/proxy.service ' + SERVICE_FILE)
            os.system('sudo systemctl daemon-reload')
            os.system('sudo systemctl enable proxy')
            
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
            os.system('sudo systemctl stop proxy 2>/dev/null')
            os.system('sudo systemctl disable proxy 2>/dev/null')
            
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
        os.system('sudo systemctl start proxy')
        time.sleep(2)
        return self.config_manager.is_active()
    
    def stop_proxy(self):
        """Para o serviço do proxy"""
        os.system('sudo systemctl stop proxy')
        time.sleep(2)
        return not self.config_manager.is_active()
    
    def restart_proxy(self):
        """Reinicia o serviço do proxy"""
        os.system('sudo systemctl restart proxy')
        time.sleep(2)
        return self.config_manager.is_active()

def show_menu():
    """Exibe o menu interativo"""
    manager = ProxyManager()
    config = manager.config_manager.config
    
    while True:
        system("clear")
        print("\033[0;34m" + "="*50 + "\033[0m")
        print("\033[1;32m PROXY SOCKS - MENU PRINCIPAL\033[0m")
        print("\033[0;34m" + "="*50 + "\033[0m")
        
        # Status
        is_installed = manager.config_manager.is_installed()
        is_active = manager.config_manager.is_active()
        ports = manager.config_manager.get_ports()
        
        status_color = "\033[1;32m" if is_active else "\033[1;31m"
        status_text = "ATIVO" if is_active else "INATIVO"
        
        obfuscation_status = "\033[1;32mAtivado\033[0m" if config['obfuscation']['enabled'] else "\033[1;31mDesativado\033[0m"
        mimic_status = "\033[1;32mAtivado\033[0m" if config['mimic_protocol']['enabled'] else "\033[1;31mDesativado\033[0m"
        shaping_status = "\033[1;32mAtivado\033[0m" if config['traffic_shaping']['enabled'] else "\033[1;31mDesativado\033[0m"
        
        print(f"\n\033[1;33mStatus:\033[0m {status_color}{status_text}\033[0m")
        print(f"\033[1;33mInstalado:\033[0m {'Sim' if is_installed else 'Não'}")
        print(f"\033[1;33mPortas:\033[0m {', '.join(map(str, ports))}")
        print(f"\033[1;33mOfuscação:\033[0m {obfuscation_status}")
        print(f"\033[1;33mImitação de Protocolo:\033[0m {mimic_status}")
        print(f"\033[1;33mTraffic Shaping:\033[0m {shaping_status}")
        
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
            print("\033[1;36m7.\033[0m Alternar Ofuscação")
            print("\033[1;36m8.\033[0m Alternar Imitação de Protocolo")
            print("\033[1;36m9.\033[0m Alternar Traffic Shaping")
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
                
            elif choice == '7' and is_installed:
                enabled = manager.config_manager.toggle_obfuscation()
                status = "ativada" if enabled else "desativada"
                print(f"\n\033[1;32mOfuscação {status} com sucesso!\033[0m")
                if is_active:
                    print("\033[1;33mReiniciando proxy...\033[0m")
                    manager.restart_proxy()
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
                
            elif choice == '8' and is_installed:
                enabled = manager.config_manager.toggle_mimic_protocol()
                status = "ativada" if enabled else "desativada"
                print(f"\n\033[1;32mImitação de Protocolo {status} com sucesso!\033[0m")
                if is_active:
                    print("\033[1;33mReiniciando proxy...\033[0m")
                    manager.restart_proxy()
                input("\n\033[1;33mPressione ENTER para continuar...\033[0m")
                
            elif choice == '9' and is_installed:
                enabled = manager.config_manager.toggle_traffic_shaping()
                status = "ativada" if enabled else "desativada"
                print(f"\n\033[1;32mTraffic Shaping {status} com sucesso!\033[0m")
                if is_active:
                    print("\033[1;33mReiniciando proxy...\033[0m")
                    manager.restart_proxy()
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
    
    def shutdown_handler(signum, frame):
        print('Shutdown signal received')
        for server in servers:
            server.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
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
    system("clear")
    if '--daemon' in sys.argv:
        # Modo daemon (executado pelo systemd)
        run_daemon()
    elif len(sys.argv) > 1 and sys.argv[1].isdigit():
        # Modo standalone com porta específica
        print("\033[0;34m━"*8,"\033[1;32m PROXY SOCKS","\033[0;34m━"*8,"\n")
        print("\033[1;33mIP:\033[1;32m " + IP)
        print("\033[1;33mPORTA:\033[1;32m " + str(PORT) + "\n")
        print("\033[0;34m━"*10,"\033[1;32m SCOTTSSH","\033[0;34m━\033[1;37m"*11,"\n")
        
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
