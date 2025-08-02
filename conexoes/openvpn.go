package main

import (
	"bufio"
	"fmt"
	"io/ioutil"
	"net"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"time"

	"github.com/fatih/color"
)

// Constantes para versões (facilitam atualizações)
const EASYRSA_VERSION = "3.1.0" // Versão estável
const OPENVPN_VERSION = "2.5.4" // Versão estável

// Variáveis globais
var (
	isOpenVPNInstalled bool
	osType             string
	groupName          string
	rcLocal            string
	red                = color.New(color.FgHiRed).SprintFunc()
	green              = color.New(color.FgHiGreen).SprintFunc()
	yellow             = color.New(color.FgHiYellow).SprintFunc()
	white              = color.New(color.FgHiWhite).SprintFunc()
	cyan               = color.New(color.FgHiCyan).SprintFunc()
	scolor             = color.New(color.Reset).SprintFunc()
)

// Limpa o ecrã do terminal
func clearScreen() {
	cmd := exec.Command("clear")
	cmd.Stdout = os.Stdout
	cmd.Run()
}

// Verifica se o script está a ser executado como root e se o TUN/TAP está disponível
func checkInitial() {
	if os.Geteuid() != 0 {
		fmt.Println(red("[x] ESTE SCRIPT PRECISA SER EXECUTADO COMO ROOT!"))
		os.Exit(1)
	}

	if _, err := os.Stat("/dev/net/tun"); os.IsNotExist(err) {
		fmt.Println(red("TUN/TAP NÃO ESTÁ DISPONÍVEL. VERIFIQUE A CONFIGURAÇÃO DO SEU KERNEL."))
		os.Exit(3)
	}

	// Deteta o sistema operativo
	if _, err := os.Stat("/etc/debian_version"); err == nil {
		osType = "debian"
		groupName = "nogroup"
		rcLocal = "/etc/rc.local"
	} else if _, err := os.Stat("/etc/centos-release"); err == nil {
		osType = "centos"
		groupName = "nobody"
		rcLocal = "/etc/rc.d/rc.local"
	} else {
		fmt.Println(red("SISTEMA OPERATIVO NÃO SUPORTADO (APENAS DEBIAN/CENTOS)."))
		os.Exit(5)
	}
}

// Função de barra de progresso corrigida
func funBar(cmdToRun string) {
	fmt.Printf("%sAguarde... %s[%s", yellow(""), white(""), yellow(""))
	done := make(chan bool)

	go func() {
		cmd := exec.Command("bash", "-c", cmdToRun)
		cmd.Run()
		done <- true
	}()

	// Animação da barra de progresso
	for {
		select {
		case <-done:
			// Preenche a barra e finaliza
			fmt.Printf("\r%sAguarde... %s[%s]%s - %sOK!%s\n", yellow(""), white(""), green(strings.Repeat("#", 18)), white(""), green(""), white(""))
			return
		default:
			for i := 0; i < 18; i++ {
				fmt.Printf("\r%sAguarde... %s[%s%s%s]", yellow(""), white(""), green(strings.Repeat("#", i)), red(">"), yellow(strings.Repeat(" ", 17-i)))
				time.Sleep(100 * time.Millisecond)
			}
		}
	}
}

// Verifica se uma porta está em uso
func verifPtrs(porta int) {
	ln, err := net.Listen("tcp", fmt.Sprintf(":%d", porta))
	if err != nil {
		fmt.Printf("\n%sA PORTA %s%d %sESTÁ EM USO%s\n", red(""), yellow(""), porta, red(""), scolor(""))
		time.Sleep(3 * time.Second)
		menuPrincipal()
	}
	if ln != nil {
		ln.Close()
	}
}

