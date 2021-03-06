#!/usr/bin/env python

from argparse import ArgumentParser
from tango import prepare
from tango import search
from tango import assign
from tango import transfer
from time import time
import sys
import os
import pandas as pd


def download(args):
    """Downloads fasta or taxonomy dump files

    If args.db == 'taxonomy', download taxonomy dump files from ncbi and
    initialize the ete3 sqlite database If args.db == 'idmap', download the
    seqid->taxid mapfile from ncbi Otherwise download the protein fastafile
    corresponding to args.db (uniref50, uniref90, uniref100 or nr)
    """

    if args.db == "taxonomy":
        prepare.download_ncbi_taxonomy(args.taxdir, args.force)
        prepare.init_sqlite_taxdb(args.taxdir, args.sqlitedb, args.force)
    elif args.db == "idmap":
        prepare.download_nr_idmap(args.dldir, args.tmpdir, args.force)
    else:
        prepare.download_fasta(args.dldir, args.db, args.tmpdir, args.force,
                               args.skip_check, args.skip_idmap)


def reformat(args):
    """Reformats a database to comply with diamond

    diamond makedb has some requirements when adding taxonomic info
    1. protein seqids cannot be longer than 14 characters
    2. nodes.dmp and names.dmp must be supplied
    3. a prot.accession2taxid.gz file mapping protein ids to taxonomy ids must
    be supplied
    """

    prepare.format_fasta(args.fastafile, args.reformatted, args.tmpdir,
                         args.force, args.taxidmap, args.forceidmap,
                         args.maxidlen)


def update(args):
    """Updates the protein -> taxid idmap

    If protein accessions were too long these were remapped during the format
    stage. This requires a new map file to be created with the new (shorter)
    protein ids.
    """
    prepare.update_idmap(args.idfile, args.taxonmap, args.newfile)


def build(args):
    """Builds the diamond database from downloaded fasta and taxonomy files"""
    prepare.build_diamond_db(args.fastafile, args.taxonmap, args.taxonnodes,
                             args.dbfile, args.cpus)


def run_diamond(args):
    """Runs diamond blastx against target database"""
    search.diamond(args.query, args.outfile, args.dbfile, args.mode, args.cpus,
                   args.evalue, args.top, args.blocksize, args.chunks,
                   args.tmpdir, args.minlen, args.taxonmap)


def assign_taxonomy(args):
    """Parses diamond results and assigns taxonomy"""
    # Check outfile
    if os.path.isdir(args.outfile):
        sys.exit("\nERROR: Outfile {} is a directory\n".format(args.outfile))
    outdir = os.path.dirname(args.outfile)
    if outdir != "" and not os.path.exists(outdir):
        os.makedirs(outdir)
    start_time = time()
    sys.stderr.write("Assigning taxonomy with {} cpus\n".format(args.cpus))
    # Parse diamond file
    assign.parse_hits(args.diamond_results, args.outfile, args.taxidout,
                      args.blobout, args.top, args.evalue, args.format,
                      args.taxidmap, args.mode, args.vote_threshold,
                      args.assignranks, args.reportranks, args.rank_thresholds,
                      args.taxdir, args.sqlitedb, args.chunksize, args.cpus)
    end_time = time()
    run_time = round(end_time - start_time, 1)
    sys.stderr.write("Total time: {}s\n".format(run_time))


def transfer_taxonomy(args):
    """Transfers taxonomy from ORFs to contigs"""
    # Read taxonomy df
    df = pd.read_csv(args.orf_taxonomy, sep="\t", header=0, index_col=0)
    orf_df_out = False
    if args.orf_tax_out:
        orf_df_out = True
    start_time = time()
    contig_df, orf_df = transfer.transfer_taxonomy(df, args.gff,
                                                   args.ignore_unc_rank,
                                                   args.cpus, args.chunksize,
                                                   orf_df_out)
    contig_df.to_csv(args.contig_taxonomy, sep="\t", index=True, header=True)
    if orf_df_out:
        orf_df.to_csv(args.orf_tax_out, sep="\t", index=True, header=True)
    end_time = time()
    run_time = round(end_time - start_time, 1)
    sys.stderr.write("Total time: {}s\n".format(run_time))


