# -*- coding: utf-8 -*-
"""
Created on Fri Sep 20 14:51:54 2019

@author: zhang, Huang
"""

from .StepBase2 import StepBase2
from .cfDNA_utils import commonError, computeCUE
import pandas as pd
import os
import math
from .Configure2 import Configure2

__metaclass__ = type


class computeOCF(StepBase2):
    def __init__(
        self,
        casebedInput=None,
        ctrlbedInput=None,
        refRegInput=None,
        outputdir=None,
        threads=1,
        caseupstream=None,
        ctrlupstream=None,
        stepNum=None, 
        verbose=True,
        **kwargs
    ):
        """
        This function is used for compute OCF values of input bed files.

        computeOCF(casebedInput=None, ctrlbedInput=None, refRegInput=None, outputdir=None, threads=1, caseupstream=None, ctrlupstream=None, labelInput=None, stepNum=None,  verbose=True)
        {P}arameters:
            casebedInput: list, input bed files of case samples.
            ctrlbedInput: list, input bed files of control samples.
            refRegInput: str, reference file for OCF computing.
            outputdir: str, output result folder, None means the same folder as input files.
            threads: int, how many thread to use.
            caseupstream: upstream output results, used for pipeline.
            ctrlupstream: upstream output results, used for pipeline.
            stepNum: int, step number for folder name.
            verbose: bool, True means print all stdout, but will be slow; False means black stdout verbose, much faster.
        """
        if (stepNum is None) and (caseupstream is not None) and (ctrlupstream is None):
            super(computeOCF, self).__init__(stepNum, caseupstream)
        elif (stepNum is None) and (caseupstream is None) and (ctrlupstream is not None):
            super(computeOCF, self).__init__(stepNum, ctrlupstream)
        elif (stepNum is None) and (caseupstream is not None) and (ctrlupstream is not None):
            if caseupstream.getStepID() >= ctrlupstream.getStepID():
                super(computeOCF, self).__init__(stepNum, caseupstream)
            else:
                super(computeOCF, self).__init__(stepNum, ctrlupstream)
        else:
            super(computeOCF, self).__init__(stepNum)

        # set casebedInput and ctrlbedInput
        if ((caseupstream is None) and (ctrlupstream is None)) or (caseupstream is True) or (ctrlupstream is True):
            self.setInput("casebedInput", casebedInput)
            self.setInput("ctrlbedInput", ctrlbedInput)
        else:
            Configure2.configureCheck()
            caseupstream.checkFilePath()
            ctrlupstream.checkFilePath()
            if caseupstream.__class__.__name__ == "bam2bed":
                self.setInput("casebedInput", caseupstream.getOutput("bedOutput"))
            else:
                raise commonError("Parameter caseupstream must from bam2bed.")
            if ctrlupstream.__class__.__name__ == "bam2bed":
                self.setInput("ctrlbedInput", ctrlupstream.getOutput("bedOutput"))
            else:
                raise commonError("Parameter ctrlupstream must from bam2bed.")

        self.checkInputFilePath()

        # set outputdir
        if (caseupstream is None) and (ctrlupstream is None):
            if outputdir is None:
                self.setOutput(
                    "outputdir", os.path.dirname(os.path.abspath(self.getInput("casebedInput")[1])),
                )
            else:
                self.setOutput("outputdir", outputdir)
        else:
            self.setOutput("outputdir", self.getStepFolderPath())

        # set refRegInput
        if refRegInput is None:
            self.setInput("refRegInput", refRegInput)
        else:
            self.setInput("refRegInput", Configure2.getConfig("OCF"))
        
        # set threads
        if (caseupstream is None) and (ctrlupstream is None):
            self.setParam("threads", threads)
        else:
            self.setParam("threads", Configure2.getThreads())
        
        self.setOutput(
            "casetxtOutput",
            [
                os.path.join(self.getOutput("outputdir"), self.getMaxFileNamePrefixV2(x)) + ".txt"
                for x in self.getInput("casebedInput")
            ],
        )

        self.setOutput(
            "ctrltxtOutput",
            [
                os.path.join(self.getOutput("outputdir"), self.getMaxFileNamePrefixV2(x)) + ".txt"
                for x in self.getInput("ctrlbedInput")
            ],
        )

        tmp = pd.read_csv(
            self.getInput("refRegInput"),
            sep="\t",
            header=None,
            names=["chr", "start", "end", "saveflag"],
        )
        save_flag = tmp["saveflag"].unique().tolist()
        self.setParam("saveflag", save_flag)
        
        casecudOutput = []
        ctrlcudOutput = []
        for x in self.getInput("casebedInput"):
            prefix = os.path.splitext(os.path.basename(x))[0]
            for flag in self.getParam("saveflag"):
                casecudOutput.append(self.getOutput("outputdir") + "/" + prefix + "-" + flag + "-cud.txt")
        for x in self.getInput("ctrlbedInput"):
            prefix = os.path.splitext(os.path.basename(x))[0]
            for flag in self.getParam("saveflag"):
                ctrlcudOutput.append(self.getOutput("outputdir") + "/" + prefix + "-" + flag + "-cud.txt")
        self.setOutput("casecudOutput", casecudOutput)
        self.setOutput("ctrlcudOutput", ctrlcudOutput)

        self.setOutput(
            "caseocfOutput",
            [
                os.path.join(self.getOutput("outputdir"), self.getMaxFileNamePrefixV2(x)) + "_OCF.txt"
                for x in self.getInput("casebedInput")
            ],
        )
        
        self.setOutput(
            "ctrlocfOutput",
            [
                os.path.join(self.getOutput("outputdir"), self.getMaxFileNamePrefixV2(x)) + "_OCF.txt"
                for x in self.getInput("ctrlbedInput")
            ],
        )

        finishFlag = self.stepInit(caseupstream)

        if not finishFlag:
            case_multi_run_len = len(self.getInput("casebedInput"))
            ctrl_multi_run_len = len(self.getInput("ctrlbedInput"))
            flagnum = len(self.getParam("saveflag"))
            if verbose:
                for i in range(case_multi_run_len):
                    print("Now, processing file: " + self.getInput("casebedInput")[i])
                    computeCUE(
                        inputFile=self.getInput("casebedInput")[i],
                        refFile=self.getInput("refRegInput"),
                        txtOutput=self.getOutput("casetxtOutput")[i],
                        cudOutput=self.getOutput("casecudOutput")[flagnum * i : flagnum * i + flagnum],
                        ocfOutput=self.getOutput("caseocfOutput")[i],
                        flags=self.getParam("saveflag"),
                    )
                for i in range(ctrl_multi_run_len):
                    print("Now, processing file: " + self.getInput("ctrlbedInput")[i])
                    computeCUE(
                        inputFile=self.getInput("ctrlbedInput")[i],
                        refFile=self.getInput("refRegInput"),
                        txtOutput=self.getOutput("ctrltxtOutput")[i],
                        cudOutput=self.getOutput("ctrlcudOutput")[flagnum * i : flagnum * i + flagnum],
                        ocfOutput=self.getOutput("crelocfOutput")[i],
                        flags=self.getParam("saveflag"),
                    )
            else:
                case_args = [[
                    self.getInput("casebedInput")[i], 
                    self.getInput("refRegInput"), 
                    self.getOutput("casetxtOutput")[i],
                    self.getOutput("casecudOutput")[flagnum * i : flagnum * i + flagnum],
                    self.getOutput("caseocfOutput")[i],
                    self.getParam("saveflag"),
                ] for i in range(case_multi_run_len)]
                self.multiRun(args=case_args, func=computeCUE, nCore=math.ceil(self.getParam("threads")/4))
                ctrl_args = [[
                    self.getInput("ctrlbedInput")[i], 
                    self.getInput("refRegInput"), 
                    self.getOutput("ctrltxtOutput")[i],
                    self.getOutput("ctrlcudOutput")[flagnum * i : flagnum * i + flagnum],
                    self.getOutput("ctrlocfOutput")[i],
                    self.getParam("saveflag"),
                ] for i in range(ctrl_multi_run_len)]
                self.multiRun(args=ctrl_args, func=computeCUE, nCore=math.ceil(self.getParam("threads")/4))
                
        self.stepInfoRec(cmds=[], finishFlag=finishFlag)
