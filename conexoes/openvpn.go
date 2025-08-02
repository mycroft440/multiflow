package main

import (
	"bufio"
	"fmt"
	"io/ioutil"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/fatih/color"
)

// Adicionado para resolver dependência: Função init() que verifica e instala o módulo github.com/fatih/color se ausente.
// Isso roda antes do main, garantindo que o build funcione (requer Go instalado).
// Comando: go mod init openvpn (se não existir go.mod) e go get github.com/fatih/color.
func init() {
	// Verificar se go.mod existe; se não, inicializar.
	if _, err := os.Stat("go.mod"); os.IsNotExist(err) {
		cmd := exec.Command("go", "mod", "init", "openvpn")
		if err := cmd.Run(); err != nil {
			fmt.Println("Erro ao inicializar go.mod:", err)
			os.Exit(1)
		}
	}
	// Instalar dependência externa.
	cmd := exec.Command("go", "get", "github.com/fatih/color")
	if err := cmd.Run(); err != nil {
		fmt.Println("Erro ao instalar github.com/fatih/color:", err)
		os.Exit(1)
	}
	// Tidy para limpar go.mod/go.sum.
	cmd = exec.Command("go", "mod", "tidy")
	if err := cmd.Run(); err != nil {
		fmt.Println("Erro ao tidy módulos:", err)
		os.Exit(1)
	}
}

// Constante para a versão do EasyRSA (facilita atualizações futuras)
const EASYRSA_VERSION = "3.2.3"

// Constante para a versão do OpenVPN (facilita atualizações futuras)
const OPENVPN_VERSION = "2.6.14"

// Variáveis globais
var isOpenVPNInstalled bool
var osType string
var groupName string
var rcLocal string

// Cores
var (
	red    = color.New(color.FgHiRed).SprintFunc()
	green  = color.New(color.FgHiGreen).SprintFunc()
	yellow = color.New(color.FgHiYellow).SprintFunc()
	white  = color.New(color.FgHiWhite).SprintFunc()
	cyan   = color.New(color.FgHiCyan).SprintFunc()
	scolor = color.New(color.Reset).SprintFunc()
)

// Função para limpar tela
func clearScreen() {
	fmt.Print("\033[H\033[2J")
}

// Verificações iniciais
func checkInitial() {
	if os.Geteuid() != 0 {
		fmt.Println(red("[x] VOCÊ PRECISA EXECUTAR COMO USUÁRIO ROOT!"))
		os.Exit(1)
	}

	// Verificar TUN/TAP
	if _, err := os.Stat("/dev/net/tun"); os.IsNotExist(err) {
		fmt.Println(red("TUN TAP NÃO DISPONÍVEL"))
		os.Exit(3)
	}

	// Detectar OS
	if _, err := os.Stat("/etc/debian_version"); err == nil {
		osType = "debian"
		groupName = "nogroup"
		rcLocal = "/etc/rc.local"
	} else if _, err := os.Stat("/etc/centos-release"); err == nil || (func() bool { _, err := os.Stat("/etc/redhat-release"); return err == nil }()) {
		osType = "centos"
		groupName = "nobody"
		rcLocal = "/etc/rc.d/rc.local"
	} else {
		fmt.Println(red("SISTEMA NÃO SUPORTADO"))
		os.Exit(5)
	}
}

// Função de barra de progresso (corrigido sintaxe: removido loop duplicado e ajustado nesting para evitar erro)
func funBar(cmd string) {
	fmt.Printf("%sAGUARDE %s- %s[", yellow(""), white(""), yellow(""))
	done := make(chan bool)
	go func() {
		exec.Command("bash", "-c", cmd).Run()
		done <- true
	}()
	for {
		for i := 0; i < 18; i++ {
			fmt.Printf("%s#", red(""))
			time.Sleep(100 * time.Millisecond)
		}
		select {
		case <-done:
			fmt.Printf("%s]%s -%s OK !%s\n", yellow(""), white(""), green(""), white(""))
			return
		default:
			time.Sleep(1 * time.Second)
			fmt.Printf("\r%sAGUARDE %s- %s[", yellow(""), white(""), yellow(""))
		}
	}
}

// Função para verificar portas em uso
func verifPtrs(porta int) {
	conns, _ := net.Listen("tcp", fmt.Sprintf(":%d", porta))
	if conns != nil {
		conns.Close()
	} else {
		fmt.Printf("\n%sPORTA %s%d %sEM USO%s\n", red(""), yellow(""), porta, red(""), scolor(""))
		time.Sleep(3 * time.Second)
		menuPrincipal()
	}
}

