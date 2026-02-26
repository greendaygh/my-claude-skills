# Neo4j 설치 및 설정 가이드

## Docker 설치 (권장)

```bash
# Neo4j Community Edition
docker run -d \
  --name neo4j-kg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  -e NEO4J_PLUGINS='["graph-data-science"]' \
  -e NEO4J_dbms_memory_heap_initial__size=512m \
  -e NEO4J_dbms_memory_heap_max__size=2G \
  -e NEO4J_dbms_memory_pagecache_size=1G \
  -v neo4j-data:/data \
  -v neo4j-logs:/logs \
  neo4j:5-community
```

## 연결 확인

```bash
# 브라우저 접속
open http://localhost:7474

# Python 드라이버 테스트
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'your_password'))
with driver.session() as session:
    result = session.run('RETURN 1 AS test')
    print(result.single()['test'])
driver.close()
"
```

## 메모리 설정 가이드

| 그래프 크기 | heap_max | pagecache | 권장 RAM |
|------------|----------|-----------|---------|
| < 1만 노드 | 1G | 512m | 4GB |
| 1만-10만 | 2G | 1G | 8GB |
| 10만-100만 | 4G | 2G | 16GB |
| > 100만 | 8G+ | 4G+ | 32GB+ |

## GDS (Graph Data Science) 플러그인

커뮤니티 탐지, 중심성 분석에 필요:

```bash
# Docker에서 자동 설치
-e NEO4J_PLUGINS='["graph-data-science"]'

# 수동 설치
# 1. https://neo4j.com/download-center/#community 에서 GDS 다운로드
# 2. plugins/ 디렉토리에 복사
# 3. neo4j.conf에 추가: dbms.security.procedures.unrestricted=gds.*
```

## 스키마 초기화 (setup_neo4j.py)

```bash
# 기본 사용
python scripts/setup_neo4j.py \
  --password your_password \
  --schema assets/schema_template.json

# 기존 스키마 리셋 후 재생성
python scripts/setup_neo4j.py \
  --password your_password \
  --schema assets/schema_template.json \
  --reset
```

## 유용한 관리 Cypher

```cypher
-- 모든 제약조건 확인
SHOW CONSTRAINTS;

-- 모든 인덱스 확인
SHOW INDEXES;

-- 노드/관계 수 확인
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count;
MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count;

-- 데이터베이스 전체 삭제 (주의!)
MATCH (n) DETACH DELETE n;
```

## 백업

```bash
# Docker 볼륨 백업
docker run --rm -v neo4j-data:/data -v $(pwd):/backup \
  busybox tar czf /backup/neo4j-backup.tar.gz /data

# 복원
docker run --rm -v neo4j-data:/data -v $(pwd):/backup \
  busybox tar xzf /backup/neo4j-backup.tar.gz -C /
```

## 문제 해결

- **연결 거부**: `docker logs neo4j-kg`로 로그 확인, 포트 충돌 체크
- **메모리 부족**: heap/pagecache 설정 조정
- **느린 쿼리**: `EXPLAIN` / `PROFILE` 사용, 인덱스 확인
- **GDS 미설치**: `RETURN gds.version()` 실행하여 확인, 없으면 NetworkX 폴백 사용
