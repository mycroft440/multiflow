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
import re
from pathlib import Path
from typing import Tuple


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter,
                        status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Handle an incoming client connection.

    This coroutine reads an initial HTTP request from the client, extracts
    optional headers to determine the appropriate backend host/port and whether
    to drop the connection, sends a series of HTTP responses to attempt to
    confuse protocol detection, optionally injects fake TLS bytes, connects
    to the chosen backend service, then relays traffic bidirectionally.

    Args:
        client_reader: asyncio StreamReader for the client.
        client_writer: asyncio StreamWriter for the client.
        status: Status string included in some responses (currently unused).
        cloudflare: If True, expect and respect Cloudflare headers.
        fake_ssl: If True, inject a fake TLS handshake to mask traffic.
    """

    # Read up to 8192 bytes from the client.  These bytes contain
    # the HTTP request headers (if any) as well as any protocol
    # preamble (SSH or VPN handshake).  Failure to read results in
    # immediate closure.
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Failed to read initial data: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Decode the headers for parsing.  Invalid UTF-8 sequences are ignored.
    header_text = initial_data.decode("utf-8", errors="ignore")

    def find_header(text: str, header: str) -> str:
        """Extract the value of a HTTP header from a header block.

        Searches case-insensitively for `header:` followed by a space, then
        returns the substring up to the following CRLF.  If the header is
        absent, returns an empty string.
        """
        idx = text.lower().find(header.lower() + ": ")
        if idx == -1:
            return ""
        # Move past the colon and space to the start of the value.
        value_start = idx + len(header) + 2
        end = text.find("\r\n", value_start)
        if end == -1:
            return ""
        return text[value_start:end]

    # Extract custom headers used by this proxy.
    host_port_header = find_header(header_text, "X-Real-Host")
    x_split_header = find_header(header_text, "X-Split")

    # Optional Cloudflare headers.  Only extracted if `cloudflare` flag set.
    cf_connecting_ip = find_header(header_text, "CF-Connecting-IP") if cloudflare else ""
    cf_ray = find_header(header_text, "CF-Ray") if cloudflare else ""
    cdn_loop = find_header(header_text, "CDN-Loop") if cloudflare else ""
    cf_ipcountry = find_header(header_text, "CF-IPCountry") if cloudflare else ""

    # If Cloudflare mode is enabled, check for potential loops.
    if cloudflare:
        logging.debug("Cloudflare headers: IP=%s, Ray=%s, Country=%s, CDN-Loop=%s",
                      cf_connecting_ip, cf_ray, cf_ipcountry, cdn_loop)
        # When a request loops through Cloudflare more than once, abort.
        if cdn_loop.lower().count("cloudflare") > 1:
            logging.warning("Potential Cloudflare loop detected via CDN-Loop: %s", cdn_loop)
            client_writer.close()
            await client_writer.wait_closed()
            return

    # Determine backend host/port.  Precedence:
    # 1. X-Real-Host header, optionally with a port suffix (host:port).
    # 2. If no header is provided, perform a protocol probe on the
    #    remaining unread bytes.  This mirrors the behaviour of the
    #    original proxy, which uses MSG_PEEK to decide between SSH and
    #    OpenVPN.  On timeout or failure, default to the SSH port.
    if host_port_header:
        # Split host and port if provided (only splits on last colon to allow IPv6).
        if ":" in host_port_header:
            hp_host, hp_port_str = host_port_header.rsplit(":", 1)
            try:
                backend_port = int(hp_port_str)
            except ValueError:
                backend_port = 22  # default to SSH on invalid port
            backend_host = hp_host
        else:
            backend_host = host_port_header
            backend_port = 22
    else:
        try:
            # Peek at the remaining bytes after the initial HTTP header to
            # determine the protocol.  A timeout of one second matches the
            # original behaviour; if the probe times out, assume SSH.
            backend_host, backend_port = await asyncio.wait_for(
                probe_backend(client_reader, client_writer), timeout=1.0
            )
        except asyncio.TimeoutError:
            backend_host, backend_port = ("0.0.0.0", 22)

    # If the X-Split header is present, consume and discard an additional chunk
    # from the client.  Some injector applications send a second request in
    # this case.  We intentionally drop these bytes and do not forward them
    # to the backend, as they are part of the proxy negotiation rather than
    # the target protocol.
    if x_split_header:
        try:
            await client_reader.read(8192)
        except Exception:
            pass

    # Compose and send a series of HTTP responses to confuse protocol
    # detection on the client side.  This mirrors the RustyProxy behaviour
    # where multiple status lines are returned.
    try:
        # Pick a plausible server header at random.
        server_variants = [
            "nginx/1.18.0 (Ubuntu)",
            "Apache/2.4.41 (Ubuntu)",
            "Microsoft-IIS/10.0",
            "cloudflare",
        ]
        server_header = f"Server: {random.choice(server_variants)}"
        # Generate a Date header in GMT format.
        now_gmt = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        date_header = f"Date: {now_gmt}"
        cache_status = "CF-Cache-Status: HIT" if cloudflare else "Cache-Control: no-cache"

        # The proxy previously allowed a custom status string via --status
        # and included it as a "Status:" header.  To produce a more
        # professional and consistent response, we no longer emit a
        # custom status header.  Instead, standard HTTP status lines
        # such as "200 Connection Established" are used.

        # Prepare optional fake SSL headers.  These are included when
        # --fake-ssl is set, to attempt to trick DPI.
        fake_ssl_headers = ""
        if fake_ssl:
            fake_ssl_headers = (
                "Strict-Transport-Security: max-age=31536000; includeSubDomains\r\n"
                "Upgrade: tls/1.3\r\n"
                "Alt-Svc: h3=\":443\"; ma=86400\r\n"
            )

        # Additional headers for advanced evasion/spoofing.
        trusted_domains = ["www.google.com", "www.example.com", "www.cloudflare.com"]
        forwarded_header = f"Forwarded: for={random.choice(trusted_domains)};host={random.choice(trusted_domains)};proto=https\r\n"
        x_forwarded_host_header = f"X-Forwarded-Host: {random.choice(trusted_domains)}\r\n"
        # Fake internal IP to obscure the real client.  Randomly generate last two octets.
        x_real_ip_header = (
            f"X-Real-IP: 192.168.{random.randint(0, 255)}.{random.randint(0, 255)}\r\n"
        )
        # Standard desktop User-Agent to look like a browser connecting.
        user_agent_header = (
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36\r\n"
        )

        # Build a list of response payloads.  Each entry is a complete
        # response to be written to the client.  Responses with body
        # terminate with an extra CRLF.
        responses = []
        responses.append("HTTP/1.1 100 Continue\r\n\r\n")
        responses.append(
            "HTTP/1.1 101 Switching Protocols\r\n"
            f"{server_header}\r\n"
            f"{date_header}\r\n"
            f"{cache_status}\r\n"
            f"{forwarded_header}"
            f"{x_forwarded_host_header}"
            f"{x_real_ip_header}"
            f"{fake_ssl_headers}\r\n"
        )
        responses.append("HTTP/1.1 204 No Content\r\n\r\n")
        responses.append(
            "HTTP/1.1 200 Connection Established\r\n"
            "Content-Type: text/plain\r\n"
            "Connection: keep-alive\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            f"{user_agent_header}"
            f"{forwarded_header}"
            f"{x_forwarded_host_header}"
            f"{x_real_ip_header}"
            f"{fake_ssl_headers}\r\n"
        )
        responses.append("HTTP/1.1 301 Moved Permanently\r\nLocation: /\r\n\r\n")
        responses.append("HTTP/1.1 403 Forbidden\r\n\r\n")
        responses.append("HTTP/1.1 404 Not Found\r\n\r\n")
        responses.append("HTTP/1.1 503 Service Unavailable\r\n\r\n")

        # Send each response line in sequence.
        for resp in responses:
            client_writer.write(resp.encode("utf-8"))
        await client_writer.drain()

        # If fake SSL is enabled, send a sequence of bytes that looks like
        # the start of a TLS handshake.  This can help defeat naive DPI.
        if fake_ssl:
            fake_tls_bytes = b'\x16\x03\x03\x00\x2a' + os.urandom(42)
            client_writer.write(fake_tls_bytes)
            await client_writer.drain()
            logging.debug("Sent fake TLS bytes for masking")

        logging.debug(
            "Evasion headers sent: Forwarded, X-Forwarded-Host, X-Real-IP, User-Agent"
        )

    except Exception as exc:
        logging.error("Failed during handshake with client: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Connect to the backend host.  If Cloudflare is enabled and
    # CF-Connecting-IP is present, log the real origin IP for auditing.
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        if cloudflare and cf_connecting_ip:
            logging.info("Forwarding from real client IP: %s to backend %s:%d", cf_connecting_ip, backend_host, backend_port)
    except Exception as exc:
        logging.error("Failed to connect to backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Once connected to the backend, immediately begin relaying data.  We
    # deliberately do not forward the initial HTTP headers or any
    # negotiation data consumed above, as those bytes are not part of the
    # target protocol.  This mirrors the original behaviour and prevents
    # injecting proxy headers into the SSH/OpenVPN handshake.

    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        """Continuously relay data from reader to writer until EOF or error."""
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

    # Kick off bidirectional data forwarding.  Use return_exceptions so both
    # tasks are awaited even if one raises.
    client_to_server = asyncio.create_task(forward(client_reader, server_writer, "client->server"))
    server_to_client = asyncio.create_task(forward(server_reader, client_writer, "server->client"))
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)


async def probe_backend(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> Tuple[str, int]:
    """Peek at the client socket to decide whether to use SSH (22) or VPN (1194).

    This helper retrieves the raw socket from the StreamWriter, does a
    non-blocking MSG_PEEK recv to inspect the first few bytes without
    consuming them, and looks for an SSH banner.  Any non-empty bytes
    not containing 'SSH' are treated as OpenVPN traffic.

    Args:
        client_reader: The client's StreamReader (unused but kept for future use).
        client_writer: The client's StreamWriter from which to get the socket.

    Returns:
        A tuple of (backend_host, backend_port).  The host defaults to
        ``0.0.0.0`` because in the original Rust code the actual backend
        addresses are defined in systemd unit files.
    """
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)

    # Extract the underlying socket from the writer.
    sock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
    if sock is None:
        return default_backend
    # Ensure we don't block on the socket directly.
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        # Perform a 0-byte read to integrate with the event loop.  This
        # ensures the socket's readiness is registered before calling recv.
        await loop.sock_recv(sock, 0)
        # Peek at up to 8192 bytes.  MSG_PEEK prevents consumption.
        data_bytes = sock.recv(8192, socket.MSG_PEEK)
        # Decode for inspection.
        text = data_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return default_backend

    # If nothing was read or we see 'SSH', treat as default SSH.
    if not text or 'SSH' in text.upper():
        return default_backend
    # Otherwise fallback to alternate VPN port.
    return alt_backend


async def run_proxy(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Start a proxy server listening on the given port.

    This creates an IPv6 listening socket (with dual-stack when available),
    then hands accepted connections to `handle_client` for processing.  The
    loop runs forever until cancelled or interrupted.

    Args:
        port: The port number to listen on.  If already bound, the server will
            raise an exception at startup.
        status: A status string passed to the client (currently unused).
        cloudflare: Whether to handle Cloudflare-specific headers and loop
            detection.
        fake_ssl: Whether to inject a fake TLS handshake to conceal traffic.
    """
    # Create a dual-stack socket if possible (AF_INET6) and bind to all
    # addresses.  Setting IPV6_V6ONLY to 0 allows both IPv4 and IPv6.
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except (AttributeError, OSError):
        # IPV6_V6ONLY may not be available on all systems; ignore if so.
        pass
    # Allow immediate reuse of the port when restarting.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, status, cloudflare, fake_ssl),
        sock=sock
    )
    # Log all bound addresses (IPv6/IPv4).  Useful for debugging.
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info(
        "Starting multiflow proxy Python port on %s (Cloudflare: %s, Fake SSL: %s)",
        addr_list, cloudflare, fake_ssl,
    )
    async with server:
        await server.serve_forever()


