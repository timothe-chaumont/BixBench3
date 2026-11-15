# Fixed-method replay: count thinning, not an autonomous-agent evaluation.
suppressPackageStartupMessages(library(DESeq2))
a <- commandArgs(TRUE); input<-a[1];output<-a[2];dir.create(output,showWarnings=FALSE,recursive=TRUE)
counts<-as.matrix(read.csv(file.path(input,'provided_counts.csv'),row.names=1,check.names=FALSE));storage.mode(counts)<-'integer'
meta<-read.delim(file.path(input,'sample_metadata.tsv'),check.names=FALSE)
print(names(meta))
# Resolve only public schema names; fail rather than silently select a cohort.
stopifnot(all(c('library_id','timepoint','treatment_ppm') %in% names(meta)))
meta$treatment_ppm<-sub('ppm$','',as.character(meta$treatment_ppm))
meta<-meta[match(colnames(counts),meta$library_id),];stopifnot(!anyNA(meta$library_id),nrow(meta)==85)
rownames(meta)<-meta$library_id
fit_all<-function(mat){
 out<-list()
 for(t in unique(meta$timepoint)){
  cd<-meta[meta$timepoint==t,,drop=FALSE];cd$dose<-relevel(factor(as.character(cd$treatment_ppm)),ref='0')
  dds<-DESeqDataSetFromMatrix(mat[,rownames(cd),drop=FALSE],cd,~dose)
  dds<-DESeq(dds,quiet=TRUE)
  for(d in setdiff(levels(cd$dose),'0')){
   z<-as.data.frame(results(dds,contrast=c('dose',d,'0'),alpha=.1));out[[paste(t,d,sep='|')]]<-z
  }
 };out
}
base<-fit_all(counts);saveRDS(base,file.path(output,'reference_full_depth.rds'))
rows<-list();n<-0
compare<-function(z,label,fraction,seed){
 for(k in names(base)){
  x<-base[[k]];y<-z[[k]];ok<-is.finite(x$log2FoldChange)&is.finite(y$log2FoldChange)
  sx<-rownames(x)[!is.na(x$padj)&x$padj<.1];sy<-rownames(y)[!is.na(y$padj)&y$padj<.1]
  intersect_n<-length(intersect(sx,sy));union_n<-length(union(sx,sy));denom<-length(sx)+length(sy)
  n<<-n+1;rows[[n]]<<-data.frame(source=label,fraction=fraction,seed=seed,contrast=k,n_reference_significant=length(sx),n_significant=length(sy),n_logfc_finite_both=sum(ok),fraction_finite_both=sum(ok)/sum(is.finite(x$log2FoldChange)),significant_recall=if(length(sx))intersect_n/length(sx) else NA,significant_precision=if(length(sy))intersect_n/length(sy) else NA,significant_jaccard=if(union_n)intersect_n/union_n else NA,significant_f1=if(denom)2*intersect_n/denom else NA,logfc_spearman=cor(x$log2FoldChange[ok],y$log2FoldChange[ok],method='spearman'),direction_agreement=mean(sign(x$log2FoldChange[ok])==sign(y$log2FoldChange[ok])))
 }
 write.csv(do.call(rbind,rows),file.path(output,'depth_metrics.csv'),row.names=FALSE)
}
compare(base,'reference',1,0)
for(f in c(.01,.03,.1,.3))for(s in c(1,2)){
 set.seed(20261115+s);thin<-matrix(rbinom(length(counts),size=as.vector(counts),prob=f),nrow=nrow(counts),dimnames=dimnames(counts))
 print(c(fraction=f,seed=s));compare(fit_all(thin),'binomial_thinning',f,s)
}
p<-file.path(input,'historical_full_counts.csv')
if(file.exists(p)){candidate<-as.matrix(read.csv(p,row.names=1,check.names=FALSE));candidate<-candidate[rownames(counts),colnames(counts)];storage.mode(candidate)<-'integer';compare(fit_all(candidate),'historical_full_counts',1,0)}
writeLines(capture.output(sessionInfo()),file.path(output,'sessionInfo.txt'))
