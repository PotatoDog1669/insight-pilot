from insight_pilot.search.pubmed import normalize_pub_date, parse_pubmed_xml


def test_normalize_pub_date():
    assert normalize_pub_date("2024 Aug 9") == "2024-08-09"
    assert normalize_pub_date("2024 Aug") == "2024-08"
    assert normalize_pub_date("2024") == "2024"


def test_parse_pubmed_xml():
    xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>123456</PMID>
          <Article>
            <Abstract>
              <AbstractText>Sample abstract.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1000/test</ArticleId>
            <ArticleId IdType="pmc">PMC12345</ArticleId>
          </ArticleIdList>
        </PubmedData>
        <KeywordList>
          <Keyword>AI</Keyword>
        </KeywordList>
        <MeshHeadingList>
          <MeshHeading>
            <DescriptorName>Agents</DescriptorName>
          </MeshHeading>
        </MeshHeadingList>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    records = parse_pubmed_xml(xml)
    assert "123456" in records
    record = records["123456"]
    assert record["abstract"] == "Sample abstract."
    assert "AI" in record["keywords"]
    assert "Agents" in record["mesh_terms"]
    assert record["doi"] == "10.1000/test"
    assert record["pmc"] == "PMC12345"
