import osmnx as ox
import networkx as nx
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError
import folium
import random
from shapely.geometry import LineString
from shapely.ops import linemerge
import os
from flask import Flask, request, render_template, jsonify
import time

app = Flask(__name__)

graph_filename = 'sao_paulo_graph.graphml'

if os.path.isfile(graph_filename):
    G = ox.load_graphml(graph_filename)
    print("Grafo carregado a partir do cache.")
else:
    cidade = 'São Paulo, Brazil'
    G = ox.graph_from_place(cidade, network_type='drive')
    ox.save_graphml(G, graph_filename)
    print("Grafo baixado e salvo em cache.")

# mantém apenas o maior componente conectado
if nx.is_directed(G):
    maior_comp = max(nx.weakly_connected_components(G), key=len)
else:
    maior_comp = max(nx.connected_components(G), key=len)
G = G.subgraph(maior_comp).copy()
print(f"Grafo filtrado para maior componente: {len(G.nodes)} nós, {len(G.edges)} arestas.")

edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
edges.reset_index(inplace=True)
edges['congestionamento'] = [random.randint(0, 100) for _ in range(len(edges))]
edges['weight'] = edges['congestionamento']
edge_weights = edges.set_index(['u', 'v', 'key'])['weight'].to_dict()
nx.set_edge_attributes(G, edge_weights, 'weight')

geolocator = Nominatim(user_agent="sistema_trafego_alexssandro_2026")

def endereco_para_coordenada(endereco):
    if "são paulo" not in endereco.lower():
        endereco = f"{endereco}, São Paulo, SP, Brasil"

    for tentativa in range(3):
        try:
            location = geolocator.geocode(
                endereco,
                timeout=12,
                exactly_one=True,
                country_codes="br",
                addressdetails=True
            )
            if location:
                return (location.latitude, location.longitude)

            print(f"Geocoding sem resultado: '{endereco}'")
            return None

        except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
            print(f"Geocoding falhou (tentativa {tentativa + 1}/3): {e}")
            time.sleep(1.2 * (tentativa + 1))

    return None

def melhor_rota(G, origem, destino):
    if origem is None or destino is None:
        print("Erro: origem/destino inválidos.")
        return []

    try:
        origem_node = ox.distance.nearest_nodes(G, X=origem[1], Y=origem[0])
        destino_node = ox.distance.nearest_nodes(G, X=destino[1], Y=destino[0])
        print(f"origem_node={origem_node}, destino_node={destino_node}")

        # 1) tenta direcionado
        try:
            return nx.shortest_path(
                G, source=origem_node, target=destino_node, weight="weight", method="dijkstra"
            )
        except nx.NetworkXNoPath:
            print("Sem caminho no grafo direcionado.")

        # 2) fallback não direcionado
        try:
            G_u = G.to_undirected()
            return nx.shortest_path(
                G_u, source=origem_node, target=destino_node, weight="weight", method="dijkstra"
            )
        except nx.NetworkXNoPath:
            print("Sem caminho também no grafo não direcionado.")
            return []

    except Exception as e:
        print(f"Erro ao calcular a melhor rota: {type(e).__name__} - {e}")
        return []

def pintar_congestionamento(G, mapa, caminho):
    rota_linhas = []
    for i in range(len(caminho)-1):
        rua1 = G.nodes[caminho[i]]
        rua2 = G.nodes[caminho[i+1]]
        rota_linhas.append(LineString([(rua1['x'], rua1['y']), (rua2['x'], rua2['y'])]))
    rota_geom = linemerge(rota_linhas)
    rota_buffer = rota_geom.buffer(0.01)
    edges_gdf = ox.graph_to_gdfs(G, nodes=False)
    edges_gdf.reset_index(inplace=True)
    nearby_edges = edges_gdf[edges_gdf.intersects(rota_buffer)]
    for idx, edge in nearby_edges.iterrows():
        congestionamento = edge['weight']
        if congestionamento < 25:
            cor = 'gray'
        elif 25 <= congestionamento <= 50:
            cor = 'yellow'
        else:
            cor = 'red'
        coords = list(edge['geometry'].coords)
        nome_rua = edge.get('name', 'Rua desconhecida')
        tooltip = f"{nome_rua}: {congestionamento}% de congestionamento"
        folium.PolyLine(
            [(coord[1], coord[0]) for coord in coords],
            color=cor,
            weight=4,
            opacity=0.5,
            tooltip=tooltip
        ).add_to(mapa)

def exibir_rota_no_mapa(G, caminho, origem, destino):
    if not caminho:
        print("Não há caminho válido para exibir no mapa.")
        return
    mapa = folium.Map(location=[origem[0], origem[1]], zoom_start=14)
    pintar_congestionamento(G, mapa, caminho)
    folium.Marker([origem[0], origem[1]], popup="Origem").add_to(mapa)
    folium.Marker([destino[0], destino[1]], popup="Destino").add_to(mapa)
    rota_coords = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in caminho]
    tooltip_rota = "Rota sugerida"
    folium.PolyLine(
        rota_coords,
        color='blue',
        weight=7,
        opacity=1,
        tooltip=tooltip_rota
    ).add_to(mapa)
    return mapa._repr_html_()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rota', methods=['POST'])
def rota():
    origem_endereco = request.form.get('origem', '').strip()
    destino_endereco = request.form.get('destino', '').strip()

    if not origem_endereco or not destino_endereco:
        return jsonify({"error": "Informe origem e destino."}), 400

    origem = endereco_para_coordenada(origem_endereco)
    destino = endereco_para_coordenada(destino_endereco)

    if origem is None or destino is None:
        return jsonify({
            "error": "Falha ao localizar endereço (Nominatim). Tente novamente em alguns segundos e use: rua, número, bairro."
        }), 400

    caminho = melhor_rota(G, origem, destino)
    if not caminho:
        return jsonify({
            "error": "Endereços localizados, mas não foi possível calcular rota entre os pontos."
        }), 404

    mapa_html = exibir_rota_no_mapa(G, caminho, origem, destino)
    if not mapa_html:
        return jsonify({"error": "Não foi possível gerar o mapa da rota."}), 500

    return mapa_html

if __name__ == '__main__':
    app.run(debug=True)