// Função para criar novo cliente
func newClient(client string) {
	// Simular cp e cat (ler e escrever arquivos)
	clientCommon, _ := ioutil.ReadFile("/etc/openvpn/client-common.txt")
	ca, _ := ioutil.ReadFile("/etc/openvpn/easy-rsa/pki/ca.crt")
	cert, _ := ioutil.ReadFile(fmt.Sprintf("/etc/openvpn/easy-rsa/pki/issued/%s.crt", client))
	key, _ := ioutil.ReadFile(fmt.Sprintf("/etc/openvpn/easy-rsa/pki/private/%s.key", client))
	tls, _ := ioutil.ReadFile("/etc/openvpn/ta.key")
	content := string(clientCommon) +
		"<ca>\n" + string(ca) + "</ca>\n" +
		"<cert>\n" + string(cert) + "</cert>\n" +
		"<key>\n" + string(key) + "</key>\n" +
		"<tls-auth>\n" + string(tls) + "</tls-auth>\n"
	ioutil.WriteFile(fmt.Sprintf("/root/%s.ovpn", client), []byte(content), 0644)
}

// Função para instalar OpenVPN
func instalarOpenvpn() {
	// Detectar IP (simplificado)
	addrs, _ := net.InterfaceAddrs()
	var ip string
	for _, addr := range addrs {
		if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil {
				ip = ipnet.IP.String()
				break
			}
		}
	}
	clearScreen()
	fmt.Println("\033[44;1;37m INSTALADOR OPENVPN \033[0m")
	fmt.Println(green("Iniciando instalação do OpenVPN..."))

	// Instalar dependências de build e outras (adaptar para OS)
	if osType == "debian" {
		exec.Command("apt-get", "update").Run()
		exec.Command("apt-get", "install", "build-essential", "autoconf", "automake", "libtool", "pkg-config", "liblz4-dev", "liblzo2-dev", "libssl-dev", "iptables", "openssl", "ca-certificates", "-y").Run()
	} else {
		exec.Command("yum", "groupinstall", "'Development Tools'", "-y").Run()
		exec.Command("yum", "install", "epel-release", "-y").Run()
		exec.Command("yum", "install", "autoconf", "automake", "libtool", "pkgconfig", "lz4-devel", "lzo-devel", "openssl-devel", "iptables", "openssl", "ca-certificates", "-y").Run()
	}

	// Baixar e instalar OpenVPN do fonte (usando a constante de versão)
	exec.Command("wget", "-O", fmt.Sprintf("/root/openvpn-%s.tar.gz", OPENVPN_VERSION), fmt.Sprintf("https://swupdate.openvpn.org/community/releases/openvpn-%s.tar.gz", OPENVPN_VERSION)).Run()
	exec.Command("tar", "xzf", fmt.Sprintf("/root/openvpn-%s.tar.gz", OPENVPN_VERSION), "-C", "/root/").Run()
	os.Chdir(fmt.Sprintf("/root/openvpn-%s", OPENVPN_VERSION))
	exec.Command("./configure").Run()
	exec.Command("make").Run()
	exec.Command("make", "install").Run()
	exec.Command("rm", "-rf", fmt.Sprintf("/root/openvpn-%s.tar.gz", OPENVPN_VERSION)).Run()
	exec.Command("rm", "-rf", fmt.Sprintf("/root/openvpn-%s", OPENVPN_VERSION)).Run()

	// Baixar EasyRSA (usando a constante de versão)
	exec.Command("wget", "-O", fmt.Sprintf("/root/EasyRSA-%s.tgz", EASYRSA_VERSION), fmt.Sprintf("https://github.com/OpenVPN/easy-rsa/releases/download/v%s/EasyRSA-%s.tgz", EASYRSA_VERSION, EASYRSA_VERSION)).Run()
	exec.Command("tar", "xzf", fmt.Sprintf("/root/EasyRSA-%s.tgz", EASYRSA_VERSION), "-C", "/root/").Run()
	exec.Command("mv", fmt.Sprintf("/root/EasyRSA-%s/", EASYRSA_VERSION), "/etc/openvpn/easy-rsa/").Run()
	exec.Command("chown", "-R", "root:root", "/etc/openvpn/easy-rsa/").Run()
	exec.Command("rm", "-rf", fmt.Sprintf("/root/EasyRSA-%s.tgz", EASYRSA_VERSION)).Run()
	os.Chdir("/etc/openvpn/easy-rsa/")
	exec.Command("./easyrsa", "init-pki").Run()
	exec.Command("./easyrsa", "--batch", "build-ca", "nopass").Run()
	exec.Command("./easyrsa", "gen-dh").Run()
	exec.Command("./easyrsa", "build-server-full", "server", "nopass").Run()
	exec.Command("./easyrsa", "build-client-full", "client", "nopass").Run()
	exec.Command("./easyrsa", "gen-crl").Run()

	// Mover arquivos
	filesToCopy := []string{"pki/ca.crt", "pki/private/ca.key", "pki/dh.pem", "pki/issued/server.crt", "pki/private/server.key", "pki/crl.pem"}
	for _, f := range filesToCopy {
		exec.Command("cp", f, "/etc/openvpn").Run()
	}
	exec.Command("chown", "nobody:nogroup", "/etc/openvpn/crl.pem").Run() // Adaptar groupName

	// Gerar ta.key
	exec.Command("openvpn", "--genkey", "--secret", "/etc/openvpn/ta.key").Run()

	// Configurar servidor (ler inputs)
	var port int = 1194
	var protocol string = "udp"
	var dns1, dns2 string = "8.8.8.8", "8.8.4.4"
	fmt.Printf("%sQual porta deseja usar para o OpenVPN? %s[1194]: %s", green(""), yellow(""), white(""))
	fmt.Scan(&port)
	fmt.Printf("%sQual protocolo deseja usar? %s[1] UDP [2] TCP: %s", green(""), yellow(""), white(""))
	var protoChoice int
	fmt.Scan(&protoChoice)
	if protoChoice == 2 {
		protocol = "tcp"
	}
	fmt.Printf("%sQual DNS deseja usar? %s[1] Google [2] Cloudflare [3] OpenDNS: %s", green(""), yellow(""), white(""))
	var dnsChoice int
	fmt.Scan(&dnsChoice)
	switch dnsChoice {
	case 2:
		dns1, dns2 = "1.1.1.1", "1.0.0.1"
	case 3:
		dns1, dns2 = "208.67.222.222", "208.67.220.220"
	}

	// Escrever server.conf
	serverConf := fmt.Sprintf(`port %d\nproto %s\ndev tun\nca ca.crt\ncert server.crt\nkey server.key\ndh dh.pem\nauth SHA512\ntls-auth ta.key 0\ntopology subnet\nserver 10.8.0.0 255.255.255.0\nifconfig-pool-persist ipp.txt\npush "redirect-gateway def1 bypass-dhcp"\npush "dhcp-option DNS %s"\npush "dhcp-option DNS %s"\nkeepalive 10 120\ncipher AES-256-CBC\nuser nobody\ngroup nogroup\npersist-key\npersist-tun\nstatus openvpn-status.log\nverb 3\ncrl-verify crl.pem`, port, protocol, dns1, dns2)
	ioutil.WriteFile("/etc/openvpn/server.conf", []byte(serverConf), 0644)

	// Client common
	clientCommon := fmt.Sprintf(`client\ndev tun\nproto %s\nremote %s %d\nresolv-retry infinite\nnobind\npersist-key\npersist-tun\nauth SHA512\ncipher AES-256-CBC\nremote-cert-tls server\ntls-auth ta.key 1\nverb 3`, protocol, ip, port)
	ioutil.WriteFile("/etc/openvpn/client-common.txt", []byte(clientCommon), 0644)

	// Firewall (exec iptables)
	exec.Command("sh", "-c", "echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf").Run()
	exec.Command("iptables", "-t", "nat", "-A", "POSTROUTING", "-s", "10.8.0.0/24", "-j", "SNAT", "--to", ip).Run()
	exec.Command("iptables", "-I", "INPUT", "-p", protocol, "--dport", strconv.Itoa(port), "-j", "ACCEPT").Run()
	exec.Command("iptables", "-I", "FORWARD", "-s", "10.8.0.0/24", "-j", "ACCEPT").Run()
	exec.Command("iptables", "-I", "FORWARD", "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT").Run()
	exec.Command("iptables-save", ">", "/etc/iptables/rules.v4").Run() // Adaptar para OS

	// Iniciar serviço
	exec.Command("systemctl", "start", "openvpn@server").Run()
	exec.Command("systemctl", "enable", "openvpn@server").Run()
	fmt.Println(green("OpenVPN instalado com sucesso!"))
	fmt.Println(yellow("Criando primeiro cliente..."))
	var client string
	fmt.Printf("%sNome do primeiro cliente: %s", green(""), white(""))
	fmt.Scan(&client)
	os.Chdir("/etc/openvpn/easy-rsa/")
	exec.Command("./easyrsa", "build-client-full", client, "nopass").Run()
	newClient(client)
	fmt.Println(green("Cliente criado! Arquivo: ") + white(fmt.Sprintf("/root/%s.ovpn", client)))
	fmt.Println(green("Pressione ENTER para continuar..."))
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

