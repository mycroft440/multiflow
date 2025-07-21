#!/bin/bash

# MultiFlow - Gerenciador e Instalador de Conexões, Ferramentas e Protocolos
# Versão: 2.0 (Corrigida)
# Autor: MultiFlow Team

set -euo pipefail  # Modo strict para bash

# Cores para a saída do terminal
readonly GREEN='\033[1;32m'
readonly YELLOW='\033[1;33m'
readonly RED='\033[1;31m'
readonly BLUE='\033[1;34m'
readonly NC='\033[0m'

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
# }

# Função para verificar conectividade com a internet
# Função para verificar conectividade com a internet
# check_internet() {
#     if ! ping -c 1 google.com &> /dev/null; then
#         error_exit "Sem conexão com a internet. Verifique sua conexão e tente novamente."
#     end
# }

# Função para atualizar pacotes do sistema
update_system() {
    info_msg "Atualizando lista de pacotes..."
    sudo apt update -qq || error_exit "Falha ao atualizar lista de pacotes."
}

# Função para instalar dependências básicas
install_basic_dependencies() {
    info_msg "Instalando dependências básicas..."
    local packages=(
        "curl"
        "wget"
        "git"
        "build-essential"
        "pkg-config"
        "libssl-dev"
        "unzip"
        "net-tools"
        "lsof"
        "systemd"
    )
    
    for package in "${packages[@]}"; do
        if ! dpkg -l | grep -q "^ii  $package "; then
            info_msg "Instalando $package..."
            sudo apt install -y "$package" || warning_msg "Falha ao instalar $package"
        fi
    done
}

# Função para instalar Rust e Cargo para o root
install_rust() {
    if command -v cargo &>/dev/null; then
        info_msg "Rust e Cargo já estão instalados."
        return 0
    fi
    
    info_msg "Instalando Rust e Cargo..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path || error_exit "Falha ao instalar Rust."
    
    # Adicionar Rust ao PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    source "$HOME/.cargo/env" 2>/dev/null || true
    
    # Configurar rustup
    if command -v rustup &>/dev/null; then
        rustup default stable || warning_msg "Não foi possível configurar rustup default stable."
    fi
    
    success_msg "Rust e Cargo instalados com sucesso."
}

# Função para verificar portas em uso
check_port() {
    local port="$1"
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1  # Porta em uso
    fi
    return 0  # Porta livre
}

