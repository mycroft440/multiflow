#!/bin/bash
# Script para instalar OpenVPN de forma não-interativa
# Baseado no script de angristan: https://github.com/angristan/openvpn-install

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

# Executa o script de instalação de forma não-interativa
echo "Executando a instalação automática do OpenVPN..."
# Fornece as respostas para as perguntas do script de forma automática
# Isso evita a necessidade de interação do usuário.
# Respostas:
# - AUTO_INSTALL=y: Habilita a instalação não-interativa
# - ENDPOINT=$(curl -s https://api.ipify.org): Detecta automaticamente o IP público
# - IPV6_SUPPORT=n: Desabilita o suporte a IPv6 (mais simples)
# - PORT_CHOICE=1: Usa a porta padrão (1194)
# - PROTOCOL_CHOICE=2: Usa o protocolo TCP
# - DNS_CHOICE=1: Usa os resolvedores de DNS atuais do sistema (da VPS)
# - COMPRESSION_ENABLED=n: Desabilita a compressão (recomendado por segurança)
# - CUSTOMIZE_ENC=n: Usa as configurações de criptografia padrão (seguras)
# - CLIENT=cliente1: Cria um primeiro cliente com o nome "cliente1"
# - PASS=1: Cria o cliente sem senha para facilitar a conexão
AUTO_INSTALL=y \
ENDPOINT=$(curl -s https://api.ipify.org) \
IPV6_SUPPORT=n \
PORT_CHOICE=1 \
PROTOCOL_CHOICE=2 \
DNS_CHOICE=1 \
COMPRESSION_ENABLED=n \
CUSTOMIZE_ENC=n \
CLIENT=cliente1 \
PASS=1 \
./openvpn-install.sh

# Verifica se o arquivo de configuração do cliente foi criado
if [ -f "/root/cliente1.ovpn" ]; then
    echo
    echo "------------------------------------------------------------"
    echo "✓ Instalação do OpenVPN concluída com sucesso!"
    echo "✓ Protocolo: TCP"
    echo "✓ DNS: Usando os DNS da VPS"
    echo "✓ O arquivo de configuração do cliente foi salvo em: /root/cliente1.ovpn"
    echo "✓ Use este arquivo para se conectar à sua VPN."
    echo "------------------------------------------------------------"
else
    echo
    echo "------------------------------------------------------------"
    echo "✗ A instalação do OpenVPN parece ter falhado."
    echo "✗ O arquivo de configuração do cliente não foi encontrado."
    echo "------------------------------------------------------------"
fi


# Limpa o arquivo de instalação após a execução
rm -f openvpn-install.sh

exit 0