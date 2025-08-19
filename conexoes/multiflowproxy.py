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
        # Check if sock is a valid socket object (not None)
        if sock is None:
            logger.warning("Could not get underlying socket for peeking (sock is None).")
            return ""

        # Use asyncio.wait_for to implement timeout
        loop = asyncio.get_event_loop()

        def _peek():
            # Perform the peek operation on the socket
            # MSG_PEEK reads data without removing it from the queue
            try:
                # Use the correct flag for peeking
                data = sock.recv(length, socket.MSG_PEEK | socket.MSG_DONTWAIT)
                return data
            except BlockingIOError:
                # No data available immediately
                return b""
            except Exception as e:
                # Re-raise other socket errors
                logger.debug(f"Socket error during peek: {e}")
                raise e

        # Apply timeout to the executor call
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
        return "" # Return empty string on error


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
        initial_buffer = bytearray(1024) # Match Rust's buffer size
        bytes_read_initial = 0
        try:
            # Read into the buffer
            bytes_read_initial = await asyncio.wait_for(client_reader.readinto(initial_buffer), timeout=1.0)
            if bytes_read_initial > 0:
                initial_data_for_check = initial_buffer[:bytes_read_initial].decode('utf-8', errors='ignore')
                logger.debug(f"Read {bytes_read_initial} initial bytes: {repr(initial_data_for_check[:100])}...")
            else:
                initial_data_for_check = ""
                logger.debug("No initial data read (EOF or zero bytes).")
        except asyncio.TimeoutError:
            logger.warning("Timeout reading initial 1024 bytes.")
            initial_data_for_check = ""
        except Exception as e:
             logger.error(f"Error reading initial data: {e}", exc_info=True)
             initial_data_for_check = "" # Default to SSH on read error

        # Send the initial HTTP 200 OK response to the client (as per Rust code)
        # This happens after the initial read in Rust
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        logger.debug(f"Sending 200 OK response to client: {repr(ok_response)}")
        client_writer.write(ok_response.encode())
        await client_writer.drain()
        logger.debug("200 OK response sent and drained.")

        # --- Use peek to inspect data for protocol detection (like Rust) ---
        logger.debug("Attempting to peek at client data for protocol detection...")
        peeked_data_str = await peek_data(client_reader, length=8192, timeout_duration=1.0)

        # Determine destination port based on peeked data (matching Rust logic closely)
        # Rust checks the peeked data: if data.contains("SSH") || data.is_empty()
        if "SSH" in peeked_data_str or not peeked_data_str.strip():
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

        # --- Important: Write the initial data that was read to the server ---
        # This is crucial. The Rust code reads the initial 1024 bytes,
        # then connects and must forward that data.
        if bytes_read_initial > 0:
             logger.debug(f"Forwarding the initial {bytes_read_initial} bytes read to the server.")
             server_writer.write(initial_buffer[:bytes_read_initial])
             await server_writer.drain()
             logger.debug("Initial data successfully forwarded to server.")

        # --- Relay data bidirectionally ---
        # The relay now continues with the streams.
        # The peeked data remains in the client stream and will be read normally.
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
        # This typically binds to both IPv4 and IPv6. AF_UNSPEC lets the system decide.
        server = await asyncio.start_server(handle_client, '::', port, family=socket.AF_UNSPEC)
        server_instance = server
        addr = server.sockets[0].getsockname()
        logger.info(f'Server successfully bound and listening on {addr[0]}:{addr[1]}')
        print(f"\n[INFO] Proxy server is now running on port {port} with status '{status}'")

        # --- Key Change: Run serve_forever in a background task ---
        # This allows the start_server function to return and the menu to continue
        logger.debug("Starting server.serve_forever in a background task...")
        # Create a task for serve_forever and store it if needed, or just let it run
        # Storing the server instance is usually enough to keep it alive
        asyncio.create_task(server.serve_forever())
        logger.info("Server background task initiated.")

    except Exception as e: # Catch general exceptions during server creation/setup
        logger.critical(f"Server failed to start or encountered an error during setup: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to start server setup: {e}")
        server_instance = None # Indicate failure


async def stop_server():
    """Stops the currently running server."""
    global server_instance
    if server_instance:
        try:
            logger.info("Stopping server...")
            server_instance.close() # Signal the server to stop accepting new connections
            logger.debug("Server close signal sent, waiting for it to close...")
            await server_instance.wait_closed() # Wait for the server to finish closing
            logger.info("Server stopped successfully.")
            print("\n[INFO] Proxy server stopped.")
        except Exception as e:
            logger.error(f"Error stopping server: {e}", exc_info=True)
            print(f"\n[ERROR] Error stopping server: {e}")
        finally:
            server_instance = None # Clear the reference regardless of success/failure
    else:
        logger.debug("Stop server called, but no server instance found or it was already None.")
        print("\n[INFO] No server instance is currently tracked or it was already stopped.")


