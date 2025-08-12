import argparse
import socket
import threading
import select
import ssl
import hashlib
import base64
import urllib.request
import sys
import time
from queue import Queue

# Constants
class Constants:
    PROXY_SERVER_VERSION = "1.0"
    PROXY_SERVER_AUTHOR = "mycroft"
    DEFAULT_PORT = 8080
    DEFAULT_WORKERS = 4
    DEFAULT_BUFFER_SIZE = 16384  # Aumentado com melhorias
    DEFAULT_SSH_PORT = 22
    DEFAULT_OPENVPN_PORT = 1194
    DEFAULT_V2RAY_PORT = 10086
    DEFAULT_ULIMIT = 65536
    DEFAULT_HTTP_RESPONSE = "HTTP/1.1 200 OK\r\n\r\n"
    WEBSOCKET_UPGRADE_RESPONSE = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
    IP_CHECK_URL = "https://ipv4.icanhazip.com/"

# Utils
class Utils:
    @staticmethod
    def trim(s):
        return s.strip()

    @staticmethod
    def split(s, delimiter):
        return s.split(delimiter)

    @staticmethod
    def is_valid_port(port):
        return 0 < port <= 65535

    @staticmethod
    def get_current_ip():
        try:
            with urllib.request.urlopen(Constants.IP_CHECK_URL, timeout=10) as response:
                return Utils.trim(response.read().decode('utf-8'))
        except:
            return "127.0.0.1"

# ProxyConfig
class ProxyConfig:
    def __init__(self):
        self.token = ""
        self.validate_only = False
        self.port = Constants.DEFAULT_PORT
        self.use_http = False
        self.use_https = False
        self.response_message = Constants.DEFAULT_HTTP_RESPONSE
        self.cert_path = ""
        self.workers = Constants.DEFAULT_WORKERS
        self.ulimit = Constants.DEFAULT_ULIMIT
        self.ssh_only = False
        self.buffer_size = Constants.DEFAULT_BUFFER_SIZE
        self.ssh_port = Constants.DEFAULT_SSH_PORT
        self.openvpn_port = Constants.DEFAULT_OPENVPN_PORT
        self.v2ray_port = Constants.DEFAULT_V2RAY_PORT
        self.show_help = False
        self.remote_host = "127.0.0.1"  # Flexível com melhorias

# ArgumentParser
class ArgumentParser:
    def parse(self, args):
        parser = argparse.ArgumentParser(description="MultiFlowPX Proxy Server")
        parser.add_argument("--token", help="Token for validation")
        parser.add_argument("--validate", action="store_true", help="Validate only")
        parser.add_argument("--port", type=int, default=Constants.DEFAULT_PORT, help="Port")
        parser.add_argument("--http", action="store_true", help="Use HTTP")
        parser.add_argument("--https", action="store_true", help="Use HTTPS")
        parser.add_argument("--response", default=Constants.DEFAULT_HTTP_RESPONSE, help="Response message")
        parser.add_argument("--cert", help="Certificate path for HTTPS")
        parser.add_argument("--workers", type=int, default=Constants.DEFAULT_WORKERS, help="Number of workers")
        parser.add_argument("--ulimit", type=int, default=Constants.DEFAULT_ULIMIT, help="Ulimit")
        parser.add_argument("--ssh-only", action="store_true", help="SSH only mode")
        parser.add_argument("--buffer-size", type=int, default=Constants.DEFAULT_BUFFER_SIZE, help="Buffer size")
        parser.add_argument("--ssh-port", type=int, default=Constants.DEFAULT_SSH_PORT, help="SSH port")
        parser.add_argument("--openvpn-port", type=int, default=Constants.DEFAULT_OPENVPN_PORT, help="OpenVPN port")
        parser.add_argument("--v2ray-port", type=int, default=Constants.DEFAULT_V2RAY_PORT, help="V2Ray port")
        parser.add_argument("--remote-host", default="127.0.0.1", help="Remote host for connections")
        parser.add_argument("--help", action="store_true", help="Show help")
        
        config = ProxyConfig()
        parsed = parser.parse_args(args)
        for key, value in vars(parsed).items():
            if value is not None:
                setattr(config, key.replace('-', '_'), value)
        self.validate_config(config)
        return config

    def validate_config(self, config):
        if not Utils.is_valid_port(config.port):
            raise ValueError(f"Invalid port: {config.port}")
        if config.use_https and not config.cert_path:
            print("Warning: Cert path required for HTTPS, using temp if possible")

# Logging simples com timestamps
def log_info(msg):
    print(f"[{time.time()}] INFO: {msg}")

def log_error(msg):
    print(f"[{time.time()}] ERROR: {msg}", file=sys.stderr)

# Connection base
class Connection:
    def __init__(self, client_socket, config):
        self.client_socket = client_socket
        self.config = config
        self.active = False

    def read(self, size):
        return self.client_socket.recv(size)

    def write(self, data):
        return self.client_socket.send(data)

    def close(self):
        if self.client_socket:
            self.client_socket.close()

    def forward_data(self, from_sock, to_sock):
        while True:
            r, _, _ = select.select([from_sock], [], [], 1.0)  # Timeout 1s
            if r:
                data = from_sock.recv(self.config.buffer_size)
                if not data:
                    break
                sent = 0
                while sent < len(data):  # Retry partial sends
                    try:
                        sent += to_sock.send(data[sent:])
                    except:
                        log_error("Write error in forward")
                        return

