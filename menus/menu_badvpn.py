
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import signal
import psutil
from pathlib import Path

class BadVPNManager:
    def __init__(self):
        self.badvpn_executable = "/usr/local/bin/badvpn-udpgw"
        self.custom_badvpn_path = "/home/ubuntu/multiflow/conexoes/BadVPN.c"
        self.compiled_badvpn = "/usr/local/bin/custom_badvpn"
        self.active_ports = []
        self.processes = {}
        
    def check_badvpn_status(self):
        """Verifica se o BadVPN está instalado e rodando"""
        try:
            # Verifica se o processo está rodando
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'badvpn' in proc.info['name'].lower() or \
                   (proc.info['cmdline'] and any('badvpn' in cmd.lower() for cmd in proc.info['cmdline'])):
                    return True, proc.info['pid']
            return False, None
        except:
            return False, None
    
    def get_active_ports(self):
        """Obtém as portas ativas do BadVPN"""
        active_ports = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['cmdline'] and any('badvpn' in cmd.lower() for cmd in proc.info['cmdline']):
                    cmdline = ' '.join(proc.info['cmdline'])
                    if '--listen-addr' in cmdline:
                        # Extrai a porta da linha de comando
                        parts = cmdline.split('--listen-addr')
                        if len(parts) > 1:
                            addr_part = parts[1].split()[0]
                            if ':' in addr_part:
                                port = addr_part.split(':')[-1]
                                active_ports.append(port)
        except:
            pass
        return active_ports if active_ports else ['7300'] if self.check_badvpn_status()[0] else []

    def install_badvpn(self):
        """Instala o BadVPN"""
        print("=== Instalando BadVPN ===")
        
        try:
            # Primeiro tenta instalar o BadVPN padrão
            print("Tentando instalar BadVPN via apt...")
            result = subprocess.run(['sudo', 'apt-get', 'update'], capture_output=True, text=True)
            if result.returncode == 0:
                result = subprocess.run(['sudo', 'apt-get', 'install', '-y', 'badvpn'], 
                                      capture_output=True, text=True)
            
            # Se não conseguir instalar via apt, compila o código customizado
            if result.returncode != 0 or not os.path.exists('/usr/bin/badvpn-udpgw'):
                print("BadVPN não encontrado no repositório. Compilando versão customizada...")
                self.compile_custom_badvpn()
            
            # Inicia o BadVPN na porta 7300
            self.start_badvpn_port(7300)
            print("✓ BadVPN instalado e iniciado na porta 7300")
            
        except Exception as e:
            print(f"✗ Erro ao instalar BadVPN: {e}")

    def compile_custom_badvpn(self):
        """Compila o código C customizado do BadVPN"""
        try:
            print("Compilando BadVPN customizado...")
            
            # Instala dependências de compilação
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'build-essential'], 
                          capture_output=True, text=True)
            
            # Compila o código C
            compile_cmd = [
                'gcc', '-o', self.compiled_badvpn, 
                self.custom_badvpn_path, 
                '-lpthread'
            ]
            
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Torna executável
                os.chmod(self.compiled_badvpn, 0o755)
                print("✓ BadVPN customizado compilado com sucesso")
            else:
                raise Exception(f"Erro na compilação: {result.stderr}")
                
        except Exception as e:
            print(f"✗ Erro ao compilar BadVPN: {e}")
            raise

    def start_badvpn_port(self, port):
        """Inicia BadVPN em uma porta específica"""
        try:
            # Verifica se já está rodando nesta porta
            if str(port) in self.get_active_ports():
                print(f"BadVPN já está rodando na porta {port}")
                return True
            
            # Comando para iniciar BadVPN
            if os.path.exists('/usr/bin/badvpn-udpgw'):
                cmd = ['sudo', 'badvpn-udpgw', '--listen-addr', f'127.0.0.1:{port}', 
                       '--max-clients', '1000']
            elif os.path.exists(self.compiled_badvpn):
                # Usa a versão customizada compilada
                cmd = ['sudo', self.compiled_badvpn]
            else:
                raise Exception("BadVPN não encontrado")
            
            # Inicia o processo em background
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
            
            self.processes[port] = process.pid
            print(f"✓ BadVPN iniciado na porta {port}")
            return True
            
        except Exception as e:
            print(f"✗ Erro ao iniciar BadVPN na porta {port}: {e}")
            return False

    def add_port(self):
        """Adiciona uma nova porta ao BadVPN"""
        print("=== Adicionar Porta ===")
        
        try:
            port = input("Digite a porta a ser adicionada: ").strip()
            
            if not port.isdigit():
                print("✗ Porta deve ser um número válido")
                return
            
            port = int(port)
            
            if port < 1 or port > 65535:
                print("✗ Porta deve estar entre 1 e 65535")
                return
            
            if self.start_badvpn_port(port):
                print(f"✓ Porta {port} adicionada com sucesso")
            else:
                print(f"✗ Falha ao adicionar porta {port}")
                
        except KeyboardInterrupt:
            print("\nOperação cancelada")
        except Exception as e:
            print(f"✗ Erro ao adicionar porta: {e}")

    def remove_port(self):
        """Remove uma porta do BadVPN"""
        print("=== Remover Porta ===")
        
        active_ports = self.get_active_ports()
        if not active_ports:
            print("✗ Nenhuma porta ativa encontrada")
            return
        
        print("Portas ativas:", ", ".join(active_ports))
        
        try:
            port = input("Digite a porta a ser removida: ").strip()
            
            if port not in active_ports:
                print(f"✗ Porta {port} não está ativa")
                return
            
            # Mata o processo da porta específica
            killed = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['cmdline'] and any('badvpn' in cmd.lower() for cmd in proc.info['cmdline']):
                    cmdline = ' '.join(proc.info['cmdline'])
                    if f':{port}' in cmdline or f' {port}' in cmdline:
                        try:
                            proc.kill()
                            killed = True
                            print(f"✓ Porta {port} removida com sucesso")
                            break
                        except:
                            pass
            
            if not killed:
                print(f"✗ Não foi possível remover a porta {port}")
                
        except KeyboardInterrupt:
            print("\nOperação cancelada")
        except Exception as e:
            print(f"✗ Erro ao remover porta: {e}")

    def remove_badvpn(self):
        """Remove completamente o BadVPN"""
        print("=== Removendo BadVPN ===")
        
        try:
            # Confirma a remoção
            confirm = input("Tem certeza que deseja remover o BadVPN? (s/N): ").strip().lower()
            if confirm not in ['s', 'sim', 'y', 'yes']:
                print("Operação cancelada")
                return
            
            # Para todos os processos do BadVPN
            killed_processes = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['cmdline'] and any('badvpn' in cmd.lower() for cmd in proc.info['cmdline']):
                    try:
                        proc.kill()
                        killed_processes += 1
                    except:
                        pass
            
            # Remove arquivos instalados
            files_to_remove = [
                '/usr/bin/badvpn-udpgw',
                '/usr/local/bin/badvpn-udpgw', 
                self.compiled_badvpn
            ]
            
            for file_path in files_to_remove:
                if os.path.exists(file_path):
                    try:
                        subprocess.run(['sudo', 'rm', '-f', file_path], capture_output=True)
                    except:
                        pass
            
            # Remove pacote se instalado via apt
            subprocess.run(['sudo', 'apt-get', 'remove', '-y', 'badvpn'], 
                          capture_output=True, text=True)
            
            print(f"✓ BadVPN removido ({killed_processes} processos finalizados)")
            
        except KeyboardInterrupt:
            print("\nOperação cancelada")
        except Exception as e:
            print(f"✗ Erro ao remover BadVPN: {e}")

    def display_status(self):
        """Exibe o status atual do BadVPN"""
        is_running, pid = self.check_badvpn_status()
        active_ports = self.get_active_ports()
        
        print(f"Status: {'ativo' if is_running else 'inativo'}")
        if active_ports:
            print(f"Portas: {', '.join(active_ports)}")
        else:
            print("Portas: nenhuma")
        
        if is_running and pid:
            print(f"PID: {pid}")

def main_menu():
    """Menu principal do BadVPN"""
    manager = BadVPNManager()
    
    while True:
        try:
            print("\n" + "="*40)
            print("         MENU BADVPN")
            print("="*40)
            
            # Exibe status atual
            manager.display_status()
            
            print("\nOpções:")
            print("1. Instalar BadVPN")
            print("2. Adicionar Porta") 
            print("3. Remover Porta")
            print("4. Remover BadVPN")
            print("5. Voltar")
            print("-" * 40)
            
            choice = input("Escolha uma opção (1-5): ").strip()
            
            if choice == '1':
                manager.install_badvpn()
            elif choice == '2':
                manager.add_port()
            elif choice == '3':
                manager.remove_port()
            elif choice == '4':
                manager.remove_badvpn()
            elif choice == '5':
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


