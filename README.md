# FAIRGraph ontologies and vocabularies

The common definitions FAIRGraph instances share: the FAIRGraph core ontology, the metadata
standards databases are created from, and the vocabularies (species, controls, ...) their
records link to. An instance reads [catalog.json](catalog.json) to find them, and stays on the
release it pinned until its administrator upgrades.

Everything here is in the public domain ([CC0 1.0](LICENSE)): reuse it freely, no credit needed.

## Contents

| Folder | What | URIs |
| --- | --- | --- |
| [ontology/](ontology/fairgraph.ttl) | Core ontology: the classes and properties FAIRGraph itself uses | `https://fairgraph.nl/ontology#...` |
| [standards/](standards/) | Metadata standards as YAML templates (MIAPPE, ISA-Tab, Questionnaires, FAIR2GROW GDP) | the standard's own |
| [vocabularies/species/](vocabularies/species/vocabulary.ttl) | 2,382 taxa: NCBI Taxonomy, plus strains and varieties NCBI does not have | `http://purl.obolibrary.org/obo/NCBITaxon_<id>`, `https://w3id.org/fairgraph/vocab/species/<id>` |
| [vocabularies/sample-controls/](vocabularies/sample-controls/vocabulary.ttl) | Controls used in place of a plant, such as unplanted soil | `https://w3id.org/fairgraph/vocab/sample-controls/<id>` |
| [catalog.json](catalog.json), [catalog.ttl](catalog.ttl) | The list of all of the above with checksums; the same as DCAT | |

Persistent URIs are served by [w3id.org](https://w3id.org): `https://w3id.org/fairgraph/...`
redirects to the files here, published with GitHub Pages. See [w3id/](w3id/).

## Term URIs

1. **An external URI wins.** A term that exists in a recognised ontology uses that ontology's URI.
   Species are NCBI Taxonomy taxa as OBO PURLs (`obo:NCBITaxon_4081`), with UniProt's taxon URI
   as `skos:exactMatch`.
2. **Never mint in someone else's namespace.** A term without an external identifier gets a
   FAIRGraph URI, `https://w3id.org/fairgraph/vocab/<vocabulary>/<id>`, linked to the nearest
   external term with `skos:broadMatch` (a strain to its species).
3. **Every term has exactly one `rdfs:label`.** Other names are `skos:altLabel`, misspellings
   `skos:hiddenLabel`. FAIRGraph resolves all three on import, so no name may belong to two terms
   in one vocabulary.
4. **Replaced URIs are kept** with `dcterms:replaces`: merged NCBI taxa, and the URIs existing
   FAIRGraph data used, so that data can be migrated.

## Proposing a change

1. Edit the vocabulary's `vocabulary.ttl` (or a standard's YAML), or add a vocabulary folder with
   a `meta.json` and a `vocabulary.ttl`.
2. Run the checks and rebuild the catalog:

   ```bash
   pip install -r requirements.txt
   python scripts/build_catalog.py
   python scripts/validate.py
   ```

3. Open a pull request. The same checks run on it, and a maintainer reviews it.

A release is a git tag (`v2026.11.0`) made by a maintainer after running
`python scripts/build_catalog.py --release v2026.11.0` and committing the catalog.

## Where the species came from

[scripts/import_metatree_species.py](scripts/import_metatree_species.py) built the first species
and sample-controls vocabularies from the species lists of the MetaTree data in FAIRGraph
(2,385 terms), on 2026-11-24:

- 2,376 terms with a numeric UniProt taxonomy ID became NCBI Taxonomy taxa, named with NCBI's
  current scientific name. 189 older or other names from the lists are kept as synonyms.
- 9 IDs NCBI has merged into another taxon use the current taxon (for example *Prosopis juliflora*
  is now *Neltuma juliflora*), with the old ID as `dcterms:replaces`.
- 9 terms without a numeric ID were curated by hand: two misspelt NCBI species, one NCBI strain
  (*Pseudomonas protegens* CHA0), four strains and varieties NCBI does not have, and two controls
  that are not taxa ("Soil", "Unplanted soil control") moved to sample-controls.
- 14 synonyms were dropped because they named several terms: the lists named some strains like
  their species ("Phytophthora infestans" for strain T30-4). Among them is "Phytophthora
  parasitica", a real synonym of *P. nicotianae* (`obo:NCBITaxon_4792`) that could be added back.
- Not curated yet: some list entries are not species but placeholders, such as
  "unclassified Brassicaceae" (`obo:NCBITaxon_1663633`), labelled "Brassicaceae" in the lists.
