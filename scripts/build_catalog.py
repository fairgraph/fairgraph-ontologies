"""Writes catalog.json and catalog.ttl from the files in this repository.

catalog.json is what FAIRGraph instances read; catalog.ttl is the same as a DCAT catalog,
for other FAIR tools. Run it after every change, before committing:

    python scripts/build_catalog.py [--release v2026.11.0]
"""
import argparse
import hashlib
import json
import os

import rdflib
import yaml
from rdflib import RDF, RDFS, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://w3id.org/fairgraph/"
FS = Namespace("https://fairgraph.nl/ontology#")
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def build(release):
    catalog = {"release": release, "license": LICENSE, "ontology": None, "vocabularies": [], "standards": []}

    onto = os.path.join(ROOT, "ontology", "fairgraph.ttl")
    catalog["ontology"] = {"id": "fairgraph", "title": "FAIRGraph core ontology",
                           "namespace": str(FS), "file": rel(onto), "sha256": sha256(onto)}

    vocab_dir = os.path.join(ROOT, "vocabularies")
    for name in sorted(os.listdir(vocab_dir)):
        folder = os.path.join(vocab_dir, name)
        meta_path, ttl = os.path.join(folder, "meta.json"), os.path.join(folder, "vocabulary.ttl")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path, encoding="utf-8"))
        g = rdflib.Graph().parse(ttl)
        terms = len(set(g.subjects(RDF.type, URIRef(meta["class"]))))
        catalog["vocabularies"].append({**meta, "file": rel(ttl), "sha256": sha256(ttl), "terms": terms})

    std_dir = os.path.join(ROOT, "standards")
    for name in sorted(os.listdir(std_dir)):
        if not name.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(std_dir, name)
        data = yaml.safe_load(open(path, encoding="utf-8"))
        catalog["standards"].append({"id": os.path.splitext(name)[0], "title": data.get("name"),
                                     "description": data.get("description", ""),
                                     "vocabularies": data.get("vocabularies", []),
                                     "file": rel(path), "sha256": sha256(path)})

    with open(os.path.join(ROOT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # The same as DCAT
    g = rdflib.Graph()
    g.bind("dcat", DCAT)
    g.bind("dcterms", DCTERMS)
    cat = URIRef(BASE)
    g.add((cat, RDF.type, DCAT.Catalog))
    g.add((cat, DCTERMS.title, Literal("FAIRGraph ontologies and vocabularies", lang="en")))
    g.add((cat, DCTERMS.license, URIRef(LICENSE)))
    g.add((cat, RDFS.comment, Literal(f"Release {release}")))
    items = [("ontology", catalog["ontology"], "text/turtle")] + \
            [("vocab", v, "text/turtle") for v in catalog["vocabularies"]] + \
            [("standards", s, "application/yaml") for s in catalog["standards"]]
    for kind, item, media in items:
        ds = URIRef(f"{BASE}{kind}/{item['id']}") if kind != "ontology" else URIRef(BASE + "ontology")
        dist = URIRef(f"{BASE}{item['file']}")
        g.add((cat, DCAT.dataset, ds))
        g.add((ds, RDF.type, DCAT.Dataset))
        g.add((ds, DCTERMS.title, Literal(item["title"], lang="en")))
        if item.get("description"):
            g.add((ds, DCTERMS.description, Literal(item["description"], lang="en")))
        g.add((ds, DCAT.distribution, dist))
        g.add((dist, RDF.type, DCAT.Distribution))
        g.add((dist, DCAT.downloadURL, dist))
        g.add((dist, DCAT.mediaType, URIRef(f"https://www.iana.org/assignments/media-types/{media}")))
    with open(os.path.join(ROOT, "catalog.ttl"), "w", encoding="utf-8") as f:
        f.write(g.serialize(format="turtle"))
    print(f"catalog {release}: 1 ontology, {len(catalog['vocabularies'])} vocabularies, "
          f"{len(catalog['standards'])} standards")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="unreleased")
    build(parser.parse_args().release)
