```bash
#!/bin/bash

# Script de Gerenciamento de Usuários SSH
# Versão: 1.0
# Autor: MultiFlow Team

# Cores para a saída do terminal
readonly GREEN="\033[1;32m"
readonly YELLOW="\033[1;33m"
readonly RED="\033[1;31m"
readonly BLUE="\033[1;34m"
readonly NC="\033[0m"

# Função para exibir mensagens de erro e sair
error_exit() {
    echo -e "${RED}[ERRO]${NC} $1" >&2
    exit 1
}

# Função para exibir mensagens de informação
info_msg() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Função para exibir mensagens de sucesso
success_msg() {
    echo -e "${GREEN}[SUCESSO]${NC} $1"
}

# Função para exibir mensagens de aviso
warning_msg() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

# Função para criar usuário SSH
create_ssh_user() {
    clear
    echo -e "${BLUE}--- Criar Usuário SSH ---${NC}"
    
    # Solicitar nome do usuário
    while true; do
        read -p "Digite o nome do usuário: " username
        if [[ -z "$username" ]]; then
            warning_msg "Nome do usuário não pode estar vazio."
            continue
        fi
        
        # Verificar se o usuário já existe
        if id "$username" &>/dev/null; then
            warning_msg "Usuário '$username' já existe."
            read -p "Deseja continuar com outro nome? (s/n): " continue_choice
            if [[ "$continue_choice" != "s" && "$continue_choice" != "S" ]]; then
                return
            fi
            continue
        fi
        break
    done
    
    # Solicitar senha
    while true; do
        read -s -p "Digite a senha para o usuário: " password
        echo
        if [[ -z "$password" ]]; then
            warning_msg "Senha não pode estar vazia."
            continue
        fi
        
        read -s -p "Confirme a senha: " password_confirm
        echo
        if [[ "$password" != "$password_confirm" ]]; then
            warning_msg "Senhas não coincidem. Tente novamente."
            continue
        fi
        break
    done
    
    # Solicitar limite de conexões (opcional)
    read -p "Digite o limite de conexões simultâneas (padrão: 2): " connection_limit
    connection_limit=${connection_limit:-2}
    
    # Solicitar data de expiração (opcional)
    read -p "Digite a data de expiração (YYYY-MM-DD) ou pressione Enter para sem expiração: " expiry_date
    
    # Criar o usuário
    info_msg "Criando usuário '$username'..."
    
    if ! sudo useradd -m -s /bin/bash "$username"; then
        error_exit "Falha ao criar usuário '$username'."
    fi
    
    # Definir senha
    echo "$username:$password" | sudo chpasswd
    if [[ $? -ne 0 ]]; then
        error_exit "Falha ao definir senha para '$username'."
        sudo userdel -r "$username" 2>/dev/null
        return 1
    fi
    
    # Configurar limite de conexões SSH
    if [[ "$connection_limit" =~ ^[0-9]+$ ]] && [[ "$connection_limit" -gt 0 ]]; then
        echo "Match User $username" | sudo tee -a /etc/ssh/sshd_config > /dev/null
        echo "    MaxSessions $connection_limit" | sudo tee -a /etc/ssh/sshd_config > /dev/null
        echo "    MaxStartups $connection_limit" | sudo tee -a /etc/ssh/sshd_config > /dev/null
    fi
    
    # Configurar data de expiração
    if [[ -n "$expiry_date" ]]; then
        if date -d "$expiry_date" &>/dev/null; then
            sudo chage -E "$expiry_date" "$username"
            info_msg "Data de expiração definida para: $expiry_date"
        else
            warning_msg "Data de expiração inválida. Usuário criado sem expiração."
        fi
    fi
    
    # Reiniciar serviço SSH para aplicar configurações
    sudo systemctl reload sshd
    
    success_msg "Usuário '$username' criado com sucesso!"
    echo "Detalhes:"
    echo "  - Nome: $username"
    echo "  - Limite de conexões: $connection_limit"
    if [[ -n "$expiry_date" ]]; then
        echo "  - Data de expiração: $expiry_date"
    else
        echo "  - Data de expiração: Sem expiração"
    fi
    read -p "Pressione Enter para continuar..."
}

# Função para remover usuário SSH
remove_ssh_user() {
    clear
    echo -e "${BLUE}--- Remover Usuário SSH ---${NC}"
    
    # Listar usuários existentes (excluindo usuários do sistema)
    echo "Usuários SSH disponíveis:"
    local users=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' | grep -v "^ubuntu$" | sort)
    
    if [[ -z "$users" ]]; then
        warning_msg "Nenhum usuário SSH encontrado."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    echo "$users" | nl -w2 -s'. '
    echo
    
    read -p "Digite o nome do usuário a ser removido: " username
    
    if [[ -z "$username" ]]; then
        warning_msg "Nome do usuário não pode estar vazio."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    # Verificar se o usuário existe
    if ! id "$username" &>/dev/null; then
        warning_msg "Usuário '$username' não existe."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    # Verificar se não é um usuário do sistema
    local uid=$(id -u "$username")
    if [[ "$uid" -lt 1000 ]] || [[ "$username" == "ubuntu" ]]; then
        warning_msg "Não é possível remover usuários do sistema."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    # Confirmar remoção
    echo -n "Deseja realmente remover o usuário '$username'? (s/N): "
    read -r confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        warning_msg "Operação cancelada."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    # Matar processos do usuário
    info_msg "Encerrando processos do usuário '$username'..."
    sudo pkill -u "$username" 2>/dev/null
    
    # Remover configurações SSH específicas do usuário
    if grep -q "Match User $username" /etc/ssh/sshd_config; then
        info_msg "Removendo configurações SSH do usuário..."
        sudo sed -i "/Match User $username/,+2d" /etc/ssh/sshd_config
        sudo systemctl reload sshd
    fi
    
    # Remover usuário e diretório home
    if sudo userdel -r "$username" 2>/dev/null; then
        success_msg "Usuário '$username' removido com sucesso!"
    else
        error_exit "Falha ao remover usuário '$username'."
    fi
    read -p "Pressione Enter para continuar..."
}

# Função para listar usuários SSH
list_ssh_users() {
    clear
    echo -e "${BLUE}--- Lista de Usuários SSH ---${NC}"
    
    # Obter usuários (UID >= 1000 e < 65534, excluindo ubuntu)
    local users=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1":"$3":"$5":"$6}' | grep -v "^ubuntu:" | sort)
    
    if [[ -z "$users" ]]; then
        warning_msg "Nenhum usuário SSH encontrado."
        read -p "Pressione Enter para continuar..."
        return
    fi
    
    printf "%-15s %-8s %-20s %-30s %-15s\n" "USUÁRIO" "UID" "NOME COMPLETO" "DIRETÓRIO HOME" "STATUS"
    printf "%-15s %-8s %-20s %-30s %-15s\n" "-------" "---" "-------------" "---------------" "------"
    
    while IFS=':' read -r username uid fullname homedir; do
        # Verificar se o usuário está logado
        local status="Offline"
        if who | grep -q "^$username "; then
            status="Online"
        fi
        
        # Verificar expiração da conta
        local expiry=$(sudo chage -l "$username" 2>/dev/null | grep "Account expires" | cut -d: -f2 | xargs)
        if [[ "$expiry" != "never" ]] && [[ -n "$expiry" ]]; then
            local expiry_date=$(date -d "$expiry" +%Y-%m-%d 2>/dev/null)
            local current_date=$(date +%Y-%m-%d)
            if [[ "$expiry_date" < "$current_date" ]]; then
                status="Expirado"
            fi
        fi
        
        printf "%-15s %-8s %-20s %-30s %-15s\n" "$username" "$uid" "${fullname:-N/A}" "$homedir" "$status"
    done <<< "$users"
    
    echo
    echo "Total de usuários: $(echo "$users" | wc -l)"
    
    # Mostrar conexões SSH ativas
    echo
    echo -e "${BLUE}--- Conexões SSH Ativas ---${NC}"
    local active_connections=$(who | grep -E "pts/|tty" | wc -l)
    if [[ "$active_connections" -gt 0 ]]; then
        printf "%-15s %-10s %-15s %-20s\n" "USUÁRIO" "TERMINAL" "IP/HOST" "HORÁRIO"
        printf "%-15s %-10s %-15s %-20s\n" "-------" "--------" "-------" "--------"
        who | grep -E "pts/|tty" | while read -r user terminal datetime ip; do
            printf "%-15s %-10s %-15s %-20s\n" "$user" "$terminal" "${ip//[()]/}" "$datetime"
        done
    else
        echo "Nenhuma conexão SSH ativa."
    fi
    read -p "Pressione Enter para continuar..."
}

# Menu principal
main_menu() {
    while true; do
        clear
        echo -e "${BLUE}=== Gerenciador de Usuários SSH ===${NC}"
        echo "1. Criar Usuário SSH"
        echo "2. Remover Usuário SSH"
        echo "3. Listar Usuários SSH"
        echo "0. Voltar ao Menu Principal"
        echo ""
        read -p "Escolha uma opção: " choice
        case $choice in
            1) create_ssh_user ;;
            2) remove_ssh_user ;;
            3) list_ssh_users ;;
            0) break ;;
            *) 
                warning_msg "Opção inválida! Tente novamente."
                read -p "Pressione Enter para continuar..."
                ;;
        esac
    done
}

# Verificar se está sendo executado como root
if [[ $EUID -ne 0 ]]; then
    error_exit "Este script precisa ser executado como root (sudo)"
fi

# Iniciar o menu principal
main_menu
```
