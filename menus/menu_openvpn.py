import os
import subprocess
from menus.menu_style_utils import print_header, clear_screen

# --- Funções de Verificação e Auxiliares ---

def verificar_openvpn_instalado():
    """Verifica se o OpenVPN está instalado procurando pelo arquivo de configuração."""
    return os.path.exists('/etc/openvpn/server.conf')

def obter_caminho_script_instalacao():
    """Encontra o script de instalação do OpenVPN para garantir a execução."""
    # O script principal (multiflow.py) define o diretório de trabalho,
    # então um caminho relativo deve funcionar.
    caminho_relativo = "conexoes/openvpn.sh"
    if os.path.exists(caminho_relativo):
        return caminho_relativo
    # Fallback para um caminho absoluto se o script for chamado de um local inesperado
    caminho_absoluto = "/opt/multiflow/conexoes/openvpn.sh"
    if os.path.exists(caminho_absoluto):
        return caminho_absoluto
    return None

def executar_script_instalacao():
    """Executa o script de instalação/gerenciamento do OpenVPN."""
    script_path = obter_caminho_script_instalacao()
    if not script_path:
        print("\n[ERRO] Script 'openvpn.sh' não encontrado.")
        input("Pressione Enter para continuar...")
        return

    # O script 'openvpn.sh' já está configurado para uma instalação automática.
    # Quando executado novamente, o script original do angristan (que é chamado por dentro)
    # lida com a adição, remoção e desinstalação de forma interativa, que é o desejado.
    try:
        # Garante que o script seja executável
        subprocess.run(['chmod', '+x', script_path], check=True)
        # Executa o script
        subprocess.run(['bash', script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERRO] Ocorreu um erro ao executar o script: {e}")
        input("Pressione Enter para continuar...")
    except FileNotFoundError:
        print(f"\n[ERRO] O comando 'bash' não foi encontrado. Verifique se ele está instalado.")
        input("Pressione Enter para continuar...")

def listar_clientes_ovpn():
    """Lista os arquivos de configuração de cliente (.ovpn) encontrados no diretório /root."""
    clear_screen()
    print_header()
    print("--- Clientes OpenVPN (.ovpn) Encontrados em /root/ ---")
    try:
        files = os.listdir('/root')
        ovpn_files = [f for f in files if f.endswith('.ovpn')]

        if not ovpn_files:
            print("\nNenhum arquivo de cliente (.ovpn) encontrado no diretório /root.")
        else:
            print("\nOs seguintes arquivos de configuração foram encontrados:")
            for filename in ovpn_files:
                print(f"  - /root/{filename}")
            print("\nUse um cliente SFTP (como FileZilla ou Termius) para baixar esses arquivos.")

    except FileNotFoundError:
        print("\n[AVISO] O diretório /root não foi encontrado ou não pôde ser acessado.")
    except Exception as e:
        print(f"\n[ERRO] Ocorreu um erro ao listar os arquivos: {e}")

    input("\nPressione Enter para voltar ao menu...")

# --- Funções do Menu ---

def menu_instalado():
    """Exibe o menu de gerenciamento quando o OpenVPN está instalado."""
    while True:
        clear_screen()
        print_header()
        print("--- Gerenciar OpenVPN (Instalado) ---")
        print("\n1. Adicionar um novo cliente")
        print("2. Remover um cliente existente")
        print("3. Listar arquivos de cliente (.ovpn)")
        print("4. Desinstalar o OpenVPN")
        print("5. Voltar ao menu principal")

        escolha = input("\nEscolha uma opção: ")

        if escolha == '1' or escolha == '2' or escolha == '4':
            clear_screen()
            print_header()
            print("Iniciando o assistente do OpenVPN...")
            print("Siga as instruções na tela.")
            executar_script_instalacao()
            input("\nAssistente finalizado. Pressione Enter para voltar ao menu.")
        elif escolha == '3':
            listar_clientes_ovpn()
        elif escolha == '5':
            break
        else:
            print("Opção inválida. Tente novamente.")
            input("Pressione Enter para continuar...")

def menu_nao_instalado():
    """Exibe o menu quando o OpenVPN não está instalado."""
    clear_screen()
    print_header()
    print("--- Gerenciar OpenVPN (Não Instalado) ---")
    print("\nO OpenVPN não parece estar instalado.")
    print("\nA instalação será totalmente automática com as seguintes configurações:")
    print("  - Protocolo: TCP")
    print("  - DNS: O mesmo da VPS")
    print("  - Primeiro Cliente: 'cliente1' (salvo em /root/cliente1.ovpn)")

    escolha = input("\nDeseja instalar o OpenVPN agora? (s/n): ").lower()

    if escolha == 's':
        clear_screen()
        print_header()
        print("Iniciando a instalação automática do OpenVPN...")
        print("Por favor, aguarde, este processo pode levar alguns minutos.")
        executar_script_instalacao()
        print("\nVerificação pós-instalação...")
        if verificar_openvpn_instalado():
             print("\n[SUCESSO] OpenVPN instalado com sucesso!")
        else:
             print("\n[FALHA] A instalação parece não ter sido concluída. Verifique os logs.")
        input("Pressione Enter para continuar...")

# --- Função Principal de Gerenciamento ---

def gerenciar_openvpn():
    """Função principal que direciona para o menu apropriado."""
    if verificar_openvpn_instalado():
        menu_instalado()
    else:
        menu_nao_instalado()