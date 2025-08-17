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
    'ovpn_host': '0.0.0.0:1194',  # Added for OpenVPN target
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
    print(f"{message}")

def error_exit(message):
    print(f"\nErro: {message}")
    sys.exit(1)

def success_message(message):
    print(f"\n{message}")

def warning_message(message):
    print(f"\n{message}")

def info_message(message):
    print(f"{message}")

def print_header():
    """Imprime o cabeçalho estilizado do programa"""
    print("\033[2J\033[H")  # Limpa a tela completamente
    print("\033[1;36m" + "╔" + "═" * 58 + "╗" + "\033[0m")
    print("\033[1;36m║\033[0m" + " " * 58 + "\033[1;36m║\033[0m")
    print("\033[1;36m║\033[0m\033[1;32m  MULTIFLOW PROXY MANAGER  \033[0m\033[1;36m║\033[0m")
    print("\033[1;36m║\033[0m\033[1;37m Sistema Avançado de Proxy \033[0m\033[1;36m║\033[0m")
    print("\033[1;36m║\033[0m" + " " * 58 + "\033[1;36m║\033[0m")
    print("\033[1;36m" + "╚" + "═" * 58 + "╝" + "\033[0m")
    print()

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
            return "Ativo"
        else:
            return "Inativo"
    except:
        return "Erro"

def is_port_active(port):
    try:
        result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                                capture_output=True, text=True)
        return result.stdout.strip() == 'active'
    except:
        return False

def print_status_panel(config_manager):
    """Exibe o painel de status do sistema"""
    proxy_status = get_proxy_status()

    # Definir cores baseadas no status
    if "ATIVO" in proxy_status:
        status_color = "\033[1;32m"
        status_icon = ""
    elif "INATIVO" in proxy_status:
        status_color = "\033[1;33m"
        status_icon = ""
    else:
        status_color = "\033[1;31m"
        status_icon = ""

    # Obter informações das portas
    active_ports_info = []
    if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
        with open(PORTS_FILE, 'r') as f:
            ports = f.read().splitlines()
            for port in ports:
                if port.strip():
                    status = get_port_status(int(port))
                    active_ports_info.append(f"{port} {status}")

    # Status SSL
    ssl_status = "Ativado" if config_manager.config['ssl']['enabled'] else "Desativado"
    ssl_domain = config_manager.config['ssl'].get('domain', '')

    # Traffic Shaping
    ts_status = "Ativado" if config_manager.config['traffic_shaping']['enabled'] else "Desativado"

    print("\033[1;34m┌─ Status do Sistema\033[0m")
    print(f"\033[1;37m│ {status_icon} Status Geral: {status_color}{proxy_status}\033[0m")
    print(f"\033[1;37m│ SSL: {ssl_status}\033[0m")
    if ssl_domain:
        print(f"\033[1;37m│ └─ Domínio: \033[1;36m{ssl_domain}\033[0m")
    print(f"\033[1;37m│ Traffic Shaping: {ts_status}\033[0m")
    print("\033[1;34m└─\033[0m")
    print()

    # Painel de portas
    if active_ports_info:
        print("\033[1;34m┌─ Portas Configuradas\033[0m")
        for i, port_info in enumerate(active_ports_info):
            connector = "├─" if i < len(active_ports_info) - 1 else "└─"
            print(f"\033[1;34m{connector}\033[0m \033[1;37m Porta {port_info}\033[0m")
        print()
    else:
        print("\033[1;34m┌─ Portas Configuradas\033[0m")
        print("\033[1;34m└─\033[0m \033[1;33m Nenhuma porta configurada\033[0m")
        print()

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

