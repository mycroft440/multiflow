import os
import subprocess
import sys
import shutil

def run_command(cmd, sudo=False):
    """Executa um comando via subprocess, com opção de sudo."""
    if sudo:
        cmd = ['sudo'] + cmd
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        print(result)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar {' '.join(cmd)}: {e.output}")
        return False
    except Exception as e:
        print(f"Exceção inesperada: {e}")
        return False

def install_dependencies():
    """Instala dependências necessárias via apt (para Ubuntu/Debian)."""
    print("Instalando dependências...")
    deps = [
        'git', 'build-essential', 'autoconf', 'automake', 'libtool', 'pkg-config',
        'libssl-dev', 'liblz4-dev', 'liblzo2-dev', 'libpam0g-dev', 'libcap-ng-dev'
    ]
    if not run_command(['apt', 'update'], sudo=True):
        return False
    for dep in deps:
        if not run_command(['apt', 'install', '-y', dep], sudo=True):
            return False
    return True

def clone_repo():
    """Clona o repositório oficial do OpenVPN."""
    repo_url = "https://github.com/OpenVPN/openvpn.git"
    clone_dir = "openvpn_source"
    if os.path.exists(clone_dir):
        print(f"Diretório {clone_dir} já existe. Removendo...")
        shutil.rmtree(clone_dir)
    print("Clonando repositório...")
    if not run_command(['git', 'clone', repo_url, clone_dir]):
        return False
    os.chdir(clone_dir)
    return True

def build_and_install():
    """Configura, compila e instala o OpenVPN."""
    print("Preparando build...")
    if not run_command(['autoreconf', '-i', '-v', '-f']):
        return False
    print("Configurando...")
    if not run_command(['./configure']):
        return False
    print("Compilando...")
    if not run_command(['make']):
        return False
    print("Instalando...")
    if not run_command(['make', 'install'], sudo=True):
        return False
    return True

def main():
    if sys.platform != 'linux':
        print("Este instalador é otimizado para Linux (Ubuntu/Debian). Para Windows/macOS, instale manualmente seguindo o README do GitHub.")
        sys.exit(1)

    print("Instalador OpenVPN do GitHub oficial em \GOD MODE/.")
    if input("Deseja prosseguir? (s/n): ").lower() != 's':
        sys.exit(0)

    if not install_dependencies():
        print("Falha na instalação de dependências. Aborte.")
        sys.exit(1)

    if not clone_repo():
        print("Falha ao clonar repositório. Aborte.")
        sys.exit(1)

    if not build_and_install():
        print("Falha no build/instalação. Aborte.")
        sys.exit(1)

    print("OpenVPN instalado com sucesso! Verifique com 'openvpn --version'.")

if __name__ == "__main__":
    main()