# Função para instalar o proxy SOCKS5 em Rust
install_rusty_socks5_proxy() {
    clear
    echo -e "${BLUE}--- Instalar Rusty SOCKS5 Proxy ---${NC}"
    
    # Solicitar porta
    local default_port=1080
    read -p "Digite a porta para o Rusty SOCKS5 Proxy (padrão: $default_port): " socks5_port
    socks5_port=${socks5_port:-$default_port}
    
    # Validar porta
    # A validação de intervalo de portas foi removida para permitir maior flexibilidade.
    # Certifique-se de que a porta escolhida não esteja em uso e entenda as implicações de segurança de portas privilegiadas.
    if ! [[ "$socks5_port" =~ ^[0-9]+$ ]]; then
        error_exit "Porta inválida. Digite um número válido."
    fi
    
    # Verificar se a porta está em uso
    if ! check_port "$socks5_port"; then
        error_exit "Porta $socks5_port já está em uso."
    fi
    
    info_msg "Iniciando instalação do Rusty SOCKS5 Proxy na porta $socks5_port..."
    
    # Criar diretório do projeto
    mkdir -p "$PROJECT_DIR/src" || error_exit "Falha ao criar diretório do projeto."
    
    # Copiar arquivos do projeto
    info_msg "Copiando arquivos do projeto..."
    sudo cp "$SCRIPT_DIR/main.rs" "$PROJECT_DIR/src/" || error_exit "Falha ao copiar main.rs."
    sudo cp "$SCRIPT_DIR/Cargo.toml" "$PROJECT_DIR/src/" || error_exit "Falha ao copiar Cargo.toml."
    sudo cp "$SCRIPT_DIR/rusty_socks_proxy.service" "$PROJECT_DIR/" || error_exit "Falha ao copiar arquivo de serviço."
    
    # Compilar o projeto
    info_msg "Compilando o projeto Rust..."
    cd "$PROJECT_DIR/src"
    
    # Garantir que o Rust está no PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    source "$HOME/.cargo/env" 2>/dev/null || true
    
    cargo build --release || error_exit "Falha ao compilar o projeto Rust."
    
    # Mover executável
    info_msg "Instalando executável..."
    sudo mv target/release/rusty_socks_proxy "$PROJECT_DIR/" || error_exit "Falha ao mover executável."
    sudo chmod +x "$PROJECT_DIR/rusty_socks_proxy"
    
    # Configurar serviço systemd
    info_msg "Configurando serviço systemd..."
    sudo cp "$PROJECT_DIR/rusty_socks_proxy.service" /etc/systemd/system/ || error_exit "Falha ao copiar arquivo de serviço."
    
    # Atualizar configurações no arquivo de serviço
    sudo sed -i "s|Environment=\"SOCKS5_PORT=.*\"|Environment=\"SOCKS5_PORT=$socks5_port\"|g" /etc/systemd/system/rusty_socks_proxy.service
    
    # Recarregar systemd e iniciar serviço
    sudo systemctl daemon-reload || error_exit "Falha ao recarregar daemon systemd."
    sudo systemctl enable rusty_socks_proxy || error_exit "Falha ao habilitar serviço."
    sudo systemctl start rusty_socks_proxy || error_exit "Falha ao iniciar serviço."
    
    # Verificar status
    if systemctl is-active --quiet rusty_socks_proxy; then
        success_msg "Rusty SOCKS5 Proxy instalado e iniciado na porta $socks5_port."
        info_msg "Verifique o status com: systemctl status rusty_socks_proxy"
    else
        error_exit "Serviço instalado mas falhou ao iniciar. Verifique os logs com: journalctl -u rusty_socks_proxy"
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para instalar gerenciador de usuários SSH
install_ssh_user_manager() {
    info_msg "Instalando gerenciador de usuários SSH..."
    
    # Criar diretório se não existir
    sudo mkdir -p "$(dirname "$SSH_USER_MANAGEMENT_SCRIPT")"
    
    # Copiar script de gerenciamento
    if [[ -f "$SCRIPT_DIR/new_ssh_user_management.sh" ]]; then
        sudo cp "$SCRIPT_DIR/new_ssh_user_management.sh" "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao copiar script de gerenciamento SSH."
    else
        error_exit "Arquivo new_ssh_user_management.sh não encontrado."
    fi
    
    sudo chmod +x "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "Falha ao dar permissão de execução."
    
    success_msg "Gerenciador de usuários SSH instalado."
}

# Função para gerenciar usuários SSH
manage_ssh_users_menu() {
    if [[ ! -f "$SSH_USER_MANAGEMENT_SCRIPT" ]]; then
        error_exit "Script de gerenciamento SSH não encontrado. Execute a instalação primeiro."
    fi
    
    # Carregar funções do script de gerenciamento
    sudo source "$SSH_USER_MANAGEMENT_SCRIPT"
    
    while true; do
        clear
        echo -e "${BLUE}--- Gerenciamento de Usuários SSH ---${NC}"
        echo "1. Criar Usuário SSH"
        echo "2. Remover Usuário SSH"
        echo "3. Listar Usuários SSH"
        echo "4. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice
        
        case $choice in
            1) create_ssh_user ;;
            2) remove_ssh_user ;;
            3) list_ssh_users ;;
            4) break ;;
            *) 
                warning_msg "Opção inválida. Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
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
        sudo echo "deb http://security.ubuntu.com/ubuntu focal-security main" > /etc/apt/sources.list.d/focal.list
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
        if dpkg -i *.deb; then
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
    
    # Criar diretório de destino
    sudo mkdir -p "$DTPROXY_DIR" || error_exit "Falha ao criar diretório $DTPROXY_DIR."
    
    # Copiar arquivos
    sudo cp "$dtproxy_source_dir/dtproxy_x86_64" "$DTPROXY_DIR/" || error_exit "Falha ao copiar dtproxy_x86_64."
    sudo cp "$dtproxy_source_dir/dtproxy_menu.sh" "$DTPROXY_DIR/" || error_exit "Falha ao copiar dtproxy_menu.sh."
    sudo cp "$dtproxy_source_dir/dtproxy_port_menu.sh" "$DTPROXY_DIR/" || error_exit "Falha ao copiar dtproxy_port_menu.sh."
    
    # Dar permissões de execução
    sudo chmod +x "$DTPROXY_DIR/dtproxy_x86_64" || error_exit "Falha ao dar permissão de execução."
    sudo chmod +x "$DTPROXY_DIR/dtproxy_menu.sh"
    sudo chmod +x "$DTPROXY_DIR/dtproxy_port_menu.sh"
    
    # Corrigir caminhos nos scripts de menu
    sed -i "s|/home/ubuntu/dtproxy_project/dtproxy_x86_64|$DTPROXY_DIR/dtproxy_x86_64|g" "$DTPROXY_DIR/dtproxy_menu.sh"
    sed -i "s|/home/ubuntu/dtproxy_project/dtproxy_x86_64|$DTPROXY_DIR/dtproxy_x86_64|g" "$DTPROXY_DIR/dtproxy_port_menu.sh"
    
    # Criar serviço systemd
    info_msg "Configurando serviço systemd para dtproxy..."
    cat > /etc/systemd/system/dtproxy.service << EOF
