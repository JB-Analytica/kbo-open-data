"""Build a small, fake KBO extract with the real file and column layout.

It exists so the pipeline can be run and tested end to end by someone who has not
registered with FOD Economie, and so CI never needs a real extract. The shapes are
deliberately lifelike -- mostly small companies, a long tail of rare legal forms so the
small-cell suppression rule has something to bite on, and a handful of natural persons
that must never reach a mart.

Nothing in here is real. Every entity number, date and postcode is generated.
"""

from __future__ import annotations

import csv
import io
import random
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SNAPSHOT_DATE = date(2026, 9, 7)

# (code, NL description, EN description). Code "1" is the natural person; the pipeline is
# not allowed to know that number, it has to find it through the description.
TYPE_OF_ENTERPRISE = [
    ("1", "Natuurlijk persoon", "Natural person"),
    ("2", "Rechtspersoon", "Legal person"),
]

STATUS = [("AC", "Actief", "Active"), ("ST", "Stopgezet", "Stopped")]

JURIDICAL_SITUATION = [
    ("000", "Normale toestand", "Normal situation"),
    ("014", "Gerechtelijke reorganisatie", "Judicial reorganisation"),
]

# code, NL, EN, rough weight in the population.
JURIDICAL_FORM = [
    ("610", "Besloten vennootschap", "Private limited company", 46),
    ("014", "Vennootschap onder firma", "General partnership", 6),
    ("015", "Naamloze vennootschap", "Public limited company", 12),
    ("017", "Commanditaire vennootschap", "Limited partnership", 3),
    ("125", "Vereniging zonder winstoogmerk", "Non-profit association", 18),
    ("706", "Coöperatieve vennootschap", "Cooperative company", 4),
    ("029", "Buitenlandse entiteit", "Foreign entity", 1),
    ("416", "Openbare instelling", "Public institution", 1),
    # Deliberately rare, so at least one legal-form cell falls under the suppression floor.
    (
        "065",
        "Europese economische samenwerkingsverbanden",
        "European economic interest grouping",
        1,
    ),
    ("140", "Private stichting", "Private foundation", 1),
]

NACE_2008 = [
    ("62010", "Ontwerpen en programmeren van computerprogramma's", "Computer programming", 9),
    ("70220", "Overige adviesbureaus op het gebied van bedrijfsbeheer", "Business consultancy", 11),
    (
        "41201",
        "Algemene bouw van residentiele gebouwen",
        "Construction of residential buildings",
        10,
    ),
    ("56101", "Eetgelegenheden met volledige bediening", "Full-service restaurants", 7),
    ("47111", "Detailhandel in niet-gespecialiseerde winkels", "Non-specialised retail", 6),
    ("86210", "Huisartspraktijken", "General medical practice", 5),
    (
        "68201",
        "Verhuur en exploitatie van eigen residentieel onroerend goed",
        "Renting of own property",
        8,
    ),
    ("01130", "Teelt van groenten en meloenen", "Growing of vegetables", 3),
    ("49410", "Goederenvervoer over de weg", "Freight transport by road", 4),
    ("96021", "Haarverzorging", "Hairdressing", 3),
    ("85592", "Beroepsopleiding", "Vocational education", 2),
    ("64200", "Holdings", "Activities of holding companies", 6),
    ("10710", "Vervaardiging van brood en van vers banketbakkerswerk", "Manufacture of bread", 2),
    ("35111", "Productie van elektriciteit", "Production of electricity", 1),
    ("90011", "Beoefening van uitvoerende kunsten", "Performing arts", 2),
]

NACE_2025 = [("62010", "Computerprogrammering", "Computer programming", 1)]

ACTIVITY_GROUP = [("001", "BTW-activiteiten", "VAT activities")]
CLASSIFICATION = [
    ("MAIN", "Hoofdactiviteit", "Main activity"),
    ("SECO", "Nevenactiviteit", "Secondary activity"),
]
TYPE_OF_ADDRESS = [
    ("REGO", "Maatschappelijke zetel", "Registered office"),
    ("SEAT", "Vestigingseenheid", "Establishment unit"),
]

