import asyncio
import argparse
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        client_writer.write(initial_response.encode())
        await client_writer.drain()

        # Read initial data to determine protocol (SSH or OpenVPN)
        try:
            data = await asyncio.wait_for(client_reader.read(8192), timeout=1.0)
            data_str = data.decode('utf-8', errors='ignore')
            logger.debug(f"Peeked data: {data_str}")
        except asyncio.TimeoutError:
            logger.warning("Timeout reading initial data, defaulting to SSH port 22")
            data_str = ""

        # Determine destination port based on initial data
        if "SSH" in data_str or not data_str.strip():
            dest_port = 22
            logger.info("Detected or defaulted to SSH traffic")
        else:
            dest_port = 1194
            logger.info("Detected OpenVPN traffic")

        dest_addr = '127.0.0.1' # Assuming localhost, change if needed
        logger.info(f"Connecting to destination: {dest_addr}:{dest_port}")

        # Connect to the destination server
        try:
            server_reader, server_writer = await asyncio.open_connection(dest_addr, dest_port)
        except Exception as e:
            logger.error(f"Failed to connect to destination {dest_addr}:{dest_port} - {e}")
            client_writer.close()
            await client_writer.wait_closed()
            return

        logger.info(f"Connected to destination {dest_addr}:{dest_port}")

        # Send the initial HTTP 200 OK response to the client
        ok_response = f"HTTP/1.1 200 {status}\r\n\r\n"
        client_writer.write(ok_response.encode())
        await client_writer.drain()

        # Relay data between client and server
        await asyncio.gather(
            relay_data(client_reader, server_writer, "client->server"),
            relay_data(server_reader, client_writer, "server->client")
        )

    except Exception as e:
        logger.error(f"Error handling client {client_addr}: {e}")
    finally:
        client_writer.close()
        await client_writer.wait_closed()
        logger.info(f"Connection with {client_addr} closed")


async def relay_data(reader, writer, direction):
    """
    Relays data from a reader to a writer.
    """
    try:
        while True:
            data = await reader.read(8192)
            if not data:
                logger.debug(f"EOF received in {direction}")
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        logger.error(f"Error relaying data ({direction}): {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_server(port, status):
    """
    Starts the TCP server.
    """
    global server_instance, current_port, current_status
    current_port = port
    current_status = status

    try:
        # Create server
        server = await asyncio.start_server(handle_client, '0.0.0.0', port)
        server_instance = server
        addr = server.sockets[0].getsockname()
        logger.info(f'Serving on {addr[0]}:{addr[1]}')
        print(f"\n[INFO] Proxy server is now running on port {port} with status '{status}'")

        # Serve forever
        async with server:
            await server.serve_forever()

    except asyncio.CancelledError:
        logger.info("Server task was cancelled.")
        print("\n[INFO] Proxy server stopped.")
    except Exception as e:
        logger.critical(f"Server failed to start or encountered an error: {e}")
        print(f"\n[ERROR] Failed to start server: {e}")
        server_instance = None # Indicate server is not running

async def stop_server():
    """Stops the currently running server."""
    global server_instance
    if server_instance and server_instance.is_serving():
        server_instance.close()
        await server_instance.wait_closed()
        print("\n[INFO] Proxy server stopped.")
        server_instance = None
    else:
        print("\n[INFO] No server is currently running.")

def display_menu():
    """Displays the interactive menu."""
    print("\n--- Rusty Proxy Manager ---")
    if server_instance and server_instance.is_serving():
        print(f"Status: Running on port {current_port}")
    else:
        print("Status: Stopped")
    print("1. Start Server")
    print("2. Stop Server")
    print("3. Show Status")
    print("4. Exit")
    print("---------------------------")

async def interactive_menu():
    """Main loop for the interactive menu."""
    global current_port, current_status

    # Set initial values from command line args or defaults
    parser = argparse.ArgumentParser(description='TCP Proxy for SSH/OpenVPN Tunneling')
    parser.add_argument('--port', type=int, default=80, help='Port to listen on (default: 80)')
    parser.add_argument('--status', type=str, default='@RustyManager', help='Status message for HTTP responses (default: @RustyManager)')
    args = parser.parse_args()

    current_port = args.port
    current_status = args.status

    print(f"Rusty Proxy Manager initialized with default port {current_port} and status '{current_status}'")

    while True:
        display_menu()
        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Enter your choice (1-4): ")
            choice = choice.strip()

            if choice == '1':
                if server_instance and server_instance.is_serving():
                    print("\n[INFO] Server is already running.")
                else:
                    port_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter port (default {current_port}): ")
                    port_input = port_input.strip()
                    if port_input:
                        try:
                            new_port = int(port_input)
                            if 1 <= new_port <= 65535:
                                current_port = new_port
                            else:
                                print("[WARNING] Invalid port number. Using current port.")
                        except ValueError:
                            print("[WARNING] Invalid input. Using current port.")

                    status_input = await asyncio.get_event_loop().run_in_executor(None, input, f"Enter status message (default '{current_status}'): ")
                    status_input = status_input.strip()
                    if status_input:
                        current_status = status_input

                    # Start server in the background
                    asyncio.create_task(start_server(current_port, current_status))

            elif choice == '2':
                await stop_server()

            elif choice == '3':
                if server_instance and server_instance.is_serving():
                    print(f"\n[INFO] Server Status: Running on port {current_port} with status '{current_status}'")
                else:
                    print("\n[INFO] Server Status: Stopped")

            elif choice == '4':
                if server_instance and server_instance.is_serving():
                    await stop_server()
                print("\nExiting Rusty Proxy Manager. Goodbye!")
                break

            else:
                print("\n[ERROR] Invalid choice. Please enter a number between 1 and 4.")

        except KeyboardInterrupt:
            print("\n\nReceived interrupt signal.")
            if server_instance and server_instance.is_serving():
                await stop_server()
            print("Exiting Rusty Proxy Manager. Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error in menu loop: {e}")
            print(f"\n[ERROR] An unexpected error occurred: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(interactive_menu())
    except Exception as e:
        logger.critical(f"Critical error running the application: {e}")
        print(f"\n[CRITICAL ERROR] Application failed: {e}")
        sys.exit(1)
