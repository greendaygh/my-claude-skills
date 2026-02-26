# 그래프 시각화 옵션

## 1. Neo4j Browser (내장)

가장 간단한 시각화. Neo4j에 직접 연결.

**접속**: http://localhost:7474

```cypher
// 전체 그래프 (소규모)
MATCH (n)-[r]->(m)
WHERE NOT n:Paper AND NOT m:Paper
RETURN n, r, m LIMIT 200;

// 특정 노드 중심 네트워크
MATCH path = (n {name: "TP53"})-[*1..2]-(m)
WHERE NOT m:Paper
RETURN path;

// 클러스터 시각화
MATCH (n)-[r]->(m)
WHERE labels(n)[0] IN ["Gene", "Disease", "Drug"]
  AND labels(m)[0] IN ["Gene", "Disease", "Drug"]
RETURN n, r, m LIMIT 500;
```

**장점**: 설치 불필요, 인터랙티브, Cypher 직접 실행
**단점**: 대규모 그래프 성능 저하, 커스터마이징 제한

## 2. pyvis (Python 인터랙티브 HTML)

```python
from pyvis.network import Network
import networkx as nx

# NetworkX에서 변환
G = nx.read_graphml("export.graphml")

net = Network(height="800px", width="100%", bgcolor="#222222", font_color="white")

# 노드 색상 (라벨별)
color_map = {
    "Gene": "#e74c3c",
    "Disease": "#3498db",
    "Drug": "#2ecc71",
    "Protein": "#f39c12",
    "Pathway": "#9b59b6",
    "CellType": "#1abc9c"
}

for node, data in G.nodes(data=True):
    label = data.get("label", "Unknown")
    net.add_node(node,
                 label=data.get("name", node),
                 color=color_map.get(label, "#95a5a6"),
                 title=f"{label}: {data.get('name', node)}",
                 size=20)

for u, v, data in G.edges(data=True):
    net.add_edge(u, v,
                 title=data.get("type", ""),
                 label=data.get("type", ""),
                 color="#7f8c8d")

net.toggle_physics(True)
net.show_buttons(filter_=['physics'])
net.save_graph("knowledge_graph.html")
```

**장점**: 인터랙티브, 브라우저 기반, 물리 시뮬레이션
**단점**: 대규모(>1000 노드) 시 느림

## 3. Gephi (데스크톱 도구)

GraphML 내보내기 후 Gephi에서 열기:

```bash
python scripts/export_graph.py \
  --password your_password \
  --format graphml \
  --output knowledge_graph.graphml
```

**Gephi 설정 권장**:
- Layout: ForceAtlas 2 (Overview → Layout)
- Node size: degree 기반 (Appearance → Nodes → Size → Ranking → Degree)
- Node color: label/partition 기반 (Appearance → Nodes → Color → Partition)
- Edge weight: confidence 기반
- Label 표시: 상위 degree 노드만

**장점**: 대규모 그래프 처리, 다양한 레이아웃, 출판 품질
**단점**: 별도 설치 필요, 학습 곡선

## 4. Cytoscape (생의학 네트워크 표준)

Cytoscape JSON 내보내기:

```bash
python scripts/export_graph.py \
  --password your_password \
  --format cytoscape \
  --output knowledge_graph.cyjs
```

**Cytoscape 장점**:
- 생의학 네트워크 분석 표준 도구
- 풍부한 플러그인 생태계 (ClusterMaker, stringApp 등)
- 자동 레이아웃 (force-directed, hierarchical, circular)
- 경로 분석 통합 (KEGG, Reactome)

**Web 버전**: Cytoscape.js로 웹 앱 내장

```html
<div id="cy"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
<script>
fetch('knowledge_graph.cyjs')
  .then(res => res.json())
  .then(data => {
    var cy = cytoscape({
      container: document.getElementById('cy'),
      elements: data.elements,
      style: [
        {selector: 'node', style: {'label': 'data(name)', 'background-color': 'data(color)'}},
        {selector: 'edge', style: {'label': 'data(interaction)', 'curve-style': 'bezier'}}
      ],
      layout: {name: 'cose'}
    });
  });
</script>
```

## 5. NetworkX + Matplotlib (정적 이미지)

```python
import networkx as nx
import matplotlib.pyplot as plt

G = nx.read_graphml("export.graphml")

# 레이아웃
pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

# 노드 색상/크기
node_colors = [color_map.get(G.nodes[n].get('label', ''), '#95a5a6') for n in G.nodes()]
node_sizes = [300 + 100 * G.degree(n) for n in G.nodes()]

plt.figure(figsize=(20, 16))
nx.draw_networkx(G, pos,
    node_color=node_colors,
    node_size=node_sizes,
    font_size=8,
    edge_color='#cccccc',
    alpha=0.8,
    width=0.5)

# 범례
import matplotlib.patches as mpatches
legend_handles = [mpatches.Patch(color=c, label=l) for l, c in color_map.items()]
plt.legend(handles=legend_handles, loc='upper left', fontsize=10)

plt.title("Knowledge Graph", fontsize=16)
plt.tight_layout()
plt.savefig("knowledge_graph.png", dpi=300, bbox_inches='tight')
```

**장점**: 출판 품질 이미지, 완전한 커스터마이징
**단점**: 비인터랙티브, 대규모 그래프 가독성 저하

## 6. 시각화 선택 가이드

| 시나리오 | 권장 도구 | 이유 |
|---------|----------|------|
| 빠른 탐색 | Neo4j Browser | 설치 불필요, Cypher 직접 |
| 인터랙티브 보고서 | pyvis | HTML 파일 공유 용이 |
| 출판/프레젠테이션 | Gephi 또는 Matplotlib | 고품질 정적 이미지 |
| 생의학 분석 | Cytoscape | 도메인 전용 기능 |
| 웹 애플리케이션 | Cytoscape.js | 웹 내장 가능 |
| 대규모 그래프 (>10K) | Gephi | 성능 최적화 |

## 7. 노드 색상 표준

```python
# 생의학 도메인 표준 색상
COLOR_SCHEME = {
    "Gene":       "#e74c3c",  # 빨강
    "Protein":    "#f39c12",  # 주황
    "Disease":    "#3498db",  # 파랑
    "Drug":       "#2ecc71",  # 초록
    "Pathway":    "#9b59b6",  # 보라
    "CellType":   "#1abc9c",  # 청록
    "Organism":   "#34495e",  # 진회색
    "Variant":    "#e67e22",  # 짙은 주황
    "ClinicalTrial": "#16a085", # 짙은 청록
    "Paper":      "#bdc3c7",  # 연회색 (provenance)
}
```
