# coding=utf-8
import pandas as pd
import numpy as np
import datetime
# import sys
# sys.path.append('../../')
from JohnsonUtil import LoggerFactory
log = LoggerFactory.log
import numba as nb
# log = LoggerFactory.getLogger('chan',show_detail=False)
# 处理k线成缠论k线,临时函数
import time
@nb.jit(nopython=True)
def fast_chan_inclusion(high, low, vol, amount):
    """
    使用 Numba 加速的缠论包含关系处理
    """
    n = len(high)
    if n == 0:
        return (np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0), 
                np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))

    res_high = np.zeros(n)
    res_low = np.zeros(n)
    res_vol = np.zeros(n)
    res_amount = np.zeros(n)
    res_idx = np.zeros(n, dtype=np.int64)
    res_end_idx = np.zeros(n, dtype=np.int64)

    res_high[0] = high[0]
    res_low[0] = low[0]
    res_vol[0] = vol[0]
    res_amount[0] = amount[0]
    res_idx[0] = 0
    res_end_idx[0] = 0
    
    count = 1
    up_direction = True 

    for i in range(1, n):
        cur_h, cur_l = high[i], low[i]
        last_h, last_l = res_high[count-1], res_low[count-1]
        
        if count >= 2:
            prev_h = res_high[count-2]
            if last_h > prev_h: up_direction = True
            elif last_h < prev_h: up_direction = False
        
        # 包含关系
        if (cur_h >= last_h and cur_l <= last_l) or (cur_h <= last_h and cur_l >= last_l):
            if up_direction:
                res_high[count-1] = max(cur_h, last_h)
                res_low[count-1] = max(cur_l, last_l)
            else:
                res_high[count-1] = min(cur_h, last_h)
                res_low[count-1] = min(cur_l, last_l)
            res_vol[count-1] += vol[i]
            res_amount[count-1] += amount[i]
            res_end_idx[count-1] = i
        else:
            res_high[count] = cur_h
            res_low[count] = cur_l
            res_vol[count] = vol[i]
            res_amount[count] = amount[i]
            res_idx[count] = i
            res_end_idx[count] = i
            count += 1
            
    return (res_high[:count], res_low[:count], res_vol[:count], res_amount[:count], 
            res_idx[:count], res_end_idx[:count])

def parse2ChanK(k_data, k_values=None, chan_kdf=True):
    if not chan_kdf:
        if 'enddate' not in k_data.columns:
            k_data = k_data.copy()
            k_data['enddate'] = k_data.index
        return k_data
    time_s = time.time()
    h, l, v, a, s_idx, e_idx = fast_chan_inclusion(
        k_data['high'].values, k_data['low'].values, 
        k_data['vol'].values, k_data['amount'].values
    )
    chanK = pd.DataFrame({
        'high': h, 'low': l, 'vol': v, 'amount': a,
        'enddate': k_data.index[e_idx],
        'open': k_data['open'].values[s_idx],
        'close': k_data['close'].values[e_idx]
    }, index=k_data.index[s_idx])
    log.info("parse2ChanK optimized: %0.4fs, %d -> %d" % (time.time()-time_s, len(k_data), len(chanK)))
    return chanK

# chanK = parse2ChanK(k_data, k_values)
# print chanK
# 找顶底分型的idx
# 如果 连续顶顶，或底底： 顶：high最大的顶， 低：low最小的低
# 顶：1 低：-1


