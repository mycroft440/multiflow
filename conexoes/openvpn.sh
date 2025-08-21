#!/bin/bash

# ======================================================================
# OpenVPN Installer & Manager - Versão Simplificada para Debian/Ubuntu v4.1
#
# Este script instala e configura um servidor OpenVPN com as melhores
# práticas de segurança e performance. Ele foi revisado para corrigir
# pequenas falhas identificadas no repositório original, adicionando
# verificações de duplicidade em regras de firewall, tratamento robusto
# de erros (via "set -Eeuo pipefail"), e traps para sinais e erros
# inesperados. O foco permanece em sistemas Debian/Ubuntu, como no
# original.
#
# Principais correções aplicadas:
#   • Uso de "set -Eeuo pipefail" para abortar imediatamente em erros
#     não tratados.
#   • Trap para capturar falhas inesperadas e reportar a linha e
#     comando que falhou, além de um trap para SIGINT/SIGTERM que
#     restaura o terminal adequadamente.
#   • Ao configurar o firewall com iptables, o script verifica se a
#     regra já existe antes de adicioná-la, evitando duplicações que
#     podem ocorrer em reinicializações repetidas.
#   • Mantém a funcionalidade original de instalação, geração de
#     certificados e criação de clientes com arquivos .ovpn contendo
#     certificados inline.
# ======================================================================

set -Eeuo pipefail

# Trap para erros inesperados
trap 'echo -e "${RED}[ERRO] Falha inesperada na linha ${LINENO}: comando \"${BASH_COMMAND}\"${SCOLOR}" >&2; exit 1' ERR
# Trap para sinais de interrupção
trap 'echo -e "\n${RED}Script interrompido pelo usuário.${SCOLOR}"; tput cnorm 2>/dev/null; exit 130' INT TERM

# ----------------------- Variáveis de Cor ------------------------------
readonly RED=$'\e[1;31m'
readonly GREEN=$'\e[1;32m'
readonly YELLOW=$'\e[1;33m'
readonly BLUE=$'\e[1;34m'
readonly CYAN=$'\e[1;36m'
readonly WHITE=$'\e[1;37m'
readonly MAGENTA=$'\e[1;35m'
readonly SCOLOR=$'\e[0m'

# -------------------- Configurações Padrão ------------------------------
readonly DEFAULT_PORT="1194"
readonly DEFAULT_PROTOCOL="tcp"
readonly DEFAULT_DNS1="8.8.8.8"
readonly DEFAULT_DNS2="8.8.4.4"
readonly DEFAULT_DNS_IPV6_1="2001:4860:4860::8888"
readonly DEFAULT_DNS_IPV6_2="2001:4860:4860::8844"

# Detecta capacidades do sistema
readonly SUPPORTS_IPV6=$(test -f /proc/net/if_inet6 && echo "yes" || echo "no")
readonly SUPPORTS_NFTABLES=$(command -v nft >/dev/null 2>&1 && echo "yes" || echo "no")
readonly SUPPORTS_SYSTEMD_RESOLVED=$(systemctl is-active systemd-resolved >/dev/null 2>&1 && echo "yes" || echo "no")
readonly CPU_CORES=$(nproc 2>/dev/null || echo "1")

# Diretórios e arquivos globais
OVPN_DIR=""
OVPN_CONF_DIR=""
OVPN_LOG_DIR="/var/log/openvpn"
SERVER_CONF=""
SERVER_UNIT=""

# ---------------------- Funções de Utilidade ---------------------------
die() {
    # Imprime mensagem de erro e encerra
    echo -e "${RED}[ERRO] $1${SCOLOR}" >&2
    exit "${2:-1}"
}

warn() {
    echo -e "${YELLOW}[AVISO] $1${SCOLOR}"
}

success() {
    echo -e "${GREEN}[SUCESSO] $1${SCOLOR}"
}

info() {
    echo -e "${CYAN}[INFO] $1${SCOLOR}"
}

debug() {
    [[ "${DEBUG:-0}" == "1" ]] && echo -e "${MAGENTA}[DEBUG] $1${SCOLOR}"
}

