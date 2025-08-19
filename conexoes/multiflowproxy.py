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
        if not sock:
            logger.warning("Could not get underlying socket for peeking.")
            return ""

        # Use asyncio.wait_for to implement timeout
        loop = asyncio.get_event_loop()

        def _peek():
            # Perform the peek operation on the socket
            # MSG_PEEK reads data without removing it from the queue
            return sock.recv(length, socket.MSG_PEEK)

        data_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _peek), timeout=timeout_duration
        )
        data_str = data_bytes.decode('utf-8', errors='ignore')
        logger.debug(f"Peeked {len(data_bytes)} bytes: {repr(data_str[:100])}...")
        return data_str
    except asyncio.TimeoutError:
        logger.warning(f"Timeout ({timeout_duration}s) while peeking data.")
        return ""
    except Exception as e:
        logger.error(f"Error during peek operation: {e}", exc_info=True)
        return ""


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

        # --- Use peek to inspect initial data without consuming it ---
        logger.debug("Attempting to peek at initial client data...")
        data_str = await peek_data(client_reader, length=8192, timeout_duration=1.0)

        # Determine destination port based on peeked data (like Rust)
        if "SSH" in data_str or not data_str.strip():
            dest_port = 22
            logger.info("Detected or defaulted to SSH traffic (port 22)")
        else:
            dest_port = 1194
            logger.info("Detected OpenVPN traffic (port 1194)")

        # --- Connect to the destination server ---
        # Match Rust proxy: connect to 0.0.0.0
        dest_addr = '0.0.0.0'
        logger.info(f"Connecting to destination: {dest_addr}:{dest_port}")

        try:
            logger.debug(f"Attempting to connect to destination server {dest_addr}:{dest_port}...")
            server_reader, server_writer = await asyncio.open_connection(dest_addr, dest_port)
            logger.info(f"Successfully connected to destination {dest_addr}:{dest_port}")
        except Exception as e:
            logger.error(f"Failed to connect to destination {dest_addr}:{dest_port} - {e}", exc_info=True)
            # Ensure client connection is closed on server connection failure
            client_writer.close()
            await client_writer.wait_closed()
            return # Exit the handler

        # Send the initial HTTP 200 OK response to the client (as per Rust code)
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        logger.debug(f"Sending 200 OK response to client: {repr(ok_response)}")
        client_writer.write(ok_response.encode())
        await client_writer.drain()
        logger.debug("200 OK response sent and drained.")

        # --- Relay data bidirectionally ---
        # Because we used peek, the initial data is still available in client_reader
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
    try:
        buffer_size = 8192
        total_bytes = 0
        while True:
            data = await reader.read(buffer_size)
            bytes_read = len(data)
            total_bytes += bytes_read
            logger.debug(f"[{direction_tag}] Read {bytes_read} bytes (Total: {total_bytes}). Data (repr, first 50 chars): {repr(data[:50])}{'...' if bytes_read > 50 else ''}")

            if not  # EOF
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
        # Match Rust proxy: Listen on all interfaces using IPv6 notation [::]
        # This typically binds to both IPv4 and IPv6
        server = await asyncio.start_server(handle_client, '::', port, family=socket.AF_UNSPEC)
        server_instance = server
        addr = server.sockets[0].getsockname()
        logger.info(f'Server successfully bound and listening on {addr[0]}:{addr[1]}')
        print(f"\n[INFO] Proxy server is now running on port {port} with status '{status}'")

        logger.debug("Entering server's serve_forever loop...")
        async with server:
            await server.serve_forever()

    except asyncio.CancelledError:
        logger.info("Server start task was cancelled.")
        print("\n[INFO] Proxy server stop initiated.")
    except Exception as e:
        logger.critical(f"Server failed to start or encountered an error: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to start server: {e}")
        server_instance = None


async def stop_server():
    """Stops the currently running server."""
    global server_instance
    if server_instance:
        if server_instance.is_serving():
            logger.info("Stopping server...")
            server_instance.close()
            logger.debug("Server close signal sent, waiting for it to close...")
            await server_instance.wait_closed()
            logger.info("Server stopped successfully.")
            print("\n[INFO] Proxy server stopped.")
        else:
            logger.debug("Server instance exists but is not serving.")
            print("\n[INFO] Server instance found but not currently serving.")
        server_instance = None
    else:
        logger.debug("Stop server called, but no server instance found.")
        print("\n[INFO] No server instance is currently tracked.")


def display_menu():
    """Displays the interactive menu."""
    print("\n--- Rusty Proxy Manager (DEBUG MODE) ---")
    if server_instance and server_instance.is_serving():
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
        asyncio.get_event_loop().set_debug(True)

    print(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")
    logger.info(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")

    while True:
        display_menu()
        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                if server_instance and server_instance.is_serving():
                    print("\n[INFO] Server is already running.")
                    logger.info("User attempted to start server, but it's already running.")
                else:
                    port_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter port (default {current_port}): ")
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

                    status_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter status message (default '{current_status}'): ")
                    status_input = status_input.strip()
                    if status_input:
                        current_status = status_input
                        logger.info(f"Status message updated to '{current_status}' based on user input.")

                    logger.info(f"Initiating server start on port {current_port} with status '{current_status}'")
                    asyncio.create_task(start_server(current_port, current_status))

            elif choice == '2':
                logger.info("User requested to stop server.")
                await stop_server()

            elif choice == '3':
                if server_instance and server_instance.is_serving():
                    status_msg = f"\n[INFO] Server Status: Running on port {current_port} with status '{current_status}'"
                else:
                    status_msg = "\n[INFO] Server Status: Stopped"
                print(status_msg)
                logger.info(status_msg.replace("\n[INFO] ", ""))

            elif choice == '4':
                logger.info("User requested to exit.")
                if server_instance and server_instance.is_serving():
                    logger.info("Server is running, initiating stop before exit.")
                    await stop_server()
                print("\nExiting Rusty Proxy Manager. Goodbye!")
                logger.info("Exiting Rusty Proxy Manager.")
                break

            else:
                print("\n[ERROR] Invalid choice. Please enter a number between 1 and 4.")
                logger.warning(f"User entered invalid menu choice: '{choice}'")

        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal (Ctrl+C).")
            print("\n\nReceived interrupt signal (Ctrl+C).")
            if server_instance and server_instance.is_serving():
                logger.info("Server is running, stopping it before exit due to interrupt.")
                await stop_server()
            print("Exiting Rusty Proxy Manager. Goodbye!")
            logger.info("Exiting Rusty Proxy Manager due to interrupt.")
            break
        except Exception as e:
            error_msg = f"\n[ERROR] An unexpected error occurred in the menu loop: {e}"
            print(error_msg)
            logger.error(error_msg, exc_info=True)


if __name__ == '__main__':
    try:
        asyncio.run(interactive_menu())
    except Exception as e:
        critical_msg = f"\n[CRITICAL ERROR] Application failed during startup or main loop: {e}"
        print(critical_msg)
        logger.critical(critical_msg, exc_info=True)
        sys.exit(1)
