#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager - Versão Moderna v3.0
# Otimizado para sistemas Linux modernos (2024+)
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
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
readonly AUTO_DNS1="1.1.1.1"   # Cloudflare DNS (mais rápido)
readonly AUTO_DNS2="1.0.0.1"   # Cloudflare DNS secundário
readonly AUTO_DNS_IPV6_1="2606:4700:4700::1111"
readonly AUTO_DNS_IPV6_2="2606:4700:4700::1001"

# --- Detecção de Capacidades do Sistema ---
readonly SUPPORTS_IPV6=$(test -f /proc/net/if_inet6 && echo "yes" || echo "no")
readonly SUPPORTS_NFTABLES=$(command -v nft >/dev/null 2>&1 && echo "yes" || echo "no")
readonly SUPPORTS_SYSTEMD_RESOLVED=$(systemctl is-active systemd-resolved >/dev/null 2>&1 && echo "yes" || echo "no")
readonly CPU_CORES=$(nproc 2>/dev/null || echo "1")

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

# Função de barra de progresso melhorada
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
    
    local start_time=$(date +%s)
    while ps -p "$pid" > /dev/null; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [[ $elapsed -gt $timeout ]]; then
            kill $pid 2>/dev/null
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
    
    tput cnorm
    return $exit_code
}

# --- Verificações Iniciais Aprimoradas ---
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
    local kernel_version=$(uname -r | cut -d. -f1,2)
    local min_version="4.9"
    
    if [[ "$(printf '%s\n' "$min_version" "$kernel_version" | sort -V | head -n1)" != "$min_version" ]]; then
        warn "Kernel $kernel_version detectado. Recomendado 4.9+"
    fi
}

# --- Detecção de Sistema Operacional Expandida ---
detect_os() {
    [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
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
        centos|rhel|rocky|almalinux)
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

# --- Instalação de Dependências Moderna ---
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "lsof" "curl" "qrencode")
    
    # Adicionar pacotes específicos do OS
    if [[ "$OS" == "debian" ]]; then
        packages+=("iptables-persistent" "netfilter-persistent")
        if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
            packages+=("nftables")
        fi
    elif [[ "$OS" == "centos" ]]; then
        packages+=("firewalld")
    fi
    
    # Verificar pacotes instalados
    for pkg in "${packages[@]}"; do
        if [[ "$OS" == "debian" ]]; then
            if ! dpkg -l | grep -q "^ii.*$pkg"; then
                missing+=("$pkg")
            fi
        elif [[ "$OS" == "centos" ]]; then
            if ! rpm -qa | grep -q "^$pkg"; then
                missing+=("$pkg")
            fi
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
    
    # Verificar versão do OpenVPN
    local ovpn_version=$(openvpn --version 2>/dev/null | head -1 | awk '{print $2}')
    if [[ -z "$ovpn_version" ]]; then
        die "OpenVPN não foi instalado corretamente"
    fi
    
    local major_version="${ovpn_version%%.*}"
    if [[ "$major_version" -lt 2 ]]; then
        die "OpenVPN $ovpn_version muito antigo. Necessário 2.5+"
    elif [[ "$major_version" -eq 2 ]]; then
        local minor_version="${ovpn_version#*.}"
        minor_version="${minor_version%%.*}"
        if [[ "$minor_version" -lt 5 ]]; then
            warn "OpenVPN $ovpn_version detectado. Recomendado 2.5+ para recursos modernos"
        fi
    fi
    
    success "Todas as dependências verificadas!"
}

# --- Otimização de Performance do Sistema ---
optimize_system() {
    info "Aplicando otimizações de sistema..."
    
    # Otimizações de rede
    cat >> /etc/sysctl.d/99-openvpn.conf << EOF
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
    sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null 2>&1
    
    # Aumentar limites de arquivo
    if ! grep -q "openvpn" /etc/security/limits.conf 2>/dev/null; then
        echo "* soft nofile 65536" >> /etc/security/limits.conf
        echo "* hard nofile 65536" >> /etc/security/limits.conf
    fi
    
    success "Otimizações aplicadas!"
}