def parse2ChanFen(chanK, recursion=False):
    fenTypes = []  # 分型类型数组 1,-1构成
    fenIdx = []  # 分型对应缠论k的下标
    # print chanK.index
    # 添加分型数据
    # 过滤连续同分型

    def appendFen(ft, fidx):
        if len(fenIdx) == 0:
            fenTypes.append(ft)
            fenIdx.append(fidx)
            return
        fenType_bf = fenTypes[len(fenTypes) - 1]
        if fenType_bf == ft:
            fenType_bf, fenIdx_bf = fenTypes.pop(), fenIdx.pop()
            fidx = fenIdx_bf if (ft == 1 and chanK['high'][fenIdx_bf] > chanK['high'][fidx])\
                or (ft == -1 and chanK['low'][fenIdx_bf] < chanK['low'][fidx]) else fidx
        fenTypes.append(ft)
        fenIdx.append(fidx)
    
    for i, dt in enumerate(chanK.index):
        # if i==0 or i==len(chanK.index)-1:continue
        if i == 0:
            continue

        if i != len(chanK.index) - 1:
            # 顶分型
            log.debug("chanK:%s hi+1:%s hi:%s hi-1:%s" % (str(chanK.index[i])[:10], chanK['high'][i + 1], chanK['high'][i], chanK['high'][i - 1]))
            if i == 1 and len(chanK.index) >= i+2:
                # if chanK['high'][i] > chanK['high'][i - 1] and chanK['low'][i] >
                # chanK['low'][i - 1] and chanK['close'][i] < ((chanK['high'][i] + chanK['low'][i]) / 2):
                if chanK['high'][i] > chanK['high'][i - 1] and chanK['low'][i] > chanK['low'][i - 1] and chanK['close'][i] > chanK['close'][i - 1]:
                    log.debug("firstLow:%s dt:%s hi-1:%s cl-1:%s cl:%s" %
                              (i-1, str(chanK.index[i-1])[:10], chanK['high'][i-1], chanK['close'][i-1], chanK['close'][i]))
                    appendFen(-1, i - 1)
                # 底分型
                # print chanK['low'][i+1],chanK['low'][i],chanK['low'][i-1]
                # if chanK['low'][i] < chanK['low'][i - 1] and chanK['high'][i] <
                # chanK['high'][i - 1] and chanK['close'][i] < ((chanK['high'][i] +
                # chanK['low'][i]) / 2):
                elif chanK['low'][i] < chanK['low'][i - 1] and chanK['high'][i] < chanK['high'][i - 1] and chanK['close'][i] < chanK['close'][i - 1]:
                    log.debug("firstTop:%s dt:%s lo-1:%s cl-1:%s cl:%s" %
                              (i-1, str(chanK.index[i-1])[:10], chanK['low'][i-1], chanK['close'][i-1], chanK['close'][i]))
                    appendFen(1, i - 1)

                else:
                    chan_h = chanK['high'][:i+2].values.tolist()
                    chan_l = chanK['low'][:i+2].values.tolist()
                    if chan_h.index(max(chan_h)) == chan_l.index(max(chan_l)):
                        appendFen(1, chan_h.index(max(chan_h)))
                        log.debug("Lis-firstTop:%s dt:%s lo-1:%s cl-1:%s cl:%s" %
                              (i-1, str(chanK.index[i-1])[:10], chanK['low'][i-1], chanK['close'][i-1], chanK['close'][i]))                    
                    elif chan_h.index(min(chan_h)) == chan_l.index(min(chan_l)):
                        appendFen(-1, chan_h.index(min(chan_h)))        
                        log.debug("Lis-firstLow:%s dt:%s hi-1:%s cl-1:%s cl:%s" %
                              (i-1, str(chanK.index[i-1])[:10], chanK['high'][i-1], chanK['close'][i-1], chanK['close'][i]))

            else:
                if chanK['high'][i + 1] < chanK['high'][i] > chanK['high'][i - 1]:
                    log.debug("Top:%s dt:%s cl+1:%s cl:%s cl-1:%s" % (i, str(chanK.index[i])
                                                                      [:10], chanK['close'][i + 1], chanK['close'][i], chanK['close'][i - 1]))
                    appendFen(1, i)
                # 底分型
                # print chanK['low'][i+1],chanK['low'][i],chanK['low'][i-1]
                if chanK['low'][i + 1] > chanK['low'][i] < chanK['low'][i - 1]:
                    log.debug("Low:%s dt:%s cl+1:%s cl:%s cl-1:%s" % (i, str(chanK.index[i])
                                                                      [:10], chanK['close'][i + 1], chanK['close'][i], chanK['close'][i - 1]))
                    appendFen(-1, i)
        else:
            if recursion:
                if chanK['high'][i] > chanK['high'][i - 1] and chanK['low'][i] > chanK['low'][i - 1] and chanK['close'][i] < ((chanK['high'][i] + chanK['low'][i]) / 2):
                    log.debug("lastTop:%s dt:%s  cl:%s cl-1:%s hi:%s" %
                              (i, str(chanK.index[i])[:10], chanK['close'][i], chanK['close'][i - 1], chanK['high'][i]))
                    appendFen(1, i)
                # 底分型
                # print chanK['low'][i+1],chanK['low'][i],chanK['low'][i-1]
                if chanK['low'][i] < chanK['low'][i - 1] and chanK['high'][i] < chanK['high'][i - 1] and chanK['close'][i] > ((chanK['high'][i] + chanK['low'][i]) / 2):
                    log.debug("lastTop:%s dt:%s cl:%s cl-1:%s low:%s" %
                              (i, str(chanK.index[i])[:10], chanK['close'][i], chanK['close'][i - 1], chanK['low'][i]))
                    appendFen(-1, i)
            else:
                continue

    log.debug("fenTypes:%s fenIdx:%s cuts:%s recurs:%s lastD:%s"%(fenTypes[:3], fenIdx[:3], len(chanK), recursion,str(chanK.index[-1])[:10]))
    return fenTypes, fenIdx
