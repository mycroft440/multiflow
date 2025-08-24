import sys
import asyncio
import socket  # Adicionado para corrigir o family no start_server (não altera lógica do proxy)

# Função principal que inicia o menu interativo para gerenciar proxies.
async def main() -> None:
    # Dicionário para rastrear servidores ativos por porta (adicionado para o menu).
    active_servers = {}

    # Loop do menu interativo.
    while True:
        # Exibe portas ativas.
        print("Portas ativas:")
        if active_servers:
            for port in sorted(active_servers.keys()):
                print(f"- {port}")
        else:
            print("Nenhuma porta ativa.")

        # Exibe opções do menu.
        print("\n1. Abrir Porta")
        print("2. Fechar Porta")
        print("0. Voltar")

        # Obtém escolha do usuário de forma assíncrona (não bloqueia o loop).
        loop = asyncio.get_event_loop()
        try:
            choice = (await loop.run_in_executor(None, input, "Escolha: ")).strip()
        except EOFError:
            print("Entrada terminada (EOF detectado). Saindo do menu.")
            break

        if choice == '1':
            # Abrir porta: pede a porta e inicia o servidor.
            try:
                port_str = (await loop.run_in_executor(None, input, "Porta para abrir: ")).strip()
            except EOFError:
                print("Entrada terminada (EOF detectado). Saindo do menu.")
                break
            try:
                port = int(port_str)
                if port in active_servers:
                    print(f"Porta {port} já está aberta.")
                else:
                    # Inicia o servidor e roda serve_forever em uma task de background.
                    server = await start_proxy_server(port)
                    asyncio.create_task(server.serve_forever())
                    active_servers[port] = server
                    print(f"Porta {port} aberta com sucesso.")
            except ValueError:
                print("Porta inválida (deve ser um número inteiro).")
            except Exception as e:
                print(f"Erro ao abrir porta {port}: {e}")

        elif choice == '2':
            # Fechar porta: pede a porta e fecha o servidor.
            try:
                port_str = (await loop.run_in_executor(None, input, "Porta para fechar: ")).strip()
            except EOFError:
                print("Entrada terminada (EOF detectado). Saindo do menu.")
                break
            try:
                port = int(port_str)
                if port in active_servers:
                    active_servers[port].close()
                    await active_servers[port].wait_closed()
                    del active_servers[port]
                    print(f"Porta {port} fechada com sucesso.")
                else:
                    print(f"Porta {port} não está aberta.")
            except ValueError:
                print("Porta inválida (deve ser um número inteiro).")
            except Exception as e:
                print(f"Erro ao fechar porta {port}: {e}")

        elif choice == '0':
            # Voltar: fecha todos os servidores ativos e sai.
            print("Fechando todas as portas ativas...")
            for port, server in list(active_servers.items()):
                server.close()
                await server.wait_closed()
            print("Saindo do menu.")
            break

        else:
            print("Opção inválida. Tente novamente.")

# Função que inicia o servidor de proxy em uma porta específica.
# Modificado ligeiramente para retornar o server em vez de rodar serve_forever internamente (necessário para múltiplos servidores).
async def start_proxy_server(port: int) -> asyncio.Server:
    try:
        # Tenta iniciar o servidor escutando em todos os endereços IPv6 (e consequentemente IPv4).
        server = await asyncio.start_server(handle_client, '::', port, family=socket.AF_INET6)
        # Imprime uma mensagem indicando que o serviço está iniciando.
        print(f"Iniciando serviço na porta: {port}")
        return server  # Retorna o server para gerenciamento externo.
    except OSError as e:
        # Imprime erro se falhar ao iniciar (ex: porta em uso).
        print(f"Erro ao iniciar o servidor na porta {port}: {e}")
        raise  # Propaga o erro para o menu tratar.
    except Exception as e:
        # Imprime erro inesperado.
        print(f"Um erro inesperado ocorreu no servidor da porta {port}: {e}")
        raise  # Propaga o erro.

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
        host, port_str = addr_proxy.split(':')
        server_reader, server_writer = await asyncio.open_connection(host, int(port_str))

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
    data = reader.peek(8192)
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

if __name__ == "__main__":
    asyncio.run(main())
