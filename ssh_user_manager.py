import subprocess
import getpass
import os
import re
import sys
from datetime import datetime, timedelta

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
        print("6. Listar Todos os Usuários SSH")  # Nova opção adicionada
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
            listar_usuarios()  # Nova função chamada aqui
        elif choice == '0':
            break
        else:
            print("Opção inválida. Tente novamente.")

def criar_usuario():
    # Modificado conforme solicitado pelo usuário
    username = input("qual nome do usuario? ")
    if not validar_username(username):
        print("Nome de usuário inválido. Deve começar com letra ou sublinhado e conter apenas letras, números, sublinhados ou hífens.")
        return

    if usuario_existe(username):
        print(f"O usuário {username} já existe.")
        return

    password = getpass.getpass("digite a senha: ")
    if not validar_senha(password):
        print("Senha inválida. Deve ter pelo menos 4 caracteres.")
        return

    limite = input("limite de conexoes: ")
    if not limite.isdigit() or int(limite) < 1:
        print("Limite inválido. Deve ser um número maior que 0.")
        return

    dias = input("Digite quantos dias o usuario ficará ativo: ")
    if not dias.isdigit() or int(dias) < 1:
        print("Número de dias inválido. Deve ser um número maior que 0.")
        return
    
    # Calcular data de expiração com base nos dias
    expiracao = (datetime.now() + timedelta(days=int(dias))).strftime('%Y-%m-%d')

    cmd = f"useradd -m -s /bin/bash -e {expiracao} {username}"
    if subprocess.run(cmd, shell=True).returncode != 0:
        print(f"Erro ao criar usuário {username}.")
        return

    if subprocess.run(f"echo '{username}:{password}' | chpasswd", shell=True).returncode != 0:
        print(f"Erro ao definir senha para {username}.")
        return

    with open(DB_FILE, 'a') as f:
        f.write(f"{username} {limite}\n")

    print(f"Usuário {username} criado com sucesso.")
    print(f"Data de expiração: {expiracao} ({dias} dias)")
    print(f"Limite de conexões: {limite}")

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

    dias = input("Quantos dias o usuário ficará ativo a partir de hoje (deixe em branco para remover expiração): ")
    
    if dias == "":
        expiracao = ""
    elif dias.isdigit() and int(dias) > 0:
        expiracao = (datetime.now() + timedelta(days=int(dias))).strftime('%Y-%m-%d')
    else:
        print("Número de dias inválido. Deve ser um número maior que 0.")
        return

    cmd = f"chage -E {expiracao if expiracao else -1} {username}"
    if subprocess.run(cmd, shell=True).returncode != 0:
        print(f"Erro ao alterar data de expiração para {username}.")
        return

    print(f"Data de expiração do usuário {username} alterada com sucesso.")
    if expiracao:
        print(f"Nova data de expiração: {expiracao} ({dias} dias)")
    else:
        print("Usuário não possui data de expiração.")

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

def listar_usuarios():
    """
    Lista todos os usuários SSH do sistema com detalhes sobre expiração e limite de conexões.
    """
    print("\n=== Lista de Usuários SSH ===\n")
    
    # Cabeçalho da tabela
    print(f"{'Usuário':<15} {'UID':<6} {'Expiração':<15} {'Limite':<10} {'Status':<10}")
    print("-" * 60)
    
    # Carregar limites de conexão do arquivo de banco de dados
    limites = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    limites[parts[0]] = parts[1]
    
    # Obter usuários com diretório home em /home
    try:
        # Usar getent para listar todos os usuários com shell válido (não /bin/false ou /sbin/nologin)
        output = subprocess.check_output("getent passwd | grep -v '/bin/false' | grep -v '/sbin/nologin'", shell=True).decode('utf-8')
        
        for line in output.splitlines():
            if ':' in line:
                parts = line.split(':')
                username = parts[0]
                uid = parts[2]
                
                # Ignorar usuários do sistema (UID < 1000, exceto root se quiser listar)
                if int(uid) < 1000 and username != 'root':
                    continue
                    
                # Verificar se o diretório home está em /home ou é /root
                home_dir = parts[5]
                if not (home_dir.startswith('/home/') or home_dir == '/root'):
                    continue
                
                # Obter informação de expiração
                try:
                    chage_output = subprocess.check_output(f"chage -l {username}", shell=True).decode('utf-8')
                    expiry_line = next((line for line in chage_output.splitlines() if "Account expires" in line), "")
                    
                    if "never" in expiry_line.lower():
                        expiracao = "Nunca"
                    else:
                        # Tentar extrair a data
                        match = re.search(r'(\w{3} \d{2}, \d{4})', expiry_line)
                        if match:
                            expiracao = match.group(1)
                        else:
                            expiracao = "Desconhecido"
                    
                    # Verificar se a conta está bloqueada
                    passwd_status = subprocess.check_output(f"passwd -S {username}", shell=True).decode('utf-8')
                    status = "Ativo"
                    if "locked" in passwd_status:
                        status = "Bloqueado"
                    
                    # Obter o limite de conexões
                    limite = limites.get(username, "N/A")
                    
                    # Imprimir informações do usuário
                    print(f"{username:<15} {uid:<6} {expiracao:<15} {limite:<10} {status:<10}")
                    
                except subprocess.CalledProcessError:
                    print(f"{username:<15} {uid:<6} {'Erro':<15} {limites.get(username, 'N/A'):<10} {'Desconhecido':<10}")
    
    except subprocess.CalledProcessError as e:
        print(f"Erro ao listar usuários: {str(e)}")
    
    print("\nTotal de usuários SSH: {0}".format(len(limites)))

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
