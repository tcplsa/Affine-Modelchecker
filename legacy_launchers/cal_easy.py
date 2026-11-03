#!/usr/bin/python
# -*- coding: UTF-8 -*-

from multiprocessing import set_forkserver_preload
import os
import os.path
from posixpath import split
from random import sample
import re
import shutil
from time import monotonic, sleep
from tokenize import Number

# global limit
CUTOFF = 5000
PUNISH = 2 #PAR2
MEMS_MAX = 61440 # 60G

class states(object):
    res = "unknown"
    time = CUTOFF*PUNISH
    mems = MEMS_MAX
    mono = False        # only this one can solve
    best = False        # show the best performance
    ls_time = 0         # LS_time

class solver(object):
    def __init__(self, res_dir, name):
        self.res_dir    = res_dir  # save the results files
        self.print_name = name     # names want to show
        self.datas      = dict()   # datas[ins] save the instances
    def reset(self):
        # SAT-ins UNSAT-ins solved-ins all-ins
        self.sat_num = self.unsat_num = self.solved_num = self.all_num = 0
        self.avg_sat_time = self.avg_unsat_time = self.avg_solved_time = self.avg_all_time = 0.0
        self.PAR_sat_time = self.PAR_unsat_time = self.PAR_solved_time = self.PAR_all_time = 0.0
        self.mono_num = 0
        self.best_num = 0
    def cal_soln(self, ins_name):
        self.all_num += 1
        state = self.datas[ins_name]
        # if(self.datas[ins_name].res=="unsat"):
        #     print(self.datas[ins_name].time)

        # if(self.datas[ins_name].time > CUTOFF):
        #     self.datas[ins_name] = states()
        if(state.res=="sat"):
            #print(self.sat_num)
            self.sat_num            += 1
            self.solved_num         += 1
            self.avg_sat_time       += state.time
            self.avg_solved_time    += state.time
            self.avg_all_time       += state.time
            self.PAR_sat_time       += state.time
            self.PAR_solved_time    += state.time
            self.PAR_all_time       += state.time
        elif(state.res=="unsat"):
            #print(self.unsat_num)
            #print(self.datas[ins_name].time)
            #print(ins_name)
            self.unsat_num          += 1
            self.solved_num         += 1
            self.avg_unsat_time     += state.time
            self.avg_solved_time    += state.time
            self.avg_all_time       += state.time
            self.PAR_unsat_time     += state.time
            self.PAR_solved_time    += state.time
            self.PAR_all_time       += state.time
        else:
            self.avg_all_time       += CUTOFF
            self.PAR_all_time       += CUTOFF * PUNISH
    def deal_avg(self):
        if(self.sat_num>0):
            self.avg_sat_time    /= self.sat_num
            self.PAR_sat_time    /= self.sat_num
        if(self.unsat_num>0):
            self.avg_unsat_time  /= self.unsat_num
            self.PAR_unsat_time  /= self.unsat_num
        if(self.solved_num>0):
            self.avg_solved_time /= self.solved_num
            self.PAR_solved_time /= self.solved_num
        if(self.all_num>0):
            self.avg_all_time    /= self.all_num
            self.PAR_all_time    /= self.all_num
    def to_string(self, state):
        line = ""
        line += str(state.res) + " "
        line += str(round(state.time,2))
        if state.mono:
            line += "[M]"
        elif state.best:
            line += "[B]"
        line += str()
        return line.ljust(18)

        return super().to_string(state)


class solver_SAT_standard_gnomon(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, "r").read()

            if(not len(re.findall(r"s\s+UNSATISFIABLE", fstr))==0):
                self.datas[ins_name].res = "unsat"
            elif(not len(re.findall(r"s\s+SATISFIABLE", fstr))==0):
                self.datas[ins_name].res = "sat"

            if(not self.datas[ins_name].res == "unknown"):
                timestr = re.findall(r"real.*m.*s", fstr)[0]
                minute = int(timestr.split('m')[0].split()[-1])
                second = float(timestr.split('m')[-1].split('s')[0])
                self.datas[ins_name].time = minute * 60 + second

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)


