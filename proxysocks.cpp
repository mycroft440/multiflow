#include <iostream>
#include <string>
#include <vector>
#include <queue>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <netdb.h>
#include <sys/select.h>
#include <signal.h>
#include <mutex>
#include <atomic>
#include <condition_variable>
#include <sys/types.h>
#include <sys/time.h>
#include <netinet/tcp.h>
#include <sys/epoll.h>
#include <fcntl.h>
#include <sys/sendfile.h>  // Para splice
#include <sys/stat.h>
#include <errno.h>

const std::string IP = "0.0.0.0";
int PORT = 80;
const std::string PASS = "";  // Senha vazia por padrão
const size_t BUFLEN = 131072;  // Otimizado para 128KB
const int TIMEOUT = 60;
const std::string MSG = "@TMYCOMNECTVPN";
const std::string COR = "<font color=\"null\">";
const std::string FTAG = "</font>";
const std::string DEFAULT_HOST = "0.0.0.0:22";
const std::string RESPONSE = "HTTP/1.1 200 " + COR + MSG + FTAG + "\r\n\r\n";

const int EPOLL_EVENTS = 2000;  // Max events por epoll_wait
const int THREAD_POOL_SIZE = 4;  // Threads fixas no pool

std::mutex logMutex;
std::atomic<bool> running(true);

void printLog(const std::string& log) {
    std::lock_guard<std::mutex> guard(logMutex);
    std::cout << log << std::endl;
}

// Queue para logging assíncrono simples
std::queue<std::string> logQueue;
std::mutex logQueueMutex;
std::condition_variable logCond;
std::thread logThread;

void asyncLogWorker() {
    while (running || !logQueue.empty()) {
        std::unique_lock<std::mutex> lock(logQueueMutex);
        logCond.wait(lock, [&] { return !logQueue.empty() || !running; });
        if (!logQueue.empty()) {
            std::string log = logQueue.front();
            logQueue.pop();
            lock.unlock();
            printLog(log);
        }
    }
}

void asyncLog(const std::string& log) {
    std::lock_guard<std::mutex> lock(logQueueMutex);
    logQueue.push(log);
    logCond.notify_one();
}

std::string findHeader(const std::string& head, const std::string& header) {
    size_t aux = head.find(header + ": ");
    if (aux == std::string::npos) return "";
    aux = head.find(':', aux);
    if (aux == std::string::npos) return "";
    std::string sub = head.substr(aux + 2);
    aux = sub.find("\r\n");
    if (aux == std::string::npos) return "";
    return sub.substr(0, aux);
}

struct ConnectionHandler {
    int clientSock;
    int targetSock = -1;
    std::string logStr;
    bool clientClosed = false;
    bool targetClosed = true;
    int epollFd = -1;  // Para epoll no túnel

    ConnectionHandler(int sock, const std::string& addr) : clientSock(sock) {
        logStr = "Conexao: " + addr;
    }

    ~ConnectionHandler() {
        close();
        if (epollFd != -1) ::close(epollFd);
    }

    void close() {
        if (!clientClosed && clientSock != -1) {
            shutdown(clientSock, SHUT_RDWR);
            ::close(clientSock);
            clientClosed = true;
        }
        if (!targetClosed && targetSock != -1) {
            shutdown(targetSock, SHUT_RDWR);
            ::close(targetSock);
            targetClosed = true;
        }
    }

    bool setNonBlocking(int sock) {
        int flags = fcntl(sock, F_GETFL, 0);
        if (flags == -1) return false;
        return fcntl(sock, F_SETFL, flags | O_NONBLOCK) != -1;
    }

    bool connectTarget(const std::string& hostPort) {
        size_t colonPos = hostPort.find(':');
        std::string host = (colonPos != std::string::npos) ? hostPort.substr(0, colonPos) : hostPort;
        int port = (colonPos != std::string::npos) ? std::stoi(hostPort.substr(colonPos + 1)) : 22;

        struct addrinfo hints, *res;
        memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;

        if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &res) != 0) {
            asyncLog(logStr + " - Erro getaddrinfo: " + std::string(strerror(errno)));
            return false;
        }

        targetSock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
        if (targetSock == -1) {
            asyncLog(logStr + " - Erro socket: " + std::string(strerror(errno)));
            freeaddrinfo(res);
            return false;
        }

        if (!setNonBlocking(targetSock)) {
            asyncLog(logStr + " - Erro non-blocking target: " + std::string(strerror(errno)));
            ::close(targetSock);
            freeaddrinfo(res);
            return false;
        }

        int opt = 1;
        setsockopt(targetSock, SOL_SOCKET, SO_KEEPALIVE, &opt, sizeof(opt));
        setsockopt(targetSock, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));  // Low-latency
