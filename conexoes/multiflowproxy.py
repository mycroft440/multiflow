import sys
import asyncio
from asyncio import StreamReader, StreamWriter
from concurrent.futures import ThreadPoolExecutor

async def main() -> None:
    # Dicionário para rastrear servidores ativos por porta
    servers = {}
    # Status global de argumentos
    global_status = get_status()

    # Se --port for fornecido, abra inicialmente essa porta
    initial_port = get_port()
    if initial_port:
        try:
            server = await asyncio.start_server(
                lambda r, w: handle_client(r, w, global_status),
                '::', initial_port, family=asyncio.socket.AF_INET6
            )
            servers[initial_port] = server
            asyncio.create_task(server.serve_forever())
            print(f"Porta inicial {initial_port} aberta.")
        except Exception as e:
            print(f"Erro ao abrir porta inicial {initial_port}: {e}")

    # Loop async para o menu interativo
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(1) as executor:
        while True:
            # Exibir status
            active_ports = sorted(servers.keys())
            if active_ports:
                print(f"Status: Ativo na porta {', '.join(map(str, active_ports))}...")
            else:
                print("Status: Desativado")

            # Exibir menu
            print("\n1. Abrir Porta")
            print("2. Fechar Porta")
            print("3. Desativar Proxy")
            print("0. Sair")

            # Ler input de forma async (usando executor para sys.stdin.readline sync)
            choice = await loop.run_in_executor(executor, sys.stdin.readline).strip()

            if choice == '1':
                # Abrir Porta
                port_str = await loop.run_in_executor(executor, sys.stdin.readline).strip()
                try:
                    port = int(port_str)
                except ValueError:
                    port = 80
                if port in servers:
                    print(f"Porta {port} já está ativa.")
                else:
                    try:
                        server = await asyncio.start_server(
                            lambda r, w: handle_client(r, w, global_status),
                            '::', port, family=asyncio.socket.AF_INET6
                        )
                        servers[port] = server
                        asyncio.create_task(server.serve_forever())
                        print(f"Porta {port} aberta.")
                    except Exception as e:
                        print(f"Erro ao abrir porta {port}: {e}")

            elif choice == '2':
                # Fechar Porta
                port_str = await loop.run_in_executor(executor, sys.stdin.readline).strip()
                try:
                    port = int(port_str)
                except ValueError:
                    print("Porta inválida.")
                    continue
                if port in servers:
                    server = servers.pop(port)
                    server.close()
                    await server.wait_closed()
                    print(f"Porta {port} fechada.")
                else:
                    print(f"Porta {port} não está ativa.")

            elif choice == '3':
                # Desativar Proxy: fechar todas as portas
                close_tasks = []
                for port, server in list(servers.items()):
                    server.close()
                    close_tasks.append(server.wait_closed())
                    print(f"Fechando porta {port}...")
                if close_tasks:
                    await asyncio.gather(*close_tasks)
                servers.clear()
                print("Proxy desativado completamente.")

            elif choice == '0':
                # Sair do menu, mas manter proxies ativos em background
                print("Saindo do menu. Proxies continuam ativos em background.")
                break

            else:
                print("Opção inválida.")

    # Após sair do menu, manter o loop rodando indefinidamente para tasks ativas
    if servers:
        await asyncio.Event().wait()  # Espera eterna, mantém tasks rodando

async def handle_client(reader: StreamReader, writer: StreamWriter, status: str) -> None:
    try:
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
    asyncio.run(main())
