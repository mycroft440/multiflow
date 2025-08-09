#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
import signal
import requests

# --- Configurações ---
# Repositório do projeto no GitHub
GITHUB_REPO_URL = "https://github.com/mycroft440/multiflow"
# Script de instalação no repositório
INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/mycroft440/multiflow/main/install.sh"
# Diretório de instalação padrão do projeto
INSTALL_DIR = "/opt/multiflow"
# Arquivo temporário para o script de instalação
TMP_INSTALL_SCRIPT = "/tmp/multiflow_install.sh"

# --- Cores para o Terminal ---
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    CYAN = '\033[0;36m'
    NC = '\033[0m' # No Color

# --- Funções Auxiliares ---

def print_step(message):
    """Imprime uma etapa do processo com formatação."""
    print(f"\n{Colors.CYAN}◆ {message}{Colors.NC}")
    print(f"{Colors.CYAN}{'-' * (len(message) + 2)}{Colors.NC}")

def print_success(message):
    """Imprime uma mensagem de sucesso."""
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_warning(message):
    """Imprime uma mensagem de aviso."""
    print(f"{Colors.YELLOW}⚠️ {message}{Colors.NC}")

def print_error(message):
    """Imprime uma mensagem de erro."""
    print(f"{Colors.RED}✗ {message}{Colors.NC}", file=sys.stderr)

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado com privilégios de superusuário (root).")
        sys.exit(1)

def run_command(command, description):
    """Executa um comando no shell, tratando erros de forma segura."""
    print(f"  - {description}...")
    try:
        # Usamos DEVNULL para silenciar a saída, pois o objetivo é limpar
        subprocess.run(
            command,
            shell=True,
            check=False, # Não para o script se o comando falhar (ex: serviço já parado)
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_success(f"  {description}: Concluído.")
    except Exception as e:
        print_warning(f"  Ocorreu um erro não crítico ao executar '{description}': {e}")

# --- Lógica Principal ---

def full_cleanup():
    """
    Executa uma limpeza completa de todos os componentes e arquivos do Multiflow.
    """
    print_step("Iniciando Limpeza Completa do Multiflow")

    # 1. Parar e desabilitar serviços
    print("\n--- Desativando Serviços ---")
    services_to_manage = [
        "badvpn-udpgw.service",
        "openvpn@server.service",
        "zram.service" # Embora não seja removido, o serviço systemd é
    ]
    for service in services_to_manage:
        run_command(f"systemctl stop {service}", f"Parando {service}")
        run_command(f"systemctl disable {service}", f"Desabilitando {service}")

    # Parar servidores Python (ProxySocks, Servidor de Download)
    pid_files = ["/tmp/proxy.state", "/tmp/download_server.state"]
    for pid_file in pid_files:
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip().split(':')[0])
                os.kill(pid, signal.SIGTERM)
                print_success(f"  Processo do arquivo {pid_file} (PID: {pid}) finalizado.")
            except (ValueError, OSError, IOError):
                pass # Ignora se o arquivo estiver mal formatado ou o processo não existir
            os.remove(pid_file)


    # 2. Remover arquivos de configuração e do sistema
    print("\n--- Removendo Arquivos de Configuração ---")
    files_to_remove = [
        "/etc/systemd/system/badvpn-udpgw.service",
        "/etc/systemd/system/zram.service",
        "/etc/cron.d/vps_optimizer_tasks"
    ]
    dirs_to_remove = [
        "/etc/openvpn",
        "~/ovpn-clients" # Diretório do usuário root
    ]

    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print_success(f"  Arquivo removido: {f}")

    for d in dirs_to_remove:
        expanded_d = os.path.expanduser(d)
        if os.path.isdir(expanded_d):
            shutil.rmtree(expanded_d, ignore_errors=True)
            print_success(f"  Diretório removido: {expanded_d}")

    # Recarregar systemd após remover arquivos de serviço
    run_command("systemctl daemon-reload", "Recarregando daemons do systemd")

    # 3. Remover links simbólicos
    print("\n--- Removendo Links Simbólicos ---")
    symlinks = ["/usr/local/bin/multiflow", "/usr/local/bin/h", "/usr/local/bin/menu"]
    for link in symlinks:
        if os.path.islink(link):
            os.remove(link)
            print_success(f"  Link simbólico removido: {link}")

    # 4. Limpar arquivos residuais e o diretório de instalação
    print("\n--- Removendo Arquivos Residuais e Projeto ---")
    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        print_success(f"  Diretório principal do projeto removido: {INSTALL_DIR}")

    # Limpar banco de dados de usuários SSH, se existir
    ssh_db = "/root/ssh_users.db"
    if os.path.exists(ssh_db):
        os.remove(ssh_db)
        print_success(f"  Banco de dados de usuários SSH removido: {ssh_db}")

    print_success("Fase de limpeza concluída!")


