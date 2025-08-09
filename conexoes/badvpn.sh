#!/bin/bash

# Cores para a saída do terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Função para exibir mensagens de status
function log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function log_error() {
    echo -e "${RED}[ERRO]${NC} $1"
}

function log_warn() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

# Função para limpar em caso de falha
function cleanup_on_failure() {
    log_error "A instalação falhou. Removendo diretório temporário..."
    [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ] && rm -rf "$TMP_DIR"
    exit 1
}

# Captura de erros para executar a limpeza
trap cleanup_on_failure ERR

# Verifica se o script está sendo executado como root
if [[ $EUID -ne 0 ]]; then
   log_error "Este script deve ser executado como root!"
   exit 1
fi

# ==============================================================================
# 1. Instalação e Configuração Base
# ==============================================================================

log_info "Iniciando a instalação e configuração do BadVPN..."

# Instalar dependências para compilação e execução
log_info "Instalando dependências (git, cmake, build-essential, screen)..."
# Redireciona a saída do apt-get para um log para não poluir a tela, mas ainda ser depurável
apt-get update -y > /tmp/badvpn_install.log 2>&1
apt-get install -y git cmake build-essential screen >> /tmp/badvpn_install.log 2>&1

# Compilar badvpn-udpgw a partir do código-fonte para garantir compatibilidade
log_info "Compilando badvpn-udpgw a partir do código-fonte..."
TMP_DIR="/tmp/badvpn-src-$$"

log_info "Clonando o repositório do BadVPN..."
# REMOVIDO: Redirecionamento de saída para permitir a visualização de erros
if ! git clone https://github.com/ambrop72/badvpn.git "$TMP_DIR"; then
    log_error "Falha ao clonar o repositório do BadVPN. Verifique sua conexão com a internet ou a saída de erro acima."
    # A trap de erro cuidará da limpeza
fi
cd "$TMP_DIR"

log_info "Configurando o ambiente de compilação com CMake..."
# REMOVIDO: Redirecionamento de saída
if ! cmake .; then
    log_error "O comando 'cmake' falhou. Verifique se todas as dependências foram instaladas corretamente."
fi

log_info "Compilando o BadVPN com 'make'..."
# REMOVIDO: Redirecionamento de saída
if ! make; then
    log_error "O comando 'make' falhou. Verifique a saída de erro acima para identificar a causa."
fi

# Verifica se a compilação foi bem-sucedida
if [[ -f "badvpn-udpgw/badvpn-udpgw" ]]; then
    # Usa /usr/local/bin, uma prática recomendada para binários compilados pelo usuário
    cp "badvpn-udpgw/badvpn-udpgw" /usr/local/bin/
    chmod +x /usr/local/bin/badvpn-udpgw
    log_info "badvpn-udpgw compilado e instalado com sucesso em /usr/local/bin/badvpn-udpgw"
else
    log_error "O binário 'badvpn-udpgw' não foi encontrado após a compilação. A compilação falhou."
fi

# Limpa os arquivos de código-fonte
log_info "Limpando arquivos de compilação..."
rm -rf "$TMP_DIR"
cd / # Retorna para um diretório seguro

# Aplicar ajustes no kernel Linux (sysctl)
log_info "Aplicando otimizações no kernel Linux (sysctl) para UDP..."
SYSCTL_CONFIG="/etc/sysctl.conf"
if ! grep -q "net.core.rmem_max" "$SYSCTL_CONFIG"; then
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
# Atualiza o caminho do executável para /usr/local/bin/
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
ExecStart=/usr/local/bin/badvpn-udpgw --listen-addr 127.0.0.1:7300 --max-clients 10000 --max-connections-for-client-ip 8 --client-socket-sndbuf 1048576
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable badvpn-udpgw > /dev/null 2>&1
log_info "Serviço badvpn-udpgw criado e habilitado para iniciar no boot."

# ==============================================================================
# 2. Lógica de Reconfiguração da Porta
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
    sed -i "s/--listen-addr 127.0.0.1:[0-9]*/--listen-addr 127.0.0.1:$NEW_PORT/g" "$SERVICE_FILE"
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
else
    log_error "O serviço BadVPN falhou ao iniciar. Verifique os logs com: journalctl -u badvpn-udpgw.service -l"
fi
