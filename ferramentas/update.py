#!/usr/bin/env python3
"""
Script Python para atualizar o projeto multiflow sem backup.
Remove o diretório atual, clona o repositório e reinicia o serviço.
Ajuste as variáveis APP_DIR, REPO_URL e SYSTEMD_SERVICE conforme necessário.
"""

import subprocess
import shutil
from pathlib import Path

# Ajustes de ambiente
APP_DIR = Path("/opt/multiflow")                # Diretório onde o projeto será instalado
REPO_URL = "https://github.com/mycroft440/multiflow.git"  # URL do repositório
SYSTEMD_SERVICE = "multiflow.service"           # Nome do serviço systemd (deixe como '' para ignorar)

def run_cmd(cmd):
    """Executa um comando no shell e aborta se houver erro."""
    print(f"Executando: {cmd}")
    subprocess.run(cmd, check=True, shell=True)

def main():
    # Interrompe o serviço, se definido
    if SYSTEMD_SERVICE:
        try:
            run_cmd(f"sudo systemctl stop {SYSTEMD_SERVICE}")
        except subprocess.CalledProcessError as e:
            print(f"Erro ao parar serviço (continuando mesmo assim): {e}")

    # Remove diretório existente
    if APP_DIR.exists():
        print(f"Removendo diretório existente: {APP_DIR}")
        shutil.rmtree(APP_DIR)

    # Clona o repositório
    run_cmd(f"git clone --depth 1 {REPO_URL} {APP_DIR}")

    # Instala dependências de Python se houver requirements.txt
    req_file = APP_DIR / "requirements.txt"
    if req_file.exists():
        venv_path = APP_DIR / "venv"
        run_cmd(f"python3 -m venv {venv_path}")
        run_cmd(f"{venv_path}/bin/pip install --upgrade pip")
        run_cmd(f"{venv_path}/bin/pip install -r {req_file}")

    # Instala dependências Node.js se houver package.json
    pkg_file = APP_DIR / "package.json"
    if pkg_file.exists():
        run_cmd(f"cd {APP_DIR} && npm install --production")

    # Reinicia o serviço, se definido
    if SYSTEMD_SERVICE:
        run_cmd(f"sudo systemctl start {SYSTEMD_SERVICE}")

    print("Atualização concluída com sucesso.")

if __name__ == "__main__":
    main()
