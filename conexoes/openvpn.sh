#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Versão Revisada, Refatorada e Aprimorada
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
readonly BOLD=$'\e[1m'

# --- Variáveis de Interface ---
readonly SCRIPT_VERSION="2.0.1"
readonly SCRIPT_NAME="OpenVPN Manager Pro"

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

print_line() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${SCOLOR}"
}

print_header() {
    clear
    print_line
    echo -e "${BOLD}${WHITE}                    ${SCRIPT_NAME} v${SCRIPT_VERSION}${SCOLOR}"
    print_line
}

print_footer() {
    print_line
    echo -e "${CYAN}          Desenvolvido com ❤️  para a comunidade VPN${SCOLOR}"
    print_line
}

loading_animation() {
    local text="$1"
    local dots=""
    for i in {1..3}; do
        echo -ne "\r${CYAN}${text}${dots}${SCOLOR}   "
        dots="${dots}."
        sleep 0.5
    done
    echo -ne "\r                                          \r"
}

fun_bar() {
    local cmd="$1"
    local spinner="/-\\|"
    local i=0
    local timeout=300  # 5min timeout em segundos

    eval "$cmd" &  
    local pid=$!
    tput civis
    echo -ne "${YELLOW}Aguarde... [${SCOLOR}"

    local start_time=$(date +%s)
    while ps -p "$pid" > /dev/null; do
        if [[ $(( $(date +%s) - start_time )) -gt $timeout ]]; then
            kill $pid 2>/dev/null
            die "Timeout na execução: $cmd demorou mais de 5min."
        fi
        echo -ne "${CYAN}${spinner:i++%${#spinner}:1}${SCOLOR}"
        sleep 0.2
        echo -ne "\b"
    done

    echo -e "${YELLOW}]${SCOLOR} - ${GREEN}Concluído!${SCOLOR}"
    tput cnorm
    wait "$pid" || die "Comando falhou: $cmd"
}

