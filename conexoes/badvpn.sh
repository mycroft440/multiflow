#!/bin/bash

# Cores para a saída do terminal
RED=
GREEN=
YELLOW=
NC=

# Função para exibir mensagens de status
function status_message() {
    echo -e "[INFO] $1"
}

function error_message() {
    echo -e "[ERRO] $1"
}

function warning_message() {
    echo -e "[AVISO] $1"
}

# Verifica se o script está sendo executado como root
if [[ $EUID -ne 0 ]]; then
   error_message "Este script deve ser executado como root!"
   exit 1
fi

status_message "Iniciando a instalação e otimização do BadVPN..."

# 1. Instalar dependências
status_message "Instalando dependências necessárias (wget, screen)..."
apt update -y > /dev/null 2>&1
apt install -y wget screen > /dev/null 2>&1

# 2. Baixar e instalar badvpn-udpgw
status_message "Baixando e instalando badvpn-udpgw..."
if [[ ! -f /bin/badvpn-udpgw ]]; then
    wget -qO /bin/badvpn-udpgw https://www.dropbox.com/s/48b36clnxkkurlz/badvpn-udpgw
    chmod +x /bin/badvpn-udpgw
    status_message "badvpn-udpgw instalado em /bin/badvpn-udpgw"
else
    warning_message "badvpn-udpgw já existe em /bin/badvpn-udpgw. Pulando o download."
fi

# 3. Aplicar ajustes no kernel Linux (sysctl)
status_message "Aplicando otimizações no kernel Linux (sysctl) para UDP..."
SYSCTL_CONFIG="/etc/sysctl.conf"

# Verifica se as linhas já existem para evitar duplicação
if ! grep -q "net.core.rmem_max = 4194304" "$SYSCTL_CONFIG"; then
    echo "# Otimizações para BadVPN UDP" | tee -a "$SYSCTL_CONFIG" > /dev/null
    echo "net.core.rmem_max = 4194304" | tee -a "$SYSCTL_CONFIG" > /dev/null
    echo "net.core.wmem_max = 4194304" | tee -a "$SYSCTL_CONFIG" > /dev/null
    echo "net.ipv4.udp_mem = 1048576 4194304 8388608" | tee -a "$SYSCTL_CONFIG" > /dev/null
    status_message "Configurações sysctl adicionadas ao $SYSCTL_CONFIG"
else
    warning_message "Configurações sysctl para UDP já existem em $SYSCTL_CONFIG. Pulando a adição."
fi

sysctl -p > /dev/null 2>&1
status_message "Configurações sysctl aplicadas."

# 4. Configurar badvpn-udpgw para iniciar no boot e gerenciar
status_message "Configurando badvpn-udpgw para iniciar automaticamente e adicionando funções de gerenciamento..."

# Cria o arquivo de serviço systemd para badvpn-udpgw
SERVICE_FILE="/etc/systemd/system/badvpn-udpgw.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
ExecStart=/bin/badvpn-udpgw --listen-addr 127.0.0.1:7300 --max-clients 10000 --max-connections-for-client 8 --client-socket-sndbuf 1048576
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable badvpn-udpgw > /dev/null 2>&1
systemctl start badvpn-udpgw

status_message "Serviço badvpn-udpgw criado e configurado para iniciar no boot na porta 7300."
status_message "Você pode gerenciar o serviço com: systemctl start|stop|restart|status badvpn-udpgw"

# Adiciona funções de gerenciamento ao .bashrc para facilitar o uso
BASHRC_FILE="/root/.bashrc"

cat <<EOF >> "$BASHRC_FILE"

# Funções de gerenciamento BadVPN
function badvpn_status() {
    systemctl status badvpn-udpgw
}

function badvpn_start() {
    systemctl start badvpn-udpgw
    echo -e "${GREEN}BadVPN iniciado!${NC}"
}

function badvpn_stop() {
    systemctl stop badvpn-udpgw
    echo -e "${RED}BadVPN parado!${NC}"
}

function badvpn_restart() {
    systemctl restart badvpn-udpgw
    echo -e "${YELLOW}BadVPN reiniciado!${NC}"
}

function badvpn_port() {
    if [[ -z "$1" ]]; then
        warning_message "Uso: badvpn_port <nova_porta>"
        return 1
    fi
    local NEW_PORT="$1"
    status_message "Alterando a porta do BadVPN para $NEW_PORT..."
    sed -i "s/--listen-addr 127.0.0.1:[0-9]*/--listen-addr 127.0.0.1:$NEW_PORT/g" "/etc/systemd/system/badvpn-udpgw.service"
    systemctl daemon-reload
    systemctl restart badvpn-udpgw
    status_message "Porta do BadVPN alterada para $NEW_PORT e serviço reiniciado."
}
EOF

status_message "Funções de gerenciamento BadVPN adicionadas ao $BASHRC_FILE. Recarregue seu terminal ou execute 'source $BASHRC_FILE' para usá-las."

status_message "Instalação e otimização do BadVPN concluídas com sucesso!"


