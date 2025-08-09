#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Versão Revisada, Refatorada e Aprimorada
# - Melhoria na escolha de Protocolo (TCP em destaque), Porta e DNS
# - Regras de firewall ajustadas para porta/protocolo escolhidos
# - Detecção do serviço (openvpn@server vs openvpn-server@server)
# - Pequenas correções de robustez e validações
# =================================================================

# --- Variáveis de Cor ---
readonly RED=$'\e[1;31m'
readonly GREEN=$'\e[1;32m'
readonly YELLOW=$'\e[1;33m'
readonly BLUE=$'\e[1;34m'
readonly CYAN=$'\e[1;36m'
readonly WHITE=$'\e[1;37m'
readonly SCOLOR=$'\e[0m'

# --- Variáveis Globais ---
OS=""
GROUPNAME=""
OVPN_SVC_NAME=""
ENDPOINT=""
PROTOCOL=""
PORT=""
DNS1=""
DNS2=""

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
    local timeout=900  # 15min timeout em segundos (instalações podem demorar)

    # Garante restaurar o cursor em qualquer saída
    trap "tput cnorm" EXIT

    eval "$cmd" &  # outputs mantidos para o usuário acompanhar
    local pid=$!

    tput civis
    echo -ne "${YELLOW}Aguarde... [${SCOLOR}"

    local start_time
    start_time=$(date +%s)
    while ps -p "$pid" > /dev/null 2>&1; do
        local current_time
        current_time=$(date +%s)
        if [[ $((current_time - start_time)) -gt $timeout ]]; then
            kill "$pid" 2>/dev/null
            tput cnorm
            trap - EXIT
            die "Timeout na execução: '$cmd' demorou mais de $(($timeout/60))min. Verifique rede ou mirrors."
        fi
        i=$(( (i + 1) % 4 ))
        echo -ne "${CYAN}${spinner:$i:1}${SCOLOR}"
        sleep 0.2
        echo -ne "\b"
    done

    echo -e "${YELLOW}]${SCOLOR} - ${GREEN}Concluído!${SCOLOR}"
    tput cnorm
    trap - EXIT
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

# --- Detecção de Sistema Operacional ---
detect_os() {
    [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
    # shellcheck disable=SC1091
    source /etc/os-release
    OS_ID="$ID"
    case "$OS_ID" in
        ubuntu|debian) OS="debian"; GROUPNAME="nogroup" ;;
        centos|fedora|rhel) OS="centos"; GROUPNAME="nobody" ;;
        *) die "Sistema operacional '$OS_ID' não suportado." ;;
    esac
}

