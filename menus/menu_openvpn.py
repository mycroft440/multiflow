#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import re
import threading
import http.server
import socketserver
from pathlib import Path
from shutil import copyfile
from datetime import datetime, timedelta

# Ajuste do path para importar utilitários visuais
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# ---------------------- Variáveis Globais para Download ----------------------

DOWNLOAD_SERVER = None
DOWNLOAD_THREAD = None
DOWNLOAD_FILE_PATH = None
DOWNLOAD_START_TIME = None
DOWNLOAD_PORT = 7777
DOWNLOAD_DURATION = 600  # 10 minutos em segundos

# ---------------------- Utilidades de execução ----------------------

def run_cmd(cmd, timeout=8):
    """Executa comando com timeout e tratamento de erro"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def ensure_root():
    """Verifica se está rodando como root"""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este menu precisa ser executado como root.{MC.RESET}")
        input("Pressione Enter para sair...")
        sys.exit(1)

def get_public_ip():
    """Obtém o IP público da VPS"""
    ip_result = run_cmd(['curl', '-4', '-s', 'https://api.ipify.org'], timeout=5)
    if ip_result.returncode == 0 and ip_result.stdout.strip():
        return ip_result.stdout.strip()
    
    # Fallback para outros serviços
    for url in ['https://ifconfig.me', 'https://ipinfo.io/ip']:
        ip_result = run_cmd(['curl', '-4', '-s', url], timeout=5)
        if ip_result.returncode == 0 and ip_result.stdout.strip():
            return ip_result.stdout.strip()
    
    # Último fallback - IP local
    ip_result = run_cmd(['hostname', '-I'])
    if ip_result.returncode == 0 and ip_result.stdout.strip():
        return ip_result.stdout.split()[0]
    
    return "IP_NAO_DETECTADO"

# ---------------------- Servidor HTTP Temporário ----------------------

class SingleFileHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Handler customizado para servir apenas um arquivo específico"""
    
    def do_GET(self):
        """Serve apenas o arquivo OVPN"""
        global DOWNLOAD_FILE_PATH
        
        if not DOWNLOAD_FILE_PATH or not os.path.exists(DOWNLOAD_FILE_PATH):
            self.send_error(404, "Arquivo não encontrado")
            return
            
        if self.path == '/' or self.path == f'/{os.path.basename(DOWNLOAD_FILE_PATH)}':
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-openvpn-profile')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(DOWNLOAD_FILE_PATH)}"')
                self.send_header('Content-Length', str(os.path.getsize(DOWNLOAD_FILE_PATH)))
                self.end_headers()
                
                with open(DOWNLOAD_FILE_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            except Exception:
                self.send_error(500, "Erro interno do servidor")
        else:
            self.send_error(404, "Arquivo não encontrado")
    
    def log_message(self, format, *args):
        """Suprime logs do servidor HTTP"""
        pass

def start_download_server(file_path):
    """Inicia o servidor HTTP temporário"""
    global DOWNLOAD_SERVER, DOWNLOAD_THREAD, DOWNLOAD_FILE_PATH, DOWNLOAD_START_TIME
    
    # Para servidor anterior se existir
    stop_download_server()
    
    DOWNLOAD_FILE_PATH = file_path
    DOWNLOAD_START_TIME = datetime.now()
    
    def run_server():
        global DOWNLOAD_SERVER
        try:
            # Configura o servidor
            handler = SingleFileHTTPHandler
            DOWNLOAD_SERVER = socketserver.TCPServer(("0.0.0.0", DOWNLOAD_PORT), handler)
            DOWNLOAD_SERVER.allow_reuse_address = True
            
            # Timeout de 10 minutos
            end_time = time.time() + DOWNLOAD_DURATION
            DOWNLOAD_SERVER.timeout = 1  # Check every second
            
            while time.time() < end_time:
                DOWNLOAD_SERVER.handle_request()
            
            # Limpa após timeout
            stop_download_server()
        except Exception:
            pass
    
    # Inicia thread do servidor
    DOWNLOAD_THREAD = threading.Thread(target=run_server, daemon=True)
    DOWNLOAD_THREAD.start()
    
    # Aguarda servidor iniciar
    time.sleep(0.5)
    
    # Verifica se porta está aberta e abre no firewall se necessário
    check_port = run_cmd(['lsof', '-i', f':{DOWNLOAD_PORT}'], timeout=2)
    if check_port.returncode != 0:
        # Tenta abrir porta no firewall
        run_cmd(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(DOWNLOAD_PORT), '-j', 'ACCEPT'])
        if os.path.exists("/etc/iptables/rules.v4"):
            save_result = run_cmd(['iptables-save'], timeout=5)
            if save_result.returncode == 0:
                try:
                    with open("/etc/iptables/rules.v4", "w") as f:
                        f.write(save_result.stdout)
                except Exception:
                    pass

