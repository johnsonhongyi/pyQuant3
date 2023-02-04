#!/usr/bin/python
# -*- encoding: utf8 -*-


import io
import datetime
import getopt
import glob
import os
import sys
import re
import string
import zipfile
from struct import *

# from readths2 import *
# 2010-09-02 by wanghp


# basedir = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq/T0002'
basedir = r'D:\MacTools\WinTools\new_tdx'
# D:\MacTools\WinTools\new_tdx\vipdoc\sh\lday
# exp_dir = basedir + r'\T0002\export'
exp_dir = basedir + r'\T0002\export'
# blocknew = 'Z:\Documents\Johnson\WinTools\zd_pazq\T0002\blocknew'
blocknew = 'D:\MacTools\WinTools\new_tdx\T0002\blocknew'
# exp_dir    = basedir + r'\T0002\export_back'
lc5_dir_sh = basedir + r'\Vipdoc\sh\fzline'
# lc5_dir_sh =  r'D:\2965\ydzqwsjy\Vipdoc\sh\fzline'
lc5_dir_sz = basedir + r'\Vipdoc\sz\fzline'
day_dir_sh = basedir + r'\Vipdoc\sh\lday'
day_dir_sz = basedir + r'\Vipdoc\sz\lday'

stkdict = {}  # ´æ´¢¹ÉÆ±IDºÍÉÏº£ÊÐ¡¢ÉîÛÚÊÐµÄ¶ÔÕÕ


#############################################################
# read Í¨´ïÐÅ·Ö±ÊÊý¾Ý
# example readfbtxt(readlines(),'20100831-600000.TXT')
# ·µ»ØµÄdata¸ñÊ½Îª
# (stkid,datetime,price,amount,vol(¹ÉÊý),±ÊÊý,buy or sale) µÄlist
#############################################################
def readfbtxt(p_lines, p_name):
    """¶ÁÍ¨´ïÐÅ·Ö±ÊÊý¾Ý """
    data = []
    shortname = os.path.split(p_name)[1]
    shortname = os.path.splitext(shortname)[0]
    sDay, stkID = shortname.split('-')
    if len(sDay) != 8:
        return data
    stky = int(sDay[0:4])
    stkm = int(sDay[4:6])
    stkd = int(sDay[6:8])
    line_no = 0

    for l in p_lines:
        line_no += 1
        if line_no <= 3:
            continue
        l = l.strip()
        t = re.split('\s+', l)
        k = datetime.datetime(stky, stkm, stkd, int(t[0][0:2]), int(t[0][3:5]))
        p = float(t[1])  # price
        vol = int(t[2]) * 100  # ¹ÉÊý
        amt = p * vol  # ³É½»Á¿
        bscnt = 0  # ±ÊÊý
        bstag = ''  # buy or sale
        try:
            bscnt = int(t[3])  # ±ÊÊý
            bstag = t[4]  # buy or sale
        except IndexError as e:
            pass
        data.append((stkID, k, p, amt, vol, bscnt, bstag))
    return data


#############################################################
# ½«·Ö±ÊÊý¾Ý×ª»¯Îª·Ö±ÊÊý¾Ý
# p_data:´«Èë²ÎÊý ÎªreadfbtxtËù·µ»Ø
# data:  ·µ»ØµÄÊý¾Ý¸ñÊ½Îª
# [stkid,datetime,open,high,low,close,amt,vol(¹É)]
#############################################################
def fbtxt2lc0(p_data):
    """·Ö±ÊÊý¾Ý×ª»¯Îª1·ÖÖÓÊý¾Ý"""
    data = []
    for i in p_data:
        t = i[1]  # datetime
        p = i[2]  # price
        data.append([i[0], t, p, p, p, p, i[3], i[4]])
    return data


