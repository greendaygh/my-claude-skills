# Cypher 쿼리 템플릿 라이브러리

## 1. 기본 통계

```cypher
// 노드 수 (라벨별)
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC;

// 관계 수 (타입별)
MATCH ()-[r]->()
RETURN type(r) AS type, count(r) AS count
ORDER BY count DESC;

// 전체 그래프 요약
MATCH (n)
WITH count(n) AS totalNodes
MATCH ()-[r]->()
WITH totalNodes, count(r) AS totalRels
RETURN totalNodes, totalRels;
```

## 2. 논문 (Paper) 쿼리

```cypher
// 전문 가용 논문 비율
MATCH (p:Paper)
RETURN p.full_text_available AS has_fulltext, count(p) AS count;

// 연도별 논문 분포
MATCH (p:Paper)
RETURN p.year AS year, count(p) AS papers
ORDER BY year;

// 가장 많은 엔티티를 산출한 논문
MATCH (p:Paper)<-[:EXTRACTED_FROM]-(n)
RETURN p.title, p.doi, count(n) AS entity_count
ORDER BY entity_count DESC
LIMIT 10;

// 특정 논문에서 추출된 모든 엔티티/관계
MATCH (p:Paper {doi: $doi})<-[ef:EXTRACTED_FROM]-(n)
RETURN labels(n)[0] AS type, n.name AS name, ef.confidence AS confidence, ef.source_section AS section;
```

## 3. 이웃 탐색

```cypher
// 1홉 이웃
MATCH (n {name: $name})-[r]-(m)
RETURN labels(m)[0] AS type, m.name AS name, type(r) AS relationship,
       CASE WHEN startNode(r) = n THEN '→' ELSE '←' END AS direction
ORDER BY type;

// N홉 이웃 (깊이 제한)
MATCH path = (n {name: $name})-[*1..$depth]-(m)
WHERE n <> m
RETURN DISTINCT labels(m)[0] AS type, m.name AS name, length(path) AS distance
ORDER BY distance, type;

// 특정 관계 타입으로 연결된 이웃
MATCH (n {name: $name})-[r:$relType]-(m)
RETURN m.name, type(r), r.confidence
ORDER BY r.confidence DESC;
```

## 4. 경로 탐색

```cypher
// 두 노드 간 최단 경로
MATCH path = shortestPath((a {name: $nameA})-[*..10]-(b {name: $nameB}))
RETURN [n IN nodes(path) | n.name] AS node_names,
       [r IN relationships(path) | type(r)] AS rel_types,
       length(path) AS hops;

// 모든 최단 경로 (여러 개)
MATCH path = allShortestPaths((a {name: $nameA})-[*..10]-(b {name: $nameB}))
RETURN [n IN nodes(path) | n.name] AS node_names,
       [r IN relationships(path) | type(r)] AS rel_types;

// 특정 노드를 경유하는 경로
MATCH path = shortestPath((a {name: $nameA})-[*..5]-(via {name: $nameVia}))
MATCH path2 = shortestPath((via)-[*..5]-(b {name: $nameB}))
RETURN path, path2;
```

## 5. 중심성 분석

```cypher
// Degree centrality (관계 수 기준)
MATCH (n)-[r]-()
WHERE NOT n:Paper
RETURN labels(n)[0] AS type, n.name AS name, count(r) AS degree
ORDER BY degree DESC
LIMIT 20;

// Betweenness centrality (GDS 필요)
CALL gds.betweenness.stream({
  nodeProjection: '*',
  relationshipProjection: {ALL: {type: '*', orientation: 'UNDIRECTED'}}
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WHERE NOT node:Paper
RETURN labels(node)[0] AS type, node.name AS name, score
ORDER BY score DESC
LIMIT 20;

// PageRank (GDS 필요)
CALL gds.pageRank.stream({
  nodeProjection: '*',
  relationshipProjection: {ALL: {type: '*', orientation: 'UNDIRECTED'}}
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WHERE NOT node:Paper
RETURN labels(node)[0] AS type, node.name AS name, score
ORDER BY score DESC
LIMIT 20;
```

