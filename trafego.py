import osmnx as ox
import networkx as nx
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import folium
import random
from shapely.geometry import LineString
from shapely.ops import linemerge
import os
from flask import Flask, request, render_template, jsonify

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

edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
edges.reset_index(inplace=True)
edges['congestionamento'] = [random.randint(0, 100) for _ in range(len(edges))]
edges['weight'] = edges['congestionamento']
edge_weights = edges.set_index(['u', 'v', 'key'])['weight'].to_dict()
nx.set_edge_attributes(G, edge_weights, 'weight')

geolocator = Nominatim(user_agent="sistema_trafego")

def endereco_para_coordenada(endereco):
    try:
        location = geolocator.geocode(endereco, timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            print(f"Erro: Não foi possível encontrar o endereço '{endereco}'.")
            return None, None
    except GeocoderTimedOut:
        print(f"Erro: Tempo esgotado ao tentar geocodificar o endereço '{endereco}'.")
        return None, None

def melhor_rota(G, origem, destino):
    if origem is None or destino is None:
        print("Erro: Não foi possível obter as coordenadas de origem ou destino.")
        return []
    try:
        origem_node = ox.distance.nearest_nodes(G, X=origem[1], Y=origem[0])
        destino_node = ox.distance.nearest_nodes(G, X=destino[1], Y=destino[0])
        caminho = nx.astar_path(G, source=origem_node, target=destino_node, weight='weight')
        return caminho
    except Exception as e:
        print(f"Erro ao calcular a melhor rota: {e}")
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
    origem_endereco = request.form['origem']
    destino_endereco = request.form['destino']
    origem = endereco_para_coordenada(origem_endereco)
    destino = endereco_para_coordenada(destino_endereco)
    if origem and destino:
        caminho = melhor_rota(G, origem, destino)
        mapa_html = exibir_rota_no_mapa(G, caminho, origem, destino)
        return mapa_html
    else:
        return jsonify({"error": "Erro ao obter as coordenadas de um ou ambos os endereços."}), 400

if __name__ == '__main__':
    app.run(debug=True)
