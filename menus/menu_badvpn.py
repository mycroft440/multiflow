import os
import time
import textwrap

# --- Código-fonte do wrapper C embutido no script ---
# Este código será compilado durante a instalação.
C_SOURCE_CODE = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <signal.h>
#include <syslog.h>
#include <errno.h>

#define PID_FILE "/var/run/badvpn_wrapper.pid"
#define LOG_IDENTITY "badvpn_wrapper"

static pid_t child_pid = 0;

void cleanup() {
    syslog(LOG_INFO, "Removendo o ficheiro PID: %s", PID_FILE);
    remove(PID_FILE);
    closelog();
}

void handle_signal(int sig) {
    syslog(LOG_INFO, "Sinal %d recebido, a encerrar...", sig);
    if (child_pid > 0) {
        syslog(LOG_INFO, "A enviar sinal SIGTERM para o processo filho com PID %d", child_pid);
        kill(child_pid, SIGTERM);
    }
    cleanup();
    exit(0);
}

void start_badvpn() {
    execl("/usr/local/bin/badvpn-udpgw", "badvpn-udpgw",
          "--listen-addr", "127.0.0.1:7300",
          "--max-clients", "512",
          "--max-connections-for-client", "4",
          "--target-addr", "1.1.1.1:53",
          (char *)NULL);
    syslog(LOG_ERR, "Falha ao executar execl para badvpn-udpgw: %m");
    exit(EXIT_FAILURE);
}

void check_and_create_pid_file() {
    FILE *f = fopen(PID_FILE, "r");
    if (f) {
        pid_t old_pid;
        if (fscanf(f, "%d", &old_pid) == 1 && kill(old_pid, 0) == 0) {
            syslog(LOG_ERR, "Processo já em execução com PID %d. A sair.", old_pid);
            fclose(f);
            exit(EXIT_FAILURE);
        }
        fclose(f);
        syslog(LOG_WARNING, "A remover ficheiro PID obsoleto (stale).");
        remove(PID_FILE);
    }
    f = fopen(PID_FILE, "w");
    if (!f) {
        syslog(LOG_ERR, "Não foi possível criar o ficheiro PID %s: %m", PID_FILE);
        exit(EXIT_FAILURE);
    }
    fprintf(f, "%d\\n", getpid());
    fclose(f);
}

int main(int argc, char** argv) {
    openlog(LOG_IDENTITY, LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "Serviço a iniciar.");
    check_and_create_pid_file();
    atexit(cleanup);
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    child_pid = fork();
    if (child_pid < 0) {
        syslog(LOG_ERR, "Falha na chamada fork: %m");
        exit(EXIT_FAILURE);
    }
    if (child_pid == 0) {
        start_badvpn();
    } else {
        syslog(LOG_INFO, "Processo filho badvpn-udpgw iniciado com PID %d", child_pid);
        while (1) {
            int status;
            waitpid(child_pid, &status, 0);
            syslog(LOG_WARNING, "Processo filho terminou. A reiniciar em 3 segundos...");
            sleep(3);
            child_pid = fork();
            if (child_pid == 0) {
                syslog(LOG_INFO, "A reiniciar o badvpn-udpgw...");
                start_badvpn();
            } else if (child_pid > 0) {
                syslog(LOG_INFO, "Processo filho reiniciado com o novo PID %d", child_pid);
            } else {
                syslog(LOG_ERR, "Falha ao reiniciar o processo (fork): %m");
                exit(EXIT_FAILURE);
            }
        }
    }
    return 0;
}
"""

# --- Constantes do Script ---
SERVICE_NAME = "badvpn.service"
SERVICE_FILE_PATH = f"/etc/systemd/system/{SERVICE_NAME}"
WRAPPER_SOURCE_PATH = "/tmp/badvpn.c"
WRAPPER_EXEC_PATH = "/usr/local/bin/badvpn_manager"
BADVPN_EXEC_PATH = "/usr/local/bin/badvpn-udpgw"

# --- Funções de Gerenciamento ---

def instalar_badvpn():
    """Compila o wrapper C, instala os binários e cria o serviço systemd."""
    print("--- Iniciando a instalação do BadVPN ---")
    
    # 1. Instalar dependências (gcc para compilação)
    print("--> Verificando dependências (gcc)...")
    os.system("apt-get update > /dev/null 2>&1")
    os.system("apt-get install -y gcc > /dev/null 2>&1")
    
    # 2. Escrever o código-fonte C num ficheiro temporário
    print(f"--> Gerando o código-fonte em {WRAPPER_SOURCE_PATH}...")
    try:
        with open(WRAPPER_SOURCE_PATH, "w") as f:
            f.write(textwrap.dedent(C_SOURCE_CODE))
    except IOError as e:
        print(f"ERRO: Falha ao escrever o ficheiro C: {e}")
        return

    # 3. Compilar o wrapper C
    print(f"--> Compilando o wrapper para {WRAPPER_EXEC_PATH}...")
    compile_cmd = f"gcc {WRAPPER_SOURCE_PATH} -o {WRAPPER_EXEC_PATH}"
    if os.system(compile_cmd) != 0:
        print("ERRO: Falha na compilação do wrapper C. Abortando.")
        return
        
    # 4. Baixar e instalar o badvpn-udpgw original
    print(f"--> Baixando e instalando o badvpn-udpgw para {BADVPN_EXEC_PATH}...")
    badvpn_url = "https://raw.githubusercontent.com/daybreakersx/premscript/master/badvpn-udpgw-master/badvpn-udpgw"
    os.system(f"wget -O {BADVPN_EXEC_PATH} {badvpn_url} > /dev/null 2>&1")
    os.system(f"chmod +x {BADVPN_EXEC_PATH}")

    # 5. Criar o ficheiro de serviço systemd
    print(f"--> Criando o serviço systemd em {SERVICE_FILE_PATH}...")
    service_content = f"""
