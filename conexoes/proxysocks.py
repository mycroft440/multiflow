"""
Python reimplementation of the RustyProxy server contained in the
`RustyProxyOnly` repository.  The original code is written in Rust and
sets up an asynchronous TCP proxy which listens on a given port and
forwards traffic to either an SSH or OpenVPN backend based on a simple
protocol probe.  It also emits HTTP‐style status lines before the
proxying begins.

This version leverages Python's :mod:`asyncio` standard library to
provide similar asynchronous networking behaviour.  Because Python
lacks a built in way to peek at socket data via the high level
:class:`asyncio.StreamReader`, the ``peek_stream`` helper uses the
underlying socket directly with the ``MSG_PEEK`` flag to inspect
incoming bytes without consuming them.  Command line arguments are
parsed using :mod:`argparse` and sensible defaults are provided for
both the listening port and the status string.  To run the server
simply invoke ``python3 rusty_proxy.py --port 80 --status "@RustyManager"``.

While this reimplementation attempts to mirror the behaviour of the
Rust code closely, there are unavoidable differences stemming from
language and library differences.  For example, error handling is
handled via exceptions and logging rather than explicit ``Result``
returns, and stream splitting is not necessary because
``asyncio`` separates reader and writer objects for each connection.
Nonetheless, the core logic—HTTP handshake, protocol probing and
bidirectional forwarding—remains faithful to the original design.
"""

import argparse
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
    # Send the HTTP handshake messages.  Use CRLF per RFC 7230.
    try:
        handshake_101 = f"HTTP/1.1 101 {status}\r\n\r\n".encode()
        handshake_200 = f"HTTP/1.1 200 {status}\r\n\r\n".encode()
        client_writer.write(handshake_101)
        await client_writer.drain()
        # Read and discard up to 1024 bytes from the client to mimic the
        # buffer flush in the Rust code.  We don't use the contents.
        # Read and discard up to 1024 bytes from the client.  The call will
        # suspend until either EOF or some data arrives, mirroring the
        # behaviour of the Rust `read` call which waits indefinitely for
        # input.  We ignore the returned data.
        await client_reader.read(1024)
        # Send the 200 OK line after the discard.
        client_writer.write(handshake_200)
        await client_writer.drain()
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed during handshake with client: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Probe the client stream to decide which backend to forward to.
    backend_host, backend_port = await probe_backend(client_reader, client_writer)

    # Establish a connection to the chosen backend.
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to connect to backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # Proxy data in both directions concurrently.  We spawn two tasks:
    # one moving data from client to server and one moving data from
    # server to client.  When either direction completes (e.g. the
    # client disconnects), the other will be cancelled to tidy up.
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    # EOF on one side, stop forwarding.
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:  # pylint: disable=broad-except
            logging.debug("Forwarding %s encountered error: %s", direction, exc)
        finally:
            # Close the writer to signal EOF to the other side.
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # Create the tasks and wait for both to finish.  If one task
    # finishes early, the other will still run to completion.
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
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(loop.run_in_executor(None, sock.recv, 8192, socket.MSG_PEEK), timeout=1.0)
    except (asyncio.TimeoutError, BlockingIOError):
        # Timeout or no data yet – assume SSH
        return default_backend
    except Exception:
        return default_backend
    # Interpret the peeked bytes as UTF‑8 text and decide on the backend.
    try:
        text = data.decode('utf-8', errors='ignore')
    except Exception:
        return default_backend
    if not text or 'SSH' in text:
        return default_backend
    return alt_backend


async def run_proxy(port: int, status: str) -> None:
    """Start the proxy listener and handle incoming connections."""
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, status),
        host="::",  # bind to both IPv4 and IPv6
        port=port
    )
    addr_list = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logging.info("Starting RustyProxy Python port on %s", addr_list)
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
        print("================= @RustyManager ================")
        print("------------------------------------------------")
        print(f"|{'RUSTY PROXY':^47}|")
        print("------------------------------------------------")
        # Display active ports
        if PORTS_FILE.stat().st_size == 0:
            print(f"| Portas(s): {'nenhuma':<34}|")
        else:
            with PORTS_FILE.open() as f:
                ports = [line.strip() for line in f if line.strip()]
            active_ports = ' '.join(ports)
            print(f"| Portas(s):{active_ports:<35}|")
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
    parser = argparse.ArgumentParser(description="RustyProxy Python implementation with menu")
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