PORTS_FILE = Path("/opt/rustyproxy/ports")


def is_port_in_use(port: int) -> bool:
    """Check whether a given port is already listening on localhost.

    Args:
        port: The TCP port number to check.

    Returns:
        True if connect_ex returns success (0), indicating a listener is present.
        False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Create and start a systemd service for a proxy on the given port.

    Writes a unit file to /etc/systemd/system/proxy{port}.service that runs
    this script in proxy mode with the provided flags.  The service is
    enabled and started via systemctl.  The port is recorded in
    ``/opt/rustyproxy/ports`` for display in the menu.  If the port is
    already in use, no service is created.

    Args:
        port: Port number to open.
        status: Status string for the proxy (unused in code but passed).
        cloudflare: Whether to enable Cloudflare handling in the service.
        fake_ssl: Whether to enable fake SSL masking in the service.
    """
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
    # Reload systemd units, enable and start the new service.  These calls
    # are best-effort (check=False) to avoid raising on failure.
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", f"proxy{port}.service"], check=False)
    subprocess.run(["systemctl", "start", f"proxy{port}.service"], check=False)
    PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PORTS_FILE.open("a") as f:
        f.write(f"{port}\n")
    print(f"Porta {port} aberta com sucesso.")


def del_proxy_port(port: int) -> None:
    """Stop and remove the systemd service for a proxy on the given port."""
    subprocess.run(["systemctl", "disable", f"proxy{port}.service"], check=False)
    subprocess.run(["systemctl", "stop", f"proxy{port}.service"], check=False)
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    if service_file_path.exists():
        service_file_path.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    # Remove the port entry from ports file.
    if PORTS_FILE.exists():
        lines = [l.strip() for l in PORTS_FILE.read_text().splitlines() if l.strip()]
        lines = [l for l in lines if l != str(port)]
        PORTS_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Porta {port} fechada com sucesso.")


