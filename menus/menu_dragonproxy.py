import subprocess
import os
import time

# Dicionário para armazenar o estado das portas e SSL
proxy_status = {
    'active_ports': {},
    'ssl_ports': set()
}

def display_status():
    status_str = "Status: "
    if not proxy_status['active_ports']:
        status_str += "Desativado"
    else:
        ports_list = []
        for port, process in proxy_status['active_ports'].items():
            if port in proxy_status['ssl_ports']:
                ports_list.append(f"{port}ssl")
            else:
                ports_list.append(str(port))
        status_str += ", ".join(ports_list)
    print(status_str)

def display_menu():
    print("\nMenu:")
    print("1. Abrir Porta")
    print("2. Remover Porta")
    print("3. Ativar SSL")
    print("4. Desativar Proxy + SSL")
    print("0. Voltar")

def open_port():
    port = input("Digite a porta a ser aberta: ")
    if not port.isdigit():
        print("Porta inválida. Digite um número.")
        return
    port = int(port)
    if port in proxy_status['active_ports']:
        print(f"A porta {port} já está aberta.")
        return

    print(f"Abrindo porta {port}...")
    try:
        # Start the proxy in a new process group to allow killing it later
        cmd = ['sudo', '../conexoes/dragon_go', '-port', f':{port}']
        process = subprocess.Popen(cmd, preexec_fn=os.setsid, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proxy_status['active_ports'][port] = process
        print(f"Porta {port} aberta com sucesso.")
    except Exception as e:
        print(f"Erro ao abrir porta {port}: {e}")

def remove_port():
    port = input("Digite a porta a ser removida: ")
    if not port.isdigit():
        print("Porta inválida. Digite um número.")
        return
    port = int(port)

    if port not in proxy_status['active_ports']:
        print(f"A porta {port} não está aberta.")
        return

    print(f"Removendo porta {port}...")
    try:
        process = proxy_status['active_ports'].pop(port)
        os.killpg(os.getpgid(process.pid), 9) # SIGKILL
        if port in proxy_status['ssl_ports']:
            proxy_status['ssl_ports'].remove(port)
        print(f"Porta {port} removida com sucesso.")
    except Exception as e:
        print(f"Erro ao remover porta {port}: {e}")

def activate_ssl():
    port = input("Digite a porta para ativar SSL: ")
    if not port.isdigit():
        print("Porta inválida. Digite um número.")
        return
    port = int(port)

    if port not in proxy_status['active_ports']:
        print(f"A porta {port} não está aberta. Abra a porta primeiro.")
        return
    if port in proxy_status['ssl_ports']:
        print(f"SSL já está ativo na porta {port}.")
        return

    print(f"Ativando SSL na porta {port}...")
    try:
        # Stop the current process for this port
        process = proxy_status['active_ports'].pop(port)
        os.killpg(os.getpgid(process.pid), 9) # SIGKILL
        
        # Start a new process with SSL
        cmd = [‘sudo’, ‘../conexoes/dragon_go’, ‘-port’, f":{port}", ‘-portssl’, f":{port}", ‘-tls’]
        new_process = subprocess.Popen(cmd, preexec_fn=os.setsid, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proxy_status['active_ports'][port] = new_process
        proxy_status['ssl_ports'].add(port)
        print(f"SSL ativado na porta {port} com sucesso.")
    except Exception as e:
        print(f"Erro ao ativar SSL na porta {port}: {e}")

def deactivate_all():
    print("Desativando todos os proxies e SSL...")
    for port, process in list(proxy_status['active_ports'].items()):
        try:
            os.killpg(os.getpgid(process.pid), 9) # SIGKILL
            proxy_status['active_ports'].pop(port)
        except Exception as e:
            print(f"Erro ao desativar proxy na porta {port}: {e}")
    proxy_status['ssl_ports'].clear()
    print("Todos os proxies e SSL desativados.")

def main():
    while True:
        display_status()
        display_menu()
        choice = input("Escolha uma opção: ")

        if choice == '1':
            open_port()
        elif choice == '2':
            remove_port()
        elif choice == '3':
            activate_ssl()
        elif choice == '4':
            deactivate_all()
        elif choice == '0':
            print("Saindo...")
            deactivate_all() # Ensure all proxies are stopped on exit
            break
        else:
            print("Opção inválida. Tente novamente.")
        time.sleep(1) # Give some time for processes to update

if __name__ == "__main__":
    main()
