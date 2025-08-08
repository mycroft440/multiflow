#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time

# Adiciona o diretório pai ao sys.path para permitir importações de outros módulos do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from ferramentas import bloqueador_sites
    from menus.menu_style_utils import Colors, BoxChars, print_colored_box, print_menu_option, clear_screen
except ImportError as e:
    print(f"Erro de importação: {e}. Verifique se todos os arquivos do projeto estão nos diretórios corretos.")
    sys.exit(1)

COLORS = Colors()

def show_dns_status():
    """Exibe o status atual do filtro DNS de forma clara."""
    current_dns = bloqueador_sites.get_current_dns()
    if not current_dns:
        return f"{COLORS.RED}Não foi possível ler a configuração de DNS.{COLORS.END}"

    for provider in bloqueador_sites.DNS_PROVIDERS.values():
        if set(provider['ips']) == set(current_dns):
            return f"{COLORS.GREEN}Ativo ({provider['name']}){COLORS.END}"
    
    if set(bloqueador_sites.DEFAULT_DNS) == set(current_dns):
        return f"{COLORS.YELLOW}Inativo (usando DNS Padrão){COLORS.END}"
    
    return f"{COLORS.YELLOW}Inativo (DNS Customizado: {', '.join(current_dns)}){COLORS.END}"

def menu_ativar_filtro_dns():
    """Apresenta um menu para o usuário escolher e ativar um filtro DNS."""
    clear_screen()
    print_colored_box("ATIVAR FILTRO DE SITES (VIA DNS)")
    
    for key, provider in bloqueador_sites.DNS_PROVIDERS.items():
        print_menu_option(key, provider['name'], color=COLORS.CYAN)
    
    print_menu_option("0", "Cancelar", color=COLORS.YELLOW)
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")
    
    choice = input(f"\n{COLORS.BOLD}Escolha um provedor de filtro: {COLORS.END}")

    if choice in bloqueador_sites.DNS_PROVIDERS:
        provider = bloqueador_sites.DNS_PROVIDERS[choice]
        print(f"\n{COLORS.YELLOW}Ativando filtro: {provider['name']}...{COLORS.END}")
        success, msg = bloqueador_sites.set_dns_servers(provider['ips'])
        if success:
            print(f"{COLORS.GREEN}✓ {msg}{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ {msg}{COLORS.END}")
    elif choice == '0':
        print(f"\n{COLORS.YELLOW}Operação cancelada.{COLORS.END}")
    else:
        print(f"\n{COLORS.RED}Opção inválida.{COLORS.END}")

def menu_desativar_filtro_dns():
    """Desativa o filtro DNS, revertendo para servidores padrão."""
    print(f"\n{COLORS.YELLOW}Revertendo para servidores DNS padrão (Google)...{COLORS.END}")
    success, msg = bloqueador_sites.set_dns_servers(bloqueador_sites.DEFAULT_DNS)
    if success:
        print(f"{COLORS.GREEN}✓ {msg}{COLORS.END}")
    else:
        print(f"{COLORS.RED}✗ {msg}{COLORS.END}")

def menu_bloquear_dominio():
    """Pede ao usuário um domínio e o bloqueia via /etc/hosts."""
    domain = input(f"\n{COLORS.CYAN}Digite o domínio que deseja bloquear (ex: facebook.com): {COLORS.END}")
    if domain:
        success, msg = bloqueador_sites.block_domain_by_hosts(domain)
        if success:
            print(f"{COLORS.GREEN}✓ {msg}{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ {msg}{COLORS.END}")
    else:
        print(f"\n{COLORS.YELLOW}Nenhum domínio inserido. Operação cancelada.{COLORS.END}")

def menu_desbloquear_dominio():
    """Pede ao usuário um domínio e o desbloqueia."""
    domain = input(f"\n{COLORS.CYAN}Digite o domínio que deseja desbloquear: {COLORS.END}")
    if domain:
        success, msg = bloqueador_sites.unblock_domain_by_hosts(domain)
        if success:
            print(f"{COLORS.GREEN}✓ {msg}{COLORS.END}")
        else:
            print(f"{COLORS.RED}✗ {msg}{COLORS.END}")
    else:
        print(f"\n{COLORS.YELLOW}Nenhum domínio inserido. Operação cancelada.{COLORS.END}")

def menu_listar_dominios():
    """Lista os domínios que foram bloqueados manualmente."""
    clear_screen()
    domains = bloqueador_sites.get_blocked_domains()
    if domains:
        print_colored_box("DOMÍNIOS BLOQUEADOS VIA /etc/hosts", domains)
    else:
        print_colored_box("DOMÍNIOS BLOQUEADOS VIA /etc/hosts", ["Nenhum domínio bloqueado manualmente."])

def main_menu():
    """Exibe o menu principal do módulo de bloqueio."""
    if os.geteuid() != 0:
        print(f"{COLORS.RED}Este script precisa ser executado como root (superusuário).{COLORS.END}")
        sys.exit(1)

    while True:
        clear_screen()
        dns_status = show_dns_status()
        print_colored_box("BLOQUEADOR DE SITES", [f"Status do Filtro DNS: {dns_status}"])
        
        print(f"\n{COLORS.BOLD}--- Bloqueio Geral (DNS para toda a rede) ---{COLORS.END}")
        print_menu_option("1", "Ativar Filtro de Pornografia/Malware", color=COLORS.CYAN)
        print_menu_option("2", "Desativar Filtro DNS", color=COLORS.CYAN)
        
        print(f"\n{COLORS.BOLD}--- Bloqueio Específico (manual) ---{COLORS.END}")
        print_menu_option("3", "Bloquear um Domínio", color=COLORS.YELLOW)
        print_menu_option("4", "Desbloquear um Domínio", color=COLORS.YELLOW)
        print_menu_option("5", "Listar Domínios Bloqueados", color=COLORS.YELLOW)
        
        print("")
        print_menu_option("0", "Voltar ao Menu Principal", color=COLORS.GREEN)
        print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * 58}{BoxChars.BOTTOM_RIGHT}")

        choice = input(f"\n{COLORS.BOLD}Escolha uma opção: {COLORS.END}")

        actions = {
            '1': menu_ativar_filtro_dns,
            '2': menu_desativar_filtro_dns,
            '3': menu_bloquear_dominio,
            '4': menu_desbloquear_dominio,
            '5': menu_listar_dominios,
        }

        if choice in actions:
            actions[choice]()
        elif choice == '0':
            break
        else:
            print(f"\n{COLORS.RED}Opção inválida. Tente novamente.{COLORS.END}")
        
        input(f"\n{COLORS.BOLD}Pressione Enter para continuar...{COLORS.END}")

if __name__ == "__main__":
    main_menu()
