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
// Caminho para o ficheiro que armazenará o PID do processo principal.
// Nota: Escrever em /var/run/ pode exigir privilégios de root.
#define PID_FILE "/var/run/badvpn_wrapper.pid"
// Nome do processo a ser exibido nos logs do sistema.
#define LOG_IDENTITY "badvpn_wrapper"

// Variável global para armazenar o PID do processo filho (badvpn-udpgw)
// Isto é necessário para que o gestor de sinais possa terminá-lo.
static pid_t child_pid = 0;

// Função para limpar os recursos antes de sair
void cleanup() {
    syslog(LOG_INFO, "A remover o ficheiro PID: %s", PID_FILE);
    remove(PID_FILE);
    closelog();
}

// Gestor de sinais para garantir um encerramento limpo
void handle_signal(int sig) {
    syslog(LOG_INFO, "Sinal %d recebido, a encerrar...", sig);
    
    // Se o processo filho estiver a ser executado, termina-o
    if (child_pid > 0) {
        syslog(LOG_INFO, "A enviar sinal SIGTERM para o processo filho com PID %d", child_pid);
        kill(child_pid, SIGTERM);
    }
    
    cleanup();
    exit(0);
}

// Função para iniciar o processo badvpn-udpgw
void start_badvpn() {
    // Substitui a imagem do processo atual pela do badvpn-udpgw
    execl("/bin/badvpn-udpgw", "badvpn-udpgw",
          "--listen-addr", "127.0.0.1:7300",
          "--max-clients", "256",
          "--max-connections-for-client", "2",
          "--target-addr", "1.1.1.1:53",
          (char *)NULL);

    // Se execl retornar, é porque ocorreu um erro
    syslog(LOG_ERR, "Falha ao executar execl para badvpn-udpgw: %m");
    exit(EXIT_FAILURE);
}

// Função para verificar e criar o ficheiro PID
void check_and_create_pid_file() {
    FILE *f = fopen(PID_FILE, "r");
    if (f) {
        // Ficheiro PID existe, verifica se o processo ainda está ativo
        pid_t old_pid;
        if (fscanf(f, "%d", &old_pid) == 1) {
            // kill(pid, 0) não envia um sinal, mas verifica se o processo existe
            if (kill(old_pid, 0) == 0) {
                syslog(LOG_ERR, "Processo já em execução com PID %d. A sair.", old_pid);
                fclose(f);
                exit(EXIT_FAILURE);
            }
        }
        fclose(f);
        syslog(LOG_WARNING, "A remover ficheiro PID obsoleto (stale).");
        remove(PID_FILE);
    }

    // Cria o novo ficheiro PID com o PID do processo atual
    f = fopen(PID_FILE, "w");
    if (!f) {
        syslog(LOG_ERR, "Não foi possível criar o ficheiro PID %s: %m", PID_FILE);
        exit(EXIT_FAILURE);
    }
    fprintf(f, "%d\n", getpid());
    fclose(f);
}


int main(int argc, char** argv) {
    // Abre a conexão com o logger do sistema (syslog)
    openlog(LOG_IDENTITY, LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "Serviço a iniciar.");

    // Garante que apenas uma instância está em execução usando um ficheiro PID
    check_and_create_pid_file();
    
    // Regista a função de limpeza para ser chamada na saída normal
    atexit(cleanup);

    // Regista os gestores de sinais para um encerramento controlado
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    // Cria o processo filho
    child_pid = fork();

    if (child_pid < 0) {
        syslog(LOG_ERR, "Falha na chamada fork: %m");
        exit(EXIT_FAILURE);
    }

    if (child_pid == 0) {
        // --- Processo Filho ---
        // Inicia o badvpn-udpgw. Esta função não retorna em caso de sucesso.
        start_badvpn();
    } else {
        // --- Processo Pai ---
        syslog(LOG_INFO, "Processo filho badvpn-udpgw iniciado com PID %d", child_pid);
        
        // Loop de monitorização e reinicialização
        while (1) {
            int status;
            waitpid(child_pid, &status, 0); // Espera pelo término do filho

            syslog(LOG_WARNING, "Processo filho terminou. A reiniciar em 3 segundos...");
            sleep(3);

            child_pid = fork();
            if (child_pid == 0) {
                // Novo processo filho
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

    return 0; // Inalcançável, mas bom para a completude
}
