#!/usr/bin/env bash
# =================================================================
# OpenVPN Installer & Manager - v2.1.1 (com Compilação de Fonte)
# Baseado no script original do SSH-PRO @TMYCOMNECTVPN
# Revisado para corrigir repositório, TUN check, compilação e systemd.
# =================================================================

set -Eeuo pipefail
IFS=$'\n\t'

# --- Variáveis de Cor e Interface ---
readonly RED=$'\e[1;31m'; readonly GREEN=$'\e[1;32m'; readonly YELLOW=$'\e[1;33m';
readonly BLUE=$'\e[1;34m'; readonly CYAN=$'\e[1;36m'; readonly WHITE=$'\e[1;37m';
readonly MAGENTA=$'\e[1;35m'; readonly SCOLOR=$'\e[0m'; readonly BOLD=$'\e[1m';
readonly SCRIPT_VERSION="2.1.1"; readonly SCRIPT_NAME="OpenVPN Manager Pro"

# Caminhos úteis
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_FINDER="${SCRIPT_DIR}/openvpn_version_finder.py"
ALT_FINDER="/opt/multiflow/ferramentas/openvpn_version_finder.py"

# --- Funções de Utilidade ---
die() { echo -e "${RED}[ERRO] $1${SCOLOR}" >&2; exit "${2:-1}"; }
warn() { echo -e "${YELLOW}[AVISO] $1${SCOLOR}"; }
success() { echo -e "${GREEN}[SUCESSO] $1${SCOLOR}"; }
info() { echo -e "${CYAN}[INFO] $1${SCOLOR}"; }
print_line() { echo -e "${BLUE}═══════════════════════════════════════════════════════════════${SCOLOR}"; }

print_header() {
    clear || true
    print_line
    echo -e "${BOLD}${WHITE}                    ${SCRIPT_NAME} v${SCRIPT_VERSION}${SCOLOR}"
    print_line
}

# --- Funções de Verificação ---
check_root() { [[ "$EUID" -ne 0 ]] && die "Este script precisa ser executado como ROOT."; }
check_tun() { [[ -e /dev/net/tun ]]; }  # retorna 0 se existe, 1 se não

# --- Detecção de Distro ---
detect_distro() {
    local id codename ver
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        id="${ID,,}"
        codename="${VERSION_CODENAME:-}"
        ver="${VERSION_ID:-}"
    else
        id="$(lsb_release -is 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo unknown)"
        codename="$(lsb_release -sc 2>/dev/null || echo)"
        ver="$(lsb_release -rs 2>/dev/null || echo)"
    fi
    if [[ "$id" != "ubuntu" && "$id" != "debian" ]]; then
        warn "Distribuição detectada: $id. Suporte testado apenas em Debian/Ubuntu. Tentando como Debian."
        id="debian"
    fi
    export OS_ID="$id" OS_CODENAME="$codename" OS_VERSION_ID="$ver"
}

enable_universe_if_ubuntu() {
    if [[ "${OS_ID}" == "ubuntu" ]]; then
        if ! grep -E -qs '^[^#].*ubuntu.*universe' /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null; then
            info "Habilitando repositório Universe do Ubuntu para instalar easy-rsa..."
            apt-get update -y
            apt-get install -y software-properties-common || true
            add-apt-repository -y universe || true
            apt-get update -y
        fi
    fi
}

# --- Repositório Oficial OpenVPN 2 ---
configure_openvpn_repo() {
    info "Preparando repositório oficial da OpenVPN..."
    apt-get update -y
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release || die "Falha ao instalar ferramentas base."

    detect_distro
    enable_universe_if_ubuntu

    # Importa a chave do repositório
    curl -fsSL https://packages.openvpn.net/packages-repo.gpg | gpg --dearmor | tee /usr/share/keyrings/openvpn-archive-keyring.gpg >/dev/null

    # Descobre base (ubuntu ou debian)
    local base="${OS_ID}"
    local repo_base="https://packages.openvpn.net/openvpn2/${base}"

    # Lista de codenames candidatos (o primeiro é o do sistema)
    local -a candidates=()
    candidates+=("${OS_CODENAME:-}")
    if [[ "$base" == "ubuntu" ]]; then
        candidates+=("noble" "jammy" "focal" "bionic")
    else
        candidates+=("trixie" "bookworm" "bullseye" "buster")
    fi
    # Remove vazios e duplicados preservando ordem
    local -a uniq=()
    local seen=""
    for c in "${candidates[@]}"; do
        [[ -z "$c" ]] && continue
        if [[ ":$seen:" != *":$c:"* ]]; then
            uniq+=("$c"); seen+=":$c"
        fi
    done

    local chosen=""
    for codename in "${uniq[@]}"; do
        if curl -fsI "${repo_base}/dists/${codename}/Release" >/dev/null 2>&1; then
            chosen="$codename"; break
        fi
    done
    [[ -z "$chosen" ]] && die "Nenhum Release encontrado em ${repo_base}/dists/ para ${OS_ID}. Verifique conexão ou suporte da sua versão."

    info "Usando repositório: ${repo_base} (dist: ${chosen})"
    echo "deb [signed-by=/usr/share/keyrings/openvpn-archive-keyring.gpg] ${repo_base} ${chosen} main" > /etc/apt/sources.list.d/openvpn-packages.list

    apt-get update -y
}

