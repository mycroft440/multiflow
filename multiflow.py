#!/usr/bin/env python3

import sys
sys.path.append("/opt/multiflow")
import os
import time
import re
import platform
import subprocess
import psutil
import json
import shutil

# Importando os módulos necessários no início
try:
    from ferramentas import manusear_usuarios
    from menus import menu_badvpn
    from menus import menu_proxysocks
    from menus import menu_bloqueador
    from menus import menu_servidor_download
except ImportError as e:
    print(f"\033[91mErro: Módulo '{e.name}' não encontrado.\033[0m")
    print(f"\033[93mCertifique-se de que todos os ficheiros .py estão no mesmo diretório que este script.\033[0m")
    sys.exit(1)

from menus.menu_style_utils import Colors, BoxChars, visible_length, clear_screen, print_colored_box, print_menu_option

# (Todo o código de cores e funções de UI permanece o mesmo...)
# Cores modernas e gradientes
class ModernColors:
    # Cores básicas
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Gradientes modernos
    PURPLE_GRADIENT = '\033[38;2;138;43;226m'  # BlueViolet
    CYAN_GRADIENT = '\033[38;2;0;191;255m'     # DeepSkyBlue
    GREEN_GRADIENT = '\033[38;2;50;205;50m'    # LimeGreen
    ORANGE_GRADIENT = '\033[38;2;255;165;0m'   # Orange
    RED_GRADIENT = '\033[38;2;220;20;60m'      # Crimson
    YELLOW_GRADIENT = '\033[38;2;255;215;0m'   # Gold
    DARK_GREEN = '\033[38;2;0;128;0m'          # DarkGreen
    
    # Cores de fundo
    BG_DARK = '\033[48;2;30;30;30m'
    BG_LIGHT = '\033[48;2;50;50;50m'
    
    # Cores para texto
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    LIGHT_GRAY = '\033[37m'

# Instanciando cores modernas
MC = ModernColors()

# Ícones modernos
class Icons:
    SERVER = ""
    USERS = ""
    NETWORK = ""
    TOOLS = ""
    SHIELD = "🛡️ " # Ícone para bloqueador
    CHART = ""
    CPU = ""
    RAM = ""
    ACTIVE = "●"
    INACTIVE = "○"
    ARROW = ">"
    BACK = "← "
    EXIT = ""
    CLOCK = ""
    SYSTEM = ""
    UPDATE = "⟳ " # Ícone para atualização

def print_gradient_text(text, start_color, end_color):
    """Imprime texto com efeito gradiente simulado."""
    return f"{start_color}{MC.BOLD}{text}{MC.RESET}"

def print_modern_header():
    """Exibe um cabeçalho moderno com arte ASCII."""
    header = f"""
{MC.CYAN_GRADIENT}{MC.BOLD}███╗   ███╗██╗   ██╗██╗  ████████╗██╗███████╗██╗      ██████╗ ██╗    ██╗{MC.RESET}
{MC.CYAN_GRADIENT}{MC.BOLD}████╗ ████║██║   ██║██║  ╚══██╔══╝██║██╔════╝██║     ██╔═══██╗██║    ██║{MC.RESET}
{MC.CYAN_GRADIENT}{MC.BOLD}██╔████╔██║██║   ██║██║     ██║   ██║█████╗  ██║     ██║   ██║██║ █╗ ██║{MC.RESET}
{MC.CYAN_GRADIENT}{MC.BOLD}██║╚██╔╝██║██║   ██║██║     ██║   ██║██╔══╝  ██║     ██║   ██║██║███╗██║{MC.RESET}
{MC.CYAN_GRADIENT}{MC.BOLD}██║ ╚═╝ ██║╚██████╔╝███████╗██║   ██║██║     ███████╗╚██████╔╝╚███╔███╔╝{MC.RESET}
{MC.CYAN_GRADIENT}{MC.BOLD}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝{MC.RESET}
"""
    print(header)

def print_modern_box(title, content, icon="", color=MC.CYAN_GRADIENT, title_color=MC.WHITE):
    """Cria uma caixa moderna com bordas estilizadas."""
    width = 62
    title_text = f"{icon}{title}"
    
    print(f"{color}╔{'═' * width}╗{MC.RESET}")
    print(f"{color}║{title_color}{MC.BOLD} {title_text:<{width-2}} {color}║{MC.RESET}")
    print(f"{color}╠{'═' * width}╣{MC.RESET}")
    
    for line in content:
        # Calcular padding corretamente considerando caracteres de controle
        clean_line = re.sub(r'\033\[[0-9;]*m', '', line)  # Remove códigos ANSI
        padding_needed = width - len(clean_line) - 2
        print(f"{color}║{MC.RESET} {line}{' ' * padding_needed} {color}║{MC.RESET}")
    
    print(f"{color}╚{'═' * width}╝{MC.RESET}")

