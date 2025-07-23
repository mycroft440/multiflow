```bash
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
    if curl -s --head http://www.google.com | head -n 1 | grep "HTTP/[12].* 200" > /dev/null; then
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
    
    curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y || error_exit "Falha ao instalar Rust e Cargo."
    source "$HOME/.cargo/env"
    success_msg "Rust e Cargo instalados com sucesso."
}

# Função para instalar o gerenciador de usuários SSH
install_ssh_user_manager() {
    info_msg "Instalando gerenciador de usuários SSH..."
    
    if [[ ! -f "$SCRIPT_DIR/new_ssh_user_management.sh" ]]; then
        error_exit "Arquivo new_ssh_user_management.sh não encontrado em $SCRIPT_DIR."
    fi
    
    sudo mkdir -p "$PROJECT_DIR" || error_exit "Falha ao criar diretório $PROJECT_DIR."
    sudo cp "$SCRIPT_DIR/new_ssh_user_management.sh" "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao copiar script."
    sudo chmod +x "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao dar permissão de execução."
    
    success_msg "Gerenciador de usuários SSH instalado."
}

# Função para resolver dependência libssl1.1 para dtproxy
install_libssl1_1() {
    info_msg "Verificando dependência libssl1.1..."
    
    if ldconfig -p | grep -q "libssl.so.1.1"; then
        info_msg "libssl1.1 já está instalada."
        return 0
    fi
    
    info_msg "Instalando libssl1.1 para compatibilidade com dtproxy..."
    
    if ! sudo grep -q "focal" /etc/apt/sources.list.d/focal.list 2>/dev/null; then
        sudo echo "deb http://security.ubuntu.com/ubuntu focal-security main" | sudo tee /etc/apt/sources.list.d/focal.list > /dev/null
        sudo apt update -qq
    fi
    
    if sudo apt install -y libssl1.1; then
        success_msg "libssl1.1 instalada com sucesso."
        return 0
    fi
    
    warning_msg "Tentando método alternativo de instalação..."
    
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
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
    
    local dtproxy_source_dir="$SCRIPT_DIR/dtproxy_project"
    if [[ ! -d "$dtproxy_source_dir" ]]; then
        error_exit "Diretório dtproxy_project não encontrado em $SCRIPT_DIR."
    fi
    
    if [[ ! -f "$dtproxy_source_dir/dtproxy_x86_64" || ! -f "$dtproxy_source_dir/dtproxy_menu.sh" ]]; then
        error_exit "Arquivos dtproxy_x86_64 ou dtproxy_menu.sh não encontrados em $dtproxy_source_dir."
    fi
    
    install_libssl1_1
    
    info_msg "Instalando dtproxy..."
    
    sudo mkdir -p "$DTPROXY_DIR" || error_exit "Falha ao criar diretório $DTPROXY_DIR."
    
    sudo cp "$dtproxy_source_dir/dtproxy_x86_64" "$DTPROXY_DIR/dtproxy_x86_64" || error_exit "Falha ao copiar executável dtproxy."
    sudo chmod +x "$DTPROXY_DIR/dtproxy_x86_64" || error_exit "Falha ao dar permissão de execução ao dtproxy."
    
    sudo cp "$dtproxy_source_dir/dtproxy_menu.sh" "/usr/local/bin/dtproxy_menu" || error_exit "Falha ao copiar script de menu dtproxy."
    sudo chmod +x "/usr/local/bin/dtproxy_menu" || error_exit "Falha ao dar permissão de execução ao script de menu dtproxy."
    
    success_msg "dtproxy instalado com sucesso."
}

# Função para instalar OpenVPN Manager
install_openvpn_manager() {
    info_msg "Instalando OpenVPN Manager..."
    if [[ ! -f "$SCRIPT_DIR/openvpn_manager.sh" ]]; then
        error_exit "Arquivo openvpn_manager.sh não encontrado em $SCRIPT_DIR."
    fi
    sudo cp "$SCRIPT_DIR/openvpn_manager.sh" "$OPENVPN_MANAGER_SCRIPT" || error_exit "Falha ao copiar script openvpn_manager.sh."
    sudo chmod +x "$OPENVPN_MANAGER_SCRIPT" || error_exit "Falha ao dar permissão de execução ao openvpn_manager.sh."
    success_msg "OpenVPN Manager instalado com sucesso."
}

# Função para instalar Ferramentas de Otimização
install_ferramentas_otimizacao() {
    info_msg "Instalando Ferramentas de Otimização..."
    if [[ ! -f "$SCRIPT_DIR/ferramentas_otimizacao.sh" ]]; then
        error_exit "Arquivo ferramentas_otimizacao.sh não encontrado em $SCRIPT_DIR."
    fi
    sudo cp "$SCRIPT_DIR/ferramentas_otimizacao.sh" "$FERRAMENTAS_OTIMIZACAO_SCRIPT" || error_exit "Falha ao copiar script ferramentas_otimizacao.sh."
    sudo chmod +x "$FERRAMENTAS_OTIMIZACAO_SCRIPT" || error_exit "Falha ao dar permissão de execução ao ferramentas_otimizacao.sh."
    success_msg "Ferramentas de Otimização instaladas com sucesso."
}

# Função para instalar o menu SOCKS5
install_socks5_menu() {
    info_msg "Instalando menu SOCKS5..."
    if [[ ! -f "$SCRIPT_DIR/rusty_socks_proxy_menu.sh" ]]; then
        error_exit "Arquivo rusty_socks_proxy_menu.sh não encontrado em $SCRIPT_DIR."
    fi
    sudo cp "$SCRIPT_DIR/rusty_socks_proxy_menu.sh" "$SOCKS5_MENU_SCRIPT" || error_exit "Falha ao copiar script rusty_socks_proxy_menu.sh."
    sudo chmod +x "$SOCKS5_MENU_SCRIPT" || error_exit "Falha ao dar permissão de execução ao rusty_socks_proxy_menu.sh."
    success_msg "Menu SOCKS5 instalado com sucesso."
}

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
    
    if [[ ! -f "$SCRIPT_DIR/Cargo.toml" ]]; then
        error_exit "Arquivo Cargo.toml não encontrado em $SCRIPT_DIR."
    fi
    
    info_msg "Compilando o projeto Rust para SOCKS5..."
    (cd "$SCRIPT_DIR" && cargo build --release)
    
    if [[ $? -ne 0 ]]; then
        error_exit "Falha ao compilar o projeto Rust."
    fi
    
    info_msg "Criando diretório de instalação: $SOCKS5_DIR..."
    sudo mkdir -p "$SOCKS5_DIR"
    
    info_msg "Copiando executável para $SOCKS5_DIR..."
    sudo cp "$SCRIPT_DIR/target/release/rusty_socks_proxy" "$SOCKS5_EXEC" || error_exit "Falha ao copiar executável rusty_socks_proxy."
    
    info_msg "Copiando arquivo de serviço systemd..."
    if [[ ! -f "$SCRIPT_DIR/rusty_socks_proxy.service" ]]; then
        error_exit "Arquivo rusty_socks_proxy.service não encontrado em $SCRIPT_DIR."
    fi
    sudo cp "$SCRIPT_DIR/rusty_socks_proxy.service" "$SOCKS5_SERVICE_FILE" || error_exit "Falha ao copiar arquivo de serviço systemd."
    
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

# --- Início do Script ---
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
sudo ln -sf "$SCRIPT_DIR/menu.sh" /usr/local/bin/menu
sudo chmod +x /usr/local/bin/menu
success_msg "Link simbólico criado. Agora você pode acessar o menu digitando 'menu'."
```
