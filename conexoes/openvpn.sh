#!/bin/bash
# =================================================================
# OpenVPN Installer & Manager - v2.1 (com Compilação de Fonte)
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Revisado para incluir instalação via código-fonte.
# =================================================================

# --- Variáveis de Cor e Interface ---
readonly RED=$'\e[1;31m'; readonly GREEN=$'\e[1;32m'; readonly YELLOW=$'\e[1;33m';
readonly BLUE=$'\e[1;34m'; readonly CYAN=$'\e[1;36m'; readonly WHITE=$'\e[1;37m';
readonly MAGENTA=$'\e[1;35m'; readonly SCOLOR=$'\e[0m'; readonly BOLD=$'\e[1m';
readonly SCRIPT_VERSION="2.1.0"; readonly SCRIPT_NAME="OpenVPN Manager Pro";

# --- Funções de Utilidade ---
die() { echo -e "${RED}[ERRO] $1${SCOLOR}" >&2; exit "${2:-1}"; }
warn() { echo -e "${YELLOW}[AVISO] $1${SCOLOR}"; }
success() { echo -e "${GREEN}[SUCESSO] $1${SCOLOR}"; }
info() { echo -e "${CYAN}[INFO] $1${SCOLOR}"; }
print_line() { echo -e "${BLUE}═══════════════════════════════════════════════════════════════${SCOLOR}"; }

print_header() {
    clear
    print_line
    echo -e "${BOLD}${WHITE}                    ${SCRIPT_NAME} v${SCRIPT_VERSION}${SCOLOR}"
    print_line
}

