#!/bin/bash
set -x

# MultiFlow - Gerenciador e Instalador de Conexões, Ferramentas e Protocolos
# Versão: 2.0 (Corrigida)
# Autor: MultiFlow Team

set -euo pipefail  # Modo strict para bash

# Cores para a saída do terminal
readonly GREEN="\033[1;32m"
readonly YELLOW="\033[1;33m"
readonly RED="\033[1;31m"
readonly BLUE="\033[1;34m"
readonly NC="\033[0m"

# Configurações globais
readonly PROJECT_DIR="/opt/rusty_socks_proxy"
readonly DTPROXY_DIR="/opt/dtproxy"
readonly SSH_USER_MANAGEMENT_SCRIPT="/opt/rusty_socks_proxy/new_ssh_user_management.sh"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Função para verificar se o script está sendo executado como root
# check_root() {
#     if [[ $EUID -ne 0 ]]; then
#         error_exit "Este script deve ser executado como root (use sudo)."
#     fi

# Função para verificar conectividade com a internet
check_internet() {
    info_msg "Verificando conectividade com a internet..."
    if ping -c 1 google.com &> /dev/null; then
        success_msg "Conectividade com a internet: OK."
    else
        error_exit "Sem conexão com a internet. Verifique sua rede."
    fi
}

# Função para instalar dependências
install_dependencies() {
    info_msg "Atualizando listas de pacotes e instalando dependências..."
    sudo apt update -y || error_exit "Falha ao atualizar listas de pacotes."
    sudo apt install -y build-essential curl wget git libssl-dev || error_exit "Falha ao instalar dependências."
    success_msg "Dependências instaladas com sucesso."
}

# Função para instalar Rust e Cargo
install_rust_cargo() {
    info_msg "Instalando Rust e Cargo..."
    if command -v cargo &> /dev/null; then
        info_msg "Rust e Cargo já estão instalados."
        return 0
    fi
    
    curl --proto \"=https\" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || error_exit "Falha ao instalar Rust e Cargo."
    source "$HOME/.cargo/env"
    success_msg "Rust e Cargo instalados com sucesso."
}

# Função para instalar o gerenciador de usuários SSH
install_ssh_user_manager() {
    info_msg "Instalando gerenciador de usuários SSH..."
    
    if [[ ! -f "$SCRIPT_DIR/new_ssh_user_management.sh" ]]; then
        error_exit "Arquivo new_ssh_user_management.sh não encontrado."
    fi
    
    sudo cp "$SCRIPT_DIR/new_ssh_user_management.sh" "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao copiar script."
    sudo chmod +x "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao dar permissão de execução."
    
    success_msg "Gerenciador de usuários SSH instalado."
}


# Função para resolver dependência libssl1.1 para dtproxy
install_libssl1_1() {
    info_msg "Verificando dependência libssl1.1..."
    
    # Verificar se já está instalada
    if ldconfig -p | grep -q "libssl.so.1.1"; then
        info_msg "libssl1.1 já está instalada."
        return 0
    fi
    
    info_msg "Instalando libssl1.1 para compatibilidade com dtproxy..."
    
    # Tentar instalar via repositório focal (Ubuntu 20.04)
    if ! sudo grep -q "focal" /etc/apt/sources.list.d/focal.list 2>/dev/null; then
        sudo echo "deb http://security.ubuntu.com/ubuntu focal-security main" | sudo tee /etc/apt/sources.list.d/focal.list > /dev/null
        sudo apt update -qq
    fi
    
    if sudo apt install -y libssl1.1; then
        success_msg "libssl1.1 instalada com sucesso."
        return 0
    fi
    
    # Método alternativo: download direto
    warning_msg "Tentando método alternativo de instalação..."
    
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
    # URLs para os pacotes .deb
    local libssl_url="http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.20_amd64.deb"
    
    if wget -q "$libssl_url"; then
        if sudo dpkg -i *.deb; then
            success_msg "libssl1.1 instalada via download direto."
            rm -rf "$temp_dir"
            return 0
        fi
    fi
    
    rm -rf "$temp_dir"
    warning_msg "Não foi possível instalar libssl1.1. O dtproxy pode não funcionar corretamente."
    return 1
}

