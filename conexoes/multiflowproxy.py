#!/usr/bin/env python3
"""
multiflowproxy: Proxy com menu e handshake multi-status.

Principais características:
- Envia múltiplos status HTTP no handshake para ofuscação.
- **200 Connection Established** é **sempre** enviado (fixo).
- Demais status HTTP ficam **ativados por padrão**, mas podem ser
  ativados/desativados pelo menu ("Modificar resposta").
- Suporte a cabeçalhos adicionais, modo Cloudflare e "fake SSL".
- Menu para abrir/fechar portas via systemd e alternar recursos.

Este arquivo substitui scripts anteriores e **remove** quaisquer
referências a "rustyproxy" (paths, descrições, logs), usando apenas
"multiflowproxy".
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

# ------------------------------------------------------------------
# Arquivos de estado (todos sob /opt/multiflowproxy/)
# ------------------------------------------------------------------
PORTS_FILE = Path("/opt/multiflowproxy/ports")
RESPONSES_STATUS_FILE = Path("/opt/multiflowproxy/response_status")

# Lista de status controláveis pelo menu (o 200 CE é sempre enviado).
RESPONSE_NAMES = [
    "100 Continue",
    "101 Switching Protocols",
    "204 No Content",
    # "200 Connection Established"  # <- FIXO, fora do toggle
    "301 Moved Permanently",
    "403 Forbidden",
    "404 Not Found",
    "503 Service Unavailable",
]


def load_response_status() -> dict[str, bool]:
    """Carrega (ou inicializa) o estado de ativação dos status HTTP.

    - Se o arquivo não existir, **todos** os status (da lista RESPONSE_NAMES)
      são considerados **ativos** por padrão.
    - O status **200 Connection Established** não é controlado por este
      arquivo: ele é sempre enviado.
    """
    status: dict[str, bool] = {name: True for name in RESPONSE_NAMES}
    if not RESPONSES_STATUS_FILE.exists():
        return status
    try:
        with RESPONSES_STATUS_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                name, state = line.split(":", 1)
                name = name.strip()
                state = state.strip().lower()
                if name in status:
                    status[name] = (state == "active")
    except Exception:
        # Em falhas de leitura/parsing, retornar padrão (todos ativos)
        pass
    return status


def save_response_status(status_dict: dict[str, bool]) -> None:
    """Salva o mapa de ativação dos status controláveis pelo menu."""
    try:
        RESPONSES_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with RESPONSES_STATUS_FILE.open("w", encoding="utf-8") as f:
            for name in RESPONSE_NAMES:
                state_str = "active" if status_dict.get(name, True) else "inactive"
                f.write(f"{name}:{state_str}\n")
    except Exception:
        pass


def is_port_in_use(port: int) -> bool:
    """Retorna True se a porta TCP estiver em uso no localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0