#############################################################
# ½«·Ö±ÊÊý¾Ý×ª»¯Îª1·ÖÖÓÊý¾Ý
# p_data:´«Èë²ÎÊý ÎªreadfbtxtËù·µ»Ø
# data:  ·µ»ØµÄÊý¾Ý¸ñÊ½Îª
# [stkid,datetime,open,high,low,close,amt,vol(¹É)]
#############################################################
def fbtxt2lc1(p_data):
    """·Ö±ÊÊý¾Ý×ª»¯Îª1·ÖÖÓÊý¾Ý"""
    data = []
    for i in p_data:
        t = i[1]  # datetime
        p = i[2]  # price
        lend = len(data)
        j = lend - 1
        while j >= 0:
            if data[j][1] == t:
                break
            j -= 1
        if j < 0:  # Ã»ÓÐÕÒµ½¸ÃÊ±¼ä
            data.append([i[0], t, p, p, p, p, i[3], i[4]])
        else:  # ÕÒµ½¸ÃÊ±¼ä
            if p > data[j][3]:  # high
                data[j][3] = p
            if p < data[j][4]:  # low
                data[j][4] = p
            data[j][5] = p  # close
            data[j][6] += i[3]  # amout
            data[j][7] += i[4]  # vol
    # data.sort(key = lambda x:x[1])  #ÒÔdatetime ÅÅÐò
    return data


#############################################################
# Ò»¸öÊ±¼ä¶ÔÓ¦µÄ5·ÖÖÓÇø¼ä¶Î
# dt ´«Èë²ÎÊý ÎªÒ»¸ödatetime.datetime or datetime.time
# ·µ»Ødatetime »òtime
#############################################################
def which5min(dt):
    """5 ·ÖÖÓÊ±¼ä»®·Ö """
    if type(dt) != datetime.datetime and type(dt) != datetime.time:
        return None
    t = dt
    ret = None
    if type(dt) == datetime.datetime:
        t = datetime.time(dt.hour, dt.minute, dt.second)

    if t < datetime.time(9, 30):
        return None
    if t < datetime.time(9, 35):
        ret = datetime.time(9, 35)
    elif t < datetime.time(9, 40):
        ret = datetime.time(9, 40)
    elif t < datetime.time(9, 45):
        ret = datetime.time(9, 45)
    elif t < datetime.time(9, 50):
        ret = datetime.time(9, 50)
    elif t < datetime.time(9, 55):
        ret = datetime.time(9, 55)
    elif t < datetime.time(10, 0):
        ret = datetime.time(10, 0)
    elif t < datetime.time(10, 5):
        ret = datetime.time(10, 5)
    elif t < datetime.time(10, 10):
        ret = datetime.time(10, 10)
    elif t < datetime.time(10, 15):
        ret = datetime.time(10, 15)
    elif t < datetime.time(10, 20):
        ret = datetime.time(10, 20)
    elif t < datetime.time(10, 25):
        ret = datetime.time(10, 25)
    elif t < datetime.time(10, 30):
        ret = datetime.time(10, 30)
    elif t < datetime.time(10, 35):
        ret = datetime.time(10, 35)
    elif t < datetime.time(10, 40):
        ret = datetime.time(10, 40)
    elif t < datetime.time(10, 45):
        ret = datetime.time(10, 45)
    elif t < datetime.time(10, 50):
        ret = datetime.time(10, 50)
    elif t < datetime.time(10, 55):
        ret = datetime.time(10, 55)
    elif t < datetime.time(11, 0):
        ret = datetime.time(11, 0)
    elif t < datetime.time(11, 5):
        ret = datetime.time(11, 5)
    elif t < datetime.time(11, 10):
        ret = datetime.time(11, 10)
    elif t < datetime.time(11, 15):
        ret = datetime.time(11, 15)
    elif t < datetime.time(11, 20):
        ret = datetime.time(11, 20)
    elif t < datetime.time(11, 25):
        ret = datetime.time(11, 25)
    elif t <= datetime.time(11, 30):
        ret = datetime.time(11, 30)
    # elif t < datetime.time(13,0): ret = datetime.time(13,0)
    elif t < datetime.time(13, 5):
        ret = datetime.time(13, 5)
    elif t < datetime.time(13, 10):
        ret = datetime.time(13, 10)
    elif t < datetime.time(13, 15):
        ret = datetime.time(13, 15)
    elif t < datetime.time(13, 20):
        ret = datetime.time(13, 20)
    elif t < datetime.time(13, 25):
        ret = datetime.time(13, 25)
    elif t < datetime.time(13, 30):
        ret = datetime.time(13, 30)
    elif t < datetime.time(13, 35):
        ret = datetime.time(13, 35)
    elif t < datetime.time(13, 40):
        ret = datetime.time(13, 40)
    elif t < datetime.time(13, 45):
        ret = datetime.time(13, 45)
    elif t < datetime.time(13, 50):
        ret = datetime.time(13, 50)
    elif t < datetime.time(13, 55):
        ret = datetime.time(13, 55)
    elif t < datetime.time(14, 0):
        ret = datetime.time(14, 0)
    elif t < datetime.time(14, 5):
        ret = datetime.time(14, 5)
    elif t < datetime.time(14, 10):
        ret = datetime.time(14, 10)
    elif t < datetime.time(14, 15):
        ret = datetime.time(14, 15)
    elif t < datetime.time(14, 20):
        ret = datetime.time(14, 20)
    elif t < datetime.time(14, 25):
        ret = datetime.time(14, 25)
    elif t < datetime.time(14, 30):
        ret = datetime.time(14, 30)
    elif t < datetime.time(14, 35):
        ret = datetime.time(14, 35)
    elif t < datetime.time(14, 40):
        ret = datetime.time(14, 40)
    elif t < datetime.time(14, 45):
        ret = datetime.time(14, 45)
    elif t < datetime.time(14, 50):
        ret = datetime.time(14, 50)
    elif t < datetime.time(14, 55):
        ret = datetime.time(14, 55)
    elif t <= datetime.time(15, 0):
        ret = datetime.time(15, 0)
    else:
        return None
    if type(dt) == datetime.datetime:
        return datetime.datetime(dt.year, dt.month, dt.day, ret.hour, ret.minute, ret.second)
    else:
        return ret


