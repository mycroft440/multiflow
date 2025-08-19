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


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, status: str) -> None:
    """Handle a single incoming client connection.

    Sends HTTP status lines to the client, performs a protocol probe on
    the incoming stream and then proxies data bidirectionally between
    the client and the selected backend.  Any exceptions raised
    during processing will cause the client connection to be closed.

    Args:
        client_reader: The reader associated with the client socket.
        client_writer: The writer associated with the client socket.
        status: The status string to embed in the HTTP response.
    """
    # The RustyProxy protocol begins with an HTTP‐like request.  Some
    # clients (e.g. injector apps) send custom headers such as
    # ``X-Real-Host``, ``X-Pass`` and ``X-Split`` to instruct the proxy
    # which upstream host to connect to.  If no ``X-Real-Host`` header is
    # present, the original Rust implementation performs a simple
    # protocol probe and decides between SSH (port 22) and OpenVPN
    # (port 1194).  We therefore read an initial chunk from the client to
    # extract these headers before sending any handshake lines.
    try:
        # Read up to 8 KiB from the client for header parsing.  This
        # should cover the entire HTTP request.  We deliberately avoid
        # reading until EOF so that subsequent protocol data (e.g.
        # OpenVPN or SSH handshake) remains buffered.
        initial_data = await client_reader.read(8192)
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to read initial data: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Decode the header for parsing; ignore undecodable bytes.
    header_text = initial_data.decode("utf-8", errors="ignore")

    # Helper to extract the value of a header.  This replicates the
    # behaviour of the original proxy scripts.
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

    # Determine the upstream host and port.  If X-Real-Host is
    # specified, parse it; otherwise fall back to protocol probing.
    backend_host: str
    backend_port: int
    if host_port_header:
        # Parse the host:port specification.  If no port is provided,
        # default to 22 (SSH) to mirror the behaviour of proxy.py.
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
        # No X-Real-Host header; perform protocol detection on any
        # remaining data in the buffer.  The bytes we already read are
        # purely HTTP headers and should not be forwarded to the
        # backend, so we discard them.  Use probe_backend with a
        # timeout just like the Rust implementation.  If the probe
        # times out, default to SSH.
        try:
            backend_host, backend_port = await asyncio.wait_for(
                probe_backend(client_reader, client_writer), timeout=1.0
            )
        except asyncio.TimeoutError:
            backend_host, backend_port = ("0.0.0.0", 22)

    # If the X-Split header is present, consume another chunk from the
    # client.  Some injector apps send a second request in this case.
    if x_split_header:
        try:
            await client_reader.read(8192)
        except Exception:
            pass

    # Send the handshake responses.  According to the original proxy
    # scripts and the Rust implementation, the proxy must send a 101
    # Switching Protocols line followed by a 200 OK line.  Use CRLF
    # sequences exactly as expected by clients.
    try:
        # Construir e enviar respostas HTTP realistas.  Na primeira
        # resposta (101 Switching Protocols) incluímos um cabeçalho
        # "Server" rotativo e um cabeçalho "Date".  Na segunda
        # resposta (200 OK) adicionamos "Content-Type" e
        # "Connection".  Isto ajuda a ofuscar a natureza do proxy.
        server_variants = [
            "nginx/1.18.0 (Ubuntu)",
            "Apache/2.4.41 (Ubuntu)",
            "Microsoft-IIS/10.0",
        ]
        server_header = f"Server: {random.choice(server_variants)}"
        # Data em formato GMT, conforme cabeçalho HTTP padrão
        now_gmt = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        date_header = f"Date: {now_gmt}"
        part1 = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            f"{server_header}\r\n"
            f"{date_header}\r\n\r\n"
        )
        part2 = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: keep-alive\r\n\r\n"
        )
        client_writer.write(part1.encode("utf-8"))
        client_writer.write(part2.encode("utf-8"))
        await client_writer.drain()
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed during handshake with client: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Establish a connection to the chosen backend.
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to connect to backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Forward data bidirectionally.  When one side closes, the other
    # writer will be closed to signal EOF.  We intentionally do not
    # forward the initial HTTP headers to the backend.
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:  # pylint: disable=broad-except
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
    """Inspect the client's incoming data to select the backend port.

    The original Rust implementation examines the first few bytes of
    the client stream without consuming them.  If the data contains
    ``"SSH"`` or if nothing is available within one second, it uses
    port 22 (SSH); otherwise it uses port 1194 (commonly OpenVPN).

    Args:
        client_reader: The reader for the client connection.
        client_writer: The writer for the client connection.

    Returns:
        A tuple ``(host, port)`` indicating where to forward the traffic.
    """
    # Attempt to peek at up to 8192 bytes of incoming data.  We use
    # the underlying socket's MSG_PEEK flag because asyncio's high
    # level API does not support peeking.  If the socket isn't
    # available or peeking fails, fall back to the default.
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)

    # Fetch the underlying socket from the transport.  This is a bit
    # fragile because it relies on private attributes, but it mirrors
    # the behaviour of tokio::net::TcpStream::peek.
    # Fetch the underlying socket via the public get_extra_info API on the writer.
    sock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
    if sock is None:
        return default_backend
    # Use the same technique as the original Proxy code: yield control
    # once via loop.sock_recv with a zero‑byte read to allow the event
    # loop to notice incoming data, then perform a non‑blocking peek.
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        # This call does not read any data but ensures that the loop
        # registers the socket as ready; it may raise if the socket is
        # closed.  Equivalent to peek_stream's loop.sock_recv(sock, 0).
        await loop.sock_recv(sock, 0)
        data_bytes = sock.recv(8192, socket.MSG_PEEK)
        text = data_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return default_backend
    # Decide on the backend based on the peeked data.
    # Perform a case‑insensitive search for "SSH".  If the peeked data is
    # empty or contains SSH, default to the SSH backend; otherwise use
    # the OpenVPN backend.  Using .upper() avoids missing lowercase "ssh".
    if not text or 'SSH' in text.upper():
        return default_backend
    return alt_backend