# ConnectionType
class ConnectionType(Connection):
    def __init__(self, client_socket, config, protocol):
        super().__init__(client_socket, config)
        self.protocol = protocol
        self.server_socket = None

    def establish(self):
        for tries in range(3):  # Retries com delay
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.connect((self.config.remote_host, self.get_port()))
                log_info(f"Connected to {self.protocol} on {self.config.remote_host}:{self.get_port()} (try {tries+1})")
                self.active = True
                return True
            except Exception as e:
                log_error(f"Failed to connect to {self.protocol} (try {tries+1}): {e}")
                time.sleep(2)
        return False

    def handle_data(self):
        if not self.active:
            return
        t1 = threading.Thread(target=self.forward_data, args=(self.client_socket, self.server_socket))
        t2 = threading.Thread(target=self.forward_data, args=(self.server_socket, self.client_socket))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.active = False

    def get_port(self):
        if self.protocol == "SSH":
            return self.config.ssh_port
        elif self.protocol == "OpenVPN":
            return self.config.openvpn_port
        elif self.protocol == "V2Ray":
            return self.config.v2ray_port
        return self.config.ssh_port  # Default

# Factory
class ConnectionTypeFactory:
    @staticmethod
    def create_connection(client_socket, initial_data, config):
        protocol = ConnectionTypeFactory.detect_protocol(initial_data)
        return ConnectionType(client_socket, config, protocol)

    @staticmethod
    def detect_protocol(initial_data):
        log_info(f"Detecting protocol from initial data: {initial_data[:32]}")
        if initial_data.startswith(b'SSH-'):
            return "SSH"
        if len(initial_data) >= 2 and (initial_data[0] & 0xF0) == 0x20:
            return "OpenVPN"
        if len(initial_data) >= 16:
            high_count = sum(1 for b in initial_data[:16] if b > 0x7F)
            if high_count > 8 or (initial_data[0] == 0x01 and initial_data[1] == 0x00):
                return "V2Ray"
        return "SSH"  # Default

# ResponseParser
class ResponseParser:
    def __init__(self, default_response=Constants.DEFAULT_HTTP_RESPONSE):
        self.default_response = default_response

    def parse_response(self, request):
        if self.is_websocket_upgrade(request):
            return self.generate_websocket_handshake(request)
        return self.default_response

    def is_websocket_upgrade(self, request):
        headers = self.extract_headers(request)
        return "upgrade: websocket" in headers.lower() or "upgrade: ws" in headers.lower()

    def generate_websocket_handshake(self, request):
        key = self.extract_websocket_key(request)
        if not key:
            key = "dGhlIHNhbXBsZSBub25jZQ=="  # Dummy para leniência
            log_info("Using dummy key for minimal WS payload")
        accept = self.generate_websocket_accept(key)
        return f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"

    def extract_websocket_key(self, request):
        lines = request.split("\r\n")
        for line in lines:
            if line.lower().startswith("sec-websocket-key:"):
                return Utils.trim(line.split(":", 1)[1])
        return ""

    def generate_websocket_accept(self, key):
        magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        combined = key + magic
        sha1 = hashlib.sha1(combined.encode()).digest()
        return base64.b64encode(sha1).decode()

    def extract_headers(self, request):
        return request.split("\r\n\r\n")[0]

# ProxyServer
class ProxyServer:
    def __init__(self, config):
        self.config = config
        self.server_socket = None
        self.running = False
        self.worker_queues = [Queue() for _ in range(config.workers)]
        self.response_parser = ResponseParser(config.response_message)

    def initialize(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(("0.0.0.0", self.config.port))
        self.server_socket.listen(10)
        self.server_socket.setblocking(False)
        log_info(f"Server running on port {self.config.port}")
        for i in range(self.config.workers):
            threading.Thread(target=self.worker_loop, args=(self.worker_queues[i],)).start()

    def run(self):
        self.initialize()
        self.running = True
        while self.running:
            r, _, _ = select.select([self.server_socket], [], [], 1.0)
            if r:
                client_socket, _ = self.server_socket.accept()
                queue = self.worker_queues[hash(client_socket) % self.config.workers]
                queue.put(client_socket)

    def worker_loop(self, queue):
        while True:
            client_socket = queue.get()
            self.handle_connection(client_socket)

    def handle_connection(self, client_socket):
        try:
            initial_data = client_socket.recv(self.config.buffer_size)
            if not initial_data:
                client_socket.close()
                return

            if self.config.use_https:
                context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                if not self.config.cert_path:
                    log_info("Generating temp cert for HTTPS...")
                    # Simule geração (em real, use subprocess para openssl)
                    self.config.cert_path = "/path/to/temp.crt"  # Ajuste manual
                context.load_cert_chain(certfile=self.config.cert_path)
                client_socket = context.wrap_socket(client_socket, server_side=True)

            if self.is_http_request(initial_data):
                response = self.response_parser.parse_response(initial_data.decode(errors='ignore'))
                client_socket.send(response.encode())
                if "101 Switching Protocols" in response:
                    pass  # Continue para protocolo
                else:
                    client_socket.close()
                    return

            conn = ConnectionTypeFactory.create_connection(client_socket, initial_data, self.config)
            if conn.establish():
                conn.handle_data()
            conn.close()
        except Exception as e:
            log_error(f"Error handling connection: {e}")
        finally:
            client_socket.close()

    def is_http_request(self, data):
        return data.startswith(b"GET ") or data.startswith(b"POST ") or data.startswith(b"HEAD ")

# Main
if __name__ == "__main__":
    parser = ArgumentParser()
    config = parser.parse(sys.argv[1:])
    server = ProxyServer(config)
    server.run()
