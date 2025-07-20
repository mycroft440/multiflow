#!/bin/bash

clear

echo "DTPROXY - Seleção de Porta"
echo "1. dtproxy 1.2.6 arm (Não compatível com este ambiente)"
echo "2. dtproxy 1.2.6 x86"
echo ""

read -p "Escolha uma opção: " arch_choice

if [ "$arch_choice" == "2" ]; then
    read -p "Digite a porta para o dtproxy (padrão: 10000): " port_choice
    port_choice=${port_choice:-10000}
    echo "Iniciando dtproxy x86_64 na porta $port_choice..."
    dtproxy --port $port_choice --http
else
    echo "Opção inválida ou arquitetura não compatível com este ambiente."
fi