# --- Funções de Verificação ---
check_root() {
    [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."
}

check_bash() {
    [[ "$(readlink /proc/$$/exe)" != *"bash"* ]] && die "Execute este script com bash, não com sh."
}

check_tun() {
    [[ ! -e /dev/net/tun ]] && die "O dispositivo TUN/TAP não está disponível."
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
        echo -e "${YELLOW}Dependências em falta: ${missing[*]}${SCOLOR}"
        echo -ne "${WHITE}Deseja instalá-las automaticamente? [s/N]: ${SCOLOR}"
        read -r install_choice
        if [[ "$install_choice" =~ ^[sS]$ ]]; then
            echo -e "${CYAN}Instalando dependências...${SCOLOR}"
            fun_bar "apt update -qq && apt install -y -qq ${missing[*]}"
            check_remaining_dependencies "${packages[@]}" "${checks[@]}"
        else
            die "Instalação das dependências é necessária."
        fi
    else
        echo -e "${GREEN}✓ Todas as dependências estão presentes.${SCOLOR}"
    fi

    local ovpn_version
    ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    [[ "$ovpn_version" < "2.5" ]] && warn "Versão do OpenVPN ($ovpn_version) é antiga. Recomendo atualizar."
}

check_remaining_dependencies() {
    local packages=("$@")
    local checks=("${!#}")
    local still_missing=()
    
    for i in "${!packages[@]}"; do
        if ! eval "${checks[$i]}"; then
            still_missing+=("${packages[$i]}")
        fi
    done

    [[ ${#still_missing[@]} -gt 0 ]] && die "Falha ao instalar: ${still_missing[*]}."
    success "Dependências instaladas com sucesso!"
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

# --- Funções de Configuração do OpenVPN ---
install_openvpn() {
    print_header
    echo -e "${BOLD}${CYAN}              🚀 INSTALAÇÃO DO OPENVPN 🚀${SCOLOR}"
    print_line
    echo
    echo -e "${WHITE}Este assistente irá configurar um servidor OpenVPN seguro.${SCOLOR}"
    echo -e "${WHITE}O processo pode levar alguns minutos.${SCOLOR}"
    echo
    print_line
    echo -ne "${YELLOW}Pressione ENTER para continuar ou CTRL+C para cancelar...${SCOLOR}"
    read -r
    
    echo
    loading_animation "Preparando instalação"

    local EASY_RSA_DIR="/etc/openvpn/easy-rsa"
    mkdir -p "$EASY_RSA_DIR" || die "Falha ao criar diretório $EASY_RSA_DIR."
    cp -r /usr/share/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || cp -r /usr/lib/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || cp -r /usr/lib64/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || die "EasyRSA não encontrado."
    chmod +x "$EASY_RSA_DIR/easyrsa" || die "Falha ao ajustar permissões do EasyRSA."
    cd "$EASY_RSA_DIR" || die "Não foi possível acessar $EASY_RSA_DIR."
    
    echo
    info "Configurando infraestrutura de chaves (PKI)..."
    ./easyrsa init-pki || die "Falha ao inicializar PKI."
    
    info "Criando Autoridade Certificadora (CA)..."
    echo "Easy-RSA CA" | ./easyrsa build-ca nopass || die "Falha ao criar CA."
    
    info "Gerando certificado do servidor..."
    echo "yes" | ./easyrsa build-server-full server nopass || die "Falha ao criar certificado do servidor."
    
    info "Gerando parâmetros Diffie-Hellman (pode demorar)..."
    ./easyrsa gen-dh || die "Falha ao gerar DH."
    
    info "Gerando chave de autenticação TLS..."
    openvpn --genkey secret pki/ta.key || die "Falha ao gerar chave TA."

    info "Copiando arquivos de configuração..."
    cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/ta.key /etc/openvpn/ || die "Falha ao copiar arquivos."
    chown root:root /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar propriedade."
    chmod 600 /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar permissões."

    configure_server
    configure_firewall
    start_openvpn_service
    
    echo
    print_line
    echo -e "${GREEN}${BOLD}     ✅ OPENVPN INSTALADO COM SUCESSO! ✅${SCOLOR}"
    print_line
    echo
    
    info "Criando primeiro cliente de demonstração..."
    create_client "cliente1"
    
    echo
    print_footer
    echo -ne "${CYAN}Pressione ENTER para voltar ao menu principal...${SCOLOR}"
    read -r
}

configure_server() {
    echo
    print_line
    echo -e "${BOLD}${WHITE}           ⚙️  CONFIGURAÇÃO DO SERVIDOR ⚙️${SCOLOR}"
    print_line
    echo
    
    local IP
    IP=$(curl -s ifconfig.me 2>/dev/null || wget -4qO- "http://ifconfig.me" 2>/dev/null || hostname -I | awk '{print $1}')
    [[ -z "$IP" ]] && die "Não foi possível determinar o IP público."
    
    echo -e "${GREEN}✓${SCOLOR} IP Público detectado: ${BOLD}${WHITE}$IP${SCOLOR}"
    echo
    
    echo -e "${CYAN}📌 Configuração da Porta:${SCOLOR}"
    echo -ne "${WHITE}   Digite a porta para o OpenVPN [${GREEN}1194${WHITE}]: ${SCOLOR}"
    read -r PORT
    [[ -z "$PORT" ]] && PORT="1194"
    echo -e "${GREEN}   ✓${SCOLOR} Porta selecionada: ${BOLD}$PORT${SCOLOR}"
    echo

    echo -e "${CYAN}📌 Configuração do Protocolo:${SCOLOR}"
    echo -e "${WHITE}   [1] UDP ${GREEN}(recomendado)${SCOLOR}"
    echo -e "${WHITE}   [2] TCP${SCOLOR}"
    echo -ne "${WHITE}   Escolha [${GREEN}1${WHITE}]: ${SCOLOR}"
    read -r PROTOCOL_CHOICE
    case $PROTOCOL_CHOICE in
        2) PROTOCOL="tcp"; PROTO_DISPLAY="TCP" ;;
        *) PROTOCOL="udp"; PROTO_DISPLAY="UDP" ;;
    esac
    echo -e "${GREEN}   ✓${SCOLOR} Protocolo selecionado: ${BOLD}$PROTO_DISPLAY${SCOLOR}"
    echo

    echo -e "${CYAN}📌 Configuração de DNS:${SCOLOR}"
    echo -e "${WHITE}   [1] Google DNS ${GREEN}(8.8.8.8)${SCOLOR}"
    echo -e "${WHITE}   [2] Cloudflare ${GREEN}(1.1.1.1)${SCOLOR}"
    echo -e "${WHITE}   [3] OpenDNS ${GREEN}(208.67.222.222)${SCOLOR}"
    echo -ne "${WHITE}   Escolha [${GREEN}1${WHITE}]: ${SCOLOR}"
    read -r DNS_CHOICE
    case $DNS_CHOICE in
        2) DNS1="1.1.1.1"; DNS2="1.0.0.1"; DNS_NAME="Cloudflare" ;;
        3) DNS1="208.67.222.222"; DNS2="208.67.220.220"; DNS_NAME="OpenDNS" ;;
        *) DNS1="8.8.8.8"; DNS2="8.8.4.4"; DNS_NAME="Google" ;;
    esac
    echo -e "${GREEN}   ✓${SCOLOR} DNS selecionado: ${BOLD}$DNS_NAME${SCOLOR}"

    mkdir -p /var/log/openvpn || die "Falha ao criar diretório de logs."
    chown nobody:"$GROUPNAME" /var/log/openvpn || die "Falha ao ajustar permissões de logs."
    
    loading_animation "Gerando configuração do servidor"
    
    cat > /etc/openvpn/server.conf << EOF
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
crl-verify crl.pem
EOF

    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    ./easyrsa gen-crl || die "Falha ao gerar CRL."
    cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao copiar CRL."
    chown root:root /etc/openvpn/crl.pem
    chmod 644 /etc/openvpn/crl.pem
    
    success "Servidor configurado com sucesso!"
}