def print_modern_menu_option(number, text, icon="", color=MC.CYAN_GRADIENT, is_back=False, number_color=None):
    """Imprime uma opção de menu moderna."""
    if number_color is None:
        number_color = color
    
    if is_back:
        print(f"  {number_color}{MC.BOLD}[{number}]{MC.RESET} {icon}{MC.WHITE}{text}{MC.RESET}")
    else:
        print(f"  {number_color}{MC.BOLD}[{number}]{MC.RESET} {icon}{MC.WHITE}{text}{MC.RESET}")

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_modern_box("AVISO DE SEGURANÇA", [
            f"{MC.RED_GRADIENT}{MC.BOLD}AVISO: Este script precisa ser executado como root para a maioria das funcionalidades.{MC.RESET}",
            f"{MC.YELLOW_GRADIENT}Algumas operações podem falhar sem privilégios adequados.{MC.RESET}"
        ], "", MC.RED_GRADIENT, MC.WHITE)
        
        confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar mesmo assim? (s/n): {MC.RESET}")
        if confirm.lower() != 's':
            print(f"{MC.GREEN_GRADIENT}Saindo...{MC.RESET}")
            sys.exit(0)
        return False
    return True

def monitorar_uso_recursos(intervalo_cpu=0.5, amostras_cpu=1):
    """Monitora o uso da memória RAM e da CPU."""
    try:
        ram = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=intervalo_cpu)
        return {'ram_percent': ram.percent, 'cpu_percent': cpu_percent}
    except Exception:
        return {'ram_percent': 0, 'cpu_percent': 0}

def get_system_info():
    """Obtém informações do sistema para o painel."""
    system_info = {"os_name": "Desconhecido", "ram_percent": 0, "cpu_percent": 0}
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                os_info = dict(line.strip().split('=', 1) for line in f if '=' in line)
            system_info["os_name"] = os_info.get('PRETTY_NAME', 'Linux').strip('"')
        recursos = monitorar_uso_recursos()
        system_info.update(recursos)
    except Exception:
        pass
    return system_info

def get_performance_color(percent):
    """Retorna cor baseada na performance."""
    if percent < 50: return MC.GREEN_GRADIENT
    if percent < 80: return MC.YELLOW_GRADIENT
    return MC.RED_GRADIENT

