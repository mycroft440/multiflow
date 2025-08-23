import os
import shutil
import subprocess
import argparse
from typing import List

# --- Constantes e Cores ---

class Cores:
    """Classe para armazenar códigos de cores ANSI para o terminal."""
    VERMELHO = '\033[91m'
    VERDE = '\033[92m'
    AMARELO = '\033[93m'
    CIANO = '\033[96m'
    FIM = '\033[0m' # Reseta a cor para o padrão

INSTALL_SCRIPT = "install.sh"
SCRIPT_NOME = os.path.basename(__file__)
GIT_DIR = ".git"

# --- Funções para o modo RESET ---

def ask_for_confirmation(force: bool) -> bool:
    """Pede a confirmação do usuário antes de continuar, a menos que a flag 'force' seja True."""
    if force:
        print(f"{Cores.AMARELO}A flag '-y' foi usada. A pular a confirmação.{Cores.FIM}")
        return True
    
    try:
        prompt = (f"{Cores.AMARELO}ATENÇÃO:{Cores.FIM} Isso apagará todos os arquivos do projeto, "
                  "exceto os da lista branca. Deseja continuar? (s/n): ")
        confirmacao = input(prompt)
        if confirmacao.lower() != 's':
            print("Operação cancelada pelo usuário.")
            return False
        return True
    except KeyboardInterrupt:
        print("\nOperação cancelada.")
        return False

def perform_cleanup(whitelist: List[str]) -> None:
    """Apaga todos os arquivos e diretórios no diretório atual, exceto os da lista branca."""
    print("\nIniciando limpeza do diretório...")
    itens_removidos = 0
    for item in os.listdir('.'):
        if item not in whitelist:
            try:
                if os.path.isdir(item):
                    shutil.rmtree(item)
                    print(f"  {Cores.VERDE}[OK]{Cores.FIM} Diretório removido: {item}")
                else:
                    os.remove(item)
                    print(f"  {Cores.VERDE}[OK]{Cores.FIM} Arquivo removido: {item}")
                itens_removidos += 1
            except OSError as e:
                print(f"  {Cores.VERMELHO}[ERRO]{Cores.FIM} Falha ao remover {item}: {e}")
    
    if itens_removidos == 0:
        print("Nenhum item para remover.")
    
    print("Limpeza concluída.\n")

def run_installation(script_path: str) -> None:
    """Executa o script de instalação e mostra a sua saída em tempo real."""
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

    except FileNotFoundError:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} O comando '{script_path}' não foi encontrado.")
    except subprocess.CalledProcessError as e:
        print(f"\n{Cores.VERMELHO}[ERRO]{Cores.FIM} O script de instalação falhou com o código de saída {e.returncode}.")
    except Exception as e:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Ocorreu um erro inesperado: {e}")

# --- Função para o modo UPDATE ---

def run_update() -> None:
    """Atualiza o projeto executando 'git pull'."""
    if not os.path.isdir(GIT_DIR):
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Este não parece ser um repositório Git.")
        return

    print("--- INICIANDO ATUALIZAÇÃO DO PROJETO ---")
    print(f"A tentar atualizar o repositório com '{Cores.CIANO}git pull{Cores.FIM}'...")
    
    try:
        subprocess.run(['git', 'pull'], check=True)
        print(f"\n{Cores.VERDE}[SUCESSO]{Cores.FIM} Projeto atualizado com sucesso!")
    except FileNotFoundError:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} O comando 'git' não foi encontrado. Verifique se o Git está instalado.")
    except subprocess.CalledProcessError:
        print(f"\n{Cores.VERMELHO}[ERRO]{Cores.FIM} 'git pull' falhou. Pode ter conflitos ou alterações locais não resolvidas.")
    except Exception as e:
        print(f"{Cores.VERMELHO}[ERRO]{Cores.FIM} Ocorreu um erro inesperado: {e}")

def main() -> None:
    """Função principal para orquestrar a gestão do projeto."""
    parser = argparse.ArgumentParser(
        description="Gerencia o projeto, permitindo um reset completo ou uma atualização via Git.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # O grupo de argumentos não é mais obrigatório para evitar o erro na execução sem argumentos
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--reset',
        action='store_true',
        help="Executa o reset completo: apaga tudo e reinstala."
    )
    group.add_argument(
        '--update',
        action='store_true',
        help="Executa a atualização: busca as últimas alterações com 'git pull'."
    )
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help="Pula a confirmação de segurança para o modo reset."
    )
    args = parser.parse_args()

    if args.update:
        run_update()
    elif args.reset:
        lista_branca = [INSTALL_SCRIPT, SCRIPT_NOME, GIT_DIR]
        diretorio_atual = os.path.abspath('.')

        print("--- INICIANDO RESET DO PROJETO ---")
        print(f"Diretório alvo: {diretorio_atual}")
        print(f"Itens na lista branca (não serão apagados): {lista_branca}\n")

        if ask_for_confirmation(args.yes):
            perform_cleanup(lista_branca)
            run_installation(f'./{INSTALL_SCRIPT}')
    else:
        # Se nenhum argumento for fornecido, imprime a ajuda
        print("Nenhuma ação especificada. Use '--reset' para reinstalar ou '--update' para atualizar.")
        parser.print_help()


if __name__ == "__main__":
    main()
