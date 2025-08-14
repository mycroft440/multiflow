#!/bin/bash
#script para a instalação do RustyProxy

# --- Configuração do Script ---
set -e
set -o pipefail

# --- Configuração de Cores e Funções de Log ---
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m" # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERRO]${NC} $1" >&2
}

error_exit() {
    log_error "$1"
    exit 1
}

# --- Início da Execução ---

# 1. Verificação de Privilégios
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
    log_warn "O script não está a ser executado como root. A usar \'sudo\' quando necessário."
else
    SUDO=""
fi

RUSTY_DIR="/opt/rustyproxy"

# Criando o diretório do script
log_info "Criando diretorio $RUSTY_DIR..."
$SUDO mkdir -p "$RUSTY_DIR" || error_exit "Falha ao criar diretorio $RUSTY_DIR"

# Instalar o RustyProxy
log_info "Compilando RustyProxy, isso pode levar algum tempo dependendo da maquina..."

if [ -d "/root/RustyProxyOnly" ]; then
    $SUDO rm -rf /root/RustyProxyOnly
fi

$SUDO git clone --branch "main" https://github.com/UlekBR/RustyProxyOnly.git /root/RustyProxyOnly || error_exit "Falha ao clonar rustyproxy"
$SUDO mv /root/RustyProxyOnly/menu.sh "$RUSTY_DIR/menu"
cd /root/RustyProxyOnly/RustyProxy
$SUDO cargo build --release --jobs $(nproc) || error_exit "Falha ao compilar rustyproxy"
$SUDO mv ./target/release/RustyProxy "$RUSTY_DIR/proxy"

# Configuração de permissões
log_info "Configurando permissões..."
$SUDO chmod +x "$RUSTY_DIR/proxy"
$SUDO chmod +x "$RUSTY_DIR/menu"
$SUDO ln -sf "$RUSTY_DIR/menu" /usr/local/bin/rustyproxy

# Criação do arquivo de portas para RustyProxy
log_info "Criando arquivo de portas para RustyProxy..."
$SUDO touch "$RUSTY_DIR/ports"
$SUDO chmod 666 "$RUSTY_DIR/ports"

# Limpeza
log_info "Limpando diretórios temporários..."
$SUDO rm -rf /root/RustyProxyOnly/

log_info "RustyProxy instalado com sucesso. Digite \'rustyproxy\' para acessar o menu ou use o menu principal do Multiflow."
