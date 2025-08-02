#!/bin/bash

# Cores para saída de console
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Função para exibir mensagens coloridas
function log_info {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function log_warn {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

function log_error {
    echo -e "${RED}[ERRO]${NC} $1" >&2
}

# Função para exibir mensagens de erro e sair
function error_exit {
    log_error "$1"
    exit 1
}

# Função para aguardar o APT ficar disponível
function wait_for_apt {
    log_info "Verificando se o APT está disponível..."
    
    local max_attempts=30
    local attempt=0
    
    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
          fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
          fuser /var/cache/apt/archives/lock >/dev/null 2>&1 || \
          fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
        
        attempt=$((attempt + 1))
        
        if [ $attempt -ge $max_attempts ]; then
            error_exit "Timeout esperando o APT ficar disponível. Tente novamente mais tarde."
        fi
        
        log_warn "APT está em uso por outro processo. Aguardando... (tentativa $attempt/$max_attempts)"
        sleep 5
    done
    
    log_info "APT está disponível."
}

# Verificar se está rodando como root
if [ "$(id -u)" -ne 0 ]; then
    if ! command -v sudo >/dev/null 2>&1; then
        error_exit "ERRO! Execute esse script como root. Caso não souber peça ajuda."
    fi
    SUDO="sudo"
else
    SUDO=""
fi

# Verificar se o sistema é compatível
if [ ! -f /etc/os-release ]; then
    error_exit "Sistema operacional não reconhecido."
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" && "$ID_LIKE" != *"debian"* ]]; then
    log_warn "Este script foi testado apenas em sistemas baseados em Debian/Ubuntu."
    read -p "Deseja continuar mesmo assim? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

log_info "Iniciando atualização e limpeza do sistema..."

wait_for_apt

$SUDO apt update && \
$SUDO apt upgrade -y && \
$SUDO apt clean && \
$SUDO apt autoclean && \
$SUDO apt --fix-broken install && \
$SUDO dpkg --configure -a && \
$SUDO apt install -f || error_exit "Falha na atualização e limpeza do sistema."

log_info "Instalando python3-pip e tqdm..."
$SUDO apt install -y python3-pip || error_exit "Falha ao instalar python3-pip."
$SUDO pip install tqdm || error_exit "Falha ao instalar tqdm."
$SUDO pip install psutil
$SUDO apt install golang-go -y
$SUDO apt autoremove -y

log_info "Processo de pré-requisitos concluído com sucesso."

# Início da instalação do zram.py
ZRAM_SCRIPT_URL="https://raw.githubusercontent.com/mycroft440/multiflow/main/zram.py"
ZRAM_LOCAL_PATH="/usr/local/bin/zram_manager.py"

log_info "Baixando e instalando zram.py..."
$SUDO wget -O "$ZRAM_LOCAL_PATH" "$ZRAM_SCRIPT_URL" || error_exit "Falha ao baixar zram.py."
$SUDO chmod +x "$ZRAM_LOCAL_PATH" || error_exit "Falha ao dar permissão de execução para zram.py."

log_info "Executando instalação do serviço zram.py..."
$SUDO "$ZRAM_LOCAL_PATH" install "$ZRAM_LOCAL_PATH" || error_exit "Falha ao instalar o serviço zram.py."

log_info "Instalação do zram.py concluída com sucesso!"

# Início da instalação do swap.py
SWAP_SCRIPT_URL="https://raw.githubusercontent.com/mycroft440/multiflow/main/swap.py"
SWAP_LOCAL_PATH="/usr/local/bin/swap.py"

log_info "Baixando e instalando swap.py..."
$SUDO wget -O "$SWAP_LOCAL_PATH" "$SWAP_SCRIPT_URL" || error_exit "Falha ao baixar swap.py."
$SUDO chmod +x "$SWAP_LOCAL_PATH" || error_exit "Falha ao dar permissão de execução para swap.py."

log_info "Executando configuração do swap.py..."
# O script swap_manager.py foi revisado para ter um comando 'setup'
$SUDO python3 "$SWAP_LOCAL_PATH" setup || error_exit "Falha ao configurar o swap.py."

log_info "Configuração do swap.py concluída com sucesso!"

# Início do script do instalador principal (Multiflow)

# Definir o diretório de instalação
INSTALL_DIR="/opt/multiflow"

# Verificar e criar backup se uma instalação anterior existir
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Instalação anterior detectada em $INSTALL_DIR"
    log_info "Removendo instalação anterior em $INSTALL_DIR..."
    $SUDO rm -rf "$INSTALL_DIR" || error_exit "Falha ao remover instalação anterior."
fi

# Clonar o repositório
REPO_URL="https://github.com/mycroft440/multiflow.git"
log_info "Clonando o repositório $REPO_URL para $INSTALL_DIR..."
$SUDO git clone "$REPO_URL" "$INSTALL_DIR" || error_exit "Falha ao clonar o repositório. Verifique sua conexão com a internet."

# Adicionar shebang e permissões de execução
log_info "Configurando permissões e shebangs para scripts Python..."
for script in "multiflow.py" "ssh_user_manager.py"; do
    if [ -f "$INSTALL_DIR/$script" ]; then
        if ! grep -q "^#!/usr/bin/env python3" "$INSTALL_DIR/$script"; then
            log_info "Adicionando shebang a $script..."
            $SUDO sed -i '1i#!/usr/bin/env python3' "$INSTALL_DIR/$script"
        fi
        $SUDO chmod +x "$INSTALL_DIR/$script" || error_exit "Falha ao dar permissão de execução para $script."
    fi
done

# Criar um link simbólico para facilitar a execução
log_info "Criando link simbólico para execução fácil..."
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/multiflow || error_exit "Falha ao criar link simbólico para multiflow."

# Adicionar links simbólicos adicionais: h e menu
log_info "Criando links simbólicos 'h' e 'menu'..."
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/h || error_exit "Falha ao criar link simbólico para h."
$SUDO ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/menu || error_exit "Falha ao criar link simbólico para menu."

log_info "Instalação do Multiflow concluída com sucesso!"
log_info "Você pode executar o Multiflow digitando 'multiflow', 'h' ou 'menu' no terminal."

# Perguntar se deseja iniciar o programa
read -p "Deseja iniciar o Multiflow agora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    log_info "Iniciando Multiflow..."
    # Executa o script diretamente, pois o shebang e as permissões já foram configurados
    /usr/local/bin/multiflow
fi