#ifdef __linux__
        int idle = 10;
        setsockopt(targetSock, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof(idle));
        int cnt = 3;
        setsockopt(targetSock, IPPROTO_TCP, TCP_KEEPCNT, &cnt, sizeof(cnt));
        int intvl = 5;
        setsockopt(targetSock, IPPROTO_TCP, TCP_KEEPINTVL, &intvl, sizeof(intvl));
#endif

        if (connect(targetSock, res->ai_addr, res->ai_addrlen) == -1) {
            if (errno != EINPROGRESS) {
                asyncLog(logStr + " - Erro connect: " + std::string(strerror(errno)));
                ::close(targetSock);
                freeaddrinfo(res);
                return false;
            }
            // Handle non-blocking connect if needed, but for simplicity assume blocking ok post-set
        }

        targetClosed = false;
        freeaddrinfo(res);
        return true;
    }

    void handle() {
        try {
            if (!setNonBlocking(clientSock)) {
                asyncLog(logStr + " - Erro non-blocking client: " + std::string(strerror(errno)));
                return;
            }

            char buffer[BUFLEN];
            memset(buffer, 0, BUFLEN);
            ssize_t len = recv(clientSock, buffer, BUFLEN - 1, 0);
            if (len <= 0) {
                asyncLog(logStr + " - Erro recv inicial: " + std::string(strerror(errno)));
                return;
            }
            std::string clientBuffer(buffer, len);

            std::string hostPort = findHeader(clientBuffer, "X-Real-Host");
            if (hostPort.empty()) hostPort = DEFAULT_HOST;

            std::string split = findHeader(clientBuffer, "X-Split");
            if (!split.empty()) {
                recv(clientSock, buffer, BUFLEN, MSG_DONTWAIT);  // Non-blocking extra
            }

            std::string passwd = findHeader(clientBuffer, "X-Pass");

            bool allowed = false;
            if (!PASS.empty() && passwd == PASS) allowed = true;
            else if (hostPort.find(IP) == 0) allowed = true;

            if (!allowed) {
                std::string errResp = (!PASS.empty() && passwd != PASS) ? "HTTP/1.1 400 WrongPass!\r\n\r\n" : "HTTP/1.1 403 Forbidden!\r\n\r\n";
                send(clientSock, errResp.c_str(), errResp.size(), 0);
                asyncLog(logStr + " - Acesso negado");
                return;
            }

            if (!connectTarget(hostPort)) {
                std::string errResp = "HTTP/1.1 502 Bad Gateway!\r\n\r\n";
                send(clientSock, errResp.c_str(), errResp.size(), 0);
                return;
            }

            int opt = 1;
            setsockopt(clientSock, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));  // Low-latency

            send(clientSock, RESPONSE.c_str(), RESPONSE.size(), 0);
            asyncLog(logStr + " - CONNECT " + hostPort);

            // Epoll para túnel
            epollFd = epoll_create1(0);
            if (epollFd == -1) {
                asyncLog(logStr + " - Erro epoll_create: " + std::string(strerror(errno)));
                return;
            }

            struct epoll_event ev;
            ev.events = EPOLLIN | EPOLLET;  // Edge-triggered
            ev.data.fd = clientSock;
            if (epoll_ctl(epollFd, EPOLL_CTL_ADD, clientSock, &ev) == -1) {
                asyncLog(logStr + " - Erro epoll_ctl client: " + std::string(strerror(errno)));
                return;
            }
            ev.data.fd = targetSock;
            if (epoll_ctl(epollFd, EPOLL_CTL_ADD, targetSock, &ev) == -1) {
                asyncLog(logStr + " - Erro epoll_ctl target: " + std::string(strerror(errno)));
                return;
            }

            struct epoll_event events[2];
            int count = 0;
            while (true) {
                int nfds = epoll_wait(epollFd, events, 2, 1000);  // Timeout granular 1s
                if (nfds == -1) {
                    if (errno == EINTR) continue;
                    asyncLog(logStr + " - Erro epoll_wait: " + std::string(strerror(errno)));
                    break;
                }
                if (nfds == 0) {
                    count++;
                    if (count >= TIMEOUT) {
                        asyncLog(logStr + " - Timeout atingido");
                        break;
                    }
                    continue;
                }

                count = 0;
                for (int i = 0; i < nfds; ++i) {
                    int fd = events[i].data.fd;
                    if (events[i].events & (EPOLLERR | EPOLLHUP)) {
                        asyncLog(logStr + " - Erro epoll event em fd " + std::to_string(fd));
                        break;
                    }

                    if (fd == clientSock) {
                        // Zero-copy splice client -> target
                        ssize_t spliced = splice(clientSock, nullptr, targetSock, nullptr, BUFLEN, SPLICE_F_MOVE | SPLICE_F_NONBLOCK);
                        if (spliced <= 0) {
                            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                                asyncLog(logStr + " - Erro splice client->target: " + std::string(strerror(errno)));
                                break;
                            }
                            // Fallback recv/send se splice falhar
                            len = recv(clientSock, buffer, BUFLEN, MSG_DONTWAIT);
                            if (len <= 0) break;
                            ssize_t sent = send(targetSock, buffer, len, MSG_DONTWAIT);
                            if (sent <= 0) break;
                        }
                    } else if (fd == targetSock) {
                        // Zero-copy splice target -> client
                        ssize_t spliced = splice(targetSock, nullptr, clientSock, nullptr, BUFLEN, SPLICE_F_MOVE | SPLICE_F_NONBLOCK);
                        if (spliced <= 0) {
                            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                                asyncLog(logStr + " - Erro splice target->client: " + std::string(strerror(errno)));
                                break;
                            }
                            // Fallback
                            len = recv(targetSock, buffer, BUFLEN, MSG_DONTWAIT);
                            if (len <= 0) break;
                            ssize_t sent = send(clientSock, buffer, len, MSG_DONTWAIT);
                            if (sent <= 0) break;
                        }
                    }
                }
            }
        } catch (const std::exception& e) {
            asyncLog(logStr + " - Excecao: " + std::string(e.what()));
        } catch (...) {
            asyncLog(logStr + " - Erro desconhecido");
        }
    }
};