# --- Instalação Principal do OpenVPN ---
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║   OpenVPN Modern Installer v3.0        ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    
    # Mostrar capacidades do sistema
    echo -e "${CYAN}Capacidades do Sistema:${SCOLOR}"
    echo -e "  ${WHITE}• CPU Cores:${SCOLOR} ${GREEN}$CPU_CORES${SCOLOR}"
    echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$SUPPORTS_IPV6${SCOLOR}"
    echo -e "  ${WHITE}• NFTables:${SCOLOR} ${GREEN}$SUPPORTS_NFTABLES${SCOLOR}"
    echo -e "  ${WHITE}• Systemd-Resolved:${SCOLOR} ${GREEN}$SUPPORTS_SYSTEMD_RESOLVED${SCOLOR}"
    echo
    
    info "Configurações automáticas:"
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT${SCOLOR}"
    echo -e "  ${WHITE}• Protocolo:${SCOLOR} ${GREEN}$AUTO_PROTOCOL${SCOLOR}"
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Cloudflare ($AUTO_DNS1, $AUTO_DNS2)${SCOLOR}"
    echo -e "  ${WHITE}• Criptografia:${SCOLOR} ${GREEN}AES-256-GCM + ChaCha20-Poly1305${SCOLOR}"
    echo
    
    sleep 2
    
    # Aplicar otimizações
    optimize_system
    
    # Configurar Easy-RSA com curvas elípticas
    local EASY_RSA_DIR="/etc/openvpn/easy-rsa"
    
    info "Criando estrutura de diretórios..."
    mkdir -p "$EASY_RSA_DIR" /etc/openvpn/client /var/log/openvpn
    
    # Copiar Easy-RSA
    for dir in /usr/share/easy-rsa /usr/lib/easy-rsa /usr/lib64/easy-rsa; do
        if [[ -d "$dir" ]]; then
            cp -r "$dir"/* "$EASY_RSA_DIR/"
            break
        fi
    done
    
    [[ ! -f "$EASY_RSA_DIR/easyrsa" ]] && die "Easy-RSA não encontrado"
    chmod +x "$EASY_RSA_DIR/easyrsa"
    
    cd "$EASY_RSA_DIR" || die "Falha ao acessar $EASY_RSA_DIR"
    
    # Configurar vars para usar curvas elípticas (mais rápido e seguro)
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
    
    # Gerar DH (ou usar parâmetros pré-computados para acelerar)
    if [[ -f /usr/share/easy-rsa/dh2048.pem ]]; then
        cp /usr/share/easy-rsa/dh2048.pem pki/dh.pem
        info "Usando parâmetros DH pré-computados"
    else
        fun_bar "./easyrsa gen-dh" "Gerando parâmetros Diffie-Hellman"
    fi
    
    # Gerar chave tls-crypt (mais seguro que tls-auth)
    info "Gerando chave tls-crypt..."
    openvpn --genkey secret pki/tc.key || die "Falha ao gerar tls-crypt"
    
    # Copiar arquivos
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/tc.key /etc/openvpn/
    chmod 600 /etc/openvpn/*.{key,crt,pem}
    
    # Configurar servidor com recursos modernos
    configure_modern_server
    
    # Configurar firewall
    configure_modern_firewall
    
    # Iniciar serviço
    info "Iniciando OpenVPN..."
    systemctl enable --now openvpn@server || die "Falha ao iniciar OpenVPN"
    
    # Verificar se está rodando
    sleep 2
    if ! systemctl is-active --quiet openvpn@server; then
        journalctl -xeu openvpn@server.service --no-pager | tail -20
        die "OpenVPN falhou ao iniciar. Verifique os logs acima."
    fi
    
    success "OpenVPN instalado com sucesso!"
    
    # Criar primeiro cliente
    info "Criando cliente inicial..."
    create_modern_client "cliente1"
    
    # Mostrar resumo
    show_installation_summary
}

# --- Configuração Moderna do Servidor ---
configure_modern_server() {
    info "Configurando servidor com recursos modernos..."
    
    local IP=$(get_public_ip)
    local IPV6=""
    
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        IPV6=$(get_public_ipv6)
    fi
    
    # Configuração moderna do servidor
    cat > /etc/openvpn/server.conf << EOF
# OpenVPN Modern Configuration
port $AUTO_PORT
proto ${AUTO_PROTOCOL}
proto ${AUTO_PROTOCOL}6
dev tun

# Certificados
ca ca.crt
cert server.crt
key server.key
dh dh.pem

# Segurança moderna
tls-crypt tc.key
auth SHA512
cipher AES-256-GCM
ncp-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384

# Rede
topology subnet
server 10.8.0.0 255.255.255.0
EOF

    # Adicionar suporte IPv6 se disponível
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        cat >> /etc/openvpn/server.conf << EOF
server-ipv6 fd42:42:42::/64
push "route-ipv6 ::/0"
push "dhcp-option DNS6 $AUTO_DNS_IPV6_1"
push "dhcp-option DNS6 $AUTO_DNS_IPV6_2"
EOF
    fi

    # Configurações de push e performance
    cat >> /etc/openvpn/server.conf << EOF

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

# Compressão moderna
compress lz4-v2
push "compress lz4-v2"

# Multi-threading (se suportado)
EOF

    # Adicionar multi-threading se tiver múltiplos cores
    if [[ "$CPU_CORES" -gt 1 ]]; then
        echo "# Multi-threading para $CPU_CORES cores" >> /etc/openvpn/server.conf
        echo "threads $CPU_CORES" >> /etc/openvpn/server.conf
    fi

    # Configurações finais
    cat >> /etc/openvpn/server.conf << EOF

# Persistência e logging
keepalive 10 120
persist-key
persist-tun
user nobody
group $GROUPNAME
status /var/log/openvpn/status.log
log-append /var/log/openvpn/openvpn.log
verb 3
mute 20

# Controle de clientes
max-clients 100
ifconfig-pool-persist /etc/openvpn/ipp.txt
client-to-client
duplicate-cn

# CRL
crl-verify crl.pem
EOF

    # Gerar CRL
    cd /etc/openvpn/easy-rsa/
    ./easyrsa gen-crl
    cp pki/crl.pem /etc/openvpn/
    chmod 644 /etc/openvpn/crl.pem
    
    success "Servidor configurado com recursos modernos!"
}

# --- Configuração Moderna do Firewall ---
configure_modern_firewall() {
    info "Configurando firewall moderno..."
    
    local IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
    [[ -z "$IFACE" ]] && die "Interface de rede não detectada"
    
    info "Interface principal: $IFACE"
    
    # Usar nftables se disponível (mais moderno)
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]] && [[ "$OS" == "debian" ]]; then
        info "Configurando nftables..."
        
        # Criar configuração nftables
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
        
        # IPv4
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        
        # IPv6 se disponível
        if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
            ip6tables -t nat -A POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE
            ip6tables -A INPUT -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
            ip6tables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        fi
        
        # Salvar regras
        if [[ "$OS" == "debian" ]]; then
            iptables-save > /etc/iptables/rules.v4
            [[ "$SUPPORTS_IPV6" == "yes" ]] && ip6tables-save > /etc/iptables/rules.v6
            systemctl enable --now netfilter-persistent
        elif [[ "$OS" == "centos" ]]; then
            firewall-cmd --add-service=openvpn --permanent
            firewall-cmd --add-port=$AUTO_PORT/udp --permanent
            firewall-cmd --add-port=$AUTO_PORT/tcp --permanent
            firewall-cmd --add-masquerade --permanent
            firewall-cmd --reload
        fi
    fi
    
    success "Firewall configurado!"
}

# --- Criação de Cliente Moderno ---
create_modern_client() {
    local CLIENT_NAME="$1"
    
    if [[ -z "$CLIENT_NAME" ]]; then
        echo -ne "${WHITE}Nome do cliente: ${SCOLOR}"
        read -r CLIENT_NAME
        [[ -z "$CLIENT_NAME" ]] && warn "Nome inválido" && return
    fi
    
    # Sanitizar nome
    CLIENT_NAME=$(echo "$CLIENT_NAME" | sed 's/[^a-zA-Z0-9_-]//g')
    
    cd /etc/openvpn/easy-rsa/
    
    if [[ -f "pki/issued/${CLIENT_NAME}.crt" ]]; then
        warn "Cliente '$CLIENT_NAME' já existe"
        return
    fi
    
    fun_bar "echo 'yes' | ./easyrsa build-client-full '$CLIENT_NAME' nopass" "Gerando certificado"
    
    # Obter informações do servidor
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    local PORT=$(grep '^port' /etc/openvpn/server.conf | awk '{print $2}')
    local PROTO=$(grep '^proto' /etc/openvpn/server.conf | head -1 | awk '{print $2}')
    
    # Criar diretório de clientes
    local CLIENT_DIR=~/ovpn-clients
    mkdir -p "$CLIENT_DIR"
    
    # Gerar configuração moderna do cliente
    cat > "$CLIENT_DIR/${CLIENT_NAME}.ovpn" << EOF
# OpenVPN Modern Client Configuration
client
dev tun
proto ${PROTO}
remote ${IP} ${PORT}
EOF

    # Adicionar IPv6 se disponível
    if [[ -n "$IPV6" ]] && [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        echo "remote ${IPV6} ${PORT}" >> "$CLIENT_DIR/${CLIENT_NAME}.ovpn"
    fi

    cat >> "$CLIENT_DIR/${CLIENT_NAME}.ovpn" << EOF
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
cipher AES-256-GCM
compress lz4-v2
verb 3
mute 20
tun-mtu 1500
mssfix 1420
sndbuf 0
rcvbuf 0

# Segurança adicional
tls-version-min 1.2
tls-cipher TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384

# Certificados embutidos
<ca>
$(cat /etc/openvpn/ca.crt)
</ca>
<cert>
$(cat "/etc/openvpn/easy-rsa/pki/issued/${CLIENT_NAME}.crt")
</cert>
<key>
$(cat "/etc/openvpn/easy-rsa/pki/private/${CLIENT_NAME}.key")
</key>
<tls-crypt>
$(cat /etc/openvpn/tc.key)
</tls-crypt>
EOF

    # Gerar QR Code para mobile
    if command -v qrencode >/dev/null 2>&1; then
        info "Gerando QR Code..."
        cat "$CLIENT_DIR/${CLIENT_NAME}.ovpn" | qrencode -o "$CLIENT_DIR/${CLIENT_NAME}-qr.png"
        success "QR Code salvo em: $CLIENT_DIR/${CLIENT_NAME}-qr.png"
    fi
    
    # Criar arquivo de informações
    cat > "$CLIENT_DIR/${CLIENT_NAME}-info.txt" << EOF
═══════════════════════════════════════════════════
Cliente VPN: ${CLIENT_NAME}
Criado em: $(date)
═══════════════════════════════════════════════════

INFORMAÇÕES DE CONEXÃO:
• Servidor: ${IP}
• Porta: ${PORT}
• Protocolo: ${PROTO}
• Criptografia: AES-256-GCM

ARQUIVOS:
• Configuração: ${CLIENT_NAME}.ovpn
• QR Code: ${CLIENT_NAME}-qr.png (se disponível)

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
   - Escaneie o QR Code ou importe .ovpn

═══════════════════════════════════════════════════
EOF
    
    success "Cliente '$CLIENT_NAME' criado!"
    echo -e "${WHITE}Arquivos salvos em: ${GREEN}$CLIENT_DIR/${SCOLOR}"
}

# --- Funções Auxiliares Adicionais ---
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
        echo "$IPV6"
    fi
}

# --- Função de Backup ---
backup_openvpn() {
    local BACKUP_DIR="/root/openvpn-backup-$(date +%Y%m%d-%H%M%S)"
    
    info "Criando backup em $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    
    # Backup de configurações
    cp -r /etc/openvpn "$BACKUP_DIR/"
    
    # Backup de clientes
    [[ -d ~/ovpn-clients ]] && cp -r ~/ovpn-clients "$BACKUP_DIR/"
    
    # Criar arquivo tar.gz
    tar -czf "${BACKUP_DIR}.tar.gz" -C "$(dirname "$BACKUP_DIR")" "$(basename "$BACKUP_DIR")"
    rm -rf "$BACKUP_DIR"
    
    success "Backup salvo em: ${BACKUP_DIR}.tar.gz"
}

# --- Monitoramento Básico ---
show_status() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║        Status do OpenVPN               ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    
    # Status do serviço
    if systemctl is-active --quiet openvpn@server; then
        echo -e "${GREEN}● Serviço: ATIVO${SCOLOR}"
        
        # Uptime
        local uptime=$(systemctl show openvpn@server --property=ActiveEnterTimestamp | cut -d= -f2)
        echo -e "${WHITE}  Uptime: ${CYAN}$uptime${SCOLOR}"
        
        # Clientes conectados
        if [[ -f /var/log/openvpn/status.log ]]; then
            local clients=$(grep -c "^CLIENT_LIST" /var/log/openvpn/status.log 2>/dev/null || echo "0")
            echo -e "${WHITE}  Clientes conectados: ${GREEN}$clients${SCOLOR}"
            
            if [[ "$clients" -gt 0 ]]; then
                echo -e "\n${YELLOW}Clientes ativos:${SCOLOR}"
                grep "^CLIENT_LIST" /var/log/openvpn/status.log | awk -F',' '{print "  • " $2 " - IP: " $3}'
            fi
        fi
        
        # Uso de recursos
        echo -e "\n${CYAN}Uso de recursos:${SCOLOR}"
        local pid=$(pgrep -f "openvpn.*server.conf")
        if [[ -n "$pid" ]]; then
            ps -p "$pid" -o %cpu,%mem,rss --no-headers | while read cpu mem rss; do
                echo -e "  CPU: ${WHITE}${cpu}%${SCOLOR} | RAM: ${WHITE}${mem}%${SCOLOR} (${rss} KB)"
            done
        fi
        
        # Tráfego de rede
        if [[ -f /proc/net/dev ]]; then
            echo -e "\n${CYAN}Tráfego (tun0):${SCOLOR}"
            local stats=$(grep "tun0" /proc/net/dev | awk '{print "  RX: " $2/1048576 " MB | TX: " $10/1048576 " MB"}')
            echo -e "${WHITE}$stats${SCOLOR}"
        fi
    else
        echo -e "${RED}● Serviço: INATIVO${SCOLOR}"
    fi
    
    echo
    echo -e "${CYAN}Pressione ENTER para voltar...${SCOLOR}"
    read -r
}

# --- Resumo da Instalação ---
show_installation_summary() {
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║   Instalação Concluída com Sucesso!    ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Resumo da Configuração:${SCOLOR}"
    echo -e "  ${WHITE}• IP Público:${SCOLOR} ${GREEN}$(get_public_ip)${SCOLOR}"
    
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        local ipv6=$(get_public_ipv6)
        [[ -n "$ipv6" ]] && echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$ipv6${SCOLOR}"
    fi
    
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT ($AUTO_PROTOCOL)${SCOLOR}"
    echo -e "  ${WHITE}• Subnet VPN:${SCOLOR} ${GREEN}10.8.0.0/24${SCOLOR}"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  ${WHITE}• Subnet IPv6:${SCOLOR} ${GREEN}fd42:42:42::/64${SCOLOR}"
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Cloudflare${SCOLOR}"
    echo -e "  ${WHITE}• Criptografia:${SCOLOR} ${GREEN}AES-256-GCM / ChaCha20${SCOLOR}"
    echo -e "  ${WHITE}• Compressão:${SCOLOR} ${GREEN}LZ4${SCOLOR}"
    echo
    echo -e "${CYAN}Recursos Modernos Ativados:${SCOLOR}"
    echo -e "  ✓ TLS-Crypt (proteção DDoS)"
    echo -e "  ✓ Curvas Elípticas (ECDSA)"
    echo -e "  ✓ Perfect Forward Secrecy"
    echo -e "  ✓ Compressão LZ4"
    [[ "$CPU_CORES" -gt 1 ]] && echo -e "  ✓ Multi-threading ($CPU_CORES cores)"
    [[ "$SUPPORTS_IPV6" == "yes" ]] && echo -e "  ✓ Suporte IPv6"
    [[ "$SUPPORTS_NFTABLES" == "yes" ]] && echo -e "  ✓ NFTables"
    echo
    echo -e "${YELLOW}Arquivo do cliente:${SCOLOR}"
    echo -e "  ${GREEN}~/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
}

# --- Função de Revogação Melhorada ---
revoke_client() {
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado"
    
    # Listar clientes
    local clients=()
    while IFS= read -r file; do
        local client=$(basename "$file" .crt)
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
        # Criar backup antes de revogar
        backup_openvpn
        
        fun_bar "echo 'yes' | ./easyrsa revoke '$CLIENT'" "Revogando certificado"
        fun_bar "./easyrsa gen-crl" "Atualizando CRL"
        
        cp pki/crl.pem /etc/openvpn/
        systemctl restart openvpn@server
        
        # Remover arquivos do cliente
        rm -f ~/ovpn-clients/"${CLIENT}"*
        
        success "Cliente '$CLIENT' revogado!"
    else
        warn "Operação cancelada"
    fi
}

# --- Desinstalação Completa ---
uninstall_openvpn() {
    echo -ne "${RED}ATENÇÃO: Isso removerá TUDO! Continuar? [s/N]: ${SCOLOR}"
    read -r confirm
    
    if [[ "$confirm" =~ ^[sS]$ ]]; then
        # Criar backup final
        backup_openvpn
        
        info "Parando serviços..."
        systemctl stop openvpn@server 2>/dev/null
        systemctl disable openvpn@server 2>/dev/null
        
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
            # Limpar iptables
            iptables -t nat -F
            iptables -F
            if [[ "$OS" == "debian" ]]; then
                > /etc/iptables/rules.v4
                > /etc/iptables/rules.v6
            fi
        fi
        
        info "Removendo arquivos..."
        rm -rf /etc/openvpn
        rm -rf ~/ovpn-clients
        rm -f /etc/sysctl.d/99-openvpn.conf
        
        sysctl -p >/dev/null 2>&1
        
        success "OpenVPN removido completamente!"
        info "Backup salvo em /root/openvpn-backup-*.tar.gz"
    else
        warn "Desinstalação cancelada"
    fi
}

# --- Menu Principal Aprimorado ---
main_menu() {
    while true; do
        clear
        echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
        echo -e "${BLUE}║   OpenVPN Modern Manager v3.0          ║${SCOLOR}"
        echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
        echo -e "${CYAN}Sistema: $OS_NAME${SCOLOR}"
        echo
        
        if systemctl is-active --quiet openvpn@server 2>/dev/null; then
            local ip=$(get_public_ip)
            local port=$(grep '^port' /etc/openvpn/server.conf 2>/dev/null | awk '{print $2}')
            local proto=$(grep '^proto' /etc/openvpn/server.conf 2>/dev/null | head -1 | awk '{print $2}')
            local clients_count=$(find /etc/openvpn/easy-rsa/pki/issued -name "*.crt" 2>/dev/null | grep -cv server)
            
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
            echo -e "${RED}● OpenVPN: NÃO INSTALADO${SCOLOR}"
            echo
            echo -e "${YELLOW}1)${SCOLOR} Instalar OpenVPN (Automático)"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        fi
        
        echo
        echo -ne "${WHITE}Opção: ${SCOLOR}"
        read -r choice
        
        if systemctl is-active --quiet openvpn@server 2>/dev/null; then
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

# --- Ponto de Entrada Principal ---
main() {
    # Verificações iniciais
    check_root
    check_bash
    check_virtualization
    check_kernel_version
    
    # Detectar sistema
    detect_os
    
    # Verificar dependências
    check_dependencies
    
    # Iniciar menu
    main_menu
}

# Tratamento de sinais
trap 'echo -e "\n${RED}Script interrompido!${SCOLOR}"; tput cnorm; exit 130' INT TERM

# Executar
main "$@"
