#include <iostream>
#include <boost/asio.hpp>
#include <memory>
#include <vector>
#include <array>
#include <netinet/in.h>
#include <limits>
#include <string>
#include <cstdlib>
#include <unistd.h>
#include <sys/wait.h>

using boost::asio::ip::tcp;
using boost::asio::io_context;
using boost::system::error_code;
using boost::asio::steady_timer;

namespace socks5 {

class ReverseSSHProxy {
public:
    ReverseSSHProxy(const std::string& ssh_server, int ssh_port, 
                   const std::string& username, const std::string& password,
                   int local_port, int remote_port) 
        : ssh_server_(ssh_server), ssh_port_(ssh_port), username_(username), 
          password_(password), local_port_(local_port), remote_port_(remote_port) {}

    bool start() {
        std::cout << "Iniciando túnel SSH reverso..." << std::endl;
        std::cout << "Servidor SSH: " << ssh_server_ << ":" << ssh_port_ << std::endl;
        std::cout << "Túnel: " << remote_port_ << " (remoto) -> " << local_port_ << " (local)" << std::endl;

        // Comando SSH para túnel reverso: ssh -R remote_port:localhost:local_port user@server
        std::string ssh_command = "sshpass -p '" + password_ + "' ssh -o StrictHostKeyChecking=no -R " + 
                                 std::to_string(remote_port_) + ":localhost:" + std::to_string(local_port_) + 
                                 " " + username_ + "@" + ssh_server_ + " -N";

        std::cout << "Executando: " << ssh_command << std::endl;

        // Executa o comando SSH em background
        pid_t pid = fork();
        if (pid == 0) {
            // Processo filho - executa o comando SSH
            system(ssh_command.c_str());
            exit(0);
        } else if (pid > 0) {
            // Processo pai - continua
            ssh_pid_ = pid;
            std::cout << "Túnel SSH reverso iniciado (PID: " << pid << ")" << std::endl;
            return true;
        } else {
            std::cerr << "Erro ao criar processo para SSH" << std::endl;
            return false;
        }
    }

    void stop() {
        if (ssh_pid_ > 0) {
            std::cout << "Parando túnel SSH reverso..." << std::endl;
            kill(ssh_pid_, SIGTERM);
            waitpid(ssh_pid_, nullptr, 0);
            ssh_pid_ = 0;
        }
    }

    ~ReverseSSHProxy() {
        stop();
    }

private:
    std::string ssh_server_;
    int ssh_port_;
    std::string username_;
    std::string password_;
    int local_port_;
    int remote_port_;
    pid_t ssh_pid_ = 0;
};

class Session : public std::enable_shared_from_this<Session> {
public:
    Session(io_context& io_ctx) : io_ctx_(io_ctx), client_socket_(io_ctx), remote_socket_(io_ctx),
                                  timer_(io_ctx) {}

    tcp::socket& client_socket() { return client_socket_; }

    void start() {
        std::cout << "Nova sessão iniciada" << std::endl;
        set_timeout(30);  // 30s timeout para handshake
        read_handshake();
    }

private:
    void set_timeout(int seconds) {
        timer_.expires_after(std::chrono::seconds(seconds));
        auto self(shared_from_this());
        timer_.async_wait([this, self](error_code ec) {
            if (!ec) {
                std::cout << "Timeout expirado" << std::endl;
                handle_error(boost::asio::error::timed_out);
            }
        });
    }

    void cancel_timeout() {
        timer_.cancel();
    }

