#!/bin/bash
# Script para instalar OpenVPN de forma não-interativa
# Baseado no script de angristan: https://github.com/angristan/openvpn-install
# Versão melhorada com tratamento de erros e recursos adicionais

set -euo pipefail  # Para falhar em erros, variáveis não definidas e pipes
IFS=$'\n\t'       # Define separador de campo interno seguro

# Cores para output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

# Configurações
readonly SCRIPT_VERSION="1.0.0"
readonly OPENVPN_SCRIPT_URL="https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh"
readonly DEFAULT_CLIENT_NAME="cliente1"
readonly LOG_FILE="/var/log/openvpn-install-$(date +%Y%m%d-%H%M%S).log"

# Função para logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Função para exibir mensagens coloridas
print_success() {
    echo -e "${GREEN}✓${NC} $1"
    log "SUCCESS: $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
    log "ERROR: $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    log "WARNING: $1"
}

# Função para exibir mensagem de erro e sair
error_exit() {
    print_error "$1"
    exit 1
}

# Função para verificar comandos necessários
check_requirements() {
    local missing_tools=()
    
    for tool in wget curl iptables systemctl; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        error_exit "Ferramentas necessárias não encontradas: ${missing_tools[*]}"
    fi
}

# Função para detectar o sistema operacional
detect_os() {
    if [[ -e /etc/os-release ]]; then
        source /etc/os-release
        OS="${ID}"
        OS_VERSION="${VERSION_ID}"
    else
        error_exit "Sistema operacional não suportado"
    fi
    
    # Verifica se o OS é suportado
    case "$OS" in
        ubuntu|debian|centos|fedora|almalinux|rocky)
            log "Sistema operacional detectado: $OS $OS_VERSION"
            ;;
        *)
            error_exit "Sistema operacional não suportado: $OS"
            ;;
    esac
}