#############################################################
# ½«1·ÖÖÓÊý¾Ý×ªÎª5·ÖÖÓÊý¾Ý
# p_data:´«Èë²ÎÊý Îªfbtxt2lc1Ëù·µ»Ø
# data:  ·µ»ØµÄÊý¾Ý¸ñÊ½Îª
# [stkid,datetime,open,high,low,close,amt,vol(¹É)]
#############################################################
def lc1tolc5(p_data):
    """1·ÖÖÓÊý¾Ý×ª»¯Îª5·ÖÖÓÊý¾Ý """
    if len(p_data) <= 0:
        return None
    data = []
    for i in p_data:
        t = which5min(i[1])  # ÕÒ¶ÔÓ¦5·ÖÖÓµÄÇø¶Î
        if t == None:
            raise ValueError('time out of range: %s' % i[1])
        lend = len(data)
        j = lend - 1
        while j >= 0:
            if data[j][1] == t:
                break
            j -= 1
        if j < 0:  # Ã»ÓÐÕÒµ½¸ÃÊ±¼ä
            data.append([i[0], t, i[2], i[3], i[4], i[5], i[6], i[7]])
        else:  # ÕÒµ½¸ÃÊ±¼ä
            if i[3] > data[j][3]:  # high
                data[j][3] = i[3]
            if i[4] < data[j][4]:  # low
                data[j][4] = i[4]
            data[j][5] = i[5]  # close
            data[j][6] += i[6]  # amout
            data[j][7] += i[7]  # vol
    # data.sort(key = lambda x:x[1])  #ÒÔdatetime ÅÅÐò
    return data


