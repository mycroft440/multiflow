#!/bin/bash

# MultiFlow - Gerenciador e Instalador de Conexões, Ferramentas e Protocolos
# Versão: 2.1 (Corrigida - Debug)
# Autor: MultiFlow Team

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
readonly OPENVPN_MANAGER_SCRIPT="/usr/local/bin/openvpn_manager.sh"
readonly FERRAMENTAS_OTIMIZACAO_SCRIPT="/usr/local/bin/ferramentas_otimizacao.sh"
readonly SOCKS5_MENU_SCRIPT="/usr/local/bin/rusty_socks_proxy_menu.sh"
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

# Função para verificar conectividade com a internet
check_internet() {
    info_msg "Verificando conectividade com a internet..."
    if curl -s --connect-timeout 10 --max-time 15 --head http://www.google.com | head -n 1 | grep -q "HTTP/[12].* 200"; then
        success_msg "Conectividade com a internet: OK."
        return 0
    else
        warning_msg "Problema de conectividade detectado, mas continuando..."
        return 0
    fi
}

# Função para instalar dependências
install_dependencies() {
    info_msg "Atualizando listas de pacotes e instalando dependências..."
    
    if ! sudo apt update -y; then
        warning_msg "Falha ao atualizar listas de pacotes, mas continuando..."
    fi
    
    if ! sudo apt install -y build-essential curl wget git libssl-dev; then
        error_exit "Falha ao instalar dependências críticas."
    fi
    
    success_msg "Dependências instaladas com sucesso."
}

# Função para instalar Rust e Cargo
install_rust_cargo() {
    info_msg "Verificando instalação do Rust e Cargo..."
    
    if command -v cargo &> /dev/null && command -v rustc &> /dev/null; then
        info_msg "Rust e Cargo já estão instalados."
        return 0
    fi
    
    info_msg "Instalando Rust e Cargo..."
    
    # Baixar e instalar Rust
    if curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; then
        # Carregar ambiente Rust
        if [ -f "$HOME/.cargo/env" ]; then
            source "$HOME/.cargo/env"
        fi
        
        # Verificar se a instalação foi bem-sucedida
        if command -v cargo &> /dev/null; then
            success_msg "Rust e Cargo instalados com sucesso."
            return 0
        else
            error_exit "Rust foi instalado mas cargo não está disponível."
        fi
    else
        error_exit "Falha ao instalar Rust e Cargo."
    fi
}

# Função para instalar o gerenciador de usuários SSH
install_ssh_user_manager() {
    info_msg "Instalando gerenciador de usuários SSH..."
    
    if [[ ! -f "$SCRIPT_DIR/new_ssh_user_management.sh" ]]; then
        error_exit "Arquivo new_ssh_user_management.sh não encontrado em $SCRIPT_DIR."
    fi
    
    if ! sudo mkdir -p "$PROJECT_DIR"; then
        error_exit "Falha ao criar diretório $PROJECT_DIR."
    fi
    
    if ! sudo cp "$SCRIPT_DIR/new_ssh_user_management.sh" "$SSH_USER_MANAGEMENT_SCRIPT"; then
        error_exit "Falha ao copiar script de gerenciamento SSH."
    fi
    
    if ! sudo chmod +x "$SSH_USER_MANAGEMENT_SCRIPT"; then
        error_exit "Falha ao dar permissão de execução ao script SSH."
    fi
    
    success_msg "Gerenciador de usuários SSH instalado."
}

# Função para resolver dependência libssl1.1 para dtproxy
install_libssl1_1() {
    info_msg "Verificando dependência libssl1.1..."
    
    if ldconfig -p | grep -q "libssl.so.1.1"; then
        info_msg "libssl1.1 já está instalada."
        return 0
    fi
    
    info_msg "Tentando instalar libssl1.1..."
    
    # Método 1: Tentar via repositório focal
    if ! grep -q "focal" /etc/apt/sources.list.d/focal.list 2>/dev/null; then
        echo "deb http://security.ubuntu.com/ubuntu focal-security main" | sudo tee /etc/apt/sources.list.d/focal.list > /dev/null
        sudo apt update -qq
    fi
    
    if sudo apt install -y libssl1.1; then
        success_msg "libssl1.1 instalada via repositório."
        return 0
    fi
    
    # Método 2: Download direto
    warning_msg "Tentando método alternativo de instalação..."
    
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
    local libssl_url="http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.20_amd64.deb"
    
    if wget -q "$libssl_url" && sudo dpkg -i *.deb; then
        success_msg "libssl1.1 instalada via download direto."
        rm -rf "$temp_dir"
        return 0
    fi
    
    rm -rf "$temp_dir"
    warning_msg "Não foi possível instalar libssl1.1. O dtproxy pode não funcionar."
    return 1
}

