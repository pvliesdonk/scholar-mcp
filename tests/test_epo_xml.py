"""Tests for EPO OPS XML biblio and search response parsers."""

from __future__ import annotations

from scholar_mcp._epo_xml import parse_biblio_xml, parse_search_xml

# ---------------------------------------------------------------------------
# Fixtures — inline XML bytes
# ---------------------------------------------------------------------------

BIBLIO_XML_FULL = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:meta name="elapsed-time" value="5"/>
  <exchange-documents>
    <exchange-document
        system="ops.epo.org"
        family-id="54321"
        country="EP"
        doc-number="1234567"
        kind="A1">
      <bibliographic-data>
        <publication-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>1234567</doc-number>
            <kind>A1</kind>
            <date>20200115</date>
          </document-id>
        </publication-reference>
        <application-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>EP</country>
            <doc-number>18123456</doc-number>
            <kind>A</kind>
            <date>20181201</date>
          </document-id>
        </application-reference>
        <priority-claims>
          <priority-claim sequence="1" kind="national">
            <document-id document-id-type="docdb">
              <country>US</country>
              <doc-number>201762123456</doc-number>
              <kind>P</kind>
              <date>20171105</date>
            </document-id>
          </priority-claim>
        </priority-claims>
        <parties>
          <applicants>
            <applicant sequence="1" data-format="docdb" app-type="applicant">
              <applicant-name><name>ACME Corporation</name></applicant-name>
            </applicant>
            <applicant sequence="2" data-format="docdb" app-type="applicant">
              <applicant-name><name>Beta Inc</name></applicant-name>
            </applicant>
          </applicants>
          <inventors>
            <inventor sequence="1" data-format="docdb">
              <inventor-name><name>Smith, John</name></inventor-name>
            </inventor>
            <inventor sequence="2" data-format="docdb">
              <inventor-name><name>Doe, Jane</name></inventor-name>
            </inventor>
          </inventors>
        </parties>
        <invention-title lang="en">A Method for Testing XML Parsers</invention-title>
        <invention-title lang="de">Ein Verfahren zum Testen von XML-Parsern</invention-title>
        <abstract lang="en">
          <p>This is the English abstract describing the invention in detail.</p>
        </abstract>
        <abstract lang="de">
          <p>Dies ist die deutsche Zusammenfassung der Erfindung.</p>
        </abstract>
        <patent-classifications>
          <patent-classification sequence="1" scheme="CPCI">
            <section>H</section>
            <class>04</class>
            <subclass>L</subclass>
            <main-group>29</main-group>
            <subgroup>06</subgroup>
            <classification-value>I</classification-value>
          </patent-classification>
          <patent-classification sequence="2" scheme="CPCI">
            <section>G</section>
            <class>06</class>
            <subclass>F</subclass>
            <main-group>21</main-group>
            <subgroup>60</subgroup>
            <classification-value>I</classification-value>
          </patent-classification>
        </patent-classifications>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>
"""

BIBLIO_XML_NON_ENGLISH_ONLY = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document
        family-id="99999"
        country="DE"
        doc-number="102020123456"
        kind="A1">
      <bibliographic-data>
        <publication-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>DE</country>
            <doc-number>102020123456</doc-number>
            <kind>A1</kind>
            <date>20210301</date>
          </document-id>
        </publication-reference>
        <application-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>DE</country>
            <doc-number>102020123456</doc-number>
            <kind>A</kind>
            <date>20200601</date>
          </document-id>
        </application-reference>
        <priority-claims>
          <priority-claim sequence="1" kind="national">
            <document-id document-id-type="docdb">
              <country>DE</country>
              <doc-number>102019123456</doc-number>
              <kind>A</kind>
              <date>20190915</date>
            </document-id>
          </priority-claim>
        </priority-claims>
        <parties>
          <applicants>
            <applicant sequence="1" data-format="docdb" app-type="applicant">
              <applicant-name><name>Firma GmbH</name></applicant-name>
            </applicant>
          </applicants>
          <inventors>
            <inventor sequence="1" data-format="docdb">
              <inventor-name><name>Mueller, Hans</name></inventor-name>
            </inventor>
          </inventors>
        </parties>
        <invention-title lang="de">Nur Deutsches Patent</invention-title>
        <abstract lang="de">
          <p>Nur eine deutsche Zusammenfassung.</p>
        </abstract>
        <patent-classifications/>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>
"""

BIBLIO_XML_MINIMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <exchange-documents>
    <exchange-document
        family-id="77777"
        country="WO"
        doc-number="2023123456"
        kind="A1">
      <bibliographic-data>
        <publication-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>WO</country>
            <doc-number>2023123456</doc-number>
            <kind>A1</kind>
            <date>20230601</date>
          </document-id>
        </publication-reference>
        <application-reference data-format="docdb">
          <document-id document-id-type="docdb">
            <country>WO</country>
            <doc-number>2023US12345</doc-number>
            <kind>A</kind>
            <date>20230101</date>
          </document-id>
        </application-reference>
        <priority-claims/>
        <parties>
          <applicants/>
          <inventors/>
        </parties>
        <patent-classifications/>
      </bibliographic-data>
    </exchange-document>
  </exchange-documents>
</ops:world-patent-data>
"""

SEARCH_XML_FULL = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="42">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country>
          <doc-number>1234567</doc-number>
          <kind>A1</kind>
        </document-id>
      </ops:publication-reference>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>WO</country>
          <doc-number>2020123456</doc-number>
          <kind>A1</kind>
        </document-id>
      </ops:publication-reference>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>US</country>
          <doc-number>10234567</doc-number>
          <kind>B2</kind>
        </document-id>
      </ops:publication-reference>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>
"""

