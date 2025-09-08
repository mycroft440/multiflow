#!/usr/bin/env python3
"""
Multiflow proxy server with extended header support.

This script implements a simple hybrid HTTP/CONNECT/WebSocket proxy that can be
used in conjunction with tunnelling tools such as HTTP Injector.  It listens
on a given port, accepts incoming client connections and forwards them to a
target host derived from a variety of HTTP headers.  Unlike the original
``multiflowproxy.py`` implementation, this version is designed to be more
robust and flexible:

* Host detection is case‑insensitive and examines multiple header names in
  order of priority (``X‑Real‑Host``, ``X‑Host``, ``X‑Forward‑Host``,
  ``X‑Forwarded‑Host``, ``X‑Online‑Host``, ``Host``).  If none are present,
  the proxy falls back to the default host specified by ``DEFAULT_HOST``.
* Split payload detection is also case‑insensitive and understands
  ``X‑Split``, ``X‑Split‑Payload`` and ``Split`` headers, discarding the
  secondary chunk when present.
* Connection persistence can be controlled from the client using the
  ``Connection`` or ``Proxy‑Connection`` headers.  If either header is set
  to ``keep‑alive``, the proxy will avoid closing the connection on idle
  timeouts.  The optional ``Keep‑Alive`` header may specify a custom
  timeout (``timeout=n``), which overrides the default ``TIMEOUT``.

Because this script is intended to be run as a standalone proxy, it does
not depend on any external frameworks.  It uses the standard ``socket`` and
``select`` modules to multiplex data between the client and the upstream
server.  Each client connection is handled in its own thread, so a large
number of simultaneous connections may consume significant resources on
resource‑constrained systems.

Example usage::

    python3 multiflowproxy.py 3129

This will start the proxy on port 3129, using the default upstream host
``127.0.0.1:22`` when no host header is present.
"""

import base64
import socket
import select
import threading
import sys

# Buffer length for socket reads
BUFLEN = 8192

# Default inactivity timeout (number of select cycles) before closing.
# The timeout controls how long an idle connection is kept open.  HTTP Injector
# may take a few seconds to negotiate an SSH handshake, so you can increase
# this value via the `MF_TIMEOUT` environment variable if connections are
# being closed too early.  The value is expressed in select cycles of 3
# seconds each (a value of 60 equates to roughly 3 minutes of idle time).
import os
try:
    TIMEOUT = int(os.environ.get("MF_TIMEOUT", "60"))
except ValueError:
    TIMEOUT = 60

# Determine a sensible default upstream host.  When no host header or CONNECT
# line is provided, the proxy will connect to this address.  By default we
# attempt to determine the server's primary IP address and use port 22.
def _detect_local_ip() -> str:
    """Attempt to determine the primary outbound IP address.

    This function creates a UDP socket to a well‑known public address
    (8.8.8.8) in order to determine the local interface used for outbound
    traffic.  It does not send any data over the network.  If detection
    fails, '127.0.0.1' is returned.
    """
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # The IP and port here are arbitrary; no packets are actually sent
        test_sock.connect(("8.8.8.8", 80))
        local_ip = test_sock.getsockname()[0]
        test_sock.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

# Default upstream host:port if none is provided in the request.  Uses the
# detected local IP so that the proxy can forward to the machine's SSH server
# rather than the loopback address.  You can override this via the
# MF_DEFAULT_HOST environment variable (format ip:port).
_env_default = os.environ.get("MF_DEFAULT_HOST")
if _env_default:
    DEFAULT_HOST = _env_default
else:
    DEFAULT_HOST = f"{_detect_local_ip()}:22"

# Optional password for clients.  Leave empty to disable authentication.
PASS = b""

def parse_header_value(value: bytes) -> str:
    """Return a header value as a UTF‑8 string with whitespace stripped.

    :param value: Raw header bytes (e.g. b"example.com:80").
    :returns: Normalised string.
    """
    return value.decode("utf-8", errors="ignore").strip()


