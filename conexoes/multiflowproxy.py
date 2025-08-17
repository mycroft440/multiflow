import asyncio
import sys
import socket
import os
import subprocess
import shutil
import json
import time
import random
import ssl  # Added for SSL support

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
    'traffic_shaping': {
        'enabled': False,
        'max_padding': 32,
        'max_delay': 0.001
    },
    'ssl': {
        'enabled': False,
        'domain': '',
        'email': '',
        'cert_path': '',
        'key_path': ''
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

def is_proxy_installed():
    return os.path.exists(PROXY_DIR) and os.path.exists('/usr/local/bin/multiflowproxy')

def get_proxy_status():
    if not is_proxy_installed():
        return "NÃO INSTALADO"
   
    if not os.path.exists(PORTS_FILE):
        return "INSTALADO - INATIVO"
   
    with open(PORTS_FILE, 'r') as f:
        ports = f.read().splitlines()
   
    if not ports:
        return "INSTALADO - INATIVO"
   
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
        return "INSTALADO - INATIVO"

def get_port_status(port):
    try:
        result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                              capture_output=True, text=True)
        if result.stdout.strip() == 'active':
            return "✓ Ativo"
        else:
            return "✗ Inativo"
    except:
        return "✗ Erro"

def is_port_active(port):
    try:
        result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                                capture_output=True, text=True)
        return result.stdout.strip() == 'active'
    except:
        return False

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

async def transfer_data(source_reader, dest_writer, traffic_shaping):
    while True:
        data = await source_reader.read(8192)
        if len(data) == 0:
            break
        if traffic_shaping['enabled']:
            padding_size = random.randint(0, traffic_shaping['max_padding'])
            delay = random.uniform(0, traffic_shaping['max_delay'])
            data += bytes([0] * padding_size)
            await asyncio.sleep(delay)
        dest_writer.write(data)
        await dest_writer.drain()
    dest_writer.close()

async def handle_client(reader, writer):
    config_manager = ConfigManager()
    traffic_shaping = config_manager.config['traffic_shaping'].copy()  # Copy to avoid mutable issues
    
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
    client_to_server = asyncio.create_task(transfer_data(reader, server_writer, traffic_shaping))
    server_to_client = asyncio.create_task(transfer_data(server_reader, writer, traffic_shaping))
    await asyncio.gather(client_to_server, server_to_client)

async def start_http(server):
    async with server:
        await server.serve_forever()

async def run_proxy():
    port = get_port_from_args()
    config_manager = ConfigManager()
    ssl_context = None
    if config_manager.config['ssl']['enabled']:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_context.load_cert_chain(
                config_manager.config['ssl']['cert_path'],
                config_manager.config['ssl']['key_path']
            )
        except Exception as e:
            print(f"Erro ao carregar certificado SSL: {e}")
            sys.exit(1)
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(('::', port))
        sock.listen(100)
        server = await asyncio.start_server(handle_client, sock=sock, ssl=ssl_context)
        print(f"Iniciando serviço na porta: {port}{' com SSL' if ssl_context else ''}")
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