def show_combined_system_panel():
    """Exibe um painel combinado com informações do sistema e serviços ativos."""
    info = get_system_info()
    
    ram_color = get_performance_color(info["ram_percent"])
    cpu_color = get_performance_color(info["cpu_percent"])
    os_name_short = (info['os_name'][:30] + '..') if len(info['os_name']) > 32 else info['os_name']

    # Barra de progresso visual compacta
    def create_progress_bar(percent, color):
        filled = int(percent / 12.5)  # 8 caracteres max
        empty = 8 - filled
        bar = f"{color}{'█' * filled}{'░' * empty}{MC.RESET}"
        return f"{bar} {color}{percent:4.1f}%{MC.RESET}"

    # Obter serviços ativos
    def run_cmd(cmd):
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    active_services = []
    
    # Verificar ZRAM e SWAP
    swapon_output = run_cmd(['swapon', '--show'])
    if 'zram' in swapon_output:
        active_services.append(f"{MC.DARK_GREEN}ZRAM {Icons.ACTIVE}{MC.RESET}")
    if '/swapfile' in swapon_output or 'partition' in swapon_output:
        active_services.append(f"{MC.DARK_GREEN}SWAP {Icons.ACTIVE}{MC.RESET}")

    # Verificar ProxySocks
    try:
        if os.path.exists(menu_proxysocks.STATE_FILE):
            with open(menu_proxysocks.STATE_FILE, 'r') as f:
                pid, port = f.read().strip().split(':')
                if psutil.pid_exists(int(pid)):
                    active_services.append(f"{MC.DARK_GREEN}ProxySocks:{port} {Icons.ACTIVE}{MC.RESET}")
    except (IOError, ValueError):
        pass

    # Verificar OpenVPN (se o arquivo de configuração do servidor existe)
    if os.path.exists('/etc/openvpn/server.conf'):
        active_services.append(f"{MC.DARK_GREEN}OpenVPN {Icons.ACTIVE}{MC.RESET}")


    # Verificar BadVPN
    try:
        result = subprocess.run(["systemctl", "is-active", "badvpn-udpgw"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip() == "active":
            active_services.append(f"{MC.DARK_GREEN}BadVPN {Icons.ACTIVE}{MC.RESET}")
    except Exception:
        pass

    # Montar conteúdo do painel
    system_content = [
        f"{MC.WHITE}Sistema: {MC.DARK_GREEN}{os_name_short}{MC.RESET}",
        f"{MC.WHITE}RAM: {create_progress_bar(info['ram_percent'], ram_color)}{MC.RESET}",
        f"{MC.WHITE}CPU: {create_progress_bar(info['cpu_percent'], cpu_color)}{MC.RESET}",
    ]
    
    if active_services:
        system_content.append("")
        system_content.append(f"{MC.WHITE}Serviços: {MC.DARK_GREEN}{' | '.join(active_services[:3])}{MC.RESET}")
        if len(active_services) > 3:
            system_content.append(f"{MC.WHITE}         {MC.DARK_GREEN}{' | '.join(active_services[3:])}{MC.RESET}")
    else:
        system_content.append("")
        system_content.append(f"{MC.WHITE}Serviços: {MC.DARK_GREEN}Nenhum ativo{MC.RESET}")
    
    print_modern_box("SISTEMA & SERVIÇOS", system_content, "", MC.PURPLE_GRADIENT, MC.WHITE)

def ssh_users_main_menu():
    """Redireciona para o menu de gerenciamento de usuários SSH."""
    clear_screen()
    manusear_usuarios.main()

def conexoes_menu():
    """Menu para gerenciar conexões."""
    while True:
        clear_screen()
        print_modern_header()
        show_combined_system_panel()
        
        print_modern_box("GERENCIAR CONEXÕES", [], "", MC.CYAN_GRADIENT)
        print()
        print_modern_menu_option("1", "Gerenciar OpenVPN", "", MC.GREEN_GRADIENT, False)
        print_modern_menu_option("2", "ProxySocks (simples)", "", MC.CYAN_GRADIENT, False)
        print()
        print_modern_menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT, True)
        
        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}┌─ Escolha uma opção: {MC.RESET}")
        
        if choice == "1":
            clear_screen()
            try:
                script_real_path = os.path.realpath(__file__)
                script_dir = os.path.dirname(script_real_path)
                openvpn_script_path = os.path.join(script_dir, 'conexoes', 'openvpn.sh')
                
                if not os.path.exists(openvpn_script_path):
                    print(f"{MC.RED_GRADIENT}Erro: O script 'openvpn.sh' não foi encontrado em '{openvpn_script_path}'.{MC.RESET}")
                    time.sleep(4)
                    continue

                os.chmod(openvpn_script_path, 0o755)
                subprocess.run(['bash', openvpn_script_path], check=True)
            
            except FileNotFoundError:
                print(f"{MC.RED_GRADIENT}Erro: O comando 'bash' não foi encontrado. Verifique a sua instalação.{MC.RESET}")
                time.sleep(3)
            except subprocess.CalledProcessError:
                input(f"\n{MC.BOLD}Pressione Enter para voltar ao menu...{MC.RESET}")
            except Exception as e:
                print(f"{MC.RED_GRADIENT}Ocorreu um erro inesperado: {e}{MC.RESET}")
                time.sleep(3)

        elif choice == "2": menu_proxysocks.main()
        elif choice == "0": break
        else: 
            print(f"{MC.RED_GRADIENT}Opção inválida.{MC.RESET}")
            time.sleep(1)

def otimizadorvps_menu():
    """Redireciona para o script otimizadorvps.py."""
    clear_screen()
    try:
        script_real_path = os.path.realpath(__file__)
        script_dir = os.path.dirname(script_real_path)
        otimizador_path = os.path.join(script_dir, 'ferramentas', 'otimizadorvps.py')
        subprocess.run([sys.executable, otimizador_path], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"{MC.RED_GRADIENT}Erro ao executar o otimizador: {e}{MC.RESET}")
    input(f"\n{MC.BOLD}Pressione Enter para continuar...{MC.RESET}")

def ferramentas_menu():
    """Menu para acessar as ferramentas de otimização."""
    while True:
        clear_screen()
        print_modern_header()
        show_combined_system_panel()
        
        print_modern_box("FERRAMENTAS DE OTIMIZAÇÃO", [], "", MC.ORANGE_GRADIENT)
        print()
        print_modern_menu_option("1", "Otimizador de VPS", "", MC.GREEN_GRADIENT, False)
        print_modern_menu_option("2", "Bloqueador de Sites", Icons.SHIELD, MC.RED_GRADIENT, False)
        print()
        print_modern_menu_option("0", "Voltar", Icons.BACK, MC.YELLOW_GRADIENT, True)

        choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}┌─ Escolha uma opção: {MC.RESET}")

        if choice == "1":
            otimizadorvps_menu()
        elif choice == "2":
            menu_bloqueador.main_menu()
        elif choice == "0":
            break
        else: 
            print(f"{MC.RED_GRADIENT}Opção inválida.{MC.RESET}")
            time.sleep(1)