# --- Funções de Verificação ---
check_root() { [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."; }
check_tun() { [[ ! -e /dev/net/tun ]] && die "O dispositivo TUN/TAP não está disponível."; }

# --- LÓGICA DE INSTALAÇÃO ---

# OPÇÃO 1: Instalação via Repositório (Rápido e Padrão)
install_from_repo() {
    info "Iniciando instalação via repositório oficial OpenVPN..."
    
    # Adiciona o repositório oficial para ter uma versão mais recente que a da distro
    info "Adicionando repositório oficial da OpenVPN..."
    apt-get update -qq >/dev/null
    apt-get install -y -qq curl gnupg lsb-release || die "Falha ao instalar ferramentas."
    curl -fsSL https://packages.openvpn.net/packages-repo.gpg | gpg --dearmor -o /usr/share/keyrings/openvpn-archive-keyring.gpg
    local codename; codename="$(lsb_release -sc)"
    echo "deb [signed-by=/usr/share/keyrings/openvpn-archive-keyring.gpg] https://packages.openvpn.net/openvpn2/debian ${codename} main" | tee /etc/apt/sources.list.d/openvpn-packages.list >/dev/null
    apt-get update -qq >/dev/null

    info "Instalando OpenVPN e Easy-RSA..."
    apt-get install -y openvpn easy-rsa || die "Falha ao instalar pacotes OpenVPN."
}

# OPÇÃO 2: Compilação do Código-Fonte (Avançado, Versão Mais Recente)
install_from_source() {
    info "Iniciando instalação avançada compilando do código-fonte..."
    
    # 1. Instalar dependências de compilação
    info "Instalando dependências para compilação..."
    apt-get update -y
    apt-get install -y build-essential libssl-dev liblzo2-dev libpam0g-dev \
        libpkcs11-helper1-dev libsystemd-dev resolvconf pkg-config wget python3 || die "Falha ao instalar dependências de compilação."

    # 2. Encontrar a URL da versão mais recente
    info "Buscando a versão mais recente do OpenVPN..."
    local finder_script="/opt/multiflow/ferramentas/openvpn_version_finder.py"
    if [[ ! -f "$finder_script" ]]; then
        die "Script localizador de versão não encontrado em $finder_script"
    fi
    
    local latest_url
    latest_url=$(python3 "$finder_script")
    if [[ -z "$latest_url" ]]; then
        die "Não foi possível encontrar a URL da versão mais recente do OpenVPN."
    fi
    success "Versão mais recente encontrada: $latest_url"

    # 3. Baixar e compilar
    local tmp_dir="/tmp/openvpn_build_$$"
    mkdir -p "$tmp_dir"
    cd "$tmp_dir" || die "Não foi possível entrar no diretório temporário."
    
    info "Baixando o código-fonte..."
    wget -q --show-progress -O openvpn.tar.gz "$latest_url" || die "Falha no download do código-fonte."
    
    local folder_name
    folder_name=$(tar -tzf openvpn.tar.gz | head -1 | cut -f1 -d"/")
    tar -xzf openvpn.tar.gz
    cd "$folder_name" || die "Não foi possível entrar no diretório do código-fonte."
    
    info "Configurando o ambiente de compilação (./configure)..."
    ./configure || die "Falha na etapa de configuração."
    
    info "Compilando o OpenVPN (make)... Isso pode levar alguns minutos."
    make || die "Falha na compilação."
    
    info "Instalando o OpenVPN (make install)..."
    make install || die "Falha na instalação."
    
    # Limpeza
    cd /
    rm -rf "$tmp_dir"
    
    # Instala o Easy-RSA separadamente, pois ele não vem com o código-fonte do OpenVPN
    info "Instalando o Easy-RSA..."
    apt-get install -y easy-rsa || die "Falha ao instalar o Easy-RSA."
}

# Função principal de instalação que oferece a escolha
install_openvpn() {
    print_header
    echo -e "${BOLD}${CYAN}              🚀 INSTALAÇÃO DO OPENVPN 🚀${SCOLOR}"
    print_line
    echo
    echo -e "${WHITE}Você pode escolher entre dois métodos de instalação:${SCOLOR}"
    echo
    echo -e "  ${CYAN}[1]${SCOLOR} ${WHITE}Instalação Padrão (Recomendado)${SCOLOR}"
    echo -e "      ${YELLOW}Rápido, usa o repositório oficial do OpenVPN. Ótimo para a maioria dos casos.${SCOLOR}"
    echo
    echo -e "  ${CYAN}[2]${SCOLOR} ${WHITE}Instalação Avançada (Compilar do Código-Fonte)${SCOLOR}"
    echo -e "      ${YELLOW}Lento, baixa e compila a versão mais recente disponível. Para usuários avançados.${SCOLOR}"
    echo
    print_line
    echo -ne "${WHITE}Escolha o método de instalação [${GREEN}1${WHITE}]: ${SCOLOR}"
    read -r INSTALL_CHOICE

    # Desinstala qualquer versão anterior para uma instalação limpa
    apt-get remove --purge -y openvpn easy-rsa >/dev/null 2>&1
    rm -rf /etc/openvpn /etc/easy-rsa ~/ovpn-clients

    if [[ "$INSTALL_CHOICE" == "2" ]]; then
        install_from_source
    else
        install_from_repo
    fi

    local ovpn_version
    ovpn_version=$(openvpn --version | head -1 | awk '{print $2}')
    success "OpenVPN v${ovpn_version} instalado com sucesso!"

    # Continua com a configuração do servidor, que é comum a ambos os métodos
    configure_server
    configure_firewall
    start_openvpn_service
    
    echo; print_line
    echo -e "${GREEN}${BOLD}     ✅ CONFIGURAÇÃO DO SERVIDOR FINALIZADA! ✅${SCOLOR}"
    print_line; echo
    
    info "Criando primeiro cliente de demonstração..."
    create_client "cliente1" # Supondo que a função create_client existe
    
    echo;
    echo -ne "${CYAN}Pressione ENTER para voltar ao menu principal...${SCOLOR}"
    read -r
}

# ... (O resto do seu script: configure_server, create_client, main_menu, etc.) ...
# As outras funções como `configure_server`, `create_client`, `main_menu`
# podem ser mantidas como estão, pois a lógica de configuração do servidor
# e gerenciamento de clientes não muda. Apenas o método de instalação do binário
# do OpenVPN foi alterado.

# --- Ponto de Entrada ---
main() {
    check_root
    check_tun
    
    # O script agora vai direto para a função de instalação
    install_openvpn
    
    # Após a instalação, você pode chamar o main_menu se desejar
    # main_menu 
}

# Garante que o script seja executável e chama a função principal.
# Esta parte é um exemplo, integre ao seu fluxo existente.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
