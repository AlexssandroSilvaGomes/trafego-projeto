# Descrição Detalhada do Programa de Tráfego Urbano

## Introdução

Este programa em Python calcula a melhor rota entre dois endereços na cidade de São Paulo, considerando o congestionamento das vias. Ele gera um mapa interativo que exibe a rota sugerida e as ruas próximas, coloridas de acordo com o nível de congestionamento. Ao passar o mouse sobre as ruas, o usuário pode visualizar a porcentagem de congestionamento e o nome da rua.

## Bibliotecas Utilizadas

- **osmnx**: Extração e manipulação de dados geoespaciais do OpenStreetMap.
- **networkx**: Criação e manipulação de grafos complexos.
- **geopy**: Geocodificação para converter endereços em coordenadas geográficas.
- **folium**: Geração de mapas interativos em HTML.
- **random**: Geração de números aleatórios.
- **shapely**: Manipulação de objetos geométricos (linhas, polígonos, etc.).
- **os**: Interação com o sistema operacional (verificação de arquivos).

## Passo a Passo do Programa

### 1. Importação das Bibliotecas

O programa começa importando todas as bibliotecas necessárias para sua execução.

### 2. Configuração do Cache do Grafo

- Define o nome do arquivo de cache para armazenar o grafo das ruas de São Paulo: `sao_paulo_graph.graphml`.
- Verifica se o arquivo de cache existe:
  - **Se existir**: Carrega o grafo a partir do arquivo local.
  - **Se não existir**: Baixa o grafo do OpenStreetMap e salva em cache.

```python
graph_filename = 'sao_paulo_graph.graphml'

if os.path.isfile(graph_filename):
    G = ox.load_graphml(graph_filename)
    print("Grafo carregado a partir do cache.")
else:
    cidade = 'São Paulo, Brazil'
    G = ox.graph_from_place(cidade, network_type='drive')
    ox.save_graphml(G, graph_filename)
    print("Grafo baixado e salvo em cache.")
```

### 3. Preparação dos Dados

- Converte o grafo em um GeoDataFrame de arestas utilizando `osmnx.graph_to_gdfs`.
- Reseta o índice do GeoDataFrame para que as colunas `'u'`, `'v'` e `'key'` estejam acessíveis.

```python
edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
edges.reset_index(inplace=True)
```

### 4. Simulação de Congestionamento

- Gera um valor aleatório de congestionamento entre 0% e 100% para cada aresta (rua).
- Atribui esse valor ao atributo `'congestionamento'` do GeoDataFrame.

```python
edges['congestionamento'] = [random.randint(0, 100) for _ in range(len(edges))]
```

### 5. Atribuição de Pesos às Arestas

- Define o atributo `'weight'` das arestas como sendo igual ao congestionamento.
- Cria um dicionário mapeando cada aresta ao seu peso.
- Atualiza os atributos do grafo com os novos pesos usando `nx.set_edge_attributes`.

```python
edges['weight'] = edges['congestionamento']
edge_weights = edges.set_index(['u', 'v', 'key'])['weight'].to_dict()
nx.set_edge_attributes(G, edge_weights, 'weight')
```

### 6. Geocodificação de Endereços

Define a função `endereco_para_coordenada` para converter endereços em coordenadas geográficas usando o Nominatim do `geopy`.

```python
def endereco_para_coordenada(endereco):
    geolocator = Nominatim(user_agent="sistema_trafego")
    location = geolocator.geocode(endereco)
    if location:
        return location.latitude, location.longitude
    else:
        return None, None
```

### 7. Cálculo da Melhor Rota

Define a função `melhor_rota` para calcular a rota mais eficiente entre a origem e o destino, considerando os pesos (congestionamento) das arestas.

- Encontra os nós mais próximos das coordenadas de origem e destino.
- Utiliza o algoritmo A* para encontrar o caminho mais curto com base no peso.