def toggle_feature(port: int, feature_flag: str, enable: bool) -> None:
    """Enable or disable a command-line flag for a running proxy service.

    Modifies the ExecStart line in the systemd unit file for the given port
    to include or exclude the specified feature_flag.  Then reloads and
    restarts the service to apply the change.

    Args:
        port: Service port whose unit file to edit.
        feature_flag: The command-line flag (e.g. '--fake-ssl' or '--cloudflare').
        enable: If True, ensure the flag is present; otherwise remove it.
    """
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    if not service_file_path.exists():
        print(f"Serviço para porta {port} não existe.")
        return
    service_content = service_file_path.read_text()
    exec_match = re.search(r'ExecStart=(.*)', service_content)
    if not exec_match:
        print("Erro ao extrair ExecStart do serviço.")
        return
    command = exec_match.group(1).strip()
    # Append or remove the flag as requested.
    if enable:
        if feature_flag not in command:
            command += f" {feature_flag}"
    else:
        command = command.replace(f" {feature_flag}", "")
    new_content = re.sub(r'ExecStart=.*', f'ExecStart={command}', service_content)
    service_file_path.write_text(new_content)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "restart", f"proxy{port}.service"], check=False)
    print(f"Feature {feature_flag} {'ativada' if enable else 'desativada'} para porta {port} com sucesso.")


