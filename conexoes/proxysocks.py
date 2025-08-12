#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiFlowPX – Proxy multiprotocolo
"""

import argparse
import base64
import hashlib
import select
import socket
import ssl
import sys
import threading
import time
import urllib.request
from queue import Queue

# --------------------------------------------------------------------------- #
#  Constantes
# --------------------------------------------------------------------------- #
class Constants:
    PROXY_SERVER_VERSION = "1.0"           # bump
    PROXY_SERVER_AUTHOR   = "mycroft"
    DEFAULT_PORT          = 80
    DEFAULT_WORKERS       = 4
    DEFAULT_BUFFER_SIZE   = 16_384
    DEFAULT_SSH_PORT      = 22
    DEFAULT_OPENVPN_PORT  = 1194
    DEFAULT_V2RAY_PORT    = 10086
    DEFAULT_ULIMIT        = 65_536
    DEFAULT_HTTP_RESPONSE = "HTTP/1.1 200 OK\r\n\r\n"
    IP_CHECK_URL          = "https://ipv4.icanhazip.com/"

# --------------------------------------------------------------------------- #
#  Utilidades
# --------------------------------------------------------------------------- #
class Utils:
    @staticmethod
    def trim(s: str) -> str:
        return s.strip()

    @staticmethod
    def is_valid_port(port: int) -> bool:
        return 0 < port <= 65_535

    @staticmethod
    def get_current_ip() -> str:
        try:
            with urllib.request.urlopen(Constants.IP_CHECK_URL, timeout=10) as resp:
                return Utils.trim(resp.read().decode())
        except Exception:
            return "127.0.0.1"

# --------------------------------------------------------------------------- #
#  Configuração
# --------------------------------------------------------------------------- #
class ProxyConfig:
    def __init__(self) -> None:
        self.token            = ""
        self.validate_only    = False
        self.port             = Constants.DEFAULT_PORT
        self.use_http         = False
        self.use_https        = False
        self.response_message = Constants.DEFAULT_HTTP_RESPONSE
        self.cert_path        = ""
        self.workers          = Constants.DEFAULT_WORKERS
        self.ulimit           = Constants.DEFAULT_ULIMIT
        self.ssh_only         = False
        self.buffer_size      = Constants.DEFAULT_BUFFER_SIZE
        self.ssh_port         = Constants.DEFAULT_SSH_PORT
        self.openvpn_port     = Constants.DEFAULT_OPENVPN_PORT
        self.v2ray_port       = Constants.DEFAULT_V2RAY_PORT
        self.remote_host      = "127.0.0.1"

# --------------------------------------------------------------------------- #
#  Parser de argumentos
# --------------------------------------------------------------------------- #
class ArgumentParser:
    def parse(self, argv) -> ProxyConfig:
        p = argparse.ArgumentParser(description="MultiFlowPX Proxy Server")
        p.add_argument("--token")
        p.add_argument("--validate", action="store_true")
        p.add_argument("--port", type=int, default=Constants.DEFAULT_PORT)
        p.add_argument("--http",  action="store_true")
        p.add_argument("--https", action="store_true")
        p.add_argument("--response", default=Constants.DEFAULT_HTTP_RESPONSE)
        p.add_argument("--cert")
        p.add_argument("--workers", type=int, default=Constants.DEFAULT_WORKERS)
        p.add_argument("--ulimit",  type=int, default=Constants.DEFAULT_ULIMIT)
        p.add_argument("--ssh-only", action="store_true")
        p.add_argument("--buffer-size", type=int, default=Constants.DEFAULT_BUFFER_SIZE)
        p.add_argument("--ssh-port", type=int, default=Constants.DEFAULT_SSH_PORT)
        p.add_argument("--openvpn-port", type=int, default=Constants.DEFAULT_OPENVPN_PORT)
        p.add_argument("--v2ray-port",  type=int, default=Constants.DEFAULT_V2RAY_PORT)
        p.add_argument("--remote-host", default="127.0.0.1")

        args = p.parse_args(argv)
        cfg  = ProxyConfig()

        # Mapeamento explícito – evita nomes divergentes
        cfg.token            = args.token or ""
        cfg.validate_only    = args.validate
        cfg.port             = args.port
        cfg.use_http         = args.http
        cfg.use_https        = args.https
        cfg.response_message = args.response
        cfg.cert_path        = args.cert or ""
        cfg.workers          = args.workers
        cfg.ulimit           = args.ulimit
        cfg.ssh_only         = args.ssh_only
        cfg.buffer_size      = args.buffer_size
        cfg.ssh_port         = args.ssh_port
        cfg.openvpn_port     = args.openvpn_port
        cfg.v2ray_port       = args.v2ray_port
        cfg.remote_host      = args.remote_host

        self._validate_config(cfg)
        return cfg

    def _validate_config(self, cfg: ProxyConfig) -> None:
        if not Utils.is_valid_port(cfg.port):
            raise ValueError(f"Porta inválida: {cfg.port}")

# --------------------------------------------------------------------------- #
#  Logging simples
# --------------------------------------------------------------------------- #
def log_info(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] INFO  {msg}", flush=True)

def log_error(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] ERROR {msg}", file=sys.stderr, flush=True)

# --------------------------------------------------------------------------- #
#  Conexões
# --------------------------------------------------------------------------- #
class Connection:
    def __init__(self, cli_sock: socket.socket, cfg: ProxyConfig):
        self.client_socket = cli_sock
        self.cfg           = cfg

    def forward_data(self, from_sock: socket.socket, to_sock: socket.socket) -> None:
        try:
            while True:
                r, _, _ = select.select([from_sock], [], [], 1.0)
                if not r:
                    continue
                data = from_sock.recv(self.cfg.buffer_size)
                if not data:
                    break
                sent = 0
                while sent < len(data):
                    n = to_sock.send(data[sent:])
                    sent += n
        except Exception as exc:
            log_error(f"forward_data: {exc}")

class ConnectionType(Connection):
    def __init__(self, cli_sock: socket.socket, cfg: ProxyConfig, proto: str):
        super().__init__(cli_sock, cfg)
        self.protocol      = proto
        self.server_socket = None  # type: socket.socket | None

    def _dst_port(self) -> int:
        return {
            "SSH":      self.cfg.ssh_port,
            "OpenVPN":  self.cfg.openvpn_port,
            "V2Ray":    self.cfg.v2ray_port,
        }.get(self.protocol, self.cfg.ssh_port)

    def establish(self) -> bool:
        for attempt in range(1, 4):
            try:
                self.server_socket = socket.create_connection(
                    (self.cfg.remote_host, self._dst_port()), timeout=5
                )
                log_info(f"Conectado a {self.protocol} em "
                         f"{self.cfg.remote_host}:{self._dst_port()} (tentativa {attempt})")
                return True
            except Exception as exc:
                log_error(f"Falha ao conectar ({attempt}/3): {exc}")
                time.sleep(2)
        return False

    def relay(self, first_data: bytes) -> None:
        if not self.server_socket:
            return
        # Envia o primeiro pacote capturado
        if first_data:
            self.server_socket.sendall(first_data)

        t1 = threading.Thread(target=self.forward_data,
                              args=(self.client_socket, self.server_socket),
                              daemon=True)
        t2 = threading.Thread(target=self.forward_data,
                              args=(self.server_socket, self.client_socket),
                              daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

# --------------------------------------------------------------------------- #
#  Fábrica / detecção de protocolo
# --------------------------------------------------------------------------- #
class ConnectionTypeFactory:
    @staticmethod
    def detect_protocol(initial: bytes) -> str:
        if initial.startswith(b"SSH-"):
            return "SSH"
        if len(initial) >= 2 and (initial[0] & 0xF0) == 0x20:
            return "OpenVPN"
        if len(initial) >= 16:
            weird = sum(1 for b in initial[:16] if b > 0x7F)
            if weird > 8 or (initial[0] == 1 and initial[1] == 0):
                return "V2Ray"
        return "SSH"

    @staticmethod
    def create(cli_sock: socket.socket, initial: bytes, cfg: ProxyConfig) -> ConnectionType:
        proto = ConnectionTypeFactory.detect_protocol(initial)
        return ConnectionType(cli_sock, cfg, proto)

# --------------------------------------------------------------------------- #
#  Parser de resposta HTTP / WebSocket
# --------------------------------------------------------------------------- #
class ResponseParser:
    def __init__(self, default_resp: str = Constants.DEFAULT_HTTP_RESPONSE):
        self.default_response = default_resp

    def parse(self, request: str) -> str:
        if self._is_ws_upgrade(request):
            return self._ws_handshake(request)
        return self.default_response

    @staticmethod
    def _is_ws_upgrade(req: str) -> bool:
        headers = req.lower()
        return "upgrade: websocket" in headers or "upgrade: ws" in headers

    def _ws_handshake(self, req: str) -> str:
        key = ""
        for line in req.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = Utils.trim(line.split(":", 1)[1])
                break
        if not key:
            key = "dGhlIHNhbXBsZSBub25jZQ=="  # fallback
        accept = self._ws_accept(key)
        return ( "HTTP/1.1 101 Switching Protocols\r\n"
                 "Upgrade: websocket\r\n"
                 "Connection: Upgrade\r\n"
                 f"Sec-WebSocket-Accept: {accept}\r\n\r\n" )

    @staticmethod
    def _ws_accept(key: str) -> str:
        magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        sha1  = hashlib.sha1((key + magic).encode()).digest()
        return base64.b64encode(sha1).decode()

# --------------------------------------------------------------------------- #
#  Servidor principal
# --------------------------------------------------------------------------- #
class ProxyServer:
    def __init__(self, cfg: ProxyConfig):
        self.cfg           = cfg
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.cfg.port))
        self.server_socket.listen(128)
        self.server_socket.setblocking(False)

        self.queues   = [Queue() for _ in range(self.cfg.workers)]
        self.parser   = ResponseParser(self.cfg.response_message)
        self.running  = True

        for i, q in enumerate(self.queues):
            threading.Thread(target=self._worker, args=(q,),
                             daemon=True, name=f"worker-{i}").start()

    # ---------------------------- loop aceitação --------------------------- #
    def serve_forever(self):
        log_info(f"Proxy {Constants.PROXY_SERVER_VERSION} pronto em :{self.cfg.port}")
        try:
            while self.running:
                r, _, _ = select.select([self.server_socket], [], [], 1.0)
                if not r:
                    continue
                cli_sock, _ = self.server_socket.accept()
                idx = hash(cli_sock) % self.cfg.workers
                self.queues[idx].put(cli_sock)
        except KeyboardInterrupt:
            log_info("Encerrando…")
        finally:
            self.running = False
            self.server_socket.close()

    # ---------------------------- worker thread --------------------------- #
    def _worker(self, q: Queue):
        while True:
            cli_sock: socket.socket = q.get()
            try:
                self._handle(cli_sock)
            except Exception as exc:
                log_error(f"_handle: {exc}")
            finally:
                try:
                    cli_sock.close()
                except Exception:
                    pass

    # ---------------------------- conexão única --------------------------- #
    def _handle(self, cli_sock: socket.socket):
        initial = cli_sock.recv(self.cfg.buffer_size, socket.MSG_PEEK)
        if not initial:
            return

        # Se pedido HTTP
        if initial.startswith(b"GET ") or initial.startswith(b"POST ") or initial.startswith(b"HEAD "):
            data = cli_sock.recv(self.cfg.buffer_size)  # consome
            resp = self.parser.parse(data.decode(errors="ignore"))
            cli_sock.sendall(resp.encode())
            # Se não for upgrade, encerra aqui
            if "101 Switching Protocols" not in resp:
                return

        conn = ConnectionTypeFactory.create(cli_sock, initial, self.cfg)
        if conn.establish():
            # remove o flag PEEK e lê de fato
            first_chunk = cli_sock.recv(self.cfg.buffer_size)
            conn.relay(first_chunk)

# --------------------------------------------------------------------------- #
#  Entry-point
# --------------------------------------------------------------------------- #
def main() -> None:
    cfg = ArgumentParser().parse(sys.argv[1:])
    server = ProxyServer(cfg)
    server.serve_forever()

if __name__ == "__main__":
    main()
