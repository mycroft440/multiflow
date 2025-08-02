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

// --- Constantes Configuráveis ---
// Template para o nome do arquivo de PID, agora específico por porta
#define PID_FILE_TEMPLATE "/var/run/badvpn_wrapper_%s.pid"
// Nome do processo para os logs do sistema
#define LOG_IDENTITY "badvpn_wrapper"

// Variáveis globais
static pid_t child_pid = 0;
// Armazena o caminho completo para o arquivo PID
char pid_file_path[256];

// Função para limpar os recursos antes de sair
void cleanup() {
    syslog(LOG_INFO, "A remover o ficheiro PID: %s", pid_file_path);
    remove(pid_file_path);
    closelog();
}

// Gestor de sinais para garantir um encerramento limpo
void handle_signal(int sig) {
    syslog(LOG_INFO, "Sinal %d recebido, a encerrar...", sig);
    
    if (child_pid > 0) {
        syslog(LOG_INFO, "A enviar sinal SIGTERM para o processo filho com PID %d", child_pid);
        kill(child_pid, SIGTERM);
    }
    
    // A função cleanup será chamada automaticamente via atexit()
    exit(0);
}

// Função para iniciar o processo badvpn-udpgw
void start_badvpn(const char* port) {
    char listen_addr[64];
    // Formata o endereço de escuta com a porta recebida
    snprintf(listen_addr, sizeof(listen_addr), "0.0.0.0:%s", port);

    syslog(LOG_INFO, "A iniciar badvpn-udpgw em %s", listen_addr);

    // Substitui a imagem do processo atual pela do badvpn-udpgw
    // Caminho comum para executáveis instalados via 'apt'
    execl("/usr/bin/badvpn-udpgw", "badvpn-udpgw",
          "--listen-addr", listen_addr,
          "--max-clients", "256",
          "--max-connections-for-client", "2",
          (char *)NULL);

    // Se execl retornar, é porque ocorreu um erro
    syslog(LOG_ERR, "Falha ao executar execl para badvpn-udpgw: %m. Verifique se 'badvpn-udpgw' está instalado.");
    exit(EXIT_FAILURE);
}

// Função para verificar e criar o ficheiro PID
void check_and_create_pid_file() {
    FILE *f = fopen(pid_file_path, "r");
    if (f) {
        pid_t old_pid;
        if (fscanf(f, "%d", &old_pid) == 1) {
            if (kill(old_pid, 0) == 0) {
                syslog(LOG_ERR, "Processo para a porta já em execução com PID %d. A sair.", old_pid);
                fclose(f);
                exit(EXIT_FAILURE);
            }
        }
        fclose(f);
        syslog(LOG_WARNING, "A remover ficheiro PID obsoleto (stale).");
        remove(pid_file_path);
    }

    f = fopen(pid_file_path, "w");
    if (!f) {
        syslog(LOG_ERR, "Não foi possível criar o ficheiro PID %s: %m", pid_file_path);
        exit(EXIT_FAILURE);
    }
    fprintf(f, "%d\n", getpid());
    fclose(f);
}

int main(int argc, char** argv) {
    // Valida se o argumento da porta foi fornecido
    if (argc != 2) {
        fprintf(stderr, "Uso: %s <porta>\n", argv[0]);
        exit(EXIT_FAILURE);
    }
    const char* port = argv[1];

    // Configura o caminho do arquivo PID e o syslog
    snprintf(pid_file_path, sizeof(pid_file_path), PID_FILE_TEMPLATE, port);
    openlog(LOG_IDENTITY, LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "Serviço a iniciar para a porta %s.", port);

    check_and_create_pid_file();
    
    // Registra a função de limpeza para ser chamada na saída
    atexit(cleanup);
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    // Loop de monitorização e reinicialização
    while (1) {
        child_pid = fork();

        if (child_pid < 0) {
            syslog(LOG_ERR, "Falha na chamada fork: %m");
            exit(EXIT_FAILURE);
        }

        if (child_pid == 0) {
            // --- Processo Filho ---
            start_badvpn(port); // Passa a porta para a função
        } else {
            // --- Processo Pai (Wrapper) ---
            syslog(LOG_INFO, "Processo filho badvpn-udpgw iniciado com PID %d para a porta %s", child_pid, port);
            
            int status;
            waitpid(child_pid, &status, 0); // Espera pelo término do filho

            // Se o processo foi terminado por um sinal (ex: kill), o wrapper também encerra.
            if (WIFSIGNALED(status)) {
                syslog(LOG_INFO, "Processo filho terminado por sinal. Encerrando o wrapper.");
                break; 
            }

            syslog(LOG_WARNING, "Processo filho para a porta %s terminou inesperadamente. A reiniciar em 3 segundos...", port);
            sleep(3);
        }
    }

    return 0;
}
