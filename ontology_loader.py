"""
Generic OWL/RDFS ontology loader.

Given any Turtle file, produces a runtime config the app uses to:
  - build the properties panel (classes and their data properties)
  - tag columns to properties
  - serialize tagged spreadsheet data as an RDF graph with proper entity nodes
  - infer object-property links between entities that co-occur on a row
  - describe the ontology to an LLM for natural-language querying

No domain-specific heuristics. Any well-formed OWL ontology works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS


@dataclass
class DataProperty:
    uri: str            # local name (e.g. "name")
    label: str          # human label
    comment: str
    domain: str         # class local name this property belongs to
    range: str          # xsd family: string | integer | float | date | boolean


@dataclass
class ObjectProperty:
    uri: str
    label: str
    comment: str
    subject_class: str  # "*" means universal (owl:Thing or unspecified)
    object_class: str


@dataclass
class OntologyClass:
    uri: str
    label: str
    comment: str
    data_properties: List[DataProperty] = field(default_factory=list)
    key_property: Optional[str] = None   # datatype property used to identify instances


@dataclass
class OntologyConfig:
    name: str
    namespace: str                                          # canonical public URI (from owl:Ontology, or working_ns)
    working_ns: str                                         # namespace of class URIs actually in the file
    data_namespace: str                                     # namespace used when creating data instances

    classes: Dict[str, OntologyClass] = field(default_factory=dict)
    object_properties: List[ObjectProperty] = field(default_factory=list)
    data_properties: List[DataProperty] = field(default_factory=list)

    # Derived helpers
    entity_model: List[Dict] = field(default_factory=list)  # ordered list for build_graph
    link_model: Dict[Tuple[str, str], str] = field(default_factory=dict)
    entity_priority: List[str] = field(default_factory=list)
    ontology_summary: str = ""                              # readable text for LLM prompts
    frontend_config: Dict = field(default_factory=dict)     # sent to /api/ontology


# ── Helpers ─────────────────────────────────────────────────────────────────

def _local(uri) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[1] if "#" in s else s.rsplit("/", 1)[1]


def _label(g: Graph, s: URIRef, fallback: str = "") -> str:
    for _, _, o in g.triples((s, RDFS.label, None)):
        return str(o).strip()
    return fallback


def _comment(g: Graph, s: URIRef) -> str:
    for _, _, o in g.triples((s, RDFS.comment, None)):
        return str(o).strip()
    return ""


def _xsd_family(range_uri) -> str:
    if range_uri is None:
        return "string"
    r = str(range_uri).lower()
    if any(w in r for w in ("integer", "int", "long", "short", "byte")):
        return "integer"
    if any(w in r for w in ("float", "double", "decimal")):
        return "float"
    if "datetime" in r:
        return "string"
    if "date" in r:
        return "date"
    if "boolean" in r or "bool" in r:
        return "boolean"
    return "string"


def _humanize(label: str, fallback_local: str) -> str:
    if label:
        return label
    return re.sub(r"(?<!^)(?=[A-Z])", " ", fallback_local).strip()


def _guess_key_property(cls: OntologyClass) -> Optional[str]:
    """Pick the property used to identify an instance. Preference: exact
    <Class>Code/ID/Id/Identifier match, then any property ending in code/id/identifier."""
    exact = {f"{cls.uri}{s}" for s in ("Code", "ID", "Id", "Identifier", "Number")}
    for dp in cls.data_properties:
        if dp.uri in exact:
            return dp.uri
    for dp in cls.data_properties:
        low = dp.uri.lower()
        if low.endswith(("code", "id", "identifier", "number")):
            return dp.uri
    return None


# ── Main loader ─────────────────────────────────────────────────────────────

def load_ontology(ttl_path: Path, name: Optional[str] = None) -> OntologyConfig:
    g = Graph()
    g.parse(str(ttl_path), format="turtle")

    # Canonical namespace: prefer declared owl:Ontology IRI
    canonical_ns = ""
    for s in g.subjects(RDF.type, OWL.Ontology):
        if isinstance(s, URIRef):
            uri = str(s)
            canonical_ns = uri if uri.endswith(("#", "/")) else uri + "#"
            break

    # Working namespace: where the actual classes live in this file
    ns_counts: Dict[str, int] = {}
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            uri = str(s)
            ns = uri.rsplit("#", 1)[0] + "#" if "#" in uri else uri.rsplit("/", 1)[0] + "/"
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
    working_ns = max(ns_counts, key=ns_counts.get) if ns_counts else canonical_ns

    public_ns = canonical_ns or working_ns
    # Data namespace: swap "-ontology" for "-data" if present, else append /data#
    if public_ns.rstrip("#/").endswith("-ontology"):
        data_ns = public_ns.rstrip("#/").rsplit("-ontology", 1)[0] + "-data#"
    elif public_ns:
        data_ns = public_ns.rstrip("#/") + "/data#"
    else:
        data_ns = "urn:data#"

    config = OntologyConfig(
        name=name or ttl_path.stem,
        namespace=public_ns,
        working_ns=working_ns,
        data_namespace=data_ns,
    )

    # ── 1. Classes ──
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef) and str(s).startswith(working_ns):
            local = _local(s)
            config.classes[local] = OntologyClass(
                uri=local,
                label=_humanize(_label(g, s), local),
                comment=_comment(g, s),
            )
    for s in g.subjects(RDF.type, RDFS.Class):
        if isinstance(s, URIRef) and str(s).startswith(working_ns):
            local = _local(s)
            if local not in config.classes:
                config.classes[local] = OntologyClass(
                    uri=local,
                    label=_humanize(_label(g, s), local),
                    comment=_comment(g, s),
                )

    # ── 2. Data properties ──
    for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
        if not isinstance(prop, URIRef):
            continue
        local = _local(prop)

        domain_cls = None
        for _, _, o in g.triples((prop, RDFS.domain, None)):
            if isinstance(o, URIRef):
                dl = _local(o)
                if dl in config.classes:
                    domain_cls = dl
                    break

        rng = None
        for _, _, o in g.triples((prop, RDFS.range, None)):
            rng = o
            break

        dp = DataProperty(
            uri=local,
            label=_humanize(_label(g, prop), local),
            comment=_comment(g, prop),
            domain=domain_cls or "_General",
            range=_xsd_family(rng),
        )

        # Ensure a bucket exists even if no domain was declared
        if dp.domain not in config.classes:
            config.classes[dp.domain] = OntologyClass(
                uri=dp.domain,
                label=_humanize("", dp.domain).replace("_", "").strip() or "General",
                comment="Properties without a declared domain",
            )
        config.classes[dp.domain].data_properties.append(dp)
        config.data_properties.append(dp)

    # ── 3. Object properties ──
    for prop in g.subjects(RDF.type, OWL.ObjectProperty):
        if not isinstance(prop, URIRef):
            continue
        local = _local(prop)

        subject_cls = None
        universal = False
        for _, _, o in g.triples((prop, RDFS.domain, None)):
            if o == OWL.Thing:
                universal = True
                break
            if isinstance(o, URIRef):
                sl = _local(o)
                if sl in config.classes:
                    subject_cls = sl
                    break

        object_cls = None
        for _, _, o in g.triples((prop, RDFS.range, None)):
            if isinstance(o, URIRef):
                ol = _local(o)
                if ol in config.classes:
                    object_cls = ol
                    break

        if not object_cls:
            continue  # can't link to nothing

        config.object_properties.append(ObjectProperty(
            uri=local,
            label=_humanize(_label(g, prop), local),
            comment=_comment(g, prop),
            subject_class=("*" if universal or not subject_cls else subject_cls),
            object_class=object_cls,
        ))

    # ── 4. Key property per class ──
    for cls in config.classes.values():
        cls.key_property = _guess_key_property(cls)

    # ── 5. Entity model (list of dicts, one per class with properties) ──
    # The frontend uses `uri` to tag columns; build_graph uses the class name.
    # No prefix matching — we route by the property URI directly, which is
    # unambiguous. This is much cleaner than the HXL prefix logic.
    ent_entries = []
    for cls_name, cls in config.classes.items():
        if not cls.data_properties:
            continue
        ent_entries.append({
            "cls": cls_name,
            "property_uris": [dp.uri for dp in cls.data_properties],
            "key_uri": cls.key_property,
        })
    config.entity_model = ent_entries

    # ── 6. Link model ──
    # For universal links (owl:Thing domain), expand to every class.
    for op in config.object_properties:
        if op.subject_class == "*":
            for cls_name in config.classes:
                if cls_name == op.object_class:
                    continue
                if not config.classes[cls_name].data_properties:
                    continue
                key = (cls_name, op.object_class)
                config.link_model.setdefault(key, op.uri)
        else:
            config.link_model.setdefault((op.subject_class, op.object_class), op.uri)

    # ── 7. Entity priority (most-connected first) ──
    conn: Dict[str, int] = {}
    for op in config.object_properties:
        if op.subject_class != "*":
            conn[op.subject_class] = conn.get(op.subject_class, 0) + 2
        conn[op.object_class] = conn.get(op.object_class, 0) + 1
    config.entity_priority = sorted(
        config.classes.keys(),
        key=lambda c: (-conn.get(c, 0), c),
    )

    # ── 8. LLM summary text ──
    lines = [f"Ontology: {config.name}", "", "Classes:"]
    for cls_name in sorted(config.classes.keys()):
        cls = config.classes[cls_name]
        if not cls.data_properties:
            continue
        prop_names = ", ".join(dp.uri for dp in cls.data_properties[:12])
        more = f", ... ({len(cls.data_properties) - 12} more)" if len(cls.data_properties) > 12 else ""
        lines.append(f"  {cls_name}: [{prop_names}{more}]")
    if config.object_properties:
        lines.append("")
        lines.append("Relationships:")
        for op in config.object_properties:
            subj = op.subject_class if op.subject_class != "*" else "any entity"
            lines.append(f"  {subj} --{op.uri}--> {op.object_class}")
    config.ontology_summary = "\n".join(lines)

    # ── 9. Frontend config ──
    config.frontend_config = {
        "name": config.name,
        "namespace": config.namespace,
        "class_count": sum(1 for c in config.classes.values() if c.data_properties),
        "property_count": len(config.data_properties),
        "link_count": len(config.object_properties),
        "groups": {
            cls.label: [
                {
                    "label": dp.label,
                    "uri": dp.uri,
                    "range": dp.range,
                    "comment": dp.comment,
                    "class": cls_name,       # the class this property belongs to
                }
                for dp in sorted(cls.data_properties, key=lambda x: x.label)
            ]
            for cls_name, cls in config.classes.items()
            if cls.data_properties
        },
        "links": [
            {
                "from": op.subject_class,
                "to": op.object_class,
                "via": op.uri,
                "label": op.label,
            }
            for op in config.object_properties
        ],
    }

    return config


# ── Empty / no-ontology sentinel ────────────────────────────────────────────

def empty_config() -> OntologyConfig:
    """Config with no ontology loaded. Returned before the user uploads one."""
    return OntologyConfig(
        name="(none)",
        namespace="urn:no-ontology#",
        working_ns="urn:no-ontology#",
        data_namespace="urn:no-ontology-data#",
        ontology_summary="No ontology is currently loaded. Upload a TTL file to begin.",
        frontend_config={
            "name": None,
            "namespace": None,
            "class_count": 0,
            "property_count": 0,
            "link_count": 0,
            "groups": {},
            "links": [],
        },
    )
