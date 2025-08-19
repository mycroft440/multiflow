#!/usr/bin/env python3
import asyncio
import sys
import socket
import os
import subprocess
import shutil
import json
import time
import random

PORTS_FILE = "/opt/multiflowproxy/ports"
PROXY_DIR = "/opt/multiflowproxy"
CONFIG_FILE = '/etc/proxy_config.json'

DEFAULT_CONFIG = {
    'installed': True,
    'active': False,
    'ports': [80],
    'ip': '0.0.0.0',
    'password': '',
    'default_host': '0.0.0.0:22',
    'traffic_shaping': {
        'enabled': False,
        'max_padding': 32,
        'max_delay': 0.001
    }
}

class ConfigManager:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.load_config()
    
    def load_config(self):
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
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"\033[1;31mErro ao salvar configuração: {e}\033[0m")
            return False
    
    def toggle_traffic_shaping(self):
        self.config['traffic_shaping']['enabled'] = not self.config['traffic_shaping']['enabled']
        self.save_config()
        return self.config['traffic_shaping']['enabled']

def is_root():
    return os.geteuid() == 0

def show_progress(message):
    print(f"Progresso: - {message}")

def error_exit(message):
    print(f"\nErro: {message}")
    sys.exit(1)

def get_port_from_args():
    args = sys.argv[1:]
    port = 80
    i = 0
    while i < len(args):
        if args[i] == "--port":
            if i + 1 < len(args):
                try:
                    port = int(args[i + 1])
                except ValueError:
                    port = 80
            i += 2
        else:
            i += 1
    return port

def get_proxy_status():
    if not os.path.exists(PORTS_FILE):
        return "INATIVO"
   
    with open(PORTS_FILE, 'r') as f:
        ports = f.read().splitlines()
   
    if not ports:
        return "INATIVO"
   
    active_count = 0
    for port in ports:
        try:
            result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                                  capture_output=True, text=True)
            if result.stdout.strip() == 'active':
                active_count += 1
        except:
            pass
   
    if active_count > 0:
        return f"ATIVO ({active_count} porta{'s' if active_count > 1 else ''})"
    else:
        return "INATIVO"

def get_port_status(port):
    try:
        result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                              capture_output=True, text=True)
        if result.stdout.strip() == 'active':
            return "Ativo"
        else:
            return "Inativo"
    except:
        return "Erro"

async def peek_stream(transport):
    sock = transport.get_extra_info('socket')
    if sock is None:
        return ""
    loop = asyncio.get_running_loop()
    try:
        await loop.sock_recv(sock, 0)
        peek_buffer = sock.recv(8192, socket.MSG_PEEK)
        data_str = peek_buffer.decode('utf-8', errors='replace')
        return data_str
    except Exception:
        return ""

async def transfer_data(source_reader, dest_writer):
    config_manager = ConfigManager()
    while True:
        data = await source_reader.read(8192)
        if len(data) == 0:
            break
        if config_manager.config['traffic_shaping']['enabled']:
            padding_size = random.randint(0, config_manager.config['traffic_shaping']['max_padding'])
            delay = random.uniform(0, config_manager.config['traffic_shaping']['max_delay'])
            data += bytes([0] * padding_size)
            await asyncio.sleep(delay)
        dest_writer.write(data)
        await dest_writer.drain()
    dest_writer.close()

async def handle_client(reader, writer):
    status = "Switching Protocols"
    writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
    await writer.drain()
    buffer = await reader.read(1024)
    writer.write(f"HTTP/1.1 200 OK\r\n\r\n".encode())
    await writer.drain()
    try:
        data = await asyncio.wait_for(peek_stream(writer.transport), timeout=1.0)
    except (asyncio.TimeoutError, Exception):
        data = ""
    addr_proxy = "0.0.0.0:22"
    if "SSH" in data or data == "":
        addr_proxy = "0.0.0.0:22"
    else:
        addr_proxy = "0.0.0.0:1194"
    try:
        server_reader, server_writer = await asyncio.open_connection(
            addr_proxy.split(':')[0], int(addr_proxy.split(':')[1])
        )
    except Exception:
        print("erro ao iniciar conexão para o proxy")
        writer.close()
        await writer.wait_closed()
        return
    client_to_server = asyncio.create_task(transfer_data(reader, server_writer))
    server_to_client = asyncio.create_task(transfer_data(server_reader, writer))
    await asyncio.gather(client_to_server, server_to_client)

async def start_http(server):
    async with server:
        await server.serve_forever()

async def run_proxy():
    port = get_port_from_args()
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(('::', port))
        sock.listen(100)
        server = await asyncio.start_server(handle_client, sock=sock)
        print(f"Iniciando serviço na porta: {port}")
        await start_http(server)
    except Exception as e:
        print(f"Erro ao iniciar o proxy: {str(e)}")
        sys.exit(1)

def is_port_in_use(port):
    try:
        result = subprocess.run(['netstat', '-tuln'], capture_output=True, text=True)
        if f":{port}" in result.stdout:
            return True
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True)
        if f":{port}" in result.stdout:
            return True
        return False
    except:
        return False

