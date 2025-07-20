# MultiFlow - Gerenciador de Conexões e Ferramentas

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04%20LTS-orange.svg)](https://ubuntu.com/)
[![Rust](https://img.shields.io/badge/Rust-1.88.0-red.svg)](https://www.rust-lang.org/)

Um gerenciador completo de conexões, proxies e ferramentas de sistema para Ubuntu, desenvolvido em Bash e Rust.

## 🚀 Características

- **Proxy SOCKS5** de alta performance desenvolvido em Rust
- **Gerenciamento completo de usuários SSH** com controle de acesso
- **dtproxy** para proxy HTTP com múltiplas portas
- **Ferramentas de otimização** e limpeza do sistema
- **Interface moderna** com menus interativos coloridos
- **Instalação automatizada** com verificações de segurança

## 📋 Pré-requisitos

- Ubuntu 22.04 LTS ou superior
- Acesso root (sudo)
- Conexão com a internet
- Arquitetura x86_64

## 🔧 Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/multiflow.git
cd multiflow

# Execute o instalador
sudo chmod +x install_fixed.sh
sudo ./install_fixed.sh
```

## 📦 Componentes

### 1. Proxy SOCKS5 (Rust)
- Proxy SOCKS5 completo e eficiente
- Configuração de porta personalizada
- Serviço systemd automático
- Suporte a IPv4 e resolução de domínios

### 2. Gerenciador SSH
- Criação e remoção de usuários
- Configuração de limites de conexão
- Controle de expiração de contas
- Monitoramento de sessões ativas

### 3. dtproxy
- Proxy HTTP de alta velocidade
- Gerenciamento de múltiplas portas
- Interface de controle avançada
- Compatibilidade total com Ubuntu 22.04

### 4. Ferramentas de Sistema
- Otimização automática do kernel
- Monitoramento com iostat
- Limpeza com Stacer/BleachBit
- Backup de configurações

## 🎯 Uso Rápido

Após a instalação, execute:

```bash
sudo ./install_fixed.sh
```

Navegue pelos menus para:
1. **Gerenciar Usuários SSH**
2. **Instalar e configurar proxies**
3. **Verificar status dos serviços**
4. **Executar ferramentas de otimização**

## 🔍 Verificação

```bash
# Verificar serviços
sudo systemctl status rusty_socks_proxy
sudo systemctl status dtproxy

# Verificar portas
sudo netstat -tlnp | grep -E "(1080|10000)"
```

## 📁 Estrutura do Projeto

```
multiflow/
├── install_fixed.sh              # Instalador principal
├── main.rs                       # Código do proxy SOCKS5
├── Cargo.toml                    # Configuração Rust
├── rusty_socks_proxy.service     # Serviço systemd
├── new_ssh_user_management.sh    # Gerenciador SSH
├── dtproxy_project/              # Módulo dtproxy
│   ├── dtproxy_x86_64           # Executável
│   └── dtproxy_menu_fixed.sh    # Menu de controle
├── RELATORIO_FINAL_CORRECOES.md  # Relatório técnico
└── README.md                     # Este arquivo
```

## 🛠️ Desenvolvimento

### Compilar o proxy SOCKS5

```bash
# Instalar Rust (se necessário)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Compilar
cargo build --release
```

### Executar testes

```bash
# Verificar sintaxe dos scripts
bash -n install_fixed.sh
bash -n new_ssh_user_management.sh

# Testar compilação Rust
cargo check
```

## 🔒 Segurança

- Validação rigorosa de entrada em todos os scripts
- Verificação de privilégios antes de operações críticas
- Backup automático de configurações do sistema
- Configurações de segurança nos serviços systemd
- Isolamento de processos com usuários específicos

## 📊 Compatibilidade

- ✅ Ubuntu 22.04 LTS (testado)
- ✅ Sistemas baseados em Debian
- ✅ Arquitetura x86_64
- ✅ OpenSSL 3.0
- ✅ Rust 1.88.0+

## 🐛 Solução de Problemas

### libssl1.1 não encontrada
```bash
sudo apt update
sudo apt install libssl1.1
```

### Porta em uso
```bash
sudo lsof -i :PORTA
sudo kill PID_DO_PROCESSO
```

### Logs dos serviços
```bash
sudo journalctl -u rusty_socks_proxy -f
sudo journalctl -u dtproxy -f
```

## 📝 Changelog

### v2.0 (Corrigida) - 2025-07-20
- ✅ Reescrita completa do instalador principal
- ✅ Implementação do proxy SOCKS5 em Rust
- ✅ Gerenciador SSH completo e funcional
- ✅ Correção do módulo dtproxy
- ✅ Interface moderna com cores
- ✅ Compatibilidade total com Ubuntu 22.04
- ✅ Testes abrangentes e validação

### v1.0 (Original)
- Versão inicial com problemas de compatibilidade

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👥 Autores

- **MultiFlow Team** - *Desenvolvimento inicial*
- **Manus AI** - *Correções e melhorias v2.0*

## 🙏 Agradecimentos

- Comunidade Rust pela excelente documentação
- Desenvolvedores do dtproxy original
- Comunidade Ubuntu pelo suporte

---

**⚠️ Aviso:** Use este software por sua própria conta e risco. Sempre teste em ambiente de desenvolvimento antes de usar em produção.

**📞 Suporte:** Para problemas ou dúvidas, abra uma issue no GitHub ou consulte a documentação técnica.