# fenTypes, fenIdx = parse2ChanFen(chanK)

# print fenTypes, fenIdx

# 分型构成笔
# 构成笔条件，1、顶低分型间隔了n个chanK线， 2、中间不会出现比第一个分型结构更高（顶）或更低（底）的分型，否则线段破坏，连接上一笔


def parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=3):
    biIdx = []  # 笔对应的缠论k线 idx
    frsBiType = 0  # 起始笔的走势，biIdx 奇数下标就是相反走势 1、向上，-1向下
    least_khl_num = least_khl_num  # 分笔间隔的最小 chanK 数量 中间排除顶低的chanK
    # print "least_khl_num:",least_khl_num
    toConBfIdx = 0  # 连接到上一笔末尾的 分型idx
    # 判断笔破坏

    def judgeBiBreak(idxb, idxa):
        fenType = fenTypes[idxb]
        fenType1 = -fenType
#         print '分型破坏前', fenType, fenIdx[idxb], fenIdx[idxa]
        _break = False
        _breaki_k = 0
        _breakj_k = 0

        # if judgeBreak(fenType, fenIdx[idxb], fenIdx[idxa]):
        #    if idxa+1==len(fenIdx): _break, _breakj_k = True, idxa-1
        #    else: _break, _breaki_k = True, idxa+1
        # return _break, _breaki_k, _breakj_k

        # 不用判断分型间的破坏
        for k in range(idxb, idxa)[2::2]:
            # 当前i分型破坏
            if judgeBreak(fenType, fenIdx[idxb], fenIdx[k]):
                _break, _breaki_k = True, k
                break
        for k in range(idxb, idxa)[1::2]:
            # 末尾j分型破坏
            if judgeBreak(fenType1, fenIdx[idxa], fenIdx[k]):
                _break, _breakj_k = True, k
                break
        return _break, _breaki_k, _breakj_k
    # 分型破坏

    def judgeBreak(fenType, bf, af):
        return (fenType == -1 and chanK['low'][af] < chanK['low'][bf])\
            or (fenType == 1 and chanK['high'][af] > chanK['high'][bf])

    def reAssignBi(biIdx, breakBi, breakBj, i, j):
        toConBfIdx = i + 1 if len(biIdx) == 0 else breakBi
        if breakBi > 0 and len(biIdx) > 0:
            fb_ = biIdx.pop()
#                         print '首分型破坏, 旧分型:%d, 新的分型:%d'%(fb_,fenIdx[breakBi])
            biIdx.append(fenIdx[breakBi])
            if len(biIdx) > 1 and 0 < breakBj < breakBi and judgeBreak(fenTypes[i - 1], biIdx[len(biIdx) - 2], fenIdx[breakBj]):
                fa_ = biIdx.pop()
                fb_ = biIdx.pop()
