#!/usr/bin/env python3
"""
MultiFlow proxy – lê a payload primeiro e depois envia o handshake:
- Sempre envia (nessa ordem) os status HTTP/1.1:
  * 101 Switching Protocols
  * 200 Connection established
- Suporta X-Real-Host, X-Online-Host, X-Forward-Host e Host para escolher o backend.
- Consome [split]/[delay_split]/X-Split e corpo por Content-Length (quando houver).
- Faz parse tolerante de cabeçalhos comuns (User-Agent, X-Forwarded-For, Keep-Alive,
  Proxy-Connection, Accept-Encoding, Cache-Control, Cookie, Referer, Origin,
  Authorization, Proxy-Authorization, etc.) para compatibilidade de payloads.
- Mantém keepalive e menu via systemd.

Observação importante:
  O backend típico (SSH/OpenVPN) não fala HTTP. Os cabeçalhos lidos servem
  para "disfarçar" a primeira fase do tráfego; por isso NÃO são repassados ao
  backend (apenas consumidos localmente).
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
from typing import Tuple, Dict, Tuple, Optional

# ----------------------------- HTTP Status Lines -----------------------------

HTTP_STATUS = {
    101: "Switching Protocols",
    200: "Connection established",  # conforme solicitado (grafia exata)
}

async def send_handshake_http11(writer: asyncio.StreamWriter) -> None:
    """Envia sempre, nessa ordem, os status HTTP/1.1 101 e 200 Connection established."""
    writer.write(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
    await writer.drain()

# ----------------------------- TCP Keepalive ---------------------------------

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
    if nodelay and hasattr(socket, "TCP_NODELAY"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

# ----------------------------- Utilidades HTTP -------------------------------

def parse_headers(text: str) -> Dict[str, str]:
    """
    Faz parse tolerante (case-insensitive) das linhas 'Nome: Valor'.
    Em duplicatas, a última ocorrência prevalece.
    """
    headers: Dict[str, str] = {}
    for raw in text.split("\r\n"):
        if not raw or ":" not in raw:
            continue
        name, val = raw.split(":", 1)
        headers[name.strip().lower()] = val.strip()
    return headers

def parse_hostport_from_token(token: str) -> Tuple[str, int]:
    """Aceita 'host[:port]', URL (http/https) e listas separadas por espaço/;."""
    if not token:
        return ("", -1)
    v = token.split(";", 1)[0].split()[0].strip()
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

def choose_backend_from_headers(h: Dict[str, str]) -> Tuple[str, int]:
    """
    Ordem de preferência para destino:
      1) x-real-host        (override explícito, tradicional no MultiFlow)
      2) x-online-host      (redireciona p/ host real sem "revelar" destino)
      3) x-forward-host     (útil em chains netfree)
      4) host               (spoof do host zero-rated)
    """
    for key in ("x-real-host", "x-online-host", "x-forward-host", "host"):
        if key in h and h[key]:
            return parse_hostport_from_token(h[key])
    return ("", -1)

async def consume_request_body_if_needed(
    initial: bytes,
    headers: Dict[str, str],
    reader: asyncio.StreamReader,
    max_extra: int = 64 * 1024,
) -> None:
    """
    Se houver 'Content-Length', consome o corpo restante (até max_extra).
    Isso garante que payloads com corpo não quebrem o fluxo do cliente.
    """
    try:
        cl_val = headers.get("content-length")
        if not cl_val:
            return
        content_length = int(cl_val)
    except Exception:
        return

    # bytes já presentes após o fim do cabeçalho
    raw = initial
    eoh = raw.find(b"\r\n\r\n")
    have = 0
    if eoh != -1:
        body = raw[eoh + 4 :]
        have = len(body)

    remaining = max(0, content_length - have)
    total_read = 0
    while remaining > 0 and total_read < max_extra:
        chunk = await reader.read(min(65536, remaining))
        if not chunk:
            break
        total_read += len(chunk)
        remaining -= len(chunk)

# ----------------------------- Seleção de backend ----------------------------

async def probe_backend_from_data(initial_data: bytes) -> Tuple[str, int]:
    """Heurística simples: vazio/contém 'SSH' => 22; senão => 1194."""
    default_backend = ("127.0.0.1", 22)
    alt_backend = ("127.0.0.1", 1194)
    try:
        text = initial_data.decode("utf-8", errors="ignore")
    except Exception:
        return default_backend
    if not text or "SSH" in text.upper():
        return default_backend
    return alt_backend

# ----------------------------- Conexão do cliente ----------------------------

async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    # Keepalive no socket do cliente
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # 1) Ler payload inicial (até 8 KiB) ANTES de qualquer resposta
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    header_text = initial_data.decode("utf-8", errors="ignore")
    headers = parse_headers(header_text)

    # 2) Ajustes finos de keep-alive a partir de cabeçalhos (opcional)
    # Connection: keep-alive / close; Keep-Alive: timeout=10, max=50
    ka = headers.get("keep-alive", "")
    if ka:
        # extrai timeout se presente
        timeout = None
        for part in ka.split(","):
            part = part.strip().lower()
            if part.startswith("timeout="):
                try:
                    timeout = int(part.split("=", 1)[1])
                except Exception:
                    pass
        if timeout and csock:
            # usa timeout como IDLE do keepalive TCP
            apply_tcp_keepalive(csock, idle=timeout)

    # 3) Determinar backend por cabeçalho; fallback p/ heurística
    backend_host: str
    backend_port: int
    host_from_hdr, port_from_hdr = choose_backend_from_headers(headers)
    if host_from_hdr:
        backend_host, backend_port = host_from_hdr, port_from_hdr
    else:
        try:
            backend_host, backend_port = await probe_backend_from_data(initial_data)
        except Exception:
            backend_host, backend_port = ("127.0.0.1", 22)

    # 4) Consumo de marcadores/splits
    x_split = headers.get("x-split")
    marker_found = ("[split]" in header_text) or ("[delay_split]" in header_text)
    if x_split or marker_found:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # 5) Se houver Content-Length, consome o corpo residual (sem repassar ao backend)
    with contextlib.suppress(Exception):
        await consume_request_body_if_needed(initial_data, headers, client_reader)

    # 6) Conectar ao backend (SSH/OpenVPN); só depois enviar handshake ao cliente
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

    # 7) Enviar handshake agora (sempre HTTP/1.1 101 + 200 Connection established)
    try:
        await send_handshake_http11(client_writer)
    except Exception as exc:
        logging.error("Falha ao enviar handshake ao cliente: %s", exc)
        for w in (server_writer, client_writer):
            with contextlib.suppress(Exception):
                w.close()
        return

    # 8) Encaminhamento bidirecional (túnel)
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

    # 9) Fechamento limpo
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()

# ----------------------------- Inicialização/systemd -------------------------

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
            input("> Porta ativada com sucesso. Pressione Enter.")
        elif option == '2':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
            del_proxy_port(port)
            input("> Porta desativada com sucesso. Pressione Enter.")
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")

# ----------------------------- Entrada principal -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MultiFlow (handshake após requisição; HTTP/1.1 101 + 200 Connection established)")
    p.add_argument("--port", type=int, help="Porta de escuta")
    return p.parse_args()

async def run_server(port: int) -> None:
    await run_proxy(port)

def main() -> None:
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_server(args.port))
        except KeyboardInterrupt:
            logging.info("Proxy encerrado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()

if __name__ == "__main__":
    main()
