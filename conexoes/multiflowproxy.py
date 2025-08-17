import asyncio
import sys
import socket
import os
import subprocess
import shutil
PORTS_FILE = "/opt/multiflowproxy/ports"
PROXY_DIR = "/opt/multiflowproxy"
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
    """Verifica se o proxy está instalado"""
    return os.path.exists(PROXY_DIR) and os.path.exists('/usr/local/bin/multiflowproxy')
def get_proxy_status():
    """Retorna o status geral do proxy"""
    if not is_proxy_installed():
        return "NÃO INSTALADO"
   
    if not os.path.exists(PORTS_FILE):
        return "INSTALADO - INATIVO"
   
    with open(PORTS_FILE, 'r') as f:
        ports = f.read().splitlines()
   
    if not ports:
        return "INSTALADO - INATIVO"
   
    # Verifica se algum serviço está rodando
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
    """Verifica o status de uma porta específica"""
    try:
        result = subprocess.run(['systemctl', 'is-active', f'proxy{port}.service'],
                              capture_output=True, text=True)
        if result.stdout.strip() == 'active':
            return "✓ Ativo"
        else:
            return "✗ Inativo"
    except:
        return "✗ Erro"
async def peek_stream(transport):
    sock = transport.get_extra_info('socket')
    if sock is None:
        return ""
    peek_buffer = sock.recv(8192, socket.MSG_PEEK)
    data_str = peek_buffer.decode('utf-8', errors='replace')
    return data_str
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
    writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
    await writer.drain()
    buffer = await reader.read(1024)
    writer.write(f"HTTP/1.1 200 OK\r\n\r\n".encode())
    await writer.drain()
    try:
        data = await asyncio.wait_for(peek_stream(writer.transport), timeout=1.0)
    except asyncio.TimeoutError:
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
    except Exception:
        return False
def list_active_ports():
    """Lista todas as portas ativas com seus status"""
    if not os.path.exists(PORTS_FILE):
        return []
   
    with open(PORTS_FILE, 'r') as f:
        ports = f.read().splitlines()
   
    port_info = []
    for port in ports:
        status = get_port_status(port)
        port_info.append((port, status))
   
    return port_info
