#!/bin/bash

=================================================================
OpenVPN Installer & Manager
Baseado no script original do SSH-PRO @TMYCOMNECTVPN
Revisado para funcionar com padrões: TCP, porta 1194, DNS Google
- Corrige incompatibilidade entre openvpn@server e openvpn-server@server
- Usa caminhos absolutos no server.conf (evita quebra quando em /etc/openvpn/server/)
- Regras de firewall idempotentes para 1194/tcp
- Instala e inicia sem prompts, usando defaults solicitados
=================================================================
--- Variáveis de Cor ---
readonly RED=$'\e[1;31m' readonly GREEN=$'\e[1;32m' readonly YELLOW=$'\e[1;33m' readonly BLUE=$'\e[1;34m' readonly CYAN=$'\e[1;36m' readonly WHITE=$'\e[1;37m' readonly SCOLOR=$'\e[0m'

--- Variáveis Globais / Defaults ---
OS="" GROUPNAME="" OVPN_SVC_NAME="" ENDPOINT="" PROTOCOL="tcp" PORT="1194" DNS1="8.8.8.8" DNS2="8.8.4.4"

--- Funções de Utilidade ---
die() { echo -e "{RED}[ERRO] $1{SCOLOR}" >&2 exit "${2:-1}" } warn() { echo -e "{YELLOW}[AVISO] $1{SCOLOR}" } success() { echo -e "{GREEN}[SUCESSO] $1{SCOLOR}" } info() { echo -e "{CYAN}[INFO] $1{SCOLOR}" }

