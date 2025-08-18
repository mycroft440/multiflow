import sys
import asyncio
import socket
from asyncio import StreamReader, StreamWriter
import os

PORTS_FILE = "/opt/multiprotocolo/ports"  # Caminho persistente; use /tmp para testes

def load_ports():
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            return [int(line.strip()) for line in f if line.strip()]
    return []

def save_ports(ports):
    with open(PORTS_FILE, 'w') as f:
        for port in ports:
            f.write(f"{port}\n")

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
    status = get_status()
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
    dest.close()
    await dest.wait_closed()

async def peek_stream(reader: StreamReader):
    peek_buffer = bytearray(8192)
    n = await reader._transport._loop.sock_recv_into(reader._transport.get_extra_info('socket'), peek_buffer, 8192, socket.MSG_PEEK)
    return peek_buffer[:n].decode(errors='ignore')

def get_status():
    return "@MultiProtocolo"  # Pode customizar via args se precisar

def show_menu(ports):
    os.system('clear')
    print("                              Menu MultiProtocolo")
    print()
    status = "Ativo" if ports else "Parado"
    portas_str = ", ".join(map(str, ports)) if ports else "Sem portas ativas"
    print(f"Proxy: {status}")
    print(f"Portas: {portas_str}")
    print()
    print("1. Abrir porta e Iniciar")
    print("2. Remover porta")
    print("3. Remover Proxy")
    print("0. voltar")
    print()

async def main_menu():
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
    valid_ports = []
    for port in ports:
        s = get_bound_socket(port)
        if s is not None:
            task = asyncio.create_task(server_task(port, sock=s))
            tasks[port] = task
            valid_ports.append(port)
        else:
            print(f"Porta {port} não disponível, removendo.")
    ports = valid_ports
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
                task = asyncio.create_task(server_task(port, sock=s))
                tasks[port] = task
                ports.append(port)
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
                    ports.remove(port)
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

if __name__ == "__main__":
    asyncio.run(main_menu())
