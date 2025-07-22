#!/bin/bash

# Ferramentas de Otimização e Limpeza do Sistema
# Versão: 1.0
# Autor: MultiFlow Team

# Cores para a saída do terminal
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BLUE='\033[1;34m'
NC='\033[0m'

# Função para exibir barra de progresso
fun_bar() {
    local cmd="$1"
    (
        [[ -e $HOME/fim ]] && rm $HOME/fim
        ${cmd} >/dev/null 2>&1
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

# Função para limpeza básica do sistema
limpeza_basica() {
    clear
    echo -e "\E[44;1;37m         LIMPEZA BÁSICA DO SISTEMA         \E[0m"
    echo ""
    echo -e "${YELLOW}Esta função irá:${NC}"
    echo -e "• Limpar cache de pacotes"
    echo -e "• Remover pacotes órfãos"
    echo -e "• Limpar logs antigos"
    echo -e "• Limpar arquivos temporários"
    echo ""
    read -p "Deseja continuar? (s/N): " confirm
    
    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
        echo ""
        echo -e "${GREEN}Iniciando limpeza básica...${NC}"
        
        limpeza_cmd() {
            # Limpar cache de pacotes
            apt-get clean
            apt-get autoclean
            apt-get autoremove -y
            
            # Limpar logs antigos (manter apenas últimos 7 dias)
            journalctl --vacuum-time=7d
            
            # Limpar arquivos temporários
            find /tmp -type f -atime +7 -delete 2>/dev/null
            find /var/tmp -type f -atime +7 -delete 2>/dev/null
            
            # Limpar cache de usuário
            find /home -name ".cache" -type d -exec rm -rf {}/* \; 2>/dev/null
            
            # Limpar thumbnails antigos
            find /home -name ".thumbnails" -type d -exec rm -rf {}/* \; 2>/dev/null
        }
        
        fun_bar 'limpeza_cmd'
        echo ""
        echo -e "${GREEN}Limpeza básica concluída com sucesso!${NC}"
    else
        echo -e "${RED}Operação cancelada.${NC}"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para otimização de memória
otimizacao_memoria() {
    clear
    echo -e "\E[44;1;37m         OTIMIZAÇÃO DE MEMÓRIA         \E[0m"
    echo ""
    echo -e "${YELLOW}Esta função irá:${NC}"
    echo -e "• Limpar cache de memória"
    echo -e "• Otimizar swap"
    echo -e "• Configurar parâmetros de kernel"
    echo ""
    read -p "Deseja continuar? (s/N): " confirm
    
    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
        echo ""
        echo -e "${GREEN}Iniciando otimização de memória...${NC}"
        
        memoria_cmd() {
            # Limpar cache de memória
            sync
            echo 3 > /proc/sys/vm/drop_caches
            
            # Otimizar swap
            swapoff -a && swapon -a
            
            # Configurar parâmetros de kernel para melhor performance
            echo 'vm.swappiness=10' >> /etc/sysctl.conf
            echo 'vm.vfs_cache_pressure=50' >> /etc/sysctl.conf
            echo 'vm.dirty_background_ratio=5' >> /etc/sysctl.conf
            echo 'vm.dirty_ratio=10' >> /etc/sysctl.conf
            
            # Aplicar configurações
            sysctl -p
        }
        
        fun_bar 'memoria_cmd'
        echo ""
        echo -e "${GREEN}Otimização de memória concluída!${NC}"
    else
        echo -e "${RED}Operação cancelada.${NC}"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para otimização de rede
otimizacao_rede() {
    clear
    echo -e "\E[44;1;37m         OTIMIZAÇÃO DE REDE         \E[0m"
    echo ""
    echo -e "${YELLOW}Esta função irá:${NC}"
    echo -e "• Otimizar buffers TCP"
    echo -e "• Configurar parâmetros de rede"
    echo -e "• Melhorar throughput"
    echo ""
    read -p "Deseja continuar? (s/N): " confirm
    
    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
        echo ""
        echo -e "${GREEN}Iniciando otimização de rede...${NC}"
        
        rede_cmd() {
            # Otimizações de rede
            echo 'net.core.rmem_max=16777216' >> /etc/sysctl.conf
            echo 'net.core.wmem_max=16777216' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_rmem=4096 87380 16777216' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_wmem=4096 87380 16777216' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_window_scaling=1' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_timestamps=1' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_sack=1' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_no_metrics_save=1' >> /etc/sysctl.conf
            echo 'net.core.netdev_max_backlog=250000' >> /etc/sysctl.conf
            echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf
            
            # Aplicar configurações
            sysctl -p
        }
        
        fun_bar 'rede_cmd'
        echo ""
        echo -e "${GREEN}Otimização de rede concluída!${NC}"
    else
        echo -e "${RED}Operação cancelada.${NC}"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para monitoramento do sistema
monitoramento_sistema() {
    clear
    echo -e "\E[44;1;37m         MONITORAMENTO DO SISTEMA         \E[0m"
    echo ""
    
    # Informações de CPU
    echo -e "${BLUE}=== CPU ===${NC}"
    echo -e "Modelo: $(cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2 | xargs)"
    echo -e "Cores: $(nproc)"
    echo -e "Uso atual: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
    echo ""
    
    # Informações de Memória
    echo -e "${BLUE}=== MEMÓRIA ===${NC}"
    free -h | grep -E "Mem|Swap"
    echo ""
    
    # Informações de Disco
    echo -e "${BLUE}=== DISCO ===${NC}"
    df -h | grep -E "^/dev"
    echo ""
    
    # Informações de Rede
    echo -e "${BLUE}=== REDE ===${NC}"
    echo -e "Interfaces ativas:"
    ip -o link show | awk -F': ' '{print $2}' | grep -v lo
    echo ""
    
    # Processos que mais consomem CPU
    echo -e "${BLUE}=== TOP 5 PROCESSOS (CPU) ===${NC}"
    ps aux --sort=-%cpu | head -6
    echo ""
    
    # Processos que mais consomem Memória
    echo -e "${BLUE}=== TOP 5 PROCESSOS (MEMÓRIA) ===${NC}"
    ps aux --sort=-%mem | head -6
    echo ""
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para limpeza avançada
limpeza_avancada() {
    clear
    echo -e "\E[44;1;37m         LIMPEZA AVANÇADA DO SISTEMA         \E[0m"
    echo ""
    echo -e "${RED}ATENÇÃO: Esta é uma limpeza avançada!${NC}"
    echo -e "${YELLOW}Esta função irá:${NC}"
    echo -e "• Limpar todos os logs do sistema"
    echo -e "• Remover kernels antigos"
    echo -e "• Limpar cache de aplicações"
    echo -e "• Otimizar banco de dados de pacotes"
    echo ""
    read -p "Tem certeza que deseja continuar? (s/N): " confirm
    
    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
        echo ""
        echo -e "${GREEN}Iniciando limpeza avançada...${NC}"
        
        limpeza_avancada_cmd() {
            # Limpar todos os logs
            journalctl --vacuum-size=50M
            find /var/log -name "*.log" -exec truncate -s 0 {} \;
            
            # Remover kernels antigos (manter apenas os 2 mais recentes)
            apt-get autoremove --purge -y
            
            # Limpar cache de snap
            snap list --all | awk '/disabled/{print $1, $3}' | while read snapname revision; do
                snap remove "$snapname" --revision="$revision"
            done 2>/dev/null
            
            # Limpar cache de flatpak
            flatpak uninstall --unused -y 2>/dev/null
            
            # Otimizar banco de dados de pacotes
            apt-get update
            dpkg --configure -a
            
            # Limpar arquivos de configuração órfãos
            dpkg -l | grep '^rc' | awk '{print $2}' | xargs dpkg --purge 2>/dev/null
        }
        
        fun_bar 'limpeza_avancada_cmd'
        echo ""
        echo -e "${GREEN}Limpeza avançada concluída!${NC}"
    else
        echo -e "${RED}Operação cancelada.${NC}"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Função para backup de configurações
backup_configuracoes() {
    clear
    echo -e "\E[44;1;37m         BACKUP DE CONFIGURAÇÕES         \E[0m"
    echo ""
    
    local backup_dir="/opt/multiflow_backup_$(date +%Y%m%d_%H%M%S)"
    
    echo -e "${YELLOW}Esta função irá criar backup de:${NC}"
    echo -e "• Configurações de rede"
    echo -e "• Configurações SSH"
    echo -e "• Configurações do sistema"
    echo -e "• Lista de pacotes instalados"
    echo ""
    echo -e "Backup será salvo em: ${GREEN}$backup_dir${NC}"
    echo ""
    read -p "Deseja continuar? (s/N): " confirm
    
    if [[ "$confirm" = "s" || "$confirm" = "S" ]]; then
        echo ""
        echo -e "${GREEN}Criando backup...${NC}"
        
        backup_cmd() {
            mkdir -p "$backup_dir"
            
            # Backup de configurações de rede
            cp -r /etc/netplan "$backup_dir/" 2>/dev/null
            cp /etc/hosts "$backup_dir/" 2>/dev/null
            cp /etc/resolv.conf "$backup_dir/" 2>/dev/null
            
            # Backup de configurações SSH
            cp -r /etc/ssh "$backup_dir/" 2>/dev/null
            
            # Backup de configurações do sistema
            cp /etc/sysctl.conf "$backup_dir/" 2>/dev/null
            cp /etc/fstab "$backup_dir/" 2>/dev/null
            
            # Lista de pacotes instalados
            dpkg --get-selections > "$backup_dir/pacotes_instalados.txt"
            snap list > "$backup_dir/snap_instalados.txt" 2>/dev/null
            
            # Criar arquivo de informações
            echo "Backup criado em: $(date)" > "$backup_dir/info_backup.txt"
            echo "Sistema: $(lsb_release -d | cut -f2)" >> "$backup_dir/info_backup.txt"
            echo "Kernel: $(uname -r)" >> "$backup_dir/info_backup.txt"
        }
        
        fun_bar 'backup_cmd'
        echo ""
        echo -e "${GREEN}Backup criado com sucesso em: $backup_dir${NC}"
    else
        echo -e "${RED}Operação cancelada.${NC}"
    fi
    
    read -p "Pressione Enter para continuar..." -n 1
}

# Menu principal
main_menu() {
    while true; do
        clear
        echo -e "\E[44;1;37m          FERRAMENTAS DE OTIMIZAÇÃO          \E[0m"
        echo ""
        echo -e "${RED}[${YELLOW}1${RED}] ${NC}• ${YELLOW}Limpeza Básica do Sistema${NC}"
        echo -e "${RED}[${YELLOW}2${RED}] ${NC}• ${YELLOW}Otimização de Memória${NC}"
        echo -e "${RED}[${YELLOW}3${RED}] ${NC}• ${YELLOW}Otimização de Rede${NC}"
        echo -e "${RED}[${YELLOW}4${RED}] ${NC}• ${YELLOW}Monitoramento do Sistema${NC}"
        echo -e "${RED}[${YELLOW}5${RED}] ${NC}• ${YELLOW}Limpeza Avançada${NC}"
        echo -e "${RED}[${YELLOW}6${RED}] ${NC}• ${YELLOW}Backup de Configurações${NC}"
        echo -e "${RED}[${YELLOW}0${RED}] ${NC}• ${YELLOW}Voltar${NC}"
        echo ""
        echo -ne "${GREEN}Escolha uma opção${NC}: "
        read -r option
        
        case $option in
            1) limpeza_basica ;;
            2) otimizacao_memoria ;;
            3) otimizacao_rede ;;
            4) monitoramento_sistema ;;
            5) limpeza_avancada ;;
            6) backup_configuracoes ;;
            0) break ;;
            *)
                echo -e "${RED}Opção inválida! Pressione qualquer tecla para continuar...${NC}"
                read -r -n 1
                ;;
        esac
    done
}

# Verificar se está sendo executado como root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Este script precisa ser executado como root (sudo)${NC}"
    exit 1
fi

# Iniciar o menu principal
main_menu

