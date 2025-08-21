#!/usr/bin/env python3
"""
DNS‑AGN Python Manager
======================

This module provides a Python re‑implementation of the original
DNS‑AGN project.  The upstream repository is a collection of bash
scripts used to install and manage a DNSTT (SlowDNS) server.  Those
scripts download a pre‑built `dns-server` binary, configure
dependencies, open firewall ports, update `resolv.conf` to use
Cloudflare, generate or import key pairs, and start the DNS tunnel in
screen sessions.  They also provide an interactive menu that allows
the operator to install different service flavours (SSH, SSL,
Dropbear and SOCKS), start/stop/restart the tunnel, inspect
configuration information and remove or update the installation.  For
example, the bash installer downloads a number of helper scripts and
the `dns-server` binary into ``/etc/slowdns`` and marks them as
executable【294821352446467†L46-L65】.  It also opens ports in
firewalld for the various services【294821352446467†L73-L79】 and
temporarily sets Cloudflare DNS by editing ``/etc/resolv.conf``【294821352446467†L84-L89】.

This Python module attempts to replicate that behaviour in a more
structured way.  All interactive input/output is handled via the
console, and the same steps (dependency installation, file
download/extraction, key management and service control) are exposed
through Python functions.  Users should run this script with root
privileges on a Debian/Ubuntu system for the commands to succeed.  If
you do not have ``apt``, ``iptables`` or ``firewalld`` available, the
script will print instructions instead of executing the commands.

Credit
------

The original bash project was created by @Laael and modified by
@KhaledAGN.  This Python rewrite was prepared by **@mycroftchat**, as
requested by the user.  The logic closely follows the upstream
scripts such as ``install``, ``slowdns``, ``slowdns-ssh`` and the
``startdns`` helpers【294821352446467†L46-L65】【508339094020233†L72-L122】【88752286916456†L28-L33】.

"""