configure_firewall() {
    echo
    info "Configurando firewall e roteamento..."
    sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
    sysctl -p >/dev/null || die "Falha ao ativar encaminhamento de IP."

    if [[ "$OS" = "debian" ]]; then
        local IFACE
        IFACE=$(ip -4 route ls | grep default | grep -Po '(?<=dev )(\S+)' | head -1)
        [[ -z "$IFACE" ]] && die "Não foi possível determinar a interface de rede."
        iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE
        iptables -A INPUT -i tun+ -j ACCEPT
        iptables -A FORWARD -i tun+ -j ACCEPT
        iptables -A FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables-save > /etc/iptables/rules.v4 || die "Falha ao salvar regras iptables."
        netfilter-persistent save || die "Falha ao persistir regras."
    elif [[ "$OS" = "centos" ]]; then
        systemctl start firewalld || die "Falha ao iniciar firewalld."
        systemctl enable firewalld || die "Falha ao habilitar firewalld."
        firewall-cmd --add-service=openvpn --permanent || die "Falha ao adicionar serviço OpenVPN."
        firewall-cmd --add-masquerade --permanent || die "Falha ao adicionar masquerade."
        firewall-cmd --reload || die "Falha ao recarregar firewalld."
    fi
    success "Firewall configurado!"
}

start_openvpn_service() {
    echo
    info "Iniciando serviço OpenVPN..."
    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable openvpn@server || die "Falha ao habilitar o serviço."
        systemctl start openvpn@server || die "Falha ao iniciar o serviço."
    else
        service openvpn@server start || die "Falha ao iniciar o serviço sem systemd."
    fi
    success "Serviço OpenVPN iniciado!"
}

