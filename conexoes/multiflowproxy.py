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

# Dicionário com os status HTTP adicionados
HTTP_STATUS = {
    100: "Continue",
    101: "Switching Protocols",
    200: "Connection Established",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found",
    403: "Forbidden",
    404: "Not Found",
    503: "Service Unavailable"
}

# --- Persistência dos status ativos (todos ativos por padrão, EXCETO o 200) ---
STATUS_FILE = Path("/opt/multiflow/http_status")
DEFAULT_ENABLED = set(HTTP_STATUS.keys()) - {200}

def load_enabled_statuses() -> Set[int]:
    """
    Carrega o conjunto de códigos HTTP ativos a partir de STATUS_FILE.
    Se não existir ou estiver vazio/inválido, inicializa com todos os códigos
    exceto 200.
    """
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATUS_FILE.exists() or STATUS_FILE.stat().st_size == 0:
        enabled = set(DEFAULT_ENABLED)
        save_enabled_statuses(enabled)
        return enabled
    enabled: Set[int] = set()
    for line in STATUS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            code = int(line)
            if code in HTTP_STATUS:
                enabled.add(code)
        except ValueError:
            continue
    if not enabled:
        enabled = set(DEFAULT_ENABLED)
        save_enabled_statuses(enabled)
    return enabled

def save_enabled_statuses(enabled: Set[int]) -> None:
    """Salva os códigos ativos em STATUS_FILE, um por linha."""
    STATUS_FILE.write_text("\n".join(str(c) for c in sorted(enabled)) + "\n")

# --------- Estabilidade de conexão: Keepalive/TCP tuning ----------
def apply_tcp_keepalive(sock: socket.socket, *, idle: int = 10, interval: int = 5,  # ALTERAÇÃO: Valores mais agressivos (idle=10, interval=5, count=3)
                        count: int = 3, nodelay: bool = True) -> None:
    """
    Ativa SO_KEEPALIVE e, quando disponível, ajusta:
      - TCP_KEEPIDLE / TCP_KEEPALIVE (macOS) -> segundos até o 1º probe
      - TCP_KEEPINTVL -> intervalo entre probes
      - TCP_KEEPCNT -> quantidade de probes antes de considerar down
    Também ativa TCP_NODELAY (baixa latência).
    """
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
    # macOS usa TCP_KEEPALIVE para o "idle"
    if hasattr(socket, "TCP_KEEPALIVE"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, idle)
    if nodelay and hasattr(socket, "TCP_NODELAY"):
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

# ------------------------- Proxy ----------------------------------
async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    """Atende uma conexão: lê cabeçalhos, decide backend e faz proxy bidirecional."""
    # Keepalive no socket do cliente já aceito
    with contextlib.suppress(Exception):
        csock: socket.socket = client_writer.get_extra_info("socket")  # type: ignore
        apply_tcp_keepalive(csock)

    # ALTERAÇÃO: Handshake movido para AQUI - envia status ANTES de ler qualquer conteúdo
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

    # Agora, APÓS handshake, lê os dados iniciais
    try:
        initial_data = await client_reader.read(8192)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return
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
    # Decide backend (por header ou heurística)
    backend_host: str
    backend_port: int
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
                probe_backend(initial_data), timeout=1.0
            )
        except asyncio.TimeoutError:
            backend_host, backend_port = ("127.0.0.1", 22)
    if x_split_header:
        with contextlib.suppress(Exception):
            await client_reader.read(8192)
    # Conecta ao backend (após decidir, que depende dos dados lidos)
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        # Keepalive no socket para o backend (com valores agressivos)
        with contextlib.suppress(Exception):
            ssock: socket.socket = server_writer.get_extra_info("socket")  # type: ignore
            apply_tcp_keepalive(ssock)
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return
    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        """
        Copia dados de uma ponta à outra até EOF/erro.
        Em EOF: faz half-close (write_eof/shutdown) em vez de fechar o socket inteiro,
        permitindo que o outro sentido continue ativo.
        """
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    # EOF: meia-finalização do lado de escrita
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
    client_to_server = asyncio.create_task(forward(client_reader, server_writer, "cliente->servidor"))
    server_to_client = asyncio.create_task(forward(server_reader, client_writer, "servidor->cliente"))
    # Aguarda os dois sentidos finalizarem
    await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)
    # Fecha ordenadamente os dois sockets
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()

async def probe_backend(initial_data: bytes) -> Tuple[str, int]:
    """Usa os dados iniciais já lidos pra decidir backend: se contiver 'SSH' ou vazio → 22; caso contrário → 1194."""
    default_backend = ("127.0.0.1", 22)
    alt_backend = ("127.0.0.1", 1194)
    text = initial_data.decode('utf-8', errors='ignore')
    if not text or 'SSH' in text.upper():
        return default_backend
    return alt_backend

async def run_proxy(port: int) -> None:
    """Inicia o listener (IPv4/IPv6) e aceita conexões para o proxy."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except AttributeError:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # herda para aceptados em alguns SOs
    sock.bind(("::", port))
    sock.listen(512)
    server = await asyncio.start_server(lambda r, w: handle_client(r, w), sock=sock)
    addr_list = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logging.info("Iniciando MultiFlow em %s", addr_list)
    async with server:
        await server.serve_forever()

# Registro de portas ativas (persistência do menu)
PORTS_FILE = Path("/opt/multiflow/ports")

def is_port_in_use(port: int) -> bool:
    """Retorna True se a porta TCP já estiver em uso localmente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        return result == 0

def add_proxy_port(port: int) -> None:
    """Cria/inicia um serviço systemd que executa este script no modo proxy."""
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    script_path = Path(__file__).resolve()
    # Sem --status: os HTTP status são globais (menu)
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
    """Para e remove o serviço systemd da porta informada."""
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
    """Menu para ativar/desativar (toggle) os códigos HTTP do proxy."""
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
    """Menu interativo para abrir/fechar portas do proxy e configurar HTTP status."""
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
        print("| 1 - Abrir Porta |")
        print("| 2 - Fechar Porta |")
        print("| 3 - Ativar/Desativar HTTP Status |")
        print("| 0 - Sair |")
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

def parse_args() -> argparse.Namespace:
    """Lê argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Implementação Python do MultiFlow com menu")
    parser.add_argument("--port", type=int, help="Porta de escuta")
    # (removido --status)
    return parser.parse_args()

def main() -> None:
    """Ponto de entrada: proxy (--port) ou menu (root)."""
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
