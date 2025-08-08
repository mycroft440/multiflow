#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import re
import time
from pathlib import Path

# Adiciona o diretório pai ao sys.path para permitir importações de outros módulos do projeto
sys.path.append(str(Path(__file__).parent.parent))

try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
    from ferramentas import bbr_manager
except ImportError as e:
    print(f"Erro de importação: {e}. Verifique se todos os arquivos do projeto estão nos diretórios corretos.")
    # Fallback para o caso de o script ser executado de forma isolada
    class Colors:
        RED = GREEN = YELLOW = CYAN = BOLD = END = ""
    class BoxChars:
        BOTTOM_LEFT = BOTTOM_RIGHT = HORIZONTAL = ""
    def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')
    def print_colored_box(title, content=None): print(f"--- {title} ---")
    def print_menu_option(num, desc, **kwargs): print(f"{num}. {desc}")
    # Se o bbr_manager falhar, criamos um dummy
    class bbr_manager:
        @staticmethod
        def check_status(): return "erro"
        @staticmethod
        def is_bbr_persistent(): return False
        @staticmethod
        def enable(): return False, "Módulo bbr_manager não encontrado."
        @staticmethod
        def disable(): return False, "Módulo bbr_manager não encontrado."


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
        """Verifica o status do serviço, a porta e o status do BBR."""
        # Status do Serviço BadVPN
        if not self._is_installed():
            service_status = f"{COLORS.YELLOW}Não Instalado{COLORS.END}"
            port = "N/A"
        else:
            try:
                result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True, check=False)
                status = f"{COLORS.GREEN}Ativo{COLORS.END}" if result.stdout.strip() == "active" else f"{COLORS.RED}Inativo{COLORS.END}"
                service_status = status
                port = "N/A"
                with self.service_file_path.open('r') as f:
                    content = f.read()
                    match = re.search(r'--listen-addr 127.0.0.1:(\d+)', content)
                    if match:
                        port = match.group(1)
            except Exception:
                service_status = f"{COLORS.RED}Erro ao obter status{COLORS.END}"
                port = "N/A"

        # Status do BBR
        bbr_raw_status = bbr_manager.check_status()
        bbr_status = f"{COLORS.GREEN}Ativo ({bbr_raw_status}){COLORS.END}" if bbr_raw_status == 'bbr' else f"{COLORS.YELLOW}Inativo ({bbr_raw_status}){COLORS.END}"

        return f"Serviço: {service_status} | Porta: {COLORS.CYAN}{port}{COLORS.END}", f"Otimização BBR: {bbr_status}"

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

    def manage_bbr(self):
        """Menu para gerenciar a otimização BBR."""
        while True:
            clear_screen()
            bbr_status = bbr_manager.check_status()
            is_persistent = bbr_manager.is_bbr_persistent()
            
            status_line = f"{COLORS.GREEN}Ativo ({bbr_status}){COLORS.END}" if bbr_status == 'bbr' else f"{COLORS.YELLOW}Inativo ({bbr_status}){COLORS.END}"
            persistence_line = f"Persistente ao Reiniciar: {COLORS.CYAN}{'Sim' if is_persistent else 'Não'}{COLORS.END}"

            print_colored_box("GERENCIAR OTIMIZAÇÃO TCP BBR", [status_line, persistence_line])
            
            print_menu_option("1", "Ativar BBR", color=COLORS.GREEN)
            print_menu_option("2", "Desativar BBR", color=COLORS.RED)
            print_menu_option("0", "Voltar", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()

            if choice == '1':
                success, msg = bbr_manager.enable()
                if success:
                    print(f"\n{COLORS.GREEN}✓ {msg}{COLORS.END}")
                else:
                    print(f"\n{COLORS.RED}✗ {msg}{COLORS.END}")
                input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            elif choice == '2':
                success, msg = bbr_manager.disable()
                if success:
                    print(f"\n{COLORS.GREEN}✓ {msg}{COLORS.END}")
                else:
                    print(f"\n{COLORS.RED}✗ {msg}{COLORS.END}")
                input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            elif choice == '0':
                break
            else:
                print(f"\n{COLORS.RED}Opção inválida.{COLORS.END}")
                time.sleep(1)

def main_menu():
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            service_status_line, bbr_status_line = manager.get_status()
            print_colored_box("GERENCIADOR BADVPN", [service_status_line, bbr_status_line])
            
            print_menu_option("1", "Instalar / Alterar Porta", color=COLORS.CYAN)
            print_menu_option("2", "Iniciar Serviço", color=COLORS.GREEN)
            print_menu_option("3", "Parar Serviço", color=COLORS.RED)
            print_menu_option("4", "Reiniciar Serviço", color=COLORS.YELLOW)
            print_menu_option("5", "Gerenciar Otimização BBR", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1': manager.install_or_change_port()
            elif choice == '2': manager._control_service('start')
            elif choice == '3': manager._control_service('stop')
            elif choice == '4': manager._control_service('restart')
            elif choice == '5': manager.manage_bbr()
            elif choice == '0': break
            else: print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"\n{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{END}")

if __name__ == "__main__":
    main_menu()
