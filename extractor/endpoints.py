import logging
import xml.etree.ElementTree as ET

import pandas as pd

from extractor.client import get_with_retry

logger = logging.getLogger(__name__)


def _parse_namespace(root: ET.Element) -> dict:
    if "}" in root.tag:
        namespace = root.tag.split("}")[0].strip("{")
        return {"ns": namespace}
    return {}


def _t(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def fetch_products(base_url: str, suffix: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fetch the product catalog XML and parse it into three flat DataFrames:
    - products  (one row per product)
    - variants  (one row per variant, keyed by product_ref)
    - images    (one row per image, keyed by product_ref)
    """
    url = base_url + suffix
    content = get_with_retry(url)
    root = ET.fromstring(content)

    products, variants, images = [], [], []

    for product in root.findall(".//product"):
        ref = _t(product, "ref")

        products.append({
            "ref":               ref,
            "name":              _t(product, "name"),
            "type":              _t(product, "type"),
            "composition":       _t(product, "composition"),
            "otherinfo":         _t(product, "otherinfo"),
            "extendedinfo":      _t(product, "extendedinfo"),
            "brand":             _t(product, "brand"),
            "printcode":         _t(product, "printcode"),
            "item_long":         _t(product, "item_long"),
            "item_hight":        _t(product, "item_hight"),
            "item_width":        _t(product, "item_width"),
            "item_diameter":     _t(product, "item_diameter"),
            "item_weight":       _t(product, "item_weight"),
            "masterbox_units":   _t(product, "masterbox_units"),
            "order_min_product": _t(product, "order_min_product"),
            "imagemain":         _t(product, "imagemain"),
            "keywords":          _t(product, "keywords"),
            "link360":           _t(product, "link360"),
            "linkvideo":         _t(product, "linkvideo"),
            "category_ref_1":    _t(product, "categories/category_ref_1"),
            "category_name_1":   _t(product, "categories/category_name_1"),
            "category_ref_2":    _t(product, "categories/category_ref_2"),
            "category_name_2":   _t(product, "categories/category_name_2"),
            "category_ref_3":    _t(product, "categories/category_ref_3"),
            "category_name_3":   _t(product, "categories/category_name_3"),
        })

        for variant in product.findall("variants/variant"):
            variants.append({
                "product_ref": ref,
                "matnr":       _t(variant, "matnr"),
                "refct":       _t(variant, "refct"),
                "colour":      _t(variant, "colour"),
                "colourname":  _t(variant, "colourname"),
                "size":        _t(variant, "size"),
                "image500px":  _t(variant, "image500px"),
            })

        for image in product.findall("images/image"):
            images.append({
                "product_ref": ref,
                "imagemax":    _t(image, "imagemax"),
                "main":        _t(image, "main") == "true",
            })

    logger.info(f"Parsed {len(products)} products, {len(variants)} variants, {len(images)} images")
    return pd.DataFrame(products), pd.DataFrame(variants), pd.DataFrame(images)


def fetch_price(base_url: str, suffix: str) -> pd.DataFrame:
    """
    Fetch and parse the price XML endpoint.
    Returns one row per product with 4 quantity-tiered price columns.
    """
    url = base_url + suffix
    content = get_with_retry(url)
    root = ET.fromstring(content)
    ns = _parse_namespace(root)

    prefix = "ns:" if ns else ""
    products = root.findall(f".//{prefix}product", ns) if ns else root.findall(".//product")

    rows = []
    for product in products:
        def text(tag):
            el = product.find(f"ns:{tag}", ns) if ns else product.find(tag)
            return el.text.strip() if el is not None and el.text else None

        rows.append({
            "ref": text("ref"),
            "name": text("name"),
            "section1": text("section1"),
            "price1": text("price1"),
            "section2": text("section2"),
            "price2": text("price2"),
            "section3": text("section3"),
            "price3": text("price3"),
            "section4": text("section4"),
            "price4": text("price4"),
        })

    logger.info(f"Parsed {len(rows)} products from price XML")
    return pd.DataFrame(rows)


def fetch_stock(base_url: str, suffix: str) -> pd.DataFrame:
    """
    Fetch and parse the stock XML endpoint.
    Returns one row per product/warehouse with stock qty and availability.
    """
    url = base_url + suffix
    content = get_with_retry(url)
    root = ET.fromstring(content)
    ns = _parse_namespace(root)

    products = root.findall(".//ns:product", ns) if ns else root.findall(".//product")

    rows = []
    for product in products:
        def text(el, tag):
            child = el.find(f"ns:{tag}", ns) if ns else el.find(tag)
            return child.text.strip() if child is not None and child.text else None

        ref = text(product, "ref")
        infostocks = (
            product.findall(".//ns:infostock", ns) if ns
            else product.findall(".//infostock")
        )

        if not infostocks:
            rows.append({"ref": ref, "warehouse": None, "stock": None, "available": None})
            continue

        for infostock in infostocks:
            rows.append({
                "ref": ref,
                "warehouse": text(infostock, "from"),
                "stock": text(infostock, "stock"),
                "available": text(infostock, "available"),
            })

    logger.info(f"Parsed {len(rows)} stock rows from stock XML")
    return pd.DataFrame(rows)


def fetch_print(base_url: str, suffix: str) -> pd.DataFrame:
    """
    Fetch and parse the print options XML endpoint.
    Returns one row per product / technique / area combination.
    """
    url = base_url + suffix
    content = get_with_retry(url)
    root = ET.fromstring(content)

    rows = []
    for product in root.findall(".//product"):
        ref = _t(product, "ref")
        for printjob in product.findall("printjobs/printjob"):
            teccode      = _t(printjob, "teccode")
            tecname      = _t(printjob, "tecname")
            colour_layers   = _t(printjob, "colour_layers")
            includedcolour  = _t(printjob, "includedcolour")
            for area in printjob.findall("areas/area"):
                rows.append({
                    "product_ref":    ref,
                    "teccode":        teccode,
                    "tecname":        tecname,
                    "colour_layers":  colour_layers,
                    "includedcolour": includedcolour,
                    "areacode":       _t(area, "areacode"),
                    "maxcolour":      _t(area, "maxcolour"),
                    "areaname":       _t(area, "areaname"),
                    "areawidth":      _t(area, "areawidth"),
                    "areahight":      _t(area, "areahight"),
                    "areaimg":        _t(area, "areaimg"),
                })

    logger.info(f"Parsed {len(rows)} print option rows")
    return pd.DataFrame(rows)


def fetch_print_price(base_url: str, suffix: str) -> pd.DataFrame:
    """
    Fetch and parse the print job prices XML endpoint.
    Returns one row per technique with up to 7 quantity-tiered price columns.
    """
    url = base_url + suffix
    content = get_with_retry(url)
    root = ET.fromstring(content)

    rows = []
    for printjob in root.findall(".//printjob"):
        row = {
            "teccode":   _t(printjob, "teccode"),
            "code":      _t(printjob, "code"),
            "name":      _t(printjob, "name"),
            "cliche":    _t(printjob, "cliche"),
            "clicherep": _t(printjob, "clicherep"),
            "minjob":    _t(printjob, "minjob"),
        }
        for i in range(1, 8):
            row[f"amountunder{i}"] = _t(printjob, f"amountunder{i}")
            row[f"price{i}"]       = _t(printjob, f"price{i}")
        rows.append(row)

    logger.info(f"Parsed {len(rows)} print price rows")
    return pd.DataFrame(rows)
