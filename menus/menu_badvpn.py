#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
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
        # Define os caminhos para o script de instalação
        self.base_dir = Path(__file__).parent.parent
        self.executable_path = self.base_dir / 'conexoes' / 'badvpn.sh'

    def _check_badvpn_installed(self):
        """Verifica se o badvpn-udpgw está instalado."""
        return True

    def display_status(self):
        """Verifica o status do serviço BadVPN."""
        try:
            result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == "active":
                return f"{COLORS.GREEN}Ativo{COLORS.END}"
            else:
                return f"{COLORS.RED}Inativo{COLORS.END}"
        except:
            return f"{COLORS.RED}Inativo{COLORS.END}"

    def start_badvpn_port(self, port):
        """Inicia o serviço BadVPN numa porta."""
        # 1. Pré-verificações
        if not self._check_badvpn_installed():
            return False

        # 2. Executar o script de instalação/configuração
        try:
            print(f"{COLORS.YELLOW}Executando script de instalação/configuração do BadVPN...{COLORS.END}")
            result = subprocess.run(["sudo", "bash", str(self.executable_path), str(port)], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"{COLORS.GREEN}✓ Script executado com sucesso.{COLORS.END}")
                
                # 3. Verificar se o serviço está ativo
                status_result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], 
                                             capture_output=True, text=True)
                if status_result.returncode == 0 and status_result.stdout.strip() == "active":
                    print(f"{COLORS.GREEN}✓ Serviço BadVPN está ativo.{COLORS.END}")
                    return True
                else:
                    print(f"{COLORS.YELLOW}Script executado, mas serviço pode não estar ativo.{COLORS.END}")
                    return True
            else:
                print(f"{COLORS.RED}✗ Erro ao executar o script: {result.stderr}{COLORS.END}")
                return False
                
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao executar o script: {e}{COLORS.END}")
            return False

    def add_port(self):
        clear_screen()
        print_colored_box("INICIAR SERVIÇO EM NOVA PORTA")
        try:
            port = input(f"{COLORS.CYAN}Digite a nova porta a ser iniciada: {COLORS.END}").strip()
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                print(f"\n{COLORS.RED}✗ Porta inválida.{COLORS.END}")
                return
            self.start_badvpn_port(port)
        except KeyboardInterrupt:
            print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")

    def remove_port(self):
        clear_screen()
        print_colored_box("PARAR SERVIÇO BADVPN")
        try:
            result = subprocess.run(["sudo", "systemctl", "stop", "badvpn-udpgw"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"{COLORS.GREEN}✓ Serviço BadVPN parado com sucesso.{COLORS.END}")
            else:
                print(f"{COLORS.RED}✗ Erro ao parar o serviço: {result.stderr}{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao parar o serviço: {e}{COLORS.END}")

    def stop_all_services(self):
        clear_screen()
        print_colored_box("PARAR SERVIÇO BADVPN")
        confirm = input(f"{COLORS.YELLOW}Deseja parar o serviço BadVPN? (s/N): {COLORS.END}").lower()
        if confirm not in ['s', 'sim']:
            print("Operação cancelada.")
            return

        try:
            result = subprocess.run(["sudo", "systemctl", "stop", "badvpn-udpgw"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"{COLORS.GREEN}✓ Serviço BadVPN parado com sucesso.{COLORS.END}")
            else:
                print(f"{COLORS.RED}✗ Erro ao parar o serviço: {result.stderr}{COLORS.END}")
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao parar o serviço: {e}{COLORS.END}")

def main_menu():
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.display_status()
            print_colored_box("GERENCIADOR BADVPN", [f"Status: {status_line}"])
            
            print_menu_option("1", "Iniciar/Configurar BadVPN", color=COLORS.CYAN)
            print_menu_option("2", "Parar Serviço BadVPN", color=COLORS.CYAN)
            print_menu_option("3", "Parar Serviço BadVPN", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1': manager.add_port()
            elif choice == '2': manager.remove_port()
            elif choice == '3': manager.stop_all_services()
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

