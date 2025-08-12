#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
from pathlib import Path

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from menus.menu_style_utils import (
        MC, Icons, TerminalManager,
        modern_box, menu_option, footer_line, simple_header
    )
except ImportError as e:
    print(f"Erro ao importar utilitários: {e}")
    sys.exit(1)

# ---------------------- Utilidades internas ----------------------

def run_cmd(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def find_server_conf():
    """
    Detecta o arquivo de configuração do servidor OpenVPN conforme o layout da distro.
    Retorna o caminho do server.conf se encontrado, senão None.
    """
    candidates = [
        "/etc/openvpn/server/server.conf",  # layout moderno (openvpn-server@server)
        "/etc/openvpn/server.conf",         # layout legado (openvpn@server)
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def detect_service_candidates():
    """
    Lista os nomes de serviço possíveis, priorizando os que existem no sistema.
    """
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
    # Garante ordem e remove duplicatas mantendo prioridade
    seen = set()
    ordered = []
    for name in present + [c.replace(".service", "") for c in base_candidates]:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered

def parse_port_proto(conf_path):
    """
    Lê port e proto do server.conf. Defaults: port=1194, proto=udp
    """
    port = "1194"
    proto = "udp"
    try:
        with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ls = line.strip()
                if ls.startswith("#") or not ls:
                    continue
                if ls.lower().startswith("port "):
                    parts = ls.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        port = parts[1]
                elif ls.lower().startswith("proto "):
                    parts = ls.split()
                    if len(parts) >= 2:
                        proto = parts[1].lower()
    except Exception:
        pass
    return port, proto

def ss_listens_on(port, proto):
    """
    Verifica se há processo openvpn escutando na porta/protocolo.
    Usa ss (preferível) e fallback para lsof.
    """
    proto = proto.lower()
    # Ajusta comando ss conforme protocolo
    if proto.startswith("udp"):
        cmd = ["ss", "-lunp"]
    else:
        cmd = ["ss", "-ltnp"]
    res = run_cmd(cmd, timeout=5)
    if res.returncode == 0 and str(port) in res.stdout:
        if "openvpn" in res.stdout.lower():
            return True
    # Fallback: lsof
    res2 = run_cmd(["lsof", "-nP", "-i", f":{port}"], timeout=5)
    if res2.returncode == 0 and "openvpn" in res2.stdout.lower():
        return True
    return False

def get_clients_dir():
    """
    Diretório padrão onde os .ovpn são salvos pelo script bash moderno.
    """
    home = str(Path("/root").expanduser())
    return os.path.join(home, "ovpn-clients")

def list_ovpn_files():
    """
    Lista arquivos .ovpn em ~/ovpn-clients (padrão) e /root (legado).
    """
    files = []
    dirs = [get_clients_dir(), "/root"]
    for d in dirs:
        try:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".ovpn"):
                        files.append(os.path.join(d, f))
        except Exception:
            pass
    # Remove duplicatas mantendo ordem
    seen = set()
    ordered = []
    for f in files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered

def descobrir_script_openvpn():
    """
    Detecta o caminho do script openvpn.sh/manager.
    Permite override via variável de ambiente OVPN_SCRIPT_PATH.
    """
    # Override via env
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

# ---------------------- Lógica de status/instalação ----------------------

def verificar_openvpn_instalado():
    """Verifica se o OpenVPN está instalado verificando arquivos, binário e serviços"""
    # Existe binário?
    result = run_cmd(['which', 'openvpn'])
    if not (result.returncode == 0 and result.stdout.strip()):
        return False

    # Existe config?
    conf = find_server_conf()
    if conf and os.path.exists(conf):
        return True

    # Existem unidades de serviço conhecidas?
    units = detect_service_candidates()
    if units:
        return True

    return False

def get_openvpn_status():
    """Obtém o status detalhado do OpenVPN"""
    if not verificar_openvpn_instalado():
        return f"{MC.RED_GRADIENT}Não Instalado{MC.RESET}"

    # Determina conf/porta/proto para checagem precisa
    conf = find_server_conf()
    port, proto = ("1194", "udp")
    if conf:
        port, proto = parse_port_proto(conf)

    # Verifica status via systemd
    service_names = detect_service_candidates()
    for service in service_names:
        result = run_cmd(['systemctl', 'is-active', service])
        status = result.stdout.strip().lower()
        if status == 'active':
            # Checa se porta está em escuta
            if ss_listens_on(port, proto):
                return f"{MC.GREEN_GRADIENT}Ativo{MC.RESET}"
            else:
                return f"{MC.GREEN_GRADIENT}Ativo (verificar porta {port}/{proto}){MC.RESET}"
        elif status == 'failed':
            return f"{MC.RED_GRADIENT}Falhou{MC.RESET}"
        elif status == 'activating':
            return f"{MC.YELLOW_GRADIENT}Iniciando{MC.RESET}"
        # inactive/unknown: tenta próximo

    # Se nenhum serviço ativo, verifica processo
    ps_result = run_cmd(['pgrep', '-x', 'openvpn'])
    if ps_result.returncode == 0:
        return f"{MC.GREEN_GRADIENT}Processo Ativo{MC.RESET}"

    return f"{MC.YELLOW_GRADIENT}Instalado (Inativo){MC.RESET}"

def count_ovpn_files():
    try:
        return len(list_ovpn_files())
    except Exception:
        return 0

# ---------------------- UI/Render ----------------------

def build_main_frame(status_msg=""):
    s=[]
    s.append(simple_header("GERENCIADOR OPENVPN"))
    status = get_openvpn_status(); clients = count_ovpn_files()
    s.append(modern_box("STATUS DO SERVIÇO", [
        f"{MC.CYAN_LIGHT}Status:{MC.RESET} {status}",
        f"{MC.CYAN_LIGHT}Clientes Configurados:{MC.RESET} {MC.WHITE}{clients}{MC.RESET}"
    ], "", MC.PURPLE_GRADIENT, MC.PURPLE_LIGHT))
    s.append("\n")
    if verificar_openvpn_instalado():
        s.append(modern_box("OPÇÕES DISPONÍVEIS", [], "", MC.BLUE_GRADIENT, MC.BLUE_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Adicionar Novo Cliente", "", MC.GREEN_GRADIENT))
        s.append(menu_option("2", "Remover Cliente", "", MC.ORANGE_GRADIENT))
        s.append(menu_option("3", "Listar Arquivos .ovpn", "", MC.CYAN_GRADIENT))
        s.append(menu_option("4", "Reinstalar OpenVPN", "", MC.YELLOW_GRADIENT))
        s.append(menu_option("5", "Desinstalar OpenVPN", "", MC.RED_GRADIENT))
    else:
        s.append(modern_box("INSTALAÇÃO DISPONÍVEL", [
            f"{MC.YELLOW_GRADIENT}OpenVPN não está instalado{MC.RESET}",
            f"{MC.WHITE}Configuração automática com:{MC.RESET}",
            "  • Protocolo UDP",
            "  • DNS Cloudflare",
            "  • Cliente inicial: cliente1.ovpn"
        ], "", MC.GREEN_GRADIENT, MC.GREEN_LIGHT))
        s.append("\n")
        s.append(menu_option("1", "Instalar OpenVPN Agora", "", MC.GREEN_GRADIENT, badge="RECOMENDADO"))
    s.append("\n")
    s.append(menu_option("0", "Voltar ao Menu Principal", "", MC.YELLOW_GRADIENT))
    s.append(footer_line(status_msg))
    return "".join(s)

def build_clients_frame():
    s=[]
    s.append(simple_header("CLIENTES OPENVPN"))
    try:
        files = list_ovpn_files()
        if files:
            content=[]
            for f in files:
                try:
                    size = os.path.getsize(f) / 1024
                    content.append(f"{MC.CYAN_LIGHT}•{MC.RESET} {f} {MC.GRAY}({size:.1f} KB){MC.RESET}")
                except Exception:
                    content.append(f"{MC.CYAN_LIGHT}•{MC.RESET} {f}")
            content.append("")
            content.append(f"{MC.YELLOW_GRADIENT}Use SFTP para baixar os arquivos{MC.RESET}")
        else:
            content=[f"{MC.YELLOW_GRADIENT}Nenhum arquivo .ovpn encontrado{MC.RESET}"]
        s.append(modern_box("ARQUIVOS DE CONFIGURAÇÃO", content, "", MC.CYAN_GRADIENT, MC.CYAN_LIGHT))
    except Exception as e:
        s.append(modern_box("ERRO", [f"{MC.RED_GRADIENT}{e}{MC.RESET}"], "", MC.RED_GRADIENT, MC.RED_LIGHT))
    s.append(footer_line())
    return "".join(s)

def build_operation_frame(title, icon, color, msg="Aguarde..."):
    s=[]
    s.append(simple_header("OPERAÇÃO EM ANDAMENTO"))
    s.append(modern_box(title, [
        f"{MC.YELLOW_GRADIENT}Não interrompa o processo{MC.RESET}",
        f"{MC.WHITE}{msg}{MC.RESET}"
    ], "", color, MC.CYAN_LIGHT))
    s.append(footer_line("Processando..."))
    return "".join(s)

# ---------------------- Execução do script bash ----------------------

def obter_caminho_script():
    return descobrir_script_openvpn()

def executar_script_openvpn():
    script_path = obter_caminho_script()
    if not script_path:
        return False, "Script openvpn.sh/openvpn-manager.sh não encontrado em conexoes/."
    try:
        TerminalManager.render(build_operation_frame("Executando openvpn.sh", "", MC.GREEN_GRADIENT, "Inicializando instalação/gestão..."))
        # Sair do alt-screen para mostrar saída do script interativo
        TerminalManager.leave_alt_screen()
        subprocess.run(['chmod', '+x', script_path], check=False)
        result = subprocess.run(['bash', script_path], check=False)
        TerminalManager.enter_alt_screen()
        return result.returncode == 0, ("Concluído" if result.returncode == 0 else "Falhou (verifique logs)")
    except Exception as e:
        TerminalManager.enter_alt_screen()
        return False, str(e)

# ---------------------- Menu principal ----------------------

def main_menu():
    if os.geteuid() != 0:
        print(f"{MC.RED_GRADIENT}Este menu precisa ser executado como root.{MC.RESET}")
        input("Pressione Enter para voltar...")
        return
    TerminalManager.enter_alt_screen()
    status=""
    try:
        while True:
            TerminalManager.render(build_main_frame(status))
            TerminalManager.before_input()
            choice = input(f"\n{MC.PURPLE_GRADIENT}{MC.BOLD}└─ Escolha uma opção: {MC.RESET}").strip()
            TerminalManager.after_input()
            if verificar_openvpn_instalado():
                if choice == "1":
                    ok,msg = executar_script_openvpn(); status = "Cliente adicionado" if ok else f"Erro: {msg}"
                elif choice == "2":
                    ok,msg = executar_script_openvpn(); status = "Cliente removido" if ok else f"Erro: {msg}"
                elif choice == "3":
                    TerminalManager.render(build_clients_frame())
                    TerminalManager.before_input()
                    input(f"\n{MC.BOLD}Pressione Enter para voltar...{MC.RESET}")
                    TerminalManager.after_input()
                    status="Listagem concluída"
                elif choice == "4":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN reinstalado" if ok else f"Erro: {msg}"
                elif choice == "5":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN desinstalado" if ok else f"Erro: {msg}"
                elif choice == "0":
                    break
                else:
                    status="Opção inválida"
            else:
                if choice == "1":
                    ok,msg = executar_script_openvpn(); status = "OpenVPN instalado com sucesso!" if ok else f"Erro: {msg}"
                elif choice == "0":
                    break
                else:
                    status="Opção inválida"
            time.sleep(0.6)
    finally:
        TerminalManager.leave_alt_screen()

if __name__ == "__main__":
    main_menu()