#############################################################
# read 5·ÖÖÓÊý¾Ý
# example readlc5(r'E:\new_gxzq_v6\Vipdoc\sh\fzline\sh600000.lc5')
#############################################################
def readlc5(p_name):
    """tdx 5min Êý¾Ý
       ÈÕÆÚÉÏµÍ16Î»±íÊ¾ÔÂÈÕ£¬¸ß16Î»±íÊ¾·ÖÖÓ
       Õâ¸ö½á¹¹¸öÈË¸Ð¾õ¾Í²»ÈçÍ¬»¨Ë³×öµÄÇÉÃî
           ÔÚÒ»¸ö4×Ö½ÚÖÐ°Ñ Äê ÔÂ ÈÕ Ê± ·Ö ¶¼¼ÇÂ¼ÏÂÀ´ÁË
    """
    f = open(p_name, 'rb')
    stkID = os.path.split(p_name)[1]
    stkID = os.path.splitext(stkID)[0]
    if string.lower(stkID[0:2]) == 'sh' or string.lower(stkID[0:2]) == 'sz':
        stkID = stkID[2:]
    icnt = 0
    data = []
    while 1:
        raw = f.read(4 * 8)
        if len(raw) <= 0:
            break
        t = unpack('IfffffII', raw)
        mins = (t[0] >> 16) & 0xffff
        mds = t[0] & 0xffff
        month = int(mds / 100)
        day = mds % 100
        hour = int(mins / 60)
        minute = mins % 60
        # datet = "d-d d:d" % (month,day,hour,minute)
        data.append((stkID, (month, day, hour, minute), t[
                    1], t[2], t[3], t[4], t[5], t[6], t[7]))
        # print datet,t[1],t[2],t[3],t[4],t[5],t[6],t[7]
        icnt += 1
    # end while
    f.close()
    return data


#############################################################
# ¹¹ÔìÍ¨´ïÐÅ5minÊý¾ÝÎÄ¼þ
# data ½á¹¹
# [stkID,(ÔÂ,ÈÕ,Ê±,·Ö),open,high,low,close,amt,vol,0]
#############################################################
def writelc5(p_name, data, addwrite=True):
    if addwrite:
        fout = open(p_name, 'ab')
    else:
        fout = open(p_name, 'wb')
    for i in data:
        t = i[1][0] * 100 + i[1][1] + ((i[1][2] * 60 + i[1][3]) << 16)
        raw = pack('IfffffII', t, i[2], i[3], i[4], i[5], i[6], i[7], i[8])
        fout.write(raw)
    # end for
    fout.close()


#############################################################
# outlist
# ½«list »òÕß tuple Êä³ö
# µÝ¹é´¹Ö±Êä³ö£¬¸ñÊ½²»ºÃ
#############################################################
def outlist(l):
    if type(l) != list and type(l) != tuple:
        print(l)
    else:
        for i in l:
            outlist(i)


#############################################################
# outlist2 ¶þ²ãÊä³ö£¬¶ÔÓÚÉÏÎÄÖÐµÄdata ÊµÓÃ
# ´«Èë²ÎÊý data£¬Ò»¸öÐÎÈç¾ØÕóµÄlist
#############################################################
def outlist2(p_data):
    for i in p_data:
        for j in i:
            print(j, end=' ')
        print()


#############################################################
# ÕýÊýÓë¶þ½øÖÆ±íÊ¾»¥Ïà±íÊ¾
#
#############################################################
# ------------------------------
# -- i2bin ÕûÊý×ªÎª 2½øÖÆ×Ö·û´®
# ------------------------------
def i2bin(x):
    result = ''
    x = int(x)
    while x > 0:
        mod = x & 0x01  # È¡2µÄÓàÊý
        x = x >> 0x01  # ÓÒÒÆÒ»Î»
        result = str(mod) + result
    return result


# ------------------------------
# -- bin2i 2½øÖÆ×Ö·û´® ×ªÎªÕýÊý
# ------------------------------
def bin2i(bin):
    result = 0
    for s in bin:
        if s != '0' and s != '1':
            raise ValueError('bad bin string:' + bin)
        result = 2 * result + int(s)
    return result


#############################################################
# fill_stkdict Ìî³äÈ«¾Ö±äÁ¿×Öµä stkdict
#
#############################################################
def fill_stkdict():
    global stkdict
    lsh = os.listdir(day_dir_sh)
    for l in lsh:
        if len(l) <= 4:
            continue
        l = l.lower()
        if l[-3:] != 'day':
            continue
        n = os.path.splitext(l)[0]
        if n[0:2] == 'sh' or n[0:2] == 'sz':
            n = n[2:]
        stkdict[n] = 'sh'
    lsz = os.listdir(day_dir_sz)
    for l in lsz:
        if len(l) <= 4:
            continue
        l = l.lower()
        if l[-3:] != 'day':
            continue
        n = os.path.splitext(l)[0]
        if n[0:2] == 'sh' or n[0:2] == 'sz':
            n = n[2:]
        stkdict[n] = 'sz'


