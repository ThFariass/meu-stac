import os
import shutil
import subprocess
import paramiko
from stat import S_ISDIR

# --- CONFIGURAÇÃO ---
# --- Preencha com os seus dados ---

# 1. Configurações do Servidor
SERVER_HOST = '172.21.5.20' # Ou 127.0.0.1. Ligamos ao nosso próprio PC
SERVER_PORT = 22        # A porta do "túnel" SSH que criámos no VirtualBox
SERVER_USER = 'censipam'      # O seu nome de utilizador no servidor Linux
SERVER_PASS = 'Censipam@2025.' # A sua senha de acesso ao servidor Linux

# 2. Caminhos no PC Windows (Hospedeiro)
PROJECT_DIR = 'D:/xampp/htdocs/meu-stac' # O caminho para a sua pasta principal de projeto
PYTHON_SCRIPT_PATH = os.path.join(PROJECT_DIR, 'script', 'gerar_catalogo.py')
STAC_BROWSER_DIR = os.path.join(PROJECT_DIR, 'stac-browser')

# 3. Caminhos no Servidor Linux (Convidado)
REMOTE_BASE_DIR = '/var/www/html/meu-stac'
# ----------------------------------------

def run_local_command(command, working_dir):
    """Executa um comando local no terminal e mostra a saída."""
    print(f"--- Executando comando: '{' '.join(command)}' em '{working_dir}' ---")
    try:
        process = subprocess.Popen(command, cwd=working_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end='')
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        print(f"--- Comando concluído com sucesso ---\n")
    except Exception as e:
        print(f"ERRO ao executar comando: {e}")
        raise

def upload_directory(sftp_client, local_dir, remote_dir):
    """Envia um diretório local e todo o seu conteúdo para o servidor recursivamente."""
    print(f"Enviando diretório '{local_dir}' para '{remote_dir}'...")
    try:
        sftp_client.mkdir(remote_dir)
    except IOError:
        pass # A pasta provavelmente já existe, o que não é um problema.
        
    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        remote_path = f"{remote_dir}/{item}"
        if os.path.isdir(local_path):
            upload_directory(sftp_client, local_path, remote_path)
        else:
            print(f"  - Enviando ficheiro: {item}")
            sftp_client.put(local_path, remote_path)

def main():
    """Função principal que orquestra todo o processo."""
    print("====== INICIANDO PIPELINE DE ATUALIZAÇÃO E DEPLOYMENT ======\n")
    
    try:
        # ETAPA 1: Gerar o catálogo
        run_local_command(['python', PYTHON_SCRIPT_PATH], working_dir=os.path.dirname(PYTHON_SCRIPT_PATH))

        # ETAPA 2: Construir a aplicação STAC Browser
        run_local_command(['npm', 'run', 'build'], working_dir=STAC_BROWSER_DIR)
        
        # ETAPA 3: Enviar tudo para o servidor
        print("--- Iniciando envio de ficheiros para o servidor ---")
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(SERVER_HOST, port=SERVER_PORT, username=SERVER_USER, password=SERVER_PASS)
        
        sftp = ssh_client.open_sftp()
        
        # Define os diretórios a serem enviados
        folders_to_upload = {
            os.path.join(PROJECT_DIR, 'catalogo'): f"{REMOTE_BASE_DIR}/catalogo",
            os.path.join(PROJECT_DIR, 'imagens_organizadas_por_satelite'): f"{REMOTE_BASE_DIR}/imagens_organizadas_por_satelite",
            os.path.join(STAC_BROWSER_DIR, 'dist'): f"{REMOTE_BASE_DIR}/stac-browser" # Enviamos para uma pasta temporária
        }
        
        # Limpa o conteúdo antigo no servidor e envia o novo
        ssh_client.exec_command(f"rm -rf {REMOTE_BASE_DIR}/catalogo {REMOTE_BASE_DIR}/stac-browser")
        ssh_client.exec_command(f"mkdir -p {REMOTE_BASE_DIR}/catalogo {REMOTE_BASE_DIR}/stac-browser")
        
        # Envia os ficheiros
        for local, remote in folders_to_upload.items():
             upload_directory(sftp, local, remote)
        
        # Renomeia a pasta 'dist' (enviada como stac-browser-novo) para o nome final
        ssh_client.exec_command(f"mv {REMOTE_BASE_DIR}/stac-browser/* {REMOTE_BASE_DIR}/stac-browser/")
        ssh_client.exec_command(f"rm -rf {REMOTE_BASE_DIR}/stac-browser")
        
        sftp.close()
        ssh_client.close()
        
        print("\n--- Envio concluído com sucesso ---")
        
    except Exception as e:
        print(f"\n!!!!!! O PIPELINE FALHOU: {e} !!!!!!")
        return

    print("\n====== PIPELINE CONCLUÍDO COM SUCESSO! O SITE FOI ATUALIZADO. ======")


if __name__ == "__main__":
    main()