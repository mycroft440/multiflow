#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import getpass
import os
import re
import sys
import random
import time
import json
from datetime import datetime, timedelta

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import (
        MC, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# Caminho para o arquivo de banco de dados de usuários
DB_FILE = '/root/ssh_users.db'
CREDENTIALS_FILE = '/root/.ssh_credentials.json'  # Arquivo para armazenar credenciais temporariamente

def generate_random_password():
    """Gera uma senha aleatória de 4 dígitos."""
    return str(random.randint(1000, 9999))

def save_credentials(username, password):
    """Salva as credenciais em arquivo JSON para exibição posterior"""
    credentials = {}
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
        except:
            credentials = {}
    
    credentials[username] = {
        'password': password,
        'created': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)
    
    # Define permissões restritivas para o arquivo
    os.chmod(CREDENTIALS_FILE, 0o600)

def get_saved_password(username):
    """Recupera a senha salva de um usuário"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
                return credentials.get(username, {}).get('password', 'N/A')
        except:
            pass
    return 'N/A'

def remove_saved_credentials(username):
    """Remove as credenciais salvas de um usuário"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
            
            if username in credentials:
                del credentials[username]
                
                with open(CREDENTIALS_FILE, 'w') as f:
                    json.dump(credentials, f, indent=2)
        except:
            pass

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

def verify_user_password(username):
    """Verifica se o usuário tem senha configurada corretamente"""
    try:
        # Verifica o status da senha
        result = subprocess.run(
            ["passwd", "-S", username],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            # Status: P = password set, L = locked, NP = no password
            status_line = result.stdout.strip()
            if " P " in status_line:
                return True, "Senha configurada"
            elif " L " in status_line:
                return False, "Conta bloqueada"
            elif " NP " in status_line:
                return False, "Sem senha"
        
        return False, "Status desconhecido"
    except:
        return False, "Erro ao verificar"

def get_ssh_users():
    """Retorna lista de usuários SSH gerenciáveis ordenada alfabeticamente"""
    users = []
    try:
        output = subprocess.check_output(["getent", "passwd"], text=True)
        for line in output.splitlines():
            parts = line.split(':')
            username, uid, home_dir = parts[0], parts[2], parts[5]
            
            if (home_dir.startswith('/home/') or (home_dir == '/root' and username != 'root')) and int(uid) >= 1000:
                users.append(username)
    except:
        pass
    
    return sorted(users)  # Retorna lista ordenada alfabeticamente

def get_total_users():
    """Conta o total de usuários SSH gerenciáveis"""
    return len(get_ssh_users())

def get_active_users():
    """Conta usuários ativos (não bloqueados)"""
    active = 0
    for username in get_ssh_users():
        try:
            passwd_status = subprocess.check_output(["passwd", "-S", username], text=True)
            if " P " in passwd_status:  # P = password set and usable
                active += 1
        except:
            pass
    return active

def build_main_frame(status_msg=""):
    s = []
    s.append(simple_header("GERENCIAR USUÁRIOS SSH"))
    
    total_users = get_total_users()
    active_users = get_active_users()
    
    s.append(modern_box("STATUS DO SISTEMA", [
        f"{MC.CYAN_LIGHT}Total de Usuários:{MC.RESET} {MC.WHITE}{total_users}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Usuários Ativos:{MC.RESET} {MC.GREEN_GRADIENT}{active_users}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Usuários Bloqueados:{MC.RESET} {MC.RED_GRADIENT}{total_users - active_users}{MC.RESET}"
    ], "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    
    s.append("\n")
    s.append(modern_box("OPÇÕES DISPONÍVEIS", [], "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    
    s.append(menu_option("1", "Criar Usuário", "", MC.GREEN_GRADIENT))
    s.append(menu_option("2", "Remover Usuário", "", MC.RED_GRADIENT))
    s.append(menu_option("3", "Alterar Senha", "", MC.CYAN_GRADIENT))
    s.append(menu_option("4", "Alterar Data de Expiração", "", MC.YELLOW_GRADIENT))
    s.append(menu_option("5", "Alterar Limite de Conexões", "", MC.ORANGE_GRADIENT))
    s.append(menu_option("6", "Listar Todos os Usuários", "", MC.PURPLE_GRADIENT))
    s.append(menu_option("7", "Ver Credenciais Salvas", "", MC.BLUE_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    
    s.append(footer_line(status_msg))
    return "".join(s)

def build_user_selection_frame(title, action_color=MC.YELLOW_GRADIENT):
    """Frame genérico para seleção de usuários"""
    s = []
    s.append(simple_header(title))
    
    users = get_ssh_users()
    
    if not users:
        s.append(modern_box("AVISO", [
            f"{MC.YELLOW_GRADIENT}Nenhum usuário SSH disponível{MC.RESET}"
        ], "", MC.YELLOW_GRADIENT, MC.YELLOW_LIGHT))
    else:
        # Obtém informações adicionais dos usuários
        users_info = []
        for i, username in enumerate(users, 1):
            try:
                # Verifica status
                passwd_status = subprocess.check_output(["passwd", "-S", username], text=True)
                if " P " in passwd_status:
                    status = f"{MC.GREEN_GRADIENT}[Ativo]{MC.RESET}"
                elif " L " in passwd_status:
                    status = f"{MC.RED_GRADIENT}[Bloqueado]{MC.RESET}"
                else:
                    status = f"{MC.YELLOW_GRADIENT}[Sem senha]{MC.RESET}"
                
                # Verifica expiração
                chage_output = subprocess.check_output(["chage", "-l", username], text=True)
                expiry_line = next((line for line in chage_output.splitlines() if "Account expires" in line), "")
                if "never" in expiry_line:
                    expiry = "Nunca"
                else:
                    expiry_date = expiry_line.split(':')[-1].strip()[:10]
                    expiry = expiry_date if expiry_date else "N/A"
                
                users_info.append(
                    f"{MC.WHITE}[{i:2d}]{MC.RESET} {MC.YELLOW_GRADIENT}{username:<15}{MC.RESET} "
                    f"{status} {MC.GRAY}Exp: {expiry}{MC.RESET}"
                )
            except:
                users_info.append(
                    f"{MC.WHITE}[{i:2d}]{MC.RESET} {MC.YELLOW_GRADIENT}{username:<15}{MC.RESET} "
                    f"{MC.GRAY}[Info não disponível]{MC.RESET}"
                )
        
        users_info.append("")
        users_info.append(f"{MC.CYAN_LIGHT}Digite o número do usuário{MC.RESET}")
        users_info.append(f"{MC.CYAN_LIGHT}Digite 0 para cancelar{MC.RESET}")
        
        s.append(modern_box("SELECIONE O USUÁRIO", users_info, "", action_color, MC.CYAN_LIGHT))
    
    s.append(footer_line())
    return "".join(s), users

def build_confirm_removal_frame(username):
    s = []
    s.append(simple_header("CONFIRMAR REMOÇÃO"))
    
    # Obtém informações do usuário
    info = []
    try:
        # Informações básicas
        pwd_entry = subprocess.check_output(["getent", "passwd", username], text=True).strip()
        parts = pwd_entry.split(':')
        home_dir = parts[5] if len(parts) > 5 else "N/A"
        
        info.append(f"{MC.RED_GRADIENT}ATENÇÃO: Esta ação é irreversível!{MC.RESET}")
        info.append("")
        info.append(f"{MC.CYAN_LIGHT}Usuário:{MC.RESET} {MC.YELLOW_GRADIENT}{username}{MC.RESET}")
        info.append(f"{MC.CYAN_LIGHT}Diretório Home:{MC.RESET} {MC.WHITE}{home_dir}{MC.RESET}")
        
        # Verifica se tem processos rodando
        try:
            ps_output = subprocess.check_output(["ps", "-u", username], text=True)
            process_count = len(ps_output.strip().split('\n')) - 1  # Remove header
            if process_count > 0:
                info.append(f"{MC.YELLOW_GRADIENT}Processos ativos:{MC.RESET} {MC.RED_GRADIENT}{process_count}{MC.RESET}")
        except:
            pass
        
        # Verifica se está conectado
        try:
            who_output = subprocess.check_output(["who"], text=True)
            if username in who_output:
                info.append(f"{MC.RED_GRADIENT}⚠ Usuário está conectado no momento!{MC.RESET}")
        except:
            pass
        
        info.append("")
        info.append(f"{MC.WHITE}Os seguintes itens serão removidos:{MC.RESET}")
        info.append(f"  • Conta do usuário")
        info.append(f"  • Diretório home e todos os arquivos")
        info.append(f"  • Configurações e credenciais salvas")
        info.append("")
        info.append(f"{MC.GREEN_GRADIENT}Pressione ENTER para prosseguir{MC.RESET}")
        info.append(f"{MC.RED_GRADIENT}Digite 'x' para cancelar{MC.RESET}")
        
    except Exception as e:
        info.append(f"{MC.RED_GRADIENT}Erro ao obter informações: {e}{MC.RESET}")
    
    s.append(modern_box("CONFIRMAR REMOÇÃO DE USUÁRIO", info, "", MC.RED_GRADIENT, MC.RED_LIGHT))
    s.append(footer_line("Aguardando confirmação..."))
    return "".join(s)

def build_expiry_change_frame(username):
    """Frame para alterar data de expiração de um usuário específico"""
    s = []
    s.append(simple_header("ALTERAR DATA DE EXPIRAÇÃO"))
    
    info = []
    try:
        # Obtém informações atuais do usuário
        chage_output = subprocess.check_output(["chage", "-l", username], text=True)
        expiry_line = next((line for line in chage_output.splitlines() if "Account expires" in line), "")
        current_expiry = "Nunca" if "never" in expiry_line else expiry_line.split(':')[-1].strip()
        
        info.append(f"{MC.CYAN_LIGHT}Usuário selecionado:{MC.RESET} {MC.YELLOW_GRADIENT}{username}{MC.RESET}")
        info.append(f"{MC.CYAN_LIGHT}Expiração atual:{MC.RESET} {MC.WHITE}{current_expiry}{MC.RESET}")
        info.append("")
        info.append(f"{MC.WHITE}Digite o número de dias de validade a partir de hoje{MC.RESET}")
        info.append(f"{MC.WHITE}Deixe vazio para remover a expiração (nunca expira){MC.RESET}")
        info.append("")
        info.append(f"{MC.YELLOW_GRADIENT}Exemplos:{MC.RESET}")
        info.append(f"  • 30 = expira em 30 dias")
        info.append(f"  • 90 = expira em 90 dias")
        info.append(f"  • (vazio) = nunca expira")
        
    except Exception as e:
        info.append(f"{MC.RED_GRADIENT}Erro ao obter informações: {e}{MC.RESET}")
    
    s.append(modern_box("NOVA DATA DE EXPIRAÇÃO", info, "", MC.YELLOW_GRADIENT, MC.YELLOW_LIGHT))
    s.append(footer_line())
    return "".join(s)

def build_create_user_frame():
    s = []
    s.append(simple_header("CRIAR NOVO USUÁRIO SSH"))
    s.append(modern_box("INFORMAÇÕES DO NOVO USUÁRIO", [
        f"{MC.YELLOW_GRADIENT}Digite as informações para criar o usuário{MC.RESET}",
        "",
        f"{MC.WHITE}• Nome deve ter 3-32 caracteres{MC.RESET}",
        f"{MC.WHITE}• Começar com letra minúscula{MC.RESET}",
        f"{MC.WHITE}• Usar apenas: a-z, 0-9, _, -{MC.RESET}",
        "",
        f"{MC.CYAN_LIGHT}A senha será gerada automaticamente{MC.RESET}"
    ], "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
    s.append(footer_line())
    return "".join(s)

def build_user_created_frame(username, password, limite, expiracao, dias):
    s = []
    s.append(simple_header("USUÁRIO CRIADO COM SUCESSO"))
    s.append(modern_box("DADOS DO NOVO USUÁRIO", [
        f"{MC.GREEN_GRADIENT}✓ Usuário criado e configurado com sucesso!{MC.RESET}",
        "",
        f"{MC.CYAN_LIGHT}Login:{MC.RESET} {MC.YELLOW_GRADIENT}{username}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Senha:{MC.RESET} {MC.YELLOW_GRADIENT}{password}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Conexões:{MC.RESET} {MC.WHITE}{limite}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Expiração:{MC.RESET} {MC.WHITE}{expiracao} ({dias} dias){MC.RESET}",
        "",
        f"{MC.RED_GRADIENT}IMPORTANTE: Anote a senha! Ela foi salva temporariamente.{MC.RESET}"
    ], "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
    s.append(footer_line("Usuário criado com sucesso!"))
    return "".join(s)

def build_list_users_frame():
    s = []
    s.append(simple_header("LISTA DE USUÁRIOS SSH"))
    
    limites = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    limites[parts[0]] = parts[1]
    
    users_data = []
    users = get_ssh_users()
    
    for username in users:
        try:
            # Verifica expiração
            chage_output = subprocess.check_output(["chage", "-l", username], text=True)
            expiry_line = next((line for line in chage_output.splitlines() if "Account expires" in line), "")
            expiracao = "Nunca" if "never" in expiry_line else expiry_line.split(':')[-1].strip()[:10]
            
            # Verifica status da senha
            has_password, pwd_status = verify_user_password(username)
            
            if has_password:
                status = f"{MC.GREEN_GRADIENT}Ativo{MC.RESET}"
            else:
                status = f"{MC.RED_GRADIENT}{pwd_status}{MC.RESET}"
            
            limite = limites.get(username, "1")
            
            users_data.append(f"{MC.CYAN_LIGHT}•{MC.RESET} {MC.WHITE}{username:<15}{MC.RESET} "
                            f"{MC.GRAY}Limite: {limite:<3}{MC.RESET} "
                            f"{MC.GRAY}Exp: {expiracao:<12}{MC.RESET} "
                            f"{status}")
            
        except subprocess.CalledProcessError:
            users_data.append(f"{MC.CYAN_LIGHT}•{MC.RESET} {MC.WHITE}{username:<15}{MC.RESET} "
                            f"{MC.RED_GRADIENT}Erro ao obter informações{MC.RESET}")

    if users_data:
        users_data.append("")
        users_data.append(f"{MC.YELLOW_GRADIENT}Total de usuários: {len(users)}{MC.RESET}")
        users_data.append("")
        users_data.append(f"{MC.CYAN_LIGHT}Use a opção 7 para ver senhas salvas{MC.RESET}")
        s.append(modern_box("USUÁRIOS DO SISTEMA", users_data, "", MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    else:
        s.append(modern_box("USUÁRIOS DO SISTEMA", [
            f"{MC.YELLOW_GRADIENT}Nenhum usuário SSH encontrado{MC.RESET}"
        ], "", MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    
    s.append(footer_line())
    return "".join(s)

def build_credentials_frame():
    s = []
    s.append(simple_header("CREDENCIAIS SALVAS"))
    
    creds_data = []
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                credentials = json.load(f)
            
            if credentials:
                for username, info in credentials.items():
                    if usuario_existe(username):
                        creds_data.append(f"{MC.CYAN_LIGHT}•{MC.RESET} {MC.WHITE}Usuário:{MC.RESET} {MC.YELLOW_GRADIENT}{username}{MC.RESET}")
                        creds_data.append(f"  {MC.WHITE}Senha:{MC.RESET} {MC.YELLOW_GRADIENT}{info['password']}{MC.RESET}")
                        creds_data.append(f"  {MC.GRAY}Criado em: {info['created']}{MC.RESET}")
                        creds_data.append("")
            
            if creds_data:
                creds_data.append(f"{MC.RED_GRADIENT}ATENÇÃO: Guarde essas senhas em local seguro!{MC.RESET}")
                s.append(modern_box("SENHAS DOS USUÁRIOS", creds_data, "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
            else:
                s.append(modern_box("SENHAS DOS USUÁRIOS", [
                    f"{MC.YELLOW_GRADIENT}Nenhuma credencial salva encontrada{MC.RESET}"
                ], "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
        except Exception as e:
            s.append(modern_box("ERRO", [
                f"{MC.RED_GRADIENT}Erro ao ler credenciais: {e}{MC.RESET}"
            ], "", MC.RED_GRADIENT, MC.RED_LIGHT))
    else:
        s.append(modern_box("SENHAS DOS USUÁRIOS", [
            f"{MC.YELLOW_GRADIENT}Nenhuma credencial salva encontrada{MC.RESET}",
            "",
            f"{MC.WHITE}As senhas são salvas quando você cria um usuário{MC.RESET}"
        ], "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    
    s.append(footer_line())
    return "".join(s)

def criar_usuario():
    TerminalManager.render(build_create_user_frame())
    TerminalManager.before_input()
    
    username = input(f"\n{MC.CYAN_GRADIENT}Nome do usuário: {MC.RESET}")
    
    if not validar_username(username):
        TerminalManager.after_input()
        return False, "Nome de usuário inválido"
    
    if usuario_existe(username):
        TerminalManager.after_input()
        return False, f"O usuário {username} já existe"
    
    password = generate_random_password()
    
    try:
        limite_input = input(f"{MC.CYAN_GRADIENT}Limite de conexões [1]: {MC.RESET}") or "1"
        limite = int(limite_input)
        if limite < 1: raise ValueError()
    except ValueError:
        TerminalManager.after_input()
        return False, "Limite inválido"
    
    try:
        dias_input = input(f"{MC.CYAN_GRADIENT}Dias de validade [30]: {MC.RESET}") or "30"
        dias = int(dias_input)
        if dias < 1: raise ValueError()
    except ValueError:
        TerminalManager.after_input()
        return False, "Número de dias inválido"
    
    TerminalManager.after_input()
    
    expiracao = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    
    try:
        # Cria o usuário
        result = subprocess.run(
            ["useradd", "-m", "-s", "/bin/bash", "-e", expiracao, username],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Define a senha usando chpasswd
        result = subprocess.run(
            ["chpasswd"],
            input=f"{username}:{password}",
            text=True,
            check=True,
            capture_output=True
        )
        
        # Verifica se a senha foi definida corretamente
        has_password, pwd_status = verify_user_password(username)
        if not has_password:
            # Tenta definir a senha novamente usando passwd
            subprocess.run(
                ["passwd", username],
                input=f"{password}\n{password}\n",
                text=True,
                check=False,
                capture_output=True
            )
        
        # Salva as credenciais
        save_credentials(username, password)
        
    except subprocess.CalledProcessError as e:
        # Se falhou, tenta remover o usuário parcialmente criado
        subprocess.run(["userdel", "-r", username], check=False, capture_output=True)
        return False, f"Erro ao criar usuário: {e}"
    
    # Salva o limite de conexões
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with open(DB_FILE, 'a') as f:
        f.write(f"{username} {limite}\n")
    
    TerminalManager.render(build_user_created_frame(username, password, limite, expiracao, dias))
    TerminalManager.before_input()
    input(f"\n{MC.BOLD}Pressione Enter para continuar...{MC.RESET}")
    TerminalManager.after_input()
    
    return True, f"Usuário {username} criado com sucesso"

def remover_usuario():
    # Renderiza a lista de usuários
    frame_content, users = build_user_selection_frame("REMOVER USUÁRIO SSH", MC.RED_GRADIENT)
    TerminalManager.render(frame_content)
    
    if not users:
        TerminalManager.before_input()
        input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
        TerminalManager.after_input()
        return False, "Nenhum usuário disponível para remoção"
    
    TerminalManager.before_input()
    choice = input(f"\n{MC.RED_GRADIENT}Digite o número do usuário a remover (0 para cancelar): {MC.RESET}")
    TerminalManager.after_input()
    
    # Valida a escolha
    try:
        choice_num = int(choice)
        if choice_num == 0:
            return False, "Operação cancelada"
        if choice_num < 1 or choice_num > len(users):
            return False, "Número inválido"
    except ValueError:
        return False, "Entrada inválida"
    
    username = users[choice_num - 1]
    
    # Mostra tela de confirmação
    TerminalManager.render(build_confirm_removal_frame(username))
    TerminalManager.before_input()
    confirm = input(f"\n{MC.RED_GRADIENT}Pressione ENTER para remover ou 'x' para cancelar: {MC.RESET}")
    TerminalManager.after_input()
    
    if confirm.lower() == 'x':
        return False, "Remoção cancelada"
    
    try:
        # Mata processos do usuário antes de remover
        subprocess.run(["pkill", "-u", username], check=False, capture_output=True)
        time.sleep(1)  # Aguarda processos terminarem
        
        # Remove o usuário
        subprocess.run(["userdel", "-r", username], check=True, capture_output=True)
        
        # Remove as credenciais salvas
        remove_saved_credentials(username)
        
    except subprocess.CalledProcessError as e:
        return False, f"Erro ao remover usuário: {e}"
    
    # Remove do arquivo de limites
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            lines = f.readlines()
        with open(DB_FILE, 'w') as f:
            for line in lines:
                if not line.startswith(f"{username} "):
                    f.write(line)
    
    return True, f"Usuário {username} removido com sucesso"

def alterar_senha():
    TerminalManager.before_input()
    username = input(f"\n{MC.CYAN_GRADIENT}Nome do usuário: {MC.RESET}")
    
    if not usuario_existe(username):
        TerminalManager.after_input()
        return False, f"O usuário {username} não existe"
    
    print(f"{MC.YELLOW_GRADIENT}Digite a nova senha ou deixe vazio para gerar automaticamente{MC.RESET}")
    password = getpass.getpass(f"{MC.CYAN_GRADIENT}Nova senha: {MC.RESET}")
    
    if not password:
        password = generate_random_password()
        print(f"{MC.GREEN_GRADIENT}Senha gerada: {password}{MC.RESET}")
    
    TerminalManager.after_input()
    
    if not validar_senha(password):
        return False, "Senha deve ter pelo menos 4 caracteres"
    
    try:
        subprocess.run(
            ["chpasswd"],
            input=f"{username}:{password}",
            text=True,
            check=True,
            capture_output=True
        )
        
        # Atualiza as credenciais salvas
        save_credentials(username, password)
        
    except subprocess.CalledProcessError as e:
        return False, f"Erro ao alterar senha: {e}"
    
    return True, f"Senha alterada. Nova senha: {password}"

def alterar_data_expiracao():
    # Renderiza a lista de usuários
    frame_content, users = build_user_selection_frame("ALTERAR DATA DE EXPIRAÇÃO", MC.YELLOW_GRADIENT)
    TerminalManager.render(frame_content)
    
    if not users:
        TerminalManager.before_input()
        input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
        TerminalManager.after_input()
        return False, "Nenhum usuário disponível"
    
    TerminalManager.before_input()
    choice = input(f"\n{MC.YELLOW_GRADIENT}Digite o número do usuário (0 para cancelar): {MC.RESET}")
    TerminalManager.after_input()
    
    # Valida a escolha
    try:
        choice_num = int(choice)
        if choice_num == 0:
            return False, "Operação cancelada"
        if choice_num < 1 or choice_num > len(users):
            return False, "Número inválido"
    except ValueError:
        return False, "Entrada inválida"
    
    username = users[choice_num - 1]
    
    # Mostra tela de alteração de expiração
    TerminalManager.render(build_expiry_change_frame(username))
    TerminalManager.before_input()
    dias_input = input(f"\n{MC.YELLOW_GRADIENT}Dias de validade (vazio=nunca): {MC.RESET}")
    TerminalManager.after_input()
    
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
            return False, "Número de dias inválido"
    
    try:
        subprocess.run(["chage", "-E", expiracao_param, username], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        return False, f"Erro ao alterar expiração: {e}"
    
    return True, f"Expiração de {username} alterada para: {expiracao_display}"

def alterar_limite_conexoes():
    TerminalManager.before_input()
    username = input(f"\n{MC.ORANGE_GRADIENT}Nome do usuário: {MC.RESET}")
    
    if not usuario_existe(username):
        TerminalManager.after_input()
        return False, f"O usuário {username} não existe"
    
    try:
        limite = int(input(f"{MC.ORANGE_GRADIENT}Novo limite de conexões: {MC.RESET}"))
        TerminalManager.after_input()
        if limite < 1: raise ValueError()
    except ValueError:
        TerminalManager.after_input()
        return False, "Limite deve ser maior que 0"
    
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
    
    return True, f"Limite alterado para {limite} conexões"

def listar_usuarios():
    TerminalManager.render(build_list_users_frame())
    TerminalManager.before_input()
    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
    TerminalManager.after_input()
    return True, "Listagem concluída"

def ver_credenciais():
    TerminalManager.render(build_credentials_frame())
    TerminalManager.before_input()
    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
    TerminalManager.after_input()
    return True, "Credenciais exibidas"

def main():
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este script deve ser executado como root.{MC.RESET}")
        sys.exit(1)
    
    TerminalManager.enter_alt_screen()
    status = ""
    
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            
            if choice == '1':
                ok, msg = criar_usuario()
                status = msg
            elif choice == '2':
                ok, msg = remover_usuario()
                status = msg
            elif choice == '3':
                ok, msg = alterar_senha()
                status = msg
            elif choice == '4':
                ok, msg = alterar_data_expiracao()
                status = msg
            elif choice == '5':
                ok, msg = alterar_limite_conexoes()
                status = msg
            elif choice == '6':
                ok, msg = listar_usuarios()
                status = msg
            elif choice == '7':
                ok, msg = ver_credenciais()
                status = msg
            elif choice == '0':
                break
            else:
                status = "Opção inválida"
            
            time.sleep(0.6)
    
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main()
