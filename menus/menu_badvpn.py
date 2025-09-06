#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import re
import time
import shutil
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

try:
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
    from ferramentas import bbr_manager
except ImportError as e:
    print(f"Erro de importação: {e}")
    sys.exit(1)

# ==================== GERENCIADOR BADVPN ====================
class BadVPNManager:
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.install_script = self.base_dir / 'conexoes' / 'badvpn.sh'
        self.service_file = Path("/etc/systemd/system/badvpn-udpgw.service")
        self.optimizations_file = Path("/etc/sysctl.d/99-badvpn-optimizations.conf")
        self.binary_path = Path("/usr/local/bin/badvpn-udpgw")
        self.build_dir = self.base_dir / 'badvpn'

    def is_installed(self):
        return self.service_file.exists()

    def get_status(self):
        """Retorna status formatado do BadVPN"""
        if not self.is_installed():
            return f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Não Instalado{MC.RESET}", "N/A"
        
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "badvpn-udpgw"],
                capture_output=True, text=True, check=False
            )
            
            if result.stdout.strip() == "active":
                status = f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} Ativo{MC.RESET}"
            else:
                status = f"{MC.RED_GRADIENT}{Icons.INACTIVE} Inativo{MC.RESET}"
            
            # Obtém porta (regex genérico para qualquer IP, ex: 0.0.0.0 ou 127.0.0.1)
            port = "7300"  # default
            with self.service_file.open('r') as f:
                content = f.read()
                match = re.search(r'--listen-addr [^:]+:(\d+)', content)
                if match:
                    port = match.group(1)
            
            return status, port
        except Exception as e:
            print(f"Erro ao obter status: {e}", file=sys.stderr)  # Log para debug
            return f"{MC.RED_GRADIENT}{Icons.CROSS} Erro{MC.RESET}", "N/A"
    
    def get_bbr_status(self):
        """Retorna status do BBR"""
        bbr = bbr_manager.check_status()
        if bbr == 'bbr':
            return f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} BBR Ativo{MC.RESET}"
        else:
            return f"{MC.YELLOW_GRADIENT}{Icons.INACTIVE} BBR Inativo ({bbr}){MC.RESET}"

    def uninstall(self):
        """Desinstala o BadVPN completamente do sistema."""
        try:
            print("--- [Iniciando a remoção do Badvpn-udpgw] ---")

            # Parar e desabilitar o serviço
            print("--> Parando e desabilitando o serviço systemd...")
            subprocess.run(['systemctl', 'stop', 'badvpn-udpgw.service'], capture_output=True, text=True)
            subprocess.run(['systemctl', 'disable', 'badvpn-udpgw.service'], capture_output=True, text=True)

            # Remover o arquivo de serviço
            if self.service_file.exists():
                print("--> Removendo o arquivo de serviço...")
                self.service_file.unlink()
                subprocess.run(['systemctl', 'daemon-reload'], check=True)
                subprocess.run(['systemctl', 'reset-failed'], check=True)
            else:
                print("--> Arquivo de serviço não encontrado.")

            # Remover o binário
            if self.binary_path.exists():
                print("--> Removendo o binário...")
                self.binary_path.unlink()
            else:
                print("--> Binário não encontrado.")

            # Remover o diretório de compilação
            if self.build_dir.exists() and self.build_dir.is_dir():
                print(f"--> Removendo o diretório de compilação '{self.build_dir}'...")
                shutil.rmtree(self.build_dir, ignore_errors=True)
            else:
                print(f"--> Diretório de compilação '{self.build_dir}' não encontrado.")

            # Remover o arquivo de otimização do kernel
            if self.optimizations_file.exists():
                print("--> Removendo otimizações de kernel...")
                self.optimizations_file.unlink()
                subprocess.run(['sysctl', '--system'], check=True)
            else:
                print("--> Arquivo de otimizações de kernel não encontrado.")

            # Remover o usuário do sistema
            try:
                subprocess.run(['id', 'badvpn'], check=True, capture_output=True)
                print("--> Removendo o usuário 'badvpn'...")
                subprocess.run(['userdel', 'badvpn'], check=True)
            except subprocess.CalledProcessError:
                print("--> Usuário 'badvpn' não encontrado.")

            print("\n--- [ Remoção Concluída! ] ---")
            return True, "BadVPN removido com sucesso!"

        except Exception as e:
            print(f"\n--- [ Erro na Remoção ] ---")
            print(str(e))
            return False, f"Erro na remoção: {e}"