# (zipcode, municipality) pairs spread over every province plus Brussels.
PLACES = [
    ("1000", "Brussel"),
    ("1180", "Ukkel"),
    ("1300", "Waver"),
    ("1500", "Halle"),
    ("2000", "Antwerpen"),
    ("2800", "Mechelen"),
    ("3000", "Leuven"),
    ("3500", "Hasselt"),
    ("4000", "Luik"),
    ("5000", "Namen"),
    ("6000", "Charleroi"),
    ("6700", "Aarlen"),
    ("7000", "Bergen"),
    ("8000", "Brugge"),
    ("8500", "Kortrijk"),
    ("9000", "Gent"),
    ("9300", "Aalst"),
]

FILES = (
    "meta.csv",
    "code.csv",
    "enterprise.csv",
    "establishment.csv",
    "address.csv",
    "activity.csv",
    "branch.csv",
    "denomination.csv",
    "contact.csv",
)


@dataclass
class Enterprise:
    number: str
    status: str
    juridical_situation: str
    type_of_enterprise: str
    juridical_form: str
    start_date: date
    zipcode: str
    municipality: str
    nace_code: str
    nace_version: str
    establishments: int


def _be_date(value: date) -> str:
    """KBO writes dates day-first. Getting this wrong is the classic bite."""
    return value.strftime("%d-%m-%Y")


def _enterprise_number(n: int) -> str:
    return f"{n // 1_000_000:04d}.{(n // 1000) % 1000:03d}.{n % 1000:03d}"


def _establishment_number(n: int) -> str:
    return f"2.{n // 1_000_000:03d}.{(n // 1000) % 1000:03d}.{n % 1000:03d}"


def _weighted(rng: random.Random, rows: list[tuple]) -> tuple:
    return rng.choices(rows, weights=[r[-1] for r in rows], k=1)[0]


def build_enterprises(rng: random.Random, count: int) -> list[Enterprise]:
    enterprises: list[Enterprise] = []
    for i in range(count):
        # Roughly a quarter of KBO registrations are natural persons (sole traders).
        natural = rng.random() < 0.25
        type_of_enterprise = "1" if natural else "2"
        zipcode, municipality = rng.choice(PLACES)
        nace_version, nace_pool = (
            ("2008", NACE_2008) if rng.random() < 0.95 else ("2025", NACE_2025)
        )
        establishments = rng.choices([0, 1, 2, 4, 8, 25], weights=[18, 60, 12, 6, 3, 1], k=1)[0]
        enterprises.append(
            Enterprise(
                number=_enterprise_number(200_000_000 + i * 7),
                status=rng.choices(["AC", "ST"], weights=[94, 6], k=1)[0],
                juridical_situation=rng.choices(["000", "014"], weights=[97, 3], k=1)[0],
                type_of_enterprise=type_of_enterprise,
                # Natural persons carry no legal form in KBO.
                juridical_form="" if natural else _weighted(rng, JURIDICAL_FORM)[0],
                start_date=date(rng.randint(1970, 2026), rng.randint(1, 12), rng.randint(1, 28)),
                zipcode=zipcode,
                municipality=municipality,
                nace_code=_weighted(rng, nace_pool)[0],
                nace_version=nace_version,
                establishments=establishments,
            )
        )
    return enterprises


