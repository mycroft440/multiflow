import sys
import asyncio
from asyncio import StreamReader, StreamWriter
import threading

# Variáveis globais para gerenciamento
active_servers = {}  # port: asyncio.Server
lock = threading.Lock()
loop = None  # Será definido no main
keep_running = asyncio.Event()  # Para manter o loop rodando indefinidamente

async def start_server(port: int) -> str:
    with lock:
        if port in active_servers:
            return "Porta já aberta"
    try:
        server = await asyncio.start_server(handle_client, '::', port, family=asyncio.socket.AF_INET6)
        with lock:
            active_servers[port] = server
        asyncio.create_task(server.serve_forever())
        return f"Porta {port} aberta com sucesso"
    except Exception as e:
        return f"Erro ao abrir porta {port}: {e}"

async def close_server(port: int) -> str:
    with lock:
        if port not in active_servers:
            return "Porta não está aberta"
        server = active_servers.pop(port)
    try:
        server.close()
        await server.wait_closed()
        return f"Porta {port} fechada com sucesso"
    except Exception as e:
        return f"Erro ao fechar porta {port}: {e}"

def get_running_status() -> str:
    with lock:
        ports = list(active_servers.keys())
    if not ports:
        return "O proxy não está funcionando"
    else:
        return f"O proxy está funcionando nas portas: {', '.join(map(str, ports))}"

def start_server_sync(port: int) -> str:
    future = asyncio.run_coroutine_threadsafe(start_server(port), loop)
    return future.result()

def close_server_sync(port: int) -> str:
    future = asyncio.run_coroutine_threadsafe(close_server(port), loop)
    return future.result()

def disable_proxy_sync() -> str:
    with lock:
        ports = list(active_servers.keys())
    for port in ports:
        close_server_sync(port)
    return "Proxy desativado e todas as portas fechadas"

async def main() -> None:
    global loop
    loop = asyncio.get_running_loop()
    initial_port = get_port()
    result = await start_server(initial_port)
    print(result)
    await keep_running.wait()  # Mantém o loop rodando indefinidamente, sem nunca setar

async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
    try:
        status = get_status()
        await writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
        await writer.drain()
        buffer = bytearray(1024)
        await reader.readinto(buffer)
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
            pass
        except Exception as e:
            print(f"Erro no peek: {e}")
            addr_proxy = "0.0.0.0:22"
        try:
            server_reader, server_writer = await asyncio.open_connection(*addr_proxy.split(':'))
        except Exception as e:
            print(f"erro ao iniciar conexão para o proxy: {e}")
            return
        # Tasks bidirecionais com gather
        client_to_server = asyncio.create_task(transfer_data(reader, server_writer))
        server_to_client = asyncio.create_task(transfer_data(server_reader, writer))
        await asyncio.gather(client_to_server, server_to_client)
    except Exception as e:
        print(f"Erro ao processar cliente: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def transfer_data(reader: StreamReader, writer: StreamWriter) -> None:
    while True:
        data = await reader.read(8192)
        if not data:
            break
        writer.write(data)
        await writer.drain()
    # Não fechar aqui; deixar para o caller

async def peek_stream(reader: StreamReader) -> str:
    data = await reader.peek(8192)
    return data.decode(errors='replace')

def get_port() -> int:
    args = sys.argv[1:]
    port = 80
    i = 0
    while i < len(args):
        if args[i] == "--port":
            if i + 1 < len(args):
                try:
                    port = int(args[i + 1])
                except ValueError:
                    port = 80
                i += 1
        i += 1
    return port

def get_status() -> str:
    args = sys.argv[1:]
    status = "@RustyManager"
    i = 0
    while i < len(args):
        if args[i] == "--status":
            if i + 1 < len(args):
                status = args[i + 1]
                i += 1
        i += 1
    return status

if __name__ == "__main__":
    # Inicia o loop asyncio em uma thread separada
    async_thread = threading.Thread(target=asyncio.run, args=(main(),))
    async_thread.start()

    # Menu interativo no thread principal
    while True:
        print("\nMenu Interativo:")
        print("1. Mostrar o status de funcionamento")
        print("2. Abrir porta")
        print("3. Fechar porta")
        print("4. Desativar proxy")
        print("0. Sair do menu interativo (deixar proxy em segundo plano)")
        choice = input("Escolha uma opção: ").strip()

        if choice == '1':
            print(get_running_status())
        elif choice == '2':
            try:
                new_port = int(input("Digite a porta a ser aberta: "))
                result = start_server_sync(new_port)
                print(result)
            except ValueError:
                print("Porta inválida. Deve ser um número inteiro.")
        elif choice == '3':
            try:
                close_port = int(input("Digite a porta a ser fechada: "))
                result = close_server_sync(close_port)
                print(result)
            except ValueError:
                print("Porta inválida. Deve ser um número inteiro.")
        elif choice == '4':
            result = disable_proxy_sync()
            print(result)
        elif choice == '0':
            print("Saindo do menu. O proxy continua rodando em segundo plano se houver portas ativas.")
            break
        else:
            print("Opção inválida. Tente novamente.")

    # Após sair do menu, o thread async continua rodando se houver servidores ativos
    # O programa não termina até que o usuário interrompa manualmente (ex: Ctrl+C)