class solver_abc_pdr(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("Output .* was asserted in frame", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("Property proved", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): #if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"


        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_abc_bmc(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("was asserted in frame", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("No output ", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): #if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"


        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_simpleIC3(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("UNSAT", fstr))>0):
                self.datas[ins_name].res = "unsat"
            elif(len(re.findall("SAT", fstr))>0):
                self.datas[ins_name].res = "sat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF):#if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"


        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)


class solver_IC3Ref(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("s\s+1\n", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("s\s+0\n", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): ##if(tmp_t <= CUTOFF*PUNISH)
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_rIC3(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("result: false\n", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("result: true\n", fstr))>0):
                self.datas[ins_name].res = "unsat"
            elif(len(re.findall("result: unsafe\n", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("result: safe\n", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): ##if(tmp_t <= CUTOFF*PUNISH)
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_modelchecker(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("s\s{2,}1\n", fstr))>0): ##s\s+1\n 避免误识别到 ctis: 125 这样的输出行
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("s\s{2,}0\n", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): #if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_modelchecker_bmc(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("s\s+1\n", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("s\s+0\n", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): #if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_iimc_bmc(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("s\s+1\n", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("s\s+2\n", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF): #if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"

        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_iimc(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("Output .* was asserted in frame", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("Property proved", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF):#if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"


        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

class solver_nuxmv(solver):
    def cal_soln(self, ins_name):
        if(not ins_name in self.datas):
            self.datas[ins_name] = states()
            real_file_path = self.res_dir + "/" + ins_name
            fstr = open(real_file_path, 'r').read()

            if(len(re.findall("Unsafe", fstr))>0):
                self.datas[ins_name].res = "sat"
            elif(len(re.findall("Safe", fstr))>0):
                self.datas[ins_name].res = "unsat"

            if(not self.datas[ins_name].res == "unknown"):
                find_all = re.findall(r"Total.*s", fstr)
                tmp_t = float(find_all[-1].split()[-1].strip('s'))
                if(tmp_t <= CUTOFF):#if(tmp_t <= CUTOFF*PUNISH):
                    self.datas[ins_name].time = tmp_t
                else:
                    self.datas[ins_name].res = "unknown"


        return super().cal_soln(ins_name)
    def to_string(self, state):
        return super().to_string(state)

SOLVER_LEN = 20
SAMPLE_LEN = 22
NUMBER_LEN = 8
print_title = True
class calculater(object):
    solvers     = []
    sample_dirs = []    # sample dirs, [sample_dir, sample_name]s
    def __init__(self, solvers, sample_dirs):
        self.solvers = solvers
        self.sample_dirs = sample_dirs
    def __show_in_mark_down(self, samp_name):
        global print_title
        if(print_title):  # 1111111
            print_title = False
            title =  "| sample".ljust(SAMPLE_LEN+2)
            title += " | solver".ljust(SOLVER_LEN+3)
            title += " | #SAT".ljust(NUMBER_LEN+3)
            title += " | avg_t".ljust(NUMBER_LEN+3)
            title += " | #UNSAT".ljust(NUMBER_LEN+3)
            title += " | avg_t".ljust(NUMBER_LEN+3)
            title += " | #ALL".ljust(NUMBER_LEN+3)
            title += " | PAR2_t".ljust(NUMBER_LEN+3)
            title += " | best".ljust(NUMBER_LEN+3)
            title += " | mono".ljust(NUMBER_LEN+3)
            title += " |"
            print(title)

            split =  "| "  + '-'*(SAMPLE_LEN)
            split += " | " + '-'*(SOLVER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " | " + '-'*(NUMBER_LEN)
            split += " |"
            self.split_line = split
            print(split)


        for slv in self.solvers: #2222222
            line =  "| "  + (samp_name + "("+str(self.sample_ins_ct) + ")").ljust(SAMPLE_LEN)
            line += " | " + slv.print_name.ljust(SOLVER_LEN)
            line += " | " + str(slv.sat_num).ljust(NUMBER_LEN)
            line += " | " + str(round(slv.avg_sat_time,2)).ljust(NUMBER_LEN)
            line += " | " + str(slv.unsat_num).ljust(NUMBER_LEN)
            line += " | " + str(round(slv.avg_unsat_time,2)).ljust(NUMBER_LEN)
            line += " | " + str(slv.solved_num).ljust(NUMBER_LEN)
            line += " | " + str(round(slv.PAR_all_time,2)).ljust(NUMBER_LEN)
            line += " | " + str(slv.best_num).ljust(NUMBER_LEN)
            line += " | " + str(slv.mono_num).ljust(NUMBER_LEN)
            line += " |"
            print(line)

    def cal_and_show(self):
        for sample in self.sample_dirs:
            title_line = ""
            for slv in self.solvers:
                title_line += slv.print_name.ljust(18)
            print(title_line)             # 输出 "modelchecker"
            samp_dir  = sample[0]
            samp_name = sample[1]
            print_line_ct = 0
            sample_ins_ct = 0
            for slv in self.solvers:
                slv.reset()
            for ins_name in open(samp_dir):
                sample_ins_ct += 1
                ins_name = ins_name.strip()
                best_time = CUTOFF*PUNISH
                solved_ct = 0
                for slv in self.solvers:#统计最快求解器的求解时间 和能解这个样例的求解器个数
                    slv.cal_soln(ins_name)
                    best_time = min(slv.datas[ins_name].time, best_time) # best_time表示求解这个aiger的最少时间
                    if not slv.datas[ins_name].res == "unknown":
                        solved_ct += 1  # solver_ct表示解出这个aiger的求解器个数
                if(not best_time == CUTOFF*PUNISH): # 找出求解效果最好和唯一能求解的求解器
                    for slv in self.solvers:
                        if(slv.datas[ins_name].time == best_time):
                            slv.datas[ins_name].best = True
                            slv.best_num += 1
                            if(solved_ct == 1):
                                slv.datas[ins_name].mono = True
                                slv.mono_num += 1


                line = ""
                no_answer       = True
                answer_this     = "unknown"
                all_can_solve   = True
                have_diff_res   = False
                have_confliction= False
                res_sat         = False
                res_unsat       = False
                for slv in self.solvers:
                    stt = slv.datas[ins_name]
                    line += slv.to_string(stt)
                    if(not stt.res == "unknown"):
                        no_answer = False
                        answer_this = stt.res
                        if(stt.res == "sat"):
                            res_sat = True
                        elif(stt.res == "unsat"):
                            res_unsat = True
                    elif(stt.res == "unknown"):
                        all_can_solve = False
                line += ins_name
                if(not all_can_solve and not no_answer):
                    have_diff_res = True
                if(res_unsat and res_sat):
                    have_confliction = True
                    have_diff_res = True

                #if(True):
                #if(False):
                #if(no_answer):
                if(not no_answer):
                #if(all_can_solve):
                #if(have_diff_res):
                #if(have_confliction):
                # if(have_diff_res and answer_this == "sat"):
                #if(answer_this == "sat"):
                # if(self.solvers[-2].datas[ins_name].res != self.solvers[-1].datas[ins_name].res):
                    print_line_ct += 1
                    print(line) # 输出aiger的求解结果

            self.sample_ins_ct = sample_ins_ct
            for slv in self.solvers:
                slv.deal_avg() # 输出汇总表格
            self.__show_in_mark_down(samp_name)
            if(print_line_ct>0):
                print("print line ct = ", print_line_ct)
            else:
                print(self.split_line)


def gen_samples(dir):
    samples = []
    for root, dirs, files in os.walk(dir):
        for file in files:
            sample_name = file.strip(".txt")
            sample_dir = os.path.join(root, file)
            # print(sample_dir, sample_name)
            samples.append([sample_dir, sample_name])
    return samples

if __name__ == "__main__":
    solvers = []
    ### MCer-pdr
    # solvers.append(solver_modelchecker("/home/zhulf/data/modelchecker8","modelchecker"))  # 打分+10/cubesize 5000cutoff  (depth>b.depth?)
    # solvers.append(solver_modelchecker("/home/zhulf/data/modelchecker20240103","add heuristic&branch"))  # 20240103重新测试的结果 多解了几个
    # solvers.append(solver_modelchecker("/home/zhulf/data/modelchecker_both_5000","mcer -sc -acc"))   #  没有punish和branch 有savepre
    ## DAC25
    # solvers.append(solver_modelchecker("/home/zhulf/data/res/mcer/20241117_base_5000","Mcer7"))
    # solvers.append(solver_modelchecker("/home/zhulf/data/res/mcer/20241117_acc_5000","Mcer7 -acc"))
    # solvers.append(solver_modelchecker("/home/zhulf/data/res/mcer/20241117_pr_5000","Mcer7 -pr"))
    # solvers.append(solver_modelchecker("/home/zhulf/data/res/mcer/20241117_accpr_5000","Mcer7 -accpr"))


    ### 其他求解器-pdr
    ## ic3ref
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/baseline","ic3ref_base"))  #0219重测的的ic3ref baseline 只少了一个4500秒样例 旧的：#solver_IC3Ref("/home/zhulf/data/res/ic3-baselines/ic3_default","IC3ref_base_old")
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20240925_base_18000","ic3ref_base")) #比上面多一个4500秒样例
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/stateof_orderAssumps_true_18000","ic3ref_reverse"))       # 降序排序
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/myidea_savepre_5000_npreverse","ic3ref_acc_noreverse_5000"))   # acc启发式 (沿用原版的升序排序 实则应该降序)
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/myidea_savepre_5000","ic3ref_acc_5000")) # acc = 降序排序 + acc启发式
    # ic3ref FM24
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20241012_sc_18000","ic3ref -sc"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20240924_acc_sc_18000","ic3ref -sc -acc"))
    # ic3ref DAC25 改用19-24的样例
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20241113_base_5000","ic3ref_base"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20241112_acc_18000","ic3ref -acc")) #   
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20241113_xff_5000","ic3ref -xff"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/20241112_xffacc_18000","ic3ref -accxff"))

    ## 各个比较对象
    ####### solvers.append(solver_simpleIC3("/home/zhulf/data/res/ic3-baselines/simpleIC3","simpleIC3"))
    # solvers.append(solver_nuxmv("/home/zhulf/data/res/ic3-baselines/nuxmv_base_5000","nuxmv"))
    # solvers.append(solver_rIC3("/home/zhulf/data/res/ic3-baselines/ric3_ic3_5000","ric3 -ic3"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3-baselines/iimc","iimc"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3-baselines/iimcquip_5000","iimcquip"))
    # solvers.append(solver_abc_pdr("/home/zhulf/data/res/ic3-baselines/abc_true","ABC")) #abc-true
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/igood_br_rs_18000","IGOODLEMMA18000"))
    # solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/dac24","dac24"))

    ## igoodlemma改
    #solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/igoodlemma_baseline","ic3ref_base_igood"))  # 原版的igood baseline 比一般的ic3ref base还要差
    #solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/minisat_heuristic","ic3ref_minisat"))    # 563行 stable_sort(assumps+sz, assumps+assumps.size(), activityOrder); 低到高效果不好
    #solvers.append(solver_IC3Ref("/home/zhulf/data/res/ic3ref/minisat_heuristic2","ic3ref_minisat"))   # 564行 reverse(assumps+sz, assumps+assumps.size()); 高到低效果好 原因：这一步已知是UNSAT 需要尽快找出矛盾 而分高就代表容易冲突


    ### MCer-bmc
    ##15 17 20   只跑了100步？是有unsat的
    #solvers.append(solver_modelchecker_bmc("/home/zhulf/data/res/bmc_test/modelchecker_bmc","own_bmc"))
    ##15 17 24 4线程 19 20 8线程  
    #solvers.append(solver_modelchecker_bmc("/home/zhulf/data/res/bmc_test/mcer_20241127_5000","mcer_bmc"))                              #mcer_20241127_5000单线程但数据乱了 被“check step”覆盖了 有bug
    #solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/mcer_20250613_5000","mcer_bmc"))
    solvers.append(solver_modelchecker_bmc("/home/zhulf/data/res/bmc_test/mcer_20241127_5000_8thread","mcer_bmc"))
    
    ### ric3-bmc 19-24?
    solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/ric3_kissat_2024_20250105_5000","ric3-bmc-kissat"))
    solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/ric3_nokissat_2024_20250105_5000","ric3-bmc-nokissat"))

    #dmc
    # solvers.append(solver_rIC3("/home/zhulf/data/res/dmc_test/ric3_dmc_5000_default_20250305","dmc"))
    # solvers.append(solver_rIC3("/home/zhulf/data/res/dmc_test/ric3_dmc_5000_disttoinit","dmc_2"))

    ### 其他求解器-bmc
    ##15 17 20
    # solvers.append(solver_iimc_bmc("/home/zhulf/data/res/bmc_test/iimc","iimc-bmc"))
    # solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc","ABC-bmc"))
    # solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc2","ABC-bmc2"))
    # solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc3","ABC-bmc3"))
    # solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/kissat","kissat_bmc2"))
    # solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/kissat_bmc1","kissat_bmc1"))
    ## 15 17 19 20 24
    solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc2_20241127_5000","abc_bmc2"))
    ## 19 20 24
    #solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc1_20250911_5000","abc_bmc1"))
    #solvers.append(solver_abc_bmc("/home/zhulf/data/res/bmc_test/abc3_20250911_5000","abc_bmc3"))

    
    #solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/mcer_bad_20250617_5000","mcer_bmc"))
    #solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/mcer_xor_20250617_5000","mcer_bmc")) # 单线程 识别xor
    #solvers.append(solver_rIC3("/home/zhulf/data/res/bmc_test/mcer_lut_20250715_5000","mcer_bmc_xor"))

    samples = []
    #samples.append(["/home/zhulf/data/MC/hwmcc2015-abc/samples/all.txt", "hwmcc2015"])
    # #samples.append(["/home/zhulf/data/MC/hwmcc2017/samples/all.txt", "hwmcc2017"])
    #samples.append(["/home/zhulf/data/MC/hwmcc2017/samples/except2015.txt", "hwmcc2017"])
    #samples.append(["/home/zhulf/data/MC/hwmcc2019/samples/all.txt", "hwmcc2019"])
    #samples.append(["/home/zhulf/data/MC/hwmcc2020/samples/all.txt", "hwmcc2020"])         #不包含19年同名的样例
    samples.append(["/home/zhulf/data/MC/hwmcc2024/samples/all.txt", "hwmcc2024"])         #不包含2个g的problem17
    clt = calculater(solvers, samples)
    clt.cal_and_show()