import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class DNSAGNManager:
    """A Python re‑implementation of the DNS‑AGN management scripts.

    Each instance of this class exposes methods to install the core
    manager, install service flavours (SSH, SSL, Dropbear and SOCKS),
    start/stop/restart the DNS tunnel, view configuration
    information, remove the installation and perform an update.  Most
    methods will call out to the system via ``subprocess.run`` and
    therefore must be executed with appropriate privileges.  When
    running on an unsupported platform, the commands are printed
    rather than executed.
    """

    #: Base URL for raw files on GitHub.  All scripts and binaries are
    #: downloaded from this location.
    BASE_URL: str = "https://raw.githubusercontent.com/khaledagn/DNS-AGN/main"

    #: Directory used to store helper scripts and the dns-server binary.
    SLOWDNS_DIR: Path = Path("/etc/slowdns")

    #: Path to the private key.  It is placed in ``/root`` to match the
    #: original bash implementation.
    PRIVKEY_PATH: Path = Path("/root/server.key")

    #: Path to the public key.  It is placed in ``/root`` to match the
    #: original bash implementation.
    PUBKEY_PATH: Path = Path("/root/server.pub")

    #: Name of the screen session used when launching dns-server.  All
    #: start/stop/restart operations interact with this session.
    SCREEN_NAME: str = "slowdns"

    def __init__(self, non_interactive: bool = False) -> None:
        self.non_interactive = non_interactive

    # ------------------------------------------------------------------
    # Helper routines
    # ------------------------------------------------------------------
    def run_command(self, command: list[str], check: bool = False) -> subprocess.CompletedProcess:
        """Execute a system command.

        If the program is running as root and the called command is
        available, it will be executed.  Otherwise the command is
        printed to the terminal.  On success the completed process is
        returned; on failure a ``CalledProcessError`` may be raised.
        """
        try:
            # When not root we only print the command to avoid
            # accidental modifications to the host.
            if os.geteuid() != 0:
                print("[DRY‑RUN]", " ".join(command))
                return subprocess.CompletedProcess(command, returncode=0)
            return subprocess.run(command, check=check)
        except FileNotFoundError:
            print(f"[WARNING] Command not found: {command[0]}. Skipping execution.")
            return subprocess.CompletedProcess(command, returncode=1)

    def download_file(self, url: str, dest: Path) -> None:
        """Download a remote file and write it to ``dest``.

        A simple implementation using curl or wget via subprocess.  If
        either program is unavailable or the process fails, an
        informative error is printed.
        """
        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Prefer curl but fall back to wget
        if shutil.which("curl"):
            cmd = ["curl", "-L", "-o", str(dest), url]
        else:
            cmd = ["wget", "-O", str(dest), url]
        print(f"Downloading {url} -> {dest}")
        self.run_command(cmd)
        # Mark as executable when appropriate
        if dest.suffix in ("", ".sh"):
            try:
                dest.chmod(dest.stat().st_mode | 0o111)
            except FileNotFoundError:
                pass

    def apt_install(self, packages: list[str]) -> None:
        """Install packages using apt.

        This calls ``apt update && apt install -y <packages>`` as the
        bash scripts do.  When not run as root the command is printed.
        """
        if not packages:
            return
        update_cmd = ["apt", "update"]
        install_cmd = ["apt", "install", "-y"] + packages
        print("Updating package lists…")
        self.run_command(update_cmd)
        print(f"Installing packages: {', '.join(packages)}")
        self.run_command(install_cmd)

    def configure_firewall(self) -> None:
        """Open the required ports in firewalld.

        The original bash installer uses a one‑liner to add multiple
        ports to the public zone【294821352446467†L73-L79】.  Here we add
        them sequentially for clarity.  If firewalld is not present
        the commands will be skipped.
        """
        ports_tcp = [80, 8080, 443, 2222]
        ports_udp = [53, 5300]
        # Install firewalld if possible
        self.apt_install(["firewalld"])
        for port in ports_tcp:
            self.run_command(["firewall-cmd", "--zone=public", "--permanent", f"--add-port={port}/tcp"])
        for port in ports_udp:
            self.run_command(["firewall-cmd", "--zone=public", "--permanent", f"--add-port={port}/udp"])
        # Reload the firewall to apply changes
        self.run_command(["firewall-cmd", "--reload"])

    def set_cloudflare_dns(self) -> None:
        """Configure resolv.conf to point at Cloudflare (1.1.1.1).

        This matches the behaviour of the bash installer which backs
        up the current ``resolv.conf``, writes a new nameserver entry
        and then re‑enables systemd‑resolved【294821352446467†L84-L89】.
        """
        resolv = Path("/etc/resolv.conf")
        backup = Path("/etc/resolv.conf.bkp")
        if os.geteuid() != 0:
            print("[DRY‑RUN] Backing up and updating /etc/resolv.conf")
            return
        try:
            if resolv.exists() and not backup.exists():
                shutil.copy2(resolv, backup)
            with open(resolv, "w", encoding="utf-8") as fp:
                fp.write("nameserver 1.1.1.1\n")
            # Restart systemd‑resolved to apply changes
            self.run_command(["systemctl", "disable", "systemd-resolved.service"])
            self.run_command(["systemctl", "stop", "systemd-resolved.service"])
            self.run_command(["systemctl", "enable", "systemd-resolved.service"])
            self.run_command(["systemctl", "start", "systemd-resolved.service"])
        except PermissionError:
            print("[ERROR] Unable to write to /etc/resolv.conf. Are you root?")

    def restore_system_dns(self) -> None:
        """Restore resolv.conf to a sensible default when removing slowdns.

        The original remove script writes ``nameserver 8.8.8.8`` to
        ``/etc/resolv.conf`` and then re‑enables systemd‑resolved
        service【985502298734345†L42-L47】.
        """
        resolv = Path("/etc/resolv.conf")
        if os.geteuid() != 0:
            print("[DRY‑RUN] Restoring DNS resolver to 8.8.8.8")
            return
        with open(resolv, "w", encoding="utf-8") as fp:
            fp.write("nameserver 8.8.8.8\n")
        self.run_command(["systemctl", "enable", "systemd-resolved.service"])
        self.run_command(["systemctl", "start", "systemd-resolved.service"])

    def start_dns_server(self, nameserver: str, local_port: int) -> None:
        """Launch the dns-server binary in a detached screen session.

        This mirrors the ``startdns`` helper scripts which use
        ``screen -dmS slowdns dns-server -udp :5300 -privkey-file …``,
        substituting the appropriate local port for SSH/SSL/Dropbear/SOCKS【88752286916456†L28-L33】.
        """
        # Build the command exactly as the bash script does
        cmd = [
            "screen", "-dmS", self.SCREEN_NAME,
            str(self.SLOWDNS_DIR / "dns-server"),
            "-udp", ":5300",
            "-privkey-file", str(self.PRIVKEY_PATH),
            nameserver,
            f"127.0.0.1:{local_port}",
        ]
        self.run_command(cmd)
        print(f"Started dns-server with NS {nameserver} on port {local_port}")

    def stop_dns_server(self) -> None:
        """Terminate the running dns-server screen session if any.

        The original ``stopdns`` script greps for a screen named
        ``slowdns`` and sends a kill signal【51916410494299†L29-L33】.  Here we
        accomplish the same via ``screen -X quit``.
        """
        # Query running screen sessions
        result = subprocess.run(["screen", "-ls"], capture_output=True, text=True)
        if self.SCREEN_NAME in result.stdout:
            # Terminate the session
            self.run_command(["screen", "-S", self.SCREEN_NAME, "-X", "quit"])
            print("SlowDNS session stopped")
        else:
            print("No SlowDNS screen session found; nothing to stop")

    def restart_dns_server(self, nameserver: str, local_port: int) -> None:
        """Restart the dns-server process.

        This mirrors the behaviour of the ``restartdns`` scripts which
        kill the running session and then start a new one with the
        correct local port【460523677091378†L28-L36】.
        """
        self.stop_dns_server()
        time.sleep(2)
        self.start_dns_server(nameserver, local_port)

    # ------------------------------------------------------------------
    # Installation routines
    # ------------------------------------------------------------------
    def install_manager(self) -> None:
        """Install the core SlowDNS manager.

        This replicates the behaviour of the ``install`` bash script.  It
        installs dependencies, creates the ``/etc/slowdns`` directory,
        downloads helper scripts and the dns-server binary, sets
        permissions, opens firewall ports and configures DNS
        forwarding【294821352446467†L46-L65】【294821352446467†L73-L79】【294821352446467†L84-L89】.
        """
        print("=== Installing SlowDNS Manager ===")
        # Basic dependencies used across all variants
        self.apt_install(["ncurses-utils", "screen", "cron", "iptables"])
        # Create working directory
        if os.geteuid() == 0:
            self.SLOWDNS_DIR.mkdir(parents=True, exist_ok=True)
        else:
            print(f"[DRY‑RUN] Would create directory {self.SLOWDNS_DIR}")
        # Download core binary and management scripts
        files_to_download = [
            ("dns-server", self.SLOWDNS_DIR / "dns-server"),
            ("remove-slow", self.SLOWDNS_DIR / "remove-slow"),
            ("slowdns-info", self.SLOWDNS_DIR / "slowdns-info"),
            ("slowdns-drop", self.SLOWDNS_DIR / "slowdns-drop"),
            ("slowdns-ssh", self.SLOWDNS_DIR / "slowdns-ssh"),
            ("slowdns-ssl", self.SLOWDNS_DIR / "slowdns-ssl"),
            ("slowdns-socks", self.SLOWDNS_DIR / "slowdns-socks"),
            # menu script (not needed by Python version but kept for
            # completeness)
            ("slowdns", self.SLOWDNS_DIR / "slowdns"),
            ("stopdns", self.SLOWDNS_DIR / "stopdns"),
        ]
        for filename, destination in files_to_download:
            url = f"{self.BASE_URL}/{filename}"
            self.download_file(url, destination)
        # Configure firewall
        self.configure_firewall()
        # Set Cloudflare DNS
        self.set_cloudflare_dns()
        print("Installation completed. Use the Python menu to proceed.")

    def _install_variant(self, variant: str, local_port: int) -> None:
        """Generic installer for a SlowDNS service flavour.

        Parameters
        ----------
        variant:
            One of ``'ssh'``, ``'ssl'``, ``'drop'`` or ``'socks'``.  It
            corresponds to the subdirectory in the upstream repository
            where the variant‑specific ``startdns`` and ``restartdns``
            scripts reside【508339094020233†L72-L90】.
        local_port:
            The TCP port on localhost to which the dns-server will
            forward connections (22 for SSH, 443 for SSL, 8080 for
            Dropbear, 80 for SOCKS)【88752286916456†L28-L33】.
        """
        print(f"=== Installing SlowDNS {variant.upper()} ===")
        # Update and install required packages
        self.apt_install(["screen", "cron", "iptables"])
        # Download the start and restart scripts for the variant
        start_script = self.SLOWDNS_DIR / "startdns"
        restart_script = self.SLOWDNS_DIR / "restartdns"
        if variant:
            self.download_file(f"{self.BASE_URL}/{variant}/startdns", start_script)
            self.download_file(f"{self.BASE_URL}/{variant}/restartdns", restart_script)
        # Ask for nameserver (NS) input
        if self.non_interactive:
            nameserver = "1.1.1.1"
        else:
            nameserver = input("Enter your NS (nameserver): ").strip()
        # Persist NS to infons file
        if os.geteuid() == 0:
            infons = self.SLOWDNS_DIR / "infons"
            with open(infons, "w", encoding="utf-8") as fp:
                fp.write(nameserver + "\n")
        else:
            print(f"[DRY‑RUN] Would write nameserver {nameserver} to {self.SLOWDNS_DIR}/infons")
        # Replace placeholder in the downloaded scripts so they refer to the chosen NS
        for script_path in (start_script, restart_script):
            try:
                content = script_path.read_text(encoding="utf-8")
                content = content.replace("1234", nameserver)
                script_path.write_text(content, encoding="utf-8")
                script_path.chmod(script_path.stat().st_mode | 0o111)
            except FileNotFoundError:
                pass
        # Install or generate keys
        self._ensure_keys()
        # Set up iptables rules and start the service
        self.run_command(["iptables", "-I", "INPUT", "-p", "udp", "--dport", "5300", "-j", "ACCEPT"])
        self.run_command(["iptables", "-t", "nat", "-I", "PREROUTING", "-p", "udp", "--dport", "53", "-j", "REDIRECT", "--to-ports", "5300"])
        # Launch dns-server
        self.start_dns_server(nameserver, local_port)
        print("Installation complete. Your NS and public key are shown below:")
        self.show_info()

    def _ensure_keys(self) -> None:
        """Ensure that key pairs exist for dns-server.

        If both ``server.key`` and ``server.pub`` exist in the root
        directory, the user may choose to reuse them, regenerate them
        or download a default pair【508339094020233†L100-L120】.  If they
        do not exist, the user may generate a new pair or download
        defaults.  When running in non‑interactive mode the defaults
        are used.
        """
        key_exists = self.PRIVKEY_PATH.exists() and self.PUBKEY_PATH.exists()
        if self.non_interactive:
            choice = "1" if key_exists else "2"
        else:
            if key_exists:
                print("A key pair already exists.")
                print("[1] Use existing key\n[2] Generate a new key\n[3] Download default key\n[x] Abort installation")
                choice = input("Select an option: ").strip()
            else:
                print("No key pair found.")
                print("[1] Generate a new key\n[2] Download default key\n[x] Abort installation")
                choice = input("Select an option: ").strip()
        if choice.lower() == "x":
            print("Installation aborted.")
            sys.exit(1)
        # Map interactive options to actions
        if key_exists and choice == "1":
            print("Using existing key pair…")
            return
        if (key_exists and choice == "2") or (not key_exists and choice == "1"):
            # Generate new keys using dns-server binary
            print("Generating a new key pair…")
            self.run_command([
                str(self.SLOWDNS_DIR / "dns-server"),
                "-gen-key",
                "-privkey-file", str(self.PRIVKEY_PATH),
                "-pubkey-file", str(self.PUBKEY_PATH),
            ])
        else:
            # Download default keys from upstream
            print("Downloading default key pair…")
            self.download_file(f"{self.BASE_URL}/server.key", self.PRIVKEY_PATH)
            self.download_file(f"{self.BASE_URL}/server.pub", self.PUBKEY_PATH)

    # ------------------------------------------------------------------
    # High‑level user commands
    # ------------------------------------------------------------------
    def install_ssh(self) -> None:
        """Install SlowDNS for SSH tunnelling (local port 22)."""
        self._install_variant("ssh", 22)

    def install_ssl(self) -> None:
        """Install SlowDNS for SSL tunnelling (local port 443)."""
        self._install_variant("ssl", 443)

    def install_dropbear(self) -> None:
        """Install SlowDNS for Dropbear tunnelling (local port 8080)."""
        self._install_variant("drop", 8080)

    def install_socks(self) -> None:
        """Install SlowDNS for SOCKS tunnelling (local port 80)."""
        self._install_variant("socks", 80)

    def show_info(self) -> None:
        """Display NS and public key information to the user.

        This replicates the ``slowdns-info`` script which prints the
        nameserver, public key and a Termux command【170030086320778†L1-L13】.
        """
        try:
            ns = (self.SLOWDNS_DIR / "infons").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            ns = "<unknown>"
        try:
            key = self.PUBKEY_PATH.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            key = "<no key>"
        print(f"\nNameserver: {ns}")
        print(f"Public key: {key}\n")
        print("Termux command:")
        print(f"curl -sO https://github.com/khaledagn/DNS-AGN/raw/main/files/slowdns && chmod +x slowdns && ./slowdns {ns} {key}")
        print("")

    def remove(self) -> None:
        """Remove the SlowDNS installation.

        This follows the logic of the ``remove-slow`` script: stop the
        service, restore the original rc.local if present, reset
        resolv.conf and delete the working directory【985502298734345†L27-L50】.
        """
        print("=== Removing SlowDNS ===")
        # Stop the running server
        self.stop_dns_server()
        # Restore rc.local backup if present
        rc_local = Path("/etc/rc.local")
        rc_backup = Path("/etc/rc.local.bkp")
        if os.geteuid() == 0 and rc_backup.exists():
            try:
                shutil.move(rc_backup, rc_local)
                print("Restored rc.local from backup")
            except Exception as exc:
                print(f"[WARNING] Could not restore rc.local: {exc}")
        # Restore system DNS
        self.restore_system_dns()
        # Remove working directory
        if os.geteuid() == 0 and self.SLOWDNS_DIR.exists():
            shutil.rmtree(self.SLOWDNS_DIR, ignore_errors=True)
            print("Removed /etc/slowdns directory")
        else:
            print(f"[DRY‑RUN] Would remove directory {self.SLOWDNS_DIR}")
        print("SlowDNS removed successfully.")

    def update(self) -> None:
        """Update the SlowDNS installation.

        In the bash implementation, update removes all files and then
        re-runs the installer【312924233180552†L34-L54】.  Here we call
        ``remove`` followed by ``install_manager``.
        """
        print("=== Updating SlowDNS ===")
        print("This will remove the current installation and reinstall.")
        if not self.non_interactive:
            input("Press [ENTER] to continue or Ctrl+C to cancel…")
        self.remove()
        self.install_manager()

    # ------------------------------------------------------------------
    # Interactive menu
    # ------------------------------------------------------------------
    def menu(self) -> None:
        """Display the interactive menu and dispatch user selections.

        This function emulates the original bash ``slowdns`` menu
        script【330467474699245†L0-L39】.  It loops until the user
        chooses to exit.  Each option calls the corresponding method
        defined above.
        """
        while True:
            print("\n" + "═" * 60)
            print("{:^60}".format("SLOWDNS PYTHON MANAGER"))
            print("═" * 60)
            print("[1] Install SlowDNS SSH (port 22)")
            print("[2] Install SlowDNS SSL (port 443)")
            print("[3] Install SlowDNS Dropbear (port 8080)")
            print("[4] Install SlowDNS SOCKS (port 80)")
            print("[5] Show information")
            print("[6] Start SlowDNS")
            print("[7] Restart SlowDNS")
            print("[8] Stop SlowDNS")
            print("[9] Remove SlowDNS")
            print("[10] Update/Reinstall")
            print("[0] Exit")
            choice = input("Select an option: ").strip()
            if choice == "1":
                self.install_ssh()
            elif choice == "2":
                self.install_ssl()
            elif choice == "3":
                self.install_dropbear()
            elif choice == "4":
                self.install_socks()
            elif choice == "5":
                self.show_info()
            elif choice == "6":
                # Start using previously saved NS and port.  Try to infer
                # port from installed variant by reading startdns script.
                ns = (self.SLOWDNS_DIR / "infons").read_text().strip() if (self.SLOWDNS_DIR / "infons").exists() else ""
                port = self._infer_port() or 22
                self.start_dns_server(ns, port)
            elif choice == "7":
                ns = (self.SLOWDNS_DIR / "infons").read_text().strip() if (self.SLOWDNS_DIR / "infons").exists() else ""
                port = self._infer_port() or 22
                self.restart_dns_server(ns, port)
            elif choice == "8":
                self.stop_dns_server()
            elif choice == "9":
                self.remove()
            elif choice == "10":
                self.update()
            elif choice == "0":
                print("Exiting.")
                break
            else:
                print("Invalid option. Please try again.")

    def _infer_port(self) -> Optional[int]:
        """Attempt to infer the local port from the installed startdns script.

        The upstream ``startdns`` scripts embed the local forwarding
        port inside a call to dns-server, e.g. ``127.0.0.1:22`` for
        SSH【88752286916456†L28-L33】.  If that script exists we parse the
        last component of the command line to determine which port
        should be used when starting or restarting the server.
        """
        start_script = self.SLOWDNS_DIR / "startdns"
        if not start_script.exists():
            return None
        try:
            with open(start_script, "r", encoding="utf-8") as fp:
                for line in fp:
                    if "dns-server" in line and "127.0.0.1:" in line:
                        segment = line.strip().split()
                        # Find the parameter that contains "127.0.0.1:"
                        for token in segment:
                            if token.startswith("127.0.0.1:"):
                                return int(token.split(":")[1])
        except Exception:
            return None
        return None


