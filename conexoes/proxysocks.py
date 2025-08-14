#!/usr/bin/env python3
# encoding: utf-8
# Merged Proxy: WebSocket Secure (WSS) and SOCKS on Same Port
# Based on wsproxy.py by @Crazy_vpn and proxy.py by Socks Scott
# Detects mode based on payload: If 'Upgrade: websocket' and 'Connection: Upgrade' are present, uses WSS mode; else SOCKS mode.
# Improvements: Added TCP keepalive for stability.
# New Features:
# - Support for Host spoofing via X-Online-Host header (extracted and logged; can be used for validation if needed).
# - Added support for GET and HEAD methods (besides CONNECT): Forwards the request to the target and returns response.
# - Forced Connection: Keep-Alive in all responses for persistent connections.
# - Added TLS/SSL support for WSS: Now the server uses HTTPS/WSS. Requires cert.pem and key.pem (self-signed OK).
#   Generate with: openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout key.pem
#   For valid certificates, use Let's Encrypt with Certbot:
#     1. Install Certbot: sudo apt install certbot (on Ubuntu/Debian) or follow https://certbot.eff.org/instructions
#     2. Run: sudo certbot certonly --standalone -d yourdomain.com (stop the proxy first, as it needs port 80/443 for validation)
#     3. Cert files: /etc/letsencrypt/live/yourdomain.com/fullchain.pem (cert) and privkey.pem (key)
#     4. Run the proxy with --cert /etc/letsencrypt/live/yourdomain.com/fullchain.pem --key /etc/letsencrypt/live/yourdomain.com/privkey.pem
#   Renew: sudo certbot renew (setup cron for auto-renewal)

import socket, threading, select, signal, sys, time, getopt
import ssl  # Added for SSL/TLS support

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
LISTENING_PORT = 443  # Default to 443 for SSL/TLS (WSS/HTTPS)
CERT_FILE = None
KEY_FILE = None

# WebSocket specific (now WSS)
WS_DEFAULT_HOST = "127.0.0.1:22"
WS_RESPONSE = 'HTTP/1.1 101 ' + str(COR) + str(MSG) + str(FTAG) + ' \r\nConnection: Keep-Alive\r\n\r\n'

# SOCKS specific
SOCKS_DEFAULT_HOST = '0.0.0.0:22'
SOCKS_RESPONSE = "HTTP/1.1 200 " + str(COR) + str(MSG) + str(FTAG) + "\r\nConnection: Keep-Alive\r\n\r\n"