[Unit]
Description=DTProxy Service
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=$DTPROXY_DIR/dtproxy_x86_64
Restart=always
RestartSec=5
User=root
Group=root
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dtproxy

[Install]
WantedBy=multi-user.target
EOF
    
    # Habilitar e iniciar serviço
    systemctl daemon-reload || error_exit "Falha ao recarregar daemon systemd."
    systemctl enable dtproxy || warning_msg "Falha ao habilitar serviço dtproxy."
    
    # Tentar iniciar o serviço
    if systemctl start dtproxy; then
        success_msg "dtproxy instalado e iniciado com sucesso."
        info_msg "Verifique o status com: systemctl status dtproxy"
    else
        warning_msg "dtproxy instalado mas falhou ao iniciar. Verifique se libssl1.1 está corretamente instalada."
        info_msg "Verifique os logs com: journalctl -u dtproxy"
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para exibir status dos serviços
show_status() {
    clear
    echo -e "${BLUE}--- Status dos Serviços ---${NC}"
    
    # Status do Rusty SOCKS5 Proxy
    echo -e "${YELLOW}Rusty SOCKS5 Proxy:${NC}"
    if systemctl is-active --quiet rusty_socks_proxy; then
        echo -e "  Status: ${GREEN}Ativo${NC}"
        local port=$(grep "SOCKS5_PORT=" /etc/systemd/system/rusty_socks_proxy.service 2>/dev/null | cut -d'=' -f3 | tr -d '"' || echo "1080")
        echo "  Porta: $port"
    else
        echo -e "  Status: ${RED}Inativo${NC}"
    fi
    
    echo
    
    # Status do dtproxy
    echo -e "${YELLOW}dtproxy:${NC}"
    if systemctl is-active --quiet dtproxy; then
        echo -e "  Status: ${GREEN}Ativo${NC}"
    else
        echo -e "  Status: ${RED}Inativo${NC}"
    fi
    
    echo
    
    # Status do OpenVPN
    echo -e "${YELLOW}OpenVPN:${NC}"
    if systemctl is-active --quiet openvpn@server; then
        echo -e "  Status: ${GREEN}Ativo${NC}"
        if [[ -f /etc/openvpn/server.conf ]]; then
            local ovpn_port=$(grep "^port " /etc/openvpn/server.conf | awk '{print $2}' || echo "N/A")
            echo "  Porta: $ovpn_port"
        fi
    else
        echo -e "  Status: ${RED}Inativo${NC}"
    fi
    
    echo
    echo "------------------------------------"
    read -p "Pressione Enter para continuar..."
}

