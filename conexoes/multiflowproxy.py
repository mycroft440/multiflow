#!/usr/bin/env python3
"""
MultiFlow proxy server with flexible handshake ordering and extended header support.

This script implements a tunelling proxy similar to the MultiFlow project. It can
listen on a specified port and forward traffic to a backend (typically SSH
on port 22 or OpenVPN on port 1194) after performing an HTTP‑style handshake.
The handshake sends HTTP status codes (101 and optionally 200) to satisfy
clients expecting a proxy or WebSocket upgrade. The order of the handshake is
dynamic per connection: clients can indicate preference via the custom
``HandShake‑First`` header (``1`` to receive handshake after sending data,
``0`` to receive handshake before sending data). If the header is absent,
the proxy uses automatic detection: if the client sends data immediately,
the handshake is sent afterwards; otherwise, it is sent first.

This version adds support for additional headers and markers to better parse
complex payloads used by some MultiFlow scripts. Specifically:

* ``Host`` and ``X‑Online‑Host`` headers are now recognised as alternatives
  to ``X‑Real‑Host`` when determining the backend address. If any of
  these headers is present, the first non‑empty one is used. Hosts may be
  specified with an optional ``:port`` suffix and may include full URLs
  (``http://...``), in which case only the hostname is extracted. When
  multiple hosts are separated by spaces or semicolons, the first is taken.
* Presence of the ``X‑Split`` header still triggers an extra read of 8192
  bytes from the client to consume additional payload segments. In addition,
  the proxy now scans the initial request for special markers ``[split]``
  or ``[delay_split]``. If either marker is found, another 8192 bytes are
  read from the client to consume delayed segments before connecting to the
  backend.

The script also includes a menu for managing multiple proxy instances via
``systemd`` services. Run this script as root without arguments to access
the menu; run with ``--port <PORT>`` to start a proxy directly on a port.
"""

import argparse
import asyncio
import logging
import os
import socket
import subprocess
import sys
import contextlib
from pathlib import Path
from typing import Tuple, Set

# ---------------------------------------------------------------------------
# HTTP status management
# ---------------------------------------------------------------------------

# Map of status codes to reason phrases. 101 and 200 are used in
# the handshake, but other codes can be toggled in the menu for completeness.
HTTP_STATUS = {
    100: "Continue",
    101: "Switching Protocols",
    200: "Connection Established",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found",
    403: "Forbidden",
    404: "Not Found",
    503: "Service Unavailable",
}

# File that records which status codes are enabled. The proxy always sends 101;
# if 200 is enabled it will send that after 101. All other enabled codes are
# ignored by the handshake routine.
STATUS_FILE = Path("/opt/multiflow/http_status")
# Default enabled statuses include 200 to satisfy clients that expect both
# 101 and 200 responses. Status 101 is always treated as enabled regardless
# of this set.
DEFAULT_ENABLED: Set[int] = {101, 200}


def load_enabled_statuses() -> Set[int]:
    """Load the set of active HTTP status codes from ``STATUS_FILE``.

    If the file does not exist or cannot be read, the default set is returned.
    Only codes present in ``HTTP_STATUS`` are retained.
    """
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return set(DEFAULT_ENABLED)
    if not STATUS_FILE.exists() or STATUS_FILE.stat().st_size == 0:
        enabled = set(DEFAULT_ENABLED)
        with contextlib.suppress(Exception):
            save_enabled_statuses(enabled)
        return enabled
    enabled: Set[int] = set()
    for line in STATUS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            code = int(line)
        except ValueError:
            continue
        if code in HTTP_STATUS:
            enabled.add(code)
    if not enabled:
        enabled = set(DEFAULT_ENABLED)
        save_enabled_statuses(enabled)
    return enabled


def save_enabled_statuses(enabled: Set[int]) -> None:
    """Save the HTTP status codes into ``STATUS_FILE``."""
    with contextlib.suppress(Exception):
        STATUS_FILE.write_text("\n".join(str(c) for c in sorted(enabled)) + "\n")


# ---------------------------------------------------------------------------
# TCP keepalive tuning
# ---------------------------------------------------------------------------


