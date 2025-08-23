import sys
import asyncio
from asyncio import StreamReader, StreamWriter, Task

# Dicionário global para rastrear os servidores ativos e suas tarefas
active_servers: dict[int, Task] = {}

async def start_proxy_server(port: int) -> None:
    """Inicia um servidor de proxy em uma porta específica."""
    try:
        # Tenta iniciar o servidor escutando em todos os endereços IPv6 (e consequentemente IPv4)
        server = await asyncio.start_server(handle_client, '::', port, family=asyncio.socket.AF_INET6)
        print(f"Serviço iniciado com sucesso na porta: {port}")
        
        async with server:
            await server.serve_forever()
    except OSError as e:
        print(f"Erro ao iniciar o servidor na porta {port}: {e}. A porta pode já estar em uso.")
    except Exception as e:
        print(f"Um erro inesperado ocorreu no servidor da porta {port}: {e}")
    finally:
        # Garante que o servidor seja removido da lista de ativos se parar
        if port in active_servers:
            del active_servers[port]
            print(f"Servidor na porta {port} foi encerrado e removido da lista de ativos.")


async def handle_client(reader: StreamReader, writer: StreamWriter) -> None:
    """Lida com as conexões de clientes, a lógica do proxy permanece a mesma."""
    try:
        status = get_status()
        # A lógica original do seu proxy
        await writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
        await writer.drain()
        buffer = bytearray(1024)
        await reader.readinto(buffer)
        await writer.write(f"HTTP/1.1 200 {status}\r\n\r\n".encode())
        await writer.drain()

        # Endereços de proxy padrão (usando localhost)
        addr_proxy_ssh = "127.0.0.1:22"
        addr_proxy_ovpn = "127.0.0.1:1194"
        addr_proxy = addr_proxy_ssh # Padrão para SSH

        try:
            # Espia o stream para decidir para onde encaminhar
            data = await asyncio.wait_for(peek_stream(reader), timeout=1.0)
            if "SSH" not in data and data:
                 addr_proxy = addr_proxy_ovpn
        except asyncio.TimeoutError:
            pass # Mantém o padrão SSH se houver timeout
        except Exception as e:
            print(f"Erro no peek: {e}")
        
        try:
            # Conecta-se ao serviço de destino
            server_reader, server_writer = await asyncio.open_connection(*addr_proxy.split(':'))
        except Exception as e:
            print(f"Erro ao conectar ao destino ({addr_proxy}): {e}")
            return
        
        # Cria tarefas para transferir dados bidirecionalmente
        client_to_server = asyncio.create_task(transfer_data(reader, server_writer))
        server_to_client = asyncio.create_task(transfer_data(server_reader, writer))

        # Aguarda a conclusão de ambas as tarefas
        await asyncio.gather(client_to_server, server_to_client)

    except Exception:
        # Silencioso para erros comuns de conexão (ex: reset de conexão)
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def transfer_data(reader: StreamReader, writer: StreamWriter) -> None:
    """Transfere dados de um leitor para um escritor até que a conexão seja fechada."""
    try:
        while not reader.at_eof():
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass # Erros esperados quando uma das conexões é fechada
    finally:
        writer.close()
        await writer.wait_closed()


async def peek_stream(reader: StreamReader) -> str:
    """Espia os dados iniciais no stream sem consumi-los."""
    data = await reader.peek(8192)
    return data.decode(errors='replace')


def get_port() -> int:
    """Obtém a porta inicial a partir dos argumentos da linha de comando."""
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
    """Obtém a mensagem de status a partir dos argumentos da linha de comando."""
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

# --- Seção do Menu Interativo ---

async def open_port():
    """Abre uma nova porta para o proxy."""
    try:
        port_str = await asyncio.to_thread(input, "Digite a porta que deseja abrir: ")
        port = int(port_str)
        if port <= 0 or port > 65535:
            print("Porta inválida. Por favor, insira um número entre 1 e 65535.")
            return
        if port in active_servers:
            print(f"A porta {port} já está em uso.")
        else:
            task = asyncio.create_task(start_proxy_server(port))
            active_servers[port] = task
            print(f"Tentando iniciar o proxy na porta {port}...")
    except ValueError:
        print("Entrada inválida. Por favor, digite um número de porta válido.")
    except Exception as e:
        print(f"Erro ao abrir a porta: {e}")


async def remove_port():
    """Fecha (remove) uma porta específica do proxy."""
    if not active_servers:
        print("Nenhum proxy para remover.")
        return
    try:
        port_str = await asyncio.to_thread(input, "Digite a porta que deseja remover: ")
        port = int(port_str)
        if port in active_servers:
            task = active_servers.pop(port)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                print(f"Proxy na porta {port} foi desativado.")
        else:
            print(f"Nenhum proxy encontrado na porta {port}.")
    except ValueError:
        print("Entrada inválida. Por favor, digite um número de porta válido.")


async def deactivate_all():
    """Desativa todos os proxies ativos."""
    if not active_servers:
        print("Nenhum proxy para desativar.")
        return
    
    print("Desativando todos os proxies...")
    ports = list(active_servers.keys())
    for port in ports:
        task = active_servers.pop(port)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            print(f"  - Proxy na porta {port} desativado.")
    print("Todos os proxies foram desativados.")


async def interactive_menu():
    """Exibe e gerencia o menu interativo."""
    while True:
        # Exibe o status atualizado antes das opções
        if not active_servers:
            status_line = "Status => Desativado"
        else:
            ports_str = ", ".join(map(str, sorted(active_servers.keys())))
            status_line = f"Status => Ativo na(s) porta(s) {ports_str}"
        
        print(f"\n{status_line}")
        print("--------------------------------")
        print("1. Abrir Porta")
        print("2. Remover Porta")
        print("3. Desativar Proxy")
        print("0. Sair")
        print("--------------------------------")
        
        choice = await asyncio.to_thread(input, "Escolha uma opção: ")

        if choice == '1':
            await open_port()
        elif choice == '2':
            await remove_port()
        elif choice == '3':
            await deactivate_all()
        elif choice == '0':
            print("Saindo do menu. O proxy continuará funcionando em segundo plano.")
            break
        else:
            print("Opção inválida. Tente novamente.")


async def main() -> None:
    """Função principal que inicia o proxy e o menu."""
    initial_port = get_port()
    
    # Inicia o servidor na porta inicial
    server_task = asyncio.create_task(start_proxy_server(initial_port))
    active_servers[initial_port] = server_task
    
    # Inicia o menu interativo
    menu_task = asyncio.create_task(interactive_menu())
    
    # Aguarda a conclusão do menu (o que significa que o usuário escolheu sair)
    await menu_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEncerrando o programa.")
