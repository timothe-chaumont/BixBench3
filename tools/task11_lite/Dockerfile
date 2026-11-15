FROM bixbench3-sandbox:1.0.0
USER root
RUN micromamba create -y -p /opt/task11-lite -c conda-forge -c bioconda --strict-channel-priority \
    r-base=4.0.2 bioconductor-deseq2=1.28.0 bioconductor-biomart=2.44.0 \
    bioconductor-piano=2.4.0 r-data.table r-readxl r-openxlsx r-jsonlite \
    && micromamba clean --all --yes
ENV PATH="/opt/task11-lite/bin:${PATH}"
RUN Rscript -e 'stopifnot(as.character(getRversion()) == "4.0.2"); stopifnot(as.character(packageVersion("DESeq2")) == "1.28.0",as.character(packageVersion("biomaRt")) == "2.44.0",as.character(packageVersion("piano")) == "2.4.0"); sessionInfo()'