def apply_tcp_keepalive(
    sock: socket.socket,
    *,
    idle: int = 10,
    interval: int = 5,
    count: int = 3,
    nodelay: bool = True,
) -> None:
    """Configure aggressive TCP keepalive on a socket.

    Enable SO_KEEPALIVE and, if available, set idle time, interval, and count.
    Also set TCP_NODELAY to disable Nagle's algorithm for more immediate sends.
    """
    if not sock:
        return
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "TCP_KEEPIDLE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
    if hasattr(socket, "TCP_KEEPINTVL"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
    if hasattr(socket, "TCP_KEEPCNT"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
    if hasattr(socket, "TCP_KEEPALIVE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, idle)
    if nodelay and hasattr(socket, "TCP_NODELAY"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


async def probe_backend_from_data(initial_data: bytes) -> Tuple[str, int]:
    """Decide backend (host, port) based on the first bytes received.

    If the initial data is empty or contains "SSH", default to port 22.
    Otherwise default to port 1194. The host defaults to 127.0.0.1.
    """
    default_backend = ("127.0.0.1", 22)
    alt_backend = ("127.0.0.1", 1194)
    try:
        text = initial_data.decode("utf-8", errors="ignore")
    except Exception:
        return default_backend
    if not text or "SSH" in text.upper():
        return default_backend
    return alt_backend


# ---------------------------------------------------------------------------
# Helpers for headers and handshake
# ---------------------------------------------------------------------------


def find_header(text: str, header: str) -> str:
    """Find an HTTP header (case-insensitive) and return its value.

    The header name should not include the trailing colon. If multiple headers
    of the same name exist, the first one encountered is returned.
    """
    for line in text.split("\r\n"):
        if line.lower().startswith(header.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""


async def send_handshake(writer: asyncio.StreamWriter) -> None:
    """Send HTTP status codes 101 and (optionally) 200 to the client."""
    enabled = load_enabled_statuses()
    codes = [101] + ([200] if 200 in enabled else [])
    for code in codes:
        reason = HTTP_STATUS.get(code, "OK")
        writer.write(f"HTTP/1.1 {code} {reason}\r\n\r\n".encode())
    await writer.drain()


# ---------------------------------------------------------------------------
# Client connection handling
# ---------------------------------------------------------------------------

# Time in seconds to wait for client data before assuming handshake-first mode
HANDSHAKE_TIMEOUT = 0.5


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    """Handle an incoming client connection.

    Uses dynamic handshake ordering based on the ``HandShake-First`` header
    and automatic detection of clients that start sending data immediately.
    Supports multiple header names (``X-Real-Host``, ``Host``,
    ``X-Online-Host``) for specifying the backend, and honours special
    markers ``[split]`` and ``[delay_split]`` to read additional data
    segments.
    """
    # Apply keepalive options on client socket
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # Attempt to read initial data quickly to detect client behaviour
    initial_data = b""
    data_received = False
    try:
        initial_data = await asyncio.wait_for(
            client_reader.read(8192), timeout=HANDSHAKE_TIMEOUT
        )
        data_received = bool(initial_data)
    except asyncio.TimeoutError:
        data_received = False

    # Decide whether to send handshake before or after reading payload
    handshake_after = False  # False -> send handshake before reading payload
    header_text = ""
    if data_received:
        header_text = initial_data.decode("utf-8", errors="ignore")
        hs_header = find_header(header_text, "HandShake-First")
        if hs_header:
            # If header present, obey its value ("1" or "0")
            handshake_after = (hs_header == "1")
        else:
            # No explicit header, but client sent data; assume handshake after
            handshake_after = True
    else:
        # Client didn't send data within timeout; send handshake immediately
        handshake_after = False

    # If handshake should be sent before reading payload
    if not handshake_after:
        await send_handshake(client_writer)
        # If we haven't read any data yet, read now to process headers
        if not data_received:
            try:
                initial_data = await client_reader.read(8192)
                header_text = initial_data.decode("utf-8", errors="ignore")
            except Exception as exc:
                logging.error("Falha ao ler dados iniciais: %s", exc)
                client_writer.close()
                await client_writer.wait_closed()
                return
    else:
        # Handshake will be sent after reading payload; header_text already set
        pass

    # Parse headers for backend selection. Recognise multiple header names.
    x_real_host = find_header(header_text, "X-Real-Host")
    host_header = find_header(header_text, "Host")
    xonline_header = find_header(header_text, "X-Online-Host")

    # Determine which header to use: X-Real-Host > Host > X-Online-Host
    header_candidate = ""
    for candidate in (x_real_host, host_header, xonline_header):
        if candidate:
            header_candidate = candidate
            break

    backend_host: str
    backend_port: int
    if header_candidate:
        # Some payloads include full URLs or multiple hosts separated by spaces or semicolons.
        # Take the first token and strip schema and path.
        # e.g. "http://example.com:8080/index" -> "example.com:8080"
        #       "example.com:22 some.other" -> "example.com:22"
        token = header_candidate.split(";", 1)[0].split()[0]
        # Remove URL scheme if present
        if token.lower().startswith("http://"):
            token = token[7:]
        elif token.lower().startswith("https://"):
            token = token[8:]
        # Remove path after '/' if present
        if "/" in token:
            token = token.split("/", 1)[0]
        # Now split into host and port if colon exists
        if ":" in token:
            hp_host, hp_port_str = token.rsplit(":", 1)
            try:
                backend_port = int(hp_port_str)
            except ValueError:
                backend_port = 22
            backend_host = hp_host
        else:
            backend_host = token
            backend_port = 22
    else:
        # Fallback to dynamic probe based on initial data
        try:
            backend_host, backend_port = await probe_backend_from_data(initial_data)
        except Exception:
            backend_host, backend_port = ("127.0.0.1", 22)

    # Check for X-Split header or special [split]/[delay_split] markers
    x_split_header = find_header(header_text, "X-Split")
    # Determine if markers appear in header text
    marker_found = ("[split]" in header_text) or ("[delay_split]" in header_text)
    if x_split_header or marker_found:
        # Consume another chunk of data to align streams with client expectations
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # If handshake was deferred, send it now
    if handshake_after:
        try:
            await send_handshake(client_writer)
        except Exception as exc:
            logging.error("Falha no handshake com o cliente: %s", exc)
            client_writer.close()
            await client_writer.wait_closed()
            return

    # Connect to the selected backend
    try:
        server_reader, server_writer = await asyncio.open_connection(
            backend_host, backend_port
        )
        # Apply keepalive on backend socket
        with contextlib.suppress(Exception):
            ssock: socket.socket = server_writer.get_extra_info("socket")  # type: ignore
            apply_tcp_keepalive(ssock)
    except Exception as exc:
        logging.error(
            "Falha ao conectar no backend %s:%d: %s",
            backend_host,
            backend_port,
            exc,
        )
        client_writer.close()
        await client_writer.wait_closed()
        return

    async def forward(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        """Forward bytes from reader to writer until EOF or error."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Erro no fluxo %s: %s", direction, exc)

    # Create tasks to forward data in both directions concurrently
    client_to_server = asyncio.create_task(
        forward(client_reader, server_writer, "cliente->servidor")
    )
    server_to_client = asyncio.create_task(
        forward(server_reader, client_writer, "servidor->cliente")
    )
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)

    # Close connections
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()


# ---------------------------------------------------------------------------
# Proxy startup and systemd integration
# ---------------------------------------------------------------------------


async def run_proxy(port: int) -> None:
    """Start the proxy on the specified port, listening on IPv4 and IPv6."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.bind(("::", port))
    sock.listen(512)
    server = await asyncio.start_server(handle_client, sock=sock)
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Iniciando MultiFlow em %s", addr_list)
    async with server:
        await server.serve_forever()

# ---------------------------------------------------------------------------
# Helpers for systemd and menu management
# ---------------------------------------------------------------------------

PORTS_FILE = Path("/opt/multiflow/ports")


def is_port_in_use(port: int) -> bool:
    """Check if the given port is already in use locally."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int) -> None:
    """Create and enable a systemd service for running the proxy on this port."""
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    command = f"{sys.executable} {script_path} --port {port}"
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
RestartSec=1

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
    """Stop and remove the systemd service associated with the port."""
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


def toggle_http_status_menu() -> None:
    """Interactive menu for toggling HTTP status codes used in the handshake."""
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'HTTP STATUS DO PROXY':^47}|")
        print("------------------------------------------------")
        enabled = load_enabled_statuses()
        all_codes = sorted(HTTP_STATUS.keys())
        for idx, code in enumerate(all_codes, start=1):
            flag = "ativo" if code in enabled else "inativo"
            print(f"{idx}. {code} - {flag}")
        print("0. Voltar")
        print("------------------------------------------------")
        sel = input("Digite qual deseja alterar: ").strip()
        if sel == "0":
            break
        if not sel.isdigit():
            input("Opção inválida. Pressione Enter para voltar.")
            continue
        idx = int(sel)
        if not (1 <= idx <= len(all_codes)):
            input("Opção inválida. Pressione Enter para voltar.")
            continue
        code = all_codes[idx - 1]
        if code == 101:
            print("> O status 101 não pode ser desativado.")
        else:
            if code in enabled:
                enabled.remove(code)
                print(f"> Status {code} desativado.")
            else:
                enabled.add(code)
                print(f"> Status {code} ativado.")
            save_enabled_statuses(enabled)
        input("Pressione Enter para continuar...")


def show_menu() -> None:
    """Interactive menu to manage proxy instances and HTTP status codes."""
    if not PORTS_FILE.exists():
        PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTS_FILE.touch()
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'MULTIFLOW PROXY':^47}|")
        print("------------------------------------------------")
        if PORTS_FILE.stat().st_size == 0:
            print(f"| Porta(s): {'nenhuma':<34}|")
        else:
            with PORTS_FILE.open() as f:
                ports = [line.strip() for line in f if line.strip()]
            active_ports = ' '.join(ports)
            print(f"| Porta(s):{active_ports:<35}|")
        print("------------------------------------------------")
        print("| 1 - Abrir Porta                     |")
        print("| 2 - Fechar Porta                    |")
        print("| 3 - Ativar/Desativar HTTP Status    |")
        print("| 0 - Sair                            |")
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
        elif option == '3':
            toggle_http_status_menu()
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Implementação Python do MultiFlow com detecção de handshake e suporte a múltiplos cabeçalhos"
        )
    )
    parser.add_argument("--port", type=int, help="Porta de escuta")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.port is not None:
        # Run directly on the specified port
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        try:
            asyncio.run(run_proxy(args.port))
        except KeyboardInterrupt:
            logging.info("Proxy encerrado pelo usuário")
    else:
        # Without --port, show the interactive menu (requires root)
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