# Função para instalar dtproxy
install_dtproxy() {
    info_msg "Instalando dtproxy..."
    
    local dtproxy_source_dir="$SCRIPT_DIR/dtproxy_project"
    if [[ ! -d "$dtproxy_source_dir" ]]; then
        warning_msg "Diretório dtproxy_project não encontrado. Pulando instalação do dtproxy."
        return 0
    fi
    
    if [[ ! -f "$dtproxy_source_dir/dtproxy_x86_64" ]]; then
        warning_msg "Executável dtproxy_x86_64 não encontrado. Pulando instalação do dtproxy."
        return 0
    fi
    
    install_libssl1_1
    
    if ! sudo mkdir -p "$DTPROXY_DIR"; then
        error_exit "Falha ao criar diretório $DTPROXY_DIR."
    fi
    
    if ! sudo cp "$dtproxy_source_dir/dtproxy_x86_64" "$DTPROXY_DIR/dtproxy_x86_64"; then
        error_exit "Falha ao copiar executável dtproxy."
    fi
    
    if ! sudo chmod +x "$DTPROXY_DIR/dtproxy_x86_64"; then
        error_exit "Falha ao dar permissão de execução ao dtproxy."
    fi
    
    # Instalar menu se disponível
    if [[ -f "$dtproxy_source_dir/dtproxy_menu.sh" ]]; then
        if sudo cp "$dtproxy_source_dir/dtproxy_menu.sh" "/usr/local/bin/dtproxy_menu" && sudo chmod +x "/usr/local/bin/dtproxy_menu"; then
            success_msg "Menu dtproxy instalado."
        fi
    fi
    
    success_msg "dtproxy instalado com sucesso."
}

# Função para instalar OpenVPN Manager
install_openvpn_manager() {
    info_msg "Instalando OpenVPN Manager..."
    
    if [[ ! -f "$SCRIPT_DIR/openvpn_manager.sh" ]]; then
        warning_msg "Arquivo openvpn_manager.sh não encontrado. Pulando instalação."
        return 0
    fi
    
    if ! sudo cp "$SCRIPT_DIR/openvpn_manager.sh" "$OPENVPN_MANAGER_SCRIPT"; then
        error_exit "Falha ao copiar script openvpn_manager.sh."
    fi
    
    if ! sudo chmod +x "$OPENVPN_MANAGER_SCRIPT"; then
        error_exit "Falha ao dar permissão de execução ao openvpn_manager.sh."
    fi
    
    success_msg "OpenVPN Manager instalado com sucesso."
}

# Função para instalar Ferramentas de Otimização
install_ferramentas_otimizacao() {
    info_msg "Instalando Ferramentas de Otimização..."
    
    if [[ ! -f "$SCRIPT_DIR/ferramentas_otimizacao.sh" ]]; then
        warning_msg "Arquivo ferramentas_otimizacao.sh não encontrado. Pulando instalação."
        return 0
    fi
    
    if ! sudo cp "$SCRIPT_DIR/ferramentas_otimizacao.sh" "$FERRAMENTAS_OTIMIZACAO_SCRIPT"; then
        error_exit "Falha ao copiar script ferramentas_otimizacao.sh."
    fi
    
    if ! sudo chmod +x "$FERRAMENTAS_OTIMIZACAO_SCRIPT"; then
        error_exit "Falha ao dar permissão de execução ao ferramentas_otimizacao.sh."
    fi
    
    success_msg "Ferramentas de Otimização instaladas com sucesso."
}

