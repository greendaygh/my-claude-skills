"""Shared fixtures for prophage-miner tests."""

import json
import shutil
from pathlib import Path

import pytest

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


@pytest.fixture
def tmp_phage_dir(tmp_path):
    """Create standard ~/dev/phage/ directory structure in tmp."""
    for d in (
        "00_config",
        "01_papers/full_texts",
        "02_extractions/per_paper",
        "03_graph/exports",
        "04_analysis",
        "05_reports",
    ):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_schema(tmp_phage_dir):
    """Copy prophage_schema.json into tmp_phage_dir/00_config/."""
    src = ASSETS_DIR / "prophage_schema.json"
    dst = tmp_phage_dir / "00_config" / "schema.json"
    shutil.copy(src, dst)
    return dst


@pytest.fixture
def schema_data():
    """Return parsed prophage_schema.json."""
    with open(ASSETS_DIR / "prophage_schema.json") as f:
        return json.load(f)


@pytest.fixture
def sample_paper_list():
    """Return valid paper_list.json data."""
    return {
        "search_date": "2026-02-28",
        "query": "prophage identification OR prophage induction",
        "total_pubmed_hits": 3500,
        "selected_count": 2,
        "papers": [
            {
                "paper_id": "P001",
                "pmid": "39876543",
                "pmcid": "PMC12345678",
                "doi": "10.1038/s41586-024-00001-x",
                "title": "Identification of novel prophages in Escherichia coli K-12",
                "authors": "Smith J, Lee K, Park S",
                "year": 2024,
                "journal": "Nature",
                "abstract": "We identified and characterized several novel prophages in E. coli K-12 genome.",
                "has_full_text": False,
                "extraction_status": "pending",
            },
            {
                "paper_id": "P002",
                "pmid": "39876544",
                "pmcid": "PMC12345679",
                "doi": "10.1126/science.abc1234",
                "title": "Prophage induction dynamics under SOS response in Salmonella enterica",
                "authors": "Kim H, Zhang W",
                "year": 2025,
                "journal": "Science",
                "abstract": "SOS-dependent prophage induction was studied using time-lapse microscopy.",
                "has_full_text": True,
                "extraction_status": "extracted",
            },
        ],
    }


@pytest.fixture
def sample_extraction():
    """Return valid per-paper extraction JSON data."""
    return {
        "paper_id": "P001",
        "paper_doi": "10.1038/s41586-024-00001-x",
        "entities": [
            {
                "label": "Prophage",
                "properties": {
                    "name": "DLP12",
                    "host_organism": "Escherichia coli K-12",
                    "genome_size_kb": 21.3,
                    "completeness": "intact",
                },
            },
            {
                "label": "Gene",
                "properties": {
                    "name": "intDLP12",
                    "symbol": "int",
                    "category": "integration",
                    "function": "Site-specific integrase",
                },
            },
            {
                "label": "Host",
                "properties": {
                    "species": "Escherichia coli",
                    "strain": "K-12 MG1655",
                    "taxonomy_id": "511145",
                },
            },
            {
                "label": "IntegrationSite",
                "properties": {
                    "locus": "tRNA-Arg",
                    "tRNA_gene": "argU",
                    "chromosome_position": "556789",
                },
            },
        ],
        "relationships": [
            {
                "type": "ENCODES",
                "from": {"label": "Prophage", "key": "DLP12"},
                "to": {"label": "Gene", "key": "intDLP12"},
                "properties": {
                    "confidence": 0.95,
                    "source_section": "results",
                    "evidence": "DLP12 prophage encodes integrase gene intDLP12",
                },
            },
            {
                "type": "INTEGRATES_INTO",
                "from": {"label": "Prophage", "key": "DLP12"},
                "to": {"label": "Host", "key": "Escherichia coli"},
                "properties": {
                    "confidence": 0.90,
                    "source_section": "results",
                    "mechanism": "site-specific",
                    "evidence": "DLP12 integrates into the tRNA-Arg locus of E. coli K-12",
                },
            },
        ],
        "unschemaed": [],
    }