def display_menu():
    """Displays the interactive menu."""
    print("\n--- Rusty Proxy Manager (DEBUG MODE) ---")
    # Simple check based on server_instance existence
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

    # Parse command line arguments for initial defaults
    parser = argparse.ArgumentParser(description='TCP Proxy for SSH/OpenVPN Tunneling (DEBUG MODE)')
    parser.add_argument('--port', type=int, default=80, help='Port to listen on (default: 80)')
    parser.add_argument('--status', type=str, default='@RustyManager', help='Status message for HTTP responses (default: @RustyManager)')
    parser.add_argument('--asyncio-debug', action='store_true', help='Enable asyncio debug mode')
    args = parser.parse_args()

    # Set initial global values from arguments or defaults
    current_port = args.port
    current_status = args.status

    # Enable asyncio debug mode if requested via argument
    if args.asyncio_debug:
        logger.info("Enabling asyncio debug mode via argument.")
        loop = asyncio.get_running_loop()
        loop.set_debug(True) # Enable debug mode on the currently running loop

    print(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")
    logger.info(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")

    # Main menu loop
    while True:
        display_menu()
        try:
            # Use run_in_executor for blocking input to keep the event loop responsive
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                # Check if server is seemingly already running/initialized
                if server_instance is not None:
                    print("\n[INFO] Server start command received. A server instance might already exist or be running.")
                    logger.info("User attempted to start server, but server_instance is not None.")
                    # You might want to prevent starting again or warn more explicitly
                    # For now, we proceed, which might lead to errors if one is truly active

                # Get port from user (optional)
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

                # Get status message from user (optional)
                status_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter status message (default '{current_status}'): ")
                status_input = status_input.strip()
                if status_input:
                    current_status = status_input
                    logger.info(f"Status message updated to '{current_status}' based on user input.")

                # Initiate server start with current port/status
                logger.info(f"Initiating server start on port {current_port} with status '{current_status}'")
                # This will now correctly start the server in the background
                await start_server(current_port, current_status)

            elif choice == '2':
                logger.info("User requested to stop server.")
                await stop_server()

            elif choice == '3':
                # Show status based on server_instance existence
                if server_instance is not None:
                    status_msg = f"\n[INFO] Server Status: Seeming running on port {current_port} with status '{current_status}'"
                else:
                    status_msg = "\n[INFO] Server Status: Stopped"
                print(status_msg)
                logger.info(status_msg.replace("\n[INFO] ", "", 1)) # Log without leading newline/prefix

            elif choice == '4':
                logger.info("User requested to exit.")
                # Attempt to stop server gracefully if it seems to be initialized
                if server_instance is not None:
                    logger.info("Server instance exists, attempting to stop it before exit.")
                    await stop_server()
                print("\nExiting Rusty Proxy Manager. Goodbye!")
                logger.info("Exiting Rusty Proxy Manager.")
                break # Exit the main menu loop

            else:
                print("\n[ERROR] Invalid choice. Please enter a number between 1 and 4.")
                logger.warning(f"User entered invalid menu choice: '{choice}'")

        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal (Ctrl+C) in menu loop.")
            print("\n\nReceived interrupt signal (Ctrl+C).")
            # Attempt to stop server gracefully on Ctrl+C
            if server_instance is not None:
                logger.info("Server instance exists, stopping it due to interrupt.")
                await stop_server()
            print("Exiting Rusty Proxy Manager. Goodbye!")
            logger.info("Exiting Rusty Proxy Manager due to interrupt.")
            break # Exit the main menu loop on Ctrl+C
        except Exception as e:
            error_msg = f"\n[ERROR] An unexpected error occurred in the menu loop: {e}"
            print(error_msg)
            logger.error(error_msg, exc_info=True) # Log full traceback for menu errors


# --- Entry Point ---
if __name__ == '__main__':
    try:
        # Run the interactive menu, which manages the server lifecycle
        asyncio.run(interactive_menu())
    except Exception as e:
        critical_msg = f"\n[CRITICAL ERROR] Application failed during startup or main loop: {e}"
        print(critical_msg)
        logger.critical(critical_msg, exc_info=True)
        sys.exit(1)