# Barra de progresso com timeout configurável (padrão: 600s)
fun_bar() {
    local cmd="$1"
    local desc="${2:-Processando}"
    local spinner="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    local i=0
    local timeout=600

    eval "$cmd" &
    local pid=$!

    # Oculta cursor
    tput civis 2>/dev/null || true
    echo -ne "${YELLOW}${desc}... [${SCOLOR}"

    local start_time=$(date +%s)
    while ps -p "$pid" >/dev/null 2>&1; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        if [[ $elapsed -gt $timeout ]]; then
            kill "$pid" 2>/dev/null || true
            die "Timeout: operação demorou mais de ${timeout}s"
        fi
        i=$(( (i + 1) % ${#spinner} ))
        echo -ne "${CYAN}${spinner:$i:1}${SCOLOR}"
        sleep 0.1
        echo -ne "\b"
    done

    wait "$pid"
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "${YELLOW}]${SCOLOR} ${GREEN}✓${SCOLOR}"
    else
        echo -e "${YELLOW}]${SCOLOR} ${RED}✗${SCOLOR}"
        die "Comando falhou: $cmd"
    fi
    tput cnorm 2>/dev/null || true
    return $exit_code
}

# ----------------------- Verificações Iniciais -------------------------
check_root() {
    [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."
}

check_bash() {
    if [[ "${BASH_VERSION%%.*}" -lt 4 ]]; then
        die "Bash 4.0+ é necessário. Versão atual: ${BASH_VERSION}"
    fi
}

check_virtualization() {
    # Verifica se TUN/TAP está disponível
    [[ -e /dev/net/tun ]] || die "TUN/TAP não disponível. Execute: modprobe tun"
    [[ -w /dev/net/tun ]] || die "Sem permissão de escrita em /dev/net/tun"
}

check_kernel_version() {
    local kernel_version=$(uname -r | cut -d. -f1,2)
    local min_version="4.9"
    if [[ "$(printf '%s\n' "$min_version" "$kernel_version" | sort -V | head -n1)" != "$min_version" ]]; then
        warn "Kernel $kernel_version detectado. Recomendado 4.9+"
    fi
}

# Detecta o sistema operacional (apenas Debian/Ubuntu suportado)
detect_os() {
    [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
    source /etc/os-release
    OS_ID="$ID"
    OS_VERSION="$VERSION_ID"
    OS_NAME="$PRETTY_NAME"
    case "$OS_ID" in
        ubuntu|debian)
            OS="debian"
            GROUPNAME="nogroup"
            if [[ "$OS_ID" == "ubuntu" && "${OS_VERSION%%.*}" -lt 20 ]]; then
                warn "Ubuntu $OS_VERSION detectado. Recomendado 20.04+"
            elif [[ "$OS_ID" == "debian" && "${OS_VERSION%%.*}" -lt 11 ]]; then
                warn "Debian $OS_VERSION detectado. Recomendado 11+"
            fi
            ;;
        *)
            die "Sistema operacional '$OS_ID' não suportado. Use Debian/Ubuntu."
            ;;
    esac
    info "Sistema detectado: $OS_NAME"
}

# Detecta layout do OpenVPN (systemd e caminhos)
detect_openvpn_layout() {
    OVPN_DIR="/etc/openvpn"
    mkdir -p "$OVPN_LOG_DIR"
    if systemctl list-unit-files 2>/dev/null | grep -q '^openvpn-server@\.service'; then
        SERVER_UNIT="openvpn-server@server"
        OVPN_CONF_DIR="$OVPN_DIR/server"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    elif systemctl list-unit-files 2>/dev/null | grep -q '^openvpn@\.service'; then
        SERVER_UNIT="openvpn@server"
        OVPN_CONF_DIR="$OVPN_DIR"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    else
        # Fallback para layout legacy
        SERVER_UNIT="openvpn@server"
        OVPN_CONF_DIR="$OVPN_DIR"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    fi
    mkdir -p "$OVPN_CONF_DIR"
    debug "Layout OpenVPN: unidade=${SERVER_UNIT} | conf=${SERVER_CONF}"
}

# -------------------------- Dependências -------------------------------
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "curl" "iptables-persistent" "netfilter-persistent")
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
        packages+=("nftables")
    fi
    # Verifica pacotes instalados
    for pkg in "${packages[@]}"; do
        if ! dpkg -l 2>/dev/null | grep -q "^ii.*$pkg"; then
            missing+=("$pkg")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        info "Instalando dependências: ${missing[*]}"
        export DEBIAN_FRONTEND=noninteractive
        echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
        echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
        fun_bar "apt-get update -qq" "Atualizando repositórios"
        fun_bar "apt-get install -y -qq ${missing[*]}" "Instalando pacotes"
    fi
    # Verificar versão do OpenVPN
    local ovpn_version=$(openvpn --version 2>/dev/null | head -1 | awk '{print $2}')
    [[ -z "$ovpn_version" ]] && die "OpenVPN não foi instalado corretamente"
    success "Todas as dependências verificadas! (OpenVPN $ovpn_version)"
}

# ------------------ Otimizações de Sistema e Módulos --------------------
optimize_system() {
    info "Aplicando otimizações de sistema..."
    # Carregar módulos necessários
    modprobe tcp_bbr 2>/dev/null || warn "Módulo tcp_bbr não carregado (BBR indisponível)"
    modprobe sch_fq 2>/dev/null || warn "Módulo fq não carregado"
    # Parâmetros de sysctl
    cat > /etc/sysctl.d/99-openvpn.conf << EOF
# OpenVPN Optimizations
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
net.ipv4.tcp_notsent_lowat = 16384
EOF
    # Aplicar configurações
    sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null 2>&1 || true
    # Aumentar limites de arquivo
    if ! grep -q "openvpn" /etc/security/limits.conf 2>/dev/null; then
        echo "* soft nofile 65536" >> /etc/security/limits.conf
        echo "* hard nofile 65536" >> /etc/security/limits.conf
    fi
    success "Otimizações aplicadas!"
}

# ------------------------- Funções Auxiliares --------------------------
get_public_ip() {
    local IP
    IP=$(curl -4 -s https://api.ipify.org 2>/dev/null) || \
    IP=$(curl -4 -s https://ifconfig.me 2>/dev/null) || \
    IP=$(curl -4 -s https://ipinfo.io/ip 2>/dev/null) || \
    IP=$(hostname -I | awk '{print $1}')
    echo "$IP"
}

get_public_ipv6() {
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        local IPV6
        IPV6=$(curl -6 -s https://api6.ipify.org 2>/dev/null) || \
        IPV6=$(curl -6 -s https://ifconfig.co 2>/dev/null) || \
        IPV6=$(ip -6 addr show scope global | grep -oP '(?<=inet6\s)[\da-f:]+' | head -1)
        [[ -z "$IPV6" ]] && warn "IPv6 detectado mas endereço público não encontrado."
        echo "$IPV6"
    fi
}

# ------------------------ Setup Easy-RSA -------------------------------
setup_easy_rsa() {
    local EASY_RSA_DIR="$OVPN_DIR/easy-rsa"
    info "Configurando PKI e certificados..."
    mkdir -p "$EASY_RSA_DIR"
    # Copiar Easy-RSA (path padrão em Debian/Ubuntu)
    if [[ -d "/usr/share/easy-rsa" ]]; then
        cp -r "/usr/share/easy-rsa"/* "$EASY_RSA_DIR/"
    else
        die "Easy-RSA não encontrado em /usr/share/easy-rsa"
    fi
    cd "$EASY_RSA_DIR" || die "Falha ao acessar $EASY_RSA_DIR"
    [[ ! -f "./easyrsa" ]] && die "Script easyrsa não encontrado"
    chmod +x "./easyrsa"
    # Configurar vars para curvas elípticas
    cat > vars << EOF
set_var EASYRSA_ALGO ec
set_var EASYRSA_CURVE secp384r1
set_var EASYRSA_DIGEST "sha512"
set_var EASYRSA_KEY_SIZE 4096
set_var EASYRSA_CA_EXPIRE 3650
set_var EASYRSA_CERT_EXPIRE 1825
set_var EASYRSA_CRL_DAYS 180
EOF
    # Inicializar PKI
    fun_bar "./easyrsa init-pki" "Inicializando PKI"
    # Criar CA
    fun_bar "echo 'OpenVPN-CA' | ./easyrsa build-ca nopass" "Criando Autoridade Certificadora"
    # Gerar certificado do servidor
    fun_bar "echo 'yes' | ./easyrsa build-server-full server nopass" "Gerando certificado do servidor"
    # Gerar Diffie-Hellman
    fun_bar "./easyrsa gen-dh" "Gerando parâmetro Diffie-Hellman"
    # Gerar tls-crypt key
    openvpn --genkey --secret tc.key
    # Copiar certificados para diretório de configuração
    cp pki/ca.crt pki/private/ca.key pki/issued/server.crt pki/private/server.key pki/dh.pem tc.key "$OVPN_CONF_DIR/"
    # Gerar CRL (revocation list) e colocar no local correto
    fun_bar "echo 'yes' | ./easyrsa gen-crl" "Gerando CRL"
    cp pki/crl.pem "$OVPN_CONF_DIR/"
    chmod 644 "$OVPN_CONF_DIR/crl.pem"
    success "PKI e certificados configurados."
}

# --------------------- Configuração do Servidor ------------------------
configure_server() {
    info "Configurando servidor OpenVPN..."
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    # Configuração do servidor com protocolo definido
    cat > "$SERVER_CONF" << EOF
# OpenVPN Server Configuration - TCP Mode
port $DEFAULT_PORT
proto $DEFAULT_PROTOCOL
dev tun

# Certificados
ca ca.crt
cert server.crt
key server.key
dh dh.pem

# Segurança moderna
tls-crypt tc.key
auth SHA512

# Criptografia de dados
cipher AES-256-GCM
ncp-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305

# TLS
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384

# Rede
topology subnet
server 10.8.0.0 255.255.255.0
EOF
    # IPv6
    if [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]]; then
        cat >> "$SERVER_CONF" << EOF
server-ipv6 fd42:42:42::/64
push "route-ipv6 ::/0"
push "dhcp-option DNS6 $DEFAULT_DNS_IPV6_1"
push "dhcp-option DNS6 $DEFAULT_DNS_IPV6_2"
EOF
    fi
    # Configurações de push e performance
    cat >> "$SERVER_CONF" << EOF

# Push para clientes
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS $DEFAULT_DNS1"
push "dhcp-option DNS $DEFAULT_DNS2"
push "block-outside-dns"

# Performance (otimizado para TCP)
sndbuf 0
rcvbuf 0
push "sndbuf 0"
push "rcvbuf 0"
txqueuelen 1000
mssfix 1420
tun-mtu 1500

# TCP específico
tcp-nodelay

# Persistência e logging
keepalive 10 120
persist-key
persist-tun
user nobody
group $GROUPNAME
status $OVPN_LOG_DIR/status.log
log-append $OVPN_LOG_DIR/openvpn.log
verb 3
mute 20

# Controle de clientes
max-clients 100
ifconfig-pool-persist $OVPN_CONF_DIR/ipp.txt
client-to-client
duplicate-cn

# CRL
crl-verify crl.pem
EOF
    success "Servidor configurado com protocolo $DEFAULT_PROTOCOL na porta $DEFAULT_PORT!"
}

# -------------------- Configuração do Firewall -------------------------
configure_firewall() {
    info "Configurando firewall..."
    # Detectar interface de saída padrão
    local IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1)
    [[ -z "$IFACE" ]] && die "Interface de rede não detectada"
    info "Interface principal: $IFACE"
    # Priorizar nftables se disponível
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
        info "Configurando nftables..."
        cat > /etc/nftables.conf << EOF
#!/usr/sbin/nft -f

flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy accept;
        iif "tun0" accept
        tcp dport $DEFAULT_PORT accept
    }
    chain forward {
        type filter hook forward priority 0; policy accept;
        iif "tun0" accept
        oif "tun0" accept
    }
}

table ip nat {
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "$IFACE" ip saddr 10.8.0.0/24 masquerade
    }
}
EOF
        if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
            cat >> /etc/nftables.conf << EOF

table ip6 nat {
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "$IFACE" ip6 saddr fd42:42:42::/64 masquerade
    }
}
EOF
        fi
        systemctl enable --now nftables
        nft -f /etc/nftables.conf
    else
        # Fallback para iptables
        info "Configurando iptables..."
        # Abrir porta TCP somente se a regra ainda não existir
        if ! iptables -C INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null; then
            iptables -A INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT
        fi
        # NAT e forward
        if ! iptables -t nat -C POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE 2>/dev/null; then
            iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        fi
        if ! iptables -C INPUT -i tun+ -j ACCEPT 2>/dev/null; then
            iptables -A INPUT -i tun+ -j ACCEPT
        fi
        if ! iptables -C FORWARD -i tun+ -j ACCEPT 2>/dev/null; then
            iptables -A FORWARD -i tun+ -j ACCEPT
        fi
        if ! iptables -C FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
            iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        fi
        if ! iptables -C FORWARD -i tun+ -o "$IFACE" -j ACCEPT 2>/dev/null; then
            iptables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        fi
        # IPv6 se disponível
        if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
            if ! ip6tables -C INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null; then
                ip6tables -A INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT
            fi
            if ! ip6tables -t nat -C POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE 2>/dev/null; then
                ip6tables -t nat -A POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE
            fi
            if ! ip6tables -C INPUT -i tun+ -j ACCEPT 2>/dev/null; then
                ip6tables -A INPUT -i tun+ -j ACCEPT
            fi
            if ! ip6tables -C FORWARD -i tun+ -j ACCEPT 2>/dev/null; then
                ip6tables -A FORWARD -i tun+ -j ACCEPT
            fi
            if ! ip6tables -C FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
                ip6tables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
            fi
            if ! ip6tables -C FORWARD -i tun+ -o "$IFACE" -j ACCEPT 2>/dev/null; then
                ip6tables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
            fi
        fi
        # Salvar regras
        mkdir -p /etc/iptables
        iptables-save > /etc/iptables/rules.v4
        [[ "$SUPPORTS_IPV6" == "yes" ]] && ip6tables-save > /etc/iptables/rules.v6
        systemctl enable --now netfilter-persistent
    fi
    success "Firewall configurado!"
}

# ------------------------- Criação de Cliente --------------------------
create_client() {
    local CLIENT_NAME="${1:-cliente1}"
    info "Criando cliente: $CLIENT_NAME"
    cd "$OVPN_DIR/easy-rsa/" || die "Diretório easy-rsa não encontrado"
    # Verificar se cliente já existe
    if [[ -f "pki/issued/${CLIENT_NAME}.crt" ]]; then
        warn "Cliente '$CLIENT_NAME' já existe"
        return
    fi
    fun_bar "echo 'yes' | ./easyrsa build-client-full '$CLIENT_NAME' nopass" "Gerando certificado do cliente"
    # Obter informações do servidor
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    # Criar diretório de clientes
    local CLIENT_DIR=~/ovpn-clients
    mkdir -p "$CLIENT_DIR"
    # Gerar configuração do cliente
    cat > "$CLIENT_DIR/${CLIENT_NAME}.ovpn" << EOF
# OpenVPN Client Configuration
client
dev tun
proto $DEFAULT_PROTOCOL
remote $IP $DEFAULT_PORT
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
cipher AES-256-GCM
verb 3
mute 20
tun-mtu 1500
mssfix 1420
sndbuf 0
rcvbuf 0

# TCP específico
tcp-nodelay

# Segurança adicional
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384

# Certificados embutidos
<ca>
$(cat "$OVPN_CONF_DIR/ca.crt")
</ca>
<cert>
$(cat "$OVPN_DIR/easy-rsa/pki/issued/${CLIENT_NAME}.crt")
</cert>
<key>
$(cat "$OVPN_DIR/easy-rsa/pki/private/${CLIENT_NAME}.key")
</key>
<tls-crypt>
$(cat "$OVPN_CONF_DIR/tc.key")
</tls-crypt>
EOF
    # Criar arquivo de informações do cliente
    cat > "$CLIENT_DIR/${CLIENT_NAME}-info.txt" << EOF
═══════════════════════════════════════════════════
Cliente VPN: ${CLIENT_NAME}
Criado em: $(date)
═══════════════════════════════════════════════════

INFORMAÇÕES DE CONEXÃO:
• Servidor: ${IP}
• Porta: ${DEFAULT_PORT}
• Protocolo: ${DEFAULT_PROTOCOL}
• DNS: Google (8.8.8.8, 8.8.4.4)
• Criptografia: AES-256-GCM

ARQUIVOS:
• Configuração: ${CLIENT_NAME}.ovpn

INSTRUÇÕES DE USO:
1. WINDOWS:
   - Baixe o OpenVPN GUI
   - Importe o arquivo .ovpn
2. MACOS:
   - Use Tunnelblick ou OpenVPN Connect
   - Importe o arquivo .ovpn
3. LINUX:
   - sudo openvpn --config ${CLIENT_NAME}.ovpn
   - Ou use NetworkManager
4. ANDROID/iOS:
   - Instale OpenVPN Connect
   - Importe o arquivo .ovpn
═══════════════════════════════════════════════════
EOF
    success "Cliente '$CLIENT_NAME' criado!"
    echo -e "${WHITE}Arquivo salvo em: ${GREEN}$CLIENT_DIR/${CLIENT_NAME}.ovpn${SCOLOR}"
}

# ----------------- Limpeza de Instalações Mal Sucedidas ----------------
# Esta função tenta remover quaisquer vestígios de uma instalação anterior
# do OpenVPN que possa ter falhado ou deixado o sistema em estado
# inconsistente. Ela remove serviços, arquivos de configuração,
# regras de firewall, diretórios de log e pacotes relacionados ao OpenVPN.
cleanup_failed_installation() {
    info "Limpando instalações anteriores de OpenVPN (se existirem)..."
    # Parar e desabilitar possíveis unidades do OpenVPN
    if systemctl list-unit-files | grep -q '^openvpn'; then
        systemctl stop "$SERVER_UNIT" 2>/dev/null || true
        systemctl disable "$SERVER_UNIT" 2>/dev/null || true
    fi
    # Remover diretórios de configuração
    rm -rf /etc/openvpn 2>/dev/null || true
    rm -rf "$OVPN_DIR/easy-rsa" 2>/dev/null || true
    # Remover logs e diretórios de clientes
    rm -rf "$OVPN_LOG_DIR" 2>/dev/null || true
    rm -rf ~/ovpn-clients 2>/dev/null || true
    # Limpar regras nftables se suportado
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
        nft flush ruleset 2>/dev/null || true
        rm -f /etc/nftables.conf 2>/dev/null || true
        systemctl disable nftables 2>/dev/null || true
    fi
    # Limpar regras iptables (IPv4)
    local IFACE
    IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1 || true)
    if [[ -n "$IFACE" ]]; then
        # Porta principal
        iptables -D INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null || true
        iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE 2>/dev/null || true
        iptables -D INPUT -i tun+ -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i tun+ -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
        iptables -D FORWARD -i tun+ -o "$IFACE" -j ACCEPT 2>/dev/null || true
    fi
    # Limpar regras ip6tables se IPv6 estiver ativo
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        if [[ -n "$IFACE" ]]; then
            ip6tables -D INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null || true
            ip6tables -t nat -D POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE 2>/dev/null || true
            ip6tables -D INPUT -i tun+ -j ACCEPT 2>/dev/null || true
            ip6tables -D FORWARD -i tun+ -j ACCEPT 2>/dev/null || true
            ip6tables -D FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
            ip6tables -D FORWARD -i tun+ -o "$IFACE" -j ACCEPT 2>/dev/null || true
        fi
    fi
    # Excluir arquivos persistentes e desabilitar serviços
    rm -f /etc/iptables/rules.v4 /etc/iptables/rules.v6 2>/dev/null || true
    systemctl disable netfilter-persistent 2>/dev/null || true
    # Remover pacotes relacionados
    if dpkg -l | grep -q '^ii.*openvpn'; then
        apt-get remove --purge -y openvpn easy-rsa 2>/dev/null || true
        apt-get autoremove -y 2>/dev/null || true
    fi
    success "Limpeza de instalações anteriores concluída."
}

# ------------------------ Iniciar Serviço -----------------------------
start_service() {
    info "Iniciando serviço OpenVPN..."
    systemctl daemon-reload
    systemctl enable --now "$SERVER_UNIT" || die "Falha ao iniciar OpenVPN"
    sleep 3
    if ! systemctl is-active --quiet "$SERVER_UNIT"; then
        journalctl -xeu "$SERVER_UNIT" --no-pager | tail -30 || true
        die "OpenVPN falhou ao iniciar. Verifique os logs acima."
    fi
    success "Serviço OpenVPN iniciado com sucesso!"
}

# ------------------- Menu de Confirmação ------------------------------
show_confirmation_menu() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║              INSTALADOR OPENVPN - CONFIRMAÇÃO              ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${YELLOW}O OpenVPN será instalado com as seguintes configurações:${SCOLOR}"
    echo -e "  • Porta: ${GREEN}$DEFAULT_PORT${SCOLOR}"
    echo -e "  • Protocolo: ${GREEN}$DEFAULT_PROTOCOL${SCOLOR}"
    echo -e "  • DNS: ${GREEN}$DEFAULT_DNS1, $DEFAULT_DNS2${SCOLOR}"
    echo -e "\n${WHITE}Deseja continuar?${SCOLOR}"
    echo -e "  ${GREEN}1.${SCOLOR} SIM, instalar"
    echo -e "  ${RED}0.${SCOLOR} Cancelar"
    echo -ne "${WHITE}Escolha: ${SCOLOR}"
    local choice
    read -r choice
    case "$choice" in
        1)
            return 0
            ;;
        0|*)
            echo -e "\n${YELLOW}Instalação cancelada.${SCOLOR}"
            exit 0
            ;;
    esac
}

# -------------------- Resumo da Instalação ----------------------------
show_installation_summary() {
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║   Instalação Concluída com Sucesso!    ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Resumo da Configuração:${SCOLOR}"
    echo -e "  • IP Público: ${GREEN}$IP${SCOLOR}"
    if [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]]; then
        echo -e "  • IPv6: ${GREEN}$IPV6${SCOLOR}"
    fi
    echo -e "  • Porta: ${GREEN}$DEFAULT_PORT${SCOLOR}"
    echo -e "  • Protocolo: ${GREEN}$DEFAULT_PROTOCOL${SCOLOR}"
    echo -e "  • Subnet VPN: ${GREEN}10.8.0.0/24${SCOLOR}"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  • Subnet IPv6: ${GREEN}fd42:42:42::/64${SCOLOR}"
    echo -e "  • DNS: ${GREEN}Google${SCOLOR}"
    echo -e "  • Criptografia: ${GREEN}AES-256-GCM${SCOLOR}"
    echo
    echo -e "${CYAN}Recursos Ativados:${SCOLOR}"
    echo -e "  ✓ TLS-Crypt (proteção DDoS)"
    echo -e "  ✓ Curvas Elípticas (ECDSA)"
    echo -e "  ✓ Perfect Forward Secrecy"
    echo -e "  ✓ Otimizações de kernel"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  ✓ Suporte IPv6"
    [[ "$SUPPORTS_NFTABLES" == "yes" ]] && echo -e "  ✓ NFTables"
    echo
    echo -e "${YELLOW}Arquivo do cliente inicial:${SCOLOR}"
    echo -e "  ${GREEN}~/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
    echo -e "${CYAN}Use o menu interativo para gerenciar clientes e configurações.${SCOLOR}"
    echo
}

# ---------------------- Verificar instalação --------------------------
check_if_installed() {
    if [[ -f "$SERVER_CONF" ]] || [[ -f "/etc/openvpn/server.conf" ]]; then
        echo -e "${YELLOW}OpenVPN já está instalado!${SCOLOR}"
        echo -e "${WHITE}Use o menu interativo para gerenciar.${SCOLOR}"
        exit 0
    fi
}

# -------------------- Limpeza de Instalação Falha --------------------
# Esta função remove restos de uma instalação mal sucedida do OpenVPN.
# Caso pacotes estejam parcialmente instalados ou diretórios de configuração
# permaneçam após uma falha, a função tenta removê-los para permitir uma
# reinstalação limpa. Ela também purga as regras de firewall criadas
# anteriormente para o OpenVPN.
cleanup_failed_installation() {
    info "Verificando e limpando possíveis instalações mal sucedidas de OpenVPN..."
    # Verifica se o pacote openvpn está instalado. Se estiver, remove-o.
    if dpkg -l 2>/dev/null | grep -q '^ii.*openvpn'; then
        warn "Pacote openvpn instalado, removendo para reinstalação limpa."
        apt-get remove --purge -y openvpn || warn "Falha ao remover pacote openvpn"
    fi
    # Verifica se easy-rsa está instalado e remove
    if dpkg -l 2>/dev/null | grep -q '^ii.*easy-rsa'; then
        warn "Pacote easy-rsa instalado, removendo para reinstalação limpa."
        apt-get remove --purge -y easy-rsa || true
    fi
    # Desabilita e remove serviços OpenVPN se existirem
    if systemctl list-unit-files 2>/dev/null | grep -q '^openvpn@'; then
        systemctl disable --now openvpn@server || true
    fi
    if systemctl list-unit-files 2>/dev/null | grep -q '^openvpn-server@'; then
        systemctl disable --now openvpn-server@server || true
    fi
    # Remove diretórios de configuração e logs
    rm -rf /etc/openvpn 2>/dev/null || true
    rm -rf "$OVPN_LOG_DIR" 2>/dev/null || true
    # Remove regras iptables específicas da porta padrão
    # ATENÇÃO: essa remoção é superficial e assume que a porta padrão
    #  não é utilizada por outros serviços. Ajuste se necessário.
    if iptables -C INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null; then
        iptables -D INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT || true
    fi
    if iptables -t nat -C POSTROUTING -s 10.8.0.0/24 -o "$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1)" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o "$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1)" -j MASQUERADE || true
    fi
    # Remove regras IPv6 se existirem
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        if ip6tables -C INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null; then
            ip6tables -D INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT || true
        fi
        if ip6tables -t nat -C POSTROUTING -s fd42:42:42::/64 -o "$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1)" -j MASQUERADE 2>/dev/null; then
            ip6tables -t nat -D POSTROUTING -s fd42:42:42::/64 -o "$(ip -4 route ls | grep default | grep -Po '(?<=dev )\S+' | head -1)" -j MASQUERADE || true
        fi
    fi
    # Remove configurações persistentes de iptables/nftables se existirem
    rm -f /etc/iptables/rules.v4 /etc/iptables/rules.v6 2>/dev/null || true
    rm -f /etc/nftables.conf 2>/dev/null || true
    success "Limpeza concluída. Se existia uma instalação parcial, ela foi removida."
}

# --------------------- Instalação Principal ---------------------------
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║        INSTALANDO OPENVPN              ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    # Mostrar capacidades do sistema
    echo -e "${CYAN}Capacidades do Sistema:${SCOLOR}"
    echo -e "  • CPU Cores: ${GREEN}$CPU_CORES${SCOLOR}"
    echo -e "  • IPv6: ${GREEN}$SUPPORTS_IPV6${SCOLOR}"
    echo -e "  • NFTables: ${GREEN}$SUPPORTS_NFTABLES${SCOLOR}"
    echo -e "  • Systemd-Resolved: ${GREEN}$SUPPORTS_SYSTEMD_RESOLVED${SCOLOR}"
    echo
    sleep 2
    # Antes de qualquer ação, certifique-se de que não há instalações parciais
    cleanup_failed_installation
    optimize_system
    check_dependencies
    setup_easy_rsa
    configure_server
    configure_firewall
    create_client "cliente1"
    start_service
    show_installation_summary
}

# --------------------------- Função Principal -------------------------
main() {
    check_root
    check_bash
    check_virtualization
    check_kernel_version
    # Executar rotina de limpeza antes de detectar o sistema
    cleanup_failed_installation
    detect_os
    detect_openvpn_layout
    check_if_installed
    show_confirmation_menu
    install_openvpn
}

# Executar a função principal
main "$@"
