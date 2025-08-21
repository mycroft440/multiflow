#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# NOTE: This file is adapted from the original `menu_openvpn.py` in the
# mycroft440/multiflow repository.  It provides a textual interface
# for managing an OpenVPN server, integrating with a shell script
# (`openvpn.sh`) when present.  It has been updated to work with
# the modified `openvpn.sh` which no longer offers its own menu and
# performs installation automatically with preset values.

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
from datetime import datetime

# Ajuste o path para importar utilitários visuais
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Paleta de cores e componentes de UI reutilizados
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# --------------------------------------------------------------------
# Variáveis globais e configurações
# --------------------------------------------------------------------
DOWNLOAD_SERVER = None          # Instância do servidor TCP
DOWNLOAD_THREAD = None          # Thread que roda o servidor
DOWNLOAD_FILE_PATH = None       # Caminho do arquivo .ovpn a ser servido
DOWNLOAD_START_TIME = None      # Data/hora de início do servidor de download
DOWNLOAD_PORT = 7777            # Porta onde o HTTP de download ficará ativo
DOWNLOAD_DURATION = 600         # Duração em segundos (10 minutos)

# --------------------------------------------------------------------
# Funções utilitárias
# --------------------------------------------------------------------
def run_cmd(cmd, timeout=8):
    """Executa um comando no sistema com timeout e captura de saída.

    Retorna um objeto CompletedProcess sempre, mesmo em caso de exceção ou
    timeout. Esse wrapper evita levantar exceções e facilita o tratamento.
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def ensure_root():
    """Encerra o programa se não estiver rodando como root."""
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este menu precisa ser executado como root.{MC.RESET}")
        input("Pressione Enter para sair...")
        sys.exit(1)

def get_public_ip():
    """Tenta determinar o IP público da VPS consultando serviços externos.

    Usa curl via run_cmd. Se os serviços externos falharem, retorna o IP
    local retornado por `hostname -I`. Caso não seja possível descobrir,
    retorna uma string indicando falha.
    """
    # Serviço principal
    ip_result = run_cmd(['curl', '-4', '-s', 'https://api.ipify.org'], timeout=5)
    if ip_result.returncode == 0 and ip_result.stdout.strip():
        return ip_result.stdout.strip()
    # Fallbacks
    for url in ['https://ifconfig.me', 'https://ipinfo.io/ip']:
        ip_result = run_cmd(['curl', '-4', '-s', url], timeout=5)
        if ip_result.returncode == 0 and ip_result.stdout.strip():
            return ip_result.stdout.strip()
    # Última alternativa: IP local
    ip_result = run_cmd(['hostname', '-I'])
    if ip_result.returncode == 0 and ip_result.stdout.strip():
        return ip_result.stdout.split()[0]
    return "IP_NAO_DETECTADO"

# --------------------------------------------------------------------
# Servidor HTTP temporário para servir arquivos .ovpn
# --------------------------------------------------------------------
class SingleFileHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Handler para servir somente um arquivo específico (.ovpn)."""

    def do_GET(self):
        """Retorna o arquivo OVPN se a rota corresponder."""
        global DOWNLOAD_FILE_PATH
        if not DOWNLOAD_FILE_PATH or not os.path.exists(DOWNLOAD_FILE_PATH):
            self.send_error(404, "Arquivo não encontrado")
            return
        # Permite acesso pela raiz '/' ou nome do arquivo
        if self.path in ('/', f'/{os.path.basename(DOWNLOAD_FILE_PATH)}'):
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
        """Suprime mensagens de log padrão do HTTP para limpar a saída."""
        pass

class ReusableTCPServer(socketserver.TCPServer):
    """TCPServer que permite reuso de porta antes do bind."""
    allow_reuse_address = True

