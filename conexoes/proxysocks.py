#!/usr/bin/env python
# encoding: utf-8
import socket
import threading
import select
import sys
import time
import base64
from os import system

# --- Configurações Globais ---
IP = '0.0.0.0'
PASS = ''
BUFLEN = 8196 * 8
TIMEOUT = 60
MSG = 'Connection established'
COR = '<font color="null">'
FTAG = '</font>'
DEFAULT_HOST = '0.0.0.0:22'
# A resposta HTTP é construída como bytes
RESPONSE = b"HTTP/1.1 200 " + COR.encode() + base64.b64encode(MSG.encode()) + FTAG.encode() + b"\r\n\r\n"

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.soc = None

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        self.soc.bind((self.host, self.port))
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
            if self.soc:
                self.soc.close()

    def printLog(self, log):
        self.logLock.acquire()
        # Garante que o log seja uma string antes de imprimir
        log_str = log.decode("utf-8", errors="ignore") if isinstance(log, bytes) else str(log)
        print(log_str)
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
        self.client_buffer = b''
        self.server = server
        self.log = f'Conexao: {addr}'
        self.target = None

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
            hostPort = self.findHeader(self.client_buffer, 'X-Real-Host')

            if hostPort == '':
                hostPort = DEFAULT_HOST
            
            split = self.findHeader(self.client_buffer, 'X-Split')
            if split != '':
                self.client.recv(BUFLEN)

            if hostPort != '':
                passwd = self.findHeader(self.client_buffer, 'X-Pass')
                if len(PASS) != 0 and passwd == PASS:
                    self.method_CONNECT(hostPort)
                elif len(PASS) != 0 and passwd != PASS:
                    self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                elif hostPort.startswith(IP):
                    self.method_CONNECT(hostPort)
                else:
                    self.client.send(b'HTTP/1.1 403 Forbidden!\r\n\r\n')
            else:
                print('- No X-Real-Host!')
                self.client.send(b'HTTP/1.1 400 NoXRealHost!\r\n\r\n')
        except Exception as e:
            self.log += f' - error: {e}'
            self.server.printLog(self.log.encode())
        finally:
            self.close()
            self.server.removeConn(self)

    def findHeader(self, head, header):
        # Decodifica os bytes para string para fazer a busca
        head_str = head.decode("utf-8", errors="ignore")
        aux = head_str.find(header + ": ")
        if aux == -1:
            return ''
        aux = head_str.find(':', aux)
        head_str = head_str[aux + 2:]
        aux = head_str.find('\r\n')
        if aux == -1:
            return ''
        return head_str[:aux]

    def connect_target(self, host):
        i = host.find(':')
        if i != -1:
            port = int(host[i + 1:])
            host = host[:i]
        else:
            port = 22  # Porta padrão para SSH
        
        (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]
        self.target = socket.socket(soc_family, soc_type, proto)
        self.targetClosed = False
        self.target.connect(address)

    def method_CONNECT(self, path):
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall(RESPONSE)
        self.client_buffer = b''
        self.server.printLog(self.log.encode())
        self.doCONNECT()

    def doCONNECT(self):
        socs = [self.client, self.target]
        count = 0
        error = False
        while not error:
            count += 1
            (recv, _, err) = select.select(socs, [], socs, 3)
            if err:
                error = True
            if recv:
                for in_ in recv:
                    try:
                        data = in_.recv(BUFLEN)
                        if data:
                            if in_ is self.target:
                                # ##################################################
                                # ## ALTERAÇÃO CRÍTICA: Enviar dados brutos     ##
                                # ## em vez de usar a função send_chunked.      ##
                                # ##################################################
                                self.client.sendall(data)
                            else:
                                self.target.sendall(data)
                            count = 0
                        else:
                            error = True
                            break
                    except:
                        error = True
                        break
            if count > TIMEOUT / 3:
                error = True
        
def main():
    system("clear")
    # Tenta pegar a porta do argumento da linha de comando, senão usa 80
    try:
        port = int(sys.argv[1])
    except (IndexError, ValueError):
        port = 80

    print("\033[0;34m━"*8,"\033[1;32m PROXY SOCKS INICIADO","\033[0;34m━"*8,"\n")
    print(f"\033[1;33mIP:\033[1;32m {IP}")
    print(f"\033[1;33mPORTA:\033[1;32m {port}\n")
    print("\033[0;34m━"*35,"\n")
    
    server = Server(IP, port)
    server.start()
    
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print('\nParando o proxy...')
        server.close()
        server.join()
        print('Proxy parado com sucesso.')

if __name__ == '__main__':
    main()
