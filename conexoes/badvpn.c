#include <stdio.h>

#include <stdlib.h>

#include <string.h>

#include <unistd.h>

#include <sys/types.h>

#include <sys/socket.h>

#include <netinet/in.h>

#include <arpa/inet.h>

#include <sys/epoll.h>

#include <errno.h>

#include <fcntl.h>



#define MAX_EVENTS 10000  // Suporte para milhares de eventos

#define BUFFER_SIZE 65536  // Tamanho máximo de pacote UDP + overhead

#define LISTEN_PORT 7300   // Porta TCP de escuta (ajustável)

#define MAX_CLIENTS 10000  // Limite de clientes (ajustável)



// Estrutura para armazenar estado de cada cliente

typedef struct {

    int tcp_fd;            // Socket TCP do cliente

    int udp_fd;            // Socket UDP associado

    struct sockaddr_in udp_addr;  // Endereço UDP destino

    char buffer[BUFFER_SIZE];     // Buffer para dados

    size_t buf_len;               // Comprimento atual no buffer

} ClientState;



ClientState clients[MAX_CLIENTS];

int client_count = 0;



void set_non_blocking(int fd) {

    int flags = fcntl(fd, F_GETFL, 0);

    fcntl(fd, F_SETFL, flags | O_NONBLOCK);

}



