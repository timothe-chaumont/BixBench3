"""Unit tests for the v2f enrichment validator (synthetic toy tables, not study data)."""

from bixbench3.inspect_harness.enrichment_validator import (
    enrichment_targets,
    gene_set_size_limits,
    parse_output_contract,
    validate,
)

PROMPT = """
## Method Guidance

Use the MSigDB v6.2 canonical pathway collections, keeping gene sets with 5 to 500 mapped genes.

## Required Outputs

### `deseq2_significant_degs`

- Path: `outputs/deseq2_significant_degs.csv`
- Format: `csv`
- Description: DESeq2 rows with adjusted p-value below 0.10.
- Row key: `contrast_gene_id`
- Rows: The contrast_gene_id must be formatted as timepoint|concentration|gene_probe_id, for example day90|6000ppm|<gene_probe_id>.
- Required columns: `contrast_gene_id`, `timepoint`, `concentration`, `gene_probe_id`, `padj`

### `piano_preranked_gsea`

- Path: `outputs/piano_preranked_gsea.csv`
- Format: `csv`
- Description: Significant directional PIANO pre-ranked GSEA results, using FDR below 0.10. Direction up ... direction down ...
- Row key: `gsea_result_id`
- Rows: The gsea_result_id must be formatted as timepoint|concentration|direction|gene_set.
- Example row identifiers: `day7|600ppm|up|<gene_set_name>`, `day90|6000ppm|down|<gene_set_name>`
- Required columns: `gsea_result_id`, `timepoint`, `concentration`, `direction`, `gene_set`, `genes_total`, `p_value`, `fdr`

### `dna_damage_enrichment`

- Path: `outputs/dna_damage_enrichment.csv`
- Format: `csv`
- Description: Targeted hypergeometric enrichment results for curated DNA damage gene sets.
- Row key: `dna_damage_result_id`
- Rows: One row per tested timepoint, concentration, crossed with the 88 retained DNA-damage gene sets. The dna_damage_result_id must be formatted as timepoint|concentration|gene_set.
- Required columns: `dna_damage_result_id`, `timepoint`, `concentration`, `gene_set`, `p_value_up`, `fdr_up`
"""

DE = "contrast_gene_id,timepoint,concentration,gene_probe_id,padj\nday7|600ppm|A_1,day7,600ppm,A_1,0.01\n"
GOOD_GSEA = (
    "gsea_result_id,timepoint,concentration,direction,gene_set,genes_total,p_value,fdr\n"
    "day7|600ppm|up|SET_A,day7,600ppm,up,SET_A,20,0.001,0.02\n"
    "day7|600ppm|down|SET_B,day7,600ppm,down,SET_B,30,0.002,0.05\n"
)
GOOD_DNA = (
    "dna_damage_result_id,timepoint,concentration,gene_set,p_value_up,fdr_up\n"
    "day7|600ppm|S1,day7,600ppm,S1,0.5,0.9\n"
    "day7|600ppm|S2,day7,600ppm,S2,1,1\n"
)


def files(gsea=GOOD_GSEA, dna=GOOD_DNA, de=DE):
    return {
        "outputs/deseq2_significant_degs.csv": de,
        "outputs/piano_preranked_gsea.csv": gsea,
        "outputs/dna_damage_enrichment.csv": dna,
    }


def test_contract_parsing_finds_enrichment_targets_only():
    specs = parse_output_contract(PROMPT)
    assert [s.artifact_id for s in specs] == ["deseq2_significant_degs", "piano_preranked_gsea", "dna_damage_enrichment"]
    targets = enrichment_targets(specs)
    assert [t.artifact_id for t in targets] == ["piano_preranked_gsea", "dna_damage_enrichment"]
    gsea = targets[0]
    assert gsea.fdr_threshold == 0.10
    assert gsea.key_template == ["timepoint", "concentration", "direction", "gene_set"]
    assert gsea.directions == ["up", "down"]
    assert targets[1].fdr_threshold is None and targets[1].crossed_grid
    assert gene_set_size_limits(PROMPT) == (5, 500)


