#!/bin/bash
# Script para instalar OpenVPN usando o script de angristan
# https://github.com/angristan/openvpn-install

# Verifica se o script está sendo executado como root
if [ "$EUID" -ne 0 ]; then
  echo "Por favor, execute como root"
  exit
fi

# Função para exibir mensagem de erro e sair
error_exit() {
    echo "$1" 1>&2
    exit 1
}

# Determina o diretório do script e muda para ele.
# Isso torna o script mais robusto e independente do diretório de onde é chamado.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR" || error_exit "Falha ao mudar para o diretório do script: $SCRIPT_DIR"

# URL direta para o script de instalação do OpenVPN
URL="https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh"

# Baixa o script de instalação do OpenVPN
echo "Baixando o script de instalação do OpenVPN..."
wget -O openvpn-install.sh "$URL"

# Verifica se o download foi bem-sucedido
if [ $? -ne 0 ]; then
    echo "Falha ao baixar o script de instalação do OpenVPN."
    exit 1
fi

# Dá permissão de execução ao script baixado
chmod +x openvpn-install.sh

# Executa o script de instalação
echo "Executando o assistente de instalação do OpenVPN..."
./openvpn-install.sh

# Limpa o arquivo de instalação após a execução
rm -f openvpn-install.sh

echo "Assistente de instalação do OpenVPN finalizado."

exit 0