// Cria um novo ficheiro de configuração de cliente (.ovpn)
func newClient(client string) {
	clientCommon, err := ioutil.ReadFile("/etc/openvpn/client-common.txt")
	if err != nil {
		fmt.Println(red("Erro ao ler client-common.txt:"), err)
		return
	}
	ca, err := ioutil.ReadFile("/etc/openvpn/easy-rsa/pki/ca.crt")
	if err != nil {
		fmt.Println(red("Erro ao ler ca.crt:"), err)
		return
	}
	cert, err := ioutil.ReadFile(fmt.Sprintf("/etc/openvpn/easy-rsa/pki/issued/%s.crt", client))
	if err != nil {
		fmt.Println(red("Erro ao ler o certificado do cliente:"), err)
		return
	}
	key, err := ioutil.ReadFile(fmt.Sprintf("/etc/openvpn/easy-rsa/pki/private/%s.key", client))
	if err != nil {
		fmt.Println(red("Erro ao ler a chave do cliente:"), err)
		return
	}
	tls, err := ioutil.ReadFile("/etc/openvpn/ta.key")
	if err != nil {
		fmt.Println(red("Erro ao ler ta.key:"), err)
		return
	}

	content := string(clientCommon) +
		"\n<ca>\n" + string(ca) + "</ca>\n" +
		"<cert>\n" + string(cert) + "</cert>\n" +
		"<key>\n" + string(key) + "</key>\n" +
		"<tls-auth>\n" + string(tls) + "</tls-auth>\n"

	err = ioutil.WriteFile(fmt.Sprintf("/root/%s.ovpn", client), []byte(content), 0644)
	if err != nil {
		fmt.Println(red("Erro ao escrever o ficheiro .ovpn:"), err)
	}
}