# Função para instalar dtproxy
install_dtproxy() {
    clear
    echo -e "${BLUE}--- Instalar dtproxy (mod mycroft) ---${NC}"
    
    # Verificar se os arquivos do dtproxy existem
    local dtproxy_source_dir="$SCRIPT_DIR/dtproxy_project"
    if [[ ! -d "$dtproxy_source_dir" ]]; then
        error_exit "Diretório dtproxy_project não encontrado."
    fi
    
    # Instalar dependência libssl1.1
    install_libssl1_1
    
    info_msg "Instalando dtproxy..."
    
    # Criar diretório de instalação
    sudo mkdir -p "$DTPROXY_DIR" || error_exit "Falha ao criar diretório $DTPROXY_DIR."
    
    # Copiar executável
    sudo cp "$dtproxy_source_dir/dtproxy_x86_64" "$DTPROXY_DIR/dtproxy_x86_64" || error_exit "Falha ao copiar executável dtproxy."
    sudo chmod +x "$DTPROXY_DIR/dtproxy_x86_64" || error_exit "Falha ao dar permissão de execução ao dtproxy."
    
    # Copiar script de menu
    sudo cp "$dtproxy_source_dir/dtproxy_menu_fixed.sh" "/usr/local/bin/dtproxy_menu" || error_exit "Falha ao copiar script de menu dtproxy."
    sudo chmod +x "/usr/local/bin/dtproxy_menu" || error_exit "Falha ao dar permissão de execução ao script de menu dtproxy."
    
    success_msg "dtproxy instalado com sucesso."
}


# Função para gerenciar OpenVPN (stub)
manage_openvpn() {
    info_msg "Gerenciando OpenVPN... (Funcionalidade a ser implementada)"
    read -p "Pressione Enter para continuar..."
}



# Função para o menu de gerenciamento do SOCKS5