def getMarketByID(id):
    global stkdict
    if len(stkdict) == 0:
        fill_stkdict()
    return stkdict.setdefault(id, '')


# copy file
# dstname = os.path.join(lc5_dir_sh,fout)
# shutil.copy(fout,dstname)


def writelcfiles(p_lines, p_name, lctype='lc5lc1', addfile=True):
    """
Ð´ÄÚÈÝ
p_lines ÎÄ¼þÐÐ
l_name  ¶ÌÎÄ¼þÃû
lctype  Òª×ª»¯Éú³ÉµÄ·ÖÖÓÀàÐÍ lc5 ±íÊ¾5·ÖÖÓ lc1 ±íÊ¾1·ÖÖÓ lc0±íÊ¾·Ö±ÊµÄ
addfile True±íÊ¾×·¼ÓÎÄ¼þ False ±íÊ¾¸²¸Ç
    """
    data1 = readfbtxt(p_lines, p_name)
    if len(data1) == 0:
        return
    data2 = fbtxt2lc1(data1)
    data3 = lc1tolc5(data2)

    # lc5 5·ÖÖÓÎÄ¼þ
    if 'lc5' in lctype:
        data = []
        for i in data3:
            data.append([i[0], (i[1].month, i[1].day, i[1].hour, i[1].minute), i[
                        2], i[3], i[4], i[5], i[6], i[7], 0])
        if len(data) == 0:
            sys.stderr.write('Error:no data in data\n')
            sys.exit(1)
        stkID = data[0][0]
        mark = getMarketByID(stkID)
        if mark == '':
            sys.stderr.write('²»ÄÜÈ·¶¨ËüµÄÊÐ³¡£º%s.Çë¼ì²é´úÂë!\n' % stkID)
        else:
            fout = mark + stkID + '.lc5'
            if mark == 'sh':
                fout = os.path.join(lc5_dir_sh, fout)
            else:
                fout = os.path.join(lc5_dir_sz, fout)

            writelc5(fout, data, addfile)
            # endif
    # endif
    if 'lc1' in lctype:
        data = []
        for i in data2:
            data.append([i[0], (i[1].month, i[1].day, i[1].hour, i[1].minute), i[
                        2], i[3], i[4], i[5], i[6], i[7], 0])
        if len(data) == 0:
            sys.stderr.write('Error:no data in data\n')
            sys.exit(1)
        stkID = data[0][0]
        mark = getMarketByID(stkID)
        if mark == '':
            sys.stderr.write('²»ÄÜÈ·¶¨ËüµÄÊÐ³¡£º%s.Çë¼ì²é´úÂë!\n' % stkID)
        else:
            fout = mark + stkID + '.lc1'
            if mark == 'sh':
                fout = os.path.join(lc5_dir_sh, fout)
            else:
                fout = os.path.join(lc5_dir_sz, fout)

            writelc5(fout, data, addfile)
            # endif.
    # endif.

    # lc0 ·Ö±ÊµÄKÏßÎÄ¼þ
    if 'lc0' in lctype:
        data0 = fbtxt2lc0(data1)
        data = []
        for i in data0:
            data.append([i[0], (i[1].month, i[1].day, i[1].hour, i[1].minute), i[
                        2], i[3], i[4], i[5], i[6], i[7], 0])
        if len(data) == 0:
            sys.stderr.write('Error:no data in data\n')
            sys.exit(1)
        stkID = data[0][0]
        mark = getMarketByID(stkID)
        if mark == '':
            sys.stderr.write('²»ÄÜÈ·¶¨ËüµÄÊÐ³¡£º%s.Çë¼ì²é´úÂë!\n' % stkID)
        else:
            fout = mark + stkID + '.lc0'
            if mark == 'sh':
                fout = os.path.join(lc5_dir_sh, fout)
            else:
                fout = os.path.join(lc5_dir_sz, fout)

            writelc5(fout, data, addfile)
            # endif.
            # endif.