# --- Dependências ---
check_dependencies() {
    local missing=()
    local packages=("openvpn" "easy-rsa" "iptables" "lsof" "curl" "wget" "openssl")
    local checks=("command -v openvpn" "[ -d /usr/share/easy-rsa ] || [ -d /usr/lib/easy-rsa ] || [ -d /usr/lib64/easy-rsa ]" "command -v iptables" "command -v lsof" "command -v curl" "command -v wget" "command -v openssl")

    if [[ "$OS" == "debian" ]]; then
        packages+=("iptables-persistent" "iproute2")
        checks+=("command -v iptables-save" "command -v ss")
    else
        packages+=("iproute")
        checks+=("command -v ss")
        # Para CentOS/RHEL será útil para firewall
        packages+=("firewalld")
        checks+=("command -v firewall-cmd")
    fi

    for i in "${!packages[@]}"; do
        if ! eval "${checks[$i]}" >/dev/null 2>&1; then
            missing+=("${packages[$i]}")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "${YELLOW}Dependências em falta: ${missing[*]}${SCOLOR}"
        echo -ne "${WHITE}Deseja instalá-las automaticamente? [s/N]: ${SCOLOR}"
        read -r install_choice
        if [[ "$install_choice" =~ ^[sS]$ ]]; then
            echo -e "${CYAN}Instalando dependências faltantes... (outputs visíveis para monitorar)${SCOLOR}"
            if [[ "$OS" == "debian" ]]; then
                fun_bar "apt update -qq && DEBIAN_FRONTEND=noninteractive apt install -y -qq ${missing[*]}"
            elif [[ "$OS" == "centos" ]]; then
                if ! yum list installed epel-release >/dev/null 2>&1; then
                    fun_bar "yum install -y epel-release"
                fi
                fun_bar "yum install -y ${missing[*]}"
                # Em alguns casos firewalld pode estar desabilitado
                systemctl enable firewalld >/dev/null 2>&1 || true
            fi

            local still_missing=()
            for i in "${!packages[@]}"; do
                if ! eval "${checks[$i]}" >/dev/null 2>&1; then
                    still_missing+=("${packages[$i]}")
                fi
            done
            [[ ${#still_missing[@]} -gt 0 ]] && die "Falha ao instalar: ${still_missing[*]}."
            success "Dependências instaladas com sucesso!"
        else
            die "Instalação das dependências é necessária para prosseguir."
        fi
    else
        echo -e "${GREEN}Todas as dependências estão presentes.${SCOLOR}"
    fi

    local ovpn_version
    ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    # Comparação simples; serve para avisar
    if [[ "${ovpn_version%%.*}" -lt 2 ]] || { [[ "${ovpn_version%%.*}" -eq 2 ]] && [[ "${ovpn_version#2.}" < "5" ]]; }; then
        warn "Versão do OpenVPN ($ovpn_version) é antiga. Recomendo 2.5+ para melhor compatibilidade."
    fi
}

# --- Auxiliares de Serviço e Configuração ---
get_server_conf_path() {
    if [[ -f /etc/openvpn/server/server.conf ]]; then
        echo "/etc/openvpn/server/server.conf"
    else
        echo "/etc/openvpn/server.conf"
    fi
}

detect_and_setup_service_name() {
    # Ajusta o nome do serviço e local do arquivo de configuração para compatibilidade
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl list-unit-files | grep -q '^openvpn-server@\.service'; then
            # Garantir que o arquivo exista na pasta "server/"
            mkdir -p /etc/openvpn/server
            if [[ -f /etc/openvpn/server.conf ]]; then
                cp -f /etc/openvpn/server.conf /etc/openvpn/server/server.conf
            fi
            OVPN_SVC_NAME="openvpn-server@server"
        else
            OVPN_SVC_NAME="openvpn@server"
        fi
    else
        OVPN_SVC_NAME="openvpn@server"
    fi
}

service_active() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl is-active --quiet "$OVPN_SVC_NAME"
    else
        service "$OVPN_SVC_NAME" status >/dev/null 2>&1
    fi
}
service_enable_start() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable "$OVPN_SVC_NAME" || die "Falha ao habilitar o serviço ($OVPN_SVC_NAME)."
        systemctl start "$OVPN_SVC_NAME" || die "Falha ao iniciar o serviço ($OVPN_SVC_NAME). Use 'journalctl -xeu $OVPN_SVC_NAME'."
    else
        service "$OVPN_SVC_NAME" start || die "Falha ao iniciar o serviço sem systemd."
    fi
}
service_restart() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl restart "$OVPN_SVC_NAME" || die "Falha ao reiniciar serviço ($OVPN_SVC_NAME)."
    else
        service "$OVPN_SVC_NAME" restart || die "Falha ao reiniciar serviço sem systemd."
    fi
}
service_stop_disable() {
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop "$OVPN_SVC_NAME" 2>/dev/null || true
        systemctl disable "$OVPN_SVC_NAME" 2>/dev/null || true
    else
        service "$OVPN_SVC_NAME" stop 2>/dev/null || true
    fi
}

