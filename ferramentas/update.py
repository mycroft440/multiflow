#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script responsável por atualizar ou reinstalar o projeto MultiFlow.

Uso:
  --update    → Executa um “git pull” no diretório atual (padrão se nenhuma opção for passada).
  --reset     → Remove todos os arquivos e diretórios (exceto instaladores/lista branca) e executa “install.sh”.
  -y/--yes    → No modo reset, ignora a confirmação.
"""

import os
import shutil
import subprocess
import argparse
from typing import List

class Cores:
    VERMELHO = '\033[91m'
    VERDE    = '\033[92m'
    AMARELO  = '\033[93m'
    CIANO    = '\033[96m'
    FIM      = '\033[0m'

INSTALL_SCRIPT = "install.sh"
SCRIPT_NOME    = os.path.basename(__file__)
GIT_DIR        = ".git"

def ask_for_confirmation(force: bool) -> bool:
    if force:
        print(f"{Cores.AMARELO}A flag '-y' foi usada. Pulando a confirmação.{Cores.FIM}")
        return True
    try:
        prompt = (f"{Cores.AMARELO}ATENÇÃO:{Cores.FIM} Isso apagará todos os arquivos do projeto, "
                  "exceto os da lista branca. Deseja continuar? (s/n): ")
        return input(prompt).strip().lower() == 's'
    except KeyboardInterrupt:
        print("\nOperação cancelada.")
        return False

def perform_cleanup(whitelist: List[str]) -> None:
    print("\nIniciando limpeza do diretório…")
    for item in os.listdir('.'):
        if item not in whitelist:
            try:
                if os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)
                print(f"  {Cores.VERDE}[OK]{Cores.FIM} Removido: {item}")
            except OSError as e:
                print(f"  {Cores.VERMELHO}[ERRO]{Cores.FIM} Falha ao remover {item}: {e}")
    print("Limpeza concluída.\n")

def run_installation(script_path: str) -> None:
    if not os.path.exists(script_path):
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Script de instalação '{script_path}' não encontrado.")
        return
    print(f"Executando o script de instalação: {Cores.CIANO}{script_path}{Cores.FIM}")
    print("--- INÍCIO DA SAÍDA DO SCRIPT DE INSTALAÇÃO ---")
    try:
        subprocess.run(['chmod', '+x', script_path], check=True, capture_output=True)
        subprocess.run([script_path], check=True)
        print("--- FIM DA SAÍDA DO SCRIPT DE INSTALAÇÃO ---")
        print(f"\n{Cores.VERDE}Reinstalação concluída com sucesso!{Cores.FIM}")
    except Exception as e:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Erro ao executar instalação: {e}")

def run_update() -> None:
    if not os.path.isdir(GIT_DIR):
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Este não parece ser um repositório Git.")
        return
    print("--- INICIANDO ATUALIZAÇÃO DO PROJETO ---")
    print(f"A tentar atualizar o repositório com '{Cores.CIANO}git pull{Cores.FIM}'…")
    try:
        subprocess.run(['git', 'pull'], check=True)
        print(f"\n{Cores.VERDE}[SUCESSO]{Cores.FIM} Projeto atualizado com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} 'git pull' falhou ({e.returncode}).")
    except Exception as e:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Erro inesperado: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gerencia o projeto, permitindo um reset completo ou uma atualização via Git.\n"
                    "Se nenhuma flag for fornecida, executa a atualização por padrão.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--reset', action='store_true',
                       help="Executa o reset completo: apaga tudo e reinstala.")
    group.add_argument('--update', action='store_true',
                       help="Executa a atualização: busca as últimas alterações com 'git pull'.")
    parser.add_argument('-y', '--yes', action='store_true',
                        help="Pula a confirmação de segurança para o modo reset.")
    args = parser.parse_args()
    if args.reset:
        whitelist = [INSTALL_SCRIPT, SCRIPT_NOME, GIT_DIR]
        print("--- INICIANDO RESET DO PROJETO ---")
        print(f"Diretório alvo: {os.path.abspath('.')}")
        print(f"Itens na lista branca: {whitelist}\n")
        if ask_for_confirmation(args.yes):
            perform_cleanup(whitelist)
            run_installation(f'./{INSTALL_SCRIPT}')
    else:
        # Sem argumentos ou com --update → update
        run_update()

if __name__ == '__main__':
    main()