# --- OPÇÃO 1: Instalação via Repositório ---
install_from_repo() {
    info "Iniciando instalação via repositório oficial OpenVPN..."
    configure_openvpn_repo

    info "Instalando OpenVPN e Easy-RSA..."
    apt-get install -y openvpn easy-rsa || die "Falha ao instalar pacotes OpenVPN."
}

# --- Descoberta do Finder Python ---
resolve_finder_script() {
    local path=""
    if [[ -f "$DEFAULT_FINDER" ]]; then
        path="$DEFAULT_FINDER"
    elif [[ -f "$ALT_FINDER" ]]; then
        path="$ALT_FINDER"
    else
        path=""
    fi
    echo -n "$path"
}

# --- Systemd Units para instalação via fonte ---
ensure_systemd_units_for_openvpn() {
    local openvpn_bin
    openvpn_bin="$(command -v openvpn || true)"
    [[ -z "$openvpn_bin" ]] && openvpn_bin="/usr/local/sbin/openvpn"

    local server_unit="/etc/systemd/system/openvpn-server@.service"
    local client_unit="/etc/systemd/system/openvpn-client@.service"

    if [[ ! -f "$server_unit" ]]; then
        info "Criando unidade systemd openvpn-server@.service..."
        cat > "$server_unit" <<EOF
[Unit]
Description=OpenVPN Server for %i
Documentation=man:openvpn(8)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
WorkingDirectory=/etc/openvpn/server
ExecStart=${openvpn_bin} --suppress-timestamps --config %i.conf
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
Restart=on-failure
RestartSec=3
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
RuntimeDirectory=openvpn
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
EOF
        chmod 0644 "$server_unit"
    fi

    if [[ ! -f "$client_unit" ]]; then
        info "Criando unidade systemd openvpn-client@.service..."
        cat > "$client_unit" <<EOF
[Unit]
Description=OpenVPN Client for %i
Documentation=man:openvpn(8)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
WorkingDirectory=/etc/openvpn/client
ExecStart=${openvpn_bin} --suppress-timestamps --config %i.conf
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
Restart=on-failure
RestartSec=3
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
RuntimeDirectory=openvpn
RuntimeDirectoryMode=0750

[Install]
WantedBy=multi-user.target
EOF
        chmod 0644 "$client_unit"
    fi

    systemctl daemon-reload || true
}

# --- OPÇÃO 2: Compilação do Código-Fonte ---
install_from_source() {
    info "Iniciando instalação avançada compilando do código-fonte..."

    info "Instalando dependências para compilação..."
    apt-get update -y
    apt-get install -y \
        build-essential automake autoconf libtool pkg-config \
        libssl-dev liblzo2-dev liblz4-dev libpam0g-dev \
        libpkcs11-helper1-dev libsystemd-dev libcap-ng-dev \
        libnl-3-dev libnl-genl-3-dev \
        resolvconf wget curl ca-certificates tar python3 || die "Falha ao instalar dependências de compilação."

    local finder_script
    finder_script="$(resolve_finder_script)"
    if [[ -z "$finder_script" ]]; then
        die "Script localizador de versão não encontrado. Coloque openvpn_version_finder.py no mesmo diretório do instalador ou em ${ALT_FINDER}."
    fi

    info "Buscando a versão mais recente do OpenVPN via ${finder_script}..."
    local latest_url
    if ! latest_url="$(python3 "$finder_script")"; then
        die "Não foi possível obter a URL da versão mais recente do OpenVPN."
    fi
    [[ -z "$latest_url" ]] && die "URL da versão mais recente vazia."

    success "Versão mais recente encontrada: $latest_url"

    local tmp_dir
    tmp_dir="$(mktemp -d /tmp/openvpn_build.XXXXXXXX)" || die "Não foi possível criar diretório temporário."
    trap 'rm -rf "$tmp_dir"' EXIT

    cd "$tmp_dir"
    info "Baixando o código-fonte..."
    wget -q --show-progress -O openvpn.tar.gz "$latest_url" || die "Falha no download do código-fonte."

    local folder_name
    folder_name="$(tar -tzf openvpn.tar.gz | head -1 | cut -f1 -d"/")"
    [[ -z "$folder_name" ]] && die "Não foi possível determinar o diretório do tarball."
    tar -xzf openvpn.tar.gz
    cd "$folder_name" || die "Não foi possível entrar no diretório do código-fonte."

    if [[ ! -x ./configure ]]; then
        info "Arquivo ./configure não encontrado. Rodando autoreconf -fi..."
        autoreconf -fi || die "Falha ao gerar arquivos de configuração (autoreconf)."
    fi

    info "Configurando o ambiente de compilação (./configure)..."
    ./configure --enable-systemd || die "Falha na etapa de configuração."

    info "Compilando o OpenVPN (make -j$(nproc))... Isso pode levar alguns minutos."
    make -j"$(nproc)" || die "Falha na compilação."

    info "Instalando o OpenVPN (make install)..."
    make install || die "Falha na instalação."

    ldconfig || true

    # Garante diretórios padrão
    install -d -m 0755 /etc/openvpn/server
    install -d -m 0755 /etc/openvpn/client

    ensure_systemd_units_for_openvpn

    info "Instalando o Easy-RSA..."
    enable_universe_if_ubuntu
    apt-get install -y easy-rsa || warn "Falha ao instalar easy-rsa via apt. Instale manualmente se necessário."

    local ovpn_version
    ovpn_version="$(openvpn --version | head -1 | awk '{print $2}')" || true
    success "OpenVPN v${ovpn_version:-desconhecido} compilado e instalado com sucesso (via fonte)."
}

