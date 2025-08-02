#!/usr/bin/env python3
import subprocess
import re
import sys
import os

def get_total_ram_bytes():
    """
    Read total physical RAM from /proc/meminfo and return in bytes.
    """
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                # MemTotal is in kB, convert to bytes
                kb = int(re.search(r'\d+', line).group())
                return kb * 1024
    raise ValueError("Could not find MemTotal in /proc/meminfo")

def setup_zram(percentage=0.3, algorithm='zstd', priority=100, num_devices=None):
    """
    Set up zram swap device(s) using the specified percentage of total RAM.
    
    Parameters:
    - percentage: Fraction of total RAM to allocate for zram (default 0.3 for 30%).
    - algorithm: Compression algorithm ('zstd' for better ratio, 'lz4' for speed).
    - priority: Swap priority (higher than disk swap, e.g., 100).
    - num_devices: Number of zram devices (defaults to number of CPU cores for parallelism).
    """
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)
    
    if num_devices is None:
        num_devices = os.cpu_count() or 1  # Fallback to 1 if cpu_count() returns None
    
    total_ram = get_total_ram_bytes()
    total_zram_size = int(total_ram * percentage)
    size_per_device = total_zram_size // num_devices
    
    # Load zram module with specified number of devices
    subprocess.run(['modprobe', 'zram', f'num_devices={num_devices}'], check=True)
    
    for dev_id in range(num_devices):
        dev = f'/dev/zram{dev_id}'
        sys_path = f'/sys/block/zram{dev_id}'
        
        # Set compression algorithm
        with open(f'{sys_path}/comp_algorithm', 'w') as f:
            f.write(algorithm)
        
        # Set disksize
        with open(f'{sys_path}/disksize', 'w') as f:
            f.write(str(size_per_device))
        
        # Format as swap
        subprocess.run(['mkswap', dev], check=True)
        
        # Activate swap with priority
        subprocess.run(['swapon', '-p', str(priority), dev], check=True)
    
    print(f"zram setup complete: {num_devices} device(s) totaling ~{total_zram_size / (1024**3):.2f} GB ({percentage*100}% of RAM).")
    print("For optimal long-term use, consider setting vm.swappiness=100 in /etc/sysctl.conf for aggressive zram usage.")

def teardown_zram():
    """
    Tear down all zram swap devices.
    """
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)
    
    # Get active zram swaps
    swaps = subprocess.check_output(['swapon', '--show=NAME,TYPE'], text=True).splitlines()
    for line in swaps[1:]:  # Skip header
        name = line.split()[0]
        if 'zram' in name:
            subprocess.run(['swapoff', name], check=True)
    
    # Reset and remove module
    subprocess.run(['modprobe', '-r', 'zram'], check=True)
    print("zram teardown complete.")

def install_systemd_service(script_path):
    """
    Install a systemd service for automatic zram setup on boot.
    
    Parameters:
    - script_path: Absolute path to this script.
    """
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)
    
    service_content = f"""
[Unit]
Description=Configura zram automaticamente
After=multi-user.target

[Service]
Type=oneshot
ExecStart={script_path} setup
ExecStop={script_path} teardown
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
"""
    service_path = '/etc/systemd/system/zram.service'
    with open(service_path, 'w') as f:
        f.write(service_content.strip())
    
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'zram.service'], check=True)
    print(f"Systemd service installed at {service_path}. zram will now activate automatically on boot.")

def uninstall_systemd_service():
    """
    Uninstall the systemd service for zram.
    """
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)
    
    service_path = '/etc/systemd/system/zram.service'
    if os.path.exists(service_path):
        subprocess.run(['systemctl', 'disable', 'zram.service'], check=True)
        os.remove(service_path)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        print("Systemd service uninstalled.")
    else:
        print("No systemd service found to uninstall.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Automate zram setup for 30% of RAM as compressed swap.")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    setup_parser = subparsers.add_parser('setup', help='Set up zram')
    setup_parser.add_argument('--percentage', type=float, default=0.3, help='Percentage of RAM (0.3 = 30%)')
    setup_parser.add_argument('--algorithm', default='zstd', choices=['zstd', 'lz4', 'lzo'], help='Compression algorithm')
    setup_parser.add_argument('--priority', type=int, default=100, help='Swap priority')
    setup_parser.add_argument('--num_devices', type=int, default=None, help='Number of zram devices (defaults to CPU cores)')
    
    teardown_parser = subparsers.add_parser('teardown', help='Tear down zram')
    
    install_parser = subparsers.add_parser('install', help='Install systemd service for boot automation')
    install_parser.add_argument('script_path', type=str, help='Absolute path to this script (e.g., /path/to/zram_manager.py)')
    
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall systemd service')
    
    args = parser.parse_args()
    
    if args.command == 'setup':
        setup_zram(args.percentage, args.algorithm, args.priority, args.num_devices)
    elif args.command == 'teardown':
        teardown_zram()
    elif args.command == 'install':
        install_systemd_service(args.script_path)
    elif args.command == 'uninstall':
        uninstall_systemd_service()
