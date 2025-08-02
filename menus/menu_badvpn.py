#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import signal
import psutil
from pathlib import Path

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

class BadVPNManager:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.custom_badvpn_source = os.path.join(self.base_dir, '..', 'conexoes', 'BadVPN.c')
        self.compiled_badvpn = "/usr/local/bin/custom_badvpn"
        self.badvpn_legacy = "/usr/bin/badvpn-udpgw" # Padrão do apt

    def _run_command(self, command, check_error=True):
        """Executa um comando shell."""
        try:
            subprocess.run(command, check=check_error, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"{COLORS.RED}Erro ao executar comando: {e}{COLORS.END}")
            return False

    def get_active_processes(self):
        """Retorna uma lista de processos BadVPN ativos."""
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Verifica pelo nome do executável ou pelo nome 'badvpn' no cmdline
                if (proc.info['name'] and 'badvpn' in proc.info['name'].lower()) or \
                   (proc.info['cmdline'] and any('badvpn' in cmd.lower() for cmd in proc.info['cmdline'])):
                    procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return procs

    def get_active_ports(self):
        """Obtém as portas ativas do BadVPN."""
        active_ports = []
        for proc in self.get_active_processes():
            try:
                cmdline = ' '.join(proc.cmdline())
                if '--listen-addr' in cmdline:
                    addr_part = cmdline.split('--listen-addr')[1].strip().split(' ')[0]
                    if ':' in addr_part:
                        port = addr_part.split(':')[-1]
                        active_ports.append(port)
            except:
                continue
        # Se não encontrar porta mas o processo existir, assume a porta padrão
        if not active_ports and self.get_active_processes():
            return ['7300']
        return sorted(list(set(active_ports)))


    def display_status(self):
        """Retorna uma string formatada com o status do BadVPN."""
        active_procs = self.get_active_processes()
        if not active_procs:
            return f"{COLORS.RED}Inativo{COLORS.END}"

        ports = self.get_active_ports()
        if ports:
            return f"{COLORS.GREEN}Ativo{COLORS.END}, Portas: {COLORS.YELLOW}{', '.join(ports)}{COLORS.END}"
        else:
            return f"{COLORS.GREEN}Ativo{COLORS.END} (Porta desconhecida)"

    def install_badvpn(self):
        """Instala e inicia o BadVPN."""
        clear_screen()
        print_colored_box("INSTALAR BADVPN")
        
        print(f"{COLORS.YELLOW}Tentando instalar BadVPN via apt...{COLORS.END}")
        if self._run_command(['sudo', 'apt-get', 'update'], check_error=False) and \
           self._run_command(['sudo', 'apt-get', 'install', '-y', 'badvpn'], check_error=False) and \
           os.path.exists(self.badvpn_legacy):
            print(f"{COLORS.GREEN}BadVPN instalado via apt com sucesso.{COLORS.END}")
            self.start_badvpn_port('7300')
            return

        print(f"{COLORS.YELLOW}Falha ao instalar via apt. Tentando compilar versão customizada...{COLORS.END}")
        if self.compile_custom_badvpn():
            self.start_badvpn_port('7300')

    def compile_custom_badvpn(self):
        """Compila o código C customizado do BadVPN."""
        if not os.path.exists(self.custom_badvpn_source):
            print(f"{COLORS.RED}Arquivo fonte '{self.custom_badvpn_source}' não encontrado.{COLORS.END}")
            return False
        
        print(f"{COLORS.YELLOW}Instalando dependências de compilação...{COLORS.END}")
        self._run_command(['sudo', 'apt-get', 'install', '-y', 'build-essential'])
        
        print(f"{COLORS.YELLOW}Compilando...{COLORS.END}")
        compile_cmd = ['gcc', '-o', self.compiled_badvpn, self.custom_badvpn_source, '-lpthread']
        if self._run_command(compile_cmd):
            self._run_command(['sudo', 'chmod', '+x', self.compiled_badvpn])
            print(f"{COLORS.GREEN}BadVPN customizado compilado com sucesso em '{self.compiled_badvpn}'.{COLORS.END}")
            return True
        else:
            print(f"{COLORS.RED}Falha na compilação.{COLORS.END}")
            return False

    def start_badvpn_port(self, port):
        """Inicia BadVPN em uma porta específica."""
        if str(port) in self.get_active_ports():
            print(f"{COLORS.YELLOW}BadVPN já está rodando na porta {port}.{COLORS.END}")
            return True
        
        # Prioriza o executável do apt se existir
        executable = self.badvpn_legacy if os.path.exists(self.badvpn_legacy) else self.compiled_badvpn
        if not os.path.exists(executable):
            print(f"{COLORS.RED}Nenhum executável do BadVPN encontrado. Por favor, instale primeiro.{COLORS.END}")
            return False

        cmd = ['sudo', executable, '--listen-addr', f'127.0.0.1:{port}', '--max-clients', '1000']
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1) # Dá um tempo para o processo iniciar
            if str(port) in self.get_active_ports():
                 print(f"{COLORS.GREEN}BadVPN iniciado com sucesso na porta {port}.{COLORS.END}")
                 return True
            else:
                 print(f"{COLORS.RED}Falha ao iniciar BadVPN na porta {port}.{COLORS.END}")
                 return False
        except Exception as e:
            print(f"{COLORS.RED}Erro ao iniciar BadVPN: {e}{COLORS.END}")
            return False

    def add_port(self):
        """Adiciona uma nova porta ao BadVPN."""
        clear_screen()
        print_colored_box("ADICIONAR PORTA BADVPN")
        try:
            port_str = input(f"{COLORS.CYAN}Digite a porta a ser adicionada: {COLORS.END}").strip()
            if not port_str.isdigit() or not (1 <= int(port_str) <= 65535):
                print(f"\n{COLORS.RED}Porta inválida.{COLORS.END}")
                return
            self.start_badvpn_port(port_str)
        except (KeyboardInterrupt, EOFError):
            print("\nOperação cancelada.")
        except Exception as e:
            print(f"\n{COLORS.RED}Erro ao adicionar porta: {e}{COLORS.END}")

    def remove_port(self):
        """Remove uma porta do BadVPN."""
        clear_screen()
        print_colored_box("REMOVER PORTA BADVPN")
        active_ports = self.get_active_ports()
        if not active_ports:
            print(f"{COLORS.YELLOW}Nenhuma porta ativa encontrada.{COLORS.END}")
            return
        
        print(f"Portas ativas: {COLORS.YELLOW}{', '.join(active_ports)}{COLORS.END}")
        port_to_remove = input(f"{COLORS.CYAN}Digite a porta a ser removida: {COLORS.END}").strip()

        if port_to_remove not in active_ports:
            print(f"\n{COLORS.RED}Porta {port_to_remove} não está ativa.{COLORS.END}")
            return

        killed = False
        for proc in self.get_active_processes():
            try:
                if f':{port_to_remove}' in ' '.join(proc.cmdline()):
                    proc.kill()
                    killed = True
                    print(f"\n{COLORS.GREEN}Processo na porta {port_to_remove} finalizado.{COLORS.END}")
                    break
            except:
                continue
        
        if not killed:
            print(f"\n{COLORS.RED}Não foi possível remover o processo da porta {port_to_remove}.{COLORS.END}")

    def remove_badvpn(self):
        """Remove completamente o BadVPN."""
        clear_screen()
        print_colored_box("REMOVER BADVPN")
        confirm = input(f"{COLORS.YELLOW}Tem certeza que deseja remover o BadVPN e parar todos os processos? (s/N): {COLORS.END}").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return

        print(f"{COLORS.YELLOW}Parando todos os processos BadVPN...{COLORS.END}")
        for proc in self.get_active_processes():
            try:
                proc.kill()
            except:
                pass
        
        print(f"{COLORS.YELLOW}Removendo arquivos e pacotes...{COLORS.END}")
        self._run_command(['sudo', 'rm', '-f', self.compiled_badvpn], check_error=False)
        self._run_command(['sudo', 'apt-get', 'remove', '--purge', '-y', 'badvpn'], check_error=False)
        self._run_command(['sudo', 'apt-get', 'autoremove', '-y'], check_error=False)
        
        print(f"\n{COLORS.GREEN}BadVPN removido com sucesso.{COLORS.END}")

def main_menu():
    """Menu principal do BadVPN."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)
        
    manager = BadVPNManager()
    
    while True:
        try:
            clear_screen()
            status_line = manager.display_status()
            print_colored_box("GERENCIADOR BADVPN", [f"Status: {status_line}"])
            
            print_menu_option("1", "Instalar BadVPN", color=COLORS.CYAN)
            print_menu_option("2", "Adicionar Porta", color=COLORS.CYAN) 
            print_menu_option("3", "Remover Porta", color=COLORS.CYAN)
            print_menu_option("4", "Remover BadVPN", color=COLORS.CYAN)
            print_menu_option("0", "Voltar ao Menu Anterior", color=COLORS.YELLOW)
            print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
            
            choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}").strip()
            
            if choice == '1':
                manager.install_badvpn()
            elif choice == '2':
                manager.add_port()
            elif choice == '3':
                manager.remove_port()
            elif choice == '4':
                manager.remove_badvpn()
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
