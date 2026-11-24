"""Checks the repository: run by the GitHub workflow on every pull request, and locally with

    python scripts/validate.py

Exits with status 1 and lists every problem found.
"""
import hashlib
import json
import os
import re
import sys
import unicodedata

import rdflib
import yaml
from rdflib import RDF, RDFS, URIRef
from rdflib.namespace import SKOS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
problems = []


def problem(msg):
    problems.append(msg)


def normalize(label):
    """As FAIRGraph matches names on import: case, accents and punctuation ignored."""
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def check_turtle(path):
    try:
        return rdflib.Graph().parse(path, format="turtle")
    except Exception as e:
        problem(f"{path}: not valid Turtle: {e}")
        return None


def check_vocabulary(folder):
    name = os.path.basename(folder)
    meta_path, ttl = os.path.join(folder, "meta.json"), os.path.join(folder, "vocabulary.ttl")
    try:
        meta = json.load(open(meta_path, encoding="utf-8"))
    except Exception as e:
        problem(f"{meta_path}: {e}")
        return
    for key in ("id", "title", "class", "uri_patterns"):
        if key not in meta:
            problem(f"{meta_path}: '{key}' is missing")
    if meta.get("id") != name:
        problem(f"{meta_path}: id '{meta.get('id')}' differs from the folder name '{name}'")
    g = check_turtle(ttl)
    if g is None:
        return
    cls = URIRef(meta["class"])
    patterns = [re.compile(p) for p in meta.get("uri_patterns", [])]
    terms = set(g.subjects(RDF.type, cls))
    if not terms:
        problem(f"{ttl}: no terms of class {cls}")
    for s in set(g.subjects()) - terms:
        if isinstance(s, URIRef):
            problem(f"{ttl}: {s} is not typed {cls}")
    names = {}
    for term in sorted(terms, key=str):
        if not any(p.match(str(term)) for p in patterns):
            problem(f"{ttl}: {term} is outside this vocabulary's namespaces (uri_patterns in meta.json)")
        labels = list(g.objects(term, RDFS.label))
        if len(labels) != 1:
            problem(f"{ttl}: {term} has {len(labels)} rdfs:label values, needs exactly 1")
        for pred in (RDFS.label, SKOS.altLabel, SKOS.hiddenLabel):
            for label in g.objects(term, pred):
                key = normalize(str(label))
                other = names.setdefault(key, term)
                if other != term:
                    problem(f"{ttl}: '{label}' names both {other} and {term}; an import could not tell them apart")
        for target in g.objects(term, SKOS.broadMatch):
            if target in terms and target == term:
                problem(f"{ttl}: {term} is its own broadMatch")


def check_standard(path):
    try:
        data = yaml.safe_load(open(path, encoding="utf-8"))
    except Exception as e:
        problem(f"{path}: not valid YAML: {e}")
        return
    if not isinstance(data, dict) or not data.get("name"):
        problem(f"{path}: needs a 'name'")
        return
    classes = data.get("classes") or []
    if not isinstance(classes, list) or not classes:
        problem(f"{path}: needs a list of 'classes'")
        return
    names = {c.get("name") for c in classes if isinstance(c, dict)}
    for i, cls in enumerate(classes):
        if not isinstance(cls, dict) or not cls.get("name") or not cls.get("uri"):
            problem(f"{path}: class {i + 1} needs a 'name' and a 'uri'")
            continue
        for ref in ("extends", "hierarchy_child"):
            if cls.get(ref) and cls[ref] not in names:
                problem(f"{path}: class '{cls['name']}' {ref} '{cls[ref]}', which is not a class here")
        for p in cls.get("properties") or []:
            if not isinstance(p, dict) or not p.get("name") or not p.get("path"):
                problem(f"{path}: class '{cls['name']}' has a property without a 'name' and 'path'")
    vocab_ids = set(os.listdir(os.path.join(ROOT, "vocabularies")))
    for v in data.get("vocabularies") or []:
        if v not in vocab_ids:
            problem(f"{path}: vocabulary '{v}' does not exist")


def check_catalog():
    path = os.path.join(ROOT, "catalog.json")
    try:
        catalog = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        problem(f"{path}: {e}")
        return
    listed = [catalog["ontology"]] + catalog["vocabularies"] + catalog["standards"]
    for item in listed:
        f = os.path.join(ROOT, item["file"])
        if not os.path.isfile(f):
            problem(f"catalog.json lists {item['file']}, which does not exist")
        elif hashlib.sha256(open(f, "rb").read()).hexdigest() != item["sha256"]:
            problem(f"catalog.json: {item['file']} changed; run scripts/build_catalog.py")
    files = {i["file"] for i in listed}
    for folder, ext in (("standards", (".yaml", ".yml")), ("vocabularies", ("vocabulary.ttl",))):
        for dirpath, _, names in os.walk(os.path.join(ROOT, folder)):
            for n in names:
                rel = os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                if n.endswith(ext) and rel not in files:
                    problem(f"{rel} is not in catalog.json; run scripts/build_catalog.py")


def main():
    check_turtle(os.path.join(ROOT, "ontology", "fairgraph.ttl"))
    vocab_dir = os.path.join(ROOT, "vocabularies")
    for name in sorted(os.listdir(vocab_dir)):
        if os.path.isdir(os.path.join(vocab_dir, name)):
            check_vocabulary(os.path.join(vocab_dir, name))
    std_dir = os.path.join(ROOT, "standards")
    for name in sorted(os.listdir(std_dir)):
        if name.endswith((".yaml", ".yml")):
            check_standard(os.path.join(std_dir, name))
    check_catalog()
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
