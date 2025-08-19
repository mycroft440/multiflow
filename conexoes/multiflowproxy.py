import asyncio
import argparse
import logging
import sys
import socket

# --- Configure maximum logging verbosity ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s'
)

console_handler.setFormatter(detailed_formatter)
logger.addHandler(console_handler)
# --- End logging configuration ---

# Global variables to hold server state
server_instance = None
current_port = None
current_status = None

async def peek_data(reader, length=8192, timeout_duration=1.0):
    """
    Attempt to peek data from the StreamReader without consuming it.
    Uses the underlying socket with MSG_PEEK flag.
    """
    try:
        # Access the underlying socket
        transport = reader._transport
        sock = transport.get_extra_info('socket')
        if sock is None:
            logger.warning("Could not get underlying socket for peeking (sock is None).")
            return ""

        # Use asyncio.wait_for to implement timeout
        loop = asyncio.get_running_loop()

        def _peek():
            try:
                flags = socket.MSG_PEEK
                # Nem todo SO tem MSG_DONTWAIT (ex.: Windows)
                if hasattr(socket, "MSG_DONTWAIT"):
                    flags |= socket.MSG_DONTWAIT
                data = sock.recv(length, flags)
                return data
            except BlockingIOError:
                return b""
            except Exception as e:
                logger.debug(f"Socket error during peek: {e}")
                raise e

        data_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _peek), timeout=timeout_duration
        )

        if isinstance(data_bytes, bytes):
            data_str = data_bytes.decode('utf-8', errors='ignore')
            logger.debug(f"Peeked {len(data_bytes)} bytes: {repr(data_str[:100])}...")
            return data_str
        else:
            logger.warning(f"Peek returned non-bytes type: {type(data_bytes)}")
            return ""

    except asyncio.TimeoutError:
        logger.warning(f"Timeout ({timeout_duration}s) while peeking data.")
        return ""
    except Exception as e:
        logger.error(f"Error during peek operation: {e}", exc_info=True)
        return ""  # Return empty string on error


async def handle_client(client_reader, client_writer):
    """
    Handles a client connection, determines the destination based on initial data,
    and forwards traffic.
    """
    client_addr = client_writer.get_extra_info('peername')
    logger.info(f"New connection from {client_addr}")

    try:
        # Send initial HTTP 101 Switching Protocols response
        status = current_status
        initial_response = f"HTTP/1.1 101 {status}\r\n\r\n"
        logger.debug(f"Sending 101 response: {repr(initial_response)}")
        client_writer.write(initial_response.encode())
        await client_writer.drain()
        logger.debug("101 response sent and drained.")

        # --- Read initial data (like Rust code does with 1024 buffer) ---
        logger.debug("Reading initial 1024 bytes from client (like Rust)...")
        initial_data = b""
        bytes_read_initial = 0
        try:
            initial_data = await asyncio.wait_for(client_reader.read(1024), timeout=1.0)
            bytes_read_initial = len(initial_data)
            if bytes_read_initial > 0:
                initial_data_for_check = initial_data.decode('utf-8', errors='ignore')
                logger.debug(f"Read {bytes_read_initial} initial bytes: {repr(initial_data_for_check[:100])}...")
            else:
                initial_data_for_check = ""
                logger.debug("No initial data read (EOF or zero bytes).")
        except asyncio.TimeoutError:
            logger.warning("Timeout reading initial 1024 bytes.")
            initial_data_for_check = ""
        except Exception as e:
            logger.error(f"Error reading initial data: {e}", exc_info=True)
            initial_data_for_check = ""  # Default to SSH on read error

        # Send the initial HTTP 200 OK response to the client (as per Rust code)
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        logger.debug(f"Sending 200 OK response to client: {repr(ok_response)}")
        client_writer.write(ok_response.encode())
        await client_writer.drain()
        logger.debug("200 OK response sent and drained.")

        # --- Use peek to inspect data for protocol detection (like Rust) ---
        logger.debug("Attempting to peek at client data for protocol detection...")
        peeked_data_str = await peek_data(client_reader, length=8192, timeout_duration=1.0)

        # Preferir usar o que já foi lido; se vazio, usar o peek
        data_to_inspect = initial_data_for_check if initial_data_for_check else peeked_data_str

        # Determine destination port based on available data (matching Rust logic closely)
        if "SSH" in data_to_inspect or not data_to_inspect.strip():
            dest_port = 22
            logger.info("Detected or defaulted to SSH traffic (port 22)")
        else:
            dest_port = 1194
            logger.info("Detected OpenVPN traffic (port 1194)")

        # --- Connect to the destination server ---
        # Conectar a 0.0.0.0 como destino não funciona; use localhost por padrão
        dest_addr = '127.0.0.1'
        logger.info(f"Connecting to destination: {dest_addr}:{dest_port}")

        try:
            logger.debug(f"Attempting to connect to destination server {dest_addr}:{dest_port}...")
            server_reader, server_writer = await asyncio.open_connection(dest_addr, dest_port)
            logger.info(f"Successfully connected to destination {dest_addr}:{dest_port}")
        except Exception as e:
            logger.error(f"Failed to connect to destination {dest_addr}:{dest_port} - {e}", exc_info=True)
            client_writer.close()
            await client_writer.wait_closed()
            return

        # --- Forward the initial data that was read to the server ---
        if bytes_read_initial > 0:
            logger.debug(f"Forwarding the initial {bytes_read_initial} bytes read to the server.")
            server_writer.write(initial_data)
            await server_writer.drain()
            logger.debug("Initial data successfully forwarded to server.")

        # --- Relay data bidirectionally ---
        logger.info("Starting bidirectional data relay...")
        await asyncio.gather(
            relay_data(client_reader, server_writer, f"client ({client_addr})->server ({dest_addr}:{dest_port})"),
            relay_data(server_reader, client_writer, f"server ({dest_addr}:{dest_port})->client ({client_addr})")
        )
        logger.info("Data relay stopped (EOF or error).")

    except asyncio.CancelledError:
        logger.info(f"Client handler for {client_addr} was cancelled.")
    except Exception as e:
        logger.error(f"Unexpected error handling client {client_addr}: {e}", exc_info=True)
    finally:
        logger.debug(f"Closing client connection {client_addr}...")
        client_writer.close()
        await client_writer.wait_closed()
        logger.info(f"Client connection {client_addr} closed.")


