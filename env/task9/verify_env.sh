#!/bin/bash
# Prove that every task 9 step runs with the PREINSTALLED tools only (run it without network).
#   bash /opt/task-env/verify_env.sh [--report FILE] [--manifest FILE]
# Tiny synthetic genome / GTF / reads (no task data, no ground truth):
#   tools      versions of hisat2, featureCounts, samtools, cutadapt, fastqc, perl
#   tagseq     tag-based_RNAseq scripts present and compile (perl -c)
#   fastqc     FastQC runs
#   cutadapt   prompt options -a AAAAAAAA -a AGATCGG -q 15 -m 25
#   hisat2     index build + alignment with --rna-strandness F, samtools sort/index
#   counts     featureCounts -s 1 gives the simulated sense counts, -s 2 gives ~0
#   R          DESeq2, rtracklayer GTF import, clusterProfiler enrichGO (BP, BH) with org.Hs.eg.db offline
# Writes MANIFEST.json (installed versions + embedded GO source dates) when --manifest is given.
set -uo pipefail
REPORT=""; MANIFEST=""
while [ $# -gt 0 ]; do
  case "$1" in --report) REPORT=$2; shift 2;; --manifest) MANIFEST=$2; shift 2;; *) echo "unknown $1"; exit 2;; esac
done
D=/opt/task-env
export MAMBA_ROOT_PREFIX=${MAMBA_ROOT_PREFIX:-/opt/conda}
T() { micromamba run -n task9-tools "$@"; }
W=$(mktemp -d)
declare -A RES
pass() { RES[$1]="PASS $2"; echo "[verify] $1 PASS $2"; }
fail() { RES[$1]="FAIL $2"; echo "[verify] $1 FAIL $2"; }

# ---- versions
HISAT2_V=$(T hisat2 --version 2>/dev/null | head -1 | awk '{print $NF}')
FC_V=$(T featureCounts -v 2>&1 | grep -oE 'v[0-9.]+' | head -1)
SAM_V=$(T samtools --version | head -1 | awk '{print $2}')
CUT_V=$(T cutadapt --version)
FQC_V=$(T fastqc --version | awk '{print $2}')
if [ "$HISAT2_V" = "2.2.1" ] && [ "$FC_V" = "v2.0.1" ]; then pass tools "hisat2 $HISAT2_V featureCounts $FC_V samtools $SAM_V cutadapt $CUT_V fastqc $FQC_V"
else fail tools "hisat2=$HISAT2_V (want 2.2.1) featureCounts=$FC_V (want v2.0.1)"; fi

# ---- tag-based_RNAseq
if [ -f "$D/tag-based_RNAseq/tagseq_clipper.pl" ] && T perl -c "$D/tag-based_RNAseq/tagseq_clipper.pl" >/dev/null 2>&1; then
  pass tagseq "tagseq_clipper.pl compiles (commit ${TAGSEQ_COMMIT:-unknown})"
else fail tagseq "tagseq_clipper.pl missing or does not compile"; fi

# ---- synthetic genome, annotation, forward-stranded reads
python3 - "$W" <<'PY'
import random, sys
w = sys.argv[1]; random.seed(9)
g = "".join(random.choice("ACGT") for _ in range(3000))
open(f"{w}/genome.fa", "w").write(">chrT\n" + "\n".join(g[i:i+60] for i in range(0, len(g), 60)) + "\n")
gtf = []
for gid, name, s, e in [("ENSG00000000001.1", "GENEA", 101, 1100), ("ENSG00000000002.1", "GENEB", 1601, 2600)]:
    attrs = f'gene_id "{gid}"; gene_name "{name}";'
    gtf.append(f"chrT\tsim\tgene\t{s}\t{e}\t.\t+\t.\t{attrs}")
    gtf.append(f'chrT\tsim\texon\t{s}\t{e}\t.\t+\t.\t{attrs} transcript_id "{gid}-T";')
