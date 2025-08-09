#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import signal
import time
import socket

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

PROXY_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'conexoes', 'proxysocks.py')
STATE_FILE = "/tmp/proxy.state"

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1)); IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_status():
    if not os.path.exists(STATE_FILE):
        return ("Inativo", None, None)
    try:
        with open(STATE_FILE, 'r') as f:
            pid_s, port_s = f.read().strip().split(':')
        pid = int(pid_s); port=int(port_s)
    except Exception:
        try: os.remove(STATE_FILE)
        except Exception: pass
        return ("Inativo", None, None)
    try:
        os.kill(pid, 0)
        return ("Ativo", pid, port)
    except OSError:
        try: os.remove(STATE_FILE)
        except Exception: pass
        return ("Inativo", None, None)

def build_main_frame(status_msg=""):
    s=[]
    s.append(simple_header("GERENCIADOR PROXY SOCKS (SIMPLIFICADO)"))
    st, pid, port = check_status()
    if st=="Ativo":
        ip = get_ip_address()
        status_lines = [
            f"{MC.CYAN_LIGHT}{Icons.SERVER} Status:{MC.RESET} {MC.GREEN_GRADIENT}{Icons.ACTIVE} Ativo (PID: {pid}){MC.RESET}",
            f"{MC.CYAN_LIGHT}{Icons.NETWORK} Endereço:{MC.RESET} {MC.WHITE}{ip}:{port}{MC.RESET}",
        ]
    else:
        status_lines = [
            f"{MC.CYAN_LIGHT}{Icons.SERVER} Status:{MC.RESET} {MC.RED_GRADIENT}{Icons.INACTIVE} Inativo{MC.RESET}",
            f"{MC.CYAN_LIGHT}{Icons.INFO} Info:{MC.RESET} {MC.WHITE}Proxy simples em Python (sem autenticação){MC.RESET}",
        ]
    s.append(modern_box("STATUS DO SERVIÇO", status_lines, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    s.append(modern_box("OPÇÕES DISPONÍVEIS", [], Icons.SETTINGS, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    if st=="Ativo":
        s.append(menu_option("2", "Alterar Porta (reinicia)", Icons.EDIT, MC.CYAN_GRADIENT))
        s.append(menu_option("3", "Desativar / Parar Proxy", Icons.TRASH, MC.RED_GRADIENT))
    else:
        s.append(menu_option("1", "Instalar / Iniciar Proxy", Icons.DOWNLOAD, MC.GREEN_GRADIENT, badge="RECOMENDADO"))
    s.append("\n")
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def start_proxy(port):
    if not os.path.exists(PROXY_SCRIPT_PATH):
        return False, f"Script não encontrado em {PROXY_SCRIPT_PATH}"
    try:
        p = subprocess.Popen([sys.executable, PROXY_SCRIPT_PATH, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(STATE_FILE, 'w') as f:
            f.write(f"{p.pid}:{port}")
        return True, f"Iniciado na porta {port} (PID {p.pid})"
    except Exception as e:
        return False, str(e)

def stop_proxy():
    st, pid, _ = check_status()
    if st!="Ativo":
        return True, "Já está inativo"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    except Exception:
        pass
    return True, "Parado com sucesso"

def main_menu():
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este script deve ser executado como root.{MC.RESET}")
        sys.exit(1)
    TerminalManager.enter_alt_screen()
    status=""
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            if choice == "1":
                TerminalManager.before_input()
                port = input(f"\n{MC.CYAN_GRADIENT}Porta para iniciar (padrão 80): {MC.RESET}").strip() or "80"
                TerminalManager.after_input()
                if port.isdigit() and 1<=int(port)<=65535:
                    ok,msg = start_proxy(int(port)); status = msg if ok else f"Erro: {msg}"
                else:
                    status = "Porta inválida"
            elif choice == "2":
                st, _, old_port = check_status()
                if st!="Ativo":
                    status="Proxy não está ativo"
                else:
                    TerminalManager.before_input()
                    port = input(f"\n{MC.CYAN_GRADIENT}Nova porta (atual {old_port}): {MC.RESET}").strip()
                    TerminalManager.after_input()
                    if port.isdigit() and 1<=int(port)<=65535:
                        stop_proxy(); time.sleep(0.5); ok,msg = start_proxy(int(port)); status = msg if ok else f"Erro: {msg}"
                    else:
                        status="Porta inválida"
            elif choice == "3":
                ok,msg = stop_proxy(); status = msg if ok else f"Erro: {msg}"
            elif choice == "0":
                break
            else:
                status="Opção inválida"
            time.sleep(0.5)
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == '__main__':
    main_menu()
