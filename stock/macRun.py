# -*- coding:utf-8 -*-
# !/usr/bin/env python
import subprocess
import os,time
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory as LoggerFactory


from docopt import docopt
log = LoggerFactory.log
args = docopt(cct.sina_doc, version='SinaMarket')

if args['-d'] == 'debug':
    log_level = LoggerFactory.DEBUG
elif args['-d'] == 'info':
    log_level = LoggerFactory.INFO
else:
    log_level = LoggerFactory.ERROR
log.setLevel(log_level)


script = '''tell application "System Events"
    activate
    display dialog "Hello Cocoa!" with title "Sample Cocoa Dialog" default button 2
end tell
'''
scriptcount = '''tell application "Terminal"
    --activate
    get the count of window
end tell
'''

'''tell application "Terminal" --activate;get the count of window end tell '''

scriptname = '''tell application "Terminal"
    --activate
    %s the name of window %s
end tell
'''
scriptquit = '''tell application "Python Launcher" to quit
'''
script_get_position = '''tell application "Terminal"
    --activate
    %s position of window %s 
end tell
'''
script_set_position = '''tell application "Terminal"
    --activate
    %s position of window %s to {%s}
end tell
'''

exit_terminal = '''osascript -e "tell application "Terminal"" 
    -e "do script "exit()" in tab 1 of front window" 
    -e "end tell" '''


'''
osascript \
    -e "tell application \"Terminal\"" \
    -e "do script \"exit()\" in tab 1 of front window" \
    -e "end tell"
'''

'''
osascript -e
 "tell application "System Events"
        tell process "Terminal"
            keystroke "w" using {command down}
        end tell
    end tell
'''
# positionKey = {'sina_Market-DurationDn.py': '313, 433',
#                'sina_Market-DurationUp.py': '-17, 470',
#                'sina_Market-DurationSH.py': '148, 560',
#                'sina_Monitor-Market-New.py': '-2, 371',
#                'sina_Monitor-Market-LH.py': '440, 293',
#                'sina_Monitor-Market.py': '19, 179',
#                'sina_Monitor-GOLD.py': '43, 80',
#                'sina_Monitor.py': '85, 27',
#                'singleAnalyseUtil.py': '583, 23',
#                'LinePower.py':'767, 527',}
               
# positionKey = {'sina_Market-DurationDn.py': '237, 403',
#                'sina_Market-DurationDnUP.py': '-23, 539',
#                'sina_Market-DurationCXDN': '31, 80',
#                'sina_Market-DurationSH.py': '217, 520',
#                'sina_Monitor-Market-New.py': '-2, 371',
#                'sina_Monitor-Market-LH.py': '341, 263',
#                'sina_Monitor-Market.py': '19, 179',
#                'sina_Monitor-GOLD.py': '-7, 149',
#                'sina_Monitor.py': '69, 22',
#                'singleAnalyseUtil.py': '583, 22',
#                'LinePower.py':'42, 504',}


# positionKeyDnup = {'sina_Market-DurationDn.py': '246, 322',
#                'sina_Market-DurationDnUP.py': '-23, 539',
#                'sina_Market-DurationCXDN': '19, 46',
#                'sina_Market-DurationSH.py': '217, 520',
#                'sina_Market-DurationUP.py': '-15, 112',
#                'sina_Monitor-Market-LH.py': '150, 159',
#                'sina_Monitor-Market.py': '19, 179',
#                'sina_Monitor.py': '83, 22',
#                'singleAnalyseUtil.py': '583, 22',
#                'LinePower.py':'40, 497',}

# positionKey = {'sina_Market-DurationDn.py': '217, 520',
#                'sina_Market-DurationCXDN': '8, 52',
#                'sina_Market-DurationSH.py': '-23, 539',
#                'sina_Market-DurationUP.py': '-19, 111',
#                'sina_Monitor-Market-LH.py': '184, 239',
#                'sina_Monitor-Market.py': '19, 179',
#                'sina_Monitor.py': '39, 22',
#                'singleAnalyseUtil.py': '620, 22',
#                'LinePower.py':'40, 497',}

# os.system("osascript -e '%s'"%(cmd))
rcmd = 'tell application "Terminal" to do script "cd /Users/Johnson/Documents/Quant/pyQuant3/stock;/usr/local/bin/python %s"'
rcmd_bin = 'tell application "Terminal" to do script "cd /Users/Johnson/Documents/Quant/pyQuant3/stock;./%s"'
rcmdnatclip = 'tell application "Terminal" to do script "cd /Users/Johnson/Documents/Quant/share_controller/webTools/natclip/natclip;/usr/local/bin/python %s"'

