# Importa as bibliotecas necessárias
import pystac
from datetime import datetime
import os
import shutil
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, mapping

# --- CONFIGURAÇÃO ---
# root_url = 'http://localhost/meu-stac'
root_url = 'http://192.168.56.1:8080/meu-stac'
source_dir = '../imagens_organizadas_por_satelite' 
catalog_dir = '../catalogo'
# --------------------

# --- LIMPEZA ---
if os.path.exists(catalog_dir):
    shutil.rmtree(catalog_dir)
# --------------------

catalog = pystac.Catalog(id='Catalogo Censipam', description='Catálogo Geoespacial de Imagens do Censipam.')
collections = {}

print("--- INICIANDO CRIAÇÃO DO CATÁLOGO PROFISSIONAL ---")

for root, dirs, files in os.walk(source_dir):
    # Pula o diretório raiz, pois ele não contém itens
    if root == source_dir:
        continue

    # Encontra o arquivo TIF principal. Se não houver, pula a pasta.
    primary_tif_file = next((f for f in files if f.lower().endswith(('.tif', '.tiff'))), None)
    if not primary_tif_file:
        print(f"  - AVISO: Nenhum arquivo TIF encontrado em '{root}'. Pulando.")
        continue

    print(f"\n> Processando diretório: {os.path.basename(root)}")

    # Define a qual coleção este item pertence
    collection_id = os.path.relpath(root, source_dir).split(os.sep)[0]
    if collection_id not in collections:
        print(f"  > Criando nova coleção: {collection_id}")
        new_collection = pystac.Collection(
            id=collection_id, description=f'Imagens da coleção {collection_id}.',
            extent=pystac.Extent(spatial=pystac.SpatialExtent([-180, -90, 180, 90]), temporal=pystac.TemporalExtent([[datetime(2020, 1, 1), None]])))
        catalog.add_child(new_collection)
        collections[collection_id] = new_collection
    current_collection = collections[collection_id]
        
    # ID do item baseado no nome do arquivo TIF
    base_name = os.path.splitext(primary_tif_file)[0]
    
    # Inicializa todas as variáveis com valores padrão.
    # Isso evita erros 'NameError' caso o XML falhe.
    geometry = None
    bbox = None
    item_datetime = datetime.utcnow() # Usa data atual como fallback
    properties = {}
    
    # --- ETAPA 2: LER XML E EXTRAIR METADADOS ---
    
    xml_file = next((os.path.join(root, f) for f in files if f.lower().endswith('.xml')), None)
    if xml_file:
        print(f"  > Lendo metadados de: {os.path.basename(xml_file)}")
        try:
            tree = ET.parse(xml_file)
            xml_root = tree.getroot()

            # Extrai metadados e os armazena no dicionário 'properties'
            # 1. Nome do Satélite
            el = xml_root.find('.//satellite_name')
            if el is not None: properties['platform'] = el.text

            # 2. Datas
            el = xml_root.find('.//acquisition_start_utc')
            if el is not None: item_datetime = datetime.fromisoformat(el.text.replace('Z', ''))
            
            el = xml_root.find('.//acquisition_end_utc')
            if el is not None: properties['end_datetime'] = el.text

            # 3. Modo de Aquisição, Lado, Órbita, etc.
            if (el := xml_root.find('.//acquisition_mode')) is not None: properties['acquisition_mode'] = el.text
            if (el := xml_root.find('.//look_side')) is not None: properties['view:off_nadir'] = el.text
            if (el := xml_root.find('.//orbit_direction')) is not None: properties['sat:orbit_state'] = el.text.lower()
            if (el := xml_root.find('.//incidence_center')) is not None: properties['view:incidence_angle'] = float(el.text)
            if (el := xml_root.find('.//polarization')) is not None: properties['sar:polarizations'] = [p.strip() for p in el.text.split(',')]
            if (el := xml_root.find('.//product_file')) is not None: properties['product_name'] = el.text

            # Extração da GEOMETRIA
            # ATENÇÃO: Encontre as tags corretas para TODOS os 4 cantos no seu XML!
            try:
                print("    > Extraindo geometria dos 4 cantos...")
                # Pega o texto de cada tag de coordenada
                # A ordem das tags pode variar, mas estas são as 4 que definem os cantos
                # Exemplo: coord_first_far -> Canto Superior Esquerdo
                #          coord_first_near -> Canto Superior Direito
                #          coord_last_near -> Canto Inferior Direito
                #          coord_last_far -> Canto Inferior Esquerdo

                # Extrai as coordenadas de cada canto
                text_canto_se = xml_root.find('.//coord_first_far').text
                text_canto_sd = xml_root.find('.//coord_first_near').text
                text_canto_id = xml_root.find('.//coord_last_near').text
                text_canto_ie = xml_root.find('.//coord_last_far').text

                # As coordenadas são os dois últimos números, separados por espaço.
                # O formato em STAC/GeoJSON é [Longitude, Latitude]
                canto_se = [float(text_canto_se.split()[3]), float(text_canto_se.split()[2])]
                canto_sd = [float(text_canto_sd.split()[3]), float(text_canto_sd.split()[2])]
                canto_id = [float(text_canto_id.split()[3]), float(text_canto_id.split()[2])]
                canto_ie = [float(text_canto_ie.split()[3]), float(text_canto_ie.split()[2])]

                # Cria a lista de coordenadas na ordem correta para formar o polígono
                # (sentido anti-horário) e fecha o polígono repetindo o primeiro ponto no final.
                coords = [canto_se, canto_sd, canto_id, canto_ie, canto_se]
                
                geometry = mapping(Polygon(coords))
                bbox = list(Polygon(coords).bounds)
                
                print("      > Geometria e Bounding Box criados com sucesso.")

            except Exception as geo_e:
                print(f"    - ERRO: Falha ao extrair geometria do XML. O mapa ficará genérico. Erro: {geo_e}")
                geometry = None
                bbox = None


        except Exception as e:
            print(f"    - ERRO: Falha crítica ao processar o arquivo XML. Erro: {e}")

    # --- ETAPA 3: CRIAR O ITEM STAC ---
    
    item = pystac.Item(id=base_name,
                       geometry=geometry,
                       bbox=bbox,
                       datetime=item_datetime,
                       properties=properties)

    # Adiciona metadados comuns se existirem
    if 'platform' in item.properties:
        item.common_metadata.platform = item.properties.pop('platform')
    
    # --- ETAPA 4: ADICIONAR ASSETS ---
    
    print(f"  > Adicionando assets para o item: {item.id}")
    for f in files:
        url_path = os.path.relpath(os.path.join(root, f), source_dir).replace('\\', '/')
        href = f"{root_url}/imagens_organizadas_por_satelite/{url_path}" # Usando caminhos relativos para SELF_CONTAINED
        if f.lower().endswith(('.tif', '.tiff')):
            item.add_asset('data', pystac.Asset(href=href, media_type=pystac.MediaType.COG, roles=['data']))
        elif f.lower().endswith('.png'):
            item.add_asset('thumbnail', pystac.Asset(href=href, media_type=pystac.MediaType.PNG, roles=['thumbnail']))
        elif f.lower().endswith('.xml'):
            item.add_asset('metadata_xml', pystac.Asset(href=href, media_type=pystac.MediaType.XML, roles=['metadata']))

    # --- ETAPA 5: ADICIONAR ITEM À COLEÇÃO ---
    current_collection.add_item(item)

    # --- ETAPA DE FINALIZAÇÃO: ATUALIZAR EXTENSÕES ---
print("\nAtualizando a extensão espacial e temporal de cada coleção com base nos seus itens...")
for collection in collections.values():
    try:
        collection.update_extent_from_items()
        print(f"  - Extensão da coleção '{collection.id}' atualizada com sucesso.")
    except Exception as e:
        print(f"  - AVISO: Não foi possível atualizar a extensão para a coleção '{collection.id}'. Erro: {e}")

# --- ETAPA FINAL: NORMALIZAR E SALVAR O CATÁLOGO ---

print("\nNormalizando os links e salvando o catálogo...")
catalog.normalize_hrefs(root_href=catalog_dir)
catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

print("\n--- PROCESSO CONCLUÍDO ---")