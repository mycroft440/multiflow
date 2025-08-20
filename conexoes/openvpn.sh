#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager - Versão Simplificada para Debian/Ubuntu v4.1
# Instalação automática com configurações padrão
# Porta: 1194 | Protocolo: TCP | DNS: Google
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

# --- Configurações Padrão (TCP como solicitado) ---
readonly DEFAULT_PORT="1194"
readonly DEFAULT_PROTOCOL="tcp"
readonly DEFAULT_DNS1="8.8.8.8"
readonly DEFAULT_DNS2="8.8.4.4"
readonly DEFAULT_DNS_IPV6_1="2001:4860:4860::8888"
readonly DEFAULT_DNS_IPV6_2="2001:4860:4860::8844"

# --- Detecção de Capacidades do Sistema ---
readonly SUPPORTS_IPV6=$(test -f /proc/net/if_inet6 && echo "yes" || echo "no")
readonly SUPPORTS_NFTABLES=$(command -v nft >/dev/null 2>&1 && echo "yes" || echo "no")
readonly SUPPORTS_SYSTEMD_RESOLVED=$(systemctl is-active systemd-resolved >/dev/null 2>&1 && echo "yes" || echo "no")
readonly CPU_CORES=$(nproc 2>/dev/null || echo "1")

# Variáveis globais de layout/paths do OpenVPN
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

# Função de barra de progresso melhorada (timeout aumentado para 600s)
fun_bar() {
    local cmd="$1"
    local desc="${2:-Processando}"
    local spinner="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    local i=0
    local timeout=600  # Aumentado para 10 min
    
    eval "$cmd" &
    local pid=$!
    
    tput civis 2>/dev/null
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
    
    tput cnorm 2>/dev/null
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

# --- Detecção de Sistema Operacional (Simplificado para Debian/Ubuntu) ---
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

# --- Detectar layout do OpenVPN (systemd e caminhos) ---
detect_openvpn_layout() {
    OVPN_DIR="/etc/openvpn"
    mkdir -p "$OVPN_LOG_DIR"
    
    # Detecta qual unidade systemd existe
    if systemctl list-unit-files 2>/dev/null | grep -q '^openvpn-server@\.service'; then
        SERVER_UNIT="openvpn-server@server"
        OVPN_CONF_DIR="$OVPN_DIR/server"
        SERVER_CONF="$OVPN_CONF_DIR/server.conf"
    elif systemctl list-unit-files 2>/dev/null | grep -q '^openvpn@\.service'; then
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
    debug "Layout OpenVPN: unidade=${SERVER_UNIT} | conf=${SERVER_CONF}"
}

# --- Instalação de Dependências (Simplificado para apt) ---
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "curl" "iptables-persistent" "netfilter-persistent")
    
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
        packages+=("nftables")
    fi
    
    # Verificar pacotes instalados
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
    if [[ -z "$ovpn_version" ]]; then
        die "OpenVPN não foi instalado corretamente"
    fi
    
    success "Todas as dependências verificadas! (OpenVPN $ovpn_version)"
}

# --- Otimização de Performance do Sistema (com carregamento de módulos) ---
optimize_system() {
    info "Aplicando otimizações de sistema..."
    
    # Carregar módulos necessários
    modprobe tcp_bbr 2>/dev/null || warn "Módulo tcp_bbr não carregado (BBR indisponível)"
    modprobe sch_fq 2>/dev/null || warn "Módulo fq não carregado"
    
    # Otimizações de rede
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
    sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null 2>&1
    
    # Aumentar limites de arquivo
    if ! grep -q "openvpn" /etc/security/limits.conf 2>/dev/null; then
        echo "* soft nofile 65536" >> /etc/security/limits.conf
        echo "* hard nofile 65536" >> /etc/security/limits.conf
    fi
    
    success "Otimizações aplicadas!"
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
        IPV6=$(ip -6 addr show scope global | grep -oP '(?<=inet6\s)[\da-f:]+' | head -1)
        [[ -z "$IPV6" ]] && warn "IPv6 detectado mas endereço público não encontrado."
        echo "$IPV6"
    fi
}

