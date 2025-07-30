# Importa as bibliotecas necessárias
import pystac
from datetime import datetime
import os
import shutil
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, mapping
import math # Importado para verificar valores NaN

# --- CONFIGURAÇÃO ---
# root_url = 'http://localhost/meu-stac'
root_url = 'http://172.21.5.20/meu-stac'
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
    if root == source_dir:
        continue

    primary_tif_file = next((f for f in files if f.lower().endswith(('.tif', '.tiff')) and 'grd' in f.lower()), None)
    if not primary_tif_file:
        print(f"  - AVISO: Nenhum arquivo TIF do tipo GRD encontrado em '{root}'. Pulando.")
        continue

    print(f"\n> Processando diretório: {os.path.basename(root)}")

    collection_id = os.path.relpath(root, source_dir).split(os.sep)[0]
    if collection_id not in collections:
        print(f"  > Criando nova coleção: {collection_id}")
        new_collection = pystac.Collection(
            id=collection_id, description=f'Imagens da coleção {collection_id}.',
            extent=pystac.Extent(spatial=pystac.SpatialExtent([-180, -90, 180, 90]), temporal=pystac.TemporalExtent([[datetime(2025, 1, 1), None]])))
        catalog.add_child(new_collection)
        collections[collection_id] = new_collection
    current_collection = collections[collection_id]
        
    base_name = os.path.splitext(primary_tif_file)[0]
    
    geometry, bbox = None, None
    item_datetime = datetime.utcnow()
    properties = {}
    
    xml_file = next((os.path.join(root, f) for f in files if f.lower().endswith('.xml') and 'grd' in f.lower()), None)
    if xml_file:
        print(f"  > Lendo metadados de: {os.path.basename(xml_file)}")
        try:
            tree = ET.parse(xml_file)
            xml_root = tree.getroot()
            ns = {}

            # --- SEÇÃO DE METADADADOS RESTAURADA ---
            # Estas linhas haviam sido removidas por engano e agora foram restauradas.
            if (el := xml_root.find('.//satellite_name')) is not None: properties['platform'] = el.text
            if (el := xml_root.find('.//acquisition_start_utc')) is not None: item_datetime = datetime.fromisoformat(el.text.replace('Z', ''))
            if (el := xml_root.find('.//acquisition_end_utc')) is not None: properties['end_datetime'] = el.text
            if (el := xml_root.find('.//acquisition_mode')) is not None: properties['acquisition_mode'] = el.text
            if (el := xml_root.find('.//look_side')) is not None: properties['view:off_nadir'] = el.text
            if (el := xml_root.find('.//orbit_direction')) is not None: properties['sat:orbit_state'] = el.text.lower()
            if (el := xml_root.find('.//incidence_center')) is not None: properties['view:incidence_angle'] = float(el.text)
            if (el := xml_root.find('.//polarization')) is not None: properties['sar:polarizations'] = [p.strip() for p in el.text.split(',')]
            if (el := xml_root.find('.//product_file')) is not None: properties['product_name'] = el.text
            
            el_centro = xml_root.find('.//coord_center', ns)
            if el_centro is not None and el_centro.text is not None:
                parts = el_centro.text.split()
                if len(parts) >= 2:
                    lon, lat = float(parts[-1]), float(parts[-2])
                    properties['centroid'] = {'lon': lon, 'lat': lat}
                    print(f"      > Metadado 'centroid' extraído: lon={lon}, lat={lat}")

            # Seção de Geometria (com a correção do JSON)
            try:
                print("    > Extraindo geometria dos 4 cantos...")
                def get_corner_text(tag_name):
                    element = xml_root.find(f'.//{tag_name}', ns)
                    return element.text if element is not None and element.text is not None else None

                text_canto_se = get_corner_text('coord_first_far')
                text_canto_sd = get_corner_text('coord_first_near')
                text_canto_id = get_corner_text('coord_last_near')
                text_canto_ie = get_corner_text('coord_last_far')

                if all([text_canto_se, text_canto_sd, text_canto_id, text_canto_ie]):
                    canto_se = [float(text_canto_se.split()[3]), float(text_canto_se.split()[2])]
                    canto_sd = [float(text_canto_sd.split()[3]), float(text_canto_sd.split()[2])]
                    canto_id = [float(text_canto_id.split()[3]), float(text_canto_id.split()[2])]
                    canto_ie = [float(text_canto_ie.split()[3]), float(text_canto_ie.split()[2])]
                    coords = [canto_se, canto_sd, canto_id, canto_ie, canto_se]
                    
                    polygon = Polygon(coords)
                    geometry = mapping(polygon)
                    bbox = list(polygon.bounds)
                    
                    if any(math.isnan(coord) for coord in bbox):
                        print("    - ERRO: Bounding box inválido (NaN) detectado. A geometria será descartada.")
                        geometry, bbox = None, None
                    else:
                        print("      > SUCESSO: Geometria e Bounding Box criados.")
                        properties.update({
                            'corner:first_far': text_canto_se.strip(), 'corner:first_near': text_canto_sd.strip(),
                            'corner:last_near': text_canto_id.strip(), 'corner:last_far': text_canto_ie.strip()
                        })

            except Exception as geo_e:
                print(f"    - ERRO CRÍTICO ao extrair geometria: {geo_e}")
        except Exception as e:
            print(f"    - ERRO: Falha crítica ao processar o arquivo XML: {e}")

    # ETAPA 3: CRIAR O ITEM STAC
    item = pystac.Item(id=base_name, geometry=geometry, bbox=bbox, datetime=item_datetime, properties=properties)

    if any(key.startswith(p) for p in ['sar:', 'view:', 'sat:'] for key in properties):
        for ext in ['sar', 'view', 'sat']: 
            ext_url = f'https://stac-extensions.github.io/{ext}/v1.0.0/schema.json'
            if ext_url not in item.stac_extensions:
                item.stac_extensions.append(ext_url)
    if 'platform' in item.properties: 
        item.common_metadata.platform = item.properties.pop('platform')
    
    # ETAPA 4: ADICIONAR ASSETS
    print(f"  > Adicionando todos os arquivos como assets para o item: {item.id}")
    for f in files:
        url_path = os.path.relpath(os.path.join(root, f), source_dir).replace('\\', '/')
        href = f"{root_url}/imagens_organizadas_por_satelite/{url_path}"
        filename_lower = f.lower()
        asset_key = os.path.splitext(filename_lower)[0].replace(base_name.lower(), '').strip('-_')
        media_type, roles = 'application/octet-stream', ['metadata']
        
        if filename_lower.endswith(('.tif', '.tiff')):
            if 'grd' in filename_lower: asset_key, roles, media_type = 'data', ['data'], pystac.MediaType.COG
            elif 'quickortho' in filename_lower: asset_key, roles, media_type = 'quickortho_tif', ['visual'], pystac.MediaType.COG
        elif filename_lower.endswith('.png'):
            if 'quicklook' in filename_lower or 'thumbnail' in filename_lower: asset_key, roles, media_type = 'thumbnail', ['thumbnail'], pystac.MediaType.PNG
        elif filename_lower.endswith('.xml'):
            if 'grd' in filename_lower: asset_key = 'metadata_grd_xml'
            elif 'slc' in filename_lower: asset_key = 'metadata_slc_xml'
            media_type = pystac.MediaType.XML
        elif filename_lower.endswith('.kml'):
            if 'quicklook' in filename_lower: asset_key = 'quicklook_kml'
            elif 'thumbnail' in filename_lower: asset_key = 'thumbnail_kml'
            media_type = 'application/vnd.google-earth.kml+xml'
        elif filename_lower.endswith('.kmz'): asset_key, media_type = 'quickortho_kmz', 'application/vnd.google-earth.kmz'
        elif filename_lower.endswith('.h5'): asset_key, media_type = 'data_slc_h5', 'application/x-hdf5'
        elif filename_lower.endswith('.json'): asset_key, media_type = 'thumbnail_json', pystac.MediaType.JSON
        else: asset_key = os.path.splitext(filename_lower)[0]

        if asset_key and asset_key not in item.assets:
            item.add_asset(key=asset_key, asset=pystac.Asset(href=href, media_type=media_type, roles=roles, title=f))

    # ETAPA 5: ADICIONAR ITEM À COLEÇÃO
    current_collection.add_item(item)

# ETAPAS FINAIS
print("\nAtualizando a extensão espacial e temporal de cada coleção...")
for collection in collections.values():
    collection.update_extent_from_items()

print("\nNormalizando os links e salvando o catálogo...")
catalog.normalize_hrefs(root_href=catalog_dir)
catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

print("\n--- PROCESSO CONCLUÍDO ---")