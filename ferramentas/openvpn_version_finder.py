#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import urllib.request
import re
import json
import sys

UA = "OpenVPNVersionFinder/1.1 (+https://openvpn.net/)"


def http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_versions_from_swupdate(html):
    # Captura apenas releases estáveis do diretório de releases
    # Ex.: openvpn-2.6.12.tar.gz
    pattern = re.compile(r'href="(openvpn-([0-9]+)\.([0-9]+)\.([0-9]+)\.tar\.gz)"')
    matches = pattern.findall(html)
    versions = []
    for fname, major, minor, patch in matches:
        versions.append((int(major), int(minor), int(patch), fname))
    return versions


def find_latest_from_swupdate():
    base = "https://swupdate.openvpn.net/community/releases/"
    try:
        html = http_get(base, timeout=12)
        versions = parse_versions_from_swupdate(html)
        if not versions:
            return None
        # Escolhe a maior versão sem rc/beta/alpha (não aparecem nesse padrão)
        versions.sort(reverse=True)
        fname = versions[0][3]
        return base + fname
    except Exception:
        return None


def find_latest_from_github():
    # Tenta via releases do GitHub (estáveis) e usa asset tar.gz se existir,
    # caso contrário usa o tarball "Source code".
    try:
        api_url = "https://api.github.com/repos/OpenVPN/openvpn/releases?per_page=20"
        data = json.loads(http_get(api_url, timeout=12))
        # Filtra releases estáveis
        releases = [r for r in data if not r.get("prerelease", False)]
        if not releases:
            return None
        # Ordena por created_at desc
        releases.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        for rel in releases:
            # Procura um asset .tar.gz oficial (raramente presente)
            for asset in rel.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".tar.gz") and name.startswith("openvpn-"):
                    return asset.get("browser_download_url")
            # Fallback: tarball do código-fonte (pode exigir autoreconf na compilação)
            tag = rel.get("tag_name", "").lstrip("v")
            if re.match(r"^\d+\.\d+\.\d+$", tag):
                return f"https://github.com/OpenVPN/openvpn/archive/refs/tags/v{tag}.tar.gz"
        return None
    except Exception:
        return None


def find_latest_openvpn_url():
    # Preferimos o tarball do servidor de releases oficial (tem configure pronto).
    url = find_latest_from_swupdate()
    if url:
        return url
    # Fallback: GitHub (pode precisar de autoreconf)
    return find_latest_from_github()


if __name__ == "__main__":
    latest_url = find_latest_openvpn_url()
    if latest_url:
        print(latest_url)
        sys.exit(0)
    sys.exit(1)
