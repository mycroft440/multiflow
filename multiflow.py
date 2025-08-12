#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiFlowPX Proxy Server Manager
Sistema de gerenciamento para servidor proxy MultiFlowPX com interface CLI interativa.
"""

import os
import sys
import subprocess
import json
import time
import shutil
import re
from functools import wraps
from typing import Dict, List, Optional, Any

# --- Constantes de Configuração ---
CONFIG_FILE = "/etc/multiflowpx/config.json"
MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_WORKERS = 4
DEFAULT_BUFFER_SIZE = 8192
MIN_LOG_LEVEL = 0
MAX_LOG_LEVEL = 2

# --- Cores para o Terminal ---
class Colors:
    """Classe para gerenciar cores ANSI do terminal."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- Decorators ---
def requires_root(func):
    """Decorator para métodos que requerem privilégios root."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.check_root():
            return None
        return func(self, *args, **kwargs)
    return wrapper

def requires_systemctl(func):
    """Decorator para métodos que requerem systemctl."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.systemctl_path:
            self._notify_systemctl_unavailable()
            return None
        return func(self, *args, **kwargs)
    return wrapper

class ConfigManager:
    """Gerencia as configurações do proxy."""
    
    def __init__(self):
        self.default_config = {
            "mode": [],
            "port": [],
            "host": "127.0.0.1:22",
            "sni": "example.com",
            "workers": DEFAULT_WORKERS,
            "buffer_size": DEFAULT_BUFFER_SIZE,
            "log_level": 1
        }
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Carrega as configurações do arquivo JSON de forma robusta."""
        config = self.default_config.copy()
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    
                for key, default_value in self.default_config.items():
                    if key in loaded_config and isinstance(loaded_config[key], type(default_value)):
                        config[key] = loaded_config[key]
                    else:
                        print(f"{Colors.WARNING}[!] Aviso: Chave '{key}' ausente ou com tipo inválido. Usando valor padrão.{Colors.ENDC}")
        except (IOError, json.JSONDecodeError) as e:
            print(f"{Colors.WARNING}[!] Aviso: Não foi possível carregar configuração: {e}. Usando padrão.{Colors.ENDC}")
        
        # Validação adicional para listas
        for key in ['port', 'mode']:
            if not isinstance(config.get(key), list):
                config[key] = self.default_config[key]
        
        return config
    
    def save_config(self) -> bool:
        """Salva as configurações atuais no arquivo JSON."""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
            print(f"\n{Colors.GREEN}[✓] Configurações salvas com sucesso em {CONFIG_FILE}{Colors.ENDC}")
            return True
        except IOError as e:
            print(f"\n{Colors.FAIL}[!] Erro ao salvar as configurações: {e}{Colors.ENDC}")
            return False

class UIHelper:
    """Classe auxiliar para interface do usuário."""
    
    @staticmethod
    def clear_screen():
        """Limpa a tela do terminal."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    @staticmethod
    def strip_ansi_codes(text: str) -> str:
        """Remove códigos ANSI para cálculo correto de largura."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    @staticmethod
    def pad_ansi_text(text: str, width: int) -> str:
        """Preenche texto com códigos ANSI para largura específica."""
        clean_text = UIHelper.strip_ansi_codes(text)
        padding_needed = width - len(clean_text)
        if padding_needed > 0:
            return text + ' ' * padding_needed
        return text
    
    @staticmethod
    def print_header(title: str):
        """Exibe um cabeçalho padronizado."""
        UIHelper.clear_screen()
        print(f"{Colors.CYAN}╔══════════════════════════════════════════════════════════════╗{Colors.ENDC}")
        print(f"{Colors.CYAN}║{Colors.BOLD}           MULTIFLOWPX PROXY SERVER MANAGER                  {Colors.CYAN}║{Colors.ENDC}")
        print(f"{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.ENDC}")
        print(f"{Colors.CYAN}║  {Colors.HEADER}{title:^58}  {Colors.CYAN}║{Colors.ENDC}")
        print(f"{Colors.CYAN}╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}\n")
    
    @staticmethod
    def print_divider():
        """Imprime um divisor visual."""
        print(f"{Colors.CYAN}{'─' * 64}{Colors.ENDC}")
    
    @staticmethod
    def validate_port(port_str: str) -> Optional[int]:
        """Valida e retorna uma porta ou None se inválida."""
        try:
            port = int(port_str)
            if MIN_PORT <= port <= MAX_PORT:
                return port
            print(f"\n{Colors.FAIL}[!] Porta deve estar entre {MIN_PORT} e {MAX_PORT}.{Colors.ENDC}")
        except ValueError:
            print(f"\n{Colors.FAIL}[!] Entrada inválida. Digite um número.{Colors.ENDC}")
        return None

class ServiceManager:
    """Gerencia operações relacionadas ao serviço systemd."""
    
    def __init__(self):
        self.systemctl_path = shutil.which("systemctl")
    
    def is_available(self) -> bool:
        """Verifica se systemctl está disponível."""
        return bool(self.systemctl_path)
    
    def is_running(self) -> bool:
        """Verifica se o serviço está em execução."""
        if not self.systemctl_path:
            return False
        result = subprocess.run(
            [self.systemctl_path, "is-active", "--quiet", "multiflowpx.service"],
            capture_output=True
        )
        return result.returncode == 0
    
    def start(self) -> bool:
        """Inicia o serviço."""
        try:
            subprocess.run([self.systemctl_path, "start", "multiflowpx.service"], check=True)
            print(f"\n{Colors.GREEN}[✓] Proxy iniciado com sucesso via systemd.{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.FAIL}[!] Erro ao iniciar o proxy: {e}{Colors.ENDC}")
            return False
    
    def stop(self) -> bool:
        """Para o serviço."""
        try:
            subprocess.run([self.systemctl_path, "stop", "multiflowpx.service"], check=True)
            print(f"\n{Colors.GREEN}[✓] Proxy parado com sucesso via systemd.{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.FAIL}[!] Erro ao parar o proxy: {e}{Colors.ENDC}")
            return False
    
    def restart(self) -> bool:
        """Reinicia o serviço."""
        print(f"{Colors.WARNING}Reiniciando o serviço...{Colors.ENDC}")
        self.stop()
        time.sleep(1)
        return self.start()

class ProxyMenu:
    """Classe principal que gerencia o menu interativo para o MultiFlowPX Proxy Server."""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.service_manager = ServiceManager()
        self.ui = UIHelper()
        self.config = self.config_manager.config
        self.systemctl_path = self.service_manager.systemctl_path
    
    # --- Métodos de Verificação ---
    
    def check_root(self) -> bool:
        """Verifica se o script está sendo executado como root."""
        if not hasattr(os, 'geteuid'):
            print(f"\n{Colors.WARNING}[!] Aviso: Não foi possível verificar privilégios de root.{Colors.ENDC}")
            return True
        
        if os.geteuid() != 0:
            print(f"\n{Colors.FAIL}[!] Erro: Esta operação requer privilégios de root. Execute com 'sudo'.{Colors.ENDC}")
            input("\n    Pressione Enter para continuar...")
            return False
        return True
    
    def _notify_systemctl_unavailable(self):
        """Informa ao usuário que o systemctl não está disponível."""
        print(f"\n{Colors.FAIL}[!] Erro: O comando 'systemctl' não foi encontrado.{Colors.ENDC}")
        print(f"{Colors.WARNING}Este script requer um sistema baseado em systemd.")
        print(f"As funções de gerenciamento de serviço estão desativadas.{Colors.ENDC}")
    
    def find_install_script(self) -> Optional[str]:
        """Detecta dinamicamente o script de instalação 'install.sh'."""
        potential_paths = [
            '/root/multiflowpx/install.sh',
            os.path.join(os.path.expanduser("~"), 'multiflowpx/install.sh'),
            './install.sh'
        ]
        
        for path in potential_paths:
            if os.path.isfile(path):
                print(f"{Colors.GREEN}[✓] Script de instalação encontrado em: {path}{Colors.ENDC}")
                return path
        return None
    
    # --- Métodos de Entrada do Usuário ---
    
    def _ask_ssl_domain(self) -> str:
        """Pergunta o domínio para emissão de certificado quando SSL for selecionado."""
        self.ui.print_divider()
        print(f"{Colors.WARNING}CONFIGURAÇÃO DE CERTIFICADO SSL{Colors.ENDC}\n")
        print("Digite o seu domínio que é apontado para o seu servidor para")
        print("que se gere um certificado funcional para o mesmo.")
        self.ui.print_divider()
        return input(f"{Colors.BOLD}Digite [exemplo: mycroft.multflowmanager.xyz]:{Colors.ENDC} ").strip()
    
    def _ask_for_install_port(self) -> int:
        """Pergunta e valida a porta principal durante a instalação."""
        self.ui.print_divider()
        print(f"{Colors.BOLD}CONFIGURAÇÃO DA PORTA PRINCIPAL{Colors.ENDC}")
        
        while True:
            port_input = input(f"{Colors.BOLD}Digite a porta que deseja usar para o serviço: {Colors.ENDC}")
            port = self.ui.validate_port(port_input)
            if port:
                return port
    
    def _ask_for_protocols(self) -> List[str]:
        """Pergunta e valida a combinação de protocolos."""
        self.ui.print_divider()
        print(f"{Colors.BOLD}CONFIGURAÇÃO DOS PROTOCOLOS{Colors.ENDC}\n")
        
        protocol_map = {
            '1': (['ssh', 'openvpn', 'v2ray'], "ssh, openvpn, v2ray"),
            '2': (['ssh', 'openvpn', 'v2ray', 'ssl'], "ssh, openvpn, v2ray e ssl"),
            '3': (['ssh', 'v2ray'], "ssh e v2ray"),
            '4': (['ssh', 'openvpn'], "ssh e openvpn"),
            '5': (['ssh', 'ssl'], "ssh e ssl"),
            '6': (['ssh'], "Apenas SSH"),
            '7': (['openvpn'], "Apenas OpenVPN")
        }
        
        print("Em qual protocolo deseja utilizar o serviço?")
        for key, (_, text) in protocol_map.items():
            print(f"  [{Colors.BOLD}{key}{Colors.ENDC}] {text}")
        
        while True:
            choice = input(f"\n{Colors.BOLD}Escolha uma opção (1-7): {Colors.ENDC}")
            if choice in protocol_map:
                protocols, _ = protocol_map[choice]
                
                if 'ssl' in protocols:
                    domain = self._ask_ssl_domain()
                    if not domain:
                        print(f"\n{Colors.WARNING}[!] Domínio não informado. SSL não será ativado.{Colors.ENDC}")
                        protocols.remove('ssl')
                    else:
                        self.config["sni"] = domain
                
                return protocols
            else:
                print(f"\n{Colors.FAIL}[!] Opção inválida. Tente novamente.{Colors.ENDC}")
    
    def save_config(self) -> bool:
        """Salva as configurações com verificação de root."""
        if not self.check_root():
            return False
        return self.config_manager.save_config()
    
    # --- Métodos de Gerenciamento do Proxy ---
    
    @requires_systemctl
    @requires_root
    def start_proxy(self):
        """Inicia o processo do proxy."""
        if self.service_manager.is_running():
            print(f"\n{Colors.WARNING}[!] O proxy já está em execução.{Colors.ENDC}")
            return
        self.service_manager.start()
    
    @requires_systemctl
    @requires_root
    def stop_proxy(self):
        """Para o processo do proxy."""
        if not self.service_manager.is_running():
            print(f"\n{Colors.WARNING}[!] O proxy não está em execução.{Colors.ENDC}")
            return
        self.service_manager.stop()
    
    @requires_systemctl
    @requires_root
    def restart_proxy(self):
        """Reinicia o processo do proxy."""
        self.ui.print_header("REINICIAR PROXY")
        self.service_manager.restart()
    
    # --- Métodos de Configuração ---
    
    def add_port(self):
        """Adiciona uma nova porta à configuração."""
        self.ui.print_header("ADICIONAR PORTA")
        self.ui.print_divider()
        
        current_ports = self.config.get('port', [])
        print(f"{Colors.BOLD}Portas atuais:{Colors.ENDC} {Colors.BLUE}{', '.join(map(str, current_ports)) if current_ports else 'Nenhuma'}{Colors.ENDC}\n")
        
        port_input = input(f"{Colors.BOLD}Digite a nova porta para adicionar:{Colors.ENDC} ")
        port = self.ui.validate_port(port_input)
        
        if port:
            if port not in self.config["port"]:
                self.config["port"].append(port)
                self.save_config()
                print(f"\n{Colors.GREEN}[✓] Porta {port} adicionada com sucesso!{Colors.ENDC}")
            else:
                print(f"\n{Colors.WARNING}[!] Porta {port} já existe.{Colors.ENDC}")
    
    def remove_port(self):
        """Remove uma porta da configuração."""
        self.ui.print_header("REMOVER PORTA")
        self.ui.print_divider()
        
        current_ports = self.config.get('port', [])
        if not current_ports:
            print(f"{Colors.WARNING}[!] Não há portas para remover.{Colors.ENDC}")
            return
        
        print(f"{Colors.BOLD}Portas atuais:{Colors.ENDC} {Colors.BLUE}{', '.join(map(str, current_ports))}{Colors.ENDC}\n")
        port_input = input(f"{Colors.BOLD}Digite a porta para remover:{Colors.ENDC} ")
        port = self.ui.validate_port(port_input)
        
        if port and port in self.config["port"]:
            self.config["port"].remove(port)
            self.save_config()
            print(f"\n{Colors.GREEN}[✓] Porta {port} removida com sucesso!{Colors.ENDC}")
        elif port:
            print(f"\n{Colors.WARNING}[!] Porta {port} não encontrada.{Colors.ENDC}")
    
    def change_protocols(self):
        """Altera a combinação de protocolos em uso."""
        self.ui.print_header("ALTERAR PROTOCOLO")
        
        current_modes = self.config.get('mode', [])
        print(f"{Colors.BOLD}Protocolos atuais:{Colors.ENDC} {Colors.BLUE}{', '.join(current_modes) if current_modes else 'Nenhum'}{Colors.ENDC}")
        
        new_protocols = self._ask_for_protocols()
        self.config['mode'] = new_protocols
        self.save_config()
        print(f"\n{Colors.GREEN}[✓] Protocolos alterados com sucesso!{Colors.ENDC}")
    
    def configure_host(self):
        """Configura o host de destino do tráfego."""
        self.ui.print_header("ALTERAR DESTINO DO TRÁFEGO DO PROXY")
        self.ui.print_divider()
        
        print(f"{Colors.BOLD}Host atual:{Colors.ENDC} {Colors.BLUE}{self.config['host']}{Colors.ENDC}\n")
        new_host = input(f"{Colors.BOLD}Digite o novo host (formato: IP:PORTA):{Colors.ENDC} ").strip()
        
        if new_host:
            self.config["host"] = new_host
            self.save_config()
            print(f"\n{Colors.GREEN}[✓] Host configurado para {new_host}!{Colors.ENDC}")
    
    def change_domain_and_reinstall_ssl(self):
        """Altera o domínio (SNI) e re-executa a instalação para gerar novo certificado."""
        self.ui.print_header("ALTERAR DOMÍNIO E GERAR CERTIFICADO")
        
        print(f"{Colors.BOLD}SNI (domínio) atual:{Colors.ENDC} {Colors.BLUE}{self.config['sni']}{Colors.ENDC}\n")
        print(f"{Colors.WARNING}Esta operação irá alterar o domínio do seu servidor e tentará")
        print(f"re-executar o script de instalação para gerar um novo certificado SSL.{Colors.ENDC}")
        
        confirm = input(f"{Colors.BOLD}Deseja continuar? (s/N):{Colors.ENDC} ").lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print(f"\n{Colors.WARNING}Operação cancelada.{Colors.ENDC}")
            return
        
        new_domain = self._ask_ssl_domain()
        if not new_domain:
            print(f"\n{Colors.WARNING}Nenhum domínio inserido. Operação cancelada.{Colors.ENDC}")
            return
        
        self.config["sni"] = new_domain
        self.save_config()
        print(f"\n{Colors.GREEN}[✓] Domínio (SNI) alterado para {new_domain}.{Colors.ENDC}")
        print(f"{Colors.WARNING}Iniciando a reinstalação para gerar o novo certificado...{Colors.ENDC}")
        
        self._run_install_script_internal()
    
    def configure_workers(self):
        """Configura o número de workers."""
        self.ui.print_header("CONFIGURAR WORKERS")
        self.ui.print_divider()
        
        print(f"{Colors.BOLD}Workers atuais:{Colors.ENDC} {Colors.BLUE}{self.config['workers']}{Colors.ENDC}\n")
        workers_input = input(f"{Colors.BOLD}Digite o número de workers:{Colors.ENDC} ")
        
        try:
            new_workers = int(workers_input)
            if new_workers > 0:
                self.config["workers"] = new_workers
                self.save_config()
                print(f"\n{Colors.GREEN}[✓] Workers configurados para {new_workers}!{Colors.ENDC}")
            else:
                print(f"\n{Colors.FAIL}[!] Número de workers deve ser maior que 0.{Colors.ENDC}")
        except ValueError:
            print(f"\n{Colors.FAIL}[!] Entrada inválida. Digite um número.{Colors.ENDC}")
    
    def configure_buffer_size(self):
        """Configura o tamanho do buffer."""
        self.ui.print_header("CONFIGURAR BUFFER SIZE")
        self.ui.print_divider()
        
        print(f"{Colors.BOLD}Buffer size atual:{Colors.ENDC} {Colors.BLUE}{self.config['buffer_size']}{Colors.ENDC}\n")
        buffer_input = input(f"{Colors.BOLD}Digite o tamanho do buffer:{Colors.ENDC} ")
        
        try:
            new_buffer = int(buffer_input)
            if new_buffer > 0:
                self.config["buffer_size"] = new_buffer
                self.save_config()
                print(f"\n{Colors.GREEN}[✓] Buffer size configurado para {new_buffer}!{Colors.ENDC}")
            else:
                print(f"\n{Colors.FAIL}[!] Buffer size deve ser maior que 0.{Colors.ENDC}")
        except ValueError:
            print(f"\n{Colors.FAIL}[!] Entrada inválida. Digite um número.{Colors.ENDC}")
    
    def configure_log_level(self):
        """Configura o nível de log."""
        self.ui.print_header("CONFIGURAR LOG LEVEL")
        self.ui.print_divider()
        
        print(f"{Colors.BOLD}Log level atual:{Colors.ENDC} {Colors.BLUE}{self.config['log_level']}{Colors.ENDC}\n")
        print(f"{Colors.BOLD}Níveis disponíveis:{Colors.ENDC} 0 (Silencioso), 1 (Normal), 2 (Verboso)\n")
        
        log_input = input(f"{Colors.BOLD}Digite o nível de log (0-2):{Colors.ENDC} ")
        
        try:
            new_log_level = int(log_input)
            if MIN_LOG_LEVEL <= new_log_level <= MAX_LOG_LEVEL:
                self.config["log_level"] = new_log_level
                self.save_config()
                print(f"\n{Colors.GREEN}[✓] Log level configurado para {new_log_level}!{Colors.ENDC}")
            else:
                print(f"\n{Colors.FAIL}[!] Log level deve estar entre {MIN_LOG_LEVEL} e {MAX_LOG_LEVEL}.{Colors.ENDC}")
        except ValueError:
            print(f"\n{Colors.FAIL}[!] Entrada inválida. Digite um número.{Colors.ENDC}")
    
    # --- Métodos de Instalação/Desinstalação ---
    
    def _run_install_script_internal(self) -> bool:
        """Executa o script de instalação (método interno)."""
        install_script_path = self.find_install_script()
        
        if not install_script_path:
            print(f"{Colors.FAIL}[!] Erro: Script 'install.sh' não encontrado.{Colors.ENDC}")
            return False
        
        try:
            subprocess.run(["chmod", "+x", install_script_path], check=True)
            subprocess.run(["/bin/bash", install_script_path], check=True)
            print(f"\n{Colors.GREEN}[✓] Script de instalação executado com sucesso!{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n{Colors.FAIL}[!] Erro ao executar o script de instalação: {e}{Colors.ENDC}")
            return False
        except Exception as e:
            print(f"\n{Colors.FAIL}[!] Um erro inesperado ocorreu: {e}{Colors.ENDC}")
            return False
    
    def run_install_script(self):
        """Encontra e executa o script de instalação com configuração inicial."""
        self.ui.print_header("INSTALAR/REINSTALAR MULTIFLOW PROXY")
        
        install_script_path = self.find_install_script()
        
        if not install_script_path:
            print(f"{Colors.FAIL}[!] Erro: Script 'install.sh' não encontrado.{Colors.ENDC}")
            print(f"{Colors.WARNING}Certifique-se de que o repositório foi clonado corretamente.{Colors.ENDC}")
            return
        
        install_port = self._ask_for_install_port()
        install_protocols = self._ask_for_protocols()
        
        print(f"\n{Colors.WARNING}Esta opção executará a instalação na porta {install_port} com os protocolos selecionados.")
        print(f"Isso pode sobrescrever configurações existentes.{Colors.ENDC}\n")
        
        confirm = input(f"{Colors.BOLD}Deseja continuar? (s/N):{Colors.ENDC} ").lower()
        if confirm in ['s', 'sim', 'y', 'yes']:
            if not self.check_root():
                return
            
            self.config['port'] = [install_port]
            self.config['mode'] = install_protocols
            self.save_config()
            
            self._run_install_script_internal()
        else:
            print(f"\n{Colors.WARNING}Instalação cancelada.{Colors.ENDC}")
    
    @requires_systemctl
    @requires_root
    def uninstall(self):
        """Desinstala completamente o MultiFlowPX."""
        try:
            print("Parando e desabilitando o serviço systemd...")
            subprocess.run([self.systemctl_path, "stop", "multiflowpx.service"], check=False, capture_output=True)
            subprocess.run([self.systemctl_path, "disable", "multiflowpx.service"], check=False, capture_output=True)
            
            files_to_remove = [
                "/etc/systemd/system/multiflowpx.service",
                "/usr/local/bin/multiflowpx_proxy",
                "/usr/local/bin/multiflowpx_menu",
                CONFIG_FILE
            ]
            
            print("Removendo arquivos...")
            for file_path in files_to_remove:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"  {Colors.GREEN}Removido:{Colors.ENDC} {file_path}")
                    except OSError as e:
                        print(f"  {Colors.FAIL}Erro ao remover {file_path}: {e}{Colors.ENDC}")
            
            config_dir = os.path.dirname(CONFIG_FILE)
            if os.path.exists(config_dir) and not os.listdir(config_dir):
                try:
                    os.rmdir(config_dir)
                    print(f"  {Colors.GREEN}Removido diretório vazio:{Colors.ENDC} {config_dir}")
                except OSError as e:
                    print(f"  {Colors.FAIL}Erro ao remover diretório {config_dir}: {e}{Colors.ENDC}")
            
            print("Recarregando o daemon do systemd...")
            subprocess.run([self.systemctl_path, "daemon-reload"], check=True)
            
            print(f"\n{Colors.GREEN}[✓] MultiFlowPX desinstalado com sucesso!{Colors.ENDC}")
            
        except Exception as e:
            print(f"\n{Colors.FAIL}[!] Erro durante a desinstalação: {e}{Colors.ENDC}")
    
    # --- Menus ---
    
    def main_menu(self):
        """Exibe o menu principal."""
        while True:
            # Preparar informações de status
            if self.service_manager.is_available():
                status_text = f"{Colors.GREEN}● ATIVO{Colors.ENDC}" if self.service_manager.is_running() else f"{Colors.FAIL}○ INATIVO{Colors.ENDC}"
            else:
                status_text = f"{Colors.WARNING}N/A (systemd não encontrado){Colors.ENDC}"
            
            current_port = self.config.get("port", [])
            port_display = ", ".join(map(str, current_port)) if current_port else "Nenhuma"
            current_mode = self.config.get("mode", [])
            protocol_display = ", ".join([m.upper() for m in current_mode]) if current_mode else "Nenhum"
            
            # Usar o método pad_ansi_text para alinhamento correto
            status_padded = self.ui.pad_ansi_text(status_text, 40)
            
            self.ui.clear_screen()
            print(f"{Colors.CYAN}╔══════════════════════════════════════════════════════════════╗{Colors.ENDC}")
            print(f"{Colors.CYAN}║{Colors.BOLD}           MULTIFLOWPX PROXY SERVER MANAGER                  {Colors.CYAN}║{Colors.ENDC}")
            print(f"{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.ENDC}")
            print(f"{Colors.CYAN}║                                                              ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  {Colors.BOLD}Status do Serviço:{Colors.ENDC}  {status_padded}{Colors.CYAN}║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  {Colors.BOLD}Porta(s) Ativa(s):{Colors.ENDC}  {Colors.BLUE}{port_display:<39}{Colors.CYAN}║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  {Colors.BOLD}Protocolo(s):{Colors.ENDC}       {Colors.BLUE}{protocol_display:<39}{Colors.CYAN}║{Colors.ENDC}")
            print(f"{Colors.CYAN}║                                                              ║{Colors.ENDC}")
            print(f"{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.ENDC}")
            print(f"{Colors.CYAN}║                      MENU PRINCIPAL                         ║{Colors.ENDC}")
            print(f"{Colors.CYAN}╠══════════════════════════════════════════════════════════════╣{Colors.ENDC}")
            print(f"{Colors.CYAN}║                                                              ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  [{Colors.BOLD}1{Colors.ENDC}{Colors.CYAN}] Instalar/Reinstalar MultiFlow Proxy                   ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  [{Colors.BOLD}2{Colors.ENDC}{Colors.CYAN}] Configurar Proxy                                       ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  [{Colors.BOLD}3{Colors.ENDC}{Colors.CYAN}] Reiniciar Proxy                                        ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  [{Colors.BOLD}4{Colors.ENDC}{Colors.CYAN}] Desinstalar Completamente                             ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║                                                              ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║  [{Colors.BOLD}0{Colors.ENDC}{Colors.CYAN}] Sair                                                   ║{Colors.ENDC}")
            print(f"{Colors.CYAN}║                                                              ║{Colors.ENDC}")
            print(f"{Colors.CYAN}╚══════════════════════════════════════════════════════════════╝{Colors.ENDC}")
            
            choice = input(f"\n  {Colors.BOLD}Escolha uma opção:{Colors.ENDC} ")
            
            if choice == '1':
                self.run_install_script()
            elif choice == '2':
                self.submenu_configure_proxy()
            elif choice == '3':
                self.restart_proxy()
            elif choice == '4':
                self.menu_uninstall()
            elif choice == '0':
                print(f"\n{Colors.GREEN}  Encerrando o sistema...{Colors.ENDC}\n")
                sys.exit(0)
            else:
                print(f"\n{Colors.FAIL}  [!] Opção inválida. Tente novamente.{Colors.ENDC}")
            
            if choice in ["1", "2", "3", "4"]:
                input(f"\n  {Colors.BOLD}Pressione Enter para voltar ao menu...{Colors.ENDC}")
    
    def submenu_configure_proxy(self):
        """Submenu para configurar o proxy."""
        while True:
            self.ui.print_header("CONFIGURAR PROXY")
            
            print(f"{Colors.CYAN}┌──────────────────────────────────────────────────────────────┐{Colors.ENDC}")
            print(f"{Colors.CYAN}│                    OPÇÕES DE CONFIGURAÇÃO                   │{Colors.ENDC}")
            print(f"{Colors.CYAN}├──────────────────────────────────────────────────────────────┤{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}1{Colors.ENDC}{Colors.CYAN}] Adicionar porta                                        │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}2{Colors.ENDC}{Colors.CYAN}] Alterar protocolo                                      │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}3{Colors.ENDC}{Colors.CYAN}] Remover porta                                          │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}4{Colors.ENDC}{Colors.CYAN}] Configuração avançada                                  │{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}0{Colors.ENDC}{Colors.CYAN}] Voltar ao menu principal                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}└──────────────────────────────────────────────────────────────┘{Colors.ENDC}")
            
            choice = input(f"\n  {Colors.BOLD}Escolha uma opção:{Colors.ENDC} ")
            
            if choice == '1':
                self.add_port()
            elif choice == '2':
                self.change_protocols()
            elif choice == '3':
                self.remove_port()
            elif choice == '4':
                self.submenu_advanced_config()
            elif choice == '0':
                break
            else:
                print(f"\n{Colors.FAIL}  [!] Opção inválida. Tente novamente.{Colors.ENDC}")
            
            input(f"\n  {Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")
    
    def submenu_advanced_config(self):
        """Submenu para configurações avançadas."""
        while True:
            self.ui.print_header("CONFIGURAÇÃO AVANÇADA")
            
            print(f"{Colors.CYAN}┌──────────────────────────────────────────────────────────────┐{Colors.ENDC}")
            print(f"{Colors.CYAN}│                   PARÂMETROS AVANÇADOS                      │{Colors.ENDC}")
            print(f"{Colors.CYAN}├──────────────────────────────────────────────────────────────┤{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}1{Colors.ENDC}{Colors.CYAN}] Alterar destino do tráfego do proxy                   │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}2{Colors.ENDC}{Colors.CYAN}] Alterar domínio do servidor e gerar novo certificado  │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}3{Colors.ENDC}{Colors.CYAN}] Configurar número de workers                           │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}4{Colors.ENDC}{Colors.CYAN}] Configurar tamanho do buffer                           │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}5{Colors.ENDC}{Colors.CYAN}] Configurar nível de log                                │{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}│  [{Colors.BOLD}0{Colors.ENDC}{Colors.CYAN}] Voltar ao menu anterior                                │{Colors.ENDC}")
            print(f"{Colors.CYAN}│                                                              │{Colors.ENDC}")
            print(f"{Colors.CYAN}└──────────────────────────────────────────────────────────────┘{Colors.ENDC}")
            
            choice = input(f"\n  {Colors.BOLD}Escolha uma opção:{Colors.ENDC} ")
            
            if choice == '1':
                self.configure_host()
            elif choice == '2':
                self.change_domain_and_reinstall_ssl()
            elif choice == '3':
                self.configure_workers()
            elif choice == '4':
                self.configure_buffer_size()
            elif choice == '5':
                self.configure_log_level()
            elif choice == '0':
                break
            else:
                print(f"\n{Colors.FAIL}  [!] Opção inválida. Tente novamente.{Colors.ENDC}")
            
            input(f"\n  {Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")
    
    def menu_uninstall(self):
        """Menu para desinstalar o MultiFlowPX."""
        self.ui.print_header("DESINSTALAR MULTIFLOWPX")
        
        print(f"{Colors.FAIL}ATENÇÃO: Esta operação removerá completamente o MultiFlowPX!{Colors.ENDC}")
        print(f"{Colors.WARNING}Isso incluirá:{Colors.ENDC}")
        print(f"  • Parar o serviço")
        print(f"  • Remover arquivos de configuração")
        print(f"  • Remover executáveis")
        print(f"  • Remover serviço systemd\n")
        
        confirm = input(f"{Colors.BOLD}Tem certeza que deseja desinstalar? (s/N):{Colors.ENDC} ").lower()
        if confirm in ['s', 'sim', 'y', 'yes']:
            self.uninstall()
        else:
            print(f"\n{Colors.WARNING}Desinstalação cancelada.{Colors.ENDC}")


def main():
    """Função principal para iniciar o menu."""
    try:
        menu = ProxyMenu()
        menu.main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Programa interrompido pelo usuário.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.FAIL}Erro crítico: {e}{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
