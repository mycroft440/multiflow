#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
import requests
import re

# Configurações
INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/mycroft440/multiflow/main/install.sh"
INSTALL_DIR = "/opt/multiflow"
TMP_INSTALL_SCRIPT = "/tmp/multiflow_install.sh"

class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'

def print_step(message):
    print(f"\n{Colors.CYAN}◆ {message}{Colors.NC}")
    print(f"{Colors.CYAN}{'-' * (len(message) + 2)}{Colors.NC}")

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.NC}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.NC}")
    sys.exit(1)

def check_root():
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado como root. Por favor, use 'sudo'.")

def run_command(command, check=True, timeout=60):
    # … (restante do código idêntico)
    pass

def stop_and_disable_services():
    # … (função de parar/desabilitar serviços)

def remove_project_files():
    # … (função de remover diretórios e links)

def remove_service_files():
    # … (função de limpar arquivos de serviço)

def remove_configs_and_logs():
    # … (função de limpar configs, logs, hosts e crontab)

def full_cleanup():
    # … (chama as quatro rotinas de limpeza em ordem)

def reinstall():
    # … (baixa e executa o último script de instalação)

def main():
    # … (exibe aviso, pede confirmação e executa full_cleanup + reinstall)

if __name__ == "__main__":
    main()
