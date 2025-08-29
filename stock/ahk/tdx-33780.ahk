;脚本功能：获取通达信软件上的股票代码
;测试环境：招商证券、中银国际提供的官方通达信客户端
;作者微信：sunwind1576157
;发布时间：2020年2月6日
;最新版本：https://blog.csdn.net/liuyukuan/article/details/104195901
;验证方式：在交易软件中按 热键 win+z
 
#z::
SendMessage,0x111,33780,0,,ahk_class TdxW_MainFrame_Class
MsgBox %Clipboard%
return 