[Unit]
Description=BadVPN UDP Gateway Wrapper by Mycroft
After=network.target

[Service]
Type=forking
PIDFile=/var/run/badvpn_wrapper.pid
ExecStart={WRAPPER_EXEC_PATH}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(SERVICE_FILE_PATH, "w") as f:
            f.write(textwrap.dedent(service_content))
    except IOError as e:
        print(f"ERRO: Falha ao escrever o ficheiro de serviço: {e}")
        return

    # 6. Recarregar o systemd, habilitar e iniciar o serviço
    print("--> Habilitando e iniciando o serviço...")
    os.system("systemctl daemon-reload")
    os.system(f"systemctl enable {SERVICE_NAME}")
    os.system(f"systemctl start {SERVICE_NAME}")
    
    # 7. Limpeza
    os.remove(WRAPPER_SOURCE_PATH)
    
    print("\n--- Instalação Concluída! ---")
    verificar_badvpn()

def desinstalar_badvpn():
    """Para e desabilita o serviço, remove todos os ficheiros criados."""
    print("--- Iniciando a desinstalação do BadVPN ---")
    
    # 1. Parar e desabilitar o serviço
    print(f"--> Parando e desabilitando o serviço {SERVICE_NAME}...")
    os.system(f"systemctl stop {SERVICE_NAME}")
    os.system(f"systemctl disable {SERVICE_NAME}")
    
    # 2. Remover os ficheiros
    files_to_remove = [SERVICE_FILE_PATH, WRAPPER_EXEC_PATH, BADVPN_EXEC_PATH, "/var/run/badvpn_wrapper.pid"]
    for f in files_to_remove:
        if os.path.exists(f):
            print(f"--> Removendo {f}...")
            os.remove(f)
            
    # 3. Recarregar o systemd
    os.system("systemctl daemon-reload")
    
    print("\n--- Desinstalação Concluída! ---")

def verificar_badvpn():
    """Verifica o status do serviço badvpn usando systemctl."""
    print("--- Status do Serviço BadVPN ---")
    status_cmd = f"systemctl status {SERVICE_NAME} | grep 'Active:'"
    result = os.popen(status_cmd).read().strip()
    if "active (running)" in result:
        print("Status: \033[92mATIVO\033[0m")
        print(result)
    else:
        print("Status: \033[91mINATIVO\033[0m")
        print(result)
    print("---------------------------------")

def menu_principal():
    """Exibe o menu principal e processa a entrada do utilizador."""
    while True:
        print("\n===== Gerenciador BadVPN (Systemd) =====")
        print("1. Instalar BadVPN")
        print("2. Desinstalar BadVPN")
        print("3. Verificar Status")
        print("4. Sair")
        print("========================================")
        
        escolha = input("Escolha uma opção: ")
        
        if escolha == '1':
            instalar_badvpn()
        elif escolha == '2':
            desinstalar_badvpn()
        elif escolha == '3':
            verificar_badvpn()
        elif escolha == '4':
            print("A sair...")
            break
        else:
            print("Opção inválida. Tente novamente.")
        
        input("\nPressione Enter para continuar...")
        os.system('clear')

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERRO: Este script precisa ser executado como root.")
        exit(1)
    os.system('clear')
    menu_principal()

