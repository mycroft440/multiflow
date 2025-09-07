#!/bin/bash

# Revised installation and port‑configuration script for BadVPN UDPGW
#
# This script improves upon the original `conexoes/badvpn.sh` by
#  * detecting when BadVPN is already installed and only updating the
#    listen port instead of recompiling the daemon every time;
#  * providing more robust error handling for package installation and
#    cloning from GitHub;
#  * wrapping systemd operations with checks so the script can abort
#    gracefully if any step fails.

set -euo pipefail

# --- Configurações padrão ---
MAX_CLIENTS=5000
MAX_CONN_PER_CLIENT=100
FILE_DESCRIPTOR_LIMIT=65536
LISTEN_PORT=${1:-7300}

# Caminho do serviço systemd e do binário
SERVICE_FILE="/etc/systemd/system/badvpn-udpgw.service"
BINARY="/usr/local/bin/badvpn-udpgw"

# Determina se systemd está disponível. Caso contrário, será utilizado um método de fallback
USE_SYSTEMD=false
if command -v systemctl &>/dev/null; then
    USE_SYSTEMD=true
fi

echo "--- [Revisão do instalador do BadVPN] ---"

# Função utilitária para logar e abortar em caso de erro
abort() {
    echo "[ERRO] $1" >&2
    exit 1
}

# Se o serviço já existe, apenas atualize a porta e reinicie
if [ -f "$SERVICE_FILE" ]; then
    echo "-- Serviço existente detectado. Atualizando porta para ${LISTEN_PORT}..."
    if [ "$USE_SYSTEMD" = true ]; then
        # Atualiza a linha --listen-addr mantendo o endereço 0.0.0.0
        if grep -q "--listen-addr" "$SERVICE_FILE"; then
            sed -i -E "s/--listen-addr [^:]+:[0-9]+/--listen-addr 0.0.0.0:${LISTEN_PORT}/" "$SERVICE_FILE"
        else
            abort "Não foi possível encontrar parâmetro --listen-addr em $SERVICE_FILE"
        fi
        systemctl daemon-reload || abort "Falha ao recarregar o systemd"
        systemctl restart badvpn-udpgw.service || abort "Falha ao reiniciar o serviço BadVPN"
        echo "Porta atualizada para ${LISTEN_PORT}."
    else
        # Fallback: mata processo em execução (se houver) e reinicia com nova porta
        PIDFILE="/var/run/badvpn-udpgw.pid"
        if [ -f "$PIDFILE" ]; then
            pid=$(cat "$PIDFILE")
            if ps -p "$pid" &>/dev/null; then
                echo "-- Encerrando processo BadVPN atual (PID $pid) para atualizar porta..."
                kill "$pid" || true
                # Aguarda processo terminar
                sleep 2
            fi
        fi
        echo "-- Iniciando badvpn-udpgw em segundo plano na porta ${LISTEN_PORT} (modo sem systemd)..."
        # Ajusta limite de descritores antes de iniciar
        ulimit -n "$FILE_DESCRIPTOR_LIMIT" 2>/dev/null || true
        nohup "$BINARY" --listen-addr 0.0.0.0:${LISTEN_PORT} \
          --max-clients ${MAX_CLIENTS} \
          --max-connections-for-client ${MAX_CONN_PER_CLIENT} \
          > /var/log/badvpn-udpgw.log 2>&1 &
        echo $! > "$PIDFILE"
        echo "Porta atualizada para ${LISTEN_PORT}."
    fi
    exit 0
fi

# Verificação de privilégio
if [ "$(id -u)" -ne 0 ]; then
    abort "Este script deve ser executado como root."
fi

echo "-- Preparando sistema para compilar BadVPN..."

# Desativa o UFW se estiver instalado, mas não interrompe se der erro
if command -v ufw &>/dev/null; then
    ufw disable || true
fi

# Atualiza pacotes e instala dependências necessárias
if command -v apt-get &>/dev/null; then
    apt-get update -y || abort "apt-get update falhou"
    # Instala dependências, incluindo pacotes adicionais necessários para compilação
    apt-get install -y cmake build-essential libnss3-dev libssl-dev git pkg-config zlib1g-dev || abort "Falha na instalação de dependências"