class ConnectionHandler(threading.Thread):
    """Handle a single client connection."""

    #: Ordered list of header names to inspect for host:port information.
    host_headers = [
        b"x-real-host",
        b"x-host",
        b"x-forward-host",
        b"x-forwarded-host",
        b"x-online-host",
        b"host",
        b"x-forwarded-for",
        b"x-originating-ip",
        b"x-remote-ip",
        b"x-remote-addr",
        b"x-client-ip",
        b"true-client-ip",
        b"x-real-ip",
        b"cf-connecting-ip",
        b"x-cluster-client-ip",
        b"forwarded",
        b"x-original-url",
        b"x-forwarded-url",
        b"x-forwarded-path",
        b"x-forwarded-scheme",
    ]

    #: Header names that indicate split payloads.  If present, the proxy will
    #: discard the next incoming chunk before proceeding with CONNECT.
    split_headers = [b"x-split", b"x-split-payload", b"split"]

    def __init__(self, client: socket.socket, addr: tuple):
        super().__init__(daemon=True)
        self.client = client
        self.addr = addr
        self.client_buffer = b""
        self.keepalive = False
        self.keepalive_timeout = TIMEOUT

    def run(self) -> None:
        try:
            self.client_buffer = self.client.recv(BUFLEN)
            if not self.client_buffer:
                self.client.close()
                return
            # Detect WebSocket handshake by presence of Upgrade: websocket
            if b"upgrade" in self.client_buffer.lower() and b"websocket" in self.client_buffer.lower():
                self.handle_websocket()
            else:
                self.process_request()
        except Exception:
            # On any unexpected error, ensure socket is closed to avoid leaks
            try:
                self.client.close()
            except Exception:
                pass

    def find_header(self, data: bytes, name: bytes) -> bytes:
        """Search for a header in a case‑insensitive manner and return its value.

        The search looks for ``name: value`` pairs separated by CRLF.  If the
        header is not found, returns an empty bytes string.

        :param data: The HTTP header block received from the client.
        :param name: The header name to search for (should already be lower‑case).
        :returns: The header value, excluding the trailing CRLF, or b"".
        """
        try:
            # Work on lower‑cased data for case‑insensitive matching
            lower = data.lower()
            idx = lower.find(name + b":")
            if idx == -1:
                return b""
            # Move past the header name and ':'
            start = idx + len(name) + 1
            # Skip any whitespace after the colon
            while start < len(data) and data[start:start + 1] in b" \t":
                start += 1
            end = lower.find(b"\r\n", start)
            if end == -1:
                end = len(data)
            return data[start:end].strip()
        except Exception:
            return b""

    def process_request(self) -> None:
        """Parse the request line and headers, then establish a tunnel."""
        data = self.client_buffer
        host_port_str: str = ""
        # Examine the request line for a CONNECT directive.  The CONNECT method
        # typically appears as 'CONNECT host:port HTTP/1.1'.  If present,
        # prefer this over header based detection because some clients omit
        # Host headers in CONNECT requests.
        try:
            line_end = data.find(b"\r\n")
            if line_end != -1:
                request_line = data[:line_end]
                parts = request_line.split()
                if parts and parts[0].lower() == b"connect" and len(parts) >= 2:
                    host_port_str = parse_header_value(parts[1])
        except Exception:
            # Fall back to header scanning if parsing fails
            host_port_str = ""
        # If no CONNECT directive provided a host, search for host headers
        if not host_port_str:
            host_port = b""
            for name in self.host_headers:
                host_port = self.find_header(data, name)
                if host_port:
                    break
            if not host_port:
                host_port_str = DEFAULT_HOST
            else:
                host_port_str = parse_header_value(host_port)
        # Ensure a port is specified; default to 80 for HTTP if absent
        if ":" not in host_port_str:
            host_port_str += ":80"
        # Check for split payload headers and discard the next chunk if needed
        for sh in self.split_headers:
            if self.find_header(data, sh):
                try:
                    self.client.recv(BUFLEN)
                except Exception:
                    pass
                break
        # Evaluate keep‑alive directives (case‑insensitive).  Consider both
        # Connection and Proxy‑Connection headers.  If either header
        # equals 'keep-alive', enable persistent connections.
        conn_hdr = parse_header_value(self.find_header(data, b"connection")).lower()
        proxy_conn_hdr = parse_header_value(self.find_header(data, b"proxy-connection")).lower()
        if conn_hdr == "keep-alive" or proxy_conn_hdr == "keep-alive":
            self.keepalive = True
        # Parse Keep-Alive header for timeout value
        ka_hdr = parse_header_value(self.find_header(data, b"keep-alive"))
        if ka_hdr:
            for part in ka_hdr.split(','):
                part = part.strip()
                if part.lower().startswith('timeout='):
                    try:
                        self.keepalive_timeout = int(part.split('=')[1])
                    except (ValueError, IndexError):
                        pass
        # Authenticate if a password is set
        if PASS:
            passwd = self.find_header(data, b"x-pass")
            if not passwd or passwd.strip() != PASS:
                try:
                    self.client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                finally:
                    self.client.close()
                return
        # Initiate CONNECT tunnel
        self.method_connect(host_port_str)

    def method_connect(self, host_port: str) -> None:
        """Establish a TCP tunnel to the target host and proxy data."""
        # Split host and port
        host, port_str = host_port.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            port = 80
        # Open connection to target server
        try:
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            target.connect((host, port))
        except Exception:
            try:
                self.client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            finally:
                self.client.close()
            return
        # Acknowledge tunnel established
        try:
            self.client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        except Exception:
            target.close()
            return
        # Forward traffic between client and target
        sockets = [self.client, target]
        inactivity = 0
        while True:
            try:
                rlist, _, xlist = select.select(sockets, [], sockets, 3)
            except Exception:
                break
            if xlist:
                break
            if rlist:
                for sock in rlist:
                    try:
                        data = sock.recv(BUFLEN)
                        if not data:
                            # Connection closed by peer
                            inactivity = self.keepalive_timeout + 1
                            break
                        # Reset inactivity counter upon receiving data
                        inactivity = 0
                        if sock is self.client:
                            target.sendall(data)
                        else:
                            self.client.sendall(data)
                    except Exception:
                        inactivity = self.keepalive_timeout + 1
                        break
            else:
                # No activity on sockets
                inactivity += 1
            # Determine idle limit based on keep‑alive settings
            idle_limit = self.keepalive_timeout if self.keepalive else TIMEOUT
            if inactivity > idle_limit:
                break
        # Cleanup sockets
        try:
            target.close()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass

    def handle_websocket(self) -> None:
        """Perform a basic WebSocket handshake and forward data."""
        # Very simple WebSocket handshake: echo a 101 response and then
        # transition to tunnel mode.  We deliberately avoid implementing
        # full WebSocket masking/unmasking because HTTP Injector usually
        # carries raw TCP streams over a WebSocket frame.  To support
        # WebSockets fully, a complete protocol implementation would be
        # required.
        try:
            # Extract the target host in the same way as process_request()
            data = self.client_buffer
            host_port = b""
            for name in self.host_headers:
                host_port = self.find_header(data, name)
                if host_port:
                    break
            if not host_port:
                host_port_str = DEFAULT_HOST
            else:
                host_port_str = parse_header_value(host_port)
            if ":" not in host_port_str:
                host_port_str += ":80"
            host, port_str = host_port_str.rsplit(":", 1)
            port = int(port_str)
            # Connect to target
            target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            target.connect((host, port))
            # Send WebSocket handshake response
            self.client.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                               b"Upgrade: websocket\r\n"
                               b"Connection: Upgrade\r\n\r\n")
        except Exception:
            try:
                self.client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            finally:
                self.client.close()
            return
        # Proxy data between client and target (no masking)
        sockets = [self.client, target]
        inactivity = 0
        while True:
            try:
                rlist, _, xlist = select.select(sockets, [], sockets, 3)
            except Exception:
                break
            if xlist:
                break
            if rlist:
                for sock in rlist:
                    try:
                        data = sock.recv(BUFLEN)
                        if not data:
                            inactivity = self.keepalive_timeout + 1
                            break
                        inactivity = 0
                        if sock is self.client:
                            target.sendall(data)
                        else:
                            self.client.sendall(data)
                    except Exception:
                        inactivity = self.keepalive_timeout + 1
                        break
            else:
                inactivity += 1
            idle_limit = self.keepalive_timeout if self.keepalive else TIMEOUT
            if inactivity > idle_limit:
                break
        try:
            target.close()
        except Exception:
            pass
        try:
            self.client.close()
        except Exception:
            pass


def start_server(port: int) -> None:
    """Start listening on the given port and spawn connection handlers."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(200)
    print(f"[+] proxy listening on 0.0.0.0:{port}")
    try:
        while True:
            client, addr = srv.accept()
            handler = ConnectionHandler(client, addr)
            handler.start()
    finally:
        srv.close()


def main() -> None:
    if len(sys.argv) < 2:
        port = 3129
    else:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            return
    try:
        start_server(port)
    except KeyboardInterrupt:
        print("\n[!] proxy terminated by user")


if __name__ == "__main__":
    main()