def convert(p_stkid, p_type='txt', filterfunc=None):
    
    if p_type == 'txt':  # txt file

        txtfiles = glob.glob(os.path.join(exp_dir, '*-' + p_stkid + '.txt'))
        if filterfunc:
            txtfiles = list(filter(filterfunc, txtfiles))
        txtfiles.sort()
        l_i = 0
        import ipdb;ipdb.set_trace()

        for fname in txtfiles:
            sys.stderr.write('%s\n' % fname)
            try:
                doc_lines = file(fname).readlines()
            except IOError as e:
                sys.stderr.write("Open file %s fail!\n" % fname)
                continue
            if len(doc_lines) <= 4:
                sys.stderr.write('No data in %s\n' % fname)
                continue
            if l_i == 0:
                writelcfiles(doc_lines, fname, 'lc5lc1', False)  # over write
            else:
                writelcfiles(doc_lines, fname, 'lc5lc1', True)  # add write
            l_i += 1
            # endfor

    else:  # zipfile
        try:
            fzip = zipfile.ZipFile(os.path.join(exp_dir, p_stkid + '.zip'))
        except IOError as e:
            print('Can not open file!', e)
            return
        zipedfiles = fzip.namelist()
        if len(zipedfiles) == 0:
            return
        if filterfunc:
            zipedfiles = list(filter(filterfunc, zipedfiles))
        zipedfiles.sort()
        l_i = 0
        for fname in zipedfiles:
            sys.stderr.write('%s\n' % fname)
            doc = fzip.read(fname)
            doc_lines = io.StringIO(doc).readlines()
            if l_i == 0:
                writelcfiles(doc_lines, fname, 'lc5lc1', False)  # over write
            else:
                writelcfiles(doc_lines, fname, 'lc5lc1', True)  # add write
            l_i += 1
            # endfor
            # endif.


#############################################################
# usage Ê¹ÓÃËµÃ÷
#
#############################################################

def usage(p):
    print("""
python %s [-t txt|zip] stkid [from] [to]
-t txt zip file 
for example :
python %s 999999 20230101 20230302
python %s -t txt 999999 20230101 20230202
    """ % (p, p, p))


if __name__ == '__main__':
    """
    python readtdxlc5.py 999999 20230101 20230131
    """
    argv = sys.argv[1:]
    try:
        opts, args = getopt.getopt(argv, "ht:", ["help", "type="])
    except getopt.GetoptError:
        usage(sys.argv[0])
        sys.exit(0)
    l_type = 'zip'  # default type is zipfiles!
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit(1)
        elif opt in ("-t", "--type"):
            l_type = arg
    if len(args) < 1:
        print('You must specified the stock No.!')
        usage(sys.argv[0])
        sys.exit(1)

    stkid = args[0]
    l_from = None
    l_to = None
    try:
        l_from = args[1]
        l_to = args[2]
    except:
        pass

    # ¹ýÂËº¯Êý
    def filfunc(x):
        if l_from == None and l_to == None:
            return True
        ymd = os.path.splitext(os.path.split(x)[1])[0].split('-')[0]
        if l_from and l_to:
            return ymd >= l_from and ymd <= l_to
        elif l_from:
            return ymd >= l_from
        else:
            return ymd <= l_to

    if l_type == 'txt':  # ´ÓÒ»°ãtxt ÎÄ¼þ
        convert(stkid, 'txt', filfunc)
    else:
        convert(stkid, 'zip', filfunc)

    mark = getMarketByID(stkid)
    if mark == '':
        sys.stderr.write('²»ÄÜÈ·¶¨ËüµÄÊÐ³¡£º%s.Çë¼ì²é´úÂë!\n' % stkid)
    else:
        os.system(
            'copy E:\\cwork\\guosen\\Vipdoc\\' + mark + '\\fzline\\' + mark + stkid + '.lc5 E:\\cwork\\my_yd\\Vipdoc\\' + mark + '\\fzline\\')
        os.system(
            'copy E:\\cwork\\guosen\\Vipdoc\\' + mark + '\\fzline\\' + mark + stkid + '.lc1 E:\\cwork\\ydzqwsjy\\Vipdoc\\' + mark + '\\fzline\\' + mark + stkid + '.lc5')

        # data = readlc5(os.path.join(lc5_dir_sh,'sh601398.lc5'))
        # outlist2(data)
