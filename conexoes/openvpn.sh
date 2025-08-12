#!/bin/bash
# =================================================================
# OpenVPN Installer - Versão Simplificada v4.0
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

# --- Variáveis Globais ---
OS=""
OS_VERSION=""
GROUPNAME=""
IP=""
INTERFACE=""

# --- Funções de Utilidade ---
die() {
    echo -e "${RED}[ERRO] $1${SCOLOR}" >&2
    exit "${2:-1}"
}

success() {
    echo -e "${GREEN}[✓] $1${SCOLOR}"
}

info() {
    echo -e "${CYAN}[INFO] $1${SCOLOR}"
}

warn() {
    echo -e "${YELLOW}[!] $1${SCOLOR}"
}

# --- Verificações Iniciais ---
check_root() {
    [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."
}

check_tun() {
    if ! [[ -e /dev/net/tun ]]; then
        die "TUN/TAP não disponível. Execute: modprobe tun"
    fi
}

# --- Detecção de Sistema ---
detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        die "Sistema operacional não suportado"
    fi
    
    case "$OS" in
        ubuntu|debian)
            GROUPNAME="nogroup"
            ;;
        centos|rhel|rocky|almalinux|fedora)
            GROUPNAME="nobody"
            ;;
        *)
            die "Sistema operacional '$OS' não suportado"
            ;;
    esac
    
    info "Sistema detectado: $PRETTY_NAME"
}

# --- Obter IP Público ---
get_public_ip() {
    IP=$(curl -4 -s https://api.ipify.org 2>/dev/null || \
         curl -4 -s https://ifconfig.me 2>/dev/null || \
         curl -4 -s https://ipinfo.io/ip 2>/dev/null || \
         hostname -I | awk '{print $1}')
    
    [[ -z "$IP" ]] && die "Não foi possível detectar o IP público"
    echo "$IP"
}

# --- Obter Interface de Rede ---
get_network_interface() {
    INTERFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
    [[ -z "$INTERFACE" ]] && die "Interface de rede não detectada"
    echo "$INTERFACE"
}

# --- Instalação de Dependências ---
install_dependencies() {
    info "Instalando dependências..."
    
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq >/dev/null 2>&1
        apt-get install -y -qq openvpn easy-rsa iptables curl >/dev/null 2>&1 || die "Falha ao instalar pacotes"
    else
        yum install -y epel-release >/dev/null 2>&1
        yum install -y openvpn easy-rsa iptables curl >/dev/null 2>&1 || die "Falha ao instalar pacotes"
    fi
    
    success "Dependências instaladas"
}

