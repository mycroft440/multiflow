#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import socketserver
import os
import sys
import cgi
import shutil
from urllib.parse import unquote

# --- Configurações ---
DOWNLOAD_DIR = '/opt/multiflow/downloads'
DEFAULT_PORT = 8080
HOST_NAME = '0.0.0.0'

class UploadDownloadHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handler customizado para servir uma página de upload e forçar o download.
    """

    def _get_current_file(self):
        """Retorna o nome do primeiro arquivo encontrado no diretório."""
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
        files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
        return files[0] if files else None

    def _html_template(self, title, body_content, status_message=""):
        """Gera o template HTML base para as páginas."""
        status_html = ""
        if status_message:
            status_html = f"""
            <div id="status-message" class="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-lg mb-6 shadow-md animate-fade-in-fast">
                <p class="font-bold">Sucesso!</p>
                <p>{status_message}</p>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - Multiflow</title>
            <script src="https://cdn.tailwindcss.com"></script>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Inter', sans-serif; }}
                .gradient-bg {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6, #93c5fd); }}
                @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
                .animate-fade-in {{ animation: fadeIn 0.5s ease-out forwards; }}
                .drop-zone--over {{ border-style: solid; background-color: #dbeafe; }}
            </style>
        </head>
        <body class="gradient-bg flex items-center justify-center min-h-screen p-4">
            <div class="bg-white bg-opacity-90 backdrop-blur-lg rounded-2xl shadow-2xl p-8 max-w-2xl w-full text-center animate-fade-in">
                {status_html}
                {body_content}
                <footer class="mt-8 text-sm text-gray-500">
                    <p>Powered by: <span class="font-semibold text-blue-700">Mycroft</span></p>
                </footer>
            </div>
            <script>
                {self._get_javascript()}
            </script>
        </body>
        </html>
        """

    def _serve_upload_page(self, status_message=""):
        """Serve a página principal com o formulário de upload."""
        current_file = self._get_current_file()
        
        file_status_html = ""
        if current_file:
            file_status_html = f"""
            <div class="bg-blue-50 border border-blue-200 p-4 rounded-lg mb-6">
                <h3 class="text-lg font-semibold text-gray-700 mb-2">Arquivo Atual para Download</h3>
                <p class="text-blue-800 font-mono break-all mb-3">{current_file}</p>
                <a href="/download" class="inline-block bg-blue-600 text-white font-bold py-2 px-5 rounded-lg shadow-md hover:bg-blue-700 transition-transform transform hover:scale-105">
                    Baixar Arquivo
                </a>
            </div>
            """
        else:
            file_status_html = f"""
            <div class="bg-yellow-50 border border-yellow-200 p-4 rounded-lg mb-6">
                <h3 class="text-lg font-semibold text-gray-700">Nenhum arquivo disponível</h3>
                <p class="text-yellow-800">Faça o upload de um arquivo para criar um link de download.</p>
            </div>
            """

        body_content = f"""
            <div class="mx-auto bg-blue-600 rounded-full h-16 w-16 flex items-center justify-center shadow-lg mb-4">
                <svg class="h-10 w-10 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
            </div>
            <h1 class="text-3xl font-bold text-gray-800 mb-4">Servidor de Upload</h1>
            {file_status_html}
            <form id="upload-form" action="/upload" method="post" enctype="multipart/form-data">
                <div id="drop-zone" class="border-4 border-dashed border-gray-300 rounded-xl p-8 cursor-pointer hover:border-blue-500 transition-colors">
                    <input type="file" name="file" id="file-input" class="hidden">
                    <p id="drop-zone-prompt" class="text-gray-500">Arraste e solte um arquivo aqui ou <span class="text-blue-600 font-semibold">clique para selecionar</span>.</p>
                </div>
                <button type="submit" class="mt-6 w-full bg-green-600 text-white font-bold py-3 px-6 rounded-lg shadow-lg hover:bg-green-700 transition-transform transform hover:scale-105 focus:outline-none">
                    Fazer Upload
                </button>
            </form>
        """
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self._html_template("Upload de Arquivo", body_content, status_message).encode('utf-8'))

    def _serve_download(self):
        """Serve o arquivo para download."""
        file_to_serve = self._get_current_file()
        if not file_to_serve:
            self.send_error(404, "Nenhum arquivo para download encontrado.")
            return

        file_path = os.path.join(DOWNLOAD_DIR, file_to_serve)
        try:
            with open(file_path, 'rb') as f:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{unquote(file_to_serve)}"')
                fs = os.fstat(f.fileno())
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()
                shutil.copyfileobj(f, self.wfile)
        except FileNotFoundError:
            self.send_error(404, "Arquivo não encontrado.")
        except Exception as e:
            self.send_error(500, f"Erro no servidor: {e}")

    def do_GET(self):
        if self.path == '/':
            self._serve_upload_page()
        elif self.path == '/download':
            self._serve_download()
        else:
            self.send_error(404, "Página não encontrada.")

    def do_POST(self):
        if self.path == '/upload':
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']}
            )
            
            if 'file' not in form or not form['file'].filename:
                self.send_error(400, "Nenhum arquivo foi enviado.")
                return

            file_item = form['file']
            filename = os.path.basename(file_item.filename)
            
            # Limpa o diretório antes de salvar o novo arquivo
            for f in os.listdir(DOWNLOAD_DIR):
                os.remove(os.path.join(DOWNLOAD_DIR, f))

            # Salva o novo arquivo
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(file_item.file.read())
            
            # Redireciona para a página principal com mensagem de sucesso
            self._serve_upload_page(status_message=f"Arquivo '{filename}' enviado com sucesso!")
        else:
            self.send_error(404, "Endpoint não encontrado.")

    def _get_javascript(self):
        return """
            const dropZone = document.getElementById('drop-zone');
            const fileInput = document.getElementById('file-input');
            const dropZonePrompt = document.getElementById('drop-zone-prompt');
            const statusMessage = document.getElementById('status-message');

            dropZone.addEventListener('click', () => fileInput.click());

            fileInput.addEventListener('change', () => {
                if (fileInput.files.length > 0) {
                    dropZonePrompt.innerHTML = `<span class="text-green-600 font-semibold">Arquivo selecionado: ${fileInput.files[0].name}</span>`;
                }
            });

            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                });
            });

            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.add('drop-zone--over'));
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, () => dropZone.classList.remove('drop-zone--over'));
            });

            dropZone.addEventListener('drop', (e) => {
                const dt = e.dataTransfer;
                if (dt.files.length > 0) {
                    fileInput.files = dt.files;
                    dropZonePrompt.innerHTML = `<span class="text-green-600 font-semibold">Arquivo selecionado: ${dt.files[0].name}</span>`;
                }
            });

            if(statusMessage) {
                setTimeout(() => {
                    statusMessage.style.transition = 'opacity 0.5s ease';
                    statusMessage.style.opacity = '0';
                    setTimeout(() => statusMessage.remove(), 500);
                }, 4000);
            }
        """

def run_server(port):
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer((HOST_NAME, port), UploadDownloadHandler) as httpd:
        print(f"Servidor de upload/download iniciado em http://{HOST_NAME}:{port}")
        print(f"Diretório de arquivos: {DOWNLOAD_DIR}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor interrompido.")
            httpd.shutdown()

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else DEFAULT_PORT
    run_server(PORT)
