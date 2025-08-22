#!/usr/bin/env python3
"""
MultiFlow proxy – lógica original solicitada:
- Lê a payload primeiro.
- Depois envia o handshake (sempre HTTP/1.1 101 + 200, nessa ordem).
- Suporte a X-Real-Host, Host e X-Online-Host para escolher backend.
- Consome [split]/[delay_split] e X-Split antes do handshake.
- Encaminhamento bidirecional e menu via systemd inclusos.
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
from typing import Tuple, Set, List, Optional

# ---------------------------------------------------------------------------
# HTTP status (sempre enviaremos 101 e 200 com HTTP/1.1)
# ---------------------------------------------------------------------------

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

def send_handshake_http11(writer: asyncio.StreamWriter) -> None:
    """Envia sempre (nessa ordem) 101 e 200 usando HTTP/1.1."""
    for code in (101, 200):
        reason = HTTP_STATUS.get(code, "OK")
        writer.write(f"HTTP/1.1 {code} {reason}\r\n\r\n".encode())

# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------

def apply_tcp_keepalive(
    sock: socket.socket,
    *,
    idle: int = 10,
    interval: int = 5,
    count: int = 3,
    nodelay: bool = True,
) -> None:
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
# Seleção de backend
# ---------------------------------------------------------------------------

async def probe_backend_from_data(initial_data: bytes) -> Tuple[str, int]:
    """Heurística simples: se vazio/contém 'SSH' => 22; senão => 1194."""
    default_backend = ("127.0.0.1", 22)
    alt_backend = ("127.0.0.1", 1194)
    try:
        text = initial_data.decode("utf-8", errors="ignore")
    except Exception:
        return default_backend
    if not text or "SSH" in text.upper():
        return default_backend
    return alt_backend

def find_header(text: str, header: str) -> str:
    """Procura um cabeçalho (case-insensitive) e retorna o valor sem espaços."""
    for line in text.split("\r\n"):
        if line.lower().startswith(header.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""

def parse_hostport_from_header(value: str) -> Tuple[str, int]:
    """Aceita 'host[:port]', URL (http/https) e listas separadas por espaço/;."""
    if not value:
        return ("", -1)
    token = value.split(";", 1)[0].split()[0]
    v = token.strip()
    if v.lower().startswith("http://"):
        v = v[7:]
    elif v.lower().startswith("https://"):
        v = v[8:]
    if "/" in v:
        v = v.split("/", 1)[0]
    if ":" in v:
        host, p = v.rsplit(":", 1)
        try:
            port = int(p)
        except ValueError:
            port = 22
        return (host, port)
    return (v, 22)

# ---------------------------------------------------------------------------
# Conexão de clientes (lógica original: handshake depois de ler payload)
# ---------------------------------------------------------------------------

async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    # Keepalive no cliente
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # 1) Ler a payload inicial (até 8 KiB) ANTES de responder
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    header_text = initial_data.decode("utf-8", errors="ignore")

    # 2) Descobrir backend por cabeçalhos (X-Real-Host > Host > X-Online-Host)
    x_real_host = find_header(header_text, "X-Real-Host")
    host_header = find_header(header_text, "Host")
    xonline_header = find_header(header_text, "X-Online-Host")

    backend_host: str
    backend_port: int

    for candidate in (x_real_host, host_header, xonline_header):
        if candidate:
            backend_host, backend_port = parse_hostport_from_header(candidate)
            break
    else:
        # Sem cabeçalhos úteis: usar heurística na payload
        try:
            backend_host, backend_port = await probe_backend_from_data(initial_data)
        except Exception:
            backend_host, backend_port = ("127.0.0.1", 22)

    # 3) Se houver X-Split ou marcadores [split]/[delay_split], consumir mais dados
    x_split_header = find_header(header_text, "X-Split")
    marker_found = ("[split]" in header_text) or ("[delay_split]" in header_text)
    if x_split_header or marker_found:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # 4) Abrir conexão ao backend ANTES do handshake (semântica CONNECT)
    try:
        server_reader, server_writer = await asyncio.open_connection(
            backend_host, backend_port
        )
        with contextlib.suppress(Exception):
            ssock: socket.socket = server_writer.get_extra_info("socket")  # type: ignore
            apply_tcp_keepalive(ssock)
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 5) Enviar o handshake agora (SEMPRE HTTP/1.1 101 + 200, nessa ordem)
    try:
        send_handshake_http11(client_writer)
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar handshake ao cliente: %s", exc)
        for w in (server_writer, client_writer):
            with contextlib.suppress(Exception):
                w.close()
        return

    # 6) Encaminhamento bidirecional
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Erro no fluxo %s: %s", direction, exc)

    c2s = asyncio.create_task(forward(client_reader, server_writer, "cliente->servidor"))
    s2c = asyncio.create_task(forward(server_reader, client_writer, "servidor->cliente"))
    await asyncio.gather(c2s, s2c, return_exceptions=True)

    # 7) Fechamento limpo
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()

# ---------------------------------------------------------------------------
# Inicialização e systemd
# ---------------------------------------------------------------------------

async def run_proxy(port: int) -> None:
    """Escuta em IPv6 dual-stack e despacha para handle_client."""
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

PORTS_FILE = Path("/opt/multiflow/ports")

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0

def add_proxy_port(port: int) -> None:
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
    """Mantido por compatibilidade (sem efeito no handshake fixo 101+200)."""
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'HTTP STATUS DO PROXY':^47}|")
        print("------------------------------------------------")
        print("Nesta versão, o handshake envia SEMPRE 101 e 200 (HTTP/1.1).")
        print("0. Voltar")
        print("------------------------------------------------")
        sel = input("Digite 0 para sair: ").strip()
        if sel == "0":
            break

def show_menu() -> None:
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
        print("| 3 - Info sobre HTTP Status          |")
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
            input("> Porta ativada. Pressione Enter para voltar ao menu.")
        elif option == '2':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            del_proxy_port(port)
            input("> Porta desativada. Pressione Enter para voltar ao menu.")
        elif option == '3':
            toggle_http_status_menu()
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")

# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MultiFlow (handshake após requisição; HTTP/1.1 101+200)")
    p.add_argument("--port", type=int, help="Porta de escuta")
    return p.parse_args()

async def run_proxy(port: int) -> None:
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

def main() -> None:
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
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