def reinstall():
    """
    Baixa e executa o script de instalação mais recente.
    """
    print_step("Reinstalando o Multiflow a partir do GitHub")

    # 1. Baixar o script de instalação
    print(f"  - Baixando install.sh de {GITHUB_REPO_URL}...")
    try:
        response = requests.get(INSTALL_SCRIPT_URL, timeout=30)
        response.raise_for_status()
        with open(TMP_INSTALL_SCRIPT, 'w') as f:
            f.write(response.text)
        os.chmod(TMP_INSTALL_SCRIPT, 0o755) # Tornar o script executável
        print_success("  Download do instalador concluído.")
    except requests.exceptions.RequestException as e:
        print_error(f"Falha ao baixar o script de instalação: {e}")
        sys.exit(1)

    # 2. Executar o script de instalação
    print("  - Executando o instalador (isso pode levar alguns minutos)...")
    try:
        # Executa o script de forma interativa para que o usuário veja a saída
        subprocess.run(["bash", TMP_INSTALL_SCRIPT], check=True)
        print_success("Instalação concluída com sucesso!")
    except subprocess.CalledProcessError as e:
        print_error(f"O script de instalação falhou com o código de saída {e.returncode}.")
        print_error("Verifique a saída acima para mais detalhes.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Ocorreu um erro inesperado ao executar o instalador: {e}")
        sys.exit(1)
    finally:
        # Limpa o script de instalação temporário
        if os.path.exists(TMP_INSTALL_SCRIPT):
            os.remove(TMP_INSTALL_SCRIPT)


def main():
    """
    Ponto de entrada do script.
    """
    os.system('clear')
    check_root()

    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"{Colors.YELLOW}      ATUALIZADOR E REINSTALADOR - MULTIFLOW         {Colors.NC}")
    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"\n{Colors.RED}{Colors.YELLOW}AVISO IMPORTANTE:{Colors.NC}")
    print("Este script irá {Colors.RED}REMOVER COMPLETAMENTE{Colors.NC} a instalação atual do Multiflow e todas as suas configurações, incluindo:")
    print("  - Serviços (BadVPN, OpenVPN, etc.)")
    print("  - Arquivos de configuração e logs")
    print("  - O diretório do projeto em /opt/multiflow")
    print("\nEm seguida, ele baixará e reinstalará a versão mais recente do GitHub.")
    print("As configurações de {Colors.GREEN}ZRAM e SWAP{Colors.NC}, se existirem, {Colors.GREEN}NÃO{Colors.NC} serão removidas.")

    try:
        confirm = input(f"\n{Colors.CYAN}Você tem certeza que deseja continuar? [s/N]: {Colors.NC}").strip().lower()
    except KeyboardInterrupt:
        print("\nOperação cancelada pelo usuário.")
        sys.exit(0)

    if confirm == 's':
        full_cleanup()
        time.sleep(2) # Pausa para o usuário ler a saída da limpeza
        reinstall()

        print_step("Processo Finalizado")
        print(f"{Colors.GREEN}O Multiflow foi reinstalado com sucesso!{Colors.NC}")
        print(f"Para iniciar, execute o comando: {Colors.CYAN}multiflow{Colors.NC}")
    else:
        print("\nOperação cancelada. Nenhuma alteração foi feita.")

if __name__ == "__main__":
    main()
