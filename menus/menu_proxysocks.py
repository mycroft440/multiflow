#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import signal
import time
import socket

# Adiciona o diretório pai ao caminho do sistema para permitir importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Importa os utilitários de estilo para a interface gráfica
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# Caminho para o script do proxy e para o arquivo de estado
PROXY_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'conexoes', 'proxysocks.py')
STATE_FILE = "/tmp/proxy.state"

def get_ip_address():
    """Obtém o endereço IP local da máquina para exibição."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Conecta-se a um IP de teste para descobrir o IP local da interface de saída
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_status():
    """Verifica se o processo do proxy está ativo lendo o arquivo de estado."""
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None, None)
    try:
        with open(STATE_FILE, 'r') as f:
            pid_s, port_s = f.read().strip().split(':')
        pid = int(pid_s)
        port = int(port_s)
    except Exception:
        # Se o arquivo de estado estiver corrompido, remove-o
        try: os.remove(STATE_FILE)
        except Exception: pass
        return ("Inativo", None, None)
    
    try:
        # Envia um sinal 0 para o PID para verificar se o processo ainda existe
        os.kill(pid, 0)
        return ("Ativo", pid, port)
    except OSError:
        # Se o processo não existe mais, limpa o arquivo de estado
        try: os.remove(STATE_FILE)
        except Exception: pass
        return ("Inativo", None, None)

def build_main_frame(status_msg=""):
    """Constrói a interface gráfica do menu."""
    s = []
    s.append(simple_header("GERENCIADOR PROXY WSS/SOCKS"))
    st, pid, port = check_status()
    if st == "Ativo":
        ip = get_ip_address()
        status_lines = [
            f"{MC.CYAN_LIGHT}{Icons.SERVER} Status:{MC.RESET} {MC.GREEN_GRADIENT}{Icons.ACTIVE} Ativo (PID: {pid}){MC.RESET}",
            f"{MC.CYAN_LIGHT}{Icons.NETWORK} Endereço:{MC.RESET} {MC.WHITE}{ip}:{port}{MC.RESET}",
        ]
    else:
        status_lines = [
            f"{MC.CYAN_LIGHT}{Icons.SERVER} Status:{MC.RESET} {MC.RED_GRADIENT}{Icons.INACTIVE} Inativo{MC.RESET}",
            # --- ALTERAÇÃO --- A informação foi atualizada para refletir a necessidade de SSL.
            f"{MC.CYAN_LIGHT}{Icons.INFO} Info:{MC.RESET} {MC.WHITE}Proxy WSS/SOCKS com SSL. Requer cert.pem e key.pem.{MC.RESET}",
        ]
    s.append(modern_box("STATUS DO SERVIÇO", status_lines, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    s.append(modern_box("OPÇÕES DISPONÍVEIS", [], Icons.SETTINGS, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    if st == "Ativo":
        s.append(menu_option("2", "Alterar Porta (reinicia)", Icons.EDIT, MC.CYAN_GRADIENT))
        s.append(menu_option("3", "Desativar / Parar Proxy", Icons.TRASH, MC.RED_GRADIENT))
    else:
        s.append(menu_option("1", "Instalar / Iniciar Proxy", Icons.DOWNLOAD, MC.GREEN_GRADIENT, badge="RECOMENDADO"))
    s.append("\n")
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

# --- FUNÇÃO CORRIGIDA ---
def start_proxy(port):
    """
    Inicia o script do proxy com os argumentos corretos, incluindo porta e certificados SSL.
    """
    if not os.path.exists(PROXY_SCRIPT_PATH):
        return False, f"Script não encontrado em {PROXY_SCRIPT_PATH}"
    
    # Define os caminhos esperados para os certificados no mesmo diretório do script do proxy.
    proxy_dir = os.path.dirname(PROXY_SCRIPT_PATH)
    cert_path = os.path.join(proxy_dir, 'cert.pem')
    key_path = os.path.join(proxy_dir, 'key.pem')

    # Verifica se os certificados existem antes de tentar iniciar.
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        error_msg = (
            "Erro: Arquivos 'cert.pem' e/ou 'key.pem' não encontrados. "
            f"Certifique-se de que eles existem em: {proxy_dir}"
        )
        return False, error_msg

    try:
        # Constrói o comando com os argumentos de opção corretos: -p, --cert, --key.
        command = [
            sys.executable,
            PROXY_SCRIPT_PATH,
            '-p', str(port),
            '--cert', cert_path,
            '--key', key_path
        ]
        
        # Inicia o processo do proxy em segundo plano.
        p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Salva o estado (PID e porta) para gerenciamento posterior.
        with open(STATE_FILE, 'w') as f:
            f.write(f"{p.pid}:{port}")
            
        return True, f"Proxy iniciado na porta {port} (PID {p.pid})"
    except Exception as e:
        return False, str(e)

def stop_proxy():
    """Para o processo do proxy usando o PID salvo no arquivo de estado."""
    st, pid, _ = check_status()
    if st != "Ativo":
        return True, "O proxy já está inativo"
    
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        # O processo pode já ter sido encerrado.
        pass
    
    try:
        # Limpa o arquivo de estado.
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception:
        pass
        
    return True, "Proxy parado com sucesso"

def main_menu():
    """Loop principal que gerencia a interação com o usuário."""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este script deve ser executado como root.{MC.RESET}")
        sys.exit(1)
        
    TerminalManager.enter_alt_screen()
    status = ""
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            
            if choice == "1":
                TerminalManager.before_input()
                port_input = input(f"\n{MC.CYAN_GRADIENT}Porta para iniciar (padrão 443): {MC.RESET}").strip()
                port = port_input or "443"
                TerminalManager.after_input()
                if port.isdigit() and 1 <= int(port) <= 65535:
                    ok, msg = start_proxy(int(port))
                    status = msg if ok else f"Erro: {msg}"
                else:
                    status = "Porta inválida"
            elif choice == "2":
                st, _, old_port = check_status()
                if st != "Ativo":
                    status = "Proxy não está ativo"
                else:
                    TerminalManager.before_input()
                    port_input = input(f"\n{MC.CYAN_GRADIENT}Nova porta (atual {old_port}): {MC.RESET}").strip()
                    TerminalManager.after_input()
                    if port_input.isdigit() and 1 <= int(port_input) <= 65535:
                        stop_proxy()
                        time.sleep(0.5) # Aguarda o sistema liberar a porta
                        ok, msg = start_proxy(int(port_input))
                        status = msg if ok else f"Erro: {msg}"
                    else:
                        status = "Porta inválida"
            elif choice == "3":
                ok, msg = stop_proxy()
                status = msg if ok else f"Erro: {msg}"
            elif choice == "0":
                break
            else:
                status = "Opção inválida"
            
            # Pequena pausa para o usuário ver a mensagem de status
            if status:
                TerminalManager.render(build_main_frame(status))
                time.sleep(1.5)

    finally:
        TerminalManager.leave_alt_screen()

if __name__ == '__main__':
    main_menu()