async def handle_client(reader, writer, config):
    traffic_shaping = config['traffic_shaping'].copy()  # Copy to avoid mutable issues

    status_options = [
        "100 Continue",
        "101 Switching Protocols",
        "102 Processing",
        "103 Early Hints",
        "200 OK",
        "201 Created",
        "202 Accepted",
        "203 Non-Authoritative Information",
        "204 No Content",
        "205 Reset Content",
        "206 Partial Content",
        "207 Multi-Status",
        "208 Already Reported",
        "226 IM Used",
        "300 Multiple Choices",
        "301 Moved Permanently",
        "302 Found",
        "303 See Other",
        "304 Not Modified",
        "307 Temporary Redirect",
        "308 Permanent Redirect",
        "400 Bad Request",
        "401 Unauthorized",
        "402 Payment Required",
        "403 Forbidden",
        "404 Not Found",
        "405 Method Not Allowed",
        "406 Not Acceptable",
        "407 Proxy Authentication Required",
        "408 Request Timeout",
        "409 Conflict",
        "410 Gone",
        "411 Length Required",
        "412 Precondition Failed",
        "413 Payload Too Large",
        "414 URI Too Long",
        "415 Unsupported Media Type",
        "416 Range Not Satisfiable",
        "417 Expectation Failed",
        "418 I'm a teapot",
        "421 Misdirected Request",
        "422 Unprocessable Content",
        "423 Locked",
        "424 Failed Dependency",
        "425 Too Early",
        "426 Upgrade Required",
        "428 Precondition Required",
        "429 Too Many Requests",
        "431 Request Header Fields Too Large",
        "451 Unavailable For Legal Reasons",
        "500 Internal Server Error",
        "501 Not Implemented",
        "502 Bad Gateway",
        "503 Service Unavailable",
        "504 Gateway Timeout",
        "505 HTTP Version Not Supported",
        "506 Variant Also Negotiates",
        "507 Insufficient Storage",
        "508 Loop Detected",
        "510 Not Extended",
        "511 Network Authentication Required"
    ]

    server_variants = ["nginx/1.18.0 (Ubuntu)", "Apache/2.4.41 (Ubuntu)", "Microsoft-IIS/10.0"]  # Rotacionar para ofuscação
    user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # Exemplos
                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15"]

    headers = f"Server: {random.choice(server_variants)}\r\n" \
              f"Content-Length: 0\r\n" \
              f"Connection: keep-alive\r\n" \
              f"User-Agent: {random.choice(user_agents)}\r\n\r\n"  # Adicione mais se necessário

    for status in status_options:
        response = f"HTTP/1.1 {status}\r\n{headers}".encode()
        writer.write(response)
        await writer.drain()

        try:
            initial_data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            if initial_data:
                break  # Dados recebidos, prosseguir com este status
        except (asyncio.TimeoutError, Exception):
            continue  # Tentar próximo status se timeout

    else:
        # Se nenhum status funcionar, fechar conexão
        writer.close()
        await writer.wait_closed()
        return

    data_str = initial_data.decode('utf-8', errors='replace')
    if "SSH" in data_str or not initial_data:
        addr_proxy = config['default_host']
    else:
        addr_proxy = config['ovpn_host']

    try:
        server_reader, server_writer = await asyncio.open_connection(
            addr_proxy.split(':')[0], int(addr_proxy.split(':')[1])
        )
    except Exception:
        print("erro ao iniciar conexão para o proxy")
        writer.close()
        await writer.wait_closed()
        return

    if initial_data:
        server_writer.write(initial_data)
        await server_writer.drain()

    client_to_server = asyncio.create_task(transfer_data(reader, server_writer, traffic_shaping))
    server_to_client = asyncio.create_task(transfer_data(server_reader, writer, traffic_shaping))
    await asyncio.gather(client_to_server, server_to_client)

async def start_http(server):
    async with server:
        await server.serve_forever()

async def run_proxy():
    port = get_port_from_args()
    config_manager = ConfigManager()
    config = config_manager.config
    ssl_context = None
    if config['ssl']['enabled']:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_context.load_cert_chain(
                config['ssl']['cert_path'],
                config['ssl']['key_path']
            )
        except Exception as e:
            print(f"Erro ao carregar certificado SSL: {e}")
            sys.exit(1)
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(('::', port))
        sock.listen(100)
        server = await asyncio.start_server(lambda r, w: handle_client(r, w, config), sock=sock, ssl=ssl_context)
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
        warning_message(f"A porta {port} já está em uso.")
        return

    print(f"\n Configurando porta {port}...")
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
    success_message(f"Porta {port} adicionada e iniciada com sucesso!")