    void read_handshake() {
        auto self(shared_from_this());
        boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 2),
            [this, self](error_code ec, std::size_t) {
                if (ec) { return handle_error(ec); }
                if (buffer_[0] != 0x05) { return handle_error(boost::asio::error::invalid_argument); }
                uint8_t nmethods = buffer_[1];
                boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, nmethods),
                    [this, self, nmethods](error_code ec, std::size_t) {
                        if (ec) { return handle_error(ec); }
                        bool no_auth = false;
                        for (uint8_t i = 0; i < nmethods; ++i) {
                            if (buffer_[i] == 0x00) { no_auth = true; break; }
                        }
                        if (!no_auth) {
                            uint8_t reply[2] = {0x05, 0xFF};
                            boost::asio::async_write(client_socket_, boost::asio::buffer(reply, 2),
                                [this, self](error_code ec, std::size_t) { handle_error(ec); });
                            return;
                        }
                        uint8_t reply[2] = {0x05, 0x00};
                        boost::asio::async_write(client_socket_, boost::asio::buffer(reply, 2),
                            [this, self](error_code ec, std::size_t) {
                                if (ec) { return handle_error(ec); }
                                cancel_timeout();
                                set_timeout(30);  // Novo timeout para request
                                read_request();
                            });
                    });
            });
    }

    void read_request() {
        auto self(shared_from_this());
        boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 4),
            [this, self](error_code ec, std::size_t) {
                if (ec) { return handle_error(ec); }
                if (buffer_[0] != 0x05 || buffer_[1] != 0x01) { // Apenas CONNECT
                    send_reply(0x07); return; // Comando não suportado
                }
                uint8_t atype = buffer_[3];
                std::string dest_addr;
                uint16_t dest_port = 0;
                if (atype == 0x01) { // IPv4
                    boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 4),
                        [this, self, &dest_addr, &dest_port](error_code ec, std::size_t) {
                            if (ec) { return handle_error(ec); }
                            uint32_t ip = ntohl(*reinterpret_cast<uint32_t*>(buffer_.data()));
                            dest_addr = boost::asio::ip::make_address_v4(ip).to_string();
                            read_port(dest_addr, dest_port);
                        });
                } else if (atype == 0x03) { // Domínio
                    boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 1),
                        [this, self, &dest_addr, &dest_port](error_code ec, std::size_t) {
                            if (ec) { return handle_error(ec); }
                            uint8_t len = buffer_[0];
                            boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, len),
                                [this, self, &dest_addr, &dest_port, len](error_code ec, std::size_t) {
                                    if (ec) { return handle_error(ec); }
                                    dest_addr.assign(reinterpret_cast<char*>(buffer_.data()), len);
                                    read_port(dest_addr, dest_port);
                                });
                        });
                } else if (atype == 0x04) { // IPv6
                    boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 16),
                        [this, self, &dest_addr, &dest_port](error_code ec, std::size_t) {
                            if (ec) { return handle_error(ec); }
                            boost::asio::ip::address_v6::bytes_type bytes;
                            std::copy(buffer_.begin(), buffer_.begin() + 16, bytes.begin());
                            dest_addr = boost::asio::ip::make_address_v6(bytes).to_string();
                            read_port(dest_addr, dest_port);
                        });
                } else {
                    send_reply(0x08); // Tipo de endereço não suportado
                }
            });
    }

    void read_port(const std::string& dest_addr, uint16_t& dest_port) {
        auto self(shared_from_this());
        boost::asio::async_read(client_socket_, boost::asio::buffer(buffer_, 2),
            [this, self, dest_addr, &dest_port](error_code ec, std::size_t) {
                if (ec) { return handle_error(ec); }
                dest_port = ntohs(*reinterpret_cast<uint16_t*>(buffer_.data()));
                std::cout << "Conectando a " << dest_addr << ":" << dest_port << std::endl;
                connect_remote(dest_addr, dest_port);
            });
    }

    void connect_remote(const std::string& dest_addr, uint16_t dest_port) {
        auto self(shared_from_this());
        tcp::resolver resolver(io_ctx_);

        // Redirecionamento para porta 22 (SSH) ou 1194 (OpenVPN)
        // Para este objetivo, vamos fixar o destino para 127.0.0.1:22 (SSH)
        // Se o usuário quiser 1194, precisaremos de uma forma de configurar isso (ex: argumento de linha de comando)
        uint16_t fixed_target_port = 22; // Porta de destino fixa (22 para SSH, ou 1194 para OpenVPN)
        std::string fixed_target_addr = "127.0.0.1"; // Endereço de destino fixo (localhost)

        resolver.async_resolve(fixed_target_addr, std::to_string(fixed_target_port),
            [this, self, fixed_target_addr, fixed_target_port](error_code ec, tcp::resolver::results_type endpoints) {
                if (ec) { send_reply(0x01); return; } // Falha geral

                // Conecta diretamente ao destino
                boost::asio::async_connect(remote_socket_, endpoints,
                    [this, self](error_code ec, tcp::endpoint) {
                        if (ec) { send_reply(0x01); return; }
                        
                        cancel_timeout();
                        send_reply(0x00, remote_socket_.local_endpoint().address(), remote_socket_.local_endpoint().port());
                        forward_data();
                    });
            });
    }

    void send_reply(uint8_t rep, boost::asio::ip::address addr = {}, uint16_t port = 0) {
        auto self(shared_from_this());
        std::vector<uint8_t> reply = {0x05, rep, 0x00};
        if (addr.is_v4()) {
            reply.push_back(0x01);
            auto bytes = addr.to_v4().to_bytes();
            reply.insert(reply.end(), bytes.begin(), bytes.end());
        } else if (addr.is_v6()) {
            reply.push_back(0x04);
            auto bytes = addr.to_v6().to_bytes();
            reply.insert(reply.end(), bytes.begin(), bytes.end());
        } else {
            // Default IPv4 0.0.0.0
            reply.push_back(0x01);
            reply.insert(reply.end(), {0x00, 0x00, 0x00, 0x00});
        }
        uint16_t net_port = htons(port);
        reply.insert(reply.end(), reinterpret_cast<uint8_t*>(&net_port), reinterpret_cast<uint8_t*>(&net_port) + 2);
        boost::asio::async_write(client_socket_, boost::asio::buffer(reply),
            [this, self, rep](error_code ec, std::size_t) {
                if (ec || rep != 0x00) { handle_error(ec); }
            });
    }

    void forward_data() {
        auto self(shared_from_this());
        set_timeout(300);  // 5min timeout para forwarding
        read_from_client(self);
        read_from_remote(self);
    }

    void read_from_client(std::shared_ptr<Session> self) {
        client_socket_.async_read_some(boost::asio::buffer(buffer_),
            [this, self](error_code ec, std::size_t length) {
                if (ec) { return handle_error(ec); }
                boost::asio::async_write(remote_socket_, boost::asio::buffer(buffer_, length),
                    [this, self](error_code ec, std::size_t) {
                        if (ec) { return handle_error(ec); }
                        read_from_client(self);
                    });
            });
    }

    void read_from_remote(std::shared_ptr<Session> self) {
        remote_socket_.async_read_some(boost::asio::buffer(buffer_),
            [this, self](error_code ec, std::size_t length) {
                if (ec) { return handle_error(ec); }
                boost::asio::async_write(client_socket_, boost::asio::buffer(buffer_, length),
                    [this, self](error_code ec, std::size_t) {
                        if (ec) { return handle_error(ec); }
                        read_from_remote(self);
                    });
            });
    }

    void handle_error(error_code ec) {
        cancel_timeout();
        if (ec && ec != boost::asio::error::eof && ec != boost::asio::error::operation_aborted) {
            std::cout << "Erro: " << ec.message() << std::endl;
        }
        client_socket_.shutdown(tcp::socket::shutdown_both, ec);
        remote_socket_.shutdown(tcp::socket::shutdown_both, ec);
        client_socket_.close();
        remote_socket_.close();
    }

    io_context& io_ctx_;
    tcp::socket client_socket_;
    tcp::socket remote_socket_;
    steady_timer timer_;
    std::array<uint8_t, 8192> buffer_;  // Buffer maior para velocidade
};

