#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager, 
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# ==================== FUNÇÕES AUXILIARES ====================
def verificar_openvpn_instalado():
    """Verifica se o OpenVPN está instalado"""
    paths = [
        '/etc/openvpn/server/server.conf',
        '/etc/openvpn/server.conf'
    ]
    
    for path in paths:
        if os.path.exists(path):
            return True
    
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "openvpn-server@server"],
            capture_output=True, text=True, check=False
        )
        if r.returncode == 0 and r.stdout.strip() == "active":
            return True
    except:
        pass
    
    return False

def get_openvpn_status():
    """Obtém status detalhado do OpenVPN"""
    if not verificar_openvpn_instalado():
        return f"{MC.RED_GRADIENT}{Icons.INACTIVE} Não Instalado{MC.RESET}"
    
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "openvpn-server@server"],
            capture_output=True, text=True, check=False
        )
        if r.returncode == 0 and r.stdout.strip() == "active":
            return f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} Ativo{MC.RESET}"
        else:
            return f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Instalado (Inativo){MC.RESET}"
    except:
        return f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Status Desconhecido{MC.RESET}"

def count_ovpn_files():
    """Conta arquivos .ovpn em /root"""
    try:
        files = [f for f in os.listdir('/root') if f.endswith('.ovpn')]
        return len(files)
    except:
        return 0

def obter_caminho_script():
    """Resolve o caminho do script openvpn.sh"""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [
        os.path.join(root_dir, "conexoes", "openvpn.sh"),
        "/opt/multiflow/conexoes/openvpn.sh"
    ]
    
    for path in paths:
        if os.path.exists(path):
            return path
    return None