def add_proxy_port(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Cria e inicia um serviço systemd para o proxy na porta informada."""
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    cf_flag = "--cloudflare" if cloudflare else ""
    ssl_flag = "--fake-ssl" if fake_ssl else ""
    command = f"{sys.executable} {script_path} --port {port} --status {status} {cf_flag} {ssl_flag}"
    service_file_path = Path(f"/etc/systemd/system/proxy{port}.service")
    service_content = f"""[Unit]
Description=multiflowproxy {port}
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
    PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PORTS_FILE.open("a") as f:
        f.write(f"{port}\n")
    print(f"Porta {port} aberta com sucesso.")


def del_proxy_port(port: int) -> None:
    """Para e remove o serviço systemd do proxy da porta informada."""
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


def toggle_feature(port: int, feature_flag: str, enable: bool) -> None:
    """Liga/Desliga uma flag de execução no serviço systemd (ex.: --fake-ssl)."""
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
    """Menu interativo para gerenciar portas e recursos do multiflowproxy."""
    if not PORTS_FILE.exists():
        PORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORTS_FILE.touch()
    while True:
        os.system("clear")
        print("------------------------------------------------")
        print(f"|{'multiflowproxy':^47}|")
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
        print("| 5 - Modificar resposta                            |")
        print("| 0 - Sair                                          |")
        print("------------------------------------------------")
        option = input(" --> Selecione uma opção: ").strip()
        if option == '1':
            port_input = input("Digite a porta: ").strip()
            while not port_input.isdigit():
                print("Digite uma porta válida.")
                port_input = input("Digite a porta: ").strip()
            port = int(port_input)
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
        elif option == '5':
            statuses = load_response_status()
            print("\nLista de status HTTP (200 Connection Established é sempre ativo):\n")
            for idx, name in enumerate(RESPONSE_NAMES, start=1):
                state_str = "ativo" if statuses.get(name, True) else "inativo"
                print(f"{idx}. {name} - {state_str}")
            selecionado = input("\nSelecione o número para alternar (ou Enter para voltar): ").strip()
            if not selecionado:
                continue
            if not selecionado.isdigit():
                input("Opção inválida. Pressione Enter para voltar ao menu.")
            else:
                idx = int(selecionado)
                if 1 <= idx <= len(RESPONSE_NAMES):
                    name = RESPONSE_NAMES[idx - 1]
                    statuses[name] = not statuses.get(name, True)
                    save_response_status(statuses)
                    estado = "ativado" if statuses[name] else "desativado"
                    input(f"> Status '{name}' {estado}. Pressione Enter para voltar ao menu.")
                else:
                    input("Opção inválida. Pressione Enter para voltar ao menu.")
        elif option == '0':
            sys.exit(0)
        else:
            input("Opção inválida. Pressione Enter para voltar ao menu.")


async def probe_backend(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> Tuple[str, int]:
    """Espia os primeiros bytes para decidir entre SSH (22) ou OpenVPN (1194)."""
    default_backend = ("0.0.0.0", 22)
    alt_backend = ("0.0.0.0", 1194)
    sock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
    if sock is None:
        return default_backend
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    try:
        await loop.sock_recv(sock, 0)  # registra readiness
        data_bytes = sock.recv(8192, socket.MSG_PEEK)
        text = data_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return default_backend
    if not text or 'SSH' in text.upper():
        return default_backend
    return alt_backend


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter,
                        status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Fluxo principal por conexão: lê headers, envia handshake, faz ponte bidirecional."""
    # Leitura inicial (headers & preâmbulo de protocolo)
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    header_text = initial_data.decode("utf-8", errors="ignore")

    def find_header(text: str, header: str) -> str:
        idx = text.lower().find(header.lower() + ": ")
        if idx == -1:
            return ""
        value_start = idx + len(header) + 2
        end = text.find("\r\n", value_start)
        if end == -1:
            return ""
        return text[value_start:end]

    host_port_header = find_header(header_text, "X-Real-Host")
    x_split_header = find_header(header_text, "X-Split")

    cf_connecting_ip = find_header(header_text, "CF-Connecting-IP") if cloudflare else ""
    cf_ray = find_header(header_text, "CF-Ray") if cloudflare else ""
    cdn_loop = find_header(header_text, "CDN-Loop") if cloudflare else ""
    cf_ipcountry = find_header(header_text, "CF-IPCountry") if cloudflare else ""

    if cloudflare:
        logging.debug("Cloudflare headers: IP=%s Ray=%s Country=%s CDN-Loop=%s",
                      cf_connecting_ip, cf_ray, cf_ipcountry, cdn_loop)
        if cdn_loop.lower().count("cloudflare") > 1:
            logging.warning("Possível loop Cloudflare detectado via CDN-Loop: %s", cdn_loop)
            client_writer.close()
            await client_writer.wait_closed()
            return

    # Resolve backend
    if host_port_header:
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
        try:
            backend_host, backend_port = await asyncio.wait_for(
                probe_backend(client_reader, client_writer), timeout=1.0
            )
        except asyncio.TimeoutError:
            backend_host, backend_port = ("0.0.0.0", 22)

    if x_split_header:
        try:
            await client_reader.read(8192)
        except Exception:
            pass

    # --------- Handshake HTTP ---------
    try:
        # Cabeçalhos dinâmicos
        server_variants = [
            "nginx/1.18.0 (Ubuntu)",
            "Apache/2.4.41 (Ubuntu)",
            "Microsoft-IIS/10.0",
            "cloudflare",
        ]
        server_header = f"Server: {random.choice(server_variants)}"
        now_gmt = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        date_header = f"Date: {now_gmt}"
        cache_status = "CF-Cache-Status: HIT" if cloudflare else "Cache-Control: no-cache"

        fake_ssl_headers = ""
        if fake_ssl:
            fake_ssl_headers = (
                "Strict-Transport-Security: max-age=31536000; includeSubDomains\r\n"
                "Upgrade: tls/1.3\r\n"
                "Alt-Svc: h3=\":443\"; ma=86400\r\n"
            )

        trusted_domains = ["www.google.com", "www.example.com", "www.cloudflare.com"]
        forwarded_header = f"Forwarded: for={random.choice(trusted_domains)};host={random.choice(trusted_domains)};proto=https\r\n"
        x_forwarded_host_header = f"X-Forwarded-Host: {random.choice(trusted_domains)}\r\n"
        x_real_ip_header = (
            f"X-Real-IP: 192.168.{random.randint(0, 255)}.{random.randint(0, 255)}\r\n"
        )
        user_agent_header = (
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36\r\n"
        )

        response_status = load_response_status()

        # 100 Continue
        if response_status.get("100 Continue", True):
            client_writer.write(b"HTTP/1.1 100 Continue\r\n\r\n")
        # 101 Switching Protocols
        if response_status.get("101 Switching Protocols", True):
            h_101 = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                f"{server_header}\r\n"
                f"{date_header}\r\n"
                f"{cache_status}\r\n"
                f"{forwarded_header}"
                f"{x_forwarded_host_header}"
                f"{x_real_ip_header}"
                f"{fake_ssl_headers}\r\n"
            )
            client_writer.write(h_101.encode("utf-8"))
        # 204 No Content
        if response_status.get("204 No Content", True):
            client_writer.write(b"HTTP/1.1 204 No Content\r\n\r\n")

        # 200 Connection Established (SEMPRE enviado e com texto fixo)
        h_200 = (
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
        client_writer.write(h_200.encode("utf-8"))

        # Demais (301/403/404/503) conforme toggle
        if response_status.get("301 Moved Permanently", True):
            client_writer.write(b"HTTP/1.1 301 Moved Permanently\r\nLocation: /\r\n\r\n")
        if response_status.get("403 Forbidden", True):
            client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        if response_status.get("404 Not Found", True):
            client_writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
        if response_status.get("503 Service Unavailable", True):
            client_writer.write(b"HTTP/1.1 503 Service Unavailable\r\n\r\n")

        await client_writer.drain()

        if fake_ssl:
            fake_tls_bytes = b'\x16\x03\x03\x00\x2a' + os.urandom(42)
            client_writer.write(fake_tls_bytes)
            await client_writer.drain()
            logging.debug("Fake TLS bytes enviados")

    except Exception as exc:
        logging.error("Falha durante handshake com o cliente: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # --------- Conexão com backend ---------
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        if cloudflare and cf_connecting_ip:
            logging.info("Encaminhando do IP real: %s para %s:%d", cf_connecting_ip, backend_host, backend_port)
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as exc:
            logging.debug("Forwarding %s erro: %s", direction, exc)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    client_to_server = asyncio.create_task(forward(client_reader, server_writer, "client->server"))
    server_to_client = asyncio.create_task(forward(server_reader, client_writer, "server->client"))
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)


async def run_proxy(port: int, status: str, cloudflare: bool, fake_ssl: bool) -> None:
    """Inicia o listener do multiflowproxy e despacha conexões."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except (AttributeError, OSError):
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen(100)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, status, cloudflare, fake_ssl),
        sock=sock
    )
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info(
        "Starting multiflowproxy on %s (Cloudflare: %s, Fake SSL: %s)",
        addr_list, cloudflare, fake_ssl,
    )
    async with server:
        await server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="multiflowproxy com menu e handshake multi-status")
    parser.add_argument("--port", type=int, help="Porta para escutar")
    parser.add_argument(
        "--status", type=str, default="MultiProtocolo", help="String de status para respostas HTTP (opcional)"
    )
    parser.add_argument("--cloudflare", action="store_true", help="Ativa cabeçalhos Cloudflare e detecção de loop")
    parser.add_argument("--fake-ssl", action="store_true", help="Envia bytes TLS falsos após o handshake")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.port is not None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        try:
            asyncio.run(run_proxy(args.port, args.status, args.cloudflare, args.fake_ssl))
        except KeyboardInterrupt:
            logging.info("Proxy finalizado pelo usuário")
    else:
        if os.geteuid() != 0:
            print("Este script deve ser executado como root para o menu.")
            sys.exit(1)
        show_menu()


if __name__ == "__main__":
    main()
