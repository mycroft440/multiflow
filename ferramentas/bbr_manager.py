#!/usr/bin/env python3
import subprocess
import os
import sys

SYSCTL_CONF = "/etc/sysctl.conf"
BBR_SETTINGS = [
    "net.core.default_qdisc=fq",
    "net.ipv4.tcp_congestion_control=bbr"
]

def _run_cmd(cmd, check=True):
    """Helper to run shell commands."""
    try:
        return subprocess.run(cmd, check=check, capture_output=True, text=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{cmd}': {e.stderr}", file=sys.stderr)
        return None

def check_status():
    """Checks the current TCP congestion control algorithm."""
    result = _run_cmd("sysctl net.ipv4.tcp_congestion_control")
    if result and result.returncode == 0:
        return result.stdout.strip().split("=")[1].strip()
    return "desconhecido"

def is_bbr_persistent():
    """Checks if BBR settings are in /etc/sysctl.conf."""
    if not os.path.exists(SYSCTL_CONF):
        return False
    try:
        with open(SYSCTL_CONF, 'r') as f:
            content = f.read()
        return all(setting in content for setting in BBR_SETTINGS)
    except IOError:
        return False

def enable():
    """Enables BBR and makes it persistent."""
    if os.geteuid() != 0:
        return False, "Este script precisa de privilégios de root para modificar configurações do sistema."

    # Check kernel version
    kernel_version_result = _run_cmd("uname -r")
    if not kernel_version_result:
        return False, "Não foi possível determinar a versão do kernel."
        
    kernel_version = kernel_version_result.stdout.split('-')[0]
    if tuple(map(int, kernel_version.split('.')[:2])) < (4, 9):
        return False, f"Seu kernel ({kernel_version}) é anterior a 4.9. O BBR não é suportado."

    try:
        # Backup sysctl.conf before modifying
        if not os.path.exists(f"{SYSCTL_CONF}.bak_multiflow"):
             _run_cmd(f"cp {SYSCTL_CONF} {SYSCTL_CONF}.bak_multiflow")

        # Remove old settings to avoid duplicates
        disable(silent=True)

        # Add new settings
        with open(SYSCTL_CONF, 'a') as f:
            f.write("\n# Configurações do TCP BBR adicionadas pelo Multiflow\n")
            for setting in BBR_SETTINGS:
                f.write(f"{setting}\n")

        # Apply settings immediately
        result = _run_cmd("sysctl -p")
        if result and result.returncode == 0:
            if check_status() == 'bbr':
                return True, "Otimização TCP BBR ativada com sucesso e configurada para persistir após reinicializações."
            else:
                return False, "As configurações foram aplicadas, mas o BBR não parece estar ativo. Verifique a saída de 'sysctl -p'."
        else:
            return False, "Falha ao aplicar as configurações do sysctl."

    except Exception as e:
        return False, f"Ocorreu um erro inesperado: {e}"

def disable(silent=False):
    """Disables BBR by removing settings from sysctl.conf."""
    if os.geteuid() != 0 and not silent:
        return False, "Este script precisa de privilégios de root."

    try:
        if os.path.exists(SYSCTL_CONF):
            with open(SYSCTL_CONF, 'r') as f:
                lines = f.readlines()

            # Filter out BBR settings and comments
            with open(SYSCTL_CONF, 'w') as f:
                for line in lines:
                    if not any(setting in line for setting in BBR_SETTINGS) and "# Configurações do TCP BBR" not in line:
                        f.write(line)

            # Apply changes to revert to system default (usually cubic)
            _run_cmd("sysctl -p")

            if not silent:
                if check_status() != 'bbr':
                    return True, "Otimização BBR desativada. O sistema voltou ao algoritmo padrão."
                else:
                    return False, "As configurações foram removidas, mas o BBR ainda parece estar ativo."
        return True, "Nenhuma configuração persistente do BBR encontrada."

    except Exception as e:
        if not silent:
            return False, f"Ocorreu um erro inesperado: {e}"
        return False, ""
