# -*- coding: utf-8 -*-
"""
Created on Sat Mar 14 14:21:15 2020

@author: Jiaqi Huang

"""

from .StepBase2 import StepBase2
from .cfDNA_utils import commonError, compute_fragprof, fragProfileplot
from .Configure2 import Configure2
import os


__metaclass__ = type


class fragprofplot(StepBase2):
    def __init__(
        self,
        casebedgzInput=None,  # list
        ctrlbedgzInput=None,  # list
        fastaInput=None,
        chromsizeInput=None,
        outputdir=None,  # str
        labelInput=None,
        cytoBandInput=None,
        stepNum=None,
        caseupstream=None,
        ctrlupstream=None,
        **kwargs
    ):
        if (stepNum is None) and (caseupstream is not None) and (ctrlupstream is None):
            super(fragprofplot, self).__init__(stepNum, caseupstream)
        elif (
            (stepNum is None) and (caseupstream is None) and (ctrlupstream is not None)
        ):
            super(fragprofplot, self).__init__(stepNum, ctrlupstream)
        elif (
            (stepNum is None)
            and (caseupstream is not None)
            and (ctrlupstream is not None)
        ):
            if caseupstream.getStepID() >= ctrlupstream.getStepID():
                super(fragprofplot, self).__init__(stepNum, caseupstream)
            else:
                super(fragprofplot, self).__init__(stepNum, ctrlupstream)
        else:
            super(fragprofplot, self).__init__(stepNum)

        labelflag = False

        if chromsizeInput is not None:
            self.setInput("chromsizeInput", chromsizeInput)
        else:
            self.setInput("chromsizeInput", Configure2.getConfig("chromsize")) #need to be checked
        
        if fastaInput is None:
            self.setInput("fastaInput", Configure2.getConfig("genome.seq"))
        else:
            self.setInput("fastaInput", fastaInput)
            
        if cytoBandInput is None:
            self.setInput("cytoBandInput", Configure2.getConfig('cytoBand'))
        else:
            self.setInput("cytoBandInput", cytoBandInput)
            
        if caseupstream is None and ctrlupstream is None:
            self.setInput("casebedgzInput", casebedgzInput)
            self.setInput("ctrlbedgzInput", ctrlbedgzInput)
            self.checkInputFilePath()

            if outputdir is None:
                self.setOutput(
                    "outputdir",
                    os.path.dirname(
                        os.path.abspath(self.getInput("casebedgzInput")[1])
                    ),
                )
            else:
                self.setOutput("outputdir", outputdir)

        else:
            Configure2.configureCheck()
            caseupstream.checkFilePath()
            ctrlupstream.checkFilePath()

            if caseupstream.__class__.__name__ == "bam2bed":
                self.setInput("casebedgzInput", caseupstream.getOutput("bedgzOutput"))
            else:
                raise commonError("Parameter upstream must from bam2bed.")

            if ctrlupstream.__class__.__name__ == "bam2bed":
                self.setInput("ctrlbedgzInput", ctrlupstream.getOutput("bedgzOutput"))
            else:
                raise commonError("Parameter upstream must from bam2bed.")

            self.setOutput("outputdir", self.getStepFolderPath())
    
        if labelInput is not None:
            self.setParam("label", labelInput)
            labelflag = True
        self.setParam("binlen", 5000000)

        self.setOutput(
            "plotOutput",
            os.path.join(
                self.getOutput("outputdir"),
                "fragmentation_profile.png",
            )
        )
        
        self.setOutput(
            "gcOutput", 
            os.path.join(
                self.getOutput("outputdir"), 
                self.getMaxFileNamePrefixV2(self.getInput("fastaInput"))
            ) + ".gc.wig"
        )

        finishFlag = self.stepInit(caseupstream)
        
        gc_tmp_cmd = self.cmdCreate(["gcCounter",
                                     "-w", self.getParam("binlen"),
                                     self.getInput("fastaInput"),
                                     ">", self.getOutput("gcOutput")])

        if not finishFlag:
            if not os.path.exists(self.getOutput("gcOutput")):
                self.run([gc_tmp_cmd])
            case_fp, case_pos = compute_fragprof(
                self.getInput("casebedgzInput"),
                self.getInput("chromsizeInput"),
                self.getOutput("gcOutput"),
                self.getParam("binlen"),
            )
            ctrl_fp, ctrl_pos = compute_fragprof(
                self.getInput("ctrlbedgzInput"),
                self.getInput("chromsizeInput"),
                self.getOutput("gcOutput"),
                self.getParam("binlen"),
            )
            if labelflag:
                fragProfileplot(
                    case_fp, 
                    case_pos,
                    ctrl_fp, 
                    ctrl_pos,
                    self.getInput("cytoBandInput"),
                    self.getOutput("plotOutput"),                    
                    self.getParam("label"),
                )
            else:
                fragProfileplot(
                    case_fp, 
                    case_pos, 
                    ctrl_fp, 
                    ctrl_pos, 
                    self.getInput("cytoBandInput"),
                    self.getOutput("plotOutput")
                )
            
        self.stepInfoRec(cmds=[[gc_tmp_cmd]], finishFlag=finishFlag)