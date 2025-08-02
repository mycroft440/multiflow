#!/bin/bash

# ==============================================================================
# Script de Instalação Remota do Multiflow (Versão Final Revisada)
#
# Otimizado para automação e execução com um único comando (ex: wget | bash).
# - Detecta modo não interativo para evitar prompts ao usuário.
# - Para a execução imediatamente em caso de erro.
# - Clona o repositório, instala dependências e a aplicação.
# ==============================================================================

# --- Configuração do Script ---
# Interrompe o script se um comando falhar
set -e
# Garante que falhas em pipelines sejam capturadas
set -o pipefail

# --- Configuração de Cores ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Funções de Log ---
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
    # Limpa o diretório temporário em caso de erro
    if [ -d "$TMP_DIR" ]; then
        log_info "Limpando arquivos temporários..."
        rm -rf "$TMP_DIR"
    fi
    exit 1
}

# --- Função para Aguardar o APT ---
wait_for_apt() {
    log_info "Verificando se o gerenciador de pacotes (APT) está disponível..."
    local max_attempts=30
    local attempt=0
    
    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
          fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
          fuser /var/cache/apt/archives/lock >/dev/null 2>&1 || \
          fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
        
        attempt=$((attempt + 1))
        if [ $attempt -ge $max_attempts ]; then
            error_exit "Timeout: O APT continuou ocupado por outro processo. Tente novamente mais tarde."
        fi
        
        log_warn "APT está em uso. Aguardando... (tentativa $attempt/$max_attempts)"
        sleep 5
    done
    
    log_info "APT está disponível para uso."
}

# --- Início da Execução ---

# 1. Verificação de Privilégios e Variáveis
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
    log_warn "O script não está sendo executado como root. Usando 'sudo' quando necessário."
else
    SUDO=""
fi

# Variáveis do Projeto
REPO_URL="https://github.com/mycroft440/multiflow.git"
INSTALL_DIR="/opt/multiflow"
TMP_DIR="/tmp/multiflow-install-$$" # Diretório temporário único

# 2. Verificação do Sistema Operacional
if [ ! -f /etc/os-release ]; then
    error_exit "Não foi possível identificar o sistema operacional."
fi
source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
    log_warn "Este script é otimizado para Debian/Ubuntu. Alguns pacotes podem variar em outras distribuições."
    # Verifica se está em modo interativo antes de perguntar
    if [ -t 0 ]; then
        read -p "Deseja continuar mesmo assim? (s/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            log_info "Instalação cancelada pelo usuário."
            exit 0
        fi
    else
        log_warn "Executando em modo não interativo. Continuando automaticamente."
    fi
fi

# 3. Atualização e Instalação de Dependências
log_info "Iniciando atualização e limpeza do sistema..."
wait_for_apt
$SUDO apt-get update -y
$SUDO apt-get upgrade -y
$SUDO apt-get --fix-broken install -y
$SUDO dpkg --configure -a

log_info "Instalando dependências essenciais: python3, pip, git, go, build-essential."
$SUDO apt-get install -y python3 python3-pip git golang-go build-essential
$SUDO pip3 install tqdm psutil
$SUDO apt-get autoremove -y
$SUDO apt-get clean

# 4. Clonar o Repositório do Projeto
log_info "Baixando o projeto Multiflow de $REPO_URL..."
git clone --depth 1 "$REPO_URL" "$TMP_DIR"

# O diretório de trabalho agora é o do projeto clonado
cd "$TMP_DIR"

# 5. Compilação de Ferramentas (BadVPN)
BADVPN_SOURCE="conexoes/BadVPN.c"
BADVPN_EXEC="/usr/local/bin/custom_badvpn"
if [ -f "$BADVPN_SOURCE" ]; then
    log_info "Compilando BadVPN customizado..."
    $SUDO gcc -o "$BADVPN_EXEC" "$BADVPN_SOURCE" -lpthread || log_warn "Falha ao compilar BadVPN. O menu pode não funcionar corretamente."
    $SUDO chmod +x "$BADVPN_EXEC"
