#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
import requests
import re

# --- Configurações ---
# URL do script de instalação no repositório
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
    print(f"{Colors.YELLOW}⚠ {message}{Colors.NC}")

def print_error(message):
    """Imprime uma mensagem de erro e sai."""
    print(f"{Colors.RED}✗ {message}{Colors.NC}")
    sys.exit(1)

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado como root. Por favor, use 'sudo'.")

def run_command(command, check=True):
    """Executa um comando no shell."""
    try:
        subprocess.run(command, shell=True, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        if check:
            print_warning(f"Comando falhou (pode ser normal se o recurso não existir): {e.cmd}")

# --- Funções de Limpeza Aprimoradas ---

def stop_and_disable_services():
    """Para e desabilita todos os serviços relacionados ao Multiflow."""
    print_step("Parando e desabilitando serviços")
    services = [
        "multiflow.service",
        "badvpn.service",
        "openvpn-server@server.service"
    ]
    for service in services:
        print(f"  - Parando {service}...")
        run_command(f"systemctl stop {service}", check=False)
        print(f"  - Desabilitando {service}...")
        run_command(f"systemctl disable {service}", check=False)
    print_success("Serviços parados e desabilitados.")

def remove_project_files():
    """Remove o diretório do projeto e todos os binários/scripts relacionados."""
    print_step("Removendo arquivos do projeto e binários")
    paths_to_remove = [
        INSTALL_DIR,
        "/usr/local/bin/multiflow",
        "/usr/local/bin/badvpn-udpgw",
        TMP_INSTALL_SCRIPT
    ]
    for path in paths_to_remove:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f"  - Diretório removido: {path}")
            elif os.path.isfile(path):
                os.remove(path)
                print(f"  - Arquivo removido: {path}")
        except FileNotFoundError:
            print_warning(f"Caminho não encontrado (já removido?): {path}")
        except Exception as e:
            print_warning(f"Não foi possível remover {path}: {e}")
    print_success("Arquivos do projeto removidos.")

def remove_service_files():
    """Remove os arquivos de serviço do systemd."""
    print_step("Removendo arquivos de serviço do Systemd")
    service_files = [
        "/etc/systemd/system/multiflow.service",
        "/etc/systemd/system/badvpn.service",
        "/etc/systemd/system/openvpn-server@server.service"
    ]
    for service_file in service_files:
        try:
            if os.path.isfile(service_file):
                os.remove(service_file)
                print(f"  - Arquivo de serviço removido: {service_file}")
        except FileNotFoundError:
            pass
    print("  - Recarregando o daemon do systemd...")
    run_command("systemctl daemon-reload")
    print_success("Arquivos de serviço removidos.")

def remove_configs_and_logs():
    """Remove arquivos de configuração, logs e reverte alterações no sistema."""
    print_step("Removendo configurações, logs e revertendo alterações")

    # Remove diretório de configuração do OpenVPN
    openvpn_dir = "/etc/openvpn"
    if os.path.isdir(openvpn_dir):
        try:
            shutil.rmtree(openvpn_dir)
            print(f"  - Diretório de configuração do OpenVPN removido: {openvpn_dir}")
        except Exception as e:
            print_warning(f"Não foi possível remover {openvpn_dir}: {e}")

    # Remove logs do OpenVPN
    openvpn_logs = ["/var/log/openvpn.log", "/var/log/openvpn-status.log"]
    for log in openvpn_logs:
        if os.path.isfile(log):
            try:
                os.remove(log)
                print(f"  - Log do OpenVPN removido: {log}")
            except Exception as e:
                print_warning(f"Não foi possível remover o log {log}: {e}")

    # Limpa o arquivo /etc/hosts de entradas do bloqueador
    hosts_file = "/etc/hosts"
    try:
        with open(hosts_file, 'r') as f:
            lines = f.readlines()
        
        # Usa regex para encontrar o bloco a ser removido
        pattern = re.compile(r"# MULTIFLOW BLOCK START.*# MULTIFLOW BLOCK END", re.DOTALL)
        content = "".join(lines)
        new_content = re.sub(pattern, "", content)

        if new_content != content:
            with open(hosts_file, 'w') as f:
                f.write(new_content.strip() + "\n")
            print("  - Entradas do bloqueador de sites removidas do /etc/hosts")
    except Exception as e:
        print_warning(f"Não foi possível limpar o arquivo /etc/hosts: {e}")

    # Restaura backup do sysctl.conf se existir
    sysctl_conf = "/etc/sysctl.conf"
    sysctl_backup = f"{sysctl_conf}.multiflow_backup"
    if os.path.isfile(sysctl_backup):
        try:
            shutil.move(sysctl_backup, sysctl_conf)
            print(f"  - Backup do sysctl.conf restaurado de {sysctl_backup}")
        except Exception as e:
            print_warning(f"Falha ao restaurar backup do sysctl.conf: {e}")

    print_success("Limpeza de configurações finalizada.")

