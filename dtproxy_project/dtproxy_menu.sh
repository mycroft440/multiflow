#!/bin/bash

# Menu para gerenciar o dtproxy
# Versão: 1.1 (Corrigida)

# Configurações
DTPROXY_DIR="/opt/dtproxy"
DTPROXY_EXEC="$DTPROXY_DIR/dtproxy_x86_64"

# Cores
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
NC="\033[0m"

# Função para verificar se dtproxy está instalado
check_dtproxy_installed() {
    if [[ ! -f "$DTPROXY_EXEC" ]]; then
        echo -e "${RED}[ERRO]${NC} dtproxy não está instalado em $DTPROXY_EXEC"
        echo "Execute o instalador principal primeiro."
        return 1
    fi
    return 0
}

# Função para verificar se uma porta está em uso
check_port_in_use() {
    local port="$1"
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Função principal do menu
main_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== DTPROXY MANAGER ===${NC}"
        echo "1. Iniciar dtproxy"
        echo "2. Gerenciar Portas"
        echo "3. Status do dtproxy"
        echo "4. Parar todos os dtproxy"
        echo "5. Remover dtproxy"
        echo "0. Voltar"
        echo ""
        read -p "Escolha uma opção: " choice

        case $choice in
            1) start_dtproxy_menu ;;
            2) port_management_menu ;;
            3) show_dtproxy_status ;;
            4) stop_all_dtproxy ;;
            5) remove_dtproxy ;;
            0) break ;;
            *)
                echo -e "${RED}Opção inválida!${NC}"
                read -p "Pressione Enter para continuar..." -n 1
                ;;
        esac
    done
}

# Função para iniciar dtproxy
start_dtproxy_menu() {
    clear
    echo -e "${BLUE}=== Iniciar dtproxy ===${NC}"
    
    if ! check_dtproxy_installed; then
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo ""
    read -p "Digite a porta para o dtproxy (padrão: 10000): " port_choice
    port_choice=${port_choice:-10000}
    
    if ! [[ "$port_choice" =~ ^[0-9]+$ ]] || [[ "$port_choice" -lt 1024 ]] || [[ "$port_choice" -gt 65535 ]]; then
        echo -e "${RED}[ERRO]${NC} Porta inválida. Use uma porta entre 1024 e 65535."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    if check_port_in_use "$port_choice"; then
        echo -e "${RED}[ERRO]${NC} Porta $port_choice já está em uso."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Iniciando dtproxy na porta $port_choice..."
    
    nohup "$DTPROXY_EXEC" --port "$port_choice" --http > /dev/null 2>&1 &
    local dtproxy_pid=$!
    
    sleep 2
    
    if kill -0 "$dtproxy_pid" 2>/dev/null; then
        echo -e "${GREEN}[SUCESSO]${NC} dtproxy iniciado na porta $port_choice (PID: $dtproxy_pid)"
    else
        echo -e "${RED}[ERRO]${NC} Falha ao iniciar dtproxy. Verifique se libssl1.1 está instalada."
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para gerenciar portas
port_management_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== Gerenciamento de Portas ===${NC}"
        echo "1. Adicionar nova porta"
        echo "2. Remover porta específica"
        echo "3. Listar portas ativas"
        echo "4. Voltar"
        echo ""
        read -p "Escolha uma opção: " port_choice

        case $port_choice in
            1) add_port ;;
            2) remove_port ;;
            3) list_active_ports ;;
            4) break ;;
            *)
                echo -e "${RED}Opção inválida!${NC}"
                read -p "Pressione Enter para continuar..." -n 1
                ;;
        esac
    done
}

