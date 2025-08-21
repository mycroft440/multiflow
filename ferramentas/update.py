#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
import requests
import json

# --- Configurações ---
# REPO_URL = "https://github.com/mycroft440/multiflow.git"
REPO_URL = "file:///home/ubuntu/multiflow_local_repo" # Usar repositório local para testes
INSTALL_DIR = "/opt/multiflow"
TMP_DIR = "/tmp/multiflow_update_temp"

# Arquivos e diretórios a serem preservados (configurações do usuário)
# Estes serão copiados de volta após a atualização.
PRESERVE_PATHS = [
    os.path.join(INSTALL_DIR, "conexoes", "meu_servidor.conf"), # Exemplo: arquivo de configuração do usuário
    os.path.join(INSTALL_DIR, "ferramentas", "usuarios.json"), # Exemplo: dados de usuários
    # Adicione outros arquivos/diretórios que você queira preservar
]

# --- Funções de Utilitário ---
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'

def print_status(message, color=Colors.CYAN):
    print(f"\n{color}◆ {message}{Colors.NC}")

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.NC}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.NC}")
    sys.exit(1)

def run_command(command, check=True, cwd=None, capture_output=False):
    try:
        result = subprocess.run(command, check=check, cwd=cwd, capture_output=capture_output, text=True, encoding='utf-8')
        if capture_output:
            return result.stdout.strip()
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Comando falhou: {e.cmd}\nSaída: {e.stderr}")
    except FileNotFoundError:
        print_error(f"Comando não encontrado: {command[0]}")
    return False

def check_root():
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado como root. Por favor, use 'sudo'.")

# --- Funções de Atualização ---
def get_current_commit_hash(repo_path):
    try:
        return run_command(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True)
    except Exception:
        return None

def get_remote_commit_hash(repo_url):
    try:
        # Clona temporariamente para obter o hash do commit mais recente
        temp_clone_dir = "/tmp/multiflow_remote_check"
        if os.path.exists(temp_clone_dir):
            shutil.rmtree(temp_clone_dir)
        run_command(["git", "clone", "--depth", "1", repo_url, temp_clone_dir])
        commit_hash = run_command(["git", "rev-parse", "HEAD"], cwd=temp_clone_dir, capture_output=True)
        shutil.rmtree(temp_clone_dir)
        return commit_hash
    except Exception:
        return None

def backup_user_files(backup_dir):
    print_status("Fazendo backup de arquivos de configuração do usuário...")
    os.makedirs(backup_dir, exist_ok=True)
    for path in PRESERVE_PATHS:
        if os.path.exists(path):
            relative_path = os.path.relpath(path, INSTALL_DIR)
            dest_path = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                if os.path.isdir(path):
                    shutil.copytree(path, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(path, dest_path)
                print_success(f"Backup de {relative_path}")
            except Exception as e:
                print_warning(f"Falha ao fazer backup de {relative_path}: {e}")
        else:
            print_warning(f"Arquivo/diretório a preservar não encontrado: {os.path.relpath(path, INSTALL_DIR)}")

def restore_user_files(backup_dir):
    print_status("Restaurando arquivos de configuração do usuário...")
    for path in PRESERVE_PATHS:
        relative_path = os.path.relpath(path, INSTALL_DIR)
        src_path = os.path.join(backup_dir, relative_path)
        if os.path.exists(src_path):
            try:
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, path)
                print_success(f"Restaurado {relative_path}")
            except Exception as e:
                print_warning(f"Falha ao restaurar {relative_path}: {e}")
        else:
            print_warning(f"Backup de {relative_path} não encontrado para restauração.")

def perform_update():
    print_status("Iniciando processo de atualização do MultiFlow...")

    # 1. Verificar se o diretório de instalação existe e é um repositório git
    if not os.path.exists(INSTALL_DIR) or not os.path.isdir(os.path.join(INSTALL_DIR, ".git")):
        print_warning(f"Diretório de instalação \'{INSTALL_DIR}\' não encontrado ou não é um repositório Git. Tentando clonar...")
        if os.path.exists(INSTALL_DIR):
            shutil.rmtree(INSTALL_DIR) # Limpa se existir mas não for um repo válido
        run_command(["git", "clone", REPO_URL, INSTALL_DIR])
        print_success("Repositório clonado com sucesso.")
        print_status("Atualização inicial concluída. Por favor, execute 'multiflow' novamente.", Colors.GREEN)
        sys.exit(0)

    current_hash = get_current_commit_hash(INSTALL_DIR)
    remote_hash = get_remote_commit_hash(REPO_URL)

    if not current_hash or not remote_hash:
        print_error("Não foi possível determinar os hashes de commit. Verifique sua conexão com a internet ou o URL do repositório.")

    # Forçando a atualização para fins de teste, mesmo que os hashes sejam iguais
    # if current_hash == remote_hash:
    #     print_status("Seu MultiFlow já está atualizado!", Colors.GREEN)
    #     return
    # else:
    print_status(f"Nova versão disponível! (Local: {current_hash[:7]}... Remoto: {remote_hash[:7]}...)")

    # 2. Criar diretório temporário para o novo clone
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    os.makedirs(TMP_DIR)

    # 3. Clonar o repositório para o diretório temporário
    print_status(f"Clonando a versão mais recente para {TMP_DIR}...")
    run_command(["git", "clone", REPO_URL, TMP_DIR])
    print_success("Novo repositório clonado.")

    # 4. Fazer backup dos arquivos do usuário
    backup_dir = os.path.join(TMP_DIR, "_backup_user_files")
    backup_user_files(backup_dir)

    # 5. Remover o diretório de instalação antigo (exceto o .git para preservar histórico)
    print_status(f"Removendo arquivos antigos em {INSTALL_DIR} (preservando .git)...")
    for item in os.listdir(INSTALL_DIR):
        if item == ".git":
            continue
        item_path = os.path.join(INSTALL_DIR, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    print_success("Arquivos antigos removidos.")

    # 6. Copiar os novos arquivos para o diretório de instalação
    print_status(f"Copiando novos arquivos de {TMP_DIR} para {INSTALL_DIR}...")
    for item in os.listdir(TMP_DIR):
        if item == ".git" or item == "_backup_user_files": # Não copiar o .git ou o backup
            continue
        s = os.path.join(TMP_DIR, item)
        d = os.path.join(INSTALL_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
    print_success("Novos arquivos copiados.")

    # 7. Restaurar arquivos do usuário
    restore_user_files(backup_dir)

    # 8. Limpar diretório temporário
    print_status("Limpando arquivos temporários...")
    shutil.rmtree(TMP_DIR)
    print_success("Limpeza concluída.")

    # 9. Executar scripts de pós-atualização (se houver)
    # Exemplo: Se houver um script 'post_update.sh' na raiz do repositório
    post_update_script = os.path.join(INSTALL_DIR, "install.sh") # Reutilizando install.sh para pós-atualização
    if os.path.exists(post_update_script):
        print_status("Executando script de pós-atualização (install.sh)...")
        # Certifique-se de que o script é executável
        os.chmod(post_update_script, 0o755)
        run_command([post_update_script, "--update-only"]) # Adicione um flag para o install.sh saber que é uma atualização
        print_success("Script de pós-atualização executado.")
    else:
        print_warning("Nenhum script de pós-atualização (install.sh) encontrado.")

    print_status("MultiFlow atualizado com sucesso!", Colors.GREEN)
    print_status("Por favor, reinicie o 'multiflow' para aplicar as mudanças.", Colors.YELLOW)

# --- Função Principal ---
def main():
    check_root()
    perform_update()

if __name__ == "__main__":
    main()