# --- Escolhas Interativas: Protocolo, Porta, DNS e Endpoint ---
detect_public_ip() {
    local ip=""
    ip=$(curl -4s https://ifconfig.me 2>/dev/null) || true
    [[ -z "$ip" ]] && ip=$(wget -4qO- "http://whatismyip.akamai.com/" 2>/dev/null) || true
    [[ -z "$ip" ]] && ip=$(hostname -I | awk '{print $1}') || true
    echo "$ip"
}

is_port_in_use() {
    local proto="$1"  # tcp|udp
    local port="$2"
    # Tenta com ss e lsof
    if command -v ss >/dev/null 2>&1; then
        if [[ "$proto" == "tcp" ]]; then
            ss -lnt "( sport = :$port )" 2>/dev/null | awk 'NR>1{print}' | grep -q .
        else
            ss -lnu 2>/dev/null | awk '{print $5}' | grep -E "[:.]$port$" -q
        fi
        return $?
    fi
    if command -v lsof >/dev/null 2>&1; then
        if [[ "$proto" == "tcp" ]]; then
            lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
        else
            lsof -nP -iUDP:"$port" >/dev/null 2>&1
        fi
        return $?
    fi
    # Se não conseguir checar, assume livre
    return 1
}

prompt_server_settings() {
    clear
    echo -e "${BLUE}--- Configuração do Servidor OpenVPN ---${SCOLOR}"

    # Protocolo (TCP em destaque e padrão)
    echo -e "${WHITE}Selecione o protocolo:${SCOLOR}"
    echo -e "  ${YELLOW}1)${SCOLOR} TCP (recomendado) [padrão]"
    echo -e "  ${YELLOW}2)${SCOLOR} UDP"
    echo -ne "${WHITE}Opção [1-2]: ${SCOLOR}"
    read -r proto_choice
    case "$proto_choice" in
        2) PROTOCOL="udp" ;;
        *) PROTOCOL="tcp" ;;
    esac
    success "Protocolo selecionado: $PROTOCOL"

    # Porta (validação + sugestão por protocolo)
    local default_port
    if [[ "$PROTOCOL" == "tcp" ]]; then
        default_port="443"
    else
        default_port="1194"
    fi

    while true; do
        echo -ne "${WHITE}Porta para o OpenVPN [padrão: ${default_port}]: ${SCOLOR}"
        read -r PORT
        [[ -z "$PORT" ]] && PORT="$default_port"
        if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
            warn "Porta inválida. Informe um número entre 1 e 65535."
            continue
        fi
        if is_port_in_use "$PROTOCOL" "$PORT"; then
            warn "A porta ${PORT}/${PROTOCOL} parece estar em uso."
            echo -ne "${WHITE}Deseja informar outra porta? [S/n]: ${SCOLOR}"
            read -r retry
            if [[ "$retry" =~ ^[Nn]$ ]]; then
                warn "Prosseguindo mesmo assim. Conflitos podem impedir o funcionamento."
                break
            fi
            continue
        fi
        break
    done
    success "Porta selecionada: ${PORT}/${PROTOCOL}"

    # DNS
    echo -e "${WHITE}Selecione o DNS a ser empurrado aos clientes:${SCOLOR}"
    echo -e "  ${YELLOW}1)${SCOLOR} Cloudflare (1.1.1.1, 1.0.0.1) [padrão]"
    echo -e "  ${YELLOW}2)${SCOLOR} Google (8.8.8.8, 8.8.4.4)"
    echo -e "  ${YELLOW}3)${SCOLOR} OpenDNS (208.67.222.222, 208.67.220.220)"
    echo -e "  ${YELLOW}4)${SCOLOR} AdGuard (94.140.14.14, 94.140.15.15)"
    echo -e "  ${YELLOW}5)${SCOLOR} Quad9 (9.9.9.9, 149.112.112.112)"
    echo -e "  ${YELLOW}6)${SCOLOR} Personalizado"
    echo -ne "${WHITE}Opção [1-6]: ${SCOLOR}"
    read -r dns_choice
    case "$dns_choice" in
        2) DNS1="8.8.8.8"; DNS2="8.8.4.4" ;;
        3) DNS1="208.67.222.222"; DNS2="208.67.220.220" ;;
        4) DNS1="94.140.14.14"; DNS2="94.140.15.15" ;;
        5) DNS1="9.9.9.9"; DNS2="149.112.112.112" ;;
        6)
            echo -ne "${WHITE}Informe o DNS primário: ${SCOLOR}"
            read -r DNS1
            echo -ne "${WHITE}Informe o DNS secundário (ou deixe em branco): ${SCOLOR}"
            read -r DNS2
            if [[ -z "$DNS1" ]]; then
                warn "DNS inválido. Usando Cloudflare por padrão."
                DNS1="1.1.1.1"; DNS2="1.0.0.1"
            fi
            ;;
        *) DNS1="1.1.1.1"; DNS2="1.0.0.1" ;;
    esac
    success "DNS selecionado: ${DNS1}${DNS2:+, $DNS2}"

    # Endpoint público (IP ou domínio)
    local detected_ip
    detected_ip=$(detect_public_ip)
    echo -ne "${WHITE}Endpoint público (IP ou domínio) [padrão: ${detected_ip}]: ${SCOLOR}"
    read -r ENDPOINT
    [[ -z "$ENDPOINT" ]] && ENDPOINT="$detected_ip"
    success "Endpoint definido: $ENDPOINT"
}