open(f"{w}/genes.gtf", "w").write("\n".join(gtf) + "\n")
reads = []
for (s, e), n in [((101, 1100), 60), ((1601, 2600), 20)]:
    for k in range(n):
        p = random.randint(s - 1, e - 91)
        seq = g[p:p + 90] + "A" * 10          # poly-A tail, removed by cutadapt
        reads.append(seq)
with open(f"{w}/reads.fastq", "w") as fh:
    for i, r in enumerate(reads):
        fh.write(f"@r{i}\n{r}\n+\n{'I' * len(r)}\n")
PY

if T fastqc -q -o "$W" "$W/reads.fastq" >/dev/null 2>&1 && ls "$W"/reads_fastqc.* >/dev/null 2>&1; then pass fastqc "report written"; else fail fastqc "FastQC did not run"; fi

if T cutadapt -a AAAAAAAA -a AGATCGG -q 15 -m 25 --quality-base 33 -o "$W/trimmed.fastq" "$W/reads.fastq" >/dev/null 2>&1 \
   && [ "$(awk 'NR%4==2' "$W/trimmed.fastq" | grep -c 'AAAAAAAAAA$')" -eq 0 ]; then
  pass cutadapt "$(awk 'END{print NR/4}' "$W/trimmed.fastq") reads kept, poly-A removed"
else fail cutadapt "cutadapt failed or poly-A not trimmed"; fi

if T hisat2-build -q "$W/genome.fa" "$W/idx" >/dev/null 2>&1 \
   && T hisat2 -q -x "$W/idx" -U "$W/trimmed.fastq" --rna-strandness F -S "$W/aln.sam" 2>"$W/hisat2.log" \
   && T samtools sort -o "$W/aln.bam" "$W/aln.sam" 2>/dev/null && T samtools index "$W/aln.bam"; then
  pass hisat2 "$(tail -1 "$W/hisat2.log")"
else fail hisat2 "index/alignment failed"; fi

T featureCounts -s 1 -a "$W/genes.gtf" -o "$W/fwd.txt" "$W/aln.bam" >/dev/null 2>&1
T featureCounts -s 2 -a "$W/genes.gtf" -o "$W/rev.txt" "$W/aln.bam" >/dev/null 2>&1
A=$(awk '$1=="ENSG00000000001.1"{print $NF}' "$W/fwd.txt"); B=$(awk '$1=="ENSG00000000002.1"{print $NF}' "$W/fwd.txt")
R=$(awk '!/^#/ && NR>2{s+=$NF} END{print s+0}' "$W/rev.txt")
if [ "${A:-0}" -ge 55 ] && [ "${B:-0}" -ge 18 ] && [ "${R:-99}" -le 2 ]; then pass counts "sense GENEA=$A GENEB=$B, antisense total=$R"
else fail counts "GENEA=${A:-?} GENEB=${B:-?} antisense=${R:-?} (want ~60/~20/0)"; fi