SEARCH_XML_EMPTY = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="0">
    <ops:search-result>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>
"""

SEARCH_XML_SINGLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data
    xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="1">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="docdb">
          <country>EP</country>
          <doc-number>9876543</doc-number>
          <kind>B1</kind>
        </document-id>
      </ops:publication-reference>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>
"""


# ---------------------------------------------------------------------------
# Tests for parse_biblio_xml
# ---------------------------------------------------------------------------


class TestParseBiblioXmlBasicFields:
    def test_publication_number(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["publication_number"] == "EP.1234567.A1"

    def test_publication_date(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["publication_date"] == "2020-01-15"

    def test_filing_date(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["filing_date"] == "2018-12-01"

    def test_priority_date(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["priority_date"] == "2017-11-05"

    def test_family_id(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["family_id"] == "54321"

    def test_url_contains_publication_number(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["url"] == (
            "https://worldwide.espacenet.com/patent/search/family/54321/publication/EP1234567A1"
        )


class TestParseBiblioXmlEnglishPreference:
    def test_title_prefers_english(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["title"] == "A Method for Testing XML Parsers"

    def test_abstract_prefers_english(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert "English abstract" in result["abstract"]

    def test_title_fallback_to_non_english(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_NON_ENGLISH_ONLY)
        assert result["title"] == "Nur Deutsches Patent"

    def test_abstract_fallback_to_non_english(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_NON_ENGLISH_ONLY)
        assert "deutsche Zusammenfassung" in result["abstract"]


class TestParseBiblioXmlApplicantsInventors:
    def test_applicants_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["applicants"] == ["ACME Corporation", "Beta Inc"]

    def test_inventors_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert result["inventors"] == ["Smith, John", "Doe, Jane"]

    def test_single_applicant(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_NON_ENGLISH_ONLY)
        assert result["applicants"] == ["Firma GmbH"]

    def test_empty_applicants(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["applicants"] == []

    def test_empty_inventors(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["inventors"] == []


class TestParseBiblioXmlClassifications:
    def test_classifications_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert "H04L29/06" in result["classifications"]
        assert "G06F21/60" in result["classifications"]

    def test_classifications_count(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert len(result["classifications"]) == 2

    def test_empty_classifications(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["classifications"] == []


class TestParseBiblioXmlMinimal:
    def test_minimal_no_priority_claims(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["priority_date"] == ""

    def test_minimal_no_title(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["title"] == ""

    def test_minimal_no_abstract(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["abstract"] == ""

    def test_minimal_publication_number(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["publication_number"] == "WO.2023123456.A1"

    def test_minimal_family_id(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_MINIMAL)
        assert result["family_id"] == "77777"


class TestParseBiblioXmlOutputKeys:
    def test_all_expected_keys_present(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        expected_keys = {
            "title",
            "abstract",
            "applicants",
            "inventors",
            "publication_number",
            "publication_date",
            "filing_date",
            "priority_date",
            "family_id",
            "classifications",
            "url",
        }
        assert set(result.keys()) == expected_keys

    def test_applicants_is_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert isinstance(result["applicants"], list)

    def test_inventors_is_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert isinstance(result["inventors"], list)

    def test_classifications_is_list(self) -> None:
        result = parse_biblio_xml(BIBLIO_XML_FULL)
        assert isinstance(result["classifications"], list)


# ---------------------------------------------------------------------------
# Tests for parse_search_xml
# ---------------------------------------------------------------------------


class TestParseSearchXmlCount:
    def test_total_count(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        assert result["total_count"] == 42

    def test_total_count_empty(self) -> None:
        result = parse_search_xml(SEARCH_XML_EMPTY)
        assert result["total_count"] == 0

    def test_total_count_single(self) -> None:
        result = parse_search_xml(SEARCH_XML_SINGLE)
        assert result["total_count"] == 1


class TestParseSearchXmlReferences:
    def test_references_count(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        assert len(result["references"]) == 3

    def test_first_reference_ep(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        ref = result["references"][0]
        assert ref["country"] == "EP"
        assert ref["number"] == "1234567"
        assert ref["kind"] == "A1"

    def test_second_reference_wo(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        ref = result["references"][1]
        assert ref["country"] == "WO"
        assert ref["number"] == "2020123456"
        assert ref["kind"] == "A1"

    def test_third_reference_us(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        ref = result["references"][2]
        assert ref["country"] == "US"
        assert ref["number"] == "10234567"
        assert ref["kind"] == "B2"

    def test_empty_results(self) -> None:
        result = parse_search_xml(SEARCH_XML_EMPTY)
        assert result["references"] == []

    def test_single_result(self) -> None:
        result = parse_search_xml(SEARCH_XML_SINGLE)
        assert len(result["references"]) == 1
        ref = result["references"][0]
        assert ref["country"] == "EP"
        assert ref["number"] == "9876543"
        assert ref["kind"] == "B1"


class TestParseSearchXmlOutputKeys:
    def test_all_expected_keys_present(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        assert set(result.keys()) == {"total_count", "references"}

    def test_references_is_list(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        assert isinstance(result["references"], list)

    def test_reference_keys(self) -> None:
        result = parse_search_xml(SEARCH_XML_FULL)
        ref = result["references"][0]
        assert set(ref.keys()) == {"country", "number", "kind"}
