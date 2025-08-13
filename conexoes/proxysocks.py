#!/usr/bin/env python
# encoding: utf-8
# Merged Proxy: WebSocket and SOCKS on Same Port
# Based on wsproxy.py by @Crazy_vpn and proxy.py by Socks Scott
# Detects mode based on payload: If 'Upgrade: websocket' and 'Connection: Upgrade' are present, uses WebSocket mode; else SOCKS mode.
# Improvements: Added TCP keepalive for stability, especially on SOCKS mode (enabled on both client and target sockets).
# Keepalive settings: Idle 30s, Interval 10s, Probes 3 (configurable via constants).

import socket, threading, thread, select, signal, sys, time, getopt
from os import system

# Clear screen for SOCKS style
system("clear")

# Common constants
MSG = '@TMYCOMNECTVPN'
COR = '<font color="null">'
FTAG = '</font>'
PASS = ''
BUFLEN = 8196 * 8
TIMEOUT = 60

# Keepalive constants (for TCP keepalive)
KEEPALIVE_IDLE = 30  # Seconds before sending keepalive probe
KEEPALIVE_INTERVAL = 10  # Seconds between probes
KEEPALIVE_PROBES = 3  # Number of unacknowledged probes before closing

# Shared listening
LISTENING_ADDR = '0.0.0.0'
LISTENING_PORT = 80  # Default shared port

# WebSocket specific
WS_DEFAULT_HOST = "127.0.0.1:22"
WS_RESPONSE = 'HTTP/1.1 101 ' + str(COR) + str(MSG) + str(FTAG) + ' \r\n\r\n'

# SOCKS specific
SOCKS_DEFAULT_HOST = '0.0.0.0:22'
SOCKS_RESPONSE = "HTTP/1.1 200 " + str(COR) + str(MSG) + str(FTAG) + "\r\n\r\n"

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
        except:
            print(f"Failed to bind on {self.host}:{self.port}")
            sys.exit(1)
        self.soc.listen(0)
        self.running = True

        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                    # Enable keepalive on client socket immediately
                    self.enable_keepalive(c)
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

    def enable_keepalive(self, sock):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_PROBES)

class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = ''
        self.server = server
        self.log = ''  # Will set based on mode
        self.is_ws = False  # Will detect in run

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
            
            # Detect mode based on payload
            if 'Upgrade: websocket' in self.client_buffer and 'Connection: Upgrade' in self.client_buffer:
                self.is_ws = True
                self.log = 'Connection: ' + str(self.client.getpeername())
            else:
                self.is_ws = False
                self.log = 'Conexao: ' + str(self.client.getpeername())
        
            hostPort = self.findHeader(self.client_buffer, 'X-Real-Host')
            
            if hostPort == '':
                hostPort = WS_DEFAULT_HOST if self.is_ws else SOCKS_DEFAULT_HOST

            split = self.findHeader(self.client_buffer, 'X-Split')

            if split != '':
                self.client.recv(BUFLEN)
            
            if hostPort != '':
                passwd = self.findHeader(self.client_buffer, 'X-Pass')
                
                if self.is_ws:
                    # WS logic
                    if len(PASS) != 0 and passwd == PASS:
                        self.method_CONNECT(hostPort)
                    elif len(PASS) != 0 and passwd != PASS:
                        self.client.send('HTTP/1.1 400 WrongPass!\r\n\r\n')
                    elif hostPort.startswith('127.0.0.1') or hostPort.startswith('localhost'):
                        self.method_CONNECT(hostPort)
                    else:
                        self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n')
                else:
                    # SOCKS logic
                    if len(PASS) != 0 and passwd == PASS:
                        self.method_CONNECT(hostPort)
                    elif len(PASS) != 0 and passwd != PASS:
                        self.client.send('HTTP/1.1 400 WrongPass!\r\n\r\n')
                    if hostPort.startswith(LISTENING_ADDR):  # Use shared ADDR for SOCKS check
                        self.method_CONNECT(hostPort)
                    else:
                        self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n')
            else:
                print('- No X-Real-Host!')
                self.client.send('HTTP/1.1 400 NoXRealHost!\r\n\r\n')

        except Exception as e:
            self.log += ' - error: ' + str(e)
            self.server.printLog(self.log)
        finally:
            self.close()
            self.server.removeConn(self)

    def findHeader(self, head, header):
        aux = head.find(header + ': ')
        if aux == -1:
            return ''
        aux = head.find(':', aux)
        head = head[aux+2:]
        aux = head.find('\r\n')
        if aux == -1:
            return ''
        return head[:aux]

    def connect_target(self, host):
        i = host.find(':')
        if i != -1:
            port = int(host[i+1:])
            host = host[:i]
        else:
            port = 443  # Default for CONNECT
            # Adjust based on mode if not CONNECT, but since always CONNECT, perhaps not needed
            # But to preserve original: assuming self.method is 'CONNECT'
            self.method = 'CONNECT'  # Set it here explicitly
            if self.method != 'CONNECT':
                port = 80 if self.is_ws else 22

        (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]

        self.target = socket.socket(soc_family, soc_type, proto)
        self.targetClosed = False
        # Enable keepalive on target socket (especially important for SOCKS stability)
        self.server.enable_keepalive(self.target)
        self.target.connect(address)

    def method_CONNECT(self, path):
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall(WS_RESPONSE if self.is_ws else SOCKS_RESPONSE)
        self.client_buffer = ''
        self.server.printLog(self.log)
        self.doCONNECT()

    def doCONNECT(self):
        socs = [self.client, self.target]
        count = 0
        error = False
        while True:
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
                                self.client.send(data)
                            else:
                                while data:
                                    byte = self.target.send(data)
                                    data = data[byte:]
                            count = 0
                        else:
                            break
                    except:
                        error = True
                        break
            if count == TIMEOUT:
                error = True
            if error:
                break

def print_usage():
    print('Use: merged_proxy.py -p <port>')
    print('       merged_proxy.py -b <ip> -p <port>')
    print('Defaults: IP 0.0.0.0, Port 80')

def parse_args(argv):
    global LISTENING_ADDR, LISTENING_PORT
    try:
        opts, args = getopt.getopt(argv, "hb:p:", ["bind=", "port="])
    except getopt.GetoptError:
        print_usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print_usage()
            sys.exit()
        elif opt in ("-b", "--bind"):
            LISTENING_ADDR = arg
        elif opt in ("-p", "--port"):
            LISTENING_PORT = int(arg)

def main():
    parse_args(sys.argv[1:])
    
    print("\033[0;34m━"*8, "\033[1;32m MERGED PROXY: WEBSOCKET & SOCKS on Same Port", "\033[0;34m━"*8, "\n")
    print("\033[1;33mIP:\033[1;32m " + LISTENING_ADDR)
    print("\033[1;33mPORTA:\033[1;32m " + str(LISTENING_PORT) + "\n")
    print("\033[0;34m━"*10, "\033[1;32m CRAZY & SCOTTSSH", "\033[0;34m━\033[1;37m"*11, "\n")
    print("\033[1;33mDetection:\033[1;32m WebSocket if 'Upgrade: websocket' and 'Connection: Upgrade' in payload, else SOCKS.\n")
    print("\033[1;33mStability Improvement:\033[1;32m TCP Keepalive enabled (Idle: 30s, Interval: 10s, Probes: 3).\n")
    
    # Start single server
    server = Server(LISTENING_ADDR, LISTENING_PORT)
    server.start()
    
    while True:
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print('Parando...')
            server.close()
            break

if __name__ == '__main__':
    main()
