#!/bin/bash

# Cores para saída de console
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para exibir mensagens coloridas
function log_info {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function log_warn {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

function log_error {
    echo -e "${RED}[ERRO]${NC} $1" >&2
}

# Função para exibir mensagens de erro e sair
function error_exit {
    log_error "$1"
    exit 1
}

# Verificar se está rodando como root
if [[ $EUID -ne 0 ]]; then
    error_exit "Este script precisa ser executado como root (sudo)."
fi

# Verificar se o sistema é compatível
if [ ! -f /etc/os-release ]; then
    error_exit "Sistema operacional não reconhecido."
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" && "$ID_LIKE" != *"debian"* ]]; then
    log_warn "Este script foi testado apenas em sistemas baseados em Debian/Ubuntu."
    read -p "Deseja continuar mesmo assim? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

# Definir o diretório de instalação
INSTALL_DIR="/opt/multiflow"
BACKUP_DIR="/opt/multiflow.bak.$(date +%Y%m%d%H%M%S)"

# Verificar e criar backup se uma instalação anterior existir
if [ -d "$INSTALL_DIR" ]; then
    log_warn "Instalação anterior detectada em $INSTALL_DIR"
    read -p "Deseja fazer backup antes de substituir? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        log_info "Criando backup em $BACKUP_DIR..."
        cp -r "$INSTALL_DIR" "$BACKUP_DIR" || error_exit "Falha ao criar backup."
        log_info "Backup concluído com sucesso."
    fi
    
    log_info "Removendo instalação anterior em $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR" || error_exit "Falha ao remover instalação anterior."
fi

# Atualizar pacotes e instalar dependências
log_info "Atualizando lista de pacotes..."
apt update || error_exit "Falha ao atualizar pacotes. Verifique sua conexão com a internet."

log_info "Instalando dependências principais..."
apt install -y git python3 python3-pip || error_exit "Falha ao instalar git, python3 ou python3-pip."

log_info "Instalando dependências Python..."
pip3 install psutil || error_exit "Falha ao instalar psutil."

log_info "Instalando dependências C++ para o socks5_server..."
apt install -y g++ libboost-all-dev libssh2-1-dev sshpass || error_exit "Falha ao instalar dependências C++."

# Verificar se o diretório atual já contém os arquivos do projeto
if [ -f "./multiflow.py" ] && [ -f "./src/socks5_server.cpp" ]; then
    log_info "Arquivos do projeto encontrados no diretório atual."
    read -p "Deseja usar os arquivos locais em vez de clonar do GitHub? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        log_info "Criando diretório de instalação..."
        mkdir -p "$INSTALL_DIR" || error_exit "Falha ao criar diretório de instalação."
        
        log_info "Copiando arquivos locais para $INSTALL_DIR..."
        cp -r ./* "$INSTALL_DIR/" || error_exit "Falha ao copiar arquivos."
        
        USE_LOCAL_FILES=true
    fi
fi

# Clonar o repositório se não estiver usando arquivos locais
if [ "$USE_LOCAL_FILES" != true ]; then
    REPO_URL="https://github.com/mycroft440/multiflow.git"
    log_info "Clonando o repositório $REPO_URL para $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR" || error_exit "Falha ao clonar o repositório. Verifique sua conexão com a internet."
fi

# Verificar se o arquivo já tem shebang, caso contrário, adicionar
if ! grep -q "^#!/usr/bin/env python3" "$INSTALL_DIR/multiflow.py"; then
    log_info "Adicionando shebang ao arquivo Python..."
    sed -i '1s/^/#!/usr\/bin\/env python3\n/' "$INSTALL_DIR/multiflow.py"
fi

# Também adicionar shebang ao arquivo ssh_user_manager.py
if [ -f "$INSTALL_DIR/ssh_user_manager.py" ] && ! grep -q "^#!/usr/bin/env python3" "$INSTALL_DIR/ssh_user_manager.py"; then
    log_info "Adicionando shebang ao arquivo ssh_user_manager.py..."
    sed -i '1s/^/#!/usr\/bin\/env python3\n/' "$INSTALL_DIR/ssh_user_manager.py"
fi

# Dar permissões de execução aos scripts
log_info "Definindo permissões de execução para os scripts..."
chmod +x "$INSTALL_DIR/multiflow.py" || error_exit "Falha ao definir permissões de execução para multiflow.py."
if [ -f "$INSTALL_DIR/ssh_user_manager.py" ]; then
    chmod +x "$INSTALL_DIR/ssh_user_manager.py" || error_exit "Falha ao definir permissões de execução para ssh_user_manager.py."
fi

# Criar um link simbólico para facilitar a execução
log_info "Criando link simbólico para execução fácil..."
ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/multiflow || error_exit "Falha ao criar link simbólico."

# Compilar o socks5_server
log_info "Compilando socks5_server..."
cd "$INSTALL_DIR" || error_exit "Falha ao navegar para o diretório de instalação."

g++ -o "$INSTALL_DIR/socks5_server" "$INSTALL_DIR/src/socks5_server.cpp" \
    -lboost_system -lboost_log -lboost_thread -lpthread -lssh2 -std=c++14

# Verificar se a compilação foi bem-sucedida
if [ $? -ne 0 ]; then
    log_error "Falha ao compilar socks5_server. Verificando dependências..."
    
    # Verificações adicionais para identificar problemas comuns
    if ! command -v g++ &> /dev/null; then
        log_error "g++ não está instalado. Tente instalar novamente com: apt install g++"
    fi
    
    if ! ldconfig -p | grep libboost_system &> /dev/null; then
        log_error "libboost_system não foi encontrada. Tente instalar novamente com: apt install libboost-all-dev"
    fi
    
    if ! ldconfig -p | grep libssh2 &> /dev/null; then
        log_error "libssh2 não foi encontrada. Tente instalar novamente com: apt install libssh2-1-dev"
    fi
    
    error_exit "A compilação falhou. Verifique as mensagens de erro acima."
fi

# Adicionar informações sobre bibliotecas e caminho do Python
log_info "Verificando configuração do ambiente..."
python3_path=$(which python3)
log_info "Python3 encontrado em: $python3_path"

# Criar ou atualizar arquivo wrapper para garantir que o Python correto seja usado
cat > "$INSTALL_DIR/multiflow_wrapper.sh" << EOF
#!/bin/bash
$python3_path "$INSTALL_DIR/multiflow.py" "\$@"
EOF

chmod +x "$INSTALL_DIR/multiflow_wrapper.sh"
log_info "Criado wrapper em $INSTALL_DIR/multiflow_wrapper.sh"

# Atualizar o link simbólico para usar o wrapper
rm -f /usr/local/bin/multiflow
ln -sf "$INSTALL_DIR/multiflow_wrapper.sh" /usr/local/bin/multiflow
log_info "Link simbólico atualizado para usar o wrapper"

log_info "Instalação concluída com sucesso!"
log_info "Você pode executar o Multiflow digitando 'multiflow' no terminal."

# Perguntar se deseja iniciar o programa
read -p "Deseja iniciar o Multiflow agora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    log_info "Iniciando Multiflow..."
    bash "$INSTALL_DIR/multiflow_wrapper.sh"
fi