# ---- R side
micromamba run -n task9 Rscript - "$W" "${MANIFEST}" "$HISAT2_V" "$FC_V" "$SAM_V" "$CUT_V" "$FQC_V" "${TAGSEQ_COMMIT:-unknown}" > "$W/r.log" 2>&1 <<'RS'
a <- commandArgs(TRUE); w <- a[1]; manifest <- a[2]
q <- function(p) suppressPackageStartupMessages(library(p, character.only = TRUE))
q("DESeq2"); q("clusterProfiler"); q("org.Hs.eg.db"); q("GO.db"); q("rtracklayer")
dds <- DESeq(makeExampleDESeqDataSet(n = 300, m = 4), quiet = TRUE)
res <- results(dds, alpha = 0.05)
stopifnot(all(c("log2FoldChange", "lfcSE", "stat", "pvalue", "padj") %in% colnames(res)))
gtf <- import(file.path(w, "genes.gtf"))
stopifnot(identical(sort(unique(gtf$gene_name)), c("GENEA", "GENEB")))
genes <- c("CDK1","CCNB1","CCNA2","BUB1","MAD2L1","PLK1","AURKA","CDC20","TOP2A","MKI67","CCNB2","KIF11","CENPF","BUB1B","TTK")
ego <- enrichGO(genes, OrgDb = org.Hs.eg.db, keyType = "SYMBOL", ont = "BP", pAdjustMethod = "BH", pvalueCutoff = 0.05)
df <- as.data.frame(ego)
stopifnot(nrow(df) > 0, all(c("ID","Description","GeneRatio","BgRatio","pvalue","p.adjust","qvalue","geneID","Count") %in% names(df)))
info <- function(f) { x <- f(); setNames(as.character(x$value), x$name) }
go_db <- info(GO_dbInfo); org <- info(org.Hs.eg_dbInfo)
cat(sprintf("R_OK DESeq2 %s clusterProfiler %s org.Hs.eg.db %s GO.db %s | %d GO BP terms | GO.db source date %s | org.Hs.eg.db GO date %s\n",
    packageVersion("DESeq2"), packageVersion("clusterProfiler"), packageVersion("org.Hs.eg.db"), packageVersion("GO.db"),
    nrow(df), go_db[["GOSOURCEDATE"]], org[["GOSOURCEDATE"]]))
if (nzchar(manifest)) {
  pins <- list(HISAT2 = "2.2.1", featureCounts = "v2.0.1", DESeq2 = "1.30.1", clusterProfiler = "3.18.1")
  inst <- list(R = paste(R.version$major, R.version$minor, sep = "."), HISAT2 = a[3], featureCounts = a[4], samtools = a[5],
               cutadapt = a[6], FastQC = a[7], DESeq2 = as.character(packageVersion("DESeq2")),
               clusterProfiler = as.character(packageVersion("clusterProfiler")),
               org.Hs.eg.db = as.character(packageVersion("org.Hs.eg.db")), GO.db = as.character(packageVersion("GO.db")),
               tag_based_RNAseq_commit = a[8])
  dev <- Filter(function(p) !identical(inst[[p]], pins[[p]]), names(pins))
  jsonlite::write_json(list(task = "9", pins = pins, installed = inst,
    deviations = lapply(dev, function(p) list(package = p, requested = pins[[p]], installed = inst[[p]])),
    not_pinned_by_prompt = list(org.Hs.eg.db = "chosen from Bioconductor 3.12 (same release as DESeq2 1.30.1 / clusterProfiler 3.18.1)",
                                GO.db = "idem"),
    go_source_dates = list(GO.db = go_db[["GOSOURCEDATE"]], org.Hs.eg.db = org[["GOSOURCEDATE"]])),
    manifest, auto_unbox = TRUE, pretty = TRUE)
}
RS
if grep -q '^R_OK' "$W/r.log"; then pass R "$(grep '^R_OK' "$W/r.log" | cut -c6-)"; else fail R "$(tail -3 "$W/r.log" | tr '\n' ' ')"; fi

ok=1; for k in "${!RES[@]}"; do [[ ${RES[$k]} == PASS* ]] || ok=0; done
if [ -n "$REPORT" ]; then
  steps=(); for k in "${!RES[@]}"; do steps+=("$k=${RES[$k]}"); done
  python3 - "$REPORT" "$ok" "${steps[@]}" <<'PY' >/dev/null
import json, sys
path, ok = sys.argv[1], sys.argv[2] == "1"
steps = dict(s.split("=", 1) for s in sys.argv[3:])
json.dump({"passed": ok, "steps": steps}, open(path, "w"), indent=2)
PY
fi
rm -rf "$W"
if [ "$ok" = 1 ]; then echo "[verify] ALL STEPS PASS with preinstalled tools"; exit 0; else echo "[verify] SOME STEPS FAILED"; exit 1; fi
