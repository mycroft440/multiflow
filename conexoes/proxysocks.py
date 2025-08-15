#!/usr/bin/env python
# encoding: utf-8
import socket
import threading
import sys
import time
from concurrent.futures import ThreadPoolExecutor

IP = '0.0.0.0'
try:
    PORT = int(sys.argv[1])
except IndexError:
    PORT = 8080  # Porta alta para evitar permissões
PASS = ''
BUFLEN = 8196 * 8
TIMEOUT = 60
MSG = 'Connection established'
COR = '<font color="null">'
FTAG = '</font>'
DEFAULT_HOST = '0.0.0.0:22'
RESPONSE = ("HTTP/1.1 200 " + str(COR) + str(MSG) + str(FTAG) + "\r\nConnection: keep-alive\r\n\r\n").encode()

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()

    def run(self):
        self.soc = socket.socket(socket.AF_INET)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        try:
            self.soc.bind((self.host, self.port))
        except Exception as e:
            print(f"Erro ao bindar na porta {self.port}: {str(e)}")
            return
        self.soc.listen(0)
        self.running = True

        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                except socket.timeout:
                    continue

                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
        finally:
            self.running = False
            self.soc.close()

    def printLog(self, log):
        self.logLock.acquire()
        print(log)
        self.logLock.release()

    def addConn(self, conn):
        try:
            self.threadsLock.acquire()
            if self.running:
                self.threads.append(conn)
        finally:
            self.threadsLock.release()

    def removeConn(self, conn):
        try:
            self.threadsLock.acquire()
            self.threads.remove(conn)
        finally:
            self.threadsLock.release()

    def close(self):
        try:
            self.running = False
            self.threadsLock.acquire()

            threads = list(self.threads)
            for c in threads:
                c.close()
        finally:
            self.threadsLock.release()

class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = ''
        self.server = server
        self.log = 'Conexao: ' + str(addr)
        self.method = None

    def close(self):
        try:
            if not self.clientClosed:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
        except:
            pass
        finally:
            self.clientClosed = True

        try:
            if not self.targetClosed:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
        except:
            pass
        finally:
            self.targetClosed = True

    def run(self):
        try:
            self.client_buffer = self.client.recv(BUFLEN)

            hostPort = self.findHeader(self.client_buffer, b'X-Real-Host')  # Ajustado para bytes se necessário

            if hostPort == b'':
                hostPort = DEFAULT_HOST.encode()

            split = self.findHeader(self.client_buffer, b'X-Split')

            if split != b'':
                self.client.recv(BUFLEN)

            if hostPort != b'':
                passwd = self.findHeader(self.client_buffer, b'X-Pass')

                if len(PASS) != 0 and passwd.decode() == PASS:
                    self.method_CONNECT(hostPort.decode())
                elif len(PASS) != 0 and passwd.decode() != PASS:
                    self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                if hostPort.decode().startswith(IP):
                    self.method_CONNECT(hostPort.decode())
                else:
                    self.client.send(b'HTTP/1.1 403 Forbidden!\r\n\r\n')
            else:
                print('- No X-Real-Host!')
                self.client.send(b'HTTP/1.1 400 NoXRealHost!\r\n\r\n')

        except Exception as e:
            self.log += ' - error: ' + str(e)
            self.server.printLog(self.log)
        finally:
            self.close()
            self.server.removeConn(self)

    def findHeader(self, head, header):
        aux = head.find(header + b': ')

        if aux == -1:
            return b''

        aux = head.find(b':', aux)
        head = head[aux+2:]
        aux = head.find(b'\r\n')

        if aux == -1:
            return b''

        return head[:aux]

    def connect_target(self, host):
        i = host.find(':')
        if i != -1:
            port = int(host[i+1:])
            host = host[:i]
        else:
            if self.method == 'CONNECT':
                port = 443
            else:
                port = 22

        try:
            (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]
            self.target = socket.socket(soc_family, soc_type, proto)
            self.targetClosed = False
            self.target.connect(address)
        except Exception as e:
            print(f"Erro ao conectar ao target: {str(e)}")
            raise

    def method_CONNECT(self, path):
        self.method = 'CONNECT'
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall(RESPONSE)
        self.client_buffer = ''
        self.server.printLog(self.log)
        self.doCONNECT()

    def doCONNECT(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            def relay(src, dst):
                while True:
                    try:
                        data = src.recv(BUFLEN)
                        if not data:
                            break
                        dst.sendall(data)
                    except Exception as e:
                        print(f"Error in relay: {e}")
                        break

            future1 = executor.submit(relay, self.client, self.target)
            future2 = executor.submit(relay, self.target, self.client)

            try:
                future1.result(timeout=TIMEOUT)
                future2.result(timeout=TIMEOUT)
            except Exception as e:
                print(f"Timeout or error in relay: {e}")

def main(host=IP, port=PORT):
    print("\033[0;34m━"*8 + "\033[1;32m PROXY MULTIFLOW" + "\033[0;34m━"*8 + "\n")
    print("\033[1;33mIP:\033[1;32m " + IP)
    print("\033[1;33mPORTA:\033[1;32m " + str(PORT) + "\n")
    print("\033[0;34m━"*10 + "\033[1;32m MULTIFLOW" + "\033[0;34m━\033[1;37m"*11 + "\n")
    server = Server(host, port)
    server.start()
    print("Server rodando. Pressione Ctrl+C para parar.")
    while True:
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print('\nParando...')
            server.close()
            break

if __name__ == '__main__':
    main()
