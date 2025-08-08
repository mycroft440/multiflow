#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import signal
import time

# Adiciona o diretório pai ao sys.path para permitir importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError:
    print("Erro: Módulo de estilo não encontrado.")
    sys.exit(1)

# --- Configurações ---
COLORS = Colors()
SERVER_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'ferramentas', 'servidor_download.py')
STATE_FILE = "/tmp/download_server.state"
DOWNLOAD_DIR = '/opt/multiflow/downloads'

def check_status():
    """Verifica se o servidor está ativo e qual arquivo está sendo servido."""
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None, "Nenhum")

    try:
        with open(STATE_FILE, 'r') as f:
            pid, port = f.read().strip().split(':')
            pid = int(pid)
    except (IOError, ValueError):
        os.remove(STATE_FILE)
        return ("Inativo", None, "Nenhum")

    try:
        os.kill(pid, 0)
    except OSError:
        os.remove(STATE_FILE)
        return ("Inativo", None, "Nenhum")
    else:
        # Verifica qual arquivo está na pasta de download
        current_file = "Nenhum"
        if os.path.exists(DOWNLOAD_DIR) and os.listdir(DOWNLOAD_DIR):
            current_file = os.listdir(DOWNLOAD_DIR)[0]
        return ("Ativo", port, current_file)

def start_server():
    """Inicia o servidor de download em uma porta especificada."""
    status, port, _ = check_status()
    if status == "Ativo":
        print(f"\n{COLORS.YELLOW}O servidor ja esta ativo na porta {port}.{COLORS.END}")
        return

    if not os.path.exists(SERVER_SCRIPT_PATH):
        print(f"\n{COLORS.RED}Erro: O script do servidor ('{os.path.basename(SERVER_SCRIPT_PATH)}') nao foi encontrado.{COLORS.END}")
        return

    try:
        new_port = input(f"{COLORS.CYAN}Digite a porta para o servidor de download (ex: 8080): {COLORS.END}").strip()
        if not new_port.isdigit() or not (1 <= int(new_port) <= 65535):
            print(f"\n{COLORS.RED}Porta invalida.{COLORS.END}")
            return
        
        # Garante que o diretório de downloads exista
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        print(f"Diretorio de downloads: {DOWNLOAD_DIR}")
        
        # Inicia o servidor como um processo em segundo plano
        process = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT_PATH, new_port],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        with open(STATE_FILE, 'w') as f:
            f.write(f"{process.pid}:{new_port}")
            
        print(f"\n{COLORS.GREEN}Servidor de download iniciado com sucesso na porta {new_port} (PID: {process.pid}).{COLORS.END}")
        print(f"{COLORS.YELLOW}Acesse http://SEU_IP:{new_port} para baixar o arquivo.{COLORS.END}")

    except Exception as e:
        print(f"\n{COLORS.RED}Ocorreu um erro ao iniciar o servidor: {e}{COLORS.END}")

def stop_server():
    """Para o processo do servidor de download."""
    status, _, _ = check_status()
    if status == "Inativo":
        print(f"\n{COLORS.YELLOW}O servidor ja esta inativo.{COLORS.END}")
        return

    with open(STATE_FILE, 'r') as f:
        pid, port = f.read().strip().split(':')
        pid = int(pid)

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"\n{COLORS.GREEN}Servidor (PID: {pid} na porta {port}) finalizado com sucesso.{COLORS.END}")
    except OSError:
        print(f"\n{COLORS.YELLOW}O processo com PID {pid} nao foi encontrado.{COLORS.END}")
    finally:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

def main():
    """Loop principal do menu de gerenciamento."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root para gerenciar processos.{COLORS.END}")
        sys.exit(1)
        
    while True:
        clear_screen()
        status, port, current_file = check_status()
        
        status_color = COLORS.GREEN if status == "Ativo" else COLORS.RED
        status_text = f"{status_color}{status}{COLORS.END}"
        if port:
            status_text += f", Porta: {COLORS.YELLOW}{port}{COLORS.END}"
        
        info_lines = [
            f"Status: {status_text}",
            f"Arquivo Servido: {COLORS.CYAN}{current_file}{COLORS.END}",
            f"Diretorio: {COLORS.CYAN}{DOWNLOAD_DIR}{COLORS.END}"
        ]

        print_colored_box("SERVIDOR DE DOWNLOAD DIRETO", info_lines)
        print_menu_option("1", "Iniciar Servidor", color=COLORS.CYAN)
        print_menu_option("2", "Parar Servidor", color=COLORS.CYAN)
        print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

        choice = input(f"\n{COLORS.BOLD}Escolha uma opcao: {COLORS.END}")
        
        if choice == '1':
            start_server()
        elif choice == '2':
            stop_server()
        elif choice == '0':
            break
        else:
            print(f"\n{COLORS.RED}Opcao invalida. Tente novamente.{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == '__main__':
    main()