fi

# 6. Instalação das Ferramentas de Otimização (ZRAM e Swap)
log_info "Instalando ferramentas de otimização..."

# Instalação do ZRAM
ZRAM_SOURCE_PATH="ferramentas/zram.py"
ZRAM_TARGET_PATH="/usr/local/bin/zram-manager"
if [ -f "$ZRAM_SOURCE_PATH" ]; then
    log_info "Instalando o gerenciador ZRAM..."
    $SUDO cp "$ZRAM_SOURCE_PATH" "$ZRAM_TARGET_PATH"
    $SUDO chmod +x "$ZRAM_TARGET_PATH"
    $SUDO "$ZRAM_TARGET_PATH" install "$ZRAM_TARGET_PATH" || log_warn "Não foi possível instalar o serviço ZRAM."
    $SUDO "$ZRAM_TARGET_PATH" setup || log_warn "Não foi possível ativar o ZRAM."
else
    log_warn "Arquivo 'ferramentas/zram.py' não encontrado. Pulando esta etapa."
fi

# Instalação do SWAP
SWAP_SOURCE_PATH="ferramentas/swap.py"
SWAP_TARGET_PATH="/usr/local/bin/swap-manager"
if [ -f "$SWAP_SOURCE_PATH" ]; then
    log_info "Configurando arquivo de SWAP..."
    $SUDO cp "$SWAP_SOURCE_PATH" "$SWAP_TARGET_PATH"
    $SUDO chmod +x "$SWAP_TARGET_PATH"
    $SUDO "$SWAP_TARGET_PATH" setup || log_warn "Não foi possível configurar o SWAP."
else
    log_warn "Arquivo 'ferramentas/swap.py' não encontrado. Pulando esta etapa."
fi

# 7. Instalação do Multiflow
log_info "Iniciando a instalação do Multiflow..."

if [ -d "$INSTALL_DIR" ]; then
    log_warn "Uma instalação anterior foi detectada em $INSTALL_DIR. Removendo..."
    $SUDO rm -rf "$INSTALL_DIR"
fi

log_info "Copiando arquivos do projeto para $INSTALL_DIR..."
$SUDO mkdir -p "$INSTALL_DIR"
# Copia todo o conteúdo do diretório atual (TMP_DIR)
$SUDO cp -a . "$INSTALL_DIR/"

# 8. Configuração de Permissões e Shebangs
log_info "Configurando permissões de execução para os scripts..."
find "$INSTALL_DIR" -type f -name "*.py" -print0 | while IFS= read -r -d $'\0' script; do
    if ! grep -q "^#\!/usr/bin/env python3" "$script"; then
        $SUDO sed -i '1i#!/usr/bin/env python3' "$script"
    fi
    $SUDO chmod +x "$script"
done
find "$INSTALL_DIR" -type f \( -name "*.sh" -o -name "*.go" \) -exec $SUDO chmod +x {} +

# 9. Criação de Links Simbólicos
log_info "Criando links simbólicos para facilitar a execução..."
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/multiflow
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/h
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/menu

# 10. Limpeza
log_info "Limpando arquivos de instalação temporários..."
rm -rf "$TMP_DIR"

# --- Finalização ---
echo
log_info "${GREEN}=====================================================${NC}"
log_info "${GREEN}  Instalação do Multiflow concluída com sucesso!   ${NC}"
log_info "${GREEN}=====================================================${NC}"
echo
log_info "Você pode iniciar a aplicação executando um dos seguintes comandos:"
echo -e "  ${BLUE}multiflow${NC}"
echo -e "  ${BLUE}h${NC}"
echo -e "  ${BLUE}menu${NC}"
echo

# Verifica se está em modo interativo antes de perguntar
if [ -t 0 ]; then
    read -p "Deseja iniciar o Multiflow agora? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        log_info "Iniciando Multiflow..."
        /usr/local/bin/multiflow
    fi
else
    log_info "Instalação concluída. Para iniciar, execute 'multiflow'."
fi