# Função para executar iostat
run_iostat() {
    clear
    echo -e "${BLUE}--- iostat (CPU, Disco, Rede) ---${NC}"
    
    # Instalar sysstat se não estiver instalado
    if ! command -v iostat &>/dev/null; then
        info_msg "Instalando sysstat..."
        apt install -y sysstat || error_exit "Falha ao instalar sysstat."
    fi
    
    info_msg "Executando iostat (5 amostras, intervalo de 1 segundo)..."
    echo
    iostat -c -d -x 1 5
    
    read -p "Pressione Enter para continuar..."
}

# Função para otimizar kernel
optimize_kernel() {
    clear
    echo -e "${BLUE}--- Otimização do Kernel ---${NC}"
    
    info_msg "Aplicando otimizações de rede e sistema..."
    
    # Backup da configuração atual
    cp /etc/sysctl.conf /etc/sysctl.conf.backup.$(date +%Y%m%d_%H%M%S)
    
    # Aplicar otimizações
    local optimizations=(
        "net.core.somaxconn=65536"
        "net.core.netdev_max_backlog=65536"
        "net.ipv4.tcp_tw_reuse=1"
        "net.ipv4.tcp_fin_timeout=30"
        "net.ipv4.tcp_keepalive_time=600"
        "net.ipv4.tcp_max_syn_backlog=65536"
        "net.ipv4.tcp_max_tw_buckets=2000000"
        "net.ipv4.tcp_mem=786432 1048576 1572864"
        "net.ipv4.tcp_rmem=4096 87380 16777216"
        "net.ipv4.tcp_wmem=4096 65536 16777216"
        "net.ipv4.ip_local_port_range=1024 65535"
        "vm.swappiness=10"
        "fs.file-max=2097152"
    )
    
    for opt in "${optimizations[@]}"; do
        echo "$opt" >> /etc/sysctl.conf
        sysctl -w "$opt" >/dev/null 2>&1 || warning_msg "Falha ao aplicar: $opt"
    done
    
    # Aplicar configurações
    sysctl -p >/dev/null 2>&1
    
    success_msg "Otimizações do kernel aplicadas."
    info_msg "As configurações foram salvas em /etc/sysctl.conf"
    
    read -p "Pressione Enter para continuar..."
}

# Função para instalar e executar Stacer
install_and_run_stacer() {
    clear
    echo -e "${BLUE}--- Stacer (Monitorar, Limpar, Otimizar) ---${NC}"
    
    if ! command -v stacer &>/dev/null; then
        info_msg "Instalando Stacer..."
        apt update -qq
        apt install -y stacer || error_exit "Falha ao instalar Stacer."
        success_msg "Stacer instalado."
    else
        info_msg "Stacer já está instalado."
    fi
    
    warning_msg "Stacer requer interface gráfica para funcionar."
    info_msg "Se você estiver em um ambiente sem GUI, use as ferramentas de linha de comando."
    
    read -p "Deseja tentar executar Stacer? (s/N): " run_stacer
    if [[ "$run_stacer" =~ ^[Ss]$ ]]; then
        stacer &
        info_msg "Stacer iniciado em segundo plano."
    fi
    
    read -p "Pressione Enter para continuar..."
}

