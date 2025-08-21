#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager
# mycroft rasqui
# =================================================================
# --- Variáveis de Cor ---
readonly RED='\e[1;31m'
readonly GREEN='\e[1;32m'
readonly YELLOW='\e[1;33m'
readonly BLUE='\e[1;34m'
readonly CYAN='\e[1;36m'
readonly WHITE='\e[1;37m'
readonly SCOLOR='\e[0m'
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
fun_bar() {
    local cmd="$1"
    local spinner="/-\\|"
    local i=0
    local timeout=600
    eval "$cmd" &
    local pid=$!
    tput civis
    echo -ne "${YELLOW}Aguarde... [${SCOLOR}"
    local start_time=$(date +%s)
    while ps -p "$pid" > /dev/null; do
        current_time=$(date +%s)
        if [[ $((current_time - start_time)) -gt $timeout ]]; then
            kill "$pid" 2>/dev/null
            die "Timeout na execução: $cmd demorou mais de 5min. Verifique rede ou mirrors."
        fi
        i=$(((i + 1) % 4))
        echo -ne "${CYAN}${spinner:$i:1}${SCOLOR}"
        sleep 0.2
        echo -ne "\b"
    done
    echo -e "${YELLOW}]${SCOLOR} - ${GREEN}Concluído!${SCOLOR}"
    tput cnorm
    wait "$pid" || die "Comando falhou: $cmd"
}
# --- Verificações Iniciais ---
check_root() {
    [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."
}
check_bash() {
    readlink /proc/$$/exe | grep -q "bash" || die "Execute este script com bash, não com sh."
}
cleanup_previous_installations() {
    echo -e "${CYAN}Verificando e removendo instalações anteriores do OpenVPN...${SCOLOR}"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop openvpn@server 2>/dev/null
        systemctl disable openvpn@server 2>/dev/null
    else
        service openvpn@server stop 2>/dev/null
    fi
    rm -rf /etc/openvpn /var/log/openvpn ~/ovpn-clients
    echo -e "${GREEN}Limpeza de instalações anteriores concluída.${SCOLOR}"
}
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "lsof")
    local checks=("command -v openvpn" "[ -d /usr/share/easy-rsa ] || [ -d /usr/lib/easy-rsa ] || [ -d /usr/lib64/easy-rsa ]" "command -v iptables" "command -v lsof")
    if [[ "$OS" == "debian" ]]; then
        packages+=("iptables-persistent" "netfilter-persistent")
        checks+=("command -v iptables-save")
    fi
    # Detecta dependências ausentes
    for i in "${!packages[@]}"; do
        if ! eval "${checks[$i]}"; then
            missing+=("${packages[$i]}")
        fi
    done
    # Instala automaticamente as dependências ausentes
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "${YELLOW}Dependências em falta: ${missing[*]}${SCOLOR}"
        echo -e "${CYAN}Instalando dependências faltantes...${SCOLOR}"
        if [[ "$OS" == "debian" ]]; then
            fun_bar "apt update -qq && apt install -y -qq ${missing[*]}"
        elif [[ "$OS" == "centos" ]]; then
            # Habilita repositório EPEL se necessário
            if ! yum list installed epel-release >/dev/null 2>&1; then
                fun_bar "yum install -y epel-release"
            fi
            fun_bar "yum install -y ${missing[*]}"
        fi
        # Verifica novamente se todas as dependências foram instaladas
        local still_missing=()
        for i in "${!packages[@]}"; do
            if ! eval "${checks[$i]}"; then
                still_missing+=("${packages[$i]}")
            fi
        done
        if [[ ${#still_missing[@]} -gt 0 ]]; then
            die "Falha ao instalar: ${still_missing[*]}."
        else
            success "Dependências instaladas com sucesso!"
        fi
    else
        success "Todas as dependências estão presentes."
    fi
    # Alerta se a versão do OpenVPN for antiga
    local ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    if [[ "$ovpn_version" < "2.5" ]]; then
        warn "Versão do OpenVPN ($ovpn_version) é antiga. Recomenda-se atualizar para 2.5+ para compatibilidade."
    fi
}
detect_os() {
    [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
    source /etc/os-release
    OS_ID="$ID"
    case "$OS_ID" in
        ubuntu|debian) OS="debian"; GROUPNAME="nogroup" ;;
        centos|fedora|rhel) OS="centos"; GROUPNAME="nobody" ;;
        *) die "Sistema operacional '$OS_ID' não suportado." ;;
    esac
}
install_openvpn() {
    clear
    echo -e "${BLUE}--- Instalador OpenVPN ---${SCOLOR}"
    local EASY_RSA_DIR="/etc/openvpn/easy-rsa"
    mkdir -p "$EASY_RSA_DIR" || die "Falha ao criar diretório $EASY_RSA_DIR."
    cp -r /usr/share/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || cp -r /usr/lib/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || cp -r /usr/lib64/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || die "EasyRSA não encontrado."
    chmod +x "$EASY_RSA_DIR/easyrsa" || die "Falha ao ajustar permissões do EasyRSA."
    cd "$EASY_RSA_DIR" || die "Não foi possível acessar $EASY_RSA_DIR."
    echo -e "${CYAN}Configurando EasyRSA...${SCOLOR}"
    ./easyrsa init-pki || die "Falha ao inicializar PKI."
    echo "Easy-RSA CA" | ./easyrsa build-ca nopass || die "Falha ao criar CA."
    echo "yes" | ./easyrsa build-server-full server nopass || die "Falha ao criar certificado do servidor."
    ./easyrsa gen-dh || die "Falha ao gerar DH."
    openvpn --genkey secret pki/ta.key || die "Falha ao gerar chave TA."
    [[ ! -s pki/ta.key ]] && die "Arquivo ta.key gerado, mas vazio ou inexistente. Verifique versão do OpenVPN."
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/ta.key /etc/openvpn/ || die "Falha ao copiar arquivos."
    chown root:root /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar propriedade."
    chmod 600 /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar permissões."
    [[ ! -s /etc/openvpn/ta.key ]] && die "ta.key copiado, mas vazio. Falha na geração."
    configure_server
    configure_firewall
    echo -e "${CYAN}Iniciando o serviço OpenVPN...${SCOLOR}"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable openvpn@server || die "Falha ao habilitar o serviço."
        systemctl start openvpn@server || die "Falha ao iniciar o serviço. Rode 'journalctl -xeu openvpn@server.service' para detalhes."
    else
        service openvpn@server start || die "Falha ao iniciar o serviço sem systemd."
    fi
    success "OpenVPN instalado e iniciado com sucesso!"
    echo -e "${CYAN}Criando o primeiro cliente...${SCOLOR}"
    create_client "cliente1"
}
configure_server() {
    echo -e "${CYAN}Configurando o servidor OpenVPN...${SCOLOR}"
    local IP
    IP=$(curl -s ifconfig.me 2>/dev/null) || IP=$(wget -4qO- "http://whatismyip.akamai.com/" 2>/dev/null) || IP=$(hostname -I | awk '{print $1}')
    [[ -z "$IP" ]] && die "Não foi possível determinar o IP público."
    PORT="1194"
    PROTOCOL="tcp"
    DNS1="8.8.8.8"
    DNS2="8.8.4.4"
    mkdir -p /var/log/openvpn || die "Falha ao criar diretório de logs."
    chown nobody:"$GROUPNAME" /var/log/openvpn || die "Falha ao ajustar permissões de logs."
    cat > /etc/openvpn/server.conf <<EOF
port $PORT
proto $PROTOCOL
dev tun
ca ca.crt
cert server.crt
key server.key
dh dh.pem
auth SHA512
tls-auth ta.key 0
key-direction 0
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS $DNS1"
push "dhcp-option DNS $DNS2"
keepalive 10 120
cipher AES-256-GCM
ncp-ciphers AES-256-GCM:AES-128-GCM
tls-version-min 1.2
user nobody
group $GROUPNAME
persist-key
persist-tun
status /var/log/openvpn/openvpn-status.log
log-append /var/log/openvpn/openvpn.log
verb 3
mssfix 1300
sndbuf 0
rcvbuf 0
txqueuelen 1000
socket-flags TCP_NODELAY
push "socket-flags TCP_NODELAY"
crl-verify crl.pem
EOF
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    ./easyrsa gen-crl || die "Falha ao gerar CRL."
    cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao copiar CRL."
    chown root:root /etc/openvpn/crl.pem
    chmod 644 /etc/openvpn/crl.pem
}
configure_firewall() {
    echo -e "${CYAN}Configurando o firewall...${SCOLOR}"
    sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
    sysctl -p >/dev/null || die "Falha ao ativar encaminhamento de IP."
    if [[ "$OS" = "debian" ]]; then
        local IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\\S+)' | head -1)
        [[ -z "$IFACE" ]] && die "Não foi possível determinar a interface de rede."
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables-save > /etc/iptables/rules.v4 || die "Falha ao salvar regras iptables."
        netfilter-persistent save || die "Falha ao persistir regras (verifique iptables-persistent)."
    elif [[ "$OS" = "centos" ]]; then
        systemctl start firewalld || die "Falha ao iniciar firewalld."
        systemctl enable firewalld || die "Falha ao habilitar firewalld."
        firewall-cmd --add-service=openvpn --permanent || die "Falha ao adicionar serviço OpenVPN."
        firewall-cmd --add-masquerade --permanent || die "Falha ao adicionar masquerade."
        firewall-cmd --reload || die "Falha ao recarregar firewalld."
    fi
}
create_client() {
    local CLIENT_NAME="$1"
    if [[ -z "$CLIENT_NAME" ]]; then
        echo -ne "${WHITE}Nome do cliente: ${SCOLOR}"
        read -r CLIENT_NAME
        [[ -z "$CLIENT_NAME" ]] && warn "Nome inválido." && return
    fi
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    [[ -f "pki/issued/${CLIENT_NAME}.crt" ]] && warn "Cliente '${CLIENT_NAME}' já existe." && return
    echo -e "${CYAN}Gerando certificado para '${CLIENT_NAME}'...${SCOLOR}"
    echo "yes" | ./easyrsa build-client-full "$CLIENT_NAME" nopass || die "Falha ao gerar certificado do cliente."
    local IP=$(curl -s ifconfig.me 2>/dev/null) || IP=$(wget -4qO- "http://whatismyip.akamai.com/" 2>/dev/null) || IP=$(hostname -I | awk '{print $1}')
    local PROTOCOL=$(grep '^proto' /etc/openvpn/server.conf | cut -d " " -f 2)
    local PORT=$(grep '^port' /etc/openvpn/server.conf | cut -d " " -f 2)
    local OVPN_DIR=~/ovpn-clients
    mkdir -p "$OVPN_DIR" || die "Falha ao criar diretório $OVPN_DIR."
    cat > "${OVPN_DIR}/${CLIENT_NAME}.ovpn" <<EOF
client
dev tun
proto ${PROTOCOL}
remote ${IP} ${PORT}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
cipher AES-256-GCM
key-direction 1
verb 3
<ca>
$(cat /etc/openvpn/easy-rsa/pki/ca.crt)
</ca>
<cert>
$(cat "/etc/openvpn/easy-rsa/pki/issued/${CLIENT_NAME}.crt")
</cert>
<key>
$(cat "/etc/openvpn/easy-rsa/pki/private/${CLIENT_NAME}.key")
</key>
<tls-auth>
$(cat /etc/openvpn/ta.key)
</tls-auth>
socket-flags TCP_NODELAY
EOF
    success "Configuração do cliente salva em: ${OVPN_DIR}/${CLIENT_NAME}.ovpn"
}
revoke_client() {
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    local clients=()
    while IFS= read -r file; do
        clients+=("$(basename "$file" .crt)")
    done < <(ls -1 pki/issued/*.crt 2>/dev/null)
    [[ ${#clients[@]} -eq 0 ]] && warn "Nenhum cliente para revogar." && return
    echo -e "${YELLOW}Selecione o cliente a revogar:${SCOLOR}"
    for i in "${!clients[@]}"; do
        echo " $((i + 1))) ${clients[$i]}"
    done
    echo -ne "${WHITE}Número do cliente: ${SCOLOR}"
    read -r choice
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#clients[@]} )); then
        warn "Seleção inválida."
        return
    fi
    local CLIENT_TO_REVOKE="${clients[$((choice - 1))]}"
    echo -ne "${YELLOW}Tem certeza que deseja revogar '${CLIENT_TO_REVOKE}'? [s/N]: ${SCOLOR}"
    read -r confirmation
    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        echo -e "${CYAN}Revogando o cliente...${SCOLOR}"
        echo "yes" | ./easyrsa revoke "$CLIENT_TO_REVOKE" || die "Falha ao revogar cliente."
        ./easyrsa gen-crl || die "Falha ao gerar CRL."
        cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao atualizar CRL."
        if command -v systemctl >/dev/null 2>&1; then
            systemctl restart openvpn@server || die "Falha ao reiniciar serviço."
        else
            service openvpn@server restart || die "Falha ao reiniciar serviço sem systemd."
        fi
        rm -f ~/ovpn-clients/"$CLIENT_TO_REVOKE".ovpn
        success "Cliente '${CLIENT_TO_REVOKE}' revogado."
    else
        warn "Operação cancelada."
    fi
}
uninstall_openvpn() {
    echo -ne "${RED}Tem CERTEZA que deseja remover o OpenVPN? [s/N]: ${SCOLOR}"
    read -r confirmation
    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        echo -e "${RED}Removendo o OpenVPN...${SCOLOR}"
        if command -v systemctl >/dev/null 2>&1; then
            systemctl stop openvpn@server 2>/dev/null
            systemctl disable openvpn@server 2>/dev/null
        else
            service openvpn@server stop 2>/dev/null
        fi
        if [[ "$OS" = "debian" ]]; then
            fun_bar "apt remove --purge -y openvpn easy-rsa iptables iptables-persistent lsof && apt autoremove -y"
            local iface=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\\S+)' | head -1)
            iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -j MASQUERADE 2>/dev/null
            iptables -D INPUT -i tun+ -j ACCEPT 2>/dev/null
            iptables -D FORWARD -i tun+ -j ACCEPT 2>/dev/null
            iptables -D FORWARD -i "$iface" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null
            iptables-save > /etc/iptables/rules.v4 2>/dev/null
            netfilter-persistent save 2>/dev/null
        elif [[ "$OS" = "centos" ]]; then
            fun_bar "yum remove -y openvpn easy-rsa firewalld lsof"
            firewall-cmd --remove-service=openvpn --permanent 2>/dev/null
            firewall-cmd --remove-masquerade --permanent 2>/dev/null
            firewall-cmd --reload 2>/dev/null
        fi
        rm -rf /etc/openvpn ~/ovpn-clients
        success "OpenVPN removido com sucesso."
    else
        warn "Remoção cancelada."
    fi
}
main() {
    clear
    check_root
    check_bash
    echo -e "${CYAN}O OpenVPN irá instalar com as seguintes configuraçoes: porta 1194, tcp, dns do google.${SCOLOR}"
    echo -e "${CYAN}Caso queira trocar configure no menu interativo.${SCOLOR}"
    echo
    echo -e "${WHITE}Deseja iniciar a instalação do openvpn?${SCOLOR}"
    echo -e "${YELLOW}1.${SCOLOR} sim"
    echo -e "${YELLOW}0.${SCOLOR} voltar"
    read -r opt
    case "$opt" in
        1)
            cleanup_previous_installations
            detect_os
            check_dependencies
            install_openvpn
            ;;
        *)
            warn "Instalação cancelada."
            exit 0
            ;;
    esac
}
main
