import sys
import asyncio
import signal

# Dicionário global para rastrear os servidores ativos e suas tarefas.
active_servers: dict[int, asyncio.Task] = {}
# Evento para sinalizar o encerramento gracioso do programa.
shutdown_event = asyncio.Event()

# Função para lidar com o sinal de interrupção (Ctrl+C) sem encerrar o programa.
def handle_interrupt_signal() -> None:
    print("\nPara encerrar o proxy, por favor, use a opção '3' no menu.")

# Função principal que inicia o proxy.
# Ela obtém a porta inicial, configura o signal handler, inicia o server inicial e o menu.
async def main() -> None:
    # Configura o manipulador de sinal para ignorar Ctrl+C.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_interrupt_signal)

    # Obtém a porta inicial a partir dos argumentos.
    initial_port = get_port()
    
    # Inicia o servidor na porta inicial e adiciona à lista de ativos.
    server_task = asyncio.create_task(start_proxy_server(initial_port))
    active_servers[initial_port] = server_task
    
    # Inicia o menu interativo.
    menu_task = asyncio.create_task(interactive_menu())
    
    # Aguarda o evento de encerramento ser disparado pela opção 3 do menu.
    await shutdown_event.wait()
    
    # Garante que o menu seja cancelado ao sair.
    menu_task.cancel()
    try:
        await menu_task
    except asyncio.CancelledError:
        pass

# Função que inicia o servidor de proxy em uma porta específica.
async def start_proxy_server(port: int) -> None:
    try:
        # Tenta iniciar o servidor escutando em todos os endereços IPv6 (e consequentemente IPv4).
        server = await asyncio.start_server(handle_client, '::', port, family=asyncio.socket.AF_INET6)
        # Imprime uma mensagem indicando que o serviço está iniciando.
        print(f"Iniciando serviço na porta: {port}")
        async with server:
            await server.serve_forever()
    except OSError as e:
        # Imprime erro se falhar ao iniciar (ex: porta em uso).
        print(f"Erro ao iniciar o servidor na porta {port}: {e}")
    except Exception as e:
        # Imprime erro inesperado.
        print(f"Um erro inesperado ocorreu no servidor da porta {port}: {e}")
    finally:
        # Garante que o servidor seja removido da lista de ativos se parar.
        if port in active_servers:
            del active_servers[port]
            print(f"Servidor na porta {port} foi encerrado e removido da lista de ativos.")

# Função que lida com uma conexão de cliente individual.
# Ela envia respostas HTTP, detecta o tipo de tráfego e redireciona para o proxy apropriado.
async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        # Obtém o status personalizado dos argumentos.
        status = get_status()
        # Envia uma resposta HTTP 101 com o status.
        writer.write(f"HTTP/1.1 101 {status}\r\n\r\n".encode())
        await writer.drain()
        # Cria um buffer para ler dados do cliente.
        buffer = bytearray(1024)
        # Lê dados do cliente (possivelmente para ignorar ou processar).
        await reader.readinto(buffer)
        # Envia uma resposta HTTP 200 com o status.
        writer.write(f"HTTP/1.1 200 {status}\r\n\r\n".encode())
        await writer.drain()

        # Define o endereço padrão do proxy (SSH na porta 22).
        addr_proxy = "0.0.0.0:22"
        try:
            # Espia o stream com timeout de 1 segundo para decidir para onde encaminhar.
            data = await asyncio.wait_for(peek_stream(reader), timeout=1.0)
            # Se contém "SSH" ou está vazio, mantém SSH; caso contrário, usa OpenVPN.
            if not (data and "SSH" not in data):
                addr_proxy = "0.0.0.0:22"
            else:
                addr_proxy = "0.0.0.0:1194"
        except asyncio.TimeoutError:
            # Em caso de timeout, mantém padrão SSH.
            pass
        except Exception as e:
            # Imprime erro no peek para verbosidade, mantém SSH.
            print(f"Erro no peek: {e}")
            addr_proxy = "0.0.0.0:22"

        # Conecta-se ao serviço de destino.
        server_reader, server_writer = await asyncio.open_connection(*addr_proxy.split(':'))

        # Inicia transferências de dados em ambas as direções.
        client_to_server = asyncio.create_task(transfer_data(reader, server_writer))
        server_to_client = asyncio.create_task(transfer_data(server_reader, writer))

        # Aguarda ambas as transferências completarem.
        await asyncio.gather(client_to_server, server_to_client)

    except Exception as e:
        # Imprime erro no processamento do cliente.
        print(f"Erro ao processar cliente: {e}")
    finally:
        # Fecha o writer do cliente.
        writer.close()
        await writer.wait_closed()

# Função que transfere dados de um leitor para um escritor até que a conexão seja fechada.
async def transfer_data(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        # Buffer para leitura de dados.
        while not reader.at_eof():
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        # Imprime erros na transferência (ex: ConnectionResetError).
        print(f"Erro na transferência de dados: {e}")
    finally:
        # Fecha graciosamente: Sinaliza EOF e drena antes de close.
        try:
            writer.write_eof()
            await writer.drain()
        except Exception:
            pass
        writer.close()
        await writer.wait_closed()

# Função que espiar (peek) os dados do stream sem consumi-los.
# Retorna os dados como string.
async def peek_stream(reader: asyncio.StreamReader) -> str:
    # Espia os bytes disponíveis.
    data = await reader.peek(8192)
    # Converte para string, permitindo perda de dados UTF-8 inválidos.
    return data.decode(errors='replace')

# Função que obtém a porta dos argumentos de comando.
# Default para 80 se não especificado.
def get_port() -> int:
    # Coleta argumentos da linha de comando.
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

# Função que obtém o status dos argumentos de comando.
# Default para "@RustyManager" se não especificado.
def get_status() -> str:
    # Coleta argumentos da linha de comando.
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

# Função para abrir uma nova porta para o proxy.
async def open_port():
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

# Função para fechar (remover) uma porta específica do proxy.
async def remove_port():
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

# Função para desativar todos os proxies ativos e sinalizar o encerramento do programa.
async def deactivate_all():
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
            pass
    print("Todos os proxies foram desativados. Encerrando o programa.")
    shutdown_event.set()  # Sinaliza para a função main que o programa pode encerrar

# Função que exibe e gerencia o menu interativo.
async def interactive_menu():
    while not shutdown_event.is_set():
        # Exibe o status atualizado antes das opções.
        if not active_servers:
            status_line = "Status => Desativado"
        else:
            ports_str = ", ".join(map(str, sorted(active_servers.keys())))
            status_line = f"Status => Ativo na(s) porta(s) {ports_str}"
        
        print(f"\n{status_line}")
        print("--------------------------------")
        print("1. Abrir Porta")
        print("2. Remover Porta")
        print("3. Desativar Proxy e Sair")
        print("0. Sair do Menu")
        print("--------------------------------")
        
        try:
            choice = await asyncio.to_thread(input, "Escolha uma opção: ")
        except EOFError:  # Lida com o caso de entrada ser fechada.
            break

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

if __name__ == "__main__":
    asyncio.run(main())
    print("Programa encerrado.")
