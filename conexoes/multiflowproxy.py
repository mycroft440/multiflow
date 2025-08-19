import asyncio
import argparse
import logging
import sys
import traceback

# --- Configure maximum logging verbosity ---
# Create a custom logger
logger = logging.getLogger(__name__) # Use __name__ for better practice
logger.setLevel(logging.DEBUG) # Set logger level to DEBUG

# Create console handler and set level to DEBUG
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

# Create formatter with maximum detail (including filename, line number, function name)
# https://docs.python.org/3/library/logging.html#logrecord-attributes
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s'
)

# Add formatter to console handler
console_handler.setFormatter(detailed_formatter)

# Add console handler to logger
logger.addHandler(console_handler)

# Optionally, also enable asyncio's internal debug mode for even more detail
# This can produce a lot of output, especially for event loop operations
# https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode
# import os
# os.environ['PYTHONASYNCIODEBUG'] = '1' # Enable before importing asyncio
# Alternatively, set it programmatically (might need to be done early)
# asyncio.get_event_loop().set_debug(True) # Enable debug mode on the loop

# --- End logging configuration ---

# Global variables to hold server state
server_instance = None
current_port = None
current_status = None

async def handle_client(client_reader, client_writer):
    """
    Handles a client connection, determines the destination based on initial data,
    and forwards traffic.
    """
    client_addr = client_writer.get_extra_info('peername')
    logger.info(f"New connection from {client_addr}")

    try:
        # Send initial HTTP 101 Switching Protocols response
        status = current_status # Use global status
        initial_response = f"HTTP/1.1 101 {status}\r\n\r\n"
        logger.debug(f"Sending 101 response: {initial_response.strip()}")
        client_writer.write(initial_response.encode())
        await client_writer.drain()
        logger.debug("101 response sent and drained.")

        # --- Attempt to peek at initial data ---
        data_str = ""
        try:
            logger.debug("Attempting to peek at initial client data...")
            # Note: asyncio.StreamReader doesn't have a direct peek method like tokio's TcpStream.
            # We'll try reading with a short timeout. This consumes the data.
            # A more robust solution might involve using lower-level transports/protocols.
            data = await asyncio.wait_for(client_reader.read(8192), timeout=1.0)
            if data:
                data_str = data.decode('utf-8', errors='ignore')
                logger.debug(f"Initial data peeked/Read ({len(data)} bytes): {repr(data_str[:100])}...") # Log first 100 chars
                # IMPORTANT: The data is now consumed from the reader.
                # We need to pass this initial data when relaying later.
                initial_client_data = data
            else:
                 logger.debug("No initial data received (EOF?).")
                 initial_client_data = b""
        except asyncio.TimeoutError:
            logger.warning("Timeout reading initial data, defaulting to SSH port 22")
            initial_client_data = b"" # No data consumed within timeout
        except Exception as e:
             logger.error(f"Error peeking initial data: {e}", exc_info=True) # Log full traceback
             initial_client_data = b"" # Treat error as no data

        # Determine destination port based on initial data
        if "SSH" in data_str or not data_str.strip():
            dest_port = 22
            logger.info("Detected or defaulted to SSH traffic (port 22)")
        else:
            dest_port = 1194
            logger.info("Detected OpenVPN traffic (port 1194)")

        dest_addr = '127.0.0.1' # Assuming localhost as per original
        logger.info(f"Connecting to destination: {dest_addr}:{dest_port}")

        # Connect to the destination server
        try:
            logger.debug(f"Attempting to connect to destination server {dest_addr}:{dest_port}...")
            server_reader, server_writer = await asyncio.open_connection(dest_addr, dest_port)
            logger.info(f"Successfully connected to destination {dest_addr}:{dest_port}")
        except Exception as e:
            logger.error(f"Failed to connect to destination {dest_addr}:{dest_port} - {e}", exc_info=True)
            client_writer.close()
            await client_writer.wait_closed()
            return # Exit the handler

        # Send the initial HTTP 200 OK response to the client
        # Note: This seems unusual after the 101. Maybe the original intent was different?
        # Keeping it as is based on the Rust code.
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        logger.debug(f"Sending 200 OK response to client: {ok_response.strip()}")
        client_writer.write(ok_response.encode())
        await client_writer.drain()
        logger.debug("200 OK response sent and drained.")

        # --- Relay data ---
        # Pass the initial data read from the client to the server first
        if initial_client_data:
             logger.debug(f"Forwarding initial client data ({len(initial_client_data)} bytes) to server before starting relay.")
             server_writer.write(initial_client_data)
             await server_writer.drain()
             logger.debug("Initial client data forwarded to server.")

        logger.info("Starting bidirectional data relay...")
        await asyncio.gather(
            relay_data(client_reader, server_writer, f"client ({client_addr})->server ({dest_addr}:{dest_port})"),
            relay_data(server_reader, client_writer, f"server ({dest_addr}:{dest_port})->client ({client_addr})")
        )
        logger.info("Data relay stopped (EOF or error).")

    except asyncio.CancelledError:
        logger.info(f"Client handler for {client_addr} was cancelled.")
    except Exception as e:
        logger.error(f"Unexpected error handling client {client_addr}: {e}", exc_info=True) # Log full traceback
    finally:
        # Ensure both connections are closed
        logger.debug(f"Closing client connection {client_addr}...")
        client_writer.close()
        await client_writer.wait_closed()
        logger.info(f"Client connection {client_addr} closed.")

        # server_writer.close() and server_reader cleanup happens in relay_data or if connection failed


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
            # logger.debug(f"[{direction_tag}] Waiting to read data...")
            data = await reader.read(buffer_size)
            bytes_read = len(data)
            total_bytes += bytes_read
            logger.debug(f"[{direction_tag}] Read {bytes_read} bytes (Total: {total_bytes}). Data (repr): {repr(data[:50])}{'...' if bytes_read > 50 else ''}")

            if not data: # EOF
                logger.info(f"[{direction_tag}] EOF received. Stopping relay. Total bytes transferred: {total_bytes}")
                break

            # logger.debug(f"[{direction_tag}] Writing {bytes_read} bytes...")
            writer.write(data)
            await writer.drain()
            # logger.debug(f"[{direction_tag}] Wrote {bytes_read} bytes and drained.")

    except asyncio.CancelledError:
        logger.info(f"[{direction_tag}] Relay task was cancelled. Total bytes transferred: {total_bytes}")
    except Exception as e:
         logger.error(f"[{direction_tag}] Error relaying data: {e}", exc_info=True) # Log full traceback
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
        # Create server - Listen on all interfaces (0.0.0.0 or [::])
        # Using '0.0.0.0' as in the Rust code [::] binds to both IPv4 and IPv6
        # If issues, try '' or specific interface
        server = await asyncio.start_server(handle_client, '0.0.0.0', port)
        server_instance = server
        addr = server.sockets[0].getsockname() # Get actual bound address
        logger.info(f'Server successfully bound and listening on {addr[0]}:{addr[1]}')
        print(f"\n[INFO] Proxy server is now running on port {port} with status '{status}'")

        # Serve forever
        logger.debug("Entering server's serve_forever loop...")
        async with server:
            await server.serve_forever()

    except asyncio.CancelledError:
        logger.info("Server start task was cancelled.")
        print("\n[INFO] Proxy server stop initiated.")
    except Exception as e:
        logger.critical(f"Server failed to start or encountered an error: {e}", exc_info=True) # Log full traceback
        print(f"\n[ERROR] Failed to start server: {e}")
        server_instance = None # Indicate server is not running

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
        server_instance = None # Clear the reference
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

    # Set initial values from command line args or defaults
    parser = argparse.ArgumentParser(description='TCP Proxy for SSH/OpenVPN Tunneling (DEBUG MODE)')
    parser.add_argument('--port', type=int, default=80, help='Port to listen on (default: 80)')
    parser.add_argument('--status', type=str, default='@RustyManager', help='Status message for HTTP responses (default: @RustyManager)')
    # Adding a flag to easily increase asyncio debug mode
    parser.add_argument('--asyncio-debug', action='store_true', help='Enable asyncio debug mode') # [[3]]
    args = parser.parse_args()

    current_port = args.port
    current_status = args.status

    # Enable asyncio debug mode if requested
    if args.asyncio_debug:
        logger.info("Enabling asyncio debug mode via argument.")
        asyncio.get_event_loop().set_debug(True) # [[3]]

    print(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")
    logger.info(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")

    while True:
        display_menu()
        try:
            # Use run_in_executor for blocking input
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                if server_instance and server_instance.is_serving():
                    print("\n[INFO] Server is already running.")
                    logger.info("User attempted to start server, but it's already running.")
                else:
                    # Get port
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

                    # Get status
                    status_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter status message (default '{current_status}'): ")
                    status_input = status_input.strip()
                    if status_input:
                        current_status = status_input
                        logger.info(f"Status message updated to '{current_status}' based on user input.")

                    logger.info(f"Initiating server start on port {current_port} with status '{current_status}'")
                    # Start server in the background using create_task
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
                logger.info(status_msg.replace("\n[INFO] ", "")) # Log without newline prefix

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
            logger.error(error_msg, exc_info=True) # Log full traceback for menu errors

if __name__ == '__main__':
    try:
        # Enable asyncio debug mode via environment variable if needed
        # import os
        # if os.environ.get('PYTHONASYNCIODEBUG'):
        #     logger.info("PYTHONASYNCIODEBUG environment variable detected, enabling asyncio debug.")
        #     asyncio.get_event_loop().set_debug(True)

        asyncio.run(interactive_menu())
    except Exception as e:
        critical_msg = f"\n[CRITICAL ERROR] Application failed during startup or main loop: {e}"
        print(critical_msg)
        logger.critical(critical_msg, exc_info=True) # Log full traceback for startup errors
        sys.exit(1)
