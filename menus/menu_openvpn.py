import os
import subprocess
import re
import time
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

    def _run_command(self, command, check_error=True, capture_output=True):
        """Executa um comando shell e retorna a saída."""
        try:
            result = subprocess.run(command, capture_output=capture_output, text=True, check=check_error)
            return result.stdout.strip() if capture_output else ""
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao executar comando: {e.cmd}{COLORS.END}")
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

    def install_openvpn(self):
        """Instala o OpenVPN utilizando o arquivo openvpn.go."""
        clear_screen()
        print_colored_box("INSTALAR OPENVPN")
        
        if not os.path.exists(self.openvpn_go_path):
            print(f"{COLORS.RED}Erro: Arquivo 'openvpn.go' não encontrado.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Compilando o gerenciador Go...{COLORS.END}")
        compile_cmd = ["go", "build", "-o", self.compiled_openvpn_go, self.openvpn_go_path]
        if self._run_command(compile_cmd, capture_output=False) is None:
            print(f"{COLORS.RED}Erro ao compilar 'openvpn.go'. Certifique-se de que o Go está instalado.{COLORS.END}")
            return
        
        print(f"{COLORS.GREEN}Compilação concluída.{COLORS.END}")
        print(f"{COLORS.YELLOW}Iniciando o instalador interativo... Siga as instruções na tela.{COLORS.END}")
        
        try:
            # O script Go é interativo, então executamos diretamente no terminal
            subprocess.run(["sudo", self.compiled_openvpn_go], check=True)
            print(f"\n{COLORS.GREEN}Instalação do OpenVPN concluída com sucesso!{COLORS.END}")
        except subprocess.CalledProcessError:
            print(f"\n{COLORS.RED}A instalação do OpenVPN foi interrompida ou falhou.{COLORS.END}")
        except FileNotFoundError:
            print(f"\n{COLORS.RED}Comando 'sudo' não encontrado. Execute como root.{COLORS.END}")


    def change_port(self):
        """Altera a porta do OpenVPN."""
        clear_screen()
        print_colored_box("ALTERAR PORTA OPENVPN")
        is_installed, current_port = self._check_openvpn_status()
        if not is_installed:
            print(f"{COLORS.RED}OpenVPN não está instalado.{COLORS.END}")
            return

        new_port = input(f"{COLORS.CYAN}Digite a nova porta (atual: {current_port}): {COLORS.END}").strip()
        if not new_port.isdigit() or not (1 <= int(new_port) <= 65535):
            print(f"\n{COLORS.RED}Porta inválida. Digite um número entre 1 e 65535.{COLORS.END}")
            return

        try:
            with open(self.server_conf_path, "r") as f:
                lines = f.readlines()

            with open(self.server_conf_path, "w") as f:
                for line in lines:
                    f.write(re.sub(r"^port \d+", f"port {new_port}", line))
            
            # Atualiza regras do iptables
            self._run_command(["sudo", "iptables", "-D", "INPUT", "-p", "udp", "--dport", current_port, "-j", "ACCEPT"], check_error=False)
            self._run_command(["sudo", "iptables", "-A", "INPUT", "-p", "udp", "--dport", new_port, "-j", "ACCEPT"])
            self._run_command(["sudo", "iptables-save"], check_error=False)

            self.restart_openvpn()
            print(f"\n{COLORS.GREEN}Porta alterada para {new_port} e OpenVPN reiniciado.{COLORS.END}")
        except Exception as e:
            print(f"\n{COLORS.RED}Erro ao alterar porta: {e}{COLORS.END}")

    def restart_openvpn(self):
        """Reinicia o OpenVPN."""
        clear_screen()
        print_colored_box("REINICIAR OPENVPN")
        is_installed, _ = self._check_openvpn_status()
        if not is_installed:
            print(f"{COLORS.RED}OpenVPN não está instalado.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Reiniciando serviço OpenVPN...{COLORS.END}")
        if self._run_command(["sudo", "systemctl", "restart", "openvpn@server"]) is None:
            print(f"{COLORS.RED}Erro ao reiniciar OpenVPN.{COLORS.END}")
            return
        print(f"{COLORS.GREEN}OpenVPN reiniciado com sucesso.{COLORS.END}")

    def remove_openvpn(self):
        """Desativa o OpenVPN e o remove."""
        clear_screen()
        print_colored_box("REMOVER OPENVPN")
        is_installed, _ = self._check_openvpn_status()
        if not is_installed:
            print(f"{COLORS.RED}OpenVPN não está instalado.{COLORS.END}")
            return

        confirm = input(f"{COLORS.YELLOW}Tem certeza que deseja remover o OpenVPN? (s/N): {COLORS.END}").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return

        print(f"{COLORS.YELLOW}Parando e desativando serviço OpenVPN...{COLORS.END}")
        self._run_command(["sudo", "systemctl", "stop", "openvpn@server"], check_error=False)
        self._run_command(["sudo", "systemctl", "disable", "openvpn@server"], check_error=False)

        print(f"{COLORS.YELLOW}Removendo arquivos de configuração...{COLORS.END}")
        self._run_command(["sudo", "rm", "-rf", "/etc/openvpn"], check_error=False)
        self._run_command(["sudo", "rm", "-f", self.compiled_openvpn_go], check_error=False)

        print(f"{COLORS.YELLOW}Removendo pacotes...{COLORS.END}")
        self._run_command(["sudo", "apt-get", "remove", "--purge", "-y", "openvpn", "easy-rsa"], check_error=False)
        self._run_command(["sudo", "apt-get", "autoremove", "-y"], check_error=False)
        self._run_command(["sudo", "yum", "remove", "-y", "openvpn", "easy-rsa"], check_error=False)

        print(f"\n{COLORS.GREEN}OpenVPN removido com sucesso.{COLORS.END}")

def main_menu():
    """Menu principal do OpenVPN."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)
        
    manager = OpenVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.display_status()
            print_colored_box("GERENCIADOR OPENVPN", [f"Status: {status_line}"])
            
            print_menu_option("1", "Instalar OpenVPN", color=COLORS.CYAN)
            print_menu_option("2", "Alterar Porta", color=COLORS.CYAN)
            print_menu_option("3", "Reiniciar OpenVPN", color=COLORS.CYAN)
            print_menu_option("4", "Remover OpenVPN", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1':
                manager.install_openvpn()
            elif choice == '2':
                manager.change_port()
            elif choice == '3':
                manager.restart_openvpn()
            elif choice == '4':
                manager.remove_openvpn()
            elif choice == '0':
                break
            else:
                print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
                
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")
            
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"\n{COLORS.RED}Erro inesperado: {e}{COLORS.END}")
            input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
