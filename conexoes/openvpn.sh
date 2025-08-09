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

add_openvpn_repo() {
    # Adiciona repositório oficial da OpenVPN
    echo "Adicionando repositório oficial da OpenVPN..."
    
    # Garante ferramentas necessárias
    apt-get update -qq
    apt-get install -y -qq curl gnupg lsb-release || die "Falha ao instalar ferramentas."

    # Adiciona a chave do repositório
    curl -fsSL https://packages.openvpn.net/packages-repo.gpg | gpg --dearmor -o /usr/share/keyrings/openvpn-archive-keyring.gpg

    # Configuração do repositório
    local codename
    codename="$(lsb_release -sc)"
    
    echo "deb [signed-by=/usr/share/keyrings/openvpn-archive-keyring.gpg] https://packages.openvpn.net/openvpn2/debian ${codename} main" | tee /etc/apt/sources.list.d/openvpn-packages.list

    # Atualiza o repositório
    apt-get update -qq
}

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

    # Adiciona o repositório e instala a versão mais recente
    add_openvpn_repo

    echo -e "${CYAN}Instalando OpenVPN...${SCOLOR}"
    fun_bar "apt-get install -y openvpn easy-rsa iptables lsof"

    # Verificação da instalação
    local ovpn_version
    ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    echo -e "${GREEN}✓ OpenVPN instalado: ${BOLD}${ovpn_version}${SCOLOR}"

    # Continuar com a configuração
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

# Restante das funções (configure_server, configure_firewall, start_openvpn_service, create_client, revoke_client, uninstall_openvpn, main_menu, main) permanece inalterado

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
    
    echo
    # Chama a função para garantir a instalação da versão mais recente do OpenVPN
    install_openvpn
    
    echo
    print_footer
    echo -ne "${CYAN}Pressione ENTER para continuar...${SCOLOR}"
    read -r
    
    main_menu
}

main
