#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys

# --- Constantes ---
HOSTS_FILE = "/etc/hosts"
RESOLV_CONF = "/etc/resolv.conf"
BLOCK_IP = "0.0.0.0"
BLOCK_MARKER = "# Blocked by Multiflow"

# Dicionário de provedores de DNS para bloqueio de conteúdo adulto e malicioso
DNS_PROVIDERS = {
    "1": {
        "name": "CleanBrowsing (Filtro Adulto)",
        "ips": ["185.228.168.10", "185.228.169.11"]
    },
    "2": {
        "name": "Cloudflare Family (Malware + Adulto)",
        "ips": ["1.1.1.3", "1.0.0.3"]
    },
    "3": {
        "name": "OpenDNS FamilyShield",
        "ips": ["208.67.222.123", "208.67.220.123"]
    }
}
# DNS padrão para reverter a configuração (Google DNS)
DEFAULT_DNS = ["8.8.8.8", "8.8.4.4"]

# --- Funções de Lógica ---

def _run_command(command, silent=False):
    """Executa um comando no shell, tratando erros de forma segura."""
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        if not silent:
            print(result.stdout)
        return True, result.stdout
    except FileNotFoundError:
        return False, f"Comando '{command[0]}' não encontrado."
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except Exception as e:
        return False, str(e)

def set_dns_servers(servers):
    """
    Define os servidores DNS do sistema e torna a configuração imutável
    para evitar que seja sobrescrita por outros serviços de rede.
    Retorna (True, "Sucesso") ou (False, "Mensagem de Erro").
    """
    if os.geteuid() != 0:
        return False, "Esta operação requer privilégios de root."

    # Torna o arquivo mutável antes de editar
    _run_command(['chattr', '-i', RESOLV_CONF], silent=True)

    try:
        with open(RESOLV_CONF, 'w', encoding='utf-8') as f:
            f.write("# Configurado por Multiflow\n")
            f.write("# Esta configuração é imutável para garantir a permanência do filtro.\n")
            for server in servers:
                f.write(f"nameserver {server}\n")
    except IOError as e:
        # Se falhar, tenta restaurar o estado original do chattr
        _run_command(['chattr', '+i', RESOLV_CONF], silent=True)
        return False, f"Não foi possível escrever em {RESOLV_CONF}: {e}"

    # Torna o arquivo imutável novamente
    success, msg = _run_command(['chattr', '+i', RESOLV_CONF], silent=True)
    if not success:
        return False, f"Falha ao proteger o arquivo {RESOLV_CONF}: {msg}"

    return True, "Servidores DNS atualizados e protegidos com sucesso."

def block_domain_by_hosts(domain):
    """
    Bloqueia um domínio adicionando-o ao arquivo /etc/hosts.
    Retorna (True, "Sucesso") ou (False, "Mensagem de Erro").
    """
    if os.geteuid() != 0:
        return False, "Esta operação requer privilégios de root."
    
    domain = domain.strip().lower()
    if not domain:
        return False, "O nome do domínio não pode ser vazio."

    try:
        with open(HOSTS_FILE, 'r+', encoding='utf-8') as f:
            content = f.read()
            # Verifica se o domínio já está bloqueado para evitar duplicatas
            if f"{BLOCK_IP} {domain}" in content:
                return True, f"O domínio {domain} já se encontra bloqueado."
            
            # Adiciona as novas entradas no final do arquivo
            f.write(f"\n{BLOCK_MARKER}\n")
            f.write(f"{BLOCK_IP} {domain}\n")
            f.write(f"{BLOCK_IP} www.{domain}\n")
        return True, f"Domínio {domain} bloqueado com sucesso."
    except IOError as e:
        return False, f"Não foi possível acessar o arquivo {HOSTS_FILE}: {e}"

def unblock_domain_by_hosts(domain):
    """
    Desbloqueia um domínio removendo suas entradas do arquivo /etc/hosts.
    Retorna (True, "Sucesso") ou (False, "Mensagem de Erro").
    """
    if os.geteuid() != 0:
        return False, "Esta operação requer privilégios de root."

    domain = domain.strip().lower()
    if not domain:
        return False, "O nome do domínio não pode ser vazio."

    try:
        lines_to_keep = []
        found = False
        with open(HOSTS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Filtra as linhas, removendo as que correspondem ao domínio bloqueado
        i = 0
        while i < len(lines):
            line = lines[i]
            # Se a linha contém o domínio e o IP de bloqueio, marca como encontrado
            if domain in line and line.strip().startswith(BLOCK_IP):
                found = True
                # Verifica se a linha anterior é o marcador para removê-la também
                if i > 0 and BLOCK_MARKER in lines[i-1]:
                    lines_to_keep.pop() # Remove o marcador já adicionado
                i += 1 # Pula a linha atual
                continue
            lines_to_keep.append(line)
            i += 1

        if not found:
            return False, f"O domínio {domain} não foi encontrado na lista de bloqueio."

        # Escreve o conteúdo filtrado de volta no arquivo
        with open(HOSTS_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines_to_keep)
        
        return True, f"Domínio {domain} desbloqueado com sucesso."
    except IOError as e:
        return False, f"Não foi possível acessar o arquivo {HOSTS_FILE}: {e}"

def get_blocked_domains():
    """Retorna uma lista de domínios únicos bloqueados via /etc/hosts."""
    blocked_domains = set()
    try:
        with open(HOSTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith(BLOCK_IP):
                    parts = line.split()
                    if len(parts) >= 2:
                        # Adiciona o domínio à lista, ignorando o 'www.'
                        domain_name = parts[1].replace("www.", "")
                        blocked_domains.add(domain_name)
    except IOError:
        return []
    return sorted(list(blocked_domains))

def get_current_dns():
    """Retorna os servidores DNS atualmente configurados em /etc/resolv.conf."""
    dns_servers = []
    try:
        with open(RESOLV_CONF, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    dns_servers.append(line.split()[1])
    except IOError:
        return []
    return dns_servers