def full_cleanup():
    """Executa todas as rotinas de limpeza."""
    print_step("Iniciando Limpeza Completa")
    stop_and_disable_services()
    remove_project_files()
    remove_service_files()
    remove_configs_and_logs()
    print_success("Sistema limpo e pronto para reinstalação.")

def reinstall():
    """Baixa e executa o script de instalação mais recente."""
    print_step("Baixando e Reinstalando o Multiflow")
    try:
        print(f"  - Baixando script de instalação de {INSTALL_SCRIPT_URL}...")
        response = requests.get(INSTALL_SCRIPT_URL, timeout=10)
        response.raise_for_status()
        
        with open(TMP_INSTALL_SCRIPT, 'w') as f:
            f.write(response.text)
        
        # Dá permissão de execução ao script
        os.chmod(TMP_INSTALL_SCRIPT, 0o755)
        print_success("Download do script de instalação concluído.")

        print("\n  - Executando o instalador...")
        # Executa o script de instalação
        subprocess.run(TMP_INSTALL_SCRIPT, shell=True, check=True)

    except requests.exceptions.RequestException as e:
        print_error(f"Erro ao baixar o script de instalação: {e}")
    except subprocess.CalledProcessError as e:
        print_error(f"O script de instalação falhou com o código de erro {e.returncode}.")
    except Exception as e:
        print_error(f"Ocorreu um erro inesperado durante a reinstalação: {e}")
    finally:
        # Limpa o script de instalação temporário
        if os.path.exists(TMP_INSTALL_SCRIPT):
            os.remove(TMP_INSTALL_SCRIPT)

def main():
    """Função principal do script."""
    check_root()
    os.system('clear')
    
    # Exibe o aviso detalhado
    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"{Colors.YELLOW}      ATUALIZADOR E REINSTALADOR - MULTIFLOW         {Colors.NC}")
    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"\n{Colors.RED}{Colors.YELLOW}AVISO IMPORTANTE:{Colors.NC}")
    print(f"Este script irá {Colors.RED}REMOVER COMPLETAMENTE{Colors.NC} a instalação atual do Multiflow e todas as suas configurações, incluindo:")
    print(f"  - O diretório principal {Colors.CYAN}{INSTALL_DIR}{Colors.NC}")
    print(f"  - Serviços do systemd ({Colors.CYAN}multiflow, badvpn, openvpn{Colors.NC})")
    print(f"  - Binários e scripts ({Colors.CYAN}/usr/local/bin/multiflow, /usr/local/bin/badvpn-udpgw{Colors.NC})")
    print(f"  - Configurações do OpenVPN ({Colors.CYAN}/etc/openvpn{Colors.NC})")
    print(f"  - Regras de bloqueio no arquivo {Colors.CYAN}/etc/hosts{Colors.NC}")
    print("\nEm seguida, ele baixará e reinstalará a versão mais recente do GitHub.")
    print(f"As configurações de {Colors.GREEN}ZRAM e SWAP{Colors.NC}, se existirem, {Colors.GREEN}NÃO{Colors.NC} serão removidas.")
    print(f"Contas de {Colors.GREEN}usuários do sistema{Colors.NC} criadas pelo script {Colors.GREEN}NÃO{Colors.NC} serão removidas.")

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
        print(f"Para iniciar, use o comando: {Colors.YELLOW}multiflow{Colors.NC}")
    else:
        print("Operação abortada.")

if __name__ == "__main__":
    main()