# rcmd2 = 'tell application "Terminal" to do script "cd /Users/Johnson/Documents/Quant/pyQuant/stock;python2 %s"'

# rproc = ['sina_Monitor.py','instock_Monitor.py' ,'singleAnalyseUtil.py','sina_Market-DurationUP.py','LinePower.py','sina_Market-DurationDnUP.py']               
rproc = ['sina_Monitor.bin','instock_Monitor.bin' ,'sina_Market-DurationUP.bin','LinePower.bin','sina_Market-DurationDnUP.bin','singleAnalyseUtil.bin']               

# rproc = ['sina_Market-DurationDn.py' ,'singleAnalyseUtil.py','sina_Market-DurationCXDN.py','sina_Monitor.py','sina_Market-DurationUP.py']               
# cmdRun_launch = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;

cmdRun_launch = '''cd /Users/Johnson/Documents/Quant/pyQuant3/stock;
open sina_Market-DurationDn.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open singleAnalyseUtil.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Market-DurationCXDN.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Monitor.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
open sina_Market-DurationUP.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 5;

'''

cmdRun = '''osascript -e '%s';sleep 10;
osascript -e '%s';sleep 10;
osascript -e '%s';sleep 10;
osascript -e '%s';sleep 10;
osascript -e '%s';sleep 10;
osascript -e '%s';sleep 10;
'''%(rcmd_bin%(rproc[0]),rcmd_bin%(rproc[1]),rcmd_bin%(rproc[2]),rcmd_bin%(rproc[3]),rcmd_bin%(rproc[4]),rcmd_bin%(rproc[5]))
# '''%(rcmd%(rproc[0]),rcmd%(rproc[1]),rcmd%(rproc[2]),rcmd%(rproc[3]),rcmd%(rproc[4]),rcmd%(rproc[5]))

cmdRun200 = '''osascript -e '%s';sleep 300;
osascript -e '%s';sleep 35;
osascript -e '%s';sleep 35;
osascript -e '%s';sleep 350;
osascript -e '%s';sleep 15;
osascript -e '%s';sleep 5;
'''%(rcmd_bin%(rproc[0]),rcmd_bin%(rproc[1]),rcmd_bin%(rproc[2]),rcmd_bin%(rproc[3]),rcmd_bin%(rproc[4]),rcmd_bin%(rproc[5]))
# '''%(rcmd%(rproc[0]),rcmd%(rproc[1]),rcmd%(rproc[2]),rcmd%(rproc[3]),rcmd%(rproc[4]),rcmd%(rproc[5]))

# cmdRun200_launch = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;

# cmdRun200_launch = '''cd /Users/Johnson/Documents/Quant/pyQuant3/stock;
# open sina_Market-DurationDn.py;
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 200;
# open singleAnalyseUtil.py;
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationCXDN.py;
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor.py;
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
# open sina_Market-DurationUP.py;
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
# '''

# print cmdRun
# print cmdRun200
# os.system(cmdRun)
# sys.exit(0)


# cmdRun_dnup = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;

# cmdRun_dnup = '''cd /Users/Johnson/Documents/Quant/pyQuant3/stock;
# open sina_Market-DurationDn.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 210;
# open singleAnalyseUtil.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationUP.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor-Market-LH.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationCXDN.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationSH.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open LinePower.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
# open sina_Market-DurationDnUP.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
# '''

# cmdRun_all = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;
cmdRun_all = '''cd /Users/Johnson/Documents/Quant/pyQuant3/stock;
open sina_Market-DurationDn.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open singleAnalyseUtil.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Monitor-Market-LH.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Market-DurationUP.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Market-DurationCXDN.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Market-DurationSH.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Monitor.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
'''


''' Triton samsung
title:sina_Market-DurationDn.py
target rect1:(-12, 661, 1401, 1116) rect2:(-12, 661, 1401, 1116)
title:sina_Monitor-Market-LH.py
target rect1:(577, 453, 1989, 873) rect2:(577, 453, 1989, 873)
title:sina_Monitor-Market.py
title:LinePower.py
title:sina_Monitor.py
target rect1:(69, 368, 1450, 828) rect2:(69, 368, 1450, 828)
title:singleAnalyseUtil.py
target rect1:(1056, 681, 2045, 1093) rect2:(1056, 681, 2045, 1093)
title:sina_Market-DurationCXDN.py
target rect1:(41, 453, 1490, 908) rect2:(41, 453, 1490, 908)
title:sina_Market-DurationUP.py
target rect1:(5, 529, 1360, 984) rect2:(5, 529, 1360, 984)
'''


