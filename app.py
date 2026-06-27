"""
HXL Ontology Tagger - Backend
Run with: python app.py
Then open: http://localhost:8000
"""

import os, io, json, re
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

load_dotenv()

app = FastAPI(title="HXL Ontology Tagger")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HXLO = Namespace("https://ontology.humanitariandata.org/hxl-ontology#")
HXLD = Namespace("https://ontology.humanitariandata.org/hxl-data#")
BASE_DIR = Path(__file__).parent

ONTOLOGY_SUMMARY = """
Properties (label | HXL tag | URI | domain | range):
ProjectCode | #project +code | ProjectCode | Project | string
ProjectName | #project +name | ProjectName | Project | string
ProjectSector | #project +sector | ProjectSector | Project | string
TargetedNumber | #project +targeted | TargetedNumber | Project | integer
BeneficiryNumber | #beneficiary +total | BeneficiryNumber | Project | string
TargetedBNF | #beneficiary +targeted | TargetedBNF | Project | string
DistributionCode | #distribution +code | DistributionCode | Distribution | string
DistributionStatus | #distribution +status | DistributionStatus | Distribution | string
StartDate | #distribution +start +date | StartDate | Distribution | date
EndDate | #distribution +end +date | EndDate | Distribution | date
DistributedQuantity | #distribution +q | DistributedQuantity | Distribution | integer
DistributionCapacity | #distribution +capacity | DistributionCapacity | Distribution | integer
DeliveryCode | #delivery +code | DeliveryCode | Delivery | string
DeliveryDate | #delivery +date | DeliveryDate | Delivery | date
DeliveryStatus | #delivery +status | DeliveryStatus | Delivery | string
ModeOfTransport | #delivery +channel | ModeOfTransport | Delivery | string
DeliveredQuantity | #delivery +quantity | DeliveredQuantity | Delivery | integer
AssessmentID | #needsAssessment +code | AssessmentID | NeedsAssessment | string
AssessmentDate | #needsAssessment +occured +date | AssessmentDate | NeedsAssessment | date
ApplicationStatus | #respondee +status | ApplicationStatus | NeedsAssessment | string
Income | #respondee +income | Income | NeedsAssessment | float
NeedCode | #respondee +need +code | NeedCode | NeedsAssessment | string
NeedName | #respondee +need +name | NeedName | NeedsAssessment | string
NeedType | #respondee +need +type | NeedType | NeedsAssessment | string
RespondeeAdolescents | #respondee +adolescents | RespondeeAdolescents | NeedsAssessment | integer
RespondeeAdults | #respondee +adults | RespondeeAdults | NeedsAssessment | integer
Respondeechildren | #respondee +children | Respondeechildren | NeedsAssessment | integer
RespondeeCode | #respondee +code | RespondeeCode | NeedsAssessment | string
RespondeeDisability | #respondee +disability | RespondeeDisability | NeedsAssessment | string
RespondeeElderly | #respondee +elderly | RespondeeElderly | NeedsAssessment | integer
RespondeeEmail | #respondee +email | RespondeeEmail | NeedsAssessment | string
RespondeeFemaleAdolescents | #respondee +f +adolescents | RespondeeFemaleAdolescents | NeedsAssessment | integer
RespondeeFemaleAdults | #respondee +f +adults | RespondeeFemaleAdults | NeedsAssessment | integer
RespondeeFemaleChildren | #respondee +f +children | RespondeeFemaleChildren | NeedsAssessment | integer
RespondeeFemaleElderly | #respondee +f +elderly | RespondeeFemaleElderly | NeedsAssessment | integer
RespondeeFemaleInfants | #respondee +f +infants | RespondeeFemaleInfants | NeedsAssessment | integer
RespondeeGender | #respondee +gender | RespondeeGender | NeedsAssessment | string
RespondeeHouseholdSize | #respondee +hh | RespondeeHouseholdSize | NeedsAssessment | integer
RespondeeInfants | #respondee +infants | RespondeeInfants | NeedsAssessment | integer
RespondeeMaleAdolescents | #respondee +m +adolescents | RespondeeMaleAdolescents | NeedsAssessment | integer
RespondeeMaleAdults | #respondee +m +adults | RespondeeMaleAdults | NeedsAssessment | integer
RespondeeMaleChildren | #respondee +m +children | RespondeeMaleChildren | NeedsAssessment | integer
RespondeeMaleElderly | #respondee +m +elderly | RespondeeMaleElderly | NeedsAssessment | integer
RespondeeMaleInfants | #respondee +m +infants | RespondeeMaleInfants | NeedsAssessment | integer
RespondeeName | #respondee +name | RespondeeName | NeedsAssessment | string
RespondeePhone | #respondee +phone | RespondeePhone | NeedsAssessment | string
SeverityLevel | #respondee +severity | SeverityLevel | NeedsAssessment | string
VulnerabilityScore | #respondee +score | VulnerabilityScore | NeedsAssessment | float
ContractID | #benefitContract +code | ContractID | BenefitContract | string
ContractStartDate | #benefitContract +start +date | ContractStartDate | BenefitContract | date
ContractEndDate | #benefitContract +end +date | ContractEndDate | BenefitContract | date
BeneficiaryCode | #beneficiary +code | BeneficiaryCode | BenefitContract | string
BeneficiaryName | #beneficiary +name | BeneficiaryName | BenefitContract | string
BeneficiaryGender | #beneficiary +gender | BeneficiaryGender | BenefitContract | string
BeneficiaryHousehold | #beneficiary +hh | BeneficiaryHousehold | BenefitContract | integer
BeneficiaryChildren | #beneficiary +children | BeneficiaryChildren | BenefitContract | integer
BeneficiaryElderly | #beneficiary +elderly | BeneficiaryElderly | BenefitContract | integer
BeneficiaryInfants | #beneficiary +infants | BeneficiaryInfants | BenefitContract | integer
BeneficiaryEmail | #beneficiary +email | BeneficiaryEmail | BenefitContract | string
BeneficiaryPhone | #beneficiary +phone | BeneficiaryPhone | BenefitContract | string
ImpactReportCode | #impactReport +code | ImpactReportCode | ImpactReport | string
Date_1 | #impactReport +date | Date_1 | ImpactReport | date
CrisisCode | #crisis +code | CrisisCode | ImpactReport | string
CrisisName | #crisis +name | CrisisName | ImpactReport | string
CrisisType | #crisis +type | CrisisType | ImpactReport | string
AffectedTotal | #affected | AffectedTotal | ImpactReport | integer
InNeedTotal | #affected +inneed | InNeedTotal | ImpactReport | integer
Targeted | #affected +targeted | Targeted | ImpactReport | integer
KilledTotal | #affected +killed | KilledTotal | ImpactReport | integer
InjuredTotal | #affected +injured | InjuredTotal | ImpactReport | integer
DisplacedTotal | #affected +displaced | DisplacedTotal | ImpactReport | integer
RefugeeTotal | #affected +refugee | RefugeeTotal | ImpactReport | integer
AffectedMales | #affected +m | AffectedMales | ImpactReport | integer
AffectedFemales | #affected +f | AffectedFemales | ImpactReport | integer
AffectedChildren | #affected +children | AffectedChildren | ImpactReport | integer
AffectedElderly | #affected +elderly | AffectedElderly | ImpactReport | integer
OrgCode | #org +code | OrgCode | Organization | string
OrgName | #org +name | OrgName | Organization | string
OrgEmail | #org +email | OrgEmail | Organization | string
OrgPhone | #org +phone | OrgPhone | Organization | string
OrgSector | #org +sector | OrgSector | Organization | string
Type | #org +type | Type | Organization | string
CountryName | #country +name | CountryName | Location | string
CountryCode | #country +code | CountryCode | Location | string
RegionName | #region +name | RegionName | Location | string
Admin1Name | #adm1 +name | Admin1Name | Location | string
Admin1Code | #adm1 +code | Admin1Code | Location | string
Admin2Name | #adm2 +name | Admin2Name | Location | string
Admin2Code | #adm2 +code | Admin2Code | Location | string
CityName | #city +name | CityName | Location | string
CityCode | #city +code | CityCode | Location | string
LocationName | #location +name | LocationName | Location | string
LocationCode | #location +code | LocationCode | Location | string
LocationType | #location +type | LocationType | Location | string
StateName | #state +name | StateName | Location | string
StateCode | #state +code | StateCode | Location | string
AreaName | #area +name | AreaName | Location | string
AreaCode | #area +code | AreaCode | Location | string
Latitude | #geo +lat | Latitude | Location | float
Longitude | #geo +long | Longitude | Location | float
AccessStatus | #access +status | AccessStatus | Location | string
ItemCode | #item +code | ItemCode | AidItem | string
ItemName | #item +name | ItemName | AidItem | string
ItemType | #item +type | ItemType | AidItem | string
Unit | #item +unit | Unit | AidItem | string
Quantity | #item +q | Quantity | AidItem | integer
Name | #sector +name | Name | AidItem | string
Cluster | #cluster +name | Cluster | AidItem | string
InventoryCode | #inventory +code | InventoryCode | Inventory | string
InventoryName | #inventory +name | InventoryName | Inventory | string
StoredItemQuantity | #inventory +quantity | StoredItemQuantity | Inventory | string
InventoryStatus | #inventory +status | InventoryStatus | Inventory | string
StorageCapacity | #storage +capacity | StorageCapacity | Inventory | integer
EmployeeCode | #employee +code | EmployeeCode | Employee | integer
EmployeeName | #employee +name | EmployeeName | Employee | string
Status | #employee +status | Status | Employee | string
EmploymentType | #employee +type | EmploymentType | Employee | string
HireDate | #employee +hire +date | HireDate | Employee | date
JobTitle | #employee +title | JobTitle | Employee | string
ReceiptCode | #receipt +code | ReceiptCode | Receipt | string
Date | #receipt +date | Date | Receipt | string
"""