// Função principal de instalação do OpenVPN
func instalarOpenvpn() {
	// Detetar IP público (simplificado)
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		fmt.Println(red("Não foi possível determinar o endereço IP local."), err)
		os.Exit(1)
	}
	defer conn.Close()
	ip := conn.LocalAddr().(*net.UDPAddr).IP.String()

	clearScreen()
	fmt.Println("\033[44;1;37m INSTALADOR OPENVPN \033[0m")
	fmt.Println(green("A iniciar a instalação do OpenVPN..."))

	// Instalação de dependências
	if osType == "debian" {
		funBar("apt-get update && apt-get install -y build-essential autoconf automake libtool pkg-config liblz4-dev liblzo2-dev libssl-dev iptables openssl ca-certificates wget tar")
	} else {
		funBar("yum groupinstall -y 'Development Tools' && yum install -y epel-release && yum install -y autoconf automake libtool pkgconfig lz4-devel lzo-devel openssl-devel iptables openssl ca-certificates wget tar")
	}

	// Baixar e instalar OpenVPN
	fmt.Println(yellow("A baixar e compilar o OpenVPN..."))
	funBar(fmt.Sprintf("wget -O /tmp/openvpn.tar.gz https://swupdate.openvpn.org/community/releases/openvpn-%s.tar.gz && tar -xzf /tmp/openvpn.tar.gz -C /tmp && cd /tmp/openvpn-%s && ./configure && make && make install", OPENVPN_VERSION, OPENVPN_VERSION))

	// Baixar e configurar EasyRSA
	fmt.Println(yellow("A baixar e configurar o EasyRSA..."))
	os.MkdirAll("/etc/openvpn/easy-rsa", 0755)
	funBar(fmt.Sprintf("wget -O /tmp/easyrsa.tgz https://github.com/OpenVPN/easy-rsa/releases/download/v%s/EasyRSA-%s.tgz && tar -xzf /tmp/easyrsa.tgz -C /tmp && mv /tmp/EasyRSA-%s/* /etc/openvpn/easy-rsa/", EASYRSA_VERSION, EASYRSA_VERSION, EASYRSA_VERSION))
	
	os.Chdir("/etc/openvpn/easy-rsa/")
	funBar("./easyrsa init-pki && ./easyrsa --batch build-ca nopass && ./easyrsa gen-dh && ./easyrsa build-server-full server nopass && ./easyrsa build-client-full client nopass && ./easyrsa gen-crl")

	// Mover ficheiros e configurar permissões
	filesToCopy := []string{"pki/ca.crt", "pki/private/ca.key", "pki/dh.pem", "pki/issued/server.crt", "pki/private/server.key", "pki/crl.pem"}
	for _, f := range filesToCopy {
		exec.Command("cp", f, "/etc/openvpn").Run()
	}
	exec.Command("chown", "nobody:"+groupName, "/etc/openvpn/crl.pem").Run()
	exec.Command("openvpn", "--genkey", "--secret", "/etc/openvpn/ta.key").Run()

	// Configuração interativa
	var port int
	fmt.Printf("%sQual porta deseja usar para o OpenVPN? %s[padrão: 1194]: %s", green(""), yellow(""), white(""))
	fmt.Scanf("%d\n", &port)
	if port == 0 {
		port = 1194
	}
	verifPtrs(port)

	var protocol string
	fmt.Printf("%sQual protocolo? %s[1] UDP (recomendado) [2] TCP: %s", green(""), yellow(""), white(""))
	var protoChoice int
	fmt.Scanf("%d\n", &protoChoice)
	if protoChoice == 2 {
		protocol = "tcp"
	} else {
		protocol = "udp"
	}

	var dns1, dns2 string
	fmt.Printf("%sQual DNS usar? %s[1] Google (padrão) [2] Cloudflare [3] OpenDNS: %s", green(""), yellow(""), white(""))
	var dnsChoice int
	fmt.Scanf("%d\n", &dnsChoice)
	switch dnsChoice {
	case 2:
		dns1, dns2 = "1.1.1.1", "1.0.0.1"
	case 3:
		dns1, dns2 = "208.67.222.222", "208.67.220.220"
	default:
		dns1, dns2 = "8.8.8.8", "8.8.4.4"
	}

	// Escrever ficheiros de configuração
	serverConf := fmt.Sprintf(`port %d
proto %s
dev tun
ca ca.crt
cert server.crt
key server.key
dh dh.pem
auth SHA512
tls-auth ta.key 0
topology subnet
server 10.8.0.0 255.255.255.0
ifconfig-pool-persist ipp.txt
push "redirect-gateway def1 bypass-dhcp"
push "dhcp-option DNS %s"
push "dhcp-option DNS %s"
keepalive 10 120
cipher AES-256-CBC
user nobody
group %s
persist-key
persist-tun
status openvpn-status.log
verb 3
crl-verify crl.pem`, port, protocol, dns1, dns2, groupName)
	ioutil.WriteFile("/etc/openvpn/server.conf", []byte(serverConf), 0644)

	clientCommon := fmt.Sprintf(`client
dev tun
proto %s
remote %s %d
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
cipher AES-256-CBC
verb 3`, protocol, ip, port)
	ioutil.WriteFile("/etc/openvpn/client-common.txt", []byte(clientCommon), 0644)

	// Configurar Firewall
	exec.Command("sh", "-c", "echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/30-openvpn-forward.conf").Run()
	exec.Command("sysctl", "-p", "/etc/sysctl.d/30-openvpn-forward.conf").Run()
	exec.Command("iptables", "-t", "nat", "-A", "POSTROUTING", "-s", "10.8.0.0/24", "-o", "eth0", "-j", "MASQUERADE").Run()
	exec.Command("iptables-save", ">", "/etc/iptables/rules.v4").Run()

	// Iniciar e habilitar serviço
	exec.Command("systemctl", "start", "openvpn@server").Run()
	exec.Command("systemctl", "enable", "openvpn@server").Run()

	fmt.Println(green("OpenVPN instalado com sucesso!"))
	fmt.Println(yellow("A criar o primeiro cliente..."))
	var client string
	fmt.Printf("%sNome do primeiro cliente: %s", green(""), white(""))
	fmt.Scanln(&client)
	os.Chdir("/etc/openvpn/easy-rsa/")
	exec.Command("./easyrsa", "build-client-full", client, "nopass").Run()
	newClient(client)
	fmt.Println(green("Cliente criado! O ficheiro está em: ") + white(fmt.Sprintf("/root/%s.ovpn", client)))
	fmt.Println(green("Pressione ENTER para continuar..."))
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

