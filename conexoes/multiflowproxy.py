#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import argparse
import os
import subprocess
import sys
from socket import socket

# --- Configurações Globais ---
# Diretório onde os arquivos de configuração e portas serão armazenados.
APP_DIR = "/opt/pyproxy"
# Arquivo para rastrear as portas ativas gerenciadas pelo menu.
PORTS_FILE = os.path.join(APP_DIR, "ports")
# Nome base para os serviços systemd.
SERVICE_NAME_TEMPLATE = "pyproxy@{}.service"

# --- Lógica do Servidor Proxy (Asyncio) ---

async def transfer_data(reader, writer, peer_name):
    """Lê dados do reader e os escreve no writer até que a conexão seja fechada."""
    try:
        while not reader.at_eof():
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        # Erros esperados quando uma das conexões é fechada abruptamente.
        pass
    except Exception as e:
        print(f"Erro durante a transferência de dados de {peer_name}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_client(client_reader, client_writer, status):
    """
    Gerencia uma nova conexão de cliente, determina o destino e estabelece o túnel de dados.
    """
    addr = client_writer.get_extra_info('peername')
    print(f"Nova conexão de: {addr}")

    status_message = status
    server_writer = None # Inicializa para o bloco finally

    try:
        # 1. Envia a resposta inicial "101 Switching Protocols".
        client_writer.write(f"HTTP/1.1 101 {status_message}\r\n\r\n".encode())
        await client_writer.drain()

        # 2. Aguarda e lê o primeiro pacote de dados do cliente.
        initial_data = await client_reader.read(1024)
        if not initial_data:
            return

        # 3. (REINTRODUZIDO) Adiciona um pequeno atraso para simular o comportamento
        #    do Rust e evitar que o cliente feche a conexão prematuramente.
        await asyncio.sleep(0.1) # Atraso de 100 milissegundos.

        # 4. (REINTRODUZIDO) Envia a segunda resposta "200 Connection established",
        #    replicando o comportamento exato do RustyProxy.
        client_writer.write(f"HTTP/1.1 200 {status_message}\r\n\r\n".encode())
        await client_writer.drain()

        # 5. Determina o endereço de destino com base nos dados iniciais.
        data_str = initial_data.decode(errors='ignore')
        if "SSH" in data_str:
            target_host, target_port = "127.0.0.1", 22
        else:
            target_host, target_port = "127.0.0.1", 1194

        print(f"Encaminhando {addr} para {target_host}:{target_port}")

        # 6. Conecta-se ao servidor de destino.
        server_reader, server_writer = await asyncio.open_connection(target_host, target_port)
        
        # 7. Envia os dados iniciais já lidos para o servidor de destino.
        server_writer.write(initial_data)
        await server_writer.drain()

        # 8. Inicia a transferência de dados bidirecional.
        client_to_server = asyncio.create_task(transfer_data(client_reader, server_writer, "cliente->servidor"))
        server_to_client = asyncio.create_task(transfer_data(server_reader, client_writer, "servidor->cliente"))

        await asyncio.gather(client_to_server, server_to_client)

    except Exception as e:
        print(f"Erro ao gerenciar cliente {addr}: {e}")
    finally:
        print(f"Fechando conexão de: {addr}")
        client_writer.close()
        await client_writer.wait_closed()
        if server_writer:
            server_writer.close()
            await server_writer.wait_closed()


async def run_proxy_server(port, status):
    """Inicia o servidor TCP na porta especificada."""
    handler = lambda r, w: handle_client(r, w, status=status)
    server = await asyncio.start_server(handler, '0.0.0.0', port)
    
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f"Servidor proxy iniciado em {addrs} com status '{status}'")

    async with server:
        await server.serve_forever()

# --- Lógica do Menu de Gerenciamento ---

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print("Erro: Este script precisa ser executado como root para gerenciar serviços.")
        sys.exit(1)

def is_port_in_use(port):
    """Verifica se uma porta TCP está em uso."""
    with socket() as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True