def get_version():
    from tango import __version__
    return '%(prog)s {version}'.format(version=__version__)


def usage(args):
    if args.version:
        import tango
        print(tango.version)
    else:
        print("""
        To print help message: tango -h
        """)


def main():
    parser = ArgumentParser()
    parser.add_argument('-v', '--version', action='version',
                        version=get_version())
    parser.set_defaults(func=usage)
    subparser = parser.add_subparsers(title="subcommands",
                                      description="valid subcommands")
    # Download parser
    download_parser = subparser.add_parser("download",
                                           help="Download fasta file and NCBI "
                                                "taxonomy files")
    download_parser.add_argument("db",
                                 choices=["uniref100", "uniref90", "uniref50",
                                          "nr", "taxonomy", "idmap"],
                                 default="uniref100", help="Database to "
                                                           "download. "
                                                           "Defaults to "
                                                           "'uniref100'")
    download_parser.add_argument("-d", "--dldir",
                                 help="Write files to this directory. "
                                      "Defaults to db name in current "
                                      "directory. "
                                      "Will be created if missing.")
    download_parser.add_argument("--tmpdir", type=str,
                                 help="Temporary directory for downloading "
                                      "files")
    download_parser.add_argument("-t", "--taxdir", default="./taxonomy",
                                 help="Directory to store NCBI taxdump files. "
                                      "Defaults to 'taxonomy/' in current "
                                      "directory")
    download_parser.add_argument("--sqlitedb", type=str,
                                 default="taxonomy.sqlite",
                                 help="Name of ete3 sqlite file to be created "
                                      "within --taxdir. Defaults to "
                                      "'taxonomy.sqlite'")
    download_parser.add_argument("-f", "--force", action="store_true",
                                 help="Overwrite downloaded files")
    download_parser.add_argument("--skip_check", action="store_true",
                                 help="Skip check of downloaded fasta file. "
                                      "Default: False")
    download_parser.add_argument("--skip_idmap", action="store_true",
                                 help="Skip download of seqid->taxid mapfile "
                                      "(only applies to 'nr' database).")
    # Call download function with arguments
    download_parser.set_defaults(func=download)
    # Format parser
    format_parser = subparser.add_parser("format",
                                         help="Format fasta file for diamond "
                                              "and create protein2taxid map")
    format_parser.add_argument("fastafile", type=str,
                               help="Specify protein fasta to reformat")
    format_parser.add_argument("reformatted", type=str,
                               help="Path to reformatted fastafile")
    format_parser.add_argument("-f", "--force", action="store_true",
                               help="Force overwrite of existing reformatted "
                                    "fastafile")
    format_parser.add_argument("--forceidmap", action="store_true",
                               help="Force overwrite of existing "
                                    "accession2taxid mapfile")
    format_parser.add_argument("-m", "--taxidmap", type=str,
                               help="Protein accession to taxid mapfile. For "
                                    "UniRef this file is created from "
                                    "information in the fasta headers and "
                                    "stored in a file named "
                                    "prot.accession2taxid.gz in the same "
                                    "directory as the reformatted fasta file. "
                                    "Specify another path here.")
    format_parser.add_argument("--maxidlen", type=int, default=14, help="""Maximum allowed length of sequence
                               ids. Defaults to 14 (required by diamond for
                               adding taxonomy info to database). Ids longer
                               than this are written to a file with the
                               original id""")
    format_parser.add_argument("--tmpdir", type=str,
                               help="Temporary directory for writing fasta "
                                    "files")
    # Call format function with arguments
    format_parser.set_defaults(func=reformat)
    # Update parser
    update_parser = subparser.add_parser("update",
                                         help="Update protein to taxid map "
                                              "file with new sequence ids")
    update_parser.add_argument("taxonmap", type=str,
                               help="Existing prot.accession2taxid.gz file")
    update_parser.add_argument("idfile", type=str,
                               help="File mapping long sequence ids to new"
                                    " ids")
    update_parser.add_argument("newfile", type=str, help="Updated mapfile")
    # Call update function with arguments
    update_parser.set_defaults(func=update)
    # Build parser
    build_parser = subparser.add_parser("build",
                                        help="Build diamond database from "
                                             "downloaded files")
    build_parser.add_argument("fastafile",
                              help="Specify (reformatted) fasta file")
    build_parser.add_argument("taxonmap",
                              help="Protein accession to taxid mapfile (must "
                                   "be gzipped)")
    build_parser.add_argument("taxonnodes",
                              help="nodes.dmp file from NCBI taxonomy "
                                   "database")
    build_parser.add_argument("-d", "--dbfile",
                              help="Name of diamond database file. Defaults "
                                   "to diamond.dmnd in same directory as "
                                   "the protein fasta file")
    build_parser.add_argument("-p", "--cpus", type=int, default=1,
                              help="Number of cpus to use when building ("
                                   "defaults to 1)")
    # Call build function with arguments
    build_parser.set_defaults(func=build)
    # Search parser
    search_parser = subparser.add_parser("search",
                                         help="Run diamond blastx with "
                                              "nucleotide fasta file")
    search_parser.add_argument("query", type=str,
                               help="Query contig nucleotide file")
    search_parser.add_argument("dbfile", type=str, help="Diamond database file")
    search_parser.add_argument("outfile", type=str, help="Diamond output file")
    search_parser.add_argument("-m", "--mode", type=str,
                               choices=["blastx", "blastp"], default="blastx",
                               help="Choice of search mode for diamond: "
                                    "'blastx' (default) for DNA query "
                                    "sequences or "
                                    "'blastp' for amino acid query sequences")
    search_parser.add_argument("-p", "--cpus", default=1, type=int,
                               help="Number of cpus to use for diamond")
    search_parser.add_argument("-b", "--blocksize", type=float, default=2.0,
                               help="Sequence block size in billions of "
                                    "letters (default=2.0). Set to 20 on "
                                    "clusters")
    search_parser.add_argument("-c", "--chunks", type=int, default=4,
                               help="Number of chunks for index processing ("
                                    "default=4)")
    search_parser.add_argument("-T", "--top", type=int, default=10,
                               help="Report alignments within this percentage "
                                    "range of top bitscore (default=10)")
    search_parser.add_argument("-e", "--evalue", default=0.001, type=float,
                               help="maximum e-value to report alignments ("
                                    "default=0.001)")
    search_parser.add_argument("-l", "--minlen", type=int, default=None,
                               help="Minimum length of queries. Shorter "
                                    "queries will be filtered prior to "
                                    "search.")
    search_parser.add_argument("-t", "--tmpdir", type=str,
                               help="directory for temporary files")
    search_parser.add_argument("--taxonmap", type=str,
                               help="Protein accession to taxid mapfile (must "
                                    "be gzipped). Only required for searching"
                                    "if diamond version <0.9.19")
    search_parser.set_defaults(func=run_diamond)
    # Assign parser
    assign_parser = subparser.add_parser("assign",
                                         help="Assigns taxonomy from diamond "
                                              "output")
    assign_parser_input = assign_parser.add_argument_group("input")
    assign_parser_output = assign_parser.add_argument_group("output")
    assign_parser_mode = assign_parser.add_argument_group("run_mode")
    assign_parser_performance = assign_parser.add_argument_group("performance")
    assign_parser.add_argument("diamond_results", type=str,
                               help="Diamond blastx results")
    assign_parser.add_argument("outfile", type=str, help="Output file")
    assign_parser_input.add_argument("--format", type=str,
                                     choices=["tango", "blast"],
                                     default="tango",
                                     help="Type of file format for diamond "
                                          "results. blast=blast tabular "
                                          "output, 'tango'=blast tabular "
                                          "output with taxid in 12th column"),
    assign_parser_input.add_argument("--taxidmap", type=str,
                                     help="Provide custom protein to taxid "
                                          "mapfile.")
    assign_parser_input.add_argument("-t", "--taxdir", type=str,
                                     default="./taxonomy",
                                     help="Directory specified during 'tango "
                                          "download taxonomy'. "
                                          "Defaults to taxonomy/.")
    assign_parser_input.add_argument("--sqlitedb", type=str,
                                     default="taxonomy.sqlite",
                                     help="Name of ete3 sqlite file to be "
                                          "created within --taxdir. Defaults "
                                          "to 'taxonomy.sqlite'")
    assign_parser_mode.add_argument("-m", "--mode", type=str,
                                    default="rank_lca",
                                    choices=['rank_lca', 'rank_vote', 'score'],
                                    help="Mode to use for parsing taxonomy: "
                                         "'rank_lca' (default), 'rank_vote' "
                                         "or 'score'")
    assign_parser_mode.add_argument("--assignranks", nargs="+",
                                    default=["phylum", "genus", "species"],
                                    help="Ranks to use when assigning taxa. "
                                         "Defaults to phylum genus species")
    assign_parser_mode.add_argument("--reportranks", nargs="+",
                                    default=["superkingdom", "phylum", "class",
                                             "order", "family", "genus",
                                             "species"],
                                    help="Ranks to report in output. Defaults "
                                         "to superkingom phylum class order "
                                         "family genus species")
    assign_parser_mode.add_argument("--rank_thresholds", nargs="+",
                                    default=[45, 60, 85], type=int,
                                    help="Rank-specific thresholds "
                                         "corresponding to percent identity "
                                         "of a hit.  Defaults to 45 (phylum), "
                                         "60 (genus) and 85 (species)")
    assign_parser_mode.add_argument("--vote_threshold", default=0.5, type=float,
                                    help="Minimum fraction required when "
                                         "voting on rank assignments.")
    assign_parser_mode.add_argument("-T", "--top", type=int, default=5,
                                    help="Top percent of best score to "
                                         "consider hits for (default=5)")
    assign_parser_mode.add_argument("-e", "--evalue", type=float, default=0.001,
                                    help="Maximum e-value to store hits. "
                                         "Default 0.001")
    assign_parser_performance.add_argument("-p", "--cpus", type=int, default=1,
                                           help="Number of cpus to use. "
                                                "Defaults to 1.")
    assign_parser_performance.add_argument("-c", "--chunksize", type=int,
                                           default=1,
                                           help="Size of chunks sent to "
                                                "process pool. For large input"
                                                " files using a large "
                                                "chunksize can make the job "
                                                "complete much faster than "
                                                "using the default value of 1")
    assign_parser_output.add_argument("--blobout", type=str,
                                      help="Output hits.tsv table compatible "
                                           "with blobtools")
    assign_parser_output.add_argument("--taxidout", type=str,
                                      help="Write output with taxonomy ids "
                                           "instead of taxonomy names to file")
    assign_parser.set_defaults(func=assign_taxonomy)
    # Transfer parser
    transfer_parser = subparser.add_parser("transfer",
                                           help="Transfer taxonomy from ORFs "
                                                "to contigs")
    transfer_parser.add_argument("orf_taxonomy", type=str,
                                 help="Taxonomy assigned to ORFs (ORF ids in "
                                      "first column)")
    transfer_parser.add_argument("gff", type=str,
                                 help="GFF or file with contig id in first "
                                      "column and ORF id in second column")
    transfer_parser.add_argument("contig_taxonomy", type=str,
                                 help="Output file with assigned taxonomy for "
                                      "contigs")
    transfer_parser.add_argument("--ignore_unc_rank", type=str, default=None,
                                 help="Ignore ORFs unclassified at <rank>")
    transfer_parser.add_argument("--orf_tax_out", type=str,
                                 help="Also transfer taxonomy back to ORFs "
                                      "and output to file")
    transfer_parser.add_argument("-p", "--cpus", type=int, default=1,
                                 help="Number of cpus to use when "
                                      "transferring taxonomy to contigs")
    transfer_parser.add_argument("-c", "--chunksize", type=int, default=1,
                                 help="Size of chunks sent to process pool. "
                                      "For large input files using a large "
                                      "chunksize can make the job complete "
                                      "much faster than using the default "
                                      "value of 1.")
    transfer_parser.set_defaults(func=transfer_taxonomy)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
