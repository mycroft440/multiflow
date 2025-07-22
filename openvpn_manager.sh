#!/bin/bash

# Cores para a saída do terminal
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m'

# Função para exibir barra de progresso
fun_bar() {
    local cmd1="$1"
    local cmd2="$2"
    (
        [[ -e $HOME/fim ]] && rm $HOME/fim
        ${cmd1} >/dev/null 2>&1
        ${cmd2} >/dev/null 2>&1
        touch $HOME/fim
    ) >/dev/null 2>&1 &
    tput civis
    echo -ne "${YELLOW}AGUARDE ${NC}- ${YELLOW}[${NC}"
    while true; do
        for ((i = 0; i < 18; i++)); do
            echo -ne "${RED}#${NC}"
            sleep 0.1s
        done
        [[ -e $HOME/fim ]] && rm $HOME/fim && break
        echo -e "${YELLOW}]${NC} "
        sleep 1s
        tput cuu1
        tput dl1
        echo -ne "${YELLOW}AGUARDE ${NC}- ${YELLOW}[${NC}"
    done
    echo -e "${YELLOW}]${NC} -${GREEN} OK !${NC}"
    tput cnorm
}

# Função para verificar portas em uso
verif_ptrs() {
    local porta="$1"
    if ss -tuln | grep -q ":$porta "; then
        echo -e "\n${RED}PORTA ${YELLOW}$porta ${RED}EM USO!${NC}"
        sleep 3
        return 1 # Indica que a porta está em uso
    fi
    return 0 # Indica que a porta está livre
}

# Função para gerar arquivo de configuração do cliente OpenVPN
newclient() {
    local client_name="$1"
    cp /etc/openvpn/client-common.txt ~/${client_name}.ovpn
    echo "<ca>" >>~/${client_name}.ovpn
    cat /etc/openvpn/easy-rsa/pki/ca.crt >>~/${client_name}.ovpn
    echo "</ca>" >>~/${client_name}.ovpn
    echo "<cert>" >>~/${client_name}.ovpn
    cat /etc/openvpn/easy-rsa/pki/issued/${client_name}.crt >>~/${client_name}.ovpn
    echo "</cert>" >>~/${client_name}.ovpn
    echo "<key>" >>~/${client_name}.ovpn
    cat /etc/openvpn/easy-rsa/pki/private/${client_name}.key >>~/${client_name}.ovpn
    echo "</key>" >>~/${client_name}.ovpn
    echo "<tls-auth>" >>~/${client_name}.ovpn
    cat /etc/openvpn/ta.key >>~/${client_name}.ovpn
    echo "</tls-auth>" >>~/${client_name}.ovpn
}