#                             print '尾分型破坏并连接上一点, 移除分型:%d，旧分型:%d, 新的分型:%d'%(fa_, fb_,fenIdx[breakBj])
                biIdx.append(fenIdx[breakBj])
                toConBfIdx = breakBj
            return toConBfIdx,  -1  # -1：break 1:continue 0:不执行
        if breakBj > 0:
            #                         breakBj = breakBj1 if breakBj==-1 or judgeBreak(fenTypes[i-1], fenIdx[breakBj], fenIdx[breakBj1]) else breakBj
            if j + 2 >= len(fenIdx) and len(biIdx) > 1 and\
                    judgeBreak(fenTypes[i - 1], biIdx[len(biIdx) - 2], fenIdx[breakBj]):
                fa_ = biIdx.pop()
                fb_ = biIdx.pop()
#                             print '尾分型破坏并连接上一点, 移除分型:%d，旧分型:%d, 新的分型:%d'%(fa_, fb_,fenIdx[breakBj])
                biIdx.append(fenIdx[breakBj])
                toConBfIdx = breakBj
                return toConBfIdx,  -1  # -1：break 1:continue 0:不执行
            return toConBfIdx,  1  # -1：break 1:continue 0:不执行
        return toConBfIdx,  0  # -1：break 1:continue 0:不执行
    for i, kidx in enumerate(fenIdx):
        #         print '生成的笔', biIdx
        #         print toConBfIdx, 'the i is ', i
        if i < toConBfIdx or i == len(fenIdx) - 1:
            continue
        # 后面没有符合条件的笔
        if len(biIdx) > 1 and toConBfIdx == 0:
            break
        toConBfIdx = 0
        for j in range(len(fenIdx))[i + 1::2]:
            log.debug("j:%s fenIdx:%s i:%s kidx:%s" % (j, fenIdx[j], i, kidx))
            if (fenIdx[j] - kidx) > least_khl_num:
                # print '差是', fenIdx[j],kidx,least_khl_num
                # if (chanK.index.tolist().index[chanK.index[fenIdx[j]]] - chanK.index.tolist().index[chanK.index[kidx]])> least_khl_num:
                #                 print 'append', i, j, fenIdx[i], fenIdx[j]
                # breakType True 同分型， False 末尾分型
                flag, breakBi, breakBj = judgeBiBreak(i, j)
                log.debug("flag:%s breakBi:%s breakBj:%s" % (flag, breakBi, breakBj))
                if flag:
                    toConBfIdx, _bcn = reAssignBi(biIdx, breakBi, breakBj, i, j)
                    if _bcn == -1:
                        break
                    if _bcn == 1:
                        continue
                if len(biIdx) == 0:
                    biIdx.append(kidx)
                    frsBiType = -fenTypes[i]
                    biIdx.append(fenIdx[j])
                    toConBfIdx, _bcn = reAssignBi(biIdx, breakBi, breakBj, i, j)
                    if _bcn == -1 or _bcn == 1:
                        biIdx = []
                        toConBfIdx = i + 1
                        break
                    toConBfIdx = j
                    break
                biIdx.append(fenIdx[j])
#                 print biIdx
                toConBfIdx = j
#                 print toConBfIdx
                break

    return biIdx, frsBiType
# 最终线段生成
# 1、遍历相对高低点，判断线段破坏，
#  破坏以后,如果总长度是0，i可以后移，否则重构之前的线段
#  重构规则，找破坏点相对高点/低点，如果存在线段高点/低点>/<破坏高点/低点， 则连接此线段
# 2、形成线段中间至少有两点j-i>2