# --- Configuração do Easy-RSA ---
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
    
    # Gerar DH (tentar pré-computado ou gerar)
    if [[ -f "/usr/share/easy-rsa/dh2048.pem" ]]; then
        cp /usr/share/easy-rsa/dh2048.pem pki/dh.pem
        info "Usando parâmetros DH pré-computados"
    else
        fun_bar "./easyrsa gen-dh" "Gerando parâmetros Diffie-Hellman"
    fi
    
    # Gerar chave tls-crypt
    info "Gerando chave tls-crypt..."
    openvpn --genkey secret pki/tc.key || die "Falha ao gerar tls-crypt"
    
    # Copiar arquivos
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/tc.key "$OVPN_CONF_DIR/"
    chmod 600 "$OVPN_CONF_DIR/"/*.{key,crt,pem} 2>/dev/null
    
    # Gerar CRL
    fun_bar "./easyrsa gen-crl" "Gerando lista de revogação"
    cp pki/crl.pem "$OVPN_CONF_DIR/"
    chmod 644 "$OVPN_CONF_DIR/crl.pem"
    
    success "Certificados configurados!"
}

# --- Configuração do Servidor OpenVPN ---
configure_server() {
    info "Configurando servidor OpenVPN..."
    
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    
    # Configuração do servidor com TCP
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

    # Adicionar suporte IPv6 se disponível
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

    success "Servidor configurado com protocolo TCP!"
}

# --- Configuração do Firewall (Simplificado para Debian/Ubuntu, priorizando nftables) ---
configure_firewall() {
    info "Configurando firewall..."
    
    local IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
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

        if [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]]; then
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
        
        # Abrir porta TCP
        iptables -A INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT
        
        # NAT e forward
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        
        # IPv6 se disponível
        if [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]]; then
            ip6tables -A INPUT -p tcp --dport "$DEFAULT_PORT" -j ACCEPT
            ip6tables -t nat -A POSTROUTING -s fd42:42:42::/64 -o "$IFACE" -j MASQUERADE
            ip6tables -A INPUT -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i tun+ -j ACCEPT
            ip6tables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
            ip6tables -A FORWARD -i tun+ -o "$IFACE" -j ACCEPT
        fi
        
        # Salvar regras
        mkdir -p /etc/iptables
        iptables-save > /etc/iptables/rules.v4
        [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]] && ip6tables-save > /etc/iptables/rules.v6
        systemctl enable --now netfilter-persistent
    fi
    
    success "Firewall configurado!"
}

# --- Criação de Cliente ---
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

    # Criar arquivo de informações
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

# --- Iniciar Serviço ---
start_service() {
    info "Iniciando serviço OpenVPN..."
    
    systemctl daemon-reload
    systemctl enable --now "$SERVER_UNIT" || die "Falha ao iniciar OpenVPN"
    
    # Verificar se está rodando
    sleep 3
    if ! systemctl is-active --quiet "$SERVER_UNIT"; then
        journalctl -xeu "$SERVER_UNIT" --no-pager | tail -30
        die "OpenVPN falhou ao iniciar. Verifique os logs acima."
    fi
    
    success "Serviço OpenVPN iniciado com sucesso!"
}

# --- Menu de Confirmação ---
show_confirmation_menu() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║              INSTALADOR OPENVPN - CONFIRMAÇÃO             ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${YELLOW}O OpenVPN será instalado com as configurações comuns:${SCOLOR}"
    echo
    echo -e "  ${CYAN}• Porta:${SCOLOR}     ${WHITE}1194${SCOLOR}"
    echo -e "  ${CYAN}• Protocolo:${SCOLOR} ${WHITE}TCP${SCOLOR}"
    echo -e "  ${CYAN}• DNS:${SCOLOR}       ${WHITE}Google (8.8.8.8, 8.8.4.4)${SCOLOR}"
    echo
    echo -e "${YELLOW}Caso queira trocar, use o menu interativo posteriormente.${SCOLOR}"
    echo -e "${YELLOW}Deseja continuar?${SCOLOR}"
    echo
    echo -e "  ${GREEN}1.${SCOLOR} SIM, bora"
    echo -e "  ${RED}0.${SCOLOR} Voltar ao menu OpenVPN"
    echo
    echo -ne "${WHITE}Escolha: ${SCOLOR}"
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

# --- Resumo da Instalação ---
show_installation_summary() {
    local IP=$(get_public_ip)
    local IPV6=$(get_public_ipv6)
    
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║   Instalação Concluída com Sucesso!    ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Resumo da Configuração:${SCOLOR}"
    echo -e "  ${WHITE}• IP Público:${SCOLOR} ${GREEN}$IP${SCOLOR}"
    
    if [[ "$SUPPORTS_IPV6" == "yes" && -n "$IPV6" ]]; then
        echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$IPV6${SCOLOR}"
    fi
    
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$DEFAULT_PORT${SCOLOR}"
    echo -e "  ${WHITE}• Protocolo:${SCOLOR} ${GREEN}$DEFAULT_PROTOCOL${SCOLOR}"
    echo -e "  ${WHITE}• Subnet VPN:${SCOLOR} ${GREEN}10.8.0.0/24${SCOLOR}"
    
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        echo -e "  ${WHITE}• Subnet IPv6:${SCOLOR} ${GREEN}fd42:42:42::/64${SCOLOR}"
    fi
    
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Google${SCOLOR}"
    echo -e "  ${WHITE}• Criptografia:${SCOLOR} ${GREEN}AES-256-GCM${SCOLOR}"
    echo
    echo -e "${CYAN}Recursos Ativados:${SCOLOR}"
    echo -e "  ✓ TLS-Crypt (proteção DDoS)"
    echo -e "  ✓ Curvas Elípticas (ECDSA)"
    echo -e "  ✓ Perfect Forward Secrecy"
    echo -e "  ✓ Otimizações de kernel"
    
    if [[ "$SUPPORTS_IPV6" == "yes" ]]; then
        echo -e "  ✓ Suporte IPv6"
    fi
    
    if [[ "$SUPPORTS_NFTABLES" == "yes" ]]; then
        echo -e "  ✓ NFTables"
    fi
    
    echo
    echo -e "${YELLOW}Arquivo do cliente inicial:${SCOLOR}"
    echo -e "  ${GREEN}~/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
    echo -e "${CYAN}Use o menu interativo para gerenciar clientes e configurações.${SCOLOR}"
    echo
}

# --- Verificar se já está instalado ---
check_if_installed() {
    if [[ -f "$SERVER_CONF" ]] || [[ -f "/etc/openvpn/server.conf" ]]; then
        echo -e "${YELLOW}OpenVPN já está instalado!${SCOLOR}"
        echo -e "${WHITE}Use o menu interativo para gerenciar.${SCOLOR}"
        exit 0
    fi
}

# --- Instalação Principal ---
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║        INSTALANDO OPENVPN              ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    
    # Mostrar capacidades do sistema
    echo -e "${CYAN}Capacidades do Sistema:${SCOLOR}"
    echo -e "  ${WHITE}• CPU Cores:${SCOLOR} ${GREEN}$CPU_CORES${SCOLOR}"
    echo -e "  ${WHITE}• IPv6:${SCOLOR} ${GREEN}$SUPPORTS_IPV6${SCOLOR}"
    echo -e "  ${WHITE}• NFTables:${SCOLOR} ${GREEN}$SUPPORTS_NFTABLES${SCOLOR}"
    echo -e "  ${WHITE}• Systemd-Resolved:${SCOLOR} ${GREEN}$SUPPORTS_SYSTEMD_RESOLVED${SCOLOR}"
    echo
    
    sleep 2
    
    # Executar etapas de instalação
    optimize_system
    check_dependencies
    setup_easy_rsa
    configure_server
    configure_firewall
    create_client "cliente1"
    start_service
    
    # Mostrar resumo
    show_installation_summary
}

# --- Função Principal ---
main() {
    # Verificações iniciais
    check_root
    check_bash
    check_virtualization
    check_kernel_version
    
    # Detectar sistema
    detect_os
    
    # Detectar layout do OpenVPN
    detect_openvpn_layout
    
    # Verificar se já está instalado
    check_if_installed
    
    # Mostrar menu de confirmação
    show_confirmation_menu
    
    # Executar instalação
    install_openvpn
}

# Tratamento de sinais
trap 'echo -e "\n${RED}Script interrompido!${SCOLOR}"; tput cnorm; exit 130' INT TERM

# Executar (ative debug se quiser: DEBUG=1)
main "$@"
