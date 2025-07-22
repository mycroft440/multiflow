#!/bin/bash

# Caminho base para os scripts do multiflow
MULTIFLOW_BASE_PATH="/home/ubuntu/home/ubuntu/multiflow-main/multiflow-main"

# Função para mostrar status dos serviços
show_status() {
    clear
    echo "Mostrando status dos serviços... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script para mostrar status dos serviços
    # ${MULTIFLOW_BASE_PATH}/status_checker.sh
    echo "Pressione qualquer tecla para voltar ao menu principal..."; read -n 1;
    show_main_menu
}

# Função para remover o script e reverter alterações (exceto dependências)
remove_script_and_revert_changes() {
    clear
    echo "========================================"
    echo "  REMOVER SCRIPT E REVERTER ALTERAÇÕES"
    echo "========================================"
    echo "Esta opção irá remover os arquivos do MultiFlow e reverter algumas alterações."
    echo "As dependências do sistema (como Rust, Cargo, etc.) NÃO serão removidas."
    echo ""
    read -p "Tem certeza que deseja continuar? (s/N): " confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        echo "Operação cancelada."
        read -p "Pressione Enter para voltar ao menu principal..."; read -n 1;
        show_main_menu
        return
    fi

    echo "Removendo arquivos do MultiFlow..."
    sudo rm -rf "/opt/rusty_socks_proxy"
    sudo rm -rf "/opt/dtproxy"
    sudo rm -f "/usr/local/bin/dtproxy_menu"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/new_ssh_user_management.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/openvpn_manager.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/menu.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/install_fixed.sh"
    sudo rm -rf "${MULTIFLOW_BASE_PATH}"

    echo "Alterações revertidas com sucesso. O MultiFlow foi removido do seu sistema."
    echo "Você pode precisar remover manualmente as dependências instaladas se desejar."
    echo ""
    echo "O script será encerrado agora."
    exit 0
}

# Função para exibir o menu principal
show_main_menu() {
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
    echo "2. Gerenciar Conexões"
    echo "3. Status dos Serviços"
    echo "4. Ferramentas (Limpeza e Performance)"
    echo "5. Remover Script e reverter alteraçoes"
    echo "0. Sair"
    echo ""
    read -p "Digite sua opcao: " main_choice
    case $main_choice in
        1) manage_ssh_users ;;
        2) manage_connections ;;
        3) show_status ;;
        4) optimization_tools ;;
        5) remove_script_and_revert_changes ;;
        0) exit 0 ;;
        *) echo "Opcao invalida. Pressione qualquer tecla para continuar..."; read -n 1; show_main_menu ;;
    esac
}

# Função para gerenciar usuários SSH
manage_ssh_users() {
    clear
    echo "========================================"
    echo "       GERENCIAR USUARIOS SSH"
    echo "========================================"
    echo "1. Criar Novo Usuario"
    echo "2. Remover Usuario Existente"
    echo "3. Listar Usuarios"
    echo "4. Monitorar Usuarios Online"
    echo "5. Voltar ao Menu Principal"
    echo ""
    read -p "Digite sua opcao: " ssh_choice
    case $ssh_choice in
        1) ${MULTIFLOW_BASE_PATH}/new_ssh_user_management.sh add ;;
        2) ${MULTIFLOW_BASE_PATH}/new_ssh_user_management.sh remove ;;
        3) ${MULTIFLOW_BASE_PATH}/new_ssh_user_management.sh list ;;
        4) monitor_online_users ;;
        5) show_main_menu ;;
        *) echo "Opcao invalida. Pressione qualquer tecla para continuar..."; read -n 1; manage_ssh_users ;;
    esac
    echo "Pressione qualquer tecla para voltar ao menu de usuarios SSH..."; read -n 1;
    manage_ssh_users
}

