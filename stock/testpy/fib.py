# -*- coding: utf-8 -*-
"""
A simple fibonacci program
"""
import argparse
parser = argparse.ArgumentParser(description='I print fibonacci sequence')
parser.add_argument('-s', '--start', type=int, dest='start',
                    help='Start of the sequence', required=True)
parser.add_argument('-e', '--end', type=int, dest='end',
                    help='End of the sequence', required=True)
parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
                    help='Enable debug info')
# from ConfigParser import ConfigParser
#
# import shlex
# config = ConfigParser()
#
# config.read('argparse_with_shlex.ini')
#
# config_value = config.get('cli', 'options')
#
# print 'Config  :',config_value
#
#
#
# argument_list = shlex.split(config_value)
#
# print 'Arg List:', argument_list
#
#
#
# print 'Results :', parser.parse_args(argument_list)
#
#     执行结果：
#
# # python argparse_with_shlex.py
#
# Config  : -a -b 2
#
# Arg List: ['-a', '-b', '2']
#
# Results : Namespace(a=True, b='2', c=None)
#
#     其中ini文件的内容如下：
#
# # vi argparse_with_shlex.ini
#
# [cli]
#
# options = -a -b 2
#
#     上面例子使用了ConfigParser来读取配置，再用shlex来切割参数。可以通过fromfile_prefix_chars 告知argparse输入参数为文件。



import logging
logger = logging.getLogger('fib')
logger.setLevel(logging.DEBUG)
hdr = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(name)s:%(levelname)s: %(message)s')
hdr.setFormatter(formatter)
logger.addHandler(hdr)

def infinite_fib():
    a, b = 0, 1
    yield a
    yield b
    while True:
        logger.debug('Before caculation: a, b = %s, %s' % (a, b))
        a, b = b, a + b
        logger.debug('After caculation: a, b = %s, %s' % (a, b))
        yield b

def fib(start, end):
    for cur in infinite_fib():
        logger.debug('cur: %s, start: %s, end: %s' % (cur, start, end))
        if cur > end:
            return
        if cur >= start:
            logger.debug('Returning result %s' % cur)
            yield cur
def main():
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.ERROR)
    for n in fib(args.start, args.end):
        print(n, end=' ')