def get_active_ports():
    """Lê e retorna a lista de portas ativas do arquivo de configuração."""
    if not os.path.exists(PORTS_FILE):
        return []
    with open(PORTS_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def add_proxy_port():
    """Adiciona e inicia um novo serviço de proxy para uma porta específica."""
    check_root()
    try:
        port = int(input("Digite a porta para abrir: "))
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        print("Porta inválida. Por favor, insira um número entre 1 e 65535.")
        return

    status = input("Digite o status de conexão (padrão: @PythonProxy): ")
    if not status:
        status = "@PythonProxy"

    if is_port_in_use(port):
        print(f"A porta {port} já está em uso por outro processo.")
        return

    script_path = os.path.abspath(sys.argv[0])
    service_name = SERVICE_NAME_TEMPLATE.format(port)
    service_file_path = os.path.join("/etc/systemd/system", service_name)

    service_content = f"""[Unit]
Description=Python Proxy Service on port {port}
After=network.target

[Service]
Type=simple
User=root
ExecStart={sys.executable} {script_path} --run-proxy --port {port} --status "{status}"
Restart=always
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(service_file_path, 'w') as f:
            f.write(service_content)

        print("Recarregando daemons do systemd...")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print(f"Habilitando serviço {service_name}...")
        subprocess.run(["systemctl", "enable", service_name], check=True)
        print(f"Iniciando serviço {service_name}...")
        subprocess.run(["systemctl", "start", service_name], check=True)

        with open(PORTS_FILE, 'a') as f:
            f.write(f"{port}\n")

        print(f"\nProxy na porta {port} iniciado com sucesso!")

    except (subprocess.CalledProcessError, IOError) as e:
        print(f"Falha ao criar ou iniciar o serviço: {e}")
        if os.path.exists(service_file_path):
            os.remove(service_file_path)

def del_proxy_port():
    """Para e remove um serviço de proxy de uma porta específica."""
    check_root()
    try:
        port_str = input("Digite a porta para fechar: ")
        port = int(port_str)
    except ValueError:
        print("Porta inválida.")
        return

    service_name = SERVICE_NAME_TEMPLATE.format(port)
    service_file_path = os.path.join("/etc/systemd/system", service_name)

    if not os.path.exists(service_file_path):
        print(f"Nenhum serviço encontrado para a porta {port}.")
        return

    try:
        print(f"Parando serviço {service_name}...")
        subprocess.run(["systemctl", "stop", service_name], check=True, stderr=subprocess.PIPE)
        print(f"Desabilitando serviço {service_name}...")
        subprocess.run(["systemctl", "disable", service_name], check=True, stderr=subprocess.PIPE)
        
        os.remove(service_file_path)
        print("Recarregando daemons do systemd...")
        subprocess.run(["systemctl", "daemon-reload"], check=True)

        ports = get_active_ports()
        if port_str in ports:
            ports.remove(port_str)
            with open(PORTS_FILE, 'w') as f:
                for p in ports:
                    f.write(f"{p}\n")
        
        print(f"\nProxy na porta {port} removido com sucesso!")

    except (subprocess.CalledProcessError, IOError) as e:
        print(f"Falha ao remover o serviço: {e}")
        print("Pode ser que o serviço já estivesse parado.")


def show_menu():
    """Exibe o menu principal de gerenciamento."""
    os.system('clear')
    print("================= @PythonProxy Manager ================")
    print("-------------------------------------------------------")
    
    active_ports = get_active_ports()
    ports_display = " ".join(active_ports) if active_ports else "nenhuma"
    print(f"| Portas Ativas: {ports_display:<32}|")

    print("-------------------------------------------------------")
    print("| 1 - Abrir Porta de Proxy                            |")
    print("| 2 - Fechar Porta de Proxy                           |")
    print("| 0 - Sair                                            |")
    print("-------------------------------------------------------")

def main_menu():
    """Loop principal do menu interativo."""
    if not os.path.exists(APP_DIR):
        try:
            check_root()
            os.makedirs(APP_DIR)
            open(PORTS_FILE, 'a').close()
        except Exception as e:
            print(f"Não foi possível criar o diretório de configuração {APP_DIR}: {e}")
            sys.exit(1)

    while True:
        show_menu()
        option = input(" --> Selecione uma opção: ")
        if option == '1':
            add_proxy_port()
            input("\nPressione Enter para voltar ao menu...")
        elif option == '2':
            del_proxy_port()
            input("\nPressione Enter para voltar ao menu...")
        elif option == '0':
            break
        else:
            input("\nOpção inválida. Pressione Enter para tentar novamente...")

# --- Análise de Argumentos e Ponto de Entrada ---

def parse_args():
    """Analisa os argumentos da linha de comando, ignorando os desconhecidos."""
    parser = argparse.ArgumentParser(description="Python Proxy e Gerenciador.")
    parser.add_argument('--run-proxy', action='store_true', help='Executa o servidor proxy em vez do menu.')
    parser.add_argument('--port', type=int, help='Porta para o servidor proxy escutar.')
    parser.add_argument('--status', type=str, default="@PythonProxy", help='Mensagem de status para as respostas HTTP.')
    return parser.parse_known_args()

if __name__ == "__main__":
    args, _ = parse_args()

    if args.run_proxy:
        if not args.port:
            print("Erro: O argumento --port é obrigatório ao usar --run-proxy.")
            sys.exit(1)
        try:
            asyncio.run(run_proxy_server(args.port, args.status))
        except KeyboardInterrupt:
            print("\nServidor proxy desligado.")
    else:
        main_menu()