## 6. 커뮤니티 탐지 (GDS 필요)

```cypher
// Louvain 커뮤니티
CALL gds.louvain.stream({
  nodeProjection: '*',
  relationshipProjection: {ALL: {type: '*', orientation: 'UNDIRECTED'}}
})
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS node, communityId
WHERE NOT node:Paper
RETURN communityId, collect(node.name) AS members, count(*) AS size
ORDER BY size DESC
LIMIT 20;

// Label Propagation
CALL gds.labelPropagation.stream({
  nodeProjection: '*',
  relationshipProjection: {ALL: {type: '*', orientation: 'UNDIRECTED'}}
})
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS node, communityId
WHERE NOT node:Paper
RETURN communityId, count(*) AS size, collect(node.name)[..5] AS sample_members
ORDER BY size DESC;
```

## 7. 패턴 탐색

```cypher
// 삼각형 패턴 (A→B, B→C, A→C)
MATCH (a)-[r1]->(b)-[r2]->(c)-[r3]->(a)
WHERE NOT a:Paper AND NOT b:Paper AND NOT c:Paper
RETURN a.name, type(r1), b.name, type(r2), c.name, type(r3)
LIMIT 20;

// 허브 노드 (높은 degree + 다양한 관계 타입)
MATCH (n)-[r]-()
WHERE NOT n:Paper
WITH n, count(r) AS degree, collect(DISTINCT type(r)) AS rel_types
WHERE degree > 5
RETURN labels(n)[0] AS type, n.name, degree, rel_types
ORDER BY degree DESC;

// 약물-표적-질환 삼각관계
MATCH (d:Drug)-[:TARGETS]->(p:Protein)<-[:ASSOCIATED_WITH]-(g:Gene)-[:ASSOCIATED_WITH]->(dis:Disease)
WHERE (d)-[:TREATS]->(dis)
RETURN d.name AS drug, p.name AS target, g.name AS gene, dis.name AS disease;
```

## 8. 신뢰도/출처 분석

```cypher
// 신뢰도별 분포
MATCH ()-[ef:EXTRACTED_FROM]->()
RETURN
  CASE
    WHEN ef.confidence >= 0.8 THEN 'high'
    WHEN ef.confidence >= 0.5 THEN 'medium'
    ELSE 'low'
  END AS confidence_level,
  count(*) AS count;

// 사이클별 추출 결과 비교
MATCH ()-[ef:EXTRACTED_FROM]->()
RETURN ef.extraction_cycle AS cycle, count(*) AS extractions,
       avg(ef.confidence) AS avg_confidence;

// 패널 검증 상태
MATCH ()-[ef:EXTRACTED_FROM]->()
RETURN ef.panel_verified AS verified, count(*) AS count,
       avg(ef.panel_confidence) AS avg_panel_confidence;

// 섹션별 추출 분포
MATCH ()-[ef:EXTRACTED_FROM]->()
RETURN ef.source_section AS section, count(*) AS count,
       avg(ef.confidence) AS avg_confidence
ORDER BY count DESC;
```

## 9. 내보내기용 쿼리

```cypher
// 전체 그래프 (Paper 제외)
MATCH (a)-[r]->(b)
WHERE NOT a:Paper AND NOT b:Paper AND NOT type(r) = 'EXTRACTED_FROM'
RETURN labels(a)[0] AS source_type, a.name AS source,
       type(r) AS relationship,
       labels(b)[0] AS target_type, b.name AS target;

// 특정 엔티티 타입만
MATCH (a:Gene)-[r]->(b)
WHERE NOT b:Paper
RETURN a.name AS gene, type(r) AS relationship, labels(b)[0] AS target_type, b.name AS target;
```

## 10. 전문 검색 (Full-text index)

```cypher
// 전문 검색 인덱스 생성 (1회)
CREATE FULLTEXT INDEX paperSearch FOR (p:Paper) ON EACH [p.title, p.abstract];

// 키워드 검색
CALL db.index.fulltext.queryNodes('paperSearch', 'CRISPR delivery')
YIELD node, score
RETURN node.title, node.doi, score
ORDER BY score DESC
LIMIT 10;
```