def main() -> None:
    manager = DNSAGNManager()
    # If invoked with arguments, dispatch directly
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "install":
            manager.install_manager()
        elif cmd == "ssh":
            manager.install_ssh()
        elif cmd == "ssl":
            manager.install_ssl()
        elif cmd == "drop" or cmd == "dropbear":
            manager.install_dropbear()
        elif cmd == "socks":
            manager.install_socks()
        elif cmd == "start":
            ns = (DNSAGNManager.SLOWDNS_DIR / "infons").read_text().strip() if (DNSAGNManager.SLOWDNS_DIR / "infons").exists() else ""
            port = manager._infer_port() or 22
            manager.start_dns_server(ns, port)
        elif cmd == "stop":
            manager.stop_dns_server()
        elif cmd == "restart":
            ns = (DNSAGNManager.SLOWDNS_DIR / "infons").read_text().strip() if (DNSAGNManager.SLOWDNS_DIR / "infons").exists() else ""
            port = manager._infer_port() or 22
            manager.restart_dns_server(ns, port)
        elif cmd == "info":
            manager.show_info()
        elif cmd == "remove":
            manager.remove()
        elif cmd == "update":
            manager.update()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: dns_agn_python.py [install|ssh|ssl|drop|socks|start|stop|restart|info|remove|update]")
    else:
        manager.menu()


if __name__ == "__main__":
    main()