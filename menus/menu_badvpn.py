#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import psutil
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
        # Define os caminhos para o código-fonte C e para o binário compilado
        self.base_dir = Path(__file__).parent.parent
        self.c_source_path = self.base_dir / 'conexoes' / 'badvpn.c'
        self.executable_path = self.base_dir / 'conexoes' / 'badvpn_wrapper'

    def _compile_c_wrapper(self):
        """Compila o wrapper C se o binário não existir ou estiver desatualizado."""
        try:
            if self.executable_path.exists() and self.executable_path.stat().st_mtime > self.c_source_path.stat().st_mtime:
                return True, "Binário já está atualizado."

            print(f"{COLORS.YELLOW}Compilando o wrapper C do BadVPN...{COLORS.END}")
            if subprocess.run(['which', 'gcc'], capture_output=True).returncode != 0:
                return False, "Erro: Compilador 'gcc' não encontrado. Instale o pacote 'build-essential'."

            compile_cmd = ['gcc', str(self.c_source_path), '-o', str(self.executable_path)]
            result = subprocess.run(compile_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                error_msg = f"Falha na compilação: {result.stderr}"
                print(f"{COLORS.RED}{error_msg}{COLORS.END}")
                return False, error_msg

            print(f"{COLORS.GREEN}✓ Compilação concluída com sucesso.{COLORS.END}")
            return True, "Compilado com sucesso."
        except Exception as e:
            return False, f"Erro inesperado durante a compilação: {e}"

    def _load_state(self):
        if not os.path.exists(STATE_FILE): return {}
        try:
            with open(STATE_FILE, 'r') as f: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}

    def _save_state(self, state):
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=4)

    def _cleanup_stale_pids(self):
        state = self._load_state()
        active_state = {port: pid for port, pid in state.items() if psutil.pid_exists(pid)}
        if len(active_state) != len(state): self._save_state(active_state)

    def get_active_ports(self):
        self._cleanup_stale_pids()
        return list(self._load_state().keys())

    def display_status(self):
        active_ports = self.get_active_ports()
        is_running = len(active_ports) > 0
        status_color = COLORS.GREEN if is_running else COLORS.RED
        status_text = f"{status_color}{'Ativo' if is_running else 'Inativo'}{COLORS.END}"
        if active_ports:
            ports_text = f"Portas: {COLORS.YELLOW}{', '.join(sorted(active_ports))}{COLORS.END}"
            return f"{status_text}, {ports_text}"
        return status_text

    def start_badvpn_port(self, port):
        """Compila e inicia o wrapper C do BadVPN em uma porta específica."""
        success, message = self._compile_c_wrapper()
        if not success:
            print(f"{COLORS.RED}Não foi possível iniciar o serviço: {message}{COLORS.END}")
            return False

        if str(port) in self.get_active_ports():
            print(f"{COLORS.YELLOW}Serviço BadVPN já está rodando na porta {port}.{COLORS.END}")
            return True

        try:
            cmd = ['sudo', str(self.executable_path), str(port)]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)

            if process.poll() is not None:
                print(f"{COLORS.RED}✗ O processo do wrapper C terminou inesperadamente.{COLORS.END}")
                print(f"{COLORS.YELLOW}Verifique os logs com 'journalctl -t {LOG_IDENTITY}' ou 'grep {LOG_IDENTITY} /var/log/syslog'.{COLORS.END}")
                print(f"{COLORS.YELLOW}Causas comuns: 'badvpn-udpgw' não instalado ou permissões incorretas em /var/run/.{COLORS.END}")
                return False

            state = self._load_state()
            state[str(port)] = process.pid
            self._save_state(state)
            print(f"{COLORS.GREEN}✓ Wrapper BadVPN iniciado para a porta {port} (PID: {process.pid}).{COLORS.END}")
            return True
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao executar o wrapper C na porta {port}: {e}{COLORS.END}")
            return False

    def add_port(self):
        clear_screen()
        print_colored_box("INICIAR SERVIÇO EM NOVA PORTA")
        try:
            port = input(f"{COLORS.CYAN}Digite a nova porta a ser iniciada: {COLORS.END}").strip()
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                print(f"\n{COLORS.RED}✗ Porta inválida.{COLORS.END}")
                return
            if not self.start_badvpn_port(port):
                print(f"\n{COLORS.RED}✗ Falha ao iniciar serviço na porta {port}.{COLORS.END}")
        except KeyboardInterrupt: print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")

    def remove_port(self):
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
                # Envia o sinal SIGTERM para o processo wrapper C
                # O wrapper C irá então encerrar o processo filho e limpar o arquivo PID
                proc = psutil.Process(pid_to_kill)
                proc.terminate() # Usar terminate (SIGTERM) para acionar o handle_signal no C
                print(f"\n{COLORS.GREEN}✓ Sinal de término enviado ao serviço na porta {port_to_remove} (PID: {pid_to_kill}).{COLORS.END}")
            except psutil.NoSuchProcess:
                print(f"\n{COLORS.YELLOW}Processo com PID {pid_to_kill} não encontrado.{COLORS.END}")
            
            state.pop(port_to_remove, None)
            self._save_state(state)
        except KeyboardInterrupt: print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")

    def stop_all_services(self):
        clear_screen()
        print_colored_box("PARAR TODOS OS SERVIÇOS BADVPN")
        state = self._load_state()
        if not state:
            print(f"{COLORS.YELLOW}Nenhum serviço BadVPN ativo para parar.{COLORS.END}")
            return

        confirm = input(f"{COLORS.YELLOW}Deseja parar todos os {len(state)} serviços? (s/N): {COLORS.END}").lower()
        if confirm not in ['s', 'sim']:
            print("Operação cancelada.")
            return

        print(f"{COLORS.YELLOW}Parando todos os processos...{COLORS.END}")
        for port, pid in list(state.items()): # Usar list() para poder modificar o dict no loop
            try:
                proc = psutil.Process(pid)
                proc.terminate()
            except psutil.NoSuchProcess: pass
        
        self._save_state({})
        print(f"\n{COLORS.GREEN}✓ Operação concluída.{COLORS.END}")

def main_menu():
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.display_status()
            print_colored_box("GERENCIADOR BADVPN (C)", [f"Status: {status_line}"])
            
            print_menu_option("1", "Iniciar/Adicionar Porta", color=COLORS.CYAN)
            print_menu_option("2", "Parar Serviço por Porta", color=COLORS.CYAN)
            print_menu_option("3", "Parar Todos os Serviços", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1': manager.add_port()
            elif choice == '2': manager.remove_port()
            elif choice == '3': manager.stop_all_services()
            elif choice == '0': break
            else: print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            
        except KeyboardInterrupt: print("\n\nSaindo..."); break
        except Exception as e:
            print(f"\n{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
