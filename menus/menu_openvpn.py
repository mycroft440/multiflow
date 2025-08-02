

import os
import subprocess
import re
import time

class OpenVPNManager:
    def __init__(self):
        self.openvpn_go_path = "/home/ubuntu/multiflow/conexoes/openvpn.go"
        self.compiled_openvpn_go = "/usr/local/bin/openvpn_manager"
        self.server_conf_path = "/etc/openvpn/server.conf"

    def _run_command(self, command, check_error=True):
        """Executa um comando shell e retorna a saída."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=check_error)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Erro ao executar comando: {e.cmd}")
            print(f"Saída: {e.stdout}")
            print(f"Erro: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"Comando não encontrado: {command[0]}")
            return None

    def _check_openvpn_status(self):
        """Verifica se o OpenVPN está instalado e rodando."""
        try:
            # Verifica se o serviço openvpn@server está ativo
            status_output = self._run_command(["systemctl", "is-active", "openvpn@server"], check_error=False)
            if status_output == "active":
                # Tenta obter a porta do server.conf
                if os.path.exists(self.server_conf_path):
                    with open(self.server_conf_path, "r") as f:
                        content = f.read()
                        match = re.search(r"port (\d+)", content)
                        if match:
                            return True, match.group(1)
                return True, "1194" # Porta padrão se não encontrar no conf
            return False, None
        except:
            return False, None

    def display_status(self):
        """Exibe o status atual do OpenVPN."""
        is_running, port = self._check_openvpn_status()
        if is_running:
            print(f"Status: Rodando em {port}")
        else:
            print("Status: Não instalado")

    def install_openvpn(self):
        """Instala o OpenVPN utilizando o arquivo openvpn.go."""
        print("=== Instalando OpenVPN ===")
        
        # Compila o arquivo openvpn.go
        print("Compilando openvpn.go...")
        compile_cmd = ["go", "build", "-o", self.compiled_openvpn_go, self.openvpn_go_path]
        if self._run_command(compile_cmd) is None:
            print("✗ Erro ao compilar openvpn.go. Certifique-se de que o Go está instalado.")
            return
        
        # Torna o executável
        os.chmod(self.compiled_openvpn_go, 0o755)
        
        print("Iniciando instalação do OpenVPN...")
        # Executa o script Go compilado para instalar o OpenVPN
        # O script Go interage com o usuário para porta e DNS, então não podemos passar argumentos aqui diretamente.
        # O usuário precisará interagir com o terminal.
        try:
            subprocess.run(["sudo", self.compiled_openvpn_go], check=True)
            print("✓ OpenVPN instalado com sucesso!")
        except subprocess.CalledProcessError:
            print("✗ A instalação do OpenVPN foi interrompida ou falhou.")

    def change_port(self):
        """Altera a porta do OpenVPN."""
        print("=== Alterar Porta ===")
        is_installed, current_port = self._check_openvpn_status()
        if not is_installed:
            print("✗ OpenVPN não está instalado.")
            return

        new_port = input(f"Digite a nova porta (atual: {current_port}): ").strip()
        if not new_port.isdigit() or not (1 <= int(new_port) <= 65535):
            print("✗ Porta inválida. Digite um número entre 1 e 65535.")
            return

        try:
            # Lê o arquivo de configuração
            with open(self.server_conf_path, "r") as f:
                lines = f.readlines()

            # Altera a porta
            with open(self.server_conf_path, "w") as f:
                for line in lines:
                    if line.startswith("port "):
                        f.write(f"port {new_port}\n")
                    else:
                        f.write(line)
            
            # Atualiza regras do iptables (remove a antiga, adiciona a nova)
            self._run_command(["sudo", "iptables", "-D", "INPUT", "-p", "udp", "--dport", current_port, "-j", "ACCEPT"], check_error=False)
            self._run_command(["sudo", "iptables", "-A", "INPUT", "-p", "udp", "--dport", new_port, "-j", "ACCEPT"])
            self._run_command(["sudo", "iptables-save"], check_error=False)

            self.restart_openvpn()
            print(f"✓ Porta alterada para {new_port} e OpenVPN reiniciado.")
        except Exception as e:
            print(f"✗ Erro ao alterar porta: {e}")

    def change_dns(self):
        """Altera o DNS do OpenVPN."""
        print("=== Alterar DNS ===")
        is_installed, _ = self._check_openvpn_status()
        if not is_installed:
            print("✗ OpenVPN não está instalado.")
            return

        print("Escolha uma opção de DNS:")
        print("1. Google (8.8.8.8, 8.8.4.4)")
        print("2. Cloudflare (1.1.1.1, 1.0.0.1)")
        print("3. OpenDNS (208.67.222.222, 208.67.220.220)")
        print("4. Personalizado")
        
        choice = input("Opção: ").strip()
        dns1, dns2 = "", ""

        if choice == '1':
            dns1, dns2 = "8.8.8.8", "8.8.4.4"
        elif choice == '2':
            dns1, dns2 = "1.1.1.1", "1.0.0.1"
        elif choice == '3':
            dns1, dns2 = "208.67.222.222", "208.67.220.220"
        elif choice == '4':
            dns1 = input("Digite o DNS primário: ").strip()
            dns2 = input("Digite o DNS secundário (opcional, deixe em branco para pular): ").strip()
        else:
            print("✗ Opção inválida.")
            return

        try:
            with open(self.server_conf_path, "r") as f:
                lines = f.readlines()

            with open(self.server_conf_path, "w") as f:
                for line in lines:
                    if line.startswith("push \"dhcp-option DNS "):
                        continue # Remove linhas de DNS existentes
                    f.write(line)
                f.write(f"push \"dhcp-option DNS {dns1}\"\n")
                if dns2:
                    f.write(f"push \"dhcp-option DNS {dns2}\"\n")
            
            self.restart_openvpn()
            print(f"✓ DNS alterado para {dns1} e {dns2} (se aplicável) e OpenVPN reiniciado.")
        except Exception as e:
            print(f"✗ Erro ao alterar DNS: {e}")

    def restart_openvpn(self):
        """Reinicia o OpenVPN."""
        print("=== Reiniciar OpenVPN ===")
        is_installed, _ = self._check_openvpn_status()
        if not is_installed:
            print("✗ OpenVPN não está instalado.")
            return

        print("Reiniciando serviço OpenVPN...")
        if self._run_command(["sudo", "systemctl", "restart", "openvpn@server"]) is None:
            print("✗ Erro ao reiniciar OpenVPN.")
            return
        print("✓ OpenVPN reiniciado com sucesso.")

    def remove_openvpn(self):
        """Desativa o OpenVPN e o remove."""
        print("=== Remover OpenVPN ===")
        is_installed, _ = self._check_openvpn_status()
        if not is_installed:
            print("✗ OpenVPN não está instalado.")
            return

        confirm = input("Tem certeza que deseja remover o OpenVPN? (s/N): ").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return

        print("Parando e desativando serviço OpenVPN...")
        self._run_command(["sudo", "systemctl", "stop", "openvpn@server"], check_error=False)
        self._run_command(["sudo", "systemctl", "disable", "openvpn@server"], check_error=False)

        print("Removendo arquivos de configuração...")
        self._run_command(["sudo", "rm", "-rf", "/etc/openvpn"], check_error=False)
        self._run_command(["sudo", "rm", "-f", self.compiled_openvpn_go], check_error=False)

        print("Removendo pacotes...")
        # Tenta remover pacotes via apt (Debian/Ubuntu)
        self._run_command(["sudo", "apt-get", "remove", "--purge", "-y", "openvpn", "easy-rsa"], check_error=False)
        self._run_command(["sudo", "apt-get", "autoremove", "-y"], check_error=False)
        # Tenta remover pacotes via yum (CentOS/RHEL)
        self._run_command(["sudo", "yum", "remove", "-y", "openvpn", "easy-rsa"], check_error=False)

        print("✓ OpenVPN removido com sucesso.")

def main_menu():
    """Menu principal do OpenVPN."""
    manager = OpenVPNManager()
    
    while True:
        try:
            print("\n" + "="*40)
            print("         MENU OPENVPN")
            print("="*40)
            
            manager.display_status()
            
            print("\nOpções:")
            print("1. Instalar OpenVPN")
            print("2. Alterar Porta")
            print("3. Alterar DNS")
            print("4. Reiniciar OpenVPN")
            print("5. Remover OpenVPN")
            print("0. Voltar")
            print("-" * 40)
            
            choice = input("Escolha uma opção (0-5): ").strip()
            
            if choice == '1':
                manager.install_openvpn()
            elif choice == '2':
                manager.change_port()
            elif choice == '3':
                manager.change_dns()
            elif choice == '4':
                manager.restart_openvpn()
            elif choice == '5':
                manager.remove_openvpn()
            elif choice == '0':
                print("Voltando ao menu anterior...")
                break
            else:
                print("✗ Opção inválida. Tente novamente.")
                
            input("\nPressione Enter para continuar...")
            
        except KeyboardInterrupt:
            print("\n\nSaindo...")
            break
        except Exception as e:
            print(f"✗ Erro inesperado: {e}")
            input("\nPressione Enter para continuar...")

if __name__ == "__main__":
    main_menu()