if __name__ == '__main__':
    # main()
    end = True
    while end:
        cmd=(input('DEBUG[top_dif,top_dd,end]:'))
        if cmd =='e' or cmd=='q':
            break
        else:
            print(eval(cmd))
    # import requests
    # data=requests.get('http://hq.sinajs.cn/?format=text&list=sz000001,sz000002,sz000004,sz000005,sz000006,sz000007,sz000008,sz000009,sz000010,sz000011,sz000012,sz000014,sz000016,sz000017,sz000018,sz000018,sz000019,sz000020,sz000021,sz000022,sz000023,sz000024,sz000025,sz000026,sz000027,sz000028,sz000029,sz000030,sz000031,sz000032,sz000034,sz000035,sz000036,sz000037,sz000038,sz000039,sz000040,sz000042,sz000043,sz000045,sz000046,sz000048,sz000049,sz000050,sz000055,sz000056,sz000058,sz000059,sz000060,sz000061,sz000062,sz000063,sz000065,sz000066,sz000068,sz000069,sz000070,sz000078,sz000088,sz000089,sz000090,sz000096,sz000099,sz000100,sz000150,sz000151,sz000153,sz000155,sz000156,sz000157,sz000158,sz000159,sz000166,sz000301,sz000333,sz000338,sz000400,sz000401,sz000402,sz000403,sz000404,sz000407,sz000408,sz000409,sz000410,sz000411,sz000413,sz000415,sz000416,sz000417,sz000418,sz000419,sz000420,sz000421,sz000422,sz000423,sz000425,sz000426,sz000428,sz000429,sz000430,sz000488,sz000498,sz000501,sz000502,sz000503,sz000504,sz000505,sz000506,sz000507,sz000509,sz000510,sz000511,sz000513,sz000514,sz000516,sz000517,sz000518,sz000519,sz000520,sz000521,sz000523,sz000524,sz000525,sz000526,sz000528,sz000529,sz000530,sz000531,sz000532,sz000533,sz000534,sz000536,sz000537,sz000538,sz000539,sz000540,sz000541,sz000543,sz000544,sz000545,sz000546,sz000547,sz000548,sz000550,sz000551,sz000552,sz000553,sz000554,sz000555,sz000557,sz000558,sz000559,sz000560,sz000561,sz000563,sz000564,sz000565,sz000566,sz000567,sz000568,sz000570,sz000571,sz000572,sz000573,sz000576,sz000581,sz000582,sz000584,sz000585,sz000586,sz000587,sz000589,sz000590,sz000591,sz000592,sz000593,sz000595,sz000596,sz000597,sz000598,sz000599,sz000600,sz000601,sz000603,sz000605,sz000606,sz000607,sz000608,sz000609,sz000610,sz000611,sz000612,sz000613,sz000615,sz000616,sz000617,sz000619,sz000620,sz000622,sz000623,sz000625,sz000626,sz000627,sz000628,sz000629,sz000630,sz000631,sz000632,sz000633,sz000635,sz000636,sz000637,sz000638,sz000639,sz000650,sz000651,sz000652,sz000655,sz000656,sz000657,sz000659,sz000661,sz000662,sz000663,sz000665,sz000666,sz000667,sz000668,sz000669,sz000670,sz000671,sz000672,sz000673,sz000676,sz000677,sz000678,sz000679,sz000680,sz000681,sz000682,sz000683,sz000685,sz000686,sz000687,sz000688,sz000690,sz000691,sz000692,sz000693,sz000695,sz000697,sz000698,sz000700,sz000701,sz000702,sz000703,sz000705,sz000707,sz000708,sz000709,sz000710,sz000711,sz000712,sz000713,sz000715,sz000716,sz000717,sz000718,sz000719,sz000720,sz000721,sz000722,sz000723,sz000725,sz000726,sz000727,sz000728,sz000729,sz000731,sz000732,sz000733,sz000735,sz000736,sz000737,sz000738,sz000739,sz000748,sz000750,sz000751,sz000752,sz000753,sz000755,sz000756,sz000757,sz000758,sz000759,sz000760,sz000761,sz000762,sz000766,sz000767,sz000768,sz000776,sz000777,sz000778,sz000779,sz000780,sz000782,sz000783,sz000785,sz000786,sz000788,sz000789,sz000790,sz000791,sz000792,sz000793,sz000795,sz000796,sz000797,sz000798,sz000799,sz000800,sz000801,sz000802,sz000803,sz000806,sz000807,sz000809,sz000810,sz000811,sz000812,sz000813,sz000815,sz000816,sz000818,sz000819,sz000820,sz000821,sz000822,sz000823,sz000825,sz000826,sz000828,sz000829,sz000830,sz000831,sz000833,sz000835,sz000836,sz000837,sz000838,sz000839,sz000848,sz000850,sz000851,sz000852,sz000856,sz000858,sz000859,sz000860,sz000861,sz000862,sz000863,sz000868,sz000869,sz000875,sz000876,sz000877,sz000878,sz000880,sz000881,sz000882,sz000883,sz000885,sz000886,sz000887,sz000888,sz000889,sz000890,sz000892,sz000893,sz000895,sz000897,sz000898,sz000899,sz000900,sz000901,sz000902,sz000903,sz000905,sz000906,sz000908,sz000909,sz000910,sz000911,sz000912,sz000913,sz000915,sz000916,sz000917,sz000918,sz000919,sz000920,sz000921,sz000922,sz000923,sz000925,sz000926,sz000927,sz000928,sz000929,sz000930,sz000931,sz000932,sz000933,sz000935,sz000936,sz000937,sz000938,sz000939,sz000948,sz000949,sz000950,sz000951,sz000952,sz000953,sz000955,sz000957,sz000958,sz000959,sz000960,sz000961,sz000962,sz000963,sz000965,sz000966,sz000967,sz000968,sz000969,sz000970,sz000971,sz000972,sz000973,sz000975,sz000976,sz000977,sz000978,sz000979,sz000980,sz000981,sz000982,sz000983,sz000985,sz000987,sz000988,sz000989,sz000990,sz000993,sz000995,sz000996,sz000997,sz000998,sz000999,sz001696,sz001896,sz002001,sz002002,sz002003,sz002004,sz002005,sz002006,sz002007,sz002008,sz002009,sz002010,sz002011,sz002012,sz002013,sz002014,sz002015,sz002016,sz002017,sz002018,sz002019,sz002020,sz002021,sz002022,sz002023,sz002024,sz002025,sz002026,sz002027,sz002028,sz002029,sz002030,sz002031,sz002032,sz002033,sz002034,sz002035,sz002036,sz002037,sz002038,sz002039,sz002040,sz002041,sz002042,sz002043,sz002044,sz002045,sz002046,sz002047,sz002048,sz002049,sz002050,sz002051,sz002052,sz002053,sz002054,sz002055,sz002056,sz002057,sz002058,sz002059,sz002060,sz002061,sz002062,sz002063,sz002064,sz002065,sz002066,sz002067,sz002068,sz002069,sz002070,sz002071,sz002072,sz002073,sz002074,sz002075,sz002076,sz002077,sz002078,sz002079,sz002080,sz002081,sz002082,sz002083,sz002084,sz002085,sz002086,sz002087,sz002088,sz002089,sz002090,sz002091,sz002092,sz002093,sz002094,sz002095,sz002096,sz002097,sz002098,sz002099,sz002100,sz002101,sz002102,sz002103,sz002104,sz002105,sz002106,sz002107,sz002108,sz002109,sz002110,sz002111,sz002112,sz002113,sz002114,sz002115,sz002116,sz002117,sz002118,sz002119,sz002120,sz002121,sz002122,sz002123,sz002124,sz002125,sz002126,sz002127,sz002128,sz002129,sz002130,sz002131,sz002132,sz002133,sz002134,sz002135,sz002136,sz002137,sz002137,sz002138,sz002139,sz002140,sz002141,sz002142,sz002143,sz002144,sz002145,sz002146,sz002147,sz002148,sz002149,sz002150,sz002151,sz002152,sz002153,sz002154,sz002155,sz002156,sz002157,sz002158,sz002159,sz002160,sz002161,sz002162,sz002163,sz002164,sz002165,sz002166,sz002167,sz002168,sz002169,sz002170,sz002171,sz002172,sz002173,sz002174,sz002175,sz002176,sz002177,sz002178,sz002179,sz002180,sz002181,sz002182,sz002183,sz002184,sz002185,sz002186,sz002187,sz002188,sz002189,sz002190,sz002191,sz002192,sz002193,sz002194,sz002195,sz002196,sz002197,sz002198,sz002199,sz002200,sz002201,sz002202,sz002203,sz002204,sz002205,sz002206,sz002207,sz002208,sz002209,sz002210,sz002211,sz002212,sz002213,sz002214,sz002215,sz002216,sz002217,sz002218,sz002219,sz002220,sz002221,sz002222,sz002223,sz002224,sz002225,sz002226,sz002227,sz002228,sz002229,sz002230,sz002231,sz002232,sz002233,sz002234,sz002235,sz002236,sz002237,sz002238,sz002239,sz002240,sz002241,sz002242,sz002243,sz002244,sz002245,sz002246,sz002247,sz002248,sz002249,sz002250,sz002251,sz002252,sz002253,sz002254,sz002255,sz002256,sz002258,sz002259,sz002260,sz002261,sz002262,sz002263,sz002264,sz002265,sz002266,sz002267,sz002268,sz002269,sz002270,sz002271,sz002272,sz002273,sz002274,sz002275,sz002276,sz002277,sz002278,sz002279,sz002280,sz002281,sz002282,sz002283,sz002284,sz002285,sz002286,sz002287,sz002288,sz002289,sz002290,sz002291,sz002292,sz002293,sz002293,sz002294,sz002295,sz002296,sz002297,sz002298,sz002298,sz002299,sz002300,sz002301,sz002302,sz002303,sz002304,sz002305,sz002306,sz002307,sz002308,sz002309,sz002310,sz002311,sz002312,sz002313,sz002314,sz002315,sz002316,sz002317,sz002318,sz002319,sz002320,sz002321,sz002322,sz002323,sz002324,sz002325,sz002326,sz002327,sz002328,sz002329,sz002330,sz002331,sz002332,sz002333,sz002334,sz002335,sz002336,sz002337,sz002338,sz002339,sz002340,sz002341,sz002342,sz002343,sz002344,sz002345,sz002346,sz002347,sz002348,sz002349,sz002350,sz002351,sz002352,sz002353,sz002354,sz002355,sz002356,sz002357,sz002358,sz002359,sz002360,sz002361,sz002362,sz002363,sz002364,sz002365,sz002366,sz002367,sz002368,sz002369,sz002370,sz002371,sz002372,sz002373,sz002374,sz002375,sz002376,sz002377,sz002378,sz002379,sz002380,sz002381')
    