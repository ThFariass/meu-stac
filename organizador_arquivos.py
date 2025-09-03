import os
import shutil
import xml.etree.ElementTree as ET
import re

# --- CONFIGURAÇÃO ---
# 1. Defina a pasta raiz onde estão as subpastas das coleções (ex: cbers-4a).
SOURCE_DIR = '../imagens'

# 2. Defina a pasta onde as pastas organizadas por satélite serão criadas.
DESTINATION_DIR = '../imagens_organizadas_por_satelite'

# 3. XPath para encontrar a tag do nome do satélite no arquivo XML.
SATELLITE_TAG_XPATH = './satellite_name'
# --------------------


def sanitize_foldername(name):
    """Remove caracteres inválidos de uma string para usá-la como nome de pasta."""
    if not name:
        return "sem_nome"
    return re.sub(r'[\\/*?:"<>|]', "", name.strip())

def organize_folders_recursively():
    """
    Função principal que busca recursivamente por pastas contendo arquivos XML
    e as move para um diretório organizado por nome de satélite.
    """
    print("--- INICIANDO ORGANIZADOR COM PRESERVAÇÃO DE ESTRUTURA ---")

    # Cria o diretório de destino principal, se não existir
    os.makedirs(DESTINATION_DIR, exist_ok=True)
    print(f"Diretório de destino: '{os.path.abspath(DESTINATION_DIR)}'")

    processed_count = 0
    error_count = 0

    # Percorre a árvore de diretórios de baixo para cima (bottom-up)
    # Isso é crucial para mover as pastas mais profundas primeiro.
    for root, dirs, files in os.walk(SOURCE_DIR, topdown=False):
        
        # Procura por um arquivo .xml na pasta atual ('root')
        xml_file_name = next((f for f in files if f.lower().endswith('.xml')), None)

        # Se não houver XML, esta não é uma pasta de produto, então a ignoramos.
        if not xml_file_name:
            continue

        # Se encontramos um XML, esta 'root' é a pasta do produto que queremos mover.
        product_folder_path = root
        product_folder_name = os.path.basename(product_folder_path)
        xml_path = os.path.join(product_folder_path, xml_file_name)
        
        print(f"\nEncontrada pasta de produto: '{product_folder_path}'")

        try:
            # 1. Extrair o nome do satélite do XML
            tree = ET.parse(xml_path)
            xml_root = tree.getroot()
            satellite_element = xml_root.find(SATELLITE_TAG_XPATH)

            if satellite_element is None or not satellite_element.text:
                print(f"  - AVISO: Tag de satélite não encontrada em '{xml_file_name}'. Pulando pasta.")
                error_count += 1
                continue
                
            satellite_name = sanitize_foldername(satellite_element.text)
            
            # 2. Construir o caminho de destino, preservando a estrutura
            # Pega o caminho relativo da pasta do produto em relação à origem
            # Ex: 'cbers-4a/920012238.../workvol/output'
            relative_path = os.path.relpath(product_folder_path, SOURCE_DIR)
            
            # Monta o caminho de destino final
            # Ex: '../imagens_organizadas/ICEYE-X43/cbers-4a/920012238.../workvol/output'
            final_destination_path = os.path.join(DESTINATION_DIR, satellite_name, relative_path)
            
            # Cria a estrutura de pastas no destino, se não existir
            # Ex: cria a pasta '../imagens_organizadas/ICEYE-X43/cbers-4a/920012238.../workvol'
            os.makedirs(os.path.dirname(final_destination_path), exist_ok=True)

            # 3. Mover a pasta inteira do produto para o novo local
            print(f"  - Satélite detectado: '{satellite_name}'")
            print(f"  - Movendo para: '{final_destination_path}'")

            if not os.path.exists(final_destination_path):
                shutil.move(product_folder_path, final_destination_path)
                processed_count += 1
            else:
                print(f"  - AVISO: A pasta '{product_folder_name}' já existe no destino. Não foi movida.")
                error_count += 1
                
        except Exception as e:
            print(f"  - ERRO: Falha ao processar a pasta '{product_folder_name}': {e}")
            error_count += 1

    print("\n--- PROCESSO CONCLUÍDO ---")
    print(f"Total de pastas de produtos movidas com sucesso: {processed_count}")
    print(f"Total de pastas com erro ou puladas: {error_count}")

    print("\n--- PROCESSO CONCLUÍDO ---")
    print(f"Total de pastas de produtos movidas com sucesso: {processed_count}")
    print(f"Total de pastas com erro ou puladas: {error_count}")


# Executa a função principal
if __name__ == "__main__":
    organize_folders_recursively()