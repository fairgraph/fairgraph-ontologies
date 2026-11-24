"""One-off import: builds vocabularies/species and vocabularies/sample-controls from the species
lists used by the MetaTree data in FAIRGraph (plant_species.ttl, other_species.ttl,
extra_plant_species.ttl).

Those files name taxa with UniProt web addresses (https://uniprot.org/taxonomy/<id>), whose IDs
are NCBI Taxonomy IDs. Each becomes http://purl.obolibrary.org/obo/NCBITaxon_<id>, with NCBI's
current scientific name as its label (fetched with NCBI E-utilities), the name in the source
file as a synonym when it differs, and UniProt's taxon URI as an exact match.
The few terms without a numeric ID are curated by hand in CURATED below.

Usage: python import_metatree_species.py <folder with the three .ttl files> <repository root>
"""
import re
import sys
import time

import rdflib
import requests
from rdflib import RDF, RDFS, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, SKOS

FS = Namespace("https://fairgraph.nl/ontology#")
OBO = Namespace("http://purl.obolibrary.org/obo/")
UNIPROT_TAXON = "http://purl.uniprot.org/taxonomy/"
LOCAL = "https://w3id.org/fairgraph/vocab/"
SOURCE_FILES = ["plant_species.ttl", "other_species.ttl", "extra_plant_species.ttl"]
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Source URI -> how it is curated. "taxon": an NCBI taxon. "local": a FAIRGraph term in a
# vocabulary, with broadMatch to its NCBI taxon if any. Checked against NCBI on 2026-11-24.
CURATED = {
    # Misspelt names of NCBI taxa
    "https://sils.uva.nl/ontology#ERYSCHEIR": {"taxon": 330168, "typo": True},   # Erysimum cheiranthoides
    "https://sils.uva.nl/ontology#EUCLSYRIA": {"taxon": 345537, "typo": True},   # Euclidium syriacum
    # A strain NCBI has (Pseudomonas protegens CHA0)
    "https://uniprot.org/taxonomy/PWCHA0": {"taxon": 1124983},
    # Strains and varieties NCBI does not have
    "https://uniprot.org/taxonomy/A0A1N7U5Z2": {"local": "species", "id": "pseudomonas-simiae-wcs417",
                                               "label": "Pseudomonas simiae WCS417", "broad": 321846},
    "https://uniprot.org/taxonomy/PWCS315": {"local": "species", "id": "pseudomonas-wcs315",
                                            "label": "Pseudomonas sp. WCS315", "broad": 286},
    "https://sils.uva.nl/ontology#BORivera": {"local": "species", "id": "brassica-oleracea-var-rivera",
                                             "label": "Brassica oleracea var. rivera", "broad": 3712},
    "https://uniprot.org/taxonomy/3712k": {"local": "species", "id": "brassica-oleracea-kimmeridge",
                                          "label": "Brassica oleracea Kimmeridge", "broad": 3712, "typo": True},
    # Not taxa: controls used in place of a plant
    "https://sils.uva.nl/ontology#ctrl001": {"local": "sample-controls", "id": "unplanted-soil",
                                            "label": "Unplanted soil control"},
    "https://sils.uva.nl/ontology#ctrlSOIL02": {"local": "sample-controls", "id": "soil", "label": "Soil"},
}


# Taxon IDs NCBI has merged into another taxon (its "AkaTaxIds"): old ID -> current ID.
# Checked with efetch on 2026-11-24. The old ID is kept as dcterms:replaces.
MERGED = {
    3613: 262928,      # Colletia armata -> Colletia hystrix
    3840: 3091605,     # Vigna unguiculata subsp. cylindrica
    4302: 185535,      # Nemopanthus mucronatus -> Ilex mucronata
    13230: 3128859,    # Prosopis juliflora -> Neltuma juliflora
    29728: 2982281,    # Sinapis arvensis -> Mutarda arvensis
    52970: 3034,       # Rhodomonas salina
    53027: 3062406,    # Bucegia romanica -> Marchantia romanica
    65404: 173545,     # Polysiphonia urceolata -> Polysiphonia stricta
    102746: 1628030,   # Hieracium piloselloides -> Pilosella piloselloides
}


def read_sources(folder):
    terms = {}
    for name in SOURCE_FILES:
        g = rdflib.Graph().parse(f"{folder}/{name}")
        for s in g.subjects(RDF.type, None):
            terms[str(s)] = str(g.value(s, RDFS.label)).strip()
    return terms


def ncbi_names(ids):
    """NCBI Taxonomy ID -> current scientific name, 200 IDs per request."""
    session = requests.Session()
    session.headers["User-Agent"] = "fairgraph-vocabulary-import"
    names, ids = {}, sorted(set(ids))
    for i in range(0, len(ids), 200):
        batch = ids[i:i + 200]
        for attempt in range(5):  # E-utilities answers 502/429 now and then
            resp = session.post(EUTILS, data={"db": "taxonomy", "retmode": "json", "id": ",".join(map(str, batch))},
                                timeout=60)
            if resp.status_code < 500 and resp.status_code != 429:
                break
            time.sleep(2 ** attempt)
        resp.raise_for_status()
        result = resp.json()["result"]
        for uid in result.get("uids", []):
            doc = result[uid]
            if doc.get("scientificname") and not doc.get("error"):
                names[int(uid)] = doc["scientificname"]
        time.sleep(0.4)  # NCBI allows 3 requests a second without an API key
    return names