# --- Configurar Easy-RSA ---
setup_easyrsa() {
    info "Configurando certificados..."
    
    # Criar diretório
    mkdir -p /etc/openvpn/easy-rsa
    
    # Copiar Easy-RSA
    if [[ -d /usr/share/easy-rsa ]]; then
        cp -r /usr/share/easy-rsa/* /etc/openvpn/easy-rsa/
    else
        die "Easy-RSA não encontrado"
    fi
    
    cd /etc/openvpn/easy-rsa/ || die "Falha ao acessar diretório"
    
    # Configurar vars
    cat > vars << EOF
set_var EASYRSA_ALGO ec
set_var EASYRSA_CURVE secp384r1
set_var EASYRSA_KEY_SIZE 2048
set_var EASYRSA_CA_EXPIRE 3650
set_var EASYRSA_CERT_EXPIRE 3650
set_var EASYRSA_CRL_DAYS 180
EOF
    
    # Inicializar PKI
    ./easyrsa init-pki >/dev/null 2>&1
    
    # Criar CA
    echo "OpenVPN-CA" | ./easyrsa build-ca nopass >/dev/null 2>&1
    
    # Criar certificado do servidor
    echo "yes" | ./easyrsa build-server-full server nopass >/dev/null 2>&1
    
    # Gerar DH
    ./easyrsa gen-dh >/dev/null 2>&1
    
    # Gerar tls-auth
    openvpn --genkey secret pki/ta.key
    
    # Copiar arquivos
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/ta.key /etc/openvpn/
    
    # Gerar CRL
    ./easyrsa gen-crl >/dev/null 2>&1
    cp pki/crl.pem /etc/openvpn/
    
    success "Certificados configurados"
}

# --- Configurar Servidor ---
configure_server() {
    info "Configurando servidor OpenVPN..."
    
    cat > /etc/openvpn/server.conf << EOF
# OpenVPN Server Configuration
port $DEFAULT_PORT
proto $DEFAULT_PROTOCOL
dev tun

# Certificados
ca ca.crt
cert server.crt
key server.key
dh dh.pem
tls-auth ta.key 0
crl-verify crl.pem

# Rede
server 10.8.0.0 255.255.255.0
topology subnet

# Roteamento
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS $DEFAULT_DNS1"
push "dhcp-option DNS $DEFAULT_DNS2"

# Segurança
cipher AES-256-GCM
auth SHA256
tls-version-min 1.2
tls-cipher TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-128-GCM-SHA256

# Performance
sndbuf 0
rcvbuf 0
push "sndbuf 0"
push "rcvbuf 0"
keepalive 10 120
comp-lzo no
push "comp-lzo no"

# Persistência
persist-key
persist-tun
user nobody
group $GROUPNAME

# Logs
status /var/log/openvpn-status.log
log-append /var/log/openvpn.log
verb 3
mute 20

# Clientes
max-clients 100
client-to-client
duplicate-cn
EOF
    
    # Habilitar forwarding
    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-openvpn.conf
    sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null 2>&1
    
    success "Servidor configurado"
}

# --- Configurar Firewall ---
configure_firewall() {
    info "Configurando firewall..."
    
    # Limpar regras antigas do OpenVPN se existirem
    iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o "$INTERFACE" -j MASQUERADE 2>/dev/null
    iptables -D INPUT -p "$DEFAULT_PROTOCOL" --dport "$DEFAULT_PORT" -j ACCEPT 2>/dev/null
    iptables -D FORWARD -i tun0 -j ACCEPT 2>/dev/null
    iptables -D FORWARD -o tun0 -j ACCEPT 2>/dev/null
    
    # Adicionar novas regras
    iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$INTERFACE" -j MASQUERADE
    iptables -A INPUT -p "$DEFAULT_PROTOCOL" --dport "$DEFAULT_PORT" -j ACCEPT
    iptables -A FORWARD -i tun0 -j ACCEPT
    iptables -A FORWARD -o tun0 -j ACCEPT
    iptables -A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
    
    # Salvar regras
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
        # Instalar iptables-persistent silenciosamente
        echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
        echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
        apt-get install -y -qq iptables-persistent >/dev/null 2>&1
        
        mkdir -p /etc/iptables
        iptables-save > /etc/iptables/rules.v4
    else
        if command -v firewall-cmd >/dev/null 2>&1; then
            firewall-cmd --add-port="$DEFAULT_PORT/$DEFAULT_PROTOCOL" --permanent >/dev/null 2>&1
            firewall-cmd --add-masquerade --permanent >/dev/null 2>&1
            firewall-cmd --reload >/dev/null 2>&1
        else
            service iptables save >/dev/null 2>&1
        fi
    fi
    
    success "Firewall configurado"
}

# --- Criar Cliente ---
create_client() {
    local CLIENT_NAME="${1:-cliente1}"
    
    info "Criando cliente: $CLIENT_NAME"
    
    cd /etc/openvpn/easy-rsa/ || die "Diretório não encontrado"
    
    # Gerar certificado do cliente
    echo "yes" | ./easyrsa build-client-full "$CLIENT_NAME" nopass >/dev/null 2>&1
    
    # Criar diretório para clientes
    mkdir -p /root/ovpn-clients
    
    # Gerar arquivo .ovpn
    cat > "/root/ovpn-clients/${CLIENT_NAME}.ovpn" << EOF
client
dev tun
proto $DEFAULT_PROTOCOL
remote $IP $DEFAULT_PORT
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
auth SHA256
verb 3
mute 20
comp-lzo no
<ca>
$(cat /etc/openvpn/ca.crt)
</ca>
<cert>
$(cat /etc/openvpn/easy-rsa/pki/issued/${CLIENT_NAME}.crt)
</cert>
<key>
$(cat /etc/openvpn/easy-rsa/pki/private/${CLIENT_NAME}.key)
</key>
<tls-auth>
$(cat /etc/openvpn/ta.key)
</tls-auth>
key-direction 1
EOF
    
    success "Cliente criado: /root/ovpn-clients/${CLIENT_NAME}.ovpn"
}

# --- Iniciar Serviço ---
start_service() {
    info "Iniciando serviço OpenVPN..."
    
    # Detectar qual serviço usar
    if systemctl list-unit-files | grep -q "openvpn-server@.service"; then
        # Layout moderno (Debian 11+, Ubuntu 20.04+)
        mkdir -p /etc/openvpn/server
        mv /etc/openvpn/server.conf /etc/openvpn/server/server.conf 2>/dev/null
        systemctl enable openvpn-server@server >/dev/null 2>&1
        systemctl restart openvpn-server@server
        
        # Verificar se iniciou
        sleep 2
        if systemctl is-active --quiet openvpn-server@server; then
            success "Serviço iniciado com sucesso"
        else
            warn "Tentando layout legado..."
            mv /etc/openvpn/server/server.conf /etc/openvpn/server.conf 2>/dev/null
            systemctl enable openvpn@server >/dev/null 2>&1
            systemctl restart openvpn@server
        fi
    else
        # Layout legado
        systemctl enable openvpn@server >/dev/null 2>&1
        systemctl restart openvpn@server
    fi
    
    # Verificação final
    sleep 2
    if pgrep -x openvpn >/dev/null; then
        success "OpenVPN está rodando"
    else
        die "Falha ao iniciar OpenVPN. Verifique: journalctl -xe"
    fi
}

# --- Menu de Confirmação ---
show_confirmation() {
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

# --- Função Principal de Instalação ---
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║                  INSTALANDO OPENVPN                       ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${SCOLOR}"
    echo
    
    # Obter informações do sistema
    IP=$(get_public_ip)
    INTERFACE=$(get_network_interface)
    
    echo -e "${CYAN}IP Público:${SCOLOR} $IP"
    echo -e "${CYAN}Interface:${SCOLOR} $INTERFACE"
    echo
    
    # Executar instalação
    install_dependencies
    setup_easyrsa
    configure_server
    configure_firewall
    create_client "cliente1"
    start_service
    
    echo
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║            INSTALAÇÃO CONCLUÍDA COM SUCESSO!              ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Informações de Conexão:${SCOLOR}"
    echo -e "  ${CYAN}• Servidor:${SCOLOR}  $IP"
    echo -e "  ${CYAN}• Porta:${SCOLOR}     $DEFAULT_PORT"
    echo -e "  ${CYAN}• Protocolo:${SCOLOR} $DEFAULT_PROTOCOL"
    echo -e "  ${CYAN}• DNS:${SCOLOR}       Google"
    echo
    echo -e "${WHITE}Arquivo de configuração do cliente:${SCOLOR}"
    echo -e "  ${GREEN}/root/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
    echo -e "${YELLOW}Use o menu interativo para gerenciar clientes e configurações.${SCOLOR}"
    echo
}

# --- Verificar se já está instalado ---
check_installed() {
    if [[ -f /etc/openvpn/server.conf ]] || [[ -f /etc/openvpn/server/server.conf ]]; then
        echo -e "${YELLOW}OpenVPN já está instalado!${SCOLOR}"
        echo -e "${WHITE}Use o menu interativo para gerenciar.${SCOLOR}"
        exit 0
    fi
}

# --- Main ---
main() {
    check_root
    check_tun
    detect_os
    check_installed
    show_confirmation
    install_openvpn
}

# Executar
main "$@"
