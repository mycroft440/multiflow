#!/bin/bash

# ==============================================================================
# Script de Atualização do Multiflow
#
# Este script realiza uma atualização limpa, garantindo que a instalação
# corresponda exatamente à versão mais recente do repositório.
# ==============================================================================

# --- Configuração do Script ---
set -e
set -o pipefail

# --- Configuração de Cores e Funções de Log ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERRO]${NC} $1" >&2
}

# --- Início da Execução ---

# 1. Verificação de Privilégios e Variáveis
if [ "$(id -u)" -ne 0 ]; then
    log_error "Este script de atualização deve ser executado como root."
    exit 1
fi

REPO_URL="https://github.com/mycroft440/multiflow.git"
INSTALL_DIR="/opt/multiflow"
TMP_DIR="/tmp/multiflow-update-$$"

# 2. Parar Serviços Ativos
#    É crucial parar os serviços para evitar que os arquivos estejam em uso.
log_info "Parando serviços ativos para uma atualização segura..."
systemctl stop badvpn-udpgw.service >/dev/null 2>&1 || true # O '|| true' evita erro se o serviço não estiver rodando

# Para o ProxySocks que roda em Python
PROXY_STATE_FILE="/tmp/proxy.state"
if [ -f "$PROXY_STATE_FILE" ]; then
    log_info "Parando o serviço ProxySocks..."
    PROXY_PID=$(cut -d':' -f1 "$PROXY_STATE_FILE")
    if ps -p "$PROXY_PID" > /dev/null; then
        kill "$PROXY_PID"
    fi
    rm -f "$PROXY_STATE_FILE"
fi

# 3. Baixar a Versão Mais Recente
log_info "Baixando a versão mais recente de $REPO_URL..."
if ! git clone --depth 1 "$REPO_URL" "$TMP_DIR"; then
    log_error "Falha ao baixar o repositório. Verifique sua conexão com a internet."
    exit 1
fi

# 4. Substituir a Instalação Antiga
log_info "Removendo a instalação antiga..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

log_info "Instalando a nova versão..."
cp -a "$TMP_DIR/." "$INSTALL_DIR/"

# 5. Aplicar Permissões
log_info "Aplicando permissões de execução..."
find "$INSTALL_DIR" -type f -name "*.py" -exec chmod +x {} +
find "$INSTALL_DIR" -type f -name "*.sh" -exec chmod +x {} +

# 6. Limpeza
log_info "Limpando arquivos temporários..."
rm -rf "$TMP_DIR"

# --- Finalização ---
echo
log_info "${GREEN}=====================================================${NC}"
log_info "${GREEN}  Atualização do Multiflow concluída com sucesso!  ${NC}"
log_info "${GREEN}=====================================================${NC}"
echo
log_warn "Os serviços foram parados durante a atualização."
log_warn "É necessário reiniciar a aplicação para que as alterações tenham efeito."
echo
