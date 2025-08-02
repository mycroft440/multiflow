#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <dirent.h>
#include <signal.h>

// Função para verificar se um processo com um determinado nome já está em execução
int process_exist(const char* process_name) {
    DIR* dir = opendir("/proc");
    if (dir == NULL) {
        perror("opendir");
        return -1;
    }

    struct dirent* entry;
    while ((entry = readdir(dir)) != NULL) {
        // Verifica se a entrada é um diretório numérico (correspondente a um PID)
        int pid = atoi(entry->d_name);
        if (pid > 0) {
            char path[256];
            snprintf(path, sizeof(path), "/proc/%d/comm", pid);

            FILE* fp = fopen(path, "r");
            if (fp != NULL) {
                char name[256];
                if (fgets(name, sizeof(name), fp) != NULL) {
                    // Remove a nova linha do final do nome do processo
                    name[strcspn(name, "\n")] = '\0';
                    if (strcmp(name, process_name) == 0) {
                        fclose(fp);
                        closedir(dir);
                        return 1; // Processo encontrado
                    }
                }
                fclose(fp);
            }
        }
    }

    closedir(dir);
    return 0; // Processo não encontrado
}

int main(int argc, char** argv) {
    // Verifica se o badvpn-udpgw já está em execução
    if (process_exist("badvpn-udpgw")) {
        printf("badvpn-udpgw já está em execução.\n");
        return 1;
    }

    pid_t pid = fork();

    if (pid < 0) {
        perror("fork");
        return 1;
    }

    if (pid == 0) {
        // Processo filho: executa o badvpn-udpgw
        printf("Iniciando o badvpn-udpgw...\n");
        
        // MUDANÇA: Adicionado --target-addr para apontar para o DNS da Cloudflare
        execl("/bin/badvpn-udpgw", "badvpn-udpgw", 
              "--listen-addr", "127.0.0.1:7300", 
              "--max-clients", "256", 
              "--max-connections-for-client", "2",
              "--target-addr", "1.1.1.1:53", // Encaminha para o DNS da Cloudflare
              (char *)NULL);

        // Se execl retornar, houve um erro
        perror("execl");
        exit(1);
    } else {
        // Processo pai: monitora o processo filho
        int status;
        while (1) {
            waitpid(pid, &status, 0);
            printf("badvpn-udpgw terminou. Reiniciando em 3 segundos...\n");
            sleep(3);
            
            pid = fork();
            if (pid == 0) {
                // Novo processo filho
                printf("Reiniciando o badvpn-udpgw...\n");
                
                // MUDANÇA: Adicionado --target-addr para apontar para o DNS da Cloudflare
                execl("/bin/badvpn-udpgw", "badvpn-udpgw", 
                      "--listen-addr", "127.0.0.1:7300", 
                      "--max-clients", "256", 
                      "--max-connections-for-client", "2",
                      "--target-addr", "1.1.1.1:53", // Encaminha para o DNS da Cloudflare
                      (char *)NULL);

                perror("execl");
                exit(1);
            }
        }
    }

    return 0;
}