# Função para adicionar porta
add_port() {
    clear
    echo -e "${BLUE}=== Adicionar Nova Porta ===${NC}"
    
    if ! check_dtproxy_installed; then
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    read -p "Digite a porta a ser adicionada: " port_to_add
    
    if ! [[ "$port_to_add" =~ ^[0-9]+$ ]] || [[ "$port_to_add" -lt 1024 ]] || [[ "$port_to_add" -gt 65535 ]]; then
        echo -e "${RED}[ERRO]${NC} Porta inválida."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    if pgrep -f "dtproxy.*--port $port_to_add" >/dev/null; then
        echo -e "${YELLOW}[AVISO]${NC} dtproxy já está rodando na porta $port_to_add."
    elif check_port_in_use "$port_to_add"; then
        echo -e "${RED}[ERRO]${NC} Porta $port_to_add já está em uso por outro processo."
    else
        echo -e "${YELLOW}[INFO]${NC} Iniciando dtproxy na porta $port_to_add..."
        nohup "$DTPROXY_EXEC" --port "$port_to_add" --http > /dev/null 2>&1 &
        sleep 2
        
        if pgrep -f "dtproxy.*--port $port_to_add" >/dev/null; then
            echo -e "${GREEN}[SUCESSO]${NC} dtproxy iniciado na porta $port_to_add."
        else
            echo -e "${RED}[ERRO]${NC} Falha ao iniciar dtproxy na porta $port_to_add."
        fi
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para remover porta
remove_port() {
    clear
    echo -e "${BLUE}=== Remover Porta Específica ===${NC}"
    
    echo "Portas ativas do dtproxy:"
    local active_ports=$(pgrep -f "dtproxy" | xargs -I {} ps -p {} -o args --no-headers | grep -o -- \"--port [0-9]*\" | awk \'{print $2}\' | sort -n)
    
    if [[ -z "$active_ports" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Nenhum dtproxy está rodando."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo "$active_ports" | nl -w2 -s\". \"\
    echo ""
    
    read -p "Digite a porta a ser removida: " port_to_remove
    
    if [[ -z "$port_to_remove" ]]; then
        echo -e "${RED}[ERRO]${NC} Porta não pode estar vazia."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    local pids=$(pgrep -f "dtproxy.*--port $port_to_remove")
    if [[ -n "$pids" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Parando dtproxy na porta $port_to_remove..."
        echo "$pids" | xargs kill
        sleep 1
        
        if ! pgrep -f "dtproxy.*--port $port_to_remove" >/dev/null; then
            echo -e "${GREEN}[SUCESSO]${NC} dtproxy na porta $port_to_remove foi parado."
        else
            echo -e "${RED}[ERRO]${NC} Falha ao parar dtproxy na porta $port_to_remove."
        fi
    else
        echo -e "${YELLOW}[AVISO]${NC} Nenhum dtproxy encontrado na porta $port_to_remove."
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para listar portas ativas
list_active_ports() {
    clear
    echo -e "${BLUE}=== Portas Ativas do dtproxy ===${NC}"
    
    local dtproxy_processes=$(pgrep -f "dtproxy" | xargs -I {} ps -p {} -o pid,args --no-headers 2>/dev/null)
    
    if [[ -z "$dtproxy_processes" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Nenhum processo dtproxy está rodando."
    else
        echo -e "${GREEN}Processos dtproxy ativos:${NC}"
        printf "%-8s %-8s %s\\n" "PID" "PORTA" "COMANDO"
        printf "%-8s %-8s %s\\n" "---" "-----" "-------"
        
        while read -r line; do
            local pid=$(echo "$line" | awk \'{print $1}\' )
            local port=$(echo "$line" | grep -o -- \"--port [0-9]*\" | awk \'{print $2}\' )
            local cmd=$(echo "$line" | awk \'{$1=""; print $0}\' | sed \'s/^ *//\')
            
            if [[ -n "$port" ]]; then
                printf "%-8s %-8s %s\\n" "$pid" "$port" "$cmd"
            fi
        done <<< "$dtproxy_processes"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para mostrar status do dtproxy
show_dtproxy_status() {
    clear
    echo -e "${BLUE}=== Status do dtproxy ===${NC}"
    
    if ! check_dtproxy_installed; then
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${GREEN}Executável:${NC} $DTPROXY_EXEC"
    
    if [[ -x "$DTPROXY_EXEC" ]]; then
        echo -e "${GREEN}Status:${NC} Instalado e executável"
    else
        echo -e "${RED}Status:${NC} Não executável"
    fi
    
    echo ""
    list_active_ports
}

# Função para parar todos os dtproxy
stop_all_dtproxy() {
    clear
    echo -e "${BLUE}=== Parar Todos os dtproxy ===${NC}"
    
    local pids=$(pgrep -f "dtproxy")
    if [[ -n "$pids" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Parando todos os processos dtproxy..."
        echo "$pids" | xargs kill
        sleep 2
        
        local remaining=$(pgrep -f "dtproxy")
        if [[ -z "$remaining" ]]; then
            echo -e "${GREEN}[SUCESSO]${NC} Todos os processos dtproxy foram parados."
        else
            echo -e "${YELLOW}[AVISO]${NC} Alguns processos ainda estão rodando. Tentando kill -9..."
            echo "$remaining" | xargs kill -9
            echo -e "${GREEN}[SUCESSO]${NC} Processos forçadamente terminados."
        fi
    else
        echo -e "${YELLOW}[INFO]${NC} Nenhum processo dtproxy está rodando."
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para remover dtproxy
remove_dtproxy() {
    clear
    echo -e "${BLUE}=== Remover dtproxy ===${NC}"
    
    echo -e "${RED}ATENÇÃO:${NC} Esta ação irá:"
    echo "- Parar todos os processos dtproxy"
    echo "- Remover o diretório $DTPROXY_DIR"
    echo "- Remover o serviço systemd (se existir)"
    echo ""
    
    read -p "Deseja continuar? (s/N): " confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        echo "Operação cancelada."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Parando todos os processos dtproxy..."
    pkill -f "dtproxy" 2>/dev/null || true
    
    echo -e "${YELLOW}[INFO]${NC} Parando e removendo serviço systemd..."
    systemctl stop dtproxy 2>/dev/null || true
    systemctl disable dtproxy 2>/dev/null || true
    rm -f /etc/systemd/system/dtproxy.service
    systemctl daemon-reload 2>/dev/null || true
    
    echo -e "${YELLOW}[INFO]${NC} Removendo diretório $DTPROXY_DIR..."
    rm -rf "$DTPROXY_DIR"
    
    echo -e "${GREEN}[SUCESSO]${NC} dtproxy removido completamente."
    read -p "Pressione Enter para continuar..." -n 1
}

# --- Funções para o menu dtproxy ---
install_dtproxy() {
    clear
    echo -e "${BLUE}=== Instalar dtproxy ===${NC}"
    
    if [[ -f "$DTPROXY_EXEC" ]]; then
        echo -e "${YELLOW}[AVISO]${NC} dtproxy já parece estar instalado."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Instalando dtproxy..."
    
    # Verificar se os arquivos do dtproxy existem
    local dtproxy_source_dir="$(dirname "${BASH_SOURCE[0]}")"
    if [[ ! -d "$dtproxy_source_dir" ]]; then
        echo -e "${RED}[ERRO]${NC} Diretório dtproxy_project não encontrado."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Criando diretório de instalação: $DTPROXY_DIR..."
    mkdir -p "$DTPROXY_DIR"
    
    echo -e "${YELLOW}[INFO]${NC} Copiando executável para $DTPROXY_DIR..."
    cp "$dtproxy_source_dir/dtproxy_x86_64" "$DTPROXY_EXEC"
    chmod +x "$DTPROXY_EXEC"
    
    echo -e "${GREEN}[SUCESSO]${NC} dtproxy instalado com sucesso."
    read -p "Pressione Enter para continuar..." -n 1
}

alter_dtproxy_port() {
    clear
    echo -e "${BLUE}=== Alterar Porta dtproxy ===${NC}"
    
    if ! check_dtproxy_installed; then
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo "Portas ativas do dtproxy:"
    local active_ports=$(pgrep -f "dtproxy" | xargs -I {} ps -p {} -o args --no-headers | grep -o -- \"--port [0-9]*\" | awk \'{print $2}\' | sort -n)
    
    if [[ -z "$active_ports" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Nenhum dtproxy está rodando."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo "$active_ports" | nl -w2 -s\". \"\
    echo ""
    
    read -p "Digite a porta atual do dtproxy que deseja alterar: " current_port
    
    if [[ -z "$current_port" ]]; then
        echo -e "${RED}[ERRO]${NC} Porta não pode estar vazia."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    if ! pgrep -f "dtproxy.*--port $current_port" >/dev/null; then
        echo -e "${RED}[ERRO]${NC} Nenhum dtproxy encontrado na porta $current_port."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    read -p "Digite a nova porta para o dtproxy: " new_port
    
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [[ "$new_port" -lt 1024 ]] || [[ "$new_port" -gt 65535 ]]; then
        echo -e "${RED}[ERRO]${NC} Porta inválida. Use uma porta entre 1024 e 65535."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    if check_port_in_use "$new_port"; then
        echo -e "${RED}[ERRO]${NC} Porta $new_port já está em uso."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Parando dtproxy na porta $current_port..."
    local pids=$(pgrep -f "dtproxy.*--port $current_port")
    echo "$pids" | xargs kill
    sleep 2
    
    echo -e "${YELLOW}[INFO]${NC} Iniciando dtproxy na nova porta $new_port..."
    nohup "$DTPROXY_EXEC" --port "$new_port" --http > /dev/null 2>&1 &
    sleep 2
    
    if pgrep -f "dtproxy.*--port $new_port" >/dev/null; then
        echo -e "${GREEN}[SUCESSO]${NC} dtproxy reiniciado com sucesso na porta $new_port."
    else
        echo -e "${RED}[ERRO]${NC} Falha ao reiniciar dtproxy na porta $new_port."
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

open_dtproxy_port() {
    clear
    echo -e "${BLUE}=== Abrir Porta dtproxy ===${NC}"
    
    if ! check_dtproxy_installed; then
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo "Portas ativas do dtproxy:"
    local active_ports=$(pgrep -f "dtproxy" | xargs -I {} ps -p {} -o args --no-headers | grep -o -- \"--port [0-9]*\" | awk \'{print $2}\' | sort -n)
    
    if [[ -z "$active_ports" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Nenhum dtproxy está rodando."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo "$active_ports" | nl -w2 -s\". \"\
    echo ""
    
    read -p "Digite a porta do dtproxy que deseja abrir no firewall: " port
    
    if [[ -z "$port" ]]; then
        echo -e "${RED}[ERRO]${NC} Porta não pode estar vazia."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    if ! pgrep -f "dtproxy.*--port $port" >/dev/null; then
        echo -e "${RED}[ERRO]${NC} Nenhum dtproxy encontrado na porta $port."
        read -p "Pressione Enter para continuar..." -n 1
        return
    fi
    
    echo -e "${YELLOW}[INFO]${NC} Abrindo porta $port no firewall (UFW)..."
    
    # Verificar se UFW está instalado
    if ! command -v ufw &> /dev/null; then
        echo -e "${YELLOW}[AVISO]${NC} UFW não está instalado. Instalando..."
        sudo apt update && sudo apt install -y ufw
    fi
    
    # Abrir a porta no UFW
    sudo ufw allow $port/tcp
    
    # Verificar se a regra foi adicionada
    if sudo ufw status | grep -q "$port/tcp"; then
        echo -e "${GREEN}[SUCESSO]${NC} Porta $port aberta no firewall."
    else
        echo -e "${YELLOW}[AVISO]${NC} Não foi possível confirmar se a porta foi aberta. Verifique manualmente com \"sudo ufw status\"."
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

dtproxy_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== Gerenciar dtproxy ===${NC}"
        echo "1. Instalar dtproxy"
        echo "2. Alterar Porta dtproxy"
        echo "3. Abrir Porta dtproxy"
        echo "4. Remover dtproxy"
        echo "0. Voltar ao Menu Anterior"
        echo ""
        read -p "Escolha uma opção: " dtproxy_choice

        case $dtproxy_choice in
            1) install_dtproxy ;;
            2) alter_dtproxy_port ;;
            3) open_dtproxy_port ;;
            4) remove_dtproxy ;;
            0) break ;;
            *)
                echo -e "${RED}Opção inválida!${NC}"
                read -p "Pressione Enter para continuar..." -n 1
                ;;
        esac
    done
}

# Inicia o menu principal
main_menu