# Função para gerenciar conexões
manage_connections() {
    clear
    echo "========================================"
    echo "       GERENCIAR CONEXOES"
    echo "========================================"
    echo "1. Gerenciar Socks5 (semi-puro customizado)"
    echo "2. Gerenciar Dtproxy (1.2.6)"
    echo "3. Gerenciar OpenVPN"
    echo "4. Voltar ao Menu Principal"
    echo ""
    read -p "Digite sua opcao: " conn_choice
    case $conn_choice in
        1) manage_socks5 ;;
        2) manage_dtproxy ;;
        3) manage_openvpn ;;
        4) show_main_menu ;;
        *) echo "Opcao invalida. Pressione qualquer tecla para continuar..."; read -n 1; manage_connections ;;
    esac
    echo "Pressione qualquer tecla para voltar ao menu de conexoes..."; read -n 1;
    manage_connections
}

# Funções placeholder para outras opções do menu principal
monitor_online_users() {
    clear
    echo "Monitorando usuarios online... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script existente para monitorar usuarios
    # ${MULTIFLOW_BASE_PATH}/monitor_users.sh
    echo "Pressione qualquer tecla para voltar ao menu de usuarios SSH..."; read -n 1;
    manage_ssh_users
}

optimization_tools() {
    clear
    echo "Ferramentas de otimizacao... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script para ferramentas de otimizacao
    # ${MULTIFLOW_BASE_PATH}/optimization.sh
    echo "Pressione qualquer tecla para voltar ao menu principal..."; read -n 1;
    show_main_menu
}

# Função para gerenciar Socks5
manage_socks5() {
    clear
    echo "Gerenciando Socks5... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script para gerenciar Socks5
    # ${MULTIFLOW_BASE_PATH}/socks5_manager.sh
    echo "Pressione qualquer tecla para voltar ao menu de conexoes..."; read -n 1;
    manage_connections
}

# Função para gerenciar Dtproxy
manage_dtproxy() {
    clear
    echo "Gerenciando Dtproxy... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script para gerenciar Dtproxy
    # ${MULTIFLOW_BASE_PATH}/dtproxy_manager.sh
    echo "Pressione qualquer tecla para voltar ao menu de conexoes..."; read -n 1;
    manage_connections
}

# Função para gerenciar OpenVPN
manage_openvpn() {
    ${MULTIFLOW_BASE_PATH}/openvpn_manager.sh
    echo "Pressione qualquer tecla para voltar ao menu de conexoes..."; read -n 1;
    manage_connections
}

# Iniciar o menu
show_main_menu



# Função para mostrar status dos serviços
show_status() {
    clear
    echo "Mostrando status dos serviços... (Funcionalidade a ser implementada ou integrada)"
    # Exemplo: chamar um script para mostrar status dos serviços
    # ${MULTIFLOW_BASE_PATH}/status_checker.sh
    echo "Pressione qualquer tecla para voltar ao menu principal..."; read -n 1;
    show_main_menu
}




# Função para remover o script e reverter alterações (exceto dependências)
remove_script_and_revert_changes() {
    clear
    echo "========================================"
    echo "  REMOVER SCRIPT E REVERTER ALTERAÇÕES"
    echo "========================================"
    echo "Esta opção irá remover os arquivos do MultiFlow e reverter algumas alterações."
    echo "As dependências do sistema (como Rust, Cargo, etc.) NÃO serão removidas."
    echo ""
    read -p "Tem certeza que deseja continuar? (s/N): " confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        echo "Operação cancelada."
        read -p "Pressione Enter para voltar ao menu principal..."; read -n 1;
        show_main_menu
        return
    fi

    echo "Removendo arquivos do MultiFlow..."
    sudo rm -rf "/opt/rusty_socks_proxy"
    sudo rm -rf "/opt/dtproxy"
    sudo rm -f "/usr/local/bin/dtproxy_menu"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/new_ssh_user_management.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/openvpn_manager.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/menu.sh"
    sudo rm -f "${MULTIFLOW_BASE_PATH}/install_fixed.sh"
    sudo rm -rf "${MULTIFLOW_BASE_PATH}"

    echo "Alterações revertidas com sucesso. O MultiFlow foi removido do seu sistema."
    echo "Você pode precisar remover manualmente as dependências instaladas se desejar."
    echo ""
    echo "O script será encerrado agora."
    exit 0
}