// Queue para tasks do thread pool
std::queue<ConnectionHandler*> taskQueue;
std::mutex taskMutex;
std::condition_variable taskCond;
std::vector<std::thread> poolThreads;

void poolWorker() {
    while (running) {
        std::unique_lock<std::mutex> lock(taskMutex);
        taskCond.wait(lock, [&] { return !taskQueue.empty() || !running; });
        if (!taskQueue.empty()) {
            ConnectionHandler* handler = taskQueue.front();
            taskQueue.pop();
            lock.unlock();
            handler->handle();
            delete handler;
        }
    }
}

void enqueueTask(ConnectionHandler* handler) {
    std::lock_guard<std::mutex> lock(taskMutex);
    taskQueue.push(handler);
    taskCond.notify_one();
}

void signalHandler(int sig) {
    running = false;
    taskCond.notify_all();
    logCond.notify_all();
}

int main(int argc, char* argv[]) {
    if (argc > 1) PORT = std::stoi(argv[1]);

    system("clear");
    std::cout << "\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[1;32m PROXY SOCKS \033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━" << std::endl;
    std::cout << "\033[1;33mIP:\033[1;32m " << IP << std::endl;
    std::cout << "\033[1;33mPORTA:\033[1;32m " << PORT << std::endl;
    std::cout << "\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[0;34m━\033[1;32m MULTIFLOW \033[0;34m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━\033[1;37m━" << std::endl;

    signal(SIGINT, signalHandler);

    // Inicia thread pool
    for (int i = 0; i < THREAD_POOL_SIZE; ++i) {
        poolThreads.emplace_back(poolWorker);
    }

    // Inicia logger assíncrono
    logThread = std::thread(asyncLogWorker);

    int serverSock = socket(AF_INET, SOCK_STREAM, 0);
    if (serverSock == -1) {
        std::cerr << "Erro ao criar socket: " << strerror(errno) << std::endl;
        return 1;
    }

    int opt = 1;
    setsockopt(serverSock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(PORT);
    inet_pton(AF_INET, IP.c_str(), &addr.sin_addr);

    if (bind(serverSock, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
        std::cerr << "Erro ao bind: " << strerror(errno) << std::endl;
        ::close(serverSock);
        return 1;
    }

    if (listen(serverSock, SOMAXCONN) == -1) {
        std::cerr << "Erro ao listen: " << strerror(errno) << std::endl;
        ::close(serverSock);
        return 1;
    }

    while (running) {
        struct sockaddr_in clientAddr;
        socklen_t addrLen = sizeof(clientAddr);
        int clientSock = accept(serverSock, (struct sockaddr*)&clientAddr, &addrLen);
        if (clientSock == -1) {
            if (errno == EINTR || !running) break;
            asyncLog("Erro accept: " + std::string(strerror(errno)));
            continue;
        }

        char ipStr[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &clientAddr.sin_addr, ipStr, sizeof(ipStr));
        std::string addrStr = std::string(ipStr) + ":" + std::to_string(ntohs(clientAddr.sin_port));

        ConnectionHandler* handler = new ConnectionHandler(clientSock, addrStr);
        enqueueTask(handler);
    }

    ::close(serverSock);

    // Shutdown gracioso
    for (auto& t : poolThreads) {
        if (t.joinable()) t.join();
    }
    if (logThread.joinable()) logThread.join();

    std::cout << "\nParando..." << std::endl;
    return 0;
}