def test_clean_outputs_pass():
    specs = parse_output_contract(PROMPT)
    assert validate(specs, files(), gene_set_size_limits(PROMPT)) == []


def severities(findings, artifact):
    return [(f.severity, f.message) for f in findings if f.artifact == artifact]


def test_missing_file_and_columns_are_severe():
    specs = parse_output_contract(PROMPT)
    found = validate(specs, files(gsea=None))
    assert any(s == "severe" and "does not exist" in m for s, m in severities(found, "piano_preranked_gsea"))
    found = validate(specs, files(gsea=GOOD_GSEA.replace(",fdr\n", ",q\n", 1)))
    assert any(s == "severe" and "missing required columns: fdr" in m for s, m in severities(found, "piano_preranked_gsea"))


def test_fdr_filter_range_key_and_direction_violations():
    specs = parse_output_contract(PROMPT)
    bad = GOOD_GSEA + "day7|600ppm|sideways|SET_C,day7,600ppm,sideways,SET_C,10,0.2,0.4\n"
    bad += "day7|600ppm|up|SET_A,day7,600ppm,up,SET_A,10,1.7,0.01\n"
    bad += "day28|600ppm|up|SET_D,day7,600ppm,up,SET_D,10,0.01,0.05\n"
    msgs = [m for s, m in severities(validate(specs, files(gsea=bad)), "piano_preranked_gsea") if s == "severe"]
    assert any("fdr >= 0.1" in m for m in msgs)
    assert any("invalid direction labels ['sideways']" in m for m in msgs)
    assert any("outside [0, 1]" in m for m in msgs)
    assert any("duplicate" in m for m in msgs)
    assert any("disagree with their own" in m for m in msgs)


def test_warnings_do_not_count_as_severe():
    specs = parse_output_contract(PROMPT)
    swapped = GOOD_GSEA.replace("0.001,0.02", "0.05,0.01").replace(",20,", ",900,")
    found = severities(validate(specs, files(gsea=swapped), (5, 500)), "piano_preranked_gsea")
    assert all(s == "warning" for s, _ in found) and len(found) == 2
    uneven = GOOD_DNA + "day28|40ppm|S1,day28,40ppm,S1,0.3,0.3\n"
    found = severities(validate(specs, files(dna=uneven)), "dna_damage_enrichment")
    assert [s for s, _ in found] == ["warning", "warning"]  # unknown contrast + uneven grid


def test_submit_gate_blocks_severe_twice_then_allows(monkeypatch):
    import asyncio

    import pytest
    from inspect_ai.tool import ToolError

    import bixbench3.inspect_harness.enrichment_validator as ev

    class FakeStore(dict):
        def set(self, key, value):
            self[key] = value

    class FakeResult:
        success = True

    class FakeSandbox:
        def __init__(self, outputs):
            self.outputs, self.log = outputs, []

        async def read_file(self, path):
            key = "outputs/" + path.removeprefix("/outputs/")
            if self.outputs.get(key) is None:
                raise FileNotFoundError(path)
            return self.outputs[key]

        async def exec(self, cmd, input=None):
            self.log.append(input)
            return FakeResult()

    fake_store = FakeStore()
    box = FakeSandbox(files(gsea=GOOD_GSEA.replace("0.02", "0.5")))
    monkeypatch.setattr(ev, "store", lambda: fake_store)
    monkeypatch.setattr(ev, "sandbox", lambda: box)
    specs = parse_output_contract(PROMPT)
    fake_store.set(ev.STORE_KEY, {"specs": [s.__dict__ for s in specs], "size_limits": [5, 500]})
    fake_store.set(ev.BLOCKS_KEY, 0)

    submit = ev.validated_submit()
    for attempt in (1, 2):
        with pytest.raises(ToolError, match=f"{attempt}/2"):
            asyncio.run(submit(answer="done"))
    assert asyncio.run(submit(answer="done")) == "done"
    assert len(box.log) == 3  # every validation is logged to the work directory

    box.outputs = files()
    fake_store.set(ev.BLOCKS_KEY, 0)
    assert asyncio.run(submit(answer="done")) == "done"
    assert "passed" in asyncio.run(ev.validate_enrichment_outputs()())
