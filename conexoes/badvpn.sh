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
# 1. Instalação e Configuração Base (Executado sempre)
# ==============================================================================

status_message "Iniciando a instalação e configuração do BadVPN..."

# Instalar dependências
status_message "Instalando dependências (wget, screen)..."
apt-get update -y > /dev/null 2>&1
apt-get install -y wget screen > /dev/null 2>&1

# Baixar e instalar badvpn-udpgw
status_message "Baixando e instalando badvpn-udpgw..."
if [[ ! -f /bin/badvpn-udpgw ]]; then
    wget -qO /bin/badvpn-udpgw https://www.dropbox.com/s/48b36clnxkkurlz/badvpn-udpgw
    chmod +x /bin/badvpn-udpgw
    status_message "badvpn-udpgw instalado em /bin/badvpn-udpgw"
else
    warning_message "badvpn-udpgw já existe em /bin/badvpn-udpgw. Pulando o download."
fi

# Aplicar ajustes no kernel Linux (sysctl)
status_message "Aplicando otimizações no kernel Linux (sysctl) para UDP..."
SYSCTL_CONFIG="/etc/sysctl.conf"
if ! grep -q "net.core.rmem_max = 4194304" "$SYSCTL_CONFIG"; then
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
if [ ! -f "$SERVICE_FILE" ]; then
    status_message "Criando o serviço systemd para o BadVPN..."
    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
ExecStart=/bin/badvpn-udpgw --listen-addr 127.0.0.1:7300 --max-clients 10000 --max-connections-for-client-ip 8 --client-socket-sndbuf 1048576
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable badvpn-udpgw > /dev/null 2>&1
    status_message "Serviço badvpn-udpgw criado e habilitado para iniciar no boot."
else
    warning_message "Serviço systemd já existe. Pulando a criação."
fi

# ==============================================================================
# 2. Lógica de Reconfiguração da Porta (Adicionado)
#    Esta seção verifica se uma porta foi passada como argumento.
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
    systemctl start badvpn-udpgw
fi

status_message "Operação do BadVPN concluída com sucesso!"
