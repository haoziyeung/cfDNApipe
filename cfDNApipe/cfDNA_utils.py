# -*- coding: utf-8 -*-
"""
Created on Fri Aug  9 11:37:46 2019

@author: zhang
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import Iterable
import pysam
import pybedtools
import os
import subprocess
import sys
from collections import defaultdict
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import gzip
import shutil
import statsmodels.api as sm
from scipy import stats, optimize
from scipy.interpolate import interp1d
from sklearn.decomposition import PCA
from sklearn.svm import NuSVR
import seaborn as sns
from tqdm import tqdm
from matplotlib import rc

__metaclass__ = type


class commonError(Exception):
    def __init__(self, message):
        self.message = message


# https://stackoverflow.com/questions/2158395/flatten-an-irregular-list-of-lists
def flatten(l):
    for el in l:
        if isinstance(el, Iterable) and not isinstance(el, (str, bytes)):
            yield from flatten(el)
        else:
            yield el


def isAlphaOrDigit(x):
    if x.isalpha() or x.isdigit():
        return True
    else:
        return False


def rmEndString(x, y):
    for item in y:
        if x.endswith(item):
            x = x.replace(item, "")

    return x


def isSoftClipped(cigar):
    """
    see here for more information about this function
    references:
        https://pysam.readthedocs.io/en/latest/api.html
        https://davetang.org/wiki/tiki-index.php?page=SAM
    """
    for (op, count) in cigar:
        if op in [4, 5, 6]:
            return True
    return False


def read_pair_generator(bam, region_string=None):
    """
    Generate read pairs in a BAM file or within a region string.
    Reads are added to read_dict until a pair is found.
    reference:
        https://www.biostars.org/p/306041/
    """
    read_dict = defaultdict(lambda: [None, None])
    for read in bam.fetch(region=region_string):
        # filter reads
        if read.is_unmapped or read.is_qcfail or read.is_duplicate:
            continue
        if not read.is_paired:
            continue
        if not read.is_proper_pair:
            continue
        if read.is_secondary or read.is_supplementary:
            continue
        if read.mate_is_unmapped:
            continue
        if read.rnext != read.tid:
            continue
        if read.template_length == 0:
            continue
        if isSoftClipped(read.cigar):
            continue

        qname = read.query_name
        if qname not in read_dict:
            if read.is_read1:
                read_dict[qname][0] = read
            else:
                read_dict[qname][1] = read
        else:
            if read.is_read1:
                yield read, read_dict[qname][1]
            else:
                yield read_dict[qname][0], read
            del read_dict[qname]


def bamTobed(bamInput=None, bedOutput=None, compress=True):
    # generate temp file for sorting and indexing
    bedOutput_path = os.path.realpath(bedOutput)
    this_pid = os.getpid()
    tmp_split = os.path.splitext(bedOutput_path)
    tmp_bedOutput = tmp_split[0] + "-temp-" + str(this_pid) + tmp_split[1]

    bai = bamInput + ".bai"
    if not os.path.exists(bai):
        message = "Index file " + bai + " do not exist!"
        raise commonError(message)

    bedWrite = open(tmp_bedOutput, "w")

    input_file = pysam.Samfile(bamInput, "rb")
    chr_reference = input_file.references
    for read1, read2 in read_pair_generator(input_file):
        read1Start = read1.reference_start
        read1End = read1.reference_end
        read2Start = read2.reference_start
        read2End = read2.reference_end

        if not read1.is_reverse:  # read1 is forward strand, read2 is reverse strand
            rstart = read1Start  # 0-based left-most site
            rend = read2End
        else:  # read1 is reverse strand, read2 is forward strand
            rstart = read2Start  # 0-based left-most site
            rend = read1End

        if (rstart < 0) or (rend < 0) or (rstart >= rend):
            continue

        tmp_str = (
            chr_reference[read1.tid] + "\t" + str(rstart) + "\t" + str(rend) + "\n"
        )
        bedWrite.write(tmp_str)

    bedWrite.close()
    print("Fragments generated, waitting for sorting......")

    bedData = pybedtools.BedTool(tmp_bedOutput)
    bedData.sort(output=bedOutput)

    os.remove(tmp_bedOutput)

    print("Fragments sorted.")

    if compress:
        print("Waitting for compressing and indexing......")
        bedgzfile = bedOutput + ".gz"
        pysam.tabix_compress(bedOutput, bedgzfile, force=False)
        pysam.tabix_index(bedgzfile, preset="bed", zerobased=True)
        print("Indexing bedgz file finished!")

    return True


def bamTobedForSingle(bamInput=None, bedOutput=None, compress=True):
    bam = pybedtools.BedTool(bamInput)
    bed = bam.bam_to_bed()
    bed.sort(output=bedOutput)

    print("Bed file generated!")

    if compress:
        print("Waitting for compressing and indexing......")
        bedgzfile = bedOutput + ".gz"
        pysam.tabix_compress(bedOutput, bedgzfile, force=False)
        pysam.tabix_index(bedgzfile, preset="bed", zerobased=True)
        print("Indexing bedgz file finished!")

    return True


# bam to bed, tackle the file without "chr", this will raise error
def bam2bedV2(bamInput, bedOutput):
    bamInput = bamInput
    bedOutput = bedOutput

    # generate temp file for sorting and indexing
    bedOutput_path = os.path.realpath(bedOutput)
    this_pid = os.getpid()
    tmp_split = os.path.splitext(bedOutput_path)
    tmp_bedOutput = tmp_split[0] + "-temp-" + str(this_pid) + tmp_split[1]

    bedWrite = open(tmp_bedOutput, "w")

    bai = bamInput + ".bai"
    if not os.path.exists(bai):
        message = "Index file " + bai + " do not exist!"
        raise commonError(message)

    input_file = pysam.Samfile(bamInput, "rb")
    chr_reference = input_file.references
    for read1, read2 in read_pair_generator(input_file):
        read1Start = read1.reference_start
        read1End = read1.reference_end
        read2Start = read2.reference_start
        read2End = read2.reference_end

        if not read1.is_reverse:  # read1 is forward strand, read2 is reverse strand
            rstart = read1Start
            rend = read2End
        else:  # read1 is reverse strand, read2 is forward strand
            rstart = read2Start
            rend = read1End

        if (rstart < 0) or (rend < 0) or (rstart >= rend):
            continue

        tmp_str = (
            "chr"
            + chr_reference[read1.tid]
            + "\t"
            + str(rstart)
            + "\t"
            + str(rend)
            + "\n"
        )
        bedWrite.write(tmp_str)

    bedWrite.close()
    print("Fragments generated, waitting for sorting......")

    bedData = pybedtools.BedTool(tmp_bedOutput)
    bedData.sort(output=bedOutput)

    print("Fragments sorted, waitting for compressing and indexing......")

    bedgzfile = bedOutput + ".gz"
    pysam.tabix_compress(bedOutput, bedgzfile, force=False)
    pysam.tabix_index(bedgzfile, preset="bed", zerobased=True)

    print("Indexing bedgz file finished!")

    os.remove(tmp_bedOutput)

    return "Program complete!"


# plot length distribution
def fraglendistribution(bedInput=None, plotOutput=None, binOutput=None, maxLimit=None):
    data = pd.read_table(bedInput, sep="\t", header=None, names=["chr", "start", "end"])
    len_info = np.asarray(data["end"] - data["start"])

    np.save(binOutput, len_info)

    len_info = len_info[np.where(len_info <= maxLimit)]

    fig = plt.figure(figsize=(10, 8))
    plot_limit = len_info.max() - len_info.min()
    plt.hist(len_info, bins=plot_limit)
    plt.savefig(plotOutput)
    plt.close(fig)

    return len_info.tolist()

def fraglenmultiplot(dataInput, plotOutput):
    fig = plt.figure(figsize = (10, 8))
    for i in range(len(dataInput)):
        bin = np.bincount(dataInput[i]) / len(dataInput[i])
        plt.plot(np.arange(len(bin)), bin, c = "b", linewidth = 0.2)
    plt.xlabel("Fragment size(bp)")
    plt.ylabel("Density")
    plt.savefig(plotOutput)
    plt.close(fig)
    
    return True
    
def fraglencompplot(caseInput, ctrlInput, plotOutput, labelInput = ["case", "control"]):
    caseprop = []
    ctrlprop = []
    fig = plt.figure(figsize = (10, 8))
    for i in range(len(caseInput)):
        casebin = np.bincount(caseInput[i]) / len(caseInput[i])
        caseprop.append(np.sum(casebin[ : 150]))
        p1, = plt.plot(np.arange(len(casebin)), casebin, c = "y", linewidth = 0.2)
    for i in range(len(ctrlInput)):
        ctrlbin = np.bincount(ctrlInput[i]) / len(ctrlInput[i])
        ctrlprop.append(np.sum(ctrlbin[ : 150]))
        p2, = plt.plot(np.arange(len(ctrlbin)), ctrlbin, c = "b", linewidth = 0.2)
    plt.xlabel("Fragment size(bp)")
    plt.ylabel("Density")
    plt.legend([p1, p2], labelInput, loc = "best")
    plt.savefig(plotOutput[0])
    plt.close(fig)
    
    f, ax = plt.subplots(figsize = (8, 10))
    casegory = [labelInput[0] for i in range(len(caseprop))]
    ctrlgory = [labelInput[1] for i in range(len(ctrlprop))]
    propdf = pd.DataFrame({"category": casegory + ctrlgory, "proportion": caseprop + ctrlprop})
    sns.violinplot(x = "category", y = "proportion", data = propdf, ax = ax)
    ax.set_xlabel("")
    ax.set_ylabel("Proportion of fragments below 150bp")
    y, h = propdf["proportion"].max() + 0.1, 0.02
    t, p = stats.ttest_ind(caseprop, ctrlprop, equal_var = False)
    if p >= 0.05:
        text = "p = " + p
    elif p >= 0.01:
        text = "*"
    elif p >= 0.001:
        text = "**"
    elif p >= 0.0001:
        text = "***"
    elif p >= 0:
        text = "****"
    plt.plot([0, 0, 1, 1], [y, y + h, y + h, y], lw = 1, c = "k")
    plt.text(0.5, y + h, text, ha = "center", va = "bottom", color = "k")
    plt.savefig(plotOutput[1])
    plt.close(f)
    
    return True

# calculate methylation level for regions
def calcMethyl(bamInput, bedInput, txtOutput):
    bai = bamInput + ".bai"
    if not os.path.exists(bai):
        message = "Index file " + bai + " do not exist!"
        raise commonError(message)

    bam_input = pysam.Samfile(bamInput, "rb")
    regions = pd.read_csv(
        bedInput, sep="\t", header=None, names=["chr", "start", "end"]
    )

    CXXname = ["unmCpG", "mCpG", "unmCHG", "mCHG", "unmCHH", "mCHH", "unmUNC", "mUNC"]
    d = dict.fromkeys(CXXname, 0)
    regions = regions.assign(**d)

    for index, row in regions.iterrows():
        count_data = [0, 0, 0, 0, 0, 0, 0, 0]
        for read in bam_input.fetch(
            reference=row["chr"], start=row["start"], end=row["end"]
        ):
            CXXinfo = read.get_tag("XM")
            count_data[0] += CXXinfo.count("z")
            count_data[1] += CXXinfo.count("Z")
            count_data[2] += CXXinfo.count("x")
            count_data[3] += CXXinfo.count("X")
            count_data[4] += CXXinfo.count("h")
            count_data[5] += CXXinfo.count("H")
            count_data[6] += CXXinfo.count("u")
            count_data[7] += CXXinfo.count("U")

        regions.loc[index, CXXname] = count_data

    regions["mlCpG"] = regions["mCpG"] / (regions["mCpG"] + regions["unmCpG"])
    regions["mlCHG"] = regions["mCHG"] / (regions["mCHG"] + regions["unmCHG"])
    regions["mlCHH"] = regions["mCHH"] / (regions["mCHH"] + regions["unmCHH"])
    regions["mlUNC"] = regions["mUNC"] / (regions["mUNC"] + regions["unmUNC"])

    regions.to_csv(txtOutput, sep="\t", header=True, index=False)


# uncompress gz file
def un_gz(gzfile):
    file = gzfile.replace(".gz", "")
    with gzip.open(gzfile, "r") as f_in, open(file, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


# run a single command line
def cmdCall(cmdLine):
    proc = subprocess.Popen(
        cmdLine,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    while True:
        nextline = proc.stdout.readline()
        if (nextline == "") and (proc.poll() is not None):
            break
        sys.stdout.write(nextline)
        sys.stdout.flush()

    output, error = proc.communicate()
    exitCode = proc.returncode

    if exitCode != 0:
        raise commonError("**********CMD running error**********")


# compute OCF value for paired end data
def ComputeOCF(bedgz, txtOutput, OCFOutput, regionFile):
    print("Input file:", bedgz)
    print("Output files:", txtOutput)
    print("Output OCF files:", OCFOutput)
    print("Region files:", regionFile)

    tbx = pysam.TabixFile(bedgz)

    # regions are 1-based
    regions = pd.read_csv(
        regionFile, sep="\t", header=None, names=["chr", "start", "end", "description"]
    )

    regions["OCF"] = 0
    cud_output = txtOutput

    Udata = np.empty(shape=(0, 241))
    Ddata = np.empty(shape=(0, 241))

    for idx, region in regions.iterrows():
        region_Chr, region_Start, region_End = (
            region["chr"],
            region["start"],
            region["end"],
        )

        if region_Start < 1:
            message = "Start of the region must > 0!"
            raise commonError(message)

        covPOS = defaultdict(lambda: [0, 0, 0])

        # fetch read in the region
        try:
            fetched_reads = tbx.fetch(region_Chr, region_Start, region_End)
        except ValueError:
            continue
        for row in fetched_reads:
            tmp_row = row.split()
            rstart = int(tmp_row[1]) + 1  # convert to 1-based
            rend = int(tmp_row[2])  # end included

            #            for i in range(rstart, rend + 1):  # for a read, add 1 to every point at which it overlapped, coverage
            #                if i >= region_Start and i <= region_End:
            #                    covPOS[i][0] += 1

            if (
                rstart >= region_Start and rstart <= region_End
            ):  # consider read start point, U end
                covPOS[rstart][1] += 1

            if (
                rend >= region_Start and rend <= region_End
            ):  # consider read start point, D end
                covPOS[rend][2] += 1

        # finished a region
        midpoint = int((region_Start + region_End) / 2)

        Udata = np.vstack(
            (Udata, [covPOS[x][1] for x in range(midpoint - 120, midpoint + 121)])
        )
        Ddata = np.vstack(
            (Ddata, [covPOS[x][2] for x in range(midpoint - 120, midpoint + 121)])
        )

        left_OCF = sum(
            [covPOS[x][2] for x in range(midpoint - 70, midpoint - 50)]
        ) - sum([covPOS[x][1] for x in range(midpoint - 70, midpoint - 50)])
        right_OCF = sum(
            [covPOS[x][1] for x in range(midpoint + 50, midpoint + 70)]
        ) - sum([covPOS[x][2] for x in range(midpoint + 50, midpoint + 70)])
        regions.loc[idx, "OCF"] = left_OCF + right_OCF

    ud_data = np.concatenate([Udata, Ddata], 1)

    np.savetxt(cud_output, ud_data, fmt="%i", delimiter="\t")

    regions.to_csv(OCFOutput, sep="\t", index=False)

    print("Processing finished!")

    return "True"


# compute coverage, U-end(upstream end) and D-end(downstream end)
# only count -1000 to 1000 from open region center
def computeCUE(inputFile, refFile, txtOutput, cudOutput):
    inputFile = pybedtools.BedTool(inputFile)
    refFile = pybedtools.BedTool(refFile)
    inputFile.intersect(refFile, wo=True, sorted=True, output=txtOutput)

    peak = 60  # distance of U and D peaks from the center
    bin = 10  # half the length of windows
    ocf = []

    data = pd.read_csv(
        txtOutput,
        sep="\t",
        header=None,
        names=[
            "read.chr",
            "read.start",
            "read.end",
            "peak.chr",
            "peak.start",
            "peak.end",
            "description",
            "overlap",
        ],
    )
    data["peak.start"] = data["peak.start"] + 1
    data["read.start"] = data["read.start"] + 1

    save_flag = ["Tcell", "Liver", "Placenta", "Lung", "Breast", "Intestine", "Ovary"]
    flag_num = -1
    for flag in save_flag:
        flag_num += 1
        print("Now, processing " + flag + "......")
        tmp_data = data.loc[
            data.description == flag,
        ]
        cov = np.zeros(shape=2000)
        uend = np.zeros(shape=2000)
        dend = np.zeros(shape=2000)
        for idx, row in tmp_data.iterrows():
            if (row["read.start"] < row["peak.start"]) and (
                row["peak.start"] <= row["read.end"]
            ):
                o_s, o_e = 0, row["read.end"] - row["peak.start"]
                cov[0: (o_e + 1)] += 1
                dend[o_e] += 1
            elif (row["peak.start"] <= row["read.start"]) and (
                row["read.end"] <= row["peak.end"]
            ):
                o_s, o_e = (
                    row["read.start"] - row["peak.start"],
                    row["read.end"] - row["peak.start"],
                )
                cov[o_s: (o_e + 1)] += 1
                uend[o_s] += 1
                dend[o_e] += 1
            elif (row["read.start"] <= row["peak.end"]) and (
                row["peak.end"] < row["read.end"]
            ):
                o_s, o_e = row["read.start"] - row["peak.start"], 1999
                cov[o_s: (o_e + 1)] += 1
                uend[o_s] += 1
            else:
                continue

        cov_tot, uend_tot, dend_tot = 0, 0, 0
        for i in range(2000):
            cov_tot += cov[i]
            uend_tot += uend[i]
            dend_tot += dend[i]

        index = np.array(range(-1000, 1000))
        df = pd.DataFrame.from_dict(
            {
                "idx": index,
                "cov": cov,
                "cov%%": cov / cov_tot * 10000,
                "uend": uend,
                "uend%%": uend / uend_tot * 10000,
                "dend": dend,
                "dend%%": dend / dend_tot * 10000,
            }
        )
        df.to_csv(cudOutput[flag_num], sep="\t", index=False)

        trueends = 0
        background = 0
        for i in index:
            if i >= -peak - bin and i <= -peak + bin:
                trueends += dend[i] / dend_tot * 10000
                background += uend[i] / uend_tot * 10000
            elif i >= peak - bin and i <= peak + bin:
                trueends += uend[i] / uend_tot * 10000
                background += dend[i] / dend_tot * 10000
        ocf.append(trueends - background)

        print("Processing " + flag + " finished!")

    return ocf


def OCFplot(ocfcaseinput, ocfctrlinput, output, x_label=["case", "control"]):
    save_flag = ["Tcell", "Liver", "Placenta", "Lung", "Breast", "Intestine", "Ovary"]
    ocfcaseinput = np.transpose(ocfcaseinput).tolist()
    ocfctrlinput = np.transpose(ocfctrlinput).tolist()

    plt.figure()
    bpl = plt.boxplot(
        ocfcaseinput,
        positions=np.array(range(len(ocfcaseinput))) * 2.0 - 0.4,
        sym="",
        widths=0.6,
        vert=True,
    )
    bpr = plt.boxplot(
        ocfctrlinput,
        positions=np.array(range(len(ocfctrlinput))) * 2.0 + 0.4,
        sym="",
        widths=0.6,
        vert=True,
    )
    plt.setp(bpl["boxes"], color="y")
    plt.setp(bpl["whiskers"], color="y")
    plt.setp(bpl["caps"], color="y")
    plt.setp(bpl["medians"], color="y")
    plt.setp(bpr["boxes"], color="b")
    plt.setp(bpr["whiskers"], color="b")
    plt.setp(bpr["caps"], color="b")
    plt.setp(bpr["medians"], color="b")
    plt.plot([], c="y", label=x_label[0])
    plt.plot([], c="b", label=x_label[1])
    plt.legend()
    plt.xticks(range(0, len(save_flag) * 2, 2), save_flag)
    plt.xlim(-2, len(save_flag) * 2)
    for k in range(7):
        plt.scatter(
            [k * 2.0 - 0.4 for j in range(len(ocfcaseinput[k]))],
            ocfcaseinput[k],
            s=8,
            c="y",
        )
        plt.scatter(
            [k * 2.0 + 0.4 for j in range(len(ocfctrlinput[k]))],
            ocfctrlinput[k],
            s=8,
            c="b",
        )
    plt.ylabel("OCF value")
    plt.tight_layout()
    plt.savefig(output)

    return True


def generate_cudoutput(input, outputdir):
    save_flag = ["Tcell", "Liver", "Placenta", "Lung", "Breast", "Intestine", "Ovary"]
    dict = {}
    prefix = os.path.splitext(os.path.basename(input))[0]
    for flag in save_flag:
        dict[flag] = outputdir + "/" + prefix + "-" + flag + "-cud.txt"
    return dict


# compress .bismark.zero.cov file
def compressMethy(InputFile=None):
    """
    input must from bismark_methylation_extractor, .bismark.zero.cov file
    """
    bedgzfile = InputFile + ".gz"
    pysam.tabix_compress(InputFile, bedgzfile, force=False)
    pysam.tabix_index(bedgzfile, preset="bed", zerobased=True)

    return "True"


# compress methylation level from .bismark.zero.cov.gz file
def calcMethylV2(tbxInput, bedInput, txtOutput):
    tbi = tbxInput + ".tbi"
    if not os.path.exists(tbi):
        message = "Index file " + tbi + " do not exist!"
        raise commonError(message)

    tbx_input = pysam.TabixFile(tbxInput)

    regions = pd.read_csv(
        bedInput, sep="\t", header=None, names=["chr", "start", "end"]
    )

    CXXname = ["unmCpG", "mCpG"]
    d = dict.fromkeys(CXXname, 0)
    regions = regions.assign(**d)

    print("Now, processing fetch and computing CpG level.")

    for index, row in regions.iterrows():
        count_data = [0, 0]
        try:
            for read in tbx_input.fetch(
                reference=row["chr"], start=row["start"], end=row["end"]
            ):
                readinfo = read.split()
                count_data[0] += int(readinfo[5])
                count_data[1] += int(readinfo[4])

        except ValueError:
            continue
        else:
            regions.loc[index, CXXname] = count_data

    regions["mlCpG"] = regions["mCpG"] / (regions["mCpG"] + regions["unmCpG"])

    regions = regions.fillna(0)

    regions.to_csv(txtOutput, sep="\t", header=True, index=False)

    print("finished!")

    return True

#process GC correction on read count data from CNV
def correctReadCount(readInput, gcInput, plotOutput, sampleMaxSize = 50000):
    read_value = readInput["value"].values.tolist()
    read_se = readInput["start-end"].values.tolist()
    gc_value = gcInput["value"].values.tolist()
    read_chr = readInput["chrom"].values.tolist()
    gc_chr = gcInput["chrom"].values.tolist()
    
    #matching different lines of read and gc inputs
    i, gcplus, readplus, nextpos = 0, 0, 0, 0
    reads, gc, chrs, ses = [], [], [], []
    mark = read_chr[0]
    while i + gcplus < len(gc_value) and i + readplus < len(read_value):
        if gc_chr[i + gcplus] not in ["chr1", "chr2", "chr3", "chr4",
            "chr5", "chr6", "chr7", "chr8", 
            "chr9", "chr10", "chr11", "chr12", 
            "chr13", "chr14", "chr15", "chr16", 
            "chr17", "chr18", "chr19", "chr20", 
            "chr21", "chr22", "chrX", "chrY", 
        ] or read_chr[i + readplus] not in ["chr1", "chr2", "chr3", "chr4",
            "chr5", "chr6", "chr7", "chr8", 
            "chr9", "chr10", "chr11", "chr12", 
            "chr13", "chr14", "chr15", "chr16", 
            "chr17", "chr18", "chr19", "chr20", 
            "chr21", "chr22", "chrX", "chrY", 
        ]:
            i += 1
            continue
        if gc_chr[i + gcplus] != read_chr[i + readplus]:
            print(1)
            if gc_chr[i + gcplus] != mark:
                nextpos = read_chr.index(gc_chr[i + gcplus])
                readplus = nextpos - i
            elif read_chr[i + readplus] != mark:
                nextpos = gc_chr.index(read_chr[i + readplus])
                gcplus = nextpos - i
        reads.append(read_value[i + readplus])
        gc.append(gc_value[i + gcplus])
        chrs.append(read_chr[i + readplus])
        ses.append(read_se[i + readplus])
        mark = read_chr[i + readplus]
        i += 1
        
    #abandoning unsatisfying data and sampling
    l = len(reads)
    tl = l
    valid = [True for i in range(l)]
    for i in range(l):
        if reads[i] <= 0 or gc[i] < 0:
            valid[i] = False
            
    ideal = [True for i in range(l)]
    routlier, doutlier = 0.01, 0.001
    lrange = np.percentile(np.array([reads[i] for i in range(l) if valid[i]]), 0)
    rrange = np.percentile(np.array([reads[i] for i in range(l) if valid[i]]), (1 - routlier) * 100)
    ldomain = np.percentile(np.array([gc[i] for i in range(l) if valid[i]]), doutlier * 100)
    rdomain = np.percentile(np.array([gc[i] for i in range(l) if valid[i]]), (1 - doutlier) * 100)
    for i in range(l):
        if (not valid[i]) or (not lrange <= reads[i] <= rrange) or (not ldomain <= gc[i] <= rdomain):
            ideal[i] = False
            tl -= 1
    ideal_prev = np.array([[reads[i], gc[i]] for i in range(l) if ideal[i]])
    row_rand_array = np.arange(ideal_prev.shape[0])
    np.random.shuffle(row_rand_array)
    ideal_aft = ideal_prev[row_rand_array[ : min(tl, sampleMaxSize)]]
    ideal_reads = [ideal_aft[j][0] for j in range(len(ideal_aft))]
    ideal_gc = [ideal_aft[j][1] for j in range(len(ideal_aft))]
    fig, (ax1, ax2) = plt.subplots(figsize = (15, 6), ncols = 2)
    ax1.scatter(ideal_gc, ideal_reads, c = "deepskyblue", s = 0.1)
    ax1.set_xlabel("GC content")
    ax1.set_ylabel("Read Count")
    ax1.set_ylim(bottom = 0);
    
    #use lowess function to remove the GC bias
    rough = sm.nonparametric.lowess(endog = ideal_reads, exog = ideal_gc, frac = 0.03, return_sorted = True)
    final = sm.nonparametric.lowess(endog = rough[:, 1], exog = rough[:, 0], frac = 0.3, return_sorted = True)
    final_x = list(zip(*final))[0]
    final_y = list(zip(*final))[1]
    f = interp1d(final_x, final_y, bounds_error = False, fill_value = "extrapolate")
    correct_reads = [(reads[i] / f(gc[i])) for i in range(l)]
    correct_reads2 = [(ideal_reads[i] / f(ideal_gc[i])) for i in range(len(ideal_reads))]
    
    ax2.scatter(ideal_gc, correct_reads2, c = "mediumaquamarine", s = 0.1)
    ax2.set_xlabel("GC content")
    ax2.set_ylabel("Read Count (corrected)")
    ax2.set_ylim(bottom = 0)
    fig.savefig(plotOutput)
    
    readOutput = pd.DataFrame({"chrom" : chrs, "start-end" : ses, "value" : correct_reads})
    
    return readOutput

#sum the read count data to each chromosome arm
def chromarm_sum(dfInput, cytoBandInput):
    cytoBand = pd.read_csv(
        cytoBandInput,
        sep = '\t',
        header = None,
        names = [
            "chrom",
            "start",
            "end",
            "band",
            "color"
        ],
    )
    sumvalue = [0]
    geneflag = [cytoBand["chrom"][0][3:] + cytoBand["band"][0][0]]
    line = 0
    for i in range(len(dfInput)):
        chrom = dfInput["chrom"][i]
        start = int(dfInput["start-end"][i].split('-')[0])
        value = float(dfInput["value"][i])
        ifget = False
        for j in range(line, len(cytoBand)):
            if chrom == cytoBand["chrom"][j] and int(cytoBand["start"][j]) <= start <= int(cytoBand["end"][j]):
                if geneflag[-1] != (chrom[3:] + cytoBand["band"][j][0]):
                    geneflag.append(chrom[3:] + cytoBand["band"][j][0])
                    sumvalue.append(0)
                sumvalue[-1] += value
                line = j
                ifget = True
                break
        if not ifget:
            for j in range(len(cytoBand)):
                if chrom == cytoBand["chrom"][j] and int(cytoBand["start"][j]) <= start <= int(cytoBand["end"][j]):
                    if geneflag[-1] != (chrom[3:] + cytoBand["band"][j][0]):
                        geneflag.append(chrom[3:] + cytoBand["band"][j][0])
                        sumvalue.append(0)
                    sumvalue[-1] += value
                    line = j
                    ifget = True
                    break
            
    return sumvalue, geneflag

#compute z-score and plot the heatmap
def compute_z_score(caseInput, ctrlInput, txtOutput, plotOutput):
    mean = ctrlInput.mean(axis = 1)
    std = ctrlInput.std(axis = 1)
    case_z = caseInput.apply(lambda x: (x - mean) / std)
    ctrl_z = ctrlInput.apply(lambda x: (x - mean) / std)
    data = pd.concat([ctrl_z, case_z], axis = 1)
    f, (ax) = plt.subplots(figsize = (20, 20))
    sns.heatmap(data, center = 0, ax = ax, cmap = "RdBu", vmin = -5, vmax = 5)
    data.to_csv(txtOutput, sep = "\t", index = True)
    f.savefig(plotOutput)
    
    return True
    
#read .wig files into dataframe
def wig2df(inputfile):
    f = open(inputfile, "r")
    data = f.readlines()
    chrom_list = []
    startend_list = []
    value_list = []
    for k in data:
        if k.split(" ")[0] == "fixedStep":
            dec = k.split(" ")
            chrom = dec[1].split("=")[1]
            start = int(dec[2].split("=")[1])
            step = int(dec[3].split("=")[1])
            if len(dec) == 5:
                span = int(dec[4].split("=")[1])
            else:
                span = 1
            rownum = -1
        else:
            rownum += 1
            chrom_list.append(chrom)
            startend_list.append(str(rownum * step + start) + "-" + str(rownum * step + start + span - 1))
            value_list.append(float(k.strip('\n')))
    df = pd.DataFrame({"chrom" : chrom_list, "start-end" : startend_list, "value" : value_list})
    return df

def DeconCCN(reference, markerData):
    markerNum = np.size(reference, 0)
    tissueNum = np.size(reference, 1)
    numOfSamples = np.size(markerData, 1)
    bestReference = []
    bestMarker = []
    conditionNumberHistory = []
    bestNumberHistory = []
    proportionDeconvolution = np.zeros([tissueNum, numOfSamples])
    for i in tqdm(range(numOfSamples)):
        selectArea = np.arange(markerNum)
        selectMixture = markerData[selectArea, i]
        selectReference = reference[selectArea, :]
        minimumConditionNumber = 10 ** (100)
        endNumber = np.size(selectReference, 0)
        for selectedNumber in range(int(endNumber / 10)):
            minDistances = 10 ** (50)
            for j in range(tissueNum):
                for k in range(j + 1, tissueNum):
                    distances = selectReference[:, j] - selectReference[:, k]
                    distances = np.sqrt(np.sum(np.multiply(distances, distances)))
                    if distances < minDistances:
                        minDistances = distances
                        closetJ = j
                        closetK = k
            sumData = selectReference[:, closetJ] + selectReference[:, closetK]
            area = sumData == 0
            sumData[area] = 10**(-100)
            collinearity = np.abs(selectReference[:, closetJ] - selectReference[:, closetK]) / (sumData)
            collinearityIndex = np.argsort(collinearity)
            area = np.ones(np.size(selectReference, 0))
            area = area.astype(np.bool)
            area[collinearityIndex[0]] = False
            selectArea = np.arange(np.size(selectReference, 0))
            selectArea = selectArea[area]
            selectMixture = selectMixture[selectArea]
            selectReference = selectReference[selectArea, :]
            ConditionNumber = mixedConditionNumber(selectReference, selectMixture)
            conditionNumberHistory.append(ConditionNumber)
            if ConditionNumber < minimumConditionNumber:
                minimumConditionNumber = ConditionNumber
                bestReference = selectReference
                bestMarker = np.zeros([np.size(selectReference, 0), 1])
                bestMarker[:, 0] = selectMixture
                bestNumber = selectedNumber
        t = iterativeWeightedSVR(bestReference, bestMarker)
        bestNumberHistory.append(bestNumber)
        proportionDeconvolution[:, i] = t[:, 0]
    return proportionDeconvolution


def mixedConditionNumber(referenceSelect, markerSelect):
    pinvReferenceSelect = np.linalg.pinv(referenceSelect)
    bNorm = np.linalg.norm(markerSelect)
    maxConditionNumber = 0
    tissueNumber = np.size(referenceSelect, 1)
    for i in range(tissueNumber):
        tq = pinvReferenceSelect[i, :]
        conditionNumber = (bNorm / np.abs(np.dot(tq, markerSelect))) * np.linalg.norm(tq)
        if conditionNumber > maxConditionNumber:
            maxConditionNumber = conditionNumber
    return maxConditionNumber


def markerFromSort(sortIndex, tissueNum, markerNum, selectedNumber):
    selectedMarker = np.zeros(markerNum)
    selectedMarker = selectedMarker.astype(np.bool)
    finalMarker = np.arange(markerNum)
    for i in range(tissueNum):
        if selectedNumber > len(sortIndex[i]):
            selectedMarker[sortIndex[i][:]] = True
        else:
            selectedMarker[sortIndex[i][0 : selectedNumber]] = True
    return finalMarker[selectedMarker]


def iterativeWeightedSVR(reference, markerData):
    tissueNum = np.size(reference, 1)
    numOfSamples = np.size(markerData, 1)
    markerNumber = np.size(reference, 0)
    proportionDeconvolution = np.zeros([tissueNum, numOfSamples])
    for i in tqdm(range(numOfSamples)):
        iterNumber = 10
        iterReference = reference
        iterMarkerData = markerData[:, i]
        # Threshold Searching
        mixture = optimize.nnls(iterReference, iterMarkerData)
        test = mixture[0]
        t = test / np.sum(test)
        c1 = np.zeros([np.size(iterReference, 0), 1])
        c1[:, 0] = iterMarkerData[:]
        t1 = np.zeros([tissueNum, 1])
        t1[:, 0] = t
        c2 = np.dot(iterReference, t1)
        error = np.abs(c2 - c1)
        error = error[:, 0]
        error = np.sort(error)
        index = int(np.size(error) * 0.8)
        threshold = error[index]
        for j in range(iterNumber):
            mixture = optimize.nnls(iterReference, iterMarkerData)
            test = mixture[0]
            t = test / np.sum(test)
            c1 = np.zeros([np.size(iterReference, 0), 1])
            c1[:, 0] = iterMarkerData[:]
            t1 = np.zeros([tissueNum, 1])
            t1[:, 0] = t
            c2 = np.dot(iterReference, t1)
            error = np.abs(c2 - c1)
            error = error[:, 0]
            iterSelected = np.arange(np.size(iterReference, 0))
            area = error < threshold
            iterSelected = iterSelected[area]
            iterReference = iterReference[iterSelected, :]
            iterMarkerData = iterMarkerData[iterSelected]
        singleMarker = np.zeros([np.size(iterReference, 0), 1])
        singleMarker[:, 0] = iterMarkerData
        t = nuSVR(iterReference, singleMarker)
        t = t[:, 0]
        proportionDeconvolution[:, i] = t
    return proportionDeconvolution


def nuSVR(reference, markerData):
    nu = [0.25,0.50,0.75]
    tissueNum = np.size(reference, 1)
    numOfSamples = np.size(markerData, 1)
    proportionDeconvolution = np.zeros([tissueNum, numOfSamples])
    nuHistory = []
    p0 = np.zeros([3, tissueNum, numOfSamples])
    for i in range(0, 3, 1):
        nuI = nu[i]
        clf = NuSVR(nu=nuI, kernel='linear')
        for j in range(numOfSamples):
            clf.fit(reference, markerData[:, j])
            t = clf.coef_
            tc = np.dot(clf.dual_coef_, clf.support_vectors_)
            t1 = np.zeros(tissueNum)
            t1[:] = t[0, :]
            area = t1 < 0
            t1[area] = 0
            t1 = t1 / np.sum(t1)
            p0[i, :, j] = t1[:]
    for i in range(numOfSamples):
        minRMSE = 10**(50)
        truth = np.zeros([np.size(reference, 0), 1])
        truth[:, 0] = markerData[:, i]
        for k in range(0, 3, 1):
            pVector = np.zeros([tissueNum, 1])
            pVector[:, 0] = p0[k, :, i]
            temp = np.dot(reference, pVector)
            error = truth - temp
            error = np.sqrt(np.mean(np.multiply(error, error)))
            if error < minRMSE:
                minRMSE = error
                proportionDeconvolution[:, i] = p0[k, :, i]
                bestNu = k
        nuHistory.append(nu[bestNu])
    return proportionDeconvolution

def preDeconCCN(mixInput, refInput):
    multi_run_len = len(mixInput)
    mix = [[] for i in range(multi_run_len)]
    ref_pd = pd.read_csv(refInput, sep = "\t", header = 0)
    ref_depos = ref_pd.iloc[:, 1:]
    celltypes = ref_depos.columns.values.tolist()
    ref = [[] for i in range(ref_depos.shape[0])]
    for i in range(ref_depos.shape[0]):
        ref[i] = ref_depos.iloc[i].tolist()
    for i in range(multi_run_len):
        data = pd.read_csv(
            mixInput[i],
            sep="\t",
            header=0,
            names=[
                "chr",
                "start",
                "end",
                "unmCpG",
                "mCpG",
                "mlCpG",
            ],
        )
        mix[i] = data["mlCpG"].tolist()
    mix = np.transpose(mix)
    
    return np.array(mix), np.array(ref), celltypes

def DeconCCNplot(mixInput, plotOutput, maxSample = 5):
    if maxSample > 0 and maxSample < mixInput.shape[1]:
        mixInput = mixInput.iloc[:, :maxSample]
    
    r = np.arange(mixInput.shape[1])
    colors = ["windows blue", "amber", "greyish",  "faded green", 
              "dusty purple", "orange", "mauve", "dark teal", 
              "light red", "chocolate", "bubblegum pink", "ivory"]
    bot = [0 for i in range(mixInput.shape[1])]
    
    for i in range(mixInput.shape[0]):
        if i < 12:
            plt.bar(
                r, 
                mixInput.iloc[i].tolist(), 
                bottom = bot, 
                color = sns.xkcd_rgb[colors[i % 12]], 
                edgecolor = "white", 
                width = 0.6, 
                label = mixInput._stat_axis.values.tolist()[i],
            )
        for j in range(mixInput.shape[1]):
            bot[j] += mixInput.iloc[i, j]

    plt.xticks(r, mixInput.columns.values.tolist())
    plt.ylabel("proportion")
    plt.legend(
        bbox_to_anchor = (1.05, 1), 
        loc = 2, 
        borderaxespad = 0,
    )
    plt.savefig(plotOutput, bbox_inches = "tight")
    
    return True
    
def processPCA(txtInput):
    multi_run_len = len(txtInput)
    ml = [[] for i in range(multi_run_len)]
    for i in range(multi_run_len):
        data = pd.read_csv(
            txtInput[i],
            sep="\t",
            header=0,
            names=[
                "chr",
                "start",
                "end",
                "unmCpG",
                "mCpG",
                "mlCpG",
            ],
        )
        ml[i] = data["mlCpG"].tolist()
    pca = PCA(n_components = 2)
    pca.fit(ml)
    data_2d = pca.fit_transform(ml)
    return data_2d
    
def clusterplot(casedata, ctrldata, plotOutput, labels = ["case", "control"]):
    theta = np.concatenate((np.linspace(-np.pi, np.pi, 50), np.linspace(np.pi, -np.pi, 50)))
    circle = np.array((np.cos(theta), np.sin(theta)))
    casesigma = np.cov(np.array((casedata[:, 0], casedata[:, 1])))
    ctrlsigma = np.cov(np.array((ctrldata[:, 0], ctrldata[:, 1])))
    ed = np.sqrt(stats.chi2.ppf(0.95, 2))
    ell1 = np.transpose(circle).dot(np.linalg.cholesky(casesigma) * ed)
    ell2 = np.transpose(circle).dot(np.linalg.cholesky(ctrlsigma) * ed)
    a1, b1 = np.max(ell1[:, 0]), np.max(ell1[:, 1])
    a2, b2 = np.max(ell2[:, 0]), np.max(ell2[:, 1])
    t = np.linspace(0, 2 * np.pi, 100)
    fig = plt.figure(figsize = (10, 10))
    p1 = plt.scatter(casedata[:, 0], casedata[:, 1], c = "y")
    plt.plot(a1 * np.cos(t), b1 * np.sin(t), c = "y")
    p2 = plt.scatter(ctrldata[:, 0], ctrldata[:, 1], c = "b")
    plt.plot(a2 * np.cos(t), b2 * np.sin(t), c = "b")
    plt.xlabel("PC1")
    plt.ylabel("PC2")
    plt.legend([p1, p2], labels, loc = "best")
    plt.savefig(plotOutput)
        
def compute_fragprof(bedgzInput, chromsize, txtOutput, gcInput, binlen):
    chf = open(chromsize, "r")
    readline = chf.readlines()
    fp = []
    pos = []
    refs, starts, ends = [], [], []
    for line in readline:
        ref = line.split("\t")
        start = 1
        if ref[0] not in ["chr1", "chr2", "chr3", "chr4",
            "chr5", "chr6", "chr7", "chr8", 
            "chr9", "chr10", "chr11", "chr12", 
            "chr13", "chr14", "chr15", "chr16", 
            "chr17", "chr18", "chr19", "chr20", 
            "chr21", "chr22", "chrX", "chrY", 
        ]:
            continue
        while start <= int(ref[1].strip("\n")):
            end = start + binlen - 1
            refs.append(ref[0])
            starts.append(start)
            ends.append(end)
            start = end + 1
    regions = pd.DataFrame({"ref": refs, "start": starts, "end": ends})
    gc_df = wig2df(gcInput)
    gc_chr = gc_df["chrom"].values.tolist()
    gc_value = gc_df["value"].values.tolist()
    for x in bedgzInput:
        print("Processing", x, "...")
        fpx, shorts, longs = [], [], []
        shorts = []
        longs = []
        f = pysam.Tabixfile(
            filename = x, 
            mode = "r"
        )
        mark = None
        chrstart, chrpos = 0, 0
        gc, posx= [], [[], []]
        for i in range(regions.shape[0]):
            reg = regions.iloc[i].tolist()
            if reg[0] != mark:
                mark = reg[0]
                chrstart = gc_chr.index(reg[0])
                chrpos = 0
            else:
                if gc_chr[chrstart + chrpos] != reg[0]:
                    continue
            if gc_value[chrstart + chrpos] < 0:
                chrpos += 1
                continue
            bin = []
            try:
                f.fetch(reg[0], reg[1], reg[2])
            except ValueError:
                shorts.append(None)
                longs.append(None)
            else:
                for read in f.fetch(reg[0], reg[1], reg[2]):
                    bin.append(int(read.split("\t")[2]) - int(read.split("\t")[1]))
                count = np.bincount(bin, minlength = 201)
                shorts.append(sum(count[100 : 151]))
                longs.append(sum(count[151 : 221]))
            gc.append(gc_value[chrstart + chrpos])
            posx[0].append(reg[0])
            posx[1].append(reg[1])
            chrpos += 1
        median_s = np.median(shorts)
        median_l = np.median(longs)
        shorts_cor = sm.nonparametric.lowess(endog = shorts, exog = gc, frac = 0.03, return_sorted = False)        
        longs_cor = sm.nonparametric.lowess(endog = longs, exog = gc, frac = 0.03, return_sorted = False)
        shorts_cor2 = sm.nonparametric.lowess(endog = shorts_cor, exog = gc, frac = 0.3, return_sorted = False)        
        longs_cor2 = sm.nonparametric.lowess(endog = longs_cor, exog = gc, frac = 0.3, return_sorted = False)         
        shorts_new, longs_new = [], []
        for i in range(len(shorts)):
            shorts_new.append(shorts[i] - shorts_cor2[i] + median_s)
            longs_new.append(longs[i] - longs_cor2[i] + median_l)
            fpx.append(shorts_new[i] / longs_new[i])
        fp.append(fpx)
        pos.append(posx)
    
    fp_df = pd.DataFrame(np.transpose(fp), columns = [x.split('/')[-1] for x in bedgzInput])
    fp_df.to_csv(txtOutput, index = None, sep = "\t")
    return fp, pos
    
def fragProfileplot(caseInput, casepos, ctrlInput, ctrlpos, cytoBandInput, plotOutput, labels = ["case", "control"]):
    cytoBand = pd.read_csv(
        cytoBandInput,
        sep = "\t",
        header = None,
        names = [
            "chrom",
            "start",
            "end",
            "band",
            "color"
        ],
    )
    geneflag = [cytoBand["chrom"][i][3:] + cytoBand["band"][i][0] for i in range(len(cytoBand["chrom"]))]
    
    intv = 1
    mark = None
    posnow = -intv
    nextstart = 0
    xpos = [[]]
    xposx = -1
    intvpos = []
    xlabels = []
    for i in range(len(casepos[0][0])):
        if casepos[0][0][i] != mark:
            mark = casepos[0][0][i]
            cytopos = cytoBand["chrom"].tolist().index(casepos[0][0][i])
            xlabels.append(geneflag[cytopos])
            cytonextpos = [cytoBand["band"][k][0] for k in range(len(cytoBand["band"])) 
                if cytoBand["chrom"][k] == casepos[0][0][i]].index("q") + cytopos
            nextstart = int(cytoBand["start"][cytonextpos])
            intvpos.append(posnow - 1)
            posnow += intv
            intvpos.append(posnow)
            xpos.append([])
            xposx += 1
        elif casepos[0][1][i] >= nextstart and nextstart > 0:
            nextstart = -1
            xlabels.append(geneflag[cytonextpos])
            intvpos.append(posnow - 1)
            posnow += intv
            intvpos.append(posnow)
            xpos.append([])
            xposx += 1
        xpos[xposx].append(posnow)
        posnow += 1
    intvpos.append(posnow - 1)
    intvmidpos = [(intvpos[2 * k + 1] + intvpos[2 * k + 2]) / 2 for k in range(int(len(intvpos) / 2))]
    f, (ax1, ax2) = plt.subplots(2, 1, figsize = [60, 12])
    for i in range(len(caseInput)):
        for j in range(len(xpos)):
            ax1.plot(
                xpos[j],
                caseInput[i][
                    sum([len(xpos[k]) for k in range(j)]) : sum([len(xpos[k]) for k in range(j)]) + len(xpos[j])
                ], 
                color = "black",
                marker = ".", 
                markersize = 0.3, 
                linewidth = 0.3
            )
    ax1.set_ylabel(labels[0])
    ax1.set_xticks(intvpos)
    ax1.set_xticklabels([])
    ax1.xaxis.set_minor_locator(ticker.FixedLocator(intvmidpos))
    ax1.xaxis.set_minor_formatter(ticker.FixedFormatter(xlabels))
    ax1.set_xlim([0, max(max(xpos))])
    ax1.set_ylim([0, 1])
    for i in range(len(ctrlInput)):
        for j in range(len(xpos)):
            ax2.plot(
                xpos[j],
                ctrlInput[i][
                    sum([len(xpos[k]) for k in range(j)]) : sum([len(xpos[k]) for k in range(j)]) + len(xpos[j])
                ], 
                color = "black",
                marker = ".", 
                markersize = 0.3, 
                linewidth = 0.3
            )
    ax2.set_ylabel(labels[1])
    ax2.set_xticks(intvpos)
    ax2.set_xticklabels([])
    ax2.xaxis.set_minor_locator(ticker.FixedLocator(intvmidpos))
    ax2.xaxis.set_minor_formatter(ticker.FixedFormatter(xlabels))
    ax2.set_xlim([0, max(max(xpos))])
    ax2.set_ylim([0, 1])
    plt.savefig(plotOutput)
    
    