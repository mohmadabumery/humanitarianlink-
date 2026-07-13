"""
Export a tagged spreadsheet as retailer-ready feed formats.

Given the RDF graph produced by `build_graph`, produces:
  - JSON-LD (for schema.org / Google Merchant Center)
  - Google Shopping XML (RSS 2.0 with Google namespace)
  - Retailer-specific CSV (columns ordered per target)
  - Generic Turtle (already handled by rdflib)

Each format walks the graph, groups triples by product (subject), and writes
one output record per product with the fields the target retailer expects.
"""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from rdflib import Graph, URIRef
from rdflib.namespace import RDF


# ── Helpers ──────────────────────────────────────────────────────────────────

def _local(uri) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[1] if "#" in s else s.rsplit("/", 1)[1]


def _group_by_subject(g: Graph, target_class_local: str) -> Dict[URIRef, Dict[str, Any]]:
    """Walk the graph and gather all triples for each instance of the target class."""
    instances: Dict[URIRef, Dict[str, Any]] = {}
    # Every subject typed as the target class
    for s in g.subjects(RDF.type, None):
        cls_local = _local(next(g.objects(s, RDF.type)))
        if cls_local != target_class_local:
            continue
        instances[s] = {"@id": str(s), "type": cls_local, "props": {}, "links": {}}

    # Fill in each instance's data properties and object properties
    for s, p, o in g:
        if s not in instances:
            continue
        if p == RDF.type:
            continue
        p_local = _local(p)
        # Object property (o is a URIRef pointing to another node)
        if isinstance(o, URIRef):
            # Store the linked object's data as a nested dict, if it exists
            linked = {}
            for _, lp, lo in g.triples((o, None, None)):
                if lp == RDF.type:
                    continue
                if isinstance(lo, URIRef):
                    continue  # skip second-level nested links for simplicity
                linked[_local(lp)] = str(lo)
            instances[s]["links"][p_local] = linked
        else:
            instances[s]["props"][p_local] = str(o)

    return instances


# ── JSON-LD export (schema.org) ──────────────────────────────────────────────

# Map internal ontology field URIs -> schema.org / Google Merchant field names.
# Anything not mapped is passed through with its original name.
JSON_LD_FIELD_MAP: Dict[str, str] = {
    "ProductID": "sku",
    "Title": "name",
    "Description": "description",
    "ProductLink": "url",
    "MainImageURL": "image",
    "AdditionalImageURL": "additionalImage",
    "Condition": "itemCondition",
    "Availability": "availability",
    "GTIN": "gtin",
    "MPN": "mpn",
    "GoogleProductCategory": "googleProductCategory",
    "ProductType": "category",
    "Color": "color",
    "Size": "size",
    "Material": "material",
    "Pattern": "pattern",
    "AgeGroup": "audience",
    "Gender": "gender",
    "Weight": "weight",
    "BrandName": "name",
    "Price": "price",
    "SalePrice": "salePrice",
    "SalePriceEffectiveDate": "priceValidUntil",
    "Currency": "priceCurrency",
    "OfferID": "sku",
    "ShippingCountry": "shippingDestination",
    "ShippingPrice": "shippingRate",
    "ShippingService": "shippingMethod",
}


def to_json_ld(g: Graph, product_class: str = "Product") -> str:
    """Emit a schema.org-flavored JSON-LD array of products.
    Suitable for embedding in a webpage or feeding to Google Merchant."""
    instances = _group_by_subject(g, product_class)
    items = []
    for _, inst in instances.items():
        item: Dict[str, Any] = {
            "@context": "https://schema.org/",
            "@type": "Product",
        }
        for field_local, val in inst["props"].items():
            key = JSON_LD_FIELD_MAP.get(field_local, field_local)
            item[key] = val

        # Nested Brand
        if "hasBrand" in inst["links"]:
            brand_data = inst["links"]["hasBrand"]
            if brand_data:
                item["brand"] = {
                    "@type": "Brand",
                    **{JSON_LD_FIELD_MAP.get(k, k): v for k, v in brand_data.items()},
                }

        # Nested Offer
        if "hasOffer" in inst["links"]:
            offer_data = inst["links"]["hasOffer"]
            if offer_data:
                item["offers"] = {
                    "@type": "Offer",
                    **{JSON_LD_FIELD_MAP.get(k, k): v for k, v in offer_data.items()},
                }

        items.append(item)

    return json.dumps(items, indent=2, ensure_ascii=False)


# ── Google Shopping XML export ────────────────────────────────────────────────
# Format: RSS 2.0 with Google namespace, per
# https://support.google.com/merchants/answer/7052112

