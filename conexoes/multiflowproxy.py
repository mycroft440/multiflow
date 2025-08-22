#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import logging
import os
import socket
import subprocess
import sys
import contextlib
from pathlib import Path
from typing import Tuple, Set, Dict, Optional

# ---------------------------------------------------------------------------
# HTTP status management
# ---------------------------------------------------------------------------

# Mapa de códigos de status -> reason phrase.
# 101 é sempre enviado primeiro no handshake (antes de ler payload).
# Após a leitura "sonda", podem ser enviados 100 (se habilitado ou Expect: 100-continue),
# 200 (se habilitado) e os demais códigos habilitados em ordem crescente, exceto 101.
HTTP_STATUS: Dict[int, str] = {
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

# Arquivo com a lista de status habilitados (um por linha).
# 101 é tratado como sempre habilitado para o 1º envio.
STATUS_FILE = Path("/opt/multiflow/http_status")

# Padrão: manter 101 e 200 habilitados.
DEFAULT_ENABLED: Set[int] = {101, 200}


def load_enabled_statuses() -> Set[int]:
    """Carrega o conjunto de status ativos de STATUS_FILE.
    Mantém apenas códigos existentes em HTTP_STATUS.
    Se não houver arquivo/valores válidos, retorna DEFAULT_ENABLED
    (e tenta persistir)."""
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
        with contextlib.suppress(Exception):
            save_enabled_statuses(enabled)
    return enabled


def save_enabled_statuses(enabled: Set[int]) -> None:
    """Persiste os status ativos em STATUS_FILE (ordenados ascendente)."""
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
    """Configura keepalive agressivo no socket (ignora opções não suportadas)."""
    if not sock:
        return
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # Linux/BSD
    if hasattr(socket, "TCP_KEEPIDLE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
    if hasattr(socket, "TCP_KEEPINTVL"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
    if hasattr(socket, "TCP_KEEPCNT"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
    # macOS
    if hasattr(socket, "TCP_KEEPALIVE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, idle)
    if nodelay and hasattr(socket, "TCP_NODELAY"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


# ---------------------------------------------------------------------------
# Headers/utilidades HTTP (parse genérico e seleção de backend)
# ---------------------------------------------------------------------------

def parse_headers(text: str) -> Dict[str, str]:
    """Parse tolerante de cabeçalhos (case-insensitive)."""
    headers: Dict[str, str] = {}
    # isola somente o cabeçalho (até CRLF-CRLF)
    head_end = text.find("\r\n\r\n")
    sep_len = 4
    if head_end == -1:
        head_end = text.find("\n\n")
        sep_len = 2 if head_end != -1 else 0
    header_only = text if head_end == -1 else text[:head_end]
    for line in header_only.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    # guarda também quantos bytes do corpo já vieram no initial_data
    headers["_body_offset_bytes"] = str(0)
    if head_end != -1:
        # bytes do corpo já presentes em initial (após separador)
        headers["_body_offset_bytes"] = str(len(text.encode("utf-8", "ignore")) - (head_end + sep_len))
    return headers


def parse_hostport_from_token(v: str) -> Tuple[str, int]:
    """Extrai (host, porta) de 'host[:porta]'; default porta=22."""
    v = v.strip()
    if not v:
        return ("", 22)
    # aceita URLs ou listas simples separadas
    for sep in [" ", ";", ","]:
        if sep in v:
            v = v.split(sep, 1)[0].strip()
            break
    # remove esquema se vier como URL
    if "://" in v:
        v = v.split("://", 1)[1]
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
    """Prioridade: x-real-host > x-online-host > x-forward-host > host."""
    for key in ("x-real-host", "x-online-host", "x-forward-host", "host"):
        v = h.get(key, "")
        if v:
            host, port = parse_hostport_from_token(v)
            if host:
                return (host, port)
    return ("", -1)


async def consume_request_body_if_needed(
    initial: bytes,
    headers: Dict[str, str],
    reader: asyncio.StreamReader,
    *,
    max_extra: int = 64 * 1024,
) -> None:
    """Se houver Content-Length, consome o corpo restante (limitado a max_extra)."""
    cl = headers.get("content-length")
    if not cl:
        return
    try:
        total = int(cl)
    except ValueError:
        return
    already_in_initial = 0
    try:
        already_in_initial = int(headers.get("_body_offset_bytes", "0"))
    except ValueError:
        already_in_initial = 0
    remaining = max(0, total - max(0, already_in_initial))
    if remaining <= 0:
        return
    to_read = min(remaining, max_extra)
    if to_read <= 0:
        return
    with contextlib.suppress(Exception):
        await reader.readexactly(to_read)


# ---------------------------------------------------------------------------
# Backend selection heuristics
# ---------------------------------------------------------------------------

async def probe_backend_from_data(initial_data: bytes) -> Tuple[str, int]:
    """Heurística: vazio/contém 'SSH' -> 22; caso contrário -> 1194. Host 127.0.0.1."""
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
# Conexão do cliente / Handshake e Túnel
# ---------------------------------------------------------------------------

async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    """Atende um cliente: handshake, parse, seleção de backend e túnel bidirecional."""
    # Keepalive no socket aceito
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # === HANDSHAKE (lógica corrigida): 101 imediato -> sonda -> demais status ===
    # 1) Envia 101 Switching Protocols imediatamente (antes de ler qualquer payload)
    try:
        # 101 é sempre enviado primeiro
        line = f"HTTP/1.1 101 {HTTP_STATUS.get(101, 'Switching Protocols')}\r\n\r\n"
        client_writer.write(line.encode())
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar HTTP 101: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 2) Leitura "sonda" curta com timeout (até 8 KiB) para parse de headers/heurísticas
    try:
        try:
            initial_data = await asyncio.wait_for(client_reader.read(8192), timeout=1.0)
        except asyncio.TimeoutError:
            initial_data = b""
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 3) Parse geral de headers a partir da sonda
    header_text = initial_data.decode("utf-8", errors="ignore")
    headers = parse_headers(header_text)

    # 3a) Ajuste opcional de keepalive com base em "Keep-Alive: timeout=X"
    ka = headers.get("keep-alive", "")
    if ka and csock:
        timeout_val: Optional[int] = None
        for part in ka.split(","):
            part = part.strip().lower()
            if part.startswith("timeout="):
                try:
                    timeout_val = int(part.split("=", 1)[1])
                except Exception:
                    pass
        if isinstance(timeout_val, int):
            apply_tcp_keepalive(csock, idle=timeout_val)

    # 4) Envio dos demais status após a sonda:
    #    - 100 Continue se (a) habilitado OU (b) cliente enviou "Expect: 100-continue"
    #    - 200 Connection Established se habilitado
    #    - Demais códigos habilitados (ascendentes), exceto 101/200/100 já enviados
    try:
        enabled = load_enabled_statuses()

        to_send: list[int] = []

        # 100 Continue (condicional)
        expect_hdr = headers.get("expect", "").lower()
        send_100 = (100 in enabled) or (expect_hdr == "100-continue")
        if send_100:
            to_send.append(100)

        # 200 Connection Established (se habilitado)
        if 200 in enabled:
            to_send.append(200)

        # Demais habilitados em ordem (exceto os já listados e o 101)
        for code in sorted(enabled):
            if code in (101,):  # 101 já foi enviado antes
                continue
            if code in to_send:
                continue
            to_send.append(code)

        # Envia sequência final
        for code in to_send:
            reason = HTTP_STATUS.get(code, "OK")
            client_writer.write(f"HTTP/1.1 {code} {reason}\r\n\r\n".encode())
            await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar status adicionais do handshake: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 5) Marcadores de split: X-Split e/ou [split]/[delay_split] no cabeçalho
    marker_found = ("[split]" in header_text) or ("[delay_split]" in header_text)
    if headers.get("x-split") or marker_found:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)

    # 6) Se houver Content-Length, consome o corpo residual (sem repassar ao backend)
    with contextlib.suppress(Exception):
        await consume_request_body_if_needed(initial_data, headers, client_reader)

    # 7) Determina backend por cabeçalho preferencial; fallback para heurística
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

    # 8) Conecta ao backend
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

    # 9) Encaminhamento bidirecional (túnel)
    async def forward(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        """Copia bytes até EOF/erro; ao ver EOF aplica half-close no writer."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    # half-close
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

    c2s = asyncio.create_task(forward(client_reader, server_writer, "cliente->servidor"))
    s2c = asyncio.create_task(forward(server_reader, client_writer, "servidor->cliente"))
    await asyncio.gather(c2s, s2c, return_exceptions=True)

    # 10) Fechamento limpo
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()


# ---------------------------------------------------------------------------
# Servidor / Systemd helpers
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


# ---------------------------------------------------------------------------
# Systemd service and menu helpers
# ---------------------------------------------------------------------------

PORTS_FILE = Path("/opt/multiflow/ports")


def is_port_in_use(port: int) -> bool:
    """True se a porta já estiver em uso localmente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def add_proxy_port(port: int) -> None:
    """Cria e inicia um serviço systemd executando o proxy na porta informada."""
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
    """Para e remove o serviço systemd da porta especificada."""
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
    """Menu interativo para ativar/desativar status HTTP do handshake."""
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'HTTP STATUS DO PROXY':^47}|")
        print("------------------------------------------------")
        enabled = load_enabled_statuses()
        all_codes = sorted(HTTP_STATUS.keys())
        for idx, code in enumerate(all_codes, start=1):
            flag = "ativo" if code in enabled or code == 101 else "inativo"
            # 101 é sempre enviado; mostre como "ativo"
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
            print("> O status 101 não pode ser desativado (é sempre enviado).")
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
    
