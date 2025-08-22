#!/usr/bin/env python3
"""
MultiFlow proxy com handshake dividido:
- Handshake-primeiro: envia **apenas 101** antes de ler a payload; o restante (ex.: 200) é enviado depois de ler/processar.
- Handshake-depois: lê a payload primeiro e só então envia todos os códigos (101 e, se habilitado, 200).

Inclui:
- Detecção automática (timeout curto).
- Cabeçalho HandShake-First: 1 (ler antes) / 0 (enviar antes).
- Suporte a X-Real-Host, Host e X-Online-Host para escolher backend.
- Consumo de marcadores [split]/[delay_split] e cabeçalho X-Split.
- Encaminhamento bidirecional e menu via systemd.
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
# HTTP status
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

STATUS_FILE = Path("/opt/multiflow/http_status")
DEFAULT_ENABLED: Set[int] = {101, 200}

def load_enabled_statuses() -> Set[int]:
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
    with contextlib.suppress(Exception):
        STATUS_FILE.write_text("\n".join(str(c) for c in sorted(enabled)) + "\n")

def get_handshake_codes() -> list[int]:
    """Retorna a lista de códigos a usar no handshake (apenas 101 e, opcionalmente, 200)."""
    enabled = load_enabled_statuses()
    codes = [101]
    if 200 in enabled:
        codes.append(200)
    return codes

async def send_statuses(writer: asyncio.StreamWriter, codes: list[int]) -> None:
    """Envia exatamente os códigos informados, na ordem fornecida."""
    for code in codes:
        reason = HTTP_STATUS.get(code, "OK")
        writer.write(f"HTTP/1.1 {code} {reason}\r\n\r\n".encode())
    await writer.drain()

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
# Utilidades de cabeçalho
# ---------------------------------------------------------------------------

def find_header(text: str, header: str) -> str:
    for line in text.split("\r\n"):
        if line.lower().startswith(header.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""

# ---------------------------------------------------------------------------
# Conexão de clientes
# ---------------------------------------------------------------------------

HANDSHAKE_TIMEOUT = 0.5  # s

async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    # keepalive no socket do cliente
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # 1) Detecção automática: tenta ler rapidamente
    initial_data = b""
    data_received = False
    try:
        initial_data = await asyncio.wait_for(client_reader.read(8192), timeout=HANDSHAKE_TIMEOUT)
        data_received = bool(initial_data)
    except asyncio.TimeoutError:
        data_received = False

    header_text = ""
    handshake_after = False  # False => enviar 101 antes; True => ler antes

    if data_received:
        header_text = initial_data.decode("utf-8", errors="ignore")
        hs_header = find_header(header_text, "HandShake-First")
        if hs_header:
            handshake_after = (hs_header == "1")
        else:
            # Sem cabeçalho e já recebemos dados => cliente fala primeiro
            handshake_after = True
    else:
        # Sem dados no timeout => cliente espera status
        handshake_after = False

    # Conjunto de códigos do handshake
    all_codes = get_handshake_codes()
    codes_after = [c for c in all_codes if c != 101]

    # 2) Fluxo: handshake-primeiro => envia **só 101**, depois lê payload
    if not handshake_after:
        try:
            await send_statuses(client_writer, [101])  # <--- APENAS 101 ANTES
        except Exception as exc:
            logging.error("Falha ao enviar 101 inicial: %s", exc)
            client_writer.close()
            await client_writer.wait_closed()
            return
        # Agora ler payload inicial
        try:
            initial_data = await client_reader.read(8192)
            header_text = initial_data.decode("utf-8", errors="ignore")
        except Exception as exc:
            logging.error("Falha ao ler dados iniciais (modo handshake-primeiro): %s", exc)
            client_writer.close()
            await client_writer.wait_closed()
            return
    # 3) Fluxo: handshake-depois => já temos initial_data/header_text

    # Extrair possíveis cabeçalhos/markers
    x_real_host = find_header(header_text, "X-Real-Host")
    host_header = find_header(header_text, "Host")
    xonline_header = find_header(header_text, "X-Online-Host")
    header_candidate = next((h for h in (x_real_host, host_header, xonline_header) if h), "")

    # Determinar backend
    if header_candidate:
        token = header_candidate.split(";", 1)[0].split()[0]
        if token.lower().startswith("http://"):
            token = token[7:]
        elif token.lower().startswith("https://"):
            token = token[8:]
        if "/" in token:
            token = token.split("/", 1)[0]
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
        try:
            backend_host, backend_port = await probe_backend_from_data(initial_data)
        except Exception:
            backend_host, backend_port = ("127.0.0.1", 22)

    # Marcadores de split/atraso ou cabeçalho X-Split
    x_split_header = find_header(header_text, "X-Split")
    marker_found = ("[split]" in header_text) or ("[delay_split]" in header_text)
    if x_split_header or marker_found:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # 4) Se o handshake foi adiado (handshake-depois), envia tudo agora;
    #    se foi “antes”, envia **o restante** (ex.: 200) agora.
    try:
        if handshake_after:
            await send_statuses(client_writer, all_codes)   # 101 e, se ativo, 200
        elif codes_after:
            await send_statuses(client_writer, codes_after) # restante (ex.: 200) depois da leitura
    except Exception as exc:
        logging.error("Falha ao enviar status de handshake: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 5) Conexão ao backend e encaminhamento
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        with contextlib.suppress(Exception):
            ssock: socket.socket = server_writer.get_extra_info("socket")  # type: ignore
            apply_tcp_keepalive(ssock)
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

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

    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()

# ---------------------------------------------------------------------------
# Inicialização e systemd
# ---------------------------------------------------------------------------

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
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'HTTP STATUS DO PROXY':^47}|")
        print("------------------------------------------------")
        enabled = load_enabled_statuses()
        for idx, code in enumerate(sorted(HTTP_STATUS.keys()), start=1):
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
        all_codes = sorted(HTTP_STATUS.keys())
        if not (1 <= idx <= len(all_codes)):
            input("Opção inválida. Pressione Enter para voltar.")
            continue
        code = all_codes[idx - 1]
        if code == 101:
            print("> O status 101 não pode ser desativado.")
        else:
            e = load_enabled_statuses()
            if code in e:
                e.remove(code)
                print(f"> Status {code} desativado.")
            else:
                e.add(code)
                print(f"> Status {code} ativado.")
            save_enabled_statuses(e)
        input("Pressione Enter para continuar...")

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
# Entrada principal
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MultiFlow com handshake 101-antes e restante-depois")
    p.add_argument("--port", type=int, help="Porta de escuta")
    return p.parse_args()

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
