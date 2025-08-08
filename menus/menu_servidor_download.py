#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import signal
import time
import socket

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

def get_ip_address():
    """Obtém o endereço IP local da máquina."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Não precisa ser alcançável
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_status():
    """Verifica se o servidor está ativo."""
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None)

    try:
        with open(STATE_FILE, 'r') as f:
            pid, port = f.read().strip().split(':')
            pid = int(pid)
    except (IOError, ValueError):
        if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
        return ("Inativo", None)

    try:
        os.kill(pid, 0)
        return ("Ativo", port)
    except OSError:
        if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
        return ("Inativo", None)

def start_server():
    """Inicia o servidor de upload/download."""
    status, port = check_status()
    if status == "Ativo":
        print(f"\n{COLORS.YELLOW}O servidor já está ativo na porta {port}.{COLORS.END}")
        return

    try:
        new_port = input(f"{COLORS.CYAN}Digite a porta para o servidor (ex: 8080): {COLORS.END}").strip()
        if not new_port.isdigit() or not (1 <= int(new_port) <= 65535):
            print(f"\n{COLORS.RED}Porta inválida.{COLORS.END}")
            return
        
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        process = subprocess.Popen([sys.executable, SERVER_SCRIPT_PATH, new_port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(STATE_FILE, 'w') as f:
            f.write(f"{process.pid}:{new_port}")
            
        ip = get_ip_address()
        print(f"\n{COLORS.GREEN}Servidor iniciado com sucesso!{COLORS.END}")
        print(f"{COLORS.YELLOW}Acesse a página de upload em: http://{ip}:{new_port}{COLORS.END}")

    except Exception as e:
        print(f"\n{COLORS.RED}Ocorreu um erro ao iniciar o servidor: {e}{COLORS.END}")

def stop_server():
    """Para o processo do servidor."""
    status, _ = check_status()
    if status == "Inativo":
        print(f"\n{COLORS.YELLOW}O servidor já está inativo.{COLORS.END}")
        return

    with open(STATE_FILE, 'r') as f:
        pid, port = f.read().strip().split(':')
        pid = int(pid)

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"\n{COLORS.GREEN}Servidor (PID: {pid}) finalizado com sucesso.{COLORS.END}")
    except OSError:
        print(f"\n{COLORS.YELLOW}O processo com PID {pid} não foi encontrado.{COLORS.END}")
    finally:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

def main():
    """Loop principal do menu de gerenciamento."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)
        
    while True:
        clear_screen()
        status, port = check_status()
        
        status_color = COLORS.GREEN if status == "Ativo" else COLORS.RED
        status_text = f"{status_color}{status}{COLORS.END}"
        
        info_lines = [f"Status: {status_text}"]
        if status == "Ativo":
            ip = get_ip_address()
            info_lines.append(f"URL de Acesso: {COLORS.YELLOW}http://{ip}:{port}{COLORS.END}")
        
        info_lines.append(f"Diretório de Arquivos: {COLORS.CYAN}{DOWNLOAD_DIR}{COLORS.END}")

        print_colored_box("SERVIDOR DE UPLOAD & DOWNLOAD", info_lines)
        print_menu_option("1", "Iniciar Servidor", color=COLORS.CYAN)
        print_menu_option("2", "Parar Servidor", color=COLORS.CYAN)
        print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")
        
        if choice == '1':
            start_server()
        elif choice == '2':
            stop_server()
        elif choice == '0':
            break
        else:
            print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == '__main__':
    main()
