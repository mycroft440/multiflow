use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;

fn main() {
    let listener = TcpListener::bind("127.0.0.1:1080").expect("Failed to bind to port 1080");
    println!("SOCKS5 proxy listening on 127.0.0.1:1080");

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