def parse2ChanXD(frsBiType, biIdx, chanK):
    lenBiIdx = len(biIdx)
    xdIdx = []
    xfenTypes = []
    if lenBiIdx == 0:
        return xdIdx, xfenTypes
    afIdx = 0
    # 重构线段

    def refactorXd(txIdx, nxIdx, chanK):
        xdIdxn = xdIdx
        xfenTypesn = xfenTypes
        if len(xdIdxn) == 0 or txIdx == -1 or nxIdx == -1:
            return 0, xdIdxn, xfenTypesn
        for m in range(-len(xdIdxn) + 1, 1)[1::2]:
            k = -m
            # 满足逆向不破坏
#             print '开始逆向破坏：逆向分型，逆向点，线段点', xfenTypesn[k], nxIdx, xdIdxn[k]
            if (xfenTypesn[k] == -1 and chanK['low'][xdIdxn[k]] < chanK['low'][nxIdx])\
                    or (xfenTypesn[k] == 1 and chanK['high'][xdIdxn[k]] > chanK['high'][nxIdx]):
                for n in range(-len(xdIdxn) + 1, m):
                    xfenTypesn.pop()
                    xdIdxn.pop()
                xdIdxn.append(txIdx)
                xfenTypesn.append(-xfenTypesn[len(xfenTypes) - 1])
                return biIdx.index(txIdx), xdIdxn, xfenTypesn
        xdIdxn = []
        xfenTypesn = []
#         print '逆向破坏', nxIdx, xdIdxn, xfenTypesn
        return biIdx.index(nxIdx), xdIdxn, xfenTypesn
    # 判断线段破坏

    def judgeBreak(fenType, afPrice, idx, chanK):
        return (fenType == -1 and afPrice < chanK['low'][idx]) \
            or (fenType == 1 and afPrice > chanK['high'][idx])
    for i, idx in enumerate(biIdx):
        if afIdx < 0:
            break  # 线段破坏以后没有合适线段
        fenType = 1 if (frsBiType == 1 and i % 2 == 1) or (frsBiType == -1 and i % 2 == 0) \
            else -1
#         print '开始判断%d,分型类型%d'%(idx, fenType)
        # 符合要求的连段
        if i < afIdx:
            continue
        # 找同向相对高低点
        afPrice = 0 if fenType == -1 else 10000
        tongxiang_price_ = 10000 - afPrice
        nixiang_idx, tongxiang_idx = -1, -1
        i_continued = False
        for j in range(i + 1, lenBiIdx)[0::2]:
            # 同向相对高低点
            if (fenType == -1 and tongxiang_price_ > chanK['low'][biIdx[j - 1]]) \
                    or (fenType == 1 and tongxiang_price_ < chanK['high'][biIdx[j - 1]]):
                tongxiang_price_ = chanK['high'][biIdx[j - 1]] if fenType == 1 else chanK['low'][biIdx[j - 1]]
                tongxiang_idx = biIdx[j - 1]
            # 线段破坏
#             print '线段破坏前', idx, tongxiang_idx
            # 同向破坏
            if judgeBreak(fenType, tongxiang_price_, idx, chanK) and idx != tongxiang_idx:
                #                 print '同向已经破坏'
                afIdx, xdIdx, xfenTypes = refactorXd(tongxiang_idx, nixiang_idx, chanK)
                i_continued = True
                break
#             print '符合要求前', biIdx[i], biIdx[j], afPrice, chanK['high'][biIdx[j]], chanK['low'][biIdx[j]],fenType
            if (fenType == -1 and chanK['high'][biIdx[j]] > afPrice) or (fenType == 1 and chanK['low'][biIdx[j]] < afPrice):
                afPrice = chanK['high'][biIdx[j]] if fenType == -1 else chanK['low'][biIdx[j]]
                nixiang_idx = biIdx[j]
                # 线段不符合要求
#                 print '符合要求的i,j', biIdx[i], biIdx[j]
                if j - i <= 2:
                    continue
                # 逆向破坏
