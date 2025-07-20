#!/bin/bash

# Função para exibir mensagens de erro e sair
error_exit() {
    echo "Erro: $1" >&2
    exit 1
}

# Diretório de destino para o projeto
PROJECT_DIR="/opt/rusty_socks_proxy"

# Caminho para o script de gerenciamento de usuários SSH
SSH_USER_MANAGEMENT_SCRIPT="/opt/rusty_socks_proxy/new_ssh_user_management.sh"

# URL base para download dos arquivos do projeto no GitHub
GITHUB_RAW_URL="https://raw.githubusercontent.com/mycroft440/SOCKS5PRO/main/"

# Instalar Rust e Cargo para o root, se não estiverem instalados
    if ! sudo -i bash -c "command -v cargo &>/dev/null"; then
        echo "[INFO] Instalando Rust e Cargo para o root...\n"
        curl --tlsv1.2 -sSf https://sh.rustup.rs | sudo sh -s -- -y --no-modify-path || error_exit "[ERRO] Falha ao instalar Rust para root.\n"
        sudo -i bash -c "/root/.cargo/bin/rustup default stable" || echo "[AVISO] Não foi possível configurar o rustup default stable para o root."
        echo "[SUCESSO] Rust e Cargo instalados para o root.\n"
    else
        echo "[INFO] Rust e Cargo já estão instalados para o root.\n"
    fi

# Função para instalar o proxy
install_proxy_single_command() {
    clear
    echo "\n--- Instalar Rusty SOCKS5 Proxy ---"
    read -p "Digite a porta para o Rusty SOCKS5 Proxy (padrão: 1080): " SOCKS5_PORT
    SOCKS5_PORT=${SOCKS5_PORT:-1080}
    export SOCKS5_PORT

    echo "[INFO] Iniciando a instalação do Rusty SOCKS5 Proxy na porta $SOCKS5_PORT...\n"



    # 2. Instalar build-essential
    echo "[INFO] Atualizando pacotes e instalando build-essential...\n"
    sudo apt update >&/dev/null || error_exit "[ERRO] Falha ao atualizar pacotes.\n"
    sudo apt install build-essential -y || error_exit "[ERRO] Falha ao instalar build-essential.\n"
    echo "[SUCESSO] build-essential instalado.\n"

    # 3. Mover arquivos do projeto para um diretório padrão
    echo "[INFO] Criando diretório do projeto em $PROJECT_DIR...\n"
    sudo mkdir -p $PROJECT_DIR || error_exit "[ERRO] Falha ao criar diretório do projeto.\n"

    echo "[INFO] Baixando arquivos do projeto para $PROJECT_DIR...\n"

    sudo wget -qO "$PROJECT_DIR/src/main.rs" "${GITHUB_RAW_URL}main.rs" || error_exit "[ERRO] Falha ao baixar main.rs.\n"
    sudo wget -qO "$PROJECT_DIR/src/Cargo.toml" "${GITHUB_RAW_URL}Cargo.toml" || error_exit "[ERRO] Falha ao baixar Cargo.toml.\n"
    sudo wget -qO "$PROJECT_DIR/rusty_socks_proxy.service" "${GITHUB_RAW_URL}rusty_socks_proxy.service" || error_exit "[ERRO] Falha ao baixar rusty_socks_proxy.service.\n"
    sudo wget -qO "$PROJECT_DIR/new_ssh_user_management.sh" "${GITHUB_RAW_URL}new_ssh_user_management.sh" || error_exit "[ERRO] Falha ao baixar new_ssh_user_management.sh.\n"
    
    # 4. Compilar o projeto Rust
    echo "[INFO] Compilando o projeto Rust...\n"

    sudo -i bash -c "cd $PROJECT_DIR/src && export PATH=\"/root/.cargo/bin:\$PATH\" && /root/.cargo/bin/cargo build --release" || error_exit "[ERRO] Falha ao compilar o projeto Rust.\n"
    echo "[SUCESSO] Projeto Rust compilado.\n"

    # 5. Mover o executável compilado
    echo "[INFO] Movendo o executável compilado...\n"
    sudo mv $PROJECT_DIR/src/target/release/rusty_socks_proxy $PROJECT_DIR/rusty_socks_proxy || error_exit "[ERRO] Falha ao mover o executável.\n"
    echo "[SUCESSO] Executável movido.\n"

    # 6. Configurar e iniciar o serviço systemd
    echo "[INFO] Configurando e iniciando o serviço systemd...\n"
    sudo cp $PROJECT_DIR/rusty_socks_proxy.service /etc/systemd/system/rusty_socks_proxy.service || error_exit "[ERRO] Falha ao copiar o arquivo de serviço.\n"
    sudo sed -i "s|ExecStart=.*|ExecStart=$PROJECT_DIR/rusty_socks_proxy|g" /etc/systemd/system/rusty_socks_proxy.service || error_exit "[ERRO] Falha ao configurar o caminho do executável no arquivo de serviço.\n"
    sudo sed -i "s|Environment=\"SOCKS5_PORT=.*|Environment=\"SOCKS5_PORT=$SOCKS5_PORT\"|g" /etc/systemd/system/rusty_socks_proxy.service || error_exit "[ERRO] Falha ao configurar a porta no arquivo de serviço.\n"
    sudo systemctl daemon-reload || error_exit "[ERRO] Falha ao recarregar o daemon do systemd.\n"
    sudo systemctl enable rusty_socks_proxy || error_exit "[ERRO] Falha ao habilitar o serviço.\n"
    sudo systemctl start rusty_socks_proxy || error_exit "[ERRO] Falha ao iniciar o serviço.\n"
    echo "[SUCESSO] Serviço Rusty SOCKS5 Proxy configurado e iniciado na porta $SOCKS5_PORT.\n"
    echo "Você pode verificar o status com: sudo systemctl status rusty_socks_proxy\n"
} || error_exit "[ERRO] Falha na instalação completa do Rusty SOCKS5 Proxy.\n"