@pytest.fixture
def sample_graph_data():
    """Return valid graph nodes and edges data."""
    return {
        "generated": "2026-02-28T12:00:00Z",
        "total_nodes": 3,
        "total_edges": 2,
        "nodes": [
            {
                "id": "prophage_DLP12",
                "label": "Prophage",
                "properties": {"name": "DLP12", "host_organism": "Escherichia coli K-12", "genome_size_kb": 21.3},
                "source_papers": ["P001"],
                "merged_count": 1,
            },
            {
                "id": "gene_intDLP12",
                "label": "Gene",
                "properties": {"name": "intDLP12", "category": "integration"},
                "source_papers": ["P001"],
                "merged_count": 1,
            },
            {
                "id": "host_ecoli",
                "label": "Host",
                "properties": {"species": "Escherichia coli", "strain": "K-12 MG1655"},
                "source_papers": ["P001"],
                "merged_count": 1,
            },
        ],
        "edges": [
            {
                "id": "edge_encodes_DLP12_intDLP12",
                "type": "ENCODES",
                "from_id": "prophage_DLP12",
                "to_id": "gene_intDLP12",
                "properties": {"evidence": "DLP12 encodes intDLP12"},
                "avg_confidence": 0.95,
                "source_papers": ["P001"],
            },
            {
                "id": "edge_integrates_DLP12_ecoli",
                "type": "INTEGRATES_INTO",
                "from_id": "prophage_DLP12",
                "to_id": "host_ecoli",
                "properties": {"mechanism": "site-specific"},
                "avg_confidence": 0.90,
                "source_papers": ["P001"],
            },
        ],
    }


@pytest.fixture
def sample_pmc_xml():
    """PMC efetch response XML sample with sections."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pmc-articleset PUBLIC "-//NLM//DTD ARTICLE SET 2.0//EN" "https://dtd.nlm.nih.gov/ncbi/pmc/articleset/nlm-articleset-2.0.dtd">
<pmc-articleset>
<article article-type="research-article">
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">39876543</article-id>
      <article-id pub-id-type="pmc">PMC12345678</article-id>
    </article-meta>
  </front>
  <body>
    <sec sec-type="intro">
      <title>Introduction</title>
      <p>Prophages are phage genomes integrated into bacterial chromosomes.</p>
    </sec>
    <sec sec-type="methods">
      <title>Methods</title>
      <p>We used PHASTER and PhiSpy for prophage identification.</p>
    </sec>
    <sec sec-type="results">
      <title>Results</title>
      <p>We identified DLP12 prophage in E. coli K-12 with intact integrase gene.</p>
      <p>The prophage genome is 21.3 kb and integrates at the tRNA-Arg locus.</p>
    </sec>
    <sec sec-type="discussion">
      <title>Discussion</title>
      <p>Our findings suggest DLP12 contributes to host fitness through lysogenic conversion.</p>
    </sec>
  </body>
  <back>
    <ref-list>
      <title>References</title>
    </ref-list>
  </back>
</article>
</pmc-articleset>"""


@pytest.fixture
def mock_pubmed_esearch_response():
    """PubMed esearch API response XML."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>3500</Count>
  <RetMax>100</RetMax>
  <RetStart>0</RetStart>
  <IdList>
    <Id>39876543</Id>
    <Id>39876544</Id>
    <Id>39876545</Id>
    <Id>39876546</Id>
    <Id>39876547</Id>
  </IdList>
</eSearchResult>"""


@pytest.fixture
def mock_pubmed_efetch_response():
    """PubMed efetch API response XML for metadata."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>39876543</PMID>
      <Article>
        <Journal>
          <Title>Nature</Title>
        </Journal>
        <ArticleTitle>Identification of novel prophages in Escherichia coli K-12</ArticleTitle>
        <Abstract>
          <AbstractText>We identified and characterized several novel prophages.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
          <Author><LastName>Lee</LastName><ForeName>K</ForeName></Author>
        </AuthorList>
        <ArticleIdList>
          <ArticleId IdType="doi">10.1038/s41586-024-00001-x</ArticleId>
          <ArticleId IdType="pmc">PMC12345678</ArticleId>
        </ArticleIdList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2024</Year>
        </PubMedPubDate>
      </History>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>39876544</PMID>
      <Article>
        <Journal>
          <Title>Science</Title>
        </Journal>
        <ArticleTitle>Prophage induction dynamics under SOS response</ArticleTitle>
        <Abstract>
          <AbstractText>SOS-dependent prophage induction was studied.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Kim</LastName><ForeName>H</ForeName></Author>
        </AuthorList>
        <ArticleIdList>
          <ArticleId IdType="doi">10.1126/science.abc1234</ArticleId>
          <ArticleId IdType="pmc">PMC12345679</ArticleId>
        </ArticleIdList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubMedPubDate PubStatus="pubmed">
          <Year>2025</Year>
        </PubMedPubDate>
      </History>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""