# Função principal para instalação e gerenciamento do OpenVPN
fun_openvpn() {
    if readlink /proc/$$/exe | grep -qs "dash"; then
        echo -e "${RED}Este script precisa ser executado com bash, não sh${NC}"
        exit 1
    fi
    [[ "$EUID" -ne 0 ]] && {
        clear
        echo -e "${RED}Execute como root${NC}"
        exit 2
    }
    [[ ! -e /dev/net/tun ]] && {
        echo -e "${RED}TUN TAP NAO DISPONIVEL${NC}"
        sleep 2
        exit 3
    }
    if grep -qs "CentOS release 5" "/etc/redhat-release"; then
        echo -e "${RED}O CentOS 5 é muito antigo e não é suportado${NC}"
        exit 4
    fi

    local OS
    local GROUPNAME
    local RCLOCAL_PATH="/etc/rc.local"

    if [[ -e /etc/debian_version ]]; then
        OS=debian
        GROUPNAME=nogroup
    elif [[ -e /etc/centos-release || -e /etc/redhat-release ]]; then
        OS=centos
        GROUPNAME=nobody
    else
        echo -e "${RED}SISTEMA NAO SUPORTADO${NC}"
        exit 5
    fi

    # Tenta obter o IP público de forma mais robusta
    local IP=$(curl -s ifconfig.me || wget -qO- ifconfig.me || curl -s checkip.amazonaws.com)
    if [[ -z "$IP" ]]; then
        IP=$(hostname -I | cut -d" " -f1)
    fi

    if systemctl is-active --quiet openvpn; then
        # Gerenciar OpenVPN existente
        while :; do
            clear
            local opnp=$(grep "^port " /etc/openvpn/server.conf | awk '{print $2}' | head -1)
            local ovpnweb="${RED}○ ${NC}"
            [[ -d /var/www/html/openvpn ]] && ovpnweb="${GREEN}◉ ${NC}"

            echo -e "\E[44;1;37m          GERENCIAR OPENVPN           \E[0m"
            echo ""
            echo -e "${YELLOW}PORTA${NC}: ${GREEN}$opnp${NC}"
            echo ""
            echo -e "${RED}[${YELLOW}1${RED}] ${NC}• ${YELLOW}ALTERAR PORTA${NC}"
            echo -e "${RED}[${YELLOW}2${RED}] ${NC}• ${YELLOW}REMOVER OPENVPN${NC}"
            echo -e "${RED}[${YELLOW}3${RED}] ${NC}• ${YELLOW}OVPN VIA LINK ${ovpnweb}${NC}"
            echo -e "${RED}[${YELLOW}4${RED}] ${NC}• ${YELLOW}MULTILOGIN OVPN ${mult}${NC}"
            echo -e "${RED}[${YELLOW}5${RED}] ${NC}• ${YELLOW}ALTERAR HOST DNS${NC}"
            echo -e "${RED}[${YELLOW}0${RED}] ${NC}• ${YELLOW}VOLTAR${NC}"
            echo ""
            echo -ne "${GREEN}O QUE DESEJA FAZER ${YELLOW}?${RED}?${NC} "
            read -r option

            case $option in
            1)
                clear
                echo -e "\E[44;1;37m         ALTERAR PORTA OPENVPN         \E[0m"
                echo ""
                echo -e "${YELLOW}PORTA EM USO${NC}: ${GREEN}$opnp${NC}"
                echo ""
                echo -ne "${GREEN}QUAL PORTA DESEJA UTILIZAR ${YELLOW}?${NC} "
                read -r porta
                if [[ -z "$porta" ]]; then
                    echo -e "\n${RED}Porta inválida!${NC}"
                    sleep 3
                    continue
                fi
                if ! verif_ptrs "$porta"; then
                    echo ""
                    echo -e "${GREEN}ALTERANDO A PORTA OPENVPN!${NC}"
                    echo ""
                    fun_opn() {
                        sed -i "s/^port .*/port $porta/" /etc/openvpn/server.conf
                        sed -i "s/remote .* $opnp/remote $IP $porta/" /etc/openvpn/client-common.txt
                        systemctl restart openvpn@server || service openvpn restart
                    }
                    fun_bar 'fun_opn'
                    echo ""
                    echo -e "${GREEN}PORTA ALTERADA COM SUCESSO!${NC}"
                    sleep 2
                fi
                ;;
            2)
                echo ""
                echo -ne "${GREEN}DESEJA REMOVER O OPENVPN ${RED}? ${YELLOW}[s/n]:${NC} "
                read -r REMOVE
                if [[ "$REMOVE" = 's' ]]; then
                    rmv_open() {
                        local PORT=$(grep '^port ' /etc/openvpn/server.conf | cut -d " " -f 2)
                        local PROTOCOL=$(grep '^proto ' /etc/openvpn/server.conf | cut -d " " -f 2)
                        
                        # Remove iptables rules
                        iptables -D INPUT -p "$PROTOCOL" --dport "$PORT" -j ACCEPT 2>/dev/null
                        iptables -D FORWARD -s 10.8.0.0/24 -j ACCEPT 2>/dev/null
                        iptables -D FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null
                        iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -j SNAT --to "$IP" 2>/dev/null

                        # Remove rules from rc.local
                        sed -i "/iptables -I INPUT -p $PROTOCOL --dport $PORT -j ACCEPT/d" "$RCLOCAL_PATH"
                        sed -i "/iptables -I FORWARD -s 10.8.0.0\/24 -j ACCEPT/d" "$RCLOCAL_PATH"
                        sed -i "/iptables -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT/d" "$RCLOCAL_PATH"
                        sed -i "/iptables -t nat -A POSTROUTING -s 10.8.0.0\/24 -j SNAT --to $IP/d" "$RCLOCAL_PATH"

                        # Stop and disable OpenVPN service
                        systemctl stop openvpn@server 2>/dev/null || service openvpn stop 2>/dev/null
                        systemctl disable openvpn@server 2>/dev/null || chkconfig openvpn off 2>/dev/null

                        # Remove OpenVPN packages and files
                        if [[ "$OS" = "debian" ]]; then
                            apt-get remove --purge -y openvpn openvpn-blacklist easy-rsa
                            apt-get autoremove -y
                        else
                            yum remove -y openvpn easy-rsa
                        fi
                        rm -rf /etc/openvpn
                        rm -rf /usr/share/doc/openvpn*
                        rm -rf /usr/local/share/easy-rsa/
                        rm -rf /usr/local/bin/easyrsa
                    }
                    echo ""
                    echo -e "${GREEN}REMOVENDO O OPENVPN!${NC}"
                    echo ""
                    fun_bar 'rmv_open'
                    echo ""
                    echo -e "${GREEN}OPENVPN REMOVIDO COM SUCESSO!${NC}"
                    sleep 2
                else
                    echo ""
                    echo -e "${RED}Retornando...${NC}"
                    sleep 2
                fi
                ;;
            3)
                if [[ -d /var/www/html/openvpn ]]; then
                    clear
                    fun_spcr() {
                        systemctl stop apache2 2>/dev/null || service apache2 stop 2>/dev/null
                        apt-get remove apache2 -y
                        apt-get autoremove -y
                        rm -rf /var/www/html/openvpn
                    }
                    function aguarde() {
                        helices() {
                            fun_spcr >/dev/null 2>&1 &
                            tput civis
                            while [ -d /proc/$! ]; do
                                for i in / - \\ \|; do
                                    sleep .1
                                    echo -ne "\e[1D$i"
                                done
                            done
                            tput cnorm
                        }
                        echo -ne "${RED}DESATIVANDO${GREEN}.${YELLOW}.${RED}. ${YELLOW}"
                        helices
                        echo -e "\e[1DOk"
                    }
                    aguarde
                    sleep 2
                else
                    clear
                    fun_apchon() {
                        apt-get install apache2 zip -y
                        sed -i "s/Listen 80/Listen 81/g" /etc/apache2/ports.conf
                        systemctl restart apache2 || service apache2 restart
                        [[ ! -d /var/www/html ]] && {
                            mkdir /var/www/html
                        }
                        [[ ! -d /var/www/html/openvpn ]] && {
                            mkdir /var/www/html/openvpn
                        }
                        touch /var/www/html/openvpn/index.html
                        chmod -R 755 /var/www
                        systemctl restart apache2 || service apache2 restart
                    }
                    function aguarde2() {
                        helices() {
                            fun_apchon >/dev/null 2>&1 &
                            tput civis
                            while [ -d /proc/$! ]; do
                                for i in / - \\ \|; do
                                    sleep .1
                                    echo -ne "\e[1D$i"
                                done
                            done
                            tput cnorm
                        }
                        echo -ne "${GREEN}ATIVANDO${GREEN}.${YELLOW}.${RED}. ${YELLOW}"
                        helices
                        echo -e "\e[1DOk"
                    }
                    aguarde2
                fi
                ;;
            4)
                if grep "duplicate-cn" /etc/openvpn/server.conf >/dev/null; then
                    clear
                    fun_multon() {
                        sed -i '/duplicate-cn/d' /etc/openvpn/server.conf
                        sleep 1.5s
                        systemctl restart openvpn@server || service openvpn restart
                        sleep 2
                    }
                    fun_spinmult() {
                        helices() {
                            fun_multon >/dev/null 2>&1 &
                            tput civis
                            while [ -d /proc/$! ]; do
                                for i in / - \\ \|; do
                                    sleep .1
                                    echo -ne "\e[1D$i"
                                done
                            done
                            tput cnorm
                        }
                        echo ""
                        echo -ne "${RED}BLOQUEANDO MULTILOGIN${GREEN}.${YELLOW}.${RED}. ${YELLOW}"
                        helices
                        echo -e "\e[1DOk"
                    }
                    fun_spinmult
                    sleep 1
                else
                    clear
                    fun_multoff() {
                        grep -v "^duplicate-cn" /etc/openvpn/server.conf >/tmp/tmpass && mv /tmp/tmpass /etc/openvpn/server.conf
                        echo "duplicate-cn" >>/etc/openvpn/server.conf
                        sleep 1.5s
                        systemctl restart openvpn@server || service openvpn restart
                    }
                    fun_spinmult2() {
                        helices() {
                            fun_multoff >/dev/null 2>&1 &
                            tput civis
                            while [ -d /proc/$! ]; do
                                for i in / - \\ \|; do
                                    sleep .1
                                    echo -ne "\e[1D$i"
                                done
                            done
                            tput cnorm
                        }
                        echo ""
                        echo -ne "${GREEN}PERMITINDO MULTILOGIN${GREEN}.${YELLOW}.${RED}. ${YELLOW}"
                        helices
                        echo -e "\e[1DOk"
                    }
                    fun_spinmult2
                    sleep 1
                fi
                ;;
            5)
                clear
                echo -e "\E[44;1;37m         ALTERAR HOST DNS           \E[0m"
                echo ""
                echo -e "${RED}[${YELLOW}1${RED}] ${NC}• ${YELLOW}ADICIONAR HOST DNS${NC}"
                echo -e "${RED}[${YELLOW}2${RED}] ${NC}• ${YELLOW}REMOVER HOST DNS${NC}"
                echo -e "${RED}[${YELLOW}3${RED}] ${NC}• ${YELLOW}EDITAR MANUALMENTE${NC}"
                echo -e "${RED}[${YELLOW}0${RED}] ${NC}• ${YELLOW}VOLTAR${NC}"
                echo ""
                echo -ne "${GREEN}O QUE DESEJA FAZER ${YELLOW}?${RED}?${NC} "
                read -r resp
                if [[ -z "$resp" ]]; then
                    echo ""
                    echo -e "${RED}Opção inválida!${NC}"
                    sleep 3
                    continue
                fi
                if [[ "$resp" = '1' ]]; then
                    clear
                    echo -e "\E[44;1;37m            Adicionar Host DNS            \E[0m"
                    echo ""
                    echo -e "${YELLOW}Lista dos hosts atuais${NC}: "
                    echo ""
                    local i=0
                    grep -w "127.0.0.1" /etc/hosts | grep -v "localhost" | cut -d" " -f2 | while read -r _host; do
                        i=$((i + 1))
                        oP+=$i
                        [[ $i == [1-9] ]] && oP+=" 0$i" && i=0$i
                        oP+=":$_host\n"
                        echo -e "${YELLOW}[${RED}$i${YELLOW}] ${NC}- ${GREEN}$_host${NC}"
                    done
                    echo ""
                    echo -ne "${YELLOW}Digite o host a ser adicionado${NC} : "
                    read -r host
                    if [[ -z $host ]]; then
                        echo ""
                        echo -e "\E[41;1;37m        Campo Vazio ou inválido !       \E[0m"
                        sleep 2
                        continue
                    fi
                    if [[ "$(grep -wc "$host" /etc/hosts)" -gt "0" ]]; then
                        echo -e "\E[41;1;37m    Esse host já está adicionado  !    \E[0m"
                        sleep 2
                        continue
                    fi
                    sed -i "3i\127.0.0.1 $host" /etc/hosts
                    echo ""
                    echo -e "\E[44;1;37m      Host adicionado com sucesso !      \E[0m"
                    sleep 2
                elif [[ "$resp" = '2' ]]; then
                    clear
                    echo -e "\E[44;1;37m            Remover Host DNS            \E[0m"
                    echo ""
                    echo -e "${YELLOW}Lista dos hosts atuais${NC}: "
                    echo ""
                    local i=0
                    local oP=""
                    grep -w "127.0.0.1" /etc/hosts | grep -v "localhost" | cut -d" " -f2 | while read -r _host; do
                        i=$((i + 1))
                        oP+=$i
                        [[ $i == [1-9] ]] && oP+=" 0$i" && i=0$i
                        oP+=":$_host\n"
                        echo -e "${YELLOW}[${RED}$i${YELLOW}] ${NC}- ${GREEN}$_host${NC}"
                    done
                    echo ""
                    echo -ne "${GREEN}Selecione o host a ser removido ${YELLOW}[${NC}1${RED}-${NC}$i${YELLOW}]${NC}: "
                    read -r option
                    if [[ -z $option ]]; then
                        echo ""
                        echo -e "\E[41;1;37m          Opção inválida  !        \E[0m"
                        sleep 2
                        continue
                    fi
                    local host_to_remove
                    host_to_remove=$(echo -e "$oP" | grep -E "\b$option\b" | cut -d: -f2)
                    local hst
                    hst=$(grep -v "127.0.0.1 $host_to_remove" /etc/hosts)
                    echo "$hst" >/etc/hosts
                    echo ""
                    echo -e "\E[41;1;37m      Host removido com sucesso !      \E[0m"
                    sleep 2
                elif [[ "$resp" = '3' ]]; then
                    echo -e "\n${GREEN}ALTERANDO ARQUIVO ${NC}/etc/hosts${NC}"
                    echo -e "\n${RED}ATENÇÃO!${NC}"
                    echo -e "\n${YELLOW}PARA SALVAR USE AS TECLAS ${GREEN}ctrl x y${NC}"
                    sleep 4
                    clear
                    nano /etc/hosts
                    echo -e "\n${GREEN}ALTERADO COM SUCESSO!${NC}"
                    sleep 3
                elif [[ "$resp" = '0' ]]; then
                    echo ""
                    echo -e "${RED}Retornando...${NC}"
                    sleep 2
                    break
                else
                    echo ""
                    echo -e "${RED}Opção inválida !${NC}"
                    sleep 2
                fi
                ;;
            0)
                break
                ;;
            *)
                echo ""
                echo -e "${RED}Opção inválida! Pressione qualquer tecla para continuar...${NC}"
                read -r -n 1
                ;;
            esac
        done
    else
        # Instalar OpenVPN
        clear
        echo -e "\E[44;1;37m              INSTALADOR OPENVPN               \E[0m"
        echo ""
        echo -e "${YELLOW}RESPONDA AS QUESTÕES PARA INICIAR A INSTALAÇÃO${NC}"
        echo ""
        echo -ne "${GREEN}PARA CONTINUAR CONFIRME SEU IP${NC}: "
        read -r -e -i "$IP" IP
        if [[ -z "$IP" ]]; then
            echo ""
            echo -e "${RED}IP inválido!${NC}"
            sleep 3
            return
        fi
        echo ""
        read -r -p "$(echo -e "${GREEN}QUAL PORTA DESEJA UTILIZAR? ${NC}")" -e -i 1194 porta
        if [[ -z "$porta" ]]; then
            echo ""
            echo -e "${RED}Porta inválida!${NC}"
            sleep 2
            return
        fi
        echo ""
        echo -e "${YELLOW}VERIFICANDO PORTA...${NC}"
        if ! verif_ptrs "$porta"; then
            echo ""
            echo -e "${RED}[${YELLOW}1${RED}] ${YELLOW}Sistema${NC}"
            echo -e "${RED}[${YELLOW}2${RED}] ${YELLOW}Google (${GREEN}Recomendado${YELLOW})${NC}"
            echo -e "${RED}[${YELLOW}3${RED}] ${YELLOW}OpenDNS${NC}"
            echo -e "${RED}[${YELLOW}4${RED}] ${YELLOW}Cloudflare${NC}"
            echo -e "${RED}[${YELLOW}5${RED}] ${YELLOW}Hurricane Electric${NC}"
            echo -e "${RED}[${YELLOW}6${RED}] ${YELLOW}Verisign${NC}"
            echo -e "${RED}[${YELLOW}7${RED}] ${YELLOW}DNS Performance${NC}"
            echo ""
            read -r -p "$(echo -e "${GREEN}QUAL DNS DESEJA UTILIZAR? ${NC}")" -e -i 2 DNS
            echo ""
            echo -e "${RED}[${YELLOW}1${RED}] ${YELLOW}UDP${NC}"
            echo -e "${RED}[${YELLOW}2${RED}] ${YELLOW}TCP (${GREEN}Recomendado${YELLOW})${NC}"
            echo ""
            read -r -p "$(echo -e "${GREEN}QUAL PROTOCOLO DESEJA UTILIZAR NO OPENVPN? ${NC}")" -e -i 2 resp_protocol
            local PROTOCOL
            if [[ "$resp_protocol" = '1' ]]; then
                PROTOCOL=udp
            elif [[ "$resp_protocol" = '2' ]]; then
                PROTOCOL=tcp
            else
                PROTOCOL=tcp
            fi
            echo ""
            # Instalar dependências de compilação
            if [[ "$OS" = 'debian' ]]; then
                echo -e "${GREEN}ATUALIZANDO O SISTEMA E INSTALANDO DEPENDÊNCIAS DE COMPILAÇÃO${NC}"
                fun_bar 'apt-get update -y && apt-get install -y build-essential libssl-dev liblzo2-dev libpam0g-dev pkg-config git wget curl unzip iproute2 net-tools'
            elif [[ "$OS" = 'centos' ]]; then
                echo -e "${GREEN}ATUALIZANDO O SISTEMA E INSTALANDO DEPENDÊNCIAS DE COMPILAÇÃO${NC}"
                fun_bar 'yum update -y && yum install -y epel-release && yum install -y gcc make autoconf automake openssl-devel lzo-devel pam-devel pkgconfig git wget curl unzip iproute2 net-tools'
            fi

            # Remover OpenVPN existente se houver
            if [[ "$OS" = 'debian' ]]; then
                apt-get remove --purge -y openvpn openvpn-blacklist easy-rsa
                apt-get autoremove -y
            elif [[ "$OS" = 'centos' ]]; then
                yum remove -y openvpn easy-rsa
            fi
            rm -rf /etc/openvpn
            rm -rf /usr/share/doc/openvpn*

            # Baixar e compilar OpenVPN do GitHub
            echo ""
            echo -e "${GREEN}BAIXANDO E COMPILANDO OPENVPN DO GITHUB ${RED}(${YELLOW}PODE DEMORAR!${RED})${NC}"
            fun_install_openvpn_from_source() {
                cd /tmp || exit
                git clone https://github.com/OpenVPN/openvpn.git
                cd openvpn || exit
                git checkout master # Sempre a versão mais recente do master
                autoreconf -ivf
                ./configure --prefix=/usr --sbindir=/usr/sbin --sysconfdir=/etc/openvpn --localstatedir=/var --enable-systemd --disable-plugin-auth-pam
                make -j"$(nproc)"
                make install
            }
            fun_bar 'fun_install_openvpn_from_source'

            # Adquirindo easy-rsa (versão mais recente do GitHub)
            echo ""
            echo -e "${GREEN}BAIXANDO EASY-RSA DO GITHUB${NC}"
            fun_get_easy_rsa() {
                rm -rf /etc/openvpn/easy-rsa/
                cd /tmp || exit
                git clone https://github.com/OpenVPN/easy-rsa.git
                mv easy-rsa/easyrsa3/ /etc/openvpn/easy-rsa/
                chown -R root:root /etc/openvpn/easy-rsa/
                chmod -R 700 /etc/openvpn/easy-rsa/
                cd /etc/openvpn/easy-rsa/ || exit
                ./easyrsa init-pki
                ./easyrsa --batch build-ca nopass
                ./easyrsa gen-dh
                ./easyrsa build-server-full server nopass
                ./easyrsa build-client-full SSHPLUS nopass
                ./easyrsa gen-crl
                cp pki/ca.crt pki/private/ca.key pki/dh.pem pki/issued/server.crt pki/private/server.key /etc/openvpn/easy-rsa/pki/crl.pem /etc/openvpn
                chown nobody:"$GROUPNAME" /etc/openvpn/crl.pem
                openvpn --genkey --secret /etc/openvpn/ta.key
            }
            fun_bar 'fun_get_easy_rsa'

            # Gerando server.conf com otimizações
            echo "port $porta
