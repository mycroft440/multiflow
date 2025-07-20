## Tarefas para instalação do MultiFlow Proxy

- [ ] **Fase 1: Extrair e analisar o arquivo fornecido**
  - [x] Extrair o arquivo `multiflow_proxy_updated.zip`.
  - [x] Analisar a estrutura de diretórios e arquivos extraídos.
  - [x] Ler o conteúdo do script `install.sh`.

- [ ] **Fase 2: Instalar dependências e configurar o projeto**
  - [x] Mover os arquivos extraídos para os diretórios de destino (`/opt/rusty_socks_proxy` e `/home/ubuntu/install.sh`).
  - [x] Instalar as dependências necessárias (Rust, Cargo, build-essential).
  - [x] Compilar o projeto Rust.
  - [x] Configurar o serviço systemd.

- [ ] **Fase 3: Executar e testar a instalação**
  - [x] Iniciar o serviço `rusty_socks_proxy`.
  - [x] Verificar o status do serviço.
  - [ ] Testar a funcionalidade do proxy (se possível).

- [ ] **Fase 4: Reportar resultados ao usuário**
  - [x] Informar o usuário sobre a conclusão da instalação.
  - [ ] Fornecer instruções sobre como usar o proxy e o gerenciador de usuários SSH.

## Tarefas para adicionar dtproxy ao menu

- [x] **Fase 1: Extrair e analisar o projeto dtproxy**
  - [x] Extrair o arquivo `dtproxy_project_improved.zip`.
  - [x] Analisar a estrutura de diretórios e arquivos extraídos.
  - [x] Ler o conteúdo do script `install.sh`.

- [x] **Fase 2: Modificar o script install.sh para incluir a nova opção e a instalação do dtproxy**
  - [x] Criar a função `install_dtproxy_mycroft()`.
  - [x] Modificar a função `manage_connections_menu()` para incluir a nova opção e atualizar a numeração.
  - [x] Implementar a lógica de instalação do dtproxy na função `install_dtproxy_mycroft()`:
    - [x] Mover os arquivos do dtproxy para `/opt/dtproxy/`.
    - [x] Tornar o executável `dtproxy_x86_64` executável.
    - [x] Criar um arquivo de serviço systemd para o dtproxy.
    - [x] Habilitar e iniciar o serviço dtproxy.

- [ ] **Fase 3: Testar a nova opção do menu**
  - [x] Executar o script `install.sh` para verificar o novo menu.
  - [x] Selecionar a opção de instalação do dtproxy.
  - [x] Verificar se o dtproxy foi instalado e está em execução.

- [ ] **Fase 4: Informar o usuário sobre as mudanças**
  - [ ] Notificar o usuário sobre a nova funcionalidade.


- [ ] Corrigir erros de sintaxe e lógica no `install.sh`, especialmente na função `install_proxy_single_command`.
- [ ] Garantir que todos os arquivos referenciados no `install.sh` (como `main.rs`, `Cargo.toml`, `rusty_socks_proxy.service`, `new_ssh_user_management.sh`) estejam presentes no pacote ou sejam baixados corretamente de um repositório acessível.
- [ ] Implementar um gerenciamento de dependências mais robusto, especialmente para `libssl1.1` e `dtproxy`, considerando a compatibilidade com o Ubuntu 22.04.
- [ ] Corrigir loops infinitos nos menus, garantindo que as opções de saída funcionem corretamente.
- [ ] Corrigir os caminhos incorretos no `dtproxy_menu.sh` e garantir que o `dtproxy_x86_64` seja executável e acessível.
- [ ] Habilitar e testar as funcionalidades de gerenciamento de usuários SSH, OpenVPN e ferramentas de limpeza/performance.
- [ ] Criar um plano de testes detalhado para cada funcionalidade após as correções.
- [ ] Documentar todas as alterações e melhorias realizadas.


