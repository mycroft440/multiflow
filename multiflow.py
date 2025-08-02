#!/usr/bin/env python3

import os
import sys
import time
import re
import platform
import subprocess
import psutil
import signal
import shutil

# Importando os módulos necessários no início
try:
    import ssh_user_manager
    from menus import menu_badvpn
    from menus import menu_openvpn
    # --- CORREÇÃO: Adicionado import para o menu do proxysocks ---
    from menus import menu_proxysocks 
except ImportError as e:
    print(f"\033[91mErro: Módulo \'{e.name}\' não encontrado.\033[0m")
    print(f"\033[93mCertifique-se de que todos os ficheiros .py estão no mesmo diretório que este script.\033[0m")
    sys.exit(1)

from menus.menu_style_utils import Colors, BoxChars, visible_length, clear_screen, print_centered, print_colored_box, print_menu_option

# Instanciando cores
COLORS = Colors()

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_colored_box("AVISO", [
            f"{COLORS.RED}Este script precisa ser executado como root para a maioria das funcionalidades.{COLORS.END}",
            f"{COLORS.YELLOW}Algumas operações podem falhar sem privilégios adequados.{COLORS.END}"
        ])
        
        confirm = input(f"{COLORS.BOLD}Deseja continuar mesmo assim? (s/n): {COLORS.END}")
        if confirm.lower() != 's':
            print(f"{COLORS.GREEN}Saindo...{COLORS.END}")
            sys.exit(0)
        return False
    return True

def monitorar_uso_recursos(intervalo_cpu=1.0, amostras_cpu=1):
    """
    Função avançada para monitorar a porcentagem de uso da memória RAM e da CPU.
    """
    try:
        if intervalo_cpu <= 0 or amostras_cpu <= 0:
            raise ValueError("Os parâmetros 'intervalo_cpu' e 'amostras_cpu' devem ser positivos.")
        
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        
        cpu_amostras = []
        for _ in range(amostras_cpu):
            cpu_amostras.append(psutil.cpu_percent(interval=intervalo_cpu))
            time.sleep(0.1)
        
        cpu_percent = sum(cpu_amostras) / len(cpu_amostras) if cpu_amostras else 0.0
        
        return {
            'ram_percent': ram_percent,
            'cpu_percent': cpu_percent
        }
    
    except ValueError as ve:
        raise ValueError(f"Erro de validação: {ve}")
    except Exception as e:
        raise Exception(f"Erro ao monitorar recursos: {e}")

def get_system_info():
    """Obtém informações do sistema para o painel."""
    system_info = {
        "os_name": "Desconhecido",
        "ram_percent": 0,
        "cpu_percent": 0
    }
    
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_info = {}
                for line in f:
                    if '=' in line:
                        key, value = line.rstrip('\n').split('=', 1)
                        os_info[key] = value.strip('"').strip("'")
            
            if 'PRETTY_NAME' in os_info:
                system_info["os_name"] = os_info['PRETTY_NAME']
            elif 'NAME' in os_info and 'VERSION_ID' in os_info:
                system_info["os_name"] = f"{os_info['NAME']} {os_info['VERSION_ID']}"
        
        if system_info["os_name"] == "Desconhecido" and sys.platform == 'darwin':
            mac_ver = platform.mac_ver()[0]
            system_info["os_name"] = f"macOS {mac_ver}"
        elif system_info["os_name"] == "Desconhecido" and sys.platform == 'win32':
            system_info["os_name"] = platform.win32_ver()[0]
    except Exception:
        pass
    
    try:
        recursos = monitorar_uso_recursos()
        system_info["ram_percent"] = recursos['ram_percent']
        system_info["cpu_percent"] = recursos['cpu_percent']
    except Exception as e:
        print(f"{COLORS.YELLOW}Aviso: Não foi possível obter informações de uso da CPU/RAM. Erro: {e}{COLORS.END}")
    return system_info

def show_system_panel():
    """Exibe o painel com informações do sistema."""
    info = get_system_info()
    
    def get_color_code(percent):
        if percent < 50:
            return COLORS.GREEN
        elif percent < 80:
            return COLORS.YELLOW
        else:
            return COLORS.RED
    
    ram_color = get_color_code(info["ram_percent"])
    cpu_color = get_color_code(info["cpu_percent"])
    
    content_lines = [
        f"{COLORS.BOLD}OS:{COLORS.END} {COLORS.WHITE}{info['os_name']}{COLORS.END}",
        f"{COLORS.BOLD}RAM:{COLORS.END} {ram_color}{info['ram_percent'] :>5.1f}%{COLORS.END} | {COLORS.BOLD}CPU:{COLORS.END} {cpu_color}{info['cpu_percent'] :>5.1f}%{COLORS.END}"
    ]
    
    print_colored_box("INFORMAÇÕES DO SISTEMA", content_lines)

def ssh_users_main_menu():
    """Redireciona para o menu de gerenciamento de usuários SSH."""
    clear_screen()
    ssh_user_manager.main()

def otimizadorvps_menu():
    """Redireciona para o script otimizadorvps.py."""
    clear_screen()
    try:
        # Garante que o caminho para o script seja construído de forma segura
        script_dir = os.path.dirname(__file__)
        otimizador_path = os.path.join(script_dir, 'ferramentas', 'otimizadorvps.py')
        subprocess.run([sys.executable, otimizador_path], check=True)
    except FileNotFoundError:
        print(f"{COLORS.RED}Erro: otimizadorvps.py não encontrado. Certifique-se de que o arquivo está no diretório 'ferramentas'.{COLORS.END}")
    except subprocess.CalledProcessError as e:
        print(f"{COLORS.RED}Erro ao executar otimizadorvps.py: {e}{COLORS.END}")
    input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

# Função principal
if __name__ == "__main__":
    check_root()
    while True:
        clear_screen()
        show_system_panel()
        print_colored_box("MENU PRINCIPAL")
        print_menu_option("1", "Gerenciar Usuários SSH", color=COLORS.CYAN)
        print_menu_option("2", "OpenVPN", color=COLORS.CYAN)
        print_menu_option("3", "BadVPN", color=COLORS.CYAN)
        print_menu_option("4", "ProxySocks (simples)", color=COLORS.CYAN)
        print_menu_option("5", "Otimizador de VPS", color=COLORS.CYAN)
        print_menu_option("0", "Sair", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")
        
        if choice == "1":
            ssh_users_main_menu()
        elif choice == "2":
            menu_openvpn.main_menu()
        elif choice == "3":
            menu_badvpn.main_menu()
        elif choice == "4":
            menu_proxysocks.main()
        elif choice == "5":
            otimizadorvps_menu()
        elif choice == "0":
            print(f"\n{COLORS.GREEN}Saindo do Multiflow...{COLORS.END}")
            break
        else:
            print(f"{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
            time.sleep(1) # Pequena pausa para o usuário ver a mensagem de erro
