#!/bin/bash

# Script para instalação e configuração otimizada do badvpn-udpgw
# Baseado no guia de Alta Performance e Baixa Latência.
# ATENÇÃO: Execute este script como root ou com sudo.

# --- Configurações ---
MAX_CLIENTS=5000
MAX_CONN_PER_CLIENT=100
LISTEN_PORT=7300
FILE_DESCRIPTOR_LIMIT=65536

# --- Início do Script ---

# Garante que o script pare se algum comando falhar
set -e

# Verifica se o script está sendo executado como root
if [ "$(id -u)" -ne 0 ]; then
  echo "Este script precisa ser executado como root. Use: sudo ./script.sh" >&2
  exit 1
fi

echo "--- [Iniciando a instalação e configuração do Badvpn-udpgw] ---"

# --- Passo 1: Instalação a Partir do Código-Fonte ---
echo "--> Passo 1: Instalando dependências e compilando o Badvpn..."
apt-get update
apt-get install -y cmake build-essential libnss3-dev libssl-dev git

# Clona o repositório (remove o diretório antigo se existir)
if [ -d "badvpn" ]; then
  echo "Diretório 'badvpn' encontrado. Removendo para uma clonagem limpa."
  rm -rf badvpn
fi
git clone https://github.com/ambrop72/badvpn.git

cd badvpn
mkdir -p build && cd build
cmake .. -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_TUN2SOCKS=1 -DBUILD_UDPGW=1
make
make install
cd ../.. # Volta para o diretório original

echo "Badvpn compilado e instalado com sucesso em /usr/local/bin/"

# --- Passo 2 & 3: Criação e Otimização do Serviço systemd ---
echo "--> Passo 2 & 3: Criando e otimizando o serviço systemd..."

# Cria o usuário do sistema para o serviço
if ! id "badvpn" &>/dev/null; then
  useradd -r -s /bin/false badvpn
  echo "Usuário 'badvpn' criado."
else
  echo "Usuário 'badvpn' já existe."
fi

# Cria o arquivo de serviço systemd usando um Here Document
cat <<EOF > /etc/systemd/system/badvpn-udpgw.service
[Unit]
Description=BadVPN UDP Gateway
After=network.target

[Service]
User=badvpn
Group=badvpn
ExecStart=/usr/local/bin/badvpn-udpgw \\
  --listen-addr 127.0.0.1:${LISTEN_PORT} \\
  --max-clients ${MAX_CLIENTS} \\
  --max-connections-for-client ${MAX_CONN_PER_CLIENT}
Restart=always
RestartSec=3

# Aumenta o limite de descritores de arquivos para o serviço. ESSENCIAL!
LimitNOFILE=${FILE_DESCRIPTOR_LIMIT}

[Install]
WantedBy=multi-user.target
EOF

echo "Arquivo de serviço '/etc/systemd/system/badvpn-udpgw.service' criado."

# --- Passo 4: Otimização para Latência Ultrabaixa (Kernel) ---
echo "--> Passo 4: Aplicando otimizações de kernel (sysctl)..."

# Cria o arquivo de configuração do sysctl
cat <<EOF > /etc/sysctl.d/99-badvpn-optimizations.conf
# Otimizações para Badvpn-udpgw
net.core.rmem_max=8388608
net.core.wmem_max=8388608
net.core.netdev_max_backlog=250000
net.core.somaxconn=4096
net.ipv4.tcp_low_latency=1
net.ipv4.tcp_timestamps=0
net.ipv4.tcp_sack=1
EOF

# Aplica as configurações
sysctl -p /etc/sysctl.d/99-badvpn-optimizations.conf

echo "Otimizações de kernel aplicadas."

echo "--> Configurando o governador da CPU para 'performance'..."
apt-get install -y cpufrequtils
echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils
systemctl restart cpufrequtils || echo "Não foi possível reiniciar cpufrequtils, pode não ser necessário."

# --- Passo 5: Fortalecimento da Segurança (Firewall com UFW) ---
echo "--> Passo 5: Configurando o firewall (UFW)..."
apt-get install -y ufw

ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow in on lo to any port ${LISTEN_PORT} proto tcp

# Ativa o UFW de forma não interativa
ufw --force enable

echo "Firewall UFW configurado e ativado."

# --- Passo 6: Ativação e Início do Serviço ---
echo "--> Passo 6: Ativando e iniciando o serviço badvpn-udpgw..."
systemctl daemon-reload
systemctl enable badvpn-udpgw.service
systemctl start badvpn-udpgw.service

echo ""
echo "--- [ Instalação e Configuração Concluídas! ] ---"
echo ""
echo "O serviço badvpn-udpgw foi instalado, configurado e iniciado."
echo "Para verificar o status, use o comando:"
echo "  sudo systemctl status badvpn-udpgw.service"
echo ""
echo "Para verificar se está escutando na porta correta (127.0.0.1:${LISTEN_PORT}), use:"
echo "  ss -tulpn | grep badvpn"
echo ""
echo "Para monitorar perdas de pacotes UDP (importante!), use:"
echo "  netstat -su | grep 'packet receive errors'"
echo ""
