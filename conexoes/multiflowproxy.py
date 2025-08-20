import argparse
import asyncio
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Tuple

# Dicionário com os status HTTP adicionados
HTTP_STATUS = {
    100: "Continue",
    101: "Switching Protocols",
    200: "Connection Established",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found",
    403: "Forbidden",
    404: "Not Found",
    503: "Service Unavailable"
}

async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, status: str) -> None:
    """Atende uma conexão: lê cabeçalhos, decide backend e faz proxy bidirecional."""
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return
    header_text = initial_data.decode("utf-8", errors="ignore")
    def find_header(text: str, header: str) -> str:
        idx = text.find(header + ": ")
        if idx == -1:
            return ""
        idx = text.find(":", idx)
        value = text[idx + 2 :]
        end = value.find("\r\n")
        if end == -1:
            return ""
        return value[:end]
    host_port_header = find_header(header_text, "X-Real-Host")
    x_split_header = find_header(header_text, "X-Split")
    backend_host: str
    backend_port: int
    if host_port_header:
        if ":" in host_port_header:
            hp_host, hp_port_str = host_port_header.rsplit(":", 1)
            try:
                backend_port = int(hp_port_str)
            except ValueError:
                backend_port = 22
            backend_host = hp_host
        else:
            backend_host = host_port_header
            backend_port = 22
    else:
        try:
            backend_host, backend_port = await asyncio.wait_for(
                probe_backend(client_reader, client_writer), timeout=1.0
            )
        except asyncio.TimeoutError:
            backend_host, backend_port = ("0.0.0.0", 22)
    if x_split_header:
        try:
            await client_reader.read(8192)
        except Exception:
            pass
    try:
        client_writer.write(f"HTTP/1.1 101 {HTTP_STATUS[101]}\r\nServer: Apache/2.4.41 (Ubuntu)\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36\r\nConnection: Upgrade\r\nKeep-Alive: timeout=60\r\n\r\n".encode())
        await client_writer.drain()
        client_writer.write(f"HTTP/1.1 200 {HTTP_STATUS[200]}\r\nServer: Apache/2.4.41 (Ubuntu)\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36\r\nConnection: keep-alive\r\nKeep-Alive: timeout=60\r\nContent-Length: 0\r\n\r\n".encode())
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha no handshake com o cliente: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        """Copia dados de uma ponta à outra até EOF/erro."""
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Erro no fluxo %s: %s", direction, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    client_to_server = asyncio.create_task(forward(client_reader, server_writer, "cliente->servidor"))
    server_to_client = asyncio.create_task(forward(server_reader, client_writer, "servidor->cliente"))
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)
async def probe_backend(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> Tuple[str, int]:
    """Espia os primeiros bytes: se contiver 'SSH' ou vazio → 22; caso contrário → 1194."""
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)
    sock: socket.socket = client_writer.get_extra_info("socket") # type: ignore
    if sock is None:
        return default_backend
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        await loop.sock_recv(sock, 0)
        data_bytes = sock.recv(8192, socket.MSG_PEEK)
        text = data_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return default_backend
    if not text or 'SSH' in text.upper():
        return default_backend
    return alt_backend
async def run_proxy(port: int, status: str) -> None:
    """Inicia o listener (IPv4/IPv6) e aceita conexões para o proxy."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)
    server = await asyncio.start_server(lambda r, w: handle_client(r, w, status), sock=sock)
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Iniciando MultiFlow em %s", addr_list)
    async with server:
        await server.serve_forever()
# Registro de portas ativas (persistência do menu)
PORTS_FILE = Path("/opt/multiflow/ports")
def is_port_in_use(port: int) -> bool:
    """Retorna True se a porta TCP já estiver em uso localmente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0
def add_proxy_port(port: int, status: str) -> None:
    """Cria/inicia um serviço systemd que executa este script no modo proxy."""
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    command = f"{sys.executable} {script_path} --port {port} --status {status}"
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    service_content = f"""[Unit]
Description=MultiFlow{port}
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
    service_file_path.write_text(service_content)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", f"proxy{port}.service"], check=False)
    subprocess.run(["systemctl", "start", f"proxy{port}.service"], check=False)
    PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PORTS_FILE.open("a") as f:
        f.write(f"{port}\n")
    print(f"Porta {port} aberta com sucesso.")
def del_proxy_port(port: int) -> None:
    """Para e remove o serviço systemd da porta informada."""
    subprocess.run(["systemctl", "disable", f"proxy{port}.service"], check=False)
    subprocess.run(["systemctl", "stop", f"proxy{port}.service"], check=False)
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    if service_file_path.exists():
        service_file_path.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    if PORTS_FILE.exists():
        lines = [l.strip() for l in PORTS_FILE.read_text().splitlines() if l.strip()]
        lines = [l for l in lines if l != str(port)]
        PORTS_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Porta {port} fechada com sucesso.")
def show_menu() -> None:
    """Menu interativo para abrir/fechar portas do proxy."""
    if not PORTS_FILE.exists():
        PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTS_FILE.touch()
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'MULTIFLOW PROXY':^47}|")
        print("------------------------------------------------")
        if PORTS_FILE.stat().st_size == 0:
            print(f"| Portas(s): {'nenhuma':<34}|")
        else:
            with PORTS_FILE.open() as f:
                ports = [line.strip() for line in f if line.strip()]
            active_ports = ' '.join(ports)
            print(f"| Portas(s):{active_ports:<35}|")
        print("------------------------------------------------")
        print("| 1 - Abrir Porta |")
        print("| 2 - Fechar Porta |")
        print("| 0 - Sair |")
        print("------------------------------------------------")
        option = input(" --> Selecione uma opção: ").strip()
        if option == '1':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            status = input("Digite o status de conexão (Enter para padrão): ").strip() or "@MultiFlow"
            add_proxy_port(port, status)
            input("> Porta ativada com sucesso. Pressione Enter para voltar ao menu.")
        elif option == '2':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            del_proxy_port(port)
            input("> Porta desativada com sucesso. Pressione Enter para voltar ao menu.")
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")
def parse_args() -> argparse.Namespace:
    """Lê argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Implementação Python do MultiFlow com menu")
    parser.add_argument("--port", type=int, help="Porta de escuta")
    parser.add_argument("--status", type=str, default="@MultiFlow", help="Texto de status nas respostas HTTP")
    return parser.parse_args()
def main() -> None:
    """Ponto de entrada: proxy (--port) ou menu (root)."""
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port, args.status))
        except KeyboardInterrupt:
            logging.info("Proxy encerrado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()
if __name__ == "__main__":
    main()