def get_client():
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise HTTPException(422, "ANTHROPIC_API_KEY not set. Add it to .env or use Settings in the app.")
    return anthropic.Anthropic(api_key=key)


def range_to_xsd(r: str):
    return {"string": XSD.string, "integer": XSD.integer, "int": XSD.integer,
            "float": XSD.float, "date": XSD.date}.get(r, XSD.string)


def build_graph(sheets, column_tags):
    g = Graph()
    g.bind("hxlo", HXLO)
    g.bind("hxld", HXLD)
    g.bind("xsd", XSD)
    for sheet in sheets:
        name = sheet["name"]
        data = sheet["data"]
        tags = column_tags.get(name, {})
        if not tags or len(data) < 2:
            continue
        for ri, row in enumerate(data[1:], 1):
            if not any(str(c).strip() for c in row):
                continue
            sid = re.sub(r"[^a-zA-Z0-9]", "_", name)
            row_uri = HXLD[f"{sid}_row_{ri}"]
            g.add((row_uri, RDF.type, HXLO.DataRow))
            for ci_str, tag in tags.items():
                ci = int(ci_str)
                val = row[ci] if ci < len(row) else ""
                if val is None or str(val).strip() == "":
                    continue
                g.add((row_uri, HXLO[tag["uri"]], Literal(str(val), datatype=range_to_xsd(tag.get("range", "string")))))
    return g


