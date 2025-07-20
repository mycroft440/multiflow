# Plano de Correção e Melhoria - Projeto MultiFlow

## 1. Análise e Correção do `install.sh`

### Problemas Identificados:
- Erros de sintaxe e lógica.
- Caminhos incorretos e arquivos ausentes.
- Dependências não gerenciadas (ex: `libssl1.1`).
- Loops infinitos em menus.

### Plano de Ação:
1. **Revisão Completa do Código**: Realizar uma revisão linha a linha do `install.sh` para identificar e corrigir todos os erros de sintaxe e lógica. Utilizar ferramentas de linting para Bash, se necessário.
2. **Validação de Caminhos e Arquivos**: Garantir que todos os caminhos de arquivos e URLs de download estejam corretos e que os arquivos (`main.rs`, `Cargo.toml`, `rusty_socks_proxy.service`, `new_ssh_user_management.sh`) estejam acessíveis. Se necessário, incluir esses arquivos diretamente no pacote `multiflow_complete_final.zip` ou fornecer URLs de repositórios confiáveis.
3. **Gerenciamento de Dependências**: 
    - Para `libssl1.1`: Pesquisar alternativas compatíveis com Ubuntu 22.04 (OpenSSL 3.0) ou fornecer instruções claras para a instalação manual de `libssl1.1` de forma segura e estável, se for estritamente necessário para o `dtproxy`.
    - Para outras dependências (`build-essential`, `sysstat`, `stacer`, `bleachbit`, `openvpn`, `easy-rsa`): Assegurar que os comandos `apt update` e `apt install` sejam executados com sucesso e que as dependências sejam verificadas antes da instalação.
4. **Correção de Menus**: Analisar a lógica dos menus para eliminar loops infinitos e garantir que todas as opções de navegação e saída funcionem conforme o esperado.

## 2. Correção do Módulo `dtproxy`

### Problemas Identificados:
- Dependência `libssl1.1` ausente.
- Caminhos incorretos no `dtproxy_menu.sh`.

### Plano de Ação:
1. **Resolução da Dependência `libssl1.1`**: 
    - **Opção A (Preferencial)**: Se possível, recompilar o `dtproxy_x86_64` para usar OpenSSL 3.0, eliminando a dependência de `libssl1.1`.
    - **Opção B (Alternativa)**: Se a recompilação não for viável, fornecer um método robusto e seguro para instalar `libssl1.1` no Ubuntu 22.04, com avisos claros sobre possíveis conflitos de dependência.
2. **Correção de Caminhos**: Atualizar o `dtproxy_menu.sh` para que referencie corretamente o executável `dtproxy_x86_64` e outros arquivos necessários.

## 3. Ativação e Teste do Rusty SOCKS5 Proxy

### Problemas Identificados:
- Inoperabilidade devido à ausência de `main.rs`, `Cargo.toml` e `rusty_socks_proxy.service`.

### Plano de Ação:
1. **Inclusão de Arquivos**: Adicionar `main.rs`, `Cargo.toml` e `rusty_socks_proxy.service` ao pacote do projeto ou garantir que sejam baixados de um repositório confiável.
2. **Revisão do Processo de Compilação**: Verificar e corrigir o processo de compilação do proxy Rust no `install.sh`, garantindo que o `cargo build --release` seja executado corretamente e que o serviço `systemd` seja configurado e iniciado com sucesso.
3. **Testes Funcionais**: Após a correção, realizar testes completos para verificar a funcionalidade do proxy SOCKS5.

## 4. Habilitação e Teste de Funcionalidades Não Testadas

### Problemas Identificados:
- Gerenciamento de Usuários SSH não testado.
- Gerenciamento de OpenVPN não testado.
- Ferramentas de Limpeza e Performance não testadas.

### Plano de Ação:
1. **Gerenciamento de Usuários SSH**: 
    - Incluir o `new_ssh_user_management.sh` no pacote ou garantir seu download.
    - Descomentar e testar a função `install_ssh_user_manager` e `manage_ssh_users_menu` no `install.sh`.
2. **Gerenciamento de OpenVPN**: 
    - Testar a função `fun_openvpn` e as opções de gerenciamento de OpenVPN no `install.sh`.
    - Verificar a geração de arquivos de configuração do cliente (`.ovpn`).
3. **Ferramentas de Limpeza e Performance**: 
    - Testar as funções `run_iostat`, `optimize_kernel`, `install_and_run_stacer`, `run_bleachbit`.
    - Garantir que a instalação e execução dessas ferramentas funcionem em um ambiente sem interface gráfica, se aplicável.

## 5. Plano de Testes e Validação

### Plano de Ação:
1. **Testes Unitários**: Se possível, criar testes unitários para as funções críticas do `install.sh`.
2. **Testes de Integração**: Testar a integração entre os diferentes módulos (proxy Rust, dtproxy, gerenciador SSH, OpenVPN).
3. **Testes de Regressão**: Após cada correção, executar testes para garantir que nenhuma funcionalidade existente tenha sido quebrada.
4. **Documentação de Testes**: Registrar os resultados dos testes e quaisquer novos problemas encontrados.

## 6. Melhorias Gerais e Documentação

### Plano de Ação:
1. **Refatoração do Código**: Melhorar a legibilidade e manutenibilidade do `install.sh` e outros scripts, utilizando funções, comentários e padronização de código.
2. **Tratamento de Erros**: Implementar um tratamento de erros mais robusto com mensagens claras para o usuário.
3. **Documentação Atualizada**: Atualizar o `README.md` do projeto com instruções claras de instalação, uso e solução de problemas.
4. **Geração de Relatório Final**: Após todas as correções e testes, gerar um relatório final detalhado com as melhorias implementadas e os resultados dos testes.