// Função para remover o OpenVPN
func removerOpenvpn() {
	clearScreen()
	fmt.Println("\033[41;1;37m REMOVER OPENVPN \033[0m")
	fmt.Println(yellow("A parar o serviço OpenVPN..."))
	exec.Command("systemctl", "stop", "openvpn@server").Run()
	exec.Command("systemctl", "disable", "openvpn@server").Run()
	fmt.Println(yellow("A remover ficheiros de configuração..."))
	os.RemoveAll("/etc/openvpn")
	os.RemoveAll("/etc/iptables/rules.v4")

	if osType == "debian" {
		funBar("apt-get remove --purge -y openvpn && apt-get autoremove -y")
	} else {
		funBar("yum remove -y openvpn")
	}
	fmt.Println(green("OpenVPN removido com sucesso!"))
	fmt.Println(green("Pressione ENTER para continuar..."))
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

// Função para criar um novo cliente
func criarCliente() {
	clearScreen()
	fmt.Println(yellow("A criar um novo cliente..."))
	var client string
	fmt.Printf("%sNome do novo cliente: %s", green(""), white(""))
	fmt.Scanln(&client)
	os.Chdir("/etc/openvpn/easy-rsa/")
	// Usar --batch para evitar prompts interativos
	cmd := exec.Command("./easyrsa", "--batch", "build-client-full", client, "nopass")
	if err := cmd.Run(); err != nil {
		fmt.Println(red("Falha ao criar o cliente com EasyRSA:"), err)
		return
	}
	newClient(client)
	fmt.Println(green("Cliente criado! O ficheiro está em: ") + white(fmt.Sprintf("/root/%s.ovpn", client)))
	fmt.Println(green("Pressione ENTER para continuar..."))
	bufio.NewReader(os.Stdin).ReadBytes('\n')
}

// Menu principal da aplicação
func menuPrincipal() {
	output, err := exec.Command("systemctl", "is-active", "openvpn@server").Output()
	if err == nil && strings.TrimSpace(string(output)) == "active" {
		isOpenVPNInstalled = true
	} else {
		isOpenVPNInstalled = false
	}

	for {
		clearScreen()
		fmt.Println("\033[44;1;37m GESTOR OPENVPN \033[0m")
		fmt.Println("")
		if isOpenVPNInstalled {
			serverConf, _ := ioutil.ReadFile("/etc/openvpn/server.conf")
			re := regexp.MustCompile(`port (\d+)`)
			match := re.FindStringSubmatch(string(serverConf))
			port := "N/A"
			if len(match) > 1 {
				port = match[1]
			}
			fmt.Printf("%sStatus: %sOpenVPN Ativo - Porta: %s%s%s\n", green(""), white(""), green(""), port, scolor(""))
			fmt.Println("")
			fmt.Printf("%s[1] %sCriar Cliente\n", cyan(""), yellow(""))
			fmt.Printf("%s[2] %sRemover OpenVPN\n", cyan(""), yellow(""))
		} else {
			fmt.Printf("%sStatus: %sOpenVPN Não Instalado%s\n", red(""), white(""), scolor(""))
			fmt.Println("")
			fmt.Printf("%s[1] %sInstalar OpenVPN\n", cyan(""), yellow(""))
		}
		fmt.Printf("%s[0] %sSair\n", cyan(""), yellow(""))
		fmt.Println("")
		fmt.Printf("%sSelecione uma opção: %s", green(""), white(""))
		var option int
		fmt.Scanf("%d\n", &option)

		if isOpenVPNInstalled {
			switch option {
			case 1:
				criarCliente()
			case 2:
				removerOpenvpn()
			case 0:
				clearScreen()
				os.Exit(0)
			default:
				fmt.Println(red("Opção inválida!"))
				time.Sleep(2 * time.Second)
			}
		} else {
			switch option {
			case 1:
				instalarOpenvpn()
			case 0:
				clearScreen()
				os.Exit(0)
			default:
				fmt.Println(red("Opção inválida!"))
				time.Sleep(2 * time.Second)
			}
		}
	}
}

func main() {
	checkInitial()
	menuPrincipal()
}