# cmdRun200_all_old = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;
cmdRun200_all_old = '''cd /Users/Johnson/Documents/Quant/pyQuant3/stock;
open sina_Market-DurationDn.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 200;
open singleAnalyseUtil.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
open sina_Monitor-Market-LH.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 15;
open sina_Market-DurationUP.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
open sina_Market-DurationCXDN.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
open sina_Market-DurationSH.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 45;
open sina_Monitor.py;
sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
'''
# sleep 0.2;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open LinePower.py;


# cmdRun = '''cd /Users/Johnson/Documents/Quant/pyQuant/stock;
# open singleAnalyseUtil.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor-GOLD.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor-Market.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor-Market-New.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Monitor-Market-LH.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationUp.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationDn.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open sina_Market-DurationSH.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 25;
# open LinePower.py;
# sleep 0.1;osascript -e 'tell application "Python Launcher" to quit';sleep 5;
# '''
closeLaunch ='''osascript -e 'tell application "Python Launcher" to quit';sleep 0.1;'''
closeterminalw = '''osascript -e 'tell application "Terminal" to close windows %s' '''
closeterminal_window = '''osascript -e 'tell application "Terminal" to close windows %s saving no' '''
activate_terminal = '''  osascript -e 'tell application "Terminal" to activate (every window whose name contains "%s")' '''
activate_terminal_argc = '''  osascript -e 'tell application "Terminal" to %s (every window whose name contains "%s")' '''


# def varname(varname):
#     return list(dict(varname=varname).keys())[0]

loc = locals()
def get_variable_name(variable):
    for k,v in list(loc.items()):
        if loc[k] is variable:
            return k