def _csv(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _code_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    groups = [
        ("TypeOfEnterprise", [r[:3] for r in TYPE_OF_ENTERPRISE]),
        ("Status", [r[:3] for r in STATUS]),
        ("JuridicalSituation", [r[:3] for r in JURIDICAL_SITUATION]),
        ("JuridicalForm", [r[:3] for r in JURIDICAL_FORM]),
        ("Nace2008", [r[:3] for r in NACE_2008]),
        ("Nace2025", [r[:3] for r in NACE_2025]),
        ("ActivityGroup", [r[:3] for r in ACTIVITY_GROUP]),
        ("Classification", [r[:3] for r in CLASSIFICATION]),
        ("TypeOfAddress", [r[:3] for r in TYPE_OF_ADDRESS]),
    ]
    for category, entries in groups:
        for code, nl, en in entries:
            rows.append([category, code, "NL", nl])
            rows.append([category, code, "FR", f"{nl} (FR)"])
            rows.append([category, code, "EN", en])
    return rows


def write_extract(path: Path, count: int = 400, seed: int = 20260907) -> Path:
    """Write a synthetic KBO zip to `path` and return it."""
    rng = random.Random(seed)
    enterprises = build_enterprises(rng, count)

    establishment_rows: list[list[str]] = []
    address_rows: list[list[str]] = []
    activity_rows: list[list[str]] = []
    branch_rows: list[list[str]] = []
    establishment_seq = 0

    for e in enterprises:
        address_rows.append(
            [
                e.number,
                "REGO",
                "",
                "",
                e.zipcode,
                e.municipality,
                f"{e.municipality} (FR)",
                "Teststraat",
                "Rue Test",
                "1",
                "",
                "",
                "",
            ]
        )
        activity_rows.append([e.number, "001", e.nace_version, e.nace_code, "MAIN"])
        if rng.random() < 0.3:
            secondary = _weighted(rng, NACE_2008)[0]
            activity_rows.append([e.number, "001", "2008", secondary, "SECO"])
        for _ in range(e.establishments):
            establishment_seq += 1
            number = _establishment_number(establishment_seq * 13)
            establishment_rows.append([number, _be_date(e.start_date), e.number])
            address_rows.append(
                [
                    number,
                    "SEAT",
                    "",
                    "",
                    e.zipcode,
                    e.municipality,
                    f"{e.municipality} (FR)",
                    "Teststraat",
                    "Rue Test",
                    "1",
                    "",
                    "",
                    "",
                ]
            )
        if rng.random() < 0.02:
            branch_rows.append(
                [f"9.{establishment_seq:03d}.000.000", _be_date(e.start_date), e.number]
            )

    contents = {
        "meta.csv": _csv(
            ["Variable", "Value"],
            [
                ["SnapshotDate", _be_date(SNAPSHOT_DATE)],
                ["ExtractTimestamp", f"{SNAPSHOT_DATE.isoformat()}T04:30:00.000"],
                ["ExtractType", "full"],
                ["ExtractNumber", "0142"],
                ["Version", "1.0"],
            ],
        ),
        "code.csv": _csv(["Category", "Code", "Language", "Description"], _code_rows()),
        "enterprise.csv": _csv(
            [
                "EnterpriseNumber",
                "Status",
                "JuridicalSituation",
                "TypeOfEnterprise",
                "JuridicalForm",
                "JuridicalFormCAC",
                "StartDate",
            ],
            [
                [
                    e.number,
                    e.status,
                    e.juridical_situation,
                    e.type_of_enterprise,
                    e.juridical_form,
                    "",
                    _be_date(e.start_date),
                ]
                for e in enterprises
            ],
        ),
        "establishment.csv": _csv(
            ["EstablishmentNumber", "StartDate", "EnterpriseNumber"], establishment_rows
        ),
        "address.csv": _csv(
            [
                "EntityNumber",
                "TypeOfAddress",
                "CountryNL",
                "CountryFR",
                "Zipcode",
                "MunicipalityNL",
                "MunicipalityFR",
                "StreetNL",
                "StreetFR",
                "HouseNumber",
                "Box",
                "ExtraAddressInfo",
                "DateStrikingOff",
            ],
            address_rows,
        ),
        "activity.csv": _csv(
            ["EntityNumber", "ActivityGroup", "NaceVersion", "NaceCode", "Classification"],
            activity_rows,
        ),
        "branch.csv": _csv(["Id", "StartDate", "EnterpriseNumber"], branch_rows),
        # These two exist in a real extract and the pipeline must never open them. They are
        # written with obviously fake personal data so a test can assert it stayed out.
        "denomination.csv": _csv(
            ["EntityNumber", "Language", "TypeOfDenomination", "Denomination"],
            [[e.number, "2", "001", f"Fictief Bedrijf {i}"] for i, e in enumerate(enterprises)],
        ),
        "contact.csv": _csv(
            ["EntityNumber", "EntityContact", "ContactType", "Value"],
            [
                [e.number, "ENT", "EMAIL", f"nobody{i}@example.invalid"]
                for i, e in enumerate(enterprises)
            ],
        ),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            zf.writestr(name, contents[name])
    return path


if __name__ == "__main__":  # pragma: no cover
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/KboOpenData_SYNTHETIC_Full.zip")
    print(write_extract(target))
