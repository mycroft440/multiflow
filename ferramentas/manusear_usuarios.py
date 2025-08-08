#!/usr/bin/env python3
import subprocess
import getpass
import os
import re
import sys
import random
from datetime import datetime, timedelta

# Importa as ferramentas de estilo para manter a consistência visual
try:
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError:
    # Fallback para o caso de o script ser executado de forma isolada
    print("Aviso: Módulo de estilo não encontrado. O menu será exibido sem formatação.")
    # Define classes e funções dummy para evitar que o script quebre
    class Colors:
        RED = GREEN = YELLOW = CYAN = BOLD = END = ""
    class BoxChars:
        BOTTOM_LEFT = BOTTOM_RIGHT = HORIZONTAL = ""
    def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')
    def print_colored_box(title, content=None): print(f"--- {title} ---")
    def print_menu_option(num, desc, **kwargs): print(f"{num}. {desc}")

# Instancia as cores
COLORS = Colors()

# Caminho para o arquivo de banco de dados de usuários
DB_FILE = '/root/ssh_users.db'

def generate_random_password():
    """Gera uma senha aleatória de 4 dígitos."""
    return str(random.randint(1000, 9999))

def main():
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script deve ser executado como root.{COLORS.END}")
        sys.exit(1)

    while True:
        clear_screen()
        print_colored_box("GERENCIAR USUÁRIOS SSH")
        print_menu_option("1", "Criar Usuário", color=COLORS.CYAN)
        print_menu_option("2", "Remover Usuário", color=COLORS.CYAN)
        print_menu_option("3", "Alterar Senha", color=COLORS.CYAN)
        print_menu_option("4", "Alterar Data de Expiração", color=COLORS.CYAN)
        print_menu_option("5", "Alterar Limite de Conexões", color=COLORS.CYAN)
        print_menu_option("6", "Listar Todos os Usuários", color=COLORS.CYAN)
        print_menu_option("0", "Voltar ao Menu Principal", color=COLORS.YELLOW)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

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
            print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")