def stop_download_server():
    """Para o servidor HTTP temporário"""
    global DOWNLOAD_SERVER, DOWNLOAD_THREAD, DOWNLOAD_FILE_PATH, DOWNLOAD_START_TIME
    
    if DOWNLOAD_SERVER:
        try:
            DOWNLOAD_SERVER.shutdown()
            DOWNLOAD_SERVER.server_close()
        except Exception:
            pass
        DOWNLOAD_SERVER = None
    
    if DOWNLOAD_THREAD and DOWNLOAD_THREAD.is_alive():
        DOWNLOAD_THREAD.join(timeout=2)
    
    DOWNLOAD_THREAD = None
    DOWNLOAD_FILE_PATH = None
    DOWNLOAD_START_TIME = None

def is_download_server_active():
    """Verifica se o servidor de download está ativo e dentro do tempo"""
    global DOWNLOAD_START_TIME, DOWNLOAD_FILE_PATH
    
    if not DOWNLOAD_START_TIME or not DOWNLOAD_FILE_PATH:
        return False
    
    elapsed = (datetime.now() - DOWNLOAD_START_TIME).total_seconds()
    return elapsed < DOWNLOAD_DURATION and os.path.exists(DOWNLOAD_FILE_PATH)

def get_remaining_download_time():
    """Retorna o tempo restante do link de download em minutos"""
    global DOWNLOAD_START_TIME
    
    if not DOWNLOAD_START_TIME:
        return 0
    
    elapsed = (datetime.now() - DOWNLOAD_START_TIME).total_seconds()
    remaining = DOWNLOAD_DURATION - elapsed
    return max(0, int(remaining / 60))

# ---------------------- Detecção de layout e estado ----------------------

