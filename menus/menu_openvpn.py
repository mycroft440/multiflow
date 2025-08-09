#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess

# Garante que o diretório pai (raiz do projeto) esteja no sys.path quando executado isolado
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError as e:
    print(f"Erro: não foi possível importar utilitários de estilo: {e}")
    sys.exit(1)

COLORS = Colors()

def verificar_openvpn_instalado():
    """
    Verifica se o OpenVPN está instalado.
    Considera as localizações mais comuns usadas pelo script do Angristan:
    - /etc/openvpn/server/server.conf
    - /etc/openvpn/server.conf (legacy)
    E também verifica o serviço systemd openvpn-server@server.
    """
    try:
        if os.path.exists('/etc/openvpn/server/server.conf'):
            return True
        if os.path.exists('/etc/openvpn/server.conf'):
            return True
        r = subprocess.run(
            ["systemctl", "is-active", "openvpn-server@server"],
            capture_output=True, text=True, check=False
        )
        if r.returncode == 0 and r.stdout.strip() == "active":
            return True
    except Exception:
        pass
    return False

def obter_caminho_script_instalacao():
    """
    Resolve o caminho do script conexoes/openvpn.sh, primeiro relativo à raiz do projeto,
    depois cai no caminho padrão de instalação (/opt/multiflow/conexoes/openvpn.sh).
    """
    # Caminho relativo à estrutura do projeto
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rel_path = os.path.join(root_dir, "conexoes", "openvpn.sh")
    if os.path.exists(rel_path):
        return rel_path

    # Caminho padrão de instalação
    abs_path = "/opt/multiflow/conexoes/openvpn.sh"
    if os.path.exists(abs_path):
        return abs_path

    return None

def executar_script_instalacao():
    """
    Executa o script de instalação/gerenciamento do OpenVPN (openvpn.sh).
    Esse script já é não-interativo para instalação inicial e delega ao script do Angristan.
    """
    script_path = obter_caminho_script_instalacao()
    if not script_path:
        print(f"\n{COLORS.RED}Script 'openvpn.sh' não encontrado em conexoes/.{COLORS.END}")
        input("Pressione Enter para continuar...")
        return

    try:
        # Garante permissão de execução e executa com bash
        subprocess.run(['chmod', '+x', script_path], check=True)
        subprocess.run(['bash', script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{COLORS.RED}Ocorreu um erro ao executar '{script_path}':{COLORS.END}\n{e}")
        input("Pressione Enter para continuar...")
    except FileNotFoundError:
        print(f"\n{COLORS.RED}O comando 'bash' não foi encontrado.{COLORS.END}")
        input("Pressione Enter para continuar...")

def listar_clientes_ovpn():
    """
    Lista arquivos .ovpn do diretório /root.
    """
    clear_screen()
    print_colored_box("CLIENTES OPENVPN (.ovpn) EM /root")
    try:
        files = os.listdir('/root')
        ovpn_files = [f for f in files if f.endswith('.ovpn')]

        if not ovpn_files:
            print("\nNenhum arquivo de cliente (.ovpn) encontrado no diretório /root.")
        else:
            print("\nArquivos de configuração de clientes encontrados:")
            for filename in ovpn_files:
                print(f"  - /root/{filename}")
            print("\nDica: use SFTP (FileZilla/Termius) para baixar os arquivos.")
    except Exception as e:
        print(f"\n{COLORS.RED}Erro ao listar /root: {e}{COLORS.END}")

    input("\nPressione Enter para voltar ao menu...")

def menu_instalado():
    """
    Menu quando OpenVPN está instalado: delega as operações ao openvpn.sh.
    """
    while True:
        clear_screen()
        print_colored_box("GERENCIAR OPENVPN (INSTALADO)")
        print_menu_option("1", "Adicionar um novo cliente", color=COLORS.CYAN)
        print_menu_option("2", "Remover um cliente existente", color=COLORS.CYAN)
        print_menu_option("3", "Listar arquivos de cliente (.ovpn)", color=COLORS.CYAN)
        print_menu_option("4", "Desinstalar o OpenVPN", color=COLORS.RED)
        print_menu_option("0", "Voltar ao menu principal", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

        escolha = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()

        if escolha in ('1', '2', '4'):
            clear_screen()
            print_colored_box("ASSISTENTE DO OPENVPN", ["Siga as instruções exibidas pelo script..."])
            executar_script_instalacao()
            input("\nAssistente finalizado. Pressione Enter para voltar ao menu.")
        elif escolha == '3':
            listar_clientes_ovpn()
        elif escolha == '0':
            break
        else:
            print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
            input("\nPressione Enter para continuar...")

def menu_nao_instalado():
    """
    Menu quando OpenVPN não está instalado: oferta instalação automática.
    """
    clear_screen()
    lines = [
        "O OpenVPN não parece estar instalado.",
        "",
        "A instalação será automática com os padrões:",
        " - Protocolo: TCP",
        " - DNS: o mesmo da VPS",
        " - Primeiro cliente: 'cliente1' salvo em /root/cliente1.ovpn",
    ]
    print_colored_box("GERENCIAR OPENVPN (NÃO INSTALADO)", lines)

    escolha = input(f"\n{COLORS.BOLD}Deseja instalar agora? (s/n): {COLORS.END}").strip().lower()
    if escolha == 's':
        clear_screen()
        print_colored_box("INSTALAÇÃO DO OPENVPN", ["Instalação em andamento... Aguarde alguns minutos."])
        executar_script_instalacao()

        print("\nVerificando instalação...")
        if verificar_openvpn_instalado():
            print(f"\n{COLORS.GREEN}✓ OpenVPN instalado com sucesso!{COLORS.END}")
        else:
            print(f"\n{COLORS.RED}✗ A instalação não parece ter concluído. Verifique os logs.{COLORS.END}")
        input("\nPressione Enter para continuar...")

def main_menu():
    """
    Entrada principal do menu de OpenVPN (usada por multiflow.py).
    """
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este menu precisa ser executado como root.{COLORS.END}")
        input("Pressione Enter para voltar...")
        return

    if verificar_openvpn_instalado():
        menu_instalado()
    else:
        menu_nao_instalado()

if __name__ == "__main__":
    main_menu()
