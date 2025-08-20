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


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Handle a single incoming client connection.

    Sends HTTP status lines to the client, performs a protocol probe on
    the incoming stream and then proxies data bidirectionally between
    the client and the selected backend.  Any exceptions raised
    during processing will cause the client connection to be closed.

    Args:
        client_reader: The reader associated with the client socket.
        client_writer: The writer associated with the client socket.
        status: The status string to embed in the HTTP response.
        cloudflare: Flag to enable Cloudflare-specific handling.
        fake_ssl: Flag to enable fake SSL masking.
    """
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Failed to read initial data: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    header_text = initial_data.decode("utf-8", errors="ignore")

    def find_header(text: str, header: str) -> str:
        idx = text.lower().find(header.lower() + ": ")
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

    # Cloudflare-specific headers extraction
    cf_connecting_ip = find_header(header_text, "CF-Connecting-IP") if cloudflare else ""
    cf_ray = find_header(header_text, "CF-Ray") if cloudflare else ""
    cdn_loop = find_header(header_text, "CDN-Loop") if cloudflare else ""
    cf_ipcountry = find_header(header_text, "CF-IPCountry") if cloudflare else ""

    if cloudflare:
        logging.debug("Cloudflare headers: IP=%s, Ray=%s, Country=%s, CDN-Loop=%s", cf_connecting_ip, cf_ray, cf_ipcountry, cdn_loop)
        if cdn_loop.count("cloudflare") > 1:
            logging.warning("Potential loop detected via CDN-Loop: %s", cdn_loop)
            client_writer.close()
            await client_writer.wait_closed()
            return

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

    # Enhanced handshake with fake SSL if enabled
    try:
        server_variants = [
            "nginx/1.18.0 (Ubuntu)",
            "Apache/2.4.41 (Ubuntu)",
            "Microsoft-IIS/10.0",
            "cloudflare",
        ]
        server_header = f"Server: {random.choice(server_variants)}"
        now_gmt = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        date_header = f"Date: {now_gmt}"
        cache_status = "CF-Cache-Status: HIT" if cloudflare else "Cache-Control: no-cache"

        # Fake SSL headers
        fake_ssl_headers = ""
        if fake_ssl:
            fake_ssl_headers = (
                "Strict-Transport-Security: max-age=31536000; includeSubDomains\r\n"
                "Upgrade: tls/1.3\r\n"
                "Alt-Svc: h3=\":443\"; ma=86400\r\n"
            )

        responses = []
        responses.append("HTTP/1.1 100 Continue\r\n\r\n")
        responses.append(
            "HTTP/1.1 101 Switching Protocols\r\n"
            f"{server_header}\r\n"
            f"{date_header}\r\n"
            f"{cache_status}\r\n"
            f"{fake_ssl_headers}\r\n"
        )
        responses.append("HTTP/1.1 204 No Content\r\n\r\n")
        responses.append(
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: keep-alive\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            f"{fake_ssl_headers}\r\n"
        )
        responses.append("HTTP/1.1 301 Moved Permanently\r\nLocation: /\r\n\r\n")
        responses.append("HTTP/1.1 403 Forbidden\r\n\r\n")
        responses.append("HTTP/1.1 404 Not Found\r\n\r\n")
        responses.append("HTTP/1.1 503 Service Unavailable\r\n\r\n")

        for resp in responses:
            client_writer.write(resp.encode("utf-8"))
        await client_writer.drain()

        # Send fake TLS bytes if fake_ssl enabled (masks as TLS record)
        if fake_ssl:
            fake_tls_bytes = b'\x16\x03\x03\x00\x2a' + os.urandom(42)  # Fake ServerHello + random data
            client_writer.write(fake_tls_bytes)
            await client_writer.drain()
            logging.debug("Sent fake TLS bytes for masking")

    except Exception as exc:
        logging.error("Failed during handshake with client: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        if cloudflare and cf_connecting_ip:
            logging.info("Forwarding from real client IP: %s to backend %s:%d", cf_connecting_ip, backend_host, backend_port)
    except Exception as exc:
        logging.error("Failed to connect to backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Forwarding %s encountered error: %s", direction, exc)
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
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)

    sock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
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


async def run_proxy(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, status, cloudflare, fake_ssl),
        sock=sock
    )
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Starting multiflow proxy Python port on %s (Cloudflare: %s, Fake SSL: %s)", addr_list, cloudflare, fake_ssl)
    async with server:
        await server.serve_forever()


PORTS_FILE = Path("/opt/rustyproxy/ports")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    cf_flag = "--cloudflare" if cloudflare else ""
    ssl_flag = "--fake-ssl" if fake_ssl else ""
    command = f"{sys.executable} {script_path} --port {port} --status {status} {cf_flag} {ssl_flag}"
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


def toggle_fake_ssl(port: int, enable: bool) -> None:
    # Para togglear, paramos o service, recriamos com o flag atualizado.
    # Mas para simplicidade, assumimos que status e cloudflare permanecem os mesmos (não salvamos, então recrie manual).
    # Melhor: fechar e reabrir com pergunta.
    print("Para togglear fake SSL, feche e reabra a porta com a opção desejada.")
    # Implementação simples: del e add com novo flag, mas precisa de inputs.
    # Por agora, sugiro manual.


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
        print("| 3 - Fake ssl                                      |")
        print("| 0 - Sair                                          |")
        print("------------------------------------------------")
        option = input(" --> Selecione uma opção: ").strip()
        if option == '1':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            status = input("Digite o status de conexão (deixe vazio para o padrão): ").strip() or "@RustyProxy"
            cf_input = input("Ativar modo Cloudflare? (s/n, default n): ").strip().lower()
            cloudflare = cf_input == 's'
            ssl_input = input("Ativar fake SSL? (s/n, default n): ").strip().lower()
            fake_ssl = ssl_input == 's'
            add_proxy_port(port, status, cloudflare, fake_ssl)
            input("> Porta ativada com sucesso. Pressione Enter para voltar ao menu.")
        elif option == '2':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            del_proxy_port(port)
            input("> Porta desativada com sucesso. Pressione Enter para voltar ao menu.")
        elif option == '3':
            print("Opção Fake SSL: Para ativar/desativar em uma porta, feche (opção 2) e reabra (opção 1) com a escolha.")
            input("Pressione Enter para voltar ao menu.")
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="multiflow proxy Python implementation with menu")
    parser.add_argument("--port", type=int, help="Port to listen on")
    parser.add_argument("--status", type=str, default="@RustyManager", help="Status string for HTTP responses")
    parser.add_argument("--cloudflare", action="store_true", help="Enable Cloudflare-specific handling")
    parser.add_argument("--fake-ssl", action="store_true", help="Enable fake SSL masking for bypass")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port, args.status, args.cloudflare, args.fake_ssl))
        except KeyboardInterrupt:
            logging.info("Proxy terminated by user")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
