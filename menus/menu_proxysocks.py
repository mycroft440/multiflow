#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import subprocess
import time
import signal

# Importa as ferramentas de estilo para manter a consistência visual
try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError:
    # Fallback para o caso de o script ser executado de forma isolada
    print("Aviso: Módulo de estilo não encontrado. O menu será exibido sem formatação.")
    class Colors:
        RED = GREEN = YELLOW = CYAN = BOLD = END = ""
    class BoxChars:
        BOTTOM_LEFT = BOTTOM_RIGHT = HORIZONTAL = ""
    def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')
    def print_colored_box(title, content=None): print(f"--- {title} ---")
    def print_menu_option(num, desc, **kwargs): print(f"{num}. {desc}")

# Instancia as cores
COLORS = Colors()

# Nome do script do proxy que será gerenciado
# O ideal é que este script esteja no mesmo diretório ou em um caminho conhecido
PROXY_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'conexoes', 'proxysocks.py')
# Arquivo para salvar o estado (PID e Porta) do proxy
STATE_FILE = "/tmp/proxy.state"

def check_status():
    """Verifica se o processo do proxy está ativo e retorna seu status."""
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None)

    with open(STATE_FILE, 'r') as f:
        try:
            pid, port = f.read().strip().split(':')
            pid = int(pid)
        except ValueError:
            os.remove(STATE_FILE)
            return ("Inativo", None)

    try:
        os.kill(pid, 0)
    except OSError:
        os.remove(STATE_FILE)
        return ("Inativo", None)
    else:
        return ("Ativo", port)

def install_start():
    """Inicia o processo do proxy em segundo plano."""
    status, port = check_status()
    if status == "Ativo":
        print(f"\n{COLORS.YELLOW}O proxy já está ativo na porta {port}.{COLORS.END}")
        return

    if not os.path.exists(PROXY_SCRIPT_PATH):
        print(f"\n{COLORS.RED}Erro: O arquivo do proxy ('{os.path.basename(PROXY_SCRIPT_PATH)}') não foi encontrado no caminho esperado.{COLORS.END}")
        return

    try:
        new_port = input(f"{COLORS.CYAN}Digite a porta para iniciar o proxy (padrão: 80): {COLORS.END}") or "80"
        if not new_port.isdigit():
            print(f"\n{COLORS.RED}Porta inválida.{COLORS.END}")
            return
        
        # Inicia o proxy.py como um novo processo
        process = subprocess.Popen([sys.executable, PROXY_SCRIPT_PATH, new_port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(STATE_FILE, 'w') as f:
            f.write(f"{process.pid}:{new_port}")
            
        print(f"\n{COLORS.GREEN}Proxy iniciado com sucesso na porta {new_port} (PID: {process.pid}).{COLORS.END}")

    except Exception as e:
        print(f"\n{COLORS.RED}Ocorreu um erro ao iniciar o proxy: {e}{COLORS.END}")

def deactivate_remove():
    """Para o processo do proxy."""
    status, port = check_status()
    if status == "Inativo":
        print(f"\n{COLORS.YELLOW}O proxy já está inativo.{COLORS.END}")
        return

    with open(STATE_FILE, 'r') as f:
        pid, _ = f.read().strip().split(':')
        pid = int(pid)

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"\n{COLORS.GREEN}Proxy (PID: {pid}) finalizado com sucesso.{COLORS.END}")
    except OSError:
        print(f"\n{COLORS.YELLOW}O processo com PID {pid} não foi encontrado. Pode já ter sido finalizado.{COLORS.END}")
    except Exception as e:
        print(f"\n{COLORS.RED}Ocorreu um erro ao parar o proxy: {e}{COLORS.END}")
    finally:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

def change_port():
    """Altera a porta do proxy (reinicia com uma nova porta)."""
    status, old_port = check_status()
    if status == "Inativo":
        print(f"\n{COLORS.YELLOW}O proxy não está ativo. Inicie-o primeiro para alterar a porta.{COLORS.END}")
        return
    
    print(f"\nO proxy está atualmente na porta {old_port}.")
    print("Desativando o proxy atual para alterar a porta...")
    deactivate_remove()
    
    time.sleep(1)
    
    print("\nAgora, vamos iniciar na nova porta.")
    install_start()

def display_menu():
    """Exibe o menu principal e o status atual."""
    clear_screen()
    status, port = check_status()
    
    status_color = COLORS.GREEN if status == "Ativo" else COLORS.RED
    status_text = f"{status_color}{status}{COLORS.END}"
    if port:
        status_text += f", Porta: {COLORS.YELLOW}{port}{COLORS.END}"

    print_colored_box("GERENCIADOR DE PROXY SOCKS", [f"Status: {status_text}"])
    print_menu_option("1", "Instalar / Iniciar Proxy", color=COLORS.CYAN)
    print_menu_option("2", "Alterar Porta do Proxy", color=COLORS.CYAN)
    print_menu_option("3", "Desativar / Remover Proxy", color=COLORS.CYAN)
    print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

def main():
    """Loop principal do menu."""
    # Garante que o script seja executado com permissões adequadas se necessário
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root para gerenciar processos.{COLORS.END}")
        sys.exit(1)
        
    while True:
        display_menu()
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")
        
        if choice == '1':
            install_start()
        elif choice == '2':
            change_port()
        elif choice == '3':
            deactivate_remove()
        elif choice == '0':
            break
        else:
            print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == '__main__':
    main()