def doScript(scriptn):
    proc = subprocess.Popen(['osascript', '-'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    # python2 str ->byte
    # stdout_output = proc.communicate(scriptn[0]   
    stdout_output = proc.communicate(scriptn.encode('utf-8'))[0]
    # print stdout_output, type(proc)
    return stdout_output.decode('utf-8')

def getPosition(cmd=None, position=None,close=False):
    # cmd = cmd.replace('.py','')
    # cmd = cmd.replace('.py','.bin')
    count = doScript(scriptcount)
    if int(count) > 0:
        for n in range(1, int(count)+1):
            title = doScript(scriptname % ('get', str(object=n)))
            # if close:
                # print "close:%s"%(title),
            # if title.lower().find(cmd.lower()) >= 0  or  title.lower().find(cmd.replace('.py','').lower()) >= 0:
            if title.lower().find(cmd.lower()) >= 0 or title.lower().find(cmd.replace('.py','.bin').lower()) >= 0:
                # print "win:%s get_title:%s "%(n,title)
                # print "get:%s"%(n)
                # position = doScript(
                    # script_set_position % ('set', str(n), positionKey[key]))
                # print(f'script_get_position:{script_get_position % ('get', str(n))}')
                position=doScript(script_get_position % ('get', str(n)))
                # position = doScript(scriptposition % ('get', str(n)))
                if close:
                    # print ("close:%s %s"%(n,title))
                    os.system(closeterminalw%(n))
                return cmd,position

# positionKey = cct.terminal_positionKey
# basedir = cct.get_now_basedir()
# import socket
# hostname = socket.gethostname() 

# if basedir.find('vm') >= 0:
#     positionKey = cct.terminal_positionKey_VM
# elif cct.get_os_system() == 'mac':
#     positionKey = cct.terminal_positionKeyMac2021
#     # positionKey = cct.terminal_positionKeyMac
# else:
#     positionKey = cct.terminal_positionKey4K
#     # positionKey = cct.terminal_positionKey1K_triton

# if hostname.find('R900') >=0:
#     positionKey = cct.terminal_positionKey2K_R9000P

# https://pypi.org/project/a-trade-calendar/
# def get_today_trade_date(sep='-'):
#     TODAY = datetime.date.today()
#     fstr = "%Y" + sep + "%m" + sep + "%d"
#     today = TODAY.strftime(fstr)
#     is_trade_date = a_trade_calendar.is_trade_date(today)
#     return(is_trade_date)


positionKey = cct.get_system_postionKey()
print("position:%s"%(positionKey))

def setPosition(cmd=None, position=None):
    if cmd is not None:
        cmd = cmd.replace('.py','.bin')
    count = doScript(scriptcount)
    # print count
    if int(count) > 3:
        doScript(scriptquit)
        for n in range(1, int(count)+1):
            # log.debug("n:%s"%(n))
            title = doScript(scriptname % ('get', str(object=n)))
            log.debug("n:%s title:%s"%(n,title))
            for key in positionKey:
                log.debug("key:%s  n:%s title:%s"%(key,n,title))
                if title.lower().find(key.lower()) >= 0 or title.lower().find(key.replace('.py','.bin').lower()) >=0:
                # if title.lower().find(key.lower()) >= 0 :
                    print(f"find:{title} key:{key} position:{positionKey[key]}")
                    # print(f'script_set_position:{script_set_position % ("set", str(n), positionKey[key])}')
                    position = doScript(script_set_position %("set", str(n), positionKey[key]))
                    # print doScript(script_get_position % ('get', str(n)))
            # position = doScript(scriptposition % ('get', str(n)))
            # print positio
    else:

        #pd auto to win clip
        # cmd_natclip='''osascript -e '%s';sleep 10;'''%(rcmdnatclip%('main.py'))
        # print('new run natclip')
        # os.system(f'{cmd_natclip}')
        # osascript -e 'tell application "Terminal" to do script "cd /Users/Johnson/Documents/Quant/pyQuant3/stock;/usr/local/bin/python sina_Market-DurationDnUP.py"';
        # osascript -e 
        if os.path.exists(cct.get_ramdisk_path('tdx_last_df')): 
            f_size = os.path.getsize(cct.get_ramdisk_path('tdx_last_df')) / 1000 / 1000
        else:
            f_size = 0 
        if f_size > 2:
            print("run Cmd")
            print(cmdRun)
            os.system(cmdRun)
        else:
            print("run Cmd200")
            # natclip='''cd /Users/Johnson/Documents/Quant/share_controller/webTools/natclip/natclip;open main.py;'''
            # os.system(f'osascript -e {natclip};sleep 3;')
            os.system(cmdRun200)
        setPosition(cmd=None, position=None)
        os.system(closeLaunch) 
        # getPosition('Johnson@',close=True)
        # getPosition('/Users/Johnson/Documents',close=True)
        print((getPosition('Johnson — bash',close=True)))
        # print getPosition('Johnson',close=True)
        # print getPosition('Johnson — bash',close=True)
        # print getPosition('Johnson — bash',close=True)
        # print getPosition('Johnson',close=True)
        print((getPosition('Johnson — python',close=True)))
        # print getPosition('Johnson',close=True)
# count = doScript(scriptcount        
# os.system(cmdRun)
# getPosition('Johnson@',close=True)

if cct.isMac():
    count = doScript(scriptcount)
    # print count
    # count = 2
    if int(count) > 2:
        # print getPosition('Johnson@bogon',close=True)
        # print getPosition('cd \'/Users/Johnson/Documents/Quant/pyQuant/stock/\'')
        # print getPosition('cd \'/Users/Johnson/Documents')
        # print getPosition('cd \'/Users/Johnson/Documents',close=True)
        for key in list(positionKey.keys()):
            print((getPosition(key)))

        # print 'singleAnalyseUtil.py:',getPosition('singleAnalyseUtil.py')
        # print 'sina_Market-DurationDn.py:',getPosition('sina_Market-DurationDn.py')
        # # print 'sina_Monitor-Market-LH.py:',getPosition('sina_Monitor-Market-LH.py')
        print((getPosition('sina_Market-DurationUP')))
        print((getPosition('sina_Market-DurationDnUP')))
        # # print 'sina_Market-DurationSH.py:',getPosition('sina_Market-DurationSH.py')
        # print 'sina_Market-DurationCXDN.py:',getPosition('sina_Market-DurationCXDN.py')
        # # print 'sina_Market-DurationCXUP.py:',getPosition('sina_Market-DurationCXUP.py')
        # # print 'sina_Market-DurationDnUP.py:',getPosition('sina_Market-DurationDnUP.py')
        # # print 'sina_Monitor-GOLD.py:',getPosition('sina_Monitor-GOLD.py')
        # print 'sina_Monitor.py:',getPosition('sina_Monitor.py')
        print((getPosition('LinePower')))
        print((getPosition('Johnson',close=True)))
        print((getPosition('/Users/Johnson/Documents',close=True)))
        setPosition(cmd=None, position=None)
        
    else:
        if cct.get_day_istrade_date():
            cmd_ls = f'ls -al {cct.get_ramdisk_dir()}{os.sep}'
            rm_ramdisk = f'/bin/rm  -f {cct.get_ramdisk_dir()}{os.sep}*'
            result = subprocess.getoutput(cmd_ls)
            # print(result,rm_ramdisk)
            work_day_idx = cct.get_work_day_idx()
            if 1 < work_day_idx < 6:
                if cct.creation_date_duration(cct.get_ramdisk_path('tdx_last_df')) > 1:
                    if result.find('stock') > 0:
                        os.system(rm_ramdisk)
                print(f'Day is Work:{work_day_idx},check 1 day')

            else:
                if cct.creation_date_duration(cct.get_ramdisk_path('tdx_last_df')) > 2:
                    if result.find('stock') > 0:
                        os.system(rm_ramdisk)
                print(f'Day is Work:{work_day_idx},,check 2 day')


        setPosition(cmd=None, position=None)
        cct.get_terminal_Position(cct.clean_terminal[2],close=True)
    cct.get_terminal_Position(cct.clean_terminal[1],close=True)

    cct.get_terminal_Position(cmd=cct.scriptquit, position=None, close=False)
    # getPosition('Johnson —',close=True)
    # getPosition('Johnson —',close=True)
    # getPosition('Johnson — python',close=True)
    # getPosition('Johnson — osasc',close=True)
    print(f'will close Johnson — python')
    time.sleep(30)
    print((getPosition('Johnson — python',close=True)))
    print((getPosition('Johnson',close=True)))
    doScript(scriptquit)
else:
    print("win")
    #positionKey = cct.terminal_positionKey_triton
    # if hostname.find('R900') >=0:

    #     positionKey = cct.terminal_positionKey2K_R9000P
    # else:
    #     positionKey = cct.terminal_positionKey1K_triton

    print("%s"%(positionKey))
    for key in positionKey:
        print(("title:%s"%(key)))
        # cct.get_window_pos(key)
        cct.get_window_pos(key)
        cct.get_window_pos(key.replace('py','exe'))
    for key in positionKey:
        pos=positionKey[key].split(',')
        # cct.get_window_pos('sina_Market-DurationUP.py')
        key = key.replace('py','exe')
        if len(pos) == 2:
            print(("status:%s"%(cct.reset_window_pos(key,pos[0],pos[1]))))
        else:
            print(("status:%s"%(cct.reset_window_pos(key,pos[0],pos[1],pos[2],pos[3]))))
# print("positionKey:%s"%(get_variable_name(positionKey)))
    # pos=cct.terminal_positionKey_triton['sina_Market-DurationDn.py'].split(',')
    # # print pos
    # # cct.get_window_pos('sina_Market-DurationUP.py')
    # cct.reset_window_pos('sina_Market-DurationDn.py',pos[0],pos[1],pos[2],pos[3])




'''

https://stackoverflow.com/questions/8798641/close-terminal-window-from-within-shell-script-unix

How do I quit the Terminal application without invoking a save dialog?

Hello, I am trying to write an AppleScript that will allow me to close the application Terminal without invoking a dialog box. In my situation I have just run a Python script on Terminal and when I try to quit the Terminal application I am always presented with a "Do you want to close this window?" dialog box. I wrote a simple AppleScript where I specify that I do not want to save when quitting but I am still presented with the dialog box. Does anybody know how to exit the Terminal application with an AppleScript that does not require any user interaction beyond initiating the AppleScript? Here is the simple script I wrote:

tell application "Terminal"
quit saving no
end tell


Then at the end of the script, use:

osascript -e 'tell application "Terminal" to close (every window whose name contains "My Window Name")' &

closeWindow() {
    /usr/bin/osascript << _OSACLOSE_
    tell application "Terminal"
        close (every window whose name contains "YourScriptName")
    end tell
    delay 0.3
    tell application "System Events" to click UI element "Close" of sheet 1 of window 1 of application process "Terminal"
_OSACLOSE_
}


This works for me:

#!/bin/sh

{your script here}

osascript -e 'tell application "Terminal" to close (every window whose name contains ".command")' &
exit


I find the best solution for this is to use Automator to create a true OSX application which will work the same way regardless of how your system is configured. You can have the Automator run your shell script, or you can embed the shell script itself in Automator.

Here is how you do it:

Run Automator (in Applications).
Choose "New Document" and when it asks "Choose a type for your document" choose "Application"
In the left panel, select "Utilities" then "Run Shell Script".
Type in your script commands in the workflow item in the right panel. You can either call another shell script, or just put your commands in their directly.
Save the Application, which will be a full-fledged Mac App. You can even cut-and-paste icons from other apps to give your script some personality.


'''

'''
Even doing a kill or killall without the -9 is abrupt. It doesn't allow Terminal.app to do it's normal checking of whether there are processes still running that you may care about. Why not tell the terminal to quit a a more appleish way? Use AppleEvents.

alias quit='/usr/bin/osascript -e "tell application \"terminal\" to quit"'
If you want something that you can always run when you're done with a window, which will quit Terminal.app in the event it was the last window, a larger script might be in order. First create this AppleScript:
tell application "Terminal"
    if (count of (every window whose visible is true)) <= 1 then
        quit
    else
        close window 1
    end if
end tell
Then just alias it to whatever command you want and add osascript to the list of ignored processes under the Processes section of the window settings.
---

jon

Just 'trap' it
Authored by: apparissus on May 05, '04 11:42:52PM
If you don't want to remember to type "quit" instead of "exit", and you're using bash, just add the following to your .bashrc or other shell startup script:
trap '/usr/bin/osascript -e "tell application \"terminal\" to quit"' 0
What's it do? When the shell receives signal 0 (zero), that is, told to exit, it will execute this command as the last thing it does. This allows your shell, etc, to exit gracefully, and asking Terminal.app to exit via applescript makes sure it does the same. In other words, type 'exit', and your shell exits, then Terminal quits, all cleanly and the way nature intended.

Note:You'll need to add login, bash, and osascript to the exclude list under "Prompt before closing window" or terminal will whine at you before exiting. Or you could just choose "Never". 

Something similar is surely possible with tcsh...but I have no idea how.
'''

'''
https://superuser.com/questions/526624/how-do-i-close-a-window-from-an-application-passing-the-file-name
Closing a window from an application

1) By window index or name of the window

The command to close a window of any named application would be something like this:

tell application "Preview" to close window 1
… or if you want to close a named document window, e.g. foo.jpg:

tell application "Preview" to close (every window whose name is "foo.jpg")
So, in your shell script that'd be:

#!/bin/sh
osascript <<EOF
tell application "Preview"
  close (every window whose name is "$1")
end tell
EOF
Here, the first argument passed to the script is the name of the window you want to close, e.g. ./quit.sh foo.jpg. Note that if your file contains spaces, you have to quote the filename, e.g. ./quit.sh "foo bar.jpg".

Or if you want to close arbitrary windows from any application, use this:

#!/bin/sh
osascript <<EOF
tell application "$1"
  close (every window whose name is "$2")
end tell
EOF
Here, you'd use ./quit.sh Preview foo.jpg for example.

2) By file name

If you want to close a window that belongs to a certain document, but supplying the file name, you need something else. This is because a multi-page PDF could be displayed as foo.pdf (Page 1 of 42), but you'd just want to pass foo.pdf to the AppleScript.

Here we iterate through the windows and compare the filenames against the argument passed to the script:

osascript <<EOF
tell application "Preview"
    set windowCount to number of windows
    repeat with x from 1 to windowCount
        set docName to (name of document of window x)
        if (docName is equal to "$1") then
            close window x
        end if
    end repeat
end tell
EOF
Now you can simply call ./quit.sh foo.pdf. In a generalized fashion, for all apps with named document windows, that'd be:

osascript <<EOF
tell application "$1"
    set windowCount to number of windows
    repeat with x from 1 to windowCount
        set docName to (name of document of window x)
        if (docName is equal to "$2") then
            close window x
        end if
    end repeat
end tell
EOF


Caveat: Auto-closing Preview.app

Preview.app is one of these applications that automatically quits once its last document window is closed. It does that in order to save memory and "clean up". To disable this behavior, run the following:

defaults write -g NSDisableAutomaticTermination -bool TRUE
Of course, to undo that, change TRUE to FALSE.



Using functions instead of scripts

Finally, I'd suggest putting your scripts into a function that is always available in your shell. To do this, add the scripts to your ~/.bash_profile. Create this file if it doesn't exist.

cw() {
osascript <<EOF
tell application "$1"
    set windowCount to number of windows
    repeat with x from 1 to windowCount
        set docName to (name of document of window x)
        if (docName is equal to "$2") then
            close window x
        end if
    end repeat
end tell
EOF
}
Once you save your bash profile and restart the shell, you can call cw Preview foo.pdf from everywhere.
'''