proto $PROTOCOL
dev tun
tun-mtu 1500
fragment 1300
sndbuf 0
rcvbuf 0
ca ca.crt
cert server.crt
key server.key
dh dh.pem
tls-auth ta.key 0
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist ipp.txt" >/etc/openvpn/server.conf
            echo "push \"redirect-gateway def1 bypass-dhcp\"" >>/etc/openvpn/server.conf
            # DNS
            case $DNS in
            1)
                # Obtain the resolvers from resolv.conf and use them for OpenVPN
                grep -v "#" /etc/resolv.conf | grep "nameserver" | grep -E -o "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}" | while read -r line; do
                    echo "push \"dhcp-option DNS $line\"" >>/etc/openvpn/server.conf
                done
                ;;
            2)
                echo "push \"dhcp-option DNS 8.8.8.8\"" >>/etc/openvpn/server.conf
                echo "push \"dhcp-option DNS 8.8.4.4\"" >>/etc/openvpn/server.conf
                ;;
            3)
                echo "push \"dhcp-option DNS 208.67.222.222\"" >>/etc/openvpn/server.conf
                echo "push \"dhcp-option DNS 208.67.220.220\"" >>/etc/openvpn/server.conf
                ;;
            4)
                echo "push \"dhcp-option DNS 1.1.1.1\"" >>/etc/openvpn/server.conf
                echo "push \"dhcp-option DNS 1.0.0.1\"" >>/etc/openvpn/server.conf
                ;;
            5)
                echo "push \"dhcp-option DNS 74.82.42.42\"" >>/etc/openvpn/server.conf
                ;;
            6)
                echo "push \"dhcp-option DNS 64.6.64.6\"" >>/etc/openvpn/server.conf
                echo "push \"dhcp-option DNS 64.6.65.6\"" >>/etc/openvpn/server.conf
                ;;
            7)
                echo "push \"dhcp-option DNS 189.38.95.95\"" >>/etc/openvpn/server.conf
                echo "push \"dhcp-option DNS 216.146.36.36\"" >>/etc/openvpn/server.conf
                ;;
            esac
            echo "keepalive 10 120
