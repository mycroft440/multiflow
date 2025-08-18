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
    """Executa um comando no shell, capturando a saída."""
    try:
        result = subprocess.run(
            command, shell=True, check=check, 
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if check:
            # Não imprime o aviso se o comando for de remoção e o recurso não existir
            if not ("No such file or directory" in e.stderr or "not found" in e.stderr):
                 print_warning(f"Comando falhou (pode ser normal se o recurso não existir): {e.cmd}\n  {e.stderr.strip()}")
        return None

# --- Funções de Limpeza Aprimoradas ---

def stop_and_disable_services():
    """Para e desabilita todos os serviços relacionados ao Multiflow."""
    print_step("Parando e desabilitando serviços")
    services = [
        "multiflow.service",
        "badvpn.service",
        "openvpn-server@server.service",
        "openvpn.service" # Adicionado para cobrir instalações genéricas
    ]
    for service in services:
        print(f"  - Parando e desabilitando {service}...")
        run_command(f"systemctl stop {service}", check=False)
        run_command(f"systemctl disable {service}", check=False)
    
    print("  - Limpando estados de falha de serviços...")
    run_command("systemctl reset-failed", check=False)
    print_success("Serviços parados e desabilitados.")

def remove_project_files():
    """Remove o diretório do projeto e todos os binários/scripts relacionados."""
    print_step("Removendo arquivos do projeto, binários e links")
    paths_to_remove = [
        INSTALL_DIR,
        "/usr/local/bin/multiflow",
        "/usr/local/bin/badvpn-udpgw",
        "/etc/easy-rsa", # Diretório de certificados do OpenVPN
        TMP_INSTALL_SCRIPT
    ]
    for path in paths_to_remove:
        try:
            if os.path.lexists(path): # Usa lexists para funcionar com links simbólicos
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                    print(f"  - Diretório removido: {path}")
                else:
                    os.remove(path)
                    print(f"  - Arquivo/Link removido: {path}")
        except Exception as e:
            print_warning(f"Não foi possível remover {path}: {e}")
    print_success("Arquivos do projeto removidos.")

def remove_service_files():
    """Remove os arquivos de serviço do systemd."""
    print_step("Removendo arquivos de serviço do Systemd")
    # Usa um glob para encontrar todos os serviços relacionados ao openvpn
    service_files = [
        "/etc/systemd/system/multiflow.service",
        "/etc/systemd/system/badvpn.service"
    ]
    openvpn_services = run_command("ls /etc/systemd/system/openvpn* 2>/dev/null", check=False)
    if openvpn_services:
        service_files.extend(openvpn_services.split('\n'))

    for service_file in service_files:
        if service_file and os.path.exists(service_file):
            try:
                os.remove(service_file)
                print(f"  - Arquivo de serviço removido: {service_file}")
            except Exception as e:
                print_warning(f"Não foi possível remover {service_file}: {e}")
    
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
            content = f.read()
        
        # Usa regex para encontrar e remover o bloco de forma segura
        pattern = re.compile(r"\n# MULTIFLOW BLOCK START.*# MULTIFLOW BLOCK END\n?", re.DOTALL)
        new_content, count = re.subn(pattern, "", content)

        if count > 0:
            with open(hosts_file, 'w') as f:
                f.write(new_content)
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
            
    # Remove cron jobs relacionados
    print("  - Verificando e removendo cron jobs...")
    try:
        current_crontab = run_command("crontab -l", check=False)
        if current_crontab and "multiflow" in current_crontab.lower():
            new_crontab = "\n".join([line for line in current_crontab.split('\n') if "multiflow" not in line.lower()])
            run_command(f'echo "{new_crontab}" | crontab -', check=True)
            print("  - Cron job do Multiflow removido.")
    except Exception as e:
        print_warning(f"Não foi possível verificar/remover cron jobs: {e}")

    print_success("Limpeza de configurações finalizada.")

def full_cleanup():
    """Executa todas as rotinas de limpeza na ordem correta."""
    print_step("Iniciando Limpeza Completa e Exaustiva")
    stop_and_disable_services()
    remove_project_files()
    remove_configs_and_logs()
    remove_service_files() # Por último, antes do reload final
    print_success("Sistema limpo e pronto para reinstalação.")

def reinstall():
    """Baixa e executa o script de instalação mais recente."""
    print_step("Baixando e Reinstalando o Multiflow")
    try:
        print(f"  - Baixando script de instalação de {INSTALL_SCRIPT_URL}...")
        response = requests.get(INSTALL_SCRIPT_URL, timeout=15)
        response.raise_for_status()
        
        with open(TMP_INSTALL_SCRIPT, 'w', newline='\n') as f:
            f.write(response.text)
        
        os.chmod(TMP_INSTALL_SCRIPT, 0o755)
        print_success("Download do script de instalação concluído.")

        print("\n  - Executando o instalador...")
        subprocess.run(f"bash {TMP_INSTALL_SCRIPT}", shell=True, check=True)

    except requests.exceptions.RequestException as e:
        print_error(f"Erro ao baixar o script de instalação: {e}")
    except subprocess.CalledProcessError as e:
        print_error(f"O script de instalação falhou com o código de erro {e.returncode}.")
    except Exception as e:
        print_error(f"Ocorreu um erro inesperado durante a reinstalação: {e}")
    finally:
        if os.path.exists(TMP_INSTALL_SCRIPT):
            os.remove(TMP_INSTALL_SCRIPT)

def main():
    """Função principal do script."""
    check_root()
    os.system('clear')
    
    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"{Colors.YELLOW}      ATUALIZADOR E REINSTALADOR - MULTIFLOW         {Colors.NC}")
    print(f"{Colors.YELLOW}====================================================={Colors.NC}")
    print(f"\n{Colors.RED}{Colors.YELLOW}AVISO IMPORTANTE:{Colors.NC}")
    print(f"Este script irá {Colors.RED}REMOVER COMPLETAMENTE{Colors.NC} a instalação atual do Multiflow e todas as suas configurações, incluindo:")
    print(f"  - Diretórios: {Colors.CYAN}{INSTALL_DIR}, /etc/openvpn, /etc/easy-rsa{Colors.NC}")
    print(f"  - Serviços: {Colors.CYAN}multiflow, badvpn, openvpn*, etc.{Colors.NC}")
    print(f"  - Binários e links: {Colors.CYAN}/usr/local/bin/multiflow, /usr/local/bin/badvpn-udpgw{Colors.NC}")
    print(f"  - Logs: {Colors.CYAN}/var/log/openvpn.log, /var/log/openvpn-status.log{Colors.NC}")
    print(f"  - Modificações: {Colors.CYAN}Regras no /etc/hosts, tarefas no crontab{Colors.NC}")
    print(f"  - Backups: {Colors.CYAN}Restaurará /etc/sysctl.conf se houver backup.{Colors.NC}")
    print("\nEm seguida, ele baixará e reinstalará a versão mais recente do GitHub.")
    print(f"\n{Colors.GREEN}O QUE NÃO SERÁ REMOVIDO:{Colors.NC}")
    print(f"  - Contas de {Colors.GREEN}usuários do sistema{Colors.NC} criadas pelo script.")
    print(f"  - Configurações de {Colors.GREEN}ZRAM e SWAP{Colors.NC}.")
    print(f"  - Pacotes instalados via APT ({Colors.GREEN}openvpn, python3, etc.{Colors.NC}) pois podem ser dependências de outros programas.")

    try:
        confirm = input(f"\n{Colors.CYAN}Você tem certeza que deseja continuar? [s/N]: {Colors.NC}").strip().lower()
    except KeyboardInterrupt:
        print("\n\nOperação cancelada pelo usuário.")
        sys.exit(0)

    if confirm == 's':
        full_cleanup()
        time.sleep(2)
        reinstall()

        print_step("Processo Finalizado")
        print(f"{Colors.GREEN}O Multiflow foi reinstalado com sucesso!{Colors.NC}")
        print(f"Para iniciar, pode ser necessário sair e entrar novamente no seu terminal.")
        print(f"Use o comando: {Colors.YELLOW}multiflow{Colors.NC}")
    else:
        print("Operação abortada.")

if __name__ == "__main__":
    main()
