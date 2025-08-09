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

# Verifica se o diretório de conexões existe
if [ ! -d "/root/multiflow/conexoes" ]; then
    error_exit "Diretório /root/multiflow/conexoes não encontrado."
fi

cd /root/multiflow/conexoes || error_exit "Não foi possível mudar para o diretório /root/multiflow/conexoes."

# URL direta para o script de instalação do OpenVPN
URL="https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh"

# Verifica se a URL está vazia (verificação de segurança)
if [ -z "$URL" ]; then
	echo
	echo "URL de instalação não definida. Saindo."
	exit 1
fi

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