# ==================== FRAMES DE RENDERIZAÇÃO ====================
def build_main_frame(status_msg=""):
    """Constrói o frame principal do menu OpenVPN"""
    s = []
    s.append(simple_header("GERENCIADOR OPENVPN"))
    
    # Status box
    status = get_openvpn_status()
    clients = count_ovpn_files()
    
    status_lines = [
        f"{MC.CYAN_LIGHT}{Icons.NETWORK} Status:{MC.RESET} {status}",
        f"{MC.CYAN_LIGHT}{Icons.FILE} Clientes Configurados:{MC.RESET} {MC.WHITE}{clients}{MC.RESET}"
    ]
    
    s.append(modern_box("STATUS DO SERVIÇO", status_lines, Icons.INFO, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    
    if verificar_openvpn_instalado():
        # Menu instalado
        s.append(modern_box("OPÇÕES DISPONÍVEIS", [], Icons.SETTINGS, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Adicionar Novo Cliente", Icons.PLUS, MC.GREEN_GRADIENT))
        s.append(menu_option("2", "Remover Cliente", Icons.MINUS, MC.ORANGE_GRADIENT))
        s.append(menu_option("3", "Listar Arquivos .ovpn", Icons.FOLDER, MC.CYAN_GRADIENT))
        s.append(menu_option("4", "Reinstalar OpenVPN", Icons.UPDATE, MC.YELLOW_GRADIENT))
        s.append(menu_option("5", "Desinstalar OpenVPN", Icons.TRASH, MC.RED_GRADIENT))
    else:
        # Menu não instalado
        s.append(modern_box("INSTALAÇÃO DISPONÍVEL", [
            f"{MC.YELLOW_GRADIENT}{Icons.INFO} OpenVPN não está instalado{MC.RESET}",
            f"{MC.WHITE}Configuração automática com:{MC.RESET}",
            f"  • Protocolo TCP",
            f"  • DNS da VPS",
            f"  • Cliente inicial: cliente1.ovpn"
        ], Icons.DOWNLOAD, MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Instalar OpenVPN Agora", Icons.DOWNLOAD, MC.GREEN_GRADIENT, badge="RECOMENDADO"))
    
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    
    return "".join(s)

def build_clients_frame():
    """Frame para listar clientes"""
    s = []
    s.append(simple_header("CLIENTES OPENVPN"))
    
    try:
        files = [f for f in os.listdir('/root') if f.endswith('.ovpn')]
        
        if files:
            content = []
            for f in files:
                size = os.path.getsize(f'/root/{f}') / 1024  # KB
                content.append(f"{MC.CYAN_LIGHT}{Icons.FILE}{MC.RESET} /root/{f} {MC.GRAY}({size:.1f} KB){MC.RESET}")
            content.append("")
            content.append(f"{MC.YELLOW_GRADIENT}{Icons.INFO} Use SFTP para baixar os arquivos{MC.RESET}")
        else:
            content = [f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Nenhum arquivo .ovpn encontrado{MC.RESET}"]
        
        s.append(modern_box("ARQUIVOS DE CONFIGURAÇÃO", content, Icons.FOLDER, MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    except Exception as e:
        s.append(modern_box("ERRO", [f"{MC.RED_GRADIENT}{Icons.CROSS} {e}{MC.RESET}"], Icons.WARNING, MC.RED_GRADIENT, MC.RED_LIGHT))
    
    s.append(footer_line())
    return "".join(s)

def build_operation_frame(operation):
    """Frame para operações em andamento"""
    s = []
    s.append(simple_header("OPERAÇÃO EM ANDAMENTO"))
    
    ops = {
        "install": ("Instalando OpenVPN", Icons.DOWNLOAD, MC.GREEN_GRADIENT),
        "add": ("Adicionando Cliente", Icons.PLUS, MC.GREEN_GRADIENT),
        "remove": ("Removendo Cliente", Icons.MINUS, MC.ORANGE_GRADIENT),
        "uninstall": ("Desinstalando OpenVPN", Icons.TRASH, MC.RED_GRADIENT)
    }
    
    title, icon, color = ops.get(operation, ("Processando", Icons.SETTINGS, MC.CYAN_GRADIENT))
    
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}Aguarde a conclusão...{MC.RESET}"
    ], icon, color, MC.CYAN_LIGHT))
    
    s.append(footer_line("Processando..."))
    return "".join(s)

# ==================== OPERAÇÕES ====================
def executar_script_openvpn(operation=""):
    """Executa o script openvpn.sh"""
    script_path = obter_caminho_script()
    if not script_path:
        return False, "Script openvpn.sh não encontrado"
    
    try:
        # Mostra frame de operação
        TerminalManager.render(build_operation_frame(operation))
        
        # Sai do alt screen para mostrar output do script
        TerminalManager.leave_alt_screen()
        
        subprocess.run(['chmod', '+x', script_path], check=True)
        result = subprocess.run(['bash', script_path], check=False)
        
        # Volta ao alt screen
        TerminalManager.enter_alt_screen()
        
        return result.returncode == 0, "Operação concluída"
    except Exception as e:
        TerminalManager.enter_alt_screen()
        return False, str(e)

# ==================== MENU PRINCIPAL ====================
def main_menu():
    """Menu principal do OpenVPN"""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este menu precisa ser executado como root.{MC.RESET}")
        input("Pressione Enter para voltar...")
        return
    
    TerminalManager.enter_alt_screen()
    status = ""
    
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            
            if verificar_openvpn_instalado():
                # Menu para OpenVPN instalado
                if choice == "1":
                    success, msg = executar_script_openvpn("add")
                    status = "Cliente adicionado" if success else f"Erro: {msg}"
                elif choice == "2":
                    success, msg = executar_script_openvpn("remove")
                    status = "Cliente removido" if success else f"Erro: {msg}"
                elif choice == "3":
                    TerminalManager.render(build_clients_frame())
                    TerminalManager.before_input()
                    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
                    TerminalManager.after_input()
                    status = "Listagem concluída"
                elif choice == "4":
                    success, msg = executar_script_openvpn("install")
                    status = "OpenVPN reinstalado" if success else f"Erro: {msg}"
                elif choice == "5":
                    success, msg = executar_script_openvpn("uninstall")
                    if success:
                        status = "OpenVPN desinstalado"
                    else:
                        status = f"Erro: {msg}"
                elif choice == "0":
                    break
                else:
                    status = "Opção inválida"
            else:
                # Menu para OpenVPN não instalado
                if choice == "1":
                    success, msg = executar_script_openvpn("install")
                    status = "OpenVPN instalado com sucesso!" if success else f"Erro: {msg}"
                elif choice == "0":
                    break
                else:
                    status = "Opção inválida"
            
            if status and "sucesso" in status.lower():
                time.sleep(1.5)
            elif status and "erro" in status.lower():
                time.sleep(2.0)
    
    except KeyboardInterrupt:
        status = "Operação cancelada"
    except Exception as e:
        status = f"Erro: {e}"
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main_menu()
