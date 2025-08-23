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

# --------------------------------------------------------------------------- 
# Backend selection heuristics 
# --------------------------------------------------------------------------- 
async def probe_backend_from_data(initial_data: bytes) -> tuple[str, int]:
    """Heurística: vazio/contém 'SSH' -> 22; caso contrário -> 1194. Host 127.0.0.1."""
    default_backend = ("127.0.0.1", 22)
    alt_backend = ("127.0.0.1", 1194)
    try:
        text = initial_data.decode("utf-8", errors="ignore")
    except Exception:
        return default_backend
    # CORREÇÃO: Tornei case-sensitive como no Rust para consistência na detecção.
    if not text or "SSH" in text:
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

    # CORREÇÃO: Removi apply_tcp_keepalive para evitar fechamentos prematuros (alto impacto).

    # 1) Envia 101 Switching Protocols imediatamente
    try:
        line = "HTTP/1.1 101 Switching Protocols\r\n\r\n"
        client_writer.write(line.encode())
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar HTTP 101: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 2) Leitura inicial curta e descarte
    try:
        # CORREÇÃO: Aumentei buffer para 4096 para requests falsos maiores (médio impacto).
        await client_reader.read(4096)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 3) Envio do 200 após a leitura inicial
    try:
        client_writer.write("HTTP/1.1 200 Connection Established\r\n\r\n".encode())
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar HTTP 200: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 4) Probe com timeout para inspecionar dados reais
    try:
        # CORREÇÃO: Aumentei buffer para 16384 para mais dados na inspeção consumidora (médio impacto).
        probe_data = await asyncio.wait_for(client_reader.read(16384), timeout=1.0)
        # Adicionei logging para depurar dados probados.
        if probe_data:
            logging.debug("Dados probados: %s bytes", len(probe_data))
    except asyncio.TimeoutError:
        probe_data = b""
    except Exception as exc:
        logging.error("Falha ao probe dados: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 5) Determina backend pela heurística no probe_data
    backend_host, backend_port = await probe_backend_from_data(probe_data)

    # 6) Conecta ao backend
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        # CORREÇÃO: Removi apply_tcp_keepalive aqui também.
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 7) Forward dos dados probe para o backend
    if probe_data:
        server_writer.write(probe_data)
        await server_writer.drain()

    # 8) Encaminhamento bidirecional (túnel)
    async def forward(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        """Copia bytes até EOF/erro; ao ver EOF aplica half-close no writer."""
        try:
            while True:
                data = await reader.read(8192)  # Buffer alinhado ao Rust
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
                    # CORREÇÃO: Adicionei mais suppress para exceções no half-close, garantindo propagação sem crashes (médio impacto).
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

    # 9) Fechamento limpo
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
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # Mantém default keepalive.
    sock.bind(("::", port))
    sock.listen(512)
    server = await asyncio.start_server(handle_client, sock=sock)
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Iniciando MultiFlow em %s", addr_list)
    async with server:
        await server.serve_forever()

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

def show_menu() -> None:
    """Menu interativo para gerenciar portas."""
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
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")

def parse_args() -> argparse.Namespace:
    """Argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="MultiFlow Proxy – handshake 101 imediato + 200 pós-sonda"
    )
    parser.add_argument("--port", type=int, help="Porta de escuta")
    # CORREÇÃO: Adicionei --no-menu para rodar direto sem menu, isolando execução (médio impacto).
    parser.add_argument("--no-menu", action="store_true", help="Roda proxy direto sem menu")
    return parser.parse_args()

def main() -> None:
    """Entrada do programa (modo proxy com --port, senão menu)."""
    args = parse_args()
    if args.port is not None or args.no_menu:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            # CORREÇÃO: Se --port não dado com --no-menu, usa default 80 como Rust.
            port = args.port if args.port else 80
            asyncio.run(run_proxy(port))
        except KeyboardInterrupt:
            logging.info("Proxy encerrado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()

if __name__ == "__main__":
    main()
