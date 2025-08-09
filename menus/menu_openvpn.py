#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import re
import time
import shutil
from pathlib import Path

# Adiciona o diretório pai ao sys.path para importações relativas
sys.path.append(str(Path(__file__).parent.parent))

try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError as e:
    print(f"Erro de importação: {e}. Certifique-se de que o projeto Multiflow está em /opt/multiflow.")
    # Fallback para o caso de o script ser executado de forma isolada
    class Colors:
        RED = GREEN = YELLOW = CYAN = BOLD = END = ""
    class BoxChars:
        BOTTOM_LEFT = BOTTOM_RIGHT = HORIZONTAL = ""
    def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')
    def print_colored_box(title, content=None): print(f"--- {title} ---")
    def print_menu_option(num, desc, **kwargs): print(f"{num}. {desc}")

# Instancia as cores para uso no script
COLORS = Colors()

class OpenVPNManager:
    """
    Classe para gerenciar a instalação e configuração do OpenVPN.
    """
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.install_script_path = self.base_dir / 'conexoes' / 'openvpn.sh'
        self.config_file = Path("/etc/openvpn/server.conf")
        self.log_file = Path("/var/log/openvpn/openvpn.log")
        self.status_log_file = Path("/var/log/openvpn/openvpn-status.log")

    def _is_installed(self):
        """Verifica se o OpenVPN está instalado checando o arquivo de configuração."""
        return self.config_file.exists()

    def _run_command(self, command, check=True, capture_output=True, text=True):
        """Executa um comando de shell de forma segura."""
        try:
            return subprocess.run(command, check=check, capture_output=capture_output, text=text)
        except FileNotFoundError:
            print(f"{COLORS.RED}Comando '{command[0]}' não encontrado.{COLORS.END}")
            return None
        except subprocess.CalledProcessError as e:
            print(f"{COLORS.RED}Erro ao executar comando: {e.stderr}{COLORS.END}")
            return None

    def _run_interactive_command(self, command):
        """Executa um comando e mostra a saída em tempo real."""
        try:
            process = subprocess.Popen(command, text=True)
            process.wait()
            return process.returncode == 0
        except Exception as e:
            print(f"\n{COLORS.RED}Ocorreu um erro: {e}{COLORS.END}")
            return False

    def get_openvpn_version(self):
        """Obtém a versão do OpenVPN instalada."""
        if not shutil.which("openvpn"):
            return "N/A"
        try:
            result = self._run_command(["openvpn", "--version"])
            if result and result.returncode == 0:
                # Pega a primeira linha da saída, ex: "OpenVPN 2.5.1 x86_64-pc-linux-gnu ..."
                first_line = result.stdout.splitlines()[0]
                match = re.search(r"OpenVPN\s+([\d\.]+)", first_line)
                if match:
                    return match.group(1)
            return "Desconhecida"
        except Exception:
            return "Erro"

    def get_status(self):
        """Obtém e formata o status atual do serviço OpenVPN."""
        if not self._is_installed():
            return [f"Status: {COLORS.YELLOW}Não Instalado{COLORS.END}"]

        try:
            result = self._run_command(["systemctl", "is-active", "openvpn@server"], check=False)
            status = f"{COLORS.GREEN}Ativo{COLORS.END}" if result and result.stdout.strip() == "active" else f"{COLORS.RED}Inativo{COLORS.END}"
            
            content = self.config_file.read_text()
            port_match = re.search(r'^port\s+(\d+)', content, re.MULTILINE)
            proto_match = re.search(r'^proto\s+(tcp|udp)', content, re.MULTILINE)
            
            port = port_match.group(1) if port_match else "N/A"
            protocol = proto_match.group(1).upper() if proto_match else "N/A"
            version = self.get_openvpn_version()
            
            status_line1 = f"Status: {status} | Porta: {COLORS.CYAN}{port}{COLORS.END} | Protocolo: {COLORS.CYAN}{protocol}{COLORS.END}"
            status_line2 = f"Versão Instalada: {COLORS.CYAN}{version}{COLORS.END}"
            
            return [status_line1, status_line2]
        except Exception as e:
            return [f"Status: {COLORS.RED}Erro ao obter informações ({e}){COLORS.END}"]

    def install_openvpn(self):
        """Executa o script de instalação interativo do OpenVPN."""
        clear_screen()
        print_colored_box("INSTALAR OPENVPN")
        if not self.install_script_path.exists():
            print(f"\n{COLORS.RED}✗ Script de instalação '{self.install_script_path}' não encontrado.{COLORS.END}")
            return

        print(f"{COLORS.YELLOW}Iniciando o assistente de instalação do OpenVPN...{COLORS.END}")
        print("Siga as instruções na tela.")
        print("-" * 60)
        
        # Garante que o script seja executável
        self._run_command(['chmod', '+x', str(self.install_script_path)])
        
        # Deixa o controle para o script de instalação
        clear_screen()
        self._run_interactive_command(['bash', str(self.install_script_path)])
        
        print("-" * 60)
        print(f"{COLORS.GREEN}✓ Assistente de instalação finalizado.{COLORS.END}")

    def show_logs(self):
        """Exibe os logs de status e de operação do OpenVPN."""
        clear_screen()
        print_colored_box("LOGS DO OPENVPN")
        if not self._is_installed():
            print(f"\n{COLORS.YELLOW}OpenVPN não instalado. Nenhum log para mostrar.{COLORS.END}")
            return

        print(f"{COLORS.CYAN}--- Log de Status ({self.status_log_file}) ---{COLORS.END}")
        if self.status_log_file.exists():
            print(self.status_log_file.read_text())
        else:
            print("Arquivo de log de status não encontrado.")

        print(f"\n{COLORS.CYAN}--- Log de Operação ({self.log_file}) ---{COLORS.END}")
        if self.log_file.exists():
            # Mostra as últimas 20 linhas para não poluir a tela
            log_lines = self.log_file.read_text().splitlines()
            for line in log_lines[-20:]:
                print(line)
        else:
            print("Arquivo de log de operação não encontrado.")

    def _restart_service(self):
        """Reinicia o serviço OpenVPN e verifica o status."""
        print(f"\n{COLORS.YELLOW}Reiniciando o serviço OpenVPN...{COLORS.END}")
        self._run_command(["systemctl", "restart", "openvpn@server"])
        time.sleep(3) # Aguarda o serviço reiniciar
        result = self._run_command(["systemctl", "is-active", "openvpn@server"], check=False)
        if result and result.stdout.strip() == "active":
            print(f"{COLORS.GREEN}✓ Serviço reiniciado com sucesso!{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ Falha ao reiniciar o serviço. Verifique os logs.{COLORS.END}")

    def _update_config(self, pattern, replacement):
        """Função genérica para atualizar uma linha no arquivo de configuração."""
        if not self._is_installed():
            print(f"\n{COLORS.YELLOW}OpenVPN não está instalado. Instale primeiro.{COLORS.END}")
            return
        try:
            content = self.config_file.read_text()
            new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
            if count == 0:
                print(f"{COLORS.RED}✗ Configuração não encontrada no arquivo. Nenhuma alteração feita.{COLORS.END}")
                return
            self.config_file.write_text(new_content)
            print(f"{COLORS.GREEN}✓ Arquivo de configuração atualizado.{COLORS.END}")
            self._restart_service()
        except Exception as e:
            print(f"{COLORS.RED}✗ Erro ao atualizar configuração: {e}{COLORS.END}")

    def change_protocol(self):
        """Altera o protocolo (UDP/TCP) no arquivo de configuração."""
        clear_screen()
        print_colored_box("ALTERAR PROTOCOLO")
        choice = input(f"{COLORS.CYAN}Escolha o novo protocolo [1] UDP (padrão) / [2] TCP: {COLORS.END}").strip()
        new_proto = "udp" if choice != '2' else "tcp"
        self._update_config(r'^proto\s+(udp|tcp)', f'proto {new_proto}')

    def change_dns(self):
        """Altera os servidores DNS no arquivo de configuração."""
        clear_screen()
        print_colored_box("ALTERAR DNS")
        print_menu_option("1", "Google (8.8.8.8, 8.8.4.4)", color=COLORS.CYAN)
        print_menu_option("2", "Cloudflare (1.1.1.1, 1.0.0.1)", color=COLORS.CYAN)
        print_menu_option("3", "OpenDNS (208.67.222.222, 208.67.220.220)", color=COLORS.CYAN)
        choice = input(f"\n{COLORS.BOLD}Escolha o novo provedor de DNS: {COLORS.END}").strip()

        dns_map = {
            "1": ("8.8.8.8", "8.8.4.4"),
            "2": ("1.1.1.1", "1.0.0.1"),
            "3": ("208.67.222.222", "208.67.220.220"),
        }
        if choice not in dns_map:
            print(f"\n{COLORS.RED}Opção inválida.{COLORS.END}")
            return
        
        dns1, dns2 = dns_map[choice]
        replacement = f'push "dhcp-option DNS {dns1}"\npush "dhcp-option DNS {dns2}"'
        self._update_config(r'push "dhcp-option DNS .*', replacement)


    def change_port(self):
        """Altera a porta no arquivo de configuração."""
        clear_screen()
        print_colored_box("ALTERAR PORTA")
        new_port = input(f"{COLORS.CYAN}Digite a nova porta (ex: 1194): {COLORS.END}").strip()
        if not new_port.isdigit() or not (1 <= int(new_port) <= 65535):
            print(f"\n{COLORS.RED}Porta inválida.{COLORS.END}")
            return
        self._update_config(r'^port\s+\d+', f'port {new_port}')

    def uninstall_openvpn(self):
        """Remove completamente o OpenVPN e suas configurações."""
        clear_screen()
        print_colored_box("DESINSTALAR OPENVPN")
        if not self._is_installed():
            print(f"\n{COLORS.YELLOW}OpenVPN não parece estar instalado.{COLORS.END}")
            return
        
        confirm = input(f"{COLORS.RED}{COLORS.BOLD}AVISO: Esta ação é irreversível e removerá TUDO.\nDigite 'sim' para confirmar: {COLORS.END}").strip().lower()
        if confirm != 'sim':
            print(f"\n{COLORS.YELLOW}Desinstalação cancelada.{COLORS.END}")
            return

        print(f"\n{COLORS.YELLOW}Parando e desabilitando serviços...{COLORS.END}")
        self._run_command(['systemctl', 'stop', 'openvpn@server'], check=False)
        self._run_command(['systemctl', 'disable', 'openvpn@server'], check=False)

        print(f"{COLORS.YELLOW}Removendo pacotes...{COLORS.END}")
        self._run_command(['apt-get', 'remove', '--purge', '-y', 'openvpn', 'easy-rsa'], check=False)
        self._run_command(['apt-get', 'autoremove', '-y'], check=False)
        
        print(f"{COLORS.YELLOW}Removendo arquivos de configuração e logs...{COLORS.END}")
        shutil.rmtree(self.config_file.parent, ignore_errors=True)
        shutil.rmtree(self.log_file.parent, ignore_errors=True)
        
        # Limpa regras de firewall persistentes
        if Path('/etc/iptables/rules.v4').exists():
             print(f"{COLORS.YELLOW}Limpando regras de firewall...{COLORS.END}")
             self._run_command(['iptables', '-F'])
             self._run_command(['iptables', '-t', 'nat', '-F'])
             self._run_command(['iptables-save', '>', '/etc/iptables/rules.v4'], check=False)


        print(f"\n{COLORS.GREEN}✓ OpenVPN desinstalado com sucesso.{COLORS.END}")