else
    abort "Sistema baseado em APT necessário para instalar dependências."
fi

# Baixa e compila BadVPN apenas se o binário não existir
if [ ! -x "$BINARY" ]; then
    echo "-- Clonando repositório BadVPN..."
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT
    git clone --depth 1 https://github.com/ambrop72/badvpn.git "$tmpdir/badvpn" || abort "Falha ao clonar repositório badvpn"
    mkdir -p "$tmpdir/badvpn/build"
    cd "$tmpdir/badvpn/build"
    # Compila UDPGW e TUN2SOCKS para atender requisitos adicionais
    cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1 -DBUILD_TUN2SOCKS=1 > /dev/null
    make -j"$(nproc)" > /dev/null
    make install > /dev/null || abort "Falha ao instalar badvpn-udpgw"
    cd - >/dev/null
else
    echo "-- Binário badvpn-udpgw já existe em ${BINARY}, pulando compilação."
fi

# Cria usuário e grupo do badvpn se necessário
if ! id badvpn &>/dev/null; then
    useradd -r -s /bin/false badvpn || abort "Falha ao criar usuário 'badvpn'"
fi

if [ "$USE_SYSTEMD" = true ]; then
    # Cria arquivo de serviço systemd
    cat > "$SERVICE_FILE" <<SERVICE_EOF
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
User=badvpn
Group=badvpn
ExecStart=${BINARY} \
  --listen-addr 0.0.0.0:${LISTEN_PORT} \
  --max-clients ${MAX_CLIENTS} \
  --max-connections-for-client ${MAX_CONN_PER_CLIENT}
Restart=always
RestartSec=3
LimitNOFILE=${FILE_DESCRIPTOR_LIMIT}

[Install]
WantedBy=multi-user.target
SERVICE_EOF
    echo "-- Serviço systemd criado em ${SERVICE_FILE}."
fi

# Aplica otimizações de rede usando sysctl.d
cat > /etc/sysctl.d/99-badvpn-optimizations.conf <<SYSCTL_EOF
# Otimizações para BadVPN UDPGW e BBR
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=8388608
net.core.wmem_max=8388608
net.core.netdev_max_backlog=250000
net.core.somaxconn=4096
net.ipv4.tcp_timestamps=0
net.ipv4.tcp_sack=1
SYSCTL_EOF

# Recarrega parâmetros de kernel
sysctl --system > /dev/null || echo "Aviso: não foi possível recarregar todos os parâmetros sysctl"

if [ "$USE_SYSTEMD" = true ]; then
    # Habilita e inicia o serviço via systemd
    systemctl daemon-reload || abort "Falha ao recarregar systemd"
    systemctl enable badvpn-udpgw.service || abort "Falha ao habilitar o serviço badvpn-udpgw"
    systemctl restart badvpn-udpgw.service || abort "Falha ao iniciar o serviço badvpn-udpgw"
    echo "--- [Instalação Concluída] ---"
    echo "O serviço badvpn-udpgw foi instalado e iniciado na porta ${LISTEN_PORT}."
    echo "Use 'systemctl status badvpn-udpgw' para verificar o status."
else
    # Inicia o serviço em segundo plano sem systemd
    echo "-- systemd não está disponível. Iniciando badvpn-udpgw em segundo plano..."
    # Ajusta limite de descritores
    ulimit -n "$FILE_DESCRIPTOR_LIMIT" 2>/dev/null || true
    nohup "$BINARY" --listen-addr 0.0.0.0:${LISTEN_PORT} \
      --max-clients ${MAX_CLIENTS} \
      --max-connections-for-client ${MAX_CONN_PER_CLIENT} \
      > /var/log/badvpn-udpgw.log 2>&1 &
    echo $! > /var/run/badvpn-udpgw.pid
    echo "--- [Instalação Concluída] ---"
    echo "badvpn-udpgw foi iniciado na porta ${LISTEN_PORT} em modo de background."
    echo "PID salvo em /var/run/badvpn-udpgw.pid. Logs em /var/log/badvpn-udpgw.log."
fi

