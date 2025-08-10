#!/bin/bash

# ==============================================================================
# Script de Instalação para o MultiFlow Manager
#
# Este script prepara o ambiente para o MultiFlow Manager, instalando todas as
# dependências de sistema e de Python necessárias para todas as ferramentas.
# ==============================================================================

# --- Cores para a Saída ---
R='\033[1;31m'
G='\033[1;32m'
Y='\033[1;33m'
C='\033[1;36m'
W='\033[0m'

# --- Funções Auxiliares ---

# Imprime um cabeçalho formatado
print_header() {
    clear
    echo -e "${C}===============================================${W}"
    echo -e "${C}      Instalador do MultiFlow Manager      ${W}"
    echo -e "${C}===============================================${W}"
    echo
}

# Verifica se o script está sendo executado como root
check_root() {
    if [ "$EUID" -ne 0 ]; then
      echo -e "${R}Erro: Este script precisa ser executado como root.${W}"
      echo -e "${Y}Por favor, execute com: sudo bash install.sh${W}"
      exit 1
    fi
}

# Instala todas as dependências do sistema
install_system_deps() {
    echo -e "${Y}>>> Atualizando a lista de pacotes do sistema (apt-get update)...${W}"
    if ! apt-get update -y; then
        echo -e "${R}Falha ao atualizar a lista de pacotes. Verifique sua conexão e repositórios.${W}"
        exit 1
    fi
    
    echo -e "\\n${Y}>>> Instalando dependências essenciais...${W}"
    echo -e "    (python3, pip, git, build-essential, cmake, libssl-dev, gcc)"
    
    # Lista de pacotes a serem instalados
    local packages=(
        python3 
        python3-pip 
        git 
        build-essential 
        cmake 
        libssl-dev \
        gcc \
        libboost-all-dev \
        libcurl4-openssl-dev    )
    
    if ! apt-get install -y "${packages[@]}"; then
        echo -e "${R}Falha ao instalar pacotes do sistema. A instalação foi abortada.${W}"
        exit 1
    fi

    echo -e "\\n${Y}>>> Clonando o repositório multiflowpx...${W}"
    if [ ! -d "/root/multiflowpx" ]; then
        git clone https://github.com/mycroft440/multiflowpx.git /root/multiflowpx
    else
        echo -e "${Y}Repositório multiflowpx já existe em /root/multiflowpx. Pulando a clonagem.${W}"
    fi
}

# Instala as dependências de Python via pip
install_python_deps() {
    echo -e "\\n${Y}>>> Instalando pacotes Python com pip...${W}"
    echo -e "    (psutil)"
    
    if ! pip3 install --break-system-packages psutil; then
        echo -e "${R}Falha ao instalar pacotes Python. A instalação foi abortada.${W}"
        exit 1
    fi
}

# Define as permissões de execução para os scripts
set_permissions() {
    echo -e "\\n${Y}>>> Configurando permissões de execução para scripts...${W}"
    
    # Encontra todos os scripts .sh e os torna executáveis
    find . -type f -name "*.sh" -exec chmod +x {} \;
    
    echo -e "${G}Permissões configuradas.${W}"
}


# --- Função Principal ---
main() {
    print_header
    check_root

    echo -e "${G}Bem-vindo ao instalador do MultiFlow Manager!${W}"
    echo -e "${Y}Este script irá preparar o ambiente, instalando todas as dependências.${W}"
    echo -e "---------------------------------------------------------------------"
    
    install_system_deps
    install_python_deps
    set_permissions

    echo
    echo -e "${C}=====================================================================${W}"
    echo -e "${G}      Ambiente preparado com sucesso!      ${W}"
    echo -e "${C}=====================================================================${W}"
    echo -e "\\n${Y}Todos os pré-requisitos foram instalados.${W}"
    echo -e "${Y}Para compilar, configurar e gerenciar as conexões, execute o menu principal:${W}"
    echo -e "\\n    ${C}sudo python3 multiflowpx/proxy_menu.py${W}\\n"
}

# Executa o script
main

# Compila o executável do proxy C++
compile_proxy() {
    echo -e "\n${Y}>>> Compilando o executável do proxy C++...${W}"
    # Cria um diretório de build temporário
    mkdir -p /root/multiflowpx/build
    cd /root/multiflowpx/build
    
    # Executa o CMake para configurar o projeto
    if ! cmake /root/multiflowpx/multiflowproxy; then
        echo -e "${R}Falha ao configurar o CMake. A instalação foi abortada.${W}"
        exit 1
    fi
    
    # Compila o projeto
    if ! make; then
        echo -e "${R}Falha ao compilar o proxy C++. A instalação foi abortada.${W}"
        exit 1
    fi
    
    # Copia o executável compilado para /usr/local/bin
    cp proxy /usr/local/bin/multiflowpx_proxy
    echo -e "${G}Executável do proxy compilado e copiado para /usr/local/bin/multiflowpx_proxy.${W}"
    cd /root/multiflowpx
}

# Instala o serviço systemd e copia o proxy_menu.py
install_systemd_service() {
    echo -e "\n${Y}>>> Instalando o serviço systemd para o MultiFlowPX e copiando o proxy_menu.py...${W}"
    cp /root/multiflowpx/multiflowproxy/multiflowpx.service /etc/systemd/system/
    cp /root/multiflowpx/proxy_menu.py /usr/local/bin/multiflowpx_menu
    chmod +x /usr/local/bin/multiflowpx_menu
    systemctl daemon-reload
    systemctl enable multiflowpx.service
    echo -e "${G}Serviço systemd instalado e habilitado. Script de menu copiado para /usr/local/bin/multiflowpx_menu.${W}"
}

# --- Função Principal (modificada) ---
main() {
    print_header
    check_root

    echo -e "${G}Bem-vindo ao instalador do MultiFlow Manager!${W}"
    echo -e "${Y}Este script irá preparar o ambiente, instalando todas as dependências.${W}"
    echo -e "---------------------------------------------------------------------"
    
    install_system_deps
    install_python_deps
    set_permissions
    compile_proxy
    install_systemd_service

    echo
    echo -e "${C}=====================================================================${W}"
    echo -e "${G}      Ambiente preparado com sucesso!      ${W}"
    echo -e "${C}=====================================================================${W}"
    echo -e "\n${Y}Todos os pré-requisitos foram instalados e o serviço configurado.${W}"
    echo -e "${Y}Para gerenciar o proxy, execute o menu principal:${W}"
    echo -e "\n    ${C}sudo python3 multiflowpx/proxy_menu.py${W}\n"
}

# Executa o script
main
