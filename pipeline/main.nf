nextflow.enable.dsl=2

params.input  = "default_input"
params.outdir = "/data/results"

workflow {
    log.info "Pipeline started"
    log.info "input:  ${params.input}"
    log.info "outdir: ${params.outdir}"
}
