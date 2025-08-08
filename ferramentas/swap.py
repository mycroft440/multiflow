#!/usr/bin/env python3
import subprocess
import os
import sys
import re

def run_command(cmd, check=True, capture_output=True):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=capture_output, text=True)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar '{cmd}': {e.stderr}")
        sys.exit(1)

def is_swap_active(swap_file):
    """Verifica se um arquivo de swap específico está ativo."""
    try:
        result = run_command("swapon --show", check=False, capture_output=True)
        if result.returncode == 0:
            return swap_file in result.stdout
        return False
    except Exception:
        return False

def setup_swap(swap_size='1.5G', swap_file='/swapfile', swappiness=10):
    """
    Configura um arquivo de swap persistente do tamanho especificado.
    
    Parâmetros:
    - swap_size: Tamanho do arquivo de swap (ex: '1.5G').
    - swap_file: Caminho para o arquivo de swap (padrão '/swapfile').
    - swappiness: Valor para vm.swappiness (padrão 10 para segurança de SSD).
    """
    if os.geteuid() != 0:
        print("Este script deve ser executado como root.")
        sys.exit(1)

    # Verificar se o swap já está ativo
    if is_swap_active(swap_file):
        print(f"Memória swap já está ativa usando {swap_file}. Pulando a configuração.")
        return
    
    # Analisar swap_size para MB
    size_match = re.match(r'(\d+(\.\d+)?)([KMG])?', swap_size.upper())
    if not size_match:
        raise ValueError("Formato de swap_size inválido. Use, por exemplo, '1.5G'.")
    
    size_num = float(size_match.group(1))
    unit = size_match.group(3) or 'G'
    
    if unit == 'K':
        count = int(size_num / 1024)
    elif unit == 'M':
        count = int(size_num)
    elif unit == 'G':
        count = int(size_num * 1024)
    else:
        raise ValueError("Unidade não suportada em swap_size.")
    
    if count <= 0:
        print("Tamanho do swap deve ser maior que 0.")
        sys.exit(1)

    # Verificar se o arquivo de swap existe
    if os.path.exists(swap_file):
        print(f"Arquivo de swap {swap_file} já existe. Pulando a criação.")
    else:
        # Criar arquivo de swap com dd
        print(f"Criando arquivo de swap de {swap_size} em {swap_file}...")
        run_command(f"dd if=/dev/zero of={swap_file} bs=1M count={count} status=progress")
    
    # Definir permissões
    run_command(f"chmod 600 {swap_file}")
    
    # Formatar como swap
    run_command(f"mkswap {swap_file}")
    
    # Habilitar swap
    run_command(f"swapon {swap_file}")
    
    # Adicionar ao /etc/fstab se não estiver presente
    fstab_entry = f"{swap_file} none swap sw 0 0\n"
    try:
        with open('/etc/fstab', 'r') as f:
            fstab_content = f.read()
        if fstab_entry not in fstab_content:
            with open('/etc/fstab', 'a') as f:
                f.write(fstab_entry)
            print("Adicionada entrada de swap ao /etc/fstab para persistência.")
        else:
            print("Entrada de swap já presente em /etc/fstab.")
    except IOError as e:
        print(f"Erro ao acessar /etc/fstab: {e}")
        sys.exit(1)
    
    # Definir swappiness para otimização de longo prazo
    sysctl_conf = '/etc/sysctl.conf'
    swappiness_line = f"vm.swappiness = {swappiness}\n"
    try:
        with open(sysctl_conf, 'r') as f:
            content = f.read()
        if swappiness_line not in content:
            with open(sysctl_conf, 'a') as f:
                f.write(swappiness_line)
            print(f"Definido vm.swappiness={swappiness} em {sysctl_conf} para uso reduzido de swap, minimizando o desgaste em SSDs.")
        else:
            print("vm.swappiness já definido em /etc/sysctl.conf.")
    except IOError as e:
        print(f"Erro ao acessar {sysctl_conf}: {e}")
        sys.exit(1)
    
    # Aplicar mudanças do sysctl
    run_command("sysctl -p")
    
    print(f"Configuração de swap completa: {swap_size} em {swap_file}. Verifique com 'free -h' ou 'swapon --show'.")

def teardown_swap(swap_file='/swapfile'):
    """
    Desfaz o arquivo de swap.
    
    Parâmetros:
    - swap_file: Caminho para o arquivo de swap (padrão '/swapfile').
    """
    if os.geteuid() != 0:
        print("Este script deve ser executado como root.")
        sys.exit(1)
    
    # Desabilitar swap
    try:
        run_command(f"swapoff {swap_file}", check=False) # check=False because swapoff might fail if not active
    except Exception as e:
        print(f"Aviso: Não foi possível desativar o swap {swap_file}. Pode não estar ativo. {e}")

    # Remover arquivo de swap
    if os.path.exists(swap_file):
        try:
            os.remove(swap_file)
            print(f"Removido {swap_file}.")
        except OSError as e:
            print(f"Erro ao remover o arquivo de swap {swap_file}: {e}")
            sys.exit(1)
    else:
        print(f"Arquivo de swap {swap_file} não encontrado. Pulando a remoção.")
    
    # Remover do /etc/fstab
    try:
        with open('/etc/fstab', 'r') as f:
            lines = f.readlines()
        with open('/etc/fstab', 'w') as f:
            for line in lines:
                if swap_file not in line:
                    f.write(line)
        print("Removida entrada de swap de /etc/fstab.")
    except IOError as e:
        print(f"Erro ao acessar /etc/fstab: {e}")
        sys.exit(1)
    
    # Remover swappiness de sysctl.conf (opcional, comente se não desejar)
    sysctl_conf = '/etc/sysctl.conf'
    try:
        with open(sysctl_conf, 'r') as f:
            lines = f.readlines()
        with open(sysctl_conf, 'w') as f:
            for line in lines:
                if not line.startswith('vm.swappiness'):
                    f.write(line)
        run_command("sysctl -p")
        print("Removido vm.swappiness de /etc/sysctl.conf.")
    except IOError as e:
        print(f"Erro ao acessar {sysctl_conf}: {e}")
        sys.exit(1)
    
    print("Desmontagem completa.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Automatiza a configuração de arquivo de swap.")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    setup_parser = subparsers.add_parser('setup', help='Configura o arquivo de swap')
    setup_parser.add_argument('--swap_size', default='1.5G', help='Tamanho do swap (ex: 1.5G)')
    setup_parser.add_argument('--swap_file', default='/swapfile', help='Caminho para o arquivo de swap')
    setup_parser.add_argument('--swappiness', type=int, default=10, help='Valor de vm.swappiness')
    
    teardown_parser = subparsers.add_parser('teardown', help='Desfaz o arquivo de swap')
    teardown_parser.add_argument('--swap_file', default='/swapfile', help='Caminho para o arquivo de swap')
    
    args = parser.parse_args()
    
    if args.command == 'setup':
        setup_swap(args.swap_size, args.swap_file, args.swappiness)
    elif args.command == 'teardown':
        teardown_swap(args.swap_file)