# Função para detectar IP público com fallback
get_public_ip() {
    local ip=""
    local ip_services=(
        "https://api.ipify.org"
        "https://ifconfig.me"
        "https://icanhazip.com"
        "https://ident.me"
    )
    
    for service in "${ip_services[@]}"; do
        ip=$(curl -s --max-time 5 "$service" 2>/dev/null || true)
        if [[ -n "$ip" ]] && [[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "$ip"
            return 0
        fi
    done
    
    error_exit "Não foi possível detectar o IP público"
}

# Função para verificar portas em uso
check_port_availability() {
    local port=$1
    if ss -tuln | grep -q ":$port "; then
        print_warning "Porta $port já está em uso"
        return 1
    fi
    return 0
}

# Função para configurar firewall
configure_firewall() {
    local port=$1
    local protocol=$2
    
    # Para sistemas com firewalld
    if systemctl is-active --quiet firewalld; then
        print_warning "Configurando firewalld..."
        firewall-cmd --permanent --add-port="${port}/${protocol}" &>/dev/null || true
        firewall-cmd --permanent --add-masquerade &>/dev/null || true
        firewall-cmd --reload &>/dev/null || true
        print_success "Firewalld configurado"
    fi
    
    # Para sistemas com ufw
    if command -v ufw &> /dev/null && ufw status | grep -q "Status: active"; then
        print_warning "Configurando UFW..."
        ufw allow "${port}/${protocol}" &>/dev/null || true
        print_success "UFW configurado"
    fi
}

# Função principal de instalação
install_openvpn() {
    local public_ip
    public_ip=$(get_public_ip)
    
    print_success "IP público detectado: $public_ip"
    
    # Baixa o script de instalação
    print_warning "Baixando script de instalação do OpenVPN..."
    if ! wget -O openvpn-install.sh "$OPENVPN_SCRIPT_URL" &>/dev/null; then
        error_exit "Falha ao baixar o script de instalação"
    fi
    
    chmod +x openvpn-install.sh
    
    # Define variáveis de ambiente para instalação não-interativa
    export AUTO_INSTALL=y
    export ENDPOINT="$public_ip"
    export IPV6_SUPPORT=n
    export PORT_CHOICE=1  # Porta padrão 1194
    export PORT=1194      # Especifica explicitamente a porta
    export PROTOCOL_CHOICE=2  # TCP
    export PROTOCOL=tcp   # Especifica explicitamente o protocolo
    export DNS=1          # DNS do sistema
    export COMPRESSION_ENABLED=n
    export CUSTOMIZE_ENC=n
    export CLIENT="$DEFAULT_CLIENT_NAME"
    export PASS=1         # Sem senha
    
    print_warning "Executando instalação do OpenVPN..."
    print_warning "Isso pode levar alguns minutos..."
    
    # Executa o script e captura a saída
    if ./openvpn-install.sh &>> "$LOG_FILE"; then
        print_success "Script de instalação executado com sucesso"
    else
        error_exit "Falha na execução do script de instalação"
    fi
    
    # Configura o firewall
    configure_firewall 1194 tcp
}

# Função para verificar a instalação
verify_installation() {
    local client_config="/root/${DEFAULT_CLIENT_NAME}.ovpn"
    local errors=0
    
    print_warning "Verificando instalação..."
    
    # Verifica se o serviço está rodando
    if systemctl is-active --quiet openvpn-server@server; then
        print_success "Serviço OpenVPN está ativo"
    else
        print_error "Serviço OpenVPN não está ativo"
        ((errors++))
    fi
    
    # Verifica se o arquivo de configuração do cliente existe
    if [[ -f "$client_config" ]]; then
        print_success "Arquivo de configuração do cliente encontrado: $client_config"
        
        # Cria cópia com nome mais descritivo
        local descriptive_name="/root/vpn-${public_ip}-$(date +%Y%m%d).ovpn"
        cp "$client_config" "$descriptive_name"
        print_success "Cópia criada: $descriptive_name"
    else
        print_error "Arquivo de configuração do cliente não encontrado"
        ((errors++))
    fi
    
    # Verifica interface tun
    if ip link show tun0 &>/dev/null; then
        print_success "Interface tun0 está ativa"
    else
        print_warning "Interface tun0 não encontrada (pode ser normal)"
    fi
    
    return $errors
}

# Função para exibir informações de conexão
show_connection_info() {
    echo
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                   INSTALAÇÃO CONCLUÍDA                        ║"
    echo "╠════════════════════════════════════════════════════════════════╣"
    echo "║ Servidor VPN:     $public_ip:1194                             ║"
    echo "║ Protocolo:        TCP                                         ║"
    echo "║ DNS:              DNS da VPS                                  ║"
    echo "║ Arquivo cliente:  /root/${DEFAULT_CLIENT_NAME}.ovpn           ║"
    echo "╠════════════════════════════════════════════════════════════════╣"
    echo "║ PRÓXIMOS PASSOS:                                              ║"
    echo "║ 1. Baixe o arquivo .ovpn para seu dispositivo                ║"
    echo "║ 2. Importe no seu cliente OpenVPN                            ║"
    echo "║ 3. Conecte-se à VPN                                          ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo
    echo "Log completo disponível em: $LOG_FILE"
}

# Função de limpeza
cleanup() {
    if [[ -f openvpn-install.sh ]]; then
        rm -f openvpn-install.sh
    fi
}

# Trap para limpeza em caso de erro
trap cleanup EXIT

# ============= EXECUÇÃO PRINCIPAL =============

main() {
    # Verifica se está rodando como root
    if [[ $EUID -ne 0 ]]; then
        error_exit "Este script deve ser executado como root"
    fi
    
    # Cria arquivo de log
    touch "$LOG_FILE"
    log "Iniciando instalação do OpenVPN v${SCRIPT_VERSION}"
    
    # Muda para o diretório do script
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
    cd "$SCRIPT_DIR" || error_exit "Falha ao mudar para o diretório: $SCRIPT_DIR"
    
    # Executa verificações e instalação
    print_warning "Iniciando instalação automatizada do OpenVPN..."
    check_requirements
    detect_os
    
    # Obtém IP público antes da instalação
    public_ip=$(get_public_ip)
    
    install_openvpn
    
    # Verifica a instalação
    if verify_installation; then
        show_connection_info
        print_success "Instalação concluída com sucesso!"
    else
        print_error "A instalação foi concluída mas alguns componentes podem não estar funcionando corretamente"
        print_warning "Verifique o log para mais detalhes: $LOG_FILE"
        exit 1
    fi
}

# Executa a função principal
main "$@"
