#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import os
import sys
import time
from datetime import datetime, timedelta
from collections import defaultdict

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

def get_online_users():
    """Obtém informações detalhadas dos usuários online"""
    users_info = defaultdict(lambda: {
        'connections': [],
        'total': 0,
        'username': '',
        'first_login': None
    })
    
    try:
        # Obtém usuários conectados via who
        who_output = subprocess.check_output(['who'], text=True).strip()
        if who_output:
            for line in who_output.split('\n'):
                parts = line.split()
                if len(parts) >= 5:
                    username = parts[0]
                    terminal = parts[1]
                    login_date = ' '.join(parts[2:4])
                    ip = parts[4] if len(parts) > 4 and parts[4].startswith('(') else 'local'
                    
                    # Converte data de login para datetime
                    try:
                        login_time = datetime.strptime(login_date, "%Y-%m-%d %H:%M")
                    except:
                        login_time = datetime.now()
                    
                    users_info[username]['connections'].append({
                        'terminal': terminal,
                        'login_time': login_time,
                        'ip': ip.strip('()')
                    })
                    users_info[username]['username'] = username
                    
                    # Guarda o primeiro login (mais antigo)
                    if users_info[username]['first_login'] is None or login_time < users_info[username]['first_login']:
                        users_info[username]['first_login'] = login_time
        
        # Obtém usuários SSH conectados via ss ou netstat
        try:
            # Tenta com ss primeiro (mais moderno)
            ssh_output = subprocess.check_output(
                ['ss', '-tn', 'state', 'established', '( dport = :22 or sport = :22 )'],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
        except:
            try:
                # Fallback para netstat
                ssh_output = subprocess.check_output(
                    ['netstat', '-tn'],
                    text=True,
                    stderr=subprocess.DEVNULL
                ).strip()
            except:
                ssh_output = ""
        
        # Conta conexões SSH ativas
        ssh_connections = 0
        for line in ssh_output.split('\n'):
            if ':22' in line and 'ESTABLISHED' in line:
                ssh_connections += 1
        
        # Adiciona informações de processos dos usuários
        try:
            ps_output = subprocess.check_output(
                ['ps', 'aux'],
                text=True
            ).strip()
            
            for username in users_info:
                process_count = 0
                for line in ps_output.split('\n'):
                    if line.startswith(username):
                        process_count += 1
                users_info[username]['processes'] = process_count
        except:
            pass
        
    except Exception as e:
        print(f"Erro ao obter usuários online: {e}")
    
    # Calcula total de conexões por usuário
    for username in users_info:
        users_info[username]['total'] = len(users_info[username]['connections'])
    
    return dict(users_info)

def format_time_ago(login_time):
    """Formata o tempo decorrido desde o login"""
    now = datetime.now()
    diff = now - login_time
    
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    if days > 0:
        if days == 1:
            return f"{days} dia"
        return f"{days} dias"
    elif hours > 0:
        if hours == 1:
            return f"{hours} hora"
        return f"{hours} horas"
    elif minutes > 0:
        if minutes == 1:
            return f"{minutes} minuto"
        return f"{minutes} minutos"
    else:
        return "agora"

def get_user_details(username):
    """Obtém detalhes adicionados de um usuário específico"""
    details = {
        'home': 'N/A',
        'shell': 'N/A',
        'groups': [],
        'last_commands': []
    }
    
    try:
        # Informações do passwd
        passwd_output = subprocess.check_output(['getent', 'passwd', username], text=True).strip()
        parts = passwd_output.split(':')
        if len(parts) >= 7:
            details['home'] = parts[5]
            details['shell'] = parts[6]
        
        # Grupos do usuário
        groups_output = subprocess.check_output(['groups', username], text=True).strip()
        details['groups'] = groups_output.split(':')[1].strip().split() if ':' in groups_output else []
        
        # Últimos comandos (se disponível no history)
        history_file = f"{details['home']}/.bash_history"
        if os.path.exists(history_file) and os.access(history_file, os.R_OK):
            try:
                with open(history_file, 'r') as f:
                    lines = f.readlines()
                    details['last_commands'] = [line.strip() for line in lines[-5:] if line.strip()]
            except:
                pass
                
    except:
        pass
    
    return details

def build_monitor_frame():
    """Constrói o frame principal de monitoramento"""
    s = []
    s.append(simple_header("MONITOR DE USUÁRIOS ONLINE"))
    
    online_users = get_online_users()
    
    if not online_users:
        s.append(modern_box("STATUS DO SISTEMA", [
            f"{MC.YELLOW_GRADIENT}Nenhum usuário conectado no momento{MC.RESET}",
            "",
            f"{MC.CYAN_LIGHT}O sistema está sem conexões ativas{MC.RESET}"
        ], "", MC.YELLOW_GRADIENT, MC.YELLOW_LIGHT))
    else:
        # Estatísticas gerais
        total_users = len(online_users)
        total_connections = sum(u['total'] for u in online_users.values())
        
        stats = [
            f"{MC.CYAN_LIGHT}Usuários Online:{MC.RESET} {MC.GREEN_GRADIENT}{total_users}{MC.RESET}",
            f"{MC.CYAN_LIGHT}Total de Conexões:{MC.RESET} {MC.WHITE}{total_connections}{MC.RESET}",
            f"{MC.CYAN_LIGHT}Hora Atual:{MC.RESET} {MC.WHITE}{datetime.now().strftime('%H:%M:%S')}{MC.RESET}"
        ]
        s.append(modern_box("ESTATÍSTICAS", stats, "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
        s.append("\n")
        
        # Lista de usuários online
        users_list = []
        for i, (username, info) in enumerate(sorted(online_users.items()), 1):
            # Calcula tempo online baseado no primeiro login
            time_online = format_time_ago(info['first_login']) if info['first_login'] else "N/A"
            
            # Determina cor baseado no número de conexões
            if info['total'] > 3:
                conn_color = MC.RED_GRADIENT
            elif info['total'] > 1:
                conn_color = MC.YELLOW_GRADIENT
            else:
                conn_color = MC.GREEN_GRADIENT
            
            # Linha principal do usuário
            users_list.append(
                f"{MC.WHITE}[{i:2d}]{MC.RESET} {MC.YELLOW_GRADIENT}{username:<12}{MC.RESET} "
                f"{conn_color}{info['total']} {'conexão' if info['total'] == 1 else 'conexões'}{MC.RESET} "
                f"{MC.GRAY}online há {time_online}{MC.RESET}"
            )
            
            # Detalhes das conexões
            for conn in info['connections'][:3]:  # Mostra até 3 conexões
                ip_display = conn['ip'] if conn['ip'] != 'local' else 'Conexão Local'
                users_list.append(
                    f"    {MC.CYAN_LIGHT}└─{MC.RESET} {MC.GRAY}Terminal: {conn['terminal']} | "
                    f"IP: {ip_display}{MC.RESET}"
                )
            
            if len(info['connections']) > 3:
                users_list.append(
                    f"    {MC.CYAN_LIGHT}└─{MC.RESET} {MC.GRAY}... e mais {len(info['connections']) - 3} conexões{MC.RESET}"
                )
            
            # Processos ativos (se disponível)
            if 'processes' in info and info['processes'] > 0:
                users_list.append(
                    f"    {MC.CYAN_LIGHT}└─{MC.RESET} {MC.GRAY}Processos ativos: {info['processes']}{MC.RESET}"
                )
            
            users_list.append("")  # Linha em branco entre usuários
        
        if users_list and users_list[-1] == "":
            users_list.pop()  # Remove última linha em branco
        
        users_list.append("")
        users_list.append(f"{MC.CYAN_LIGHT}Digite o número do usuário para ver detalhes{MC.RESET}")
        users_list.append(f"{MC.YELLOW_GRADIENT}Digite 'r' para atualizar{MC.RESET}")
        users_list.append(f"{MC.RED_GRADIENT}Digite 'k' seguido do número para desconectar usuário{MC.RESET}")
        
        s.append(modern_box("USUÁRIOS CONECTADOS", users_list, "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
    
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(f"Atualizado em: {datetime.now().strftime('%H:%M:%S')}"))
    
    return "".join(s), online_users

def build_user_detail_frame(username, user_info):
    """Constrói frame com detalhes de um usuário específico"""
    s = []
    s.append(simple_header(f"DETALHES DO USUÁRIO: {username.upper()}"))
    
    details = get_user_details(username)
    
    # Informações básicas
    basic_info = [
        f"{MC.CYAN_LIGHT}Usuário:{MC.RESET} {MC.YELLOW_GRADIENT}{username}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Diretório Home:{MC.RESET} {MC.WHITE}{details['home']}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Shell:{MC.RESET} {MC.WHITE}{details['shell']}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Grupos:{MC.RESET} {MC.WHITE}{', '.join(details['groups']) if details['groups'] else 'N/A'}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Total de Conexões:{MC.RESET} {MC.GREEN_GRADIENT}{user_info['total']}{MC.RESET}"
    ]
    
    if user_info['first_login']:
        basic_info.append(
            f"{MC.CYAN_LIGHT}Tempo Online:{MC.RESET} {MC.WHITE}{format_time_ago(user_info['first_login'])}{MC.RESET}"
        )
    
    s.append(modern_box("INFORMAÇÕES DO USUÁRIO", basic_info, "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
    s.append("\n")
    
    # Conexões ativas
    connections_info = []
    for i, conn in enumerate(user_info['connections'], 1):
        login_time_str = conn['login_time'].strftime("%H:%M:%S")
        time_connected = format_time_ago(conn['login_time'])
        ip_display = conn['ip'] if conn['ip'] != 'local' else 'Conexão Local'
        
        connections_info.append(f"{MC.WHITE}Conexão #{i}:{MC.RESET}")
        connections_info.append(f"  {MC.CYAN_LIGHT}Terminal:{MC.RESET} {conn['terminal']}")
        connections_info.append(f"  {MC.CYAN_LIGHT}IP:{MC.RESET} {ip_display}")
        connections_info.append(f"  {MC.CYAN_LIGHT}Login às:{MC.RESET} {login_time_str}")
        connections_info.append(f"  {MC.CYAN_LIGHT}Conectado há:{MC.RESET} {time_connected}")
        connections_info.append("")
    
    if connections_info and connections_info[-1] == "":
        connections_info.pop()
    
    s.append(modern_box("CONEXÕES ATIVAS", connections_info, "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
    
    # Últimos comandos (se disponível)
    if details['last_commands']:
        s.append("\n")
        commands_info = []
        for cmd in details['last_commands']:
            commands_info.append(f"{MC.GRAY}$ {cmd}{MC.RESET}")
        s.append(modern_box("ÚLTIMOS COMANDOS", commands_info, "", MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    
    s.append(footer_line())
    return "".join(s)

def disconnect_user(username):
    """Desconecta todas as sessões de um usuário"""
    try:
        # Mata todos os processos do usuário
        subprocess.run(['pkill', '-u', username], check=False, capture_output=True)
        
        # Mata especificamente sessões SSH
        subprocess.run(['pkill', '-KILL', '-u', username, 'sshd'], check=False, capture_output=True)
        
        return True, f"Usuário {username} desconectado"
    except Exception as e:
        return False, f"Erro ao desconectar: {e}"

def monitor_users():
    """Função principal de monitoramento"""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este monitor precisa ser executado como root.{MC.RESET}")
        return False, "Permissão negada"
    
    TerminalManager.enter_alt_screen()
    status = ""
    auto_refresh = False
    
    try:
        while True:
            frame_content, online_users = build_monitor_frame()
            
            if status:
                frame_content = frame_content.replace(
                    footer_line(f"Atualizado em: {datetime.now().strftime('%H:%M:%S')}"),
                    footer_line(status)
                )
            
            TerminalManager.render(frame_content)
            
            if auto_refresh:
                # Modo auto-refresh - atualiza a cada 5 segundos
                time.sleep(5)
                status = f"Auto-refresh ativado (5s)"
                continue
            
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip().lower()
            TerminalManager.after_input()
            
            if choice == '0':
                break
            elif choice == 'r':
                status = "Lista atualizada"
                continue
            elif choice == 'a':
                auto_refresh = not auto_refresh
                status = "Auto-refresh " + ("ativado" if auto_refresh else "desativado")
            elif choice.startswith('k'):
                # Desconectar usuário
                try:
                    user_num = int(choice[1:])
                    users_list = sorted(online_users.keys())
                    if 1 <= user_num <= len(users_list):
                        username = users_list[user_num - 1]
                        ok, msg = disconnect_user(username)
                        status = msg
                    else:
                        status = "Número de usuário inválido"
                except ValueError:
                    status = "Use 'k' seguido do número (ex: k1)"
            elif choice.isdigit():
                # Ver detalhes do usuário
                user_num = int(choice)
                users_list = sorted(online_users.keys())
                if 1 <= user_num <= len(users_list):
                    username = users_list[user_num - 1]
                    user_info = online_users[username]
                    
                    TerminalManager.render(build_user_detail_frame(username, user_info))
                    TerminalManager.before_input()
                    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
                    TerminalManager.after_input()
                    status = f"Detalhes de {username} visualizados"
                else:
                    status = "Número de usuário inválido"
            else:
                status = "Opção inválida"
            
            time.sleep(0.3)
    
    finally:
        TerminalManager.leave_alt_screen()
    
    return True, "Monitor encerrado"

def main():
    """Função principal para teste standalone"""
    ok, msg = monitor_users()
    print(msg)

if __name__ == "__main__":
    main()
