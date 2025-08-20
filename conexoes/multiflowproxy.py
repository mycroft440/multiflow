"""
Python reimplementation of the RustyProxy server together with the
interactive menu from ``menu.sh``.  The original Rust program
(``RustyProxyOnly``) implements an asynchronous TCP proxy that
listens on a configurable port and forwards traffic to either an SSH
or OpenVPN backend based on a simple protocol probe.  The Bash
``menu.sh`` script provides a text‑based menu for opening and
closing multiple proxy instances via systemd services.

This single Python script encapsulates both pieces of functionality:

* **Proxy mode**: When invoked with ``--port`` (and optionally
  ``--status``), it runs a proxy on the specified port.  It sends
  HTTP status lines to the client, peeks at the first bytes of the
  connection using the underlying socket's ``MSG_PEEK`` flag to
  choose between port 22 (SSH) and 1194 (OpenVPN), and then
  asynchronously shuttles data between client and server.

* **Menu mode**: When invoked without ``--port`` (and executed as
  root), it presents an interactive menu similar to the original
  ``menu.sh``.  Users can add or remove proxy ports; the script
  writes appropriate systemd unit files to run itself in proxy mode,
  starts/stops the units via ``systemctl`` and records active ports in
  ``/opt/rustyproxy/ports``.

This code leverages Python's :mod:`asyncio` standard library to
provide asynchronous networking.  Because Python lacks a direct
``peek`` on the high‑level streams, the implementation uses the
socket's ``recv`` with ``MSG_PEEK`` via a thread pool to inspect
incoming data without consuming it.  Error handling is done via
exceptions and logging rather than ``Result`` values, and stream
splitting is unnecessary because ``asyncio`` separates readers and
writers for each connection.  Despite these differences, the core
logic—HTTP handshake, protocol detection and bidirectional
forwarding—mirrors the original Rust design.
"""

import argparse
import random
from datetime import datetime, timezone
import asyncio
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Tuple


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    """Handle a single incoming client connection.

    Sends HTTP status lines to the client, performs a protocol probe on
    the incoming stream and then proxies data bidirectionally between
    the client and the selected backend.  Any exceptions raised
    during processing will cause the client connection to be closed.

    Args:
        client_reader: The reader associated with the client socket.
        client_writer: The writer associated with the client socket.
    """
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.warning("Falha ao ler dados iniciais: %s", exc)
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

    # Suporte expandido: X-Online-Host como fallback para X-Real-Host (comum em HTTP Injector)
    host_port_header = find_header(header_text, "X-Real-Host") or find_header(header_text, "X-Online-Host")
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

    # Enviar respostas HTTP variadas, com headers do Cloudflare para imitação
    # Fixado o status como "Connection Established" no 200
    try:
        server_variants = [
            "cloudflare",
            "nginx/1.18.0 (Ubuntu)",
            "Apache/2.4.41 (Ubuntu)",
            "Microsoft-IIS/10.0",
        ]
        server_header = f"Server: {random.choice(server_variants)}"
        now_gmt = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        date_header = f"Date: {now_gmt}"
        cf_ray = f"CF-Ray: {random.randint(1000000000, 9999999999)}-{random.choice(['AMS', 'LHR', 'CDG', 'SFO'])}"
        cf_connecting_ip = f"CF-Connecting-IP: {'.'.join(str(random.randint(1, 255)) for _ in range(4))}"
        cf_cache_status = f"CF-Cache-Status: {random.choice(['HIT', 'MISS', 'DYNAMIC'])}"
        hsts = "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload"
        x_forwarded_for = f"X-Forwarded-For: {'.'.join(str(random.randint(1, 255)) for _ in range(4))}"  # Adicionado para anonimato

        responses = []
        # 100 Continue
        responses.append("HTTP/1.1 100 Continue\r\n\r\n")
        # 101 Switching Protocols com headers Cloudflare
        responses.append(
            "HTTP/1.1 101 Switching Protocols\r\n"
            f"{server_header}\r\n"
            f"{date_header}\r\n"
            f"{cf_ray}\r\n"
            f"{cf_connecting_ip}\r\n"
            f"{hsts}\r\n"
            f"{x_forwarded_for}\r\n\r\n"
        )
        # 200 com status fixo "Connection Established"
        responses.append(
            "HTTP/1.1 200 Connection Established\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: keep-alive\r\n"
            "Cache-Control: no-cache\r\n"
            f"{cf_cache_status}\r\n\r\n"
        )
        # Adicionados: 302 Redirect, 429 Too Many Requests, 502 Bad Gateway, 503
        responses.append(f"HTTP/1.1 302 Found\r\nLocation: https://example.com\r\n\r\n")
        responses.append("HTTP/1.1 429 Too Many Requests\r\n\r\n")
        responses.append("HTTP/1.1 502 Bad Gateway\r\n\r\n")
        responses.append("HTTP/1.1 503 Service Unavailable\r\n\r\n")

        for resp in responses:
            client_writer.write(resp.encode("utf-8"))
        await client_writer.drain()
    except Exception as exc:
        logging.warning("Falha no handshake: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Conexão ao backend, sem TLS
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
    except Exception as exc:
        logging.warning("Falha ao conectar ao backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Forward bidirecional
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Erro no forwarding %s: %s", direction, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    client_to_server = asyncio.create_task(forward(client_reader, server_writer, "client->server"))
    server_to_client = asyncio.create_task(forward(server_reader, client_writer, "server->client"))
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)


async def probe_backend(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> Tuple[str, int]:
    """Inspect the client's incoming data to select the backend port."""
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)

    sock: socket.socket = client_writer.get_extra_info("socket")
    if sock is None:
        return default_backend
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        await loop.sock_recv(sock, 0)
        data_bytes = sock.recv(8192, socket.MSG_PEEK)
        text = data_bytes.decode('utf-8', errors='ignore').upper()
    except Exception as exc:
        logging.warning("Falha no peek durante probe: %s", exc)
        return default_backend

    # Detecção simples: SSH ou default para OpenVPN
    if not text or 'SSH' in text:
        return default_backend
    return alt_backend


async def run_proxy(port: int) -> None:
    """Start the proxy listener and handle incoming connections."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)

    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w),
        sock=sock
    )
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Iniciando multiflow proxy Python na porta %s", addr_list)
    async with server:
        await server.serve_forever()


PORTS_FILE = Path("/opt/rustyproxy/ports")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int) -> None:
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    command = f"{sys.executable} {script_path} --port {port}"
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    service_content = f"""[Unit]
Description=multiflow proxy {port}
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
    if not PORTS_FILE.exists():
        PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTS_FILE.touch()
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'multiflow proxy':^47}|")
        print("------------------------------------------------")
        if PORTS_FILE.exists() and PORTS_FILE.stat().st_size > 0:
            with PORTS_FILE.open() as f:
                ports = [line.strip() for line in f if line.strip()]
            status_line = f"Status: Ativo - {', '.join(ports)}"
        else:
            status_line = "Status: Inativo"
        print(f"| {status_line:<45}|")
        print("------------------------------------------------")
        print("| 1 - Abrir Porta                                   |")
        print("| 2 - Fechar Porta                                  |")
        print("| 0 - Sair                                          |")
        print("------------------------------------------------")
        option = input(" --> Selecione uma opção: ").strip()
        if option == '1':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            add_proxy_port(port)
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
    parser = argparse.ArgumentParser(description="multiflow proxy Python implementation with menu")
    parser.add_argument("--port", type=int, help="Port to listen on")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port))
        except KeyboardInterrupt:
            logging.info("Proxy terminado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
