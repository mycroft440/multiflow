#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import re
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
        # Define os caminhos de forma robusta
        self.base_dir = Path(__file__).parent.parent
        self.install_script_path = self.base_dir / 'conexoes' / 'badvpn.sh'
        self.service_file_path = Path("/etc/systemd/system/badvpn-udpgw.service")

    def _is_installed(self):
        """Verifica se o serviço BadVPN parece estar instalado."""
        return self.service_file_path.exists()

    def _run_command_interactive(self, command):
        """Executa um comando e mostra sua saída em tempo real."""
        try:
            # Usa Popen para ter controle sobre o processo e exibir a saída
            process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, text=True)
            process.wait()
            return process.returncode == 0
        except FileNotFoundError:
            print(f"\n{COLORS.RED}Erro: Comando '{command[0]}' não encontrado.{COLORS.END}")
            return False
        except Exception as e:
            print(f"\n{COLORS.RED}Ocorreu um erro inesperado: {e}{COLORS.END}")
            return False

    def get_status(self):
        """Verifica o status do serviço e a porta configurada."""
        if not self._is_installed():
            return f"{COLORS.YELLOW}Não Instalado{COLORS.END}"

        try:
            # Verifica se o serviço está ativo
            result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True)
            status = f"{COLORS.GREEN}Ativo{COLORS.END}" if result.stdout.strip() == "active" else f"{COLORS.RED}Inativo{COLORS.END}"

            # Tenta ler a porta do arquivo de serviço
            port = "N/A"
            with self.service_file_path.open('r') as f:
                content = f.read()
                match = re.search(r'--listen-addr 127.0.0.1:(\d+)', content)
                if match:
                    port = match.group(1)
            
            return f"{status} | Porta: {COLORS.CYAN}{port}{COLORS.END}"

        except Exception:
            return f"{COLORS.RED}Erro ao obter status{COLORS.END}"

    def install_or_change_port(self):
        """Instala o BadVPN ou altera a porta se já estiver instalado."""
        clear_screen()
        action = "Alterar Porta" if self._is_installed() else "Instalar"
        print_colored_box(f"{action.upper()} BADVPN")
        
        try:
            port = input(f"{COLORS.CYAN}Digite a porta para o BadVPN (ex: 7300): {COLORS.END}").strip()
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                print(f"\n{COLORS.RED}✗ Porta inválida. Tente novamente.{COLORS.END}")
                return

            print(f"\n{COLORS.YELLOW}Executando script de configuração... Acompanhe a saída abaixo.{COLORS.END}")
            print("-" * 60)
            
            command = ["sudo", "bash", str(self.install_script_path), port]
            success = self._run_command_interactive(command)
            
            print("-" * 60)
            if success:
                print(f"\n{COLORS.GREEN}✓ Operação concluída com sucesso!{COLORS.END}")
            else:
                print(f"\n{COLORS.RED}✗ A operação encontrou um erro.{COLORS.END}")

        except KeyboardInterrupt:
            print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")

    def _control_service(self, action):
        """Função auxiliar para iniciar, parar ou reiniciar o serviço."""
        if not self._is_installed():
            print(f"\n{COLORS.YELLOW}BadVPN não está instalado. Instale primeiro.{COLORS.END}")
            return

        clear_screen()
        print_colored_box(f"{action.upper()} SERVIÇO BADVPN")
        command = ["sudo", "systemctl", action, "badvpn-udpgw.service"]
        self._run_command_interactive(command)
        # Adiciona uma verificação de status após a ação
        subprocess.run(["sudo", "systemctl", "status", "badvpn-udpgw.service", "--no-pager"], check=False)

def main_menu():
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.get_status()
            print_colored_box("GERENCIADOR BADVPN", [f"Status: {status_line}"])
            
            print_menu_option("1", "Instalar / Alterar Porta", color=COLORS.CYAN)
            print_menu_option("2", "Iniciar Serviço", color=COLORS.GREEN)
            print_menu_option("3", "Parar Serviço", color=COLORS.RED)
            print_menu_option("4", "Reiniciar Serviço", color=COLORS.YELLOW)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1': manager.install_or_change_port()
            elif choice == '2': manager._control_service('start')
            elif choice == '3': manager._control_service('stop')
            elif choice == '4': manager._control_service('restart')
            elif choice == '0': break
            else: print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"\n{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