def main_menu():
    """Exibe e gerencia o menu principal."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    manager = OpenVPNManager()
    
    while True:
        clear_screen()
        status_lines = manager.get_status()
        print_colored_box("GERENCIADOR OPENVPN", status_lines)
        
        is_installed = manager._is_installed()
        
        if not is_installed:
            print_menu_option("1", "Instalar OpenVPN", color=COLORS.GREEN)
        else:
            print_menu_option("1", "Reinstalar OpenVPN (apaga config atual)", color=COLORS.YELLOW)
            print_menu_option("2", "Ver Logs da Instalação/Status", color=COLORS.CYAN)
            print_menu_option("3", "Alterar Protocolo (UDP/TCP)", color=COLORS.CYAN)
            print_menu_option("4", "Alterar Servidores DNS", color=COLORS.CYAN)
            print_menu_option("5", "Alterar Porta", color=COLORS.CYAN)
            print_menu_option("6", "Desinstalar OpenVPN", color=COLORS.RED)

        print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
        
        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
        
        if choice == '1':
            manager.install_openvpn()
        elif choice == '0':
            break
        elif is_installed:
            if choice == '2': manager.show_logs()
            elif choice == '3': manager.change_protocol()
            elif choice == '4': manager.change_dns()
            elif choice == '5': manager.change_port()
            elif choice == '6': manager.uninstall_openvpn()
            else: print(f"\n{COLORS.RED}Opção inválida.{COLORS.END}")
        else:
            print(f"\n{COLORS.RED}Opção inválida.{COLORS.END}")
            
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
