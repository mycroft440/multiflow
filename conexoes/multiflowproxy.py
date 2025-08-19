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
        if sock is None: # Correct way to check for None
            logger.warning("Could not get underlying socket for peeking.")
            return ""

        # Use asyncio.wait_for to implement timeout
        loop = asyncio.get_event_loop()

        def _peek():
            # Perform the peek operation on the socket
            # MSG_PEEK reads data without removing it from the queue
            # Handle potential errors during peek
            try:
                return sock.recv(length, socket.MSG_PEEK)
            except BlockingIOError:
                 # No data available immediately, return empty bytes
                 return b""
            except Exception as e:
                 # Re-raise other socket errors
                 raise e

        # Apply timeout to the executor call
        data_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _peek), timeout=timeout_duration
        )
        # Ensure data_bytes is not None (though it shouldn't be from recv)
        if data_bytes is None:
            data_bytes = b""
        data_str = data_bytes.decode('utf-8', errors='ignore')
        logger.debug(f"Peeked {len(data_bytes)} bytes: {repr(data_str[:100])}...")
        return data_str
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

        # --- Read initial data for protocol detection (Rust code reads, not peeks here) ---
        # Note: The Rust code actually *reads* the first 1024 bytes into a buffer
        # and then proceeds. It doesn't seem to rely on peeking for the initial detection
        # in the way the previous Python version tried to. Let's mimic the Rust logic more closely.
        # However, the Rust peek is used for content inspection.

        # First, read the initial data (like Rust does with the 1024 buffer)
        logger.debug("Reading initial client data for protocol detection (like Rust)...")
        initial_buffer = bytearray(1024) # Match Rust's initial buffer size
        try:
             bytes_read_initial = await asyncio.wait_for(client_reader.readinto(initial_buffer), timeout=1.0)
             if bytes_read_initial > 0:
                  initial_data_for_check = initial_buffer[:bytes_read_initial].decode('utf-8', errors='ignore')
                  logger.debug(f"Read {bytes_read_initial} bytes for initial check: {repr(initial_data_for_check[:100])}...")
             else:
                  initial_data_for_check = ""
                  logger.debug("No initial data read (EOF?).")
        except asyncio.TimeoutError:
            logger.warning("Timeout reading initial data for protocol check.")
            initial_data_for_check = ""
        except Exception as e:
             logger.error(f"Error reading initial data for protocol check: {e}", exc_info=True)
             initial_data_for_check = "" # Default to SSH on error

        # --- Use peek to inspect initial data without consuming it (for detailed inspection if needed) ---
        # The peek can still be useful for more detailed inspection if the initial read is inconclusive
        # or if we want to be extra sure. For now, let's rely primarily on the initial read like Rust.
        logger.debug("Attempting to peek at initial client data (for potential detailed inspection)...")
        peeked_data_str = await peek_data(client_reader, length=8192, timeout_duration=1.0)

        # Determine destination port based on *initial read data* (mimicking Rust closer)
        # Rust checks the data read into the 1024 buffer
        if "SSH" in initial_data_for_check or not initial_data_for_check.strip():
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
        # Note: The Rust code writes this *after* reading the initial 1024 bytes
        # and *before* connecting to the server. Let's keep this order.
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        logger.debug(f"Sending 200 OK response to client: {repr(ok_response)}")
        client_writer.write(ok_response.encode())
        await client_writer.drain()
        logger.debug("200 OK response sent and drained.")

        # --- Important: Write the initial data that was read to the server ---
        # The Rust code reads 1024 bytes initially. That data must be sent to the server
        # because it's part of the client's stream.
        if bytes_read_initial > 0:
             logger.debug(f"Forwarding initial {bytes_read_initial} bytes read to the server.")
             server_writer.write(initial_buffer[:bytes_read_initial])
             await server_writer.drain()
             logger.debug("Initial data forwarded to server.")

        # --- Relay data bidirectionally ---
        # The peeked data is still in the client stream, but we already sent the initial read data.
        # The relay should now continue normally.
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
        # Run the server forever in the background task
        # We don't await serve_forever here directly inside start_server
        # because it blocks. Instead, we let the task run.
        # The menu loop needs to continue.
        # We need to signal that the server is running and let the menu continue.
        # Let's run serve_forever in its own task.
        server_task = asyncio.create_task(server.serve_forever())
        # Keep a reference to the task to prevent it from being garbage collected?
        # Or store the task? Let's just log that it's started.
        logger.info("Server task started, running in background.")

    except Exception as e: # Catch general exceptions during server creation
        logger.critical(f"Server failed to start or encountered an error during setup: {e}", exc_info=True)
        print(f"\n[ERROR] Failed to start server setup: {e}")
        server_instance = None


async def stop_server():
    """Stops the currently running server."""
    global server_instance
    if server_instance:
        # Check if it's actually serving (hasn't been closed already)
        # is_serving might not be perfectly reliable, but it's a start
        # Let's try closing it directly and handle potential errors
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
    # Check if server instance exists and seems to be serving
    # This check might not be 100% accurate, but gives a general idea
    if server_instance is not None:
        # Let's assume if it exists, it's intended to be running
        # A more robust check might involve checking the task or internal state
        # but this is simpler for now.
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
        # Enable asyncio debug mode on the current loop
        loop = asyncio.get_running_loop()
        loop.set_debug(True)

    print(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")
    logger.info(f"Rusty Proxy Manager (DEBUG) initialized with default port {current_port} and status '{current_status}'")

    while True:
        display_menu()
        try:
            # Use run_in_executor for blocking input to keep the event loop free
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                # Check if server is seemingly already running
                if server_instance is not None:
                    print("\n[INFO] Server start command received, but a server instance might already exist. Attempting to start anyway (this might fail or create issues if one is truly running).")
                    logger.info("User attempted to start server, but server_instance is not None. Proceeding with caution.")
                #else: # Normal case

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
                # Start server - this should now correctly initiate the server task
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
                # Attempt to stop server if it seems to be running
                if server_instance is not None:
                    logger.info("Server instance exists, attempting to stop it before exit.")
                    await stop_server()
                print("\nExiting Rusty Proxy Manager. Goodbye!")
                logger.info("Exiting Rusty Proxy Manager.")
                break # Exit the menu loop

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
            break # Exit the menu loop on Ctrl+C
        except Exception as e:
            error_msg = f"\n[ERROR] An unexpected error occurred in the menu loop: {e}"
            print(error_msg)
            logger.error(error_msg, exc_info=True) # Log full traceback for menu errors


if __name__ == '__main__':
    try:
        # Run the interactive menu, which manages the server lifecycle
        asyncio.run(interactive_menu())
    except Exception as e:
        critical_msg = f"\n[CRITICAL ERROR] Application failed during startup or main loop: {e}"
        print(critical_msg)
        logger.critical(critical_msg, exc_info=True)
        sys.exit(1)