async def run_proxy(port: int, status: str) -> None:
    """Start the proxy listener and handle incoming connections."""
    """
    Start the proxy listener and handle incoming connections.

    To ensure that both IPv4 and IPv6 clients can connect, create
    an explicit IPv6 socket and disable the IPV6_V6ONLY flag.  This
    mirrors the behaviour of the original proxy, which binds to
    ``::`` and allows dual‑stack operation.
    """
    # Create an IPv6 socket configured for dual stack
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # Allow both IPv4 and IPv6 (0 disables the v6 only flag)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        # IPV6_V6ONLY may not exist on all platforms; ignore if missing
        pass
    # Allow reusing the address immediately after the program exits
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, status),
        sock=sock
    )
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    # Log a start message without referencing "RustyProxy".  Use
    # "multiflow proxy" as the identifier instead.
    logging.info("Starting multiflow proxy Python port on %s", addr_list)
    async with server:
        await server.serve_forever()


# File used to record active proxy ports, mirroring menu.sh behaviour.
PORTS_FILE = Path("/opt/rustyproxy/ports")


def is_port_in_use(port: int) -> bool:
    """Return True if the given TCP port is bound on the local machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int, status: str) -> None:
    """Create and start a systemd service to run this script as a proxy on a port."""
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    # Determine the path to this script.  When installed via the installer
    # this file should reside at /opt/rustyproxy/proxy.py but we compute
    # it dynamically to support other setups.
    script_path = Path(__file__).resolve()
    command = f"{sys.executable} {script_path} --port {port} --status {status}"
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
    # Ensure ports file exists
    PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PORTS_FILE.open("a") as f:
        f.write(f"{port}\n")
    print(f"Porta {port} aberta com sucesso.")


def del_proxy_port(port: int) -> None:
    """Stop and remove the systemd service for a proxy port."""
    subprocess.run(["systemctl", "disable", f"proxy{port}.service"], check=False)
    subprocess.run(["systemctl", "stop", f"proxy{port}.service"], check=False)
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    if service_file_path.exists():
        service_file_path.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    # Remove from ports file
    if PORTS_FILE.exists():
        lines = [l.strip() for l in PORTS_FILE.read_text().splitlines() if l.strip()]
        lines = [l for l in lines if l != str(port)]
        PORTS_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Porta {port} fechada com sucesso.")


def show_menu() -> None:
    """Interactive menu for managing proxy ports, similar to menu.sh."""
    # Ensure the ports file exists
    if not PORTS_FILE.exists():
        PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTS_FILE.touch()
    while True:
        os.system("clear")
        # Título: substituir referências a RustyProxy por multiflow proxy.
        # O cabeçalho decorativo "@RustyManager" foi removido a pedido do utilizador.
        print("------------------------------------------------")
        print(f"|{'multiflow proxy':^47}|")
        print("------------------------------------------------")
        # Exibir o estado actual do proxy.  Se houver portas
        # activas registadas em PORTS_FILE, indicamos "Ativo" e
        # listamos as portas separadas por vírgula; caso contrário
        # mostramos "Inativo" sem portas.  Isto oferece uma visão
        # dinâmica do estado do serviço.
        if PORTS_FILE.exists() and PORTS_FILE.stat().st_size > 0:
            with PORTS_FILE.open() as f:
                ports = [line.strip() for line in f if line.strip()]
            status_line = f"Status: Ativo - {', '.join(ports)}"
        else:
            status_line = "Status: Inativo"
        # Ajustar o preenchimento para caber dentro da moldura de 47
        # caracteres (45 depois das barras laterais).
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
            status = input("Digite o status de conexão (deixe vazio para o padrão): ").strip() or "@RustyProxy"
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
    """Parse command line arguments.

    If --port is provided the script will run in proxy mode.  If
    omitted, the interactive menu will be shown (root privileges
    required).
    """
    parser = argparse.ArgumentParser(description="multiflow proxy Python implementation with menu")
    parser.add_argument("--port", type=int, help="Port to listen on")
    parser.add_argument("--status", type=str, default="@RustyManager", help="Status string for HTTP responses")
    return parser.parse_args()


def main() -> None:
    """Program entry point.

    If a port is specified on the command line the script runs the
    proxy on that port, otherwise it launches the interactive menu.
    The menu requires root privileges because it manipulates systemd
    services.  Logging is enabled when running as a proxy to provide
    diagnostic information.
    """
    args = parse_args()
    # If a port was passed, run in proxy mode
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port, args.status))
        except KeyboardInterrupt:
            logging.info("Proxy terminated by user")
    else:
        # Menu mode; ensure running as root
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
