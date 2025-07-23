```bash
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

# Função para verificar status dos serviços
check_services_status() {
    clear
    echo -e "${BLUE}=== Status dos Serviços ===${NC}"
    echo ""

    local services=("rusty_socks_proxy" "openvpn@server")
    local service_status

    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            service_status="${GREEN}Ativo${NC}"
        else
            service_status="${RED}Inativo${NC}"
        fi
        printf "%-30s: %s\n" "$service" "$service_status"
    done

    # Verificar dtproxy (assumindo que é um processo, não um serviço systemd)
    if pgrep -f "dtproxy_x86_64" > /dev/null; then
        dtproxy_status="${GREEN}Ativo${NC}"
    else
        dtproxy_status="${RED}Inativo${NC}"
    fi
    printf "%-30s: %s\n" "dtproxy" "$dtproxy_status"

    echo ""
    read -p "Pressione Enter para continuar..."
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
            1)
                if [[ -f "/opt/rusty_socks_proxy/new_ssh_user_management.sh" ]]; then
                    sudo /opt/rusty_socks_proxy/new_ssh_user_management.sh
                else
                    error_exit "Script new_ssh_user_management.sh não encontrado em /opt/rusty_socks_proxy."
                fi
                ;;
            2)
                if [[ -f "/usr/local/bin/dtproxy_menu" ]]; then
                    sudo /usr/local/bin/dtproxy_menu
                else
                    error_exit "Script dtproxy_menu não encontrado em /usr/local/bin."
                fi
                ;;
            3)
                if [[ -f "/usr/local/bin/rusty_socks_proxy_menu.sh" ]]; then
                    sudo /usr/local/bin/rusty_socks_proxy_menu.sh
                else
                    error_exit "Script rusty_socks_proxy_menu.sh não encontrado em /usr/local/bin."
                fi
                ;;
            4)
                if [[ -f "/usr/local/bin/openvpn_manager.sh" ]]; then
                    sudo /usr/local/bin/openvpn_manager.sh
                else
                    error_exit "Script openvpn_manager.sh não encontrado em /usr/local/bin."
                fi
                ;;
            5)
                if [[ -f "/usr/local/bin/ferramentas_otimizacao.sh" ]]; then
                    sudo /usr/local/bin/ferramentas_otimizacao.sh
                else
                    error_exit "Script ferramentas_otimizacao.sh não encontrado em /usr/local/bin."
                fi
                ;;
            6)
                check_services_status
                ;;
            0)
                exit 0
                ;;
            *)
                warning_msg "Opção invalida. Pressione qualquer tecla para continuar..."
                read -n 1
                ;;
        esac
    done
}

# Iniciar o menu
main_menu
```