class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.ssl_context = None
        if CERT_FILE and KEY_FILE:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)

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
                    if self.ssl_context:
                        try:
                            c = self.ssl_context.wrap_socket(c, server_side=True)
                        except ssl.SSLError as e:
                            print(f"SSL handshake failed: {e}")
                            c.close()
                            continue
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
        self.method = ''  # To store the HTTP method

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
            
            # Parse the HTTP method from the first line
            first_line = self.client_buffer.split(b'\n')[0].decode('utf-8', errors='ignore').strip()
            if first_line:
                parts = first_line.split()
                if len(parts) >= 1:
                    self.method = parts[0].upper()
            
            # Detect mode based on payload
            buffer_str = self.client_buffer.decode('utf-8', errors='ignore')
            if 'Upgrade: websocket' in buffer_str and 'Connection: Upgrade' in buffer_str:
                self.is_ws = True
                self.log = 'Connection: ' + str(self.client.getpeername())
            else:
                self.is_ws = False
                self.log = 'Conexao: ' + str(self.client.getpeername())
        
            hostPort = self.findHeader(buffer_str, 'X-Real-Host')
            
            if hostPort == '':
                hostPort = WS_DEFAULT_HOST if self.is_ws else SOCKS_DEFAULT_HOST

            # Extract X-Online-Host for spoofing support (log it for now; can add validation)
            online_host = self.findHeader(buffer_str, 'X-Online-Host')
            if online_host:
                self.log += ' - X-Online-Host: ' + online_host

            split = self.findHeader(buffer_str, 'X-Split')

            if split != '':
                self.client.recv(BUFLEN)
            
            if hostPort != '':
                passwd = self.findHeader(buffer_str, 'X-Pass')
                
                allowed = False
                if self.is_ws:
                    # WS logic
                    if len(PASS) != 0 and passwd == PASS:
                        allowed = True
                    elif len(PASS) != 0 and passwd != PASS:
                        self.client.send('HTTP/1.1 400 WrongPass!\r\n\r\n'.encode())
                    elif hostPort.startswith('127.0.0.1') or hostPort.startswith('localhost'):
                        allowed = True
                    else:
                        self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n'.encode())
                else:
                    # SOCKS logic
                    if len(PASS) != 0 and passwd == PASS:
                        allowed = True
                    elif len(PASS) != 0 and passwd != PASS:
                        self.client.send('HTTP/1.1 400 WrongPass!\r\n\r\n'.encode())
                    if hostPort.startswith(LISTENING_ADDR):  # Use shared ADDR for SOCKS check
                        allowed = True
                    else:
                        self.client.send('HTTP/1.1 403 Forbidden!\r\n\r\n'.encode())
                
                if allowed:
                    if self.method == 'CONNECT':
                        self.method_CONNECT(hostPort)
                    elif self.method in ('GET', 'HEAD'):
                        self.method_GET_HEAD(hostPort)
                    else:
                        self.client.send('HTTP/1.1 405 Method Not Allowed\r\n\r\n'.encode())
            else:
                print('- No X-Real-Host!')
                self.client.send('HTTP/1.1 400 NoXRealHost!\r\n\r\n'.encode())

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
            port = 443 if self.method == 'CONNECT' else (80 if self.is_ws else 22)

        (soc_family, soc_type, proto, _, address) = socket.getaddrinfo(host, port)[0]

        self.target = socket.socket(soc_family, soc_type, proto)
        self.targetClosed = False
        # Enable keepalive on target socket
        self.server.enable_keepalive(self.target)
        self.target.connect(address)

    def method_CONNECT(self, path):
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall((WS_RESPONSE if self.is_ws else SOCKS_RESPONSE).encode())
        self.client_buffer = ''
        self.server.printLog(self.log)
        self.doCONNECT()

    def method_GET_HEAD(self, path):
        self.log += f' - {self.method} ' + path
        self.connect_target(path)
        
        # Forward the original request to the target
        self.target.sendall(self.client_buffer)
        
        # Receive response from target
        response = b''
        while True:
            data = self.target.recv(BUFLEN)
            if not data:
                break
            response += data
        
        # Send response back to client, adding Keep-Alive if not present
        if b'Connection: Keep-Alive' not in response:
            response = response.replace(b'\r\n\r\n', b'\r\nConnection: Keep-Alive\r\n\r\n')
        
        self.client.sendall(response)
        
        self.server.printLog(self.log)
        self.close()  # Close after single request for GET/HEAD

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
    print('Use: merged_proxy.py -p <port> --cert <certfile> --key <keyfile>')
    print('       merged_proxy.py -b <ip> -p <port> --cert <certfile> --key <keyfile>')
    print('Defaults: IP 0.0.0.0, Port 443')
    print('For self-signed cert: openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout key.pem')
    print('For Let\'s Encrypt (free valid cert):')
    print('  1. Install Certbot: sudo apt install certbot (Ubuntu/Debian) or see https://certbot.eff.org/instructions')
    print('  2. Obtain cert: sudo certbot certonly --standalone -d yourdomain.com (stop proxy first)')
    print('  3. Use --cert /etc/letsencrypt/live/yourdomain.com/fullchain.pem --key /etc/letsencrypt/live/yourdomain.com/privkey.pem')
    print('  4. Auto-renew: sudo certbot renew --quiet (add to cron: crontab -e, add "0 12 * * * /usr/bin/certbot renew --quiet")')

def parse_args(argv):
    global LISTENING_ADDR, LISTENING_PORT, CERT_FILE, KEY_FILE
    try:
        opts, args = getopt.getopt(argv, "hb:p:", ["bind=", "port=", "cert=", "key="])
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
        elif opt == "--cert":
            CERT_FILE = arg
        elif opt == "--key":
            KEY_FILE = arg

    if CERT_FILE is None or KEY_FILE is None:
        print("Error: --cert and --key are required for WSS/SSL. See usage for how to obtain.")
        print_usage()
        sys.exit(1)

def main():
    parse_args(sys.argv[1:])
    
    print("\033[0;34m━"*8, "\033[1;32m MERGED PROXY: WSS & SOCKS on Same Port", "\033[0;34m━"*8, "\n")
    print("\033[1;33mIP:\033[1;32m " + LISTENING_ADDR)
    print("\033[1;33mPORTA:\033[1;32m " + str(LISTENING_PORT) + "\n")
    print("\033[1;33mCERT:\033[1;32m " + CERT_FILE)
    print("\033[1;33mKEY:\033[1;32m " + KEY_FILE + "\n")
    print("\033[0;34m━"*10, "\033[1;32m CRAZY & SCOTTSSH", "\033[0;34m━\033[1;37m"*11, "\n")
    print("\033[1;33mDetection:\033[1;32m WSS if 'Upgrade: websocket' and 'Connection: Upgrade' in payload, else SOCKS.\n")
    print("\033[1;33mStability Improvement:\033[1;32m TCP Keepalive enabled (Idle: 30s, Interval: 10s, Probes: 3).\n")
    print("\033[1;33mNew Features:\033[1;32m Host spoof via X-Online-Host (logged), GET/HEAD support, Forced Keep-Alive, SSL/TLS for WSS with certificates.\n")
    
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
