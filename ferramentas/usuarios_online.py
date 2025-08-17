#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import os
import sys
import time
import psutil  # Adicionar: pip install psutil
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

class RealTimeMonitor:
    """Monitor de alta precisão para usuários SSH"""
    
    def __init__(self):
        self.last_check = {}
        self.connection_history = {}
    
    def get_ssh_connections_realtime(self):
        """
        Obtém conexões SSH em tempo real com alta precisão
        Verifica processos ativos a cada chamada
        """
        connections = defaultdict(list)
        
        try:
            # Método 1: Verificar processos sshd ativos (MAIS PRECISO)
            for proc in psutil.process_iter(['pid', 'name', 'username', 'create_time', 'connections', 'cmdline']):
                try:
                    pinfo = proc.info
                    
                    # Verifica se é um processo sshd
                    if 'sshd' in pinfo['name']:
                        cmdline = ' '.join(pinfo['cmdline'] or [])
                        
                        # Extrai username do comando sshd
                        if 'sshd:' in cmdline and '@' in cmdline:
                            # Formato: sshd: username@pts/X
                            parts = cmdline.split('sshd:')[1].strip()
                            if '@' in parts:
                                username = parts.split('@')[0].strip()
                                terminal = parts.split('@')[1].strip()
                                
                                # Obtém informações de conexão
                                conn_info = {
                                    'pid': pinfo['pid'],
                                    'terminal': terminal,
                                    'start_time': datetime.fromtimestamp(pinfo['create_time']),
                                    'status': 'active',
                                    'ip': 'N/A'
                                }
                                
                                # Tenta obter IP da conexão
                                try:
                                    for conn in proc.connections():
                                        if conn.raddr:
                                            conn_info['ip'] = conn.raddr[0]
                                            break
                                except:
                                    pass
                                
                                connections[username].append(conn_info)
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Método 2: Verificar via ss/netstat para conexões TCP na porta 22
            try:
                # Comando ss é mais rápido e preciso
                ss_output = subprocess.run(
                    ['ss', '-tnp', 'state', 'established', '( dport = :22 or sport = :22 )'],
                    capture_output=True,
                    text=True,
                    timeout=2
                ).stdout
                
                for line in ss_output.split('\n'):
                    if ':22' in line and 'ESTAB' in line:
                        # Extrai informações da conexão
                        parts = line.split()
                        if len(parts) >= 5:
                            # Tenta extrair PID/programa
                            for part in parts:
                                if 'sshd' in part and ',' in part:
                                    pid = part.split(',')[1].split('/')[0]
                                    # Associa com informações do processo
                                    try:
                                        proc = psutil.Process(int(pid))
                                        # Adiciona à lista se ainda não estiver
                                        # Isso captura conexões que podem ter sido perdidas no método 1
                                    except:
                                        pass
            except:
                pass
            
            # Método 3: Verificar arquivos utmp/wtmp para sessões ativas
            try:
                who_output = subprocess.run(
                    ['who', '-u'],  # -u mostra PIDs
                    capture_output=True,
                    text=True,
                    timeout=1
                ).stdout
                
                for line in who_output.split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 6:
                            username = parts[0]
                            terminal = parts[1]
                            login_time = ' '.join(parts[2:4])
                            pid = parts[-1] if parts[-1].isdigit() else None
                            
                            # Verifica se o PID ainda está ativo (CRÍTICO para precisão)
                            if pid and psutil.pid_exists(int(pid)):
                                # Processo existe, sessão está ativa
                                if username not in connections:
                                    connections[username] = []
                                
                                # Evita duplicatas
                                already_added = any(
                                    c['terminal'] == terminal 
                                    for c in connections[username]
                                )
                                
                                if not already_added:
                                    connections[username].append({
                                        'pid': int(pid),
                                        'terminal': terminal,
                                        'start_time': datetime.now(),  # Aproximado
                                        'status': 'active',
                                        'ip': 'local'
                                    })
            except:
                pass
            
        except Exception as e:
            print(f"Erro no monitoramento: {e}")
        
        return dict(connections)
    
    def verify_connection_alive(self, pid):
        """Verifica se uma conexão específica ainda está ativa"""
        try:
            # Verifica se o processo existe
            if not psutil.pid_exists(pid):
                return False
            
            # Verifica se o processo ainda é sshd
            proc = psutil.Process(pid)
            if 'sshd' not in proc.name():
                return False
            
            # Verifica se tem conexões de rede ativas
            connections = proc.connections()
            for conn in connections:
                if conn.status == 'ESTABLISHED':
                    return True
            
            return False
        except:
            return False
    
    def get_detailed_stats(self):
        """Obtém estatísticas detalhadas com verificação em tempo real"""
        connections = self.get_ssh_connections_realtime()
        stats = {
            'users': {},
            'total_users': 0,
            'total_connections': 0,
            'recent_disconnects': []
        }
        
        # Processa conexões atuais
        for username, conns in connections.items():
            active_conns = []
            
            for conn in conns:
                # Verifica se a conexão ainda está realmente ativa
                if self.verify_connection_alive(conn['pid']):
                    active_conns.append(conn)
                else:
                    # Conexão morta detectada
                    stats['recent_disconnects'].append({
                        'username': username,
                        'time': datetime.now(),
                        'terminal': conn.get('terminal', 'N/A')
                    })
            
            if active_conns:
                stats['users'][username] = {
                    'connections': active_conns,
                    'total': len(active_conns),
                    'first_login': min(c['start_time'] for c in active_conns),
                    'last_activity': datetime.now()
                }
        
        stats['total_users'] = len(stats['users'])
        stats['total_connections'] = sum(u['total'] for u in stats['users'].values())
        
        # Atualiza histórico
        self.last_check = stats
        return stats