def del_proxy_port(port):
    print(f"\n Removendo porta {port}...")
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
    success_message(f"Porta {port} removida com sucesso!")

def restart_proxy_port(port):
    print(f"\n Reiniciando porta {port}...")
    service_name = f"proxy{port}.service"
    subprocess.run(['systemctl', 'restart', service_name])
    success_message(f"Porta {port} reiniciada com sucesso!")

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
        show_progress(f"Progresso: [{CURRENT_STEP}/{TOTAL_STEPS}]")

    print_header()
    print("\033[1;32m INICIANDO INSTALAÇÃO DO MULTIFLOW PROXY\033[0m\n")

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
    show_progress(f"Sistema {os_name} {version} suportado!")
    increment_step()

    show_progress("Atualizando o sistema e instalando dependências...")
    try:
        subprocess.run(['apt', 'upgrade', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['apt-get', 'install', 'curl', 'build-essential', 'git', '-y'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        error_exit("Falha ao atualizar o sistema ou instalar pacotes")
    increment_step()

    show_progress("Criando estrutura de diretórios...")
    os.makedirs('/opt/multiflowproxy', exist_ok=True)
    increment_step()

    show_progress("Copiando arquivos do sistema...")
    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/multiflowproxy/multiflowproxy.py')
    increment_step()

    show_progress("Configurando permissões e links simbólicos...")
    os.chmod('/opt/multiflowproxy/multiflowproxy.py', 0o755)
    if os.path.exists('/usr/local/bin/multiflowproxy'):
        os.remove('/usr/local/bin/multiflowproxy')
    os.symlink('/opt/multiflowproxy/multiflowproxy.py', '/usr/local/bin/multiflowproxy')
    increment_step()

    show_progress("Finalizando configuração...")
    time.sleep(1)
    increment_step()

    show_progress("Limpeza final...")
    increment_step()

    print("\n" + "="*60)
    success_message("INSTALAÇÃO CONCLUÍDA COM SUCESSO!")
    print("\n\033[1;36m Para acessar o menu, digite: \033[1;32mmultiflowproxy\033[0m")
    print("\033[1;36m Ou execute novamente este script como root.\033[0m")
    print("="*60)

def uninstall_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")

    print("\n Iniciando desinstalação...")

    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            ports = f.read().splitlines()
        print(" Removendo serviços das portas...")
        for port in ports:
            if port.strip():
                del_proxy_port(int(port))

    print(" Removendo diretórios e arquivos...")
    if os.path.exists(PROXY_DIR):
        shutil.rmtree(PROXY_DIR)

    if os.path.exists('/usr/local/bin/multiflowproxy'):
        os.remove('/usr/local/bin/multiflowproxy')

    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

    success_message("DESINSTALAÇÃO CONCLUÍDA COM SUCESSO!")

def generate_ssl_cert(domain, email):
    try:
        print("\n Configurando certificado SSL...")

        # Instalar Certbot se não estiver instalado
        if not shutil.which('certbot'):
            print(" Instalando Certbot...")
            subprocess.run(['apt', 'install', 'snapd', '-y'], check=True)
            subprocess.run(['snap', 'install', 'core'], check=True)
            subprocess.run(['snap', 'refresh', 'core'], check=True)
            subprocess.run(['snap', 'install', '--classic', 'certbot'], check=True)
            subprocess.run(['ln', '-s', '/snap/bin/certbot', '/usr/bin/certbot'], check=True)

        # Parar porta 80 temporariamente se ativa
        was_running = False
        if is_port_active(80):
            print(" Parando porta 80 temporariamente...")
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
        print(" Gerando certificado SSL...")
        subprocess.run(cmd, check=True)

        # Reiniciar porta 80 se estava rodando
        if was_running:
            print(" Reiniciando porta 80...")
            subprocess.run(['systemctl', 'start', 'proxy80.service'], check=True)

        success_message("Certificado SSL gerado com sucesso!")
        return True
    except Exception as e:
        print(f"\n\033[1;31m Erro ao gerar certificado SSL: {e}\033[0m")
        return False

def configure_ssl(config_manager):
    print("\n\033[1;34m┌─ Configuração SSL\033[0m")
    print("\033[1;34m│\033[0m")
    print("\033[1;34m│\033[0m \033[1;37mEscolha a configuração de porta para SSL:\033[0m")
    print("\033[1;34m│\033[0m")
    print("\033[1;34m│\033[0m \033[1;32m[1]\033[0m  HTTP (80) + HTTPS (443)")
    print("\033[1;34m│\033[0m \033[1;32m[2]\033[0m  Apenas HTTPS (443)")
    print("\033[1;34m│\033[0m")
    print("\033[1;34m└─\033[0m")

    option = input("\n\033[1;33m Escolha uma opção (1 ou 2): \033[0m")
    while option not in ['1', '2']:
        print("\033[1;31m Opção inválida. Escolha 1 ou 2.\033[0m")
        option = input("\033[1;33m Escolha uma opção (1 ou 2): \033[0m")

    print("\n" + "─" * 50)
    domain = input("\n \033[1;37mDigite o seu domínio (ex: meusite.com.br):\033[0m\n\033[1;33m➤ \033[0m")
    while not domain:
        print("\033[1;31m Domínio obrigatório.\033[0m")
        domain = input("\033[1;33m Digite o domínio: \033[0m")

    email = input("\n \033[1;37mDigite seu email para notificações (opcional):\033[0m\n\033[1;33m➤ \033[0m").strip()

    if generate_ssl_cert(domain, email):
        config_manager.config['ssl']['enabled'] = True
        config_manager.config['ssl']['domain'] = domain
        config_manager.config['ssl']['email'] = email
        config_manager.config['ssl']['cert_path'] = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        config_manager.config['ssl']['key_path'] = f"/etc/letsencrypt/live/{domain}/privkey.pem"
        config_manager.save_config()

        # Adicionar portas conforme opção
        print("\n Configurando portas...")
        if option == '1':
            if not os.path.exists(PORTS_FILE) or '80' not in open(PORTS_FILE).read():
                add_proxy_port(80)
            add_proxy_port(443)
        elif option == '2':
            add_proxy_port(443)
    else:
        print("\033[1;31m Falha ao configurar SSL.\033[0m")

def remove_ssl(config_manager):
    if not config_manager.config['ssl']['enabled']:
        warning_message("SSL já está desativado.")
        return

    print("\n Desativando SSL...")
    config_manager.config['ssl']['enabled'] = False
    config_manager.config['ssl']['cert_path'] = ''
    config_manager.config['ssl']['key_path'] = ''
    config_manager.save_config()

    success_message("SSL desativado com sucesso!")

    # Reiniciar portas 80 e 443 se estiverem ativas
    print(" Reiniciando serviços...")
    for port in [80, 443]:
        if is_port_active(port):
            restart_proxy_port(port)

def print_menu_options(is_installed):
    """Imprime as opções do menu de forma estilizada"""
    print("\033[1;34m┌─ Menu de Opções\033[0m")

    if not is_installed:
        print("\033[1;34m│\033[0m")
        print("\033[1;34m│\033[0m \033[1;32m[1]\033[0m  \033[1;37mInstalar Proxy\033[0m")
        print("\033[1;34m│\033[0m \033[1;31m[0]\033[0m  \033[1;37mSair\033[0m")
        print("\033[1;34m│\033[0m")
    else:
        print("\033[1;34m│\033[0m")
        print("\033[1;34m│\033[0m \033[1;32m[1]\033[0m  \033[1;37mAdicionar Porta\033[0m")
        print("\033[1;34m│\033[0m \033[1;33m[2]\033[0m  \033[1;37mRemover Porta\033[0m")
        print("\033[1;34m│\033[0m \033[1;36m[3]\033[0m  \033[1;37mReiniciar Porta\033[0m")
        print("\033[1;34m│\033[0m \033[1;35m[4]\033[0m  \033[1;37mDesinstalar Proxy\033[0m")
        print("\033[1;34m│\033[0m \033[1;34m[5]\033[0m  \033[1;37mAlternar Traffic Shaping\033[0m")
        print("\033[1;34m│\033[0m \033[1;32m[6]\033[0m  \033[1;37mConfigurar SSL\033[0m")
        print("\033[1;34m│\033[0m \033[1;31m[7]\033[0m  \033[1;37mRemover SSL\033[0m")
        print("\033[1;34m│\033[0m \033[1;37m[8]\033[0m  \033[1;37mMonitorar Sistema\033[0m")
        print("\033[1;34m│\033[0m \033[1;31m[0]\033[0m  \033[1;37mSair\033[0m")
        print("\033[1;34m│\033[0m")

    print("\033[1;34m└─\033[0m")

def get_user_input(prompt, validation_func=None):
    """Função auxiliar para entrada do usuário com validação"""
    while True:
        try:
            value = input(f"\n\033[1;33m{prompt}\033[0m")
            if validation_func is None or validation_func(value):
                return value
            else:
                print("\033[1;31m Valor inválido. Tente novamente.\033[0m")
        except KeyboardInterrupt:
            print("\n\n\033[1;31m Operação cancelada pelo usuário.\033[0m")
            return None

def validate_port(port_str):
    """Valida se a entrada é uma porta válida"""
    try:
        port = int(port_str)
        return 1 <= port <= 65535
    except ValueError:
        return False

def monitor_system():
    """Função para monitorar o sistema em tempo real"""
    print_header()
    print("\033[1;32m MONITOR DO SISTEMA - MULTIFLOW PROXY\033[0m")
    print("\033[1;37m(Pressione Ctrl+C para voltar ao menu)\033[0m\n")

    try:
        while True:
            # Limpar apenas o conteúdo do monitor, manter o cabeçalho
            print("\033[10;1H\033[J")  # Move para linha 10 e limpa dali para baixo

            # Informações do sistema
            try:
                # CPU e Memória
                cpu_info = subprocess.run(['top', '-bn1'], capture_output=True, text=True).stdout
                load_avg = subprocess.run(['uptime'], capture_output=True, text=True).stdout.strip()

                print("\033[1;34m┌─ Recursos do Sistema\033[0m")
                print(f"\033[1;37m│  Load Average: \033[1;32m{load_avg.split('load average:')[-1].strip()}\033[0m")

                # CPU usage from top
                cpu_lines = [line for line in cpu_info.split('\n') if line.startswith('%Cpu(s):')]
                if cpu_lines:
                    cpu = cpu_lines[0].split(':')[1].strip()
                    print(f"\033[1;37m│  CPU: \033[1;32m{cpu}\033[0m")

                # Memória
                mem_info = subprocess.run(['free', '-h'], capture_output=True, text=True).stdout.split('\n')[1]
                mem_parts = mem_info.split()
                print(f"\033[1;37m│  Memória: \033[1;32m{mem_parts[2]}\033[0m usado de \033[1;36m{mem_parts[1]}\033[0m total")

                # Espaço em disco
                disk_info = subprocess.run(['df', '-h', '/'], capture_output=True, text=True).stdout.split('\n')[1]
                disk_parts = disk_info.split()
                print(f"\033[1;37m│  Disco: \033[1;32m{disk_parts[2]}\033[0m usado de \033[1;36m{disk_parts[1]}\033[0m total")
                print("\033[1;34m└─\033[0m")
                print()

                # Status das portas em tempo real
                port_info = list_active_ports()
                if port_info:
                    print("\033[1;34m┌─ Status das Portas (Tempo Real)\033[0m")
                    for i, (port, status) in enumerate(port_info):
                        # Verificar conexões ativas na porta
                        try:
                            netstat_result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
                            connections = len([line for line in netstat_result.stdout.split('\n')
                                               if f':{port}' in line and 'ESTABLISHED' in line])
                            connector = "├─" if i < len(port_info) - 1 else "└─"
                            print(f"\033[1;34m{connector}\033[0m \033[1;37m Porta {port}: {status} \033[1;36m({connections} conexões)\033[0m")
                        except:
                            connector = "├─" if i < len(port_info) - 1 else "└─"
                            print(f"\033[1;34m{connector}\033[0m \033[1;37m Porta {port}: {status}\033[0m")
                    print()

                # Logs recentes (últimas 5 linhas do syslog)
                try:
                    recent_logs = subprocess.run(['tail', '-5', '/var/log/syslog'], capture_output=True, text=True).stdout
                    if recent_logs:
                        print("\033[1;34m┌─ Logs Recentes\033[0m")
                        for line in recent_logs.strip().split('\n')[-3:]:  # Só mostrar 3 linhas
                            if line.strip():
                                timestamp = line.split()[0:3]
                                print(f"\033[1;34m│\033[0m \033[1;37m{' '.join(timestamp)}\033[0m \033[0;37m{' '.join(line.split()[3:])[:60]}...\033[0m")
                        print("\033[1;34m└─\033[0m")
                        print()
                except:
                    pass

                print(f"\033[1;37m Atualizado em: {time.strftime('%H:%M:%S')}\033[0m")
                print("\033[1;33m(Atualizando a cada 3 segundos...)\033[0m")

            except Exception as e:
                print(f"\033[1;31m Erro ao obter informações do sistema: {e}\033[0m")

            time.sleep(3)

    except KeyboardInterrupt:
        print("\n\n\033[1;32m Saindo do monitor...\033[0m")
        time.sleep(1)

def show_menu():
    config_manager = ConfigManager()

    while True:
        print_header()
        print_status_panel(config_manager)
        print_menu_options(is_proxy_installed())

        print("\n" + "─" * 60)
        option = input("\033[1;33m Digite sua escolha: \033[0m").strip()

        if option == '1':
            if not is_proxy_installed():
                # Instalação
                confirm = input("\n\033[1;33m Deseja realmente instalar o MultiFlow Proxy? (s/N): \033[0m").lower()
                if confirm in ['s', 'sim', 'y', 'yes']:
                    install_proxy()

                    # Perguntar sobre primeira porta após instalação
                    print("\n" + "─" * 60)
                    print("\033[1;36m Proxy instalado! Vamos configurar a primeira porta.\033[0m")
                    port_input = get_user_input(" Digite a porta inicial (ex: 80, 443, 8080): ", validate_port)

                    if port_input:
                        add_proxy_port(int(port_input))
                else:
                    info_message("Instalação cancelada.")
            else:
                # Adicionar porta
                port_input = get_user_input(" Digite a porta para adicionar (1-65535): ", validate_port)
                if port_input:
                    add_proxy_port(int(port_input))

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '2' and is_proxy_installed():
            # Remover porta
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;34m┌─ Portas Disponíveis para Remoção\033[0m")
                for i, (port, status) in enumerate(port_info):
                    connector = "├─" if i < len(port_info) - 1 else "└─"
                    print(f"\033[1;34m{connector}\033[0m \033[1;37m {port} - {status}\033[0m")

                port_input = get_user_input(" Digite a porta para remover: ",
                                            lambda x: x.isdigit() and x in [p[0] for p in port_info])
                if port_input:
                    confirm = input(f"\n\033[1;31m Confirma a remoção da porta {port_input}? (s/N): \033[0m").lower()
                    if confirm in ['s', 'sim', 'y', 'yes']:
                        del_proxy_port(int(port_input))
                    else:
                        info_message("Remoção cancelada.")
            else:
                warning_message("Nenhuma porta configurada para remover.")

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '3' and is_proxy_installed():
            # Reiniciar porta
            port_info = list_active_ports()
            if port_info:
                print("\n\033[1;34m┌─ Portas Disponíveis para Reiniciar\033[0m")
                print("\033[1;34m│\033[0m")
                for i, (port, status) in enumerate(port_info):
                    connector = "├─" if i < len(port_info) - 1 else "└─"
                    print(f"\033[1;34m{connector}\033[0m \033[1;37m {port} - {status}\033[0m")
                print("\033[1;34m│\033[0m")
                print(f"\033[1;34m└─\033[0m \033[1;36m Digite 'all' para reiniciar todas\033[0m")

                port_input = input(f"\n\033[1;33m Digite a porta ou 'all': \033[0m").strip().lower()

                if port_input == 'all':
                    confirm = input(f"\n\033[1;33m Confirma reiniciar TODAS as portas? (s/N): \033[0m").lower()
                    if confirm in ['s', 'sim', 'y', 'yes']:
                        print(f"\n Reiniciando todas as portas...")
                        for port, _ in port_info:
                            restart_proxy_port(int(port))
                        success_message("Todas as portas foram reiniciadas!")
                    else:
                        info_message("Operação cancelada.")
                elif port_input.isdigit() and port_input in [p[0] for p in port_info]:
                    restart_proxy_port(int(port_input))
                else:
                    warning_message("Porta inválida ou não encontrada.")
            else:
                warning_message("Nenhuma porta configurada para reiniciar.")

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '4' and is_proxy_installed():
            # Desinstalar
            print("\n\033[1;31m ATENÇÃO: Esta ação irá remover completamente o MultiFlow Proxy!\033[0m")
            print("\033[1;33m Isso incluirá:\033[0m")
            print(" • Todos os serviços das portas")
            print(" • Arquivos de configuração")
            print(" • Certificados SSL")
            print(" • Diretórios do sistema")

            confirm = input(f"\n\033[1;31m Digite 'CONFIRMAR' para prosseguir: \033[0m")
            if confirm == 'CONFIRMAR':
                uninstall_proxy()
            else:
                info_message("Desinstalação cancelada.")

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '5' and is_proxy_installed():
            # Traffic Shaping
            current_status = "ativado" if config_manager.config['traffic_shaping']['enabled'] else "desativado"
            print(f"\n\033[1;37m Traffic Shaping está atualmente: \033[1;36m{current_status}\033[0m")

            confirm = input(f"\n\033[1;33m Deseja alternar o Traffic Shaping? (s/N): \033[0m").lower()
            if confirm in ['s', 'sim', 'y', 'yes']:
                enabled = config_manager.toggle_traffic_shaping()
                new_status = "\033[1;32mativado\033[0m" if enabled else "\033[1;31mdesativado\033[0m"
                success_message(f"Traffic Shaping {new_status}!")

                # Reiniciar todas as portas para aplicar mudanças
                port_info = list_active_ports()
                if port_info:
                    print(" Reiniciando portas para aplicar mudanças...")
                    for port, _ in port_info:
                        restart_proxy_port(int(port))
            else:
                info_message("Operação cancelada.")

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '6' and is_proxy_installed():
            # Configurar SSL
            if config_manager.config['ssl']['enabled']:
                warning_message(f"SSL já está ativado para o domínio: {config_manager.config['ssl']['domain']}")
                renew = input("\n\033[1;33m Deseja reconfigurar o SSL? (s/N): \033[0m").lower()
                if renew not in ['s', 'sim', 'y', 'yes']:
                    input("\n\033[1;33m Pressione Enter para continuar...\033[0m")
                    continue

            configure_ssl(config_manager)
            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '7' and is_proxy_installed():
            # Remover SSL
            if not config_manager.config['ssl']['enabled']:
                warning_message("SSL já está desativado.")
            else:
                confirm = input(f"\n\033[1;31m Confirma a remoção do SSL? (s/N): \033[0m").lower()
                if confirm in ['s', 'sim', 'y', 'yes']:
                    remove_ssl(config_manager)
                else:
                    info_message("Operação cancelada.")

            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

        elif option == '8' and is_proxy_installed():
            # Monitor do sistema
            monitor_system()

        elif option == '0':
            print("\n\033[1;36m Obrigado por usar o MultiFlow Proxy!\033[0m")
            print("\033[1;37m Sistema desenvolvido para alta performance e segurança.\033[0m")
            sys.exit(0)

        else:
            warning_message("Opção inválida. Tente novamente.")
            input("\n\033[1;33m Pressione Enter para continuar...\033[0m")

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
