#!/usr/bin/env python3
import subprocess
import getpass
import os
import re
import sys
import random # Adicionado para geração de senhas aleatórias
from datetime import datetime, timedelta

# Caminho para o arquivo de banco de dados de usuários
DB_FILE = '/root/ssh_users.db'

def generate_random_password():
    """Gera uma senha aleatória de 4 dígitos."""
    return str(random.randint(1000, 9999))

def main():
    if os.geteuid() != 0:
        print("Este script deve ser executado como root.")
        sys.exit(1)

    while True:
        print("\nGerenciamento de Usuários SSH")
        print("1. Criar Usuário")
        print("2. Remover Usuário")
        print("3. Alterar Senha")
        print("4. Alterar Data de Expiração")
        print("5. Alterar Limite de Conexões")
        print("6. Listar Todos os Usuários SSH")
        print("0. Sair")
        choice = input("Escolha uma opção: ")

        if choice == '1':
            criar_usuario()
        elif choice == '2':
            remover_usuario()
        elif choice == '3':
            alterar_senha()
        elif choice == '4':
            alterar_data_expiracao()
        elif choice == '5':
            alterar_limite_conexoes()
        elif choice == '6':
            listar_usuarios()
        elif choice == '0':
            break
        else:
            print("Opção inválida. Tente novamente.")

def criar_usuario():
    username = input("Qual o nome do usuário? ")
    if not validar_username(username):
        print("Nome de usuário inválido. Deve ter entre 3 e 32 caracteres, começar com letra minúscula e conter apenas letras minúsculas, números, sublinhados ou hífens.")
        return

    if usuario_existe(username):
        print(f"O usuário {username} já existe.")
        return

    password = generate_random_password() # Senha gerada automaticamente
    print(f"Senha gerada automaticamente: {password}")
    input("Pressione Enter para continuar...") # Adicionado para confirmação

    try:
        limite = int(input("Limite de conexões: "))
        if limite < 1:
            raise ValueError()
    except ValueError:
        print("Limite inválido. Deve ser um número inteiro maior que 0.")
        return

    try:
        dias_input = input("Digite quantos dias o usuário ficará ativo (padrão: 30): ") or "30"
        dias = int(dias_input)
        if dias < 1:
            raise ValueError()
    except ValueError:
        print("Número de dias inválido. Deve ser um número inteiro maior que 0.")
        return
    
    expiracao = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

    try:
        subprocess.run(["useradd", "-m", "-s", "/bin/bash", "-e", expiracao, username], check=True)
        subprocess.run(["chpasswd"], input=f"{username}:{password}", text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao criar usuário {username}: {e}")
        return

    # Garante que o diretório /root exista
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with open(DB_FILE, 'a') as f:
        f.write(f"{username} {limite}\n")

    print("\nCriado Com Sucesso:")
    print(f"login: {username}")
    print(f"senha: {password}")
    print(f"conexoes: {limite}")
    print(f"Expiração: {expiracao} ({dias} dias)")

def remover_usuario():
    username = input("Nome do usuário a remover: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    try:
        subprocess.run(["userdel", "-r", username], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao remover usuário {username}: {e}")
        return

    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            lines = f.readlines()
        with open(DB_FILE, 'w') as f:
            for line in lines:
                if not line.startswith(f"{username} "):
                    f.write(line)

    print(f"Usuário {username} removido com sucesso.")

def alterar_senha():
    username = input("Nome do usuário: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    password = getpass.getpass("Nova senha: ")
    if not validar_senha(password):
        print("Senha inválida. Deve ter pelo menos 4 caracteres.")
        return

    try:
        subprocess.run(["chpasswd"], input=f"{username}:{password}", text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao alterar senha para {username}: {e}")
        return

    print(f"Senha do usuário {username} alterada com sucesso.")

def alterar_data_expiracao():
    username = input("Nome do usuário: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    dias_input = input("Quantos dias o usuário ficará ativo a partir de hoje (deixe em branco para remover expiração): ")
    
    if not dias_input:
        expiracao_param = "-1" # Parâmetro para remover expiração no chage
        expiracao_display = "Nunca"
    else:
        try:
            dias = int(dias_input)
            if dias <= 0:
                raise ValueError()
            expiracao_param = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
            expiracao_display = f"{expiracao_param} ({dias} dias)"
        except ValueError:
            print("Número de dias inválido. Deve ser um número inteiro maior que 0.")
            return

    try:
        subprocess.run(["chage", "-E", expiracao_param, username], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao alterar data de expiração para {username}: {e}")
        return

    print(f"Data de expiração do usuário {username} alterada com sucesso.")
    print(f"Nova data de expiração: {expiracao_display}")

def alterar_limite_conexoes():
    username = input("Nome do usuário: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    try:
        limite = int(input("Novo limite de conexões simultâneas: "))
        if limite < 1:
            raise ValueError()
    except ValueError:
        print("Limite inválido. Deve ser um número inteiro maior que 0.")
        return

    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    lines = []
    updated = False
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            lines = f.readlines()
    
    with open(DB_FILE, 'w') as f:
        for line in lines:
            if line.startswith(f"{username} "):
                f.write(f"{username} {limite}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"{username} {limite}\n")

    print(f"Limite de conexões do usuário {username} alterado para {limite}.")

def listar_usuarios():
    print("\n=== Lista de Usuários SSH ===\n")
    print(f"{'Usuário':<15} {'UID':<6} {'Expiração':<20} {'Limite':<10} {'Status':<10}")
    print("-" * 75)
    
    limites = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    limites[parts[0]] = parts[1]
    
    try:
        output = subprocess.check_output(["getent", "passwd"], text=True)
        user_count = 0
        for line in output.splitlines():
            parts = line.split(':')
            username, uid, home_dir = parts[0], parts[2], parts[5]
            
            if not (home_dir.startswith('/home/') or home_dir == '/root') or int(uid) < 1000:
                continue
            
            user_count += 1
            try:
                chage_output = subprocess.check_output(["chage", "-l", username], text=True)
                expiry_line = next((line for line in chage_output.splitlines() if "Account expires" in line), "")
                expiracao = "Nunca" if "never" in expiry_line else expiry_line.split(':')[-1].strip()
                
                passwd_status = subprocess.check_output(["passwd", "-S", username], text=True)
                status = "Bloqueado" if " L " in passwd_status else "Ativo"
                
                limite = limites.get(username, "N/A")
                
                print(f"{username:<15} {uid:<6} {expiracao:<20} {limite:<10} {status:<10}")
                
            except subprocess.CalledProcessError:
                print(f"{username:<15} {uid:<6} {'Erro ao obter dados':<20} {limites.get(username, 'N/A'):<10} {'Desconhecido':<10}")
        
        print("\nTotal de usuários SSH gerenciáveis: {0}".format(user_count))

    except subprocess.CalledProcessError as e:
        print(f"Erro ao listar usuários: {e}")
    except FileNotFoundError:
        print("Comando 'getent' não encontrado. Verifique se o pacote 'passwd' está instalado.")

def validar_username(username):
    return re.match(r'^[a-z][a-z0-9_-]{2,31}$', username) is not None

def validar_senha(senha):
    return len(senha) >= 4

def usuario_existe(username):
    try:
        subprocess.run(["id", username], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

if __name__ == "__main__":
    main()


