import asyncio
import argparse
import socket
import os
import subprocess

PORTS_FILE = "ports.txt"

async def transfer_data(reader, writer):
    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        print(f"Erro na transferência: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_client(client_reader, client_writer, status):
    client_writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
    await client_writer.drain()
    
    await client_reader.read(1024)
    
    client_writer.write(f"HTTP/1.1 200 {status}\r\n\r\n".encode())
    await client_writer.drain()
    
    try:
        peeked_data = await asyncio.wait_for(client_reader.peek(8192), timeout=1.0)
        data_str = peeked_data.decode(errors='ignore')
        if "SSH" in data_str or not data_str:
            addr_proxy = ("0.0.0.0", 22)
        else:
            addr_proxy = ("0.0.0.0", 1194)
    except asyncio.TimeoutError:
        addr_proxy = ("0.0.0.0", 22)
    
    try:
        server_reader, server_writer = await asyncio.open_connection(*addr_proxy)
    except Exception as e:
        print(f"Erro ao conectar ao proxy {addr_proxy}: {e}")
        client_writer.close()
        await client_writer.wait_closed()
        return
    
    asyncio.create_task(transfer_data(client_reader, server_writer))
    await transfer_data(server_reader, client_writer)

async def run_proxy(port, status):
    print(f"Iniciando serviço na porta: {port}")
    server = await asyncio.start_server(lambda r, w: handle_client(r, w, status), "::", port, family=socket.AF_INET6)
    async with server:
        await server.serve_forever()

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def add_proxy_port(port, status="MultiFlow Proxy"):
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return
    cmd = ["python", __file__, "--port", str(port), "--status", status]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(PORTS_FILE, "a") as f:
        f.write(f"{port}\n")
    print(f"Porta {port} aberta com sucesso.")

def del_proxy_port(port):
    os.system(f"fuser -k {port}/tcp")
    with open(PORTS_FILE, "r+") as f:
        lines = f.readlines()
        f.seek(0)
        f.truncate()
        for line in lines:
            if line.strip() != str(port):
                f.write(line)
    print(f"Porta {port} fechada com sucesso.")

def show_menu():
    while True:
        print("================= MultiFlow Proxy ================")
        if os.path.exists(PORTS_FILE) and os.path.getsize(PORTS_FILE) > 0:
            with open(PORTS_FILE, "r") as f:
                ports = " ".join(line.strip() for line in f)
            print(f"Portas(s): {ports}")
        else:
            print("Portas(s): nenhuma")
        print("1 - Abrir Porta")
        print("2 - Fechar Porta")
        print("0 - Sair")
        option = input("Selecione: ")
        if option == "1":
            port = int(input("Porta: "))
            status = input("Status (vazio para padrão): ") or "MultiFlow Proxy"
            add_proxy_port(port, status)
        elif option == "2":
            port = int(input("Porta: "))
            del_proxy_port(port)
        elif option == "0":
            break
        else:
            print("Inválido.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--status", default="MultiFlow Proxy")
    args = parser.parse_args()

    if args.port is not None:
        asyncio.run(run_proxy(args.port, args.status))
    else:
        show_menu()