def install_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")
    
    TOTAL_STEPS = 9
    CURRENT_STEP = 0
    
    def increment_step():
        nonlocal CURRENT_STEP
        CURRENT_STEP += 1
        show_progress(f"[{CURRENT_STEP}/{TOTAL_STEPS}]")

    os.system('clear')
    show_progress("Atualizando repositórios...")
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    try:
        subprocess.run(['apt', 'update', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao atualizar os repositórios")
    increment_step()

    show_progress("Verificando o sistema...")
    try:
        subprocess.run(['apt', 'install', 'lsb-release', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao instalar lsb-release")
    increment_step()

    os_name = subprocess.run(['lsb_release', '-is'], capture_output=True, text=True).stdout.strip()
    version = subprocess.run(['lsb_release', '-rs'], capture_output=True, text=True).stdout.strip()

    if os_name == 'Ubuntu':
        if not version.startswith(('24.', '22.', '20.', '18.')):
            error_exit("Versão do Ubuntu não suportada. Use 18, 20, 22 ou 24.")
    elif os_name == 'Debian':
        if not version.startswith(('12', '11', '10', '9')):
            error_exit("Versão do Debian não suportada. Use 9, 10, 11 ou 12.")
    else:
        error_exit("Sistema não suportado. Use Ubuntu ou Debian.")
    show_progress("Sistema suportado, continuando...")
    increment_step()

    show_progress("Atualizando o sistema e instalando pacotes...")
    try:
        subprocess.run(['apt', 'upgrade', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['apt-get', 'install', 'curl', 'build-essential', 'git', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao atualizar o sistema ou instalar pacotes")
    increment_step()

    show_progress("Criando diretório /opt/multiflowproxy...")
    os.makedirs('/opt/multiflowproxy', exist_ok=True)
    increment_step()

    show_progress("Copiando script...")
    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/multiflowproxy/multiflowproxy.py')
    increment_step()

    show_progress("Configurando permissões...")
    os.chmod('/opt/multiflowproxy/multiflowproxy.py', 0o755)
    os.symlink('/opt/multiflowproxy/multiflowproxy.py', '/usr/local/bin/multiflowproxy')
    increment_step()

    show_progress("Limpando temporários...")
    increment_step()

    print("Instalação concluída com sucesso. Digite 'multiflowproxy' para acessar o menu.")

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
    print("\n✓ Desinstalação concluída com sucesso.")

def generate_ssl_cert(domain, email):
    try:
        # Instalar Certbot se não estiver instalado
        if not shutil.which('certbot'):
            subprocess.run(['apt', 'install', 'snapd', '-y'], check=True)
            subprocess.run(['snap', 'install', 'core'], check=True)
            subprocess.run(['snap', 'refresh', 'core'], check=True)
            subprocess.run(['snap', 'install', '--classic', 'certbot'], check=True)
            subprocess.run(['ln', '-s', '/snap/bin/certbot', '/usr/bin/certbot'], check=True)
        
        # Parar porta 80 temporariamente se ativa
        was_running = False
        if is_port_active(80):
            subprocess.run(['systemctl', 'stop', 'proxy80.service'], check=True)
            was_running = True
        
        # Preparar comando base
        cmd = [
            'certbot', 'certonly', '--standalone', '-d', domain,
            '--agree-tos', '--non-interactive'
        ]
        
        if email:
            cmd += ['--email', email]
        else:
            cmd += ['--register-unsafely-without-email']
        
        # Gerar certificado
        subprocess.run(cmd, check=True)
        
        # Reiniciar porta 80 se estava rodando
        if was_running:
            subprocess.run(['systemctl', 'start', 'proxy80.service'], check=True)
        
        print("\nCertificado SSL gerado com sucesso!")
        return True
    except Exception as e:
        print(f"\n\033[1;31mErro ao gerar certificado SSL: {e}\033[0m")
        return False

def configure_ssl(config_manager):
    print("\nDeseja rodar SSL em qual porta?")
    print("1. 80 e 443")
    print("2. Somente 443")
    option = input("\033[1;33m ➜ \033[0m")
    while option not in ['1', '2']:
        print("\033[1;31m✗ Opção inválida. Escolha 1 ou 2.\033[0m")
        option = input("\033[1;33m ➜ \033[0m")
    
    domain = input("\nAgora É MUITO IMPORTANTE digite o seu dominio que está apontado para seu IP para o SSL funcionar?\nDigite: ")
    while not domain:
        print("\033[1;31m✗ Domínio obrigatório.\033[0m")
        domain = input("Digite o domínio: ")
    
    email = input("\nDigite seu email para notificações do Let's Encrypt (opcional, pressione Enter para pular): ").strip()
    
    if generate_ssl_cert(domain, email):
        config_manager.config['ssl']['enabled'] = True
        config_manager.config['ssl']['domain'] = domain
        config_manager.config['ssl']['email'] = email
        config_manager.config['ssl']['cert_path'] = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        config_manager.config['ssl']['key_path'] = f"/etc/letsencrypt/live/{domain}/privkey.pem"
        config_manager.save_config()
        
        # Adicionar portas conforme opção
        if option == '1':
            if not os.path.exists(PORTS_FILE) or '80' not in open(PORTS_FILE).read():
                add_proxy_port(80)
            add_proxy_port(443)
        elif option == '2':
            add_proxy_port(443)
    else:
        print("\033[1;31m✗ Falha ao configurar SSL.\033[0m")

def show_menu():
    config_manager = ConfigManager()
    while True:
        os.system('clear')
        print("\033[0;34m━"*8, "\033[1;32m MULTIFLOW PROXY \033[0m", "\033[0;34m━"*8, "\n")
        
        proxy_status = get_proxy_status()
        if "ATIVO" in proxy_status:
            status_color = "\033[1;32m"
        elif "INATIVO" in proxy_status:
            status_color = "\033[1;33m"
        else:
            status_color = "\033[1;31m"
        print(f"\033[1;33mStatus:\033[0m {status_color}{proxy_status}\033[0m")
        
        active_ports = "Nenhuma porta configurada"
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, 'r') as f:
                ports = f.read().splitlines()
                if ports:
                    active_ports = ", ".join(ports)
        print(f"\033[1;33mPortas:\033[0m \033[1;32m{active_ports}\033[0m\n")
        
        ssl_status = "\033[1;32mAtivado\033[0m" if config_manager.config['ssl']['enabled'] else "\033[1;31mDesativado\033[0m"
        print(f"\033[1;33mSSL:\033[0m {ssl_status}\n")
        
        print("\033[0;34m━"*10, "\033[1;32m MENU \033[0m", "\033[0;34m━\033[1;37m"*11, "\n")
        
        if not is_proxy_installed():
            print("\033[1;33m[1]\033[0m Instalar Proxy")
            print("\033[1;33m[0]\033[0m Sair")
        else:
            print("\033[1;33m[1]\033[0m Adicionar Porta")
            print("\033[1;33m[2]\033[0m Remover Porta")
            print("\033[1;33m[3]\033[0m Reiniciar Porta")
            print("\033[1;33m[4]\033[0m Desinstalar Proxy")
            print("\033[1;33m[5]\033[0m Alternar Traffic Shaping")
            print("\033[1;33m[6]\033[0m Adicionar SSL")
            print("\033[1;33m[0]\033[0m Sair")
        
        print("\n\033[0;34m━"*10, "\033[1;32m ESCOLHA \033[0m", "\033[0;34m━\033[1;37m"*11, "\n")
        option = input("\033[1;33m ➜ \033[0m")
        
        if option == '1':
            if not is_proxy_installed():
                install_proxy()
                port_input = input("\n\033[1;33mDeseja iniciar proxy em qual porta? \033[0m")
                while not port_input.isdigit() or int(port_input) < 1 or int(port_input) > 65535:
                    print("\033[1;31m✗ Digite uma porta válida (1-65535).\033[0m")
                    port_input = input("\033[1;33mDeseja iniciar proxy em qual porta? \033[0m")
                add_proxy_port(int(port_input))
            else:
                port = input("\n\033[1;33m➜ Digite a porta para adicionar: \033[0m")
                while not port.isdigit() or int(port) < 1 or int(port) > 65535:
                    print("\033[1;31m✗ Digite uma porta válida (1-65535).\033[0m")
                    port = input("\033[1;33m➜ Digite a porta: \033[0m")
                add_proxy_port(int(port))
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '2' and is_proxy_installed():
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;33mPortas ativas:\033[0m")
                for port, status in port_info:
                    print(f" \033[1;32m{port}\033[0m - {status}")
                port = input("\n\033[1;33m➜ Digite a porta para remover: \033[0m")
                while not port.isdigit():
                    print("\033[1;31m✗ Digite uma porta válida.\033[0m")
                    port = input("\033[1;33m➜ Digite a porta: \033[0m")
                del_proxy_port(int(port))
            else:
                print("\033[1;31m✗ Nenhuma porta ativa para remover.\033[0m")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '3' and is_proxy_installed():
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;33mPortas disponíveis para reiniciar:\033[0m")
                for port, status in port_info:
                    print(f" \033[1;32m{port}\033[0m - {status}")
                port = input("\n\033[1;33m➜ Digite a porta para reiniciar (ou 'all' para todas): \033[0m")
               
                if port.lower() == 'all':
                    for p, _ in port_info:
                        restart_proxy_port(int(p))
                elif port.isdigit():
                    restart_proxy_port(int(port))
                else:
                    print("\033[1;31m✗ Opção inválida.\033[0m")
            else:
                print("\033[1;31m✗ Nenhuma porta ativa para reiniciar.\033[0m")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '4' and is_proxy_installed():
            uninstall_proxy()
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '5' and is_proxy_installed():
            enabled = config_manager.toggle_traffic_shaping()
            status = "\033[1;32mativada\033[0m" if enabled else "\033[1;31mdesativada\033[0m"
            print(f"\nTraffic Shaping {status} com sucesso!")
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '6' and is_proxy_installed():
            configure_ssl(config_manager)
            input("\n\033[1;33mPressione Enter para continuar...\033[0m")
           
        elif option == '0':
            print("\nSaindo...")
            sys.exit(0)
           
        else:
            print("\n\033[1;31m✗ Opção inválida.\033[0m")
            input("\033[1;33mPressione Enter para continuar...\033[0m")

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
