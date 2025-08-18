import asyncio
import sys
import socket
import os
import subprocess
import shutil
import time
import random

PORTS_FILE = "/opt/multiflowproxy/ports"

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
   
    server_variants = ["nginx/1.18.0 (Ubuntu)", "Apache/2.4.41 (Ubuntu)", "Microsoft-IIS/10.0"]
   
    headers = "Server: {0}\r\n".format(random.choice(server_variants)) + \
              "Content-Length: 0\r\n" + \
              "Connection: keep-alive\r\n" + \
              "Date: {0}\r\n".format(time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime())) + \
              "Content-Type: text/html; charset=UTF-8\r\n" + \
              "Cache-Control: no-cache\r\n" + \
              "X-Content-Type-Options: nosniff\r\n" + \
              "X-Frame-Options: DENY\r\n" + \
              "X-XSS-Protection: 1; mode=block\r\n" + \
              "Strict-Transport-Security: max-age=31536000; includeSubDomains\r\n" + \
              "Set-Cookie: sessionid={0}; Path=/; HttpOnly\r\n\r\n".format(random.randint(100000, 999999))
   
    for status in status_options:
        response = "HTTP/1.1 {0}\r\n{1}".format(status, headers).encode()
        
        writer.write(response)
        await writer.drain()
       
        try:
            initial_data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            if initial_data:
                break
        except asyncio.TimeoutError:
            continue
   
    else:
        writer.close()
        await writer.wait_closed()
        return
   
    data_str = initial_data.decode('utf-8', errors='replace')
    addr_proxy = "0.0.0.0:22"
    if "SSH" in data_str or not initial_data:
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

    if initial_data:
        server_writer.write(initial_data)
        await server_writer.drain()

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

def add_proxy_port(port):
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return

    command = f"/usr/bin/python3 /opt/multiflowproxy/proxy.py --port {port}"
    service_file_path = f"/etc/systemd/system/proxy{port}.service"
    service_content = """[Unit]
Description=MultiflowProxy{0}
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
ExecStart={1}
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
""".format(port, command)

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

    print(f"Porta {port} aberta com sucesso.")

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

    print(f"Porta {port} fechada com sucesso.")

def restart_proxy_port(port):
    try:
        subprocess.run(['systemctl', 'restart', f"proxy{port}.service"], check=True)
        print(f"Proxy na porta {port} reiniciado com sucesso.")
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
    os.symlink('/opt/multiflowproxy/proxy.py', '/usr/local/bin/multiflowproxy')

    if not os.path.exists(PORTS_FILE):
        open(PORTS_FILE, 'w').close()

    print("Instalação concluída com sucesso. Digite 'multiflowproxy' para acessar o menu.")

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
    shutil.rmtree('/opt/multiflowproxy', ignore_errors=True)
    os.remove('/usr/local/bin/multiflowproxy') if os.path.exists('/usr/local/bin/multiflowproxy') else None

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
            add_proxy_port(int(port))
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
