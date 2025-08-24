import asyncio
import subprocess
import os
from pathlib import Path
import socket
from typing import Optional

PORTS_FILE = "/conexoes/ports"


def is_port_in_use(port: int) -> bool:
    port_str = str(port)

    try:
        netstat_output = subprocess.check_output(["netstat", "-tuln"]).decode("utf-8")
        if f"::{port_str}\\b" in netstat_output or f"0.0.0.0:{port_str}\\b" in netstat_output:
            return True
    except subprocess.CalledProcessError:
        pass

    try:
        ss_output = subprocess.check_output(["ss", "-tuln"]).decode("utf-8")
        if f"::{port_str}\\b" in ss_output or f"0.0.0.0:{port_str}\\b" in ss_output:
            return True
    except subprocess.CalledProcessError:
        pass

    return False


def add_proxy_port(port: int, status: Optional[str] = None) -> None:
    if is_port_in_use(port):
        print(f"A porta {port} já está em uso.")
        return

    status_str = status or "@RustyProxy"
    command = f"/opt/rustyproxy/proxy --port {port} --status {status_str}"
    service_file_path = f"/etc/systemd/system/proxy{port}.service"
    service_file_content = f"""
    [Unit]
    Description=RustyProxy{port}
    After=network.target

    [Service]
    LimitNOFILE=infinity
    LimitNPROC=infinity
    LimitMEMLOCK=infinity
    LimitSTACK=infinity
    LimitCORE=0
    LimitAS=infinity
    LimitRSS=infinity
    LimitCPU=infinity
    LimitFSIZE=infinity
    Type=simple
    ExecStart={command}
    Restart=always

    [Install]
    WantedBy=multi-user.target
    """

    # Write service file
    with open(service_file_path, 'w') as f:
        f.write(service_file_content)

    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", f"proxy{port}.service"])
    subprocess.run(["sudo", "systemctl", "start", f"proxy{port}.service"])

    # Save port to file
    with open(PORTS_FILE, "a") as f:
        f.write(f"{port}\n")

    print(f"Porta {port} aberta com sucesso.")


def del_proxy_port(port: int) -> None:
    subprocess.run(["sudo", "systemctl", "disable", f"proxy{port}.service"])
    subprocess.run(["sudo", "systemctl", "stop", f"proxy{port}.service"])
    subprocess.run(["sudo", "rm", "-f", f"/etc/systemd/system/proxy{port}.service"])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])

    # Remove port from file
    with open(PORTS_FILE, "r") as f:
        ports_content = f.readlines()

    new_ports_content = [line for line in ports_content if line.strip() != str(port)]

    with open(PORTS_FILE, "w") as f:
        f.writelines(new_ports_content)

    print(f"Porta {port} fechada com sucesso.")


async def start_http(listener: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        data = await listener.read(1024)
        if not data:
            break

        # Handle client connection and proxy transfer
        addr_proxy = "0.0.0.0:22"  # Default

        if "SSH" in data.decode() or not data:
            addr_proxy = "0.0.0.0:22"
        else:
            addr_proxy = "0.0.0.0:1194"

        server_stream = await asyncio.open_connection(addr_proxy.split(":")[0], int(addr_proxy.split(":")[1]))
        server_reader, server_writer = server_stream

        # Transfer data between client and server
        await asyncio.gather(
            transfer_data(listener, server_writer),
            transfer_data(server_reader, writer),
        )


async def transfer_data(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    buffer = bytearray(8192)
    while True:
        n = await reader.readinto(buffer)
        if n == 0:
            break
        writer.write(buffer[:n])
        await writer.drain()


def get_port() -> int:
    import sys
    port = 80
    if "--port" in sys.argv:
        port_index = sys.argv.index("--port") + 1
        if port_index < len(sys.argv):
            port = int(sys.argv[port_index])
    return port


def get_status() -> str:
    import sys
    status = "@RustyManager"
    if "--status" in sys.argv:
        status_index = sys.argv.index("--status") + 1
        if status_index < len(sys.argv):
            status = sys.argv[status_index]
    return status


async def show_menu():
    if not Path(PORTS_FILE).exists():
        subprocess.run(["sudo", "touch", PORTS_FILE])

    while True:
        os.system("clear")
        print("================= @RustyManager ================")
        print("------------------------------------------------")
        print("|                  RUSTY PROXY                 |")
        print("------------------------------------------------")

        active_ports = ""
        with open(PORTS_FILE, "r") as f:
            active_ports = f.read().strip()
        print(f"| Portas(s): {'nenhuma' if not active_ports else active_ports:<34}|")

        print("------------------------------------------------")
        print("| 1 - Abrir Porta                              |")
        print("| 2 - Fechar Porta                             |")
        print("| 0 - Voltar ao menu                           |")
        print("------------------------------------------------")

        option = input("--> Selecione uma opção: ")

        if option == "1":
            port = int(input("Digite a porta: "))
            status = input("Digite o status de conexão (deixe vazio para o padrão): ") or None
            add_proxy_port(port, status)
        elif option == "2":
            port = int(input("Digite a porta: "))
            del_proxy_port(port)
        elif option == "0":
            break
        else:
            print("Opção inválida. Pressione qualquer tecla para voltar ao menu.")
            input()


async def main():
    import sys

    if "--menu" in sys.argv:
        await show_menu()
    else:
        port = get_port()
        server = await asyncio.start_server(start_http, "0.0.0.0", port)
        print(f"Iniciando serviço na porta: {port}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
