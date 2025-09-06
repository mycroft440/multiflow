#!/bin/bash

# Script para instalação e configuração otimizada do badvpn-udpgw
# Removemos a diretiva tcp_low_latency para garantir compatibilidade com outros proxys.

# --- Configurações ---
MAX_CLIENTS=5000
MAX_CONN_PER_CLIENT=100
# A porta é recebida como primeiro argumento ($1), com 7300 como padrão.
LISTEN_PORT=${1:-7300}
FILE_DESCRIPTOR_LIMIT=65536

# --- Início do Script ---

# Garante que o script pare se algum comando falhar
set -e

# Verifica se o script está sendo executado como root
if [ "$(id -u)" -ne 0 ]; then
  echo "Este script precisa ser executado como root." >&2
  exit 1
fi

echo "--- [Iniciando a instalação e configuração do Badvpn-udpgw] ---"

# --- Desativa o firewall UFW para evitar conflitos ---
echo "--> Verificando e desativando o firewall UFW..."
if command -v ufw &> /dev/null; then
  ufw disable
  echo "Firewall UFW desativado para garantir a conectividade."
else
  echo "Firewall UFW não encontrado. Nenhuma ação necessária."
fi

# --- Passo 1: Instalação a Partir do Código-Fonte ---
echo "--> Passo 1: Instalando dependências e compilando o Badvpn..."
apt-get update > /dev/null
apt-get install -y cmake build-essential libnss3-dev libssl-dev git > /dev/null

if [ -d "badvpn" ]; then
  rm -rf badvpn
fi
git clone https://github.com/ambrop72/badvpn.git > /dev/null

cd badvpn
mkdir -p build && cd build
cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_TUN2SOCKS=1 -DBUILD_UDPGW=1 > /dev/null
make > /dev/null
make install > /dev/null
cd ../..
rm -rf badvpn

echo "Badvpn compilado e instalado com sucesso."

# --- Passo 2 & 3: Criação e Otimização do Serviço systemd ---
echo "--> Passo 2 & 3: Criando o serviço systemd..."

if ! id "badvpn" &>/dev/null; then
  useradd -r -s /bin/false badvpn
fi

# Define o endereço de escuta como 0.0.0.0 para aceitar conexões externas
LISTEN_ADDRESS="0.0.0.0"

cat <<EOF > /etc/systemd/system/badvpn-udpgw.service
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
User=badvpn
Group=badvpn
ExecStart=/usr/local/bin/badvpn-udpgw \\
  --listen-addr ${LISTEN_ADDRESS}:${LISTEN_PORT} \\
  --max-clients ${MAX_CLIENTS} \\
  --max-connections-for-client ${MAX_CONN_PER_CLIENT}
Restart=always
RestartSec=3
LimitNOFILE=${FILE_DESCRIPTOR_LIMIT}

[Install]
WantedBy=multi-user.target
EOF

echo "Serviço systemd criado."

# --- Passo 4: Otimização de Rede (Kernel) ---
echo "--> Passo 4: Aplicando otimizações de kernel (sysctl) e ativando BBR..."
cat <<EOF > /etc/sysctl.d/99-badvpn-optimizations.conf
# Otimizações para Badvpn-udpgw e BBR
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=8388608
net.core.wmem_max=8388608
net.core.netdev_max_backlog=250000
net.core.somaxconn=4096
# A linha abaixo foi removida por causar conflitos com outros serviços de proxy.
# net.ipv4.tcp_low_latency=1
net.ipv4.tcp_timestamps=0
net.ipv4.tcp_sack=1
EOF

# Aplica as configurações
sysctl -p /etc/sysctl.d/99-badvpn-optimizations.conf > /dev/null
echo "Otimizações de rede e BBR aplicados."

# --- Passo 5: Ativação e Início do Serviço ---
echo "--> Passo 5: Ativando e iniciando o serviço badvpn-udpgw..."
systemctl daemon-reload
systemctl enable badvpn-udpgw.service > /dev/null
systemctl restart badvpn-udpgw.service

echo ""
echo "--- [ Instalação Concluída! ] ---"
echo "O serviço badvpn-udpgw foi instalado e iniciado na porta ${LISTEN_PORT}."
echo "Para verificar o status, use: systemctl status badvpn-udpgw"