def show_menu() -> None:
    """Display and handle the interactive text menu.

    Presents options to open/close ports and toggle features, similar to
    menu.sh.  Only works when running as root.  Reads/writes to
    /opt/rustyproxy/ports to track active services.
    """
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
        print("| 4 - Ativar Cloudflare                             |")
        print("| 0 - Sair                                          |")
        print("------------------------------------------------")
        option = input(" --> Selecione uma opção: ").strip()
        if option == '1':
            # Solicita apenas a porta a ser aberta.  O status de conexão é
            # fixo e não mais solicitado ao usuário para simplificar o fluxo.
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            # Use um valor de status fixo e verídico para todas as conexões criadas pelo menu.
            # Em vez de um identificador simbólico, indicamos explicitamente que a conexão foi estabelecida.
            fixed_status = "connection established"
            add_proxy_port(port, fixed_status, cloudflare=False, fake_ssl=False)
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
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            enable_input = input("Ativar fake SSL? (s/n): ").strip().lower()
            enable = enable_input == 's'
            toggle_feature(port, "--fake-ssl", enable)
            input("> Operação concluída. Pressione Enter para voltar ao menu.")
        elif option == '4':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            enable_input = input("Ativar Cloudflare? (s/n): ").strip().lower()
            enable = enable_input == 's'
            toggle_feature(port, "--cloudflare", enable)
            input("> Operação concluída. Pressione Enter para voltar ao menu.")
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for proxy and menu modes."""
    parser = argparse.ArgumentParser(description="multiflow proxy Python implementation with menu")
    parser.add_argument("--port", type=int, help="Port to listen on")
    parser.add_argument(
        "--status", type=str, default="@RustyManager", help="Status string for HTTP responses"
    )
    parser.add_argument(
        "--cloudflare", action="store_true", help="Enable Cloudflare-specific handling"
    )
    parser.add_argument(
        "--fake-ssl", action="store_true", help="Enable fake SSL masking for bypass"
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: dispatch to proxy or menu mode based on arguments."""
    args = parse_args()
    if args.port is not None:
        # Run in proxy mode.  Configure logging and start the asyncio loop.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port, args.status, args.cloudflare, args.fake_ssl))
        except KeyboardInterrupt:
            logging.info("Proxy terminated by user")
    else:
        # Run in menu mode.  Ensure script has root privileges.
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