```python
def melhor_rota(G, origem, destino):
    if origem is None or destino is None:
        print("Erro: Não foi possível obter as coordenadas de origem ou destino.")
        return []
    origem_node = ox.distance.nearest_nodes(G, X=origem[1], Y=origem[0])
    destino_node = ox.distance.nearest_nodes(G, X=destino[1], Y=destino[0])
    if origem_node is None or destino_node is None:
        print("Erro: Não foi possível encontrar os nós mais próximos no grafo.")
        return []
    caminho = nx.astar_path(G, source=origem_node, target=destino_node, weight='weight')
    return caminho
```

### 8. Visualização do Congestionamento no Mapa

Define a função `pintar_congestionamento` para adicionar as ruas próximas à rota no mapa, colorindo-as de acordo com o congestionamento e adicionando tooltips interativos.

- Cria uma geometria da rota e um buffer ao seu redor para selecionar as ruas próximas.
- Filtra as ruas que intersectam o buffer.
- Define a cor das ruas com base no congestionamento.
- Adiciona as ruas ao mapa com tooltips exibindo o nome da rua e o congestionamento.

```python
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
            weight=2,
            opacity=0.5,
            tooltip=tooltip
        ).add_to(mapa)
```

### 9. Exibição da Rota no Mapa

Define a função `exibir_rota_no_mapa` para gerar o mapa interativo final.

- Inicializa o mapa centrado na origem.
- Chama `pintar_congestionamento` para adicionar as ruas próximas.
- Adiciona marcadores para a origem e o destino.
- Adiciona a rota calculada com um tooltip indicando "Rota sugerida".

```python
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
        weight=5,
        opacity=1,
        tooltip=tooltip_rota
    ).add_to(mapa)
    mapa.save("rota_completo_sao_paulo.html")
    print("Mapa salvo como 'rota_completo_sao_paulo.html'.")
```

### 10. Interação com o Usuário

Define a função `sistema_trafego` para interagir com o usuário.

- Solicita ao usuário os endereços de origem e destino.
- Converte os endereços em coordenadas geográficas.
- Calcula a melhor rota e exibe o mapa resultante.

```python
def sistema_trafego():
    origem_endereco = input("Digite o endereço de origem: ")
    destino_endereco = input("Digite o endereço de destino: ")
    origem = endereco_para_coordenada(origem_endereco)
    destino = endereco_para_coordenada(destino_endereco)
    if origem and destino:
        caminho = melhor_rota(G, origem, destino)
        exibir_rota_no_mapa(G, caminho, origem, destino)
        print("Rota calculada e salva no mapa.")
    else:
        print("Erro ao obter as coordenadas de um ou ambos os endereços.")
```

### 11. Execução do Programa

O programa é executado chamando a função `sistema_trafego()`.

```python
sistema_trafego()
```

## Como Utilizar o Programa

1. **Instalação das Dependências**: Certifique-se de instalar todas as bibliotecas necessárias, listadas no `requirements.txt`.

2. **Execução**: Execute o script Python em um ambiente adequado.

3. **Interação**: Insira os endereços de origem e destino quando solicitado.

4. **Resultado**: O programa gera um arquivo `rota_completo_sao_paulo.html` que pode ser aberto em um navegador web para visualizar o mapa interativo.

## Personalizações Possíveis

- **Tamanho do Buffer**: Ajuste o valor em `rota_buffer = rota_geom.buffer(0.01)` para aumentar ou diminuir a área de ruas próximas consideradas.

- **Geração de Congestionamento**: Substitua a geração aleatória por dados reais de congestionamento, se disponíveis.

- **Estilo do Mapa**: Personalize cores, opacidades e estilos das linhas e marcadores.

- **Outras Cidades**: Modifique a variável `cidade` para utilizar o programa em outras localidades.

## Conclusão

Este programa integra diversas bibliotecas para oferecer uma solução que calcula rotas otimizadas com base no congestionamento das vias, proporcionando uma visualização interativa e informativa para o usuário.

---