install_ssh_user_manager() {
    clear
    echo "\n--- Instalar Gerenciador de Usuários SSH ---"
    echo "[INFO] Baixando o script de gerenciamento de usuários SSH...\n"
    sudo wget -qO "$SSH_USER_MANAGEMENT_SCRIPT" "${GITHUB_RAW_URL}new_ssh_user_management.sh" || error_exit "[ERRO] Falha ao baixar new_ssh_user_management.sh.\n"
    sudo chmod +x "$SSH_USER_MANAGEMENT_SCRIPT" || error_exit "[ERRO] Falha ao dar permissão de execução ao script de gerenciamento de usuários SSH.\n"
    echo "[SUCESSO] Gerenciador de Usuários SSH instalado em $SSH_USER_MANAGEMENT_SCRIPT.\n"
    read -p "Pressione Enter para continuar..."
}

# Função para gerenciar usuários SSH
manage_ssh_users_menu() {
    # Inclui o script de gerenciamento de usuários SSH
    if [ -f "$SSH_USER_MANAGEMENT_SCRIPT" ]; then
        source "$SSH_USER_MANAGEMENT_SCRIPT" &>/dev/null # Redireciona stdout e stderr para /dev/null
    else
        echo "[ERRO] Script de gerenciamento de usuários SSH não encontrado: $SSH_USER_MANAGEMENT_SCRIPT"
        read -p "Pressione Enter para continuar..."
        return 1
    fi

    while true; do
        clear
        echo "\n--- Gerenciamento de Usuários SSH ---"
        echo "1. Criar Usuário SSH"
        echo "2. Remover Usuário SSH"
        echo "3. Listar Usuários SSH"
        echo "4. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice

        # Validação de entrada: verifica se a escolha é um número e está dentro das opções válidas
        if ! [[ "$choice" =~ ^[1-4]$ ]]; then
            echo "Opção inválida. Tente novamente."
            read -p "Pressione Enter para continuar..."
            continue
        fi

        case $choice in
            1) create_ssh_user ;;
            2) remove_ssh_user ;;
            3) list_ssh_users ;;
            4) break ;;
        esac
        # Adiciona uma pausa apenas se a opção não for sair
        if [[ "$choice" != "4" ]]; then
            read -p "Pressione Enter para continuar..."
        fi
    done
}

