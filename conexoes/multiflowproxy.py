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

# Table of supported HTTP status codes and their reason phrases.  These
# are sent in the order defined by sorted(enabled) when performing the
# initial handshake with a client.  Users can toggle which codes are
# active via the interactive menu.
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

# Location of the file that stores active status codes.  On first
# launch, all statuses except 200 are enabled by default.
STATUS_FILE = Path("/opt/multiflow/http_status")
# Default set of enabled codes; exclude 200 so that only a 101 is sent
# unless the user explicitly enables 200.
DEFAULT_ENABLED: Set[int] = set(HTTP_STATUS.keys()) - {200}


def load_enabled_statuses() -> Set[int]:
    """Load the set of active HTTP status codes from ``STATUS_FILE``.

    If the file does not exist or is empty/invalid, all codes except
    200 are enabled by default.  The returned set is always a subset
    of ``HTTP_STATUS.keys()``.
    """
    # Ensure the parent directory exists.
    # Attempt to ensure the directory exists.  If we lack permission
    # (e.g. running as an unprivileged user during testing), fall back
    # to the default set without persisting anything.
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return set(DEFAULT_ENABLED)
    if not STATUS_FILE.exists() or STATUS_FILE.stat().st_size == 0:
        enabled = set(DEFAULT_ENABLED)
        # Persist the default set if possible; ignore errors
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
    # If nothing valid was loaded, fall back to defaults
    if not enabled:
        enabled = set(DEFAULT_ENABLED)
        save_enabled_statuses(enabled)
    return enabled


