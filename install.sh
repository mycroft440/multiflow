#!/bin/bash

# ==============================================================================
# Script de Instalação Remota do Multiflow (v2.1)
#
# Otimizado para automação, robustez e execução com um único comando.
# - Removemos a compilação de binários Go para o OpenVPN.
# - O script agora depende do openvpn.sh para o gerenciamento.
# ==============================================================================

# --- Configuração do Script ---
set -e
set -o pipefail

# --- Configuração de Cores e Funções de Log ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
        log_info "A limpar ficheiros temporários..."
        rm -rf "$TMP_DIR"
    fi
    exit 1
}

# --- Função para Aguardar o APT ---
wait_for_apt() {
    log_info "A verificar se o gestor de pacotes (APT) está disponível..."
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
        
        log_warn "APT está em uso. A aguardar... (tentativa $attempt/$max_attempts)"
        sleep 5
    done
    
    log_info "APT está disponível para uso."
}

# --- Início da Execução ---

# 1. Verificação de Privilégios e Variáveis
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
    log_warn "O script não está a ser executado como root. A usar 'sudo' quando necessário."
else
    SUDO=""
fi

REPO_URL="https://github.com/mycroft440/multiflow.git"
INSTALL_DIR="/opt/multiflow"
TMP_DIR="/tmp/multiflow-install-$$"

# 2. Verificação do Sistema Operacional
if [ ! -f /etc/os-release ]; then
    error_exit "Não foi possível identificar o sistema operacional."
fi
source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
    log_warn "Este script é otimizado para Debian/Ubuntu. Alguns pacotes podem variar."
    if [ -t 0 ]; then
        read -p "Deseja continuar mesmo assim? (s/n): " -n 1 -r; echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            log_info "Instalação cancelada."
            exit 0
        fi
    else
        log_warn "A executar em modo não interativo. A continuar automaticamente."
    fi
fi

# 3. Atualização e Instalação de Dependências
log_info "A iniciar atualização e limpeza do sistema..."
wait_for_apt
$SUDO apt-get update -y
$SUDO apt-get upgrade -y --with-new-pkgs
$SUDO apt-get --fix-broken install -y
$SUDO dpkg --configure -a

log_info "A instalar dependências essenciais..."
# REMOVIDO: golang-go foi removido das dependências
$SUDO apt-get install -y python3 python3-pip git build-essential automake autoconf libtool gcc python3-psutil python3-requests
$SUDO apt-get autoremove -y
$SUDO apt-get clean

# 4. Clonar o Repositório
log_info "A baixar o projeto Multiflow de $REPO_URL..."
git clone --depth 1 "$REPO_URL" "$TMP_DIR"
cd "$TMP_DIR"

# 5. Instalação do Multiflow
log_info "A iniciar a instalação do Multiflow..."
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Instalação anterior detetada em $INSTALL_DIR. A remover..."
    $SUDO rm -rf "$INSTALL_DIR"
fi
$SUDO mkdir -p "$INSTALL_DIR"
$SUDO cp -a . "$INSTALL_DIR/"

# 6. Compilação dos Binários
# REMOVIDO: Bloco de compilação do OpenVPN em Go foi removido.

# Compila o wrapper BadVPN em C
log_info "A compilar o wrapper BadVPN (C)..."
# O executável será criado em $INSTALL_DIR/conexoes/badvpn_wrapper
gcc "$INSTALL_DIR/conexoes/badvpn.c" -o "$INSTALL_DIR/conexoes/badvpn_wrapper"
log_info "Wrapper BadVPN compilado com sucesso."

cd "$INSTALL_DIR"

# 7. Configuração de Permissões e Shebangs
log_info "A configurar permissões de execução para os scripts..."
find "$INSTALL_DIR" -type f -name "*.py" -print0 | while IFS= read -r -d $'\0' script; do
    # Garante que o shebang está correto
    if ! grep -q "^#\!/usr/bin/env python3" "$script"; then
        $SUDO sed -i '1i#!/usr/bin/env python3' "$script"
    fi
    $SUDO chmod +x "$script"
done
find "$INSTALL_DIR" -type f -name "*.sh" -exec $SUDO chmod +x {} +

# 8. Instalação de Ferramentas de Otimização (ZRAM e SWAP)
log_info "A instalar e configurar ferramentas de otimização..."

# Instalação do ZRAM
ZRAM_SCRIPT="$INSTALL_DIR/ferramentas/zram.py"
if [ -f "$ZRAM_SCRIPT" ]; then
    log_info "A instalar o gestor ZRAM..."
    # O próprio script gere a sua cópia e instalação do serviço systemd
    $SUDO python3 "$ZRAM_SCRIPT" install "$ZRAM_SCRIPT" || log_warn "Não foi possível instalar o serviço ZRAM."
    $SUDO python3 "$ZRAM_SCRIPT" setup || log_warn "Não foi possível ativar o ZRAM."
else
    log_warn "Script do ZRAM não encontrado."
fi

# Instalação do SWAP
SWAP_SCRIPT="$INSTALL_DIR/ferramentas/swap.py"
if [ -f "$SWAP_SCRIPT" ]; then
    log_info "A configurar ficheiro de SWAP..."
    $SUDO python3 "$SWAP_SCRIPT" setup || log_warn "Não foi possível configurar o SWAP."
else
    log_warn "Script de SWAP não encontrado."
fi

# 9. Criação de Links Simbólicos
log_info "A criar links simbólicos para facilitar a execução..."
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/multiflow
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/h
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/menu

# 10. Limpeza
log_info "A limpar ficheiros de instalação temporários..."
rm -rf "$TMP_DIR"

# --- Finalização ---
echo
log_info "${GREEN}=====================================================${NC}"
log_info "${GREEN}  Instalação do Multiflow concluída com sucesso!   ${NC}"
log_info "${GREEN}=====================================================${NC}"
echo
log_info "Pode iniciar a aplicação executando um dos seguintes comandos:"
echo -e "  ${BLUE}multiflow${NC}"
echo -e "  ${BLUE}h${NC}"
echo -e "  ${BLUE}menu${NC}"
echo
log_info "A instalação do OpenVPN e do BadVPN pode ser feita através dos menus da aplicação."
echo

# Pergunta se o utilizador deseja iniciar a aplicação
if [ -t 0 ]; then
    read -p "Deseja iniciar o Multiflow agora? (s/n): " -n 1 -r; echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        log_info "A iniciar Multiflow..."
        /usr/local/bin/multiflow
    fi
else
    log_info "Instalação concluída. Para iniciar, execute 'multiflow'."
fi