# ── API status ────────────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    return {"status": "ok", "api_key_configured": bool(os.getenv("ANTHROPIC_API_KEY", "").strip())}


# ── Upload ────────────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(422, "Could not parse file. Please upload a valid .xlsx file.")
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(c) if c is not None else "" for c in row])
            if len(rows) > 1000:
                break
        sheets.append({"name": name, "data": rows})
    wb.close()
    return {"sheets": sheets, "filename": file.filename}


# ── Serialize ─────────────────────────────────────────────────────────────────
class SerializeReq(BaseModel):
    sheets: List[Dict]
    columnTags: Dict


@app.post("/api/serialize")
def serialize(req: SerializeReq):
    g = build_graph(req.sheets, req.columnTags)
    if len(g) == 0:
        raise HTTPException(422, "No tagged data found. Please tag at least one column first.")
    return {"turtle": g.serialize(format="turtle"), "triple_count": len(g)}


# ── Export HXL Excel ──────────────────────────────────────────────────────────
class ExportReq(BaseModel):
    sheets: List[Dict]
    columnTags: Dict
    active_sheet: int = 0


@app.post("/api/export-hxl")
def export_hxl(req: ExportReq):
    sheet = req.sheets[req.active_sheet] if req.active_sheet < len(req.sheets) else None
    if not sheet:
        raise HTTPException(422, "No sheet data.")
    name = sheet["name"]
    data = sheet["data"]
    tags = req.columnTags.get(name, {})
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = name[:31]
    headers = data[0] if data else []
    ws.append(headers)
    ws.append([tags.get(str(ci), {}).get("hxl", "") for ci in range(len(headers))])
    for row in data[1:]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(content=buf.read(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=hxl_{name}.xlsx"})


# ── AI suggest (single column) ────────────────────────────────────────────────
class SuggestReq(BaseModel):
    header: str
    samples: List[str]


@app.post("/api/suggest")
def suggest(req: SuggestReq):
    client = get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=300,
        system=f"""You are an expert in the HXL humanitarian data ontology.
Given a column header and sample values, return the best matching property.

{ONTOLOGY_SUMMARY}

Respond ONLY with valid JSON (no markdown):
{{"label":"...","hxl":"...","uri":"...","domain":"...","range":"..."}}
If no good match: {{"uri":null}}""",
        messages=[{"role": "user", "content": f'Header: "{req.header}"\nSamples: {", ".join(req.samples[:5])}'}]
    )
    text = msg.content[0].text.strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(m.group()) if m else {"uri": None}


# ── AI suggest all columns ────────────────────────────────────────────────────
class ColInfo(BaseModel):
    sheet: str
    col_index: int
    header: str
    samples: List[str]


class SuggestAllReq(BaseModel):
    columns: List[ColInfo]


@app.post("/api/suggest-all")
def suggest_all(req: SuggestAllReq):
    if not req.columns:
        return {"suggestions": []}
    client = get_client()
    col_list = "\n".join(
        f'{i}. Sheet="{c.sheet}" Col={c.col_index} Header="{c.header}" Samples=[{", ".join(c.samples[:4])}]'
        for i, c in enumerate(req.columns)
    )
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=4000,
        system=f"""You are an expert in the HXL humanitarian data ontology.
Suggest the best matching property for each column.

{ONTOLOGY_SUMMARY}

Respond ONLY with a JSON array — one object per column in the same order:
{{"col_index":N,"sheet":"...","uri":"...","label":"...","hxl":"...","domain":"...","range":"..."}}
If no match for a column: {{"col_index":N,"sheet":"...","uri":null}}
No markdown fences.""",
        messages=[{"role": "user", "content": f"Columns:\n{col_list}"}]
    )
    text = msg.content[0].text.strip()
    try:
        return {"suggestions": json.loads(text)}
    except Exception:
        m = re.search(r'\[.*\]', text, re.DOTALL)
        return {"suggestions": json.loads(m.group()) if m else []}


