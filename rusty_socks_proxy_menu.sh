```bash
#!/bin/bash

# Menu para gerenciar o SOCKS5
# Versão: 1.0

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurações
SOCKS5_DIR="/opt/rusty_socks_proxy"
SOCKS5_EXEC="$SOCKS5_DIR/rusty_socks_proxy"
SOCKS5_SERVICE_FILE="/etc/systemd/system/rusty_socks_proxy.service"
PROJECT_DIR="/opt/multiflow"

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

# Função para verificar se uma porta está em uso
check_port_in_use() {
    local port="$1"
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Função para verificar dependências Rust
check_rust_dependencies() {
    info_msg "Verificando dependências Rust..."
    if ! command -v cargo &> /dev/null; then
        error_exit "Rust e Cargo não estão instalados. Execute o script de instalação primeiro."
    fi
    if [[ ! -f "$PROJECT_DIR/Cargo.toml" ]]; then
        error_exit "Arquivo Cargo.toml não encontrado em $PROJECT_DIR."
    fi
    info_msg "Dependências Rust verificadas com sucesso."
}

# Função para instalar SOCKS5
install_socks5() {
    clear
    echo -e "${BLUE}=== Instalar SOCKS5 ===${NC}"
    
    if [[ -f "$SOCKS5_EXEC" ]]; then
        warning_msg "SOCKS5 já parece estar instalado."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    check_rust_dependencies
    
    info_msg "Compilando o projeto Rust para SOCKS5..."
    (cd "$PROJECT_DIR" && cargo build --release)
    
    if [[ $? -ne 0 ]]; then
        error_exit "Falha ao compilar o projeto Rust. Verifique as dependências no Cargo.toml."
    fi
    
    info_msg "Criando diretório de instalação: $SOCKS5_DIR..."
    sudo mkdir -p "$SOCKS5_DIR"
    
    info_msg "Copiando executável para $SOCKS5_DIR..."
    if [[ ! -f "$PROJECT_DIR/target/release/rusty_socks_proxy" ]]; then
        error_exit "Executável rusty_socks_proxy não encontrado em $PROJECT_DIR/target/release."
    fi
    sudo cp "$PROJECT_DIR/target/release/rusty_socks_proxy" "$SOCKS5_EXEC" || error_exit "Falha ao copiar executável."
    
    info_msg "Copiando arquivo de serviço systemd..."
    if [[ ! -f "$PROJECT_DIR/rusty_socks_proxy.service" ]]; then
        error_exit "Arquivo rusty_socks_proxy.service não encontrado em $PROJECT_DIR."
    fi
    sudo cp "$PROJECT_DIR/rusty_socks_proxy.service" "$SOCKS5_SERVICE_FILE" || error_exit "Falha ao copiar arquivo de serviço."
    
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
alter_socks5_port() {
    clear
    echo -e "${BLUE}=== Alterar Porta SOCKS5 ===${NC}"
    
    if [[ ! -f "$SOCKS5_SERVICE_FILE" ]]; then
        error_exit "Serviço SOCKS5 não encontrado. Instale-o primeiro."
    fi
    
    current_port=$(grep -oP 'Environment="SOCKS5_PORT=\K[0-9]+' "$SOCKS5_SERVICE_FILE")
    info_msg "Porta atual do SOCKS5: ${current_port:-1080}"
    
    read -p "Digite a nova porta para o SOCKS5: " new_port
    
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [[ "$new_port" -lt 1024 ]] || [[ "$new_port" -gt 65535 ]]; then
        error_exit "Porta inválida. Use uma porta entre 1024 e 65535."
    fi
    
    if check_port_in_use "$new_port"; then
        error_exit "Porta $new_port já está em uso."
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
open_socks5_port() {
    clear
    echo -e "${BLUE}=== Abrir Porta SOCKS5 ===${NC}"
    
    if [[ ! -f "$SOCKS5_SERVICE_FILE" ]]; then
        error_exit "Serviço SOCKS5 não encontrado. Instale-o primeiro."
    fi
    
    current_port=$(grep -oP 'Environment="SOCKS5_PORT=\K[0-9]+' "$SOCKS5_SERVICE_FILE")
    port=${current_port:-1080}
    
    info_msg "Abrindo porta $port no firewall (UFW)..."
    
    if ! command -v ufw &> /dev/null; then
        warning_msg "UFW não está instalado. Instalando..."
        sudo apt update && sudo apt install -y ufw
    fi
    
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
remove_socks5() {
    clear
    echo -e "${BLUE}=== Remover SOCKS5 ===${NC}"
    
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

# Função para o menu de gerenciamento do SOCKS5
socks5_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== Gerenciar SOCKS5 ===${NC}"
        echo "1. Instalar SOCKS5"
        echo "2. Alterar Porta SOCKS5"
        echo "3. Abrir Porta SOCKS5"
        echo "4. Remover SOCKS5"
        echo "0. Voltar ao Menu Anterior"
        echo ""
        read -p "Escolha uma opção: " socks5_choice

        case $socks5_choice in
            1) install_socks5 ;;
            2) alter_socks5_port ;;
            3) open_socks5_port ;;
            4) remove_socks5 ;;
            0) break ;;
            *)
                warning_msg "Opção inválida! Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}

# Inicia o menu principal
socks5_menu
```
