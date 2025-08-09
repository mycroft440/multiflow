import os
import subprocess
import sys
import requests

# Adiciona o diretório do script ao sys.path para permitir importações de outros módulos
# Isso é útil se o script de atualização for executado diretamente
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from menus.menu_style_utils import print_header, print_center, print_line, print_error
except ImportError:
    print("Erro: Não foi possível importar utilitários de estilo.")
    print(f"Verifique se o multiflow está instalado corretamente em {current_dir} e se o PYTHONPATH está configurado.")
    sys.exit(1)

# URL do repositório no GitHub
GITHUB_REPO = "mycroft440/multiflow"
# O diretório onde o script está instalado
INSTALL_DIR = current_dir

def get_latest_commit_sha():
    """Obtém o SHA do último commit do repositório no GitHub."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        return response.json()['sha']
    except requests.exceptions.RequestException as e:
        print_error(f"Erro ao verificar atualizações: {e}")
        return None

def get_local_commit_sha():
    """Obtém o SHA do commit local."""
    sha_file = os.path.join(INSTALL_DIR, '.git_sha')
    if os.path.exists(sha_file):
        with open(sha_file, 'r') as f:
            return f.read().strip()
    return None

def update_local_commit_sha(sha):
    """Atualiza o arquivo com o SHA do commit local."""
    sha_file = os.path.join(INSTALL_DIR, '.git_sha')
    with open(sha_file, 'w') as f:
        f.write(sha)

def main():
    """Função principal para verificar e aplicar atualizações."""
    limpar_tela()
    print_header("Atualizador MultiFlow")
    print_center("Verificando atualizações...")

    latest_sha = get_latest_commit_sha()
    if not latest_sha:
        return

    local_sha = get_local_commit_sha()

    if latest_sha == local_sha:
        print_center("Você já está com a versão mais recente.")
    else:
        print_center("Nova versão encontrada! Atualizando...")
        try:
            # Comando para baixar e executar o script de instalação/atualização
            update_command = "wget -O /tmp/install.sh https://raw.githubusercontent.com/mycroft440/multiflow/main/install.sh && bash /tmp/install.sh"
            
            # Usamos subprocess.run para executar o comando
            process = subprocess.run(update_command, shell=True, check=True, capture_output=True, text=True)
            
            print_center("Atualização concluída com sucesso!")
            # Atualiza o SHA local após a atualização bem-sucedida
            update_local_commit_sha(latest_sha)
        except subprocess.CalledProcessError as e:
            print_error("Falha na atualização.")
            print_error(f"Saída do erro:\n{e.stderr}")
        except Exception as e:
            print_error(f"Ocorreu um erro inesperado: {e}")

    print_line()
    input("Pressione Enter para voltar ao menu principal...")

def limpar_tela():
    """Limpa a tela do terminal."""
    os.system('clear' if os.name == 'posix' else 'cls')

if __name__ == "__main__":
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado como root.")
        sys.exit(1)
    main()
