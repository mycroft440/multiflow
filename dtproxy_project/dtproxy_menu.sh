#!/bin/bash

function main_menu() {
    clear
    echo "DTPROXY"
    echo "1. Instalar dtproxy"
    echo "2. Porta do proxy"
    echo "3. Remover dtproxy"
    echo "4. Voltar"
    echo ""
    read -p "Escolha uma opção: " choice

    case $choice in
        1)
            install_dtproxy_menu
            ;;
        2)
            port_menu
            ;;
        3)
            remove_dtproxy
            ;;
        4)
            exit 0
            ;;
        *)
            echo "Opção inválida! Pressione qualquer tecla para continuar..."
            read -n 1
            main_menu
            ;;
esac
}

function install_dtproxy_menu() {
    clear
    echo "Instalar dtproxy"
    echo ""
    echo "1. dtproxy 1.2.6 x86"
    echo ""
    read -p "Escolha uma opção: " arch_choice

    if [ "$arch_choice" == "1" ]; then
        read -p "Digite a porta para o dtproxy (padrão: 10000): " port_choice
        port_choice=${port_choice:-10000}
        echo "Iniciando dtproxy x86_64 na porta $port_choice..."
        sudo mv /home/ubuntu/dtproxy_x86_64 /usr/local/bin/dtproxy
        sudo chmod +x /usr/local/bin/dtproxy
        dtproxy --port $port_choice --http &
        echo "dtproxy iniciado na porta $port_choice."
        echo "Pressione qualquer tecla para continuar..."
        read -n 1
    else
        echo "Opção inválida! Pressione qualquer tecla para continuar..."
        read -n 1
    fi
    main_menu
}

function remove_port() {
    read -p "Digite a porta a ser removida: " port_to_remove
    if pgrep -f "dtproxy --port $port_to_remove"; then
        kill $(pgrep -f "dtproxy --port $port_to_remove")
        echo "dtproxy na porta $port_to_remove foi parado."
    else
        echo "Nenhum dtproxy encontrado na porta $port_to_remove."
    fi
    echo "Pressione qualquer tecla para continuar..."
    read -n 1
}

function add_port() {
    read -p "Digite a porta a ser adicionada: " port_to_add
    if pgrep -f "dtproxy --port $port_to_add"; then
        echo "dtproxy já está rodando na porta $port_to_add."
    else
        dtproxy --port $port_to_add --http &
        echo "dtproxy iniciado na porta $port_to_add."
    fi
    echo "Pressione qualquer tecla para continuar..."
    read -n 1
}

function port_menu() {
    clear
    echo "Porta do Proxy"
    echo "1. Remover porta"
    echo "2. Adicionar porta"
    echo "3. Voltar"
    echo ""
    read -p "Escolha uma opção: " port_choice

    case $port_choice in
        1)
            remove_port
            ;;
        2)
            add_port
            ;;
        3)
            ;;
        *)
            echo "Opção inválida! Pressione qualquer tecla para continuar..."
            read -n 1
            ;;
    esac
    main_menu
}

function remove_dtproxy() {
    clear
    echo "Remover dtproxy"
    echo "Parando todos os processos dtproxy..."
    pkill -f "dtproxy"
    echo "Removendo o executável dtproxy..."
    sudo rm -f /usr/local/bin/dtproxy
    echo "Removendo o script do menu dtproxy..."
    rm -f /home/ubuntu/dtproxy_menu.sh
    echo "Removendo os arquivos dtproxy_x86_64 e dtproxy_aarch64..."
    rm -f /home/ubuntu/dtproxy_x86_64
    rm -f /home/ubuntu/dtproxy_aarch64
    echo "dtproxy e arquivos relacionados removidos com sucesso."
    echo "Pressione qualquer tecla para continuar..."
    read -n 1
    main_menu
}

# Inicia o menu principal
main_menu