# --- Limpar instalação anterior (opcional) ---
purge_previous_installation() {
    local answer
    if command -v openvpn >/dev/null 2>&1 || dpkg -s openvpn >/dev/null 2>&1; then
        warn "Uma instalação anterior de OpenVPN foi detectada."
        read -r -p "Deseja remover configuração antiga para uma instalação limpa? [s/N]: " answer || true
        if [[ "${answer,,}" == "s" || "${answer,,}" == "sim" || "${answer,,}" == "y" ]]; then
            info "Removendo pacotes e arquivos antigos..."
            apt-get remove --purge -y openvpn easy-rsa || true
            rm -rf /etc/openvpn /etc/easy-rsa ~/ovpn-clients || true
        else
            info "Mantendo arquivos existentes."
        fi
    fi
}

# --- Stubs de configuração (você pode substituir pelos seus) ---
configure_server() {
    info "Configuração de servidor não implementada neste snippet. Integre com sua função existente."
}
configure_firewall() {
    info "Configuração de firewall não implementada neste snippet. Integre com sua função existente."
}
start_openvpn_service() {
    if ! check_tun; then
        warn "Dispositivo TUN/TAP não está disponível (/dev/net/tun). A execução do serviço poderá falhar até habilitar TUN no provedor."
    fi
    info "Recarregando systemd..."
    systemctl daemon-reload || true
    info "Serviços do OpenVPN instalados. Ative uma instância com: systemctl enable --now openvpn-server@server"
}
create_client() {
    local name="${1:-cliente1}"
    info "Função create_client não implementada neste snippet. Criar cliente: ${name}"
}

# --- LÓGICA DE INSTALAÇÃO PRINCIPAL ---
install_openvpn() {
    print_header
    echo -e "${BOLD}${CYAN}              🚀 INSTALAÇÃO DO OPENVPN 🚀${SCOLOR}"
    print_line
    echo
    echo -e "${WHITE}Você pode escolher entre dois métodos de instalação:${SCOLOR}"
    echo
    echo -e "  ${CYAN}[1]${SCOLOR} ${WHITE}Instalação Padrão (Recomendado)${SCOLOR}"
    echo -e "      ${YELLOW}Usa o repositório oficial da OpenVPN (openvpn2).${SCOLOR}"
    echo
    echo -e "  ${CYAN}[2]${SCOLOR} ${WHITE}Instalação Avançada (Compilar do Código-Fonte)${SCOLOR}"
    echo -e "      ${YELLOW}Baixa e compila a versão mais recente estável disponível.${SCOLOR}"
    echo
    print_line
    echo -ne "${WHITE}Escolha o método de instalação [${GREEN}1${WHITE}]: ${SCOLOR}"
    local INSTALL_CHOICE
    read -r INSTALL_CHOICE || true
    INSTALL_CHOICE="${INSTALL_CHOICE:-1}"

    purge_previous_installation

    if [[ "$INSTALL_CHOICE" == "2" ]]; then
        install_from_source
    else
        install_from_repo
    fi

    local ovpn_version
    ovpn_version="$(openvpn --version | head -1 | awk '{print $2}')" || true
    success "OpenVPN v${ovpn_version:-desconhecido} instalado com sucesso!"

    configure_server
    configure_firewall
    start_openvpn_service

    echo; print_line
    echo -e "${GREEN}${BOLD}     ✅ INSTALAÇÃO FINALIZADA! ✅${SCOLOR}"
    print_line; echo

    info "Criando primeiro cliente de demonstração..."
    create_client "cliente1"

    echo
    echo -ne "${CYAN}Pressione ENTER para finalizar...${SCOLOR}"
    read -r || true
}

# --- Ponto de Entrada ---
main() {
    check_root
    # Não checamos TUN aqui; apenas ao iniciar serviço
    install_openvpn
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