# Função para exibir o status do serviço e a porta
show_status() {
    clear
    echo "\n--- Status do Rusty SOCKS5 Proxy ---"
    SERVICE_STATUS=$(sudo systemctl is-active rusty_socks_proxy)
    SERVICE_ENABLED=$(sudo systemctl is-enabled rusty_socks_proxy)

    echo "Status do Serviço: $SERVICE_STATUS"
    echo "Habilitado na Inicialização: $SERVICE_ENABLED"

    # Tenta obter a porta do arquivo de serviço ou da variável de ambiente
    PORT=$(grep "Environment=\"SOCKS5_PORT=" /etc/systemd/system/rusty_socks_proxy.service | cut -d\"=\" -f3 | cut -d\"\" -f1 2>/dev/null || echo $SOCKS5_PORT)
    if [ -z "$PORT" ]; then
        PORT="Não Definida (Padrão: 1080)"
    fi
    echo "Porta do SOCKS5: $PORT"

    echo "------------------------------------"
    read -p "Pressione Enter para continuar..."
}

# Função para instalar o dtproxy (mod mycroft)
install_dtproxy_mycroft() {
    clear
    echo "\n--- Instalar dtproxy (mod mycroft) ---"
    echo "[INFO] Movendo arquivos do dtproxy para /opt/dtproxy/...\n"
    sudo mkdir -p /opt/dtproxy || error_exit "[ERRO] Falha ao criar diretório /opt/dtproxy.\n"
    sudo cp /home/ubuntu/dtproxy_project/dtproxy_x86_64 /opt/dtproxy/dtproxy_x86_64 || error_exit "[ERRO] Falha ao copiar dtproxy_x86_64.\n"
    sudo cp /home/ubuntu/dtproxy_project/dtproxy_menu.sh /opt/dtproxy/dtproxy_menu.sh || error_exit "[ERRO] Falha ao copiar dtproxy_menu.sh.\n"
    sudo cp /home/ubuntu/dtproxy_project/dtproxy_port_menu.sh /opt/dtproxy/dtproxy_port_menu.sh || error_exit "[ERRO] Falha ao copiar dtproxy_port_menu.sh.\n"
    echo "[SUCESSO] Arquivos do dtproxy movidos.\n"

    echo "[INFO] Dando permissão de execução ao dtproxy_x86_64...\n"
    sudo chmod +x /opt/dtproxy/dtproxy_x86_64 || error_exit "[ERRO] Falha ao dar permissão de execução ao dtproxy_x86_64.\n"
    sudo chmod +x /opt/dtproxy/dtproxy_menu.sh || error_exit "[ERRO] Falha ao dar permissão de execução ao dtproxy_menu.sh.\n"
    sudo chmod +x /opt/dtproxy/dtproxy_port_menu.sh || error_exit "[ERRO] Falha ao dar permissão de execução ao dtproxy_port_menu.sh.\n"
    echo "[SUCESSO] Permissão de execução concedida.\n"

    echo "[INFO] Criando e configurando o serviço systemd para dtproxy...\n"
    DTPROXY_SERVICE_FILE="/etc/systemd/system/dtproxy.service"
    echo "[Unit]" | sudo tee $DTPROXY_SERVICE_FILE > /dev/null
    echo "Description=DTProxy Service" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "After=network.target" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "[Service]" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "ExecStart=/opt/dtproxy/dtproxy_x86_64" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "Restart=always" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "User=root" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "[Install]" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null
    echo "WantedBy=multi-user.target" | sudo tee -a $DTPROXY_SERVICE_FILE > /dev/null

    sudo systemctl daemon-reload || error_exit "[ERRO] Falha ao recarregar o daemon do systemd.\n"
    sudo systemctl enable dtproxy || error_exit "[ERRO] Falha ao habilitar o serviço dtproxy.\n"
    sudo systemctl start dtproxy || error_exit "[ERRO] Falha ao iniciar o serviço dtproxy.\n"
    echo "[SUCESSO] Serviço dtproxy configurado e iniciado.\n"
    echo "Você pode verificar o status com: sudo systemctl status dtproxy\n"
    read -p "Pressione Enter para continuar..."
}

# Função para gerenciar conexões
manage_connections_menu() {
    while true; do
        clear
        echo "\n--- Gerenciamento de Conexões ---"
        echo "1. Instalar Rusty SOCKS5 Proxy"
        echo "2. Instalar dtproxy (mod mycroft)"
        echo "3. Gerenciar OpenVPN"
        echo "4. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice

        if ! [[ "$choice" =~ ^[1-4]$ ]]; then
            echo "Opção inválida. Tente novamente."
            read -p "Pressione Enter para continuar..."
            continue
        fi

        case $choice in
            1) install_proxy_single_command ;;
            2) install_dtproxy_mycroft ;;
            3) manage_openvpn_menu ;;
            4) break ;;
        esac
        if [[ "$choice" != "4" ]]; then
            read -p "Pressione Enter para continuar..."
        fi
    done
}


