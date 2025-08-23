import os
import shutil
import subprocess
import sys

def limpar_e_reinstalar():
    """
    Função principal para limpar o diretório do projeto e reinstalar.

    Esta função apaga todos os arquivos e diretórios no local atual,
    exceto por uma 'lista branca' que contém o próprio script e o
    script de instalação 'install.sh'.

    Após a limpeza, executa 'install.sh' para configurar o projeto novamente.
    """
    # --- 1. Definição da Lista Branca ---
    # Adicione aqui qualquer outro arquivo ou pasta que NUNCA deve ser apagado.
    lista_branca = ['install.sh', os.path.basename(__file__)]
    diretorio_atual = '.' # Representa o diretório atual

    print("--- INICIANDO RESET DO PROJETO ---")
    print(f"Diretório alvo: {os.path.abspath(diretorio_atual)}")
    print(f"Itens na lista branca (não serão apagados): {lista_branca}\n")

    # --- 2. Confirmação do Usuário ---
    # Este passo é crucial para evitar a exclusão acidental de arquivos.
    try:
        confirmacao = input("ATENÇÃO: Isso apagará todos os arquivos do projeto, exceto os da lista branca. Deseja continuar? (s/n): ")
        if confirmacao.lower() != 's':
            print("Operação cancelada pelo usuário.")
            return
    except KeyboardInterrupt:
        print("\nOperação cancelada.")
        return

    print("\nIniciando limpeza do diretório...")

    # --- 3. Processo de Exclusão ---
    # Itera sobre todos os itens no diretório.
    for item in os.listdir(diretorio_atual):
        if item not in lista_branca:
            try:
                # Remove a pasta e todo o seu conteúdo se for um diretório.
                if os.path.isdir(item):
                    shutil.rmtree(item)
                    print(f"  [OK] Diretório removido: {item}")
                # Remove o arquivo se for um arquivo.
                else:
                    os.remove(item)
                    print(f"  [OK] Arquivo removido: {item}")
            except OSError as e:
                print(f"  [ERRO] Falha ao remover {item}: {e}")

    print("Limpeza concluída.\n")

    # --- 4. Reinstalação ---
    # Executa o script 'install.sh' para reinstalar o projeto.
    script_instalacao = './install.sh'
    if os.path.exists(script_instalacao):
        print(f"Executando o script de instalação: {script_instalacao}")
        try:
            # Garante que o script tenha permissão de execução.
            subprocess.run(['chmod', '+x', script_instalacao], check=True)
            
            # Executa o script e captura a saída.
            resultado = subprocess.run(
                [script_instalacao], 
                check=True, 
                text=True, 
                capture_output=True
            )
            
            print("\n--- Saída do install.sh ---")
            print(resultado.stdout)
            if resultado.stderr:
                print("\n--- Erros do install.sh ---")
                print(resultado.stderr)
            print("---------------------------\n")
            print("Reinstalação concluída com sucesso!")

        except FileNotFoundError:
            print(f"[ERRO] O script '{script_instalacao}' não foi encontrado.")
        except subprocess.CalledProcessError as e:
            print(f"[ERRO] O script de instalação falhou com o código de saída {e.returncode}.")
            print("--- Saída do Erro ---")
            print(e.stdout)
            print(e.stderr)
            print("---------------------")
        except Exception as e:
            print(f"Ocorreu um erro inesperado ao executar o instalador: {e}")
    else:
        print(f"[ERRO] Script de instalação '{script_instalacao}' não encontrado. Não é possível reinstalar.")

if __name__ == "__main__":
    limpar_e_reinstalar()
