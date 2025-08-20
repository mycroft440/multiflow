#!/usr/bin/env bash

# Script para instalar e configurar o BadVPN, com tratamento de erros aprimorado.
# Corrigido para listen-addr 0.0.0.0 (acesso externo) e uso de make install.

# --- Configurações de Segurança e Cores ---
set -Eeuo pipefail  # Fail-fast: erro em comandos, pipelines, variáveis não definidas; herda ERR em funções
set -o errtrace     # Herda traps em subshells e funções

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
NC="\033[0m"

# --- Funções de Log ---
function log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function log_error() {
    echo -e "${RED}[ERRO]${NC} $1" >&2
}

# --- Tratamento de Erros ---
# Função chamada no evento ERR: captura código, comando, fonte e linha
function _on_err() {
    local exit_code=$?
    local cmd="${BASH_COMMAND}"
    local src="${BASH_SOURCE[1]:-$0}"
    local line="${BASH_LINENO[0]:-$LINENO}"
    log_error "Erro ($exit_code) em $src:$line => Comando: '$cmd'"
    log_error "A instalação falhou. Removendo diretório temporário..."
    # Garante que TMP_DIR existe antes de remover (evita erro unbound)
    [ -n "${TMP_DIR:-}" ] && [ -d "${TMP_DIR:-}" ] && rm -rf "$TMP_DIR" || true
    exit "$exit_code"
}

# Registra o trap com aspas simples para evitar expansão prematura
trap '_on_err' ERR

# --- Verificação de Root ---
if [[ $EUID -ne 0 ]]; then
   log_error "Este script deve ser executado como root!"
   exit 1
fi

# ==============================================================================
# 1. Instalação e Configuração Base
# ==============================================================================

log_info "Iniciando a instalação e configuração do BadVPN..."

# Instalar dependências para compilação e execução
log_info "Instalando dependências (git, cmake, build-essential, screen, pkg-config, libssl-dev, libnspr4-dev, libnss3-dev)..."
apt-get update -y > /tmp/badvpn_install.log 2>&1
apt-get install -y git cmake build-essential screen pkg-config libssl-dev libnspr4-dev libnss3-dev >> /tmp/badvpn_install.log 2>&1

# Compilar badvpn-udpgw
log_info "Compilando badvpn-udpgw a partir do código-fonte..."
TMP_DIR="/tmp/badvpn-src-$$"

log_info "Clonando o repositório do BadVPN..."
git clone https://github.com/ambrop72/badvpn.git "$TMP_DIR"
cd "$TMP_DIR"

log_info "Criando diretório de build..."
mkdir -p build
cd build

log_info "Configurando o ambiente de compilação com CMake (somente udpgw)..."
cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1

log_info "Compilando o BadVPN com 'make'..."
make

log_info "Instalando o binário com 'make install'..."
make install

# Verifica se a instalação foi bem-sucedida
if [[ -f "/usr/local/bin/badvpn-udpgw" ]]; then
    log_info "badvpn-udpgw instalado com sucesso em /usr/local/bin/badvpn-udpgw"
else
    log_error "O binário 'badvpn-udpgw' não foi encontrado. A instalação falhou."
    exit 1
fi

# Limpa os arquivos de código-fonte
log_info "Limpando arquivos de compilação..."
rm -rf "$TMP_DIR"
cd / # Retorna para um diretório seguro

# Aplicar ajustes no kernel Linux (sysctl)
log_info "Aplicando otimizações no kernel Linux (sysctl) para UDP..."
SYSCTL_CONFIG="/etc/sysctl.conf"
if ! grep -q "net.core.rmem_max" "$SYSCTL_CONFIG" || true; then  # Evita disparar ERR se grep falhar (saída 1 esperada)
    echo -e "\n# Otimizações para BadVPN UDP" >> "$SYSCTL_CONFIG"
    echo "net.core.rmem_max = 4194304" >> "$SYSCTL_CONFIG"
    echo "net.core.wmem_max = 4194304" >> "$SYSCTL_CONFIG"
    echo "net.ipv4.udp_mem = 1048576 4194304 8388608" >> "$SYSCTL_CONFIG"
    log_info "Configurações sysctl adicionadas."
fi
sysctl -p > /dev/null 2>&1
log_info "Configurações sysctl aplicadas."

# Cria o arquivo de serviço systemd para badvpn-udpgw
SERVICE_FILE="/etc/systemd/system/badvpn-udpgw.service"
log_info "Criando ou atualizando o serviço systemd para o BadVPN..."
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=BadVPN UDP Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/badvpn-udpgw --listen-addr 0.0.0.0:7300 --max-clients 10000 --client-socket-sndbuf 1048576
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable badvpn-udpgw > /dev/null 2>&1
log_info "Serviço badvpn-udpgw criado e habilitado para iniciar no boot."

# ==============================================================================
# 2. Lógica de Reconfiguração da Porta e Inicialização
# ==============================================================================

# Se um argumento de porta ($1) for passado, reconfigure e reinicie o serviço.
if [ ! -z "$1" ]; then
    NEW_PORT="$1"
    
    # Validação simples da porta
    if ! [[ "$NEW_PORT" =~ ^[0-9]+$ ]] || [ "$NEW_PORT" -lt 1 ] || [ "$NEW_PORT" -gt 65535 ]; then
        log_error "Porta inválida: $NEW_PORT. Forneça um número entre 1 e 65535."
        exit 1
    fi
    
    log_info "Reconfigurando a porta do BadVPN para $NEW_PORT..."
    # Sed melhorado: usa ERE, escapa pontos e limita a porta (2-5 dígitos)
    sed -E -i "s/--listen-addr 0\.0\.0\.0:[0-9]{2,5}/--listen-addr 0.0.0.0:$NEW_PORT/g" "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl restart badvpn-udpgw
    log_info "Porta do BadVPN alterada para $NEW_PORT e serviço reiniciado."
else
    # Se nenhuma porta for passada, apenas garante que o serviço está rodando
    log_info "Iniciando o serviço BadVPN na porta padrão..."
    systemctl start badvpn-udpgw
fi

# Verifica o status final do serviço
sleep 2 # Dá um tempo para o serviço iniciar
if systemctl is-active --quiet badvpn-udpgw; then
    log_info "Operação do BadVPN concluída com sucesso! O serviço está ativo."
    log_info "Verifique com 'netstat -tuln | grep 7300' ou 'journalctl -u badvpn-udpgw -f' para logs."
    log_info "Se usar firewall, abra a porta 7300 (ex.: ufw allow 7300)."
else
    log_error "O serviço BadVPN falhou ao iniciar. Verifique os logs com: journalctl -u badvpn-udpgw.service -l"
fi

# --- Checklist de Validação (como comentário para depuração) ---
# - Verifique trap com: bash -x script.sh (para traçar comandos)
# - Teste falha intencional: adicione 'false' em algum lugar e veja o handler
# - Valide sed: echo o SERVICE_FILE antes/depois da substituição
# - Systemd: systemctl cat badvpn-udpgw.service para inspecionar