async def relay_data(reader, writer, direction_tag):
    """
    Relays data from a reader to a writer.
    Logs detailed information about data transfer.
    """
    logger.debug(f"Relay task started for {direction_tag}")
    total_bytes = 0
    try:
        buffer_size = 8192
        while True:
            data = await reader.read(buffer_size)
            bytes_read = len(data)
            total_bytes += bytes_read
            logger.debug(
                f"[{direction_tag}] Read {bytes_read} bytes (Total: {total_bytes}). "
                f"Data (repr, first 50 chars): {repr(data[:50])}{'...' if bytes_read > 50 else ''}"
            )

            # --- FIX de sintaxe: antes estava 'if not  # EOF' ---
            if not data:  # EOF
                logger.info(f"[{direction_tag}] EOF received. Stopping relay. Total bytes transferred: {total_bytes}")
                break

            writer.write(data)
            await writer.drain()
            logger.debug(f"[{direction_tag}] Wrote {bytes_read} bytes and drained.")

    except asyncio.CancelledError:
        logger.info(f"[{direction_tag}] Relay task was cancelled. Total bytes transferred: {total_bytes}")
    except Exception as e:
        logger.error(f"[{direction_tag}] Error relaying data: {e}", exc_info=True)
    finally:
        logger.debug(f"[{direction_tag}] Closing writer stream...")
        writer.close()
        await writer.wait_closed()
        logger.debug(f"[{direction_tag}] Writer stream closed.")


async def start_server(port, status):
    """
    Starts the TCP server.
    """
    global server_instance, current_port, current_status
    current_port = port
    current_status = status

    try:
        logger.info(f"Attempting to bind server to port {port}...")
        # Listen on all interfaces using IPv6 notation [::]
        server = await asyncio.start_server(handle_client, '::', port, family=socket.AF_UNSPEC)
        server_instance = server
        addr = server.sockets[0].getsockname()
        logger.info(f'Server successfully bound and listening on {addr[0]}:{addr[1]}')
        print(f"\n[INFO] Proxy server is now running on port {port} with status '{status}'")

        # Run serve_forever in background
        logger.debug("Starting server.serve_forever in a background task...")
        asyncio.create_task(server.serve_forever())
        logger.info("Server background task initiated.")

    except Exception as e:
        logger.critical(f"Server failed to start or encountered an error during setup: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to start server setup: {e}")
        server_instance = None


async def stop_server():
    """Stops the currently running server."""
    global server_instance
    if server_instance:
        try:
            logger.info("Stopping server...")
            server_instance.close()
            logger.debug("Server close signal sent, waiting for it to close...")
            await server_instance.wait_closed()
            logger.info("Server stopped successfully.")
            print("\n[INFO] Proxy server stopped.")
        except Exception as e:
            logger.error(f"Error stopping server: {e}", exc_info=True)
            print(f"\n[ERROR] Error stopping server: {e}")
        finally:
            server_instance = None
    else:
        logger.debug("Stop server called, but no server instance found or it was already None.")
        print("\n[INFO] No server instance is currently tracked or it was already stopped.")