def save_enabled_statuses(enabled: Set[int]) -> None:
    """Persist the set of active status codes to ``STATUS_FILE``."""
    # Try to write the file; ignore failures in unprivileged environments
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
    """Configure aggressive TCP keepalive settings on a socket.

    This enables SO_KEEPALIVE and, where supported, sets the idle time
    before the first probe, the interval between probes and the number
    of failed probes before the connection is considered dead.  It
    also enables TCP_NODELAY to reduce latency.
    """
    if not sock:
        return
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # Linux/BSD specific options
    if hasattr(socket, "TCP_KEEPIDLE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
    if hasattr(socket, "TCP_KEEPINTVL"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
    if hasattr(socket, "TCP_KEEPCNT"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
    # macOS uses TCP_KEEPALIVE for the idle time
    if hasattr(socket, "TCP_KEEPALIVE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, idle)
    if nodelay and hasattr(socket, "TCP_NODELAY"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


# ---------------------------------------------------------------------------
# Proxy core logic
# ---------------------------------------------------------------------------

async def probe_backend_from_data(initial_data: bytes) -> Tuple[str, int]:
    """Decide which backend to use based on the initial bytes received.

    The MultiFlow protocol allows connecting either to an SSH backend
    (port 22) or to an OpenVPN backend (port 1194).  This helper
    examines the provided data; if it is empty or contains the
    substring ``"SSH"`` (case insensitive), it selects the SSH
    backend.  Otherwise it selects the OpenVPN backend.  Both
    selections default to the localhost address (127.0.0.1) so that
    systemd services can bind on all interfaces.

    Args:
        initial_data: Bytes already read from the client.

    Returns:
        A tuple ``(host, port)`` representing the backend.
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


async def handle_client(
    client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
) -> None:
    """Handle a single client connection.

    Upon accepting a connection the proxy immediately sends all active
    HTTP status lines to the client.  It then reads up to 8 KiB of
    request data to parse custom headers and decide the backend
    destination.  If ``X-Real-Host`` is present the proxy connects to
    that host:port; otherwise it calls
    :func:`probe_backend_from_data` to choose between SSH and OpenVPN.
    Finally, it establishes a connection to the backend and shuttles
    data asynchronously between the client and server.  Half‑closures
    are honoured so that one direction can finish without killing the
    other.
    """
    # Apply TCP keepalive to the client socket if possible
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # Send handshake status lines before reading any payload
    try:
        enabled = load_enabled_statuses()
        for code in sorted(enabled):
            reason = HTTP_STATUS.get(code, "OK")
            client_writer.write(f"HTTP/1.1 {code} {reason}\r\n\r\n".encode())
            await client_writer.drain()
    except Exception as exc:
        logging.error("Falha no handshake com o cliente: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Now read up to 8KiB of initial data for header parsing
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Decode initial data into text for header extraction
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

    # Decide the backend address
    backend_host: str
    backend_port: int
    if host_port_header:
        # Parse "host[:port]"
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
        # No explicit host; determine via probe on initial data
        try:
            backend_host, backend_port = await probe_backend_from_data(initial_data)
        except Exception:
            backend_host, backend_port = ("127.0.0.1", 22)

    # If X-Split is present, consume another chunk from the client
    if x_split_header:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # Connect to the backend
    try:
        server_reader, server_writer = await asyncio.open_connection(
            backend_host, backend_port
        )
        # Apply keepalive to the backend socket
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
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ) -> None:
        """Forward bytes from reader to writer until EOF or error."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    # Perform a half close to signal EOF
                    try:
                        if writer.can_write_eof():
                            writer.write_eof()
                            await writer.drain()
                        else:
                            wsock: socket.socket = writer.get_extra_info("socket")  # type: ignore
                            if wsock:
                                with contextlib.suppress(OSError):
                                    wsock.shutdown(socket.SHUT_WR)
                    except Exception as exc:
                        logging.debug("Half-close %s: %s", direction, exc)
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Erro no fluxo %s: %s", direction, exc)

    # Launch bidirectional forwarding tasks
    client_to_server = asyncio.create_task(
        forward(client_reader, server_writer, "cliente->servidor")
    )
    server_to_client = asyncio.create_task(
        forward(server_reader, client_writer, "servidor->cliente")
    )
    # Wait for both directions to finish
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)
    # Close both sockets cleanly
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()


async def run_proxy(port: int) -> None:
    """Start the MultiFlow proxy on the specified port.

    Binds an IPv6 socket with dual‑stack enabled (so IPv4 clients can
    connect) and dispatches each connection to :func:`handle_client`.
    """
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Enable keepalive on the listening socket so accepted sockets may inherit it
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
# Systemd service and menu helpers
# ---------------------------------------------------------------------------

# File used to record active proxy ports.  Each line contains a port
# number for which a systemd service has been created.
PORTS_FILE = Path("/opt/multiflow/ports")


def is_port_in_use(port: int) -> bool:
    """Return True if the given TCP port is already bound locally."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int) -> None:
    """Create and start a systemd service running the proxy on ``port``."""
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
    """Stop and remove the systemd service for the specified port."""
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
    """Interactive menu to enable/disable HTTP status codes."""
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
        if code in enabled:
            enabled.remove(code)
            print(f"> Status {code} desativado.")
        else:
            enabled.add(code)
            print(f"> Status {code} ativado.")
        save_enabled_statuses(enabled)
        input("Pressione Enter para continuar...")


def show_menu() -> None:
    """Interactive menu for managing proxy instances and status codes."""
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
            input(
                "> Porta ativada com sucesso. Pressione Enter para voltar ao menu."
            )
        elif option == '2':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            del_proxy_port(port)
            input(
                "> Porta desativada com sucesso. Pressione Enter para voltar ao menu."
            )
        elif option == '3':
            toggle_http_status_menu()
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Implementação Python do MultiFlow com menu"
    )
    parser.add_argument("--port", type=int, help="Porta de escuta")
    return parser.parse_args()


def main() -> None:
    """Program entry point.

    If a port is specified via ``--port`` then the proxy is run on
    that port; otherwise the interactive menu is shown.  The menu
    requires root privileges because it manipulates systemd units.
    Logging is enabled when running as a proxy to aid in debugging.
    """
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
        )
        try:
            asyncio.run(run_proxy(args.port))
        except KeyboardInterrupt:
            logging.info("Proxy encerrado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
