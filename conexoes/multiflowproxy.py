import asyncio
import sys
import socket
import os
import subprocess
import shutil

PORTS_FILE = "/opt/rustyproxy/ports"

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

def get_status_from_args():
    args = sys.argv[1:]
    status = "Switching Protocols"
    i = 0
    while i < len(args):
        if args[i] == "--status":
            if i + 1 < len(args):
                status = args[i + 1]
            i += 2
        else:
            i += 1
    return status

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
    status = get_status_from_args()
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
    server = await asyncio.start_server(handle_client, '::', port)
    print(f"Iniciando serviço na porta: {port}")
    await start_http(server)

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

def add_proxy_port(port, status="@RustyProxy"):
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return

    command = f"python /opt/rustyproxy/proxy.py --port {port} --status {status}"
    service_file_path = f"/etc/systemd/system/proxy{port}.service"
    service_content = f"""[Unit]
Description=RustyProxy{port}
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

    with open(service_file_path, 'w') as f:
        f.write(service_content)

    subprocess.run(['systemctl', 'daemon-reload'])
    subprocess.run(['systemctl', 'enable', f"proxy{port}.service"])
    subprocess.run(['systemctl', 'start', f"proxy{port}.service"])

    with open(PORTS_FILE, 'a') as f:
        f.write(f"{port}\n")

    print(f"Porta {port} aberta com sucesso.")

def del_proxy_port(port):
    subprocess.run(['systemctl', 'disable', f"proxy{port}.service"])
    subprocess.run(['systemctl', 'stop', f"proxy{port}.service"])
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

    print(f"Porta {port} fechada com sucesso.")

def restart_proxy_port(port):
    subprocess.run(['systemctl', 'restart', f"proxy{port}.service"])
    print(f"Proxy na porta {port} reiniciado com sucesso.")

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

    show_progress("Criando diretorio /opt/rustyproxy...")
    os.makedirs('/opt/rustyproxy', exist_ok=True)

    # Copiar o script atual para /opt/rustyproxy/proxy.py
    current_script = os.path.abspath(sys.argv[0])
    shutil.copy(current_script, '/opt/rustyproxy/proxy.py')

    show_progress("Configurando permissões...")
    os.chmod('/opt/rustyproxy/proxy.py', 0o755)
    os.symlink('/opt/rustyproxy/proxy.py', '/usr/local/bin/rustyproxy')

    if not os.path.exists(PORTS_FILE):
        open(PORTS_FILE, 'w').close()

    print("Instalação concluída com sucesso. Digite 'rustyproxy' para acessar o menu.")

def uninstall_proxy():
    if not is_root():
        error_exit("EXECUTE COMO ROOT")

    # Remover serviços
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            ports = f.read().splitlines()
        for port in ports:
            del_proxy_port(port)

    # Remover diretórios e links
    shutil.rmtree('/opt/rustyproxy', ignore_errors=True)
    os.remove('/usr/local/bin/rustyproxy') if os.path.exists('/usr/local/bin/rustyproxy') else None

    print("Desinstalação concluída com sucesso.")

def show_menu():
    while True:
        os.system('clear')
        print("------------------------------------------------")
        print("|                  MULTIFLOW PROXY             |")
        print("------------------------------------------------")

        active_ports = "nenhuma"
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, 'r') as f:
                active_ports = " ".join(f.read().splitlines())

        print(f"| Portas(s): {active_ports.ljust(34)}|")
        print("------------------------------------------------")
        print("| 1 - Instalar Proxy                           |")
        print("| 2 - Abrir Porta                              |")
        print("| 3 - Remover Porta                            |")
        print("| 4 - Reiniciar Proxy                          |")
        print("| 5 - Desinstalar Proxy                        |")
        print("| 0 - Voltar                                   |")
        print("------------------------------------------------")
        print()

        option = input(" --> Selecione uma opção: ")

        if option == '1':
            install_proxy()
            input("> Pressione qualquer tecla para voltar ao menu.")
        elif option == '2':
            port = input("Digite a porta: ")
            while not port.isdigit():
                print("Digite uma porta válida.")
                port = input("Digite a porta: ")
            status = input("Digite o status de conexão (deixe vazio para o padrão): ") or "@RustyProxy"
            add_proxy_port(int(port), status)
            input("> Porta ativada com sucesso. Pressione qualquer tecla para voltar ao menu.")
        elif option == '3':
            port = input("Digite a porta: ")
            while not port.isdigit():
                print("Digite uma porta válida.")
                port = input("Digite a porta: ")
            del_proxy_port(int(port))
            input("> Porta desativada com sucesso. Pressione qualquer tecla para voltar ao menu.")
        elif option == '4':
            port = input("Digite a porta para reiniciar: ")
            while not port.isdigit():
                print("Digite uma porta válida.")
                port = input("Digite a porta: ")
            restart_proxy_port(int(port))
            input("> Proxy reiniciado com sucesso. Pressione qualquer tecla para voltar ao menu.")
        elif option == '5':
            uninstall_proxy()
            input("> Desinstalação concluída. Pressione qualquer tecla para voltar ao menu.")
        elif option == '0':
            sys.exit(0)
        else:
            print("Opção inválida. Pressione qualquer tecla para voltar ao menu.")
            input()

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--port" in sys.argv):
        asyncio.run(run_proxy())
    else:
        if not is_root():
            error_exit("EXECUTE COMO ROOT para acessar o menu.")
        show_menu()
