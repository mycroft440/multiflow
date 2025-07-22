#!/bin/bash

# Script de Gerenciamento de Usuários SSH
# Versão: 1.0
# Autor: MultiFlow Team

# Função para criar usuário SSH
create_ssh_user() {
    clear
    echo "\n--- Criar Usuário SSH ---"
    
    # Solicitar nome do usuário
    while true; do
        read -p "Digite o nome do usuário: " username
        if [[ -z "$username" ]]; then
            echo "Nome do usuário não pode estar vazio."
            continue
        fi
        
        # Verificar se o usuário já existe
        if id "$username" &>/dev/null; then
            echo "Usuário '$username' já existe."
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
            echo "Senha não pode estar vazia."
            continue
        fi
        
        read -s -p "Confirme a senha: " password_confirm
        echo
        if [[ "$password" != "$password_confirm" ]]; then
            echo "Senhas não coincidem. Tente novamente."
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
    echo "[INFO] Criando usuário '$username'..."
    
    if ! sudo useradd -m -s /bin/bash "$username"; then
        echo "[ERRO] Falha ao criar usuário '$username'."
        return 1
    fi
    
    # Definir senha
    echo "$username:$password" | sudo chpasswd
    if [[ $? -ne 0 ]]; then
        echo "[ERRO] Falha ao definir senha para '$username'."
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
            echo "[INFO] Data de expiração definida para: $expiry_date"
        else
            echo "[AVISO] Data de expiração inválida. Usuário criado sem expiração."
        fi
    fi
    
    # Reiniciar serviço SSH para aplicar configurações
    sudo systemctl reload sshd
    
    echo "[SUCESSO] Usuário '$username' criado com sucesso!"
    echo "Detalhes:"
    echo "  - Nome: $username"
    echo "  - Limite de conexões: $connection_limit"
    if [[ -n "$expiry_date" ]]; then
        echo "  - Data de expiração: $expiry_date"
    else
        echo "  - Data de expiração: Sem expiração"
    fi
}

# Função para remover usuário SSH
remove_ssh_user() {
    clear
    echo "\n--- Remover Usuário SSH ---"
    
    # Listar usuários existentes (excluindo usuários do sistema)
    echo "Usuários SSH disponíveis:"
    local users=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' | grep -v "^ubuntu$" | sort)
    
    if [[ -z "$users" ]]; then
        echo "Nenhum usuário SSH encontrado."
        return
    fi
    
    echo "$users" | nl -w2 -s'. '
    echo
    
    read -p "Digite o nome do usuário a ser removido: " username
    
    if [[ -z "$username" ]]; then
        echo "Nome do usuário não pode estar vazio."
        return
    fi
    
    # Verificar se o usuário existe
    if ! id "$username" &>/dev/null; then
        echo "Usuário '$username' não existe."
        return
    fi
    
    # Verificar se não é um usuário do sistema
    local uid=$(id -u "$username")
    if [[ "$uid" -lt 1000 ]] || [[ "$username" == "ubuntu" ]]; then
        echo "Não é possível remover usuários do sistema."
        return
    fi
    
    # Confirmar remoção
    echo -n "Deseja realmente remover o usuário '$username'? (s/N): "
    read -r confirm
    if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
        echo "Operação cancelada."
        return
    fi
    
    # Matar processos do usuário
    echo "[INFO] Encerrando processos do usuário '$username'..."
    sudo pkill -u "$username" 2>/dev/null
    
    # Remover configurações SSH específicas do usuário
    if grep -q "Match User $username" /etc/ssh/sshd_config; then
        echo "[INFO] Removendo configurações SSH do usuário..."
        sudo sed -i "/Match User $username/,+2d" /etc/ssh/sshd_config
        sudo systemctl reload sshd
    fi
    
    # Remover usuário e diretório home
    if sudo userdel -r "$username" 2>/dev/null; then
        echo "[SUCESSO] Usuário '$username' removido com sucesso!"
    else
        echo "[ERRO] Falha ao remover usuário '$username'."
        return 1
    fi
}

# Função para listar usuários SSH
list_ssh_users() {
    clear
    echo "\n--- Lista de Usuários SSH ---"
    
    # Obter usuários (UID >= 1000 e < 65534, excluindo ubuntu)
    local users=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1":"$3":"$5":"$6}' | grep -v "^ubuntu:" | sort)
    
    if [[ -z "$users" ]]; then
        echo "Nenhum usuário SSH encontrado."
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
    echo "--- Conexões SSH Ativas ---"
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
}

