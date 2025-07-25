#!/bin/bash

# Função para exibir mensagens de erro e sair
function error_exit {
    echo "Erro: $1" >&2
    exit 1
}

# Atualizar pacotes e instalar dependências
echo "Atualizando pacotes e instalando dependências..."
sudo apt update || error_exit "Falha ao atualizar pacotes."
sudo apt install -y git python3 python3-pip || error_exit "Falha ao instalar git, python3 ou python3-pip."
pip install psutil || error_exit "Falha ao instalar psutil."

# Definir o diretório de instalação
INSTALL_DIR="/opt/multiflow"

# Remover instalação anterior se existir
if [ -d "$INSTALL_DIR" ]; then
    echo "Removendo instalação anterior em $INSTALL_DIR..."
    sudo rm -rf "$INSTALL_DIR" || error_exit "Falha ao remover instalação anterior."
fi

# Clonar o repositório
REPO_URL="https://github.com/mycroft440/multiflow.git"
echo "Clonando o repositório $REPO_URL para $INSTALL_DIR..."
sudo git clone "$REPO_URL" "$INSTALL_DIR" || error_exit "Falha ao clonar o repositório."

# Dar permissões de execução ao script principal
echo "Definindo permissões de execução para o script principal..."
sudo chmod +x "$INSTALL_DIR/multiflow.py" || error_exit "Falha ao definir permissões de execução."

# Criar um link simbólico para facilitar a execução
echo "Criando link simbólico para execução fácil..."
sudo ln -sf "$INSTALL_DIR/multiflow.py" /usr/local/bin/multiflow || error_exit "Falha ao criar link simbólico."

# Instalar dependências do C++ para o socks5_server
echo "Instalando dependências C++ para socks5_server..."
sudo apt install -y g++ libboost-all-dev libssh2-1-dev || error_exit "Falha ao instalar dependências C++."

# Compilar o socks5_server
echo "Compilando socks5_server..."
sudo g++ -o "$INSTALL_DIR/socks5_server" "$INSTALL_DIR/src/socks5_server.cpp" -lboost_system -lboost_log -lboost_thread -lpthread -lssh2 -std=c++14 || error_exit "Falha ao compilar socks5_server."

echo "Instalação concluída! Você pode executar o Multiflow digitando 'multiflow' no terminal."

# Iniciar o Multiflow (opcional, pode ser removido se o usuário preferir iniciar manualmente)
# echo "Iniciando Multiflow..."
# sudo python3 "$INSTALL_DIR/multiflow.py"


