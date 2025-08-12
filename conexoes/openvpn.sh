#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager - Versão Moderna v3.1 (2025-08)
# Otimizado para sistemas Linux modernos (2024+)
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Ajustes: correções de proto, unidade systemd, firewall, compat 2.6
# =================================================================

# --- Variáveis de Cor ---
readonly RED=$'\e[1;31m'
readonly GREEN=$'\e[1;32m'
readonly YELLOW=$'\e[1;33m'
readonly BLUE=$'\e[1;34m'
readonly CYAN=$'\e[1;36m'
readonly WHITE=$'\e[1;37m'
readonly MAGENTA=$'\e[1;35m'
readonly SCOLOR=$'\e[0m'

# --- Configurações Automáticas Modernas ---
readonly AUTO_PORT="1194"
readonly AUTO_PROTOCOL="udp"  # UDP é mais eficiente para VPN
readonly AUTO_DNS1="1.1.1.1"   # Cloudflare DNS
readonly AUTO_DNS2="1.0.0.1"
readonly AUTO_DNS_IPV6_1="2606:4700:4700::1111"
readonly AUTO_DNS_IPV6_2="2606:4700:4700::1001"

# --- Detecção de Capacidades do Sistema ---
readonly SUPPORTS_IPV6=$(test -f /proc/net/if_inet6 && echo "yes" || echo "no")
readonly SUPPORTS_NFTABLES=$(command -v nft >/dev/null 2>&1 && echo "yes" || echo "no")
readonly SUPPORTS_SYSTEMD_RESOLVED=$(systemctl is-active systemd-resolved >/dev/null 2>&1 && echo "yes" || echo "no")
readonly CPU_CORES=$(nproc 2>/dev/null || echo "1")

# Variáveis globais de layout/paths do OpenVPN (definidas em detect_openvpn_layout)
OVPN_DIR=""
OVPN_CONF_DIR=""
OVPN_LOG_DIR="/var/log/openvpn"
SERVER_CONF=""
SERVER_UNIT=""

# --- Funções de Utilidade ---
die() {
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

# Função de barra de progresso
fun_bar() {
    local cmd="$1"
    local desc="${2:-Processando}"
    local spinner="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    local i=0
    local timeout=300
    
    eval "$cmd" &
    local pid=$!
    
    tput civis
    echo -ne "${YELLOW}${desc}... [${SCOLOR}"
    
    local start_time
    start_time=$(date +%s)
    while ps -p "$pid" > /dev/null; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [[ $elapsed -gt $timeout ]]; then
            kill $pid 2>/dev/null
            tput cnorm
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
        tput cnorm
        die "Comando falhou: $cmd"
    fi
    
    tput cnorm
    return $exit_code
}

# --- Verificações Iniciais ---
check_root() {
    [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."
}

check_bash() {
    if [[ "${BASH_VERSION%%.*}" -lt 4 ]]; then
        die "Bash 4.0+ é necessário. Versão atual: ${BASH_VERSION}"
    fi
}

check_virtualization() {
    if [[ -f /proc/user_beancounters ]]; then
        warn "OpenVZ detectado. Pode haver limitações."
    fi
    
    if ! [[ -e /dev/net/tun ]]; then
        die "TUN/TAP não disponível. Execute: modprobe tun"
    fi
    
    if [[ ! -w /dev/net/tun ]]; then
        die "Sem permissão de escrita em /dev/net/tun"
    fi
}

check_kernel_version() {
    local kernel_version min_version
    kernel_version=$(uname -r | cut -d. -f1,2)
    min_version="4.9"
    
    if [[ "$(printf '%s\n' "$min_version" "$kernel_version" | sort -V | head -n1)" != "$min_version" ]]; then
        warn "Kernel $kernel_version detectado. Recomendado 4.9+"
    fi
}

# --- Detecção de Sistema Operacional ---
detect_os() {
    [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
    # shellcheck source=/dev/null
    source /etc/os-release
    
    OS_ID="$ID"
    OS_VERSION="$VERSION_ID"
    OS_NAME="$PRETTY_NAME"
    
    case "$OS_ID" in
        ubuntu)
            OS="debian"
            GROUPNAME="nogroup"
            if [[ "${OS_VERSION%%.*}" -lt 20 ]]; then
                warn "Ubuntu $OS_VERSION detectado. Recomendado 20.04+"
            fi
            ;;
        debian)
            OS="debian"
            GROUPNAME="nogroup"
            if [[ "${OS_VERSION%%.*}" -lt 11 ]]; then
                warn "Debian $OS_VERSION detectado. Recomendado 11+"
            fi
            ;;
        centos|rhel|rocky|almalinux|alpine)
            OS="centos"
            GROUPNAME="nobody"
            if [[ "${OS_VERSION%%.*}" -lt 8 ]]; then
                warn "CentOS/RHEL $OS_VERSION detectado. Recomendado 8+"
            fi
            ;;
        fedora)
            OS="centos"
            GROUPNAME="nobody"
            ;;
        *)
            die "Sistema operacional '$OS_ID' não suportado."
            ;;
    esac
    
    info "Sistema detectado: $OS_NAME"
}