#                 if judgeBreak(-fenType, nixiang_idx, idx, chanK) and idx!=nixiang_idx:
# #                     print '逆向已经破坏'
#                     afIdx, xdIdx, xfenTypes = refactorXd(tongxiang_idx, nixiang_idx, chanK)
#                     break
                if len(xdIdx) == 0:
                    #                     print '线段长度为0破坏', fenType, idx, judgeBreak(fenType, tongxiang_price_, idx, chanK)
                    if judgeBreak(fenType, tongxiang_price_, idx, chanK):
                        i_continued = True
                        break
                    xfenTypes.append(fenType)
                    xdIdx.append(idx)
                    xdIdx.append(biIdx[j])
                    xfenTypes.append(-fenType)
                else:
                    # 不用同向线段连接
                    #                     fenTypeb = xfenTypes[len(xfenTypes)-1]
                    #                     xdIdxb = xdIdx.pop()
                    #                     if fenTypeb == -fenType:
                    #                         xdIdx.append(biIdx[j])
                    #                     else:
                    #                         xdIdx.append(xdIdxb)
                    #                         xfenTypes.append(-fenTypeb)
                    #                         xdIdx.append(biIdx[j])
                    xfenTypes.append(-xfenTypes[len(xfenTypes) - 1])
                    xdIdx.append(biIdx[j])
                afIdx = j
                i_continued = True
                break
            else:
                continue
        if not i_continued and len(xdIdx) > 0:
            # 都不符合要求时，最后重构最小线段
            last_idx = xdIdx.pop()
            last_type = xfenTypes[len(xfenTypes) - 1]
            for j in range(biIdx.index(last_idx), len(biIdx))[2::2]:
                if judgeBreak(last_type, chanK['low'][biIdx[j]] if last_type == -1 else chanK['high'][biIdx[j]], last_idx, chanK):
                    last_idx = biIdx[j]
            xdIdx.append(last_idx)
            break
    return xdIdx, xfenTypes
# biIdx, frsBiType = parse2ChanBi(fenTypes, fenIdx, chanK)
# print biIdx,frsBiType
# 简单线段形成，主要用于判断是否是大级别的笔
# 区间找高低点，判断是否符合 高低点中包含>2个笔点就阔以


def parse2Xianduan(biIdx, chanK, least_windows=2):
    xdIdx = []
    if len(biIdx) == 0:
        return xdIdx, 0

    def appendXd(lowIdx, highIdx, xdType):
        if len(xdIdx) == 0:
            if xdType == 1:
                xdIdx.append(lowIdx)
            else:
                xdIdx.append(highIdx)
        if (xdType == 1 and len(xdIdx) % 2 == 1) or (xdType == -1 and len(xdIdx) % 2 == 0):
            xdIdx.append(highIdx)
        else:
            xdIdx.append(lowIdx)

    def genXianduan(biIdx, chanK, xdType=0):
        highMax, lowMin = 0, 10000
        highIdx, lowIdx = -1, -1
        lenXd = len(xdIdx)
        for idx in biIdx:
            if chanK['high'][idx] > highMax:
                highMax = chanK['high'][idx]
                highIdx = idx
            if chanK['low'][idx] < lowMin:
                lowMin = chanK['low'][idx]
                lowIdx = idx

        # 构成简易线段
        # print biIdx, xdIdx, lowIdx, highIdx
        if lowIdx != -1:
            xdDiff = biIdx.index(lowIdx) - biIdx.index(highIdx)
            # print least_windows
            if abs(xdDiff) > least_windows:
                if lenXd == 0:
                    xdType = 1 if xdDiff < 0 else -1
                appendXd(lowIdx, highIdx, xdType)
    #             print lowIdx, highIdx, xdIdx
                genXianduan(biIdx[biIdx.index(xdIdx[len(xdIdx) - 1]):], chanK, xdType)
        return xdType
    xdType = genXianduan(biIdx, chanK)
    return xdIdx, xdType

# 笔形成最后一段未完成段判断是否是次级别的走势形成笔