int main() {

    int tcp_listen_fd = socket(AF_INET, SOCK_STREAM, 0);

    if (tcp_listen_fd < 0) {

        perror("Erro ao criar socket TCP");

        exit(1);

    }



    struct sockaddr_in server_addr;

    memset(&server_addr, 0, sizeof(server_addr));

    server_addr.sin_family = AF_INET;

    server_addr.sin_addr.s_addr = INADDR_ANY;

    server_addr.sin_port = htons(LISTEN_PORT);



    if (bind(tcp_listen_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {

        perror("Erro no bind");

        close(tcp_listen_fd);

        exit(1);

    }



    if (listen(tcp_listen_fd, SOMAXCONN) < 0) {

        perror("Erro no listen");

        close(tcp_listen_fd);

        exit(1);

    }



    set_non_blocking(tcp_listen_fd);



    int epoll_fd = epoll_create1(0);

    if (epoll_fd < 0) {

        perror("Erro ao criar epoll");

        exit(1);

    }



    struct epoll_event ev;

    ev.events = EPOLLIN;

    ev.data.fd = tcp_listen_fd;

    if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, tcp_listen_fd, &ev) < 0) {

        perror("Erro ao adicionar epoll");

        exit(1);

    }



    struct epoll_event events[MAX_EVENTS];



    printf("Servidor UDPGW iniciado na porta %d\n", LISTEN_PORT);



    while (1) {

        int nfds = epoll_wait(epoll_fd, events, MAX_EVENTS, -1);

        if (nfds < 0) {

            perror("Erro no epoll_wait");

            continue;

        }



        for (int i = 0; i < nfds; i++) {

            if (events[i].data.fd == tcp_listen_fd) {

                // Nova conexão TCP

                struct sockaddr_in client_addr;

                socklen_t addr_len = sizeof(client_addr);

                int tcp_fd = accept(tcp_listen_fd, (struct sockaddr*)&client_addr, &addr_len);

                if (tcp_fd < 0) continue;



                if (client_count >= MAX_CLIENTS) {

                    close(tcp_fd);

                    continue;

                }



                set_non_blocking(tcp_fd);



                // Criar socket UDP para este cliente

                int udp_fd = socket(AF_INET, SOCK_DGRAM, 0);

                if (udp_fd < 0) {

                    close(tcp_fd);

                    continue;

                }

                set_non_blocking(udp_fd);



                // Adicionar TCP e UDP ao epoll

                ev.events = EPOLLIN | EPOLLET;

                ev.data.fd = tcp_fd;

                epoll_ctl(epoll_fd, EPOLL_CTL_ADD, tcp_fd, &ev);

                ev.data.fd = udp_fd;

                epoll_ctl(epoll_fd, EPOLL_CTL_ADD, udp_fd, &ev);



                // Armazenar estado

                clients[client_count].tcp_fd = tcp_fd;

                clients[client_count].udp_fd = udp_fd;

                clients[client_count].buf_len = 0;

                client_count++;

            } else {

                // Encontrar o cliente correspondente

                int j;

                int is_tcp = 1;

                ClientState* client = NULL;

                for (j = 0; j < client_count; j++) {

                    if (clients[j].tcp_fd == events[i].data.fd) {

                        client = &clients[j];

                        break;

                    } else if (clients[j].udp_fd == events[i].data.fd) {

                        client = &clients[j];

                        is_tcp = 0;

                        break;

                    }

                }

                if (!client) continue;



                if (events[i].events & EPOLLERR || events[i].events & EPOLLHUP) {

                    // Erro ou desconexão: fechar

                    close(client->tcp_fd);

                    close(client->udp_fd);

                    // Remover do array (simples shift para simplicidade)

                    memmove(&clients[j], &clients[j+1], (client_count - j - 1) * sizeof(ClientState));

                    client_count--;

                    continue;

                }



                if (is_tcp) {

                    // Dados do TCP: ler e encaminhar para UDP

                    ssize_t len = recv(client->tcp_fd, client->buffer + client->buf_len, BUFFER_SIZE - client->buf_len, MSG_DONTWAIT);

                    if (len <= 0) {

                        if (errno != EAGAIN) {

                            // Desconexão

                            close(client->tcp_fd);

                            close(client->udp_fd);

                            memmove(&clients[j], &clients[j+1], (client_count - j - 1) * sizeof(ClientState));

                            client_count--;

                        }

                        continue;

                    }

                    client->buf_len += len;



                    // Processar pacotes completos (cabeçalho: uint32_t tamanho)

                    while (client->buf_len >= 4) {

                        uint32_t pkt_size;

                        memcpy(&pkt_size, client->buffer, 4);

                        pkt_size = ntohl(pkt_size);

                        if (client->buf_len < 4 + pkt_size) break;



                        // Extrair endereço UDP do pacote (assumindo formato: tamanho + addr_len + addr + data)

                        // Para simplicidade, assuma destino fixo ou parseie; aqui, forwarding direto para um destino exemplo

                        // Ajuste para parsear addr de destino real se necessário

                        struct sockaddr_in dest_addr;

                        memset(&dest_addr, 0, sizeof(dest_addr));

                        dest_addr.sin_family = AF_INET;

                        dest_addr.sin_addr.s_addr = inet_addr("8.8.8.8");  // Exemplo: DNS Google; ajuste dinamicamente

                        dest_addr.sin_port = htons(53);  // Exemplo porta



                        sendto(client->udp_fd, client->buffer + 4, pkt_size, 0, (struct sockaddr*)&dest_addr, sizeof(dest_addr));



                        // Shift buffer

                        memmove(client->buffer, client->buffer + 4 + pkt_size, client->buf_len - 4 - pkt_size);

                        client->buf_len -= 4 + pkt_size;

                    }

                } else {

                    // Dados do UDP: ler e encaminhar para TCP

                    struct sockaddr_in src_addr;

                    socklen_t addr_len = sizeof(src_addr);

                    ssize_t len = recvfrom(client->udp_fd, client->buffer + 4, BUFFER_SIZE - 4, MSG_DONTWAIT, (struct sockaddr*)&src_addr, &addr_len);

                    if (len <= 0) continue;



                    // Adicionar cabeçalho de tamanho

                    uint32_t pkt_size = htonl(len);

                    memcpy(client->buffer, &pkt_size, 4);



                    // Enviar de volta pelo TCP

                    send(client->tcp_fd, client->buffer, 4 + len, MSG_DONTWAIT | MSG_NOSIGNAL);

                }

            }

        }

    }



    close(epoll_fd);

    close(tcp_listen_fd);

    return 0;



}
