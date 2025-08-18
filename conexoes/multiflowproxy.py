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
    'installed': False,
    'active': False,
    'ports': [80],
    'ip': '0.0.0.0',
    'password': '',
    'default_host': '0.0.0.0:22',
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
            print("Erro ao salvar configuracao: " + str(e))
            return False

def is_root():
    return os.geteuid() == 0

def error_exit(message):
    print("\nErro: " + message)
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

def is_proxy_installed():
    return os.path.exists(PROXY_DIR) and os.path.exists('/usr/local/bin/multiflowproxy')

def get_proxy_status():
    if not is_proxy_installed():
        return "NAO INSTALADO"
   
    if not os.path.exists(PORTS_FILE):
        return "INSTALADO - INATIVO"
   
    with open(PORTS_FILE, 'r') as f:
        ports = f.read().splitlines()
   
    if not ports:
        return "INSTALADO - INATIVO"
   
    active_count = 0
    for port in ports:
        try:
            result = subprocess.run(['systemctl', 'is-active', "proxy" + port + ".service"],
                                  capture_output=True, text=True)
            if result.stdout.strip() == 'active':
                active_count += 1
        except:
            pass
   
    if active_count > 0:
        return "ATIVO (" + str(active_count) + " porta" + ('s' if active_count > 1 else '') + ")"
    else:
        return "INSTALADO - INATIVO"