# Função para instalar SOCKS5
install_socks5_proxy() {
    clear
    echo -e "${BLUE}--- Instalar SOCKS5 ---${NC}"
    
    local SOCKS5_DIR="/opt/rusty_socks_proxy"
    local SOCKS5_EXEC="$SOCKS5_DIR/rusty_socks_proxy"
    local SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
    
    if [[ -f "$SOCKS5_EXEC" ]]; then
        warning_msg "SOCKS5 já parece estar instalado."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    info_msg "Compilando o projeto Rust para SOCKS5..."
    (cd "$SCRIPT_DIR" && cargo build --release)
    
    if [[ $? -ne 0 ]]; then
        error_exit "Falha ao compilar o projeto Rust."
    fi
    
    info_msg "Criando diretório de instalação: $SOCKS5_DIR..."
    sudo mkdir -p "$SOCKS5_DIR"
    
    info_msg "Copiando executável para $SOCKS5_DIR..."
    sudo cp "$SCRIPT_DIR/target/release/rusty_socks_proxy" "$SOCKS5_EXEC"
    
    info_msg "Copiando arquivo de serviço systemd..."
    sudo cp "$SCRIPT_DIR/rusty_socks_proxy.service" "$SOCKS5_SERVICE_FILE"
    
    info_msg "Recarregando daemon systemd, habilitando e iniciando serviço SOCKS5..."
    sudo systemctl daemon-reload
    sudo systemctl enable rusty_socks_proxy
    sudo systemctl start rusty_socks_proxy
    
    sleep 2
    
    if sudo systemctl is-active --quiet rusty_socks_proxy; then
        success_msg "SOCKS5 instalado e iniciado com sucesso na porta 1080."
    else
        error_exit "Falha ao iniciar o serviço SOCKS5. Verifique os logs com \"journalctl -u rusty_socks_proxy\"."
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para alterar porta do SOCKS5
alter_socks5_port_proxy() {
    clear
    echo -e "${BLUE}--- Alterar Porta SOCKS5 ---${NC}"
    
    local SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
    
    if [[ ! -f "$SOCKS5_SERVICE_FILE" ]]; then
        error_exit "Serviço SOCKS5 não encontrado. Instale-o primeiro."
    fi
    
    current_port=$(grep -oP \"Environment=\"SOCKS5_PORT=\\K[0-9]+\"\" "$SOCKS5_SERVICE_FILE")
    info_msg "Porta atual do SOCKS5: ${current_port:-1080}"
    
    read -p "Digite a nova porta para o SOCKS5: " new_port
    
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [[ "$new_port" -lt 1024 ]] || [[ "$new_port" -gt 65535 ]]; then
        error_exit "Porta inválida. Use uma porta entre 1024 e 65535."
    fi
    
    info_msg "Parando serviço SOCKS5..."
    sudo systemctl stop rusty_socks_proxy
    
    info_msg "Alterando porta no arquivo de serviço..."
    sudo sed -i "s/^Environment=\"SOCKS5_PORT=[0-9]*\"/Environment=\"SOCKS5_PORT=$new_port\"/" "$SOCKS5_SERVICE_FILE"
    
    info_msg "Recarregando daemon systemd e iniciando serviço SOCKS5 com a nova porta..."
    sudo systemctl daemon-reload
    sudo systemctl start rusty_socks_proxy
    
    sleep 2
    
    if sudo systemctl is-active --quiet rusty_socks_proxy; then
        success_msg "SOCKS5 reiniciado com sucesso na porta $new_port."
    else
        error_exit "Falha ao reiniciar o serviço SOCKS5 na porta $new_port. Verifique os logs."
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para abrir porta do SOCKS5
open_socks5_port_proxy() {
    clear
    echo -e "${BLUE}--- Abrir Porta SOCKS5 ---${NC}"
    
    local SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
    
    if [[ ! -f "$SOCKS5_SERVICE_FILE" ]]; then
        error_exit "Serviço SOCKS5 não encontrado. Instale-o primeiro."
    fi
    
    current_port=$(grep -oP \"Environment=\"SOCKS5_PORT=\\K[0-9]+\"\" "$SOCKS5_SERVICE_FILE")
    port=${current_port:-1080}
    
    info_msg "Abrindo porta $port no firewall (UFW)..."
    
    # Verificar se UFW está instalado
    if ! command -v ufw &> /dev/null; then
        warning_msg "UFW não está instalado. Instalando..."
        sudo apt update && sudo apt install -y ufw
    fi
    
    # Abrir a porta no UFW
    sudo ufw allow $port/tcp
    
    success_msg "Porta $port aberta no firewall."
    
    info_msg "Verificando se o serviço SOCKS5 está rodando..."
    if sudo systemctl is-active --quiet rusty_socks_proxy; then
        success_msg "Serviço SOCKS5 está ativo na porta $port."
    else
        warning_msg "Serviço SOCKS5 não está ativo. Iniciando..."
        sudo systemctl start rusty_socks_proxy
        if sudo systemctl is-active --quiet rusty_socks_proxy; then
            success_msg "Serviço SOCKS5 iniciado na porta $port."
        else
            error_exit "Falha ao iniciar o serviço SOCKS5."
        fi
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para remover SOCKS5
remove_socks5_proxy() {
    clear
    echo -e "${BLUE}--- Remover SOCKS5 ---${NC}"
    
    local SOCKS5_DIR="/opt/rusty_socks_proxy"
    local SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
    
    echo -e "${RED}ATENÇÃO:${NC} Esta ação irá:"
    echo "- Parar o serviço SOCKS5"
    echo "- Remover o diretório $SOCKS5_DIR"
    echo "- Remover o arquivo de serviço systemd"
    echo "- Desabilitar o serviço"
    echo ""
    
    read -p "Deseja continuar? (s/N): " confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        echo "Operação cancelada."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    info_msg "Parando serviço SOCKS5..."
    sudo systemctl stop rusty_socks_proxy 2>/dev/null || true
    
    info_msg "Desabilitando serviço SOCKS5..."
    sudo systemctl disable rusty_socks_proxy 2>/dev/null || true
    
    info_msg "Removendo arquivo de serviço systemd..."
    sudo rm -f "$SOCKS5_SERVICE_FILE"
    
    info_msg "Recarregando daemon systemd..."
    sudo systemctl daemon-reload
    
    info_msg "Removendo diretório $SOCKS5_DIR..."
    sudo rm -rf "$SOCKS5_DIR"
    
    success_msg "SOCKS5 removido completamente."
    read -p "Pressione Enter para continuar..."
}

# Função para o menu de gerenciamento do dtproxy
dtproxy_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== Gerenciar dtproxy ===${NC}"
        echo "1. Iniciar dtproxy"
        echo "2. Gerenciar Portas"
        echo "3. Status do dtproxy"
        echo "4. Parar todos os dtproxy"
        echo "5. Remover dtproxy"
        echo "0. Voltar ao Menu Anterior"
        echo ""
        read -p "Escolha uma opção: " dtproxy_choice

        case $dtproxy_choice in
            1) /usr/local/bin/dtproxy_menu start_dtproxy_menu ;;
            2) /usr/local/bin/dtproxy_menu port_management_menu ;;
            3) /usr/local/bin/dtproxy_menu show_dtproxy_status ;;
            4) /usr/local/bin/dtproxy_menu stop_all_dtproxy ;;
            5) /usr/local/bin/dtproxy_menu remove_dtproxy ;;
            0) break ;;
            *)
                warning_msg "Opção inválate. Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}