# Função para executar BleachBit
run_bleachbit() {
    clear
    echo -e "${BLUE}--- BleachBit (Limpeza do Sistema) ---${NC}"
    
    if ! command -v bleachbit &>/dev/null; then
        info_msg "Instalando BleachBit..."
        apt update -qq
        apt install -y bleachbit || error_exit "Falha ao instalar BleachBit."
        success_msg "BleachBit instalado."
    else
        info_msg "BleachBit já está instalado."
    fi
    
    echo "Opções disponíveis:"
    echo "1. Executar BleachBit (GUI)"
    echo "2. Limpeza rápida via linha de comando"
    echo "3. Voltar"
    
    read -p "Escolha uma opção: " bleach_choice
    
    case $bleach_choice in
        1)
            warning_msg "BleachBit GUI requer interface gráfica."
            read -p "Deseja tentar executar? (s/N): " run_gui
            if [[ "$run_gui" =~ ^[Ss]$ ]]; then
                bleachbit &
                info_msg "BleachBit iniciado em segundo plano."
            fi
            ;;
        2)
            info_msg "Executando limpeza básica..."
            bleachbit --clean system.cache system.localizations system.trash || warning_msg "Alguns itens podem não ter sido limpos."
            success_msg "Limpeza básica concluída."
            ;;
        3)
            return
            ;;
        *)
            warning_msg "Opção inválida."
            ;;
    esac
    
    read -p "Pressione Enter para continuar..."
}

# Menu de gerenciamento de conexões
manage_connections_menu() {
    while true; do
        clear
        echo -e "${BLUE}--- Gerenciamento de Conexões ---${NC}"
        echo "1. Instalar Rusty SOCKS5 Proxy"
        echo "2. Instalar dtproxy (mod mycroft)"
        echo "3. Gerenciar OpenVPN"
        echo "4. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice
        
        case $choice in
            1) install_rusty_socks5_proxy ;;
            2) install_dtproxy ;;
            3) 
                warning_msg "Funcionalidade OpenVPN será implementada em versão futura."
                read -p "Pressione Enter para continuar..."
                ;;
            4) break ;;
            *) 
                warning_msg "Opção inválida. Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}

# Menu de ferramentas
manage_tools_menu() {
    while true; do
        clear
        echo -e "${BLUE}--- Ferramentas (Limpeza e Performance) ---${NC}"
        echo "1. iostat (CPU, Disco, Rede)"
        echo "2. Otimização do Kernel"
        echo "3. Stacer (Monitorar, Limpar, Otimizar)"
        echo "4. BleachBit (Limpeza do Sistema)"
        echo "5. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice
        
        case $choice in
            1) run_iostat ;;
            2) optimize_kernel ;;
            3) install_and_run_stacer ;;
            4) run_bleachbit ;;
            5) break ;;
            *) 
                warning_msg "Opção inválida. Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}

# Menu principal
main_menu() {
    # Verificações iniciais
    # check_root
    # check_internet
    
    # Instalar dependências básicas
    update_system
    install_basic_dependencies
    install_rust
    
    # Instalar gerenciador SSH automaticamente
    if [[ ! -f "$SSH_USER_MANAGEMENT_SCRIPT" ]]; then
        install_ssh_user_manager
    fi
    
    while true; do
        clear
        echo -e "${GREEN}"
        cat << "EOF"
    __  _____  ____  __________________    ____ _       __
   /  |/  / / / / / /_  __/  _/ ____/ /   / __ \ |     / /
  / /|_/ / / / / /   / /  / // /_  / /   / / / / | /| / / 
 / /  / / /_/ / /___/ / _/ // __/ / /___/ /_/ /| |/ |/ /  
/_/  /_/\____/_____/_/ /___/_/   /_____/\____/ |__/|__/   
                                                          
EOF
        echo -e "${NC}"
        echo -e "${BLUE}        --- Bem-vindo ao MULTIFLOW manager ---${NC}"
        echo
        echo "1. Gerenciar Usuários SSH"
        echo "2. Gerenciar Conexões"
        echo "3. Status dos Serviços"
        echo "4. Ferramentas (Limpeza e Performance)"
        echo "5. Sair"
        echo "----------------------------------------------------"
        read -p "Escolha uma opção: " choice
        
        case $choice in
            1) manage_ssh_users_menu ;;
            2) manage_connections_menu ;;
            3) show_status ;;
            4) manage_tools_menu ;;
            5) 
                echo -e "${GREEN}Obrigado por usar o MultiFlow!${NC}"
                exit 0
                ;;
            *) 
                warning_msg "Opção inválida. Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}

# Verificar se o script está sendo executado diretamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main_menu
fi

