from unittest.mock import patch

import pandas as pd
import pytest

from extractor.endpoints import (
    fetch_print,
    fetch_print_price,
    fetch_price,
    fetch_products,
    fetch_stock,
)

# ─── XML fixtures ──────────────────────────────────────────────────────────────

PRODUCTS_XML = b"""<products>
  <product>
    <ref>ABC123</ref>
    <name>Test Pen</name>
    <type>pen</type>
    <composition>plastic</composition>
    <otherinfo/>
    <extendedinfo/>
    <brand>BrandX</brand>
    <printcode>P1</printcode>
    <item_long>15</item_long>
    <item_hight>2</item_hight>
    <item_width>1</item_width>
    <item_diameter/>
    <item_weight>10</item_weight>
    <masterbox_units>100</masterbox_units>
    <order_min_product>50</order_min_product>
    <imagemain>http://example.com/img.jpg</imagemain>
    <keywords>pen writing</keywords>
    <link360/>
    <linkvideo/>
    <categories>
      <category_ref_1>C1</category_ref_1>
      <category_name_1>Office</category_name_1>
      <category_ref_2/>
      <category_name_2/>
      <category_ref_3/>
      <category_name_3/>
    </categories>
    <variants>
      <variant>
        <matnr>V1</matnr>
        <refct>ABC123-BL</refct>
        <colour>BL</colour>
        <colourname>Blue</colourname>
        <size>ONE</size>
        <image500px>http://example.com/v1.jpg</image500px>
      </variant>
    </variants>
    <images>
      <image>
        <imagemax>http://example.com/main.jpg</imagemax>
        <main>true</main>
      </image>
      <image>
        <imagemax>http://example.com/alt.jpg</imagemax>
        <main>false</main>
      </image>
    </images>
  </product>
</products>"""

PRICE_XML_NO_NS = b"""<products>
  <product>
    <ref>ABC123</ref>
    <name>Test Pen</name>
    <section1>10</section1>
    <price1>5.00</price1>
    <section2>25</section2>
    <price2>4.50</price2>
    <section3>50</section3>
    <price3>4.00</price3>
    <section4>100</section4>
    <price4>3.50</price4>
  </product>
</products>"""

PRICE_XML_WITH_NS = b"""<products xmlns="http://example.com/schema">
  <product>
    <ref>ABC123</ref>
    <name>Test Pen</name>
    <section1>10</section1>
    <price1>5.00</price1>
    <section2>25</section2>
    <price2>4.50</price2>
    <section3>50</section3>
    <price3>4.00</price3>
    <section4>100</section4>
    <price4>3.50</price4>
  </product>
</products>"""

STOCK_XML = b"""<stocks>
  <product>
    <ref>ABC123</ref>
    <infostocks>
      <infostock>
        <from>ES</from>
        <stock>100</stock>
        <available>2024-12-31</available>
      </infostock>
    </infostocks>
  </product>
  <product>
    <ref>XYZ456</ref>
  </product>
</stocks>"""

PRINT_XML = b"""<root>
  <product>
    <ref>ABC123</ref>
    <printjobs>
      <printjob>
        <teccode>PAD</teccode>
        <tecname>Pad Printing</tecname>
        <colour_layers>4</colour_layers>
        <includedcolour>1</includedcolour>
        <areas>
          <area>
            <areacode>F</areacode>
            <maxcolour>4</maxcolour>
            <areaname>Front</areaname>
            <areawidth>50</areawidth>
            <areahight>30</areahight>
            <areaimg>http://example.com/area.jpg</areaimg>
          </area>
        </areas>
      </printjob>
    </printjobs>
  </product>
  <product>
    <ref>XYZ456</ref>
    <printjobs/>
  </product>
</root>"""

PRINT_PRICE_XML = b"""<printjobsprices>
  <printjob>
    <teccode>PAD</teccode>
    <code>PAD01</code>
    <name>Pad Printing</name>
    <cliche>25.00</cliche>
    <clicherep>10.00</clicherep>
    <minjob>15.00</minjob>
    <amountunder1>10</amountunder1><price1>2.50</price1>
    <amountunder2>25</amountunder2><price2>2.00</price2>
    <amountunder3>50</amountunder3><price3>1.75</price3>
    <amountunder4>100</amountunder4><price4>1.50</price4>
    <amountunder5>250</amountunder5><price5>1.25</price5>
    <amountunder6>500</amountunder6><price6>1.00</price6>
    <amountunder7>0</amountunder7><price7>0.00</price7>
  </printjob>
</printjobsprices>"""


# ─── fetch_products ────────────────────────────────────────────────────────────

@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_returns_three_dataframes(mock_get):
    result = fetch_products("http://example.com", "/products")
    assert len(result) == 3
    assert all(isinstance(df, pd.DataFrame) for df in result)


@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_url_concatenation(mock_get):
    fetch_products("http://example.com", "/products")
    mock_get.assert_called_once_with("http://example.com/products")


@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_product_fields(mock_get):
    products, _, _ = fetch_products("http://example.com", "/products")
    assert len(products) == 1
    row = products.iloc[0]
    assert row["ref"] == "ABC123"
    assert row["name"] == "Test Pen"
    assert row["category_ref_1"] == "C1"
    assert row["category_ref_2"] is None


