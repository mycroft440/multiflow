use std::env;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;
use std::time::Duration;

const SOCKS_VERSION: u8 = 0x05;
const CONNECT_COMMAND: u8 = 0x01;
const IPV4_ADDR_TYPE: u8 = 0x01;
const DOMAIN_ADDR_TYPE: u8 = 0x03;
const IPV6_ADDR_TYPE: u8 = 0x04;

fn main() {
    let port = env::var("SOCKS5_PORT")
        .unwrap_or_else(|_| "1080".to_string())
        .parse::<u16>()
        .unwrap_or(1080);

    let listener = TcpListener::bind(format!("0.0.0.0:{}", port))
        .expect("Failed to bind to address");

    println!("SOCKS5 proxy server listening on port {}", port);

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                thread::spawn(move || {
                    if let Err(e) = handle_client(stream) {
                        eprintln!("Error handling client: {}", e);
                    }
                });
            }
            Err(e) => {
                eprintln!("Error accepting connection: {}", e);
            }
        }
    }
}

fn handle_client(mut stream: TcpStream) -> io::Result<()> {
    // Set timeouts
    stream.set_read_timeout(Some(Duration::from_secs(30)))?;
    stream.set_write_timeout(Some(Duration::from_secs(30)))?;

    // Peek into the stream to detect protocol
    let initial_data = peek_stream(&stream)?;

    if initial_data.contains("SSH") {
        // Handle as SSH traffic
        println!("Detected SSH traffic. Routing to 0.0.0.0:22");
        stream.write_all(b"HTTP/1.1 200 OK\r\n\r\n")?;
        let target_stream = TcpStream::connect("0.0.0.0:22")?;
        relay_data(stream, target_stream)?;
    } else if initial_data.contains("OpenVPN") || initial_data.contains("VPN") {
        // Handle as OpenVPN traffic (assuming it's TCP for now)
        println!("Detected OpenVPN traffic. Routing to 0.0.0.0:1194");
        stream.write_all(b"HTTP/1.1 200 OK\r\n\r\n")?;
        let target_stream = TcpStream::connect("0.0.0.0:1194")?;
        relay_data(stream, target_stream)?;
    } else {
        // Assume SOCKS5 or other HTTP traffic
        // Handle authentication
        handle_authentication(&mut stream)?;

        // Handle connection request
        handle_connection_request(&mut stream)?;
    }

    Ok(())
}

fn handle_authentication(stream: &mut TcpStream) -> io::Result<()> {
    let mut buffer = [0u8; 2];
    stream.read_exact(&mut buffer)?;

    let version = buffer[0];
    let nmethods = buffer[1];

    if version != SOCKS_VERSION {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Unsupported SOCKS version",
        ));
    }

    let mut methods = vec![0u8; nmethods as usize];
    stream.read_exact(&mut methods)?;

    // We support no authentication (0x00)
    let response = [SOCKS_VERSION, 0x00];
    stream.write_all(&response)?;

    Ok(())
}

fn handle_connection_request(stream: &mut TcpStream) -> io::Result<()> {
    let mut buffer = [0u8; 4];
    stream.read_exact(&mut buffer)?;

    let version = buffer[0];
    let command = buffer[1];
    let _reserved = buffer[2];
    let addr_type = buffer[3];

    if version != SOCKS_VERSION {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Unsupported SOCKS version",
        ));
    }

    if command != CONNECT_COMMAND {
        send_error_response(stream, 0x07)?; // Command not supported
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Unsupported command",
        ));
    }

    let target_addr = match addr_type {
        IPV4_ADDR_TYPE => {
            let mut addr_buf = [0u8; 6]; // 4 bytes IP + 2 bytes port
            stream.read_exact(&mut addr_buf)?;
            let ip = format!(
                "{}.{}.{}.{}",
                addr_buf[0], addr_buf[1], addr_buf[2], addr_buf[3]
            );
            let port = u16::from_be_bytes([addr_buf[4], addr_buf[5]]);
            format!("{}:{}", ip, port)
        }
        DOMAIN_ADDR_TYPE => {
            let mut len_buf = [0u8; 1];
            stream.read_exact(&mut len_buf)?;
            let domain_len = len_buf[0] as usize;

            let mut domain_buf = vec![0u8; domain_len + 2]; // domain + 2 bytes port
            stream.read_exact(&mut domain_buf)?;

            let domain = String::from_utf8_lossy(&domain_buf[..domain_len]);
            let port = u16::from_be_bytes([
                domain_buf[domain_len],
                domain_buf[domain_len + 1],
            ]);
            format!("{}:{}", domain, port)
        }
        IPV6_ADDR_TYPE => {
            let mut addr_buf = [0u8; 18]; // 16 bytes IP + 2 bytes port
            stream.read_exact(&mut addr_buf)?;
            // IPv6 implementation would go here
            send_error_response(stream, 0x08)?; // Address type not supported
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "IPv6 not supported",
            ));
        }
        _ => {
            send_error_response(stream, 0x08)?; // Address type not supported
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Unsupported address type",
            ));
        }
    };

    // Connect to target
    match TcpStream::connect(&target_addr) {
        Ok(mut target_stream) => {
            // Send success response
            let response = [
                SOCKS_VERSION,
                0x00, // Success
                0x00, // Reserved
                IPV4_ADDR_TYPE,
                0, 0, 0, 0, // Bind IP (0.0.0.0)
                0, 0, // Bind port (0)
            ];
            stream.write_all(&response)?;

            // Start relaying data
            relay_data(stream.try_clone()?, target_stream)?;
        }
        Err(_) => {
            send_error_response(stream, 0x05)?; // Connection refused
        }
    }

    Ok(())
}

fn send_error_response(stream: &mut TcpStream, error_code: u8) -> io::Result<()> {
    let response = [
        SOCKS_VERSION,
        error_code,
        0x00, // Reserved
        IPV4_ADDR_TYPE,
        0, 0, 0, 0, // Bind IP
        0, 0, // Bind port
    ];
    stream.write_all(&response)?;
    Ok(())
}

fn relay_data(mut client: TcpStream, mut target: TcpStream) -> io::Result<()> {
    let mut client_clone = client.try_clone()?;
    let mut target_clone = target.try_clone()?;

    let client_to_target = thread::spawn(move || {
        io::copy(&mut client_clone, &mut target_clone)
    });

    let target_to_client = thread::spawn(move || {
        io::copy(&mut target, &mut client)
    });

    // Wait for either direction to finish
    let _ = client_to_target.join();
    let _ = target_to_client.join();

    Ok(())
}

// Function to peek into the stream to detect protocol
fn peek_stream(stream: &TcpStream) -> io::Result<String> {
    let mut peek_buffer = vec![0; 8192];
    let bytes_peeked = stream.peek(&mut peek_buffer)?;
    let data = &peek_buffer[..bytes_peeked];
    let data_str = String::from_utf8_lossy(data);
    Ok(data_str.to_string())
}