fun_bar() { local cmd="$1" local spinner="/-\|" local i=0 local timeout=900 # até 15 min (mirrors lentos)

trap "tput cnorm" EXIT
eval "$cmd" &
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

--- Verificações Iniciais ---
check_root() { [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT." } check_bash() { readlink /proc/$$/exe | grep -q "bash" || die "Execute este script com bash, não com sh." } check_tun() { [[ ! -e /dev/net/tun ]] && die "O dispositivo TUN/TAP não está disponível. Ative-o com 'modprobe tun' ou verifique o kernel." }

--- Detecção de Sistema Operacional ---
detect_os() { [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional." # shellcheck disable=SC1091 source /etc/os-release OS_ID="$ID" case "$OS_ID" in ubuntu|debian) OS="debian"; GROUPNAME="nogroup" ;; centos|fedora|rhel) OS="centos"; GROUPNAME="nobody" ;; *) die "Sistema operacional '$OS_ID' não suportado." ;; esac }

--- Dependências ---
check_dependencies() { local missing=() local packages=("openvpn" "easy-rsa" "iptables" "lsof" "curl" "wget" "openssl") local checks=("command -v openvpn" "[ -d /usr/share/easy-rsa ] || [ -d /usr/lib/easy-rsa ] || [ -d /usr/lib64/easy-rsa ]" "command -v iptables" "command -v lsof" "command -v curl" "command -v wget" "command -v openssl")

if [[ "$OS" == "debian" ]]; then
    packages+=("iptables-persistent" "iproute2")
    checks+=("command -v iptables-save" "command -v ss")
else
    packages+=("iproute" "firewalld")
    checks+=("command -v ss" "command -v firewall-cmd")
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
        echo -e "${CYAN}Instalando dependências faltantes...${SCOLOR}"
        if [[ "$OS" == "debian" ]]; then
            fun_bar "apt update -qq && DEBIAN_FRONTEND=noninteractive apt install -y -qq ${missing[*]}"
        elif [[ "$OS" == "centos" ]]; then
            if ! yum list installed epel-release >/dev/null 2>&1; then
                fun_bar "yum install -y epel-release"
            fi
            fun_bar "yum install -y ${missing[*]}"
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
if [[ "${ovpn_version%%.*}" -lt 2 ]] || { [[ "${ovpn_version%%.*}" -eq 2 ]] && [[ "${ovpn_version#2.}" < "5" ]]; }; then
    warn "Versão do OpenVPN ($ovpn_version) é antiga. Recomendo 2.5+ para compatibilidade."
fi
}

--- Auxiliares de Serviço e Configuração ---
get_server_conf_path() { if [[ -f /etc/openvpn/server/server.conf ]]; then echo "/etc/openvpn/server/server.conf" else echo "/etc/openvpn/server.conf" fi }

detect_and_setup_service_name() { if command -v systemctl >/dev/null 2>&1; then if systemctl list-unit-files | grep -q '^openvpn-server@.service'; then OVPN_SVC_NAME="openvpn-server@server" else OVPN_SVC_NAME="openvpn@server" fi else OVPN_SVC_NAME="openvpn@server" fi }

service_active() { if command -v systemctl >/dev/null 2>&1; then systemctl is-active --quiet "$OVPN_SVC_NAME" else service "$OVPN_SVC_NAME" status >/dev/null 2>&1 fi } service_enable_start() { if command -v systemctl >/dev/null 2>&1; then systemctl enable "
O
V
P
N
S
V
C
N
A
M
E
"
∣
∣
d
i
e
"
F
a
l
h
a
a
o
h
a
b
i
l
i
t
a
r
o
s
e
r
v
i
c
\c
o
(
OVPN 
S
​
 VC 
N
​
 AME"∣∣die"Falhaaohabilitaroservi 
c
\c
​
 o(OVPN_SVC_NAME)." systemctl start "
O
V
P
N
S
V
C
N
A
M
E
"
∣
∣
d
i
e
"
F
a
l
h
a
a
o
i
n
i
c
i
a
r
o
s
e
r
v
i
c
\c
o
(
OVPN 
S
​
 VC 
N
​
 AME"∣∣die"Falhaaoiniciaroservi 
c
\c
​
 o(OVPN_SVC_NAME). Use 'journalctl -xeu $OVPN_SVC_NAME'." else service "$OVPN_SVC_NAME" start || die "Falha ao iniciar o serviço sem systemd." fi } service_restart() { if command -v systemctl >/dev/null 2>&1; then systemctl restart "
O
V
P
N
S
V
C
N
A
M
E
"
∣
∣
d
i
e
"
F
a
l
h
a
a
o
r
e
i
n
i
c
i
a
r
s
e
r
v
i
c
\c
o
(
OVPN 
S
​
 VC 
N
​
 AME"∣∣die"Falhaaoreiniciarservi 
c
\c
​
 o(OVPN_SVC_NAME)." else service "$OVPN_SVC_NAME" restart || die "Falha ao reiniciar serviço sem systemd." fi } service_stop_disable() { if command -v systemctl >/dev/null 2>&1; then systemctl stop "$OVPN_SVC_NAME" 2>/dev/null || true systemctl disable "$OVPN_SVC_NAME" 2>/dev/null || true else service "$OVPN_SVC_NAME" stop 2>/dev/null || true fi }

--- Redes e auxiliares ---
detect_public_ip() { local ip="" ip=$(curl -4s https://ifconfig.me 2>/dev/null) || true [[ -z "ip" ]] && ip=(wget -4qO- "http://whatismyip.akamai.com/" 2>/dev/null) || true [[ -z "ip" ]] && ip=(curl -4s https://ipv4.icanhazip.com 2>/dev/null) || true [[ -z "ip" ]] && ip=(hostname -I | awk '{print $1}') || true echo "$ip" }

--- Funções Principais do OpenVPN ---
write_server_conf() { local path="$1" cat > "$path" << EOF port $PORT proto $PROTOCOL dev tun ca /etc/openvpn/ca.crt cert /etc/openvpn/server.crt key /etc/openvpn/server.key dh /etc/openvpn/dh.pem auth SHA512 tls-version-min 1.2 tls-auth /etc/openvpn/ta.key 0 topology subnet server 10.8.0.0 255.255.255.0 ifconfig-pool-persist /etc/openvpn/ipp.txt push "redirect-gateway def1 bypass-dhcp" push "dhcp-option DNS $DNS1" push "dhcp-option DNS $DNS2" keepalive 10 120 cipher AES-256-GCM ncp-ciphers AES-256-GCM:AES-128-GCM user nobody group $GROUPNAME persist-key persist-tun status /var/log/openvpn/openvpn-status.log log-append /var/log/openvpn/openvpn.log verb 3 crl-verify /etc/openvpn/crl.pem EOF }

configure_server() { echo -e "
C
Y
A
N
A
c
o
n
f
i
g
u
r
a
r
o
s
e
r
v
i
d
o
r
O
p
e
n
V
P
N
.
.
.
CYANAconfiguraroservidorOpenVPN...{SCOLOR}"

ENDPOINT=$(detect_public_ip)
[[ -z "$ENDPOINT" ]] && die "Não foi possível determinar o IP público."

echo "$ENDPOINT" > /etc/openvpn/endpoint 2>/dev/null || true

mkdir -p /var/log/openvpn || die "Falha ao criar diretório de logs."
chown nobody:"$GROUPNAME" /var/log/openvpn || die "Falha ao ajustar permissões de logs."

# Cria configuração para ambos os templates de serviço
mkdir -p /etc/openvpn/server
write_server_conf "/etc/openvpn/server.conf"
write_server_conf "/etc/openvpn/server/server.conf"

# Gera CRL
cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."
./easyrsa gen-crl || die "Falha ao gerar CRL."
cp pki/crl.pem /etc/openvpn/crl.pem || die "Falha ao copiar CRL."
chown root:root /etc/openvpn/crl.pem
chmod 644 /etc/openvpn/crl.pem
}

configure_firewall() { echo -e "
C
Y
A
N
A
c
o
n
f
i
g
u
r
a
r
o
f
i
r
e
w
a
l
l
.
.
.
CYANAconfigurarofirewall...{SCOLOR}"

# Ativar IP forward
if grep -qE '^\s*net\.ipv4\.ip_forward=' /etc/sysctl.conf; then
    sed -i 's/^\s*net\.ipv4\.ip_forward=.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf
else
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
fi
sysctl -w net.ipv4.ip_forward=1 >/dev/null || die "Falha ao ativar encaminhamento de IP."
sysctl -p >/dev/null 2>&1 || true

local fw_port="$PORT"
local fw_proto="$PROTOCOL"

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
    iptables-save > /etc/iptables/rules.v4 || warn "Falha ao salvar regras iptables."
    if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save || warn "Falha ao persistir regras (iptables-persistent)."
    fi
elif [[ "$OS" = "centos" ]]; then
    systemctl start firewalld || die "Falha ao iniciar firewalld."
    systemctl enable firewalld || die "Falha ao habilitar firewalld."
    firewall-cmd --add-port="${fw_port}/${fw_proto}" --permanent || die "Falha ao liberar porta no firewalld."
    firewall-cmd --add-masquerade --permanent || die "Falha ao adicionar masquerade."
    firewall-cmd --reload || die "Falha ao recarregar firewalld."
fi
}

install_openvpn() { clear echo -e "
B
L
U
E
−
−
−
I
n
s
t
a
l
a
d
o
r
O
p
e
n
V
P
N
(
P
a
d
r
o
~
e
s
:
T
C
P
/
1194
,
D
N
S
G
o
o
g
l
e
)
−
−
−
BLUE−−−InstaladorOpenVPN(Padr 
o
~
 es:TCP/1194,DNSGoogle)−−−{SCOLOR}"

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
openvpn --genkey --secret pki/ta.key || die "Falha ao gerar chave TA."
[[ ! -s pki/ta.key ]] && die "Arquivo ta.key gerado, mas vazio ou inexistente."

cp pki/ca.crt pki/issued/server.crt pki/private/server.key pki/dh.pem pki/ta.key /etc/openvpn/ || die "Falha ao copiar arquivos."
chown root:root /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar propriedade."
chmod 600 /etc/openvpn/*.{key,crt,pem} || die "Falha ao ajustar permissões."
[[ ! -s /etc/openvpn/ta.key ]] && die "ta.key copiado, mas vazio."

configure_server
detect_and_setup_service_name
configure_firewall

echo -e "${CYAN}A iniciar o serviço OpenVPN...${SCOLOR}"
service_enable_start

success "OpenVPN instalado e iniciado com sucesso!"

echo -e "${CYAN}A criar o primeiro cliente (cliente1)...${SCOLOR}"
create_client "cliente1"

echo -e "\n${CYAN}Pressione ENTER para voltar ao menu...${SCOLOR}"
read -r
}

create_client() { local CLIENT_NAME="$1"

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
client dev tun proto ${PROTOCOL_C} remote ${ENDPOINT_C} ${PORT_C} resolv-retry infinite nobind persist-key persist-tun remote-cert-tls server auth SHA512 cipher AES-256-GCM key-direction 1 verb 3 $(cat /etc/openvpn/easy-rsa/pki/ca.crt) 
(
a
w
k
′
B
E
G
I
N
p
=
0
/
B
E
G
I
N
C
E
R
T
I
F
I
C
A
T
E
/
p
=
1
p
;
/
E
N
D
C
E
R
T
I
F
I
C
A
T
E
/
p
=
0
′
"
/
e
t
c
/
o
p
e
n
v
p
n
/
e
a
s
y
−
r
s
a
/
p
k
i
/
i
s
s
u
e
d
/
(awk 
′
 BEGINp=0/BEGINCERTIFICATE/p=1p;/ENDCERTIFICATE/p=0 
′
 "/etc/openvpn/easy−rsa/pki/issued/{CLIENT_NAME}.crt") 
(
c
a
t
"
/
e
t
c
/
o
p
e
n
v
p
n
/
e
a
s
y
−
r
s
a
/
p
k
i
/
p
r
i
v
a
t
e
/
(cat"/etc/openvpn/easy−rsa/pki/private/{CLIENT_NAME}.key") $(cat /etc/openvpn/ta.key) EOF success "Configuração do cliente salva em: 
O
V
P
N
D
I
R
/
OVPN 
D
​
 IR/{CLIENT_NAME}.ovpn" }

revoke_client() { cd /etc/openvpn/easy-rsa/ || die "Diretório easy-rsa não encontrado."

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

local CLIENT_TO_REVOKE="${clients[$((choice - 1))])}"
CLIENT_TO_REVOKE="${clients[$((choice - 1))]}"

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

uninstall_openvpn() { echo -ne "${RED}Tem CERTEZA que deseja remover o OpenVPN? [s/N]: ${SCOLOR}" read -r confirmation

if [[ "$confirmation" =~ ^[sS]$ ]]; then
    echo -e "${RED}A remover o OpenVPN...${SCOLOR}"

    detect_and_setup_service_name
    service_stop_disable

    # Remover regras de firewall associadas
    local fw_port="$PORT" fw_proto="$PROTOCOL"
    if [[ "$OS" = "debian" ]]; then
        local IFACE
        IFACE=$(ip -4 route ls | awk '/default/ {for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')
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

    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^openvpn-server@\.service'; then
        rm -f /etc/openvpn/server/server.conf
    else
        rm -f /etc/openvpn/server.conf
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

--- Menus de Gestão ---
is_installed_and_active() { detect_and_setup_service_name service_active }

main_menu() { while true; do clear echo -e "{BLUE}--- OpenVPN Installer & Manager ---{SCOLOR}" echo -e "
C
Y
A
N
P
a
d
r
o
~
e
s
:
T
C
P
(
1194
)
,
D
N
S
G
o
o
g
l
e
CYANPadr 
o
~
 es:TCP(1194),DNSGoogle{SCOLOR}\n"

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
        echo -e "${YELLOW}1)${SCOLOR} Instalar OpenVPN (padrões automáticos)"
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

--- Ponto de Entrada ---
main() { clear check_root check_bash check_tun detect_os check_dependencies main_menu } main