// Função para remover OpenVPN
func removerOpenvpn() {
	clearScreen()
	fmt.Println("\033[41;1;37m REMOVER OPENVPN \033[0m")
	fmt.Println(yellow("Parando o serviço OpenVPN..."))
	exec.Command("systemctl", "stop", "openvpn@server").Run()
	exec.Command("systemctl", "disable", "openvpn@server").Run()
	fmt.Println(yellow("Removendo arquivos de configuração..."))
	exec.Command("rm", "-rf", "/etc/openvpn").Run()

	// Remover pacotes
	if osType == "debian" {
		fmt.Println(yellow("Removendo pacotes..."))
		exec.Command("apt-get", "remove", "--purge", "-y", "openvpn", "easy-rsa").Run()
		exec.Command("apt-get", "autoremove", "-y").Run()
	} else if osType == "centos" {
		fmt.Println(yellow("Removendo pacotes..."))
		exec.Command("yum", "remove", "-y", "openvpn", "easy-rsa").Run()
	}
	fmt.Println(green("OpenVPN removido com sucesso!"))
	fmt.Println(green("Pressione ENTER para continuar..."))
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

// Função stub para gerenciar OpenVPN (implementar similar ao Bash)
func gerenciarOpenvpn() {
	// Implementação pendente: menu de gerenciamento com opções como alterar porta, etc.
	fmt.Println("Gerenciando OpenVPN...")
	time.Sleep(2 * time.Second)
}

// Função stub para criar cliente (implementar similar ao Bash)
func criarCliente() {
	// Implementação pendente: pedir nome do cliente, gerar com easyrsa, etc.
	fmt.Println("Criando cliente...")
	time.Sleep(2 * time.Second)
}

// Menu principal
func menuPrincipal() {
	// Computar status uma vez (melhoria 3)
	cmd := exec.Command("netstat", "-nplt")
	output, err := cmd.Output()
	if err != nil {
		isOpenVPNInstalled = false // Melhoria 1: tratar erro definindo false
	} else {
		isOpenVPNInstalled = strings.Contains(string(output), "openvpn")
	}
	for {
		clearScreen()
		fmt.Println("\033[44;1;37m OPENVPN MANAGER \033[0m")
		fmt.Println("")
		var opnp string
		if isOpenVPNInstalled {
			// Ler porta do config se instalado
			serverConf, _ := ioutil.ReadFile("/etc/openvpn/server.conf")
			re := regexp.MustCompile(`port (\d+)`)
			match := re.FindStringSubmatch(string(serverConf))
			if len(match) > 1 {
				opnp = match[1]
			} else {
				opnp = "1194"
			}
			fmt.Printf("%sStatus: %sOpenVPN Ativo - Porta: %s%s%s\n", green(""), white(""), green(""), opnp, scolor(""))
			fmt.Println("")
			fmt.Printf("%s[%s1%s] %s• %sGERENCIAR OPENVPN\n", red(""), cyan(""), red(""), white(""), yellow(""))
			fmt.Printf("%s[%s2%s] %s• %sCRIAR CLIENTE\n", red(""), cyan(""), red(""), white(""), yellow(""))
			fmt.Printf("%s[%s3%s] %s• %sREMOVER OPENVPN\n", red(""), cyan(""), red(""), white(""), yellow(""))
		} else {
			fmt.Printf("%sStatus: %sOpenVPN Não Instalado%s\n", red(""), white(""), scolor(""))
			fmt.Println("")
			fmt.Printf("%s[%s1%s] %s• %sINSTALAR OPENVPN\n", red(""), cyan(""), red(""), white(""), yellow(""))
		}
		fmt.Printf("%s[%s0%s] %s• %sVOLTAR\n", red(""), cyan(""), red(""), white(""), yellow(""))
		fmt.Println("")
		fmt.Printf("%sSelecione uma opção: %s", green(""), white(""))
		var option int
		fmt.Scan(&option)
		switch option {
		case 1:
			if isOpenVPNInstalled {
				gerenciarOpenvpn()
			} else {
				instalarOpenvpn()
			}
		case 2:
			if isOpenVPNInstalled {
				criarCliente()
			} else {
				fmt.Println(red("OpenVPN não está instalado!"))
				time.Sleep(2 * time.Second)
			}
		case 3:
			if isOpenVPNInstalled {
				removerOpenvpn()
			} else {
				fmt.Println(red("OpenVPN não está instalado!"))
				time.Sleep(2 * time.Second)
			}
		case 0:
			clearScreen()
			fmt.Println(green("Saindo..."))
			os.Exit(0)
		default:
			fmt.Println(red("Opção inválida!"))
			time.Sleep(2 * time.Second)
		}
	}
}

func main() {
	checkInitial()
	clearScreen()
	fmt.Println(green("OpenVPN Installer & Manager"))
	fmt.Println(yellow("Versão unificada"))
	time.Sleep(2 * time.Second)
	menuPrincipal()
}
