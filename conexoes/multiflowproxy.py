import sys
import asyncio
import socket
from asyncio import StreamReader, StreamWriter
import os

PORTS_FILE = "/opt/rustyproxy/ports"  # Caminho persistente; use /tmp para testes

def load_ports():
    if os.path.exists(PORTS_FILE):
        with open(PORTS_FILE, 'r') as f:
            return [int(line.strip()) for line in f if line.strip()]
    return []

def save_ports(ports):
    with open(PORTS_FILE, 'w') as f:
        for port in ports:
            f.write(f"{port}\n")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        try:
            s.bind(('::', port))
            return False
        except OSError:
            return True

async def server_task(port):
    try:
        server = await asyncio.start_server(handle_client, '::', port)
        print(f"Server iniciado na porta {port}")
        async with server:
            await server.serve_forever()
    except OSError as e:
        print(f"Erro ao iniciar server na porta {port}: {e}")

async def handle_client(reader: StreamReader, writer: StreamWriter):
    status = get_status()
    await writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
    await writer.drain()

    buffer = await reader.read(1024)
    await writer.write(f"HTTP/1.1 200 {status}\r\n\r\n".encode())
    await writer.drain()

    addr_proxy = "0.0.0.0:22"
    try:
        data = await asyncio.wait_for(peek_stream(reader), timeout=1.0)
        if "SSH" in data or not data:
            addr_proxy = "0.0.0.0:22"
        else:
            addr_proxy = "0.0.0.0:1194"
    except asyncio.TimeoutError:
        addr_proxy = "0.0.0.0:22"

    try:
        server_reader, server_writer = await asyncio.open_connection(*addr_proxy.split(':'))
    except Exception as e:
        print("erro ao iniciar conexão para o proxy")
        writer.close()
        await writer.wait_closed()
        return

    asyncio.create_task(transfer_data(reader, server_writer))
    await transfer_data(server_reader, writer)

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
    return "@RustyManager"  # Pode customizar via args se precisar

def show_menu(ports):
    os.system('clear')
    print("                              Menu Multiflow Proxy")
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
    ports = load_ports()
    tasks = {}
    for port in ports:
        task = asyncio.create_task(server_task(port))
        tasks[port] = task

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
                if is_port_in_use(port):
                    print("Porta já em uso.")
                    await asyncio.sleep(2)
                    continue
                task = asyncio.create_task(server_task(port))
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
