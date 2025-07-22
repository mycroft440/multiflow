# MultiFlow - Gerenciador de Conexões e Ferramentas

MultiFlow é um sistema completo para gerenciamento de conexões, ferramentas de otimização e usuários SSH em sistemas Linux.

## Características

- **Gerenciamento de dtproxy**: Instalação, configuração e gerenciamento de portas
- **Gerenciamento de SOCKS5**: Proxy SOCKS5 customizado em Rust
- **Gerenciamento de usuários SSH**: Criação, remoção e monitoramento de usuários
- **Interface interativa**: Menus coloridos e intuitivos
- **Instalação automatizada**: Script de instalação que configura todas as dependências

## Instalação

### Método 1: Instalação via GitHub (Recomendado)

```bash
sudo apt update && sudo apt install -y git && sudo rm -rf multiflow && git clone https://github.com/mycroft440/multiflow.git && cd multiflow && sudo chmod +x install_fixed.sh && sudo ./install_fixed.sh
```

### Método 2: Instalação Manual

1. Baixe e extraia o projeto
2. Entre no diretório do projeto
3. Execute o script de instalação:

```bash
sudo chmod +x install_fixed.sh
sudo ./install_fixed.sh
```

## Uso

Após a instalação, você pode acessar o menu principal através do script:

```bash
sudo ./menu.sh
```

### Funcionalidades Disponíveis

#### 1. Gerenciar dtproxy
- Instalar dtproxy
- Iniciar/parar instâncias
- Gerenciar portas
- Abrir portas no firewall
- Monitorar status

#### 2. Gerenciar SOCKS5
- Instalar proxy SOCKS5
- Alterar porta do serviço
- Abrir portas no firewall
- Remover instalação

#### 3. Gerenciar Usuários SSH
- Criar novos usuários
- Remover usuários existentes
- Listar usuários e conexões ativas
- Configurar limites de conexão
- Definir datas de expiração

## Estrutura do Projeto

```
multiflow/
├── install_fixed.sh              # Script de instalação principal
├── menu.sh                       # Menu principal interativo
├── new_ssh_user_management.sh    # Gerenciador de usuários SSH
├── openvpn_manager.sh            # Gerenciador OpenVPN (em desenvolvimento)
├── rusty_socks_proxy.service     # Arquivo de serviço systemd para SOCKS5
├── rusty_socks_proxy_menu.sh     # Menu do SOCKS5
└── dtproxy_project/
    ├── dtproxy_menu.sh           # Menu do dtproxy
    └── dtproxy_x86_64            # Executável do dtproxy
```

## Dependências

O script de instalação automaticamente instala:

- build-essential
- curl, wget, git
- libssl-dev
- libssl1.1 (para compatibilidade com dtproxy)
- Rust e Cargo
- UFW (firewall)

## Compatibilidade

- **Sistema Operacional**: Ubuntu 22.04+ (testado)
- **Arquitetura**: x86_64
- **Privilégios**: Requer sudo para instalação e algumas operações

## Solução de Problemas

### dtproxy não inicia
- Verifique se libssl1.1 está instalada
- Confirme que a porta não está em uso
- Execute: `sudo systemctl status dtproxy`

### SOCKS5 não funciona
- Verifique o status do serviço: `sudo systemctl status rusty_socks_proxy`
- Confirme que a porta está aberta no firewall
- Verifique os logs: `journalctl -u rusty_socks_proxy`

### Problemas de permissão
- Certifique-se de executar com sudo quando necessário
- Verifique as permissões dos arquivos: `ls -la`

## Contribuição

Para contribuir com o projeto:

1. Faça um fork do repositório
2. Crie uma branch para sua feature
3. Commit suas mudanças
4. Abra um Pull Request

## Licença

Este projeto é distribuído sob licença MIT. Veja o arquivo LICENSE para mais detalhes.

## Suporte

Para suporte e relatórios de bugs, abra uma issue no repositório GitHub.

---

**Versão**: 2.0 (Corrigida)
**Autor**: MultiFlow Team
**Data**: 2025