def con2Cxianduan(stock, k_data, chanK, frsBiType, biIdx, end_date, cur_ji=1):
    max_k_num = 4
    if cur_ji >= 4 or len(biIdx) == 0:
        return biIdx
    idx = biIdx[len(biIdx) - 1]
    k_data_dts = list(k_data.index)
    st_data = chanK['enddate'][idx]
    if st_data not in k_data_dts:
        return biIdx
    # 重构次级别线段的点到本级别的chanK中

    def refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji):
        new_biIdx = []
        biIdxB = biIdx[len(biIdx) - 1] if len(biIdx) > 0 else 0
        for xdIdxcn in xdIdxc:
            for chanKidx in range(len(chanK.index))[biIdxB:]:
                if judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
                    new_biIdx.append(chanKidx)
                    break
        return new_biIdx
    # 判断次级别日期是否被包含

    def judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
        _end_date = chanK['enddate'][chanKidx] + datetime.timedelta(hours=15) if cur_ji == 1 else chanK['enddate'][chanKidx]
        _start_date = chanK.index[chanKidx] if chanKidx == 0\
            else chanK['enddate'][chanKidx - 1] + datetime.timedelta(minutes=1)
        return _start_date <= chanKc.index[xdIdxcn] <= _end_date
    # cur_ji = 1 #当前级别
    # 符合k线根数大于4根 1日级别， 2 30分钟， 3 5分钟， 4 一分钟
    if len(k_data_dts) - k_data_dts.index(st_data) > 4:
        frequency = '30m' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else '1m'
        k_data_c = get_price(stock, st_data, end_date, frequency=frequency)
        chanKc = parse2ChanK(k_data_c, k_data_c.values)
        fenTypesc, fenIdxc = parse2ChanFen(chanKc)
        if len(fenTypesc) == 0:
            return biIdx
        biIdxc, frsBiTypec = parse2ChanBi(fenTypesc, fenIdxc, chanKc)
        if len(biIdxc) == 0:
            return biIdx
        xdIdxc, xdTypec = parse2Xianduan(biIdxc, chanKc)
        biIdxc = con2Cxianduan(stock, k_data_c, chanKc, frsBiTypec, biIdxc, end_date, cur_ji + 1)
        if len(xdIdxc) == 0:
            return biIdx
        # 连接线段位为上级别的bi
        lastBiType = frsBiType if len(biIdx) % 2 == 0 else -frsBiType
        if len(biIdx) == 0:
            return refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
        lastbi = biIdx.pop()
        firstbic = xdIdxc.pop(0)
        # 同向连接
        if lastBiType == xdTypec:
            biIdx = biIdx + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
        # 逆向连接
        else:
            #             print '开始逆向连接'
            _mid = [lastbi] if (lastBiType == -1 and chanK['low'][lastbi] <= chanKc['low'][firstbic])\
                or (lastBiType == 1 and chanK['high'][lastbi] >= chanKc['high'][firstbic]) else\
                [chanKidx for chanKidx in range(len(chanK.index))[biIdx[len(biIdx) - 1]:]
                 if judge_day_bao(chanK, chanKidx, chanKc, firstbic, cur_ji)]
            biIdx = biIdx + [_mid[0]] + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
    return biIdx

