use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;
use std::env;

fn main() {
    let port = env::var("SOCKS5_PORT").unwrap_or_else(|_| "1080".to_string());
    let bind_address = format!("127.0.0.1:{}", port);
    let listener = TcpListener::bind(&bind_address).expect(&format!("Failed to bind to port {}", port));
    println!("SOCKS5 proxy listening on {}", bind_address);

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                thread::spawn(move || {
                    handle_client(stream);
                });
            }
            Err(e) => {
                eprintln!("Error accepting connection: {}", e);
            }
        }
    }
}

fn handle_client(mut stream: TcpStream) {
    let mut buffer = [0; 1024];
    
    // Read the initial SOCKS5 handshake
    match stream.read(&mut buffer) {
        Ok(n) if n > 0 => {
            // Simple SOCKS5 response (no authentication)
            let response = [0x05, 0x00]; // Version 5, No authentication
            if stream.write_all(&response).is_err() {
                return;
            }
        }
        _ => return,
    }

    // Read the connection request
    match stream.read(&mut buffer) {
        Ok(n) if n > 0 => {
            // Simple response: connection not allowed
            let response = [0x05, 0x07, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
            let _ = stream.write_all(&response);
        }
        _ => return,
    }
}