@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_variant_has_product_ref_fk(mock_get):
    _, variants, _ = fetch_products("http://example.com", "/products")
    assert len(variants) == 1
    row = variants.iloc[0]
    assert row["product_ref"] == "ABC123"
    assert row["colour"] == "BL"
    assert row["matnr"] == "V1"


@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_image_main_is_bool(mock_get):
    _, _, images = fetch_products("http://example.com", "/products")
    assert len(images) == 2
    assert images.iloc[0]["main"] == True  # noqa: E712  numpy.bool_ != Python True
    assert images.iloc[1]["main"] == False  # noqa: E712


@patch("extractor.endpoints.get_with_retry", return_value=b"<products/>")
def test_fetch_products_empty_catalog(mock_get):
    products, variants, images = fetch_products("http://example.com", "/products")
    assert products.empty
    assert variants.empty
    assert images.empty


# ─── fetch_price ──────────────────────────────────────────────────────────────

@patch("extractor.endpoints.get_with_retry", return_value=PRICE_XML_NO_NS)
def test_fetch_price_no_namespace(mock_get):
    df = fetch_price("http://example.com", "/price")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ref"] == "ABC123"
    assert row["price1"] == "5.00"
    assert row["section2"] == "25"


@patch("extractor.endpoints.get_with_retry", return_value=PRICE_XML_WITH_NS)
def test_fetch_price_with_namespace(mock_get):
    df = fetch_price("http://example.com", "/price")
    assert len(df) == 1
    assert df.iloc[0]["ref"] == "ABC123"
    assert df.iloc[0]["price4"] == "3.50"


@patch("extractor.endpoints.get_with_retry", return_value=PRICE_XML_NO_NS)
def test_fetch_price_all_columns_present(mock_get):
    df = fetch_price("http://example.com", "/price")
    expected_cols = {"ref", "name", "section1", "price1", "section2", "price2",
                     "section3", "price3", "section4", "price4"}
    assert expected_cols.issubset(set(df.columns))


# ─── fetch_stock ──────────────────────────────────────────────────────────────

@patch("extractor.endpoints.get_with_retry", return_value=STOCK_XML)
def test_fetch_stock_with_infostock(mock_get):
    df = fetch_stock("http://example.com", "/stock")
    abc_rows = df[df["ref"] == "ABC123"]
    assert len(abc_rows) == 1
    row = abc_rows.iloc[0]
    assert row["warehouse"] == "ES"
    assert row["stock"] == "100"
    assert row["available"] == "2024-12-31"


@patch("extractor.endpoints.get_with_retry", return_value=STOCK_XML)
def test_fetch_stock_product_without_infostock_gets_null_row(mock_get):
    df = fetch_stock("http://example.com", "/stock")
    xyz_rows = df[df["ref"] == "XYZ456"]
    assert len(xyz_rows) == 1
    row = xyz_rows.iloc[0]
    assert row["warehouse"] is None
    assert row["stock"] is None


@patch("extractor.endpoints.get_with_retry", return_value=STOCK_XML)
def test_fetch_stock_total_row_count(mock_get):
    df = fetch_stock("http://example.com", "/stock")
    assert len(df) == 2


# ─── fetch_print ──────────────────────────────────────────────────────────────

@patch("extractor.endpoints.get_with_retry", return_value=PRINT_XML)
def test_fetch_print_fields(mock_get):
    df = fetch_print("http://example.com", "/print")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["product_ref"] == "ABC123"
    assert row["teccode"] == "PAD"
    assert row["areacode"] == "F"
    assert row["areawidth"] == "50"


@patch("extractor.endpoints.get_with_retry", return_value=PRINT_XML)
def test_fetch_print_empty_printjobs_produces_no_rows(mock_get):
    df = fetch_print("http://example.com", "/print")
    assert "XYZ456" not in df["product_ref"].values


@patch("extractor.endpoints.get_with_retry", return_value=b"<root/>")
def test_fetch_print_empty_xml(mock_get):
    df = fetch_print("http://example.com", "/print")
    assert df.empty


# ─── fetch_print_price ────────────────────────────────────────────────────────

@patch("extractor.endpoints.get_with_retry", return_value=PRINT_PRICE_XML)
def test_fetch_print_price_fields(mock_get):
    df = fetch_print_price("http://example.com", "/print_price")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["teccode"] == "PAD"
    assert row["cliche"] == "25.00"
    assert row["minjob"] == "15.00"


@patch("extractor.endpoints.get_with_retry", return_value=PRINT_PRICE_XML)
def test_fetch_print_price_all_seven_tiers(mock_get):
    df = fetch_print_price("http://example.com", "/print_price")
    row = df.iloc[0]
    for i in range(1, 8):
        assert f"amountunder{i}" in df.columns
        assert f"price{i}" in df.columns
    assert row["amountunder1"] == "10"
    assert row["price1"] == "2.50"
    assert row["amountunder6"] == "500"
    assert row["price6"] == "1.00"