def start_download_server(file_path):
    """Inicia o servidor HTTP em background para servir o arquivo fornecido.

    Cria uma thread que escuta na porta DOWNLOAD_PORT por DOWNLOAD_DURATION
    segundos. Configura regra de firewall apenas se ainda não existir.
    """
    global DOWNLOAD_SERVER, DOWNLOAD_THREAD, DOWNLOAD_FILE_PATH, DOWNLOAD_START_TIME
    # Encerra qualquer servidor em execução
    stop_download_server()
    DOWNLOAD_FILE_PATH = file_path
    DOWNLOAD_START_TIME = datetime.now()
    def run_server():
        global DOWNLOAD_SERVER
        try:
            handler = SingleFileHTTPHandler
            DOWNLOAD_SERVER = ReusableTCPServer(("0.0.0.0", DOWNLOAD_PORT), handler)
            end_time = time.time() + DOWNLOAD_DURATION
            DOWNLOAD_SERVER.timeout = 1
            while time.time() < end_time:
                DOWNLOAD_SERVER.handle_request()
            stop_download_server()
        except Exception:
            pass
    DOWNLOAD_THREAD = threading.Thread(target=run_server, daemon=True)
    DOWNLOAD_THREAD.start()
    time.sleep(0.5)
    # Ajusta firewall se necessário: cria regra apenas se ela não existir
    check_rule = run_cmd(['iptables', '-C', 'INPUT', '-p', 'tcp', '--dport', str(DOWNLOAD_PORT), '-j', 'ACCEPT'])
    if check_rule.returncode != 0:
        run_cmd(['iptables', '-A', 'INPUT', '-p', 'tcp', '--dport', str(DOWNLOAD_PORT), '-j', 'ACCEPT'])

def stop_download_server():
    """Encerra o servidor HTTP de download, se ativo."""
    global DOWNLOAD_SERVER, DOWNLOAD_THREAD
    if DOWNLOAD_SERVER:
        try:
            DOWNLOAD_SERVER.server_close()
        except Exception:
            pass
        DOWNLOAD_SERVER = None
    if DOWNLOAD_THREAD and DOWNLOAD_THREAD.is_alive():
        DOWNLOAD_THREAD.join(timeout=0.1)
    DOWNLOAD_THREAD = None

def get_remaining_download_time():
    """Retorna o tempo restante (em minutos) para o servidor de download."""
    if not DOWNLOAD_START_TIME:
        return DOWNLOAD_DURATION // 60
    elapsed = (datetime.now() - DOWNLOAD_START_TIME).total_seconds()
    remaining = max(DOWNLOAD_DURATION - elapsed, 0)
    return int(remaining // 60) or 1

def is_download_server_active():
    """Retorna True se o servidor de download estiver rodando."""
    return DOWNLOAD_SERVER is not None

# --------------------------------------------------------------------
# Helpers de serviço
# --------------------------------------------------------------------
def detect_service_candidates():
    """Tenta detectar serviços openvpn@*.service ativos ou instalados."""
    result = run_cmd(['systemctl', 'list-unit-files', '--type=service', '--no-legend'])
    units = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].startswith('openvpn@'):
                name = parts[0]
                if name not in units:
                    units.append(name)
    return units

def pick_server_unit():
    """Retorna o primeiro serviço systemd encontrado, ou None."""
    units = detect_service_candidates()
    return units[0] if units else None

def verificar_openvpn_instalado():
    """Retorna True se o OpenVPN parece estar instalado e configurado."""
    r = run_cmd(['which', 'openvpn'])
    if not (r.returncode == 0 and r.stdout.strip()):
        return False
    # Configuração
    if find_server_conf():
        return True
    # Unidades
    if detect_service_candidates():
        return True
    return False

def parse_port_proto_dns(conf_path):
    """Extrai porta, protocolo e DNS da configuração do servidor."""
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
                    m = re.search(r'DNS\s+([0-9]{1,3}(?:\.[0-9]{1,3}){3})', ls, re.I)
                    if m:
                        dns_list.append(m.group(1))
    except Exception:
        pass
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