def add_proxy_port(port):
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    command = f"/usr/bin/python3 /opt/multiflowproxy/proxy.py --port {port}"
    service_file_path = f"/etc/systemd/system/proxy{port}.service"
    service_content = f"""[Unit]
Description=MultiflowProxy{port}
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
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
"""
    with open(service_file_path, 'w') as f:
        f.write(service_content)
    subprocess.run(['systemctl', 'daemon-reload'])
    try:
        subprocess.run(['systemctl', 'enable', f"proxy{port}.service"], check=True)
        subprocess.run(['systemctl', 'start', f"proxy{port}.service"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Falha ao ativar o serviço: {e.stderr.decode() if e.stderr else str(e)}")
        return
    with open(PORTS_FILE, 'a') as f:
        f.write(f"{port}\n")
    print(f"✓ Porta {port} aberta com sucesso.")
def del_proxy_port(port):
    try:
        subprocess.run(['systemctl', 'disable', f"proxy{port}.service"], check=True)
        subprocess.run(['systemctl', 'stop', f"proxy{port}.service"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Falha ao desativar o serviço: {e.stderr.decode() if e.stderr else str(e)}")
    if os.path.exists(f"/etc/systemd/system/proxy{port}.service"):
        os.remove(f"/etc/systemd/system/proxy{port}.service")
    subprocess.run(['systemctl', 'daemon-reload'])
    lines = []
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            lines = f.readlines()
        with open(PORTS_FILE, 'w') as f:
            for line in lines:
                if line.strip() != str(port):
                    f.write(line)
    print(f"✓ Porta {port} fechada com sucesso.")
def restart_proxy_port(port):
    try:
        subprocess.run(['systemctl', 'restart', f"proxy{port}.service"], check=True)
        print(f"✓ Proxy na porta {port} reiniciado com sucesso.")
    except subprocess.CalledProcessError as e:
        print(f"Falha ao reiniciar o serviço: {e.stderr.decode() if e.stderr else str(e)}")
        print(f"Dica: Rode 'systemctl status proxy{port}.service' ou 'journalctl -xeu proxy{port}.service' para detalhes.")
def install_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")
    show_progress("Atualizando repositorios...")
    subprocess.run(['apt', 'update', '-y'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    show_progress("Verificando o sistema...")
    try:
        subprocess.run(['lsb_release'], check=True, stdout=subprocess.DEVNULL)
    except:
        subprocess.run(['apt', 'install', 'lsb-release', '-y'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os_name = subprocess.run(['lsb_release', '-is'], capture_output=True, text=True).stdout.strip()
    version = subprocess.run(['lsb_release', '-rs'], capture_output=True, text=True).stdout.strip()
    supported = False
    if os_name == 'Ubuntu' and version.startswith(('24.', '22.', '20.', '18.')):
        supported = True
    elif os_name == 'Debian' and version.startswith(('12', '11', '10', '9')):
        supported = True
    if not supported:
        error_exit("Sistema não suportado. Use Ubuntu ou Debian.")
    show_progress("Atualizando o sistema...")
    subprocess.run(['apt', 'upgrade', '-y'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['apt-get', 'install', 'curl', 'build-essential', 'git', '-y'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    show_progress("Criando diretorio /opt/multiflowproxy...")
    os.makedirs('/opt/multiflowproxy', exist_ok=True)
    # Copiar o script atual para /opt/multiflowproxy/proxy.py
    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/multiflowproxy/proxy.py')
    show_progress("Configurando permissões...")
    os.chmod('/opt/multiflowproxy/proxy.py', 0o755)
   
    # Remover link simbólico se já existir
    if os.path.exists('/usr/local/bin/multiflowproxy'):
        os.remove('/usr/local/bin/multiflowproxy')
    os.symlink('/opt/multiflowproxy/proxy.py', '/usr/local/bin/multiflowproxy')
    if not os.path.exists(PORTS_FILE):
        open(PORTS_FILE, 'w').close()
    print("\n✓ Instalação concluída com sucesso!")
    # Perguntar pela porta e iniciar o proxy nessa porta
    port = input("\n➜ Digite a porta para iniciar o proxy: ")
    while not port.isdigit() or int(port) < 1 or int(port) > 65535:
        print("✗ Digite uma porta válida (1-65535).")
        port = input("➜ Digite a porta: ")
    add_proxy_port(int(port))
def uninstall_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")
    confirm = input("Tem certeza que deseja desinstalar o proxy? (s/n): ")
    if confirm.lower() != 's':
        print("Desinstalação cancelada.")
        return
    # Remover serviços
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            ports = f.read().splitlines()
        for port in ports:
            del_proxy_port(port)
    # Remover diretórios e links
    shutil.rmtree('/opt/multiflowproxy', ignore_errors=True)
    if os.path.exists('/usr/local/bin/multiflowproxy'):
        os.remove('/usr/local/bin/multiflowproxy')
    print("\n✓ Desinstalação concluída com sucesso.")
def show_menu():
    while True:
        os.system('clear')
       
        # Obter status do proxy
        proxy_status = get_proxy_status()
       
        # Definir cor do status baseado no estado
        if "ATIVO" in proxy_status:
            status_display = f"\033[92m{proxy_status}\033[0m" # Verde
        elif "INATIVO" in proxy_status:
            status_display = f"\033[93m{proxy_status}\033[0m" # Amarelo
        else:
            status_display = f"\033[91m{proxy_status}\033[0m" # Vermelho
       
        print("================================================")
        print("| MULTIFLOW PROXY |")
        print("================================================")
        print(f"| Status: {status_display:<45}|")
        print("------------------------------------------------")
       
        active_ports = "Nenhuma porta configurada"
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, 'r') as f:
                ports = f.read().splitlines()
                if ports:
                    active_ports = ", ".join(ports[:3])
                    if len(ports) > 3:
                        active_ports += f" (+{len(ports)-3})"
       
        print(f"| Portas: {active_ports[:37]:<37}|")
        print("================================================")
       
        if not is_proxy_installed():
            print("| 1 - Instalar Proxy ")
            print("| 0 - Sair ")
        else:
            print("| 1 - Adicionar Porta ")
            print("| 2 - Remover Porta ")
            print("| 3 - Reiniciar Proxy ")
            print("| 4 - Desinstalar Proxy ")
            print("| 0 - Sair ")
       
        print("================================================")
        print()
        option = input(" ➜ Selecione uma opção: ")
        if option == '1':
            if not is_proxy_installed():
                install_proxy()
            else:
                # Adicionar nova porta
                port = input("\n➜ Digite a porta para adicionar: ")
                while not port.isdigit() or int(port) < 1 or int(port) > 65535:
                    print("✗ Digite uma porta válida (1-65535).")
                    port = input("➜ Digite a porta: ")
                add_proxy_port(int(port))
            input("\n➜ Pressione Enter para continuar...")
           
        elif option == '2' and is_proxy_installed():
            port_info = list_active_ports()
            if port_info:
                print("\nPortas ativas:")
                for port, status in port_info:
                    print(f" {port} - {status}")
                port = input("\n➜ Digite a porta para remover: ")
                while not port.isdigit():
                    print("✗ Digite uma porta válida.")
                    port = input("➜ Digite a porta: ")
                del_proxy_port(int(port))
            else:
                print("✗ Nenhuma porta ativa para remover.")
            input("\n➜ Pressione Enter para continuar...")
           
        elif option == '3' and is_proxy_installed():
            port_info = list_active_ports()
            if port_info:
                print("\nPortas disponíveis para reiniciar:")
                for port, status in port_info:
                    print(f" {port} - {status}")
                port = input("\n➜ Digite a porta para reiniciar (ou 'all' para todas): ")
               
                if port.lower() == 'all':
                    for p, _ in port_info:
                        restart_proxy_port(int(p))
                elif port.isdigit():
                    restart_proxy_port(int(port))
                else:
                    print("✗ Opção inválida.")
            else:
                print("✗ Nenhuma porta ativa para reiniciar.")
            input("\n➜ Pressione Enter para continuar...")
           
        elif option == '4' and is_proxy_installed():
            uninstall_proxy()
            input("\n➜ Pressione Enter para continuar...")
           
        elif option == '0':
            print("\nSaindo...")
            sys.exit(0)
           
        else:
            print("\n✗ Opção inválida.")
            input("➜ Pressione Enter para continuar...")
if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