def find_server_conf():
    """Encontra o arquivo de configuração do servidor"""
    candidates = [
        "/etc/openvpn/server/server.conf",  # layout moderno
        "/etc/openvpn/server.conf",         # layout legado
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def detect_service_candidates():
    """Detecta possíveis nomes de serviço do OpenVPN"""
    base_candidates = [
        "openvpn-server@server",
        "openvpn@server",
        "openvpn",
        "openvpn@server.service",
        "openvpn-server@server.service",
    ]
    result = run_cmd(['systemctl', 'list-unit-files'])
    present = []
    if result.returncode == 0:
        listing = result.stdout
        for name in base_candidates:
            base = name.replace(".service", "")
            if base + ".service" in listing or name in listing:
                present.append(base)
    # ordenar e remover duplicatas
    seen = set()
    ordered = []
    for name in present + [c.replace(".service", "") for c in base_candidates]:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered

def pick_server_unit():
    """Escolhe a unidade de serviço apropriada"""
    units = detect_service_candidates()
    return units[0] if units else None

def verificar_openvpn_instalado():
    """Verifica se OpenVPN está instalado"""
    # binário
    r = run_cmd(['which', 'openvpn'])
    if not (r.returncode == 0 and r.stdout.strip()):
        return False
    # config
    if find_server_conf():
        return True
    # unidades
    if detect_service_candidates():
        return True
    return False

def parse_port_proto_dns(conf_path):
    """Extrai porta, protocolo e DNS da configuração"""
    port = "1194"
    proto = "udp"
    dns_list = []
    try:
        with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ls = line.strip()
                if not ls or ls.startswith("#"):
                    continue
                low = ls.lower()
                if low.startswith("port "):
                    parts = ls.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        port = parts[1]
                elif low.startswith("proto "):
                    parts = ls.split()
                    if len(parts) >= 2:
                        proto = parts[1].lower()
                elif low.startswith('push "') and "dhcp-option" in low and " dns " in low:
                    # Ex.: push "dhcp-option DNS 1.1.1.1"
                    m = re.search(r'DNS\s+([0-9]{1,3}(?:\.[0-9]{1,3}){3})', ls, re.I)
                    if m:
                        dns_list.append(m.group(1))
    except Exception:
        pass
    
    # label do DNS
    dns_label = "custom"
    set_dns = set(dns_list)
    if set_dns == {"8.8.8.8", "8.8.4.4"}:
        dns_label = "google"
    elif set_dns == {"1.1.1.1", "1.0.0.1"}:
        dns_label = "cloudflare"
    elif set_dns == {"9.9.9.9", "149.112.112.112"}:
        dns_label = "quad9"
    elif set_dns == {"208.67.222.222", "208.67.220.220"}:
        dns_label = "opendns"
    elif not dns_list:
        dns_label = "desconhecido"
    
    return port, proto, dns_label, dns_list

# ---------------------- Geração de arquivo OVPN ----------------------

def criar_arquivo_ovpn(client_name):
    """Cria um arquivo OVPN para o cliente especificado"""
    
    # Verifica se OpenVPN está instalado
    if not verificar_openvpn_instalado():
        return None, "OpenVPN não está instalado"
    
    # Encontra configuração do servidor
    server_conf = find_server_conf()
    if not server_conf:
        return None, "Configuração do servidor não encontrada"
    
    # Extrai informações do servidor
    port, proto, _, _ = parse_port_proto_dns(server_conf)
    server_ip = get_public_ip()
    
    # Diretórios de certificados
    conf_dir = os.path.dirname(server_conf)
    easy_rsa_dir = "/etc/openvpn/easy-rsa"
    
    # Verifica se easy-rsa existe
    if not os.path.exists(easy_rsa_dir):
        return None, "Easy-RSA não encontrado"
    
    # Verifica se cliente já existe
    client_cert = f"{easy_rsa_dir}/pki/issued/{client_name}.crt"
    if not os.path.exists(client_cert):
        # Precisa criar o certificado do cliente
        try:
            os.chdir(easy_rsa_dir)
            create_result = run_cmd(['bash', '-c', f'echo "yes" | ./easyrsa build-client-full "{client_name}" nopass'], timeout=30)
            if create_result.returncode != 0:
                return None, f"Erro ao criar certificado do cliente"
        except Exception as e:
            return None, f"Erro ao criar certificado: {str(e)}"
    
    # Cria diretório para clientes
    client_dir = os.path.expanduser("~/ovpn-clients")
    os.makedirs(client_dir, exist_ok=True)
    
    # Caminho do arquivo OVPN
    ovpn_file = os.path.join(client_dir, f"{client_name}.ovpn")
    
    # Lê certificados necessários
    try:
        with open(f"{conf_dir}/ca.crt", 'r') as f:
            ca_cert = f.read()
        
        with open(f"{easy_rsa_dir}/pki/issued/{client_name}.crt", 'r') as f:
            client_cert_content = f.read()
        
        with open(f"{easy_rsa_dir}/pki/private/{client_name}.key", 'r') as f:
            client_key = f.read()
        
        # Verifica se existe tls-crypt ou tls-auth
        tls_key = ""
        tls_directive = ""
        if os.path.exists(f"{conf_dir}/tc.key"):
            with open(f"{conf_dir}/tc.key", 'r') as f:
                tls_key = f.read()
            tls_directive = "<tls-crypt>\n" + tls_key + "</tls-crypt>"
        elif os.path.exists(f"{conf_dir}/ta.key"):
            with open(f"{conf_dir}/ta.key", 'r') as f:
                tls_key = f.read()
            tls_directive = "<tls-auth>\n" + tls_key + "</tls-auth>\nkey-direction 1"
        
        # Gera arquivo OVPN
        ovpn_content = f"""# OpenVPN Client Configuration
client
dev tun
proto {proto}
remote {server_ip} {port}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
cipher AES-256-GCM
verb 3
mute 20
tun-mtu 1500
mssfix 1420
sndbuf 0
rcvbuf 0

# Segurança adicional
tls-version-min 1.2

# Certificados embutidos
<ca>
{ca_cert}
</ca>
<cert>
{client_cert_content}
</cert>
<key>
{client_key}
</key>
{tls_directive}
"""
        
        # Escreve arquivo
        with open(ovpn_file, 'w') as f:
            f.write(ovpn_content)
        
        return ovpn_file, None
        
    except Exception as e:
        return None, f"Erro ao criar arquivo OVPN: {str(e)}"

# ---------------------- Helpers de edição de config ----------------------

def backup_file(path):
    """Cria backup do arquivo"""
    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        copyfile(path, f"{path}.bak-{ts}")
        return True
    except Exception:
        return False

def write_file(path, content):
    """Escreve conteúdo no arquivo"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def read_file(path):
    """Lê conteúdo do arquivo"""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def set_conf_port(conf_path, new_port):
    """Altera a porta na configuração"""
    text = read_file(conf_path)
    if re.search(r'^\s*port\s+\d+', text, re.M):
        text = re.sub(r'^\s*port\s+\d+', f"port {new_port}", text, flags=re.M)
    else:
        text = f"port {new_port}\n{text}"
    write_file(conf_path, text)

def set_conf_proto(conf_path, new_proto):
    """Altera o protocolo na configuração"""
    text = read_file(conf_path)
    if re.search(r'^\s*proto\s+\S+', text, re.M):
        text = re.sub(r'^\s*proto\s+\S+', f"proto {new_proto}", text, flags=re.M)
    else:
        text = f"proto {new_proto}\n{text}"
    write_file(conf_path, text)

def set_conf_dns(conf_path, dns_list):
    """Altera os servidores DNS na configuração"""
    text = read_file(conf_path)
    text = re.sub(r'^\s*push\s+"dhcp-option\s+DNS\s+[0-9\.]+"\s*\n', "", text, flags=re.M|re.I)
    insert = ""
    for ip in dns_list:
        insert += f'push "dhcp-option DNS {ip}"\n'
    if re.search(r'^\s*push\s+"redirect-gateway\b.*"\s*$', text, flags=re.M):
        text = re.sub(r'(^\s*push\s+"redirect-gateway\b.*"\s*$)', r'\1' + f"\n{insert}".rstrip("\n"), text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + insert
    write_file(conf_path, text)

def update_clients_configs(new_port=None, new_proto=None):
    """Atualiza configurações dos clientes existentes"""
    dirs = [str(Path("/root/ovpn-clients")), "/root"]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.endswith(".ovpn"):
                continue
            path = os.path.join(d, name)
            try:
                content = read_file(path)
                if new_proto:
                    if re.search(r'^\s*proto\s+\S+', content, re.M):
                        content = re.sub(r'^\s*proto\s+\S+', f"proto {new_proto}", content, flags=re.M)
                if new_port:
                    content = re.sub(r'^(remote\s+\S+\s+)\d+(\b.*)$', rf'\g<1>{new_port}\2', content, flags=re.M)
                write_file(path, content)
            except Exception:
                pass

# ---------------------- Firewall helpers ----------------------

def update_firewall_port(old_port, new_port):
    """Atualiza porta no firewall"""
    # iptables
    run_cmd(['iptables', '-D', 'INPUT', '-p', 'udp', '--dport', str(old_port), '-j', 'ACCEPT'])
    run_cmd(['iptables', '-D', 'INPUT', '-p', 'tcp', '--dport', str(old_port), '-j', 'ACCEPT'])
    
    check_udp = run_cmd(['iptables', '-C', 'INPUT', '-p', 'udp', '--dport', str(new_port), '-j', 'ACCEPT'])
    if check_udp.returncode != 0:
        run_cmd(['iptables', '-A', 'INPUT', '-p', 'udp', '--dport', str(new_port), '-j', 'ACCEPT'])
    
    check_tcp = run_cmd(['iptables', '-C', 'INPUT', '-p', 'tcp', '--dport', str(new_port), '-j', 'ACCEPT'])
    if check_tcp.returncode != 0:
        run_cmd(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(new_port), '-j', 'ACCEPT'])
    
    if os.path.exists("/etc/iptables/rules.v4"):
        save_result = run_cmd(['iptables-save'], timeout=10)
        if save_result.returncode == 0:
            try:
                with open("/etc/iptables/rules.v4", "w") as f:
                    f.write(save_result.stdout)
            except Exception:
                pass

# ---------------------- Controle do serviço ----------------------

def restart_openvpn():
    """Reinicia o serviço OpenVPN"""
    unit = pick_server_unit()
    if not unit:
        return False, "Serviço OpenVPN não encontrado"
    
    run_cmd(['systemctl', 'daemon-reload'])
    res = run_cmd(['systemctl', 'restart', unit], timeout=20)
    if res.returncode != 0:
        return False, res.stderr.strip() or "Falha ao reiniciar serviço"
    
    time.sleep(1.5)
    st = run_cmd(['systemctl', 'is-active', unit])
    if st.stdout.strip() == "active":
        return True, "Serviço reiniciado"
    
    log = run_cmd(['journalctl', '-xeu', unit, '--no-pager', '-n', '30'], timeout=10).stdout
    return False, f"Falha ao iniciar. Logs:\n{log}"

# ---------------------- Integração com openvpn.sh ----------------------

def descobrir_script_openvpn():
    """Descobre o caminho do script bash de instalação"""
    env_path = os.environ.get("OVPN_SCRIPT_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root_dir, "conexoes", "openvpn.sh"),
        os.path.join(root_dir, "conexoes", "openvpn-manager.sh"),
        "/opt/multiflow/conexoes/openvpn.sh",
        "/opt/multiflow/conexoes/openvpn-manager.sh",
        "/etc/openvpn/openvpn-manager.sh",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def executar_script_openvpn():
    """Executa o script bash de instalação"""
    script_path = descobrir_script_openvpn()
    if not script_path:
        return False, "Script openvpn.sh não encontrado."
    try:
        TerminalManager.render(build_operation_frame("Executando openvpn.sh", "", MC.GREEN_GRADIENT, "Inicializando..."))
        TerminalManager.leave_alt_screen()
        subprocess.run(['chmod', '+x', script_path], check=False)
        result = subprocess.run(['bash', script_path], check=False)
        TerminalManager.enter_alt_screen()
        return result.returncode == 0, ("Concluído" if result.returncode == 0 else "Falhou")
    except Exception as e:
        TerminalManager.enter_alt_screen()
        return False, str(e)

# ---------------------- Ações do menu ----------------------

def is_valid_port(p):
    """Valida se é uma porta válida"""
    try:
        n = int(p)
        return 1 <= n <= 65535
    except Exception:
        return False

ipv4_re = re.compile(r'^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$')

def alterar_porta():
    """Altera a porta do OpenVPN"""
    conf = find_server_conf()
    if not conf:
        return False, "OpenVPN não instalado/configurado."
    
    port, proto, _, _ = parse_port_proto_dns(conf)

    TerminalManager.before_input()
    new_port = input(f"\n{MC.BOLD}Nova porta (atual {port}): {MC.RESET}").strip()
    TerminalManager.after_input()
    
    if not is_valid_port(new_port):
        return False, "Porta inválida."

    try:
        backup_file(conf)
        set_conf_port(conf, new_port)
        try:
            update_firewall_port(port, new_port)
        except Exception:
            pass
        update_clients_configs(new_port=new_port, new_proto=None)
        ok, msg = restart_openvpn()
        return ok, f"Porta alterada para {new_port}. {msg}"
    except Exception as e:
        return False, f"Erro ao alterar porta: {e}"

def alterar_protocolo():
    """Altera o protocolo do OpenVPN"""
    conf = find_server_conf()
    if not conf:
        return False, "OpenVPN não instalado/configurado."
    
    port, proto, _, _ = parse_port_proto_dns(conf)
    current = proto.upper()

    print(f"\n{MC.WHITE}Protocolo atual: {MC.CYAN}{current}{MC.RESET}")
    print(f"{MC.WHITE}Escolha:{MC.RESET}")
    print("  1) TCP")
    print("  2) UDP")
    TerminalManager.before_input()
    choice = input(f"{MC.BOLD}Opção: {MC.RESET}").strip()
    TerminalManager.after_input()

    new_proto = "tcp" if choice == "1" else "udp" if choice == "2" else None
    if not new_proto:
        return False, "Operação cancelada."

    try:
        backup_file(conf)
        set_conf_proto(conf, new_proto)
        update_clients_configs(new_port=None, new_proto=new_proto)
        ok, msg = restart_openvpn()
        return ok, f"Protocolo alterado para {new_proto.upper()}. {msg}"
    except Exception as e:
        return False, f"Erro ao alterar protocolo: {e}"

def alterar_dns():
    """Altera os servidores DNS do OpenVPN"""
    conf = find_server_conf()
    if not conf:
        return False, "OpenVPN não instalado/configurado."
    
    _, _, dns_label, dns_list = parse_port_proto_dns(conf)

    print(f"\n{MC.WHITE}DNS atual: {MC.CYAN}{dns_label} {('(' + ', '.join(dns_list) + ')') if dns_list else ''}{MC.RESET}")
    print(f"{MC.WHITE}Escolha o DNS:{MC.RESET}")
    print("  1) Google (8.8.8.8, 8.8.4.4)")
    print("  2) Cloudflare (1.1.1.1, 1.0.0.1)")
    print("  3) Quad9 (9.9.9.9, 149.112.112.112)")
    print("  4) OpenDNS (208.67.222.222, 208.67.220.220)")
    print("  5) Personalizado")
    TerminalManager.before_input()
    choice = input(f"{MC.BOLD}Opção: {MC.RESET}").strip()
    TerminalManager.after_input()

    if choice == "1":
        dns = ["8.8.8.8", "8.8.4.4"]
    elif choice == "2":
        dns = ["1.1.1.1", "1.0.0.1"]
    elif choice == "3":
        dns = ["9.9.9.9", "149.112.112.112"]
    elif choice == "4":
        dns = ["208.67.222.222", "208.67.220.220"]
    elif choice == "5":
        TerminalManager.before_input()
        custom = input(f"{MC.BOLD}Informe um ou dois DNS (separados por espaço): {MC.RESET}").strip()
        TerminalManager.after_input()
        parts = [p for p in custom.split() if ipv4_re.match(p)]
        if not parts:
            return False, "DNS inválido."
        dns = parts[:2]
    else:
        return False, "Operação cancelada."

    try:
        backup_file(conf)
        set_conf_dns(conf, dns)
        ok, msg = restart_openvpn()
        return ok, f"DNS alterado para {', '.join(dns)}. {msg}"
    except Exception as e:
        return False, f"Erro ao alterar DNS: {e}"

def gerar_download_ovpn():
    """Gera arquivo OVPN e cria link de download temporário"""
    global DOWNLOAD_FILE_PATH
    
    if not verificar_openvpn_instalado():
        return False, "OpenVPN não está instalado"
    
    # Verifica se já existe um servidor ativo
    if is_download_server_active():
        ip = get_public_ip()
        remaining = get_remaining_download_time()
        file_name = os.path.basename(DOWNLOAD_FILE_PATH)
        
        print(f"\n{MC.YELLOW}Link de download ainda ativo!{MC.RESET}")
        print(f"{MC.WHITE}Tempo restante: {MC.CYAN}{remaining} minutos{MC.RESET}")
        print(f"\n{MC.WHITE}Baixe o {MC.GREEN}{file_name}{MC.WHITE} no link a seguir:{MC.RESET}")
        print(f"\n{MC.WHITE}Copie o link e coloque no navegador:{MC.RESET}")
        print(f"{MC.CYAN}http://{ip}:{DOWNLOAD_PORT}{MC.RESET}")
        print()
        
        TerminalManager.before_input()
        input(f"{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
        TerminalManager.after_input()
        return True, "Link exibido"
    
    # Solicita nome do cliente
    print(f"\n{MC.WHITE}Qual nome deseja utilizar para o ovpn? [ex: mycroft]{MC.RESET}")
    TerminalManager.before_input()
    client_name = input(f"{MC.BOLD}Digite: {MC.RESET}").strip()
    TerminalManager.after_input()
    
    if not client_name:
        return False, "Nome inválido"
    
    # Sanitiza nome
    client_name = re.sub(r'[^a-zA-Z0-9_-]', '', client_name)
    if not client_name:
        return False, "Nome inválido após sanitização"
    
    # Cria arquivo OVPN
    print(f"\n{MC.YELLOW}Gerando arquivo {client_name}.ovpn...{MC.RESET}")
    ovpn_file, error = criar_arquivo_ovpn(client_name)
    
    if error:
        return False, error
    
    # Inicia servidor de download
    print(f"{MC.YELLOW}Iniciando servidor de download...{MC.RESET}")
    start_download_server(ovpn_file)
    
    # Aguarda servidor iniciar
    time.sleep(1)
    
    # Exibe link
    ip = get_public_ip()
    print(f"\n{MC.GREEN}Arquivo gerado com sucesso!{MC.RESET}")
    print(f"\n{MC.WHITE}Baixe o {MC.GREEN}{client_name}.ovpn{MC.WHITE} no link a seguir, esse link irá funcionar por apenas {MC.YELLOW}10 minutos{MC.WHITE}, após esse tempo será excluído e você terá que gerar um novo link:{MC.RESET}")
    print(f"\n{MC.WHITE}Copie o link e coloque no navegador:{MC.RESET}")
    print(f"{MC.CYAN}http://{ip}:{DOWNLOAD_PORT}{MC.RESET}")
    print()
    
    TerminalManager.before_input()
    input(f"{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
    TerminalManager.after_input()
    
    return True, f"Link criado para {client_name}.ovpn"

def desinstalar_openvpn():
    """Desinstala o OpenVPN"""
    script_path = descobrir_script_openvpn()
    if script_path:
        return executar_script_openvpn()

    print(f"\n{MC.RED_GRADIENT}ATENÇÃO: Isso removerá OpenVPN e easy-rsa.{MC.RESET}")
    TerminalManager.before_input()
    c = input(f"{MC.BOLD}Confirmar? [s/N]: {MC.RESET}").strip().lower()
    TerminalManager.after_input()
    if c != "s":
        return False, "Operação cancelada."
    
    os_release = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_release[k] = v.strip('"')
    except Exception:
        pass
    
    id_like = (os_release.get("ID_LIKE", "") + " " + os_release.get("ID", "")).lower()
    if any(x in id_like for x in ["debian", "ubuntu"]):
        run_cmd(['systemctl', 'stop', pick_server_unit() or 'openvpn@server'])
        r = run_cmd(['apt-get', 'remove', '--purge', '-y', 'openvpn', 'easy-rsa'], timeout=120)
        run_cmd(['apt-get', 'autoremove', '-y'], timeout=120)
        ok = r.returncode == 0
    else:
        run_cmd(['systemctl', 'stop', pick_server_unit() or 'openvpn@server'])
        r = run_cmd(['yum', 'remove', '-y', 'openvpn', 'easy-rsa'], timeout=120)
        ok = r.returncode == 0
    
    return ok, ("Desinstalado" if ok else "Falha ao desinstalar")

# ---------------------- UI ----------------------

def build_status_box():
    """Constrói a caixa de status"""
    installed = verificar_openvpn_instalado()
    status_str = "Openvpn instalado" if installed else "Openvpn não instalado"
    porta = "—"
    protocolo = "—"
    dns_label = "—"
    
    if installed:
        conf = find_server_conf()
        if conf:
            port, proto, dns_lab, _ = parse_port_proto_dns(conf)
            porta = port
            protocolo = proto.upper()
            dns_label = dns_lab
            dns_label = {"google": "google", "cloudflare": "cloudflare"}.get(dns_label, dns_label)
    
    lines = [
        f"{MC.CYAN_LIGHT}Status:{MC.RESET} {MC.WHITE}{status_str}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Porta:{MC.RESET} {MC.WHITE}{porta}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Protocolo:{MC.RESET} {MC.WHITE}{protocolo}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Dns:{MC.RESET} {MC.WHITE}{dns_label}{MC.RESET}",
    ]
    
    # Adiciona status do servidor de download se ativo
    if is_download_server_active():
        remaining = get_remaining_download_time()
        lines.append(f"{MC.CYAN_LIGHT}Download:{MC.RESET} {MC.GREEN}Ativo ({remaining} min restantes){MC.RESET}")
    
    return modern_box("STATUS", lines, "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

def build_menu_frame(status_msg=""):
    """Constrói o frame do menu principal"""
    s = []
    s.append(simple_header("GERENCIADOR OPENVPN"))
    s.append(build_status_box())
    s.append("\n")
    s.append(menu_option("1", "Instalar openvpn", "", MC.GREEN_GRADIENT))
    s.append(menu_option("2", "Alterar porta", "", MC.CYAN_GRADIENT))
    s.append(menu_option("3", "Alterar protocolo", "", MC.BLUE_GRADIENT))
    s.append(menu_option("4", "Alterar Dns", "", MC.ORANGE_GRADIENT))
    s.append(menu_option("5", "Gerar e baixar arquivo ovpn", "", MC.MAGENTA_GRADIENT))  # Corrigido aqui
    s.append(menu_option("6", "Desinstalar Openvpn", "", MC.RED_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_operation_frame(title, icon, color, msg="Aguarde..."):
    """Constrói frame de operação em andamento"""
    s = []
    s.append(simple_header("OPERAÇÃO EM ANDAMENTO"))
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}{msg}{MC.RESET}"
    ], "", color, MC.CYAN_LIGHT))
    s.append(footer_line("Processando..."))
    return "".join(s)

# ---------------------- Loop principal ----------------------

def main_menu():
    """Menu principal do gerenciador OpenVPN"""
    ensure_root()
    TerminalManager.enter_alt_screen()
    status_msg = ""
    
    try:
        while True:
            TerminalManager.render(build_menu_frame(status_msg))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()

            if choice == "1":
                ok, msg = executar_script_openvpn()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "2":
                TerminalManager.render(build_operation_frame("Alterar porta", "", MC.CYAN_GRADIENT, "Aplicando alterações..."))
                ok, msg = alterar_porta()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "3":
                TerminalManager.render(build_operation_frame("Alterar protocolo", "", MC.BLUE_GRADIENT, "Aplicando alterações..."))
                ok, msg = alterar_protocolo()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "4":
                TerminalManager.render(build_operation_frame("Alterar DNS", "", MC.ORANGE_GRADIENT, "Aplicando alterações..."))
                ok, msg = alterar_dns()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "5":
                TerminalManager.render(build_operation_frame("Gerar arquivo OVPN", "", MC.MAGENTA_GRADIENT, "Criando arquivo e link..."))  # Corrigido aqui
                ok, msg = gerar_download_ovpn()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "6":
                TerminalManager.render(build_operation_frame("Desinstalar OpenVPN", "", MC.RED_GRADIENT, "Removendo..."))
                ok, msg = desinstalar_openvpn()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "0":
                # Para servidor de download ao sair
                stop_download_server()
                break
            else:
                status_msg = "Opção inválida"

            time.sleep(0.7)
    finally:
        # Garante que servidor de download seja parado
        stop_download_server()
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main_menu()
