# 전문(Full Text) 접근 방법

## 개요

문헌의 전문(full text)을 확보하는 3가지 경로:

| 경로 | 대상 | 형식 | 장점 | 제한 |
|------|------|------|------|------|
| PMC XML API | PubMed Central OA 논문 | 구조화된 XML | 섹션 자동 분리 | OA 논문만 |
| bioRxiv PDF | bioRxiv/medRxiv 프리프린트 | PDF → 마크다운 | 프리프린트 전체 커버 | 섹션 분리 휴리스틱 |
| 사용자 제공 PDF | 모든 논문 | PDF → 마크다운 | 제한 없음 | 수동 제공 필요 |

## 1. PMC XML API

### API 엔드포인트

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
  ?db=pmc
  &id={PMCID}        # PMC1234567 (숫자만)
  &rettype=xml
```

### Rate Limiting
- API key 없이: 3 requests/second
- API key 사용: 10 requests/second
- API key 발급: https://www.ncbi.nlm.nih.gov/account/settings/

### XML 구조 파싱

```python
from lxml import etree

tree = etree.parse(xml_file)
root = tree.getroot()
article = root.find('.//article')

# 초록
abstract = article.find('.//abstract')
abstract_text = ' '.join(p.text or '' for p in abstract.findall('.//p'))

# 본문 섹션
body = article.find('.//body')
for sec in body.findall('.//sec'):
    title = sec.find('title')
    section_name = title.text if title is not None else 'unknown'
    paragraphs = sec.findall('.//p')
    text = ' '.join(p.text or '' for p in paragraphs)

# 표
for table_wrap in article.findall('.//table-wrap'):
    label = table_wrap.find('label')
    caption = table_wrap.find('.//caption')

# 그림
for fig in article.findall('.//fig'):
    label = fig.find('label')
    caption = fig.find('.//caption')
```

### 섹션 매핑

PMC XML의 `<sec sec-type="...">` 속성 값:

| sec-type 값 | 매핑 |
|-------------|------|
| `intro`, `introduction` | introduction |
| `methods`, `materials`, `materials|methods` | methods |
| `results` | results |
| `discussion` | discussion |
| `conclusions` | discussion (결론 병합) |
| `supplementary-material` | supplementary |
| 없음 | 제목 텍스트로 휴리스틱 매핑 |

## 2. bioRxiv PDF

### PDF 다운로드 URL

```
# 최신 버전
https://www.biorxiv.org/content/{doi}v{version}.full.pdf
# 예: https://www.biorxiv.org/content/10.1101/2024.01.15.123456v1.full.pdf

# medRxiv
https://www.medrxiv.org/content/{doi}v{version}.full.pdf
```

### 버전 확인

bioRxiv API로 최신 버전 확인:
```
GET https://api.biorxiv.org/details/biorxiv/{doi}
```

### PDF → 마크다운 변환

**방법 1: markitdown (권장)**
```python
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert("paper.pdf")
markdown_text = result.text_content
```

**방법 2: pypdf (폴백)**
```python
from pypdf import PdfReader
reader = PdfReader("paper.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"
```

### 섹션 분리 휴리스틱

PDF에서 변환된 텍스트의 섹션 분리:

```python
import re

SECTION_PATTERNS = [
    (r'(?i)^#{1,3}\s*(?:1\.?\s*)?introduction', 'introduction'),
    (r'(?i)^#{1,3}\s*(?:2\.?\s*)?(?:materials?\s+and\s+)?methods?', 'methods'),
    (r'(?i)^#{1,3}\s*(?:3\.?\s*)?results?', 'results'),
    (r'(?i)^#{1,3}\s*(?:4\.?\s*)?discussion', 'discussion'),
    (r'(?i)^#{1,3}\s*(?:5\.?\s*)?conclusions?', 'discussion'),
    (r'(?i)^#{1,3}\s*references', 'references'),
    (r'(?i)^#{1,3}\s*(?:supplementa|supporting)', 'supplementary'),
]

# 또는 대문자 제목 패턴 (PDF에서 흔함)
UPPERCASE_PATTERNS = [
    (r'^INTRODUCTION\s*$', 'introduction'),
    (r'^(?:MATERIALS?\s+AND\s+)?METHODS?\s*$', 'methods'),
    (r'^RESULTS?\s*$', 'results'),
    (r'^DISCUSSION\s*$', 'discussion'),
]
```

## 3. 사용자 제공 PDF

### 파일 매칭

```python
# DOI 기반 매칭 (파일명에서 / → _)
# 예: 10.1038_s41586-024-07000-0.pdf
doi_safe = doi.replace("/", "_").replace(":", "_")
pdf_path = os.path.join(local_dir, f"{doi_safe}.pdf")

# 제목 기반 매칭 (유사도)
from difflib import SequenceMatcher
for pdf_file in os.listdir(local_dir):
    name = os.path.splitext(pdf_file)[0].replace("_", " ").replace("-", " ")
    ratio = SequenceMatcher(None, name.lower(), title.lower()).ratio()
    if ratio > 0.8:
        matched = True
```

## 4. Fallback: 초록만 사용

전문 접근 불가 시:

```json
{
  "doi": "10.1234/...",
  "full_text_available": false,
  "source_type": "abstract_only",
  "sections": {
    "abstract": "논문 초록 텍스트..."
  },
  "confidence_penalty": -0.2
}
```

- 모든 추출 결과의 confidence에 -0.2 페널티 적용
- `full_text_available: false` 메타데이터 기록
- 패널에 초록만 사용된 논문 목록 전달

## 5. 전문 수집 통계 예시

```
전문 수집 결과:
  총 논문: 50편
  PMC XML 전문: 28편 (56%)
  bioRxiv PDF: 8편 (16%)
  사용자 PDF: 3편 (6%)
  초록만: 11편 (22%)

  섹션 분리 성공: 36/39 (92%)
  표/그림 캡션 추출: 24편
```