# ==================== FRAMES ====================
def build_main_frame(manager, status_msg=""):
    """Frame principal do BadVPN"""
    s = []
    s.append(simple_header("GERENCIADOR BADVPN"))
    
    # Status
    service_status, port = manager.get_status()
    bbr_status = manager.get_bbr_status()
    
    status_lines = [
        f"{MC.CYAN_LIGHT}{Icons.SERVER} Serviço:{MC.RESET} {service_status}",
        f"{MC.CYAN_LIGHT}{Icons.NETWORK} Porta:{MC.RESET} {MC.WHITE}{port}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.ROCKET} Otimização:{MC.RESET} {bbr_status}"
    ]
    
    s.append(modern_box("STATUS DO SISTEMA", status_lines, Icons.CHART, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    
    # Menu
    s.append(modern_box("OPÇÕES DISPONÍVEIS", [], Icons.SETTINGS, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    
    if manager.is_installed():
        s.append(menu_option("1", "Alterar Porta", Icons.EDIT, MC.CYAN_GRADIENT))
        s.append(menu_option("2", "Iniciar Serviço", Icons.ACTIVE, MC.GREEN_GRADIENT))
        s.append(menu_option("3", "Parar Serviço", Icons.INACTIVE, MC.RED_GRADIENT))
        s.append(menu_option("4", "Reiniciar Serviço", Icons.UPDATE, MC.YELLOW_GRADIENT))
        s.append(menu_option("6", "Remover BadVPN", Icons.TRASH, MC.RED_GRADIENT, badge="PERIGO"))
    else:
        s.append(menu_option("1", "Instalar BadVPN", Icons.DOWNLOAD, MC.GREEN_GRADIENT, badge="NECESSÁRIO"))
    
    s.append(menu_option("5", "Gerenciar BBR", Icons.ROCKET, MC.PURPLE_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    
    s.append(footer_line(status_msg))
    return "".join(s)

def build_bbr_frame(status_msg=""):
    """Frame do gerenciador BBR"""
    s = []
    s.append(simple_header("OTIMIZAÇÃO TCP BBR"))
    
    current = bbr_manager.check_status()
    persistent = bbr_manager.is_bbr_persistent()
    
    status_lines = [
        f"{MC.CYAN_LIGHT}{Icons.CPU} Algoritmo Atual:{MC.RESET} {MC.WHITE}{current}{MC.RESET}",
        f"{MC.CYAN_LIGHT}{Icons.SAVE} Persistente:{MC.RESET} {MC.GREEN_GRADIENT if persistent else MC.YELLOW_GRADIENT}{'Sim' if persistent else 'Não'}{MC.RESET}"
    ]
    
    if current == 'bbr':
        status_lines.append(f"{MC.GREEN_GRADIENT}{Icons.CHECK} BBR está ativo e otimizando a rede{MC.RESET}")
    else:
        status_lines.append(f"{MC.YELLOW_GRADIENT}{Icons.INFO} BBR pode melhorar a performance da rede{MC.RESET}")
    
    s.append(modern_box("STATUS BBR", status_lines, Icons.ROCKET, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    
    s.append(menu_option("1", "Ativar BBR", Icons.ACTIVE, MC.GREEN_GRADIENT))
    s.append(menu_option("2", "Desativar BBR", Icons.INACTIVE, MC.RED_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT))
    
    s.append(footer_line(status_msg))
    return "".join(s)

def build_operation_frame(operation, port=None):
    """Frame para operações"""
    s = []
    s.append(simple_header("EXECUTANDO OPERAÇÃO"))
    
    if operation == "install":
        title = "Instalando BadVPN"
        icon = Icons.DOWNLOAD
        color = MC.GREEN_GRADIENT
        msg = f"Configurando na porta {port}..." if port else "Instalando serviço..."
    elif operation == "port":
        title = "Alterando Porta"
        icon = Icons.EDIT
        color = MC.CYAN_GRADIENT
        msg = f"Mudando para porta {port}..."
    elif operation == "uninstall":
        title = "Removendo BadVPN"
        icon = Icons.TRASH
        color = MC.RED_GRADIENT
        msg = "Desinstalando o serviço e removendo arquivos..."
    else:
        title = "Processando"
        icon = Icons.SETTINGS
        color = MC.YELLOW_GRADIENT
        msg = "Aguarde..."
    
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}{msg}{MC.RESET}"
    ], icon, color, MC.CYAN_LIGHT))
    
    s.append(footer_line("Processando..."))
    return "".join(s)

# ==================== MENU PRINCIPAL ====================
def main_menu():
    """Menu principal do BadVPN"""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este script deve ser executado como root.{MC.RESET}")
        sys.exit(1)
    
    manager = BadVPNManager()
    TerminalManager.enter_alt_screen()
    status = ""
    
    try:
        while True:
            TerminalManager.render(build_main_frame(manager, status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            
            if choice == "1":
                # Instalar ou alterar porta
                TerminalManager.before_input()
                port = input(f"\n{MC.CYAN_GRADIENT}Digite a porta (ex: 7300): {MC.RESET}").strip()
                TerminalManager.after_input()
                
                if port.isdigit() and 1 <= int(port) <= 65535:
                    TerminalManager.render(build_operation_frame("install" if not manager.is_installed() else "port", port))
                    TerminalManager.leave_alt_screen()
                    
                    try:
                        subprocess.run(['bash', str(manager.install_script), port], check=True)
                        status = f"Porta configurada: {port}"
                    except Exception as e:
                        status = f"Erro na configuração: {e}"
                    
                    TerminalManager.enter_alt_screen()
                else:
                    status = "Porta inválida"
            
            elif choice == "2" and manager.is_installed():
                # Ativar BBR se não estiver ativo
                if bbr_manager.check_status() != 'bbr':
                    success, msg = bbr_manager.enable()
                    if not success:
                        status = f"Erro ao ativar BBR: {msg}. Serviço iniciado mesmo assim."
                    else:
                        status = "BBR ativado e Serviço iniciado."
                else:
                    status = "Serviço iniciado."
                subprocess.run(['systemctl', 'start', 'badvpn-udpgw'], check=False)
            
            elif choice == "3" and manager.is_installed():
                subprocess.run(['systemctl', 'stop', 'badvpn-udpgw'], check=False)
                status = "Serviço parado"
            
            elif choice == "4" and manager.is_installed():
                # Ativar BBR se não estiver ativo
                if bbr_manager.check_status() != 'bbr':
                    success, msg = bbr_manager.enable()
                    if not success:
                        status = f"Erro ao ativar BBR: {msg}. Serviço reiniciado mesmo assim."
                    else:
                        status = "BBR ativado e Serviço reiniciado."
                else:
                    status = "Serviço reiniciado."
                subprocess.run(['systemctl', 'restart', 'badvpn-udpgw'], check=False)
            
            elif choice == "5":
                # Submenu BBR
                bbr_status = ""
                while True:
                    TerminalManager.render(build_bbr_frame(bbr_status))
                    TerminalManager.before_input()
                    bbr_choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha: {MC.RESET}").strip()
                    TerminalManager.after_input()
                    
                    if bbr_choice == "1":
                        success, msg = bbr_manager.enable()
                        bbr_status = "BBR ativado!" if success else f"Erro: {msg}"
                    elif bbr_choice == "2":
                        success, msg = bbr_manager.disable()
                        bbr_status = "BBR desativado!" if success else f"Erro: {msg}"
                    elif bbr_choice == "0":
                        break
                    else:
                        bbr_status = "Opção inválida"
                
                status = "Configuração BBR atualizada"
            
            elif choice == "6" and manager.is_installed():
                TerminalManager.before_input()
                confirm = input(f"\n{MC.RED_GRADIENT}{Icons.WARNING} Tem certeza que deseja remover o BadVPN? (s/N): {MC.RESET}").strip().lower()
                TerminalManager.after_input()

                if confirm == 's':
                    TerminalManager.render(build_operation_frame("uninstall"))
                    TerminalManager.leave_alt_screen()
                    
                    success, message = manager.uninstall()
                    status = message
                    
                    input("\nPressione Enter para voltar ao menu...")
                    
                    TerminalManager.enter_alt_screen()
                else:
                    status = "Remoção cancelada."

            elif choice == "0":
                break
            else:
                status = "Opção inválida"
    
    except KeyboardInterrupt:
        status = "Operação cancelada"
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main_menu()

