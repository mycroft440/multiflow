#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import re
import sys

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

class OpenVPNManager:
    def __init__(self):
        # Caminhos ajustados para maior robustez
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.openvpn_go_path = os.path.join(self.base_dir, '..', 'conexoes', 'openvpn.go')
        self.compiled_openvpn_go = "/usr/local/bin/openvpn_manager_go"
        self.server_conf_path = "/etc/openvpn/server.conf"

    def _run_command(self, command, check_error=True, capture_output=True, cwd=None):
        """Executa um comando shell e retorna a saída."""
        try:
            result = subprocess.run(
                command, 
                capture_output=capture_output, 
                text=True, 
                check=check_error,
                cwd=cwd
            )
            return result.stdout.strip() if capture_output else ""
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao executar comando: {' '.join(e.cmd)}{COLORS.END}")
            if capture_output:
                print(f"{COLORS.RED}Saída: {e.stdout}{COLORS.END}")
                print(f"{COLORS.RED}Erro: {e.stderr}{COLORS.END}")
            return None
        except FileNotFoundError:
            print(f"{COLORS.RED}Comando não encontrado: {command[0]}{COLORS.END}")
            return None

    def _check_openvpn_status(self):
        """Verifica se o OpenVPN está instalado e rodando."""
        if not os.path.exists(self.server_conf_path):
            return False, None
        
        status_output = self._run_command(["systemctl", "is-active", "openvpn@server"], check_error=False)
        if status_output == "active":
            try:
                with open(self.server_conf_path, "r") as f:
                    content = f.read()
                    match = re.search(r"port (\d+)", content)
                    return True, match.group(1) if match else "1194"
            except IOError:
                return True, "Desconhecida"
        return False, None

    def display_status(self):
        """Exibe o status atual do OpenVPN."""
        is_running, port = self._check_openvpn_status()
        if is_running:
            return f"{COLORS.GREEN}Ativo{COLORS.END}, Porta: {COLORS.YELLOW}{port}{COLORS.END}"
        else:
            return f"{COLORS.RED}Inativo / Não Instalado{COLORS.END}"

    def run_go_installer(self):
        """Compila e executa o instalador Go."""
        clear_screen()
        print_colored_box("INSTALADOR OPENVPN")
        
        go_script_path = os.path.join(self.base_dir, '..', 'conexoes')
        go_script_name = 'openvpn.go'

        if not os.path.exists(os.path.join(go_script_path, go_script_name)):
            print(f"{COLORS.RED}Erro: Arquivo '{go_script_name}' não encontrado em '{go_script_path}'.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Compilando o gerenciador Go...{COLORS.END}")
        # CORREÇÃO: Passa o nome do arquivo sem aspas extras.
        # O comando é executado dentro do diretório do script Go.
        compile_cmd = ["go", "build", "-o", self.compiled_openvpn_go, go_script_name]
        if self._run_command(compile_cmd, capture_output=False, cwd=go_script_path) is None:
            print(f"{COLORS.RED}Erro ao compilar '{go_script_name}'. Certifique-se de que o Go está instalado e o código-fonte não tem erros.{COLORS.END}")
            return
        
        print(f"{COLORS.GREEN}Compilação concluída.{COLORS.END}")
        print(f"{COLORS.YELLOW}Iniciando o instalador interativo... Siga as instruções na tela.{COLORS.END}")
        
        try:
            # O script Go é interativo, então executamos diretamente no terminal
            # Usamos sys.stdin, sys.stdout, sys.stderr para permitir a interatividade
            subprocess.run(["sudo", self.compiled_openvpn_go], check=True, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
            print(f"\n{COLORS.GREEN}Instalação do OpenVPN concluída com sucesso!{COLORS.END}")
        except subprocess.CalledProcessError:
            print(f"\n{COLORS.RED}A instalação do OpenVPN foi interrompida ou falhou.{COLORS.END}")
        except FileNotFoundError:
            print(f"\n{COLORS.RED}Comando 'sudo' não encontrado. Execute como root.{COLORS.END}")

    def main_menu(self):
        """Menu principal do OpenVPN."""
        if os.geteuid() != 0:
            print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
            return
            
        while True:
            try:
                clear_screen()
                status_line = self.display_status()
                print_colored_box("GERENCIADOR OPENVPN", [f"Status: {status_line}"])
                
                # A única opção é instalar/executar o script Go
                print_menu_option("1", "Instalar / Gerenciar OpenVPN (via script Go)", color=COLORS.CYAN)
                print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
                print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

                choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
                
                if choice == '1':
                    self.run_go_installer()
                elif choice == '0':
                    break
                else:
                    print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                    
                input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
                
            except KeyboardInterrupt:
                print("\n\nSaindo...")
                break

# Função para ser chamada pelo multiflow.py
def main_menu():
    manager = OpenVPNManager()
    manager.main_menu()

if __name__ == "__main__":
    main_menu()
