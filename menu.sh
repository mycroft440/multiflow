#!/bin/bash

# MultiFlow - Menu Principal
# Versão: 2.0 (Corrigida)
# Autor: MultiFlow Team

set -euo pipefail  # Modo strict para bash

# Cores para a saída do terminal
readonly GREEN="\033[1;32m"
readonly YELLOW="\033[1;33m"
readonly RED="\033[1;31m"
readonly BLUE="\033[1;34m"
readonly NC="\033[0m"

# Função para exibir mensagens de erro e sair
error_exit() {
    echo -e "${RED}[ERRO]${NC} $1" >&2
    exit 1
}

# Função para exibir mensagens de informação
info_msg() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Função para exibir mensagens de sucesso
success_msg() {
    echo -e "${GREEN}[SUCESSO]${NC} $1"
}

# Função para exibir mensagens de aviso
warning_msg() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

# Função para exibir o menu principal
main_menu() {
    while true; do
        clear
        echo "
    __  _____  ____  __________________    ____ _       __
   /  |/  / / / / / /_  __/  _/ ____/ /   / __ \ |     / /
  / /|_/ / / / / /   / /  / // /_  / /   / / / / | /| / / 
 / /  / / /_/ / /___/ / _/ // __/ / /___/ /_/ /| |/ |/ /  
/_/  /_/\____/_____/_/ /___/_/   /_____/\____/ |__/|__/   
                                                          
"
        echo "========================================"
        echo "          MENU PRINCIPAL MULTIFLOW"
        echo "========================================"
        echo "1. Gerenciar Usuários SSH"
        echo "2. Gerenciar Dtproxy"
        echo "3. Gerenciar SOCKS5"
        echo "4. Gerenciar OpenVPN"
        echo "5. Ferramentas (Limpeza e Performance)"
        echo "6. Status dos Serviços"
        echo "0. Sair"
        echo ""
        read -p "Digite sua opcao: " main_choice
        case $main_choice in
            1) sudo /opt/rusty_socks_proxy/new_ssh_user_management.sh ;;
            2) sudo /usr/local/bin/dtproxy_menu ;;
            3) sudo /usr/local/bin/rusty_socks_proxy_menu.sh ;;
            4) sudo /usr/local/bin/openvpn_manager.sh ;;
            5) sudo /usr/local/bin/ferramentas_otimizacao.sh ;;
            6) info_msg "Mostrando status dos servicos... (Funcionalidade a ser implementada)"; read -p "Pressione Enter para continuar..."; ;;
            0) exit 0 ;;
            *)
                warning_msg "Opcao invalida. Pressione qualquer tecla para continuar...";
                read -n 1;
                ;;
        esac
    done
}

# Iniciar o menu
main_menu