# Função para instalar o menu SOCKS5
install_socks5_menu() {
    info_msg "Instalando menu SOCKS5..."
    
    if [[ ! -f "$SCRIPT_DIR/rusty_socks_proxy_menu.sh" ]]; then
        warning_msg "Arquivo rusty_socks_proxy_menu.sh não encontrado. Pulando instalação."
        return 0
    fi
    
    if ! sudo cp "$SCRIPT_DIR/rusty_socks_proxy_menu.sh" "$SOCKS5_MENU_SCRIPT"; then
        error_exit "Falha ao copiar script rusty_socks_proxy_menu.sh."
    fi
    
    if ! sudo chmod +x "$SOCKS5_MENU_SCRIPT"; then
        error_exit "Falha ao dar permissão de execução ao rusty_socks_proxy_menu.sh."
    fi
    
    success_msg "Menu SOCKS5 instalado com sucesso."
}

# Função para instalar SOCKS5
install_socks5_proxy() {
    info_msg "Instalando SOCKS5 Proxy..."
    
    local SOCKS5_EXEC="$PROJECT_DIR/rusty_socks_proxy"
    local SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
    
    if [[ -f "$SOCKS5_EXEC" ]]; then
        warning_msg "SOCKS5 já parece estar instalado."
        return 0
    fi
    
    if [[ ! -f "$SCRIPT_DIR/Cargo.toml" ]]; then
        error_exit "Arquivo Cargo.toml não encontrado em $SCRIPT_DIR."
    fi
    
    info_msg "Compilando o projeto Rust para SOCKS5..."
    
    # Carregar ambiente Rust se necessário
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
    
    cd "$SCRIPT_DIR"
    if ! cargo build --release; then
        error_exit "Falha ao compilar o projeto Rust."
    fi
    
    if [[ ! -f "$SCRIPT_DIR/target/release/rusty_socks_proxy" ]]; then
        error_exit "Executável rusty_socks_proxy não foi gerado."
    fi
    
    info_msg "Copiando executável para $PROJECT_DIR..."
    if ! sudo cp "$SCRIPT_DIR/target/release/rusty_socks_proxy" "$SOCKS5_EXEC"; then
        error_exit "Falha ao copiar executável rusty_socks_proxy."
    fi
    
    info_msg "Instalando serviço systemd..."
    if [[ -f "$SCRIPT_DIR/rusty_socks_proxy.service" ]]; then
        if sudo cp "$SCRIPT_DIR/rusty_socks_proxy.service" "$SOCKS5_SERVICE_FILE"; then
            sudo systemctl daemon-reload
            sudo systemctl enable rusty_socks_proxy
            
            if sudo systemctl start rusty_socks_proxy; then
                sleep 2
                if sudo systemctl is-active --quiet rusty_socks_proxy; then
                    success_msg "SOCKS5 instalado e iniciado com sucesso na porta 1080."
                else
                    warning_msg "SOCKS5 instalado mas falha ao iniciar serviço."
                fi
            else
                warning_msg "SOCKS5 instalado mas falha ao iniciar."
            fi
        else
            warning_msg "Falha ao instalar arquivo de serviço systemd."
        fi
    else
        warning_msg "Arquivo de serviço systemd não encontrado."
    fi
}

# Função principal
main() {
    info_msg "=== Iniciando instalação do MultiFlow ==="
    
    check_internet
    install_dependencies
    install_rust_cargo
    install_ssh_user_manager
    install_dtproxy
    install_openvpn_manager
    install_ferramentas_otimizacao
    install_socks5_menu
    install_socks5_proxy
    
    # Criar link simbólico para o menu
    info_msg "Criando link simbólico para o menu..."
    if [[ -f "$SCRIPT_DIR/menu.sh" ]]; then
        if sudo ln -sf "$SCRIPT_DIR/menu.sh" /usr/local/bin/menu && sudo chmod +x /usr/local/bin/menu; then
            success_msg "Link simbólico criado. Agora você pode acessar o menu digitando 'menu'."
        else
            warning_msg "Falha ao criar link simbólico para o menu."
        fi
    else
        warning_msg "Arquivo menu.sh não encontrado."
    fi
    
    success_msg "=== Instalação do MultiFlow concluída ==="
}

# Executar função principal
main "$@"