# Funções para as novas ferramentas
run_iostat() {
    clear
    echo "\n--- iostat (CPU, Disco, Rede) ---"
    echo "[INFO] Executando iostat...\n"
    sudo apt update >&/dev/null
    sudo apt install sysstat -y
    iostat -c -d -N -x 1 5 # Exibe CPU, disco, LVM, estendido, a cada 1 segundo, 5 vezes
    read -p "Pressione Enter para continuar..."
}

optimize_kernel() {
    clear
    echo "\n--- Otimização do Kernel ---"
    echo "[INFO] Aplicando otimizações básicas no kernel (sysctl)...\n"
    # Exemplo de otimizações (pode ser expandido)
    sudo sysctl -w net.core.somaxconn=65536
    sudo sysctl -w net.core.netdev_max_backlog=65536
    sudo sysctl -w net.ipv4.tcp_tw_reuse=1
    sudo sysctl -w net.ipv4.tcp_fin_timeout=30
    sudo sysctl -w net.ipv4.tcp_keepalive_time=600
    sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65536
    sudo sysctl -w net.ipv4.tcp_max_tw_buckets=2000000
    sudo sysctl -w net.ipv4.tcp_mem='786432 1048576 1572864'
    sudo sysctl -w net.ipv4.tcp_rmem='4096 87380 16777216'
    sudo sysctl -w net.ipv4.tcp_wmem='4096 65536 16777216'
    sudo sysctl -w net.ipv4.ip_local_port_range='1024 65535'
    
    echo "[INFO] Salvando as configurações do sysctl...\n"
    sudo sysctl -p
    echo "[SUCESSO] Otimizações do kernel aplicadas e salvas.\n"
    read -p "Pressione Enter para continuar..."
}

install_and_run_stacer() {
    clear
    echo "\n--- Stacer (Monitorar, Limpar, Otimizar) ---"
    echo "[INFO] Verificando e instalando Stacer...\n"
    if ! command -v stacer &>/dev/null; then
        sudo apt update >&/dev/null
        sudo apt install -y stacer || error_exit "[ERRO] Falha ao instalar Stacer.\n"
        echo "[SUCESSO] Stacer instalado.\n"
    else
        echo "[INFO] Stacer já está instalado.\n"
    fi
    echo "[INFO] Iniciando Stacer... (Pode ser necessário uma interface gráfica)\n"
    stacer
    read -p "Pressione Enter para continuar..."
}

run_bleachbit() {
    clear
    echo "\n--- BleachBit (Limpeza do Sistema) ---"
    echo "[INFO] Verificando e instalando BleachBit...\n"
    if ! command -v bleachbit &>/dev/null; then
        sudo apt update >&/dev/null
        sudo apt install -y bleachbit || error_exit "[ERRO] Falha ao instalar BleachBit.\n"
        echo "[SUCESSO] BleachBit instalado.\n"
    else
        echo "[INFO] BleachBit já está instalado.\n"
    fi
    echo "[INFO] Iniciando BleachBit... (Pode ser necessário uma interface gráfica)\n"
    bleachbit
    read -p "Pressione Enter para continuar..."
}