float
cipher AES-256-GCM
ncp-ciphers AES-256-GCM:AES-128-GCM
;compress lz4-v2
;push \"compress lz4-v2\"
user nobody
group $GROUPNAME
persist-key
persist-tun
status openvpn-status.log
management localhost 7505
verb 3
crl-verify crl.pem
client-to-client
username-as-common-name
plugin $(find /usr -type f -name \"openvpn-plugin-auth-pam.so\") login
duplicate-cn" >>/etc/openvpn/server.conf
            
            # Apply sysctl settings directly
            sysctl -w net.ipv4.ip_forward=1
            sysctl -w net.core.rmem_max=16777216
            sysctl -w net.core.wmem_max=16777216
            sysctl -w net.ipv4.tcp_rmem=\"4096 87380 16777216\"
            sysctl -w net.ipv4.tcp_wmem=\"4096 87380 16777216\"
            sysctl -w net.ipv4.tcp_window_scaling=1
            sysctl -w net.ipv4.tcp_timestamps=1
            sysctl -w net.ipv4.tcp_sack=1
            sysctl -w net.ipv4.tcp_no_metrics_save=1
            sysctl -w net.core.netdev_max_backlog=250000

            # Configure iptables
            iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -j SNAT --to "$IP"
            iptables -I INPUT -p "$PROTOCOL" --dport "$porta" -j ACCEPT
            iptables -I FORWARD -s 10.8.0.0/24 -j ACCEPT
            iptables -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT

            # Save iptables rules (using iptables-persistent if available)
            if command -v iptables-save >/dev/null; then
                iptables-save > /etc/iptables/rules.v4
            elif command -v netfilter-persistent >/dev/null; then
                netfilter-persistent save
            else
                echo "WARNING: iptables rules not saved persistently. Install iptables-persistent or netfilter-persistent."
            fi

            if hash sestatus 2>/dev/null; then
                if sestatus | grep "Current mode" | grep -qs "enforcing"; then
                    if [[ "$porta" != '1194' || "$PROTOCOL" = 'tcp' ]]; then
                        if ! hash semanage 2>/dev/null; then
                            yum install policycoreutils-python -y
                        fi
                        semanage port -a -t openvpn_port_t -p "$PROTOCOL" "$porta"
                    fi
                fi
            fi
            fun_ropen() {
                systemctl enable openvpn@server || chkconfig openvpn on
                systemctl start openvpn@server || service openvpn start
            }
            
            fun_qos_config() {
                # Priorização de pacotes (QoS) - Exemplo básico
                # Prioriza o tráfego OpenVPN (porta UDP 1194 ou TCP 443, dependendo da configuração)
                # Adapte as regras de QoS conforme a necessidade específica da rede e tráfego.
                # Este é um exemplo simples e pode precisar de ajustes.
                
                # Limpa quaisquer regras tc existentes na interface tun0
                tc qdisc del dev tun0 root 2>/dev/null
                
                # Adiciona uma fila de disciplina de raiz (htb) na interface tun0
                tc qdisc add dev tun0 root handle 1: htb default 10
                
                # Cria uma classe para tráfego de alta prioridade (OpenVPN)
                tc class add dev tun0 parent 1: classid 1:1 prio 1 rate 100mbit ceil 100mbit
                
                # Cria uma classe para tráfego de baixa prioridade
                tc class add dev tun0 parent 1: classid 1:10 prio 2 rate 100mbit ceil 100mbit
                
                # Filtra o tráfego OpenVPN e o direciona para a classe de alta prioridade
                # Assumindo que o OpenVPN usa a porta configurada (ex: 1194 UDP ou 443 TCP)
                if [[ "$PROTOCOL" = "udp" ]]; then
                    tc filter add dev tun0 protocol ip parent 1:0 prio 1 udp dport "$porta" flowid 1:1
                elif [[ "$PROTOCOL" = "tcp" ]]; then
                    tc filter add dev tun0 protocol ip parent 1:0 prio 1 tcp dport "$porta" flowid 1:1
                fi
                
                # Filtra o restante do tráfego para a classe de baixa prioridade
                tc filter add dev tun0 protocol ip parent 1:0 prio 2 flowid 1:10
            }

            echo ""
            echo -e "${GREEN}INICIANDO O OPENVPN${NC}"
            echo ""
            fun_bar 'fun_ropen'
            echo ""
            echo -e "${GREEN}APLICANDO CONFIGURAÇÕES DE QoS${NC}"
            echo ""
            fun_bar 'fun_qos_config'
            
            cat <<-EOF >/etc/openvpn/client-common.txt
                # OVPN_ACCESS_SERVER_PROFILE=[SSHPLUS]
                client
                dev tun
                tun-mtu 1500
                fragment 1300
                proto $PROTOCOL
                sndbuf 0
                rcvbuf 0
                remote $IP $porta
                #payload "HTTP/1.1 [lf]CONNECT HTTP/1.1[lf][lf]|[lf]."
                http-proxy $IP 80 # Assuming default proxy port 80, adjust if needed
                resolv-retry 5
                nobind
                persist-key
                persist-tun
                remote-cert-tls server
                cipher AES-256-GCM
                ;comp-lzo yes
                setenv opt block-outside-dns
                key-direction 1
                verb 3
                auth-user-pass
                keepalive 10 120
                float
EOF
            # gerar client.ovpn
            newclient "SSHPLUS"
            if systemctl is-active --quiet openvpn; then
                echo -e "\n${GREEN}OPENVPN INSTALADO COM SUCESSO${NC}"
            else
                echo -e "\n${RED}ERRO ! A INSTALAÇÃO CORROMPEU${NC}"
            fi
        fi
    fi
    # Ensure IP forwarding is enabled persistently
    if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
        echo "net.ipv4.ip_forward=1" | tee -a /etc/sysctl.conf >/dev/null
    fi
    sysctl -p >/dev/null

    # Disable IPv6 (optional, but in original script)
    if ! grep -q "net.ipv6.conf.all.disable_ipv6=1" /etc/sysctl.conf; then
        echo "net.ipv6.conf.all.disable_ipv6=1" | tee -a /etc/sysctl.conf >/dev/null
    fi
    sysctl -p >/dev/null

    # Add basic firewall rules if not already present
    if ! iptables -C INPUT -p tcp --dport 25 -j DROP 2>/dev/null; then
        iptables -A INPUT -p tcp --dport 25 -j DROP
    fi
    if ! iptables -C INPUT -p tcp --dport 110 -j DROP 2>/dev/null; then
        iptables -A INPUT -p tcp --dport 110 -j DROP
    fi
    if ! iptables -C OUTPUT -p tcp --dport 25 -j DROP 2>/dev/null; then
        iptables -A OUTPUT -p tcp --dport 25 -j DROP
    fi
    if ! iptables -C OUTPUT -p tcp --dport 110 -j DROP 2>/dev/null; then
        iptables -A OUTPUT -p tcp --dport 110 -j DROP
    fi
    if ! iptables -C FORWARD -p tcp --dport 25 -j DROP 2>/dev/null; then
        iptables -A FORWARD -p tcp --dport 25 -j DROP
    fi
    if ! iptables -C FORWARD -p tcp --dport 110 -j DROP 2>/dev/null; then
        iptables -A FORWARD -p tcp --dport 110 -j DROP
    fi

    # Save iptables rules persistently
    if command -v iptables-save >/dev/null; then
        iptables-save > /etc/iptables/rules.v4
    elif command -v netfilter-persistent >/dev/null; then
        netfilter-persistent save
    else
        echo "WARNING: iptables rules not saved persistently. Install iptables-persistent or netfilter-persistent."
    fi
    sleep 3
}

# Menu principal para o script OpenVPN
main_menu() {
    while true; do
        clear
        echo -e "\E[44;1;37m          GERENCIADOR DE OPENVPN           \E[0m"
        echo ""
        echo -e "${RED}[${YELLOW}1${RED}] ${NC}• ${YELLOW}Instalar/Gerenciar OpenVPN${NC}"
        echo -e "${RED}[${YELLOW}0${RED}] ${NC}• ${YELLOW}Sair${NC}"
        echo ""
        echo -ne "${GREEN}Escolha uma opção${NC}: "
        read -r option
        case $option in
            1)
                fun_openvpn
                ;;
            0)
                echo -e "${GREEN}Saindo...${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Opção inválida! Pressione qualquer tecla para continuar...${NC}"
                read -r -n 1
                ;;
        esac
    done
}

# Iniciar o menu principal
main_menu