# ==============================================================================
# FUNÇÃO DE ATUALIZAÇÃO MODIFICADA
# ==============================================================================
def atualizar_multiflow():
    """Executa o script de atualização em Python e encerra o programa."""
    clear_screen()
    print_modern_box("ATUALIZADOR MULTIFLOW", [
        f"{MC.YELLOW_GRADIENT}Este processo irá baixar a versão mais recente do GitHub.{MC.RESET}",
        f"{MC.YELLOW_GRADIENT}Serviços ativos como BadVPN e ProxySocks serão parados.{MC.RESET}",
        f"{MC.RED_GRADIENT}O programa será encerrado após a atualização.{MC.RESET}",
        f"{MC.WHITE}Você precisará iniciá-lo novamente para usar a nova versão.{MC.RESET}"
    ], Icons.UPDATE, MC.PURPLE_GRADIENT)

    confirm = input(f"\n{MC.BOLD}{MC.WHITE}Deseja continuar com a atualização? (s/n): {MC.RESET}").lower()
    
    if confirm == 's':
        try:
            # Encontra o caminho do script de atualização de forma robusta
            script_dir = os.path.dirname(os.path.realpath(__file__))
            update_script_path = os.path.join(script_dir, 'update.py') # <-- ALTERADO para update.py

            if not os.path.exists(update_script_path):
                print(f"\n{MC.RED_GRADIENT}Erro: Script 'update.py' não encontrado!{MC.RESET}")
                time.sleep(3)
                return

            print("\n" + "="*60)
            # Executa o script de atualização e mostra a saída para o usuário
            # Usa sys.executable para garantir que está usando o mesmo interpretador Python
            subprocess.run(['sudo', sys.executable, update_script_path], check=True)
            print("="*60)
            
            print(f"\n{MC.GREEN_GRADIENT}O programa foi atualizado com sucesso.{MC.RESET}")
            print(f"{MC.YELLOW_GRADIENT}Encerrando agora. Por favor, inicie-o novamente com o comando 'multiflow'.{MC.RESET}")
            sys.exit(0) # Encerra o script para forçar a reinicialização

        except subprocess.CalledProcessError:
            print(f"\n{MC.RED_GRADIENT}Ocorreu um erro durante a atualização. Verifique a saída acima.{MC.RESET}")
            input(f"{MC.BOLD}Pressione Enter para voltar ao menu...{MC.RESET}")
        except Exception as e:
            print(f"\n{MC.RED_GRADIENT}Ocorreu um erro inesperado: {e}{MC.RESET}")
            input(f"{MC.BOLD}Pressione Enter para continuar...{MC.RESET}")
    else:
        print(f"\n{MC.YELLOW_GRADIENT}Atualização cancelada.{MC.RESET}")
        time.sleep(2)


# Função principal
if __name__ == "__main__":
    check_root()
    
    while True:
        try:
            clear_screen()
            print_modern_header()
            show_combined_system_panel()
            
            print_modern_box("MENU PRINCIPAL", [], "", MC.PURPLE_GRADIENT, MC.WHITE)
            print()
            print_modern_menu_option("1", "Gerenciar Usuários SSH", "", MC.GREEN_GRADIENT, False, MC.CYAN_GRADIENT)
            print_modern_menu_option("2", "Gerenciar Conexões", "", MC.CYAN_GRADIENT, False, MC.CYAN_GRADIENT)
            print_modern_menu_option("3", "BadVPN", "", MC.PURPLE_GRADIENT, False, MC.CYAN_GRADIENT)
            print_modern_menu_option("4", "Ferramentas", "", MC.ORANGE_GRADIENT, False, MC.CYAN_GRADIENT)
            print_modern_menu_option("5", "Atualizar Multiflow", Icons.UPDATE, MC.YELLOW_GRADIENT, False, MC.CYAN_GRADIENT)
            print_modern_menu_option("6", "Servidor de Download", "▶️", MC.GREEN_GRADIENT, False, MC.CYAN_GRADIENT)
            print()
            print_modern_menu_option("0", "Sair", "", MC.RED_GRADIENT, True, MC.ORANGE_GRADIENT)
            
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}┌─ Escolha uma opção: {MC.RESET}")
            
            if choice == "1": ssh_users_main_menu()
            elif choice == "2": conexoes_menu()
            elif choice == "3": menu_badvpn.main_menu()
            elif choice == "4": ferramentas_menu()
            elif choice == "5": atualizar_multiflow()
            elif choice == "6": menu_servidor_download.main()
            elif choice == "0":
                print(f"\n{MC.GREEN_GRADIENT}Saindo do Multiflow...{MC.RESET}")
                break
            else:
                print(f"{MC.RED_GRADIENT}Opção inválida. Tente novamente.{MC.RESET}")
                time.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n\n{MC.YELLOW_GRADIENT}Operação interrompida pelo usuário. Saindo...{MC.RESET}")
            break