create_client() {
    local CLIENT_NAME="${1:-}"
    
    if [[ -z "$CLIENT_NAME" ]]; then
        print_header
        echo -e "${BOLD}${CYAN}              👤 CRIAR NOVO CLIENTE 👤${SCOLOR}"
        print_line
        echo
        echo -ne "${WHITE}Digite o nome do cliente: ${SCOLOR}"
        read -r CLIENT_NAME
        [[ -z "$CLIENT_NAME" ]] && warn "Nome inválido." && return
    fi

    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    [[ -f "pki/issued/${CLIENT_NAME}.crt" ]] && warn "Cliente '$CLIENT_NAME' já existe." && return

    echo
    loading_animation "Gerando certificado para '$CLIENT_NAME'"
    echo "yes" | ./easyrsa build-client-full "$CLIENT_NAME" nopass || die "Falha ao gerar certificado do cliente."

    local IP PROTOCOL PORT
    IP=$(curl -s ifconfig.me 2>/dev/null || wget -4qO- "http://ifconfig.me" 2>/dev/null || hostname -I | awk '{print $1}')
    PROTOCOL=$(grep '^proto' /etc/openvpn/server.conf | cut -d " " -f 2)
    PORT=$(grep '^port' /etc/openvpn/server.conf | cut -d " " -f 2)

    local OVPN_DIR=~/ovpn-clients
    mkdir -p "$OVPN_DIR" || die "Falha ao criar diretório $OVPN_DIR."

    loading_animation "Criando arquivo de configuração"
    
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
    
    echo
    print_line
    echo -e "${GREEN}${BOLD}     ✅ CLIENTE CRIADO COM SUCESSO! ✅${SCOLOR}"
    print_line
    echo
    echo -e "${WHITE}📁 Arquivo de configuração salvo em:${SCOLOR}"
    echo -e "${CYAN}   ${OVPN_DIR}/${CLIENT_NAME}.ovpn${SCOLOR}"
    echo
    echo -e "${YELLOW}💡 Dica: Transfira este arquivo para o dispositivo cliente${SCOLOR}"
    echo -e "${YELLOW}   e importe no aplicativo OpenVPN.${SCOLOR}"
    echo
    print_footer
}

