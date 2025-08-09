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

def verificar_openvpn_instalado():
    for path in ('/etc/openvpn/server/server.conf', '/etc/openvpn/server.conf'):
        if os.path.exists(path):
            return True
    try:
        r = subprocess.run(["systemctl", "is-active", "openvpn-server@server"], capture_output=True, text=True, check=False)
        return r.returncode == 0 and r.stdout.strip() == "active"
    except Exception:
        return False

def get_openvpn_status():
    if not verificar_openvpn_instalado():
        return f"{MC.RED_GRADIENT}{Icons.INACTIVE} Não Instalado{MC.RESET}"
    try:
        r = subprocess.run(["systemctl", "is-active", "openvpn-server@server"], capture_output=True, text=True, check=False)
        if r.returncode == 0 and r.stdout.strip() == "active":
            return f"{MC.GREEN_GRADIENT}{Icons.ACTIVE} Ativo{MC.RESET}"
        return f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Instalado (Inativo){MC.RESET}"
    except Exception:
        return f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Status Desconhecido{MC.RESET}"

def count_ovpn_files():
    try:
        return len([f for f in os.listdir('/root') if f.endswith('.ovpn')])
    except Exception:
        return 0

def obter_caminho_script():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(root_dir, "conexoes", "openvpn.sh"), "/opt/multiflow/conexoes/openvpn.sh"):
        if os.path.exists(path):
            return path
    return None

def build_main_frame(status_msg=""):
    s=[]
    s.append(simple_header("GERENCIADOR OPENVPN"))
    status = get_openvpn_status(); clients = count_ovpn_files()
    s.append(modern_box("STATUS DO SERVIÇO", [
        f"{MC.CYAN_LIGHT}{Icons.NETWORK} Status:{MC.RESET} {status}",
        f"{MC.CYAN_LIGHT}{Icons.FILE} Clientes Configurados:{MC.RESET} {MC.WHITE}{clients}{MC.RESET}"
    ], Icons.INFO, MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    if verificar_openvpn_instalado():
        s.append(modern_box("OPÇÕES DISPONÍVEIS", [], Icons.SETTINGS, MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Adicionar Novo Cliente", Icons.PLUS, MC.GREEN_GRADIENT))
        s.append(menu_option("2", "Remover Cliente", Icons.MINUS, MC.ORANGE_GRADIENT))
        s.append(menu_option("3", "Listar Arquivos .ovpn", Icons.FOLDER, MC.CYAN_GRADIENT))
        s.append(menu_option("4", "Reinstalar OpenVPN", Icons.UPDATE, MC.YELLOW_GRADIENT))
        s.append(menu_option("5", "Desinstalar OpenVPN", Icons.TRASH, MC.RED_GRADIENT))
    else:
        s.append(modern_box("INSTALAÇÃO DISPONÍVEL", [
            f"{MC.YELLOW_GRADIENT}{Icons.INFO} OpenVPN não está instalado{MC.RESET}",
            f"{MC.WHITE}Configuração automática com:{MC.RESET}",
            "  • Protocolo TCP",
            "  • DNS da VPS",
            "  • Cliente inicial: cliente1.ovpn"
        ], Icons.DOWNLOAD, MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Instalar OpenVPN Agora", Icons.DOWNLOAD, MC.GREEN_GRADIENT, badge="RECOMENDADO"))
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", Icons.BACK, MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_clients_frame():
    s=[]
    s.append(simple_header("CLIENTES OPENVPN"))
    try:
        files = [f for f in os.listdir('/root') if f.endswith('.ovpn')]
        if files:
            content=[]
            for f in files:
                try:
                    size = os.path.getsize(f'/root/{f}') / 1024
                    content.append(f"{MC.CYAN_LIGHT}{Icons.FILE}{MC.RESET} /root/{f} {MC.GRAY}({size:.1f} KB){MC.RESET}")
                except Exception:
                    content.append(f"{MC.CYAN_LIGHT}{Icons.FILE}{MC.RESET} /root/{f}")
            content.append("")
            content.append(f"{MC.YELLOW_GRADIENT}{Icons.INFO} Use SFTP para baixar os arquivos{MC.RESET}")
        else:
            content=[f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Nenhum arquivo .ovpn encontrado{MC.RESET}"]
        s.append(modern_box("ARQUIVOS DE CONFIGURAÇÃO", content, Icons.FOLDER, MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    except Exception as e:
        s.append(modern_box("ERRO", [f"{MC.RED_GRADIENT}{Icons.CROSS} {e}{MC.RESET}"], Icons.WARNING, MC.RED_GRADIENT, MC.RED_LIGHT))
    s.append(footer_line())
    return "".join(s)

def build_operation_frame(title, icon, color, msg="Aguarde..."):
    s=[]
    s.append(simple_header("OPERAÇÃO EM ANDAMENTO"))
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}{Icons.WARNING} Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}{msg}{MC.RESET}"
    ], icon, color, MC.CYAN_LIGHT))
    s.append(footer_line("Processando..."))
    return "".join(s)

def executar_script_openvpn():
    script_path = obter_caminho_script()
    if not script_path:
        return False, "Script openvpn.sh não encontrado em conexoes/."
    try:
        TerminalManager.render(build_operation_frame("Executando openvpn.sh", Icons.DOWNLOAD, MC.GREEN_GRADIENT, "Inicializando instalação/gestão..."))
        # Sair do alt-screen para mostrar saída do script
        TerminalManager.leave_alt_screen()
        subprocess.run(['chmod', '+x', script_path], check=True)
        result = subprocess.run(['bash', script_path], check=False)
        TerminalManager.enter_alt_screen()
        return result.returncode == 0, ("Concluído" if result.returncode == 0 else "Falhou (verifique logs)")
    except Exception as e:
        TerminalManager.enter_alt_screen()
        return False, str(e)

def main_menu():
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este menu precisa ser executado como root.{MC.RESET}")
        input("Pressione Enter para voltar...")
        return
    TerminalManager.enter_alt_screen()
    status=""
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            if verificar_openvpn_instalado():
                if choice == "1":
                    ok,msg = executar_script_openvpn(); status = "Cliente adicionado" if ok else f"Erro: {msg}"
                elif choice == "2":
                    ok,msg = executar_script_openvpn(); status = "Cliente removido" if ok else f"Erro: {msg}"
                elif choice == "3":
                    TerminalManager.render(build_clients_frame()); TerminalManager.before_input()
                    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}"); TerminalManager.after_input(); status="Listagem concluída"
                elif choice == "4":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN reinstalado" if ok else f"Erro: {msg}"
                elif choice == "5":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN desinstalado" if ok else f"Erro: {msg}"
                elif choice == "0":
                    break
                else: status="Opção inválida"
            else:
                if choice == "1":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN instalado com sucesso!" if ok else f"Erro: {msg}"
                elif choice == "0":
                    break
                else: status="Opção inválida"
            time.sleep(0.6)
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main_menu()
