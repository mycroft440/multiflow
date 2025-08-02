#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import psutil
import re
import time
import json
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
# Arquivo para armazenar o estado dos processos (PID e porta)
STATE_FILE = "/tmp/badvpn_pids.json"

class BadVPNManager:
    def __init__(self):
        # O script a ser gerenciado é o script Python
        script_dir = os.path.dirname(__file__)
        self.badvpn_script_path = os.path.join(script_dir, '..', 'conexoes', 'badvpn.py')

    def _load_state(self):
        """Carrega o estado (portas e PIDs) do arquivo JSON."""
        if not os.path.exists(STATE_FILE):
            return {}
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_state(self, state):
        """Salva o estado no arquivo JSON."""
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)

    def _cleanup_stale_pids(self):
        """Verifica e remove PIDs de processos que não existem mais."""
        state = self._load_state()
        active_state = {}
        for port, pid in state.items():
            if psutil.pid_exists(pid):
                active_state[port] = pid
        if len(active_state) != len(state):
            self._save_state(active_state)

    def get_active_ports(self):
        """Obtém as portas ativas a partir do arquivo de estado."""
        self._cleanup_stale_pids()
        state = self._load_state()
        return list(state.keys())

    def display_status(self):
        """Retorna uma string formatada com o status atual do BadVPN."""
        active_ports = self.get_active_ports()
        is_running = len(active_ports) > 0

        status_color = COLORS.GREEN if is_running else COLORS.RED
        status_text = f"{status_color}{'Ativo' if is_running else 'Inativo'}{COLORS.END}"

        if active_ports:
            ports_text = f"Portas: {COLORS.YELLOW}{', '.join(sorted(active_ports))}{COLORS.END}"
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

        if '7300' in self.get_active_ports():
            print(f"{COLORS.YELLOW}O serviço BadVPN já está em execução na porta 7300.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Iniciando BadVPN na porta padrão 7300...{COLORS.END}")
        if self.start_badvpn_port('7300'):
            print(f"{COLORS.GREEN}✓ Serviço BadVPN iniciado com sucesso na porta 7300.{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ Falha ao iniciar o serviço.{COLORS.END}")

    def start_badvpn_port(self, port):
        """Inicia o script BadVPN em uma porta específica e salva seu PID."""
        if str(port) in self.get_active_ports():
            print(f"{COLORS.YELLOW}Serviço BadVPN já está rodando na porta {port}.{COLORS.END}")
            return True

        try:
            cmd = ['sudo', sys.executable, self.badvpn_script_path, str(port)]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            time.sleep(0.5) # Dá um tempo para o processo iniciar
            
            state = self._load_state()
            state[str(port)] = process.pid
            self._save_state(state)
            
            print(f"{COLORS.GREEN}✓ Serviço BadVPN iniciado na porta {port} (PID: {process.pid}).{COLORS.END}")
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

    def remove_port(self):
        """Para um processo BadVPN em uma porta específica usando seu PID."""
        clear_screen()
        print_colored_box("PARAR SERVIÇO POR PORTA")
        active_ports = self.get_active_ports()
        if not active_ports:
            print(f"{COLORS.YELLOW}Nenhum serviço BadVPN ativo encontrado.{COLORS.END}")
            return
        
        print(f"Portas ativas: {COLORS.YELLOW}{', '.join(sorted(active_ports))}{COLORS.END}")
        try:
            port_to_remove = input(f"{COLORS.CYAN}Digite a porta do serviço a ser parado: {COLORS.END}").strip()
            state = self._load_state()
            
            pid_to_kill = state.get(port_to_remove)
            if not pid_to_kill:
                print(f"\n{COLORS.RED}✗ Nenhum serviço encontrado na porta {port_to_remove}.{COLORS.END}")
                return
            
            try:
                proc = psutil.Process(pid_to_kill)
                proc.kill()
                print(f"\n{COLORS.GREEN}✓ Serviço na porta {port_to_remove} (PID: {pid_to_kill}) parado com sucesso.{COLORS.END}")
            except psutil.NoSuchProcess:
                print(f"\n{COLORS.YELLOW}Processo com PID {pid_to_kill} não encontrado. Já pode ter sido finalizado.{COLORS.END}")
            
            # Remove a entrada do estado independentemente do resultado
            state.pop(port_to_remove, None)
            self._save_state(state)

        except KeyboardInterrupt:
            print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")

    def stop_all_services(self):
        """Para todos os serviços BadVPN em execução."""
        clear_screen()
        print_colored_box("PARAR TODOS OS SERVIÇOS BADVPN")
        state = self._load_state()
        if not state:
            print(f"{COLORS.YELLOW}Nenhum serviço BadVPN ativo para parar.{COLORS.END}")
            return

        confirm = input(f"{COLORS.YELLOW}Tem certeza que deseja parar todos os {len(state)} serviços BadVPN? (s/N): {COLORS.END}").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return

        print(f"{COLORS.YELLOW}Parando todos os processos do serviço BadVPN...{COLORS.END}")
        killed_processes = 0
        for port, pid in state.items():
            try:
                proc = psutil.Process(pid)
                proc.kill()
                killed_processes += 1
            except psutil.NoSuchProcess:
                # O processo já não existe, o que é bom
                pass
        
        # Limpa o arquivo de estado
        self._save_state({})
        print(f"\n{COLORS.GREEN}✓ Operação concluída. {killed_processes} processos finalizados.{COLORS.END}")

# CORREÇÃO: Função principal que será chamada pelo multiflow.py
def main_menu():
    """Função de entrada para o menu do BadVPN."""
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
