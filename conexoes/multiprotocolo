#!/usr/bin/env python3
import asyncio
import socket
import sys

# -------------------------
# Utilitários de argumentos
# -------------------------

def get_port() -> int:
    args = sys.argv[1:]
    port = 80
    for i in range(len(args)):
        if args[i] == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                port = 80
    return port

def get_status() -> str:
    args = sys.argv[1:]
    status = "@RustyManager"
    for i in range(len(args)):
        if args[i] == "--status" and i + 1 < len(args):
            status = args[i + 1]
    return status

# -------------------------
# Lógica principal do proxy
# -------------------------

async def transfer_data(read_sock: socket.socket, write_sock: socket.socket) -> None:
    loop = asyncio.get_running_loop()
    bufsize = 8192
    while True:
        data = await loop.sock_recv(read_sock, bufsize)
        if not data:
            break
        await loop.sock_sendall(write_sock, data)

async def peek_stream(sock: socket.socket) -> str:
    # Equivalente ao peek(&mut stream) do Rust, retornando String com utf8 lossy
    # Tenta ler até 8192 bytes sem consumir (MSG_PEEK).
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def on_readable():
        try:
            data = sock.recv(8192, socket.MSG_PEEK)
            if not fut.done():
                fut.set_result(data)
        except BlockingIOError:
            # Ainda não há dados prontos
            pass
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)

    loop.add_reader(sock.fileno(), on_readable)
    try:
        data = await fut
    finally:
        loop.remove_reader(sock.fileno())

    # Conversão "lossy" (substitui inválidos), similar ao from_utf8_lossy
    return data.decode("utf-8", errors="replace")

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    loop = asyncio.get_running_loop()
    client_sock: socket.socket = writer.get_extra_info("socket")
    client_sock.setblocking(False)

    status = get_status()

    # Equivalente:
    # client_stream.write_all("HTTP/1.1 101 {status}\r\n\r\n")
    await loop.sock_sendall(client_sock, f"HTTP/1.1 101 {status}\r\n\r\n".encode())

    # Lê até 1024 bytes e descarta, como no código original
    try:
        _ = await loop.sock_recv(client_sock, 1024)
    except Exception:
        pass

    # Envia "HTTP/1.1 200 {status}\r\n\r\n"
    await loop.sock_sendall(client_sock, f"HTTP/1.1 200 {status}\r\n\r\n".encode())

    # Heurística do destino com peek e timeout de 1s
    addr_proxy = "0.0.0.0:22"
    try:
        data = await asyncio.wait_for(peek_stream(client_sock), timeout=1.0)
        if ("SSH" in data) or (data == ""):
            addr_proxy = "0.0.0.0:22"
        else:
            addr_proxy = "0.0.0.0:1194"
    except asyncio.TimeoutError:
        addr_proxy = "0.0.0.0:22"
    except Exception:
        addr_proxy = "0.0.0.0:22"

    # Conecta no servidor de destino
    host, port_str = addr_proxy.rsplit(":", 1)
    port = int(port_str)
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setblocking(False)
    try:
        await loop.sock_connect(server_sock, (host, port))
    except Exception:
        print("erro ao iniciar conexão para o proxy ")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        try:
            server_sock.close()
        except Exception:
            pass
        return

    # Túnel bidirecional (cliente <-> servidor)
    try:
        await asyncio.gather(
            transfer_data(client_sock, server_sock),
            transfer_data(server_sock, client_sock),
        )
    finally:
        try:
            server_sock.close()
        except Exception:
            pass
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def start_http() -> None:
    port = get_port()
    # Bind em [::]:port como no original (IPv6)
    server = await asyncio.start_server(handle_client, host="::", port=port, family=socket.AF_INET6)
    print(f"Iniciando serviço na porta: {port}")
    async with server:
        await server.serve_forever()

def main() -> None:
    try:
        asyncio.run(start_http())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