def parse2ChanZS(biIdx, chanK):
    """
    中枢识别: 连续三笔有重叠价格区间
    :param biIdx: 分笔索引列表
    :param chanK: 缠论 K 线 DataFrame
    :return: zs_list [{"start":, "end":, "zd":, "zg":, "bi_count":}]
    """
    zs_list = []
    if len(biIdx) < 3:
        return zs_list
        
    def get_bi_range(idx1, idx2, chanK):
        # 笔的价格区间
        p1 = chanK['high'][idx1] if chanK['high'][idx1] > chanK['high'][idx2] else chanK['high'][idx2]
        p2 = chanK['low'][idx1] if chanK['low'][idx1] < chanK['low'][idx2] else chanK['low'][idx2]
        # 但更严谨的缠论定义：笔是连接两个分型的
        # 我们用 biIdx[i] 和 biIdx[i+1] 之间的价格极值
        h = max(chanK['high'][idx1], chanK['high'][idx2])
        l = min(chanK['low'][idx1], chanK['low'][idx2])
        return l, h

    i = 0
    while i <= len(biIdx) - 3:
        # 取连续三笔
        l1, h1 = get_bi_range(biIdx[i], biIdx[i+1], chanK)
        l2, h2 = get_bi_range(biIdx[i+1], biIdx[i+2], chanK)
        l3, h3 = get_bi_range(biIdx[i+2], biIdx[i+3] if i+3 < len(biIdx) else biIdx[i+2], chanK) # 若只有三笔，最后一笔用原点

        # 重叠区间 ZD, ZG
        zd = max(l1, l2, l3)
        zg = min(h1, h2, h3)
        
        if zd < zg:
            # 构成中枢
            zs = {
                'start': biIdx[i],
                'end': biIdx[i+3] if i+3 < len(biIdx) else biIdx[i+2],
                'zd': zd,
                'zg': zg,
                'bi_start_idx': i,
                'bi_end_idx': i+2
            }
            # 扩展中枢: 检查后续笔是否仍在 zd, zg 范围内
            j = i + 3
            while j < len(biIdx):
                lj, hj = get_bi_range(biIdx[j-1], biIdx[j], chanK)
                # 只要这笔与当前中枢区间有重叠，就属于同一个中枢的延伸
                if max(zd, lj) < min(zg, hj):
                    zs['end'] = biIdx[j]
                    zs['bi_end_idx'] = j - 1
                    j += 1
                else:
                    break
            zs_list.append(zs)
            i = j - 1 # 跳过已进入中枢的笔，寻找下一个独立中枢
        else:
            i += 1
            
    return zs_list

def get_chan_analysis(k_data, least_khl_num=3, chanK_flag=True):
    """
    缠论分析统一接口
    :param k_data: 原始 K 线 DataFrame (含 open, close, high, low, vol, amount)
    :param least_khl_num: 分笔最小 K 线数
    :param chanK_flag: 是否进行包含处理
    :return: (chanK, {biIdx, frsBiType, xdIdxs, xfenTypes, fenIdx, fenTypes})
    """
    # 1. 包含处理
    chanK = parse2ChanK(k_data, chan_kdf=chanK_flag)
    
    # 2. 顶底分型
    fenTypes, fenIdx = parse2ChanFen(chanK)
    
    # 3. 分笔 (核心性能点)
    biIdx, frsBiType = parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
    
    # 4. 线段 (原版更灵活的识别)
    xdIdxs_easy, xdType_easy = parse2Xianduan(biIdx, chanK, least_windows=2)
    # 构造 xfenTypes 已匹配前端绘图逻辑 (1为顶, -1为底)
    # parse2Xianduan 返回的 xdIdxs 已经是高低点交替，我们需要对应的类型
    easy_xfenTypes = []
    if len(xdIdxs_easy) > 0:
        # 第一个点的类型由 xdType_easy 决定（或者根据价格比较）
        curr_type = xdType_easy
        for _ in xdIdxs_easy:
            easy_xfenTypes.append(curr_type)
            curr_type = -curr_type
    
    # 标准缠论线段 (保留备用)
    xdIdxs_strict, xfenTypes_strict = parse2ChanXD(frsBiType, biIdx, chanK)
    
    # 5. 中枢 (NEW)
    zs_list = parse2ChanZS(biIdx, chanK)
    
    results = {
        'biIdx': biIdx,
        'frsBiType': frsBiType,
        'xdIdxs': xdIdxs_strict, # 切回逐笔迭代的线段逻辑，解决前面一段“没合成线段”的问题
        'xfenTypes': xfenTypes_strict,
        'xdIdxs_easy': xdIdxs_easy, 
        'xfenTypes_easy': easy_xfenTypes,
        'fenIdx': fenIdx,
        'fenTypes': fenTypes,
        'zs_list': zs_list
    }
    return chanK, results

class ChanAnalyzer:
    """
    封装缠论分析逻辑的类
    """
    def __init__(self, least_khl_num=3, chanK_flag=True):
        self.least_khl_num = least_khl_num
        self.chanK_flag = chanK_flag

    def analyze(self, k_data):
        return get_chan_analysis(k_data, self.least_khl_num, self.chanK_flag)