def display_menu():
    """Displays the interactive menu."""
    print("\n--- Rusty Proxy Manager (DEBUG MODE) ---")
    if server_instance is not None:
        print(f"Status: Running on port {current_port}")
    else:
        print("Status: Stopped")
    print("1. Start Server")
    print("2. Stop Server")
    print("3. Show Status")
    print("4. Exit")
    print("----------------------------------------")


async def interactive_menu():
    """Main loop for the interactive menu."""
    global current_port, current_status

    parser = argparse.ArgumentParser(description='TCP Proxy for SSH/OpenVPN Tunneling (DEBUG MODE)')
    parser.add_argument('--port', type=int, default=80, help='Port to listen on (default: 80)')
    parser.add_argument('--status', type=str, default='@RustyManager', help='Status message for HTTP responses (default: @RustyManager)')
    parser.add_argument('--asyncio-debug', action='store_true', help='Enable asyncio debug mode')
    args = parser.parse_args()

    current_port = args.port
    current_status = args.status

    if args.asyncio_debug:
        logger.info("Enabling asyncio debug mode via argument.")
        loop = asyncio.get_running_loop()
        loop.set_debug(True)

    print(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")
    logger.info(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")

    while True:
        display_menu()
        try:
            choice = await asyncio.get_running_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                if server_instance is not None:
                    print("\n[INFO] Server start command received. A server instance might already exist or be running.")
                    logger.info("User attempted to start server, but server_instance is not None.")

                port_input = await asyncio.get_running_loop().run_in_executor(None, input, f"Enter port (default {current_port}): ")
                port_input = port_input.strip()
                if port_input:
                    try:
                        new_port = int(port_input)
                        if 1 <= new_port <= 65535:
                            current_port = new_port
                            logger.info(f"Port updated to {current_port} based on user input.")
                        else:
                            print("[WARNING] Invalid port number. Using current/default port.")
                            logger.warning(f"User entered invalid port number: {new_port}. Keeping {current_port}.")
                    except ValueError:
                        print("[WARNING] Invalid input. Using current/default port.")
                        logger.warning(f"User entered non-integer port: '{port_input}'. Keeping {current_port}.")

                status_input = await asyncio.get_running_loop().run_in_executor(None, input, f"Enter status message (default '{current_status}'): ")
                status_input = status_input.strip()
                if status_input:
                    current_status = status_input
                    logger.info(f"Status message updated to '{current_status}' based on user input.")

                await start_server(current_port, current_status)

            elif choice == '2':
                logger.info("User requested to stop server.")
                await stop_server()

            elif choice == '3':
                if server_instance is not None:
                    status_msg = f"\n[INFO] Server Status: Seeming running on port {current_port} with status '{current_status}'"
                else:
                    status_msg = "\n[INFO] Server Status: Stopped"
                print(status_msg)
                logger.info(status_msg.replace("\n[INFO] ", "", 1))

            elif choice == '4':
                logger.info("User requested to exit.")
                if server_instance is not None:
                    logger.info("Server instance exists, attempting to stop it before exit.")
                    await stop_server()
                print("\nExiting Rusty Proxy Manager. Goodbye!")
                logger.info("Exiting Rusty Proxy Manager.")
                break

            else:
                print("\n[ERROR] Invalid choice. Please enter a number between 1 and 4.")
                logger.warning(f"User entered invalid menu choice: '{choice}'")

        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal (Ctrl+C) in menu loop.")
            print("\n\nReceived interrupt signal (Ctrl+C).")
            if server_instance is not None:
                logger.info("Server instance exists, stopping it due to interrupt.")
                await stop_server()
            print("Exiting Rusty Proxy Manager. Goodbye!")
            logger.info("Exiting Rusty Proxy Manager due to interrupt.")
            break
        except Exception as e:
            error_msg = f"\n[ERROR] An unexpected error occurred in the menu loop: {e}"
            print(error_msg)
            logger.error(error_msg, exc_info=True)


# --- Entry Point ---
if __name__ == '__main__':
    try:
        asyncio.run(interactive_menu())
    except Exception as e:
        critical_msg = f"\n[CRITICAL ERROR] Application failed during startup or main loop: {e}"
        print(critical_msg)
        logger.critical(critical_msg, exc_info=True)
        sys.exit(1)