# --- Detectar layout do OpenVPN (systemd e caminhos) ---
detect_openvpn_layout() {
    OVPN_DIR="/etc/openvpn"
    mkdir -p "$OVPN_LOG_DIR"
    
    # Detecta qual unidade systemd existe
    if systemctl list-unit-files | grep -q '^openvpn-server@\.service'; then
        SERVER_UNIT="openvpn-server@server"
        OVPN_CONF_DIR="$OVPN_DIR/server"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    elif systemctl list-unit-files | grep -q '^openvpn@\.service'; then
        SERVER_UNIT="openvpn@server"
        OVPN_CONF_DIR="$OVPN_DIR"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    else
        # Fallback: assume layout legacy
        SERVER_UNIT="openvpn@server"
        OVPN_CONF_DIR="$OVPN_DIR"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    fi
    
    mkdir -p "$OVPN_CONF_DIR"
    info "Layout OpenVPN: unidade=${SERVER_UNIT} | conf=${SERVER_CONF}"
}

# --- Instalação de Dependências ---
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "lsof" "curl" "qrencode")
    
    if [[ "$OS" == "debian" ]]; then
        packages+=("iptables-persistent" "netfilter-persistent")
        [[ "$SUPPORTS_NFTABLES" == "yes" ]] && packages+=("nftables")
    elif [[ "$OS" == "centos" ]]; then
        packages+=("firewalld")
    fi
    
    for pkg in "${packages[@]}"; do
        if [[ "$OS" == "debian" ]]; then
            dpkg -l | grep -q "^ii\s\+$pkg\b" || missing+=("$pkg")
        elif [[ "$OS" == "centos" ]]; then
            rpm -qa | grep -q "^$pkg" || missing+=("$pkg")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        info "Instalando dependências: ${missing[*]}"
        if [[ "$OS" == "debian" ]]; then
            export DEBIAN_FRONTEND=noninteractive
            echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
            echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
            fun_bar "apt-get update -qq" "Atualizando repositórios"
            fun_bar "apt-get install -y -qq ${missing[*]}" "Instalando pacotes"
        elif [[ "$OS" == "centos" ]]; then
            if ! yum list installed epel-release >/dev/null 2>&1; then
                fun_bar "yum install -y epel-release" "Instalando EPEL"
            fi
            fun_bar "yum install -y ${missing[*]}" "Instalando pacotes"
        fi
    fi
    
    local ovpn_version
    ovpn_version=$(openvpn --version 2>/dev/null | head -1 | awk '{print $2}')
    [[ -z "$ovpn_version" ]] && die "OpenVPN não foi instalado corretamente"
    
    success "Dependências OK (OpenVPN ${ovpn_version})"
}

# --- Otimização de Performance do Sistema ---
optimize_system() {
    info "Aplicando otimizações de sistema..."
    cat > /etc/sysctl.d/99-openvpn.conf << 'EOF'
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
    sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null 2>&1
    
    if ! grep -q "^\* soft nofile 65536" /etc/security/limits.conf 2>/dev/null; then
        echo "* soft nofile 65536" >> /etc/security/limits.conf
        echo "* hard nofile 65536" >> /etc/security/limits.conf
    fi
    
    success "Otimizações aplicadas!"
}