# Função para gerenciar ferramentas
manage_tools_menu() {
    while true; do
        clear
        echo "\n--- Ferramentas (Limpeza e Performance) ---"
        echo "1. iostat (CPU, Disco, Rede)"
        echo "2. Otimização do Kernel"
        echo "3. Stacer (Monitorar, Limpar, Otimizar)"
        echo "4. BleachBit (Limpeza do Sistema)"
        echo "5. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice

        if ! [[ "$choice" =~ ^[1-5]$ ]]; then
            echo "Opção inválida. Tente novamente."
            read -p "Pressione Enter para continuar..."
            continue
        fi

        case $choice in
            1) run_iostat ;;
            2) optimize_kernel ;;
            3) install_and_run_stacer ;;
            4) run_bleachbit ;;
            5) break ;;
        esac
        if [[ "$choice" != "5" ]]; then
            read -p "Pressione Enter para continuar..."
        fi
    done
}

# Função para gerenciar OpenVPN
manage_openvpn_menu() {
    while true; do
        clear
        echo "\n--- Gerenciamento de OpenVPN ---"
        echo "1. Instalar OpenVPN"
        echo "2. Alterar Porta"
        echo "3. Remover OpenVPN"
        echo "4. Voltar ao Menu Principal"
        echo "------------------------------------"
        read -p "Escolha uma opção: " choice

        if ! [[ "$choice" =~ ^[1-4]$ ]]; then
            echo "Opção inválida. Tente novamente."
            read -p "Pressione Enter para continuar..."
            continue
        fi

        case $choice in
            1) 
                clear
                echo "\n--- Instalar OpenVPN ---"
                echo "[INFO] Iniciando instalação do OpenVPN..."
                echo "[INFO] Esta operação pode demorar alguns minutos."
                read -p "Pressione Enter para continuar ou Ctrl+C para cancelar..."
                fun_openvpn
                ;;
            2) 
                clear
                echo "\n--- Alterar Porta OpenVPN ---"
                if [[ $(netstat -nplt | grep -wc "openvpn") != "0" ]]; then
                    local opnp=$(cat /etc/openvpn/server.conf | grep "port" | awk '{print $2}' | head -1)
                    echo "Porta atual: $opnp"
                    read -p "Digite a nova porta: " nova_porta
                    if [[ -n "$nova_porta" ]]; then
                        sed -i "s/^port .*/port $nova_porta/g" /etc/openvpn/server.conf
                        sed -i "s/remote .* [0-9]*/remote $(wget -4qO- "http://whatismyip.akamai.com/") $nova_porta/g" /etc/openvpn/client-common.txt
                        systemctl restart openvpn@server
                        echo "[SUCESSO] Porta alterada para $nova_porta"
                    else
                        echo "[ERRO] Porta inválida"
                    fi
                else
                    echo "[ERRO] OpenVPN não está instalado ou não está rodando"
                fi
                read -p "Pressione Enter para continuar..."
                ;;
            3) 
                clear
                echo "\n--- Remover OpenVPN ---"
                if [[ $(netstat -nplt | grep -wc "openvpn") != "0" ]]; then
                    echo -n "Deseja realmente remover o OpenVPN? [s/N]: "
                    read -r confirm
                    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
                        systemctl stop openvpn@server
                        systemctl disable openvpn@server
                        apt-get remove --purge -y openvpn
                        rm -rf /etc/openvpn
                        echo "[SUCESSO] OpenVPN removido com sucesso"
                    else
                        echo "[INFO] Operação cancelada"
                    fi
                else
                    echo "[ERRO] OpenVPN não está instalado"
                fi
                read -p "Pressione Enter para continuar..."
                ;;
            4) break ;;
        esac
    done
}

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
    local PT=$(lsof -V -i tcp -P -n | grep -v "ESTABLISHED" | grep -v "COMMAND" | grep "LISTEN")
    for pton in $(echo -e "$PT" | cut -d: -f2 | cut -d" " -f1 | uniq); do
        local svcs=$(echo -e "$PT" | grep -w "$pton" | awk '{print $1}' | uniq)
        [[ "$porta" = "$pton" ]] && {
            echo -e "\\n${RED}PORTA ${YELLOW}$porta ${RED}EM USO PELO ${NC}$svcs${NC}"
            sleep 3
            return 1 # Indica que a porta está em uso
        }
    done
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
    local RCLOCAL

    if [[ -e /etc/debian_version ]]; then
        OS=debian
        GROUPNAME=nogroup
        RCLOCAL="/etc/rc.local"
    elif [[ -e /etc/centos-release || -e /etc/redhat-release ]]; then
        OS=centos
        GROUPNAME=nobody
        RCLOCAL="/etc/rc.d/rc.local"
    else
        echo -e "${RED}SISTEMA NAO SUPORTADO${NC}"
        exit 5
    fi

    local IP1=$(ip addr | grep "inet" | grep -v inet6 | grep -vE "127\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}" | grep -o -E "[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}" | head -1)
    local IP2=$(wget -4qO- "http://whatismyip.akamai.com/")
    local IP

    [[ "$IP1" = "" ]] && {
        IP1=$(hostname -I | cut -d" " -f1)
    }
    [[ "$IP1" != "$IP2" ]] && {
        IP="$IP1"
    } || {
        IP="$IP2"
    }

    # Instalar OpenVPN
    clear
    echo -e "\\E[44;1;37m              INSTALADOR OPENVPN               \\E[0m"
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
    echo -ne "${GREEN}DIGITE A PORTA PARA O OPENVPN (padrão: 1194)${NC}: "
    read -r -e -i "1194" porta
    porta=${porta:-1194}
    
    echo ""
    echo -e "${YELLOW}VERIFICANDO PORTA...${NC}"
    if ! verif_ptrs "$porta"; then
        return
    fi
    
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
        fun_bar 'apt-get update -y && apt-get install -y build-essential libssl-dev liblzo2-dev libpam0g-dev pkg-config git wget curl unzip iproute2 net-tools openvpn easy-rsa'
    elif [[ "$OS" = 'centos' ]]; then
        echo -e "${GREEN}ATUALIZANDO O SISTEMA E INSTALANDO DEPENDÊNCIAS DE COMPILAÇÃO${NC}"
        fun_bar 'yum update -y && yum install -y epel-release && yum install -y gcc make autoconf automake openssl-devel lzo-devel pam-devel pkgconfig git wget curl unzip iproute2 net-tools openvpn easy-rsa'
    fi

    # Configurar easy-rsa
    echo ""
    echo -e "${GREEN}CONFIGURANDO EASY-RSA${NC}"
    fun_get_easy_rsa() {
        rm -rf /etc/openvpn/easy-rsa/
        mkdir -p /etc/openvpn/easy-rsa/
        cp -r /usr/share/easy-rsa/* /etc/openvpn/easy-rsa/
        chown -R root:root /etc/openvpn/easy-rsa/
        chmod -R 700 /etc/openvpn/easy-rsa/
        cd /etc/openvpn/easy-rsa/ || exit
        ./easyrsa init-pki
        ./easyrsa --batch build-ca nopass
        ./easyrsa gen-dh
        ./easyrsa build-server-full server nopass
        ./easyrsa build-client-full SSHPLUS nopass
        ./easyrsa gen-crl
        cp pki/ca.crt pki/private/ca.key pki/dh.pem pki/issued/server.crt pki/private/server.key pki/crl.pem /etc/openvpn/
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
        grep -v "#" /etc/resolv.conf | grep "nameserver" | grep -E -o "[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}" | while read -r line; do
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
user nobody
group $GROUPNAME
persist-key
persist-tun
status openvpn-status.log
verb 3
crl-verify crl.pem
duplicate-cn" >>/etc/openvpn/server.conf

    sed -i "s/^net.ipv4.ip_forward=.*/net.ipv4.ip_forward=1/" /etc/sysctl.conf
    echo 1 >/proc/sys/net/ipv4/ip_forward

    if [[ "$OS" = 'debian' && ! -e "$RCLOCAL" ]]; then
        echo -e "#!/bin/sh -e\\nexit 0" >"$RCLOCAL"
    fi
    chmod +x "$RCLOCAL"
    iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -j SNAT --to "$IP"
    sed -i "1 a\\iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -j SNAT --to $IP" "$RCLOCAL"
    
    if pgrep firewalld; then
        firewall-cmd --zone=public --add-port="$porta"/"$PROTOCOL"
        firewall-cmd --zone=trusted --add-source=10.8.0.0/24
        firewall-cmd --permanent --zone=public --add-port="$porta"/"$PROTOCOL"
        firewall-cmd --permanent --zone=trusted --add-source=10.8.0.0/24
    fi
    
    if iptables -L -n | grep -qE 'REJECT|DROP'; then
        iptables -I INPUT -p "$PROTOCOL" --dport "$porta" -j ACCEPT
        iptables -I FORWARD -s 10.8.0.0/24 -j ACCEPT
        iptables -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
        sed -i "1 a\\iptables -I INPUT -p $PROTOCOL --dport $porta -j ACCEPT" "$RCLOCAL"
        sed -i "1 a\\iptables -I FORWARD -s 10.8.0.0/24 -j ACCEPT" "$RCLOCAL"
        sed -i "1 a\\iptables -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT" "$RCLOCAL"
    fi

    fun_ropen() {
        systemctl enable openvpn@server.service
        systemctl start openvpn@server.service
    }

    echo ""
    echo -e "${GREEN}INICIANDO O OPENVPN${NC}"
    echo ""
    fun_bar 'fun_ropen'
    
    local pt_proxy=80 # Valor padrão, pode ser ajustado se necessário
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
resolv-retry 5
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
setenv opt block-outside-dns
key-direction 1
verb 3
auth-user-pass
keepalive 10 120
float
EOF
    
    # gerar client.ovpn
    newclient "SSHPLUS"
    [[ "$(netstat -nplt | grep -wc 'openvpn')" != '0' ]] && echo -e "\\n${GREEN}OPENVPN INSTALADO COM SUCESSO${NC}" || echo -e "\\n${RED}ERRO ! A INSTALAÇÃO CORROMPEU${NC}"
    
    echo ""
    echo -e "${GREEN}Arquivo de configuração do cliente criado: ~/SSHPLUS.ovpn${NC}"
    read -p "Pressione Enter para continuar..."
}

