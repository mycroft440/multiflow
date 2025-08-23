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
# Seleção de backend baseada em heurísticas
# ---------------------------------------------------------------------------
# Esta seção define uma função assíncrona que analisa os dados iniciais recebidos
# do cliente para decidir qual backend usar. O proxy é "multiflow", ou seja, ele
# pode redirecionar o tráfego para diferentes serviços (backends) dependendo do
# tipo de conexão detectada. Aqui, ele verifica se os dados parecem ser de uma
# conexão SSH (porta 22) ou algo diferente, como OpenVPN (porta 1194). O host
# é sempre local (127.0.0.1), e a decisão é baseada em se os dados estão vazios
# ou contêm "SSH" (case-sensitive para consistência com a versão em Rust).
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
# Manipulação da conexão do cliente: Handshake e Túnel
# ---------------------------------------------------------------------------
# Esta função é o coração do proxy. Ela lida com cada conexão de cliente individual.
# O proxy simula um servidor HTTP para "enganar" possíveis censores ou firewalls,
# enviando respostas HTTP como "101 Switching Protocols" e "200 Connection Established".
# Em seguida, ele inspeciona os dados reais do cliente para decidir o backend,
# conecta-se ao backend escolhido e cria um túnel bidirecional, forwarding dados
# entre cliente e backend. Isso permite que conexões SSH ou VPN sejam "camufladas"
# como tráfego HTTP normal. O processo é assíncrono para lidar com múltiplas conexões
# simultaneamente sem bloquear.
async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    """Atende um cliente: handshake, parse, seleção de backend e túnel bidirecional."""

    # CORREÇÃO: Removi apply_tcp_keepalive para evitar fechamentos prematuros (alto impacto).

    # 1) Envia 101 Switching Protocols imediatamente
    # Aqui, o proxy envia uma resposta HTTP inicial para estabelecer o "handshake"
    # como se fosse um upgrade de protocolo (como WebSocket), mas na verdade é para
    # mascarar a conexão real.
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
    # Lê e descarta os cabeçalhos HTTP falsos enviados pelo cliente, que são usados
    # para simular uma requisição HTTP CONNECT (comum em proxies HTTP para túneis).
    try:
        # CORREÇÃO: Aumentei buffer para 4096 para requests falsos maiores (médio impacto).
        await client_reader.read(4096)
    except Exception as exc:
        logging.error("Falha ao ler dados iniciais: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 3) Envio do 200 após a leitura inicial
    # Envia uma resposta de sucesso HTTP para confirmar o "estabelecimento da conexão",
    # continuando a simulação de um proxy HTTP legítimo.
    try:
        client_writer.write("HTTP/1.1 200 Connection Established\r\n\r\n".encode())
        await client_writer.drain()
    except Exception as exc:
        logging.error("Falha ao enviar HTTP 200: %s", exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 4) Probe com timeout para inspecionar dados reais
    # Agora, lê os dados reais da aplicação (ex: SSH handshake) com um timeout curto.
    # Isso é usado para a heurística de seleção de backend sem bloquear indefinidamente.
    try:
        # CORREÇÃO: Aumentei buffer para 16384 para mais dados na inspeção consumidora (médio impacto).
        probe_data = await asyncio.wait_for(client_reader.read(8192), timeout=1.0)
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
    # Usa a função de probe para decidir se encaminha para SSH (22) ou outro (1194).
    backend_host, backend_port = await probe_backend_from_data(probe_data)

    # 6) Conecta ao backend
    # Estabelece uma conexão com o backend local escolhido (SSH ou VPN).
    try:
        server_reader, server_writer = await asyncio.open_connection(backend_host, backend_port)
        # CORREÇÃO: Removi apply_tcp_keepalive aqui também.
    except Exception as exc:
        logging.error("Falha ao conectar no backend %s:%d: %s", backend_host, backend_port, exc)
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 7) Forward dos dados probe para o backend
    # Envia os dados inspecionados (probe_data) para o backend, para que o handshake
    # da aplicação continue normalmente.
    if probe_data:
        server_writer.write(probe_data)
        await server_writer.drain()

    # 8) Encaminhamento bidirecional (túnel)
    # Define uma função interna para copiar dados de um lado para o outro.
    # Isso cria o túnel: dados do cliente vão para o servidor, e vice-versa.
    # Usa loops assíncronos para ler e escrever dados em blocos de 8192 bytes.
    # Quando uma extremidade termina (EOF), faz um "half-close" para sinalizar
    # o fim da transmissão em uma direção sem fechar a outra.
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

    # Cria tarefas assíncronas para forwarding em ambas as direções.
    c2s = asyncio.create_task(forward(client_reader, server_writer, "cliente->servidor"))
    s2c = asyncio.create_task(forward(server_reader, client_writer, "servidor->cliente"))

    # Aguarda as tarefas terminarem, capturando exceções.
    await asyncio.gather(c2s, s2c, return_exceptions=True)

    # 9) Fechamento limpo
    # Fecha as conexões de forma segura, suprimindo erros para evitar crashes.
    for w in (server_writer, client_writer):
        with contextlib.suppress(Exception):
            w.close()
            await w.wait_closed()

# ---------------------------------------------------------------------------
# Servidor principal e helpers para Systemd
# ---------------------------------------------------------------------------
# Esta função inicia o servidor proxy, escutando em uma porta específica.
# Usa IPv6 dual-stack para suportar IPv4 e IPv6. O servidor despacha cada
# conexão recebida para a função handle_client. Isso permite que o proxy
# rode como um serviço, lidando com múltiplas conexões.
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

# Arquivo para armazenar as portas ativas gerenciadas pelo menu.
PORTS_FILE = Path("/opt/multiflow/ports")

# Função auxiliar para verificar se uma porta já está em uso localmente.
def is_port_in_use(port: int) -> bool:
    """True se a porta já estiver em uso localmente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0

# Função para adicionar uma porta: cria um serviço systemd que roda o proxy nessa porta.
# Isso permite gerenciar múltiplos proxies em portas diferentes como serviços do sistema.
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

# Função para remover uma porta: para e deleta o serviço systemd correspondente.
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

# Menu interativo para gerenciar as portas ativas.
# Exibe opções para abrir/fechar portas e lista as portas atuais.
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

# Parser de argumentos de linha de comando.
def parse_args() -> argparse.Namespace:
    """Argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="MultiFlow Proxy – handshake 101 imediato + 200 pós-sonda"
    )
    parser.add_argument("--port", type=int, help="Porta de escuta")
    # CORREÇÃO: Adicionei --no-menu para rodar direto sem menu, isolando execução (médio impacto).
    parser.add_argument("--no-menu", action="store_true", help="Roda proxy direto sem menu")
    return parser.parse_args()

# Função principal: decide se roda o proxy diretamente (com --port) ou exibe o menu.
# Se for modo proxy, configura logging e inicia o servidor assíncrono.
# O menu requer privilégios de root para manipular serviços systemd.
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
