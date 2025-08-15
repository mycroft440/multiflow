#!/bin/bash
#script para a instalação do projeto multiflow, zram e swap automaticos.

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
    log_warn "O script não está a ser executado como root. A usar \'sudo\' quando necessário."
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
# REMOVIDO: build-essential, automake, autoconf, libtool, gcc, pois badvpn.c não é mais compilado.
# REMOVIDO: python3-requests, pois não parece ser usado. Adicionado python3-psutil.
$SUDO apt-get install -y python3 python3-pip git python3-psutil lsb-release build-essential openssh-server
$SUDO apt-get autoremove -y
$SUDO apt-get clean

# Configurações adicionais para estabilidade de rede (sysctl)
log_info "A configurar parâmetros sysctl para melhorar a estabilidade das conexões TCP..."
$SUDO sysctl -w net.core.somaxconn=1024
$SUDO sysctl -w net.ipv4.tcp_keepalive_time=60
$SUDO sysctl -w net.ipv4.tcp_keepalive_intvl=30
$SUDO sysctl -w net.ipv4.tcp_keepalive_probes=5
$SUDO sysctl -w net.ipv4.tcp_fin_timeout=30
echo "net.core.somaxconn = 1024" | $SUDO tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_keepalive_time = 60" | $SUDO tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_keepalive_intvl = 30" | $SUDO tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_keepalive_probes = 5" | $SUDO tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_fin_timeout = 30" | $SUDO tee -a /etc/sysctl.conf
$SUDO sysctl -p

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
# REMOVIDO: Bloco de compilação do badvpn.c foi completamente removido, pois o arquivo não existe mais.
# O projeto agora usa badvpn.sh.
log_info "Etapa de compilação C ignorada (não é mais necessária)."

cd "$INSTALL_DIR"

# 7. Configuração de Permissões e Shebangs
log_info "A configurar permissões de execução para os scripts..."
find "$INSTALL_DIR" -type f -name "*.py" -exec bash -c 'if ! grep -q "^#!/usr/bin/env python3" "$0"; then sudo sed -i "1i#!/usr/bin/env python3" "$0"; fi; sudo chmod +x "$0"' {} \;
find "$INSTALL_DIR" -type f -name "*.sh" -exec $SUDO chmod +x {} \;

# Instalação do ZRAM
ZRAM_SCRIPT="$INSTALL_DIR/ferramentas/zram.py"
if [ -f "$ZRAM_SCRIPT" ]; then
    log_info "A instalar o gestor ZRAM..."
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

# Configuração de Keep-Alives no SSHD
SSHD_CONFIG="/etc/ssh/sshd_config"
log_info "A configurar keep-alives no sshd_config para manter conexões SSH ativas..."

# Verificar e adicionar ClientAliveInterval se não existir
if ! grep -q "^ClientAliveInterval" "$SSHD_CONFIG"; then
    echo "ClientAliveInterval 60" | $SUDO tee -a "$SSHD_CONFIG" > /dev/null
else
    $SUDO sed -i 's/^ClientAliveInterval.*/ClientAliveInterval 60/' "$SSHD_CONFIG"
fi

# Verificar e adicionar ClientAliveCountMax se não existir
if ! grep -q "^ClientAliveCountMax" "$SSHD_CONFIG"; then
    echo "ClientAliveCountMax 3" | $SUDO tee -a "$SSHD_CONFIG" > /dev/null
else
    $SUDO sed -i 's/^ClientAliveCountMax.*/ClientAliveCountMax 3/' "$SSHD_CONFIG"
fi

# Verificar e adicionar TCPKeepAlive se não existir
if ! grep -q "^TCPKeepAlive" "$SSHD_CONFIG"; then
    echo "TCPKeepAlive yes" | $SUDO tee -a "$SSHD_CONFIG" > /dev/null
else
    $SUDO sed -i 's/^TCPKeepAlive.*/TCPKeepAlive yes/' "$SSHD_CONFIG"
fi

# Reiniciar o serviço SSH para aplicar as mudanças
$SUDO systemctl restart ssh || $SUDO service ssh restart || log_warn "Não foi possível reiniciar o serviço SSH."
log_info "Configuração de keep-alives no SSH concluída."

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
    log_info "Instalação concluída. Para iniciar, execute \'multiflow\'."
fi


# Instalação do Dtunnel Proxy (se necessário, adicione dependências aqui)
log_info "A verificar e instalar dependências para Dtunnel Proxy..."
$SUDO apt-get install -y unzip curl
# Nenhuma dependência específica adicionada por padrão, pois os binários geralmente são auto-suficientes.
# Se houver erros de biblioteca, adicione-as aqui.