def add_proxy_port(port):
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    
    # Criar diretório se não existir
    os.makedirs(PROXY_DIR, exist_ok=True)
    
    # Copiar script atual para o diretório
    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/multiflowproxy/multiflowproxy.py')
    os.chmod('/opt/multiflowproxy/multiflowproxy.py', 0o755)
    
    command = f"/usr/bin/python3 {PROXY_DIR}/multiflowproxy.py --port {port}"
    service_name = f"proxy{port}.service"
    service_file = f"/etc/systemd/system/{service_name}"
    service_content = f"""[Unit]
Description=MultiFlowProxy on port {port}
After=network.target

[Service]
LimitNOFILE=infinity
LimitNPROC=infinity
LimitMEMLOCK=infinity
LimitSTACK=infinity
LimitCORE=0
LimitAS=infinity
LimitRSS=infinity
LimitCPU=infinity
LimitFSIZE=infinity
Type=simple
ExecStart={command}
Restart=always

[Install]
WantedBy=multi-user.target
"""
    with open(service_file, 'w') as f:
        f.write(service_content)
    subprocess.run(['systemctl', 'daemon-reload'])
    subprocess.run(['systemctl', 'enable', service_name])
    subprocess.run(['systemctl', 'start', service_name])
    with open(PORTS_FILE, 'a') as f:
        f.write(f"{port}\n")
    print(f"Porta {port} adicionada com sucesso.")

def del_proxy_port(port):
    service_name = f"proxy{port}.service"
    subprocess.run(['systemctl', 'disable', service_name])
    subprocess.run(['systemctl', 'stop', service_name])
    if os.path.exists(f"/etc/systemd/system/{service_name}"):
        os.remove(f"/etc/systemd/system/{service_name}")
    subprocess.run(['systemctl', 'daemon-reload'])
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            lines = f.readlines()
        with open(PORTS_FILE, 'w') as f:
            for line in lines:
                if line.strip() != str(port):
                    f.write(line)
    print(f"Porta {port} removida com sucesso.")

def restart_proxy_port(port):
    service_name = f"proxy{port}.service"
    subprocess.run(['systemctl', 'restart', service_name])
    print(f"Porta {port} reiniciada com sucesso.")

def list_active_ports():
    if not os.path.exists(PORTS_FILE):
        return []
    with open(PORTS_FILE, 'r') as f:
        ports = [p.strip() for p in f.readlines() if p.strip()]
    return [(p, get_port_status(int(p))) for p in ports]

def show_menu():
    config_manager = ConfigManager()
    while True:
        os.system('clear')
        print("="*50)
        print("           MULTIFLOW PROXY")
        print("="*50)
        
        proxy_status = get_proxy_status()
        if "ATIVO" in proxy_status:
            status_color = "\033[1;32m"
        else:
            status_color = "\033[1;33m"
        print(f"Status: {status_color}{proxy_status}\033[0m")
        
        active_ports = "Nenhuma porta configurada"
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, 'r') as f:
                ports = f.read().splitlines()
                if ports:
                    active_ports = ", ".join(ports)
        print(f"Portas: \033[1;32m{active_ports}\033[0m")
        
        # Status do Traffic Shaping
        ts_status = "Ativado" if config_manager.config['traffic_shaping']['enabled'] else "Desativado"
        ts_color = "\033[1;32m" if config_manager.config['traffic_shaping']['enabled'] else "\033[1;31m"
        print(f"Traffic Shaping: {ts_color}{ts_status}\033[0m")
        
        print("\n" + "="*50)
        print("               MENU")
        print("="*50)
        
        print("\033[1;33m[1]\033[0m Adicionar Porta")
        print("\033[1;33m[2]\033[0m Remover Porta")
        print("\033[1;33m[3]\033[0m Reiniciar Porta")
        print("\033[1;33m[4]\033[0m Alternar Traffic Shaping")
        print("\033[1;33m[0]\033[0m Sair")
        
        print("\n" + "="*50)
        option = input("\033[1;33mEscolha uma opcao: \033[0m")
        
        if option == '1':
            port = input("\n\033[1;33mDigite a porta para adicionar: \033[0m")
            while not port.isdigit() or int(port) < 1 or int(port) > 65535:
                print("\033[1;31mDigite uma porta valida (1-65535).\033[0m")
                port = input("\033[1;33mDigite a porta: \033[0m")
            add_proxy_port(int(port))
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '2':
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;33mPortas ativas:\033[0m")
                for port, status in port_info:
                    print(f" \033[1;32m{port}\033[0m - {status}")
                port = input("\n\033[1;33mDigite a porta para remover: \033[0m")
                while not port.isdigit():
                    print("\033[1;31mDigite uma porta valida.\033[0m")
                    port = input("\033[1;33mDigite a porta: \033[0m")
                del_proxy_port(int(port))
            else:
                print("\033[1;31mNenhuma porta ativa para remover.\033[0m")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '3':
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;33mPortas disponiveis para reiniciar:\033[0m")
                for port, status in port_info:
                    print(f" \033[1;32m{port}\033[0m - {status}")
                port = input("\n\033[1;33mDigite a porta para reiniciar (ou 'all' para todas): \033[0m")
               
                if port.lower() == 'all':
                    for p, _ in port_info:
                        restart_proxy_port(int(p))
                elif port.isdigit():
                    restart_proxy_port(int(port))
                else:
                    print("\033[1;31mOpcao invalida.\033[0m")
            else:
                print("\033[1;31mNenhuma porta ativa para reiniciar.\033[0m")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '4':
            enabled = config_manager.toggle_traffic_shaping()
            status = "\033[1;32mativado\033[0m" if enabled else "\033[1;31mdesativado\033[0m"
            print(f"\nTraffic Shaping {status} com sucesso!")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '0':
            print("\nSaindo...")
            sys.exit(0)
           
        else:
            print("\n\033[1;31mOpcao invalida.\033[0m")
            input("\033[1;33mPressione Enter para continuar...\033[0m")

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
