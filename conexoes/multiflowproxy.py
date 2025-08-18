import sys
import asyncio
import socket
from asyncio import StreamReader, StreamWriter
import os

PORTS_FILE = "/opt/multiprotocolo/ports"  # Caminho persistente; use /tmp para testes

port_to_status = {}

def load_ports():
    if os.path.exists(PORTS_FILE):
        ports = {}
        with open(PORTS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    if ':' in line:
                        port_str, status = line.split(':', 1)
                    else:
                        port_str = line
                        status = "@MultiProtocolo"
                    ports[int(port_str)] = status
        return ports
    return {}

def save_ports(ports):
    with open(PORTS_FILE, 'w') as f:
        for port, status in ports.items():
            f.write(f"{port}:{status}\n")

def get_bound_socket(port):
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.bind(('::', port))
        s.listen(1)  # Reserva a porta
        return s
    except OSError:
        return None

async def server_task(port, sock=None):
    try:
        server = await asyncio.start_server(handle_client, '::', port, sock=sock)
        print(f"Server iniciado na porta {port}")
        async with server:
            await server.serve_forever()
    except OSError as e:
        print(f"Erro ao iniciar server na porta {port}: {e}")
        if sock:
            sock.close()

async def handle_client(reader: StreamReader, writer: StreamWriter):
    port = writer.get_extra_info('sockname')[1]
    status = port_to_status.get(port, "@MultiProtocolo")
    await writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
    await writer.drain()

    buffer = await reader.read(1024)
    await writer.write(f"HTTP/1.1 200 {status}\r\n\r\n".encode())
    await writer.drain()

    addr_proxy = "127.0.0.1:22"
    try:
        data = await asyncio.wait_for(peek_stream(reader), timeout=1.0)
        if "SSH" in data or not data:
            addr_proxy = "127.0.0.1:22"
        else:
            addr_proxy = "127.0.0.1:1194"
    except asyncio.TimeoutError:
        addr_proxy = "127.0.0.1:22"

    try:
        server_reader, server_writer = await asyncio.open_connection(*addr_proxy.split(':'))
    except Exception as e:
        print("erro ao iniciar conexão para o proxy")
        writer.close()
        await writer.wait_closed()
        return

    t1 = asyncio.create_task(transfer_data(reader, server_writer))
    t2 = asyncio.create_task(transfer_data(server_reader, writer))
    await asyncio.gather(t1, t2)

async def transfer_data(source: StreamReader, dest: StreamWriter):
    while True:
        data = await source.read(8192)
        if not data:
            break
        dest.write(data)
        await dest.drain()
    # Removido close explícito para match original

async def peek_stream(reader: StreamReader):
    peek_buffer = bytearray(8192)
    n = await reader._transport._loop.sock_recv_into(reader._transport.get_extra_info('socket'), peek_buffer, 8192, socket.MSG_PEEK)
    return peek_buffer[:n].decode(errors='ignore')

def get_status():
    args = sys.argv[1:]
    status = "@MultiProtocolo"
    for i in range(len(args)):
        if args[i] == "--status":
            if i + 1 < len(args):
                status = args[i + 1]
    return status

def show_menu(ports):
    os.system('clear')
    print("                              Menu MultiProtocolo")
    print()
    status = "Ativo" if ports else "Parado"
    portas_str = ", ".join(f"{port} ({status})" for port, status in ports.items()) if ports else "Sem portas ativas"
    print(f"Proxy: {status}")
    print(f"Portas: {portas_str}")
    print()
    print("1. Abrir porta e Iniciar")
    print("2. Remover porta")
    print("3. Remover Proxy")
    print("0. voltar")
    print()

async def main_menu():
    global port_to_status
    dir_path = os.path.dirname(PORTS_FILE)
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path)
            with open(PORTS_FILE, 'w') as f:
                pass
            print("Instalação inicial realizada: Diretório e arquivo de portas criados.")
        except PermissionError:
            print("Erro de permissão ao criar diretório (execute com sudo).")
            return
    ports = load_ports()
    tasks = {}
    valid_ports = {}
    for port, status in ports.items():
        s = get_bound_socket(port)
        if s is not None:
            task = asyncio.create_task(server_task(port, sock=s))
            tasks[port] = task
            valid_ports[port] = status
        else:
            print(f"Porta {port} não disponível, removendo.")
    ports = valid_ports
    port_to_status = ports
    save_ports(ports)

    while True:
        show_menu(ports)
        option = input("Selecione uma opção: ").strip()
        if option == '1':
            if not ports:
                port_str = input("Digite a porta para iniciar: ").strip()
            else:
                port_str = input("Qual porta deseja adicionar? ").strip()
            try:
                port = int(port_str)
                if port in ports:
                    print("Porta já ativa.")
                    await asyncio.sleep(2)
                    continue
                if port < 1024 and os.getuid() != 0:
                    print("Portas abaixo de 1024 requerem privilégios de root (execute com sudo).")
                    await asyncio.sleep(2)
                    continue
                s = get_bound_socket(port)
                if s is None:
                    print("Porta já em uso ou erro ao bind.")
                    await asyncio.sleep(2)
                    continue
                status_str = input("Digite o status de conexão (deixe vazio para @MultiProtocolo): ").strip()
                status = status_str if status_str else "@MultiProtocolo"
                task = asyncio.create_task(server_task(port, sock=s))
                tasks[port] = task
                ports[port] = status
                port_to_status[port] = status
                save_ports(ports)
                print("Porta adicionada e iniciada.")
            except ValueError:
                print("Porta inválida.")
            await asyncio.sleep(2)
        elif option == '2':
            if not ports:
                print("Nenhuma porta ativa.")
                await asyncio.sleep(2)
                continue
            port_str = input("Digite a porta para remover: ").strip()
            try:
                port = int(port_str)
                if port in ports:
                    tasks[port].cancel()
                    del tasks[port]
                    del ports[port]
                    del port_to_status[port]
                    save_ports(ports)
                    print("Porta removida.")
                else:
                    print("Porta não encontrada.")
            except ValueError:
                print("Porta inválida.")
            await asyncio.sleep(2)
        elif option == '3':
            for task in tasks.values():
                task.cancel()
            ports.clear()
            port_to_status.clear()
            save_ports(ports)
            print("Proxy removido.")
            await asyncio.sleep(2)
        elif option == '0':
            for task in tasks.values():
                task.cancel()
            break
        else:
            print("Opção inválida.")
            await asyncio.sleep(2)

async def main_single(port):
    global port_to_status
    port_to_status[port] = get_status()
    server = await asyncio.start_server(handle_client, '::', port)
    print(f"Iniciando serviço na porta {port}")
    async with server:
        await server.serve_forever()

def get_port():
    args = sys.argv[1:]
    port = None
    for i in range(len(args)):
        if args[i] == "--port":
            if i + 1 < len(args):
                try:
                    port = int(args[i + 1])
                except ValueError:
                    port = None
    return port

if __name__ == "__main__":
    port = get_port()
    if port is not None:
        asyncio.run(main_single(port))
    else:
        asyncio.run(main_menu())