def new_graph():
    g = rdflib.Graph()
    for prefix, ns in (("fs", FS), ("obo", OBO), ("skos", SKOS), ("dcterms", DCTERMS),
                       ("uniprot", UNIPROT_TAXON), ("species", LOCAL + "species/"),
                       ("controls", LOCAL + "sample-controls/")):
        g.bind(prefix, ns)
    return g


def add_synonym(g, term, name, label, typo=False):
    """The source file's name, when the label differs: an older or other name is an alternative
    label, a misspelling a hidden label (not shown, but still resolved on import)."""
    if name and name.lower() != label.lower():
        g.add((term, SKOS.hiddenLabel if typo else SKOS.altLabel, Literal(name)))


def main(folder, root):
    sources = read_sources(folder)
    numeric = {uri: int(uri.rsplit("/", 1)[1]) for uri in sources
               if re.fullmatch(r"https://uniprot\.org/taxonomy/\d+", uri)}
    numeric = {uri: MERGED.get(n, n) for uri, n in numeric.items()}
    missing = [u for u in sources if u not in numeric and u not in CURATED]
    if missing:
        sys.exit(f"Not curated: {missing}")
    wanted = set(numeric.values()) | {c["taxon"] for c in CURATED.values() if "taxon" in c} \
        | {c["broad"] for c in CURATED.values() if "broad" in c}
    names = ncbi_names(wanted)
    print(f"NCBI: {len(names)} of {len(wanted)} taxon IDs found")

    graphs = {"species": new_graph(), "sample-controls": new_graph()}
    species = graphs["species"]
    not_in_ncbi = []

    def add_taxon(taxon_id, source_name, source_uri, typo=False):
        term = OBO[f"NCBITaxon_{taxon_id}"]
        label = names.get(taxon_id)
        if label is None:
            not_in_ncbi.append((source_uri, source_name))
            return
        if (term, RDF.type, FS.Species) in species:
            # Two source terms for one taxon: keep the other name as a synonym
            add_synonym(species, term, source_name.rstrip("."), str(species.value(term, RDFS.label)), typo)
            return
        species.add((term, RDF.type, FS.Species))
        species.add((term, RDFS.label, Literal(label)))
        add_synonym(species, term, source_name.rstrip("."), label, typo)
        species.add((term, SKOS.exactMatch, URIRef(f"{UNIPROT_TAXON}{taxon_id}")))

    for uri, taxon_id in sorted(numeric.items(), key=lambda kv: kv[1]):
        add_taxon(taxon_id, sources[uri], uri)

    for old, new in MERGED.items():
        if (OBO[f"NCBITaxon_{new}"], RDF.type, FS.Species) in species:
            species.add((OBO[f"NCBITaxon_{new}"], DCTERMS.replaces, OBO[f"NCBITaxon_{old}"]))

    for uri, cur in CURATED.items():
        if "taxon" in cur:
            add_taxon(cur["taxon"], sources[uri], uri, cur.get("typo", False))
            species.add((OBO[f"NCBITaxon_{cur['taxon']}"], DCTERMS.replaces, URIRef(uri)))
            continue
        g = graphs[cur["local"]]
        term = URIRef(f"{LOCAL}{cur['local']}/{cur['id']}")
        g.add((term, RDF.type, FS.Species if cur["local"] == "species" else FS.ControlSample))
        g.add((term, RDFS.label, Literal(cur["label"])))
        add_synonym(g, term, sources[uri], cur["label"], cur.get("typo", False))
        if "broad" in cur:
            g.add((term, SKOS.broadMatch, OBO[f"NCBITaxon_{cur['broad']}"]))
        g.add((term, DCTERMS.replaces, URIRef(uri)))

    # A synonym from the source files that is another term's name, or a synonym of several terms,
    # is ambiguous: the source named a strain like its species ("Phytophthora infestans" for
    # strain T30-4). Drop it, so a name resolves to one term only.
    for g in graphs.values():
        def key(s):
            return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))
        labels = {key(o): s for s, o in g.subject_objects(RDFS.label)}
        owners = {}
        for pred in (SKOS.altLabel, SKOS.hiddenLabel):
            for s, o in g.subject_objects(pred):
                owners.setdefault(key(o), set()).add(s)
        for pred in (SKOS.altLabel, SKOS.hiddenLabel):
            for s, o in list(g.subject_objects(pred)):
                if (key(o) in labels and labels[key(o)] != s) or len(owners[key(o)]) > 1:
                    g.remove((s, pred, o))
                    print(f"dropped ambiguous synonym '{o}' of {s} ({g.value(s, RDFS.label)})")

    if not_in_ncbi:
        sys.exit(f"Not found in NCBI Taxonomy (merged or deleted IDs?), curate them first: {not_in_ncbi}")

    headers = {
        "species": "# Species: NCBI Taxonomy taxa (http://purl.obolibrary.org/obo/NCBITaxon_<id>) used by FAIRGraph\n"
                   "# databases, plus strains and varieties NCBI does not have (https://w3id.org/fairgraph/vocab/species/...).\n"
                   "# Generated by scripts/import_metatree_species.py; edit by pull request, see README.md.\n",
        "sample-controls": "# Sample controls: controls used in place of a biological material.\n"
                           "# Generated by scripts/import_metatree_species.py; edit by pull request, see README.md.\n",
    }
    for vocab, g in graphs.items():
        path = f"{root}/vocabularies/{vocab}/vocabulary.ttl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(headers[vocab] + "\n" + g.serialize(format="turtle"))
        print(f"{path}: {len(set(g.subjects(RDF.type, None)))} terms")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
