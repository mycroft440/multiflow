#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import re
import json

def find_latest_openvpn_url():
    """
    Encontra a URL do código-fonte da versão estável mais recente do OpenVPN.
    
    Tenta primeiro via API do GitHub, que é mais confiável. Se falhar,
    usa como fallback a página de downloads da comunidade.
    """
    # --- Método 1: API do GitHub (Preferencial) ---
    try:
        api_url = "https://api.github.com/repos/OpenVPN/openvpn/releases/latest"
        with urllib.request.urlopen(api_url, timeout=10) as response:
            data = json.loads(response.read().decode())
            # Procura pelo arquivo tar.gz nos assets da release
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".tar.gz"):
                    return asset.get("browser_download_url")
    except Exception:
        # Se a API do GitHub falhar, ignora e tenta o método 2
        pass

    # --- Método 2: Scraping da Página de Downloads (Fallback) ---
    try:
        community_url = "https://community.openvpn.net/openvpn/wiki/OpenvpnDownloads"
        with urllib.request.urlopen(community_url, timeout=10) as response:
            html_content = response.read().decode('utf-8')
        
        # Expressão regular para encontrar links como 'openvpn-2.6.11.tar.gz'
        # Prioriza versões estáveis (sem 'alpha', 'beta', 'rc')
        regex = r'href="(https://swupdate\.openvpn\.net/community/releases/openvpn-[\d\.]+\.tar\.gz)"'
        matches = re.findall(regex, html_content)
        
        if matches:
            # A página pode listar várias versões, a mais recente geralmente está no topo.
            # A regex já filtra para garantir que seja um link de release da comunidade.
            return matches[0]
            
    except Exception:
        return None

    return None

if __name__ == "__main__":
    latest_url = find_latest_openvpn_url()
    if latest_url:
        # Imprime a URL para que o script shell possa capturá-la
        print(latest_url)
    else:
        # Sai com um código de erro se não encontrar
        exit(1)