revoke_client() {
    print_header
    echo -e "${BOLD}${CYAN}              🚫 REVOGAR CLIENTE 🚫${SCOLOR}"
    print_line
    echo
    
    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    
    local clients=()
    while IFS= read -r file; do
        clients+=("$(basename "$file" .crt)")
    done < <(ls -1 pki/issued/*.crt 2>/dev/null | grep -v server.crt)

    if [[ ${#clients[@]} -eq 0 ]]; then
        echo -e "${YELLOW}⚠️  Nenhum cliente disponível para revogar.${SCOLOR}"
        echo
        print_footer
        echo -ne "${CYAN}Pressione ENTER para voltar...${SCOLOR}"
        read -r
        return
    fi

    echo -e "${WHITE}Selecione o cliente que deseja revogar:${SCOLOR}"
    echo
    for i in "${!clients[@]}"; do
        echo -e "  ${CYAN}[$((i + 1))]${SCOLOR} ${WHITE}${clients[$i]}${SCOLOR}"
    done
    echo
    echo -e "  ${RED}[0]${SCOLOR} ${WHITE}Cancelar${SCOLOR}"
    echo
    print_line
    echo -ne "${WHITE}Digite sua escolha: ${SCOLOR}"
    read -r choice

    if [[ "$choice" == "0" ]]; then
        return
    fi
    
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#clients[@]} )); then
        warn "Seleção inválida."
        sleep 2
        return
    fi

    local CLIENT_TO_REVOKE="${clients[$((choice - 1))]}"
    
    echo
    echo -e "${RED}⚠️  ATENÇÃO: Esta ação não pode ser desfeita!${SCOLOR}"
    echo -ne "${YELLOW}Confirma a revogação de '${WHITE}${CLIENT_TO_REVOKE}${YELLOW}'? [s/N]: ${SCOLOR}"
    read -r confirmation
    
    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        echo
        loading_animation "Revogando cliente '$CLIENT_TO_REVOKE'"
        echo "yes" | ./easyrsa revoke "$CLIENT_TO_REVOKE" || die "Falha ao revogar cliente."
        ./easyrsa gen-crl || die "Falha ao gerar CRL."
        cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao atualizar CRL."
        start_openvpn_service
        rm -f ~/ovpn-clients/"$CLIENT_TO_REVOKE".ovpn
        
        echo
        print_line
        echo -e "${GREEN}${BOLD}     ✅ CLIENTE REVOGADO COM SUCESSO! ✅${SCOLOR}"
        print_line
        echo
        echo -e "${WHITE}Cliente '${CLIENT_TO_REVOKE}' foi revogado e removido do sistema.${SCOLOR}"
        echo
        print_footer
    else
        echo
        warn "Operação cancelada."
    fi
    
    echo -ne "${CYAN}Pressione ENTER para voltar...${SCOLOR}"
    read -r
}

uninstall_openvpn() {
    print_header
    echo -e "${BOLD}${RED}           ⚠️  DESINSTALAÇÃO DO OPENVPN ⚠️${SCOLOR}"
    print_line
    echo
    echo -e "${YELLOW}Esta ação irá:${SCOLOR}"
    echo -e "${WHITE}  • Parar o serviço OpenVPN${SCOLOR}"
    echo -e "${WHITE}  • Remover todos os pacotes relacionados${SCOLOR}"
    echo -e "${WHITE}  • Apagar todas as configurações${SCOLOR}"
    echo -e "${WHITE}  • Remover todos os certificados de clientes${SCOLOR}"
    echo
    echo -e "${RED}⚠️  ESTA AÇÃO NÃO PODE SER DESFEITA!${SCOLOR}"
    echo
    print_line
    echo -ne "${RED}Digite 'CONFIRMAR' para prosseguir com a desinstalação: ${SCOLOR}"
    read -r confirmation

    if [[ "$confirmation" == "CONFIRMAR" ]]; then
        echo
        loading_animation "Parando serviços"
        
        if command -v systemctl >/dev/null 2>&1; then
            systemctl stop openvpn@server 2>/dev/null
            systemctl disable openvpn@server 2>/dev/null
        else
            service openvpn@server stop 2>/dev/null
        fi

        loading_animation "Removendo pacotes"
        
        if [[ "$OS" = "debian" ]]; then
            fun_bar "apt remove --purge -y openvpn easy-rsa iptables iptables-persistent lsof && apt autoremove -y"
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

        loading_animation "Removendo arquivos de configuração"
        rm -rf /etc/openvpn ~/ovpn-clients
        
        echo
        print_line
        echo -e "${GREEN}${BOLD}     ✅ OPENVPN REMOVIDO COM SUCESSO! ✅${SCOLOR}"
        print_line
        echo
        print_footer
    else
        echo
        warn "Desinstalação cancelada."
    fi
    
    echo -ne "${CYAN}Pressione ENTER para sair...${SCOLOR}"
    read -r
    exit 0
}

# --- Menu Principal ---
main_menu() {
    while true; do
        print_header
        
        if systemctl is-active --quiet openvpn@server 2>/dev/null; then
            local port proto clients_count
            port=$(grep '^port' /etc/openvpn/server.conf 2>/dev/null | awk '{print $2}')
            proto=$(grep '^proto' /etc/openvpn/server.conf 2>/dev/null | awk '{print $2}' | tr '[:lower:]' '[:upper:]')
            clients_count=$(ls -1 /etc/openvpn/easy-rsa/pki/issued/*.crt 2>/dev/null | grep -v server.crt | wc -l)
            
            echo -e "${BOLD}${WHITE}                   📊 STATUS DO SERVIDOR${SCOLOR}"
            print_line
            echo
            echo -e "  ${GREEN}●${SCOLOR} Status: ${GREEN}${BOLD}ATIVO${SCOLOR}"
            echo -e "  ${WHITE}📡${SCOLOR} Porta: ${CYAN}${port}${SCOLOR}"
            echo -e "  ${WHITE}🔌${SCOLOR} Protocolo: ${CYAN}${proto}${SCOLOR}"
            echo -e "  ${WHITE}👥${SCOLOR} Clientes: ${CYAN}${clients_count}${SCOLOR}"
            echo
            print_line
            echo -e "${BOLD}${WHITE}                      MENU DE OPÇÕES${SCOLOR}"
            print_line
            echo
            echo -e "  ${CYAN}[1]${SCOLOR} ${WHITE}👤 Criar novo cliente${SCOLOR}"
            echo -e "  ${CYAN}[2]${SCOLOR} ${WHITE}🚫 Revogar cliente existente${SCOLOR}"
            echo -e "  ${CYAN}[3]${SCOLOR} ${WHITE}📋 Listar clientes ativos${SCOLOR}"
            echo -e "  ${CYAN}[4]${SCOLOR} ${WHITE}🗑️  Desinstalar OpenVPN${SCOLOR}"
            echo
            echo -e "  ${MAGENTA}[0]${SCOLOR} ${WHITE}🚪 Sair${SCOLOR}"
        else
            echo -e "${BOLD}${WHITE}                   📊 STATUS DO SERVIDOR${SCOLOR}"
            print_line
            echo
            echo -e "  ${RED}●${SCOLOR} Status: ${RED}${BOLD}NÃO INSTALADO${SCOLOR}"
            echo
            print_line
            echo -e "${BOLD}${WHITE}                      MENU DE OPÇÕES${SCOLOR}"
            print_line
            echo
            echo -e "  ${CYAN}[1]${SCOLOR} ${WHITE}🚀 Instalar OpenVPN${SCOLOR}"
            echo
            echo -e "  ${MAGENTA}[0]${SCOLOR} ${WHITE}🚪 Sair${SCOLOR}"
        fi
        
        echo
        print_line
        echo -ne "${WHITE}Digite sua opção: ${SCOLOR}"
        read -r choice

        if systemctl is-active --quiet openvpn@server 2>/dev/null; then
            case "$choice" in
                1) create_client ;;
                2) revoke_client ;;
                3) 
                    print_header
                    echo -e "${BOLD}${CYAN}              📋 CLIENTES ATIVOS 📋${SCOLOR}"
                    print_line
                    echo
                    local client_list=()
                    while IFS= read -r file; do
                        client_list+=("$(basename "$file" .crt)")
                    done < <(ls -1 /etc/openvpn/easy-rsa/pki/issued/*.crt 2>/dev/null | grep -v server.crt)
                    
                    if [[ ${#client_list[@]} -eq 0 ]]; then
                        echo -e "${YELLOW}  Nenhum cliente cadastrado.${SCOLOR}"
                    else
                        for client in "${client_list[@]}"; do
                            echo -e "  ${GREEN}✓${SCOLOR} ${WHITE}${client}${SCOLOR}"
                        done
                    fi
                    echo
                    print_footer
                    echo -ne "${CYAN}Pressione ENTER para voltar...${SCOLOR}"
                    read -r
                    ;;
                4) uninstall_openvpn ;;
                0) 
                    print_footer
                    echo -e "${WHITE}Obrigado por usar ${SCRIPT_NAME}!${SCOLOR}"
                    echo
                    exit 0 
                    ;;
                *) 
                    warn "Opção inválida!"
                    sleep 1
                    ;;
            esac
        else
            case "$choice" in
                1) install_openvpn ;;
                0) 
                    print_footer
                    echo -e "${WHITE}Obrigado por usar ${SCRIPT_NAME}!${SCOLOR}"
                    echo
                    exit 0 
                    ;;
                *) 
                    warn "Opção inválida!"
                    sleep 1
                    ;;
            esac
        fi
    done
}

# --- Ponto de Entrada ---
main() {
    check_root
    check_bash
    check_tun
    detect_os
    
    print_header
    echo -e "${BOLD}${WHITE}              🔍 VERIFICAÇÃO DO SISTEMA 🔍${SCOLOR}"
    print_line
    echo
    
    echo -e "${CYAN}Verificando requisitos do sistema...${SCOLOR}"
    echo
    
    echo -ne "  ${WHITE}Sistema Operacional:${SCOLOR} "
    loading_animation ""
    echo -e "${GREEN}✓${SCOLOR} ${WHITE}$(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)${SCOLOR}"
    
    echo -ne "  ${WHITE}Permissões ROOT:${SCOLOR} "
    loading_animation ""
    echo -e "${GREEN}✓${SCOLOR} ${WHITE}Confirmado${SCOLOR}"
    
    echo -ne "  ${WHITE}Dispositivo TUN/TAP:${SCOLOR} "
    loading_animation ""
    echo -e "${GREEN}✓${SCOLOR} ${WHITE}Disponível${SCOLOR}"
    
    echo -ne "  ${WHITE}Verificando dependências:${SCOLOR} "
    loading_animation ""
    check_dependencies
    
    echo
    print_footer
    echo -ne "${CYAN}Pressione ENTER para continuar...${SCOLOR}"
    read -r
    
    main_menu
}

main
