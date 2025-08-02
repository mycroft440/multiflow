#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import subprocess
import time
import signal

# Nome do script do proxy que será gerenciado
PROXY_SCRIPT_NAME = "proxy.py"
# Arquivo para salvar o estado (PID e Porta) do proxy
STATE_FILE = "proxy.state"

def clear_screen():
    """Limpa a tela do terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def check_status():
    """Verifica se o processo do proxy está ativo e retorna seu status."""
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None)

    with open(STATE_FILE, 'r') as f:
        try:
            pid, port = f.read().strip().split(':')
            pid = int(pid)
        except ValueError:
            # Arquivo de estado corrompido
            os.remove(STATE_FILE)
            return ("Inativo", None)

    # Verifica se o processo com o PID salvo realmente existe
    try:
        os.kill(pid, 0)
    except OSError:
        # Processo não existe, mas o arquivo de estado sim. Limpa.
        os.remove(STATE_FILE)
        return ("Inativo", None)
    else:
        return ("Ativo", port)

def install_start():
    """Inicia o processo do proxy em segundo plano."""
    status, port = check_status()
    if status == "Ativo":
        print(f"\n\033[1;33mO proxy já está ativo na porta {port}.\033[0m")
        return

    if not os.path.exists(PROXY_SCRIPT_NAME):
        print(f"\n\033[1;31mErro: O arquivo '{PROXY_SCRIPT_NAME}' não foi encontrado no mesmo diretório.\033[0m")
        return

    try:
        new_port = input("Digite a porta para iniciar o proxy (padrão: 80): ") or "80"
        if not new_port.isdigit():
            print("\n\033[1;31mPorta inválida.\033[0m")
            return
        
        # Inicia o proxy.py como um novo processo
        # Usamos python3 para garantir compatibilidade
        process = subprocess.Popen(['python3', PROXY_SCRIPT_NAME, new_port])
        
        # Salva o PID e a porta no arquivo de estado
        with open(STATE_FILE, 'w') as f:
            f.write(f"{process.pid}:{new_port}")
            
        print(f"\n\033[1;32mProxy iniciado com sucesso na porta {new_port} (PID: {process.pid}).\033[0m")

    except Exception as e:
        print(f"\n\033[1;31mOcorreu um erro ao iniciar o proxy: {e}\033[0m")

def deactivate_remove():
    """Para o processo do proxy."""
    status, port = check_status()
    if status == "Inativo":
        print("\n\033[1;33mO proxy já está inativo.\033[0m")
        return

    with open(STATE_FILE, 'r') as f:
        pid, _ = f.read().strip().split(':')
        pid = int(pid)

    try:
        # Envia um sinal de término para o processo
        os.kill(pid, signal.SIGTERM)
        print(f"\n\033[1;32mProxy (PID: {pid}) finalizado com sucesso.\033[0m")
    except OSError:
        print(f"\n\033[1;33mO processo com PID {pid} não foi encontrado. Pode já ter sido finalizado.\033[0m")
    except Exception as e:
        print(f"\n\033[1;31mOcorreu um erro ao parar o proxy: {e}\033[0m")
    finally:
        # Remove o arquivo de estado independentemente do resultado
        os.remove(STATE_FILE)

def change_port():
    """Altera a porta do proxy (reinicia com uma nova porta)."""
    status, old_port = check_status()
    if status == "Inativo":
        print("\n\033[1;33mO proxy não está ativo. Inicie-o primeiro para alterar a porta.\033[0m")
        return
    
    print(f"\nO proxy está atualmente na porta {old_port}.")
    print("Desativando o proxy atual para alterar a porta...")
    deactivate_remove()
    
    # Pequena pausa para garantir que o processo foi finalizado
    time.sleep(1)
    
    print("\nAgora, vamos iniciar na nova porta.")
    install_start()

def display_menu():
    """Exibe o menu principal e o status atual."""
    clear_screen()
    status, port = check_status()
    
    status_color = "\033[1;32m" if status == "Ativo" else "\033[1;31m"
    status_text = f"{status_color}{status}\033[0m"
    if port:
        status_text += f", Porta: \033[1;33m{port}\033[0m"

    print("\033[0;34m━" * 10, "\033[1;32m GERENCIADOR DE PROXY ", "\033[0;34m━" * 10, "\n")
    print(f" Status: {status_text}\n")
    print("\033[0;34m" + "─" * 41 + "\033[0m")
    print(" \033[1;33m1.\033[1;37m Instalar / Iniciar Proxy")
    print(" \033[1;33m2.\033[1;37m Alterar Porta do Proxy")
    print(" \033[1;33m3.\033[1;37m Desativar / Remover Proxy")
    print(" \033[1;33m0.\033[1;37m Sair")
    print("\033[0;34m" + "─" * 41 + "\033[0m\n")

def main():
    """Loop principal do menu."""
    while True:
        display_menu()
        choice = input("\033[1;36mEscolha uma opção: \033[0m")
        
        if choice == '1':
            install_start()
        elif choice == '2':
            change_port()
        elif choice == '3':
            deactivate_remove()
        elif choice == '0':
            print("\n\033[1;32mSaindo do gerenciador...\033[0m")
            # Opcional: garante que o proxy seja parado ao sair do manager
            # status, _ = check_status()
            # if status == "Ativo":
            #     deactivate_remove()
            break
        else:
            print("\n\033[1;31mOpção inválida. Tente novamente.\033[0m")
        
        input("\nPressione Enter para continuar...")

if __name__ == '__main__':
    # Garante que o gerenciador seja executado com python3
    if sys.version_info.major < 3:
        print("Este script requer Python 3. Por favor, execute com 'python3'.")
        sys.exit(1)
    main()