GOOGLE_FEED_FIELD_MAP: Dict[str, str] = {
    "ProductID": "g:id",
    "Title": "g:title",
    "Description": "g:description",
    "ProductLink": "g:link",
    "MainImageURL": "g:image_link",
    "AdditionalImageURL": "g:additional_image_link",
    "Condition": "g:condition",
    "Availability": "g:availability",
    "GTIN": "g:gtin",
    "MPN": "g:mpn",
    "GoogleProductCategory": "g:google_product_category",
    "ProductType": "g:product_type",
    "Color": "g:color",
    "Size": "g:size",
    "Material": "g:material",
    "Pattern": "g:pattern",
    "AgeGroup": "g:age_group",
    "Gender": "g:gender",
    "Weight": "g:shipping_weight",
    # from Brand
    "BrandName": "g:brand",
    # from Offer
    "Price": "g:price",
    "SalePrice": "g:sale_price",
    "SalePriceEffectiveDate": "g:sale_price_effective_date",
}


def to_google_shopping_xml(g: Graph, store_title: str = "My Store",
                           store_link: str = "https://example.com",
                           product_class: str = "Product") -> str:
    """Emit a Google Merchant Center XML feed."""
    root = ET.Element("rss", {
        "version": "2.0",
        "xmlns:g": "http://base.google.com/ns/1.0",
    })
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = store_title
    ET.SubElement(channel, "link").text = store_link
    ET.SubElement(channel, "description").text = f"{store_title} product feed"

    instances = _group_by_subject(g, product_class)
    for _, inst in instances.items():
        item = ET.SubElement(channel, "item")
        # Flatten product properties
        combined: Dict[str, str] = dict(inst["props"])
        # Merge Brand fields (BrandName -> g:brand)
        brand = inst["links"].get("hasBrand", {})
        for k, v in brand.items():
            combined[k] = v
        # Merge Offer fields (Price, SalePrice, etc.)
        offer = inst["links"].get("hasOffer", {})
        for k, v in offer.items():
            combined[k] = v

        # Combine Price + Currency into a single "PRICE CURRENCY" string for Google
        if "Price" in combined and "Currency" in combined:
            combined["Price"] = f"{combined['Price']} {combined['Currency']}"
        if "SalePrice" in combined and "Currency" in combined:
            combined["SalePrice"] = f"{combined['SalePrice']} {combined['Currency']}"

        for field_local, val in combined.items():
            xml_tag = GOOGLE_FEED_FIELD_MAP.get(field_local)
            if not xml_tag or not val:
                continue
            ET.SubElement(item, xml_tag).text = str(val)

    # Pretty-print
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# ── CSV export ────────────────────────────────────────────────────────────────

def to_csv(g: Graph, product_class: str = "Product",
           column_order: Optional[List[str]] = None) -> str:
    """Emit a flat CSV, one row per product. Nested Offer/Brand fields are flattened."""
    import csv
    instances = _group_by_subject(g, product_class)
    rows: List[Dict[str, str]] = []
    all_keys: List[str] = []
    seen_keys = set()

    for _, inst in instances.items():
        row = dict(inst["props"])
        for link_data in inst["links"].values():
            for k, v in link_data.items():
                row[k] = v
        rows.append(row)
        for k in row:
            if k not in seen_keys:
                seen_keys.add(k)
                all_keys.append(k)

    columns = column_order if column_order else all_keys

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


# ── Preset dispatcher ────────────────────────────────────────────────────────

EXPORT_FORMATS = {
    "json-ld": {
        "label": "JSON-LD (schema.org)",
        "extension": "json",
        "mime": "application/ld+json",
        "func": to_json_ld,
    },
    "google-shopping-xml": {
        "label": "Google Shopping XML",
        "extension": "xml",
        "mime": "application/xml",
        "func": to_google_shopping_xml,
    },
    "csv": {
        "label": "CSV",
        "extension": "csv",
        "mime": "text/csv",
        "func": to_csv,
    },
}


def export(g: Graph, fmt: str, product_class: str = "Product", **kwargs) -> Dict[str, Any]:
    """Main entry point. Returns {content, filename, mime}."""
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Unknown format: {fmt}. Choose from: {list(EXPORT_FORMATS)}")
    spec = EXPORT_FORMATS[fmt]
    content = spec["func"](g, product_class=product_class, **kwargs) if fmt != "csv" \
              else spec["func"](g, product_class=product_class)
    return {
        "content": content,
        "filename": f"catalog.{spec['extension']}",
        "mime": spec["mime"],
        "format_label": spec["label"],
    }
