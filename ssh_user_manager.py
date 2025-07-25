import subprocess
import getpass
import os
import re
import sys

# Caminho para o arquivo de banco de dados de usuários
DB_FILE = '/root/usuarios.db'

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
        elif choice == '0':
            break
        else:
            print("Opção inválida. Tente novamente.")

def criar_usuario():
    username = input("Nome do usuário: ")
    if not validar_username(username):
        print("Nome de usuário inválido. Deve começar com letra ou sublinhado e conter apenas letras, números, sublinhados ou hífens.")
        return

    if usuario_existe(username):
        print(f"O usuário {username} já existe.")
        return

    password = getpass.getpass("Senha: ")
    if not validar_senha(password):
        print("Senha inválida. Deve ter pelo menos 4 caracteres.")
        return

    expiracao = input("Data de expiração (YYYY-MM-DD, deixe em branco para sem expiração): ")
    if expiracao and not validar_data(expiracao):
        print("Data inválida. Use o formato YYYY-MM-DD.")
        return

    limite = input("Limite de conexões simultâneas: ")
    if not limite.isdigit() or int(limite) < 1:
        print("Limite inválido. Deve ser um número maior que 0.")
        return

    cmd = f"useradd -m -s /bin/bash {'-e ' + expiracao if expiracao else ''} {username}"
    if subprocess.run(cmd, shell=True).returncode != 0:
        print(f"Erro ao criar usuário {username}.")
        return

    if subprocess.run(f"echo '{username}:{password}' | chpasswd", shell=True).returncode != 0:
        print(f"Erro ao definir senha para {username}.")
        return

    with open(DB_FILE, 'a') as f:
        f.write(f"{username} {limite}\n")

    print(f"Usuário {username} criado com sucesso.")

def remover_usuario():
    username = input("Nome do usuário a remover: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    if subprocess.run(f"userdel -r {username}", shell=True).returncode != 0:
        print(f"Erro ao remover usuário {username}.")
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

    if subprocess.run(f"echo '{username}:{password}' | chpasswd", shell=True).returncode != 0:
        print(f"Erro ao alterar senha para {username}.")
        return

    print(f"Senha do usuário {username} alterada com sucesso.")

def alterar_data_expiracao():
    username = input("Nome do usuário: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    expiracao = input("Nova data de expiração (YYYY-MM-DD, deixe em branco para remover expiração): ")
    if expiracao and not validar_data(expiracao):
        print("Data inválida. Use o formato YYYY-MM-DD.")
        return

    cmd = f"chage -E {expiracao if expiracao else -1} {username}"
    if subprocess.run(cmd, shell=True).returncode != 0:
        print(f"Erro ao alterar data de expiração para {username}.")
        return

    print(f"Data de expiração do usuário {username} alterada com sucesso.")

def alterar_limite_conexoes():
    username = input("Nome do usuário: ")
    if not usuario_existe(username):
        print(f"O usuário {username} não existe.")
        return

    limite = input("Novo limite de conexões simultâneas: ")
    if not limite.isdigit() or int(limite) < 1:
        print("Limite inválido. Deve ser um número maior que 0.")
        return

    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            lines = f.readlines()
        with open(DB_FILE, 'w') as f:
            updated = False
            for line in lines:
                if line.startswith(f"{username} "):
                    f.write(f"{username} {limite}\n")
                    updated = True
                else:
                    f.write(line)
            if not updated:
                f.write(f"{username} {limite}\n")
    else:
        with open(DB_FILE, 'w') as f:
            f.write(f"{username} {limite}\n")

    print(f"Limite de conexões do usuário {username} alterado para {limite}.")

def validar_username(username):
    return re.match(r'^[a-z_][a-z0-9_-]{0,31}$', username) is not None

def validar_senha(senha):
    return len(senha) >= 4

def validar_data(data):
    return re.match(r'^\d{4}-\d{2}-\d{2}$', data) is not None

def usuario_existe(username):
    try:
        subprocess.check_output(f"id {username}", shell=True)
        return True
    except subprocess.CalledProcessError:
        return False

if __name__ == "__main__":
    main()