class Server {
public:
    Server(io_context& io_ctx, short port) : io_ctx_(io_ctx), acceptor_(io_ctx) {
        tcp::endpoint ep(tcp::v6(), port);  // Dual-stack IPv4/IPv6
        acceptor_.open(ep.protocol());
        acceptor_.set_option(tcp::acceptor::reuse_address(true));
        acceptor_.bind(ep);
        acceptor_.listen();
        accept();
    }

private:
    void accept() {
        auto session = std::make_shared<Session>(io_ctx_);
        acceptor_.async_accept(session->client_socket(),
            [this, session](error_code ec) {
                if (!ec) { session->start(); }
                else { std::cout << "Erro no accept: " << ec.message() << std::endl; }
                accept();
            });
    }

    io_context& io_ctx_;
    tcp::acceptor acceptor_;
};

} // namespace socks5

int main(int argc, char* argv[]) {
    try {
        io_context io_ctx;

        uint16_t fixed_target_port = 22; // Default para SSH
        if (argc > 1) {
            try {
                fixed_target_port = static_cast<uint16_t>(std::stoi(argv[1]));
            } catch (...) {
                std::cerr << "Aviso: Porta de destino inválida fornecida. Usando 22 como padrão." << std::endl;
            }
        }

        // Lógica para selecionar porta disponível
        short port = 0;
        while (true) {
            std::cout << "Digite a porta desejada (1-65535): ";
            std::string input;
            std::getline(std::cin, input);
            try {
                int temp_port = std::stoi(input);
                if (temp_port < 1 || temp_port > 65535) {
                    std::cerr << "Porta inválida! Tente novamente." << std::endl;
                    continue;
                }
                port = static_cast<short>(temp_port);
            } catch (...) {
                std::cerr << "Entrada inválida! Digite um número." << std::endl;
                continue;
            }

            // Pergunta se quer criar túnel SSH reverso
            std::cout << "Deseja criar um túnel SSH reverso? (s/n): ";
            std::string create_tunnel;
            std::getline(std::cin, create_tunnel);
            
            std::unique_ptr<socks5::ReverseSSHProxy> ssh_proxy;
            
            if (create_tunnel == "s" || create_tunnel == "S") {
                std::string ssh_server, username, password;
                int ssh_port, remote_port;
                
                std::cout << "IP do servidor SSH: ";
                std::getline(std::cin, ssh_server);
                
                std::cout << "Porta SSH (22): ";
                std::string ssh_port_str;
                std::getline(std::cin, ssh_port_str);
                ssh_port = ssh_port_str.empty() ? 22 : std::stoi(ssh_port_str);
                
                std::cout << "Usuário SSH: ";
                std::getline(std::cin, username);
                
                std::cout << "Senha SSH: ";
                std::getline(std::cin, password);
                
                std::cout << "Porta remota para o túnel: ";
                std::string remote_port_str;
                std::getline(std::cin, remote_port_str);
                remote_port = std::stoi(remote_port_str);
                
                ssh_proxy = std::make_unique<socks5::ReverseSSHProxy>(
                    ssh_server, ssh_port, username, password, port, remote_port);
                
                if (!ssh_proxy->start()) {
                    std::cerr << "Erro ao iniciar túnel SSH reverso!" << std::endl;
                    continue;
                }
                
                std::cout << "Túnel SSH reverso criado!" << std::endl;
                std::cout << "Agora você pode acessar este SOCKS5 através da porta " << remote_port 
                         << " no servidor " << ssh_server << std::endl;
            }

            // Tenta bind para verificar se a porta está livre
            try {
                socks5::Server server(io_ctx, port);
                std::cout << "Servidor SOCKS5 rodando na porta " << port << " (IPv4/IPv6)" << std::endl;
                if (ssh_proxy) {
                    std::cout << "Com túnel SSH reverso ativo!" << std::endl;
                }
                break;  // Sucesso, sai do loop
            } catch (const boost::system::system_error& e) {
                if (e.code() == boost::asio::error::address_in_use) {
                    std::cerr << "Porta " << port << " já em uso! Tente outra." << std::endl;
                } else {
                    std::cerr << "Erro ao bindar porta: " << e.what() << std::endl;
                }
            } catch (...) {
                std::cerr << "Erro inesperado ao tentar usar a porta!" << std::endl;
            }
        }

        io_ctx.run();
    } catch (std::exception& e) {
        std::cerr << "Exceção: " << e.what() << "\n";
    }
    return 0;
}