def get_port_status(port):
    try:
        result = subprocess.run(['systemctl', 'is-active', "proxy" + str(port) + ".service"],
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
    while True:
        data = await source_reader.read(8192)
        if len(data) == 0:
            break
        dest_writer.write(data)
        await dest_writer.drain()
    dest_writer.close()

async def handle_client(reader, writer):
    status = "Switching Protocols"
    writer.write(("HTTP/1.1 101 " + status + "\r\n\r\n").encode())
    await writer.drain()
    buffer = await reader.read(1024)
    writer.write(("HTTP/1.1 200 OK\r\n\r\n").encode())
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
        print("erro ao iniciar conexao para o proxy")
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
        print("Iniciando servico na porta: " + str(port))
        await start_http(server)
    except Exception as e:
        print("Erro ao iniciar o proxy: " + str(e))
        sys.exit(1)

def is_port_in_use(port):
    try:
        result = subprocess.run(['netstat', '-tuln'], capture_output=True, text=True)
        if ":" + str(port) in result.stdout:
            return True
        result = subprocess.run(['ss', '-tuln'], capture_output=True, text=True)
        if ":" + str(port) in result.stdout:
            return True
        return False
    except:
        return False

def add_proxy_port(port):
    if is_port_in_use(port):
        print("A porta " + str(port) + " ja esta em uso.")
        return
    command = "/usr/bin/python3 " + PROXY_DIR + "/multiflowproxy.py --port " + str(port)
    service_name = "proxy" + str(port) + ".service"
    service_file = "/etc/systemd/system/" + service_name
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
        f.write(str(port) + "\n")
    print("Porta " + str(port) + " adicionada com sucesso.")

def del_proxy_port(port):
    service_name = "proxy" + str(port) + ".service"
    subprocess.run(['systemctl', 'disable', service_name])
    subprocess.run(['systemctl', 'stop', service_name])
    os.remove("/etc/systemd/system/" + service_name)
    subprocess.run(['systemctl', 'daemon-reload'])
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            lines = f.readlines()
        with open(PORTS_FILE, 'w') as f:
            for line in lines:
                if line.strip() != str(port):
                    f.write(line)
    print("Porta " + str(port) + " removida com sucesso.")

def restart_proxy_port(port):
    service_name = "proxy" + str(port) + ".service"
    subprocess.run(['systemctl', 'restart', service_name])
    print("Porta " + str(port) + " reiniciada com sucesso.")

def list_active_ports():
    if not os.path.exists(PORTS_FILE):
        return []
    with open(PORTS_FILE, 'r') as f:
        ports = [p.strip() for p in f.readlines() if p.strip()]
    return [(p, get_port_status(int(p))) for p in ports]

def install_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")
    
    os.system('clear')
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    try:
        subprocess.run(['apt', 'update', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao atualizar os repositorios")
    
    try:
        subprocess.run(['apt', 'install', 'lsb-release', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao instalar lsb-release")

    os_name = subprocess.run(['lsb_release', '-is'], capture_output=True, text=True).stdout.strip()
    version = subprocess.run(['lsb_release', '-rs'], capture_output=True, text=True).stdout.strip()

    if os_name == 'Ubuntu':
        if not version.startswith(('24.', '22.', '20.', '18.')):
            error_exit("Versao do Ubuntu nao suportada. Use 18, 20, 22 ou 24.")
    elif os_name == 'Debian':
        if not version.startswith(('12', '11', '10', '9')):
            error_exit("Versao do Debian nao suportada. Use 9, 10, 11 ou 12.")
    else:
        error_exit("Sistema nao suportado. Use Ubuntu ou Debian.")
    
    try:
        subprocess.run(['apt', 'upgrade', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao atualizar o sistema")

    try:
        subprocess.run(['apt', 'install', 'curl', 'build-essential', 'git', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao instalar pacotes adicionais")
    
    os.makedirs('/opt/multiflowproxy', exist_ok=True)

    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/multiflowproxy/multiflowproxy.py')
    
    os.chmod('/opt/multiflowproxy/multiflowproxy.py', 0o755)
    os.symlink('/opt/multiflowproxy/multiflowproxy.py', '/usr/local/bin/multiflowproxy')

    print("Instalacao concluida com sucesso. Digite 'multiflowproxy' para acessar o menu.")

def uninstall_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            ports = f.read().splitlines()
        for port in ports:
            del_proxy_port(int(port))
    if os.path.exists(PROXY_DIR):
        shutil.rmtree(PROXY_DIR)
    os.remove('/usr/local/bin/multiflowproxy')
    print("\nDesinstalacao concluida com sucesso.")

def show_menu():
    config_manager = ConfigManager()
    while True:
        proxy_status = get_proxy_status()
        active_ports = "Nenhuma porta configurada"
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, 'r') as f:
                ports = f.read().splitlines()
                if ports:
                    active_ports = ", ".join(ports)
        print("Status: " + proxy_status)
        print("Portas: " + active_ports + "\n")
        
        print("1. Abrir porta")
        print("2. Remover Porta")
        print("0. Voltar")
        
        option = input(" ➜ ")
        
        if option == '1':
            if not is_proxy_installed():
                install_proxy()
                port_input = input("Deseja iniciar proxy em qual porta? ")
                while not port_input.isdigit() or int(port_input) < 1 or int(port_input) > 65535:
                    print("Digite uma porta valida (1-65535).")
                    port_input = input("Deseja iniciar proxy em qual porta? ")
                add_proxy_port(int(port_input))
            else:
                port = input("Digite a porta para adicionar: ")
                while not port.isdigit() or int(port) < 1 or int(port) > 65535:
                    print("Digite uma porta valida (1-65535).")
                    port = input("Digite a porta: ")
                add_proxy_port(int(port))
            input("Pressione Enter para continuar...")
           
        elif option == '2':
            if is_proxy_installed():
                port_info = list_active_ports()
                if port_info:
                    print("Portas ativas:")
                    for port, status in port_info:
                        print(" " + str(port) + " - " + status)
                    port = input("Digite a porta para remover: ")
                    while not port.isdigit():
                        print("Digite uma porta valida.")
                        port = input("Digite a porta: ")
                    del_proxy_port(int(port))
                else:
                    print("Nenhuma porta ativa para remover.")
                input("Pressione Enter para continuar...")
            else:
                print("Proxy nao instalado.")
                input("Pressione Enter para continuar...")
           
        elif option == '0':
            print("Saindo...")
            sys.exit(0)
           
        else:
            print("Opcao invalida.")
            input("Pressione Enter para continuar...")

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
