#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import psutil
import re
import time
from pathlib import Path

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

class BadVPNManager:
    def __init__(self):
        # O script a ser gerenciado é o script Python, apesar da extensão .c
        script_dir = os.path.dirname(__file__)
        self.badvpn_script_path = os.path.join(script_dir, '..', 'conexoes', 'badvpn.c')

    def _get_badvpn_processes(self):
        """Helper para encontrar todos os processos python do 'badvpn.c' em execução."""
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Verifica se é um processo python executando o script 'badvpn.c'
                if proc.info['cmdline'] and 'python' in proc.info['name'] and self.badvpn_script_path in proc.info['cmdline']:
                    procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return procs

    def check_badvpn_status(self):
        """Verifica se algum processo do BadVPN (script python) está rodando."""
        return len(self._get_badvpn_processes()) > 0

    def get_active_ports(self):
        """Obtém as portas ativas dos scripts em execução."""
        active_ports = []
        procs = self._get_badvpn_processes()
        for proc in procs:
            try:
                # O último argumento da linha de comando deve ser a porta
                if len(proc.info['cmdline']) > 1 and proc.info['cmdline'][-1].isdigit():
                    active_ports.append(proc.info['cmdline'][-1])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return active_ports

    def display_status(self):
        """Retorna uma string formatada com o status atual do BadVPN."""
        is_running = self.check_badvpn_status()
        active_ports = self.get_active_ports()

        status_color = COLORS.GREEN if is_running else COLORS.RED
        status_text = f"{status_color}{'Ativo' if is_running else 'Inativo'}{COLORS.END}"

        if active_ports:
            ports_text = f"Portas: {COLORS.YELLOW}{', '.join(active_ports)}{COLORS.END}"
            return f"{status_text}, {ports_text}"
        return status_text

    def start_service_default(self):
        """Inicia o serviço BadVPN na porta padrão 7300."""
        clear_screen()
        print_colored_box("INICIAR SERVIÇO BADVPN")
        if not os.path.exists(self.badvpn_script_path):
            print(f"{COLORS.RED}✗ Erro: Script '{os.path.basename(self.badvpn_script_path)}' não encontrado.{COLORS.END}")
            print(f"{COLORS.YELLOW}Caminho esperado: {self.badvpn_script_path}{COLORS.END}")
            return

        if self.check_badvpn_status():
            print(f"{COLORS.YELLOW}O serviço BadVPN já está em execução.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Iniciando BadVPN na porta padrão 7300...{COLORS.END}")
        if self.start_badvpn_port('7300'):
            print(f"{COLORS.GREEN}✓ Serviço BadVPN iniciado com sucesso na porta 7300.{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ Falha ao iniciar o serviço.{COLORS.END}")

    def start_badvpn_port(self, port):
        """Inicia o script BadVPN em uma porta específica."""
        if str(port) in self.get_active_ports():
            print(f"{COLORS.YELLOW}Serviço BadVPN já está rodando na porta {port}.{COLORS.END}")
            return True

        try:
            # Usa sys.executable para garantir que está usando o mesmo interpretador python
            cmd = ['sudo', sys.executable, self.badvpn_script_path, str(port)]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Pequena pausa para dar tempo ao processo de iniciar
            time.sleep(0.5)
            print(f"{COLORS.GREEN}✓ Serviço BadVPN iniciado na porta {port}.{COLORS.END}")
            return True
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao iniciar o serviço na porta {port}: {e}{COLORS.END}")
            return False

    def add_port(self):
        """Adiciona uma nova porta ao BadVPN."""
        clear_screen()
        print_colored_box("INICIAR SERVIÇO EM NOVA PORTA")
        try:
            port = input(f"{COLORS.CYAN}Digite a nova porta a ser iniciada: {COLORS.END}").strip()
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                print(f"\n{COLORS.RED}✗ Porta inválida. Deve ser um número entre 1 e 65535.{COLORS.END}")
                return
            
            if not self.start_badvpn_port(port):
                print(f"\n{COLORS.RED}✗ Falha ao iniciar serviço na porta {port}.{COLORS.END}")

        except KeyboardInterrupt:
            print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")
        except Exception as e:
            print(f"\n{COLORS.RED}✗ Erro ao adicionar porta: {e}{COLORS.END}")

    def remove_port(self):
        """Para um processo BadVPN em uma porta específica."""
        clear_screen()
        print_colored_box("PARAR SERVIÇO POR PORTA")
        active_ports = self.get_active_ports()
        if not active_ports:
            print(f"{COLORS.YELLOW}Nenhum serviço BadVPN ativo encontrado.{COLORS.END}")
            return
        
        print(f"Portas ativas: {COLORS.YELLOW}{', '.join(active_ports)}{COLORS.END}")
        try:
            port_to_remove = input(f"{COLORS.CYAN}Digite a porta do serviço a ser parado: {COLORS.END}").strip()
            if port_to_remove not in active_ports:
                print(f"\n{COLORS.RED}✗ Nenhum serviço encontrado na porta {port_to_remove}.{COLORS.END}")
                return
            
            killed = False
            procs = self._get_badvpn_processes()
            for proc in procs:
                if len(proc.info['cmdline']) > 1 and port_to_remove == proc.info['cmdline'][-1]:
                    proc.kill()
                    killed = True
                    print(f"\n{COLORS.GREEN}✓ Serviço na porta {port_to_remove} parado com sucesso.{COLORS.END}")
                    break
            
            if not killed:
                print(f"\n{COLORS.RED}✗ Não foi possível parar o serviço na porta {port_to_remove}.{COLORS.END}")

        except KeyboardInterrupt:
            print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")
        except Exception as e:
            print(f"\n{COLORS.RED}✗ Erro ao parar serviço: {e}{COLORS.END}")

    def stop_all_services(self):
        """Para todos os serviços BadVPN em execução."""
        clear_screen()
        print_colored_box("PARAR TODOS OS SERVIÇOS BADVPN")
        confirm = input(f"{COLORS.YELLOW}Tem certeza que deseja parar todos os serviços BadVPN? (s/N): {COLORS.END}").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return

        print(f"{COLORS.YELLOW}Parando todos os processos do serviço BadVPN...{COLORS.END}")
        killed_processes = 0
        procs = self._get_badvpn_processes()
        for proc in procs:
            try:
                proc.kill()
                killed_processes += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        print(f"\n{COLORS.GREEN}✓ Operação concluída. {killed_processes} processos finalizados.{COLORS.END}")

def main_menu():
    """Menu principal do BadVPN."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.display_status()
            print_colored_box("GERENCIADOR BADVPN", [f"Status: {status_line}"])
            
            print_menu_option("1", "Iniciar Serviço (porta padrão 7300)", color=COLORS.CYAN)
            print_menu_option("2", "Iniciar em Nova Porta", color=COLORS.CYAN) 
            print_menu_option("3", "Parar Serviço por Porta", color=COLORS.CYAN)
            print_menu_option("4", "Parar Todos os Serviços", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1':
                manager.start_service_default()
            elif choice == '2':
                manager.add_port()
            elif choice == '3':
                manager.remove_port()
            elif choice == '4':
                manager.stop_all_services()
            elif choice == '0':
                break
            else:
                print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"\n{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