def criar_usuario():
    clear_screen()
    print_colored_box("CRIAR NOVO USUÁRIO SSH")
    username = input(f"{COLORS.CYAN}Qual o nome do usuário? {COLORS.END}")
    if not validar_username(username):
        print(f"\n{COLORS.RED}Nome de usuário inválido. Deve ter entre 3 e 32 caracteres, começar com letra minúscula e conter apenas letras minúsculas, números, sublinhados ou hífens.{COLORS.END}")
        return

    if usuario_existe(username):
        print(f"\n{COLORS.RED}O usuário {username} já existe.{COLORS.END}")
        return

    password = generate_random_password()
    
    try:
        limite_input = input(f"{COLORS.CYAN}Limite de conexões (padrão: 1): {COLORS.END}") or "1"
        limite = int(limite_input)
        if limite < 1: raise ValueError()
    except ValueError:
        print(f"\n{COLORS.RED}Limite inválido. Deve ser um número inteiro maior que 0.{COLORS.END}")
        return

    try:
        dias_input = input(f"{COLORS.CYAN}Digite quantos dias o usuário ficará ativo (padrão: 30): {COLORS.END}") or "30"
        dias = int(dias_input)
        if dias < 1: raise ValueError()
    except ValueError:
        print(f"\n{COLORS.RED}Número de dias inválido. Deve ser um número inteiro maior que 0.{COLORS.END}")
        return
    
    expiracao = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")

    try:
        subprocess.run(["useradd", "-m", "-s", "/bin/bash", "-e", expiracao, username], check=True, capture_output=True)
        subprocess.run(["chpasswd"], input=f"{username}:{password}", text=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{COLORS.RED}Erro ao criar usuário {username}: {e.stderr}{COLORS.END}")
        return

    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with open(DB_FILE, 'a') as f:
        f.write(f"{username} {limite}\n")

    print_colored_box("USUÁRIO CRIADO COM SUCESSO", [
        f"Login: {COLORS.YELLOW}{username}{COLORS.END}",
        f"Senha: {COLORS.YELLOW}{password}{COLORS.END}",
        f"Conexões: {COLORS.YELLOW}{limite}{COLORS.END}",
        f"Expiração: {COLORS.YELLOW}{expiracao} ({dias} dias){COLORS.END}"
    ])

def remover_usuario():
    clear_screen()
    print_colored_box("REMOVER USUÁRIO SSH")
    username = input(f"{COLORS.CYAN}Nome do usuário a remover: {COLORS.END}")
    if not usuario_existe(username):
        print(f"\n{COLORS.RED}O usuário {username} não existe.{COLORS.END}")
        return

    try:
        subprocess.run(["userdel", "-r", username], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{COLORS.RED}Erro ao remover usuário {username}: {e.stderr}{COLORS.END}")
        return

    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            lines = f.readlines()
        with open(DB_FILE, 'w') as f:
            for line in lines:
                if not line.startswith(f"{username} "):
                    f.write(line)

    print(f"\n{COLORS.GREEN}Usuário {username} removido com sucesso.{COLORS.END}")

def alterar_senha():
    clear_screen()
    print_colored_box("ALTERAR SENHA DE USUÁRIO")
    username = input(f"{COLORS.CYAN}Nome do usuário: {COLORS.END}")
    if not usuario_existe(username):
        print(f"\n{COLORS.RED}O usuário {username} não existe.{COLORS.END}")
        return

    password = getpass.getpass(f"{COLORS.CYAN}Nova senha: {COLORS.END}")
    if not validar_senha(password):
        print(f"\n{COLORS.RED}Senha inválida. Deve ter pelo menos 4 caracteres.{COLORS.END}")
        return

    try:
        subprocess.run(["chpasswd"], input=f"{username}:{password}", text=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{COLORS.RED}Erro ao alterar senha para {username}: {e.stderr}{COLORS.END}")
        return

    print(f"\n{COLORS.GREEN}Senha do usuário {username} alterada com sucesso.{COLORS.END}")

def alterar_data_expiracao():
    clear_screen()
    print_colored_box("ALTERAR DATA DE EXPIRAÇÃO")
    username = input(f"{COLORS.CYAN}Nome do usuário: {COLORS.END}")
    if not usuario_existe(username):
        print(f"\n{COLORS.RED}O usuário {username} não existe.{COLORS.END}")
        return

    dias_input = input(f"{COLORS.CYAN}Quantos dias o usuário ficará ativo a partir de hoje (deixe em branco para remover expiração): {COLORS.END}")
    
    if not dias_input:
        expiracao_param = "never"
        expiracao_display = "Nunca"
    else:
        try:
            dias = int(dias_input)
            if dias <= 0: raise ValueError()
            expiracao_param = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
            expiracao_display = f"{expiracao_param} ({dias} dias)"
        except ValueError:
            print(f"\n{COLORS.RED}Número de dias inválido. Deve ser um número inteiro maior que 0.{COLORS.END}")
            return

    try:
        subprocess.run(["chage", "-E", expiracao_param, username], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{COLORS.RED}Erro ao alterar data de expiração para {username}: {e.stderr}{COLORS.END}")
        return

    print(f"\n{COLORS.GREEN}Data de expiração do usuário {username} alterada para: {COLORS.YELLOW}{expiracao_display}{COLORS.END}")

def alterar_limite_conexoes():
    clear_screen()
    print_colored_box("ALTERAR LIMITE DE CONEXÕES")
    username = input(f"{COLORS.CYAN}Nome do usuário: {COLORS.END}")
    if not usuario_existe(username):
        print(f"\n{COLORS.RED}O usuário {username} não existe.{COLORS.END}")
        return

    try:
        limite = int(input(f"{COLORS.CYAN}Novo limite de conexões simultâneas: {COLORS.END}"))
        if limite < 1: raise ValueError()
    except ValueError:
        print(f"\n{COLORS.RED}Limite inválido. Deve ser um número inteiro maior que 0.{COLORS.END}")
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

    print(f"\n{COLORS.GREEN}Limite de conexões do usuário {username} alterado para {COLORS.YELLOW}{limite}{COLORS.END}")

def listar_usuarios():
    clear_screen()
    print_colored_box("LISTA DE USUÁRIOS SSH")
    
    header = f"{COLORS.BOLD}{'Usuário':<15} {'UID':<6} {'Expiração':<20} {'Limite':<10} {'Status':<10}{COLORS.END}"
    print(header)
    print(f"{COLORS.CYAN}{'-' * 75}{COLORS.END}")
    
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
                
                status_color = COLORS.GREEN if status == "Ativo" else COLORS.RED
                
                print(f"{username:<15} {uid:<6} {expiracao:<20} {limite:<10} {status_color}{status:<10}{COLORS.END}")
                
            except subprocess.CalledProcessError:
                print(f"{username:<15} {uid:<6} {'Erro':<20} {limites.get(username, 'N/A'):<10} {'Erro':<10}")
        
        print(f"\n{COLORS.BOLD}Total de usuários SSH gerenciáveis: {COLORS.YELLOW}{user_count}{COLORS.END}")

    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{COLORS.RED}Erro: Não foi possível listar os usuários. Verifique se o comando 'getent' está disponível.{COLORS.END}")

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
