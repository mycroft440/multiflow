#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import signal
import time

# --- Configurações ---
REPO_URL = "https://github.com/mycroft440/multiflow.git"
INSTALL_DIR = "/opt/multiflow"
TMP_DIR = f"/tmp/multiflow-update-{int(time.time())}"
PROXY_STATE_FILE = "/tmp/proxy.state"
SERVER_STATE_FILE = "/tmp/download_server.state"

# --- Funções de Log com Cores ---
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'

def log_info(message):
    """Exibe uma mensagem de informação."""
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {message}")

def log_warn(message):
    """Exibe uma mensagem de aviso."""
    print(f"{Colors.YELLOW}[AVISO]{Colors.NC} {message}")

def log_error(message):
    """Exibe uma mensagem de erro."""
    print(f"{Colors.RED}[ERRO]{Colors.NC} {message}", file=sys.stderr)

def check_root():
    """Verifica se o script está sendo executado como root."""
    return os.geteuid() == 0

def run_command(command, check=True):
    """Executa um comando no shell e trata exceções."""
    try:
        subprocess.run(command, check=check, capture_output=True, text=True)
    except FileNotFoundError:
        log_error(f"Comando '{command[0]}' não encontrado. Verifique se o programa está instalado.")
        raise
    except subprocess.CalledProcessError as e:
        # Não levanta exceção se o comando falhar, apenas loga o erro,
        # útil para comandos de parada/desinstalação que podem falhar se o serviço não existir.
        if not check:
            log_warn(f"Comando '{' '.join(command)}' falhou (pode ser normal se o serviço não existir): {e.stderr.strip()}")
        else:
            log_error(f"Erro ao executar '{' '.join(command)}': {e.stderr}")
            raise

def uninstall_services():
    """Para e desinstala serviços ativos para uma atualização limpa."""
    log_info("Desinstalando serviços antigos para uma atualização limpa...")

    # --- Desinstalação do OpenVPN ---
    if os.path.isdir("/etc/openvpn"):
        log_info("Desinstalando OpenVPN...")
        run_command(['systemctl', 'stop', 'openvpn@server'], check=False)
        run_command(['systemctl', 'disable', 'openvpn@server'], check=False)
        if os.path.exists('/etc/debian_version'):
            run_command(['apt-get', 'remove', '--purge', '-y', 'openvpn', 'easy-rsa'], check=False)
            run_command(['apt-get', 'autoremove', '-y'], check=False)
        elif os.path.exists('/etc/redhat-release'):
             run_command(['yum', 'remove', '-y', 'openvpn', 'easy-rsa'], check=False)
        
        shutil.rmtree("/etc/openvpn", ignore_errors=True)
        user_home = os.path.expanduser("~")
        ovpn_clients_dir = os.path.join(user_home, "ovpn-clients")
        shutil.rmtree(ovpn_clients_dir, ignore_errors=True)
        log_info("OpenVPN desinstalado.")

    # --- Desinstalação do BadVPN ---
    badvpn_service_path = "/etc/systemd/system/badvpn-udpgw.service"
    badvpn_binary_path = "/usr/local/bin/badvpn-udpgw"
    if os.path.exists(badvpn_service_path):
        log_info("Desinstalando BadVPN...")
        run_command(['systemctl', 'stop', 'badvpn-udpgw.service'], check=False)
        run_command(['systemctl', 'disable', 'badvpn-udpgw.service'], check=False)
        try:
            os.remove(badvpn_service_path)
            if os.path.exists(badvpn_binary_path):
                os.remove(badvpn_binary_path)
            run_command(['systemctl', 'daemon-reload'], check=False)
            log_info("BadVPN desinstalado.")
        except OSError as e:
            log_warn(f"Erro ao remover arquivos do BadVPN: {e}")

    # --- Parada de serviços baseados em Python ---
    for state_file, service_name in [(PROXY_STATE_FILE, "ProxySocks"), (SERVER_STATE_FILE, "Servidor de Download")]:
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    pid_str = f.read().strip().split(':')[0]
                    pid = int(pid_str)
                log_info(f"Parando {service_name} (PID: {pid})...")
                os.kill(pid, signal.SIGTERM)
            except (IOError, ValueError, ProcessLookupError) as e:
                log_warn(f"Não foi possível parar o processo de {service_name}: {e}")
            finally:
                os.remove(state_file)

def download_latest_version():
    """Baixa a versão mais recente do repositório Git."""
    log_info(f"Baixando a versão mais recente de {REPO_URL}...")
    if not shutil.which('git'):
        log_error("O comando 'git' não foi encontrado. Por favor, instale o git para continuar.")
        sys.exit(1)
    run_command(['git', 'clone', '--depth', '1', REPO_URL, TMP_DIR])

def replace_installation():
    """Remove a instalação antiga e a substitui pela nova."""
    log_info("Removendo a instalação antiga...")
    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR)
    os.makedirs(INSTALL_DIR, exist_ok=True)

    log_info("Instalando a nova versão...")
    # Copia o conteúdo do diretório temporário para o diretório de instalação
    for item in os.listdir(TMP_DIR):
        source = os.path.join(TMP_DIR, item)
        destination = os.path.join(INSTALL_DIR, item)
        if os.path.isdir(source):
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination)

def apply_permissions():
    """Aplica permissões de execução para scripts .py e .sh."""
    log_info("Aplicando permissões de execução...")
    for root, _, files in os.walk(INSTALL_DIR):
        for name in files:
            if name.endswith((".py", ".sh")):
                filepath = os.path.join(root, name)
                try:
                    # Adiciona permissão de execução para o dono, grupo e outros
                    os.chmod(filepath, os.stat(filepath).st_mode | 0o111)
                except OSError as e:
                    log_warn(f"Não foi possível definir permissão para {filepath}: {e}")

def cleanup():
    """Remove o diretório temporário de atualização."""
    log_info("Limpando arquivos temporários...")
    if os.path.isdir(TMP_DIR):
        shutil.rmtree(TMP_DIR)

def main():
    """Função principal que orquestra a atualização."""
    if not check_root():
        log_error("Este script de atualização deve ser executado como root.")
        sys.exit(1)

    try:
        uninstall_services()
        download_latest_version()
        replace_installation()
        apply_permissions()
        print("\n" + "="*60)
        log_info("Atualização do Multiflow concluída com sucesso!")
        log_warn("Os serviços foram parados/desinstalados durante a atualização.")
        log_warn("É necessário reiniciar a aplicação para que as alterações tenham efeito.")
        print("="*60 + "\n")
    except Exception as e:
        log_error(f"Ocorreu um erro inesperado durante a atualização: {e}")
        sys.exit(1)
    finally:
        cleanup()

if __name__ == "__main__":
    main()