# --- Funções Principais do OpenVPN ---
install_openvpn() {
    clear
    echo -e "${BLUE}--- Instalador OpenVPN ---${SCOLOR}"

    prompt_server_settings

    local EASY_RSA_DIR="/etc/openvpn/easy-rsa"
    mkdir -p "$EASY_RSA_DIR" || die "Falha ao criar diretório $EASY_RSA_DIR."
    cp -r /usr/share/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    cp -r /usr/lib/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    cp -r /usr/lib64/easy-rsa/* "$EASY_RSA_DIR/" 2>/dev/null || \
    die "EasyRSA não encontrado."
    chmod +x "$EASY_RSA_DIR/easyrsa" || die "Falha ao ajustar permissões do EasyRSA."
    cd "$EASY_RSA_DIR" || die "Não foi possível acessar $EASY_RSA_DIR."

    echo -e "${CYAN}A configurar EasyRSA...${SCOLOR}"
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
    detect_and_setup_service_name
    configure_firewall

    echo -e "${CYAN}A iniciar o serviço OpenVPN...${SCOLOR}"
    service_enable_start

    success "OpenVPN instalado e iniciado com sucesso!"

    echo -e "${CYAN}A criar o primeiro cliente...${SCOLOR}"
    create_client "cliente1"

    echo -e "\n${CYAN}Pressione ENTER para voltar ao menu...${SCOLOR}"
    read -r
}

configure_server() {
    echo -e "${CYAN}A configurar o servidor OpenVPN...${SCOLOR}"

    # Persistir endpoint para uso nos clientes
    echo "$ENDPOINT" > /etc/openvpn/endpoint 2>/dev/null || true

    mkdir -p /var/log/openvpn || die "Falha ao criar diretório de logs."
    chown nobody:"$GROUPNAME" /var/log/openvpn || die "Falha ao ajustar permissões de logs."

    local server_conf="/etc/openvpn/server.conf"
    cat > "$server_conf" << EOF
port $PORT
proto $PROTOCOL
dev tun
ca ca.crt
cert server.crt
key server.key
dh dh.pem
auth SHA512
tls-auth ta.key 0
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "block-outside-dns"
push "dhcp-option DNS $DNS1"
$( [[ -n "$DNS2" ]] && echo "push \"dhcp-option DNS $DNS2\"" )
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

    # explicit-exit-notify é útil apenas para UDP
    if [[ "$PROTOCOL" == "udp" ]]; then
        echo "explicit-exit-notify 1" >> "$server_conf"
    fi

    cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
    ./easyrsa gen-crl || die "Falha ao gerar CRL."
    cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao copiar CRL."
    chown root:root /etc/openvpn/crl.pem
    chmod 644 /etc/openvpn/crl.pem
}

configure_firewall() {
    echo -e "${CYAN}A configurar o firewall...${SCOLOR}"

    # Ativar IP forward de forma idempotente
    if grep -qE '^\s*net\.ipv4\.ip_forward=' /etc/sysctl.conf; then
        sed -i 's/^\s*net\.ipv4\.ip_forward=.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf
    else
        echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
    fi
    sysctl -w net.ipv4.ip_forward=1 >/dev/null || die "Falha ao ativar encaminhamento de IP."
    sysctl -p >/dev/null 2>&1 || true

    # Leitura segura de porta/protocolo do arquivo vigente
    local conf_path
    conf_path=$(get_server_conf_path)
    local fw_port fw_proto
    fw_port=$(grep -E '^port ' "$conf_path" | awk '{print $2}')
    fw_proto=$(grep -E '^proto ' "$conf_path" | awk '{print $2}')
    if [[ -z "$fw_port" || -z "$fw_proto" ]]; then
        fw_port="$PORT"
        fw_proto="$PROTOCOL"
    fi

    if [[ "$OS" = "debian" ]]; then
        local IFACE
        IFACE=$(ip -4 route ls | awk '/default/ {for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')
        [[ -z "$IFACE" ]] && die "Não foi possível determinar a interface de rede."

        # Regras idempotentes
        iptables -C INPUT -p "$fw_proto" --dport "$fw_port" -j ACCEPT 2>/dev/null || iptables -I INPUT -p "$fw_proto" --dport "$fw_port" -j ACCEPT
        iptables -C INPUT -i tun+ -j ACCEPT 2>/dev/null || iptables -I INPUT -i tun+ -j ACCEPT
        iptables -C FORWARD -i tun+ -j ACCEPT 2>/dev/null || iptables -I FORWARD -i tun+ -j ACCEPT
        iptables -C FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -I FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
        iptables -t nat -C POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE

        mkdir -p /etc/iptables
        iptables-save > /etc/iptables/rules.v4 || warn "Falha ao salvar regras iptables em /etc/iptables/rules.v4."
        if command -v netfilter-persistent >/dev/null 2>&1; then
            netfilter-persistent save || warn "Falha ao persistir regras (verifique iptables-persistent)."
        fi
    elif [[ "$OS" = "centos" ]]; then
        systemctl start firewalld || die "Falha ao iniciar firewalld."
        systemctl enable firewalld || die "Falha ao habilitar firewalld."
        firewall-cmd --add-port="${fw_port}/${fw_proto}" --permanent || die "Falha ao liberar porta no firewalld."
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
    if [[ -f "pki/issued/${CLIENT_NAME}.crt" ]]; then
        warn "Cliente '$CLIENT_NAME' já existe."
        return
    fi

    echo -e "${CYAN}A gerar certificado para '$CLIENT_NAME'...${SCOLOR}"
    echo "yes" | ./easyrsa build-client-full "$CLIENT_NAME" nopass || die "Falha ao gerar certificado do cliente."

    local conf_path
    conf_path=$(get_server_conf_path)
    local PROTOCOL_C PORT_C
    PROTOCOL_C=$(grep -E '^proto ' "$conf_path" | awk '{print $2}')
    PORT_C=$(grep -E '^port ' "$conf_path" | awk '{print $2}')

    local ENDPOINT_C
    if [[ -f /etc/openvpn/endpoint ]]; then
        ENDPOINT_C=$(cat /etc/openvpn/endpoint 2>/dev/null)
    fi
    if [[ -z "$ENDPOINT_C" ]]; then
        ENDPOINT_C=$(detect_public_ip)
    fi

    local OVPN_DIR=~/ovpn-clients
    mkdir -p "$OVPN_DIR" || die "Falha ao criar diretório $OVPN_DIR."

    cat > "${OVPN_DIR}/${CLIENT_NAME}.ovpn" << EOF
client
dev tun
proto ${PROTOCOL_C}
remote ${ENDPOINT_C} ${PORT_C}
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
$(awk 'BEGIN{p=0} /BEGIN CERTIFICATE/{p=1} p; /END CERTIFICATE/{p=0}' "/etc/openvpn/easy-rsa/pki/issued/${CLIENT_NAME}.crt")
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

    echo -ne "${YELLOW}Tem certeza que deseja revogar '$CLIENT_TO_REVOKE'? [s/N]: ${SCOLOR}"
    read -r confirmation

    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        echo -e "${CYAN}A revogar o cliente...${SCOLOR}"
        echo "yes" | ./easyrsa revoke "$CLIENT_TO_REVOKE" || die "Falha ao revogar cliente."
        ./easyrsa gen-crl || die "Falha ao gerar CRL."
        cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao atualizar CRL."
        detect_and_setup_service_name
        service_restart
        rm -f ~/ovpn-clients/"$CLIENT_TO_REVOKE".ovpn
        success "Cliente '$CLIENT_TO_REVOKE' revogado."
    else
        warn "Operação cancelada."
    fi
}

uninstall_openvpn() {
    echo -ne "${RED}Tem CERTEZA que deseja remover o OpenVPN? [s/N]: ${SCOLOR}"
    read -r confirmation

    if [[ "$confirmation" =~ ^[sS]$ ]]; then
        echo -e "${RED}A remover o OpenVPN...${SCOLOR}"

        detect_and_setup_service_name
        service_stop_disable

        # Remover regras de firewall associadas
        local conf_path
        conf_path=$(get_server_conf_path)
        local fw_port fw_proto
        fw_port=$(grep -E '^port ' "$conf_path" | awk '{print $2}')
        fw_proto=$(grep -E '^proto ' "$conf_path" | awk '{print $2}')
        if [[ "$OS" = "debian" ]]; then
            local IFACE
            IFACE=$(ip -4 route ls | awk '/default/ {for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')
            # Tenta remover, ignorando erros caso não existam
            iptables -D INPUT -p "$fw_proto" --dport "$fw_port" -j ACCEPT 2>/dev/null || true
            iptables -D INPUT -i tun+ -j ACCEPT 2>/dev/null || true
            iptables -D FORWARD -i tun+ -j ACCEPT 2>/dev/null || true
            iptables -D FORWARD -i "$IFACE" -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
            iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o "$IFACE" -j MASQUERADE 2>/dev/null || true
            mkdir -p /etc/iptables
            iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
            if command -v netfilter-persistent >/dev/null 2>&1; then
                netfilter-persistent save 2>/dev/null || true
            fi
        elif [[ "$OS" = "centos" ]]; then
            firewall-cmd --remove-port="${fw_port}/${fw_proto}" --permanent 2>/dev/null || true
            firewall-cmd --remove-masquerade --permanent 2>/dev/null || true
            firewall-cmd --reload 2>/dev/null || true
        fi

        if [[ "$OS" = "debian" ]]; then
            fun_bar "apt remove --purge -y openvpn easy-rsa iptables iptables-persistent lsof && apt autoremove -y"
        elif [[ "$OS" = "centos" ]]; then
            fun_bar "yum remove -y openvpn easy-rsa firewalld lsof"
        fi

        rm -rf /etc/openvpn ~/ovpn-clients
        success "OpenVPN removido com sucesso."
    else
        warn "Remoção cancelada."
    fi
}

# --- Menus de Gestão ---
is_installed_and_active() {
    detect_and_setup_service_name
    service_active
}

main_menu() {
    while true; do
        clear
        echo -e "${BLUE}--- OpenVPN Installer & Manager ---${SCOLOR}"
        echo -e "${CYAN}Versão Revisada (melhorias em protocolo/porta/DNS e firewall)${SCOLOR}\n"

        if is_installed_and_active; then
            local conf_path port proto
            conf_path=$(get_server_conf_path)
            port=$(grep -E '^port ' "$conf_path" | awk '{print $2}')
            proto=$(grep -E '^proto ' "$conf_path" | awk '{print $2}')
            echo -e "${GREEN}STATUS: Ativo${SCOLOR} | ${WHITE}Porta: $port ($proto)${SCOLOR}\n"
            echo -e "${YELLOW}1)${SCOLOR} Criar um novo cliente"
            echo -e "${YELLOW}2)${SCOLOR} Revogar um cliente existente"
            echo -e "${YELLOW}3)${SCOLOR} Desinstalar o OpenVPN"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        else
            echo -e "${RED}STATUS: Não Instalado ou Inativo${SCOLOR}\n"
            echo -e "${YELLOW}1)${SCOLOR} Instalar OpenVPN"
            echo -e "${YELLOW}0)${SCOLOR} Sair"
        fi

        echo -ne "\n${WHITE}Escolha uma opção: ${SCOLOR}"
        read -r choice

        if is_installed_and_active; then
            case "$choice" in
                1) create_client ;;
                2) revoke_client ;;
                3) uninstall_openvpn; main_menu ;;
                0) exit 0 ;;
                *) warn "Opção inválida." ;;
            esac
        else
            case "$choice" in
                1) install_openvpn ;;
                0) exit 0 ;;
                *) warn "Opção inválida." ;;
            esac
        fi
        [[ -n "$choice" && "$choice" != "0" ]] && echo -e "\n${CYAN}Pressione ENTER para continuar...${SCOLOR}" && read -r
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
main
