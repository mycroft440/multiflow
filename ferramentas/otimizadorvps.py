#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import subprocess
import shutil

# Arquivo onde os cron jobs serão salvos para fácil gerenciamento
CRON_FILE_PATH = "/etc/cron.d/vps_optimizer_tasks"

def clear_screen():
    """Limpa a tela do terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print("\n\033[1;31mErro: Este script precisa ser executado com privilégios de superusuário (root).\033[0m")
        print("Por favor, execute com: sudo python3 optimizer.py")
        sys.exit(1)

def run_command(command, silent=False):
    """Executa um comando no shell e exibe a saída."""
    try:
        stdout_pipe = subprocess.PIPE if not silent else subprocess.DEVNULL
        stderr_pipe = subprocess.STDOUT if not silent else subprocess.DEVNULL
        
        process = subprocess.Popen(
            command, shell=True, stdout=stdout_pipe, stderr=stderr_pipe, universal_newlines=True
        )
        
        if not silent:
            for line in process.stdout:
                print(line, end='')
        
        process.wait()
        
        if process.returncode != 0 and not silent:
            print(f"\n\033[1;31mComando finalizado com erro (código: {process.returncode}).\033[0m")
    except Exception as e:
        if not silent:
            print(f"\n\033[1;31mOcorreu um erro ao executar o comando: {e}\033[0m")

def clean_memory_cache(silent=False):
    """Limpa o cache de memória do kernel (PageCache, dentries e inodes)."""
    if not silent:
        print("\n\033[1;36m--- Limpando Cache de Memória RAM ---\033[0m")
        print("Sincronizando dados em disco...")
    run_command("sync", silent)
    if not silent:
        print("Limpando PageCache, dentries e inodes...")
    run_command("echo 3 > /proc/sys/vm/drop_caches", silent)
    if not silent:
        print("\033[1;32mCache de memória limpo com sucesso!\033[0m")

def clean_apt_cache(silent=False):
    """Limpa o cache de pacotes do APT."""
    if not silent:
        print("\n\033[1;36m--- Limpando Cache de Pacotes (APT) ---\033[0m")
    run_command("apt-get clean", silent)
    if not silent:
        print("\033[1;32mCache do APT limpo com sucesso!\033[0m")

def autoremove_packages(silent=False):
    """Remove pacotes e dependências que não são mais necessários."""
    if not silent:
        print("\n\033[1;36m--- Removendo Pacotes Inúteis (Autoremove) ---\033[0m")
    run_command("apt-get autoremove -y", silent)
    if not silent:
        print("\033[1;32mPacotes desnecessários removidos com sucesso!\033[0m")

def clean_journal_logs(silent=False):
    """Limpa logs antigos do systemd-journald."""
    if not silent:
        print("\n\033[1;36m--- Limpando Logs Antigos do Sistema (Journald) ---\033[0m")
        print("Mantendo apenas os logs dos últimos 7 dias...")
    run_command("journalctl --vacuum-time=7d", silent)
    if not silent:
        print("\033[1;32mLogs antigos do sistema limpos com sucesso!\033[0m")

def run_disk_optimizations(silent=False):
    """Executa as otimizações de disco em sequência."""
    if not silent:
        clear_screen()
        print("\033[1;33m--- INICIANDO OTIMIZAÇÃO DE DISCO ---\033[0m")
    clean_apt_cache(silent)
    autoremove_packages(silent)
    clean_journal_logs(silent)
    if not silent:
        print("\n\033[1;32m✅ OTIMIZAÇÃO DE DISCO FINALIZADA! ✅\033[0m")

def run_all_optimizations(silent=False):
    """Executa todas as funções de limpeza em sequência."""
    if not silent:
        clear_screen()
        print("\033[1;33m--- INICIANDO OTIMIZAÇÃO COMPLETA ---\033[0m")
    clean_memory_cache(silent)
    run_disk_optimizations(silent)
    if not silent:
        print("\n\033[1;32m✅ OTIMIZAÇÃO COMPLETA FINALIZADA! ✅\033[0m")

def setup_automatic_cleaning():
    """Configura cron jobs para executar a limpeza diária (RAM) e semanal (Disco)."""
    clear_screen()
    print("\033[1;33m--- Configurando Limpeza Automática Otimizada ---\033[0m")

    if os.path.exists(CRON_FILE_PATH):
        print("\n\033[1;33mAVISO: A limpeza automática já parece estar configurada.\033[0m")
        choice = input("Deseja sobrescrever a configuração existente? (s/N): ").lower()
        if choice != 's':
            print("Nenhuma alteração foi feita.")
            return

    script_path = os.path.abspath(__file__)
    python_path = sys.executable

    # Cron job para rodar a limpeza de RAM diariamente às 4 da manhã
    cron_ram = f"0 4 * * * root {python_path} {script_path} --clean-ram-silently > /dev/null 2>&1\n"
    # Cron job para rodar a limpeza de disco todo domingo às 3 da manhã
    cron_disk = f"0 3 * * 0 root {python_path} {script_path} --clean-disk-silently > /dev/null 2>&1\n"

    try:
        with open(CRON_FILE_PATH, 'w') as f:
            f.write("# Cron jobs para otimização automática da VPS, gerenciado por optimizer.py\n")
            f.write("# Limpeza diária do cache de RAM\n")
            f.write(cron_ram)
            f.write("# Limpeza semanal de pacotes, dependências e logs\n")
            f.write(cron_disk)
        
        os.chmod(CRON_FILE_PATH, 0o644)

        print("\n\033[1;32m✅ Limpeza automática configurada com sucesso!\033[0m")
        print("  - Cache da RAM será limpo diariamente às 04:00.")
        print("  - Otimização de disco será executada semanalmente aos domingos às 03:00.")
        print(f"A configuração foi salva em: {CRON_FILE_PATH}")

    except Exception as e:
        print(f"\n\033[1;31mOcorreu um erro ao criar o arquivo de agendamento: {e}\033[0m")
        print("Verifique se você tem permissão para escrever no diretório /etc/cron.d/")

def remove_automatic_cleaning():
    """Remove o arquivo de cron job da limpeza automática."""
    clear_screen()
    print("\033[1;33m--- Removendo Limpeza Automática ---\033[0m")
    if os.path.exists(CRON_FILE_PATH):
        try:
            os.remove(CRON_FILE_PATH)
            print(f"\n\033[1;32mArquivo de agendamento '{CRON_FILE_PATH}' removido com sucesso.\033[0m")
            print("A limpeza automática foi desativada.")
        except Exception as e:
            print(f"\n\033[1;31mOcorreu um erro ao remover o arquivo: {e}\033[0m")
    else:
        print("\n\033[1;33mNenhuma configuração de limpeza automática foi encontrada.\033[0m")


def display_menu():
    """Exibe o menu principal."""
    clear_screen()
    print("\033[0;34m━" * 10, "\033[1;32m OTIMIZADOR DE VPS ", "\033[0;34m━" * 10, "\n")
    print(" \033[1;33m1.\033[1;32m Executar todas as funçoes do 2 ao 5\033[0m")
    print("\n \033[1;33m2.\033[1;37m Limpar Cache de Memória RAM")
    print(" \033[1;33m3.\033[1;37m Limpar Cache de Pacotes (APT)")
    print(" \033[1;33m4.\033[1;37m Remover Pacotes Inúteis (Autoremove)")
    print(" \033[1;33m5.\033[1;37m Limpar Logs Antigos do Sistema")
    print("\n \033[1;33m6.\033[1;36m Adicionar Limpeza Automática (Otimizada)\033[0m")
    print(" \033[1;33m7.\033[1;31m Remover Limpeza Automática\033[0m")
    print("\n \033[1;33m0.\033[1;37m Sair")
    print("\033[0;34m" + "─" * 48 + "\033[0m\n")

def main():
    """Loop principal do menu."""
    check_root()
    while True:
        display_menu()
        choice = input("\033[1;36mEscolha uma opção: \033[0m")
        
        if choice == '1':
            run_all_optimizations()
        elif choice == '2':
            clean_memory_cache()
        elif choice == '3':
            clean_apt_cache()
        elif choice == '4':
            autoremove_packages()
        elif choice == '5':
            clean_journal_logs()
        elif choice == '6':
            setup_automatic_cleaning()
        elif choice == '7':
            remove_automatic_cleaning()
        elif choice == '0':
            print("\n\033[1;32mSaindo do otimizador...\033[0m")
            break
        else:
            print("\n\033[1;31mOpção inválida. Tente novamente.\033[0m")
        
        input("\nPressione Enter para continuar...")

if __name__ == '__main__':
    # Verifica se o script foi chamado com argumentos para execução silenciosa
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        check_root()
        if arg == '--run-all-silently':
            run_all_optimizations(silent=True)
        elif arg == '--clean-ram-silently':
            clean_memory_cache(silent=True)
        elif arg == '--clean-disk-silently':
            run_disk_optimizations(silent=True)
        sys.exit(0)
    
    main()
