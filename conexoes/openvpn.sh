#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager - Versão Automática
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Versão Revisada, Refatorada e Aprimorada (Instalação Automática)
# =================================================================
# --- Variáveis de Cor ---
readonly RED=$'\e[1;31m'
readonly GREEN=$'\e[1;32m'
readonly YELLOW=$'\e[1;33m'
readonly BLUE=$'\e[1;34m'
readonly CYAN=$'\e[1;36m'
readonly WHITE=$'\e[1;37m'
readonly SCOLOR=$'\e[0m'

# --- Configurações Automáticas ---
readonly AUTO_PORT="1194"
readonly AUTO_PROTOCOL="tcp"
readonly AUTO_DNS1="8.8.8.8"
readonly AUTO_DNS2="8.8.4.4"

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

fun_bar() {
    local cmd="$1"
    local spinner="/-\\|"
    local i=0
    local timeout=300  # 5min timeout em segundos
   
    eval "$cmd" &  # Removido >/dev/null 2>&1 para mostrar outputs reais
    local pid=$!
   
    tput civis
    echo -ne "${YELLOW}Aguarde... [${SCOLOR}"
   
    local start_time=$(date +%s)
    while ps -p "$pid" > /dev/null; do
        current_time=$(date +%s)
        if [[ $((current_time - start_time)) -gt $timeout ]]; then
            kill $pid 2>/dev/null
            die "Timeout na execução: $cmd demorou mais de 5min. Verifique rede ou mirrors."
        fi
        i=$(( (i + 1) % 4 ))
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

check_tun() {
    [[ ! -e /dev/net/tun ]] && die "O dispositivo TUN/TAP não está disponível. Ative-o com 'modprobe tun' ou verifique o kernel."
}

check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "lsof")
    local checks=("command -v openvpn" "[ -d /usr/share/easy-rsa ] || [ -d /usr/lib/easy-rsa ] || [ -d /usr/lib64/easy-rsa ]" "command -v iptables" "command -v lsof")
   
    if [[ "$OS" == "debian" ]]; then
        packages+=("iptables-persistent")
        checks+=("command -v iptables-save")
    fi
   
    for i in "${!packages[@]}"; do
        if ! eval "${checks[$i]}"; then
            missing+=("${packages[$i]}")
        fi
    done
   
    if [[ ${#missing[@]} -gt 0 ]]; then
        info "Dependências em falta detectadas: ${missing[*]}"
        info "Instalando dependências automaticamente..."
        
        if [[ "$OS" == "debian" ]]; then
            # Configurar respostas automáticas para iptables-persistent
            echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
            echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections
            
            fun_bar "apt update -qq && DEBIAN_FRONTEND=noninteractive apt install -y -qq ${missing[*]}"
        elif [[ "$OS" == "centos" ]]; then
            if ! yum list installed epel-release >/dev/null 2>&1; then
                fun_bar "yum install -y epel-release"
            fi
            fun_bar "yum install -y ${missing[*]}"
        fi
       
        local still_missing=()
        for i in "${!packages[@]}"; do
            if ! eval "${checks[$i]}"; then
                still_missing+=("${packages[$i]}")
            fi
        done
        [[ ${#still_missing[@]} -gt 0 ]] && die "Falha ao instalar: ${still_missing[*]}."
        success "Dependências instaladas com sucesso!"
    else
        info "Todas as dependências já estão presentes."
    fi
    
    local ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    if [[ "$ovpn_version" < "2.5" ]]; then
        warn "Versão do OpenVPN ($ovpn_version) é antiga. Recomendo atualizar para 2.5+ para compatibilidade."
    fi
}

# --- Detecção de Sistema Operacional ---
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

# --- Funções Principais do OpenVPN ---
install_openvpn() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${BLUE}║   Instalação Automática do OpenVPN     ║${SCOLOR}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    info "Configurações automáticas:"
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT${SCOLOR}"
    echo -e "  ${WHITE}• Protocolo:${SCOLOR} ${GREEN}$AUTO_PROTOCOL${SCOLOR}"
    echo -e "  ${WHITE}• DNS:${SCOLOR} ${GREEN}Google ($AUTO_DNS1, $AUTO_DNS2)${SCOLOR}"
    echo
    
    sleep 2
    
    local EASY_RSA_DIR="/etc/openvpn/easy-rsa"
    
    info "Criando estrutura de diretórios..."
    mkdir -p "$EASY_RSA_DIR" || die "Falha ao criar diretório $EASY_RSA_DIR."
    
    info "Copiando arquivos do Easy-RSA..."
    cp -r /usr/share/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    cp -r /usr/lib/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    cp -r /usr/lib64/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    die "EasyRSA não encontrado."
    
    chmod +x "$EASY_RSA_DIR/easyrsa" || die "Falha ao ajustar permissões do EasyRSA."
    cd "$EASY_RSA_DIR" || die "Não foi possível acessar $EASY_RSA_DIR."
    
    info "Inicializando PKI..."
    ./easyrsa init-pki || die "Falha ao inicializar PKI."
    
    info "Criando Autoridade Certificadora..."
    echo "Easy-RSA CA" | ./easyrsa build-ca nopass || die "Falha ao criar CA."
    
    info "Gerando certificado do servidor..."
    echo "yes" | ./easyrsa build-server-full server nopass || die "Falha ao criar certificado do servidor."
    
    info "Gerando parâmetros Diffie-Hellman (pode demorar alguns minutos)..."
    ./easyrsa gen-dh || die "Falha ao gerar DH."
    
    info "Gerando chave TLS-Auth..."
    openvpn --genkey secret pki/ta.key || die "Falha ao gerar chave TA."
    [[ ! -s pki/ta.key ]] && die "Arquivo ta.key gerado, mas vazio ou inexistente. Verifique versão do OpenVPN."
   
    info "Copiando certificados para /etc/openvpn..."
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/ta.key /etc/openvpn/ || die "Falha ao copiar arquivos."
    chown root:root /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar propriedade."
    chmod 600 /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar permissões."
    [[ ! -s /etc/openvpn/ta.key ]] && die "ta.key copiado, mas vazio. Falha na geração."
   
    configure_server_auto
    configure_firewall_auto
    
    info "Iniciando o serviço OpenVPN..."
    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable openvpn@server || die "Falha ao habilitar o serviço."
        systemctl start openvpn@server || die "Falha ao iniciar o serviço. Rode 'journalctl -xeu openvpn@server.service' para detalhes."
    else
        service openvpn@server start || die "Falha ao iniciar o serviço sem systemd."
    fi
   
    success "OpenVPN instalado e iniciado com sucesso!"
   
    info "Criando o primeiro cliente automaticamente..."
    create_client "cliente1"
    
    echo
    echo -e "${GREEN}╔════════════════════════════════════════╗${SCOLOR}"
    echo -e "${GREEN}║   Instalação Concluída com Sucesso!    ║${SCOLOR}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${SCOLOR}"
    echo
    echo -e "${WHITE}Detalhes da instalação:${SCOLOR}"
    echo -e "  ${WHITE}• IP do servidor:${SCOLOR} ${GREEN}$(get_public_ip)${SCOLOR}"
    echo -e "  ${WHITE}• Porta:${SCOLOR} ${GREEN}$AUTO_PORT${SCOLOR}"
    echo -e "  ${WHITE}• Protocolo:${SCOLOR} ${GREEN}$AUTO_PROTOCOL${SCOLOR}"
    echo -e "  ${WHITE}• Arquivo do cliente:${SCOLOR} ${GREEN}~/ovpn-clients/cliente1.ovpn${SCOLOR}"
    echo
    echo -e "${CYAN}Pressione ENTER para voltar ao menu...${SCOLOR}"
    read -r
}

get_public_ip() {
    local IP
    IP=$(curl -s ifconfig.me 2>/dev/null) || \
    IP=$(wget -4qO- "http://whatismyip.akamai.com/" 2>/dev/null) || \
    IP=$(hostname -I | awk '{print $1}')
    echo "$IP"
}

configure_server_auto() {
    info "Configurando o servidor OpenVPN automaticamente..."
   
    local IP
    IP=$(get_public_ip)
    [[ -z "$IP" ]] && die "Não foi possível determinar o IP público."
   
    mkdir -p /var/log/openvpn || die "Falha ao criar diretório de logs."
    chown nobody:"$GROUPNAME" /var/log/openvpn || die "Falha ao ajustar permissões de logs."
   
    cat > /etc/openvpn/server.conf << EOF
port $AUTO_PORT
proto $AUTO_PROTOCOL
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
push "dhcp-option DNS $AUTO_DNS1"
push "dhcp-option DNS $AUTO_DNS2"
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
crl-verify crl.pem
EOF
    
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    ./easyrsa gen-crl || die "Falha ao gerar CRL."
    cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao copiar CRL."
    chown root:root /etc/openvpn/crl.pem
    chmod 644 /etc/openvpn/crl.pem
    
    success "Servidor configurado com sucesso!"
}

configure_firewall_auto() {
    info "Configurando firewall automaticamente..."
    
    # Ativar encaminhamento de IP
    sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf 2>/dev/null
    sysctl -p >/dev/null || die "Falha ao ativar encaminhamento de IP."
    
    if [[ "$OS" = "debian" ]]; then
        local IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
        [[ -z "$IFACE" ]] && die "Não foi possível determinar a interface de rede."
        
        info "Interface de rede detectada: $IFACE"
        
        # Adicionar regras do iptables
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        
        # Salvar regras
        iptables-save > /etc/iptables/rules.v4 || die "Falha ao salvar regras iptables."
        netfilter-persistent save >/dev/null 2>&1 || true
        
    elif [[ "$OS" = "centos" ]]; then
        systemctl start firewalld || die "Falha ao iniciar firewalld."
        systemctl enable firewalld || die "Falha ao habilitar firewalld."
        firewall-cmd --add-service=openvpn --permanent || die "Falha ao adicionar serviço OpenVPN."
        firewall-cmd --add-port=$AUTO_PORT/tcp --permanent || die "Falha ao adicionar porta."
        firewall-cmd --add-masquerade --permanent || die "Falha ao adicionar masquerade."
        firewall-cmd --reload || die "Falha ao recarregar firewalld."
    fi
    
    success "Firewall configurado com sucesso!"
}

create_client() {
    local CLIENT_NAME="$1"
   
    if [[ -z "$CLIENT_NAME" ]]; then
        echo -ne "${WHITE}Nome do cliente: ${SCOLOR}"
        read -r CLIENT_NAME
        [[ -z "$CLIENT_NAME" ]] && warn "Nome inválido." && return
    fi
   
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    [[ -f "pki/issued/${CLIENT_NAME}.crt" ]] && warn "Cliente '$CLIENT_NAME' já existe." && return
   
    info "Gerando certificado para '$CLIENT_NAME'..."
    echo "yes" | ./easyrsa build-client-full "$CLIENT_NAME" nopass || die "Falha ao gerar certificado do cliente."
   
    local IP PROTOCOL PORT
    IP=$(get_public_ip)
    PROTOCOL=$(grep '^proto' /etc/openvpn/server.conf | cut -d " " -f 2)
    PORT=$(grep '^port' /etc/openvpn/server.conf | cut -d " " -f 2)
   
    local OVPN_DIR=~/ovpn-clients
    mkdir -p "$OVPN_DIR" || die "Falha ao criar diretório $OVPN_DIR."
   
    cat > "${OVPN_DIR}/${CLIENT_NAME}.ovpn" << EOF
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
EOF
    
    success "Configuração do cliente salva em: ${OVPN_DIR}/${CLIENT_NAME}.ovpn"
}

revoke_client() {
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
   
    local clients=()
    while IFS= read -r file; do
        clients+=("$(basename "$file" .crt)")
    done < <(ls -1 pki/issued/*.crt 2>/dev/null | grep -v server.crt)
   
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
   
    echo -ne "${YELLOW}Tem certeza que deseja revogar '$CLIENT_TO_REVOKE'? [s/N]: ${SCOLOR}"
    read -r confirmation
   
    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        info "Revogando o cliente..."
        echo "yes" | ./easyrsa revoke "$CLIENT_TO_REVOKE" || die "Falha ao revogar cliente."
        ./easyrsa gen-crl || die "Falha ao gerar CRL."
        cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao atualizar CRL."
        
        if command -v systemctl >/dev/null 2>&1; then
            systemctl restart openvpn@server || die "Falha ao reiniciar serviço."
        else
            service openvpn@server restart || die "Falha ao reiniciar serviço sem systemd."
        fi
        
        rm -f ~/ovpn-clients/"$CLIENT_TO_REVOKE".ovpn
        success "Cliente '$CLIENT_TO_REVOKE' revogado com sucesso!"
    else
        warn "Operação cancelada."
    fi
}

uninstall_openvpn() {
    echo -ne "${RED}Tem CERTEZA que deseja remover o OpenVPN? [s/N]: ${SCOLOR}"
    read -r confirmation
   
    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        info "Removendo o OpenVPN..."
       
        if command -v systemctl >/dev/null 2>&1; then
            systemctl stop openvpn@server 2>/dev/null
            systemctl disable openvpn@server 2>/dev/null
        else
            service openvpn@server stop 2>/dev/null
        fi
       
        if [[ "$OS" = "debian" ]]; then
            fun_bar "apt remove --purge -y openvpn easy-rsa iptables iptables-persistent lsof && apt autoremove -y"
            
            # Limpar regras do iptables
            iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -j MASQUERADE 2>/dev/null
            iptables -D INPUT -i tun+ -j ACCEPT 2>/dev/null
            iptables -D FORWARD -i tun+ -j ACCEPT 2>/dev/null
            iptables -D FORWARD -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null
            iptables-save > /etc/iptables/rules.v4 2>/dev/null
            netfilter-persistent save 2>/dev/null
            
        elif [[ "$OS" = "centos" ]]; then
            fun_bar "yum remove -y openvpn easy-rsa firewalld lsof"
            firewall-cmd --remove-service=openvpn --permanent 2>/dev/null
            firewall-cmd --remove-masquerade --permanent 2>/dev/null
            firewall-cmd --reload 2>/dev/null
        fi
       
        rm -rf /etc/openvpn ~/ovpn-clients
        success "OpenVPN removido com sucesso!"
    else
        warn "Remoção cancelada."
    fi
}

# --- Menus de Gestão ---
main_menu() {
    while true; do
        clear
        echo -e "${BLUE}╔════════════════════════════════════════╗${SCOLOR}"
        echo -e "${BLUE}║   OpenVPN Installer & Manager v2.0     ║${SCOLOR}"
        echo -e "${BLUE}╚════════════════════════════════════════╝${SCOLOR}"
        echo -e "${CYAN}Versão com Instalação Automática${SCOLOR}\n"
       
        if systemctl is-active --quiet openvpn@server 2>/dev/null || service openvpn@server status >/dev/null 2>&1; then
            local port proto ip
            port=$(grep '^port' /etc/openvpn/server.conf 2>/dev/null | awk '{print $2}')
            proto=$(grep '^proto' /etc/openvpn/server.conf 2>/dev/null | awk '{print $2}')
            ip=$(get_public_ip)
            
            echo -e "${GREEN}● STATUS: Ativo${SCOLOR}"
            echo -e "${WHITE}  IP: $ip | Porta: $port ($proto)${SCOLOR}\n"
            
            echo -e "${YELLOW}1)${SCOLOR} Criar um novo cliente"
            echo -e "${YELLOW}2)${SCOLOR} Revogar um cliente existente"
            echo -e "${YELLOW}3)${SCOLOR} Desinstalar o OpenVPN"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        else
            echo -e "${RED}● STATUS: Não Instalado${SCOLOR}\n"
            echo -e "${YELLOW}1)${SCOLOR} Instalar OpenVPN (Automático)"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        fi
       
        echo -ne "\n${WHITE}Escolha uma opção: ${SCOLOR}"
        read -r choice
       
        if systemctl is-active --quiet openvpn@server 2>/dev/null || service openvpn@server status >/dev/null 2>&1; then
            case "$choice" in
                1) create_client ;;
                2) revoke_client ;;
                3) uninstall_openvpn; main_menu ;;
                0) 
                    echo -e "\n${GREEN}Obrigado por usar o OpenVPN Manager!${SCOLOR}"
                    exit 0 
                    ;;
                *) warn "Opção inválida." ;;
            esac
        else
            case "$choice" in
                1) install_openvpn ;;
                0) 
                    echo -e "\n${GREEN}Obrigado por usar o OpenVPN Manager!${SCOLOR}"
                    exit 0 
                    ;;
                *) warn "Opção inválida." ;;
            esac
        fi
        
        if [[ -n "$choice" && "$choice" != "0" && "$choice" != "3" ]]; then
            echo -e "\n${CYAN}Pressione ENTER para continuar...${SCOLOR}"
            read -r
        fi
    done
}

# --- Ponto de Entrada ---
main() {
    clear
    check_root
    check_bash
    check_tun
    detect_os
    check_dependencies
    main_menu
}

# Executar o script
main
