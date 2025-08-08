#!/bin/bash

# Cores para a saída do terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Função para exibir mensagens de status
function status_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function error_message() {
    echo -e "${RED}[ERRO]${NC} $1"
}

function warning_message() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

# Verifica se o script está sendo executado como root
if [[ $EUID -ne 0 ]]; then
   error_message "Este script deve ser executado como root!"
   exit 1
fi

# ==============================================================================
# 1. Instalação e Configuração Base
# ==============================================================================

status_message "Iniciando a instalação e configuração do BadVPN..."

# Instalar dependências para compilação e execução
status_message "Instalando dependências (git, cmake, build-essential, screen)..."
apt-get update -y > /dev/null 2>&1
apt-get install -y git cmake build-essential screen > /dev/null 2>&1

# Compilar badvpn-udpgw a partir do código-fonte para garantir compatibilidade
status_message "Compilando badvpn-udpgw a partir do código-fonte..."
TMP_DIR="/tmp/badvpn-src-$$"
if git clone https://github.com/ambrop72/badvpn.git "$TMP_DIR" > /dev/null 2>&1; then
    cd "$TMP_DIR"
    cmake . > /dev/null 2>&1
    make > /dev/null 2>&1

    # Verifica se a compilação foi bem-sucedida
    if [[ -f "badvpn-udpgw/badvpn-udpgw" ]]; then
        # Usa /usr/local/bin, uma prática recomendada para binários compilados pelo usuário
        cp "badvpn-udpgw/badvpn-udpgw" /usr/local/bin/
        chmod +x /usr/local/bin/badvpn-udpgw
        status_message "badvpn-udpgw compilado e instalado em /usr/local/bin/badvpn-udpgw"
    else
        error_message "Falha na compilação do badvpn-udpgw. Verifique as dependências e a saída de erros."
        rm -rf "$TMP_DIR"
        exit 1
    fi
    # Limpa os arquivos de código-fonte
    rm -rf "$TMP_DIR"
    cd / # Retorna para um diretório seguro
else
    error_message "Falha ao clonar o repositório do BadVPN. Verifique sua conexão com a internet."
    exit 1
fi


# Aplicar ajustes no kernel Linux (sysctl)
status_message "Aplicando otimizações no kernel Linux (sysctl) para UDP..."
SYSCTL_CONFIG="/etc/sysctl.conf"
if ! grep -q "net.core.rmem_max" "$SYSCTL_CONFIG"; then
    echo -e "\n# Otimizações para BadVPN UDP" >> "$SYSCTL_CONFIG"
    echo "net.core.rmem_max = 4194304" >> "$SYSCTL_CONFIG"
    echo "net.core.wmem_max = 4194304" >> "$SYSCTL_CONFIG"
    echo "net.ipv4.udp_mem = 1048576 4194304 8388608" >> "$SYSCTL_CONFIG"
    status_message "Configurações sysctl adicionadas."
fi
sysctl -p > /dev/null 2>&1
status_message "Configurações sysctl aplicadas."

# Cria o arquivo de serviço systemd para badvpn-udpgw
SERVICE_FILE="/etc/systemd/system/badvpn-udpgw.service"
status_message "Criando ou atualizando o serviço systemd para o BadVPN..."
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
status_message "Serviço badvpn-udpgw criado e habilitado para iniciar no boot."

# ==============================================================================
# 2. Lógica de Reconfiguração da Porta
# ==============================================================================

# Se um argumento de porta ($1) for passado, reconfigure e reinicie o serviço.
if [ ! -z "$1" ]; then
    NEW_PORT="$1"
    
    # Validação simples da porta
    if ! [[ "$NEW_PORT" =~ ^[0-9]+$ ]] || [ "$NEW_PORT" -lt 1 ] || [ "$NEW_PORT" -gt 65535 ]; then
        error_message "Porta inválida: $NEW_PORT. Forneça um número entre 1 e 65535."
        exit 1
    fi
    
    status_message "Reconfigurando a porta do BadVPN para $NEW_PORT..."
    sed -i "s/--listen-addr 127.0.0.1:[0-9]*/--listen-addr 127.0.0.1:$NEW_PORT/g" "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl restart badvpn-udpgw
    status_message "Porta do BadVPN alterada para $NEW_PORT e serviço reiniciado."
else
    # Se nenhuma porta for passada, apenas garante que o serviço está rodando
    status_message "Iniciando o serviço BadVPN na porta padrão..."
    systemctl start badvpn-udpgw
fi

# Verifica o status final do serviço
sleep 2 # Dá um tempo para o serviço iniciar
if systemctl is-active --quiet badvpn-udpgw; then
    status_message "Operação do BadVPN concluída com sucesso! O serviço está ativo."
else
    error_message "O serviço BadVPN falhou ao iniciar. Verifique os logs com: journalctl -u badvpn-udpgw.service -l"
fi

