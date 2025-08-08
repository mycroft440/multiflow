#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import socketserver
import os
import sys
from urllib.parse import unquote

# --- Configurações ---
# O diretório onde o arquivo para download será colocado.
DOWNLOAD_DIR = '/opt/multiflow/downloads'
# Porta padrão caso nenhuma seja fornecida
DEFAULT_PORT = 8080

class DownloadRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handler customizado para forçar o download de um arquivo específico.
    """
    def do_GET(self):
        # Garante que o diretório de downloads exista
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)

        try:
            # Lista os arquivos no diretório de downloads
            files_in_dir = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
            
            if not files_in_dir:
                # Se não houver arquivos, envia uma mensagem de erro amigável
                self.send_response(404)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Erro 404</h1>")
                self.wfile.write(b"<p>Nenhum arquivo disponivel para download no momento.</p>")
                self.wfile.write(b"<p>Por favor, faca o upload de um arquivo para o diretorio: ")
                self.wfile.write(DOWNLOAD_DIR.encode('utf-8'))
                self.wfile.write(b"</p>")
                return

            # Pega o primeiro arquivo encontrado na pasta
            file_to_serve = files_in_dir[0]
            file_path = os.path.join(DOWNLOAD_DIR, file_to_serve)
            
            # Força o navegador a baixar o arquivo em vez de exibi-lo
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{unquote(file_to_serve)}"')
            fs = os.fstat(open(file_path, 'rb').fileno())
            self.send_header("Content-Length", str(fs.st_size))
            self.end_headers()
            
            # Envia o arquivo em blocos para economizar memória
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Erro 500 - Erro Interno do Servidor</h1>")
            self.wfile.write(f"<p>Ocorreu um erro: {e}</p>".encode('utf-8'))
            print(f"Erro ao servir o arquivo: {e}")

def run_server(port):
    # Muda o diretório de trabalho para o diretório de downloads
    # Isso é necessário para o SimpleHTTPRequestHandler funcionar corretamente
    os.chdir(DOWNLOAD_DIR)
    
    # Configura o servidor para reutilizar o endereço, evitando erros de "porta em uso"
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", port), DownloadRequestHandler) as httpd:
        print(f"Servidor de download iniciado na porta {port}")
        print(f"Servindo arquivos do diretorio: {DOWNLOAD_DIR}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor interrompido.")
            httpd.shutdown()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            print(f"Porta invalida. Usando a porta padrao {DEFAULT_PORT}.")
            PORT = DEFAULT_PORT
    else:
        PORT = DEFAULT_PORT
    
    run_server(PORT)