# ── Natural language SPARQL query ─────────────────────────────────────────────
class QueryReq(BaseModel):
    sheets: List[Dict]
    columnTags: Dict
    question: str


@app.post("/api/query")
def query(req: QueryReq):
    client = get_client()
    g = build_graph(req.sheets, req.columnTags)
    if len(g) == 0:
        raise HTTPException(422, "No tagged data to query. Please tag columns first.")
    turtle_str = g.serialize(format="turtle")

    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1000,
        system=f"""You are a SPARQL expert for the HXL humanitarian ontology.
PREFIX hxlo: <https://ontology.humanitariandata.org/hxl-ontology#>
PREFIX hxld: <https://ontology.humanitariandata.org/hxl-data#>
All rows are hxlo:DataRow with properties like hxlo:BeneficiaryName, hxlo:CityName etc.

{ONTOLOGY_SUMMARY}

Given Turtle data and a question, generate SPARQL and return ONLY JSON (no markdown):
{{"sparql":"SELECT...WHERE{{...}}","explanation":"what this does"}}""",
        messages=[{"role": "user", "content": f"Data:\n{turtle_str[:5000]}\n\nQuestion: {req.question}"}]
    )
    text = msg.content[0].text.strip()
    try:
        ai = json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        ai = json.loads(m.group()) if m else {}

    sparql = ai.get("sparql", "")
    if not sparql:
        return {"sparql": "", "columns": [], "rows": [], "summary": "Could not generate SPARQL.", "triple_count": len(g)}

    try:
        results = g.query(sparql)
        columns = [str(v) for v in (results.vars or [])]
        rows = [[str(r[v]) if r[v] is not None else "" for v in results.vars] for r in results]
    except Exception as e:
        return {"sparql": sparql, "columns": [], "rows": [], "summary": f"SPARQL error: {e}", "triple_count": len(g)}

    return {
        "sparql": sparql,
        "columns": columns,
        "rows": rows,
        "summary": (ai.get("explanation", "") + f" Found {len(rows)} result(s).").strip(),
        "triple_count": len(g)
    }


# ── Set API key at runtime ────────────────────────────────────────────────────
class SetKeyReq(BaseModel):
    key: str


@app.post("/api/set-key")
def set_key(req: SetKeyReq):
    os.environ["ANTHROPIC_API_KEY"] = req.key.strip()
    return {"ok": True}


# ── Serve frontend ────────────────────────────────────────────────────────────
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 50)
    print("  HXL Ontology Tagger")
    print("  Open: http://localhost:8000")
    print("=" * 50 + "\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