# --- Instalação Principal do OpenVPN ---
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║   OpenVPN Modern Installer v3.1        ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    
    echo -e "${CYAN}Capacidades do Sistema:${SCOLOR}"
    echo -e "  ${WHITE}• CPU Cores:${SCOLOR} ${GREEN}$CPU_CORES${SCOLOR}"
    echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$SUPPORTS_IPV6${SCOLOR}"
    echo -e "  ${WHITE}• NFTables:${SCOLOR} ${GREEN}$SUPPORTS_NFTABLES${SCOLOR}"
    echo -e "  ${WHITE}• Systemd-Resolved:${SCOLOR} ${GREEN}$SUPPORTS_SYSTEMD_RESOLVED${SCOLOR}"
    echo
    
    info "Configurações automáticas:"
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT${SCOLOR}"
    echo -e "  ${WHITE}• Protocolo:${SCOLOR} ${GREEN}$AUTO_PROTOCOL (IPv4)${SCOLOR}"
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Cloudflare ($AUTO_DNS1, $AUTO_DNS2)${SCOLOR}"
    echo -e "  ${WHITE}• Criptografia:${SCOLOR} ${GREEN}AES-256-GCM + ChaCha20-Poly1305${SCOLOR}"
    echo
    
    sleep 1
    
    optimize_system
    
    local EASY_RSA_DIR="$OVPN_DIR/easy-rsa"
    info "Criando estrutura de diretórios..."
    mkdir -p "$EASY_RSA_DIR" "$OVPN_CONF_DIR" /etc/openvpn/client "$OVPN_LOG_DIR"
    
    # Copiar Easy-RSA
    local ersa_src=""
    for dir in /usr/share/easy-rsa /usr/lib/easy-rsa /usr/lib64/easy-rsa; do
        [[ -d "$dir" ]] && ersa_src="$dir" && break
    done
    [[ -z "$ersa_src" ]] && die "Easy-RSA não encontrado"
    cp -r "$ersa_src"/* "$EASY_RSA_DIR/"
    chmod +x "$EASY_RSA_DIR/easyrsa"
    
    cd "$EASY_RSA_DIR" || die "Falha ao acessar $EASY_RSA_DIR"
    
    # Vars utilizando EC (ECDSA)
    cat > vars << EOF
set_var EASYRSA_ALGO ec
set_var EASYRSA_CURVE secp384r1
set_var EASYRSA_DIGEST "sha512"
set_var EASYRSA_KEY_SIZE 4096
set_var EASYRSA_CA_EXPIRE 3650
set_var EASYRSA_CERT_EXPIRE 1825
set_var EASYRSA_CRL_DAYS 180
EOF
    
    fun_bar "./easyrsa init-pki" "Inicializando PKI"
    fun_bar "echo 'OpenVPN-CA' | ./easyrsa build-ca nopass" "Criando Autoridade Certificadora"
    fun_bar "echo 'yes' | ./easyrsa build-server-full server nopass" "Gerando certificado do servidor"
    
    # DH (não necessário para ECDSA, mas mantemos compatibilidade; usar 'dh none' seria suficiente)
    if [[ -f /usr/share/easy-rsa/dh2048.pem ]]; then
        cp /usr/share/easy-rsa/dh2048.pem pki/dh.pem
        info "Usando parâmetros DH pré-computados"
    else
        fun_bar "./easyrsa gen-dh" "Gerando parâmetros Diffie-Hellman"
    fi
    
    # tls-crypt
    info "Gerando chave tls-crypt..."
    openvpn --genkey secret pki/tc.key || die "Falha ao gerar tls-crypt"
    
    # Copiar para o diretório da config do servidor
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/tc.key "$OVPN_CONF_DIR/"
    chmod 600 "$OVPN_CONF_DIR/"*.{key,crt,pem}
    
    configure_modern_server
    configure_modern_firewall
    
    info "Iniciando OpenVPN..."
    systemctl enable --now "$SERVER_UNIT" || die "Falha ao iniciar OpenVPN"
    
    sleep 2
    if ! systemctl is-active --quiet "$SERVER_UNIT"; then
        journalctl -xeu "$SERVER_UNIT" --no-pager | tail -30
        die "OpenVPN falhou ao iniciar. Verifique os logs acima."
    fi
    
    success "OpenVPN instalado com sucesso!"
    info "Criando cliente inicial..."
    create_modern_client "cliente1"
    show_installation_summary
}

# --- Configuração Moderna do Servidor ---
configure_modern_server() {
    info "Configurando servidor..."
    
    local use_ipv6="$SUPPORTS_IPV6"
    
    # Configuração do servidor (IPv4 listener; IPv6 dentro do túnel se disponível)
    cat > "$SERVER_CONF" << EOF
# OpenVPN Modern Configuration
port $AUTO_PORT
proto ${AUTO_PROTOCOL}
dev tun

# Certificados
ca ca.crt
cert server.crt
key server.key
dh dh.pem

# Segurança moderna
tls-crypt tc.key
auth SHA512

# Criptografia de dados (OpenVPN 2.5/2.6)
data-ciphers AES-256-GCM:CHACHA20-POLY1305:AES-128-GCM
data-ciphers-fallback AES-256-GCM
# Para compat com 2.4/2.5 (aviso em 2.6, mas inofensivo)
ncp-ciphers AES-256-GCM:CHACHA20-POLY1305:AES-128-GCM

# TLS
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384
tls-ciphersuites TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256

# Rede
topology subnet
server 10.8.0.0 255.255.255.0
EOF

    if [[ "$use_ipv6" == "yes" ]]; then
        cat >> "$SERVER_CONF" << EOF
server-ipv6 fd42:42:42::/64
push "route-ipv6 ::/0"
push "dhcp-option DNS6 $AUTO_DNS_IPV6_1"
push "dhcp-option DNS6 $AUTO_DNS_IPV6_2"
EOF
    fi

    cat >> "$SERVER_CONF" << EOF

# Push para clientes
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS $AUTO_DNS1"
push "dhcp-option DNS $AUTO_DNS2"
push "block-outside-dns"

# Performance
sndbuf 0
rcvbuf 0
push "sndbuf 0"
push "rcvbuf 0"
txqueuelen 1000
mssfix 1420
tun-mtu 1500

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

    # Gerar CRL
    cd "$OVPN_DIR/easy-rsa/" || die "Diretório easy-rsa não encontrado"
    ./easyrsa gen-crl
    cp pki/crl.pem "$OVPN_CONF_DIR/"
    chmod 644 "$OVPN_CONF_DIR/crl.pem"
    
    success "Servidor configurado!"
}

# --- Configuração do Firewall ---
configure_modern_firewall() {
    info "Configurando firewall..."
    local IFACE
    IFACE=$(ip -4 route ls | awk '/default/ {print $5; exit}')
    [[ -z "$IFACE" ]] && die "Interface de rede não detectada"
    info "Interface principal: $IFACE"
    
    if [[ "$SUPPORTS_NFTABLES" == "yes" && "$OS" == "debian" ]]; then
        info "Configurando nftables..."
        cat > /etc/nftables.conf << EOF
#!/usr/sbin/nft -f

flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy accept;
        iif "tun0" accept
        udp dport $AUTO_PORT accept
        tcp dport $AUTO_PORT accept
    }
    chain forward {
        type filter hook forward priority 0; policy accept;
        iif "tun0" accept
        oif "tun0" accept
        ct state related,established accept
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
        nft -f /etc/nftables.conf || die "Falha ao aplicar regras nftables"
    else
        info "Configurando iptables..."
        # Abrir porta de entrada (FALTAVA NO SCRIPT ORIGINAL)
        iptables -A INPUT -p "$AUTO_PROTOCOL" --dport "$AUTO_PORT" -j ACCEPT
        # Se desejar, abrir TCP também (mesmo que não seja usado)
        iptables -A INPUT -p tcp --dport "$AUTO_PORT" -j ACCEPT
        
        # NAT e forward
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        
        if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
            # Abrir porta UDP/IPv6 somente se você futuramente migrar para proto udp6.
            ip6tables -A INPUT -p "$AUTO_PROTOCOL" --dport "$AUTO_PORT" -j ACCEPT
            ip6tables -t nat -A POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE
            ip6tables -A INPUT -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
            ip6tables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        fi
        
        if [[ "$OS" == "debian" ]]; then
            mkdir -p /etc/iptables
            iptables-save > /etc/iptables/rules.v4
            [[ "$SUPPORTS_IPV6" == "yes" ]] && ip6tables-save > /etc/iptables/rules.v6
            systemctl enable --now netfilter-persistent
        elif [[ "$OS" == "centos" ]]; then
            firewall-cmd --add-service=openvpn --permanent || true
            firewall-cmd --add-port=$AUTO_PORT/udp --permanent || true
            firewall-cmd --add-port=$AUTO_PORT/tcp --permanent || true
            firewall-cmd --add-masquerade --permanent || true
            firewall-cmd --reload || true
        fi
    fi
    
    success "Firewall configurado!"
}

# --- Criação de Cliente ---
create_modern_client() {
    local CLIENT_NAME="$1"
    
    if [[ -z "$CLIENT_NAME" ]]; then
        echo -ne "${WHITE}Nome do cliente: ${SCOLOR}"
        read -r CLIENT_NAME
        [[ -z "$CLIENT_NAME" ]] && warn "Nome inválido" && return
    fi
    
    CLIENT_NAME=$(echo "$CLIENT_NAME" | sed 's/[^a-zA-Z0-9_-]//g')
    cd "$OVPN_DIR/easy-rsa/" || die "Diretório easy-rsa não encontrado"
    
    if [[ -f "pki/issued/${CLIENT_NAME}.crt" ]]; then
        warn "Cliente '$CLIENT_NAME' já existe"
        return
    fi
    
    fun_bar "echo 'yes' | ./easyrsa build-client-full '$CLIENT_NAME' nopass" "Gerando certificado"
    
    local IP IPV6 PORT PROTO
    IP=$(get_public_ip)
    IPV6=$(get_public_ipv6)
    PORT=$(grep -E '^\s*port\s+' "$SERVER_CONF" | awk '{print $2}')
    PROTO=$(grep -E '^\s*proto\s+' "$SERVER_CONF" | awk '{print $2}')
    
    local CLIENT_DIR=~/ovpn-clients
    mkdir -p "$CLIENT_DIR"
    
    cat > "$CLIENT_DIR/${CLIENT_NAME}.ovpn" << EOF
# OpenVPN Modern Client Configuration
client
dev tun
proto ${PROTO}
remote ${IP} ${PORT}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server

# Criptografia alinhada ao servidor
data-ciphers AES-256-GCM:CHACHA20-POLY1305:AES-128-GCM
auth SHA512

verb 3
mute 20
tun-mtu 1500
mssfix 1420
sndbuf 0
rcvbuf 0

# TLS
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384
tls-ciphersuites TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256

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

    # Se e quando mudar o servidor para proto udp6, adicione esta linha remota IPv6:
    # if [[ "$PROTO" == "udp6" || "$PROTO" == "tcp6" ]]; then
    #     echo "remote ${IPV6} ${PORT}" >> "$CLIENT_DIR/${CLIENT_NAME}.ovpn"
    # fi
    
    if command -v qrencode >/dev/null 2>&1; then
        info "Gerando QR Code..."
        qrencode -o "$CLIENT_DIR/${CLIENT_NAME}-qr.png" < "$CLIENT_DIR/${CLIENT_NAME}.ovpn"
        success "QR Code salvo em: $CLIENT_DIR/${CLIENT_NAME}-qr.png"
    fi
    
    cat > "$CLIENT_DIR/${CLIENT_NAME}-info.txt" << EOF
═══════════════════════════════════════════════════
Cliente VPN: ${CLIENT_NAME}
Criado em: $(date)
═══════════════════════════════════════════════════

INFORMAÇÕES DE CONEXÃO:
• Servidor: ${IP}
• Porta: ${PORT}
• Protocolo: ${PROTO}
• Criptografia: AES-256-GCM/ChaCha20

ARQUIVOS:
• Configuração: ${CLIENT_NAME}.ovpn
• QR Code: ${CLIENT_NAME}-qr.png (se disponível)

INSTRUÇÕES DE USO:

1. WINDOWS:
   - Instale OpenVPN GUI
   - Importe o arquivo .ovpn

2. MACOS:
   - Use Tunnelblick ou OpenVPN Connect
   - Importe o arquivo .ovpn

3. LINUX:
   - sudo openvpn --config ${CLIENT_NAME}.ovpn
   - Ou use NetworkManager

4. ANDROID/iOS:
   - Instale OpenVPN Connect
   - Escaneie o QR Code ou importe .ovpn

═══════════════════════════════════════════════════
EOF
    
    success "Cliente '$CLIENT_NAME' criado!"
    echo -e "${WHITE}Arquivos salvos em: ${GREEN}$CLIENT_DIR/${SCOLOR}"
}

# --- Funções Auxiliares ---
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
        IPV6=$(ip -6 addr show scope global | awk '/inet6/ {print $2}' | cut -d/ -f1 | head -1)
        echo "$IPV6"
    fi
}

# --- Backup ---
backup_openvpn() {
    local BACKUP_DIR="/root/openvpn-backup-$(date +%Y%m%d-%H%M%S)"
    info "Criando backup em $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    cp -r "$OVPN_DIR" "$BACKUP_DIR/"
    [[ -d ~/ovpn-clients ]] && cp -r ~/ovpn-clients "$BACKUP_DIR/"
    tar -czf "${BACKUP_DIR}.tar.gz" -C "$(dirname "$BACKUP_DIR")" "$(basename "$BACKUP_DIR")"
    rm -rf "$BACKUP_DIR"
    success "Backup salvo em: ${BACKUP_DIR}.tar.gz"
}

# --- Status ---
show_status() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║        Status do OpenVPN               ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    
    if systemctl is-active --quiet "$SERVER_UNIT"; then
        echo -e "${GREEN}● Serviço: ATIVO${SCOLOR}"
        local uptime
        uptime=$(systemctl show "$SERVER_UNIT" --property=ActiveEnterTimestamp | cut -d= -f2)
        echo -e "${WHITE}  Uptime: ${CYAN}$uptime${SCOLOR}"
        
        if [[ -f "$OVPN_LOG_DIR/status.log" ]]; then
            local clients
            clients=$(grep -c "^CLIENT_LIST" "$OVPN_LOG_DIR/status.log" 2>/dev/null || echo "0")
            echo -e "${WHITE}  Clientes conectados: ${GREEN}$clients${SCOLOR}"
            if [[ "$clients" -gt 0 ]]; then
                echo -e "\n${YELLOW}Clientes ativos:${SCOLOR}"
                grep "^CLIENT_LIST" "$OVPN_LOG_DIR/status.log" | awk -F',' '{print "  • " $2 " - IP: " $3}'
            fi
        fi
        
        echo -e "\n${CYAN}Uso de recursos:${SCOLOR}"
        local pid
        pid=$(pgrep -f "openvpn.*server.conf")
        if [[ -n "$pid" ]]; then
            ps -p "$pid" -o %cpu,%mem,rss --no-headers | while read -r cpu mem rss; do
                echo -e "  CPU: ${WHITE}${cpu}%${SCOLOR} | RAM: ${WHITE}${mem}%${SCOLOR} (${rss} KB)"
            done
        fi
        
        if [[ -f /proc/net/dev ]]; then
            echo -e "\n${CYAN}Tráfego (tun0):${SCOLOR}"
            local stats
            stats=$(grep "tun0" /proc/net/dev | awk '{printf "  RX: %.2f MB | TX: %.2f MB", $2/1048576, $10/1048576}')
            [[ -n "$stats" ]] && echo -e "${WHITE}$stats${SCOLOR}" || echo -e "${WHITE}  Sem dados.${SCOLOR}"
        fi
    else
        echo -e "${RED}● Serviço: INATIVO${SCOLOR}"
        journalctl -xeu "$SERVER_UNIT" --no-pager | tail -20
    fi
    
    echo
    echo -e "${CYAN}Pressione ENTER para voltar...${SCOLOR}"
    read -r
}

# --- Resumo ---
show_installation_summary() {
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║   Instalação Concluída com Sucesso!    ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Resumo da Configuração:${SCOLOR}"
    echo -e "  ${WHITE}• IP Público:${SCOLOR} ${GREEN}$(get_public_ip)${SCOLOR}"
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        local ipv6
        ipv6=$(get_public_ipv6)
        [[ -n "$ipv6" ]] && echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$ipv6${SCOLOR}"
    fi
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT ($AUTO_PROTOCOL)${SCOLOR}"
    echo -e "  ${WHITE}• Subnet VPN:${SCOLOR} ${GREEN}10.8.0.0/24${SCOLOR}"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  ${WHITE}• Subnet IPv6:${SCOLOR} ${GREEN}fd42:42:42::/64${SCOLOR}"
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Cloudflare${SCOLOR}"
    echo -e "  ${WHITE}• Criptografia:${SCOLOR} ${GREEN}AES-256-GCM / ChaCha20${SCOLOR}"
    echo
    echo -e "${CYAN}Recursos Modernos Ativados:${SCOLOR}"
    echo -e "  ✓ TLS-Crypt (proteção DDoS)"
    echo -e "  ✓ Curvas Elípticas (ECDSA)"
    echo -e "  ✓ Perfect Forward Secrecy"
    [[ "$CPU_CORES" -gt 1 ]] && echo -e "  ✓ Otimizações de kernel (BBR, fq)"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  ✓ Suporte IPv6 dentro do túnel"
    [[ "$SUPPORTS_NFTABLES" == "yes" ]] && echo -e "  ✓ NFTables (se disponível)"
    echo
    echo -e "${YELLOW}Arquivo do cliente:${SCOLOR}"
    echo -e "  ${GREEN}~/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
}

# --- Revogação ---
revoke_client() {
    cd "$OVPN_DIR/easy-rsa/" || die "Diretório easy-rsa não encontrado"
    local clients=()
    while IFS= read -r file; do
        local client
        client=$(basename "$file" .crt)
        [[ "$client" != "server" ]] && clients+=("$client")
    done < <(find pki/issued -name "*.crt" 2>/dev/null)
    
    if [[ ${#clients[@]} -eq 0 ]]; then
        warn "Nenhum cliente para revogar"
        return
    fi
    
    echo -e "${YELLOW}Selecione o cliente a revogar:${SCOLOR}"
    for i in "${!clients[@]}"; do
        echo " $((i + 1))) ${clients[$i]}"
    done
    echo -ne "${WHITE}Número: ${SCOLOR}"
    read -r choice
    
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#clients[@]} )); then
        warn "Seleção inválida"
        return
    fi
    
    local CLIENT="${clients[$((choice - 1))]}"
    echo -ne "${RED}Revogar '$CLIENT'? [s/N]: ${SCOLOR}"
    read -r confirm
    
    if [[ "$confirm" =~ ^[sS]$ ]]; then
        backup_openvpn
        fun_bar "echo 'yes' | ./easyrsa revoke '$CLIENT'" "Revogando certificado"
        fun_bar "./easyrsa gen-crl" "Atualizando CRL"
        cp pki/crl.pem "$OVPN_CONF_DIR/"
        systemctl restart "$SERVER_UNIT"
        rm -f ~/ovpn-clients/"${CLIENT}"*
        success "Cliente '$CLIENT' revogado!"
    else
        warn "Operação cancelada"
    fi
}

# --- Desinstalação ---
uninstall_openvpn() {
    echo -ne "${RED}ATENÇÃO: Isso removerá TUDO! Continuar? [s/N]: ${SCOLOR}"
    read -r confirm
    
    if [[ "$confirm" =~ ^[sS]$ ]]; then
        backup_openvpn
        info "Parando serviços..."
        systemctl stop "$SERVER_UNIT" 2>/dev/null
        systemctl disable "$SERVER_UNIT" 2>/dev/null
        
        info "Removendo pacotes..."
        if [[ "$OS" == "debian" ]]; then
            apt-get remove --purge -y openvpn easy-rsa
            apt-get autoremove -y
        elif [[ "$OS" == "centos" ]]; then
            yum remove -y openvpn easy-rsa
        fi
        
        info "Limpando firewall..."
        if [[ "$SUPPORTS_NFTABLES" == "yes" ]] && [[ -f /etc/nftables.conf ]]; then
            rm -f /etc/nftables.conf
            systemctl stop nftables
        else
            iptables -t nat -F || true
            iptables -F || true
            if [[ "$OS" == "debian" ]]; then
                mkdir -p /etc/iptables
                > /etc/iptables/rules.v4
                > /etc/iptables/rules.v6
            fi
        fi
        
        info "Removendo arquivos..."
        rm -rf "$OVPN_DIR"
        rm -rf ~/ovpn-clients
        rm -f /etc/sysctl.d/99-openvpn.conf
        sysctl -p >/dev/null 2>&1
        
        success "OpenVPN removido completamente!"
        info "Backup salvo em /root/openvpn-backup-*.tar.gz"
    else
        warn "Desinstalação cancelada"
    fi
}

# --- Menu Principal ---
main_menu() {
    while true; do
        clear
        echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
        echo -e "${BLUE}║   OpenVPN Modern Manager v3.1          ║${SCOLOR}"
        echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
        echo -e "${CYAN}Sistema: $OS_NAME${SCOLOR}"
        echo
        
        if systemctl is-active --quiet "$SERVER_UNIT" 2>/dev/null; then
            local ip port proto clients_count
            ip=$(get_public_ip)
            port=$(grep -E '^\s*port\s+' "$SERVER_CONF" 2>/dev/null | awk '{print $2}')
            proto=$(grep -E '^\s*proto\s+' "$SERVER_CONF" 2>/dev/null | awk '{print $2}')
            clients_count=$(find "$OVPN_DIR/easy-rsa/pki/issued" -name "*.crt" 2>/dev/null | grep -cv server)
            
            echo -e "${GREEN}● OpenVPN: ATIVO${SCOLOR}"
            echo -e "${WHITE}  Servidor: $ip:$port ($proto)${SCOLOR}"
            echo -e "${WHITE}  Clientes criados: $clients_count${SCOLOR}"
            echo
            echo -e "${YELLOW}1)${SCOLOR} Criar novo cliente"
            echo -e "${YELLOW}2)${SCOLOR} Revogar cliente"
            echo -e "${YELLOW}3)${SCOLOR} Mostrar status detalhado"
            echo -e "${YELLOW}4)${SCOLOR} Fazer backup"
            echo -e "${YELLOW}5)${SCOLOR} Desinstalar OpenVPN"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        else
            echo -e "${RED}● OpenVPN: NÃO ATIVO/INSTALADO${SCOLOR}"
            echo
            echo -e "${YELLOW}1)${SCOLOR} Instalar OpenVPN (Automático)"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        fi
        
        echo
        echo -ne "${WHITE}Opção: ${SCOLOR}"
        read -r choice
        
        if systemctl is-active --quiet "$SERVER_UNIT" 2>/dev/null; then
            case "$choice" in
                1) create_modern_client ;;
                2) revoke_client ;;
                3) show_status ;;
                4) backup_openvpn ;;
                5) uninstall_openvpn && break ;;
                0) 
                    echo -e "\n${GREEN}Obrigado por usar o OpenVPN Modern Manager!${SCOLOR}"
                    exit 0
                    ;;
                *) warn "Opção inválida" ;;
            esac
        else
            case "$choice" in
                1) install_openvpn ;;
                0) 
                    echo -e "\n${GREEN}Até logo!${SCOLOR}"
                    exit 0
                    ;;
                *) warn "Opção inválida" ;;
            esac
        fi
        
        if [[ -n "$choice" ]] && [[ "$choice" != "0" ]] && [[ "$choice" != "5" ]]; then
            echo
            echo -e "${CYAN}Pressione ENTER para continuar...${SCOLOR}"
            read -r
        fi
    done
}

# --- Ponto de Entrada ---
main() {
    check_root
    check_bash
    check_virtualization
    check_kernel_version
    detect_os
    check_dependencies
    detect_openvpn_layout
    main_menu
}

trap 'echo -e "\n${RED}Script interrompido!${SCOLOR}"; tput cnorm; exit 130' INT TERM
main "$@"