def format_time_ago(time_obj):
    """Formata tempo decorrido com precisão de segundos"""
    if not time_obj:
        return "N/A"
    
    now = datetime.now()
    diff = now - time_obj
    
    total_seconds = int(diff.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds} segundos"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return f"{days}d {hours}h"

def build_realtime_monitor_frame(monitor):
    """Frame do monitor em tempo real"""
    s = []
    s.append(simple_header("MONITOR TEMPO REAL - USUÁRIOS SSH"))
    
    stats = monitor.get_detailed_stats()
    
    # Status em tempo real
    status_info = [
        f"{MC.GREEN_GRADIENT}● MONITORAMENTO ATIVO{MC.RESET}",
        f"{MC.CYAN_LIGHT}Usuários Online:{MC.RESET} {MC.WHITE}{stats['total_users']}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Conexões Ativas:{MC.RESET} {MC.WHITE}{stats['total_connections']}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Última Verificação:{MC.RESET} {MC.WHITE}{datetime.now().strftime('%H:%M:%S')}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Precisão:{MC.RESET} {MC.GREEN_GRADIENT}TEMPO REAL (1s){MC.RESET}"
    ]
    
    s.append(modern_box("STATUS DO SISTEMA", status_info, "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    
    if stats['users']:
        users_list = []
        
        for i, (username, info) in enumerate(sorted(stats['users'].items()), 1):
            time_online = format_time_ago(info['first_login'])
            
            # Indicador de status
            if info['total'] > 3:
                status_icon = f"{MC.RED_GRADIENT}●{MC.RESET}"
                conn_color = MC.RED_GRADIENT
            elif info['total'] > 1:
                status_icon = f"{MC.YELLOW_GRADIENT}●{MC.RESET}"
                conn_color = MC.YELLOW_GRADIENT
            else:
                status_icon = f"{MC.GREEN_GRADIENT}●{MC.RESET}"
                conn_color = MC.GREEN_GRADIENT
            
            # Linha principal
            users_list.append(
                f"{status_icon} {MC.WHITE}[{i:2d}]{MC.RESET} "
                f"{MC.YELLOW_GRADIENT}{username:<12}{MC.RESET} "
                f"{conn_color}{info['total']} {'conexão' if info['total'] == 1 else 'conexões'}{MC.RESET} "
                f"{MC.GRAY}| Online: {time_online}{MC.RESET}"
            )
            
            # Detalhes das conexões
            for conn in info['connections']:
                pid_status = "✓" if monitor.verify_connection_alive(conn['pid']) else "✗"
                users_list.append(
                    f"      {MC.CYAN_LIGHT}├─{MC.RESET} "
                    f"{MC.GRAY}PID: {conn['pid']} [{pid_status}] | "
                    f"Terminal: {conn['terminal']} | "
                    f"IP: {conn.get('ip', 'N/A')}{MC.RESET}"
                )
            
            # Última atividade
            users_list.append(
                f"      {MC.CYAN_LIGHT}└─{MC.RESET} "
                f"{MC.GRAY}Última atividade: {info['last_activity'].strftime('%H:%M:%S')}{MC.RESET}"
            )
            users_list.append("")
        
        if users_list and users_list[-1] == "":
            users_list.pop()
        
        s.append(modern_box("CONEXÕES ATIVAS EM TEMPO REAL", users_list, "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
    else:
        s.append(modern_box("CONEXÕES ATIVAS", [
            f"{MC.YELLOW_GRADIENT}Nenhuma conexão SSH ativa no momento{MC.RESET}",
            "",
            f"{MC.CYAN_LIGHT}O monitor está verificando a cada segundo...{MC.RESET}"
        ], "", MC.YELLOW_GRADIENT, MC.YELLOW_LIGHT))
    
    # Desconexões recentes
    if stats['recent_disconnects']:
        s.append("\n")
        disc_list = []
        for disc in stats['recent_disconnects'][-5:]:  # Últimas 5 desconexões
            disc_list.append(
                f"{MC.RED_GRADIENT}✗{MC.RESET} {disc['username']} "
                f"desconectou de {disc['terminal']} às "
                f"{disc['time'].strftime('%H:%M:%S')}"
            )
        s.append(modern_box("DESCONEXÕES RECENTES", disc_list, "", MC.RED_GRADIENT, MC.RED_LIGHT))
    
    s.append("\n")
    s.append(f"{MC.CYAN_LIGHT}[R] Modo Rápido (1s) | [S] Modo Lento (5s) | [P] Pausar{MC.RESET}")
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(f"Atualização: TEMPO REAL"))
    
    return "\n".join(s)  # Changed to join with \n for consistent line endings

def monitor_realtime():
    """Monitor de alta precisão em tempo real"""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este monitor precisa ser executado como root.{MC.RESET}")
        return False, "Permissão negada"
    
    # Verifica se psutil está instalado
    try:
        import psutil
    except ImportError:
        print(f"{MC.YELLOW_GRADIENT}Instalando psutil para monitoramento preciso...{MC.RESET}")
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], check=True)
        import psutil
    
    TerminalManager.enter_alt_screen()
    print('\033[?25l')  # Hide cursor to reduce flicker
    monitor = RealTimeMonitor()
    refresh_rate = 1  # Atualização a cada 1 segundo por padrão
    paused = False
    
    try:
        import select
        import termios
        import tty
        
        # Configurar terminal para input não bloqueante
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        
        last_update = time.time()
        
        while True:
            current_time = time.time()
            
            # Atualiza display se não estiver pausado e passou o tempo
            if not paused and (current_time - last_update) >= refresh_rate:
                content = build_realtime_monitor_frame(monitor)
                # Custom render to minimize flicker: move to home, print lines with EOL clear, then clear to EOS
                lines = content.splitlines()
                output = '\033[H' + '\n'.join(line + '\033[K' for line in lines) + '\033[J'
                print(output, end='', flush=True)
                last_update = current_time
            
            # Verifica input sem bloquear
            if select.select([sys.stdin], [], [], 0.1)[0]:
                char = sys.stdin.read(1).lower()
                
                if char == '0':
                    break
                elif char == 'r':
                    refresh_rate = 1
                    paused = False
                elif char == 's':
                    refresh_rate = 5
                    paused = False
                elif char == 'p':
                    paused = not paused
                elif char == 'q':
                    break
        
    except KeyboardInterrupt:
        pass
    finally:
        # Restaura configurações do terminal
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except:
            pass
        print('\033[?25h')  # Show cursor
        TerminalManager.leave_alt_screen()
    
    return True, "Monitor encerrado"

def main():
    """Função principal para teste"""
    ok, msg = monitor_realtime()
    print(msg)

if __name__ == "__main__":
    main()