def find_server_conf():
    """Retorna o caminho para /etc/openvpn/server.conf se existir."""
    candidates = [
        "/etc/openvpn/server.conf",
        "/etc/openvpn/openvpn.conf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

# --------------------------------------------------------------------
# Helpers de firewall
# --------------------------------------------------------------------
def update_firewall_port(old_port, new_port):
    """Remove regras antigas para old_port e adiciona regras para new_port."""
    run_cmd(['iptables', '-D', 'INPUT', '-p', 'udp', '--dport', str(old_port), '-j', 'ACCEPT'])
    run_cmd(['iptables', '-D', 'INPUT', '-p', 'tcp', '--dport', str(old_port), '-j', 'ACCEPT'])
    # Adiciona regra UDP se ainda não existir
    check_udp = run_cmd(['iptables', '-C', 'INPUT', '-p', 'udp', '--dport', str(new_port), '-j', 'ACCEPT'])
    if check_udp.returncode != 0:
        run_cmd(['iptables', '-A', 'INPUT', '-p', 'udp', '--dport', str(new_port), '-j', 'ACCEPT'])
    # Adiciona regra TCP se ainda não existir
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

# --------------------------------------------------------------------
# Controle do serviço OpenVPN
# --------------------------------------------------------------------
def restart_openvpn():
    """Reinicia o serviço OpenVPN e retorna (True, msg) em caso de sucesso."""
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

# --------------------------------------------------------------------
# Integração com openvpn.sh
# --------------------------------------------------------------------
def descobrir_script_openvpn():
    """Localiza script shell de instalação/gerência openvpn.sh, se existir."""
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
    """Executa o script shell openvpn.sh de forma não-interativa.

    O script `openvpn.sh` modificado exibe uma pergunta inicial perguntando
    ao usuário se deseja iniciar a instalação do OpenVPN (opções 1 ou 0). No
    contexto deste menu, o próprio menu já representa a confirmação de
    instalação (quando o usuário escolhe a opção "Instalar openvpn"). Por
    isso, alimentamos a opção "1\n" diretamente na entrada padrão do
    script, para que ele siga em frente automaticamente sem exigir
    interação adicional. A saída do script é exibida na tela normal
    (fora da tela alternada) e, ao terminar, retornamos para a tela
    alternada. Caso o script não seja encontrado, retorna uma mensagem
    apropriada.
    """
    script_path = descobrir_script_openvpn()
    if not script_path:
        return False, "Script openvpn.sh não encontrado."
    try:
        # Exibe um quadro de operação para informar que o script será executado
        TerminalManager.render(build_operation_frame("Executando openvpn.sh", "", MC.GREEN_GRADIENT, "Inicializando..."))
        # Sai da tela alternada para que o usuário veja a execução do shell script
        TerminalManager.leave_alt_screen()
        # Garante permissão de execução
        subprocess.run(['chmod', '+x', script_path], check=False)
        # Alimenta "1\n" como resposta automática à pergunta inicial do script
        # definindo text=True para aceitar string como input
        result = subprocess.run(['bash', script_path], input='1\n', text=True)
        # Volta para a tela alternada após finalização
        TerminalManager.enter_alt_screen()
        # Retorna True/False dependendo do código de saída
        return result.returncode == 0, ("Concluído" if result.returncode == 0 else "Falhou")
    except Exception as e:
        # Assegura retorno à tela alternada mesmo em caso de exceção
        TerminalManager.enter_alt_screen()
        return False, str(e)

# --------------------------------------------------------------------
# Geração de arquivo OVPN
# --------------------------------------------------------------------
def criar_arquivo_ovpn(client_name):
    """Cria um arquivo OVPN para o cliente especificado.

    Gera o certificado do cliente se ainda não existir, constrói o conteúdo
    do perfil com as diretivas padrão e inclui os certificados e chaves
    como blocos <ca>, <cert>, <key> e <tls-crypt>/<tls-auth> quando
    apropriado. Retorna o caminho do arquivo gerado e None em caso de
    sucesso, ou (None, msg) em caso de erro.
    """
    if not verificar_openvpn_instalado():
        return None, "OpenVPN não está instalado"
    server_conf = find_server_conf()
    if not server_conf:
        return None, "Configuração do servidor não encontrada"
    # Extrai informações básicas
    port, proto, _, _ = parse_port_proto_dns(server_conf)
    server_ip = get_public_ip()
    conf_dir = os.path.dirname(server_conf)
    easy_rsa_dir = "/etc/openvpn/easy-rsa"
    if not os.path.exists(easy_rsa_dir):
        return None, "Easy-RSA não encontrado"
    client_cert = f"{easy_rsa_dir}/pki/issued/{client_name}.crt"
    if not os.path.exists(client_cert):
        # Gera certificado se não existir
        try:
            os.chdir(easy_rsa_dir)
            create_result = run_cmd(['bash', '-c', f'echo "yes" | ./easyrsa build-client-full "{client_name}" nopass'], timeout=30)
            if create_result.returncode != 0:
                return None, "Erro ao criar certificado do cliente"
        except Exception as e:
            return None, f"Erro ao criar certificado: {str(e)}"
    client_dir = os.path.expanduser("~/ovpn-clients")
    os.makedirs(client_dir, exist_ok=True)
    ovpn_file = os.path.join(client_dir, f"{client_name}.ovpn")
    try:
        with open(f"{conf_dir}/ca.crt", 'r') as f:
            ca_cert = f.read().strip()
        with open(f"{easy_rsa_dir}/pki/issued/{client_name}.crt", 'r') as f:
            client_cert_content = f.read().strip()
        with open(f"{easy_rsa_dir}/pki/private/{client_name}.key", 'r') as f:
            client_key = f.read().strip()
        tls_key = ""
        tls_directive = ""
        if os.path.exists(f"{conf_dir}/tc.key"):
            with open(f"{conf_dir}/tc.key", 'r') as f:
                tls_key = f.read().strip()
            tls_directive = f"<tls-crypt>\n{tls_key}\n</tls-crypt>"
        elif os.path.exists(f"{conf_dir}/ta.key"):
            with open(f"{conf_dir}/ta.key", 'r') as f:
                tls_key = f.read().strip()
            tls_directive = f"<tls-auth>\n{tls_key}\n</tls-auth>\nkey-direction 1"
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
    tls-version-min 1.2

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
        with open(ovpn_file, 'w') as f:
            f.write(ovpn_content)
        return ovpn_file, None
    except Exception as e:
        return None, f"Erro ao criar arquivo OVPN: {str(e)}"

# --------------------------------------------------------------------
# Helpers de edição e backup de configuração
# --------------------------------------------------------------------
def backup_file(path):
    """Cria uma cópia de backup do arquivo com sufixo timestamp."""
    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        copyfile(path, f"{path}.bak-{ts}")
        return True
    except Exception:
        return False

def write_file(path, content):
    """Escreve texto em um arquivo com codificação UTF-8."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def read_file(path):
    """Lê conteúdo de um arquivo ignorando erros de codificação."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def set_conf_port(conf_path, new_port):
    """Substitui ou insere diretiva 'port' no arquivo de configuração."""
    text = read_file(conf_path)
    if re.search(r'^\s*port\s+\d+', text, re.M):
        text = re.sub(r'^\s*port\s+\d+', f"port {new_port}", text, flags=re.M)
    else:
        text = f"port {new_port}\n" + text
    write_file(conf_path, text)

def set_conf_proto(conf_path, new_proto):
    """Substitui ou insere diretiva 'proto' no arquivo de configuração."""
    text = read_file(conf_path)
    if re.search(r'^\s*proto\s+\w+', text, re.M):
        text = re.sub(r'^\s*proto\s+\w+', f"proto {new_proto}", text, flags=re.M)
    else:
        text = f"proto {new_proto}\n" + text
    write_file(conf_path, text)

def set_conf_dns(conf_path, dns_list):
    """Substitui ou insere diretivas DHCP DNS no arquivo de configuração."""
    text = read_file(conf_path)
    # Remove todas as diretivas push "dhcp-option DNS X.X.X.X"
    text = re.sub(r'^\s*push\s+"dhcp-option\s+DNS\s+[0-9.]+"\s*$', '', text, flags=re.M)
    # Insere novas entradas logo após a linha 'push "redirect-gateway def1 bypass-dhcp"'
    lines = text.splitlines()
    idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith('push "redirect-gateway'):
            idx = i
            break
    new_push_lines = [f"push \"dhcp-option DNS {dns}\"" for dns in dns_list]
    if idx != -1:
        lines[idx+1:idx+1] = new_push_lines
    else:
        lines.extend(new_push_lines)
    write_file(conf_path, "\n".join(lines))

def update_clients_configs(new_port=None, new_proto=None):
    """Atualiza configurações de clientes existentes ao alterar porta ou protocolo."""
    client_dir = os.path.expanduser("~/ovpn-clients")
    if not os.path.isdir(client_dir):
        return
    for filename in os.listdir(client_dir):
        if filename.endswith(".ovpn"):
            path = os.path.join(client_dir, filename)
            try:
                content = read_file(path)
                if new_proto:
                    content = re.sub(r'^proto\s+\w+', f"proto {new_proto}", content, flags=re.M)
                if new_port:
                    content = re.sub(r'^(remote\s+\S+\s+)\d+(\b.*)$', rf'\g<1>{new_port}\2', content, flags=re.M)
                write_file(path, content)
            except Exception:
                pass

# --------------------------------------------------------------------
# Ações do menu
# --------------------------------------------------------------------
def is_valid_port(p):
    try:
        n = int(p)
        return 1 <= n <= 65535
    except Exception:
        return False

# Regex para validar IPv4 (utilizado no input de DNS customizado)
ipv4_re = re.compile(r'^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$')

def alterar_porta():
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
    conf = find_server_conf()
    if not conf:
        return False, "OpenVPN não instalado/configurado."
    _, _, dns_label, dns_list = parse_port_proto_dns(conf)
    print(f"\n{MC.WHITE}DNS atual: {MC.CYAN}{dns_label} {( '(' + ', '.join(dns_list) + ')' ) if dns_list else ''}{MC.RESET}")
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
        return ok, f"DNS alterado. {msg}"
    except Exception as e:
        return False, f"Erro ao alterar DNS: {e}"

def gerar_download_ovpn():
    """Interação para gerar arquivo .ovpn e disponibilizá-lo via HTTP."""
    global DOWNLOAD_FILE_PATH
    if not verificar_openvpn_instalado():
        return False, "OpenVPN não está instalado"
    TerminalManager.before_input()
    client_name = input(f"\n{MC.BOLD}Nome do cliente (ex. user1): {MC.RESET}").strip()
    TerminalManager.after_input()
    if not client_name:
        return False, "Nome inválido."
    ovpn_file, error = criar_arquivo_ovpn(client_name)
    if error:
        return False, error
    # Inicia servidor
    start_download_server(ovpn_file)
    return True, f"Arquivo gerado: {client_name}.ovpn (porta {DOWNLOAD_PORT})"

def desinstalar_openvpn():
    """Interação para desinstalar OpenVPN e easy-rsa.

    Atualizado para evitar chamar o script openvpn.sh para desinstalação,
    pois o script shell modificado não fornece mais um menu de ações. A
    desinstalação é realizada diretamente aqui após confirmação do usuário.
    """
    # Aviso ao usuário
    print(f"\n{MC.RED_GRADIENT}ATENÇÃO: Isso removerá OpenVPN e easy-rsa.{MC.RESET}")
    TerminalManager.before_input()
    c = input(f"{MC.BOLD}Confirmar? [s/N]: {MC.RESET}").strip().lower()
    TerminalManager.after_input()
    if c != "s":
        return False, "Operação cancelada."
    # Tenta detectar sistema
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
    # Para Debian/Ubuntu usa apt, caso contrário yum (CentOS/Fedora/RHEL)
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

# --------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------
def build_status_box():
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
            dns_label = {"google": "google", "cloudflare": "cloudflare"}.get(dns_lab, dns_lab)
    lines = [
        f"{MC.CYAN_LIGHT}Status:{MC.RESET} {MC.WHITE}{status_str}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Porta:{MC.RESET} {MC.WHITE}{porta}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Protocolo:{MC.RESET} {MC.WHITE}{protocolo}{MC.RESET}",
        f"{MC.CYAN_LIGHT}Dns:{MC.RESET} {MC.WHITE}{dns_label}{MC.RESET}",
    ]
    if is_download_server_active():
        remaining = get_remaining_download_time()
        lines.append(f"{MC.CYAN_LIGHT}Download:{MC.RESET} {MC.GREEN}Ativo ({remaining} min restantes){MC.RESET}")
    return modern_box("STATUS", lines, "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT)

def build_menu_frame(status_msg=""):
    s = []
    s.append(simple_header("GERENCIADOR OPENVPN"))
    s.append(build_status_box())
    s.append("\n")
    s.append(menu_option("1", "Instalar openvpn", "", MC.GREEN_GRADIENT))
    s.append(menu_option("2", "Alterar porta", "", MC.CYAN_GRADIENT))
    s.append(menu_option("3", "Alterar protocolo", "", MC.BLUE_GRADIENT))
    s.append(menu_option("4", "Alterar Dns", "", MC.ORANGE_GRADIENT))
    s.append(menu_option("5", "Gerar e baixar arquivo ovpn", "", MC.MAGENTA_GRADIENT))
    s.append(menu_option("6", "Desinstalar Openvpn", "", MC.RED_GRADIENT))
    s.append("\n")
    s.append(menu_option("0", "Voltar", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_operation_frame(title, icon, color, msg="Aguarde..."):
    s = []
    s.append(simple_header("OPERAÇÃO EM ANDAMENTO"))
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}{msg}{MC.RESET}"
    ], "", color, MC.CYAN_LIGHT))
    s.append(footer_line("Processando..."))
    return "".join(s)

# --------------------------------------------------------------------
# Loop principal
# --------------------------------------------------------------------
def main_menu():
    """Menu principal do gerenciador OpenVPN."""
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
                TerminalManager.render(build_operation_frame("Gerar arquivo OVPN", "", MC.MAGENTA_GRADIENT, "Criando arquivo e link..."))
                ok, msg = gerar_download_ovpn()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "6":
                TerminalManager.render(build_operation_frame("Desinstalar OpenVPN", "", MC.RED_GRADIENT, "Removendo..."))
                ok, msg = desinstalar_openvpn()
                status_msg = msg if ok else f"Erro: {msg}"
            elif choice == "0":
                stop_download_server()
                break
            else:
                status_msg = "Opção inválida."
    finally:
        TerminalManager.leave_alt_screen()

# Executa menu se script for executado diretamente
if __name__ == "__main__":
    main_menu()