# Menu principal
main_menu() {
    # Instala o gerenciador de usuários SSH automaticamente no início
    install_ssh_user_manager

    while true; do
        clear
        echo "
    __  _____  ____  __________________    ____ _       __
   /  |/  / / / / / /_  __/  _/ ____/ /   / __ \ |     / /
  / /|_/ / / / / /   / /  / // /_  / /   / / / / | /| / / 
 / /  / / /_/ / /___/ / _/ // __/ / /___/ /_/ /| |/ |/ /  
/_/  /_/\____/_____/_/ /___/_/   /_____/\____/ |__/|__/   
                                                          
        --- Bem-vindo ao MULTIFLOW manager ---"

        echo "1. Gerenciar Usuários"
        echo "2. Gerenciar Conexões"
        echo "3. Status dos serviços"
        echo "4. Ferramentas (Limpeza e Performance)"
        echo "5. Sair"
        echo "----------------------------------------------------"
        read -p "Escolha uma opção: " choice

        # Validação de entrada: verifica se a escolha é um número e está dentro das opções válidas
        if ! [[ "$choice" =~ ^[1-5]$ ]]; then
            echo "Opção inválida. Tente novamente."
            read -p "Pressione Enter para continuar..."
            continue
        fi

        case $choice in
            1) manage_ssh_users_menu ;;
            2) manage_connections_menu ;;
            3) show_status ;;
            4) manage_tools_menu ;;
            5) echo "Saindo..." ; exit 0 ;;
        esac
    done
}


main_menu


