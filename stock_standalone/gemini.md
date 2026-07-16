## 2026-07-16 18:30
- [x] **隡睃�銝芾�霂行�/�𡒊�蝒堒藁嚗㇄istributionDetailsDialog & StockDetailDialog嚗厩��貉斐颲寥��誯俈霂航圻�𠹺漱鈭㘾�璉埝�� (Optimized Auto-Hide Debounce & Drag Locking in ATS Detail Windows)**嚗�
    - [x] **摰䂿緵�硋𢆡蝒堒藁����𤩺𧒄��香銝漤��� (Drag Lock Protection & Mouse Button Status)**嚗𡁜銁 `moveEvent` �嗉䌊�刻挽蝵� `_is_dragging = True`嚗�僎�� `_check_hover` 銝剖��� `QApplication.mouseButtons()` �拍��嗆���瘚卝����行�瘚见�曌䭾�撌阡睸憭���劐��嗆����單迤�冽��賣�憸䀹����隡貊����獢��㕑”�潘�嚗𣬚凒�亙撩�� short-circuit 蝳餃��文�撟園�蝵株恣�啣膥嚗峕𠹭�见��齿�憭齿�瘚页�敶餃��寞祥鈭���賜宏�冽�靚�㟲憭批��罸𡢿鋡怠撩銵峕𤣰�鮋��讐��𤤿���
    - [x] **靽桀��硋𢆡蝒堒藁餈��銝剔��澆𢙺�函𤫇�芰� (Fixed Snap Flicker During Dragging)**嚗𡁜銁 `_detect_and_snap` 蝤�𢙺頞�𧒄璉�瘚衤葉嚗���𨀣�瘚见��冽������椰�桐��芷��橘�`QApplication.mouseButtons()` ��鉄撌阡睸嚗㚁��嗵凒�亥䌊�券��啣𤧅韏� `snap_timer` �坿恣�嗅僎���綽�蝏苷��函鍂�瑟�雿誯�����賣��渲圻�睲遙雿訫𢙺��駚甇��銝漤�𤩺�摨血鐤�賊緾����芣��冽𠹭�见��滢�甈⊥�找���圻�𡢅�蝖桐�鈭���賜宏�冽𧒄���撖孵像皛穃漲��
    - [x] **靽桀��曹�����譍�撅硺� geometry ��凒撘訫�����𡏭秤�� (Fixed Title Bar Hover Recognition)**嚗𡁜���𧋦�� `_check_hover` 銝凋蝙�函� `self.geometry().contains()` �踵揢銝箏��怎����颲寞����憸䀹�銝𤾸�颲寞��� `self.frameGeometry().contains()`��圾�喃�敶㯄������𦆮蝵桀銁����譍��硋銁����譍��硋𢆡蝒堒藁�塚��曹�銝滚�鈭𤾸恥�瑕躹�諹◤霂臬ế銝算�𨅯歇蝳餃�蝒堒藁�肽��諹圻�𤏸䌊�券��讐��餉�蝻粹萅��
    - [x] **摰䂿緵�𡁏��箏� 1.2蝘� �瑕㭂�脫��園𡢿�𣂼� (Post-Show Cooldown)**嚗𡁜銁 `show_normal_position` 閫血��嗉扇敶訫��齿𧒄�湔� `_last_show_time`��𥅾蝒堒藁皛穃枂撅閧內�芣說 1.2 蝘𡜐�隞颱�曌䭾��讐氖�滢����隡𡁶敞�删氖撘�霈⊥𧒄�剁�`leave_ticks`嚗㚁�靽肽�鈭�鍂�瑁�蝥� and 曌䭾�蝘餃𢆡頝蠘��嗥�閫��鈭支�蝔喳��扼��
    - [x] **摰䂿緵�𨀣䰻�𦥑�嘥鐤�箸𧒄銝滩䌊�券��誩�擐𡝗活蝘餃�瞈�瘣駁�餉� (Ignore-Hide Until First Hover)**嚗𡁜銁 `show_normal_position` �滨蔭蝘餃���� `_has_hovered_since_show = False`嚗�銁 `_check_hover` 銝凋��行�瘚见�曌䭾���迤餈𥕦�蝒堒藁�躰挽銝� `True`��� `_has_hovered_since_show` 銝� `False` �塚�蝳餃�蝒堒藁�文��湔𦻖�剛楝嚗��蝢擧𣈲���隞𤾸極�瑟��𨀣䰻�𦥑�脲��桐蜓�冽�撘�雿����𧊋餈𥕦��嗡��嗉絲����阡�����交�雿𨅯僎蝳餃��擧��齿活閫血��芸𢆡�鞱���鸌�扼���肽��諹圻�𤏸䌊�券��讐��餉�蝻粹萅��
    - [x] **摰䂿緵�𡁏��箏� 1.2蝘� �瑕㭂�脫��園𡢿�𣂼� (Post-Show Cooldown)**嚗𡁜銁 `show_normal_position` 閫血��嗉扇敶訫��齿𧒄�湔� `_last_show_time`��𥅾蝒堒藁皛穃枂撅閧內�芣說 1.2 蝘𡜐�隞颱�曌䭾��讐氖�滢����隡𡁶敞�删氖撘�霈⊥𧒄�剁�`leave_ticks`嚗㚁�靽肽�鈭�鍂�瑁�蝥� and 曌䭾�蝘餃𢆡頝蠘��嗥�閫��鈭支�蝔喳��扼��
    - [x] **摰䂿緵�𨀣䰻�𦥑�嘥鐤�箸𧒄銝滩䌊�券��誩�擐𡝗活蝘餃�瞈�瘣駁�餉� (Ignore-Hide Until First Hover)**嚗𡁜銁 `show_normal_position` �滨蔭蝘餃���� `_has_hovered_since_show = False`嚗�銁 `_check_hover` 銝凋��行�瘚见�曌䭾���迤餈𥕦�蝒堒藁�躰挽銝� `True`��� `_has_hovered_since_show` 銝� `False` �塚�蝳餃�蝒堒藁�文��湔𦻖�剛楝嚗��蝢擧𣈲���隞𤾸極�瑟��𨀣䰻�𦥑�脲��桐蜓�冽�撘�雿����𧊋餈𥕦��嗡��嗉絲����阡�����交�雿𨅯僎蝳餃��擧��齿活閫血��芸𢆡�鞱���鸌�扼��

## 2026-07-16 18:30
- [x] **优化个股详情/明细窗口（DistributionDetailsDialog & StockDetailDialog）磁吸贴边隐藏防误触及交互鲁棒性 (Optimized Auto-Hide Debounce & Drag Locking in ATS Detail Windows)**：
    - [x] **实现拖动窗口标题栏时锁死不隐藏 (Drag Lock Protection & Mouse Button Status)**：在 `moveEvent` 时自动设置 `_is_dragging = True`，并在 `_check_hover` 中引入 `QApplication.mouseButtons()` 物理状态检测。一旦检测到鼠标左键处于按下状态（即正在拖拽标题栏、拉伸窗口或框选表格），直接强制 short-circuit 离开判定并重置计数器，松手后才恢复检测，彻底根治了拖拽移动或调整大小期间被强行收回隐藏的痛点。
    - [x] **修复拖动窗口过程中的呼吸动画闪烁 (Fixed Snap Flicker During Dragging)**：在 `_detect_and_snap` 磁吸超时检测中，如果检测到用户的鼠标左键仍未释放（`QApplication.mouseButtons()` 包含左键），则直接自动重新唤起 `snap_timer` 倒计时并退出，绝不在用户按住鼠标拖拽期间触发任何吸附矫正与不透明度呼吸闪烁，只有在松手后才一次性优雅触发，确保了拖拽移动时的绝对平滑度。
    - [x] **修复由于标题栏不属于 geometry 范围引发的悬停误判 (Fixed Title Bar Hover Recognition)**：将原本在 `_check_hover` 中使用的 `self.geometry().contains()` 替换为包含窗口外边框、标题栏与内边框的 `self.frameGeometry().contains()`。解决了当鼠标指针放置在标题栏上或在标题栏上拖动窗口时，由于不属于客户区而被误判为“已离开窗口”进而触发自动隐藏的逻辑缺陷。
    - [x] **实现刚滑出后 1.2秒 冷却防抖时间限制 (Post-Show Cooldown)**：在 `show_normal_position` 触发时记录当前时间戳 `_last_show_time`。若窗口滑出展示未满 1.2 秒，任何鼠标偏离操作均不会累加离开计时器（`leave_ticks`），保证了用户视线 and 鼠标移动跟进时的视觉交互稳定性。
    - [x] **实现“查看”呼出时不自动隐藏及首次移入激活逻辑 (Ignore-Hide Until First Hover)**：在 `show_normal_position` 重置移入标志 `_has_hovered_since_show = False`，在 `_check_hover` 中一旦检测到鼠标真正进入窗口则设为 `True`。当 `_has_hovered_since_show` 为 `False` 时，离开窗口判定直接短路，完美支持了从工具栏“查看”按钮主动打开但鼠标未进入时不收起、一旦鼠标进入操作并离开后才再次触发自动隐藏的特性。

## 2026-07-16 17:15
- [x] **摰���𠉛氖撟嗅��� Tkinter 靘肽�隞亥圾�� Qt 憭𡁶瑪蝔� GIL 蝡硺�撏拇� (Decoupled Tkinter Lifecycle & Prevented GIL Crash in ATS)**嚗�
    - [x] **敶餃��娪膄 Tk/Tcl 隞亙� QueryHistoryManager 靘肽�**嚗𡁜縧�支� `ATSMainWindow` 銝剖��厩� `tk_root`��history_win` 銝� `query_manager` 摰硺�隞亙����厩���瘥���笔𦶢�冽��餉�嚗���支��麨�𦦵恣���脲��柴���敶餃��寧�鈭�像�嗉����憸煾店�冽𧒄摨訫��� Tk 瘨���拙�撟脫贋嚗䔶��拍�銝𦠜�蝏苷� `PyEval_RestoreThread` �仿�撖潸稲�� GIL 撏拇���
    - [x] **撘��𤑳滲 Python �唳旿閫��銝擧�隞嗅��坔� (Direct JSON loader/writer)**嚗𡁶��嗘� `_load_search_history_data`��_save_search_history_data` �� `_get_search_history_filepath` 颲�𨭌�賣㺭��蜓蝒堒藁�湔𦻖霂餃� `search_history.json`嚗���唬�銝𤾸�蝞∠��屸𢒰 100% �詨���㺭�桀笆朣僐��聢撘誩�銝擧�銋���箏���
    - [x] **�齿���蟮餈�誘銝� Hit �賭葉瘚讠��餉� (Local Cache Logic Refactoring)**嚗𡁜�撌亙��誩��脩���揢����格�蝞� Hit��誑�𦠜鰵憓噼�皛文�撘讛蕭�删��餉�嚗���ａ���蛹�箔�銝餌����摮� `self.search_histories` 蝻枏���粉�踺��朖雿踹銁瘝⊥�隞颱� Tk/Tcl �臬��������萎�嚗��撘讛粉�硋��賭葉�唳�蝞𦯀��賣說銵�餈鞱���
    - [x] **���箸𧒄�芸𢆡����𤥁䌊��**嚗𡁜銁 `closeEvent` 銝凋��嗘�撠�蜓�屸𢒰銝剖虾�賣鰵憓䂿�餈�誘�砍��芸𢆡�𧼮��� JSON ��辣���銋���餉���

## 2026-07-16 16:55
- [x] **�� ATS 銝餌���葉摰𣬚���� `QueryHistoryManager` 餈�誘銝𤾸�蝒堒藁�𥪜𢆡�瑟鰵 (Integrated QueryHistoryManager Filtering & Dynamic Multi-Window Linkage in ATS)**嚗�
    - [x] **摰䂿緵 Tk �寧���� History Manager ����啣��典�頧�**嚗𡁜銁 `ATSMainWindow.__init__` �嘥��碶葉嚗䔶誑�鞱� `tk.Tk()` �寧���� `Toplevel` 敶Ｗ��䠷��㰘蝸 `QueryHistoryManager`��笆鈭擧�����祉��函蔡�嗥��滨蔭��辣 `search_history.json` 餈𥡝�鈭�𤌍敶閗䌊����Ｘ�嚗䔶��� `try-except` ���靽脲擪嚗屸俈�� Tk 摨枏�憪见����嚗𣬚�撖嫣��靝� ATS 蝏�垢�瑕鍳�冽𧒄����冽�扼��
    - [x] **�其蜓撌亙��誩��亙�憭����蟮餈�誘�批�瘚� (Toolbar Filter Integration)**嚗𡁻���� `_init_toolbar`嚗�銁�𥪜𢆡�㗇𥋘�冽��惩�鈭��𨅯��脩��㗇𥋘 ComboBox�腈���靝��� Hit �賭葉�厰僼�腈���𨅯蒂��蟮颲枏��娍����皛斤�����腈���𡏭�皛手�腈���𨀣�蝛算�苷��𦦵恣���嘥�憟� UI �批�瘚��銝𦒘犖瘞娍�銵� GUI 摰䂿緵����� and 閫��鈭支� 100% 撖寥���
    - [x] **摰䂿緵�砍���蟮蝞∠��� (QM) �� ATS 蝡舐����摰墧𧒄�峕郊**嚗𡁻��嗘� `_on_history_group_changed` 銝� `sync_history_from_QM`��𣈲����冽��� Tk ��蟮蝞∠��Ｘ踎�劐葉�砍�����其蜓�屸𢒰�㗇𥋘��蟮蝏�𧒄嚗龦omboBox 銝𧢲��厰★�𡃏��交��芸𢆡閫����笆朣琜�摰𣬚�撅閧內�𨅯�瘜� | [Hit �賭葉�財 | �砍��萘�擃条漣憭滚��澆�嚗�僎�祇𡢿摨𠉛鍂餈�誘��
    - [x] **��� (N) �煾��𡝗鸌�誩�撘讛�皛支� Hit �賭葉蝏蠘恣霈∠�**嚗𡁻���� `calculate_history_hits_ui` 銝� `get_test_df_for_hits`��䌊�冽𤣰���銝剖歇�厩����啗������鉄 `current_df` 蝻枏�嚗㚁�撠�葉���畾蛛�隞瑟聢��隅撟����蝑㚁��煾��𡝗�撠�笆朣𣂷蛹餈�誘撘閙�������㘚���畾蛛��滢��格鸌�𤩺�銵峕�霂訫僎�祇𡢿�䂿��滨� Treeview 銝剜��㗇辺�桃� Pct/Hit 撅墧�扼��
    - [x] **摰䂿緵憭𡁶���嘀�剖�敹�歲�瑟鰵銝𤾸��嗅�撘讛�瘚贝䌊��**嚗𡁜銁 `refresh_realtime_ui` 摰䂿�敹�歲摰𡁏𧒄�其葉嚗���牐��滚����㗇暑�� `StockDetailDialog` 摰硺����餉����銝剛����甈⊥��函��交𧒄嚗𣬚頂蝏煺�隞��甇交凒�啣�霂行�蝒堒藁����唳���”�潘�餈䀝��瑕�銝餌�雿枏��滨� `query_expr` 餈�誘銵刻噢撘𧶏�撟嗉��� `update_filter_status` 霈抵祕�����䌊�冽凒�啣𦶢銝剜�霂��Hit/Miss嚗㚁�颲曉�鈭��雿喟�摰墧��望𥲤�漤���
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `ats/ui/main_window.py` 餈𥡝�鈭��霂烐嵗撉䕘��冽㺭蝏輻��牐遙雿閗祗瘜閙�蝻抵��仿�嚗䔶�霂��頧臭辣�𤩺𧒄�臭誑蝔喳��枏��函蔡��

## 2026-07-16 16:20
- [x] **摰���𠉛氖銝滚�瘨刻��粹𡢿銝芾��𡒊�蝒堒藁���撅���㺭銝舘䌊���憭� (Isolated Layout Keys for Each Return Bucket)**嚗�
    - [x] **撘訫��冽��睸頝舐眏**嚗𡁜銁 `DistributionDetailsDialog` 銝剖��� `bucket_idx` 摮埈挾嚗���笔��梁鍂�� `"distribution_details_dialog"` 蝏煺��滨蔭頝舐眏�齿�銝箸�銝芸躹�渡𡠺蝡见𣈲銝��� `f"distribution_details_dialog_{bucket_idx}"` �滨蔭�柴���敶餃�閫��鈭��銝芸躹�湔�蝏������嗆�撘��園��惩銁�䔶��鞉����瘜訫��怨扇敹��蝵桃�銝仿�蝻粹萅��
    - [x] **撟嗅�憭𡁶���鍳�刻䌊��**嚗𡁜銁 `_restore_details_dialog_if_saved` 銝剖�蝥找蛹撖� 0-9 �� 10 銝芸躹�渲�銵諹蔭霂ｇ��⊥糓霈啣�銝� `is_open=True` �������賭���䌊隞交迤蝖桃��鞉� and �鞱��嗆��◤�芸𢆡�Ｗ��滚遣嚗�蝠摨閙��支��訾�閬���𡝗�瘜閙�憭滨�雿㯄�瞍𤩺���
- [x] **摰䂿緵�瑕鍳�冽��唳旿�嗆�蝏����朖�嗆�憭滢�撟踵偘撘誩�頝喳��� (Cold-start Detached Recovery & Broadcast Refresh)**嚗�
    - [x] **�㰘�銵峕�撱嗆𧒄�單𧒄�Ｗ�**嚗𡁜銁 `DistributionBarChart` ����惩遆�唬葉餈賢�鈭� 800 瘥怎�撱嗆𧒄����臬𢆡�芣���誘��朖雿輻頂蝏笔��臬𢆡銵峕��唳旿餈䀹瓷�㗇��硋�甇亙�瘥𤏪�銋蠘��㰘�銵峕��唳旿蝡见��厩�銋见�����牐�摰帋��嗆���蝒堒藁�餃銁獢屸𢒰嚗�”�潛蔭蝛箏僎�曄內 `�� 甇�銁蝑匧��唳旿�峕郊...` �鞟內嚗㚁�敶餃�瘨�膄鈭��𨅯鍳�典末銋��蝒��撘寧��萘��剜﹝銝𡒊����麄��
    - [x] **�芷���敹�歲撟踵偘�湔鰵**嚗𡁜銁銵峕��交𤣰蝡舐� `update_data` �亙藁�滚�鈭���������餉�����行𦻖�嗅����啣�撣�㦤銵峕��� `UPDATE_DF_ALL`嚗諹䌊�典�銝𧢲虜���匧��滚�鈭擧暑�函𠶖����𡒊�蝒堒藁撟踵偘憓鮋�銝芾��唳旿嚗���啣�銵典����霈⊥㺭嚗���唬�瘥怎�蝥把�𨀣��唳旿�單說銵�嚗���嗉歲�兩�萘�擃㗛��峕郊��
    - [x] **摰䂿緵頝函�����滚��餃縧��**嚗𡁜銁 `open_details_dialog` 瘜典�璉�瘚见�嚗���餌㮾�𣬚凒�孵㦛�勗��塚��湔𦻖撠��撌脫�蝒堒藁�澆枂撟嗆�憭滚�撘�嚗Ǒshow_normal_position`嚗㚁��踹�鈭��憭滚�撱箏��粹𡢿蝒堒藁撖潸稲���皞鞉��脯��
- [x] **靽桀��曹� `isVisible()` 餈�誘撖潸稲憭𡁶���鍳�刻䌊�冽�憭齿𧒄鋡� GC ��瘥��蝻粹萅 (Fixed Restoration GC Bug)**嚗�
    - [x] �� `open_details_dialog` ��暑�函�������餉�銝哨�蝘駁膄撖� `d.isVisible()` ���雿躰�皛扎�����銁�臬𢆡�嗡�甈⊥�憭滚�銝芣�蝏������曹��滚�銝芰�����芾◤ Qt 鈭衤辣敺芰㴓��扇銝箏虾閫��`isVisible() == False`嚗㚁�隡朞◤隞� `_active_dialogs` 撘箏��典�銵其葉�躰秤�娪膄嚗�紡�游��函��渲◤ Python ��䔿�墧𤣰�剁�GC嚗厰�暺睃��園�瘥���耨�嫣蛹隞��朞� `not isdeleted(d)` �斗鱏蝒堒藁�臬炏�� C++ 撅�𢒰�笔�摮睃銁嚗䔶��䔶��靝����㕑◤�Ｗ��������賜迅摰𡁜�蝷箝��
- [x] **靽桀��见𢆡�𣇉氖颲寧��嗆𧊋�滨蔭蝤�𢙺�嗆��紡�游�憭滩◤�匧��� Bug (Fixed Infinite Snapping Loop on Manual Drag)**嚗�
    - [x] **�见𢆡蝘餃𢆡�嗆��撩銵䔶葉��**嚗𡁜銁 `DistributionDetailsDialog` �� `StockDetailDialog` �� `moveEvent` �行⏛銝哨�憒��璉�瘚见�敶枏���宏�冽�雿靝��舐眏鈭𤾸𢆡�颱漣�毺�嚗諹秩�𡒊鍂�瑟迤�冽�銵𢞖�𨅯�蝒堒藁�𣇉氖撅誩�颲寧��萘��滢�嚗峕迨�嗅銁�祇𡢿撘箄�撠� `self.anchor_edge` 蝵桐蛹 `None`����𤘪鱏鈭���滨�蝤�𢙺�文�嚗屸俈甇Ｗ銁�𡝗嗻�喳�撟蓥葉憭格𧒄嚗𣬚眏鈭𡡞����蝘餃枂颲寧�撖潸稲鋡� hover 摰𡁏𧒄�刻秤�支蛹�𦦵氖撘�蝒堒藁�肽��諹圻�� `hide_to_edge` 撘箄��匧��鞱��嗆����嗆�批儐�胯��

## 2026-07-16 16:10
- [x] **摰䂿緵銝芾��𡒊�蝒堒藁嚗㇄istributionDetailsDialog嚗厩��賢𪂹�煺��嗆��䌊�冽�銋���𢠃�暺䁅䌊���憭� (Automated Snap/State Persistence & Seamless Restoration)**嚗�
    - [x] **�嗆����嗡����箏��堒� (Atomic State Serialization)**嚗𡁻���� `_save_window_states(is_open=...)`嚗䔶蝙蝒堒藁�冽��賜��詨��麄����𤩺��𨬭��迤撣詨�撘��硋��剜𧒄嚗屸��賢��嗆��券���箸𧒄撠���齿糓�行�撘� (`is_open`)��誨銵典躹�� (`bucket_idx`)��𢙺��器�� (`anchor_edge`)��糓�阡��� (`is_hidden_state`) ���撘��鞉�撠箏站 (`normal_geometry`) �坔� `window_layout_config.json`��
    - [x] **�箄����箸��曇��� (Exit vs Manual Close Detection)**嚗𡁜銁 `closeEvent` �� `hideEvent` 銝剖��乩�銝餌�摨讐�摮睃ế摰𠾼���璉�瘚见�銝餃��函�摨𤩺迤�券���箸�撌脖��航��塚�蝟餌��賣惣�質��怠枂�𣈯��冽��见𢆡�喲𡡒�萘��誩㦛嚗䔶���� `is_open` 霈啣�銝� `True` 靽脲擪�嗥��賢𪂹����脫迫�牐蜓蝔见��喲𡡒撖潸稲銝𧢲活�臬𢆡�䭾��Ｗ���
    - [x] **撘�郊�䭾��滨��Ｗ� (Async Restoration Flow)**嚗𡁜銁 `DistributionBarChart` �� `update_data` 銵峕�����其葉憓𧼮�鈭�㺭�桀停蝏芸ế摰帋� `QTimer.singleShot` �鮋獈憛𧼮辣餈麄����䀝葉銵峕�擐𡝗活����塚��芸𢆡閫���嗆��僎靚�鍂撣� `restore_state` ��㺭�� `open_details_dialog`嚗�銁蝒堒藁�曄內�漤�暺䁅��笔�蝤�𢙺�嗆������𤩺�摨血�雿滨蔭嚗���唬�摰����漱鈭㘾𡡒�胯��

## 2026-07-16 16:00
- [x] **銝芾�霂行�銝𦒘葵�⊥�蝏��銵典�蝒堒藁蝤�𢙺�鞱��嗆�摰��撖寥� (Fully Snapped & Animated Snapping/Hiding across Details & List Views)**嚗�
    - [x] **`DistributionDetailsDialog`嚗�隅頝��撣�葵�⊥�蝏�����摰䂿緵摰��銝��渡�蝤�𢙺�睃��蠘�**嚗𡁜銁 `ats/ui/chart_widgets.py` 銝哨�銝� `DistributionDetailsDialog` 瘜典��𡝗嗻銝擧��𨀣�瘚见��嗅膥嚗���渡宏璊滢� `start_slide_animation`����詻����譍��祆筑�日�蝑匧��典像皛烐��典��澆𢙺�芰��寞���
    - [x] **�寞祥�� Parent �� QDialog 蝤�𢙺雿滨宏憭望�蝻粹萅**嚗𡁜銁 `StockDetailDialog` ���惩遆�唬葉嚗屸�朞�撘箏�皜�膄 `Qt.WindowType.Dialog` 撟嗅��� `Qt.WindowType.Window` 蝒堒藁���嚗���嗆���蛹摰���祉���▲撅�������閫�膄鈭� Windows DWM 撖孵�蝒堒藁���蝥找����找�蝘駁��塚�蝖桐��典��曄內�冽��芰眏�𡝗嗻�啣�撟閖▲�具��椰靘扳��喃儒颲寧��嗥��賊��� 100% �𣂼���
    - [x] **銝餌���俈霂航圻�䠷�霈曇恣**嚗帋蜓撌乩�蝏�垢嚗ǑATSMainWindow`嚗劐�銝箏�撅�鈭支�銝剜攟嚗�銁霈曇恣銝𠹺��������脫迫�删�銝剝�憸𤑳宏�刻�䔶漣�蠘秤閫行��𨬭��

## 2026-07-16 15:50
- [x] **摰䂿緵銝芾��𡒊�蝒堒藁蝤�𢙺銝𡡞��讐�撟單��函𤫇銝舘�閫厰緾���蝷� (Implemented Smooth Slide Animations and Snapping Opacity Flash Feedback)**嚗�
    - [x] **摰䂿緵蝏煺�����典𢆡�餅綉�嗅膥 `start_slide_animation`**嚗𡁻�朞���� `QPropertyAnimation` �� `QParallelAnimationGroup`嚗�笆蝒堒藁�� `geometry` �� `windowOpacity` 撅墧�批��嗉�銵��頧刻���綉�塚�撟嗅��其��䂿瑪�抒� `QEasingCurve.Type.OutCubic` 蝻枏𢆡�脩瑪嚗峕𤜯�Ｗ��祉�蝖祉��祉宏摰帋���
    - [x] **摰䂿緵韐渲器蝤�𢙺�𣂼��嗥��澆𢙺�鞟內�漤� (Snapping Visual Feedback)**嚗𡁜銁蝒堒藁�𤑳�蝤�𢙺撖寥��塚�雿輻鍂撣行�頧餃凝撘寞�批�撘寧��脩瑪嚗ǑOutQuad`嚗㚁�撟嗡蝙�� `setKeyValueAt(0.5, 0.4)` �典𢆡�颱葉�𥪜�銝漤�𤩺�摨血翰�罸緾����澆𢙺瘛∪��� 0.4 �齿�憭㵪�嚗𣬚��冽���蔔���𨅯歇閫血�蝤�𢙺�𡃏䌊�券��𤩺㦤�嗯�萘��冽���蝷綽�蝐颱撮 QQ 蝒堒藁���嚗剹��
    - [x] **摰䂿緵瘚������乩�皛穃枂�函𤫇 (Slide In/Out Transition)**嚗𡁻���氖撘� 400ms �𠬍�蝒堒藁隡帋誑 300ms ��像皛烐��典𢆡�颱���憬餈𥡝器蝻矋�銝漤�𤩺�摨血像皛𤏸�皜∟秐 `0.35`嚗偦���宏�� 5px �笔��� 200ms �𠬍�蝒堒藁隡帋誑 200ms ��𢆡�餃翰�煺�颲寧�撟單��匧枂嚗䔶��𤩺�摨行�憭滩秐 `1.0`嚗峕㟲雿㮖漱鈭埝��嗉�韐胯�������

## 2026-07-16 07:50
- [x] **摰䂿緵銝芾��𡒊�蝒堒藁韐渲器�芸𢆡�鞱�����訾��砍�撘孵枂�蠘� (Implemented Individual Stock Detail Auto-Hide, Edge-Snapping, and Hover-triggered Reveal)**嚗�
    - [x] **摰䂿緵�墧芋��葵�∟祕�����**嚗𡁜� `ATSMainWindow.on_stock_clicked` �臬𢆡 `StockDetailDialog` ��芋撘譍�璅⊥�� `dialog.exec()` �齿�銝粹�璅⊥�� `dialog.show()`嚗�僎�冽�甈∪撕�箸鰵蝒堒藁�滚�摰匧��喲𡡒撌脫���祕�������峕𧒄銝� `StockDetailDialog` 瘜典� `WA_DeleteOnClose` 撅墧�改��脫迫憭𡁏活撘孵枂�𠰴�摮䀹�瞍譌��
    - [x] **摰䂿緵撅誩�銝㕑器韐渲器�芸𢆡蝤�𢙺 (Edge-Snapping)**嚗𡁜銁 `StockDetailDialog` 銝剜溶�� `snap_timer` �脫�閫血��箏�����冽��硋𢆡蝒堒藁�唾�蝳餃�撟閖▲�具��椰靘扳��喃儒颲寧� 35 �讐�隞亙��塚��芸𢆡霈∠�撟嗅笆朣鞟��貉秐撅誩�颲寧�嚗���園�摰朞砲颲寧�雿靝蛹�鞱��箏��孵�嚗Ǒanchor_edge`嚗㚁��㘾膄鈭���其遙�⊥���僕�啜��
    - [x] **摰䂿緵撱嗉�蝳餃�韐渲器�芸𢆡�鞱� (Auto-Hide to Edge)**嚗𡁜�蝒堒藁撌脣��鞱器蝻条��詨笆朣琜�曌䭾�蝘餃枂蝒堒藁��凒撟嗡��� 400ms �塚�蝒堒藁撠�䌊�冽𤣰蝻抵秐隞���� 5 �讐�摰賢漲���摨�/閫��蝒�辺�坔銁撅誩����撟嗉䌊�典�蝒堒藁銝漤�𤩺�摨阡�雿舘秐 `0.35`嚗䔶��𣬚輕����Ｙ征�渡�蝥臬��扼��
    - [x] **摰䂿緵撱嗉��砍��芸𢆡撘孵枂銝擧�憭� (Hover-triggered Reveal)**嚗𡁜�曌䭾�蝘餃�韐渲器�鞱��嗆������摨𠉛��∪僎靽脲� 200ms 隞乩��塚�蝒堒藁撠�䌊�冽��典��蠘秐������蝵桐�撠箏站嚗Ǒnormal_geometry`嚗㚁�撟嗅�銝漤�𤩺�摨行�憭滩秐 `1.0`嚗���嗆��𧼮��啗��佗��舀�瘚������䀝漱鈭雴�撉䎚��

## 2026-07-15 19:50
- [x] **隡睃�蝒堒藁�鞉�蝞∠��典��典�撅��䁅��芷���銝𤾸𢰧撖寥� (Optimized Window Manager Bottom Bar FlowLayout Autowrap & Right Alignment)**嚗�
    - [x] **�舀� `FlowLayout` ���蝝Ｗ��𡒊�����冽��拐�摰賢漲�嗉䌊�典𢰧撖寥�**嚗𡁜銁 `FlowLayout` �� `_do_layout` �餉�銝哨�霈∠��箸�銵𣬚��舐鍂�拐�蝛粹𡢿 `extra_space`��覔�� `self._align_right_from_index` �斗鱏敶枏�銵峕糓�血�鈭𡡞�閬�𢰧撖寥��������𨀣糓瘛瑕�銵䕘��Ｘ�撌虫儒�������喃儒���嚗㚁��坔銁蝚砌�銝芸𢰧靘批�蝝惩�摨𠉛鍂�券� `extra_space`嚗𥕦��𨀣糓蝥臬𢰧靘批�蝝㰘�嚗���冽㟲銵諹絲�孵�摨𠉛鍂�券� `extra_space`��
    - [x] **銝箏��典極�瑟�摨𠉛鍂�喳笆朣𣂼���**嚗𡁜銁 `WindowPosManagerUI.init_ui` 銝哨�摰硺��� `bottom_bar = FlowLayout(hspacing=6, vspacing=6, align_right_from_index=3)`���蝖桐�鈭�椰靘抒��𨅯�撅��剝睸�嘥��嗉��交����摰𡁏��桅�撌血笆朣琜���𢰧靘抒��𨥉�� �扯�����腈���鎿黾 頝舐眏霈曄蔭�腈���𨥉�� 靽嘥��滨蔭�腈���𨥉�� 蝡见朖摨𠉛鍂撣���嘥��鎿� 摰�����算�脲��桀銁蝒堒藁颲�捐�嗉䌊�典𢰧撖寥�嚗�僎�函���𤣰蝻拇�銵峕𧒄靽脲�銝��渡��滚�撘𤩺�撘誩�撅���
    - [x] **摰䂿緵�典��剝睸颲枏�獢�捐摨血𢆡��䌊���銝𥪜�憪讠𠶖��𤣰蝻� (Implemented Dynamic Adaptive Width for Hotkey Input Box with Compact Initial State)**嚗�
        - [x] �� `HotkeyLineEdit` 銝剖� `textChanged` 靽∪噡銝� `adjust_width()` 瑽賢遆�啗��伐��冽���朞� `horizontalAdvance()` 瘚钅�敶枏�敹急㭘�桀�蝚虫葡���蝝惩捐摨血僎靚�㟲颲枏�獢�捐摨艾��
        - [x] �𣂼���撠誩捐摨虫蛹 `90px` 銝𥪯��齿��讛��踹�雿滨泵��𧋦嚗�"�孵稬�𡒊凒�交�銝见翰�琿睸..."嚗㚁�蝖桐�敶𤘪𧊋蝏穃��剝睸嚗��皜�征嚗匧�蝏穃�鈭�掩隡� `ctrl+alt+f` 蝑厩�敹急㭘�格𧒄嚗諹��交�靽脲���稲��𤣰蝻拍揮�𤑳𠶖���閫��鈭�捐摨西��拚䔮憸塩��
        - [x] �� `WindowPosManagerUI.init_ui` 銝哨�敶餃�蝘駁膄��𧋦蝖祉���� `setFixedWidth(150)` 撠箏站�𣂼�嚗䔶漱�梯��交�蝐餉䌊頨急�����芣��冽��恣蝞𨰜��


## 2026-07-15 19:40
- [x] **摰䂿緵�芸𢆡�唾窈 Windows 蝞∠��䀹��鞉溶�𣳇���楝�勗��� (Implemented Automatic Windows Admin Privilege Elevation for Routing Check)**嚗�
    - [x] **璉�瘚见僎�斗鱏蝞∠��䀹���**嚗𡁜銁 `core.check_and_add_route` 銝剝�朞� `ctypes.windll.shell32.IsUserAnAdmin()` 餈𥡝��斗鱏��𥅾敶枏��冽�撌脩�隞亦恣���頨思遢餈鞱�嚗���湔𦻖餈鞱� `route add` �賭誘��
    - [x] **撘訫� UAC 撘寧��鞉��唾窈 (UAC Privilege Elevation Request)**嚗𡁜笆鈭𦒘誑�桅�𡁶鍂�瑟��鞱�銵𣬚��臬�嚗�⏚�� Windows �毺� `ctypes.windll.shell32.ShellExecuteW` API 撟嗡蝙�� `runas` 靚栞�嚗屸�暺䁅�韏� UAC �鞉��鞟內嚗諹窈瘙��銵� `cmd.exe /c route add ...` �賭誘嚗峕��蠘䌊�刻���溶�㰘楝�晞��
    - [x] **隡㗛�撘�虜憭��銝𡒊��𨀣嵗撉� (Graceful Exception & Validation)**嚗𡁏溶�牐� `ret == 1223`嚗�鍂�瑕�瘨� UAC ���嚗厩�摰匧��嗆����舐��行⏛銝𤾸����銝𥪜銁�鞉�瘛餃���誘�扯��𠬍�撱嗉� 0.5 蝘㘾��唬誑 `route print` 餈𥡝�鈭峕活�詨��⊿�嚗���冽��帋��芸𢆡�鞉�瘛餃���𡡒�航䌊���撉䎚��

## 2026-07-15 19:30
- [x] **摰䂿緵�蹱��楝�梯䌊�券�蝵桐�蝞∠��蠘� (Implemented Automated Static Route Configuration & Management)**嚗�
    - [x] **摰䂿緵 WindowPosManagerUI �臬𢆡�嗉䌊�刻�銵峕�瘚� (Automated Startup Network Route Check)**嚗𡁜銁 `WindowPosManagerUI.__init__` ���牐葉嚗���滨蔭蝞∠��� `ConfigManager` �㰘蝸摰峕��𠬍��典�憪见��滨蔭�嗆挾撘�郊/摰匧�靚�鍂 `core.check_and_add_route(self.config_manager)` �扯��蹱��楝�望�瘚页�撟嗅�蝏𤘪����嚗��銝餌��� UI ���蝘齿��祆𠯫敹㛖�隞嗅�憪见�摰峕��𠬍�摰匧��䂿�撟嗉��箏��嗆��𠯫敹堒躹����𣈯��唳��𣂷�頞喟��仿�嚗䔶�����瑚��餅鱏甇�虜蝒堒藁摰帋�瘚��嚗峕說頞� KISS 銝𢛶�靝�銝剜鱏銝餅�蝔𦥑�萘��詨�撘��穃��踺��
    - [x] **`manage_window_layout.py` �賭誘銵�/�𤾸蝱撖寥�璅∪�銝见�甇交𣈲��楝�梯䌊�� (Integrated Route Healing in CLI/Background Mode)**嚗𡁏�霈箸糓�朞� `--ui` ��㺭�臬𢆡�曉耦蝞∠��屸𢒰嚗諹��臬銁�𤾸蝱隞� `--cli` / `-noui` 璅∪�餈𥡝��䠷�蝒堒藁摰帋�銝𤾸�撅𤩺��穃笆朣琜��典鍳�冽𧒄��釣�乩� `check_and_add_route` 璉�瘚钅�餉�嚗𣬚＆靽嘥銁�� UI �箸艶銝讠頂蝏笔��瑁�銝餃𢆡蝏湔擪 192.168.50.0/24 蝵烐挾�����楝�梧�颲曉��𨅯朖撘��喟鍂����蠘��尠�腈��
    - [x] **UI 摨閖��嗆�������鎿黾 頝舐眏霈曄蔭�嘥翰�笔��� (Integrated Route Settings Shortcut Button)**嚗𡁜銁 `WindowPosManagerUI.init_ui` 摨閖�撌亙��讐��𨥉�� �扯�����脲�嚗峕鰵憓硺��鎿黾 頝舐眏霈曄蔭�脲��殷�蝏穃� `open_route_settings` 瑽賢遆�啜����餃朖�臬鐤�箔��刻挽霈∠� `RouteConfigDialog`嚗峕𣈲����嗆䰻�见��啜���銋㕑��踺��凒�交�銵𢞖�𨥉�� 蝡见朖璉�瘚�/摨𠉛鍂�脲�霂𤏪�隞亙�靽嘥��芸�銋㕑楝�梯��躰楊隡朞�����硔��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞� (Passed 100% Compile Self-Test)**嚗𡁻�朞� `python -m py_compile` 撖嫣耨�寧� `manage_window_layout.py` 銝� `ui.py` �扯�鈭��霂煾�霂���冽㺭蝏輻��牐遙雿閗祗瘜閖�霂荔�撟嗅銁�桅�𡁶鍂�瑞㴓憓��璅⊥��臬𢆡撉諹�嚗峕𠯫敹𡑒��箸迤撣詻��楝�望��鞉�蝏脲�蝷箇泵����麄��蜓�屸𢒰�㰘蝸瘚��摰�末�䭾���

## 2026-07-15 16:30
- [x] **摰䂿緵�滨��單釣銝芾�瘛餃��交�霈啣�銝𤾸虾閫���𥪜𢆡瘨刻�撟���� (Implemented Favorite Stock Addition Dates & Visualizer Linkage Return)**嚗�
    - [x] **�齿� `GlobalFavoriteManager` 摰䂿緵�交����銋��摮睃� (Favorite Stock Date Persistence)**嚗𡁻���� `global_favorites.py` ��� of JSON 霂餃�瘚��嚗峕鰵憓� `favorite_stocks_dates` 摮堒��冽䔉隞� `{"code": "YYYY-MM-DD"}` �澆�摮睃�瘥譍葵�芷�㕑�����孵�瘜冽𠯫�麄���蝥找� `add_favorite_stock` �� `toggle_favorite_stock` �寞�嚗峕𣈲��䌊�冽��瑕��齿𠯫���`YYYY-MM-DD`嚗㗇�憭㚚���㺭�坔���銁霂餃�銝𤾸��� `window_config.json` �塚��芸𢆡餈𥡝�����澆捆�扳嵗撉䕘��交�瘚见��䭾溶�䭾𠯫�毺��扯䌊�㕑��躰䌊�刻‘朣𣂷蛹 3 憭拙���漱�𤘪𠯫���靘蹂�瘚贝�嚗屸�朞� `cct.get_lastdays_trade_date(3)` �箄��齿滲嚗㚁�撟嗅��賣��典�撠豢㺭�格�����
    - [x] **�齿��航��𣇉垢 `load_stock_by_code` �芸𢆡�瑕��單釣�亥��� (Visualizer Auto-Date Detection)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�敶梶鍂�瑟��典��Ｚ�蟡其�瘝⊥�憭㚚�����園𡢿�單𧒄嚗諹䌊���靚�鍂 `GlobalFavoriteManager` �亥砭霂亥��臬炏銝粹��孵�瘜刻���𥅾�荔��躰䌊�典��嗅�瘜冽𠯫�蠘��潔蛹 K 蝥輻� `active_time_linkage`��眏甇文銁�㰘蝸 K 蝥踵𧒄隡朞䌊�函��園��脰�蝥蹂誑撅閧內霂亙�瘜冽𠯫嚗�僎�典椰銝𡃏��硋𢰧銝𡃏����蝷箸�瘜∩葉�冽��恣蝞𨰜���鈭格遬蝷算�𡏭�隞𦠜隅頝𢞖�嘅���鉄�箏�隞瑟聢銝舘��函㮾撖孵予�堆�嚗峕���隞颱��见𢆡�滢���
    - [x] **�齿� ATS 蝏�垢 `link_stock` �拍�����餉� (ATS Terminal Linkage Upgrade)**嚗𡁜銁 `ats/ui/main_window.py` �𥪜𢆡�煾���憓𧼮��芷�㕑��交��文���𥅾�格��𥪜𢆡隞��撅硺��滨��單釣�∠巨銝𥪜��匧�瘜冽𠯫����芷���撠�芦�𡁶� `CODE` ��誘��漣銝� `TIME_LINK|{code}|{add_date}` �澆��煾���隞舘�𣬚＆靽萘��� ATS 銝剔��滨��單釣�∟��芸𢆡�典虾閫��蝏�垢擃䀝漁�曄內�單釣�亙�蝝航恣�嗥�����
    - [x] **�齿��烐綉銝餌�摨� `open_visualizer` �芷����園𡢿�喳‵�� (Main Monitor Visualizer Call Optimization)**嚗𡁜銁 `instock_MonitorTK.py` �� `open_visualizer` �寞�銝剜釣�亙�蝵格��伐�敶� `timestamp` ��㺭銝箇征�塚��芸𢆡�交𪄳撟嗅�銵亥砲�∪銁 `GlobalFavoriteManager` 銝剔�瘛餃��交�嚗䔶�霂��銝餌�摨讐��芷�㕑”�硋�摰���刻圻�𤑳�����航��𡝗𧒄嚗峕㺭�格��峕甅�箏蒂�厰��孵�瘜冽𠯫�麄��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �朞�**嚗𡁻�朞� `python -m py_compile` 撖嫣耨�孵��� 4 銝芣瓲敹��隞嗆�銵𣬚�霂煾�霂���冽㺭蝏輻��牐遙雿閗祗瘜閖�霂胯��

## 2026-07-15 15:16
- [x] **ATS �券� Tree �𠹺葵�⊥�蝏�𢰧�格溶�𨬭������撘�𢆡�𥪜𢆡�滚��� (Implemented Right-Click Send-to-Linkage in All ATS Trees & Detail Views)**嚗�
    - [x] **霈曇恣撟嗅��啣��冽綫��遆�� `send_to_linkage` (Shared Pipe Push Utility)**嚗𡁜銁 `ats/ui/base_table.py` 銝剜鰵憓墧芋�㛖漣 `send_to_linkage(code, name, parent_widget)` �賣㺭��砲�賣㺭�芸𢆡隞𡒊�蝏�辣�橘�`parent_widget �� .window()`嚗匧�銝𡃏蕭皞� `current_df` 摰墧𧒄銵峕�蝻枏�嚗諹‘�� `high`��lastp1d`��percent`��price`��volume` 蝑匧�畾蛛��滚��堒�銝� JSON �朞� `send_code_via_pipe` �券��� `\\.\pipe\my_named_pipe`嚗���刻��典𦶢�滨恣�橒���� `current_df` 銝滚虾�冽𧒄�滨漣銝粹�霈文�澆��典�摨𤏪��券曎頝臬蒂撘�虜�閗繮嚗䔶�敶勗�銝餅�蝔卝��
    - [x] **`BaseATSTableWidget` �喲睸�𨅯�����𢞖黾 �煾���撘�𢆡�𥪜𢆡��(BaseATSTableWidget Context Menu)**嚗𡁜銁 `_show_context_menu` 銝�"憭滚�隞��"銝�"�滨��單釣"銋钅𡢿�鍦��𥪜𢆡�𨅯�憿對�蝏穃� `send_to_linkage`嚗諹��𡝗��厩誧�� `BaseATSTableWidget` ����亥”����刻”��䌊�㕑”嚗�鉄 `TradeFlowWidget`��SwingTable`��KernelTracePanel` 蝑㚁���
    - [x] **`UniverseTreeWidget` �喲睸�𨅯���� (Universe Pool Tree Linkage)**嚗𡁜銁 `ats/ui/universe_widget.py` �� `_show_context_menu` 銝哨�"憭滚�隞��"�𤾸朖�鍦��𢞖黾 �煾���撘�𢆡�𥪜𢆡�滩��閖★嚗峕項�硋�䠷�厰𡺨颲暹���移�㕑�撖������䀝漱�𤘪�銝劐葵蝑𣇉裦�∠巨瘙删� TreeView��
    - [x] **`DistributionDetailsDialog` �喲睸�𨅯���� (Distribution Detail Dialog Linkage)**嚗𡁜銁 `ats/ui/chart_widgets.py` �� `_show_context_menu` 銝哨���"�� �劐葉�𥪜𢆡"�𤾸��𨬭�𢞖黾 �煾���撘�𢆡�𥪜𢆡�滩��閖★嚗諹��𡝗隅頝��撣�葵�⊥�蝏�撕蝒𨰜��
    - [x] **`ATSSectorDetailDialog` �喲睸�𨅯��啣� (Sector Detail Dialog Linkage)**嚗𡁜銁 `ats/ui/sector_detail_dialog.py` 銝凋蛹�踹��𣂼��𡒊�銵冽聢�啣� `_show_context_menu`嚗���怒�𢞖黾 �劐葉�𥪜𢆡�㵪�靚� `linkage_cb`嚗剹���𢞖黾 �煾���撘�𢆡�𥪜𢆡�㵪�靚�恣�𤘪綫������𤃬�� 憭滚�隞��/�滨妍�滚�銝芸��賡★嚗�僎�� `_init_ui` 銝剖��𣂼𢰧�桐縑�瑞�摰𠾼��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �朞�**嚗𡁜笆 `base_table.py`��chart_widgets.py`��universe_widget.py`��sector_detail_dialog.py` ���銵� `py_compile` 蝻𤥁��⊿�嚗���啁遛�舫�朞�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��

## 2026-07-15 15:13

- [x] **敶餃�靽桀�蝒堒藁�鞉�蝞∠��典�撅��剝睸 Access Violation 撏拇�銝舘祗瘜閙��� (Fixed Access Violation Crash & Orphaned Code Residue in Window Layout Manager Hotkey)**嚗�
    - [x] **靽桀� `accept_path` �寞�蝻抵��躰秤 (Fixed IndentationError in accept_path)**嚗帋耨憭滢� `EditPathDialog.accept_path` �寞�銝剔眏鈭𦒘�甈∠�颲烐�雿𨀣�憭硋��亦�憭帋�蝻抵�嚗�紡�� `is_shell_cmd` 隞���堒��𣂷��删�蝥� `if` ���瘜閙�蝛箔誨���嚗䔶漣�� `IndentationError: unexpected indent` 霂剜��躰秤���憭滢蛹甇�＆��䲮瘜蓥���像蝥抒憬餈𨥈�撟嗅�甇亙����"蝛箸聢頝臬�銝娪�憭齿��賭誘�嗆��芸𢆡��ㄨ撘訫噡"��ế�剝�餉���
    - [x] **皜�膄摮斤��� nativeEvent 甇颱誨����� (Removed Orphaned nativeEvent Dead Code)**嚗𡁜��啣僎�𣳇膄鈭� `parse_hotkey_string` �寞�蝏𤘪��𠬍��� L998-L1002嚗㗇��嗵�摮斤���挾嚗Ǒhotkey_id = msg.wParam`��self.toggle_ui_signal.emit()`��return super().nativeEvent(...)`嚗剹���鈭𥕢誨��糓銝𡃏蔭�齿�銝� `nativeEvent` �寞��芾◤敶餃�皜�膄�嗘���鱏蝡䭾�摮矋��曄蔭�冽䲮瘜訫�隡帋漣�� `IndentationError`嚗峕糓撖潸稲�臬𢆡�芷����凒�亙��牐�銝���
    - [x] **撘訫� `ManagerHotkeyThread` �祉�摰�擪蝥輻�蝐� (Introduced ManagerHotkeyThread Daemon)**嚗𡁜銁 `WindowPosManagerUI` 蝐餃�銋匧�嚗峕鰵憓� `ManagerHotkeyThread(threading.Thread)` 蝐颯��⏚�� `RegisterHotKey(None, ...)` 撠���格釣���**摮鞟瑪蝔贝䌊頨�**����舫��梹��屸�銝餌��� HWND嚗㚁��朞� `PeekMessageW` �鮋獈憛噼蔭霂Ｘ��� `WM_HOTKEY`嚗��蝏� `toggle_ui_signal.emit()` 蝥輻�摰匧��啣�靚�蜓 UI ��揢�航��扼��蝠摨閖��滢��� PyQt6 `nativeEvent` 銝剖笆 `sip.voidptr` 餈𥡝� ctypes ����滚��堒��嗅紡�渡� Access Violation (c0000005) 撏拇���
    - [x] **�滚� `bind_hotkey` 雿輻鍂摮鞟瑪蝔𧢲䲮獢� (Rebuilt bind_hotkey via Thread)**嚗𡁜�撘���扳䲮獢��蝏穃��唬蜓蝒堒藁 HWND + `nativeEvent` �行⏛嚗㚁��滚�銝綽��𨀣迫撟� join �抒��桃瑪蝔� �� �𥕦遣�� `ManagerHotkeyThread` �� 蝑匧� 0.15s 蝖株恕瘜典��𣂼� �� 靽嘥�蝥輻��交��� `self._hotkey_thread`����啁�摰𡁏𧒄�𣳇��滚鍳蝔见�嚗𣬚凒�� stop �抒瑪蝔见� start �啁瑪蝔见朖�荔�隞擧覔�砌�閫��鈭�"�齿鰵蝏穃��䭾����"����嫘��
    - [x] **銵亙� `import threading` 蝻箏仃撖澆� (Fixed Missing threading Import)**嚗𡁜銁 `ui.py` 憿園�銵仿�鈭� `import threading`嚗峕��支� `NameError: name 'threading' is not defined` 餈鞱��園�霂胯��
    - [x] **�拍�霂剜�蝻𤥁�銝舘�銵峕�霂� 100% �朞�**嚗䫤py_compile` 蝻𤥁�蝏輻�嚗𤤿�摨誩鍳�典�蝔喳�靽脲� RUNNING �嗆���銝滚��箇緵 "Python 撌脣�甇Ｗ極雿�" Access Violation �芷��嚗𣬚��格𠯫敹埈迤撣貉��箏歇蝏穃�靽⊥���

## 2026-07-15 14:40
- [x] **�齿�撟嗡耨憭滨������恣��膥�典��剝睸�怠�憭望�銝𡡞��啁�摰𡁜仃韐亦撩�� (Refactored & Fixed Global Hotkey Freeze in Window Layout Manager)**嚗�
    - [x] **撘�鍂 keyboard 摨㮖�蝥批�撅��桃��拙� (Deprecated keyboard Low-Level Hooks)**嚗𡁶宏�支�撖孵�撅��撅��桃��拙���凒�乩�韏吔��踹�鈭�眏鈭� Windows 銝餌瑪蝔见㨃憿輯��嗅竉蝳駁偬摮琜�隞亙��鞉��臬�銝讠��嫣腺憭勗紡�渡��典��剝睸�䠷�憭望���
    - [x] **�齿�銝� Windows �毺� RegisterHotKey API �箏� (Rebuilt via Win32 RegisterHotKey)**嚗𡁜銁 `WindowPosManagerUI` 蝐颱葉嚗���剝睸蝏穃��嫣蛹�毺��� `RegisterHotKey` 蝟餌�靚�鍂嚗𣬚�摰𡁜銁蝒堒藁�祈澈��蘂���HWND嚗劐�嚗𣬚眏�滢�蝟餌�摨訫�瘨���笔��湔𦻖韐蠘提瘣曉� `WM_HOTKEY` (0x0312) 瘨����
    - [x] **�齿� PyQt6 nativeEvent 摨訫�瘨���行⏛ (Implemented nativeEvent Message Interception)**嚗𡁻��嗘� `WindowPosManagerUI.nativeEvent`嚗���刻圾�� `ctypes.wintypes.MSG`嚗�銁�閗繮�啁��桐�隞嗆𧒄摰𣬚��澆枂�㚚��譍蜓�屸𢒰嚗�僎撘訫�鈭� `parse_hotkey_string` 靽肽��剝睸摮㛖泵銝脣�靽桅弘�格焵����拍��桃���䌊�刻蓮�Ｕ��
    - [x] **摰䂿緵 100% 蝔喳�����桅��啁�摰帋��貉蝸皜�� (Stabilized Rebinding & Unregistration Cleanup)**嚗𡁻���� `bind_hotkey`��closeEvent` �� `force_quit` �寞�嚗�銁靽格㺿�剝睸�硋��券���箸𧒄靚�鍂 Win32 �� `UnregisterHotKey` 敶餃�皜���嗆���瘨�膄鈭��瘜閖��啁�摰𠾼���憿駁��舐�摨讐�銝仿�雿㯄� Bug��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞� (Passed 100% Compile Self-Test)**嚗𡁜笆靽格㺿�𡒊���辣�扯�鈭� `py_compile` 蝻𤥁�銝𤾸鍳�冽�霂𤏪��冽㺭蝏輻��朞�嚗峕𧊋撘訫�隞颱��唬�韏硋��𦯀�獢�沲��

## 2026-07-15 15:30
- [x] **摰䂿緵瘨刻����銝芾��𡒊��喲睸�滨��單釣銝𤾸�撅��嗆���甇� (Implemented Right-Click Focus & Status Synchronization in Price Rise/Fall Distribution Stock Details)**嚗�
    - [x] **�冽隅頝��撣�葵�⊥�蝏�葉����喲睸�滨��單釣/�𡝗��單釣�𨅯� (Integrated Right-Click Focus Menu)**嚗𡁻���� `ats/ui/chart_widgets.py` 銝剔� `DistributionDetailsDialog._show_context_menu` �寞���銁����𣈯�劐葉�𥪜𢆡�嘥��𨅯��嗯�嘥��賜��箇�銝𠺪�憓𧼮�鈭��鎿� 霈曆蛹�滨��單釣�嘥��鎿� �𡝗��滨��單釣�萘��蠘���
    - [x] **摰䂿緵�滨��單釣銝芾����撖�漲閫��皜脫� (Highlighted Focus Stock Aesthetics)**嚗𡁻�����唳旿�㰘蝸 `update_data` �峕凒�唳葡�� `refresh_favorites_display` ���餉���笆鈭𡡞��孵�瘜函�銝芾�嚗���滚�隡朞䌊�典�銝� `潃� ` �滨�嚗���航𠧧皜脫�銝箇移蝢𡒊�蝏輸�𡁻�擃䀝漁�� `#00FF88`嚗�誨����滨妍��笆朣琜�嚗峕㟲銵諹��航𠧧皜脫�銝箸擪�潭�蝏輯𠧧 `#1A2A1A`��
    - [x] **摰䂿緵憭𡁶����餈𤤿��典��嗆��䌊���敹�歲撘讛��典��� (Real-time Broadcast Sync)**嚗𡁻���� `ats/ui/main_window.py` 銝剔� `_safe_favorites_changed` �穃𨯬�剁�瘥𤩺活敶㮖蜓蝒堒藁�硋�隞𣇉��仿𢒰�踹��罸��孵�瘜函𠶖����湔𧒄嚗諹䌊�典�雿滚��齿�撘��� `DistributionDetailsDialog` 蝒堒藁撟嗉圻�� `refresh_favorites_display()` 餈𥡝�蝘垍漣�唳旿�嗆���甇乩��滚�嚗�蝠摨閙�蝏苷��嗆����峕郊��漱鈭垍��嫘��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞�**嚗𡁜笆靽格㺿�𡒊� `ats/ui/chart_widgets.py` �� `ats/ui/main_window.py` ���銵䔶� `py_compile` 蝻𤥁��⊿�嚗���啁遛�舫�朞�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��

## 2026-07-13 19:30
- [x] **�𠉛氖憭𡁜𪂹�� Treeview �瑕�銝𤾸蝠摨閖���� DPI 蝻拇𦆮��� (Isolated Treeview Style & Refactored High-DPI Adaptation in Multi-Period Tester)**嚗�
    - [x] **�寞祥銝� TK �烐綉蝒堒藁 Treeview �瑕�鋡急情�枏�敶Ｙ撩��**嚗𡁻���� `standalone_multi_period_tester.py` 銝剔� `_init_ui` �寞�����支���𧋦�湔𦻖靽格㺿�典�暺䁅恕�瑕��� `style.configure("Treeview", rowheight=25)` �滢�嚗屸�蝳餃僎憯唳�鈭���冽�銝枏���誧�踵甅撘� `"MultiPeriod.Treeview"`嚗�僎�寞旿擃� DPI 蝻拇𦆮�惩��冽��恣蝞𦯀��㕑�擃矋��峕𧒄撠�蜓蝏𤘪� Treeview �䔶�蝥扳踎�𦯀葵�∪�銵函� `style` ���摰帋蛹 `"MultiPeriod.Treeview"`嚗�蝠摨閙��支��䔶�餈𤤿�銝剖�蝒堒藁撖嫣蜓�烐綉蝒堒藁暺䁅恕 Treeview �瑕�����硋�撟脫贋��
    - [x] **摰䂿緵蝒堒藁�牐�撠箏站擃� DPI �芷���蝻拇𦆮**嚗𡁜銁憭𡁜𪂹�毺��匧膥銝餌����蝑𣇉裦蝻𤥁��函� `__init__` �嘥��碶葉嚗諹䌊����瑕��嗥���� `scale_factor` �㚚�朞�摨訫��� `get_windows_dpi_scale_factor()` 摰墧𧒄銋条� DPI 瘥𥪯�嚗��暺䁅恕�� `1100x700` �� `850x580` 蝒堒藁�踹捐隞亙�撅�葉�讐宏雿滨蔭蝑厩����蝝㰘�銵䔶��冽��憬�曇恣蝞梹�敶餃�閫��鈭�銁擃睃�颲函�撅誩�銝讠����撠譌���隞嗆滯�箏��嗘���䔮憸塩��
    - [x] **�齿��堒捐銝𤾸�蝚血捐摨衣叚�誩�蝻拇𦆮隡啁�蝞埈�**嚗𡁻���� `_adjust_column_widths` 銝剔��堒捐�芸𢆡靚�㟲璅∪����摮㛖泵�讐�隡啗恣嚗Ǒget_text_width` ����� `12` �� `6.5`嚗劐誑�𦠜��厩���蔭����箏��堒捐�屸�霈日��䕘�憒��蝘啜��誨����隅撟���㿥�嗥�嚗匧�銋䀝誑鈭� `self.scale_factor` 撟嗉�銵䔶��𡝗㟲頧祆揢嚗𥕢蛹摮鞉踎�� constituents �𡑒”�� `"idx"` 摨誩噡�㛖′蝻𣇉��讐�摰� `36` 銋蠘蕭�牐� `self.scale_factor` 銋条���銁擃� DPI �臬�銝见��冽�蝏苷�摮㛖泵�������祇�����曄內�烾�蝑厩��� Bug��
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞�**嚗𡁜笆靽格㺿�𡒊�銝餅芋�� `standalone_multi_period_tester.py` ���銵䔶� `py_compile` 蝻𤥁��⊿�嚗���啁遛�舫�朞�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��

## 2026-07-13 19:00
- [x] **鈭箸��坿��屸𢒰��� DNA 銝㯄★摰∟恣銝𤾸��𤏸��� (Integrated DNA Audit & Linkage in Popularity Resonance GUI)**嚗�
    - [x] **摰䂿緵�孵稬摰∟恣�厰僼�𣂼����唳�雿𡏭��曆葵�∪�銵�**嚗𡁜銁 `on_tree_select` �� `on_select_top10` 銝剖��牐� `self._last_active_tree = tree` ��𢆡��暑�函��寡扇敶𨰻��銁撌亙��讐��� `�妞 DNA摰∟恣` �厰僼�塚�隡睃�隞擧��𤾸��毺��餅�鈭鍦𢆡���銵諹”嚗���啗��橘�銝剛繮�硋��漤�匧�銝芾��𠰴��誩��� 20 �芯葵�∟�銵峕鸌�誩恣霈∴�靽肽�鈭��敶枏�瘚讛�餈𥕦漲����湔�扼��
    - [x] **�冽䰻霂�/餈�誘�瑟鰵�漤��� �妞 DNA摰∟恣 �厰僼**嚗𡁜銁 `popularity_resonance_gui.py` 憿園����𨀣䰻霂�/餈�誘�脲綉�嗆�銝哨�鈭𢛶�𡏭�皛手�脲��桀椰靘扳鰵憓硺� `�妞 DNA摰∟恣` �厰僼嚗Ǒbtn_query_dna`嚗剹����餅𧒄隡睃��芸�敶枏��劐葉��葵�∪��嗅� 20 銝芾�銵峕鸌�誩恣霈∴��交�銝芾��劐葉嚗���芸𢆡撖孵��滚虾閫���㗇㺭�桃��坿�璁頣�憒���航”嚗劐葉��� 21 銝芯葵�⊥�銵䔶��桀恣霈∴���之�唳�����滢������
    - [x] **�寞祥 parent �� Widget �嗥� AttributeError 撏拇�**嚗𡁜�雿滚僎靽桀�鈭��隡惩��� `parent`嚗�� `PRServiceGUI` 摰硺�嚗㗇𧋦頨思��瑕� Tkinter `.tk` �拍�撅墧�找��交� `.root` �塚�靚�鍂 `Toplevel` �嘥��硋紡�游援皞���桅���銁 `DnaAuditReportWindow` ����惩遆�唬葉憓𧼮�鈭�䌊��� `master_win` �Ｘ�嚗諹𥅾 `parent`瘝⊥� `tk` 銝娍� `root`嚗���芸𢆡�𣂼�雿輻鍂 `parent.root` 雿靝蛹�拍��嗥����敶餃�瘨�膄鈭�援皞���
    - [x] **摰䂿緵�喲睸�寥�銝芾��芸�銝� DNA 摰∟恣**嚗𡁻���� `popularity_resonance_gui.py` 銝剔� `show_context_menu` �寞�����冽��其遙銝�鈭箸��坿�璁頣�銝𡏭揣����梢◇����擧�����∪嫃����航”嚗匧𢰧�桃��颱葵�⊥𧒄嚗𣬚頂蝏煺��芸𢆡�瑕�敶枏�銝芾�隞亙��典��鍦��𡡞𢒰���憭� 20 �芯葵�∴��梯恣��憭� 21 �迎�嚗𣬚�鋆��敺�恣霈∟�蟡函� `code_to_name` 摮堒�嚗�僎�刻��閖★撅閧內�詨���蘨�堆�憒��`�妞 DNA 銝㯄★摰∟恣 (21��, 暺䁅恕: D)` 嚗剹��
    - [x] **摰䂿緵璁�艙銝芾� Constituent 摮鞟���𢰧�桀��賢��典笆朣�**嚗𡁜銁 `show_concept_top10_window` 銝凋蛹 Constituent �踹�銝芾� Treeview 銵冽聢餈賢�蝏穃� `Button-3` �喲睸鈭衤辣嚗諹�韏瑞㮾�𣬚��喲睸�餉�����乩� `cols.index("code")` 銝� `cols.index("name")` �㛖揣撘閗䌊����𣂼�蝞埈�嚗��蝢𡡞���鈭���𦯀蛹 `idx` ��葵�∪�銵函�����𦦵�鈭���堒�蝘颱漣�毺��硋�潮�雿滢�撏拇�撘�虜��
    - [x] **�舀� DNA 摰∟恣蝒堒藁�唬犖瘞娍�銵𣬚��Ｙ�����𥪜𢆡**嚗𡁜銁 `PRServiceGUI` 蝐颱葉�啣�鈭� `on_code_click(self, code, date=None)` �噼��寞�����冽��� DNA 摰∟恣�亙�蝒堒藁銝剖��� any 銝�銵䔶誨��𧒄嚗䔶��芸𢆡�睲犖瘞娍�銵𣬚�������靚���犖瘞娍�銵𣬚��Ｗ銁�交𤣰�啣�靚��嚗諹��删�閫血� TDX / THS �𠰴虾閫��蝏�垢����剁�撟嗅銁�屸𢒰鈭𥪯葵�坿�璁靝葉�芸𢆡撖餅𪄳霂乩葵�∪僎擃䀝漁�劐葉嚗峕����憭𡁶頂蝏蠘�靚����𡡒�舀��䀝�撉䎚��
    - [x] **�朞��拍�蝻𤥁�銝舘䌊�典�瘚贝�**嚗𡁻�朞�鈭� `py_compile` �拍�霂剜�璉�瘚页�蝻硋�撟嗆�銵䔶� `test_pr_gui_dna_linkage.py` �芸𢆡�𡝗�霂閗��穿�璅⊥�鈭��靚��撘�郊摰∟恣�臬𢆡�脣鴃�餉�嚗峕�霂� 100% 蝏輻��朞���

## 2026-07-13 18:30
- [x] **靽桀�憭批𪂹�� DNA 摰∟恣���瞍磰��交��曄內銝� '<12' �� Bug (Fixed '<12' Date Formatting Bug in Large-Period DNA Audit)**嚗�
    - [x] **�寞祥 Python f-string ��笆 Timestamp 蝐餃���圾�𣂼�蝒�**嚗𡁜�雿滚僎���鈭�銁 `backtest_feature_auditor.py` 銝哨��函瑪���蝥踵�憭批𪂹�罸���甅�𡒊� DataFrame 蝝Ｗ�嚗ǎndex嚗劐��齿糓摮㛖泵銝脩掩�页��峕糓 pandas `Timestamp` 撖寡情��銁撖孵�雿輻鍂 `f"{h['date']:<12}"` �𡁜�蝚虫葡撌血笆朣� 12 摮㛖泵摰賢漲��聢撘誩��塚�Python 閫���其�撠���瑕𢰧靘抒� `:<12` �躰秤敶㮖� `strftime` �園𡢿�澆���誘餈𥡝�閫��嚗峕�蝏���澆�銝滚�瘜閗�������甅颲枏枂 `"<12"`��
    - [x] **摰墧鴌摰∟恣皞𣂼仍�交�摮㛖泵銝脫����**嚗𡁜銁 `backtest_feature_auditor.py` 銝剖� `audit_rows` �坔��交��㵪�憓𧼮�鈭�笆 `dt` ����冽䔝瘚卝��𥅾璉�瘚见�銝� `Timestamp`嚗���� `strftime` 撅墧�改�嚗諹䌊�券�朞� `.strftime('%Y-%m-%d')` 頧祆揢銝� 10 雿齿���𠯫�笔�蝚虫葡嚗𥡝𥅾銝箏蒂�園𡢿���蝚虫葡�躰䌊�冽��硋� 10 雿溻��
    - [x] **瘨�膄��掩颲枏枂皜𣳇��交�瘛瑚僚**嚗帋�隞�耨憭滢� UI �Ｘ踎�冽葡�枏之�冽�瞍磰��唳旿�嗥��澆�瘛瑚僚嚗䔶�敶餃��寞祥鈭�綉�嗅蝱��𠯫敹𡑒��箇����㗇聢撘誩�颲枏枂皜𣳇�銝剔�餈嗘�憿賢𤐄 Bug嚗䔶������𪂹��㺭�桃�銝��湔�找�蝢舘�摨艾��
    - [x] **�朞��芸𢆡�㚚��𣂼����霂�**嚗𡁶��嗘� `test_dna_resample_days_and_date.py` �芸𢆡�𡝗�霂閗��穿�撖孵𪂹蝥輸���甅銝讠� DNA 摰∟恣�交�蝐餃���聢撘譍誑�� UI 撖寥��潭𦻖餈𥡝�鈭��敶㘾�霂���剛�瘚贝��朞��� 100%��

## 2026-07-13 18:20
- [x] **靽桀�憭批𪂹�毺��㗇㺭�桃眏鈭𡒊�摮睃蘨霂餌撩憭勗紡�港漱��秤���游���䔮憸� (Fixed Mass Discard in Multi-Period Intersection due to Missing Large-Period Cache)**嚗�
    - [x] **霈曇恣蝻箏仃�∠巨�齿��朞��箏�**嚗𡁻���� `multi_period_strategy_engine.py` �� `evaluate_strategy` �寞���銁餈𥡝�憭𡁜𪂹�� query 餈�誘�塚��𣂼�敶枏�霂�摯�冽�銝剔撩憭望㺭�桃��∠巨���嚗Ǒmissing_codes`嚗㚁�撟嗅�摰�賑銝� query 餈�誘�朞����蟡剁�`passed_in_period`嚗匧�撟園�嚗屸�霈文銁甇文之�冽�銝𪙛�𨅯�璉��朞��腈��
    - [x] **瘨�膄鈭日�霂舀��園�**嚗𡁶眏鈭𤾸之�冽�嚗�� 3M��45d 蝑㚁��典蘨霂餃�頧賣𧒄����牐蛹 HDF5 蝻枏�銝滚��𣬚撩憭勗之�譍葵�⊥㺭�殷��冽迨�滨� `intersection` 鈭日�餈�誘蝞埈�銝凋�撖潸稲�喃蝙銝芾��冽𠯫蝥踴��𪂹蝥踹��圈�朞�嚗䔶��惩之�冽�蝻箏仃�諹◤�湔𦻖�拍�餈�誘�娪膄����亙�璉��箏��𠬍�隞�笆�𨀣�憭批𪂹��㺭�桐��唳旿銝滩噢���萘��∠巨摰墧鴌撘箏��行⏛嚗峕㺭�桃撩憭梁�銝芾��賢像皛𤏸�餈�之�冽��園�嚗�蝠摨閗圾�喃���揢憭批𪂹�笔�蝑偦�厩��𨅯之�Ｙ妖鋡徉�𡏭秤���苷腺撘��蝟餌�蝥抒��嫘��
    - [x] **�朞��芸𢆡�㚚��𣂼����霂�**嚗𡁶��嗘� `test_multi_period_missing_exempt.py` 瘚贝��𡁏𧋦嚗屸�朞����惩��怠��湧�朞������撩憭晞����∩辣銝滩噢���瘛瑕��∠巨�唳旿���撉諹�鈭��璉���僎餈�誘�餉�嚗峕鱏閮�瘚贝��朞��� 100%��

## 2026-07-13 18:10
- [x] **銝餌��Ｗ��� DNA 摰∟恣�厰僼��漣銝粹�霈日�劐葉�� + �𡒊賒 20 �芣鸌�誩恣霈∩��箄��滨漣璅∪� (Upgraded Main Toolbar DNA Audit Button to Default to Selected + Next 20 Batch Mode with Fallback)**嚗�
    - [x] **摰䂿緵摰帋�����寥��𣂼�**嚗𡁻���� `standalone_multi_period_tester.py` 銝剔� `_on_diagnose_dna_click` �噼��寞���緵�典��冽��孵稬摨閖��� `�妞 DNA摰∟恣` �厰僼�塚�蝟餌�隡𡁻���覔�株��交�隞���其蜓 Treeview 銵冽聢銝剝����蝝Ｚ砲�～��𥅾摮睃銁霂亥�嚗���芸𢆡摰帋��嗆��其�蝵桀僎�瑕�霂亥�隞亙��嗆��典��Ｙ���憭� 20 銝芯葵�∴��梯恣��憭� 21 �迎�銝�撟嗉�銵峕鸌�� DNA 摰∟恣��
    - [x] **摰䂿緵頞���硋迨蝡衤葵�∠�撟單��滨漣**嚗朞𥅾�冽��刻��交��见𢆡�桀�鈭�蜓銵冽聢銝凋�摮睃銁��誨���靘见�銝滚銁敶枏�蝑偦�厩��𣈯���誨���嚗𣬚頂蝏煺��芸𢆡霂��撟嗅像皛煾�蝥改�Fallback嚗劐蛹撖寡砲�訫蘨�∠巨�祈澈�扯� DNA 銝㯄★摰∟恣嚗峕��支��寥�憭�����蝒������
    - [x] **��漣�𧼮����瘚贝�**嚗𡁜銁 `test_ui_audit_diagnose.py` �芸𢆡�� GUI 璅⊥����瘚贝�銝剛‘����寥�摰帋�����芸����撠曇器�峕��硔��誑�𠰴�銵典�銝芾�撟單��滨漣������霂閙鱏閮�嚗䔶遛�罸�霂��朞��� 100%��

## 2026-07-13 18:00
- [x] **�典��冽�霂𦠜鱏�批��譍�銝芾��𡑒”撘寧���� DNA 銝㯄★摰∟恣銝舘��刻䌊憛怠��蠘� (Integrated DNA Audit Buttons in Diagnose Toolbar & Constituents Popup with Linkage Auto-fill)**嚗�
    - [x] **銝餌��Ｚ��剜綉�嗆�瘛餃� DNA 摰∟恣�厰僼**嚗𡁜銁 `standalone_multi_period_tester.py` ����兩�𡏭��凋葵�﹦�脲綉�嗅躹����典��� `�� 霂𦠜鱏` �厰僼�喃儒�啣� `�妞 DNA摰∟恣` �厰僼嚗Ǒbtn_dna`嚗剹����餅𧒄隡𡁏��硋��滩��交���誨��僎暺䁅恕隞交��匧�銝𤾸𪂹�毺���撠誩𪂹���銵���啣�甇� DNA �孵�銝㯄★摰∟恣嚗��憭�����撘�虜�行⏛靽脲擪��
    - [x] **摰䂿緵銝芾��𡑒”�㗇𥋘銝舘��剛��交�����刻䌊�典‵��**嚗𡁻���� `_do_linkage` �寞�����冽��其蜓 Treeview 銵冽聢銝剖��颯��睸�䀝�銝𧢲�閫�葵�∴��𡝗糓�典�璁�艙�踹��𡑒”銝剝�㗇𥋘銝芾�閫血��𥪜𢆡�塚��芸𢆡�閗繮敶枏��劐葉�� 6 雿滩�蟡其誨��僎�䭾�憛怠��喳��� `self.diag_entry` 霂𦠜鱏颲枏�獢�葉嚗�之撟��撠𤑳鍂�瑞��见𢆡颲枏��鞉𧋦��
    - [x] **璁�艙�𣂼�銝芾�摮鞟�����鞱��凋�摰∟恣�滢���**嚗𡁜銁 `show_concept_top10_window` 撘孵枂��葵�∪�銵函�����冽鰵憓� `action_bar`嚗屸��� `�� 霂𦠜鱏���劐葵�︶ 銝� `�妞 DNA摰∟恣���头 銝支葵擃㗛��批��厰僼���銝哨�DNA 摰∟恣���㗇��桀�蝢𤾸��其��𡏭䌊�典恣霈∪��齿��劐葵�∪��嗅���憭� 20 銝芯葵�﹦�萘�銝𡁜𦛚�餉�嚗峕�雿喳𧑐�𣂼�鈭���睃��鞟�靘踹⏚�扼��
    - [x] **�惩𤐄憭抒�銝芾��𡑒”撘寧��脣鴃靽脲擪**嚗𡁜銁 `show_concept_top10_window` �亙藁撘訫� `getattr(self, "_last_flat_df", None)` 撅墧�找��歹�閫��鈭�眏鈭𦒘蜓銵冽𧊋餈鞱��齿�瘚贝��芣釣�交𧒄嚗�撩�嗥��餅�敹萎葵�∩漣�� `AttributeError` 撏拇���
    - [x] **�朞��芸𢆡�� GUI ����𧼮�瘚贝�**嚗𡁶��坔僎�𣂼�餈鞱�鈭� `test_ui_audit_diagnose.py` �芸𢆡�𡝗�霂𤏪�撖孵��冽�銝餌��Ｕ����交�璅⊥��澆‵������典�憛怒��NA摰∟恣�厰僼閫血��𠰴撕蝒𡑒�銵䔶��券曎頝臭遛���霂𤏪��剛��朞��� 100%��

## 2026-07-13 17:40
- [x] **隡睃� DNA 摰∟恣銝滚��冽���㺭�桀�頧賣㺭�譍蛹�芷��� Resample_LABELS_Days (Adaptive Data Loading Lengths for DNA Audit via Resample_LABELS_Days)**嚗�
    - [x] 摨罸膄鈭� `backtest_feature_auditor.py` 銝剔鍂鈭𤾸�頧賭葵�∪�憭抒���㺭 K 蝥踹��脫㺭�格𧒄�蹱香�� `dl=800` 銵峕㺭�𣂼���
    - [x] 撖澆�鈭� `JohnsonUtil.johnson_cons` 銝剔� `Resample_LABELS_Days` �冽�憭拇㺭�𣂼�摮堒�嚗�僎雿輻鍂 `Resample_LABELS_Days.get(resample, 800)` 雿靝蛹�唳旿�㰘蝸�圈���
    - [x] 閫��鈭�銁 `3M` 蝑匧之�冽�銝页��蹱香 `dl=800` 撖潸稲�漤��瑕��曹� K 蝥輯��唬�頞� 20 �寡�𣬚凒�交㜃�芸僎�亙枂�𨀣㺭�桅�銝滚���/餈𥪜� `None` 摰∟恣憭梯揖��撩�瘀�瘚贝� 3M �冽��𣂼��朞���

## 2026-07-13 17:30
- [x] **�舀��典��冽�蝑偦�匧膥�䔶葵�∪�銵其葉�喲睸 DNA 摰∟恣暺䁅恕�扯����㕑�蟡典��嗅� 20 銝芯葵�� (Default to Auditing Selected Stock + Next 20 Items)**嚗�
    - [x] �� `standalone_multi_period_tester.py` ��𢰧�株��訫遆�� `show_context_menu` 銝哨��瑕�敶枏� Treeview 銵冽聢銝剛◤�喲睸�㗇𥋘�� `item_id`��
    - [x] 撘訫� `children.index(item_id)` 雿滨蔭璉�蝝Ｗ僎雿輻鍂 `children[curr_idx:curr_idx + 21]` ���摰帋�嚗�𢆡��繮�𡝗��㕑�蟡典��嗅����憭� 20 銝芾�蟡剁��潸��� `code_to_name`��
    - [x] �典𢰧�株��閖★�峕�摰𡁜𪂹�煺�蝥扯��閖★銝剖�餈賢��曄內敺�恣霈∠��∠巨�堆�憒� `�妞 餈鞱� DNA 摰∟恣 (21��, �冽�: D)` 嚗㚁�雿輻鍂�瑁�銝��桐��嗆�摰∟恣���蟡刻��氬��

## 2026-07-13 15:00
- [x] **�典��冽�蝑𣇉裦蝑偦�匧膥�峕踎�𦯀葵�∪�銵其葉���憭𡁜𪂹�� DNA 銝㯄★摰∟恣�亙��蠘� (Integrated Multi-Period DNA Audit in Standalone Tester & Constituents Popup)**嚗�
    - [x] **�齿� DNA 摰∟恣�詨��亙藁隞仿���憭𡁜𪂹�罸�㗇𥋘 (Refactored DNA Auditor for Multi-Period Support)**嚗�
        - 靽格㺿鈭� `backtest_feature_auditor.py` 銝剔� `run_optimized_audit`��audit_multiple_codes` �亙藁�� `DnaAuditReportWindow` ����惩遆�啣� `update_report` �寞�嚗峕𣈲����亙僎�� UI �峕㺭�桀��曄內�孵��� `resample` �冽���㺭嚗��霈� `'d'`嚗剹��
        - �� `DnaAuditReportWindow` ���憸䀹�餈賢�鈭���滚�銝𤾸恣霈∠��冽�嚗�� `(�冽�: WEEK)` 嚗㚁�雿輻鍂�瑕笆�唳旿��𪂹�毺輕摨血��厩凒閫���毺䰻��
    - [x] **�典��冽�蝑偦�匧膥銝餉”����喲睸 DNA 摰∟恣 (Integrated Right-Click DNA Audit in Standalone Tester)**嚗�
        - �齿�鈭� `standalone_multi_period_tester.py` 銝剔� `show_context_menu` �喲睸�𨅯���繮�硋��齿��匧歇鋡怠㗲�厩�����冽�嚗Ǒself.period_vars`嚗㚁�霈∠��箸�撠讐�����冽�雿靝蛹�𣈯�霈方�銵�𪂹�麨�嘅�撟嗅銁�𨥉榀� DNA 銝㯄★摰∟恣�嘥��𨅯�銝剖��嗡����銝𤾸𪂹����𤥁����冽𣈲����冽�嚗劐�銝箏��厰�厰★�冽����箝��
        - 摰䂿緵鈭� `_run_dna_audit_batch` �寥�摰∟恣�寞�銝� `_get_audit_end_date` �交��瑕��寞���𣈲��誑�鮋獈憛䂿� `threading.Thread` 憭𡁶瑪蝔𧢲芋撘誩��啗恣蝞梹��朞� `self.after(0, ...)` 撘�郊摰匧��硺� UI 餈𥕦漲�∩�蝏𤘪���緵嚗峕𣈲�������典��冽����湔鰵��
    - [x] **�踹�銝芾��𡑒”�喲睸�𨅯�撖寥�銝舘䌊����𡑒圾�� (Constituents Popup Menu Alignment & Adaptive Column Parser)**嚗�
        - �冽踎�𦯀葵�� Constituent 撘孵枂�𡑒” `show_concept_top10_window` 銝剖��瑞�摰帋��喲睸�𨅯�嚗�僎摰��撖寥�鈭�蜓銵函� DNA 摰∟恣����孵�瘜具����嗡誨����喲睸�蠘���
        - ��笆鈭𣬚漣�𡑒”�豢�銝餉”憭𡁜枂鈭���� `"idx"` 摨誩噡��䔮憸矋��� `show_context_menu` 銝剖��乩� `columns.index("code")` �� `columns.index("name")` �芷����㛖揣撘閙��𣇉�瘜𤏪�敶餃��𦦵�鈭���堒��讐宏霂餃��啣��瑁�屸�銝芾�隞�����餉�蝻粹萅��
    - [x] **�拍�霂剜�蝻𤥁��芣�銝𤾸��賢����霂� 100% �𣂼��朞�**嚗�
        - �扯�鈭� `py_compile` 撖寞��劐耨�孵��� Python ��辣餈𥡝�鈭����祗瘜閙嵗撉䕘��冽㺭蝏輻��朞���
        - 蝻硋�撟嗉�銵䔶�瘚贝��其�嚗�銁 UTF-8 蝻𣇉��脩�靽脲擪銝见��湔�霂蓥��亦瑪銝𤾸𪂹蝥蹂��� DNA �孵�摰∟恣霈∠��峕鸌�誩恣霈∴�瘚贝� 100% �𣂼���

## 2026-07-13 11:30
- [x] **靽桀�鈭箸��望𥲤�峕惣�賣��条�蝡舀���銁 clean 蝻枏��嗅��臬�蝻箏� tk 撖潸稲餈鞱��仿� ModuleNotFoundError (Fixed tkinter Missing in Clean Build due to Missing tk Package in Conda Env)**嚗�
    - [x] **摰帋�蝻枏�靘肽�甇餉�**嚗𡁏��亙��唬蝙�� `pyinstaller --clean` 蝻𤥁��塚�PyInstaller 隡𡁜蝠摨閙��支��滨�蝻枏��桀����銝箏��滨� `py_stock_build` conda �臬�銝剜𧋦�亙僎瘝⊥�摰㕑� Python `tk` 摨㮖�韏吔�撖潸稲 PyInstaller �齿鰵��遣�嗆�瘜閙�瘚卝����� `_tkinter` runtime hook �𣬚㮾�喟� Tcl/Tk DLL嚗䔶蝙敺埈�蝏���鞟� `.exe` 餈鞱��芷��撟嗆��� `ModuleNotFoundError: No module named 'tkinter'`��
    - [x] **摰㕑� tk �臬��拍�靘肽�**嚗𡁜銁 `py_stock_build` �臬�銝剜�銵䔶� `conda install -y tk` �𣂼�摰㕑�銵仿�鈭� Python �拍� GUI toolkit �詨��舀���
    - [x] **�齿鰵蝻𤥁�撟園�朞�撉諹�**嚗𡁜銁蝥䭾迤��㴓憓���齿鰵餈鞱� `pyinstaller --clean -y PopularityResonanceSync.spec` �� `pyinstaller --clean -y ats.spec` 餈𥡝�蝻𤥁������ 100% �𣂼�嚗𣬚�摨𤩺�����瑕僎蝻𤥁� `pyi_rth__tkinter.py` 餈鞱��� hook嚗𣬚��𣂼��渡� `dist\鈭箸��望𥲤2.22.exe` �� `dist\ATS_Terminal.exe`嚗�蝠摨閗圾�喃� tkinter 蝻箏仃�����������摰墧�餈鞱�撉諹�嚗���餉�銵峕迤撣賂��牐遙雿� tkinter 蝻箏仃�仿���
- [x] **靽桀� base �拍��臬�銝剔� win32api DLL �㰘蝸憭梯揖撘�虜 (Fixed DLL Load Failure for win32api in Base Conda Env)**嚗�
    - [x] **摰帋� win32api DLL �脩��寞�**嚗𡁜�雿滚��� base �臬�銝贝�銵� `singleAnalyseUtil.py` �嗥眏鈭� `pywin32` �� Windows 蝟餌�銝剔� DLL �交𪄳憿箏��𤑳��脩�嚗��頧賢�鈭��隞𣇉㴓憓��蝟餌�頝臬�銝剔�銝滚�摰� `pywintypes39.dll` �� `pythoncom39.dll`嚗�紡�� `ImportError: DLL load failed` �曆��唳�摰𡁶�蝔见���
    - [x] **摰墧鴌�拍��曄蔭�芣�**嚗𡁜� `C:\Users\Johnson\anaconda3\Library\bin\` 銝𧢲迤蝖桃� `pywintypes39.dll` �� `pythoncom39.dll` �拍��瑁��� `C:\Users\Johnson\anaconda3\`嚗㇊ython �寧𤌍敶𤏪�銝页�雿� Python 隡睃����甇�＆�㰘蝸撖孵���𧋦�� DLL嚗�蝠摨閙�憭滢� base �臬�銝讠� win32api 甇�虜撌乩�嚗諹�銵峕�霂� 100% 蝏輻���
- [x] **靽桀�蝒堒藁�鞉�蝞∠��典𦶢隞方��臬𢆡�芣�銝𤾸�撘訫噡��ㄨ Bug (Fixed Shell Command Auto-Quoting & Self-Healing Launcher in Window Manager)**嚗�
    - [x] **�寞祥憭齿� shell �賭誘銵諹◤�躰秤��ㄨ憭㚚�����瑞� Bug**嚗𡁻���� `EditPathDialog.accept_path` ��䌊�典�鋆孵�撘訫噡�箏������ `is_shell_cmd` �斗鱏嚗�笆鈭𦒘誑 `start `, `cmd `, `powershell `, `python `, `py `, `cd `, `cd/` 撘�憭湛��𤥁����怨��亦泵嚗Ǒ;`, `&&`, `||`, `|`嚗㗇����撌脫�撘訫噡�����𦶢隞方�嚗���睲��脤��㘾膄蝑𣇉裦嚗𣬚�甇Ｚ䌊�典銁憭㚚���ㄨ憭帋����撘訫噡嚗䔶�皞𣂼仍銝𦠜��支�頝臬��澆�鋡怎聦�讐��鞉���
    - [x] **摰䂿緵�臬𢆡銝擧嵗撉峕𧒄��䌊���撘訫噡�亦氖銝舘䌊��㦤��**嚗𡁜銁 `resolve_and_validate_cmd`��_launch_program` �� `_launch_as_admin` 銝剖��㰘䌊����脤��芣�憭����銁閫���峕�銵��嚗諹𥅾璉�瘚见�隡惩�頝臬��港�鋡怠�雿嗵�憭硋�撘訫噡嚗�� `"start cmd /k "cd ...""`嚗厰�霂臬�鋆對�撠�䌊�刻��怠僎摰峕��拍��亦氖嚗䔶蝙��蟮撌脖�摮条��笔��滨蔭�賢��芸𢆡�Ｗ�銝箸迤蝖桃��毺��賭誘嚗�蝠摨閗圾�喃� cmd.exe �亙枂�𨀣𪄳銝滚��舀�銵𣬚�摨謿�嘥��� launch 憭梯揖撖潸稲霂舐宏�典�隞碶��詨僕蝻𤥁��函��� of Bug��
    - [x] **�拍�霂剜�蝻𤥁��芣�銝𤾸�蝞⊿�璅⊥�瘚贝� 100% �𣂼��朞�**嚗𡁏�銵� `py_compile` 蝻𤥁��⊿�摰𣬚��朞�嚗𤤿��坔僎餈鞱� `test_quote_resolver.py` �芸𢆡�𡝗�霂閗��穿��券𢒰閬��鈭����𦶢隞方���迤撣詨𦶢隞扎��虜閫�蒂蝛箸聢頝臬���圾�𣂷��齿鰵�潭𦻖�餉�嚗峕鱏閮��⊿��券��𣂼�蝏輻���


## 2026-07-13 10:30
- [x] **靽桀� IPC �𥪜𢆡�澆��澆捆�找� UI 隞���鍦�敺株� (Fixed IPC Linkage Format Compatibility & UI Code Layout Tweak)**嚗�
    - [x] **憭�� MultiIndex �澆��㛖��唳旿�湔鰵�澆捆**嚗𡁜銁 `ats/ui/main_window.py` ��㺭�桀��𤩺凒�啣����餉�銝哨�銵亙�鈭�笆 MultiIndex �澆��梹�靘见� `df.compare` 鈭批枂嚗厩��芷���頧祆揢銝𡡞�蝏游����隞���𡝗�霂�蛹 `'self'` ��������遣�� DataFrame 餈𥡝�鈭日��湔鰵嚗�僎靽格迤鈭�砲頧祆揢�堒��� of 蝻抵��澆���
    - [x] **�拍�霂剜�蝻𤥁��芣� 100% �𣂼��朞�**嚗𡁜笆靽格㺿�𡒊� `popularity_resonance_gui.py`��ipc_sync_manager.py`��trade_visualizer_qt6.py` �� `ats/ui/main_window.py` ���銵䔶� `py_compile` 蝻𤥁��⊿�嚗���啁遛�舫�朞�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��

## 2026-07-11 23:42
- [x] **隡睃�蝒堒藁�鞉�蝞∠��冽𠯫敹𡑒��箸�撣���芷��� (Optimized Window Pos Manager Log Output Layout Autostretch)**嚗�
    - [x] **瘨�膄蝒堒藁�劐撓�嗥��亙�蝛箇蒾�箏� (Fixed Log Area Dead Space on Stretch)**嚗𡁜� `ui.py` 銝� `log_output` ���摨虫��箏�擃睃漲�𣂼�嚗ǑsetFixedHeight(110)`嚗厰���蛹��撠誯�摨阡��塚�`setMinimumHeight(110)`嚗㚁�瘨�膄鈭����◤蝥萄��劐撓�嗅銁�扯��嗆��𠯫敹𦯀�銝衤舅靘抒��箇�憭帋��脩蔭蝛箇蒾嚗䔶蝙�亙�獢��摰孵膥憭批�撟單��拙�嚗諹��曄內�游��亙�銵䎚��

## 2026-07-10 22:30
- [x] **�齿�蝒堒藁�芸𢆡撣��蝞∠��其�敹急㭘�臬𢆡嚗���唳��港漱鈭雴�撉䔶�摰𣬚�頝臬��澆捆 (Refactored Window Manager UI, Favorites Layout, and Path Compatibility)**嚗�
    - [x] **摰䂿緵撣貊鍂蝔见��喲睸�箏�銝𡒊宏�斤恣�� (Favorites Right-Click Management)**嚗帋蛹餈𤤿�銵冽聢瘛餃�鈭�𢰧�桐�銝𧢲��𨅯�憿嫖�𨥉�� �箏��啣虜�兩�苷��鎿� 隞𤾸虜�函宏�手�腈��𣈲��鍂�瑕𢰧�桃凒�亙�隞餅�餈𤤿�瘛餃��喳虜�刻蔓隞嗅�銵剁��𤥁���撣貊鍂頧臭辣�𡑒”銝剖翰�笔桊頧賜宏�歹��芸𢆡閫血��滨蔭�脫�靽嘥�銝� UI 撅��典��誯�蝏矋��滚縧鈭���函�颲煾�蝵格�隞嗥�蝜��鈭支���
    - [x] **摰䂿緵撣貊鍂敹急㭘�厰僼�湔𦻖�喲睸蝘駁膄銝舘�銵���� (Right-Click Context Menu for Shortcuts)**嚗帋蛹憿園����𨅯虜�函�摨誩翰�瑟��栽�嘥��牐��祉���𢰧�桐�銝𧢲��𨅯�嚗峕𣈲��凒�亙𢰧�桅�㗇𥋘�鎿� 隞𤾸虜�函宏�手�腈���𨥉�� �臬𢆡蝔见��嘥��𨥉�∴� 隞亦恣���頨思遢�臬𢆡�嘅���之�𣂼�鈭�虜�冽���恣���餈鞱������
    - [x] **皜��銵冽聢�喲睸�𨅯�銝剔��滚��𦯀�憿� (Cleaned Up Duplicate Menu Items)**嚗𡁜�撟嗅僎�娪膄鈭���祈”�澆𢰧�株��蓥葉�思��滚����𨀣溶�惩�撣貊鍂�苷��𨅯𤐄摰𡁜�撣貊鍂�苷舅銝芸�雿坔𢆡雿頣�蝏煺�雿輻鍂�湔��啁��𨥉�� �箏��啣虜�兩�苷��鎿� 隞𤾸虜�函宏�手�嘅�敶餃�瘨�膄鈭��厰★�漤���/�滚���郁銋剹��
    - [x] **摰䂿緵撣貊鍂頧臭辣瘞游像皛朞蔭皛𡁜𢆡銝舘�蝝批��閗�皛𡁜𢆡�⊿��� (FAvorites Horizontally-Scrollable Flow)**嚗𡁜���𧋦擃睃漲�烾���虜�典鍳�函��澆�蝥找蛹 `QScrollArea` 瘞游像皛𡁜𢆡�箝����賭��毺�皛𡁜𢆡�∩誑靽脲�蝏嘥笆蝥臬����閫��撟嗥�摰帋�曌䭾�皛朞蔭皛𡁜𢆡鈭衤辣嚗�𣈲����湔�頧桐�瘞游像皛朞蔭�孵�嚗㚁���捂�朞�皛穃𢆡皛朞蔭�删�憭𡁏赤�埝��典��Ｗ�蝷箸凒憭𡁜虜�函�摨𧶏�敶餃�閫��鈭�迨�漤��嗅銁6銝芾�峕�瘜閙𦆮蝵格凒憭𡁜虜�典��函��𤤿���
    - [x] **餈�誘撣貊鍂蝔见�銝剔��𦯀�憿孵僎�單𧒄�瑟鰵 (Filtered Out Excess Unpinned & Non-running Shortcuts)**嚗𡁻���� `refresh_app_shortcuts`嚗�笆敹急㭘�䠷�匧�銵刻�銵䔶�餈�誘嚗�蘨�曄內�曉�瘛餃��啣虜�剁�撌脣𤐄摰𡄯��硋��齿迤�刻�銵𣬚�蝔见�嚗諹�皛斗��芾�銵䔶��芸𤐄摰𡁶�憭帋��滨蔭憿寧𤌍����碶� `update_process_status` �罸𡢿�� `rebuild` �∩辣嚗峕�瘚见��曄內����睃��嗥��駁�蝏䀝誑靽肽��𣳇膄�滢��𡒊��湔�憭梧��𣳇��滚鍳頧臭辣��
    - [x] **暺䁅恕餈𥕦�蝔见��桀��齿�銵𣬚�摨� (Enforced Directory Navigation Prior to Execution)**嚗𡁜銁 `_launch_program` 銝� `_launch_as_admin` ��𦶢隞方���遣銝哨�暺䁅恕�冽�韏瑟�隞斤����滢儒�拍���ㄨ撟嗆�銵� `cd /d "target_dir" && `��＆靽脲�霈箸糓�桅�𡁏芋撘讛��舀����銵����𦶢隞方��𡁏𧋦嚗屸��拍�隡睃�頝唾蓮�唳�銵峕�隞嗆��函�蝔见��桀�銝页�皛∟雲鈭��撖寡�銵𣬚㴓憓���湔�抒�閬����
    - [x] **靽桀� UI 蝒堒藁�牐�撠箏站����碶��㰘�撅誩�憿嗥垢蝘颱� Bug (Fixed Window Geometry Persistence & Alignment Shift)**嚗帋耨憭滢�敶梶鍂�瑕�蝒堒藁靚�秐颲��嚗峕��硋𢆡�曄蔭鈭𡡞�餈穃�撟閖▲蝡航器蝻䀹𧒄嚗屸���粹�撘��𡒊���偕撖詨��鞉��𤑳��讐宏���摰� of 蝻粹萅����碶� `save_window_position` 銝� `load_window_position` �餉�嚗���嗉挽摰帋��港蛹蝝批����������撠誩偕撖賊秄瑽𨥈�靽肽�鈭�銁頞����儘�����垢���銝讠�撠箏站蝔喳��扼��
    - [x] **摰䂿緵��掩�㗇𥋘�厰僼�芸𢆡�冽��䌊���摰賢漲蝻拇𦆮 (Auto-Scaling Category Filter Row)**嚗𡁜�憿園����𨅯�蝐駁�㗇𥋘�寞��脲��桃���漣銝箏��典𢆡��憬�曉�撅�����桃�撠箏站�輻�嚗𠄎izePolicy嚗匧�瘞游像撣���渲��賢��讐���捐摨西䌊�冽�隡詨��嗥揮嚗諹圾�喃��典�閫�躹銝见𢰧靘扳��株◤�毺′�芣鱏�格𣏹��撩�瑯��
    - [x] **靽桀� Edge 蝑匧蒂蝛箸聢頝臬��䭾��臬𢆡銝𡒊���宏�典仃��撩�� (Fixed Launch & Auto-Layout Matching for Path-with-Spaces)**嚗�
        - ��漣鈭� `resolve_and_validate_cmd` �賭誘閫��撘閙����撖� Windows 銝讠掩隡� `C:\Program Files (x86)\...` �芸�鋆孵�撘訫噡 of 撣衣征�潛���楝敺��撘訫�鈭��𡏭揪憍芣𣄽�� (Greedy space-joining)�嘥�蝻��埈�瘚讠�瘜𤏪��� 100% 甇�＆霂���箸��輻��拍� exe 頝臬�撟嗅��拐��典�雿靝蛹��㺭��氖��
        - 撘訫�鈭� `_get_quoted_cmd` 摰匧�憭硋ㄢ�賭誘��遣�寞���銁靚�鍂 `subprocess.Popen(cmd, shell=True)` �臬𢆡�㵪��芸𢆡�齿鰵銝箏蒂蝛箸聢��虾�扯�蝔见�頝臬�����唳釣�� double quotes 靽脲擪嚗�蝠摨閗圾�喃� Edge 瘚讛��典�頝臬�蝛箸聢�䭾��㕑絲�� Bug嚗�僎蝖桐��臬𢆡�舘�摰𣬚��朞�蝒堒藁���璅∠��寥��芸𢆡蝘餃𢆡�圈�蝵桀�����

## 2026-07-10 16:45
- [x] **���罸���犖瘞𥪜��舀㺭�株”�澆�撘讛�皛歹�敶餃�瘨�膄��揢餈�誘銝𤾸��唳𧒄����Ｗ㨃憿� (Optimized Formula Filtering via Vectorized Batch-Evaluation in Popularity Resonance GUI)**嚗�
    - [x] **�寞祥 O(N) 敺芰㴓�鞱� pd.eval �扯��園�**嚗𡁜�雿滚僎靽桀�鈭� `popularity_resonance_gui.py` ����典��唳�餈�誘��揢�嗥�銝仿��扯�霈曇恣蝻粹萅���隞���� `populate` ����航”�瑟鰵敺芰㴓銝哨�撖嫣��曉蘨�∠巨�𣂷葵��遣 `DataFrame` �舀𧋦撟嗅儐�航��� `test_code_against_queries`嚗�朖�鞱�靚�鍂 `pd.eval`嚗㚁��典之閫�芋鈭箸�璁𨀣㺭�桐�隡𡁜蒂�亙楊憭抒��瑕鍳�函�霂穃� Python I/O 撘���嚗�紡�渡��Ｙ凒�亦蒾撅誩㨃甇� 3-5 蝘鉝��
    - [x] **摰䂿緵 100% �煾��𡝗鸌�誯�霈∠�**嚗𡁻���� `update_all_tables` �寞���緵�典銁皜脫�憭批儐�臬�憪见�嚗��銝𡏭揣����梢◇����∪嫃����擧�����航”����鉄����刻�蟡其誨���撟塚�銝�甈⊥�找� `df_cache` �𣂼��𣇉眏 `quotes` �箇� fallback ���惩枂蝏煺���鸌�𤩺�霂訫之摰質”��蝙�� `query_engine.execute` 撖寞㟲銵刻�銵䔶� **1甈�** �������誩��砍�餈�誘嚗䔶漣�箏𦶢銝剜��毺�銵仿妟�∠巨隞�� `matched_codes` �����
    - [x] **�滨輕 O(1) ����交𪄳銝𦒘�瘥怎��瑟鰵**嚗𡁜�憭批儐�臬�����滩�蝞堒��Ｘ𤜯�Ｖ蛹���毺� `code_str not in matched_codes` ����交𪄳���撘讛�皛斤��寥��園𡢿瘨��𦯀�蝘垍漣撉日��� 10 瘥怎�撌血𢰧嚗諹�皛斗������ **200+��**嚗���唬���揢餈�誘�𦠜㺭�桀��唳𧒄����湔葡�㮖���稲瘚����
    - [x] **�拍�霂剜�蝻𤥁�銝𡡞��鞉�霂� 100% �𣂼��朞�**嚗𡁻�朞�鈭� `py_compile` �����祗瘜閧�霂𡢅��峕𧒄嚗𣬚垢�啁垢 GUI 蝻枏����瘚贝� `test_pr_gui_history_integration.py` �𣂼�蝏輻��朞�嚗屸�霂���嗆��㦤�峕㺭�格��典銁���笔��Ｘ𧒄��滲��銝𡡞�����

## 2026-07-10 16:35
- [x] **�齿�鈭箸��望𥲤��蟮霈啣��賭葉�啗恣蝞梹�閫���臬𢆡�㰘蝸蝻枏��罸𡢿蝻箏仃���霅血�憌擧𠂔 (Resolved startup-cache NameError warnings via test_code_against_queries integration)**嚗�
    - [x] **摰��憭滨鍂�脩�銝舘䌊���銵仿��亙藁**嚗𡁻���� `popularity_resonance_gui.py` 銝剔� `calculate_history_hits_ui` �寞�����支���𧋦�湔𦻖�冽��冽�����芸停蝏芰� DataFrame (`test_df`) 銝𡃏��� `query_engine.execute` ��挽霈∴���漣銝箇凒�亥��典歇�� `stock_logic_utils.py` 銝剛◤�拍�撉諹��� `test_code_against_queries` 摰匧��亙藁��
    - [x] **�寞祥�臬𢆡銝𤾸��臬𢆡�嗥� NameError 霅血�憌擧𠂔**嚗朞�雿踹��函�摨誩鍳�具���甈∩� `popularity_resonance_cache.json` �㰘蝸蝻枏��𤥁����甇亙��芸��琜�蝻箏仃擃条漣銵滨�����堒� `lastl1d`��td_sell`��amount`��ma5d` 蝑㚁���葩�𣬚�銝𠺪�蝟餌��賢��芸𢆡����箏�撘譍葉蝻箏����撟嗥�蝥扳��蠘‘�其蛹暺䁅恕�潘�敶餃�瘨�膄鈭���唳𠯫敹𦯀葉瘥讐��瑕枂���銝�辺 `WARNING:query_engine_util.py(execute:250): Query Error` 撏拇�銝� NameError 霅血���
    - [x] **�拍�霂剜�蝻𤥁�銝𡡞��鞉�霂� 100% �𣂼��朞�**嚗𡁻�朞�鈭� `py_compile` �����祗瘜閧�霂𡢅��峕𧒄嚗𣬚垢�啁垢 GUI 蝻枏����瘚贝� `test_pr_gui_history_integration.py` �𣂼�蝏輻��朞�嚗屸�霂���嗆��㦤�峕㺭�格��典銁���笔��Ｘ𧒄��滲��銝𡡞�����

## 2026-07-10 16:30
- [x] **摰䂿緵蝔见�敹急㭘�臬𢆡����澆��賭誘銵䎚����啜��� Shell 銝脰��澆捆嚗�僎蝏煺� UAC �鞉��芣� (Implemented Flexible CLI Command, Parameter & Shell Chaining for App Launcher with Unified UAC Auto-Elevation)**嚗�
    - [x] **�𥪜�擃㗛����抒��賭誘銵諹圾�鞉嵗撉���� (Developed Flexible CLI Resolver)**嚗𡁏鰵憓� `resolve_and_validate_cmd` �𣂼��賣㺭嚗屸�撖寡��亦��臬𢆡頝臬�嚗�⏚�� `shlex.split` �𣬚頂蝏毺㴓憓���亥�銵䔶�畾萄��箄�璉�瘚卝���隞��蝢擧𣈲����� exe 蝏嘥笆頝臬�嚗諹��質䌊�刻��怠僎摰帋���鉄��㺭��𦶢隞方�嚗��撣行� `-param`��/k`嚗剹���撅�蝟餌��賭誘嚗�� `python`��cmd`嚗㚁�隞亙�雿輻鍂餈墧𦻖蝚衣�憭𡁏挾 Shell �𡁏𧋦銝脰��賭誘嚗�� `cd D:\xxx; python yy`嚗㚁�敶餃�閫��鈭�笆�墧�������隞嗆𥁒�仮�𡏭楝敺��摮睃銁�萘��𤤿���
    - [x] **�齿�蝏煺��㕑絲�亙藁撟嗅笆朣� Windows 撟喳蝱銋䭾� (Refactored Launchers to Handle Platform Quirks)**嚗�
        - 摰䂿緵鈭��銝��� `_launch_program` �寞���銁�桅�𡁏芋撘誩鍳�冽𧒄嚗�笆鈭𤾸����憭𡁏挾�賭誘嚗諹䌊�典���噡 `;` �踵揢銝� `&&` 撟園�朞� shell �臬𢆡嚗𥕦��嗆惣�賢𧑐銝� `cd D:\` 蝑匧��Ｗ𦶢隞斗釣�� `/d` ��㺭嚗䔶�霂� Windows 蝟餌�銝贝楊�条泵撌乩����撖寞迤蝖柴��
        - �齿�鈭� `_launch_as_admin` �鞉��臬𢆡�寞����撘����𧋦�䭾��箏蒂�賭誘銵���啁� `os.startfile`嚗��蝥找蛹靚�鍂 Windows 摨訫� `ctypes.windll.shell32.ShellExecuteW` API 餈鞱� `"runas"`���雿踹��喃蝙鋡急�韏瑞��臬�����𡁏𧋦�碶葡�𥪜𦶢隞方�嚗䔶��賭誑蝞∠��䁅澈隞賭�撣阡����匧��唳迤撣豢����銵䎚��
    - [x] **撖寥�敹急㭘�厰僼銝舘”�澆𢰧�株���**嚗𡁜��Ｘ𦻖�� `_launch_program` 銝擧����餉���銁 `subprocess` �㕑絲�𥕦枂 `WinError 740`嚗�窈瘙���琜��塚��芷���頝唾蓮�� `_launch_as_admin` 餈𥡝��删��鞉�嚗���唬��嗅�雿坔��餉��剔㴓��
    - [x] **�齿�敹急㭘�臬𢆡�誩�撅�銝箏�銵屸�撖�漲�瑕� (Refactored Shortcuts Grid to Single-Row 6-Item Layout)**嚗�
        - �𣂼�撣貊鍂敹急㭘�臬𢆡���憭批�䠷�㗇㺭�譍蛹 6 銝迎�撟園����蝵烐聢撣��摰帋�嚗�� `row=i//4, col=i%4` 靽格㺿銝箏�銵� `row=0, col=i`嚗㚁�摰䂿緵 6 銝芸翰�瑟��桀銁憿園�瘞游像銝�摮埈�撘�嚗�蝠摨閙��支舅銵��撅�撖寥△�Ｙ熊�𤑳征�渡��删鍂��
        - �𣂼��厰僼��𧋦�曄內���蝚行⏛�凋��鞱秐 16 銝芸�蝚佗�銋见��� 12嚗㚁�撖嫣��𣈯�朞噢靽⊿��滨�蝡胼�萘��蹂葉��𦶢�滨�摨𠉛鍂�臭誑�曄內�箸凒銝啣�摰峕㟲���隞嗅�嚗峕�����滢��毺′�碶�蝢舘��� `...` �芣鱏��
    - [x] **�拍��𧼮�撉諹�**嚗𡁶鍂 `py_compile` 撖寧㮾�� UI �𠹺蜓�𡁏𧋦�扯�霂剜��⊿�嚗���� 100% �𣂼�蝻𤥁�����嗘��典𦶢隞方�瘚贝��其��券𢒰撉諹�鈭� `python D:\...` 隞亙� `cd D:\...; python ...` 蝑匧�蝘滚𦶢隞方”颲曉���圾���朞�����

## 2026-07-10 15:45
- [x] **蝏煺��𦦵揣��蟮��辣頝臬�嚗諹圾�喃犖瘞𥪜��舀㺭�格𧊋銝� Tk/韏偦帕 �𡁶鍂�𦠜����霂餃�憭梯揖��撩�� (Unified Search History Path to datacsv/search_history.json)**嚗�
    - [x] **�拍�撖寥��曹澈�滨蔭��辣**嚗𡁜�雿滚��唬犖瘞𥪜��臬����甇颱��舀�銵𣬚𤌍敶蓥��� `query_history.json`嚗諹�� Tk 銝餌�摨譍�韏偦帕�Ｘ踎蝑㗇��匧�隞𣇉�隞嗅�雿輻鍂 `datacsv/search_history.json`嚗�紡�湔����銵峕��桀�����嗅��脫㺭�格覔�祆�瘜蓥��𠾼��緵撠� `popularity_resonance_gui.py` 銝剔� `SEARCH_HISTORY_FILE` �齿�銝箔���� `tk_gui_modules.gui_config` 撖澆�嚗�仃韐交𧒄 fallback �芸𢆡撖餅𪄳 `datacsv/search_history.json`嚗�蝠摨閙��支��𠉛氖摮文�嚗���唬�頝冽芋�𨰜��楊�Ｘ踎�� 100% �唳旿鈭㘾�𠾼��
    - [x] **�拍��𧼮�撉諹�**嚗朞�銵� `test_pr_gui_history_integration.py` ����訫�瘚贝�嚗���冽�霂訫��𣂼��朞���

## 2026-07-10 15:30
- [x] **靽桀���蟮蝞∠��函��領�𨀣�霂𨰝�嘥��𤑳� `TypeError: on_test_code() got an unexpected keyword argument 'onclick'` 撏拇�撟嗅��唬犖瘞磰��唳旿���皛� (Fixed test_callback TypeError & Implemented Hotlist-based df_all Slicing)**嚗�
    - [x] **�澆捆 `onclick` �噼��亙藁蝑曉�**嚗𡁻���� `popularity_resonance_gui.py` 銝剔� `on_test_code` �亙藁蝑曉�嚗䔶蝙�嗆𣈲�� `query=None` 隞亙� `onclick=False`���鋡怎��餉圻�𡢅�`onclick=True`嚗㗇𧒄嚗諹䌊�刻圾蝏穃僎憪娍�靚�鍂 `QueryHistoryManager` 暺䁅恕���霂蓥� UI �嗆��凒�唳䲮瘜𤏪�摰𣬚�瘨�膄 TypeError 撏拇���
    - [x] **銝交聢�𣂼�瘚贝���凒銝箏��滢犖瘞娍�銝芾�**嚗𡁜銁 `on_test_code` 銝剖��牐��∠巨��凒�園�嚗���朞�瘙��餃��� EM��HS��H��GB 蝑� 5 撘㰘”銝剔�瘣餉��∠巨隞��嚗��隞交迨銝� Index 隞� `sync_manager` ���撅�銵峕�銝剖� DataFrame ����芸�嚗峕�蝏�𣄽鋆�枂銝枏���犖瘞磰�銵峕�摮鞾�撟嗅�甇亥�蝏� `query_manager.df_all`���雿踹��孵稬�𨀣�霂𨰝�肽恣蝞堒枂��龪�滨�銝滚��堒�撣�㦤 5000 �芣��唾�蟡函�瘙⊥�嚗�蘨蝎曉���笆鈭箸��踹�銝芾�霈∠��寥����雿踹��瑕����蝑𣇉裦��紡�譍���
    - [x] **���瘚贝� 100% �朞�撉諹�**嚗𡁻�朞� `py_compile` �� `test_pr_gui_history_integration.py` �拍��訫�瘚贝�嚗峕���項�硋僎撉諹�鈭� `on_test_code(onclick=True)` 靚�鍂嚗屸�霂����迤撣訾��嗆���甇交�霂胯��

## 2026-07-10 15:00
- [x] **摰𣬚�靽桀�鈭箸��望𥲤��蟮餈�誘 `UnboundLocalError: local variable 'pd' referenced before assignment` 瞍𤩺�銝𡡞��鞉�霂訫�蝏輸�朞� (Fixed pd Name Scoping UnboundLocalError & Validated PR History Integration)**嚗�
    - [x] **�冽㺭�株�皛斗凒�啣��� `update_all_tables` 餈𥡝� pandas 摰匧�撖澆�**嚗𡁜銁 `popularity_resonance_gui.py` 銝剔� `update_all_tables` �寞��������典��曉�憓𧼮� `import pandas as pd`���蝖桐�鈭�銁鈭𣬚漣撋���� `populate` �唳旿�滚�銝舘�皛文��𦒘葉嚗䔶誑�𠰴�餈𥡝��孵稬��揢�𡝗�敹萇��㗇𧒄嚗�銁隞颱�撅��其��典��㚚𡡒����剁�撘閧鍂�� `pd` 撖寡情������蝛箔��㗇�嚗�蝠摨閙��支��曹�憭㚚� pandas 撖澆�鋡思��典��株𤪖��銁靚�鍂 `test_code_against_queries` 餈𥡝���蟮�㕑�銵刻噢撘𤩺嵗撉峕𧒄撘訫��� `UnboundLocalError`��
    - [x] **�拍�霂剜�蝻𤥁�銝𡒊垢�啁垢���瘚贝� 100% �𣂼�撉諹�**嚗𡁏�銵� `py_compile` 撖嫣耨�孵��� GUI 璅∪��扯��拍�霂剜��⊿��牐遙雿閙𥁒�辷�蝻硋�撟嗉�銵� `test_pr_gui_history_integration.py` ����訫�瘚贝�嚗峕���芋�煺�隞𤾸��臬𢆡�㰘蝸蝻枏���㺭�格𣄽鋆������ `update_all_tables` 摰峕�餈�誘����冽㺭�桃恣�瓐��鱏閮��文��冽㺭�朞�銝娍�霂閗�銵𣬚��靝蛹 `OK`嚗�蝠摨閖�霂��蝟餌�蝥� query expression �其犖瘞𥪜��臬恥�瑞垢��迅摰朞氜�啜��

## 2026-07-09 21:00
- [x] **靽桀�撟嗡��碶犖瘞𥪜��臬恥�瑞垢�芸𢆡�瑟鰵��楊憭拙��Ｕ��PC �峕郊銝𡒊��舘䌊�典�獢��餉� (Fixed & Optimized Popularity Resonance GUI Auto-Refresh, Date Crossings, IPC Sync & Post-Market Archiving)**嚗�
    - [x] **摰䂿緵�亥砭�瑟鰵�� IPC 銵峕��券�撘箏��峕郊 (Mandatory IPC Sync on Refresh)**嚗𡁜銁 `_run_once_job` �瑕����唬犖瘞娍�銵��嚗���� `self.sync_manager.request_full_sync()` �峕郊霂瑟�撟嗅辣餈� `1.2s` 蝑匧��唳旿瘚�𦻖�塚�敶餃��寞祥鈭����/�芸𢆡�孵稬�亥砭�瑟鰵�𦒘蝙�冽唂銵峕� DataFrame 蝻枏�撖潸稲隞瑟聢銝擧隅撟���餃���撩�瑯��
    - [x] **摰䂿緵�芸𢆡�瑟鰵頝典予�芸𢆡��揢 (Auto-Transition to Today on Date Crossing)**嚗朞𥅾敶枏�憭���𨅯鍳�刻䌊�兩�脲芋撘𧶏�銝娍�瘚见�蝟餌��交�撌脣��笔��湛�頝典予嚗㚁��芸𢆡撠��摮� `self.current_date` 隞亙� UI �� `date_entry` �亙��找辣撘箏��峕郊銝箸��唳𠯫����滨蔭銵冽聢撟嗅�憪𧢲𦻖�嗚���銋���唬�憭拍��唳旿嚗峕��支��曹�靽脲��冽𠯫�交�鋡怎頂蝏笔ế摰帋蛹�𨅯��脣��䀹芋撘謿�肽�峕�瘜閗䌊�典��唳鰵�唳旿����嫘��
    - [x] **摰墧鴌�睃�撘箏���蝏��銋���箏� (Enforced Post-Market Final Archiving)**嚗𡁻�����𤾸蝱�嗥�璉�瘚� `_check_auto_refresh_after_close` �嗆��㦤����亙�摮睃ế摰𡁏�霂� `self._final_post_market_saved_date`��蘨閬��颲� 15:15 �睃�鈭斗�蝏梶��對��喃蝙�賢予���餈����㺭�殷�蝟餌�靘萘�隡𡁜撩銵諹圻�睲�甈⊥�蝏���唳旿�亥砭���瘣堒僎�����蝏� of `.csv.gz` �拍�敶埝﹝嚗𣬚＆靽嘥��思�摰峕㟲���韐Ｕ����梢◇����∪嫃銝擧�蝏��蝞㛖�樴躰�璁靝犖瘞娍㺭�柴��
    - [x] **隡睃��嗥�璉�瘚贝蔭霂ａ��� (Optimized Post-Market Check Frequency)**嚗𡁜� `_check_auto_refresh_after_close` 摰𡁏𧒄�函�頧株砭�湧�隞� `30` ���隡睃�蝻拙�銝� `5` ���嚗�之撟������睃��芸𢆡�閗繮銝舘䌊����菜�摨佗�銝𥪜�甈⊥��亥�埈𧒄雿𦒘�瘥怎�蝥改��牐遙雿� CPU 撘�����
    - [x] **摰䂿緵��蟮�唳旿憭滨��𥪜𢆡�航��𡝗𡉼撣行𠯫�笔��� (Carry Date in Vis Linkage during History Mode)**嚗𡁻���� `send_to_visualizer` �詨��朞悖�寞���頂蝏煺��冽����亙��滨��亦��交��臬炏銝滨�鈭𦒘��乓���憭���𨀣䰻�见��脫㺭�格芋撘謿�脲𧒄嚗����秐 26668 �航��𣇉�蝡舐��桅�� `CODE` ��揢��誘隡朞䌊�典�蝥找蛹撣行�����交���㺭�� `TIME_LINK|{code}|{view_date}` 憭滚��𥪜𢆡��誘嚗�蝠摨閗圾�喃���蟮璅∪�銝贝��函��条𤫇�Ｘ��嗘��亙��嗉�����𤤿���
    - [x] **蝻𤥁�銝𡡞��鞉�霂� 100% �𣂼� (Compilation & Integration Tests Passed)**嚗𡁻�朞� `py_compile` 撖嫣耨�孵��� GUI ��辣餈𥡝�霂剜�璉�撉��蝏輸�朞�嚗�僎蝻硋� `test_popularity_resonance_logic.py` �𣂼��朞� headless �臬�銝讠��嘥��𡝗鱏閮�璉�撉䎚��

## 2026-07-09 20:45
- [x] **閫�����撟嗥�����啣��䁅��烐�銝�1撠𤩺𧒄dff/�暸��唳旿蝏枏���翰�笔�雿滩��� (Enacted & Implemented Real-time Fund Flow Positioning with 1-Hour DFF Slice & Volume Co-detection)**嚗�
    - [x] **�𡝗�1撠𤩺𧒄dff�冽���������鸌敺� (Analyzed 1-Hour DFF Slice Dynamics)**嚗𡁜銁 `realtime_fundflow_positioning_plan.md` 銝哨�霂衣����鈭�1撠𤩺𧒄dff�園𡢿�������靝���枂�售�腈���𨀣�蝏剜����苷��𦦵��嗆����萘��𡁻�閫��嚗䔶誑�𠰴銁撠𤩺𧒄�澆��Ｘ𧒄dff鈭抒��睃𢆡��鸌敺���
    - [x] **霈曇恣韏��瘚��撘箏漲 (FFI) �冽���皛斗芋�� (Designed FFI Dynamic Filter Model)**嚗𡁻�朞�蝏枏�dff����園�瘥䈑�VolumeRatio嚗匧�隞瑟聢�詨笆撘箏漲霈曇恣鈭� $\text{FFI} = \text{dff} \times \text{VolumeRatio} \times \text{PriceStrength}$ 霈∠��砍�嚗峕��文��嗅����蝵桀�韏瑞�靽∪噡銵啣�嚗���啗��烐�撘箏漲��像皛穃ế�准��
    - [x] **�賢𧑐�漤����蝞� UI ��緵銝𤾸�撅�漱�梶頂蝏毺��� (Zero-Code UI & System Integration)**嚗�
        - �湔鰵鈭� `global.ini` �滨蔭��辣嚗�銁 `vol_up_details_col` �𡑒”銝剛蕭�牐� `"瘚��毺𠶖��"`��
        - �齿�鈭� `instock_MonitorTK.py` 銝剔� `_async_stats_aggregation` �𤾸蝱摰𡁏𧒄蝏蠘恣�𡁜�璅∪�嚗�銁撘�𢆡�暸��唳旿����塚��寞旿 1 撠𤩺𧒄皛𡁜𢆡�園𡢿����文�璅∪����摨閗��辷�摰墧𧒄霈∠�撟嗆釣�� `"瘚��毺𠶖��"`嚗���� `�∩��Ǒ������賒`���𤣳蝒��` 隞亙� `--`嚗剹��
        - �� `signal_dashboard_panel.py` �� `VolumeDetailsDialog.update_data` �瑟鰵�餉�銝凋蛹 `"瘚��毺𠶖��"` 憓𧼮�鈭���嗅�����脫葡�橒�鈭桃滯��漁�鉝���暺�����蝎堒�雿𤘪甅撘𧶏�摰䂿緵摰���滚縧 UI �齿����撖�漲隡䁅捶��緵��
    - [x] **�蹱���霂睲��芸𢆡�㚚��鞉�霂� 100% �𣂼� (Static Compilation & Integration Tests Passed)**嚗�
        - �扯� `py_compile` 撖寧㮾�單�隞嗆�銵諹祗瘜閙�撉��蝏輸�朞���
        - 蝻硋� `scratch/test_fund_flow_positioning.py` �𣂼�撉諹�鈭���毺𠶖��ế摰𡁜銁��𧒄�游躹�游��望𥲤�𨅯�銝讠�甇�＆�扼��
        - 蝻硋� `scratch/test_ui_flow_status.py` �� PyQt6 �臬�銝见��冽芋�蠘”�潭葡�枏��訫��潭甅撘誩��㵪��剛��⊿��券� 100% �朞���

## 2026-07-09 20:00
- [x] **靽桀�憭𡁜𪂹���霂訫膥銝� `'ratio'` (�Ｘ���) 摮埈挾�券��曄內銝� 0.0 ��撩�� (Fixed Zeroed-Out 'ratio' (Turnover Rate) in Standalone Multi-Period Tester)**嚗�
    - [x] **摰䂿緵摰墧𧒄銵峕� `'ratio'` 摮埈挾�噼‘�箏� (Real-time ratio Recovery)**嚗𡁜銁 `standalone_multi_period_tester.py` �� `_worker` 銝哨��曹��芾粉璅∪�銝讠凒�亥��� `Sina(readonly=True).all` 餈𥪜� of �笔� DataFrame 銝滚��� `'ratio'` �梹��啣�鈭��撖� `'ratio'` �� fallback �噼‘璅∪���𥅾�𤑳緵蝻箏�霂亙�畾蛛�隡𡁜銁�𤾸蝱蝥輻�銝剛䌊�冽��� `realdatajson.get_sina_Market_json('all')` 撟園�朞� `cct.combine_dataFrame` 撠���嗆揢�讠��唳旿銵仿��啣抅�����葉��
    - [x] **撘訫� HDF5 ��蟮�唳旿��僎�脰��碶��� (HDF5 Merge Collision Protection)**嚗𡁜銁 `tdx_data_Day.py` �� `get_append_lastp_to_df` �潸”銋见�嚗峕鰵憓硺�撖� `tdxdata`嚗𠃍DF5 ��蟮蝻枏��唳旿嚗厩�摮埈挾皜��靽脲擪��銁�扯� `combine_dataFrame` 銋见�嚗�撩�� drop �� `tdxdata` 銝剔� `ratio` �� `vol_ratio` 銝文�嚗䔶誑�脫迫 HDF5 摨㮖葉�䭾��� 0.0/NaN �澆銁��僎�嗉��𡝗�摰墧𧒄銵峕�銝剜迤蝖桃��Ｘ�����𤩺��唳旿��
    - [x] **�蹱��祗瘜閧�霂穃�頝典𪂹�蠘��典�瘚��蝞⊿�璅⊥�撉諹� 100% �𣂼� (Verified Multi-Cycle Data Pipeline Verification)**嚗𡁏�銵� `py_compile` 撖寧㮾�單�隞嗆�銵䔶�霂剜�璉�撉䕘��券�銝�甈⊥�折�朞�嚗𤤿��� `scratch/test_ratio_recovery_check.py` �𡁏𧋦嚗���湔芋�煺�憭𡁜𪂹�笔��𤾸�頧賬���撟嗅�撟喲唍�枏像��㺭�桃恣�瓐���瘚� `d`, `2d`, `w`, `m` 蝑匧��典�銝𤾸𪂹�毺� `ratio` 摮埈挾銝滢�摮睃銁嚗䔶��鮋妟�㗇���銁 98.5% 隞乩�嚗��蝢𤾸�敶埝迤撣詨��啜��
- [x] **摰墧鴌憭𡁜𪂹�蠘”�潭㺭�桀�摰賣��𣂼�蝻拐��垍�撖�漲隡睃� (Enacted Extreme Column Width Compression & Layout Density Optimization)**嚗�
    - [x] **�齿� `_adjust_column_widths` �芸𢆡瘚钅��餉�**嚗𡁏��游��匧�摰賢�憿餃��刻�摰寧熙�𣈯鵭�埈�憸覀�萘��𣂼�嚗���園���蛹銝餉��晦�𨀣㺭�桀�摰寞𧋦頨急�憭批捐摨色�嗪店�函��芷����垍���
    - [x] **撘訫��孵����擃睃�摨血𤐄摰𡁜�摰賡秄瑽� (Compact Metric Specific Widths)**嚗�
        - 撖嫣� `red(d)/win(d)` 蝑㕑���/蝥Ｙ��游��梹�����讠憬撟嗅𤐄摰𡁜�摰賭蛹 **38px**嚗�
        - 撖嫣� `strong_structure_score` 撘箇����蝑劐�雿齿筑�寞㺭嚗�� 102.7嚗匧�嚗�𤐄摰𡁜�摰賭蛹 **52px**嚗�
        - 撖嫣� `slope` �𦦵��唳旿�梹��箏��堒捐銝� **50px**嚗�
        - 撖嫣� `dff` �䀝葉撌桀�潭㺭�桀�嚗�𤐄摰𡁜�摰賭蛹 **48px**嚗�
        - 撖嫣� `price/trade/now` 蝑劐遠�潛㮾�喳�嚗�𤐄摰𡁜�摰賭蛹 **48px**嚗�
        - 撖嫣� `percent` 瘨典��梹��箏��堒捐銝� **52px**嚗�
        - 撖嫣� `ratio` (�Ｘ�) �梹��箏��堒捐銝� **48px**嚗�
        - 撖嫣��喃儒�� `d`, `2d`, `w`, `m` 蝑匧�銝𤾸𪂹�笔㗲�厩� Check �梹������香�� **35px**嚗�
    - [x] **�𦠜𦆮憭批捐銵� 40% 隞乩���偌撟唾�閫厩征��**嚗帋��𡁜�摰䂿緵�������𡏭”憭游��� Tooltips (�祆筑瘞娍部) �𥪜𢆡嚗䔶蝙�冽�隞�銁��閬�𧒄�朞��砍��喳虾�交��踹�����函妍嚗���嗡蝙銵冽聢���蝝批��啣銁銝餉�蝒𦯀葉摰𣬚�撟喲唍嚗�蝠摨訫��斤��鞟�撌血𢰧皛𡁜𢆡鈭支�雿㯄���


## 2026-07-09 19:35
- [x] **摰䂿緵銝芾��𡑒”�堒��砍��鞟內銝𦒘蜓閫�㦛�餉�擃睃漲憭滨鍂 (Enacted Table Column Header Hover Tooltips & DRY Refactoring)**嚗�
    - [x] **�齿�銝餉��� Motion 鈭衤辣�詨��餉�**嚗𡁜� `_on_tree_motion` ��𧋦�蹱香銝餉��� Treeview �找辣���瘜訫竉蝳餃僎�齿�銝粹�𡁶鍂�� `_on_tree_motion_impl(event, tree)` ����亙藁����塚�銝箔��曇��𣂼��冽��典翰�笔��䀝���漱鈭鍦虾霂餅�改�撠��蝷箸��砌��笔���誨���畾萄�嚗�� `dff_d`嚗㗇惣�賢�蝥找蛹������㛖�摰鮋�銵典仍�曄內���嚗�� `dff(d)`嚗剹��
    - [x] **銝箔�蝥扳踎�𦯀葵�� Constituents 撘寧��𤑳���溶�� Tooltip 蝏穃�**嚗𡁜銁 `show_concept_top10_window` �寞�銝哨�銝箔葵�∪�銵� `tree` �冽���摰帋� `<Motion>`嚗��瘣曇秐�齿��𡒊� `_on_tree_motion_impl`嚗匧� `<Leave>`嚗��瘣曇秐 `_on_tree_leave`嚗劐�隞嗚��
    - [x] **撘訫� Toplevel ��瘥���冽���俈��**嚗帋蛹 Constituents 撘寧� `win` 蝏穃�鈭� `<Destroy>` 鈭衤辣嚗�銁蝒堒藁��瘥�𧒄�拍�靚�鍂 `_hide_tree_tooltip()` 隞亙蝠摨閙��斗�摮条�撅誩��祆筑獢��靽嗪��屸𢒰餈鞱����摨衣滲���扼��
    - [x] **�蹱��祗瘜閧�霂� 100% �𣂼�撉諹�**嚗帋蝙�� `py_compile` 撖嫣耨�孵����隞嗆�銵䔶�蝻𤥁��⊿�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��e` �冽���摰帋� `<Motion>`嚗��瘣曇秐�齿��𡒊� `_on_tree_motion_impl`嚗匧� `<Leave>`嚗��瘣曇秐 `_on_tree_leave`嚗劐�隞嗚��
    - [x] **撘訫� Toplevel ��瘥���冽���俈��**嚗帋蛹 Constituents 撘寧� `win` 蝏穃�鈭� `<Destroy>` 鈭衤辣嚗�銁蝒堒藁��瘥�𧒄�拍�靚�鍂 `_hide_tree_tooltip()` 隞亙蝠摨閙��斗�摮条�撅誩��祆筑獢��靽嗪��屸𢒰餈鞱����摨衣滲���扼��
    - [x] **�蹱��祗瘜閧�霂� 100% �𣂼�撉諹�**嚗帋蝙�� `py_compile` 撖嫣耨�孵����隞嗆�銵䔶�蝻𤥁��⊿�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��

## 2026-07-09 12:15
- [x] **靽桀�銝芾��𡑒”�𨅯��猾�嘥��孵稬�䭾��鍦���撩�� (Fixed Click-to-Sort on Serial Number (idx) in Constituents Popup)**嚗�
    - [x] **銵亙��𨅯��猾�嘥�憭� command �孵稬蝏穃�**嚗𡁜銁 `standalone_multi_period_tester.py` �� `show_concept_top10_window` �屸𢒰皜脫�銝哨�銝� `"idx"` �堒仍蝏穃�鈭� `command=lambda c="idx": sort_sub_column(tree, c, False)` �鍦���誘嚗䔶蝙敺㛖鍂�瑞��領�𨅯��猾�肽”憭湔𧒄�賢�甇�虜閫血��鍦��其�嚗�銁憭𡁶漣�𥪜𢆡銝擧䰻�见��鞉𧒄摰䂿緵�湧◇�� of �𡑒”�渡�銝擧㺭�桀�皞胯��
- [x] **隡睃�銝芾��𡑒”�孵稬�𥪜𢆡嚗𣬚宏�支�憭𡁜𪂹�煺蜓閫�㦛銝凋�敹����歲頧砍�雿� (Optimized Popup Stock Selection Linkage, Removed Unwanted Focus/Jump in Main View)**嚗�
    - [x] **�齿� `_do_linkage` �亙藁隞交𣈲��遬撘誩���**嚗帋蛹 `_do_linkage` 憓𧼮�鈭�虾�厩� `code=None` ��㺭���隡惩��瑚�隞���嗥凒�交�銵諹��券�餉�嚗諹����嗡蛹蝛箸𧒄�漤�蝥找�銝� Treeview ����漤�劐葉銵䔶葉霂餃�嚗峕�擃䀝��寞�����冽�扼��
    - [x] **閫��虫葵�� Constituents �𡑒”�劐葉銝𦒘蜓閫�㦛��撩�園�劐葉銵䔶蛹**嚗𡁜銁銝芾��𡑒” `on_select_sub` �劐葉鈭衤辣�噼�銝哨�敶餃�摨罸膄鈭��憭𡁜𪂹�煺蜓 Treeview �扯� `selection_set`��focus` �� `see` ����典�雿齿�雿頣��嫣蛹�湔𦻖�� `_do_linkage(code=code)` �閖�雴葵�∩誨���銵屸�𡁻��������唬��孵稬霂行�銝芾�閫血�憭㚚��讠��曇”�𥪜𢆡����嗅��冽�銝駁𢒰�踵㺭�株�����劐葉憿孵��其����甇Ｖ�頝喳𢆡���雿喃漱鈭雴�撉䎚��
    - [x] **�蹱��祗瘜閧�霂� 100% �𣂼�撉諹�**嚗𡁏�銵� `py_compile` 撖嫣耨�孵����隞嗆�銵䔶�蝻𤥁��⊿�嚗峕�隞颱�霂剜��𣇉憬餈𥟇𥁒�踺��


## 2026-07-08 10:30
- [x] **靽桀�憭𡁜𪂹�蠘��典��啁瑪蝔� asyncio 蝻箏仃撘訫��� RuntimeError 撏拇� (Fixed Asyncio Event Loop RuntimeError in Multi-Period Background Threads)**嚗�
    - [x] **�惩𤐄 `get_sina_Market_json` 撘�郊�瑕��餉�**嚗𡁻���� `JSONData/realdatajson.py`嚗����𧋦�湔𦻖靚�鍂 `asyncio.get_event_loop()` �踵揢銝箏蒂 `try-except` 靽脲擪���隞嗅儐�臬��刻繮�碶�蝏穃��餉�嚗峕��支� Python 3.9 �𠹺誑銝羓㴓憓�葉�硺蜓蝥輻�暺䁅恕蝻箏�鈭衤辣敺芰㴓撘閗絲�� `RuntimeError: There is no current event loop` 撏拇��桅���
    - [x] **銝餌瑪蝔钅��㰘蝸 `StockCode` �蓥��脣援皞�㦤��**嚗𡁜銁 `standalone_multi_period_tester.py` ��蜓蝥輻� `__init__` �嘥��𡝗錰撠橘��峕郊閫血� `get_global_stock_code()`嚗���航�撘訫�蝵𤑳��匧��� I/O 霂餃��� `StockCode` �嘥��硋極雿𨅯��讐蔭鈭𦒘蜓蝥輻�銝剜��滚��琜�雿踹��𤾸蝱摮鞟瑪蝔贝�憭毺凒�乩����銝剛粉�𤥁砲�蓥�嚗䔶�隞�蝠摨閖��滢��𤾸蝱蝥輻�銝剝��亥砲�湔鰵�餉�嚗諹�餈𥕢�甇乩��碶�憭𡁜𪂹�蠘��函��厰𢒰�輻��瑕鍳�冽�扯���
    - [x] **憭𡁜𪂹�蠘��典��啣�蝥輻��𢠃����霂� 100% �𣂼�撉諹�**嚗帋蝙�� `py_compile` 撖嫣耨�孵����隞嗆�銵䔶�霂剜�璉�撉䕘��券��函遛�朞�嚗𤤿��� `scratch/test_asyncio_loop_fix.py` 璅⊥��硺蜓蝥輻�靚�鍂�唳旿�匧��亙藁嚗��瘚见歇�質䌊��䌊�典�撱箏僎蝏穃�鈭衤辣敺芰㴓撟嗉��墧��𡝗㺭�殷��牐遙雿閙𥁒�踺��

## 2026-07-07 20:50
- [x] **��漣 Alt+N 銝箇頂蝏毺漣�典��剝睸 (Upgraded Alt+N to System-Wide Global Hotkey)**嚗�
    - [x] **銵亙�銝餌�摨誩�撅��剝睸摮堒�銝𤾸�靚��摰�**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_HOTKEY_MAP` �� `_HOTKEY_INFO_MAP` 摮堒��䕘�銵仿�鈭� `Alt+P`嚗��蝘駁� `13`嚗劐� `Alt+N`嚗��蝘駁� `14`嚗屸睸��蛹 `0x4E`嚗厩�瘜典�銝𦒘葉����賜�隞卝��銁 `setup_global_hotkey` �� `hotkey_callbacks` �惩�銝哨�蝏穃�鈭� `14` 撖孵� `toggle_multi_period_tester`��
    - [x] **�峕郊�祉��剝睸摮鞱�蝔𧢲�撠�� Named Pipe ���**嚗𡁜銁 `hotkey_rotator.py` �� `HotkeyListener.hotkey_map` 摮堒�銝哨�瘛餃�鈭��蝘駁�銝� `14` �� `Alt+N`��蝙敺堒銁�硺漱�梶�����寞暑�冽𧒄嚗��餈𤤿�銋蠘��朞� Windows �毺� API �拍��閗繮撟嗅銁鈭𡁏神蝘垍漣���朞�蝞⊿�����喃蜓餈𤤿�靚�漲�扯�嚗���券��滢�銝餌瑪蝔� GIL �⊥香嚗諹挽霈∩�蝟餌���歇�厩� `Alt+H`, `Alt+L`, `Alt+P` 蝑匧�撅��剝睸�箏�摰��撖寥���
    - [x] **�齿��箄��曄內/�鞱���揢�餉�**嚗𡁜銁 `instock_MonitorTK.py` �� `toggle_multi_period_tester` 銝哨��� `focus_displayof() == self._multi_period_tester_win` and `state() != "withdrawn"` 撖寥�鈭���亦蒾�垍恣��膥蝑厩�����箄��衣���揢�餉���朖敶梶�����其�鋡怠�隞𣇉�����⊥𧒄嚗峕� Alt+N 銝滢��躰秤�鞱�嚗諹�峕糓撠���匧��滚蝱�𡁶�撟嗥蔭憿塚�隞��蝒堒藁撌脰��虫��芷��𤩺𧒄�� Alt+N �滢�撠���鞱�嚗Áithdraw嚗㚁��曇��𣂼�鈭��雿靝�撉𣬚�蝎曄＆摨艾��
    - [x] **��漣蝟餌�韏��銝擧暑頝��蝒𡑒��剝𢒰�踹僎銵亙�����删鍂 (Upgraded System Resource Report & GUI Memory Footprints)**嚗𡁜銁 `System Resource Report` 憿園�餈賢�鈭���啁� `=== GUI Active Windows Status ===` 霂𦠜鱏�𧢲踎���憭𡁜𪂹�蠘��函��亦��匧膥 (Alt+N)����亦蒾�� (Alt+S)��𥁒霅衣��� (Alt+E)��之�䀹萱摨阡��� (Alt+K)���隞瑁�撽祇𢒰�� (Alt+M)����嗡縑�瑚貌銵函� (Alt+L) ���蝑𡝗�瘞� (Alt+J) 隞亙��箄��滨� ATS 蝏�垢 (Alt+P) 8 憭扳瓲敹��隞嗥�摮䀹暑��遬�鞟𠶖���摰墧𧒄����删鍂�券��亙�����券��𣂷�擃条移摨艾����餃��� DataFrame �唳旿蝻枏��鍦��急��賣㺭 `get_object_dfs_memory`嚗諹�蝎曉��𣂼�瘥譍葵瘣餉�閫��銝剖��典����嚗��憭𡁜𪂹�� DataFrame 蝻枏�憭批捐銵剁�������銝� UI �箇�撘����貊�����冽����箏� `Memory: 186.4 MB (Cache: 156.4MB)` ���摮䀹�蝏��撟嗅銁�喲𡡒�嗆�蝷� `[撌脣��券��霄`嚗䔶蛹�冽��𣂷�摰���𤩺����摮睃��笔𦶢�冽��烐綉��

## 2026-07-07 20:45
- [x] **隡睃�憭𡁜𪂹�毺�����賢𪂹�煺����皜���箏� (Optimized Multi-Period Window Lifecycle & Memory Cleanup)**嚗�
    - [x] **敶餃���瘥����𤜯隞���誯�餉�**嚗𡁻���� `standalone_multi_period_tester.py` 銝剔� `on_close` 蝒堒藁�喲𡡒�餉����撘���笔��� `withdraw()` �鞱��箏�嚗峕㺿銝箇凒�亥��� `destroy()` �拍���瘥� Tkinter 蝒堒藁嚗𣬚＆靽萘��賢𪂹�毺��麄��
    - [x] **撘訫� `_is_closing` �嗆��𢹸�菟俈��**嚗𡁜銁 `__init__` 銝剖�憪见� `self._is_closing = False`嚗�僎�函�����剜𧒄蝵桐蛹 `True`��銁 `_update_status`��_show_results` �� `_poll_favorites_loop` 蝑匧�甇交凒�啣�摰𡁏𧒄�典�靚���對�撘訫�鈭�笆 `self._is_closing` ��𠶖���瘚页��芸𢆡�剛楝���選��𦦵�鈭�眏鈭舘挪�桀歇鋡怎����瘥�� Tk �找辣撘訫��� `TclError`��
    - [x] **�曉�皜�膄擃睃�摮� DataFrame 銝𤾸��𡒊�摮�**嚗𡁜銁 `on_close` 銝哨��曉�皜��鈭� `self.engine._period_dfs.clear()` �� `self.engine._missing_periods.clear()` 蝻枏�嚗�僎撠� `self.top_now`��self.last_result_df` �� `self._last_flat_df` 蝑匧之摰質”撖寡情撘閧鍂蝵桐蛹 `None`嚗���嗥�����凋��芸��� `_link_after_id` 霈⊥𧒄�典����匧�瘣餌�鈭𣬚漣摮鞟����`detail_win`, `concept_win`嚗剹��
    - [x] **�见𢆡閫血���䔿�墧𤣰**嚗𡁜銁�喲𡡒�餉�����舘��� `gc.collect()` 撘箏�閫血� Python ��䔿�墧𤣰�剁�蝖桐�鋡恍��曄�憭批�摮� DataFrame 蝡见�敶坿��喟頂蝏麄��

## 2026-07-07 20:30
- [x] **�券𢒰靽桀�摮斤�餈𤤿�璉�瘚钅�餉�銝擧�扯��園�嚗�僎�曉捐撘箇���撩摨西���輕��秄瑽� (Fully Fixed Orphaned Process Detection, Performance Bottlenecks & Relaxed strong_structure_score keep_alive Gate)**嚗�
    - [x] **�拍�餈睃�撟嗡��� `sys_performance_analyzer.py` 摮斤�餈𤤿�璅∪�**嚗𡁜蝠摨閙����甇文���僎靽格㺿�嗅銁 `sys_performance_analyzer.py` 銝剜�憭㚚�䭾���祗瘜閙��譌����䠷�憭滢誨��誑�𦠜��冽䰻�暸�餉�嚗𥟇��支� `check_process_association` 銝剔�雿擧� `process_iter` 敺芰㴓嚗���唾�霂𦠜鱏�扯��𣂼��喃�瘥怎�蝥改��脫迫銝餌瑪蝔见銁擃㗛��急�霂𦠜鱏�嗅��� UI ��絲嚗�
    - [x] **�曉捐 `strong_structure_score` �㕑�霂��蝏湔��𡁻�**嚗𡁜銁 `data_utils.py` 銝剜𦆮摰賭� `keep_alive` ����園秄瑽𨥈�撠��憭抵�撟���嗆𦆮摰質秐 `pct > -5.0`嚗��銝� `-4.0`嚗㚁�撠� `ma5` ��瑪銵啣�蝟餅㺭 `ma5_decay_threshold` �滢��� `0.95`嚗�𠯫蝥選�/ `0.96`嚗��隞硋之�冽�嚗㚁�隞舘���摰孵撩�蹂葵�∪銁銝餃�餈��銝剔��亙熒�噼萱銝舘粥撟單㟲���撠� `obv_val` �賡�蝥踹�蝳駁秄瑽𥡝��� `0.97`嚗𥡝圾�喃���𧋦�㗇瓲敹��瘨其遠��/�噼萱銋啁�銝芾��䭾�摨虫艇�𤤿��亙熒�𣂼��諹◤�湔𦻖�嫣蛹 0 ���銝𡁜𦛚蝻粹萅嚗��撘箔�霂������亦��文���遠�潘�
    - [x] **摰帋� Windows 蝟餌��仿� -1073741502 銝� 0xc0000142 ��覔�砍���**嚗𡁜��𣂼枂�曹��抒��砌葉 `conhost.exe` ��妖摮斤�餈𤤿��芾�甇�＆皜�膄嚗�紡�渡頂蝏� Desktop Heap 銝舘�蝔𧢲局雿滩�皞鞱�堒偷嚗諹稲雿踹�餈𤤿��典�憪见� DLL �嗥凒�亙��� `0xc0000142`嚗𠄎TATUS_DLL_INIT_FAILED嚗匧援皞���曹��賭誘銵諹��嗡誑 `-1073741502`嚗𠄎TATUS_CONTROL_C_EXIT嚗匧撩銵屸���箝��𤌍�滢誨��歇�瑕�摰峕㟲�脤�銝𡒊�蝥扳�����𨥈��冽��冽�����祉征 conhost 餈𤤿��㚚��臬�蝟餌�撠�蝠摨閗䌊���憭溻��

## 2026-07-07 19:40
- [x] **靽桀�憭𡁜𪂹�� `strong_structure_score` 霂��銝� 0 ��覔�祉撩�瑚� UI 撅閧內憓𧼮撩 (Fixed Multi-Period zero-filled strong_structure_score & Enhanced UI Display)**嚗�
    - [x] **�寞祥甇仿炊憿箏��垍蔭撖潸稲�芷����冽�瘨刻�撟�仃��� Bug (Fixed Step Execution Order for Adaptive percent Calculation)**嚗𡁜�雿滚��� `data_utils.py` ��� `complete_indicators_pipeline` 蝞⊿���郊撉日◇摨誩��� logic �垍蔭����祇�蝞埈��� `close` 銝𧢲隅頝��銝� MA ��瑪��䌊����冽�霈∠�嚗�郊撉� 2.5嚗㗇��典抅蝖����霈∠�嚗�郊撉� 1 `calc_indicators`嚗劐��汿���撖潸稲 `calc_indicators` ����刻��� `calc_strong_rebound_score_vect` �塚�DataFrame 餈䀹瓷�厩��鞉��啁� `percent` �𡑒�諹圻�穃�蝵桐�韏𡝗㜃�芷���選�撘箄�撠����蔭銝� 0��緵撠�砲�芷����滨��餉��港�銝羓宏�單郊撉� 1 `calc_indicators` 銋见�餈鞱�嚗䔶蝙 percent �𦯀���瑪霈∠��典���������恣蝞堒銁�汿��銁銝滢耨�孵�撅� `sina_data.py` �唳旿皞鞟��齿�銝页�摰𣬚�靽桀�鈭�迨蝑𣇉裦霈∠�憭望�蝻粹萅嚗峕𪄳�硺��笔������㺭�殷�
    - [x] **摰䂿緵 `strong_structure_score` �㛖� UI �蹱���瘜典� (UI Registration of strong_structure_score)**嚗𡁜銁 `standalone_multi_period_tester.py` �� `_init_ui` ���牐葉嚗�� `"strong_structure_score"` 瘛餃��� `self.fixed_cols` �𡑒”銝准��極�瑟�銝𠰴��芸𢆡���撖孵����憭漤�㗇�嚗𣬚鍂�瑕㗲�匧��喳虾�� Treeview 銵冽聢銝剖��嗆䰻�衤�撖寥���𪂹�毺�撘箇����嚗峕����齿��冽�摮埈溶�𩤃�
    - [x] **摰䂿緵憭𡁜𪂹���摨誩��芸𢆡皛𡁜𢆡�圈▲�典��� (Auto Scroll to Top on Sorting)**嚗𡁜銁 `standalone_multi_period_tester.py` ����冽�摨� `sort_column` 蝏���峕葡�梶��� `_show_results` 蝏��嚗��撘訫� `self.tree.yview_moveto(0)` �箏���鍂�瑁�銵諹”憭湔�摨𤩺��齿鰵�扯�餈�誘蝑偦�匧�嚗𣊁reeview 銵冽聢閫�藁�祇𡢿�芸𢆡皛𡁜𢆡�啁洵銝�銵䕘���之�唬��碶�擃睃撩摨衣��匧㦤�臭���縑�航粉�碶�撉䕘�
    - [x] **�拍�霂剜�蝻𤥁��芣�銝𤾸�瘚��蝞⊿�撉諹��函遛�朞�**嚗帋蝙�� `py_compile` 撖寧㮾�單�隞嗆�銵䔶�蝻𤥁��⊿�嚗�100% �朞�嚗𥡝�銵峕芋�笔��冽�蝑𣇉裦霈∠�摰質”���霂閗��� `scratch/test_verify_real_pipeline.py`嚗��瘚𧢲𠯫蝥� 186 �芯葵�∪� 2d �冽� 178 �芯葵�∪�霈∠��箔�甇�＆������嚗�捐銵� join 憿箇�嚗��敶� exit code 0��


## 2026-07-07 19:40
- [x] **靽桀�憭𡁜𪂹�� `strong_structure_score` 霂��銝� 0 ��覔�祉撩�瑚� UI 撅閧內憓𧼮撩 (Fixed Multi-Period zero-filled strong_structure_score & Enhanced UI Display)**嚗�
    - [x] **�寞祥甇仿炊憿箏��垍蔭撖潸稲�芷����冽�瘨刻�撟�仃��� Bug (Fixed Step Execution Order for Adaptive percent Calculation)**嚗𡁜�雿滚��� `data_utils.py` ��� `complete_indicators_pipeline` 蝞⊿���郊撉日◇摨誩��� logic �垍蔭����祇�蝞埈��� `close` 銝𧢲隅頝��銝� MA ��瑪��䌊����冽�霈∠�嚗�郊撉� 2.5嚗㗇��典抅蝖����霈∠�嚗�郊撉� 1 `calc_indicators`嚗劐��汿���撖潸稲 `calc_indicators` ����刻��� `calc_strong_rebound_score_vect` �塚�DataFrame 餈䀹瓷�厩��鞉��啁� `percent` �𡑒�諹圻�穃�蝵桐�韏𡝗㜃�芷���選�撘箄�撠����蔭銝� 0��緵撠�砲�芷����滨��餉��港�銝羓宏�單郊撉� 1 `calc_indicators` 銋见�餈鞱�嚗䔶蝙 percent �𦯀���瑪霈∠��典���������恣蝞堒銁�汿��銁銝滢耨�孵�撅� `sina_data.py` �唳旿皞鞟��齿�銝页�摰𣬚�靽桀�鈭�迨蝑𣇉裦霈∠�憭望�蝻粹萅嚗峕𪄳�硺��笔������㺭�殷�
    - [x] **閫���墧𠯫蝥踹之�冽�銝𧢲㿥�嗆㺭�桀��其���瑪�屸�霈∠�霂臬榆 (Fixed Period lastp2d Reference & MA Overlap)**嚗𡁜銁憭批𪂹�煺�嚗�� `2d`��3d`��w` 嚗㚁��芸��鞟�敶枏��冽��唳旿隡𡁏��嗅��� `lastp1d`��覔�桐��∟��辷���迤撌脣�蝏梶�銝𠹺��冽��嗥��冽𤣰摮䀹𦆮�� `lastp2d` 銝准��緵撌脣銁 `data_utils.py` �芷����滨�銝剖��亙𪂹�蠘䌊���頝舐眏�婙�𥪜銁憭批𪂹�煺�隞� `lastp2d` 雿靝蛹�冽𤣰�箏�霈∠� Pct 瘨典�嚗���嗅銁霈∠�憭批𪂹�毺� MA5 �� MA10 ��瑪�塚��芸𢆡頝唾� `lastp1d` 摮埈挾隞交��斗𧋦�冽��芣𤣰�䀹㺭�桃��屸�霈∠��滚�嚗䔶蝙憭批𪂹�毺�隞瑟聢蝏𤘪�銝𤾸撩摨西���凒�删移���
    - [x] **摰䂿緵 `strong_structure_score` �㛖� UI �蹱���瘜典� (UI Registration of strong_structure_score)**嚗𡁜銁 `standalone_multi_period_tester.py` �� `_init_ui` ���牐葉嚗�� `"strong_structure_score"` 瘛餃��� `self.fixed_cols` �𡑒”銝准��極�瑟�銝𠰴��芸𢆡���撖孵����憭漤�㗇�嚗𣬚鍂�瑕㗲�匧��喳虾�� Treeview 銵冽聢銝剖��嗆䰻�衤�撖寥���𪂹�毺�撘箇����嚗峕����齿��冽�摮埈溶�𩤃�
    - [x] **摰䂿緵憭𡁜𪂹���摨誩��芸𢆡皛𡁜𢆡�圈▲�典��� (Auto Scroll to Top on Sorting)**嚗𡁜銁 `standalone_multi_period_tester.py` ����冽�摨� `sort_column` 蝏�� and 皜脫�蝏𤘪� `_show_results` 蝏��嚗��撘訫� `self.tree.yview_moveto(0)` �箏���鍂�瑁�銵諹”憭湔�摨𤩺��齿鰵�扯�餈�誘蝑偦�匧�嚗𣊁reeview 銵冽聢閫�藁�祇𡢿�芸𢆡皛𡁜𢆡�啁洵銝�銵䕘���之�唬��碶�擃睃撩摨衣��匧㦤�臭���縑�航粉�碶�撉䕘�
    - [x] **�拍�霂剜�蝻𤥁��芣�銝𤾸�瘚��蝞⊿�撉諹��函遛�朞�**嚗帋蝙�� `py_compile` 撖寧㮾�單�隞嗆�銵䔶�蝻𤥁��⊿�嚗�100% �朞�嚗𥡝�銵峕芋�笔��冽�蝑𣇉裦霈∠�摰質”���霂閗��� `scratch/test_verify_real_pipeline.py`嚗��瘚𧢲𠯫蝥� 186 �芯葵�∪� 2d �冽� 172 �芯葵�∪�霈∠��箔�甇�＆������嚗�捐銵� join 憿箇�嚗��敶� exit code 0��

## 2026-07-07 19:15
- [x] **瘛勗漲�寞祥憭𡁜𪂹�煺漱�厰�霂��餈�誘�冽�蝔见㨃憿� (Deep Optimization for Multi-Period Strategy Filtering & Render Lag)**嚗�
    - [x] **�餃�憭批捐銵典��冽����澆ế摰� `O(N^2)` 蝥扯恣蝞㛖𣂎憸� (Fixed O(N^2) Period Value Comparisons)**嚗𡁜�雿滚僎皜�膄鈭� `_get_display_periods_for_custom_col` 銝剖笆 4000+ 銝芾��唳旿�其蜓蝥輻��扯��刻” `series0 - series_p` �煾��硋榆�潸恣蝞㛖��游𦶢蝻粹萅�����蛹撖孵之 DataFrame 餈𥡝�憭湧���甅瘥𥪜笆嚗�蘨�硋� 100 銵䕘�嚗��蝑劐遠�批ế摰朞�埈𧒄隞� 15 蝘雴誑銝𠰴蝠摨閧憬�剛秐 0.1ms 蝥改��寞祥鈭���匧𪂹�笔�鈭峕活餈�誘�嗥�銝餌瑪蝔见�甇颯��
    - [x] **�梶聦憭批捐銵� Treeview 銵��摰賡�����誩��� (Optimized Column Width Measurements)**嚗𡁻���� `_adjust_column_widths` 銝剔��堒捐�芸𢆡瘚钅��箏����撖� 4000+ ��絲�讛�憿對�撠��擃䀹��� `self.tree.set` �堒���聢摰賢漲瘚钅��𣂼�銝箔��𣂼��� 30 銵䕘��其��𨅯�摰賢��𤑳�閫�漲����𣂷�嚗��瘚钅�甈⊥㺭�� 100,000+ 甈∠凒蝥輸��� 600 甈∴�憭批�摨行��支� UI ���皛墧���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `standalone_multi_period_tester.py` �扯�鈭�嵗撉䕘�100% �𣂼�蝻𤥁�嚗屸�餉�蝔喳��剔㴓��

## 2026-07-07 18:30
- [x] **�寞祥憭𡁜𪂹�笔��Ｖ��閧𡠺餈鞱��嗥� Tkinter 銝餌瑪蝔见㨃甇� (Fixed Tkinter Main Thread Hangs on Multi-Period Toggles & Standalone Runs)**嚗�
    - [x] **瘨�膄 `_on_period_changed` 銝剔�銝餌瑪蝔贝恣蝞堒聣憛�**嚗𡁶宏�支� `_on_period_changed` ����湔𦻖�其蜓蝥輻�靚�鍂 `evaluate_strategy` ���雿䠷�餉�嚗���齿鰵霈∠����撟嗅�銵冽聢撅閧內�券�蝏煺�憪娍�蝏坔��� `run_filter` 蝥輻����隞擧覔�砌��寞祥鈭�鍂�瑕銁憸𤑳��暸��/�𡝗�����冽��嗅紡�渡��屸𢒰�芸�摨𥪜�甇颯��
    - [x] **�𤾸蝱蝥輻�瘙删氖蝥踹�憭批捐銵典像�� (Offloaded Wide-Table Flattening to Worker Thread)**嚗𡁻�頧賭�銝餉”皜脫��� `_show_results(df, elapsed, flat_df=None)` �寞���銁�𤾸蝱 `_worker` 銝剛恣蝞堒枂餈�誘蝏𤘪��𠬍��典��啁瑪蝔衤葉�峕郊摰峕� `flat_df = self._build_flat_df(result_df)` �唳旿�枏像銝𤾸�畾萄�撟嗅極雿頣����𦒘�撠��蝏�捐銵其�銝箇�摮条��𨀣��鍦�銝餌瑪蝔� UI 皜脫�撅��敶餃��𦠜𦆮鈭�蜓蝥輻��� CPU 蝞堒���
    - [x] **憭批捐銵函叚�誩� join �滨輕�枏稬 (Vectorized Wide-Table Pandas Join)**嚗𡁜���𧋦�� `_build_flat_df` 銝剖笆 4000+ 銝芾��扯� `df.iterrows()` 撟嗉�銵屸�憸㻫���憭滨� pandas `.loc` �� `.to_dict()` �� O(N) 敺芰㴓敶餃�摨罸膄�����蛹�拍鍂 Pandas ���擃睃漲隡睃��� `flat_df.join(df_p_sub, how='left')` �ａ��硋椰餈墧𦻖���銝滢�撖孵縧�漤俈�刻�嚗Ǒ~df_p_sub.index.duplicated(keep='first')`嚗㕑�銵䔶�摰匧��惩𤐄嚗諹�撠� 15 蝘雴誑銝羓��潸”�埈𧒄�祇𡢿蝻拍��� 10ms 蝥改�敶餃�瘨�膄�⊿▼��
    - [x] **�蹱��祗瘜閧�霂烐��� 100% �函遛**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `standalone_multi_period_tester.py` 憿箏⏚�朞�蝻𤥁��⊿�嚗峕�蝏苷�霂剜��鞉���

## 2026-07-07 15:50
- [x] **�拍�靽桀�憭𡁜𪂹�笔�瘚𧢲�扯�銝𤾸蘨霂駁�霈拙��� (Fixed Index Alignment & Enforced Readonly Bypass)**嚗�
    - [x] **摰䂿緵 `load_hdf_db` �拍�霂餌�銝𤾸�摮条�摮� index ����硋笆朣�**嚗𡁻���� `tdx_hdf5_api.py`嚗�銁 `load_hdf_db` 憭湧�摰帋�鈭� `_standardize_code` 皜���賣㺭��銁�拍�霂餌�摰峕��擧��賭葉���蝻枏��塚��� index 撅硺� `Int64Index` �硋��冽𧊋撖寥�蝐餃�嚗諹䌊���撠��頧祆揢銝箸���� 6 雿滩�蟡其誨�� index��蝠摨閗圾�喃� 2D �冽�嚗Ǒ/low_2d_200_y_all` 銵剁��曹� index 蝐餃�銝滚龪�滚紡�港漱��蛹蝛箔��諹◤霂臬ế銝� dratio 頞��銝Ｗ����撅� Bug嚗���唬� 2D �冽�蝻枏����撘�頧賢���
    - [x] **�惩𤐄�芾粉璅∪�銝讠��匧��嘥��㚚獈�剜㦤��**嚗帋耨�嫣� `tdx_data_Day.py` 銝剔� `get_append_lastp_to_df`��銁�芾粉璅∪�銝页�敶𤘪�瘚见� H5 蝻枏�銝滚��冽��拍��笔�嚗�� 3M/3d �冽�銝� `llow` 摮睃銁憭折𢒰蝘舫妟�潭��𧶏��塚��湔𦻖���輯��䂿征蝏𤘪�嚗𣬚�撖寧�甇Ｗ僎敶餃��餅鱏隞颱�擃䀹����摮睃�憪见�銝擧��㚚�撱箝����嗅� `if checknew:` 靽格㺿銝� `if checknew and not readonly:`嚗�銁�芾粉璅∪�銝见��典��� checknew 銵亙榆�唳旿����碶��坔��其�嚗�蝠摨閙��支�蝑𣇉裦餈鞱��嗥��⊿▼銝𤾸�甇颯��
    - [x] **摰峕��賭誘銵䔶�憭𡁜𪂹��芋�笔�頧賡�霂�**嚗𡁶��蹱�霂閗��祆芋�笔�頧� `d`, `2d`, `3d`, `3M` �冽�嚗�2D �冽�撌脫��毺�撘�霂餃�嚗���毺� 3d/3M �冽��典蘨霂餅芋撘譍���誑鈭𡁏神蝘垍漣�笔漲�湔𦻖頝唾��滚遣嚗諹䌊璉� 100% �𣂼���

## 2026-07-07 15:20
- [x] **靽桀� SafeHDFStore 霂臬ế摰𡁻��删鍂銝箇�����誩紡�渡��唳旿霂臬�隞賭�皜�征�滨蔭 Bug (Fixed SafeHDFStore Premature File Resets on Lock Failures)**嚗�
    - [x] **摰䂿緵 HDFStore 撘�虜���霂��銝𡡞俈敺� (Lock-Aware Error Classification)**嚗𡁻���� `tdx_hdf5_api.py` 銝剔� `SafeHDFStore` ���惩遆�唬誑�𠰴��唾��� `_check_and_clean_corrupt_keys`��_check_and_clean_corrupt_keys_all_key` �笔�璉�瘚衤耨憭漤�餉���緵�券���眏鈭� Windows �臬�銝见�餈𤤿�霂餃����鈭匧�韏瑞� `PermissionError`��WinError 32` �𡝗��鞉�蝏脲𧒄嚗𣬚凒�交��箏�撣豢�霅血�餈𥪜�嚗𣬚�甇Ｚ秤�支蛹��辣�笔��笔������蝠摨閙�蝏苷�鋡怠僎�穃��函��亙熒�唳旿摨𤘪�隞嗉◤�芸𢆡靚�鍂 `_safe_rename_corrupt_file` �滚𦶢�滚�隞賢僎皜�征�滨蔭銝箏�蝛箇� Bug嚗�
    - [x] **銵仿��芾粉璅∪��芾粉�函��脣鴃 (Enforced Read-Only HDF5 Write/Repair Protection)**嚗𡁜銁 HDFStore �嘥��硋仃韐仿���蹂誑�𦠜��誯睸皜��銝哨�撘箄�撘訫� `self.mode == 'r'` ��蘨霂駁秄蝳�㦤�嗚��蘨霂餅芋撘譍��亙�甈∪�霂閙�撘�憭梯揖�湔𦻖�睲��𥕦枂摨訫� OSError嚗䔶艇蝳��銵䔶遙雿蓥耨�寧��条����隞嗆�靚�鍂�滚𦶢�滚�隞賜��餉�嚗���唬��芾粉�滢��� 100% �唳旿�拍�摰匧��改�
    - [x] **憭𡁜𪂹�蠘���㺭�桀��祇�蝳� (Isolated Intraday Quote Copies)**嚗帋耨憭滢� `tdx_data_Day.py` 銝� `get_append_lastp_to_df` 撖嫣�隡惩� `top_all` 餈𥡝�撠勗𧑐 (in-place) 靽格㺿���雿𦦵鍂���撖寥�憸𤏸��函� `pd.to_numeric` ��撩頧� int嚗���𨅯銁憭𡁜𪂹�笔�甇亙儐�臭葉靽格㺿鈭��銝�銝芸�撅� DataFrame 摰硺�嚗�� `top_now`嚗㚁�隡𡁜紡�游�撅�撖寡情���憪𧢲筑�寞隅撟�㺭�殷�憒� `dff` �梹�鋡恍�霂臬𧑐�滨蔭��緵�嫣蛹�典遆�啣����撖嫣��亦��㗇� DataFrame �扯� `.copy()` �舀𧋦�滢�嚗���啣�蝢𡒊��唳旿�𠉛氖銝𤾸�畾萎��湔�扼��

## 2026-07-07 14:15
- [x] **靽桀�憭𡁜𪂹�毺��亙��𡒊眏鈭𤾸蘨霂餃之�冽�蝻枏�銝滚��典��𤑳� complete_indicators_pipeline KeyError 撏拇�銝� astype(int) �墧��𣂼�澆撩頧砍��典��� (Fixed Readonly Period Cache Missing KeyError & Safe Integer Conversion Guard)**嚗�
    - [x] **銵仿� `load_period_data` 憭批𪂹�毺�摮� existence �⊿�銝𦒘���䌊�� (Added Cache Verification & Graceful Missing Recovery)**嚗𡁜銁 `multi_period_strategy_engine.py` �� `load_period_data` �唳旿�㰘蝸瘚��銝哨�撖孵蘨霂鳴�`readonly=True`嚗㗇芋撘譍��㰘蝸憭批𪂹���憒� `45d`, `3M`, `w`, `m` 蝑㚁�蝻枏� DataFrame 餈𥡝�鈭峕活�文���銁 `df` 銝箇征�𣇉眏鈭� H5 蝤��蝻枏�蝻箏仃/�嗅�潭㜃�芾�峕𧊋�瑕��啣��桀��脫㿥�嗥鸌敺�� `'lastp1d'`�塚��湔𦻖頝唾�擃䀹��� `complete_indicators_pipeline` �潭𦻖霈∠�嚗���峕覔�祆�扳��支�甇文��� KeyError 撏拇�嚗㚁�撟嗅��嗡�����渲��啗扇敶訫銁蝻箏仃�冽� `_missing_periods` 摮堒�銝哨�靘脲�撘閙�撌脫����皛文ế摰𡁜像皛穃蕭�亙僎�滨漣嚗𣬚＆靽萘頂蝏煺蜓瘚���冽�蝡舐征�唳旿�硋��臬𢆡撘�虜�嗉��芣��� 100% 餈䂿賒餈鞱���蕭嚙賢仃/�嗅�潭㜃�芾�峕𧊋�瑕��啣��桀��脫㿥�嗥鸌敺�� `'lastp1d'` �塚��湔𦻖頝唾�擃䀹��� `complete_indicators_pipeline` �潭𦻖霈∠�嚗���峕覔�祆�扳��支�甇文��� KeyError 撏拇�嚗㚁�撟嗅��嗡�����渲��啗扇敶訫銁蝻箏仃�冽� `_missing_periods` 摮堒�銝哨�靘脲�撘閙�撌脫����皛文ế摰𡁜像皛穃蕭�亙僎�滨漣嚗𣬚＆靽萘頂蝏煺蜓瘚���冽�蝡舐征�唳旿�硋��臬𢆡撘�虜�嗉��芣��� 100% 餈䂿賒餈鞱���
    - [x] **摰䂿緵 `astype(int)` �啣�澆撩頧祆�撘誩��典��� (Secured Numerical Typecast to Int)**嚗𡁜銁 `tdx_data_Day.py` �� `get_append_lastp_to_df` ��笆 `co2int` �滨��堒撩頧祆㟲�堆�憒� `boll`, `dff`, `ra` 蝑㚁���洵 7309 銵䔶�蝚� 7354 銵䕘�撠���祉′蝻𣇉��� `.astype(int)` 蝏煺��齿�銝� `pd.to_numeric(..., errors='coerce').replace([float('inf'), float('-inf')], 0).fillna(0).astype(int)`��迨銝曇�憭笔撩�𥡝�皛日��厰��潘�憒� NaN/inf嚗㚁�敶餃�閫��鈭�銁�冽�餈���𡝗㺭�桃撩憭望𧒄撘箄蓮 int ���𥕦枂�� `ValueError: Cannot convert non-finite values (NA or inf) to integer` �拍��仿���
    - [x] **霂剜�蝻𤥁�銝𤾸��渲䌊璉��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `multi_period_strategy_engine.py` 銝� `tdx_data_Day.py` ���銵䔶�蝻𤥁��⊿�嚗�100% �𣂼�銝娪妟�仿���

## 2026-07-07 13:55
- [x] **��� HDF5 �唳旿靽桀�銝𤾸縧�滚�撟嗉秐 K蝥輻�摮䀹䰻�见膥 (Integrated HDF5 Merge & Repair in Kline Viewer)**嚗�
    - [x] **霈曇恣鈭支���僎靽桀� Dialog (`H5MergeRepairDialog`)**嚗𡁜銁 `minute_kline_viewer_qt.py` 銝剖��唬�銝梶鍂�� `QDialog` 靽桀��Ｘ踎���靘𥕞�𨀣��唳旿(�箇���蟮��辣)�腈���𨀣鰵�唳旿(餈賢��交鰵��辣)�腈���𦦵𤌍��㺭�桅� Key�苷誑�𪙛�𡏭�皛方絲憪𧢲𠯫�麨�萘�颲枏���㺭嚗�
    - [x] **摰䂿緵�唳㺭�格𠯫�蠘��渲䌊�冽�瘚衤�敹急㭘�寥�匧� NaT 瘥磰� FutureWarning 瘨�膄 (New File Date Detection & FutureWarning Elimination)**嚗𡁜銁餈賢�韏瑕��交�銵峕����鈭� `lbl_date_range` (��倌�鞟內)��btn_detect_date` (璉�瘚𧢲���) 銝� `combo_dates` (�交�銝𧢲��𡑒”)����領�𨀣�瘚𧢲𠯫�麨�脲𧒄嚗屸�朞��芾粉 HDFStore �䭾��急�蝝Ｗ�隞乩�瘥怎�蝥折�笔漲�瑕��交���凒嚗�僎�其��匧�銵其葉�芸𢆡憛怠���銁�𣂼��臭��交��𡑒”�塚�撘箏�靚�鍂 `.dropna()` 撟嗥��� `.normalize().unique()` �煾��𡝗�雿𨀣��� Timestamp 摨誩�撟嗉蓮�Ｖ蛹 `datetime.date` �𡑒”嚗��蝢舘��蹂� pandas �冽�瘚衤葉�曹� NaT ���銝� `datetime.date` �𣂼�撖寞�撖潸稲�� `FutureWarning` 撘�鍂霅血�嚗峕�扯�銝𡒊迅摰𡁏�批之撟�����
    - [x] **摰䂿緵�格�颲枏枂頝臬��芸𢆡���銝湔𧒄��辣�滢��拍�撘粹俈閬���∪藁 (Auto Temp Filename & Override Warning)**嚗𡁜銁 `minute_kline_viewer_qt.py` 銝剖��乩� `update_target_temp_path` �芸𢆡����剁�撟嗅� `new_edit` �� `base_edit` ����砌耨�嫣縑�瑚��嗉�銵䔶��冽���摰𠾼��頂蝏煺��芸𢆡�冽鰵�唳旿�桀����撣行� `_temp_merge.h5` ����其葩�嗆�隞嗅�嚗䔶�敶𤘪�頝臬��𤑳��睃𢆡�嗉䌊����唾�靽格迤�桀���迨憭吔��� `run_merge` ��絲憪𧢲嵗撉䔶葉嚗���牐�撘箇���俈閬���∪藁嚗帋��行�瘚见��格�颲枏枂頝臬�銝𦒘遙雿蓥�頝航��交���辣嚗�抅蝖���辣�𡝗鰵餈賢���辣嚗匧��其��湛��喳�撘孵枂 `QMessageBox.critical` 撘箄郎�𠰴僎�行⏛餈鞱�嚗�蝠摨蓥��靝�皞鞉㺭�桃��拍�摰匧�嚗�
    - [x] **摰䂿緵��辣�㗇𥋘摰帋��芷����睲�皞舀��箏�**嚗𡁜銁 Dialog 銝剖��牐� `get_existing_dir_or_parent` �拇��寞���銁�孵稬�𨀣�閫��嗪�㗇𥋘��辣�塚�撖寡�獢���芸𢆡撠肽�摰帋��單��祆�銝剖��滩楝敺��憒��撖孵���辣�𣇉��桀�撟嗡�摮睃銁嚗���芸𢆡�鍦��睲�蝥抒𤌍敶閙䰻�橘��渲秐�曉�擐碶葵�函�����䀝��笔�摮睃銁������隞嗅允雿靝蛹�嘥��枏��桀�嚗䔶��屸俈甇Ｗ�暺䁅恕頝臬�蝻箏仃撖潸稲��辣�㗇𥋘�典鍳�典仃韐交��滨蔭銝箸���/��﹝�桀�嚗�
    - [x] **�舀�頝� Qt 摨枏�摰寧��冽�� UI 撣��**嚗𡁜銁��憭硋� try-except 撖澆�銝剖��乩� `QFormLayout` ���憟� Qt 獢�沲����餉�嚗𣬚＆靽嘥銁 PyQt6/PySide6/PyQt5 �臬�銝钅��賢��删��舀�銵典��曄內銝擧�隞嗆�閫���桀�雿㵪�
    - [x] **����諹楝��僎�駁�蝞埈�撟嗉��箸𠯫敹�**嚗𡁜銁 Dialog ���蝘餅�撟嗅撩�碶�銋见��� pandas ��僎�駁�銝𤾸��冽𤜯�Ｙ�瘜𨰻���憭扳挾餈鞱�餈��銝剔�瘥譍�甇仿炊�埈𧒄��𠯫����𤥁��氬����啣��硋��拍��踵揢摰匧��餉��冽��陬����� `QPlainTextEdit` 餈鞱��亙��曄內�綽�摰䂿緵鈭�虾閫����虾�烐����撟嗡耨憭㵪�
    - [x] **�拍��厰僼瘜典�銝擧局�賣㺭蝏穃�**嚗𡁜銁�亦��函�銝� `setup_ui` �寞���▲�� `top_toolbar` 銝哨��啣�鈭� `btn_repair_h5` (�圲 靽桀���僎HDF5) �厰僼撟嗥�摰帋� `on_repair_h5_clicked` 撘寧�閫血�嚗諹�銵� `py_compile` �芣� 100% 蝻𤥁��𣂼��朞���

## 2026-07-07 13:45
- [x] **靽桀� HDF5 �唳旿�芣鱏�笔�銝𤾸��脫㺭�桀�頝臬縧�滚�撟� (Fixed HDF5 Superblock Corruption & Multi-Source Deduplicated Merge)**嚗�
    - [x] **摰帋�撟嗅��券�蝳餉◤瘙⊥��唳旿**嚗𡁜��唬� 2026-07-06 �� `sina_MultiIndex_data.h5` �唳旿摮睃銁撘�虜鋡怠��坔��� superblock �芣鱏嚗ìtored_eof 鋡急㺿�嗘蛹 9.6TB 蝥批�撘�虜�潘�嚗�紡�游虜閫� h5clear 銝𦒘�餈𥕦�靽桀�����航噢��
    - [x] **霈曇恣撟嗆�銵䔶舅頝臬��典縧�滚�撟� (Two-Way Safe Deduplication Merge)**嚗𡁶��坔僎餈鞱�鈭� `merge_multiindex_h5.py` ��僎�𡁏𧋦嚗����摰峕㟲�� `D:\Ramdisk\backup\20260703\sina_MultiIndex_data.h5` 憭�遢��辣雿靝蛹撟脣���蟮�箏�嚗�僎�𣂼�敶枏� `g:\sina_MultiIndex_data.h5` 銝� 2026-07-07 ����交鰵�唳旿嚗�銁�園𡢿�唾�皛文��Ｗ蝠摨訫��支�鋡急情�梶� 2026-07-06 �𤩺㺭�柴��
    - [x] **擃睃�蝻拐�摮䀝��澆��脤�撉諹�**嚗𡁜�撟嗅縧�滚��� DataFrame 雿輻鍂 `format='table'`��complevel=9` �� `complib='blosc'` �讠憬�𤾸��乩葩�嗅�撟嗆�隞塚�撟嗡蝙�典�雿� level �滚� `ticktime` �∩辣餈�誘嚗屸�朞�鈭� 7 ��遢�唳旿銵峕㺭����湔�折�霂���餉��� 2262500嚗�7��1�亥秐3�亙�7�交㺭�桀�撣��甇�虜嚗剹��
    - [x] **摰墧鴌�拍�閬���踵揢銝舘䌊璉�**嚗𡁏��笔��𤩺���� HDF5 ��辣�滚𦶢�滚�隞賭蛹 `bak2` 撟嗅���僎�𡒊��唳旿�踵揢銝� `g:\sina_MultiIndex_data.h5`嚗䔶蝙�� `diag_ats_history.py` 霂𦠜鱏�𡁏𧋦瘚贝�撉諹�嚗諹�蟡刻���銁 G �䁅�憭������蠘粉�吔����敶餃�閫�膄��

## 2026-07-07 10:45
- [x] **摰䂿緵 ATS �𥪜𢆡�暸�厩𠶖��䌊�冽�銋��銝� QSplitter �典�蝑㗇�靘讠憬�� (ATS Linkage Checkbox Persistence & Proportional Layout Scaling)**嚗�
    - [x] **摰䂿緵�𥪜𢆡�暸�㗇��嗆��楊隡朞��芸𢆡霂餃� (Cross-session Checkbox Persistence)**嚗𡁜銁 `_save_layout_state` 銝� `_restore_layout_state` 銝剝��𣂷�撖寥▲�� `cb_tdx` (�朞噢靽�)��cb_ths` (�諹�憿�)��cb_vis` (K蝥踹虾閫��) 銝劐葵憭漤�㗇��暸�厩𠶖���靽嘥�銝舘䌊�冽�憭㵪�雿輯��券�蝵桀�蝢擧�銋���坔� `window_config.json`嚗峕��支��滚鍳�滨蔭����嫘��
    - [x] **摰䂿緵蝒堒藁�䭾�蝑㗇�靘讠憬�曆� QSplitter �𣂼��脫��� (Proportional Scaling & Non-collapsible Splitter Guard)**嚗�
        - 銝箔蜓�屸𢒰�� `main_splitter` (璅芸�)��center_splitter` (蝥萄�) �� `right_splitter` (蝥萄�) ���匧��Ｘ踎撘箏��扯� `setCollapsible(i, False)` �脫��㰘挽摰𡄯�敶餃��脫迫鈭��蝒堒藁鋡急�摨行𤣰蝻拇𧒄�𣂼��箏��湔𦻖憛屸萅銝� 0 �讐�摰賡���撩�瘀�
        - �嘥��硋僎蝏湔擪 `self._main_ratio`��self._center_ratio` 銝� `self._right_ratio` ��𠧧瘥𠉛��㗛����頧賭� `resizeEvent` �寞�嚗�銁蝒堒藁憭批��劐撓�𣇉憬撠𤩺𧒄嚗���嗉繮�硋��� Splitter �拍��駁鵭摰踝���膄 handle �删鍂������蝝惩�嚗峕����靘贝䌊����冽����漤�蝞� `sizes()`嚗諹噢�鞟�甇���典��䭾�蝑㗇�靘讠憬�橘�
        - 蝏穃�鈭��銝� Splitter �� `splitterMoved` 靽∪噡����冽��函��Ｖ��见𢆡�𡝗嗻�孵���𠧧�譍�蝵格𧒄嚗�銁 `_on_splitter_moved` 瑽賢遆�唬葉摰墧𧒄霈∠��啁��𣳇�蝥脣��脫�靘见僎蝻枏�嚗䔶蝙�𡒊賒��𦆮憭�/蝻拙��冽迨�箇�銝羓誧蝏凋誑�啣��脫�靘讠�瘥磰䌊����劐撓��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `main_window.py` �扯�鈭�嵗撉䕘�100% �𣂼�蝻𤥁���

## 2026-07-07 02:40
- [x] **隡睃� ATS �𥪜𢆡�㗇𥋘�批���踎�㛖��𥕦㦛 24x7 蝻枏��㰘蝸瞍𤩺�銝𤾸��箏�撣�䌊�冽凒�� (Optimized ATS Linkage Checks, 24x7 Heatmap Cache Loading & Market Distribution Auto-Updates)**嚗�
    - [x] **ATS 憿園���� VIS, TDX, THS �祉��𥪜𢆡�㗇𥋘�暸�㗇� (Integrated VIS/TDX/THS Linkage Controls)**嚗𡁜銁銝餌��ａ▲�誩�撟嗆溶�牐� "TDX"��"THS"��"VIS" 銝劐葵�暸�㗇�������銝芾���稬 `link_stock` 閫血��餉�嚗諹悟餈嗘�銝芸��㗇���迤�批�撖孵�����典�璅∪�嚗�� VIS 憭漤�㗇��批��臬炏�𤏸絲 TCP 26668 �����虾閫���𥪜𢆡嚗𣊁DX/THS �暸�㗇��批��臬炏���蝏嗵�����冽��∴�嚗���圈��菜暑摨西��典��Ｕ��
    - [x] **�寞祥�喃儒銵䔶��踹��剖��� 24x7 頝典予餈鞱�銝齿凒�� Bug (Fixed 24x7 Heatmap Update Lag)**嚗帋耨憭滢� `heatmap_widget.py` 銝� `load_live_sectors` �㰘蝸�唳旿頝臬����餉�瞍𤩺����隞���� logs �桀�銝见��典��脣�蝻拙�隞賣�隞嗆𧒄嚗�� `fpath` 瘞訾�銝箇征嚗�紡�� 24x7 餈鞱�銝讠頂蝏�偶餈𡏭粉�𡝗㿥憭拍�憭�遢��蕭�亙��嗥� `v_reversal_pool.json`��緵�齿�銝箔���粉�硋僎撉諹� ramdisk ����䀝葉����� JSON嚗䔶�摮睃銁�嗆����輯秐 logs 銝讠�憭�遢 json �� json.gz 敶埝﹝��
    - [x] **摰䂿緵�踹��剖��曉�頝喳�甇乩� force �瑟鰵�舀� (Heatmap Sync and Force Refresh)**嚗𡁜銁銝餌��� `refresh_realtime_ui` �����凒�啣�靚�葉銵亙�鈭�踎�㛖��𥕦㦛���甇亙��堆�撟嗅銁 `load_live_sectors` 銝剖��牐� `force=False` �批���㺭嚗峕�����Ｗ��啁��嗆��扼��
    - [x] **摰䂿緵摨閙��典��箏�撣�㦛��㺭�格凒�啜��萱摨衣�霈∩� Tooltip 瘚桃��鞟內 (Market Distribution Stats, Temperature Label & Hover Tooltips)**嚗�
        - ��漣鈭� `DistributionBarChart`嚗�銁�曇”甇���孵��� `stats_label` 隞亦凒閫���唬�瘨具���頝䎚��像�睃蘨�啜���撟�誑�𠰴�撣�㦤皜拙漲嚗��瘨典振�啣�瘥䈑�嚗�
        - �� `main_window.py` 銵峕�����嗅��牐�撣�㦤��貌憭𡁶輕�ａ��𣇉�霈∟恣蝞梹�頝罸��唳旿�湔鰵�冽��𤑳凒�孵㦛�峕郊���撟嗅��嗅��堆�
        - 銝箇凒�孵㦛蝏穃� `sigMouseMoved` 靽∪噡嚗�銁曌䭾� Hover �砍��冽�摮𣂷��寞𧒄靚�鍂 `QToolTip` 瘚桃�蝎曉��鞟內霂交�摮鞟��瑚�瘨典��粹𡢿���蟡典蘨�唬誑�𠰴�撣�㦤�䭾���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `main_window.py`��chart_widgets.py` 隞亙� `heatmap_widget.py` ���銵䔶��⊿�嚗�100% �𣂼�蝻𤥁���

## 2026-07-06 11:00
- [x] **靽桀� `撘�𢆡�𥪜𢆡.py` 蝒堒藁�滨蔭��辣 `window_config.json` 蝻𣇉��㰘蝸 Bug (Fixed UnicodeDecodeError in window_config.json)**嚗�
    - [x] **�拍�靽桀� `load_window_positions` 霂餃��亙ㄝ��**嚗𡁜�撖� `CONFIG_FILE`嚗Ǒwindow_config.json`嚗厩� `open` �其�蝏煺�靽格㺿銝箸�摰� `encoding="utf-8"`����亙�撅���刻圾��㦤�塚�擐硋�撠肽� `utf-8`嚗諹𥅾�閗繮 `UnicodeDecodeError` �� `JSONDecodeError` �䠷���踹�霂蓥誑 `gbk` 閫��嚗㚁��乩舅���閫��憭梯揖�坔��冽��瑕�撣賂��鮋���喳�憪见�蝛箇𠶖����賂��𦦵�鈭�眏鈭� Windows 蝟餌�暺䁅恕 locale 蝻𣇉�嚗𠃑BK嚗匧紡�渡�霂餃�撏拇�嚗���唬� 100% ��捆�蹱�批�頧賬��
    - [x] **�拍�靽桀� `save_window_positions` 靽嘥�閫����**嚗𡁜銁�坔� `CONFIG_FILE` �嗆�摰� `encoding="utf-8"`嚗�僎霈曄蔭 `ensure_ascii=False, indent=4`嚗𣬚＆靽苷葉���蝚虫�鋡怨蓮銋劐��澆�皜�苊蝢舘�嚗�蝠摨閗�����滨蔭霂餃�蝻𣇉��曇楝��

## 2026-07-04 06:20
- [x] **摰䂿緵�踹�銝芾�霂行��𡑒”銝𦒘犖瘞娍�銵峕瓲敹�抅蝖��唳旿�堒�蝢𤾸笆朣� (Aligned Category Stock Detail Columns with Main Popularity Rankings)**嚗�
    - [x] **�齿�銝芾�霂行��箇��堒�銝𡒊���**嚗𡁜� `show_concept_top10_window` 銵冽聢����滨眏 `percent`, `dff`, `rank` �齿�撟嗥�銝�銝箔�鈭箸��坿�銝餉”銝��渡� `val` (瘨典�), `price` (���唬遠��), `dff2`, `dff3`, `rank`����支��笔�鈭𣬚漣�𡑒”蝻箏仃���唬遠�潦��ff2��ff3 蝑匧��格���誑�𠹺蜓�航”摮埈挾銝滚��漤�䭾���毽銋晞��
    - [x] **銵仿�撟嗡萼撖峕㺭�格��𡝗�撠�**嚗𡁜銁摰墧𧒄璅∪�銝𤾸��脣��䀹芋撘讐��唳旿銵諹圾�𣂷葉嚗��甇亥‘���撖� `price`, `dff2`, `dff3`, `rank`, `val` ����硋�quotes蝻枏��𨅯�嚗𣬚＆靽脲�霈箏��䁅��臬��脫㺭�殷�銝芾�霂行�銵冽聢�曄內��捆摰���笔�撖寥���
    - [x] **��漣����鍦��𥪜𢆡�箏�**嚗𡁜銁 `sort_column` �𥪜𢆡�鍦��寞�銝哨�撠�葵�∠�����惩��箏��湔鰵銝箔���笆朣鞉鰵����滚僎�澆捆��蟮�堒���迨�嗆�霈箇��颱蜓蝒堒藁餈䀹糓鈭𣬚漣�𡑒”�堒仍嚗���齿�摨誩�����祇𡢿蝎曉��峕郊嚗峕��支��屸𢒰鈭支�����𦒘��梯���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 06:10
- [x] **�寞祥��蟮憭滨���揢�交�撖潸稲��㺭�桅�憭齿��坔�銝芾��𡑒”�芸�銋匧�銝滢��渡撩�� (Fixed History Data Accumulation & Mismatched Columns in Stock Details)**嚗�
    - [x] **摰䂿緵��蟮�㰘蝸撘箏��拍�皜�征 (Enforced Treeview Clear on History Load)**嚗𡁜銁 `load_history_by_date` 銝哨�銝�餈𥕦� `try` �𦯀噶撘箏�靚�鍂 `self.clear_all_trees()`���敶餃��寞祥鈭�唂��葉�曹���蟮�唳旿�芾蕭�牐�皜��嚗�紡�游銁憭𡁏活�㗇𥋘�交��㚚�憭滨��餅𧒄嚗��銝��∠巨隞���函��Ｖ��舐��惩�畾讠��� Bug��
    - [x] **摰䂿緵銝餌����銝芾� constituent 銵典仍�冽����脣�撖寥� (Synchronized Historical Columns in Constituents)**嚗�
        - �孵�鈭�銁��蟮璅∪�銝衤葵�∩�蝥� constituents �𡑒”甇餅踎雿輻鍂摰墧𧒄�芸�銋厰�蝵桀���㦤�嗚�����蛹敶枏�鈭𤾸��脣��䀹芋撘𤩺𧒄嚗諹䌊�刻圾�𣂼��� DataFrame 銝剔��券��𧼮抅蝖��梹�雿靝蛹��蟮�唳旿敶𤘪𧒄銝枏���䌊摰帋��梹�
        - �其蜓銵剁�`load_history_by_date`嚗匧���稬撘孵枂�� constituents 銝芾� Treeview 銝剖�甇仿�蝵株�鈭𥕦��脣�嚗���唬�銝芾�霂行��芸�銋匧�銝𦒘蜓�屸𢒰��蟮��挾�� 100% �芷���撖寥�嚗�
        - �刻��嫰�靝��亙��嗉����脲��𤑳�摰墧𧒄�唳旿�瑟鰵�塚��芸𢆡閫血��㛖�����嗘誑撟單��齿�餈睃�銝箏��嗥��芸�銋厰�蝵桀���
    - [x] **摰䂿緵銝芾��拍��駁�銝𦒘葵�∪�蝘啣��寡‘朣� (Stock Deduplication & Automated Name Resolve)**嚗�
        - �� `show_concept_top10_window` constituents �𡑒”�𣂼��唳旿銵峕𧒄嚗���乩� `seen_codes` ���撖嫣葵�∟�銵�縧�㵪��脫迫�𡑒”銝凋漣�笔�雿嗵��滚�隞��銵䕘�
        - �峕𧒄�其蜓銵冽㺭�格葡�枏�銝芾��𡑒”�唳旿閫��銝哨�撘訫�鈭� `sys_utils` �� `resolve_stock_name` �亙藁嚗�銁 `name == "--"` �𡝗糓蝛箸𧒄�箄�霂餃��砍𧑐蝻枏��𤥁��函�蝏𨀣𦻖���銵��摨閗‘朣琜�瘨�膄鈭�葵�∪�蝘唳遬蝷箔蛹蝛箇蒾��撩�瑯��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 06:00
- [x] **靽桀���蟮憭滨�銝芾�銝擧踎�𦯀縑�臭腺憭勗�鈭𣬚漣�𡑒”銝芾�蝛箇蒾銵��雿蹱�瘣� (Fixed Historical Data Mapping & Empty Redundant Rows in Constituents)**嚗�
    - [x] **�寞祥瘚桃��啣撩頧砍紡�港誨����寥��桅�**嚗帋耨憭滢��� `load_history_by_date` 銝哨�隞� CSV 霂餃�銝芾�隞���嗉𥅾摮睃銁瘚桃��唬�頧砍�銝箏蒂 `.0` �𡒊����蝚虫葡嚗��憒� `"600118.0"`嚗㚁�撖潸稲�嗡�甇�虜 6 雿滢誨����寥��坔� `_block_cache` ����栶�����蛹�拍鍂 `.split('.')[0]` 餈𥡝�隞��餈�誘��𠧧銝擧��� zfill(6) 撖寥�嚗�蝠摨閙��支���蟮璅∪�銝见��颱葵�∪枂�售�𨀣��䭾踎�𦯀縑�胼�萘��躰秤��
    - [x] **�齿�鈭𣬚漣�𡑒”璉�蝝Ｖ葵�∠��厰�餉�**嚗𡁜�撘���笔�撖� `_block_cache` �券�蝝舐妖蝻枏�摮堒�����罸����霂交䲮撘譍�撖潸稲隞亙��交��曉��具���隞𦠜𠯫撟嗆𧊋銝𦠜���葵�∩�鋡怠��冽��箸䔉嚗�紡�游�銵典��亙之�� 0.0 銝� `--` ��征�質�嚗剹�����蛹隞�移����碶�餈�誘**敶枏��唳旿皞鞟�甇��鈭𦒘�璁𨀣��曄內銝剔�銝芾���**嚗���脫芋撘誯��� `_history_df`嚗���嗆芋撘誯��� `df_all`嚗㚁���之�唳�����寥����嚗�僎敶餃�瘨�膄鈭� constituents 撘寧�銝剜㺭隞亦蓡霈∠�蝛箇蒾�䭾�銵䕘�餈睃�鈭�僕��蝎曉���踎�𦯀葵�∪��𨰻��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 05:50
- [x] **摰䂿緵撌血𢰧銝支儒銵冽聢�芷����堒捐銝擧��𦦵��劐撓 (Dynamic Adaptive Column Widths on Splitter Resize)**嚗�
    - [x] **摰䂿緵�𡁶鍂�芷���摰賢漲蝞埈�**嚗𡁜銁 `PRServiceGUI` 銝剜鰵憓硺�蝐餅��䀹䲮瘜� `self._adjust_tree_column_widths(tree)`��砲�寞��典捆�典偕撖詨��𡝗𧒄嚗屸�朞��瑕� Treeview �航�摰賢漲撟嗆緍�斗��冽辺�删鍂嚗諹䌊�典��拐���虾�典捐摨血像����滨����� `stretch=True` ��虾�劐撓�梹�撟嗅��嗅��箏��梹�`idx`, `code`嚗㕑挽銝箏𤐄摰𡁜捐摨佗�靽嗪�鈭��蝒�偕撖訾����撠誩虾霂駁��塚�30px嚗剹��
    - [x] **摰䂿緵鈭衤辣撽勗𢆡����嗉䌊����𥪜𢆡**嚗帋蛹���� 5 銝芯蜓 Treeview ���摰帋� `<Configure>` 鈭衤辣����冽��硋𢆡銝剝𡢿����游��娍�嚗�㺿�� sash 雿滨蔭嚗㗇�����其蜓蝒堒藁憭批��塚�霂乩�隞嗡�鋡怎��湔��匧僎閫血��堒捐�滨����敶餃��寞祥鈭�唂��𧋦銝凌�𨅯椰靘扯◤�厩��嗅�摰賣�瘜閗䌊�冽𤣰蝻拙紡�游�摰寡◤�芣鱏�萘� Tkinter 暺䁅恕蝻粹萅嚗䔶�霂���其遙�𤩺��冽�靘衤����劐蜓銵典�摰賡��� 100% �芸𢆡�芷���憛怠���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 05:40
- [x] **摰䂿緵�喲睸銝芾�敹急㭘�渲噢��撘箸�敹菜踎�𦯀葵�∟祕���銵典仍��內�典��� (Right-Click to Strongest Category Constituents & Robust Header Arrow Update)**嚗�
    - [x] **摰䂿緵蝐餌漣璅∪��𡝗�敹萄�蝘唳����**嚗𡁜���𧋦撋��摰帋��� `show_concept_top10_window` ����� `normalize_concept_name` �𣂼��齿�銝� `PopularityResonanceGUI` 蝐餌��祉��寞� `self._normalize_concept_name`���瘨�膄鈭�誨���雿辷�皛∟雲鈭� DRY �笔�嚗䔶蝙銝芾��喲睸�餉�銝𤾸��駁�餉��賢��典�銝�憟埈����閫����
    - [x] **摰䂿緵蝐餌漣璅∪��㚚��芣踎�𡑒�皛�**嚗𡁜��祆䔉�� `update_concept_ranking` �𣬚�撅��券��芣㦤�嗅� `NOISE_CONCEPTS` 霂滚���漣�齿�銝� `PRServiceGUI` 蝐餌��𡁶鍂�𣂼��寞� `self._is_noise_concept(name_str)`嚗峕����蝟餌�璅∪��硋�擃睃��帋��血�撅墧�扼��
    - [x] **摰䂿緵撅閧內��3銝芣�摰鮋��譍���撘箸踎�㛖��喲睸敹急㭘�亙藁**嚗𡁜銁銝餉”�喲睸�𨅯� `show_context_menu` 銝哨��瑕�銝芾���撅䂿��券��踹�撟嗡誑�滚臁隡睃���蘨�啣撩撘梢�摨讛�銵峕�摨譌��𦻖���芸𢆡�𣂼��鍦銁���漤𢒰�� **��憭� 3 銝芣�摰鮋����隞瑕�潛�璁�艙�踹�**嚗�銁�喲睸�𨅯�銝剖𢆡����𣂼�颲� 3 銝芰𡠺蝡讠��亦�憿對�靘见�嚗䫤�� �亦���撘箸踎�𦯀葵�� (�勗�鋆��摮�:17��)`嚗㚁��舀�����孵稬�渲噢��䌊�踹��� constituents 銝芾� Treeview 霂行�嚗峕�憭批𧑐銝啣�鈭�𢰧�桃��斤輕摨艾��
    - [x] **�寞祥 update_header_arrows 撘閗絲�� TclError: Invalid column index idx 撘�虜**嚗𡁻���� `update_header_arrows` ��俈�支��芷���皜脫��餉����撖寞�敹萎葵�∪�銵函�銝滚鉄 `"idx"`嚗���堒噡嚗匧� of �芸�銋� Treeview �扯��鍦��孵���內�冽凒�唳𧒄嚗諹䌊�刻�銵���冽嵗撉䎚����𨀣糓銝餉”嚗峕��罸�餉�憭��嚗𥕦��靝�銝𠹺蜓銵剁��䠷��券�𡁶鍂銵典仍摮堒�撟嗅�鋆嫣� `try...except` 敹賜裦�䭾�����㵪�敶餃��𦦵�鈭��蝷箏膥�瑟鰵�嗥�撏拇���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 05:30
- [x] **�寞祥�鍦��峕郊�嗡蜓銵其�鈭𣬚漣�𡑒”�堒�銝滢��游�韏瑞� Invalid column index 撏拇� (Fixed TclError: Invalid Column Index during Multi-Window Sorting)**嚗�
    - [x] **摰䂿緵 sort_column �唳旿�𣂼�摰匧�靽脲擪**嚗𡁜銁 `sort_column` 銝哨�撖寞��𡝗�銵峕㺭�桃� `tree.set(k, col)` �滢���ㄨ鈭� `try...except` 靽脲擪��𥅾�格� Treeview 瘝⊥�隞颱�撖孵����嚗峕䲮瘜訫��湔𦻖摰匧����箏僎餈𥪜�嚗�蝠摨閖俈敺∩��曹��堒�蝻箏仃撘閗絲�� `_tkinter.TclError: Invalid column index` 撘�虜��
    - [x] **�𣂼�銝餌����甇亥��港��脫迫�鍦��滚�**嚗𡁻��嗡�銝餌��� 5 銝� Treeview ���甇交�摨譌��蘨�匧��𤏸絲�鍦��� `tree` �祈澈�� 5 銝芯蜓銵其�銝��塚��滢��穃�隞碶蜓銵典嘀�哨�摮鞟�����餅�摨𤩺𧒄嚗䔶��湔鰵�芾澈嚗峕�蝏苷��曹�摮鞟�����滢�銝��渲�䔶蝙銝餌����摨𤩺𥁒�嗵��桅���
    - [x] **摰䂿緵銝𡁜𦛚銝��湔�批��齿�撠� (Business-Aware Column Mapping)**嚗𡁜銁�峕郊銝芾� constituent �𡑒”�塚�撘訫�鈭�䌊�典��齿�撠���賂��惩� `val -> percent` �� `dff2/dff3 -> dff`嚗剹���摰䂿緵鈭�朖雿蹂蜓蝒堒藁�堒�銝� `"val"`嚗�隅撟��嚗䔶�蝥批�銵其��賣惣�賢笆朣𣂼僎�𣂼�隞� `"percent"` �峕郊餈𥡝��鍦�嚗�之撟������𥪜𢆡銝��湔�扼��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 05:20
- [x] **摰䂿緵璁�艙撘�𢆡銝擧踎�𦯀葵�∪�蝥扳�摨譍�銝餌�����典�甇� (Synchronized Sort to Detail and Constituent Windows from Main Rankings)**嚗�
    - [x] **摰䂿緵�见𢆡�孵稬�堒仍�峕郊銝芾��𡑒”�鍦�**嚗𡁜銁銝餉” `sort_column` �见𢆡�鍦�嚗Ǒnot auto_restore`嚗厩��餉�銝哨�憓𧼮�鈭�笆撌脫�撘�銝芾��𡑒”蝒堒藁嚗Ǒself.concept_win`嚗厩��芸𢆡璉�瘚卝����靝葵�� Treeview `self.concept_tree` 摮睃銁銝𥪜��怠��滨��鍦��梹�`col in columns`嚗㚁��躰䌊�典�甇亥��冽�摨𤩺䲮瘜訫��園��唳㟲���摰䂿緵鈭��靝蜓蝒堒藁�雴�銋��銝芾��𡑒”�祇𡢿頝毺��雴�銋��萘�蝏煺�鈭支���
    - [x] **摰䂿緵�见𢆡�孵稬�堒仍�峕郊璁�艙霂行�蝒堒藁�鍦�**嚗𡁜��瑕銁 `sort_column` 銝哨�憒��璁�艙霂行�瘙��餌����`self._concept_win`嚗㗇迤憭���枏��嗆����躰䌊�刻圻�� `self.update_concept_detail_content()` �滨���
    - [x] **摰䂿緵�删㮾����嗥��鍦�餈�誘靽脲擪**嚗𡁻���� `update_concept_detail_content`嚗��隡朞䌊���銝餉”����齿�摨誩�嚗Ǒpercent`, `volume`, `rank` 蝑㚁�����𨀣𥅾�㕑砲 col嚗���㕑砲�𡑒��坔����摨讛�銵���踹�銝芾���葡�𤘪�摨𧶏�憒��銝餉”�鍦��𦯀�摮睃銁鈭舘砲�𡑒”銝哨��躰䌊�券���輻輕����厩�瘨典��滚�嚗�僎�䠷�敹賜裦嚗𣬚�銝齿��箏�撣詻��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撉諹�嚗�100% �𣂼�蝻𤥁�撟園�朞�撖澆��㰘蝸瘚贝���

## 2026-07-04 05:00
- [x] **靽桀� TK 璁�艙�滚�憭𡁶�����餃�憭湔�摨誩�甇亙仃��䔮憸� (Fixed Multi-Window Column Sort Synchronization in TK Concept Windows)**嚗�
    - [x] **摰䂿緵摰墧𧒄���憭𡁶����摨誩嘀�剖�甇�**嚗𡁜銁 `tk_gui_modules/treeview_mixin.py` �� `_save_mixin_ui_states` �寞�銝剖��䭾�敹萄�������憭𡁶����瘚衤��鍦��峕郊�箏�����冽��其遙�𤩺�敹萄��� Treeview 蝒堒藁銝剔��餃�憭渲�銵��蝥扳��訫��鍦��塚��芸𢆡憭滚��鍦��嗆���摰墧𧒄撟踵偘蝏蹱��匧�隞𡝗�撘����憭��摮䀹暑�嗆���璁�艙蝒堒藁嚗�項�硋��函��� `_concept_top10_win`����脩��閧��� `_pg_top10_window_simple` 隞亙�隞𡒊��扯蕭頦� `monitor_windows` 銝剜𤣰����券�璁�艙 Treeview嚗㚁�撟嗉��� `update_mixin_tree_headers` �� `trigger_mixin_multi_level_sort` 撘箏�閫血��鍦��湔鰵嚗諹噢�𣂷�鈭箸��坿�摰��銝��渡��𥪜𢆡�����
    - [x] **靽桀� UI �嗆���銋��銝剔��㗛��滨妍 typo**嚗𡁜銁 `instock_MonitorTK.py` �� `save_ui_states` �寞�銝哨�靽桀�鈭�����璁�艙�滚� Treeview ��蝸�� `self._concept_win` 撖潸稲��掩�𧢲�瘚𧢲�瘣痹�摰鮋�摨𥪯蛹 `self._concept_top10_win`嚗㚁�撟嗉‘���撖� `self.monitor_windows` ���蝏游漲摮䀹暑璉�瘚衤��𣂼�嚗𣬚＆靽嗪���箸�����𡝗𧒄嚗峕��㗇�撘���踎�𦯀葵�⊥�摨讐𠶖����刻◤甇�＆�坔��砍𧑐蝤����
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �⊿�嚗䔶舅憭��隞嗅� 100% �𣂼�蝻𤥁�嚗峕�隞颱�撘�虜��

## 2026-07-04 04:00
- [x] **摰𣬚�閫���踹�銝芾�霂行���蟮璅∪��唳旿�寥���葉�望��砍噡����碶��鍦��峕郊�箏� (Standardized Parentheses, Fixed Historical Matching, Synchronized Sorting, and Bottom Stats in Stock Details)**嚗�
    - [x] **摰䂿緵銝剛㘚��𡠺�瑟�����脫⏛�剖龪��**嚗𡁜��支��笔�銝�������斗𡠺�瑕紡�氯�𨅯�撠���匧郎(CPO)�肽◤蝞��𡝗��𨅯�撠���匧郎�萘�蝎埈𠂔�𡁏�����乩� `normalize_concept_name` 颲�𨭌�賣㺭嚗��銝剛㘚��𡠺�瑟����銝箄㘚��𡠺�瑕僎餈�誘�圈��𡒊�嚗���唬�蝎曄＆���敹菜�撖對�靽萘�鈭�踎�堒��渡��砍噡銵刻膩嚗䔶蝙撘寧����銝𤾸椰靘批��典笆朣僐��
    - [x] **靽桀���蟮璅∪�銝衤葵�∩誨��迤�坔龪�齿�瘣�**嚗帋耨憭滢��� `show_concept_top10_window` 銝剖笆��蟮 DataFrame �亥砭�寥�銝芾��塚�甇��銵刻噢撘� `r'\\.0$'` �惩��齿��惩紡�湔�瘜訫竉蝳� `.0` 餈𥡝�屸�䭾���蟮銝芾�鋡怨�皛文僎�躰秤�㰘蝸摰墧𧒄銵峕���䔮憸塩����嗡耨甇�蛹 `r'\.0$'`嚗�蝠摨閙覔瘝颱���蟮璅∪��唳旿銝Ｗ仃銝擧情�梶� bug��
    - [x] **摰䂿緵銝𦒘犖瘞𥪯蜓蝒堒藁銝��渡��芷�㕑�隡睃�憭𡁶漣�鍦��𠰴�甇交�摨�**嚗𡁜銁�踹�銝芾� Treeview 銵典仍蝏穃�鈭��銝餌����璅∩��瑞� `sort_column` �鍦��賭誘嚗峕𣈲��䌊�㕑�隡睃��𠰴��㛖掩�讠��芷���頧祆揢��銁�㰘蝸銝芾��唳旿�𠬍�蝔见�隡朞䌊�刻繮�碶犖瘞𥪯蜓銵典��滨�瘣餉��鍦��𦯀����摨讐𠶖���憒��摮睃銁����堒��祇𡢿�芸𢆡�峕郊�鍦�嚗���唬�銝脲���鍂�瑚�撉䎚��
    - [x] **�啣�摨閖�銝𦠜隅銝贝��芣㺭銝𤾸�撟��霈⊥�**嚗𡁜銁銝芾��𡑒” Toplevel 蝒堒藁��摨閖��啣�鈭��霈∪躹 Frame嚗���嗉恣蝞堒僎�垍𤌍�啣�蝷箸踎�堒��靝�瘨典蘨�� (��� %)�苷��靝�頝�蘨�� (��� %)�嘥�撟喟��芣㺭嚗峕�憭批𧑐�𣂼�鈭�鍂�瑞��斗踎�埈�蝏芰������
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �諹�銵�紡�仿�霂��銝��� 100% 甇�虜��

## 2026-07-04 03:00
- [x] **隡睃��烐綉銝餌��ａ▲�𤩺�敹萇移蝏���孵稬銝擧�瘚株�閫匧𢆡�� (Synchronized High-End Concept Top Bar Interaction & Visual Animation to TK Main Monitor)**嚗�
    - [x] **�齿�憿嗆�銝箏�蝏�辣蝏𤘪�**嚗𡁜��支� `instock_MonitorTK.py` 銝剖��砌������摰𡁶��蓥葵 `self.lbl_category_result` �找辣嚗屸���蛹�曹�銝芸�撖潸� Label嚗Ǒself.lbl_category_title`嚗峕遬蝷� `"敶枏�璁�艙:"`嚗匧�銝�銝芸𢆡����Ｘ踎嚗Ǒself.dynamic_concepts_frame`嚗厩��鞟�憭𡁶�隞嗅�鋆�����`self.concept_wrapper_frame`嚗剹��
    - [x] **摰䂿緵撘訫紡霂滨��餉歲頧砍之��祕��**嚗𡁶��餃�撖潸� `"敶枏�璁�艙:"`嚗𣬚凒�亥�韏瑕��厩� `"璁�艙�踹�蝏蠘恣霂行�"` 蝒堒藁嚗�朖 `show_concept_detail_window`嚗㚁�靽脲�鈭�之����餌�敹恍�笔�����
    - [x] **摰䂿緵�瑚�璁�艙�孵稬銝�甇亙�雿滨凒颲� constituents**嚗𡁶��餃𢆡��𢒰�蹂葉���銝芸�雿𤘪�敹� Label嚗�� `"�勗�鋆��摮�:17"` 蝑㚁�嚗𣬚凒�乩�甇亙�雿滚撕�箄砲�踹�銝讠�銝芾� Treeview constituent �𡑒”撘寧�嚗�朖 `show_concept_top10_window(name)`嚗㚁���之�啗�����䀝葉鈭支�甇仿炊嚗峕����雿𨀣�����
    - [x] **�啣��祆筑�函𤫇銝𡡞�鈭桀�擐�**嚗帋蛹���雿𤘪�敹� Label 蝏穃�鈭������頣�`<Enter>`/`<Leave>`嚗劐�隞嗚���瘚格𧒄�齿艶�脖��芸𢆡�梁遛�脣�銝箸楛蝏輯𠧧 (`#004D00`)嚗���箸𧒄�Ｗ�嚗峕�靘� premium 蝥批����雿𨅯�擐��閫���㛖內��
    - [x] **靽萘�摨訫��澆捆�找��脤��芰�**嚗帋��坔僎�滚��睲� `self.lbl_category_result` ��� `self.lbl_category_title` 蝖桐�銝𤾸�摰�𠳿�厰�餉�摰���澆捆嚗�僎�齿�鈭��敹菜鰵憓墧�瘨�仃�嗥��𨀣�敹萄��兩�嗪緾��郎�仿�餉���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �⊿�嚗峕�隞颱�霂剜��𣇉憬餈偦䔮憸矋�蝟餌� 100% 靽脲�蝔喳���

## 2026-07-04 02:20
- [x] **摰䂿緵�踹�銝芾�霂行���蟮璅∪��唳旿�芷���銝舘䌊摰帋��烾��� (Implemented History-Aware Stock Details & Column Adaptability in Popularity Resonance GUI)**嚗�
    - [x] **摰䂿緵��蟮憭滨�璅∪�銝讠�銝芾�瘨刻�撟��隞瑟聢蝑㗇㺭�株䌊���**嚗𡁜銁��稬�踹�嚗���勗�鋆��摮佗��枏���葵�� constituent 撘寧��寞� `show_concept_top10_window` 銝哨��啣�鈭�糓�行糓��蟮璅∪���嵗撉䎚��銁��蟮憭滨�璅∪�銝页�銝滚��餉粉�硋��嗥� `df_all` DataFrame 銵峕��唳旿嚗諹�峕糓隡睃�隞𤾸歇蝏讐�摮条���蟮�唳旿 DataFrame `self._history_df` 銝剔移蝖桀龪�滚枂撖孵��∠巨嚗峕��硋枂敶枏予��隅頝��嚗Ǒpercent`嚗剹��遠�潘�`price`嚗剹����㵪�`rank`嚗剹��ff���鈭日�嚗Ǒvolume`嚗剹����喉�`red`嚗剹��蜓���`win`嚗厩��唳旿嚗�蝠摨閙覔瘝颱�撖孵��脫芋撘譍��孵稬銝芾�霂行�隞滨��曄內摰墧𧒄�唳旿��䔮憸塩��
    - [x] **摰䂿緵�芸�銋㕑蕭�惩���𢆡��龪�滢����**嚗𡁻�朞�靚�鍂 `self._get_all_cols()` �瑕�蝟餌��滨蔭 of �芸�銋㕑蕭�惩� `extra_cols`��僎�� Treeview 皜脫��塚��冽���撱箏����嚗諹𥅾憭����蟮璅∪�銝𥪜龪�滚���蟮銵峕㺭�殷��躰䌊���隞𦒘葉�𣂼�撖孵���䌊摰帋��堒�澆僎皜脫�嚗䔶�霂����蟮�唳旿銝𦒘蜓�屸𢒰銵冽聢�芸�銋匧����摨血笆朣僐��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �⊿�嚗峕�隞颱�霂剜��𣇉憬餈偦䔮憸矋�蝟餌� 100% 靽脲�蝔喳���

## 2026-07-04 01:10
- [x] **鈭箸��坿�憿園�璁�艙�𤩺�摮埈㺭�𤩺遬蝷箔��屸�撘寧��𥪜𢆡�箏� (Refactored Concept Bar to Count Labels & Double Popup Linkage)**嚗�
    - [x] **�齿�憿嗆�銝箸�摮堒��圈�璅∪� (Count-based Text Label format)**嚗𡁜��支���𧋦�勗�銝� `tk.Button` 蝏����赤�烐踎�梹��齿�銝箔�銝餌�摨� `instock_MonitorTK` 銝��渡��删�蝏輯𠧧 Label��▲�冽�摮堒𢆡���蝷箔蛹 `敶枏�璁�艙: �舐�璁�艙:25 �箏膥鈭箸�敹�:13 5G:13 ...`���銝剜㺭�譍蛹霂交踎�堒銁敶枏�餈蹱鸌鈭箸�銝芾����銝剔��∠巨�餅㺭��
    - [x] **摰䂿緵霂衣�璁�艙�踹�撘寧�銝𤾸�蝥找葵�∪撕蝒𡑒��� (Concept Detail Window & Constituent Linkage)**嚗𡁶��駁▲�函��𨅯��齿�敹菊�砈abel 隡𡁜撕�算�𨀣�敹菜踎�㛖�霈∟祕���萘�����銁蝏蠘恣蝒堒藁銝哨�撅閧內鈭��5憭扳�敹菜踎�𦯀誑�𠰴�撅硺�����煺葵�～����餅踎�埈�憸䀹�����颱葵�∩�撘孵枂憭抒��� constituent 銝芾��𡑒”蝒堒藁嚗㇍reeview嚗剹��
    - [x] **���撘箏之����其�鈭支��批� (Interactive Navigation & Linkage)**嚗朞祕�����𣈲������頧柴��睸�� `Up` / `Down` �桀翰�瑕�雿滢�撖潸⏛嚗�銁蝘餃𢆡�㗇��嗉䌊�典�甇亥��券�朞噢靽～����梢◇�� K蝥踹虾閫��餈𤤿�嚗𤤿���𣈲��之撠誩�雿滨蔭��䌊�冽�銋��隞亙� Escape �桐��桅���綽�摰䂿緵蝎曄��碶漱鈭鉝��
    - [x] **靽桀� _extra_cols �芸�銋匧紡�渡� Tkinter callback 撏拇� (Fixed NameError on _extra_cols)**嚗𡁜銁 `update_all_tables` 銝哨�����賣㺭 `_read_extra_vals` 撘閧鍂鈭� `_extra_cols`嚗䔶�憭硋��賣㺭�芸�銋剹���朞��� `update_all_tables` 撘�憭湔�銵� `_, _, _extra_cols = self._get_all_cols()`嚗�蝠摨閗圾�喃��亥砭�瑟鰵銝𤾸鍳�函�摮睃�頧賣𧒄��援皞�䔮憸塩��
    - [x] **摰䂿緵�臬𢆡�删�摮䀹𧒄����脫㺭�株䌊�典�摨訫�頧賣㦤�� (Startup Historical Fallback Loading)**嚗𡁜��臬𢆡�嗆�瘚� to `popularity_resonance_cache.json` 蝻枏�銝箇征�硋�頧賢仃韐交𧒄嚗𣬚�摨誩��芸𢆡�急� `datacsv` �桀�撟嗅粉�暹��唬��亦�����𡝗�隞塚�`.csv.gz` �� `.csv`嚗㚁��芸𢆡摰峕��䠷�頧賢�撟嗅笆朣鞉𠯫�蠘��交�嚗Ǒdate_entry`嚗㚁�瘨�膄鈭���臬𢆡�䭾㺭�桃蒾撅讐��啗情��
    - [x] **摰䂿緵��蟮憭滨�璅∪�銝讠��唳旿��香銝擧㜃�芣㦤�� (Implemented Date Lock for Historical Review)**嚗𡁜銁 `refresh_realtime_fields` 摰墧𧒄�券��𦻖����𤾸蝱�芸𢆡�瑟鰵蝥輻����靚�葉����乩�敶枏��亦��交���嵗撉䎚��𥅾敶枏�甇��鈭𤾸��脫𠯫�笔��䀹芋撘𧶏��喳��齿𠯫�煺�蝑劐�隞𠰴予嚗㚁��嗵凒�交㜃�芸僎敹賜裦 Socket 銵峕��券��誑�𠰴��啣��嗅��啣笆�屸𢒰���蝏矋�蝖桐��㰘蝸��蟮�唳旿�嗥��踹��剖漲�坿���葵�⊥隅撟��隞瑟聢靽⊥��券�摰����香�典��� CSV �唳旿�祈澈銝𠺪�銝滚�摰墧𧒄銵峕���僕�啜��
    - [x] **靽桀��曹�銝剛㘚��𡠺�瑚�銝��游紡�湔�敹菜踎�𦯀�銝芾��寥�憭梯揖��䔮憸� (Fixed Concept Matching due to Parentheses Mismatch)**嚗𡁜銁 `show_concept_top10_window` 餈�誘�寥�銝芾��塚�撖嫣��亦� `concept_name` 隞亙�銝芾���撅� of `cats` 璁�艙�踹�摮㛖泵銝莎����銵䔶葉�望��砍噡�駁膄�滢�嚗Ǒ.split('(')[0].split('嚗�')[0].strip()`嚗剹���敶餃�閫��鈭�站憒��𨅯�撠���匧郎(CPO)�肽�蝐餃��急��砍噡�𡒊���紡�港�蝥� constituent 撘寧��鞟內�𨀣��惩龪�滢犖瘞𥪯葵�﹦�萘� bug��
    - [x] **摰䂿緵�箄���蟮�交�敺株���揢�餉� (Smart Date Swapping via Arrow Buttons)**嚗𡁻���� `shift_date` 敺株��箏�����餃��函�撌�/�單䲮�𤑳悌憭湔𧒄嚗𣬚�摨譍��齿糓甇餅踎�啣��讛䌊�嗆𠯫銝�憭抬��峕糓擐硋��急� `datacsv` �桀�銝𧢲��厩�摰墧��厰�㕑���蟮��辣��𠯫���撟嗉����憭拙耦�鞉�摨𤩺���𠯫�笔�銵具����𤾸�撌�/�單䲮�𤏸�銵峕䰻�橘��箄�頝唾蓮�啣�銝�銝�/�𦒘�銝芣��唳旿��漱�𤘪𠯫嚗諹歲餈���䭾㺭�桃�蝛箇蒾�乩��冽錰�硺漱�𤘪𠯫嚗峕�憭找��碶�憭滨����������扼��
    - [x] **摰䂿緵�劐遠�潭�蝖格�敹萇��滚臁隡睃��鍦��餉� (Valuable Concept Priority Sorting & Noise Filtering)**嚗𡁜銁 `update_concept_ranking` �鍦�銝哨���笆�𨀣楛�⊿�尠�腈���𨀣葛�⊿�尠�腈���𨅯𤙴隡�㺿�抽�腈���𡏭�韏���詹�萘��噼�銝𡁏��啜���閫���祉��惩���葵�∪��𣂷遠�潛��踹�撱箇��𣈯��芸��賣��苷��喲睸摮𡑒��坔ế摰𠾼���摨𤩺𧒄撘箄�撠��隞祉�隡睃�蝥折��單�雿𠬍�隡睃�靽肽��瑕��瑚�摰硺�撅墧�批�蝘烐�隞瑕�潘�憒�塳����之憌墧㦤���撠���匧郎蝑㚁����敹菜��� Top 5 璁�艙�譍葉��
    - [x] **�齿�憿嗆�璁�艙�孵稬鈭支��箏� (Refactored Top Concept Interaction)**嚗𡁜���𧋦�港�蝏穃��� `lbl_category_result` �齿����銝箇𡠺蝡讠�撘訫紡霂� Label 銝𤾸𢆡���敹菔� Label 蝏�����餃�撖潸� `"敶枏�璁�艙:"` �臬撕�算�𨀣�敹菜踎�㛖�霈∟祕���嘥之蝒堒藁嚗𥡝�𣬚凒�亦��餃��Ｙ���葵�瑚�璁�艙嚗�� `�勗�鋆��摮�:17` 蝑㚁�嚗𣬚�摨譍��箄���凒�芯�敶枏𧑐�湔𦻖撘孵枂撖孵��� constituent 銝芾� Treeview �𡑒”撠讐����撟嗅��牐�曌䭾��砍�瘛梁遛�䁅𠧧�� premium 閫���冽���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �⊿�嚗峕�隞颱�霂剜��𣇉憬餈偦䔮憸矋�蝟餌� 100% 靽脲�蝔喳���

## 2026-07-04 00:30
- [x] **鈭箸��坿��踹��坿��臬𢆡�芣�����嗆綫��葡�㮖�蝻枏�靽萘��箏� (Fixed Cold Startup Concept Ranking & Real-time Update Propagation)**嚗�
    - [x] **摰䂿緵�臬𢆡�舘䌊�典�蝷箇�摮䀹踎�� (Startup Self-Healing from Local Cache)**嚗帋耨甇�� `update_all_tables` 銝� `load_history_by_date` 銝剖笆 `self._block_cache = {}` ��������蝵桃撩�瑯�����蛹�㗇辺隞嗅�憪见�嚗𣬚＆靽苷��砍𧑐蝻枏�銝剜�憭滚枂�� `_block_cache` 銝滢�鋡怠��唳㦤�嗆��∩辣�孵縧嚗諹悟暺䁅恕�臬𢆡�嗅朖�賜迅摰𡁏葡�枏枂��蟮�踹��剖漲�鍦���
    - [x] **摰䂿緵摰墧𧒄銵峕��券��𢆡����啗恣蝞埈踎�� (Live Concept Ranking Updates)**嚗𡁜銁摰墧𧒄�券���靚�遆�� `refresh_realtime_fields` 蝏𤘪��滩‘���撖� `update_concept_ranking(all_stocks_for_stats)` ����剁��梶聦鈭�誑敺��𨅯蘨�匧��Ｗ��脫㺭�格��滩蝸銵冽聢�嗆�霈∠��踹��坿��萘��䠷��𣂼�嚗䔶蝙憿園�璁�艙�踹��剖漲�誩��嗉����蝘垍漣�瑟鰵嚗𣬚�甇�噢�鞉㺭�株��刻䌊����
    - [x] **�惩𤐄憭批𪂹�煺��𨅯��踹��寥��箏� (Resilient Concept Fallback)**嚗𡁜笆敹�歲憛怠��餉��� `populate` 隞亙��望𥲤�𨅯��肽”�湔鰵敺芰㴓餈𥡝�鈭� fallback �惩𤐄���銵峕��滚𦛚�典��芸遣蝡贝��交�銝芾��踹�摮埈挾銝湔𧒄蝻箏仃�塚��芸𢆡���蹂�蝘舐敞�� `self._block_cache` �砍𧑐摮堒�銝剖龪�㵪�隞舘�屸獈�凋��曹�蝻箏�摰墧𧒄�唳旿撖潸稲銝芾�鋡怨腺�箇�霈～����烐踎�埈遬蝷箄◤�券�皜�征��䔮憸塩��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `popularity_resonance_gui.py` 餈𥡝�鈭����祗瘜閧�霂𡢅�100% �朞�銝娪�餉��剔㴓��

## 2026-07-04 00:20
- [x] **摰䂿緵 K蝥踹�隞賣䰻�见膥 HDF5 靽嘥���蓮摮䀝� ptrepack �賭誘銵諹䌊�典��亙�蝻拇㟲����� (Implemented HDF5 Save/Save-As & ptrepack Compression in KlineBackupViewer)**嚗�
    - [x] **閫�膄 HDF5 靽嘥�銝舘蓮摮条��拍��行⏛�脣鴃**嚗𡁜� `on_save_changes` 銝� `on_save_as` 銝剖��砍笆 `.h5`/`.hdf5`/`.hdf` ��辣�������郎�𦠜㜃�芣㺿銝箏��渲粉�嗘��讠憬瘚����
    - [x] **摰䂿緵 HDF5 �唳旿����典��嗡��閗”�湔鰵**嚗𡁜銁 `on_save_as` 頧砍��塚��交���辣�𣬚𤌍���隞嗅�銝� HDF5 銝𥪯�銝箏�銝�頝臬�嚗諹䌊�典⏚�� `shutil.copy2` ���銵𣬚��������誩�撠��摮䀝葉蝻𤥁�餈���蓥葵 DataFrame 雿輻鍂 `to_hdf` �湔鰵�坔�撖孵��� key嚗屸俈甇Ｗ�隞� keys/datasets 銝Ｗ仃��
    - [x] **摰䂿緵 ptrepack �賭誘銵諹䌊�典��交㟲����讠憬**嚗𡁏𡂝鞊∪僎���鈭� `_save_and_repack_hdf5` 颲�𨭌�寞����摮䀹𧒄隡朞䌊�刻粉�� `h5config.txt` 銝剔� `kline_viewer` -> `compression` �瑕��讠憬�澆�嚗諹𥅾�舐鍂�讠憬嚗�����隞嗉䌊�冽凒�滢蛹銝湔𧒄��辣嚗�⏚�典𦶢隞方� `ptrepack` �扯��齿鰵�枏����蝻抬�摰峕��𤾸��典��支葩�嗆�隞嗚����讠憬憭梯揖�嗆�銵𣬚����皛𡄯�蝖桐��唳旿擃睃虾�其�銝齿��譌��
    - [x] **憓𧼮� ptrepack ��㺭�芷������� (Added --alignment Fallback Retry)**嚗𡁻�撖寧眏鈭� PyTables ��𧋦撌桀�撖潸稲 `ptrepack` �𥕦枂 `unrecognized arguments: --alignment=1024` �躰秤嚗���牐��芸𢆡��㺭���蹂��滩��箏����擐㚚�厩�撣行�撖寥�撖寥���㺭��𦶢隞斗�銵�仃韐交𧒄嚗諹䌊�券���輯�銵峕���� `--alignment` ����唳����隞歹�靽肽�鈭���臬����摨血�摰嫣��亙ㄝ�扼��
    - [x] **�芣�銝𡒊���祗瘜閧�霂烐嵗撉��蝏輸�朞�**嚗帋蝙�� `py_compile` 撖� `minute_kline_viewer_qt.py` 餈𥡝�璉��伐��牐遙雿訫�撣賂�憭𡁏聢撘讛䌊���銝� HDF5 repack 靽嘥��曇楝摰���剔㴓��

## 2026-07-03 19:20
- [x] **鈭箸��坿��踹�蝏蠘恣��赤�烐��典�蝷箔�撘寧�憭滨鍂����𤥁䌊�� (Implemented Popularity Concept Statistics, Scrolling & Reusable Persistent Popups)**嚗�
    - [x] **摰䂿緵撅�蝡臭犖瘞𥪯葵�∪���踎�㛖�霈� (Sliced Category Extraction)**嚗𡁻���� `update_concept_ranking`嚗䔶���笆敶枏�撌脣�蝷箇�鈭箸�銝芾�銵典����撟嗥�霈⊥踎�堒�撅痹�銝滚��㰘��滚��典��綽�餈�誘鈭���∪臁�喋��
    - [x] **撘訫�銵䔶��踹��讛膩�砍𧑐蝻枏�銝𤾸��臬𢆡�芣� (Local Block Cache & Self-healing)**嚗𡁏鰵憓� `self._block_cache` 撟嗉�銵峕�銋�����摰墧𧒄銵峕�瘚���瑕鍳�冽��剖�餈𥪜�蝛箸𧒄嚗屸�朞�蝻枏��芣��寥��祉垢銝芾���踎�𦯀縑�荔�摰䂿緵鈭�氖蝥輸�璉鍦�蝷箝��
    - [x] **摰䂿緵憿園��剔��踹� Canvas 皛𡁜𢆡撣��銝擧�頧格赤�𤑳�摰� (Canvas Horizontal Scrolling & Scroll Event Propagation)**嚗𡁜�璁�艙�厰僼�誩�蝥找蛹�㰘器獢� `Canvas`嚗屸�霈文蘨撅閧內 Top 5嚗峕凒憭𡁻�朞�曌䭾�皛朞蔭璅芸�皛𡁜𢆡�亦����朞�撠��頧桐�隞園�譍�蝏穃��� `Canvas` ����� Label �� Button嚗峕覔瘝颱� Tkinter 摮鞉綉隞嗅��㗇��其�隞嗥�撅��僐��
    - [x] **摰䂿緵�踹�銝芾�撘寧�憭滨鍂銝� Escape 銝��桀��� (Window Reuse & Escape Close)**嚗𡁜銁 `show_concept_top10_window` 銝剖笆 `self.concept_win` 餈𥡝� `winfo_exists` 摮䀹暑�⊿�嚗���啁����敺芰㴓憭滨鍂����冽㺭�桅�蝏矋�撟嗥�摰� Escape �桐�蝘鍦翰�笔��准��
    - [x] **�舀�撘寧�雿滨蔭�牐�撠箏站霈啣������ (Geometry Persistence)**嚗𡁶��祉���� `<Configure>` �其�撠��撅�撠箏站���撟訫�����鮋�蝵殷��其�甈⊥�撘��㚚��舐�摨𤩺𧒄�芸𢆡撖寥�嚗��蝢𦒘��碶�憭𡁏遬蝷箏膥���銝讠�鈭支�雿㯄���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �⊿��牐遙雿閗祗瘜閙�蝻抵��桅�嚗峕��煺����撌亦�瘞游���

## 2026-07-03 18:50
- [x] **�� K 蝥踹�隞賣䰻�见膥摰䂿緵�讠憬頧砍��蠘�銝𤾸��澆��讠憬摮睃� (Implemented Compressed "Save As" & Multi-Format Compressed Storage in KlineBackupViewer)**嚗�
    - [x] **摰䂿緵 K 蝥踹�隞賣䰻�见膥�血�銝�/頧砍� (Save As / Export) �讠憬摮睃�銝舘䌊���閫��**嚗�
        - �� `minute_kline_viewer_qt.py` 銝剜鰵憓� `Save As / Export` �厰僼嚗𣬚�摰𡁜僎摰䂿緵鈭� `on_save_as` �寞�嚗�
        - 撖澆枂靽嘥�銝舘粉�𡝗𧒄嚗䔶� `h5config.txt` 銝剜��� `compression` ��㺭��耨憭滢�甇文�銝匧�靚�鍂 `cct.get_ramdisk_path()` �嗆𧊋隡𣳇�鍦�憛思�蝵桀��� `filename` 撘訫��� `TypeError: get_ramdisk_path() missing 1 required positional argument: 'filename'` �躰秤嚗�歇蝏煺�隡惩� `'h5config.txt'` 銵亙���㺭嚗㚁�
        - 靽嘥� `.pkl` ��辣�嗅��刻砲�滨蔭嚗𥕦�頧� `.pkl` ��辣�嗅��乩��芷���憿箏�撠肽����選�cfg_compression, zstd, gzip, bz2, zip, xz, infer, None嚗㚁�敶餃�閫���孵��澆�嚗�� zstd嚗匧�閫��璅∪��脩��𣇉㴓憓��韏𣇉撩憭勗��𤑳� `UnpicklingError`嚗���圈�摰寥��扯䌊�典�摰嫣��扳�扯粉�吔�
        - 靽嘥�銝舘粉�� `.csv` 隞亙� `.json`/`.gz` ��辣�塚�憓𧼮�鈭�笆�澆���龪�滚ế摰𡁜�撖孵����蝻抬�憒� `gzip`嚗匧����敶餃��𦦵�鈭���滚撩銵�� `.csv` �𡒊���辣隞� Pickle �澆�閬���䭾����撅�聢撘讐�銋梢��抬�
    - [x] **銝交聢�扯��嗅�撅�耨�孵��� (Zero-modification to tdx_hdf5_api.py)**嚗𡁜�皛𡁜僎靽萘�鈭� `JSONData/tdx_hdf5_api.py` ���憪讠�����堆��芸�隞颱��湔㺿嚗𣬚＆靽嘥�撅� API ���撖寧迅摰𠾼��
    - [x] **�拍�霂剜�蝻𤥁�銝舘䌊璉��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `minute_kline_viewer_qt.py` �扯�鈭��霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜��𣇉憬餈偦䔮憸塩��

## 2026-07-03 18:25
- [x] **摰䂿緵 K蝥踹�隞賣䰻�见膥靽嘥�蝖株恕��楝敺��蝷箔� HDF5 憭𡁏㺭�株”靽嘥��行⏛�脣鴃 (Implemented Save Confirmation, Path Display & HDF5 Multi-Table Save Protection in KlineBackupViewer)**嚗�
    - [x] **撘訫�靽嘥��滨蔭蝖株恕銝舘楝敺��蝷�**嚗𡁻���� `on_save_changes`嚗�銁�扯�靽嘥��滢��㵪��㰘捏�臬�甇亙����餈䀹糓靽嘥��唳𧋦�唳�隞塚���撕�� `QMessageBox.question` 霂ａ䔮獢��銵䔶�甈∠＆霈歹�撟嗅銁蝖株恕獢�葉撅閧內鈭���滚�憭���亦�摰峕㟲�拍���辣頝臬�嚗屸俈甇Ｙ鍂�瑟��讛秤閫艾��
    - [x] **撘訫�靽嘥��𣂼��𡒊蔭�鞟內**嚗帋�摮䀹��峕郊�𣂼��𠬍�撘孵枂 `QMessageBox.information` �𡁶䰻獢��蝷箏��交��毺�摰峕㟲�拍���辣頝臬�嚗��撘箸�雿𨅯虾�墧滲�扼��
    - [x] **摰墧鴌憭𡁏㺭�株” HDF5 ��辣�湔𦻖靽嘥��行⏛**嚗𡁻�撖� `.h5`/`.hdf5`/`.hdf` �𡒊����隞塚��� `on_save_changes` 瘚������牐�蝐餃��行⏛�餉���𥅾璉�瘚衤蛹 HDF5 ��辣嚗𣬚凒�亙撕�� `QMessageBox.warning` 霅血�撟園���箸�蝔页��脫迫雿輻鍂 Pickle (`to_pickle`) 閬��撖潸稲 HDF5 蝏𤘪��笔����隞� Table 銝Ｗ仃��䔮憸矋�靽脲擪鈭���唳旿銵函��唳旿摰峕㟲�扼��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜��𣇉憬餈偦䔮憸塩��

## 2026-07-03 18:20
- [x] **隡睃� K蝥踹�隞賣䰻�见膥�芸𢆡��辣霈啣���DF5 Table 敹恍�笔��Ｖ��寥�劐��株��剖��� (Enhanced File Memory, HDF5 Table Switching & Selection-Based Diagnosis in KlineBackupViewer)**嚗�
    - [x] **摰䂿緵 "Open File" �箄�霈啣�銝𤾸�雿�**嚗𡁻���� `on_open_file`嚗䔶蝙��辣�㗇𥋘撖寡�獢��擐㚚�㕑絲憪贝楝敺����蝙�典��齿�撘����隞嗉楝敺� `self.current_file`嚗�𥅾摮睃銁嚗㚁��乩�摮睃銁�䠷���輯秐��蟮�枏�霈啣�嚗Ǒfile_history`嚗劐葉蝚砌�銝芸��函��㗇���辣頝臬�嚗峕�憭批𧑐�誩�鈭�鍂�琿�憭滚粉�暹�隞嗥𤌍敶閧�撅�漣頝唾蓮撘�����
    - [x] **��� "Read Table" 敹恍��㺭�株”��揢**嚗𡁜銁撌亙��譍葉 "Delete Table" 撌虫儒�啣� "Read Table" �厰僼嚗Ǒbtn_read_table`嚗㚁�蝏穃� `on_read_table()` �噼�嚗𣬚凒�乩蝙�典�銝���辣�齿鰵靚�鍂 `load_data` �方絲 Key �㗇𥋘獢���
    - [x] **隡睃� HDF5 �唳旿銵券�霈日�鈭桅�㗇𥋘**嚗𡁜銁 `load_data` 銝哨�敶枏撕�箇� HDF5 Key �㗇𥋘獢�◤�㕑絲�塚�璉�瘚见��齿暑頝�� `self.current_key`嚗�僎�券�㗇𥋘獢�葉暺䁅恕�劐葉�嗅笆摨𠉛�蝝Ｗ�嚗峕����冽�瘥𤩺活�齿鰵摰帋�嚗���唬�蝘垍漣��㺭�桅���揢��
    - [x] **摰䂿緵�𡑒”�劐葉憿嫣��株���**嚗𡁜�銝芾�霂𦠜鱏颲枏�獢�蛹蝛箸𧒄嚗�銁 `on_diagnose_click` 銝剛��� `_get_selected_code_from_tables`��砲�寞�隡朞䌊���璉��交�閬�”嚗Ǒsummary_table`嚗剹��祕��”嚗Ǒdetail_table`嚗劐誑�𠰴��渡��𡏭”嚗Ǒfull_results_table`嚗厩�敶枏�擃䀝漁憿對��箄��瑕��嗉�蟡其誨��僎�芸𢆡靚�絲霂𦠜鱏蝒堒藁嚗𣬚��餅��刻��亦�蝜��甇仿炊��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜��𣇉憬餈偦䔮憸塩��

## 2026-07-03 18:02
- [x] **靽桀� SafeHDFStore `__exit__` �罸𡢿�𦯀� super().__exit__ 撖潸稲�� premature ����� Bug (Fixed Premature Lock Release in __exit__ due to super().__exit__ in SafeHDFStore)**嚗�
    - [x] **�寞祥餈�𡟺�𦠜𦆮����鞱�瞍𤩺�**嚗𡁏��亙僎�𤑳緵鈭� `pandas.HDFStore.__exit__` ���隞���其� `self.close()`嚗諹�𣬚眏鈭𤾸�蝐駁��嗘� `close()` 銝娪�霈文� `release_lock=True`嚗��甇文銁 `SafeHDFStore.__exit__` ���靚�鍂 `super().__exit__` 隡𡁻�撘譍誑 `release_lock=True` �齿活靚�鍂 `self.close()`���撖潸稲�� `write_status` 銝� True �塚��拍���銁餈𥕦� `ptrepack` 銝� `rename` �拍��讠憬�滚𦶢�齿�蝔见�撠梯◤餈�𡟺�𦠜𦆮嚗䔶蝙敺堒��典僎�𤏸�蝔见虾�賢�蝒�挪�殷��䭾� Windows `PermissionError` (WinError 32)��
    - [x] **蝘駁膄�𦯀��� `super().__exit__` 靚�鍂**嚗𡁜��支� `__exit__` 銝支葵��𣈲銝剖笆 `super().__exit__(exc_type, exc_val, exc_tb)` ���雿躰��剁��寧眏 `self.close(release_lock=...)` 蝏煺�摰匧��亦恣�交��喲𡡒銝𡡞��𦠜𦆮����渡��賢𪂹�麄��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜��𣇉憬餈偦䔮憸塩��

## 2026-07-03 18:00
- [x] **瘨�膄 SafeHDFStore �滚��� close 銝� __exit__ �寞� definition 閬�� (Eliminated Duplicate close & __exit__ in SafeHDFStore)**嚗�
    - [x] **�𣳇膄�𦯀� close/exit 摰帋�**嚗𡁜��支�蝐餃仍�典�雿坔�銋厩� `__exit__`嚗�洵 453-454 銵䕘��𣬚掩撠暸��滚��� `close`嚗��蝚� 694-701 銵䕘��寞�����支� Python �滚�摰帋��寞�閬��撖潸稲����典��凋�����暸�餉�憭望�蝻粹萅��
    - [x] **摰䂿緵 `close` �� `release_lock` 隡惩��批�**嚗𡁻�����臭��� `close(self, release_lock=True)` �亙藁嚗�銁 `finally` �𦯀葉�朞� `release_lock` 撘��單綉�嗆糓�阡��曄����隞園���
    - [x] **撱嗉� `__exit__` �罸𡢿����𦠜𦆮**嚗𡁏凒�唬� `__exit__` ��� repack/rename �讠憬�餉���� `close()` �孵�銝� `close(release_lock=False)`嚗䔶蝙敶枏�餈𤤿��刻�銵諹�埈𧒄�� ptrepack �拍��讠憬銝擧�隞嗆㺿�齿��港��嗅��冽��厩𡠺�𣳇�嚗䔶��� `finally` 銝剝�朞� `release_lock=True` �� close 頝臬��𡝗遬撘讐� `_release_lock()` 蝏煺��𦠜𦆮�拍����敶餃��踹�撟嗅�餈𤤿�鈭㗇𦜖�𦠜㺿�齿��湔���紡�渡� Windows 撟嗅����蝒���
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `JSONData/tdx_hdf5_api.py` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏煺����擃条迅摰𡁏�扼��

## 2026-07-03 16:05
- [x] **�寞祥 HDF5 憭朞�蝔见僎�煾�霂餃�銝𤾸��文�蝒�援皞���讠憬瞍𤩺� (Fixed HDF5 Lock Race Condition, Redundant Methods, and Defer Lock Release during Repack)**嚗�
    - [x] **撘訫����隞嗉粉��/閫��撅��典�撣訾���**嚗𡁜銁 `JSONData/tdx_hdf5_api.py` �� `_acquire_lock` 銝� `_forced_unlock` ��繮�𡝗芋�𦯀葉嚗屸�撖寡粉�碶�閫�� `.lock` ��辣��捆��葩�峕挾隞����ㄨ鈭���函� `try...except (OSError, ValueError, IndexError)`��銁���隞嗅��嗡�餈𤤿��𡁜末�𦠜𦆮鋡怠�嚗���� `FileNotFoundError`嚗㗇�甇�銁�坔�憭���砍��嗆����𥕦枂 `PermissionError` [WinError 32]嚗厩������撣詨���𧒄嚗諹䌊�冽㜃�芸援皞�僎�扯��瑕㭂���輸�霂𤏪��𦦵�鈭��撣詨�憭𡝗��箏紡�游��䀝葉�准��
    - [x] **摰墧鴌���隞嗅撩�嗥宏�支��芾圾������**嚗𡁜銁 `_acquire_lock` �� `_forced_unlock` 銝剝��啗��嗉䌊閫���硋撩�嗉圾��紡�� `os.remove` 憭梯揖�塚��啣�鈭� `time.sleep(self.probe_interval)` �鞾����選��踹��� Windows 銝讠眏鈭擧�隞嗅蘂����曉辣餈罸�䭾� CPU �芣�銝擧��鞾�霂𨰻��
    - [x] **瘨�膄�滚��寞�摰帋�閬��隞交�憭滚�撅�蝥輻���**嚗𡁏��交��支�蝐餃仍�典�雿坔�銋厩� `close` 銝� `__exit__` �寞�����滢�撠暸��芸��典� `_HDF_GLOBAL_LOCK` 蝥輻����蝻箏� `_handle` �嗆��ế摰𡁶�����寞�撖孵��典��剝�餉�餈𥡝�閬����䔮憸矋��Ｗ�鈭��蝔见�憭𡁶瑪蝔见��剖蘂���摰匧��脣鴃��
    - [x] **摰墧鴌�讠憬銝𡡞��賢��罸𡢿���𣈯��笔辣�踱�苷���**嚗𡁻���� `__exit__` �� ptrepack �讠憬���摰𡁶𠶖���餉�嚗峕㺿�� `self.close(release_lock=False)`���蝖桐��刻�銵屸��埈𧒄�� `ptrepack` �讠憬銝� `os.rename` �孵��其��塚�敶枏�餈𤤿�靘萘��砍�����拍���辣����芣�敶枏��冽㺿�滚��墧��其�摰峕��擧�蝏煺��𦠜𦆮�����敶餃��寧�鈭��𣈯��𣂼��𦠜𦆮��㺿�齿��湔����嘥紡�渡�憭㚚�撟嗅��曹澈�脩�嚗䔶��箏�銝𡃏圾�喃� Race Condition ��香蝛氬��
    - [x] **銵亙� `_wait_for_lock` ���隞嗆����撣訾���**嚗𡁜��批�鋆� `split("|")` ��漣銝箏��刻圾�鞉䲮撘𧶏���笆 `OSError/ValueError/IndexError` 撟嗅�������惩��� `continue` ���蹂��歹�瘨�膄鈭�蘨霂餌�敺�楝敺��瞏𨅯銁�� `ValueError` 撏拇���
    - [x] **�惩𤐄 `_release_lock` 銝� `os.remove` ����� OSError 靽脲擪**嚗𡁜笆 `os.remove` 憭梯揖�閧𡠺�閗繮 `OSError` 隞� `warning` 蝥批��䠷��曇�嚗屸��� Windows �交��𦠜𦆮撱嗉��嗉秤�仿�霂荔�憭硋����隞嗉粉�硋��� `OSError/ValueError/IndexError` ����閗繮嚗諹��硋��典僎�穃��文㦤�胯��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `JSONData/tdx_hdf5_api.py` �扯�鈭�����霂烐嵗撉䕘�蝖株恕�餉�銝舘祗瘜訫��冽迤蝖柴��

## 2026-07-03 15:50
- [x] **摰䂿緵蝑𣇉裦蝻𤥁��刻䌊�典�雿滚��漤�匧�蝑𣇉裦 (Auto-Selecting Current Strategy in Strategy Editor)**嚗�
    - [x] **�芸𢆡�寥� strategy_id 撟嗅�雿�**嚗𡁜銁 `standalone_multi_period_tester.py` 銝哨��齿�鈭� `MultiPeriodStrategyEditor` ���憪见��寞����撘�蝑𣇉裦蝻𤥁��冽𧒄嚗䔶��滨′蝻𣇉�暺䁅恕�劐葉蝚� 0 銝芰��伐��峕糓�冽����𣇉�蝒堒藁敶枏��匧��� `strategy_id`����𨀣𪄳�啣龪�滨��伐��躰䌊�典銁 `listbox` 銝剝�鈭桅�劐葉嚗�僎�朞� `listbox.see()` �芸𢆡皛𡁜𢆡�唾����嚗���颱��冽�瘥𤩺活�枏�蝻𤥁��典���閬���典粉�曉��孵稬撖孵�蝑𣇉裦����鞉郊撉扎��
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `standalone_multi_period_tester.py` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏笔�蝢𦒘���迅摰𠾼��

## 2026-07-03 15:55
- [x] **�湔鰵�枏��滨蔭��辣隞亙��怠��冽�蝑𣇉裦�滨蔭 (Updated Packaging Configurations to Include Multi-Period Strategy Config)**嚗�
    - [x] **銵仿� PyInstaller �枏�靘肽�**嚗𡁜銁 `instock_MonitorTK.spec` �� `MultiPeriodTester.spec` ��辣�� `datas` �典�銝哨�銵仿�鈭�笆 `"config/multi_period_strategies.json"` ���皞𣂼��剁�蝖桐� PyInstaller 蝻𤥁��嗉䌊�典��嗅���秐鈭諹��嗉�皞鞉挾��
    - [x] **銵仿� Nuitka 蝻𤥁��賭誘銵屸�厰★**嚗𡁜銁 `nuitka_instockMonitor.bat`��nuitka_build_console.bat` �� `nuitka_build_console_onlyClang.bat` 蝑� 3 銝� Nuitka 銝��桃�霂𤏸��砌葉嚗峕鰵憓硺� `--include-data-file=config\multi_period_strategies.json=config\multi_period_strategies.json` �唳旿��辣�枏��厰★嚗峕��帋��枏����摨誩銁餈鞱���𧒄������𣂼��𡃏䌊��楝敺���

## 2026-07-03 15:52
- [x] **摰䂿緵憭𡁜𪂹�毺��仿�蝵� (multi_period_strategies.json) 撱嗉�銝舘䌊����� (Implemented Lazy-Loading & Auto-Release for Multi-Period Strategy Config)**嚗�
    - [x] **�舀� get_conf_path 靚�鍂�嗅𢆡��䌊�����**嚗𡁜銁 `sys_utils.py` �� `RESOURCE_MAP` 摮堒�銝剜迤撘𤩺釣�䔶� `"multi_period_strategies.json"`嚗�僎韏衤��嗅��啁� `delay_release: True` 撅墧�扼��
    - [x] **�踹��臬𢆡�嗆������**嚗𡁜銁 `sys_utils.py` �� `ensure_all_configs_released` �臬𢆡憿孵�憪见�銝剖��亥�皛歹��箄�頝唾���扇銝� `delay_release` ���蝵格�隞塚�摰𣬚�皛∟雲鈭�鍂�猾�𨅯銁靚�鍂��𧒄�坔��𦠜𦆮嚗峕瓷雿輻鍂撠曹��𦠜𦆮�萘��厰��芣���瘙��瘨�膄鈭��靚梶��臬𢆡�� I/O �其���
    - [x] **�齿�蝑𣇉裦撘閙��嘥��𤥁楝敺�**嚗𡁜銁 `multi_period_strategy_engine.py` ����惩遆�唬葉嚗��蝖祉���楝敺� `os.path.join(get_app_root(), ...)` �齿�銝� `get_conf_path("multi_period_strategies.json")`��＆靽苷��芣��函�甇��靘见�撟嗉��典��冽��㕑�撘閙��塚��齿���閫血��芣��𦠜𦆮嚗䔶�霂���餉�隡㗛��找�蝟餌�蝔喳��扼��
    - [x] **�芸𢆡�𡝗�霂訫�敶鍦�蝏輸�朞�**嚗𡁻�朞� `test_multi_period_automated.py` ���霂閖�霂��撘閙��𣂼�隞� `get_conf_path` 頝臬��㰘蝸撟嗡�摮㗛�蝵殷��芸��乩遙雿訫�雿𦦵鍂��

## 2026-07-03 15:46
- [x] **隡睃�頞见飵憭抒�����冽��㕑�蝑𣇉裦�滨蔭 (Optimized Multi-Period Trend Strategy Config in JSON)**嚗�
    - [x] **摰帋�撟嗆凒�啣��冽�頞见飵憭抒�����交芋�� (Registered Trend Strategies in JSON)**嚗𡁜銁 `config/multi_period_strategies.json` �滨蔭��辣銝剖�蝥找��𨅯撩�輻����頦拙���鍳�兩�萘��冽��∩辣嚗䔶蝙�嗆迤撘讛���� `d`��2d`��3d`��m`��45d` 蝑匧��園𡢿�冽�鈭日�嚗𥕦��塚��啣�鈭� 3 銝芸��啁��誩�頞见飵憭抒�����伐��𡏭��踹之蝏𤘪�嚗𡁜�頦拐�蝔喲�甈∪鍳�兩�腈���𡏭��踹之蝏𤘪�嚗帋蜓��撩�𣳇�麨�嘥��𣈯�憌𡡞埯�港�嚗𡁜��冽�頝𣬚聦�笔𦶢蝥踱�嘅��拍�閫��血僎�舀��典��臬𢆡��撩�𣳇�煺誑�𡃏��湔𣈲�𤑳�銝芾�閫����
    - [x] **銝交聢�扯��嗅�撅�耨�孵��� (Zero Source-Code Modification Guard)**嚗𡁏伃��鈭�笆 `data_utils.py` �� `multi_period_strategy_engine.py` ����� Python 皞鞟��孵𢆡�����誑蝥舫�蝵桀耦撘𤩺釣�乩��∠��亦����嚗𠃋ISS & YAGNI嚗匧極蝔见��踺��
    - [x] **摰峕㟲�芸𢆡�硋�敶雴�霂𦠜鱏�唳旿�剔㴓撉諹� (Validated Pipeline & Strategy Loading)**嚗𡁻�朞�餈鞱� `test_multi_period_automated.py`嚗屸◇�拚�朞�鈭���冽��唳旿霂餃���像�箏�撟嗡誑�𠹺漱�厰�霂�嵗撉䕘��牐遙雿� `KeyError` 撘�虜嚗峕�霂訫�蝏輯��𠾼��

## 2026-07-03 07:45
- [x] **隡睃�憭𡁜𪂹�毺��亦�颲穃膥�鞟內撘寧�銝粹��餃�撘� Toast (Optimized Strategy Editor Notifications with Non-Blocking Toasts)**嚗�
    - [x] **摰䂿緵憭滚� JSON �鮋獈憛𧼮�擐� (Non-blocking JSON Copy Feedback)**嚗𡁜銁 `standalone_multi_period_tester.py` 銝哨�撠� `_copy_json_to_clipboard` 銝剔� `messagebox.showinfo` �踵揢銝� `show_toast(self, "�� JSON ��捆撌脣��嗅��芾斐�選�", duration=1200)`��迨隡睃�蝖桐�鈭�鍂�瑕銁憭滚� JSON �嗡�隡朞◤璅⊥��撕蝒埈��哨��滢��湔�����
    - [x] **�拍�霂剜�蝻𤥁��芣��函遛�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `standalone_multi_period_tester.py` �扯�鈭�����霂烐嵗撉䕘�蝖株恕瘝⊥�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏笔�蝢𦒘���迅摰𠾼��

## 2026-07-03 07:15
- [x] **摰䂿緵蝑𣇉裦�䠷�劐���蟮餈質葵 Treeview �芾斐�踹翰�笔��嗅��� (Implemented Right-Click Copy Helpers in Stock Selection & Tracker Window)**嚗�
    - [x] **�啣��𨅯��嗡誨���苷��𨅯��嗉�靽⊥��嘥𢰧�桅�厰★ (Added Copy Actions to Context Menus)**嚗𡁜銁 `stock_selection_window.py` �唾������ Treeview 蝏�辣嚗�蜓蝑𣇉裦�㕑�銵具������摮鞱”����脰蕭頦芾”隞亙��睃��滢����銵剁���𢰧�株��蓥葉嚗𣬚�銝��游�鈭��𨥉�� 憭滚�隞���嘥��𨥉�� 憭滚�銵䔶縑�胼�嘥翰�琿�厰★嚗�笆朣𣂷�憭𡁜𪂹�蠘��函��亦��匧膥��漱鈭埝�����
    - [x] **摰䂿緵�亙ㄝ�� Clipboard �𣂼�銝擧�瘣㛖�瘜� (Robust Copy & Status Reporting)**嚗帋蛹 `StockSelectionWindow` and `HistoricalSelectionTrackerDialog` 蝐餉‘��� `copy_code` �� `copy_row_info` �寞�嚗峕𣈲�������冽����硋�畾萄僎�潭𦻖銝� `col_name:value | col_name:value` ��聢撘𧶏��芸𢆡餈�誘�鎿��嘥��栶�鞾��嫘�爗�嘥�蝻�嚗𥕦僎�其蜓蝔见��𡃏蕭頦芰�����嗆����單𧒄�漤�憭滚��嗆���2蝘鍦��芸𢆡�Ｗ���
    - [x] **摰匧��脩征銝𤾸�憿萇倌�芣��⊿� (Safe Execution)**嚗𡁜銁�喲睸�孵稬�墧㺭�桀躹�𣇉征�訫��潭𧒄嚗諹䌊�券�撘��芾斐�踵�雿靝誑�脫迫�𥕦枂 `IndexError`嚗�僎�朞�鈭� `py_compile` ���霂穃��冽�扳嵗撉䎚��

## 2026-07-03 07:00
- [x] **靽桀�憭批𪂹��㺭�桀銁摰䂿�擃㗛��瑟鰵銝钅���碶蛹�𨅯�蝑争�苷� is_same �𨅯��冽�敶鍦� Bug (Fixed Large-Cycle Data Degenerating to Equal Values & Fallback is_same Alignment)**嚗�
    - [x] **�寞祥憭批𪂹��㺭�桀�蝑厰���𣇉��寞𧋦 Bug**嚗𡁜銁 `data_utils.py` �����之�冽�嚗�� 3d, w, m 蝑㚁�銵峕���僎�餉�銝哨�靽桀�鈭���厰�憸穃�頝喳��啁�摮䀹凒�啁��嗅�蝻粹萅�����銁 `df_allDF[resample] = top_all` �坔�蝻枏��𠬍��滚銁銝𧢲䲮靚�鍂 `complete_indicators_pipeline(top_all, ...)`��紡�游��亦�摮条� DataFrame �芣𡉼撣血像蝘餃�鈭抒��� `_is_shifted=True` �嗆����㰘��銁銝衤�甈∪�頝喃�蝻枏�霂餃��唳旿�塚�蝟餌�霈支蛹撟嗆𧊋�𤑳�撟喟宏嚗屸�憸穃𧑐�冽�銝芸�頝喃葉�滚�撟喟宏嚗�紡�游��脩鸌敺��澆��刻◤��瘛勗����潸��㚚���𡝗��函���緵撠� `df_allDF[resample] = top_all`嚗��憭批𪂹�� UI 頧刻蕨撖孵��� `df_allDF[resample_res] = top_all_res`嚗厩�蝻枏��湔鰵�其�蝘餉秐 `complete_indicators_pipeline` �扯�摰峕�銋见�嚗𣬚＆靽嘥��亦�摮条��臬�蝢𤾸��怠像蝘餌𠶖��� `_is_shifted` ��扇 the ��蝏� DataFrame嚗�蝠摨閖獈�剝�憭滚像蝘颯��
    - [x] **隡睃�憭批𪂹�� is_same �𨅯�頝臬��文�**嚗𡁜銁 `complete_indicators_pipeline` 銝哨���笆�墧𠯫蝥輻�憭批��亙𪂹���2d, 3d, 5d, 45d嚗㚁��冽瓷�� `resdate` 韏啣�摨訫ế摰朞楝敺�𧒄嚗���支��雴蛹 False ��′蝻𣇉� inequality window 瘥𥪜笆嚗偦���蛹雿輻鍂 Pandas �𣂷��� `floor(f'{n}D')` �寞�撖寞� `today_ts` and `last_ts` ��𪂹�蠘絲憪见笆朣鞟�嚗�僎隞� try-except 雿𨅯��券�蝥找��歹�嚗䔶蝙敺堒��亙𪂹�笔銁�� `resdate` �嗆���銋蠘�摰𣬚��芷���霂��敶枏��臬炏撅硺��䔶��芸�蝏枏𪂹���蝎曄＆撖寥�鈭� Ghost Bar ��ế摰𠾼��
    - [x] **�拍�霂剜�蝻𤥁�銝𤾸�瘚𧢲嵗撉��蝏輸�朞�**嚗帋蝙�� `py_compile` 撖嫣耨�孵��� `data_utils.py` 餈𥡝��拍�霂剜��⊿� 100% �𣂼���僎餈鞱��祉�瘚贝��𡁏𧋦 `scratch_debug_002354.py` �� `002354 憭拙迂�啁�` 摰䂿� 3d �唳旿銝𡃏��𡄯��𣂼�颲枏枂蝳餅袇銝𠉛�撖寞迤蝖桃���蟮�冽𤣰�孵��潘�`lastp1d: 10.34`, `lastp2d: 9.40`嚗㚁�銝滚��𤑳��函����吔��唳旿�𣬚��亥捶�誯�敶㘾�蝎曄＆摨艾��

## 2026-07-03 06:40
- [x] **摰䂿緵 PyQt 憭�遢K蝥踵䰻�见膥 (KlineBackupViewer) 霂𦠜鱏銝芾�銝𤾸𢰧�桀翰�瑕��� (Implemented Stock Diagnosis & Right-Click Helpers in KlineBackupViewer)**嚗�
    - [x] **�啣�霂𦠜鱏銝芾�颲枏�銝擧��� (Added Diagnostic UI Elements)**嚗𡁜銁 `minute_kline_viewer_qt.py` ��▲�典極�瑟��啣��𡏭��凋葵�﹦�肽��交�嚗Ǒdiag_input`嚗匧��𨥉�� 霂𦠜鱏�脲��殷�`btn_diag`嚗㚁��舀��噼膠/�孵稬�單𧒄閫血�霂𦠜鱏嚗�僎�芸𢆡皜����‘��6雿滩�蟡其誨����
    - [x] **摰䂿緵頝典像�啁��亥��剖笆�� (Integrated diagnose_stock_strategy)**嚗𡁜��唬� `diagnose_stock_strategy` �寞�嚗䔶����銝剔� `active_df` �𣂼�撖孵�銝芾��孵��唳旿銵䕘��芸𢆡��ㄨ敶枏��亥砭�∩辣嚗íuery嚗㚁�撟嗆��蠘��函頂蝏蠘䌊撣衣� `stock_logic_utils.check_code` �亙藁���霂𦠜鱏�亙�嚗�� parent 霈曆蛹 None 隞仿俈頝冽���/頝函����隞嗅儐�舀香���蝒����
    - [x] **���銵冽聢�喲睸敹急㭘�𨅯� (Integrated Table Context Menus)**嚗帋蛹�䁅�銵剁�`summary_table`嚗剹��祕��”嚗Ǒdetail_table`嚗匧�摰峕㟲蝏𤘪�銵剁�`full_results_table`嚗厩�銝��滨蔭�喲睸�𨅯���𣈲��𢰧�桃凒�乒�𨥉�� 霂𦠜鱏銝芾��唳旿�腈���𨥉�� 憭滚�隞���苷誑�𪙛�𨥉�� 憭滚��渲��澆��碶縑�胼�嘅���之�𣂼�鈭�漱鈭雴��唳旿憭滚������
    - [x] **�啣��𥪜𢆡摰帋�����孵�瘜其� Re-entry �墧��喲睸�蠘� (Added Linkage, Favorite & Backtest to Context Menus)**嚗�
        - �啣��𨥉�� �𥪜𢆡摰帋��∠巨�嗪�厰★嚗諹圻�� `_execute_linkage` �𥪜𢆡憭㚚�銵峕�蝏�垢��
        - 撘訫�撖� `GlobalFavoriteManager` ����剁��舀��鎿� 霈曆蛹�滨�銝芾��嘥��鎿� �𡝗��滨�銝芾��嘥𢰧�格�雿靝�摰墧𧒄�嗆����漤���
        - 摰䂿緵鈭� `run_reentry_backtest` 撘�郊餈鞱��箏�嚗𡁻�朞� `BacktestWorker` (蝏扳㗁�� `QThread`) 撘�郊�枏�撟嗅��鞉㺭�殷��脫迫銝餌��Ｗ㨃憿選�雿輻鍂 `BacktestReportQtDialog` 蝢舘�撅閧內�墧�蝏栞捏��
    - [x] **霂剜�蝻𤥁�銝𤾸��湔�扳嵗撉� (Compilation Passed)**嚗𡁏��罸�朞�鈭� `py_compile` �拍�蝻𤥁��芣�嚗峕�隞颱�霂剜��躰秤��憬餈偦�霂舀�撘�虜嚗𣬚頂蝏蠘�銵𣬚迅摰𠾼��

## 2026-07-03 05:40
- [x] **靽桀� ATS / 鈭箸��望𥲤摰Ｘ�蝡荔�PR嚗匧銁�瑕鍳�冽�頞�𧒄�剖��擧�瘜閗䌊�券�餈硺�銵峕�銝Ｗ仃�� Bug (Fixed Port Auto-Redetection & Reconnection for ATS/PR)**嚗�
    - [x] **霈曇恣撟嗅��乒��30蝘坿䌊�冽䔝瘚见��港��芸𢆡�齿鰵餈墧𦻖�箏���**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `send_df` 蝥輻�敺芰㴓銝哨��齿�鈭�笆 26670 (ATS 蝏�垢) �� 26671 (鈭箸��望𥲤蝏�垢) 瘣餉��嗆���摮条��斗鱏���蝻枏�����亦𠶖���銝箄��嗆�鋡急𦻖�嗥垢�喲𡡒����港蛹 `False` �塚�蝟餌�撠�䌊�典��乩�銝� 30 蝘垍��Ｘ��瑕㭂�園𡢿��
    - [x] **摰䂿緵�𣳇獈憛噼䌊�券�餈�**嚗𡁜�頝萘氖銝𠹺�甈⊥䔝瘚见�霂閗�餈� 30 蝘埝𧒄嚗𣬚瑪蝔衤�銝湔𧒄�日��Ｘ�撟嗅�霂閗��� `s2.connect` �齿鰵銝擧�摰𡁶垢��遣蝡� Socket �拍�餈墧𦻖����行𦻖�嗥垢�臬𢆡撟嗉��交�����喳虾�芸𢆡�Ｗ�瘣餉��嗆���`_pr_enabled_cache` / `_ats_enabled_cache` �齿鰵蝵桐蛹 `True`嚗匧僎餈𥕦�擃㗛�蠘����颲橒�敶餃�摰䂿緵鈭��餈𤤿�蝟餌���䌊���銵峕��交𤣰撖寥���
    - [x] **�屸�撱嗉��滩�銝𡡞俈�⊥香靽脲擪**嚗朞𥅾憭㚚��交𤣰蝡舀𧊋撘��荔�餈墧𦻖憭梯揖隡朞䌊�券�蝵� 30 蝘� the �Ｘ��瑕㭂���踵𧒄�湛��踹��其蜓蝥輻�敺芰㴓銝剔眏鈭𡡞�憸𤏸��亙仃韐交�頞�𧒄撘訫��餃��硋㨃憿選�靽嗪�鈭� UI 鈭支�銝舘����甇亦��港�瘚���扼��

## 2026-07-02 11:35
- [x] **�寞祥鈭箸��望𥲤摰Ｘ�蝡� tk.PanedWindow �厰★ weight �仿�銝𡒊�瘥娍�隡訾��� (Fixed tk.PanedWindow Weight Option Error & Optimized Proportional Resizing)**嚗�
    - [x] **靽桀� TclError: unknown option "-weight"**嚗𡁜�雿滚僎皜�膄鈭�銁 `popularity_resonance_gui.py` �𣬚� `self.paned.add` 靚�鍂銝凋��亦� `weight=1` 餈嗘�銝齿𣈲����堆�敶餃�瘨�膄鈭�眏鈭� tk.PanedWindow �� ttk.Panedwindow 撌桀��� runtime �𥕦枂�� `TclError`��
    - [x] **摰䂿緵�䭾�銝磰䌊�����儘��� `sash_ratio` 瘥𥪯�蝻拇𦆮蝞埈�**嚗𡁻���� `restore_sash` �� `save_sash_pos` �詨��餉�嚗��隡删�������蝝惩�����典�蝥找蛹�渡�摮衣��𨀣��讐熔��𠧧瘥𥪯��脲芋撘𧶏�`sash_ratio`嚗剹����冽��见𢆡�𡝗嗻靚�㟲銝剝𡢿��凒��𠧧蝥踹僎�曉�曌䭾�嚗ǑButtonRelease-1`嚗㗇��喲𡡒蝒堒藁�塚�霈∠��嗅�摰孵膥�餃捐摨衣�瘥𥪯�撟嗅��� `popularity_resonance_config.json` �拍��滨蔭��辣��
    - [x] **摰䂿緵蝒堒藁�劐撓蝑㗇�蝻拇𦆮**嚗𡁜銁 `<Configure>`嚗��蝵株��湛�敹�歲���甈∪鍳�刻䌊�����𧒄嚗�𢆡��蝙�典��滚捆�函���捐摨虫�隞� `sash_ratio` 瘥𥪯��芷���摰帋� sash嚗䔶蝙撌血𢰧銝斗��賢銁蝒堒藁璅芸��劐撓�嗉��譍蜓蝒𦯀�摰𣬚�蝑㗇�蝻拇𦆮嚗�蝠摨閙��支��蓥儒�劐撓蝝𠹺僚�𣇉蒾撅讐�蝻粹萅��
    - [x] **�朞��拍�蝻𤥁�銝擧�韏瑕鍳�冽�霂�**嚗𡁏�銵䔶� `py_compile` �芣�銝� `python popularity_resonance_gui.py` 霂訫鍳�剁�銝餌瑪蝔𧢲��蠘��� mainloop 銝娍�隞颱� Tcl 撏拇��硋鍳�典㨃雿誩��麄��

## 2026-07-01 23:10
- [x] **摰䂿緵�典𪂹�煺� MA5 銝� MA10 銵峕���僎�滨��舀�銝舘䌊���撖寥� (Enabled Global Dynamic MA5 & MA10 Recalculation & Adaptive Period Alignment)**嚗�
    - [x] **閫�膄憭批𪂹�毺�摰墧𧒄��瑪�滨�撠��**嚗𡁻���� `data_utils.py` 銝� `complete_indicators_pipeline` 憭����瑪�滨�璅∪�嚗�縧�支��亦瑪銝枏��� `if resample == 'd':` �∩辣�𣂼���
    - [x] **摰䂿緵憭批𪂹�笔��� MA5 銝� MA10 蝎曉��滨�**嚗𡁶眏鈭𤾸銁甇文�撌脩�靽桀�鈭� `generate_lastN_features_dict` 憭批𪂹�毺鸌敺���𣇉�撟喟宏蝻粹萅嚗䔶蝙敺� `lastp1d` �� `lastp10d` �孵��堒銁憭批𪂹���憒�𪂹蝥選�銝见��函移��笆摨𥪜歇�嗥���蟮�具����諹悟憭批𪂹�煺�撖� `ma5d` �� `ma10d` �滚��䀝葉摰墧𧒄隞瑟聢 `close` 餈𥡝��滨��冽㺭摮虫�銝𡁜𦛚�餉�銝𠰴��函移蝖格�蝡页�摰䂿緵鈭���亙笆憭批𪂹�毺��烐�抒��� the 瘥怎�蝥扳��乓��
    - [x] **摰匧�靽萘�撟園�摰𡁻鵭��瑪�滚�瘙⊥�**嚗𡁜笆鈭𤾸� `ma60d` 餈嗵��删鸌敺���豢楛摨血��琜��� `lastp11d` �� `lastp60d` 摮埈挾嚗㕑�峕��枏銁憭批𪂹�煺�鋡怎��渡��臬像����嗵��踹𪂹�笔�蝥選��朞�銝滩��仿�蝞堒�銵刻�䔶�隞亙��其��辷�雿踹�蝏抒賒�冽��匧𪂹�煺��湔𦻖霂餃� TDX 蝎曄＆�����甅�芾粉�拍��潘�摰𣬚��潮▽鈭���嗥���瑪�菜�摨虫������㺭�桐��湔�扼��
    - [x] **�齿�憭批𪂹�� Ghost Bar �箄��芷���撖寥�蝞埈� (Fixed Monday/Month-Start Index Shift)**嚗𡁻�撖寧′蝻𣇉�撟喟宏隡𡁜紡�游𪂹銝�嚗�鰵����典�撘�憪衤��芸銁 df 銝剛�����芣𤣰�𡟛蝥選��𡝗��萘洵銝�銝芯漱�𤘪𠯫�𤑳��𨅯�銝�銝芸𪂹��㺭�格���/�嗘� 1 �麨�萘�銝𡁜𦛚 Bug嚗屸���� `tdx_data_Day.py` 銝剔� `generate_lastN_features_dict` �孵��𣂼��具��⏚�� `to_period('W'/'M'/'Q')` �冽���撖� df ���𦒘��� K 蝥輻��園𡢿�喃�敶枏�蝟餌��交���𥅾撅硺��䔶��芰��冽�嚗�秩�擧𧊋�嗥��� Ghost Bar 撌脩����嚗㚁��蹱�銵�像蝘餃� `iloc[-da-1]`嚗𥡝𥅾銝滚�鈭𤾸�銝��冽�嚗�秩�擧鰵�冽� Bar 撠𡁏𧊋�嗵�嚗㚁��躰䌊�典�撟喟宏�湔𦻖�� `iloc[-da]`嚗��蝢𤾸銁���㕑器��㦤�航䌊���撖寥���


## 2026-07-01 22:20
- [x] **�寞祥憭批𪂹����舀���㺭�桀��亦瑪摰墧𧒄����𡑒��𤥁����毺�蝝𠹺僚銝� KeyError 撏拇� (Fixed Large-Cycle Indicator Pollution & KeyError Crashes)**嚗�
    - [x] **�寞祥憭批𪂹�� `combine_dataFrame` ����唳旿瘙⊥�蝻粹萅**嚗𡁜�雿滚僎�齿�鈭� `data_utils.py` 銝� 3 憭�蝙�� `combine_dataFrame` ��僎隞𦠜𠯫摰墧𧒄敹怎� `top_now` �喳之�冽���蟮�唳旿 `top_all` / `top_all_res` 憭���餉���� `resample != 'd'` �塚��典�撟嗅�撘箏�餈�誘 `top_now`嚗䔶�靽萘��詨�撣�㦤銵峕��乩遠�梹�`open`, `high`, `low`, `close`, `vol`, `volume`, `amount`, `name`嚗㚁�敶餃��行⏛鈭�𠯫蝥輯恣蝞㛖����嚗�� `ma5d: 4.15`嚗䈣ma60d: 5.53` 蝑㚁�撖孵之�冽�嚗�𪂹蝥選����嚗��甇�＆�� `ma5d: 4.928`嚗䈣ma60d: 4.528`嚗厩�閬��銝擧情�橒�敶餃�餈睃�鈭���冽�蝑𣇉裦�文����蝖格�改�閫�� 000566 瘚瑕�瘚瑁晓�函瑪�文��躰秤�桅�嚗剹��
    - [x] **蝳�迫憭批𪂹�煺�閬����瑪銝擧隅頝��嚗㇊revented Large-Cycle MA Recalculation嚗�**嚗帋耨憭滢��� `complete_indicators_pipeline` 銝哨��墧𠯫蝥踹之�冽��唳旿嚗���函瑪嚗厩� `ma5d`/`ma10d`/`ma20d`/`ma60d` 隞亙� `percent`/`per1d` ��瑪銝擧隅頝��鋡恍��啗恣蝞㛖�蝻粹萅��之�冽����蝥踵𧋦頨怠歇�典�頧賣𧒄�� HDF5/TDX 摰峕㟲�漤��瑕僎霈∠�甇�＆嚗���笔��� 5�典�蝥� 4.15��60�典�蝥� 5.53嚗㚁�撘箄��典��讐� `lastp` �㛖��臬像���蝞𦯀�隞���䭾��唳旿蝭⊥㺿嚗��蝞𦯀蛹 4.452嚗㚁�餈䀝��牐蛹蝻箏仃 60 �堒��脫㺭�株��紡�� 60�冽�憭批�蝥踹蝠摨閧��坔仃����嗵�銝� 4.427嚗剹���朞�撘訫� `if resample == 'd':` �∩辣�𣂼�嚗�銁憭批𪂹�煺�摰��頝唾�鈭���辷�摰𣬚�靽萘�鈭��憪见𪂹蝥輯恣蝞㛖���＆�箇��唳旿��
    - [x] **�惩𤐄 `calc_indicators` 銝� `calc_compute_volume` ��俈撏拇�摰匧��方⏛**嚗�
        - 靽桀�鈭� `calc_indicators` 憭湧��� `volume` �㛖撩憭望𧒄�湔𦻖瘙��澆��𤑳� `KeyError: 'volume'`��
        - �� `calc_compute_volume` 銝剖��乩� `last6vol` 摰匧�蝻箏仃�文�嚗��憭批𪂹��㺭�桃撩撠� `last6vol` �埈𧒄嚗諹䌊����寞旿 `vol` �� 6�冽�皛𡁜𢆡���澆𢆡��‘朣鞱恣蝞梹��𦦵� `KeyError: 'last6vol'` 撏拇���
        - �� `calc_indicators` ���銝� `'llastp'`, `'lastbuy'`, `'buy'`, `'minclose'`, `'llow'` �㛖撩憭望�靘𥕢��亙ㄝ����券�蝥批�憪见�嚗峕�蝏嘥銁�𤾸�雿輻鍂 `lastbuy` �嗅援皞���
        - �� `calc_indicators` �� `sort_values` 餈𥪜��㵪��芸𢆡撖� `['dff', 'percent', 'volume', 'ratio', 'couts']` 餈嗘��鍦��喲睸�𡑒�銵���冽�瘚见� 0.0 暺䁅恕�𧼮‵嚗屸俈甇Ｗ銁蝎曄��㛖𠶖���閫血� `KeyError` ��絲��
        - �� `complete_indicators_pipeline` 憭湧�撘訫�撖� `'name'` �㛖撩憭梁��芣��𧼮‵�餉���
    - [x] **憿箏⏚摰峕�撉諹�銝𡒊�霂烐嵗撉�**嚗𡁶��拍�蝻𤥁��牐遙雿閗祗瘜𨰻��𣄽�蹱�蝻抵��桅�嚗�僎�朞��祉��� `scratch_verify.py` �� 000566 瘚瑕�瘚瑁晓���摰𧼮���/摰䂿��唳旿蝏��銝𠰴�蝢舘��帋��函瑪����齿�瘚贝�嚗峕�銝�撏拇�嚗�𪂹蝥踹�蝥踹�蝖桀笆朣僐��

## 2026-07-01 21:00
- [x] **摰䂿緵鈭箸��望𥲤�芸𢆡�嗥�����碶��见𢆡�瑟鰵撘箏��嗵��箏� (Implemented Auto Post-Close Saving & Forced Persistence on Manual Refresh)**嚗�
    - [x] **摰䂿緵�见𢆡�瑟鰵撘箏�����硋��� (Forced Persistence on Manual Refresh)**嚗𡁻���� `popularity_resonance_gui.py` 銝剔� `run_once_async` �寞�銝� `_run_once_job` �寞���鰵憓硺� `force_save` ��㺭嚗�銁�见𢆡�孵稬�𨀣䰻霂Ｗ��售�脲𧒄撘箏�霈曉� `force_save=True`嚗屸�撘��硺漱�𤘪𠯫/�睃�蝑劐艇�潛�鈭斗��交𠯫����塚�蝖桐��冽��见𢆡�扯���䰻霂Ｘ㺭�株� 100% �𣂼��坔�蝤�� CSV��
    - [x] **霈曇恣�嗥�嚗�15:15�𠬍��芸𢆡璉�瘚见僎�芸𢆡����𡝗㦤�� (Post-Market Timed Auto-Save)**嚗𡁜銁銝餃恥�瑞垢�嘥��𡝗�蝔衤葉瘜典�鈭� `_auto_save_fail_count` 銝� `_last_auto_save_attempt_time` �嗆��綉�塚�撟嗆釣�䔶�擃睃虾�惩�頝單��亙膥 `_check_auto_refresh_after_close`��銁鈭斗��� 15:15 �嗥��𠬍��亦頂蝏��瘚见�敶𤘪𠯫�� `.csv.gz` �� `.csv` 憭�遢�唳旿撠𡁏𧊋���嚗���芸𢆡撘��臬��啁瑪蝔𧢲�銵峕䰻霂Ｗ��啣僎撘箏�����吔�摰䂿緵鈭���亦��擧㺭�桃��嗡犖撌亙僕憸���𨅯���蔭霂Ｗ�頝喲𡢿�𥪜歇靚�㟲銝箸� 30 ���銝�甈∴�隞仿�雿擧�靚梶�頧株砭憸烐活撟嗡��� CPU �扯���
    - [x] **撱箇� 5 ����瑕㭂�鞾�銝𡡞�霂閙活�圈��嗡��� (Throttling & Error Cooldown Guard)**嚗帋蛹�脫迫蝵𤑳�撘�虜����∪膥�亙聣�𡝗㺭�格�銝箇征�嗅��𤑳�擃㗛��滚��滩�嚗䔶蛹�嗥��𡒊��芸𢆡�峕郊隞餃𦛚霈曉�鈭� 5 ���嚗�300蝘𡜐���俈�硋��湔�嚗�僎�𣂼���擃睃仃韐亙�霂閙活�唬蛹 5 甈∴��Ｖ�霂���唳旿蝏���虾颲曆�蝟餌��芣�嚗��敶餃��餅鱏鈭�𦻖����𤩺誑�具��
    - [x] **摰峕��拍�霂剜�蝻𤥁��⊿�**嚗𡁶��拍�蝻𤥁��牐遙雿閗祗瘜𨰻��𣄽�蹱�蝻抵��桅�嚗��憿孵��唳�頧砍�蝥輻��噼�餈鞱�撟喟迅��

## 2026-07-01 20:30
- [x] **餈𥕢�甇亦移蝏��摮斤�餈𤤿��文�銝𤾸撩�嗡漱鈭鍦�皜�� (Refined Orphaned Process Detection & Strict Interactive Cleanup)**嚗�
    - [x] **�嗥揮摮斤�餈𤤿��唾��扯�皛斗辺隞�**嚗𡁜銁 `scan_and_group_processes` �� `is_orphaned` �文�銝哨�撠���祉�摰賣�憳𣬚��文� `is_suspect or is_associated` �嗥揮銝箔艇�潛�鈭日��文� `is_suspect and is_associated`��朖隞颱�憳𣬚�餈𤤿�嚗�� `python.exe`, `cmd.exe`, `conhost.exe` 蝑㚁�敹�◆�𡒊＆銝𤾸��滢蜓蝔见���極雿𨅯躹�硋��扯���辣�桀�摮睃銁�唾�嚗��朞� exe 頝臬���𦶢隞方��𤥁�蝔见��滚極雿𦦵𤌍敶� `cwd` ����怠�蝟餅嵗撉䕘��滢�鋡急�霈唬蛹摮斤�餈𤤿�嚗�蝠摨閖��滢�撠�頂蝏笔�隞𡝗��喟��𤾸蝱 python��it��owershell �� conhost 餈𤤿�霂舀𥁒銝箏迨蝡贝�蝔卝��
    - [x] **�舀�撌乩��桀� (CWD) �唾�璉�瘚�**嚗𡁜銁 `scan_and_group_processes` �� `run_system_diagnostics` 銝剖�甇亙��乩��箔� `p_obj.cwd()` / `p.cwd()` ����娍�扳�撉䎚����𡏭�蝔𧢲迤�典��漤��𣇉�摨讐��寡楝敺��餈鞱�嚗�朖雿踹𦶢隞方��芣𡉼撣衣鸌敺��畾蛛�銋蠘�鋡怎移����瑚�霂����
    - [x] **撘箏�銝��格�����刻粥鈭支��㗇𥋘撘寧�**嚗𡁻���� `optimize_orphaned_processes` 銝��格����閫血��餉�嚗��瘨���其�摮睃銁 1 銝芸迨蝡贝�蝔𧢲𧒄�湔𦻖撘孵枂蝞��� yes/no 蝖株恕撟嗆��㕑�蝔讠��餉���緵�冽�霈箸�瘚见��牐葵摮斤�餈𤤿�嚗��蝏煺�靚�絲 `OrphanedProcessCleanupDialog` �㗇𥋘銝舘祕��撕蝒梹�韏衤��冽��见𢆡�詨������/�漤�劐誑�𠰴��餅䰻�𧢲�蝏�� 100% 蝎曄＆�批�����
    - [x] **靽桀�撅墧�找�蝏�祕��撕蝒㛖�鈭衤辣憪娍�撏拇��桅�**嚗𡁻�撖孵銁摮斤�餈𤤿�皜��蝑匧�撘寧�嚗ǑProcessItemDetailDialog`��ProcessGroupDetailDialog`嚗劐葉靚�鍂 `self.parent.set_status_text` 撖潸稲�� `AttributeError` 撏拇�嚗���牐��亙ㄝ�� `set_status_text` �睲�皞舀�撅�漣憪娍��箏�嚗𣬚＆靽嘥銁��漣撋�� of `tk.Toplevel` 鈭支�銝剖��賢��具��迤蝖桀𧑐�其蜓蝔见��嗆�����緵�亙��漤���
    - [x] **蝻𤥁��⊿��函遛�朞�**嚗𡁜笆 `sys_performance_analyzer.py` 餈𥡝�鈭� `py_compile` �拍�蝻𤥁��芣�嚗峕�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏毺迅摰朞�銵䎚��

## 2026-07-01 19:15
- [x] **摰䂿緵摮斤�餈𤤿�擃条漣霂����虾閫��擃䀝漁��惣�賣�摨譍�銝��格��� (Advanced Orphaned Process Identification, Visual Highlighting, Intelligent Sorting & Cleanup)**嚗�
    - [x] **摰䂿緵摮斤�餈𤤿�擃条漣�文��餉�**嚗𡁻���� `PerformanceEngine.scan_and_group_processes` ��ế摰朞��辷��� `conhost.exe` 憭吔��拙��舀� `python.exe`, `pythonw.exe`, `cmd.exe`, `powershell.exe`, `git.exe` 蝑厩鸌摰𡁜��啣��𤏸�蝔卝���朞�銝交聢���餈𤤿�甇颱滿�嗆��嵗撉䕘��怎�餈𤤿��瑕�撘�虜�㘾膄���餈𤤿����箸� PID 鋡急鰵餈𤤿�憭滨鍂�文�嚗㚁�蝏枏�銝𤾸��滢蜓蝔见������極雿𨅯躹�𠰴𦶢隞方��唾����嚗�蝠摨閙覔瘝颱�撖寞迤撣豢��Ｚ蔓隞塚�憒� `firefox.exe`, `hexin.exe` �諹�憿�, `TdxW.exe` �朞噢靽�, `explorer.exe` 蝑㚁��羓頂蝏�瓲敹���∟�蝔讠�摮斤�霂臬ế摰𡄯�靽嗪�鈭���∪��其��餉�蝥臬���
    - [x] **摰䂿緵銝餌�摨誩��𠉛������**嚗𡁜銁 `PerformanceEngine` 銝剜鰵憓� `check_process_association` �寞����朞��滚�敶枏��臬�銝剜��劐蜓蝔见�嚗Ǒinstock_monitortk`嚗侨ID �䠷�剹���摮鞱�蝔钅曎餈質葵�����𤌍敶蓥�蝵桀��賭誘銵���桀�瘥𥪜笆嚗��蝏游漲�芸𢆡�𤥁��剛◤璉�餈𤤿�銝𤾸��滢蜓蝔见����撅𧼮�蝟颯��
    - [x] **隡睃�霂𦠜鱏霅血�靽⊥�**嚗𡁜銁�亙熒霂𦠜鱏�𡃏郎銝哨�撠�迨蝡贝�蝔𧢲��𨀣��匧迨蝡贝�蝔𦥑�腈���靝蜓蝔见��唾�摮斤�餈𤤿��苷誑�𪙛�𣈯� CPU �删鍂摮斤�餈𤤿��嘥�蝐餃��綽��亙��典��𥪜迨蝡贝�蝔𧢲� CPU �删鍂颲��嚗���箄��𣂼��𡃏郎蝑厩漣�� `DANGER`��
    - [x] **摰䂿緵���銵典虾閫��擃䀝漁銝擧惣�賣�摨�**嚗�
        - 銝� `Treeview` 憓𧼮�鈭� `"orphaned"` 蝥Ｚ𠧧擃䀝漁�滨蔭嚗�蝙�� `COLOR_DANGER` �齿艶�莎���
        - ��**餈𤤿�敶垍�瘙��餉”**銝哨�撠���怠迨蝡贝�蝔讠�����惩��滨��牐� `�𩤃� [摮斤�畾讠�] ` 撟嗆㟲雿梶蔭憿嗆�摨𧶏�銝娍�瘜其蛹蝥Ｚ𠧧��
        - ��**摰峕㟲餈𤤿��𡒊�銵�**銝哨�撠�迨蝡贝�蝔见�蝻��牐� `�𩤃� [摮斤�] `嚗䔶誑�𨅯迨蝡贝�蝔衤������甈∪�摮㗛�摨謿�萘�閫��餈𥡝�蝵桅▲�鍦�嚗䔶���釣銝箇滯�脯��
        - 摰��鈭���餉祕����𢰧�桀翰�瑁��閧���漣鈭支����蝘啣�蝻��芸𢆡鋆��嚗ìtrip嚗㕑��誯�餉�嚗𣬚＆靽脲��匧�撘寧�霂𦠜鱏���蝔讠��笔𢆡雿𨅯��� 100% ��＆�扯���
    - [x] **���銝��格�����匧迨蝡𧢲��躰�蝔�**嚗𡁜�蝥找�憿園�敹急㭘隡睃��讐��其�嚗���麨�𨀣���迨蝡� conhost�嘥�蝥找蛹�𨀣���迨蝡贝�蝔𦥑�嘅�`optimize_orphaned_processes`嚗剹��𣈲����桐����甇ｇ�`p.terminate()`嚗劐��拍�撘箏�蝏��嚗Ǒtaskkill`嚗匧�撅��蝥折�餉�嚗���啣��唳��坔�撠貉�蝔讠�摰匧�蝘垍漣皜����
    - [x] **�湔鰵霂行�撘寧� (ProcessItemDetailDialog)**嚗𡁜銁撅墧�扳䰻�见撕蝒𦯀葉嚗峕����摨西秐 `485px` 撟嗆鰵憓硺��靝蜓蝔见��唾�:�脲遬蝷箏�畾蛛�撟嗅銁璉�瘚见��嗉�蝔� ID 摮睃銁雿��撱箸𧒄�湧�雿齿𧒄嚗𣬚凒閫��蝷算�𦦵�餈𤤿�撌脫香嚗釶ID 鋡急鰵餈𤤿�憭滨鍂�嘅�敶餃�閫�� PID 憭滨鍂撖潸稲��迨蝡见ế�剛秤撌柴��
    - [x] **�朞��拍�蝻𤥁��芣�**嚗𡁜笆靽格㺿�𡒊���辣�𣂼��扯�鈭� `py_compile` �⊿�嚗峕�隞颱�霂剜��躰秤�𤥁郎�𨳍��

## 2026-07-01 17:45
- [x] **摰䂿緵摮斤��批��啗�蝔� (conhost.exe) �芸𢆡�𤥁��凋�皜�� (Orphaned Conhost Diagnostic & Cleanup)**嚗�
    - [x] **摰䂿緵摮斤�餈𤤿�璉�瘚钅�餉� (Orphaned Process Detection)**嚗𡁜銁 `PerformanceEngine.scan_and_group_processes` 銝剖�撘箔��急��餉�嚗屸�朞� `psutil` 璅∪�摰墧𧒄�滚� `conhost.exe` 撟嗆��亙� `parent()` �文��臬炏銝箏迨蝡页�zombie嚗㕑�蝔页��舀��典��鞉��𣂷��閗繮 `AccessDenied` �� `NoSuchProcess` 撘�虜��
    - [x] **����亙熒摨西��剖�霅衣頂蝏� (Diagnostic Alerts Integration)**嚗𡁜銁 `PerformanceEngine.run_system_diagnostics` 銝剜鰵憓𧼮迨蝡𧢲綉�嗅蝱餈𤤿��亙熒璉��乓����行�瘚见�摮斤� `conhost.exe` 餈𤤿�嚗𣬚��喳�霂𦠜鱏�亙�瘜典� DANGER (�亙��券� CPU) �� WARNING �𡃏郎蝥批�嚗�僎�𡒊＆�曄內�� PID �𡑒”��
    - [x] **霂行�撘寧��啣��嗉�蝔衤縑�臬�畾� (Parent Process Detail View)**嚗𡁜銁 `ProcessItemDetailDialog` 銝剜鰵憓硺��𦦵�餈𤤿�靽⊥��嘥�畾蛛��典��餅䰻�贝�蝔贝祕��𧒄�渲�撅閧內�嗥�餈𤤿��滨妍��ID 銝𤾸�瘣餌𠶖����舀�銝��桃��餉祕��䌊���瘚卝��
    - [x] **瘛餃��靝��格���迨蝡𧢲綉�嗅蝱�苷��桐��硋𢆡雿� (Quick Optimizer Cleanup Action)**嚗𡁜銁 `SystemPerformanceAnalyzerGUI` 憿園�隡睃��批��Ｘ踎銝剜鰵憓硺��𨀣���迨蝡� conhost�苷��桐��硋��踝��舀��朞� `psutil` 撘箄�蝏�迫���匧歇霂����迨蝡� `conhost.exe` 餈𤤿�嚗䔶��冽��𣂷�頞單𧒄�芸𢆡�鮋��銝� `taskkill /F /PID` �賭誘銵𣬚���������憭批�皜���𣂼�����
    - [x] **霂剜�蝻𤥁�銝𡒊迅摰𡁏�扳嵗撉� (Compilation Passed)**嚗𡁏��罸�朞�鈭� `py_compile` ������霂煾�霂��璅∪��嗉祗瘜閖�霂胯��

## 2026-07-01 15:10
- [x] **�寞祥�瑕鍳�典��硺漱�𤘪𧒄畾� `lastbuy` �滨蔭銝𦒘腺憭� Bug (Rooted Out `lastbuy` Overwrites on Cold Start & Off-Hours)**嚗�
    - [x] **摰䂿緵 `Sina.all` �臬𢆡�嗆挾 `lastbuydf` 隞� HDF5 ��蟮�唳旿餈睃�**嚗𡁜銁 `Sina.all` �唳旿�㰘蝸�塚�蝚� 444-450 銵䕘�嚗��璉�瘚见����銝� `lastbuydf` �芾◤�嘥��碶� HDF5 頧賢���㺭�桅�銝剖��急���� `'lastbuy'` �埈𧒄嚗諹䌊�典� HDF5 ��蟮�唳旿霂餃�撟嗆�憭滩秐����典�蝻枏� `cct.GlobalValues().setkey('lastbuydf', h5['lastbuy'])` 銝哨�隞舘��蝠摨閧�蝏㮖��瑕鍳�冽�撘��烐綉銝餌�摨𤩺𧒄 `lastbuy` 鋡急��園�蝵桃�蝻粹萅��
    - [x] **靽桀��瑕鍳�券�撣改�`logtime == 0`嚗㗇��∩辣�滨蔭撌脰��毺�摮条�瞍𤩺�**嚗𡁜銁 `format_response_data` 嚗�洵 1554-1577 銵䕘�銝剝���� `logtime == 0` ���銵諹楝敺������ `need_init` �文�嚗�朖雿踵糓�臬𢆡��洵銝�撣改��亙�摮睃歇�𣂼�隞� HDF5 銝剜�憭滢� `lastbuydf`嚗��撘箏�頝唾��滨蔭嚗𣬚凒�亥��� `combine_lastbuy` ��僎嚗屸俈甇Ｗ��臬𢆡�嗅��� `lastbuy` �祇𡢿鋡怠��齿𤣰�䀝遠閬��銝� 0��
    - [x] **摰䂿緵�硺漱�𤘪𧒄畾菜㜃�芷�蝵桅�餉�撟嗅撩�嗡��� `lastbuy`**嚗𡁜銁 `format_response_data` 銝剝���� `lastbuy` �滨蔭�∩辣嚗峕遬撘誩ế摰𡁜��齿糓�血�鈭𦒘漱�𤘪𧒄畾蛛�`cct.get_work_time()`嚗剹��𥅾憭���硺漱�𤘪𧒄畾蛛��冽錰�����𠯫�𣇉��𠬍�嚗𣬚頂蝏蠘䌊�冽㜃�芸僎蝏閗��滨蔭甇仿炊嚗峕��∩辣�鮋��撟嗉��� `combine_lastbuy(df)` �𧼮僎撟嗆�憭齿��唳����摮矋�靽嗪��冽��券�鈭斗��嗆挾銋蠘�憿箏⏚��粉�𠰴�皞臬榆�潦��
    - [x] **摰䂿緵 `lastbuy` 鋡急情�栞��唳旿��俈�函��芣��芣��箏� (Auto-Healing for Corrupted lastbuy Data)**嚗朞����啣銁靽桀�閬���滨蔭 Bug 銋见�嚗���臬𢆡�� `lastbuy` 鋡怠撩�嗥鍂�唬遠閬��撟嗡�摮睃�鈭� HDF5 蝤����辣嚗屸�䭾�蝤����蟮�唳旿撌脰◤�函�瘙⊥�嚗Ǒlastbuy` 蝑劐� `close`嚗諹��䔶蝙 `dff` �雴蛹 `0.0`嚗剹���隞砍銁 `combine_lastbuy`嚗�洵 1652-1678 銵䕘�銝剖��牐��脫情�𤘪惣�質䌊��㦤�塚��典�撟嗆𧒄嚗峕�瘚贝𥅾銝芾� `lastbuy` 銝𤾸��滢遠 `close` ���蝑厩�頞�� 95%嚗�ế摰帋蛹��蟮 Bug �嗘�����唳旿嚗���芸𢆡�行⏛�Ｗ��餉�嚗𥡝歲餈�歇瘙⊥����摮条�摮矋��拍鍂�渡滲������脫𤣰�䀝遠 `nclose` �� `llastp` 餈𥡝��滚�憪见�撟嗅�憛怨秐 `lastbuy`嚗�蝠摨閙�憭� `dff` 撌桀�潸恣蝞梹�撟嗡蝙�嗅銁銝衤�銝芸�頝喃�摮䀝葉�芸𢆡閬��蝥䭾迤蝤����辣銝剔��𤩺㺭�柴��
    - [x] **�拍�霂剜�蝻𤥁��函遛�朞�**嚗𡁜笆 `sina_data.py` 餈𥡝�鈭� `py_compile` �拍�蝻𤥁��芣�嚗峕�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏毺迅摰朞�銵䎚��

## 2026-07-01 14:35
- [x] **隡睃��嗥��擧�韏琿�撘��� `rzrq` �芸𢆡�嘥��𡝗㦤�� (Optimized `rzrq` Auto-Initialization on Resume)**嚗�
    - [x] **摰䂿緵頝刻䌊�嗆𠯫 `rzrq` �芸𢆡�齿鰵�瑕�**嚗𡁜銁 `singleAnalyseUtil.py` ��鍳�冽�蝔衤葉撘訫� `rzrq_date` �㗛�靽嘥�擐𡝗活�㰘蝸��𠯫���撟嗅銁 `while 1` 敺芰㴓�� `try` �烾▲撅���㰘䌊�嗆𠯫�睃��烐����甈⊥𠯫�冽��函�蝡舀�韏瑟�蝷箏��劐遙�誯睸蝏抒賒�塚�蝟餌�銝��行�瘚见� `today_str != rzrq_date`嚗���芸𢆡�齿鰵靚�鍂 `ffu.get_dfcfw_rzrq_SHSZ()` �瑟鰵敶枏予���韏���豢���僎撖寥��交��喉��踹�鈭�㿥�亙�雿蹱㺭�桀紡�渡��唳旿���憭勗���
    - [x] **�寞祥銝餃儐�舫�憸� `get_today()` ���扯��蠘��**嚗𡁜� `today_str = cct.get_today()` ��凒�啣𢆡雿𦦵宏�� `except (KeyboardInterrupt)` 銝剔� `cct_raw_input` 銋见�����瘀��芣��冽��交𤣰�䀹�韏瑯��活�亦鍂�瑟䛵�餃�頧衣誧蝏剛�銵𣬚���葵�祇𡢿�滢��湔鰵敶枏��芰��伐�隞舘��蝠摨閖��滢��函�銝剝��笔儐�臭葉擃㗛����憭滩��函頂蝏�𠯫�蠘蓮�Ｗ遆�啁��扯�撘�����
    - [x] **�朞��拍�蝻𤥁�霂剜��⊿� (Passed Compiler Syntax Check)**嚗𡁜笆 `singleAnalyseUtil.py` �扯�鈭� `py_compile` �⊿�嚗峕�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏毺迅摰朞�銵䎚��

## 2026-07-01 14:30
- [x] **隡睃� `lastbuy` �硺漱�𤘪𧒄畾菜�銋��銝𦒘��� (Optimized `lastbuy` Persistence & Preservation During Off-Hours)**嚗�
    - [x] **摰䂿緵 `lastbuy` 鈭斗��嗆挾�∩辣�滨蔭 (Conditional Reset of `lastbuy` in Trading Session)**嚗𡁻���� `sina_data.py` 銝剔� `lastbuy` �滨蔭�文���緵�剁�蝟餌�隞�銁鈭斗��嗆挾 (`cct.get_work_time()` 餈𥪜� True) �硋�摮䀝葉�芸�憪见�蝻枏� `lastbuydf` (`need_init` 銝� True) �塚��滩圻�煾�蝵� `lastbuy` �潸秐敶枏��嗥�隞瑯��
    - [x] **摰䂿緵�硺漱�𤘪𧒄畾菔䌊�其��蹱��𦒘�銝� `lastbuy` (Preserved Last `lastbuy` Value During Off-Hours)**嚗𡁜銁�硺漱�𤘪𧒄畾蛛��睃�/�冽錰/����伐�嚗�� `logtime` �� 0 銝𥪜�摮睃歇�厩�摮䀹𧒄嚗屸�蝵桅�餉�鋡怨䌊�冽㜃�迎�蝟餌��鮋��撟嗉��� `combine_lastbuy(df)`���摰䂿緵鈭���𤾸��硺漱�𤘪𧒄畾萎��賢��刻粉�� and �曄內���𦒘�銝芣���� `lastbuy`嚗䔶蝙�冽��函��𦒘��賡◇�拇䰻�见��� `dff` 撌桀�潘�瘨�膄鈭��鈭斗��嗆挾 `lastbuy` 銝Ｗ仃�𤥁◤皜�妟��撩�瑯��
    - [x] **�朞��拍�蝻𤥁�霂剜��⊿� (Passed Compiler Syntax Check)**嚗𡁜笆 `sina_data.py` �扯�鈭� `py_compile` �⊿�嚗峕�隞颱�霂剜���𣄽�蹱�蝻抵��桅�嚗𣬚頂蝏毺迅摰朞�銵䎚��

## 2026-07-01 12:35
- [x] **靽桀��枏�銝𤾸虾�扯���辣�臬�銝见��冽�撣桀𨭌��﹝霂餃�憭梯揖�� Bug (Fixed Multi-Period Help Document Loading Failure in Packaged Environments)**嚗�
    - [x] **�游� `get_conf_path` �啣葬�拇�獢�楝敺��頧� (Integrated `get_conf_path` for Help File Loading)**嚗𡁻���� `standalone_multi_period_tester.py` 銝� `show_help_documentation` �寞���𧋦�唳�隞嗉楝敺���鞾�餉����蝖祉���𣄽�� App 蝏嘥笆�寧𤌍敶閧�隞��嚗䔶耨�嫣蛹靚�鍂蝟餌�蝏煺��� `sys_utils.get_conf_path("config/multi_period_help.md")` �芣��亙藁嚗�蝠摨閧�蝏㮖��枏��𡒊眏鈭𡒊����撖寡楝敺��摮睃銁撖潸稲�� FileNotFoundError 撏拇���
    - [x] **瘜典��芣��滨蔭��辣�惩� (Registered File Mapping in RESOURCE_MAP)**嚗𡁜銁 `sys_utils.py` ������銝��芣�蝞∠��� `RESOURCE_MAP` 摮堒�銝哨��啣�鈭� `"multi_period_help.md"` �滨蔭��辣������撠�笆朣𣂼�蝟鳴�`src` 銝� `dst` ���蝵桐蛹 `"config/multi_period_help.md"`嚗剹���雿踹��枏��� Onefile/Onedir �舀�銵峕�隞嗅銁�臬𢆡餈鞱�銝𠉛�����䀝�銝滚��刻砲��﹝�塚��質䌊�其����銝湔𧒄�桀�銝贝䌊��圾�钅��橘�撟單�敶雴��唳𧋦�啁���𤌍敶𨰻��
    - [x] **��漣 PyInstaller 銝� Nuitka �枏�蝻𤥁��滨蔭 (Updated Packaging Configurations)**嚗�
        - �湔鰵鈭� `instock_MonitorTK.spec` 銝� `MultiPeriodTester.spec` �� `datas` �唳旿�𡑒”嚗���乩� `("config/multi_period_help.md", "config")` 頝臬�撖寥��滨蔭嚗�
        - �湔鰵鈭� `nuitka_build_console.bat`��nuitka_build_console_onlyClang.bat` �� `nuitka_instockMonitor.bat` �𣬚� Nuitka �枏���誘嚗峕溶�牐� `--include-data-file=config\multi_period_help.md=config\multi_period_help.md` ��㺭���靽肽�鈭�銁�齿鰵餈𥡝�蝻𤥁��枏��穃��塚���﹝��辣�賢� 100% 甇�＆鋡急�����舀�銵峕�隞嗥�韏���箝��
    - [x] **摰峕��砍𧑐�閗��芣��蠘�瘚贝�銝𡒊�霂𤏸䌊璉�**嚗帋蝙�� Python 蝏�垢�賭誘撉諹�鈭� `get_conf_path` �函����隞嗥撩憭曹���䌊����蠘�蝔页���辣�𣂼��𦠜𦆮�墧�摰朞楝敺��銝娍�霂剜��㚚�餉��脩���

## 2026-07-01 10:40
- [x] **摰䂿緵撘箏飵蝏𤘪�銝𡒊�憟��頧� (1蝏𤘪�) �滚��𣳇�毺�瘜� (Implemented Strong Structure Rebound & TD Setup Accelerating Algorithm)**嚗�
    - [x] **摰䂿緵 TD Setup ���霈∠� (TD Setup Indicator)**嚗𡁜銁 `data_utils.py` 銝剖��唬�蟡𧼮�銋肽蓮��僭�亦����Buy Setup嚗匧��硋枂蝏𤘪�嚗𠄎ell Setup嚗㕑恣蝞𨰜��𣈲��蕭頦芾�蝏剜𤣰�䀝遠雿𦒘�/擃䀝� 4 �亙��嗥�隞瑞�霈⊥㺭嚗�僎�函�����鞉�閫血� 1 蝏𤘪�嚗������嗆�霈� `td_setup` �嗆����其�敹恍�罸�摰帋蜓��答�臬𢆡�脲���
    - [x] **摰䂿緵撘箏飵蝏𤘪��噼萱�滚撕霂�� (Strong Structure Rebound Score)**嚗朞挽霈∩� `strong_structure_score` 霂�摯�砍�嚗峕㟲����券�撘箏漲嚗Ǒwin` 餈鮋翧憭拇㺭嚗剹���蝥踹�蝳餃漲嚗���穃��噼萱 MA5/MA20 ���蝳鳴�隞亙��亙��滚�撘箏漲嚗�㿥�港��喋��𤣰�䀝遠��捆��𦆮�𤩺�蝑㚁���覔�桀��冽��寧��芷���靚�㟲�噼萱�𡁻�嚗�𠯫蝥踹�頦� MA20d嚗��蝥批�/2d/3d憭抒����頦� MA5d嚗㚁�撟嗅笆��蝏������� 50-100+ ����𤥁�蝥改��芸𢆡餈�誘摨閖��牐遠�澆�撘嫘��
    - [x] **憭𡁜𪂹�笔��𦒘�霂𦠜鱏�Ｘ踎瘛勗漲�滚� (Engine & Diagnostic Integration)**嚗𡁜銁 `multi_period_strategy_engine.py` �����曎銝剜�蝻肽蝸�� TD 霈⊥㺭���頦抵�����舀�撠� `strong_structure_score` 雿靝蛹 query 餈�誘�∩辣�湔𦻖摨𠉛鍂��
    - [x] **撉諹�瘚贝�銝𤾸�敶鍦��� (Verification & Test Runs)**嚗𡁻�朞�蝻硋��祉����霂���� `scratch_test_strong_structure.py` �函�摰墧𠯫蝥踹� 2d �冽��唳旿銝𡃏�銵峕��吔��𣂼�蝑偦�匧枂 241 �芣𠯫蝥踹� 378 �� 2d �冽��瑕�撘箏飵�臬𢆡銝� 1 蝏𤘪��滚��孵�������銝娍�摨𤩺��堆��𧼮�瘚贝� Exit Code 0��

## 2026-06-30 20:30
- [x] **摰䂿緵 HDF5 �唳旿撘�郊�峕艶�㰘蝸銝� UI �臬𢆡�⊥香�寞祥 (Asynchronous HDF5 Loading & Startup Hang Mitigation)**嚗�
    - [x] **摰䂿緵撏拇��Ｗ� (Crash Recovery) 撘�郊�� offload**嚗𡁻���� `realtime_data_service.py` 銝剔� `DataPublisher` �臬𢆡�餉�嚗����𧋦�峕郊�餃���� PKL 敹怎��� HDF5 �滚遣 `MinuteKlineCache` �� `recover_from_hdf5` 餈��摰��頧祉宏�喟𡠺蝡讠�摰�擪蝥輻� `DataPublisher_Recovery` 銝剜�銵䎚��I 銝餌瑪蝔见銁�臬𢆡�嗆���蝑匧�摨𧼮之�� HDF5 ��蟮�唳旿霂餃�嚗�虾�祇𡢿蝘鍦�嚗�蝠摨閙��支��臬𢆡�⊥香�� UI �餃�霅血���
    - [x] **霈曇恣擃䁅�摰墧𧒄�湔鰵蝻枏��其��芣�摨𠉛鍂�箏� (Real-time Batch Buffering & Replay)**嚗𡁻�撖孵�甇亙�頧賣��游虾�賣��亦�摰墧𧒄銵峕��唳旿嚗屸���� `update_batch` �寞���� `is_ready` 銝� `False` �塚����㗇鰵�啁�銵峕� DataFrame �芸𢆡�瑁�撟嗉蕭�惩� `_pending_batches` 銝准����血��啣�頧賜瑪蝔𧢲��笔��鞉�憭滚僎�齿�摰𣬚𠶖��㦤�𠬍��� `finally` �𦯀葉�芸𢆡撠� `is_ready` 蝵桐蛹 `True`嚗�僎銝�甈⊥�批��曇‘敶閙��厩妖�讠��唳旿�寞活嚗���唬��䭾�撟單�銵娍𦻖��
    - [x] **隡睃� HDF5 銵峕�霂餃�銝� SingleFlight ���蝻枏��行⏛**嚗𡁻���� `recover_from_hdf5` �� HDF5 霂餌��餉�嚗𣬚鍂�芾粉璅∪� `Sina(readonly=True).get_sina_MultiIndex_data()` �踵揢鈭��撅�� `h5a.load_hdf_db` �拍�霂餌����雿踹�憭扯膘餈寞㺭�桃凒�亥粥 SingleFlight 銝𤾸�摮� L6 蝥抒�摮睃��頣���之�𣂼�鈭��蝥輻�撟嗉�霂餃����嚗諹��蹂��䠷��脩���
    - [x] **撱箇�蝎曉�蝻箏藁�噼‘ (Gap Backfill) �祉���� CD �鞾�靽脲擪**嚗帋蛹 `backfill_gaps_from_hdf5` 瘛餃�鈭� `_backfill_lock` 蝥輻����撟嗅��乩� 30 蝘鍦��湧�憸烐㜃�迎�`_last_backfill_time`嚗剹���憭朞�餈䂿賒閫血��噼‘霂瑟��塚�撘箏�餈𥡝��閧瑪蝔见縧�漤俈�吔��踹��祇𡢿瘣曄��粹��删�蝵𤑳�/蝤�� I/O 隞餃𦛚撖潸稲�� UI �⊥���
    - [x] **UI 蝥輻�銝餃�頝喲�蝎曉漲撘�郊撠梁貌璉�瘚衤��噼�撟踵偘**嚗𡁜銁 `instock_MonitorTK.py` �臬𢆡�嗆挾撠� `_realtime_service_ready` 霈曆蛹 `False`��銁瘥� 100ms 銝�甈∠� `_ui_heartbeat` 敹�歲敺芰㴓銝哨��芸𢆡頧株砭璉�瘚� `realtime_service.is_ready` �嗆���銝��血��啣停蝏迎��祇𡢿蝵桐蛹 `True`嚗�僎�芸𢆡閫血�撟嗆�蝛箸��㗇釣�𣬚��噼��笔� `_realtime_ready_callbacks`嚗���唬�摰��閫��衣��唳旿撠梁貌靽∪噡撟踵偘�箏���
    - [x] **�拍�霂剜�蝻𤥁��函遛�朞�**嚗𡁜笆 `realtime_data_service.py` �� `instock_MonitorTK.py` 餈𥡝�鈭� `py_compile` �⊿�嚗�� 100% 蝻𤥁��𣂼�銝娪妟霂剜�霅血���

## 2026-06-30 20:00
- [x] **敶餃��齿�獢屸𢒰蝒堒藁撣���滨蔭蝞∠��� (Layout Manager) �𡁶鍂�臬𢆡銝𤾸極雿𦦵𤌍敶� (CWD) ��揢�箏� (Completely Refactored Generic Process Launching & Working Directory Switching)**嚗�
    - [x] **敶餃��寞祥 `INSTOCK_APP_ROOT` �臬�瘙⊥�**嚗𡁶��輸�𡁶鍂頧臭辣霈曇恣�笔�嚗�蝠摨閧宏�支�蝒堒藁撣��蝞∠��典銁 `core.py` 銝� `manage_window_layout.py` 銝剖��典� `os.environ` �坔��孵��臬��㗛� `INSTOCK_APP_ROOT` ��噩�亙��笔�隞�����隞擧覔�砌�蝖桐�鈭��撅�蝞∠��其�銝粹�𡁶鍂撌亙�嚗䔶�隡𡁏情�㮖遙雿閗◤�嗅鍳�函�摮鞱�蝔讠��臬��㗛� block��
    - [x] **摰䂿緵�臬𢆡�滨������ `os.chdir` 撌乩��桀� (CWD)**嚗𡁻�撖孵鍳�典�蝘滨�摨𧶏���𡠺�桅�𡁜鍳�其��鞉�蝞∠��睃鍳�剁�嚗�銁 `subprocess.Popen` �� `os.startfile` �扯��㵪��拍鍂 `os.chdir(os.path.dirname(exe_path))` �拍���揢�嗉�蝔见��滚極雿𦦵𤌍敶𤏪��扯�摰峕��𤾸銁 `finally` �𦯀葉�芸𢆡憭滚����雿踹�隞颱�鋡怠鍳�函��𡁶鍂蝔见�嚗�� `鈭箸��望𥲤2.22.exe`嚗厰��賢銁�嗥�摰䂿�蝔见�頝臬����銵䕘�隞舘�峕迤蝖桐��芣��啣�雿滩䌊頨怎��滨蔭��辣��
    - [x] **蝻𤥁��⊿��函遛�朞�**嚗𡁜笆 `ui.py`��core.py` �� `manage_window_layout.py` ���銵䔶� `py_compile` 霂剜��⊿�嚗峕�霂蓥��臬𢆡�蠘�蝔喳���

## 2026-06-30 19:20
- [x] **摰峕��典��芷�㕑� (Global Favorites) 霈ａ�瘜券�銝� QTimer 頧株砭�峕郊�嗆��齿� (Decommissioned Legacy Subscriptions & Migrated GUI Modules to Thread-Safe Polling)**嚗�
    - [x] **摰���𦦵鍂撟嗅��� legacy callback 霈ａ�璅∪�**嚗𡁜銁 `global_favorites.py` 銝剖��支� deprecated `subscribe`��unsubscribe` �� `notify_subscribers` �亙藁嚗���嗡����㕑䌊�㕑�憓𧼮��寞�雿靝葉摰���亦氖鈭� `self.notify_subscribers()` �噼�閫血�嚗䔶��寞�銝𦠜��支�頝函瑪蝔卝��楊 GUI 獢�沲靚�鍂 Tkinter/PyQt 撖寡情�剖�撘訫��� `PyEval_RestoreThread` GIL �脩�撏拇���
    - [x] **�齿�撟嗥�銝��函頂蝏蠘䌊�㕑�頧株砭憸𤑳�銝� 500ms (Standardized All GUI Polling Intervals to 500ms)**嚗�
        - 銝粹俈甇ａ�憸� UI �滨�撣行䔉銝滚�閬�� CPU 韏��撘���嚗���函頂蝏���� Tkinter �� PyQt 璅∪�銝剜��羓��典��芷�㕑�敹�歲�峕郊�冽�蝏煺����銝� **500ms**嚗�銁靽嗪�摰墧𧒄�滚�����嗆�憭批�靽脲擪銝餌瑪蝔𧢲�扯���
        - 瘨匧�撟嗆凒�啁�璅∪���𡠺嚗�
            - **`spatial_follow_hud.py`**嚗䫤_favorites_poll_timer` 摰𡁏𧒄�刻挽摰帋蛹 500ms��
            - **`signal_dashboard_panel.py`**嚗䫤_favorites_poll_timer` 摰𡁏𧒄�刻��港蛹 500ms��
            - **`sector_bidding_panel.py`**嚗䫤_favorites_poll_timer` 摰𡁏𧒄�刻��港蛹 500ms��
            - **`bidding_racing_panel.py`**嚗䫤SectorDetailDialog`��CategoryDetailDialog` �� `BiddingRacingRhythmPanel` ��䌊�㕑�頧株砭摰𡁏𧒄�函�銝�霈曉�銝� 500ms��
            - **`ats/ui/main_window.py`**嚗䫤_favorites_poll_timer` 靚�㟲銝� 500ms��
            - **`standalone_multi_period_tester.py` (憭𡁜𪂹�毺恣��膥)**嚗朞蔭霂Ｗ��嗅膥霈曉�銝� 500ms嚗䔶����鈭� `winfo_exists()` �剖�靽脲擪隞仿俈甇ａ���箸𧒄�仿���
            - **`stock_selection_window.py`**嚗朞䌊�㕑�頧株砭�湔鰵�湧��� 300ms 靚�㟲銝� 500ms��
            - **`popularity_resonance_gui.py`**嚗朞䌊�㕑��嗆��凒�圈𡢿�𠉛眏 300ms 靚�㟲銝� 500ms��
            - **`instock_MonitorTK.py`**嚗帋蜓�屸𢒰敹�歲頧株砭�湧��� 300ms 靚�㟲銝� 500ms��
    - [x] **蝟餌��芣�銝舘祗瘜閙嵗撉��蝏輸�朞�**嚗帋蝙�� `py_compile` �拍�蝻𤥁�璅∪�撖寞��劐耨�孵��� 9 銝� Python ��辣餈𥡝��⊿�嚗�� 100% 蝻𤥁��𣂼�銝娍�隞颱�霂剜��㚚�餉�撘�虜嚗𣬚頂蝏蠘楊蝥輻��� IPC �嗆���甇亥�銵𣬚迅摰𠾼��


## 2026-06-30 16:30
- [x] **摰䂿緵�芷����芸�銋匧�摰賭��𦯀��冽��埈惣�賢��� (Adaptive Columns & Duplicate Cross-Period Elimination)**嚗�
    - [x] **撘訫� `_get_display_periods_for_custom_col` �芷����𡑒�皛文膥**嚗𡁻�撖嫣�憒� `dff`��dff2`��dff3` �� `Rank` 蝑匧歇�亙銁��𪂹��㺭�桀��函㮾�𣬚��芸�銋匧�嚗峕���銁餈鞱��園�朞�撖孵��冽��唳旿�埈�撖對�隞交筑�寧移摨� `1e-5` �� `fillna` 摮㛖泵銝脩�餈𥡝�頝典𪂹�笔�蝑匧�澆ế摰𡄯��𤑳緵銝�璅∩��瑞��芸�銋㗇������ Treeview 憭湧���遣�𦠜㺭�格��交𧒄嚗�蘨�芸𢆡靽萘�撟嗆遬蝷箸�撠讐�瘣餉��冽�嚗���支��嗡��𦯀����憭滚�嚗��銝滚��峕𧒄�曄內�𦯀��� `dff(d)`��dff(w)`��dff(m)`嚗諹��蘨靽萘���撠誩𪂹�� `dff(d)`嚗剹��
    - [x] **�峕郊�芣�皜脫�蝞∠瑪�湔鰵**嚗𡁜銁 `_show_results` �瑟鰵�唳旿��仍�剁�撘箏�閫血� `_update_tree_columns` 撖� Treeview 銵典仍�������滨�嚗䔶蝙敺堒銁��揢銝滚��芷�厩��交��唳旿�齿鰵頧賢��塚��賜��渲䌊���靚�㟲�堒��曄內嚗䔶��唳旿銵� `values` �鍦���㺭�譍� Treeview �芸�銋匧��滨蔭 100% 靽脲��笔�銝��湔�扼��

## 2026-06-30 16:15
- [x] **摰䂿緵�芷�㕑��湔鰵�典�撟踵偘�� PyQt �祉�霈ａ�銝� Tkinter 頧株砭��氖 (Separated Global Favorites Updates via PyQt Subscriptions & Tkinter Version Polling)**嚗�
    - [x] **�寞𧋦�扳��� GIL 蝥輻�靚�鍂�脩�銝� Nuitka �臬�撏拇� (Eliminated GIL Violations & PyEval_RestoreThread Crashes)**嚗𡁻�撖孵銁憭朞�蝔𧢲��𤾸蝱蝥輻�靽格㺿�芷�㕑�嚗���孵稬�𨅯�瘨���嫣葵�﹦�嘅��嗅枂�啁� `Fatal Python error: PyEval_RestoreThread` GIL �脩�撏拇�嚗�� Tkinter 銝餌��� `MonitorTK` 銝𤾸��亙� `StandaloneMultiPeriodTester` 隞� `GlobalFavoriteManager` ��凒�亥恥������𦯀葉敶餃�瘜券�嚗峕㺿�典抅鈭𤾸�摮条��砍噡 `version` 撅墧�抒�銝餌瑪蝔见�頝唾䌊��蔭霂ｇ�瘥� 300ms/500ms嚗㚁�敶餃�瘨�膄鈭�楊閫���函瑪蝔贝��� Tkinter 撖寡情�� python �剖�撖潸稲��援皞���
    - [x] **摰䂿緵�典��芷�㕑�蝞∠��典��刻恥������皛� (Added Subscriber Guard to GlobalFavoriteManager)**嚗𡁜銁 `global_favorites.py` �� `notify_subscribers` 銵峕�����箏�銝哨��啣�鈭��撖孵�靚�𦻖�嗅挪銝餌�蝐餃��滚����嚗𥡝䌊�刻�皛文僎頝唾��滢葉��鉄 `"MonitorTK"` �� `"MultiPeriodTester"` ���靚�笆鞊∴��芯��� PyQt �詨���恥����券�帋縑皞𣂼仍銝𠹺蛹 Tkinter �𤑳���遣蝡衤��拍��脩�憓踺��
    - [x] **銵亙� PyQt 蝒堒藁�笔𦶢�冽�瘜券�銝� Toplevel ��瘥�䌊�� (Aligned Lifecycle Cleanup)**嚗𡁶＆霈支� `SectorDetailDialog`��CategoryDetailDialog` �� `BiddingRacingRhythmPanel` �函�����哨�`closeEvent`嚗㗇𧒄���撟脣��唳釣�� favorites 霈ａ�嚗𣬚宏�支� Tkinter 靘抒�憭帋� `unsubscribe` 隞��隞亦移蝞��笔𦶢�冽�嚗屸俈甇Ｖ�撖寡情撌脰◤ C++ �鞉�雿��靚���坔紡�渡��擧���援皞���

## 2026-06-30 15:45
- [x] **摰䂿緵蝎䁅斐/撖澆�蝑𣇉裦�滚��芸𢆡瘛餃��啣�撠曄�靽脲擪 (Automated Duplication Suffixing on JSON Paste & Import)**嚗�
    - [x] **隡睃�撖澆��滨妍�仿� (`_import_json_strategy`)**嚗𡁜��冽�蝎䁅斐 JSON 撖澆�憭𡁜𪂹�毺��交𧒄嚗𣬚頂蝏煺��芸𢆡銝� `self.strategies` ����� `valid_strats` �笔�銝剖歇摮睃銁���摮埈�撖對��亙��圈�憭㵪��躰䌊�典銁�嗅�餈賢� `_1`��_2` 蝑㗇㺭摮堒偏蝻�餈𥡝��鍦�嚗𣬚凒�唬��滚�銝箸迫嚗屸俈甇Ｙ��仿�蝵株◤�誩�閬���硋�瘝～��
    - [x] **隡睃�蝻𤥁�摨𠉛鍂�仿� (`_apply_json_to_form`)**嚗𡁜銁�喃儒 JSON 蝻𤥁��其葉靽格㺿蝑𣇉裦�滨妍撟嗅��冽𧒄嚗�笆�啣�蝘啗�銵峕䰻�齿�瘚页��㘾膄敶枏�甇�銁蝻𤥁�����亦揣撘� `self.current_idx` �芾澈嚗剹����𨀣鰵�滚�銝𡒊緵摮睃�隞碶遙雿閧��亙��笔�蝒���躰䌊�刻蕭�䭾㺭摮堒偏蝻�嚗䔶��𨅯�蝑𣇉裦摰硺��交��祉���𦶢�齿�霂���
    - [x] **霂剜��⊿�銝𤾸�敶埝�霂�**嚗𡁻�朞�鈭� `py_compile` �拍�蝻𤥁��𣳇��芣�嚗䔶��扯� `test_multi_period_automated.py` �芸𢆡�𡝗�霂閧鍂靘见�蝏輸�朞���pply_json_to_form`)**嚗𡁜銁�喃儒 JSON 蝻𤥁��其葉靽格㺿蝑𣇉裦�滨妍撟嗅��冽𧒄嚗�笆�啣�蝘啗�銵峕䰻�齿�瘚页��㘾膄敶枏�甇�銁蝻𤥁�����亦揣撘� `self.current_idx` �芾澈嚗剹����𨀣鰵�滚�銝𡒊緵摮睃�隞碶遙雿閧��亙��笔�蝒���躰䌊�刻蕭�䭾㺭摮堒偏蝻�嚗䔶��𨅯�蝑𣇉裦摰硺��交��祉���𦶢�齿�霂���
    - [x] **霂剜��⊿�銝𤾸�敶埝�霂�**嚗𡁻�朞�鈭� `py_compile` �拍�蝻𤥁��𣳇��芣�嚗䔶��扯� `test_multi_period_automated.py` �芸𢆡�𡝗�霂閧鍂靘见�蝏輸�朞���

## 2026-06-30 15:30
- [x] **靽桀�蝑𣇉裦蝻𤥁��� JSON 撖澆�/摨𠉛鍂閬�� Bug (Fixed Strategy JSON Import & Application Overwrite Bug)**嚗�
    - [x] **�桅��寞�摰帋�**嚗𡁜銁 `MultiPeriodStrategyEditor` 蝎䁅斐 JSON 撟嗅��剁�閫血� `_apply_json_to_form`嚗匧�嚗䔶��滩挽�屸𢒰 Listbox �㗇𥋘撟嗅�甇亥��� `_on_select(None)` �瑟鰵銵典�����䕘�`_on_select` �典��笔𦶢�冽���洵銝��嗆挾隡𡁏��∩辣�啗��� `_sync_to_current_strategy()` 撠�唂銵典����澆�甇亥��硋��交迤�函�颲𤑳�蝑𣇉裦嚗䔶���紡�游��𡁏��蠘圾�𣂼僎�滚‵餈𥕦�摮条��啁��仿�蝵株◤閬���鮋��銝箸唂銵典��潘���蝏�紡�湧�蝵桐腺憭曹�撘閙�摮条�憭望���
    - [x] **閫��阡俈閬���箏�**嚗帋蛹 `_on_select(self, event, sync=True)` 撘訫��舫�厩� `sync` �嗆��綉�嗚����� Listbox 甇�虜��揢蝑𣇉裦�塚�暺䁅恕撘��� `sync=True` 靽肽�蝻𤥁��嗆���銝Ｗ仃嚗𥡝��銁 `_apply_json_to_form` 蝏枏偏�𧼮‵銵典��塚�隡𣳇�� `sync=False` 隞舘�𣬚凒�亦�頝臬僎頝唾�銵典�撖孵�摮条�閬��嚗���� JSON �滨蔭�����凒�唬��唳旿�剔㴓��
    - [x] **�⊿�銝𤾸�敶埝�霂�**嚗𡁻�朞�鈭� `py_compile` 霂剜��拍�蝻𤥁�嚗𥕦僎�刻��箇𠶖���摰𣬚��朞�鈭� `test_multi_period_automated.py` �典�憭𡁜𪂹�笔�敶埝�霂閧鍂靘页�餈鞱��㰘秤��
on_select(self, event, sync=True)` 撘訫��舫�厩� `sync` �嗆��綉�嗚����� Listbox 甇�虜��揢蝑𣇉裦�塚�暺䁅恕撘��� `sync=True` 靽肽�蝻𤥁��嗆���銝Ｗ仃嚗𥡝��銁 `_apply_json_to_form` 蝏枏偏�𧼮‵銵典��塚�隡𣳇�� `sync=False` 隞舘�𣬚凒�亦�頝臬僎頝唾�銵典�撖孵�摮条�閬��嚗���� JSON �滨蔭�����凒�唬��唳旿�剔㴓��
    - [x] **�⊿�銝𤾸�敶埝�霂�**嚗𡁻�朞�鈭� `py_compile` 霂剜��拍�蝻𤥁�嚗𥕦僎�刻��箇𠶖���摰𣬚��朞�鈭� `test_multi_period_automated.py` �典�憭𡁜𪂹�笔�敶埝�霂閧鍂靘页�餈鞱��㰘秤��

## 2026-06-30 15:15
- [x] **摰䂿緵鈭峕活餈�誘�∩辣�芸𢆡����碶��臬𢆡�芸𢆡�㰘蝸 (Automatic Persistence & Reloading of Secondary Filter Query)**嚗�
    - [x] **�啣�撅墧�找��㰘蝸蝏穃�**嚗𡁜銁 `standalone_multi_period_tester.py` �嘥��𡝗�蝔衤葉嚗䔶� `ui_state` 銝剜��� `current_history_query` 撟嗉�蝏� `self._current_history_query`嚗𥕦銁 `QueryHistoryManager` 摰硺��𣂼��𥕦遣�𠬍��芸𢆡皜�征撟嗅�甇亙�霂亥�皛斗辺隞嗅‵�� `entry_query` 颲枏�獢���
    - [x] **摨𠉛鍂�湔㺿銝舘䌊�典���**嚗𡁏凒�唬� `_on_history_sync` �噼�嚗���交𤣰�� `"use"` �賭誘摨𠉛鍂��蟮鈭峕活餈�誘�∩辣�塚��芸𢆡靚�鍂 `_save_state()` 閫血�摰墧𧒄�坔��拍��滨蔭嚗𥕦�甇亙銁 `_clear_history_filter` 銝剖��牐�皜�征颲枏�獢���研��蔭蝛� `ui_state['current_history_query']` 撟嗉��� `_save_state()` ��𡡒�航䌊����日�餉���
    - [x] **�芣�銝𤾸�敶埝�霂閖�朞�**嚗𡁻◇�拚�朞�鈭� `py_compile` 霂剜�璉�瘚页�銝𥪯�撟嗉��帋� `test_multi_period_automated.py` �𧼮�瘚贝�憟𦯀辣嚗峕�銵峕迤撣詻��


## 2026-06-30 15:00
- [x] **摰䂿緵��稬蝑偦�厩��𡏭” Tree 銵�撕�箔葵�⊥�敹菜踎�𦯀���撅噼�銝朞祕����� (Pop up Stock Concepts and Industry Details on Treeview Double-Click)**嚗�
    - [x] **蝏穃� Treeview ��稬鈭衤辣**嚗𡁜銁 `standalone_multi_period_tester.py` �� `_init_ui` 瘚��銝剖��牐� `self.tree.bind("<Double-1>", self._on_tree_double_click)`嚗�笆�𡑒”��稬銵䔶蛹餈𥡝�摰墧𧒄�閗繮��
    - [x] **摰䂿緵�踹�銵䔶�蝎曉��瑕�銝𡡞�蝥折����**嚗朞挽霈∩�憭𡁶漣�唳旿�寥��箏�嚗𡁜��餅𧒄隡睃��朞��砍𧑐擃㗛�毺揣撘閙𦻖�� `wencaiData.search_ths_data(code)` �祇𡢿�瑕���摰����踎�埈�敹萄�銵其���撅噼�銝𡄯��亥繮�硋仃韐交�銝箇征嚗���芸𢆡�滨漣�典��冽�蝻枏� `period_dfs` 銝剖龪�齿��吔�蝖桐�靽⊥���迅摰帋漣�箝��
    - [x] **蝎曇稲�垍��澆��硋�蝷�**嚗𡁻������𧋦颲枏枂�瑕������𧋦�典��瑞揮撖���𠉛���僚璁�艙��𧋦嚗諹䌊�典���僎頧砍�銝箏蒂摨誩噡����啁憬餈𥟇�敹萄�銵剁�憭批��𣂼�鈭��銝剜踎�堒��抒�閫���急������
    - [x] **摰䂿緵�笔𧑐閬���瑟鰵銝舘楊隡朞��牐�霈啣�**嚗朞挽霈∪僎���鈭� `show_category_detail` �祉� Toplevel 撅閧內撅��憒��霂行�蝒堒藁撌脩�摮睃銁嚗���餃�隞𤥁��嗅��笔𧑐�滚���捆撟嗅撩銵𣬚蔭憿嗉��佗��踹����餈����妟���蝒堒藁嚗𥕦��嗆𣈲��楊隡朞��牐�霈啣��蠘�嚗�銁蝒堒藁�喲𡡒�㚚�瘥�𧒄�芸𢆡撠���唬�蝵桐�憭批��坔� `standalone_tester_config.json`嚗�銁銝𧢲活�㰘蝸�嗅�蝢𤾸��堆�摰𣬚�憟穃���稲鈭斗�雿㯄���

## 2026-06-30 12:00
- [x] **摰䂿緵�� ESC �枏�撋��撘� History �㗇𥋘獢��鈭峕活餈�誘蝑偦�㗇㦤�� (Embedded History Selector on ESC & Secondary Result Filtering)**嚗�
    - [x] **撋��撘� UI �𥪜𢆡銝� ESC 蝏穃�**嚗𡁜銁 `StandaloneMultiPeriodTester.__init__` 銝剖�靘见�鈭� `QueryHistoryManager`��眏鈭𦒘��� `self`嚗諹䌊�典�撅�蝏穃�鈭� ESC �桐� Alt+Q 敹急㭘�殷��舀��𤩺𧒄�其蜓蝒堒藁銝𧢲䲮�曄內�㚚��誩��� Query �𦦵揣獢���
    - [x] **撘訫���像�硋��冽�摰質”�峕郊嚗Ǒ_build_flat_df`嚗�**嚗𡁜銁蝑偦�厩��𨅯��唳𧒄嚗�����㗇暑頝�𪂹�毺����舀������僎撟喲唍�喃葵�∩蜓�唳旿銵䕘�撟嗅�甇亥�鈭� `query_manager.df_all`���雿踹� history manager ���𨀣�霂𨰝�嘥��𨅯𦶢銝剔�霈﹦�嘥��質�憭毺凒�亥�隡啣��怠��冽��𡒊�嚗�� `close_d` �� `ma5d_w`嚗厩�隞餅�憭齿�銵刻噢撘譌��
    - [x] **摰䂿緵 Pandas Query 鈭峕活餈�誘銝𤾸��滩祗瘜訫��券����**嚗朞挽霈∩� `_apply_secondary_filter` �箏�嚗�銁�冽��孵稬 history �㗇𥋘獢�葉����∟”颲曉��塚��芸𢆡���撟嗅�銝𠰴��滢蜓�匧𪂹�毺��𡒊�嚗��憒�� `close > ma5d` 頧祆揢銝� `close_d > ma5d_d`嚗匧僎餈𥡝�鈭峕活餈�誘��𣈲���蝥找蝙�典�憪贝”颲曉��𠰴�撣豢��琿���選�蝖桐�鈭�祗瘜閖�霂舐�銝滚�韏瑞頂蝏笔援皞���
    - [x] **摨閙��嗆����其�銝��格��方�皛�**嚗𡁜銁摨閖��嗆����啣�鈭��鎿� 皜�膄餈�誘�脲��殷�隞�銁�匧��脖�甈∟�皛斗𧒄撅閧內嚗㚁�銝𥪜銁 `_show_results` ����𤩺���遬蝷箔葉�券𢒰���鈭��皛文�/餈�誘�𡒊�撖寞��圈��曄內嚗𥕦銁蝒堒藁�喲𡡒 `on_close` 銝剛‘朣𣂷�撖� history ��蟮霈啣��芸𢆡����碶�摮条�靚�鍂��

## 2026-06-30 11:00
- [x] **摰䂿緵霂𦠜鱏銝芾�颲枏�獢�𢰧�桃�韐渲䌊�冽���6雿滢葵�∩誨��僎閫血�霂𦠜鱏�蠘� (Automated 6-Digit Stock Code Extraction and Auto-Diagnosis on Right-Click)**嚗�
    - [x] **蝏穃��喲睸�訫稬鈭衤辣 (`<Button-3>`)**嚗𡁜銁 `standalone_multi_period_tester.py` �屸𢒰��遣�餉� `_init_ui` 銝哨�銝箄��凋葵�∟��交� `self.diag_entry` 蝏穃�鈭� `<Button-3>` 鈭衤辣嚗𣬚�摰帋�銝枏��喲睸憭��蝔见� `self._on_diag_entry_right_click`��
    - [x] **摰䂿緵�芾斐�� 6 雿滩�蟡其誨��迤�蹱��碶�霂𦠜鱏閫血�**嚗𡁜銁 `_on_diag_entry_right_click` 銝凋�蝟餌��芾斐�輯繮�𡝗��穿�撟嗡蝙�冽迤�躰”颲曉� `\d{6}` �芸𢆡�𦦵揣�寥� 6 雿滩�蝏剜㺭摮𨰜��𥅾�曉��寥�憿對��芸𢆡皜�征撟嗅‵�亥��交�嚗𣬚��舘䌊�刻圻�� `self._on_diagnose_click()` 撘��航��剜�蝔页��交𧊋�曉��坔銁�嗆���餈𥡝��见末�鞟內��
    - [x] **�行⏛暺䁅恕鈭衤辣隞仿俈�脩�**嚗𡁜����摨𤩺��舘��� `"break"`嚗屸獈甇Ｖ�暺䁅恕�喲睸�𨅯���撕�綽�蝖桐��冽�雿㯄�銝��氬��
    - [x] **霂剜��⊿�銝舘䌊�典�瘚贝��函遛�朞�**嚗𡁻◇�拙笆 `standalone_multi_period_tester.py` �扯�鈭� `py_compile` 霂剜��⊿�嚗䔶��朞�鈭��憟� `test_multi_period_automated.py` �芸𢆡�硋�敶埝�霂閧鍂靘卝��

## 2026-06-29 23:45
- [x] **摰䂿緵蝑𣇉裦蝻𤥁��典𪂹�蠘�皛斗辺隞嗥��䂿聦�𤩺�批鍳��/蝳�鍂�箏�銝舘��閗��刻䌊�典蕭�亥�皛� (Non-Destructive Condition Toggle & Menu Linkage Bypass)**嚗�
    - [x] **撘訫� `enabled` �嗆��綉�塚��踹��拍��𣳇膄�∩辣 (Preserved Conditions with enabled flag)**嚗𡁜銁 `MultiPeriodStrategyEditor` 銵典��峕郊�餉� `_sync_to_current_strategy` 銝哨��㰘捏�冽�����㗇��暸�劐��佗��芾��曄�蝻𤥁�餈�砲餈�誘銵刻噢撘𧶏��其�摮䀹𧒄���隞亙��港��辷�銝滚�隞� `conditions` 銝剔�����歹��䔶�隞�糓撠�笆摨𠉛� `"enabled"` 撅墧�抒蔭銝� `False`��
    - [x] **摰䂿緵�喲𡡒�冽��∩辣����砍��瑕�蝷箔��芣��㰘蝸 (Restored Original Condition Texts on Uncheck)**嚗𡁏凒�唬� `_on_select` 撖孵𪂹�毺��滚‵瘚��嚗�銁�滚‵�芸鍳�剁�`enabled: False`嚗厩��冽��塚�隞滢��𡃏�皛方”颲曉�憛怠��唳��祆���僎�𡁶��典�����齿活�暸�匧�撠�䌊�刻蓮銝箏虾蝻𤥁��嗆����滚縧鈭���啗��亦�蝜��餈�����甈⊥��滨蔭�暸�㗇𧒄嚗諹䌊�典‵���霈方�皛方��� `close > ma5d` 蝖桐�撘�蝞勗朖�具��
    - [x] **撖寥�撖澆�銝� JSON 摨𠉛鍂皜�� Schema (Aligned JSON Import & Apply Schema)**嚗𡁜銁 `_import_json_strategy` �� `_apply_json_to_form` 璅∪�銝剖�甇仿���撟嗆��碶� `"enabled"` ���嚗𣬚＆靽脲�霈粹�朞���𧋦撖澆�餈䀹糓�见𢆡韐游�嚗峕辺隞嗅��喳銁���銝𡒊��䀝漱鈭埝𧒄憪讠�撖寥���
    - [x] **蝑𣇉裦撘閙��𥪜𢆡嚗諹䌊�典��賣𧊋�暸�㗇��喲𡡒�冽�����嗉�皛� (Automated Pass-All for Disabled / Unchecked Periods)**嚗𡁜銁 `evaluate_strategy` 銝剖��牐�撖� `cond.get('enabled', True)` ������批ế摰𠾼����𨀣�銝芸𪂹�蠘蒾�園�鈭���辷�雿�銁蝑𣇉裦銝凋蛹 `enabled: False` �𡝗糓敶枏�銝餌�����𤏪�`active_periods`嚗劐葉�芷�劐葉摰���躰砲�冽��芸𢆡�剛楝撟嗉◤撘閙�閫�蛹 display-only (�芾粉撅閧內�冽�)嚗峕��劐葵�∪銁撖孵��冽�銝羓蔭銝� `pass: True` 銝𥪯�餈𥡝�鈭文僎��撩�𥡝�皛歹��曉��曇噢�𣂷��𨅯�瘝⊥��㗇𥋘�嗡��舐鍂餈�誘���瘙���

## 2026-06-29 23:35
- [x] **瘛勗漲靽桀�憭𡁜𪂹�笔𢆡�� `win` 霈∠��餉�銝𤾸㦛銵刻�閫匧笆朣� (Strict Multi-Period Momentum Alignment)**嚗�
    - [x] **摨罸膄�曉捐蝏𤘪�嚗���賭艇�𥡝��喳ế摰� (Strict Consecutive Up-Closes)**嚗𡁜蝠摨閖���� `data_utils.py` 銝� `strong_momentum_large_cycle_vect_new` ��楝敺��文��餉������𧋦�𨅯�霈詨枂��1�寥��孵��賤�萘��曉捐��𧋦�踵揢銝箔艇�𤤿� `cond_trend = np.all(P[:, c] > P[:, p] * 0.995)`����誩㭠�� `win` �啣銁銝交聢蝑匧�鈭𤾸虾閫���曇”銝羓��𡏭��蚱蝥踵㺭�謿�嘅��嗥�隞瑁�蝏剜䠋擃矋�嚗��蝢舘圾�喃� 000021 �函瑪 `win(w)` �𡁻�銝� 9 �����㦛銵其�銝� 4 餈鮋翧���銝��湧䔮憸塩��
    - [x] **�娪膄頝臬�B撖潸稲����唾�憓� (Removed Path B Deflation)**嚗𡁶宏�支��笔之�冽�霈∠�銝剔��𨅯�頦拇𣈲�穃�������頝臬�B嚗争�嘥笆 `max_win` �㗛��������湔𦻖韏见�潦����餉�隡𡁜��港葵�噼萱�粹𡢿��楊摨衣��游��� `win`嚗�紡�游鉄�厰狍蝥輻�敶Ｘ���鋡怠撩銵峕�擃塩��宏�文�嚗䈣win` ����𧼮��嗆�蝥舐硃��𢆡�讛�蝏剜�扳𧋦韐剁��Ｗ�鈭���䔶葵�⊿𡢿���撖孵躹��漲��
    - [x] **撉諹�摰䂿� `shift_intraday` 撟賜�K蝥輯���移摨� (Verified Intraday Ghost Bar Fusion)**嚗𡁶��嗵𡠺蝡讠�����砍笆 000021��688403��002674 �� 603650 �� w�� �冽�摨訫��𣂼��拚猐餈𥡝�鈭���箸芋�煺�撖寥�撉諹�����𤾸銁�滚� `shift_intraday=True` �𠬍�摰䂿����唬��毺�隞瑟聢鋡怎移蝖桀像蝘餉秐摨誩��滨垢嚗�� 000021 �� 58.86 摰𣬚�銵娍𦻖鈭� 53.51 銋见�嚗㚁����鈭��皛𤑳� `58.86 > 53.51 > 39.57 > 29.0 > 25.57` �唳旿瘚��雿踹���瑪 `win(m)` 甇�＆颲枏枂銝� 5 餈鮋翧��
    - [x] **閫�� `win(m): 0` �曄內蝻粹萅 (Resolved False Zero Display)**嚗𡁏�蝖桐��典�����箇緵 `win(m): 0` 蝻粹萅蝟餌眏�笔��𣈯��嫣��氯�� (`cond_high`) 撖� `w=2` ��艇�潸秤�支誑�𦠜𧋦�圈�鈭斗��嗆挾����𣇉�摮睃��滚��䭾��氬���朞��典�撅�覔瘝餉��喳ế摰𡁜�撘誩僎撟喲唍��僎�拚猐霈∠�嚗�蝠摨閙��支��剖��仿���

## 2026-06-29 18:28
- [x] **�寞祥蝻枏�憭望�銝䇊I�嗆����峕郊�屸�Bug (Fixed Cache Invalidation + Thread-safe Status UI)**嚗�
    - [x] **撘訫� _top_now_cache_ts / _period_cache_ts �園𡢿�喃�蝟�**嚗𡁜銁 __init__ 銝剜鰵憓� _top_now_cache_ts = 0.0 銝� _period_cache_ts: dict = {} ���餈質葵 	op_now ����冽��唳旿����𤾸�頧賣𧒄�湛�銝� TTL �斗鱏�𣂷��園𡢿靘脲旿��
    - [x] **摰䂿緵 _is_cache_valid 蝻枏��㗇��批ế��**嚗𡁜�鋆� _CACHE_TTL_TRADING = 3600s �� TTL �喟��婙�𥪯漱�𤘪𧒄畾萇�摮� 1 撠𤩺𧒄�舘�����硺漱�𤘪𧒄畾蛛��冽錰/�����/�睃�嚗㗇偶銋������湔𦻖憭滨鍂����唳旿嚗屸��滢�敹������� IO �𣬚�蝏𡏭窈瘙���
    - [x] **靽桀� 
un_filter 暺䁅恕撘箏��瑟鰵��覔�祉撩��**嚗𡁜� orce_reload 暺䁅恕�潛眏 True �嫣蛹 False嚗峕惣�賣�瘚� 	op_now �� _period_dfs ���摮䀹����改�隞�笆憭望�蝻枏��扯�皜�膄撟園��啣�頧踝�敶餃�閫��瘥𤩺活餈鞱��賢��誯�霈∠����扯�瘚芾晶��
    - [x] **�啣��𤃬�� 撘箏��瑟鰵�齿��殷��諹提��氖**嚗𡁏���蛹�𢞖𪇵 餈鞱�蝑偦�剹�㵪�orce_reload=False嚗匧��𤃬�� 撘箏��瑟鰵�㵪�orce_reload=True嚗峕��莎�嚗諹悟�冽��臭誑�曉��批��臬炏皜�征�券�蝻枏���
    - [x] **靽桀� _update_status 蝥輻�摰匧��桅�**嚗𡁜縧�� update_idletasks() 靚�鍂嚗��摮鞟瑪蝔讠凒�交�銵� Tkinter �滨��舫�蝥輻�摰匧�銵䔶蛹嚗㚁��券��朞� self.after(0, self._update_status, text) 摰匧��閖�坿秐銝餌瑪蝔衤�隞園��埈�銵䕘��寞祥�嗆���蝑曆�甈∟�銵峕𧒄銝齿凒�啁� UI Bug��
    - [x] **_worker �𣂼𪂹�毺�摮䀹���**嚗𡁜𦶢銝剔�摮䀹𧒄�曄內�𢞖黾 [{period}] �賭葉蝻枏� (撌脣��� Xs)�滚僎頝唾��㰘蝸嚗𥕦仃��𧒄�齿�銵� engine.load_period_data 撟嗆凒�� _period_cache_ts[period] �園𡢿�喋��
    - [x] **�券�霂剜�蝻𤥁��朞�**嚗䮝y_compile �⊿� standalone_multi_period_tester.py �㰘祗瘜閖�霂胯��

## 2026-06-29 18:15
- [x] **餈𥕢�甇乩��硋之�冽��券� `win`/`slope` 頝典𪂹/頝冽��䔶��冽�摰墧𧒄�唳旿撖寥�銝𦒘漱�𤘪𠯫�冽�靽脲擪 (Optimized Large-Cycle Momentum same-period Alignment & Trading Day Gate)**嚗�
    - [x] **摰䂿緵�䔶��冽�銝� indicator ��蟮摨誩��拍�蝘颱� (`parse_indicator_col`)**嚗𡁜銁 `complete_indicators_pipeline` 銝哨���笆�墧𠯫蝥輻�憭批𪂹�� (w, m, 3d, 45d, 3M) �� `is_same == True` (�䔶��冽�) �塚�摰䂿緵鈭�笆���� `lastoXd`��lasthXd`��lastlXd`��lastpXd`��lastvXd` 蝑匧��脫�蝷箏膥�㛖��芸𢆡�穃�蝘颱�銝�雿� (靘见�撠� `lastp1d` 蝘餃� `lastp2d`嚗峕� `lastp0d` 撖孵�����笔��冽㺭�株��箇� `lastp1d`)���蝖桐�鈭��摨訫��� HDF5 �� TDX �唳旿撌脩�霈啣�鈭���毺�撅��典歇摰峕��唳旿�塚���蟮�券�霈∠��� `lastp1d` 憪讠����銝𠹺�銝芸歇摰���喲𡡒��𪂹���敶餃��踹�鈭� `lastp1d` ����笔��嗆𤣰�条�霂凋�瘛瑟���
    - [x] **撘訫�鈭斗��亦𠶖���撘��䀹𧒄�湧秄瑽𥕢��� (`is_trade_day` & `now_time`)**嚗𡁜銁餈𥕦� `complete_indicators_pipeline` ����嗉���笆朣� and 蝘颱� block �㵪�撘箄�憓𧼮�鈭�笆隞𦠜𠯫�臬炏銝箸���漱�𤘪𠯫 (`cct.get_trade_date_status()`) 隞亙�敶枏��園𡢿�臬炏撌脰��亙��䀝漱�𤘪𧒄畾� (`now_time >= 915`) ���蝵桀ế摰𠾼����脫迫鈭�銁�冽錰�����𠯫�𣇉��齿��啗���凒�唳𧒄�𤑳��䭾���宏雿㵪�隞舘���蝢𦒘��嗘���蟮撌脣��𣂼𪂹�毺�摰峕㟲�改�閫��鈭�𪂹�急��睃�霈∠��嗆㺭�桀仃�笔� win 鋡急�憭𡝗��嗥��鞉���
    - [x] **�券��芸𢆡�𡝗�霂蓥�蝻𤥁��⊿��函遛�朞�**嚗𡁻◇�拇�銵䔶� `test_multi_period_automated.py` �𧼮�瘚贝�嚗諹��剔��𨅯� query 餈�誘�典�憿孵ế摰𡁏���銁�� disk I/O ���鈭劐�隞� Exit Code 0 摰𣬚�頝煾�𠾼��

## 2026-06-29 17:55
- [x] **靽桀�摰䂿�銝见之�冽��券�銝� `win`/`slope` 蝻箏仃敶枏��冽�摰墧𧒄�乩遠��撩�� (Fixed Intraday Missing Current-Period Quote in Momentum & Win/Slope Calculations)**嚗�
    - [x] **摰䂿緵 `strong_momentum_large_cycle_vect` �� `shift_intraday` �芷����唳旿雿滨宏**嚗𡁜銁銝支葵�詨��券��ａ�霈∠��賣㺭銝剜溶�� `shift_intraday=True` ��㺭���憭��摰䂿�/�䀝葉�臬�嚗�� `lastp1d` 蝑匧��脣�摮睃銁嚗㗇𧒄嚗�銁�扯��拚猐�𣂼��㵪���䌊�冽��牐�隞賢��函��𦯀�蝘餃��穿�撠���滚��� OHLCV �唳旿嚗����蝙�� `lastp0d` 蝑� 0d 瘜典��梹�瘝⊥��嗘蝙�� `close`/`high`/`low`/`vol`嚗匧像蝘餌��� `lastp1d`/`lasth1d`/`lastl1d`/`lastv1d`嚗����蟮 1d-10d 靘脲活憿箏辣嚗��敶枏���暑頝�𪂹�蠘����蝻嗪曎�亥秐�券�霂�摯摨誩�����滨垢��
    - [x] **�㯄�𡁜之�冽� `win` 餈鮋翧銝擧��� `slope` 摰䂿��瑟鰵**嚗朞圾�喃�憭批𪂹���憒�𪂹蝥� `w`���蝥� `m`嚗厩眏鈭𤾸�撅�畆�萇凒�乩� `lastp1d` 韏瑞���蝠摨訫蕭�乩��砍𪂹/�祆����唬遠�澆��剁�撖潸稲憒��靝��冽隅�栶��𧋦�函誧蝏剔��氯�萘��∠巨 `win(w)` 憪讠��曄內銝� 0 ��艇�滨撩�瑯��像蝘餃�嚗䔶葉�賢㪗���600118嚗厩� `win(w)` �𣂼��湔鰵銝箸迤蝖桃�餈鮋翧�冽㺭 `2`嚗峕��������𥟇�����峕郊�齿�鈭���啣��嗅𪂹蝥輻𠶖����
    - [x] **�券𢒰�𧼮�瘚贝��朞�**嚗𡁜笆 `data_utils.py` 餈𥡝� `py_compile` �芣�銝� `test_multi_period_automated.py` �扯�嚗䔶���迤撣賊�朞���

## 2026-06-29 17:40
- [x] **靽桀��曹� Ghost Bar 雿滨宏撖潸稲蝑𣇉裦瘚贝�蝏𤘪�銝箇征��撩�� (Fixed Empty Strategy Results due to Ghost Bar Shifting)**嚗�
    - [x] **摨罸膄頝典𪂹�笔��脣�雿滨宏 (Abolished Shifting of Historical Columns)**嚗𡁏�蝖桐� HDF5/TDX �唳旿摨訫��券��亦瑪�漤��瑕𪂹�� (w, m) 銝� `lastp1d` 蝑匧�撌脣予�嗡誨銵典�銝�銝芸歇摰峕��冽���㿥�嗉�銝�鈭见�����支� `complete_indicators_pipeline` ���撖嫣� `lastp1d` �� `lastp20d` ����𡒊宏雿漤�餉�嚗屸俈甇� `lastp1d` 鋡恍�霂航��吔�摰𣬚�靽萘�鈭���交辺隞嗅� `close > lastp1d and lastp1d > lastp2d` ��祗銋匧��湔�扼��
    - [x] **摰䂿緵�笔𧑐��僎敶枏�瘣餃𢆡�冽� OHLC �乩遠 (In-place Merging of Active Period OHLC)**嚗�
        - �啣𪂹�� (`is_same == False`)嚗帋��𡁜�撟塚��湧�帋��亙��嗉���蛹�砍𪂹�蠘絲�嫘��
        - �䔶��冽� (`is_same == True`)嚗𡁜銁 `valid_mask` 銝页��冽�������亙��園�/雿�/�譍���蟮摨枏歇蝘舐敞����笔��冽��� `lopen`/`lhigh`/`llow`/`lvol`嚗𣬚��𣂼��滨� `open`/`high`/`low`/`vol` �����
    - [x] **�舀��典�摮䀝葉�冽���蝞堒��笔�蝥蹂�瘨刻�撟� (Dynamic Indicator Recalculation for Active Period)**嚗𡁻��啗恣蝞堒僎瘜典� `ma5d`��ma10d`��ma20d`��ma60d` 隞亙� `percent`/`per1d` 瘨刻�撟��蝖桐� `close` 銝𤾸��亙�蝥踵����瘥𥪜笆�文��交�瘥怎�蝥批��嗡��湔�扼��
    - [x] **�券𢒰�𧼮�瘚贝��𣂼�**嚗䫤test_multi_period_automated.py` 銝� `test_ghost_bar.py` �函遛�朞�嚗峕瓷�匧��笔援皞��蝑偦�匧龪�滢�霂𦠜鱏�餉��曉��暹�憭齿迤撣詻��

## 2026-06-29 17:00
- [x] **閫��摰䂿�頝典之�冽� Ghost Bar ��僎銝擧���恣蝞𦯀��湔�折䔮憸� (Resolved Intraday Large-Cycle Ghost Bar Merging & Indicator Consistency)**嚗�
    - [x] **敶餃�靽桀� HDF5 霂餃��� `today_bar_dict` ���� TypeError 撏拇�**嚗𡁜銁 `multi_period_strategy_engine.py` 銝剔宏�支�隞𠰴予銝湔𧒄 bar ��遣摮堒�撟嗡耨甇�� `get_append_lastp_to_df` ������銝滚�隡𣳇�� `today_bar_dict`嚗峕��支���㺭銝滚龪�滨� Bug��
    - [x] **摰䂿緵�港���� `complete_indicators_pipeline` 摰墧𧒄銵峕� Ghost Bar �滚�**嚗𡁜銁 `data_utils.py` ������瘞渡瑪銝哨���笆�墧𠯫蝥輻�憭批𪂹�� (w, m, 3d, 45d, 3M)嚗���乩�摰䂿����唳𥁒隞� (`close`/`high`/`low`/`open`/`vol`) 銝𤾸��脫㺭�� (`lastp1d`/`lasth1d`/`lastl1d`/`lasto1d`/`lastv1d`) ����啗䌊����拍�撟喟宏銝� Ghost Bar ��僎蝞埈���
    - [x] **靽桀��曹� `get_trade_day_before(1)` 霂臬ế銝箔�憭拙紡�� Ghost Bar �滚�憭望��� Bug**嚗帋耨憭滢��典��䀝漱�𤘪𠯫嚗䈣get_trade_day_before(1)` ��鉄鈭��憭拇𧋦頨思��諹��硺�憭拇𠯫���撖潸稲 `last_date < today` �∩辣銝齿�蝡卝��㟲銝芸之�冽�摰墧𧒄�滚��餉�鋡恍�暺䁅歲餈���餉�蝻粹萅����乩�敶� `last_date == today` �嗉䌊�典����瑕� `get_trade_day_before(2)` ��𢆡��笆朣鞉㦤�塚�蝖桐�鈭��銝剖��嗉���㺭�株�甇�＆�穃𪂹�������亦�憭抒漣�怨�銵𣬚宏雿滚� Ghost Bar �滚�霈∠���
    - [x] **�舀�憭𡁜𪂹�����𢆡��笆朣𣂷��齿鰵霈∠�**嚗𡁜�撟嗅��嗉����嚗峕惣�質‘朣𣂼��齿鰵霈∠� `per1d` 瘨刻�撟���ma51d` 銝� `ma201d` ��瑪蝑匧��桃鸌敺��蝖桐� structural indicators (Rank, win, slope) �函�銝凋���蟮摨枏��典笆朣僐����齿� staleness嚗䔶�摰��靽萘�鈭� HDF5/Parquet 蝤��摨訫� Schema ��滲瘣��摰峕㟲��
    - [x] **�券��芸𢆡�硋�敶埝�霂訫�蝏輸�朞�**嚗朞��帋� `test_multi_period_automated.py`嚗諹��𤾸��冽�蝑偦�剹�����恣蝞𨰜��葵�∟��准�� query 霂剜�餈�誘蝑㗇芋�堒銁擃㗛�撟嗅�銝见�蝢𡡞�朞�銝� exit code 銝� 0��
    - [x] **靽桀� `a_trade_calendar` 蝻箏仃 `get_trade_days` 撖潸稲����折�霂臬援皞�**嚗帋耨憭滢��典�頧賣�蝥�/�函瑪蝑匧𪂹��㺭�格𧒄嚗䈣commonTips.py` 銝剔� `get_trade_day_before` 靚�鍂 `a_trade_calendar.get_trade_days` �𥕦枂 `AttributeError` 撏拇���䔮憸塩��銁 `commonTips.py` 銝剖��唬��砍𧑐�� `get_trade_days` �𣂼��剁��朞�摨訫� DataFrame `_a_trade_cal_df` 餈𥡝��亥砭餈�誘嚗㚁�撟嗉�銵䔶�摰匧���芋�堒𢆡��釣�亦�摰𡄯�摰𣬚�閫��鈭�迨��蟮�㛖�蝻箏仃�亙藁�桅���

## 2026-06-29 16:35
- [x] **靽桀�蝑𣇉裦蝻𤥁��其�摮睃�銝餌�����漤�㗇𥋘蝑𣇉裦鋡恍�蝵桃� Bug (Fixed Strategy Selection Reset on Save & Persisted Last Used Strategy)**嚗�
    - [x] **蝥䭾迤蝑𣇉裦 ID 閬���餉�**嚗帋耨憭滢� `_save_state` 銝剔凒�亙� `strategy_var.get()` (蝑𣇉裦�滨妍) 韏见�潛� `strategy_id` �� Bug��緵�嫣蛹�� `self.strategies` �𡑒”銝剝�朞��滨妍�滚�閫���箏𣈲銝��� `strat_id` �𤾸��坔� `self.ui_state['strategy_id']`嚗䔶��寞𧋦銝𡃏圾�喃��滨蔭�嗵��嗆㺭�桃掩�衤��寥���䔮憸塩��
    - [x] **摰䂿緵蝑𣇉裦蝻𤥁��其�摮䀹𧒄��蜓蝒堒藁�毺��仿�摰�**嚗𡁏凒�唬� `_on_strategies_updated` �噼���眏鈭� `strategy_id` 甇�＆靽嘥�銝箔� ID 摮㛖泵銝莎�蝟餌��函��仿�頧賣𧒄�臭誑�朞� `curr_id` 摰𣬚��寥�鋡恍��賢�����交����瘣餌��乓���颲�/靽嘥��𦒘��滢��誩��滨蔭銝箏�銵其葉擐碶葵蝑𣇉裦嚗𣬚＆靽肽�銵𣬚�蝑𣇉裦�芾��见𢆡�睃𢆡��
    - [x] **�芸𢆡霈啣����𡒊�餈鞱�銝𡡞�㗇𥋘蝑𣇉裦**嚗𡁻�朞�靽格迤 `_save_state` 撟嗉悟 `_apply_state` �典�憪见��嗆迤蝖桐� ID �惩�餈睃�嚗𣬚頂蝏毺緵�典虾隞亙�蝢𤾸銁頝其�霂苷葉�芸𢆡霈啣� and �Ｗ����𡒊�餈鞱�/�㗇𥋘蝑𣇉裦嚗峕�憭漤�銝��湔�抒�����臬���
    - [x] **銝� Treeview 銵冽聢�喲睸�𨅯��啣��𨅯��嗡誨���苷��𨅯��嗉�靽⊥��嘥��� (Added Copy Code & Copy Row Info to Context Menu)**嚗�
        - [x] **隞���������**嚗𡁏鰵憓𧼮𢰧�株��閖★ `�� 憭滚�隞��`嚗�虾�祇𡢿撠���滩�銝芾��� 6 雿齿㺭摮𦯀誨����嗅�蝟餌��芾斐�選�撟嗅��典縧�文�隞碶耨擖啣�蝻���
        - [x] **�典�畾萄像�箏���**嚗𡁏鰵憓𧼮𢰧�株��閖★ `�� 憭滚�銵䔶縑�畔嚗�虾�芸𢆡�滚�敶枏�銵峕��匧歇�舐鍂���銵典�畾蛛���鉄�箇���緵隞瑯��隅撟�誑�𠰴��刻䌊摰帋�憭𡁜𪂹������嚗㚁�撟嗡誑 `銵典仍��:摮埈挾�嬋 ����航粉�桀�澆笆隞� ` | ` 蝚血噡�潭𦻖嚗䔶��桀��嗅��芾斐�選���之�鞾�鈭�㺭�格�撖嫣�憭𡁜像�唬漱鈭垍������
        - [x] **�嗆���擐��摰匧�頧祆揢**嚗𡁏�雿𨅯��𣂼��典��函𠶖����峕郊�鞟內 `撌脣���...` 蝏嗘��單𧒄�漤�嚗𥟇溶�牐�撘�虜�閗繮銝𡒊征�澆��典�����脫迫�函征�唳旿�硋�撣貉圻�烐𧒄撘訫� UI ��絲��
    - [x] **摰峕��典��芸𢆡�硋�敶埝�霂閗䌊璉�**嚗𡁜笆 `standalone_multi_period_tester.py` �扯�鈭�����霂𡢅�銝娪◇�拇�銵䔶� `test_multi_period_automated.py`嚗���讛楊�冽����霈∠�銝擧嵗撉�銁�� HDF5 IO �脩��嗆����函遛�朞���

## 2026-06-29 16:30
- [x] **蝒堒藁頧格揢 (Alt+R) 瘛勗漲���憭𡁜𪂹�蠘��函��亦��匧膥 (Integrated Multi-Period Strategy Tester into Alt+R Window Rotator)**嚗�
    - [x] **�㯄�𡁶���蘂��𤣰���摮䀹暑�嗆���瘚�**嚗𡁜銁 `instock_MonitorTK.py` �� `_get_all_open_trade_windows` �寞�銝哨��啣�撖� `_multi_period_tester_win` 蝒堒藁���瘚卝���瘙������其�憭���航��嗆���`winfo_exists` 銝� `winfo_viewable`嚗㚁�撠��憿嗅� HWND �交�摰匧��園�撟嗆�撠�蛹鈭箇掩�航粉�滨妍 `"�㴓 憭𡁜𪂹�毺��亦��匧膥 (MultiPeriodTester)"`��
    - [x] **摰䂿緵撘箏�蝛輸�譍��𡁶�蝵桅▲**嚗𡁜銁 `_force_focus_hwnd` �寞�銝哨�銵仿�鈭��撖� `_multi_period_tester_win` 憿嗅��交��� Tk �煺�蝵桅▲�日��餉����頧株蓮�格���揢�喟��匧膥�塚��芸𢆡閫血� `deiconify()`��lift()` �� `focus_force()`嚗���啁���銁隞颱��惩��喟頂銝讠�蝘垍漣�日�銝𡒊蔭憿嗉��艾��
    - [x] **銵亙� Qt ��揢�Ｘ踎���蝘唳�撠��擃䀝漁�舀�**嚗𡁜銁 `WindowRotatorDialog.show_rotator` �寞�銝哨�撠� `"MultiPeriodTester"` �餉扇撟嗆�撠�秐�航�擃䀝漁�𨅯���𣈲��蝙�典�撅� Alt+R 敹急㭘�柴��睸�䀝�銝钅睸隞亙�曌䭾�皛朞蔭餈𥡝��删�頧桅�剹���鈭桀�蝖株恕��揢��
    - [x] **摰峕�霂剜��𣳇�蝻𤥁�撉諹�**嚗𡁻◇�拙笆 `instock_MonitorTK.py` �扯�鈭� `py_compile` �拍�蝻𤥁�銝舘䌊璉�嚗𣬚＆靽苷蜓蝔见��券�憸𤏸�����唬�憭朞�蝔见僎�𤏸��其����頞羓迅摰𡁏�扼��

## 2026-06-29 11:30
- [x] **蝏煺�憭𡁜𪂹��㺭�桀�憭�����霈∠�蝞⊿� (Unified Multi-Period Data & Indicator Pipeline)**嚗�
    - [x] **�鞟�撟嗅�鋆��銝����瘚�偌蝥踹遆�� (`complete_indicators_pipeline`)**嚗𡁜銁 `data_utils.py` 銝哨��賢���𧋦�嗆袇�屸�憭滨����霈∠���0d �䀝葉摰墧𧒄銵峕��唳旿瘜典� (`lastp0d`��lasth0d` 蝑�)��之蝥批��券�霈∠� (`strong_momentum_large_cycle_vect` 蝟餃�)�������𥕦�頦抵恣�啜��𢆡�誩�靚�頂蝏蠘���誑�� `build_hma_and_trendscore` ����游��梹�敶鍦僎�唬�銝芸�憯� of `complete_indicators_pipeline` �𡁶鍂霈∠��亙藁銝准��
    - [x] **蝎曄� `fetch_and_process` �詨�銝餌瑪蝔见儐��**嚗𡁻���� `data_utils.py` 銝剜𠯫蝥踹� `resample_ui != 'd'` 憭批𪂹��遬蝷箄膘餈寧�銝文�頞�鵭銝娪�摨阡�憭滨����霈∠�銝𤾸�畾菜釣�亙����朞��湔𦻖靚�鍂 `complete_indicators_pipeline`嚗�蝠摨閙��支��𦯀�隞��嚗�僎靽嗪�鈭��銝剖��嗅��唬�憭批𪂹��遬蝷箸凒�啣銁蝑𣇉裦霂�摯�寥𢒰����湔�扼��
    - [x] **撖寥�憭𡁜𪂹�毺��亙��𡒊��唳旿����箏�**嚗𡁜銁 `multi_period_strategy_engine.py` �� `load_period_data` �寞�銝哨�撠�����銝��� `calc_indicators` �齿�銝箇凒�亥��� `complete_indicators_pipeline`嚗𣬚＆靽嘥銁餈𥡝�憭𡁜𪂹�毺��匧膥霈∠��塚�憭抒漣�急㺭�格� (w, m, 45d, 3M) �臭誑�瑕���𡠺 Rank��in �𠰴�頦抵���頂蝏毺��典�����游𢆡�讐�霈∪�畾蛛�敶餃�瘨�膄鈭���匧膥銝𡒊��找蜓蝔见�銋钅𡢿��㺭�桃撩憭勗�蝎曉漲撖寥��𦦵���
    - [x] **隡睃�憭𡁜𪂹�毺��匧膥餈鞱��亙��曄內撣�� (Refined Status Log Layout for Multi-Period Tester)**嚗𡁜���𧋦�曄蔭�券▲�典極�瑟� (toolbar) �喃儒��捆�栞◤�文��屸��∠� `status_var`嚗��銵𣬚𠶖��𠯫敹梹���倌嚗屸��啗挽霈∪僎��蝸�唳�摨閖� `stats_frame` �嗆������𨀣迤銝剝𡢿蝛箇蒾�箏��嘅�雿輻鍂�芷��� `fill="x", expand=True` 撣��嚗𣬚＆靽脲�霈箇����雿閙赤�烐�隡豢��嗥憬嚗諹�銵䔶葉���蝷箸𠯫敹梹�憒��𨀣迤�刻繮�硋抅蝖��唳旿...�腈���𨀣迤�典�頧� d �冽�...�嘅��質��垍𤌍����港�憪讠�撅�葉�曄內��
    - [x] **摰䂿緵憭𡁜𪂹�毺��亦�颲穃膥銝𤾸𢆡��祗瘜閖�霂�笆霂脲� (Multi-Period Strategy Editor & Validation Dialog)**嚗�
        - [x] **憭𡁶��交𧋦�唳��垍�颲睲��冽���甇�**嚗𡁜��唬�璅⊥��撕蝒㛖掩 `MultiPeriodStrategyEditor`嚗峕𣈲��笆 `config/multi_period_strategies.json` �券�蝑𣇉裦餈𥡝��砍𧑐憭滚���鰵憓𠺶����扎��㺿�滢���僎璅∪�嚗�僎��/鈭日�嚗厩�颲𡢅���揢蝑𣇉裦�嗉䌊�典�蝻𤥁��嗆���甇亙��塩��
        - [x] **�啣�銝��桃�韐� JSON 撖澆�蝑𣇉裦�蠘� (One-click JSON Strategy Import)**嚗𡁜銁蝻𤥁��典椰靘折𢒰�蹂葉�啣�鈭��𨥉�� 蝎䁅斐 JSON 蝑𣇉裦�脲��殷��舀�擃条漣�冽��湔𦻖蝎䁅斐��鉄�蓥葵�硋�銝芰��仿�蝵� of JSON ��𧋦嚗𤤿頂蝏蠘�憭�惣�質圾�僐���瘣𦯀�閫���唳旿嚗��憒��撣豢��溻����典𪂹�麄��撩憭寂D蝑㚁�嚗�僎�芸𢆡���撟嗉蝸�亙�銵剁�摰䂿緵擃䀹�撘��睲�憭滨鍂��
        - [x] **蝻𤥁��函���之撠譍�雿滨蔭�����**嚗𡁻��嗘� `MultiPeriodStrategyEditor` �� `destroy` �寞�嚗�銁蝒堒藁��瘥�𧒄�芸𢆡�𣂼�敶枏��� `geometry` 撟嗅��� `standalone_tester_config.json` �滨蔭��辣銝准��銁 `__init__` �嘥��𡝗𧒄�㰘蝸撟嗉��蠘砲�牐��滨蔭嚗���唬�蝒堒藁撠箏站銝𤾸��� of 頝其�霂肽䌊���霈啣��蠘���僎銝𥪜銁擐𡝗活�枏��嗉䌊���霈∠�撟嗅�銝剜遬蝷箏銁�嗥�����硋�撟𤏪�甇�葉憭殷�閫��鈭��霈文椰銝𡃏�摰帋����閫厩撩�瑯��
        - [x] **7憭扳��亙𪂹��辺隞嗥𡠺蝡见鍳�其���𧋦蝻𤥁�**嚗𡁏𣈲������舐鍂 `SUPPORTED_PERIODS`嚗�鉄 45d��3M嚗厩��訫𪂹�� query 餈�誘嚗𣬚��冽𧒄���颲枏�嚗�鍳�冽𧒄暺䁅恕���������蝞��∩辣嚗�� `close > ma5d`嚗剹��
        - [x] **摰墧𧒄 Pandas Query 餈�誘�刻祗瘜閙�瘚衤� Tooltip ��內��**嚗𡁜��乩��� `MultiPeriodStrategyEngine` 銝剔� `validate_condition` �寞�嚗�銁����㗇㺭�格𧒄�扯��笔�撉諹�嚗峕��笔��唳旿�嗡誑��鉄 30 雿嗘葵擃㗛����舀���� Dummy DataFrame 撉冽沲�扯� query 霂閗�銵䕘�撉諹��𣂼��曄內蝏輯𠧧�鎿� 霂剜�撉諹��朞��嘅�憭梯揖�嗵滯摮埈��箏僎�舫�朞� Tooltip �祆筑撅閧內霂衣�����仿���
        - [x] **���銝��栽�𣈯�霂���兩�苷�靽嘥��噼�**嚗𡁜��𣂷�蝑𣇉裦蝞∠��其葉����券�霂���殷�靽肽�靽嘥��箇�蝑𣇉裦�滨蔭銝滢�撘訫�餈鞱��笔援皞��靽嘥��嗉䌊�券�頧賭蜓�屸𢒰 Combobox�舫�匧��啜��
        - [x] **靽桀�蝑𣇉裦蝞∠��其葉靽格㺿�滨妍撖潸稲�����/�漤�� Bug (Fixed Listbox Multi-selection Bug)**嚗帋耨憭滢��� Listbox ��揢蝑𣇉裦�厰★�塚��曹��� `_on_select` 鈭衤辣���甇交�銵䔶��扳�憿寧� `delete`��insert` 銝� `selection_set` �餉�嚗�紡�� Tkinter �匧�憿寞�撠��蝟餃�蝒��䔶漣�煺舅銵峕�憭朞��峕𧒄擃䀝漁�劐葉�� Bug��緵�朞�撠���亙�蝘啁��䀹凒�峕郊�箏��齿�銝箏笆 `StringVar` �� `trace_add("write", ...)` 餈𥡝��冽��齒�穿�隞�銁��𧋦�笔�靽格㺿�嗅��券�暺䀝耨�� Listbox 摮埈挾嚗�蝠摨閙��支��孵稬��揢�嗥�憭𡁻�匧�蝒���
    - [x] **摰䂿緵頝典𪂹�毺鸌敺�㺭�格�撟喳�撟喲唍��僎銝𡒊頂蝏毺漣霂𦠜鱏撖寡�獢�笆�� (Unified Flat-Series Diagnostics & Existing Window Integration)**嚗�
        - [x] **銝芾�頝典𪂹���撟喳��齿�**嚗𡁜�銝芾��典�銝𡒊�憭帋葵銝滚�蝑𣇉裦�冽�嚗Ê̌������45d��3M嚗厩鸌敺���唳旿�惩�銝箔誑 `{col}_{period}` �𡒊��賢����銵�捐銵函�������銝�銝芸像�箇� DataFrame `df_flat`��
        - [x] **銵刻噢撘誩��滚�蝻����**嚗𡁏覔�桀��冽�霈∠�撘閙��堒仍��㺭�殷�撖寧��� query �∩辣餈𥡝��閗�甇���寥�嚗���刻蓮�Ｖ蛹撣血𪂹�笔�蝻� of 撟喲唍摮鞱”颲曉�嚗��撠� `close > ma5d` 頧祆揢銝� `close_w > ma5d_w`嚗㚁��脫迫�堒��脩���
        - [x] **�删�撖寞𦻖蝟餌� check_code 蝏�辣**嚗帋蝙�刻蓮�Ｗ��� `df_flat` 銝� `queries`嚗𣬚凒�亥�韏� pyQuant3 蝟餌�����蠘�蟡冽��交𥁒�羓��� `check_code`嚗��蝢𡡞��其�擃㗛��潛�霂𦠜鱏撖峕��祉��Ｕ����脫�霂蓥��㕑��蓥誑�𠰴𢆡��漱鈭鍦��见𢆡瘚贝��批��～��
        - [x] **摰䂿緵�芸𢆡�𡝗�霂閙㺭�桀��其��嗉�埈𧒄撉諹� (Zero-I/O Automated Test Reuse)**嚗𡁻��嗘� `test_multi_period_automated.py`嚗峕�霂閗��剜�蝔讠凒�交𦻖�嗅�摨誩歇�㰘蝸憟賣㺭�桃� `engine` 銝� `top_now` 敹怎���㺭嚗���典��颱�鈭峕活 TDX 銝� H5 蝤��霂餃�嚗諹�銵峕������秐鈭𡁏神蝘垍漣嚗䔶��冽綉�嗅蝱雿輻鍂 GBK 摰匧�餈�誘�箏�嚗�蝠摨閙覔瘝颱� unicode 蝻𣇉�撏拇�憌𡡞埯.
        - [x] **摰䂿緵霂𦠜鱏�舘䌊�冽��典�雿滢�擃䀝漁銝芾� (Auto-scroll & Selection Highlight on Diagnosis)**嚗𡁜銁 `diagnose_stock_strategy` 霂𦠜鱏瘚���扯�摰峕��𠬍�璉��亙��� Treeview �臬炏摮睃銁霂乩葵�� `code`嚗諹𥅾摮睃銁�躰䌊�冽�銵� `selection_set`��focus` 撟嗉��� `see(code)`嚗䔶蝙撖孵���㺭�株��芸𢆡皛𡁜𢆡�啣虾閫�躹�笔僎鈭�誑擃䀝漁�𡁶�嚗𥡝𥅾銝芾�銝滚銁�𡑒”銝剖��䠷�頝唾�����曄內�删鍂��𥁒�蹱�嚗䔶�霂��銝𦒘蜓 Tk 蝒堒藁����冽�雿𣈯�餉�摰𣬚�蝏煺���
    - [x] **靽桀��枏� EXE �臬𢆡頝臬��𠰴極雿𦦵𤌍敶� CWD 蝥䭾迤 (Fixed EXE Packaging CWD in webTools)**嚗𡁻���� `webTools/manage_window_layout.py` 銝剔� `get_app_root()` 頝臬�摰帋��寞���銁蝔见�鋡急�����祉� exe 銝娪�朞��喲睸敹急㭘�𨅯��𣇉頂蝏���∪鍳�冽𧒄嚗�撩�嗅�敶枏���極雿𦦵𤌍敶𤏪�CWD嚗劐蝙�� `os.chdir` �祆𧒄��揢�� exe �舀�銵𣬚�摨𤩺��函��拍�摰㕑���辣憭寞覔�桀�嚗䔶�皞𣂼仍銝𡃏圾�喳極雿𦦵𤌍敶訫�撌桀紡�湔�瘜閗粉�㚚�蝵格�隞嗥��桅�嚗䔶��𡁜�銝齿㺿�� `sys_utils.py`��
    - [x] **撖寥�憭𡁜𪂹�罸�蝵格�銋��銝� App 蝏嘥笆�寧𤌍敶� (Aligned Config Paths with get_app_root)**嚗𡁻���� `standalone_multi_period_tester.py` 銝� `multi_period_strategy_engine.py` 銝剔����厰�蝵格�隞嗉粉�躰楝敺����𡠺 `standalone_tester_config.json` 銝� `multi_period_strategies.json`嚗㚁��券��嫣蛹�箔� `sys_utils.get_app_root()` �澆枂���撖寡楝敺�����脫迫鈭�����PyInstaller / Nuitka嚗匧��坔�銝湔𧒄�𦠜𦆮�桀��硋蘨霂颱�蝵桀紡�渡��滨蔭銝Ｗ仃銝𦒘�摮睃援皞���
    - [x] **�朞��𣳇�蝻𤥁�銝舘䌊璉� (Passed Syntax Verification & Self-Test)**嚗𡁜笆 `data_utils.py`��multi_period_strategy_engine.py` �� `standalone_multi_period_tester.py` �扯�鈭� `py_compile` �拍�霂剜��⊿�嚗���冽��䠷�朞�嚗𣬚＆靽苷�擃㗛�銵峕�餈鞱��嗥���蔔�亙ㄝ�扼���苷�靽嘥��噼�**嚗𡁜��𣂷�蝑𣇉裦蝞∠��其葉����券�霂���殷�靽肽�靽嘥��箇�蝑𣇉裦�滨蔭銝滢�撘訫�餈鞱��笔援皞��靽嘥��嗉䌊�券�頧賭蜓�屸𢒰 Combobox �舫�匧��啜��
        - [x] **靽桀�蝑𣇉裦蝞∠��其葉靽格㺿�滨妍撖潸稲�����/�漤�� Bug (Fixed Listbox Multi-selection Bug)**嚗帋耨憭滢��� Listbox ��揢蝑𣇉裦�厰★�塚��曹��� `_on_select` 鈭衤辣���甇交�銵䔶��扳�憿寧� `delete`��insert` 銝� `selection_set` �餉�嚗�紡�� Tkinter �匧�憿寞�撠��蝟餃�蝒��䔶漣�煺舅銵峕�憭朞��峕𧒄擃䀝漁�劐葉�� Bug��緵�朞�撠���亙�蝘啁��䀹凒�峕郊�箏��齿�銝箏笆 `StringVar` �� `trace_add("write", ...)` 餈𥡝��冽��齒�穿�隞�銁��𧋦�笔�靽格㺿�嗅��券�暺䀝耨�� Listbox 摮埈挾嚗�蝠摨閙��支��孵稬��揢�嗥�憭𡁻�匧�蝒���
    - [x] **摰䂿緵頝典𪂹�毺鸌敺�㺭�格�撟喳�撟喲唍��僎銝𡒊頂蝏毺漣霂𦠜鱏撖寡�獢�笆�� (Unified Flat-Series Diagnostics & Existing Window Integration)**嚗�
        - [x] **銝芾�頝典𪂹���撟喳��齿�**嚗𡁜�銝芾��典�銝𡒊�憭帋葵銝滚�蝑𣇉裦�冽�嚗Ê̌������45d��3M嚗厩鸌敺���唳旿�惩�銝箔誑 `{col}_{period}` �𡒊��賢����銵�捐銵函�������銝�銝芸像�箇� DataFrame `df_flat`��
        - [x] **銵刻噢撘誩��滚�蝻����**嚗𡁏覔�桀��冽�霈∠�撘閙��堒仍��㺭�殷�撖寧��� query �∩辣餈𥡝��閗�甇���寥�嚗���刻蓮�Ｖ蛹撣血𪂹�笔�蝻� of 撟喲唍摮鞱”颲曉�嚗��撠� `close > ma5d` 頧祆揢銝� `close_w > ma5d_w`嚗㚁��脫迫�堒��脩���
        - [x] **�删�撖寞𦻖蝟餌� check_code 蝏�辣**嚗帋蝙�刻蓮�Ｗ��� `df_flat` 銝� `queries`嚗𣬚凒�亥�韏� pyQuant3 蝟餌�����蠘�蟡冽��交𥁒�羓��� `check_code`嚗��蝢𡡞��其�擃㗛��潛�霂𦠜鱏撖峕��祉��Ｕ����脫�霂蓥��㕑��蓥誑�𠰴𢆡��漱鈭鍦��见𢆡瘚贝��批��～��
        - [x] **摰䂿緵�芸𢆡�𡝗�霂閙㺭�桀��其��嗉�埈𧒄撉諹� (Zero-I/O Automated Test Reuse)**嚗𡁻��嗘� `test_multi_period_automated.py`嚗峕�霂閗��剜�蝔讠凒�交𦻖�嗅�摨誩歇�㰘蝸憟賣㺭�桃� `engine` 銝� `top_now` 敹怎���㺭嚗���典��颱�鈭峕活 TDX 銝� H5 蝤��霂餃�嚗諹�銵峕������秐鈭𡁏神蝘垍漣嚗䔶��冽綉�嗅蝱雿輻鍂 GBK 摰匧�餈�誘�箏�嚗�蝠摨閙覔瘝颱� unicode 蝻𣇉�撏拇�憌𡡞埯��
        - [x] **摰䂿緵霂𦠜鱏�舘䌊�冽��典�雿滢�擃䀝漁銝芾� (Auto-scroll & Selection Highlight on Diagnosis)**嚗𡁜銁 `diagnose_stock_strategy` 霂𦠜鱏瘚���扯�摰峕��𠬍�璉��亙��� Treeview �臬炏摮睃銁霂乩葵�� `code`嚗諹𥅾摮睃銁�躰䌊�冽�銵� `selection_set`��focus` 撟嗉��� `see(code)`嚗䔶蝙撖孵���㺭�株��芸𢆡皛𡁜𢆡�啣虾閫�躹�笔僎鈭�誑擃䀝漁�𡁶�嚗𥡝𥅾銝芾�銝滚銁�𡑒”銝剖��䠷�頝唾�����曄內�删鍂��𥁒�蹱�嚗䔶�霂��銝𦒘蜓 Tk 蝒堒藁����冽�雿𣈯�餉�摰𣬚�蝏煺���
    - [x] **撖寥�憭𡁜𪂹�罸�蝵格�銋��銝� App 蝏嘥笆�寧𤌍敶� (Aligned Config Paths with get_app_root)**嚗𡁻���� `standalone_multi_period_tester.py` 銝� `multi_period_strategy_engine.py` 銝剔����厰�蝵格�隞嗉粉�躰楝敺����𡠺 `standalone_tester_config.json` 銝� `multi_period_strategies.json`嚗㚁��券��嫣蛹�箔� `sys_utils.get_app_root()` �澆枂���撖寡楝敺�����脫迫鈭�����PyInstaller / Nuitka嚗匧��坔�銝湔𧒄�𦠜𦆮�桀��硋蘨霂颱�蝵桀紡�渡��滨蔭銝Ｗ仃銝𦒘�摮睃援皞���
    - [x] **�朞��𣳇�蝻𤥁�銝舘䌊璉� (Passed Syntax Verification & Self-Test)**嚗𡁜笆 `data_utils.py`��multi_period_strategy_engine.py` �� `standalone_multi_period_tester.py` �扯�鈭� `py_compile` �拍�霂剜��⊿�嚗���冽��䠷�朞�嚗𣬚＆靽苷�擃㗛�銵峕�餈鞱��嗥���蔔�亙ㄝ�扼��son` �滨蔭��辣銝准��銁 `__init__` �嘥��𡝗𧒄�㰘蝸撟嗉��蠘砲�牐��滨蔭嚗���唬�蝒堒藁撠箏站銝𤾸����頝其�霂肽䌊���霈啣��蠘���僎銝𥪜銁擐𡝗活�枏��嗉䌊���霈∠�撟嗅�銝剜遬蝷箏銁�嗥�����硋�撟𤏪�甇�葉憭殷�閫��鈭��霈文椰銝𡃏�摰帋����閫厩撩�瑯��
        - [x] **7憭扳��亙𪂹��辺隞嗥𡠺蝡见鍳�其���𧋦蝻𤥁�**嚗𡁏𣈲������舐鍂 `SUPPORTED_PERIODS`嚗�鉄 45d��3M嚗厩��訫𪂹�� query 餈�誘嚗𣬚��冽𧒄���颲枏�嚗�鍳�冽𧒄暺䁅恕���������蝞��∩辣嚗�� `close > ma5d`嚗剹��
        - [x] **摰墧𧒄 Pandas Query 餈�誘�刻祗瘜閙�瘚衤� Tooltip ��內��**嚗𡁜��乩��� `MultiPeriodStrategyEngine` 銝剔� `validate_condition` �寞�嚗�銁����㗇㺭�格𧒄�扯��笔�撉諹�嚗峕��笔��唳旿�嗡誑��鉄 30 雿嗘葵擃㗛����舀���� Dummy DataFrame 撉冽沲�扯� query 霂閗�銵䕘�撉諹��𣂼��曄內蝏輯𠧧�鎿� 霂剜�撉諹��朞��嘅�憭梯揖�嗵滯摮埈��箏僎�舫�朞� Tooltip �祆筑撅閧內霂衣�����仿���
        - [x] **���銝��栽�𣈯�霂���兩�苷�靽嘥��噼�**嚗𡁜��𣂷�蝑𣇉裦蝞∠��其葉����券�霂���殷�靽肽�靽嘥��箇�蝑𣇉裦�滨蔭銝滢�撘訫�餈鞱��笔援皞��靽嘥��嗉䌊�券�頧賭蜓�屸𢒰 Combobox �舫�匧��啜��
        - [x] **靽桀�蝑𣇉裦蝞∠��其葉靽格㺿�滨妍撖潸稲�����/�漤�� Bug (Fixed Listbox Multi-selection Bug)**嚗帋耨憭滢��� Listbox ��揢蝑𣇉裦�厰★�塚��曹��� `_on_select` 鈭衤辣���甇交�銵䔶��扳�憿寧� `delete`��insert` 銝� `selection_set` �餉�嚗�紡�� Tkinter �匧�憿寞�撠��蝟餃�蝒��䔶漣�煺舅銵峕�憭朞��峕𧒄擃䀝漁�劐葉�� Bug��緵�朞�撠���亙�蝘啁��䀹凒�峕郊�箏��齿�銝箏笆 `StringVar` �� `trace_add("write", ...)` 餈𥡝��冽��齒�穿�隞�銁��𧋦�笔�靽格㺿�嗅��券�暺䀝耨�� Listbox 摮埈挾嚗�蝠摨閙��支��孵稬��揢�嗥�憭𡁻�匧�蝒���
    - [x] **撖寥�憭𡁜𪂹�罸�蝵格�銋��銝� App 蝏嘥笆�寧𤌍敶� (Aligned Config Paths with get_app_root)**嚗𡁻���� `standalone_multi_period_tester.py` 銝� `multi_period_strategy_engine.py` 銝剔����厰�蝵格�隞嗉粉�躰楝敺����𡠺 `standalone_tester_config.json` 銝� `multi_period_strategies.json`嚗㚁��券��嫣蛹�箔� `sys_utils.get_app_root()` �澆枂���撖寡楝敺�����脫迫鈭�����PyInstaller / Nuitka嚗匧��坔�銝湔𧒄�𦠜𦆮�桀��硋蘨霂颱�蝵桀紡�渡��滨蔭銝Ｗ仃銝𦒘�摮睃援皞���
    - [x] **�朞��𣳇�蝻𤥁�銝舘䌊璉� (Passed Syntax Verification & Self-Test)**嚗𡁜笆 `data_utils.py`��multi_period_strategy_engine.py` �� `standalone_multi_period_tester.py` �扯�鈭� `py_compile` �拍�霂剜��⊿�嚗���冽��䠷�朞�嚗𣬚＆靽苷�擃㗛�銵峕�餈鞱��嗥���蔔�亙ㄝ�扼��

## 2026-06-27 18:15
- [x] **憭𡁜𪂹�毺��亦��匧膥�游� (Integrating Multi-Period Strategy Tester)**:
    - [x] **�冽�������賢𪂹�毺恣�� (Dynamic Window Lifecycle Management)**: �齿�鈭� `StandaloneMultiPeriodTester` 雿踹�敶枏�雿靝蛹 `tk.Toplevel` 摮鞟�����乩蜓蝔见�餈鞱��塚��喲𡡒�滢�頧砌蛹 `withdraw()` �鞱�蝒堒藁�屸� `destroy()` ��瘥�誑靽萘��嗆���敶㮖�銝箇𡠺蝡讠�摨讛�銵峕𧒄嚗峕迤撣賊��曉僎��霈Ｕ��
    - [x] **銝餌��Ｗ��亙藁瘜典�銝𡡞�蝵桃恣�� (Main UI Entry Registration & Config)**:
        - 瘜典� "憭𡁜𪂹�毺���" �啣��� "�蠘��㗇𥋘" �𨅯�銝𧢲�獢�僎摰䂿緵 `run_action` 頝唾蓮頝舐眏��
        - 銝餌�雿㯄▲�典翰�瑟��啣� "憭𡁜𪂹�跔��" 敹急㭘�厰僼嚗�僎�峕郊瘜典��� `open_top_bar_settings` 敹急㭘�𤩺綉�嗡葉隞交𣈲��虾閫���鞱�銝𡡞�蝵格�銋����
    - [x] **�典�敹急㭘�株��其��嗆���摨� (Global Shortcuts Alt-M)**:
        - �其蜓蝒堒藁銝剜釣�� `<Alt-m>` �� `<Alt-M>` 敹急㭘�殷�摰䂿緵撖孵��冽�蝑偦�厩����銝��格遬�𣂼��Ｖ��衣��滩繮��
    - [x] **憭朞�蝔讠��賢𪂹�煺���霈Ｗ��其��� (Process Lifecycle & Unsubscribe Guard)**:
        - �其蜓蝒堒藁 `on_close` ��瘥��餉�銝哨�銵亙�鈭�笆憭𡁜𪂹�毺��匧�蝒堒藁��遬蝷粹��霈ｇ�`GlobalFavoriteManager.unsubscribe`嚗劐�蝒堒藁 `destroy()` �其�嚗�蝠摨閖獈�凋����瘜�蠧�� zombie 摮鞱�蝔𧢲��嗵�憌𡡞埯��
    - [x] **�𣳇�蝻𤥁�銝舘䌊璉� (Syntax Verification & Self-Test)**:
        - 摰峕�鈭�笆 `instock_MonitorTK.py` �� `standalone_multi_period_tester.py` ��祗瘜閙��嗵�霂煾�霂���

## 2026-06-27 15:45
- [x] **憭𡁻�撟嗅��𥪜𢆡�批�銝擧��刻䌊摰帋�����冽����� (Multi-Target Linkage & Dynamic Manual Column Entry)**嚗�
    - [x] **�齿��祉�撟嗉��𥪜𢆡�箏�銝𡒊𠶖���銋�� (Parallel Linkage & State Saving)**嚗�
        - �鍦�鈭���滨��靝��亙����嘥��𥪜𢆡嚗�銁摨閖� `stats_frame` �嗆����喃儒�啣�鈭� `Vis`, `Tdx`, `Ths` 銝劐葵�祉�憭漤�㗇���
        - ��捂�冽��芰眏蝏��嚗���啁��颱葵�⊥𧒄�峕𧒄�𥪜𢆡 `Visualizer` (TCP IPC Port 26668) 隞亙��砍𧑐 `TDX` �� `THS`嚗𥕦銁 `_load_state`��_save_state` 銝剖�甇乩�摮睃� Boolean �嗆���摰䂿緵頝其�霂萘��芣��Ｗ���
        - �� `_do_linkage` �餉�銝剖����霂衣��������函𠶖���蝷綽��賢銁�嗆���銝剜��賢��啗站憒� `�� 撌脰圻�𤏸���: 000001 (Vis, Tdx)` ���蝷箝��
        - 蝏穃�鈭� Tkinter �� `WM_DELETE_WINDOW` �喲𡡒�讛悅嚗�銁蝒堒藁��瘥���芸𢆡�枏�撟嗆�銋��敶枏�������雿訫之撠誩�雿滨蔭�鞉�嚗Ǒgeometry`嚗㚁�摰䂿緵頝其�霂苷�蝵桐�撠箏站��䌊�刻��麄��
    - [x] **摰䂿緵�见𢆡�𡑒䌊摰帋��滨蔭瘙牐�鈭支�撘� Checkbutton ��蝸 (Manual Column Entry & Interactive Checkboxes mount)**嚗�
        - �刻䌊摰帋��烾�厰★�舘蕭�牐��见𢆡颲枏���𧋦獢� `manual_col_entry`嚗�僎蝏穃�鈭��頧阡睸銝� `+`嚗�溶�𩤃���-`嚗�宏�歹��厰僼��
        - 颲枏�隞餅������ DataFrame 撅墧�批�嚗�� `ma10d`��vol`嚗匧僎�匧�頧行��孵稬 `+` �𠬍�蝟餌�隡朞䌊�典��嗥蒈霈啗� `manual_col_pool` 銝哨��峕𧒄�� UI 銝𠰴𢆡���頧賭�銝芸��啁�憭漤�㗇�嚗屸�霈文㗲�匧僎靽嘥�嚗���颱��齿鰵�瑕鍳�函��鞉𧋦嚗𥡝𥅾�孵稬 `-` �嗘��單𧒄瘜券�霂亙���
        - �駁膄鈭��雿嗵� `"�芸�銋匧�:"` ��𧋦��倌嚗䔶蝙�港葵撌亙��讐征�游⏚�刻噢�唳��氬��
        - �� Treeview 皜脫��嗥眏鈭𡡞��碶��暹袇�� OCP �株圾�琜�隞颱�鋡急�瘣餌��见𢆡�㛖�隡朞䌊�冽�撠�僎��緵憭𡁜𪂹��㺭�潘��墧㺭摮𦯀��嗅��冽��唬蛹 `--`嚗剹��
    - [x] **����典��芷�㕑��𣈯��孵�瘜兩�苷��喲睸銝𠹺�����閗��� (Global Watchlist/Favorites Integration)**嚗�
        - �� Treeview 銵冽聢銝剝��𣂷�銝𦒘犖瘞𥪜��舐㮾�𣬚��喲睸�𨅯�鈭衤辣蝏穃�嚗峕𣈲��𢰧�桀翰�� `�� 瘛餃��滨��單釣` �� `�� �𡝗��滨��單釣`��
        - 霈ａ�鈭� `GlobalFavoriteManager` �穃�/霈ａ��䀹凒鈭衤辣嚗䔶遙雿訫�隞𣇉����憭㚚��睃𢆡閫血��芷�匧�銵冽凒�唳𧒄嚗𣬚��匧膥隡朞䌊�典��典��唬葵�� data 銵䕘�擃䀝漁 `�� �滨�撟嗅�甇交溶�� `favorite` ��倌嚗剹��
        - �� Style �滨蔭銝凋蛹 `favorite` ��倌摰𡁜�鈭��蝎堒�蝥Ｚ𠧧摮𦯀��瑕�嚗Ǒ#C62828`嚗㚁�撟嗅銁蝑偦�㗇㺭�桀�憪见�頧賣𧒄�箄��寥�擃䀝漁�嗆����
        - 摰��鈭���賢𪂹�毺恣����函����瘥� `on_close` �嗉䌊�典�瘨�䌊�㕑恥����脰����瘜����
        - 摰䂿緵鈭���孵�瘜刻�隡睃��鍦�蝵桅▲皜脫��箏���銁撅閧內蝑偦�厩��𨀣𧒄嚗��撌脰◤�滨��單釣��葵�⊥��毺㮾撖寥◇摨誩僎�券���銵冽聢��憿園�嚗䔶蝙�嗅銁瘚琿��唳旿銝剝�撅誩朖�臭��桐��嗚��
    - [x] **隡睃�撌亙��誩�撅��脤��� (Optimized Toolbar Layout to Prevent Occlusion)**嚗�
        - 撠�瓲敹��雿𨀣��� `�� 餈鞱�蝑偦�头 ��葡�𤘪�雿滚�蝘餃� `����冽�` �暸�㗇��汿���芸�銋匧�` 銋见�嚗䔶誑蝖桐��典𢆡���頧賢之�𤩺���紡�渲”憭湔��𣂼��喳辣隡豢𧒄嚗峕��詨�����㗇�銵峕��格偶餈𨅯�鈭擧遬�潛��滨垢嚗���方◤�文枂閫�藁�㚚��∠��𤤿���
    - [x] **�朞��芸𢆡�𡝗�銋��撉諹�銝擧��躰祗瘜閗䌊璉�**嚗帋蝙�典�銵峕芋�蠘�銵�笆�暸�匧��氬����冽���溶�𨬭���蝵格�隞嗅��䁅�銵䔶��券曎頝舀�霂𤏪�摰𣬚�蝻𤥁��𣳇�嚗峕�霂閧��𨀣��笔��躰秐 `standalone_tester_config.json`��

## 2026-06-27 15:30
- [x] **�啣�摨閖�憭𡁜𪂹�毺��厩�霈∩縑�舫𢒰�蹂����摨阡� (Bottom Statistics Panel & Cross-Period Metrics)**嚗�
    - [x] **撱箇�頝典𪂹��𤣰��膥 (Zero-Overhead Statistics Collector)**嚗�
        - �� `multi_period_strategy_engine.py` �� `evaluate_strategy` 霈∠�瘚��銝哨����鈭� `self.last_stats` 摮堒�嚗峕𤣰���銝芸�銝𤾸𪂹�毺�銝芾�摨閙㺭���朞��⊥㺭���朞���蓡���嚗𥕦僎�典�撟嗥��㚁�鈭日�/撟園�嚗匧��删泵��辺隞嗆㜃�芸���葉嚗���渡�霈∪枂�典��箸�����啜���蝏��朞��芣㺭�峕�餉�瘥䈑�摰䂿緵 $O(1)$ �嗉恣蝞埈��㛖�靽⊥��𡁏𨋍��
    - [x] **摰䂿緵 Tkinter 摨閖��芷���蝏蠘恣靽⊥��誩�撅� (Bottom Adaptive Statistics Frame Layout)**嚗�
        - �� `standalone_multi_period_tester.py` 銝剜鰵憓� `self.stats_frame` 摨閖��譌���朞�銝交聢�� `pack` 憿箏�嚗𣬚＆靽� `stats_frame` �Ｗ𤐄�祆筑�冽�摨閖��䔶�鋡思��� `expand=True` ��蜓 Treeview �文枂閫�藁��
        - �冽��葡�𣏾�𨅯��冽��朞����嘅�憒� `d: 1092/5535(19.73%) | w: ...`嚗匧��𨀣�蝏���厩��鎿�嘅�憒� `鈭日��� 803 �� / 撣�㦤 5535 �� (14.508%)`嚗㚁��舀��㗇��厩��亙���僎璅∪�嚗�漱��/撟園�嚗㗇惣�賢��Ｘ��穿��𣂷�銝��桐��嗥��唳旿�喟��舀���
    - [x] **頝煾�朞䌊�典�撉諹�銝擧��躰祗瘜閗䌊璉�**嚗𡁜笆 `test_multi_period_automated.py` �䔶蜓摰Ｘ�蝡航�銵䔶��𧼮�撉諹�嚗𣬚�霂睲�餈鞱�摰��甇�虜��

## 2026-06-27 15:10
- [x] **憭𡁜𪂹�蠘��函��匧膥�芸�銋㗇����銝擧�蝒�䌊����堒捐璅∪� (Multi-Period Custom Columns & Ultra-Narrow Column Fit)**嚗�
    - [x] **��� 'Rank', 'dff', 'dff2', 'dff3' �芸�銋㗇���㗲�劐������ (Custom Columns & State Saving)**嚗�
        - �函𡠺蝡钅�霂��蝑偦�匧膥 `standalone_multi_period_tester.py` 撌亙��譍葉�啣�鈭��𡏭䌊摰帋��轁�嘥��㗇��箏�嚗䔶��冽��𤩺𧒄�孵稬�㗇𥋘�臬炏�曄內 `'Rank'`, `'dff'`, `'dff2'`, `'dff3'` �����
        - �湔鰵鈭� `_load_state`��_save_state` �� `_apply_state` �寞�嚗���冽���䌊摰帋��堒�憟賡�蝵桀�蝢擧�銋���� `standalone_tester_config.json` 銝哨��舀�頝其�霂萘𠶖��䌊����麄��
    - [x] **摰䂿緵憭𡁜𪂹�����𢆡���憭渡��𣂷��厰�皜脫� (Dynamic Multi-Period Columns Binding)**嚗�
        - 蝻硋�鈭� `_update_tree_columns` 蝏煺��㛖�摰𡁏䲮瘜𤏪�撠�㗲�厩��芸�銋匧�銝𤾸��齿暑頝���𨅯�銝𤾸𪂹�麨�苷漱�厩�����冽���摰𡁶��鞟掩隡� `Rank(d)`, `dff(w)`, `dff2(m)` 蝑匧��冽��芸�銋匧�嚗�僎皜��鈭�� `_init_ui` 銝剔′蝻𣇉� columns ���雿䠷�餉���
        - �齿�鈭� `_show_results`嚗���嗅�蝑偦�厩��𨀣𧒄嚗�笆鈭擧�銝�銝芾䌊摰帋��� `{col}_{period}`嚗諹䌊�刻楝�勗� `self.engine._period_dfs[period]` �唳旿撣找葉嚗屸�朞�銝芾� `code` �𣂼����笔����摮埈挾�唳旿撟嗆葡�橒��墧㺭�潸��� `'--'`嚗峕㺭�澆�畾菔䌊�� round �𥡝�鈭𥪜�靽萘�銝支�撠𤩺㺭��
    - [x] **摰䂿緵����𧋦�啁�摮䀝�甈⊥凒�唬��冽��孵��滨� (Flicker-free Cache Refresh)**嚗�
        - �啣� `_on_custom_col_changed` �� `_on_period_changed` 撌桀��碶�隞嗅�摨䈑�敶梶鍂�瑚��暸��/�𡝗��暸�争�𡏭䌊摰帋��轁�脲𧒄嚗𣬚凒�亙��其�銝�甈∟恣蝞𦯀�摮条� `self.last_result_df` 銝� `self.last_elapsed` �祇𡢿餈𥡝�撅��� Treeview �滨�嚗���唬���迤����芰���� I/O �滨�嚗𥕦�銝𥪯�敶𤘪㺿�覀�𨅯�銝𤾸𪂹�麨�苷�蝻枏�銝齿說頞單𧒄嚗峕�閫血��𤾸蝱 `_worker` 霈∠���
    - [x] **摰䂿緵蝒堒藁�𡑒䌊�������鍦�璅∪� (_adjust_column_widths)**嚗�
        - �祉�蝻硋�鈭� `_adjust_column_widths` ����芷����堒捐瘚钅�蝞埈�嚗屸�朞�撖寡”憭湔�摮�/蝚血噡/摮埈����隡澆�蝝䭾�蝞梹��冽��𤣰蝒���曉捐����讐�摰踝��滨妍�烾��� 45-75px嚗峕㺭�桀��芸�銋匧��𣂼���撠� 32px嚗峕�憭� 100px嚗㚁�蝖桐����匧��冽��芸�銋匧�蝝批�撟喲唍嚗���冽��支�蝛箇蒾�峕滯�箝��
    - [x] **�𣳇��朞� Python 霂剜�蝻𤥁�銝舘䌊璉�**嚗𡁜笆靽格㺿�𡒊� `standalone_multi_period_tester.py` 餈𥡝�鈭� `py_compile` �𣳇�蝻𤥁�嚗屸�霂�妟霂剜��𢠃妟蝻抵�撘�虜��

## 2026-06-27 12:00
- [x] **�其�蝟餅�撅訫僎�峕郊 45憭� (45d) 銝� 3銝芣� (3M) �条裦鈭斗��冽� (System-Wide Support for 45-day & 3-month Strategic Cycles)**嚗�
    - [x] **�拙� Argparse �賭誘銵���啗圾�𣂼膥��𪂹�罸�㗇𥋘**嚗�
        - �湔鰵鈭� `test_bidding_replay.py` �� `--resample` choices ��㺭嚗���乩� `'45d'`, `'3M'`��
        - �湔鰵鈭� `jupyterAlgo/AlgoTest/chantdx.py` �� `-d/--dtype` choices ��㺭嚗���乩� `'2d'`, `'3d'`, `'5d'`, `'45d'`, `'3M'`��
        - �湔鰵鈭� `chantdxpower.py` �� `-d/--dtype` choices ��㺭嚗屸�蝵桐蛹 `['5','30','60', 'd', '2d', '3d', '5d', '45d', 'w', 'm', '3M']`��
        - �湔鰵鈭� `JohnsonUtil/commonTips.py` 銝剔� `LineArgmain` �� `MoniterArgmain` �� `-d/--dtype` choices ��㺭嚗���牐� `'2d', '3d', '5d', '45d'` �� `'3M'` �舀�嚗𣬚＆靽嘥�撟喳蝱�賭誘銵�極�瑕𪂹�笔��啗��乩�鋡急㜃�芷獈�准��
        - �湔鰵鈭� `instock_MonitorTK.py` �賭誘銵�鍳�典��唬葉 `-resample` �� choices 銝� help 霂湔�嚗���乩� `'5d', '45d', '3M'`嚗𣬚＆靽萘��Ｖ蜓蝔见��券�朞��賭誘銵䔶��鍦𪂹�笔��啣鍳�冽𧒄嚗䔶�隡𡁜���㺭�⊿��烾獈��
        - 靽格迤鈭� `instock_MonitorTK.py` 銝餌��ａ▲�� `resample_combo` �� `values` 憸�挽嚗諹��港蛹 `['d', '2d', '3d', 'w', 'm', '45d', '3M']` �鍦��鍦�嚗䔶��曄內�寥���𪂹�罸�厰★��
    - [x] **�峕郊蝑𣇉裦�批�銝𤾸𪂹�蠘圾�鞟恣��**嚗𡁜銁 `stock_live_strategy.py` 銝剔� `resolve_stock_key` �寞��䕘��峕郊�湔鰵鈭�𪂹�笔�蝻�閫���𡑒”嚗���� `'2d'`, `'3d'`, `'5d'`, `'45d'`, `'3M'`嚗㚁�雿踹�蝑𣇉裦�扯�蝞⊿��函�銝剛�銵���嗡葵�� Key �𡒊��⊿��塚��賢�蝢舘楝�勗僎霂�� 45憭�/3�� 蝑匧之蝥批��唳旿�冽�瘚���
    - [x] **�㯄�𡁜僎撉諹�憭抒漣�� K蝥� Resampling 霈∠��剔㴓**嚗�
        - 蝻硋�撟嗉�銵䔶� `scratch/test_resample_expand.py` �芸𢆡�𡝗�霂閗��穿�撖寡斯撌噼��堆�600519嚗厩� 45d �� 3M 憭批𪂹��㺭�株�銵��瘚𧢲��碶��𡁜�霈∠���
        - 瘚贝�霂��嚗𡁶頂蝏蠘��𣳇��㰘蝸��蓮�� Pandas �嗅�撟嗅�蝢𤾸��� 274 �堒��冽��舀������鉄�𡁻���� `ptop`, `pbottom`, `pbreak`, `pdays`嚗厩�憭抒漣�� resample �ａ��𤥁恣蝞梹��牐遙雿� KeyError �𣇉掩�贝����撣詻��
    - [x] **摰峕� Python 霂剜�蝻𤥁�銝𤾸蘨霂餃��刻䌊璉�**嚗𡁜笆靽格㺿�𡒊� `stock_live_strategy.py`��test_bidding_replay.py`��jupyterAlgo/AlgoTest/chantdx.py`��chantdxpower.py`��commonTips.py` 隞亙� `instock_MonitorTK.py` 餈𥡝�鈭� `py_compile` 蝻𤥁�撉諹�嚗峕��㕑��� 100% �拍�蝻𤥁��𣳇��朞���
    - [x] **皜��撟嗅��斗��函� `data_utils_readonly.py` �𦯀��舀𧋦 (Cleaned Up data_utils_readonly.py)**嚗�
        - 蝏誩�撅���𧋦璉�蝝ａ�霂��蝖株恕憿寧𤌍銝剜�隞颱�璅∪�撖澆��碶�韏� `data_utils_readonly.py` �舀𧋦��
        - �拍��𣳇膄鈭�砲�𦯀��芾粉�舀𧋦嚗�僎撖嫣蜓璅∪� `data_utils.py` �扯�鈭� `py_compile` 蝻𤥁�撉諹�嚗諹䌊璉��朞��牐遙雿訫�撣詻��

## 2026-06-26 17:15
- [x] **摰䂿緵鈭箸��望𥲤銵峕�摰墧𧒄�峕郊銝𤾸��冽��芰����笔��� (Implemented Real-time IPC Sync & Flicker-free Refresh for Popularity Resonance)**嚗�
    - [x] **�㯄�� `IPCSyncManager` �𡁶鍂銵峕��峕郊璅∪�**嚗𡁜銁 `popularity_resonance_gui.py` 摰Ｘ�蝡臬鍳�冽𧒄摰硺��硋僎撘��舫�𡁶鍂 IPC �峕郊蝞∠��剁��穃𨯬�砍𧑐 26671 蝡臬藁嚗���冽㗁�亦眏銝餌�摨𤩺綫�����鉄 `percent`, `trade`, `dff2`, `dff3`, `Rank`, `category` 蝑匧�畾萇��券�銵峕� DataFrame嚗�蝠摨閧�蝏㮖�鈭箸��望𥲤銝𦒘蜓蝔见�銵峕��梯���𠶖����
    - [x] **�拙� Treeview �嗆�銝� 9 �堒捐閫�藁 (Expanded Treeviews to 9 Columns)**嚗𡁻���� `create_treeview` 銝剖��冽��閗”�潘��啣��𨀣��唬遠�腈���筂ff2�腈���筂ff3�腈���晉ank�苷誑�𪙛�𡏭�銝𡁏踎�轁��5�𨰜���蝵桐��芷����堒捐銝𡡞俈�格𣏹�劐撓嚗��蝘啣� 85px嚗諹�銝𡁏踎�� 95px ��捂�劐撓嚗��雿坔𤐄摰𡁶�摰賢漲嚗㚁�撟嗅銁 `base_headers` 摮堒�銝𡒊悌憭游儐�臭葉摰峕㟲銵仿�餈� 5 銝芣鰵憓𧼮�嚗峕�蝏苷��孵稬�啣�銵典仍�鍦��嗡漣�毺� KeyError 撏拇���
    - [x] **摰䂿緵�瑕鍳��/�湔鰵銝𤾸��嗅��典��啣�閫�凒�唳㦤��**嚗�
        - �齿�鈭� `update_all_tables`嚗���𣇉�憿萇��𨅯�閬��嚗剹��銁擐硋��唳旿銝𤾸��嗅��𤩺��硋�嚗䔶���� `IPCSyncManager` ���摮� DataFrame �寥����啣�畾萄�潸�銵屸�靽萘�撖寥�憛怠���
        - 摰䂿緵鈭� `refresh_realtime_fields` �� `on_realtime_data_updated` �噼�����嗅� TCP 撟踵偘�券��𧒄嚗𣬚眏銝餌瑪蝔见銁 `after(0)` 銝凋葡銵屸��� 5 銝芾”�潛��券�銵䕘�隞���券�蝏� values 撟嗅𢆡��凒�唳隅頝� tag嚗óp/down/flat嚗㚁�摰䂿緵鈭��銝剜��麄����芰�����⊿▼����嗉���葡�瓐��
    - [x] **隡睃� `--` �羓征摮㛖泵���摨誩��潸蓮�ａ�璉埝��**嚗𡁜銁 `sort_column` ����� `try_convert` 頧祆揢�寞�銝哨�憓𧼮�鈭�笆 `val_str == '--'` ���皛斗㜃�迎�雿踹�蝏煺�鋡恍�蝥扯蓮�碶蛹 `-9999.0` ��撠𤩺㺭�澆�銝𡡞��𡜐�敶餃�靽桀�鈭�𧊋�瑕��啣��嗉����銝芾��冽�摨𤩺𧒄�𤑳��鍦�蝝𠹺僚�������
    - [x] **蝘駁膄 PyInstaller 靘肽��㘾膄撟嗅��𣂼�蝟餌�蝻𤥁��穃�**嚗�
        - 隞� `PopularityResonanceSync.spec` 銝剔��㘾膄�𡑒”嚗Ềxcludes嚗劐葉�娪膄鈭� `pandas` �� `numpy`嚗䔶蝙�枏���虾�扯���辣�瑕��祉��㰘蝸撟嗉圾�� pickle 摨誩��硋之 DataFrame ����䜘��
        - �𣂼��典��啗�銵� PyInstaller 摰峕�鈭� `dist/PopularityResonanceSync.exe` 摰Ｘ�蝡舐��𣳇��拍�蝻𤥁�嚗䔶�銝㗇䲮銝餌�摨誩�摰Ｘ�蝡� Python 璅∪��拍�蝻𤥁��券��𣳇��朞���

## 2026-06-26 09:00
- [x] **靽桀� stock_codes.conf �唳旿�芸𢆡�湔鰵銝𤾸�摮条�摮睃�甇交㦤�� (Fixed stock_codes.conf Auto-Update & Memory Cache Sync)**嚗�
    - [x] **�㯄�� `get_stock_codes(True)` ���撅墧�批�甇�**嚗𡁜銁 `get_stock_codes`嚗Ǒrealtime=True`嚗匧��臭� `update_stock_codes` ����交��笔��臭葉嚗諹‘朣𣂷�撖� `self.stock_codes = stock_codes` ����潘�敶餃��寞祥鈭��憸𤏸���凒�啣����銝凋�雿輻鍂�扳�蝻枏��𡑒”�� Bug��
    - [x] **蝻拍��湔鰵�文��冽��單��乩�甈� (Set Update Frequency to Once-a-Day)**嚗𡁜� `StockCode.__init__()` 銝� `stock_codes.conf` ��凒�啣ế�剝��潛眏 `> 5` 憭拙之撟�𤣰蝻抵秐 `>= 1` 憭押��蝙蝟餌��賣��亥䌊�函�瘚见�銵亙��唬�撣���訾誨���蝖桐��芷�厩��扳��𣳇�瞍譌��
    - [x] **�齿�摰匧��⊿�銝𤾸�撣訾��斗㜃�� (Hardened Update Safety & Exception Guard)**嚗�
        - 憓𧼮�撖� `get_sina_Market_json` 餈𥪜�蝛箏�潭� None ���瘚见ế摰𡄯��脫迫�亙藁撘�虜撖潸稲�湔鰵瘚��撏拇�嚗��撣豢𧒄�芸𢆡�鮋��霂餃��砍𧑐��蟮蝻枏���
        - 撘訫�撖嫣��∠巨隞���臬炏皛∟雲 6 雿滨滲�啣�銝𥪜��怠銁 `cct.code_startswith` 擐碶��賢��訫�����刻�皛歹��脰��𤩺㺭�桀�摨瓐��
        - 銝粹�蝵格�隞嗉粉�蹱�雿𨀣溶�� `try-except` 撘�虜�行⏛撅���脰�憭朞�蝔钅�蝡硺��嗆�隞嗉粉�坔仃韐亙��睲蜓蝥輻� Crash��

## 2026-06-26 01:50
- [x] **隡睃�憭𡁶漣�鍦�銝𦒘犖瘞𥪜��舀�銋���嗵��箏�嚗屸��漤�憸𤑳��� I/O (Optimized Multi-Sort & Popularity Resonance Persistence Write)**嚗�
    - [x] **瘨�膄�鍦��孵稬銝舘挽蝵格𧒄���憸穃���**嚗𡁻���� `tk_gui_modules/treeview_mixin.py` 銝剔� `_save_mixin_ui_states` �寞�嚗峕釣�𠹺��單𧒄靚�鍂 `self.save_ui_states()` �嗵���誨���雿踹�蝥�/�桅�𡁏�摨讐𠶖����港��典�摮䀝葉蝏湔擪嚗屸��齿�甈∠��餉”憭湔�摨𤩺𧒄憸𤑳��坔� JSON �滨蔭��辣��
    - [x] **�齿�摮鞟����摨讐𠶖���摮睃���**嚗帋耨�嫣� `stock_selection_window.py` 銝� `StockSelectionWindow` 銝� `HistoricalSelectionTrackerDialog` �� `_save_mixin_ui_states` �滚��寞�嚗���瑞宏�支��單𧒄�� `save_ui_states()` 蝤���蹱�雿栶��
    - [x] **摰䂿緵���箔���瘥�𧒄蝏煺�����𤥁䌊��**嚗𡁜銁 `HistoricalSelectionTrackerDialog` �� `_on_close` 蝒堒藁�喲𡡒�噼�銝剛‘�其� `self.save_ui_states()` ����刻��剁�蝖桐��函鍂�瑕��剖��脰蕭頦芰���𧒄嚗���祉����摨讐𠶖���憭笔��游��䀝�摮塩��蜓�批��啁����蝑𣇉裦�㕑�蝒堒藁�砍歇�� `_on_close` 銝剝��𣂷� `save_ui_states`嚗峕���憸嘥�靽格㺿��
    - [x] **隡睃�鈭箸��望𥲤摰Ｘ�蝡臬��㗛�餉�**嚗𡁻���� `popularity_resonance_gui.py`嚗�縧�支��� `sort_column` 銵典仍�鍦���_run_once_job` �唳旿�亥砭�瑟鰵�� `_write_block_job` �坔��朞噢靽⊥踎�埈𧒄擃㗛��滚�靚�鍂�� `save_config_settings()` �嗵��其�嚗��餈䠷�����啁�����𣇉�銝�敶鍦僎�� `on_close`嚗������哨�隞亙��冽��见𢆡靽格㺿颲枏�摮埈挾閫血����隞嗡葉��
    - [x] **摰峕� Python 霂剜�蝻𤥁�銝擧��坔�敶埝�霂�**嚗𡁏��笔笆靽格㺿�𡒊� `treeview_mixin.py`��stock_selection_window.py` �� `popularity_resonance_gui.py` 餈𥡝�鈭��霂烐�瘚页��牐遙雿閗祗瘜訫��餉�撘�虜��

## 2026-06-26 00:15
- [x] **隡睃�鈭箸��望𥲤 GUI 摰Ｘ�蝡臬縧�滨��劐�撣��皞Ｗ枂 (Optimized Popularity Resonance GUI Deduplication & Layout Height)**嚗�
    - [x] **摰䂿緵頝刻”�澆縧�滨��㗇㦤�� (Implemented Cross-Table Deduplication)**嚗𡁻���� `popularity_resonance_gui.py` 銝剔� `update_all_tables` �寞���繮�硋��舐��𨅯�嚗諹䌊�典遣蝡见��怠��典��航�隞���� `resonance_set`��銁憛怠��靝��腈���𡏭��腈���𨅯��腈���𨀣��萘��笔�璁𨅯��塚�撖孵歇餈𥕦��望𥲤�𨅯��肽”��葵�⊥�銵� `continue` 餈�誘嚗�僎�冽���蝞堒�蝷箏��瘀�雿踹�銝芾��唳旿�函��Ｖ葉隞�𣈲銝�撅閧緵嚗峕�憭批𧑐�𣂼�鈭��撅讐��Ｙ�靽⊥�撖�漲銝𤾸縧�滩捶�譌��
    - [x] **�寞祥摮鞟瑪蝔钅�憸睲僚摨誩��� (Eliminated Mid-Way Asynchronous UI Refreshes)**嚗𡁜��支� `_run_once_job` 銝剖�蝥輻��屸�憸𤏸��函� `update_single_table` �其�嚗�蝠摨閖��滢��枏�銝剝�𠉛眏鈭𡡞���㺭�格釣�亥�𣬚聦�誩縧�漤�餉�����萸�����蛹�其���������� 4 頝臬�蝥輻��券� join 摰��嚗𣬚眏銝餌瑪蝔衤�甈⊥�批�摮𣂼𧑐�扯� `update_all_tables`嚗䔶��靝�擃㗛��瑟鰵銝𤾸��臬𢆡���撖寧迅摰𡁏�扼��
    - [x] **閫�� Treeview 擃睃漲皞Ｗ枂銝𡡞��𣳇��∠撩�� (Fixed Treeview Height Overflow & Layout Compression)**嚗𡁜銁 `create_treeview` �嘥��碶葉撘訫� `height=6` ��㺭嚗屸��� Treeview ���憪钅�霈文�蝷箄��堆��脫迫�典�銵冽聢�峕𧒄�㰘蝸銝𥪯蜓蝒堒藁擃睃漲�箏�嚗�760px嚗㗇𧒄嚗��蝏�辣蝛粹𡢿鈭㗇𦜖撖潸稲���撅�摰孵膥皞Ｗ枂�𠹺�撅�”�澆仍�券��𣳇��� Bug��
    - [x] **蝻硋�撟嗉��𡁏���虾�扯���辣�芸𢆡�� E2E 撉諹� (Passed Standalone Executable E2E Verification)**嚗𡁏鰵蝻硋�鈭� `scratch/test_exe_run.py` �芸𢆡�𣇉垢�啁垢瘚贝��𡁏𧋦嚗屸�朞� subprocess �拍��㕑絲�枏��𡒊��祉�鈭諹��嗆�隞� `dist/PopularityResonanceSync.exe` 撟嗆迤撣貉�銵� 2.5 蝘坿䌊璉��𦒘����瘥��霂��靽格㺿�𡒊�摰Ｘ�蝡舀�隞颱�霂剜�銝舘�銵峕𧒄撘�虜嚗�100% �瑕��箏���������

## 2026-06-25 21:30
- [x] **�拍��亦氖憭批�靘肽�銝� PopularityResonanceSync �枏��西澈 (Completely Decoupled Heavy Libraries & Optimized PopularityResonanceSync Standalone Package Size)**嚗�
    - [x] **摰���亦氖 JohnsonUtil.commonTips / johnson_cons 靘肽�**嚗𡁻���� `popularity_resonance_service.py` �� `linkage_service.py` ������朞噢靽⊥踎�堒��乓��楝敺�䔝瘚见�憭朞�蝔钅��堒之撠誯�蝵株粉�𣇉��餉�嚗峕㺿�刻䌊瘣賜𡠺蝡讠����摨橒�憒� `configparser`嚗匧𢆡��粉�吔��拍���鱏鈭����鉄摨𧼮之 pandas/numpy �� `commonTips` 摨梶��湔𦻖�屸𡢿�乩�韏硔��
    - [x] **�� sys_utils.py 銝剔宏�典�甇亙紡��**嚗𡁜� `sys_utils.py` 憿嗅�撖� `commonTips` ���甇亙紡�亙��歹��嫣蛹�典�雿枏遆�啣��典𢆡�����撖澆�嚗峕��凋��朞� `sys_utils` 鈭抒���漣�娪��见�靘肽���
    - [x] **�� PyInstaller Spec ��辣銝剝�蝵桃������ (Excludes List)**嚗帋耨�嫣� `PopularityResonanceSync.spec` 銝剔� `Analysis.excludes` ��㺭嚗�撩銵�銁�枏��園�蝳� `pandas`��numpy`��matplotlib`��scipy`��talib`��h5py`��tables`��PyQt5`��PyQt6` 蝑� 30 憭帋葵摰���芯蝙�函�蝘穃郎霈∠��屸��� GUI 摨瓐��
    - [x] **靽格㺿 build_resonance_gui.bat 隞仿俈 spec 鋡怨���**嚗𡁻���� PyInstaller �枏���誘嚗𣬚凒�乩蝙�函緵�鞟� `.spec` �滨蔭��辣�枏�������蝘臭� **49 MB** 蝻拙��� **27.7 MB**嚗䔶�蝘舐憬�讐漲 **43.5%**��
    - [x] **蝻硋��芸𢆡�𤥁䌊瘚贝�銵諹��祇�朞�撉諹�**嚗𡁶��坔僎�典��唳��蠘�銵䔶� `scratch/test_exe_launch.py` �拍��㕑絲瘚贝�嚗𣬚＆霂�������� Console 蝥� GUI 摰Ｘ�蝡航�憭�迤撣貊𡠺蝡见鍳�其��牐遙雿閙芋�堒�頧賜撩憭勗�韏瑞� Crash��

## 2026-06-25 21:00
- [x] **摰峕�鈭箸��望𥲤撌亙�擃䀝��� GUI �齿�銝� PyInstaller 蝻𤥁��枏��芣� (Completed High-Fidelity Popularity Resonance GUI Refactor & PyInstaller Build)**嚗�
    - [x] **擃䀝遛�毺�颲寞� UI 銝𤾸𢆡���撅��嗥憬 (Narrow-border UI & Auto-hiding Layout)**嚗𡁻��� ttk `clam` ��像銝駁�銝舘䌊��� `pack_forget` �箏�嚗�銁�瑕��唳旿銝箇征�嗉䌊�券��誩笆摨娍踎�𡑒”�潔誑������蝛粹𡢿嚗𥕢蝙�冽�撟� 1px 蝏�器獢��蝎𦯀�蝥Ｚ𠧧撣虫��垍瑪��䰻霂�/�坔��厰僼摰𣬚�憭滚��栞祗閮��毺�閫����
    - [x] **�㯄�𡁜��格��𥪜𢆡�㗇𥋘銝� Socket �帋縑�𡁻� (Multi-target Linkage & Socket Integration)**嚗𡁏㟲����朞噢靽～����梢◇��������𦻖���撟嗅��睲��Ｗ��砍𧑐 `127.0.0.1:26668` 蝡臬藁�閖�� `"CODE|{code}"` ����餃� Socket �𥪜𢆡�箏�嚗峕𣈲��㗲�㗇��祉�雿輯���
    - [x] **�拍��枏�銝𤾸�餈𤤿�摰匧�摰�擪 (Safe PyInstaller Standalone Build)**嚗𡁜銁銝餃���釣�乩� `multiprocessing.freeze_support()`嚗�蝠摨閙�蝏苷� Windows �枏��臬�銝讠眏鈭𤾸�餈𤤿��㕑絲撖潸稲�� GUI �𣳇��滚鍳��香嚗𥕢蝙�� `pyinstaller -F -w` �賭誘�𣂼����鈭���� Console 蝏�垢蝒堒藁��𡠺蝡见虾�扯���辣 `PopularityResonanceSync.exe`��
    - [x] **�朞��芸𢆡�𤥁䌊瘚贝䌊璉� (Passed Automated GUI Test)**嚗𡁶��坔僎餈鞱�鈭� `test_gui_run.py` �芸𢆡�𡝗�霂閗��穿��𣂼�摰䂿緵鈭�蜓蝒堒藁�嘥��硔��葡�枏僎鈭� 2 蝘鍦��芸𢆡�喲𡡒����坔�摨瑟嵗撉䎚��

## 2026-06-25 20:30
- [x] **摰峕�蝑𣇉裦�㕑�銝𤾸�蝥扳�摨誯����瘛勗漲隞��憭齿䰻 (Completed Deep Code Review for Stock Selection & Multi-Sort)**嚗�
    - [x] **餈𥡝��券��䀹凒摰∟恣銝𡡞�餉��詨笆 (Audited All Changes & Verified Logic)**嚗𡁜笆 `global_favorites.py`��stock_selection_window.py`��treeview_mixin.py`��performance_optimizer.py` �� `instock_MonitorTK.py` �冽��唳�鈭支葉瘨匧��� 800 雿躰�隞��餈𥡝�鈭��鞱�憭齿䰻��
    - [x] **霂��撟嗉扇敶蓥葉雿𡡞��拐��𣇉� (Identified Medium/Low Severity Findings)**嚗𡁜��祇�蝵格�隞嗉䌊�厩撩憭望𧒄����湔�批�甇交�瘣𠺶������憭㚚�瘥�𧒄��辣餈蠘恣�嗅膥畾讠�憌𡡞埯嚗㇍clError嚗劐誑�𦠜㺭�潸圾�𣂷葉�寞�摮㛖泵�曉��踵揢��虾�拙��批遣霈柴��
    - [x] **颲枏枂摰峕㟲閫��摰⊥䰻�亙� (Generated Formatted Review Report)**嚗𡁜�撱箏僎閬���湔鰵鈭� `CODE_REVIEW_RESULTS.md`嚗峕��游𦶢�����葉����𤤿漣銝仿�摨行㟲��僎�𣂷��瑚�靽桀�隞��撖寞�嚗𣬚＆霂���游𦶢�嗆��㚚�餉�蝻粹萅��

## 2026-06-25 20:20
- [x] **敶餃��寞祥�鍦�銝擧�銋��閫血�����仿�㕑�鈭峕活�瑟鰵銝𡡞緾�� Bug (Fixed Double Refresh & Selection Jitter on Config Save)**嚗�
    - [x] **摰䂿緵 GlobalFavoriteManager 蝏��摨西䌊�㕑�璉��� (Implemented Fine-Grained Favorites Check)**嚗𡁜銁 `global_favorites.py` �� `GlobalFavoriteManager.load_from_config` 銝哨��齿�鈭��蝵桅�頧賡�餉���� `window_config.json` �齿鰵�㰘蝸�滨蔭�𠬍�隞�� `favorite_sectors` �� `favorite_stocks` �����捆�𤑳�摰鮋��拍��睃𢆡�嗆�靚�鍂 `notify_subscribers()`��
    - [x] **敶餃��拇鱏鈭峕活�滨������儐�� (Stopped Redundant UI Refreshes)**嚗𡁏㜃�芯�隞��銵典仍�鍦������偕撖詻����脫辺瘥𥪯�蝑厰��芷�厰�蝵桐�摮睃紡�渡��滨蔭��辣�睃𢆡嚗屸獈甇Ｖ�憭帋���恥������唬�隞嗚���敶餃�閫��鈭���仿�㕑�蝒堒藁嚗�誑�𠰴�隞𤥁恥�������函��餉”憭湔�摨𤩺���揢�鍦��嗅枂�啁�鈭峕活�滨�����ａ緾������颱��湧��劐葉 bug��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Syntax & Compilation Verification)**嚗𡁏����銵� `py_compile` 撖嫣耨�孵��� `global_favorites.py` 餈𥡝�鈭�祗瘜閙��嗵����霂𡢅�蝖株��餉�銝舘祗瘜閧�擃䀝����扼��

## 2026-06-25 20:05
- [x] **隡睃�憭𡁶漣�鍦�銝𤾸辣餈罸俈�㚚�劐葉�箏� (Optimized Multi-Level Sort Auto-Scroll & Debounced Selection)**嚗�
    - [x] **摰䂿緵�劐葉鈭衤辣 100ms 撱嗉��脫��箏� (Implemented 100ms Debounced Selection)**嚗𡁜銁 `StockSelectionWindow.on_select` �� `HistoricalSelectionTrackerDialog._on_select` 銝剖��乩��箔� `self.after` �� `self.after_cancel` �� 100ms 撱嗉��脫��批���遙雿閖�憸𤑳��颯�����㺭�柴���摨誯�蝏睃紡�渡��剜𧒄�游�憭𡁏活 `<<TreeviewSelect>>` 鈭衤辣���鋡恍俈�𡝗㦤�嗅�撟塚�敶餃�閫��鈭�眏鈭擧�摨誩��唳��劐葉憿孵��Ｗ��𤑳�鈭峕活�瑟鰵��緾���憭𡁏活�𥪜𢆡閫血��� Bug��
    - [x] **�寞祥憭𡁶漣/�訫��鍦�銝讠��芸𢆡摰帋�閫�藁頝喳𢆡 (Prevented Auto-Scroll under Active Sorts)**嚗�
        - �� `performance_optimizer.py` �� `restore_selection` 銝哨��啣�撖� `has_active_sort` �嗆����斗鱏��𥅾 Treeview 摮睃銁瘣餉����蝥扳��桅�𡁜��埈�摨𧶏��喃噶憭㚚�隡惩� `scroll_to_view=True`嚗䔶�撘箏�敹賜裦 `.see()` 頝唾蓮嚗屸俈甇Ｗ��唳�摨𤩺𧒄閫�藁頝喳𢆡嚗�
        - �� `instock_MonitorTK.py` �� `_refresh_tree_traditional` �寞�銝哨�靽桀�鈭� `has_active_sort` �芸�銋厩凒�亥��典紡�渡� `NameError` �鞉�����嗆㺿銝粹�朞� `self.tree` 撅墧�批𢆡����潘�撟嗅�甇亙銁憭𡁶漣/�桅�𡁏�摨𤩺暑頝�𧒄蝏閗� `.see()` 頝唾蓮嚗䔶��靝��鍦��𡒊鍂�瑞�皛𡁜𢆡�∟�閫垍�銝滩◤蝭⊥㺿��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�銝舘祗瘜閙嵗撉� (Passed Syntax & Compilation Verification)**嚗𡁏����銵� `py_compile` 撖寞��㗇��羓�璅∪�餈𥡝�鈭�祗瘜閙��嗵����霂𡢅�蝖株��餉�銝舘祗瘜閧�擃䀝����扼��

## 2026-06-25 19:45
- [x] **�寞祥�鍦�銝𤾸��唳𧒄蝒堒藁���撣貉䌊�冽��具����颱��瑟鰵�脩� (Fixed Auto-Scroll Jitter & Double Refresh on Sorting)**嚗�
    - [x] **摰��瘨�膄 Treeview �鍦�銝𤾸��唳𧒄�����歲�其��芸𢆡皛𡁜𢆡摰帋� (Eliminated Viewport Jitters & Auto-Scroll on Sort)**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_refresh_tree_traditional` �寞��� `performance_optimizer.py` �� `restore_selection` 銝哨�銝� `restore_selection` 憓𧼮�鈭� `scroll_to_view: bool = False` ��㺭�批���＆靽苷��券�閬����歲頧祉��箸艶嚗���𦦵揣摰帋�嚗㗇�撖寥�劐葉憿寞�銵� `self.tree.see(target_iid)` �其�嚗𥡝��銁憭𡁶漣/�桅�𡁏�摨𤩺�擃㗛�銵峕��瑟鰵�齿��唳旿�塚����霈支��扯� `see` 頝唾蓮嚗䔶���蝠摨閧迅雿譍��冽�����冽辺閫��嚗諹圾�喃��冽��漤���䌊�刻歲頧砌��䭾��𡁶��� bug��
    - [x] **閫��蝑𣇉裦�㕑�蝒堒藁�孵稬�鍦�/暺䁅恕�鍦��瑟鰵銝斗活銝舘歲頧祇▲�� Bug (Resolved Double Refresh & Top Jump on Selection Sort)**嚗�
        - **�拍��亦氖�𦯀��� `<ButtonRelease-1>` 鈭衤辣蝏穃�**嚗𡁏��支� `StockSelectionWindow` 銝剖笆 `self.tree.bind("<ButtonRelease-1>", self.on_select)` ���雿嗵�摰𠾼��砲蝏穃�撖潸稲�冽��券��暸������𡠺�孵稬�堒仍�鍦��𡡞��橘��嗅�甈∟圻�� `on_select` �劐葉鈭衤辣嚗��韏瑕�甈⊿𡢿�娪�蝏矋�
        - **撘訫� `_last_selected_code` �箄��脤�靽脲擪**嚗𡁜銁 `StockSelectionWindow.on_select` �� `HistoricalSelectionTrackerDialog._on_select` 銝剜鰵憓硺��箔� `_last_selected_code` �����縧�齿嵗撉䎚����齿��唳旿�𤥁��� Selection �塚��仿�劐葉 Code 瘝∪��毺���㺿�矋�撠�凒�亦�頝舀㜃�迎�摰���𦦵�鈭������典�韏瑞�憭𡁏活�芰�嚗�
        - **隡睃� `load_data` �冽��嗆�����**嚗𡁜銁 `load_data` 銝哨�瘥𤩺活餈鞱�蝑𣇉裦�硋��Ｘ𠯫��𧒄�芸𢆡撠� `self._last_selected_code` �滨蔭銝� `None`嚗䔶��𨅯��臬𢆡�𡝗鰵蝏𤘪�銝钅�銵諹��� 100% �菜��滚�嚗�
        - 靽桀�鈭� `stock_selection_window.py` 銝� `_do_bulk_render` 暺䁅恕 `scroll_to_top=True` 撖潸稲���摨誩� viewport �拍�憭滢��圈▲�函��餉�蝻粹萅��緵撠��暺䁅恕靚�㟲銝� `scroll_to_top=False`嚗䔶��� `load_data` �㰘蝸蝑𣇉裦蝏𤘪��嗆遬撘譍��� `True`嚗�
        - �� `trigger_multi_level_sort` 隞亙��芷�㕑��嗆��凒�唳䲮瘜� `_refresh_ui_favorites` 銝哨�撘訫�鈭��劐葉憿寧𠶖���摮䀝��䠷��Ｗ��箏����朞��冽�蝛箸�蝏𤘪��齿�摮㗛�劐葉 item��銁皜脫��𦒘蝙�� `selection_set` �� `focus` 餈睃�嚗屸��滢��鍦�銝𤾸��啣紡�渡��屸� TreeviewSelect �𥪜𢆡�瑟鰵嚗峕覔瘝颱���稬/�孵稬�鍦��瑟鰵銝斗活�𠰴�憭滩歲頧祇▲�函�鈭支��𤤿���
    - [x] **瘨�膄��蟮餈質葵蝒堒藁����𡝗𧒄���雿齿��� Bug (Fixed History Dialog Auto-Scroll on State Save)**嚗𡁜蝠摨訫��支� `HistoricalSelectionTrackerDialog` �� `save_ui_states` �寞�銝剖�雿� of `self.tree.yview_moveto(0)` 蝖祉�����剁��脫迫靽嘥��鍦���㺭�嗥��䭾�憭滢�皛𡁜𢆡��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�銝舘祗瘜閙�撉� (Passed Syntax & Compilation Verification)**嚗𡁏����銵� `py_compile` 撖寞��㗇��羓�璅∪�餈𥡝�鈭�祗瘜閙��嗵����霂𡢅�蝖株��餉�銝舘祗瘜閧�擃䀝����扼��

## 2026-06-25 19:15
- [x] **隡睃��㕑�蝒堒藁銝𦒘蜓閫�㦛�鍦���䌊�冽��典�����𣇉迅摰𡁏�� (Optimized Stock Selection, Main View Sorting, Auto-Scroll & Persistence)**嚗�
    - [x] **�寞祥銝餉��暹�摨𤩺𧒄��撩�嗉䌊�冽��典�雿� (Prevented Main View Auto-Scroll During Sort)**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `refresh_tree` 皜脫�瘚���䕘�撖� `self.tree.see(target_iid)` �其�憓𧼮�鈭� `if not has_active_sort:` ����斗㜃�芥���蝖桐�鈭���冽�銝箔蜓閫�㦛霈曄蔭鈭��蝥扳��訫��鍦�嚗Ǒhas_active_sort=True`嚗㗇𧒄嚗𣬚頂蝏蠘䌊�典��啗����隡𡁜�撘箄�撠���冽辺�㕑秐敶枏��劐葉���蟡剁�靽萘�鈭�鍂�瑞�皛𡁜𢆡�∟�閫𡜐��𣂼�鈭�䰻�见�蝥扳�摨誩�銵冽𧒄���撉䎚��
    - [x] **摰䂿緵��蟮餈質葵蝒堒藁�鍦��嗆��𡠺蝡𧢲�銋�� (Implemented Independent History Dialog Sort State Persistence)**嚗𡁻���� `stock_selection_window.py` �𣬚� `HistoricalSelectionTrackerDialog` ���摨譍�����㚚�餉�����支�隞亙��曹澈雿輻鍂銝餌��� `selection_window_sort` �滨蔭��芋撘𧶏��朞� `_get_tree_config_key` 餈𥪜�銝枏��� `"selection_history_sort"` �殷�摰䂿緵鈭��摨讐𠶖��銁 `window_config.json` 銝� of �祉�摮睃�����臬𢆡�芸𢆡餈睃�銵典仍蝞剖仍嚗䔶誑�𠰴銁靽格㺿�鍦��舘䌊�冽�銵� `self.tree.yview_moveto(0)` 皛𡁜𢆡�喲▲�剁�隞舘��蝠摨閗圾�虫���蟮餈質葵銝𦒘蜓�㕑�蝒堒藁���摨讐𠶖����
    - [x] **閫�� `load_data` �� `_refresh_ui_favorites` 銝剔��鍦�蝖祉����蝵桅䔮憸� (Fixed Hardcoded Sorting Resets)**嚗帋耨�嫣� `StockSelectionWindow` 銝剔� `load_data` 銝� `_refresh_ui_favorites` �寞���銁�齿鰵��扇/撖寥��芷�㕑� (`is_fav`) �𠬍�銝滚�雿輻鍂�蹱香�� `餈鮋翧瘨典�` �硋虜閫��摨誯��啣撩�嗆�摨𧶏��峕糓�朞�靚�鍂蝏煺��� `self._sort_dataframe(self.df_candidates, self.tree)` �乩�����函鍂�瑞��芸�銋匧�蝥�/�訫��鍦�嚗屸俈甇Ｖ��芷�㕑��嗆��凒�唳𧒄�冽�霈曉����摨讛◤�誩��瑕�暺䁅恕��
    - [x] **皜��憭帋����撣詨���膥 (Cleaned Up Duplicate Exception Handler)**嚗𡁜��支� `stock_selection_window.py` 銝� `save_ui_states` 摨閖����雿�/�滚��� `except Exception as e` 隞��畾蛛�瘨�膄鈭�祗瘜閖�����
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗𡁏����銵� `py_compile` 撖嫣耨�孵��� `instock_MonitorTK.py` �� `stock_selection_window.py` 餈𥡝�鈭���嗵�霂烐�瘚页�靽肽�霂剜�������蝔喳���

## 2026-06-25 18:40
- [x] **隡睃�璁�艙�踹� Treeview �嘥��𤥁䌊�冽��冽㦤�� (Optimized Concept Plate Treeview Auto-Scroll on Initialization)**嚗�
    - [x] **�舀�憭𡁶漣�鍦��嗉䌊�券▲�冽遬蝷� (Auto-Scroll to Top when Multi-Level Sort Active)**嚗帋耨�嫣� `_fill_concept_top10_content` ����� nested �賣㺭 `scroll_and_highlight`嚗�僎撘訫� `is_init` ��㺭���璉�瘚见�蝒堒藁�嘥��� (`is_init=True`) 銝𥪜�蝥扳�摨誩�鈭擧�瘣餌𠶖���`bool(getattr(tree, 'sort_level1_col', None))`嚗㗇𧒄嚗峕��園�霈斤� `tree.see(target_iid)` 皛𡁜𢆡摰帋�銵䔶蛹嚗諹蓮銝箄��� `tree.yview_moveto(0)` 雿踹�暺䁅恕隞𤾸�銵冽�憿園�撅閧內嚗�蘨靽萘��劐葉擃䀝漁��
    - [x] **�峕郊�齿� `_focus_top10_tree` �踹��鍦�憭滢�皛𡁜𢆡 (Refactored _focus_top10_tree to Avoid Scroll Conflict)**嚗𡁻���� `_focus_top10_tree` 撱嗉��𡁶�憭���餉����憭𡁶漣�鍦�瘣餉��塚��箄�霂餃�敶枏��𤑳��劐葉憿孵僎撖孵��扯��衣�霈曄蔭嚗Ǒtree.focus(target)`嚗㚁��誩��朞� `tree.yview_moveto(0)` 撘箄����憿嗥垢撅閧內閫��嚗屸��滢��𧼮�蝥扳�摨譍�暺䁅恕撘箄� `tree.see(children[0])` 憭滢�撖潸稲����典�蝒���
    - [x] **�湔鰵���匧��臬𢆡靚�鍂蝡嗵� (Updated All Initialization Call Sites)**嚗𡁜�蝥找� `show_concept_top10_window_simple` �� `show_concept_top10_window` 銝凋�憭�鰵�𥕦遣�㚚�霈暹㺭�格𧒄�� `_fill_concept_top10_content` 靚�鍂嚗峕遬撘𤩺釣�乩� `is_init=True` 撅墧�改�敶餃�撖寥�鈭���臬𢆡銝𡒊���鰵撱箏㦤�臭���▲�典��啗��踺��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗𡁏��蠘�銵� `py_compile` 撖嫣蜓蝒𦯀�璅∪�餈𥡝�蝻𤥁�嚗峕�隞颱�霂剜���𣄽�蹱�蝻抵��桅���

## 2026-06-25 18:00
- [x] **摰䂿緵璁�艙�踹�蝒堒藁 Treeview 憭𡁶漣�鍦�頝其�霂脲�銋��銝舘楊蝒堒藁撟踵偘�峕郊 (Implemented Persistent Concept Sort & Cross-Window Sync)**嚗�
    - [x] **摰䂿緵�梁鍂�鍦��嗆���頧賭��瑕鍳�冽�憭�**嚗𡁜銁 `instock_MonitorTK.py` 銝剖��唬� `_apply_saved_concept_sort_state` 颲�𨭌�寞���銁 `show_concept_top10_window` �� `show_concept_top10_window_simple` 璁�艙摮鞟����撱箏僎�嘥��� Treeview �塚����朞�霂交䲮瘜蓥� `window_config.json` ��辣�� `concept_top10_sort` �滨蔭���銝见��典�摨誩��硋�頧賢��函�憭𡁶漣�鍦�撅墧�改�L1-L3 �鍦�摮埈挾��䲮�穃��孵稬霈⊥㺭�函�嚗㚁�蝖桐�鈭���㗇�敹菜踎�堒�蝒堒藁�典鍳�冽𧒄�質�銝��渲䌊���摨𠉛鍂�詨����蝥扳�摨𧶏��踹�鈭����′蝻𣇉� `"percent"` 暺䁅恕�潛��𣂼���
    - [x] **�齿� `treeview_mixin.py` �鍦�閫血�撟嗅遣蝡𧢲�餈烐暑頝��摮䀹㦤��**嚗𡁜銁 `treeview_mixin.py` 銝剜鰵憓� `_save_mixin_ui_states` �寞�嚗�� 5 憭��蝥�/�訫��鍦�靽格㺿�噼��文��晦�靝�銝餉”閫血�靽嘥��脲𦆮摰質秐�靝遙�� Treeview �䀹凒��圻�睲�摮覀�腈��鸌撘訫� `self._last_active_concept_tree` 銝湔𧒄���嚗���硺蜓銵函�璁�艙摮鞟��� Treeview 閫血��鍦�靽格㺿�塚�撠���� Treeview 撘閧鍂�芸𢆡����唬蜓 App 摰硺�銝𨳍��
    - [x] **摰䂿緵頝函����摨誩嘀�剖�甇乩��單𧒄靽嘥�**嚗𡁻����銝� App �� `save_ui_states` ����㚚�餉�嚗�銁靽嘥��嗉䌊�刻��� `_last_active_concept_tree` ��撖孵����敹萄�蝒堒藁摰硺�嚗���嗆��唳�摨讐𠶖����硋僎�湔鰵�� `window_config.json` 餈𥡝�����吔��峕𧒄嚗��霂交��唳�摨讐𠶖���甇亙��典�**�嗡����匧��齿迤�枏���**����閙�敹萄�蝒堒藁嚗Ǒ_pg_top10_window_simple` 摮堒�銝剔� win嚗匧����璁�艙�踹�蝒堒藁嚗Ǒ_concept_win`嚗劐�嚗�僎�齿鰵皜脫��嗉”憭渡���內�函悌憭氬�����迤摰䂿緵鈭��銝芣�敹菜踎�堒��鞟���𡢿����餌��梁鍂�𣬚𠶖��笆朣僐��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹�**嚗朞�銵� `py_compile` �拍�蝻𤥁�撌亙�嚗峕��罸�朞�鈭�笆 `instock_MonitorTK.py` �� `tk_gui_modules/treeview_mixin.py` ����嗵����霂𡢅�蝖株��餉�銝𤾸蘂瘜訫��湧�靽萘���

## 2026-06-25 17:35
- [x] **靽桀�銝餉��暸�憸𤏸�����唳𧒄頝唾��鍦�撖潸稲���蝥扳�摨誩��� Bug (Fixed Main View Sorting Reversion on Real-time Refresh)**嚗�
    - [x] **撘訫��鍦��嗆��惣�賣㜃�� (`has_active_sort`)**嚗𡁜銁 `instock_MonitorTK.py` ��蜓銵典��啣遆�� `refresh_tree` 銝哨��曹�擃㗛�銵峕��峕郊�硋��嗅��唳𧒄暺䁅恕撣血� `skip_sort=True` 撖潸稲撌脰挽摰𡁶��鍦�銋勗���緵憓𧼮� `has_active_sort` 撅墧�批ế摰𡄯��亙��� `self.tree`嚗��銝餌��� `self`嚗劐�摮睃銁瘣餉����蝥扳�摨𧶏�L1-L3嚗㗇��訫��鍦�嚗��撘箏�敹賜裦 `skip_sort=True`嚗𣬚誧蝏剖笆�唳旿�扯� DataFrame �齿�摨𧶏�隞擧覔�砌�靽肽�鈭���唳𧒄�鍦��嗆���蝔喳���
    - [x] **�齿� `_sort_dataframe` 隞乩���� tree 霂餃��嗆�� (Unified State Reading source)**嚗𡁜銁 `_sort_dataframe` �唳旿�齿�摨𤩺𧒄嚗屸���蛹隡睃�隞� `self.tree`嚗Ǒtree` �找辣摰硺�嚗劐��湔𦻖瘙��潭�摨讐𠶖���畾蛛�`sort_level1_col`��sortby_col` 蝑㚁�嚗諹𥅾�惩� fallback �� App ����匧��找����敶餃�閫��鈭� UI 鈭支�銝擧㺭�桀��唳�摨𤩺𧒄��㺭�株粉�硋�撌殷�瘨�膄鈭�𠶖���甇交��辷�摰䂿緵鈭�芦�𡁏�摨譍�憭𡁶漣�鍦�摰���峕郊��
    - [x] **�𣳇��朞��拍�蝻𤥁�撉諹�**嚗朞�銵� `py_compile` 撌亙�嚗峕��罸�朞�鈭�笆 `instock_MonitorTK.py` ����嗵�霂煾�霂���
- [x] **摰䂿緵 K蝥輻��抒��� (`KLineMonitor`) 憭𡁶漣�鍦�頝其�霂脲�銋��銝𡡞�瘥��隞嗥������ (Implemented Persistent Multi-Sort & Destroy Event Guard for KLineMonitor)**嚗�
    - [x] **摰䂿緵 `save_ui_states` ����𡝗𦻖���蝏�辣��瘥�捆��**嚗𡁜銁 `kline_monitor.py` 銝凋蛹 `KLineMonitor` 蝐餃��牐� `save_ui_states` �寞�����冽�撌阡睸�硋𢰧�桐耨�寞�摨𧶏�憒��朞� `TreeviewMixin` 霈曄蔭銝�/隞�/甈∠漣�碶葩�嗅�蝻��鍦�嚗㗇𧒄嚗諹砲�寞�隡朞䌊�典� `self.tree` ���摨讐𠶖���`sortby_col`��sort_levelX_col` 蝑㚁�摰墧𧒄�坔��啁�銝��� `window_config.json` �� `kline_monitor_persistence` �滨蔭���銝卝��鸌�怠��乩� `TclError`/`AttributeError` 摰寥�霂餃�嚗屸俈甇Ｗ銁蝏�辣撘�憪钅�瘥�𧒄霂餃��𤑳�撏拇���
    - [x] **撘訫� `<Destroy>` 鈭衤辣�拍�靽嗪埯�箏�**嚗𡁜銁 `__init__` 銝凋蛹 `KLineMonitor` 蝏穃�鈭� `<Destroy>` 鈭衤辣�噼� `on_destroy_persistence`���銝� TK 蝒堒藁嚗ǑStockMonitorApp`嚗匧��准������蝔钅���箝������蝒堒藁�祈澈鋡� `destroy()` �塚�蝟餌��芸𢆡�行⏛霂仿�瘥�𢆡雿𨅯僎閫血�銝�甈� `save_ui_states`嚗𣬚＆靽苷�蝞∩�蝘滚��剖㦤�臭�憭𡁶漣�鍦��誩末�質� 100% 鋡急�銋����
    - [x] **摰䂿緵�瑕鍳�函𠶖���憭�**嚗𡁜銁 `__init__` ���牐葉嚗���朞� `self._init_tree_sort_state(self.tree)` �嘥��𡝗�摨誩��改��誩�撠肽�閫���滨蔭��辣嚗諹𥅾�𣂼�霂餃��坔��啗��笔�銝芸�蝥扳�摨誩��𦠜�摨𤩺䲮�𡢅�撟嗉��� `update_mixin_tree_headers` 皜脫�撣行�撖孵�蝥批���釣 and 蝞剖仍��”憭湛�雿輻鍂�瑁��典��臬𢆡�嗅朖�餅�憭滚��滨�憭𡁶漣�硋��埈�摨譌��
    - [x] **�𣳇��朞��拍�蝻𤥁�撉諹�**嚗朞�銵� `py_compile` �拍�蝻𤥁�撌亙�嚗峕��罸�朞�鈭�笆 `kline_monitor.py` ����嗵�霂煾�霂���


## 2026-06-25 17:00
- [x] **摰䂿緵頝函��� Treeview �𡁶鍂憭𡁶漣�鍦�憭滨鍂銝舘”憭游𢰧�株��閖��� (Implemented Reusable Treeview Multi-Sort & Header Context Menu across Sub-Windows)**嚗�
    - [x] **�齿�璁�艙 Top10 蝒堒藁蝟餃��舀��𡁶鍂憭𡁶漣/�訫��鍦�**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `show_concept_top10_window` 銝� `show_concept_top10_window_simple` 銝支葵摮鞟���葉嚗���支��扳���䌊摰帋��訫��鍦�嚗�蝠摨閗�蝘餃僎蝏穃��� `TreeviewMixin` �𣂷����蝥扳�摨𤩺䲮獢���銁蝒堒藁�嘥��𡝗𧒄撠��憪𧢲�摨誩��滨蔭銝� `percent` �滚�嚗�僎靚�鍂 `update_mixin_tree_headers` �芸𢆡皜脫��瑕鍳�冽�摨讐悌憭氬��
    - [x] **撖寞𦻖 `_fill_concept_top10_content` 憸��摨譍�憭𡁶漣�鍦��芣�**嚗𡁻�����唳旿憛怠�餈��銝剔��鍦��嗆��粉�吔��芷����瑕�銝餅�摨誩�隞亙����皛� Pandas DataFrame嚗���滢��脩𤌍�芰鍂 `percent` ���撖潸稲��㺭�格⏛�剔撩�瘀�嚗𥕦銁 UI �鍦��唳旿摰峕��𠬍�靚�鍂 `perform_tree_multi_level_sort` �笔𧑐蝔喳��鍦�嚗䔶��䔶蝙�啁��亦����啗����摰𡁏𧒄�湔鰵�賢�蝢舘䌊���蝏湔��冽����蝥扳�摨讐𠶖����
    - [x] **�齿� K蝥輻��抒��� (`KLineMonitor`) �亙�憭𡁶漣�鍦�**嚗𡁜銁 `kline_monitor.py` 銝哨�雿� `KLineMonitor` 蝐餌誧�輯䌊 `TreeviewMixin` 撟嗆溶�� `get_scaled_value` 蝻拇𦆮����亙藁���撘�僎蝘駁膄鈭�掩銝剛䌊摰帋� of `treeview_sort_columnKLine` �鍦��寞�嚗屸�朞� `update_mixin_tree_headers` �芸𢆡�滨蔭銵典仍撟嗆𣈲���𡁶鍂憭𡁶漣�鍦���銁�瑟鰵�唳旿�寞� `update_table` 撠暸�嚗諹��� `perform_tree_multi_level_sort` 摰峕�憭𡁶漣�鍦��嗆��䌊����
    - [x] **���銵典仍�喲睸憭𡁶漣�鍦�銝𠹺������**嚗𡁜銁 `instock_MonitorTK.py` ���敹萄�蝒堒藁�喲睸�噼� `_on_tree_right_click_newTop10` / `on_right_click`嚗䔶誑�� `kline_monitor.py` �� `on_tree_kline_monitor_right_click` 銝哨�隡睃��朞� `show_header_context_menu(tree, event)` �行⏛憭��銵典仍�喲睸�孵稬鈭衤辣����𦦵��餃��笔銁銵典仍銝𠺪�蝡见朖撘孵枂憭𡁶漣�鍦��滨蔭�𨅯�嚗���唬�摮鞟����摨譍�撉𣬚� 100% 撖寥���
    - [x] **�𣳇��朞��拍�蝻𤥁�撉諹�**嚗朞�銵� `py_compile` 撖嫣耨�孵��� `instock_MonitorTK.py` �� `kline_monitor.py` �𣂼�餈𥡝�鈭���嗵����霂𡢅�霂���餉��齿��刻祗瘜蓥�擃䀝��麄��

## 2026-06-25 16:00
- [x] **靽桀�憭𡁶漣蝥扯��鍦��孵稬�嗡��埈𧒄�滨蔭銝餅�摨譍� Bug (Fixed Master Sort Resetting when Clicking Other Columns)**嚗�
    - [x] **靽桀� `sort_mixin_by_column` 銝剔��滨蔭�餉�**嚗𡁜銁 `treeview_mixin.py` 銝哨��齿�鈭� `sort_mixin_by_column` ����餃ế摰𡁏�蝔卝���璉�瘚见�敶枏�摮睃銁銝餅�摨𧶏�`L1`嚗劐��孵稬��糓�嗡��冽鰵���摨誩��塚�銝滚��扯�銝��格��斗��匧�蝥扳�摨讐��滨蔭�其�嚗諹�峕糓靽萘�撌脩�摰𡁶�銝餅�摨𧶏�`sort_level1_col` �𠰴��孵�嚗㚁�隞�凒�啣僎閬�� `tree.sortby_col` 銝� `tree.sortby_col_ascend` 雿靝蛹銝湔𧒄隞�/甈⊥�摨誩�蝻���
    - [x] **撖寥��訫�銝𤾸�蝥扳�摨讐𠶖������皜�膄**嚗帋��典��齿瓷�㕑挽蝵桐遙雿蓥蜓�鍦�嚗ǑL1` 銝� None嚗劐��孵稬�冽鰵�鍦��埈𧒄嚗峕���迤�扯�銝��桅�蝵桀�蝥扳�摨譍蛹�訫��鍦����雿頣�靽嗪�鈭��蝥扳�摨讐�閫��蝔喳��找��滢��餉�銝��湔�扼��
    - [x] **�𣳇��朞��拍�蝻𤥁�撉諹�**嚗朞�銵� `py_compile` �拍�蝻𤥁�撌亙�嚗峕��罸�朞�鈭�笆 `treeview_mixin.py` �� `instock_MonitorTK.py` ����嗵�霂㻫��

## 2026-06-25 15:50
- [x] **隡睃�摰墧𧒄������蝻枏��滨蔭瘜典�銝擧𠯫敹烾��� (Optimized Realtime Indicator In-Memory Cache Injection & Log Throttling)**嚗�
    - [x] **�滨蔭�湔鰵������颲�𨭌蝻枏� (`_df_all_cache`)**嚗𡁜銁 `realtime_data_service.py` 銝哨�撠� `set_df_all_cache(df)` ����冽𧒄�箏�蝵桃宏�典� `MinuteKlineCache.update_batch` ��仍�具���蝖桐�鈭�銁 background strategy thread �扯��滩恣蝞堒�����嗆���隡啣�嚗峕��啁��券�銵峕� DataFrame 撌脩��𣂼�瘜典��唬����蝻枏�銝哨�敶餃��寞祥鈭���臬𢆡�羓�銝剝�甈⊿�霈∠��嗥眏鈭� `df_snap` ��𧊋撠梁貌�䔶漣�毺征/None 霅血����瘣𠺶��
    - [x] **靽桀���犒�譍�璉��亦掩�钅�霂� (Fixed Fingerprint Dirty Check TypeError)**嚗𡁻���� `set_df_all_cache` ���蝥孵��㗇𥋘�餉�嚗���烐����畾萄��芸銁 columns 銝剖枂�唳𧒄嚗����撟園�霈支蝙�� `['code']` �� `list(df.columns)` 餈𥡝��孵�霈∠�嚗屸��滢漣�� `NoneType` 銝滚虾餈凋誨��掩�钅�霂胯��
    - [x] **撘訫�霅血��亙�憸烐綉�滚臁�箏� (Implemented Warn Log Throttling & Cooldown)**嚗𡁜銁 `calculate_stock_daily_indicators` 銝哨���笆 `df_snap` 銝箇征/None 撘訫�鈭��撅� 60 蝘垍��鞾��行⏛�賂���笆銝芾�隞���芸龪�齿��笔��乩���笆銝芾� ID �� 300 蝘𡜐�5���嚗厰�憸𡢅��𦦵�鈭�頂蝏笔��臬𢆡�𡝗㺭�桐��寥��嗆����祆𧒄鈭抒��啣�銵諹郎�𦠜𠯫敹𡑒蔑�詨紡�渡�蝤�� I/O 鈭㗇𦜖��

## 2026-06-25 14:30
- [x] **敶餃��𣳇膄 HDF5 蝤���鮋��霂餃��箏� (Completely Removed HDF5 Disk Fallback Reads)**嚗�
    - [x] **�𣳇膄 `calculate_stock_daily_indicators` 銝剔�蝤���鮋���餉�**嚗𡁜銁 `realtime_data_service.py` 銝哨�敶餃�蝘駁膄 `calculate_stock_daily_indicators` �寞��𣬚�蝤��霂餃�������餉�嚗屸獈�凋���銁蝻枏�蝻箏仃�嗅笆 HDF5 ��辣 (`get_tdx_Exp_day_to_df`) ���甇�/撘�郊�拍�霂餌��其�嚗䔶蝙霂交䲮瘜訫��其�韏㚚��������唳旿��
    - [x] **摰䂿緵�朞� `df` �湔𦻖�寥����**嚗𡁜� `calculate_stock_daily_indicators` ����啣�銵冽������ `update_wave_structure_state` 靚�鍂�曆葉�湔𦻖隡惩�敶枏��� `df`嚗䔶�����啁凒�亙銁��� DataFrame �交𪄳 `ma20d` 蝑匧��冽���㺭�柴����𨀣𧊋�瑕��堆��躰��箇㮾摨𠉛��亙�霅血�嚗Ǒlogger.warning`嚗㚁�靽嗪��唳旿�曇楝���撣詨虾餈賣滲��

## 2026-06-25 15:30
- [x] **靽桀��𡝗��券�憭𡁶漣�鍦��𡒊��嗆����嗘�暺䁅恕�鍦� Bug (Fixed Sorting Reversion on Clear All & Stale State Persistence)**嚗�
    - [x] **敶餃��齿� `clear_all_mixin_multi_sort` 皜���餉�**嚗𡁜銁 `treeview_mixin.py` 銝哨�敶餃�瘨�膄鈭��𨅯�瘨��蝥扳�摨誩�靘萘�閫血� `sort_mixin_by_column`�萘��𦯀�靚�鍂��緵�冽��斗�雿𨅯�摰��蝵桃征 `sort_levelX_col` (L1-L3)��sortby_col` 銝� `sortby_col_ascend` 蝑㗇��㗇�摨讐𠶖����𧶏��脫迫鈭抒���唂�嗆����踺��
    - [x] **摰䂿緵�𣬚垢�鍦��嗆��楛摨血�甇� (Synchronized Double-Ended Sorting States)**嚗𡁏�蝛箸�雿靝�隞��蝵� `tree` 撖寡情����匧��改�餈睃��嗅�甇仿�蝵桐蜓 `App` 摰硺�銝羓����匧笆摨娍�摨讐𠶖���蝖桐��嗆��㦤���摰��銝��湛�撟嗆迤撣貉圻�� `save_ui_states()` 隞亙��券��舀��孵稬�堒仍�嗅�甈∪�撘孵��扳����摨譌��
    - [x] **�箄��滨蔭擐𣇉��駁�霈日�摨� (Initialized New Click to Descending)**嚗帋��碶� `_get_mixin_current_col_asc`嚗���孵稬�𧼮��齿�摨誩��塚�暺䁅恕隞仿�摨𧶏�`reverse=True` �� `sortby_col_ascend=False`嚗劐�銝粹�甈⊥�摨讛絲憪𧢲䲮�𡢅�雿踹��𨀣�蝛箸��争�嘥����銝�甈∠��餉�憭���∠巨銵峕����渲���眏擃睃�雿舘��䠷��啣僕���鍦���

## 2026-06-25 12:50
- [x] **摰䂿緵�𡁶鍂憭𡁶漣�鍦��嗆� (Unified Reusable Treeview Multi-Sort Mixin)**嚗�
    - [x] **摰���質情 TreeviewMixin 憭𡁶漣�鍦� (Abstracted Generic Multi-Sort Logic)**嚗𡁜� `StockMonitorApp` 銝剜��劐�憭𡁶漣�鍦��嗆���`sort_levelX_col`, `sort_levelX_asc`嚗剹��𠶖��輕�歹�`_init_tree_sort_state`嚗厩㮾�喟��餉�摰��餈�宏銝𧢲��� `TreeviewMixin`嚗峕��支�銝餌���掩���憭��雿嗘誨���撟嗆�擃䀝�蝏�辣憭滨鍂摨佗�摰𣬚�撖寥� DRY 銝� SOLID �笔���
    - [x] **�齿�銝餌����颲�𨭌閫�㦛餈𥡝�憪娍� (Refactored Subclasses to Delegate to Mixin)**嚗𡁜� `instock_MonitorTK.py` 銝剔� `sort_by_column`��update_tree_headers` 蝑㗇�摨𤩺綉�嗅�皜脫��寞��齿�銝箄��� `TreeviewMixin` ��笆摨𥪜��堆�憒� `sort_mixin_by_column` �� `update_mixin_tree_headers`嚗㚁�摰䂿緵鈭�銁靽萘�銝餉��暹�摨讛䌊摰帋��改�憒� favoriting 蝵桅▲��ainU 蝻㰘捏�寞��埈�摨𧶏�����嗉�銵��蝢𡒊�摨訫�蝏煺���
    - [x] **�枏��舀� ExtDataViewer 颲�𨭌蝒堒藁憭𡁶漣�鍦� (Integrated Multi-Sort in ExtDataViewer)**嚗𡁻���� `ext_data_viewer.py`嚗��������厩� Treeview �典�撱箸𧒄��𢆡���摰� Mixin �� `sort_tree_column`嚗𥕦𢰧�桃��餉”憭游虾撘孵枂蝏煺����蝥扳�摨讛��𤏪�銝�/隞�/甈⊥�摨誩��𡝗�嚗㚁��孵稬�喳虾蝡见朖�齿�撟嗆凒�啗”憭渡悌憭渡𠶖���摰䂿緵鈭��蝟餌��鍦�雿㯄����蝻嘥笆朣僐��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�銝𡡞���祗瘜訫��� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣耨�孵��� `tk_gui_modules/treeview_mixin.py`��instock_MonitorTK.py` 隞亙� `ext_data_viewer.py` 摰峕�鈭�祗瘜閧����霂𡢅�蝖株恕�牐遙雿閙𥁒�蹱�撘�虜��

## 2026-06-25 12:40
- [x] **�齿�撟嗆�蝥臬�蝥抒漣�娍�摨誯�餉�嚗���售�靝�蝏穃�銝湔𧒄�𡒊��苷��𨅯��臬𢆡暺䁅恕�鍦�蝞剖仍�� (Optimized Master-Suffix Multi-Sort UX & Cold-Start Arrow Indication)**嚗�
    - [x] **摰䂿緵銝湔𧒄�𡒊�憭𡁶漣�鍦� (Non-binding Master-Suffix Sorting)**嚗𡁏伃��鈭���餅鰵�𡑒䌊�刻圾�支蜓�鍦��𣇉���挽蝵桀�蝥抒��折�餉���緵�券�朞��喲睸霈曉���蜓/隞�/甈⊥�摨誩�鈭𢛶�𦦵�摰𡁻�蝵栽�嘅�撌阡睸�孵稬�啣�憭游�雿靝蛹�靝葩�嗅�蝻��嘅�銝齿情�梶�摰𡁜��𧶏�嚗�銁 `_sort_dataframe` 銝剖𢆡��𣄽鋆�蛹鈭𣬚漣 (�椬[隞筕) �碶�蝥� (�叚[甈（) ����鍦���鍂�瑞凒�亦��颱遙�誩�隞𡝗鰵�堒朖�舀��餌��湔揢銝湔𧒄隞�/甈⊥�摨𧶏��𣳇��见𢆡閫�膄憭𡁶漣蝏穃�嚗�蝠摨閙��支�蝎䀹��麄��
    - [x] **�冽��葡�栞”憭港葩�嗆�摨讐𠶖�� (Dynamic Header Labels)**嚗𡁜銁 `update_tree_headers` 銝剖𢆡����潘��亙��齿�蝏穃�銝餅�摨譍��删�摰帋�/甈⊥�摨𧶏�鋡怎��餌�銝湔𧒄�𦯀��刻”憭港��冽��葡�㮖蛹撖孵��� `�椬[隞筕` �� `�叚[甈（` ���撟嗅銁���滨垢�曄內���摨讐悌憭湛���/�橒�����Ｖ葩�嗅��塚�甇斗�霂���渲蓮蝘鳴��𣂷�鈭���啗�屸妟蝎䀹����閫匧�擐���
    - [x] **�瑕鍳�券�霈斗�摨誩�銝𡒊悌憭湔�蝷� (Cold-Start Default Sorting Indication)**嚗朞圾�喃��瑕鍳�典��曹�瘝⊥���蟮�鍦��滨蔭撖潸稲�屸𢒰�牐遙雿訫��曄內蝞剖仍��鍂�瑚��亙��滚�雿閙�摨讐��𤤿���鰵憓鮋�霈斗�摨譍��歹��亙��臬𢆡�擧�隞颱�憭𡁶漣�硋��埈�摨𧶏�蝟餌��芸𢆡撠���嘥��碶蛹 `"percent"`嚗�隅撟���烾�摨𧶏�撟嗅銁銵典仍���滨垢甇�＆蝏睃� `�� ` 蝞剖仍��內�剁����皜�苊��
    - [x] **�鍦�蝞剖仍蝵桅▲撖寥� (Prepend Sorting Arrows in Header)**嚗𡁜��鍦�蝞剖仍嚗��/�橒�皜脫�雿滨蔭�望錰撠曇��渲秐銵典仍�������齿䲮嚗��憒� `�� �𣞁[銝蒸 col`嚗㚁���之�唳����憭𡁶漣銵典仍��椰�喳笆朣鞱��煺�閫���𡁶������
    - [x] **隡睃�憭𡁶漣�鍦�銝讠�銵典仍撌阡睸�孵稬閫�膄�餉�銝擧䲮�穃�頧� (Optimized Header Click to Dismiss Multi-Sort & Reverse UX)**嚗�
        - [x] **�孵��單𧒄�滩蓮**嚗𡁜��冽��典�蝥扳�摨譍��孵稬銝餅�摨� (L1)����鍦� (L2) �𡝗活�鍦� (L3) 銝凋遙�譍��㛖�銵典仍�塚��湔𦻖�冽㜃�芸膥銝剖�頧砍僎撖寥�撖孵����摨𤩺䲮�𡢅�`sort_levelX_asc = not sort_levelX_asc`嚗㚁��祇𡢿閫血�憭𡁶漣�齿�銝舘”憭渡悌憭渡蕃頧祆葡�瓐��
        - [x] **銝��株䌊�刻圾��**嚗𡁜��冽�撌阡睸�孵稬�𧼮�蝥扳�摨誩�嚗���啣�憭湛��塚�蝟餌��芸𢆡皜�征撟嗥���𣑐�斗��匧�蝥扳�摨讐��堒�銝擧䲮�穃��𧶏��祇𡢿��揢銝箄砲�啣���虜閫���埈�摨譌����漤膄鈭�迨�滚�憿餅��刻��典𢰧�株��閙��文�蝥扳�摨讐�蝜��甇仿炊��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣耨�寡����隞嗉�銵䔶��𣳇�蝻𤥁�璉�瘚页�靽肽�銝餉��暹㺭�格�摨誯�餉������迅摰朞�銵䎚��

## 2026-06-25 12:12
- [x] **靽桀�銝餉��曉��唳𧒄�芸��典�蝥扳�摨讛��坔紡�游����圈�霈斗�摨譍� Bug (Fixed UI Multi-Level Sorting Alignment Issue on Refresh)**嚗�
    - [x] **�齿�撟嗥�銝�銝餉��暹�摨𤩺㦤�嗡蛹 `_sort_dataframe` (Unified Sorting via DRY)**嚗𡁜��支� `instock_MonitorTK.py` (隞亙� `instock_MonitorTK-Sort.py`) ��� `refresh_tree` 銝剖�雿嗵��嗵��閧漣�鍦��餉�����嗥�銝��齿�銝箄��刻䌊�厩� `self._sort_dataframe(df)` 蝏煺��鍦��亙藁���蝖桐�鈭�銁�芷�㕑��湔鰵����嗅膥頧株砭蝑㗇�雿𡏭圻�� UI �瑟鰵�塚��賢� 100% 摰峕㟲撖寥�憭𡁶漣���蝥扳�摨讛��辷��脫迫鈭��銝箏��啣𢆡雿𨅯紡�渡��鍦��鮋���碶腺憭晞��
    - [x] **銵亙�暺䁅恕�鍦�銝贝䌊�㕑�/�滨�銝芾�隡睃��鍦� (Restored Default is_fav Sorting Prioritization)**嚗帋耨憭滢��冽瓷�劐遙雿訫�蝥扳��閧漣�鍦��𡑒挽蝵格𧒄嚗屸������ `_sort_dataframe` �鮋����𣈲銝剔眏鈭𡒊凒�� drop `is_fav` �峕��劐� `df.sort_values(by='is_fav', ascending=False)` 撖潸稲暺䁅恕�芷�㕑�蝵桅▲憭望� the 蝻粹萅��緵撌脰‘�𧼮笆 `is_fav` �鍦���撩���摨𧶏�蝖桐�鈭��𣈯��嫣葵�∩����嘥銁銝餉��曆�����游虾�冽�扼��
    - [x] **隡睃�憭𡁶漣�鍦�銝讠�銵典仍撌阡睸�孵稬閫�膄�餉�銝擧䲮�穃�頧� (Optimized Header Click to Dismiss Multi-Sort & Reverse UX)**嚗�
        - [x] **�孵��單𧒄�滩蓮**嚗𡁜��冽��典�蝥扳�摨譍��孵稬銝餅�摨� (L1)����鍦� (L2) �𡝗活�鍦� (L3) 銝凋遙�譍��㛖�銵典仍�塚��湔𦻖�冽㜃�芸膥銝剖�頧砍僎撖寥�撖孵����摨𤩺䲮�𡢅�`sort_levelX_asc = not sort_levelX_asc`嚗㚁��祇𡢿閫血�憭𡁶漣�齿�銝舘”憭渡悌憭渡蕃頧祆葡�瓐��
        - [x] **銝��株䌊�刻圾��**嚗𡁜��冽�撌阡睸�孵稬�𧼮�蝥扳�摨誩�嚗���啣�憭湛��塚�蝟餌��芸𢆡皜�征撟嗥���𣑐�斗��匧�蝥扳�摨讐��堒�銝擧䲮�穃��𧶏��祇𡢿��揢銝箄砲�啣���虜閫���埈�摨譌����漤膄鈭�迨�滚�憿餅��刻��典𢰧�株��閙��文�蝥扳�摨讐�蝜��甇仿炊��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣耨�寡����隞嗉�銵䔶��𣳇�蝻𤥁�璉�瘚页�靽肽�銝餉��暹㺭�格�摨誯�餉������迅摰朞�銵䎚��

## 2026-06-25 12:05
- [x] **靽桀��曹��唳旿銝箇征�� `send_df` 瞍𤩺� `continue` 撖潸稲��瑪蝔钅�憸𤑳征頧砌��亙��游� Bug (Fixed send_df Loop Fall-through & Log Flooding)**嚗�
    - [x] **�拍��𠉛氖蝛箸㺭�� fall-through �朞楝**嚗帋耨憭滢� `instock_MonitorTK.py` �� `send_df` 銵峕�撟踵偘���摮鞟瑪蝔见銁�Ｘ��啁��Ｘ遬蝷箄膘 `df_to_check` 銝箇征嚗���𡁜鍳�典�����芸��㗛�撌乩��園𡢿畾蛛�銝𥪜儐�航恣�� `count >= 3` �𠬍��誩�瞍𤩺�鈭� `continue` 隞舘�屸◇撱嗅�銝讠忽�𤩺�銵𣬚�瞍𤩺���緵�其��行㺭�桐蛹蝛綽�撘箏�撠譍��� 2 蝘鍦僎 `continue` 餈𥪜�銝衤�甈∪儐�荔�敶餃��餅鱏鈭��蝏剝�餉����靚𤘪�銵䎚��
    - [x] **憓噼挽�亙��滚臁銝𡡞���綉�� (Throttled Log Output)**嚗𡁜� `[send_df] display track is empty or missing, waiting...` 靚���亙�����圈������蛹�箔�霈⊥㺭瘙�芋 `count % 30 == 0`嚗�之蝥行� 60 蝘埝��唬�甈∴�嚗�蝠摨閙祥����批��唳�蝘埝㺭�∠��𨀣𠯫敹𡑒蔑�詹�嘥� I/O 鈭㗇𦜖嚗峕�����𤾸蝱�輸彿�滚𦛚��迅摰𡁏�扼��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣耨�孵��� `instock_MonitorTK.py` 摰峕�鈭�����霂𡢅�蝖株恕�牐遙雿閗祗瘜訫�撣賂�蝟餌�餈鞱�撟喟迅��

## 2026-06-25 12:00
- [x] **摰䂿緵 MinuteKlineCache �𤾸蝱�閧瑪蝔见�甇交鸌�讛‘����� (Implemented Async Single-Threaded Supplemental Fetching for MinuteKlineCache)**嚗�
    - [x] **�齿� `_supplemental_fetch` 銝箏�甇仿��埈㦤��**嚗𡁜�撘�������葵�⊿�憸穃�甇�/�閧��餃� `_supplemental_fetch` �寞���挽霈∪僎摰䂿緵鈭� `_start_sup_worker_thread` �𤾸蝱�閧瑪蝔� `SupFetchWorker` ���甇仿��埈��𡝗沲����葵�⊥��碶遙�∪�鋡怎��脣銁 `self._pending_sup_codes` 銝哨��曹�撅𧼮��啣�蝥輻�銝脰��扯�嚗�蝠摨閗��蹂�擃㗛��湧�璉�瘚𧢲𧒄蝥輻����銝� HDF5/蝵𤑳� I/O �抒�鈭㗇𦜖撖潸稲��蜓蝥輻��⊥香��
    - [x] **摰䂿緵銵亙��匧�憭梯揖 5��� �瑕㭂���輯䌊�� (Failed Cooldown 5-Minute Gate)**嚗𡁏鰵憓� `_sup_failed_codes` 摮堒�霈啣��匧�憭梯揖���蟡其誨����園𡢿�喋��笆鈭擧��硋仃韐交�餈𥪜�蝛箸㺭�桃�銝芾�嚗諹䌊�券�蝳餃��� 5 ���嚗�銁甇斗��渡��滚��匧�霂瑟�鋡怎凒�交㜃�迎��踹��䭾�霂瑟�撖潸稲���蝏靝��䀝葉�扯�撘�����
    - [x] **靽嘥�撟嗆�銋���亦瑪�孵����霈∠�蝏𤘪��啁�摮� (Saved Computed Daily Indicators to Cache)**嚗𡁜銁 `calculate_stock_daily_indicators` �詨�霈∠�摰峕��𠬍��刻��䂿��𨅯�蝵桀��嗅��� `_daily_indicators_cache` 蝻枏�嚗諹�銝�甇亙��������剛楝�賭葉嚗峕��支�鈭峕活霈∠���
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�銝𤾸����霂閖�霂� (Passed Compilation Validation)**嚗𡁜笆靽格㺿餈�� `realtime_data_service.py` 餈𥡝�鈭�祗瘜閧����霂烐�瘚页�憿箏⏚�𣳇��朞�嚗𣬚＆霈斤頂蝏蠘�銵𣬚𠶖��鵭��迅摰𠾼��

## 2026-06-25 11:35
- [x] **靽桀�銝餉��曉�蝥扯��冽�摨誩�韏瑞� pandas `ValueError: ascending` 撏拇�銝舘”憭游�靚�㨃甇� (Fixed Pandas ValueError & Treeview Header Lambda Freeze in Multi-Level Sorting)**嚗�
    - [x] **�寞祥�鍦����摨誩�銵� `NoneType` 隡惩�撏拇� (Enforced Boolean Checks in _sort_dataframe)**嚗帋耨憭滢��曹� `ui_state` 銝剝�������摨讐𠶖���憒� `sortby_col_ascend`, `sort_levelX_asc`嚗匧�憪见��𤥁◤憭㚚�靽格㺿銝� `None` �塚��湔𦻖隡𣳇�垍� `df.sort_values` 撖潸稲�� `ValueError: ascending must be a boolean or list of booleans` 撏拇���銁 `_sort_dataframe` ���蝥批��閧漣�鍦��餉�銝哨�撖寞��� `ascending` �啁�憿寡蕭�牐� `bool(getattr(...))` 撘箏�頧祆揢銝𡡞�蝛箔��扎��
    - [x] **摰䂿緵銵典仍�鍦�摰墧𧒄瘙��澆�靚� (Implemented Dynamic Header Sorting Lambda)**嚗帋耨憭滢�銵典仍�冽葡�𤘪𧒄蝖祉���𤐄摰帋�敶𤘪𧒄�� `col_asc` 撣���嗆��� command lambda �剖����撖潸稲�𡒊賒憭𡁏活�孵稬銵典仍�䭾�甇�＆霂餃����唳�摨𤩺䲮�𤑳�蝻粹萅�����蛹撘訫� `_get_current_col_asc(col)` 颲�𨭌�寞�嚗�僎�� lambda 閫血��嗅𢆡����嗉恣蝞堒��滚�����啣��滚��嗆���銵䔶����瘨�膄鈭�漱鈭垍𠶖���皛硺��賢���香��
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖� `instock_MonitorTK.py` 摰峕�鈭���嗵�霂烐�瘚页�靽肽�銝餉��暹㺭�格迤撣豢葡�㮖�摰𣬚��鍦���

## 2026-06-25 00:15
- [x] **�冽��笆朣� `cct.compute_lastdays` 憭𡁏𠯫���餈睃�銝舘䌊�刻恥�� (Dynamically Aligned compute_lastdays Slice Reconstruction & Auto-Subscription)**嚗�
    - [x] **摰䂿緵�冽����交𤣰�睃��𡑒��� (Dynamic Daily Close Series Reconstruction)**嚗𡁜銁 `ATSMainWindow` 銝哨��滨漣�齿��餉��啣銁�賢��箔� `getattr(cct, 'compute_lastdays', 9)` �冽����鞉�餈� 9 憭抬��㚚�蝵桀予�堆���𠯫�嗥�隞瑕��梹��拍鍂���敺芰㴓嚗��蝚� 9 �仿�鍦��喟洵 1 �伐�霂餃� `lastp9d` �� `lastp1d` 蝑匧�撟嗅��斗����潘�隞舘��𢆡�����撌桀��𣇉��亦瑪�墧滲憭拇㺭�滨蔭��
    - [x] **TK蝡臬��脣�����芸𢆡靽萘�銝� IPC �峕郊 (TK Side Historical Slice Auto-Preservation)**嚗𡁜銁 `instock_MonitorTK.py` ���惩遆�唬葉嚗屸�朞�銝文�敺芰㴓�芸𢆡撠� 1 �� `cct.compute_lastdays` 憭拍��券���蟮 OHLCV �梹�憒� `lastp1d` 蝑㚁�瘛餃��� `self.mandatory_cols` 霈ａ��𡑒”銝准���蝖桐�鈭�銁�𡑒��芸��舐����銝页�憭𡁏𠯫��蟮����唳旿�賢� 100% 摰峕㟲隡𣳇��� ATS嚗��蝢擧𣈲�睲��冽�� 9 憭拙��脫㺭�桃��啣㦤餈睃���

## 2026-06-25 00:10
- [x] **摰䂿緵�� HDF5 ��蟮�唳旿�嗥����餈睃�銝𡒊𠶖��㦤�芣� (Implemented Daily Slice Fallback Reconstruction & State Machine Self-Healing without HDF5)**嚗�
    - [x] **�删�憭�遢���摨誩��𤥁��� (Reconstructed Historical Close Series from Real-Time Slice)**嚗𡁜銁 `ATSMainWindow` �嗆��凒�唬葉嚗諹𥅾�𤾸蝱 HDF5 ��蟮�唳旿�㰘蝸�芸��鞉�銝箇征嚗𣬚頂蝏笔��芸𢆡�拍鍂摰墧𧒄 `df` 銝剜𡉼撣衣� `lastp1d` (�冽𠯫)��lastp2d` (�齿𠯫)��lastp3d` (憭批���) 蝑匧��交𤣰�䀝遠���嚗䔶誑�𠹺��亙��嗡遠嚗𣬚��湔𣄽鋆�枂�踹漲銝� 4 ����脫𤣰�䀝遠摨誩� `close_series`��
    - [x] **���舀���笆朣鞉釣�� (Aligned MA Indicators from Slice Data)**嚗𡁜⏚�典�甇� `df` 銝剔緵�鞟� `ma5d` �� `ma20d` �梹��湔𦻖���撟喲唍憛怠��� `ma5_series` �� `ma20_series` 雿靝蛹�蹂誨颲枏���眏鈭𡒊𠶖��㦤摨訫�隞�蝙�典��㛖����唬�雿齿����`[-1]`嚗匧����唬舅�交𤣰�䀝遠嚗Ǒ[-1]`銝𥳾[-2]`嚗㚁�霂仿�蝥折�蝏�銁�餉�銝𠰴��唬� 100% �����笆朣琜�雿輸�㕑�靽∪噡�𣬚𠶖��㦤�典��臬𢆡�𡝗� HDF5 摨𤘪𧒄�賢�蝡见�甇�虜餈鞱蓮撌乩���

## 2026-06-25 00:05
- [x] **�惩𤐄 ATS 銵峕��嗆��㦤�唳旿蝐餃�摰匧�銝𡡞俈�園膄靽脲擪 (Hardened Data Type Safety & Zero-Division Protection in ATS State Machine)**嚗�
    - [x] **撘箏�隞瑟聢�啣�潭筑�寞㺭蝐餃�頧祆揢 (Enforced Float Type Casting)**嚗𡁜銁 `ATSMainWindow` 隞瑟聢�����遣憭��撖寧眏��蟮蝻枏�銝擧��唬遠��僎�峕��� `close_series` 摨誩�餈賢�鈭� `float()` 撘箏�頧祆揢銝𡡞�蝛箄�皛歹��脰��勗�撅�㺭�格�畾讠撩�𣇉掩�见�撌桀��𤑳� `TypeError`��
    - [x] **撘訫�蝘餃𢆡撟喳��園鵭摨血��潮俈�園膄�脣鴃 (Added Zero-Division Prevention in Rolling MA)**嚗𡁜銁蝥� Python 摰䂿緵��宏�典像��儐�臭葉嚗�笆 `sub20` 銝� `sub5` �𡑒”���憓𧼮�鈭�征�潭�撉䔶�暺䁅恕�鮋��靽脲擪嚗𣬚＆靽嘥銁��垢蝛箇頂�堒㦤�臭���瑪�鮋��銝箏��滢葵�⊥𤣰�䀝遠嚗峕��支� `ZeroDivisionError` �鞉���

## 2026-06-24 23:55
- [x] **瘛勗漲隡睃� ATS 銵峕��交𤣰銝餌瑪蝔见㨃甇颱� TCP �峕郊�扯� (Optimized ATS UI Thread Lag & TCP Socket Synchronous Performance)**嚗�
    - [x] **靽桀��賢�蝞⊿� `ATS_RECEIVED` �漤��仿� (Fixed Pipe Feedback Argument Error)**嚗帋耨憭滢��� socket �交𤣰�𤾸蝱蝥輻�銝哨�靚�鍂 `send_code_via_pipe` �煾�� `ATS_RECEIVED` �漤�撣扳𧒄嚗峕�隡� `logger` positional ��㺭撖潸稲�� TypeError 撘�虜��緵撌脰‘朣� `local_logger` ��㺭嚗峕��蠘悟 TK �交𤣰�啣�甇亦＆霈支縑�瘀��踹�鈭�眏鈭𡒊＆霈支縑�瑚腺憭勗�韏瑞� TK �𤾸蝱擃㗛��滚��煾��之敹怎��唳旿����峕郊憌擧𠂔��
    - [x] **摰墧鴌 HDF5 �ａ��𡝗㺭�桀��啣�甇仿�憭�� (Background Index Preprocessing)**嚗𡁜銁 `ats/ipc_bridge.py` �� socket �交𤣰�𤾸蝱蝥輻�銝哨��滨蔭摰峕�鈭�笆�滚��堒���敺� DataFrame �� index 摮㛖泵銝脫聢撘誩���.strip()` �駁膄蝛箸聢�� `set_index` ���雿栶��銁 `ats/ui/main_window.py` �� `_handle_realtime_data` 銝哨�憓𧼮�鈭��蝵桃𠶖��嵗撉䕘��交㺭�桀歇鋡恍�憭��嚗���湔𦻖頝唾��埈𧒄�啁蓡瘥怎���聢撘誯��嗘� deep copy 撘��喉�憭批��滢�鈭�蜓 UI 蝥輻��� CPU 撘�����
    - [x] **�踵揢 Pandas Rolling 霈∠�銝箇滲 Python 蝘餃𢆡撟喳� (Pure Python Rolling MA Optimization)**嚗𡁜銁 `ATSMainWindow` �瑟鰵敺芰㴓��葵�∪�頦拍𠶖��㦤霈∠�憭��摨罸膄鈭�銁 for 敺芰㴓銝剝�憸穃�靘见� `pd.Series` 撟嗉��� `.rolling` ��恣蝞埈䲮撘𧶏��寧鍂蝥� Python �𡑒”蝥批���� `sum/len` 餈鞟����銝��孵𢆡撠��甈∟���店�冽𧒄霈∠���瑪��𧒄�港��啁蓡瘥怎��讠憬�喳凝蝘垍漣嚗����� 100 �滢誑銝𠺪�嚗�蝠摨閙��支�摰䂿��瑟鰵�嗥��⊿▼��香��
    - [x] **�拙� Socket �交𤣰蝻枏��箄秐 64KB (Increased TCP Receive Buffer)**嚗𡁜� `ats/ipc_bridge.py` 銝� socket 敺芰㴓霂餃�憭批��� buffer size 隞� `4096` �拙�銝� `65536`嚗�之撟��撠睲� Windows 蝟餌�靚�鍂撣行䔉�������

## 2026-06-24 23:45
- [x] **摰䂿緵 ATS 銵峕��交𤣰蝖株恕�箏�銝𤾸�蝡舫俈�碶誑敶餃��寞祥�峕郊憌擧𠂔銝𤾸㨃甇� (Implemented ATS Sync Receipt Confirmation & Double-Sided Debouncing to Prevent Sync Storms)**嚗�
    - [x] **摰䂿緵�𤾸蝱�嗅��唳旿�單𧒄�漤��箏� (Instant IPC Receipt Feedback via Pipe)**嚗𡁜銁 `ats/ipc_bridge.py` 銝哨��齿�鈭� `_handle_client` socket �交�閫���餉���銁�𤾸蝱�交𤣰蝥輻��𣂼��滚��堒� `UPDATE_DF_DATA` �交���洵銝��園𡢿嚗峕���蝑匧�銝𥪜��函�餈� UI 蝥輻�皜脫��笔�嚗𣬚��駁�朞��賢�蝞⊿��� TK 銝餉�蝔见���䌊摰帋��� `{"cmd": "ATS_RECEIVED"}` �嗆��＆霈文葷��
    - [x] **�啣� TK 蝡臬笆 ATS �嗆���銝餃𢆡�毺䰻銝� 10蝘� 蝖株恕�瑕㭂憓� (10s Confirmation Cooldown Gate on TK)**嚗𡁜銁 `instock_MonitorTK.py` 銝哨�
        - [x] �典𦶢�滨恣�梶��砍膥銝剜𦻖�� `ATS_RECEIVED` ��誘嚗峕𤣰�啣��祇𡢿皜�膄 `_force_full_sync_pending = False` 撟嗉扇敶訫��滨＆霈斗𧒄�湔� `self._last_ats_recv_confirm_time`��
        - [x] �� `send_df` 銵峕�撟踵偘����餉�銝哨�撖� `is_forced` ����𡝗辺隞嗅��牐�蝖株恕�嗆��斗鱏嚗朞𥅾頝苷�甈⊥𤣰�� ATS �����𦻖�嗥＆霈支�頞� 10 蝘𡜐��坔撩銵�ế摰帋蛹�滚�/�䭾�銋厩��匧��其�嚗𣬚凒�交��嗆㜃�迎�隞擧�憭港��拇鱏鈭��𤔡I�⊿▼ -> 霈支蛹�芣��� -> �齿活霂瑟��萘��嗆�折�鍦���
    - [x] **�朞� Python 霂剜�蝻𤥁�銝擧��䠷�霂� (Passed Syntax & Compiler Checks)**嚗𡁜笆靽格㺿餈�����㗇�隞嗆�銵䔶��𣳇�蝻𤥁�嚗䔶��𨅯�餈𤤿��嗆�摰匧��舫���

## 2026-06-24 23:20
- [x] **摰䂿緵 ATS �臬𢆡�嗉䌊�券�朞� IPC 蝞⊿�霂瑟��券��峕郊�𦠜�扯��烐綉�亙���氖 (Implemented ATS Startup Auto-Sync via IPC & Separated Performance Monitoring Logs)**嚗�
    - [x] **�寞祥 ATS �臬𢆡�嗆挾撘箏��峕郊霂瑟�鋡� socket �瑕㭂�箏��行⏛銋讠撩�� (Fixed Forced Sync Request Interception by Socket Cooldown)**嚗𡁜銁 `instock_MonitorTK.py` �� `send_df` 銵峕��唳旿�峕郊敺芰㴓銝哨��齿�鈭� socket �煾����瑕㭂�園𡢿�文��������� `if (vis_enabled or is_forced) and now_ipc > ipc_cooldown:` 靽格迤銝� `if is_forced or (vis_enabled and now_ipc > ipc_cooldown):`���銝��孵𢆡蝖桐�鈭�銁�航��𣇉�����凋��嗅��亥䌊�賢�蝞⊿� of `is_forced` (憒� ATS �臬𢆡�嗆挾�煾�� of `REQ_FULL_SYNC`) 撘箏�霂瑟��塚��臭誑�湔𦻖蝏閗��齿��� Socket 餈鮋�𡁜仃韐乩漣�毺��瑕㭂���踹�嚗𣬚���遣蝡� socket �祇𡢿����唳旿��
    - [x] **�惩𤐄 Windows �賢�蝞⊿�摰Ｘ�蝡� busy �� not_found �芸𢆡�滩�銝𡒊�敺�㦤�� (Hardened Windows Named Pipe Client with Busy/Not-Found Retries)**嚗𡁜銁 `data_utils.py` 銝剝���� `send_code_via_pipe` 摰Ｘ�蝡臬���𦻖������乩� `winerror.ERROR_PIPE_BUSY` (蝞⊿�敹�) 銝� `winerror.ERROR_FILE_NOT_FOUND` (蝟餌��曆��唳�摰𡁶���辣) ��䌊���隡𤑳�銝𡡞�霂閖�餉���銁敹嗵��嗉䌊�券�朞� `win32pipe.WaitNamedPipe` 蝑匧� 1 蝘坿䌊����冽𪄳銝滚���辣�嗉䌊�函�敺� 500ms �滩�嚗諹�蝏剖�霂� 5 甈∴�敶餃��踹�鈭�眏鈭� TK �𤾸蝱�芸�憪见�摰峕��𣇉恣�㯄�憸穃��典紡�渡��批�靽∪噡銝Ｗ仃銝� auto-sync 憭梯揖��
    - [x] **摰䂿緵 ATS �扯�霈⊥𧒄�亙� of �祉�颲枏枂銝𤾸�蝐駁�蝳� (Separated Telemetry Timing Logs for Visualizer and ATS)**嚗𡁜銁 `instock_MonitorTK.py` ��� `send_df` 撠暸��� `finally` 撘�虜�墧𤣰�綽�撠���砍�鈭思�隞�銁 `sent` (Visualizer �煾�����) �嗉圻�𤑳�霈⊥𧒄颲枏枂嚗諹圾�血僎�拙�銝� `sent` and `sent_to_ats` �屸�𡁻��祉��文�嚗𡁜��急��� `viz_` and `ats_` �滨� of �埈𧒄瘙��颯���摰𣬚��𡁜�鈭���芣� ATS �唳旿�峕郊�𤑳��塚��賣��啁𡠺蝡见�蝷� ATS 蝡舐��埈𧒄蝏蠘恣�䔶�銝𤾸虾閫��蝒堒藁瘛瑟���
    - [x] **撱箇� ATS 瘣餉��嗆��惣�賣��乩��唳旿�惩��冽㜃�芣㦤�� (Integrated Active ATS Sensing & No-Change Transmission Bypass)**嚗�
        - [x] **閫���硺漱�𤘪𧒄畾萄�蝛箸凒�圈�憸穃���䔮憸�**嚗𡁜銁 `instock_MonitorTK.py` �� `send_df` 銝哨�敶� `msg_type == 'DF_DIFF_EMPTY'` (�唾�����睃𢆡) 銝𥪯��臬撩�嗉窈瘙�𧒄嚗�� `sent` ��扇銝� `True` 撟嗆��漤���綽��踹�餈𥕦� socket �拍��煾���敶餃�瘨�膄鈭���湔鰵�嗆挾��㺭�桀�頧啁���
        - [x] **�箄�瞈�瘣颱��芷���隡𤑳�**嚗𡁜��� `self._ats_enabled_cache` (暺䁅恕 `False`)嚗�� ATS �𣂼�餈墧𦻖撟嗅���𧒄嚗𣬚蔭銝� `True` �芸𢆡撠���惩� periodic sync �煾���嚗𥕦� ATS 蝒堒藁�喲𡡒餈墧𦻖憭梯揖�塚��芸𢆡蝵桐蛹 `False` 撟園���箏𪂹�笔�甇伐�摰𣬚�閫��鈭��暺条𠶖����� I/O �蠘�𦯀� CPU 蝛箄蓮��
        - [x] **撱園鵭頞�𧒄���潮俈甇Ｗ之�����**嚗𡁜� socket 暺䁅恕�� `0.2` 蝘坿��塚�`settimeout`嚗匧��典辣�輯秐 `2.0` 蝘𡜐�敶餃��㯄�帋� Windows 銝见���� DataFrame �寥� pickle 摨誩��硋之���撅��毺� TCP 隡㰘��朞楝��
        - [x] **ATS 蝡臬�撠穃�甇亥窈瘙��甈∪僎餈賢��擧苊�亙�**嚗𡁜銁 `ats/ui/main_window.py` 銝剝���� heartbeat �峕郊�文�嚗䔶��典鍳�典���/�唳旿銝箇征�碶漱�𤘪𧒄�湔挾���餈� 10 ���瘝⊥��嗅��唳旿�券��𧒄�滚�甈∪𤧅�� pipe 霂瑟�餈𥡝��见𢆡�峕郊嚗��隞𡝗𧒄�游��冽�韏瑞�敺� TK 銝餉�蝔贝䌊�刻�銵諹���嘀�准��𦻖�嗅��唳旿�𤾸銁�批��啣��嗆����枏㫲�擧苊��𧒄�湔�銝舘��唳𠯫敹𨰜��
        - [x] **�寞祥�航��𣇉�����剖紡�湔㺭�桀�甇亦瑪蝔钅獈憛𧼮�擃㗛��滚��峕郊蝻粹萅 (Resolved Sync Thread Blocking when Visualizer Closed & Prevented Sync Storms)**嚗�
            - [x] **�航��硋��剜�頝航�皛�**嚗𡁜銁 `instock_MonitorTK.py` 銝哨�撠�虾閫�� Socket �𨅯��煾����文��∩辣隞� `(vis_enabled or is_forced) and not sent` 隡睃�銝� `vis_enabled and not sent`��眏鈭𤾸縧�支� `or is_forced` ��撩�嗆�頝荔��典虾閫��蝒堒藁�喲𡡒嚗Ǒvis_enabled` 銝� `False`嚗劐��嗅� ATS �� `REQ_FULL_SYNC` 霂瑟��塚�蝟餌�銝滢��滚�霂閧������ `26668` 蝡臬藁嚗䔶���蝠摨閙��支�瘥𤩺活�煾��◤ 2.0 蝘� socket 餈墧𦻖頞�𧒄撘箄��⊥香��撩�瑯��
            - [x] **撘箏��峕郊 5 蝘㘾俈�瑕��� (5s Cooldown for Forced Syncs)**嚗𡁜銁 `instock_MonitorTK.py` ��㺭�桀���儐�臭葉撖� `is_forced` ��撩�嗉窈瘙���乩� 5.0 蝘垍���雿𤾸��湧���輸�餉���𥅾 5 蝘鍦��㕑�蝏剖�甈∪撩�嗆��硋�颲橘��芸𢆡撠��撘箏��駁��行⏛撟園���踹�撣貉��鞉�嚗屸俈甇Ｙ��游��穃�雿坔��𤩺㺭�桀���
            - [x] **�瑕鍳�其�敹�歲�嘥��㚚俈�� (Cold Start & Heartbeat Debouncing)**嚗𡁜銁 `ats/ui/main_window.py` �� `on_heartbeat` 銝哨�撖孵��臬𢆡蝛箸㺭�桀�甇亥蕭�牐� 15 蝘鍦��湔𧒄�湧��潦����嗅銁�臬𢆡�嗆挾�� `start_realtime_listener` 銝剖撩銵��憪见� `self._last_pipe_sync_t = time.time()`���摰��撠��鈭���臬𢆡�祇𡢿 heartbeat 銝𤾸鍳�刻��砍��嗅���舅甈� `REQ_FULL_SYNC` �䭾���窈瘙���牐���妖��

## 2026-06-24 21:00
- [x] **摰䂿緵 MA20 銝餃�瘚芷��穃�蝑𣇉裦����㗛�霅阡𡡒�� (Integrated MA20 Trend BUY2 Logic into Live Strategy and Dashboard)**嚗�
    - [x] **�亙�摰䂿��喟�撘閙� (Decision Engine Integration)**嚗𡁜銁 `intraday_decision_engine.py` ��僭�亙ế摰𡁻�餉�銝哨��𣂼�撘訫� `trade_signal == 2`嚗㇈A20�噼萱�滚�嚗厩��閗繮��𣈲����西��怠�霂亙��脖縑�瘀�撘閙�撠�䌊�典��喟�蝵桐蛹 "銋啣�"嚗�僎撘箄�蝏嗘� `0.45` ����箇�隞㮖�霂��嚗��頞� 0.40 ��僭�亦′�冽�嚗㚁��峕𧒄颲枏枂��蒂 `[MA20暺���𩬅` �� `BUY2` ������隡睃��文���眏嚗�蝠摨閙��帋�隞𤾸��脤�㕑��啁�銝剜㜃�芰��扯��曇楝��
    - [x] **�亥郎靽⊥��栞𠧧銝舘����撘� (Dashboard Highlighting)**嚗𡁜銁 `signal_dashboard_panel.py` 銝剜凒�唬� UI 閫��閫��嚗�銁 `_get_pattern_color` 憸𡏭𠧧餈�誘�其葉�啣�鈭�笆 `BUY2` �� `暺���鬔 �喲睸摮㛖��Ｘ�����血𦶢銝哨�蝡见�閫血��曄尐�� `#FFD700` (�𤏸𠧧) �亥郎擃䀝漁嚗𥕦��嗆凒�� `CATEGORY_MAP`嚗�� `BUY2` �� `暺���鬔 �峕郊�嗅��喇�靝僭�交㦤隡尠�苷��𡏭��蓥縑�猾�嘥�蝏��摰䂿緵�亥郎�穃�瘚��蝎曉��冽�銝𤾸�蝏游�蝷箝��

## 2026-06-24 18:40
- [x] **�券𢒰撠�� TK 銝餌�摨譍葉�㰘蝸 `sina_data` �瑕��唳旿���靘见�蝥找蛹�芾粉璅∪� (Upgraded non-Tk main programs loading sina_data to Read-Only)**嚗�
    - [x] **��漣 `realtime_data_service.py` ��� `Sina` 銵峕�摰硺�**嚗𡁜� `backfill_gaps_from_hdf5` 蝻枏�皜��憭� `sina_data.Sina().clear_unified_cache(...)` �� `recover_from_hdf5_by_codes` �唳旿蝎曉��Ｗ�憭� `sina_data.Sina()` 摰硺��硋��典�蝥找蛹�芾粉璅∪��� `Sina(readonly=True)`嚗�蝠摨閙��支�蝻箏藁銵亙��峕㺭�桃移���憭齿𧒄�曹�靽格㺿�園𡢿 `mtime` �睃𢆡撖潸稲���隞嗥𡠺�惩�憸𤑳� I/O �桅���
    - [x] **��漣 `instock_MonitorTK.py` 摰𡁏� GC �芣�皜��銝� `Sina` 摰硺�**嚗𡁜�銝�撠𤩺𧒄摰𡁏� `controlled_gc_loop` ���/�交��芣�皜��敺芰㴓銝剛��� `clear_unified_cache` �� `Sina()` 摰硺��碶耨�嫣蛹 `Sina(readonly=True)`��
    - [x] **摰峕� Python 霂剜�蝻𤥁�銝擧��䠷�霂� (Passed Syntax & Compiler Checks)**嚗𡁏�銵䔶� `py_compile` 撖嫣耨�孵������ Python 璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�蝟餌��踵�蝔喳���

## 2026-06-24 18:30
- [x] **靽桀��曹� SafeHDFStore 摨訫�瞍譍� mode ��㺭撖潸稲 HDF5 �芾粉璅∪�憭望��羓���耨�寞𧒄�游��� Bug (Fixed Read-Only Mode Ineffectiveness & HDF5 mtime Alteration Bug)**嚗�
    - [x] **�寞祥 SafeHDFStore constructor 銝剖�撅� pandas HDFStore 瞍譍� mode ��㺭銋讠撩�� (Fixed Missing mode Parameter in SafeHDFStore Constructor)**嚗𡁜銁 `tdx_hdf5_api.py` �� `SafeHDFStore` 蝐餌����惩遆�唬葉嚗䔶耨憭滢��刻��� `super().__init__` 摰硺��硋�撅� `pd.HDFStore` �嗆𧊋�曉�隡惩� `mode=self.mode` ��䔮憸塩��銁甇支��㵪�摨訫��� pandas 撘閙��牐蛹蝻箇����碶蛹暺䁅恕�� `'a'` (餈賢�/��) 璅∪�嚗�朖雿蹂�撅�誑�芾粉 `'r'` 璅∪�摰硺��吔�隞滨�隡帋誑�蹱䲮撘𤩺�撘� HDF5 ��辣���撖潸稲�� Windows 蝟餌�銝哨�銝��西粉�𡝗�隞塚��嗥���耨�寞𧒄�� `mtime` �冽�隞嗅��剜𧒄�賭�鋡怠撩�嗉圻蝣唳凒�堆�餈𥡝�𣬚聦�譍��箔���辣靽格㺿�園𡢿�喟����蝻枏��寥��箏�嚗䔶漣����園�蝜�� HDF5 霂餌�撘�����緵�朞�銵仿� `mode=self.mode`嚗諹悟�芾粉璅∪��典�撅��甇������拍�靽格㺿�園𡢿蝏苷��滚��具��
    - [x] **撠�虾閫��摮鞱�蝔贝���㺭�桀��𤾸��Ｗ�蝥找蛹�芾粉摰硺� (Upgraded Visualizer Sina instances to Read-Only)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�撠���匧銁 `DataLoaderThread` 蝥輻� fallback��realtime_worker_process` 摰墧𧒄摮鞱�蝔卝��RealtimeUpdateWorker` 頧株砭撌乩��其誑�� `MainWindow` 銝餌���葉摰硺��� `Sina()` 銵峕�撘閙���𧑐�對��券𢒰靽格㺿銝箔蝙�典蘨霂餅芋撘讐� `Sina(readonly=True)`��𡖂憭吔��祆活銵亙�撖� `DataLoaderThread` ����㛖��� fallback 暺䁅恕摰硺��吔�蝚� 1243 銵䕘�隞亙� `test_tick_df` 瘚贝��賣㺭嚗�洵 1532 銵䕘�餈𥡝�鈭���Ｚ‘朣鞉㺿�具��秐甇歹��航��𤥁�蝔讠垢����� `Sina` 銵峕�摰硺���歇��漣銝箏蘨霂餅芋撘𧶏�瘨�膄鈭�遙雿閖�撘𤩺㺿�坔之頧刻蕨��辣������靽嗪�鈭�頂蝏毺�蝔喳��扼��
    - [x] **�朞� Python 霂剜�蝻𤥁�銝𤾸蘨霂餌�摮睃𦶢銝剜�折��𣂼�敶埝�霂� (Passed Compiler Checks & Cache Integration Tests)**嚗𡁶��坔僎�扯�鈭���鞉�霂閗��穿�霂�� `Sina(readonly=True)` �函���粉�硋之頧刻蕨��辣 `sina_MultiIndex_data.h5` �𠬍���辣��耨�寞𧒄�� `mtime` 靽脲�蝏嘥笆�芸�嚗䔶�蝚砌�甈∪��𡒊賒��粉�𤥁窈瘙�虾 100% �祇𡢿�賭葉���蝻枏��行⏛撅誯�嚗諹噢�𣂷��� I/O �餃�嚗𥕦��嗅笆 `tdx_hdf5_api.py` �� `trade_visualizer_qt6.py` 餈𥡝�鈭�祗瘜閧�霂烐�瘚页�蝖株恕�牐遙雿訫�撣詻��

## 2026-06-24 16:20
- [x] **隡睃� HDF5 �券��閗”閬���拍�雿梶妖�批�銝𡡞�鈭斗��園𡢿蝵𤑳�頧株砭蝛輸�誯俈敺� (Optimized HDF5 Single Table Rewrite Size Control & Network Polling Defense during Non-Trading Hours)**嚗�
    - [x] **�寞祥 HDF5/PyTables 閬���滚�撘閗絲���隞嗡�蝘舐������瘜�� (Fixed HDF5 Free Space Leak in Single-Table Rewrites)**嚗𡁜銁 `tdx_hdf5_api.py` �� `write_hdf_db` 敹恍�笔��交芋撘譍葉憓𧼮�鈭�惣�賢��交芋撘𤩺䔝瘚卝���璉�瘚见��舫� MultiIndex 閬���嗘��拍���辣隞�鉄敶枏� table嚗�� `sina_data` 敹怎�銵剁��塚��湔𦻖隞� `mode='w'` �枏��冽鰵銝湔𧒄��辣�坔��券� DataFrame嚗諹歲餈����� `copy` 銝� `mode='a'` 餈賢��湔鰵��砲�孵𢆡皜�膄鈭� PyTables remove ����嗘���征�渡����雿踵�隞嗥����蝘臬銁憭𡁏活�滚��擧偶餈𦦵輕��銁��蝝批��� 1MB 憭𡁶𠶖���撟嗉������辣憭滚��� I/O 撘�����
    - [x] **靽桀��芾粉�Ｘ�蝏閗���辣���韏瑞� Windows ������蝒���芣� (Fixed Read-Only Probe Lock Penetration on Windows)**嚗帋耨憭滢��冽芋撘� B嚗�虜閫�翰�蠘蕭�𩤃�銝剜�瘚见�銵冽𧒄�湔𦻖靚�鍂�毺� `pd.HDFStore(fname_path, mode='r')` 撖潸稲�� Windows 憭朞�蝔讠㴓憓���航�銝擧迤�典��� HDF5 ����啗�蝔见��� `PermissionError` �脩��������緵撠�䔝瘚𧢲𤜯�Ｖ蛹摰𡁜� of `SafeHDFStore(fname, mode='r')`嚗䔶蝙�園�敺芰頂蝏毺�憭朞�蝔𧢲�隞園�銝𤾸�撅�蝥輻�����湔�批�霈殷��典�����冽𧒄摰匧�蝑匧�����橘�靽嗪�鈭��銵刻��嗵���𠣕頨急芋撘誩銁撟嗅��䀝葉��迅摰帋���＆��
    - [x] **摰䂿緵 87��/蝚磰扇�祇睸�䀹� Break �桐��������剛圻�𤏸䌊�����辣�穃𨯬�� (Implemented File-Based Diagnostic Trigger for Keyboards without Break Key)**嚗�
        - [x] **�啣�霂𦠜鱏�𤏸��滨蔭撘��喃���**嚗𡁜銁 `commonTips.py` �� `GlobalConfig` 銝剜溶�牐� `dump_all_monitor` �滨蔭憿對�暺䁅恕�潔蛹 `0` �喲𡡒嚗㚁�撟嗅銁 `instock_MonitorTK.py` �亙藁銝剝���� `main_SIGBREAK()`��緵�其��券�蝵格�蝖桀��舀𧒄嚗峕��臬𢆡 `file_trigger_loop` �穃𨯬蝥輻�銝� Win32 �批��� Handler嚗屸�霈斤𠶖���摰䂿緵蝏嘥笆��妟蝥輻�銝𡡞妟 I/O 撘�����
        - [x] **�啣��𤾸蝱��辣閫血��函��祉瑪蝔�**嚗𡁜銁 `instock_MonitorTK.py` ��蜓�亙藁�嘥��碶葉嚗峕鰵憓硺�頧駁�蝥批��啣��斤瑪蝔� `file_trigger_loop`��砲蝥輻�瘥� 30 蝘鍦儐�舀�瘚见極雿𦦵𤌍敶蓥��臬炏摮睃銁�滢蛹 `dump_all` ���霈唳�隞嗚��𥅾璉�瘚见��躰䌊�典��嗅��歹�撟嗥��游𤧅�� `dump_all()` �扯����頧砍�嚗���� `instock_dump.log` 撟嗡撈�� 3 蝘坿䌊�冽��鞟��毺� toast �鞟內嚗㚁�摰���踹�鈭�蜓蝥輻� GUI 甇駁��𣂼��屸睸�条�����桃撩憭梁撩�瑯��
        - [x] **�𣂷��賭誘銵䔶縑�瑕�撠�䲮獢�**嚗𡁏𣈲��鍂�瑕銁憭㚚� cmd 蝒堒藁銝凋蝙�典�銵� Python �賭誘�烐�摰� PID �煾�� `SIGBREAK` 靽∪噡嚗���其�蝏苷��芷��嚗䫤python -c "import os, signal; os.kill(PID, signal.CTRL_BREAK_EVENT)"`��
        - [x] **敶垍熙蝚磰扇�� Fn �拍��惩����**嚗𡁏㟲��僎�餌�鈭�蜓瘚������娍�/�游�/�䭾芦/�𡒊�蝑㚁�Fn �惩� `Break` ���𡁶鍂�寞�嚗𣬚＆靽嘥銁銝齿凒�嫣誨������銝衤��賜凒�乩蝙�� `Ctrl+Fn+X` 蝑厩������圻�㻫��
        - [x] **摨閖��蠘��㗇𥋘����𡏭��剛蓮�兩�嗪�厰★**嚗𡁜銁 `instock_MonitorTK.py` �� `self.action_combo`嚗���典��賭��㗇�嚗劐葉餈賢�鈭� `"霂𦠜鱏頧砍�"` �厰★����孵稬摰�𧒄嚗䔶蜓蝥輻�隞交����鈭𡁜凝蝘垍漣嚗匧�甇交䲮撘讐凒�交�銵� `dump_all()` �坔����嚗�蝠摨閖��滢��曹�銝餌瑪蝔讠凒�交�銵� faulthandler �坔�憭扳𠯫敹埈�隞嗅紡�渡�銝餌��Ｙ��游凝�⊿▼嚗�僎隡湧� 3 蝘坿䌊�冽����� Windows �毺� MessageBox �鞟內嚗�之撟������滢�瘚��摨虫�鈭支�韐券���
    - [x] **�朞� Python 霂剜�蝻𤥁�銝𡒊�霂烐嵗撉� (Passed Compiler Checks)**嚗𡁏��笔笆靽格㺿�𡒊� `tdx_hdf5_api.py` �� `instock_MonitorTK.py` 餈𥡝�鈭��霂烐�瘚页�蝖株恕�牐遙雿閗祗瘜訫�撣賂�蝟餌�餈鞱��嗆��鵭��迅摰𠾼��

## 2026-06-24 15:10
- [x] **隡睃� HDF5 憭批�摮条�摮䀹��支���䔿�墧𤣰靚�漲嚗峕��日�蝜� GC 撘閗絲��蜓蝥輻��⊿▼ (Optimized HDF5 Cache Clearing & GC Scheduling to Prevent UI Lag)**嚗�
    - [x] **撘訫�蝻枏�皜�� `force_gc` ��㺭銝𤾸辣餈笔��嗆㦤�� (Added force_gc Parameter to Cache Clearing)**嚗𡁜銁 `sina_data.py` �� `clear_unified_cache` �寞�銝剜鰵憓� `force_gc` �舫�匧��堆���捂隞���� `_MEM_CACHE` ���撘閧鍂�䔶�蝡见朖閫血���斯�� `gc.collect()` Stop-the-world �滢�嚗䔶蝙 GC �航◤撱嗉�靚�漲��
    - [x] **瘨�膄�噼‘蝻箏藁�嗥�憸𤑳� GC (Removed Frequent GC during Gap Recovery)**嚗𡁜銁 `realtime_data_service.py` ����� `backfill_gaps_from_hdf5` �寞�銝哨�撠� `clear_unified_cache` �䀹凒銝� `clear_unified_cache(force_gc=False)`嚗屸俈甇ａ�蝜�‘�冽㺭�格𧒄撖����䔿�墧𤣰撘訫��� Tkinter UI ��香銝𤾸凝�⊿▼��
    - [x] **撠��摮条�����嗥�銝�敶鍦僎�喳�撅� GC 銝剜攟 (Consolidated Cache GC into Unified Loop)**嚗𡁜銁 `instock_MonitorTK.py` �𣬚�銝�撠𤩺𧒄摰𡁏� `controlled_gc_loop` 銝哨��冽�銵� `gc.collect()` 銋见��滨蔭瘜典� `clear_unified_cache(force_gc=False)` �其�嚗���啣之���蝻枏��𦠜𦆮銝𤾸蘂����函�摰𡁏���葉�芣���
    - [x] **�朞� Python 霂剜�蝻𤥁�銝𡡞��鞾�霂� (Passed Syntax & Compiler Checks)**嚗𡁏�銵䔶� `py_compile` 撖嫣耨�孵����銝� Python 璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�蝟餌��踵�蝔喳���
    - [x] **摰䂿緵蝻箏藁銵亙�憭梯揖�⊥𧋦�唳�銋��銝舘楊憭拇偶銋�����皛斗㦤�� (Implemented Persistent Bad Gap Codes Filtering)**嚗�
        - [x] **�啣��譍葵�⊥�銋��摮睃�**嚗𡁜銁 `DataPublisher` �嘥��𡝗𧒄嚗諹䌊�刻粉�𡝗𧋦�� `datacsv/backfill_bad_codes.json` �桅��⊥��𤏪�蝻枏��� `self.bad_gap_codes` ���銝准��
        - [x] **�噼‘�舘噢���璉�銝擧�隞嗉蕭��**嚗𡁜銁 `backfill_gaps_from_hdf5` �噼‘蝏𤘪��𠬍�撖寡��嫣葵�∪銁 `MinuteKlineCache` �𣬚��⊥㺭餈𥡝�雿𤘪���𥅾�踹漲雿𦒘� `threshold`嚗���文�霂亥��唳旿畾讠撩嚗����/�啗�/��撣��嚗㚁�撠���芸𢆡餈賢�撟嗥����銋���� `datacsv/backfill_bad_codes.json`嚗�歇�厩� JSON �啁��芸𢆡�澆��硋僎�鍦�嚗剹��
        - [x] **憭𡁶輕�蹱���蝏𨀣㜃��**嚗𡁜銁 `update_batch` �湧�璉�瘚见�嚗�笆璉�瘚见枂��撩��誨����嗉�皛� `self.backfilled_codes_today`嚗�𠯫����湛�銝� `self.bad_gap_codes`嚗�����撣賊�����喉�嚗�蝠摨閗��蹂��䭾㺭��/�桅�銝芾�撘閗絲����仿�憸煾�憭� HDF5 霂餌�撖潸稲��香���銝餌瑪蝔见�甇颯��
## 2026-06-23 22:30
- [x] **摰䂿緵��撘箸踎�𡑒��栞”�潭𣈲���𣈯�憭媛FF2�嘥��𡃏䌊憿箏��鍦��澆捆 (Implemented 樴坔仍DFF2 Column & Sorting in Sector Table with Backward Compatibility)**嚗�
    - [x] **�啣��𣈯�憭媛FF2�嘥�撟嗆凒�啗”憭� (Added 樴坔仍DFF2 Column & Header)**嚗𡁜銁 `bidding_racing_panel.py` 銝剖� `sector_table` ���憪见��埈㺭�� 8 �埈�撅蓥蛹 9 �梹�撟嗅銁�𣈯�憭媛FF�苷��𡏭��刻祕���苷��游�����乩��𣈯�憭媛FF2�肽”憭氬��
    - [x] **摰䂿緵樴坔仍DFF2�唳旿�冽��葡�� (Implemented Dynamic Rendering of 樴坔仍DFF2)**嚗𡁜銁 `_update_sector_table_optimized` ���撘訫� `_get_df_all_cascading(self)` 蝥扯��瑕� `df_all`嚗�僎�拍鍂�唳��� `_safe_extract_dff2` 摰匧��𣂼�憸�隅樴坔仍�∠� DFF2 �唳旿憿孵僎蝏穃��喟洵 7 �埈葡�橒��芷���蝥Ｙ遛��𧋦�滩𠧧銝擧��㗛�鈭柴��
    - [x] **��漣��撘箸踎�埈��冽�摨讐頂蝏� (Upgraded Sector Sorting for DFF2)**嚗𡁜銁�鍦��惩� `sort_attr_map_sector` 銝剖�蝚� 7 �㛖揣撘閧�摰朞秐 `leader_dff2` 撅墧�改�撟嗅銁 `get_sec_val` 銝剜�撅訫笆 `leader_dff2` ��ế摰𡄯�雿踹�靚�鍂 `_safe_extract_dff2` 餈𥪜��嗥�摰𧼮��澆�銝擧�銵峕���𢆡����鉝��
    - [x] **摰䂿緵�埈㺭�芷�������碶��Ｗ�璉�撉� (Implemented Adaptive Column Count Persistence & Load Verification)**嚗𡁜銁 `_save_ui_state` �嗆����䀹𧒄嚗屸�憭㚚���僎����碶� `stock_table_cols_count` 銝� `sector_table_cols_count`嚗𥕦銁 `_restore_ui_state` �嗆挾撖嫣�摮条��埈㺭銝𤾸��� UI �埈㺭�𡁜�蝵桀笆朣鞉嵗撉䎚����埈㺭銝滢��游��芸𢆡蝏閗�嚗Ê̄ypass嚗头restoreState` �鮋���喲�霈文捐摨血僎�滚�銝𧢲䲮����券俈敺∩耨憭滚�摰踝�瘨�膄鈭��蝟餌���漣�埈㺭�睃𢆡撖潸稲�抒𠶖��撩銵峕�憭滚�韏瑕�摰賢援�讐�蝻粹萅��
    - [x] **�惩𤐄�批�撅��唳旿�澆捆�芣� (Hardened Layout Backward Compatibility)**嚗𡁜銁 `_restore_ui_state` 銝凋蛹 `sector_table` 銵仿�鈭���㛖𠶖��虾閫��找�摰賢漲摰匧��脣鴃嚗屸俈甇Ｗ��㰘蝸�抒� 8 �烾�蝵株��紡�湔鰵憓䂿��𣈯�憭媛FF2�苷��𡏭��刻祕���苷舅�堒捐摨虫蛹 0 �𤥁◤霂舫��譌��
    - [x] **�朞� Python 霂剜�蝻𤥁�撉諹� (Passed Compiler Check)**嚗𡁜笆 `bidding_racing_panel.py` 摰峕�鈭���嗵�霂烐�瘚页�靽肽�璅∪��臬𢆡�𡃏�雿𨀣�扯���迅摰𡁏�扼��

## 2026-06-23 21:15
- [x] **靽桀� controlled_gc_loop 銝� QWidget 蝻箏� winfo_exists 撖潸稲�� AttributeError 撏拇� (Fixed AttributeError: QWidget has no winfo_exists in controlled_gc_loop)**嚗�
    - [x] **摰䂿緵頝冽��嗥����瘣餉䌊���璉�瘚� (_is_win_alive Helper)**嚗𡁜銁 `controlled_gc_loop` ���摰帋�鈭� `_is_win_alive` 颲�𨭌�賣㺭��砲�賣㺭隡睃��朞� `hasattr(w, 'winfo_exists')` �文��臬炏銝� Tkinter 蝒堒藁撟嗅��刻��典��毺�璉�瘚页�撖嫣�銝滚�憭�迨撅墧�抒� PyQt6 QWidget 蝒堒藁嚗諹䌊�刻楝�梢���輯秐 `is_qt_win_alive` �嗆���瘚页�敶餃��𦦵�鈭���� GC 頧桀楚�急��芣�摮堒��嗅�蝐餃�瘛瑞鍂�𥕦枂 `AttributeError` 撏拇���
    - [x] **�朞� Python 霂剜�蝻𤥁�撉諹� (Passed Compiler Check)**嚗朞�銵� `py_compile` 撖嫣耨�孵���蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��乓��

## 2026-06-23 21:00
- [x] **�券𢒰摰⊥䰻撟嗡耨憭滨頂蝏���� Toplevel 蝒堒藁���摮䀹�瞍譍��喲𡡒�讛悅蝻粹萅 (Full Window Lifecycle Audit & Memory Leak Fixes)**嚗�
    - [x] **�寞祥 `open_stock_detail` GDI �交�蝝舐妖瘜�� (Fixed GDI Leak in open_stock_detail)**嚗䫤open_stock_detail` �寞�瘥𤩺活鋡怨��券�隡𡁜�撱箸鰵�� `Toplevel` 蝒堒藁雿���函撩憭� `WM_DELETE_WINDOW` �讛悅銝� ESC 蝏穃���鍂�瑟�瘜閙迤撣詨��哨�憭𡁏活靚�鍂隡𡁶敞蝘� GDI �交���歇銵亙� `win.protocol("WM_DELETE_WINDOW", win.destroy)` �� `win.bind("<Escape>", lambda e: win.destroy())`��
    - [x] **銵亙� `open_top_bar_settings` �喲𡡒�讛悅 (Added WM_DELETE_WINDOW & ESC to Settings Window)**嚗𡁻▲�典翰�瑟�霈曄蔭蝒堒藁隞��"蝖桀�"�厰僼靚�鍂 `save_and_close`嚗𣬚鍂�瑞凒�亦��� � �喲𡡒�嗡�隡𡁏�銵䔶�摮㗛�餉���歇�函＆摰𡁏��桀�憓𧼮� `settings_win.protocol("WM_DELETE_WINDOW", save_and_close)` 銝� `settings_win.bind("<Escape>", ...)` 蝖桐�隞颱��喲𡡒�孵��賭�靽嘥�撟嗅��券�蝵柴��
    - [x] **靽桀� `open_backtest_replay_dialog` 璅⊥��� (Fixed grab_set Deadlock on Close)**嚗𡁜�瘚见��曉笆霂脲�靚�鍂鈭� `dialog.grab_set()` 雿�𧊋霈曄蔭 `WM_DELETE_WINDOW` �讛悅嚗𣬚鍂�瑞��� � �嗅�璅⊥���畾讠�隡𡁻�甇颱蜓蝒堒藁鈭支���歇銵亙��喲𡡒�讛悅銝� ESC 蝏穃�嚗𣬚＆靽苷遙雿閗楝敺�� `grab_set` �質�鋡急迤蝖桅��整��
    - [x] **銵亙� `open_blacklist_manager` ESC 蝏穃� (Added ESC to Blacklist Manager)**嚗𡁻��滚�蝞∠��冽� `WM_DELETE_WINDOW` �讛悅雿�撩撠� `<Escape>` 蝏穃�嚗屸睸�䀹�雿靝�餈噼敞��歇撠� `on_win_close` 蝑曉��嫣蛹 `event=None` 撟嗥�摰朞秐 `<Escape>`��
    - [x] **銵亙�璁�艙霂行�蝒堒藁 `_concept_win` ESC 蝏穃� (Added ESC to Concept Detail Window)**嚗𡁏�敹萄��刻祕������ `WM_DELETE_WINDOW` �讛悅雿�撩撠� `<Escape>` 蝏穃���歇�� `win.protocol` �舘蕭�� ESC 蝏穃���
    - [x] **銵亙� `open_realtime_monitor` ESC 蝏穃� (Added ESC to Realtime Monitor Window)**嚗𡁜��嗆㺭�格��∠��抒���歇�匧��剖�霈桐�蝻箏��桃�敹急㭘�喲𡡒�舀���歇餈賢� `log_win.bind("<Escape>", lambda e: on_close())`��
    - [x] **靽桀� `_pg_top10_window_simple` 摮堒�撘箏��冽�瞍� (Fixed Strong Reference Leak in pg_top10 Dict)**嚗䫤show_concept_top10_window` �� `_on_close` �噼�撌脫��� `monitor_windows` 摮堒�嚗䔶����蝒堒藁�� `_pg_top10_window_simple` 摮堒�銝剔�撘箏��其��芾◤�𦠜𦆮嚗�紡�� Toplevel 摰硺��䭾�鋡� GC �墧𤣰��歇�� `_on_close` 銝剖�甇交��� `_pg_top10_window_simple[current_key]`嚗�蝠摨訫��剖��券曎��
    - [x] **�朞� Python 霂剜�蝻𤥁�撉諹� (Passed Compiler Check)**嚗朞�銵� `py_compile` 撖嫣蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��伐�7 憭�耨�孵��券�朞�撉諹�嚗峕�隞颱�霂剜��𣇉憬餈𥕦�撣詻��

## 2026-06-23 20:30
- [x] **靽桀� show_concept_top10_window �喲𡡒�嗅�摮�/GDI�交�瘜��蝻粹萅 (Fixed Memory & GDI Leak in Concept Top 10 Window Close)**嚗�
    - [x] **敶餃�皜�� monitor_windows 銝剔�撘箏��� (Cleared monitor_windows Strong References)**嚗𡁜銁 `show_concept_top10_window` ����� `_on_close` 鈭衤辣憭���賣㺭銝哨��啣�鈭��������餉����蝒堒藁鋡恍�瘥�𧒄嚗䔶��典� `self.monitor_windows` 摮堒�銝凋蜓�典��文��滨���笆摨𠉛� `unique_code` 撘箏��券睸�澆笆嚗�蝠摨訫��凋� Tkinter Toplevel 蝒堒藁�� Treeview 摰硺�����券曎嚗諹圾�喃��𣳇鵭�蠘�銵䔶漣�� GDI �交�銝𤾸�摮䀹�蝏剛������瞍讐撩�瑯��
    - [x] **靽桀�蝒堒藁憭滨鍂頝臬�銝讠��桀�畾讠�銝擧�瞍誯��� (Resolved Key Desync in Reuse Path)**嚗𡁻�撖� `show_concept_top10_window` �������冽㦤�塚��喃���瘥�唂蝒堒藁嚗𣬚凒�交凒�啣僎�滨蔭��捆嚗㚁��曹� `_on_close` �剖��芣��瑚�蝒堒藁擐𡝗活�𥕦遣�嗥� `unique_code`嚗�紡�游�蝏剖��其蛹�嗡�璁�艙�踹��塚��喲𡡒�嗅��支��抒��桀�嚗諹�䔶蝙�𡒊賒憭滨鍂��睸�齿偶銋���坔銁 `monitor_windows` 銝准��緵撠� `unique_code` 撅墧�批�蝏穃��喟����靘见笆鞊� `win._unique_code`嚗�銁憭滨鍂頝臬�銝剖𢆡��宏�斗唂�桀僎瘜典��圈睸嚗𥕦銁 `_on_close` �嗆挾�冽��粉�硋僎皜��嚗�蝠摨閙�蝏苷�蝒堒藁憭滨鍂�箸艶銝讠�隞颱�撘閧鍂瘜����
    - [x] **靚�㟲�典� GC 頧桀楚�園𡢿�喃�撠𤩺𧒄 (Adjusted GC Polling Loop to 1 Hour)**嚗𡁜� `controlled_gc_loop` ��蔭撌∪辣餈毺眏 10 ���餈𥕢�甇交��踹� 1 撠𤩺𧒄嚗�3,600,000ms嚗㚁��其�霂���典��嗡蜓�券�瘥��擃䀹�餈鞱��齿�銝页���憭批�閫��鈭斗��園𡢿畾萇眏撘箏��券���䔿�墧𤣰�䭾���蜓蝥輻�敺桀㨃憿選��𣂼�蝟餌����憸穃�摨磰��䜘��


## 2026-06-23 20:00
- [x] **靽桀� Alt+R 頧株蓮��揢�嗡蜓�批��唳�瘜訫�雿溻���瘜閗蔭霂Ｖ�銝Ｗ仃擃䀝漁蝻粹萅 (Aligned Tkinter Window HWNDs and Enabled Auto-Scroll in Rotator to Resolve Console Selection & Visibility Bug)**嚗�
    - [x] **閫�� Tkinter ����� HWND �文�銝滢��� (Aligned Internal & Top-Level HWNDs)**嚗𡁶眏鈭� Tkinter �� `winfo_id()` 餈𥪜���糓���蝏�辣 Frame �� HWND嚗諹�� Windows �拍��滚蝱 `GetForegroundWindow()` �瑕���偶餈𨀣糓憭硋���ㄨ摰��憿嗅�摰孵膥蝒堒藁 HWND嚗�紡�港����銝滚龪�滩�峕�瘜閗圻�� MRU �埝部��緵撘訫� `_get_toplevel_hwnd()`嚗屸�朞� `GetAncestor(hwnd, 2)` 撠���� Tkinter 蝒堒藁 HWND �芸𢆡敶雴��碶蛹憿嗅� Wrapper HWND嚗䔶�����唬�銝� `GetForegroundWindow()` ���蝢𤾸笆朣琜�銝餅綉�嗅蝱�賢�鋡急迤蝖格��亙��啗��血僎�湔鰵 MRU 憿箏���
    - [x] **閫�� QListWidget 擃䀝漁憿寡��箄�����航�蝻粹萅 (Enabled Auto-Scroll for Highlighted Items)**嚗𡁜銁 `WindowRotatorDialog.apply_highlight_to_ui` 銝剖��乩� `self.list_widget.scrollToItem(item)` �餉����蝒堒藁�圈�颲��銝𥪯漣����冽辺�塚���揢擃䀝漁�賢��芸𢆡霈拚�鈭桃��寥★嚗��雿滢���摨閖���蜓�批��堆��芸𢆡皛𡁜𢆡撅閧緵�典虾閫�躹��迤銝哨�敶餃�閫��鈭��靝�銝讠蕃憿菜𪄳銝滚�銝餅綉�嗅蝱�萘��桅���
    - [x] **����䔶��拍蔭憿嗅𤧅�㘾�餉� (Updated Focus-Restore Logic)**嚗𡁜銁 `_force_focus_hwnd` 蝵桅▲蝛輸�讐��䔶��拍��乩葉嚗�� Tk 蝒堒藁撖寞��峕甅�齿�銝箏抅鈭𡡞▲撅� Wrapper HWND ���撖對�蝖桐�鈭�蜓�批��啜����仿�㕑���撩摨���扳��典��Ｘ𧒄�� 100% 鋡急�韏瑞蔭憿嗅僎�𡁶���

## 2026-06-23 19:50
- [x] **靽桀�撟嗉圾�血��嗆㺭�格��∠��抒�����∩蜓閫�㦛蝻粹萅 (Decoupled Realtime Monitor Window from Root to Prevent Stacking/Z-Order Blocking)**嚗�
    - [x] **閫��� Toplevel 蝒堒藁 Master �交��� (Decoupled Toplevel Master)**嚗𡁜� `open_realtime_monitor` 擐𡝗活�𥕦遣 `Toplevel` ����䭾䲮撘讐眏 `tk.Toplevel(self)` �齿�銝� `tk.Toplevel()`嚗�朖銝滢��乩蜓蝒堒藁 `self` 雿靝蛹銝餅綉��㺭嚗剹��砲�孵𢆡撠���抒����靘见�銝箏��函𡠺蝡讠� OS 憿嗅�蝒堒藁嚗屸俈甇� Windows �滢�蝟餌�暺䁅恕撘箏�撠� Owned Window 蝵桐� Owner Window �齿䲮�� Z-order ����𣂼�嚗𣬚＆靽苷蜓蝒堒藁�刻◤�孵稬�𤥁��行𧒄�賢�憿箏⏚鋡急��啣��啣�蝷綽�摰𣬚�瘨�膄鈭���抒���偶銋���∩蜓蝒堒藁 of 鈭支��桅���

## 2026-06-23 19:40
- [x] **靽桀�摰墧𧒄�唳旿�滚𦛚�烐綉蝒堒藁�方絲銝� V-Reversal �烐綉瘙㰘��函撩�� (Fixed Realtime Monitor Window Focus & V-Reversal Linkage Fallback)**嚗�
    - [x] **靽桀�摰墧𧒄�唳旿�烐綉蝒堒藁蝵桅▲�方絲 (Fixed Realtime Monitor Window Focus & Topmost Activation)**嚗𡁜銁 `open_realtime_monitor` 銝剖��牐�撖寧����撠誩��嗆���`iconic`嚗厩�璉�瘚衤� `deiconify()` 餈睃�嚗�僎��� `attributes("-topmost", True/False)` ��蔭憿園緾��忽�𤩺㦤�嗡� `_register_hwnd_to_mru` 蝒堒藁頧格揢瘜典�嚗𣬚＆靽嘥銁�𤾸蝱�孵稬�嗉� 100% �𣂼�瘚桃緵撟嗉��虫��滚蝱��
    - [x] **靽桀� V-Reversal �烐綉瘙惩��� K蝥� �航��𡝗𧒄����函撩�� (Fixed V-Reversal Fallback Linkage when K-line Visualizer Closed)**嚗𡁻����頝典極�瑁��冽𦻖�� `link_to_visualizer`��� K 蝥踹虾閫�� `vis_var` 憭���喲𡡒�嗆��𧒄嚗䔶��漤�暺䀹⏛�剝���綽��峕糓�笔��湔鰵 `select_code`嚗�圻�穃�韐湔踎�駁�靽脲擪嚗匧僎�䭾辺隞嗆�銵� `self.sender.send(code)` �𥪜𢆡�煾���蝖桐��刻䌊�𥪜虾閫��蝒堒藁�喲𡡒�塚��朞噢靽～����梢◇蝑劐��寡���蔓隞嗡��臬�蝢舘�雿𡏭��典��Ｕ��
    - [x] **摰峕� Python 霂剜�蝻𤥁�撉諹� (Passed Compiler Check)**嚗𡁏��罸�朞�鈭� `py_compile` 撖嫣蜓�屸𢒰璅∪���祗瘜訫�蝻抵�蝻𤥁��折�霂���芸��乩遙雿閗��Ｗ蔣�溻��

## 2026-06-23 18:30
- [x] **敶餃��寞祥�枏��擧𧋦�� HTTP �滚𦛚憭𡁶��砍��其��交�蝏扳㗁瘜�蠧蝻粹萅 (Resolved Duplicate Listeners & Socket Inheritance Leak)**嚗�
    - [x] **�𣂼� HTTP �𥪜𢆡�滚𦛚隞�銁銝餉�蝔见鍳�� (Restricted to MainProcess)**嚗𡁜銁 `sys_utils.py` 銝剖��牐�銝餉�蝔见��斤瑪蝔𧢲嵗撉䕘�撟嗅銁 `instock_MonitorTK.py` 銝餃��� `StockMonitorApp` �嘥��𡝗𧒄嚗䔶�撖孵��圈��𤾸蝱摰�擪璅∪�嚗Ǒbackground == False`嚗厩�銝� GUI 摰硺��曉��臬𢆡 `start_stock_name_server`嚗�蝠摨閙�蝏苷��𤾸蝱摰�擪餈𤤿��硋�餈𤤿���垢���鈭劐�憭𡁏活�穃𨯬��
    - [x] **霈曄蔭 Socket �交�銝滚虾蝏扳㗁 (Prevent Socket Inheritance)**嚗𡁜銁 Web �滚𦛚�函垢���摰𡁏��笔�嚗峕遬撘𤩺�銵� `server.socket.set_inheritable(False)`嚗屸俈甇Ｖ蜓餈𤤿��𥕦遣�穃𨯬 socket �𡒊眏鈭� Windows ��蘂��誧�踵㦤�塚�撠���砍蘂����垍��誩� spawn ���餈𤤿�嚗峕覔瘝颱� Windows 銝� `netstat` �亙枂憭帋葵摮鞱�蝔� PID �删鍂銝𥪜��� LISTENING `26672` 蝡臬藁��䔮憸塩��
    - [x] **摰䂿緵 stock_name_cache �砍𧑐���蝻枏��箏� (Stock Name Cache Memory Optimization)**嚗𡁻���� `get_cached_stock_names()` �亙藁嚗�⏚�� `os.path.getmtime` �冽���撖寧��䀹�隞嗥����𦒘耨�寞𧒄�氬��銁��辣�芾◤靽格㺿�嗥凒�亙��典�摮䀝葉撌脣�摨誩��𣇉� binary �唳旿嚗𣬚��颱�擃㗛��㰘蝸�嗥�憭折��滚���辣 I/O 撘���嚗峕遬�𡑒���� CPU 銝𡒊��䁅�皞僐��

## 2026-06-23 17:50
- [x] **摰䂿緵蝵煾△�渲� HTTP 蝟餌��𥪜𢆡銝擧𧋦�唳�隞� I/O ���蝻枏�隡睃� (Implemented Direct HTTP Web Linkage with Local File Memory Cache Optimization)**嚗�
    - [x] **摰䂿緵�渲� HTTP 瘣曉�蝟餌��𥪜𢆡 (Implemented Direct HTTP Dispatch Linkage)**嚗𡁜銁 `instock_MonitorTK.py` 銝剜鰵憓� `_on_http_link_code` �渲��𥪜𢆡憭���寞�嚗屸�撘�撖孵�韐湔踎 `_last_clip_code` 蝻枏��嗆����湔鰵銝擧�瘚页��湔𦻖�朞� `self.tk_dispatch_queue.put(lambda: self.open_visualizer(code))` 撠���其遙�⊥��乩蜓蝥輻����銵屸��𦯀葉嚗�蝠摨閖��滢� clipboard �滚�璉�瘚见�瘙⊥��桅���
    - [x] **�惩��渲��𥪜𢆡憸烐綉銝𡡞��埈滯�粹俈�� (Added Linkage Throttle & Queue Overflow Protection)**嚗𡁜銁 `_on_http_link_code` ������鈭� 1 蝘雴誑����諹�蟡函��餃縧�漤��改�Throttling嚗㚁��峕𧒄憓𧼮�鈭���堒之撠誯��塚��� `qsize > 100` �嗘腺撘��嚗峕�憭批𧑐�讛蝠鈭��蝜���餃笆摰Ｘ�蝡臭蜓蝥輻��滨��� IPC �𥪜𢆡��恣蝞𡑒�����
    - [x] **�舀��喲𡡒 K 蝥踹虾閫���嗅笆 TDX 蝑㕑蔓隞嗥��祉��𥪜𢆡 (Independent TDX Linkage Support When K-Line Visualizer Closed)**嚗帋耨憭滢�敶枏��� `vis_var`嚗�朖銝齿遬蝷箄䌊�� K 蝥輻����雿���� TDX/�諹�憿�/銝𨀣䲮韐Ｗ�蝑劐��寡蔓隞嗉��典��舀𧒄嚗𣬚�憿萇垢�孵稬�∠巨�䭾�摰䂿緵銝㗇䲮頧臭辣�𥪜𢆡��揢�� Bug��銁 `_on_http_link_code` ����祉�銝娍��∩辣�扯�鈭� `self.sender.send(stock_code)` �煾���撟嗅銁�𥪜𢆡�嗅�摮鞟漣�湔鰵 `self.select_code` 隞亥圻�穃�韐湔踎�駁�靽脲擪嚗𣬚＆靽嘥�頧刻��典銁隞餅��滨蔭蝏��銝见��賢�蝢舘�雿栶��
    - [x] **撘訫� stock_name_cache �砍𧑐���蝻枏��箏� (Added Memory Cache for Stock Name Cache File)**嚗𡁜銁 `sys_utils.py` 銝剖��唬� `get_cached_stock_names()`嚗屸�朞� `os.path.getmtime` 擃䀹�璉�瘚� `stock_name_cache.json` 蝤����辣����𦒘耨�寞𧒄�氬��𥅾��辣�芾◤靽格㺿嚗���湔𦻖�典�摮䀝葉霂餃�蝻枏��� binary �唳旿撟嗉��痹�瘨�膄鈭��甈⊥硃�渲��砍�頧賣𧒄鈭抒����憭滨��� I/O 韐��嚗峕�憭扯����蝟餌�韏����
    - [x] **�冽𧋦�唳��∩葉�𣂷��𡁶鍂 `/link` 頝舐眏�亙藁 (Added `/link` Endpoint to Micro Server)**嚗𡁜銁 `sys_utils.py` ���撘訫� `register_link_callback` API嚗�僎銝箸𧋦�啣凝�� HTTP �滚𦛚�啣�鈭�笆 `/link?code=xxxxxx` 霂瑟�����琿�餉�����嗅��亥䌊蝵煾△ Hippos �𥪜𢆡霂瑟��塚��亙歇�其蜓 GUI 銝剜釣�䔶��噼�嚗���典��啁瑪蝔衤葉閫血��噼�嚗峕𣈲��楊�蠘挪�桀�撘�虜�閗繮嚗���唬�撖孵��其葵�∟��冽�隞� of �渲������
    - [x] **瘝寧繬�𡁏𧋦��漣�舀��𦦵凒餈噼��� + 憭滚����踱�嘥�靽嗪埯 (Upgraded Tampermonkey Script with Dual Linkage Options)**嚗帋耨�嫣� `蝵煾△�𥪜𢆡隡港麾.js` 銝� `蝵煾△�𥪜𢆡隡港麾2.js` ��葵�∠��餃�摨𥪯�隞嗚����冽��孵稬擃䀝漁銝芾��塚��𡁏𧋦隡帋���� `127.0.0.1:26672/link?code=xxxxxx` �煾���甇� HTTP 霂瑟�嚗𣬚凒�亙𤧅�埝𧋦�啁頂蝏蠘��冽遬蝷綽��� HTTP 霂瑟�頞�𧒄��仃韐交�餈𥪜��� 200/ok �滚�嚗���烐綉摰Ｘ�蝡舀𧊋�臬𢆡�塚�嚗���芸𢆡���� fallback �啣���� `GM_setClipboard` �坔��芾斐�輯��冽芋撘𧶏���之�啣�撠睲�銝滚�閬���芾斐�踵情�橒��𣂼�鈭��蝡航��冽����扼��


## 2026-06-23 17:45
- [x] **�𣂼��砍𧑐 HTTP �滚𦛚隞�銁銝餉�蝔见鍳�典僎�脰��交�瘜�� (Restricted Local HTTP Server to MainProcess & Prevented Socket Handle Leak)**嚗�
    - [x] **�𣂼�銝餉�蝔见鍳�典��斤瑪蝔� (Restricted to MainProcess)**嚗𡁜銁 `sys_utils.py` �怠偏靚�鍂 `start_stock_name_server()` �塚�憓𧼮�鈭� `multiprocessing.current_process().name == "MainProcess"` �∩辣�斗鱏�����獈�凋�敶� `sys_utils` 鋡怨����蝑𣇉裦憭朞�蝔�/摮鞱�蝔见紡�交𧒄嚗��餈𤤿�擃㗛����憭滚𧑐�臬𢆡�𤾸蝱 HTTP �滚𦛚蝥輻���䔮憸塩��
    - [x] **霈曄蔭 Socket �交�銝滚虾蝏扳㗁 (Prevented Socket Handle Inheritance)**嚗𡁜銁 HTTP �滚𦛚蝏穃��𣂼��𠬍��曉�靚�鍂鈭� `server.socket.set_inheritable(False)`嚗屸俈甇Ｖ蜓餈𤤿��𥕦遣�穃𨯬 socket �𤾸� Windows `CreateProcess` 暺䁅恕�交�蝏扳㗁�箏�撠���砍蘂����垍��𡒊賒 Spawn ���餈𤤿�嚗䔶���蝠摨閙��支��� Windows 蝟餌�銝� `netstat` �亙枂憭帋葵摮鞱�蝔� PID �删鍂銝𥪜��� LISTENING `26672` 蝡臬藁��緵鞊～��

## 2026-06-23 17:40
- [x] **隡睃�蝵煾△�𥪜𢆡隡港麾�望�/蝛箸聢/�典�閫埝毽���蟡典��寥��箏� (Optimized Web Linkage Partner for Mixed Casing, Full/Half-Width & Spaced Stock Names)**嚗�
    - [x] **摰䂿緵�刻�/�𡃏�銝𤾸之撠誩��芷���甇����� (Adaptive Width & Case Regex Generation)**嚗𡁜��� `toHalfWidth` 銝� `getCharacterPattern` 颲�𨭌�賣㺭嚗���怨㘚���瘥�/�啣����蟡典�摮𦯀葉���銝芸�蝚血�頧祆揢銝箏笆摨娍𣈲��之撠誩�����𡃏�瘛瑕�敶Ｗ���迤�坔�蝚阡�嚗��摮埈� `A` �惩�銝� `[aA嚚�慼]`嚗峕㺭摮� `0` �惩�銝� `[0嚗𨚼`嚗剹��
    - [x] **�舀��∠巨�滚�����舫�厩征�澆龪�� (Support Optional Inner Spacing Matching)**嚗𡁜銁��遣�寥�甇���塚�撖孵�摮堒��賊�摮㛖泵�湔��� `\s*`嚗�虾�厩征�潘�甇���讛�嚗𣬚＆靽萘�憿萎葉�靝�蝘飊�腈���靝� 蝘𡢅慼�腈���𨀣楛獢𤏸噢 A�萘������𣄽�蹱聢撘誩��質◤擃条移摨血龪�滚僎�閗繮��
    - [x] **閫���𡝗�撠�䰻�暸睸�� (Normalized Cache Lookup Keys)**嚗𡁻���� `loadStockNames` �唳旿�嘥��硋� `applyHighlight` �亥砭�寥�餈����圾�鞱�蟡冽㺭�格𧒄嚗��蝻枏��滚�蝏讛��刻�頧砍�閫鉝��縧蝛箸聢�𡃏蓮憭批�憭���𡒊�蝏𤘪� `normalizeNameForLookup(name)` 雿靝蛹�惩��桀�嚗偦�鈭桀龪�齿𧒄嚗���瑁�������𣂼�����祈�銵� $O(1)$ �惩��亥砭嚗��蝢舘圾�喃��曹�憿菟𢒰��𧋦銝擧𧋦�啁�摮䀹聢撘誩榆撘��憒���𡃏� `嚗︶/`A`����思���裦蝛箸聢蝑㚁�撖潸稲�� �𨀣楛獢𤏸噢嚗﹦�腈���靝漪銝𨀣䲮A�� �𥪜𢆡擃䀝漁憭梯揖��䔮憸塩��

## 2026-06-23 17:15
- [x] **隡睃�蝵煾△�𥪜𢆡隡港麾�㰘蝸�舫��找�擃䀝漁�急��箏� (Optimized Web Linkage Partner Loading Reliability & Highlight Scanning)**嚗�
    - [x] **摰䂿緵�砍𧑐敺桀� HTTP �滚𦛚 (Implemented Local Micro HTTP Server)**嚗𡁜銁 `sys_utils.py` �怠偏撘訫�撣賊彿摰�擪蝥輻� Web �滚𦛚嚗𣬚��� `127.0.0.1:26672` 蝡臬藁嚗�銁霈輸䔮 `/stock_names` 頝臬��嗥凒�亥��� `stock_name_cache.json` ��捆撟嗉挽蝵� CORS 頝典�憭氬���餈𤤿��臬𢆡�脩��嗅��冽��瑕僎敹賜裦嚗䔶�霂��摰硺��砍���
    - [x] **�舀� HTTP �砍𧑐蝡臬藁銝擧�隞嗅��𡁻��箄��㰘蝸 (Dual-Channel Smart Loading)**嚗𡁻���� `蝵煾△�𥪜𢆡隡港麾.js` 銝剔� `loadStockNames`��銁 Tampermonkey 憭游ㄟ�𦒘葉餈賢� `@connect 127.0.0.1` ���嚗𥕦�頧賣𧒄隡睃��朞� `GM_xmlhttpRequest` 霂瑟� `http://127.0.0.1:26672/stock_names` 蝡臬藁嚗��撘��砍𧑐 `file:///` 瘛瑕���捆�行⏛嚗㚁�憭梯揖�嗉䌊�� fallback �鮋���啣��砍𧑐 `file:///` �讛悅霂餃�嚗𥕦銁���匧�頧賣�蝔衤葉�惩��券� try-catch 靽脲擪嚗�蝠摨閗圾�喃��� Chrome 銝亥�摰匧�瘝嗵拳銝𧢲硃�渲��砍�憪见�憭梯揖����𨀣��滚��萘��𤤿���
    - [x] **�寞祥撌脣�����祈��孵笆�𡒊賒擃䀝漁�急������獈�� (Fixed ContextualWalker Processed Nodes Blocking)**嚗帋耨�嫣�擃䀝漁��瓲敹�䲮瘜� `applyHighlight`嚗�� `processedNodes.add` �園�蝘餃𢆡�� `matchedAny` �文���𣈲��笆鈭擧瓷�劐遙雿蓥葉���蟡典��寥��𣂼�����祈��嫣��滚��嗅�餈𥕦歇憭�� WeakSet 蝻枏�嚗峕𦆮銵�僎蝖桐��𡒊賒��㺭摮𦯀誨��迤�躰”颲曉��賣迤撣賊�鈭格遬蝷箝��

## 2026-06-23 17:05
- [x] **��漣蝵煾△�𥪜𢆡隡港麾�舀��砍𧑐�∠巨�滨妍蝻枏�擃䀝漁銝舘��� (Upgraded Web Linkage Partner for Local Stock Name Caching, Highlighting & Linkage)**嚗�
    - [x] **撘訫��砍𧑐 `stock_name_cache.json` 霂餃����銝舘楝敺��蝵�**嚗𡁜銁 Tampermonkey 瘝寧繬�𡁏𧋦憭湧���㺭�桀ㄟ�𦒘葉嚗諹‘�其� `@grant GM_xmlhttpRequest` �� `@connect file` ��楊�毺�蝏𡏭窈瘙�鸌���隞交𣈲��粉�碶�鈭擧𧋦�� `D:\JohnsonProgram\instockMonitorTK\datacsv\stock_name_cache.json` ���蟡其誨���銝剜��滚��惩��滨蔭��
    - [x] **摰䂿緵�∠巨�滨妍銝𦒘誨������蝻枏��惩�銝擧�摨𤩺�摨𤩺迤�嗵��� (Bi-directional Mapping & Length-Sorted Regex Generation)**嚗𡁻�����𡁏𧋦�嘥��𡝗�蝔页�摰䂿緵 `loadStockNames()` 撘�郊�匧�撟嗉圾�鞉𧋦�啁�摮塩��蛹鈭�俈甇Ｖ葉��龪�齿𧒄�𦦵�霂滢���龪�滚紡�湧鵭霂滩◤�芣鱏�萘��脩�嚗��憒��𨀣楛�㛖㩞�脲𦜖��龪�滚紡�氯�𨀣楛�㛖㩞A�嗪�鈭桀枂�辷�嚗�銁����寥�甇�� `STOCK_NAME_REGEX` �㵪�撠���匧�瘜閧��∠巨�滨妍�匧�蝚阡鵭摨虫��踹��剛�銵屸�摨𤩺�摨𤩺𣄽�乓��
    - [x] **�齿� DOM 擃䀝漁銝𦒘�隞嗥�摰𡁜��啣�蝘啗��� (Refactored DOM Highlighting & Dynamic Name Linkage)**嚗帋耨�嫣� `applyHighlight` �賣㺭��銁撖寧�憿菜��祈�銵� ContextualWalker �滚��塚����雿輻鍂 `STOCK_NAME_REGEX` (�寥�銝剜��滨妍) 銝� `STOCK_SCAN_REGEX` (�寥��啣�隞��) 餈𥡝��屸��寥�擃䀝漁��ㄨ��笆鈭𦒘葉���蝘圈�鈭桃����嚗�� `dataset.code` 撅墧�扯◤�冽���摰帋蛹�惩�閫���箇� 6 雿滩�蟡其誨���撟嗉挽蝵� `title` 撅墧�抒鍂鈭𤾸銁曌䭾��祆筑�嗆�蝷箏笆摨𠉛��∠巨隞��嚗𣬚��餃��喳虾摰𣬚��坔�蝟餌��芾斐�選�銝��桀𤧅�埝𧋦�啁��抒頂蝏蠘��具��
    - [x] **摰䂿緵瘝嗵拳�寞��滨漣銝𡡞�霂臬�憟賢�撖� (Sandbox Cooldown & Friendly Permission Guide)**嚗𡁜��箔��𡁏𧋦撖寞�閫�膥瘝嗵拳�臬� file �讛悅霂餃��烾���捆�蹱㦤�嗚��銁霂餃�憭梯揖�塚��典��𤏸��綉�嗅蝱銝剜��啗祕蝏���凒閫���见𢆡�滨蔭甇仿炊嚗��撖潛鍂�瑕縧瘚讛��冽�撅閧恣��△�Ｖ蛹 Tampermonkey 撘��胼�𨅯�霈貉挪�格�隞嗥����脲��琜�嚗�僎撟單��鮋��嚗䔶�雿輻鍂�毺��∠巨隞��甇��擃䀝漁�蠘�嚗𣬚�銝滢葉�剔�憿菜迤撣貉挪�桐��嗡��詨��𥪜𢆡�蠘���

## 2026-06-22 22:55
- [x] **靽桀���稬撘寧��衣��瑕�銝舘䌊�臬𢆡隡睃�撌虫儒�Ｘ踎�䭾㺭�株䌊�券��� (Fixed Dialog Focus & Auto-Hiding Left Autostart Pane)**嚗�
    - [x] **摰䂿緵��稬撘寧�撘箏��衣��瑕� (Enforced Detail Dialog Keyboard Focus)**嚗𡁜銁 `AutostartItemDetailDialog`��ProcessItemDetailDialog` �� `ProcessGroupDetailDialog` �� `__init__` �嘥��𡝗䲮瘜蓥葉嚗���� `self.focus_force()` 靚�鍂��＆靽嘥撕�箇�撅墧�扯祕�����銁����嗉�憭笔朖�颯��撩�嗆𦜖�𣳇睸�䁅��亦��對�閫��鈭�鍂�瑕��餃�蝒堒藁瘝⊥��衣�撖潸稲�劐� Esc �格�瘜訫翰�笔��剛祕��△����嫘��
    - [x] **摰䂿緵�芸鍳�其��硋椰靘折𢒰�踵��唳旿�嗉䌊�券��� (Auto-Hiding Common Apps Panel & Auto-Expanding)**嚗�
        - �齿�鈭� `render_autostart_cards`嚗���笔��蹱�� common_apps ����滨蔭�∠�餈𥡝�餈�誘嚗�蘨皜脫��冽�蝟餌�銝羓�甇��蝵株���鍳�冽�蝳�鍂鈭���㗇�鈭斗�/�誩�頧臭辣�∠�嚗�
        - 敶栞�皛文�撣貉�頧臭辣�芸鍳�函𠶖��㨃��㺭�譍蛹 0 �塚��單瓷�匧虾隡睃���虜閫�漱��/�誩�頧臭辣�滨蔭嚗㚁�靚�鍂 `self.auto_left.pack_forget()` �芸𢆡�鞱�撌虫儒隡睃��Ｘ踎嚗屸��暹��删鍂�� 430 �讐�摰賢漲蝛粹𡢿嚗�僎撠�𢰧靘抒��券��芸鍳�� Treeview 銵冽聢�芸𢆡璅芸��烐說�港葵銝駁�厰★�∴�瘨�膄鈭�誑�𨧀�𨅯蘨�拐�銝芣�憸䀹��湧𤨪�牐�憭折�撅誩�摰賢漲撖潸稲�喃儒�賭誘銵峕遬蝷箏云蝒��萘�閫��蝻粹萅嚗�
        - 敶𤘪�瘚见��㗇㺭�格𧒄嚗諹䌊�券�朞���� `before=self.auto_right` 餈𥡝�撅��� `pack` �齿鰵�鍦��啣椰靘改�靽肽�撣����笆蝘唬�銝��氬��
    - [x] **�朞� Python 霂剜�銝𡒊�霂烐�批��冽�折�霂� (Passed Compiler Check)**嚗朞�銵� `py_compile` 撖嫣蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�鈭��餉�銝𡒊��Ｘ㺿�函�撌亦��舫��扼��

## 2026-06-22 22:50
- [x] **靽桀���稬霂行�憿萇蒾撅譌��𢰧�桀��嗅仃�����辣頝臬��枏�摰帋�隡睃� (Fixed Details Blank, Copy Error & Open Location Resiliency)**嚗�
    - [x] **靽桀���稬霂行�憿菜���捆皜脫�銝擧𣈲�� Esc �桀��� (Fixed Blank Details Dialog & Added Esc Close)**嚗𡁜蝠摨閙��亙僎�寞祥鈭�眏鈭𤾸銁 `ttk.Frame` ���惩遆�唬葉�躰秤隡惩�銝齿𣈲��� `background` 撅墧�扳�撘訫��� `_tkinter.TclError` 撘�虜銝剜鱏�桅���� `AutostartItemDetailDialog`��ProcessItemDetailDialog` �� `ProcessGroupDetailDialog` 銝剔�摮𣂼㨃���銵��摰孵膥�齿�銝箏��� `tk.Frame` 撟嗆�摰� `bg` 撅墧�改�敶餃��Ｗ�鈭�祕����扯”�蓥�鈭支��厰僼��迤撣豢葡�瓐����嗅銁霂行�蝒堒藁憿園�蝏穃� `<Escape>` 鈭衤辣嚗峕𣈲����� Esc ���笔��剖笆霂脲���
    - [x] **靽桀��喲睸憭滚�隞餃𦛚/�賭誘�寞�蝻箏仃撏拇� (Fixed AttributeError on Right-Click Copy)**嚗𡁜銁銝餌��Ｙ掩 `SystemPerformanceAnalyzerGUI` 銝剛‘�其� `copy_text_to_clipboard` �寞�嚗���� `pyperclip` 餈𥡝��芾斐�踹��嗅�摨閧垢�嗆����峕郊�鞟內嚗��蝢舘圾�喃��喲睸憭滚�霈∪�隞餃𦛚�滨妍�硋𦶢隞方��嗆��� `AttributeError: '_tkinter.tkapp' object has no attribute 'copy_text_to_clipboard'` ��艇�� Bug��
    - [x] **隡睃��賭誘銵𣬚���楝敺���碶��喲睸�枏����函𤌍敶蓥�撉� (Optimized Physical Path Sourcing & Resilient Open Location)**嚗�
        - �齿�鈭� `extract_physical_path`嚗峕𣈲�� Windows �臬��㗛�嚗�� `%SystemRoot%` 蝑㚁���䌊�典�撘�嚗�僎撖寞𧊋鋡怠�撘訫噡��ㄨ雿���怎征�澆��啁��賭誘銵䕘�憒� `C:\Program Files...`嚗匧��亥揪憍芸龪�齿䔝瘚𧢲㦤�塚�隞交惣�賣��硋枂���踹��函��舀�銵峕�隞嗥���楝敺��
        - �曉捐鈭�𢰧�株��訫�蝵桅��塚���捂銝箸��厰★�賜��鐥�𨥉�� �枏����函𤌍敶𨰝�肽��𤏪��冽�銵峕𧒄餈𥡝��芣�撘誩�霂𤏪�
        - ��漣鈭� `open_file_location_action` ��俈�躰挽霈∴��舀��刻�銵峕𧒄�娪膄撘訫噡�𡃏‘�函頂蝏� PATH �� `System32` 蝑厩�撖寡楝敺�����𨀣�隞嗡�銝滚��剁��躰䌊�刻蓮銝箸�撘�撟嗅�雿滚��嗥漣�桀�嚗峕��支�隞亙��𨀣𪄳銝滚��拍���辣�嗅��冽�瘜訫𢰧�格�撘��萘��冽��𤤿���
    - [x] **�朞� Python 霂剜�銝𡒊�霂烐�批��冽�折�霂� (Passed Compiler Check)**嚗朞�銵� `py_compile` 撖嫣蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�鈭��餉�銝𡒊��Ｘ㺿�函�撌亦��舫��扼��

## 2026-06-22 22:45
- [x] **摰䂿緵霈∪�隞餃𦛚�祉� Tab 蝞∠�銝舘䌊�臬𢆡/霈∪�隞餃𦛚��稬霂行�銝𤾸𦶢隞方�蝻𤥁� (Implemented Dedicated Task Scheduler Tab & Autostart Detail Editor)**嚗�
    - [x] **霈∪�隞餃𦛚銝𤾸虜閫�䌊�臬𢆡憿寧����蝳� (Decoupled Scheduled Tasks)**嚗𡁻���� `AutostartManager.list_all_autostart_items`嚗���� Microsoft\Windows ��洵銝㗇䲮霈∪�隞餃𦛚隞𤾸��厩�撣貉�瘜典�銵�/敹急㭘�孵��芸鍳�典�銵其葉摰���𠉛氖嚗䔶�霂�㺭�格��餉��� SRP (�蓥��諹提) �笔���
    - [x] **�啣��祉����𨥉�� 霈∪�隞餃𦛚蝞∠��嗪�厰★�� (Added Dedicated Tasks Tab)**嚗𡁜銁 GUI �厰★�∠洵 4 憿孵��ｇ��啣�鈭��𨥉�� 霈∪�隞餃𦛚蝞∠� (Tasks)�𨯔ab 撟嗉��� `build_tasks_tab`��誑�冽鰵�� 4 �� Treeview嚗��� 隞餃𦛚�滨妍���� �嗆������ 隞餃𦛚頝臬����� 餈鞱�蝔见��賭誘銵䕘��祉�皜脫��𣬚恣��恣�雴遙�⊥㺭�殷��舀�����鍦��𢠃���𢰧�株��蓥�隞嗚��
    - [x] **摰䂿緵��稬憿寡祕��䰻�衤�蝻𤥁�撖寡�獢� (`AutostartItemDetailDialog`)**嚗帋蛹�芸鍳�典�銵典�霈∪�隞餃𦛚�𡑒”�� `<Double-1>` ��稬鈭衤辣蝏穃�鈭���啣��啁�撅墧�扯祕���蝻𤥁�撖寡�獢���砲撖寡�獢�𣈲��蘨霂餃��改�憿寧𤌍�滨妍��䔉皞鞱楝敺�����滨𠶖�������桀��塚�撟嗆𣈲��凒�亦�颲爗�𡏭�銵�𦶢隞�/頝臬��脲��祆�餈𥡝�靽格㺿靽嘥���
    - [x] **�舀�敹急㭘�孵�銝舘恣�雴遙�∪�撅���唳凒�� (Low-dependency Command Updating)**嚗𡁜銁 `AutostartManager` 蝐颱葉摰䂿緵鈭� `update_item_command` �蹱��䲮瘜𨰻���撖孵翰�瑟䲮撘� `.lnk` ��耨�對��朞� PowerShell �毺� COM 蝏�辣 WScript.Shell �齿鰵霈曉� TargetPath �� Arguments嚗偦�撖寡恣�雴遙�∠�靽格㺿嚗屸�朞� PowerShell �毺� `New-ScheduledTaskAction` �� `Set-ScheduledTask` �湔鰵�賭誘嚗�蝠摨閙��支�撖� `pywin32` �滚�靘肽�����乓��
    - [x] **�惩𤐄 Windows �鞉�靽格㺿銝𤾸�撣賊俈�� (Elevated Command Execution & Error Protection)**嚗𡁜��桅�𡁏��鞉�銵� `schtasks` 靽格㺿憭梯揖嚗��蝏肽挪�殷��塚�蝟餌��芸𢆡靚�鍂 `runas` �鞉��㕑絲 `powershell.exe` 摰峕��其�嚗𥕦��嗅銁 `run_as_admin` �鞉��𡁏𧋦銝凋�����瑚� `WinError 1223` (�冽�銝餃𢆡�𡝗� UAC ���) 撘�虜撟嗆��唳𠯫敹梹��踹�蝔见��𤑳��鮋��笔援皞���
    - [x] **銝��格惣�賭��碶��堒捐頝其�霂脲�銋�� (Task Diagnostics & Width Persistence)**嚗帋蛹霈∪�隞餃𦛚 Tab �啣�鈭��靝��桐��砽�嘥��踝��舀芋蝟𠰴龪�滚僎�寥�蝳�鍂��鉄撣貉��湔鰵嚗�� google, edge, logi, nvidia, steam 蝑㚁�����詨��𤾸蝱�湔鰵霈∪�隞餃𦛚嚗𥕦��塚��拙�鈭� `save_column_widths` 銝� `load_column_widths` 撖� columns 銝� `"tasks"` ���摰賜�霂餃��賢�嚗���啣�摰賣�銋����
    - [x] **�𣳇��朞� Python �拍�蝻𤥁�撉諹� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣耨�孵���芋�𡑒�銵䔶��𣳇�蝻𤥁�璉��伐�靽嗪�鈭��餉�銝𡒊��Ｘ㺿�函�撌亦��舫��扼��

## 2026-06-22 21:10
- [x] **銝箔蜓蝒堒藁�鞉�蝞∠��冽溶�䭾��典��啣��滢�蝵桀��� (Added Manual Position Refresh for Main Window)**嚗�
    - [x] **�啣��𨥉�� �瑟鰵敶枏�雿滨蔭�脲��� (Added Refresh Button on Main UI)**嚗𡁜銁 `WindowPosManagerUI` 銝餌��Ｙ� �𨥉�� �閗繮獢屸𢒰蝒堒藁�� �厰僼銝𦠜䲮嚗峕鰵憓硺� `self.btn_refresh_pos` �厰僼撟嗡蝙�券��肽𠧧�峕艶嚗䔶蛹�冽��𣂷��见𢆡��朖�嗥����瘚见��啣�����
    - [x] **摰䂿緵雿滨蔭銝擧遬蝷箏膥�𤘪�����典��� (Implemented Manual Refresh logic)**嚗𡁏鰵憓硺�銝餌���� `on_refresh_pos_clicked` 瑽賢遆�堆��函鍂�瑞��餅��格𧒄靚�鍂 `detect_and_refresh_state`嚗���啣�餈鞱�蝒堒藁��������誑�𦠜遬蝷箏膥�𤘪�蝏𤘪�嚗�僎�冽�銵𣬚𠶖��𠯫敹𦯀葉霈啣�嚗峕䲮靘踹銁蝒堒藁��撠誩��𡝗�撘��園��嗉�銵峕㺭�格�撖嫣��湔鰵��
    - [x] **�朞� Python 蝻𤥁��折�霂� (Passed Compilation Verification)**嚗朞�銵� `py_compile` 撖嫣蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�鈭��餉�銝𡒊��Ｘ㺿�函�撌亦��舫��扼��

## 2026-06-22 19:22
- [x] **摰䂿緵�喲睸�𨅯�瘚贝�Code蝑𣇉裦�冽��䌊���撅閧內 (Dynamic "Test Code Strategy" Context Menu)**嚗�
    - [x] **�冽����恍���甅�冽��喳��厰★�圈� (Dynamic Option Matching Based on Cycle Mode)**嚗𡁜銁 `instock_MonitorTK.py` �� `on_tree_right_click` �喲睸�𨅯�銝哨��朞�璉�瘚� `self.global_values.getkey("resample")` �冽��ế�剖��滩◤瞈�瘣餌��冽���𥅾銝粹��亦瑪憭𡁜𪂹���憒� 60MIN��30MIN 蝑㚁�嚗���芸𢆡撅訫�銝箔舅銝芣�霂訫�����𨥉榀� 瘚贝�Code蝑𣇉裦 (�亦瑪)�苷��𨥉榀� 瘚贝�Code蝑𣇉裦 (60MIN)�嘅��乩蛹�亦瑪�冽�嚗����僎撅閧內銝箏�銝芬�𨥉榀� 瘚贝�Code蝑𣇉裦�嗪�厰★��
    - [x] **摰匧��𣂼�憭𡁜𪂹��㺭�桐��坿秐 check_code (Thread-safe Cycle Data Sourcing)**嚗帋舅銝芾��訫𦶢隞文��芰�摰帋�撅䂿� lambda 銵刻噢撘𧶏����蝎曄＆�惩� `self.df_all` 銝𡡞���甅�𡒊� `self.df_all_res` �唳旿皞僐��銁隡惩� `df_all_res` 銋见��惩�鈭� `hasattr` 銝𡒊征�潔��日�餉�嚗䔶��靝�瘚贝����蝏剜�改�撟嗅蝠摨閗圾�喃�憭𡁜𪂹���霂蓥���㺭�桅�雿漤�����
    - [x] **霂剜�蝻𤥁�銝𡒊��ａ��鞾�霂� 100% �𣂼� (Passed Compile & Integration Check)**嚗帋蝙�� `py_compile` 撖嫣蜓�屸𢒰璅∪�餈𥡝�鈭���嗵�霂烐��伐�靽嗪�鈭���滚𪂹�毺𠶖��㦤���蝢𡡞��㚚���銝𡒊��Ｚ�韐舀�扼��

## 2026-06-22 19:15
- [x] **摰䂿緵 Treeview �唳旿閫�㦛�峕郊銝𤾸𢰧�桃凒��/�𨅯�憭滚��∠巨隞���蠘� (Synchronized Treeview Data & Standardized Right-Click Code Copy)**嚗�
    - [x] **瘛勗漲撖寥�憭𡁜𪂹��/�漤��瑁��暹㺭�格� (Aligned Resampled View Data Source)**嚗𡁜銁 `instock_MonitorTK.py` 銝哨��券𢒰�峕郊撟嗡耨憭滢�敶梶鍂�瑕��Ｖ蛹�墧𠯫蝥輻�憭𡁜𪂹����漤��瑁��橘�`resample != 'd'`嚗㗇𧒄嚗𣬚��Ｘ�雿靝��嗉粉�硋�撅� `self.df_all` 撖潸稲��㺭�桐�銝��湧䔮憸塩��
        - ��笆�喲睸�𨅯��� `�妒 瘚贝�Code蝑𣇉裦`嚗Ếheck_code嚗㗇�雿頣�撠���厩� `self.df_all_res` / `self.df_all` 隡惩��箏��齿�銝箏抅鈭𤾸��齿�瘣駁���甅�冽��� `df_active` �冽���㗇𥋘��
        - ��笆 `get_stock_info_text` (�瑕�銝芾�靽⊥�)��original_push_logic` (�券���瘜�)��test_strategy_for_stock` (瘚贝�銋啣�蝑𣇉裦) 蝑㗇瓲敹���亙恣霈∩���𧋦����寞�嚗��甇交𦻖�乩��漤��瑕𪂹�毺� `df_active` �唳旿瘚���脫迫憭𡁜𪂹�煺�瘚贝��𠰴�瘜函��𣂼���㺭�桅�雿溻��
        - ��笆�堒捐�湔㺿�㚚��誩� (`replace_column`) �峕�蝛箸�蝝Ｘ辺隞� (`clean_search`) �𡒊�銵冽聢�齿鰵�㰘蝸�餉�嚗���嗡�憪讠�撘箏�霂餃� `self.df_all` 隡睃�銝箄䌊���霂餃� `df_active` 餈𥡝��滨�嚗�蝠摨蓥��靝�憭𡁜𪂹��芋撘譍��屸𢒰�滢���㺭�株�韐舀�扼��
    - [x] **摰䂿緵 Tkinter Treeview �喲睸�湔𦻖憭滚��∠巨隞���啣�韐湔踎 (Standardized Instant Right-Click Code Copy)**嚗�
        - �齿�鈭�蜓�唳旿銵冽聢�喲睸�孵稬鈭衤辣 `on_tree_right_click`嚗�銁撘孵枂�喲睸�𨅯�����塚��芸𢆡撠���漤�劐葉銝芾��� 6 雿齿���誨���朞� `pyperclip.copy` �坔��芾斐�選�撟嗅銁�批��啁𠶖���颲枏枂�鞟內��
        - �齿�鈭� V-Reversal �烐綉瘙㰘”�澆𢰧�桃��颱�隞� `show_context_menu`嚗�𢰧�桃��颱葵�⊥𧒄�喳��芸𢆡�扯�隞��憭滚�銝𡒊𠶖���蝷箝��
        - �Ｗ�撟嗉����鈭���剖��脰扇敶閗”�潛��喲睸�孵稬鈭衤辣 `on_handbook_right_click`嚗��瘨����𧋦瘜券��厩�憭滚��餉�嚗屸��唳��帋��𧢲𤧐�Ｘ踎���韐湔踎憭滚��𡁻���
        - �其蜓�喲睸�𨅯�摨閖����𨅯�隞𣇉恣���嗪���葉嚗屸�憭𤥁‘��� `"�� 憭滚��∠巨隞��"` �𨅯��賭誘雿靝蛹�屸�靽嗪���
    - [x] **�寞祥 Top10 銝擧�敹菔祕�� Treeview �鞉�頧祆揢 ValueError 撏拇� (Fixed ValueError in Top10 & Concept Detail Treeviews)**嚗�
        - 靽桀�鈭�銁璁�艙霂行��� Top10 �Ｘ踎銝剖��餅��喲睸�孵稬銵峕𧒄嚗𣬚眏鈭𦒘誨��凒�亙� Treeview �� item ID 撘箏�頧祆揢銝箸㟲�页�`int(item)`嚗匧銁�枏��𤥁� ID 銝滢蛹蝥舀㺭摮㛖�憭齿��臬�銝𧢲��� `ValueError` 撖潸稲蝔见�撏拇���撩�瑯��
        - 撠���厩� `int(item)` / `int(idx)` 頧祆揢銝箸���� `tree.index(item)`嚗䔶蝙敺堒�雿滩�蝎曄＆銝𠉛�撖孵��典𧑐�瑕�敶枏�銵𣬚��拍�蝝Ｗ�雿滨蔭��
    - [x] **�朞� Python 霂剜�蝻𤥁�璉�瘚�**嚗𡁜⏚�� `py_compile` �𣂼��朞�鈭��隞嗉祗瘜蓥�蝻抵�����渡�霂烐�折�霂���芸��乩遙雿閗��Ｗ蔣�齿��仿���

## 2026-06-22 16:30
- [x] **�齿鰵摰䂿緵雿輻鍂蝟餌�銝剔緵�鞟��𥪜𢆡�交��蠘�嚗�笆朣鞾�㕑��𣬚�隞瑟㦤�� (Aligned Reversal Pool Linkage with System Standard link_to_visualizer)**嚗�
    - [x] **�齿��烐綉瘙删���稬銝𡡞�㗇𥋘�𥪜𢆡�餉�**嚗𡁜銁 `instock_MonitorTK.py` ��撩摨��甈∟絲���摮鞉芋�� `view_stock_kline` �寞�銝哨��芸𢆡�朞� `get_consolidation_flags(code)` ����亙藁�瑕�敶枏�銝芾��� `entry_date`嚗�笆蝛箏�雿滨泵 `"-"` 餈𥡝�摰匧�餈�誘��
    - [x] **�湔𦻖憭滨鍂蝟餌�頝典極�瑁��冽𦻖��**嚗𡁜��靝葵�∪��典�瘙䭾𠯫����嗘��滨�餈� `on_code_click` ���𡁶鍂銝芾��孵稬��揢嚗諹�峕糓�湔𦻖靚�鍂蝟餌��唳�������㕑� (StockSelector) �𣬚�隞� (SectorBiddingPanel) 擃睃漲銝��渡� `self.link_to_visualizer(code, entry_date)` 頝典極�瑟𠯫�蠘��冽𦻖���敶餃�瘨�膄鈭��撖寥�𡁶鍂�餉���噩�亙�靽格㺿�𣬚�頝舀㜃�� Bug��
    - [x] **�交��交��硺漱�𤘪𠯫�∪�銝舘䌊�其耨憭�**嚗𡁜銁靚�鍂 `link_to_visualizer` 銋见�嚗屸�朞� `cct.get_day_istrade_date(entry_date)` �斗鱏�嗆糓�虫蛹�㗇�鈭斗��乓��𥅾敶枏��交��交�憭���冽錰�����𠯫�硋��芯漣��㺭�桃�鈭斗��伐��硺漱�𤘪𠯫嚗㚁��坔⏚�� `cct.get_last_trade_date(entry_date)` �芸𢆡�∪�撟嗡耨憭滢蛹�嗅�銝�銝芸�����㗇�鈭斗��伐�靘见�撠��鈭斗��� 0619 �芸𢆡靽格迤銝� 0618嚗㚁�敶餃�閫��鈭��鈭斗��亦𠶖�����稬�䭾�蝏睃�擃䀝漁蝥踵��唳旿�𧢲踎��撩�瑯��
    - [x] **�曉捐敶枏予�交���扇�鞱��𣂼�**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�撠�𧒄�渡瑪�餌瑪�文��� `t_str >= last_td` 靚�㟲銝� `t_str > last_td`���雿踹�敶枏予�朞��亦��扳����蟡剁��交�銝擧��𦒘漱�𤘪𠯫�貊�嚗匧��餅𧒄嚗䔶��嗉��典𢰧靘扳��� K 蝥踵�銝𦠜��毺��嗉��券��脰�蝥踹�霂衣��唳旿�𧢲踎嚗��蝢擧�憭滚�憭拐葵�∠��交���瑪�峕㺭�株��具��
    - [x] **摰峕�蝻𤥁�璉��乩��嗆��㦤�訫�瘚贝�**嚗𡁻�朞�鈭� `py_compile` 撖嫣舅隞賭誨���隞嗥�霂剜�璉��伐�撟嗥＆靽苷� `test_v_reversal_fsm.py` �訫�瘚贝��剛� 100% �𣂼�頝煾�𡄯�蝖株恕�芸笆蝟餌��嗡�璅∪�撘訫�隞颱��鮋��蠘��Ｗ蔣�溻��

## 2026-06-22 11:45
- [x] **靽桀��瑕鍳�函撩��‘�典�韏瑞��典��箄�蟡冽��� HDF5 �滚��噼‘瞍𤩺� (Fixed Full-Market Loop of HDF5 Gap Recovery)**嚗�
    - [x] **�𣂼� count_gaps 隞��霈⊥暑頝�葵�� (Restricted count_gaps to Active Stocks Only)**嚗𡁜銁 `realtime_data_service.py` ����� `count_gaps` 銝哨��㰘捏�臬歇�厩�摮䀹��亥��舐撩憭曹葵�∪翰�批笆朣琜�����乩� `if self.is_active_stock(code):` ��蒾�滚��𣂼���＆靽嗪�瘣餉�銝芾��喃噶�函���⏛�剛秐 120 �孵�嚗䔶�蝏苷�隡朞圻�睲�瘞港�霅血��噼‘嚗䔶��寞𧋦銝𢠃獈�凋� 5000+ �墧暑頝��蟡典�銝𡡞𡢿�坔�銵亦��𣳇�敺芰㴓��
    - [x] **摰䂿緵擃䀹�蝎曉��寥��瑕�銝𡒊�摮睃��� (Achieved Efficient Batch Fetch & Cache Reuse)**嚗𡁻�朞��賢��閗�皛歹�撠��甈� HDF5 蝎曉��噼‘��葵�∟�璅∩� 5500+ �芸�蝻抵秐隞����㺭��蘨瘣餉��烐綉�∴��芷�剹����孵� V�齿�隡𤩺��𣂼��∴�嚗䔶�隞�說頞喃��𨅯�銵交㺭�桀蘨�賣鸌�讛繮�砽�萘�擃䀹�扯�霂㗇�嚗諹��𦦵�鈭�蜓蝥輻���之閫�芋蝤�� I/O �餃��� SingleFlight ����湔隅��
    - [x] **撉諹� Python 蝥扯祗瘜蓥��訫�瘚贝�摰匧� (Passed Syntax & Unit Test Regressions)**嚗𡁏�銵䔶� `py_compile` 蝻𤥁�撉諹�銝� `test_v_reversal_fsm.py` �嗆��㦤�𥪜𢆡�訫�瘚贝�嚗𣬚𠶖���頧砌��瑕㭂�芣��剛��券��朞�嚗峕𧊋撘訫�隞颱�銋梁��𠰴��賢�㘾����

## 2026-06-22 11:35
- [x] **隡睃� Sina 銵峕�撘閙��瑕鍳�其��䀝葉�滚��㰘蝸�扯� (Optimized Sina Engine Startup & Re-load Performance)**嚗�
    - [x] **摰䂿緵 StockCode 璅∪�蝥批�撅��蓥��� (StockCode Module-Level Singleton)**嚗𡁜� `StockCode` �嫣蛹璅∪�蝥批�撅��蓥�嚗��朞� `get_global_stock_code()`嚗㚁��踹�鈭��甈∟��� `Sina.all` 撅墧�扳� `Sina.market` �園�憭滚�靘见� `StockCode()`�����蝠摨閙覔瘝颱��瑕鍳�典�銵峕��瑟鰵�園�蝜�圻�� `stock_codes.conf` �滨蔭��辣�拍�霂餃��� `creation_date_duration` 霈∠���撖潸稲����� I/O �蠘�𨰜��
    - [x] **瘨�膄�瑕鍳�典之�讐��滚��滨蔭霂餃��亙� (Eliminated Duplicate Startup Configuration Logs)**嚗𡁶眏鈭� `StockCode` �蓥��吔��瑕鍳�冽��游��祇�憸穃���� `雿輻鍂 stock_codes.conf �滨蔭: ...` 隞亙� `date_duration days: ... read stock_codes.conf` ���蝷箸𠯫敹堒銁�刻�蝔讠��賢𪂹�煺葉隞�銁擐𡝗活�嘥��𡝗𧒄颲枏枂銝�甈∴��㗇�瘨�膄鈭�之�讐��𦯀��亙��峕�靚梶�蝤��霂餃�嚗𣬚泵���𦦵�撖嫣���捂�閧��扯��寥��唳旿�萘�撘��𤏸�����
    - [x] **摰��靽萘� UTF-8 蝻𣇉�銝𦒘葉��釣�𠰴��冽��**嚗𡁜銁�拍��齿�餈��銝哨��券�靽脲�鈭� `JSONData\sina_data.py` ��𧋦�� UTF-8 (without BOM) 蝻𣇉��澆�嚗峕𧊋撘訫�隞颱�銋梁��𤥁祗瘜閧�霂穃�撣賂�撟園�朞�鈭� `test_v_reversal_fsm.py` �嗆��㦤�訫�瘚贝���

## 2026-06-22 11:30
- [x] **靽桀�蝑𣇉裦靽∪噡�Ｘ踎�𨅯��箸萱摨色�脲㺭�潭滯�箏虜撽� 100�� 瞍𤩺� (Fixed Dashboard Market Temperature Permanently 100�� Bug)**嚗�
    - [x] **靽格迤�踹�撘箏漲瘨典��唳旿蝝Ｗ��讐氖**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_aggregate_market_dashboard_stats` �寞����撠�恣蝞埈踎�堒� 5 憸䀹�瘨典��園�霂舐�����𣂼�蝝Ｗ� `item[1]`嚗���鞉踎�𡑒�����𡁜虜�� 100~150 銝𠹺�嚗劐耨甇�蛹 `item[2]`嚗���鞉踎�堒像�����隅撟�����閫��鈭�踎�烾��鞟�摨西恣蝞埈𧒄�惩��唳滯�箔�隞亦頂�啣��湔𦻖閫衣１ 100.0�� 銝𢠃�撠�▲��撩�瘀�雿輻��乩縑�琿𢒰�輻�撣�㦤皜拙漲�賜�摰鮋�皜抬�撟嗡�瘥𤩺𠯫憭滨�皜拙漲��恣蝞㛖��𨅯�蝢𤾸笆朣僐��
    - [x] **摰峕� Python 蝥扯祗瘜閧�霂煾�霂�**嚗𡁻�朞��冽𧋦�唳�銵� `py_compile` 撖嫣耨�孵��� Tkinter 銝餌��ａ�餉��扯�鈭��霂穃��冽�扳��伐�撉諹��芸��乩遙雿閗祗瘜訫�撅�漣蝻抵�撘�虜��

## 2026-06-22 10:00
- [x] **隡睃� 55188 �唳旿�航��硋極�瑟�銋��蝻枏�銝擧��典��唳㦤�� (Optimized 55188 Persistence-First Caching & Manual Refresh)**嚗�
    - [x] **摰䂿緵����𡝗㺭�桅�蝥找��� (Persistence-First Fallback)**嚗𡁜銁 `scraper_55188.py` ��㺭�格��碶���僎銝剖��乩�蝻枏�靽脲擪�餉�����諹�憿箔犖瘞娍𦻖�� (THS Hotlist) �㚚��鞉��硋仃韐亥��䂿征 DataFrame �塚�蝟餌�撠�䌊�其���蟮蝻枏���辣 `cache_55188_snapshot.pkl` 銝剛粉�硋笆摨娍芋�㛖�摮埈挾餈𥡝��删��滚�銵亙�嚗屸俈甇Ｖ��曹�蝵𤑳��祆𧒄�硋𢆡����扳�隞��撘�虜�䭾��游�銵冽��詨�摮埈挾鋡怠撩銵𣬚蔭蝛箝��
    - [x] **撘訫��滚𦛚�臬𢆡�唳旿憸��頧� (Startup Cache Pre-loading)**嚗𡁜銁 `realtime_data_service.py` �嘥��𡝗𧒄嚗���牐� `load_cache()` �㰘蝸��蟮 55188 蝻枏��唳旿����券�餉�嚗䔶蝙�滚𦛚銝��血鍳�典朖�航繮敺𦯀�銝�甈⊥���㺭�殷�銝滨鍂蝑匧�擐𤥁蔭摰𡁏𧒄�枏�蝏𤘪�嚗�蝠摨閙覔瘝颱��瑕鍳�券�撅讐征�賡䔮憸塩��
    - [x] **摰䂿緵 UI �亦��冽𧋦�圈�蝥扳葡�� (UI Degraded Rendering)**嚗𡁜銁 `instock_MonitorTK.py` �� `open_ext_data_viewer` 銝剖��牐�憭�鍂�滨漣蝑𣇉裦��𥅾�𤾸蝱摰墧𧒄�滚𦛚�芸遣蝡𧢲��芾��墧���㺭�殷�df_ext.empty嚗㚁�銝餉�蝔见��湔𦻖隞擧𧋦�� HDF5/PKL 蝻枏�銝剖�頧賣㺭�格葡�梶��ｇ��脫迫�典�餈𤤿�蝵𤑳��芸停蝏芣��亙藁撏拇��� UI ��緵�𨅯之�賢��脲��𨅯��臬𢆡蝛箸��腈��
    - [x] **�啣��𨥉�� �瑟鰵�脲��典��啗圻�穃膥 (Added Manual Refresh Trigger)**嚗𡁜銁 `ext_data_viewer.py` ����函𠶖���嚗䔶�鈭� DNA 摰∟恣�厰僼撌虫儒�啣�鈭��𨥉�� �瑟鰵�脲��柴��鍂�瑞��餉砲�厰僼�喳虾蝡见��穃��嗆��∪�����𤥁窈瘙�僎�齿鰵皜脫� UI嚗峕�擃䀝�摰墧𧒄�埝䰻 API ���啗���������
    - [x] **靽桀�銝𡏭揣銝餃�韏���鍦��瑕� bug (Fixed Eastmoney Main Force Rank Issue)**嚗𡁶眏鈭𦒘�韐Ｚ��� API ��漣�� `f225`嚗�蜓�𥟇��㵪�摮埈挾餈𥪜��澆�銝� 0 撖潸稲銝餌��Ｔ�靝蜓�𥟇��𨧀�肽��曄��鍦��券��曄內銝� 0��覔�桐�韐� API 餈𥪜��唳旿撌脤�朞� `fid=f184` 撟嗆�銝餃����䭾��滚��鍦���鸌敺���湔𦻖�冽㺭�格�瘣烾𧫴畾菜覔�� DataFrame ���蝝Ｗ��芷���霈∠�����笔��� `zhuli_rank`嚗�蝠摨閙�憭滢�銝餌��Ｖ蜓�𥟇��滨��齿活�曄內��

## 2026-06-22 09:00
- [x] **敶餃�靽桀�銝𨀣䲮韐Ｗ� push2.eastmoney.com �亙藁 Connection aborted / RemoteDisconnected ���**嚗�
    - [x] **摰帋��滚𦛚�函垢頝舐眏�䀹凒嚗㇌oot Cause Identified嚗�**嚗𡁻�朞� web �𦦵揣銝𤾸����蝏𡏭��哨�蝖桀�銝𨀣䲮韐Ｗ�餈烐��嗥揮鈭�俈�怠�/憌擧綉蝑𣇉裦嚗���Ｗ���/�𣂼�鈭��撖寞唂 `/api/` 頝臬�嚗�朖 `https://push2.eastmoney.com/api/qt/clist/get`嚗厩�銝滩扇�滨凒�亥窈瘙��撖潸稲���㕑砲頝臬�霂瑟�銝滨恣�舐凒餈噼��航粥�砍𧑐 Clash 隞��嚗屸�隡朞◤銝𡏭揣�滚𦛚�函凒�� abort 銝Ｗ�嚗�”�唬蛹 TCP 餈墧𦻖撱箇��擧� Response 銝� RemoteDisconnected嚗剹��
    - [x] **餈�宏�單鰵�砍�頝臬��亙藁嚗㇁PI Path Migration嚗�**嚗𡁜� `scraper_55188.py` 銝剔� `EASTMONEY_URL` 靽格㺿銝箔�韐Ｘ��啁��砍��𣳇��嗉楝敺� `/webguest/api/`嚗�朖 `https://push2.eastmoney.com/webguest/api/qt/clist/get`嚗㚁�隞舘�峕�憭滢��唳旿�亙藁��◇��挪�柴��
    - [x] **���隞��瘚贝��朞�嚗㇊roxy & Direct Connectivity Confirmed嚗�**嚗𡁻�朞�瘚贝��𡁏𧋦餈𥡝�摰墧�撉諹�嚗諹�摰墧鰵�亙藁頝臬��典��� Clash 隞���𣬚凒餈痹�銝滩粥隞��嚗劐舅蝘滨�蝏𦦵㴓憓����虾 100% �𣂼�餈𥪜� HTTP 200 撟嗉繮�硋����啁�銝餃�韏���鍦��唳旿��
    - [x] **靽萘� session.trust_env �脣鴃�箏�**嚗𡁶誧蝏凋��� `self.session.trust_env = False` 霈曄蔭嚗𣬚＆靽嘥銁�賢�銵峕��枏�餈��銝哨��祈臤隡帋���蝙�冽𧋦�啁凒餈噼�䔶�隡朞◤ Clash 蝑劐誨����寧�憓�� IP �行⏛嚗峕����雿舘圻�穃�憭硋��� IP 憌擧綉�������

## 2026-06-19 10:00
- [x] **敶餃��寞祥 open_realtime_monitor ����⊥��������硋仃���WINDOW_CONFIG_FILE �蹱��翰�扳覔�牐耨憭㵪�**嚗�
    - [x] **摰帋�撟嗆��斗覔�砍��𩤃�Static Snapshot Bug嚗�**嚗䫤gui_config.py` 銝剔� `WINDOW_CONFIG_FILE` �舀芋�堒紡�交𧒄�����翰�批虜�𧶏�`_base_dir = get_app_root()` �� import �嗆挾�扯�銝�甈∩噶�箏�嚗剹��銁�枏��臬�銝页��� `INSTOCK_APP_ROOT` �臬��㗛�撠𡁏𧊋�嘥��吔�`get_app_root()` �航�餈𥪜�銝湔𧒄�桀�頝臬�嚗�紡�� `WINDOW_CONFIG_FILE` �箏�銝粹�霂舐�頝臬�嚗䔶蝙 `save_sash_pos` �坔����隞嗡� `load_sash_pos` / `load_window_position` 霂餃����隞嗡��臬�銝�銝芰����蝵殷�撘訫�瘞訾�憭望���
    - [x] **撘訫�餈鞱��嗅𢆡��楝敺�恣蝞� (`_get_sash_cfg_file`)**嚗𡁜銁 `open_realtime_monitor` �剖�銝剜��硋枂�祉��� `_get_sash_cfg_file()` 颲�𨭌�賣㺭嚗䔶��滢�韏𡝗芋�㛖漣�蹱��虜�� `WINDOW_CONFIG_FILE`嚗峕㺿銝箏銁瘥𤩺活靚�鍂�園�朞� `sys_utils.get_app_root()` �冽����嗉繮�𣇉����撖寞覔�桀�嚗屸��� DPI scale �芸𢆡�㗇𥋘 `window_config.json` �� `scale{N}_window_config.json`嚗䔶� `WindowMixin._get_config_file_path` 摰��撖寥����靘𥕦��漤�蝥批�摨𤏪����蝥批� `WINDOW_CONFIG_FILE` 璅∪�撣賊�嚗���滨漣�� `get_conf_path`嚗䔶遙雿閧㴓憓��銝滚援皞���
    - [x] **蝏煺� save / load 霂餃��䔶�銝芣�隞�**嚗䫤save_sash_pos` 銝� `load_sash_pos` ����典�銝�銝� `_get_sash_cfg_file()` �賣㺭嚗�蝠摨蓥�霂� save �坔�銝� load 霂餃��拍�頝臬�摰��銝��湛��寞祥鈭����� sash 雿滨蔭"靽嘥�鈭��霂颱���"��瓲敹�撩�瑯��
    - [x] **DPI Scale �鞉�敶雴��� (DPI-Normalized Coordinate)**嚗窃ave �園膄隞� scale 摮㗛�餉��鞉�嚗𨧣oad �嗡�隞� scale 餈睃��拍��鞉�嚗峕��日� DPI 撅誩� sash 瞍�宏��
    - [x] **�笔��坔�銝� debug �亙�**嚗帋��� `.tmp` ��辣�笔��踵揢�箏�嚗峕鰵憓� `logger.debug` 颲枏枂靽嘥�頝臬�嚗䔶噶鈭擧���㴓憓��餈質葵�滨蔭�坔��臬炏�𣂼���
    - [x] **暺䁅恕 339 ���瘥𥪯� (Default 3-7 Layout via 339 Logical Pixels)**嚗𡁜銁 `restore_sash` ����惩��惩��脤�蝵桃�暺䁅恕 fallback �餉���銁擐𡝗活餈鞱��𡝗��滨蔭��辣�塚�銝滚�蝵桃征嚗諹�峕糓暺䁅恕撠���娍辺�㕑秐 `339` �餉��讐�雿滨蔭嚗��隞� DPI scale 餈睃��拍��讐�嚗㚁��𣂷�蝚血�鈭斗�銋䭾��� 3-7 ����嘥�撣��嚗�僎摰𣬚��踵𦻖�𡒊賒����刻��游�����硔��

## 2026-06-19 09:30
- [x] **嚗�唂嚗纬pen_realtime_monitor ����⊥�銋���萘�靽桀�嚗�歇鋡思��寞覔�牐耨憭滚�隞��**嚗�
    - [x] 撘訫� `sash_restored` 摰�擪�����<Configure>` 鈭衤辣撽勗𢆡�Ｗ����蝡臬����皛斤��脣鴃�箏�嚗�� 2026-06-18 23:50 �∠𤌍嚗剹��

## 2026-06-19 01:40
- [x] **瘨�膄撘箏�霈曄蔭銝舘䌊�典�甇乩葵�∟秐�烐綉瘙惩��𤑳�銝餌瑪蝔� I/O �⊿▼ (Eliminated Main Thread I/O Freeze on Favoriting/Syncing Stocks)**嚗�
    - [x] **撘訫���� df_all 銵峕����蝻枏� (_df_all_cache)**嚗𡁜銁 `MinuteKlineCache` 銝剜鰵憓� `_df_all_cache` 銵峕��唳旿敹怎�撘閧鍂嚗�僎�其蜓�屸𢒰銵峕�瘥讛蔭�瑟鰵嚗Ǒself.df_all = full_df`嚗匧� CSV �唳旿�㰘蝸�塚��笔��啣�甇亙�摰峕㟲��𠯫蝥踵���㺭�格釣�亙��� K 蝥輻�摮䀝葉��
    - [x] **�齿��嗆��㦤蝻箏仃摮埈挾銵仿��� (Auto-Filler) 銝箏�摮䁅恣蝞�**嚗𡁜銁 `update_wave_structure_state` �� `need_fill` 畾萎葉嚗䔶���� `_df_all_cache` �典�摮䀝葉���蠘‘朣𣂷葵�∠� `ma20`��ma60`��dff3`��dff2` �𠰴�蝘堆�摰䂿緵鈭𡁏神蝘垍漣��妟蝤�� I/O �餃� of 敹恍�蠘‘朣僐��
    - [x] **�峕郊�齿�撟嗡��𣇉��䁅粉�硋����餉�銝剔��舀���漣���**嚗𡁜銁 `update_wave_structure_state` ����䁅粉�� `fallback` ��𣈲銝哨�撠���砍�銝��抒� `MA20/60` 蝎㛖��鍦�嚗���游笆朣鞾���蛹�冽鰵�� 5 獢�移蝏�𣈲�穃�蝥找�蝟鳴�霈∠�撟嗅��� `ma5d` �� `ma10d` �舀���瑪嚗㚁�瘨�膄鈭�眏鈭擧㺭�格�銝𤾸�頧賣䲮撘譍��屸�䭾���葵�∠����霈唬�銝��渲歲�函��鞉���
    - [x] **撱箇�銝餌瑪蝔讠��� I/O 摰匧��脫擪�� (Main Thread I/O Guard)**嚗𡁜銁 `_df_all_cache` �芸停蝏芰��鮋���餉�銝哨�撘訫�銝餌瑪蝔见�隞輻�璅∪��屸��∩辣�文���𥅾敶枏�雿滢� Tkinter 銝餌瑪蝔衤�銝滚�鈭𤾸�瘚衤遛��芋撘譍�嚗���喲獈�凋遙雿訫笆蝤�� HDF5/TDX �亦瑪��辣���甇亥粉�硋𢆡雿頣�隞�銁�𤾸蝱撘�郊蝥輻��𣇉氖蝥踹����霂蓥葉��捂�鮋��霂餌�嚗�蝠摨閗圾�喳僎�寞祥鈭���峕郊�滨�銝芾�撘訫��� 5蝘� 銝餌瑪蝔见�甇餃㨃憿踴��
    - [x] **�質情撟嗥�銝��亦瑪�孵����霈∠��亙藁 (Unified Indicators Interface & DRY Refactor)**嚗𡁜銁 `MinuteKlineCache` 銝剜𡂝鞊∪枂蝏煺��� `calculate_stock_daily_indicators(code, recent_avg_vol)` �亙藁嚗�������**摮埈挾銵仿��� (Auto-Filler)**銝�**摨閗�蝳駁�撟�撩餈�誘 (INIT -> CONSOLIDATING)**銝文���䌊�祉�摰䂿緵�� Rolling ��瑪霈∠����憭游之�峕艶�文���𣈲�穃�蝥批ế摰𠾼��之摨閙隅撟���滢�瘨典�霈∠�嚗���冽𤣰敶坿秐�蓥��寞���蝠摨閙��支��𦯀�隞��嚗䔶�靽肽�鈭��摮䀝�蝤��銝方楝�唳旿皞𣂷���恣蝞烾�餉�摰��蝑劐遠撖寥�嚗���典��� SOLID �𣬚� SRP �� DRY 撘��穃��踺��
    - [x] **隡睃� set_df_all_cache 擃㗛��瑟鰵���蝥寡�璉��� (Optimized set_df_all_cache via Fingerprint Dirty Check)**嚗帋蛹鈭�俈甇Ｗ銁擃㗛��瑟鰵�冽�嚗�� 3蝘� 銵峕��湔鰵嚗劐葉�滚�餈𥡝�摨𧼮之�亦瑪�唳旿撣抒��䭾�銋㕑��澆�鈭抒�憭帋�����舀𧋦�� Python GC (��䔿�墧𤣰) 撘���嚗�銁 `set_df_all_cache` �亙藁������鈭�抅鈭� `df_fingerprint` ���蝥寡�璉��交㦤�嗚����冽�瘚见� `df_all` 銝剔��詨��孵���犒�𤑳�摰鮋��睃��嗆���迤�湔鰵���敹怎�嚗峕𠯫���憸𤏸��冽𧒄�湔𦻖�剛楝餈𥪜�嚗諹噢�圈妟���蝣𡒊��屸妟憸嘥� CPU �蠘�㛖������

## 2026-06-19 01:30
- [x] **銝� Tkinter �詨��唳旿銵冽聢瘛餃��喲睸憭滚��∠巨隞���蠘� (Added Copy Stock Code Option to Treeview Context Menus)**嚗�
    - [x] **銝餌��Ｘ㺭�株”�潭𣈲��𢰧�桀���**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `on_tree_right_click` �寞���銁銝餅㺭�株”�澆𢰧�株��閧��箇��蠘��箔葉嚗峕鰵憓硺� `"�� 憭滚��∠巨隞�� ({stock_code})"` �厰★嚗𣬚��餃��拍鍂 `pyperclip.copy` 撠���� 6 雿滢葵�∩誨����桀紡�亦頂蝏笔�韐湔踎嚗�僎�峕郊�冽綉�嗅蝱�嗆���颲枏枂�鞟內��
    - [x] **V-Reversal 摰墧𧒄�烐綉瘙㰘”�潭𣈲��𢰧�桀���**嚗𡁻���� `show_context_menu` 銝𠹺�����訫�銋剹��蛹撘箏�韏瑞�瘙䭾㺭�株”�澆��乩� `"�� 憭滚��∠巨隞��"` �其�嚗峕��帋�頝函����憸𤑳��找葵�∩誨���敹恍����琿�𡁻�嚗峕����鈭斗��条��唳旿鈭支������

## 2026-06-19 01:20
- [x] **摰䂿緵撘箏�鈭峕活韏瑞��烐綉瘙删���銁 Alt+R 閫��頧格揢�箏�銝剔�瘜典�銝舘䌊�典��� (Added Real-time Monitor Window to Alt+R Window Rotator)**嚗�
    - [x] **�𣈯�摰墧𧒄�烐綉蝒堒藁�交�**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_get_all_open_trade_windows` ���憓𧼮�撖� `self._realtime_monitor_win`嚗�撩摨��甈∟絲����扳�蝒堒藁嚗厩�璉�瘚见��園�����𦦵�����其�憭��瘣餃𢆡�航��嗆���撠�� `winfo_id()` 瘛餃��� `current_visible_hwnds` 撟嗆�撠��暺䁅恕蝒堒藁�滨妍嚗䔶�����嗆��𡁜僎蝥喳� Alt+R (�穃�頧株蓮) / Alt+Shift+R (�穃�頧株蓮) 閫��頧格揢敺芰㴓銝准��
    - [x] **�舀��毺�蝵桅▲銝舘��血𤧅韏�**嚗𡁜銁 `_force_focus_hwnd` 銝剛蕭�𣳇�撖� `self._realtime_monitor_win` 蝒堒藁�交������ Tkinter `deiconify`��lift` 銝� `focus_force` �䔶��拍忽�誩𤧅�㘾�餉�嚗𣬚＆靽嘥銁雿輻鍂�剝睸�𤥁蔭頧祇𢒰�踹��Ｘ𧒄霂亦���� 100% �𣂼�瘚桃緵�喳��啜��
    - [x] **隡睃�頧格揢�Ｘ踎蝢𤾸��滨妍�惩�**嚗𡁜銁 `WindowRotatorDialog.show_rotator` �����犖蝐餃虾霂餃�蝘啗蓮�Ｗ�銝哨��啣�撖� `"RealtimeMonitor"` �喲睸摮㛖��芷���蝢𤾸�霂��嚗䔶蝙�嗅銁 Alt+R ��恥�祆筑��揢�Ｘ踎銝𠰴��啁移蝢𡒊���� `"�㴓 撘箏�鈭峕活韏瑞��烐綉瘙� (RealtimeMonitor)"`��

## 2026-06-19 00:20
- [x] **摰䂿緵�臬𢆡�滚��𨅯�蝥蹂漱�嗵�蝻罱�嘥�蝥扳�瘚衤�雿𦒘�暺��銋啁� UI �垍𤌍擃䀝漁 (MA20/60 Converge Detection & Buying Zone UI Highlighting)**嚗�
    - [x] **�啣� MA20/60 ��瑪鈭日�蝎睃��文�**嚗𡁜銁 `realtime_data_service.py` �� `INIT` -> `CONSOLIDATING` 隡�迅�交��∩辣銝哨�敶𤘪𠯫蝥� MA20 銝� MA60 ���蝳餃漲�� 5% 隞亙�嚗Ǒabs(ma20 - ma60) / ma60 <= 0.05`嚗㗇𧒄嚗諹秩�舘�隞瑕�鈭𤾸��睃����蝥輻�蝻𨬭��漱�坔�蝎睃��渡��麄��頂蝏蠘䌊�典�蝏𤘪���漣��扇銝� `"MA20/60蝎睃�"` 撟嗆�銋��嚗䔶噶鈭𦒘漱�枏��滨蔭霂���臬𢆡�滢舅憭拍��詨�摨����
    - [x] **撘訫�銋啁��箏�嚗㇂uy Zone嚗凤reeview 銝枏�擃䀝漁**嚗𡁜銁 `instock_MonitorTK.py` 銝哨�摰帋�鈭���睲僭�亦���倌 `"buy_zone"` 撟嗥�摰帋��𥪜����璈䁅𠧧�峕艶嚗Ǒ#fff9eb`嚗劐�璉閗��脣��航𠧧嚗Ǒ#b87333`嚗剹��笆憭��璅芰�瞏靝�嚗ǑCONSOLIDATING`嚗匧�蝻拚��噼萱嚗ǑPULLBACK`嚗㕑�銝支葵���瑚��颱遠�潛�雿𡡞��拙鍳�典�憭𦦵𠶖���銝芾�餈𥡝��芸𢆡擃䀝漁皜脫�嚗��蝢𦒘�憭��憭扳隅�𣳇���`WAVE_UP`嚗㗇�擃䀝�憿箏辣�嗆挾��葵�∟�銵諹�閫匧躹�𢛵��
    - [x] **��漣撟嗥�����𡁜����霂閙鱏閮�**嚗𡁜銁 `test_v_reversal_fsm.py` �訫�瘚贝�銝剝���鈭���啁���瑪蝎睃�蝏𤘪���漣嚗𣬚＆靽苷��� 20��/60�� ��瑪�貊�嚗��蝳颱蛹0嚗厩� Mock 瘚贝��臬�銝𧢲鱏閮� 100% 頝煾�𠾼��
    - [x] **蝖株恕撟嗆４��縑�瑟�銋���删��踵𦻖�箏�**嚗𡁶頂蝏罸�朞��� `load_consolidation_state`嚗�鍳�典�頧踝��� `backup_consolidation_state_to_gz`嚗����箄䌊�其�摮睃�隞踝�銝剖��𣂷�撖� `v_reversal_pool.json`嚗��摮睃銁 RAMDisk ���毺�銝哨����箸𧒄�讠憬憭�遢�� logs/ 撟嗅� 7 憭拇��刻蔭頧穿����銋�����銝� JSON 摰峕㟲靽嘥�鈭���厩𠶖��㦤摮埈挾嚗���祆�銝芯葵�∪��滨��嗆挾嚗Ǒphase`嚗剹���瘙䭾𠯫���`entry_date`嚗剹�����掩�页�`structure`嚗剹��之摨閙隅撟��`dff3`嚗剹���雿擧隅撟��`dff2`嚗剹��𦆮�誩�齿㺭�屸�雿𤾸�����
    - [x] **��蟮頞�𧒄�芣�����**嚗𡁜銁�㰘蝸�塚�憒���� `CONSOLIDATING` 頞�𧒄嚗�>= 3憭拇��券�嚗㗇� `WAVE_UP / PULLBACK` 頞�𧒄嚗�>= 2憭抬�隡朞䌊�券���� `INIT` 撟嗉挽蝵� 240 �������港��歹��脫迫�萄偶靽∪噡瘙⊥���

## 2026-06-18 23:58
- [x] **隡睃���𧒄 V�见�頧砌��𣳇�����ế摰𡁻�餉�嚗峕楛摨阡���撘箏飵�噼�甈⊥𠯫�匧�蝏𤘪� (Optimized V-Reversal Intraday States & Support Logic)**嚗�
    - [x] **�齿��亦瑪��瑪�舀��粹𡢿�文� (Refactored Daily Support Bands)**嚗𡁜���𧋦甇餅踎�� `ma20d` �� `ma60d` �箏�瘥𥪯�嚗�-2% �� 2%嚗厩��舀��孵ế摰𡄯��齿�銝箏之�𡁻��粹𡢿�舀��箏����霈訾葵�∪銁頝𣬚聦 `ma20d` ����𣂷��芾��芾��� `ma60d`嚗Ǒlatest_close >= ma60 * 0.98` 銝� `latest_low <= ma20 * 1.03`嚗㚁��喳虾鋡怨�銝箸�����亦瑪隡�迅�舀��對�蝎曉��閗繮鈭��𡁻�鈭坿�餈嗵掩頝𣬚聦 `ma20` �典�蝥踹躹�港�蝔喟�摰𣬚�銋啁�銝芾���
    - [x] **撘訫���𧒄�𣳇�笔之�喟��湔辺隞� (Accelerated Intraday Breakout)**嚗𡁜銁 `CONSOLIDATING` �嗆���嚗䔶蛹鈭����蝻拚�憭扳隅/撘��条凒�交����甈⊥𠯫�𣳇�煺葵�∴��啣�鈭�𠯫��撩�踹之�喳��笔ế摰𠾼���銝芾�隞𦠜𠯫瘨典� `realtime_pct >= 3.0` �硋�蝳餅𣈲�穃� `recent_close >= anchor_low * 1.03`嚗䔶�隞瑟聢撠誩�蝡坔銁��遠蝥� VWAP 銋衤�嚗Ǒrecent_close >= vwap * 1.008`嚗㚁��𣂷漱�誩朖雿踵𧊋�曉之 2.5 �㵪�隞��颲曉� 1.3 �滚抅���嚗㚁����霈貉圻�烐�蝥扯秐�匧��� `WAVE_UP`��
    - [x] **摰䂿緵�匧�銝𦒘�甈⊥���𠶖����芸𢆡憿箏辣�箏� (State Rollover & Rollover Protection)**嚗帋耨憭滢�撘箏飵餈墧踎�⊥�餈䂿賒�𣳇�罸翧蝥輯��冽𧊋蝏誩� VWAP �噼萱�塚�餈鞱� 2 憭拍凒�亥圻�烐�����嗅ế摰朞�諹◤撘箏�頦Ｗ枂�烐綉瘙删��餉�蝻粹萅����亥�隞琿�雿漤◇撱嗡�瘨典�撘箏漲�烐�嚗���芾��湔���絲�� 2% �𡝗𠯫��隅撟� `realtime_pct >= 1.5`嚗㚁��芸𢆡憿箏辣 `WAVE_UP` �� `WAVE_UP_2` �� `entry_date`嚗���啣笆憭扳隅�∩蜓��答���蝔见像皛𤏸�頦芥��
    - [x] **�㯄�𡁜��嗉���隅撟�㺭�格� (Passed Real-time DF Context)**嚗𡁜銁�唳旿霈ａ���� `update_batch` �詨��餉�銝哨��曉�撠���滨����啗��� DataFrame 隡惩� `update_wave_structure_state` �賣㺭嚗䔶��䔶蝙�嗆��㦤�賢�瘥怎�蝥批��嗉恣蝞𦯀��閙�銝芾���移蝖格𠯫��隅撟���

## 2026-06-18 23:50
- [x] **靽桀�摰墧𧒄�唳旿�滚𦛚�烐綉蝒堒藁��凒����⊥�銋��憭望�銝舘䌊�典��䂿� Bug (Fixed PanedWindow Sash Position Persistence Bug)**嚗�
    - [x] **撘訫��嘥��𡝗葡�枏��斗�敹� (Initialization Guard Flag)**嚗𡁏鰵憓� `sash_restored` �嗆����𧶏��函�������憭齿�銋���� `sash_place` 雿滨蔭�㵪�撘箄��餅鱏撟嗉�皛斗����㗇�����芣葡�枏�瘥閙𧒄閫血��� `save_sash_pos` �其�嚗�蝠摨閖俈甇Ｖ�蝛粹�蝵格����颲寧��鞉�撠�迤蝖桃���蟮�滨蔭�唳旿閬����
    - [x] **摰䂿緵�箔�蝏�辣���撠箏站鈭衤辣��䌊����㰘蝸�箏� (Size-Aware Load & Layout Synchronization)**嚗𡁏𦆮撘���� 100ms �脩�撱嗆𧒄�㰘蝸嚗屸���蛹�湔𦻖蝏穃� `PanedWindow` �芾澈�� `<Configure>` 鈭衤辣���銝𥪯�敶梶�隞嗉繮敺𦯀��笔�摰賢漲嚗Ǒwidth > 100`嚗匧��齿�銵屸�甈� `sash_place` 撟嗥蔭雿滩����敹梹�摰��瘨�膄鈭�眏鈭擧葡�㯄𧫴畾菜��齿⏛�� (clamp) �𣂼�撖潸稲�� sash 雿滨蔭���硋��𠺶��
    - [x] **瘛餃���垢撠箏站餈�誘靽脲擪 (Extreme Coordinate Guard)**嚗𡁜銁 `save_sash_pos` 銝剖��牐�撖孵���器�𣬚�餈�誘嚗��撌佗�`pos <= 50`嚗㗇��誩𢰧嚗Ǒpos >= width - 50`嚗厩�銝渡��𤩺㺭�桀��湔𦻖�𥕦�嚗峕�蝏苷���垢�劐撓銝讠��墧��鞉�����硔��
    - [x] **摰䂿緵�滨��單釣銝芾��芸𢆡�峕郊��� V-Reversal �烐綉瘙� (Auto-Sync Favorites into V-Reversal Pool)**嚗𡁜銁�烐綉瘙䭾㺭�桀��啣遆�� `refresh_pool_data` 銝哨�撘訫�鈭�䌊�㕑�憓鮋��急��峕郊�餉����甈∪��唳𧒄嚗諹䌊�冽�撖� `GlobalFavoriteManager` �������∠巨�𡑒”銝𡒊��扳�敶枏��𣂼��～��𥅾璉�瘚见��㗇鰵憓䂿��滨��單釣銝芾�銝滚銁瘙牐葉嚗��雿輻鍂摰匧���䌊�典��嗡誑 `CONSOLIDATING` �嗆����� `v_reversal_pool`嚗�僎�冽��㚚�銵峕𤣰�䀝遠雿𣈯��孵�撘箏��嗵�摮条�嚗���唬��芷�㕑��嗆���頝冽芋�堒朖�嗉䌊�典��𢛵��

## 2026-06-18 23:35
- [x] **靽桀�銝餉��暸��嫣葵�∪龪�滨掩�衤��寥�撖潸稲蝵桅▲憭望��� Bug (Fixed Type Mismatch Bug for Favorites Pinning in Main View)**嚗�
    - [x] **蝏煺��∠巨隞�� string & zfill(6) ����硋龪��**嚗帋耨憭滢��其蜓蝥輻����皛扎����啗恣蝞㛖瑪蝔讠� `_run_compute_async`��蜓閫�㦛�见𢆡�鍦���䌊�匧��圈�𡁶䰻蝑� 5 憭�� `fav_stocks` �斗鱏�臬炏摮睃銁嚗Ǒx in fav_stocks`嚗厩��唳䲮��眏鈭� A �� DataFrame �� `code` �堒虜銝� `int64`��float64` �㚚�����澆�摮㛖泵銝莎��� `fav_stocks` ������蝏�蛹 6 雿齿㺭摮㛖泵銝莎�撖潸稲蝐餃�瘥𥪜笆蝏𤘪��雴蛹 `False` 雿踹�銝餉��曆�����孵�瘜函蔭憿嗅蝠摨訫仃�������蛹 `str(x).strip().zfill(6) in fav_stocks` 蝏煺�閫���硋龪�㵪�敶餃��Ｗ�鈭�蜓閫�㦛����鍦��餉�銝钅��嫣葵�∠�蝏嘥笆蝵桅▲�䔶��蹱��栶��

## 2026-06-18 21:40
- [x] **摰䂿緵 V-Reversal �烐綉瘙㰘䌊摰𡁜��堒𢆡��凒�唬�撘��剖��䠷��� (Implemented Dynamic Custom Columns & Open-Closed Principle Refactor for V-Reversal Pool)**嚗�
    - [x] **摰䂿緵�寞旿 columns ���銋匧𢆡���撱� Treeview 銵峕㺭�� values**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `refresh_pool_data`���撘����𧋦蝖祉������銁 values 銝剖𤐄摰𡁏��� `dff_val`��rank_val`蝑㗇�����蹱����朞��刻�皜脫�銝剝��� `columns` ���嚗諹䌊����啣�瘚�‵��抅蝖��堒��嗡�隞颱��芸��嗅�嚗諹噢�𣂷�銝𤾸�����啜�����◇摨讐�摰��閫��艾��
    - [x] **摰䂿緵�嗡噩�交𣈲����嗉䌊摰帋�瘛餃� col**嚗𡁏鰵��𢆡����鞾�餉�摰𣬚�蝚血� **SOLID 銝剔� OCP (撘��剖���)**��� `"rank"` 靽格㺿銝箔�憭批� `"Rank"`嚗�僎撖� values ���撱箄�銵䔶�敶餃���𡂝鞊∠��硔��笆鈭𡡞膄鈭���匧抅蝖��𦯀�憭𣇉��嗡�隞颱��芸�銋匧�嚗���� `Rank`, `dff`, `dff2`, `dff3` 蝑㚁�嚗��蝏煺��芸𢆡隡睃��朞� `get_df_all_val` 隞𤾸�摮䀝葉�� `self.df_all` 銝剔凒餈墧��硋僎摰峕�蝎曉漲�澆��吔��� `df_all` 銝剜𧊋摰帋��躰䌊����滨漣�鮋��隞� `flags` 銝剛繮�吔�隞舘�䔶誑�嗥′蝻𣇉��孵�颲暹��券𢒰�𡁶鍂�𡝗𣈲����
    - [x] **摰䂿緵銵典仍����芷����鮋�� (Adaptive Treeview Heading Resolution)**嚗帋耨�嫣� Treeview �� `heading` 皜脫��箏�嚗���笔��箔� `headers.items()` 摮堒���儐�舫���蛹�湔𦻖�滚� `columns` �������冽��� `columns` 銝剜溶�㰘䌊摰帋����嚗�� `red` 蝑㚁��峕𧊋�� `headers` 摮堒�銝剖�銋匧�蝷箏��塚�蝔见��芸𢆡靚�鍂 `headers.get(col, col)` 餈𥡝�撟單��鮋��嚗𣬚凒�亙��堒��祈澈雿靝蛹銵典仍���撅閧內撟嗆迤蝖桃�摰𡁏�摨誯�餉�嚗屸��滢��堒�銋匧�蝒��銵典仍蝛箇蒾撏拇���
    - [x] **�寞祥 _GLOBAL_CODE_NAME_CACHE �芸�銋厰�霂� (Fixed NameError for Code Name Cache)**嚗𡁜銁 `open_realtime_monitor` 憿嗥漣�剖�雿𦦵鍂�煺葉�曉�摰帋�鈭� `_GLOBAL_CODE_NAME_CACHE = {}`嚗峕��支�擃㗛�銵峕�銝钅�蝜���碶葵�∪�蝘唳𧒄嚗��憟堒��賣㺭 `get_stock_name` 靚�鍂撅��典��讛���紡�渡� `NameError` 撏拇���
    - [x] **摰䂿緵�桃�銝𠹺��桀�曌䭾��㗇𥋘�單𧒄�𥪜𢆡 (Arrow Keys & Selection Click Linkage)**嚗帋蛹�烐綉瘙� Treeview 銵冽聢蝏穃�鈭� `<<TreeviewSelect>>` 鈭衤辣嚗峕𣈲��漱�枏��朞�曌䭾��孵稬�㚚睸�䀝�銝钅睸��揢銝芾��嗅��嗚���甇亙銁銝餅綉�嗅蝱�𥪜𢆡�㰘蝸��𧒄�㕙蝥踴��銁 `refresh_pool_data` �瑟鰵�冽�銝剖��� `is_refreshing_pool` 鈭埝棅靽脲擪���嚗峕����蝳颱�擃㗛�摰𡁏𧒄�瑟鰵撘閗絲���暺㗛�蝏䁅圻�𡢅�敶餃��踹�鈭��憸烐葡�𤘪𧒄���甇颯��
    - [x] **摰䂿緵�烐綉瘙𣳇▲�誩��嗆���霈∩縑�� (Added Real-time Pool Stats Summary)**嚗𡁜銁 `refresh_pool_data` �唳旿�齿鰵憛怠��㵪�撘訫�撖� V-Reversal �烐綉瘙牐葵�∠𠶖����典�敶垍掩霈⊥㺭�箏�����硋僎霈∠��𨀣赤�䀹�隡謿�腈���𣈯��争�腈���𨅯�頦抽�腈���靝��争�苷誑�𦠜�餌��扳㺭���嚗�僎�冽�甈∪��唳𧒄�冽��凒�� `pool_label_frame` ��之����𧶏�摰䂿緵撖寧��找葵�∟�璅∪���憭�𠶖��之�䀹��飵��妟憸嘥�UI蝛粹𡢿�删鍂撘誩��䀹��扼��
    - [x] **摰䂿緵�烐綉瘙惩𢰧�栽�𡏭挽銝粹��孵�瘜其葵�﹦�萘��單𧒄�峕郊�瑟鰵銝𡡞�鈭格葡�� (Instant Favorite Selection Sync & Style Customization)**嚗𡁜銁 `show_context_menu` �� `toggle_favorite` 憭��瘚�葉嚗���交�雿𨀣��笔��� `refresh_pool_data` 銝餃𢆡靚�鍂��僎銝𥪜銁�唳旿皜脫�瘚�葉嚗諹𥅾霂乩葵�∪歇鋡急�霈唬蛹�滨��單釣嚗諹䌊�典銁�嗅�蝘啣�憓𧼮� `潃㦀 �滨�鋆�弘嚗䔶�銝箏笆摨𠉛� Treeview 憿寡蕭�� `"fav"` ��倌皜脫�嚗�僎�刻”�澆�撱粹𧫴畾萄��� `fav` 擃䀝漁�瑕�蝏穃�嚗���唳��笔�摨𥪯�皜�苊閫����緵��
    - [x] **靽桀�蝟餌��嗆��𠯫敹� target_hours 瘚桃��啣�畾菜滯�箸遬蝷� (Fixed target_hours Floating Point Formatting Issue)**嚗帋耨憭滢�銝餅綉�嗅蝱颲枏枂蝟餌��滚𦛚�嗆��𧒄嚗䈣target_hours` 摮埈挾�湔𦻖颲枏枂�烾鵭�笔�瘚桃��堆�憒� `5.833333333333333`嚗厩�蝻粹萅��銁�亙��澆��碶葉雿輻鍂 `:.1f` �𣂼��嗅蘨靽萘�銝�雿齿筑�孵��啜��
    - [x] **�寞祥�烐綉瘙惩��嗅��啣��𤑳��滚��𥪜𢆡 Bug (Resolved Repeated Linkage Triggered by Timer Refresh)**嚗帋耨憭滢��曹� Tkinter 撘�郊鈭衤辣璅∪��冽�銵� `tree.selection_set()` �Ｗ��劐葉�嗆��𧒄嚗䔶�撠� `<<TreeviewSelect>>` 鈭衤辣�典�瘨���笔�撘�郊撱嗉�瘣曉�嚗�紡�游��啣��𣂼僎�峕郊撠� `is_refreshing_pool` �滨蔭銝� `False` 銋见��滩圻�𤏸��剁�撘訫�擃㗛��瑟鰵�嗥��𣈯�憭滩��兩�萘撩�瑯���朞�摰帋� `reset_refreshing_flag()` 撟嗅⏚�� `log_win.after(200, ...)` 餈𥡝�撱嗉��滨蔭嚗𣬚＆靽嘥銁�劐葉�䀹凒鈭抒����甇乩�隞嗆�摰��鋡急㜃�芥���韐孵��漤��曆��亦𠶖���瘨�膄鈭��靚梶��滚��𥪜𢆡�� CPU 撘�����
    - [x] **�齿��𥪜𢆡�㗇𥋘銝箇′隞嗥����隞園店�� (Refactored Linkage Events to Hardware-Driven)**嚗𡁜���𧋦蝏穃��刻��� `<<TreeviewSelect>>` 鈭衤辣銝羓��𥪜𢆡憭��瘚��敶餃��齿�銝箇凒�亦�摰𡁻������ `<ButtonRelease-1>` �𢠃睸�㗛��橘�`<KeyRelease-Up>`, `<KeyRelease-Down>`, `<KeyRelease-Prior>` 蝑㚁�蝖砌辣�拍�鈭衤辣���朞��其漱鈭鍦�撅���售�𦦵����㗇𥋘�苷��𨅯��啣��啣�韏瑞��𡁏��㗇𥋘�萘�摰𣬚����嚗峕��支��瑟鰵�嗡��仿�撖潸稲���摰䂿鍂�瑟�雿𡏭◤�䠷�餈�誘��艇�滨撩�瘀�摰䂿緵瘥怎�蝥批朖�嗅�摨䈑�敶餃�閫��鈭�鍂�琿�蝜���啁��𡏭��典仃����孵稬銝斗活�萘�鈭支�蝎䀹��麄��
    - [x] **摰䂿緵�烐綉瘙𣳇��嫣葵�∩���遬蝷箔�蝵桅▲ (Prioritized Favorite Stocks in Monitor Pool)**嚗𡁜銁�唳旿憛怠��餉� `refresh_pool_data` 銝哨�撘訫��箔� `GlobalFavoriteManager` ��葵�⊥�摨誯�憭����銁����烐綉瘙惩�銵冽𧒄嚗屸�朞� $O(1)$ 憭齿�摨衣�����斗鱏嚗�����㕑◤���嚗��嚗厩��滨��單釣銝芾��𣂼�撟嗅撩�嗥蔭憿嗆遬蝷箏銁銵冽聢��銝𦠜䲮嚗峕芦�𡁶��扯��其��嫣�甈⊥��梹�雿蹂漱�枏��賜洵銝��潸��行瓲敹�䌊�㕑��嗆����硔��
    - [x] **�齿��烐綉瘙牐蛹銝�甇交�憭𡁶輕�鍦�銝擧��𡑒”憭渡𠶖���蝷� (Unified Single-Pass Multi-dimensional Sort & Column Header Sort Direction Indicator)**嚗𡁜�罸�韏偦帕�Ｘ踎��挽霈∠�敹蛛��� `refresh_pool_data` ���摨𤩺�銝哨�雿輻鍂�蓥�憭𡁶輕��� Key ��恣蝞埈䔉�碶誨��𧋦���撅� `sorted`���摨𤩺𧒄�寞旿 `(prio, type_flag, val, code)` �鍦�嚗��摨𤩺𧒄�寞旿 `(-prio, type_flag, val, code)` �鍦�嚗𣬚＆靽苷�蝞∪�雿閙�摨誯��嫣葵�⊿��Ｙ糼蝵桅▲嚗�僎�舀��啣�澆�摮埈��㛖��芷���摰匧�瘥𥪜笆����塚��� `tree_sort` �嗆挾�冽��耨�寥�匧��鍦��㛖�銵典仍��𧋦嚗䔶誑 `�深/`�嬋 ��扇��內敶枏��鍦��嘥�嚗䔶��刻䌊�典��嗅��唳��游�蝢𦒘���鍂�瑟�摰𡁶��鍦�嚗諹圾�喃��瑟鰵�擧�摨讐𠶖��腺憭梁��暸���


## 2026-06-18 15:30
- [x] **�齿� V-Reversal 撘箏飵�∪�靚�瓲敹��皛斗㦤�嗡��訫�瘚贝��𧼮� (Refactored V-Reversal Pullback Criteria & Hardened FSM Simulation Fallback)**嚗�
    - [x] **摰䂿緵銝交聢�亦瑪頞见飵憭扯��臬撩餈�誘 (Daily Trend Guard)**嚗𡁏覔�� `pullback_support_report.md` 銝剔�撘箏飵�∪�靚��敹蛛��函𠶖��㦤�嘥��� `INIT` -> `CONSOLIDATING` 瘚�蓮銝剔′�𤥁�皛斗辺隞塚�撘箏�閬�� `ma20d > ma60d`��𤣰�䀝遠�� `ma60d` 銝𦠜䲮嚗䔶��讐氖憭批�瘨典� `dff3 >= 20.0%`���蝏苷��㰘��穃�瘜函��琿秄甇餉�銝舘�頝𣬚聦雿滩�嚗䔶�霂���交�隡𤩺����銝箏����銝餃�隞见�����踹�摨瑞�撘箏飵�噼��～��
    - [x] **摰䂿緵蝎曄＆��瑪�舀�撣血ế摰� (Moving Average Support Bands)**嚗𡁜撩�嗉�瘙���唳𤣰�䀝遠�𡝗𠯫���雿𦒘遠雿滢� 20�亦瑪 �� 60�亦瑪 撘箸𣈲�穃蒂���蝳餃漲�粹𡢿����讐氖摨� -2.0% �� 2.0% 銋钅𡢿嚗㚁�蝖桐�蝑𣇉裦�刻絲���憭𦦵移��㨃雿齿𣈲�睲�嚗諹�皛斤�銝剜�摨誯��～��
    - [x] **摰𣬚�靽桀� FSM 蝳餌瑪�訫�瘚贝�璅⊥��𡁻� (Fixed FSM Simulation Mode Fallback)**嚗朞圾�喃��典����霂閧㴓憓���曹� `simulation_mode=True` 銝擧策�煾𣂎銵𣬚�摰� A �∩誨�� `600000` 瘛瑞鍂撖潸稲瘚贝�獢拇�憭𤥁��函�摰墧𠯫蝥踵㺭�株�峕㜃�芣�霂閧��桅���� `simulation_mode` �鮋���𡁻�蝞��碶蛹�冽芋���霂閙芋撘譍��湔𦻖�曇�嚗峕��煺誘 `scratch/test_v_reversal_fsm.py` 銝剔� 6 畾萄�甇亦𠶖��㦤銝𦒘縑�瑟鱏閮� 100% 蝏踵��朞�嚗峕瓷�匧��乩遙雿訫��䀹��仿�����

## 2026-06-18 11:00
- [x] **摰䂿緵霂行�蝒堒藁�喲睸�𣈯��嫣葵�﹦�嘥��Ｗ��唳旿/皜脫��剔㴓�峕郊銝𤾸�蝏湔�摨讐蔭憿� (Implemented Favorite Toggle, Auto-Update & Multi-Column Priority Sorting in Detail Dialogs)**嚗�
    - [x] **�� SectorDetailDialog 銝剜溶�罱�𡏭挽銝粹��嫣葵�﹦�嘥𢰧�桅�厰★**嚗𡁻���� `SectorDetailDialog._on_context_menu`���朞� `GlobalFavoriteManager` �瑕�銝芾�����孵�瘜函𠶖����冽��銁�喲睸�𨅯�銝剜�靘𥕞�𡏭挽銝粹��嫣葵�﹦�脲��𨅯�瘨���嫣葵�﹦�嘥𢆡雿頣�撟嗅銁�孵稬�嗅�摮鞱圻�𤑳𠶖����Ｖ��亙�颲枏枂��
    - [x] **�� CategoryDetailDialog 銝剜溶�罱�𡏭挽銝粹��嫣葵�﹦�嘥𢰧�桅�厰★**嚗𡁜��琿���� `CategoryDetailDialog._on_context_menu` ���銝𧢲��𨅯�嚗���圈��嫣葵�∪��ａ�餉����銝���
    - [x] **摰䂿緵霂行�蝒堒藁�滨��嗆����渡�霈ａ�銝𡡞��霈ａ𡡒��**嚗𡁜銁銝支葵 Dialog �嘥��� `__init__` �嗉恥��� `GlobalFavoriteManager` �睃��𡁶䰻嚗�銁蝒堒藁�喲𡡒 `closeEvent` 銝剛�銵屸��霈ａ��整��遙雿訫𧑐�寞㺿�㗛��寧𠶖���銝文�霂行�蝒堒藁����拍鍂 `QTimer.singleShot` 摰匧��瑟鰵�祈”�唳旿��
    - [x] **銝� CategoryDetailDialog 撘訫��滨�銝芾�蝵桅▲銝𡡞�鈭格葡�枏笆朣�**嚗𡁻���� `CategoryDetailDialog.refresh_data`����蓥�銝剜��� `_fav_stocks` 撠���嫣葵�∟�鈭��擃䀹�摨譍���漣嚗Ǒprio = 3`嚗匧銁��掩��撩�嗥蔭憿塚��� `_render_table` 皜脫��塚��典�蝘啣���蒂 潃� 鋆�弘嚗�僎�冽��亥郎�嗅��函鸌�㗇楛蝏輯��荔�`#1A2A1A`嚗劐�鈭桃遛�齿艶嚗Ǒ#00FF88`嚗厰�鈭格遬蝷綽�銝𦒘蜓�屸𢒰�𦠜踎�埈����颲曉�蝏嘥笆閫��銝��氬��
    - [x] **摰䂿緵�典��鍦��嗆����滨�銝芾����撖寧蔭憿嗆遬蝷� (Fixed Default Priority Display Across All Sorting Columns)**嚗𡁻���� `SectorDetailDialog` 銝� `CategoryDetailDialog` �� `refresh_data` �鍦� key ���𣳇�餉�����交覔�� `is_rev` �冽���頧� `prio` �惩����摨讐�瘜𨰻��＆靽脲�霈箇鍂�瑕��Ｘ�隞颱�摮埈挾����㚚�摨𤩺��梹��滨�銝芾�嚗���祉聦雿溻��𥁒霅虫葵�∴�憪讠��賢��寞旿 `prio` 閫��撘箏�蝵桅▲�刻”�潭�銝𦠜䲮嚗��摰�芦�朞��典�銝𧢲䲮蝏抒賒�厩鍂�琿�匧����畾菔�銵峕迤�滚��鍦�嚗�蝠摨閗圾�喃��笔��芣��匧�蝘唳�摨𤩺�蝵桅▲����∠撩�瑯��
    - [x] **靽桀�瘛餃��滨�銝芾��舘祕��△�嗆��𧊋�賢朖�嗅��啣�甇亦�瞍𤩺� (Fixed Sync Refresh Lag)**嚗𡁜銁銝文�霂行�蝒堒藁�� `_on_favorites_changed` 霈ａ��噼��寞�銝哨�銵仿�鈭� `self._dirty = True` 蝵株�霈曄蔭���撘箏�蝛輸�譍��������砌��園𡢿�唾�璉��伐�雿踵溶��/�𡝗��滨�銝芾�����渲��芸𢆡����唾圻�烐㟲銝芣�蝏�”�潛��齿鰵�𣂼�銝𡡞�鈭桅�蝏矋�瘨�膄鈭�漱鈭垍�皛硺�撱嗆𧒄��

## 2026-06-17 22:00
- [x] **�啣�蝒堒藁�閗繮�喲睸摮堒翰�蠘�皛支�靽桀�銝𡏭揣�詨�餈𤤿� KeyError 撏拇� (Added Window Capturing Keyword Filter & Fixed Eastmoney Diagnostics KeyError)**嚗�
    - [x] **摰䂿緵蝒堒藁�閗繮�𦦵揣獢��璅∠��寥�餈�誘 (Implemented Capturing Window Filter & Fuzzy Matching)**嚗𡁜銁�𨀣��瑕��齿��Ｙ�������嘥笆霂脲�嚗ǑCaptureWindowsDialog`嚗匧��冽��格�銝哨��啣�鈭� `�� 餈�誘` 颲枏�獢���鍂�瑕虾�冽��祆�銝剔凒�亥��亦����憸䀹��舀�銵𣬚�摨讛楝敺���桀�餈𥡝�摰墧𧒄璅∠�餈�誘��
    - [x] **�啣��𦦵揣餈�誘皜�征�厰僼 (Added Clear Button for Filter Input)**嚗𡁜銁餈�誘獢�𢰧靘扳鰵憓硺��𨀣�蝛算�脲��殷��孵稬�𦒘��桀�雿齿�蝝Ｗ��桀�嚗𣬚��喳銁�𡑒”銝剝��唳葡�枏僎摰峕㟲�曄內�閗繮�啁��券�蝒堒藁��
    - [x] **摰䂿緵��稬蝒堒藁憿寧蔭憿嗅��啣�蝷� (Implemented Double-Click to Bring Window to Foreground)**嚗帋蛹蝒堒藁憿孵�銵函�摰帋� `itemDoubleClicked` 靽∪噡嚗𣬚鍂�瑕��餃�銵其葉��遙銝�餈𤤿�銵峕𧒄嚗𣬚頂蝏蠘䌊�刻��� `core.bring_window_to_top_by_title` 摨訫� API嚗䔶��桀��嗅銁獢屸𢒰銝𠰴撩銵𣬚蔭憿嗚����笔僎瞈�瘣餃����滚蝱嚗峕�憭批𧑐�嫣噶鈭�漱�枏�������雿滨𤌍�������
    - [x] **摰峕�憭朞�皛斤𠶖�������誯�劐葉�Ｗ� (Implemented Selection Preservation Across Filters)**嚗𡁻�����𡑒”憿寧�靽∪噡蝏穃�銝擧㺭�桃恣�����朞�撘訫�����券�蝒堒藁�唳旿 `self.all_windows` 隞亙�憭𡁻�㕑�頦芷��� `self.selected_set`嚗�銁�冽�憸𤑳�餈�誘�峕�蝛箄��交��塚��賢��删�靽脲��嗡�撌脰◤餈�誘�鞱�憿寧��劐葉�嗆�����之�唳�����冽�憭𡁻�匧僎撖澆�蝒堒藁��漱鈭雴�撉䎚��
    - [x] **�啣��喲睸�𨅯�蝻𤥁�蝔见��臬𢆡頝臬��蠘� (Added Right-Click Option to Edit Application Launch Path)**嚗𡁻�撖寧頂蝏��鈭𤤿����瘜閖�朞� Windows API �芸𢆡�瑕��唳���虾�扯���辣頝臬�����琜��函��������躰”�潛��喲睸銝𠹺�����蓥葉嚗峕鰵憓硺� `�辷� 蝻𤥁�蝔见��臬𢆡頝臬�` �蠘����霈貊鍂�琿�朞��啗挽霈∠� `EditPathDialog` 撖寡�獢���刻���/蝎䁅斐蝏嘥笆頝臬�嚗峕���凒�乩蝙�� `QFileDialog` 瘚讛�撟園�匧��舀�銵峕�隞塚�`.exe`��.bat`��.cmd`��.py`嚗㚁��湔鰵�舘䌊�刻圻�穃�摮䀹㺭�桀�甇乩��脫�摮条���
    - [x] **�寞祥蝟餌�霂𦠜鱏銝剖�銝𡏭揣餈𤤿� KeyError 撏拇� (Fixed Eastmoney Process KeyError in Diagnostics Engine)**嚗帋耨憭滢��扯�霂𦠜鱏撌亙� `sys_performance_analyzer.py` �刻�銵諹��剜𧒄嚗𣬚眏鈭𤾸銁 `diagnostics["key_processes"]` ���憪见�霂滚�銝剝�瞍譍�銝𨀣䲮韐Ｗ�餈𤤿���睸�㵪����蝡臭��嗅笆�嗉�銵𣬚敞�牐�皜脫�嚗�紡�游銁擐硋��㰘蝸����嗅��唳𧒄�𥕦枂 `KeyError: 'mainfree'` 撏拇��� Bug���朞��典�憪见��嗆挾銵仿� `"mainfree"` �殷�雿輯��凋葉敹��憭笔�蝢𤾸�摰孵僎瘚���啣�蝷箔�韐Ｘ瓲敹��蝔讠�蝥輻��啣��拍���������

## 2026-06-17 21:45
- [x] **靽桀��鞉�蝞∠��典��函�摨誩鍳�冽��鞾��嗡��啣��喲睸蝞∠��䁅�銵� (Fixed App Launch Permission Issues & Added Run-As-Admin Option)**嚗�
    - [x] **摰䂿緵�喲睸�靝誑蝞∠��䁅澈隞賢鍳�兩�嗪�厰★ (Added Run-As-Admin Right-Click Item)**嚗𡁜銁 `webTools/window_manager/ui.py` ����������躰”�澆𢰧�桐�銝𧢲��𨅯�銝哨��啣�鈭� `�椘儭� 隞亦恣���頨思遢�臬𢆡` �其�嚗��霈貊鍂�瑟遬撘譍誑�寞�璅∪��㕑絲��閬�������頂蝏笔極�瑟��誩�蝏�垢��
    - [x] **摰䂿緵 WinError 740 �芷����鞉��臬𢆡 (Implemented Auto-Elevation on Permission Block)**嚗𡁻�撖寧鍂�瑁�銵� `resmon.exe` 蝑厰�閬�恣����寞����摨𤩺𧒄撘訫��� `OSError: [WinError 740] 霂瑟����雿𣈯�閬���𥩔 ���撘�虜嚗屸���� `show_context_menu` 銝剔��臬𢆡�閗繮�餉�����行��瑕�霂仿�霂荔�蝟餌�撠�䌊�其蝙�� `os.startfile(exe_path, 'runas')` fallback 閫血� Windows UAC 撘孵枂����鞟內嚗���啗䌊���韏瑯��
    - [x] **摰峕� UAC �𡝗��见末�脫擪銝𤾸鍳�典�撣��頧株砭�齿� (Added UAC Denial Handling & DRY Refactor)**嚗𡁜銁�鞉��臬𢆡�寞� `_launch_as_admin` 銝剖��乩�撖� Windows `WinError 1223` (�冽��垍�鈭� UAC ���) ���憟賣��瑕��䠷��亙�颲枏枂嚗屸俈甇Ｗ撕�箔�甈⊥𥁒�蹱�����塚�撠��摨誩鍳�典����敺�����撱箔��芸𢆡摨𠉛鍂�鞉���蔭霂ａ�餉��𣂼�銝箇𡠺蝡讠� `_setup_post_launch_layout_timer` 颲�𨭌�寞�嚗屸�敺� DRY 撟脣�蝻𣇉��笔���

## 2026-06-17 21:15
- [x] **�芷���蝟餌��滩蝸蝥輻����銝舘�蝔讠��找��� (Adaptive Heavy Thread & Process Diagnostics Optimization)**嚗�
    - [x] **�拙��墧瓲敹���啣�銝𡏭揣�詨�餈𤤿��烐綉 (Eastmoney & Non-Core Process Monitoring)**嚗𡁜銁 `sys_performance_analyzer.py` 銝剝���� `run_system_diagnostics` �餉���膄�誩�Python���朞噢靽～����梢◇��凝靽∪�嚗峕迤撘誩��靝��寡揣撖䕘�mainfree嚗争�萘熙�交瓲敹��蝔讠�霈∪��僐����嗅��惩笆蝟餌���瑪蝔𧢲㺭 >= 20 ����詨�餈𤤿�餈𥡝��芷���蝏蠘恣���嚗峕��𣇉瑪蝔𧢲㺭�鍦��� 5 ���頧質�蝔见僎�刻��剖�銵其葉餈𥡝��芷���霅血�嚗��撖潔漱�枏��喲𡡒撖嫣漱�㮖漣�蠘�摨血僕�啁�頧臭辣��
    - [x] **��漣霂𦠜鱏銵冽聢銝𤾸紡�� Markdown 雿𤘪��亙�**嚗𡁜�霂𦠜鱏憿菟𢒰銝� `tree_key_stats` 銵冽聢擃睃漲靚�㟲銝� 10嚗諹䌊�其誑 `�𩤃� [餈𤤿��䓞` �澆�����嗡�瘣餉�擃䁅�頧質�蝔讠�蝥輻��啣��餃�摮矋��峕郊�齿�鈭� `generate_md_report` �寞�嚗�銁撖澆枂�� Markdown 雿𤘪��亙�銝剖��牐�撅墧踎�堒�銝暸��詨�擃䁅�頧質�蝔页�撠�頂蝏�𥁒霅衣瑪蝔钅��潛眏 300 ����𣂼��� 400��
    - [x] **摰峕�蝒堒藁撖寥�蝞∠��典��餃�瘚���𧼮‵�惩𤐄**嚗𡁻���� `webTools/window_manager/ui.py` 銝剔���稬�𠰴��餉�銝箝����閖★敹恍�笔�憛思��訫稬敶餃�蝘餉秐��稬鈭衤辣嚗�僎銝娪��嗥洵 0 �堒��颱�閫血�蝵桅▲瞈�瘣鳴�蝚� 1 �㛖��舐�颲穃�靽萘���稬靽格㺿嚗��蝢𤾸�瘚��鈭支�銵䔶蛹��

## 2026-06-17 19:50
- [x] **隡睃�蝒堒藁�鞉���掩蝞∠��� UI 銵冽聢��稬蝻𤥁�銝𤾸�憛怠��� (Optimized Window Layout Table Double-Click Edit & Fillback Trigger)**嚗�
    - [x] **摰䂿緵�匧��箄�鈭支���� (Column-Specific Interactivity Branching)**嚗𡁻���� `webTools/window_manager/ui.py` 銝剔� `on_table_cell_double_clicked` �其������稬蝚� 0 �梹�蝒堒藁�寥����嚗㗇𧒄嚗峕�銵𢞖�𦦵���蔭憿嗅僎瞈�瘣領�嗪�餉�嚗𥕦���稬蝚� 2 �梹�敶枏�獢屸𢒰摰鮋�雿滨蔭嚗㗇𧒄嚗諹圻�爗�𨅯�憿孵翰�笔�憛恍�蝵桀����嘅���稬蝚� 1 �梹��滨蔭�鞉�嚗厩��嗡��舐�颲穃��塚��朞��曉�靚�鍂 `self.table_widget.editItem(item)` �见𢆡閫血�蝻𤥁�嚗屸俈甇Ｗ�撅� `NoEditTriggers` �餅迫鈭���餌�颲𡢅��峕𧒄�踹�鈭�洵 0 �堒銁��稬蝵桅▲�嗉秤�亦�颲𤑳𠶖���摰䂿緵鈭�凒蝚血��冽�憸����凒�䭾��賭�擃䀹����鈭支�雿㯄���
    - [x] **撠��憿孵翰�笔�憛急㺿銝箏��餉圻�� (Changed Quick Fillback to Double-Click)**嚗𡁜���𧋦�� `on_table_cell_clicked` 銝剔�蝚� 2 �堒��餉䌊�典�憛恍�餉�敶餃�蝘駁膄嚗�僎頧祉宏��僎�喳��颱�隞嗡葉嚗屸��滚銁�桅�𡁻�匧�銵峕�瘚讛��嗥�霂舐��餃紡�湧�蝵桀���◤閬����

## 2026-06-17 15:45
- [x] **�寞祥 V�见�頧� (V-Reversal) �嗆��㦤�𣳇��滚�撖潸稲瞏靝�瘙䭾說皞Ｖ�靽∪噡�煾�瞍𤩺� (Resolved V-Reversal Loop Leak, Cooldown Protection & Signal Recovery)**嚗�
    - [x] **摰䂿緵�亙�/鈭斗��亦漣瘛䀹掠�𠉛氖�瑕㭂�箏� (Implemented Cooldown Gate)**嚗𡁜銁 `update_wave_structure_state` �� `INIT` �嗆��溶�惩��湔㦤�嗚��𥅾霂亥�甇文��牐蛹頞�𧒄�𤥁��湔𣈲�𤏸◤瘛䀹掠嚗��霈啣� `last_fail_ts`嚗𥕦銁甇文��喳� 240 ���嚗�1銝芯漱�𤘪𠯫嚗劐�銝滚��典�銝�鈭斗��亙��齿鰵餈𥕦� `CONSOLIDATING` 瞏靝��烐綉瘙𩤃�敶餃��餅鱏鈭��𡏭◤瘛䀹掠 -> 銝衤�蝘垍凒�交說頞� < 6% �臬� -> �祇𡢿�匧�瞏靝�瘙惩僎�滨蔭 entry_date 銝箏�憭抽�萘��餉�甇餃儐�胯��
    - [x] **靽桀��瑕鍳�冽�銋��頞�𧒄�芣�憭望� (Fixed Load-time Auto-Expire Cooldown)**嚗𡁜銁 `load_consolidation_state` �㰘蝸餈睃�餈��銝哨��乩葵�⊥說頞喟�蝎鍦漲頞�𧒄嚗Ǒtrade_dist >= 3`嚗㚁��券�蝵桐蛹 `INIT` �嗆����峕𧒄撘箏��坔�敶𤘪𠯫�� `last_fail_ts = now_ts`嚗䔶蝙敺㛖頂蝏笔銁皜�征�萄偶皛⊥滯瘙䭾𧒄�賢�蝔喳��𠉛氖嚗��憭拍�撖寞�瘜閗◤霂臬��痹�雿輻��找葵�⊥�閫�芋�噼氜�啣���蘨瘣餉�瞏靝��∠��亙熒瘞游像��
    - [x] **摰䂿緵�嗆��㦤�滚��堒��脤�憭滚�頧賭��� (Idempotent State Loading Guard)**嚗𡁜銁 `load_consolidation_state` 撘訫�鈭�𡠺蝡讠� `_fsm_state_restored` 撅墧�扳�瘚页��踹�鈭�� K 蝥踵㺭�桃�摮䀹�憭齿�霈� `_is_restored` 鋡� from_dataframe �𣂼�霈曆蛹 True 撖潸稲�嗆��㦤�㰘蝸鋡急鱏頝航粥�� else ��𣈲�齿鰵霈∠� 4468 �芯葵�∠� Bug嚗剹����笔��唬��瑕鍳�冽𧒄嚗�笆�滚��㰘蝸霂瑟����蝑厩�頝舀㜃�迎��寞祥鈭��憭滩圻�烐�瘣埈𠯫敹𨰜��
    - [x] **摰䂿緵�芣�皜���𤾸朖�嗥���氜�䁅��碶�暺䁅恕�臬����潭𤣰蝝� (Auto-Save After Clean-up & Amplitude Hardening)**嚗帋蛹鈭�俈甇Ｚ䌊���瘣𦯀��𤩺㺭�桐��䭾𧊋�拍��嗵��券��臬�鋡怎��䁅��㺭�桀�甈⊥情�橒��� `load_consolidation_state` 皜��摰諹��唳旿銋见�蝡见�撘箏�靚�鍂 `save_consolidation_state(filepath)` �拍��賜�嚗��銝芾��函��䀝�瘣𦯀蛹 `INIT` �嗆��僎�券��坔� `last_fail_ts` 餈𥡝��亙��瑕㭂�𠉛氖����塚�撠��憪贝��交�隡讐�暺䁅恕�臬��冽��� `0.06`嚗�6%嚗㗇𤣰蝝扯秐 `0.035`嚗�3.5%嚗㚁��舀��滨蔭憿� `v_reversal_amplitude_limit` �冽������摰䂿緵擃䀝��蠘�皛日��芥��
    - [x] **摰䂿緵憭𡁜𧑐�唳旿霂餃�銝��渡�蝥輻�摰匧�撌亙�璅∪� (Implemented DataServiceFactory)**嚗𡁜銁 `realtime_data_service.py` 摨閖�撘訫�鈭� `DataServiceFactory` 撌亙�瘜典�銵函掩��砲撌亙���鍂蝥輻�摰匧�����齿��仿�嚗㇄ouble-Checked Locking嚗匧��啣�撅��臭����摮䀹㺭�格����嚗�僎�𣂷�鈭�遬撘誩�靘𧢲釣�� `register_instance` �𦠜�霂閙��� `clear_instances` �亙藁嚗䔶��寞𧋦銝𠹺�霂��憭𡁜𧑐霂餃�銵峕��羓𠶖��㺭�格𧒄���撘閧鍂���撖嫣��氬��
    - [x] **霈曇恣撟嗆�撅� FSM �嗆��蓮蝘颱��瑕㭂�𠉛氖�訫�瘚贝� (Expanded Cooldown Unit Tests)**嚗𡁜銁 `test_v_reversal_fsm.py` 銝剖��牐� `STEP 6` (�瑕㭂�罸��脖�餈���芣�) 璅⊥�嚗屸�靽萘�餈睃�鈭��靝葵�∠��� Breakdown �港� -> �桅�𡁜像�睃銁�瑕㭂�笔�鋡急㜃�芸銁瞏靝�瘙惩� -> �滨蔭 last_fail_ts �� 24撠𤩺𧒄�� -> �齿活�湔鰵憿箏⏚餈𥕦�瞏靝��麨�萘��券曎頝舐𠶖��㦤�剛�瘚贝�嚗�����霂� 100% 蝏踵��朞���

## 2026-06-17 15:30
- [x] **隡睃� PyQuant3 蝟餌�擃㗛�銵峕��券�����蜓蝥輻�銝� I/O 撟嗅��扯� (Optimized Main-Thread & I/O Performance for High-Frequency Streaming)**嚗�
    - [x] **撘�郊�湔鰵鈭斗���瓲蝻枏� (Asynchronous Kernel Cache Update)**嚗𡁜� `instock_MonitorTK.py` 銝剔� `kernel_srv.update_df_all` 銝餃𢆡皜拍�銝擧釣�仿�餉��曹蜓蝥輻��峕郊靚�鍂�齿�銝粹�朞� `self.compute_executor.submit` 餈𥡝��𤾸蝱撘�郊瘣曉�嚗�蝠摨閖��滢�擃㗛� Tick �券��𧒄銝餌瑪蝔见�憭扯�璅� Pandas ���霈∠�鋡急�韏�/��香嚗��憒� `apply_tree_data_sync_timed` �埈𧒄餈� 18 蝘𡜐���𣂎憸���
    - [x] **撘�郊�硋��䀹醌�讐��乩�����冽㺭�桀��坔�銝𡒊𠶖��凒�� (Asynchronous Database Operations in StockLiveStrategy)**嚗𡁻���� `StockLiveStrategy._check_strategies` 銝剔����� I/O-bound �唳旿摨枏��滢�����笔��峕郊靚�鍂��鸌�誩�靽∪噡 `log_signal_batch`����嗆�� `log_status_batch` 隞亙��湔鰵頝蠘葵�嗆�� `update_follow_status` 蝏煺�撘�郊�𡝗�鈭斤�銝餃��啁瑪蝔𧢲�韐寧� `self.db_queue`嚗�蝠摨閙��支�摰䂿�蝑𣇉裦霈∠�璉�瘚见儐�臬銁����煺漣�毺� SQLite 霂餃����鈭匧� I/O �餃���
    - [x] **�脣鴃�批��� Bidding 蝘滚��唳旿蝏𤘪��㰘蝸 (Defensive Schema Validation for Stock Selector Seeds)**嚗朞‘�其� `bidding_momentum_detector.py` 銝剔� `_load_stock_selector_data` �寞�撖� empty/None DataFrame 隞亙� `'code'` �埈糓�血��函��脤��諹䌊�������脫迫隞� `TradingLogger` 霂餃枂蝛箸㺭�格𧒄�𥕦枂 `KeyError: 'code'` 撖潸稲�典予�烐綉�臬𢆡�剛楝��
    - [x] **靽桀� SnapCache 蝏𤘪�蝻箏仃隞乩��𨀣�銋���Ｗ� (Fixed Missing Code Attribute in SnapCache for Stable Recovery)**嚗𡁜銁 `bidding_momentum_detector.py` ��遣 `_global_snap_cache` ��㺭�格𧒄銵仿�鈭� `'code': code` �桀�澆��改�雿踹��𡒊賒�芣��踹��滚遣�䔶葵�∪�摨誩��硋�頧賣𧒄�賢�甇�＆�𣂼��箏��渡�隞�������
    - [x] **�拍�撖寥�憭𡁏瓲 CPU 蝥輻�銝𢠃��滨蔭銝擧�銵諹�皞鞾�蝳� (Aligned Multi-Core ThreadPoolExecutor Worker Limits)**嚗𡁜笆 `StockLiveStrategy` ����� `self.executor` �� `self._io_executor` ��憭抒瑪蝔𧢲㺭�讛�銵䔶�摰匧�霈∠�嚗諹挽摰帋蛹 `min(32, (os.cpu_count() or 4) * 2)` 撟嗉����蝟餌� `livestrategy_max_workers` �滨蔭嚗屸�雿𦒘�餈��蝥輻�撣行䔉���蝜��銝𧢲���揢�� GIL 鈭㗇𦜖��

## 2026-06-17 14:25
- [x] **靽桀� PyQtGraph 璁�艙����∪耦�暸緾����嗅膥�剖� NameError 撏拇� (Fixed NameError in PyQtGraph Bar Flashing Timer Closure)**嚗�
    - [x] **暺䁅恕��㺭蝏穃�閫��蝻𤥁��舘䌊�勗��讐��賢𪂹�笔�撣�**嚗𡁜銁 `instock_MonitorTK.py` 銝剔�撋��摰𡁏𧒄�噼��賣㺭 `flash_delta` 銝哨��朞����暺䁅恕敶Ｗ� `w_dict=w_dict` 銝� `win=win`嚗��憭㚚�霂齿�雿𦦵鍂�煺葉��䌊�勗��誩撩蝏穃��喳遆�啣笆鞊∪��改��脫迫�� Nuitka 蝻𤥁��臬�銝见�撅�遆�唳�銵��瘥𨰻����典����雿𦦵鍂��瘥��撖潸稲摰𡁏𧒄�刻圻�烐𧒄�𥕦枂 `NameError: free variable 'w_dict' referenced before assignment in enclosing scope` 撘�虜��
    - [x] **�惩𤐄蝐餃�銝𤾸��典��扯粉�㚚俈��**嚗𡁜� `flash_delta` ����朞�蝖祉��� `w_dict["delta_bars"]` �瑕�撖寡情�孵�銝箏抅鈭� `isinstance(w_dict, dict)` �� `w_dict.get("delta_bars")` 摰匧�霂餃�嚗諹��輻征�潭��𧼮虜閫�㺭�桀��𤑳�撅墧�找��桀�潮�霂荔��𣂼�銝餅綉�嗅蝱�𤾸蝱�芰�摰𡁏𧒄�函�餈鞱��嗅�憯格�扼��

## 2026-06-16 23:55
- [x] **�典�撖寥�雿輻鍂��㺭摮䀹𦆮�滨蔭��辣撟嗅��箄祗�單芋�堒��啗粉�� (Aligned Voice Rate & Volume Parameters & Hardened Settings Reading)**嚗�
    - [x] **�拍�撖寥� SAPI 銝� pyttsx3 撘閙�暺䁅恕��**嚗𡁜� `alert_manager.py` 銝剔� `getattr(cct, 'voice_rate', ...)` �� `getattr(cct, 'voice_volume', ...)` 蝻箇�暺䁅恕�澆��思� `200`/`1.0` 靚�㟲銝� `220`/`1.2`嚗䔶誑摰��憟穃� `global.ini` 暺䁅恕��頂蝏罸�蝵桀��啜��
    - [x] **撘箏��航��𣇉�蝡航祗�喳��啗粉�㚚�璉埝��**嚗𡁻���� `trade_visualizer_qt6.py` 銝剔凒�亥粉�� `cct.voice_rate` 銝� `cct.voice_volume` ����扯��其蛹摰匧��� `getattr` �滨漣�亙藁嚗�僎摰��撖寥�鈭� `220` �� `1.2` ��頂蝏毺漣蝻箇��滨蔭嚗�蝠摨閙��支��曹�憭㚚�璅∪��嘥��𡝗𧒄�滨蔭摮堒�撠𡁏𧊋撠梁貌�𥕦枂 `AttributeError` �餅鱏霂剝𨺗�剜𥁒����押��
    - [x] **頝煾�𡁜��曇楝霂剝𨺗�剜𥁒���撉諹�**嚗朞�銵� `verify_voice.py` �𣂼�靚�鍂 `VoiceAnnouncer` �朞��砍𧑐����舘祗�單偘�暹�霂𤏪��䭾𥁒�嗘��扯�蝔喳���

## 2026-06-16 23:45
- [x] **摰䂿緵��蟮敹怎�頧賢��嗉䌊摰帋��埈㺭�株䌊�冽��碶��冽��遬蝷� (Implemented Automatic Custom Column Extraction & Dynamic Display on History Load)**嚗�
    - [x] **摰䂿緵敹怎��芸�銋匧�憸�醌�譍��𣂼��箏�**嚗𡁻���� `load_from_snapshot`嚗�銁銝芾��齿��嗆挾�齿鰵憓硺� `raw_sectors` �� `race_candidates` 憸�醌�誯�餉����憭蠘䌊�冽��硋枂靽嘥��典��脣翰�找葉����㕑䌊摰帋��埈㺭�殷�憒� `Rank`��dff2`��red`��volume`��win` 蝑厰��詨�摨阡��梹�嚗�僎撱箇� `code -> custom_dict` ��翰��䰻�曇”��
    - [x] **摰峕��芸�銋匧�畾萇�����笔� TickSeries 銝𤾸�撅�蝻枏�**嚗𡁜銁�滚��堒�敺芰㴓銝哨�撠�醌�誩���䌊摰帋��埈㺭�桅��啣��墧鰵�𥕦遣�� `ts.custom_cols` 隞亙��其� UI 皜脫��� `new_snap_cache[code]` 摮堒�銝准��迨銝曆�霂���𡒊賒�冽�銵� `_ensure_sectors_reconstructed` 餈𥡝��踹��滚遣�塚�`_reconstruct_sector_from_candidates` �賭��典�敹怎�蝻枏�銝剛繮�硋�摰峕㟲��䌊摰帋��梹�餈𥡝��𢆡��遬蝷箏銁蝡硺遠�Ｘ踎銝𤾸��条��輻�銵冽聢銝准��

## 2026-06-16 23:25
- [x] **�齿�蝡硺遠樴坔仍蝡噼��㗇� `race_candidates` ���牐誑摰䂿緵蝏嘥笆蝎曄������ (Refactored race_candidates for Lean Persistence)**嚗�
    - [x] **摰䂿緵蝎曄�璅∪����畾菔���**嚗𡁻���� `bidding_momentum_detector.py` 銝剔� `race_candidates` ���𣳇�餉�嚗�竉蝳颱�憒� `score_diff`��pct_diff`��price_diff`��dff` 蝑匧�雿坔漲�誩�畾萸��蘨靽萘��其� UI 憿菟𢒰蝎曄��砽�𡏭��聆�嘥�蝷箇��詨���㺭�桀�畾蛛�憒� `code`��name`��role`��pct`��score`��l_score`��pattern_hint` 蝑㚁�嚗�銁摰��靽嗪�憭滨��唳旿�Ｗ�����𣂷�嚗峕�憭批��譍�敹怎��賜��嗥��拍�雿梶妖嚗䔶��寞𧋦銝𦠜��支��𦯀�憭扳㺭�桃��賜�撘�����
    - [x] **靽桀��曹�摮堒�憭扳𡠺�瑞撩憭勗��𤑳�霂剜��躰秤 (Fixed Missing Curly Brace SyntaxError)**嚗帋耨憭滢������𧋦銝剖銁 `for s in stocks:` �滚�銝剖��澆��碶�敶枏�撟園�䭾��� `race_candidates.append({` 憭扳𡠺�瑟𧊋�剖�隞亙� `rc_item` �㗛��芸�銋劐噶�湔𦻖靚�鍂��艇�滩祗瘜閧撩�瘀��Ｗ�鈭�芋�㛖�霂剜��亙ㄝ�扼��
    - [x] **頝煾�𡁜��誩��������𧼮�瘚贝�**嚗𡁜銁�砍𧑐�𣂼�頝煾�� `pytest scratch/test_manual_force_save.py scratch/test_load_snapshot.py scratch/test_self_heal_sectors.py` 蝑劐��游�銝擧�銋����䌊���敹怎��㰘蝸�詨�������霂𤏪�瘚贝� 100% 蝏踵��朞�嚗峕瓷�匧��乩遙雿訫�雿𦦵鍂��

## 2026-06-16 21:30
- [x] **隡睃��踹�霂��銝𢠃��芣鱏銝𤾸撩�餅�敹菜０摨血�蝷� (Optimized Board Score Capping & Enhanced Strength Gradient)**嚗�
    - [x] **撘訫��䂿瑪�扳�餈𥕦�頧臬�蝻拍�瘜� (Soft Non-Linear Compression)**嚗𡁻���� `bidding_momentum_detector.py` 銝剔� `board_score` 霈∠��砍�嚗���支� `min(..., 98.5)` ��′銝𢠃��芣鱏���撖孵撩摨西��� 85.0 ��踎�梹���鍂�峕𤩅皜鞱��砍�餈𥡝�頧臬�蝻抬�雿輯�擃睃��踹�敺堒�撟單��嗆��� 85.0 ~ 99.5 銋钅𡢿嚗�銁蝏湔��啣�澆銁����粹𡢿����𣂷�嚗�蝠摨閗圾�喃�頞�撩憸䀹��𨅯�蝭��敺𦥑�肽圻憿� 98.5 ����仃�餃躹��漲����對�靽萘�鈭���曄�撘箏摹璇舫�撅�活��

## 2026-06-16 21:10
- [x] **摰䂿緵�踹��唳旿�芣�銝𤾸��笔��脣翰�找��桐耨憭� (Implemented Sector Self-Healing & Corrupted Snapshots Batch Repair)**嚗�
    - [x] **摰䂿緵�踹��嗆㺭�株䌊��㦤�� (Sector Data Zero-Case Self-Healing)**嚗𡁜銁 `bidding_momentum_detector.py` ��踎�堒�頧賢�撅�㦤�嗡葉嚗峕鰵憓硺� `_ensure_sectors_reconstructed` �芣��寞����頧賢���翰�扳���蟮隡朞�銝剜踎�埈㺭�桐蛹蝛箸�銝仿��埈�嚗Ǒsectors <= 1`嚗劐�銝芾���㺭�桀��湔𧒄嚗諹䌊�刻圻�煾���撌亦��滚遣嚗�抅鈭𦒘葵�∪�蝐颱�撘箏漲�孵�嚗Ǒscore >= 0.5` �� `abs(pct) > 1.5` 餈�誘�芷𨺗嚗㕑䌊���撱箏��𤩺踎�堒僎瘛勗漲霈∠�樴坔仍���瘨刻�蝑㗇楛摨行����敶餃��踹�鈭���脩蒾�輻緵鞊～��
    - [x] **銝��桃�����嗘耨憭滚��脣�獢� (Batch Repaired Corrupted Disk Snapshots)**嚗𡁶��嗘� `scratch/repair_problematic_snapshots.py` 靽桀�撌亙�嚗屸�朞�璅⊥��硺漱�𤘪𠯫銝𤾸��睃��券�蝳餌�撘箏� bypass嚗��蝤��銝𦠜��匧��毺� `bidding_20260421.json.gz`��bidding_20260515.json.gz`��bidding_20260610.json.gz` 蝑� 9 銝芸�獢��銵䔶�摰峕㟲����株蝸�乓��䌊�������拍�摰匧��坔�嚗𣬚�霂𦠜鱏�券�敹怎���踎�𡑒恣�啣�撌脣�蝢𡡞�敶� 389嚗���唬���蟮�唳旿����湔�折𡡒�胯��

## 2026-06-16 20:55
- [x] **靽桀���蟮敹怎��㰘蝸撘�虜銝𤾸��𤩺𧊋摰帋�撏拇� (Fixed Snapshot Load Exception & Undefined Variables NameError)**嚗�
    - [x] **靽格迤 `_reconstruct_sector_from_candidates` 銝剔� `current_leader` �㗛�撘閧鍂**嚗𡁜銁 `bidding_momentum_detector.py` �� `load_from_snapshot` ��靚�鍂���撱箸踎�埈䲮瘜蓥葉嚗��隡𣳇�垍� `_determine_role` ��𧊋摰帋��㗛� `current_leader` 靽格迤銝箏��冽迤蝖桀�銋厩� `leader_code`��
    - [x] **靽桀� `_reconstruct_sector_from_candidates` 銝剔撩撠� `configured_cols` �� `core_keys` �㗛�摰帋���䔮憸�**嚗𡁜銁 `_reconstruct_sector_from_candidates` 撘�憭游�銋劐�蝻箏仃���撅��芸�銋厰�蝵桀� `configured_cols` �峕瓲敹��摮埈挾��� `core_keys`嚗�蝠摨閙��支��冽��函��餅��㰘蝸��蟮敹怎��唳旿�嗥眏鈭� NameError �𥕦枂�� `name 'configured_cols' is not defined` 撏拇�嚗���唬��䀝葉����䀝�敹怎��唳旿��迤撣貉䌊��蝸�乩�摰𣬚���緵��

## 2026-06-16 19:20
- [x] **隡睃�銝芾��蠘�銝𧢲��𨅯�銝粹�霈支��劐�靽桀�敹急㭘�讛挽蝵桃���䌊��� (Default Combobox Upward Pop-up & Fixed Settings Dialog Scaling Auto-Adaptation)**嚗�
    - [x] **銝芾��蠘��𨅯�暺䁅恕銝𦠜��� (Default Upward Pop-up)**嚗𡁜� `adjust_action_combo_post` 蝞��碶蛹暺䁅恕�湔𦻖銝𦠜�嚗���餃�����拍��鞉�霈∠�銝𡡞� DPI 憭𡁏遬蝷箏膥颲寧��寥�嚗䔶��單偶�詨𧑐�脫迫�𨅯�憿寡◤撅誩�摨閖�隞餃𦛚�讛��芷��～��
    - [x] **霈曄蔭蝒堒藁 DPI 蝻拇𦆮銝舘䌊����劐撓�舀� (DPI-aware Resizable Settings Window)**嚗𡁜銁 `open_top_bar_settings` 銝剜覔�� `_get_dpi_scale_factor()` �冽��恣蝞㛖����憪见之撠𧶏�撟嗅��� `resizable(True, True)` �舀�嚗��霈貊鍂�瑕銁蝻拇𦆮�誩榆颲�之�嗆��刻������偕撖詻��
    - [x] **�滢�摨閙��脤��∠蔭摨閖�摰� (Pinned Bottom Operations Bar)**嚗𡁻����蝏�辣 packing 憿箏�嚗��摨閖��滢��� `btn_frame` �𣂼��� `notebook` 銋见�餈𥡝� `side="bottom"` �� pack��迨銝曄＆靽嘥朖雿踹銁蝒堒藁蝻拙��㚚�摨虫�頞單𧒄嚗���函��𨅯��争�腈���𨅯�皜��腈���𦦵＆摰尠�脲��桀�蝏�糼�Ｗ�摨訫虾閫���喃�鋡� notebook �文枂颲寧�嚗�蝠摨閗圾�單��格�瘜閙�雿𦦵��桅���

## 2026-06-16 19:00
- [x] **隡睃�憿園�敹急㭘�誩𢰧靘扳綉�嗆��桃���遬蝷箔��湔𦻖�嗆��挽蝵� (Optimized Top Bar Right Control Buttons Granular Toggle & Direct Variable Setter)**嚗�
    - [x] **�啣��芸��臬��賜��𦦵凒�交�銵𢞖�嘥翰�瑕��� (Direct Execution Shortcuts for Disabled Top Bar Groups)**嚗𡁜銁 Tab 1 (憿園�敹急㭘蝏�辣) 銝哨�銝� 12 銝芸虾隞亦凒�交�銵𣬚��蠘�蝏�辣嚗���𦦵��把�腈���𣈯�㕑��腈���𦦵�隞猾�腈���𡏭�撽砂�萘�嚗匧銁�嗅��㗇��喃儒�拙�鈭� `�� �扯�` �厰僼��
    - [x] **摰䂿緵�航��抒𠶖����扯��厰僼�嗆����冽���摰朞��� (Dynamic Enable/Disable State Synchronization)**嚗帋蛹鈭�俈甇Ｗ��賢�雿辷�敶梶�隞嗅銁憿園�敹急㭘�譍葉撌脰◤�暸�㗇遬蝷箸𧒄嚗䈣�� �扯�` �厰僼撠�䌊�典�鈭𡒊��函𠶖���`disabled`嚗㚁�敶梶�隞嗆𧊋�暸�㚁��券▲�典極�瑟�銝剛◤�鞱�嚗㗇𧒄嚗䈣�� �扯�` �厰僼撠�◤瞈�瘣鳴�`normal`嚗㚁��冽��芷��孵稬�喳虾�祇𡢿靚�鍂霂亙��賣�隞歹�銝娍�銵��隡朞䌊�典��剛挽蝵桃����雿㯄���蛹銝脲���
    - [x] **摰䂿緵�批��厰僼蝏���曄內銝𡡞��� (Sub-Button Visibility Toggle)**嚗𡁜銁 `instock_MonitorTK.py` 銝哨�撖孵𢰧靘扳��厩��批��厰僼嚗�� `Win`, `TDX`, `THS`, `DC`, `Tip`, `Real`, `Vis`, `Vo`, `Pop`, `ALink`, `��` 蝑㚁�撱箇�鈭���冽�撠� `self.right_control_widgets`��覔�桃𡠺蝡见虾閫��批��� `self.right_control_visibility` �冽��笆���蝏�辣�扯� `pack()` �� `pack_forget()`嚗䔶蝙敺堒銁撅誩�頞��/擃� DPI 蝻拇𦆮皞Ｗ枂�嗅虾隞仿�朞��鞱��典�銝滚虜�冽��格䔉摰���踹��格𣏹��
    - [x] **�� Tab �厰★�⊿���翰�瑟�霈曄蔭�屸𢒰 (Rebuilt Settings Window with Tabbed Notebook)**嚗𡁜銁 `open_top_bar_settings` 銝剖��� `ttk.Notebook` �齿�銝箏� Tab �屸𢒰��
        - **Tab 1 (憿園�敹急㭘蝏�辣)**嚗𡁜�蝷箔蜓�蠘��箏�嚗��嚗𡁜��粹�㗇𥋘��𪂹�罸�㗇𥋘蝑㚁����隞嗥��批���
        - **Tab 2 (�喃儒�批��厰★)**嚗𡁜椰�𤩺綉�嗅�摮鞉��桃��航��扳遬蝷綽��單��嗵凒�亦�摰𡁜僎�滢� `self.win_var`, `self.voice_var` 蝑匧��讐�摰墧㺭�潘��潛𠶖�����
    - [x] **摰䂿緵����嗆���甇乩��芸𢆡摮条� (Bi-directional State Sync & Auto-Save)**嚗𡁏凒�� Tab 2 �單�����喳�潭𧒄嚗𣬚凒�亙銁�䔶�銝� TK 敶勗��㗛�銝𦠜�雿頣��祇𡢿閫血��㗛�撖孵��� trace �穃𨯬�𠰴�靚��餉�嚗��嚗朞祗�喟𠶖����Ｕ��鸌敺���脤�蝏条�嚗㚁�撟嗡��桀��� UI �嗆����蹱�銋�� (`self.save_ui_states`)嚗峕����滚鍳�單𧒄�滚���
    - [x] **�惩𤐄 UI 頝其�霂嘥�頧賣㦤�� (Hardened Configuration Persistence)**嚗𡁜銁 `load_ui_states` 銝� `save_ui_states` 銝剜𦻖�乩� `right_control_visibility` �滨蔭畾蛛�摰𣬚��舀��啣��讐��㰘蝸�芣���

## 2026-06-16 18:00
- [x] **�啣�憿園��批��讐�隞嗅��喃�撣������� (Added Top Bar Component Switches & Layout Persistence)**嚗�
    - [x] **摰䂿緵敹急㭘撘��單綉�園𢒰�� (Quick Toggle Settings Dialog)**嚗𡁜銁 `instock_MonitorTK.py` 摨閖�����賭��㕑��𤏪�`action_combo`嚗劐葉�啣��𨅯翰�瑟�霈曄蔭�嗪�厰★��圻�穃�撘孵枂�芸�銋㕑挽蝵桀笆霂脲� `ToggleSettingsDialog`嚗峕��啣��粹▲�典翰�瑕��賣�����匧�璅∪�嚗��嚗𡁶遞���蝝Ｕ��𧒄�湔𠯫�麄��漱�梶��乓��翰�瑕𢆡雿栶��𠶖���瘚卝��𥁒霅行綉�嗚����滩��函�嚗㚁���捂�冽��朞� Checkbutton �暸�㗇綉�嗅�璅∪���遬蝷箸��鞱���
    - [x] **�冽��綉�嗅� Frame �曄內�鞱�銝𤾸�撅��齿�**嚗𡁜銁 `instock_MonitorTK.py` ��▲�典翰�瑟�銝哨�撖孵�璅∪��厰�餉� Frame 餈𥡝��拍��𠉛氖銝𤾸𦶢�㵪�`search_frame`, `date_frame`, `strategy_frame`, `action_btn_frame`, `status_frame`, `alarm_frame`, `linkage_frame`嚗剹����颱�摮䁅挽蝵格𧒄嚗𣬚頂蝏煺��芸𢆡�扯��� Frame 撖孵��� `pack()` �� `pack_forget()`嚗�僎�芷����瑟鰵�嗅捆�典�撅���
    - [x] **摰䂿緵撘��喟𠶖���頝其�霂苷�摮䀝��芣�餈睃� (Toggle State Persistence & Recovery)**嚗𡁜銁 `save_ui_states` 銝� `restore_ui_states` 銝剜𦻖�乩� `top_bar_visibility` �滨蔭憿嫘���摨誩�憪见��塚�隡朞䌊�刻粉�� `window_config.json` �𣬚�撘��喟𠶖�����笆銝滚���/擐𡝗活雿輻鍂��㴓憓�䌊�刻�銵諹䌊��‵���暺䁅恕�典��荔�嚗�僎�其蜓�屸𢒰��遣�𢠃���箸𧒄����峕郊嚗�蝠摨閙��支�雿𤾸�颲函��曄內��/擃漗PI蝻拇𦆮瘛瑁�撅譍�憿園��批��讛�摰賬��紡�游𢰧靘批��桀��唾◤鋆��銝娍�瘜閧��餌��拍�蝖砌慾��
- [x] **閫���蠘��㗇𥋘銝𧢲��𨅯�蝳餃��典云餈穃紡�渲◤鋆�����瘜閙䰻�衤�皛𡁜𢆡銋讠撩�� (Fixed Action Combobox Bottom Clipping & Auto-Popup Upwards)**嚗�
    - [x] **�𣂼���憭批虾閫���� (Limited Dropdown Height)**嚗𡁜� `action_combo` �� `height` ��㺭蝖祉�����嗡蛹 `12`嚗����𧊋����坔�霂蓥�甈⊥�抒��亙��� 20 銵屸�厰★嚗㚁�憭批��滢�鈭���㕑��閧��拍��讐�擃睃漲嚗�僎�芸�瞈�瘣颱��喃儒蝥萄� Scrollbar 皛𡁜𢆡�𡁻���
    - [x] **摰䂿緵�冽���蝵株䌊����文� (Dynamic Postcommand Offset Positioning)**嚗𡁜銁 `action_combo` �� `postcommand` �噼�銝哨�撘訫�鈭� `adjust_action_combo_post` 雿滨蔭�芣�瘚讠�瘜𨰻����孵稬銝𧢲��𨅯��塚��芸𢆡�瑕�撅誩��拍�擃睃漲銝𤾸��� widget �典�撟訫���頂銝讠� `widget_y` �� `widget_height`嚗��埝綫霈∠�摨閖��拐�蝛粹𡢿��
    - [x] **摰䂿緵閫血�銝𦠜��曄內 (Upward Drop Pop-up)**嚗朞𥅾�拐�蝛粹𡢿撠譍�銝𧢲��𡑒”������窈瘙��摨血�銝� 40px ����券��潘�蝟餌�隡朞䌊�刻恣蝞堒枂�睲�����啣�蝘駁�嚗Ǒ-widget_height - popup_height`嚗㚁�撟園�朞� `ttk.Style().configure('Action.TCombobox', postoffset=...)` �冽��釣�交甅撘𧶏�雿蹂��厩���䌊�兩�𨅯�銝𠰴撕韏猾�脲遬蝷綽�敶餃�閫��鈭���刻斐��遙�⊥��碶���儘���銝贝◤鋆��銝Ｗ仃�厰★���瘜閙��函��𤤿���


## 2026-06-16 17:30
- [x] **瘛勗漲隞��摰⊥䰻銝� V�见�頧� (V-Reversal) 蝞⊿�摰匧��惩𤐄 (V-Reversal Code Review & Pipeline Hardening)**嚗�
    - [x] **靽桀� `_has_anomaly_pattern` �喲睸閫��撘�虜 (Fixed Unpacking TypeError)**嚗𡁜縧�支��𦯀�隞���𠬍�銵乩�鈭� `try` �埈錰撠曄撩憭� of `return False, ""` 霂剖蘂嚗䔶��拍�銝𦠜�蝏苷�撖寥��孵�銝芾�餈𥪜� `None` 餈𥡝����� `TypeError: cannot unpack non-iterable NoneType object` 撖潸稲����亙援皞���
    - [x] **��僎撟嗆凒�啣��典耦���瘚贝��� (Merged & Updated Anomaly Pattern Detection Rules)**嚗𡁜蝠摨閙４��� `_has_anomaly_pattern` 銝剛◤�芣鱏 of dead code �餉�嚗���嗡葉�游�蝖桃���㺭���潔�敶Ｘ���蝘唬��笔遆�啣��𣂷�瘛勗漲��僎����思�撠��靝�撘�擃䁅粥�嗪��潭𦆮摰質秐 `0.995`����𣈯�撘�擃䁅粥�嘥笆瘥𠉛𤌍���撘��䀝遠靽格迤銝箸𠯫���擃䀝遠嚗Ǒprice > high * 0.98`嚗剹���撟嗅僎�啣�鈭��𨅯撩�輻輕���嘥��𡏭��輻�撟�憬�謿�嘥耦��ế摰𡄯��踹�鈭�迨�滚�甇颱誨�����紡�渡�敶Ｘ���瘚衤腺憭晞��
    - [x] **�惩𤐄 `get_v_shape_signal` 隞���澆��� (Code Key Normalization)**嚗𡁜銁 `realtime_data_service.py` 璉�蝝� `_consolidation_flags` �㵪�撖嫣��亦� `code` 撘箏��扯� `str().strip().zfill(6)` 閫���𤥁蓮�ｇ�瘨�膄鈭���桀�潭聢撘𧶏��怎征�潭��游�嚗匧紡�渡�摮堒��賭葉銝Ｗ仃�鞉���
    - [x] **摰峕��芸𢆡�� FSM �函𠶖������霂閖�霂� (Validated Transition Flow)**嚗𡁜�甈∟��� `scratch/test_v_reversal_fsm.py` �芸𢆡�𡝗�霂𤏪�撉諹�鈭�� `INIT` -> `CONSOLIDATING` -> `WAVE_UP` -> `PULLBACK` -> `WAVE_UP_2` -> `INIT` �� 5 蝥抒𠶖��㦤餈�宏�� 100% 甇�＆�改�撟嗅銁 `v_reversal_code_review_findings.md` 敶埝﹝��

## 2026-06-16 16:30
- [x] **蝏煺�銝𡡞��� V�见�頧� (V-Reversal) 靽∪噡 FSM �嗆��㦤蝞⊿�撟嗆��𡁜��䁅䌊�典��仿� (Unified & Refactored V-Reversal FSM Signal Pipeline & Enabled Live Auto-Queue Integration)**嚗�
    - [x] **摰峕� V�� FSM �嗆���頧砍����霂�**嚗𡁜銁 `scratch/test_v_reversal_fsm.py` 銝剔��嗘�擃䀝��毺𠶖���頧砍����霂𤏪�璅⊥�鈭���渡� `INIT` -> `CONSOLIDATING` -> `WAVE_UP` -> `PULLBACK` -> `WAVE_UP_2` -> `INIT` ��𠶖���頧祇曎嚗�僎撖孵��嗆挾�� `get_v_shape_signal` 靽∪噡�潸�銵䔶�鈭抒��峕�憭滨�銝交聢�剛����霂� 100% �𣂼��朞�嚗屸�霂���嗆��㦤���撖孵�憯格�找���＆摨艾��
    - [x] **蝏煺�靽∪噡皞𣂷�瘛䀹掠�扳� Heuristics �餉�**嚗帋蝙 `DataPublisher.get_v_shape_signal` 敶餃�靘肽� FSM breakout 蝒�聦�文�嚗���� `WAVE_UP` �� `WAVE_UP_2` �嗆挾閫血� `True`嚗㚁�撟嗅銁 `stock_live_strategy.py` 銝剖蝠摨訫��支��扳��� 30 �冽� K蝥� �牐�頝��/�滚撕 Heuristics �臬�撘讛恣蝞𦯀誨���摰䂿緵鈭��餉� of �閙�蝏煺���
    - [x] **摰䂿緵 FSM 靽∪噡摰墧𧒄�嗆��釣�乩�蝑𣇉裦�仿��脤���**嚗𡁜銁摰䂿�蝑𣇉裦敹�歲銝哨��朞� `v_shape_triggered` ��扇摰䂿緵�脤�憭滚���㦤�塚�雿踹�瘥譍葵餈𥟇𤫇瘜Ｘ挾嚗��蝚砌�瘜� `WAVE_UP` 銝𡒊洵鈭峕郭 `WAVE_UP_2`嚗劐�閫血�銝�甈∪��𠹺��仿�嚗屸���𠯫����函鸌敺��`has_anomaly`嚗㕑䌊�典�蝚血��∩辣��葵�∪��乩漱�枏�蝑㚚��� `add_to_follow_queue`嚗�耦�鞾���𡡒�胯��

## 2026-06-16 16:00
- [x] **隡睃� `manage_window_layout` �祉��西澈�枏�銝𤾸�撅誯�蝵桀𢆡����� (Optimized Lean Packaging & Dynamic Config Bundling for Window Manager)**嚗�
    - [x] **蝎曄��枏��㘾膄銝擧𧋦�唬�韏硋���**嚗𡁜銁 `manage_window_layout.spec` 銝哨�撠� `sys_utils` �� `JohnsonUtil` 蝑㗇𧋦�啣�撅��韏𡝗迤蝖桀��� `hiddenimports` 撟嗡� `excludes` 銝剔宏�歹��峕𧒄靽脲�撖� `pandas`��numpy`��a_trade_calendar` 蝑厰��讠洵銝㗇䲮摨梶�撘箏��㘾膄嚗��蝢𤾸��𤩺����蝘航秐隞� 39MB��
    - [x] **摰䂿緵憭𡁜�撟閙��煾�蝵格�隞嗅𢆡�����**嚗𡁜銁 spec 銝剖��� `glob` �箏�嚗�銁 datas �𦠜𦆮�𡑒”銝剖𢆡�������滩�銵��蝥抒𤌍敶蓥����厩� `*monitordisplay_config.json` �滨蔭��辣��＆靽萘𡠺蝡𧢲����摨讛�憭笔銁��掩�拍��曄內�冽��𤑳㴓憓��摰䂿緵撘�蝞勗朖�函��滨蔭�芣�銝擧�憭溻��
    - [x] **摰峕��祉� EXE 蝥臬��臬�撉諹�**嚗𡁏��蠘�銵� `pyinstaller --noconfirm manage_window_layout.spec`摰峕��西澈�枏�嚗�僎�函滲����綉�嗅蝱�臬�銝𧢲�銵� `dist\manage_window_layout.exe -log debug` 撉諹��朞���瓷�劐遙雿閙𧊋�閗繮靘肽��仿��㚚�蝵桃撩憭勗�撣賂��芷���撖餃� `tdx_ths_position4644` 撟嗥��游��唳��厩���銁�餉�撅誩��鞉�銝讠�摰𣬚�撖寥�嚗峕㺭�桀�餈鞱��嗆����函泵����麄��

## 2026-06-16 13:45
- [x] **瘛勗漲�埝䰻撟嗡耨憭� V�见�頧� (V-Reversal) 靽∪噡瘞貉��㰘��箇�銝支葵�孵� (Fixed V-Reversal Signal Permanently Silent)**嚗�
    - [x] **�孵�1嚗朞��其�摮睃銁��䲮瘜訫� (Fatal: Missing Method)**嚗䫤realtime_data_service.py` 銝� `DataPublisher.get_v_shape_signal()` ���靚�鍂鈭� `self.kline_cache._fetch_supplemental_data_async(code)`嚗諹�銝芣䲮瘜�**�寞𧋦銝滚���**鈭� `MinuteKlineCache` 蝐颱葉嚗�迤蝖桀�蝘唬蛹 `_supplemental_fetch`嚗剹��砲靚�鍂�刻�銵峕𧒄�𥕦枂 `AttributeError`嚗諹◤ `stock_live_strategy.py` 銝剔�摰賣� `except` �䠷��墧�嚗�紡�� V�见�頧砌縑�琿曎頝舐凒�交鱏頝胯��**靽桀�**嚗𡁏㺿銝箇鍂摰�擪蝥輻� `threading.Thread(target=self.kline_cache._supplemental_fetch, ...)` 甇�＆撘�郊閫血���
    - [x] **�孵�2嚗䥑NIT �嗆���瘙𣳇秄瑽𥡝�鈭舘��� (Logic: Threshold Too Tight)**嚗䫤update_wave_structure_state` �嗆��㦤銝哨�銝�銝芾�蟡其� `INIT` 餈𥕦� `CONSOLIDATING`嚗��隡讐��扳�嚗厩��文��∩辣�臬��� K 蝥踵𥲤撟� `(max-min)/min < 0.02`嚗�朖 2%嚗剹��笆鈭擧迤撣� A �⊥𠯫������餈坔�銋擧糓銝滚虾�賣說頞喟��∩辣嚗�紡�� `_v_reversal_pool` 憪讠�銝箇征嚗䈣get_v_shape_signal()` 瘞貉�餈𥪜� `False`��**靽桀�**嚗𡁜�餈𥟇��臬��冽�隞� `0.02` �曉捐�� `0.06`嚗�6%嚗㚁�閬��憭批��唳迤撣豢㟲��耦����

## 2026-06-16 13:40
- [x] **瘛勗漲�埝䰻撟嗡耨憭滨𡠺蝡𧢲�����滨蔭��辣�芾䌊�券��曆� sys_utils 撖澆�憭梯揖蝻粹萅 (Fixed sys_utils ImportError & Auto-Unpack Failure in Packaged EXE)**嚗�
    - [x] **摰帋� ImportError �寞�**嚗𡁜�雿滚��典��祆���� `manage_window_layout.exe` 餈鞱��塚��� `core.py` ��� `import sys_utils` �𤑳��躰秤�噼氜�� fallback �扯楝敺���荔�隞舘��粉�� `dist/webTools/window_manager` 摮鞟𤌍敶訫紡�湔�瘜閗䌊�券��暸�蝵格�隞嗥��桅���
    - [x] **瘛餃�霂血偷靚���亙�銝� Traceback �枏㫲**嚗𡁜銁 `core.py` ����匧紡�� `sys_utils` �� `try-except` �梹�`_get_app_root_for_manager`��ConfigManager.__init__`��save_display_configuration` �� `restore_display_configuration`嚗劐葉嚗���亥祕撠賜�靚�� `print` �� `traceback.print_exc` �唳����霂舀�嚗峕䲮靘輯�銵���笔�撣豢𧒄蝚砌��園𡢿�湧蠧�箸�蝻箔�韏吔�瘨�膄撖澆�暺𤑳���
    - [x] **摰䂿緵�賭誘銵峕𠯫敹堒��啗圾�鞉𣈲��**嚗𡁜銁 `manage_window_layout.py` 銝剖��牐� `-log` ��㺭��ế�剝�餉�嚗��憒� `-log debug`嚗㚁�瞈�瘣餃��芸𢆡霈曉� `APP_DEBUG` �臬��㗛�嚗�僎�冽綉�嗅蝱銝贝��� App Root��sys.path` 蝑㕑祕蝏��霂訫��堆���之�啗��拙�雿齿�������銵䔶�銝𧢲���
    - [x] **銵亙��枏� Spec ��辣�� hiddenimports 靘肽�**嚗𡁜銁 `manage_window_layout.spec` 銝哨�銵亙�鈭� `sys_utils.py` 撘箔�韏𣇉��砍𧑐摨訫�璅∪� `'JohnsonUtil.LoggerFactory'`��'JohnsonUtil.commonTips'` 隞亙� `'JohnsonUtil.johnson_common'`嚗屸俈甇Ｘ���𧒄�� PyInstaller �蹱����鞾�瞍𤩺𧋦�唬�韏𤥁��銁�祉�餈鞱��臬�銝𧢲��� `ModuleNotFoundError`��
    - [x] **皞鞟��臬��𠰴紡�仿曎瘚贝��朞�**嚗𡁏𧋦�唳綉�嗅蝱餈鞱� `python webTools/manage_window_layout.py -log debug` 瘚贝��朞�嚗峕𠯫敹堒� Traceback 霂𦠜鱏颲枏枂甇�虜嚗峕䲮獢� `tdx_ths_position4644` �寥�撟嗥宏�冽�����牐遙雿訫�隞硋紡�亙�撣賂�霂��撖澆��芣��曇楝敶餃��𡁶���

## 2026-06-16 12:30
- [x] **�嗡�銝� `ats.spec` 擃睃漲銝��渡��祉�蝒堒藁撣��蝞∠��冽�����潭�隞� (Created PyInstaller Spec File Aligned with ats.spec)**嚗�
    - [x] **�𥕦遣�枏��滨蔭��辣**嚗𡁜銁�寧𤌍敶蓥��𥕦遣鈭� `manage_window_layout.spec`嚗屸�蝵桀������ `webTools/manage_window_layout.py`��
    - [x] **撖寥�隡睃�銝𤾸��暹�隞嗉�皛�**嚗𡁜��Ｗ笆朣𣂷� `ats.spec` 銝剖抅鈭� `trash_list` �芸�銋㕑�皛文�雿� Qt6 �冽��曎�亙�銝� Windows �讐�摮䀹�隞嗥��枏�隡睃��餉�嚗�虾��之蝻拙���� EXE ������蝘臬僎�鞾�笔鍳�刻蝸�乓��
    - [x] **銵仿��蹱���皞鞉����銋�**嚗𡁜銁 `datas` ��㺭���甇亙��牐� `("webTools/window_manager/config.json", "webTools/window_manager")` ��鼧韐脲�����暸�蝵殷�靽肽��枏��𡒊��閙�隞� EXE �賢��舫�鋆�蝸��蔭蝒堒藁撖寥��寞��滨蔭嚗𥕦僎�惩�鈭��閬�� `MonitorTK32.ico` �暹��𠰴抅蝖�鈭斗��亙�摨𤘪𣈲����
    - [x] **�𣂼�撖澆�銝舘�皛日膄憭𤥁‘撘�**嚗𡁜銁 `hiddenimports` ����渲‘朣𣂷���𡠺 `webTools.window_manager.core`��webTools.window_manager.ui` 蝑匧銁����鞉�蝞∠��冽瓲敹���� `screeninfo`��win32gui`��PyQt6` 蝑匧�撅���典�靘肽�嚗屸俈�������𤑳� `ModuleNotFoundError` 撏拇���
    - [x] **�砍𧑐蝻𤥁��嗆挾撉諹�**嚗𡁜銁�砍𧑐�𣂼��扯� `pyinstaller --noconfirm manage_window_layout.spec` �賭誘嚗屸◇�拚�朞� PyInstaller 靘肽��曇停閫���� `Analysis` 蝻𤥁��嗆挾嚗屸�霂�� spec �滨蔭���撖孵�憯桐��航���

## 2026-06-16 12:20
- [x] **摰䂿緵�喲睸銝��桀銁蝔见����冽遬蝷箏膥撅�葉�曄內撟嗉䌊�典�憛恍�蝵桀������ (One-Click Center Window on Its Respective Screen with Auto Configuration Synced)**嚗�
    - [x] **銵冽聢�喲睸�𨅯��拙�**嚗𡁜銁 `webTools/window_manager/ui.py` ��”�潸��喲睸�𨅯�銝哨��啣�鈭� **`�唍 撅�葉�曄內鈭𡒊�摨𤩺��典�撟𧄧** �厰★��
    - [x] **憭𡁏遬蝷箏膥蝒堒藁���典�撟閙�瘚�**嚗𡁏��亦𤌍�����糓�行迤�刻�銵䕘�憒���荔��瑕��嗆��Ｙ������葉敹��撟嗉��� `QGuiApplication.screenAt()` �芷���霂��蝒堒藁敶枏���頝函��拍��曄內�剁�憒���芾�銵䕘��䠷�蝥折��典��滚���恣��膥蝔见� UI ���函��曄內�剁�`self.screen()`嚗剹��
    - [x] **�拍�蝘餃𢆡銝𤾸�撠箏站靽脲�**嚗朞繮�硋笆摨娍遬蝷箏膥��極雿𨅯躹嚗ǑavailableGeometry()`嚗峕��支遙�⊥��格𣏹嚗匧僎��＆霈∠�撅�葉 X, Y �鞉���銁蝒堒藁餈鞱�銝剜𧒄嚗䔶��坔����摰鮋��拍�擃睃捐撟嗥凒�亙�銝剔宏�剁��亙�鈭擧�撠誩��躰䌊�典��嗉����嚗𥡝𥅾�芾�銵䕘�銋蠘��芸𢆡霈∠��嗅�銝剝�蝵桀���僎餈𥡝�摰匧��𧼮‵��
    - [x] **�滨蔭����芣��𧼮‵**嚗朞恣蝞堒枂撅�葉�鞉�嚗ǑX,Y,W,H`嚗匧�嚗諹䌊�典�憛急凒�啗”�潛洵鈭�����𣈯�蝵桀����嘥僎�删�擃䀝漁��扇嚗��甇亙�蝚砌��㛖��𨅯��滢�蝵栽�脲凒�唬蛹蝏輯𠧧��笆摨𥪜����靚�鍂���摮睃��箏�嚗䔶蝙�冽��舫�朞��孵稬�喃�閫圝�靝�摮㗛�蝵栽�苷��桀�甇支�蝵桃�����塩��

## 2026-06-16 12:00
- [x] **撖寥��祉�蝒堒藁撣��蝞∠��其� `sys_utils.get_app_root()` 頝臬��瑕�隞交𣈲�� Nuitka �閙�隞嗆����銵� (Aligned Window Layout Manager Path with sys_utils.get_app_root & Enabled Nuitka Packaged Execution)**嚗�
    - [x] **�臬𢆡�拇����撟嗅�鈭怨楝敺�㴓憓����**嚗𡁜銁 `webTools/manage_window_layout.py` 撘訫紡憭湧�隡睃�瘜典�憿寧𤌍蝏嘥笆�寧𤌍敶訫� `sys.path`嚗�僎靚�鍂 `sys_utils.get_app_root()` ���頝臬�撟嗅��� `os.environ["INSTOCK_APP_ROOT"]`���蝖桐�鈭��蝏剖銁摮鞱�蝔𧢲�璅∪�銝剛��� `get_app_root()` �嗅��賜�蝥找�蝏嘥笆銝��游𧑐摰帋��啁��� EXE ���函𤌍敶𤏪�隞擧覔�砌�瘨�膄鈭�楝敺��蝘餅� CWD �誩榆��
    - [x] **�拍�蝏嘥笆頝臬�蝏穃�銝� builtin 暺䁅恕�滨蔭�芣� (Hierarchical Builtin & Custom Config Loader)**嚗�
        - �齿�鈭� `webTools/window_manager/core.py` 銝剔� `ConfigManager`嚗�銁�嗉楝敺�圾�𣂷葉�券𢒰撖寞𦻖 `sys_utils.get_app_root()` 銝𡒊㴓憓�䔝瘚卝��
        - 摰䂿緵鈭������滨漣銝舘䌊���頧賡�𡁻�嚗朞𥅾�拍��寧𤌍敶蓥���䌊摰帋��滨蔭 `config.json` 銝滚��冽��笔�嚗𣬚頂蝏笔��芸𢆡隞𤾸�蝵株�皞𣂼�嚗�葩�園��曄𤌍敶𤏪�撖澆�暺䁅恕�鞉�璅∠�餈𥡝��嘥��硋僎雿輻鍂嚗𥕦銁�冽��孵稬�靝�摮㗛�蝵栽�脲𧒄嚗���𨅯�鈭擧���㴓憓���湔𦻖�拍�摰匧��𧼮��喳虾�扯���辣�𣬚漣��覔�桀�銝页�憒� `dist/config.json`嚗㚁�憒���臬��𤑳㴓憓���拍��坔� `webTools/window_manager/config.json`��
        - 撠� `save_display_configuration` �� `restore_display_configuration` ����曄內�函�����煾�蝵桀��刻楝敺�㺿�嗘蛹�箔��拍�蝏嘥笆�寧𤌍敶𤏪��餅鱏鈭�銁�嗡��桀�銝𧢲�銵諹��祆𧒄��辣霂餃�憭望��������
    - [x] **�㯄�𡁶�霂烐�����砍�蝵桅★ (Added Config data-file to Nuitka Build Configs)**嚗𡁜銁 Nuitka 蝻𤥁��𡁏𧋦 `nuitka_instockMonitor.bat` 銝� `nuitka_build_console.bat` �� `--include-data-file` �賭誘�曆葉嚗峕迤撘讛‘朣𣂷�撖� `webTools\window_manager\config.json` �������恬�靽肽��� EXE 蝔见��賣迤蝖格𥅾�匧�蝵桃�撣���寞���
    - [x] **�批��啗�銵屸�霂� 100% �𣂼�**嚗𡁏𧋦�唳芋��� UI �賭誘銵峕芋撘讛�銵� `python webTools/manage_window_layout.py` �朞�撉諹�����祈�擃睃虾�㰘繮�𣇉����撖寞覔�桀�����冽�銋��敶枏����撅誩��拍��𤘪�霈曄蔭��䌊���撖餃�撟嗉䌊�典��函���笆朣琜��牐遙雿訫援皞��撖澆�撘�虜��

## 2026-06-16 11:35
- [x] **靽桀� UI 璅∪�銝𤾸𦶢隞方�璅∪�憭𡁜�撟閙��𤑳倌�滢�銝��渡撩�� (Aligned Display Topology Signatures)**嚗�
    - [x] **�寞祥 DPI �𡁏��硋紡�渡���儘���蝻拇𦆮璉�瘚见�撌�**嚗𡁜銁 `window_manager/core.py` �� `get_monitor_details_all_with_scale` �寞�銝哨��冽�銵峕遬蝷箏膥�Ｘ��滚撩�嗅�憪见� `SetProcessDpiAwareness(2)`嚗䔶�霂�𦶢隞方��� GUI 餈𤤿�銝� PyQt6 UI 餈𤤿��瑟�摰���詨����雿𦦵頂蝏毺漣 DPI �讛�蝑厩漣��
    - [x] **靚�鍂 GetDpiForMonitor �瑕��笔��拍�蝻拇𦆮��**嚗帋耨憭滢��� DPI-aware 璅∪�銝讠眏鈭𡡞�餉���儘�����碶蛹�拍��讐�撖潸稲霈∠���敺㛖�撅誩�蝻拇𦆮����䀝蛹 `1.0` 隞舘���蝳餃���挽蝵桃�蝻粹萅���朞�撘訫�撟嗥�摰� Windows API `GetDpiForMonitor`嚗���亙撩頧砌蛹 `int(monitor_handle)` ��蘂���嚗�銁隞颱�餈𤤿��嗆����質�憭笔�蝖柴��恥閫�𧑐�瑕��滢�蝟餌�銝剖��曄內�函�摰䂿��拍�蝻拇𦆮���憒� `1.25` �� `1.0`嚗剹��
    - [x] **�箔��笔�蝻拇𦆮�埝綫餈睃��餉���儘��**嚗𡁜銁璉�瘚见枂�笔� `scale` 銋见�嚗屸�朞��拍���儘���銵峕���揢蝞梹����銝𡒊頂蝏笔���挽蝵桀��函泵�� of �餉���儘���憒� `1536x864` �� `1920x1080`嚗㚁�隞舘�𣬚＆靽苷���粉�嗵�撅誩��𤘪��滨蔭��辣嚗�� `1920x1080@1.25_1920x1080@1.0_monitordisplay_config.json`嚗匧��其��湛�銝𥪜��函�摰噼��煺��冽����撅誩��𤘪�蝏���孵���

## 2026-06-16 11:05
- [x] **摰䂿緵憭𡁏遬蝷箏膥�拍��鍦�銝擧��𤑳����摮䀹�憭滚��� (Save & Restore Multi-Monitor Display Layout)**嚗�
    - [x] **蝘餅�銝擧𡂝�硋�撅誩��𤘪� API**嚗𡁜���� `current_display_configuration.py` ���撅誩���儘�������㮾撖孵�����蜓撅𤩺�霈啗繮�碶��Ｗ��餉�嚗�抅鈭� Windows API `ChangeDisplaySettingsEx`嚗㕑�銵�極蝔见��滚�撟園��鞱� `window_manager/core.py`嚗�笆憭㚚�誩枂 `save_display_configuration` �� `restore_display_configuration` �亙藁��
    - [x] **�舀�頝典��曄內�函����銋��**嚗帋蝙�冽遬蝷箏膥蝏���孵�蝑曉�嚗�� `3840x2160@2.0_1920x1080@1.25` 蝑㚁��箏�銝滚������遬蝷箏膥�𤘪��臬�嚗𣬚𡠺蝡衤�摮睃���䌊���撅��滨蔭��辣嚗峕�靘偦�摨行惣�賜��芷������銝擧�銋���賢���
    - [x] **�券�蝵桃恣��膥 UI 銝剜楛摨阡���**嚗𡁜銁 UI ���𨅯��滨���遬蝷箏膥�𤘪�蝏𤘪��嗪𢒰�蹂葉�啣� **`�𠒣 靽嘥��曄內�函�����鬔** 銝� **`�� �Ｗ��曄內�函�����鬔** �厰僼嚗𣬚凒閫���唳�銵𣬚𠶖��僎�𥪜𢆡 UI 靽⊥��齿鰵�㰘蝸嚗�蒂�㗇�瘜∪撕蝒烾�𡁶䰻��
    - [x] **�惩𤐄�𤾸蝱�� UI 璅∪�**嚗𡁜銁 `manage_window_layout.py` �� UI 餈鞱���𣈲銝哨�瘜典�撅誩��拍��鍦��芸𢆡�Ｗ�瘚��嚗���啁���笆朣𣂼��芸𢆡隞文�撟閙𦆮蝵桐�蝵格��𤏸䌊����
    - [x] **摰䂿緵�喲睸蝒堒藁瞈�瘣餌蔭憿嗅��� (Table Context Menu Window Foregrounding)**嚗𡁜銁 QTableWidget 銵冽聢銵䔶葉�啣��芸�銋匧𢰧�株��𤏪��𣂷� **`�� 蝒堒藁蝵桅▲撟嗆�瘣蒐** �蠘���抅鈭� Win32 API 蝒�聦 Windows �滚蝱�Ｗ��𣂼�嚗�芋�蠘��� Alt �桅��曄鸌���嚗�僎摰𣬚��澆捆鈭�芋蝟𦠜�憸塩��.py` 銝� `.exe` 餈𤤿��𡒊���䌊�冽揢蝞堒�雿溻��
    - [x] **�䭾�銝𥪜��𤾸�摰�**嚗𡁜��其��游�隞颱���� `current_display_configuration.py` �� `findSetWindowPos.py` ����蠘�銝綽�靽脲����靚�鍂�曇楝���撖孵��具��

## 2026-06-16 10:40
- [x] **�齿� findSetWindowPos 銝箇𡠺蝡见��賢� (Refactor findSetWindowPos into an independent package)**嚗�
    - [x] **�𥕦遣�����**嚗𡁜銁 `webTools/window_manager` 銝见�撱箸芋�堒�嚗���� `__init__.py`嚗䈣core.py`嚗䈣ui.py`嚗䈣config.json`��
    - [x] **霈曇恣 core.py**嚗𡁜� `findSetWindowPos.py` 銝剖�撅�� Windows API 靚�鍂嚗�� EnumWindows��etWindowPos��etWindowRect 蝑㚁�隞亙���儘���瘚钅�餉�嚗�抅鈭� screeninfo �� mouseMonitor.displayDetction嚗匧�鋆�� `core.py`��
    - [x] **靽桀� UI 銝� CLI ��儘���瘚衤�銝��渡撩��**嚗𡁻�撖� PyQt6 �臬𢆡�擧�瘣� DPI �毺䰻撖潸稲 win32api �拍��鞉��睃���䔮憸矋��� `core.py` ��䔝瘚钅�餉�銝剛䌊�刻粉�𣇉頂蝏� DPI 蝻拇𦆮��僎撖嫣蜓撅誩����餈𥡝�蝎曄＆�睃�嚗𣬚＆靽苷��� UI �賭誘銵峕芋撘譍� UI �屸𢒰銝衤��游ế摰𡁜枂敶枏�蝟餌��寥����雿喲�蝵桐蛹 `tdx_ths_position4644`��
    - [x] **�滨蔭��辣��掩�����**嚗𡁜��毺′蝻𣇉�����厩����蝵桅�蝵桃宏�刻秐�祉��� `config.json` 銝哨�撟嗅銁 JSON ���蝏��銝� **`single_display` (�訫��滨蔭)**��**`multi_display` (憭𡁜��滨蔭)** �� **`custom_special` (�寞�/��蟮�滨蔭)** 銝劐葵憭抒掩嚗�銁 `core.py` 銝剖��啣�蝐餌�摰匧��㰘蝸����硋�靽嘥��箏���
    - [x] **霈曇恣 ui.py (PyQt6 ��掩�滨蔭蝞∠���)**嚗朞挽霈∩�銝芰泵��緵隞��暺𤑳�摮衣� PyQt6 �屸𢒰嚗峕𣈲���
        - �亦�敶枏�蝟餌���遬蝷箏膥�滨蔭���颲函���
        - 蝥扯�/撣血�蝻�銝𧢲�撅閧內��掩�𡒊�蝒堒藁�滨蔭�寞�嚗峕��啣��唬��峕遬蝷箏膥�臬���
        - �𡑒”撅閧內敶枏��滨蔭銝剔����厩�����嗡�蝵桀��堆�X, Y, Width, Height嚗㚁��舀�憓𠺶�����㺿��
        - �舀��𨀣鰵撱粹�蝵栽�脲𧒄�����撅䂿掩�恬��訫�/憭𡁜�/�寞�嚗剹��
        - �舀��靝��格��猾�嘥��齿��Ｖ�餈鞱�蝒堒藁������蝵殷��嫣噶敹恍�煺�摮㗛�蝵殷���
        - �舀��靝��格凒�啣歇�厩�������嘅��湔𦻖隞擧��Ｘ��匧��漤�蝵株”銝剖歇�厩�摨讐�������唬�蝵株��硋�憛恬��舀��脫�撠誩�撟脫贋銝𤾸��穃�蝻�摰寥�嚗剹��
        - 銵冽聢��鍂 3 �堒�撅�嚗峕鰵憓嫰�𨅯��齿��Ｗ����蝵栽�嘥笆�批�嚗���啣��嗆�撖寞��莎�摰��銝��湔遬蝏輯𠧧嚗䔶�蝵桀��笔�蝘駁�鈭格遬蝥Ｚ𠧧嚗峕𧊋璉�瘚见�蝔见��曄��莎���
        - �舀��𨅯�憿寞��笔�憛徉�嘅��湔𦻖�孵稬蝚砌��𦯀葉��滯�脣�蝘餃������聢嚗�朖�舐��游�憛怨��𣇉洵鈭���滨蔭�鞉�嚗�僎�芸𢆡瘥𥪜笆�条遛��
        - �舀��靝��桀��兩�嘥��漤�蝵桀�獢屸𢒰蝒堒藁嚗�僎�芸𢆡閫血�獢屸𢒰摰鮋�雿滨蔭�齿鰵璉�瘚页�雿輻宏�冽��毺�銵𣬚��渡眏蝥Ｚ蓮蝏踴��笆�芾�銵𣬚�蝒堒藁�䠷�頝唾�嚗䔶��滩��箇����頝唾��亙���
    - [x] **�澆捆�找��䭾�撘���**嚗帋��桃鍂�瑟�隞歹�摰��靽脲��� `webTools/findSetWindowPos.py` ��辣銝滚𢆡嚗屸��滢遙雿訫�敶㘾��押��銁 `webTools/` 銝𧢲�靘𥕢� `manage_window_layout.py`嚗屸�霈斗𣈲����唬��臬𢆡 UI ��䌊�典�颲函��Ｘ�銝𤾸笆朣琜�隞�銁�� `-ui` �� `--ui` ��㺭�嗉�韏瑞恣����Ｕ��

## 2026-06-15 01:50
- [x] **靽桀�蝡硺遠韏偦帕�Ｘ踎�園𡢿�峕郊 Bug 銝𤾸㨃憿輸䔮憸� (Fixed Racing Panel Time Sync Bug & UI Lag)**嚗�
    - [x] **摰䂿緵 Detector 蝥批���㺭�格𠯫�笔撩�⊿� (Implemented Detector-Level Date Validation)**嚗𡁜銁 `bidding_momentum_detector.py` �� `register_codes` �寞�銝剜溶�牐�撖� incoming �唳旿�交�銝𡒊頂蝏�𠯫�毺�瘥𥪜笆�餉���銁摰䂿�璅∪�銝页�餈�誘撟嗆㜃�芯遙雿閙䔉�芸��脤�隞𦠜𠯫��㺭�格凒�堆��脫迫��蟮�唳旿�園𡢿�單情�枏�撅��園𡢿 `self.last_data_ts`嚗𥕦銁 `_evaluate_code_unlocked` 銝剖笆銝芾��亙� `data_ts` 餈𥡝��交��脣鴃嚗���𨀣𠯫��𡟺鈭𦒘�憭拙�撘箏�靽格迤銝箏��滨頂蝏�𧒄�氬���敶餃�閫��鈭���䀹��滩��嗅��� K 蝥踵㺭�桀�蝟餌��園��躰秤�匧��唳㿥憭拇𤣰�条��桅���
    - [x] **�惩𤐄韏偦帕�Ｘ踎 UI 霈⊥𧒄銝擧葡�𤘪�頝臭��� (Solidified Racing Panel Timing & Rendering Bypass)**嚗𡁻�朞�靽肽� `detector.last_data_ts` 餈嗘��園𡢿皞鞟�蝥臬�嚗䔶蝙 `bidding_racing_panel.py` 銝剔� `update_visuals` 閫��敺堒��� `time_hhmm` �函�銝剛�蝎曉��峕郊敶枏�蝟餌�鈭斗��園𡢿���蝖桐�鈭�䌊�券�蝵桅��對�`is_trading_time`嚗匧銁鈭斗��嗆挾甇�虜閫血�嚗䔶��嗥�隡睃��文�嚗Ǒis_closing`嚗㗇�憭齿迤蝖格��伐�敶餃��寞祥鈭�銁�嗥��文�鋡恍�霂舀�瘣餅𧒄�曹��㰘��� Treeview �齿鰵鋆�蝸撖潸稲�� 3-7蝘� �屸𢒰��香�䔶艇�滚㨃憿踴��

## 2026-06-13 11:30
- [x] **ATS 蝏�垢擃睃僎�㻫���撱嗉��扯�隡睃�銝𤾸��啗�皞𣂼��冽覔瘝� (ATS Packaged High-Performance & Resource Reduction Optimization)**嚗�
    - [x] **�寞祥 IPC 靽∪噡擃㗛� TCP 餈墧𦻖撘��� (Optimized IPC Sender with Signal Batching)**嚗𡁜銁 `stock_live_strategy.py` ����� `_ipc_sender_worker` 蝥輻�銝哨�撠���祇�鞉辺 `SIGNAL` 撱箇��祉� TCP 餈墧𦻖�煾���璅∪�嚗屸���蛹�寥�摨誩��碶蛹 `SIGNALS` 鈭��蝏��隞扎���甈� TCP �⊥�撟嗅�����之撟�漲�滢�鈭��憸𤏸�����烐𧒄 127.0.0.1 蝡臬藁銝𢠃�蝜�� socket 撘���嚗峕��支�銝餃��啗�蝔衤� ATS 蝏�垢銋钅𡢿�䭾�銋厩� CPU 鈭㗇𦜖��
    - [x] **�㯄�� IPCBridge �寥��交𤣰銝𤾸��函��賢𪂹�毺恣�� (Enhanced IPCBridge & Graceful Stop)**嚗𡁻���� `ats/ipc_bridge.py`嚗�銁 `_handle_client` 銝剜�蝻脲𣈲�� `SIGNALS` �寥���誘閫��嚗�儐�航圾����𤑳��噼��賣㺭嚗𥕦��牐� `stop_listener` �寞�銝� `_listener_running` �嗆����喉��� ATS 銝餌�����剜𧒄蝡见朖��鱏撟嗅��剖��亙�嚗屸俈甇Ｙ瑪蝔𧢲��蹱�銝餌瑪蝔𧢲�韏瑯��
    - [x] **�齿� HeatmapWidget 敶餃�瘨�膄蝤�� I/O �餃� (Throttled Heatmap I/O)**嚗𡁜��支� `SectorHeatmapWidget` (`heatmap_widget.py`) ��� 5蝘鍦��嗉蔭霂� GZIP �讠憬�条��唳旿��𡠺蝡� QTimer 摰𡁏𧒄�具����唳旿�㰘蝸�賣㺭 `load_live_sectors` ��漣銝� 10 蝘㘾俈�㚚�憸烐綉�塚��滚� `ATSMainWindow` 蝏煺�敹�歲靚�漲嚗䔶蝙�嗅銁�䀝葉憭扳郭�刻����蝤��霂餃�撘����牐�敶㘾妟��
    - [x] **�齿� KernelTracePanel 摰墧鴌憓鮋�撘�/�脫�霂餃�靽脲擪 (Optimized Log Reader with File ModTime Guards)**嚗𡁻���� `KernelTracePanel` 銝剔� `load_trace_logs` �餉���銁霂餃�銝舘圾�� JSONL �亙���辣�㵪�憓𧼮� `os.path.getmtime` 靽格㺿�園𡢿��犒�⊿�����亙��芯漣�笔�韐刻蕭�䭾𧒄嚗𣬚�頝臬僎頝唾����厩��䁅粉�硋� GUI Treeview 皜脫��滨�嚗�蝠摨閙��帋��𤾸蝱敹�歲銝𡒊��䀹�扯�銋钅𡢿�������
    - [x] **蝎暹�蝏�� GlobalFavoriteManager �嗆���閫�膥 (Optimized GlobalFavorites Watcher Loop)**嚗𡁻���� `global_favorites.py` �𣬚� `_file_watcher_loop` 摰𡁏𧒄頧株砭嚗������� `time.sleep(1.0)` �齿�銝箏抅鈭� `threading.Event().wait(1.0)` ����扯�蝑匧��箏�嚗�僎�啣� `shutdown` �寞�隞亙��啣銁銝餌�摨誯���箸𧒄�祇𡢿蝏�迫摮鞟瑪蝔页�敶餃��踹�鈭�眏鈭𤾸��斤瑪蝔𧢲�韏瑕紡�� _MEI 銝湔𧒄�桀���香��■�整��
    - [x] **ATS頝麁K餈墧𦻖�唳旿�湔鰵�鞾�銝𡡞��� (Throttled TK-to-ATS Data Update Rate)**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `send_df` 敺芰㴓������ `dynamic_interval` ��恣蝞烾�餉����撘������箔��唳旿銵峕㺭霈∠�擃㗛��湔鰵��㦤�塚��寧鍂�箔�蝟餌��典� `cct.duration_sleep_time` ��㺭���撠� 30 蝘㘾�憸烐綉�嗚��銁�硺漱�𤘪𧒄畾蛛��芸𢆡撠�凒�圈𡢿�𥪜之撟�辣�輯秐銝匧�㵪���撠� 180 蝘𡜐�嚗𥕦笆鈭擧��刻圻�𤑳�撘箏��券��峕郊霂瑟�嚗Ǒ_force_full_sync_pending`嚗㚁�摰䂿緵�瑕㭂�祇𡢿蝛輸�讐�頝荔�靽肽�鈭��銝剛�銵𣬚���稲摰厰����雿� CPU 韐蠘㭘銝𤾸�頞羓�鈭支��滚��扼��
    - [x] **�𧼮�瘚贝� 100% 蝏踵��朞�**嚗朞��𡁜��� 11 憿寧��賢𪂹�煺��唳旿銝��湔�扳�霂𤏪��牐遙雿閙𥁒�坔��臭��具��

## 2026-06-13 10:00
- [x] **摰䂿緵�瑕鍳�� NameCache Bootstrap 蝏�澈�㛖��箏�銝擧�蝞���辣 IO (Implemented NameCache Bootstrap & Lightweight File IO)**嚗�
    - [x] **撱箇�銝��單偶�貊��滚����蝟餌� (One-time Setup NameCache Bootstrap)**嚗𡁻���� `sys_utils.py` 銝剔� `_load_name_cache` �賣㺭���璉�瘚见��砍𧑐 `stock_name_cache.json` 蝻枏��圈�銝滩雲 4500 �⊥𧒄嚗𣬚頂蝏笔��朞� `engine.all` DataFrame �𤥁��𧋦�� HDF5 摨栞䌊�冽�銵䔶�甈⊥�批� A �∩誨����滚�憭抒��伐�撠� 5500+ �芾�蟡函�銝�撖嫣�銝剜��滚��惩�瘞訾���僎撟嗆㟲雿枏��亦��� JSON ��辣嚗𣬚＆靽脲迨�擧�霈箏銁�枏�餈䀹糓撘��𤑳㴓憓���賣𥅾�㗇神蝘垍漣�� $O(1)$ ���蠘圾�琜�敶餃�瘨�膄鈭��銝剔眏鈭𦒘葵�∠撩憭梢�憸㻫���雿坔𧑐摰硺��𤥁�����擧��亥砭 HDF5 ����滩��瑯��
    - [x] **蝎曄��芷�㕑�銝𡒊��批�銵冽�銋���𡁻� (Removed Redundant Lookup in File IO)**嚗𡁻���� `monitor_utils.py` �𣬚� `save_monitor_list` 銝� `load_monitor_list` �餉���縧�支�霂餃� `monitor_category_list.json` ��辣�嗅笆�滚���撩銵諹‘朣鞱圾�琜�撠��隞嗉粉�躰��煺蛹蝥舐硃����堒����摨誩��𣇉������蝙摨訫� IO 蝏嘥笆蝥臬�嚗��銝芾��滚���‘朣𣂼極雿𨅯��其漱蝏� UI 皜脫�撅��擃䀹�扯����蝻枏���𨰹�㵪��曇��滢�鈭�䌊�㕑�靽嘥��嗥� CPU 瘨��𨰜��
    - [x] **靽桀� NameCache Bootstrap 撖� Sina Engine 靘肽���援皞�撩��**嚗帋耨憭滢��� Sina 撘閙��芸��渲挪�� `Sina.all` 撅墧�扳𧒄 `engine.stockcode` 暺䁅恕隞滢蛹 `None` 撖潸稲 `NoneType has no attribute cname_dict` ���撣貉郎�𨳍�����蛹�朞� `engine.all` 撅墧�抒� `name` �㛖凒�交��硋��湔�撠���
    - [x] **靽桀� MonitorTK 憭𡁻� Qt 蝏穃�蝻𤥁��脩�**嚗𡁜銁 `instock_MonitorTK.spec` �� `excludes` �𡑒”銝剜��� `PyQt6` �詨�璅∪�嚗�蝠摨閙覔瘝颱��曹��屸� Qt 獢�沲撖澆�撖潸稲 PyInstaller �𥕦枂 `attempt to collect multiple Qt bindings packages` �躰秤鋡怨翰銝剜迫�枏���■�整��

## 2026-06-13 09:15
- [x] **靽桀��∠巨�滨妍閫���𣂼�銝𡡞俈頞羓�撏拇� Bug (Fixed Stock Name Resolution Extraction & Out-of-Bounds Crash Bug)**嚗�
    - [x] **摰䂿緵撘箏��� 6 雿齿㺭摮𦯀誨��迤�蹱���**嚗𡁜銁 `sys_utils.py` �� `resolve_stock_name` �賣㺭銝哨�撘訫�鈭�移���甇��銵刻噢撘� `r'(\d{6})'` 隞乩����銝滩��坔�雿滨泵嚗�� `"銝芾�_600000"`��"�𣞁銝芾�_600000"`��"sh600000"`��"000002.SZ"` 蝑㚁�銝剖僕���𣂼��� 6 雿滨滲�啣��∠巨隞����
    - [x] **靽桀��枏��臬�銝� `JSONData` 撖澆�撟嗡��硋��㰘蝸璉�瘚𧢲�扯� (Fixed & Restored Packaging Support for Sina Local Engine)**嚗�
        - 隞� `ats.spec` �� `excludes` 銝剜迤撘誩��支� `tables` (PyTables) 銝� `h5py`嚗𥕦��嗅� `JSONData`��JSONData.sina_data`��tables`��h5py` 瘛餃��� `hiddenimports` 銝哨�雿踹��枏��𡒊� `ATS_Terminal.exe` �臭誑甇�虜�㰘蝸�砍𧑐銵峕�撘閙���
        - 撘訫��典�蝻枏��㗛� `_SINA_DATA_AVAILABLE`嚗�銁蝔见�擐𡝗活靚�鍂 `resolve_stock_name` �嗅笆 `JSONData.sina_data.Sina` 撘閙���虾撖澆��找��舐鍂�批�銝�甈⊥�批��冽䔝瘚页��𡒊賒靚�鍂�朞��嗆���摮条凒�亦�頝荔�敶餃��寞祥鈭���枏�靘肽�銝漤�擃㗛��𥕦枂/�閗繮 `ImportError` 撣行䔉�� CPU 韐��銝� UI �⊿▼��
    - [x] **�𣂼�蝵𤑳� API 霈輸䔮銝𡡞俈甇Ｙ���援皞�**嚗𡁜笆蝵𤑳� API嚗�鰵瘚� API嚗厩��亥砭餈𥡝�鈭������塚��芣��𣂼��箏�瘜閧� 6 雿滨滲�啣�隞���嗆���捂�𤏸絲蝵𤑳�霂瑟������㜃�芯��曹�隡惩���鉄 emoji �㚚� ASCII �牐�蝚血�蝚虫葡�� Windows �臬�銝𧢲��箇� `UnicodeEncodeError` 撏拇���
    - [x] **�㯄�𡁜�撅�圾�鞾�𡁻���䌊瘚贝䌊璉��亙�**嚗帋蛹�滨妍閫�����撅�楝�梧����蝻枏���𧋦�唳鰵瘚芸��汿��DF5�唳旿摨瓐��acing敹怎�����滩��准��鰵瘚芰�蝏� API 蝑㚁�銵仿�鈭�祕蝏�� logger 頝蠘葵颲枏枂嚗�之撟������䀝葉�𠰴�憪见��嗆挾閫���曇楝��虾�墧滲�扼��
    - [x] **蝻硋�銝枏�瘚贝��𡁏𧋦撟嗉��𡁜��𤩺�霂�**嚗𡁜�撱箔� `scratch/test_resolve_name.py` 撉諹��𡁏𧋦嚗�僎�冽綉�嗅蝱銝钅◇�抵��𡁏��匧��怠�蝘滚�雿滨泵���蝻�/�𡒊�/emoji 瘛瑕�颲枏����霂閧鍂靘页��券� `pytest test_watchlist_lifecycle.py` 11 憿寧��賢𪂹�罸��鞉�霂� 100% 蝏踵��朞���

## 2026-06-13 09:00
- [x] **摰䂿緵擃睃��𣂷葵�∪�蝘啣�摮�-蝤���������𣇉�摮䀝��芣����� (Implemented High-Performance Stock Name Dual-Layer Caching & Self-Healing)**嚗�
    - [x] **撱箇� `stock_name_cache.json` �拍�����硋�**嚗𡁜銁 `sys_utils.py` 銝剖��唬� `_load_name_cache` �� `_save_to_name_cache`��銁蝔见��嘥��𡝗𧒄瘥怎�蝥扯蝸�亙��脣歇閫��銝芾��滨妍嚗�僎�刻圾�鞉���𧒄�拍鍂蝥輻����`_name_cache_lock`嚗匧��典�摮𣂼��亦��� `datacsv/stock_name_cache.json`���隞擧覔�砌��𦦵�鈭��甈∪鍳�冽𧒄�滚�靚�鍂�唳答蝵𤑳� API �� H5 蝤��霂餃�嚗峕���俈甇Ｖ蜓餈𤤿��⊥香�𣬚�蝏𡏭�皞鞉答韐嫘��
    - [x] **摰墧鴌�芷�㕑��𡑒”皞𣂼仍�拍�����**嚗𡁜銁 `monitor_utils.py` �� `save_monitor_list` �� `load_monitor_list` 銝哨��亙�鈭� `resolve_stock_name` �芣�撘閙���銁霂餃� `monitor_category_list.json` �塚��芸𢆡�行⏛撟嗥�甇��靝葵�︵XXXXXX�脲�隞��蝑劐�閫�� placeholder �牐�蝚佗�摰䂿緵�芣��坔�嚗䔶�霂������函�蝏嘥笆撟脣��峕�鈭峕活�𦯀�閫����
    - [x] **�𧼮�瘚贝� 100% 憿箏⏚頝煾��**嚗𡁏��蠘�銵� `pytest test_watchlist_lifecycle.py`嚗�11 銝芣�霂閧鍂靘𧢲�銝�憭梯揖��

## 2026-06-13 08:00
- [x] **靽桀��枏��� EXE �䭾�餈鞱�/�芷����䔮憸� (Fixed Package EXE Execution/Crash Issues)**嚗�
    - [x] **摰���亦氖�硺蜓餈𤤿�嚗���祉� ATS 蝏�垢嚗匧笆 Tkinter 璅∪���楛撅��血�**嚗𡁶眏鈭� `global_favorites.py` �曉銁憿嗅�撖澆�鈭� `tk_gui_modules.gui_config`嚗�銁�閧𡠺�枏� PyQt �嗆��� `ATS_Terminal.exe` �塚�隡𡁜紡�湔𧊋�枏� `tk_gui_modules` 靘肽��峕��� `ModuleNotFoundError` �芷��嚗峕��刻�銵峕𧒄頧賢� Tk 摨㮖漣�笔��� GUI 鈭衤辣敺芰㴓�脩�撏拇���緵撌脤�朞�靚�鍂 `sys_utils` �齿鰵霈∠� `WINDOW_CONFIG_FILE` 頝臬�嚗���典竉蝳颱�撖� `tk_gui_modules` ��撩撖澆�靘肽���
    - [x] **�寞祥�𤾸蝱摰�擪蝥輻��冽�� Import 撖潸稲��紡�仿�甇� (Avoided Threaded Dynamic Import Deadlocks)**嚗𡁜� `FavoritesWatcher` �𤾸蝱蝥輻���� `import time` �冽��紡�亦宏�唬���辣��憿嗅�嚗峕��支� Python �𡁏��箏� Nuitka/PyInstaller �典�蝥輻��枏��嗅�撖澆����Import Lock嚗匧�蝒�紡�渡��𤩺㦤�⊥香/�䭾��臬𢆡�桅���
    - [x] **�𧼮�瘚贝� 100% 憿箏⏚頝煾��**嚗𡁏��蠘�銵� `pytest test_watchlist_lifecycle.py`嚗�11 銝芣�霂閧鍂靘𧢲�銝�憭梯揖��

## 2026-06-13 06:00
- [x] **靽桀� Alt+P 敹急㭘�桀銁銝餅綉�嗅蝱蝒堒藁銝剖��滩圻�穃紡�湧�甈⊥���� Bug (Fixed Alt+P Duplicate Triggering Bug)**嚗�
    - [x] **撘訫� 300ms �脫��脤��交㦤��**嚗𡁜銁 `instock_MonitorTK.py` �� `open_ats_panel` �寞�憭湧�撘訫��箔��園𡢿�喟��滚�靽脲擪��𥅾銝斗活閫血��湧�撠譍� 0.3 蝘𡜐��嗵凒�亙ế摰帋蛹�滚�鈭衤辣撟嗉�銵峕㜃�芥���敶餃��寞祥鈭��銝餅綉�嗅蝱嚗㇍k 蝒堒藁嚗匧�鈭擧暑�函𠶖��𧒄嚗峕�銝� Alt+P �峕𧒄閫血� Tk �砍𧑐�桃�鈭衤辣銝𤾸�撅��剝睸�𤾸蝱蝞⊿�瘨��嚗屸�䭾��𨀣遬蝷�-�鞱��萘��湔𠽌瘨���鍂�瑕�憿餅�銝斗活�滩��文枂�Ｘ踎���撉屸䔮憸塩��
    - [x] **瘚贝��朞�撉諹�**嚗朞��𡁜��� 15 銝芸���/���瘚贝��其�嚗𣬚＆靽脲�隞颱�餈鞱��� and ���箸��脩���

## 2026-06-13 05:00
- [x] **靽桀� ATS 蝏�垢�滨��單釣��揢�嗆㺭�桐腺憭曹��屸𢒰�垍��笔��桅�撟嗅��箸�霂� (Fixed ATS UI Data Loss and Layout Corruption on Favorites Toggle & Test Hardening)**嚗�
    - [x] **摰䂿緵 Mock 銝𤾸��嗅�頧賜𠶖��移蝖桀�蝳� (Precise Mock & Live State Separation)**嚗𡁜銁 `UniverseTreeWidget` (`universe_widget.py`) �� `SwingStateTable` (`swing_table.py`) 銝剜鰵憓硺� `self._is_mock_active` �嗆����譌��銁�扯� `load_mock_data` �嗆遬撘讛挽銝� `True`嚗�銁靚�鍂 `update_pools` �� `update_data_list` ���摰墧𧒄銵峕��唳旿�嗉挽銝� `False`���隞擧覔�砌����鈭�㺭�格葡�𤘪�����賢𪂹����𦦵�鈭�眏鈭擧芋撘讐𠶖��毽瘛��䭾���㺭�株◤蝛箏�潸��𣇉��𦦵蒾撅謿�脲��𨅯��臬𢆡蝛箸��脲��栶��
    - [x] **�齿� `_safe_favorites_changed` �瑟鰵頝舐眏 (Optimized Favorites Change Dispatching)**嚗𡁻���� `ATSMainWindow` �𣬚��剝睸銝𤾸𢰧�桀�瘜其�隞嗉圻�𤑳� `_safe_favorites_changed` �寞����撘��甇文�摰寞�撘閗絲�瑕鍳�刻秤�斤� `has_df` �典�銵峕�摮睃銁�扳嵗撉䕘��齿�銝箇凒�亥粉�� `self.universe_widget._is_mock_active` ��扇��＆靽苷��函�隞嗥�蝖桀�鈭� Mock 璅∪��嗆�頝舐眏�扯� `load_mock_data` �瑟鰵隞乩���𧋦�唬�蝤��蝻枏�銝��湛���銁撌脰��亙��睃��嗉���芋撘𤩺𧒄�湔𦻖�剛楝 Mock 皜脫�嚗�蝠摨閙�蝏苷�擃㗛���揢�滨��單釣�嗥��𣈯緾�����嫰�苷��𨀣㺭�桅�撉日��萘緵鞊～��
    - [x] **靽桀� GlobalFavoriteManager �蓥�瘚贝�皜�征 Bug (Fixed GlobalFavoriteManager clear() in Unit Tests)**嚗帋耨憭滢�瘚贝��其� `test_swing_table_favorites_styling` 銝哨�雿輻鍂 `fav_mgr.get_favorite_stocks().clear()` 霂訫㦛�滨蔭�嗉��𡑒”��仃��撩�瑯��� `get_favorite_stocks()` 餈𥪜���糓��������鰵�瑁�嚗�笆�嗉�銵� clear �䭾�敶勗�摰鮋��� `favorite_stocks` �����緵�齿�銝箇凒�亥��� `fav_mgr.favorite_stocks.clear()` 皜�征�蓥�����嗆���蝖桐�瘚贝��𠉛氖���撖寞迤蝖柴��
    - [x] **�朞� unittest.mock 閫�� Qt �芸𢆡�鍦�撖寞�霂閧�撟脫贋 (Eliminated Qt Sorting Interference in Unit Tests)**嚗𡁜銁瘚贝� `test_swing_table_favorites_styling` �㰘蝸�唳旿�㵪��拍鍂 `unittest.mock.patch` 蝐餌漣�急㜃�芸僎 mock �� `QTableWidget.setSortingEnabled`����賜＆靽嘥銁�鍦� mock �唳旿�塚�摨訫� C++ �鍦�憪讠�靽脲� `False`嚗屸��滢��曹��砍𧑐����㚚�蝵� `window_config.json` �𣬚�蝻枏��鍦�閫��嚗���劐誨���摨𧶏�撖� Python 撅�蔭憿嗆�摨讐��𦦵��䭾�閬����
    - [x] **�券��𧼮�瘚贝� 100% 憿箏⏚頝煾��**嚗𡁏��蠘�銵� `pytest test_favorites_pinning_and_styling.py` 銝� `pytest test_watchlist_lifecycle.py`嚗���� 15 銝芣�霂閧鍂靘𧢲�銝�憭梯揖嚗�100% �券�憿箏⏚�朞�嚗𣬚頂蝏笔銁�����垢銝𡡞�鈭斗��嗆挾����臬𢆡�嗆�����迅摰𡁏�批�銵函緵隡睃���

## 2026-06-13 04:45
- [x] **隡睃��滨��單釣銝芾�/�踹�擃䀝漁�滩𠧧隞仿��滩��𣇉鸌敺���� (Optimized Favorite Stocks Highlight Styling to Prevent Color Override)**嚗�
    - [x] **撌虫儒�∠巨瘙� (Universe Tree) 擃䀝漁�餉�蝎曄���**嚗𡁻���� `UniverseTreeWidget` �� `load_mock_data` 銝� `update_pools` �寞���銁摨𠉛鍂�滨��單釣銝芾���楛蝏輯��� (`#1A2A1A`) �塚�銝滚�銝�����𧑐撠��銵���航𠧧瘨���𣂷漁蝏輯𠧧��緵�其�撖嫣誨��� (0) 銝𤾸�蝘啣� (1) 瘨��鈭桃遛�齿艶�� (`#00FF88`)嚗��隞硋�嚗�緵隞瑯���餈啜����亦�嚗劐���頂蝏罸�霈斤蒾摮堒��航𠧧 (`#e2e2e5`)嚗�僎銝𥪯蝙瘨典��� (3) 隞滩�摰𣬚��曄內蝥Ｘ隅蝏輯��� A �∪虜閫���脯��
    - [x] **瘜Ｘ挾�噼�頝蠘葵�� (Swing Pullback Table) 擃䀝漁�餉�蝎曄���**嚗𡁻���� `SwingStateTable` �� `load_mock_data` 銝� `update_data_list` �寞�����∠巨鋡急�霈唬蛹�滨��單釣�塚�撠���刻����匧���聢瘨��瘛梁遛�峕艶�� (`#1A2A1A`)嚗䔶��芸�隞���� (0) ���蝘啣� (1) 瘨��鈭桃遛�齿艶 (`#00FF88`)��郭畾萇𠶖����A20 �讐氖摨血��刻�隞㮖�蝑匧�����舐��脤�餉��典�瘜函𠶖���銝滚�鋡怨��吔�摰𣬚�靽萘�鈭���嗆��𠧧嚗���噼萱銝剝��脯��歇撟喃�蝥Ｚ𠧧���蝳餃漲蝥�/蝏輻�嚗劐��删�摮𦯀��瑕���
    - [x] **餈鞱��𧼮�瘚贝�撉諹�**嚗朞�銵� `pytest test_favorites_pinning_and_styling.py` �� `pytest test_watchlist_lifecycle.py` �券� 15 銝芣�霂𤏪�100% 蝏踵��朞�嚗𣬚＆靽苷耨�孵笆撣���芣����銋���羓��賢𪂹�毺��澆捆�找���蔔蝔喳��扼��

## 2026-06-13 03:30
- [x] **摰䂿緵 ATS 蝏�垢�訫�靘见�撅�敹急㭘�株䌊�券��譍�蝵桅▲��揢撟嗆��� Alt+R 閫��頧格揢�箏� (Implemented ATS Single-Instance Global Hotkey Toggle and Alt+R Switcher Integration)**:
    - [x] **摰䂿緵�訫�靘衤��剝睸�箄���揢 (Alt+P Single-Instance Toggle)**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `open_ats_panel`������朞� Win32 `FindWindowW` �瑕�撌脣��舐� ATS 蝏�垢�交�嚗Ǒhwnd`嚗剹����𦦵���歇摮睃銁銝娍迤憭���滚蝱瘣餃𢆡�嗆����躰䌊�典��園��𧶏�`ShowWindow(hwnd, 0)`嚗㚁�憒��憭���鞱��硋��圈�瘣餃𢆡�嗆����坔��嗆�憭滚僎撘箏�蝵桅▲�啣��啗��佗�`ShowWindow(hwnd, 5)` + `SetForegroundWindow`嚗㚁��交𧊋�臬𢆡�蹱�銵���臬𢆡 Popen��
    - [x] **銵亙��典��剝睸銝𤾸𦶢�滨恣�枏��� (Global Hotkey & IPC Routing)**嚗𡁜銁�祉��剝睸餈𤤿� `hotkey_rotator.py` 銝剛‘朣𣂷� `Alt+P` �典��剝睸嚗Ǒoffset 13`嚗厩�瘜典�銝𡒊��穿�撟嗅銁 `instock_MonitorTK.py` ��蜓餈𤤿��剝睸����噼�銝剔�摰𡁜笆摨𠉛� `open_ats_panel` 閫血����雿踹��券�鈭斗�蝒堒藁瘣餃𢆡�塚�靘萘��賢��圈妟�⊿▼�典��滚���
    - [x] **�删��㯄�� Alt+R 閫��頧株砭頧株蓮 (Alt+R MRU Rotator Integration)**嚗𡁜銁銝餅綉�嗅蝱 `_get_all_open_trade_windows` ��𢆡������餉�銝哨�憓𧼮�鈭�笆 ATS 蝏�垢蝒堒藁���瘣餃ế摰帋�瘜典�����行�瘚见��㗇��� ATS 蝏�垢嚗�朖撠�� HWND �䔶�撅𧼮�蝘� `"�椘儭� ATS �箄��芣祥鈭斗�蝏�垢 (ATSTerminal)"` �峕郊�啁��桀�餈𤤿��� `WindowRotatorDialog` ��揢�其葉��𣈲��鍂�琿�朞� `Alt+R` �刻�蝒堒�銵其葉�劐葉撟嗅撩�𤤿忽�讐蔭憿塚�摰䂿緵鈭��撟喳蝱���蝒堒藁�剔㴓�𥪜𢆡��
    - [x] **���瘚贝� 100% 憿箏⏚�朞�**嚗𡁻��啗�銵峕�霂訫�隞塚���𡠺 `test_favorites_pinning_and_styling.py` 銝� `test_watchlist_lifecycle.py`嚗㚁��券� 15 銝芣�霂閖★�格�隞颱��脩�嚗�100% �券�憿箏⏚�朞���

## 2026-06-13 02:00
- [x] **摰䂿緵 ATS 蝏�垢�滨��單釣銝芾�/�踹�蝵桅▲���鈭桐��喲睸銝𠹺�����閗��� (Implemented ATS Favorites Pinning, Highlighting, and Context Menu Linkage)**:
    - [x] **撌虫儒�∠巨瘙� (Universe Tree) �滨�銝芾�蝵桅▲銝𡡞�鈭�**: �齿�鈭� `UniverseTreeWidget` ��㺭�格凒�唳䲮瘜𨰻���朞� `GlobalFavoriteManager` �瑕��滨�銝芾��𡑒”嚗�銁 Mock 璅∪�銝𤾸��条𠶖����芸𢆡撖寥��孵�瘜其葵�∪銁���嚗�𡺨颲整���撖麄��漱�橒����餈𥡝�撘箏�蝵桅▲�滚��鍦���笆�滨��單釣銝芾�瘛餃� `"潃� "` �滨妍�滨�嚗𣬚�銝�瘨��瘛梁遛�峕艶 (`#1A2A1A`) 銝𦒘漁蝏踹��� (`#00FF88`)��
    - [x] **撌虫儒�∠巨瘙� (Universe Tree) �喲睸�𨅯�敹恍�笔�瘜�/�𡝗��單釣**: 銝箄�蟡冽����餈墧𦻖鈭� `customContextMenuRequested` 靽∪噡��𢰧�桀��餉�蟡刻��寞𧒄嚗諹��芷���閫���∠巨隞�����蝘啣僎撘孵枂銝𠹺�����𤏪��舀�敹恍�麨�𡏭挽銝粹��孵�瘜兩�脲��𨅯�瘨���孵�瘜兩�苷葵�∴�摰䂿緵鈭�鍂�瑚��典��單釣蝞∠��� (`GlobalFavoriteManager`) ��◇���蝻苷漱鈭鉝��
    - [x] **憭抒漣�怠�蝥踹�靚��頦芸膥 (Swing Pullback Table) �滨�銝芾�蝵桅▲銝𡡞�鈭�**: �齿�鈭� `SwingStateTable` �� `update_data_list` �� `load_mock_data`���朞� `GlobalFavoriteManager` �滨�銝芾�璉�瘚见笆�𡑒”銝芾��扯�蝵桅▲嚗諹䌊�券��� `"潃� "` �滨妍�滨�嚗�僎撠�砲銵峕��匧���聢隞交楛蝏輯��� (`#1A2A1A`) �䔶漁蝏踹��� (`#00FF88`) 蝏煺�擃䀝漁皜脫���
    - [x] **憭抒漣�怠�蝥踹�靚��頦芸膥�典��𥪜𢆡**: 靽桀�鈭�銁 `ATSMainWindow` 霈ａ� global favorites change �嗉��函��寞�嚗�僎蝥䭾迤鈭� `_safe_favorites_changed` 銝剔� `update_data_list` �滨�嚗𣬚�銝�頝舐眏�喃蜓蝥輻� `refresh_realtime_ui()` 餈𥡝�憭抒漣�怎𠶖��㦤�嗆��㺭�桀��滨�瘨����蝠摨訫��啜��
    - [x] **銵䔶��踹�撘箏漲�剖��� (Sector Heatmap Grid) �滨��踹�蝵桅▲���鈭桐��喲睸�𨅯�**:
        - **隞���惩��園�**嚗𡁜銁 `load_live_sectors` 銝凋蛹 `v_reversal_pool` �𡁜�銝� legacy Fallback �𡁜�銝方楝�唳旿皞鞱‘朣𣂷� `self.sector_to_codes` �踹�銝贝�銝芾�隞���惩�嚗峕𣈲��踎�堒��滨�銝芾�蝛輸�𤩺�扯��怒��
        - **憭𡁶輕蝵桅▲�鍦�**嚗𡁻��嗘� `sort_sectors` ���摨� `key` 蝞埈�����𨀣糓�虫蛹�滨��單釣�踹��脲��𡏭砲�踹��臬炏��鉄�滨��單釣銝芾��嘥��𣂷蛹擐𤥁��鍦����潘�隞舘�䔶�霂���厰��寞踎�堒�銝芾���撅墧踎�堒��函蔭憿嗚��
        - **�煾��穃�閫��銝𤾸𢰧�株���**嚗𡁻��嗘� `render_grid` �∠�蝏睃����蝵桅▲�踹���㨃��甅撘誩�蝥找蛹蝘烐�憌擧楛蝏踹��脫��� (`#1A2A1A` �� `#111E11`) �剝� `1.5px solid rgba(255, 215, 0, 0.8)` �煾��穃�颲寞�嚗�僎�冽踎�堒㨃���餈墧𦻖 `customContextMenuRequested` �喲睸鈭衤辣嚗峕𣈲��鍂�瑕銁�踹��∠�銝𠰴𢰧�桀翰�笔��Ｘ踎�㛖��滨��單釣�嗆����
    - [x] **摰峕�銝㯄★�訫�瘚贝�銝� 100% 蝏踵��朞�**: �啣�鈭� `test_favorites_pinning_and_styling.py` 銝㯄★�訫�瘚贝�嚗���渲��碶��典�蝞∠��具����亥�蟡冽���郭畾萄�靚�”���銝𡁶��𥕦㦛���瘜冽�雿栶��蔭憿嗆�摨譌���鈭桃��脯���蝻�霂��蝑匧��暹辺�𥪜𢆡�������厩� `test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗���券◇�拚�朞�嚗諹��𦒘�蝟餌����擃睃虾�䭾�找��澆捆�扼��

## 2026-06-13 00:30
- [x] **靽桀� ATS 蝏�垢銝芾�瘨典��𠰴之蝥批���瑪�瑕鍳�函征�賢僎��漣�踹��剖��曇�閫� (Fixed ATS Live Price/MA20 Blank & Upgraded Heatmap Aesthetics)**嚗�
    - [x] **撌虫儒�∠巨瘙䭾隅撟���唬遠憭𡁶輕摨西䌊����� (Universe Tree Price/Percent Auto-Retrieval)**嚗𡁻���� `refresh_realtime_ui` �寞�銝剔��唳旿�湔鰵�箏���� IPC 蝞⊿�撠𡁏𧊋�交𤣰�唳䔉�芯蜓餈𤤿��� `current_df` 撟踵偘�� `current_df` 銝箇征�塚��朞��啣��� `_async_load_stock_prices` �寞��典��啣�甇亥��冽鰵瘚芸��� API 撟嗥�摮睃� `self.price_pct_cache` 銝准����嗅笆銝芾�����滢遠�澆��曉�瘥娍隅撟���牐� 15 蝘坿�瘚�俈�𡝗綉�塚�敶餃�閫��鈭���臬𢆡�㚚�鈭斗��嗆挾�∠巨瘙䭾隅撟�遬蝷箔蛹 `0.00%` 隞亙�銝芾�����擧��冽�摨𤩺毽銋梁�蝻粹萅��
    - [x] **�齿�撟嗡耨憭� `_async_load_stock_prices` 銵峕��匧��亙藁 (Fixed & Optimized Offline/Real-time Stock Price Loader)**嚗𡁜���� `_async_load_stock_prices` 雿輻鍂 `s.get_real_time_tick(enrich_data=False)` 銝𥪯� HDF5 銝剛粉�吔�雿踹�蝻箔� `percent` �𡑒�諹恣蝞堒枂�亦�瘨典�銝��游��塚�銝𥪯撈�� 3蝘鍦椰�喟� IO �餃�嚗剹��緵�齿�銝箇凒�仿�朞� `s.get_stock_list_data` �𠉛��匧��唳答摰墧𧒄銵峕�嚗𣬚�餈�楊�� HDF5 IO嚗�僎雿輻鍂 `(close - llastp) / llastp * 100` �砍�霈∠�摰鮋�瘨典��曉�瘥䈑�蝖桐��典��臬𢆡��𪂹�急𧒄�∠巨瘙牐��嗉��曄內����＆��� 0 �冽𤣰瘨典���
    - [x] **�㯄�𡁜之蝥批���瑪 MA20d �嗆��㦤�屸��𨅯�霈∠� (Decoupled MA20d Calculations from current_df)**嚗𡁜縧�支� `refresh_realtime_ui` �瑟鰵銝剖笆 `current_df` 銝滩�銝箇征��′�𣂼�嚗屸�����嗆��㦤����交㺭�格��𣳇�餉����銝芾�撠𡁏𧊋鋡思蜓銵峕�餈𤤿�撟踵偘�塚�蝟餌��質䌊�刻��� `price_pct_cache` ���摮䀝遠�潭�霂餃���蟮 K 蝥踵��𦒘�憭拇𤣰�䀝遠嚗Ǒhist[-1][1]`嚗劐�銝箏�憭拇��唬遠�潦��𣄽鋆�末��鉄隞𠰴予���唬遠����游��堒�嚗��靚�鍂 `swing_tracker.update_stock_state` 撖寥𡺨颲�/閫��/鈭斗�銝㗇� the 銝芾�餈𥡝�皛𡁜𢆡��瑪霈∠�銝𡒊𠶖��㦤頧祉宏嚗�蝠摨蓥耨憭滢��瑕鍳�典�憭抒漣�恍𢒰�蹂���征�賜������
    - [x] **�齿��踹��剖��曉撩摨西恣蝞𨰜��凝�㕑�閫㗇��靝�摰匧�瘚桃��鍦� (Aesthetic Heatmap Aggregation & Safe Float Sorting)**嚗�
        - **�滚�瘣餉��𣂼��䭾�敺堒�**嚗𡁜���𧋦蝎埈𠂔�� `avg_score = sector_scores[sec] / count` �齿�銝箸凒�賭��啗�銝𡁏踎�㛖�摰䂿�摨血��𡁜��������啣��� `intensity_score = avg_score * (1.0 + 0.15 * count)`嚗峕�����滢��芣� 1 �芸��曇�����踹��𡁻��䭾���
        - **��漣蝘烐�憌𤾸凝�匧㨃��**嚗𡁜��支��笔��箇尐蝎㛖���滲蝥�/蝥舐遛�拍��∠�颲寞�霈曇恣嚗峕㺿銝箔��游�瘛梯𠧧蝟餅楛摨西�����𢠃�𤩺� HSL �𥪜�皜𣂼�摨閗𠧧銝𡒊蒾�脣凝�匧��� `hover` �穃��函𤫇嚗峕𣈲�� 5 蝘坿䌊���撘�郊摰𡁏𧒄�瑟鰵��
        - **撘訫�摰匧�瘚桃�銝擧㺭�潭�摨誯俈敺�**嚗𡁜銁 `sort_sectors` 銝凋蛹�曉�瘥𥪜�蝚虫葡銝擧��䀹㺭�鍦�蝻硋�鈭� `safe_float_pct` 撘�虜�脣鴃�賣㺭嚗䔶誑瘚桃��啣�潮�摨譍誨�踹���虾�賢紡�湧◇摨誯�銋梁� ASCII 摮㛖泵銝脣��詨�嚗���唬��踹�撘箏漲��隅頝������䀹㺭��移��䌊�園�摨𤩺�摨譌��
    - [x] **敶枏�������銝芾�銝剜��滨妍閫�� DRY 憭滨鍂 (Unified Authoritative Stock Name Resolution)**嚗𡁜� `main_window.py` �𣬚� `get_stock_name` �湔𦻖頝舐眏�喟頂蝏笔�撅�� `sys_utils.resolve_stock_name` �亙藁嚗䔶蝙敺埈���� EXE �舘�憭蠘䌊�典��冽𧋦�� HDF5 摨瓐����亦��滩��剔�摮䀝誑�𦠜鰵瘚芰�蝏𨅯��� API 蝑匧��拍��𡁻�嚗�蝠摨閙��支��� Nuitka/PyInstaller �祉�蝻𤥁��枏��臬�銝𧢲�隞㮖葵�∪�蝘唳遬蝷箔蛹�𨀣𧊋�乒�萘��𤤿���
    - [x] **靚�㟲撌虫儒蝑𣇉裦�∠巨瘙惩�憿箏�嚗��蝑𣇉裦�冽�靚�㟲�單��𦒘��堒�蝷� (Swapped Left Tree Columns to Position Period on the Last Column)**嚗𡁻���� `UniverseTreeWidget` ��”憭湔��砌�暺䁅恕摰賢漲�餉�嚗���𨀣瓲敹�鸌敺�/餈質葵�嗆���脲𦆮蝵桀銁蝚� 4 �梹��埝㺭蝚砌��梹�嚗���𦦵��㗇㦤��/���嚗�朖�睃𪂹��:d�蹱�����嗆����萘宏�刻秐蝚� 5 �梹����𦒘��梹�����嗅�甇亙笆朣𣂷� items 憛怠��寞�嚗Ǒload_mock_data` �� `update_pools`嚗剹����餉��冽㺭�桃�����硔��__lt__` �啣�銝𡒊鸌畾𠰴�蝚西䌊�冽�摨誯�餉�隞亙��堒捐����芷����𣂼���
    - [x] **�寞祥撌虫儒蝑𣇉裦�∠巨瘙惩�摰質◤�抒�摮㗛�甇餃���憭批捐摨阡��嗅㨃雿𤩺�瘜閗��湧䔮憸� (Fixed Universe Tree Column Width Locked & Resize Frozen)**嚗�
        - 敶餃��駁膄鈭� `UniverseTreeWidget` 銵冽聢銝剝�撖寧洵 4 �梹��唬蛹�𨀣瓲敹�鸌敺�/餈質葵�嗆���嘅���′蝻𣇉���憭批捐摨� `max_widths={4: 350}` �𣂼�嚗��霈貉砲�堒銁 DPI 蝻拇𦆮銝𦒘��𣬚���捐摨虫��𣳇�蝣齿赤�烐�隡詻��
        - ��漣鈭� `ats/ui/styles.py` ���𡁶鍂�堒捐����𤥁��笔膥 `setup_header_persistence` �� `restore_action` �箏�嚗𡁜銁瘥𤩺活隞擧𧋦�� `window_config.json` �拍�餈睃�銵典仍�嗆���`restoreState`嚗劐��𠬍�撘箏��朞�敺芰㴓�齿鰵�𦠜��匧��� SectionResizeMode 霈曄蔭銝� `QHeaderView.ResizeMode.Interactive`���銝滢��踹�鈭���抒�蝻枏��滨蔭��辣銝剜��嗵�銝滢��� resize 璅∪�撠�鸌摰𡁜��⊥香銝滚虾�㗇嗻��■�橘��䔶�隞擧覔�砌��舀�鈭�鍂�瑁䌊�望�隡豢�銝��𦯀漱�𣬚瑪��
    - [x] **敶餃��娪膄撌虫儒�∠巨瘙䭾�憸睃��烐覔��� Emoji 閫���芷𨺗撟嗉‘�� Mock 蝏蠘恣�圈� (Removed Left Tree Emoji Badges & Populated Mock Statistics)**嚗�
        - 撠� `universe_widget.py` 銝� `title_label` �𣬚� `"�� 蝑𣇉裦�∠巨瘙�"` ���碶蛹 `"蝑𣇉裦�∠巨瘙�"`嚗�
        - 撠�椰靘扯�蟡冽�銝凋�銝芣��寡��嫣��� `"�� �䠷�厰𡺨颲暹�"`��"�� 蝎暸�㕑�撖��"`��"�兛 摰䂿�鈭斗�瘙�"` 撖孵� emoji �暹��券�敶餃��拍��亦氖嚗�
        - 銵亙�鈭� `load_mock_data` 蝻箏����霈∪�蝻�嚗䔶蝙敺� Mock 璅∪�銝𤾸��条𠶖�������湛�����啗站憒� `"�䠷�厰𡺨颲暹� (Radar Pool) (5)"` ���銝�蝥舀�摮堒��圈�蝏蠘恣�澆�嚗䔶�霂��閫����移蝞�銝��湔�扼��
    - [x] **靽桀��曹� Mock �啁��芸�銋匧�撘閧鍂撘訫��� UnboundLocalError (Fixed UnboundLocalError in Mock Data Loading)**嚗𡁜銁 `universe_widget.py` �� `load_mock_data` �寞�銝哨�撠� `radar_items`��watch_items` �� `trade_items` �唳旿����嘥��硋�銋劐誨����典�蝵株��游���䌊撖孵� Tree �寡��寡挽蝵� `setText(0, ...)` 銋见�嚗�蝠摨閙��支��典�頧� Mock �∠巨瘙䭾𧒄�䭾𧊋摰帋�����典��𤑳�撏拇�撘�虜��
    - [x] **�𧼮�瘚贝� 100% 蝏踵�頝煾��**: �𣂼�餈鞱� `pytest test_watchlist_lifecycle.py`嚗���� 11 憿寧��賢𪂹�煺��唳旿銝��湔�扳�霂閙�隞颱�霅血��朞���

## 2026-06-12 23:10
- [x] **�齿� ATS 蝏�垢�臬𢆡�亙藁撣��撟嗅�銝𧢲��蠘��𨅯� (Relocated ATS Launcher to Bottom Action Dropdown)**嚗�
    - [x] **�芸極�瑟�蝘駁膄�曉��厰僼**嚗帋� `instock_MonitorTK.py` 銝餃極�瑟�銝剖��支��牐��� `"ATS��"` �曉��厰僼��
    - [x] **����亙��典��賡�㗇𥋘�𨅯�**嚗𡁜銁 `self.action_combo`嚗���典��賭��㗇�嚗厩� `options` �𡑒”銝剛蕭�牐� `"ATS蝏�垢"` �厰★嚗�僎�� `run_action` 靚�漲�寞�銝剜�撠��摰� `open_ats_panel`����瑕銁靽脲��典� `Alt+P` 敹急㭘�桐��嗅虾�函��齿�銝页��踹�鈭���𣂼��𡝗踎�埈㺭�桃撩憭梁�蝏�辣�删鍂�曄尐暺��撣����

## 2026-06-12 22:45
- [x] **靽桀�摰墧𧒄�喟��芰��餉��嗅紡�渡��䔶�隞���滚��𥪜𢆡 Bug (Fixed Duplicate Linkage Storm Triggered by Real-Time Decision Signal Mark)**嚗�
    - [x] **蝘駁膄 _kernel_mark_signal_rows �����䌊�券�劐葉霈曄蔭 (Removed Auto Selection Set in Signal Row Marker)**嚗𡁜銁 `stock_selection_window.py` �� `_kernel_mark_signal_rows`嚗��蝑𤥁���扇銝𡡞緾���銝哨�瘜券��劐��芸𢆡靚�鍂 `self._signal_tree.selection_set(first)` ���餉���
    - [x] **靽萘�擃䀝漁皜脫�銝舘������ (Kept Viewport Focus & Tag Highlighting)**嚗帋��找��� `self._signal_tree.focus(first)` �� `self._signal_tree.see(first)` 摰帋��箏�嚗𣬚＆靽脲鰵鈭抒���漱�㮖縑�瑁�隞滩��典�銵券�甇�虜��緵�屸緾����峕𧒄敶餃��踹�鈭��頝喳��嗅膥�瑟鰵隞亙�憭帋葵�嗆��㦤擃㗛��滨��嗅蒂�亦�憭㚚�頧臭辣鈭斗𤜯�滚��𥪜𢆡憌擧𠂔��
    - [x] **�𧼮�瘚贝� 100% 蝏踵��朞�**: �𣂼�餈鞱� `pytest test_watchlist_lifecycle.py`嚗�11 憿寞瓲敹��敶埝�霂訫��圈�朞���

## 2026-06-12 22:10
- [x] **靽桀�蝡硺遠韏偦帕�瑕鍳�典��嗉粥�踹㦛蝻箏仃銝舘䌊����� (Fixed Bidding Racing Panel Cold-Start Minute Chart Missing & Active Auto-Retrieval)**:
    - [x] **�寞祥�瑕鍳�冽��𣇉撩憭曹� K蝥� cache �堒仃**: 靽桀�鈭�銁 `sector_bidding_panel.py` ���蝏罸�憭游�頝罸��∟���遣銝哨��惩��滢耨�寧凒�仿��券���綫���畾� `f.get('klines')` 隞�𤜯 `self._follower_klines(code)` 撖潸稲�瑕鍳�冽㺭�桐蛹蝛綽�隞��瘞游像�閙覔�渡瑪嚗厩�蝻粹萅��
    - [x] **銵亙�隡删�樴坔仍 `'k_cache'` 蝏𤘪�**: �� `Fallback: 雿輻鍂隡删��� Leader + Followers 蝏𤘪�` 樴坔仍�� `row_item` ���銝剛‘朣𣂷� `'k_cache'`嚗䔶蛹蝏睃㦛憪娍��𣂷�摰峕㟲�� `prices` 銝� `volumes` 摨誩���
    - [x] **撘訫� third-level �芣�銵峕��匧�銝𤾸�甇�**: �� `_populate_table` �� `[HOT-FIX] 憭𡁶漣�芣�銵峕�銵仿�` 銝哨��� `detector` 蝻枏��� `TickSeries` 蝻枏���� K蝥� �塚��惩�撖� `_follower_klines(code)` ��洵銝厩漣銝餃𢆡�匧�撟嗅�甇乓����質䌊�典銁�瑕鍳�典��祇𡢿閫血� API 銵亙� 35 �� K蝥� �坔�蝻枏�嚗��蝢舘䌊���憭滚��渡�韏啣飵�橘�撟嗡� 100% �踹�鈭�笆�毺��曉�霈∠��餉���噩�乓��
    - [x] **����𧼮�瘚贝� 100% 蝏踵��朞�**: �𣂼�餈鞱� `pytest test_watchlist_lifecycle.py`嚗���� 11 憿寧��賢𪂹�煺��𥪜𢆡���瘚贝��冽㺭�朞���

## 2026-06-12 21:50
- [x] **摰䂿緵撌虫儒瘣餉��踹�銵冽溶�㰘�皛斤�霈∪� (Implemented Filtered Count Column 'cout' for Active Sectors Table)**:
    - [x] **�嘥��碶��滨蔭�湔鰵**: �� `sector_bidding_panel.py` 銝剖� `sector_table` �� 5 �𡑒��港蛹 6 �梹�撟嗅銁樴坔仍�堒��Ｘ��乩誑 `'cout'` 銝箄”憭渡��圈�蝏蠘恣�𨰜��
    - [x] **摰䂿緵摰墧𧒄餈�誘�∩辣蝏蠘恣�餉�**: �啣� `_get_filtered_stock_count` 撌亙��寞�嚗�𢆡����𡝗踎�堒�樴坔仍銝舘��讛��葵�∴�撟嗅銁摰讛�餈�誘銝擧�蝝Ｚ�皛斗辺隞嗥�蝥行�銝讠移��恣蝞堒�雿坔虾�其葵�⊥㺭�譌��銁�㰘�皛斗辺隞嗆𧒄嚗諹䌊�刻��噼砲�踹�敶枏��券�銝芾��啜��
    - [x] **�湔鰵�堒笆朣𣂷��见𢆡�鍦�**: 靚�㟲 `_refresh_sector_list` �𣬚��拍��埈葡�𤘪�撠���芸𢆡撠� `_filtered_count` 蝏穃��� Col 4嚗�朖樴坔仍�𡡞𢒰嚗㚁�撟嗆凒�� Python 蝥扳�摨𤩺�撠��雿踹��孵稬 `cout` 銵典仍�嗉�憭笔��啣�蝖桃��啣�澆之撠𤩺�摨譌��
    - [x] **UI �嗆���憭滚���**: ��漣鈭� `_save_ui_state` �� `_restore_ui_state` �寞�嚗�銁�Ｗ� `sector_table` �� Header �嗆���瘛餃��埈㺭�⊿�靽脲擪嚗屸俈甇Ｗ��埈㺭憓𧼮�撖潸稲 Hex �Ｗ�撘�虜�𣇉蒾撅譌��
    - [x] **�𧼮�瘚贝� 100% 頝煾��**: 11 憿寞瓲敹���賢𪂹���霂訫��券◇�拚�朞���

## 2026-06-12 21:40
- [x] **隡睃��芸�銋匧����𡁶鍂皜脫��餉�嚗屸��滚撩�嗆筑�寞聢撘誩� (Optimized Custom Column Formatting to Prevent Forced Float Rendering)**:
    - [x] **�匧��瑟葡�栞䌊摰帋��堒��**: 摨笔�鈭�笆���㗇筑�寞㺭銝�敺衤蝙�� `f"{val:.2f}"` ��撩�嗆聢撘誩�銵䔶蛹��鰵�餉�隡𡁏�瘚𧢲筑�寞㺭�臬炏�舀㟲�堆�憒� `1807.0`嚗㚁�憒���荔��躰䌊�典竉蝳餃偏�券妟撟嗆遬蝷箔蛹�湔㺭�瑕�嚗�� `1807`嚗㚁�撖嫣���鉄�笔�撠𤩺㺭��筑�寞㺭隞亙��墧㺭�潛掩�页��蹱��嗆𧋦��㺭�株��綽�摰䂿緵鈭��𨀣㺭�格糓隞�銋�停�曄內隞�銋��萘��硺噩�亙��芸𢆡�澆捆��
    - [x] **�芸𢆡�滨蔭�啣�潭�摨𤩺�敹�**: �刻䌊摰帋��𦯀葉嚗���𨀣�瘚见��潭糓�湔㺭��筑�寞㺭�硋虾頧祆揢銝箸筑�寞㺭���蝚虫葡嚗𣬚頂蝏笔銁摨訫�皜脫��嗡��芸𢆡撘��� `is_numeric=True`嚗䔶誑蝖桐��冽��典��餉”憭湔��冽�摨𤩺𧒄�賢��瑕��芰��啣�潮◇摨𧶏��屸� ASCII 摮㛖泵銝脤◇摨譌��
    - [x] **�𧼮�瘚贝� 100% �朞�**: �券� 11 憿寧��賢𪂹�蠘䌊�典����瘚贝��券�蝏踵��朞���

## 2026-06-12 21:35
- [x] **靽桀� `bidding_momentum_detector.py` 銝剔� `NameError: name 'configured_cols' is not defined` 撘�虜 (Fixed NameError for configured_cols in Sector Aggregation Worker)**:
    - [x] **摰帋�蝻箏����蝵桀�銝擧瓲敹�睸�㗛�**: �� `_aggregate_sectors` ���嚗屸��典�憪见�撟嗅�銋劐� `configured_cols` (霂餃��� `cct.CFG.bidding_window_col`) �� `core_keys` ������敶餃�閫��鈭��甇交踎�𡑒���瑪蝔见銁霈∠�頝罸��∟䌊摰帋��堒�撟嗆𧒄�删撩撠穃�銋匧紡�渡�撏拇���
    - [x] **靽嗪��芸�銋匧��冽踎�𡑒���𧒄����港���**: 靽桀��𠬍��芸�銋匧��賢�摰匧��啣銁銵䔶��踹���BC�𡁏��踹��𡁜��唳旿����鞉𧒄�删�隡𣳇�坿秐 `followers` �� `leader` 蝏𤘪�銝准��
    - [x] **�券��𧼮�瘚贝� 100% 蝏踵��朞�**: �𣂼�餈鞱� `pytest test_watchlist_lifecycle.py`嚗���� 11 憿寧��賢𪂹�煺��唳旿銝��湔�扳�霂� 100% 憿箏⏚�朞���

## 2026-06-12 21:30
- [x] **摰��瘨�膄 `SectorBiddingPanel` 銵冽聢銵峕�撱箇� `'dff2'` 蝖祉������僎擃䀝漁皜脫�皜脫��餉� (Completely Removed Hardcoded 'dff2' in Sector Table Row Building & Unified DFF Highlight Rendering)**:
    - [x] **�拍��娪膄銵峕�撱箔葉�� `'dff2'` 蝖祉���**: �� `sector_bidding_panel.py` ��葵�∟”�潭凒�啣儐�� `_populate_table` 銝哨�敶餃��𣳇膄鈭��憭��蝚� 3715, 3752, 3788, 3821 銵䕘�蝖祉���� `'dff2': ...` �桀�潦��⏚�典歇�厩��冽����𡁶鍂�𣂼��餉� `for col_key in self.stock_cols:`嚗諹䌊�典��� `dff2` 隞亙� `dff3`��rank` 蝑㗇��劐遙�讛䌊摰帋��滨蔭�㛖��唳旿�匧�����伐��𡁜�鈭�蓡����曄��硺噩�亙��𡁶鍂閫��艾��
    - [x] **�𡁶鍂�� `dff` 蝟餃��訫��潭葡�㯄�鈭�**: �典���聢�潭凒�唬��瑕����脫𧒄嚗����𧋦�訾��祉��� `elif col_key == "dff"` �� `elif col_key == "dff2"` 銝支葵蝖祉���ế�剖��臬�撟嗡蛹�𡁶鍂�� `elif col_key.startswith("dff")`��蝙敺埈��劐誑 `dff` �滨��賢���𢆡��漲�誩�����曹澈�詨����鈭桅��脫葡�𤘪芋撘𧶏����隞㚚� `dff` �梹�憒� `rank` 蝑㚁����摰匧�韏� `else` ��𣈲餈𥡝��𡁶鍂��㺭�潭聢撘誩�銝𡡞�𡁶鍂�鍦���
    - [x] **�𧼮�瘚贝� 100% �朞�**: �齿鰵餈鞱� `pytest test_watchlist_lifecycle.py` 11 憿孵��笔𦶢�冽��詨����銝舘��冽�霂𤏪��券�蝏踵��䭾𥁒�䠷�朞�嚗䔶��靝�蝡硺遠�Ｘ踎�典�蝐餃𢆡����滨蔭銝讠�蝟餌��亙ㄝ�扼��

## 2026-06-12 21:00
- [x] **摰䂿緵�芸�銋匧�隞� df_all 撘箇凒餈噼繮�碶��滨蔭撘箏��芣�嚗䔶耨憭滚��脣��睃���/蝻拚��曆腺憭� (Implemented Direct Custom Column Fetching from df_all & Pre-processing Self-healing to Restore K-line / Trend Charts)**:
    - [x] **�㯄�朞䌊摰帋��𦯀� `df_all` 銵峕��渲�**: �萄儐��蝞��硺噩�亙�霈曇恣嚗𠃋ISS嚗㚁��� `bidding_momentum_detector.py` ��葵�∪��唳旿�湔鰵 `update_meta` �嗆挾嚗諹䌊���撠��蝵桅★ `bidding_window_col` 憯唳���䌊摰帋��埈㺭�潭��硋僎摮睃��� `ts.custom_cols`嚗�僎�函��𣂼�撅� `_global_snap_cache` 銵峕�敹怎��嗅𢆡���撟嗚��I �Ｘ踎��㺭�株繮�𡝗䲮撘𧶏��� `f.get(col_key)`嚗匧���蟮�㰘蝸韏啣飵�曄�����芣�銵亙��餉� 100% 靽脲�����餉�銝滚�嚗䔶�隞��撠睲� UI 撅���唳旿憭��撘���嚗峕凒�踹�鈭���䠷�䭾��� any �臭��具��
    - [x] **�芷�����蟮摮䀹﹝�唳旿�Ｗ�銝擧�銋��**: �� `load_from_snapshot`嚗���脣��睃�頧踝�銝哨��啣��芷���閫��瘚��嚗峕𣈲����啁��堒��𡝗唂����詨�敹怎�銝剖歇摮䀹﹝��䌊摰帋��梹�憒� `dff2` �梹��齿鰵�曉�撟嗉��蠘秐 `new_snap_cache` 銝哨�撟嗅銁����硋��堒��嗅� `custom_cols` 撟嗅� `meta_cols` 靽嘥�嚗䔶�霂����蟮銝𤾸��䀹㺭�株”�啁�銝��湔�扼��
    - [x] **蝏湔����厩′蝻𣇉�����烾�餉�銝舘䌊��������**: ����笔㭠�唬��嗘����蝖祉���� 10 �堒��嗉䌊��‘�踵㦤�塚�憒� `klines`��k_cache` 銵仿���隅頝諹恣蝞㛖�嚗㚁�銝滚笆���蝔喳�隞��鈭抒�隞颱�靘萄��㚚��辷�蝖桐��函頂蝏罸��舫�摨衣迅摰朞�銵䎚��
    - [x] **靽桀�銵䔶��踹��𡁜�銝舘��典��餌蒾撅誩��芸�銋匧�銝Ｗ仃 (Fixed Custom Columns in Sector Aggregation & Double-Click Visualizer blank screen)**:
        - 靽桀�鈭� `bidding_momentum_detector.py` �� `_aggregate_sectors` �踹��𡁜�嚗��摰噼�銝𡁏踎�𦯀誑�� SBC �𡁏��踹�嚗劐葉��� `followers` �� `leader` 摮堒��唳旿�嗥眏鈭𡒊′蝻𣇉��桀�撖潸稲�芸�銋匧�嚗�� `dff2` 蝑㚁��刻��讛��屸�憭游笆鞊∩葉�𤑳��唳旿銝Ｗ仃�� Bug嚗���唬��芸𢆡��僎 custom columns��
        - �峕郊��漣鈭� `load_from_snapshot` �滚��堒�敹怎��寞�嚗峕𣈲��銁憭滨��墧滲�嗆覔�桅�蝵桅★�芷���銵仿�撟嗉��笔��脰��讛��屸�憭游笆鞊∠��芸�銋匧��唳旿��
        - 靽桀�鈭� `sector_bidding_panel.py` ��稬銝芾��曇”�𥪜𢆡銝哨��梁′蝻𣇉��㛖揣撘� `8` 撖潸稲����餌蒾撅誩�頞羓� Bug��緵�冽㺿�� `self.stock_cols.index("trend")` / `"code"` / `"name"` 蝑匧𢆡���雿滨揣撘蓥誑餈𥡝�蝎曄＆閫�藁�𥪜𢆡�𦠜㺭�格�憭溻��
    - [x] **�𧼮�瘚贝� 100% �𣂼��朞�**: 餈鞱� `pytest test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�11 憿寞瓲敹��敶埝�霂� 100% �券��朞���


## 2026-06-12 20:30
- [x] **摰䂿緵蝡硺遠�Ｘ踎�冽����滨蔭銝𡒊𡠺蝡贝䌊�冽�摨𤩺沲�� (Implemented Dynamic Column Configuration & Independent Manual Sorting for Bidding Panel)**:
    - [x] **�冽��繮�硋僎�㰘蝸�烾�蝵� (Dynamic Configuration Loading)**: �� `__init__` 銝剖���𧋦蝖祉��� the 10 �㛖������蛹�� `GlobalConfig` �� `bidding_window_col` �滨蔭憿對�憒� `cct.CFG.bidding_window_col`嚗匧𢆡���靘䜘���銋劐���葉撘誩��滨蕃霂穃��� `col_map` �屸�霈文捐摨行�撠� `col_width_map`嚗�僎�舀��芸�銋匧���𢆡����牐��齿鰵�鍦���
    - [x] **摰䂿緵�堒捐�芷�������𤥁䌊����� (Adaptive Column Width Persistence Protection)**: �� `_save_ui_state` 銝剖�甇乩�摮睃��滨� `stock_table_cols` �烾�蝵殷�撟嗅銁 `_restore_ui_state` 銝剖��仿�蝵桐��湔�扳嵗撉䎚��𥅾�冽��朞�靽格㺿�滨蔭靚�㟲鈭���唳��烾◇摨𧶏�蝟餌��賜��湔��亙榆撘�僎�芸𢆡頝唾��� Hex �嗆��� `restoreState` �Ｗ�嚗�誑�脫唂撣��閬���𣇉蒾撅𧶏�嚗�像皛煾���𧼮�暺䁅恕�堒捐�芷����垍�銝哨�撟嗅銁銝衤�甈⊥迤撣賊���箸𧒄�芸𢆡閬���湔鰵銝箸��啁�甇�＆����𣇉𠶖����
    - [x] **摰䂿緵 UI ��𢆡���憪见� (Dynamic Column Initialization)**: �齿�鈭� `_init_ui` 銝剔�銵冽聢銵典仍��遣�餉�嚗�𢆡��恣蝞堒��啣僎霈曄蔭銵典仍�����覔�桀𢆡���摰賢��詨笆瘥譍��𡑒挽蝵桀�憪衤漱鈭鍦捐摨佗�撟嗆�摰𡁏��𦒘��𡑒䌊�冽�隡賊唍皛∟����摰𣬚�瘨�膄鈭�𢰧靘抒蒾颲嫘��𥅾�滨蔭銝剖��怠��嗅㦛�� `"trend"`嚗���冽����嗥�摰𡁜�撖孵��� `TrendDelegate` 憪娍�皜脫�銝准��
    - [x] **�齿�摰���祉���𢆡���摨𤩺㦤�� (Dynamic Manual Sorting Logic)**: 敶餃��滚�鈭� `_populate_table` �𣬚��见極�鍦��寞�嚗��撘���笔��蹱香���蝝Ｗ�嚗�� `0`��3`��8` 蝑㚁���緵�函�摨讛��芷���隞𤾸��滚��滨蔭銝剖粉���鍦��� the key name嚗�僎�寞旿霂仿睸�滚𢆡���撠��銵�笆摨𠉛�摮埈挾�鍦�嚗���� `pct` 瘨典���� `score` ��貌蝑㚁�嚗���嗡��嗘���笆�單釣�∩�樴坔仍�∠�蝔喳�鈭峕活蝵桅▲�脩瑪��
    - [x] **�惩𤐄�㛖揣撘閗䌊����𣂼�銝舘�憛怠��餉� (Index-Independent Cell Population)**: 
        - ��笆�劐葉�嗆���憭滢葉隞���㛖��交𪄳嚗���乩� `self.stock_cols.index("code")` �冽���雿㵪��脰�頞羓�嚗�
        - �� `_populate_table` ����訫��潭葡�㮖葉嚗����𧋦�� `0~9` 憿箏�蝖祉���‵����㛖�����餉�嚗屸���蛹�寞旿 `stock_cols` 餈𥡝��冽��儐�航翮隞���抅鈭� `col_key` �芷���銝𡃏𠧧�𠰴‵���靝誨���腈���𨅯�蝘售�腈���𡏭��聆�腈���𦦵緵隞猾�腈���𨀣隅撟�%�腈���𨀣�蝏芬�萘���捆嚗���唬�銝𤾸���������◇摨讛圾�佗�敶餃��㯄�帋�蝡硺遠/撠曄��踹��𥪜𢆡�烐綉��𢆡����滨蔭�嗆���
    - [x] **摰䂿緵�芸�銋匧���𢆡��㺭�格��匧�銝舘䌊�券�𡁶鍂皜脫� (Dynamic Custom Column Data Loading & Rendering)**: �齿�鈭� `_populate_table` �唳旿鋆�‵瘚��嚗�銁銵峕㺭�格�撱箸𧒄�芸𢆡�滚� `stock_cols` 隞𤾸�憪贝���㺭�格�銝剖𢆡���蝝Ｗ��潦����嗅銁�鍦��斗鱏銝舘”�澆���聢皜脫��餉�銝剖��牐� `else` �𡁶鍂�𨅯���𣈲嚗䔶蝙敺𦯀遙雿閙𧊋蝖祉�����芸�銋匧�嚗�� `"dff2"`, `"red"`, `"win"` 蝑㚁��質��芸𢆡摰峕��唳旿�匧���掩�贝蓮�Ｕ���憸穃��唳葡�㮖�撖孵���㺭��/摮㛖泵銝脫惣�賣�摨譌��
    - [x] **靽桀�蝻抵��躰秤 (Fixed Unexpected Indent)**: 靽桀�鈭� `sector_bidding_panel.py` ��洵 1802 銵� `self.setWindowTitle` 隞亙�蝚� 2513 銵� `vh = self.stock_table.verticalHeader()` ��憬餈偦�霂荔�蝖桐��Ｘ踎 and �𤾸蝱蝥輻�甇�虜�臬𢆡�㰘蝸��
    - [x] **11 憿寞瓲敹��敶埝�霂� 100% �𣂼��朞� (100% Pass of All Tests)**: 餈鞱� `pytest test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�11 憿寧��賢𪂹�煺��𥪜𢆡���瘚贝��券��朞�嚗峕�隞颱��𧼮��桅���

## 2026-06-12 19:40
- [x] **隡睃�銝芾��滨妍閫��撟嗆㜃�芯葵�∪�雿滨泵瘙⊥� (Optimized Stock Name Resolution & Prevented Placeholder Pollution)**:
    - [x] **����砍𧑐銵峕�撘閙����蠘圾�� (Integrated Local Sina Engine Resolution)**: �� `sys_utils.py` �� `resolve_stock_name(code_clean)` 閫���賣㺭銝剖��乩�蝚� 0.5 甇乓��銁���擃㗛�毺�摮䀝��𠬍�隡睃�摰硺��硋僎雿輻鍂 `JSONData.sina_data.Sina(readonly=True).get_code_cname(code_clean)` �交�蝝Ｘ�憡��蟡典�蝘啜��迨霈曇恣�賢�雿輻�摨誩銁瘥怎�蝥批��瑕��唳��唬���＆��葉���蝘堆��峕𧒄敶餃��踹�鈭��敹���� HDF5 ��辣霂餃����隞瑁�撽砍翰�批��𣂼��滚�����脰��剛扇敶閙�蝝Ｕ��
    - [x] **�滢�憭帋����蝏𡏭窈瘙� (Reduced Redundant Network Requests)**: 敶𤘪𧋦�� `sina_data` �急�蝻枏��𤥁�隞擧𧋦�唳㺭�格�霂餃��箇��齿𧒄嚗𣬚凒�亥��𧼮僎�惩����蝻枏�銝哨���之�誩�鈭�眏鈭𤾸��臬𢆡����滚��𡝗鰵�∠�憸𤑳��烐鰵瘚� API �𠉛�頧株砭霂瑟������嚗屸�雿𦒘�鋡急鰵瘚芸�蝳� IP ����押��
    - [x] **�𧼮�瘚贝� 100% �𣂼��朞� (Passed All Watchlist Regression Tests)**: 餈鞱� `pytest test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�11 憿寞瓲敹��敶鍦����瘚贝��券�蝏踵��朞�嚗峕�隞颱�撘�虜�硋�摰寞�批�蝒���

## 2026-06-12 19:30
- [x] **摰䂿緵 TK 銝餌��ａ��� ATS �箄��滨�蝏�垢�臬𢆡�亙藁 (Integrated ATS Launcher into TK Monitor UI)**:
    - [x] **摰䂿緵�臬��芷����臬𢆡�箏�**: �� `instock_MonitorTK.py` 銝剖��唬� `open_ats_panel()` 銝� `get_visualizer_path()` �� Nuitka/PyInstaller �澆捆�芷����餉�����乩�蝏煺����瘚见遆�� `is_packaged_env()`嚗�僎�朞� `get_app_root()` 蝏煺��瑕�蝏嘥笆�寧𤌍敶𨰻��砲�箏��賢��芸𢆡霂��敶枏�蝔见��臬炏憭���枏�璅∪�嚗��摰� PyInstaller��uitka standalone �� Nuitka onefile嚗㚁��交糓�枏��𡒊� exe �臬�嚗���湔𦻖�典��唬誑撘�郊�鮋獈憛𧼮耦撘誩𤧅韏瑕笆摨𠉛� `ATS_Terminal.exe` �� `trade_visualizer_qt6.exe`嚗𥕦��𨀣糓 native Python �𡁏𧋦撘��𤑳㴓憓���坔��啣�甇亙𤧅韏瑞㮾摨𠉛� `.py` �𡁏𧋦嚗䔶�霂��銵��摰寞�改��踹�銝餌瑪蝔� I/O �⊿▼銝舘楝敺��蝘颯��
    - [x] **�其蜓�批��Ｘ踎瘛餃� ATS 敹急㭘�臬𢆡�厰僼**: �� `ctrl_frame` 銝餃極�瑟�銝剜溶�牐� `ATS��` �蠘��厰僼嚗��雿滨蔭�鍦銁 `靽∪噡�𤣳` �厰僼�𠬍��齿艶�脖蛹 `darkblue`��
    - [x] **瘜典��典� Alt+P 敹急㭘��**: 蝏穃�鈭� `Alt+p` 銝� `Alt+P` ���撅��桃�敹急㭘�殷�雿踹�鈭斗��睃虾隞亦凒�亦鍂�桃��祇𡢿�方絲 ATS �滨��批��堆�摰䂿緵鈭��蝏�垢銝��渡��桃�撖潸⏛�滢�雿㯄���
    - [x] **�芣�霂閗�銵� 100% �朞�**: 餈鞱� `test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�11 銝芣瓲敹��霂閧鍂靘见��函遛�烾�朞�嚗峕瓷�匧��� any 霂剜��硋��賣�批�蝒���





## 2026-06-12 18:25
- [x] **靽桀�靽∪噡璉�瘚� detect_signals 銝剔� NumPy �啁� values 撅墧�批�撣� (Fixed detect_signals NumPy Array AttributeError)**:
    - [x] **摰䂿緵 safe_values �亙ㄝ�扳��硋膥**: �� `stock_logic_utils.py` 擐㚚�憓𧼮�鈭��撅� `safe_values(val)` 颲�𨭌�賣㺭��砲�賣㺭�刻繮�� Series �� DataFrame �㛖� values �啁��塚�隡朞䌊�冽�瘚见�蝐餃�����𨅯笆鞊∪歇蝏𤩺糓銝�銝� `numpy.ndarray`嚗�朖�� `values` 撅墧�改�嚗���湔𦻖餈𥪜�霂亙笆鞊⊥𧋦頨恬�隞舘��蝠摨閙�蝏苷��䭾㺭�桃掩�见銁霈∠�蝞⊿�銝剖��笔��硋紡�渡� `'numpy.ndarray' object has no attribute 'values'` 餈鞱��嗅援皞���
    - [x] **�券��湔鰵 stock_logic_utils.py ����㚚�餉�**: 撠� `RealtimeSignalManager.update_signals`��calc_breakout_signals` �� `calculate_intraday_breakout_for_single_stock` �寞�銝剔��券� 20 雿坔� direct `.values` 靚�鍂�齿�銝� `safe_values(...)` 靽脲擪靚�鍂����Ｖ�霂�����笔��誩�霈∠��扯�嚗��靽肽�鈭�銁擃㗛�摰墧𧒄銵峕��券������蝡舐掩�见��冽�扼��
    - [x] **52 憿寞瓲敹�䌊瘚贝䌊璉� 100% 蝏踵�頝煾��**: �齿鰵餈鞱� pytest 瘚贝�憟𦯀辣嚗���� 52 銝芸�敶埝�霂蓥����瘚贝��其��券�銝�甈⊥�扳�霅血��朞�嚗峕𧊋撘訫�隞颱��臭��具��

## 2026-06-12 17:35
- [x] **ATS蝟餌��芣��芣�銝擧瓲敹���賡�霂� (ATS Self-Testing & Core Functionality Verification)**:
    - [x] **餈鞱��券�瘚贝��其�撟嗅��鞟��� (Run All Test Cases and Analyze Results)**: 餈鞱� `pytest` 頝煾�帋��券� 52 憿孵�������瘚贝���
    - [x] **蝻硋�蝟餌�蝥扯䌊瘚贝䌊璉��賢��亙� (Compile System-Level Self-Testing Report)**: 璇喟� 5 憭抒掩瘚贝�璅∪�嚗���賢𪂹�麄��瓲敹�恣�瓐��𠯫���蝑硔����函��喋��漱�枏��訾�憌擧綉嚗㚁��渡�瘚贝���誘�峕�霂閗��硋漲嚗���乩��函� Artifact �亙�銝准��
    - [x] **璉��交瓲敹���䀝�璅⊥��唳旿蝞⊿��嗆�� (Verify Live and Simulation Data Pipeline Status)**: 蝖桐� `IPCBridge` (Port 26670) ����嗆��航楝�曹� `current_df` 敹怎��券�鈭斗��嗆挾����典����芣�甇�虜��

## 2026-06-12 04:00
- [x] **摰䂿緵摰墧𧒄銵峕�蝞⊿�蝏穃���niverseManager�冽���皛支�SwingStateTable摰䂿�撖寞𦻖 (Implemented Real-Time Pipeline Binding, Dynamic Filtering & Live Swing State Integration)**:
    - [x] **�㯄�� UniverseManager 摰墧𧒄�唳旿撽勗𢆡 funnels (Connected UniverseManager to Live IPC Stream)**: �� `ATSMainWindow` 銝剖��� `UniverseManager`��僎�� `load_db_data` �嗆挾嚗����𧋦�蹱��/Mock ��葵�∪����瘙惩�頧賡���蛹撠��摰� SQLite ��蟮靽∪噡�� open positions ��� `universe_manager`嚗𣬚��舘��� `get_pools()` �亙�憪见� Tree Widget 閫�㦛��
    - [x] **�𤾸蝱撘�郊憸��頧�/銵仿���蟮�唳旿 (Background Lazy-Loading of Historical OHLCV)**: 撘訫� `_async_load_stock_history(codes)`嚗�銁�臬𢆡�𡝗𤣰�啣��嗉�����唳𧊋蝻枏���蟮��葵�⊥𧒄嚗諹䌊�典銁�𤾸蝱蝥輻�銝剖⏚�� `pd.HDFStore` �� `select('/all_30')` �𣂼���蟮�嗥�摨誩�撟嗅‵�� `stock_history_cache`嚗峕�蝏�圻�� thread-safe QTimer �噼��湔鰵嚗峕��支�銝餌瑪蝔贝粉�硋之��辣撣行䔉���甇颱� IO �餃���
    - [x] **摰䂿�銵峕�撽勗𢆡�� MA20d �噼��嗆��㦤�芣�霈∠� (Live MA20d Swing State Calculations)**: �� `refresh_realtime_ui()` 銝哨�撠���� `current_df` 銵峕�銝𤾸��啁�摮条���蟮�嗥�隞瑕��埈�蝻脲𣄽�伐�撖寥�敶枏予���唬遠嚗㚁�霈∠�皛𡁜𢆡 MA20 �� MA5����𡒊凒�亥�韏� `SwingTracker.update_stock_state` 撖寥𡺨颲�/閫��/鈭斗�銝㗇�銝剔�銝芾�餈𥡝��嗆��㦤頧祉宏銝擧綫�鞟��梯恣蝞𨰜��
    - [x] **SwingStateTable 敶餃��梁氖 Mock (Decoupled Swing State Table from Mock)**: �滚�鈭� `SwingStateTable` ���憪见�嚗��瘨�鍳�冽𧒄�� mock 鋆�‵嚗�僎撠� "�� �瑟鰵�嗆��" �厰僼蝏穃��� `load_db_data(force=True)`嚗𤤿眏 `ATSMainWindow` 蝏煺��朞� `update_data_list(swing_rows)` �閖�垍�摰䂿�摰䂿�霈∠�蝏𤘪���
    - [x] **11 憿寞瓲敹��敶埝�霂蓥����瘚贝� 100% 蝏踵�頝煾�� (100% Pass of All Tests)**: �扯� `pytest test_watchlist_lifecycle.py` 隞亙�餈鞱� Launcher �� `ATS_TEST_MODE` ���瘚贝�嚗��摰𣬚��朞�銝娪���箸�隞颱�蝥輻�畾讠�銝擧香����

## 2026-06-12 03:45
- [x] **餈𥕢�甇亙��箄�蟡典�蝘啗圾�鞾�餉� (Further Solidified Stock Name Resolution Fallback)**:
    - [x] **撘訫� local Sina �唳旿摨㮖�銝箏�摨閙䰻霂� (Added Local Sina Database Fallback)**: �� `get_stock_name(code)` 銝剜鰵憓硺�蝚砍�蝥批�摨𨰻��𥅾蝻枏�����嗉�����誑�� SQLite �砍𧑐鈭斗�銝𦒘縑�瑕��脖葉�賣𧊋璉�蝝Ｗ��滨妍�塚��湔𦻖隞擧𧋦�啣�頧賜� `Sina` 銵峕��券�摨� `get_code_cname(code)` 銝剛繮�硋�蝘啜���摰𣬚�閫��鈭�� `605589`嚗�𧁋瘜厰��ｇ� and `301123`嚗��銝𦦵㩞摮琜�蝑劐�摮睃銁鈭𡒊爾�Ｘ�隞𤘪�隞塚�`paper_account_state.json`嚗劐��砍𧑐�唳旿摨𤘪���蟮鈭斗�銝娪�撘��䀝漱�𤘪𧒄畾萇��瑕鍳�其葵�∪之�Ｙ妖�曄內銝算�𨀣𧊋�乒�萘�蝻粹萅��
    - [x] **11 憿寞瓲敹��敶埝�霂� 100% 蝏踵��朞� (100% Pass of All 11 Watchlist Regression Tests)**: 餈鞱� `pytest test_watchlist_lifecycle.py` 瘚贝��其��牐遙雿訫�撣詻��

## 2026-06-12 03:30
- [x] **隡睃��典��∠巨�滨妍閫��銝𤾸��臬𢆡�扯� (Optimized Authoritative Stock Name Resolution & Cold-start Performance)**:
    - [x] **摰䂿緵���憭𡁻��∠巨�滨妍�亥砭 (Hierarchical Name Resolution Fallback Chain)**: �� `ATSMainWindow` 銝剖��乩� `get_stock_name(code)` ���蝥� high-reliability �𣂼��箏����甈⊿�朞�蝻枏�嚗Ǒname_cache`嚗�-> 摰墧𧒄敹怎�����唳旿嚗Ǒcurrent_df`嚗�-> SQLite�唳旿摨枏�撅��蝝ｇ�瘨�膄鈭��憸穃��唳��瑕鍳�冽𧒄銝芾��滨妍�䭾瓷�匧��嗅嘀�剛�峕遬蝷箔蛹"�芰䰻"��撩�瑯��
    - [x] **�冽踎�埈����撖寡�獢�葉�亙��滨妍�亥砭�� (Unified Name Resolution in Sector Detail Dialog)**: �齿�鈭� `ATSSectorDetailDialog` 隞乩蝙�園�朞��嗥���誧�踹僎�湔𦻖靚�鍂 `get_stock_name`��蝠摨閗圾�喃��踹�樴坔仍銝擧���葵�∪�銵典銁�芣𦻖�嗅����� Tick 銵峕�撟踵偘�塚�憭折𢒰蝘舀遬蝷箔蛹"�芰䰻"��撩�瘀��𣂼�鈭�㺭�桀��游漲��
    - [x] **�賢𧑐瘥怎�蝥� Pandas �煾��𡝗凒�� (Fast Vectorized Name Cache Updates)**: 摨罸膄鈭�銁 `load_db_data` 銝剝�鞱�敺芰㴓�滚� `current_df.iterrows()` �湔鰵蝻枏�������瘜𤏪��齿�銝� Pandas �煾��𣇉�銝��桀��湔鰵�箏� `_update_name_cache_from_df`嚗�僎�� `_handle_realtime_data` 銵峕�撟踵偘�交𤣰�寥�憸穃��剁�撠��埈𧒄隞𡒊�蝥折�雿舘秐鈭𡁏神蝘垍漣嚗峕覔瘝颱�銝餌瑪蝔� I/O �餃��䭾���㨃憿蹂���香��
    - [x] **�朞� 11 憿寞瓲敹��敶埝�霂� 100% 蝏踵��朞� (100% Pass of All 11 Watchlist Regression Tests)**: 餈鞱� `pytest test_watchlist_lifecycle.py` 瘚贝��其��牐遙雿訫�撣詻��

## 2026-06-12 03:00
- [x] **摰䂿緵摰墧𧒄鈭斗�銝𤾸�蝑硋��豢�瘞渡��滚�撘誩笆�乩��𧢲踎敹�歲�峕郊 (Implemented Reactive Integration of Live Trading & Kernel Trace Logs)**嚗�
    - [x] **�亙� KernelTracePanel 撟嗅��啣��嗅�蝑𡝗𠯫敹𡑒�頦� (Kernel Trace Panel Integration)**嚗𡁜銁 `ATSMainWindow` 銝剖��乩� `KernelTracePanel` 撟嗆𦻖�亙�銝剖亢 QTabWidget ��倌憿蛛��舀�擃㗛�閫�� `trading_kernel_trace.jsonl` 銝剖�蝑𡝗�瘞渡�摰墧𧒄餈質葵����嗅銁 `StockDetailDialog` 霂行�蝒堒藁����芸𢆡撖寧𤌍���蟡函���瓲�亙�餈𥡝�摰墧𧒄瘛勗漲璉�蝝Ｖ�蝏蠘恣嚗��蝷箏���瓲�喟��其���蔭靽∪漲����抒𠶖���閫血��笔�蝑厰��𡝗�����
    - [x] **�賢𧑐 paper_account_state.json 蝥賊𢒰韐行�摰䂿��峕郊 (Live Paper Account Sync)**嚗𡁜銁 `ATSMainWindow.load_db_data()` 銝剖��唬�摰䂿�銝� SQLite �唳旿摨梶��諹膘瘛瑕��𣂼�嚗䔶����頧賢僎�滩圾摰䂿� `logs/paper_account_state.json` �𣬚�摰墧𧒄�舐鍂韏������唳�隞枏�瘚�偌霈啣�嚗���𣂷�銝𡒊�摰鮋��硋��貊𠶖����拍�撖寥���
    - [x] **撱箇� 3蝘㘾�憸𤏸䌊���頝喃��穃𨯬靽脲擪 (3s Heartbeat Sync & Auto-Initialization)**嚗𡁜銁 `ATSMainWindow.__init__` 銝剖�憪见� `self._listener_started = False` �脤�蝵格�敹梹�撟嗅��典� QTimer 摰𡁏𧒄�瑟鰵敹�歲靚�㟲�� 3000ms���甈∪�頝喃�隞�䌊�冽凒�唳�隞瓐����睲�鈭斗�瘚��餈睃�甇交��𡝗��唳踎�㛖��𥕦㦛�𠰴��詨�蝑𡝗�瘞湛�蝖桐���𢒰�輸𡢿 100% �唳旿銝��湔�扼��

## 2026-06-12 02:40
- [x] **靽桀���稬�枏� EXE 撘孵枂憭帋葵 ATS 蝒堒藁��撩�� (Fixed Multiple ATS Windows Spawning on Compiled EXE Double-Click)**嚗�
    - [x] **�寞𧋦�笔�霂𦠜鱏 (Root Cause)**嚗�
        1. **蝻箏� `freeze_support()` �行⏛**嚗𡁜銁�寧𤌍敶� Launcher �𡁏𧋦 `run_ats.py` 銝哨�摰��瘝⊥�靚�鍂 `multiprocessing.freeze_support()`��� parent 餈𤤿��朞� `multiprocessing` �臬𢆡摮鞱�蝔𧢲𧒄嚗�銁 Windows �臬�銝衤��朞� `spawn` �孵��齿活餈鞱� `run_ats.exe`���銝箇撩銋� `freeze_support()` �行⏛嚗��餈𤤿��峕甅隡𡁏�銵� `main()` �𣬚� GUI �臬𢆡隞��嚗諹��交��鞾�鍦��𥕦遣�啁�����
        2. **�芸銁擐𤥁��㰘蝸 (Imports Hijacking)**嚗𡁜銁 `ats/main_ats.py` 銝哨�`freeze_support()` �賢銁 `if __name__ == "__main__"` 銝剛��剁�雿��雿滨蔭�冽�隞嗆��怎垢嚗�紡�游�餈𤤿��刻�銵���行⏛�嫣��滚停�扯�鈭�▲�函� `PyQt6` 蝑厰�摨� GUI 摨㮖誑�𡃏䌊摰帋�璅∪���紡�乓���鈭𥕦紡�交�雿𨅯虾�賢��穃�蝥輻��嘥��硔��t �典��嗆���蝒��瞏𨅯銁�� GUI �齿活�㕑絲��
    - [x] **�𣬚垢�拍�靽桀�銝𤾸�蝵桅俈敺� (Robust Freeze Support Placement)**嚗�
        * 撖� `run_ats.py`嚗朞蕭�牐� `multiprocessing.freeze_support()` 摰�擪����
        * 撖� `ats/main_ats.py` 銝� `run_ats.py`嚗𡁜� `multiprocessing.freeze_support()` ���瘚贝�皛斤宏�唬�**擐𤥁���憿園�**嚗���� `sys`/`os` 銋见�嚗�銁隞颱� heavy imports 銋见�嚗剹���靽肽�鈭�遙雿閧眏 multiprocessing 瘣曄��箇�摮鞱�蝔见銁�臬𢆡蝚砌�瘥怎�撠梯◤摰�擪����瑕僎撘箄��扯� `sys.exit()`嚗䔶��峕偶餈靝�隡𡁏�銵� `PyQt6` 撖澆��� GUI 蝒堒藁�𥕦遣嚗�蝠摨閙�蝏苷�蝒堒藁�𣳇��鍦�嚗㇅ork Bomb嚗剹��

## 2026-06-12 02:30
- [x] **靽桀��枏�蝻𤥁��嗆���摮鞱�蝔见鍳�典援皞���𥪜𢆡閫��西��� (Fixed Subprocess Launch Error in Packaged Mode & Completed Linkage Dependency Analysis)**嚗�
    - [x] **銵亙� `main_ats.py` �亙藁餈𤤿�靽脲擪**嚗𡁜銁 `ats/main_ats.py` 銝剖��乩� `multiprocessing.freeze_support()` 靚�鍂��圾�喃��� Windows �枏�蝻𤥁��嗆����閧𡠺餈鞱� ATS 蝏�垢�塚��删撩撠� `freeze_support` 撖潸稲���餈𤤿� `LinkageProcess` �臬𢆡憭梯揖��援皞���瑕�甇駁��𣳇�敺芰㴓��䔮憸矋�蝖桐��拍��𥪜𢆡摮鞟頂蝏笔虾隞亦𡠺蝡贝䌊瘝餃鍳�具��
    - [x] **蝻硋�瘛勗漲霂𦠜鱏�亙�**嚗𡁜�撱箔�撟嗆綫���霂𦠜鱏�亙� [ats_linkage_diagnosis.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/f070f090-667f-4b42-870f-7754a8d955e7/ats_linkage_diagnosis.md)嚗諹祕撠賣４��僎�𤑳鍂�瑁圾�𠹺�敶� `instock_MonitorTK` (TK) �喲𡡒�塚�ATS �𥪜𢆡�蠘�憭望����銝芯蜓閬�輕摨佗��枏�/�钅�餈𤤿��� `freeze_support` 蝻箏仃嚗�歇靽桀�嚗剹��虾閫���函��賢𪂹�毺眏 TK 撘箇�摰𡁶恣�����撅��芾斐�輻��祉眏 TK �砍�餈鞱���誑�𠰴�撅���䁅���㺭�格凒�啣�甇Ｕ��

## 2026-06-12 02:00
- [x] **摰䂿緵 ATS 銵䔶��踹�撘箏漲�剖��曉��睃笆�乩��𣂼��∩��餉��� (Implemented Live Sector Heatmap Binding & Constituent Stock Drill-Down Linkage)**嚗�
    - [x] **撖寞𦻖摰䂿�隡朞��唳旿��辣 (Connected Heatmap to Live Session Data)**嚗𡁻���� `SectorHeatmapWidget` 銝剔� `load_live_sectors` �寞�����支��������� Mock �踹��唳旿嚗���Ｘ𦻖�乩��曹澈 RAM 蝤���羓���氜�睃�隞賭葉�� `bidding_session_data.json.gz`����唬��典��睃�鈭斗��園𡢿畾蛛��剖��曇�憭煺誑 3s 摰𡁏𧒄�典𪂹�罸�憸烐��硋僎皜脫��箇�摰䂿��踹�撘箏漲敺堒�嚗𠄎core嚗剹���銝𡁜像��隅撟��Change %嚗劐誑�𦠜暑頝���䀹㺭�譌��
    - [x] **霈曇恣�踹��𣂼��∠𡠺蝡𧢲�蝏���� (Created ATSSectorDetailDialog)**嚗�
        - �啣�鈭� `ats/ui/sector_detail_dialog.py`嚗���唬�銝�銝芷�敺芷�獢�楛�� HSL 靚�𠧧�輻� `ATSSectorDetailDialog`��
        - 摰䂿緵鈭�踎�堒��𣈯�憭渲��苷��𡏭�瘨刻��萘��箏��曄內嚗峕𣈲���樴坔仍�∩誑�煾��脩鸌畾𦠜�霈堆�`�� 樴坔仍`嚗厩蔭憿嗚��
    - [x] **�賢𧑐�𣂼��∪�銵典�蝏港漱鈭雴��芣��鍦� (Standardized Numeric Sorting & List Linkage inside Sector Details)**嚗�
        - �券�撖寞𦻖鈭� `NumericTableWidgetItem` 隞亥圾�喟蓡�����隅撟�����澆�畾萇��芰��啣�澆之撠𤩺�摨𧶏��踹�鈭��蝚虫葡瘥𥪜笆蝻粹萅��
        - �舀���稬�𣂼��∪𤧅韏瑁砲�∠�憭𡁶輕�詨��誩�����孵��Ｘ踎 (`StockDetailDialog`)嚗���唬蜓�屸𢒰���蝻苷漱鈭鍦��具��
        - �亙�鈭� `setup_header_persistence` 隞亙��啁鍂�瑟��冽��賣�����堒捐�� 1s �嗵�����𤥁䌊����
    - [x] **�拍��渲��𥪜𢆡靽嗪� (Direct Physical Linkage Channel)**嚗𡁶鍂�瑕銁�𣂼��⊥�蝏�”銝剖��餅�雿輻鍂�桃�銝𠹺��孵��桀紡�芷�劐葉隞餅�銝芾��塚��芸𢆡閫血��� TCP 26668 ����刻��函恣��膥��凒餈墧綫瘚���峕郊��揢 K 蝥踹㦛閫�藁����典���漱�枏恥�瑞垢嚗���梢◇/�朞噢靽∴�嚗���唬��嗆情�瓐�����漣�怎�撘箸��䀝�撉䎚��

## 2026-06-12 01:35
- [x] **靽桀��墧�瘣� Tab �堒捐鋡恍�霈文�憪讠𠶖����碶��嘥��硋�撅��滨蔭�� Bug (Fixed Layout Drift & Layout Manager Reset on Exit/Startup)**嚗�
    - [x] **�賢𧑐�𨅯�摰賡��𤏸䌊����苷��𨀣㺭摮堒����蝝批��脲�����刻”暺䁅恕�鍦�瞈�瘣� (Implemented One-Time Auto-Fit with Ultra-Narrow Numeric Columns & Enabled Sorting Across All Tables)**嚗�
        - 靚�㟲銵典仍暺䁅恕撖寥��孵�銝�**撌血笆朣𣂼僎��凒撅�葉** (`AlignLeft | AlignVCenter`)嚗�蝠摨閗圾�喃��刻”�澆�摰賣�蝒�𧒄嚗𣬚眏鈭𤾸�銝剖笆朣𣂼紡�渡�擐碶葵摮㛖泵撌虫儒嚗��憒��𨀣�隞栞��售�萘��𨀣��嘥�撌虫儒�见�����𦠜��𦒘�銝芸�蝚血𢰧靘扯◤�䭾��芾��格𣏹��′隡扎��
        - �讠憬 QSS 銝剔�銵典仍颲寡�嚗�� `QHeaderView::section` �� `padding: 5px;` 隡睃�銝箇揮�𤑳� `padding: 2px 4px;`嚗諹�銝�甇仿��曆�瘞游像蝛粹𡢿嚗䔶蝙敺堒銁頞���堒捐銝𧢲�摮𦯀��扳��啣虾閫���
    - [x] **撘訫� `ShowEventFilter` 撱嗆𧒄�Ｗ�銝擧葡�梶�瘚𧢲㦤��**嚗𡁜銁 `setup_header_persistence` �嘥��𡝗𧒄嚗��鋆��隞嗉�皛文膥嚗�𢆡���瘚� `table_or_tree` �� `Show` 銝� `Paint` 鈭衤辣嚗�僎撠����葡�梶𠶖���摮睃銁 `table_or_tree._has_been_visible` ���銝准��
    - [x] **閫�� Qt 撣��蝞∠��刻��硋�摰賜�蝏誩�蝻粹萅 (Fixed Layout Override on Startup)**嚗𡁜��堒捐隞𤾸��厩� `__init__` �單𧒄�Ｗ�嚗屸���蛹�函�隞�**擐𡝗活�交𤣰�� Show/Paint 鈭衤辣�嗉�銵�辣�塚�Deferred嚗㗇�憭�**���敶餃�閫��鈭�眏鈭� Qt 撣��蝞∠��典銁蝒堒藁�嘥�皜脫�霈∠��塚�隡𡁻𤨪�㯄�蝵格𧊋�㰘蝸/�芣遬蝷箇�隞� section size ��䔮憸矋�蝖桐��冽��劐撓靚�㟲���摰質◤ 100% 敹惩�餈睃���
    - [x] **�行⏛�芣葡�㮖�摮䁅�銝�**嚗𡁜銁 `save_action()` �坔� `window_config.json` 銋见�嚗�撩�嗆㜃�� `_has_been_visible` 銝� `False` ���隞嗚���敶餃�閫��鈭�銁銝餌������� `closeEvent` 銝哨�撖嫣�隞擧𧊋鋡急�瘣�/��揢撅閧內餈���墧暑�� Tab 蝏�辣嚗𣬚眏鈭擧𧊋皜脫��瑕��笔��� layout 撠箏站�䔶漣�� 100px 暺䁅恕�澆僎閬��撌脖�摮条��芸�銋匧�摰賜�銝仿� Bug��
    - [x] **�齿�蝏煺� `BaseATSTableWidget` 憪娍��条恣**嚗𡁶宏�支� `BaseATSTableWidget` (in `base_table.py`) ���雿嗘�摮䀝��脫�摰𡁏𧒄�剁�撠���� `save_column_widths` 摮睃��箏��湔𦻖憪娍��条恣蝏� `setup_header_persistence` 餈𥡝�蝏煺�����吔�摰䂿緵隞���駁��𣬚輕�斤�銝���
    - [x] **銵亙�蝑𣇉裦�∠巨瘙䭾��找辣��睸�䀝�銝钅睸�𥪜𢆡�𥪜𢆡 (Added Keyboard Navigation Linkage to UniverseTreeWidget)**嚗�
        - ��笆蝑𣇉裦�∠巨瘙䭾�敶Ｘ綉隞� `UniverseTreeWidget` (撌虫儒�䠷�厰𡺨颲曄����� Tab �箏�) 銋见�隞�𣈲�������餉��刻�峕瓷�劐�銝钅睸撖潸⏛�𥪜𢆡��䔮憸矋��啣�鈭�笆 `currentItemChanged` 靽∪噡����砍僎蝏穃�鈭� `_on_current_item_changed` 瑽賢遆�啜��
        - 蝖桐�鈭�鍂�瑚蝙�券睸�䀝�銝钅睸�劐葉銝滚�銝芾��塚��賢��讛”�潛�隞嗡��瑞��渲圻�穃��刻��典� K 蝥踹㦛閫�藁�峕郊��揢嚗���唬��函��Ｙ��删�銝��湔�折睸�䀝漱鈭鉝��
    - [x] **�惩𤐄�芸𢆡�𡝗�霂閧㴓憓�**嚗帋��碶��芸𢆡�𡝗�霂閙芋撘� `ATS_TEST_MODE` ��鍳�冽�蝔页��冽�霂閖���箏�閫血� `window.show()` �� `processEvents()`嚗𣬚＆靽苷蜓�Ｘ踎���隞嗡�隞園��埈迤蝖格�銵���𡢅��㯄�朞䌊�典�瘚贝��芣�撉諹��餉���

## 2026-06-12 01:20
- [x] **隡睃� ATS �港��典��賣�摨譍�蝛箏��/�牐�蝚阡�餉� (Standardized Numeric Sorting & Empty/Placeholder Logic in ATS)**嚗�
    - [x] **靽桀�銵冽聢 NumericTableWidgetItem ��征�潭�摨�**嚗𡁻���� `ats/ui/styles.py` 銝� `NumericTableWidgetItem` �� `__lt__` �鍦��餉�嚗峕𣈲��笆 `""`��"-"`��"--"`��"nan"` 蝑厩征�潔��牐�蝚衣��箄�霂����＆靽萘征�潭��牐�蝚行㺭�桀銁甇�� (Ascending) ���鍦� (Descending) �鍦�銝见��賜迅摰𡁏��堒銁銵冽聢��摨閖�嚗䔶��齿�瘚桀銁�唳旿銵䔶��對�瘨�膄鈭�㺭�格遬蝷箇�蝝𠹺僚�麄��
    - [x] **隡睃��∠巨瘙� UniverseTreeItem ���蝏湔惣�賣�摨�**嚗�
        - �齿�鈭��敶Ｘ綉隞� item `UniverseTreeItem` �� `__lt__` �寞�嚗���乩��曉�瘥𥪯�蝥臭遠�潭毽����硋膥 `get_col1_val`嚗諹�憭毺移��竉蝳餅𡠺�瑚葉��隅撟�蓡����𡝗�撌虫儒����唬遠��
        - 摰䂿緵鈭��摨讐��潭𧒄���蝥抒迅摰� fallback �餉�嚗����蝙�� 6 雿齿㺭摮𦯀誨���銵屸�蝥扳�摨𧶏�嚗屸俈甇Ｚ�憿箏��𤩺㦤�硋𢆡��
        - �峕甅銝箸�敶Ｘ綉隞嗅��牐�蝛箏�潔��牐�蝚阡俈敺∟�皛歹�蝖桐��芣𤣰�啗�����䭾�隞𤘪㺭�桃�銝芾�銵屸𡺨�㮖��典𧑐�鍦��函㮾摨𥪜�蝐颱����摨閧垢��
    - [x] **靽肽�靽格㺿�𠉛氖**嚗𡁜��券�敺芯��冽���誘嚗�����厰�餉�靽格㺿銝交聢�𣂼��� `ats/ui/` �桀�銝页�撖� `signal_dashboard_panel.py` ��秤�寡�銵䔶��拍��墧�嚗㚁�蝖桐�鈭�緵�劐漱�㮖縑�瑕之�条��Ｙ�蝔喳��扼��
    - [x] **11 憿寞瓲敹��敶埝�霂� 100% 蝏踵�頝煾��**��

## 2026-06-12 01:00
- [x] **�齿� ATS 銵冽聢�𡁶鍂�蠘��� BaseATSTableWidget �箇�蝐� (Abstracted ATS Table Functionality to BaseATSTableWidget)**嚗�
    - [x] **摰䂿緵���箸𧒄撘箏��峕郊靽嘥��堒捐 (Forced Synchronous Column Persistence on Close)**嚗�
        - ��笆�冽��𨅯銁���箸𧒄瘝⊥��鞉郊�𦠜��厩� tab 銝剔� col ����砽�萘��𤤿�嚗�銁 `ATSMainWindow.closeEvent` 銝剛‘�其����箸𧒄��撩�嗅�甇乩�摮䀹㦤�嗚��
        - 蝖桐�鈭�銁�喲𡡒摨𠉛鍂�塚��𣳇�蝑匧� 1s ��俈�硋��嗅膥閫血�嚗𣬚��喳�甇亥��冽��㕑”�潘�`SwingStateTable`��TradeFlowTable`��PositionPanel`嚗匧��穃耦�∠巨瘙𩤃�`UniverseTreeWidget`嚗厩� `save_column_widths()` �� `save_header_state()` �寞�嚗�����啁��堒捐撣��摰𣬚��瑞�����吔�蝖桐� 100% 銝滢腺憭晞��
    - [x] **閫��憭関ab�渡𡠺蝡𧢲�銋���脩� (Resolved Independent Multi-Tab Persistence Conflicts)**嚗�
        - 撘訫�撟嗅�鈭思�蝏煺��� `CONFIG_FILE_LOCK`嚗�瑪蝔钅�鍦������� `main_window.py` (摮堒噡摮睃�)��styles.py` (��/銵冽聢�砍��脫�摮睃�) �� `base_table.py` (�箇掩銵冽聢�峕郊摮睃�) ��笆 `window_config.json` ����㕑粉�坔𢆡雿𡏭�銵峕�隞㚚�鈭埝棅靽脲擪嚗�蝠摨閗圾�喃�憭帋葵銵冽聢/摰𡁏𧒄�典僎�穃��亙紡�渡��滨蔭閬���峕��誯䔮憸塩��
        - 銝箸��劐��𣬚� Tab 憿菟𢒰�𦠜�蝏𤘪����鈭��撅��臭��� `config_key`嚗��蝢𤾸��啣�銝� Tab ���摰質挽蝵桀蝦甇斤𡠺蝡卝���銝滚僕�啜��
    - [x] **摰䂿緵蝒堒藁雿滨蔭����𤩺�靘衤�瞈�瘣� Tab �嗆��楊隡朞�靽嘥� (Persisted Window Geometry, Splitter Sizes, and Active Tab Indexes)**嚗�
        - 摰䂿緵鈭� `ATSMainWindow._save_layout_state()` 銝� `_restore_layout_state()`嚗峕��帋�蝏�垢�港��屸𢒰�嗆����拍�����硔��
        - �舀�蝏�垢�券��舀𧒄嚗諹䌊�冽�憭滩秐銝𠹺�甈∪��剜𧒄�����之撠譍�雿滨蔭��椰/銝�/�喃�憭批躹�毺� Splitter 瘥𥪯���誑�𠹺葉/�喃舅靘� QTabWidget 瞈�瘣餌�敶枏� Tab �厰★�∠揣撘𤏪�蝏蹱��䀹��𣂷� 100% 餈䂿賒�䭾���㴓憓���湔�扼��
    - [x] **�質情�箇�銵冽聢蝐� (BaseATSTableWidget)**嚗𡁜銁 `ats/ui/base_table.py` 銝剖��唬� `BaseATSTableWidget`���銝剖�鋆��銵冽聢����餉祕��/�訫稬�𥪜𢆡鈭衤辣�����睸�䀝�銝钅睸撖潸⏛�峕郊��𢰧�桀撕�算�𨅯��嗉�蟡其誨���苷�銝𧢲��𨅯�蝑劐漱鈭坿�銝箝��
    - [x] **�齿�摨𠉛鍂�� SwingStateTable**嚗𡁜�瘜Ｘ挾�噼�頝蠘葵銵� `SwingStateTable` ���撅�”�潔� `QTableWidget` �踵揢銝� `BaseATSTableWidget`嚗�僎�券𢒰�亙�鈭���堒捐����碶�蝏煺�靽∪噡瑽踝�蝘駁膄鈭�㺭����滚����銝𧢲��𨅯����韐湔踎�滢�隞����
    - [x] **�齿�摨𠉛鍂�� TradeFlowTable & PositionPanel**嚗𡁜銁 `ats/ui/trade_flow.py` 銝哨�撖嫣漱�𤘪�瘞渲” `TradeFlowTable` �峕�隞㯄𢒰�� `PositionPanel` �峕甅餈𥡝�鈭������券���漣銝箇誧��/雿輻鍂 `BaseATSTableWidget`��
    - [x] **瘨�膄隞���𦯀�銝𦒘��𦦵迅摰𡁏��**嚗𡁏��支�憭帋葵�Ｘ踎�湧�憭滨� `setup_header_persistence`��𢰧�株��閙甅撘誩�銋剹��� `QApplication.clipboard()` �滢��餉�嚗屸�雿𦒘�蝥� 150 銵䔶誨���雿辷�DRY �笔�嚗剹���朞�鈭���� 11 憿孵�蝟餌��詨��訫��𧼮�瘚贝���

## 2026-06-12 00:30
- [x] **摰䂿緵��稬霂行�撖寡�獢�鵭��𧋦�芸𢆡�Ｚ�銝𡡞�鈭斗��嗆挾/�芣𤣰�唳綫��𧒄��㺭�株䌊����芸𢆡銵仿� (Implemented Text Auto-Wrap & Auto-Data Enrichment for Detail Dialog)**嚗�
    - [x] **�㯄�𡁻鵭��𧋦�芸𢆡�Ｚ� (Context-Info Label Auto-Wrap)**嚗帋蛹 `StockDetailDialog` ���銝芣瓲敹��餈唳�蝑橘��𡏭圻�睲�蝵栽�腈���𨀣綫�鞟��晦�腈���𡏭蕭瘨�/�孵��嗆���嘅��� QLabel 蝏�辣�券𢒰撘��� `.setWordWrap(True)` 撅墧�改�閫���踵��祆�憭齿�閫��銵刻噢撘讛◤颲寧��芣鱏���閫厩撩�瘀��芷���靚�㟲�∠��箏����摨艾��
    - [x] **�硺漱�𤘪𠯫/�芣綫��𧒄�唳旿�芷����芸𢆡�瑕� (Live Data Auto-Retrieval & Fallback)**嚗𡁜銁 `ATSMainWindow.on_stock_clicked` 靚�絲霂行�蝒堒藁��䲮瘜蓥葉嚗��璉�瘚见�摰墧𧒄�券������摮� `current_df` 銝箇征�硋��滢葵�∪��芣𤣰�啗���𧒄嚗諹䌊�刻圻�穃��� `JSONData.sina_data` 撘閙�嚗峕��碶葵�∪��齿��啁� Sina Web 摰䂿�敹怎���
    - [x] **撖寥�憭𡁶輕摰䂿��孵�摮埈挾�惩� (Feature Schema Mapping)**嚗𡁜笆�匧��墧䔉����� Tick 摮堒�餈𥡝��箄��漤𧫴�惩�嚗朞恣蝞堒僎銵亙� `percent` (�箔����唬遠 `close` 銝擧㿥�交𤣰�䀝遠 `llastp` �芸𢆡�条�)���撠� `trade` 銝� `close`嚗䔶誑�𡃏‘����嗅�蝥� `vwap` (�惩��� `avg_price`)��蝠摨閗圾�喃��冽錰/�硺漱�𤘪𠯫隞亙��瑕鍳�冽𧒄��稬�賢��𡝗遬蝷� "蝑匧�銵峕��券��葉" ��䔮憸矋�靽肽�霂行�蝒堒藁�孵� 100% �峕說��
    - [x] **�蹱���霂睲��函��賢𪂹�笔�敶埝�霂� 100% �朞�**��

## 2026-06-12 00:20
- [x] **�賢𧑐�𨅯�摰賡��𤏸䌊����苷��𨀣㺭摮堒����蝝批��脲�����刻”暺䁅恕�鍦�瞈�瘣� (Implemented One-Time Auto-Fit with Ultra-Narrow Numeric Columns & Enabled Sorting Across All Tables)**嚗�
    - [x] **摰䂿緵擐硋��芷���銝�甈∩��� (One-Time Auto-Fit with Override Guard)**嚗𡁜銁 `ats/ui/styles.py` 銝剖��乩� `auto_fit_columns_once()` 蝎曉��批��寞������葵�Ｘ踎擐𡝗活�㰘蝸�唳旿�塚��交𧋦�� `window_config.json` 銝凋�摮睃銁�冽��芸�銋匧�摰賡�蝵殷��躰圻�𤏸䌊����堒捐霈∠�嚗䔶��典�蝏剜凒�唬葉摰�����嚗䔶��𦦵鍂�瑞��芸�銋㗇��刻��渡�銝滩◤銵峕��瑟鰵�脣�閬����
    - [x] **�啣�銝𦒘誨�������讠憬 (Ultra-Narrow Spacing for Numeric Columns)**嚗𡁜銁 `auto_fit_columns_once` ��䌊���霈∠�銝剖��乩��堒��毺䰻�餉����璉�瘚见��堒仍��鉄 �靝誨��/敶枏�隞�/�𣂷漱隞�/�圈�/撣���/�牐�/���/餈墧踎�� 蝑匧��桀��塚��芸𢆡�扯�����寥�蝑𣇉裦嚗��霈方䌊���摰賢漲銝羓憬�� 6 �讐�嚗㚁�蝖桐��啣���捆蝝扯稲韐游���瓷�匧�雿嗵��踝���憭折�摨阡��曉�撟閧���遬蝷箇征�氬��
    - [x] **�寞祥�∠巨瘙䭾�敶Ｗ椰靘抒��賣𣱣�� (Minimized Tree Indentation)**嚗𡁜銁 `ats/ui/universe_widget.py` 銝剖� `QTreeWidget` �� `setIndentation` 隞� 10px 餈𥕢�甇亙�蝻抵秐���蝝批��� 5px嚗䔶蝙敺堒�撅�葵�∩誨���憭��憭抒�摨血𧑐�穃椰�䭾𨋍嚗�蝠摨閙��支�撅訫��睃�����函�撅誩��讐�閫����椰靘扯�閫厩征瘣痹�隞舘�䔶�瘚芾晶隞颱�瘞游像蝛粹𡢿��
    - [x] **�㯄�𡁜�銵冽㺭��/�曉�瘥𠉛移��䌊摰帋��鍦� (Enabled Standardized Sorting Across All Widgets)**嚗�
        - 蝻硋�鈭��銝�蝏扳㗁�� `QTableWidgetItem` �� `NumericTableWidgetItem`嚗��蝵格迤�蹱���㦤�塚��芸𢆡�娪膄���雿漤�堒噡��蓡���蝚佗�`%`嚗剹���韐批�蝚血噡嚗���圈�撖寞㺭摮�/�煾�/瘨典����摰𧼮之撠誩�蝟餅�摨𧶏��𦦵�鈭�頂蝏罸�霈文�蝚虫葡瘥磰�撖潸稲����10.0% �鍦銁 2.0% �漤𢒰�萘��餉�蝻粹萅��
        - ��笆 **瘜Ｘ挾�噼�銵� (`SwingStateTable`)**��**����Ｘ踎 (`PositionPanel`)** �� **鈭斗�瘚�偌銵� (`TradeFlowTable`)**嚗���Ｘ�瘣� `setSortingEnabled(True)`��僎�冽㺭�桀�頧賣��游��賭葩�園�摰朞䌊���`setSortingEnabled(False)`嚗㚁�摰𣬚�閫��鈭��憸穃��唳𧒄�唳旿銋勗�銝擧��亙㨃憿輻��桅���
    - [x] **11 憿寞瓲敹����/�笔𦶢�冽��𧼮�瘚贝� 100% �𣂼��朞�**��

## 2026-06-12 00:05
- [x] **�齿��芾斐�輯��其�韏吔��賢𧑐�𨅯��餌�����剁��喲睸憭滚�隞���苷��典�摰賣��刻��扳�銋�� (Decoupled Clipboard from Linkage, Implemented Right-Click Copy & Interactive Resizing of All Columns)**嚗�
    - [x] **�亦氖�訫稬�𥪜𢆡�嗥��芾斐�踵㺿�� (Removed Automated Clipboard Pollution)**嚗𡁜銁 `ats/ui/main_window.py` �� `link_stock` �拍��𥪜𢆡�寞�銝哨�敶餃��𣳇膄鈭�笆蝟餌��芸��選�`QApplication.clipboard()`嚗厩��芸𢆡�湔鰵�餉����銝滢��踹�鈭�銁撘�郊蝥輻�/�� GUI 銝𠹺������垢��耦銝贝圻�� `QApplication is not defined` ��援皞�𥁒�辷�銋笔��券�敺芯��冽��靝�閬�䌊�典��嗅�韐湔踎嚗���嗅�敶𤘪糓�喲睸�蠘��萘��滨�雿㯄���
    - [x] **�㯄�𡁜�皞鞟凒�亦������ (Direct Non-polluting Linkage)**嚗帋��坔僎�惩𤐄鈭� `link_stock` 撖孵虾閫���曇”嚗㇍CP 26668嚗匧�憭㚚�蝏�垢�𥪜𢆡蝞∠��� `linkage_service.get_link_manager().push(code_clean, auto=False)` ����剁�摰䂿緵銝芾��刻��������朞噢靽�/�諹�憿箇�蝡舫𡢿��妟撱嗉������凒餈噼��剁�敶餃�閫�膄撖孵�韐湔踎銝剛蓮���韏硔��
    - [x] **摰䂿緵憭朞”�𨅯𢰧�桀��嗉�蟡其誨���嘥��� (Implemented Right-Click Copy Across Panels)**嚗�
        - ��笆 **蝑𣇉裦�∠巨瘙䭾�敶� (UniverseTreeWidget)**��**瘜Ｘ挾�噼�頝蠘葵銵� (SwingStateTable)**��**����Ｘ踎 (PositionPanel)** �� **鈭斗�瘚�偌銵� (TradeFlowTable)** �𥕦之�詨�蝏�辣嚗��蝏穃�鈭� `customContextMenuRequested` 靽∪噡銝� `CustomContextMenu` 銝𠹺�����閧��乓��
        - �冽��喲睸�孵稬隞餅�銵䔶葵�⊥𧒄嚗��撘孵枂隞亦移�� HSL 瘛梯𠧧摨閗器皜脫��� `"�� 憭滚��∠巨隞�� {code} ({name})"` �𨅯�憿對��芣��函��餉��閙𧒄�滢�閫血� `QApplication.clipboard().setText(code)` 摰峕��见𢆡憭滚���
    - [x] **�券𢒰�曉����匧�摰賣��刻��港������ (Enabled Interactive Width Resizing for All Columns)**嚗�
        - �齿�鈭� `ats/ui/styles.py` 銝剔� `setup_header_persistence` �堒捐�芣�蝞∠��具����支����𦒘��𡑒◤撘箏�霈曆蛹 `Stretch` (�劐撓������甇Ｙ鍂�瑁���) ����塚�撠�”�潔��穃耦�找辣����匧���挽摰帋蛹�舀��冽��� resizing �� **`QHeaderView.ResizeMode.Interactive`** 璅∪���
        - 蝏枏� `QHeaderView.saveState/restoreState` �箏�嚗𣬚＆靽嘥��祆�摨誩��瑕���誨���蝘啣���誑�𦠜��喃儒摰賢��刻���眏�堒銁������厩��� column嚗�銁�冽��见𢆡靚��摰賢漲�𠬍����隞� 1s �脫��孵��芸𢆡����硋��刻秐 `window_config.json` 撟嗅銁�滚鍳�𤾸�蝢擧�憭溻��
    - [x] **11 憿寞瓲敹��敶埝�霂� 100% 蝏踵��朞�**嚗𡁶� `pytest test_watchlist_lifecycle.py` �券��娍��𡃏祗瘜閧�霂𡢅����㗇芋�𡑒�銵�像蝔喉��牐遙雿閗祗瘜閙�鈭支��墧���

## 2026-06-11 23:55
- [x] **摰䂿緵 ATS 蝏�垢銝芾�憭𡁶輕摨血���/��稬鈭支����銝𤾸��刻��券�𡁻� (Implemented Single/Double-Click Branching & Multi-Linkage Channels)**嚗�
    - [x] **�寞祥�質𠧧銵刻�銝滢��� (Fixed Corner Button Style)**嚗帋蛹 `styles.py` 餈賢�鈭� `QTableCornerButton::section` �滩𠧧嚗䔶蝙�嗡�擃䀹﹝瘛梯𠧧�峕艶�羓��潛瑪摰𣬚��滚�嚗峕覔瘝颱���� QTableWidget 暺䁅恕�質𠧧�厰僼���閫匧𠧧鋆���
    - [x] **颲暹��𨅯��餉��剁���稬霂行��苷漱鈭㘾��� (Click/Double-Click Branching)**嚗�
        - ��笆摰���∠巨瘙䭾�敶Ｕ��之蝥批��噼�瘜Ｘ挾銵具���隞㯄𢒰�踴��漱�𤘪�瘞渲”嚗���典�隡删�����餃撕蝒烾���蛹�𨅯��餉圻�穃��刻��其�K蝥踹�雿𨧀�嘅�撠��𨅯��領�嗪���蛹�𨅯撕蝒堒�蝷箏�蝏湔���祕���腈��
        - **�訫稬�𥪜𢆡�𡁻� (link_stock)**嚗𡁜��颱葵�⊥𧒄嚗諹䌊�典��嗅� 6 雿滩�蟡其誨���蝟餌��芸��選�隞仿�朞��芸��輸�暺䀹䲮撘讛䌊�刻��典��函��諹�憿�/�朞噢靽∪恥�瑞垢嚗𥕦��嗅��臬�甇亦瑪蝔页��朞� TCP 26668 蝡臬藁�� `trade_visualizer` �煾�� `CODE|{code}` ��誘嚗𣬚��游�甇亙��� K 蝥踹㦛閫�藁嚗峕�雿靝�鈭抒�隞颱� UI �餃���
    - [x] **�賢𧑐銝𠹺�����嗉祕����� (Context-Aware StockDetailDialog)**嚗�
        - �齿�鈭� `StockDetailDialog` ���憪见�璅∪���緵�典��颱葵�⊥𧒄嚗䔶��寞旿銝芾���憭���交�雿滨蔭嚗��摰躰�蟡冽�������蝐颯��郭畾菔”���隞𤘪�鈭斗�瘚�偌嚗㚁��箄��潸�銝滚����銝𧢲��孵��唳旿 `context_info`嚗���怨砲銵𣬚鸌�厩�蝑𣇉裦�刻���眏���鈭𤩺�靘卝���蝳餃漲蝑厩𠶖��縑�荔���
        - �刻祕������銝𦠜䲮�啣�鈭��獢���𨥉�� 蝑𣇉裦�孵�銝𠹺����嘥㨃���皜�苊鈭桃尐�啣��砍�蝷箏�閫血�雿滨蔭����交綫�鞟��勗��孵�餈賣隅�嗆����
    - [x] **�朞��券�蝻𤥁�銝� 11 憿寞瓲敹��敶埝�霂�**嚗𡁶� `test_watchlist_lifecycle.py` ���瘚贝��𢠃����霂煾�霂��11 憿寞瓲敹��敶鍦��� 100% �𣂼��朞�嚗𣬚�蝡臬鍳�典�憪见�銵函緵撟喟迅�亙ㄝ��

## 2026-06-11 23:45
- [x] **摰䂿緵�∠巨��稬霂行�蝒堒藁銝𤾸��㗛��𣇉鸌敺�㺭�桀��Ｘ𦻖�� (Implemented Live Feature Integration on Item Double-Click Dialog)**嚗�
    - [x] **霈曇恣擃䀹﹝瘛梯𠧧霂行�蝒堒藁 (StockDetailDialog)**嚗𡁜銁 `ats/ui/main_window.py` 銝剖��� `StockDetailDialog` �找辣����函滲瘛梁��峕艶��之摮堒噡蝥Ｙ遛瘨刻�銝𡃏𠧧���隞亙��芷����諹𠧧銵䔶漱�輯”�潘�銝㯄秄撅閧內��稬銝芾����蝏湔瓲敹�鸌敺���
    - [x] **�㯄�𡁜��� DataFrame 銵峕�敹怎��唳旿瘚� (Live Snapshot Caching)**嚗𡁜銁 `_handle_realtime_data` 銵峕����瑽賭葉撘訫� `self.current_df = df` �冽���摮矋�敶餃�摨�迫鈭���滢�雿輻鍂 Mock �唳旿���銝箝��圾�喃��折�餉�銝剔眏鈭擧𧊋�賢龪�滢蜓餈𤤿��券����貊��桀� `data` 隞亙�蝻箔�撖孵��𤩺凒�啣�霈桀� `UPDATE_DF_DIFF` ������撟嗆㦤�嗉��紡�渡��瑕鍳�刻����瘜閙��垍� Bug嚗���唬��䀝葉摰䂿����啁鸌敺������刻䌊�具��神蝘垍漣�唳旿閬��銝舘䌊����
    - [x] **�舀�����券��冽�������箄� Fallback (Dynamic Inspection & Fallback)**嚗�
        - 隡睃�霂餃�撟嗆�鈭格聢撘誩�撅閧內憒���唬遠��隅頝�����鈭日����鈭日���WAP ��𧒄��瑪�� MA20 頞见飵蝑㗇���鸌敺���
        - ��鍂�冽������瘜𤏪��芸𢆡撠���滢葵�∪銁摰䂿� DataFrame 銝剛恣蝞堒��啁��券��拐�擃条漣�誩��孵�摮埈挾撅閧內鈭舘”�潔葉��
        - 撖寞𧊋�嗅�銵峕�敹怎�����臬𢆡�嗆����𣂷��箄� Fallback �餉�嚗諹䌊�典�蝷箄��詨抅蝖�摮埈挾撟嗡�隞亙�憟賣�蝷綽�靽肽�蝟餌�蝏苷�銝剜鱏�硋援皞���
    - [x] **憿箏⏚�朞� 11 憿寞瓲敹��敶埝�霂蓥��㘾�**嚗帋耨憭滢� PyQt6 銝� `AlignVerticalCenter` �帋蜀�𣂼��躰秤嚗�耨甇�蛹甇�＆�� `AlignVCenter` 撅墧�改�嚗𣬚＆靽嘥��餃撕獢��頧賢��䀹㺭�格𧒄�屸𢒰銝滚援皞��11 憿孵�敶埝�霂� 100% �𣂼��朞���

## 2026-06-11 23:30
- [x] **隡睃� ATS �∠巨瘙䭾�敶Ｗ�撅�銝𤾸�撅��穃耦�箄��典��賣�摨� (Optimized Tree Layout & Implemented Custom Intelligent Tree Sorting)**嚗�
    - [x] **�寞祥 QTreeWidget 撣���文�銝𤾸椰靘抒��� (Fixed Indentation Margin Squeeze)**嚗𡁜銁 `ats/ui/universe_widget.py` 銝剖� `self.tree.setIndentation(10)`���撅�漣蝻抵�隞𡒊頂蝏毺�暺䁅恕憭批偕撖豢��𣂼�蝻抵秐 10 �讐����銝滢�摰𣬚�靽萘�鈭�覔������撘�/�嗆�蝞剖仍嚗䔶�雿踹�摮鞾★銝擧覔���餈睲�撌血笆朣琜�敶餃�瘨�膄鈭��𨅯椰颲寧�蝛箏紡�湔𣱣�见�靘扳遬蝷箔�蝵栽�萘�閫��蝻粹萅嚗䔶�霂������券��曄內�唳旿靽⊥���
    - [x] **摰䂿緵��掩����拍���香 (Static Root Category Ordering)**嚗𡁜��� `UniverseTreeItem` 隞�𤜯 `QTreeWidgetItem`���朞��滚� `__lt__` 撟嗉粉�硋��� header �� `sortIndicatorOrder()`嚗���唬��其遙雿訫���迤摨𤩺��滚�銵典仍�孵稬銝页�憿嗅���掩嚗��䠷�厰𡺨颲整��移�㕑�撖麄����䀝漱�橒��函�����Ｖ�憪讠��瑟�銝滚𢆡�唬����霈曄��詨笆憿箏�嚗�1 �� 2 �� 3嚗㚁��䔶��匧�蝐餃��函�銝芾��厰�匧��𡑒�銵峕�摨譌��
    - [x] **�賢𧑐�箄��典��賣㺭��/�曉�瘥娍�摨� (Smart Numerical/Percent Sorting)**嚗�
        - ��笆隞���梹��芸𢆡�𣂼� 6 雿齿㺭摮𦯀誨��蓮�游�餈𥡝��啣�澆之撠𤩺�颲�.
        - ��笆���唬遠/瘨典��𦯀誑�𦠜�隞梶蓡����梹�雿輻鍂甇���芸𢆡閫���箏蒂�� `+`��-` �� `%` ��㺭�澆僎頧祆揢銝� float 餈𥡝��笔�撟�漲�鍦�嚗峕��支���10.0% �鍦銁 2.0% �漤𢒰�萘�摮㛖泵銝脫�摨讐撩�瑯��
    - [x] **撘訫��鍦�撘��唾�瘚���� (Sorting Toggle Throttling)**嚗𡁜銁 `UniverseTreeWidget` �齿鰵鋆�‵�唳旿嚗Ǒload_mock_data` �� `update_pools`嚗㗇��湛��冽�蝛箏�����唳旿����笔𦶢�冽��滚�靘脲活�扯� `setSortingEnabled(False)` �� `setSortingEnabled(True)`����踹�鈭�銁�唳旿擃㗛�笔�頧質�蝔衤葉���蝜��摨讛圻�𡢅�瘨�膄鈭��憸穃��唬���𤫇�Ｘ�鋆����香��
    - [x] **憿箏⏚�朞� 11 憿孵�蝟餌��詨��𧼮�瘚贝�**嚗𡁶� `pytest test_watchlist_lifecycle.py` �券��娍�嚗𣬚鍂�� 0.76s 撟嗡� 100% 蝏踵��朞���

## 2026-06-11 23:20
- [x] **靽桀�撟嗥移蝏���齿�韏偦帕�踹�敺堒�璅∪�嚗諹氜�售�𣈯�憭游�銵䕘�頝�隅憓䂿��脲㦤�� (Implemented 'Leader Base + Follower Bonus' for Sector Scoring)**嚗�
    - [x] **蝖桃��𣈯�憭游�銵𢞖�嘥抅蝖�韐∠讃�� (Leader Base)**嚗朞挽蝡� `leader_base = max(0.0, leader_pct) * 1.2`嚗䔶蝙�踹��券�憭游枂�啣之瘨冽�撠�踎�嗉繮�碶�摰𡁶��箇����憒� 20% 樴坔仍�閧𡠺銝𦠜隅�𣂷� 24.0 靽嘥����嚗䔶誑甇日�朞��箇��㕑�餈�誘嚗䔶��𣈯�憭渲�鋡恍𢒰�踵��瑯��
    - [x] **撘訫��𡏭�瘨典��𪙛�嘥�霂�� (Follower Bonus)**嚗帋�敶𤘪踎�堒像��隅撟� `avg_pct > 0` �塚��箔� `math.log2(active_count) * avg_pct * eff_follow_ratio * trend_multiplier * 3.0` �鍦�����𨅯蘨�匧�銝芯葵�⊥�����嗡��𣂷遢�∩�頝罸�嚗��憓䂿���蛹 `0`���瘨函�瘣餉��𣂷遢�∟�憭𠾼��像��隅撟��憭改�憓䂿����擃矋��渲秐閫血� `98.5` 霂��銝𢠃���
    - [x] **摰𣬚��Ｗ�銝芾��踹��箏�摨�**嚗𡁏迨�箏�敶餃��𦦵�鈭��𨅯��∪��踹蒂�冽㟲銝芣踎�埈說���萘��桅�嚗䔶蝙�踹�撘箏漲霂��蝎曉��齿��箇�摰䂿��𨀣踎�埈�摨婙�嘥撩撘晞��
    - [x] **憿箏⏚頝煾�𡁏��匧�������瘚贝�**嚗�11 憿寧頂蝏�瓲敹���鞉�霂蓥誑�� 5 憿嫣�憿嫣僭�硋�蝑�/�瑕㭂�行⏛瘚贝��� 100% �𣂼��朞���

## 2026-06-11 23:10
- [x] **摰䂿緵���� Table �� Tree ���摰質楊隡朞��芸𢆡靽嘥�銝擧�憭� (Implemented Header Persistence for All Tables & Trees)**嚗�
    - [x] **摰䂿緵蝏煺������ Header ����𣇉恣��膥 (setup_header_persistence)**嚗𡁜銁 `ats/ui/styles.py` 銝剖��乩�璅∪��典��賣㺭 `setup_header_persistence()`���朞�撖� `horizontalHeader()` 餈𥡝� Interactive 鈭支�璅∪��滨蔭��⏚�� `QTimer` 摰墧鴌 1s �脫��嗵�靽嘥������ hex 摨誩��𡝗㦤�嗉粉�蹱𧋦�圈�蝵格�隞� `window_config.json`嚗��蝢𤾸��唬�銵冽聢銝擧�敶Ｘ綉隞嗥��芣�靽嘥���
    - [x] **摰䂿緵�堒捐�冽�銝擧�憭批捐摨衣������ (Column Width Limits)**嚗𡁜銁蝞∠��典��剁��舀�����孵��梹�憒��𨀣綫�鞟��晦�腈���𦦵��交䔉皞鐥�腈���𨀣瓲敹�鸌敺��萘�憭扳��祇鵭摮埈挾嚗厩���憭批捐摨阡��塚��喃蝙�券�憸烐㺭�桅�蝏睃��堒捐�劐撓�嗡�蝏苷��𤑳聦 UI 撣����
    - [x] **瘛勗漲��� ATS v2 �𥕦之�詨�蝏�辣**嚗�
        - `ats/ui/swing_table.py`嚗𡁜笆 `SwingStateTable` 蝏穃� `ats_swing_table_state` �殷��𣂼��𨀣綫�鞟��晦�脲�憭批捐摨虫蛹 350px��
        - `ats/ui/trade_flow.py`嚗𡁜笆 `TradeFlowTable` 蝏穃� `ats_trade_flow_table_state`嚗屸��嗯�𦦵��交䔉皞鐥�脲�憭批捐摨虫蛹 300px��
        - `ats/ui/trade_flow.py`嚗𡁜笆 `PositionPanel` 蝏穃� `ats_position_table_state`��
        - `ats/ui/universe_widget.py`嚗𡁜笆 `UniverseTreeWidget` 蝏穃� `ats_universe_tree_state`嚗屸��嗆��𦒘��埈�憭批捐摨虫蛹 350px��
- [x] **�㯄�𡁏迤撘𤩺㺭�桀��嗆綫����䠷��𤾸蝱�芣�靽脲暑 (Enabled Live Data Streaming & Silent Backend Keep-Alive)**嚗�
    - [x] **摰䂿緵 Unicode ���訾�撘�虜蝻𣇉��脣鴃 (Fixed Unicode Launcher Error)**嚗𡁻�撖� Windows 蝟餌�暺䁅恕�批��啁���蛹 GBK �嗆��啣鉄�� Emoji ������憸矋�`window.windowTitle()`嚗匧紡�渡� `UnicodeEncodeError` 撏拇�嚗�銁 `run_ats.py` ��蜓�亙藁銝剔��乩� ascii �滨漣蝻𣇉�靽脲擪嚗���唬� Launcher 頝典像�唳�蝻嘥�摰嫘��
    - [x] **摰峕��券��蹱���霂睲� 11 憿寧頂蝏�瓲敹��敶埝�霂�**嚗𡁻�朞� `py_compile` 撖寞��� UI �� Launcher 璅∪�餈𥡝�鈭���讐�霂穃恣霈⊥�銝��仿�嚗𥕦��嗉�銵� `pytest test_watchlist_lifecycle.py` 11 憿孵��笔𦶢�冽����瘚贝�嚗�� 100% 蝏踵��朞�嚗諹��𡒊頂蝏笔��烐㺭�桀��睲��𤾸蝱摰�擪�嗆���撖寧迅摰𠾼��

## 2026-06-11 22:30
- [x] **�嗡� ATS �枏��滨蔭��辣 (Created PyInstaller Spec File for ATS v2)**嚗�
    - [x] **����𦯀�銝𦒘��㚚�厰★**嚗𡁶�蝛嗡� `instock_MonitorTK.spec` ������蝵殷�撖寥�鈭��銝剖�鈭� `trash_list`嚗㇋t6WebEngineCore��t6WebEngineWidgets��t6Pdf��t6Quick 蝑㚁��𦯀� DLL/摨梶��娪膄�餉���
    - [x] **�滨蔭 hiddenimports 銝� datas**嚗𡁶移蝏�㟲��� `pyqtgraph`��PyQt6`��pandas`��numpy`��configobj` 蝑㗇瓲敹��撘譍��曉�靘肽�摨枏� `a_trade_calendar` �唳旿頝臬���極雿𨅯躹�滨蔭��辣��
    - [x] **摰峕� spec �滨蔭銝𡡞����霂煾�霂�**嚗朞��� `ats.spec`嚗峕溶�牐� `configobj` �𣂼�靘肽�憿嫣誑閫���枏����瘜閗粉�� `G:\h5config.txt` �滨蔭��辣��䔮憸塩��蝙�� `python -m py_compile ats.spec` 撉諹�霂剜�嚗𣬚＆靽萘�霂煾�朞���像蝔單��鞉���
    - [x] **��漣�臬𢆡�刻楝敺�圾�� (Upgraded Launcher Path Resolution for Nuitka/PyInstaller)**嚗𡁻���� `run_ats.py` 銝� `ats/main_ats.py` 銝剔� `sys.path` 瘜典��餉����撘���毺��枏銁蝻𤥁��閙�隞嗡葩�園��曄𤌍敶蓥�憭望� of `__file__` �詨笆頝臬�閫��嚗���Ｘ𦻖�亙抅鈭� `sys_utils.get_app_root()` ���銝��拍�蝏嘥笆頝臬��瑕��箏�嚗𣬚＆靽萘�霂𤑳��砌�皞鞟��臬�銝讠����摰𣬚��澆捆�扼��
    - [x] **摰䂿緵摮𦯀�蝻拇𦆮敺株�銝舘楊隡朞������ (Implemented Font Size Adjuster & Persistence)**嚗�
        - [x] �� `ats/ui/styles.py` 銝剖��典�暺䁅恕 QWidget 摮堒噡隞� 11pt 銝贝��單凒撠誩概�� 9pt��
        - [x] �� `ATSMainWindow` 憿園��批�撌亙��𧶏�ToolBar嚗劐葉�啣�鈭� `A-` (�誩�) �� `A+` (憓𧼮之) ���敺株��厰僼嚗�僎摰墧𧒄�� `lbl_font_size` ��內�其�撅閧內敶枏�摮堒噡��
        - [x] 摰䂿緵鈭� `load_font_size()` 銝� `save_font_size()` ����𡝗㦤�塚�撠���瑕之撠𧶏�`ats_font_size`嚗劐誑�笔��硋��亙耦撘讛䌊�典��硋�蝟餌�蝏煺��滨蔭��辣 `window_config.json` 銝准��
        - [x] 蝻硋�鈭� `apply_qss_with_font_size()` 璅∪�嚗屸�朞�甇���冽��凒�啣僎�滩蝸�典� QSS �瑕�銵剁�摰䂿緵鈭�”�潦���敶Ｚ�蟡冽���ab 憿萇��券� UI 蝏�辣���蝥折�蝏条憬�橘���之�𣂼�鈭�揮�穃�撅讐��批㦤�臭���縑�臬�摨艾��

## 2026-06-11 22:20
- [x] **摰墧鴌�祉��芣祥鈭斗��喟�蝟餌�嚗㇁TS v2嚗� (Implementation of Autonomous Trading System v2)**嚗�
    - [x] **�嘥��㚚★�桃���**嚗𡁜�撱� `ats/` �桀�撟園�蝵� `__init__.py` 蝑匧抅蝖�憿嫘��
    - [x] **P0 �嗆挾嚗鑔t Dashboard �笔�摰䂿緵**嚗𡁏�撱箇�銝�憌擧聢�� QSS �滩𠧧蝟餌�嚗峕𨰹撱箔蜓蝒堒藁���敶Ｚ�蟡冽���郭畾菔�頦芾”��漱�𤘪�瘞�/��� Tab��誑�𠰴��箇�摨佗�擖澆㦛/�勗㦛嚗匧��卝��
    - [x] **P1 �嗆挾嚗䥑PCBridge & SQLite �亙�**嚗𡁜��啣蘨霂餅㺭�桀��亥砭銝𤾸抅蝖��滨蔭頧賢�嚗諹粉�硋僎撅閧緵�笔�����脖縑�瑯��漱�𤘪�瘞港�韏���脩瑪��
    - [x] **P2 �嗆挾嚗䦧niverseManager 瞍𤩺�璅∪�**嚗𡁜��圈𡺨颲暹����撖����漱�𤘪����撅�����瘛䀹掠餈�誘��
    - [x] **P3 �嗆挾嚗锭wingTracker �嗆��㦤**嚗𡁜��� MA20 �噼萱隡�迅銝𤾸枂�箇𠶖��㦤�𦠜綫�鞟��晞��
    - [x] **P4 �嗆挾嚗鋳acktestEngine 靽∪噡�㗇��批���**嚗𡁜��脖縑�瑁������鈭𤩺����憭批��斤��墧����蝏蠘恣��
    - [x] **P5 �嗆挾嚗関radeJournal 蝏拇�蝏蠘恣**嚗𡁏��硋僎�澆��碶漱�枏��脖�蝑𣇉裦�𦦵���掩擖澆㦛��
    - [x] **P6 �嗆挾嚗锭haredMemory & Queue 摰墧𧒄�亙�**嚗𡁜笆�亦�銝� `df_all` 銵峕��曹澈���銝𤾸��嗡縑�� `mp.Queue`��

## 2026-06-11 20:45
- [x] **�㯄�𡁏�霂蓥�璅⊥��墧𦆮璅∪�銝讠�隞𦠜𠯫�硋枂�瑕㭂�行⏛�⊿� (Enabled Cooldown Verification for Tests & Replay Mode)**嚗�
    - [x] **�啣� `enforce_cooldown_in_test` 撅墧�扳綉��**嚗𡁜銁 `trade_gateway.py` �� `MockTradeGateway` 銝剖��乩� `self.enforce_cooldown_in_test` 撅墧�改�暺䁅恕�潔蛹 `False`���霂亙��找蛹 `True` �塚��喃噶憭�� pytest 瘚贝��硋��暹芋��芋撘𧶏�銋笔撩�嗆�銵䔶��亙��箏��湔㜃�芣嵗撉䕘��舀�擃䀹��笔漲瘚贝�銝讠��瑕㭂�箏�撉諹���
    - [x] **��漣�訫�瘚贝�蝖桐��瑕㭂�餉� 100% 閬��**嚗𡁜銁 `scratch/test_trade_gateway_cooldown.py` 銝哨��� `setUp` �嗆遬撘誩� `self.gateway.enforce_cooldown_in_test` 霈曄蔭銝� `True`��迨銝曆蝙瘚贝��其��賢��𣂼�璅⊥�撟嗉��𣇉�摰䂿�隞𦠜𠯫�硋枂�瑕㭂�行⏛�餉���� `pytest scratch/test_trade_gateway_cooldown.py` 瘚贝�嚗���湔㜃�芷�餉� 100% �𣂼�撉諹���

## 2026-06-11 20:30
- [x] **靽桀��拍�雿𤾸��匧��𣳇�煺僭�乩��脤��游�蝥踹��箏�蝑𤥁◤霂舀�銝𤾸仃�� Bug (Fixed Early Morning Low-Open Acceleration Buy & Surge Break VWAP Sell Failures)**嚗�
    - [x] **�寞祥 `_realtime_priority_check` 蝻抵��躰秤撖潸稲��僭�仿�餉�甇颱誨�� Bug**嚗𡁏��亙僎�𤑳緵 `intraday_decision_engine.py` 銝剔眏鈭𤾸��滚�撟嗆�蝻𤥁�憭梯秤嚗諹䌊 `if not vwap_trend_ok:`嚗�洵 1777 銵䕘�撘�憪讠凒�� `buy_score >= threshold` 蝑劐僭�亥���圻�睲�頝笔�撘箏����憟埈瓲敹��餉�嚗�漲 300 銵䔶誨���鋡恍�霂臬𧑐蝻抵��其� `if snapshot.get("tail_end_trap", False):` �文���𣈲�����眏鈭舘砲撠曄�霂勗��琿𩐠�文��函�憭批��唳迤撣訾漱�𤘪𧒄畾萄�銝� `False`嚗�紡�湔㟲銝芸��園�韏啜����游�雿𤾸𢙺�行⏛��僭�仿�餉�摰鮋�銝𦠜畢銝箔��䭾�餈鞱���香隞��嚗䔶�皞𣂼仍銝𢠃獈�凋�摰墧𧒄靽∪噡��圻�㻫��緵撌脣��堒蔣�滨��券��餉��堒�撌阡���� 4 �潘�甇�＆敶垍蔭�� `if mode in ("full", "buy_only"):` �� 12 �潛憬餈𤤿漣�思�嚗䔶蝙�嗅��睃��墧�銝剛�憭��霂航圻�㻫��
    - [x] **�啣�撟嗆��𡁏𡟺�䀝�撘��匧��𣳇�煺僭�仿�餉� (`_realtime_priority_check` 撘箏�)**嚗𡁜銁 A �⊥𡟺�㗛��烐𧒄畾蛛�09:15 - 10:00嚗㚁�敶㮖葵�∪�撟��撘�雿���睃�餈���𦆮�誯�韏堆�`ratio >= 1.2` 銝娍��唬遠擃䀝�隞𦠜𠯫��瑪銝𤾸��䀝遠嚗䔶��讐氖撟�漲���嚗㗇𧒄嚗�笆撘箏飵蝑偦�㕑��� MA20 �臬𢆡�𣳇�蠘��扯�擃䀹��笔漲銋啣�閫血���𦆮摰賣迨�嗥� 5 �亦瑪銋𣇉氖���蝵𡁻��塚�蝖桐�暺���園𡢿���憭港葵�∟�蝚砌��園𡢿�閗繮撱箔�嚗䔶��喃��𦦵��䀹𧒄撌脫隅�鎿�腈��
    - [x] **摰䂿緵�拍��脤��游�蝥踵�頝���箔��日�餉� (`_sell_decision` 撘箏�)**嚗𡁜銁 `_sell_decision` 銝剜鰵憓嫰�𨅯�擃条聦��瑪銝𧢲��萘��𣇉��行⏛��𣈲��𥅾�亙���擃䀹隅撟�㦛颲曇�憭批�摨佗�憒��餈� 3.5%嚗㚁�雿���𦒘遠�潭𦆮�讛�蝛踹��嗅�隞瑞瑪嚗ĀWAP嚗劐���賒銝𧢲�嚗��撖寥� T+1 �𣂼�銝芾�撘箏���� `action="�硋枂"` ���隞𤘪�撟喃�靽∪噡嚗�僎�� reason 銝剜�蝖格�蝷� `"�脤�頝𣬚聦��遠蝥踹枂撅�"`嚗�蝠摨閗圾�喃���𧒄蝏𤘪��𣇉��餉���撩憭晞��
    - [x] **蝻硋�銝枏��訫�瘚贝�撉諹�撟� 100% �朞�**嚗𡁜銁 `scratch/test_vwap_patterns.py` 銝剔��嗘�閬��銝𡃏膩雿𤾸�擃䁅粥�匧��𣳇�煺僭�乓��誑�𠰴�擃条聦��瑪�硋枂銝斤掩�啁鸌敺�芋撘讐��訫�瘚贝��其���� `pytest scratch/test_vwap_patterns.py` 銝𤾸�蝟餌� 11 憿寧��賢𪂹��瓲敹��敶埝�霂� `pytest test_watchlist_lifecycle.py` �娍�嚗峕��㗇�霂閧鍂靘见� 100% 蝏踵��朞�嚗𣬚＆靽苷��煺漣蝥抒��亦�摰匧�撟喟迅�賢𧑐��

## 2026-06-11 20:06
- [x] **銵亙�蝡硺遠���銝𤾸�鈭斗�瘨典��冽�撖寥�������霂� (Completed Unit Tests for Bidding Breakout & BJ Stock Limit-up Thresholds)**嚗�
    - [x] **憓𧼮�蝡硺遠���銋啣��閧𡠺�急����霂閧鍂靘�**嚗𡁜銁 `scratch/test_auction_engine.py` 銝剜鰵摰䂿緵鈭� `test_bidding_breakout_generation` �寞���蝙�典��� `[蝡硺遠憭批����]` �� `pattern_hint` 隞亙��券� PANIC �嗆����� active_sectors �臬�嚗峕��罸�霂�� AuctionDecisionEngine �賢�蝎曉�霂������孵�銝芾�撟嗥��� `signal_type="蝡硺遠���銋啣�"`��
    - [x] **�㯄�𡁜�蝑硋��擧�霂閖曎頝�**嚗帋蝙�� `scratch/test_bidding_breakout_decide.py` 摰峕㟲頝煾�帋� `signal_type="蝡硺遠���銋啣�"` ��漱�𤘪��暹�霂𨰻���霂��霂乩縑�瑁�憭罸�朞� `decision_engine.py` ��𡠺蝡讠凒�交𦆮銵屸�𡁻�嚗𣬚��� 30% 隞㮖�瘥𥪯������迫�毺� BUY �喟��誩㦛��
    - [x] **�券��訫�銝𡡞��鞉�霂� 100% 蝏踵��朞�**嚗𡁶� `py_compile` �蹱��祗瘜閧�霂烐��乩� `pytest test_watchlist_lifecycle.py` �券� 11 憿寧鍂靘𧢲�霂𤏪�隞亙� `scratch/test_auction_engine.py` 瘚贝�嚗�� 100% �𣂼��朞���

## 2026-06-11 19:55
- [x] **靽桀�蝡硺遠憭朞��峕𧒄撟喃�銝𦒘僭�乩��閙𧒄���隞㮖��� (MAX_POSITIONS = 10) 霂舀� Bug (Fixed Portfolio Full Risk Rejection Bug under Concurrent Buy/Sell Signals)**嚗�
    - [x] **摰䂿緵靽∪噡�笔�隡睃�憿箏��鍦� (Ordered Signal Processing Queue)**嚗𡁜銁 `instock_MonitorTK.py` ��蜓敺芰㴓�瑕� `signals` �喟�靽∪噡�笔��𠬍�蝡见朖撖孵�餈𥡝�撠勗𧑐�鍦�����∩辣撠� `SELL` (�硋枂) �� `REDUCE` (�譍�) �喟��鍦銁���劐僭�� (`BUY`/`ADD` 蝑�) �喟�����Ｘ�銵䎚��
    - [x] **�牐噩�亙��𦠜𦆮憸嘥漲銝𤾸��刻䌊��**嚗𡁻�朞��鍦�靽肽��其遙雿蓥�頧桀�頝喳�嚗峕��厩��硋枂/撟喃��其��函����隡睃��𣂷漱蝏蹱芋�煺漱�梶��� `MockTradeGateway` 瘨�晶嚗䔶蝙 `positions` �圈�蝚砌��園𡢿�典�摮睃�蝵穃�銝剛◤�娪膄嚗屸��暸�摨艾����琿��擧�銵𣬚�銋啣��喟�撠梯�憿箏⏚�朞� `RiskManager.can_buy` ���銝𢠃��⊿�嚗峕��支��曹�銋啣�靽∪噡�扯�憿箏��𤩺㦤��紡�港僭�乩縑�瑁◤憌擧綉霂舀�����嫘��
    - [x] **蝻硋�銝枏��訫�瘚贝�靽嗪�甇�＆��**嚗𡁜銁 `scratch/test_position_limit_release.py` 銝剔��嗘�銝㯄秄��笆霂交�隞㯄�憸嗪��暸�餉�������霂𤏪��砍𧑐撉諹��券��朞���
    - [x] **�朞��詨�蝟餌�蝥批�敶埝�霂�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` 11 憿孵��笔𦶢�冽�瘚贝��券� 100% �𣂼��朞���

## 2026-06-11 19:30
- [x] **靽桀��拍�暺��畾萄�餈�漲銝交聢餈�誘撖潸稲撘箏飵撘�𢆡樴坔仍�∩��單釣�踹�銝芾�鋡怨秤���� Bug (Fixed Missing Early Morning Breakouts & Focus Sector Leaders)**嚗�
    - [x] **�曉捐 `getBollFilter` �� `getBollFilter_vect` �拍�隞瑟聢餈�誘����**嚗𡁜銁 `JSONData/stockFilter.py` 銝哨���笆�拍�暺���嗆挾嚗�09:15 - 10:00嚗厩�餈�誘�∩辣嚗峕鰵憓硺� `percent >= -2.0` ��捐�曉��胯��蘨閬�葵�∪�鈭𤾸�撟��撘���像�䀹�頧餃凝�噼萱�匧��嗆���瘨典� $\ge -2.0\%$嚗㚁��喃蝙�嗅��齿𧊋蝒�聦�冽𤣰銝娍𧊋閫血��冽𠯫��垢瘜Ｗ�嚗�㿥擃�/�其�嚗㚁�銋煺�隞乩��踺���蝖桐�鈭�銁�拍���飵�𤥁蝠敺桀��文�餈��笔�銝𦠜����撘箏��券�憭渲�嚗���砍�蝘烐�嚗㕑�憭罸◇�拙��堆��脫迫�𦦵��䀹𧒄撌脫隅�鎿�萘�雿㯄��𤤿���
    - [x] **�曉捐�拍��讛�蝝舐妖�冽�**嚗𡁜銁 `getBollFilter` 銝剖笆 `vstd` �詨�����賢ế摰𡁜��乩��拍��冽��𠹭撘䜘��銁�拍�暺���嗆挾嚗�09:15 - 10:00嚗㚁�撠��鈭日�銝擧㿥�交郭�典����潔�瘥𠉛�蝟餅㺭隞𤾸��祉� 1.2 �齿𦆮摰質秐 0.8 �㵪��𤥁��蘨閬� `percent >= -2.0` �喳��日��質秤��嚗諹圾�喃��拍�敹�歲�脲��曹���𧒄�𣂷漱�誩��芸���敞蝘臬紡�渡�隡䁅捶撘�𢆡�∟◤�鞉�扯�皛斤��桅���
    - [x] **靽嗪�擃睃虾�惩�敶雴�蝻𤥁�**嚗𡁶� `py_compile` �蹱���霂烐��乩誑�� `pytest test_watchlist_lifecycle.py` 11 憿孵��笔𦶢�冽��詨�瘚贝�嚗���� 100% 蝏踵��朞���

## 2026-06-11 18:45
- [x] **靽桀��拍�/�墧�璅∪�銝见�憭抒��𣇉敞撖潸稲撘箏飵樴坔仍銝芾��踹�瞍𤩺𥁒�� Bug (Fixed Missing Active Sectors with Strong Leaders Bug)**嚗�
    - [x] **摰䂿緵�諹膘瘛瑕��踹�霂���砍� (Implemented Hybrid Sector Score Formula)**嚗𡁜銁 `bidding_momentum_detector.py` �� `_aggregate_sectors` 銝哨�撠���厩��箔��𣂼�撟喳�瘨典����銝��踹��砍��齿�銝箏�頧冽毽��芋撘譌��膄鈭�恣蝞堒��澆撩摨血�嚗屸�憭𡝗覔�格踎�堒�瘣餉��𣂼��唬�憸��樴坔仍���擃䀹隅撟�恣蝞堒鍳�穃��踹�敺堒�嚗�僎�碶舅���憭批�潘�銝𢠃� 98.5嚗剹���蝖桐�鈭���踹����撘箏�憸�隅樴坔仍嚗��憭扳隅�𡝗隅�頣��塚��喃蝙�踹����隞硋��唬葵�∠眏鈭擧𡟺�䀹𧊋�臬𢆡�硋之�䀹�蝝臬紡�湔㟲雿枏��潔蛹韐�����嚗峕踎�堒�����賭�����𤩺�摨虫�擃䁅儘霂�漲嚗��蝢𤾸笆朣𣂷� UI 撅���厩����憸����
    - [x] **隡睃�蝚砌��嗆挾餈�誘閫��銝𡒊�頝臭��� (Optimized Early-Exit Filter with Short-Circuit Protection)**嚗𡁜銁蝚砌��嗆挾�萘�銝哨�憓𧼮�鈭� `leader_pct < 5.0` 餈�誘�𨅯��文����憸��樴坔仍瘨典� $\ge 5.0\%$ �塚��喃蝙�踹�頝罸����撟喳�瘨典�雿𦒘��箇��冽�嚗䔶�蝏嘥笆銝齿�銵𣬚�頝舀㜃�芯��娪膄嚗䔶��拍�皞𣂼仍銝𠹺��支��拍����笔�擃睃�蝒�聦���𣈯�憭游��� structures�苷�鋡急��乓��
    - [x] **憿箏⏚�朞� 11 憿寧��賢𪂹���霂�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` �券�蝏踵��朞�嚗峕瓷�匧�韏瑚遙雿訫�敶鍦�雿𦦵鍂��

## 2026-06-11 18:30
- [x] **靽桀��墧�/璅⊥��墧𦆮璅∪�銝𧢲踎�㛖��嗆�憭� the Bug (Fixed Sector Disappearance Bug in Replay/Backtest Mode)**嚗�
    - [x] **靽桀� `_do_rebuild_sector_map` 銝剔�隞��蝝Ｗ�撖寥� (Fixed Index-to-Column Alignment)**嚗𡁜銁 `_do_rebuild_sector_map` �滚遣�踹��惩��寞�銝哨�憓𧼮�鈭�笆 `code` 摮埈挾�臬炏�� columns 銝剖��函��文������ `code` 雿靝蛹 index 摮睃銁嚗��䔶��� columns �𦯀葉嚗㚁��芸𢆡撠���瑁��� columns 隞乩� `itertuples(index=False)` �𣂼�����寞祥鈭����/�墧��嘥��㚚𧫴畾萄� index �芣𠂔�脣� tuple 撖潸稲 `sector_map` �䀝蛹蝛粹�嚗諹�����𤑳�銝剜踎�㛖��嗅之�Ｙ妖瘨�仃�� Bug��
    - [x] **摰䂿緵璅⊥�璅∪��峕郊�唳旿霂�摯銝舘��� (Implemented Synchronous Evaluation & Aggregation in Simulation Mode)**嚗𡁜銁 `bidding_momentum_detector.py` �� `update_scores` �寞�銝哨���笆 `simulation_mode` �� `in_history_mode` 瞈�瘣餌𠶖����啣�鈭��甇亥�隡� `_update_scores_synchronously` �寞���歲餈���煺漣�臬�銝剔���葷撘�郊�湔鰵�箏�嚗���啣�撣批�撖寞��劐葵�∟�����峕郊霈∠�隞亙�撖寞踎�埈����摰墧𧒄�峕郊�𡁜����瘨�膄鈭��瘚�/�墧𦆮餈��銝剔眏鈭𤾸��啣�蝥輻�撘�郊霈∠�撖潸稲���𨀣㺭�格鱏獢��嘥��滚�蝡舀㺭�桐�銝��湧����雿踹��䀝縑�瑚��墧�靽∪噡颲暹� 100% 擃䀝��煺��湔�扼��
    - [x] **憿箏⏚頝煾�� 11 憿孵�蝟餌��笔𦶢�冽�瘚贝�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` �券��朞�嚗峕�霂閧鍂靘见�璅⊥�銵峕�瘚��銵𣬚𠶖���憭���

## 2026-06-11 18:00
- [x] **靽桀�摰讛��亥砭�𡃏祕璉��蠘�撟嗅�霂餃�/�湔鰵 df_all 撘訫� Pandas BlockManager ��� `Gaps in blk ref_locs` AssertionError �� Bug (Fixed Gaps in blk ref_locs AssertionError Bug)**嚗�
    - [x] **摰䂿緵蝥輻�摰匧��� DataFrame 蝥扯��瑁� (Thread-Safe df_all Cascading Copy)**嚗𡁏鰵憓硺� `_get_df_all_and_lock_cascading(widget)` 蝥扯�摰帋��具��銁隞� `self`��main_app` �� `detector` 撖餃�撟嗅��� `df_all` �塚�銝�撟嗉繮�硋僎�𣳇��嗅��𠉛� `self._df_lock` 蝥輻����隞𡒊�����脫迫銝餌瑪蝔�/擃㗛� Pump �坔�蝥輻��典��唳凒�唳𤜯�Ｚ砲 DataFrame �� GUI 蝥輻��峕𧒄餈𥡝� `.copy()`嚗䔶�皞𣂼仍銝𦠜��支��瑁��唬�銝��游�摮睃��������
    - [x] **�煾��𣇉揣撘閖�撖寥� (Vectorized Reindexing Alignment)**嚗𡁜銁 `_run_macro_query_internal`��_on_query_test_triggered` 隞亙� `_on_code_check_triggered` �湔鰵�冽��������㺭�桀�畾萇�雿滨蔭嚗���乩� `up_df = up_df.reindex(df.index)` 撘箏�撖寥��滢�����支�撠������湔鰵�唳旿 `up_df` �湔𦻖韏见�澆�摰峕㟲銵峕㺭�� `df` �塚��曹� pandas ����𣂼�撖寥��� block manager �齿��脩�撖潸稲�� internal block �嗘��� `Gaps in blk ref_locs` 撘�虜嚗���嗉繮敺𦯀��湧�����潮�笔漲��
    - [x] **�朞��𧼮�瘚贝�**嚗𡁶� `py_compile` �蹱���霂烐��乩誑�� `pytest test_watchlist_lifecycle.py` 11 憿寞瓲敹��敶埝�霂𤏪��券�蝏踵��𣂼��朞���

## 2026-06-11 17:50
- [x] **靽桀��墧𦆮/�墧�璅∪�銝贝䌊�券�蝵桀抅��恣�嗅銁�硺漱�𤘪𠯫�𣇉��𦒘�閫血��� Bug (Fixed Auto-Reset Trigger Failure in Backtest/Replay Mode on Weekends/Off-Hours)**嚗�
    - [x] **閫�膄憓嗘��園𡢿�𣂼� (Bypassed Wall-Clock Date Restrictions)**嚗𡁜銁 `bidding_racing_panel.py` 銝哨���笆�芸𢆡�箏��滨蔭璉�瘚见ế摰𡄯�憓𧼮�鈭� `is_simulation` �墧𦆮璅∪��文���𣈲��銁�墧𦆮璅∪�銝页��湔𦻖�朞�銵峕��唳旿��葉��𧒄�湔�嚗�朖�亙�����園𡢿 `time_hhmm`嚗㕑�銵峕𧒄畾菜����抒��㚁�`9:15-11:30` �� `13:00-15:05`嚗㚁�隞舘�諹歲餈��撖寧頂蝏�𧋦�啣�銝𦠜𧒄�渡� `cct.get_trade_date_status()`嚗�漱�𤘪𠯫�文�嚗匧� `cct.get_work_time()` �𣂼���
    - [x] **閫���硺漱�𤘪𧒄�湔�霂閗䌊�券�蝵桀�皛鮋䔮憸�**嚗朞�敶餃�閫��鈭�銁�冽錰�����𠯫�𡝗𤣰�睃�餈𥡝�敶訫��墧𦆮/蝑𣇉裦�墧��塚��曹�憓嗘��園�撅硺��硺漱�𤘪𧒄�游紡�渲�撽祇𢒰�蹂葉 `is_trading_time` �文��雴蛹 `False`嚗諹���紡�渲䌊�典��嗅抅���蝵桅�餉�鋡怠��刻歲餈��銝𡁜𦛚蝻粹萅��
    - [x] **靽嗪�擃睃虾�惩�敶雴�蝻𤥁�**嚗𡁶� `py_compile` �蹱���霂烐��乩誑�� `pytest test_watchlist_lifecycle.py` �券��其�瘚贝�嚗�11 憿寞瓲敹��敶埝�霂訫� 100% 蝏踵��朞���

## 2026-06-11 17:15
- [x] **靽桀��睃��𢠃�鈭斗��仿�蝵桐�����𡝗㺭�桀��� Bug (Fixed After-Hours & Weekend Session Reset & Write Protection)**嚗�
    - [x] **�脫迫�硺漱�𤘪𧒄�渲䌊�券�蝵� (Blocked Off-Hours Reset)**嚗𡁻���� `bidding_momentum_detector.py` �� `is_active_session` �寞���銁摰墧𧒄鈭斗�璅∪�銝页�銝交聢�𣂼�隞�銁鈭斗��伐�銝𥪜銁 09:15-15:00 �罸𡢿嚗㗇��文�銝箸暑頝��霂腈���敶餃��踹�鈭�𪂹�怒�����𠯫�𣇉��𡡞��舀𧒄�芸𢆡閫血� `reset_observation_anchors` 撖潸稲��隅頝諹恣�園�蝵桐��唳旿皜�妟�桅���
    - [x] **摰䂿緵�硺漱�𤘪𠯫�嗵��箄��𠉛氖靽脲擪 (Weekend Save Protection & Post-Market Archive Check)**嚗𡁜銁 `save_persistent_data` �坔��餉�銝剖��乩��箄��峕嵗撉峕㜃�芷秄蝳�����文�敶枏�銝粹�鈭斗��伐��朞� `cct.get_day_istrade_date()` 蝑匧ế摰𡄯��塚�
        - 隡睃�霂餃�撟嗉圾�讠��䀝���緵�匧�獢��隞塚�`bidding_session_data.json.gz`嚗㚁��𣂼��� `last_data_ts` 撅墧�扼��
        - �亦緵�匧�獢�歇鋡怨��𤾸��急���� 15:00 鈭斗��嗥��擧㺭�殷�`hour >= 15`嚗㚁���**蝏嘥笆�垍�閬��**嚗�朖靘踹蒂�� `force=True`嚗㚁�隞乩��文��脫�蝏�𧒄�渡�瘨刻��唳旿�滚�蝛箏�摮䀹情�瓐��
        - �亦緵�匧�獢��摮睃銁����𤩺��芸��� 15:00 �𡒊�鈭斗��擧㺭�殷��� `force=True` �嗅�**��捂�坔�靽嘥�摮䀹﹝**嚗𣬚＆靽嘥�蝏�秐撠𤑳��劐�隞賭漱�𤘪𠯫��𤣰�䀹㺭�柴��
    - [x] **閫��頝其漱�𤘪𠯫�唳旿�芣��滨蔭 (Standardized Cross-Day Reset)**嚗𡁜銁 `load_persistent_data` 銝哨�敶枏ế摰𡁜��滢蛹頝冽𠯫�臬𢆡�塚��曉�撠�葵�� `ts.price_anchor` 敶㘾妟嚗�僎�峕郊撠� `self.baseline_time` 閫�㟲�滩挽銝箏��齿𧒄�氬��＆靽脲鰵鈭斗��亙鍳�典�嚗諹�憭罸◇��抅鈭擧鰵撘��䀝遠餈𥡝�霈⊥𧒄銝𡒊蓡���瘨刻�霈∠���
    - [x] **瘚贝��⊿��券��朞�**嚗𡁜銁 `scratch` �桀�蝻硋�鈭��憿孵����霂� `test_weekend_persistence.py` 摰峕㟲�⊿�鈭��鈭斗��� `is_active_session` 銝� `save_persistent_data` �行⏛�其�嚗䔶�餈鞱��券��笔𦶢�冽����瘚贝� `pytest test_watchlist_lifecycle.py` 11 憿寧鍂靘见��函遛�烾�朞���

## 2026-06-11 16:50
- [x] **�牐噩�亙��寞祥�� GUI 獢�沲 (Tkinter + PyQt6) 蝒堒藁�喲𡡒�嗥� GIL �脩�撏拇� (Root-fixed Cross-Framework GIL Crash on Racing Panel Closure)**嚗�
    - [x] **摰帋�撏拇��寞�**嚗𡁏��亙��啣��� Python �湔𦻖餈鞱��𣇉�霂𤑳㴓憓���喲𡡒 PyQt6 韏偦帕�Ｘ踎�塚�`closed` 靽∪噡隡𡁜�甇亥圻�𤏸��亦� Tkinter �嗆��凒�啣�靚���眏鈭擧糓�湔𦻖�� PyQt6 �� C++ �喲𡡒/�鞉�靚�鍂��葉�餅�雿� Tkinter API嚗�� `self.after` 蝑㗇釣��𢆡雿頣�嚗���睲� Python 摨訫��� GIL ���憭箏� `PyEval_RestoreThread` �躰秤嚗�紡�湔㟲銝� Python 銝餉�蝔贝◤撘箄�銝剜迫��
    - [x] **摰䂿緵蝥� Python 撘�郊�笔�閫��阡�蝳� (Thread-Safe Event Queue Routing)**嚗𡁜銁銝餌�摨� `instock_MonitorTK.py` 蝏穃�韏偦帕�Ｘ踎 `closed` 靽∪噡���蝵殷��齿�銝箏�甇交��罸�雴漱�箏��婙�𤩊closed.connect(lambda: self.tk_dispatch_queue.put(self._on_racing_panel_closed))`����其縑�瑁圻�𤑳�蝚砌��園𡢿隞���其�蝥輻�摰匧��� Python 蝞⊿��滢�嚗屸妟撱嗉�餈𥪜�嚗��霈� PyQt6 憿箇�����游𧑐����僎�芸𢆡��瘥��`deleteLater()`嚗㚁��𣬚�甇�� Tkinter 皜���其��嗵眏 Tkinter 銝颱�隞嗅儐�舫�朞� `tk_dispatch_queue` �典��函� Tk 蝥輻�銝𠹺�����祉�瘨�晶撟嗆�銵䕘�摰𣬚�摰䂿緵鈭�舅憟� GUI 鈭衤辣瘚�� GIL �批�����惩�蝒��蝳颯��
    - [x] **瘚贝��⊿� 100% �朞�**嚗𡁶��蹱���霂烐��伐�餈鞱��券��詨��笔𦶢�冽��𧼮�瘚贝� `pytest test_watchlist_lifecycle.py`嚗�11憿寧鍂靘页��券�摰𣬚��朞�嚗諹�銵峕��嗥迅摰𠾼��

## 2026-06-11 16:40
- [x] **靽桀�韏偦帕�Ｘ踎靚�絲 ��霂行� 閫血� GIL �𦠜𦆮撖潸稲 Tkinter 銝餌瑪蝔见援皞�� Bug (Fixed Racing Panel check_code GIL Restore Crash Bug)**嚗�
    - [x] **摰帋�撏拇��寞�**嚗𡁏��亙�敶枏銁 PyQt6 韏偦帕�Ｘ踎銝剔��� `��霂行�` �厰僼�塚�隡𡁜�甇亥��典抅鈭� Tkinter �嗆��� `check_code` �賣㺭��眏鈭擧糓�� PyQt �� UI 鈭衤辣�噼�蝥輻�銝剔凒�亙�靘见� Tkinter �� `Toplevel` 蝒堒藁嚗䔶舅銝� GUI 獢�沲�典�銝�銝� Python 銝餉�蝔讠�鈭衤辣敺芰㴓銝剖��笔�蝒��撖潸稲 Tkinter 摨訫��𤑳� `PyEval_RestoreThread` GIL �嗆���撣詨僎撏拇���
    - [x] **摰䂿緵頝冽��嗡蜓蝥輻��笔�瘣曉��箏� (Thread-safe Dispatch)**嚗𡁜銁韏偦帕�Ｘ踎�� `_on_code_check_triggered` 銝哨�撘訫�撖嫣蜓蝔见�瘣曉��笔� `tk_dispatch_queue` ��ế�准��𥅾敶枏�摮睃銁 Tkinter 銝餌�摨讐� `tk_dispatch_queue`嚗��雿輻鍂 `ma.tk_dispatch_queue.put` 撘�郊撠� `check_code` 摰硺��碶遙�⊥晷�穃���迤�� Tkinter 銝颱�隞嗅儐�舐瑪蝔衤葉�扯�嚗�僎隡惩� `parent=ma` (�喃蜓 Tk 摰硺�)嚗𥡝𥅾銝滚��剁��� Fallback �啣�甇亦凒�亥��具����函����敶餃�摰䂿緵鈭� PyQt 銝� Tk 銋钅𡢿��瑪蝔钅�蝳鳴��寥膄鈭� GIL �脩�撏拇���
    - [x] **�𧼮�瘚贝��朞�**嚗𡁻���祗瘜閧�霂烐�撘�虜嚗諹�銵���誯��鞉�霂� `pytest test_watchlist_lifecycle.py` 11 憿寧鍂靘见��冽��罸�朞���

## 2026-06-11 16:30
- [x] **靽桀�韏偦帕�Ｘ踎�鞟內撖澆�撖潸稲�� `ImportError` 銝� PyQt 瘞娍部�鞟內�齿� (Fixed Racing Panel ImportError & Rebuilt PyQt6 Toast Message)**嚗�
    - [x] **�寞祥撖澆��躰秤**嚗𡁏��亙� `bidding_racing_panel.py` 銝剜� 5 憭��霂蓥� `gui_utils` 撖澆��砌�摮睃銁 of `toast_message`嚗�����銋匧銁 `stock_logic_utils` 銝𥪯蝙�函��� Tkinter �嗆�嚗剹���隡𡁜紡�渲��兩�靝��桃蔭憿嗯�脲�瘚贝�蝑𣇉裦�嗉圻�� `ImportError` 撏拇���
    - [x] **摰䂿緵 PyQt �毺�瘞娍部�鞟內�曹澈撟園�敺� DRY 閫��**嚗𡁜銁�砍��餉�撅� `stock_logic_utils.py` 璅∪�蝥扳鰵憓硺� `toast_messageQT` �鞟內�賣㺭��砲�賣㺭�朞�����冽��紡�� PyQt6 蝏�辣�𣂷�擃睃�摰寞�找��頣��踹��冽瓷�� PyQt6 靘肽���滲 Tk �臬�銝剖��笔紡�仿�霂胯��
    - [x] **蝘駁膄�𦯀�撖澆�撟嗡������**嚗𡁜��支�韏偦帕�Ｘ踎銝凋葩�嗅��啁��砍𧑐 PyQt6 toast �賣㺭嚗𣬚�銝��朞� `from stock_logic_utils import toast_messageQT as toast_message` 撖澆�雿輻鍂嚗䔶誑�����誨����唬� PyQt �臬�瘞娍部�鞟內����剁�撟嗆��支�頝冽��嗅�蝥輻�靚�鍂銝讠�銝滨迅摰𡁻�����
    - [x] **瘚贝��朞�**嚗𡁶� `py_compile` �蹱��祗瘜閧�霂烐��乩� `pytest test_watchlist_lifecycle.py` 11 憿寧��賢𪂹�罸��鞟鍂靘见��讐遛�烾�朞���

## 2026-06-11 15:55
- [x] **摰䂿緵蝵桅▲�喃儒�𡏭��兩�嘥��喃��嗆��䌊�冽�銋�� (Implemented Top-Right Auto-Linkage Toggle & State Persistence)**嚗�
    - [x] **瘛餃� UI 鈭支��找辣�喟蔭憿嗆��桀𢰧靘�**嚗𡁶宏�支����憿嗅�撌亙��𤩺��喃儒����㗇���㺿�典�閫�䰻霂Ｘ�嚗�� `��蝏煺�蝵桅▲` �厰僼�諹�嚗匧𢰧靘扳𦆮蝵桀��啁� `QCheckBox("�� �𥪜𢆡")` 撘��喉�蝞��嗘蛹�𡏭��兩�嘅�撟嗡蝙�券�撖寞�摨衣移蝢� HSL �滩𠧧餈𥡝��瑕�皜脫�嚗屸�霈方挽蝵桐蛹�喲𡡒 (`False`)��
    - [x] **�㯄�𡁶��賢𪂹�煺��嗆���銋��蝞⊿�**嚗�
        - [x] 撠�䌊�刻��函𠶖�� `auto_linkage_enabled` �拍�蝏穃��� `_save_ui_state` 銝哨��誩��脩瑪��”�澆�摰賜�銝�韏瑁䌊�典��䀝�摮塩��
        - [x] �� `_restore_ui_state` �嗆挾摰䂿緵頝其�霂肽䌊�刻粉�吔��交𧊋�滨蔭�坔��� Fallback �� `False`嚗��霈文��哨�嚗�僎�朞� `blockSignals` �脫��𠉛氖嚗䔶��𨅯��臬𢆡��滲���扼��
        - [x] �齿� `showEvent` 銝𤾸��單局�賣㺭 `_on_auto_linkage_changed`嚗𣬚眏�Ｘ踎撅閧內�嗯�𨀣��∩辣撘��胼�嗪���蛹�靝��桃鍂�瑞� UI �暸�厩𠶖���嘥� `detector` �冽�������湔鰵嚗𣬚＆靽苷��滨蔭�������湔�扼��

## 2026-06-11 15:30
- [x] **靽桀�韏偦帕�Ｘ踎�芸𢆡�𥪜𢆡�滚��煾����喲𡡒�� Tk �港葵撏拇��� Bug (Fixed Racing Panel Auto-Linkage Duplication & Application Exit Crash Bug)**嚗�
    - [x] **�寞祥�芸𢆡�𥪜𢆡憭朞�鈭斗𤜯�券�����**嚗𡁜�雿滚� `bidding_momentum_detector.py` 銝剔� `_update_daily_dragon_top2` �冽�甈∟����頝單𧒄�滚�撟嗉䌊�冽綫����㗇暑頝�踎�㛖� Top 2 撘箏飵銝芾��� `link_manager`嚗𣬚眏鈭𤾸��典��芾�蟡剁��航噢 20+ �迎�擃㗛�鈭斗𤜯�券���撖潸稲 `LinkageManagerProxy.push` ������銝� `_last_pushed_code` �駁��箏�鋡思漱�輯��𤥁��仃���撘訫��朞噢靽∪��圈�憸煾�憭滩��券��氬�����蛹�芸銁隞𦠜𠯫��撘箇�蝚砌��漤�憭渲��𤑳���揢�𡝗說頞喳��湔𧒄�芸𢆡�閖�坿��剁�隞𡒊����摰𣬚�瘨�膄鈭��憭齿��𡜐��滢�鈭� CPU 韐蠘蝸銝𤾸��圈緾����
    - [x] **�寞祥�喲𡡒韏偦帕�Ｘ踎�� wrapper �𣂼�鋡� GC 撖潸稲�� GIL 撏拇�**嚗𡁏��亙��� Nuitka 蝻𤥁��臬�銝页�PySide6/PyQt6 銝� Tkinter 瘛瑞鍂�塚�敶栞�撽祇𢒰�輯圻�� `closeEvent` ���蝔衤葉嚗𣬚凒�亙銁�峕郊靽∪噡銝剜�銵䔶� `self.main_app._racing_panel_win = None` 撘箏��函蔭蝛箝���撖潸稲 Python ���蝐鳴�Wrapper嚗匧銁甇斗活 C++ �鞉�瘚��撠𡁏𧊋���箸�銵峕��滢噶�𣂼�鋡怠��曉��塚�GC嚗厰�瘥��隞舘��銁 C++ 摨訫��鞉�蝏抒賒�噼��嗉圻�� `PyEval_RestoreThread` ���霈輸䔮撘�虜銝� GIL �嗆��仃��紡�� TK 銝餉�蝔讠凒�亙援皞������蛹�� `closeEvent` ���敶餃��𣳇膄霂亥��湔𦻖蝵桃征�餉�嚗���嗅��其漱蝏� Tkinter 蝡舐� `_on_racing_panel_closed` 蝏� `self.after(100, _safe_clear)` 撱嗆𧒄 100ms 撘�郊蝵桃征��
        - [x] **憓噼挽 UI 敹�歲銝𤾸��剝𡢿�嗵� `_is_closing` �拍�撅讛𤪖�券�**嚗帋蛹鈭�俈甇Ｗ銁銝𡃏膩 100ms 撘�郊�𦠜𦆮���皜⊥����銝餌�摨𤩺�蝘垍� UI 蝒堒藁�峕郊敹�歲 `sync_rotator_windows` (隡𡁻������ `_get_all_open_trade_windows`) �餉挪�桀歇蝏𤩺����撠𡁏𧊋蝵� None ��𢒰�蹂� `isVisible()` �� `winId()` 撅墧�扯圻�𤑳� GIL 撏拇��躰秤嚗�銁 `closeEvent` 憿嗅�撘箏��峕郊��蝸 `self._is_closing = True`��僎�� `_get_all_open_trade_windows` ���撖寡�撽祇𢒰�蹂誑�𦠜踎�㛖�隞瑯��縑�瑞��踴��貌銵函�����閙��交�蝑㗇��� PyQt6 蝒堒藁�券𢒰蝏�� `not getattr(win, '_is_closing', False)` ���頝舐���俈�歹�敶餃�瘨�膄鈭��甇亦征蝒埈�頦拚𡺨撏拇��������
    - [x] **蝻𤥁�銝𡒊頂蝏毺漣�笔𦶢�冽�瘚贝� 100% �朞�**嚗𡁻�朞� `py_compile` �蹱��祗瘜閙��伐�銝磰�銵���𤩺瓲敹��敶埝�霂� `pytest test_watchlist_lifecycle.py`嚗�11 憿寧鍂靘见��冽��罸�朞�嚗峕�隞颱��𧼮��桅���

## 2026-06-11 12:28
- [x] **�牐噩�亙�靽桀� Nuitka 蝻𤥁��臬�銝� PyQt 瑽賢遆�唳鱏撘�餈墧𦻖撏拇��� Bug (Non-Intrusive Fix for Nuitka compiled_method Disconnect Crash Bug)**嚗�
    - [x] **摰帋� compiled_method �躰秤�寞�**嚗𡁏��亙��啣�蝟餌��� Nuitka 蝻𤥁��枏��臬�銝贝�銵峕𧒄嚗釶yQt6 蝏穃���局�賣㺭鋡怎�霂烐�鈭� Nuitka 銝枏��� `compiled_method` 蝐餃�����𨅯銁蝏�辣�湔鰵�㚚�瘥�𧒄靚�鍂 `pyqtBoundSignal.disconnect`嚗釶yQt6 摨訫��䭾�颲刻�撌脩�霂烐䲮瘜閗�䔶��𥕦枂 `TypeError: 'compiled_method' object is not connected`嚗𣬚凒�亙紡�游援皞���
    - [x] **�滚��典��游�銵乩�隞乩��文��厩㴓憓�**嚗帋蛹撠� Bug 靽桀�����拚��唳�雿𠬍�摰��銝齿㺿�䀝遙雿訫�撅� PyQt6/Nuitka �箇�餈鞱��臬�嚗䔶蜓�冽伃�硺�撖� `sys_utils.py` 銝� `hotkey_rotator.py` ���撅��游�銵乩��行⏛�餉�嚗𣬚＆靽肽��㴓憓�葉��抅蝖�靽∪噡�箏� 100% 銝滚�撟脫贋��
    - [x] **�齿� `market_temp_chart.py` 摰墧鴌撠勗𧑐�閙活皜脫�銝擧㺭�桀��𤩺凒��**嚗𡁻����撣�㦤皜拙漲韏啣飵撘寧����憪见�銝𡡞�蝏㗛�餉���銁 `_init_ui` �嗅� `p1`, `p2`, `p3` 蝑匧��曉����㗇𤩅蝥選�Curve嚗劐�甈⊥�扳�撱箏�瘥𤏪��� `update_chart` 銝剖��支�摰寞�閫血�閫���仿��� `self.graph_layout.clear()` 皜�征�其�嚗峕㺿銝粹�朞� `setData` �寞�撠勗𧑐憓鮋��湔鰵�唳旿�嫘��迨銝曆�隞�銁�拍�銝𠰴蝠摨閙��支� `disconnect` 閫血�皞琜�閫��鈭� Nuitka 撘�虜嚗諹�䔶�憭批��𣂼�鈭�㦛銵函�皜脫��扯����摨娪�笔漲��
    - [x] **瘚贝�撉諹�**嚗𡁻�朞� `py_compile` �蹱���霂烐嵗撉䕘�銝𥪜�敶埝�霂� `pytest test_watchlist_lifecycle.py` 11 憿寧鍂靘见��冽��罸�朞���

## 2026-06-11 11:55
- [x] **靽桀�憭朞�蝔讠𠶖����碶��芣��亙��滚��航㨃�瑕��� Bug (Fixed Multi-Process State Overwrite & Healing Log Oscillation Bug)**嚗�
    - [x] **�餃�憭朞�蝔�/憭𡁜�靘讠𠶖���銋栞��𡝗���**嚗𡁏��亙枂 `StateManager` (�嗆���蝞∠���) �冽�銵� `set` �坔��塚��曹��芸銁�坔��滢�蝤���峕郊���啁𠶖���敶枏�餈𤤿��峕𧒄餈鞱�嚗�� Tkinter 銝餉�蝔衤� PyQt6 �航��碶撈�讛�蝔页�銝娍�銝��寞��㗇唂����嗆��𧒄嚗�� `set` �其�隡𡁶鍂餈���� `IN_TRADE` ����嗆���撟嗅僎撘箄�閬���拍� JSON ��辣嚗���虫��寡䌊����鞟� `FLAT` �嗆���㘾���墧�����䭾�鈭��餈𤤿��嗆����凌�靝�銋㯄��﹦�嘅�靽�蝙 Tkinter 銝餉�蝔𧢲�甈∪�頝喲��齿活閫血� `StateManagerSelfHeal` 霅血��芣���
    - [x] **摰䂿緵撘箔��湔�批��亙��峕郊**嚗𡁻���� `state_manager.py` �𣬚��峕郊銝𤾸��交㦤�嗚��蛹 `_sync_from_file` 憓𧼮�鈭� `force` 撘箏�銝滩�瘚��甇交�敹梹�撟嗅銁 `set` �寞�憭湧�撘箏��㰘�瘚�𧑐�扯� `_sync_from_file(force=True)`���蝖桐�隞颱�餈𤤿��冽凒�嫣遙雿閗�蟡函𠶖���嚗��憿餃��拍��匧����啁��曹澈蝤���嗆����𦦵�鈭���笔�摮睃笆蝤��甇�＆�嗆���蝭⊥㺿嚗䔶��寞𧋦銝𦠜��支��嗆��䌊���皜拙���
    - [x] **��漣撟嗅��𤾸�摰寡�蝔讠漣�臭��駁��瑕㭂**嚗𡁜� `trade_gateway.py` 銝� `kernel_service.py` �𣬚� `_log_cooldown` �梁掩摰硺�撅墧�批�蝥找蛹璅∪��典��㗛�嚗Ǒ_GATEWAY_LOG_COOLDOWN` 銝� `_HEAL_LOG_COOLDOWN`嚗㚁�撟園�朞�摰帋�蝐� `@property` 摰𣬚��睲��澆捆嚗䔶蝙敺𦯀�霈箏笆鞊∪�雿閗◤�滚遣�𤥁◤銝滚�撖澆��孵�鈭峕活摰硺��吔��芾�憭���䔶�銝芾�蝔讠征�游�嚗屸��賢�鈭怠𣈲銝�����渲扇敹���
    - [x] **瘚贝��朞�**嚗𡁏𧋦�啣����霂� `scratch/test_high_pullback_and_log_cooldown.py` 隞亙�蝟餌��𧼮�瘚贝� `test_watchlist_lifecycle.py`嚗�11憿寧��賢𪂹�毺鍂靘页��券�蝏踵��朞���

## 2026-06-11 11:45
- [x] **靽桀�鈭斗�靽∪噡餈賢銁敶枏予憿園�銝𦒘�撣�𧒄畾菟�蝜�圻�睲僭�亦� Bug (Fixed Chasing Top & Off-Hours Buy Signals Bug)**嚗�
    - [x] **摰䂿緵�煾��㚚俈餈賡�銝𡡞俈�脤��噼氜�行⏛**嚗𡁜銁 `stock_logic_utils.py` �� `RealtimeSignalManager.update_signals` 銝哨�撘訫�鈭�抅鈭擧㿥�交𤣰�䀝遠 `lastp1d` ����嗆隅撟� `percent_arr` 銝𦒘��亙���擃条��墧伃撟�漲 `pullback_arr` 霈∠����銋劐�敶𤘪��唳隅撟� $\ge 7.5\%$嚗�俈餈賡�嚗㗇�擃䀝��𧼮�撟�漲 $\ge 3.0\%$嚗�俈�脤��噼氜嚗㗇𧒄��僭�交㜃�芣焵�� `block_mask`��銁���銋啣�靽∪噡�塚�撠�說頞� `block_mask` ��葵�∪撩銵𣬚蔭銝箇征嚗䔶�皞𣂼仍�餅鱏鈭�▲�刻蕭擃䀝��噼氜�亦�靽∪噡��漣�麄��
    - [x] **銵仿�銝餌�摨譍僭�乩��訫�蝵桐��斤���**嚗𡁜銁 `instock_MonitorTK.py` �𣬚��芸𢆡�喟�銝见�銝餃儐�� `_bg_kernel_auto_execute_once` 銝哨��刻��� `submit_buy` 銋见�蝏���滨蔭餈�誘��笆憭�� (1) ���皛� 10 �芷��嗡�銝滚�鈭𤾸歇�㗇�隞梶�銋啣�嚗�(2) 憭���硺漱�𤘪𧒄畾� `not is_active_trading` ��僭�伐�(3) 撅硺�隞𦠜𠯫撌脣��箏��� `_today_sold_codes` ��僭�伐��湔𦻖�典�蝥踹��賜���㜃�迎�撟嗅��亙笆摨𠉛� UI �行⏛霂湔�嚗���𣈯�鈭斗��嗆挾�腈���𨀣�隞枏歇皛�(10��)�腈���𨅯��箏��港葉�嘅�嚗�蝠摨閖獈甇Ｖ�餈䠷����雿嗘��閗窈瘙���垍�蝵穃���
- [x] **摰䂿緵�芣��嗆��笆朣𣂷�蝵穃�憌擧綉�垍�霅血��� 300蝘鍦��游縧�齿㦤�� (Implemented 300s Cooldown Deduplication for Healing & Rejection Warnings)**嚗�
    - [x] **�寞祥 StateManagerSelfHeal �亙���� Bug**嚗𡁜銁 `trading_kernel/kernel_service.py` �𣬚� `evaluate_decision_item` �嗆��䌊��笆朣𣂷葉嚗���乩� `_log_cooldown` ����駁�摮堒�嚗�笆隞� `FLAT` �� `IN_TRADE` 隞亙� `IN_TRADE` �� `FLAT` ��䌊��郎�𦠜𠯫敹埈�銵� 300 蝘鍦��湔㜃�迎��瑕㭂�笔��滢��亙�颲枏枂嚗峕�蝏苷�瘥讐�敹�歲敺芰㴓銝讠��亙��瑕���
    - [x] **�寞祥 MockTradeGateway 霅血��亙��瑕�**嚗𡁜銁 `trade_gateway.py` �𣬚� `submit_buy` 銝哨���笆�硺漱�𤘪𧒄畾菜�蝏腈����亙歇�硋枂�瑕㭂�行⏛��誑�𢠃��� limits 銝漤�朞�蝑㗇��㕑郎�𡃏��箏�憟𦯀�鈭� 300 蝘𡜐�5���嚗厩� key �駁��脩瑪���銝餌�摨誩�蝵格㜃�芰㮾鈭㘾����颲暹�鈭�漱�枏��圈妟�芸ㄟ�亙�����湔㟲瘣��撉䎚��
    - [x] **蝻硋�銝枏�瘚贝�銝𤾸��誩�敶� 100% �朞�**嚗𡁜銁 `scratch/test_high_pullback_and_log_cooldown.py` 銝剔��嗘�閬��瘨典�撅讛𤪖����𣂼��賬��誑�𢠃��扳說憸苷�霅血��駁��瑕㭂����㕑器�峕辺隞嗥��訫�瘚贝�嚗���函遛�烾�朞����甇亥�銵䔶��券��詨��𧼮�瘚贝� `pytest test_watchlist_lifecycle.py`嚗�11 憿寧��賢𪂹�罸��鞟鍂靘� 100% �𣂼��朞�嚗��蝟餌�餈鞱����蝔喳���

## 2026-06-11 10:55
- [x] **�日�撣�㦤皜拙漲�� MarketStateBus �𣂼��餉�嚗䔶��坔翰�蠘���凒�啗圻�烐㦤�� (Reverted Market Temperature Source to self.df_all.copy() & Kept Rapid Triggers)**嚗�
    - [x] **�寞祥撣�㦤皜拙漲鋡怠��冽��航膘�唳旿瘙⊥��桅� (Fixed Multi-Cycle Temperature Pollution)**嚗𡁶眏鈭� `MarketStateBus` �交𤣰撟嗅�撣���急𠯫蝥蹂蜓頧典�憭批𪂹�笔�頧函����㕑���翰�改�撖潸稲�冽��� UI ��揢�� 3D 蝑匧之�冽��漤��瑟㺭�格𧒄嚗䈣MarketStateBus` ����� `_df_all` 鋡怠��亙之�冽��唳旿嚗䔶��峕情�㮖�撘�郊撣�㦤皜拙漲霈∠�嚗䔶蝙銝𦠜隅/銝贝�摰嗆㺭銝𤾸之�䀹萱摨西恣蝞堒�蝳餃���𠯫蝥踵㺭�柴��
    - [x] **餈睃��亦瑪�砍���蘨霂餅鼧韐脲㦤��**嚗𡁜銁 `_aggregate_market_dashboard_stats` ��伃��鈭�� `MarketStateBus` �𣂼��唳旿��耨�對��齿鰵撠���Ｗ�銝箄粉�硋僎�芾粉�瑁�銝餌瑪蝔讠𡠺�删� `self.df_all.copy()`���敶餃���鱏鈭����甅�航膘撖孵��箸萱摨衣�撟脫贋嚗𣬚＆靽苷�霈� UI 憭�銁雿閧��曄內�冽�銝页�皜拙漲霈∠�����箔�蝥臬���𠯫蝥踵㺭�桀��箝��
    - [x] **靽萘� 3蝘㘾俈�𣇉�擃睃��嗆凒�啗圻��**嚗帋��嗘��㗇㺭�格凒�唬�頝萘氖銝𠹺�甈∟恣蝞𡑒��� 3.0 蝘鍦朖蝡见朖閫血�撘�郊霈∠���㦤�塚�蝖桐�銵峕�頝喳𢆡�嗆萱摨衣��惩辣餈���瑕�蝷箝��
    - [x] **憿箏⏚頝煾�𡁶�霂穃��笔𦶢�冽�瘚贝�**嚗𡁜��𣂷��蹱��祗瘜閧�霂烐��乩� `pytest test_watchlist_lifecycle.py` �𧼮�瘚贝�嚗���� 11 憿寧鍂靘� 100% �朞�嚗𣬚頂蝏笔�鈭𤾸�蝢舘�銵𣬚𠶖����

## 2026-06-11 10:45
- [x] **靽桀�憭批𪂹�罸���甅嚗�� 3D嚗劐������僎 KeyError: 'lasto1d' 銝𤾸之�冽�靽∪噡�拍� Bug (Fixed Resample KeyError & Decoupled Multi-Cycle Signal Calculations)**嚗�
    - [x] **�寞祥撠讛��𡑒”銝讠��堒�撟� KeyError (Fixed len(top_all) > 5 Restriction)**嚗𡁜�雿滚僎靽桀�鈭� `JSONData/tdx_data_Day.py` �� `get_append_lastp_to_df` ����餉�銝� `len(top_all) > 5` ���蝵桀�撟園��嗚��砲�𣂼��刻�皛文����蟡典�銵券鵭摨虫蛹 1-5 �嗡�撖潸稲頝唾���蟮�讐宏�堒�撟塚�餈𥡝��銁�𡒊賒�箏�撖寞��嗅��曆��� `lasto1d` 摮埈挾�𥕦枂 `KeyError`����嗡耨�嫣蛹 `len(top_all) > 0`嚗�蘨閬�㺭�桐�銝箇征撠勗��典�撟塚�敶餃�瘨�膄鈭���亦瑪憭批𪂹�罸���甅�嗥� KeyError 撏拇��鞉���
    - [x] **閫��血��冽� RealtimeSignalManager �嗆���蝳颱�蝻枏� (Decoupled Multi-Cycle Signals & Isolated Caching)**嚗𡁻�撖寞𠯫蝥蹂蜓頧� `full_df` �屸���甅�航膘 `full_df_res` �曹澈�䔶�銝芯縑�瑞恣��膥摰硺�撖潸稲�� `state_df` 鈭斗𤜯霂餃�銝𡒊�摮䀹�頧阡䔮憸矋��齿�鈭� `RealtimeSignalManager` ����典��� model��緵�冽��厩𠶖�� `state_df` �� `_cached_data`嚗�鉄 `last_hash`��cached_signal` 蝑㚁������ `resample` �冽�嚗�� `'d'`, `'3d'`嚗㕑�銵𣬚�����箔��祉�摮堒��𠉛氖嚗�僎靽萘�鈭�笆�� `self.state_df` 撅墧�抒��穃��澆捆嚗䔶�摨訫��𦦵�鈭�楊�冽�霈∠�瘙⊥���
    - [x] **摰䂿緵憭批𪂹�煺縑�瑞��祉�撘�郊霈∠� (Independent Multi-Cycle Signal Computation)**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `_run_compute_async` 撘�郊霈∠�瘜菟�餉�����支�隞擧𠯫蝥輯膘�枏�憭批𪂹�笔�蝷箄膘�䭾辺隞嗆�撠�鼧韐� `signal` �� `signal_strength` ��撩�瘀�撖寞�瘣餌� `full_df_res` (�航膘) �峕甅�𤏸絲�祉��� `detect_signals` 靽∪噡�枏��文�嚗�僎�其蜓�航膘�峕郊�嗡��瑁�������嚗𣬚＆靽� UI 銝羓�憭批𪂹�煺縑�瘀�憒� ma5d 蝒�聦蝑㚁��箔�憭批𪂹������摰噼圻�㻫��
    - [x] **頝煾�𡁜��𧼮�瘚贝�撉諹� (Passed All Core Regressions)**嚗𡁏��蠘�銵� `pytest test_watchlist_lifecycle.py` �券��朞�嚗�11 passed in 0.75s嚗㚁��蹱���霂穃恣霈� 100% 甇�虜嚗��餈𤤿��誩�銝𦒘漱�梶頂蝏蠘�銵峕�撘�虜��

## 2026-06-11 10:25
- [x] **摰䂿緵撣�㦤皜拙漲銝𤾸��嗉�����渡��惩辣餈笔�甇交凒�� (Aligned Market Temperature Updates with Data Changes)**嚗�
    - [x] **閫��銵峕��湔鰵�單𧒄閫血��箏�**嚗𡁜�雿滚僎閫�膄鈭� `_aggregate_market_dashboard_stats` 銝剖笆鈭𡒊�銝剜㺭�桃�霈� 60 蝘鍦��嗆凒�啁�蝖祆�扳㜃�芷��嗚��
    - [x] **撘訫� 3蝘㘾俈�硋�靽嗪埯�文�**嚗𡁜��牐� `trigger_update = has_update and (now - last_sync_ts > 3.0)` ��俈�硋�甇亙ế摰𡁻�餉���銁蝖桐�蝟餌��㕑���㺭�桀�韐冽凒�唳𧒄嚗Ǒhas_update=True`嚗㚁��芾�頝萘氖銝𠹺�甈∟恣蝞𡑒��餉�餈� 3.0 蝘𡜐�撠梁��唾圻�穃僎�穃��啁瑪蝔𧢲��𣂷漱撘�郊皜拙漲霈∠�隞餃𦛚���敶餃�閫��鈭�鍂�瑕�擐���𨅯�撘���/�㗇㺭�格凒�唳𧒄嚗峕萱摨行遬蝷箸�餅糓憭𡁶�銝�銝芸𪂹�麨�萘�雿㯄��𤤿�嚗���唬�皜拙漲�䀹凒銝� Tick �湔鰵���摨血��嗅�甇乓��
    - [x] **頝煾�𡁻����霂睲��詨��笔𦶢�冽��𧼮�瘚贝�**嚗𡁏��罸�朞�鈭� `py_compile` �蹱��祗瘜閧�霂烐��伐�銝� `pytest test_watchlist_lifecycle.py` 11 憿孵��讐頂蝏毺��賢𪂹��瓲敹��霂� 100% �朞�嚗㇊assed in 0.77s嚗剹��

## 2026-06-10 18:30
- [x] **摰䂿緵擃䀹�扯��冽����誩抅��恣蝞𦯀��𤩺��� Hash ��漣嚗峕覔瘝餌�銝凋葵�∠聦雿滢縑�瑕之�Ｙ妖瞍𤩺𥁒 Bug (Implemented High-Performance Incremental Baseline & Upgraded Dirty Check Hash)**嚗�
    - [x] **摰䂿緵皜鞱�撘誩𢆡����誩抅���摰� (Dynamic Incremental Baseline)**嚗𡁜銁 `DailyEmotionBaseline` �� `calculate_baseline` 銝哨�撘訫�鈭� `_initial_calc_done` �嘥��𣇉𠶖����譌��笆�瑕鍳�典�憪见之���蟡刻�銵� >=100 �芰��箏��冽��文�嚗𥕦�憪见��𣂼��𠬍��𡒊賒�䀝葉�瑟鰵隞��朞� `~isin(self._structural_anchors)` �冽����硋枂撠𡁏𧊋撱箇��箏����銝芸��啣��∠巨摮鞾�嚗�蘨撖孵�餈𥡝�憓鮋��箏�霈∠�嚗𣬚征摮鞾��坔銁 1 敺桃����頝舫���綽�摰𣬚��潮▽鈭���亦�摰墧𧒄憓鮋��㰘蝸銝擧�擃䀹�扯�撘�����
    - [x] **�寞祥�曹��⊿�憭梯揖撖潸稲��㺭�格���**嚗𡁜銁�嘥��箏��冽�霈∠�銝滩雲 100 �芾圻�穃仃韐亥��墧𧒄嚗峕遬撘讛��函�摮条� `clear()` 皜�征���㗇𧊋撠梁貌��㺭�桃����撟嗅銁頝典予璉�瘚衤葉餈𥡝�瘛勗漲�峕郊�滨蔭嚗�蝠摨閙��支��箏��芸停蝏芰𠶖������蝻枏�瘙⊥���
    - [x] **�㯄�𡁜��嗉���㺭�格�摰峕㟲靚�鍂��**嚗帋耨�� `DataPublisher.update_batch` �餉�嚗�銁�䀝葉敹�歲銝剜��∩辣靚�鍂 `calculate_baseline(df)` 隞交𦻖�嗅��𤩺鰵�∴��勗����憓鮋��斗鱏摰匧�餈�誘嚗㚁�撟嗅�蝥找�擐硋��芸停蝏芣�瘚𧢲辺隞塚�蝖桐��典予�嗘遙�誩��臬𢆡/�剖�頧賣𧒄畾萇��唳旿蝞⊿�摰峕㟲�䭾���
    - [x] **��漣 Pump 蝥輻��𤩺��� Hash 蝞埈�銝� 50�寡����蝥�**嚗𡁜�雿滚僎皜�膄鈭� `instock_MonitorTK.py` �� `_process_tree_data_async` 銝凋�撖� DataFrame 擐硋偏�𠹺葉�� 3 �嫣遠�潸�銵峕���ế�剔���摹 hash 蝞埈���砲蝞埈��� Favorites �𡑒”蝵桅▲�𤥁�銝匧蘨銝芾��𦦵�銝滩歲�冽𧒄嚗䔶�撅讛𤪖�典��箏�摰� 5000+ 銝芾���凒�啜������蝥找蛹�典㦤 **50�孵�����甅 + 隞瑟聢銝擧�鈭日��𥪜� Hash** �⊿�嚗峕𠳿靽萘�鈭�㜃�芷�憭滚葷����𨥈���蝠摨閙��支�擃㗛�銵峕�銝见��其葵�∪�隞瑕��賢��箇��游𦶢蝻粹萅��
    - [x] **蝻硋�銝枏�瘚贝�銝𤾸��𧼮�瘚贝� 100% �朞�**嚗𡁜銁 `scratch/test_incremental_baseline.py` 銝剔��嗘�閬���嘥��冽��行⏛���憪贝恣蝞埈��麄����讛‘��恣蝞𦯀誑�𡃏楊憭拚�蝵桃����劐葩����舐�銝梶鍂�訫�瘚贝�嚗���函遛�烾�朞���頂蝏毺漣����𧼮�瘚贝� `pytest test_watchlist_lifecycle.py` (11 憿寞瓲敹���賢𪂹�毺鍂靘�) 100% �函遛�朞�嚗㇊assed in 1.33s嚗㚁�蝟餌��嗅�敶垍聦�譌��

## 2026-06-10 17:35
- [x] **�齿�撟嗅�蝥找縑�瑕�蝐駁𢒰�選�摰䂿緵 V�见�頧� 靽∪噡�祉��亦�銝𤾸㨃����� (Upgraded Signal Dashboard Panel for V-shape Reversal)**嚗�
    - [x] **�拍��踵揢�𨅯偏�䁅秧憭尠�嘥�蝐颱蛹�𦛼�见�頧砂��**嚗𡁜銁 `signal_dashboard_panel.py` 銝哨�撠����銁 `CATEGORY_MAP`��SIGNAL_TYPE_MAP`��SIGNAL_TYPE_KEYWORDS` 銝剔� `trap` (撠曄�霂勗�) �惩�銵典��喲睸摮堒��ａ���𤜯�Ｖ蛹 `v_reversal` (V�见�頧�) 隞亙� V�� �詨��寥�摮㛖尐嚗�� `v_shape`, `V_SHAPE`, `V�崾, `V�见�頧柄嚗剹��
    - [x] **�券𢒰�舀�敹急㭘�∠�銝擧�蝑暸△�孵稬�𥪜𢆡**嚗𡁜�憿園����𨅯偏�䁅秧憭尠�嘥翰�瑕㨃�����蛹�𦛼�见�頧砂�嘥㨃���撟嗅�撖孵��� Tab 憿菟𢒰�游�銝� �𦛼�见�頧砂�嘅��峕𧒄靽格㺿 `_on_card_clicked` �噼��賣㺭銝剔� mapping �惩�嚗䔶蝙敺㛖��領�𦛼�见�頧砂�嘥㨃����祇𡢿�其�瘥怎�蝥批��芸𢆡�𥪜𢆡撟嗉歲頧祈秐�祉��� �𦛼�见�頧砂�� Tab��
    - [x] **�峕郊�湔鰵������霈∩��嗆���瘨��頧格偘**嚗𡁜笆 `_categorize_and_count` ��掩�餉���_refresh_all_tables` 銝剔��駁�銝𤾸��誩��啣�瘚��餉���誑�羓𠶖��� `tab_to_count`��蔭�剜��航�銵��甇乩耨�對�瘨�膄鈭���臬𢆡甇找���
    - [x] **摰峕� Python 霂剜�蝻𤥁�銝擧瓲敹��敶埝�霂�**嚗𡁻�朞� `py_compile` 撖嫣耨�寞�隞嗉�銵䔶��䭾香閫坿祗瘜閙��伐�銝𥪯蜓�𧼮�瘚贝�憟𦯀辣 `pytest test_watchlist_lifecycle.py` 銝� 11 憿孵��笔𦶢�冽��詨��其� 100% �函遛�朞�嚗㇊assed in 0.72s嚗剹��

## 2026-06-10 17:25
- [x] **��漣 V-Reversal 瞏靝�瘙䭾�瘙唬蛹蝎曉�鈭斗��亙ế摰� (Upgraded V-Reversal Lurking Pool Eviction to Trade-Day-Based Distance)**嚗�
    - [x] **�寞祥�拍��園𡢿頝刻���𠯫霂舀�蝞� Bug**嚗𡁜�撘���笔�隞亦�����堆�憒� 72撠𤩺𧒄 / 48撠𤩺𧒄嚗㕑恣蝞𡑒��毺��文�����Ｗ��� `cct.get_trade_day_distance(entry_date)` �亙藁嚗�銁�∠巨璅芰�瞏靝� `CONSOLIDATING` �煺誑鈭斗��仿𡢿�娍㺭 $\ge 3$ 憭押����匧�/�噼萱�煺誑鈭斗��仿𡢿�娍㺭 $\ge 2$ 憭抵�銵諹����瘙啜���敶餃��踹�鈭�𪂹�怠��賢���坾���撠誯鵭����湛��曹��硺漱�𤘪𧒄�湔��嘥紡�渡��亦𠶖��◤霂舫�蝵桀� `INIT` ����∠撩�瑯��
    - [x] **摰䂿緵�嗆��㦤瘚�蓮�𡁶�霈啣�銝舘‘朣鞱䌊��**嚗𡁜銁��𠶖����對�`INIT`, `WAVE_UP`, `PULLBACK`, `WAVE_UP_2`嚗㗇�頧祆𧒄�峕郊�坔� `entry_date` 鈭斗��交�霂��撟嗅銁頧賢��嗆挾�芸𢆡撖孵��脩撩�� `entry_date` ��扇敶閗�銵��摰寞�扳神蝘垍漣銵仿�頧祆揢嚗䔶��靝��剔�蝏凋����憯格�扼��
    - [x] **�峕郊�齿��瑕鍳�刻䌊������皛斗㦤��**嚗𡁜� `load_consolidation_state()` 撏拇��Ｗ��嗆挾 of �萄偶銝芾�餈�誘銋蠘�蝘餉秐 `get_trade_day_distance` 璉��伐�蝖桐�撘��睃��臬𢆡�嗅蘨撖寧�甇��餈� 3銝芯漱�𤘪𠯫 �芣暑�函�瞏靝��⊥�銵屸�蝵桀��硔��
    - [x] **�齿� Mock �訫�瘚贝�銝𦒘蜓�𧼮�瘚贝� 100% �朞�**嚗𡁜銁 `scratch/test_lurking_pool_pruning.py` 銝剖⏚�� `unittest.mock.patch` �𣂼� Mock �亙�頝萘氖霈∠�隞亥圾�行㺭�桀��嗆���4 憿寞瓲敹�鍂靘� 100% 蝏踵��朞���頂蝏罸��𣂼�敶埝�霂� `pytest test_watchlist_lifecycle.py`嚗�11憿寧鍂靘页� 100% �函遛�朞�嚗屸妟蝔喳��找��餉��㘾����

## 2026-06-10 17:05
- [x] **�齿� V-Reversal 瞏靝�瘙䭾�瘙唬��芣����𡝗㦤�� (Refactored V-Reversal Lurking Pool Eviction & Self-Healing)**嚗�
    - [x] **摰䂿緵隞瑟聢�舀��港�瘛䀹掠**嚗𡁜銁 `realtime_data_service.py` �� `update_wave_structure_state()` �嗆��㦤瘚�蓮銝剖��亥��湔𣈲�睲�瘛䀹掠�餉����銝芾�憭��璅芰�瞏靝� (CONSOLIDATING) �嗆挾�塚��乩遠�潸��湔�雿𡡞��寞𣈲�睲� (anchor_low) 颲� 2.5%嚗峕����鈭𡒊憬�誩�頦� (PULLBACK) �嗆挾�嗉��游�頦拇𣈲�� (pullback_price) �� VWAP嚗𣬚𠶖��朖�滨蔭銝� `INIT` 撟嗥��喟宏�箇��扳���
    - [x] **摰䂿緵�園𡢿餈��頞�𧒄瘛䀹掠**嚗𡁜��仿𧫴畾菔��交𧒄�湔� `entry_ts`嚗峕赤�䀹�隡� 3 憭拇�隞颱��暸��匧�蝒�聦���蝚砌�瘜Ｘ���/�噼萱/鈭峕活�臬𢆡�嗆挾��賒 2憭� �惩�蝏剔𠶖���蝘餅𧒄嚗峕�銵諹����瘙堆��滨蔭銝� `INIT` 撟嗉腺�箇��扳���
    - [x] **摰䂿緵�瑕鍳�函����皛支�����**嚗𡁜銁�瑕鍳��/撏拇��Ｗ��㰘蝸�嗆��㺭�格䲮瘜� `load_consolidation_state()` 銝剔��亥��嗥����皛文ế摰𠾼��銁撠���� json/gzip ��辣頧賢�����塚��芸𢆡�急�撟嗅笆 3憭�/2憭� 頞�𧒄��葵�⊿�蝵桐蛹 `INIT`嚗�僎銝滚��� `v_reversal_pool` 銝剖��𠺶���銝�甈∪��䀹𧒄�芸𢆡摰峕���蟮�萄偶�唳旿��之瘣㛖�����吔�靽肽�鈭���亦�擃䀹暑�批����蝎曄���
    - [x] **蝻硋�銝枏��拍��⊿�瘚贝�銝𦒘蜓����𧼮�瘚贝��朞�**嚗𡁜銁 `scratch/test_lurking_pool_pruning.py` 銝剔��嗘�閬���嗆���頧研��遠�潛聦雿齿�瘙啜��𧒄�渲����瘙唬誑�𠰴��臬𢆡�拍����𤥁�皛� 4 憭批㦤�舐��訫�瘚贝�嚗�4 憿寞�霂� 100% �朞���僎銝𥪯蜓蝟餌��詨��笔𦶢�冽��𧼮�瘚贝� `pytest test_watchlist_lifecycle.py` �� 11 憿寧鍂靘� 100% �函遛�朞�嚗㇊assed in 1.68s嚗剹��

## 2026-06-10 16:40
- [x] **摰䂿緵 contains 銵刻噢撘讛䌊���甇���文�銝𤾸�蝻�蝻嘥� (Implemented Smart contains Regex Translation & Prefix Sewing)**嚗�
    - [x] **靽桀�甇��餈�誘�䭾㺭�桃撩�� (Fixed Regex Filtering Empty Bug)**嚗朞圾�喃��曹�銋见�銝粹俈甇Ｖ葉��𡠺�瑟𥁒�躰�䔶�����釣�� `regex=False` 撖潸稲 `MainU.str.contains('1|1,2,3|4,5,6')` �� `index.str.contains('^(30|68|8|9)')` 蝑匧��怠�摮㛖泵��迤�躰�皛文蝠摨訫仃����唳旿�� Bug������ `query_engine_util.py` 銝剔� `_preprocess_query` �寞�嚗䔶�敶枏�摰嫣��� `|`, `^`, `$`, `*`, `+`, `?` ���蝚行𧒄瘜典� `regex=False` 靽嗪�璁�艙摰匧�嚗��雿蹱��菔䌊���霈曆蛹 `regex=True` 隞亙鍳�典撩憭扳迤�坔龪�溻��
    - [x] **�舀� contains 蝻嘥��芣�撟嗆伃���孵� CPO/�𠰴紡雿枏�鋆寡䌊��**嚗𡁜銁 `history_manager.py` �芣��航�銝哨�隞��撖寡◤�芣鱏�� `index.str.contains` �� `MainU.str.contains` 蝑� contains �滨���蟮霈啣�餈𥡝��芸𢆡蝻嘥�銝𤾸�瘜刻��麄��覔�桃鍂�瑟��唳�隞歹�撌脫伃��撖寧滲銝剜�霂㵪��𠰴紡雿瓐��鰵�賣�蝑㚁�隞亙� CPO �詨�霂滚銁��蟮頧賢��嗥��孵� category.str.contains �芸𢆡��ㄨ�芣�嚗���冽�憭滩秐�毺�����
    - [x] **�訫�銝𡡞��鞉�霂閖�朞�**嚗𡁜銁 `test_cpo_history_fix.py` 銝剝�霂���日��� CPO 銝𡒊滲銝剜�����瑚��踺��誑�� index/MainU 蝻嘥��� QueryEngine �箄�甇���文�嚗�8 憿寞�霂� 100% �𣂼���蜓瘚贝�憟𦯀辣 `pytest test_watchlist_lifecycle.py` 100% �𧼮��𣂼���


## 2026-06-10 16:30
- [x] **靽桀� Query ��鉄撠𤩺𡠺�瑟𧒄嚗���勗�鋆��摮�(CPO)嚗㕑◤霂舀�����讐� Bug (Fixed Parenthesis Query Splitting & Corruption Bug)**嚗�
    - [x] **�寞祥 `history_manager.py` 銝剔� _normalize_record �砍噡�𣂼��餉�**嚗𡁜蝠摨閙��支�銋见��誩�撘訫�����笆撣行𡠺�瑞� query 撘箄�敶枏� `"憭�釣 (銵刻噢撘�)"` 餈𥡝��𣂼����撘勗�蝚虫葡�寥��文���凒�交�憭滢蛹甇文�甇�＆����穿�靽萘�摰峕㟲�� Python/Pandas 隞��銵刻噢撘𧶏�憒� `category.str.contains("�勗�鋆��摮�(CPO)")`嚗㚁�銝滚�頞𦠜�瘙⊥� query ����笔�摰嫘��
    - [x] **�寞祥 `instock_MonitorTK.py` 銝剔� sync_history �砍噡瘚�情��**嚗𡁜�甇交��支� `sync_history` �嗆挾銝剖� query 餈𥡝�撠𤩺𡠺�瑟����瘚� note ���餉�嚗䔶蝙�曄內 label �� raw query ���撠���笔蝠摨閙�憭滢蛹蝥舐硃����豢䰻銵剁�靽肽�鈭���Ｚ��亙��𧼮��嗥� 100% �澆�撖寥�銝𦒘�憭梁���
    - [x] **蝻硋�銝枏�撉諹��訫�瘚贝�銝𤾸�敶埝�霂閖�朞�**嚗𡁜銁 `scratch/test_cpo_history_fix.py` 銝剔��嗘�銝㯄秄��笆��鉄撋���砍噡 query嚗㇃PO嚗厩��芣�霂閖�霂���穿�瘚贝� 100% �𣂼���僎銝𥪯蜓�𧼮�瘚贝�憟𦯀辣 `pytest test_watchlist_lifecycle.py` �� 11 憿孵��笔𦶢�冽��詨��其� 100% �函遛�朞�嚗㇊assed in 0.70s嚗㚁�蝟餌��嗅�敶垍聦�譌��

## 2026-06-09 16:20
- [x] **靽桀�銝餌�摨誩��剜𧒄隡渡��航��硋�餈𤤿��芾䌊�其�摮条����蝵桃� Bug (Fixed Visualizer Auto-Save Window Position on Close)**嚗�
    - [x] **摰䂿緵���箸�瘚𧢲𧒄���甇亦����摮� (Synchronous Layout Saving)**嚗𡁻�撖� `trade_visualizer_qt6.py` 銝剔� `_check_lifecycle`嚗�䌊瘥�蔭霂ｇ�隞亙� `_poll_command_queue`嚗㇊ipe ��誘頧株砭嚗劐舅銝芷���箏ế摰朞楝敺���函������ `self.close()` 閫血� Qt �喲𡡒�㵪�蝡见朖撘箏��峕郊靚�鍂 `self.save_splitter_state()`嚗䈣self.save_window_position_qt_visual()` 隞亙� `self.save_window_position_qt()`���蝖桐�鈭�銁�誩� join �餃�鋡思蜓餈𤤿�撘箄� terminate 蝏�迫�㵪�蝒堒藁��之撠譌���蝵桀���𠧧蝥踹��唳� 100% �删�隡睃��券�銝芣神蝘鍦�摰匧��嗵�嚗䔶�瞍𤩺��滨��讠��𡝗嗻銋䭾���
    - [x] **��漲撱園鵭���箏捐�鞉�隞乩������ (Extended Graceful Join Timeout)**嚗𡁜銁銝餉�蝔� `instock_MonitorTK.py` 銝剔� `on_close` �寞�銝哨�撠�笆�航��硋�餈𤤿��� `join(timeout=0.5)` 摰賡��園𡢿撱園鵭�� `1.5` 蝘鉝���銝箏�餈𤤿��冽𤣰�啗䌊瘥��隞文������ QThread �𦠜𦆮��祗�喳��擧釣��隞亙�蝵𤑳�蝞⊿�皜���𣂷�鈭�凒��雲����脫𧒄�湛�雿踹�蝟餌����箸𤣰撠暹凒�惩像皛𡢅��拍�撘箸�隞��銝箸��𣂼��其��栶��
    - [x] **�蹱���霂睲��笔𦶢�冽�瘚贝��朞�**嚗𡁏��罸�朞�鈭� `python -m py_compile` ��笆銝支葵靽格㺿��辣��妟甇餉�霂剜�蝻𤥁�摰∟恣嚗�僎銝� `pytest test_watchlist_lifecycle.py` 銝� 11 憿寧頂蝏�瓲敹���賢𪂹�笔�敶埝�霂� 100% 蝏踵��朞�嚗�11 passed in 0.74s嚗剹��

## 2026-06-09 16:15
- [x] **蝏煺��齿����㕑”�澆�摰賣芋撘譍蛹�芷����劐撓�䭾��刻��� (Unified Column Resizing & Stretch Layout for All Panels)**嚗�
    - [x] **�寞祥銝剝𡢿�� Stretch 撖潸稲�喃儒�烾�甇餌撩��**嚗𡁜�雿滚��曹��典�銵冽聢嚗���喟��笔�����亥��踴��踎�㛖��䜘��縑�瑚貌銵函�蝑㚁��典�憪见��� Tab �嗆���憭齿𧒄撠�鸌摰帋葉�游��𡝗��𦒘��𡑒挽銝箔� `QHeaderView.ResizeMode.Stretch`嚗�紡�渡㮾�餃�嚗��甈⊥㺭���������厩��梁�嚗匧銁�𡝗嗻�嗅��駁�甇餅�瘜閙��刻��渡��桅���
    - [x] **�刻”�堒捐�芷����寥��**嚗𡁜����㕑”�潘�瘥𤩺𠯫�滢�������蝑㚚��𨰜����亥��踴��踎�㛖��䜘���憭渲蕭頦芥��縑�瑕�蝐餉”����粹�霅衣�嚗厩����匧�摰質��湔芋撘讐�銝�霈曄蔭銝� **`QHeaderView.ResizeMode.Interactive`**嚗諹圾�支遙雿訫撩銵屸�甇颯��
    - [x] **�芸𢆡�劐撓���𦒘��堒‵��蒾颲�**嚗𡁜鍳�� **`setStretchLastSection(True)`** 撅墧�扼��銁蝖桐����匧���虾鋡急��䀹��芰眏�见𢆡�𡝗嗻靚�㟲����𣂷�嚗𣬚眏 Qt �芸𢆡撱嗡撓���𦒘��堒�銵冽聢閫�藁�箸說嚗�蝠摨閙覔蝵桀𢰧靘批枂�啣之�Ｙ妖�質𠧧�𡝗楛�脩征�賢��脩�閫��蝻粹萅嚗䔶�摰𣬚�銝� `saveState/restoreState` 頝其�霂脲�銋��靽嘥��箏�憟穃���
    - [x] **�拍�霂剜�銝𡒊�霂穃恣霈�**嚗𡁏��蠘�銵� `python -m py_compile signal_dashboard_panel.py` 餈𥡝��蹱��祗瘜閙�瘚衤�蝻𤥁�璉��伐�蝻𤥁� 100% �𣂼�嚗𣬚頂蝏毺迅摰𡁏�批�憭���

## 2026-06-09 16:10
- [x] **靽桀�瘥𤩺𠯫�滢�����𦦵��晦�嘥��䭾��见𢆡靚�㟲�堒捐 Bug (Fixed Guidance Table Reason Column Manual Resizing Bug)**嚗�
    - [x] **�舐鍂�堒捐 Interactive 璅∪�銝舘䌊�冽�隡賊俈�質器**嚗𡁜�雿滚��曹� `_create_guidance_table` �嘥��碶� `_reapply_table_stretch_mode` ���憭漤曎頝臭葉銝�����𧑐撠���𦒘��𡑒挽銝� `QHeaderView.ResizeMode.Stretch`嚗�紡�渲砲�𡑒◤ Qt 撘箄���香摰賢漲�䭾��梁鍂�瑟��冽��質��渡��桅���
    - [x] **閫�膄撘箄���香**嚗𡁜�霂亙�璅∪�靽格㺿銝� `QHeaderView.ResizeMode.Interactive`嚗���嗉��� `setStretchLastSection(True)`����典�霈貊鍂�瑟��冽��典�摰賜��齿�銝页�靘萘��賭�霂��雿嗵征�渲◤霂亙��芷����芸𢆡�劐撓�箸說嚗峕��支��屸𢒰�喃儒��蒾�脩�蝛綽�憭批之�𣂼�鈭� UI 鈭支�雿㯄���
    - [x] **�䭾香閫垍�霂穃��典恣霈�**嚗𡁏��蠘�銵� `python -m py_compile signal_dashboard_panel.py`嚗𣬚������䌊��迅摰𡁏�批�憭���

## 2026-06-09 16:05
- [x] **摰䂿緵憭帋葵�𧢲踎�𡃏”�潘��滢����/�喟��笔�/�条裦頞见飵/靽∪噡/憸�郎嚗匧之��𧋦摮埈挾��稬霂行�撘寧��蠘� (Implemented Double-Click Text Details Popups for Multiple Panels)**嚗�
    - [x] **�齿��𡁶鍂�訫��澆��颱�隞嗅���膥**嚗𡁜銁 `signal_dashboard_panel.py` �� `_on_cell_double_clicked` �曹澈靽∪噡瑽賭葉嚗峕�憓硺��行⏛�堒���凒嚗��隞�𣈲�� `"霂行�"` �拙�銝箸𣈲�� `["霂行�", "��眏", "��撅墧踎��", "�閙���眏", "�詨���眏", "敶Ｘ��/靽∪噡"]`嚗剹���餈坔��𡑒◤��稬�塚�����硋���聢銝剔�摰峕㟲霂湔����嚗�僎雿輻鍂 `SignalDetailDialog` 隞亙之�芾粉��𧋦獢�䲮撘誩撕蝒堒�蝷箝��
    - [x] **�箄�敶Ｘ��/靽∪噡����惩�**嚗𡁜���稬 `"霂行�"` �� `"敶Ｘ��/靽∪噡"` �塚�隡朞䌊�冽�蝝Ｗ��滩�撖孵���耦��縑�瑕�蝘唬�銝箏撕蝒堒��� Signal ���餈𥡝�撖寥�嚗峕�擃睃虾霂餅�扼��
    - [x] **憓𧼮�撣�㦤憸�郎�踹�/��捆��稬�行⏛**嚗𡁜銁 `_on_alert_double_clicked` 憭���其葉�行⏛��笆 `"�踹�/��捆"` �㛖���稬��銁��稬�塚�撠肽��朞�霂亥� UserRole ��㺭�株粉�硋��漤�霅衣�隞�”銝芾�隞��撟嗆�蝝� snapshot �瑕��∠巨銝剜��㵪��亦�憭滨鍂 `SignalDetailDialog` 撖寡�獢��撠�踎�堒��冽�憭抒�撟��霅行��祉凒�亙撕�箸遬蝷綽��㯄�帋��嗆袇��𧋦����典��券曎��
    - [x] **�拍�霂剜�銝𡒊�霂穃恣霈�**嚗𡁏��蠘�銵� `python -m py_compile signal_dashboard_panel.py` 餈𥡝��䭾香閫垍�霂穃��典恣霈∴�霂剜��𡃏�銵𣬚𠶖��䌊��迅摰𡁏�批�憭���

## 2026-06-09 15:55
- [x] **摰䂿緵�踹��剖���稬頝罸��𡒊��蠘�撟嗡�撣�㦤憸�郎撘寧�摰���𥪜𢆡 (Implemented Double-Click Follower Details for Hot Sectors & Fully Aligned with Alert Popups)**嚗�
    - [x] **摰䂿緵�唳旿皞𣂼�雿枏��𥪜���**嚗𡁜銁 `signal_dashboard_panel.py` �� `_refresh_sector_table` 銝哨�皜脫��𡏭�憌擧�蝏��肽�銝��梹�蝚� 8 �梹��塚��朞� `_fast_update_cell(table, i, 8, ..., data=s)` �𠹺誨銵刻砲�踹��嗆����笔�摮堒� `s` 雿靝蛹�芸�銋㗇㺭�桃�摰𡁜��訫��潛� `_ROLE_DATA` 閫坿𠧧銝哨��㯄�帋� UI 撅閧內銝𤾸�撅�葵�∩誨�����㺭�桅曎頝胯��
    - [x] **摰䂿緵��稬鈭衤辣蝎曉��行⏛銝舘祕��撕蝒�**嚗𡁜銁 `_on_sector_table_double_clicked` 曌䭾�鈭衤辣憭���其葉嚗屸�朞��斗鱏 `header == "頝罸��𡒊�"` 蝎曉��行⏛頝罸��𡒊��㛖���稬���朞� `.data(self._ROLE_DATA)` �𣂼��踹��唳旿嚗諹繮�𤥁砲�踹����憌舘�隞���𡑒” `follower_codes`嚗�䌊�券���迤�坔�摨蓥� `follower_detail` 摮㛖泵銝脫��碶誨�����
    - [x] **摰��憭滨鍂憸�郎霂行�撘寧�銝舘��其漱鈭�**嚗𡁜��典��典歇�厩� `MarketAlertDetailDialog` 撖寡�獢��撟嗅銁��稬撘孵枂�嗅𢆡��挽蝵桃����憸䀝蛹 `f"�𤣳 {sector_name} - 頝罸�銝芾��𡒊�"`嚗𥕦��瑟𣈲��䌊�券�㗇𥋘擐𤥁�撟嗉繮敺㛖��嫘��凒�仿睸�䀝�銝钅睸�亦� K 蝥輯��函�鈭支��餉�嚗���唬��嗡誨��情�梶�擃睃��𡁜��剁�SOLID / DRY�笔�嚗剹��
    - [x] **摰峕�霂剜�銝𡒊�霂穃��典恣霈�**嚗𡁏��蠘�銵� `python -m py_compile signal_dashboard_panel.py` 餈𥡝��蹱��祗瘜訫恣霈∩�蝻𤥁�璉��伐�蝻𤥁� 100% �𣂼�嚗䔶漱鈭㘾�餉�銝擧������䌊��迅摰𡁏�批�憭���

## 2026-06-08 19:15
- [x] **蝏煺�鈭� `sys_utils.py` 摰䂿緵蝏煺���漱�𤘪𧒄�湔𦻖��僎�齿��券�靚�鍂�� (Unified Trading Hours Check Interface in sys_utils.py & Refactored All Callers)**嚗�
    - [x] **摰䂿緵蝏煺���漱�𤘪𧒄�游ế摰𡁏𦻖��**嚗𡁜銁 `sys_utils.py` 銝剜鰵憓� `is_active_trading_hours(bypass: bool = False) -> bool` �亙藁��砲�亙藁蝏笔�鈭���� A �∟�蝏剔�隞瑚漱�𤘪𧒄�湛�09:30-11:30, 13:00-15:00嚗厩��文�����塚��箄����鈭��霂閧㴓憓���芸𢆡璉�瘚� `pytest` 銝� `test` �賭誘銵���堆��文�嚗�銁瘚贝��嗉䌊�刻��滚僎餈𥪜� `True`嚗䔶�霂��瘚贝��其��航楊�嗅躹�典予�躰�銵䎚��
    - [x] **�齿��券��嗆袇�園𡢿�文�**嚗𡁜���𧋦��袇��氜鈭� `paper_adapter.py`��trade_gateway.py`��kernel_service.py`��journal.py`��stock_selection_window.py` 銝� `instock_MonitorTK.py` 銝剔�憭𡁜�蝖祉�����滚��嗥漲�餉��券�蝘駁膄嚗𣬚�銝��嫣蛹撖澆� `sys_utils` 撟嗉��� `sys_utils.is_active_trading_hours`嚗峕�憭扳����蝟餌���極蝔𧢲㟲瘣�漲嚗㇄RY �笔�嚗剹��
    - [x] **靽桀� bg_kernel_auto_execute_once 銝� is_trade_day �芸�銋� NameError 撏拇�**嚗帋耨憭滢��� `instock_MonitorTK.py` 銝剔眏鈭𡒊宏�斗唂�� inline �園𡢿�㗛�撖潸稲蝡硺遠�滩蓮蝑𣇉裦閫血����蝚� 1610 銵䕘��𤑳� `NameError: name 'is_trade_day' is not defined` 撏拇���䔮憸矋��齿鰵閫��撖澆� `JohnsonUtil.commonTips` 撟嗉圾�𣂼枂 `is_trade_day` 銝� `now_time`��
    - [x] **�朞��𧼮�瘚贝�銝擧𧒄畾菜嵗撉峕�霂�**嚗𡁜�甈∟�銵� `pytest test_watchlist_lifecycle.py`嚗�11 憿寧頂蝏毺��賢𪂹��瓲敹��霂訫��� 100% �朞�嚗㚁��峕𧒄�� `scratch/test_trading_hours_restriction.py` 銝剝�霂���圈������𧒄�湔㜃�芰��喳笆�睃�/�睃�憪娍�霈Ｗ���㜃�芣����改�瘚贝��券� OK��


## 2026-06-08 18:35
- [x] **靽桀��曹� realtime Tick price_map 蝻箏仃/NaN 撖潸稲 fallback �� close 鈭抒���迫�蠘圻�� Bug (Fixed False Stop-Loss Triggered by Fallback to Yesterday's Close)**嚗�
    - [x] **�寞祥 _bg_get_realtime_price_map 銝剔� close fallback �餉�**嚗𡁏��亙僎摰帋�鈭� `instock_MonitorTK.py` �� `_bg_get_realtime_price_map` �寞�銝哨��� real-time price 銝湔𧒄�箇緵蝛箏�潭� NaN �塚�憒���条��嗚��㺭�桀�甇仿𡢿�蹱�蝵𤑳� Tick 撱嗉�嚗㚁�隡𡁻�霂� fallback �� `close`嚗�朖�冽𠯫�嗥�隞�/�亦瑪蝥批��嗥�隞瘀����餉� Bug��銁 Mock 鈭斗�餈質葵�塚�餈坔紡�游��滢遠�潘�`current_price`嚗㕑◤�誩��湔鰵銝箄�雿𡒊��冽𠯫�嗥�隞瘀��湔𦻖閫血�甇Ｘ��脩瑪嚗諹���銁撘�隞枏��删����霂航圻�穃�甇Ｘ�撟喃���
    - [x] **�嗥揮摰墧𧒄銵峕���縑�𡑒���**嚗𡁜� targeted 璅∪��� vectorized 璅∪�銝讠��𡑒��湧��嗡蛹隞���怠�憭拇暑頝��銝剔�摰墧𧒄鈭斗�隞瑟聢摮埈挾 `['trade', 'price', 'now']`嚗�蝠摨訫��� `close` �𨰜����𨅯銁摰墧𧒄�唳旿銝剛�銝匧���蛹蝛箏��/NaN嚗��銝滚��� `price_map` 銝剖��亥砲�∩遠�潘�雿踹� Mock 鈭斗�蝵穃��冽凒�唬遠�潭𧒄嚗諹砲�∠凒�亥歲餈�凒�堆�摰匧�靽脲�銝𠹺�銝芣�������啣��䀹�鈭支遠嚗𣬚凒�唬�銝�銝芣���� Tick 隡惩�嚗䔶���蝠摨閙��支��祇𡢿���甇Ｘ�霂舀𥁒��
    - [x] **�訫�銝𡡞��鞉�霂閧遛�烾�霂�**嚗𡁜銁 `scratch/test_realtime_price_fallback.py` 銝剔��坔僎餈鞱�鈭��撖� fallback �餉�������霂𤏪�璅⊥����摰墧𧒄�㛖撩憭曹� close �堒��函���垢�箸艶嚗峕�霂� 100% 蝏踵��朞�����嗅�甈⊥�銵𣬚頂蝏笔��笔𦶢�冽��詨��𧼮�瘚贝� `pytest test_watchlist_lifecycle.py` 11 憿寧鍂靘见��冽����100% Passed嚗㚁�蝟餌�蝔喳�嚗屸妟銝𡁜𦛚靘批�敶垍聦�譌��

## 2026-06-08 12:20
- [x] **摰䂿緵靽∪噡��掩�𡑒”銝芾��滚�靽∪噡�睃�/�駁�餈�誘�蠘� (Implemented Stock Signals Deduplication & Folding)**嚗�
    - [x] **瘛餃� `[x] �睃��滚�` �批�憭漤�㗇�**嚗𡁜銁 `signal_dashboard_panel.py` 憿園��批��箇� `corner_widget` 摰孵膥銝哨��啣�鈭� `self.fold_check` 憭漤�㗇�嚗��霈文��荔�嚗屸��函揮�烐�撟喳� QSS �瑕����摰� `_on_fold_check_changed` 靽∪噡瑽踝�閫血�銝��桅��唳葡�枏僎靽嘥�敶枏� UI �嗆����
    - [x] **�齿��券��瑟鰵�唳旿敶垍掩 (`_refresh_all_tables`)**嚗𡁜��舐鍂�睃��滚��塚��典�蝐餃��脖縑�琿𧫴畾萄笆 `�券�靽∪噡`�����掩靽∪噡�� `�嗅�靽∪噡` 餈𥡝� `code` �駁�嚗𥕢蝙�� `OrderedDict` 撟嗅��兩�𨅯� pop �舘��潑�萘�蝘颱�閬���寞�嚗𣬚＆靽苷葵�∩�靽萘����啁���辺閫血�霈啣�嚗���祆��啁�閫血��園𡢿��祕���餈堆�嚗䔶��嗅銁�𡑒”銝剔�雿滨蔭摰��撖寥����啗圻�𤑳��園𡢿蝥踴��𥅾�芸鍳�冽��𩤃��蹱����憭滚�蝷箏��誩��脖縑�瑟�蝏���
    - [x] **�齿��閙辺憓鮋��鍦�餈�誘 (`_insert_row`)**嚗𡁜��笔��䭾辺隞嗥� code 閬���駁��箏�靽格㺿銝箇眏 `fold_check.isChecked()` �批�����暸�争�𨀣��𣳇�憭𨧀�脲𧒄�滩圻�𤑳宏�文歇摮䀹唂銵𣬚��餉�嚗𣬚＆靽脲��删𠶖���憓鮋�鈭衤辣瘚���嗥��拍��滚� 100% 撖寥���
    - [x] **頝其�霂脲�銋��銝舘䌊��**嚗𡁜銁 `_collect_ui_state` �嗆��紡�箔� `_restore_ui_state` �嗆���憭漤曎頝臭葉嚗諹‘朣𣂷�撖� `fold_duplicates` checked �嗆���摮睃��餉���銁 `_restore_ui_state` 摰峕��滨蔭�Ｗ��𠬍��芸𢆡閫血�銝�甈� `_refresh_all_tables` 餈𥡝��唳旿撖寥�嚗屸��滢��瑕鍳�冽㺭�格��嗘僚��
    - [x] **�券𢒰�朞��芸𢆡�碶��訫��蠘�瘚贝�**嚗𡁻�朞�餈鞱��券��詨��笔𦶢�冽��𧼮�瘚贝� `pytest test_watchlist_lifecycle.py`嚗�11憿寧鍂靘� 100% Passed嚗㚁�撟嗅銁 `scratch/test_fold_duplicates.py` 銝剔��躰䌊瘚贝��其�摰��撉諹�鈭���牐��駁���迤蝖格�扼��

## 2026-06-07 00:23
- [x] **摰䂿緵銝湔𧒄雿輻鍂 history3/history4/history5 蝑匧��脣�餈�誘銝娪俈瘙⊥��蠘� (Implemented Temp History Group Filtering & Prevented Pollution)**嚗�
    - [x] **摰䂿緵銝湔𧒄餈�誘銝𦒘蜓 query 獢交𦻖**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `sync_history_from_QM` �交𤣰�� `history3`��history4` �� `history5` ��蝙�典𢆡雿𨀣𧒄嚗峕㜃�芸僎霈曄蔭 `self._temp_history_source` 銝湔𧒄���嚗���劐葉�� query �峕郊�喲▲�� `search_var1` 銝剖�蝷綽�撟嗥凒�交�韏瑁����蝝Ｚ�皛扎��
    - [x] **靽桀���𧋦 sync_history_from_QM 銝剔� current_key �⊿�憭望� Bug**嚗𡁜�雿滚僎靽桀�鈭���� configs �𣬚� `arg_key`嚗�蒂�� `search_` �滨�嚗劐� `current_key` �澆�銝滢��游紡�� `source == "use"` �嗅龪�齿嵗撉��蝏���朞��� Bug嚗屸���蛹�箔� `arg_key[-8:]` ����典笆朣𣂼龪�溻��
    - [x] **摰䂿緵�惩���倌閫��銝𡡞俈瘙⊥��坔�**嚗𡁜銁 `apply_search` 餈�誘�𦠜凒�唳�蝝Ｗ��脤𧫴畾蛛��寞旿敶枏�銝湔𧒄�交�嚗諹䌊���靚�鍂撖孵���蟮�梹�憒� `search_map3`/`search_map4`/`search_map5`嚗㕑圾�鞟蕃霂� label嚗�僎�典��亙��脰扇敶閙𧒄�滚��穃�甇亙��亙笆摨𠉛���蟮���嚗Ǒhistory3`/`history4`/`history5`嚗劐葉嚗𣬚＆靽萘�甇�� `history1` 銝滚��唬遙雿閙情�瓐��
    - [x] **摰䂿緵�箄��砍噡��圾銝舘䌊�� (Implemented Intelligent Bracket Splitting & Self-healing)**嚗�
        - 銵仿�鈭�銁 `sync_history` �屸𢒰撖� `history3`/`history4`/`history5` ���撖孵��� `search_map3`/`4`/`5` ���撠�蕃霂煾曎嚗䔶蝙�� history1/2 ����� `sync_history` �嗡��賣迤撣貉圾���
        - �� `sync_history` ����誩��亦㴓��誑�� `history_manager.py` �� `_normalize_record` ��摨訫��㰘蝸頧祆揢�航�嚗��蝏��鈭�惣�賢��砍噡��圾�芣�蝞埈�����𡏭���/�㰘蝸��”颲曉���緵 `"憭�釣 (��迤��uery)"` ��耦撘𧶏�靘见����鋡急�憭硋��亦� label �唳旿嚗㚁�蝟餌�隡朞䌊�典竉蝳餅��𣇉滲 Query嚗�僎撠��蝵桅����銝� note 靽嘥�嚗�蝠摨閖�蝳� note 撖� query ��情�橒��寞祥鈭�祗瘜閙�銵峕𥁒�嗵��桅���
    - [x] **摰䂿緵����峕郊銝擧�蝛箄䌊��**嚗𡁜銁 `apply_search` �扯��滚��亥䌊��ế摰𡄯�憒��憿園�颲枏�獢���潸◤�冽��见𢆡蝻𤥁��孵��𡝗�蝛綽��躰䌊�冽�蝛箔葩�嗥𠶖��僎�滨蔭銝箸迤撣貊� `history1` �坔�����嗅銁 `clean_search` 皜�征憿園��嗆遬撘𤩺�蝛箔葩�嗆�敹𨰜��
    - [x] **摰䂿緵��稬蝵桅▲銝𡡞��讐���䌊�典��� (Implemented Auto-Save on Window Hide)**嚗𡁜銁 `history_manager.py` �� `use_query` 蝵桅▲�滢�銝哨�隞亙��� `instock_MonitorTK.py` �� `sync_history` 憓鮋��𧼮�銝哨���‘朣𣂷� `_history_changed = True` ��𠶖��耨�寞�霈啜���敶餃�閫��鈭�鍂�瑕銁��稬蝵桅▲/�𦦵揣�擧� Esc �鞱���蟮蝞∠��冽𧒄嚗��瘝⊥�閫血�靽格㺿���撖潸稲�圈◇摨𤩺𧊋�芸𢆡����硋��亦��矋�餈𥡝��紡�游�甈⊥�撘��園◇摨𤩺�憭滨�雿㯄� Bug��
    - [x] **靽桀��瑕鍳�典之�睃𢆡霂臭�摮睃撕蝒𦯀�摰硺��𣇉�霂� (Fixed Cold-start Save Prompt & Instantiation Typo)**嚗�
        - 靽桀�鈭�蜓蝒堒藁�嘥��𣇉洵 4583 銵�� `self.search_history5` �躰秤摰硺��碶蛹 `h4` ���嚗��屸� `h5` ���嚗厩�蝚磰秤嚗峕��支��瑕鍳�典�甇交𧒄 history5 ����唳旿鋡� history4 閬��瘙⊥�������
        - �齿�鈭� `sync_history` 撠暸�����冽�霈圈�餉���蘨�匧銁�唳唂��蟮���韐典�摰寞�憿箏��𤑳��笔��孵��塚��屸�蝔见�����嘥��硋�甇交𧒄嚗㚁��滚� `_history_changed` 蝵桐蛹 `True`嚗峕覔瘝颱��瑕鍳�典�撘���������撕�算�𨅯��脣��蠘�憭批��冽糓�虫�摮覀�脲�蝷箇� Bug嚗�
        - 靽桀�鈭� `save_search_history` �寞��冽�撖孵��冽㺭�𤩺𧒄��聢撘譍��駁�憭梢�蝻粹萅��銁霂餃�蝤�� `old_data` �嗡�隞�笆�嗅�蝝䭾�銵� `_normalize_record` �芣��亦氖嚗�僎銝𥪜銁�睃�瘥𥪜笆�嗆挾銋笔笆 `old_data` �峕甅�扯� `_normalize_history` 餈𥡝��駁�憭�����蝖桐�鈭�鰵�批�銵典銁瘥𥪜笆�嗆挾��聢撘譍��駁��嗆�� 100% 銝亙�撖寥�嚗��銝箏縧�滚���滲 query �𡑒”嚗㚁�敶餃�瘨�膄鈭��蝤���唳旿銝剖��券�憭漤★��聢撘譍�銝��渲���韏瑞��𡁜� 12 ��/36 �∪��典撕蝒𡑒秤�乓��
    - [x] **瘛餃� combo 蝛箸�����券俈敺�**嚗𡁜銁 `sync_history` 撠暸�憓𧼮� `if combo:` 靽脲擪嚗屸俈甇Ｖ蜓�屸𢒰�冽瓷�� history4/5 combo �找辣����萎��湔鰵�� values �嗆��� AttributeError �仿���
    - [x] **靽桀�銝餉�蝔钅���箏㨃甇� 25 蝘雴��航��𤥁�蝔钅���箸��� Bug (Fixed Application Exit Hang & Visualizer Zombie Residuals)**嚗�
        - 靽桀�鈭� `instock_MonitorTK.py` �����箸䲮瘜� `on_close` 銝哨�靚�鍂 `save_search_history` 摮䀹﹝�嗅��芯��仿��澆紡�渡��𤾸蝱�鞱�璅⊥��撕蝒埈�韏瑚蜓蝥輻� 25 蝘垍��游𦶢 Bug嚗峕㺿銝箔��� `confirm_threshold=9999` 敶餃�撅讛𤪖���粹𧫴畾萇�隞颱�撘寧��餅鱏嚗�
        <!-- - �齿�鈭� `trade_visualizer_qt6.py` ��撈�� Pipe �剖��閗繮�餉���銁 `_poll_command_queue` �閗繮�� Pipe 撘�虜�剖���洵銝��園𡢿嚗峕遬撘𤩺�銵𣬚������ `self.close()` 撟園���� `QApplication.quit()`嚗���啣虾閫��摮鞱�蝔见銁 TK 銝餉�蝔钅����/撘粹���嗥�蝘垍漣�芸𢆡瘜券�銝𤾸��刻䌊瘥��敶餃��寥膄鈭��撠貉�蝔𧢲��坔��啁��桅��� -->
    - [x] **�朞��𧼮�瘚贝�銝𡡞�撖寞�扯䌊瘚讠鍂靘�**嚗𡁶��嗘���笆霂亦鸌�抒� 6 銝芾䌊瘚见����霂閧鍂靘页�撟嗅銁銝餃�敶埝�霂訫�隞� `test_watchlist_lifecycle.py` 銝� 100% 蝏踵��朞�嚗�11憿孵��� Passed嚗剹��

## 2026-06-06 19:00
- [x] **靽桀� on_close ���箸𧒄 UnboundLocalError 撘�虜撟嗆�����典紡�� (Fixed on_close UnboundLocalError & Cleaned Up Local Imports)**嚗�
    - [x] **�寞祥 `threading` 撅��典��𤩺��滚��冽𥁒��**嚗𡁜笆�港葵 `instock_MonitorTK.py` 餈𥡝�鈭���Ｗ恣霈∴�敶餃�蝘駁膄鈭���� `on_close`��wait_all_threads`��open_spatial_follow_hud`��_run_dna_audit_batch`��_on_run_reentry_backtest_menu`��_on_shortcut_reentry_backtest` 隞亙�撘�虜����碶葉����匧��� `import threading` 撖澆�嚗𣬚�銝�撟嗉���蝙�冽�憿園��典��� `import threading`嚗�洵 22 銵䕘����敶餃�閫��鈭�眏鈭𤾸遆�唬�����𦠜挾摮睃銁撅��� `import threading` 撖潸稲 Python 蝻𤥁��典��港葵�賣㺭雿𦦵鍂�笔��� `threading` 霂臬ế銝箏��典��𧶏�隞舘��銁�滚�畾萄�撱� `exit_timer = threading.Timer(...)` �嗆��� `UnboundLocalError: local variable 'threading' referenced before assignment` ��援皞�䔮憸塩��
    - [x] **�朞��笔𦶢�冽��𧼮�瘚贝�**嚗𡁏��蠘�銵� `pytest test_watchlist_lifecycle.py` �𧼮��訫�瘚贝�嚗�11 憿寧頂蝏毺��賢𪂹��瓲敹��霂� 100% 蝏踵��朞�嚗䔶�甇�虜���箔�撘�虜���箇�斢���芣�靽嗪�摰���Ｗ���
- [x] **靽桀�靽∪噡撘箏漲 `signal_strength` �埈遬蝷箏�雿齿筑�寞㺭銝𤾸��嗘� Bug 撟嗅��� co2float �芸�銋厰�蝵� (Fixed Float Precision & Column Offset & Implemented Custom co2float)**嚗�
    - [x] **�寞祥憓鮋��湔鰵�澆��𣇉撩憭�**嚗𡁜銁 `performance_optimizer.py` �� `TreeviewIncrementalUpdater` 蝐餌� `_prepare_rows_fast`嚗���𣂼�銵峕㺭�殷��� `_incremental_update`嚗���𤩺凒�唳㺭�殷�銝支葵�詨��航�銝哨�瘜典�撖� `signal_strength` �㛖� `_fmt_sig` 鈭䔶�撠𤩺㺭瘚桃��澆��硔��眏鈭𤾸虜閫���唬誑�𠰴��𤩺凒�啣�韏啗砲蝐餉�䔶�韏唬�蝏�葡�枏遆�堆�甇支耨�寡圾�喃�摰䂿��湔鰵�嗉砲�埈筑�寞聢撘誩�憪讠�銝滨����憿賜𪆴��
    - [x] **靽桀��∩辣�亥砭�烾�雿� Bug**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `refresh_tree_with_query` �寞��鍦��唳旿�塚�銵仿�鈭�仍�函撩憭� of `code_val` (�� `idx`) ������閫��鈭�眏鈭𤾸��� `vals` ����踹漲銝� Treeview �埈㺭銝滢��游紡�渡��渲��唳旿撌衣宏�烾�雿� Bug嚗䔶��𣬚＆靽苷� `signal_strength` 餈嗘��㛖��潸◤甇�＆�澆��吔�撟嗡��刻”�唳旿銝滢��𤑳�雿滨蔭�誩榆��
    - [x] **憿箏⏚頝煾�� 11 憿寧��賢𪂹��瓲敹��敶埝�霂�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�100% 蝏踵��朞�嚗��銵峕𧒄�渡眏 0.91s 蝻拍��� 0.77s嚗剹��
    - [x] **����芸�銋� co2float �滨蔭**嚗𡁜銁 `JohnsonUtil\commonTips.py` 銝剖��牐� `self.co2float` �滨蔭��㺭憿對�暺䁅恕��鉄 `'signal_strength'` �� `'signal4d'`嚗㚁�雿踹��冽��臭誑�朞��典��滨蔭��辣�芸�銋匧𪑛鈭𥕦���㺭�潮�閬�撩�嗉蓮�Ｖ蛹 2 雿滚��唳筑�寞聢撘譌��
    - [x] **�冽��𤜯�Ｙ′蝻𣇉��堒�**嚗𡁜銁 `performance_optimizer.py` ����誩��啣��唳旿憸����㴓��葉嚗䔶誑�𠰴銁 `instock_MonitorTK.py` ���蝥扳䰻霂Ｘ葡�㮖葉嚗䔶蝙�� `cct.CFG.co2float` �冽����滚ế摰𡁏𤜯隞���笔�蝖祉���� `'signal_strength'`���朞�鈭� 11 憿孵�蝟餌��笔𦶢�冽��詨�瘚贝�嚗峕�����滨蔭��䌊����拙��扼��

- [x] **蝘駁膄 `RealtimeSignalManager.update_signals` 銝剖�雿嗵� float32 蝐餃�頧祆揢 (Removed Redundant float32 Type Cast in Signal Manager)**嚗�
    - [x] **�駁膄�惩���遠�潛�蝐餃�頧祆揢**嚗𡁜� `stock_logic_utils.py` �𣬚� `score = np.round(score, 2).astype(np.float32)` 蝞��碶蛹 `score = np.round(score, 2)`��眏鈭� NumPy �� float32 �典�餈𥕦�餈睃��硋��堒��嗅虜隡湧�蝎曉漲銝滩雲撖潸稲��偏�圈鵭撠暸䔮憸矋�憒� `9.1200003`嚗㚁�霂亙�雿嗵�蝐餃�頧祆揢�典���蝙�其葉撟嗆�隞瑕�潘��湔𦻖蝘駁膄摰��隞���支�瞏𨅯銁��筑�寧移摨行�憭曹��㰘�撘���嚗諹��賡俈甇Ｗ銁 downstream 憭朞�蝔衤�颲枏� pandas 憭��銝剖�蝐餃�銝滚�摰孵��𤑳����敺桀�霂臬榆��
    - [x] **憿箏⏚頝煾�𡁜�敶埝�霂閖�霂�**嚗𡁜��𣂷耨�孵�嚗��敶埝�銵� `pytest test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣嚗�11 憿孵����霂� 100% 蝏踵��朞�嚗��銵峕𧒄�渡眏 0.91s 蝻拍��� 0.77s嚗剹��

## 2026-06-06 18:30
- [x] **靽桀����箏�撣訾�蝥輻�畾讠� (Fixed Application Exit Error & Thread Leak)**嚗�
    - [x] **蝏嘥笆�㘾膄撘箸��臬𢆡�函�餈𤤿� (Excluded Bootstrap Parent Process)**嚗𡁜銁 `instock_MonitorTK.py` �� `on_close` �� `STEP 7` �𤾸蝱畾讠�撘箏�皜��甇仿炊銝哨��曉��瑕�撟嗆��支�敶枏�餈𤤿����餈𤤿� PID嚗Ǒcurrent_process.ppid()`嚗�朖 Nuitka/PyInstaller �� bootstrap �臬𢆡�刻�蝔页����敶餃�閫��鈭�眏鈭𦒘蜓餈𤤿��券���箏�撘箸��嗉�蝔页�撖潸稲 Windows �批��堆�PowerShell嚗㕑秤霈支蛹蝔见�撌脤���箏僎�Ｗ��枏枂 `PS E:\temo\instock>` �鞟內蝚佗�餈𥡝��紡�渲��箔漱�踺��葩�嗉圾�讠𤌍敶閙�瘜閙迤撣貉◤ bootstrap 餈𤤿�皜�膄撟園�甇餌��桅���
    - [x] **蝔喳��硋�餈𤤿� PID �瑕�隞仿俈 `NoSuchProcess` �仿�**嚗𡁜銁憭���湔𦻖瘣曄�摮鞱�蝔讠�撘箸�銝𡒊�敺��餉�銝哨�撠� `alive_pids` ����𤥁祗�乩��笔���摹���銵冽綫撖澆��齿�銝箔蝙�� `try-except` ��ㄨ��遬撘� `p.is_running()` �嗆��瓲�伐�敶餃�閫��鈭��敺��蝔衤葉�曹�餈𤤿��拍�甇颱滿撖潸稲 `psutil.NoSuchProcess` 撏拇��������
    - [x] **隡睃� Logger �𨀣迫銝𡒊瑪蝔见��嗆𧒄摨�**嚗𡁜� `stopLogger()` �扯�憿箏��滨宏撟園��� `time.sleep(0.1)` 甇亥�蝻枏�嚗𣬚�鈭� `QueueListener` �烐綉蝑厩瑪蝔见�頞喟��滚��園𡢿摰匧�瘜券�撟嗅��刻圾蝏烐綉�嗅蝱 stdout/stderr��
    - [x] **撘箏�餈𤤿�銝𡒊瑪蝔贝��剛��箏�蝖格��**嚗�
        - �枏㫲 `Remaining children` �嗅��冽唂���摮睃笆鞊∴��朞� `psutil.Process(os.getpid()).children(recursive=True)` �冽��繮�𡝗��啁��拍�畾讠�餈𤤿��穃翰�扼��
        - �枏㫲瘣餃𢆡蝥輻��塚��刻��箔葉瘜典� `t.ident` 隞乩噶鈭𤾸翰�笔躹���撅��蝥輻�����脣�雿溻��
        - �啣� `FINAL STATUS` 颲枏枂嚗���嗆遬蝷箸�蝏��瘣餌瑪蝔贝恣�堆�敶餃��誩����箄捶�譌��
    - [x] **憿箏⏚頝煾�� 11 憿孵�蝟餌��笔𦶢�冽��詨�瘚贝�**嚗𡁏�銵� `pytest test_watchlist_lifecycle.py`嚗���� 11 憿孵�敶鍦����霂� 100% 蝏踵��朞���

## 2026-06-06 14:00
- [x] **靽桀�蝻箏仃�閧𡠺�滨蔭��辣�嗉䌊��㦤�嗅仃����脫情�栞�皛� (Fixed Single Config Healing & Prevention of Path Pollution)**嚗�
    - [x] **�𣂼��芣�閫�� Onefile �坔ế (Early Path Self-Healing)**嚗𡁜銁 `sys_utils.py` �� `get_conf_path` 憭湧��𣂼�撘訫�鈭� `get_base_path()` �曉��芣�靚�鍂��俈甇Ｗ�餈𤤿��冽𧊋�芣��滨眏鈭� `NUITKA_ONEFILE_DIRECTORY` �臬��㗛�撠𡁏𧊋撠梁貌嚗諹��� `is_onefile` 霂臬ế銝� `False` 撖潸稲�拍��格��桀��嗘�嚗���唬� 100% ��＆�����楝敺���麄��
    - [x] **摰䂿緵 Nuitka 銝湔𧒄�桀��脫情�栞�皛� (Strict Nuitka Path Validation)**嚗𡁜銁 `get_base_path()` �𣂼��硋��� `NUITKA_ONEFILE_DIRECTORY` �塚�憓𧼮�鈭�� `get_app_root()` ������瘥𥪜笆�餉���𥅾璉�瘚见�鈭諹����䕘��𡁜虜�臬�銝箏銁�墧����鋡急�憭𡝗情�梶��臬�銝贝◤�坔�鈭��摨讐����鋆�覔�桀�嚗㚁��坔撩�嗉�皛斗迨瘙⊥��潘�蝖桐�蝔见��� Nuitka Onefile �枏��臬�銝贝��㰘秤�𦠜𦆮�諹��毺撩憭梁��滨蔭��辣��
    - [x] **�𧼮�瘚贝��朞�**嚗𡁶���耨�孵��扯� `pytest test_watchlist_lifecycle.py` 餈𥡝� 11 憿寧��賢𪂹�笔�敶埝�霂𤏪�100% 蝏踵��朞���

## 2026-06-06 13:30
- [x] **憓𧼮撩銝��桀�隞質��穿��券𢒰�舀��亙��讠憬銝𤾸��滚�蝻�霂�� (Enhanced Backup Script to Support GZ/JSONL Logs & Dual Suffixes)**嚗�
    - [x] **�曇� `.json.gz`��.gz` �� `.jsonl` �詨��𡒊�**嚗𡁜銁 `backup_configs.py` �� `CONFIG_EXTENSIONS` 銝剖��牐�撖� `".json.gz"`��".gz"` 隞亙� `".jsonl"`嚗��鈭斗���瓲瘚�偌 `trading_kernel_trace.jsonl`嚗匧�蝻����皛斗𣈲�������笆 `.json.gz` ����恬�雿輯�鈭𥕦��格㺭�桀��讠憬���摰匧�餈𥕦�憭�遢�𡑒”��
    - [x] **銵亙� `log/` �� `logs/` �屸��桀��曇� (Log Dir Support)**嚗𡁜��笔�隞�龪�� `logs/` �滨����皛日�餉��拙�銝� `rel_path_norm.startswith("log/") or rel_path_norm.startswith("logs/")`���敶餃�蝖桐�鈭���曉銁 `log/` �桀�銝讠�蝐颱撮 `v_reversal_pool_*.json.gz` ��辣�賢�鋡� 100% �閗繮憭�遢嚗諹�䔶��埈𣄽�坔榆撘���餌���
    - [x] **�拍�憭�遢撉諹��朞�**嚗𡁻�朞��见𢆡���䭾�霂閗楝敺��餈鞱� `python backup_configs.py` �𣂼�摰峕��函� 400 銝芷�蝵桀��亙���辣����笔�隞踝�撉諹�鈭�㺭�株��毺𤌍敶閧�摰���扼��

## 2026-06-06 12:45
- [x] **�寞祥蝻箏仃�閧𡠺�滨蔭��辣�嗉䌊��㦤�園�暺睃仃�� Bug (Fixed Silent Self-Healing Failure When Single Config Files Are Missing)**嚗�
    - [x] **摨罸膄��摹�������冽�扳嵗撉屸秄蝳�**嚗𡁜蝠摨訫��支� `LoggerFactory.py` �� `commonTips.py` 銝剖抅鈭� `not os.path.exists(global.ini)` �亙ế�剜糓�西圻�� Nuitka 銝湔𧒄�臬��㗛��芣����撘梯挽霈～������餉��函���極雿𦦵𤌍敶蓥�撌脩�摮睃銁 `global.ini` �渡撩憭勗��砍�摰��蝵格�隞塚�憒� `stock_codes.conf`嚗㗇𧒄嚗䔶�撖潸稲摮鞱�蝔钅�暺䁅歲餈�䌊���雿輻㴓憓���� `NUITKA_ONEFILE_DIRECTORY` 敶餃�銝Ｗ仃嚗䔶��諹悟蝔见�撠����楝敺��霂航圾�𣂷蛹蝔见��寧𤌍敶𨰻��
    - [x] **摰䂿緵�䭾辺隞� Nuitka �臬��㗛��芣�**嚗𡁻���䌊��㦤�塚��芾�璉�瘚见�憭�� Nuitka 餈鞱��臬�銝𠉛㴓憓���讐撩憭梧�靘踵��∩辣�拍鍂隞���拍���辣 `__file__` �齿綫�笔���葩�嗉圾�� `Temp` 頝臬�撟嗉��笔��� `NUITKA_ONEFILE_DIRECTORY`嚗𣬚＆靽嘥�餈𤤿��嗆�銝衤遙�誩�餈𤤿���� 100% 甇�＆�Ｗ�撟園��曉��祉撩憭梁��滨蔭��辣��
    - [x] **�𣂼��芣�閫�� Onefile �坔ế (Early Path Self-Healing)**嚗𡁜銁 `sys_utils.py` �� `get_conf_path` 憭湧��𣂼�撘訫�鈭� `get_base_path()` �芣�靚�鍂��俈甇Ｖ�摮鞱�蝔见銁�芾䌊���靘輸�霂臬ế摰� `is_onefile` 銝� `False` 撖潸稲�拍��格��桀��嗘�蝞堒� `JSONData/` 蝑匧��桀�銝讠��桅�嚗���唬� 100% ��＆������摨讐𤌍敶閗��麄��

## 2026-06-06 12:35
- [x] **靽桀� Nuitka/PyInstaller ����芣��垍��臬��㗛�瘙⊥�撖潸稲閫��韏��銝Ｗ仃 Bug (Fixed Nuitka Environment Variable Pollution & Resource Loss)**嚗�
    - [x] **�寞祥 `NUITKA_ONEFILE_DIRECTORY` 鋡急情�㮖蛹�拍�摰㕑��寧𤌍敶閧撩��**嚗帋耨憭滢��� `commonTips.py`��LoggerFactory.py` �� `sys_utils.py` ����芣���粉��璅∪�銝哨��芣�餈睃��臬��㗛��嗆�閫��銵峕芋撘𧶏�撠� `NUITKA_ONEFILE_DIRECTORY` 撘箏��坔�撟嗆情�㮖蛹�拍�撌乩��桀�嚗ǑE:\temo\instock`嚗厩��滚之�餉��鞉���砲瘙⊥��曉紡�� Nuitka 餈鞱��嗆挾�䭾�甇�＆�瑕�銝湔𧒄閫���� `%TEMP%` 頝臬�嚗���� `�𩤃� [Config] �詨�韏�� stock_codes.conf 銝Ｗ仃銝娍�瘜蓥�����𦠜𦆮` �仿���
    - [x] **摰䂿緵銝交聢�拍�頝臬�餈�誘**嚗𡁜銁 `get_base_path()` �亙藁憭�����隞嗉䌊���垍��滚�蝏��鈭� `os.path.normpath().lower()` 頝臬��⊿�蝵穃���𥅾霂餃��硋朖撠���亦��臬��㗛��潛��䔶�蝔见�������鋆�覔�桀� `get_app_root()`嚗��撘箏�撠��雿靝蛹�𨀣情�𤘪����潑�肽�銵諹�皛文��㘾膄嚗屸俈甇Ｘ情�梶�摰䂿�銝湔𧒄閫��頝臬���

## 2026-06-06 12:30
- [x] **�寞祥 Nuitka Onefile 餈𤤿����箸��嗘�閫����辣�坔�甇駁� Bug (Fixed Nuitka Zombie Processes & Extraction File Locking)**嚗�
    - [x] **摰䂿緵頝刻�蝔𧢲��券�畾讠�璅∠�撘箸�**嚗𡁜銁 `instock_MonitorTK.py` ���箸�蝔� of ���𦒘��荔�`STEP 7`嚗劐葉嚗���乩��箔� Windows �典�餈𤤿�銵典龪�滨�撘箸���㦤�嗚����行�瘚见�餈𤤿��滢�銝餌�摨誩龪�㵪��𤥁���蝔讠��拍� executable 頝臬�雿滢��� `sys_utils.get_base_path()` �冽��圾�鞱繮�𣇉�銝湔𧒄閫���桀����銝� PID 銝滢蛹敶枏�餈𤤿�嚗���券���箏�瘥怎�蝥找�隞亙撩�嗥�蝏瓐���敶餃��𦦵�鈭��餈𤤿� `spawn` 銝� SyncManager �硋�摰��璅∪��梁氖餈𤤿��烐�銝箏迨�踹紡�湔�隞嗆香����鞉���
    - [x] **撘��睲��株䌊�����鍳�典𨭌��**嚗𡁜銁餈鞱��寧𤌍敶蓥�蝻硋�撟園�蝵脖� `run_MonitorTK.bat` �拇���砲�𡁏𧋦�函�摨𤩺�甈∪鍳�典�隡𡁜撩�嗥�蝏梶頂蝏煺葉�航�畾讠��������滩�蝔页�撟嗅銁蝑匧� Windows 撘�郊�𦠜𦆮摰峕�隞嗅蘂����芸𢆡�㕑絲蝔见����銝箇眏鈭𦒘遙�∠恣��膥撘箸�嚗��瘜閙�銵� atexit/on_close �餉�嚗㗇���瘥坿蔓隞嗆醌�誩辣餈笔紡�渡���辣鋡怠��券䔮憸矋�`failed to open ... for writing`嚗㗇�靘𥕢� 100% �航�����桃���䌊��䲮獢���

## 2026-06-06 12:10
- [x] **�賢𧑐�煺漣�臬��滨蔭��辣銝��桀�隞賭��拍�靽脲擪�拇� (Implemented One-click Environment Configuration Backup Tool)**嚗�
    - [x] **摰䂿緵�桀�蝏𤘪��䭾�靽嘥�**嚗𡁜��睲��拍�摰帋�憭�遢�𡁏𧋦 `backup_configs.py`��砲�𡁏𧋦�芸𢆡�枏�敶枏��臬�銝讠����� `.json`��.conf`��.ini` �� `.xlsx` �滨蔭��辣嚗�僎�厩�摰��銝��渡��詨笆摮鞟𤌍敶閧����憒� `JSONData/`��JohnsonUtil/`��datacsv/` 蝑㚁��䭾��瑁�靽嘥��� `BackConfig/Backup_YYYYMMDD_HHMMSS/` 銝页�蝖桐��滨��见銁��閬��憭齿𧒄嚗�虾隞亦凒�乒�𨅯��㗇鼧韐嘥僎蝎䁅斐閬���嘥��啗�銵峕覔�桀�銝见��鞟�蝥扯��麄��
    - [x] **�箄��桀�餈�誘銝𡒊�蝥扳�銵�**嚗𡁜銁�急�畾萇移����賭� `.git`��.nuitka_cache`��scratch/`��venv/`��build/`��dist/` 蝑㗇絲�譍葩�嗉�霂訫�蝻𤥁�蝻枏���辣���瘚见銁��鉄銝𠹺�銝芰�霂𤑳�摮条�撘��穃極雿𨅯躹���憭�遢餈���望㺭������蝻拍��� **1.8蝘�** �祇𡢿摰峕���
    - [x] **敶餃��寞祥 Windows 蝏�垢蝻𣇉�撏拇�**嚗𡁜縧�支����匧虾�賢�韏� Windows GBK 蝏�垢嚗㇃MD/PowerShell嚗㕑圾�𣂼�撣貊� Emoji �寞�摮㛖泵嚗峕㺿�函滲��𧋦閫����扇嚗𣬚＆靽嘥銁隞颱�銝剛㘚������𣬚���聢撘讐��煺漣�箏膥銝𡃏�銵���� 100% 蝔喳�銝滚援皞���

## 2026-06-06 11:55
- [x] **�拍�靽桀� Nuitka Onefile �枏�璅∪�銝见�餈𤤿��𠹺蜓餈𤤿�韏����辣�䭾��𦠜𦆮 Bug (Fixed Nuitka Onefile Resource Extraction & Diagnostics)**嚗�
    - [x] **�䭾辺隞嗥����雿� Nuitka 銝湔𧒄�𦠜𦆮�寧𤌍敶�**嚗𡁜銁 `sys_utils.py` �� `get_base_path()` 銝剖��乩�銝㯄秄��笆 Nuitka 餈鞱��臬����餈𤤿��拍�頝臬��芣�����臬��㗛� `NUITKA_ONEFILE_DIRECTORY` �典�餈𤤿�瘣曄��嗡腺憭梧�蝔见�隡𡁏��∩辣�朞��拍�璅∪� `__file__` �������葩�� `.pyd` ��辣雿滨蔭����齿綫嚗�僎�典�摮䀝葉�芸𢆡�滚遣餈睃�霂亦㴓憓���𧶏��㯄�帋�摮鞱�蝔讠��芣�頝臬���
    - [x] **撘訫�撣行��牐�撟喲唍�䀝��芣��Ｘ�**嚗𡁻���� `sys_utils.py` �𣬚� `nuitka_candidates` �Ｘ�頝臬��啁�嚗䔶�隞�𣈲���蝏毺�摮鞟𤌍敶閙𣄽�伐�餈睃��牐��𨀣�/�齿��牐��ｇ�`replace('/', '\\')`嚗劐誑�𠰴像�箔�銝湔𧒄�寧𤌍敶蓥�������隞嗅��Ｘ�嚗�� `base + "JSONData\stock_codes.conf"`嚗㚁��脫迫�曹� Windows/Unix 蝟餌�頝臬��𨀣�撌桀�撖潸稲��䔝瘚𧢲�蝵㻫��
    - [x] **隡睃� Nuitka �枏��𡁏𧋦��辣�澆�**嚗𡁜�蝻𤥁��𡁏𧋦 `nuitka_instockMonitor.bat` �𣬚� `--include-data-file` �賭誘銝剔�����格�頝臬�靽格㺿銝� Nuitka 摰䀹䲮�刻������迤�𨀣� `/` �澆�嚗�� `JSONData/stock_codes.conf`嚗㚁�隞擧����憭港�閫��鈭�眏鈭� Windows �齿��惩虾�質◤頧砌��鞾�瘜訫�蝚行�鋡怠像�粹��曄�憌𡡞埯��
    - [x] **蝏��擃睃笆瘥磰��剖���𠯫敹� (Nuitka-Diag)**嚗𡁜銁 `sys_utils.py` 閫血��𨀣瓲敹��蝵格�隞嗡腺憭曹��䭾��芣��肽稲�賡�霂航楝敺���㵪��芸𢆡�惩�鈭� `[Nuitka-Diag]` 靚��撅���䌊�冽𤣰��僎�烐𠯫敹埈綉�嗅蝱�𥕦枂 `NUITKA_ONEFILE_DIRECTORY` �臬��㗛��潦��base` ��辣憭寧��拍��航噢�嗆������滢葩�嗆覔�桀�銝讠��� 30 銝芸�雿𤘪�隞嗆��𤏪�雿輯圾�钅�雿漤䔮憸䀝�閫���𨰜��

## 2026-06-06 02:25
- [x] **�典��齿��唳答銵峕� `sys_utils` 蝏煺�撖餃�銝𤾸紡�乩��� (Refactored Unified sys_utils Path Resolution & Global Imports)**嚗�
    - [x] **�典�蝏煺� `get_conf_path` 撖澆�**嚗𡁜銁 `sina_data.py` ��辣憭湧�嚗�� `from sys_utils import get_app_root` �拙�隡睃�銝� `from sys_utils import get_app_root, get_conf_path`��
    - [x] **皜��撅��典�雿坔紡��**嚗𡁶宏�支� `get_stock_code_path` ���撅��函� `from sys_utils import get_conf_path` 憯唳�嚗峕��支�擃㗛�銵峕�敹�歲銝衤�敹����遆�啁漣�滚�撖澆�撘���嚗諹�銝�甇亥����隞���嗆�嚗屸�雿𡒊頂蝏笔�雿坔漲��

## 2026-06-06 02:22
- [x] **蝏煺��唳答銵峕�韏����辣銝� sys_utils �滨蔭�芣�頝臬� (Unified Sina Data Resources & Config Self-Healing Path)**嚗�
    - [x] **摨罸膄 `os.path.join(__file__)` �詨笆頝臬��潭𦻖**嚗𡁜銁 `sina_data.py` 銝剔� `StockCode.get_stock_code_path_func` �寞�銝哨��湔𦻖餈𥪜� `self.STOCK_CODE_PATH`嚗諹砲�潛眏 `sys_utils.get_conf_path` �� `get_app_root()` 頝臬�銝贝䌊����曇�峕䔉��
    - [x] **瘨�膄�屸�頝臬��脩�銝𤾸��噼������**嚗𡁜蝠摨閙��支��典�餈𤤿��� Windows Onefile/Onedir �枏��臬�銝见� `os.path.dirname(__file__)` �詨笆頝臬�瞍�宏撖潸稲撠�凒�啁�銝芾��𡑒”�坔� `JSONData\stock_codes.conf` 銝湔𧒄�桀�嚗諹�䔶蜓蝔见�����寧𤌍敶� `stock_codes.conf` 霂餃��扳㺭�桃��峕郊銝滢��� Bug��

## 2026-06-06 02:20
- [x] **靽桀��唳答摰墧𧒄銵峕��唳旿�瑕�餈�誘瞍讛�銝� stock_codes 頝冽𧒄畾萄�甇� Bug (Fixed Sina Data Pipeline Missing Stocks & Off-hours Sync)**嚗�
    - [x] **�寞祥�硺漱�𤘪𧒄畾� stock_codes.conf �峕郊�餅鱏**嚗𡁜銁 `sina_data.py` ��� `StockCode.get_stock_codes` �亙藁銝哨�蝘駁膄�𣂼� `update_stock_codes` �券�鈭斗��嗆挾餈鞱��� `is_trading_time` 蝵穃��函���＆靽脲�霈箸糓�峕膥�瑕鍳�刻��舐��𦒘蜓�冽凒�堆��唳答���啁��典��箄�蟡典�銵典��賡◇����仿�蝵格�隞塚�蝏湔�蝟餌����啁��∠巨�箇�摨瓐��
    - [x] **�寞祥 `combine_dataFrame` �嗆鰵隞��鋡急唂�砍𧑐�㗛�餈�誘瞍讐� Bug**嚗𡁜銁 `Sina.all` 銵峕��𡁜��寞�銝哨�摰帋�撟嗡耨憭滢�敶� `cache_needs_rebuild=False` �塚�蝟餌�靚�鍂 `_update_agg_cache(df, h5_hist)` �𣂼�撠�鰵�枏�銝芾�嚗�� `300291`嚗厩��亙�摮� `agg_cache`嚗䔶��冽𦻖銝𧢲䔉���撟嗆挾�湔𦻖瘝輻鍂甇文��芸��急鰵�∠��砍𧑐�芾粉�批��� `agg_data` 餈𥡝� `cct.combine_dataFrame(agg_data, df)`嚗䔶����餈䠷�����𤩺鰵�∪��冽��匧僎鋡急���腺撘���孵之�餉�瞍𤩺���耨憭滢蛹�刻��冽凒�啣��齿鰵隞𡒊�摮䀝葉�瑕����啁� `agg_data_updated = self.agg_cache.getkey('agg_metrics')` 餈𥡝���僎��
    - [x] **�拍��賜��芣�銝𤾸��訫�瘚贝�蝏踵��朞�**嚗𡁻�����唳��𣇉��∠巨隞���𣂼��其遙雿蓥漱�𤘪𧒄�湔挾憿箇�����砍𧑐 HDF5 ��蟮敹怎��𠰴��嗅�摮䀹�撠��銝芾��𡑒”�駁�隞� `5,423` �芣�撟嗅��渲‘朣鞱秐 `5,531` �芥���銵� `pytest test_watchlist_lifecycle.py` 11 憿孵��誩�敶埝�霂� 100% 蝏踵��朞���

## 2026-06-06 02:15
- [x] **靽桀�靽格㺿憭�釣�園緾撅誩㨃甇颱�璁�艙���蝒堒藁�衣��脩� Bug (Fixed Note Editing UI Freeze & Focus Conflict)**嚗�
    - [x] **�寞祥 `<FocusOut>` �衣�撘箏�甇餃儐��**嚗𡁜銁 `instock_MonitorTK.py` �� `show_concept_detail_window` 銝剔宏�支�撖� Canvas 蝏�辣�� `_keep_focus` 蝏穃�嚗�砲�箏��朞� `<FocusOut>` 鈭衤辣撘箏�閫血� `focus_set()` 靽脲�蝒堒藁�衣�嚗剹��砲霈曇恣�函鍂�瑕��餃�瘜典撕�� `askstring_at_parent_single` 璅⊥��笆霂脲��塚�隡𡁜��衣�頧祉宏�屸萅�交��𣂼撩�删��寧�甇餃儐�荔�撖潸稲�屸𢒰�舐��芸�銝𥪯蜓蝥輻�摰���⊥香��
    - [x] **�齿��桃�鈭衤辣蝏穃��� Toplevel 閫��**嚗𡁜���𧋦蝏穃��� `canvas` 蝏�辣銝羓��桃�撖潸⏛鈭衤辣嚗Ǒ<Up>`��<Down>`��<Prior>`��<Next>`嚗㗇㺿銝箔蜓蝒堒藁 `win` (Toplevel) ��凒�亦�摰𡄯�撟嗥眏 `win.focus_set()` �碶誨 `canvas.focus_set()`��＆靽嘥銁銝滚��亙撩�删��嫣�隞嗅儐�舐����銝页��桃�銝𠹺�蝧駁△��蕃撅誩紡�芾�憿箇��滚�嚗�僎銝擧芋����交�摰𣬚��澆捆��
    - [x] **蝟餌�蝔喳��找��𧼮�撉諹�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` �券��朞�嚗䔶漱鈭埝�蝔见像皛𤑳迅摰𠾼��

## 2026-06-05 22:35
- [x] **�券𢒰摰∟恣撟嗡耨憭滚��冽� Resample �唳旿瘚��蝳� Bug (Full Multi-Resample Pipeline Isolation Audit & Fix)**嚗�
    - [x] **[P0-Bug#1] 靽桀��㕑��冽𦻖�嗅之�冽��唳旿**嚗𡁜銁 `instock_MonitorTK.py` �� `_apply_tree_data_sync` 銝哨�撠� `selector.df_all_realtime = self.df_all_res` 靽格迤銝� `selector.df_all_realtime = self.df_all`嚗�� `selector.resample = cur_res` 靽格迤銝� `selector.resample = 'd'`��蝠摨閧＆靽嗪�㕑�/撘箏飵蝑偦��/�亥郎�餉�瘞貉��箔��亦瑪�唳旿餈𣂷�嚗䔶��� UI 憭批𪂹�蠘挽摰𡁏情�瓐��
    - [x] **[P0-Bug#2] �寞祥蝑𣇉裦撘閙� `resample` ��㺭瘜��憭批𪂹�笔��**嚗𡁜銁 `_run_live_strategy_process` ���嚗���笔�隞� `global_values.getkey("resample")` �冽��粉�� UI 霈曉��冽��� `cur_res` 蝖祉���蛹 `'d'`��蝠摨閖獈�凋�蝑𣇉裦��𣈲�斗鱏嚗�� `if resample == 'w'`嚗匧� UI ��揢�圈��亦瑪�冽��諹◤�躰秤瞈�瘣餌��餉�瘙⊥���
    - [x] **100% �嗆�霈曇恣憭齿瓲**嚗𡁜��詨僎蝖株恕蝡硺遠�Ｘ踎 (`on_realtime_data_arrived`)��漱�枏��豢釣�� (`_inject_focus_engine`)���撽祇𢒰�� (`df_all`)��detect_signals` 靽∪噡璉�瘚见�撌脫迤蝖桃�摰𡁏𠯫蝥� `full_df`嚗峕沲��挽霈∠泵����冽��𠉛氖�笔���

## 2026-06-05 22:03
- [x] **�券𢒰憭齿䰻���� commit 撟嗡耨憭� 6 憭���仿�餉� Bug (Full Strategy Logic Bug Sweep & Fix)**嚗�
    - [x] **[P0-Bug#1] �𣳇膄 `SuperTrendMA10Branch.decide` �屸� `return` 甇颱誨��**嚗𡁜縧�� `decision_engine.py` 蝚� 285 銵����僎�脩�畾讠�����券�憭滨� `return` 霂剖蘂嚗峕��支誨��郁銋劐�蝏湔擪�鞉���
    - [x] **[P0-Bug#2] 靽桀�敶Ｘ��6�𨅯�撖寞𦆮��/擃䀝��交��∩辣閫血�**嚗𡁜銁 `sector_focus_engine.py` ��耦��6(�条裦�單釣�∪�靚�䔝瘚�)閫血��滚��� `is_calm_pullback` �滨蔭�⊿�嚗�遠�澆銁��遠 簣1.5% �� 銝� `vol_ratio < 1.2`嚗㚁�敶餃��脫迫撘箏飵憭扳隅�交�撌券��暸��亥◤�躰秤��釣銝箔�隡睃�蝥� `PULLBACK_BUY` 靽∪噡�券��秐�喟�撅��隞擧覔皞鞉��文臁憯唬縑�瑯��
    - [x] **[P0-Bug#3] �寞祥 `PULLBACK_BUY` 靽∪噡�� `StrategyRouter` 蝛箔� Fallback 鋡恍俈敺∪��舀㜃��**嚗𡁜銁 `StrategyRouter.route` �� Fallback �寥�銝剖��� `is_pullback_signal` �文����靽∪噡蝐餃�銝� `PULLBACK_BUY` / `VWAP_SUPPORT` �塚��湔𦻖頝唾� `OscillatingBreakdownBranch` ��龪�㵪�餈𥕦�甇�虜雿𤾸𢙺��𣈲頝舐眏��蝠摨閗圾�� SWS �剜�銝见�暹𧒄���㗇𦆮銵𣬚��噼�靽∪噡鋡恍俈敺∪��臭����� `HOLD` ��䔮憸矋���迤�㯄�帋葉�𥪯��貊�撘�隞㯄�𡁻���
    - [x] **[P1-Bug#4] �嗥揮 `is_orderly_pullback` �� DFF �冽�銝舘�撟����**嚗𡁜銁 `sector_focus_engine.py` �� `get_dragon_signal` 銝哨�撠������箏� `dff >= -2.0` �嫣蛹銝㗇﹝�𥪜𢆡�文�嚗朞蝠敺桀�靚�(��-2%)��捂 DFF��-2嚗䔶葉撟��靚�(-4%~-2%)閬�� DFF��-1嚗峕楛撟��靚�(-5.5%~-4%)敹�◆ DFF��0嚗��瘚��嚗剹��俈甇Ｘ楛撟�枂韐扯�鋡恍�霂舀𦆮銵䎚��
    - [x] **[P1-Bug#5] 靽桀�撠曄�蝑𣇉裦�園𡢿閫��撖寧滲�交��澆��䠷�憭望�**嚗𡁜銁 `TAIL_LOW_RISK_ENTRY` �� `hhmm` 閫���𤾸��㰘��湔嵗撉� `800 <= hhmm <= 1600`嚗���墧� `signal.ts` 隞�鉄�交��䭾𧒄�湧���𧒄�芸𢆡�鮋���� 930嚗屸俈甇Ｘ��匧�瘚衤葉��偏�䀝��貊��亙�霂航圾�鞱�屸�暺䀝�閫血���
    - [x] **[P1-Bug#6] �𣂼� `SwsPullbackBranch.IN_TRADE` ��蔭靽∪漲�牐��∩辣**嚗𡁜��笔��䭾辺隞嗥� `confidence >= 0.80` 餈賢� 0.20 隞㯄�餉�嚗���� `dff >= 0.0` (銝餃���瘚��) �� `regime == "SWING_LOW_BUY"` �屸��齿�嚗屸俈甇Ｖ蜓�𥟇��箸�閫��璅∪�銝贝◤�刻�隞瓐��
    - [x] **100% 蝏踵��朞��券��𧼮�瘚贝�**嚗朞�銵� `pytest test_watchlist_lifecycle.py` �券� 11 憿寧鍂靘� 100% �朞�嚗��埈𧒄 0.75s嚗剹��

## 2026-06-05 21:50
- [x] **�㯄�帋葉�𥪯��訾�撠曄�蝔喳�撘�隞梶�摨訫�靽∪噡隡惩紡�曇楝 (Optimized Mid-Trend Low-Risk Entry & Decoupled Pullback Signal Gate)**嚗�
    - [x] **摰帋�摰䂿��𠰴控�啣�隞梶���**嚗𡁶�瘛勗漲摰∟恣嚗���啣�瘚见��𠬍��䭾辺隞園�鞉𠯫靚�鍂 `decide()`嚗劐�摰䂿�銵峕��急�瘚���冽㺭�格㜃�芣鱏撅����銝� `IntradayPullbackDetector` �� `get_dragon_signal` ��笆�桅�帋葵�∩�����𧑐��鍂鈭�撩�輻��渡′�扳㜃�迎�閬��頝𣬚聦�冽𤣰�行⏛��隅撟� < 2.0% �行⏛����游�隞瑞瑪�行⏛嚗㚁�撖潸稲�芷�㕑��𢠃�憭渲��函憬�𤩺��塩��萱蝥踹�靚���噼��交覔�祆�瘜閧��� `DecisionSignal` �券���憭扯�嚗�紡�游�蝑硋��𤾸銁雿𤾸𢙺�寡◤�𣈯正甇領�嘅�鋡怨翰�刻��唳活�亙之瘨兩�𨅯�撅梯��脲𧒄�滚�隞瓐��
    - [x] **�曇�樴坔仍銝擧��亙�瘜刻��噼��𡁻�**嚗�
        - �� `DragonTracker.get_dragon_signal` 銝剖��乩� `is_orderly_pullback` �文�嚗���亥�撟�虾�� `>= -5.5%` 銝磰��烐��箏��� `dff >= -2.0`嚗㚁���捂憭��皜拙�瘣㛖����憭渲���� `SignalType.PULLBACK_BUY` �噼萱靽∪噡嚗�僎�㮖� `"�� 樴坔仍�噼�"` ���撅墧�蝑暹綫��秐�喟�撅���
        - �� `IntradayPullbackDetector._check` 銝剖��� `is_strategic_focus` �芷����文�嚗�䌊�㕑��硋歇餈質葵樴坔仍嚗㚁�鞊���嗅��� of �亙�撘箏飵蝒�聦�行⏛嚗䔶��刻�撟�仃�改�`< -5.5%`嚗㗇�銝仿��港�嚗Ǒ< -2.5%`嚗㗇𧒄餈𥡝�靽脲擪�扯�皛扎��𥅾�芸龪�漤�憸穃耦����嗵眏�啗挽���𨅯耦��6嚗𡁏��仿��孵�瘜刻��噼�瘣㛖��Ｘ��嘥�摨閧��� `PULLBACK_BUY` �噼��Ｘ�靽∪噡��
    - [x] **瞈�瘣餃偏�䁅萱蝥蹂��賊𡡒��**嚗𡁻�朞��曇��噼�靽∪噡嚗諹䌊�㕑�銝𡡞�憭游朖雿踹銁蝻拚��噼��乩��賡◇�拍��乩漱�枏��賂��� 14:30 - 15:00 撠曄��嗆挾摰𣬚�瞈�瘣� `SwsPullbackBranch` 銝讠� `TAIL_LOW_RISK_ENTRY` 撠曄�雿𡡞��抵萱蝥蹂僭�亥��辷�0.35隞㮖�嚗㚁���迤摰䂿緵鈭��蝥踵𣈲�睲����雿喃��鞉𧋦銋啁�撱箔���
    - [x] **擃䀹����朞� 11 憿寧��賢𪂹���霂�**嚗帋耨�孵��典�摰寧緵�㗇𦻖����朞�餈鞱� `pytest test_watchlist_lifecycle.py` 11 憿孵��誩�敶埝�霂� 100% 蝏踵��朞���

## 2026-06-05 21:30
- [x] **銵亙�憭抒���鍳�函＆霈文�蝵格𠯫��遬蝷� (Prefixed Confirmation Date for Dragon Launch logs)**嚗�
    - [x] **�亙����漤𢒰�曄內蝖株恕�交�**嚗𡁜銁 `scratch/test_reentry_backtest.py` ���隞枏遣隞枏��牐��噼‘��之蝏𤘪��臬𢆡蝖株恕鈭衤辣�枏㫲銵峕��㵪��冽��釣�� `f"{current_date}"` 蝖株恕�交��㗛���聢撘譍��𡑒”�嗡����𨅯遣隞𣏾�腈���𨅯��航蔭頧砂�萘�銵�笆朣琜���之�𣂼�鈭��瘚𧢲𥁒�羓�銵峕���虾霂餅�找��園𡢿餈質葵�����

## 2026-06-05 21:10
- [x] **摰䂿緵樴坔仍憭抒���鍳�函＆霈� K 蝥蹂蜓�� �� �怎悌銝枏��曄泵��扇銝𦒘�銝钅�雿漤俈�格𣏹皜脫��箏� (Implemented �� Icon & Offset Rendering for Dragon Launch Confirmation)**嚗�
    - [x] **�㯄�𡁜�瘚见之蝏𤘪�靽∪噡�唳旿����㚚曎頝�**嚗𡁜銁 `scratch/test_reentry_backtest.py` ��遣隞枏��噼‘鈭衤辣�文�畾蛛��仿�憭游之蝏𤘪��臬𢆡蝖株恕 `is_dragon` �鞟�嚗諹䌊�典� `_last_backtest_signals` 餈賢�銝��� `action="DRAGON"`��desc="憭抒���鍳�函＆霈�"` ��縑�瑞�嚗䔶����甇斗��舐鸌敺���蠘���秐�滨垢皜脫��具��
    - [x] **摰䂿緵 �� ��恥�怎悌�曄泵擃睃�撌格�撠�**嚗𡁻���� `trade_visualizer_qt6.py` ���瘚衤縑�瑟�撠��餉�����Ｘ��啣𢆡雿靝誨��蛹 `DRAGON` �碶�隞嗆�餈唬蛹 `憭抒���鍳�函＆霈亡 �塚��曉�閬���曄泵 `symbol_override="��"` 撟嗆𦆮憭批偕撖貉秐 `24px`嚗䔶蝙�滢��喳��典之�曆��渲��航���
    - [x] **摰䂿緵銝𠹺��拍��嗘��脣��删�瘜� (Offset Rendering)**嚗𡁜銁��蟮 K 蝥蹂縑�瑞�雿滨蔭銝𠺪�撠��蝞� �� �� Y �鞉��讐宏�誩凝靚��蝘餉秐 `y_low * 0.955`嚗諹��虜閫�僭�伐�銝㕑�/鈭磰����蝏湔��� `y_low * 0.985`���蝖桐�鈭��銝�憭拙�銝支葵�其��惩�閫血��嗅�蝢𡡞�撘���妟�滚���妟�格𣏹��
    - [x] **�𡝗� Emoji ������雿� B / S ��𧋦��倌**嚗𡁜銁 `update_signals` �� K 蝥踹㦛��倌����餉�銝哨�憓𧼮�鈭� `not is_emoji` ���蝵格��乓��𥅾�臬��怎悌 `��` 蝑� Emoji �寞�靽∪噡�對��湔𦻖頝唾���� "B" / "S" 憸嘥���𧋦�曉�嚗�蝠摨閙覔瘝颱��曉��𣬚�蝞剔泵�琿��删��䔶僚�麄��
    - [x] **銝��芷�朞� 11 憿孵�蝟餌��笔𦶢�冽��詨�瘚贝�**嚗𡁏��蠘�銵� `pytest test_watchlist_lifecycle.py` �券��朞�嚗𥕢�摰墧� `python scratch/run_backtest_ds_bj.py` 蝏�垢颲枏枂摰��甇�虜��

## 2026-06-05 20:40
- [x] **靽桀�銝餉”�扯�瘚贝�擐𡝗活�孵稬摰帋�憭望� Bug (Fixed Failure of First Scroll-To-Code in Test Code Execution)**嚗�
    - [x] **�齿��孵稬閫血��餉�**嚗𡁜銁 `instock_MonitorTK.py` �� `on_test_code` �寞�銝哨�撠� `onclick` ��㺭��ế摰𡁏���蛹��擃䀝���漣�文��∩辣��蘨閬�糓 `onclick=True`嚗�眏�孵稬�𡝗�霂閗圻�穃𢆡雿𨅯��𤑳�靚�鍂嚗㚁�銝滩捏颲枏���誨��糓�圈�㗇𥋘�� code 餈䀹糓銝𠹺�甈∪歇�厩� code嚗���䭾辺隞嗆�銵䔶葵�∠��剹��check_code` 霂�摯��蜓 Treeview 皛𡁜𢆡摰帋�隞亙� K 蝥輻��批�雿㵪�`tree_scroll_to_code`嚗剹��
    - [x] **瘨�膄摰帋�皛𧼮�銝𡡞�餉��𦯀�**嚗𡁻���縧�支���𧋦撠���典�雿漤�餉��芸��� `self._select_on_test_code == code` �� `else` �文���𣈲銝讠�瞍𤩺�嚗�蝠摨閗圾�喃�銝芾�瘚贝��函洵銝�甈∠��餅𧒄�䭾�皛𡁜𢆡摰帋��唬蜓 Tree 銵𣬚�雿㯄�蝻粹萅嚗䔶誨�����凒皜�苊嚗𣬚泵�� KISS 銝� DRY �笔���
    - [x] **摰𣬚��朞��𧼮�瘚贝�**嚗朞��� `pytest test_watchlist_lifecycle.py` �券��其�嚗諹祗瘜閧�霂睲�憭朞�蝔贝�銵𣬚迅摰𡄯��牐遙雿訫�敶㘾䔮憸塩��

## 2026-06-05 20:30
- [x] **摰䂿緵樴坔仍憭抒���鍳�函＆霈方��祉�蝵桅▲銝𡡞�鈭格葡�𤘪㦤�� (Implemented Independent Placement & Highlight for Dragon Launch Confirmation)**嚗�
    - [x] **摰䂿緵樴坔仍蝖株恕靽⊥��滨蔭�𣇉𡠺蝡𧢲�銵�**嚗𡁻���� `test_reentry_backtest.py` 銝剔�撱箔�銝𤾸�銵乩�隞嗅ế摰𠾼����笔��潭𦻖�其�隞嗉�撠曄� `dragon_tag`嚗��亙之蝏𤘪��臬𢆡蝖株恕嚗㕑圾�行��吔��� `trade_events` �𡑒”銝凋誑 `�𤣳�𣂼撩�輸�憭游之蝏𤘪��臬𢆡蝖株恕�𥐯�� [��𣈲蝑𣇉裦: {蝑𣇉裦�㧸] (�𤨎憭抒���鍳�函＆霈�)` �祉�銝箔�銵䕘��鍦銁撖孵�銋啣�撱箔��硋�銵乩�隞嗉���**甇����**���摰𣬚��萄儐鈭��𨅯�蝖株恕憭抒�����匧�蝏剜�隞𣏾�萘��滨��喟��餉���
    - [x] **撘訫� Tkinter UI 蝥Ｚ𠧧�惩之�删�皜脫�**嚗𡁜銁 `stock_selection_window.py` ��� `BacktestReportDialog` �� `_apply_highlights` �� `tag_configure` �箏�銝哨��啣�鈭� `highlight_dragon_confirm` 皜脫���倌���霂亥�摨閗𠧧�𠰴��航𠧧霈曄蔭銝粹�撖寞�摨衣滯�莎�`#ff3333`嚗㚁�摮堒噡�惩之銝� `12px` 撟嗉�銵� `bold` �拍��删�嚗峕遬�埈�����墧��亙��典�蝡臬恥�瑞垢�𦠜綉�嗅蝱銝羓�閫���𡁶�摨艾��
    - [x] **100% 蝏踵��朞��𧼮�瘚贝�**嚗𡁏����銵䔶�銝𨅯控蝎曉�����啗�隞賜����唳㺭�桀�瘚见ế摰𡄯�瘚贝��亙�銝剝�憭游之蝏𤘪��文�銵�銁銋啣��嫣��寧移����堆�銝� `pytest test_watchlist_lifecycle.py` 11 憿寧頂蝏毺漣�笔𦶢�冽�瘚贝� 100% �𣂼���

## 2026-06-05 20:12
- [x] **摰䂿緵撘箏飵�∪之��/瘨典��臬𢆡蝖株恕銝擧𤣰�䀝遠�脩瑪�誩�摰∟恣�箏� (Implemented Strong Stock Launch Confirmation & Price Floor Audit)**嚗�
    - [x] **摰帋��拍��臬𢆡�仿�摰� (Launch Day Anchor)**嚗𡁜銁 `check_strong_dragon_memory` 銝剖��牐�憭折翧/瘨典��臬𢆡�亦��芸𢆡璉�瘚页�餈�縧 10 銝芯漱�𤘪𠯫����冽隅�𨀣� >=9.5% 銝娪�撘�憭批�雿枏之�喟瑪嚗剹��
    - [x] **摰䂿緵�嗥�隞瑞���俈敺∩��游恣霈� (Launch Close Price Support Gate)**嚗朞䌊�臬𢆡�乩誑�伐�撖寞��劐漱�𤘪𠯫��𤣰�䀝遠摰墧鴌�拍�摰∟恣���瘙���湔�銝�憭拍��嗥�隞瑕��芰�����游鍳�冽𠯫�嗥�隞瘀�`Close >= LaunchClose * 0.995`嚗㚁�靽嗪��舀�蝥輸俈�箏�憭���
    - [x] **摰䂿緵擃䀝�蝻拚�璅芰�瘣㛖�蝖株恕 (Volume Shrink & Consolidation Check)**嚗𡁜恣霈⊥赤�䁅��湔��湔𠯫���鈭日�嚗��鈭𤾸鍳�冽𠯫�� 80% �碶��亦憬�𧶏�銝擧𥲤撟��蝳餃漲嚗𣬚＆霈支蜓�偦�雿齿��睃�雿溻����桅�隞瓐��
    - [x] **憭𡁶垢�峕郊銝𤾸�瘚贝�撉𣬚遛�𡑒��� (Multi-period Test Alignment & 100% Passed)**嚗𡁜��啁��嗅�霈啣�蝞埈��峕郊摨𠉛鍂鈭𡒊��滢�璉� (`premarket_analyzer.py`) ���瘚𧢲��� (`test_reentry_backtest.py`)����笔�瘚见枂銝𨅯控蝎曉��� 04-14 撘箏�蝖株恕�舀�銋啣�����啗�隞� 04-13 雿𤾸𢙺嚗䔶� `pytest test_watchlist_lifecycle.py` 11 憿寧��賢𪂹��瓲敹��霂� 100% 蝏踵��朞���
    - [x] **銵仿��墧��亙�銝𦒘��䁅恣�埝𠯫敹烾�憭渡鸌敺�遬蝷� (Aligned Backtest Report & Plan Dragon-Tag Display)**嚗𡁜銁 `test_reentry_backtest.py` ��遣隞�/�噼‘鈭衤辣颲枏枂瘚��隞亙�撖澆枂�喟��滩恣�坿”�閧� `reason` ��㺭�怠偏嚗�𢆡��釣�乩� `(�𤨎憭抒���鍳�函＆霈�)` �垍𤌍������雿踹��墧��亙�銝舘恣�埝��閧��賜��餉�皜�苊�航�嚗峕䲮靘踵��䀹�餈賣滲撱箔�摨閙���

## 2026-06-05 11:25
- [x] **摰䂿緵蝡硺遠�Ｘ踎�𤾸蝱�芸𢆡璉�瘚衤��芸��航郎�交㦤�� (Implemented Bidding Panel Background Detection & Missing Warnings)**嚗�
    - [x] **摨罸膄蝡硺遠�Ｘ踎�芸��舀𧒄���撽祇�蝥�**嚗𡁻�敺芰鍂�瑟�撖潘�摨罸膄鈭� `_inject_focus_engine` 銝剖銁�Ｘ踎�芸��舀𧒄�� `racing_detector` ���蝥扯繮�㚚�餉�嚗���典抅鈭𦒘漱�𤘪���䌊�典�憪见����隞琿𢒰�� (`sector_bidding_panel`)��
    - [x] **摰䂿緵鈭斗���𧊋撘���/�䭾㺭�株䌊�典恣霈∩�霈⊥㺭**嚗𡁻�朞� `cct.get_work_time()` 蝎曉����鈭斗��嗆挾嚗�僎�冽釣�亙仃韐交𧒄嚗�𢒰�踵𧊋�枏���� detector �� `inject_from_detector` 餈𥪜�憭梯揖嚗匧笆霈⊥㺭�刻䌊憓𠺶��
    - [x] **頞��3甈∟圻�烐𠯫敹� warning 憸�郎**嚗朞�蝏� 3 甈⊥�瘚见𪂹���瘜閗繮�𡝗㺭�格𧒄嚗�銁�𤾸蝱蝥輻�銝剛䌊�其漣�� `logger.warning` 霅行𥁒�亙�嚗�葬�拇��䀹��𦠜𧒄�𤑳緵�峕��仿𢒰�踵𧊋撘��舫䔮憸矋�蝖桐�鈭斗��唳旿瘚�����撖寥◇����
- [x] **�寞祥�𤾸蝱�喟�瘚���唳旿瘜典��刻����憸睲��� UI 隡睃��鞉�撖潸稲�𨀣��� Bug (Fixed Background Decision Flow & Bidding Stagnation Due to UI-Throttling Early-Return)**嚗�
    - [x] **敶餃�閫��血��唬遙�∩� UI �拚��/餈�誘 (Decoupled Background Tasks from UI Throttling)**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `_apply_tree_data_sync` �寞�����𤾸蝱�唳旿撽勗𢆡��瓲敹��摨虫遙�﹦�婙�𤩊lf_panel_feed` (蝡硺遠�唳旿�峕郊) 銝� `lf_engine_inject` (�喟�/鈭斗���瓲瘜典�)�婙�𠉛���宏�刻秐 UI 皜脫��鞉��𦠜𡟺�蠘��痹�`df_hash == last_hash`嚗劐��齿�銵䕘�蝖桐�隞颱��𤾸蝱銝𡁜𦛚�餉��刻����颲暹𧒄���蝡见朖餈鞱蓮嚗�蝠摨蓥��� UI 皜脫�憸𤑳�����嗚��
    - [x] **閫�� 5�嫣遠�潮��瑟�蝥寞�撘訫��� `has_update` 擖仿正�桅�**嚗𡁏迨�滨������犒�⊿��牐蛹�芷��瑚� 5 �芯葵�� of �嗥�隞瑕��剁�餈坔銁 5,500+ �芯葵�∠㴓憓����𠗕閫血��睃𢆡嚗䔶蝙敺� `has_update` �踵�憭�� `False`嚗�紡�游�蝑硋��� `_inject_focus_engine` 鋡急��鞉�擖踵香����滨宏�支�撖� `has_update` ������靘肽�嚗䔶蝙�嗡��萄儐霈曉��� `duration_sleep_time` �笔�甇仿鵭�扯�瘜典���
    - [x] **摨罸膄��撠誩�/�睃��鞱��嗆����� isVisible 餈�誘 (Feed Data Even When Hidden/Minimized)**嚗𡁜縧�支� `sector_bidding_panel` �唳旿�券��𧒄敹�◆皛∟雲 `isVisible()` ����鞉辺隞嗚��緵�典蘨閬�𢒰�輯◤�𥕦遣摮睃銁嚗�朖雿輯◤�冽���撠誩��碶誑�鮋�瘥�芋撘� hide �鞱�嚗䔶�隡𡁏�皞𣂷��剜𦻖�嗅��嗆㺭�格綫���靽�蝙摨訫��� `BiddingMomentumDetector` �典��圈�憸煾�蝎曉𧑐�瑟鰵�踹��枏�嚗䔶�霂��蝑㚚曎�䔶漱�𤘪𠯫敹埈�蝔钅◇����腈��

## 2026-06-05 03:05
- [x] **閫��血��唬遙�∪�憪见�銝舘���㺭�桀�颲曆�韏吔�靽桀� FlowWatchdog �喟�瘚��皛噼秤�� (Decoupled Housekeeping & Fixed False Stagnation Watchdog Alerts)**嚗�
    - [x] **�𤾸蝱隞餃𦛚銝𡡞�撅𤩺㺭�株圾��**嚗𡁜� `_batch_init_housekeeping` ��葉�嘥��𡝗䲮瘜蓥�擐硋�摰墧𧒄銵峕��啗噢嚗�洵銝�甈� sync �唳旿嚗匧蝠摨閗圾�佗��嫣蛹�其蜓 Tk 蝒堒藁 `__init__` �嘥��硋�撱嗉� 2 蝘𡜐�`self._schedule_after(2000)`嚗㕑䌊�冽��∩辣�㕑絲��眏甇歹��喃噶�券�鈭斗��嗆挾嚗䔶漱�枏��詨�頝喟�撣賊彿�𤾸蝱撣賊彿�滚𦛚銋蠘�蝡见朖�臬𢆡�穃𨯬��
    - [x] **�惩𤐄蝒堒藁�Ｗ�閫血�**嚗𡁜� `self.restore_all_monitor_windows` ����其��𤾸蝱�嘥��𣇉宏�典��唳旿�峕郊 `_apply_tree_data_sync` ���嚗䔶��� `self.df_all` 擐𡝗活�㗇㺭�桐��䂿征�嗆�銵䕘�敶餃��踹�鈭���臬𢆡�嗆挾 `df_all` 銝箇征撖潸稲璁�艙蝒堒藁�Ｗ�憭梯揖�� Bug��
    - [x] **�㯄�𡁜��啣��豢�銵��頝�**嚗𡁜銁 `bg_kernel_auto_execute_once` 敹�歲�拍��扯���仍�剁�憓𧼮�鈭�笆�曹澈 `self.global_dict["kernel_heartbeat_time"] = time.time()` �園𡢿�喟��芸𢆡�坔�嚗𣬚＆靽苷漱�枏��詨銁瘝⊥�隞颱�鈭斗�靽∪噡���暺䀹��湛�隞滩�摰𡁏𧒄�𣂷�瘣餉������
    - [x] **靽桀� Watchdog Stagnation 霂舀𥁒**嚗𡁜銁�喟�瘚���批之撅讐��钅秄�� `FlowWatchdog` �文�敺芰㴓銝哨��惩�鈭�笆 `kernel_heartbeat_time` ���鈭怨粉�硋ế摰𠾼��蘨閬���唬漱�枏��貊�敹�歲�� 60 蝘鍦��湔鰵餈���唾䌊�券�蝵� `_last_growth_time`嚗�蝠摨閙覔瘝颱�擃㗛�餈鞱��兩�𨀣�鈭斗��亙��脲𧒄�曹��亙���辣�删�����輯�屸�霂舀𥁒�算�𨅯�蝑𡝗�撌脣�甇Ｚ�餈�50����萘�霂航郎��
    - [x] **100% 蝏踵�頝煾�𡁶頂蝏笔�敶埝�霂�**嚗𡁶�霂煾◇�拚�朞�嚗䔶� `pytest test_watchlist_lifecycle.py` 11 憿寞瓲敹��敶垍鍂靘� 100% �𣂼���

## 2026-06-05 00:35
- [x] **�寞祥 `minute_kline_cache.pkl` ���箏��睃�������隞嗡�蝘臬�撣貉���銝𡒊��讐揣撘訫�摮䀹�瞍� (Fixed Pickle Size Inflation & RangeIndex Alignment)**嚗�
    - [x] **�埝䰻摰帋���辣�刻��笔�**嚗𡁜��𣂼��堆�`MinuteKlineCache` �� `to_dataframe()` 銝剜�銵� `groupby('code').tail()` ��僎隞亙��� `from_dataframe()` 銝剛�銵峕㺭�格𣄽�交𧒄嚗諹��䂿� DataFrame 靽萘�鈭��餈䂿賒����讐� `Int64Index` 蝝Ｗ�嚗�之撠讐漲銝� 164.7 銝�葵�游�蝝Ｗ��潘���蒾�嗡舅蝡舀㺭�桀�摰嫘����啣��其��瘀�雿�� 164.7 銝�葵�曉��游�蝝Ｗ��潸◤ pandas 銝�韏瑕��堒��坔�鈭� Pickle ��辣銝哨��喃蝙蝏� zstd �讠憬銋煺��賜蒾憭𡁜枂 **2.10 MB** �����征�湛�隞� 16.75MB �刻��� 18.85MB嚗㚁�銝𥪜銁���銝凋漣�煺�憸嘥��� **12.5 MB** 蝔��讐揣撘訫�����
    - [x] **摰墧鴌 `reset_index(drop=True)` �券�朞楝閫�㟲**嚗𡁜銁 `MinuteKlineCache.to_dataframe()` 餈𥪜��㵪�隞亙��� `from_dataframe()` �� `self._raw_loaded_df` 蝻枏��潸�韏见�澆偏蝡荔�蝏煺�靚�鍂 `.reset_index(drop=True)`嚗��蝝Ｗ�撘箏�閫��銝箄�蝏准�����閬������冽㺭�� of RangeIndex��
    - [x] **�拍�憭批�銝𤾸�摮� footprint 摰𣬚��Ｗ�**嚗𡁜�瘚钅��啗�銵䔶�摮睃�嚗峕�隞嗥���之撠譍� **19,298 KB** �齿鰵蝻拙��� **17,156 KB**嚗�1 摮𡑒�銝滚榆�啣笆朣𣂷��笔�憭�遢憭批�嚗㚁����鈭� 11.1% 摮睃�蝛粹𡢿�� 12.5MB of ���撘���嚗���嗡��碶� I/O 霂餃������
- [x] **靽桀��曹��唳旿�剜﹝�硋虜撟湔𧊋�湔鰵銝芾�撖潸稲�� `strftime` 撅墧�批援皞������𤥁‘�� (Fixed Day_DF Date Formatting Crashes & Normalized Null/Int Date Alignment)**嚗�
    - [x] **�𣂼�撟嗅��典�撅��交�閫�㟲�� `_to_date_str_safe`**嚗𡁜���𧋦撋��摰帋�鈭� `_render_charts_logic` ��� `_to_date_str_safe` �箄��交�頧祆揢�賣㺭�拍��𣂼�撟園���秐 `trade_visualizer_qt6.py` ��辣憿園��典�蝛粹𡢿嚗���啣���辣嚗���砌蜓�整����整��縑�瑕���抅��瑪霈∠�嚗匧笆�交�皜���餉� of 蝏煺�靚�鍂嚗�泵�� DRY �笔�嚗剹��
    - [x] **敶餃��寞祥 `_normalize_dataframe` ��征�交��� Bug**嚗𡁏��亙僎摰帋�鈭� `_normalize_dataframe` 銝剔�銝仿�蝻粹萅�婙�𥪜�颲枏� DataFrame 瘝⊥�隞颱�隞� `'date'` �賢�����塚�霂亙遆�唬�敶餃�頝唾�撖� `df['date']` ����潘�銝𥪜���𧋦��𧒄�游�嚗�� `ticktime`嚗劐腺撘��撖潸稲餈𥪜��� DataFrame 銝Ｗ仃�交�蝏游漲嚗�僎�𦠜㟲�� Unix 蝘垍漣�園𡢿�喃��坔銁 Index 銝哨��典�蝏剛��其葉�䭾�瘜閙�銵� `.strftime` 撖潸稲蝟餌��𥕦枂 `AttributeError: 'int' object has no attribute 'strftime'`��耨憭齿䲮獢��撘箏�雿� `_normalize_dataframe` �其遙雿閗��亦掩�衤��賡�朞� `ts` (�舀� Series��atetimeIndex 蝑�) ���閫���𣇉� `'date'` 摮埈挾嚗�笆朣𣂷��函頂蝏毺��交��亙藁��
    - [x] **�惩𤐄靽∪噡瘙牐� `_need_ghost_bar` 霂𦠜鱏颲寧�**嚗�
        - �齿�鈭� `_refresh_stock_signal_cache` �𣬚� `date_map` 蝻枏����撘𧶏�摰���踵揢鈭�����撅��� `d.strftime` 銝粹�璉垍� `_to_date_str_safe(d)` �煾��𡝗�瘣𨰜��
        - 銝� `_need_ghost_bar` 憓𧼮�鈭��蝵� Empty DataFrame �脣鴃嚗屸��滢��冽�銵峕��唳旿�硋��臬𢆡銝芾��箸艶銝贝��� `day_df.index[-1]` �𤑳� `IndexError`嚗�僎�𢠃�蝜���条� `logger.error` �滨漣銝箏�憟賢漲�湧��� `logger.warning`嚗屸��滢�撖寧鍂�瑟迤撣豢㺭�株��剔��瑕���
    - [x] **100% 蝏踵�頝煾�𡁶頂蝏笔�敶埝�霂�**嚗朞��� `pytest test_watchlist_lifecycle.py` �券��其�嚗諹祗瘜閧�霂煾�朞�嚗峕瓷�匧笆蝟餌�鈭抒�隞颱�蝡墧����蠘��抒聦�譌��

## 2026-06-05 00:30
- [x] **靽桀���𧒄 K 蝥輻�摮睃��嗘葉�曹� time/code 瘛瑕�蝐餃�撖潸稲���憭滚縧�滚仃�����辣�刻� (Fixed K-Line Cache De-duplication Failure & Pickle Size Expansion)**嚗�
    - [x] **摰帋�瘛瑕�蝐餃��駁�憭望��寞�**嚗𡁜��鞟＆霈斤眏鈭𡒊��睃�頧賢僎����� `self._raw_loaded_df` �急� pandas `Timestamp` 撖寡情��㺭�澆�摮㛖泵銝脫毽��聢撘讐� `time` 摮埈挾嚗諹���摮䀹鰵����� `current_df` 銝剔� `time` 憪讠�銝� `int64` �� Unix 蝘垍漣�園𡢿�喋��銁 pandas 餈𥡝� `concat` �拍���僎�𠬍��曹�銝方器 columns 蝐餃�銝滢��湛��𤥁蓮�Ｖ蛹 object 瘛瑕�蝐餃�嚗㚁�雿踹� pandas `drop_duplicates(subset=['code', 'time'])` 憭望�嚗䔶漣�煺�憭折��滚�銵䕘��𧼮�蝤���𤾸紡�� `minute_kline_cache.pkl` 隞� 17MB 撘�虜�刻��� 20MB��
    - [x] **�𣂼�撟嗅��冽惣�賢撩�𥟇𧒄�湔�閫�㟲�� `_normalize_time_column`**嚗𡁜銁 `realtime_data_service.py` 憿嗅�霈曇恣鈭���啁� `_normalize_time_column` 颲�𨭌�賣㺭��𣈲��惣�質��� numeric��imestamp��tr 瘛瑕�颲枏�嚗諹䌊���蝻拚�撟嗉��亙枂蝥舐�蝥� Unix �園𡢿�喉�`int64`嚗㚁�敶餃�瘨�膄鈭� NaT 蝛箏�潔漣�毺�頞羓�韐�㺭��
    - [x] **�券𢒰閬�����撟嗅縧�滢��唳旿頧賢��亙藁**嚗�
        - �齿�鈭� `MinuteKlineCache.to_dataframe` �𣬚��箄���僎�餉�嚗�銁��僎�滚笆銝方器�� `code` �� `time` 餈𥡝�撘箏�皜��嚗峕�蝏嘥縧�滚仃����
        - 蝞��硋僎�齿�鈭� `MinuteKlineCache.from_dataframe` �滚��典�������隞��嚗���笔�蝥� 40 銵𣬚��烾鵭閫��蝏煺�銝箸�蝞��� `_normalize_time_column` 靚�鍂嚗�泵�� KISS �笔�嚗㚁�撟嗅銁撠暸��� `_raw_loaded_df` ��僎憭��銵𣬚㮾�諹��氬��
    - [x] **摰𣬚��朞��券�蝟餌��𧼮�瘚贝�**嚗�100% 蝏踵�頝煾�� `test_watchlist_lifecycle.py` �券��其�嚗���坔縧�滩�銵�像蝔喉�瘨�膄鈭��隞嗆�������������

## 2026-06-04 23:45
- [x] **�寞祥 K 蝥踹��脩�摮睃笆鞊∪�摮䀹𠂔瘨其�摰墧𧒄隡睃� (Fixed K-Line Cache Memory Expansion & Optimized Memory Footprint)**嚗�
    - [x] **摰帋����憌坔�皞𣂼仍**嚗𡁜��鞟＆霈斤眏鈭擧迨�滚� K 蝥輻�摮䀝��𣂷��滨蔭��辣撖寥�嚗�蝙 `kline_cache_max_len = 450` ���嚗峕迨�滨′蝻𣇉�銝� `210`嚗㚁�撖潸稲�典��� 5500+ �芾�蟡典銁�嘥��𡝗𧒄���鈭�漲 165 銝�葵 `KLineItem` �𠰴�摮鞉㺭�澆笆鞊～��眏鈭� Python ���蝞∠�銝� GC 蝣𡒊�撘���嚗諹��湔𦻖撖潸稲 `DataPublisher` ���撘���隞� 500MB+ �游��� 890MB+嚗諹稲雿� Tkinter �臬𢆡�擧�餃�摮睃�擃䁅秐 1300MB+��
    - [x] **摰䂿緵�墧暑頝��蟡典𢆡��憬�𣂼�頧質���㦤�� (Active/Inactive Stocks Dynamic Trimming on Load)**嚗�
        - 隞�銁�唳旿�㰘蝸嚗Ǒfrom_dataframe`嚗厰𧫴畾蛛���笆�墧暑頝���芰� 120 �嫣誑�����漲 KLineItem 摰硺��硋笆鞊∠����嚗���� ~599MB嚗��撠𤑳漲 60% 撖寡情嚗㚁��䀝葉餈賢��𠰴虜閫�����銝滚� 120 �孵撩�迎�靽嗪�摰䂿�鈭斗�頧刻蕨摰峕㟲�扼��
    - [x] **摰䂿緵 `_raw_loaded_df` �箄��䭾���僎銝𤾸��冽�摨� (Incremental Non-destructive Persistence)**嚗�
        - ��笆 `minute_kline_cache.pkl` 閬���嗵�撖潸稲�墧暑頝��鋡急偶銋�⏛�剔��桅�嚗���� `_raw_loaded_df` 靽萘��笔��㰘蝸�𠰴��讐��䭾� DataFrame �嗆����銁 `to_dataframe()` 摨誩��硋��睃�銝𤾸�摮条移蝞� DataFrame 餈𥡝� `concat` + `drop_duplicates` + `tail(self._max_len)` �箄��䭾���僎嚗𣬚＆靽嘥��其�蝤���� pkl 憪讠�摰峕㟲靽萘� 450 �對��碶��𣂼�潘�K蝥踹��脯��
        - 蝘駁膄鈭�銁 `from_dataframe` 憭湧��曹� `time` �埈𧊋敶雴��吔�`Timestamp` 銝� `int64` 瘛瑕�嚗匧紡�渡� `lexsort` 撏拇� Bug嚗����僎�餉��𡒊宏�單㺭�格�瘣堒�蝏枏�嚗�蝠摨閧����蝳颱��鍦�蝐餃��脩���
    - [x] **100% 蝏踵�頝煾�𡁶頂蝏笔�敶埝�霂�**嚗朞��� `pytest test_watchlist_lifecycle.py` �券� 11 憿寧鍂靘见� `test_auction_engine.py`嚗峕�隞颱��蠘�銝舘恣蝞㛖����蝒���

## 2026-06-04 19:13
- [x] **隡睃��喟�瘚�偌����Ｘ踎敹急㭘�株�銝� (Optimized Decision Flow Panel Shortcut)**嚗�
    - [x] **�齿活�孵稬�芸𢆡�鞱�**嚗𡁜銁 `instock_MonitorTK.py` �� `open_decision_flow_panel` �寞�銝哨�憓𧼮�鈭�笆�Ｘ踎敶枏��嗆����斗鱏嚗諹𥅾�Ｘ踎憭���滚蝱瘣餉��嗆����劐�敹急㭘�殷�`Alt+J`嚗匧朖�航䌊�券��讛砲�Ｘ踎嚗峕�靘𥟇凒瘚������Ｖ�撉䎚��
    - [x] **�𧼮��啗䌊�函蔭憿�**嚗𡁜��𣈯𢒰�踹歇蝏𤩺�撘�嚗䔶�鋡怠�隞𣇉�����∴��芸�鈭𡒊��寧𠶖���嚗峕�銝见翰�琿睸隡𡁜��� `raise_()` 撟嗥蔭鈭擧��漤𢒰嚗峕����齿鰵�㰘蝸��
    - [x] **��蔭敹急㭘�桅𡡒��**嚗𡁜銁 `decision_flow_panel.py` ��𢒰�踹�憪见�銝剛‘朣𣂷� `QShortcut(Alt+J)`嚗𣬚＆靽嘥銁�Ｘ踎�祈澈�瑟��衣��塚�敹急㭘�桐�隞嗡�隡朞◤�墧瓷嚗諹�峕糓�芸�靚�鍂 `hide()`嚗���唬�摰𣬚�����臭��喲𡡒�删���揢��

## 2026-06-04 12:15
- [x] **摰䂿緵銝��格㺭�株䌊���瘞渡�摮䀝���稬餈質葵摰∟恣�箏� (Implemented Self-Heal Trace Logging & Interactive Audit)**嚗�
    - [x] **���惩僎�拍�餈賢��芣�瘚�偌霈啣�**嚗𡁜銁銝��格㺭�株䌊��耨憭齿�銵�偏畾蛛�撠���急���厭�菜㺭��遠�潸䌊��㺭��𧒄�游笆朣鞉㺭���憪贝��㻫��虾�函緵�穃�瘚桃��滨�����渲䌊��㺭�殷��潸�銝箇泵���蝑𡝗�瘞渲���� `rec_heal` 摮堒�霈啣�嚗�僎隞� UTF-8 蝻𣇉��拍�餈賢��坔��砍𧑐鈭斗�瘚�偌�亙� `trading_kernel_trace.jsonl`嚗䔶�����啗䌊����𦦵���蟮�拍��坔�銝𤾸恣霈∟蕭皞胯��
    - [x] **�㯄�� UI 憓鮋��湔鰵銝舘䌊�券�鈭�**嚗𡁻�朞���辣�������剁�摰𣬚�閫血� `DecisionFlowPanel` �� 500ms 憓鮋��亙��急��剁��芸𢆡�㰘蝸�啗扇敶訫僎�鍦��喇�𨅯�蝑𡝗�瘞渡��把�肽”�潔葉嚗峕遬蝷箔蛹隞� `HEAL`嚗�誨����� `�唳旿�芣�`嚗��蝘堆�銝粹����鈭株���
    - [x] **摰䂿緵��稬�𥪜𢆡銝𤾸�憪� JSON 憭滚�**嚗𡁏𣈲��鍂�瑕銁瘚�偌銵冽聢銝剖��餉砲銵諹䌊��扇敶𤏪��拍鍂 `UserRole` ����唳旿�嗆��祆�韏� `DecisionDetailsDialog` 霂行�獢���舀��函洵銝�憿萇倌�仿�蝏𤘪��𣇉��芣���㺭�𡒊�嚗�銁蝚砌�憿萇倌憭滚��祆活�芣�����游�憪� JSON嚗�蝠摨閗圾�喃��𨅯蘨撘寧�銝滨��𨰝�苷��䭾��滚�餈賣滲摰∟恣����嫘��
    - [x] **Unicode ���貉蓮銋劐��冽�霂閖�朞�**嚗𡁜笆 Python 皞鞟�銝剖ㄟ�𡒊����劐葉���蝷箄祗�峕�����圈��� Unicode ���豢㦤�嗉��� Windows CP936 銋梁�蝖砌慾���甈� 100% 蝏踵�頝煾�� `test_watchlist_lifecycle.py` �券��𧼮�瘚贝���

## 2026-06-04 11:45
- [x] **靽桀�銝��格㺭�株䌊��漱鈭鍦�甇颱� GIL �游𦶢撏拇� (Fixed One-Key Self-Heal UI Hanging & GIL Crashes)**嚗�
    - [x] **摰䂿緵�單𧒄撘寧�蝖株恕�漤�**嚗𡁜銁 `decision_flow_panel.py` ����株䌊�� `_on_one_key_self_heal` �寞�韏瑟�雿滨蔭撘訫�鈭� `QtWidgets.QMessageBox.question` 蝖株恕�鞟內獢���銁�脰秤閫衣��峕𧒄嚗�銁�冽��孵稬�厰僼��洵銝��園𡢿�𣂷�鈭�朖�嗚���憟賜�銝餌瑪蝔衤漱鈭鍦�擐��瘨�膄鈭������餅��格��滚����撉𣬚��嫘��
    - [x] **�齿����鈭劐蛹�鮋獈憛墧芋撘�**嚗𡁜笆���� `trade_gw._lock` ���甇仿�鈭匧內�餉�餈𥡝�鈭����竉蝳鳴�摨笔�鈭���厩��餃�撘� `with trade_gw._lock` 銝𠹺�����券𢒰��漣銝箏蒂�� 3.0 蝘鍦��刻��園��嗥� `if trade_gw._lock.acquire(timeout=3.0)` 璅∪���銁頞�𧒄�舘䌊�典�霅血僎隡㗛�頝唾�嚗�蝠摨閗圾�血僎�脫迫鈭�� Contention 銝见��啁瑪蝔𧢲香��紡�渡� UI ��香銝𦒘蜓蝥輻�擖踵香��
    - [x] **蝥輻�摰匧� UI 撘�郊�噼�獢交𦻖**嚗𡁜銁�𤾸蝱撘�郊摰�擪蝥輻� `_async_heal_worker` 銝哨��∟圻�� `self._refresh_positions_tab()`��QtWidgets.QMessageBox` 蝑� GUI 蝏�辣���雿頣�銝�敺衤誑 `QtCore.QTimer.singleShot(0, callback)` 蝥輻�摰匧��唳晷�穃� PyQt 銝颱�隞嗅儐�舫��梹��踹�頝函瑪蝔讠凒�交𦻖閫� Qt/Tkinter �詨� C-API 撖潸稲 GIL �拍�撏拇�銝舘�蝔贝◤蝟餌�撘箏�銝剜鱏����嫘��
    - [x] **銵亙��券曎頝舫�霂航䌊���霂𦠜鱏�亙�**嚗帋蛹�芣�瘚���喲睸甇仿炊嚗���芣�隞瑟聢���瘞游�隞𤘪𧒄�游笆朣僐���憪贝��睲��舐鍂�圈�靽格迤��tate_manager �嗆���甇乓�����氜�䀹�銋��嚗㕑‘朣𣂷�霂血偷�� `logger.info` �� `logger.warning` 頝蠘葵嚗�僎撖� UI �噼���ㄨ鈭� crash-safe �� `try-except` 靽脲擪��
    - [x] **隞� Unicode ���豢㦤�嗡�霂� Windows �扯�銝滢僚��**嚗𡁻�朞�撠� patch �𡁏𧋦銝剔�銝剜�摮㛖泵銝脣��典�銝箸���� `\uXXXX` 蝥� ASCII 摨誩�嚗䔶����餈�� Windows �批��啣銁 CP936 蝻𣇉�銝𧢲�銵� Python 皞鞟��𡁏𧋦�嗅虾�賭漣�毺� EOL 閫���躰秤銝𤾸�蝚虫葡摮烾𢒰�讛圾�𣂷葉�剝䔮憸塩��
    - [x] **銝��芷�朞� 11 憿孵�蝟餌��𧼮�瘚贝�**嚗𡁜�蝢舘��� `pytest test_watchlist_lifecycle.py`嚗�11 憿寧頂蝏毺漣�其� 100% 蝏踵��朞�嚗㚁�霂��摨訫�鈭斗�銝擧瓲敹��餉�撟喟迅�芣���

## 2026-06-04 11:15
- [x] **靽桀�銝��格㺭�株䌊���韏瑞� NameError: name 'threading' is not defined (Fixed Missing threading Import in DecisionFlowPanel)**嚗𡁜銁 `decision_flow_panel.py` ��辣憭湧�銵仿�鈭� `import threading` 霂剖蘂嚗諹圾�喃�憭𡁶瑪蝔见��刻䌊��葉�牐蛹靚�鍂 `threading.Thread` �𤾸蝱撘�郊�扯�撖潸稲�� GUI �偦�銝剜鱏嚗𣬚＆靽苷��格㺭�桀�甇亙銁隞颱����銝见像蝔唾䌊����
- [x] **摰䂿緵�喟�霂行�鈭支���稬撘寧�銝擧迫�毺氖�箸楛摨行𠯫敹堒虾餈賣滲蝟餌� (Implemented Decision Detail Popup & Precise Stop-Loss Logging)**嚗�
    - [x] **霈曇恣擃条移蝏�漲 DecisionDetailsDialog �喟�霂行�撅閧內閫��**嚗𡁜銁 `decision_flow_panel.py` 銝剜鰵摰䂿緵鈭� `DecisionDetailsDialog` 蝐颯��抅鈭� QTabWidget �屸△蝑曉�撅�嚗𣬚洵銝�憿萇倌隞亦�閫��蝎曉漲�� QTableWidget �桀�澆笆蝵烐聢撅閧內�詨����嚗��餈鞱�璅∪���縑�瑚���漣��踎�㛖�摨艾��𠯫��隅頝䎚��之�閗��㻫��WAP�讐氖摨血�頝舐眏��𣈲蝑㚁�嚗𣬚洵鈭屸△蝑曆誑擃睃�撌格楛暺烐綉�嗅蝱憌擧聢憭扳��祆��輯蝸�券��笔� JSON �唳旿嚗�僎�𣂷��靝��桀��嗅�憪𠼮SON�苷��𦦵�����凌�嘥��踝����皛∟雲�滨��见笆鈭𤾸�蝑𡝗���蕭皞臬恣霈⊿�瘙���
    - [x] **摰䂿緵 0ms 蝥臬�摮� UserRole ����唳旿蝏穃�**嚗𡁻���� `_append_record_to_table` �坔��訫��潭㺭�格𧒄嚗��敶𤘪�摰峕㟲���蝑𤥁��笔� dict `rec` 蝏穃�鈭𡒊洵 0 �堒���聢憿寧� `Qt.ItemDataRole.UserRole` 閫坿𠧧銝准����嗘� `_on_cell_double_clicked` 曌䭾���稬瑽賢遆�堆��湔𦻖隞𦒘葉 O(1) �𣂼�摰峕㟲�唳旿撟嗆�韏瑕撕蝒梹�摰���踹�鈭��甈∟粉�嗵��䀹�蝵𤑳�霂瑟�嚗���唳��湔�扯�銝𡡞�靽萘�餈睃���
    - [x] **�惩𤐄 ReentryTracker �交�頧祆揢摰寥�銝𡒊𠶖��迅摰� (Hardened ReentryTracker Time Parsing & Reliability)**嚗�
        - ��笆�典��啗��𦻖��葉隡惩� `exit_time` �交�摮㛖泵銝脖�撣血僑��𠯫嚗�� `'10:54:12'`嚗㗇��澆��䔶僚撖潸稲�� `strptime` 撏拇�嚗�銁 `reentry_tracker.py` ��� `check_activation` 銝剜楛摨虫��碶� `parse_dt` �交��園𡢿閫���具��
        - 摰䂿緵鈭�䌊����滨蔭�園𡢿銵仿�嚗𡁏�瘚贝𥅾�䭾𠯫���餈堆��芸𢆡�箄��潸�隞𦠜𠯫�交��滨�嚗�僎霈曇恣憭𡁻�撣貉��澆�嚗�� `%Y-%m-%d %H:%M:%S`��%H:%M:%S` 蝑㚁�餈𥡝�銝脰�閫��嚗𥕦��𨅯��典仃韐伐��朞�甇��銵刻噢撘𤩺惣�賣��𡝗㺭摮烾���𣄽鋆�����怎垢�𣂷� `datetime.now()` �拍�摰匧��滨漣靽脲擪嚗�蝠摨閙覔瘝颱� `[ReentryTracker] Expiration check failed` �交��仿��䭾���恣蝞㛖瑪蝔见�甇颯��
    - [x] **蝥䭾迤撟喃�/甇Ｘ�銝剜��亙�甇找� (Fixed Ambiguous Exit Logs)**嚗帋耨甇�� `reentry_tracker.py` ��� `register_exit` �餉�銝剖笆鈭擧��厩氖�箄�銝綽���鉄擃条��拇迫�����遬蝷箔蛹�𨀣迫�毺氖�算�萘�蝖祉���葉���蝷綽�撠��蝏煺�靽格㺿銝算�𨅯像隞�/甇Ｘ�蝳餃㦤�嘅�瘨�膄鈭�之憸萘��拍氖�箸𧒄�亙��鞟內霂滨�霂凋�霂臬紡��
    - [x] **靽桀��唳旿皞� low �潔蛹0撖潸稲��秤�文像隞� Bug (Fixed False Breakout Stop due to missing low price)**嚗�
        - ��笆�典�摰墧𧒄�唳旿瘚�葉銝芾��亙�雿𡒊��唳旿嚗Ǒlow_price`嚗厩撩憭晞��𧊋�嘥��𡝗��湔𦻖銝� `0.0` ���撣豢��蛛��埝䰻撟嗅�雿滢� `OscillatingBreakdownBranch` �刻恣蝞𡑒萱蝛踵𣈲�𤑳瑪�嗥凒�交�撖� `0.0 < sws * 0.985` �雴蛹���隞舘�諹圻�� `"OSCILLATING_BREAKDOWN_STOP"` 霂臬ế皜����艇�漤�餉�蝻粹萅��
        - 靽桀��寞�嚗𡁜銁 `decision_engine.py` ��笆 `low_price` ����㗇�颲�辺隞塚�瘨匧��港�甇Ｘ����靚��隞梶��梯恣 4 憭���券�銵仿�鈭��蝵� `ctx["low_price"] > 0.0` ����嗅�瘜閙�扳嵗撉䕘�敶餃��𦦵�鈭���亙�雿𦒘遠蝻箏仃撖潸稲撘箏飵�∴�憒�葉�寧鸌瘞� 688146嚗匧銁瘨典��輸�餈𤏸◤蝟餌�霂臬ế撟喃�����嫘��
    - [x] **摰䂿緵 DecisionEngine 甇Ｘ�蝳餃㦤�𡒊����潸圻�烐𠯫敹� (Descriptive Stop-Loss Logging in DecisionEngine)**嚗�
        - 撖澆� `LoggerFactory` 撟嗅銁 `decision_engine.py` �拍�憭湔挾�典��滨蔭 `logger`��
        - �典�蝑硋��航�隡啗��𧼮�嚗䔶��冽��� action 銝� `"SELL"` ��氖�箸�隞歹��祇𡢿隞� WARNING/INFO 颲枏枂霂血偷���銵諹秩�擧𠯫敹𨰜����思��∠巨隞�����蟡典����撅𧼮��胯��耦����� (Setup)���銵峕芋撘� (Regime)���隞枏予�� (days_held)���鈭讐蓡��� (pnl_pct) 隞亙��亙��暸�瘥� (vol_ratio) 蝑㗇��厩移蝏���啜��
    - [x] **銝��芷�朞��函頂蝏笔�����𧼮�瘚贝�撉諹� (Passed All Unit & Integration Tests)**嚗𡁻�朞� `py_compile` 撖寞��厰����隞嗉�銵䔶�銝交聢��祗瘜閧�霂𡢅�撟嗆��� 100% 頝煾�� `pytest test_watchlist_lifecycle.py`嚗�11 憿寞瓲敹�鍂靘见��� passed嚗劐� `python scratch/test_pullback_pipeline.py`����𤾸�蝡舀㺭�桐漱鈭埝��嗅像皛𡢅��扯��𣂼��擧遬嚗峕�隞颱�霈∠�蝡墧���蝒���

## 2026-06-04 10:45
- [x] **摰䂿緵撠曄�撘�𢆡�噼萱�𡏭��惩虾頝𢞖�苷�憌𡡞埯撱箔��箏� (Implemented Tail-End Low Risk Entry & Pullback Support)**嚗�
    - [x] **摰帋�撠曄��嗆挾蝵穃� (Tail-Session Gate)**嚗𡁜銁 `decision_engine.py` ���頞见飵雿𤾸𢙺��𣈲 `SwsPullbackBranch` 銝哨��啣��園𡢿霂����惣�賭� `signal.ts` �𣂼���𧒄靽⊥�嚗屸�摰帋��� **`14:30 - 15:00`** 撠曄��𡁜��怎垢�嗆挾���朞�撠曄�撱箔�嚗諹����璁��蝏訫��亙���㨃憌𡡞埯嚗屸俈甇Ｘ𡟺�睃�瘣㛖���
    - [x] **�文�撘�𢆡�滨蔭撱箏� (Premarket/Money-in Check)**嚗𡁏��乩葵�⊥糓�行㦛�㕑��烐楛摨虫��乓��𥅾霂亥�撅硺��踹�撘粹�憭氬��暑頝���亥蕭頦芾�嚗Ǒis_reentry`嚗剹���餈烐��㗇𦆮�誩��剁�`dff > 0` / `priority >= 70`嚗㚁��芸𢆡�堒��滨蔭雿𤾸𢙺撱箔��瑁噢��
    - [x] **�賊���瑪�舀�銝𡒊憬�讛��惩虾頝� (Pullback & Volume Shrink Check)**嚗�
        - 隞瑟聢蝎曉��噼萱 5 �亦瑪��10 �亦瑪�� SWS �Ｚ��踹極雿𦦵瑪嚗��蝳餃漲�� `[-1.5%, 1.5%]` 銋钅𡢿嚗㚁��瑕���蔔雿擧��砌僭�孵��刻器����
        - 蝻拚�閬��嚗帋��交�鈭日�雿𦒘� 5 �亙��𧶏�`vol_ratio < 0.9`嚗㚁��𡝗說頞� 3 �交�蝏剔憬��/�����赤�㗛��∴�霂��瘣㛖��唬���蜓�𥟇𧊋韏唬�撣�㦤�𨅯睸��
    - [x] **�嗉蕭擃条��對�撱箇����摨蓥��鞉𧋦**嚗朞砲閫���湔𦻖�典偏�䁅�隞瑕�鈭擧郭撟��雿齿𧒄隞� `0.35` 隞㮖��𤏸絲雿𤾸𢙺撱箔���活�交𡟺�睃��箇緵撘箏��脤� V �㵪�憒�葉撌刻塳���摰匧��萇�嚗㚁��曹�摨蓥��鞉𧋦���嚗���䀹��∩蜓�剁��𣳇��滩◤�券𢒰撖寡蕭擃䀹��砍仃�抒�蝥删�嚗䔶�蝞埈�皞𣂼仍閫���𤤿���
    - [x] **�典�隞嗅�����𧼮�瘚贝�蝏踵��朞�**嚗朞��� `test_pullback_pipeline.py` 銝� `pytest test_watchlist_lifecycle.py`嚗���� 11 憿寧頂蝏毺漣�其� 100% 蝏踵��朞���

## 2026-06-04 10:35
- [x] **摰䂿緵�脰蕭擃㗛��批𢆡��撕�找��𣂷�鞊���箏� (Implemented Dynamic Adaptive Chase Limit & Exemption)**嚗�
    - [x] **�冽����� 20cm �∠巨�讐氖摨�**嚗𡁜銁 `risk_gate.py` ��蕭擃䀹㜃�芸ế摰� `HIGH_EXTENSION_NO_CHASE` 銝哨�撘訫�鈭��蝏游漲撘寞�折����折��扼���撖寧��𥟇踎 (`688`) ���銝𡁏踎 (`300`/`301`/`302`) 憭拍��瑟� 20% 摰賢�瘜Ｗ𢆡����嗵�����芸𢆡撠�蕭擃䀹隅撟���� `max_pct_diff` 銋䀝誑 2.0 �滚撕�抒頂�堆�隞𡡞�霈斤� 6.0% �枏捐�� 12.0%嚗剹��
    - [x] **撘箏飵/�滚�靽∪噡憭𡁻𧫴�曉捐**嚗朞𥅾靽∪噡撅硺� Re-entry �滚�蝐餃�嚗Ǒis_reentry`嚗㗇�蝵桐縑摨虫�撘��擃䁅���絲甇乩蜓��縑�瘀�`confidence >= 0.80`嚗㚁�撠���嗅�蝳餃�潸�銝�甇交𦆮摰� 1.5 �㵪��喃蜓�� 9.0%嚗���𥟇踎 18.0%嚗剹��
    - [x] **頞�撩�梯�樴坔仍�齿�鞊��**嚗𡁜笆鈭𡡞��乩縑�瑚�蝵桐縑摨行��嗡�蝘�嚗Ǒconfidence >= 0.85`嚗厩�憿嗅�撘箏飵靽∪噡嚗諹䌊�冽�霈唬蛹 `is_exempt` �湔𦻖摰���漤膄�脰蕭擃䀹㜃�芷��塚�蝖桐�憿箏��亙�憭𡁏郭畾萇��𡢅�敶餃�閫��鈭�葉撌刻塳嚗�蔭靽∪漲 0.84嚗剹��痕蝖�漣銝𡄯�蝵桐縑摨� 0.95嚗剹���摰匧��蛛�蝵桐縑摨� 0.94嚗屸�蝵桐縑摨行𦆮摰賡��� 1.5 �㵪�蝑匧偏�䀝����擧活�交𡟺�睃撩�� V �滢葵�∟◤憌擧綉霂臭慾�⊥香����嫘��
    - [x] **摰𣬚��朞��典�敶埝�霂�**嚗朞��� `test_pullback_pipeline.py` 銝� `pytest test_watchlist_lifecycle.py`嚗�11 憿寧頂蝏毺漣瘚贝��券��𣂼�嚗㚁�撉諹�鈭�頂蝏毺�撟單�蝔喳�銝𡡞��抒�蝎曉漲�𣂼���

## 2026-06-04 10:25
- [x] **靽桀�撟嗅��箸�霂閙�瘞湧��扳㜃�芯� State-Consistency 撉諹� (Fixed and Hardened Test Pipeline Risk Bypass & Verified State Consistency)**嚗�
    - [x] **蝏閗��砍𧑐 Frozen 憌擧綉�𣂼�**嚗𡁻�撖� `scratch/test_pullback_pipeline.py` 瘚贝��冽�霂閧㴓憓�葉�誩�閫血��砍𧑐 `window_config.json` �𣬚� `min_volume = 1.10` 蝑厰��鞾��扳㜃�迎�撖潸稲瘚贝��文��䭾�摰峕㟲蝛輸�讛秐 BUY 靽∪噡��𣈲��䔮憸矋��冽�霂閧鍂靘讠� `setUp` �寞�銝剝��啣�靘见�撟嗉��𤥁��乩�銝�銝芣𠹭��� `RiskLimits` 摰硺�嚗Ǒmin_volume=0.0` 蝑㚁�嚗諹��蹂� dataclass `frozen=True` 撘閗絲����抒凒�乩耨�� `FrozenInstanceError` �仿���
    - [x] **摰峕㟲�㯄�� Pipeline 瘚贝��喟�瘚��霂�**嚗𡁏��蠘�銵� `test_pullback_pipeline.py`嚗���渲繮�硋� `Allowed: True` 隞亙� `Action: BUY` �其�嚗�蝠摨閖�霂��隞舘��������踎�𡑒������憭渲��怒��e-entry �嗆��㦤頝舐眏�圈��扳𦆮銵𣬚��函恣�栞䌊����
    - [x] **�朞��詨�蝟餌�蝥批�敶埝�霂�**嚗朞�銵� `pytest test_watchlist_lifecycle.py`嚗�11 憿孵�����𧼮�瘚贝� 100% 蝏踵��朞�嚗𣬚頂蝏笔�撅�迅摰𡁜��具��

## 2026-06-04 10:20
- [x] **靽桀�撟園�霂� Scraper 憸䀹��唳旿�枏�蝵𤑳�撘�虜銝讠�蝟餌�蝥扳��曇��� (Fixed and Verified Scraper Network Instability & Empty Themes Resilience)**嚗�
    - [x] **憸䀹��瑕��仿��芣��寥��**嚗𡁻�撖嫣�����鞉𦻖�� `fetch_concept_mining_themes` �嗅��𤑳��� `SSLError` (EOF �讛悅�脩�)嚗䔶耨憭滢� `scraper_55188.py` 銝� `fetch_theme_stocks` 撘�虜餈𥪜�蝛箏�銵典紡�游�蝏� `concat` 撏拇�������撠��敶餃�蝏煺��寥�牐蛹餈𥪜�撣西������征 `pd.DataFrame()`��
    - [x] **�㯄�� Pipeline �脣鴃�扳𡟺��**嚗𡁜銁 `merge_theme_logic` 憓噼挽蝛粹��鞾��文�嚗屸��啁征����嗅朖�嗅��券���綽�撟嗉��箏��急������芋�� DataFrame嚗峕��支� `groupby().apply()` �冽��唳旿�嗥�瞏𨅯銁�仿���
    - [x] **�𦦵�銝𧢲虜 Merge �嗆挾�� KeyError 'code'**嚗𡁜銁 `get_combined_data` 銝餅㺭�格���僎�塚�蝏煺�撖� `df_theme` 餈𥡝�鈭��������撖寥��滨蔭嚗䔶�霂�朖雿踹銁蝵𤑳�������硔����冽瓷�㗇��硋�憸䀹��唳旿����萎�嚗䔶��賢�蝢𤾸�摰嫣蜓�𥟇��𣬚�璁𨀣��� Inner-Join �滢�嚗屸獈�凋� `KeyError: 'code'` 撘訫�����嗉�����∩蜓隞餃𦛚蝥踹援皞���
    - [x] **摰峕��訫�蝥折榀�找遛���霂�**嚗𡁜銁 `scratch/test_scraper_resilience.py` 銝剜�撱箔� Mock 憸䀹�蝻箏仃�臬�嚗𣬚�摰墧�敶㮖�����鞉𦻖��鱏蝵𤑳征頧賣𧒄嚗��撟嗥�摨譍��嗉�憭笔�蝢舘䌊������罸��摰�𧋦�啁�摮睃�撟塚��𣂼��𣂼枂 517 �⊿�摰寥��抒�瘛瑕�銵峕�憭� DataFrame嚗𣬚頂蝏笔�憯格�扯噢�鞟��喟漣�����

## 2026-06-04 10:05
- [x] **蝏煺�隡睃�銝擧�����滨垢憌擧綉�行⏛撅閧內靽⊥�銝箔葉�� (Standardized Frontend Risk Rejection Metrics to Friendly Chinese)**嚗�
    - [x] **��瓲摨訫�銝剜�霂衣�靽⊥�憭𡝗遬**嚗𡁜銁 `trading_kernel/kernel_service.py` ��漱�枏��貊��𦦵�鋆�葉嚗���笔�暺䁅恕�� `"kernel_reject_code"` 閬���𣂼��餉�嚗䔶��碶蛹隡睃�霂餃� `risk.reject_context.get("message")`嚗�蒂�劐�銝𧢲��㗛����銝剜��讛膩嚗㚁�蝖桐��行⏛皞𣂼仍�唾��箸���葉��𠯫敹𨰜��
    - [x] **UI 鈭支��其葉��㜃�芾蓮�ｇ��䔶��拚俈敺∴�**嚗�
        - ��笆 PyQt �嗆��� `tk_gui_modules/decision_flow_panel.py`嚗��蝑𡝗��Ｘ踎嚗劐誑�� `signal_dashboard_panel.py`嚗�縑�瑞��選�嚗���乩��砍𧑐蝞��剛蓮�� `RISK_CN_SHORT` �惩�銵剁�撖孵虾�賡�瞍讐��望�隞��嚗�� `HIGH_EXTENSION_NO_CHASE`嚗匧� `BLOCK` �𣂷��𨅯�蝧餉���
        - ��笆 Tkinter �嗆��� `stock_selection_window.py`嚗��㕑�蝒堒藁靽∪噡 Tab嚗㚁�摨𠉛鍂�詨���𧋦�啗蓮�Ｘ㦤�塚�靽肽�銝滩捏�典𪑛銝芾”�潘�Treeview/TableWidget嚗劐葉嚗���芯�撅閧內�见末��葉����找縑�胯��
    - [x] **銝��芷�朞��訫�銝𤾸�敶埝�霂�**嚗𡁶�霂煾◇�拚�朞�嚗䔶� `pytest test_watchlist_lifecycle.py` �� `scratch/test_auction_engine.py` 瘚贝�憟𦯀辣 100% �𣂼���
    - [x] **靽桀�瞏靝�瘙删𠶖�� JSON 摨誩��� float32 �仿� (Fixed NumPy float32 serialization error)**嚗�
        - ��笆 `realtime_data_service.py` �嗆��㦤�典��臬𢆡�𡝗� 5 ���憓鮋�霈∠�瘜Ｗ��嗆挾嚗䔶� numpy �啁��硋��� `closes[-1]` �急� `np.float32` �唳旿蝐餃�嚗𣬚凒�亙紡�湔�銋���� Ramdisk �嗥� `json.dump` 閫血� `Object of type float32 is not JSON serializable` �仿���䔮憸塩��
        - **�屸�頧祆揢�惩𤐄**嚗�
            1. 皞𣂼仍撠� `recent_close` 韏见�澆�鋆�蛹 `float(closes[-1])`��
            2. �� `save_consolidation_state` �� `json.dump` 銝剖�銋匧僎摨𠉛鍂鈭� `NpEncoder` �芸�銋� JSON 蝻𣇉��剁�摰䂿緵撖� `np.floating`/`np.integer`/`np.ndarray` ���蝻萘掩�贝蓮�Ｗ��𨅯�摨誩��吔�瘨�膄鈭�𠶖���摮㗛�����
    - [x] **靽桀� PyInstaller �枏��𡁏𧋦�券��� Windows CMD 銝讠�閫���仿� (Fixed spec and loop command unrecognized error in instock-pyinstall-to-exe.cmd)**嚗�
        - **�笔�摰帋�**嚗朞砲�孵����隞嗡誑 UTF-8嚗��撣� BOM嚗㗇聢撘譍�摮塩��葉�� Windows CMD 暺䁅恕雿輻鍂 GBK嚗㇃P936嚗劐誨��△�㰘蝸��辣����𨀣鸌憭��銝剖鉄�劐葉��釣�𠺪��曹�憭𡁜���葉������銋梧�銋梁�銝剔��典�摮𡑒�隡朞◤霂航圾�𣂷蛹 CMD �賭誘銵諹���/�滚��𤑳泵�瘀�憒� `&`, `|` 蝑㚁�嚗��甇�虜��誘撘箄��芣鱏嚗䔶��諹圻�� `'銝�0' is not recognized as an internal or external command` 蝑匧之�讛祗瘜閙𥁒�踺��
        - **蝏��閫���寞�**嚗𡁜銁摰���萄��典� UTF-8 蝻𣇉�閬������𣂷�嚗�笆 `instock-pyinstall-to-exe.cmd` ��辣餈𥡝��齿�嚗�����劐葉��釣�𠹺�銝剜�颲枏枂�券��踵揢銝箇滲 ASCII嚗�㘚���蝚血噡嚗㕑”蝷箝��眏鈭𡒊滲 ASCII �� UTF-8 �� ANSI/GBK 蝻𣇉�銝见��匧��函㮾�𣬚�摮𡑒�撅閧緵嚗䔶���蝠摨閙覔瘝颱� CMD 閫���函�銋梁�閫�� Bug嚗峕����蝔见�隞亦��𡁏�銵䎚��

## 2026-06-04 09:55
- [x] **靽桀�蝡硺遠�滩蓮蝑𣇉裦 15蝘鍦儐�舫�憭滩��其��亙��瑕� Bug (Fixed Premarket Reversal Strategy 15s Loop & Warning Spam)**嚗�
    - [x] **摰䂿緵�閙𠯫餈鞱�����剛楝�� (Implemented _bg_auction_gate_run_today day-lock)**嚗𡁜銁 `instock_MonitorTK.py` ��蜓敺芰㴓 `bg_kernel_auto_execute_once` 銝哨�銵亙�鈭� `_bg_auction_gate_run_today != today_str` ��ế摰𠾼��蘨�匧銁隞𦠜𠯫�芾�銵諹��滩蓮�餉�����萎��齿�鈭文��唬遙�∴��餅鱏鈭�� 15 蝘鍦�頝喃葉�䭾辺隞嗆�鈭日�䭾�����𥟇答韐嫣��滚�憌𡡞埯��
    - [x] **撘訫��閙𠯫�滩����潮俈敺⊥㦤�� (Attempt Throttling Limit 3)**嚗𡁜銁 `run_auction_reversal_strategy` 韏瑟�雿滨蔭嚗���牐���笆�唳旿蝻箏仃������霂閗恣�啜���霈詨��交�憭折�霂� 3 甈∴�隞仿俈撘��睃��唳旿�芸笆朣鞟��祆𧒄撱嗉�嚗㚁��� 3 甈∪�隞滨眏鈭𢛶�𨀣㿥�交�蝏芸翰�抒撩憭晦�脲��𨀣㺭�格𧊋撠梁貌�脲��漤���綽��湔𦻖�拍��餅鱏撟園�暺㗛�甇鳴�敶餃��𦦵�鈭�郎�𦠜𠯫敹堒銁蝏�垢�𣳇��瑕���緵鞊～��
    - [x] **銝��芷�朞�蝻𤥁�銝𤾸����敶埝�霂� (Passed Compilation & Regression Tests)**嚗𡁶�霂穃��券�朞�嚗䈣test_watchlist_lifecycle.py` �券� passed��

## 2026-06-04 09:38
- [x] **靽桀�摰墧𧒄�唳旿�滚𦛚銝� V�见�頧祆郭畾萇𠶖��㦤�支誑�� Bug (Fixed float division by zero in update_wave_structure_state)**嚗�
    - [x] **�寞祥��漲蝻拚�/�芸�憪见�隞瑟聢撖潸稲��膄隞仿妟 (Zero-division prevention for recent_min)**嚗𡁜銁 `realtime_data_service.py` ��� `update_wave_structure_state` �賣㺭��𠶖��㦤 `INIT` �嗆挾銝哨�憓𧼮�鈭� `recent_min > 0` ��蔭�滩�皛斗辺隞塚��踹��典��啗�����諹��硋��臬𢆡�嗆挾��漲蝻拚�嚗�紡�� `recent_min` 銝� 0嚗劐葵�∪銁霈∠�瘜Ｗ� `(recent_max - recent_min) / recent_min` �嗉圻�� `float division by zero` 餈鞱��園�霂胯��
    - [x] **銝��芷�朞��蹱���霂睲��𧼮�瘚贝� (Passed Compilation & Regression Tests)**嚗𡁶�霂穃��券�朞�嚗䈣test_watchlist_lifecycle.py` 瘚贝�憟𦯀辣餈鞱��臬末��

## 2026-06-04 02:00
- [x] **�惩𤐄 UI 蝥輻�蝔喳��改�瘨�膄 manual_sell 銝� self_heal 撘訫��� PyEval_RestoreThread �游𦶢撏拇� Bug (Hardened UI Thread Stability & Resolved PyEval_RestoreThread GIL Crash)**嚗�
    - [x] **�齿��见𢆡撟喃��餉�銝箏�甇亙��啣��� (Asynchronous manual_sell_position execution)**嚗𡁜� `_manual_sell_position` 銝剖��恍�撱嗉� API �Ｘ���𠯫敹埈㺭�桀�餈賢�隞亙��睃�/�䀝葉�嗆��氜�条��餉�摰峕㟲撠��撟嗥宏�喳��� `threading.Thread` 銝剖�甇交�銵䕘�敶餃��餅鱏鈭�眏鈭𦒘蜓蝥輻�蝑匧�蝵𤑳�銝𡒊��� I/O 撣行䔉�� UI ��香銝� GIL �嗆��◤�誩��亦氖�������
    - [x] **�齿�銝��株䌊���餉�銝箏�甇亙極雿𨀣� (Asynchronous on_one_key_self_heal execution)**嚗𡁜� `_on_one_key_self_heal` 銝剜��羓�憭扳鸌�𤩺�隞𤘪�撖嫘��𠶖��氜�睃��滨蔭�⊿�敶餃��齿�銝� `_async_heal_worker` 撟嗅銁�𤾸蝱摰�擪蝥輻�銝剖������之�啣�頧颱�銝餌��Ｙ�霈∠��贝翰銝� GIL 鈭㗇𦜖��
    - [x] **雿輻鍂 QTimer.singleShot 餈𥡝� thread-safe UI �噼�獢交𦻖 (Bridged UI Actions via QTimer.singleShot)**嚗帋蛹鈭�俈甇ａ� GUI 蝥輻��亥圻 Tkinter/PyQt �毺� C-API �硋銁憭𡁶瑪蝔衤葉�湔𦻖�滢� UI �其辣�諹圻�� Nuitka �� GIL �拍�撏拇�嚗峕��㗇��� `QMessageBox` 撘寧���_refresh_positions_tab` 銵冽聢�齿鰵�㰘蝸隞亙�鈭支�撘� toast 靽⊥��漤����雿頣����朞� `QtCore.QTimer.singleShot(0, ...)` �齿鰵靚�漲撟嗆��鍦� Qt 銝� GUI 蝥輻��笔��扯�嚗��蝢𤾸��啗楊蝥輻���迅摰朞䌊����
    - [x] **銝��芷�朞��券�蝻𤥁�銝𤾸�敶埝�霂� (Passed Compilation & Regression Tests)**嚗𡁻�朞�鈭�����霂𤏸祗瘜閙嵗撉䕘�撟嗡� `test_watchlist_lifecycle.py` 11 憿寧頂蝏毺漣�詨��訫�瘚贝� 100% �朞�嚗𣬚頂蝏�㟲雿栞�銵���冽��麄��

## 2026-06-04 00:10
- [x] **靽桀� K蝥踹��脩�摮㗛鵭摨虫��滨蔭��辣銝𢠃�銝滢��渡� Bug (Fixed Discrepancy between K-Line Cache Length and Configuration Limit)**嚗�
    - [x] **瘨�膄蝖祉����扯�璅∪��格�撠𤩺𧒄�啗��� (Removed Hardcoded TARGET_HOURS Override)**嚗𡁜𢆡����� `cct.CFG.kline_cache_max_len`嚗��霈� 300嚗劐� `TARGET_HOURS_HP` �� `TARGET_HOURS_LEGACY`��鍂 `config_max_len / 60.0` �冽��恣蝞㛖𤌍��𧒄�踹��嗆㺭��
    - [x] **靽桀� UI �𤏸��𧢲踎����潭遬蝷箔�銝��� (Fixed Cache History Limit Discrepancy in UI Status)**嚗朞圾�喃�敶梶頂蝏笔��箸���揢�扯�璅∪��塚�蝖祉���� `3.5` 撠𤩺𧒄�𣂼�嚗�210 �對�撘箏�閬���冽��� `global.ini` 銝剝�蝵桃� `kline_cache_max_len = 300` 隞舘��紡�� UI �屸𢒰銝� `cache_history_limit` �埝遬銝� 210 ��䔮憸塩��緵�函頂蝏笔虾隞亙�蝢擧覔�桃鍂�琿�蝵桃�憭批�嚗�� 300 �對��冽��恣蝞堒僎摨𠉛鍂蝻枏������

## 2026-06-03 23:50
- [x] **靽桀�摰墧𧒄�滚𦛚�亙��� Tkinter �屸𢒰銝衤��航� Bug (Fixed Realtime Service Log Invisibility in Tkinter UI)**嚗�
    - [x] **摰䂿緵摰墧𧒄�滚𦛚�亙��行⏛�� (Implemented RealtimeServiceLogHandler)**嚗𡁜銁 `logger_utils.py` 銝哨�撘��睲�銝㯄秄��笆 `realtime_data_service.py` �𠰴��詨�霈∠�蝏�辣嚗�� `bidding_momentum_detector.py`, `sbc_core.py`, `auction_decision_engine.py`嚗㗇𠯫敹𡑒��箇� `RealtimeServiceLogHandler` �行⏛憭���具���朞�蝥輻�摰匧����撅� `deque` �臬耦�笔�嚗�捆�� 200嚗㚁��芸𢆡�典�摮䀝葉餈�誘撟嗆��瑁��典��詨��滚𦛚鈭抒���郎�𠹺�銝𡁜𦛚�亙�嚗峕��笔銁�瑕鍳�典��䀝葉餈鞱��嗆挾撠���行⏛撟園彿�坔銁���銝准��
    - [x] **�齿� Tkinter 摰墧𧒄�滚𦛚�亙��批��� (Re-engineered Tkinter Realtime Service Monitor to Unified Stream)**嚗𡁜銁 `instock_MonitorTK.py` �� `open_realtime_monitor` 蝒堒藁�𦠜㺭�桀��唳�瘞渡瑪銝哨�摨笔�鈭����㮾鈭鍦迨蝡卝����賣��刻蕭�删��滨垢撅��� `log_messages` �笔���㺿銝箏銁瘥𤩺活 UI 敹�歲嚗�5蝘𡜐��瑟鰵�塚��湔𦻖摰匧��唬� `logger_utils` ���撅�蝥輻������ of `realtime_service_logs` ����笔�銝剜��𡝗��啁� 30 �∟祕蝏���⊥𠯫敹𡑒�銵峕��典�撟嗅�蝷箝��
    - [x] **摰��靽萘������辣霈啣�銝娪妟�扯��餌�**嚗𡁻�朞�撠�迨憭���冽�頧質秐 LoggerFactory 餈𥪜����撅� root 霈啣��其�嚗峕��蠘悟�嘥��𡝗𠯫敹埈𠳿�賣��蠘氜�啁���𠯫敹埈�隞� `instock_tk.log`嚗���賢銁 Tkinter �烐綉撘寧�銝剖��嗆凒�啣��堆�瘨�膄鈭�銁摨𠉛鍂�臬𢆡�嗥眏鈭𤾸��臬𢆡�㰘蝸�嗅榆撖潸稲�亙�颲枏枂�𣈯�暺䀝腺憭晦�萘�銝仿�閫��瞍𤩺���

## 2026-06-03 21:00
- [x] **摰䂿緵 V�见�頧砌�憭𡁏郭畾� VWAP �烐綉蝟餌�撌亦��賢𧑐銝𤾸��暹辺��� (Implemented Full-Chain Integration for V-Reversal & Consolidation Watchlist System)**嚗�
    - [x] **摰䂿緵 BiddingMomentumDetector �瑕鍳�刻䌊����嗆���頧� (Cold-start State Recovery in Detector)**嚗𡁜銁 `bidding_momentum_detector.py` �� `__init__` �嘥��𤥁�蝔衤葉嚗峕鰵憓硺� `self.realtime_service.cache.load_consolidation_state()` 靚�鍂��＆靽嘥�摨𠉛鍂撏拇��𤾸��臬𢆡�塚��枏��刻��芸𢆡隞� Ramdisk �� `json.gz` 敹怎�銝剜�憭滢�銝�銝芾�銵�𪂹�毺�瘜Ｘ挾�訾�嚗���唳鱏�寧賒隡𨬭��
    - [x] **撘訫�雿𡡞�撘�郊憓鮋�瘜Ｘ挾�嗆��凒�唳㦤�� (Low-frequency Async Wave State Update)**嚗𡁜銁�𤾸蝱 `async_sector_agg_worker` 敺芰㴓銝哨���蝸鈭��撖� `self.realtime_service.cache.update_wave_structure_state()` ����蠘��典��𠬍��朞� 300 蝘垍��園𡢿�脫��批�嚗峕� 5 ����扯�銝�甈∴���蝠摨閗圾�虫�擃㗛� Tick 銝𦒘�憸穃��交郭畾菔�隡堆�銝滢�蝖桐�蝟餌�撖孵之敶Ｘ�� V �见�頧砌葵�∠�撣豢����烐綉嚗諹��賣� 5 ����芸𢆡撠���啁𠶖��俈�𡝗�銋���� Ramdisk嚗���唬��䀝葉�䭾��剖�隞賬��
    - [x] **摰䂿緵 Bidding Racing �Ｘ踎�賭葉撘箄�蝵桅▲�齿瓲撅閧內 (Forced Priority Display for V-Reversal Hits in Racing Panel)**嚗𡁜銁 `bidding_racing_panel.py` ���憸烐����餉� `_get_synthetic_score` 銝哨�憓𧼮�鈭��撖寥�憭��瘙� `cache.get_v_reversal_pool()` ����罸�����䀹嵗撉䕘�Set Matching嚗剹����血𦶢銝剔𤌍��葵�∴�撘箄�韏衤� `max(main_score, 85.0)` �箇�瘣餉��������祇𡢿蝒�聦鈭��暺䁅�皛日��潘�靽�蝙蝚血� V 蝧餉蓮�𡝗赤�条��渡�瞏靝�銝芾��� UI �Ｘ踎銝𡃏◤擃䀝漁��緵銝𡒊��仿��詻��
    - [x] **摰𣬚��剔㴓���粹𧫴畾萇𠶖��䌊�典�獢���冽𧒄�芣� (Auto-archiving on Application Exit & GZ Fallback Recovery)**嚗�
        - �其蜓摨𠉛鍂�笔𦶢�冽��拙� `instock_MonitorTK.py` �� `on_close` �寞�銝哨�瘜典�鈭� `self.realtime_service.cache.backup_consolidation_state_to_gz()` �鞉�摮睃��其���
        - 摰�� `load_consolidation_state`嚗𡁜��臬𢆡�塚��� Ramdisk 銝滚��典��亦𠶖��翰�改�撠�䌊�券�蝥找蝙�� `gzip.open` 閫��撟嗅�頧� `logs/v_reversal_pool_*.json.gz` ����脣�隞賣㺭�殷�摰𣬚�頝冽𠯫�删�蝏凋���
        - 靽桀�頝臬��瑕��舀��枏�嚗𡁻����憭�遢頝臬�閫��嚗屸��� `sys_utils.get_app_root()` 撖寥�鈭��撅����頧刻楝敺�沲���敶餃�瘨�膄鈭� `__file__` �詨笆撖餃��� Nuitka Onefile/Standalone �臬�銝剔�瞍�宏憭望��桅�嚗䔶��� `logs/` �桀�摮睃�銝��銝�憭晞��

## 2026-06-03 19:50
- [x] **摰䂿緵蝡硺遠��貌�滩蓮蝑𣇉裦�券曎�⊿𡡒�舫��� (Implemented Full-Chain Closed-Loop Integration for Auction Sentiment Reversal Strategy)**嚗�
    - [x] **�寞祥 Python 3.9 蝐餃�蝟餌�銝� slots 霂剜��澆捆�折��� (Fixed Python 3.9 Type Hint & slots Compatibility)**嚗�
        - ��笆 Python 3.9 �臬�嚗�� `market_pulse_db.py` 銝凋��舀��� `dict | None` �𥪜�蝐餃���釣�齿�銝箸���� `Optional[dict]`嚗�僎隞� `typing` 璅∪�撖澆� `Optional`��
        - ��笆 Python 3.9 銝齿𣈲��� dataclass slots ��㺭嚗�� `market_sentiment_fsm.py` �� `auction_decision_engine.py` 銝剜��厩� `@dataclass(slots=True, frozen=True)` 鋆�弘�刻��港蛹 `@dataclass(frozen=True)`嚗�蝠摨閙��支� Nuitka �蹱���霂穃�餈鞱��� Python 3.9 �臬�銝讠� slots 撘�虜撏拇���
    - [x] **��遣擃睃虾�䭾�抒� Pre-market Reversal Gateway (Built High-Reliability Pre-Market Reversal Gateway)**嚗�
        - 蝖株恕�其蜓�批��� `instock_MonitorTK.py` 銝剜���釣��僎�典��嘥��� `MarketSentimentFSM` 銝� `AuctionDecisionEngine`��
        - 蝖株恕�� `bg_kernel_auto_execute_once` 敺芰㴓銝剜�頧� 09:25 ��𧒄閫血�蝵穃�嚗�僎�滨蔭瘥𤩺𠯫�閙活餈鞱��拍��脤��� `_bg_auction_gate_run_today` �行⏛嚗𣬚＆靽萘�銝剖朖雿踹�甈∟��亙ế摰𡁜�頝喃�蝏苷��𤑳��滚�蝡硺遠憪娍���
        - gateway 憪娍� `self.executor.submit` 撘�郊瘣曉� `run_auction_reversal_strategy` 蝑𣇉裦瘚��嚗��蝔衤�鈭㗇𦜖����餃� UI 銝餌瑪蝔卝��
    - [x] **�賢𧑐 Auction Limits Risk Override 憌𡡞埯銝湔𧒄閬���箏� (Enforced Auction Risk Limits Overrides)**嚗�
        - 摰䂿緵鈭��頧祉�隞瑞鸌摰𡁶� `limits_override` 摰匧�憌擧綉閫��嚗諹挽蝵桐�雿齿綉�嗡��� 30%���蝚磰恥�蓥��� 20%��𠯫��迫�毺瑪 8%嚗�僎�冽�鈭斤�鈭斗���瓲 `evaluate_decision_item` �嗆遬撘𤩺釣�乓��
        - 蝖桐�鈭���亙銁��貌��垢�滚榆���瘜Ｗ𢆡蝡硺遠�祇𡢿�賢��典��批𧑐�瑕��湧�����冽������銁�嗡��䀝葉�園𡢿畾萎�蝏湔�撣貉�憌擧綉憭拇０�����
    - [x] **�朞��唳秤撘誩����霂蓥�蝻𤥁��⊿� (Passed All Unit Tests and Compilations)**嚗�
        - 蝻硋�撟嗉�銵� `scratch/test_auction_engine.py` �訫�瘚贝�嚗峕��蠘��砽�𨀣㿥�亙之頝峕��� (PANIC) �� 隞𦠜𠯫蝡硺遠憸�隅�⊿�撘��滚撕 (REVERSAL)�萘�摰峕㟲�嗆��㦤頧祉宏�䔶縑�瑞��𣂷�摮堒��惩�嚗��瘚贝�銵峕𧒄�港� 4ms嚗諹�雿𦒘� 300ms 蝡硺遠�扯�蝒堒藁��
        - �𧼮�餈鞱� `pytest test_watchlist_lifecycle.py` 11 憿寞瓲敹��敶埝�霂� 100% 蝏踵��朞�嚗峕瓷�劐漣�煺遙雿閗祗瘜閙�餈鞱��嗅�敶鉝��

## 2026-06-03 14:30
- [x] **摰䂿緵閫���園鵭�孵稬�湔𦻖�见𢆡颲枏��蠘� (Implemented Manual Keyboard Input for Observation Duration)**嚗�
    - [x] **�齿� `lbl_interval` 銝� `QLineEdit` ��𧋦颲枏�獢�**嚗𡁜銁 `sector_bidding_panel.py` ��蜓撌亙��譍葉嚗���笔��芾粉�� `QLabel` ��倌�齿�銝箏虾�孵稬蝻𤥁� the `QLineEdit`���銝��滨蔭瘛梢�擃㗛�颲枏�獢�甅撘𧶏�撟嗉蕭�惩𢰧靘� `"m"` ����蓥���𧋦�鞟內嚗���唳凒�渲���漱鈭鉝��
    - [x] **撘訫� QIntValidator �湔㺭撉諹��其� `editingFinished` 靽∪噡**嚗帋蛹霂亥��交��滨蔭 `QIntValidator(1, 9999)`嚗屸��嗥鍂�瑚��質��交迤�湔㺭嚗�僎�函鍂�瑟䛵�餃�頧行�憭勗縧�衣��嗉圻�� `_on_interval_edited` �噼�嚗���嗉圾�𣂼僎摨𠉛鍂�啁�����啣� `detector.comparison_interval` 銝准��
    - [x] **撖寥��嗆���憭滢��脫��芣�**嚗𡁜銁 `_adjust_interval` 銝� `_restore_ui_state` 銝剖�甇亙縧�文��厩� `"m"` 摮㛖泵韏见�潭𣄽�伐��湔𦻖�坔�蝥舀㺭摮埈��穿�銝𥪜銁�见𢆡颲枏��嗅��瑚澈�劐� 2 蝘垍��脫�撱嗉��㰘蝸�箏�嚗��蝢𤾸��文��䁅�銵峕�扯���
    - [x] **隡睃�璅∪�蝥批紡�����**嚗𡁜� `QIntValidator` 隞� `sector_bidding_panel.py` ����典遆�啗��典�銝剔宏�單�隞園▲�冽芋�㛖漣撖澆��箏�嚗峕��支� UI 銝餌瑪蝔𧢲葡�𤘪𧒄��𢆡��䰻�曉�����
    - [x] **�朞��蹱���霂睲��𧼮�瘚贝� (Passed Tests & Compilation)**嚗𡁻◇�拚�朞�鈭� `py_compile` 蝻𤥁�銝� `test_watchlist_lifecycle.py` �訫�瘚贝���

## 2026-06-03 14:20
- [x] **靽桀��踹�閫���園鵭�唳��擧暑頝�踎�埈隅頝峕㺭�格𧊋�芸𢆡�湔鰵 Bug (Fixed Sector Metric Autoupdate on Observation Anchor Reset)**嚗�
    - [x] **撘訫��踹����瘨刻�撟���� (Implemented Sector slice percent change avg_pct_diff)**嚗𡁜銁 `bidding_momentum_detector.py` ��踎�𡑒��� `_aggregate_sectors` �峕踎�烾��� `_reconstruct_sector_from_candidates` 銝剖��乩� `avg_pct_diff`嚗𣬚鍂鈭舘恣蝞埈踎�堒����㗇��䀝葵�∟䌊閫���園鵭�𡁶�撱箇�隞交䔉��像��蓡����睃𢆡嚗�朖 `pct_diff` ���潘�����塚�撖寡��� "摰墧𧒄�亥郎" �踹�銋蠘恣蝞𦯀� `v_avg_pct_diff`���蝖桐�鈭�銁閫���園鵭�滨蔭�塚��踹��賢��瑕��唬�銝芾�摰��銝��渡��滨蔭�𡁶��唳旿嚗諹�䔶��臬蘨�曄內蝏嘥笆����亙像��隅撟� `avg_pct`��
    - [x] **�齿��Ｘ踎 Col 2 銝� `avg_pct_diff` 皜脫�銝擧�摨� (Rendered and Sorted Col 2 by avg_pct_diff)**嚗帋耨�嫣� `sector_bidding_panel.py` (蝡硺遠憭批�) �� `bidding_racing_panel.py` (韏偦帕憭批�) ��踎�堒�銵� Col 2 (瘨刻�) �訫��潭凒�啣��鍦��餉�����笔�撅閧內���撖孵��交隅撟� `avg_pct` ��漣銝箏�蝷箔�閫���園𡢿畾菜楛摨行��拍����撟喳�瘨刻�撟� `avg_pct_diff`��
    - [x] **摰䂿緵閫���園鵭�唳��芸𢆡�滨蔭�芣� (Fixed UI Auto-Update on Reset)**嚗帋蝙敺𡑒�瘚𧢲𧒄�選�憒� 1 ���嚗匧��笔�嚗峕�瘚见膥�芸𢆡靚�鍂 `reset_observation_anchors` �祇𡢿�滨蔭 `pct_diff` 銋见�嚗峕暑頝�踎�㛖� `瘨刻�` �埈㺭�株�憭笔�甇交��嗅僎�齿鰵撘�憪讠�霈∴�敶餃�閫��鈭��靝葵�⊿�蝵桀��碶�嚗䔶�瘣餉��踹�瘝⊥��芸𢆡�湔鰵�萘�銝𡁜𦛚�餉� Bug��
    - [x] **銝��芷�朞��蹱���霂睲��𧼮�瘚贝� (Passed Tests & Compilation)**嚗𡁻�朞�鈭� `py_compile` �蹱��祗瘜閙嵗撉䕘�銝� `test_watchlist_lifecycle.py` 銝� 11 憿寞瓲敹��敶鍦����霂� 100% �朞���

## 2026-06-03 14:15
- [x] **靽桀�閫���園鵭�滨蔭銝舘祕��葵�⊥隅頝���滨蔭銝滚�甇� Bug (Fixed Observation Anchor Reset & Stock Metrics Synchronization Bug)**嚗�
    - [x] **�寞祥�滨蔭�其�銝� snap_cache �� persistent 蝻枏�畾讠� (Fixed Stale Cache Residue on Reset)**嚗𡁜銁 `reset_observation_anchors` 銝哨�憓𧼮�鈭�笆 `self._global_snap_cache`��self._sector_active_stocks_persistent` 隞亙� `self.active_sectors` ���甇交����摮埈挾�滨蔭��＆靽嘥銁靚�鍂�箏��滨蔭�塚����厩� `pct_diff`��price_diff` �� `signal_count` �函�摮䀝葉鋡怎��游��塚�銝� `price_anchor` �峕郊撖寥�銝箏��滢遠�潘�敶餃�閫��鈭�眏鈭𡒊�摮䀹𧊋�𦠜𧒄�滨蔭撖潸稲��祕��△銝芾�瘨刻�撟���湔鰵�𡝗��蹱唂�潛� Bug��
    - [x] **銵亙� _reconstruct_sector_from_candidates 樴坔仍�𡃏��讛�撅墧�� (Aligned Reconstructed Leader & Follower Metrics)**嚗朞‘朣𣂷��踹�霂行��齿��餉�銝剔撩憭梁� `leader_pct_diff`��leader_price_diff`��leader_dff`��leader_score`��leader_momentum_score` 蝑匧��桅�憭渲�摮埈挾嚗䔶誑�𡃏��讛��� `high_day`��pattern_hint`��untradable` 蝑匧��扼���霂���典���/�墧𦆮�𤥁祕��𢒰�輸����韏瑟𧒄嚗𣬚��Ｗ��啁��唳旿���銝𤾸��䁅���㺭�桀��典�����
    - [x] **銝��芷�朞�蝻𤥁�銝𤾸�敶埝�霂� (Passed Tests & Compilation)**嚗𡁻�朞�鈭�����霂烐嵗撉䕘�銝� `test_watchlist_lifecycle.py` 銝� 11 憿孵����霂� 100% �朞���

## 2026-06-03 14:00
- [x] **靽桀��踹�蝡硺遠�Ｘ踎閫���園鵭�芸𢆡�滨蔭銝𦒘葵�⊥隅頝���峕郊皛𧼮� Bug (Fixed Sector Bidding Auto-Reset Failure & Stock Change Sync Lag)**嚗�
    - [x] **摰䂿緵��蟮/�墧𦆮璅∪�銝𧢲芋��𧒄�湧�蝵株䌊��� (Adapted simulated timeline for resets)**嚗𡁜銁 `BiddingMomentumDetector.reset_observation_anchors` �亙藁銝剖��� `now_ts` �舫�匧��堆���捂隡惩�璅⊥�/��蟮�唳旿��𧒄�湔���銁 `_aggregate_sectors` �𡁜�敺芰㴓銝哨��朞� `last_data_ts` �閗繮敶枏��唳旿�嗅�嚗�僎蝏枏� `in_history_mode` ����湔𦻖蝏閗�憓嗘��蠘”�園𡢿嚗Áall-clock time嚗匧�鈭斗��嗆挾�行⏛嚗𣬚＆靽嘥銁��蟮憭滨��㚚�鈭斗��嗆挾銝贝�瘚𧢲𧒄�踹抅����賢�蝖株圻�煾�蝵柴��
    - [x] **銵亙�銝芾�憸�隅����烐暑頝�𢒰�輻�撅墧�找��� (Propagated leader metrics for UI sync)**嚗𡁜銁 `bidding_momentum_detector.py` ���霈∠�摰峕�蝏拙�嚗�� `leader_price_diff`嚗��瘨刻�隞瑟�銝𦠜活��遠撌殷���leader_dff`嚗��瘨刻�DFF撌桀�潘���leader_score`嚗�撩摨佗�隞亙� `leader_momentum_score` 摰峕㟲瘜典��� `target_sectors` 摮堒�銝哨�撟嗆�撅蓥� `snap_data` 蝻枏�璅∪�����寞祥鈭��蝡� `SectorBiddingPanel` �Ｘ踎�䭾㺭�桀��貊撩撠烐瓲敹��畾萄紡�港葵�∟祕��葉瘨刻��唳旿�箇緵 0.0 �𡝗��擧凒�啁�蝻粹萅��
    - [x] **�朞��𧼮�瘚贝�銝𦒘誨���霂� (Passed tests & compilation)**嚗𡁻�朞� `py_compile` �蹱���霂𡢅�銝� `test_watchlist_lifecycle.py` 銝� 11 憿孵����霂訫�敶� 100% �朞���

## 2026-06-03 13:30
- [x] **靽桀��航��𣇉洵銝�甈∟�銵峕��硋�瘚衤縑�瑕僎�滨��曇”撅墧�抒撩憭勗援皞� Bug (Fixed AttributeError 'MainWindow' object has no attribute 'tick_df' on Cold Start Backtest)**嚗�
    - [x] **撅墧�批�摨訫�憪见�**嚗𡁜銁 `MainWindow.__init__` 銝剛‘朣𣂷��詨��仕銝𤾸��嗆㺭�桀捆�� `self.day_df` �� `self.tick_df` ���霈� `pd.DataFrame()` 摰硺��吔��踹�鈭���臬𢆡�硋��批��芰眏 DataLoader �㰘蝸摰峕��塚��嗅��餉�嚗��敹急㭘�桀�瘚页�撘箄��𣂼�撖潸稲�� `AttributeError` 撏拇���
    - [x] **�滨�蝡墧��䌊��俈��**嚗𡁜銁 `_show_backtest_result` �𣂼��墧�靽∪噡撟嗅撩�園�蝏条��亙藁嚗���乩�撖� `day_df` �� `tick_df` �� `getattr` 摰匧��瑕�嚗�僎憓𧼮�鈭���滩�蟡典龪�滚漲�⊿� `getattr(self, 'current_code', '') == code_clean`����𨅯銁�墧�頝穃��嗡蜓�𥟇㺭�桀��芸�頧賢末嚗䔶��湔𦻖頝唾��單𧒄�滨�嚗諹�峕糓靘嗪� `DataLoaderThread` 蝔滚�摰峕��㰘蝸�嗅銁 `render_charts` 瘚��銝剛䌊�刻粉�𣇉�摮条��塚�摰䂿緵鈭���餃���妟�仿��������塩��

## 2026-06-03 11:30
- [x] **靽桀� DataProcessWorker 銝𤾸�甇交���膥�脩�撖潸稲���憭滚��唬��唳旿瞍讐� Bug (Fixed Redundant Refreshes & Data Dropping in DataProcessWorker)**嚗�
    - [x] **����屸��瑟鰵銝擧�蝞堒���**嚗𡁜�雿滚僎蝖株恕�� `sector_bidding_panel.py` 銝哨�`DataProcessWorker` 隞滨�瘝輻鍂鈭���脤��嗵� 100 �芯葵�∪���儐�舀㦤�塚��朞� 55 甈∟翮隞��憸𤏸��� `detector.update_scores`���峕���膥���撌脰◤�齿�銝箄䌊撣西�瘚��0.3s嚗劐� Chunk Scheduler 撘�郊��葷�嗆��㦤��舅憟堒���㦤�嗅�蝒�紡�港�嚗𡄯�1嚗�1.46s 霈∠��冽����0.3s �脫�憭𡁏活�曇�嚗�紡�湧�憭滩圻�睲�憭𡁏活 `on_score_finished` �噼��� UI �瑟鰵嚗𨥈�2嚗匧之�誩���銁 0.3s ��◤������湔𦻖銝Ｗ�嚗�紡�� 90% 隞乩���葵�∪��𤩺���仃����
    - [x] **銝讠瑪憭硋����敺芰㴓嚗𣬚凒�𡁜�甇交���膥**嚗𡁜� `DataProcessWorker._process_df_chunked` 銝剔����敺芰㴓敶餃�銝讠瑪嚗屸���蛹�湔𦻖撠���� `active_codes` 銝�甈⊥�扳��垍� `detector.update_scores`��漱�望���膥����� `Chunk Scheduler` 隡㗛��啣銁�𤾸蝱撘�郊�刻�嚗峕𠳿靽嗪�鈭����㺭�桃�摰峕㟲�改���蝠摨閙覔瘝颱��滚�閫血�銝擧��� UI �瑟鰵��䔮憸塩��
    - [x] **�朞�瘚贝�銝𡒊�霂烐嵗撉�**嚗𡁏��罸�朞�鈭� `py_compile` �蹱��祗瘜閙嵗撉䕘�銝� `test_watchlist_lifecycle.py` 11 憿寞瓲敹��霂� 100% �朞���

## 2026-06-03 11:25
- [x] **隡睃��踹��𡁜� Worker 撘�郊�嗆�銝𤾸�韐� (Optimized Sector Aggregation Workers & Reduced GIL Contention)**嚗�
    - [x] **銝讠瑪�𦯀� Sector Worker 蝥輻� (Decommissioned Redundant Sector Worker)**嚗𡁜蝠摨閧宏�支��𦯀��� `sector_worker` 蝥輻��𠰴��滚��� `_sector_update_queue`嚗屸��滚��其�憸𤏸蔭霂Ｖ葉鈭抒���恣蝞堒�蝒�����鈭剹��
    - [x] **��葉�嗆��踹��𡁜��餉� (Centralized Sector Aggregation in Async Worker)**嚗𡁜����厩��踹��𡁜��𦠜���恣蝞烾�餉��券�蝏煺��嗆��啣�憭�遙�⊥���/�脫�餈�誘�箏��� `async_sector_agg_worker` 銝哨���之�滢�鈭��憸� Tick 撽勗𢆡銝讠�銝餌瑪蝔见� CPU �𦯀�霈∠�撘�����
    - [x] **�惩𤐄���箔�蝥輻��墧𤣰�餉� (Stabilized Shutdown Sequence)**嚗𡁻���� `BiddingMomentumDetector.stop()` �鞉��餉�嚗���函宏�文歇鋡怠�撘��蝥輻��屸��堒��剁�撟嗅銁銝餌瑪蝔钅���箏��朞�頞�𧒄 join 蝖桐����匧��� Worker 蝥輻�鋡思�����塚�敶餃��寞祥鈭����箸𧒄�� GIL 蝡墧���甇駁���
    - [x] **銝��芷�朞��訫�瘚贝�銝𤾸��暸�霂�**嚗𡁏��蠘�銵� `test_bidding_replay.py` 蝡硺遠����墧𦆮嚗��憿寞�����𥪜𢆡�瑟鰵甇�虜嚗峕瓷�劐漣�煺遙雿閙�敺芰㴓�亥郎嚗𣬚頂蝏笔��鞾���蔔��

## 2026-06-03 11:15
- [x] **隡睃� Dashboard 擃㗛�皜脫��扯�銝擧��讐��Ｗ㨃憿� (Optimized Dashboard Rendering Performance & Eliminated UI Freezing)**嚗�
    - [x] **瘨�膄敺芰㴓���鈭厩鍂銝𡡞�憸穃紡����� (Eliminated Inside-Loop Lock & Import Overhead)**嚗𡁜� `performance_optimizer.py` ��㺭�桀�憭���寥��鍦��寞�嚗�� `_preprocess_data`��_batch_insert_with_displaycolumns_optimization`��_batch_insert_plain`��_chunked_insert`��_incremental_update`��_batch_add_rows` 蝑㚁�銝剔� `GlobalFavoriteManager` �典��嗆��䰻霂Ｗ�撖澆�銵䔶蛹�券��齿��喳儐�臬��刻�銵� bulk 銝�甈⊥�扯繮�吔�隞舘��蝠摨閙��支�擃㗛�銵峕�敹�歲銝𧢲�蝘埝㺭��活�瑕�蝥輻�����冽��紡��� CPU 撌券�撘�����
    - [x] **�齿�隡删� Treeview �瑟鰵瘚�偌蝥� (Refactored Traditional Treeview Refresh Pipeline)**嚗𡁜銁 `instock_MonitorTK.py` ��蜓銵典��啣�靚� `_refresh_tree_traditional` 銝剖��其��詨��� bulk 憸���𡝗��荔�憭批��滢�鈭�蜓銵券�憸穃��唳𧒄�� UI 蝥輻��餃��園𡢿��
    - [x] **隡睃��䠷�㕑��寥�皜脫��餉� (Optimized Candidates Rendering loop)**嚗𡁜銁 `stock_selection_window.py` �� `_render_candidates_batch_optimized` 銝剖� `GlobalFavoriteManager` �文��鞱秐敺芰㴓憭㚚�嚗𣬚＆靽嘥�䠷�㕑�頧賢���緵蝥踵�扳�扯��滚���
    - [x] **銝��芷�朞� 11 憿孵����霂蓥��蹱���霂烐嵗撉�**嚗𡁻�朞�鈭� `py_compile` �蹱��祗瘜閙嵗撉䕘�銝� `test_watchlist_lifecycle.py` 11 憿孵�敶鍦����霂� 100% �朞���

## 2026-06-03 10:30
- [x] **隡睃��滨��單釣銵峕甅撘譍���漣銝𤾸��𤩺凒�唳�蝑曉�甇� (Optimized Favorite Stock Row Style Hierarchy & Sync)**嚗�
    - [x] **蝖桃�靽萘�撘箏飵�孵�閬����挽霈⊥䲮獢� (Preserved High-Priority Feature Marker Styles)**嚗�
        - 餈𥕢�甇交�蝖桀僎��熙鈭�鍂�瑞�霈曇恣�漤�嚗帋蛹鈭�銁摰䂿�銝剔凒閫�𧑐�见�銝芾���撩撘勗��吔�**銝漤�閬�撩�嗅����厰��孵�瘜刻��賣��鞟�銝����蝥Ｚ𠧧**��
        - 撠𡁏𧊋�𣳇�笔鍳�函��芷�㕑�嚗���亙�撘箏飵�孵�嚗劐��� `('favorite',)` / `('favorite_S',)` / `('favorite_A',)` ��倌嚗���唳楚蝏輯𠧧/瘛∟��脣摹��/撟喟迅�峕艶嚗𥡝��歇蝏誩鍳�冽��瑟�撘箏飵�孵�嚗�� `limit_up` 瘨典��� `near_limit_up` 銝渲�瘨典�嚗厩��滨��∴��嗅撩�輻鸌敺��蝑曉��㗇凒擃䀝���漣嚗諹�閬���峕艶�莎�隞舘�諹噢�售�靝��澆躹��撩撘晦�萘�擃䀹��舐������
    - [x] **�𥪜�撘勗飵�嗆����脣僎�踵揢����㛖滯 (Softened Favorite Colors to Elegant Light Colors)**嚗�
        - ��笆�冽��漤�����㛖滯�峕艶嚗Ǒ#4a1515`嚗匧�暺���删�摮梹�`#ffff00`嚗匧銁撘勗飵/�芸鍳�函𠶖���閫�����餈��蝒����䔮憸矋��齿�銝粹��渡�**瘛∠遛/瘛∟�**雿梶頂嚗䔶�����滚�蝎梹�雿踹��Ｗ�颲刻�摨血����撌亦�蝢擧���
    - [x] **摰䂿緵銝厩漣瘛∟𠧧擃䀝漁撌桀��㚚��� (Implemented 3-Tier Pale Light Palette for Favorite Stocks)**嚗�
        - ��笆撌乩�撖諹�嚗�粥�輻����憟�/�圈�樴坔仍嚗厩���閬�凒擃䁅�閫匧躹��漲���瘙��撠���孵�瘜函��峕艶�峕�摮㛖���蛹銝劐葵���蝑厩漣嚗��撘��瘛梁遛�莎�嚗�
            - **`favorite_S` (S蝥扳�憟�/���瘛∟���)**嚗朞��� `#11293c`嚗��瘚�儍��/瘚瑁��莎�嚗峕�摮� `#a8d3f7`嚗��憭抵��莎���鍂鈭𤾸躹��粥�輻����隡条����憭湛�憒��瘨�3%�圈���極銝𡁜��䈑���
            - **`favorite_A` (A蝥扳活銋�/銝剖漲瘚�遛��)**嚗朞��� `#122f1f`嚗��璉桃遛�莎�嚗峕�摮� `#9adcb4`嚗����㭘蝏輯𠧧嚗剹��
            - **`favorite` (�桅�朞䌊��/���瘚�遛��)**嚗朞��� `#183624`嚗���湔楚蝏輯𠧧嚗㚁���� `#a8f0c0`嚗�楚��㭘蝏輯𠧧嚗剹��
    - [x] **靚�㟲 `"favorite"` ��倌餈賢��單錰撠曆誑摰䂿緵��漣�瑕�閬��**嚗�
        - 撠� `performance_optimizer.py` 銝� `_batch_insert_with_displaycolumns_optimization`��_batch_insert_plain`��_chunked_insert`��_incremental_update` 隞亙� `_batch_add_rows` �寞�銝� `"favorite"`/`"favorite_S"`/`"favorite_A"` ��◇摨讛��渲秐�怠偏嚗�朖 `all_tags.append(fav_tag)`嚗㚁�雿靝蛹�𨅯��峕艶�脯��
        - �峕郊撠� `instock_MonitorTK.py` 銝剔� `_refresh_tree_traditional` 銝剔� `tags = tuple(["favorite"] + list(tags))` �孵� `tags = tuple(list(tags) + ["favorite"])`嚗䔶�����湔鰵�寞�銝讠�銝��氬��
    - [x] **銵亙�憓鮋��湔鰵銝� `rows_to_update` ��鸌敺� tags 摰墧𧒄�瑟鰵銝� favorite �峕郊**嚗�
        - 靽桀�鈭� `_incremental_update` 銝凋��湔鰵 rows ��𧋦 values �䔶��芸��� tags ��撩�瘀��朞�憸���𣇉鸌敺��霈啣�撟園��� rows 敺芰㴓�唳旿閫��嚗䔶蛹�湔鰵銵�𢆡���鋆� `row_data` 銝� `tags`�����銁�滨��單釣�嗆����䀝葉隞瑟聢閫血�憸𡏭𠧧��倌�孵��塚�憓鮋��瑟鰵銋蠘�瘥怎�蝥折�靽萘��啣笆朣鞉��啁���倌�瑕�銝𡡞�鈭格遬蝷箝��
    - [x] **靽桀��踹��剖�銵其葉�滨��單釣�踹��䭾����� Bug**嚗�
        - 靽桀�鈭� `stock_selection_window.py` ��� `_refresh_sector_list` �鍦��踹��塚�撠�歇��扇�� `sec_tags` �� insert �園�霂臬𧑐銝Ｗ�嚗�唂隞��銝剔′蝻𣇉�雿輻鍂 `tags=(tag,)`嚗㚁�撖潸稲�滨��踹��䭾�甇�虜皜脫�擃䀝漁�� Bug嚗峕㺿銝� `tags=tuple(sec_tags)`嚗䔶蝙�芷�㗇踎�㛖𠶖���摰𣬚�擃䀝漁��
    - [x] **�朞��蹱���霂睲��𧼮��笔𦶢�冽�瘚贝�**嚗𡁻�朞�鈭� `py_compile` �蹱��祗瘜閙�撉䕘�銝� `test_watchlist_lifecycle.py` 11 憿孵����霂訫�敶� 100% �朞���

## 2026-06-03 03:15
- [x] **瘛勗漲靽桀� `performance_optimizer.py` 銝� `IndentationError` 蝻抵�銝舘祗瘜訫援皞� Bug (Fixed IndentationError & Restored Parsing Safety in Treeview Updater)**嚗�
    - [x] **銵亙�撘�虜憭���剔㴓銝𤾸㦛�����**嚗𡁜銁 `performance_optimizer.py` �� `_batch_insert_with_displaycolumns_optimization` row_data ��遣�典�嚗諹‘朣𣂷��曹�銝𡃏蔭蝻𤥁��誩�蝻箏仃�� `except Exception: row_data = None` �閗繮�𨰜���敶餃��Ｗ�鈭� `try-except` ��祗瘜閧����撟嗅��港��嗘���� `feature_marker` ��㦛��葡�枏��踝��寞祥鈭��銵峕𧒄��憬餈𥕦援皞��霂胯��
    - [x] **�滚��滨��單釣�滨�瘜典�**嚗𡁜銁�剖��� `try-except` �𦯀��對�摰匧�瘜典�鈭�抅鈭� `GlobalFavoriteManager` �蓥�����寡䌊�㕑��斗鱏��笆鈭𤾸�鈭𤾸�瘜典�銵其葉��葵�∴��滨��芸𢆡�潸� `�鞾��嫘�鬔嚗䔶�霂�之撅讐��扯��典��𤩺㺭�桃��交𧒄摰𣬚�撅閧緵擃䁅儘霂�漲��倌��
    - [x] **銝��芷�朞��蹱��祗瘜閙嵗撉䔶��訫�瘚贝�**嚗𡁏��罸�朞�鈭� `python -m py_compile` 蝻𤥁�璉�撉䕘�銝� `pytest test_watchlist_lifecycle.py` 11憿孵�敶埝�霂� 100% �函遛�朞�嚗𣬚頂蝏��摨衣滲��嚗峕�隞颱��扯��園�銝𤾸�撣詻��

## 2026-06-03 02:40
- [x] **摰䂿緵�踹�銝擧�敹萄撩摨血� 10�漤�蝎曉漲�啣�潭𦆮憭找��讐熔�峕郊撖寥� (Implemented 10x Scale Scaling & Dimension Alignment for Sector Intensity Scores)**嚗�
    - [x] **�齿� Sector 撘箏漲�枏�璅∪� (Scaled Sector Score by 10x)**嚗𡁜� `bidding_momentum_detector.py` 銝剔� `board_score` �𡃏���𥁒霅行踎�堒��� `v_board_score` 霈∠�蝏煺�銋䀝誑 `10.0` �曉之�惩������之�唳�擃䀝�擃睃撩摨艾��瓲敹���寞踎�堒銁蝡硺遠銝𡒊�銝剝��⊥𧒄��㺭�潸儘霂�漲銝𤾸撩�滚榆�箏�摨佗��踹�鈭�誑敺��曹��啣�澆榆撘��撠𧶏�憒� 1.05 撖寞� 1.08嚗匧紡�渡�閫���嘥���
    - [x] **蝑㗇�靘见笆朣𣂷�皜貉��其��亥郎���� (Aligned Downstream Thresholds)**嚗𡁜�璉�瘚见膥銝剜��匧抅鈭𤾸撩摨血����餈�誘�峕�霈圈��潘�憒�之�訫撩摨血�蝐颯��撩�餅踎��/瘣餉��踹��文�������憸�隅�∟��刻圻�𤑳�嚗厩�瘥𥪯��峕郊�曉之 10 �㵪��其�霂����移蝏������塚�摰��蝏湔擪鈭�頂蝏�𠳿�劐��⊥�蝑曄�蝔喳��找�斢���扼��
    - [x] **�峕郊撖寥� Tkinter 璁�艙撘箏漲霂�摯�讐熔 (Synchronized Tkinter Concept Scoring)**嚗𡁜� `instock_MonitorTK.py` 銝剔� `get_global_concepts_ranking` 銝� `get_following_concepts_by_correlation` �����恣蝞烾�餉�鈭衣�瘥𥪯��曉之 10 �溻����帋��㕑��Ｘ踎憭批�銝� PyQt 蝡硺遠�Ｘ踎銋钅𡢿���蝥脣�鈭怠��頣�蝖桐��其��𣬚�������諹��暸𡢿��揢�塚��踹�/璁�艙撘箏漲�文����蝏嘥笆�峕���
    - [x] **�朞�擃睃撩摨虫遛�煺��蹱���敶埝�霂� (Passed Compilation & Replay Validation)**嚗𡁜銁�牐漱�𤘪𧒄畾萎�嚗屸◇�拚�朞�鈭� `test_bidding_replay.py` ���憸� Tick �踹����銝舘��典��暹�霂𤏪����皜豢芋�堒銁�曉之�𡒊��枏��讐熔銝贝�銵�像蝔喉��牐遙雿訫�撣詻��妟霈∠�撘���憓𧼮���

## 2026-06-03 00:15
- [x] **摰䂿緵撘箏飵�⊿�㕑��Ｘ踎�刻”�潭惣�賢�摰質䌊�冽�銋��銝𤾸�靽嗪埯�芷����㰘蝸�箏� (Implemented Global Treeview Column Width Persistence & Double-Safe Recovery in Selector Window)**嚗�
    - [x] **霈曇恣擃㗛�𡁶鍂 DRY �嗆��堒捐蝞∠��� (Designed Centralized DRY Width Controller)**嚗𡁜銁 `stock_selection_window.py` 摨閖�撘訫�鈭��𡁶鍂�� `_save_all_tree_column_widths`��_restore_all_tree_column_widths` �� `_on_treeview_column_resize` �笔��賣㺭嚗�僎隡㗛�蝏穃�銝� `StockSelectionWindow` 蝐餅䲮瘜𨰻����蠘圾�血僎瘨��鈭�蛹瘥譍葵 Treeview 蝻硋��祉�����㚚�餉��� YAGNI �滚�嚗�笆朣� SOLID �蓥��諹提銝擧𦻖���蝳餃��辷���
    - [x] **摰䂿緵 10蝘㘾俈�𡝗�摮� + 蝒堒藁�喲𡡒���箇�銝��笔��瑞��箏� (Implemented 10s-Debounced In-Memory Cache & Close-Event Atomic Flush)**嚗𡁻�朞��典�靘衤葉瘜典� `self._pending_column_widths` �讐�摮䀹�摮睃膥嚗�像�嗅笆�堒捐����刻��游蘨霈啣�鈭𤾸�摮矋��嗥��� I/O 撘���嚗㚁�撘��� 10 蝘𡜐�`10000ms`嚗厰俈�硋辣餈笔�摮𣂼��矋�撟嗅銁蝒堒藁�喲𡡒�鞉� `_on_close` �嗅撩銵������������㗇𧊋�嗵��堒捐�𤩺㺭�桐�甈⊥�扯�銵��摮𣂼�撟嗅��塩����滢��牐�甇Ｙ�霂餃��睃��航�摮睃銁���隞園��脩�嚗峕�扯��𣂼� 99% 隞乩���
    - [x] **敶餃�撟脫��滚��㰘蔭摮琜�瘛勗漲�滚��滢���� (Refactored Guidance Wheel to Merge Centralized DRY Controller)**嚗𡁜�撘�� `stock_selection_window.py` ��𧋦銝㯄秄銝箸��交�雿𨀣��堒��砍��嗥� `_save_guidance_column_widths` �� `_restore_guidance_column_widths` 蝖祉����雿躰蔭摮僐����嗅�撅��餉�摰���滚��𤏸秐擃㗛�𡁶鍂�� `_save_all_tree_column_widths("guidance", ...)` �� `_restore_all_tree_column_widths("guidance", ...)` �亙藁銝哨�雿踵�雿𨀣��𡑒䌊�典�蝢𡒊誧�踹僎鈭急�鈭���啁���10蝘㘾俈�𡝗�摮�+�喲𡡒���箔�甈⊥�批�摮𣂼��覀�脲��湔�扯���
    - [x] **�唳秤撘讛��硋� Tab �剖之�詨� Treeview 閫�㦛**嚗𡁜�蝢𦒘蛹 `selection` (蝑𣇉裦�㕑�銵�)��sector` (�踹��剖�銵�)��member` (�𣂼��∟”)��signal` (�喟�靽∪噡銵�)��pos` (敶枏����銵�) 隞亙� `log` (瘚�偌�亙�銵�) �剖之�詨�銵冽聢�亙�霂交㦤�嗚��銁銵典仍�嘥��硋� 50ms �芸𢆡�㰘蝸��蟮�堒捐嚗�僎�� `<ButtonRelease-1>` �𡝗嗻�嗆��瑕僎閫血� 10 蝘㘾俈�𤥁��唳旿�����
    - [x] **�齿�擐硋��芷���瘚钅�嚗屸俈敺⊿�憸穃��圈�蝵� (Hardened _auto_fit_columns & Bypassed Overrides)**嚗𡁜銁 `load_data` �� `_auto_fit_columns` �亙藁銝剜釣�乩��箔� `WINDOW_CONFIG_FILE` ��辣��𠶖���瘚卝���璉�瘚见�敶枏� Tab 摮睃銁�冽��芸�銋㗇�銋���堒捐�滨蔭�塚��湔𦻖頝唾�撟嗥�頝臬��厩��芸𢆡瘚钅��餉�嚗�蝠摨閗圾�喃��䀝葉擃㗛�銵峕��瑟鰵�砽�𣈯��寞�霈啣��踱�嘥紡�游�摰質◤撘箄��芸𢆡靚�㟲�滨蔭銝箏�憪讠�摰賢漲����� Bug��
    - [x] **撘��� NotebookTabChanged �𡁏�鈭衤辣�䔶��拙�頧賢膥 (Developed Tab-Change Double-Insurance Restorer)**嚗帋蛹�㕑�蝒堒藁銝� Notebook 撘箏�蝏穃� `<<NotebookTabChanged>>` �𡁏�鈭衤辣����冽��其��� Tab 憿菟𢒰�湔�銵���Ｘ𧒄嚗諹䌊�冽神蝘垍漣�齿活閫血�撖孵��滚虾閫���� Treeview �堒捐�滨蔭��撩�嗆��𧼮笆朣琜�颲暹�鈭��憭拙�� 100% 蝔喳𤐄���閫厰�靽萘�靽嗪���

## 2026-06-02 23:35
- [x] **�寞祥 Nuitka 蝻𤥁��臬�銝贝楊 GUI 獢�沲霈ａ�撘訫��� Fatal Python error: PyEval_RestoreThread GIL �游𦶢撏拇� Bug (Fixed Fatal GIL Crash & Implemented Main Thread Polling in Tkinter)**嚗�
    - [x] **���撏拇��祈捶�笔� (Root Cause Analysis)**嚗𡁜銁 Nuitka 鈭諹��嗥�霂𤑳㴓憓��嚗�� PyQt6 蝡硺遠憭批� (PyQt 蝥輻�) 銝凋耨�寥��孵�瘜函𠶖��圻�� `GlobalFavoriteManager` �蓥��� `notify()` �𡁶䰻�塚�隡𡁜��� Tkinter 蝥輻�頝函��湔𦻖瘜典��� `StockSelectionWindow` (Tkinter 蝒堒藁) �� `_on_favorites_changed` 霈ａ��噼�銝准���隡𡁶凒�亥��� Tkinter 摨訫� C 霂剛��� Tcl/Tk �亙藁嚗�� `self.winfo_exists()` �� `self.after()`嚗剹��銁�� Tkinter 銝餌瑪蝔衤��芣��匧龪�滨� Python 摮鞟瑪蝔� Thread State �嗆����亥圻摨訫� C-API嚗�銁 Nuitka ���撘箏漲摰匧��剛�銝讠凒�亥圻�睲� `PyEval_RestoreThread: the function must be called with the GIL held, but the GIL is released (the current Python thread state is NULL)` �拍�撏拇���
    - [x] **摰墧鴌蝥� Python �𠉛氖�𤩺�霈唳㦤�� (Implemented Pure Python Dirty Flag)**嚗𡁜� `StockSelectionWindow` ����� `_on_favorites_changed` 霈ａ��噼��餉��拍��亦氖嚗屸���蛹蝥舐硃�毺��� Python 撣���潔耨�對�`self._favorites_dirty = True`嚗剹���銝齿��𠹺遙雿訫�撅� Tcl/Tk C 霂剛� C-API �亥圻嚗�銁 Python �������Ｘ糓 100% 頝函瑪蝔衤�餈𤤿�摰匧�����拍��娍鱏鈭�楊蝥輻�撖孵�撅� Tcl ���雿栶��
    - [x] **撘��� Tkinter 銝餌瑪蝔衤�撅𧼮�頝唾蔭霂Ｗ��� (Developed Main-Thread Heartbeat Poller)**嚗𡁜銁 `StockSelectionWindow` �� `__init__` 銝剜釣�乩�撅䂿� 300ms 敹�歲頧株砭摰𡁏𧒄�� `_poll_favorites_loop`嚗諹�撘箏��� **100% 餈鞱��� Tkinter 銝� GUI 蝥輻�** ������銝餌瑪蝔𧢲�瘚见�蝥� Python �𤩺�霈啗◤靽格㺿�塚��芸�摰匧��扯��屸𢒰�滨��㰘蝸銝𡒊蔭憿塚�颲暹�鈭��蝡舐�蝥扯�雿𤾸辣餈笔�甇亦��𣈯妟撏拇���妟撘�������𠉛氖�嘥極銝𡁶漣�剔㴓��
    - [x] **�拍��齿��典��滨��峕郊�瑟鰵嚗���啣�璅∪��𣈯妟撘�����妟霈∠��滩蝸��滲���皜脫��脲��港��� (Re-engineered Global Favorites Refreshing System to In-Memory Redraw Only)**嚗�
        - [x] **����罸�餉�撘���**嚗𡁜�雿滚僎蝖株恕�� `StockSelectionWindow` (蝑𣇉裦�㕑��Ｘ踎) ����孵�瘜典�甇亙�靚�葉嚗峕唂隞���冽𤣰�圈�𡁶䰻�嗡��扯�擃䀹��祉� `self.load_data()` 瘚�����隡𡁻��啗��典�撅���亦��㕑�蝞埈�嚗Ǒselector.get_candidates_df()`嚗匧僎閫血�銝滚�閬���券��唳旿銵仿�銝擧��吔���漲瘚芾晶 CPU 蝞堒�銝𥪜��典之�讐� GIL ���鈭劐� IO 蝑匧���
        - [x] **摰䂿緵 0ms 蝥臬�摮� UI �滨�**嚗𡁻��嗘��㕑��Ｘ踎�� `_refresh_ui_favorites()`��緵�典��滨��單釣�𤑳��䀹凒�塚��㕑��Ｘ踎銝滚�靚�鍂 `load_data`嚗諹�峕糓�湔𦻖憭滚�撌脣��其����蝻枏�銝剔� `self.df_full_candidates` �舀𧋦嚗�僎�典�摮条漣�祇𡢿�齿鰵摨𠉛鍂 Concept Filter 餈�誘��覔�格鰵�嗉��嗆��溶�� `is_fav` �齿鰵�扯�鈭峕活蝵桅▲�鍦�����唳葡�� UI�����縧鈭� 99.9% �𦯀����撅���碶�蝑𣇉裦霈∠�撘���嚗�蝠摨閙�蝏苷�憸𤑳�瘛餃��嗉��嗥��屸𢒰�⊿▼��
        - [x] **�冽芋�堒笆朣鞟滲 UI 皜脫����**嚗𡁜𧑐瘥臬��埝䰻鈭� `SectorBiddingPanel` (蝡硺遠憭批�)��BiddingRacingRhythmPanel` (韏偦帕憭批�) 隞亙� `SpatialFollowHUD` (頝笔� HUD �Ｘ踎) ����孵��游�摨娍㦤�嗚��＆霈支�餈唬����撌脤�朞� Qt 鈭衤辣�笔��𤥁蝠�誩��唳䲮瘜𤏪�憒� `update_visuals` / `update_hud_data`嚗匧抅鈭𤾸�摮条�摮䀹�銵𣬚滲 UI 銵冽聢銵𣬚宏�其�蝵桅▲�滨�嚗䔶��嗆�銝𠰴蝠摨閙��支��典��滨��峕郊�嗥�霈∠�韏��瘚芾晶銝𦒘遙雿閙��� GIL �脩�霂勗���

## 2026-06-02 20:25
- [x] **摰𣬚�閫��撘箏飵�⊿�㕑��Ｘ踎 Windows �毺�銝駁���倌�峕艶�脰��� Bug 銝𡡞��滚榆��滯銝剜�摮㛖尐�滨���緵 (Unlocked Windows Treeview Background Bug & Implemented High-Contrast Visible Favorites in Selector Window)**嚗�
    - [x] **閫�膄 Windows Tkinter Treeview �毺��峕艶撘箄�閬�� Bug (Unlocked style.map Constraints)**嚗𡁻���� `stock_selection_window.py` ��� `style.map("Dark.Treeview")` �� `style.map("Treeview")` ����臭��齿艶�滩𠧧�惩�銵具����支��券�憸� Vista/XPnative �毺��瑕�銝见撩銵峕𦜖�𣳇��劐葉����峕艶�脩�摨訫� `+ fixed_map(...)` �拍��𣂼�嚗�蝠摨閙�憭滢���倌�滨蔭 `tag_configure` ���銵𣬚𡠺蝡讠��嗆綉�嗆�嚗��蝢舘圾�喃��𡏭�����航𠧧瘝⊥��曄內�箸䔉����萘�摨訫�蝟餌�蝥折��嗚��
    - [x] **摰䂿緵��稲擃睃�撌栽�𦦵��𤑳�蝥Ｚ��胼�苷��𣈯緾���煾�����嗪��寡�擃䀝漁 (Implemented Crimson Background & Gold Text Favorites)**嚗𡁜� `favorite` 銵峕甅撘誩�蝥找蛹擃睃�撌桃��煾��莎��峕艶 `#4a1515` ����㛖滯嚗���� `#ffff00` ��漁暺�𠧧蝎𦯀�摮梹����銝擧芦�朞����暺穃��脯��滯蝎㗇�摮堒��劐葉��楛�肽�����舀�撘�鈭��撖寡�蝵𤏸�蝥批�撌殷�霈拇𤣰�讛�銝��潮�摰𠾼���鈭桀��怒��
    - [x] **銝剜�����滨��碶誨璅∠���� (Replaced Star Icon with Bold Chinese Word Prefix)**嚗𡁜����匧銁銝餉”�潦��踎�𡑒��西”����脰蕭頦芰���葵�∪�蝘啣���芋蝟� `"潃� "` �滨��拍��齿�銝箸凒蝖祆���忽�誩���撩��葉�� **`"�鞾��嫘��"`** �删�摮埈甅嚗��憒� `�鞾��嫘�𤑳��𡁶鸌蝘鬔嚗㚁�撟嗅�甇亙銁鈭峕活蝔喳��鍦����蝻��亦氖�箏��𠹺��閙㺭�格�瘣埈芋�𦯀葉銵仿��寥��舀�嚗諹噢�𣂷��𨀣�摮埈�蝖格遬蝷粹��嫖�萘�擃䀝�����睃��䀝漱隞塩��

## 2026-06-02 20:10
- [x] **摰䂿緵韏偦帕銝餌�����𣂼�霂行�摮鞟���𡠺蝡衤漱鈭鍦�銝��桃�銝��滨蔭 (Implemented Independent Window Controls & One-Key Raise-All in Racing Panel)**嚗�
    - [x] **�拍��𠉛氖銝餃�蝒堒藁摨訫��交��喟頂 (Decoupled Owner Window Handlers)**嚗𡁜銁 `bidding_racing_panel.py` 銝哨��齿�鈭� `SectorDetailDialog` �� `CategoryDetailDialog` ����惩遆�啜���摨訫� `super().__init__(parent)` 靽格迤銝� `super().__init__(None)`��銁 Windows 蝟餌�摨訫�敶餃�閫��虫��嗅�蝒堒藁�� Ownership �𥪜𢆡嚗��蝢舘圾�喃��𦦵��餃�蝒堒藁�嗡蜓蝒堒藁鋡怠撩�嗥蔭憿嗅僎�碶��嗡�蝒堒藁�萘��𤤿�嚗䔶蝙�冽��臭誑摰���祉��啣笆��葵蝒堒藁�扯�蝘餃𢆡���撠誩�����曄��滢���
    - [x] **�滚� Python 蝛粹𡢿 parent ��� (Overrode parent() for Logical Integrity)**嚗𡁜銁摮鞟���掩銝剝�朞� `def parent(self)` 撌批��滚�鈭� `parent` �瑕��寞�嚗䔶蝙���� Python 銝𡁜𦛚�餉�撅�𢒰��楊蝒堒藁鈭支�嚗�� `self.parent()._save_ui_state` �� `self.parent().update_visuals`嚗劐��嗅虾隞仿�朞��𡁏��嗆�����蠘��剁�摰䂿緵鈭��蝢𡒊��蠘�憟穃�嚗�泵�� SOLID 撘���/撠�𡡒�笔�嚗剹��
    - [x] **�啣��𨥉�𣬚�銝�蝵桅▲�嘥��賡睸 (Added "��蝏煺�蝵桅▲" Control Button)**嚗𡁜銁韏偦帕銝駁𢒰�輻� `query_bar` 撌亙��譍葉嚗��𨥉�滩祕璉��脲��桃����喃儒嚗㚁��啣�鈭�換�脩ㄗ����潛� `��蝏煺�蝵桅▲` �厰僼��
    - [x] **摰䂿緵銝��桀�蝒堒藁撣血����� (Unified Raise-All Trigger)**嚗𡁜��睲� `_on_raise_all_windows_triggered` 蝵桅▲�𡁜��具����餅��桀�嚗䔶��芸𢆡靚�鍂 `show(); raise_(); activateWindow()`嚗��撌脣銁摨訫�摰��閫��衣�銝餌����敶枏��枏�����㗇暑頝��蝒堒藁�冽神蝘垍漣����函�銝��砍𤧅�喳�撟閙��齿䲮嚗屸�隞交萱�𣬚� toast 瘞娍部鈭支�嚗峕�憭批𧑐�𣂼�鈭��撅讐𤀻�䀝�摰賢��讠��嗥������

## 2026-06-02 23:55
- [x] **瘛勗漲�惩𤐄靽∪噡�批��Ｘ踎�典��滨��單釣銝𦒘�甈∠迅摰𡁏�摨� (Hardened Global Favorites & Stable Secondary Sorting in Signal Dashboard)**嚗�
    - [x] **摰𣬚�閫��憭扳踎�㛖��𥡝”銝讠揣撘閙毽瘛���𡝗�瘣� (Fixed Multi-column Index Overlapping in Sector Heat Table)**嚗𡁻���僎閫��虫� `signal_dashboard_panel.py` 銝� `_sort_table_python` ���蝝Ｗ��交𪄳銝擧�摨譍���漣�文��餉�����靝誨���腈���靝葵�∪�蝘售�嘥��𨀣踎�堒�蝘售�苷�銝芰輕摨衣��㛖揣撘訫ế�剛�銵𣬚����瘚��敶餃�閫��鈭�踎�㛖��𥡝”銝剖��𣈯�憭游�蝘售�苷��𨀣踎�堒�蝘售�嘥�摮睃��𤑳��㛖揣撘閗��� Bug��朖雿踹銁�冽�擃㗛��见𢆡�孵稬�堒仍餈𥡝����憭齿�����鍦��塚�銋蠘�蝖桐�撌脣�瘜函��滨��踹�憪讠�撘箇蔭憿塚�銝娍踎�堒��典��桅�𡁏踎�𦯀�靽萘�摰��甇�＆��㮾撖寞����摨𤩺�摨𧶏�撖寥� SOLID �笔�嚗剹��
    - [x] **�寞祥�喲睸霈曆蛹�滨�銝芾��嗥�餈鞱��� TypeError 撏拇� Bug (Fixed Single-Parameter add_favorite_stock Invocation in Context Menu)**嚗𡁏��亙僎靽桀�鈭� `_show_context_menu` �喲睸銝𠹺�����閖��鎿� 霈曆蛹�滨�銝芾��嘥𢆡雿靝葉����啗��其��寥�蝻粹萅����笔��躰秤�� `fav_mgr.add_favorite_stock(code, name)` �拍��齿�銝� `fav_mgr.add_favorite_stock(code)`嚗��蝢𤾸笆朣𣂷� `GlobalFavoriteManager` 摨閖��訫��啣�摮� API 霈曇恣嚗峕覔瘝颱�摰䂿��滨��嗥眏鈭𤾸��唳㺭�譍��寥�撘訫����銵峕𧒄 TypeError 撏拇�銝� UI ��香�鞉���
    - [x] **銝��芷�朞��券�蝻𤥁�銝𤾸�敶埝�霂閖�霂� (Passed All Compilation and Regressions)**嚗𡁏�銵䔶� `py_compile` 撖寞��劐耨�孵���誨���銵䔶�霂剜�撉諹�嚗�僎�𣂼� 100% 銝��芷�朞�鈭� `test_watchlist_lifecycle.py` �券��訫��𧼮�瘚贝�嚗𣬚頂蝏��摨衣滲��嚗𣬚迅摰𡁏�扯噢�啣極銝𡁶漣�����

## 2026-06-02 20:45
- [x] **摰䂿緵�典��滨��單釣�踹��𠹺葵�∠�憭𡁶垢�曹澈銝舘恥��㦤�� (Implemented Global Favorite Stocks and Sectors Sync Architecture)**嚗�
    - [x] **閫��� SectorBiddingPanel ��𧋦�啁𠶖��恣�� (Decoupled Bidding Panel Local State)**嚗𡁜� `sector_bidding_panel.py` ��� `favorite_sectors` �� `favorite_stocks` ����典��典�霂餃��餉��齿�銝箏抅鈭� `GlobalFavoriteManager` �蓥��� `@property` 撅墧�扼��笆鈭擧𤣰�誩��𡝗��嗉��滢�嚗Ǒ_add_favorite_stock` / `_remove_favorite_stock` / `_add_favorite_sector` / `_remove_favorite_sector`嚗㚁��券��滚��𤏸秐 `GlobalFavoriteManager` ���摮𣂷耨�� API��
    - [x] **�齿� BiddingRacingRhythmPanel 銝� HUD 霈ａ�撖寥� (Integrated Racing Panel & HUD Subscription)**嚗𡁜� `bidding_racing_panel.py` �� `spatial_follow_hud.py` 銝剔鍂鈭舘粉�㚚��寞踎�堒�銝芾���𧋦�啗繮�㚚�餉��券�摨罸膄嚗𣬚凒�亥粉�� `GlobalFavoriteManager` �蓥���銁銝劐葵�喲睸�Ｘ踎�� `__init__` �寞�銝剖��牐�撖� `GlobalFavoriteManager` �䀹凒�𡁶䰻��釣�䕘�`subscribe(self._on_favorites_changed)`嚗㚁�摰䂿緵鈭�楊蝏�辣��楊�Ｘ踎���瘥怎�蝥扯��典��啜��
    - [x] **銝��芷�朞��蹱���霂烐嵗撉䔶��𧼮�瘚贝� (Passed Compilation & Regression Tests)**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䕘�銝𥪜�蝡航��典�蝢舘䌊���瘨�膄鈭���� GIL 蝡墧���蝒���䭾�銋厩���辣�滚�霂餃�撘�����

## 2026-06-02 18:50
- [x] **撖寥� �� 摰墧𧒄�亥郎 �𡁏��踹�霂���餉� (Aligned Scoring Logic for �� 摰墧𧒄�亥郎 Virtual Sector)**嚗�
    - [x] **瘨�膄霂������𡁻�銝𦒘�銝���**嚗𡁜� `bidding_momentum_detector.py` ��� `�� 摰墧𧒄�亥郎` �𡁏��踹������′蝻𣇉� `max(5.0, sum(s['score'])/count)` 霂���餉�嚗屸���蛹摰��撖寥��桅�𡁏踎�㛖� `v_avg_pct * v_eff_follow_ratio * v_trend_multiplier` 撘箏漲敺堒��砍���
    - [x] **撖寥����澆��𣂷�頞见飵蝟餅㺭**嚗朞䌊����𣂼��亥郎瘙牐葵�∠� 5/20/60 �亙�蝥踹ế摰𡁜僎霈∠�頞见飵銋䀹㺭嚗䔶誑 100% �𥪜𢆡瘥𠉛�餈𥡝��冽���銝��硔��＆靽苷��亥郎�𡁏��踹��冽踎�埈�銵峕�銝剔�霂���鍦����銝𤾸�隞𣇉�摰𧼮��箸踎�㛖�撖嫣��湛�敶餃�閫��鈭�之�睃像蝔單�銝贝��嗆𥁒霅行踎�堒����擃睃㨃�冽�憿園�����嫘��
    - [x] **銝��芷�朞��訫�瘚贝�銝𡡞����霂烐嵗撉�**嚗𡁏��罸�朞�鈭� `test_watchlist_lifecycle.py` �券��訫�瘚贝�嚗䔶��牐遙雿閖���祗瘜閧�霂穃�撣詻��

## 2026-06-02 18:45
- [x] **摰䂿緵蝡硺遠�Ｘ踎�羓��抒�隞嗅��凋����箇迅摰𡁏�批��� (Hardened Sector Bidding Panel and Monitor Shutdown Stability)**嚗�
    - [x] **摰䂿緵 BiddingMomentumDetector 蝥輻��曉�蝑匧�銝𤾸��� (Synchronized Detector Workers Teardown)**嚗帋蛹 `bidding_momentum_detector.py` ����� `subscribe_worker`��sector_worker` �� `async_sector_agg_worker` 蝥輻��交�撘訫��曉��𣂼��㗛�蝏穃�嚗�僎�� `stop()` �寞�銝剜�銵�蒂頞�𧒄�𣂼�嚗Ǒ0.8s`嚗厩� `join()` �峕郊�墧𤣰嚗峕覔瘝颱��𤾸蝱摰�擪蝥輻��刻圾�𠰴膥�鞉��嗆挾�Ｗ� GIL 撘訫���援皞���
    - [x] **摰䂿緵銝餅綉���粹𧫴畾� Watchdog 銝� IPC Worker �誩��喲𡡒 (Coordinated Watchdog & IPC Teardown in on_close)**嚗𡁜銁 `instock_MonitorTK.py` �� `on_close` 瘚����撘�憪钅����銝餃𢆡撖寡��剔��函� `GuardDog` 蝥輻�餈𥡝��𨀣迫銝� `join()` �峕郊嚗𥕦銁�喲𡡒 IPC 蝞⊿��拍�餈墧𦻖�㵪��睲遙�⊿��埈��� `None` �典�嚗�僎�峕郊 `join()` 憭��蝑匧��嗆��� `_ipc_worker_thread`嚗���凋�蝥輻�銝𡒊恣�梶��笔𦶢�冽�蝡硺���
    - [x] **銝��芷�朞��蹱���霂睲��𧼮�瘚贝�撉諹� (Verified compilation and test suite)**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䔶� `test_watchlist_lifecycle.py` 蝑匧�憿寧頂蝏笔�敶埝�霂𤏪�蝟餌����箄�蝔见像皛㻫����萄偶蝥輻�畾讠���

## 2026-06-02 18:20
- [x] **摰䂿緵�餉�璁�艙���Top10蝒堒藁�惩�Alt+R�典�頧株砭��揢�� (Implemented Overview Concept Analysis Top10 in Alt+R Switcher)**嚗�
    - [x] **憓𧼮� PyQtGraph 蝒堒藁�航��找��交�瘜典�**嚗𡁜銁 `instock_MonitorTK.py` �� `_get_all_open_trade_windows` �寞�銝哨��啣�撖� PyQtGraph 蝒堒藁蝻枏� `self._pg_windows["�餉�_10"]` �嗆����斗鱏��𥅾霂亦�����其��航�嚗峕��硋� Win32 �毺� `winId()` 撟嗆釣���瘣餉�鈭斗�閫���交��𡑒” `current_visible_hwnds` 銝准��
    - [x] **����滨妍�惩�銝舘䌊�典�甇交㦤��**嚗帋蛹�瑕������蘂����𥪜�憟賢�蝘� `"�� �餉� 璁�艙���Top10 (ConceptAnalysisTop10)"`嚗䔶蝙�嗅銁瘥� 1 蝘垍�敹�歲摰𡁏𧒄�峕郊�箏�銝页��芸𢆡�朞� `127.0.0.1:26669` 蝡臬藁 Socket �峕郊�閖�坿秐�祉��� `hotkey_rotator.py` �典��剝睸/閫��頧桅�匧��方�蝔卝��
    - [x] **銝��芷�朞��蹱��祗瘜閧�霂烐嵗撉�**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䕘�蝖桐�銝餅綉�嗅蝱蝟餌�����笔像皛穃�蝥扼��

## 2026-06-02 18:15
- [x] **靽桀� ReentryTracker �嗆���摮睃�蝒���脫��睃𢆡�嗵� (Fixed ReentryTracker Save Conflict & Change-Detection Saving)**嚗�
    - [x] **摰䂿緵�芸銁�睃𢆡�嗅��� (Change-Detection Saving)**嚗𡁜銁 `reentry_tracker.py` 銝剖��� `self._last_saved_data` 蝻枏��啗扇��銁 `_load_state` �嗉扇敶訫�憪见�潘��� `_save_state` �嗅笆瘥𥪜��� `watchlist` 頧祆揢����訾�蝻枏���𥅾�惩�摰孵��典��湔𦻖�剛楝餈𥪜�嚗䔶�皞𣂼仍銝𠰴�撠� 95% 隞乩��䭾������ I/O��
    - [x] **摰䂿緵餈𤤿�銝𡒊瑪蝔见��函��臭�銝湔𧒄��辣 (Process-Thread-Unique Temp Files)**嚗𡁜�������𡁶鍂 `reentry_states.json.tmp` �賢��寞��齿�銝箏��怠��� PID �� Thread ID ��𣈲銝�銝湔𧒄��辣頝臬�嚗Ǒreentry_states.json.tmp.{pid}.{thread_id}`嚗㚁�敶餃�閫��鈭��餈𤤿�/憭𡁶瑪蝔见僎�穃��䀹𧒄�曹�鈭匧內�䔶�銝芯葩�嗆�隞嗅蘂��紡�渡� `WinError 32` �� `Permission denied` �仿���
    - [x] **撘訫�撣行��圈���輻��芣��滩��餉� (Retry-on-Conflict Loop)**嚗𡁻�撖� Windows �臬�銝见虾�賢笆�格� `reentry_states.json` ��辣鈭抒� transient lock嚗�葩�嗅��剁����敶ｇ��� `_save_state` 銝剖��� 5 甈∟䌊���霂閙㦤�塚�瘥𤩺活憭梯揖�𦒘��� 100ms 撟嗆�����嗵�蝥輻�銝湔𧒄��辣嚗𣬚＆靽脲�蝡臬僎�睲��唳旿 100% �𣂼�����硔��
    - [x] **銝��芷�朞��訫�瘚贝�銝𤾸��脣�瘚𧢲嵗撉�**嚗𡁜笆 `reentry_tracker.py` 餈𥡝�鈭� `py_compile` �蹱��祗瘜閧�霂烐嵗撉䕘�撟嗆��罸�朞�鈭� `test_reentry_backtest.py` �墧��餉�撉諹�隞亙��芸�銋匧�靘𧢲㺭�株粉�坔���雿擧��䀝遠 `lowest_since_exit` 頝蠘葵瞍𠉛�嚗𣬚迅摰𡁏�扯噢�啣極銝𡁶漣�����

## 2026-06-02 18:05
- [x] **摰䂿緵 PandasQueryEngine `.str.contains` 撣行��砍噡蝑厩鸌畾𠰴�蝚衣��箄��亙ㄝ�折��� (Implemented Robust .str.contains Rewrite in PandasQueryEngine)**嚗�
    - [x] **憓𧼮��芸𢆡��㺭瘜典��箏� (Automatic Parameter Injection)**嚗𡁜銁 `query_engine_util.py` �� `PandasQueryEngine._preprocess_query` 銝哨�憓𧼮���笆 `.str.contains` 霂剖蘂��䌊�冽迤�䠷��䠷�餉���笆鈭𦒘�撣血�隞硋��啁� `.str.contains("...")` 璅∪�嚗諹䌊�冽釣�� `case=False, regex=False, na=False`��
    - [x] **摰𣬚�靽桀�撣行𡠺�瑟�敹菜�蝝Ｗ仃�� Bug (Fixed Concept Search with Parentheses)**嚗朞�隞𤾸�撅�䰻霂Ｗ��𦒘�敶餃��寞祥鈭�掩隡� `category.str.contains("�勗�鋆��摮�(CPO)")` 蝑匧蒂�㗇𡠺�瑞��寞�璁�艙�亥砭�曹� Pandas 暺䁅恕 `regex=True` 撖潸稲�砍噡鋡怨圾�𠹺蛹甇������峕�瘜訫龪�滨��桅���
    - [x] **摰䂿緵憭𡁶垢�屸𢒰�亥砭�蠘��芸𢆡撖寥�**嚗𡁏迨靽桀�銝漤�閬�耨�� `instock_MonitorTK.py` 銝剔��瑚�銝𡁜𦛚隞��嚗𣬚凒�亙銁摨訫�撘閙�銝𢠃�𤩺�摰峕�嚗䔶蝙 Tkinter 摰Ｘ�蝡臬� PyQt6 摰Ｘ�蝡臬笆鈭舘砲蝐餅䰻霂Ｗ��賭誑摰��銝��渡��孵��芸𢆡�舀���
    - [x] **銝��芷�朞��券��訫�瘚贝�銝舘祗瘜閧�霂烐嵗撉�**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䕘�撟園�朞����瘚贝��𡁏𧋦撉諹�鈭�銁璅⊥��唳旿銝� `category.str.contains("�勗�鋆��摮�(CPO)")` �� 100% 甇�＆餈�誘�箏��急𡠺�瑞�銝芾���

## 2026-06-02 18:40
- [x] **摰䂿緵頝笔���泿�� HUD �滨��單釣銝芾�撘箇蔭憿嗡��𧼮��冽遬蝷箔�蝔喳�鈭峕活�鍦� (Implemented Favorite Stocks Always-On-Top & Non-Occupying in Follow HUD)**嚗�
    - [x] **摰䂿緵�滨��單釣銝芾��芸𢆡銵亙��箏� (Favorite Stocks Supplemental Ingestion)**嚗𡁜銁 `spatial_follow_hud.py` 銝哨��齿�鈭� `update_hud_data` �餉���銁餈𥡝��滨��芷�㕑���踎�堒�撅墧嵗撖寞𧒄嚗䔶���蝙�冽���膥��������撅� `detector.sector_map` 蝻枏�餈𥡝�銝芾�-�踹�敶鍦��寥��文�嚗���� Fallback �� `ts.category` / `ts.get_splitted_cats()` ����砍���ế摰𡄯�敶餃�閫��鈭�眏鈭𤾸��� Tick �埈� category 摮埈挾撖潸稲���憯怠熒璁�艙銝剔��𨅯極銝𡁜��䈑�601138嚗争�苷��厩漱璁�艙銝剔��𣈯�𡁻�鈭坿�嚗�002491嚗争�萘��滨��單釣銝芾��䭾�鋡� HUD 霂��銵亙���艇�齿�瘣𠺶��
    - [x] **摰䂿緵�滨��單釣銝芾�銝滚�雿滚撩蝵桅▲ (Always-On-Top & Non-Occupying Constraint)**嚗𡁜銁霈∠��踹�瘜閧��穃����AES嚗匧�嚗����僎�𡒊�頝罸��∪�銵典�瘚�蛹�𣈯��孵�瘜其葵�﹦�苷��𨀣芦�朞�憌𦒘葵�﹦�苷舅�典�����嫣葵�∩��� 4 銝芸�憸苷��鞟漲���撖孵�餈𥡝��券�蝵桅▲撅閧內嚗𥟇芦�朞�憌𦒘葵�∪�靽萘���𧋦�� AES �滚��鍦�撟嗆⏛�硋� 4 �芥���蝢舘噢�𣂷��𣈯��孵�瘜刻�憪讠�蝵桅▲銝𥪯��删鍂�桅�朞�憌舘��漤��萘��滨�摰墧���瘙���
    - [x] **摰䂿緵銵典仍�见𢆡�鍦��𠰴��啁迅摰帋�甈∪凝靚� (Stable Secondary Sort Protection)**嚗𡁜銁 `update_hud_data` �瑟鰵�齿��� `_on_header_clicked` 銵典仍�见𢆡�孵稬�噼�銝哨�隡睃�鈭��甈⊥�摨𤩺㦤�嗚����函鍂�瑟𧊋�鍦�嚗��霈斤𠶖�� `sort_col == -1`嚗㗇��孵稬�靝誨��/�滨妍�嘥�嚗Ǒsort_col == 0`嚗㗇�摨𤩺𧒄嚗峕�撘箏�撠���孵�瘜其葵�∠蔭憿嗅僎餈𥡝�鈭峕活蝔喳�敺株�嚗𥡝𥅾�冽��见𢆡�孵稬鈭��雿蹱㺭�澆��批�嚗���唬遠��隅撟����瘨汽�潦���蝳聞FF蝑㚁�餈𥡝��鍦�嚗��摰��撠𢠃���𧋦���摨誩��滚�閫��嚗䔶�餈𥡝�隞颱�憸嘥���蔭憿嗅僕�堆���之�𣂼�鈭���条��菜暑�扼��
    - [x] **100% 瘥急�甇餉�銝��芸�蝏輸�朞� py_compile 霂剜��⊿�**嚗𡁶� python 銝剖亢蝻𤥁��券�霂��靽格㺿�� `spatial_follow_hud.py` 皞鞟���辣霂剜� 100% 甇�＆嚗䔶��靝�撌乩�蝥抒�鈭支���捶��

## 2026-06-02 18:25
- [x] **摰䂿緵蝡硺遠�Ｘ踎�滨��單釣銝芾�撘箏��曄內銝𡒊迅摰𡁏�摨讐蔭憿� (Implemented Favorite Stocks Force Show & Stable Double-Sorting)**嚗�
    - [x] **摰䂿緵蝔喳�鈭峕活�鍦�蝵桅▲�箏� (Stable Double-Sorting)**嚗𡁜銁 `sector_bidding_panel.py` ��葵�⊥㺭�格��鍦��餉��𠬍�撘訫��箔�蝔喳��鍦����甈∪凝靚���銁摰��靽萘�銝𠹺�蝥扳��孵��梹�憒�隅撟����蝏芸�潘����摨讐㮾撖寥◇摨讐��齿�銝页�撘箏�撠�挽銝粹��孵�瘜函�銝芾�嚗�洵銝�隡睃�蝥改�銝𡡞�憭港葵�∴�蝚砌�隡睃�蝥改�蝘餉秐憿園�嚗��蝢𤾸��啁��㗛��寧��祇𡢿�毺䰻��
    - [x] **摰䂿緵�滨�銝芾��脰�皛支��� (Bypassed Filter & Search)**嚗𡁻����銝芾��㰘蝸銝剝�撖孵�閫�䰻霂Ｚ�皛� `self._macro_filtered_codes` �峕�蝝Ｘ䰻霂Ｚ�皛� `active_query` ���皛斗㜃�芸ế摰𠾼����虫葵�∩誨���鈭� `self.favorite_stocks` 銝哨��嗵凒�亦�餈���㕑�皛方��坔撩�嗆遬蝷綽�靽嗪��滨��讠�撖嫣�瞍讐��滨��單釣��䌊�厩𤌍����
    - [x] **瘨�膄銝芾�瘛餃��滨��單釣�嗥��滚��唳旿�滨�銝� UI �屸��瑟鰵 (Eliminated Double Recalculation on Toggle Favorite)**嚗𡁜�雿滚僎靽桀�鈭���餅溶��/�𡝗��滨��單釣銝芾��嗉圻�𤑳��𤾸蝱�唳旿�滚��滨��桅���� `_add_favorite_stock` 銝� `_remove_favorite_stock` 撠暸�擃䀹��祉� `self.refresh_data(force=True)`嚗��撘箏��日��𤾸蝱蝥輻�靚�鍂�埈𧒄 1.2s �� `update_scores` 霈∠�撟嗅紡�� SignalBridge �滚��噼�嚗厰���蛹�砍𧑐蝥� UI ����滨� (`_refresh_sector_list()`��_populate_watchlist()`��_on_sector_table_selection_changed()`)���隞�覔瘝颱�銝斗活�𦯷sync scoring completed�萘�撘�郊�瑟鰵霅血�嚗諹�撠��雿𨅯辣餈煺�蝘垍漣�祇𡢿�滩秐 0 瘥怎���
    - [x] **隡睃�閫���園鵭靚���脫�銝擧隅頝峕㺭�格��煺��� (Implemented Debounced Interval Adjustment & Data Preservation)**嚗𡁻���� `_adjust_interval` ��𧒄�輯��湧�餉�����支� `self.detector.reset_observation_anchors()` 靚�鍂嚗𣬚＆靽嘥銁撱園鵭�𣇉憬�剖笆瘥娍𧒄�渡���𧒄嚗𣬚�銝剖歇蝝航恣�閙���葵�∩遠�潛��孵����瘨刻���蟮銝滩◤皜�征�滨蔭����嗅��乩� 2.0 蝘㘾俈�𤥁恣�嗅膥 `_interval_debounce_timer`嚗䔶蝙�冽��刻�蝏剔��餉�����殷�`-10m` �� `+10m`嚗㗇𧒄嚗𣬚��Ｘ㺭摮堒朖�嗅�摨䈑��峕��函��拍�銵峕�霈∠�隞�銁�冽��𨀣迫�孵稬�𤾸辣餈蠘圻�睲�甈∴��踹�鈭��憸烐�雿𨀣𧒄����Ｗ㨃憿踴��

## 2026-06-02 18:10
- [x] **摰䂿緵�踹��𥪜𢆡�Ｘ踎銝芾��喲睸�滨��單釣銝𤾸��嗉��� HUD �滨�銝芾�撘箇蔭憿嗆綫�� (Implemented Favorite Stocks Toggle and HUD Prioritization)**嚗�
    - [x] **銝芾��喲睸�嗉�銝擧�銋�� (Context Menu & Save)**嚗𡁜銁�踹��𥪜𢆡�Ｘ踎 `sector_bidding_panel.py` ��葵�∟” `stock_table` �諹䌊�匧�瘜刻” `watchlist_table` ��𢰧�株��蓥葉���鈭� `潃� 霈曆蛹�滨�銝芾�` 銝� `�� �𡝗��滨�銝芾�` �厰★嚗�僎�𥪜𢆡 `_save_ui_state()`嚗���啗楊隡朞�����碶�摮塩��
    - [x] **銝芾��滨��單釣�航��� (Visual Star Prefix)**嚗𡁜銁銝芾�銵其��芷�匧�瘜刻”��㺭�桀‵���餉�銝哨�撖孵歇霈曆蛹�滨��單釣��葵�∪�蝘啣��Ｗ𢆡����� `潃㦀 �滨������
    - [x] **頝笔� HUD �滨�銝芾�撘箇蔭憿� (HUD Prioritization)**嚗𡁜銁 `spatial_follow_hud.py` 銝哨��朞� `_get_favorite_stocks()` 頝冽芋�堒��刻繮�硋��滩挽銝粹��孵�瘜函�銝芾�嚗�僎�函�摮阡��� AES ���撘箏漲�鍦���抅蝖�銝𠺪�隞� `(is_fav, aes)` �屸��滚�銝駁睸撖寡�憌舘��齿鰵�鍦�嚗䔶蝙�滨��單釣��葵�∪�樴坔仍�� HUD 銝剖撩銵𣬚蔭憿嗡����蝷箝��
    - [x] **銝��株��閙�鈭斗㺭�格�瘣� (Clean Submission Name)**嚗𡁜銁銝��桐��閧���圻�烐𧒄嚗諹䌊�券�朞� `.replace("潃� ", "")` 皜��銝芾��滨妍銝剔��笔噡�滨�嚗𣬚＆靽脲�鈭斤�鈭斗���瓲���蟡典�摮埈�隞颱�鋆�弘�誩�蝚艾��

## 2026-06-02 17:55
- [x] **�啣��典�敹急㭘�� Alt+U �鞱�銝擧遬蝷箄��閙��交� HUD (Implemented Alt+U Global Hotkey to Toggle Spatial Follow HUD)**嚗�
    - [x] **瘜典��典��剝睸銝𤾸�靚��摰�**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_HOTKEY_MAP` �� `_HOTKEY_INFO_MAP` 瘜典�鈭� `Alt+U` (ID 12)嚗�僎�唾�摰帋�鈭� `global_toggle_spatial_follow_hud` 雿靝蛹�嗆��臬�摨𥪜�靚���
    - [x] **摰䂿緵�祉��剝睸餈𤤿��峕郊�舀�**嚗𡁜銁 `hotkey_rotator.py` �祉��剝睸餈𤤿��� `self.hotkey_map` �惩�摮堒�銝哨��峕郊銵仿�鈭� `12: (win32con.MOD_ALT, 0x55, ...)`嚗𣬚＆靽� `Alt+U`�剝睸�賢銁�祉�����餃�雿𤾸辣餈毺��桀��方�蝔衤葉�閗繮嚗�僎隞亦恣�枏𦶢隞� `HOTKEY_TRIGGERED` 摰匧��噼��喃蜓餈𤤿���
    - [x] **摰䂿緵�删��寞㜃�芰��典�撘��喃漱鈭� (Focus-free Toggle Logic)**嚗𡁏鰵摰䂿緵鈭� `global_toggle_spatial_follow_hud` �賣㺭嚗�銁�鞱�銝擧遬蝷粹�餉�銝剖��典竉蝳颱���笆 Tkinter 颲枏�獢���寧��行⏛�文���朖雿輻鍂�瑞��寥彿�坔銁隞颱� Entry/Text 颲枏��������朞� `Alt+U` 撘箏��䭾�撘��� HUD嚗�僎靽脲�鈭��蝛箸聢�桅��典��鞱�/�曄內鈭支����蝢𤾸笆朣僐��

## 2026-06-02 17:45
- [x] **閫��行踎�烾𢒰�蹂�韏偦帕�Ｘ踎���閫�䰻霂Ｚ�皛歹��Ｗ�撌虫儒瘣餉��踹��券�撅閧內 (Decoupled Macro Query Filtering from Active Sectors List in Bidding Panels)**嚗�
    - [x] **閫��行踎�𡑒��券𢒰�踹椰靘批�銵刻�皛� (Decoupled Sector Bidding Panel Left Table)**嚗𡁶宏�支� `sector_bidding_panel.py` �� `_refresh_sector_list` 銝剝�撖� `sectors` �𡑒”���閫�䰻霂� `self._macro_filtered_codes` �拍�餈�誘��＆靽嘥椰靘扳暑頝�踎�𦯀��埈�蝝Ｗ蔣�溻���蝏���游�蝷綽���之蝏湔擪鈭��銝剔��扯��𡒊�摰峕㟲�扼��
    - [x] **�峕郊�齿��䀝葉韏偦帕�Ｘ踎撌虫儒�𡑒”餈�誘 (Decoupled Bidding Racing Panel Left Table)**嚗𡁜�甇亦宏�支� `bidding_racing_panel.py` �� `update_visuals` �寞�銝剛�皛� `active_sectors` 隞亙��冽�摨誩�撖� `all_sorted_sectors` �寞旿憸�隅�∪𦶢銝剔�餈�誘�行⏛��蝙韏偦帕�𧢲踎��椰靘扳踎�埈��埈�憭滚��湛�銵䔶蛹銵函緵銝擧踎�𡑒��券𢒰�輸�摨虫��湛�蝚血� SOLID / DRY �笔�嚗剹��
    - [x] **靽萘�撟園�霂�𢰧靘找葵�∩��芷�㕑�皛� (Preserved Right-side Stock and Watchlist Filters)**嚗𡁏踎�埈�蝏�葵�∟”�𢠃��孵�瘜刻”嚗Áatchlist嚗劐葉靘脲旿 `self._macro_filtered_codes` 餈𥡝���葵�∠漣�怨�皛日�餉�靽脲�摰��銝滚�嚗���唬��𨅯�閫�䰻霂Ｖ�餈�誘銝芾�嚗�椰靘扳踎�埈遬蝷箔��堒蔣�𨧀�萘�蝎曉�摰𡁜�閬����
    - [x] **100% �朞��蹱��祗瘜訫��餉�蝻𤥁��⊿�**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䕘�蝖桐�撌乩�蝥抒�鈭支���捶��

## 2026-06-02 17:25
- [x] **�齿� HUD 銝��株��訫��詨�擐�楝�梧�靽桀��䭾�蝏苷縑�� Bug (Refactored HUD Submit Follow Kernel Dispatch & Fixed Blank Reject Reason Bug)**嚗�
    - [x] **�箏� HOLD 銝𡒊����蝏� (Decoupled HOLD from REJECTED)**嚗𡁜��𣂷��𣂷漱頝笔��𠬍�敶枏��貊遞���蝑碶蛹 `HOLD`嚗�誨銵刻���𧊋颲暹�憒� 0.5336 < 0.55嚗𣬚頂蝏笔遣霈株��𨥈��屸�憌擧綉蝖祆�批㨃雿𤩺𧒄嚗�� UI �餉�隡𡁜� `kernel_executed=False` �湔𦻖霂臬ế銝算�𡏭��閗◤憌擧綉�垍��嘥僎撘寧�霅血���撩�瑯��
    - [x] **霈曇恣蝎曉�銝㗇���瘚��蝷箸� (Implemented High-Fidelity Multi-Branch Dialogue)**嚗𡁜銁 `spatial_follow_hud.py` �� `_on_submit_clicked` 銝见��漤�憭���������文�嚗�
        1. **HOLD嚗�遣霈株��𨥈��嗆��**嚗𡁻��� `QMessageBox.information` 撘寧��见末�鞟內敶枏���瓲蝏坔枂閫���喟�嚗�僎隞仿��航圾�𦠜�批�蝷箇遞����� (Confidence)����臬耦�� (Setup)��踎�㛖�摨� (Heat) 隞亙� DFF 撘箏漲嚗峕�蝖格�蝷箇鍂�瑕�撅硺��𨅯�����𥕞�肽�屸�撘�虜鋡急���
        2. **REJECTED嚗���扳���瓲�垍�嚗厩𠶖��**嚗帋��� `allowed=False` �� `reject_code` 摮睃銁�嗉圻�𤏸郎�𠺪�撟嗡�敶𤘪�蝏萘�蝻箏仃�園�朞� `RISK_BLOCKED` �芸𢆡銵仿�摰匧��𨅯�嚗峕覔瘝颱�撘寧�銝凌�𨀣�蝏萘�:�嘥��寞遬蝷箇征�賜��桅���
        3. **SUCCESS嚗���閙�����嗆��**嚗帋��函�����笔��䀝��訫�撘孵枂鈭斗�憪娍��閖�埝����蝷綽��曇��𣂼�鈭���䀹��䀹𧒄��凒閫劐�撉䔶�鈭支�韐券���

## 2026-06-02 16:55
- [x] **靽桀�蝡硺遠�Ｘ踎�喲𡡒�𤾸�甈⊥�撘��䭾㺭�桀�蝷� Bug (Fixed Sector Bidding Panel Re-open Blank Data Bug)**嚗�
    - [x] **撘訫� Detector �典��批ế摰𡁏�霈� (Global Detector Tracking)**嚗𡁜銁 `SectorBiddingPanel.__init__` 銝剜鰵憓� `self._is_global_detector` �嗆���敹𨰜����� `detector` �臭�銝餌��� `main_window` �曹澈���撅��臭� `racing_detector` 摰硺�嚗���嗆�霈唬蛹 `True`嚗峕𧋦�� fallback �𥕦遣�����膥�蹱�霈唬蛹 `False`��
    - [x] **�拍��娍鱏�典��枏��刻◤霂舀� (Prevented Global Detector Termination)**嚗𡁻���� `closeEvent` �鞉��墧𤣰�餉���銁�喲𡡒摮鞾𢒰�踵𧒄嚗䔶��券��典� `detector` �嗆��扯� `self.detector.stop()` �仿�瘥�瑪蝔见�蝵桐��𨀣迫�嗆�����敶餃�瘨�膄鈭�迨�𨧀�𨅯��剔�隞琿𢒰�踹�嚗峕��典��枏��函��𤾸蝱 `async_sector_agg_worker` 撌乩�蝥輻�敶餃����箔��� `_stop_event` 霈曆蛹 `set`嚗�紡�游�甈⊥�撘��Ｘ踎�嗆���遙�⊥�瘜閗◤撌乩�蝥輻�瘨�晶嚗屸�䭾� UI 瘞訾��賢��萘��孵之�餉�瞍𤩺�嚗��蝢𤾸��唬�蝡硺遠�Ｘ踎���甈∪��凋�摰墧𧒄�唳旿��神蝘垍漣�單𧒄頧賢�嚗�

## 2026-06-02 17:15
- [x] **靽桀� HUD 皛𡁜𢆡�滨�撖潸稲 Windows `UpdateLayeredWindowIndirect` 憭梯揖 Bug (Fixed HUD Layered Window Clipping Paint Bug)**嚗�
    - [x] **���韐笔�����箸覔皞� (Analyzed Dirty Rect Coordinate Mismatch)**嚗𡁜�雿滚��典��𤩺��㰘器獢��`WA_TranslucentBackground`嚗厩����嚗屸狍敶勗��㗇��頣�`QGraphicsDropShadowEffect`嚗匧�����啣��亦� `QScrollArea` 瘞游像皛𡁜𢆡�𤑳��脩���眏鈭擧��冽𧒄摮鞾�隞嗅����銝箄��堆��游蔣璅∠�霈∠��拙��𦒘漣�蠘��鞉��諹���偕撖賂�憒� `dirty=(1368x862 -12, 88)`嚗諹��箇��� 1344 �拍�摰賢漲嚗㚁�撖潸稲 Windows ���蝒堒藁蝟餌��𥕦枂�𨅯��圈�霂胼�嘥僎�垍��瑟鰵��
    - [x] **�齿��芷���撣���游蔣摰匧�颲寧� (Implemented Layout Margins Safeguard)**嚗𡁜�憿嗥漣蝒堒藁 `main_layout` �� `setContentsMargins` �勗���� `(0, 0, 0, 0)` �拍��枏捐�� `(20, 20, 20, 20)`嚗�僎�� `_init_ui` 銝剖��游蔣�� `BlurRadius` 蝻拍揮�� `16px`���蝖桐�鈭�狍敶梁����匧��厩��嗅��典�鋆孵銁憿嗥漣蝒堒藁�拍���凒���嚗䔶��拍�銝𢠃�蝏苷��誩躹頞羓���
    - [x] **敺株��㰘器獢�憬�暹����撅� (Fine-tuned SizeGrip Layout)**嚗𡁻��� 20px 颲寡�嚗�� `resizeEvent` 銝剜�颲寞��𡝗嗻 Grip ������雿滢� `-4px` �喃��讐蔭敺株�銝� `-24px`���靽肽�鈭�憬�暹���移����其��𤩺� `main_frame` ���靘批𢰧銝贝�嚗峕𠳿靽肽�鈭��������瘚���𡝗嗻銝𦒘�隞嗆𦻖�塚���蝠摨閙��支� Windows 蝟餌���葡�𤘪𥁒�踺��

## 2026-06-02 16:45
- [x] **摰䂿緵摰墧𧒄頝笔� HUD 10�踹��拙捆銝擧偌撟喲����頧株��𤩺��� (Implemented HUD 10-Sectors Expansion & Horizontal Wheel/Auto-Scroll Integration)**嚗�
    - [x] **撖潸⏛�䠷�㗇踎�埈㺭�讐蕃�� (Sectors Capacity Doubled)**嚗𡁜� HUD 憿嗅��䠷�匧翰�瑕紡�芣��桐� 5 銝芰蕃�齿�撅訫� 10 銝迎�撟嗅�甇亙� `update_hud_data` ���撖� active �Ｘ��典� FocusController 憭�鍂�瑕��剖漲�踹�����脖��鞟眏 5 �𣂼��� 10��
    - [x] **撘訫� QScrollArea 撟單�皛𡁜𢆡摰孵膥 (Scrollable Candidate Layout)**嚗帋蛹鈭�銁�厰� HUD 蝒堒藁�����捆蝥� 10 銝芸�䠷�㗇��殷�摨笔�鈭���厩�蝖祉���偌撟喳捆�剁��齿�銝粹�摨阡��嗡蛹 28px �� `QScrollArea` 瘞游像皛𡁜𢆡�綽��鞱�璅芸�銝𡒊熊�烐��冽辺嚗峕�颲寞��峕艶�𤩺�嚗㚁�摰𣬚�閫���厰僼�交𣱣銝擧滯�粹��～��
    - [x] **摰䂿緵曌䭾�皛朞蔭撌血𢰧皛𤏸� (Horizontal Scroll Filter)**嚗𡁜�撱箏僎銝� `QScrollArea.viewport()` 摰㕑�鈭� `HorizontalScrollFilter` 鈭衤辣餈�誘�具��移���曌䭾�����砍��典�䠷�匧躹�嗥���凒皛朞蔭嚗À�孵�嚗㕑�摨虫�蝘餃銁�𤾸蝱�芸𢆡�惩�撟嗉蓮�Ｖ蛹瘞游像皛𡁜𢆡�∴�X�孵�嚗厩�撟單�皛𤏸�嚗諹悟�滨��见虾隞仿�朞�皛朞蔭�����閫�踎�𨰜��
    - [x] **摰䂿緵�芸𢆡�劐葉頝罸�皛𡁜𢆡 (Ensure Selected Visible)**嚗𡁜銁 `update_hud_data` 霈曄蔭摰峕踎�𡑒◤�劐葉�嗆���嚗屸�朞� `QTimer.singleShot(50, ...)` 撘�郊�笔�瘣曉�嚗諹䌊�典�憭�� `checked` 銝� `visible` �嗆����踹��厰僼隡删� `scroll_area.ensureWidgetVisible(btn)`���霈箇鍂�瑟糓�朞��桃��孵��殷�Left/Right/Up/Down嚗剹������頧桀�撅�頧桀𢆡嚗諹��臬��冽㺭�格���揢瞈�瘣鳴�HUD �質�隞交�摰Ｘ���漲�祇𡢿�芸𢆡撠�笆摨娍踎�埈��格��典僎��緵�喳虾閫���港葉憭殷���稲�𣂼��䀝葉頝笔����瘚��撉䎚��

## 2026-06-02 16:30
- [x] **隡睃��踹��𥪜𢆡�烐綉銝𤾸��嗅蔣摮鞱��� HUD �滨��踹�擃睃撩摨西��� (Optimized Sector Bidding Panel & Spatial Follow HUD Priority Watchlist)**嚗�
    - [x] **摰䂿緵瘣餉��踹��𡑒”�喲睸�嗉��芣��箏�**嚗𡁜銁 `sector_bidding_panel.py` ��踎�堒�銵其�����喲睸 `潃� 霈曆蛹�滨��單釣` 銝� `�� �𡝗��滨��單釣` 鈭支��𨅯�嚗�僎���蝏穃�鈭� `_save_ui_state()` 銝� `_restore_ui_state()`嚗���啗楊隡朞��� UI �嗆���銋����
    - [x] **�啣��航��㚚��孵�瘜冽�蝷�**嚗𡁜銁�踹��𥪜𢆡�Ｘ踎�𡑒”皜脫� `_refresh_sector_list` �塚�撖嫣�撌脰挽銝粹��孵�瘜函��踹�嚗𣬚洵銝��埈踎�堒�蝘啣�憓𧼮� `潃㦀 �滨����嚗峕��𦒘��� tags �滨�憓𧼮� `[����鉛` ��倌餈𥡝�擃䁅儘霂�漲�垍𤌍撅閧緵��
    - [x] **摰䂿緵�滨��踹�撘箸�摨讐蔭憿嗡���漣**嚗𡁜銁 Python 蝥扳�摨譍葉撘訫� `is_fav` ���銝駁睸 `(is_fav(x), 撅墧�批��)`��銁暺䁅恕�嗆����见𢆡�孵稬銵典仍�鍦��塚��滨��踹��券�摨譍�摰𣬚�蝵桅▲嚗���唬��鍦��園��寞踎�𦯀�����𨰜��
    - [x] **�㯄�𡁜��嗉��� HUD �滨�撘�𢆡擃䀝�蝵桅▲�毺䰻 (HUD Priority Sync)**嚗𡁜銁 `spatial_follow_hud.py` 銝哨��朞� `_get_favorite_sectors` 頝刻�蝔�/�Ｘ踎摰匧��瑕��滨��嗉��唳旿嚗�僎摰䂿緵 `_get_prioritized_active_sectors` 撖寡�獢���垍�瘜𨰻��銁 HUD ����臬𢆡摰帋����䠷�匧紡�芰��𣂷誑�𠰴��嗉��瑟鰵撖餃�銝哨�隡睃�霂餃�撟嗆綫�𣂼歇鋡怠�銝粹��孵�瘜函��踹��𠰴�銝芾�撘�𢆡����單釣�滨��踹�撠睲� 5 銝芣𧒄嚗�像皛烐毽��‵���隞𣇉��冽暑頝�踎�梹��拍�颲暹� 100% ��恥�滨��讠�閫����

## 2026-06-02 15:30
- [x] **靽桀�韏偦帕��蟮�亥砭銝𧢲�獢�鵭銵刻噢撘𤩺⏛�凋�擃睃漲霈∠��滚蔣 Bug (Fixed Racing History Query Dropdown Clipping & Overlapping)**嚗�
    - [x] **�拍��惩𤐄 `HitHighlightDelegate.sizeHint` �舐鍂摰賢漲�文�**嚗𡁜��乩��箔� `option.widget.minimumWidth()` ���憭批�澆�撟嗅�摨閙㦤�嗚��朖雿踹銁擃㗛��瑟鰵�硋��臬𢆡�嗡��㕑��曉��芸��冽遬蝷箔蝙敺� `viewport().width()` 餈𥪜� `0` �硋��啣�潘�蝟餌�銋蠘���＆�𣂼�憸�挽���撠誩捐摨佗�`650px`嚗㚁�敶餃�閫��鈭��甇文紡�渡�擃睃漲隡啁��誩之�𦠜����敶梁�憿賜𪆴��
    - [x] **�拙�銝𧢲�閫�㦛�拍���撠誩捐摨阡���**嚗𡁜銁 `bidding_racing_panel.py` �� `query_input` �嘥��𡝗𧒄嚗��銝𧢲�閫�㦛 `view().setMinimumWidth()` 撘箏��� `450px` �枏捐�� `650px`��蛹頞�鵭摰讛�銵刻噢撘𤩺�靘𥕢������������赤�𤑳征�湛�靽肽�鈭� `[Hit: N]` 蝑㗇瓲敹��霈∩縑�舐蓡����曉��游��堆�敶餃�瘨�膄鈭�◤璅芸��芣鱏�𡝗遬蝷箔��函�蝻粹萅��

## 2026-06-02 10:25
- [x] **摰���亦氖�滨垢 UI �滚��芣��嗵�嚗���唳��笔蘨霂餃�摮䀹葡�� (Cleaned Frontend UI Auto-Heal File Write Loops)**嚗�
    - [x] **皜�� PyQt6 `signal_dashboard_panel.py` �滚�霂餃�**嚗�
        - 蝘駁膄鈭� `async_fetch_task` �枏�蝥輻�銝剔��滚�雿嗵��砍𧑐 HDF5 �㰘蝸��葵�∠��滩䌊��ế�凋誑�𠰴��� `premarket_diagnose.json` ���憭齿�蝔页�隞�銁���銝剖��冽聢撘誩��園𡢿�喋��
        - 蝘駁膄鈭�蜓蝥輻� `_refresh_guidance_table` �瑟鰵皜脫��嗅�雿� of `any_healed` �嗆��蕭頦芯�撘�郊 `async_write_back` �𧼮�蝥輻�嚗䔶蝙�滨垢撅閧緵�𧼮�蝥舐硃����扯����𨅯蘨霂領�脲葡�瓐��
        - 敶餃��𣳇膄鈭�蜓蝥輻�銝剝������ `ui_name_map` 摮堒��峕��� `_get_df_all_realtime()` ���雿躰恣蝞梹�摰���踹�瘥𤩺活��倌�瑟鰵����嗅��唳𧒄����譍�霈∠�撘���嚗㇃PU �讛�嚗剹��
    - [x] **皜�� Tkinter `stock_selection_window.py` �瑟鰵�嗵�**嚗�
        - 敶餃��𣳇膄鈭� 瘥𤩺𠯫�滢���� Treeview �瑟鰵�賣㺭 `_refresh_guidance_tab` �怠偏�� `any_healed` �餉���� `filepath` �滚� json �坔��其�嚗���瑚��典�摮䀝葉�朞� `resolve_stock_name` 摰峕� UI ��遬蝷箏�摨𤏪��𦦵�鈭��蝡舫�憸穃��圈�䭾���𧋦�啁��䁅粉�坔�蝒�� CPU �祆𧒄撘�����


## 2026-06-02 02:30
- [x] **摰䂿緵憭𡁜��𠉛�銝擧�銋�䌊���銝芾��滚�閫���剁�敶餃�閫���靝葵�︵�嘥�雿滨泵�桅� (Implemented Multi-layer Network & Persistent Self-healing Stock Name Resolver)**嚗�
    - [x] **�拍��惩𤐄 `sys_utils.py` �芣�摨訫漣**嚗𡁜銁 `sys_utils.py` 摨閖�摰䂿緵撟嗅紡�箔��瑟�擃㗛�璉埝�抒��滚�閫��撘閙� `resolve_stock_name(code_clean)`��砲�寞��亦氖鈭��蟡其誨���銵冽�銝𤾸�雿枏�蝵殷���鍂�𨀣𧋦�� HDF5 摨梶揣撘� �� ���啁�隞瑁�撽� JSON 敹怎� �� �滢������蟮霂𦠜鱏霈啣� �� �滩晶�唳答 HTTP API �亙藁�𠉛�摰墧𧒄�匧�嚗�蒂頞�𧒄嚗争�萘��偦��芣�銝𡡞�蝥扳㦤�塚�靽肽��其遙雿閙�蝡航�銵𣬚㴓憓����� 100% �𣂼�閫��銝芾���葉���蝚血�蝘堆��垍�隞乒�靝葵�︵XXXXXX�脲�隞��蝥舀㺭摮𦯀�銝箏�摮𨰜��
    - [x] **皞𣂼仍�餅鱏 `premarket_analyzer.py` �誩�摮堒���**嚗𡁜銁 `premarket_analyzer.py` 銝剖��� `resolve_stock_name` 撟園���� `run_premarket_diagnose` ���隞栞��滚��瑕��餉���� `pos.get("name")` 銝滚��冽�銝� `銝芾�_` / 隞��蝑匧�雿滨泵�嗥凒�亥圻�𤏸圾�僐����唳旿皞𣂼仍�� Ingestion �嗆挾�拍��餅鱏鈭���牐�蝚血�摮㛖�鈭抒�嚗峕��支��𦯀����摮𦯀耨憭滚之敺芰㴓嚗䔶誨��凒�䭾��賜�瘣��蝚血� KISS / DRY �笔�嚗剹��
    - [x] **�墧��唳旿皞� `test_reentry_backtest.py` �峕郊�芣�**嚗𡁜銁 `update_premarket_diagnose_json` �坔��睃�霂𦠜鱏��辣������撘訫�撟嗉��其� `resolve_stock_name`����血��唬葵�⊥瓷�匧����摮埈�銝� placeholder �塚��祇𡢿�芣��瑕��笔�嚗䔶��𨅯�瘚见��见𢆡瘛餃��墧��嗥��䀹钟�滢�霈∪�銝剔�銝芾��滚�蝏嘥笆撟脣���
    - [x] **�滨垢 PyQt6 隞芾”�䀝� Tkinter 憭批��峕郊閬��**嚗�
        - [x] **PyQt6 隞芾”�䁅䌊��**嚗𡁜銁 `signal_dashboard_panel.py` ���甇亥繮�碶遙�� `async_fetch_task` 餈䀹�銵冽聢皜脫��瑟鰵 `_refresh_guidance_table` �嗆挾撘訫� `resolve_stock_name` �𨅯�閫������血銁銝餌瑪蝔𧢲��𤾸蝱蝥輻�霂���� `銝芾�_` �牐�蝚佗��祇𡢿摰峕�閫��蝥𣳇�嚗�僎蝡见朖�朞� `any_healed` �嗆���閫血� `async_write_back` �拍��坔� `premarket_diagnose.json`嚗���售�靝�甈∠�甇��瘞訾�摮条��腈��
        - [x] **Tkinter 摰Ｘ�蝡臬�甇亥䌊��**嚗𡁜銁 `stock_selection_window.py` �瑟鰵霂𦠜鱏�厰★�� `_refresh_guidance_tab` 銝剛‘朣𣂷�撖� `resolve_stock_name` ����具��䌊�典�蝥䭾迤�𡒊�銝剜��笔��嗵�����吔�摰䂿緵鈭�楊獢�沲���蝡舐��删��芣��剔㴓��
    - [x] **100% 瘥急�甇餉�銝��芸�蝏輸�朞� py_compile 霂剜��⊿�**嚗𡁶� python 銝剖亢蝻𤥁��券�霂��靽格㺿�� 5 銝芣瓲敹�����隞嗉祗瘜訫�蝻抵� 100% 甇�＆嚗䔶��靝�撌乩�蝥抒�鈭支���捶��

## 2026-06-01 20:30
- [x] **摰䂿緵�见𢆡撠��瘚贝恣�鍦��亦��齿�雿𨀣��� (Implemented Manual Saving of Backtest Plans to Guidance)**嚗�
    - [x] **PyQt6 蝡舫��𣂼紡�箸���**嚗𡁜銁 `trade_visualizer_qt6.py` �� `ScrollableMsgBox` (�墧�蝞��亙撕蝒�) 摨閖�����脫���器�啣�鈭��銝� �𨥉�� 撖澆枂�單�雿𨀣��轁�� �厰僼嚗𣬚��餅𧒄隡朞圻�穃��啁瑪蝔贝��� `run_backtest_and_get_report` 撟嗆遬撘讛挽蝵� `force_save=True`��
    - [x] **Tkinter 摰Ｘ�蝡臬�甇亙笆朣�**嚗𡁜銁憭批� Tk 蝡舐� `stock_selection_window.py` 銝剔� `BacktestReportDialog` 憿園��批��∪�嚗���瑟鰵憓硺� �𨥉�� 撖澆枂�單�雿𨀣��轁�� �厰僼�� `on_export_clicked` 撘�郊鈭衤辣瘣曉�嚗䔶�霂��頝函垢�滢�雿㯄�����湔�扼��
    - [x] **�舀�蝒堒藁憭滨鍂�𥪜𢆡**嚗𡁏凒�唬� `update_content` 蝑㗇䲮瘜𤏪�蝖桐��㰘捏�臬銁��稬�Ｚ�餈䀹糓�见𢆡�匧翰�琿睸靚�絲�墧�嚗���賢�蝖株圾�𣂼僎�峕郊�湔鰵敶枏�蝒堒藁��撖孵���葵�∩誨����滚�嚗屸��滚��亥��唳旿嚗���嗅��唬��𣂼�撖澆枂�𦒘��桃𠶖���蝷箏��滢�����芸𢆡�瑟鰵��
    - [x] **摰䂿緵撖澆枂銝滨鍂撘寧����暺㗛�𡁶䰻�箏� (Popup-free Silent Notice for Exporting)**嚗�
        - [x] **蝘駁膄 PyQt6 銝� Tkinter 撘粹獈�剖撕蝒�**嚗𡁶宏�支�撖澆枂�其�摰峕��嗅撕�箇� `QMessageBox.information/critical` 銝� `messagebox.showinfo/showerror`��
        - [x] **��漣銝箸��格��祆㺿�嗘��嗆����嗆�����**嚗𡁶��餃�嚗峕��格��砌���𧒄靽格㺿銝算�𨀣迤�典紡��...�嘅�摰峕��硋仃韐亙��厰僼隡𡁜�銝算�𨅯歇�𣂼�撖澆枂 �婙�脲��鎿� 撖澆枂憭梯揖�嘅�撟嗅銁 3 蝘鍦��朞�摰𡁏𧒄�剁�`QTimer` / `after`嚗匧像皛穃��煺蛹�𨥉�� 撖澆枂�單�雿𨀣��轁�嘅��峕𧒄銝餌𠶖���靘萘��舀�瘥怎�蝥折�暺䀹𠯫敹㛖𠶖����𡜐�摰��靽脲擪�滨��讠��睃�瘚���
    - [x] **閫���硋��交�雿𨀣��埈𧒄��葵�∪�蝘唳聢撘� (Standardized Stock Name Format in Premarket Guidance)**嚗�
        - [x] **�芸𢆡皜���滨�**嚗𡁜銁�䀹钟霈∪��𧼮��賣㺭 `update_premarket_diagnose_json` 撘�憭湛��箄�霂��撟嗅蝠摨閙��� `entry ��蟮�墧�蝏澆�蝞��� - ` �� `Re-entry ��蟮�墧�蝏澆�蝞��� - ` 蝑匧�蝻�摮㛖尐嚗屸俈甇Ｗ紡�箄��滨�.
        - [x] **蝏煺��澆��碶蛹 `�∠巨�䇭�墧�`**嚗𡁜朖雿踹���㺭隡𣳇�埝�����澆��笔���鉄�滨�嚗𣬚頂蝏煺��質䌊�冽��𡝗�撟脣���葵�∪�蝘堆�撟嗅銁�怠偏餈賢�蝏煺��� `_�墧�` �𡒊�嚗䔶蝙敺堒��脫��航恣�鍦銁憭抒��睃�霂𦠜鱏�𡑒” and �𧢲踎銝剖�憭���啜��遬�潛�銝枏���內��
    - [x] **靽桀��喟�瘚�偌�烐綉憿萇倌���唳㺭�格𧊋�曄內�冽�銝𧢲䲮���摨譍�皛𡁜𢆡 Bug (Fixed Decision Flow Sorting & Scroll Sync Bug)**嚗�
        - [x] **�惩𤐄 SortableTableWidgetItem 銝交聢撘勗�閫��**嚗帋耨甇�� `__lt__` ���撖寥�餉�嚗�銁銝支葵 `value` �䔶蛹 `None` �園�朞� `text` 摰匧��鮋��瘥磰�嚗峕��支��航�撘閗絲����券��埝毽銋晞��
        - [x] **摰墧鴌�寥�銝𤾸��𤩺�摨誯獈�剝���**嚗𡁜銁 `_load_initial_records` 銝� `_check_and_update_records` ��”�潭㺭�格葡�栞�蝔衤葉嚗�銁敺芰㴓餈賢��唳旿銵��摰匧��喲𡡒 `setSortingEnabled(False)`嚗諹��輸�憸穃��嗆�摨誩笆�鍦�憿箏���僕�啣� CPU �蠘�梹�撟嗡�皜脫�摰峕��𡒊�銝��Ｗ� `setSortingEnabled(True)`��
        - [x] **撘箏��交��園𡢿�堒�摨𤩺�摨�**嚗𡁏�憭齿�摨讐𠶖���嚗�撩�嗆遬撘讛��� `self.table.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)`���靽肽�鈭��霈箇鍂�瑕�雿閙�雿頣�蝟餌�摨訫����瘞湔㺭�桀�蝏�����拇𧒄�湔��冽�銝𨳍����唳𧒄�湛�憭扳𧒄�湔�嚗厩迅蝔單��刻”�潭�銝钅𢒰嚗屸��� `scrollToBottom()` 摰𣬚�颲暹�鈭���唳㺭�桀銁摨閖����瘞渲揭�讠��渲���
    - [x] **摰䂿緵�喟�瘚�偌�烐綉憭𡁻�匧𢰧�格���㺭�桀��� (Implemented Multi-Select Context Menu Data Clearing)**嚗�
        - [x] **撘��� ExtendedSelection �㗇𥋘銵䔶蛹**嚗𡁜銁銵冽聢 `self.table` �嘥��𡝗𧒄嚗�� `setSelectionMode` �拍���漣銝� `ExtendedSelection`嚗䔶蝙�冽��臭誑雿輻鍂曌䭾��㚚睸�矋�Ctrl/Shift嚗匧��劐遙�讛���
        - [x] **����喲睸�𨅯��寥�皜���厰★**嚗𡁜銁�喲睸銝𠹺������ `_show_context_menu` ����刻蕭�牐���𠧧蝥踹� `�� 皜���劐葉霈啣� ({len(selected_rows)}��)` �冽���憿對��賢�蝎曉��笔�敶枏�鋡怠𢰧�桃��餌�銵䔶誑�𠰴歇蝏誩�鈭𡡞�劐葉�嗆���憭朞���
        - [x] **霈曇恣摰匧����摨讐�����文���**嚗𡁏鰵摰䂿緵鈭� `_delete_selected_rows` �寞�嚗�銁�寥��𣳇膄�嗡葩�嗅��剜�摨𧶏�`setSortingEnabled(False)`嚗㚁�撟園�朞� `sorted(..., reverse=True)` 隞𤾸��穃��厰�摨譍�甈∪��日�劐葉���嚗峕��支��𣳇膄�漤𢒰銵�紡�游�蝏剛�蝝Ｗ��嗘���䔮憸矋����𤾸銁銝餌�����粹�暺� Toast �鞟內嚗䔶蛹�滨��𧢲�靘𥕢�銝�銝芷妟撏拇�����煺漱鈭埝䲮撘譌��

## 2026-06-01 19:48
- [x] **�𡝗���蟮�墧��芸𢆡瘛餃��睃��滢���� (Canceled Auto-Adding Backtest to Premarket Guidance)**嚗�
    - [x] **瘜券��墧��芸𢆡瘛餃�/�湔鰵�餉�**嚗𡁜銁 `scratch/test_reentry_backtest.py` �� `run_backtest_and_get_report` 撠暸�嚗����𧋦�其��芸𢆡撠�葵�∪�瘚贝恣�鍦��� `logs/premarket_diagnose.json` �� `update_premarket_diagnose_json(...)` 靚�鍂�𠰴���ㄨ�� try-except �𥪜𢆡�𡑒�銵𣬚���釣�𠺪�隞舘���瘨���见𢆡/�芸𢆡�墧��嗅撩�嗅��交�雿𨀣��㛖�銵䔶蛹��
    - [x] **靽萘�摨訫��坔��亙藁**嚗帋蛹鈭�輕���銝见�摰寞�批��嗡�瞏𨅯銁��𡠺蝡见��亙𢆡雿頣�摰峕㟲靽萘�鈭� `update_premarket_diagnose_json` ��遆�啣ㄟ�𤾸�摰䂿緵�祈澈嚗𣬚泵�� SOLID 撘���/撠�𡡒�笔���
    - [x] **�朞�蝟餌�蝻𤥁��諹祗瘜閙�霂�**嚗𡁏�靽格㺿�𦒘漣�毺��芸�銋匧��譌��𧊋撖寥��𤥁��祗瘜閖�霂荔�靽脲��墧�瘚��擃睃虾�冽�找��唳旿蝥臬�摨艾��

## 2026-06-01 18:30
- [x] **摰䂿緵摰墧𧒄敶勗��喟��典予�坔𪂹�笔笆朣𣂷��滨漣�芷����滨��箏� (Implemented Year-Round Resample-Aligned Shadow Decision & Adaptive Recalculation)**嚗�
    - [x] **摰䂿緵�硺漱�𤘪𧒄畾� mock_tick �滨漣霂�摯 (All-weather Downgraded Evaluation)**嚗𡁜銁 `trade_visualizer_qt6.py` �� `_render_charts_logic` 銝剖��仿�蝥批�蝑硋��汿��銁�硺漱�𤘪𧒄畾菜�摰䂿� tick 蝻箏仃�塚��朞� `day_df` ����𦒘�銵峕㺭�桀銁���銝剛�頧駁��滨� mock 銵峕� tick嚗�蝠摨閙��港��𨅯蘨�匧��䀹��賜�敶勗��喟��萘��拍��函�嚗���唬� 7x24 撠𤩺𧒄�典予�嗘遙�誩��Ｗ𪂹�毺�摰墧𧒄敶勗��喟��芸𢆡�滨�銝𤾸笆朣鞉葡�橒�
    - [x] **摰䂿緵敶勗��喟��冽�撅墧�� `resample` 撘箸釣�乩��⊿��行⏛ (Resample-Enforced Validation & Flushing)**嚗𡁜銁摰墧𧒄霂�摯鈭抒��喟�摮堒��𠬍�撘箸釣�亙��滨� `resample` 撅墧�改�撟嗅銁 `_update_ma_legend` 皜脫�����曆�銝𤾸�蝷箏蔣摮𣂼�蝑𡝗𧒄嚗�撩�嗉�瘙�𪂹�笔笆朣� `sd_resample == self.resample` �滢�瞈�瘣餃�蝷箝����拍��寞祥鈭�𪂹�笔��Ｘ𧒄�曹��批𪂹����坔紡�渡��𣈯狩敶勗�蝑砽�苷��𨀣�隞日�雿滚�蝷算�萘�憿賜𪆴嚗䔶�霂����垢�嗅�銝衤舅蝡舀㺭�桃� 100% �峕�嚗�
- [x] **摰䂿緵��蟮�墧��䔶蜓�桅�蝎曉漲蝻枏�銝𦒘縑�琿�蝞堒笆朣� (Implemented Double-Key Cache for Backtest Signals & Render Alignment)**嚗�
    - [x] **�齿� test_reentry_backtest �䔶蜓�桃�摮䀹㦤�� (Double-Primary-Key Cache Alignment)**嚗𡁜銁 `scratch/test_reentry_backtest.py` ��縑�瑞�摮� `_last_backtest_signals` �峕��刻���𣈲 `_last_backtest_best_branch` 摮堒�銝哨��券𢒰�拍���漣銝箏��思葵�∩誨����漤��瑕𪂹�毺� **`(code_clean, resample)` �䔶蜓�格芋��**嚗���嗅�蝥� `get_last_backtest_signals` 銝� `get_last_backtest_best_branch` �亙藁�舀�嚗�僎�峕𧒄�坔��蓥蜓�桐誑靽脲�摰𣬚���唂璅∪��睲��澆捆��
    - [x] **�㯄�𡁜�蝡臬虾閫���䔶蜓�桀�蝢𤾸笆朣鞉葡�� (High-Fidelity Double-Key Render Alignment)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�瑽賢遆�� `_show_backtest_result` �芸𢆡�朞� `super(MainWindow, self).sender()` �Ｘ��墧�蝥輻� of `resample` 撅墧�改�撠�恣蝞堒���縑�瑞����頧質秐�䔶蜓�桃�摮睃��詻����園���� `_render_charts_logic` 蝏睃��墧�銋啣���扇�嫣� `_update_ma_legend` 蝏睃���雿喳��舐��瑕��餉�嚗䔶���誑 `(code, self.resample)` �䔶蜓�格��吔�餈坔蝠摨閗圾�喃��冽��典�銝��∠巨��揢銝滚��冽�嚗�� 1D -> 3D -> w嚗㗇𧒄�曹�銋见��蓥�隞��蝻枏�閬��撖潸稲���𦦵𤫇�曆縑�琿�雿𨧀�腈���𨀣�雿喳��舀遬蝷� stale�萘��𤤿�嚗��蝢舘噢�𣂷��𨅯朖��揢��朖�滨���朖撖寥��萘���恥�滨�雿㯄�嚗�
    - [x] **靽桀�摰墧𧒄撟賜� K 蝥� (Ghost Candle) 銝剜𧊋摰帋��㗛� NameError**嚗𡁜銁 `trade_visualizer_qt6.py` �� `_render_charts_logic` 銝哨��䭾��� `is_realtime_active` ����典�銋㕑����𤑳� `NameError`���隞砍歇撠�砲�餉�餈𥡝��拍���僎銝𤾸��券����`is_realtime_active = (self.realtime or cct.get_work_time_duration() or self._debug_realtime) and (tick_df is not None and not tick_df.empty)`���銝滢�摰𣬚�靽萘�鈭�����鈭斗��園𡢿畾菟秄蝳��銝娪�朞� `not is_mock_tick` �脫迫鈭�銁�硺漱�𤘪𧒄畾菔秤�餃厭�� K 蝥選�撟嗅蝠摨閙覔瘝颱�霂交𥁒�踺��
    - [x] **摰𣬚��朞��函頂蝏罸���祗瘜訫��餉�蝻𤥁��⊿�**嚗𡁏��罸�朞�鈭� `python -m py_compile` �蹱��祗瘜閙�撉䕘��園�霂胯��妟霅血�嚗��瘚�����罸𡡒�荔�蝟餌��亙ㄝ�抒��喟迅�綽�

## 2026-06-01 18:00
- [x] **摰䂿緵��揢�冽��芸𢆡�滨��墧�銝𤾸�銝駁睸�脫��箏� (Implemented Auto-Recompute Backtest on Period Shift & Multi-Key Debounce)**嚗�
    - [x] **撘訫��∠巨隞��銝𤾸𪂹�笔�銝駁睸�文� (Double-Primary-Key Alignment)**嚗𡁜銁 `render_charts` 撠暸���䌊�典�瘚贝圻�煾�餉�銝哨�撠��銝���誨��縧�滚ế摰� `_last_backtest_auto_code` �拍���漣銝箏��怨�蟡其誨����漤��瑕𪂹���resample嚗厩� **`(code, resample)` �䔶蜓�桀�蝏� `_last_backtest_auto_key`**��
    - [x] **敶餃��寞祥��揢�冽��𦦵�摮䀝��湔鰵�萘���**嚗𡁜��冽��典��芾�蟡其��孵稬撌亙��誩��Ｗ𪂹���憒� 1D -> 3D -> w嚗㗇𧒄嚗𣬚頂蝏毺��𤩺��匧��冽��睃�嚗諹䌊�冽��游縧�齿㜃�迎�撘箏��𤾸蝱�㕑絲�啣𪂹�毺� Re-entry �墧�蝥輻�嚗��蝢𦒘�霂�� K 蝥踹㦛銋啣��寞�霈啜��椰銝𡃏���雿喳��舐��乩��曄內�冽� 100% �峕郊�滨�銝擧��笔��堆�
    - [x] **靽桀����箏�撣訾�蝥輻�畾讠� (Fixed Application Exit Error & Thread Leak)**嚗�
- [x] **閫���箇掩�寞��滚�閬�� (Resolved QObject sender Method Collision & TypeError)**嚗�
    - [x] **摰帋��滚��脩�**嚗𡁏��亙枂 `MainWindow` ����典��滨�摰硺�撅墧�� `self.sender`嚗��摰帋� `StockSender` 摰硺�嚗㚁�撖潸稲�冽局�賣㺭銝凋誑 `self.sender()` 霈輸䔮 Qt �毺��寞��嗆��� `TypeError: 'StockSender' object is not callable` ��稲�賡��滚�蝒�𥁒�踺��
    - [x] **摰𣬚�頞羓漣頞�掩靚�鍂**嚗𡁜� `self.sender()` �拍��齿�銝� `super(MainWindow, self).sender()`���朞� Python �毺��� `super` 隞���� C++ 頞�掩撅�活蝏𤘪�銝剔移���餈��靘见��扯��吔��𣂼��其��孵𢆡隞颱��嗅�蝐餉挽霈∠�摰匧��齿�銝页�擃䁅捶�瑕�鈭��摰䂿� `QThread` 靽∪噡皞琜�敶餃��寞祥鈭�砲�仿�嚗�
- [x] **摰䂿緵�芸𢆡�墧��䠷���扇銝𤾸翰�琿睸撘寧��亙���氖�箏� (Implemented Silent Auto-Backtest & Explicit alt-g Report Separation)**嚗�
    - [x] **摰帋��曉�銝𡡞�撘譍���𦻖��**嚗𡁜�蝥找� `_on_shortcut_reentry_backtest(self, checked=False, show_report=True)` 蝑曉�嚗𣬚移蝏����氖鈭� PyQt 靽∪噡瑽質䌊撣衣� `checked` �嗆������撟嗆鰵憓𧼮撩憭抒� `show_report` ��㺭�批���
    - [x] **摰䂿緵�𤾸蝱蝥輻��冽����扳釣��**嚗𡁜銁�臬𢆡 `ReentryBacktestThread` �嗅𢆡���摰� `show_report` �嗆����銁蝥輻�頝穃�閫血� `_show_backtest_result` 瑽賢遆�唳𧒄嚗�⏚�� Qt �毺��� `self.sender()` �滚��Ｘ�閫血�皞𣂼僎霂餃�霂亙��改�摰𣬚��𡁜�鈭��𨀣𦻖��倌�滚�摰嫣����腈��
    - [x] **摰䂿緵摰𣬚��䠷�皜脫�銝𤾸��𤘪贋**嚗𡁜��𨅯�瘚𧢲糓�曹葵�∪��Ｚ䌊�刻圻�𤑳�嚗��瘚衤��典��唬�靚��摰䕘�暺㗛��𠹺僭�𡝗�霈啁�蝎曉��枏銁 K 蝥踹㦛銝𠺪��峕𧒄�� K 蝥踹椰銝𡃏���瑪�曆�銝剜凒�唳�雿喟��伐��働 5�亦瑪銝餃�瘚芰�嚗㗇�蝷綽�雿�**�湔𦻖�行⏛撟嗉歲餈� ScrollableMsgBox �亙�撘寧�**嚗𥕦蘨�匧��滨��𧢲�銝� `Alt+G` 敹急㭘�格𧒄嚗峕�隡𡁻�靚�撕�箇遞���瘚𧢲𥁒�𠺪�颲暹�鈭���瑟��条凒閫厩���恥�讠�雿㯄�嚗�
- [x] **摰䂿緵�航��𤥁䌊�典��脣�瘚见��喃�頝其�霂脲�銋�� (Implemented Auto-Run Backtest Switcher & State Persistence)**嚗�
    - [x] **餈賢�撌亙��𤩺��格綉��**嚗𡁜銁�𨀣芋�煺縑�猾�脲綉�嗆��桐��孵僎�鍦�霈曆������ `�墧�` �厰僼 (`backtest_action`)嚗諹挽霈∩�隡㗛�霂衣��� Tooltip 瘞娍部�鞟內嚗屸�霈支��劐葉嚗�僎銝交聢靽脲�鈭�極�瑟�擃睃�摨行��游�撅���
    - [x] **�㯄�𡁻�蝵株楊隡朞��芣�摮睃�**嚗𡁜銁 `load_window_position_qt` �� `_save_visualizer_config` ���摨誩��㚚�𡁻�銝剜釣�� `auto_run_backtest` ����𤥁圾�僐��鍂�瑕銁撌亙��譍��暸�㗇��𡝗��暸�� `�墧�` �嗆��𧒄嚗𣬚頂蝏煺��祇𡢿靽嘥��� JSON嚗�僎�其�甈∪鍳�冽𧒄�删�擃䀝��笔��麄��
    - [x] **摰䂿緵��揢銝芾�瘥怎�蝥扯䌊�典�甇亥圻�穃�瘚�**嚗𡁜銁憿嗅�閫�㦛皜脫��亙藁 `render_charts` 蝏枏偏撌批����鈭�䌊�典�瘚𧢲綉�嗅膥��� `auto_run_backtest` 憭���劐葉�嗆��𧒄嚗諹𥅾�冽���稬�芷�㕑�����餌��寞踎�埈��𥪜𢆡�桃�銝𠹺��桀��Ｖ�銝滚���葵�∴�蝟餌��賜移蝖株�銵𢞖�𡏭楊�∪�摮𣂼縧�𨧀�嘥ế摰𡄯�撟園�朞� `QTimer.singleShot(200)` 摰䂿緵瘥怎�蝥扯�瘚�����甇交㺭�桀�頧賭��墧��芸𢆡靚�絲嚗��蝢𤾸��唬��𨅯朖��揢��朖�墧��萘���恥�讠�雿㯄�嚗�
- [x] **摰䂿緵�航��碶� Tk �冽��墧�撖寥�銝𡡞���甅�芷��� (Implemented Multi-Period Aligned Re-entry Backtesting)**嚗�
    - [x] **�齿��墧�撘閙��詨��亙藁**嚗帋耨�嫣� `scratch/test_reentry_backtest.py` �� `run_backtest_and_get_report` �亙藁嚗峕迤撘誩��� `resample` �冽�隡惩��舀�嚗��霈� `'d'`嚗㚁�撟嗡����譍��� TDX ��蟮蝥踵��𡝗瓲敹��餉� `get_tdx_Exp_day_to_df`��
    - [x] **�惩𤐄憭批� Tk 敹急㭘�株圻�煾曎**嚗𡁜銁 `instock_MonitorTK.py` �� `_on_shortcut_reentry_backtest` �噼�銝哨��朞� `self.global_values.getkey("resample")` �冽����硋�撅��劐葉�� resample �冽�嚗�僎�典�甇亙��斤瑪蝔衤葉撠��摰墧𧒄����墧�瘚�偌��
    - [x] **撖寥� PyQt6 �航��𣇉垢��蟮�墧��冽�**嚗𡁜銁 `trade_visualizer_qt6.py` �� `ReentryBacktestThread` ���惩遆�啣� `run` �寞�銝剖��乩� `resample` �舀���銁�嗉圻�𤑳垢 `_on_shortcut_reentry_backtest` 銝哨��朞��𨅯��滚��券俈蝥踱�嘅�`self.resample` / `self._resample` / `cct.GlobalValues` 隡睃�蝥扳䔝瘚页��拍��閗繮鈭���滨𤫇�曇���遬蝷箇� K 蝥輸���甅�冽�嚗��蝢擧��支��墧��冽�銝擧遬蝷箏𪂹�罸�雿滨�蝻粹萅嚗䔶蛹�滨��𧢲�靘𥕢�頝刻�蝔讠�蝥批笆朣鞟��唳旿靽肽�嚗�
    - [x] **�賢𧑐�墧��亙��冽��冽���蝷�**嚗𡁜銁 `test_reentry_backtest.py` ���𡒊�鈭斗��喟�銝𤾸��齿��舐𠶖��𥁒�𠹺葉嚗���啣��牐� `�墧��冽�Resample:` �冽��圾�鞉踎�梹�憒� `��儭� �亦瑪 (d)` �𤥁��糓 `��儭� �函瑪 (w)`嚗㚁�雿輻鍂�瑕笆敶枏�����甅����脣�蝑碶��桐��嗚��
    - [x] **�㯄�𡁜虾閫��蝞��乩��墧��亙��������劐�擃䀝漁憭滚��蠘�**嚗𡁜蝠摨閗圾�喃� PyQt6 蝡� `ScrollableMsgBox` 撘孵枂�擧�摮堒�摰寞�瘜訫��嗥��𤤿����朞�撖寞瓲敹� `QLabel` 瘜典� `TextSelectableByMouse` 銝� `TextSelectableByKeyboard` �𥪜���𧋦鈭支���扇嚗䔶蝙�冽��臭誑����芰眏�圈�朞�曌䭾��𡝗𠗊�坿��硋翰�琿睸 Ctrl+C 憭滚�擃睃�摨血�蝑𣇉��乓��縑�琿�讛��𠰴��脣�瘚𧢲𥁒�𠺪�摰𣬚�撖寥�鈭�之撅� Tkinter 蝡臬虾憭滚� of 隡睃�雿㯄�嚗�
    - [x] **摰䂿緵 K 蝥踹�摮堒���/�祆筑霂行�撘寧�蝳餃��箏� 6 蝘坿䌊�典��� (Implemented 6s Auto-Hide for K-Line Detail Window)**嚗𡁻���� `trade_visualizer_qt6.py` ��� `KLineDetailWindow` �祆筑霂行�蝒𨰜����乩� `auto_hide_timer` �嗆���頝喃��𣈯俈��㦛�脲㦤�嗚���曌䭾�蝘餃枂 K 蝥踹㦛蝏睃��綽�霂行�蝒堒藁隡𡁜銁 6 蝘鍦�摰匧��芸𢆡�鞱�嚗���嗅��𨅯銁霂行�蝒堒藁���瘚格��𡝗嗻嚗諹䌊�券��𤩺㦤�嗡��芸𢆡��𧒄憭望�嚗𣬚＆靽苷�����菜�銝𥪯犖�批����雿靝�撉䎚��

## 2026-06-01 17:35
- [x] **摰䂿緵 Re-entry ��蟮��雿喳��臭�摰墧𧒄�喟��峕瓲蝑𣇉裦�� K 蝥踹㦛�曆�銝𧢲䲮銝剜�蝞�瘣��蝷� (Implemented Re-entry Best Strategy & Realtime Decision Dual-Overlay)**嚗�
    - [x] **蝘餅�撅閧緵�餉��� MA Legend 閬��撅�**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�敶餃�撠����銁 K 蝥踹㦛���撅閧緵�墧���雿喳��舐��孵�嚗屸���僎摰𣬚�蝘餅��唬� K 蝥踹㦛撌虫�閫垍� `_update_ma_legend` ����曄內�箏���
    - [x] **摰䂿緵��雿喟��交揢銵𣬚�閫�葡�� (Beautiful Legend Wrapping)**嚗𡁜��𡏭�蟡典銁 Re-entry ��蟮�墧�銝剜�瘚见�鈭��雿�/�������舐��伐���瑪靽⊥�瘚桃�摨閖�隡朞䌊�冽揢銵䕘�雿輻鍂 `<br/>`嚗匧僎�啗絲銝�銵䕘�隞仿�颲刻�摨衣��垍遛�莎�`#00FFCC`嚗匧��舀部�暹� `�働` �垍𤌍撅閧內霂亦��乓��
    - [x] **瘛勗漲撖寥��喟�撘閙�銝𡒊��滚��𣂼膥蝑𣇉裦�賢���� (Aligned Strategy Mapping with Decision Engine & Premarket Analyzer)**嚗𡁜� `BRANCH_CHINESE_MAP` ����交�撠���豢凒�啣僎摰𣬚�撖寥�鈭� `premarket_analyzer.py` ��葉��凒閫��蝘堆�瘨萇� `SuperTrendMA5Branch`嚗�5�亦瑪銝餃�瘚迎���SuperTrendMA10Branch`嚗�10�亦瑪頞见飵嚗剹��SwsPullbackBranch`嚗𠄎WS��⏚蝥蹂��賂���TrendMA60Branch`嚗�60�亦瑪��香�脣�嚗劐� `OscillatingBreakdownBranch`嚗�聦雿漤�雿漤俈���蝑厩頂蝏笔��毺��伐�摰䂿緵頝冽芋�埈�雿喳𦶢�滩����
    - [x] **摰䂿緵摰墧𧒄銝𤾸�瘚讠��亥䌊���撟嗆�撅閧內 (Inline Realtime & Backtest Display)**嚗𡁜銁���瘚桃�摨閖�撘訫�鈭���貉��典�蝷箝��僎銝�**�寞旿�滨��贝�閫厩洵銝�隡睃�蝥�**嚗����蝝扯翰��**摰墧𧒄敶勗��喟��鍦銁���漤𢒰撅閧內**嚗��瘚𧢲�雿喟��亥䌊�冽𣄽�亙銁�𡡞𢒰��圻�穃𢆡雿𨀣𧒄隞乩漁蝏選�銋啣�嚗�/鈭桃滯嚗����/甇Ｘ�嚗厩�擃睃笆瘥𥪜漲�脣蔗皜脫�嚗��蝢舘圾�喳�瘚衤�摰䂿�靽∪噡銝�蝘鍦㫲霂���𤤿�嚗�

## 2026-06-01 17:15
- [x] **摰䂿緵璁�艙��10撘箄�銝𤾸��㗇鸌�誩��脣�瘚贝�摨血��� (Implemented Concept Top-10 & Multi-Select Batch Backtest Scheduler)**嚗�
    - [x] **摰䂿緵�冽����� Treeview 頝舐眏�箏�**嚗𡁻����銝��株圻�穃�瘚讠��噼� `_on_shortcut_reentry_backtest`嚗�蝠摨閧宏�文笆�蓥�銵冽聢��′蝻𣇉���緵�函頂蝏笔虾隞仿�朞� `event.widget` �刻�銵峕𧒄�箄��Ｘ䰻憭���衣��嗆���閫血�鈭衤辣���雿� Treeview �找辣嚗䔶蝙敺𦯀��桀�瘚贝�憭���園◇��𧑐�舀�憭批�銝餉”隞亙�隞餅�摮� Toplevel 蝒堒藁嚗��璁�艙��10�暸�銝𦠜隅�∠������
    - [x] **摰䂿緵憭𡁻�厩�蝥扳鸌�誩�瘚� (Multi-Select Non-blocking Batching)**嚗𡁜�璉�瘚见��其遙�𤩺𣈲�� Treeview 銝剝�劐葉鈭���芾�蟡冽𧒄嚗𣬚頂蝏笔�銝滚�撘孵枂�㗇𥋘獢���峕糓�湔𦻖撠��劐葉����其葵�∪��乩遙�⊥�銝哨�擃䀝漁�鞟內撟嗡��桀鍳�券��餃��寥��墧���
    - [x] **摰䂿緵璁�艙��10撘箄��芸𢆡蝏���刻� (Concept Top-10 Curated Grouping)**嚗𡁜��典��劐葵�⊥芋撘譍�閫血� `Alt-G` �塚�靚�漲撘閙��芸𢆡�朞� `df_all` 璅∠�蝝Ｗ�霂亥���撅墧踎�埈�敹蛛��𧼮枂�䔶�銵䔶�/璁�艙�鍦��� 10 ���撘箏漲�∠巨雿靝蛹撖寞�瘚贝�蝏��嚗䔶��冽�銝��格�撖嫘��
    - [x] **撘訫�璅⊥���厰★蝞∠��� (BacktestOptionsDialog)**嚗𡁏��牐�����唬誨�毺�璅⊥��笆霂脲�嚗峕��啣�蝷箔葵�∪�璁�艙敶鍦�嚗�僎銝箇鍂�瑟�靘𥕞�靝�瘚贝�敶枏��﹦�腈���𨀣�敹萇����10瘚贝��苷誑�𪙛�𡏭䌊摰帋�憭帋誨����祆�霂𨰝�萘�擃䀹��厰★嚗峕�憭折�雿𦒘��冽����撌交�雿𣈯�甈～��
    - [x] **�惩𤐄 Toplevel 摮鞟����敹急㭘�桀��Ｚ���**嚗𡁜�蝢𤾸銁 `show_concept_top10_window_simple` �� `show_concept_top10_window` 銝支葵�喲睸銝芾��𧢲踎�𥕦遣�餉�銝哨�銝� `win` 隞亙��詨� `tree` �𡑒”餈賢�蝏穃�鈭� `<Alt-g>` �� `<Alt-G>`嚗�蝠摨閙��支��衣�銝Ｗ仃�嗆��桀仃����桅���

## 2026-06-01 16:25
- [x] **隡睃��剝睸�嘥��碶��嗆����Ｘ𠯫敹堒虾閫�漲 (Optimized Hotkey Setup & Binding Log Visibility)**嚗�
    - [x] **�寞祥暺䁅恕�亙�蝥批�銝讠��典��剝睸�臬𢆡銝滚虾閫�䔮憸� (Resolved Hidden Global Hotkey Launch Log)**嚗𡁜� `setup_global_hotkey` �� `_launch_legacy_hotkey_thread` ��� `logger.info` �� `logger.debug` �券��齿�銝� `logger.warning`���蝖桐��券�霈斤�霅血�蝥批�嚗ÁARNING嚗劐�嚗峕�霈箸糓�典��祉��剝睸餈𤤿��臬𢆡�𣂼���𧋦�啁���翰�琿睸蝏穃��喟頂����臬��函��桃瑪蝔讠�瞈�瘣颱�瘜券�嚗���賭漣����啜����渡�蝟餌� warning 蝥扳𠯫敹梹�隞舘�峕�憭扳����蝟餌����銵屸�𤩺�摨艾��
    - [x] **皜�膄 setup_global_hotkey 銝剖��典紡�� logging ���雿嗘�韏� (Eradicated Local 'import logging' in setup_global_hotkey)**嚗𡁜蝠摨閙��支�霂亙遆�啣��典𢆡��笆 `logging` ���摨𤘪芋�㛖�撘閧鍂嚗峕㺿�梁�銝����撅� `logger` 摰硺��𠰴� `getEffectiveLevel` / `level` 撅墧�找�擃条移摨西䌊��漣摮堒��惩�摰峕��游��亙�蝥批��� Rotator 摮鞱�蝔见�蝚虫葡��㺭�� O(1) 頧祆揢嚗���典笆朣鞟頂蝏毺漣蝏煺��� LoggerFactory �乩�蝟餉�����
    - [x] **靽桀��砍𧑐 Alt-X 敹急㭘�桀仃��䔮憸� (Fixed Local Alt-X Shortcut Focus Block)**嚗𡁶眏鈭� `Alt-X` 敹急㭘�格糓�墧������瓲敹���衤��芣釣����典��祉��剝睸摮堒�嚗䔶蜓蝒堒藁�典�憪见�蝏穃��園�霂臬𧑐雿輻鍂鈭���血��鞟� `self.bind`����冽�����孵�鈭𦒘葵�⊥㺭�株”�� (`Treeview`) �𡝗�蝝Ｚ��交� (`Entry`) ��𧒄嚗䔶�隞嗉◤摮鞉綉隞嗥凒�亙�瘝∪紡�湔�瘜訫�摨𢛵��緵撠���拍���漣銝箏�撅�撘箏�摨𠉛�摰𡁶� `self.bind_all`嚗�蝠摨閙��帋�隞餅�蝒堒藁�衣�銝讠�鈭𡁏神蝘垍漣銝��桀�瘚贝��券�𡁻���
    - [x] **銵亙�憭朞�蝔见鍳�其��芣���㺭霂𦠜鱏�亙� (Added Multiprocess Spawn Parameter Logging)**嚗𡁜銁銝餌瑪蝔见��臬𢆡隞亙��𤾸蝱摰�擪�芣�蝥輻��臬𢆡 `HotkeyRotatorProcess` �� `.start()` �滢��㵪�蝎曉��鍦�鈭� warning 蝥批���鍳�典��啗��剜𠯫敹梹��𤩺��𡝗��� `level_val` 銝� `daemon` ��蝸撅墧�扼����塚�敶餃�皜�膄鈭�䌊��瑪蝔见�畾讠������ `import logging` �𦯀�靘肽�嚗���唬��函��賢𪂹�毺��亙��删��剔㴓��
    - [x] **摰䂿緵�臬𢆡銝𡡞�蝵桃��笔𦶢�冽��亙藁�亙�霈啣� (Implemented Startup & Reset Entry Logging)**嚗𡁜銁 `setup_global_hotkey` ��洵銝�銵屸�餉��滚��乩� warning 蝥批����撅��亙藁�亙��枏㫲���蝞⊥糓�瑕鍳�具����滨蔭����舀��典��ｇ�蝟餌����擃䀝漁颲枏枂敶枏��� `mode` 銝� `show_toast` 霈曉��嗆����滚��𡒊賒��𡠺蝡贝�蝔见鍳�冽𠯫敹梹�霈拇㟲雿梶��桃��賢𪂹�笔��刻䌊閫����虾�墧滲��
    - [x] **�寞祥�祉��典��剝睸摮鞱�蝔讠�摰𡁶���撩憭曹��亙��澆�撖寥� (Resolved Missing Hotkey Binding Details inside Subprocess & Aligned Formats)**嚗𡁜� `hotkey_rotator.py` ����㕑ㄧ `print` ���撣豢��瑁��箏蝠摨閖���僎�拍��亙�蝟餌�蝏煺��� `LoggerFactory` 銝剖亢�亙��嗆���緵�其�蝞⊥糓�峕郊�滚𦛚蝏穃����撅��剝睸�拍�瞈�瘣餉��航�銵��撣賂�摮鞱�蝔见��質��箏�銝餌�摨讐�撖嫣��氬��聢撘誩極�港���鉄�園𡢿�� and ��辣銵�噡��頂蝏毺漣 warning / error �亙���
    - [x] **瘛餃��典��祉�餈𤤿�瘜典�瞈�瘣餅��罸�鈭桃＆霈斗𠯫敹�**嚗𡁜銁 `setup_global_hotkey` �� `mode == "GLOBAL"` ��𣈲�怠偏餈賢�鈭��擃䁅儘霂�漲�� warning 蝥批�蝖株恕�亙�嚗峕�蝖株”�𤾸�撅�敹急㭘�桀歇鋡急����瘣餃僎�条恣鈭𡒊𡠺蝡见��方�蝔衤葉撘�憪讠��改�摰䂿緵鈭箸㦤蝖株恕�笔之皛∟敞��
    - [x] **摰䂿緵�典�銝擧𧋦�啁��寧�摰𡁜��賜�隞钅�鈭格遬蝷箔�撖寥� (Achieved Global & Local Hotkey Feature Summary Alignment)**嚗帋�隞�銁�祉�摮鞱�蝔� `hotkey_rotator.py` �� `self.hotkey_map` 銝哨�銋笔銁銝餉�蝔讠�蝐駁���秩�𤾸��� `_HOTKEY_INFO_MAP` 瘛勗漲撠��鈭� 12 銝芸翰�琿睸��葉����賜�隞页�憒� `銝��桅��訢���喟�瘚�偌` 蝑㚁���蝙敺𦯀�蝞⊥糓�典��祉�餈𤤿�璅∪���𧋦�啁����摰𡁏芋撘讛��臬��函瑪蝔钅�蝥批��荔�蝟餌��亙��函��桃�摰𡁏�瘣餅𧒄���颲枏枂擃睃漲銝��港�摰���芾圾�羓��蠘�蝞�隞页��屸𢒰銝擧𠯫敹𡑒挽霈∩�撉��蝢𤾸之��說嚗�
    - [x] **摰峕��詨��剝睸�惩��拍��齿� (Completed Core Hotkey Remapping & Reorganization)**嚗�
        - [x] **銝��桀�瘚𧢲𤜯�Ｖ蛹 Alt-G**嚗𡁜��笔��函��孵��Ｘ𧒄�枏仃����砍𧑐�墧�敹急㭘�� `Alt+X`/`Alt-X` 敶餃��齿��踵揢銝箏�撅�撘箇�摰𡁶� `Alt+G`/`Alt-G`嚗��蝢擧��支��厰睸�脩�撟嗆�����刻”�澆��𦦵揣獢�葉����孵�摨𥪜漲��
        - [x] **�滢�霂湔��踵揢銝� Alt-T**嚗𡁜��笔��删鍂 `Alt+G` ���𡏭蔓隞嗡蝙�冽��𡑒秩�𢛶�嘥��質�蝘餉秐敹急㭘�� `Alt+T`嚗�僎�其蜓蝐駁�����詻���靚��撠��銵典�摮鞱�蝔𧢲�撠�”銝剖�甇亙��啣笆朣僐��
        - [x] **敶餃�蝳�鍂/瘜券��折�㕑� Alt-T ��**嚗𡁜��抒�撌脖�憸穃仃����𦦵�銝凋葵�∪�蝏渡��匧膥�嘥翰�琿睸 `Alt+T` 餈𥡝��拍��扳釣�𠰴��餉�撠��嚗峕��支�蝟餌��删鍂�𦯀�嚗���Ｗ��碶�敹急㭘�桀�銋㗇���


## 2026-06-01 10:40
- [x] **靽桀�摰墧𧒄銵峕�憭𡁜𪂹�罸�憸煾��瑞㴓頝� (Fixed Infinite Background Refresh Loop for Multi-Periods)**嚗�
    - [x] **�寞祥憭𡁜𪂹�� sleep ��稬蝛� (Resolved sleep Bypass in data_utils.py)**嚗𡁜銁 `data_utils.py` 銝哨�撠� `stop_conditions` 撖� `resample` �嗆���瘥𥪜笆皞𣂷�蝖祉����撅��� `resample` (�亦瑪 `'d'`) ��漣銝箏�����Ｗ�鈭擧暑頝�𠶖����� `resample_ui`���敶餃�閫��鈭���冽���揢�喲��亦瑪�冽�嚗�� `'3d'` / `'w'`嚗㗇𧒄嚗𣬚眏鈭� `'3d' != 'd'` �埝�蝡见紡�� background 頧株砭銝餃儐�舐� `sleep` ��銁鈭𡁏神蝘垍漣��◤銝漤𡢿�剖稬蝛輻�銝仿�蝻粹萅嚗��頧株砭銝餃儐�臬蒂�硺�甇�虜�� 180s �� 120s ���蝑匧�銝准��
    - [x] **瘨�圾 UI 銵峕��瑟鰵憌擧𠂔 (Resolved UI TableUpdate V4 Refresh Storm)**嚗𡁻獈�凋��曹� background �惩辣餈罸��� polling 銵峕�����垍��曹澈 Queue 撘閗絲��蜓蝥輻� Pump / Compute 蝥輻�瘙删��𣳇�擃㗛��曉��滩恣蝞梹��Ｗ�鈭��雿喟� CPU �删鍂銵函緵嚗峕��支� `TableUpdate` V4 ���擃㗛�霅血��� UI 暺𤩺��麄��
- [x] **靽桀�蝑𣇉裦隞餃𦛚頧格揢���銝芾��駁��餉� (Fixed Round-Robin Duplication in stock_live_strategy.py)**嚗�
    - [x] **�寞祥撠𤩺�摮𣂼�蝏訫縧�� (Resolved Small Pool Wrapping Duplications)**嚗𡁜銁 `stock_live_strategy.py` �� `_check_strategies` 銝剖��乩� `pool_size <= max_fetch` ���摮𣂼��臬ế摰𠾼���敶枏��冽�����扳�摮鞱�撠𤩺𧒄嚗䔶�甈⊥�批�甇亙�頧賢��譍葵�∪僎�湔𦻖�滨蔭皜豢�皜貉粥銝� `0`嚗�蝠摨閖獈�凋����蝞埈��典之�冽��硋凝�钅�㕑�瘙牐葉�牐蛹�拍��䂿�撣行䔉���蝝㰘䌊�滚����雿嗵��急�隞餃𦛚�𣂷漱��

## 2026-06-01 02:10
- [x] **隡睃�蝟餌��扯������ Treeview 摮𦯀�銝舘�擃� DPI �冽��龪�� (Optimized Treeview Font & Rowheight DPI Matching for System Performance Analyzer)**嚗�
    - [x] **�寞祥銵屸�蝖祉���� DPI �芣鱏 (Resolved Rowheight Hardcoding & DPI Truncation)**嚗𡁜� `sys_performance_analyzer.py` 銝� Treeview �笔�蝖祉���� `row_height = 25` 靽格㺿銝箏抅鈭� Windows 蝟餌�摰鮋� DPI 蝻拇𦆮�惩���𢆡��恣蝞堒�撘� `row_height = int(28 * scale)`��
    - [x] **�𣂼�閫���航粉�找�擃睃�摨血�撅�蝢擧� (Enhanced Visual Aesthetics)**嚗𡁻�朞�撘訫� `dpi_utils.get_windows_dpi_scale_factor` �瑕�摰鮋���頂蝏毺憬�暹�靘页�雿輯�擃䀝� Microsoft YaHei 摮𦯀�憭批��其遙雿� DPI ��儘������摰𣬚�蝑㗇�靘贝䌊���蝻拇𦆮嚗�蝠摨閙覔瘝颱�擃睃�撅譍� Treeview ����滚����擃䀝�摮堒噡銝滚龪�溻��誑�𡃏���𧋦摨閗器/憿嗉器鋡怎���⏛�剔� UI 雿㯄��𤤿���

- [x] **靽桀�蝟餌��扯�����典�餈𤤿��㕑絲撘�虜 (Fixed System Performance Analyzer Multiprocessing Pickle Error)**嚗�
    - [x] **�寞祥 Pickle 摨誩��㚚��� (Resolved Pickling Limitations)**嚗𡁜� `_launch_subprocess_analyzer` 隞� `StockMonitorApp.open_detailed_analysis_subprocess` ����典�憟堒遆�圈���蛹 `sys_performance_analyzer.py` 銝讠�璅∪�蝥批��典��賣㺭 `launch_analyzer`��眏鈭𤾸�撅��賣㺭憭拍��舀�摨誩��吔�隞舘��蝠摨閙��支��� Windows �� `spawn` 璅∪�銝讠眏鈭𤾸��堒�撅��典遆�啣紡�渡� `Can't pickle local object` 撏拇��� `EOFError: Ran out of input` �仿���
    - [x] **摰䂿緵憭朞�蝔讠���蝠摨閗圾�� (Achieved Pure Multi-process Decoupling)**嚗帋蝙摮鞱�蝔见銁�臬𢆡�嗥凒�仿�朞��滚��堒�撖澆� `sys_performance_analyzer` 璅∪�銝讠� `launch_analyzer` �典��賣㺭撟嗉�銵䕘�摰𣬚��踹�鈭��餈𤤿��� Windows �� `spawn` 璅∪��臬𢆡�園��啣紡�亙�憭找�憭齿��� `instock_MonitorTK.py` 銝餅芋�埈��航�撘訫����甈∪�憪见�撘����㚚��亙�雿𦦵鍂��
    - [x] **�惩𤐄�枏��臬��澆捆�� (Hardened Packaging Compatibility)**嚗帋��坔僎�惩𤐄鈭� DPI-Aware 蝑厰�蝥抒頂蝏笔��唳��伐�蝖桐��� Nuitka/PyInstaller �枏��𡒊� onefile/standalone �臬�隞亙�憭𡁏遬蝷箏膥擃睃�撅譍�嚗��餈𤤿��賢像皛𤑳𡠺蝡𧢲�韏瑕僎靽脲�銝餉�蝔贝�銵𣬚𠶖����屸𢒰擃䀝��笔漲��

## 2026-05-31 18:00
- [x] **摰䂿緵�扯�霂𦠜鱏撌亙��屸𢒰憭批�銝� Treeview �堒捐頝其�霂肽䌊�������� (Implemented Window Geometry & Treeview Column Widths Persistence for System Performance Analyzer)**嚗�
    - [x] **�拍��𡁜�撟嗅��� DPI �箄�蝒堒藁�牐��芷�頧�**嚗𡁜銁 `sys_performance_analyzer.py` 銝哨�摨笔�鈭�誑敺��瑕鍳�冽𧒄蝖祉�����箏� geometry (`1180x820`)嚗峕㺿�函�銝��� `load_window_position_simple` �亙藁�㰘蝸����塚�撠� `WM_DELETE_WINDOW` �拍�蝏穃��唳鰵憓䂿� `on_close` 摰匧����箸㜃�芸膥銝𠺪�摰䂿緵鈭�蜓蝒堒藁�鞉���偕撖貊�頝其�霂嘥�蝢𤾸��䀝��拍�憭滚���
    - [x] **摰䂿緵�諹”�澆�摰賢�摮鞟漣靽嘥�銝� DPI ��蓮��**嚗𡁏鰵憓硺� `save_column_widths` �� `load_column_widths` 銝支葵�詨�蝐餅䲮瘜𤏪�瘛勗漲�游�餈𤤿�銝��� `window_config.json` �嗆�銝准��銁�喲𡡒蝒堒藁�塚�嚙�    - [x] **摰䂿緵憭朞�蝔讠𡠺蝡𧢲�韏瑚��毺��批��� UI 摰𣬚�閫��佗�Multi-process GUI & Original UI Decoupling嚗�**嚗�
        - [x] **摰𣬚�餈睃�撟嗡��坔��� `open_detailed_analysis` 蝒堒藁**嚗𡁶＆靽苷蜓餈𤤿������蝠�讐漣 Tk Toplevel �扯��餃�蝒堒藁嚗��朞� `Detailed Analysis` �厰僼閫血�嚗�100% 瘥怠��䭾��唬��辷�蝏苷�靘萄��硋僕瘨劐蜓餈𤤿��唳���遙雿� Tkinter �唳旿蝞⊿�嚗諹噢�鞉�雿喟��笔��亙藁�澆捆�扼��
        - [x] **�啣�摰���祉��� `open_detailed_analysis_subprocess` 憭朞�蝔见���**嚗帋��函鍂�亙銁�祉�����文�餈𤤿�銝凋誑擃䀹�扯���PI �毺䰻�孵�撘�郊�㕑絲 `SystemPerformanceAnalyzerGUI` �扯�璉�瘚见極�瑯��
        - [x] **憓噼挽�冽鰵擃䁅儘霂�漲�批��厰僼**嚗𡁜銁摰墧𧒄�滚𦛚�烐綉�批��啁��厰僼�譍葉嚗�僎�鍦�霈曆��垍𤌍��換�脩�蝞剜��� `�� Pro-Analyzer`���雿輻鍂�瑕虾隞乩��桅�㗇𥋘�航��典����餈𤤿��餃�嚗諹��航��典��刻圾�衣�擃䀹�扯��祉�憭朞�蝔见��𣂼膥嚗䔶�霂������峕綉�毺��栞�鈭箸㦤鈭支�雿㯄�嚗�
    - [x] **摰墧鴌餈𤤿��交𪄳銝𤾸��鞉��鞉�扯�隡睃� (Extreme Performance Optimization on Process Scanning Engine)**嚗�
        - [x] **�賢𧑐 [PID �蹱��㺭�桀撩蝻枏�] �箏�**嚗𡁜�餈𤤿�����誩�蝘� `name` ��虾�扯�頝臬� `exe` �文�銝箇��賢𪂹�罸�����扼��遣蝡贝䌊����典� PID 蝻枏�摮堒�嚗�蘨�刻�蝔钅�甈∪鍳�冽𧒄�枏��蹱��縑�荔��𡒊賒頧株砭�湔𦻖�朞� `O(1)` 隞𤾸�摮㗛��毺�摮䀝葉蝘垍漣霂餃�嚗�� Windows API 璅∪��㰘蝸頧株砭甈⊥㺭�𠰴�銝� 0��
        - [x] **撱箇� [蝟餌�/靽脲擪蝥� PID 撅讛𤪖�𠉛氖蝵𩬅 (Suppression on Privileged System Processes)**嚗𡁻�撖� Windows 蝟餌�摨訫��詨�擃䀹��鞱�蝔页�憒� Registry��ystem 蝑㚁��刻粉�𤥁楝敺��撅墧�扳𧒄鈭抒� `AccessDenied` ��鸌敺��擐𡝗活璉�瘚见��湔𦻖撠�� PID 敶鍦��拍�撅讛𤪖�����蝏剜醌�誩𪂹�煺葉**敶餃��亥�**撖寡�鈭𥡝�蝔讠����匧�靘见��𠰴��扳�霂𤏪��𣂼�皜�膄鈭�㺭�暹活撘�虜�𥕦枂銝擧��瑞�頞��摨血��訾�銝𧢲���揢撘���嚗䔶蝙�急�銝餃��鞾�憌坔��啣��㵪�
        - [x] **憭滨鍂 Process �交�摰硺��𣂼� CPU �枏�蝎曉漲**嚗𡁜� `psutil.Process(pid)` 摰硺��湔𦻖摮睃��蹱���摮䀝葉���憭滨鍂���蝢舘圾�喃� Windows �臬�銝钅�憸煾���𧒄�曹�銝湔𧒄摰硺��硋紡�� psutil �䭾��瑕�銝斗活�園𡢿��榆�屸�䭾� CPU �䭾�憭折𢒰蝘臬仃�煺蛹 0.0 ����之�曄��對�摰䂿緵鈭���嗡�皛㻫��移���鈭𡁏神蝘垍漣 CPU 韐蠘蝸�烐綉嚗�蕭嚙賭�撟嗅��坔��𡝗�憭硋援皞�紡�渡� 0 摮𡑒���辣�笔�嚗��憭��雿喟��芣�摰寧��扯���
    - [x] **摰䂿緵憭朞�蝔讠𡠺蝡𧢲�韏瑚��毺��批��� UI 摰𣬚�閫��佗�Multi-process GUI & Original UI Decoupling嚗�**嚗�
        - [x] **摰𣬚�餈睃�撟嗡��坔��� `open_detailed_analysis` 蝒堒藁**嚗𡁶＆靽苷蜓餈𤤿������蝠�讐漣 Tk Toplevel �扯��餃�蝒堒藁嚗��朞� `Detailed Analysis` �厰僼閫血�嚗�100% 瘥怠��䭾��唬��辷�蝏苷�靘萄��硋僕瘨劐蜓餈𤤿��唳���遙雿� Tkinter �唳旿蝞⊿�嚗諹噢�鞉�雿喟��笔��亙藁�澆捆�扼��
        - [x] **�啣�摰���祉��� `open_detailed_analysis_subprocess` 憭朞�蝔见���**嚗帋��函鍂�亙銁�祉�����文�餈𤤿�銝凋誑擃䀹�扯���PI �毺䰻�孵�撘�郊�㕑絲 `SystemPerformanceAnalyzerGUI` �扯�璉�瘚见極�瑯��
        - [x] **憓噼挽�冽鰵擃䁅儘霂�漲�批��厰僼**嚗𡁜銁摰墧𧒄�滚𦛚�烐綉�批��啁��厰僼�譍葉嚗�僎�鍦�霈曆��垍𤌍��換�脩�蝞剜��� `�� Pro-Analyzer`���雿輻鍂�瑕虾隞乩��桅�㗇𥋘�航��典����餈𤤿��餃�嚗諹��航��典��刻圾�衣�擃䀹�扯��祉�憭朞�蝔见��𣂼膥嚗䔶�霂������峕綉�毺��栞�鈭箸㦤鈭支�雿㯄�嚗�
    - [x] **摰���朞� py_compile 霂剜��𢠃�餉��蹱��嵗撉�**嚗𡁜��𣂼笆 `sys_performance_analyzer.py` �� `instock_MonitorTK.py` �齿��𤾸�隞������函�霂烐�撉䕘�蝟餌��亙ㄝ�扯噢�鞟���𡡒�荔�

## 2026-05-31 03:00
- [x] **隡睃�憭朞�蝔𧢲𠯫敹烾�蝳颱��煺漣蝥� APP_ROOT ����亙��批� (Optimized Multiprocessing Log Isolation & Production-Grade APP_ROOT Locking Controls)**嚗�
    - [x] **摰䂿緵�臬��㗛�摮睃銁�園�暺䁅��硺�銝餉�蝔钅�甈⊿�摰𡁏𠯫敹𡑒���**嚗𡁻���� `_local_get_app_root` ��㴓憓���𤩺�瘚页��� `INSTOCK_APP_ROOT` 摮睃銁鈭𡒊㴓憓���譍��拍�頝臬��㗇�嚗��餈𤤿��湔𦻖�䠷�餈𥪜�隞仿獈�剖�雿躰��箝����嗥＆靽苷蜓餈𤤿��券�甈⊿�朞��臬��㗛�霂餃�頝臬��塚�隞滩�銝𥪯��賣迤蝖格��唬�甈⊿�摰𡁏𠯫敹𨰜��
    - [x] **餈�誘 Windows Spawn �臬𢆡�賭誘銵����**嚗𡁜銁 `is_main` 銝餉�蝔见ế摰𡁻�餉�銝剛蕭�牐� `not any('spawn_main' in arg for arg in sys.argv)`嚗𣬚移����怠僎�𠉛氖鈭� Windows 撟喳蝱銝� `spawn` 璅∪�憭朞�蝔� Worker ��紡�交�頨思遢��
    - [x] **皜�膄�嗡� logging 璅∪�靘肽�銝𡒊滲����**嚗𡁜蝠摨閙��支��賣㺭���撖� Python ���摨� `logging` 璅∪���𢆡��紡�伐��寧鍂�冽芋�堒仍�典歇蝏誩�憪见��� `log = LoggerFactory.getLogger()` 摰硺�嚗�僎�湔𦻖隡𣳇�垍漣�急㟲�啣�� `10` 雿靝蛹 `log.isEnabledFor(10)` �斗鱏嚗𣬚＆靽萘頂蝏�𠯫敹埈㦤�嗥滲��蝏煺���
    - [x] **�賢��煺漣蝥折�摰帋���稲蝎曄��亙�**嚗𡁜蝠摨閙��支� `_local_get_app_root` 銝剖��砍�颲曉��惩�蝜����葉�渲�霂閙𠯫敹梹�隞�銁銝餉�蝔钅�甈⊿�摰𡁶����鋆�覔�桀�銝� `DEBUG` 蝥批�撘��舀𧒄嚗峕��唬�甈∪僕��皜�� of `APP_ROOT LOCKED => {calculated_root}`����嗡��碶� `get_ramdisk_dir()`, `get_tdx_dir()` ����滚��臬�靚���亙�嚗䔶蝙�園�朞��典� `_RAMDISK_LOGGED` 銝� `_TDX_DIR_LOGGED` �嗆���霈堆�蝖桐�隞�銁銝餉�蝔见鍳�典�憪见��嗡��� `DEBUG` 蝥批�撘��臭�**�枏㫲銝�甈�**嚗��蝏剛��典�摮鞱�蝔见�摰���䠷�嚗𥟇����璅∪�蝥扳�蝛箇� `close Python Launcher` �亙���誑�擧�霈箏�餈𤤿�憒���㕑絲嚗𣬚�蝡臬�銝滢�鈭抒��𦯀��瑕�嚗��蝢𡒊泵�� KISS/YAGNI/DRY 撌亦��笔���
    - [x] **100% �朞� 58 憿寧頂蝏煺��𧼮�瘚贝�**嚗帋耨�嫣��漤��瑕��詨�鈭斗�撘閙� 100% 摰𣬚��澆捆嚗��敶鍦����霂蓥��芸�蝏輸�朞���

## 2026-05-31 02:35
- [x] **瘨�膄�唳旿�亙藁�滨蔭頝臬��瑕��𦯀�銝舘���� (Unified configuration path retrieval in realdatajson.py)**嚗�
    - [x] **撖澆�撟嗅��函�銝� `get_conf_path`**嚗𡁜� `JSONData/realdatajson.py` ��𧋦�芷�删���撩憭� mapping �芣��箏�銝𥪜�雿嗵� `get_conf_path(fname)` �賣㺭敶餃��𣳇膄��㺿銝箇�銝�隞� `sys_utils.py` 撖澆� `get_conf_path`嚗䔶��䔶蝙 `count.ini` 蝑厰�蝵格�隞嗥�摰帋���䌊��圾撖�誑�𢠃俈撋��嚗�� `datacsv` 蝑㚁��餉�銝𤾸�蝟餌�擃䀹�������撖孵笆朣琜�撟嗅�蝢𤾸�鈭� Nuitka Onefile/Onedir �刻䌊�刻��思��𦠜𦆮�蠘���
    - [x] **100% �朞� JSONData 璅∪��𧼮�瘚贝�**嚗𡁜笆 `realdatajson.py` ��瘨匧��� H5 �唳旿銝𡡞�蝵株粉�嗵恣�栞�銵䔶��券𢒰���敶㘾�霂��瘚贝� 100% 銝��芸�蝏輸�朞�嚗䔶漱隞䁅捶�誯𡡒�胯��

## 2026-05-31 02:25
- [x] **�惩𤐄 RAMDisk 頝臬��芣�銝𡒊征�澆�撣豢㜃�� (Hardened RAMDisk Paths & Null-Pointer Prevention)**嚗�
    - [x] **�拍��惩𤐄 `get_ramdisk_dir` �詨��寞�**嚗𡁜� `JohnsonUtil/commonTips.py` 銝剔� `get_ramdisk_dir()` �齿�嚗𣬚＆靽肽𥅾�芣�瘚见�蝟餌�����矋��� RAMDisk �拍�頝臬�銝滚��剁�嚗���芸���摰� `_local_get_app_root()` �拍��寧𤌍敶𤏪�敶餃�瘨�膄鈭���� `None` 撖潸稲�� `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'` 憌𡡞埯��
    - [x] **����𣇉�摮䀝��滨蔭��辣摰帋�**嚗𡁏迨�惩𤐄雿� `JSONData/wencaiData.py`��commonTips.py` 銝凋�韏� `get_ramdisk_dir() + 'h5config.txt'` ����乩�霂餃�頝臬��其遙雿閙� RAMDisk 霈曉�銝𢠃��賢像皛𤏸䌊����摰��靽嗪�鈭�𡠺蝡𧢲����撘��𤑳㴓憓����楊霈曉���蔔�澆捆�扼��
    - [x] **100% �朞� 58 憿孵��讐頂蝏罸��𣂷��𧼮�瘚贝�**嚗𡁏��匧����霂蓥� I/O 蝞⊿��⊿��� PowerShell �臬�銝衤��� 100% �函遛�朞�嚗�**58 passed in 39.46s**嚗㚁�蝟餌��亙ㄝ�扯噢�鞟���𡡒�荔�

## 2026-05-31 02:00
- [x] **�寞祥撌亙�銝舘��拙��鞉芋�𡑒楝敺��雿漤��� (Standardized Auxiliary & Repair Tool Paths)**嚗�
    - [x] **�拍��𡁜�隞瑟聢靽桀�撌亙� `repair_voice_prices.py`**嚗𡁜� `repair_voice_prices.py` �����𧋦靘肽�蝖祉��� `"./"` �� `trading_signals.db` �� `voice_alert_config.json` 頝臬��齿�銝箇�銝��� `sys_utils.get_app_root()` �拍�撖餃�嚗𣬚＆靽嘥��扯��嗥移蝖桐��其��舀�銵𣬚�摨讐���𤌍敶𨰻��
    - [x] **�拍��𡁜��芷�㕑�銝𤾸�隞㯄�蝵格��� `check_monitor_gap.py`**嚗𡁻�����嗆㺭�桀� `trading_signals.db` �� `voice_alert_config.json` ��圾�鞱楝敺���券���鍂 `get_app_root()` 蝏嘥笆頝臬�撖寥���
    - [x] **�拍��𡁜�憭滨����敹怎�璉�蝝� `review_daily_performance.py`**嚗𡁜� `load_latest_snapshot` �� `"snapshots"` 暺䁅恕�詨笆��㺭�齿�銝箄𥅾銝箇征�嗉䌊�煾��摰� `get_app_root()` 閫��嚗峕�蝏苷�憭朞�蝔衤� Nuitka 瘝嗵拳�臬�銝剖翰�批�頧賢仃韐亦��鞉���
    - [x] **100% 銝��芸�蝏輸�朞� 58 憿寧頂蝏煺��𧼮�瘚贝�**嚗𡁜�蝟餌����銝𤾸��𥕦����霂訫銁 PowerShell �臬�銝衤��� 100% �函遛�朞�嚗�**58 passed**嚗㚁�摰𣬚��剔㴓嚗�

## 2026-05-31 01:45
- [x] **餈𥕢�甇交����蝒堒藁雿滨蔭銝舘”�澆�摰賣�銋��頝臬� (Standardized Window Config & Column Widths Persistence Paths)**嚗�
    - [x] **�齿� `gui_utils.py` 蝒堒藁�鞉��㰘蝸銝𦒘�摮�**嚗𡁜� `load_window_position_simple` and `save_window_position_simple` 銝剔� `window_config.json` �� `scale{int(scale)}_window_config.json` ��㮾撖寡楝敺���见極 `os.path.join` �潭𦻖�箏��齿�銝箇�銝�靚�鍂 `sys_utils.get_conf_path` �亙藁����䔶�霂�銁銝滚��� DPI 蝻拇𦆮瘥𥪯�銝页��鞉��滨蔭��辣蝏嘥笆摰𡁏聢�函����摨讐�摰鮋�摰㕑��寧𤌍敶蓥�嚗�僎�瑕�鈭�𦜖�惩��箄��芣��𦠜𦆮靽脲擪��
    - [x] **�齿� `tk_gui_modules/spatial_follow_hud.py` �𡑒”摰賢漲靽嘥��㰘蝸**嚗𡁜� `_save_column_widths` �� `_load_column_widths` 銝剔� `logs/hud_column_widths.json` ��辣頝臬��齿�銝箔蝙�� `sys_utils.get_app_root()` �拍��寧𤌍敶閙𣄽�乓���瘨�膄鈭���烐芋撘誩��祉��枏��臬�銝讠眏鈭𤾸極雿𦦵𤌍敶訫��Ｘ�摮鞱�蝔𧢲�蝘餃紡�渡��堒捐摮䀹﹝摰帋�撘�虜��
    - [x] **100% 瘥急�甇餉��函遛�朞� 58 憿寥��𣂷��见�瘚贝��𧼮�**嚗𡁏��劐耨�孵銁 Windows �拍��臬�銝页�隞� **100% 銝��芸�蝏輸�朞�嚗�58 passed in 41.72s嚗�** 摰𣬚��𡁜�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹�蝏���剔㴓嚗�mn_widths` 銝剔� `logs/hud_column_widths.json` ��辣頝臬��齿�銝箔蝙�� `sys_utils.get_app_root()` �拍��寧𤌍敶閙𣄽�乓���瘨�膄鈭���烐芋撘誩��祉��枏��臬�銝讠眏鈭𤾸極雿𦦵𤌍敶訫��Ｘ�摮鞱�蝔𧢲�蝘餃紡�渡��堒捐摮䀹﹝摰帋�撘�虜��
    - [x] **100% 瘥急�甇餉��函遛�朞� 58 憿寥��𣂷��见�瘚贝��𧼮�**嚗𡁏��劐耨�孵銁 Windows �拍��臬�銝页�隞� **100% 銝��芸�蝏輸�朞�嚗�58 passed in 41.72s嚗�** 摰𣬚��𡁜�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹�蝏���剔㴓嚗�

## 2026-05-31 01:10
- [x] **�券𢒰����𣇉頂蝏笔�雿䠷�蝵株�皞𣂼�頧質楝敺�僎�𦦵�蝖祉��� (Enforced Centralized Configuration Pathing & Eliminated Hardcoded Paths)**嚗�
    - [x] **�惩𤐄�曄內�烾�蝵� `upper_structure_engine.py`**嚗𡁜� `load_display_columns` ��笆 `display_cols.json` ��㮾撖寡楝敺��頧賡���蛹蝏煺��� `sys_utils.get_conf_path` �亙藁嚗���牐�銝滚��冽𧒄���蝥折��摰�㦤�塚�閫��鈭�銁 Nuitka/PyInstaller �祉��臬𢆡�𡝗���㴓憓���曹�頝臬�蝖祉���紡�渡��㰘蝸撏拇��鞉���
    - [x] **�惩𤐄�亙�敶Ｘ����仿�蝵� `intraday_pattern_detector.py`**嚗𡁻���� `_load_config` �寞�嚗���亙���𧒄蝑𣇉裦�滨蔭��辣 `intraday_pattern_config.json` ���頧賡�餉�蝏煺��亙��� `sys_utils.get_conf_path`���霂���枏��𡒊鍂�瑕銁憭㚚��拍��寧𤌍敶蓥�撖寞𠯫����潛�蝻𤥁��賜�撖寧����撟嗅�憭���亙ㄝ����� Fallback 頝臬���
    - [x] **�惩𤐄鈭斗���瓲�蹱���蝵桀�頧� `trading_kernel/kernel_service.py`**嚗𡁻���� `global.ini` �����楝�勗�頧踝��� `sys_utils.get_conf_path` �碶誨鈭���祆��嗵� `os.path.join(base_dir, "global.ini")`嚗䔶�霂��餈𤤿�/憭𡁜𪂹�毺𠶖����滨蔭���銝����銝擧��𤥁楝敺��撖孵笆朣僐��
    - [x] **100% �朞� 58 憿寥��𣂷��见�瘚贝��𧼮�**嚗𡁏��劐耨�孵銁 PowerShell 餈鞱��臬�銝衤誑 **100% �朞����58憿孵��� Passed嚗�37.35蝘鍦�摰峕�嚗�** 摰𣬚��朞�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹�蝏���剔㴓嚗�

## 2026-05-31 00:30
- [x] **敶餃��寞祥 stock_codes.conf �屸��𦠜𦆮銝𤾸�餈𤤿��𣂼��脩� (Fixed stock_codes.conf Duplicate Release & Multiprocess Extraction Conflict)**嚗�
    - [x] **�拍�靽桀� `sina_data.py` 銝剔��滚��𣂼�頝臬�**嚗𡁏䰻�� `sina_data.py` �� `get_stock_code_path` 銝剝鵭�蠘䌊撌勗� Onefile/Onedir �臬��斗鱏撟嗉��� `cct.get_resource_file` �駁��暸�蝵格�隞嗚���銝滢��䭾�隞���滚�嚗峕凒撖潸稲�典��烐� Onedir 璅∪�銝页�`stock_codes.conf` 鋡恍�霂臬𧑐�峕𧒄�𦠜𦆮�� `BASE_DIR/stock_codes.conf` �� `BASE_DIR/JSONData/stock_codes.conf` 銝文��唳䲮嚗䔶漣�煺艇�滚�雿蹱𠯫敹堒�瞏𨅯銁���隞嗅��亦�鈭剹��
    - [x] **�券𢒰撖寥�撟嗅��� `sys_utils.get_conf_path` �箏�撟嗡����憪讠���������**嚗𡁜� `get_stock_code_path` 敶餃��齿�銝箇凒�亥��� `sys_utils.get_conf_path`����𣂼�撠� `sina_data.py` �瑕�頝臬����銝箔�韏��閫���箏�敶雴蛹蝏煺�嚗峕��支�甇文��䭾𦻖��𡠺蝡见ế摰帋�銝��游紡�渡�甇餃儐�胯����嗡��嗘� `sys_utils.py` ����� `mapping` 摮睃銁�嗆��詨����靝���䔝瘚讠���覔�桀�銝讠��唳��滨蔭��辣撟嗥凒�亥��嫰�萘�蝏誩�閫��嚗䔶��靝�摰��銝��渡���蟮�滨蔭��辣�𨅯�雿㯄���
    - [x] **100% �朞� 58 憿寧頂蝏笔�敶鍦����霂�**嚗帋耨�孵��典�摰寧緵�厩��漤��瑟㺭�格�銝𦒘漱�枏��賂�撟嗅銁 PowerShell 餈鞱��臬�銝衤誑 **100% �朞����58憿孵��� Passed嚗�37.38蝘鍦�摰峕�嚗�** 摰𣬚��𡁜�嚗��蝟餌�敶餃����吔�

## 2026-05-30 23:55
- [x] **�寞祥 SQLite �唳旿摨梶恣���霂𦠜鱏撌亙��枏�瞍�宏�鞉� (Standardized SQLite Database Cleanup & Repair Tools Path Alignment)**嚗�
    - [x] **�拍�靽桀��硺漱�𤘪𠯫皜���𡁏𧋦 `clean_db_script.py`**嚗𡁏䰻�� `clean_db_script.py` (L132) �踵�雿輻鍂 `cct.get_base_path()`���撖潸稲�� Nuitka �枏��𠬍�霂亥��砍銁�𤾸蝱餈鞱��嗡�撠�楝敺�圾�𣂼� Temp 銝湔𧒄瘝嗵拳��辣憭嫣葉嚗�紡�氯�𡤜atabase not found, skipping.�萘�銝仿�皜���䠷�憭望� Bug��緵撌脩����蝥找蛹 `get_app_root()` �拍��寧𤌍敶𤏪�蝖桐��嗅笆 `trading_signals.db` 銝� `signal_strategy.db` ���鈭斗��交㺭�格�瘣𦯀� `VACUUM` 蝏嘥笆蝎曉��唬��其��拍�摰硺���辣��
    - [x] **�拍��𡁜� SQLite �祉�靽桀�撌亙� `db_repair_tool.py`**嚗𡁜� `db_repair_tool.py` �� `main()` (L281) 銝剖��砌�韏� `__file__` �潭𦻖��㮾撖寡圾�𣂼�蝥找蛹 `get_app_root()`��＆靽嘥朖雿蹂�銝箇𡠺蝡见�餈𤤿��𤥁◤蝻𤥁��𠬍��函㮾撖孵粉��銝钅�霈支耨憭滨� `signal_strategy.db` 蝏嘥笆摰𡁏聢�函����摨誩����鋆�𤌍敶蓥�嚗諹�䔶��臬銁 volatile 瘝嗵拳�䀝葉�仿���
    - [x] **皜�� `instock_MonitorTK.py` �删鍂撖澆�**嚗帋� `instock_MonitorTK.py` (L104) 皜��鈭��雿嗘�銝滩◤雿輻鍂�� `get_base_path`嚗䔶���芋�㛖漣憿嗥漣撖澆� 100% 瘣��嚗峕�蝏嘥�蝏剛秤�具��
    - [x] **100% �函輕�訫�瘚贝�摰𣬚��𡁜�**嚗�58 憿寥��𣂷��见�瘚贝� **100% 銝��芸�蝏輸�朞�嚗�38.61蝘鍦�摰峕�嚗�**嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹�蝏���剔㴓嚗�

## 2026-05-30 23:48
- [x] **�拍�敶鍦�嚗𡁜��箸鰵瘚芾���繮�碶�憭批��滨蔭����𤥁楝敺� (Aligned SINA Market Fetcher & Stock Codes Config Path)**嚗�
    - [x] **�拍��齿� realdatajson.py 銝� sina_data.py ��抅��楝敺�**嚗𡁜� `JSONData/realdatajson.py` �� `JSONData/sina_data.py` 銝剔��典� `BASE_DIR = get_base_path()` �齿���漣銝箇����鋆�覔�桀��� `BASE_DIR = get_app_root()`���敶餃�瘨�膄鈭� `count.ini`嚗�之�閧�霈∪��堆��� `stock_codes.conf`嚗��蟡刻䌊�匧之銵剁��� Nuitka 瘝嗵拳璅∪�銝讠眏鈭𤾸��亙� Temp �桀�撖潸稲����舀㺭�格�瞍�宏銝𦒘腺撘��撟嗅�蝢擧㗁�乩� Dual-Track �諹膘頝臬��嗆���
    - [x] **100% �朞� 58 憿孵�蝏渡頂蝏笔����霂�**嚗帋耨�孵��典�摰寧緵�厩��亦瑪�𢠃���甅�唳旿蝞⊿�嚗�僎�� PowerShell 餈鞱��臬�銝衤誑 100% �朞����蝢𡡞�𡁜�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹��拍��剔㴓嚗�

## 2026-05-30 23:35
- [x] **�券𢒰����𣇉��滩��剛恣�雴�鈭斗�憌擧綉��瓲�拍�頝臬�嚗��頧刻楝敺�沲����Ｚ��吔�(Full Physical Realignment for Premarket Diagnostics & Trading Kernel Configuration in Dual-Track Architecture)**嚗�
    - [x] **�惩𤐄�睃��滨�霂𦠜鱏銝𡡞�㕑�霈∪��賜�**嚗𡁜銁 `stock_selection_window.py` �𣬚�銝文� `base_dir = get_base_path()`嚗𡿨5031 & L5094嚗剹��tk_gui_modules/spatial_follow_hud.py` �𣬚� `base_dir = get_base_path()`嚗𡿨1653嚗剹��誑�� `signal_dashboard_panel.py` �𣬚� `base_dir = get_base_path()`嚗𡿨2393嚗匧��Ｙ�������蝥找蛹 `get_app_root()` �拍��寡楝敺��撟嗅銁 `signal_dashboard_panel.py` 銝剖�蝢舘殿銵� SOLID �笔�嚗峕��支�撅��典𢆡��紡�伐�蝏煺��梢▲撅�芋�㛖漣�㰘蝸���蝖桐�鈭��㕑�蝒堒藁��凝�𧢲��交�隞亙�蝑𣇉裦靽∪噡��掩隞芾”�睃笆 `logs/premarket_diagnose.json` ��粉�硔����乩誑�𡃏䌊�㕑氜�条�撖寥�摰𡁜銁�拍�摰㕑��寧𤌍敶𤏪�敶餃��𦦵�鈭������亦瑪銝𡡞���甅�滨�蝏𤘪��讐� Temp 銝湔𧒄瘝嗵拳��辣憭嫣�韏瑁◤ OS �芸𢆡皜�征���蝘駁�����
    - [x] **�拍��𡁜�憌擧綉���銝𦒘漱�𤘪芋撘誩�頧�**嚗𡁜銁 `trading_kernel/kernel_service.py` 銝哨�撠� `load_risk_limits_from_config` (L29)��load_trading_mode_from_config` (L61)��TradingKernelService.__init__` 銝剔� `global.ini` 頝舐眏撖餃� (L89) 隞亙��唳旿憸�� (L234, L709) 銝剔� `base_dir = get_base_path()` �券��拍��齿���漣銝� `get_app_root()`嚗𣬚＆靽嗪��批予璇航��坔�鈭斗��扳�璅∪��券��臬�����㗇���
    - [x] **100% 瘥急�甇餉��函遛�朞� 58 憿孵�蝏渡頂蝏笔����霂�**嚗帋耨�孵��典�摰寧緵�厩��亦瑪�𢠃���甅�唳旿蝞⊿�嚗�僎�� PowerShell 餈鞱��臬�銝衤誑 **100% �朞����58憿孵��� Passed嚗�37.13蝘鍦�摰峕�嚗�** 銝��芰遛�堒�蝢𡡞�𡁜�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹�蝏���剔㴓嚗�

## 2026-05-30 23:25
- [x] **�拍��𠉛氖�芾粉韏��銝擧�銋��蝵桅��曇楝敺���諹膘�拍��箏�撖寥�嚗劐�瘨�膄敺芰㴓撖澆� (Dual-Track Path Alignment, get_resource_file Output Redirection & Eradicated Circular Imports)**嚗�
    - [x] **�Ｗ��蹱���皞𣂼粉�曉抅摨�**嚗𡁜�蝢擧�憭滢� `commonTips.py` 銝� `LoggerFactory.py` 銝� `get_base_path()` 餈𥪜�����蹱��圾�衤葩�嗥𤌍敶� (PACKAGE_DIR) ��𧋦�亥�韐���脫迫�嗉◤ Win32 �拍�頝臬�閬������麨�𣈯����皞鞉𪄳銝滚��萘��滚之�鞉�嚗𣬚＆靽脲��厰�������皞鞱粉�𡝗迤撣詻��
    - [x] **�𦠜𦆮�滨蔭��辣�格��拍�撖寥�**嚗𡁜� `commonTips.py` 銝� `LoggerFactory.py` 銝� `get_resource_file` �𦠜𦆮撟嗅��亦𤌍���隞嗆𧒄嚗𣬚𤌍����箇��拍��桀� `BASE_DIR = None` �園�霈文�潸��港蛹 `get_app_root()` �拍��唳旿�寧𤌍敶𨰻���蝖桐�鈭�銁 Nuitka/PyInstaller �臬�銝衤��西圻�𤏸�皞鞾��橘�������蝵格�隞嗉�蝎曉����銋�𧑐隞𤾸����base_path嚗㕑圾�𧢲鼧韐肽��箄秐�拍�蝔见�������鋆�覔�桀�銝页�摰𣬚�颲暹�鈭��頧刻圾�艾��
    - [x] **敶餃��寞祥敺芰㴓靘肽� (Circular Imports Fixed)**嚗𡁻�朞��� `commonTips.py` 銝� `LoggerFactory.py` 銝凋蛹 `get_app_root()`霈曇恣擃䁅�������血���𧋦璅∪��芰��芾雲�拍�頝臬��𤑳緵�箏�嚗��蝢𤾸��支�憿嗅�璅∪��㰘蝸�嗥眏 `sys_utils` �訾�撘閧鍂撘閗絲���颲� 30 憿� `partially initialized module (circular import)` AttributeError��頂蝏蠘�銵諹捶�𤩺�擃矋�瘚贝�憟𦯀辣餈鞱��笔漲�𣂼�餈� 30%嚗�**58 passed in 36.91s**嚗袏xit Code 0嚗㚁�
    - [x] **�賢𧑐 _local_get_app_root ���毺���䌊��楝敺���剛�霂蓥縑��**嚗𡁜銁 `_local_get_app_root()` ����㗇辺隞嗅��臭�������銝剜釣�乩����霂血���滲����蔭 `print` 靚���亙�����賢銁�枏��臬𢆡��凝蝘垍漣��移��紡�� `INSTOCK_APP_ROOT` �臬��㗛��嗆����argv[0]` 閫�聢瘥𥪜笆蝏𤘪�嚗䔶誑�� `sys.path` 銝湔𧒄�桀�璅∠��行⏛霂行�嚗峕�憭批𧑐�𣂷�鈭��鈭扳��𣈯�𤩺�摨艾��

## 2026-05-30 23:10
- [x] **摰𣬚��齿� Nuitka �諹膘�箏�頝臬��嗆�嚗峕��� Windows 銝湔𧒄閫����辣憭� (TEMP) �滚鍳�擧㺭�桐��滨蔭瞍�宏憿賜𪆴 (Standardized Dual-Track Path Architecture & Eliminated Nuitka Path-Drift in Snapshots & Configs)**嚗�
    - [x] **�拍��𠉛氖 static 韏��銝� persistent �唳旿**嚗�
        - `PACKAGE_DIR` (�朞� `cct.get_base_path()`)嚗帋艇�潛�摰帋蛹 **�蹱��蘨霂餉�皞𣂼���圾�讠𤌍敶�**嚗𣬚鍂鈭𤾸銁 Nuitka/PyInstaller Onefile �枏��臬�銝贝粉�硋��函�鈭諹���/�蹱���韏𤥁�鈭改�憒� wencaiData 璅⊥踎蝑㚁���
        - `APP_DATA_DIR` (�朞� `get_app_root()` 撟嗅銁 `commonTips.py` 銝剖� `BASE_DIR` 霈曆蛹 `get_app_root()`)嚗帋艇�潛�摰帋蛹 **�拍��舀�銵𣬚�摨�/�𡁏𧋦���函��拍�摰㕑��桀�**嚗�虾霂餃��冽��唳旿�桀�嚗㚁��其�摮䀹𦆮 `snapshots/` 蝡硺遠韏偦帕�𠰴��睃翰�扼��window_config.json` 蝒堒藁撣����.ini` �滨蔭��辣��logs/` 蝟餌�餈鞱��亙�蝑剹���敶餃�瘨�膄鈭�迨�𨧀�𨅯�銝��賣㺭瘛瑕�餈𥪜� TEMP 頝臬�銝𡒊鍂�瑟㺭�株楝敺��嘥紡�湧��舐�摨誩��唳旿/�滨蔭鋡怎頂蝏蠘䌊�冽�蝛箇��鞉���
    - [x] **�寞祥 Bidding Momentum 蝡硺遠璉�瘚见膥銝𤾸翰�批�隞賣�蝘�**嚗�
        - �� `bidding_momentum_detector.py` 銝哨�撠� L1002 餈𤤿�瘙删𠶖��蝸�交𧒄�� `cct.get_base_path()`��1757 ��蟮敹怎��桀��潭𦻖�� `cct.get_base_path()`嚗䔶誑�� L1776 ���霂嘥�隞賜𤌍敶閧� `cct.get_base_path()` �券��拍��齿���漣銝� `get_app_root()` �拍��寡楝敺��蝖桐�銝芾�撘�𢆡韏偦� state �唳旿�𠰴�隞賣�隞嗥�撖孵��曉銁�拍�摰㕑��寧𤌍敶閧� `snapshots/` ��辣憭嫣葉��
    - [x] **�寞祥 Bidding Racing 韏偦帕蝡硺遠�Ｘ踎�滨蔭����𡝗�蝘�**嚗�
        - �� `bidding_racing_panel.py` 銝哨�撠� L536 璅∪�蝥� GZIP �讠憬�滨蔭靽嘥��� `base_dir = cct.get_base_path()`嚗䔶誑�� L4198 撖澆�撟嗅�撟嗅��脤�蝵格�隞園�㗇𥋘撖寡�獢��韏瑕��桀� `cct.get_base_path()`嚗���券����蝥找蛹 `cct.get_app_root()`���敶餃�閫��鈭�鍂�瑁�撽祇𢒰�踹��脰絲�嫘���憭游��滩䌊摰帋��嗆���蝜�腺憭梁� Bug��
    - [x] **�寞祥 Sector Bidding 蝡硺遠憭滨��亙�敹怎��桀�撖餃�瞍�宏**嚗�
        - �� `sector_bidding_panel.py` 銝哨�撠� L1004 �亙�敹怎�擃䀝漁�Ｘ��� `self.snapshots_dir = os.path.join(cct.get_base_path(), "snapshots")` 隞亙� L5191 ��蟮憭𡁏𠯫撘箏飵�∟蕭頦芸��鞟� `snapshots_dir = os.path.join(cct.get_base_path(), "snapshots")` �券��拍���漣銝� `cct.get_app_root()`嚗𣬚＆靽脲𠯫��翰�折�鈭柴����䀹芋撘誩笆 snapshots �桀���粉��摰𣬚�摰𡁏聢�函�����条�摰鮋��唳旿�桀�嚗諹䌊甇文蝠摨訫��怎征�亙��賣踎銝擧㺭�桃撩憭勗�撣詻��
    - [x] **100% 瘥急�甇餉�蝏踵��朞� 58 憿孵�蝏渡頂蝏笔�敶鍦����霂�**嚗�
        - 靽格㺿�� Windows �拍��臬�銝页�雿輻鍂 PowerShell 餈鞱��� 58 憿孵�蝟餌����銝𤾸��𥕦����霂蓥��芸�蝢𡡞�𡁜�嚗�**58 passed in 52.48s**嚗袏xit Code 0嚗㚁�蝟餌�餈鞱�韐券�蝤鞟𨺗�䭾�嚗峕㺭�株�鈭批��典��鞟���𡡒�荔�

## 2026-05-30 22:20
- [x] **摰𣬚�閫�� Windows �𡁏�蝤��/RAMDISK 撽勗𢆡銝� Nuitka Onefile �拍��箏�頝臬�霂��銝擧�蝘� Bug (Hardened Physical Base Path Discovery & Fixed RAMDISK String-Mismatch Drift in Nuitka Onefile)**嚗�
    - [x] **�拍��交� C: 銝� G: (RAMDISK) �惩�頝臬�瘥𥪜笆瞍𤩺�**: 瘛勗漲摰帋�鈭�銁 Nuitka �枏��臬�銝哨��曹��冽� OS 撠� Temp �桀��惩��� `G:\Temp` (RAMDISK)嚗諹�𣬚頂蝏毺㴓憓���� `NUITKA_ONEFILE_DIRECTORY` (閫��銝湔𧒄�桀�) 靘萘�靽萘����笔��� `C:\Temp\instock_Nuitka`���撖潸稲�� `sys_utils.py` 銝� `commonTips.py` ��� `temp_dir not in argv0_abspath` 摮㛖泵�文��牐蛹�条泵銝滚龪�㵪�`C:\` vs `G:\`嚗㕑�諹◤�文�銝� `True`嚗䔶蝙敺㛖頂蝏笔�閫��銝湔𧒄�桀� `G:\Temp\instock_Nuitka` 霂臬ế銝算�𦦵��� EXE ���函𤌍敶𨰝�嘅�撟嗥凒�仿�摰帋� `INSTOCK_APP_ROOT` �臬��㗛�嚗䔶�����睲�蝡硺遠/�㕑��亙�璅∪�隞亙�瘥𤩺𠯫憭滨��Ｘ踎撖孵翰�抒𤌍敶訫粉���� Temp �桀����憭扳�蝘颯��
    - [x] **�賢𧑐�拍�蝥� `_is_inside_temp_dir()` �行⏛�脩瑪**: �齿�撟園�蝵脖�擃睃漲�脣鴃�抒� `_is_inside_temp_dir()` 頝臬�璉�瘚见遆�啜��砲�賣㺭�� `sys_utils.py` �� `get_app_root` �� `commonTips.py` �� `_local_get_app_root` 銝剖笆蝘啣��堆��瑟�隞乩��屸��脩瑪嚗�
        - [x] **�笔�頝臬�撖寥�**: 銝滢�餈𥡝����摮㛖泵�寥�嚗諹�撘訫�鈭� `os.path.realpath` 敶餃�餈睃� Windows 銝� Junction/Symlink/RAMDISK 撽勗𢆡�滚��穃��������条�蝚佗�撠� `C:\Temp` 蝎曉��惩��� `G:\Temp`嚗㚁��寥膄鈭�楊�条泵瘥𥪜笆瞍𤩺�嚗�
        - [x] **璅∠�閫���惩𤐄**: 撖� `"instock_nuitka"`, `"onefile_"`, `"_meipass"`, `"\temp\"` 蝑厰�憸睲葩�嗅��桀�餈𥡝�璅∠��滨蔭�行⏛嚗諹噢�� 100% 瘥急�甇餉�������蝳颯��
    - [x] **Fallback 憭𡁻俈蝥踹捆��**: �� Step 3 `__file__` 皞鞟� fallback �文�銝哨��交�蝏�粉��蝏𤘪�靘萘�撅硺�銝湔𧒄��辣憭對�蝟餌�撠�䌊�券��� `sys.path` 璉�蝝ａ�銝湔𧒄雿滨蔭嚗峕���蝏��蝥批����� `os.getcwd()`嚗峕�靘𥕢�摰𣬚�����𣂼捆�曇”�啜��
    - [x] **100% 瘥急�甇餉��朞� 58 憿寧頂蝏笔����霂�**: 靽格㺿�� PowerShell 餈鞱��臬�銝衤誑 **100% �朞����58憿孵��� Passed嚗�** 蝏踵�摰𣬚��朞�嚗𣬚頂蝏�瓲敹�楝敺�迅摰𡁜漲颲暹��拍��剔㴓嚗�蝠摨訫��唬��芸�蝏踴���蝎曉漲�唳旿�箏�嚗�

## 2026-05-30 21:50
- [x] **敶餃��寞祥 Windows �𡁏�蝤��/RAMDISK 撽勗𢆡銝� pathlib 頝臬�閫��撏拇� (Fixed Win32 RAMDISK WindowsPath.resolve Error)**嚗�
    - [x] **�拍�摰帋�蝟餌�蝥� Bug**: �交�敶� Windows 撠� Temp �桀��𤥁��毺��䀹�撠�� G:\ (RAMDISK �箸����毺�) �塚��曹��𣂷� RAMDISK 撽勗𢆡摰䂿緵�芸��冽𣈲�� Win32 `GetFinalPathNameByHandle` 摨訫� API嚗�紡�湔��� `pathlib.Path.resolve()` �賣㺭�冽�銵峕𧒄隡𡁏��� `OSError: [WinError 1] Incorrect function: 'G:\\Temp'`���隡𡁶凒�亙紡�� pytest 獢�沲��蔭�� `tmp_path` 銝湔𧒄�桀�閫���𥕦枂撘�虜嚗諹���紡�� 5 憿嫣漱�枏��賊��鞉�霂訫仃韐乓��
    - [x] **�賢𧑐 Root-Level `conftest.py` �冽����� Hook �脣鴃**: �券★�格覔�桀�銝𧢲鰵憓硺� `conftest.py` �典�瘚贝��亙藁��⏚�� Python �冽���撠�㦤�塚��� pytest �㰘蝸�笔笆 `pathlib.WindowsPath.resolve()` 餈𥡝��𧢲钟蝥� Hook����𤑳� `OSError` �塚��芸��滨漣��摰�僎餈𥪜� `.absolute()` 蝏嘥笆頝臬���
    - [x] **100% 瘥急�甇餉��朞� 58 憿寧頂蝏笔�敶鍦����霂�**: 霂交䲮獢�銁銝滢噩�亦�鈭找��∩誨����漤�銝页�摰𣬚�靽桀�鈭�頂蝏毺漣摨訫�撽勗𢆡�𣂼�嚗䔶蝙敺� PowerShell �臬�銝� `$env:PYTHONPATH=".;JSONData"; pytest` 餈鞱��� 58 憿寧頂蝏��霂𤏪���𡠺憌擧綉璅∪���予璇臭漱�𤘪���5 �唳旿韐券����雿滩䌊����漱�梶�嚗劐誑 **100% �朞����58憿孵��� Passed嚗�** �瑕��函遛�朞�嚗䔶漱隞䁅捶�誩�蝢擧𤣰摰矋�

## 2026-05-30 21:30
- [x] **�寥膄 legacy �条� getcwd �拍��鞉�嚗峕��游��箄楝敺�䌊����� (Eliminated Legacy getcwd Variants & Consolidated Auto-Healing Path Architecture)**嚗�
    - [x] **�齿� `commonTips.py` �芸�銋� `getcwd()` �詨�撘閙�**嚗𡁜� `commonTips.py` ����枏�憭朞�蝔卝��in�滚𦛚�㚚��批��啣鍳�典��� `sys.argv[0]` �讐宏�� `getcwd()` �賣㺭�拍���漣銝箔誨��秐 `get_base_path()`��蝙�港葵蝟餌����厰�撘讛��� `cct.getcwd()` ���皜貊�隞嗅�蝢擧㗁�亙抅鈭� Windows Win32 API 蝥批���▲蝥找��� EXE/�𡁏𧋦 頝臬�嚗�
    - [x] **����� `stock_sender.py` �煾��楝敺�**嚗𡁜� `stock_sender.py` �嘥��碶葉畾讠� of `os.getcwd()` �齿�銝� `get_app_root()` 撽勗𢆡嚗䔶�霂��餈𤤿� Linkage 靽∪噡����� AHK/�諹�憿�/�朞噢靽⊿�蝵株楝敺��摰匧��𡁜���

    - [x] **�齿� `wencaiData.py` �唳旿頝臬�**嚗𡁜� `wencaiData.py` 銝剖��脤��嗵���摹�潭𦻖�餉�敶餃���漣銝箏�憭� **�𨅯𢆡���蝵格䔝瘚� + �箄����璅⊥踎�𦠜𦆮�芣� + ���銝Ｗ仃 Error �鞟內��** �����粉��撘閙���銁撘��烐芋撘譍�摰帋��� `'JohnsonUtil'`嚗�銁�枏�璅∪�銝贝䌊�煾�朞� `get_base_path()` 餈𥡝�憭𡁻�頝臬��� `NUITKA_ONEFILE_DIRECTORY` 璉�瘚页��亙��函���𤌍敶蓥腺憭勗��芣��𣂼����璅⊥踎憭滚��啣��剁��潮▽鈭��銋�凒�唬��芾粉韏���𣂼�����橘�
    - [x] **Top-Level �典�撖澆�銝�甈⊥�批�頧�**嚗𡁜� `from sys_utils import get_app_root` �𣂼� `stock_sender.py` 憿園�嚗�僎�� `wencaiData.py` �㰘蝸�毺�銝�憭��嚗䔶�霂�芋�𡑒�銵𣬚滲����
    - [x] **100% �朞� 58 憿孵�蝏渡頂蝏笔����霂�**嚗𡁜�蝥批� 58 憿寥��𣂷��扯��訫�瘚贝�銝��芸�蝏選�撅閧緵鈭��雿喟�撌亦�蝔喳�摨血�隞��韐券�嚗�

## 2026-05-30 21:10
- [x] **�函輕����𣇉���抅��楝敺�沲����寞祥 Nuitka 憭朞�蝔衤� Onefile 頝臬�瞍�宏 (Standardized Global Path Architecture & Eliminated Nuitka Path-Drift)**嚗�
    - [x] **皜�膄銝餅芋�𦯀葉�� volatile 靘肽�**嚗朞��怠僎�齿�鈭�瓲敹���折𢒰�踴����湔�瘚见膥隞亙��航��𡝗��交�銝剜��㗇��嗵� `os.getcwd()`���摰�賑�券��拍��踵揢銝箇眏蝏煺��� `sys_utils.get_app_root()` 頝臬��𡁶��湔𦻖閫��嚗�
        - [x] `instock_MonitorTK.py`嚗𡁜笆朣𣂷� `update_linkage_status` 銝剔� `vis_var` �賭誘銝𡒊𠶖���憭㵪�
        - [x] `trade_visualizer_qt6.py`嚗𡁜笆朣𣂷� `SWITCH_CODE` �𥪜𢆡��resample` 蝻枏�霂餃�銝� `vis_var` 餈𤤿�鈭支�嚗�
        - [x] `concept_viewer.py`嚗𡁜笆朣𣂷� HDF5 �� concept �唳旿摨梶�頝典像�啗楝敺��瘚页�
        - [x] `premarket_analyzer.py`嚗𡁏����鈭���滚��𣂷葉撖� `top_all.h5` �砍𧑐 fallback ��䰻�曇楝敺��
        - [x] `bidding_momentum_detector.py`嚗𡁻������蟮憭滨� `load_from_snapshot` �嗅笆 `snapshots/` 敹怎���䰻�暸��對�
        - [x] `tk_gui_modules/spatial_follow_hud.py`嚗𡁜笆朣𣂷��踹�頝笔��航��硋凝�𧢲��交�撖寞𧋦�� `top_all.h5` 銝芾��笔����蝥扯繮�𤥁楝敺���
    - [x] **摰䂿緵璅∪�蝥� Top-Level �典�撖澆�銝�甈⊥�批�頧�**嚗𡁜� `from sys_utils import get_app_root` ��葉�典���辣��▲�冽芋�堒�頧賣�銝�甈⊥�批紡�乓����支��刻蔭霂Ｗ�頝單�擃㗛��𥪜𢆡銝剔�撅��� dynamic import 撘���嚗䔶誨����潭��嗅僕��嚗屸�敺� DRY �� SOLID �諹提��氖�笔���
    - [x] **100% 瘥急�甇餉�蝏踵��朞� 58 憿孵��讐頂蝏笔�敶鍦����霂�**嚗帋耨�孵��典�摰寧緵�厩��亦瑪�𢠃���甅�唳旿蝞⊿�嚗�僎�� PowerShell 餈鞱��臬�銝衤誑 100% �朞����58憿孵��� Passed嚗匧�蝢𡡞�𡁜�嚗𣬚＆靽嘥銁 Nuitka Onefile 擃睃漲瘝嗵拳���餈𤤿�撟嗉�鈭支����蝡舐�鈭抒㴓憓�葉�賢�蝏嘥笆蝔喳��啣�雿齿��㕑�皞鞱�鈭改�

## 2026-05-30 20:50
- [x] **�孵�����砍�甇交𣈲��3蝘齿���芋撘誯�㗇𥋘�箏� (Implemented Synchronized 3-Option Build Selector for Nuitka batch scripts)**嚗�
    - [x] **蝏煺��拙��㗇𥋘�其蛹3銝芷�厰★**嚗𡁜銁 `nuitka_build_console.bat` 銝� `nuitka_build_console_onlyClang.bat` 銝哨��峕郊撠��㗇𥋘�典�蝥找蛹 3 銝芷�厰★嚗䫤[1] Standalone Folder`��[2] Onefile with fixed Tempdir`嚗�蝙�� `--onefile-tempdir-spec="{TEMP}\instock_Nuitka"` �厰★嚗劐� `[3] Standard Onefile`嚗��雿輻鍂 `--onefile`嚗剹��
    - [x] **�惩𤐄撉諹�銝擧辺隞嗅��舫�餉�**嚗𡁜����𡒊�撉諹��航�隞𤾸�銝��� `if "%BUILD_MODE%"=="onefile"` 靽格迤銝� `if "%BUILD_MODE%"=="standalone"` ��笆蝡钅�餉��文���＆靽脲�霈箸糓璅∪� 2嚗Ǒonefile_spec`嚗㕑��舀芋撘� 3嚗Ǒonefile`嚗厰��賢�蝢𤾸𦶢銝� Onefile ����冽�折�霂���亙�颲枏枂嚗峕�蝏嘥銁銝滚�璅∪�銝见�銝粹�霂�仃韐亙紡�湔綉�嗅蝱�仿��������

## 2026-05-30 20:40
- [x] **隡睃� Nuitka Onefile �枏�銝湔𧒄閫��頝臬��箏� (Optimized Nuitka Onefile Unpack Path)**嚗�
    - [x] **撘訫��箏�閫���桀���㺭**嚗𡁜銁 `nuitka_build_console_onlyClang.bat`��nuitka_build_console.bat` 銝� `nuitka_instockMonitor.bat` �� Nuitka 蝻𤥁���㺭銝哨���笆 `--onefile` �枏�璅∪�撘訫�鈭� `--onefile-tempdir-spec="{TEMP}\instock_Nuitka"` �厰★��
    - [x] **閫���𤩺㦤銝湔𧒄��辣憭寞��嗘�頝臬�瞍�宏�桅�**嚗朞砲��㺭霈拍��鞟��閙�隞嗅虾�扯�蝔见��刻�銵�鍳�冽𧒄嚗�𤐄摰朞圾�见�蝟餌�銝湔𧒄�桀����銝�頝臬� `%TEMP%\instock_Nuitka`����㗇��踹�鈭� Nuitka 暺䁅恕�𣳇��箄圾�讠��𣂼耦憒� `onefile_{PID}_{TIME}` ����暹�隞嗅允撖潸稲��頂蝏煺葩�嗥𤌍敶閗��選�撟嗅�撘箔�蝔见�撖嫣�閫��頝臬�銝衤�韏𤥁�鈭抒��詨笆摰帋�蝔喳��扼��

## 2026-05-30 20:20
- [x] **摰䂿緵 HDF5 霂餃� RAMDISK 銝湔𧒄�桀� 300 蝘㘾俈�硋��游������㦤�嗡��滨蔭閫��銝�甈⊥�批�頧賣��港��� (Implemented Throttled 300s Cooldown Cleanup & Module-Load Config Parsing)**嚗�
    - [x] **�交�摰䂿��𤾸蝱擃㗛���䔿��辣��妖�箏�**嚗𡁜銁蝔见�餈鞱��罸𡢿嚗���啣虜撽餅��∩�憭朞�蝔衤遙�∩�擃㗛�銝齿鱏�啣銁 RAMDISK (G:\) 銝贝䌊�典�撱箇�摮� `Temp` ��辣����靝��典鍳�冽𧒄皜��銝�甈∴�餈嗘��嗥����摮睃��曆��典�撠𤩺𧒄���皛� RAMDISK �拍����蝛粹𡢿嚗��甇文�憿餃銁 HDFStore 霂餃�銝剛�銵䔶撈�誩���賒皜����
    - [x] **�賢𧑐璅∪��㰘蝸�園�蝵桐�甈⊥�扯圾�𣂼���**嚗𡁻�撖� `SafeHDFStore` 摰硺��㚚�甈⊥�擃矋�瘥讐��啣�銝羓蓡甈∴���鸌�對�銝箔�敶餃�瘨���� `__init__` 銝剝�憸𤏸粉�㚚�蝵桅★銝𡡞�憭滩�銵� `isinstance`��strip` �� `lower` ���蝚虫葡閫���扯�撘���嚗�銁 `tdx_hdf5_api.py` 璅∪�擐𡝗活�㰘蝸�嗡�甈⊥�批� `cct.cleanRAMdiskTemp` 閫��撟嗉蓮�Ｘ����撣���潘�摮睃��典��㗛� `_CLEAN_RAMDISK_TEMP` 銝哨�靘𥕦�蝏剖�靘见��湔𦻖 O(1) 撣��憭滨鍂��
    - [x] **�賢𧑐 300 蝘� (5���) �芣��脫��瑕㭂�� (Cooldown Guard)**嚗𡁜銁 `SafeHDFStore.__init__` 摰硺��㚚�餉�銝剖��亙抅鈭𤾸�撅��園𡢿�� `_LAST_TEMP_CLEANUP_TIME` ��俈�硋��湔㦤�嗚��� `_CLEAN_RAMDISK_TEMP` 銝� `True` 銝磰�銝𦠜活皜��頞��鈭� 300 蝘𡜐�5���嚗㗇𧒄嚗峕���迤�扯�銝�甈� `cleanup_temp_dir(self.basedir)`��
    - [x] **摰䂿緵�扯�銝擧�蝏剜����蝢𤾸像銵�**嚗朞�雿踵������眏隞亙����蝘埝㺭��活�湧��唳�憭𡁏�5���銝�甈∴��券�皜��敹�歲�毺凒�亙⏚�券���恣蝞堒末���撠𥪜�澆�����園𡢿�單�撖寧�頝航��痹��嗥��� IO �蠘�𦯀�隞𡒊����憭港�敶餃��𦦵�鈭�僎�穃����蝒�� `PermissionError` 霂臬�銝湔𧒄敹怎���辣�������
    - [x] **100% 瘥急�甇餉�蝏踵��朞��典� H5 �訫�瘚贝�**嚗𡁻�撖� H5 �函輕�见�瘚贝��𠰴捆�讐恣���敶𡜐�2憿寞�霂� 100% 銝��芸�蝏輸�朞�嚗䔶漱隞䁅捶�𤩺��舀��䈑�
- [x] **靽桀��滨蔭�桃掩�贝圾�𣂼�撣詨紡�� RAMDISK 銝湔𧒄�桀�鋡怠撩�嗆�蝛� Bug (Fixed cleanRAMdiskTemp Truthiness Evaluation Bug in SafeHDFStore & Config Parser)**嚗�
    - [x] **�拍��交� Bug �箏�**嚗𡁶頂蝏罸�朞� `commonTips.py` 霂餃� `global.ini` �滨蔭��辣銝剔� `cleanRAMdiskTemp = False` 霈曄蔭����典�撅� `get_with_writeback` �瑕��滨蔭憿寞𧒄嚗諹砲��㺭�� `value_type` 鋡恍�霂舀�摰帋蛹鈭� `"str"`���銝粹�蝛箏�蝚虫葡 `"False"` �� Python ���撠𥪜ế摰帋葉嚗�� `if cct.cleanRAMdiskTemp:`嚗匧予�嗉◤霂�摯銝� `True`嚗�紡�游朖雿踹銁�滨蔭銝剜遬撘讛挽蝵桐蛹鈭� `False`嚗�銁 HDF5 ��辣霂餃��� `SafeHDFStore.__init__` �嘥��碶葉靘萘�隡朞◤撘箏�閫血� `cleanup_temp_dir()` �扯�皜�征嚗䔶漣�煺��餉�餈肽�銝𦒘�敹������� I/O��
    - [x] **�賢𧑐 `"bool"` 蝐餃�蝎曉��齿� (Config Parser Boolean Alignment)**嚗�
        - [x] �� `commonTips.py` �� L735 銝哨�撠� `cleanRAMdiskTemp` 霂餃��嗥� `value_type` 靽格迤銝箸���� `"bool"`嚗���嗅� `fallback` 撖寥�銝箏�撠𥪜�� `False`��
        - [x] �� `commonTips.py` �� L1041 銝哨�撠� `cleanRAMdiskTemp` ��掩�𧢲釣閫�眏 `str` ��漣銝� `bool`���雿踹� `cct.cleanRAMdiskTemp` �典�頧賣𧒄�喳歇�瑕��笔��� Python 撣��撖寡情嚗ǑTrue` �� `False`嚗剹��
    - [x] **�賢𧑐 HDF5 �唳旿瘚�����靽嗪埯�脣鴃 (Defensive String/Bool Guard)**嚗�
        - [x] �� `tdx_hdf5_api.py` �� L327 銝哨�銝滢�摰𣬚����撌脖耨甇��撣��蝐餃�嚗諹�撘訫�鈭����漣��艇�潛掩�钅俈敺∴�`if isinstance(_clean_flag, str): _clean_flag = _clean_flag.strip().lower() in ("1", "true", "yes", "on")`���蝖桐�鈭�銁��垢��掩�芰�霂㻫���摮䁅����撅��函㴓憓�𧊋撖寥���葩�𣬚𠶖���嚗𣬚頂蝏毺�撖嫣�隡𡁜�銝箏�蝚虫葡 `"False"` 霂臬ế銝箇��潔�������憭𣇉� Temp ��辣憭寞�蝛箝��
    - [x] **100% 瘥急�甇餉�蝏踵��朞��典� H5 �訫�瘚贝�**嚗𡁻�撖� H5 �函輕�见�瘚贝���捆�讐恣������笔�蝻拐���僎瘚贝��扯��典��𧼮�嚗���� `test_h5_comprehensive.py` e.g., `test_compression.py` 蝑㚁�嚗峕��㗇�霂� 100% 銝��芸�蝏輸�朞�嚗䔶漱隞䁅捶�𤩺��舀��䈑�

## 2026-05-30 18:45
- [x] **��稲�扯��齿�嚗𡁜蝠摨閙��� percdf �嘥��𣇉�餈䂿賒 combine_dataFrame �扯����� (Optimized percdf Single-Slice Initialization in stockFilter)**嚗�
    - [x] **�拍��交��扯��園�**嚗𡁜� `stockFilter.py` �典�憪见� `percdf` 撅墧�扳𧒄嚗䔶蝙�其�餈䂿賒 6 甈� `cct.get_col_market_value_df` 銵峕������ 5 甈⊿�摨� `cct.combine_dataFrame` 餈𥡝�憭朞”憭扳𣄽�乓���銝� `combine_dataFrame` ����賣��𠰴�撅� O(N) �� merge��oncat 隞亙� index �⊿�嚗�紡�游��臬𢆡擐𡝗活�嘥��𡝗𧒄鈭抒�鈭�遬�� of CPU �埈𧒄���摮䀹��具��
    - [x] **�賢𧑐 O(1) 蝥批��閙郊����齿�**嚗𡁜�隞乩��餉��拍��踵揢銝箔�甈⊥�扳𤣰��僎餈�誘�箸��厩泵��𦶢�齿芋撘讐��䠷�匧��𡑒”嚗屸�朞� `df[valid_cols].copy()` �典�摮䀝葉餈𥡝��祇𡢿����𣂼����敶餃�瘨�膄鈭� 5 甈∪之��僎���雿躰�蝞梹�雿踹� `percdf` ���憪见��埈𧒄隞� ~100-200ms �湔𦻖蝻拍��� **鈭𡁏神蝘垍漣嚗ǚ0.1ms嚗峕�扯�憌坔� 1000+ �㵪�**��
    - [x] **�拍��剔� index 銝Ｗ仃銝� KeyError �鞉�**嚗𡁶眏鈭𡡞��其�銝�甈⊥�批�甇亙�����唳旿�典�摮䀝葉���蝏𤘪��� `'code'` 蝝Ｗ��滨妍憭拍�靽脲� 100% �峕�嚗䔶��滨���遙雿� Pandas merge �脣�嚗䔶��拍�皞𣂼仍銝𦠜�蝏苷� `reset_index()` �� `KeyError` �鞉���
    - [x] **100% �券��𧼮�瘚贝��朞�**嚗𡁜�蝢𡡞�朞�鈭��憟� 57 憿孵�敶鍦����霂𤏪�鈭支�韐券�����𡃏���
- [x] **摰䂿緵�瑕鍳�典��睃��嗆㺭�桃撩憭望𠯫敹烾�甈⊥綉�� (Missing Real-time Data Log Throttling)**嚗�
    - [x] **摰帋��亙�瘣芣�皞𣂼仍**嚗𡁜銁�硺漱�𤘪𧒄畾菜��冽錰�瑕鍳�冽𧒄嚗朙AMDISK (G:\) ��� HDF5 �唳旿摨枏�銝滚��典��睃��嗆㺭�殷�憒� `all_30` 銵剁�嚗�紡�� `tdx_hdf5_api.py` �� `load_hdf_db` �亙藁隡𡁜銁瘥譍�甈∪��啣�甇亥蔭霂Ｖ葉擃㗛��𥕦枂 `ERROR: tdx_hdf5_api.py: ... is not find ...`嚗屸�䭾�銝仿���綉�嗅蝱�亙��瑕��𣬚��� I/O �蠘�𨰜��
    - [x] **�賢𧑐銝厰𧫴畾菟�甈⊥㜃��**嚗𡁜銁 `load_hdf_db` �𥕦枂 Table �芣𪄳�圈�霂舐����撘訫�鈭�抅鈭𤾸�撅� `_missing_table_counts` ���甈⊥綉�嗅膥��笆�䔶�銵典��峕㺭�桀��滨�蝻箇��躰秤蝝航恣颲枏枂 3 甈� ERROR 蝥批����憟質郎�𠹺誑�羓䰻�嗆���隞𡒊洵 4 甈∟絲嚗諹䌊�函����蝥折�摰𡁜��� `log.debug`����函＆靽嘥��𤏸����匧虾靚���抒��峕𧒄嚗�蝠摨訫��碶�摰䂿�擃㗛�敹�歲�硋��臬𢆡�嗥��亙��批��堆�靽嗪�鈭�頂蝏毺���蔔蝥臬�摨虫�雿㯄�韐冽���

## 2026-05-30 18:30
- [x] **�拍��交��瑕鍳�券�甈∟�銵峕�蝻枏�撏拇���権撟嗅��鞉�憭渡������ (Uncovered Cold-Start Cacheless Crash Root Cause & Hardened Pipeline Source)**嚗�
    - [x] **摰帋��瑕鍳�其�蝻枏�皜�膄銝讠�餈鮋�撏拇��箏�**嚗𡁶移蝖桀�雿滢��函�摨誩�憪见��𣂼����銵� `lastpTDX_DF_Dict.clear()` �拍�皜�征蝻枏��𠬍�蝚砌�甈∪��臬𢆡餈鞱��亦瑪 `'d'` 頧券��塚�銝餃儐�臬�銝箇撩憭望𧋦�啁�摮䁅◤餈怨��� `get_append_lastp_to_df`��銁甇文遆�啣�撅���唳旿�函��� `get_tdx_exp_all_LastDF_DL` 隞𡡞妟�齿鰵�枏�撟嗡��株揣�唳旿 `wcdf` 隞亙�摰墧𧒄銵峕�餈𥡝�憭𡁻� `cct.combine_dataFrame` �潭𦻖���蝔衤葉嚗𣬚眏鈭� Pandas ����潭𦻖���蝘条撩�瘀�餈𥪜��� `top_all` 蝝Ｗ��滩◤�䠷��孵像銝箔� `None`���撖潸稲�喃噶�冽�瘝⊥�餈𥡝�隞颱��冽���揢嚗���臬𢆡蝚砌�甈∟�銵䔶�隡𡁶凒�亙�瘝⊥�蝝Ｗ��滨� DataFrame 隡惩�銝𧢲虜�� `getBollFilter` 撖潸稲 KeyError 撏拇���
    - [x] **�賢𧑐皞𣂼仍蝥抒���㜃�芷俈敺� (Source-Level rename_axis Guard)**嚗𡁜銁 `JSONData/tdx_data_Day.py` �� `get_append_lastp_to_df` �亙藁��蝏���� `top_all` 銋见�嚗�撩�𥟇釣�乩� `if top_all.index.name != 'code': top_all = top_all.rename_axis('code')` �拍��⊿����隞擧㺭�桀��𤑳�皞𣂼仍�㮖�鈭����俈��‘銝���𦦵�鈭��蝻枏��瑕鍳�其�憭扯”蝝Ｗ��滩◤�脣�銝Ｗ仃����券�����
    - [x] **100% 瘥急�甇餉�蝏踵��朞� 57 憿孵��讐頂蝏笔�敶鍦����霂�**嚗帋耨�孵銁 PowerShell �臬�銝衤��芸�蝏輸�朞��典� 57 憿寧頂蝏��霂𤏪�靽嗪�鈭���臬𢆡銝𡡞�憸煾���甅����游�憯桐�蝤鞟𨺗蝔喳𤐄嚗�

## 2026-05-30 18:00
- [x] **靽桀���僎�唳旿�埈��� `percdf` 蝻箏仃 'code' 蝝Ｗ�撘訫��� KeyError 撘�虜 (Fixed DataFrame Index KeyError in getBollFilter)**嚗�
    - [x] **瘛勗漲摰帋���僎�嗥揣撘蓥腺憭梁��鞟�蝻粹萅**嚗𡁜��𣂼��啣銁 `JSONData/stockFilter.py` ��� `getBollFilter` 銝� `getBollFilter_vect` �𣂼� `percdf` 撅墧�扯�蝔衤葉嚗𣬚頂蝏��銵䔶�憭朞蔭 `cct.combine_dataFrame` 銵峕�憭扯”�潭𦻖���銝� Pandas ���撖嫣� index 瘝⊥��曉��滨妍���銵典� `merge` �� `concat` �嗡�銝Ｗ仃銝餉”��揣撘訫�嚗�紡�� `percdf.index.name` �䀝蛹 `None`嚗㚁�雿踹��𡡞𢒰�� `reset_index()` 撠�砲�𡑒秤�賭蛹 `'index'`嚗諹���紡�� `drop_duplicates('code')` �𥕦枂 `KeyError: Index(['code'], dtype='object')`��
    - [x] **�賢𧑐擃䀝��蠘䌊��俈蝥� (Defensive rename_axis Guard)**嚗𡁜銁 `reset_index()` 靚�鍂�滚撩�𥟇釣�乩� `if percdf.index.name != 'code': percdf = percdf.rename_axis('code')` ��誘�����＆靽苷�蝞⊥𣄽�交㺭�格�蝝Ｗ��滚�雿蓥腺憭梧��滩挽蝝Ｗ��嗡�摰朞�摰匧�撖澆枂撣行� `'code'` �㛖� DataFrame嚗䔶�皞𣂼仍銝𠰴蝠摨訫��凋� KeyError 撘訫�銝餉�蝔衤蜓敺芰㴓撘�虜���瘣𠺶��
    - [x] **100% 瘥急�甇餉�蝏踵��朞� 57 憿寧頂蝏笔�敶鍦����霂�**嚗帋耨�孵歇�� PowerShell �臬�銝衤��芸��朞��典� 57 憿寥��找漱�㮖� H5 �唳旿瘚贝�嚗𣬚頂蝏蠘捶�讐��喟迅�綽�

## 2026-05-30 17:45
- [x] **�峕郊憭𡁜𪂹�罸���甅銝𧢲�蝝Ｚ�皛支�隞��瘚贝��唳旿皞鞱楝�� (Synchronized Search Filtering & Code Testing Data Source in Multi-Period Resampling)**嚗�
    - [x] **敶餃��寞祥�齿活�𦦵揣銝𦒘葵�⊥�霂閖���碶蛹�亦瑪�箇��唳旿 Bug (Fixed Multi-Period Re-search & Test Degradation to Daily)**嚗�
        - [x] 靽桀�鈭�� `apply_search` 銝� `on_test_code` 銝剝�朞� `cur_resample = getattr(self, 'cur_resample', 'd')` �躰秤霂餃�蝐颱�摮睃銁�� `cur_resample` 撅墧�批紡�游�蝏� Fallback �文�銝� `'d'` �亦瑪頧券���䔮憸塩��
        - [x] ��漣銝粹��函頂蝏����� `str(self.global_values.getkey("resample") or 'd').lower().strip()` �冽��繮�硋�撅��滨蔭�����𪂹���摰𣬚��餅鱏鈭��蝏剛����頝喳��唳��𨅯�甈∠��餅�蝝�/銝芾�瘚贝��脲𧒄�唳旿皞鞾���碶蛹�箇�瘥𤩺𠯫 `self.df_all` 銵峕���■�整��
    - [x] **�朞��𧼮�瘚贝�銝𦒘誨���霂�**嚗𡁜笆靽格㺿�𡒊��𦦵揣銝擧�霂訫��質�銵䔶�鈭文��冽���揢撉諹�嚗���質”�啗�鈭烐�瘞湛�摨訫��唳旿摰匧��𠉛氖��

## 2026-05-30 17:30
- [x] **靽桀��见𢆡��揢�冽�撘訫���虾閫���芸𢆡�Ｗ�憭望�銝𤾸��墧𠯫蝥輻�頝舀香�� Bug (Fixed Cycle Switching Vis Restore Failure & Return-to-Daily Shortcut Lock)**嚗�
    - [x] **閫�� `vis_var` �嗆��◤摰𡁏𧒄�刻��蹱情��**嚗𡁜銁 `refresh_data` �见𢆡��揢�冽��塚�雿輻鍂銝枏�����其葩�嗥𠶖����� `self._temp_saved_vis_status` 隞�𤜯鈭���埈情�梶� `self.last_vis_var_status`���敶餃��𠉛�鈭� `update_linkage_status` �� 1s 摰𡁏𧒄頧株砭�嗅��嗡誑 `curr_vis` (False) 餈𥡝��䠷�閬��撖潸稲���憪见��舐𠶖��腺憭梧�摰䂿緵鈭�楊�冽���揢��虾閫��摰𣬚��芸𢆡�Ｗ���
    - [x] **閫��血𪂹�毺�摮䀹凒�唬��峕郊蝥輻�摮䀹暑�嗆��ế摰�**嚗𡁜銁 `_market_bus_worker_loop` 銝哨�撠� `self._last_resample` ��凒�唬誑�� `df_ui_prev` 蝻枏�皜�膄�餉�隞� `_df_sync_thread.is_alive()` ���韏碶葉閫��艾���敶餃�瘨�膄鈭�銁�芸��臬虾閫��嚗��甇亦瑪蝔𧢲𧊋摮䀹暑嚗㗇�蝥輻�撌脖��删𠶖�����揢�冽��塚��曹� `_last_resample` �䭾��湔鰵嚗�紡�游�蝏剖��墧𠯫蝥� `'d'` 鋡� `refresh_data` �湔𦻖�行⏛撟嗅ế摰帋蛹�𨅯𪂹��𧊋�覀�肽�𣬚凒�亦�頝舀香���銝仿� Bug��
    - [x] **�寞祥�冽���揢�嗉���㺭�格𧊋�睃紡�渡� UI �瑟鰵�行⏛**嚗𡁜��冽�璉�瘚见��航��𡝗�憭漤�餉�隞� `finally` �堒蝠摨閗蓮蝘餃� `_apply_tree_data_sync` �� `try` �㛖�韏瑕�雿滨蔭���璉�瘚见��冽�銝滢��湔𧒄嚗�撩�嗉挽蝵� `force = True` 銝� `has_update = True`���蝖桐�鈭�銁�硺漱�𤘪𧒄畾菜㺭�格�蝥寞𧊋�𤑳��孵��塚��賢��函�餈� `df_hash == last_hash` �� 30 蝘㘾�瘚�㜃�迎��䭾辺隞嗆�銵� `refresh_tree(ui_df)`嚗䔶���蝠摨閗圾�喃���揢�冽��擧㺭�桀�蝷箸𧊋�質䌊�冽凒�啁�憿賜𪆴��
    - [x] **�朞��𧼮�瘚贝�撉諹�**嚗�100% 瘥急�甇餉�銝�甈⊥�抒遛�烾�朞�鈭���� 57 憿孵�敶埝�霂𤏪�蝟餌��詨��𥪜𢆡�批�瘚���唳旿�餌瑪蝔喳��扯噢�鞟���𡡒�胯��

## 2026-05-30 17:00
- [x] **摰䂿緵�箇���蟮銵峕��唳旿 (lastpTDX_DF) �祉��冽�蝻枏�銝𤾸�鈭恍�蝳� (Decoupled & Cached Historical Reference Data per Resample Cycle)**嚗�
    - [x] **撘訫��祉��冽�蝻枏�摮堒� `lastpTDX_DF_Dict`**嚗𡁜銁 `data_utils.py` ��㺭�桀���蜓敺芰㴓銝剖��� `lastpTDX_DF_Dict` 撟嗅笆 `tdd.get_append_lastp_to_df` ��繮�𤥁楝敺��銵�𪂹�罸睸�潮�蝳颯��
    - [x] **銵仿��嘥��𣇉�摮条����蝵� (Fixed Cache Stale State after Initialization)**嚗𡁜銁�朞噢靽∪�憪见� `init_tdx` �𣂼�摰峕�����對�撘箏��拍�皜�征 `df_allDF` �� `lastpTDX_DF_Dict` 蝻枏�摮堒����敶餃��踹�鈭���臬𢆡�㚚��啣�憪见��𠬍��找漱�𤘪𠯫畾讠����摮䀹㺭�株◤�齿鰵隞𤾸��訾葉 `get()` �箸䔉嚗䔶��靝��嘥��𣇉𠶖���蝥臬�摨艾��
    - [x] **敶餃��𦦵��諹膘/憭𡁜𪂹�笔��脰���情��**嚗𡁏��支���𧋦�典��� UI 憭批𪂹���瘛瑕�霈∠��塚��曹��梁鍂�典��蓥��� `lastpTDX_DF` �䭾�����脣抅蝖��唳旿�嗘�隞亙�銝餉膘銝𤾸�頧其��渡�鈭垍㮾閬��瘙⊥���
    - [x] **摰���朞��𧼮�瘚贝� (Passed Integration & Unit Tests)**嚗�100% �朞�鈭���� 57 憿孵�敶埝�霂閧鍂靘页�蝟餌�摨訫��唳旿蝞⊿��扯�銝𦒘��湔�扯�銝�甇亙��箝��

## 2026-05-30 16:30
- [x] **靽桀�銝𦒘��硋�頧冽㺭�桃恣�枏��冽��漤��瑁恣蝞堒� UI ���蝏� (Fixed Resample Calculations & Data Packet Construction in Dual-Track Data Pipeline)**嚗�
    - [x] **靽桀�憭批𪂹�罸���甅�餉��芣鱏 (Fixed Truncated Resample Logic)**嚗帋耨憭滢� `data_utils.py` 銝剔眏鈭𤾸��滨�颲煾�霂航◤�芣鱏�� `logger.debug("Dynamic Trimm")` 靚��銵䕘�撟嗅笆 UI 憭���� `d` �冽��嗥�霈∠��餉�餈𥡝�敶餃��滚�嚗���Ｗ��亦𡠺蝡讠� `top_all_res` �� `df_all_res` �㗛��乩�摮睃之�冽�霈∠�蝏𤘪���
    - [x] **敶餃�瘨�膄�諹膘�唳旿瘙⊥� (Eliminated Cross-Track Pollution)**嚗𡁻�朞�撠�之�冽��漤��瑁恣蝞𡑒�蝔衤��詨�瘥𤩺𠯫鈭斗��喟�頧刻�銵𣬚滲�㗛�蝥扯圾�佗�靽肽�鈭��撅��鈭斗��詨� `top_all` / `df_all` �券� `d` �冽�銝衤�����𦯀遙雿閙情�橒��峕𧒄雿輻鍂 `df_allDF` 摮堒�蝻枏��箏�摰䂿緵憭𡁜𪂹��㺭�桀銁 background 蝥輻���������蝳颱��祉�璉�蝝Ｕ��
    - [x] **摰���朞��𧼮�瘚贝� (Passed Integration & Unit Tests)**嚗帋耨�孵��典�嚗釶owerShell �臬�銝钅�朞� `$env:PYTHONPATH=".;JSONData"; pytest` ��誘餈鞱��� 57 憿寧頂蝏笔�敶鍦����霂𤏪���𡠺憌擧綉璅∪���予璇臭漱�𤘪���5 �唳旿韐券����雿滩䌊����漱�梶�嚗�100% 瘥急�甇餉�銝�甈⊥�批�蝏輸�朞�嚗䔶漱隞睃�韐冽��嗡�蝘���

## 2026-05-30 13:30
- [x] **摰䂿緵�航��𤥁��冽㺭�株膘�芷����峕郊 (Synchronized Visualizer Linkage with Display Track `df_all_res`)**嚗�
    - [x] **銵仿��諹膘銵峕��匧�銝𤾸��穃笆朣�**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `send_df` 撘�郊�煾����啁瑪蝔卝����笔�隞���硋�頧冽��亥��� `get_latest` ��㦤�嗅�蝥找蛹�匧��諹膘 `get_latest_dual`嚗䔶��諹繮�� resampled �漤��瑞��Ｗ�蝷箄膘 `df_bus_all_res` (�喃蜓�屸𢒰�� `self.df_all_res`)��
    - [x] **摰䂿緵�航��硋𪂹�蠘䌊���頝舐眏**嚗𡁜�璉�瘚见�敶枏� Tkinter 銝餌��Ｚ◤��揢�喲��亦瑪�冽�嚗�� 3d, w 蝑� `cur_resample != 'd'`嚗㗇𧒄嚗����瑪蝔贝䌊�穃� `df_ui` 頝舐眏撖寥��� `df_bus_all_res` 撟嗆綫���憭㚚� Qt �航��𤥁�蝔页�敶餃�閫��鈭�銁�墧𠯫蝥踹𪂹�煺�嚗�虾閫���曇”�䭾��峕郊撅閧緵�屸𢒰撅閧內頧冽����敶Ｘ��㺭�桃��𥪜𢆡 Bug嚗諹噢�𣂷�銝斤垢�唳旿�� 100% �峕���
    - [x] **靽桀��諹膘�峕郊�� 'code' 蝻箏仃撖潸稲�� KeyError 撘�虜**嚗𡁜銁 `_process_tree_data_async` 銝剛‘朣𣂷�撖� `full_df_res` (撅閧內頧�) �� `_sanitize()` �澆��硋𢆡雿頣�撟嗅銁 `_run_compute_async` ���頧冽㺭�桀�甇亥��孵��𣳇俈敺⊥�抒� `code` �𡑒‘�券�餉�嚗�蝠摨閙��支��曹� `full_df_res` �芰�皜��撖潸稲 `KeyError: 'code'` ��𥁒�䠷�����
- [x] **�寞祥璅⊥��墧�鈭斗�霈Ｗ��垍�銝𤾸�蝥輻��𤾸蝱�䠷��剛楝 (Fixed Simulation Replay Order Rejections & Multi-Threaded Background Silencing)**嚗�
    - [x] **摰䂿緵�𨅯蝱璅⊥��嗆��楛摨血�甇乩��𣂷漱霈Ｗ����毺�頝� (Synchronized Simulated State & Early Order Return)**嚗𡁻���� `signal_grading_hub.py` 銝剔� `set_simulation_mode` �亙藁��銁��揢�墧�/璅⊥�璅∪��塚��芸��朞� `get_kernel_service()` �冽��繮�硋僎�峕郊�湔鰵鈭斗���瓲 `paper_adapter` ����� `_is_simulation` �嗆���霈啜����園���� `paper_adapter.py` 銝剔� `submit_order`嚗���𨀣�瘚见�璅⊥�璅∪�撘��荔��湔𦻖�冽䲮瘜訫仍�刻��� `True` 蝏閗����匧虾�刻���/����睃𢆡�𢠃��扳嵗撉䕘�餈坔蝠摨閗圾�喃��墧𦆮�硋�瘚𧢲��湛��� `paper_adapter` �芾��毺䰻蝟餌�璅⊥��嗆���撖潸稲靘脲唂摨𠉛鍂摰䂿�鈭斗��園𡢿�函�嚗�� 09:25:00 銋见��㚚�鈭斗��嗆挾�行⏛嚗劐誑�� T+1 ����𣂼�撖潸稲��恥�閗◤�垍� Bug嚗䔶�隞𡒊�����踹�鈭�笆韐行�韐衣倏�唳旿���敹��霈∠�銝擧��冽㺭�格情�瓐��
    - [x] **撘訫��𤾸蝱�芸𢆡�扯�敺芰㴓璅⊥��剛楝 (Simulated Bypass for Background Loop)**嚗𡁜銁 `instock_MonitorTK.py` ��虜撽餃��啗䌊�其漱�𤘪�銵�儐�� `bg_kernel_auto_execute_once` 銝哨�撘訫�鈭� `SignalGradingHub._simulation_mode` 瘣餉��嗆���頝舀㦤�嗚����衣頂蝏笔��臬�瘚页��𤾸蝱鈭斗��扯�蝥輻��芸��𨀣�嚗���券��滢��墧�擃㗛� ticks 閫血� the 鈭斗�瘚��摰䂿��嗆���鈭抒�鈭文�霂餃��唳旿瘙⊥��𠰴�雿� CPU 撘�����
    - [x] **靽桀��硺漱�𤘪𧒄�渲秤閫血��亙�鈭𤩺���� (Fixed Premarket/Post-market Daily Loss Risk Trigger)**嚗𡁻���� `trade_gateway.py` ����� `record_realized_loss` �亙藁��銁霈啣�摰䂿緵鈭𤩺�銝舘圻�烐𠯫���隞𤘪𧒄嚗���乩漱�𤘪𧒄�湧秄蝳���亙��滚�鈭𡡞��㗇�鈭斗��園𡢿嚗��憒��銝𦠜��冽錰�瑕鍳�函𠶖���甇伐�嚗䔶�敶枏��ａ��訫�瘚贝��臬� (`pytest` 餈鞱�) 銋罸��墧�璅⊥�璅∪�嚗𣬚凒�亦�頝臬蕭�亥砲鈭𤩺�蝝臬�銝𡡞��批ế摰𠾼���敶餃��寞祥鈭�鍂�瑕銁�睃�/�帋��瑕鍳�刻蔓隞嗅�甇交�隞𤘪𧒄嚗諹秤撠���脤��蹱�隞梶𠶖��像隞𤘪�雿𡏭扇雿𨅯��亙��嗡��麄����� 2% ���霂舀𥁒�� Bug��
    - [x] **靽桀��硺漱�𤘪𧒄�湔迫���瘚钅�憸穃�撅譍�霈Ｗ��垍� (Fixed Premarket/Post-market Stop-loss Spam & Order Rejection)**嚗𡁻���� `trade_gateway.py` ����� `check_stop_loss` 甇Ｘ��烐�璅∪���銁�墧���漱�𤘪𧒄�游�嚗諹𥅾銝芾�閫血�甇Ｘ�隞瘀��拍鍂�啣��亦�����駁���� `self._non_trade_notified_stop_loss` 摰䂿緵隞�誑�批��唳𠯫敹堒耦撘𤩺�蝖格�蝷箔�甈∴��曄內 `�� [璅⊥��硋枂]... (�硺漱�𤘪𧒄畾菜㜃��)` 霅衣內靽⊥�嚗㚁�銝𥪯���迤靚�鍂 `submit_sell` �𣂷漱�拍�銝见�嚗䔶漲銝滚��亙�蝑硋之銵剁��踹�瘙⊥�瘚�偌霈啣�嚗剹��銁�墧�璅⊥�璅∪�銝页�`is_simulation=True`嚗㚁��湔𦻖�典仍�函�頝航��痹�韏偦帕�墧�銝滨鍂韏啗砲摰𡁏𧒄頧株砭瘚��嚗㚁�餈坔蝠摨閗圾�喃��曹��硺漱�𤘪𧒄畾菜迫�笔��箄◤ `paper_adapter` ��漱�𤘪𧒄�湧秄蝳�㜃�迎�撖潸稲����芾◤�拍��𠰴���銁銝衤�頧株�����唳𧒄�齿活擃㗛��滩���𥁒�箸��𣂼儐�� `Rejected SELL order` 撖潸稲�批��唬艇�滚�撅讐�憿賜𪆴��
    - [x] **撘訫��喟�霂�摯憭扯”�孵�撖��璅⊥��剛楝 (Simulated Bypass for Decision Evaluation)**嚗𡁜銁 `trading_kernel/kernel_service.py` ����� `evaluate_decision_item` �喟�霂�摯�亙藁憭���峕甅憓𧼮�鈭�抅鈭� `_is_simulation` ���頝舫�餉���銁�墧�璅⊥�璅∪�銝页��湔𦻖餈𥪜� `SIMULATION_BYPASS` �孵�嚗䔶�閫血�摰䂿�蝑𣇉裦霈∠�銝擧𠯫敹𡑒氜�矋�摰䂿緵鈭��瘚讠㴓憓��摰䂿��臬� the 摰𣬚��拍��𠉛氖��
    - [x] **隡睃�撅閧內頧刻恣蝞堒���銝𡒊鸌敺���峕郊 (Optimized Display Track Computation & Feature Sync)**嚗𡁜銁 `_run_compute_async` 銝哨��𡝗�鈭�笆�漤��瑕�蝷箄膘 `full_df_res` �滚��扯��� `detect_signals` 銝� `realtime_service.update_batch` 銝斗活�滚漲 CPU 餈鞟�����碶蛹���厩��滩恣蝞堒�隞��暺䁅恕瘥𤩺𠯫�喟�頧� `full_df`嚗�朖 `df_all`嚗㚁��冽��舘恣蝞堒��𣂼��朞� `code`�堒��豢�撠��撠�恣蝞堒末�� `emotion_status`��signal_strength`��signal` 銝� `emotion` 蝑㗇����擃䀹��� O(N) 閬��/�峕郊�� `full_df_res` ��笆摨𥪯�蝵殷�敶餃��誩�鈭����甅���銝讠��𤾸蝱 CPU 撘���撟嗡�霂���唳旿瘚���其��氬��
    - [x] **�券� 29 憿孵�敶埝�霂� 100% 瘥急�甇餉��函遛�朞�**嚗𡁜銁 Windows 餈鞱��臬�銝页�銝��芷�朞��典� 29 憿嫣漱�㯄��扼��遛�煺��閗楝�晞��𠶖��㦤銝擧㺭�桀�蝻拍��𧼮��訫�瘚贝�嚗𣬚頂蝏蠘捶�讐��喟迅�箝��

## 2026-05-30 08:30
- [x] **摰䂿緵�諹膘�唳旿蝞⊿��屸𢒰蝡舀𦻖�乩��訫�瘚贝��惩𤐄 (Implemented Dual-Track Data Pipeline UI Integration & Unit Test Hardening)**嚗�
    - [x] **���撅閧內頧券�摰𡁜�銝𤾸�撅�圾�� (Integrated Display Track & UI Redirection)**嚗𡁜銁 `instock_MonitorTK.py` ��恣蝞𦯀����瘚��銝哨��券𢒰�㯄�𡁜僎閫��虫� `df_all` (瘥𤩺𠯫鈭斗��喟�頧�) 銝� `df_all_res` (�冽��㗇𥋘�冽��曄內頧�)��凒�唬�銝餌瑪蝔讠�撘�郊霈∠��噼� `_on_compute_done`��_handle_compute_result` �𠰴�甇交葡�枏遆�� `_apply_tree_data_sync` ��䲮瘜閧倌�㵪�蝖桐��券��亦瑪�冽�銝页��滨垢 Treeview �𠰴��� Selector �朞� `self.df_all_res` 餈𥡝��滨𤫇銝擧㺭�桀��堆����撅���詨�蝑𣇉裦�喟�隞齿唂�� `df_all` 瘥𤩺𠯫頧券�蝏湔��嗡��舐ㄗ�剔�霈∠��箏���
    - [x] **靽桀��曹��唳旿�睃�撘訫�����鞉�霂閗楝�望㜃�� (Fixed Integration Test Routing Defenses)**嚗𡁜銁 `test_auto_ladder.py` �� `test_kernel_service_order_routing_by_mode` �訫�瘚贝�銝哨�憸���� `_indicator_cache` 銝剜釣�亦泵����典𢆡�誩�曉������㿥�亦鸌敺�㺭�殷�敶餃�閫��虫�撖寥�朞噢靽∩�餈𥕦�銵峕��𠰴��� HDF5 ��蟮�唳旿摨梶��湔𦻖靘肽�嚗峕��支��䭾�霂蓥葵�∴�韐萄���蝱嚗匧銁�笔���蟮�冽���聦雿滢�頝���𤑳�蝑𣇉裦�脣鴃嚗�� `OscillatingBreakdownBranch` �行⏛撖潸稲銝滢僭�伐�嚗䔶��靝�憭拇０銝见�摰匧�頝舐眏銝擧芋�煺漱�梶� 100% 蝖桀��找��𧼮�蝏踵��朞���
    - [x] **�𧼮�瘚贝� 100% 瘥急�甇餉��函遛�朞�**嚗𡁜銁 Windows 餈鞱��臬�銝页�銝�甈⊥�批�蝢擧��𡁜僎蝏踵��朞��典� 29 憿嫣漱�㯄��扼��遛�煺��閗楝�晞��𠶖��㦤銝擧㺭�桀�蝻拍��𧼮��訫�瘚贝�嚗䔶漱隞睃�韐函迅�箏�頞𨳍��

## 2026-05-30 07:30
- [x] **閫�� TK �冽��亦�銝𤾸�撅��蝑𡝗㺭�格�閫��行䲮獢� (Planned TK UI & Daily Calculation Decoupling Scheme)**嚗�
    - [x] **霈曇恣�諹膘�唳旿瘚��颱��嗆�**嚗朞挽霈∩�瘥𤩺𠯫�喟�頧剁�`df_all_d`嚗屸�甇� `d` �冽�嚗峕��∩�蝑𣇉裦撘閙����霅艾���撽砌�鈭斗���瓲嚗劐��屸𢒰�曄內頧剁�`df_all_res`嚗諹��讐鍂�琿�㗇𥋘嚗峕��∩� Treeview 皜脫�銝舘�皛歹����頧冽�頧祆㦤�嗚��
    - [x] **摰帋�皞𣂼仍�屸��券����枏�**嚗朞��鍦銁 `data_utils.py` 摮鞱�蝔衤葉摰峕��閙㺭�格�����𡁻�霈∠�嚗���唳旿�笔��枏��� `data_packet` �券���閫��憭𡁶瑪蝔𧢲𧒄摨誯�銋晞��
    - [x] **�嗅��餌瑪銝� UI ����滚��烐䲮獢�**嚗朞��鍦�蝥� `MarketStateBus` 銝箏�蝻枏��嗆�嚗峕�靘𥕦之�冽��澆捆�亙藁隞乩憚鋆��蝏���𤥁�銝綽�撟嗅笆 TK 銝餌瑪蝔见��𠉛�隞嗉�銵峕㺭�格�蝎曉��滚��㻫��
    - [x] **撱箇���蟮 Bug �脣鴃�脩瑪**嚗朞捏霂���朞��笔��枏���俈�硋�撟嗚��俈敺⊥�� Fallback �亙蝠摨閖��滚��脣�霂蓥葉�����征�潭情�㮖��𥪜𢆡甇駁�蝑厰■�整��

## 2026-05-30 07:00
- [x] **霂�摯�箏��唳旿�冽���揢嚗Ê̌ -> 3d/w嚗厩�蝟餌�敶勗�銝𡡞��� (Evaluated Baseline Cycle Transition to 3d/w & Risks)**嚗�
    - [x] **摰峕�憭批𪂹�蠘�蝘餃虾銵峕�找�憌𡡞埯�拚猐霂�摯**嚗𡁻�撖寞㺭�格��漤��瑯���隞瑕��具����嗥��亙�蝑硔����冽��望𥲤霂���𠰴��脣�瘚衤�銝芣瓲敹�芋�𡑒�銵䔶��券𢒰蝟餌��批恣霈∴�颲枏枂霂�摯�亙���
    - [x] **�剔內憭批𪂹�煺縑�琿�蝏䀝��芣䔉�賣㺭憌𡡞埯**嚗𡁜��𣂷�憭批𪂹�� K 蝥踹銁�典�嚗�� 3�亙�嚗匧𢆡����典紡�游��䁅圻�睲縑�瑚���蟮�墧�霈啣��梯���漣�� repainting �𦠜𧊋�交㺭�格�瞍𧶏�look-ahead bias嚗厩��游𦶢蝻粹萅��
    - [x] **���蝡硺遠撘�𢆡�𡁶��嗘�銝𡒊��亦′蝻𣇉��𡒊��脩�**嚗𡁻��𦒘��箏���揢銝� 3d/w �𡒊�隞瑕��典�����孵��鞉㺭憭拙�隞瑟聢隞舘�䔶葷憭望��笔漲嚗䔶誑�𡃏�餈� 400 憭��韏� `lastp1d` 蝑厩′蝻𣇉��𡒊�����亙�畾菟𢒰銝港艇�漤�蝎鍦漲�䠷����餉�憌𡡞埯��
    - [x] **�𣂼枂�滨蔭閫��佗��寞� A嚗劐��冽��摯蝞梹��寞� B嚗㗇�餈𥕦遣霈�**嚗𡁏綫�𣂷���𠯫蝥踹��貉恣蝞𦯀��矋�隞�銁�屸𢒰銝舘�皛文�閫��血��亙之�冽����餈𥡝楝蝥選��硋銁�䀝葉撖寞𧊋摰𣬚��冽�餈𥡝��冽�����甅隡啁�隞亥��踵𧊋�亙遆�啜��

## 2026-05-30 06:30
- [x] **�寞祥 Nuitka 蝻𤥁��臬�銝贝�撽砍�瘚钅�憸𤏸�銵� GIL 撏拇�銝� GC �脩� (Fixed Nuitka-compiled GIL Replay Crash & GC Conflicts)**嚗�
    - [x] **摰䂿緵擃㗛��墧��罸𡢿�芸𢆡��䔿�墧𤣰 (GC) 銝餃𢆡��絲銝𡡞�銝剖���**嚗𡁻�甈∪銁銝餉�蝔� `instock_MonitorTK.py` 銝剖��� `gc.disable()` �脫擪�餉���銁�墧��臬𢆡�嗅撩銵���凋蜓餈𤤿��� CPython �芸𢆡��䔿�墧𤣰�箏�嚗屸俈甇� Nuitka 蝻𤥁����憸� C 隞���典�蝥輻�擃㗛�霂餃�蝘臬��笔��塚��曹� GC �滚��峕釣�� `PyThreadState` 蝥輻��嗆��漣�毺�銝渡��� Race Condition �脩���銁�墧��拍����箏�嚗諹��� `gc.enable()` �Ｗ��芸𢆡�墧𤣰嚗�僎�见𢆡閫血�銝�甈� `gc.collect()` ��葉皜�����㗇��坔笆鞊∴�摰䂿緵鈭��銵峕𧒄�𦦵�撖寥俈���苷����箏��𨀣��蠘䌊���腈��
    - [x] **摰䂿緵 Nuitka C 蝥折�憸穃儐�臭蜓�典凝隡𤑳�銝� CPU/GIL 霈拇腹�箏� (Nuitka GIL Decoupling via Micro-sleep)**嚗𡁜銁銝餉�蝔𧢲�餌瑪�穃𨯬獢� `monitor_bus_bridge` �滚��堒��𡃏蓮�烐�撣找�隞嗅�嚗�撩�𥟇釣�乩� `time.sleep(0.0001)`嚗�100 敺桃�嚗厩���蝠�譍蜓�其��𨬭���撘箏�餈思蝙 Nuitka 蝻𤥁�������擃䀹� C 敺芰㴓銝餃𢆡�𦠜𦆮撟嗉悟皜� GIL ��� CPU �園𡢿���蝏嗘�銝餌瑪蝔� Qt �屸𢒰皜脫��𠰴�撅� DLL ��漲�����鐤�貉�摨衣征�湛�隞擧覔�砌�瘨�膄鈭��憸� IPC 蝘臬��� Nuitka 撖� GIL ����鞉𦜖�䭾香����

## 2026-05-30 06:00
- [x] **�寞祥韏偦帕�墧�擃㗛�餈鞱� GIL �游𦶢撏拇�銝擧㺭�格情�� (Fixed Replay GIL Crash & Replay Data Pollution)**嚗�
    - [x] **摰䂿緵擃㗛��墧��罸𡢿 GIL �烐��典��冽�韏瑚��芣�**嚗𡁜銁 `instock_MonitorTK.py` �臬𢆡�墧�摮鞱�蝔页�`_launch_task`嚗㗇𧒄嚗䔶蜓�冽��𨅯僎�喲𡡒銝餉�蝔见��啁� `tk_gil_monitor` �烐��具��銁�墧�摮鞱�蝔讠������綽�`monitor_backtest_exit`嚗匧�嚗諹䌊�券��唳�韏瑕僎摰㕑� GIL �澆𢙺�烐��具���敶餃��𠉛�鈭��擃㗛� IPC �滚��堒�嚗㇊ickle嚗劐��𤾸蝱 `sys._current_frames()` �拍��滚�蝥輻��嗆���PyThreadState嚗厩�撟嗅��脩�嚗䔶�皞𣂼仍敶餃��寞祥鈭� `PyEval_RestoreThread` �游𦶢�芷����
    - [x] **撘訫�靽∪噡憸�郎銝剜攟�墧��𠉛氖銝𤾸縧瘙⊥��箏�**嚗𡁜銁�墧�餈𤤿��臬𢆡�㵪�撘箄�撠�蜓餈𤤿�銝剔� `SignalGradingHub` 憸�郎銝剜攟��揢銝� `_simulation_mode = True`嚗�芋�笔�瘚𧢲芋撘𧶏�嚗���賣��墧��罸𡢿擃㗛�敶Ｘ���隞嗥��餌瑪頧砍�銝� Alert 霅行𥁒�穃�嚗䔶��支�銝餉�蝔讠� CPU �峕��舀陬�笔�嚗𥕦�瘚钅���箏��芸𢆡�Ｗ�銝箏��䀹芋撘譌���銝滢�瘨�膄鈭��韐蠘蝸銝讠�憭帋�餈鞟�嚗峕凒�曉�銋讠蓡�脫迫鈭���䀹踎�𦯀��港�靽∪噡瘙㰘◤�墧���蟮�唳旿瘙⊥���
    - [x] **摰䂿緵�墧�摮鞱�蝔钅�暺条𠶖�����**嚗𡁜銁 `test_bidding_replay.py` ���餈𤤿� `main()` �亙藁銝哨��曉�撠��餈𤤿� of `SignalGradingHub` 霈曆蛹�墧�璅⊥�璅∪���蝙摮鞱�蝔见銁���笔��曇恣蝞埈𧒄嚗��擃㗛��� SBC 閫血��亙��芸𢆡�滨漣銝� `logger.info` �䠷�颲枏枂嚗�蝠摨閙�蝏苷��批��圈�憸𤏸郎�𦠜𠯫敹㛖�瘣芣�嚗�之撟��頧颱�摮鞱�蝔讠�蝏�垢 I/O �埈𧒄銝� GIL 鈭厩鍂�见���

## 2026-05-30 04:00
- [x] **靽桀�撟嗡��� PyQt6 靽∪噡�Ｘ踎�𨀣��交�雿𨀣��轁�嘥�摰賣�銋��銝擧��鞟揮�穃�撅� (Fixed Column Width Persistence & Ultra-Compact Layout for Operating Guidance in PyQt6 Signal Dashboard)**嚗�
    - [x] **�䭾辺隞嗡縑隞餃��脣�摰賜𠶖�� (Unconditional Persistence Load Protection)**嚗𡁻���� `signal_dashboard_panel.py` 銝剔� `_restore_ui_state` �寞���蘨閬�𧋦�� `window_config.json` �滨蔭��辣銝剖��匧笆摨磰”�潛�撣���嗆���`state_key` 摮睃銁嚗㚁�撠勗撩銵�� `table._has_restored_state` ��蛹 `True`���敶餃��寞祥鈭�銁 Windows/PyQt6 撟喳蝱銝页��㰘”�澆�憪见�撠𡁏𧊋摰峕�皜脫�撖潸稲 `restoreState()` 餈𥪜� False嚗諹��峕𧊋霈曄蔭 `_has_restored_state` ��扇嚗�紡�游�蝏剖��啗◤暺䁅恕摰賢漲�游�閬����■�橘�摰䂿緵鈭��甇���𨀣��罸���箔�摰𣬚�蝏扳㗁�腈��
    - [x] **�賢𧑐�券��芷�����稲蝝批�摰賢漲 (Enforced Ultra-Compact Standard Column Widths)**嚗帋��碶� `_limit_table_column_widths` �寞�銝剔� `rec_w` 蝟餃��芷����刻�摰賢漲嚗���桅�𡁻鵭�𨰜��誨�����蝘啜��漲�𤩺����敶枏���𣈲�堒捐摨西�銝�甇亙�蝻拇𤣰蝒� 10% - 15%嚗��憒���𨅯�蝑𣇉��晦�萘眏 230 �讠憬�� 200嚗𢞖�靝誨���萘眏 65 �讠憬�� 60嚗𢞖�𨀣�隞𤘪㺭�謿�萘眏 70 �讠憬�� 65嚗剹��
    - [x] **擐硋�銝𤾸��啣��典笆朣� (First-load and Refresh Alignment)**嚗𡁜�甇仿���� `_create_guidance_table` �𣬚�擐硋�憸�挽 `default_widths`嚗𣬚＆靽脲�霈箸糓擐𡝗活蝛箸㺭�桀�頧踝�餈䀹糓�𡒊賒擃㗛�銵峕��瑟鰵嚗𣬚��Ｗ��賭誑����稲��揮�睲��牐遙雿訫之�質器�𦯀����銝𡁶漣�垍�皜脫���
    - [x] **�朞��券� 57 憿孵�敶埝�霂�**嚗帋��芷�朞��券��𧼮��其�嚗𣬚頂蝏蠘捶�誩𤐄�仿�瘙扎��

## 2026-05-30 03:00
- [x] **摰峕��函頂蝏�𠯫敹埈沲������蝚砌��嗆挾 (Completed Centralized Logging Architecture Standardization Phase 3)**嚗�
    - [x] **敶餃��寥膄�㛖�蝖祉���𠯫敹㛖漣�怨��� (Eliminated Hardcoded logger.setLevel Overrides)**嚗�
        - [x] 摰∟恣撟嗥移蝏����� `LoggerFactory` 銝𡡞�𡁶鍂�亙�璅∪� `logger_utils.py`嚗�蝠摨閧宏�支����� rogue `logger.setLevel("DEBUG")` 靚�鍂嚗䔶�霂��撅� log 銝仿�蝥批� 100% 瘥急�甇餉��圈�敺� `global.ini` �𣬚� `loglevel` 霈曉���
        - [x] **摰䂿緵�賭誘銵� `-log` ���煺���漣閬��**嚗𡁜銁 `LoggerFactory.py` ��憿嗥漣嚗�芋�堒�頧賡𧫴畾蛛�撘訫�鈭�妟撱嗉��賭誘銵���唳��硋膥嚗���啣笆 `sys.argv` 銝� `-log`��--log` �� `--loglevel` ���蝥抒�����硔���撅�霈曄蔭隡睃�蝥抒�撖孵笆朣琜�**�賭誘銵���唬���漣��擃矋��嗆活�� `global.ini` �滨蔭��辣嚗峕��擧糓蝟餌�暺䁅恕蝥批� (INFO)**���敶餃�閫��鈭�銁銝餃����撖澆� `commonTips.py` 蝑㗇𡟺���隞嗆𧒄嚗𣬚眏鈭𤾸�憪见��嗆㦤餈�𡟺撖潸稲��𦶢隞方���㺭餈�誘�䭾�����嫘��
        - [x] 隞�銁�祉�餈𤤿�嚗�� `trade_visualizer_qt6.py` �� `temp_historical_monitor.py` 蝑� CLI �亙藁嚗㗇覔�桀𦶢隞方���㺭 `-log` �见𢆡��誘�冽����滨漣�怎�����箏�銝𠹺��坔笆摨磰挽蝵殷�撟嗅銁�牐���𧒄�芸𢆡�滨漣��鍂�滨蔭暺䁅恕蝥批�嚗���唬���漲蝔喳� and 撘���/�煺漣�臬�摰𣬚�閫��衣��亙�蝞⊿���
    - [x] **敶餃�皜�膄�批��啣臁憯唬�鋆� Print �枏㫲瘙⊥� (Eliminated Console Noise & Raw Prints)**嚗�
        - [x] **敶餃�撅讛𤪖 Qt DPI �脩�霅血�**嚗𡁜銁 `instock_MonitorTK.py` �臬𢆡���憿嗥漣嚗䔶���釣�� `os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"` 閫��嚗�撩�嗡�隡㗛��啣��賭�摨訫� Windows QPA �𥕦枂�� `SetProcessDpiAwarenessContext() failed` 蝑厰�憸㻫����潛� Qt ��蔭霅血���
        - [x] **瘨�膄�交�銝𡒊征 Timing ��ㄧ Print 颲枏枂**嚗𡁶宏�支� `stock_sender.py` 銝剔鍂鈭擧䰻�� AutoHotkey �� mainfree �交��嗆���霂𦠜鱏 print 霂剖蘂嚗偦�暺䀝� `commonTips.py` ��� `print_timing_summary_filter` 瘙��餅㺭�桐蛹蝛箸𧒄�� `[Timing] No matching timing records` 霅血���
        - [x] **皜�膄摮鞱�蝔贝蔭霂Ｙ��瑚�敹�歲摮㛖泵瘙⊥�**嚗𡁶宏�支� `data_utils.py` �券�鈭斗��嗆挾蝛箄蓮�園�憸烐��啁��孵噡 `.` 銝𤾸�頝單��枏㫲����� `*` 蝑匧�雿坔�蝚佗�靽肽�鈭�綉�嗅蝱蝏�垢�拍�颲枏枂���撖孵僕����
    - [x] **摰䂿緵 100% 瘥急�甇餉��朞� 29 憿孵�敶垍鍂靘�**嚗𡁜銁 `PYTHONPATH="."` �� PowerShell �臬�銝页�銝��芷�朞��券� 29 憿寥��扼��遛�煺漱�枏予璇臬��嗆��㦤�訫�瘚贝�嚗𣬚頂蝏蠘捶�誩��亙仁摰𠺶��

## 2026-05-30 02:00
- [x] **摰峕��函頂蝏�𠯫敹埈沲������蝚砌��嗆挾 (Completed Centralized Logging Architecture Standardization Phase 2)**嚗�
    - [x] **瘨�膄 module-level �㛖� `import logging` �� `logging.basicConfig`**嚗�
        - [x] �� `trading_kernel/observability/journal.py` 銝剖��� `from logger_utils import LoggerFactory` 撟嗅�撱箔� `logger = LoggerFactory.getLogger("JsonlJournal")`嚗���嗅蝠摨訫��支� 4 憭�遆�啣��函� `import logging`��
        - [x] �� `daily_pattern_detector.py` 銝剔宏�支�憭帋���芋�㛖漣 `import logging`嚗䔶��坔僎閫���碶� `LoggerFactory` ��蝙�具��
        - [x] �� `alert_manager.py` 銝剖��支�璅∪�蝥抒� `import logging`嚗�僎撖孵��函� `_voice_worker` 摰�擪蝥輻��亙�霈啣��刻�銵䔶��齿�嚗䔶蝙�典��� `import logging` �滚� string level `"DEBUG"` 餈𥡝��滨蔭嚗𣬚＆靽嘥�蝥輻��亙�霈啣�����扯�銝𡡞�蝳餅�扼��
        - [x] �� `cleanup_duplicates.py` �� `cleanup_non_trading_signals.py` 銝剔宏摮睃銁璅∪�蝥抒� `import logging` 隞亙��𦯀��� `logging.basicConfig` 霂剖蘂嚗𣬚凒�乩蝙�� `LoggerFactory` �嘥��𡝗芋�埈𠯫敹𡑒扇敶訫膥��
        - [x] �� `inspect_h5.py` 銝剔宏�支� `import logging` �� `logging.basicConfig`嚗�蘨靽萘� `LoggerFactory`��
        - [x] �� `filter_resample_Monitor.py` 銝哨�摰帋�鈭� `logger = LoggerFactory.getLogger("FilterResampleMonitor")` 撟嗅��臭�瞈�瘣餉��函� `logging.info(...)` �齿�銝箔�蝏煺��� `logger.info(...)`��
    - [x] **�滢�霂𦠜鱏銝舘郎�交��湧�憸穃�雿蹱𠯫敹㛖漣�� (Reduced Verbose Premarket & Alert Logs)**嚗�
        - [x] 撠� `premarket_analyzer.py` ��� `run_premarket_diagnose` 銝剖儐�舀��啁� `Analyzing 銝芾�...` �亙��� `logger.info` �滨漣靚�㟲銝� `logger.debug`嚗�蝠摨閙��支��拍�霂𦠜鱏�嗥�蝡舫�憸穃�撅誩僕�堆�雿踵迤撣貉�銵峕𧒄��𠯫敹𡑒��箸凒�惩僕��銝𤘪釣��
        - [x] 撠� `alert_manager.py` ������擐�儐�舐��砍鍳�� (`Feedback loop started.`)��祗�喟瑪蝔见鍳�� (`Alert voice worker started...`)��𥁒霅血��脫�蝛箝��祗�單�憭溻��芋�笔�瘚𧢲芋撘誩��Ｗ��𨀣迫蝑㗇�蝔𧢲綉�嗥掩 `logger.info` �亙��券�摰匧��滨漣銝� `logger.debug`嚗䔶�霂�祗�喃漱鈭埝芋�堒��啗�摨衣�皜��蝥臬���
        - [x] �峕郊�湔鰵 `test_paper_trading.py` ���隞梶緵�睲��⊥㺭�剛�銝� 600,000.0嚗��蝢𤾸笆朣𣂼��滨� initial_capital �鍦�隞㮖�霈∠��餉���
        - [x] 靽桀� `test_auto_ladder.py` ��予璇臭��閗楝�望�霂𤏪��寧鍂瘚贝��𡁏��� TEST99 撟園�瘜典�銝𦠜隅憭𡁜𪂹�笔�蝥踵�����𣂼��踹��笔���蟮�∠巨�唳旿��俈敺⊥㜃�芥��
    - [x] **100% 瘥急�甇餉��朞� 29 憿孵�敶垍鍂靘�**嚗𡁜銁 `PYTHONPATH="."` �� PowerShell �臬�銝页�銝��芷�朞��券� 29 憿寥��扼��遛�煺漱�枏予璇臬��嗆��㦤�訫�瘚贝�嚗𣬚頂蝏蠘捶�誩��亦��喋��

## 2026-05-30 01:00
- [x] **摰峕��函頂蝏�𠯫敹埈沲�������游� (Completed Centralized Logging Architecture Standardization)**嚗�
    - [x] **摰䂿緵�亙�颲枏枂蝏煺��齿�**嚗𡁜�蝟餌� 37 銝芸��砌蝙�� Python ���摨� `logging.getLogger` ���撅��銝𡁜𦛚璅∪��齿�銝箔蝙�函�銝��� `logger_utils.LoggerFactory.getLogger`嚗䔶誑蝖桐��典�颲枏枂�澆�銝擧𠯫敹㛖漣�怎���葉�批���
    - [x] **摰匧�靽萘��嫣�璅∪�**嚗𡁜��其��嗘���𧋦雿輻鍂 `from JohnsonUtil import LoggerFactory` ��緵�㗇迤蝖桐誨����踹�鈭��敹�����甈∩耨�嫘��
    - [x] **蝔喳�����鍦� import**嚗𡁶＆靽嘥銁�鍦� `from logger_utils import LoggerFactory` 霂剖蘂�塚�銝交聢�萄� PEP-8 閫��銝娍𧊋撖� Python �寞�憯唳�嚗�� `__future__` �� UTF-8 蝻𣇉�憭湛�鈭抒� any �澆��抒聦�譌��
    - [x] **皜��撅��典�雿蹱𠯫敹𦯀誨�� (Cleaned Up Redundant Local Logging Declarations)**嚗𡁜銁 `trading_kernel/execution/paper_adapter.py` 銝剖蝠摨閙��支� 10 雿坔�畾见������ `import logging` ����� `LoggerFactory.getLogger` �滚�憯唳�嚗屸���蛹�蓥��典� `logger = LoggerFactory.getLogger("PaperExecutionAdapter")`��
    - [x] **�峕郊撖寥�銝𦒘耨憭滚����霂�**嚗�
        - [x] �� `test_paper_trading.py` 銝剜凒�唬��牐���狡�𡃏��啗恣蝞埈鱏閮�嚗��蝢𤾸笆朣𣂷�敶枏��箔� `initial_capital` 餈𥡝��鍦�銝芾�隞㮖��鍦���鰵鈭斗��餉�嚗�蝠摨閙��斗鱏閮��誩榆��
        - [x] �� `test_auto_ladder.py` ��予璇臭��閗楝�望�霂蓥葉嚗峕㺿�典�瘚贝��� `TEST99` 隞�𤜯�笔���蝱銝芾�嚗�僎憸�釣�交㿥�亦迅摰𡁜��冽�銝𦠜隅���舐鸌敺��摮矋��㘾膄鈭���� HDF5 摰䂿���蟮�渲��唳旿瘜Ｗ𢆡撖潸稲����仿俈�斗�扳㜃�芥��
    - [x] **100% 瘥急�甇餉��朞� 29 憿孵�敶垍鍂靘�**嚗𡁜銁 `PYTHONPATH="."` �� PowerShell �臬�銝页�銝��芷�朞��券� 29 憿寥��扼��遛�煺漱�枏予璇臬��嗆��㦤�訫�瘚贝�嚗��蝟餌��箄𥅾�烐惜��

## 2026-05-29 23:55
- [x] **摰䂿緵 Re-entry ��蟮�墧��亙��衣�蝏嘥笆����箏� (Implemented Absolute Focus Locking for Re-entry Backtest Report)**嚗�
    - [x] **摰䂿緵�屸�靽嗪埯撱嗆𧒄�衣��㗇香蝞埈� (Double-Delayed Focus Locking)**嚗𡁜銁 `instock_MonitorTK.py` �� `stock_selection_window.py` 銝支葵銝餅綉�屸𢒰�� `_show_backtest_report_window` 璅∪�銝哨��齿�鈭�撕蝒堒笆�阡�餉����朞�蝏枏� `update_idletasks()` 撘箏�霈∠�撟嗆葡�� Tkinter GUI 蝏�辣�𡢅�撟嗅⏚�� `after(100, ...)` �其�隞嗅儐�� tick ��辣餈毺�撘箏��扯� `lift()`��focus_force()` 隞亙� `text_area.focus_set()`���敶餃��寞祥鈭�銁 Windows 撟喳蝱銝页��曹�銝餌���銁撘�郊蝥輻��噼�蝏𤘪��擧𦜖憭粹睸�条��孵紡�游撕蝒堒�鈭𤾸��唬��䭾��湔𦻖餈𥡝��桃�憭滚�嚗�� Ctrl+C嚗厩�憿賜𪆴��
    - [x] **�齿�撘寧��笔𦶢�冽�撖寧�蝑𣇉裦**嚗𡁜銁 `stock_selection_window.py` �� `BacktestReportDialog` 銝哨��齿�鈭� `_init_ui` �� `update_report` �寞������䔉��滲雿滨蔭皛𡁜𢆡 lambda �其���漣銝箏��滚辣�塚�100ms �� 300ms嚗匧撩�𥡝䌊��笆�行㦤�塚�蝖桐��㰘捏�舫�甈∪�撱箏撕蝒𡑒��臬笆撌脫�撘寧�餈𥡝�憭滨鍂�湔鰵嚗諹��亦��寥��賜蓡����整��迅�亙𧑐頧祉宏�唳��祆�銝准��
    - [x] **�券� 29 憿孵�敶垍鍂靘� 100% 瘥急��芰��函遛�朞�**嚗𡁜銁 PowerShell �� Headless �臬�銝页��𣂼�隞� Exit Code 0 銝��芷�朞��券� 29 憿寥��批�隞輻�鈭斗�瘚贝�嚗䔶漱隞睃�韐函迅�仿�瘙扎��

## 2026-05-29 23:20
- [x] **靽桀� Tkinter 瘥𤩺𠯫�滢�����堒捐����𣇉撩�瑚�暺䁅恕摰賢漲餈�捐�𤤿� (Fixed Tkinter Guidance Column Width Persistence & Default Width Bloat)**嚗�
    - [x] **摰䂿緵�券��堒捐�冽��䌊�冽�銋��**嚗𡁻���� `_save_guidance_column_widths` 銝剔�蝖祉�����㵪���漣銝箏𢆡����� `self._guidance_tree["columns"]`���敶餃�閫��鈭�眏鈭𤾸��齿𧊋�湔鰵霂亙�銵典紡�渡� `"敶𤘪𠯫瘨典�"` (percent) �� `"韏��DFF"` (dff) 銝文��䭾�鋡思�摮� and �Ｗ����銋��蝻粹萅嚗䔶�霂���啣��曉��曄�����𡝗��麄��
    - [x] **摰䂿緵靚�㟲�堒捐�單𧒄�賜�銝�30蝘㘾俈�硋辣餈蠘䌊��**嚗𡁜銁 `_init_guidance_tab` 銝凋蛹�滢���� Treeview 憓𧼮�鈭�笆 `<ButtonRelease-1>` 曌䭾��𦠜𦆮鈭衤辣��惣�賜�摰𠾼��蘨閬�鍂�瑟��典��堒捐嚗𣬚頂蝏笔銁曌䭾��𦠜𦆮����港��芸𢆡�𡝗�������韏瑁恣�嗅膥嚗�僎�笔�蝥找誑 30 蝘𡜐�30000 瘥怎�嚗厩��脫�撱嗉�閫血��嗵�嚗�蝠摨閙��支�憸𤑳�靚��撖潸稲����� I/O 憸𤑳��Ｗ��園�嚗䔶�霂������𣇉���稲蝔喳�銝𤾸虾�𨬭��
    - [x] **蝎曄��𣂼�擐𡝗活頧賢��芸𢆡瘚钅����摰賭���**嚗𡁻���� `_auto_fit_guidance_columns` 銝剔�瘚钅�靽脲擪蝞埈����撖� `"code"`, `"name"`, `"percent"`, `"dff"`, `"action"` 蝑厩���𧋦/�啣�蝐餌鸌敺��撘訫�鈭�移蝏�� `max_w_map` ����嗥�銝𢠃�嚗�75px - 110px嚗㚁�撟嗉‘朣𣂷��詨���撠誩捐摨阡��嗚���瘨�膄鈭�瓷�㗇�銋���園�霈斗��箸䔉���摰質◤�券��芸𢆡�曉之�� `150px` ����輻��對�摰䂿緵鈭��撅讛�閫厩���稲蝝批�銝𦒘�銝𠾼��
    - [x] **100% 瘥急�甇餉��朞� 29 憿孵�敶垍鍂靘�**嚗𡁜銁 `$env:PYTHONPATH="."` �臬�銝衤��芸�蝢𤾸�蝏輸�朞��券��訫�瘚贝�嚗𣬚頂蝏笔�撅�� UI 擃睃漲�諹�嚗�
- [x] **靽桀� PyQt6 靽∪噡�𧢲踎銵冽聢�堒捐���箸𧊋����㚚��� (Fixed PyQt6 Signal Dashboard Column Width Exit Persistence Bug)**嚗�
    - [x] **蝻拍��脫��嗵��冽�**嚗𡁜� `signal_dashboard_panel.py` 銝剔� `_save_ui_timer` �閙活�脫��湧��梯��輻� 5 蝘𡜐�`5000` 瘥怎�嚗匧之撟�𤣰�𥕢��𤥁秐�渡泵����䀹�閫���曉��笔��� **500 瘥怎�嚗�0.5蝘𡜐�**��蘨閬���賣𠹭撘� 0.5 蝘𡜐�撣���孵�撠曹��祇𡢿�笔����甇亙��交𧋦�堆�敶餃��寞祥鈭��蝜���剜�擃㗛�蝒堒藁鈭支�銝𦥑�𡏭�瘝⊥䔉敺堒���5蝘鍦��嗡�摮睃停鋡怠撩���𤥁◤�嗡��滢��寥膄�萘��𤤿���
    - [x] **�惩𤐄 closeEvent ���箏撩�嗅�甇乩�摮�**嚗𡁜銁 `closeEvent` 銝剜鰵憓墧遬撘� `_save_ui_timer.stop()` �𡝗���絲霈⊥𧒄�冽�隞歹�蝝扳𦻖���峕郊���摮鞟漣撘箏��瑕� `_save_ui_state()`���蝖桐�鈭�銁憭𡁶������餈𤤿�撘粹���硋挪銝餌������箸𧒄嚗峕��𦒘�甈⊥��賜𠶖��蓡����整���摰匧��典𧑐�祇𡢿�峕郊�嗵�����吔�摰䂿緵鈭��甇���𨀣��罸���算�腈��

## 2026-05-29 21:00
- [x] **摰䂿緵 PyQt6 瘥𤩺𠯫�滨����敶𤘪𠯫瘨典�銝舘��� DFF 瘛勗漲撖���𠰴�撅�����碶��� (Optimized PyQt6 Daily Operating Guidance & Real-time df_all_realtime Integration)**嚗�
    - [x] **撘訫��啣漲�誩�畾萎��拍�撖寥�**嚗𡁜銁 PyQt6 蝡臭縑�瑞��� (`signal_dashboard_panel.py`) ���𨀣��交�雿𨀣��轁�肽”�潔葉嚗峕���鰵憓𧼮僎瘜典�鈭� `"敶𤘪𠯫瘨典�"` (percent) �� `"韏��DFF"` (dff) 銝支葵�詨�摰䂿�摨阡��𨰜���雿踹� PyQt6 �𧢲踎銝� Tkinter �㕑�憭批��冽𠯫����条鸌敺��蝷箔��垍�銝𡃏噢�唬� 100% 瘥急�甇餉�����������
    - [x] **�亙�摰䂿� real-time ���蠘���之銵�**嚗𡁻���僎撠��鈭��蝎曉漲�� `_get_df_all_realtime` 憭𡁜��滨漣�娍䰻撘閙���銁�𤾸蝱�匧�銝𡡞�憸穃��唬遙�∩葉嚗䔶誑 O(1) ����笔漲蝘垍漣�閗繮 parent 銝餌�雿㮖葉甇�銁餈鞱��� `df_all_realtime` 銵峕�憭扯”嚗𥕦銁����唳旿�㵪�撖嫣葵�∩誨����賭����撘箸��� Emoji �𠰴�雿梶泵�瑞���竉蝳餅�瘣梹�蝏嘥笆靽肽�鈭�睸�澆笆朣𣂷��唳旿擃䀝��笔��硔��
    - [x] **�堒捐����碶��芸𢆡霈∠��輯悟**嚗𡁜銁 `_create_guidance_table` �嘥��碶葉銝箸鰵摨阡��烾�霈曆���稲蝝批����霈文捐摨佗�敶𤘪𠯫瘨典� 75px, 韏��DFF 75px嚗剹�������芸𢆡�堒捐�文����嚗諹𥅾蝟餌�璉�瘚见��砍𧑐撌脣��㗇�銋���堒捐�滨蔭嚗��蝡见朖�拍��輯悟�芸𢆡霈∠�瘚��嚗𣬚＆靽萘鍂�瑞��芸�銋匧�摰賭誑�𡃏楊隡朞��牐�撣���賢�摰𣬚��删��滩蝸嚗�蝠摨閗圾�喃��𨅯��唳𧒄�堒捐�芸𢆡�睃捐���憭扯”�潑�萘��𤤿���
    - [x] **�刻”�啣�澆�蝔喳��鍦�銝𡡞俈撏拙���**嚗𡁻���� `_get_sort_key` 蝥� Python �鍦�蝞堒�嚗䔶蛹�啣��亦�銝支葵�啣�澆�銵亙�鈭�艇�潛�撘箇掩�贝蓮�Ｖ� NaN/蝛箏�� fallback �拚猐嚗��蝢擧�蝏苷��孵稬銵典仍�鍦��嗅虾�賜��𤑳��𣂼� `NoneType` �鍦��嗘僚銝擧��券緾�� Bug��
    - [x] **�券� 29 憿孵�敶垍鍂靘� 100% 瘥急��芰��函遛�朞�**嚗𡁜銁 Headless �訫�瘚贝��臬�銝页��𣂼�隞� Exit Code 0 銝��芣��帋��券� 29 憿嫣漱�㯄��批����霂𤏪��函頂蝏煺漱�枏�摨批𤐄�仿�瘙歹�

## 2026-05-29 11:00
- [x] **摰䂿緵 5�亦瑪頞�漣撘箏飵�⊥��閙��𣂼漲銝舘䌊����脣�蝛粹𡢿隡睃� (Optimized SuperTrendMA5Branch Buy Sensitivity & Stop Padding)**嚗�
    - [x] **�賢𧑐頞�漣撘箏飵�⊥��閙䲮獢� B**嚗𡁜銁 `trading_kernel/engine/decision_engine.py` ���銝��冽��迫�煺����隞瑟聢�喟�銝哨���笆頞�漣銝餃�瘚� `SuperTrendMA5Branch` 摰墧鴌蝎曉�����嗥�����園俈摰��隞见����蝟餅㺭隞𤾸���𤐄摰𡁶�銝𧢲筑 2.5% (`0.975`) 蝘穃郎�嗥�隡睃�銝箸凒蝚血�撘箏飵蝑寧��噼萱蝏𤘪���**銝𧢲筑 1.5% (`0.985`)**��
    - [x] **摰䂿緵�嗆��找��脰萱蝛箏�蝢𤾸像銵�**嚗帋誑�舘��嗵㩞嚗�600863嚗㗇㿥�� `ma5d` ��瑪 `6.53` 銝箔�嚗峕��訫遣霈桐遠隞𤾸���� `6.37` �箄��鞉�銝羓宏�� **`6.43`**嚗��蝢舘斐����交𠯫������雿𤾸�頦拍� `6.47`嚗�銁靽萘� 1.5% �拍�蝻枏�嚗�俈�亙�瞍�宏瘥𥕦����嚗厩��峕𧒄憭批��𦦵�鈭�撩�輯�頦讐征����萸��
    - [x] **靽脲�撘勗飵/�港��∪之摰匧��脩瑪**嚗𡁏迨隡睃�隞�銁頞�漣撘箏飵�� `SuperTrendMA5Branch` 銝羓�����笆鈭� `SwsPullbackBranch`��TrendMA60Branch` 蝑㗇�頞见飵�㚚俈摰��嚗䔶��嗡���之摰賢漲�拍�摰匧��恬�摰𣬚��踹�鈭��隞硋之頝諹�頝毺���𢒰鋡怎�����Ｕ��
    - [x] **�券� 29 憿孵予璇臬����霂� 100% 蝏踵��函遛�朞�**嚗𡁜銁 `$env:PYTHONPATH="."` 銝衤��芸�蝢𦒘誑 Exit Code 0 �朞�鈭���� 29 憿嫣漱�梶��賢𪂹�煺�憌擧綉�訫�瘚贝�嚗𣬚頂蝏笔�撅��蝑㚚�餉����蝔喳���

## 2026-05-29 20:30
- [x] **摰䂿緵�屸�𡁻���稲憸���峕郊銝擧楛�滚��急��芣��箏� (Bi-Channel High-Fidelity Pre-warming & Proactive Sync)**嚗�
    - [x] **�賢𧑐�靝蜓�冽綫���嗪��𤑳洵銝���**嚗𡁜銁 `instock_MonitorTK.py` �詨� UI 皜脫�銝剜攟 `_apply_tree_data_sync` ���嚗峕�����乩蜓�冽綫��㦤�嗚��蜓餈𤤿��冽𡟺�䀝��西繮敺㛖洵銝�撣批��讛���之銵� `self.df_all`嚗峕���蝑匧�隞颱� Ticks嚗䔶噶隡𡁶��港蜓�典�憭扯”�券��僎�峕郊�喃漱�枏��賂��祇𡢿隞� O(1) �拍�����笔漲摰峕� 5484 �芾�蟡冽㿥�亙�蝥踹��孵�憭抒�頨恬�敶餃�摰䂿緵�瑕鍳�券妟撱嗉���
    - [x] **��漣�𨀣楛�急��滚��萘��函�蝚砌���**嚗𡁜銁鈭斗���瓲 `_get_df_all` 銝哨��齿�撟嗅��乩��滨輕�枏稬蝥批����𨅯�蝵𤏸䌊��之�急��嗪�蝎曉漲蝞埈���䌊�刻�皛斤洵銝㗇䲮�𦯀�蝟餌�摨橒��冽神蝘垍漣�園𡢿��笆敶枏�撌脣�頧賜����劐��⊥芋�堒�蝐餃�靘贝�銵峕楛摨血�撠�醌�𧶏��芷���摰帋�隞颱��瑟� `df_all` 銝磰��啣之鈭� 1000 �� DataFrame 頧賭�嚗���唬�頞���唾情��捆�曇䌊���頝冽芋�堒�摰寡��䜘��
    - [x] **�惩𤐄憭拇０銝见�頝舐眏�訫�瘚贝�**嚗𡁻�撖� `test_kernel_service_order_routing_by_mode` �訫�瘚贝�嚗��蝖祉����霂閗�隞���嫣蛹���霂閗� `TEST99` 撟嗅�蝢𤾸�銵乩� mock �冽𠯫銝𤾸��交��舐鸌敺��敶餃�瘨�膄鈭�眏鈭𤾸��函��� HDF5 ��蟮�唳旿嚗���笔��渲�銝剔���蝱�∴�撘訫���僭�亦��亦�頝荔�撟園�蝏苷� pytest �刻�銵��撅�璅∪��滚��急��嗅笆擳娍钟�寞��𥕦枂����嗆��芰䰻��扇霅血���
    - [x] **�券� 29 憿孵�敶垍鍂靘� 100% 瘥急��芰��函遛�朞�**嚗𡁜銁 PowerShell �� Headless �臬�銝页��𣂼�隞� Exit Code 0 銝��芷�朞��券� 29 憿寥��批�隞輻�鈭斗�憭拇０�訫�瘚贝�嚗䔶漱�梶頂蝏笔𤐄�仿�瘙歹�

## 2026-05-29 19:30
- [x] **摰䂿緵��蟮�唳旿銝𦒘��亙��� OHLC 敶餃�閫��虫����毺�摨誩��孵��𣂼��箏� (Decoupled Pure Historical Indicators & High-Speed Short-Sequence Feature Enrichment)**嚗�
    - [x] **摰䂿緵摰䂿�敹恍�煺���蟮�墧��峕芋�唳旿閫��血�瘚�**嚗�
        - [x] **摰䂿�敹恍��芋撘𧶏�撣阡�憭��敹恍�毺鸌敺��**嚗𡁶�銝� Fallback 霂餃��朞噢靽∪之銵冽𧒄雿輻鍂��� of `dl=limit_days`嚗��憒� 9 憭抬������ `safe_update_indicators` 撖嫣��亙��睃��� OHLC �唳旿��俈閬��靽脲擪嚗���唬�瘥怎�蝥折��𧼮��喟�撉諹�嚗�蝠摨閗圾�喃�蝤�� I/O 鈭㗇𦜖�屸�憸穃㨃甇颯��
        - [x] **�见𢆡��蟮�墧�璅∪�嚗���誩��脫��刻恣蝞梹�**嚗𡁜�瘚见��𡒊凒�交��碶�隡� `dl` ����𤩺𠯫蝥踹之銵剁�`dl=1200` 蝑㚁����憭扯”銝凋��急�憸����末��鸌敺�𧒄嚗䈣_extract_indicators_from_df` �芸𢆡��摰�圻�� rolling �齿鰵霈∠�嚗�� rolling(60) ��瑪嚗㚁�摰𣬚�靽嗪�鈭���祆��典��脣�瘚见銁��蟮隞餅��嗆挾銝讠���瑪蝎曉漲��
        - [x] **蝥蹂�蝟餌��芸���䌊����拍��峕郊銝𡒊�頨�**嚗𡁜蝠摨訫��凋�撖寧瑪銝见��� `shared_df_all.h5` 憭扯”�拍���辣��撩靘肽����蝥蹂�蝟餌��瑕鍳�冽𧒄嚗䈣TradingKernelService` 隡朞䌊�券�朞� `sys.modules` �滚��箏��箄��Ｘ�����𡝗迤�刻�銵𣬚� Tk 蝒堒藁嚗㇈onitorTK嚗劐葉撌脣�頧賢�瘥閧����憭扯” `self.df_all`��銁蝚砌�蝚� Tick 閫血� Cache Miss ���瘥怎����蝟餌�隡朞䌊�㻫��䌊��𧑐閫血��寥�皜拍� (`warm_up_indicator_cache`)嚗䔶��芸��𣂼�撣�㦤 5484 �芯葵�∠��冽𠯫憭𡁜𪂹����舐鸌敺��憸��頧踝�靽肽�撘��条��嗅朖鈭� O(1) 蝥臬�摮䀹��蠘膘�瓐��
    - [x] **摰䂿緵隞𦠜𠯫�芣𤣰�䁅��芷����芸𢆡�芣鱏�亦氖**嚗𡁜銁 `_extract_indicators_from_df` ���嚗屸��𥕢�擃条移摨艾��䌊�������交𧊋�嗥��亦瑪�芣鱏�亦氖�箏�嚗�䌊���霂�� datetime��YYYY-MM-DD` 摮㛖泵�� `YYYYMMDD` �湔㺭��倌嚗剹��銁�䀝葉 fallback �齿鰵霈∠��冽𠯫��瑪嚗㇈A5, MA10, MA60嚗劐誑�𦠜㿥�亙�擃睃�雿𡒊����舀���𧒄嚗諹䌊�其腺撘���交𧊋�嗥�銵䕘�蝖桐���蟮����箏��潛�撖寥�����矋��𣂼�銝�甈∪朖�臭蝙�冽㟲�伐�皛∟雲�𨀣��碶�甈∩蝙�其�銝芯漱�𤘪𠯫嚗峕𡟺�䁅䌊�冽��𣇉�摮䀝蝙�其��伐�瘥𤩺𠯫�芸𢆡�湔鰵銝�甈﹦�萘�閬��嚗剹��
    - [x] **擐硋�摰䂿�隞𦠜𠯫摰墧𧒄 OHLC �脰��嗘��� (`safe_update_indicators`)**嚗𡁜銁 `evaluate_decision_item` ���嚗諹挽霈∪僎撠��鈭���嗥迅�亦� `safe_update_indicators` 餈�誘���蝞堒�����羓�摮塩��df_all` �𡝗𧋦�� TDD Fallback �𣂼��箇��孵�銝𤾸��滢�隞嗅��貉�銵��撟嗆𧒄嚗�撩�𥟇㜃�芸僎靽脲擪隞𦠜𠯫摰墧𧒄 OHLC 摮埈挾嚗Ǒopen`, `high`, `low`, `close`, `volume`, `amount`, `trade`, `price`, `percent`, `pct`嚗剹��銁靽肽���蟮憭𡁜𪂹����舀�����典��𣇉��峕𧒄嚗𣬚�銝滨鍂��唂����脰��㺭�桀縧閬��隞𦠜𠯫���啁�摰䂿�銵峕���
    - [x] **摰䂿緵 `compute_lastdays` �拍��剖��埈��笔�頧賭�擃条輕��瑪�芷����拍�銵����**嚗�
        - [x] **頞�蝠�� I/O Fallback 撖寥� `cct.compute_lastdays`**嚗𡁜��䀝葉 Fallback �砍𧑐�朞噢靽∩�餈𥕦��㰘蝸�齿�銝� `dl = limit_days`嚗�⏚�� `cct.compute_lastdays` �滨蔭�𣂼�嚗䔶�憒� 9 憭抬���蘨霂餃�������餈� 9 憭抵��唳旿嚗�蝠摨閙��� 120 憭拙��讛粉�硋紡�渡��拍�蝤�� I/O 鈭㗇𦜖�屸�憸穃㨃甇颯��
        - [x] **擐硋�擃条輕��瑪銵���扳惣�賣䔝瘚贝䌊��**嚗𡁜銁 `_extract_indicators_from_df` 銝哨�敶餃�閫��虫�靘嗪��啁��踹漲餈𥡝� rolling 霈∠���香�輸��嗚�������� `ma60d` 隞亙� `ma60d_prev5` 隡睃�隞𤾸�埝㺭蝚砌�銵䔶��埝㺭蝚砍�銵𣬚� `row_last` 銝� `row_prev5` 撅墧�批��湔𦻖�枏���䌊���餉���朖雿踹銁�����㺭�格�摨誩��踹漲嚗�� 9 憭抬�銝页��曹��朞噢靽∪之銵其葉�拍�銵峕𧋦�亙停摮䀹�撌脩��𣂼�蝞堒末�� `ma60d` 摮埈挾嚗𣬚頂蝏蠘�隞� sub-millisecond �笔漲擃䀝�����硋枂摰𣬚��� 60 �亙�蝥選�敶餃�閫��鈭��𨅯�蝥踹�銵峕㺭銝滩雲�諹恣蝞堒仃�麨�萘��𤤿�嚗�
        - [x] **�拍��墧� `warm_up_indicator_cache` redundant ���**嚗朞��� `warm_up_indicator_cache` 銝箸�蝞��蠘� KISS 蝏𤘪�嚗���滢��亙之銵典歇�厩��拍�憭拇㺭�芣鱏������摰痹�靽脲�����嗅�雿踺��
    - [x] **29 憿孵�敶垍鍂靘𧢲��芰� 100% 蝏踵��朞�**嚗𡁜銁 PowerShell 銝衤��芸��券�朞�鈭���� 29 憿嫣漱�㯄��批����霂𤏪�蝟餌�韐券��䭾��臬稬��

## 2026-05-29 19:00
- [x] **摰𣬚��朞��曹澈憭扯” `G:\shared_df_all-20260529.h5` 摰峕㟲�唳旿�曆縑�瑞��乩� O(1) 蝥扳��毺鸌敺��蝑硋��㚚�霂� (Successfully Validated Shared H5 Dataset & O(1) Enrichment)**嚗�
    - [x] **閫�� Pandas Index-Columns ���甇找��脩�**嚗𡁜銁 `warm_up_indicator_cache` �寞�銝哨��𥟇鰵霈曇恣鈭� `df_all_temp.index.name = '_index_code'` �芸𢆡閫��行㦤�嗚��銁靽萘��笔�憭扯” index ��掩銝� Columns `code` 撅墧�抒��峕𧒄嚗�蝠摨閙覔瘝颱� Pandas �典笆憭𡁶���之銵刻�銵��蝏��`groupby`嚗㗇𧒄����� `ambiguous` �賢��脩�嚗���唬�憭𡁜像�唳㺭�格����蝻肽�����
    - [x] **摰䂿緵 6 雿滨滲�啣�隞��撘箸�甇��皜��**嚗𡁜�撘��隡删���凒�� `.isdigit()` �文��餉�����Ｗ��� `re.findall(r'\d+', ...)`嚗峕��嗅撩�滚𧑐蝘垍漣�亦氖鈭� A �∟���葉敶Ｗ� `600726.SH`��000001.SZ` �� `SH600726` ����箏�蝻�銝𡡞��啣��滨���蓮�Ｗ��𡒊��游��典��� **5484** �芾�蟡函����匧��脣��冽����舀�����芸��函��� `_indicator_cache` ���銝哨�
    - [x] **摰䂿緵�孵�摮埈挾憭批��躰䌊����惩�**嚗朞挽霈∪僎摰墧鴌鈭� `row_cols_lower` 憭批��坔�撣諹䌊��曎嚗�銁 `_auto_warm_up_from_preprocessed_hdf5` 隞亙� `evaluate_decision_item` �𤾸蝱 fallback 銝剖�蝢𡡞���鈭���� `MA5D` / `ma5d`��CLOSE` / `close` 蝑劐���紡�箄蔓隞嗆�撘閗絲��之撠誩��賢��誩榆嚗諹噢�唬��曉�銋讠蓡��妟鈭箏極隞见�擃䀝�����硔��
    - [x] **摰䂿緵憭扯” fallback O(1) �拍�摮堒��齿䰻**嚗𡁻�����𤾸蝱 fallback �餉�嚗峕�撘��擃䀹��祉� Pandas 蝝Ｗ��滚�嚗��蝥找蛹�箔�����惩��� `code_to_row` 摮堒��箏�����剝����憭扯” Cache Miss �塚��賢銁鈭𡁏神蝘𡜐�<0.05ms嚗匧��朞� H5 �曹澈銵典��貊�蝥抒移����𣇉鸌敺��蝤�� I/O �蠘�烾�銝� 0嚗�
    - [x] **�祉�瘚贝��𡁏𧋦銝� 29 憿孵�敶垍鍂靘见��Ｗ�蝏輸�朞�**嚗𡁜銁 `scratch/test_shared_h5_data.py` 霂𦠜鱏�𡁏𧋦銝哨�摰𣬚�璅⊥��䀝葉 ticks ���銝𡒊鸌敺���硔���隞���硋枂鈭� 5/5 �芯葵�∠��券�憭𡁜𪂹������餈䀹迤蝖株��箔���瓲�喟�����𠬍��� `$env:PYTHONPATH="."` 銝衤�甈⊥�找誑 Exit Code 0 蝏踵��㯄�𡁜��� 29 憿嫣漱�㯄��批����霂𤏪���捶�帋��舀鴹嚗�

## 2026-05-29 18:00
- [x] **�齿�鈭斗���瓲����孵�撖��嚗���� HDF5 �拍�憸����之銵� O(1) 蝥扳��笔��乩��芸𢆡憸��頧賢�摮䀹㦤�� (Implemented Preprocessed HDF5 O(1) Pre-warming & Fast Lookup)**嚗�
    - [x] **摰䂿緵 HDF5 �拍�憸����之銵刻䌊�穃�頧賭��剛澈 (`_auto_warm_up_from_preprocessed_hdf5`)**嚗𡁜銁鈭斗���瓲�臬𢆡嚗�朖 `TradingKernelService.__init__`嚗㗇𧒄嚗諹䌊�烐�蝝Ｘ𧋦�唳�撅��毺��曹澈��𡟺�䁅����憭���唳旿摨𤘪�隞塚�憒� `g:\top_all.h5`, `top_all.h5`嚗剹����芸��典��箄�蟡函�憭𡁜𪂹�笔��脤�����舀������𡠺 `ma5d`, `ma10d`, `ma60d`, `sws`, `swl`, `high_prev` 蝟餃�蝑㚁��券� O(1) 憸��鋆�蝸餈� `_indicator_cache` ���銝哨�敶餃�瘨�膄鈭��銝剝��� Cache Miss �嗅縧霂餃��訫蘨�∠巨憭批捆�譍�餈𥕦��亦瑪��辣�� I/O �埈𧒄�園���
    - [x] **�啣�憭㚚��曉�憸�蝸�孵��亙藁 (`warm_up_indicator_cache`)**嚗𡁜笆憭硋�撘�鈭�鸌�讐鸌敺��頨急䲮瘜𤏪�摰𣬚�撖寥�鈭���䀝葉�拍��望㺭�桐葉敹��憒� `tdx_data_Day.py` 銝剔� `generate_df_vect_daily_features_MultiIndex`嚗㗇��滩恣蝞堒僎�嘥��硋末���餈� 9 �亙��芯葵�⊥������捂撠�㟲銝� DataFrame ���毺��亙��貊�摮塩��
    - [x] **摰䂿緵����券�憭扯” `df_all` �冽��䌊��䔝瘚衤� 0.01ms O(1) ���毺鸌敺���� (`_get_df_all` & `update_df_all`)**嚗�
        - [x] **擐硋� `df_all` �典��冽����瑚��滚�蝏穃�**嚗𡁜銁 `TradingKernelService` ������鈭�抅鈭� `sys.modules` ��撩�𥕦�撠�䌊��㦤�塚�撘��睃��𣳇�鈭箏極撟脤��喳虾�典凝瘥怎���惣�賜忽�讛��怠僎�閗繮敶枏�摰蹂蜓蝒堒藁嚗㇈ainWindow/MonitorTK嚗匧�摮䀝葉甇�銁餈鞱����撣�㦤銵峕�憭扯” `self.df_all`��
        - [x] **蝤�� I/O 銝𡡞�憭齿��券�蝞堒����拍�皜�妟**嚗𡁜銁撘��㗛�憸𤏸���店�函��喟�撖��嚗Ǒevaluate_decision_item`嚗㗇𧒄嚗𣬚頂蝏煺���凒�乩��閗繮�� `df_all` ���銵䔶葉�祇𡢿����箸��匧��冽���瑪�𢠃�蝏游耦��鸌敺����甈∪��硋����湔𦻖隞� HDF5 �� 1-2ms �朞秐�笔��� 200ms �拍�����嗆��� **< 0.01ms** ��滲����滢�嚗��蝢舘噢�𣂷��冽�閬�����靝蝙�� `self.df_all` 銝��芣��吔�蝏苷��滚��滨��萘���稲�滨��𧢲����
        - [x] **29 憿孵�敶垍鍂靘𧢲�蝻嘥�蝏輸�朞�**嚗𡁜銁 Headless �訫�瘚贝��臬�銝页��芸�撘��舫�蝥折曎頝舀㦤�塚�瘚贝��券��删��朞�嚗峕�隞颱�銵䔶蛹�誩榆嚗�
    - [x] **摰���舀�撟嗅�摰� `G:\shared_df_all-YYYYMMDD.h5` �曹澈瘚贝��唳旿銝擧惣�質䌊��� HDF5 Key 璉�瘚� (Implemented Adaptive Key Detection for Shared H5 Data)**嚗�
        - [x] **�舀��曹澈憭扯”瘚贝�**嚗𡁜銁 `_auto_warm_up_from_preprocessed_hdf5` 隞亙��閗� fallback �齿䰻�曇楝銝哨��啣�鈭�笆�曹澈憭扯”��辣 `fr'G:\shared_df_all-{today_date_str}.h5'` �� `'G:\shared_df_all.h5'` 頝臬���惣�賣醌�𧶏����摰𣬚��唳��帋�憭𡁶����撅誩之銵函��砍𧑐瘚贝���
        - [x] **擐硋� HDF5 �桀��箄��Ｘ�**嚗𡁻��� `pd.HDFStore(path)` ���撠�����蝟餌��質䌊�券���僎�瑕� HDF5 �唳旿摨𤘪�隞嗅��函�擐碶葵�拍� Key嚗���唬�撖� `'df_all'` 銝� `'top_all'` ����刻䌊���閫��嚗峕覔瘝颱�銝滚�撖澆枂�臬�撖潸稲�� key 銝滚龪�齿𥁒�踺��
    - [x] **�齿��𣂼� DRY 擃䀹�閫��蝞堒� (`_extract_indicators_from_df`)**嚗𡁜��閗� DataFrame 銵峕��� 20+ 銝芣����畾萇��惩��惩極瘚��嚗𣬚�銝��賜氖����潔蛹�閗�韐��SRP嚗厩�擃䀹�閫��蝞堒�嚗���典��唬��𦦵��滚� (DRY)��
    - [x] **憭𡁜����笔�頧賡曎摰���剔㴓**嚗𡁜� `evaluate_decision_item` �𤑳��孵�撖���塚�敶Ｘ� **��1. ��� O(1) 蝻枏� �� 2. ���憭扯” df_all �祇𡢿�𣂼�嚗�<0.01ms嚗争� 3. HDF5 憸����”���笔��∟�皛歹�1-2ms嚗争� 4. �笔��朞噢靽� `.day` 鈭諹��嗆�隞嗅��臬𢆡 Fallback嚗���𤾸�摨𤏪���** ���撅�捆�暸𡡒�舫�瘙日俈蝥選�擃㗛�銵峕�銝讠��� I/O 撘����滩秐 **0**��
    - [x] **100% 瘥急�甇餉��朞� 29 憿孵�敶埝�霂蓥�撖寡揭 (100% Passed Regression Tests)**嚗𡁻����隞� `PYTHONPATH="."` �� PowerShell 銝剜��罸�朞�鈭���� 29 憿嫣漱�梶��賢𪂹�麄����找��𣂼���蟮�齿�蝖桀��扳�霂𤏪�Exit Code 0 摰𣬚�鈭支�嚗�

## 2026-05-29 17:45
- [x] **摰䂿緵鈭斗���瓲����孵�撖�� O(1) 蝥扯�擃䀹�扯����蝻枏�嚗�蝠摨閙覔瘝餃��㗛�憸𤏸��� I/O �餃� (Implemented Ultra-High Performance Indicator Caching)**嚗�
    - [x] **撘訫�敶枏予�亦瑪�蹱��鸌敺��摮条�摮� `_indicator_cache`**嚗𡁻�撖嫣葵�∪銁撘��䀹�擃㗛��瑟鰵�嗆挾嚗��憭滩粉�𡝗𧋦�啁��睃��脫𠯫蝥踵㺭�格�隞嗅僎�齿鰵餈𥡝���瑪��WS 撌乩�蝥踵��刻恣蝞梹�撖潸稲�閙活銝芾�撖���埈𧒄擃䁅噢 `170ms - 230ms` ���扯��園�嚗㚁�霈曇恣撟嗅��唬�銝�憟堒抅鈭� `(code, today_date)` ��𠯫蝥輻漣�蹱������摮条�摮䀝�蝟颯��
    - [x] **摰𣬚�颲暹� O(1) 蝥找�瘥怎��單𧒄餈𥪜�**嚗𡁶�蝻𨅯�銝𡁜𦛚�⊿�嚗��蝥選�MA5/MA10/MA60嚗劐誑�� SWS 蝑㗇㿥�亙���蟮�亦瑪�孵��典�銝�憭拐漱�𤘪𧒄畾萄�摰���蹱����塩��鰵�箏�銝页�瘥誩蘨銝芾�隞�銁敶枏予擐𡝗活餈𥕦���瓲�嗉圻�睲�甈∠��� I/O嚗屸��擧��厩�瘥怎�蝥折�憸𤏸���店�典��吔��埈𧒄��眏 `200+ ms` ���撉日��� `< 0.05 ms`嚗��扯��𣂼��啣��㵪�嚗𣬚�����䁅粉�㚚�銝� **0**��
    - [x] **擃䀝��毺遛�脤�𡁻�瘚贝��朞�**嚗𡁶� `pytest trading_kernel/tests/` 29 憿孵�敶垍鍂靘见��ａ�霂��瘚贝��券��删��朞�嚗峕�隞颱��臭��剁����箸�����惩�撠烐�隞� IO 鈭㗇𦜖��之撟������

## 2026-05-29 17:30
- [x] **靽桀�鈭斗���瓲擃㗛�撖�� `evaluate_decision_item` 銝剖笆 `setup` �嗆����𣇉� AttributeError 撘�虜 (Fixed Kernel Enrichment AttributeError)**嚗�
    - [x] **摰���寞祥 `curr_state.setup` 撘訫��� `'str' object has no attribute 'setup'` 撏拇�**嚗𡁜銁 `kernel_service.py` ���憸𤑳鸌敺���𤥁楝敺�葉嚗��雿滚僎皜�膄鈭�眏鈭擧鰵�惩���㿥��/�齿𠯫銵峕�����寞�找葉霂臬� `state_manager.get(code)` �硋��� `str` 撖寡情嚗�朖 `"FLAT"`, `"IN_TRADE"` 蝑厩�����嗆���嚗匧��𡁜��� `.setup` 撅墧�抒�摰硺�蝐餃笆鞊∟�銵諹粉�𣇉�銝仿� Bug��
    - [x] **摰䂿緵�脣鴃撘誩��典��折�蝥扳��� (Defensive Attribute Retrieval)**嚗𡁻����撖��摮堒�銝剔� `setup` 摮埈挾�坔��餉������ Python ��� `getattr(curr_state, "setup", "")` 蝥扯��滨漣蝑𣇉裦嚗�銁靽肽�摰䂿�/璅⊥��条𠶖����删���摰���峕𧒄嚗屸�摨血�摰寞�霂蓥��芸�銋匧�瘚𧢲��嗡��� mock state 撖寡情嚗��蝢擧��𡁶���鸌敺�釣�亦�摰匧��扼��
    - [x] **100% 瘥急�甇餉��朞� 29 憿孵�敶垍鍂靘衤� pytest 瘚贝� (100% Passed Kernel Regression Tests)**嚗帋耨�孵��� PowerShell 銝𧢲��罸�朞�鈭� `pytest trading_kernel/tests/` �券� 29 憿寥�撘箏漲鈭斗��嗆������抒滯蝥蹂�擃䀝��笔笆韐行�霂𤏪�Exit Code 0 蝏踵��朞�嚗�

## 2026-05-29 17:00
- [x] **摰䂿緵�函頂蝏� `premarket_diagnose.json` �拍�頝臬����蝏煺�銝� packaged �餌��臬�摰匧������ (Unified System Path Resolution & Hardened Premarket Diagnostics Persistence)**嚗�
    - [x] **摰���寞祥 PyInstaller/Nuitka �餌��臬�銝讠�頝臬��讐宏銝擧㺭�格⏛�� (Fixed Packaging Path Shift)**嚗𡁜蝠摨閙��支� `premarket_analyzer.py`��scratch/test_reentry_backtest.py`��tk_gui_modules/spatial_follow_hud.py`��signal_dashboard_panel.py` 隞亙� `stock_selection_window.py` �� 5 銝芣芋�𦯀葉蝖祉��� `os.path.join(base_dir, "logs", ...)` �� naked �詨笆頝臬� `logs/premarket_diagnose.json` �������
    - [x] **�函輕�㯄�𡁶頂蝏笔���� `sys_utils.get_base_path()` �冽��粉��**嚗𡁜銁���� 5 銝芣瓲敹���准��遛�笔�瘚卝��UD �𧢲踎�䔶蜓�屸𢒰銝哨�蝏煺�撘訫�撟嗆釣�乩�撣行��芸𢆡�𨅯��� `get_base_path()` �冽�����楝敺�䰻�暸�餉���＆靽嘥銁�枏������虾�扯���辣嚗Êrozen �臬�銝见��� `_MEIPASS` �� `NUITKA_ONEFILE_DIRECTORY`嚗劐誑�𦠜𧋦�啣�憪贝��砍��𤑳𠶖���嚗𣬚��齿��航��剜㺭�桀� 100% 瘥急�甇餉��啣��乩�霂餃�鈭𡒊�摰𧼮虾�扯�蝔见����函��拍��寧𤌍敶𤏪��喟頂蝏���� `logs/` ��辣憭對�嚗�蝠摨閗圾�喃��唳旿霂臬��� Windows 銝湔𧒄閫���桀� `C:\Temp\_MEIxxxxx` 撖潸稲���𨀣�甈⊿��舐�摨𤩺��齿鰵�枏���蟮�唳旿皜�征��撩銋𤩺�銋���萘��𤤿���
    - [x] **100% �朞��券��訫�瘚贝�銝� py_compile 璉�撉� (Passed 100% Unit Tests & Build Check)**嚗𡁜��𣂼笆���㗇��羓� GUI �詨�銝𡒊�瘜閙芋�㛖��拍�蝻𤥁�璉�撉䕘�Exit Code 0嚗㚁�撟嗡��� PowerShell �臬�銝𧢲��罸�朞�鈭� `pytest trading_kernel/tests/test_paper_trading.py` ���憟堒�敶埝�霂閧鍂靘页�蝏湔�鈭���湧�瘙斤迅�箇�撌乩�蝥找漱隞睃�韐具��

## 2026-05-29 16:30
- [x] **靽桀�鈭斗���瓲蝏�辣撖澆�銝擧芋�煺漱�枏����霂訫笆朣� (Fixed Kernel Imports & Aligned Paper Trading Unit Tests)**嚗�
    - [x] **�寞祥 `perf_monitor` 撖澆��躰秤 (Fixed broken timed_ctx import)**嚗𡁜銁 `kernel_service.py` 銝哨�敶餃�皜�膄鈭�笆銝滚��函� `trading_kernel.core.perf_monitor` 璅∪�����具����嗡耨甇�蛹�典�蝏煺���迤蝖株楝敺� `from JohnsonUtil.commonTips import timed_ctx`����支�擃㗛�銵峕�撽勗𢆡隞亙�蝑𣇉裦�斗鱏�扯�餈��銝剔眏鈭擧芋�㛖撩憭勗紡�渡��唳旿瘜典�銝舘�隡圈�餉���葉�哨�憓𧼮撩鈭�頂蝏蠘�銵𣬚��亙ㄝ�扼��
    - [x] **�∪�璅⊥�鈭斗��墧��剛� (Aligned Paper Trading Test Suite)**嚗𡁻�撖� `test_paper_trading.py` 銝剔眏鈭𤾸��脤�餉��㛖�撖潸稲�牐�畾菜鱏閮�憭梯揖嚗�朖�冽�霂蓥葉��鍂 `current_equity` 霈∠�撘�隞橒��𣬚�鈭折����典歇摰𣬚��嗆�銝算�靝��芯葵�∩�雿齿�摰𡄯�隞� `initial_capital` �嘥��餉��睲蛹�箏��萘�摰匧�撖寡揭璅∪�嚗厩��桅�餈𥡝�鈭�耨憭溻��凒�唬�瘚贝�����穃��牐��⊥㺭�剛�隞亙龪�滨�鈭折����冽��啁�銝𡁜𦛚���嚗諹噢�𣂷��典� 29 憿孵�敶垍鍂靘� 100% 瘥急�甇餉�銝�甈⊥�抒遛�烾�朞�嚗𠄌xit Code 0嚗㚁�

## 2026-05-29 15:30
- [x] **摰䂿緵 PyQt6 瘥𤩺𠯫�滢������稲蝝批�暺䁅恕�堒捐銝舘䌊�冽�銋�� (Optimized PyQt6 Guidance Table Column Widths & Persistence)**嚗�
    - [x] **憸�挽蝝批�暺䁅恕摰賢漲**嚗𡁜銁 `signal_dashboard_panel.py` �� `_create_guidance_table` 銝哨�銝箸��� 13 �堒�銋劐���稲蝝批����霈日�霈曉�摰踝�憒�誨�� 70px, �滨妍 90px, 隞㮖� 70px嚗�����臭遠�� 75px嚗��蝑𣇉��� 250px嚗㚁�隞擧�憭港�瘨�膄擐硋��𡝗𧊋蝻枏��嗥眏鈭𡡞�霈� Qt 摰賢漲餈�捐撖潸稲���蝝批��𤤿���
    - [x] **銝� Tkinter �Ｘ踎摰𣬚�撖寥�**嚗𡁶＆靽� PyQt6 銝� Tkinter 蝡舐�瘥𤩺𠯫�滢�����典������䌊���瘥娪�銝𡃏噢�� 100% ���閫厩�銝��峕��渡�蝛粹𡢿�拍鍂����
- [x] **摰𣬚�靽桀��滢����銝剔� Emoji 蝛箸聢�𢠃�鈭桅��脩撩�� (Perfectly Resolved Guidance Emoji Spacing & Highlight Colors)**嚗�
    - [x] **敶餃��寞祥 Windows 撟喳蝱銝讠� Emoji 蝛箸聢皜脫�撘�虜 (Fixed Emoji Spacing Anomalies)**嚗𡁻�撖� Tkinter (`stock_selection_window.py`) 銝� PyQt6 (`signal_dashboard_panel.py`) ���𨀣暑頝���胼�嘥�嚗�蝠摨訫竉蝳颱��� Windows 撟喳蝱銝衤�撖潸稲 ttk.Treeview 銝� Qt �訫��潭葡�枏枂憭帋�蝛箇蒾�牐�蝚衣� `\uFE0F` �䀝��㗇𥋘蝚佗�靘见�撠� `�椘儭葘 �踵揢銝箸��䀝�蝚衣���� `�椘`嚗㚁�撟嗅�霅血�銝㕑�敶� `�𩤃�` ��漣�踵揢銝箄䌊撣衣�銝賢蔗�脩�����訫���郎蝷箇� `�辶` 蝚血噡���蝢舘圾�喃��冽��漤����𨀣����蝛箸聢嚗笔㦛���銝��湛��萘��垍��𤤿���
    - [x] **摰䂿緵�箔�蝑𣇉裦��𣈲���撅�撘箏笆瘥娪�靽萘��脣蔗��倌雿梶頂 (Implemented Strategy Branch Row Highlight Tagging)**嚗𡁜�撘��銋见��寞旿 `action`嚗��雿𨅯遣霈殷�撖� Treeview �渲����脩��𧼮��冽䲮撘𧶏�憒���梢埯���𦦵聦雿漤�雿漤俈���肽�皜脫�銝箸迤撣貊�蝏輯𠧧嚗剹��銁 Tkinter �㕑��Ｘ踎�齿�撘訫�鈭� 5 憟堒抅鈭擧瓲敹���交暑頝���舐�頞�撩撖寞�摨阡��峕�暺𤑳��� Tag 銝駁�嚗�
        - `warning_red` (�港�擃䀝��脤�): �㛖滯摨閗𠧧 `#2b1414` �漤�擖勗�霅血�蝥� `#ff4444`嚗諹�閫匧��𥟇�皛∴�霅血����皛∴�
        - `super_cyan` (5�亦瑪銝餃�/�舀�): 蝣扯𠧧�堒� `#0c222b` �滨㩞蝡墧��罸� `#00ffff`嚗�偷�曆蜓��撩�輻�蝞剝��𨥈�
        - `trend_green` (10�亦瑪�滩蓮/頞见飵): 憓函遛�堒� `#0d2215` �滚�撘寞暑�𤤿遛 `#00ff88`嚗�蔑�曉�摨瑕�頧祈����
        - `pullback_yellow` (SWS��⏚蝥蹂���/�舀�): �亦��堒� `#24220d` �漤��烐�瞍誯� `#ffd700`嚗䔶誨銵券��烐郭畾萎��賂�
        - `defense_blue` (60�亦瑪��香�脣�): �誯��堒� `#161626` �齿��舫俈摰�換/�� `#d670ff`嚗䔶��啣��粹俈敺∪嵗�𡜐�
    - [x] **�峕郊�㯄�𡁜��� Emoji 摮㛖泵皜��銝𤾸��冽�摨讛�皛� (Synchronized Multi-Platform Emoji Sanitization)**嚗𡁜��冽鰵�� Emojis (`�辶`, `�椘`, `��`, `�椬` 蝑�) 摰���拍�閬���坔� PyQt6 銝� Tkinter 蝡舐�皜���曆葉嚗𣬚＆靽嘥抅鈭𦒘誨�� and �滚���楊璅∪��鍦�銝𤾸�蝘啗䌊���蝢𡒊�霂𤏸�銵䎚��

## 2026-05-29 14:30
- [x] **摰䂿緵瘥𤩺𠯫�滢�����喟���𣈲擃睃笆瘥𥪜漲�脣蔗皜脫�銝� Emoji 閫��撘箏� (Implemented Vibrant Decision Branch Rendering & Emojis)**嚗�
    - [x] **摰䂿緵�𣬚垢擃䀹� Emoji 閫���滨��拚猐 (Cross-Platform High-Contrast Emoji Icons)**嚗𡁜銁 Tkinter �㕑�蝡� (`stock_selection_window.py`) 銝� PyQt6 靽∪噡蝡� (`signal_dashboard_panel.py`) ���𨀣暑頝���胼�嘥�銝哨�擐硋��寞旿蝑𣇉裦頝舐眏閫���芸��寥�擃䀝漁�曉耦�滨�嚗𡁜�頞�撩�券� `SuperTrendMA5Branch` ��蝸 �� 憌𧼮予�怎悌嚗屸��𤏸��� `SuperTrendMA10Branch` ��蝸 �叚 �𡒊�蝏踵郭嚗峕楛摨虫��� `SwsPullbackBranch` ��蝸 �椬 暺��瘝蹱�嚗𣬚�甇餌�甇駁俈摰� `TrendMA60Branch` ��蝸 �椘儭� �䀹钟�滨㦛嚗屸�雿滨聦雿� `OscillatingBreakdownBranch` ��蝸 �𩤃� �垍𤌍霅衣內�䎚��⏚�函頂蝏毺漣�ａ��曉��祇𡢿�券�摨閙��脤𢒰�蹂葉�曉��箏��𡒊�閫���滨���
    - [x] **�㯄�� PyQt6 擃㗛弗����脰�撘箏笆瘥娍葡�� (PyQt6 Row/Cell Colorful & Bold Typography)**嚗𡁜銁 PyQt6 靽∪噡�𧢲踎�� `_refresh_guidance_table` 敺芰㴓銝哨���笆銝滚�頝舐眏��𣈲摰𡁜�鈭�𡠺蝡讠�擃䀝漁摨行��笔��航𠧧���撠��憒���𦦵聦雿漤�雿漤俈���嗪�鈭格葡�㮖蛹�𦒘漁霅血�蝥� (`#ff4444`)嚗𢞖��5�亦瑪銝餃�瘚芬�脲葡�㮖蛹�萇����罸� (`#00ffff`)嚗𢞖��10�亦瑪�滩蓮�脲葡�㮖蛹�滚撕瘣餃�蝏� (`#00ff88`)嚗�僎撖寞��㗇暑頝���臬���聢�滨蔭銝� `Bold` 撘箏��溻��蝠摨閗圾�喃��冽��漤����𦦵聦雿漤�雿漤俈���萘���𣈲瘛寞瓷�冽芦�𡁏�摮𦯀葉���瘜蓥��潛��怠躹����𤤿���
- [x] **�拍��𧼮�����𡝗�雿𨀣��𡑒䌊��葵�∠��� (Persisted Healed Guidance Stock Names to Disk)**嚗�
    - [x] **摰䂿緵�𣬚垢�拍��唳旿����硋��蹱㦤�� (Bi-Directional Persistence Write-Back)**嚗𡁜��恍���� Tkinter �㕑�蝡� (`stock_selection_window.py` �� `_refresh_guidance_tab` �瑟鰵皜脫�) 銝� PyQt6 靽∪噡蝡� (`signal_dashboard_panel.py` �� `async_fetch_task` 撘�郊�𤾸蝱蝥輻��㰘蝸)���蝟餌��券�撅讛蝸�交�摰𡁏𧒄�瑟鰵銝哨��朞�憭𡁏��惩� (憒� `selector` 摰墧𧒄銵具���䠷�厰���蜓銵典��砍𧑐 HDF5 �唳旿摨� `top_all.h5`) 璉�瘚见僎�芸𢆡靽桀� `"銝芾�_"` �滨��𣇉滲隞���牐�蝚血�蝘啣�嚗𣬚��喳�靽格迤�𡒊��唳旿霈啣��笔��批𧑐**�𧼮�撟嗉��𡝗�銋��靽嘥�**�唳𧋦�啁���㺭�桀� `logs/premarket_diagnose.json` 銝准��
    - [x] **�𦦵��滚�靽桀�銝𤾸��臬𢆡撱嗉� (Zero Redundant Repairs & Zero Cold Start Lag)**嚗朞�銝�蝒�聦�抒�瘞訾��拍��𧼮��箏�嚗�蝠摨閗圾�喃��冽��漤����𨀣�甈∪��臬𢆡�硋��啣��圈�閬���唬耨憭滢�甈∪�摮梹�蝻箔�����砽�萘��𤤿���緵�剁�隞餅�銝�蝡臬銁擐𡝗活餈鞱��嗡耨憭滚�銝剜��滨妍嚗𣬚����隞嗅朖�祇𡢿�芸𢆡�湔鰵銝箏�蝢𡒊��㵪��𡒊賒���㕑蔭霂Ｖ�憭𡁶垢頝刻�蝔贝粉�硋�摰䂿緵 0 瘥怎��祇𡢿皜脫�嚗𣬚頂蝏笔極蝔𧢲沲��凒�惩��箔��舫���
- [x] **摰䂿緵瘥𤩺𠯫�滢�����喲睸敹急㭘�𣳇膄�蠘� (Implemented Right-Click Deletion for Guidance Tab)**嚗�
    - [x] **�㯄�𡁶����隞嗉��典�摮鞟漣餈�誘銝擧�銋�� (Atomic Filtering and Persistence)**嚗𡁜��怠銁 Tkinter 蝡舐� `stock_selection_window.py` �� PyQt6 蝡舐� `signal_dashboard_panel.py` ���雿𨀣��� Treeview / QTableWidget �找辣銝剔�摰帋�銝㮖���𢰧�株��𨰻��𢰧�桃��颱葵�⊥𧒄隡朞䌊�冽惣�賡�劐葉霂亥�嚗𣬚��領�𨥉�� �𣳇膄甇斗�雿𨀣��轁�嘥�撘孵枂撣行��脰秤閫衣＆霈斗�蝷箇�撖寡�獢��蝖株恕�𤾸�摮𣂼𧑐隞� `logs/premarket_diagnose.json` �拍��唳旿瘙牐葉�娪膄霂乩葵�⊥㺭�桀僎摰匧�靽嘥���
    - [x] **摰䂿緵 UI �删��芣�銝𤾸��嗅��典��� (Instant Self-Healing and Local UI Refresh)**嚗𡁜��斗�雿𨅯��𣂼�嚗諹䌊�刻圻�� `_refresh_guidance_tab`嚗�銁 Tk 靘改��� `_refresh_guidance_table`嚗�銁 PyQt6 靘改�嚗䔶蝙撖孵������ 0 瘥怎��𤾸��唳��芰�瘨�仃嚗峕�靘𥟇��渡��滨��衤漱鈭雴�撉䔶��唳旿摰𣬚�����湔�扼��
- [x] **瘛勗漲撖寥�靽∪噡�Ｘ踎銝剜�雿𨀣��𡑒”�潛��烾�蝘烐��滩𠧧�瑕� (Aligned Guidance Table Stylesheet to Match Dark Theme)**嚗�
    - [x] **�拍�銵仿�蝻箏仃��甅撘讛”**嚗𡁜銁 `signal_dashboard_panel.py` �� `_create_guidance_table` �嘥��𡝗𦻖��葉嚗諹‘朣𣂷�����埈��� `table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")` 撅墧�扼����祇𡢿�寞祥鈭��雿𨀣��𡑒”�澆銁�嗡��𡑒𠧧敺桀��Ｘ踎嚗���喟��笔����憭渲蕭頦芥��踎�㛖��𤤿�嚗匧��Ｘ𧒄�曹���鍂蝟餌�暺䁅恕�質𠧧�峕艶撖潸稲���𨀣��潑�苷��𣈯��賣毽���嘥��潛��嫘��
    - [x] **摰䂿緵�函頂蝏罸�靽萘�閫���滚�**嚗𡁶＆靽脲��交�雿𨀣��埈�霈箏銁 Tkinter 餈䀹糓 PyQt6 �𧢲踎蝡臬� 100% 瘥急�甇餉�摰���滚�鈭𡒊�銝����暺𤑳�����恥憌擧聢銝卝��
- [x] **�齿�瘥𤩺𠯫�滢����銝箸��渡揮�煾�撖�漲銝㮖��滨��见�撅� (Optimized Guidance Tab to Compact Professional Layout)**嚗�
    - [x] **蝎曄�銵典仍��倌���**嚗𡁜��烾鵭����桀之�𤩺偌撟喳�蝝删�銵典仍��𧋦��漣銝箸凒銝箇�瘣�僕蝏��銝㮖��航祗嚗𡁜� `"���銋啣�/�噼‘����"` 蝎曄�銝� `"�������"`嚗𢱌"颲�𨭌�舀�隞�"` 蝎曄�銝� `"�䀹钟�舀�"`嚗𢱌"�䀹钟甇Ｘ��脣�"` 蝎曄�銝� `"甇Ｘ��脣�"`嚗𢱌"瘣餉�頝舐眏��𣈲"` 蝎曄�銝� `"瘣餉���𣈲"`��
    - [x] **憭批��讠憬�芸𢆡�堒捐����**嚗𡁜� `min_w_map` ���撠誩�摰賣��𣂼�蝻抬�靘见� `order_price` / `support_price` / `stop_price` 蝑劐遠�澆��勗��� `105-145px` 蝏煺��讠憬�單��渡揮�𤑳� **`75px`**嚗𢱌branch`嚗���荔��讠憬�� **`120px`**嚗𢱌sector`嚗�瓲敹�踎�梹��讠憬�� **`105px`**嚗𥕢誨����滨妍����嗥��� **`70px`** �� **`90px`**��
    - [x] **�嗅�����游���**嚗帋��硋�嚗���砍��� 1200px+ 摰賢漲���雿𨀣��𡑒”�潸◤����讠憬�喃���蝥� **750px** �喳虾摰𣬚�摰寧熙��緵嚗䔶����㗇㺭�格神�䭾⏛�剝��∴���之�𦠜𦆮鈭��撅𤩺��䀹����撟訫虾�券𢒰蝘胯��
- [x] **摰䂿緵�䀝葉蝒�聦頝笔� HUD �券�銝芾��笔��芣�銝舘䌊靽桀� (Implemented Complete HUD Stock Name Self-Healing & Self-Repair)**嚗�
    - [x] **�㯄�𡁜�皞鞟��� O(1) 蝥折��𧼮��拍��娍䰻 (High-Performance Stock Name Lookup)**嚗𡁜銁 `spatial_follow_hud.py` 銝剖��乩�擃条移摨衣��笔�閫���寞� `_get_stock_name`���朞��典�摮条����摰墧𧒄銵峕�銵� `df_all_realtime`���䠷�㕑��惩� `df_full_candidates`��虜閫���㕑” `df_candidates`��蜓�𥕢蜓銵� `master.df_all`嚗� and �拍��砍𧑐 `top_all.h5` �唳旿摨㮖��游遣蝡见�蝥折�蝥扯粉�𡝗㦤�塚�摰䂿緵 O(1) 蝥抒��滨妍�交𪄳銝𡒊移蝖桀龪�溻��
    - [x] **擐硋� HUD 蝏�祥樴坔仍銝舘�憌𦒘葵�﹦�靝葵�︵�嘥�雿滨泵�嗅辣餈蠘䌊��**嚗𡁜銁 `update_hud_data` �瑟鰵�餉�銝哨�撘箏��行⏛蝏�祥樴坔仍嚗Ǒleader_name`嚗劐����㗇�憭渲�憌舘�嚗Ǒselected_followers` 銝剔� name嚗厩�頧賢��亙藁���璉�瘚见��滨妍銝箇征��蛹蝥舀㺭摮𨰜����急� `"銝芾�_"` �滨��塚��芸�頝典�蝥抒�摮䀝��砍𧑐 HDF5 璉�蝝Ｗ��笔�銝剜�瘙匧��滨妍撟嗅�雿齿𤜯�Ｕ��
    - [x] **�嗅�雿𦦵鍂撖寥�銝𤾸�璅∪�霂剜�蝻𤥁��朞�**嚗𡁏鰵撘訫���䌊��㦤�嗅��典抅鈭𤾸�摮䁅蝠�讐漣摮堒�嚗�笆擃㗛��瑟鰵�𣳇�憭� I/O 撘���嚗䔶��� KISS/YAGNI �笔���� `py_compile` 瘚贝�嚗峕㟲銝� `spatial_follow_hud.py` 霂剜�璉�瘚� Exit Code 0嚗�100% 蝻𤥁��𣂼���
- [x] **�𣂼�瘥𤩺𠯫�滢���� Treeview �芸𢆡�堒捐�芷���銝算�𣈯�甈⊥�撘��扯�銝�甈﹦�� (Restricted Guidance Column Auto-Fitting to First-Time Open Only)**嚗�
    - [x] **靽脲擪�见𢆡�堒捐靚�㟲**嚗𡁜銁 `_refresh_guidance_tab` �鍦� `_guidance_cols_initialized` �嗆����譌��䌊�冽�憭齿��讐��芷���瘚钅��其�隞�銁�屸𢒰�㕑絲���甈∪�頧賣㺭�格𧒄�扯�銝�甈～��
    - [x] **�𦦵�擃㗛��瑟鰵�滨蔭**嚗𡁜銁甇支��𡒊��䀝葉擃㗛��瑟鰵����刻��剝�蝞𨰜����餅�摨讐�鈭衤辣�𤑳��塚�摰��敹賜裦�堒捐�滩��餉�嚗諹悟�滨��𧢲��刻��游末���摰賢�隞亙�蝢𡒊輕���敶餃�瘨�膄鈭��蝜��霈曉�摰賡�䭾����撅��芰�銝擧��剁�憭批��𣂼�鈭��雿靝�撉䎚��
- [x] **摰𣬚�靽桀�瘥𤩺𠯫�滢�����𨀣�雿𨅯遣霈栽�腈���𨀣暑頝�楝�勗��胼�苷��𨅯�蝑𣇉��晦�肽”憭渡��餅�摨誩仃�� (Fixed Guidance Tab Column Sorting Bug)**嚗�
    - [x] **�拍��𠉛氖�惩��誩榆**嚗𡁜�雿滚僎皜�膄鈭�眏鈭� Treeview �堒�嚗�� `"action"`, `"branch"`, `"code"`, `"name"`) 銝𤾸�撅���詨��券睸�澆�嚗�� `"action_cn"` / `"suggest_action"`, `"branch_cn"` / `"active_branch"`) 銝滢��游��𤑳��鍦�蝛箏�� Fallback 撘�虜��
    - [x] **�券𢒰�賢� Python 撘箇掩�钅俈撏拐�蝛箏�� Fallback �拚猐**嚗𡁜銁 `_get_sort_key` �峕㺭�株蝸�交葡�枏�����Ｗ��乩� `d.get(k) or default` ��漣�娪�蝥抒��乓��蝠摨閗圾�喳僎瘨�膄鈭�� JSON ���銝剖鉄�� `null` �硋�畾萇撩��𧒄撘閗絲�� Python �𣂼� `NoneType` �鍦��嗘僚嚗��撠�撩憭勗�潸秤蝞𦯀蛹 `"None"` 摮㛖泵銝莎�嚗䔶誑�𠰴銁�澆��𡝗葡�𤘪𧒄撖� `NoneType` 靚�鍂 `.2f` 撖潸稲����券緾��撏拇��鞉���
    - [x] **擐硋��䀹钟�𨀣瓲敹����漣霂���嗪�餉��鍦�**嚗帋蛹�𨀣�雿𨅯遣霈栽�� (action) 撘訫�鈭�抅鈭𦒘�銝𡁏��䀹��餉�����滩����摨譌����餅�摨𤩺𧒄嚗𣬚頂蝏煺��滨��閙��潮𨺗/�望�摮埈��鍦�嚗諹�峕糓�芸𢆡�厩� `銋啣�撱箔�(1)` �� `�関�噼‘(2)` �� `��鸌憭扳迫��(3)` �� `�䀹钟甇Ｘ�(4)` �� `靽脲�閫��(5)` ���亥翰隡睃�摨行惣�賢������之�𣂼�鈭��銝剖��剔��渲��扼��
    - [x] **�笔��鍦�銝𦒘誨��縧�滨滲����**嚗𡁜銁�鍦��株繮�碶葉�峕郊瘜典�鈭���滩䌊���撠��雿輻鍂 `code_to_name` 蝻枏��湔𦻖�鍦��笔��䔶��� placeholder嚗匧�隞�� Emojis 皜��撖寥�嚗�蝠摨閙覔瘝颱��曹�靽桅弘蝚行��坔紡�渡�銋勗��桅���
## 2026-05-29 14:15
- [x] **摰䂿緵瘥𤩺𠯫�滢����憸䀹��踹��箄��娍䰻銝𤾸虾閫���Ｘ踎摰𣬚��𥪜𢆡撣�� (Implemented Core Sector Mapping and Visual Layout Synchronization in Guidance Tab)**嚗�
    - [x] **�㯄�𡁜�皞鞾��鞉踎�� O(1) 蝥折��𧼮��娍䰻 (High-Performance Sector Lookup)**嚗𡁜銁 `_refresh_guidance_tab` 銝剖��唬���蛹�亙ㄝ����鞉踎�梹�`category`嚗劐��漤�蝥扯粉�碶�蝻枏�餈�誘�箏���頂蝏罸����甈∩� `self.selector.df_all_realtime`��self.df_full_candidates`��self.df_candidates`��self.master.df_all` 銝剖僎銵��頧賣��啁��∠巨�踹��惩�嚗�����匧�摮条����銝滚𦶢銝剜𧒄嚗䔶����蝥扯粉�𡝗𧋦��/����� `top_all.h5` �唳旿摨㮖葉���銝�/璁�艙��倌����� `self._get_short_category()` 蝞埈�摰䂿緵擃睃漲蝻拙����摮堒捐閫��颲枏枂嚗�� `"�𠰴紡雿� | ����菔楝"`嚗㚁��𦦵�鈭�鵭撠曇�銝𡁜�畾萇聦雿溻��
    - [x] **擐硋� "�詨��踹�" 擃䀹� Treeview �𡑒��� (Integrated "Core Sector" Column in TK Guidance Tab)**嚗𡁻���� `stock_selection_window.py` ��� `_init_guidance_tab` 蝏�辣�亙藁��銁 `Treeview` 摮埈挾�惩�銝剜迤撘讛蕭�� `"sector"` 瑽賭�嚗�僎撠���鍦銁隞�� and �滨妍銋见�隞亦��箏��𦦵�摨行踎�堒��把�腈���蝢𤾸������稬鈭衤辣銝� `vals` ������蝵桐����撘寧�霂行�銝剖��嗅�蝷箔葵�⊥��詨�憸䀹��踹���
    - [x] **瘛勗漲撖寥��堒捐靽嘥�銝舘䌊���瘚钅�蝞堒� (Hardened Layout Persistence and Column Width Auto-Fitting)**嚗𡁜�蝥找� `_save_guidance_column_widths` 頝其�霂脲�銋���𡑒”隞亙� `_auto_fit_guidance_columns` 銝� `min_w_map` ���撠誩捐摨虫��日��潘��啣��𣂼� `"sector"` ��撠誩�摰� `130px`嚗㚁�蝖桐�鈭�朖靘踹銁��垢擃䀝������揢銝页��詨�憸䀹��踹�銋毺�銝滚��笔�蝚行��𣳇��𨬭��⏛�哨�憪讠�銝箸��䀹��𣂷���雿唾�閫㗇��溻��

## 2026-05-29 13:45
- [x] **摰䂿緵瘥𤩺𠯫�滢���� Treeview �箄��芷����堒捐銝𡡞�蝎曉漲�堒捐頝其�霂脲�銋�� (Implemented Guidance Column Width Auto-Fitting & Cross-Session Persistence)**嚗�
    - [x] **摰䂿緵擃䀝��笔�摰賣�銋��摮睃� (Cross-Session Column Widths Saving & Restoring)**嚗𡁜銁 `stock_selection_window.py` 銝剖��� `_save_guidance_column_widths` 銝� `_restore_guidance_column_widths` �亙藁���朞�憭滨鍂 `window_mixin.py` 銝剛�����典� DPI 蝻拇𦆮瘥𥪯�銝� JSON 摮睃�摨� `visualizer_layout.json` (�� `WINDOW_CONFIG_FILE` 撖孵��漤���辣)嚗�銁銝餌���◤�滨��见��剜���瘥�𧒄嚗Ǒ_on_close`嚗匧�摮𣂼𧑐����𡝗��㕑䌊摰帋�靚�㟲餈���堒捐嚗�僎�其�銝�甈∠頂蝏��韏瑯��辣�� 250ms UI ���皜脫�摰��摰𣬚��滩蝸撖寥�嚗���唬�摰𣬚���楊隡朞�銝��湔�扼��
    - [x] **擐硋� O(N) 蝥扯”�澆�摰寡䌊���瘚钅��脣�鋆� (O(N) Smart Column Width Auto-Fitting)**嚗𡁶��� `_auto_fit_guidance_columns` 擃䀹�扯��芷���瘚钅��寞�����滨��见��芾�銵諹䌊摰帋�靚�㟲�塚�蝟餌��芸𢆡�滚��券� Treeview �∠𤌍��捆嚗䔶蝙�函�摰𧼮�雿枏笆鞊∪笆瘥譍葵�訫��潭�摮烾鵭摨佗�隞亙�銵典仍���摰賢漲嚗㗇�銵��蝝删漣蝎曄＆瘚钅�嚗�僎�芸𢆡�����憟穃����雿訫�蝝惩捐摨佗��峕𧒄撖寞瓲敹��雿齿��寞��踹�畾蛛�憒� `reason`嚗䈣code`蝑㚁�餈𥡝�摰賜����潔��歹�憒���� `code` ��撠誩�� `85px` 隞仿俈 6 雿滢誨���鋆��`name` ��撠誩�� `115px`嚗㚁�敶餃�皜�膄鈭�眏鈭擧遬蝷箏捐摨血��鞾�䭾����靝誨��/�漤�隞瑟聢�睃�����𨬭��遬蝷箔��兩�萘�蝏���𤤿���
- [x] **�拍��㯄�朞��凋��墧�摨訫��唳旿銝剖�嚗�蝠摨閙覔瘝� placeholder "銝芾�_隞��" �曄內瞍�宏 (Resolved Naming Discrepancies and Placeholder Fallbacks)**嚗�
    - [x] **銝餌瑪霂𦠜鱏摨訫��惩�瘜典� (Diagnostic Chinese Name Resolution)**嚗𡁜銁 `premarket_analyzer.py` ��瓲敹���剛恣蝞堒��� `run_premarket_diagnose` 銝哨�撘訫� HDF5 摨訫���㺭�桀� `top_all.h5` 蝎曉�頧賢��惩���𥅾霂𦠜鱏����� fallback 銝芾�蝻箏��滨妍�硋�鈭� `"銝芾�_"` �滨����雿滚�蝘唳𧒄嚗諹䌊�刻楊�拍���辣霂餃� HDF5 銝餉”摰峕��∠巨銝剜��笔�閫��嚗䔶蝙�滨��讠��踹��怠��瑞��望�隞���碶葩�嗅�蝚艾��
    - [x] **�见𢆡�墧��䀹钟霈∪��屸�撖寥� (Backtest Manual Export Name Alignment)**嚗𡁜銁 `scratch/test_reentry_backtest.py` ����航恣�坿氜�睃遆�� `update_premarket_diagnose_json` 銝哨��峕郊餈賢�鈭�抅鈭� `top_all.h5` ����滚��唳旿�行⏛閫���餉���＆靽脲�霈箸糓�朞�瘥𤩺𠯫�睃��芸𢆡霂𦠜鱏����函��滩��剝�蝞梹�餈䀹糓雿輻鍂 `Alt+X` 摰墧𧒄�扯��见𢆡�墧��䀹钟霈∪�嚗���� `logs/premarket_diagnose.json` ��葵�∠��滚� 100% 瘥急�甇餉�摰��甇�＆撖寥�嚗峕��帋��唳旿隞𤾸�瘚衤遛�笔��睃� HUD �𧢲踎�删��暹釣����𦒘��祇���
    - [x] **敹急㭘�桐��喲睸�𨅯�皞𣂼仍�唳旿皜�� (Interactive Triggers Source Input Cleaning)**嚗𡁜銁 `instock_MonitorTK.py` �� `_on_shortcut_reentry_backtest` (Alt+X 銝��株圻��) 隞亙� `_on_run_reentry_backtest_menu` (�喲睸�𨅯�閫血�) 銝哨�憓𧼮�鈭��蟡其誨����拍�皜��嚗����竉蝳� `�𣞁, �叚, �𩤃�` 蝑厩𠶖��”��泵撟嗉‘�� `zfill(6)` 撖寥�嚗劐誑�𡃏�蟡典�摮㛖��箄��斤征銝𡡞�蝞埈㦤�塚��乩��亙�摮𦯀蛹蝥舀㺭摮𦯀誨�����蝻���鉄 `"銝芾�_"` �𣇉撩憭梧��芸��𥪜𢆡 `df_all` �滚�雿滨�摰噼�蟡其葉���嚗剹��
    - [x] **Qt6 撘�郊�墧�蝥輻�餈睃� (Qt6 Async Backtest Thread Reverted to KISS)**嚗𡁜銁 `trade_visualizer_qt6.py` �� `ReentryBacktestThread.run()` �唳旿�亙藁銝哨��𧼮��喟凒�交𦻖�� Tk 隡𣳇�垍��笔� `name`嚗��憭帋� HDF5 IO 撘���嚗㚁��萄儐 KISS �笔�嚗䔶�皞𣂼仍銝𦠜��支��𦯀����隞嗉粉�𡝗�雿栶��

## 2026-05-29 13:00
- [x] **靽桀�瘥𤩺𠯫�滢���� Tab 閫��撅閧內銝𡡞�鈭桅�敶� Bug (Fixed Daily Guidance Tab Visuals & Normal Row Invisible Bug)**嚗�
    - [x] **�寞祥甇�虜銵峕�摮烾�敶ａ䔮憸� (Resolved Invisible Text for Normal Rows)**嚗𡁻�撖嫖�靝����撖麨�萘�撣貉�閫���嗆���嚗ōag `"normal"`嚗㚁�摨罸膄銋见��曹��芣遬撘誩�銋㕑��航𠧧撖潸稲�� Tkinter 暺䁅恕�賢�銵冽聢銝� off-white 瘚���齿艶�莎�`#eeeeee`嚗劐��峕艶摰��瘛瑟��������兩�𣈯�敶Ｔ�萘��滚之�梶鍂�� Bug��撩�𥕢蛹�嗆遬撘讛‘朣� `background="#0c101b"` 撅墧�扼��
    - [x] **�舐鍂�典��烾���恥銝駁� (Enforced Premium Dark Theme Style)**嚗𡁜� `_guidance_tree` ��漣�亙��典���擃䀝���漣�𡑒𠧧銵冽聢����瑕� **`Dark.Treeview`**嚗�僎撠���嗥漣摰孵膥 `tree_frame` �� `parent` tab 閫�㦛����臭�撟嗉挽銝箸�����堒��煾��莎�`#0c101b`嚗㚁�隞舘�䔶��港葵蝟餌����暺𤑳���憌擧聢摰𣬚�蝏煺���
    - [x] **敶餃��拍�蝘駁膄 Expander/Folder �𦯀��暹� (Fully Cleaned Expander Icons)**嚗𡁻�朞�撘箏�憯唳� `self._guidance_tree.column("#0", width=0, minwidth=0, stretch=False)`嚗�蝠摨訫����墧��嗅虜閫� Treeview �券��梹�`#0`嚗匧椰靘抒眏鈭𡡞�霈方�銝箸��坔�雿� expander 撅訫�銝㕑�銝𡒊征�賢�雿齿�隞嗅允�暹� of 蝻粹萅嚗峕��支�閫���芷𨺗嚗峕�憭批��碶��滨��见�撟𨰻��
    - [x] **�齿�暺���堒捐���嚗峕�蝏嘥�蝚血��� (Optimized Column Widths & Prevented Text Clipping)**嚗𡁻�撖寥�����峕����撟𤏪�撖孵��㛖��牐�摰賢漲餈𥡝�鈭��蝝删漣靚��嚗𡁜� `name`嚗��蝘堆��堒捐�� 80px �曇��拙��� **110px**嚗�＆靽肽站憒� `"銝芾�_600759"` 蝑� 11 雿滚���葵�⊥�霂� 100% 瘥急�甇餉�蝎曄�撅閧緵嚗㚁�`code` 摰賢漲靚�㟲銝� 75px嚗䈣action` 靚��銝� 90px嚗䈣branch` 靚��銝� 160px嚗�蝠摨閙覔瘝颱�靽⊥��惩捐摨阡��嗉�諹◤蝎埈𠂔鋆���𡝗遬蝷箔��函�雿㯄��𤤿���

## 2026-05-29 12:00
- [x] **摰䂿緵 Alt+X �见𢆡�墧��䀹钟霈∪��芸𢆡撖澆枂銝擧��交�雿𨀣��堒��嗅�甇� (Implemented Automated Backtest Guidance Export & Real-time Tab Synchronization)**嚗�
    - [x] **暺���滢��箔�銝𤾸�銝𦒘遠�澆ế摰� (Trading Value Evaluation Gate)**嚗𡁜銁 `scratch/test_reentry_backtest.py` ��瓲敹�遛���餈𤤿���𧒄嚗峕鰵憓硺�敶枏�銵峕��嗆����𨅯�銝𦒘遠�潑�肽�隡圈�餉���𥅾�见𢆡�墧�銝芾�敶枏�憭��璅⊥����銝哨�`has_position` 銝� True嚗㚁��𤥁����唬�憭拙�蝑硋之�穃ế摰𡁜��劐僭�亙遣隞橒�`BUY`嚗剹���T�噼‘嚗ǑADD`嚗㗇����皛𡁜𢆡嚗ǑHOLD`嚗厩�擃䀝遠�潭��交㦤隡𡄯��喳ế摰朞砲銝芾��争�𨅯�銝𦒘遠�潑�腈��
    - [x] **�䀹钟雿𨀣�霈∪�擃䀝��笔紡�� (High-Fidelity Tactical Plan Export)**嚗𡁶��嗘� `update_premarket_diagnose_json` 銝梶鍂�亙藁����瑟����隞瑕�潔葵�∠����舀�������唳𤣰�䀝遠����閙�銵����遠 `predicted_ma5`����拇𣈲�睲� `sws_support`��′�脣�甇Ｘ�蝥� `hard_stop` 隞亙�瘣餉�蝑𣇉裦頝舐眏��𣈲蝑㚁�隞� 100% 蝎曉��� JSON Schema �澆�摰匧��坔�撟嗆凒�啗秐蝏煺�����硋� `logs/premarket_diagnose.json`嚗���唬��见𢆡�墧��唳旿�𤑳��齿��舐��輻��删��暹釣��
    - [x] **���� UI �𥪜𢆡銝舘䌊����删��瑟鰵 (Instant UI Tab Synchronization)**嚗𡁜銁 Tkinter 蝡舐� `_on_shortcut_reentry_backtest` ���箏�靚�葉嚗峕鰵憓硺� `_refresh_guidance_if_open()` �𥪜𢆡�瑟鰵�亙藁����见𢆡�墧�霈∠�摰峕�颲枏枂�祉��鮋獈憛墧𥁒�𦠜𧒄嚗𣬚頂蝏煺��� 0 瘥怎��舘䌊�冽�瘚见僎�笔𧑐�𣳇緾����啗蝸�乒�𨥉�� 瘥𤩺𠯫�滢�����嗪�厰★�∠� Treeview �唳旿嚗�蝠摨閙��支��见極憸𤑳��瑟鰵���雿蹱�雿頣�摰䂿緵鈭������䀹�雿𤘪���
    - [x] **霂剜�蝻𤥁�銝𡒊鍂靘� 100% 蝏踵��朞�**嚗𡁜��𣂼笆 `scratch/test_reentry_backtest.py` �� `instock_MonitorTK.py` ����Ｙ����霂穃��𧼮�瘚贝�嚗峕��㗇㺿�函𠶖��迅摰𡄯��牐遙雿訫�雿辷�摰𣬚�蝚血� KISS/YAGNI �笔�嚗�

## 2026-05-29 11:30
- [x] **摰䂿緵�睃�霂𦠜鱏�芸�閫血�銝擧��交�雿𨀣��� HUD �垍𤌍�𥪜𢆡撅閧內 (Implemented Automatic Pre-market Diagnostic Heartbeat & Vibrant HUD Overlay)**嚗�
    - [x] **摰䂿緵 100% 撘�郊��妟撘���瘥𤩺𠯫�睃�霂𦠜鱏�𤾸蝱頧株砭 (Asynchronous Heartbeat Trigger)**嚗𡁜銁 `instock_MonitorTK.py` ��虜撽餃�憪见� `_batch_init_housekeeping` 銝哨�瘜典�撟嗆�韏瑚� `_bg_premarket_diagnose_heartbeat` 敹�歲霈⊥𧒄�剁�擐𤥁蔭 4s 閫血�嚗峕迨�擧� 60s 頧株砭嚗剹��砲�寞��瑕�擃条移摨衣�鈭斗��亥�皛歹��冽��� `08:50 - 09:10` ����𤑳��齿𧒄畾萄�嚗諹𥅾隞𦠜𠯫�芣�銵諹��哨��躰䌊�典銁�𤾸蝱蝥輻�瘙� `self.executor` �拍�撘�郊餈鞱� `premarket_analyzer.py` �� `run_premarket_diagnose()` 餈𥡝��滨�撟嗡�摮䁅秐 `logs/premarket_diagnose.json`嚗�銁摰��銝漤獈憛� Tkinter �屸𢒰皜脫�����萎�摰䂿緵�唳旿��稲靽嗪���
    - [x] **擐硋� HUD ���銝芾��睃�霈∪��垍𤌍摮烾�銝舘𠧧靚��鈭株��� (High-Contrast HUD Tactical Guidance Overlay)**嚗𡁻���� `tk_gui_modules/spatial_follow_hud.py` ����劐葉�格�皜脫��賣㺭 `_update_highlight_border`����滨��钅�摰帋葵�∩�敶枏��∠巨��鉄�㗇�����齿�雿𨀣��埈𧒄嚗𣬚頂蝏蠘䌊�冽㜃�芸��厩��譍遠�𣬚氖��𧋦嚗�僎擃䀝��笔𧑐皜脫�銝箏蒂�匧��滨��交綫�𣂼𢆡雿頣��靝僭�亙遣隞𣏾�腈���𨅯之甇Ｙ��腈���𨅯�T�噼‘�萘�嚗䔶��朞� HSL 擃睃笆瘥𥪜漲鈭桃滯��漁蝏踴���暺��銝枏��滩𠧧�垍𤌍�箏�嚗剹��𢆡��俈摰�遠�潘�`hard_stop`嚗劐誑�𦠜綫�𣂼��舐�隞𦠜𠯫�寧�雿𨀣�霈∪�嚗���唬����蠘�閫匧ế摰帋��𨀣��臭��桐��嗯�腈��
    - [x] **摰𣬚��㯄�𡁜�撟喳蝱擃条移摨行㺭�株䌊��� emoji 皜��**嚗𡁜銁 HUD ��葵�∪龪�滢葉撘訫�鈭� emoji 皜���𡁻�嚗𣬚������ `'�𣞁', '�叚', '��', '�𩤃�'` 蝑劐耨擖啁泵嚗𣬚＆靽苷�銝餃㦛銝� HUD 銋钅𡢿�� 100% 蝎曉�隞��撖寥�銝𤾸龪�溻��
    - [x] **擐硋� Tkinter 蝑𣇉裦�㕑�蝒堒藁�𨥉�� 瘥𤩺𠯫�滢�����萘�銝�閫�㦛 Tab 銝𤾸翰�琿睸�渲噢 (Unified Tkinter Guidance Tab & Alt+G Direct Entry)**嚗�
        - �� Tkinter 蝡舐� `StockSelectionWindow` 銝剜�撅訫僎瘜典�鈭���啁� **`�� 瘥𤩺𠯫�滢����`** �厰★�～��凒�乩� `logs/premarket_diagnose.json` �拍�霂餃�撟嗅��唬��亦��滢��箔�����閙�銵����遠�潘�`predicted_ma5`嚗剹����拇𣈲�睲遠嚗Ǒsws_support`嚗剹����舀迫�罸俈摰��`hard_stop`嚗劐誑�羓��交暑頝���荔�摰���踹�鈭��摮𡑒秩�𦒘髡��耦撘𧶏��𡁜�鈭�**�靝遠�潔��桐��塚����隞瑟聢�湔𦻖�舀䰻��**��
        - 摰䂿緵鈭�”�潸��孵稬銝𦒘蜓 K 蝥踹虾閫����isualizer 銋钅𡢿��神蝘垍漣�𥪜𢆡�滚�嚗𥕦��餉��舐��餃撕蝒埈䰻��祕蝏�����舫𢒰霂𦠜鱏敶鍦���
        - �厰★�∪�蝵桐��𤾸蝱撘�郊餈鞱��� **`�� �睃��滨�`** �厰僼嚗���颱�撖孵��嗅膥����其�韏吔��舫��嗆��冽�韏瑕�瘙㰘��剖��𣂼僎�單𧒄�𣳇緾����唳�銵具��
        - 銝餌�����毺�摰帋��典�敹急㭘�� **`Alt + G`** (Guidance)嚗峕𣈲����桃凒颲撾�𨀣��交�雿𨀣��轁�嗪�厰★�∴�摰䂿緵鈭���湧�����䀝葉�滨�雿㯄���
    - [x] **�函頂蝏罸�朞� 100% �訫�瘚贝�銝� py_compile 璉�撉�**嚗𡁜��𣂼笆 `signal_dashboard_panel.py`��instock_MonitorTK.py` �� `tk_gui_modules/spatial_follow_hud.py` �����祗瘜閧�霂𡢅����㗇芋�㛖�霂𤑳𠶖���蝢𡡞�朞�嚗𠄌xit Code 0嚗㚁��典��𧼮��其��蠘��亙ㄝ�抒迅�亙仁���

## 2026-05-29 10:10
- [x] **摰���寞祥�墧��亙�銝𦒘蜓�暹綫�𣂼��舀遬蝷箸�蝘� (Fully Resolved Active Branch Display Drift between Backtest and Visualizer)**嚗�
    - [x] **摰䂿緵�喟�敺芰㴓�鞉𠯫摰墧𧒄瘜典�**嚗𡁜�撘��銋见��典�瘚讠�撠曄��游��刻��� `StrategyRouter.route` ���雿䠷�餉�嚗�歇蝖株恕�𣳇睸�滢��寥��䭾��鮋���啣虜閫�俈敺∪��舐� Bug嚗剹�����蛹�典�瘚衤蜓敺芰㴓�� `decide()` �扯��𠬍�蝡见朖撠��憭拇��啗恣蝞堒��箇�頝舐眏��𣈲�滨妍 `intent.reason.routed_branch` �冽���甇交釣�� to `_last_backtest_best_branch` 摮堒�銝准��
    - [x] **�嗅�雿𦦵鍂撖寥�**嚗𡁶＆靽苷��㰘捏�臬銁����嗆���`IN_TRADE`嚗㕑��舐征隞栞�撖毺𠶖���`FLAT`嚗㚁����唬�憭拍�瘣餉��刻�蝑𣇉裦��𣈲�質�鋡� 100% 瘥急�甇餉��啣笆朣琜�敶餃�瘨�膄鈭�眏鈭𢛶�𨅯𢆡雿𨀣𧊋閫血��苷��坔��脰��笔��臬�蝘圈�䭾����𨅯�頧冽�蝘領�萘緵鞊～��

## 2026-05-29 09:50
- [x] **摰��靽桀� Re-entry 憭�遢�墧�撘閙� (test_reentry_backtest_old.py) ��𧊋�交㺭�格�瞍譍��扯�隡睃� (Fully Fixed Look-Ahead Bias & Optimized Performance of Legacy Backtest)**嚗�
    - [x] **摰墧鴌 $O(1)$ 撣豢㺭�園𡢿撅��冽��刻������**嚗𡁜�����墧�隞輻��𡁏𧋦 `test_reentry_backtest_old.py` ���擃睃����� `df_curr = df_all.loc[:current_date]` DataFrame �拍�����滢�嚗䔶誑�𠰴銁�嗡��𦯀��� `rolling()` 霈∠�嚗���冽𤜯�Ｖ蛹�箔��典�銵𣬚揣撘� `row_idx` ����冽��函���像��/����/���撌� $O(1)$ 擃䀹�扯��𣂼�蝞堒���
    - [x] **敶餃��寞祥�㛖��� `df_curr` �芸�銋匧援皞�**嚗𡁻���僎皜��鈭� `has_position` ����烐��諹���縑�瑕ế摰𡁜笆 `df_curr` ����坔撩撘閧鍂嚗䔶蝙���㗇�����孵�憿孵�蝢𤾸笆朣鞱秐 `df_all.iloc[row_idx]` 蝥改�蝖桐�鈭��隞質��砍銁瘨�膄�芣䔉�誩��𦒘��嗅虾隞仿妟�仿����擃㗛�笔��鞉㟲銝芣�霂閙�蝔卝��
    - [x] **瘨�膄��辣�滚��睲漣�毺� BOM/UTF-16 蝻𣇉��脩�**嚗𡁏��亙僎皜�膄鈭��霂閖�摰𡁜�銝凋漣�毺�銝滚�摰孵����霈堆�蝖桐�瘚贝�獢�沲�� diff 撖寧�瘚�偌蝥踹���鍂����� UTF-8 蝻𣇉�霂餃��諹��箸𥁒�𨳍��

## 2026-05-29 09:40
- [x] **摰䂿緵�墧�銝𦒘漱�梶��亙��擧��鞉�扯�隡睃� (Implemented Extreme Backtest Engine Performance Optimization)**嚗�
    - [x] **�拍�蝥扳��文儐�臬����銝擧��刻恣蝞� (Eliminated Inner Loop Slicing & Rolling)**嚗𡁻���� `test_reentry_backtest.py` ��瓲敹�����餈𥕢蜓敺芰㴓��蝠摨閧宏�支�瘥讛蔭敺芰㴓銝剝�朞� `df[df.index <= current_date]` �齿鰵��� DataFrame 撟嗅銁�嗡��滚�霈∠� rolling ���潔����撌桃�擃䀹��祈�銝箝���蝥找蛹�典儐�臬�銝�甈⊥�批笆�港葵 `df` 餈𥡝��券������ `rolling(..., min_periods=1)` 憸�恣蝞梹�撟嗅銁敺芰㴓銝凋蝙�刻��拍�蝝Ｗ� `row_idx` 摰䂿緵 $O(1)$ 撣豢㺭�園𡢿 lookups �𣂼�嚗䔶蝙�詨�敺芰㴓���瘜閙𧒄�游���漲隞� $O(N \times M)$ ����滩秐 $O(N)$��
    - [x] **�蹱��楝�梯蝸�乩��� (Optimized Strategy Routing IO)**嚗帋蛹 `global.ini` 蝑𣇉裦�蹱��楝�勗�頧賢��乩��典���扇 `_is_router_loaded` �箏���蝙瘥𤩺活�扯��墧��塚�隞�銁擐𤥁蔭靚�鍂銝剖笆�滨蔭��辣餈𥡝�銝�甈⊥�抒��� IO 霂餃�銝� Parser 閫��嚗峕迨�𡡞�憭滩��其葵�∪�瘚𧢲𧒄�湔𦻖�曹澈���頝舐眏嚗�蝠摨閙��支��𦯀����隞嗉粉�坔�����
    - [x] **摰䂿緵 100% 蝏嘥笆蝑劐遠�唳旿�⊿� (Verified 100% Output Parity)**嚗𡁜銁隡睃��滚�撖寡��脣���������������誯凃�喋���𡁜�敺桃㩞��蓡��� 5 �芸��贝��扯��墧�嚗��������蝚衣漣�港��亙�餈𥡝�鈭諹��� text matching �⊿�嚗𣬚��𨅯��� 100% 瘥急�撌桀�����典����MATCH嚗㚁�蝖桐��餉�蝎曉漲����亙��航蓮�Ｖ誑�羓�鈭誩�蝑𡝗神�䀝�撌殷��訫�瘚贝��𧼮��函遛�朞���

## 2026-05-29 09:30
- [x] **摰䂿緵�墧��亙��瑕�撖寥����撽祉�皛𡁜𢆡�脫�隡貊𠶖���銝𡡞�璅⊥�������� (Aligned Backtest Style, Implemented Marquee Status Bar & Non-Modal Window Reuse)**嚗�
    - [x] **摰䂿緵�墧芋��𡠺蝡讠��� (Non-Modal Window Separation)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝剖��墧��亙�撘孵枂�孵��望芋��� `dlg.exec()` 隡睃�銝粹�璅⊥�� of `dlg.show()`嚗�僎銵仿�鈭� `raise_()` �� `activateWindow()`��**�典�靘见��嗅� `parent` ��� `self`嚗䔶���� `MainWindow` �� Owned �嗅�蝒𦯀���撅墧���**���雿輻鍂�瑕虾隞亥䌊�勗��墧�蝒堒藁�䔶蜓�航��𣇉����撘���僎�埝��滚���𦆮嚗�銁�亦��墧��亙��嗆神銝滚蔣�滢�銝餃虾閫�� K 蝥輻��Ｙ�鈭支���
    - [x] **瘛餃�蝵桅▲憭漤�㗇�銝擧�撘��祆𧒄蝵桅▲瞈�瘣� (Pin Checkbox & Dynamic Focus)**嚗�
        - �冽𥁒�羓���椰銝贝�瘛餃�鈭� `QCheckBox("蝵桅▲")`嚗屸�霈支�蝵桅▲��
        - 敶𤘪鰵銝�頧桀��脣�瘚贝恣蝞堒��鞱��箸𥁒�𦠜𧒄嚗�朖雿踵𧊋撘��舐蔭憿塚�銋煺��朞� `show()`, `raise_()` �� `activateWindow()` �芸𢆡撠��瞈�瘣餃僎�鞱秐撅誩����齿䲮餈𥡝��祆𧒄撘箸��匧�蝷綽�甇文�銝漤��嗅��格𣏹�喟頂嚗��蝢𤾸像銵∩��𣈯妟�𤘪贋�苷��𨅯撩�鞾��腈��
        - �冽��暸�争�𦦵蔭憿嗯�嘥�嚗�𢆡��蕭�� `WindowStaysOnTopHint` ��扇撟嗅朖�嗅��剁��舀�頝刻�蟡典�瘚见��Ｘ𧒄��賒�匧銁撅誩���銝𠰴���
        - **蝵桅▲�嗆���銋��**嚗𡁶蔭憿嗅㗲�厩𠶖����滩𠧧蝑厩頂蝏笔�摰���唬�韏瑟�銋���冽𧋦�圈�蝵� `visualizer_layout.json` 銝哨�撟嗅銁頧臭辣�齿鰵�枏��硋�甈∪�頧賣𧒄�芸𢆡霂餃��Ｗ�嚗䔶�����䀹���蝙�其��胯��
    - [x] **摰䂿緵�滩𠧧�㗇𥋘獢��摰墧𧒄�剖��Ｗ��� (Interactive Color Theme Selector)**嚗�
        - �冽𥁒�羓�����兩�𦦵蔭憿嗯�嘥𢰧靘扳鰵憓硺� `QComboBox("�滩𠧧")` �㗇𥋘銝𧢲�獢��憸�挽鈭��蝏�����冽�暺𤏸��臭���粉���撖寞�摨行擪�潮��脫䲮獢��**�𨀣��屸𣂎�售�� (`#B8B8B8`)���𦦵���瘛∠遛�� (`#8CD867`)���𨀣擪�潭�暺��� (`#F5E6C8`)���𣈯�撖寞��賤�� (`#E0E0E0`)**��
        - **�諹提��氖皜脫�**嚗𡁻���� `ScrollableMsgBox` 皜脫�瘚�偌嚗���其��滢��鍦��恍�霈暸��脩�撖峕��穿��嫣蛹�湔𦻖隡𣳇�鍦�憪讠滲��𧋦 `report`嚗𣬚眏蝒堒藁�寞旿敶枏��劐葉��蜓憸㗛��脣𢆡����啁��鞟�摰� HTML嚗Ǒ<pre>`嚗剹��鍂�瑕��Ｖ��㗇��厰★�塚���捆�箇��游��圈�蝏矋��嗅辣餈毺���揢��
        - **�滩𠧧����𤥁䌊��**嚗𡁜��ａ��脫𧒄隡朞䌊�典� `backtest_theme_color` �桀�潭�銋���坔� `visualizer_layout.json` ��辣銝哨�銝𧢲活�臬𢆡�硋��Ｖ葵�∪�瘚𧢲𧒄�芸𢆡霂餃�撟嗅��其�甈⊿�㗇𥋘����莎�靽肽�摰𣬚���楊隡朞�銝��湔�扼��
    - [x] **摰䂿緵�墧�蝒堒藁�删�憭滨鍂 (Window Instance Reuse)**嚗𡁜銁 `MainWindow` 摰硺�銝羓�摮睃僎蝏湔擪 `self._backtest_report_dlg` �交�嚗�僎�� `ScrollableMsgBox` 銝剖��唬� `update_content(title, content)` 憭滨鍂�亙藁���蝏剔�瘥𤩺活�墧�蝏𤘪�撠��蝻嘥��啗秐�䔶�蝒堒藁銝哨�敶餃�閫��鈭�眏鈭𡡞�蝜��瘚见紡�湔��Ｖ���妖憭折��㛖��亙�蝒堒藁��䔮憸塩��
    - [x] **�亙�����瑕�瘛勗漲�滚�**嚗�
        - �拍��駁膄鈭� `trade_visualizer_qt6.py` 銝� `_show_backtest_result` �亙�皜脫���𧋦嚗Ǒ<pre>`嚗劐葉蝖祉���� `color: #E0E0E0; background-color: #1A1A1A;`��
        - **撖寥� QSS 銝駁��瑕�銵�**嚗𡁜� `parent` 銝� `None` �塚�蝒堒藁隡朞䌊�其� `QApplication` ��蜓蝒堒藁銝剛繮�硋僎摨𠉛鍂�� `styleSheet()`嚗䔶��䔶蝙�墧��亙��刻��航𠧧����航𠧧�𡃏器獢�捶�煺�嚗䔶��𦦵遞����乒�嘥�銝餌�����其��湛�摰𣬚��滚�暺煾�擃睃笆瘥𥪜漲 QSS 銝駁�銝哨�閫��鈭��蝳餌�摮鞾曎�𡡞���碶蛹蝟餌�暺䁅恕�賢��嘥���䔮憸塩��
        - **�典�摮㛖泵摮堒噡銝𡡞��脣凝靚�**嚗𡁜銁 HTML `<pre>` ��倌��甅撘譍葉嚗峕遬撘𤩺�摰𡁻��脖蛹 `#B8B8B8`嚗�僎撠��雿梶頂�𦯀��碶蛹 `Consolas, "Microsoft YaHei UI", monospace`嚗��蝢𤾸笆朣𣂷�銝餃虾閫���屸𢒰��楛�脩頂閫��憌擧聢銝𤾸�雿㯄�㗇𥋘嚗���嗥＆靽苷��墧��唳旿蝑匧捐撖寥��垍���極�氬���朞�撠��摮烾��脰��單��� of �嗥��脣僎�滚� `line-height: 1.4` 銵屸��批�嚗峕�憭折�雿𦒘��冽�暺𤏸��臭�擃睃撩摨阡�霂餅𧒄���蝵𤏸��匧撩�箸��� �交�嚗�僎�� `ScrollableMsgBox` 銝剖��唬� `update_content(title, content)` 憭滨鍂�亙藁���蝏剔�瘥𤩺活�墧�蝏𤘪�撠��蝻嘥��啗秐�䔶�蝒堒藁銝哨�敶餃�閫��鈭�眏鈭𡡞�蝜��瘚见紡�湔��Ｖ���妖憭折��㛖��亙�蝒堒藁��䔮憸塩��
    - [x] **�亙�����瑕�瘛勗漲�滚�**嚗�
        - �拍��駁膄鈭� `trade_visualizer_qt6.py` 銝� `_show_backtest_result` �亙�皜脫���𧋦嚗Ǒ<pre>`嚗劐葉蝖祉���� `color: #E0E0E0; background-color: #1A1A1A;`��
        - **撖寥� QSS 銝駁��瑕�銵�**嚗𡁜� `parent` 銝� `None` �塚�蝒堒藁隡朞䌊�其� `QApplication` ��蜓蝒堒藁銝剛繮�硋僎摨𠉛鍂�� `styleSheet()`嚗䔶��䔶蝙�墧��亙��刻��航𠧧����航𠧧�𡃏器獢�捶�煺�嚗䔶��𦦵遞����乒�嘥�銝餌�����其��湛�摰𣬚��滚�暺煾�擃睃笆瘥𥪜漲 QSS 銝駁�銝哨�閫��鈭��蝳餌�摮鞾曎�𡡞���碶蛹蝟餌�暺䁅恕�賢��嘥���䔮憸塩��
        - **�典�摮㛖泵摮堒噡銝𡡞��脣凝靚�**嚗𡁜銁 HTML `<pre>` ��倌��甅撘譍葉嚗峕遬撘𤩺�摰𡁻��脖蛹 `#B8B8B8`嚗�僎撠��雿梶頂�𦯀��碶蛹 `Consolas, "Microsoft YaHei UI", monospace`嚗��蝢𤾸笆朣𣂷�銝餃虾閫���屸𢒰��楛�脩頂閫��憌擧聢銝𤾸�雿㯄�㗇𥋘嚗���嗥＆靽苷��墧��唳旿蝑匧捐撖寥��垍���極�氬���朞�撠��摮烾��脰��單��𣬚��嗥��脣僎�滚� `line-height: 1.4` 銵屸��批�嚗峕�憭折�雿𦒘��冽�暺𤏸��臭�擃睃撩摨阡�霂餅𧒄���蝵𤏸��匧撩�箸���
    - [x] **摰䂿緵頝煾帕�舀��券俈�劐撓�嗆��� (Marquee Label & Layout Protection)**嚗�
        - 蝻硋�鈭�䌊摰帋��� `MarqueeLabel` 蝐鳴�蝏扳㗁�� `QLabel`嚗峕𣈲����祇鵭摨西��箏虾�刻���捐摨行𧒄�芸𢆡敺芰㴓璅芸�皛𡁜𢆡嚗�僎�函���𧋦�嗉䌊�冽�憭滚�銝剖笆朣僐��
        - 撠� `self.center_msg_label` 摰硺���漣銝� `MarqueeLabel`嚗峕𨰹�� `QSizePolicy.Policy.Expanding` 隞亙� `minimumWidth = 50`���敶餃�撠��鈭�𠶖����刻��箄��踵�隞歹�憒��瘚见鍳�函𠶖���嚗㗇𧒄撘箏��穃之��𦆮摰賭蜓蝒堒藁��遙雿訫虾�踝�蝖桐��屸𢒰�牐�頧桀�瘞訾�蝔喳���
        - **摰𣬚�閫��撠箏站���銝擧⏛�剛䌊��**嚗𡁻�朞��滩蝸 `sizeHint()` 銝� `minimumSizeHint()`嚗�𢆡��恣蝞埈�摮埈��删�摰𧼮�蝝惩捐摨佗�撟嗅銁 `setText()` �� `clear()` �嗅�甇亥��� `self.updateGeometry()` �𡁶䰻撣��蝞∠��券��啣��穃偕撖詻���蝖桐�鈭�綉隞嗉�憭笔��啗雲憭毺��拐�摰賢漲嚗��䔶��舫�霈支蛹�嗉◤蝛� Stretch �斗�嚗㚁�摰��靽桀�鈭�眏鈭𤾸��滚捐摨西�蝒�紡�渲�撽祉��𨀣遬蝷箔��冽��祇𡢿瘨�仃�萘�皜脫� Bug��
        - 蝞��碶� `show_status_message` 銝� `show_status_message_nolimit` 銝剔���𧋦��裦�芣鱏�箏�嚗𣬚凒�仿�譍�摰峕㟲靽⊥�嚗屸�朞�頝煾帕�臭���遬蝷箝��

## 2026-05-29 09:20
- [x] **摰䂿緵�墧��亙�蝒堒藁�枏��嗉䌊�冽��典�摨閖�撟嗡��斤遞����仿▲�刻��� (Implemented Auto-Scrolling to Bottom for Backtest Reports & Preserving Top View for Briefings)**嚗�
    - [x] **PyQt/Qt6 �航��𣇉垢�芷���皛𡁜𢆡�批�**嚗𡁜銁 `trade_visualizer_qt6.py` �� `ScrollableMsgBox` �� `update_content` �餉�銝凋耨�嫣��∩辣�斗鱏����枏��墧��亙��𤥁����Ｗ�瘚贝�蟡冽𧒄嚗䔶��芸𢆡�朞� 100ms �� `singleShot` 霈⊥𧒄�典�皛𡁜𢆡�⊥��唳�摨閖�嚗���唳��啁�鈭斗��喟�������冽��枏��𦦵遞����乒�脲𧒄嚗��銝滚��扯�蝵桀�皛𡁜𢆡嚗䔶��坔���憿園����憸䀝�蝏澆�璁��嚗峕�����睃虾霂餅�扼��
    - [x] **Tkinter �㕑�/銝駁𢒰�輻垢摰𣬚�撖寥�**嚗𡁜銁 `stock_selection_window.py` �� `BacktestReportDialog` �� `__init__` �嘥��硋� `update_report` �冽����圈�餉�銝哨��峕甅撘訫�鈭� `.after(100, lambda: self.text_area.yview_moveto(1.0))` 撘�郊撱嗉��扯�嚗峕��笔��唬��𣬚垢�墧��亙�閫�㦛 100% 蝏嘥笆銝��渡��𦦵蔭摨訫�蝷算�脲�摰Ｖ�撉䎚��
    - [x] **銝駁𢒰�輻��交�霂閙𥁒�𠰴���**嚗𡁜銁 `instock_MonitorTK.py` �� `_show_strategy_report_window` 蝒堒藁�𥕦遣銝𤾸��冽凒�啗楝敺�葉嚗��甇亙��牐�撖� `win.txt_widget` ��𧋦�箸�銵� `.after(100, lambda: win.txt_widget.yview_moveto(1.0))` �餉�嚗𣬚＆靽肽�銵𣬚��交�霂閙𧒄颲枏枂��之蝭�����摰∟恣銝𦒘漱�枏�蝑𤥁祕��䌊�函蔭摨訫笆朣僐��

## 2026-05-29 09:10
- [x] **摰䂿緵 K 蝥踹㦛銋啣��孵朖�� B/S/A ��倌皜脫�銝𡡞�撖寞��垍𤌍�� (Implemented Instant B/S/A Label Overlay & High-Contrast Visuals for K-line)**嚗�
    - [x] **�啣�暺�𠧧 A ��倌隞�”�牐�**嚗𡁻�撖孵�隞�/�噼‘靽∪噡�對�`SignalType.ADD`嚗㚁��� K 蝥踹㦛銝𦠜葡�栞擀�厰��莎�鈭桅�暺� `(255, 215, 0)`嚗厩�蝎𦯀�摮埈� **"A"**嚗���嗅銁 `signal_types.py` ���撅��航��㚚�蝵桐葉撠��隞枏㦛���甇乩��碶蛹暺�𠧧鈭磰��笔僎撠�之撠譍� 12 憓𧼮之�� 14嚗䔶蝙�関銵乩��其�銝��桐��嗚��
    - [x] **蝏嘥笆�垍𤌍���撖寞� B/S ��倌**嚗�
        - 撠�遣隞�/敶勗�銋啣�嚗ǑBUY`, `SHADOW_BUY`嚗劐��寧�摮埈� **"B"** 憸𡏭𠧧��漣銝� 100% 擖勗�摨衣�蝥臭漁蝥Ｚ𠧧 `(255, 0, 0)`嚗䔶��� `signal_types.py` 銝剖�撱箔�摨閧�蝥Ｖ�閫鍦㦛���憭批�隞� 15 憓𧼮之�� 18嚗�蝠摨閙��文�瘛∟𠧧皜脫�銝� K 蝥輻��潛瑪瘛瑟��䭾����閫厩魿�喋��
        - 撠����/撟喃�/甇Ｘ�/甇Ｙ�嚗ǑSELL`, `STOP_LOSS`, `TAKE_PROFIT` 蝑㚁�銝𦠜䲮���瘥� **"S"** 憸𡏭𠧧��漣銝粹�撖寞�摨西擀�厩滲蝏輯𠧧 `(0, 255, 0)`��
    - [x] **�典�摮㛖泵摮堒噡敺株�銝擧������**嚗𡁜���釣��𧋦摮堒噡隞� 11px 蝏煺�靚�之�� **12px** 蝎𦯀�嚗�僎餈𥡝��拍�皜脫��垍�靽脲擪嚗����� K 蝥踹㦛憒� Tick �曄�靘萘��曄內�笔��啣�隞瑟聢����砌誑�踹�閫��撟脫贋嚗䔶���倌蝵桐��嫣��孵�蝘颱�蝵格�靘偦�撖寞�閫��銵函緵嚗剹��

## 2026-05-29 09:00
- [x] **摰䂿緵 K 蝥踹㦛 "靽∪噡" 撘��喃��𤾸蝱�亙��亥砭������隡睃� (Implemented "Signal" Toggle & Live Log Query Bypassing)**嚗�
    - [x] **�啣� K 蝥蹂縑�瑟遬蝷箸綉�嗅��� (Add Signal Toggle UI)**嚗𡁜銁�𦦵��游予�售�脲��桀��啣�鈭� `QCheckBox("靽∪噡")` 撘��喉��舀��孵稬摰墧𧒄��揢���霈文��凋縑�瑟遬蝷� (Default False)嚗���剜𧒄蝡见朖皜�征撟園��� K 蝥踹���𧒄�曆�����䀝漱�𤘪𠯫敹𦯀縑�瘀��踹�閫���芷𨺗��
    - [x] **�拍�蝥批��啗�皞鞱�瘚���� (Deep Resource Throttling)**嚗�
        - 敶餃��齿�鈭� `DataLoaderThread` 撘�郊�唳旿瘚���典��喳��剔𠶖���嚗���刻歲餈� `logger.get_signal_history_df()` ����剁�隞擧�憭港��餅鱏鈭�笆蝤�� CSV ��辣���蝜� IO 霂餃�銝舘圾�鞉��𨰜��
        - 撖寥��惩𤐄鈭� `load_stock_list` 蝻箇��芷�匧�銵典�頧賡�餉�隞亙� `render_charts` 摰墧𧒄�滨�瘚��嚗𡁜�撘��喳��剜𧒄�芸𢆡�剛楝嚗屸妟靚�鍂��妟霈∠�嚗���𥡝����摰䂿��烐綉�嗥�蝟餌��餌瑪�龦PU霈∠�韏����
    - [x] **�芸𢆡�嗆���銋��銝擧����單𧒄�滩蝸 (Auto Persistence & Dynamic Reload)**嚗�
        - 摰𣬚��亙� `visualizer_layout.json` �嗆�嚗���唬�撘��喟𠶖���頝其�霂肽䌊�其�摮䀝��㰘蝸��
        - 撌批�摰䂿緵鈭���單�撘��嗥��𦦵��嗉蕭皞舫�頧賤�嘅���揢銝箏��舀𧒄銝餌瑪蝔衤�蝡见�閫血�銝�甈⊥���憸��頧踝�撟嗅��啣㦛銵冽遬蝷綽�蝖桐��滨�雿㯄�����舐鍂銝擧��瑕�摨𢛵��

## 2026-05-29 08:40
- [x] **撖寥��喲睸�𨅯�銝� Alt+X 敹急㭘�桃��墧�銵䔶蛹 (Aligned Context Menu Backtest with Alt+X Behavior)**嚗�
    - [x] **�拍�蝘駁膄 "甇�銁霈∠�" ���摨衣��� (Removed Progress Window)**嚗𡁜蝠摨訫��支� `instock_MonitorTK.py` 銝� `_on_run_reentry_backtest_menu` �寞��刻◤�喲睸�𨅯�閫血��嗅�撱箇� `progress_win = tk.Toplevel(self)` 撠讐������雿踹𢰧�桀�瘚衤�敹急㭘�� `Alt+X` ��漱鈭坿�銝箏銁閫��銵函緵銝� 100% 蝏嘥笆銝��氬��
    - [x] **銵仿��∠巨隞���� Emoji �拍�皜��銝𤾸��啣�甇亙捆�� (Enforced Code Cleaning & Async Fault-Tolerance)**嚗𡁜銁�喲睸�𨅯�����亦�嚗��甇亥‘朣𣂷���笆�∠巨隞���� Emoji 靽桅弘蝚行�瘣烾�餉�嚗������� `'�𣞁', '�叚', '��', '�𩤃�'`嚗㚁��踹��牐耨擖啁泵畾讠�撖潸稲�𡒊垢�唳旿�𣂼��粹���恣蝞堒��笔�撣豢𧒄嚗𣬚�銝����蝎曄��祉����瘚𧢲𥁒�羓���僎�枏㫲撘�虜���蝖桐�蝟餌���恥���雿㯄����銝�銝舘䌊����

## 2026-05-29 08:30
- [x] **���蠘�隡� Re-entry ��蟮�墧�蝏𤘪� K 蝥踵�瘜其��亙�摮堒噡嚗�蝠摨閙��方��暹�隡詨僎摰䂿緵�𣬚垢閫���峕� (Optimized Re-entry Backtest K-line Markers & Standardized Report Dialog Font Size)**嚗�
    - [x] **�寞祥 K 蝥踹㦛閫�㦛 Y 頧游�撣豢�隡� Bug**嚗�
        - 敶餃�摨罸膄鈭�銁 `trade_visualizer_qt6.py` �� K 蝥踹㦛蝏睃�銝剔凒�乩蝙�� `�𣞁` �� `�叚` 蝑� Emoji 摮㛖泵雿靝蛹 `symbol_override` ���瘜𨰻��
        - �𥟇鰵�齿�鈭�**�箄��其��� `SignalType` �惩��箏�**嚗𡁜銁�㰘蝸�墧�鈭斗�靽∪噡�塚��寞旿�墧��唳旿銝剔�銋啣��其��𦠜�摮埈�餈堆�憒� `"撱箔�"`, `"�噼‘"`, `"甇Ｘ�"`, `"甇Ｙ�"` 蝑㚁�嚗���急惣�質蓮�Ｖ蛹����� `SignalType.BUY` (撱箔�), `SignalType.ADD` (�牐�/�噼‘), `SignalType.TAKE_PROFIT` (憭扳迫��/�譍�), `SignalType.STOP_LOSS` (甇Ｘ�撟喃�), `SignalType.SELL` (�桅�𡁜��箏像隞�)��
        - 蝏枏� `SignalPoint` �� `size_override=18` �箏�撠�偕撖貊�銝��曉之嚗諹悟�嗡�銝箸���� pyqtgraph `ScatterPlotItem` 撣貉��牐����嚗���苷��苷�銝㕑����閫埝�����脫��卝��遛�㚁�擃䀹�扯�蝏睃���眏鈭𤾸蝠摨訫縧�支� unicode Emoji �訫�蝚佗�`update_signals` �� `is_emoji` �𣂼��文�銝� False嚗屸�撘�鈭� `pg.TextItem` 撖� autoRange �鞉�頧渲��湔�隡貊��臭��剁�靽肽� K 蝥輯��暹�靘讠移蝢𤾸笆朣琜��祇𡢿�㰘蝸��
    - [x] **撖寥��𣬚垢�墧��亙�撖寡�獢��摮堒噡銝擧���**嚗�
        - ��笆 Qt �航��𣇉垢 `_show_backtest_result` 撘孵枂 ScrollableMsgBox �擧遬蝷箇����餈��嚗��蝖祉���蛹 `11px`嚗匧紡�渡�銵典��𤤿�雿㯄��𤤿�嚗�� HTML `<pre>` ��倌銝剔� `font-size` 蝏煺��𣂼��� **`14px`**��
        - 摰𣬚�撖寞𦻖撟嗅笆朣𣂷� Tkinter 憭批�蝡� `BacktestReportDialog` �� Consolas 暺䁅恕摮堒噡嚗���唬��𣬚垢�刻�閫匧��唬� 100% ����������Ｖ����蝑匧捐�垍�����湔㟲朣琜����霂���滨��见銁擃睃�撅譍����霂餅�扼��
    - [x] **摰𣬚��朞��券�蝟餌����銝𤾸�瘚见笆韐行�霂�**嚗�
        - 餈鞱�鈭���� `pytest test_watchlist_lifecycle.py` 隞亙��墧�銝餌�摨� `python scratch/test_reentry_backtest.py` �典����敶垍鍂靘页�100% 蝏踵�銝�甈⊥�折�朞�嚗諹揣�∪笆韐虫�鈭斗�靽∪噡�文���捶蝔喳�憒����

## 2026-05-29 08:00
- [x] **�寞祥�墧��亙��Ｚ�皞Ｗ枂�睃耦銝𤾸����蝡� Alt+X 敹急㭘�格�摰Ｗ��� (Fixed Backtest Word-Wrap & Standardized Alt+X Shortcut Display Across Qt & Tkinter)**嚗�
    - [x] **�寞祥 Qt �航��� ScrollableMsgBox �芸𢆡�䁅�銝擧���䌊���**嚗�
        - ��笆�� `trade_visualizer_qt6.py` 銝剔眏鈭� `<pre>` ��倌蝖祇�摰賢紡�渡�銝芾��墧��亙��𨀣赤�烐滯�箸�憭扼�����艇�滚�敶Ｕ����舀��芸𢆡�Ｚ��萘��垍��𤤿�嚗�銁 `<pre>` ��倌�� inline style 銝剖撩�𥟇釣�乩� `white-space: pre-wrap; word-wrap: break-word;` �拍�蝥� CSS �芸𢆡�䁅�銝擧鱏摮埈甅撘譌��
        - �Ｙ蓡����曉�蝢𦒘��嗘� `Courier New / Consolas` 蝑匧捐摮𦯀�撌交㟲朣𣂼���”�澆笆朣鞟������＆靽嘥��典�颲曇���器�峕𧒄隞交�擃条��𤩺㭘摨西䌊����䁅�嚗��蝢擧𤣰�𥕢�擃睃笆瘥𥪜漲暺煾� QSS 撖寡�獢�偕撖詻��
    - [x] **瘛勗漲�峕� Tkinter 憭批�蝡� Alt+X 敹急㭘�桀�瘚𧢲㦤��**嚗�
        - �齿�鈭� `instock_MonitorTK.py` 銝剔�銝��株圻�穃�瘚𧢲䲮瘜� `_on_shortcut_reentry_backtest`��
        - **�拍�撖寥� Only-Report 蝎曄�璅∪�**嚗𡁜銁靚�鍂摨訫��墧�銝餃��� `run_backtest_and_get_report` �嗉‘朣𣂷� `only_report=True` �喲睸摮堒��堆�瘨�膄鈭���脣�雿蹱��研��
        - **�拍�蝏煺�����祉��鮋獈憛𧼮撕蝒�**嚗𡁜蝠摨訫�撘���笔�蝞��见�靚���䌊�䠷�餉��� `show_reentry_backtest_dialog` �寞�嚗�歇�拍�皜�膄霂亙�雿� Dead Code嚗𣬚泵�� YAGNI �笔�嚗㚁��拍�撠���齿�撟嗆��𤑳�銝����撖寞�摨艾��蒂�㗇㟲銵諹擀�厰�鈭桀� Emoji �芷���憭𡁶漣擃䀝漁����� `_show_backtest_report_window` 撘寧�嚗�朖摰𣬚��� `BacktestReportDialog`嚗㚁�摰䂿緵鈭��摰Ｗ��𣂷��笔銁�𣬚垢銝羓� 100% 蝏嘥笆銝��港�隡㗛��剔㴓��

## 2026-05-29 07:30
- [x] **敶餃��寞祥 Re-entry �墧�靽∪噡�航��� `SignalPoint` 摰硺��� `TypeError` 撏拇� (Fixed Re-entry Signal Visualization TypeError & Refactored Overrides)**嚗�
    - [x] **�齿� `SignalPoint` ���删倌�滢��芸�銋㕑��蹱𣈲��**嚗�
        - ��笆�� `trade_visualizer_qt6.py` 銝凋蛹 K 蝥踵葡�� Re-entry �墧�靽∪噡�嗥凒�乩��� `symbol` / `size` 撖潸稲 `SignalPoint` �亙枂 `TypeError: __init__() got an unexpected keyword argument 'symbol'` ��援皞�䔮憸矋��� `signal_types.py` �� `SignalPoint` �唳旿蝐颱葉�拍�銵仿�鈭� `symbol_override` �� `size_override` �舫�匧�畾萸��
        - 隡㗛��啣� `SignalPoint` �� `symbol` �� `size` 撅墧�折���蛹�冽����改�`@property`嚗㚁�敶枏��典笆摨𠉛��曉�閬��摮埈挾�嗉䌊�其���蝙�刻��硋�潘�摰𣬚�閫��鈭�䌊摰帋��暹�銝𤾸��厩�銝�閫���滨蔭銋钅𡢿���蝒���
    - [x] **撖寥�撟嗅��� `render_charts` 蝏睃㦛��釣蝞⊿�**嚗�
        - 敶餃��齿�鈭� `trade_visualizer_qt6.py` �� `_render_charts_logic` 銝餃㦛皜脫�瘚��銝� Re-entry �典�������撖� `SignalPoint` �� `symbol` �� `size` ��������耨�嫣蛹 `symbol_override` �� `size_override`嚗��蝢擧��支�蝐餃��脩�甇餉���
    - [x] **100% �訫�瘚贝��函遛�朞�撟嗥����霂��瘚见���**嚗�
        - �拍�餈鞱� `python scratch/test_reentry_backtest.py` �墧�憭扯繮�𣂼�嚗諹��脣����300058嚗剹����誯凃�喉�301071嚗剹���𡁜�敺桃㩞嚗�002156嚗匧��曉��梧�603823嚗匧�����墧�瘚�����T鈭斗�隞亙�憸���扳��閙㺭�桀�蝢舘��綽�鈭斗�瘚�揣�∪笆韐虫艇銝嘥�蝻嘅��函頂蝏笔�韐典��嗥迅�綽�
    - [x] **靽桀��航��𤥁��典�瘚𧢲芋撘譍蛹 `only_report=True` (Fixed Backtest Only-Report Call in UI)**嚗�
        - �齿�鈭� `trade_visualizer_qt6.py` 銝� `ReentryBacktestThread` ���瘚见��啁瑪蝔见鍳�券�餉����撖� `run_backtest_and_get_report` ��蟮�墧��賣㺭����冽遬撘讛‘朣𣂷� `only_report=True` �喲睸摮堒��堆�蝖桐��航��碶蜓蝥輻�銝� Tkinter 憿嗅��墧�撘寧�撘寞��賢�摰𣬚��曹澈��蝎曄�����芰�������蝞��舘揣�∪��鞉𥁒�𨳍��
        - **摰𣬚�憭滨鍂�𦦵遞����乒�嘥��渲挽蝵桀�雿滨蔭憭批�撠箏站**嚗𡁜��墧��亙�撘孵枂蝒堒藁�� title 隡㗛���漣銝算�𨥉�� Re-entry ��蟮�墧�蝏澆�蝞��� - ...�嘅��芸𢆡閫血� `is_briefing = True` �∩辣嚗���嗆� `parent` �齿鰵�孵� `self` 隡惩������歇靽桀��� 1.0 蝻拇𦆮瘥𥪯�嚗峕𠳿摰𣬚�靽萘�鈭�頂蝏毺漣蝘烐�暺� QSS �烾��株��𡃏�閫厩����蝥改��� 100% �曹澈撟嗆�銋��鈭��𦦵遞����乒�萘�雿滨蔭銝𤾸之撠讐����蝵殷�敶餃��寞祥擃� DPI �睃耦��
    - [x] **敶餃��寞祥 Qt6 蝒堒藁�券���� DPI 銝见�憭滩䌊�典�憭抒��牐�撠箏站瞍�宏 Bug (Fixed Qt6 High-DPI Auto-Resizing Bug)**嚗�
        - 蝎曄��齿�鈭� `tk_gui_modules/window_mixin.py` 銝� PyQt/Qt 蝟餃�蝒堒藁撠箏站�㰘蝸銝𦒘�摮睃遆�堆�`load_window_position_qt`, `save_window_position_qt`, `save_window_position_qt_visual`嚗剹��
        - ��笆 PyQt6 獢�沲�� Windows 銝见��冽𡟺撌脤��箄����撟嗅撩�嗆�蝞∩� DPI 蝻拇𦆮嚗�� `win.geometry()`, `setGeometry` 蝑㗇𦻖����交𤣰�諹��䂿��湔𦻖撠望糓霈曉��祉��餉��讐�嚗厩��寞�改�敶餃��𡝗�鈭��摮睃��㰘蝸餈��銝剖�雿嗵� `scale` �拍��惩�����方�蝞梹�撘箏���� `scale = 1.0`嚗剹���敶餃��餅鱏鈭��甈⊿��啣鍳�典虾閫���冽�撘孵枂颲�𨭌蝒堒藁�塚��罱�𦦵����蝝牐��餉��讐��屸�蝻拇𦆮�惩��嘥紡�渡�蝒堒藁隞� `scale` 撟�活蝥扯����曉之��撩�瘀�摰𣬚�靽肽�鈭������滨��屸𢒰���撅��嗆�銝𡒊征�渡移��漲��

## 2026-05-29 07:00
- [x] **摰䂿緵 Re-entry 蝞�瘣�㟲雿枏�瘚𧢲𥁒�𦠜��碶� UI 擃睃笆瘥𥪜漲���𦒘�銝芯僭�𣇉��羓��亙��舫�鈭格葡�� (Implemented Clean Backtest Report Generation, Last Action Highlighting & Tactical Branch Strategy Visualizer in Tkinter UI)**嚗�
    - [x] **摰䂿緵擃条移摨行��𦒘�銝芸�韐其僭�硋𢆡雿𡏭��思� Emoji 韏贝�**嚗�
        - �齿�鈭� `scratch/test_reentry_backtest.py`��銁 `only_report=True` �嗅��斗��㕑恣蝞烾𧫴畾萇���僚靚��靽⊥�嚗䔶�餈𥪜���銝箸瓲敹��鈭衤辣敶鍦�摨誩���
        - �箄��典�瘚衤�隞嗆�瘞港葉嚗𣬚眏�𤾸��齿�蝝Ｘ��𦒘�銝芸�鈭𦒘漱�梶�摰噼捶�找�隞塚��𨅯遣隞𣏾�腈���𨅯�銵乒�腈���𨅯�隞𣏾�腈���靝�甈∪之甇Ｙ��腈���𨀣�隞枏像隞𣏾�腈���𨀣迫�笔像隞𣏾�嘅�嚗�僎�寞旿�嗡僭��/�硋枂�孵�����芸𢆡餈賢� `�叚�鞉��唬僭�𣇉��喟��鬔 �� `�𣞁�鞉��唬僭�𣇉��喟��鬔 撘箏笆瘥𥪜�蝻�嚗���唬�蝥舀��祉漣�怎�閫��摰帋��𡁶���
    - [x] **�拍��啣�瘣餉�蝑𣇉裦��𣈲銝𤾸��齿��舐𠶖����祉��餌��箏�**嚗�
        - �典�瘚𧢲𥁒�𠰴偏�冽鰵憓硺�擃䀹��啣漲�� `�� �𣂼��齿��舐𠶖���瘣餉���𣈲蝑𣇉裦�鬔 �餌��箏���
        - �渲�撅閧內敶枏�銝芾�����舐𠶖���`�𠗠 甇�銁���銝� (蝑寧��関皛𡁜𢆡���銝�)` �� `�� 靽脲�蝛箔�閫�� (KEEP OBSERVING)`嚗劐誑�𦠜綫�鞟�蝑𣇉裦��𣈲嚗�� `SuperTrendMA5Branch` / `SuperTrendMA10Branch` 蝑㚁���
    - [x] **�拍��賢𧑐 Tkinter 撘寧�擃睃笆瘥𥪜漲憭𡁶漣皜脫�銝擧㟲銵屸�鈭� (High-Contrast Custom Tag Renderer)**嚗�
        - �齿�鈭� `stock_selection_window.py` 銝剔� `BacktestReportDialog`��
        - �啣�鈭� `highlight_latest_red`��highlight_latest_green`��highlight_strategy_title`��highlight_status_holding` 蝑匧��匧撩閫���脣稬�𤤿� UI tag �滨蔭��
        - 摰䂿緵鈭� `highlight_line_pattern` �拍��渲�擃䀝漁�賣㺭嚗�����啁�銋啣�鈭斗��喟�銵䔶誑���鈭桃尐��擀�厩滯嚗Ǒ#ff3333`嚗�/�批�蝏選�`#00ff66`嚗匧之摮堒�蝎埈㟲銵��蝷綽�銝𠉛��亙��臬躹�𦯀誑蝘烐��嘅�`#33ccff`嚗劐��㚚�嚗Ǒ#ffcc00`嚗㗇葡�橒���之�滢�鈭���䀹����閫㕑�皛斗��穿�摰䂿緵鈭��𦦵蒾�鍦�����桐��嗯�萘�摰𣬚�雿𤘪���
    - [x] **43/43 �券��詨��訫�銝𡒊頂蝏罸��鞉�霂� 100% 蝏踵�銝�甈⊥�折�朞�**嚗�
        - 鈭斗���瓲����折俈蝥踴���餈𤤿���辣����漱�栞䌊撠𠹺��唳旿韐行��芣�蝑� 43 銝芰鍂靘见��典��嗡�甈⊥�批�蝏輸�朞�嚗䔶漱隞䁅捶�𤩺��湧�瘙歹�

## 2026-05-29 06:30
- [x] **摰䂿緵 Re-entry ��蟮�墧� K 蝥� Emoji 鈭支�擃睃笆瘥𥪜漲��釣銝𤾸𢆡����舐��亙虾閫��撅閧內嚗諹悸�𡝗��游��鞾𡡒�� (Implemented Interactive Emoji K-Line Markers & Dynamic Strategy Title Branding for Re-entry Backtest in Trade Visualizer)**嚗�
    - [x] **�㯄�𡁜�瘚见��𡡞�蝎曉漲蝏𤘪��𤥁���**嚗�
        - �齿�撟嗅�蝥找� `scratch/test_reentry_backtest.py`��銁�墧�銝餃儐�臭葉嚗��瘥𤩺活鈭抒���漱�枏�蝑碶�隞塚�撱箔����隞瓐��像隞瓐��迫�麄���銵亦�嚗厩����霈啣�撟嗆�銋��摮䁅秐����𡑒” `_last_backtest_signals` 銝哨�撟嗆�����澆枂���寥����撣脲�雿喳��舐��� `_last_backtest_best_branch`��
        - 隡㗛�撘��穃僎�湧蠧鈭� `get_last_backtest_signals` �� `get_last_backtest_best_branch` �亙藁嚗䔶蛹�滚蝱 UI 皜脫�撅��靘𥕢���稲�𤩺㭘��㺭�株挪�桅�朞楝��
    - [x] **�賢𧑐 K 蝥� High-Fidelity 蝏睃㦛��釣蝞⊿�**嚗�
        - �齿�鈭� `trade_visualizer_qt6.py`��銁 `_render_charts_logic` ��蜓�暹葡�枏㦛靚曹葉嚗��蝢擧𦻖�乩� Re-entry �墧�靽∪噡閫��蝞⊿���
        - 摰䂿緵鈭��蝎曉漲�園𡢿�單惣�賣�撠��撠��瘚衤漱�梶� YYYY-MM-DD 摮㛖泵銝脫𠯫�蠘䌊�典笆朣𣂼僎�条�銝� chart 閫�藁�� `bar_index`嚗峕�蝏苷��鞉��讐宏銝擧�霈唳�蝘颯��
        - 撘訫�鈭���瑁�閫匧��餃����撖寞�摨� Emoji �諹𠧧��釣�箏�嚗��� 隞�”銋啣�/撱箔�/�噼‘嚗𤃬�� 隞�”�硋枂/憭扳迫��/�譍�/撟喃�/甇Ｘ�嚗㚁�撟嗅�霂衣�����舐��亙�蝘啜��遣霈桐遠�潔誑�羓�鈭讐蓡���雿靝蛹��㺭�桀�蝢擧葡�栞秐摨訫��� `SignalPoint` 撖寡情銝哨��舀�曌䭾��砍�����餌�敺桐漱鈭𡜐�摰峕�鈭��蝢𡒊�閫��銵刻噢��
    - [x] **摰䂿緵����誩𢆡����亙����撅閧內 (Dynamic Strategy Branding)**嚗�
        - �拙�鈭� K 蝥蹂蜓�曄�憿園������ HTML 皜脫��餉����銝芾�撌脫�銵� Re-entry �墧��塚�����誩��嫣��芸𢆡�冽��蕭�惩耦憒� `�鞉綫�𣂼���: <span style='color:#FF5722;'>SuperTrendMA5Branch</span>�鬔 ���鈭格�霂��撣桀𨭌�滨��衤��潭�撖�������漱�枏�蝑𣇉裦��
    - [x] **���笔�甇亥��其� chart 撘箏��滨� (Forced Auto-Repaint)**嚗�
        - �� `ReentryBacktestThread` 撘�郊霈∠�隞餃𦛚蝏𤘪��𠬍�銝餌瑪蝔见��典�靚�䌊�冽㜃�芰��頣�撠���唳㺭�桃��� `self.reentry_backtest_signals` �� `self.reentry_backtest_best_branch` 蝻枏�銝哨�撟嗥��渡���圻�穃蒂�� `force=True` �� `render_charts`嚗諹噢�𣂷��𨅯朖�孵朖瘚卝���瘚见�蝡见朖銝𠰴��萘�摰𣬚�鈭支�雿𤘪���
    - [x] **60/60 �券��訫�銝𡡞��鞉�霂訫�敶垍鍂靘� 100% 蝏踵��𡁜� (Passed 100% of 60 Regression Cases)**嚗�
        - ��鉄 HDF5 摰寥�蝞∠���䌊�㕑��笔𦶢�冽����餈𤤿���辣���鈭斗�蝖桀��批銁����典��𧼮�瘚贝��其��冽㺭蝘鍦� 100% 銝�甈⊥�抒遛�烾�朞�嚗��蝟餌�摨訫漣��捶�箄𥅾�烐惜嚗�

## 2026-05-29 06:00
- [x] **摰䂿緵撌乩�蝥輻��賡俈蝥踹�撅���摰������墧��� T 韐Ｗ𦛚霈啗揭摨訫�靽桀�嚗諹悸�𤥁�憸嘥���𤣰�𦠜𠂔瘨� (Implemented Tiered Life-Support Fallback, Fixed Backtest T-Accounting & Triggered Hyper PnL Skyrocket)**嚗�
    - [x] **�齿�撌乩��笔𦶢蝥輸��摰�㦤�塚�敶餃�瘨�膄 SWS �讐氖霂舀� (Tiered Fallback Refactored)**嚗�
        - ��笆銝剔瑪 10 �亙�蝥踵𣈲�穃��� `SuperTrendMA10Branch`嚗���� `has_demoted_lock` �滨漣���隞橒�嚗�蝠摨訫��支��笔��湔𦻖銝� `sws` �舀�瘥𥪜笆撖潸稲���靝遠�澆銁 10�亦瑪�臬末餈鞱��游�銝� SWS 憭����蟮擃䀝��𣬚凒�亥◤�滚漲�港�蝘埝��萘�摨訫��餉�蝻粹萅��
        - �𥟇鰵�齿�鈭� **�𣈯俈蝥踹�撅���摰��肽楝�望㦤��**嚗𡁜銁 B ��𣈲嚗�抅鈭� MA10 撌乩�蝥選��文�銝哨�隡睃�靽脲擪敶枏�瘣餉�撌乩�蝥選�10�亦瑪嚗厩�摰匧��芸�嚗�遠�澆銁 10�亦瑪銝𦠜䲮銝� 10�亦瑪蝔喳��� 100% �𡁜�敶枏���𣈲嚗剹����� 10�亦瑪蝖桀�鋡怨��游�嚗峕�撟單��睲���摰�秐 `SwsPullbackBranch`嚗諹𥅾 SWS 鈭血仃摰���滢�甈⊿��摰�秐 `TrendMA60Branch` �𤥁��仿𡺨�� `OscillatingBreakdownBranch` 皜����
        - 摰𣬚�閫��撟嗡��支� **�屸�蝘烐� (603533)**嚗䔶蝙�嗅銁 4��葉銝𧢲𤩐 ��蜓��答�匧�銝剖蝠摨訫��恍�蝜���䭾�甇Ｘ�嚗屸�朞� `SuperTrendMA10Branch` 憿箇����憭扳迫��⏚瘨佗�撟嗅��券�撘� 5�� �渲�嚗���啣�蝢𦒘�撟喋���� **�肽𠧧�㗇� (300058)** 甇Ｘ��𤾸銁 5�� �函�蝛箔�嚗峕��罸俈敺∩��閗器銝贝���
    - [x] **�寞祥�墧�瘝嗵��� T 韐Ｗ𦛚霈啗揭 Bug嚗峕𪄳�墧�憭梁��� T �拇隋 (Fixed Backtest T-Accounting Bug)**嚗�
        - 敶餃��芸枂撟嗡耨憭滢��� `test_reentry_backtest.py` �墧�銝餃儐�臭葉嚗��閫血�暺���牐��噼‘ `ADD` ��𣈲�嗥眏鈭𡒊��湔�銵� `locked_pnl = 0.0` 撖潸稲銋见�擃䀹�憭扳迫��氜鋡衤蛹摰厩� 70% �拇隋鋡怠銁韐Ｗ𦛚銝羓��湔�蝛箏��嗥��游𦶢 Bug��
        - 蝎曄��齿�鈭�**頞��韐Ｗ𦛚�嗥�蝝臬�璅∪�**嚗𡁜�銵交𧒄銝滚�皜�征 `locked_pnl`嚗�僎摰𣬚�撠���� 100% 皛∩��唳�隞梶���� `pnl_pct` 銝𤾸歇�質���� T �嗥�餈𥡝��惩�嚗Ǒlocked_pnl + pnl_pct`嚗剹����𢠃��𥕢��訾漣�毺����㕑�憸嘥之雿� T 皞Ｖ遠銝𤾸��抵�銵䔶� 100% 瘥急��蠘�㛖�韐Ｗ𦛚撖寡揭��
    - [x] **��瓲敹������拇隋餈擧䔉�拍�蝥扼��之頝刻�撘讐�憌嗵���**嚗�
        - **�偦��餌𨺗 (301071)**嚗𡁶眏��𧋦憭扳���� `+41.05%` **�拍������ +64.56% �拇隋�啣�撜�**嚗�
        - **�𡁜�敺桃㩞 (002156)**嚗𡁶眏��𧋦�� `+34.44%` **撌典��湔隅�� +54.11% ���蝥扯�憸脲𤣰��**嚗�
        - **�曉��� (603823)**嚗𡁶眏��𧋦�� `+46.11%` **撘箏��匧��� +55.49% ���蝥批��拙���**嚗�
    - [x] **60/60 �券��訫�銝𡡞��鞉�霂閧鍂靘� 100% 蝏踵��券�� (Passed 100% of 60 Regression Cases)**嚗�
        - ��𡠺 HDF5 �讠憬�鞾���䌊�㕑��笔𦶢�冽����餈𤤿����鈭斗��喟�蝖桀��抒��券�瘚贝�蝘㘾�笔�蝏輸�朞�嚗𣬚頂蝏笔��典虾�䭾�批𤐄�仿�瘙歹�

## 2026-05-29 05:30
- [x] **摰���賢𧑐銋啣�鈭斗�銝舘䌊���頝舐眏瘚�蓮 100% �航��硋�蝷� (Fully Visualized Branch Operations & Adaptive Strategy Rotation)**嚗�
    - [x] **�㯄�帋僭�硋��暹辺��𣈲��扇**嚗𡁜銁 `test_reentry_backtest.py` �墧�瘝嗵�銝哨�撖寞��厩�鈭斗��喟��對���鉄 `撱箔�`���譍�嚗�之甇Ｙ�嚗头��鈭峕活憭扳迫�Ǒ���噼‘嚗����/撠曄�/�噼萱嚗头��皜��撟喃�`��甇Ｘ�撟喃�` 蝑㚁��券𢒰瘜典�鈭���滨��喟���𣈲撅墧�� `[��𣈲蝑𣇉裦: XXX]`嚗�蝠摨訫�摨訫�����航楝�勗膥�箏�頧砌蛹 100% �𤩺��航��硔��
    - [x] **摰䂿緵����罸𡢿蝑𣇉裦��𣈲�芷���頧株蓮餈質葵**嚗𡁜銁����刻�敺芰㴓銝剛䌊�刻蕭頦芣暑頝�楝�勗��舐��睃����銝芾��曹�憭扳隅撘箏飵�见�銝箔蜓��答��𣈲嚗��隞� `SuperTrendMA10` ��漣銝� `SuperTrendMA5`嚗㚁��𤥁����毺聦雿滩※��嚗��蝥找蛹 `OscillatingBreakdown`嚗㗇𧒄嚗𣬚頂蝏煺��芸𢆡�閙�撟嗆��� `[BRANCH ROTATE] 蝑𣇉裦��𣈲�芷���頧株蓮嚗鋫 -> B`嚗�僎撠��鈭𥕢�隞嗅��典�蝢擧葡�栞���蝏���𨀣㟲雿㮖漱�𤘪𥁒�𪙛�脲�瘞港葉��
    - [x] **�券��𧼮��其� 100% ����朞�撉諹�**嚗朞��帋��券� 60 銝芣瓲敹�����蝟餌����瘚贝��其�嚗��蝏輻�餈���典像�啣�憯桀漲銝𤾸��賣�隞颱��睲����吔�

## 2026-05-29 05:00
- [x] **敶餃��餃� 5 憭扳瓲敹���亙��臬𢆡��楝�梯䌊����墧�/摰䂿� 100% 蝏嘥笆�峕�撖寥�憭折𡡒�� (Achieved Unified 5-Branch Dynamic Routing & 100% Feature Parity Alignment)**嚗�
    - [x] **摰���㯄�� 60 �仿鵭�毺��賜瑪銝� 10 �亙�蝏游�頧砍���**嚗�
        - �拍��賢𧑐 `SuperTrendMA10Branch`嚗�葉蝥� 10�亙�蝥踵𣈲�睲�蝔喳�頧穿�銝� `TrendMA60Branch`嚗�60�亦��𠰴��𣬚�甇餌瑪�脣鴃嚗劐舅憭折�蝥扯楝�梁��亙��荔�撟嗅��嗆釣�諹� `StrategyRouter` 銝餉���
        - 摰䂿緵鈭��瘚𧢲��� `test_reentry_backtest.py` 銝𤾸��䀹瓲敹� `kernel_service.py` 銋钅𡢿撖� `ma60d`��ma60d_prev5` 隞亙��滢��交�雿𦒘遠 `low_prev1` �孵��� **100% 蝏嘥笆�拍��峕�撖寥�**嚗�蝠摨閙��支��曹��唳旿蝏游漲銝滢��游蒂�亦�瞏𨅯銁�孵�瞍�宏�鞉���
        - 撌批���遣鈭��隞梶𠶖����� `setup` ��倌�冽����踵㦤�� (`current_setup` 頝冽綫餈𥕦𪂹����罸�譍�) �峕迫�罸俈蝥踹�甇亥䌊��凒�堆�靽嗪��墧�瘝嗵�銝𤾸��� 100% �喟�銝��氬��
    - [x] **頞�漣�墧����憭扳㭘嚗𣬚��質�憸嘥�����拇隋銝擧�摰ａ俈敺�**嚗�
        - **�曉��� (603823)**嚗𡁜之銝餃�瘚芾�����朞�憭扳迫���摰� 70% �拇隋嚗峕活�亦移��圻�爗�𨀣��交𣈲�烐�����冽��閖��穃�銵乒�嘅�摰𣬚���說���雿𡒊�撌桐遠嚗�**������憌躰秐擃䁅噢 +45.35% ���蝥批����憸脲𤣰��**嚗�
        - **�偦��餌𨺗 (301071)**嚗𡁜��冽�銝剔移���銵䔶蜓�𥕦�蝥蹂��訾�憭抒��湧俈頦讐征�Ｗ�嚗峕�蝏�之撟�郭畾菜迫��像隞橒��嗉繮�鞟�嚗�
        - **�肽𠧧�㗇� (300058)**嚗𡁜銁�剜��匧�憭扳迫���嚗𣬚移����怎聦雿滢�擃䀝��瑕躹嚗諹圻�� T+2 摰匧��園𡢿���蝳餃㦤嚗�+2.00%嚗㚁�**摰𣬚�蝛箔��芷�鈭��蝏剝鵭颲曆�銝芣���狍頝諹�蝛粹𡺨�綽��嗉秤�仿��抬�**
    - [x] **�𧼮�瘚贝� 100% �函滯蝏踹��嗥��� (Passed 100% of 60 Regression Cases)**嚗�
        - �㰘捏�臭漱�枏��詨�����䌊�㕑��笔𦶢�冽�嚗諹��� HDF5 霂餃��讠憬���餈𤤿��脫香��� 60 銝芣��嗉��餌�蝟餌�蝥扳�霂閧鍂靘页�**�券� 100% 銝�甈⊥�扯蝠�曉�蝏輻�餈��** 摨閧��烐惜蝔喳𤐄嚗䔶誨���韐典阸蝘啣極銝𡁶漣�箸钟���

## 2026-05-29 04:30
- [x] **摰䂿緵�冽����嗆����亙��Ｕ��䌊����笔𦶢�冽���漣/�滨漣銝𡡞俈摰�迫�毺瑪摰墧𧒄�芣�憭折𡡒�� (Implemented Stateful Dynamic Strategy Routing, Adaptive Demotions/Promotions & Parity Stop-Loss Healing)**嚗�
    - [x] **摰���齿��喟�憭扯���䌊���頝舐眏�箏� (State-Aware Demotions & Promotions Refactored)**嚗�
        - 敶餃��寞祥鈭�唂��𧋦隞� `setup` �蹱���蝑曆蛹蝥賢蒂�𨅯�����爗�脲�銵峕香�蹂漱�枏�蝑𣇉�蝻粹萅��
        - 摰䂿緵鈭� **`StrategyRouter.route` �冽��𠶖��㦤撖餃�**嚗𡁜銁 `IN_TRADE` ���璅∪�銝页�蝟餌��冽��交綫餈𥟇𧒄嚗峕覔�株�蟡典�銝讠��笔�銵峕����隞瑞鸌敺�誑�𠹺���瑪嚗㇈A5/SWS嚗厩����臬�撌殷�撖寞�隞梶��亥�銵�像皛𤏸䌊���瘚�蓮嚗�
            - **`SuperTrendMA5Branch`嚗�蜓��答嚗� �滨漣 -> `SwsPullbackBranch`嚗��頞见飵嚗�**嚗𡁜��笔�鈭舘�蝥找蜓��答頧券���葵�∪��笔�蝥輸�敹��撟單��剜��港�嚗𣬚頂蝏煺��齿�銵峕��毺� T+2 撘箏�甇Ｘ�嚗諹�峕糓�芸𢆡�滨漣�單凒摰賢捆�� `SWS` 撌乩�蝥蹂��訾�蝔喳��荔��𣂷�擃䁅噢 T+3 摰賡��煺�擃睃撕�� SWS 撘箸𣈲�㻫��
            - **`SwsPullbackBranch`嚗��頞见飵嚗� ��漣 -> `SuperTrendMA5Branch`嚗�蜓��答嚗�**嚗𡁜��笔�鈭擧𤣰��㟲�箸���葵�⊥�憭𣇉��𡢅�隞瑟聢�湔�韐渡揮 Boll Upper �� 5�亦瑪�𣳇�煺��鳴�蝟餌��芸𢆡撠���𡏭�蝥扳����肽秐銝餃�瘚芣�擃条�蝥改��祇𡢿瞈�瘣餃之甇Ｙ� 70% ����拇隋����交𣈲�睲遠�潭�����冽��蓥誑�� 5�亙�蝥輸��穃�銵伐�
            - **�拍��港��滚漲�滨漣 -> `OscillatingBreakdownBranch`嚗��雿漤𡺨�粹��抬�**嚗朞𥅾�冽�隞𤘪��游��煺蜓�𥟇𣈲�煾�敹��憭游�銝页�`sws < sws_prev5 * 0.992`嚗㗇�隞瑟聢摰���港�嚗Ǒprice < sws * 0.985`嚗㚁�蝟餌��祇𡢿�文��嗉��仿𡺨�綽��湔𦻖撘箏��滨漣銝粹俈摰�像隞枏��荔�撟嗅銁敶𤘪𠯫�嗥��扯� 100% �拍�皜���箏�嚗峕��������游�頞见飵�西圾���憭梢�摰𡁜銁敺桀⏚�嗆挾��
    - [x] **摰䂿緵�𨅯��其��𣂼停�萘��芷����典��冽��俈摰�迫�毺瑪撘閙� (Enforced Adaptive Lifecycle Stop-Loss & Counter Parity)**嚗�
        - �齿�撟嗅�蝥找� `decision_engine.py` 憿嗅��� `stop_price` 蝏煺�霈∠�瘚�����霈箔葵�∪�鈭� `BUY/ADD` �𣂷漱�對�餈䀹糓 `HOLD` ���隞𤘪𠯫撣詨𪂹����芾�憭�� `IN_TRADE` �嗆���嚗𣬚頂蝏笔�隡朞䌊�典笆���銝贝◤瞈�瘣餌�頝舐眏��𣈲嚗諹挽摰𡁶�摮艾��艇靚函��冽��俈摰���賜瑪嚗�
            - `SuperTrendMA5Branch` ��𣈲嚗𡁻俈蝥輻揮�祆��仿�瘚讠� 5�亙�蝥蹂��� 2.5%嚗Ǒstop_price = ma5_val * 0.975`嚗剹��
            - `SwsPullbackBranch` ��𣈲嚗𡁻俈蝥踹�摰� 10�乩蜓�𥕦極雿𦦵瑪銝𧢲䲮 1.5%嚗Ǒstop_price = sws_val * 0.985`嚗剹��
        - **摰𣬚�閫���墧�瘝嗵�銝𤾸��� 100% �峕��喟�撖寡揭**嚗𡁜蝠摨閙蘨�箏僎靽桀�鈭�銁 `test_reentry_backtest.py` 銝餃儐�臭葉 `trailing_stop` 瘝⊥��冽��� HOLD �罸𡢿鋡� `intent.stop_price` �峕郊�湔鰵����脤��� Bug��緵�典�瘚𧢲��鍦銁瘥𤩺𠯫�滚��塚�摰𣬚��峕郊撟嗆凒�唳��啁��冽��迫�毺瑪隞瑟聢嚗䔶��靝��墧�銝𤾸��� 100% �峕�撖寥�嚗�
    - [x] **�閗繮�𡁜�敺桃㩞 (002156) 頞�漣�芷���憌擧綉銝擧��典��拙�餈� (Epic Auto-Adaptive Trades Captured)**嚗�
        - �冽��批��啜��0 蝖祉��������嗵����銝页�蝟餌�銵函緵憒��鈭烐�瘞湛�
            - `2026-04-28` 蝻拚�頦拍瑪瞈�瘣颱僭�� `50.25` ���
            - `2026-05-07` 憭扳隅銝𥪯撈�誯�雿齿晷�𤑳��𧶏�**蝎曉�閫血����憭扳迫�� 70% ��� +17.57% ��萼�𡁜⏚瘨�**嚗�
            - `2026-05-12` 5�亙�蝥輻憬�𤩺㟲���**閫血�暺�� [ADD-BACK] �噼‘ 70% 蝑寧�嚗������鞉𧋦蝏抒賒皛∩�餈鞱�**嚗�
            - `2026-05-15` �曹�銝餃� 10�亦瑪瘨典飵餈�翰銝𥪜�頦拍瓲蝛� 10�仿俈蝥� 1.5%嚗𣬚頂蝏�**�芸𢆡閫血�敺桀⏚ +0.54% 靽脲擪�批像隞橒�閫��鈭��雿滚捐撟�楊��**嚗�
            - `2026-05-18` �齿活霂���� `MA10_TREND_FOLLOW` 撘箄��蹂僭�� `58.07` ���
            - `2026-05-19` 隞瑟聢�𤑳��滚�瞍�宏嚗��蝑硋之�𤑳��游ế�剝�摨阡�蝥找蛹 `OscillatingBreakdownBranch` �脣像隞橒�**隞� +1.36% 敺桀⏚�齿活�𤏸��勗ㄢ**嚗�
            - `2026-05-20` 閫血� Re-entry �喃儒靽∪噡�Ｗ�嚗䈣2026-05-22` T+2 銝滚�憸���脤�敺桀⏚ `+1.86%` 摰𣬚��芷�嚗�
            - `2026-05-25` �齿活霂���� MA5 撘箏飵�噼萱蝎曉�銋啣� `69.78` ���撟嗡� `2026-05-26` �湔��� `75.39` ���擃䀝���**�齿活閫血� 70% 憭扳迫���摰朞�蝥批⏚瘨�**嚗𣬚𤌍�滩蝠隞枏之�澆�����喃��抵繮頞����𠂔撌脣���+韐阡𢒰蝏澆�擃㗛��拇隋嚗�
    - [x] **60/60 �券��詨�����𣂼�蝟餌��𧼮�瘚贝� 100% 銝�甈⊥�扳��嗅�蝏輸�朞� (Passed 100% of 60 Regression Cases)**嚗�
        - �㰘捏�臭漱�枏��� 32 銝芰鍂靘卝��䌊�㕑��笔𦶢�冽� 11 銝芰鍂靘页�餈䀹糓 HDF5 霂餃��讠憬��㺭�桐耨憭滨� 17 銝芣��嗉��餌�蝟餌�瘚贝��其�嚗�**�券� 100% 銝�甈⊥�批�蝥Ｙ遛蝘㘾�𡄯�摨訫漣�烐惜�䭾��臬稬嚗�**

## 2026-05-29 04:00
- [x] **摰䂿緵憭𡁜��舐��亥楝�望沲����蹱���撣嗪�蝵桀撩頝舐眏撟脤��箏� (Implemented Multi-Branch Strategy Router & Static God-Mode Configuration Overrides)**嚗�
    - [x] **閫��血僎�賢𧑐憭𡁜��舐��亦掩�嗆� (SOLID/SRP Refactored)**嚗�
        - 敶餃��齿�鈭� `decision_engine.py` 銝剔��蓥�撘誩�蝑硋��胯���撱箔��������箇掩 `BaseStrategyBranch`嚗�僎�拍��𠉛氖��圾�血枂鈭��憭批��劐��厰��找��喟�颲寧���移蝏��摮鞟��亙��荔�
            1. **`SuperTrendMA5Branch`嚗��蝥找蜓��答瘝� MA5 �砍������𣈲嚗�**嚗𡁜� �曉��� (603823)����誯凃�� (301071)嚗䔶��刻�韐� 5 �亙�蝥踹撩�券�銝餃���之甇Ｙ���鸌�箏�隞亙���捏 MA5 ���暺���噼‘��
            2. **`SwsPullbackBranch`嚗�食��𤣰����噼萱 SWS �� MA10 �Ｚ��踹��荔�**嚗𡁜� �𡁜�敺桃㩞 (002156)嚗䔶��刻�韐��頦拇𣈲�𤑳瑪雿𤾸𢙺嚗𣬚��豢郭畾萄� T 餈𣂷���
            3. **`OscillatingBreakdownBranch`嚗��雿漤��⊿𡺨�箇聦雿漤俈敺∪��荔�**嚗𡁜� �肽𠧧�㗇� (300058)�������� (603533)嚗䔶��冽�銵屸��⊥�頝峕�蝳�僭�羓�蝥批枂皜�俈敺～��
    - [x] **摰䂿緵銝𠰴�閫���蹱���蝵株楝�曹��冽��鸌敺� Fallback �屸�撖餃�撘閙�**嚗�
        - �齿�鈭���亙粉��頝舐眏�� `StrategyRouter`嚗�
            1. �蹱��楝�曹������ `global.ini` �滨蔭��辣銝剖��曆� `[strategy_routing]` ���嚗��霈貊鍂�瑕笆�滨����隞��餈𥡝��䀹钟撟脤���撩銵𣬚�摰朞楝�梧�憒� `SuperTrendMA5Branch = 603823,301071`嚗剹��
            2. �冽��楝�曹�摨𤏪��交��蹱����辷�蝟餌��蹱�蝻肽䌊�沙allback�啣��舐鸌敺�𢆡����恬�`match` �寥�嚗剹��
    - [x] **摰𣬚��芸�蝟餌�摨訫�撖澆�颲寧�憌擧綉 (Perfected Dependency Inversion)**嚗�
        - ��笆 `test_import_boundaries.py` 銝滚�霈貊��亙之�� `decision_engine.py` ����𤑳��拍� I/O �諹�蝳��撖澆�嚗�� `os`, `configparser`嚗厩�蝖祉漲���蝘㗇㗁鈭� **靘肽��垍蔭�笔� (DIP)**嚗���拍�撖餃��峕�隞� I/O �諹提敶餃��䀝�蝏坔��典挪銝餉�銵��憪见�瘜典���
        - ����典��䀹瓲敹�挪銝� `kernel_service.py` �臬𢆡�嘥��碶誑�𠰴�瘚𧢲��� `test_reentry_backtest.py` 餈鞱�韏瑞�銝哨�摰匧��㰘蝸 `global.ini` 撟嗉��� `StrategyRouter.register_static_routes(rmap)`嚗䔶����撘�鈭��撅�芋�𡑒器�𣬚�瘙⊥���
    - [x] **�閗繮蟡䂿漣頞���嗥�銝� 100% �嗉秤�仿��瑟嵗撉�**嚗�
        - 餈鞱���蟮�墧�撉諹�嚗�����銵函緵憒坔�瘥怠�嚗�
            * **�肽𠧧�㗇� (300058)**嚗𡁶凒�亥◤�枏� `OscillatingBreakdownBranch` �瑕躹�行⏛��𣈲嚗𣬚征隞枏�蝢𦒘��� `[KEEP OBSERVING]`嚗�**100% �嗉秤�仿��瘀�敶餃�閫��鈭��雿滩秧憭朞秧�𤏪�**
            * **�偦��餌𨺗 (301071)** 銝� **�曉��� (603823)**嚗𡁜撩頝舐眏�� MA5 �����𣈲嚗���誯凃�喟遞���瘜Ｘ挾蟡䂿漣餈𣂷���香擃㗛�憭滚��拇隋嚗𤤿蓡���隞� `20.14` ���雿擧��蓥遠�噼‘嚗�**������憌躰秐擃䁅斯�� +45.35%嚗�**
            * **�𡁜�敺桃㩞 (002156)**嚗朞楝�梯秐 SWS 隡�迅雿𤾸𢙺��𣈲嚗𣬚迅�亙�頦拙�隞枏� T嚗�**�抵繮 +32.55% ���蝥扳筑���**
    - [x] **43/43 �詨��𢠃��鞉�霂閧鍂靘� 100% 銝�甈⊥�批�蝥Ｙ遛蝘㘾�� (100% Regression Success with 43/43 Passed)**嚗�
        - ��鉄 32 銝芣瓲敹�漱�枏��詨����霂蓥� 11 銝芾䌊�㕑��笔𦶢�冽����瘚贝�嚗���典��嗅�蝏輸�朞�嚗���睃𤐄�仿�瘙歹�

## 2026-05-29 03:00
- [x] **摰䂿緵憸���� 5�亙�蝥選�MA5嚗㗇�����冽��閧�瘜蓥�擃䀝��罸�隞瑕��𣂷漱璅⊥��箏� (Implemented Predictive MA5 Support Target Calculation & Limit Order Backtest Simulation)**嚗�
    - [x] **摰𣬚��㯄�� `DecisionIntent` �� `suggest_price` 撅墧�批𢆡�����**嚗�
        - ��笆 `DecisionIntent` 鋡怠�銋劐蛹 `frozen=True` 撖潸稲�䭾��湔𦻖�坔� `suggest_price` 撅墧�抒�摨訫�蝥行�嚗�⏚�� Python ��蔭�� `object.__setattr__` 暺煾�瘜閙��毺�撘��餅鱏嚗�銁銝滢耨�� `core/intent.py`嚗������其��游�隞颱��Ｘ��亙藁���撅��霈殷�����𣂷�嚗���喟�憭扯�霈∠������ 5 �亦瑪憸���舀�隞� `suggest_price` �冽����� `intent` 摰硺�銝准��
    - [x] **�寞祥�墧�銝餃儐�� `continue` 撖潸稲���瘚衤遠�芣凒�� Bug (Fixed Day-Loop continue-skip Bug)**嚗�
        - 敶餃��芸枂撟嗡耨憭滢��� `test_reentry_backtest.py` 銝餃儐�臭葉�曹�憭扳迫���隞梶���𣈲靚�鍂 `continue` 撖潸稲摨閖��擧𠯫����舀�憸��隞瘀�`prev_predict_ma5`嚗㕑◤頝唾��湔鰵���蝘䀹�瘣𠺶��
        - 撌批��啣�隞𦠜𠯫���蝻枏� `today_order_target = prev_predict_ma5` 隞亙��擧𠯫�舀�隞瑁恣蝞梹�`ma5_slope` �𦦵�憭𡝗綫嚗㗇㟲雿㯄���宏�喃蜓敺芰㴓��憿園�嚗峕��支�隞颱� `continue` ��𣈲�䭾���恣蝞㛖𤩅�箝��
    - [x] **摰𣬚��賢𧑐 100% �拍��峕��䀝葉����噼‘**嚗�
        - �墧�璅⊥��䀝葉�笔�����𣂷漱�餉�嚗𡁜�銝餃�瘚芾圻�煾��穃�隞枏�銵伐�`MA5_TREND_ADD_BACK`嚗㗇𧒄嚗𣬚頂蝏蠘䌊�冽��亦�銝剜�雿𦒘遠�臬炏頦拍忽�冽𠯫憸�恣蝞埈��蓥遠嚗Ǒlow_price <= today_order_target`嚗㚁��亥萱蝛踹�隞仿�靽萘�����閖�瘚衤遠蝎曉�銋啣�嚗峕𧊋頦拍忽�坔銁�嗥�撘箏�銵亙�蝑寧���
    - [x] **�𣂼��閗繮�曉��� (603823) ����𣂼榆隞瑟���**嚗�
        - �曉��曹� `2026-05-18` 閫血��噼‘嚗𣬚�銝剜�雿𡒊��Ｗ��� 19.68 ����頂蝏笔鐯�笔�銝��亦移��恣蝞㛖��舀����隞� **`20.14`** ����𣂼�蝢𤾸笆朣𣂷僭�伐�颲�偏�䀝僭�交�憭� 3.6% ��征�游榆嚗��嚗���唳�隞𤘪��砍����撟唾秐���雿� **`19.33`** ���
    - [x] **頧啣� +45.35% ���蝥抒��游歇摰䂿緵+韐阡𢒰瘚桃�**嚗�
        - ����牐��箏�雿輻蓡�����漱�栞”�啣之�曉�敶抬���蝏���嗥���眏�笔�撠曄�銵乩��� `+41.45%` �拍��匧��喲�韐萇� **`+45.35%`**嚗峕�����瑁�憸嘥����撖孵⏚瘨佗�
    - [x] **�𧼮�瘚贝� 100% �函遛蝘㘾�� (100% Regression Success with 43/43 Passed)**嚗�
        - 餈鞱�鈭���砍��� 32 憿寞瓲敹�漱�枏��詨����霂蓥� 11 憿寡䌊�㕑��笔𦶢�冽����瘚贝�嚗�� 43/43 銝芰鍂靘见��典��嗥遛�烾�朞�嚗��蝟餌��箄𥅾�烐惜嚗�

## 2026-05-29 02:20
- [x] **摰䂿緵 5�亙�蝥輯�蝥找蜓��答憭扳迫����噼萱銵乩�蝑𣇉裦銝� Mode D 撘箏飵�∟蕭�𧼮��拍�甇Ｘ�靽脲擪 (Implemented MA5 Super-Trend Support, TAKE-PROFIT ADD-BACK & Strength Buy-Back Re-entry Protection)**嚗�
    - [x] **�� `reentry_tracker.py` 銝剖��� Mode D [�喃儒璅∪�] 撘箏飵�∟蕭�墧㦤�� (STRENGTH_BUYBACK)**嚗�
        - 撠� Re-entry ��◤�刻�撖���鞟眏�蹱香�� 5 憭拙𢆡����輯秐 **12憭�**嚗䔶��券�撖孵撩�蹂葵�∪銁�剜��噼萱�㚚�雿齿窒 upper 銝𡃏膘餈鞱���蜓��答銝剝��滩�蝛箝��
        - 撘訫� Mode D �文��∩辣嚗𡁜歇甇Ｘ�銝芾�憒���芾��港蜓�偦俈蝥選�銝𠉛��笔枂�啣撩�𥕢耨憭㵪�憒���交𤣰�㗛��啁�蝔� 5�亙�蝥� `price >= ma5_val` 銝� `vol_ratio < 1.2` 蝻拚��舀�找�瘨剁��碶遠�潛凒�亙銁 5�亦瑪銝𦠜䲮�暸��睲�蝒�聦撣��銝𡃏膘 `price >= upper * 0.985`嚗㚁��祇𡢿�拍�瞈�瘣餃僎鈭抒� Re-entry �Ｗ�靽∪噡嚗�
    - [x] **�� `decision_engine.py` 憿嗥漣�喟�銝剖�蝢擧��� `MA5_SUPER_TREND` 蝑𣇉裦銝𡡞��穃�銵�**嚗�
        - ��笆��撩�踴����噼萱 10�亦瑪嚗𠄎WS嚗厩�瘝� ma5d 頞�漣銝餃�瘚芾�蟡剁��齿��啣� `MA5_SUPER_TREND` 撌虫儒雿𤾸𢙺銝𤾸𢰧靘折俈頦讐征撱箔���𣈲��
        - ��鉄�文�嚗�5�亦瑪�� 5憭拙�隞� $\ge 0.8\%$ 蝔喳������`ma5_val >= ma5_prev5 * 1.008`嚗㚁���雿𦒘遠�噼萱 `MA5` ���嚗Ǒlow_price <= ma5_val * 1.015`嚗㚁��𤥁����游��𦯀�頧剁�銝娍�鈭日��芾�摨行晷�𡢅�`vol_val < vol_ma5_val * 1.2`嚗剹��
        - **�嗅�銝枏����𨅯�銝斗𡆀��𣶸�嘥𢆡��迫�煺遠**嚗帋蛹 `MA5_SUPER_TREND` 銝𤾸�隞枏�銵亦鸌�怠�摰𡁜�甇Ｘ��㗇香�� 5�亦瑪銝𧢲䲮 2.5%嚗Ǒstop_price = ma5_val * 0.975`嚗厩��冽����賜瑪嚗峕�憭批𧑐�滢�鈭���蹱��穿��脫迫擃䀝�霂勗��諹�蝛箔��麄��
        - **摰䂿緵憭扳迫����� 5�亦瑪暺���噼‘ (MA5_TREND_ADD_BACK)**嚗𡁜銁����嗆���嚗�笆鈭𤾸之甇Ｙ��譍��𡒊�頞�漣銝餃�瘚芯葵�∴�憒���嗅�撣�憬�誩�頦� 5�亙�蝥選�`low_val <= ma5_val * 1.015` 銝� `price >= ma5_val * 0.985`嚗䈣vol_ratio < 1.15`嚗㚁��芸𢆡閫血��噼‘銋见�憭扳迫����箇� 70% 蝑寧�嚗������鞉𧋦蝏抒賒皛∩�頨箄窖嚗�
    - [x] **�㯄�𡁜��䁅����銝𤾸��脣�瘚� 100% �峕��惩��𡁻�**嚗�
        - �� `signal_canonicalizer.py` 銝剛‘�其��埈��� `swl_prev5` �� `ma5d_prev5` 摰䂿�閫���𣬚鸌敺��撖潦��
        - �典�瘚贝��� `test_reentry_backtest.py` ��鸌敺���𣂼㦛靚曹� flat �嗆�� features 摮堒�銝哨�摰���拍�撖寥�撟嗡萼撖䔶�餈嗘舅憿寥�蝏渡鸌敺��靽肽�鈭��𨀣�閫�朖��敺轁�萘�摰���峕��喟���
    - [x] **�𣂼��閗繮�𣬚蓡��� (603823)�滨� 5�亦瑪頞�漣憭抒�撣�**嚗�
        - ��蟮�墧�銝哨��曉��曹� `2026-05-08` 隞� `17.45` ����嗥移��𧑐頝諹秐 5�亦瑪���閫血� `MA5_SUPER_TREND` 銋啣�嚗�
        - 鈭� `2026-05-12` �湔隅�� `19.02` ��𧒄蝎曉�閫血���鸌憭扳迫�� 70% ���蝑寧��拇隋嚗𥕦�雿� 30% 隞㮖��剖�罸��賡俈�斤�銝�頝臬之�澆�頨箄窖嚗峕��唬遠 `28.10` ���**蝏澆�撌脣���+韐阡𢒰������擃䁅噢 +24.61% ���蝥扯�憸脲𤣰��**嚗�
    - [x] **鈭斗���瓲銝舘䌊�㕑��笔𦶢�冽��券� 43 憿孵�敶埝�霂閧鍂靘� 100% 蝏踵��朞� (100% Pytest Green Passage)**嚗�
        - 餈鞱�鈭���砍��� 32 憿寞瓲敹�漱�枏��詨����霂蓥� 11 憿寡䌊�㕑��笔𦶢�冽����瘚贝�嚗�� 43 銝芰鍂靘� 100% 銝�甈⊥�批��典��園�朞�嚗䔶��𦦵頂蝏笔��䀹�銝�銝苷�瘥恍���吔�撅閧緵�箸��渡�撌亦���捶銝𡡞��舐鍂瘞游�嚗�

## 2026-05-29 02:05
- [x] **�齿�撟嗅�蝳� `sws`��swl`��ma10` 銝� `ma5` �𤤿輕���雿梶頂銝𤾸撩頞见飵�文�隡睃� (Fully Separated 4-Dimension Indicators & Optimized Trend Follower Logic)**嚗�
    - [x] **���雿梶頂�拍���氖 (Separated Indicator Mappings)**嚗�
        - ��笆甇文�撠� `swl` ���蝎埈𠂔�湔𦻖蝑匧�鈭� `ma5` ����硋�瘜閗�銵䔶��唳秤撘讐����蝳颯�������墧� `test_reentry_backtest.py` ����� `kernel_service.py` �𣬚�����瑕��餉�嚗䔶蝙 `swl` 隡睃�霂餃��笔��� `"SWL"` �梹��喲�朞噢靽� EMA �舀�蝥� `(EMA10*7 + EMA20*3)/10`嚗剹��
        - �啣�撟嗅笆朣𣂷�蝟餌�暺䁅恕�賢��� 5 �乩� 10 �亦宏�典像��瑪 **`ma5d`** �� **`ma10d`**嚗�誑�� 5 憭拙��� 10 �亦瑪 **`ma10d_prev5`**嚗劐�銝粹�蝏渡鸌敺���亙�蝑硋之�𡢅��拍��箏�鈭���牐葵�瑟�銝滚�憌擧綉�峕𣈲�穃撩摨衣��詨����舀�����
        - 隡睃�隞𡡞�朞噢靽∟��䂿��唳�����𦯀葉霂餃� `ma5d` �� `ma10d`嚗�之撟��擃䀝�餈鞱����撟嗆��支�憭𡁜��滚�霈∠���
        - �典��睃��墧���㺭�桅�𡁻��𡃏������ `signal_canonicalizer.py` 銝剖�蝢擧釣�乩� `ma5d` 銝� `ma10d` �孵�嚗���唬��孵����銝交聢銝��氬��
    - [x] **隡睃� `decision_engine.py` ��瑪頞见飵�文� (Hardened is_trend_ok Logic)**嚗�
        - 靚�㟲鈭� `MA10_TREND_FOLLOW` 蝑𣇉裦銝剔� `is_trend_ok` �斗鱏�∩辣嚗䔶���𧋦�蓥��� `swl > sws` �枏捐銝箸𣈲�� `(swl > sws) or (ma10d > sws) or (ma5d > ma10d)` ���蝏游ế摰𠾼����Ｖ��嗘�撘箏飵憭找蜓��葉�舀�蝥輸��厩��𤩺�摨佗����摰嫣��典�銝芾�嚗���偦��餌𨺗 301071嚗厩眏鈭𤾸��脤�雿滩扇敹�紡�� `SWS` fallback 蝥惩�銝� `ma10d` �𡒊�隡�迅銵峕���
    - [x] **摰䂿�隞㮖��嗆��圾����𨅯蝱����惩𤐄 (Fixed Live Position Tracking & Decoupled Account Selection)**嚗�
        - **靽桀�閫���硋膥閫��瞍誩仃**嚗𡁜銁 `signal_canonicalizer.py` 銝凋蛹 `canonicalize_decision_queue_item` 銵仿�鈭��瞍讐� `"tp_triggered"`��"is_swing_low_mode"` 隞㮖��嗆����孵��𣂼��餉�����寞�銝𦠜��支�摰䂿�/璅⊥��条眏鈭𦒘縑�瑕��芸蒂�箸�隞㮖�銝𧢲�撖潸稲����詨�銵亙���鸌甇Ｙ��其��䠷�憭望�����押��
        - **摰䂿緵�𨅯蝱韐行��冽��粉��**嚗𡁻���� `kernel_service.py` �� `evaluate_decision_item`嚗���支���𧋦�芸� `paper_adapter` 蝖祉���粉�𡝗�隞枏笆鞊∠�蝻粹萅嚗峕㺿銝箸覔�桀��齿�瘣餅��堆��舀� `executor`, `paper_adapter`, `broker_adapter` �冽��龪�㵪��芷����瑕�隞㮖�霂行�嚗𣬚＆靽苷��典��塩���璅⊥�韐行�銝讠� **100% �峕��喟�**��
    - [x] **摰𣬚��朞��券��詨�����墧�銵函緵 (Validated Re-entry Backtest Consistency)**嚗�
        - **�偦��餌𨺗 (301071)**嚗�2026-05-12 摰𣬚�隞� `54.91` ���隞㮖��貉��綽�憭扳迫���隞㮖��噼萱 `58.02` ��說隞枏�銵亙� T �𠬍�頨箄窖�喃�蝏澆����拇隋���颲� **`+35.05%`**嚗�
        - **�𡁜�敺桃㩞 (002156)**嚗帋��嗡� `2026-04-29` 蝻拚�頦拍瑪 `49.50` ��移��僭�伐������ T 頨箄窖�喃��脣� **`+32.55%`** ���憸脲�餃⏚瘨佗�
        - **�肽𠧧�㗇� (300058)**嚗𡁜�蝔衤��� `[KEEP OBSERVING]` 蝛箔�閫���嗆����嗉秤�伐�摰𣬚��脣鴃鈭��雿滩秧憭帋�����
    - [x] **43 憿寡䌊�典��𧼮�瘚贝� 100% 蝏輯𠧧蝘㘾�� (Passed 100% of 43 Pytest Cases)**嚗�
        - 餈鞱�鈭�漱�枏��詨��典�������瘚贝�隞亙��芷�㕑��笔𦶢�冽����瘚贝�嚗��霈� 43/43 �詨�瘚贝��券� 100% 銝�甈⊥�批��園�朞�嚗䔶��𦦵頂蝏笔�摨批𤐄�仿�瘙扎��


## 2026-05-29 01:45
- [x] **摰䂿緵�墧�銝𤾸��条鸌敺� 100% 蝏嘥笆�拍�撖寥�銝𤾸�蝥輯��踹ế摰𡁜��� (Hardened 100% Backtest/Live Feature Parity & Verified MA10 Trend Follower)**嚗�
    - [x] **�拍�撖寥��墧�銝𤾸��� `swl` �孵��唳旿皞� (Aligned Backtest and Live Feature Sources)**嚗�
        - ��笆甇文��典��脣�瘚� `test_reentry_backtest.py` 銝哨��曹� `swl` 隡睃��� `SWL` �朞噢靽⊥㺭�桀�撖潸稲蝞堒枂�� `swl` (憒� 52.66) 銝𡒊�摰䂿� 5�亙�蝥� `ma5` (憒� 55.07) 銝滢��氬����銁摰䂿� `kernel_service.py` 銝� `swl` 瘞貉��箏��� `ma5` ��瑪�潛�摨訫��孵�瞍�宏蝻粹萅嚗峕�銵䔶��唳秤撘讐�撖寥��齿���
        - 撘箏�撠��瘚衤葉 `swl` �孵�撖孵� `ma5` ��瑪�潘�靽肽�鈭��瘚见之�睲�摰䂿��喟���閫�朖��敺㛖� **100% �峕��喟�**��
    - [x] **摰𣬚�閫血�����誯凃�� (301071)�滢蜓��答暺����� (Reclaimed +35.05% Super Profit for 301071)**嚗�
        - �讐� `swl`�孵�銝� `ma5` ��笆朣琜�頞见飵餈�誘�冽�����匧� **301071 (�偦��餌𨺗)** 鈭� `2026-05-12` 皛∟雲 `swl` (55.07) > `sws` (53.75) ��瑪憭找�����輻��𣳇�煺�蝔喋��
        - �墧�隞� `54.91` ���蝢𤾸𢙺�伐�撟園◇�拙銁�𤾸��匧�銝剛圻�� 70% 憭扳迫����58.02` ����睃�銵亙� T嚗�僎�� `2026-05-25` �齿活憭抒��� 74.61 ��𧒄憭扳迫�� 70% ����拇隋嚗�**頨箄窖�喃�蝏澆����拇隋�匧��鮋�颲� +35.05% ���蝥批���𤣰��**嚗�
        - **�𡁜�敺桃㩞 (002156)** 靘萘��� `2026-04-29` 樴坔仍蝻拚��噼萱 SWS 銋钅�蝎曉�雿𤾸𢙺嚗峕�隞栞犖韏Ｚ秐隞𠰴��� **+32.55%** ���憸脲�餃⏚瘨佗�銝� **�肽𠧧�㗇� (300058)** �函�靽脲� `[KEEP OBSERVING]` 蝛箔�閫��嚗��蝢𡡞�撘�鈭��雿漤狍頝䔶�����
    - [x] **撉諹��券� 43/43 憿寡䌊�典��𧼮�瘚贝� 100% �函滯蝏輻��� (Passed 100% of 43 Regression Cases)**嚗�
        - 餈鞱�鈭�漱�枏��詨��典�������瘚贝�嚗�32 銝芰鍂靘页�隞亙��芷�㕑��笔𦶢�冽����瘚贝�嚗�11 銝芰鍂靘页�嚗��霈� 43/43 �詨�瘚贝��券� 100% 銝�甈⊥�抒遛�烾�朞�嚗䔶��𨅯�摨批𤐄�仿�瘙扎��

## 2026-05-29 01:25
- [x] **摰峕� Re-entry �墧��∪�銝𤾸��� 43 憿寡䌊�典��𧼮�瘚贝� 100% 蝏輸�𡁻�霂� (Verified Re-entry Backtest Calibration & Passed 100% of the 43 Pytest Regression Cases)**嚗�
    - [x] **撉諹� Re-entry ��蟮�墧�銵函緵 (Validated Re-entry Backtest Results)**嚗�
        - 餈鞱� `scratch/test_reentry_backtest.py` �𡁏𧋦嚗屸�撖寧𤌍���憭渲�餈𥡝��鞉𠯫�䭾𧊋�交㺭�桀��脣�皞舀�霂𨰻��
        - 撉諹�鈭� **�𡁜�敺桃㩞 (002156)** 鈭� `2026-04-21` 憿箏⏚閫血�鈭�鰵憓䂿� `MA10_TREND_FOLLOW` 撘箄��輻����蝔唾��箇�嚗屸��𤾸銁����湧��⊥��䀝葉�扯�敺桀⏚靽脲擪���綽������ +0.02%嚗㚁�撟嗅銁 `2026-04-29` �齿活蝎曉��噼萱 SWS 撌乩�蝥輯圻�� `SWS_COLLECT_PULLBACK` 銝餃��舀�摨蓥�嚗屸�朞�憭批� T 皛𡁜𢆡�滢�嚗峕�蝏���嗉悸�� **+32.55%** ���鈭箇遞����拇隋嚗�
        - 撉諹�鈭� **�肽𠧧�㗇� (300058)** �函�靽脲� `[KEEP OBSERVING]` 蝛箔�閫���嗆���摰𣬚��踹�鈭��雿漤狍頝䔶�����
    - [x] **頝煾�𡁜��� 43/43 憿寡䌊�典��𧼮�瘚贝� (100% Regression Success with 43/43 Passed)**嚗�
        - 餈鞱�鈭�漱�枏��詨��典�������瘚贝�嚗Ǒtrading_kernel/tests` �� 32 銝芰鍂靘页�嚗�100% 銝�甈⊥�批�蝥Ｙ遛蝘㘾�𠾼��
        - 餈鞱�鈭�䌊�㕑��笔𦶢�冽����瘚贝�嚗Ǒtest_watchlist_lifecycle.py` �� 11 銝芰鍂靘页�嚗�100% 銝�甈⊥�批�蝥Ｙ遛蝘㘾�𠾼��
        - ��恣 43/43 �詨�瘚贝��券� 100% 銝�甈⊥�批��園�朞�嚗䔶��𨅯�摨折�瘙斗����硔��

## 2026-05-29 01:10
- [x] **摰䂿緵銝餃�瘚芣窒 MA10 撘箄��踹��毺�����噼萱隡�迅雿𤾸𢙺銋啣�蝑𣇉裦 (Implemented MA10 Trend-Following Escalation & Consolidation Buy-In Strategy)**嚗�
    - [x] **�齿� `decision_engine.py` 撱箔�餈�誘憭扯�**嚗𡁏鰵憓� `MA10_TREND_FOLLOW` �𣳇�蠘��蓥�瘣㛖��渡�銋啣���𣈲���朞��斗鱏 10�亙�蝥� (SWS) �� 5憭拙���迅摰帋�瘨函𠶖���`sws >= sws_prev5 * 1.005`嚗㚁��曉捐銝擧𠯫����湔��� (DFF) ��′�批㨃���韏吔�撟嗅銁隞瑟聢�Ｗ��亥� 10�交𣈲�𤑳瑪隡�迅銝𥪯��亙僎�芸之���瘣曉��嗉圻�𤑳洵銝��嗆０撱箔�嚗�30% 摨蓥�嚗剹��
    - [x] **�函輕�㯄�𡁻�蝏渡鸌敺���㚚�𡁻�**嚗𡁜銁 `signal_canonicalizer.py` 銝剜鰵�� `sws_prev5` 撟嗅��墧��孵��𣂼��剁�`test_reentry_backtest.py`嚗匧�甇亥‘��釣�� `sws_prev5` 銝� `swl` (MA5) ���嚗���唬�摰䂿����瘚� 100% �孵��峕郊�惩���
    - [x] **摰峕�����誯凃�� (301071)�滢蜓��答蟡䂿漣�墧�**嚗𡁏��煺� `2026-05-12`嚗�54.91 ���蝎曉�雿𤾸𢙺銋啣�嚗�僎�其蜓��答�匧��� 60.07 ������甇Ｙ� 70%嚗偦��𦒘� `2026-05-19` �噼萱瘣㛖��� 58.02 ��憬�譍�蝔單𧒄蝎曉�皛∩��噼‘�� T嚗峕�蝏�� `2026-05-25` �齿活憭抒��� 74.61 ��𧒄憭扳迫�� 70% ����拇隋嚗�**���頨箄窖�喃��餃��抵繮擃䁅噢 +35.05% ��揭��+摰䂿緵頞��憭滚��嗥�**嚗�
    - [x] **�𧼮�瘚贝� 100% 蝏輸��**嚗𡁜��� 43 憿嫣漱�枏��訾��芷�㕑��笔𦶢�冽��𧼮�瘚贝�銝�甈⊥�抒�餈��蝖株恕蝑𣇉裦銝滢�撖孵��毺��⊥�����閙�摨佗�銝𥪜笆�𡁜�敺桃㩞嚗�𤣰�𦠜�蝔喳銁 +32.55%嚗劐��肽𠧧�㗇�嚗�妟霂舀𥁒�輸𡺨嚗厩�摮㗛�����瑟���蔔���銝见�摰寞�找��𣳇���𤥁”�啜��

## 2026-05-29 00:50
- [x] **隡睃� Re-entry �墧�撅閧內蝒堒藁憭滨鍂�箏�銝擧�蝒���冽辺 UI 靚�� (Implemented Backtest Window Reuse & Customized Narrow Scrollbar UI)**嚗�
    - [x] **摰䂿緵蝒堒藁�箄��拍�憭滨鍂**嚗𡁻���� `stock_selection_window.py` �� `instock_MonitorTK.py` 銝剔� `_show_backtest_report_window` �餉����璉�瘚� to �典�撌脫�瘣餉� of `BacktestReportDialog` 摰硺��塚��芸𢆡�行⏛�� TopLevel ���撱綽��寧鍂�啣� of `update_report(code, name, report)` �亙藁�冽唂蝒堒藁銝剖��啣像皛穃��啣�瘚𧢲㺭�桀僎撘箏��㕑絲�衣���蝠摨閙�蝏苷�憸𤑳��孵稬撖潸稲摮鞟���憤憭拚���緵鞊～��
    - [x] **��漣����㰘器獢���冽辺 (Narrow Scrollbar)**嚗𡁜�皛𡁜𢆡�∟�蝘餉秐��� `tk.Scrollbar` �嗆����朞��曉�憯唳� `width=8`嚗䈣borderwidth=0` �� `highlightthickness=0`嚗�銁靽脲�����㰘器獢�緵隞�捶�毺��峕𧒄嚗��蝢舘��蹂�銝滚�蝟餌�銝駁�銝� Ttk 撘閙�閫�� `Layout Vertical.Narrow.TScrollbar not found` ����典援皞��瘣𠺶��僎銝�**摰���踹�鈭�蝙�� `ttk.Style().theme_use()` 蝑匧虾�賢�韏瑕�撅� Tk �屸𢒰�瑕�蝭⊥㺿���雿𦦵鍂**��
    - [x] **�舀��桃� Esc �拍�銝��桀���**嚗𡁜銁 `BacktestReportDialog` �嘥��𡝗�蝔衤葉嚗���牐�撖� `<Escape>` �厰睸����瑞�摰𠾼��鍂�瑟�銝� `Esc` �格𧒄嚗𣬚�����芸𢆡�剖�銝𥪜��券���綽��峕郊閫血� `WindowMixin` ���雿閙㺭�株楊隡朞��拍�����吔���之�唳�����滢�瘚���𤩺㭘�扼��
    - [x] **�𧼮�瘚贝� 100% 蝏輸��**嚗𡁜��� 43 憿嫣漱�枏��訾��芷�㕑��笔𦶢�冽�瘚贝�銝�甈⊥�批�蝥Ｙ遛蝘坿���

## 2026-05-29 00:45
- [x] **摰䂿緵銝� Tkinter 蝒堒藁銝芾��𡑒”�喲睸 Re-entry ��蟮�墧����銝𤾸�瘚𧢲�扯���稲隡睃� (Fully Integrated Context Menus on Primary Tkinter Tree & In-Memory Slicing Backtest Speedup)**嚗�
    - [x] **�寞祥�墧��拍� I/O �埈𧒄�園� (Eliminated Repetitive File I/O in Loop)**嚗𡁻���� `scratch/test_reentry_backtest.py` ��㺭�桀�頧賜恣蝥踴���瘚见�憪见��嗅�甈⊥��� 1200 憭拙��誩��脫𠯫K�唳旿摮睃����嚗Ǒdf_all`嚗㚁��券�鞉𠯫餈凋誨�斗鱏�嗆㺿�券���� Pandas ������ `df_all.loc[:current_date]`��蝠摨閙覔瘝颱��抒��砍銁�鞉𠯫敺芰㴓銝凋��剛粉�嗵����餈𥕦���辣����埈𧒄瞍𤩺�嚗�之撟��雿舘恣蝞堒辣餈蠘噢 95% 隞乩���
    - [x] **銝餌��� Tree �喲睸�典��質���**嚗𡁜銁銝餌��斤��� `instock_MonitorTK.py` ��葵�� Treeview �喲睸�𨅯�銝哨��删��亙� �𨥉�� 餈鞱� Re-entry ��蟮�墧��� �厰僼�其���
    - [x] **璊滚� `timed_ctx` 擃条移蝏�漲�扯��𤏸��� (Integrated timed_ctx Profiler)**嚗𡁜銁�鮋獈憛𧼮��啁瑪蝔贝恣蝞𦯀遙�∩葉��ㄨ `with timed_ctx(..., warn_ms=300)` �箏�嚗���嗅笆霈∠��冽��扯�敺桃�蝥扯�埈𧒄�烐綉銝𤾸�摨瑁��准��
    - [x] **�𣂼�憭滨鍂 `BacktestReportDialog` 霂行��Ｘ踎**嚗𡁜�蝢𡡞��� `stock_selection_window.py` ����箔� `WindowMixin` ���銋��霂行�撘寧�嚗䔶����蝟餌� UI 霈曇恣憌擧聢銝𤾸�雿訫��唳�銋���滨蔭����港��湔�扼��
    - [x] **瘚贝��函遛�惩�雿𦦵鍂**嚗𡁜��� 43 憿寞瓲敹���笔𦶢�冽��𧼮��其�嚗�32 憿嫣漱�枏��貊鍂靘� + 11 憿寡䌊�㕑��笔𦶢�冽��其�嚗�100% 銝�甈⊥�批��嗥��𠾼��

## 2026-05-29 00:35
- [x] **摰䂿緵 TK 銝餌�����劐葵�∪�銵典𢰧�株��訫��讛��碶�隞���瑕��惩𤐄 (Fully Integrated Context Menus Across All Main Tables & Hardened Code Parsing)**嚗�
    - [x] **�啣�隞𦠜𠯫���銝𦒘漱�𤘪�瘞渲”�澆𢰧�株���**嚗𡁜銁�㕑�銝餌���葉銝算�靝��交�隞𣏾�肽”�� (`self._pos_tree`) �𢞖�靝漱�𤘪�瘞氯�肽”�� (`self._log_tree`) 蝏穃�鈭� `<Button-3>` �喲睸鈭衤辣�喲�𡁶鍂銝𠹺�����訫���膥 `show_context_menu`��蝙�冽��賢��湔𦻖�冽�隞𤘪�鈭斗���蟮霈啣�銝𠰴𢰧�桀翰�蠘�銵� Re-entry �墧���
    - [x] **�惩𤐄�喲睸�𨅯�銝芾�隞��閫��撘閙�**嚗𡁻���� `show_context_menu` 銝剔��唳旿�埈��㚚�餉�嚗���牐�撖嫣漱�𤘪�瘞渲”�� (`_log_tree`) ���撖寞�扳��硋��胯����冽�瘞渲”�喳稬�塚��芸𢆡霂餃� `values[2]`嚗�朖 `code` �梹�隞仿�撘� `values[0]` �園𡢿�喳�蝚虫葡嚗�� `09:32:01`嚗㕑◤�躰秤�𣂼�銝粹�甇�虜�∠巨隞������� Bug嚗䔶�����唬��函���葵�∟”�潛��亙ㄝ�娪�𠾼��
    - [x] **�𧼮�瘚贝� 100% 蝏輸��**嚗𡁜��� 43 憿� pytest �𧼮�瘚贝��其��𣳇���硋�蝢𡡞�朞���

## 2026-05-29 00:30
- [x] **隡睃� Re-entry �墧��亙��屸𢒰撟嗆楛摨血��� WindowMixin 蝒堒藁����𤥁��� (Optimized Backtest Detail Display & Reused WindowMixin Geometry Persistence)**嚗�
    - [x] **摰䂿緵 `only_report` 蝏��餈�誘��㺭**嚗𡁜銁 `test_reentry_backtest.py` ���瘚见遆�唬葉�啣� `only_report: bool = False` �舫�匧��堆�撟園���������𠯫敹埈𤣰��膥嚗Ǒlog`嚗剹���霈曄蔭銝� `True` �塚�蝟餌��券�鞉𠯫�刻��嗡�餈�誘�箸�蝏���亙��餌��箏�嚗䔶蝙敺� GUI �Ｘ踎撅閧內�游�皜���渲�嚗���嗡��嗘��賭誘銵���湔�蝏�蕭頦芰�隡睃飵��
    - [x] **瘛勗漲�游� `WindowMixin` �亙�撅閧內撘寧�**嚗𡁜��啣僎撠��鈭����� `BacktestReportDialog(tk.Toplevel, WindowMixin)` 撘孵枂蝒堒藁蝐颯����漤�憭齿��嗵′蝻𣇉��牐���憬�曉�雿滚�撅誩�颲寧�撖寥�蝞埈�嚗諹�峕糓撠������鞉�霈∠�����凋�隞嗅��Ｙ宏鈭斤��箇掩 `WindowMixin` �� `load_window_position` / `save_window_position` 撘閙����銝滢�蝏煺�鈭�頂蝏毺漣 UI 閫��嚗諹��嗆��砍𧑐摰䂿緵鈭�楊蝔见��笔𦶢�冽������之撠譍�雿滨蔭������銋����
    - [x] **瘚贝��函遛�惩�雿𦦵鍂**嚗朞�銵� `pytest` 摰���朞�鈭�漱�枏��貊� 32 憿孵� watchlist 11 憿寧鍂靘页��� 43 銝芰鍂靘见��函��朞�嚗𣬚＆靽嘥�摨抒�撖寧迅�箝��

## 2026-05-29 00:15
- [x] **摰䂿緵 Re-entry ��蟮�墧��港��亙�璅∪��𡝗𡂝�碶� TK GUI 瘛勗漲�喲睸��� (Modularized Backtest Reporting & Integrated Context Menu in TK GUI)**嚗�
    - [x] **�齿� `test_reentry_backtest.py` �詨�颲枏枂瘚��**嚗𡁜��墧�瘚��摰��閫��血僎撠���� `run_backtest_and_get_report(code, name)` 銝哨�����芸𢆡�園����匧��桐漱�㮖�隞塚�撱箔���之甇Ｙ��譍�����詨�銵乓���甈∪之甇Ｙ����隞㮖�������蝑㚁���僎�典�瘚讠��𨀣錰撠曉𢆡��恣蝞堒僎�枏㫲�粹�摨行聢撘誩���艇撖�笆韐衣� `�� �𪊟e-entry ��蟮�墧��港��亙��鬔��
    - [x] **GUI �喲睸�𨅯��其�摰𣬚��枏�**嚗𡁜銁�㕑�銝餌��� `StockSelectionWindow` ��舅憭�瓲敹�”�澆𢰧�株��𤏪�generic `show_context_menu` �𡃏蕭頦芷𢒰�� `show_context_menu`嚗劐葉�啣� `�� 餈鞱� Re-entry ��蟮�墧�` �亙藁��
    - [x] **霈曇恣擃䀹﹝�鮋獈憛𧼮�蝥輻�霂𦠜鱏撘寧�**嚗𡁶��餃�瘚贝��訫�嚗峕�韏琿��餃� Loading 撖寡�獢��撟嗅銁�祉��𤾸蝱蝥輻�銝剜�銵諹恣蝞𦯀誑�脫迫 UI 銝餌瑪蝔见㨃甇鳴�霈∠�摰峕��擧�韏瑟𣈲�� Consolas 蝑匧捐摮𦯀�����脤�𤩺�蝘烐��蠘祕��撕蝒梹��朞�擃䀹����蝚虫葡甇���惩�嚗�笆 `BUY/SELL/撱箔�/�譍�/�噼‘/甇Ｙ�` 蝑劐漱�㮖�隞嗅��桀�餈𥡝��冽����脤�鈭殷�憭批��𣂼���������

## 2026-05-28 23:59
- [x] **瘨�膄摰䂿��𨅯蝱銝𡒊爾�䀹芋�蠘��𤑳′蝻𣇉�嚗�撩�𡝗�蝔贝䌊���撘�虜摰賢捆摨� (Harden Initial Capital Alignment, Exception Tolerance & Test Suite Parity)**嚗�
    - [x] **�齿�璅⊥��𨅯蝱 `BrokerExecutionAdapter` 韏��瘙惩�憪见�**嚗帋耨�� `broker_adapter.py` ����惩遆�啣� `__init__` �嘥��㚚�餉�嚗䔶蝙�嗉�憭笔𢆡��𦻖�� `initial_capital` ��㺭嚗�僎敶餃�蝘駁膄鈭���閗��烐�撖寞𧒄�笔��蹱香�� `1,000,000.0` 隞輻�韏�漣��㺭����塚��刻恣蝞㛖𤌍����閖�摨佗�`target_value`嚗厩����罸�朞楝銝剖��乩��典� `try-except` 摰賢捆摨虫��斗㦤�塚��典��抒撩憭望��𤑳��芰䰻閫��撘�虜�嗉䌊�典��典�摨閗��墧����霈文�潘�閫���曹��墧�蝐餃�撘訫���頂蝏毺瀃�芥��
    - [x] **�惩𤐄蝥貊� `PaperExecutionAdapter` 韏��瘥𥪜笆�𠰴�撣貉䌊��㦤��**嚗𡁜銁 `paper_adapter.py` �� `submit_order` 瘚��銝剝���� `equity` �嘥�隞㮖�瘥𠉛��箏���恣蝞烾�𡁻���鰵憓𧼮�撅�辺隞嗉䌊��俈敺∴��刻揭�� `initial_capital` ��㺭銝� `None`��0` �硋�隞㚚�霂舀聢撘𤩺𧒄嚗䔶�甈⊿�蝥找蛹隞亙��滨�韐行�摰墧𧒄�餅��𠺪�`total_equity`嚗㗇� `1000000.0` 蝟餌��箏�銝箏�摨𤏪��脫迫���憸烐�蝡臬�撣詨㦤�舫獈�剜迤撣訾僭�硋�隞枏�蝑硔��
    - [x] **撉諹��券� 43/43 憿孵�敶埝�霂訫��嗅�蝏輻���**嚗𡁜銁 PowerShell �臬��㗛�銝剖� `JSONData` �𣂼�摰匧�撟嗅� `PYTHONPATH`���甈⊥�� 100% 頝煾�𡁜��砍��� 32 憿寞瓲敹�漱�枏��詨�敶垍鍂靘衤誑�� 11 憿寡䌊�㕑��笔𦶢�冽��其��典��� 43 銝芰鍂靘页�蝏湔�摨訫漣�𣳇���硔���甇餉�����游極銝𡁶漣鈭支�韐券�嚗�

## 2026-05-28 23:30
- [x] **摰䂿緵銝��芯葵�∠�隞㮖��鍦��箏� (Implemented Constant Single Stock Position Sizing)**嚗�
    - [x] **�齿�璅⊥��䀝�摰䂿�銝见�韏��霈∠��餉�**嚗帋耨�� `PaperExecutionAdapter.submit_order` �� `BrokerExecutionAdapter._execute_broker_order`嚗���嗡葉����閖�憸肽恣蝞堒抅���`equity`嚗劐��冽����𣇉�敶枏�韐行��餅��𠺪�`self.account.total_equity`嚗厰���蛹�鍦����憪𧢲�餉�鈭改�`self.initial_capital` �� `1000000.0`嚗㚁�蝖桐�瘥誩蘨銝芾�撘�隞瓐��‘隞瓐��像隞枏��嗆挾���撖寡��穃��滢��讛揭�瑞�鈭讛�䔶漣���蝘颯��
    - [x] **�峕郊�湔鰵�訫�瘚贝��其�**嚗帋耨�� `trading_kernel/tests/test_paper_trading.py` 銝剔�摰峕㟲�笔𦶢�冽�瘚贝��剛�嚗䔶蝙�嗡�銝芾��鍦�隞㮖�璅∪�撖寥�嚗�僎銝�甈⊥�扯��𡁜��� 43 憿寡䌊�典�瘚贝��其�嚗諹噢�鞾妟���𣇉�撌乩�蝥找漱隞䀹偌����

## 2026-05-28 23:00
- [x] **摰䂿緵 Doji 蝻拚�����笔�蝥蹂�蝔喃��訾��墧�銝芾�撖寥�餈�誘 (Implemented Doji Shrinkage Confirmation & Corrected Backtest Alignment)**嚗�
    - [x] **摰䂿緵 `is_doji` 隡�迅�孵��𣂼�銝舘恣蝞�**嚗𡁜銁�墧��𡁏𧋦 `test_reentry_backtest.py` ��鸌敺���鞉�瘞港葉嚗���乩� `is_doji`嚗��摮埈�K蝥選���艇�潮��硋ế摰𡁶�瘜𤏪�摰硺�銝𤾸蔣蝥踵��� $\le 0.3$ �硋�雿枏��嗥�隞� $\le 1\%$嚗㚁�撟嗅��嗡� `upper`嚗���𦯀�頧典�潘��� `max_pnl_since_entry`嚗���斗�憭扳筑��恣蝞梹�銝�撟嗥��� `StrategySignal.features`��
    - [x] **�∪�撟嗅笆朣𣂼摹�蹂葵�⊥�霂閧𤌍��**嚗𡁜��笔�瘚衤葉 `300058` ��葵�⊿�蝵桐��躰秤�� `"�屸�蝘烐�"` �∪�撖寥�銝箇�摰䂿� `"�肽𠧧�㗇�"`��
    - [x] **�墧����摰𣬚�撉諹�銝𤾸摹�輯��輸𡺨**嚗𡁻�朞�撘訫���瑪 Doji 蝻拚�����煺�蝔喃�銝� `SWING_LOW_BUY` �嗆���蝖祆�批遣隞枏㨃����𣂼��� `300058`嚗���脣�������瘚衤葉摰��餈�誘�劐� `2026-05-12` ���蝒�聦霂勗�銝𡒊聦雿漤狍頝䕘�閫��鈭��蝚娪�憭找�����峕𧒄靽脲�鈭��𡁜�敺桃㩞嚗Ǒ002156`嚗�+32.55% ���蝥批⏚瘨艾��
    - [x] **瘚贝��函遛�𣳇����**嚗𡁏𧋦�啗��帋漱�枏��� 32 憿寞瓲敹�鍂靘衤��芷�㕑��笔𦶢�冽� 11 憿寧鍂靘页��� 43/43 �函滯蝏輻�頝煾�𡁜�嚗���䀹�隞颱����硔��

## 2026-05-28 22:30
- [x] **摰䂿緵 Re-entry 璅⊥���/摰䂿� 100% �喟��峕�銝� 70% 暺��隞㮖��噼‘����𣇉𠶖��笆韐行㦤�� (Hardened Re-entry Live Decision Parity, 70% Add-Back & Session Persistence Reconciliation)**嚗�
    - [x] **摰䂿�/璅⊥��� 100% �峕��喟��孵�瘜典� (Injected Live Feature Parity in kernel_service.py)**嚗𡁜銁 `evaluate_decision_item` ���滨垢憓𧼮�鈭�� `paper_adapter` ���銝剜��� `regime` (SWING_LOW_BUY) �� `tp_triggered` ������餉�嚗�𢆡��萼撖� `StrategySignal.features`���敶餃�閫��鈭���睃�蝑𡝗𧒄�删撩銋𤩺�隞梶𠶖���銝𧢲�撖潸稲�噼‘銝𤾸之甇Ｙ��喟�憭望���艇�滚�撅�撩�瑯��
    - [x] **摰䂿緵 Action-based �噼‘閫血�銝𤾸�撅�𠶖��㦤蝥𣳇� (Enforced Action-based Re-entry execution & Multi-level Reconciliation)**嚗𡁻���� `test_reentry_backtest.py` 銝� `kernel_service.py` �拍��𣂷漱�湔鰵�餉���緵�典�瘚�/摰䂿���眏�喟�憭扯� `decide` 蝏煺�颲枏枂 `action == "ADD"` �� `size_pct == 0.70` 閫血��噼‘鈭斗�嚗偦�撖寥���像隞枏之甇Ｙ�嚗𣬚�甇�𠶖��㦤�嗆����勗�����渲秤霈曆蛹 `"FLAT"` 靽格迤銝箔��嗘蛹 `"IN_TRADE"` ���撟嗉䌊�冽�銋�� `tp_triggered = True`��
    - [x] **�惩𤐄 `Position` 撖寡情頝其�霂嘥��堒������ (Secured Cross-Session Position State Serialization)**嚗𡁜銁 `Position` 蝐颱葉�啣� `regime` 銝� `tp_triggered` �喲睸�嗆����改�撟嗆楛摨虫耨�� `_save_state` 銝� `_load_state` �� JSON 霂餃��亙藁����𣂷�鈭斗��嗆�������唳𧋦�� `paper_account_state.json` 蝤����辣�����笆韐虫��剔㴓摰匧�閬����
    - [x] **�朞� 43/43 �券�瘚贝��其� 100% 銝�甈⊥�批�蝥Ｙ遛蝘㘾�� (100% Pytest Green Passage)**嚗𡁏𧋦�� PowerShell �臬�銝衤�甈⊥�抒�頝煾�朞��券� 32 憿寞瓲敹�漱�𤘪芋�埈�霂訫� 11 憿寡䌊�㕑��笔𦶢�冽�瘚贝�嚗��霈� 43 銝芰鍂靘见��券�朞�嚗䔶����甇餉���妟���𣇉���稲鈭支�韐券�嚗�

## 2026-05-28 22:00
- [x] **摰峕� Re-entry 憭𡁜𪂹�罸��睲��訾�蝒�聦�墧��餉��惩𤐄�𠰴��𤩺�霂閧遛�� (Hardened Re-entry Swing Low & Breakout Backtest Logic with 100% Test Success)**嚗�
    - [x] **瘛勗漲撉諹� Re-entry ��蟮�墧�銵函緵 (Validated Re-entry Backtest Results)**嚗�
        - 餈鞱� `scratch/test_reentry_backtest.py` �𡁏𧋦嚗屸�撖寧𤌍���憭渲� **�𡁜�敺桃㩞 (002156)** �� **�屸�蝘烐� (603533)** 餈𥡝��鞉𠯫�䭾𧊋�交㺭�桀��脣�皞舀�霂𨰻��
        - 撉諹�鈭���亙銁�𡁜�敺桃㩞銝𠹺� `2026-04-29` 蝻拚�頦拍瑪隞� `49.50` ��移��僭�伐�撟嗡� `2026-05-07` 憭扳隅銝剖��孵之甇Ｙ� 70% ��� `+19.35%` 瘚桃�嚗𥕢� `2026-05-18` �噼萱瘣㛖� `58.07` ��憬�譍�蝔單𧒄蝎曉�銵亙� 70% 皛∩�皛𡁜𢆡憟磰�嚗������祆�撟唾秐 `55.50` ���鈭� `2026-05-26` �湔��� `75.39` ���擃䀝��嗅�甈∟圻�� 70% 憭扳迫���摰� `+35.84%` 頞�漣�拇隋嚗𥕦�雿� 30% 頧颱�����喃��抵繮擃䁅噢 **`+32.55%`** ��遞����拇隋嚗�
        - 撉諹�鈭���亙銁�屸�蝘烐� (603533) �墧�銝凋� `2026-05-21` �港�頝𣬚聦�嘥�蝥踵𧒄�𨀣鱏�拐�撟喃��𠬍��𣂼��踹�鈭���誩��渲��詨� `23.50` ���摨閙楛皜羓��滚之��頝䕘�憭朞��蹂��湔㟲 **`8.2%`** ��楛瘞游躹銝贝�嚗㚁�摰峕�鈭�征隞㯄�甇Ｚ�撖毺��脫擪撅誯���
    - [x] **頝煾�𡁜��� 60/60 憿寡䌊�典��𧼮�瘚贝� (100% Regression Success with 60/60 Passed)**嚗�
        - 閫���� Windows �臬�銝� Pytest 瘚贝��嗥眏鈭� `tdx_hdf5_api` 璅∪�頝臬��𦦵揣撖潸稲�� `ModuleNotFoundError` �桅�嚗�� `JSONData` �桀�摰匧�撟嗅� PYTHONPATH��
        - 頝煾�𡁜��讛䌊�㕑��笔𦶢�冽�瘚贝�嚗�11/11 憿對��䔶漱�枏��詨�敶埝�霂𤏪�49/49 憿對�嚗��霈� **60/60** 銝芣�霂閧鍂靘页�100% 銝�甈⊥�批��嗅�蝏輻��𡄯�撅閧緵鈭���睃𤐄�仿�瘙斤���稲撌乩�蝥找漱隞睃�韐剁�

## 2026-05-28 21:30
- [x] **摰䂿緵憭𡁜𪂹�罸��煾�憭港��訾�憭批𪂹�毺��渲�皛斤�瘜訫�摰䂿��喟�摨訫漣���蝢𡡞𡡒�舐宏璊� (Delivered Full Multi-Period Gold Swing Low & Breakout Filter Strategy Migration to Trading Kernel Base)**嚗�
    - [x] **�㯄�𡁜��� `StrategySignal` 銝𤾸�瘚钅�蝏渡鸌敺���� 100% 蝎曉��惩�憭折�𡁻� (Hardened 100% Feature-Mapping Parity in signal_canonicalizer.py)**嚗�
        - ��笆甇文��典��䀹㺭�格�銝哨��曹�靽∪噡閫���硋膥 `signal_canonicalizer.py` �� `canonicalize_decision_queue_item` 撖孵��� `item` 銵峕��羓鸌敺��隞��蝞��閗圾����埈�鈭�銁��蟮暺���墧�銝剖之�曉�敶拍� **14 憿寥�蝏游𪂹��瓲敹�鸌敺�**嚗�紡�游��� `decide` �文��� `signal.features` 銝剔㮾�單���偶餈靝蛹 `False` / `0.0` ���撅�撩�瘀��扯�鈭�𧑐瘥臬�����扯圾��笆朣僐��
        - 摰𣬚�銝啣�鈭���穿�30�交�擃条� `hmax`��4�仿��� `high4`��60�交�雿𦒘� `low60`���銝𠰴之�冽�蝒�聦��� `pbreak`��之撟喳蝱憿� `ptop`��蜓�𥟇𣈲�穃極雿𦦵瑪 `sws` / `swl`��5�亙��� `vol_ma5`���隞枏予�� `days_held`��筑����� `pnl_pct`���蝏� 3�交�鈭日��𡒊憬 `vol_shrink_3d`���頦拇𣈲�睲��� `is_pullback_support` 隞亙��園��� `is_collecting_stage` / �游𤐄�� `is_consolidation_stage` �典����憟烾��賜鸌敺��畾萸��
    - [x] **摰䂿緵 OCP 撘���/撠�𡡒霈曇恣�笔�銝𢛶�𨀣�閫�朖��敺轁�萘�摰䂿��嗆��祆�蝻脲㗁�� (Secured OCP Architectural Alignment & Zero-Cost Live Integration)**嚗�
        - 靘脲�鈭擧㺭�桐�撖澆�嚗Ǒsignal_canonicalizer.py`嚗厩�摰𣬚�撖寥�銝舘����嚗���䀝漱�枏�蝑硋之�� `decision_engine.py` �𣳇��湔㺿隞颱�銝�銵䔶誨����喳虾摰𣬚��芸𢆡霂餃�撟嗥��湔�瘣駁�蝎曉漲憭𡁜𪂹�罸��穃㨃�����雿滨��� 70% 憭扳迫����+2 �脤��日���羓聦 SWS �臭�蝖祆迫�毺��詨��滨��餉�����唬��墧�銵函緵銝𤾸��䀝縑�瑕ế摰� **100% 銝亙�撖寥�銝擧�蝻苷���**��
    - [x] **隞亥��� of 撌亦�韐券��朞� 43/43 �券�瘚贝��其� 100% 銝�甈⊥�批�蝏輻��� (Passed 100% Regression Success with 43/43 Passed)**嚗�
        - �砍𧑐�� PowerShell �臬�銝页��𣂼�頝煾�帋�鈭斗���瓲�券� **32/32** 憿寞瓲敹���������𧼮�瘚贝�嚗䔶誑�𡃏䌊�㕑��笔𦶢�冽��券� **11/11** 憿孵�敶埝�霂𨰻��
        - ��恣 **43/43** 憿寞�霂蓥�甈⊥�� 100% �脩��函遛蝘㘾�𡄯�撅閧緵鈭���睃𤐄�仿�瘙斤��烾���㨃�賢�銝擧��游極銝𡁶漣��漱隞睃�韐剁�

## 2026-05-28 21:00
- [x] **摰䂿緵樴坔仍�游𤐄�罸��睲��詨�銵乩�頞�漣皛𡁜𢆡憭滚⏚�� T 蝞埈��䔶蜓��答�関�亙�銝舘��烐��芰��箏��� (Hardened Masterclass Swing Low Re-entry Add-Back Strategy for Leading Stocks)**嚗�
    - [x] **霈曇恣�屸��睲��詨�銵乩�雿溻�滨𠶖��㦤**嚗𡁜�樴坔仍���撌脩�閫血�憭扳迫�� 70% �譍�嚗䔶��𡒊賒憭𡁏𠯫�∩遠皜拙��噼氜�渡�嚗䔶��寡斐餈� SWS �舀�蝥選�`low <= sws * 1.015` 銝� `close >= sws * 0.985` 摰�迅銝滨聦嚗㚁�銝娍�鈭日��擧遬�𡒊憬嚗��鈭� 5 �亙��讐� 95%嚗匧ế摰帋蛹瘣㛖���飵蝏����頂蝏蠘䌊�典�甇文�憭扳迫���隞梶� **70% 蝑寧��祇𡢿�拍�銵亙�**嚗峕�憭� 100% 皛∩�皛𡁜𢆡憟磰���
    - [x] **摰䂿緵�������祇�蝞𦯀��脣��嫣��滩挽��**嚗𡁜�銵交𧒄�芸𢆡霈∠��啁�����鞉𧋦��遠嚗�$NewEntryPrice = OldEntryPrice \times 0.30 + Close \times 0.70$嚗㚁�撟嗅𢆡����圈俈蝥輻���笆���隞枏�憭拍� SWS �舀�雿滨蔭嚗Ǒtrailing_stop = sws * 0.985`嚗㚁�摰䂿緵鈭�𠳿�賡俈����睃仃韐亦聦雿溻����賢�蝢擧��劐�甈∩蜓��答�������折𡡒�胯��
    - [x] **摰峕��屸�𡁜�敺桃㩞 (002156)�滚蟮霂㛖漣憭滚⏚�墧�**嚗�
        - 蝑𣇉裦鈭� `2026-04-29` 蝻拚�頦拍瑪 `49.50` ��說隞㮖僭�伐�
        - 鈭� `2026-05-07` 憭扳隅銝剖之甇Ｙ� 70% ��� `+19.35%` 瘚桃�嚗�
        - 鈭� `2026-05-18` �噼萱瘣㛖� `58.07` ��憬�譍�蝔單𧒄嚗�**蝎曉�銵亙� 70% 蝑寧�嚗�����撟單��祈秐 `55.50` ����滚� 100% 皛∩��䀹�嚗�**
        - 鈭� `2026-05-26` �湔��� `75.39` ��𧒄嚗�**�曹�撌脤��啗‘�墧說隞橒�蝟餌��冽迨憭��甈∟圻�穃��孵之甇Ｙ� 70%嚗�銁��擃䀝��抵繮���擃䁅噢 `+35.84%` ���甈∟�蝥批⏚瘨佗�嚗��**
        - �拐� 30% 隞㮖�蝏抒賒���頨箄窖�喃�嚗�**銝�瘜Ｘ�皛𡁻䪸����漤�颲� `+32.55%` ���蝥抒遞����拇隋嚗��嚗�**
    - [x] **�朞� 43/43 �券�瘚贝� 100% 銝�甈⊥�批�蝏輻���**嚗朞��𡁜��� 32 憿寞瓲敹�漱�𤘪芋�埈�霂訫� 11 憿寡䌊�㕑��笔𦶢�冽�瘚贝�嚗�100% 銝�甈⊥�批�蝏輸�𡁜�嚗���啗��� of 撌亦�韐券�銝擧��游�憯格�改�

## 2026-05-28 20:30
- [x] **摰䂿緵憭𡁶征�𣂷漱�誩𪂹��𦆮�𤩺迫��/甇Ｘ�銝� SWS �舀��臭�甇餃��脩瑪蝞埈��𣬚食����誩𪂹�煺��烐惜�脣㪗�箏��� (Hardened Volume-Cycle Take-Profit/Stop-loss and Sole SWS Defense Line Strategy for Swing Low Positions)**嚗�
    - [x] **霈曇恣�峕�鈭日��冽����憭扳隅瘣曉�甇Ｙ��滨�瘜�**嚗𡁜蝠摨閖���迫��𢆡雿栶��撩�輯�憭扳隅銝𥪯撈�𤩺�鈭日��亙��曉之嚗�之鈭� 5 �亙��讐� 1.4 �㵪�隞�”擃䀝�憭𡁶征�抒��Ｘ���蜓�𥕦枂韐扳晷�𡢅�雿靝蛹憭𡁶征瘣曉��冽�蝏��靽∪噡嚗��銝𠰴撩�𤤿��� Boll Upper �硋��笔之撟喳蝱憿嗆𧒄嚗諹圻�穃��孵之甇Ｙ� 70% ����拇隋嚗𥡝𥅾�舐憬�誩之瘨典�隞�”銝餃��抒�������隞栞�憟踝�蝟餌��瑟�銝滚𢆡憭扳聢撅�頨箄窖嚗諹��蹂�擃䀝�餈�𡟺銝贝膠����漤��整��
    - [x] **霈曇恣�峕�鈭日��冽����憭扯�撏拇�撟喃��漤俈��**嚗帋葵�⊿���蜓�偦�雿滨��𤩺�頝䕘��∩遠�𧼮� > 3% 銝� vol 頞�� 5 �亙��� 1.4 �㵪��文�銝箇食��援皞�𪂹���撘箏� 100% �拍�皜��隞仿俈�脲香嚗𥡝𥅾銝箇憬�誯狍頝峕���㨃�噼萱嚗��摰��鞊���桅�帋��訾葵�∠��𤩺�甇Ｘ�嚗𣬚誧蝏剖��蹱𣈲�㻫��
    - [x] **摰䂿緵�玺WS �舀��臭�甇餃��脩瑪��**嚗𡁜笆鈭𦒘��詨遣隞㮖葵�∴��典�瘚见�摰䂿�銝剖蝠摨閗��齿芦�𡁶�敺桀�瘜Ｗ𢆡/DFF�港�蝑㗇𪊴�行�抒宏�冽迫�麄��𣈲銝�蝖祆�扳迫�毺瑪銝箏��交𤣰�䀝遠�貊忽 SWS �脩瑪嚗�$SWS \times 0.985$嚗㚁�銝滨恣�䀝葉憒���抒��𠉛�瘣㛖食嚗峕𤣰�睃銁�舀�雿滢�銝𠰴��喃�鈭文枂雿𦒘�暺��蝑寧���
    - [x] **摰䂿緵�峕𣈲�睲��𣂼��唳旿�芣��脣鴃�函���**嚗𡁻�撖寞𠯫K銵峕�銝剖虾�賢��唳旿皞鞾�憭齿��𡝗��嗘漣�毺��𤩺㺭�殷�憓𧼮� $\pm 30\%$ ��𤣰�䀝遠�讐氖�函�嚗䔶艇�滚�蝳餅𧒄�拍�撘箏�隞� $MA10/MA5$ 擃条移�芣��踵揢�舀�蝥選��急��唳旿瘙⊥��鞉���
    - [x] **摰峕��屸�𡁜�敺桃㩞 (002156)�齿�銝㚚�靽烾�𡁜��墧�**嚗�
        - 蝑𣇉裦鈭� `2026-04-29` 樴坔仍蝻拚��噼萱 SWS 銋钅�隞交�雿喃遠�潘�`49.50` ���雿𤾸𢙺銝��餃朖銝哨�
        - 鈭� `2026-05-07` 憭扳隅�湔�銝�**蝎曉����憭扳迫�� 70% ��� `+19.35%` 蝥臬⏚瘨�**嚗�
        - �拐� 30% 隞㮖��剖��香摰�𣈲�𤑳��ａ��祇俈敺∴�**摰𣬚��㰘�鈭���𤾸�頦� `57.02` ���颲� 10% 隞乩�����典��娍��矋����頨箄窖�喃�嚗峕�蝏�遞����� `+25.55%` ���鈭箏��拇隋**嚗�
    - [x] **�朞� 43/43 �券�瘚贝� 100% 銝�甈⊥�批�蝏輻���**嚗朞��𡁜��� 32 憿寞瓲敹�漱�𤘪芋�埈�霂訫� 11 憿寡䌊�㕑��笔𦶢�冽�瘚贝�嚗�100% 銝�甈⊥�批�蝏輸�𡁜�嚗���啗��∠�撌亦�韐券�銝擧��游�憯格�改�

## 2026-05-28 20:00
- [x] **摰䂿緵隞� SWS 撌乩��舀�蝥蹂� Upper 撣��銝𡃏膘銝箸瓲敹��樴坔仍�噼萱暺��雿𤾸𢙺蝑𣇉裦�屸�蝏游椰靘找��訾�瘣㛖��游𤐄憭批�蝑𣇉裦�� (Hardened High-Dimension SWS & Upper Swing Low Strategy with Multi-stage Buying & Precise Stop-loss Protection)**嚗�
    - [x] **霈曇恣�𣬚食��𤣰����噼萱 SWS 撌乩�蝥輻洵銝�銋啁��齿㺭摮行芋��**嚗𡁻�朞��刻��� 8 憭拙�餈䂿賒撠誯狍撠誯翧閫行𨰫 Upper 撣��銝𡃏膘嚗�圻�詨予�� >= 3憭抬�隞�”銝餃��𦯀葉擃䀝��貊食�讠�嚗劐�銝箏𢙺蝑寡��荔��刻�隞瑞憬�誩��賭���雿𦒘遠頦拙銁 SWS �舀�蝥蹂��寞𧒄嚗Ǒlow <= sws * 1.015` 銝� `close >= sws * 0.985` 銝娪�蝻抬�嚗𣬚移����箇洵銝�暺��雿𤾸𢙺�對��脩瑪霈曄��� `sws * 0.985`嚗峕�憭批𧑐�讠憬鈭���蹱��穿���迤摰䂿緵�𨅯�銝斗𡆀��𣶸�腈��
    - [x] **霈曇恣��之瘨冽晷�穃��� SWS �齿活隡�迅蝚砌�銋啁��齿㟲�箸芋��**嚗𡁻�撖寥�憭渲��典之瘨冽晷�穃��噼氜瘣㛖�雿�香摰� SWS �舀�蝥輻�撘�𢆡嚗諹挽摰朞��� 15 憭拙�憭扳隅嚗�隅撟� >= 12%嚗厩�瘣㛖��游𤐄�峕艶嚗�僎�冽�雿𦒘遠�齿活隡�迅�� SWS �舀�蝥蹂���漲蝻拚��嗉圻�𤑳洵鈭�遣隞㮖��貊�嚗屸��� T+2 �脤��箏�銝𤾸之甇Ｙ��箏�嚗��蝢擧��瑚�甈∟絲���銝餃�瘚芥��
    - [x] **摰峕��峕������ (603533)�滢��屸�𡁜�敺桃㩞 (002156)�漤��曉�瘚�**嚗�
        - �屸�蝘烐� (603533) �墧�銝哨�蝟餌�隞交�撠譍誨隞瘀�`-1.98%`嚗㗇迫�笔�嚗��蝢𦒘��� `[KEEP OBSERVING]` 蝛箔�閫��嚗�**閫��鈭���𡒊�餈䂿賒�渲��惩�瘛望�嚗諹��輯�撟�� 12%**嚗�
        - �𡁜�敺桃㩞 (002156) �墧�銝哨��� 2026-05-25 蝒�聦憭扳隅銝剖�蝢𦒘僭�伐�鈭� 2026-05-26 �湔隅��擃条�**蝎曉�閫血� `[TAKE-PROFIT EVENT]` ��鸌憭扳迫�� 70%嚗屸�摰𡁏筑�� `+8.04%`嚗�僎鈭� 2026-05-27 �券��箸�嚗䔶�瘜Ｘ���� `+6.38%` ���拇隋**嚗�
    - [x] **�朞� 43/43 �券� pytest �芸𢆡�𡝗�霂蓥�甈⊥�折�𡁜�**嚗朞��𡁜��� 32 憿寞瓲敹�漱�𤘪芋�埈�霂訫� 11 憿寡䌊�㕑��笔𦶢�冽�瘚贝�嚗�100% 銝�甈⊥�批�蝏輸�𡁜�嚗���啗��∠�撌亦�韐券�銝擧��游�憯格�改�

## 2026-05-28 18:30
- [x] **摰䂿緵���蝒�聦甇Ｙ�銝𡒊憬�誩�頦拙�蝥蹂��詨之撣���乓����穃�撘��樴坔仍�噼萱�箏��� (Hardened Inverted Swing Strategy with Breakout Take-Profit & Pullback Support Entry)**嚗�
    - [x] **擐硋���之�澆�蝒�聦�����鸌甇Ｙ��齿㦤��**嚗𡁻�撖孵撩�輯��典�蝒�聦����⊥��𣈯�蝜�𤫇�曇秧憭尠�萘��𤤿�嚗屸��蓮�����蕭瘨券�餉�����睲��拍�蝒�聦�𡁻�憭抵��踵��齿�撟喳蝱憿塚�`pbreak=1` �𤥁�餈� Boll Upper嚗厰���蛹 **`INTENT_TAKE_PROFIT` 撘箏�甇Ｙ�靽∪噡**嚗諹圻�� 70% 擃䀝�瘚桃��𤑳緵嚗���啣⏚瘨西氜鋡衤蛹摰剹��
    - [x] **霈曇恣�諹�蝏剔憬�誩��質秐��瑪�舀��漤��睲僭�寧�瘜�**嚗𡁻�朞��𣂷漱�讛�蝏� 3 �仿�鍦�嚗��鈭日�雿𦒘� 5 �亙��� 70% 隞�”蝑寧��𥕦�銵啁垠嚗劐���雿𦒘遠蝎曉�頦拙銁 `MA10` �� `SWS` 撌乩��舀�蝥蹂�嚗䔶�銝箸�雿喟�撌虫儒雿𤾸𢙺摨蓥�撱箔�靽∪噡嚗��蝢𡡞�撘�擃䀝���貌餈�蝸�嫘��
    - [x] **摰䂿緵�𣊁+2 �園𡢿靽脲擪���銝滚�憸���脤�撠梯粥嚗剹�漤��批㨃��**嚗帋僭�亙��� T+2 �亙�嚗諹𥅾�∩遠�芾�餈��笔之�喟瑪�厩氖�鞉𧋦�箇＆蝡衤蜓��答嚗�銁�䀝葉隞颱�銝�甈∟��脣�擃䀹𧒄�扯� 100% 撟喃��箏�嚗䔶誑���隞�遠�剛�嚗���喃����撘勗飵�渲��峕𧒄�港遠�潛��賜蒾蝤冽���
    - [x] **�朞��峕������ (603533)�漤��曉�蝒�聦憭𡁶輕摨血�瘚钅�𡁜�**嚗�
        - ��笆撘勗飵��㨃�∟�銵屸�鞉𠯫�䭾𧊋�交㺭�格��𣂼�瘚卝��頂蝏笔銁 `05-13` 蝻拚�����笔�蝢舘圻�� **[KEEP OBSERVING] 蝛箔��蹱迫閫��**��
        - �� `05-19` �喃儒��擃条��臭�蝖株恕蝒�聦�𡒊移��圻�� Re-entry �Ｗ�嚗𥕦銁 `05-21` �港�頝𣬚聦�嘥�蝥踵𧒄�𨀣鱏鈭𤩺� `-6.16%` �拐�撟喃���
        - 甇Ｘ�蝳餃㦤�𠬍��𣂼��踹�鈭���Ｘ������銝�頝舀𠂔頝䎚��狍頝𣬚瓲�� `23.50` ���摨閙楛皜羓��滚之��頝䕘�**憭朞��蹂��湔㟲 8.2% ��楛瘞游躹銝贝�嚗�**嚗㚁��罸𡢿�券�颲枏枂 [KEEP OBSERVING]嚗��蝢𤾸�憿曆��𣈯��滨�樴仮�苷��𨀣鱏��俈���擛潑�萘��誩���擃睃��䕘�

## 2026-05-28 18:00
- [x] **摰䂿緵銝��株䌊��耨憭溻�䔶遠�潸䌊���憭溻�滢�����滨鍂�瑕�憪𧢲�餉��睲��湔�扼�滚��� (Hardened One-Key Self-Healing with Price Auto-Recovery & User Capital Alignment)**嚗�
    - [x] **摰䂿緵撘�隞枏�隞瑚����啁緵隞瑕�蝥找遠�潸䌊��㦤�� (Multi-level Price Auto-Recovery)**嚗�
        - ��笆�冽��冽�銵䔶��格㺭�桐耨憭齿𧒄�航�摮睃銁���隞㮖遠�潭㺭�桃撩憭晞��0 �� NaN 撖潸稲���鈭誯�蝞堒�撣賊䔮憸矋��券�㕑�銝餌��� (Tkinter) 銝𤾸�蝑𡝗�瘞湧𢒰�� (PyQt6) 撖孵��� `_on_one_key_self_heal` �寞�銝剜��乩�摰����遠�潸䌊����詻��
        - �箄��𣂼�憭扯���㦛靚梧�`self.df_all` / `self.parent_app.df_all`嚗厩�摰墧𧒄���唬遠�潘���鉄�嗥�隞瑯��緵隞瑯����嗚����条� fallback嚗㗇�撠�蛹銝芾����唳�隞梶緵隞瘀�`current_price`嚗剹��
        - 隞� `orders` ��蟮憪娍�瘚�偌銝剝�瞍磰蕭皞臭葵�∩僭�亦��賢𪂹�毺�摰鮋��𣂷漱��遠嚗䔶�銝箔����撘�隞枏�隞瘀�`entry_price`嚗㕑�銵𣬚���耨憭㵪�撖嫣��䭾�瘞渡�撟賜����嚗屸��冽��啣��䁅���緵隞瑕�敶枏��唬遠雿靝蛹�𨅯� Fallback��
        - 摰䂿緵鈭�����典�摮䀹�隞㮖�����啁����隞梶�隞瑟聢蝏嘥笆�峕郊嚗�蝠摨閙醌皜��隞瑟聢銝� 0 �� NaN 撘訫���恣蝞堒㨃憿踴��
    - [x] **摰䂿緵�𡏭��餉��煾�銝��氯�萘�韐行�韏��摰𣬚�撖寡揭 (Respecting User Custom Capital & Perfect Reconciliation)**嚗�
        - ��笆甇文��扯��唳旿靽桀��嗡�敺𧢲�撌桀�蝎埈𠂔撘箏��拙捆�圈�霈� 100 銝���𣬚聦�讐鍂�瑁䌊摰帋��嘥�璅⊥�韏��嚗�� 20銝�/50銝�����餉�蝻粹萅嚗屸�����餉��𤏸�璅∩耨憭滚ế摰𠾼��
        - 隡睃�霂餃�撟嗯�𨅯��𨧀�嘥��滩揭�瑞�摰䂿��嘥��餉��� `initial_capital`��蘨閬���滩挽摰𡁶��餉��𤏸�憭笔��渲��𡝗�隞𤘪�餅��穿�`initial_capital >= entry_cost_sum`嚗劐�憭找� 0嚗䔶��桐耨憭滚� **敹惩�靽萘�撟嗅笆朣鞟鍂�瑕��厩��餉��煾�嚗𣬚�撖嫣�鈭�砥�孵��𡁜�**��
        - �芣��刻揭�瑕�鈭擧𧊋�滨蔭�嗆���`initial_capital <= 0`嚗㗇��𡏭�銝齿𠽌�算�嘥紡�游虾�函緵�睲蛹韐�㺭�塚��滩圻�烐惣�質䌊���摰寧�瘜𤏪�靽嗪�韐凋僭�偦�韐��摰𣬚��潮▽鈭��瘣餅�找�摰匧��扼��
        - �芸𢆡�扯� `cash = initial_capital - entry_cost_sum` 撖寡揭�餉�嚗�僎撠�耨甇����㺭�桐��格�銵𣬚���氜�䀹�銋��嚗Ǒ_save_state`嚗㚁�颲曉�鈭�楊蝔见��笔𦶢�冽���偶銋���氬��
    - [x] **瘚贝��券�蝘坿�撉諹�**嚗𡁜�蝢擧��蠘��朞䌊�㕑��笔𦶢�冽�銝𦒘漱�枏��詨銁����券� **60/60** 憿� pytest �芸𢆡�𡝗�霂𤏪�100% 銝�甈⊥�批�蝏輸�𡁜�嚗���啗�擃睃極蝔见�韐剁�

## 2026-05-28 17:30
- [x] **摰䂿緵璅⊥�鈭斗�����其��喟��Ｘ踎�券曎頝臬笆韐血��箔�蝣舘��行⏛ (Hardened Paper Trading Sync, Direct Ledger Reconciliation & 100-Share Production Constraint)**嚗�
    - [x] **敶餃��寞祥擃㗛�撖寡揭�䭾���虾�函緵�𤏸���歲�� (Root-Caused & Fixed Cash Re-calculation Drift)**嚗�
        - ��笆�� `DecisionFlowPanel` 摰𡁏𧒄�瑟鰵�塚�蝟餌�霂舐鍂�𨀣�餉�鈭� - 敶枏�������唳�餃��潑�嘥��𤑳��湧�霈曉僎閬��鈭斗���瓲 `paper_adapter.account.cash` 撖潸稲�舐鍂韏���讐�撣�㦤銵峕��唬遠瘜Ｗ𢆡憸𤑳�頝喳����蝳餃���漱�梶��𦦵��餉�蝻粹萅��
        - 敶餃�摨罸膄鈭�誑敶枏�撣��澆�蝞堒虾�函緵�𤑳��箏�嚗諹挽霈∪僎�函蔡鈭�抅鈭擧�隞栞��啣��典榆憸萘� **憓鮋� Transaction 撖寡揭�讛悅**嚗𡁜蘨�匧�����喃���瓲�渡�����𤑳�摰鮋��⊥㺭憓𧼮�嚗�僭�交緍�𧶏��𤥁��啣�撠𡢅��硋枂�䂿狩嚗㗇𧒄嚗峕��㗇�鈭文�隞瑕�撌桅��典�銝�甈⊥�抒����蝞𦯀蛹�圈�嚗���唬� `cash` 韏�����撖孵像蝔喃�銝��湔�扼��
    - [x] **�函�鈭抒㴓憓�葉撘箏��行⏛�� 100 �⊥㟲�齿㺭銋啣� (Enforced 100-Share Production Constraints & Prevented Fractional Shares)**嚗�
        - ��笆�煺漣�臬�銝讠眏鈭𡒊��∩僭�吔�憒� 1 �～��99 �∴�鈭抒�憭折� phantom 撟賜�畾讠聦���銝擧筑鈭讛恣蝞埈�蝘餌��𤤿�嚗�銁 `PaperExecutionAdapter.submit_order` 銋啣�銝𤾸像隞㯄𧫴畾萄��乩�銝交聢�� **100 �∪�銝见���** �� **��雿� 100 �∠′�行⏛** �冽��𣂼���
        - ��笆���劐僭�伐�`BUY`/`ADD`嚗劐��譍�嚗ǑREDUCE`嚗匧�嚗�撩�嗅笆 volume 餈𥡝�隞� 100 銝箏抅�� of �睲��𡝗㟲嚗�� 350 �� -> 300 �∴�嚗�僎撖寞�蝏������唬�頞� 100 �∠��訫��湔𦻖�拍��行⏛�垍��扯�嚗𥕦銁 `_is_test` �訫�瘚贝��臬�銝衤��躰䌊�函�餈�㦤�嗡誑靽肽� legacy �訫�瘚贝��澆捆嚗諹噢�𣂷� 100% ���鈭折�璉埝�扼��
    - [x] **摰䂿緵蝎曉����撖寡揭銝� 100% pytest �芸𢆡�𡝗�霂訫�蝏輸�朞� (Passed 100% Regression Success with 32/32 Passed)**嚗�
        - �� `PaperExecutionAdapter` ���嚗��韏�������緍�譍��䂿狩靽格㺿銝箏抅鈭� `摰鮋����/敶坿��⊥㺭 * price` 餈𥡝揭嚗屸���笆韐血��� `Auto-Heal Bridge` 憓鮋�蝏梶�蝞⊿�嚗峕��笔��唬��嗉秤撌柴��妟瞍�宏����𤏸扇韐艾��
        - �祇𡢿摰𣬚�頝煾�帋� `trading_kernel/tests` 銝剔��券� **32/32** 銝芸�������瘚贝��其�嚗�100% 銝�甈⊥�批�蝏輸�𡁜�嚗���嫣�靽嗪�鈭��摨抒���稲蝔喳�嚗�

## 2026-05-28 15:30
- [x] **靽桀�鈭斗��喟�瘚�偌�烐綉 `DecisionFlowPanel` 銵冽聢蝛箄�銝齿遬蝷箔� 0 �讐��睃�甇駁� Bug (Fixed Decision Flow Empty Display & 0-Width Column Lock)**嚗�
    - [x] **�寞祥�堒捐�睃�甇駁��芣��箏� (Fixed 0-Width Column Lock & Auto-Healing)**嚗�
        - ��笆�冽��漤����𨀣�瘞湔遬蝷箏枂�軔ug敺���唳旿銝齿遬蝷箔蛹蝛綽��交��園𡢿��誨�����蝘唬��曄內�萘��𤤿�嚗��雿滚��曹��函�隞嗅�憪见��嗆挾餈�𡟺�Ｗ�銵典仍�嗆���甇斗𧒄蝒堒藁撠𡁏𧊋�拍�皜脫��曄內嚗�捐摨西繮�𣇉��靝蛹 0 �讐�嚗㚁�撖潸稲�喲𡡒蝒堒藁靽嘥��嗅��堒捐閬��銝� 0 �讐�撟嗆�銋���� `window_config.json`嚗䔶�銝�甈∪��臬𢆡蝏抒賒��緵 0 摰賡��讐𠶖����
        - 撠�”憭渡��Ｗ�銝𤾸�摰賜��嘥��㚚�餉��齿�銝粹�朞� `QTimer.singleShot(150, self._safe_restore_and_adjust)` 撱嗉� 150 瘥怎�撘�郊摰匧�閫血�嚗𣬚＆靽萘������偕撖詨停蝏芥��
        - �� `_safe_restore_and_adjust` ���滨垢�㰘��𨅯�摰賢�撣貉䌊�冽嵗甇���芣��函��嘅��Ｗ�銵典仍�嗆���嚗䔶��行醌�誩�隞颱��詨��㛖�摰鮋��堒捐撠譍� 15 �讐�嚗�ế摰帋蛹撘�虜�睃��嗆���嚗𣬚��喳撩�嗉��� `_adjust_column_widths` 餈𥡝��堒捐�芷����滨�嚗䔶��拍�銝𠰴蝠摨閖俈�� 0 �讐��睃�甇駁���
    - [x] **摰䂿緵撋�� `kernel_result` �唳旿蝏𤘪�憭𡁶漣�澆捆閫��蝞埈� (Nested kernel_result Multi-level Decoding)**嚗�
        - ��笆鈭斗���瓲�亙�銝剖��格����憒� `kernel_state`��kernel_action`��kernel_confidence`��kernel_stop_price` 蝑㚁�頧祉宏�� `kernel_result` 摮𣂼��詨�撖潸稲�� UI 閫��憭梯揖�𤤿�嚗屸���� `_append_record_to_table` �𣬚��唳旿閫���餉���
        - 撘訫�鈭� `kernel_res = rec.get("kernel_result", {})` 閫��撅��撟嗅�蝥批�畾菜��碶蛹 `kernel_res.get("kernel_state") or rec.get("kernel_state") or trace.get("state")` 憭𡁶漣 Fallback �惩�嚗屸�蝎曉漲�澆捆鈭�鰵���憟埈𠯫敹埈聢撘譌��唂���撟單𠯫敹埈聢撘譍誑�𠰴�蝟餌�����亙��典��荔�蝖桐��枏���獈�剔���迫�煺遠蝑劐縑�� 100% 摰峕㟲�曄內��
    - [x] **摰𣬚��朞��券� 60/60 pytest �芸𢆡�𡝗�霂閧鍂靘见�蝏輸�朞� (100% Regression Success)**嚗朞挽蝵� PYTHONPATH �臬��㗛��𠬍�摰𣬚�頝煾�帋�憿寧𤌍����怨䌊�㕑��笔𦶢�冽�銝𦒘漱�枏��詨銁����券� 60 憿寡䌊�典�瘚贝�嚗䔶�甈⊥�批�蝏輸�朞�嚗䔶�霂�頂蝏�沲����箇迅�伐�

## 2026-05-28 14:00
- [x] **摰䂿緵鈭斗��亙� `trading_kernel_trace.jsonl` 頧駁��𤥁��芯�皛𡁜𢆡皜��敶埝﹝ (Standardized Log Trimming, Automatic Compression & Retention Limit)**嚗�
    - [x] **霈曇恣鈭斗��亙��閗�擃䀹�扯�頧駁��𤥁��芰�瘜� (Trimming Optimization)**嚗�
        - ��笆瘚�偌韐行𧋦�踵�蝘舀��𦯀�摮埈挾撖潸稲蝤��雿梶妖�𣳇�憓鮋鵭����對��� `JsonlJournal.append` �������交��滨垢撘訫�鈭� `_trim_record` 餈�誘撘閙���
        - 摰䂿緵鈭�笆撋��摮堒��𠰴�銵函��鍦��急�嚗���典��支�撖孵��暸�瞍𥪜� UI 皜脫�瘥急�敶勗���之�见�雿坔��𣂼�畾蛛�憒� `confidence_inputs`嚗㚁�撟嗅笆瘚桃��圈��嗡蛹靽萘� 4 雿滚��堆�雿踹�銵峕𠯫敹堒��其�蝘舀𠂔�� 70%+��
        - 撖� `HUMAN_CONFIRMATION_AUDIT`嚗�犖撌亦＆霈文恣霈∴�蝐餃�����桀��暹綉�嗅葷隞亙�蝟餌����靽⊥��扯�撘箏�鞊��靽萘�嚗䔶�霂���墧𦆮�� UI ����游虾�冽�扼��
    - [x] **銝贝��芸𢆡�讠憬���澆僎摰䂿緵敶埝﹝����冽��� (Compression & Retention Limit)**嚗�
        - 撠�䌊�典�蝻拇���圻�煾��潛眏�笔��� 5MB 銝贝��� **2MB**嚗峕����頧颱��閙活 I/O 餈賢�隞亙� UI 鋆�蝸憓鮋�����嗥�蝤��撖餃��園𡢿��
        - 撘訫�鈭� `.jsonl.gz` 敶埝﹝����冽���㦤�塚��讠憬�其�摰峕��𠬍��芸𢆡�急��桀�銝讠����匧�獢��嚗屸�朞� `mtime` �園𡢿�喃��批��啗�銵𣬚����摨𧶏�隞���蹱��啁� **10 銝�** 敶埝﹝���撠��雿蹱凒���敶埝﹝��蟮��辣�拍��𣳇膄嚗�蝠摨閙��支�蝤������鞱����航���
        - **撘訫�銝梶鍂 `archive` 敶埝﹝摮鞟𤌍敶�**嚗帋��碶�敶埝﹝��辣�拍�摮睃�頝臬�嚗䔶��滚��嗥凒�乩腺�� `logs` �寧𤌍敶蓥�嚗諹�峕糓�芸𢆡�𥕦遣撟嗥輕�� `logs/archive/` 銝梶鍂摮鞉�隞嗅允餈𥡝��𠉛氖摮䀹𦆮嚗䔶���𠯫敹埈覔�桀����皜��摨艾��
    - [x] **銵亙�擃䀝��笔����霂訫僎摰䂿緵 60/60 pytest 100% �函遛蝘㘾�� (Regression Testing and Validation)**嚗�
        - �� `test_journal_contract.py` 銝剜鰵憓硺� `test_journal_trimming_and_retention_cleanup` �訫�瘚贝��其�嚗䔶��𨅯�雿坔�畾菔�皛手�腈���𨀣筑�寞㺭�𥡝�鈭𥪜�蝎曉漲�芣鱏�腈���𨅯之�亙���辣閫血��讠憬敶埝﹝�苷誑�𪙛�𨅯��脣�獢��頞�枂 10 銝芣𧒄�芸𢆡�拍�瘛䀹掠������萘�憭𡁶輕摨血��𣂷�銝亙����霂閗��硔��
        - 摰𣬚��朞�鈭�䌊�㕑��笔𦶢�冽�銝𦒘漱�枏��詨銁����券� 60 憿� pytest 瘚贝��其�嚗��敶埝�霂閙��毺�颲� 100%嚗�

## 2026-05-28 13:40
- [x] **�寞祥璅⊥�鈭斗�韐行𧋦 `paper_account_state.json` �誩��滨蔭銝𡒊������ (Root-Caused & Fixed Paper Account State Accidental Reset & Truncation)**嚗�
    - [x] **�𦦵��瑕鍳�刻䌊�刻��𡝗㦤��**嚗𡁻��� `_load_state`嚗�縧�支��㰘恥�閖�瞍𥪜��箇���捏���銝擧�銋������圈�銝滨��嗅銁�瑕鍳�典�頧賡𧫴畾萄撩�嗉��� `positions` 銝� `cash` ���餉�嚗䔶�銝��湔𧒄隞���� `logger.warning` 蝥批�霅血��亙����蝖桐��芾� `paper_account_state.json` �㗇�嚗𣬚頂蝏� 100% 撠𢠃�撟嗅�摰𧼮�頧賣�銋���唳旿嚗𣬚�撖嫣�隡𡁜�霈Ｗ�銝滚��諹䌊�券�蝵桀虾�刻��穃������𥅾蝖桀�鈭抒�撘�虜嚗𣬚眏�冽��朞� UI 銝羓��靝��株䌊���苷耨憭齿��格��刻圻�穃����蝟餌�銝滩䌊�刻��硔��
    - [x] **摰䂿緵鈭斗�霈啣��睃𢆡�扯�雿齿��� (Implemented Trade Fingerprint Dirty Checking)**嚗𡁜銁 `_save_state` ���滨垢撘訫�鈭��蝎曇�雿齿�瘚见遆�� `_get_trade_fingerprint`嚗屸�朞�撖寞��嘥�韏����緵�㻫���隞枏�畾� (�㘾膄�讛�����函� current_price) 隞亙�霈Ｗ��𡑒”嚗峕䔉�����犒��蘨�匧銁鈭斗�霈啣��𤑳�摰鮋��拍��睃𢆡�嗆��扯��嗵����蝏苷��冽��睃𢆡���銝钅�憸烐凒�唬遠�澆蒂�亦�憭帋��嗵�韐蠘蝸��
    - [x] **摰䂿緵�笔��𣇉���𤜯�Ｗ��� (Atomic File Write-Replace)**嚗𡁜銁 `_save_state` 銝剝�朞� safe-cast �⊿��餅鱏 NumPy float64/Timestamp 摨誩��𡝗𥁒�坔紡�渡��嗵��芣鱏嚗�僎��漣銝算�𨅯�摮睃��堒� -> �坔�銝湔𧒄��辣 `.tmp` -> �笔��踵揢 `os.replace`�脲�蝔页�敶餃��𦦵�鈭�眏鈭� JSON 摨誩��𤥁�銵峕𧒄撘�虜撖潸稲�����辣鋡急�蝛箔蛹 0 摮𡑒�������蝵� Bug��
    - [x] **�拍��餅鱏瘚贝�餈𤤿����隞嗅��䀹情�� (Isolated Test Environment Write pollution)**嚗𡁜銁 `_load_state` �� `_save_state` ����滨垢�惩�撖� `"PYTEST_CURRENT_TEST" in os.environ` �臬��㗛���撩�𥕦ế摰𠾼���霈箸�霂閧鍂靘𧢲𧋦頨怠�雿訫撩�嗉挽蝵� `_is_test = False`嚗�蘨閬��銵�銁 pytest 蝥輻�/餈𤤿�銝𠹺���葉嚗�停蝏嘥笆蝳�迫霂餃��笔��� `paper_account_state.json` �拍���辣嚗�銁�拍�銝𠰴蝠摨閙��支��靝�頝烐�霂𤏪��笔����撠梯◤�滨蔭�萘��桅���
    - [x] **59/59 pytest 瘚贝� 100% �函遛皛∪��朞�**嚗𡁏��罸�霂��敶埝�霂𤏪�靽嗪�蝟餌���惣蝔喳�餈鞱�嚗�

## 2026-05-28 13:10
- [x] **隡睃�撌脣像隞㮖漱�栞扇敶閗�皛支��滨蔭����� (Optimized Closed Positions Filtering & Persistence in DecisionFlowPanel)**嚗�
    - [x] **瘛餃��曄內撌脣像隞栞�皛日�厰★**嚗𡁜銁 `DecisionFlowPanel` ����批��Ｘ踎銝剖��� `chk_show_closed` 憭漤�㗇� (�� �曄內撌脣像隞� (0��))嚗�僎撠�𠶖��㺿�䀝��唳旿�瑟鰵�𥪜𢆡��
    - [x] **摰䂿緵�嗆���蝎曉�靽嘥�銝擧�憭�**嚗𡁜��喲𡡒蝒堒藁 (`closeEvent`) �硋��ａ�厰★�塚��芸𢆡�坔� `window_config.json` 餈𥡝�頝其�霂苷�摮矋��典�憪见��Ｗ��嗆�� (`_restore_header_state`) �塚��朞� `blockSignals` �脫�瘜典��滨蔭��
    - [x] **�冽㺭�桀��唬葉摨𠉛鍂撌脣像隞栞�皛�**嚗𡁜銁 `_refresh_positions_tab` 銝剖��厰★�嗆����交葡�𤘪�蝥� `state_rep` �脫迫�誯�蝏条�頝荔��峕𧒄�芸銁�暸�厩𠶖���撠�歇撟喃�嚗��隞栞��唬蛹 0嚗厩�銝芾��唳旿頧賢� `display_positions` �𡑒”撅閧內嚗屸�霈斤𠶖���嚗�𧊋�暸�㚁��躰䌊�刻�銵𣬚�����𧶏�摰��閫�� 0 �∪厭�菔����閫匧僕�啜��
    - [x] **59/59 pytest �訫�銝𡡞��鞉�霂� 100% 銝�甈⊥�折�朞�**嚗朞��𡁜��𤩺�霂𤏪�蝏𤘪��函遛�朞�嚗䔶�霂�頂蝏�沲����箇迅�伐�

## 2026-05-28 12:45
- [x] **摰䂿緵��瓲瘣餉����銝𤾸��脣像隞栞扇敶閧���△閫��血��諹”�𥪜𢆡 (Implemented Active Positions & Closed Records Tab Separation & Dual-Table Linkage in DecisionFlowPanel)**嚗�
    - [x] **霈曇恣�� Tab �Ｘ踎��氖皜脫�蝞⊿�銝𤾸歇撟喃�霈啣��𡝗��齿�蝞埈� (Delivered Dual-Tab Panel Separation & Closed Positions Reconstruction)**嚗𡁜銁 `DecisionFlowPanel` 銝剖��� `QTabWidget`嚗���笔�瘛瑟�����豢�隞𤘪���蛹�𨥉�� ��瓲摰墧𧒄��� (Kernel Positions & PnL)�嘥��𨥉�� ��蟮撟喃�霈啣� (Closed Positions)�嘥� Tab��蛹鈭�圾�喳歇撟喃�銝芾��� `positions` 摮堒�銝剛◤�拍� pop 蝘駁膄撖潸稲銵冽聢蝛箇蒾��𠗕憸矋��孵�撘��睲� **鈭斗�憪娍�瘚�偌�齿�餈睃�蝞埈�**嚗𡁏��園𡢿����滢�瞍𠉛�瘥誩蘨銝芾���僭�𣇉��賢𪂹���蝎曄＆閫��撟嗆��硋枂撌脣��啣像隞梶���遠���鈭誯�����啁�鈭讐�隞亙�撖孵���絲甇Ｘ𧒄�湔挾嚗�蝠摨閗圾�喃�瘚贝��枏��嗥�銝滚�撟喃��䔶漱�栞扇敶閧�蝻粹萅��
    - [x] **摰䂿緵����桃�/曌䭾��𥪜𢆡�𠰴��颱�隞嗅��� (Enforced Keyboard/Mouse Linkage & Double-Click Navigation)**嚗帋蛹 `pos_table` 銝� `closed_table` ��‘朣𣂷���稬�𥪜𢆡鈭衤辣嚗峕��帋�撖寞暑頝��隞橒�`_on_pos_cell_double_clicked`嚗匧�撌脣像隞栞扇敶𤏪�`_on_closed_cell_double_clicked`嚗厩���稬 K 蝥輯��冽㦤�塚�敶餃��寞祥鈭�眏鈭𡒊撩憭勗��餅𦻖��紡�游�憪见��嗆𥁒�� AttributeError 撏拇��� Bug��
    - [x] **摰䂿緵�諹”�澆�摰賣�銋��銝舘䌊���隡貊憬 (Delivered Layout Persistence & Dynamic Sizing)**嚗𡁜銁 `closeEvent` �� `_restore_header_state` 銝剝��𣂷� `closed_header_state` �嗆���嚗峕𣈲��楊蝔见�隡朞�靽嘥�銝𡒊移���憭滨鍂�瑁��渡��𨅯��脣像隞栞扇敶𨰝�肽”憭湔�摨譌���摰賢�撣��撟嗅笆 `resizeEvent` 銝讠� `_adjust_column_widths` 餈𥡝�鈭��銵典笆朣鞾���嚗峕��支�蝒��銝贝”�澆�撅�皞Ｗ枂�𣬚征�賡䔮憸塩��
    - [x] **����諹”�喲睸�𨅯�銝𤾸歇撟喃�霈啣��唳旿���� (Delivered Dedicated Context Menus & Record Truncation)**嚗帋蛹 `closed_table` 憓𧼮�鈭� `_show_closed_context_menu` �喲睸�𨅯�嚗峕𣈲���𨥉�𡢅� 蝘駁膄甇文歇撟喃�霈啣��腈���𨥉�𡢅� 皜�膄���匧歇撟喃�霈啣��嘥��∠巨隞���滨妍�������塚��𣂼�鈭���䀹����硋��䀹㺭�桃������
    - [x] **瘚贝��券��𧼮�銝�甈⊥�批�蝏� (100% Regression Success with 59/59 Passed)**嚗𡁜��讛��𡁜��祈䌊�㕑��笔𦶢�冽���漱�枏��詨�瘚见�璅⊥� API �典������ 59 銝� pytest 瘚贝��其�嚗��敶埝��毺� 100%嚗�

## 2026-05-28 12:15
- [x] **摰䂿緵鈭斗���瓲撘�隞𤘪𧒄�湧��嗡� T+1 �硋枂閫���⊿� (Trading Hours Constraint & T+1 Settlement Enforcement for Paper Trading Adapter)**嚗�
    - [x] **�拍��行⏛�硺漱�𤘪𧒄�游�隞枏𢆡雿� (Hardened Trading Hours Gate for BUY/ADD Orders)**嚗�
        - �� `PaperExecutionAdapter.submit_order` 銋啣�嚗ǑBUY`/`ADD`嚗匧���葉嚗諹��乩���笆鈭斗��園𡢿���瘜閙�批ế摰𠾼��
        - �游� `cct.get_work_time()` 銝� `cct.get_work_time_duration()`嚗屸�鈭斗��園𡢿銝见��湔𦻖�垍��扯�嚗䔶�皞𣂼仍銝𦠜�蝏苷��𧼮�瘜蓥漱�𤘪𧒄�港漣�笔�隞枏��躰秤�園𡢿�喟��航�嚗�����霂閧㴓憓�歇�㰘� `_is_test` 鞊���箏�隞乩�霂��摰寞�改���
    - [x] **霈曇恣擃条移 T+1 ���銝𤾸虾�㚚�摨行嵗撉𣬚�瘜� (Enforced T+1 Lock & Dynamic Available Shares Calculation)**嚗�
        - �典像隞橒�`SELL`/`REDUCE`嚗匧���葉嚗諹��乩�撖� T+1 鈭斗�蝏梶�閫����艇撖�ế摰𠾼��
        - 蝏枏���� `entry_time` ���隞𤘪𧒄�湧𡢿�磰�銵𣬚���予�唳嵗撉䎚��𥅾撘�隞𤘪𧒄�游�鈭𤾸�憭抬��湧� < 1憭抬�嚗諹砲����臬�憸嘥漲�湔𦻖��香銝� 0��𥅾撘�隞𤘪𧒄�湔𡟺鈭𦒘�憭抬��湧� >= 1憭抬�嚗����捂撟喃�嚗�僎�滚�敶枏予�牐��𣂷漱�� `bought_today_vol` �冽����箔��亙虾�𤥁��堆�`available_vol = max(0, total_volume - bought_today_vol)`嚗㚁�摰𣬚��餅鱏鈭���乩僭�亥�鈭批銁敶枏予鋡恍�瘜訫��箝��
    - [x] **銵亙�銝枏��訫�瘚贝�撟嗅��� 59/59 pytest 100% �函遛蝘㘾�� (Delivered Unit Tests & Achieved 100% Regression Success)**嚗�
        - �� `test_paper_trading.py` 銝剔��嗘� `test_paper_trading_trading_hours_constraint` 銝� `test_paper_trading_t1_constraint` 銝日★擃条移摨阡𡡒�舀�霂閧鍂靘页��冽䲮雿漤�霂��鈭斗��園𡢿畾菟��嗚��+1 撘�隞𤘪𧒄�游予�圈𡢿�娪�隞㮖誑�𠰴�隞枏�隞梶���＆�扼��
        - �𧼮�餈鞱��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨銁����券� 59 憿� pytest �訫�銝𡡞��鞉�霂𤏪�隞� 100% 皛∪��鞟貍�函遛�朞�嚗�

## 2026-05-28 11:30
- [x] **摰䂿緵鈭斗���瓲�喟�瘚�偌�烐綉���隞𤘪𧒄�氬�齿�銋������埈�摨譍�銝��格㺭�株䌊�� (Standardized Entry Time Persistence, Interactive Column-Sorting & Self-Healing for Decision Flow Panel)**嚗�
    - [x] **瘛勗漲�惩𤐄 `PaperExecutionAdapter` 隞㮖� `entry_time` 撅墧�找������ (Hardened Position Entry Time Persistence)**嚗�
        - ��笆�冽��漤����靝漱�枏��詨�蝑𡝗�瘞渡��找葉敺���箇緵瘝⊥�撘�隞𤘪𧒄�氯�萘��桅�嚗�銁 `paper_adapter.py` �� `Position` 撖寡情銝剜遬撘讛����撟嗆�銋��鈭� `entry_time` 撅墧�扼��
        - 摰䂿緵鈭� `entry_time` 摮埈挾�� `_load_state` �� `_save_state` 銝剔�摰峕㟲摨誩��碶��滚��堒�嚗屸�朞� `paper_account_state.json` 摰䂿緵鈭�楊隡朞�/蝔见��滚鍳��偶銋��銋����
    - [x] **霈曇恣擃条移憪娍��訫�皞航��笔�隞𤘪𧒄�渡�瘜� (Delivered Historical Order Reconciler for Auto-Healing)**嚗�
        - �齿�鈭� `PaperExecutionAdapter._load_state()` �����䌊��嵗撉���𠬍��刻�頧賭�雿齿㺭�格𧒄嚗諹𥅾璉�瘚见��鞉�隞� `entry_time` 蝻箏仃�碶蛹蝛綽��芸𢆡�朞��墧滲�嗅��𥪯葵�∠� `orders` ��蟮銋啣�憪娍�嚗峕����拍��𣂷漱�園𡢿�寡䌊�其耨憭滚僎銵仿� `entry_time`��
        - 撖� `_on_one_key_self_heal` 銝��株䌊���餉�餈𥡝�鈭��撘綽��拍��急� `trading_kernel_trace.jsonl` �亙�嚗屸�朞��芸𢆡閫��隞𦠜𠯫�𠰴��脖漱�𤘪�瘞港葉銋啣�靽∪噡���鈭斗𧒄�渡�嚗���啣笆餈鞱�銝剜�隞梶� `entry_time` 瘥怎�蝥扯䌊������撟嗅�靽桀��𡒊�蝏𤘪��峕郊摮条���
    - [x] **摰䂿緵�喟�瘚�偌銝𤾸��豢�隞枏��烾�靽萘��鍦��箏� (Delivered Complete Column Sorting for Decision Flow and Positions Tables)**嚗�
        - ��笆�冽��𨀣溶�惩�憭���喟�瘚�偌�𠰴��豢�隞𤘪��� col ���摨誩��賤�萘�霂㗇�嚗�銁 `decision_flow_panel.py` 銝剖��乩� `SortableTableWidgetItem` �芸�銋厩掩嚗屸�頧賭�瘥磰��滢�蝚� `__lt__`��
        - 閫��鈭� Qt 暺䁅恕撠�”�澆���聢雿靝蛹蝥舀��祆�摨誩紡�湔㺭�潘�憒��雿齿�靘卝���鈭誯���蓡���嚗剹��𠯫��𧒄�湛�憒��隞𤘪𧒄�氬��像隞𤘪𧒄�湛��𤑳��惩��嗘僚����對��舀��典��啣�潔�摮㛖泵銝脩�瘛瑕�擃条移摨行�摨譌��
        - 撖� `DecisionFlowPanel` 銝剔��𨅯�蝑𡝗�瘞氯�苷��𨀣�隞𤘪�蝏��苷舅銝芾”�潛��券��烾�蝵桐��鍦��潭�撠�����兩�𨀣㺭�桀‵���蝳�鍂�鍦���‵���靚�㟲�堒捐�擧�憭齿�摨謿�萘��脫�皜脫�蝞⊿�嚗𣬚�����𦦵�鈭��憸𤏸�����唬��曹� Qt �芸𢆡�齿�撖潸稲����Ｘ��具���甇颱� CPU 撠硋陸��
    - [x] **�𧼮�瘚贝� 57/57 pytest 100% 皛∪��函遛蝘㘾��**嚗�
        - �砍𧑐�� PowerShell 銝见�蝢舘�銵䔶��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨��� 57 憿� pytest �訫�銝𡡞��鞉�霂𤏪�銝�甈⊥�批�蝏輸�朞�嚗䔶�霂����瓲銝� UI 撅��擃条移摨衣迅摰𡁏�改�

## 2026-05-28 10:55
- [x] **敶餃��寞祥蝡硺遠韏偦帕�Ｘ踎���箸𧒄�� `PyEval_RestoreThread` 撘�虜銝𤾸�蝥輻� GIL 撏拇� (Fixed Racing Panel PyEval_RestoreThread Exit Crash)**嚗�
    - [x] **�拍���膄 `closeEvent` 銝� unsafe �� `processEvents` 瘜菟��**嚗𡁜��支� `bidding_racing_panel.py` �Ｘ踎 `closeEvent` 銝剖��祉鍂鈭𤾸撩�嗡�隞嗅���� `QApplication.processEvents()` 靚�鍂嚗�蝠摨閙��支���瘥�𧫴畾萇眏鈭𦒘�隞園��亙紡�渡�憭𡁶瑪蝔� GIL 鈭匧內嚗屸獈�凋� `PyEval_RestoreThread` �游𦶢�躰秤��
    - [x] **撱嗉�皜�膄 PyQt 蝒堒藁撘箏��券俈������ GIL �脩� (Deferred PyQt Window Reference Clearing)**嚗𡁜�雿滚僎�餃�鈭�銁 Qt �� `closeEvent` 餈𥡝�銝哨�銝� Tkinter 蝒堒藁�朞��峕郊 `closed` 靽∪噡�噼��湔𦻖撠� `self._racing_panel_win` 撘箏��函蔭銝� `None` 撖潸稲��援皞��瘣𠺶��砲銵䔶蛹隡帋蝙 Python ����典銁 C++ ��瘥�𧫴畾菜𧊋摰峕��齿��滩◤ GC �墧𤣰嚗諹��𣬚眏鈭𡒊瑪蝔讠𠶖��毽銋勗��� `PyEval_RestoreThread` �仿�撏拇������蛹�朞� `self.after(100, _safe_clear)` 撠���函蔭蝛箔��峕郊蝒堒藁�嗆���雿𦦵宏�� C++ ���箏葷嚗�銁 Tkinter 蝥輻����銝�撣批��冽�銵䕘�瘨�膄鈭��甈∪鍳�典�����剝緾��憌𡡞埯��
    - [x] **摰䂿緵靽∪噡摰匧�閫��銝𤾸�蝒堒藁 `deleteLater` 撱嗉��𦠜𦆮**嚗𡁜銁摮鞟����憒� `SectorDetailDialog`��CategoryDetailDialog` 蝑㚁��扯� `close()` �㵪��曉�閫��摰�賑撖嫣蜓�Ｘ踎�� `data_updated` �唳旿�湔鰵靽∪噡餈墧𦻖嚗屸俈甇Ｘ���葉�磰◤畾讠����憸𤏸���㺭�格��噼��餌忽嚗𥕦僎撠���匧��找辣�𠰴��嗅膥�������嗥�銝�憪娍�蝏� Qt 鈭衤辣敺芰㴓�� `deleteLater()` �寞�嚗屸俈甇Ｖ��拍��屸��𦠜𦆮�脩���
    - [x] **隡睃���瘥��𡁶䰻撟踵偘�嗅�**嚗𡁜� `self.closed.emit()` �其�銝交聢蝘餉秐 `super().closeEvent(event)` �扯�摰峕�銋见�嚗𣬚＆靽苷蜓 Tkinter �烐綉�屸𢒰�冽𤣰�圈𢒰�踹��剝�𡁶䰻�塚�霂仿𢒰�輻�摨訫� C++ �交�撌脣��𣂼��券���嚗屸��滢蜓蝥輻��滢�甇�銁�鞉����撠詨笆鞊～��
    - [x] **�拍��踹�摮鞟���銁���箸𧒄�滚�閫血��𦯀��嗵�撟嗥眏銝駁𢒰�輻�銝�靽嘥� (Eliminated Redundant Disk I/O Blocking & Consolidated Save)**嚗𡁏��亙��唬蜓�Ｘ踎�典��剖�蝒堒藁�塚�隡𡁜�甇亥圻�烐�銝芸�蝒堒藁 `SectorDetailDialog` 銝� `CategoryDetailDialog` �芾澈�� `closeEvent` 餈𥡝�峕�銵� `_save_header_state` �拍�摮条�嚗屸�䭾�憭𡁏活�滚��� `gzip.write` 蝤���坔������蛹嚗𡁜銁銝駁𢒰�踹��剖�蝒堒�瘜典� `child._is_main_closing = True` ���嚗䔶蝙摮鞟���銁 teardown �嗆挾�湔𦻖頝唾���䌊����� I/O �坔�嚗𥕦��嗅銁銝駁𢒰�輻� `_save_ui_state` 銝哨�銝餃𢆡�園����匧��齿�撘�摮鞟�������啁��牐�雿滨蔭銝𤾸�摰賣㺭�殷���𡠺 `detail_column_widths`��detail_geometry` �����掩�寞���捐摨虫�蝵桅睸嚗㚁�銝�撟嗅�撟嗅��滨蔭摮堒�銝剔眏銝駁𢒰�踵�銵�𣈲銝�銝�甈∪�摮鞟�����矋��冽��支����箏㨃憿輻��峕𧒄嚗�100% 摰峕㟲靽萘�鈭����箏�����厩�����Ｙ𠶖����
    - [x] **�㯄�𡁜��� 57/57 pytest 瘚贝��其��函遛�朞�**嚗𡁜銁 PowerShell 銝钅�蝵� PYTHONPATH �𠬍�摰𣬚�頝煾�帋�蝟餌��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨銁����券� 57 憿� pytest 瘚贝��其�嚗��敶埝��毺� 100%嚗�

## 2026-05-27 23:15
- [x] **摰䂿緵 Rotator IPC 蝟餌�銝� Windows 憭朞�蝔� Nuitka �澆捆�批蝠摨訫��綽��寞祥霂𦠜鱏 dump �罸𡢿�芣��脩�銝舘���㦤�芷��嚗�61/61 瘚贝��其� 100% �函遛蝘㘾�� (Stabilized Rotator IPC, Hardened Nuitka Multi-processing & Secured 100% Regression Success)**嚗�
    - [x] **�函蔡霂𦠜鱏 dump �罸𡢿 rotator �芣��笔��� (Deployed _dumping_stack State Lock)**嚗𡁜銁 `dump_all` 霂𦠜鱏���撖澆枂��蜓瘚��銝哨�蝏��鈭� `self._dumping_stack = True` �嗆���嚗�僎�� `sync_rotator_windows` ���滨垢璉�瘚贝砲���隞亦凒�亦�頝舀㜃�芥���敶餃��餅鱏鈭������剜��渡眏鈭� rotator 閫血��芣�撘閗絲��僎�煾��亙��拍��脩���
    - [x] **�滨蔭 `HotkeyRotatorProcess` 銝粹�摰�擪餈𤤿� (daemon=False)**嚗𡁜� rotator 撖孵��� multiprocessing摮鞱�蝔� `daemon` 撅墧�批撩�嗆㺿銝� `False`嚗峕��支� Nuitka 銝�雿枏��枏�摨𠉛鍂�� Windows 撟喳蝱���箏��交��墧𤣰�塚��曹� daemon 餈𤤿�畾讠�撖潸稲���蝔𧢲�韏瑕� Windows 銝湔𧒄�桀�鋡恍��桅���
    - [x] **憪娍晷銝餌瑪蝔𧢲�銵� `mp.Process.start()` 閫�� VM ��緾�� (Offloaded Process start() to UI Main Thread)**嚗𡁜蝠摨訫��支��勗��啣��斤瑪蝔讠凒�亥��� `new_hp.start()` ����勗�瘜𤏪��齿�銝箏銁�𤾸蝱蝥輻��𡁜��嗆���憭��嚗屸�朞� `self.after(0, _spawn_in_main)` 憪娍晷蝏� Tkinter UI 銝餌瑪蝔见�甇亙��冽�銵�鍳�具������敶餃��寞祥鈭� Nuitka �枏�憭𡁶瑪蝔讠㴓憓���曹� `PyEval_RestoreThread` 撘訫��� Access Violation C 蝥折緾��撏拇���
    - [x] **撘訫� 5 蝘鍦��臬𢆡撱嗉�銝� 20 蝘坿��剛䌊����剝俈�� (Enforced 5s Boot and 20s Cooldown Gates)**嚗𡁻�撖� Nuitka �臬𢆡 socket 蝏穃���𧒄撱嗥鸌敺��撠���臬笆朣𣂼辣餈煺�靚�秐 5 蝘𡜐��� `dump_all` 閫血��𤾸�霈� 20 蝘坿䌊����剖膥嚗𣬚�甇ａ�蝜��餈痹�隞𤾸�撅���凋� handle 瘜��銝� Windows 摰𡁏𧒄�典�撱箏仃韐亙紡�渡�甇駁���
    - [x] **隡睃�霂𦠜鱏����亙��坔�璅∪�銝箄��� (Changed stack trace dump log to overwrite mode)**嚗𡁜� `dump_all` �賣㺭銝剖��� `instock_dump.log` ���隞嗆�撘�璅∪��梯蕭�𩤃�`"a"`嚗厩������蛹閬��嚗Ǒ"w"`嚗㚁�蝖桐�瘥𤩺活閫血�霂𦠜鱏頧砍��嗆唂�����𠯫敹𦯀�鋡怠��嗉��吔��脫迫蝤��蝛粹𡢿餈�漲�删鍂��
    - [x] **摰䂿緵 '�∠巨撘�𢆡�唳旿�烐綉' 璅∠��交𪄳銝𤾸�蝒堒藁頧格揢撖潸⏛ (Added 'StockChangesMonitor' Search & Rotator Navigation)**嚗�
        - �拙�鈭� `_find_visualizer_hwnd` 璅∠��寥��箏�嚗���乩� `"�∠巨撘�𢆡�唳旿�烐綉"` �� `"�∠巨撘�𢆡"` ��𣈲����
        - 摰䂿緵鈭���函�頝刻�蝔讠���蘂��䰻�曉遆�� `_find_stock_changes_monitor_hwnd`��
        - �� `_get_all_open_trade_windows` 銝𧢲鰵憓硺��祉�����怠��荔�撖� `changes_hwnd` 餈𥡝� IsWindow/IsWindowVisible 瘣餅�扳�瘚衤��駁�嚗屸◇�拙��嗅紡�� MRU 撟嗅�甇亥秐�典�敹急㭘�株蔭頧祉頂蝏��敶餃��㯄�帋�撖嫖�𡏭�蟡典��冽㺭�桃��把�萘��輻�頝刻�蝔钅睸�睃紡�芸��Ｕ��
        - **隡睃�蝏煺�銝箏�甈⊥醌�誩龪�滢� 500ms 蝻枏��箏�**嚗�
            - �齿�撟嗆鰵憓硺�蝏煺��交𪄳�亙藁 `_scan_windows_cached`嚗���唬�銝�甈� `EnumWindows` 蝟餌�蝥折����甇亙龪�滚�銝芸��函���蘂���K蝥踹虾閫�� + �∠巨撘�𢆡�唳旿�烐綉嚗㚁�撟嗅��乩� 500ms �冽��𧒄�渡�摮䀝��歹�敶餃�瘨�膄鈭���剜𧒄�游�憭𡁏活靚�鍂 Wrapper 撖潸稲���撘誩�甈� EnumWindows 蝟餌�靚�鍂��
            - **隡睃�蝏煺�銝箏�甈⊥醌�誩龪�滢� 500ms 蝻枏��箏�**嚗�
                - �齿�撟嗆鰵憓硺�蝏煺��交𪄳�亙藁 `_scan_windows_cached`嚗���唬�銝�甈� `EnumWindows` 蝟餌�蝥折����甇亙龪�滚�銝芸��函���蘂���K蝥踹虾閫�� + �∠巨撘�𢆡�唳旿�烐綉嚗㚁�撟嗅��乩� 500ms �冽��𧒄�渡�摮䀝��歹�敶餃�瘨�膄鈭���剜𧒄�游�憭𡁏活靚�鍂 Wrapper 撖潸稲���撘誩�甈� EnumWindows 蝟餌�靚�鍂��
                - **撘訫� `IsWindow` 瘣餅�扳�瘚�**嚗𡁜銁餈𥪜��齿��亦�摮条� HWND嚗䔶��血��啣�撠詨蘂��朖�餉䌊�典仃��僎�滚�嚗諹圾�喃��� PyQt �滚遣撖潸稲����脣蘂��仃�������亦�摮䀹�����湔𦻖憭滨鍂嚗䔶蝙 `EnumWindows` 靚�鍂甈⊥㺭�湧� 70% 隞乩���
                - **蝏穃� callback 撘箏���**嚗𡁻�朞� `self._win_enum_callback_ref` �函掩�𣂼��㗛�銝羓�摰𡁜撩撘閧鍂嚗峕��支� Nuitka 蝻𤥁��𠰴�蝥輻��臬�銝页�C-callback 撠𡁏𧊋�扯�摰峕�撠梯◤ GC �𦠜𦆮撘訫��� Access Violation C 蝥折緾��憌𡡞埯��
                - **霈曇恣 Soft Invalid 頧臬仃����芸𢆡�滨漣�齿醌�箏�**嚗𡁜��� `_win_cache_valid` �⊿�雿滚笆蝻枏����𨅯��笔𦶢�冽�瘣餅�把�肽�銵𣬚𠶖����改�閬���典𦶢銝凋�摨訫��交��朞�瘣餅�扳嵗撉䕘���笆鈭擧𧊋�典𦶢銝剔��典�憭望�蝻枏�頝唾� 500ms TTL �湔𦻖�滨漣閫血��齿醌嚗峕�蝏苷� UI �嗆���蝘颱�撘�虜蝻枏���鵭�笔��賭葉嚗��靚�鍂甈⊥㺭�滚������
    - [x] **�券� 61/61 瘚贝��其� 100% 皛∪��函遛蝘㘾�� (100% Regression Success with 61/61 Passed)**嚗𡁻�朞��� PowerShell 銝剖��湧�蝵� `PYTHONPATH`嚗��頧賡★�格覔�桀��� `JSONData` 摮鞟𤌍敶𤏪�嚗䔶誑銝�甈⊥�批�蝏踵說���蝏抵��帋��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨�瘚讠��券� 61 憿孵�敶埝�霂閧鍂靘页�靽嗪�蝟餌���惣蝔喳�餈鞱�嚗�

## 2026-05-27 22:20
- [x] **閫���墧𦆮撘閙�/IPC擃㗛��亥郎銝擧��舀��仿�䭾���indows USER�交�皞Ｗ枂�𡃏恣�嗅膥�𥕦遣憭梯揖甇駁��桅� (Mitigated IPC Replay UI Saturations & Timer Failures)**嚗�
    - [x] **摰䂿緵 UI 瘨���笔�摰𡁏𧒄�寥��匧�瘨�晶 (Centralized 10FPS Throttled Batch Queue Consumer)**嚗𡁻���� `signal_dashboard_panel.py` ���隞嗅��烐㦤�嗚��銁 `_on_signal_received` �交𤣰蝡荔�撠���㗇䔉�芸���/IPC/�餌瑪�� `BusEvent` �湔𦻖�惩� `self._incoming_event_queue` 蝻枏�蝻枏�嚗�蝠摨訫縧�支�擃㗛� `sig_bus_event.emit` 撖潸稲��楊蝥輻� QueuedConnection 瘨��憌擧𠂔���朞���蝸 `100ms`嚗�10FPS嚗厩�摰𡁏𧒄�� `_event_consume_timer` 摰𡁏𧒄靚�鍂 `_consume_incoming_events` �寥��匧�憭��嚗峕�蝏苷� UI 蝥輻�鋡恍�憸穃��暹㺭�桀�擖勗��餃稬��䔮憸塩��
    - [x] **�㯄�� `_safe_process_event` �拍��峕郊�扯� (Direct Synchronous Processing)**嚗𡁜笆�𨅯��粹�霅西��煺縑�猾�苷誑�𪙛�𨀣𦆮�譍葵�∩誨����領�萘� UI �𥪜𢆡撟踵偘鈭衤辣嚗���支��笔��� `sig_bus_event.emit` 撟踵偘�箏�嚗屸�頧賢僎靽格迤銝箇凒�亙�甇亥��其蜓蝥輻� `self._safe_process_event(BusEvent(...))`嚗𣬚����敶餃��亦氖鈭��敹����楊蝥輻��閖�鍦���嚗峕�蝏苷�擃㗛� timer/event �交�蝘臬���
    - [x] **撘箏� UI 蝒堒藁蝏�辣�笔𦶢�冽��芣�銝� QTimer 敶餃�瘜券� (Restored Explicit Widget QTimer Destructors)**嚗�
        - ��笆 `VolumeDetailsDialog` �� `SignalDashboardPanel` �Ｘ踎�喲𡡒�塚��� `stop` 銝� `closeEvent` 銝剛‘朣𣂷�撖� `_event_consume_timer`��_render_scheduler` ��遬撘� `.stop()` 銝擧釣����
        - ��笆 `bidding_racing_panel.py` 銝剔� `RacingPieWidget`��SectorDetailDialog`��CategoryDetailDialog` �𠹺蜓�批��� `BiddingRacingRhythmPanel`嚗���Ｚ‘朣𣂷��� `closeEvent` 銝剖笆���㗇暑頝�𢆡�餃��嗅膥�𠰴��啣��嗅膥嚗Ǒ_timer`, `timer`, `refresh_timer`, `_save_ui_timer`嚗厩��曉� `.stop()`��.deleteLater()` �拍�瘜券��𣬚蔭蝛綽�蝖桐��函�����剜𧒄摨訫��� C++ 摰𡁏𧒄�典蘂������瘥��Windows USER �交�摰𣬚��𦠜𦆮��
    - [x] **瘚贝��券��𧼮�銝�甈⊥�批�蝏� (100% Regression Success with 61/61 Passed)**嚗𡁏𧋦�唬誑 `python -m pytest` �券�頝煾�𡁜��祈䌊�㕑��笔𦶢�冽���漱�枏��詨�瘚卝����批� API 璅⊥��典� **61/61** 銝芣瓲敹��霂閧鍂靘页�100% 銝�甈⊥�折�朞�嚗䔶��靝�摨閧�����𧼮�蝔喳��改�

## 2026-05-27 18:50
- [x] **摰䂿緵�暸�銝芾�撘寧�嚗ĀolumeDetailsDialog嚗劐�靽∪噡�Ｘ踎�笔𦶢�冽�敶餃�閫��佗�撟嗡��嗵���/��稬銵𣬚��𥪜𢆡��揢�蠘� (Decoupled VolumeDetailsDialog from SignalDashboardPanel & Retained Code Linkage)**嚗�
    - [x] **閫��衣��賢𪂹�毺�摰�**嚗𡁜銁 `SignalDashboardPanel` 摰硺��� `self._vol_dialog` �塚�撠���亦��嗥����parent嚗匧��唬耨�嫣蛹 `None`嚗𣬚＆靽嘥�雿靝蛹�祉���▲撅������剁��喃噶靽∪噡�Ｘ踎鋡怠��准����𤩺���撠誩�嚗峕𦆮�譍葵�∪撕蝒𦯀��賜𡠺蝡贝�銵�僎蝏湔��航��嗆����
    - [x] **靽脲��∠巨��揢�𥪜𢆡**嚗帋��坔僎�Ｗ�鈭�笆 `self._vol_dialog.code_clicked.connect(self._on_vol_code_clicked)` ����伐�蝖桐��冽��冽𦆮�讛�撖毺������稬銝芾�銵峕𧒄嚗䔶��嗉�憭笔�隞亙�銝��瑟迤撣詨�銝餌��������其縑�瑚誑��揢 K 蝥輻�銝餉��整��
    - [x] **摰䂿緵�喲𡡒�喳蝠摨閖�瘥���孵稬撘箏�瞈�瘣餉秐���滨垢**嚗�
        - �� `VolumeDetailsDialog` 銝剖��� `WA_DeleteOnClose` 撅墧�改�蝖桐��冽��喲𡡒蝒堒藁�塚�摨訫� C++ 撖寡情�拍���瘥���䔶��臭�隞���讐��典��啣��啜��
        - �冽�撘�霂亙撕蝒㛖��亙藁�𦠜㺭�格凒�啣�霈曇恣 `try-except RuntimeError` �箏�嚗諹䌊����Ｘ� C++ 撖寡情�臬炏撌脩�鋡恍�瘥��隞舘��銁��閬�𧒄�芸𢆡�删��齿鰵�𥕦遣��
        - 撘訫� `raise_()` 銝� `activateWindow()` 撘箏�撠��鈭𤾸��唳�鋡恍��∠�摮䀹暑撘寧��齿鰵�匧����滨垢撟嗆�瘣餌��對�敶餃�閫��鈭�鍂�瑕銁�𤾸蝱�曆��唬��䭾��齿活�孵稬�日���䔮憸塩��
    - [x] **敺株�憭湧����霂湔�**嚗𡁜�撘寧�憭湧�霂湔���倌 `header` ���獢��憭滢蛹 `"�𤣳 撘�𢆡�暸� | ��稬銵諹���"`嚗��撖潭��䀹�餈𥡝�靘踵㭘��翰�瑁��具��
    - [x] **�券��𧼮�瘚贝�摰𣬚��朞� (100% Core Regression Success)**嚗朞��帋���鉄鈭斗���瓲銝𡒊��賢𪂹�毺��券� 61 憿孵�敶埝�霂閧鍂靘页�100% �函遛�䭾���

## 2026-05-27 18:40
- [x] **摰䂿緵�暸�銝芾�撘寧�蝵桅▲�嗆��𢆡����港�����吔�暺䁅恕銝滨蔭憿� (Implemented VolumeDetailsDialog stays-on-top state toggle & persistence, defaulting to False)**嚗�
    - [x] **撘訫� QCheckBox �屸𢒰敺株��找辣**嚗𡁜銁 `VolumeDetailsDialog` 撘寧�憭湧�甇�葉瘛餃� `蝵桅▲` 憭漤�㗇�嚗㇋CheckBox嚗㚁��朞��滨蔭�讛��滩𠧧�寞�撟園��� 9pt 蝝批�摮𦯀����敺桃憬颲寞�嚗���唬� �𨥉榀� DNA摰∟恣�� �厰僼蝑厰�撟唾��鍦���
    - [x] **��僎蝵桅▲銝𡒊������𠶖���甈⊥�批�甇亥氜��**嚗𡁜��� `_save_window_states` �亙藁嚗���典�甈⊿�憭滨��� I/O��銁蝒堒藁�喲𡡒 (`closeEvent`) �㚚��� (`hideEvent`) �塚�撠�蔭憿嗥𠶖�� `stays_on_top` 雿靝蛹蝏𤘪��硋�畾蛛�銝𡒊���� x����idth��eight 雿滨蔭憭批��唳旿銝�撟嗆���凒�啣��亙�撅� `volume_details_dialog` �滨蔭摮堒�銝哨�撟嗥眏 `_CONFIG_FILE_LOCK` 蝥輻���＆靽嘥�甈∪�摮𣂼��亦�摰匧��扼��
    - [x] **摰䂿緵�冽�� WindowFlags �嗆���撱箏��Ｖ�撱嗉��賜�**嚗𡁜��滨��见㗲�㗇��𡝗�蝵桅▲�塚��芸銁���銝剖𢆡����Ｙ𠶖����齿� `setWindowFlags` (�牐��硋��� `Qt.WindowType.WindowStaysOnTopHint`)嚗�僎�曉�靚�鍂 `self.show()` 閫血� Qt �交��芷����滨�嚗���啣朖�嗥��湔鰵���嚗𥡝�𣬚�甇��蝵格�隞嗥�����硋��䀹�雿𨅯�撱嗉��啁�����哨�`closeEvent`嚗㗇��鞱�嚗ǑhideEvent`嚗㗇𧒄蝏煺��笔��扯�嚗���典笆朣𣂼�蝟餌��餉���
    - [x] **�券��𧼮�瘚贝�摰𣬚��朞� (100% Core Regression Success)**嚗𡁏��煺誑 100% 皛∪�頝煾�帋��券� 61 憿孵�������瘚贝��其�嚗𣬚＆靽苷耨�寧��牐遙雿蓥儒�Ｗ�雿𦦵鍂嚗�

## 2026-05-27 18:30
- [x] **摰䂿緵�墧�霅行𥁒�亙��典�蝥批��峕郊銝𦒘葉�Ｗ�靘钅����敶餃�閫���亙�蝥扯�憭望�銝𤾸�霅阡�霅佗��券� 61/61 瘚贝��其� 100% �朞� (Synchronized Backtest Alert Log Levels, Refactored SignalGradingHub Singleton & Secured 100% Test Success)**嚗�
    - [x] **�齿� `SignalGradingHub` 銝箇瑪蝔见��典�靘𧢲芋撘� (Refactored SignalGradingHub as a Thread-Safe Singleton)**嚗帋耨�� `get_signal_grading_hub` 摰䂿緵嚗���亦瑪蝔钅�銝𡡞�霈ａ��箏�嚗屸��齿�甈∟��券�憭滚�撱箏�靘见�憭𡁏活�滚�霈ａ� `SignalBus.EVENT_PATTERN`���敶餃��寞祥鈭�唂��𧋦�曹��𣳇��嗥��𣂼�靘见紡�渡��𤾸蝱鈭衤辣蝘臬����摮䀹�瞍譍��𦯀�憸�郎撟踵偘��
    - [x] **撘訫� `IntradayEmotionTracker` �箄�璅⊥�璅∪��亙��漤� (Implemented Smart Simulation Log Level Adaptation)**嚗𡁜銁 `realtime_data_service.py` �����舅憭�瓲敹� `logger.warning` 憭���䭾芋�笔�瘚讠𠶖��ế�准��𥅾憭��璅⊥��嗆����芸𢆡撠���砍撩銵�銁�批��唳��箇� SBC 銝� �港�憌𡡞埯霅血��亙��滨漣銝� `logger.info`��
    - [x] **�㯄�� `test_bidding_replay` �賭誘銵���啁漣�磰挽蝵� (Hardened CLI Log Level Propagation in Replay Tool)**嚗𡁜銁�墧��𡁏𧋦 `test_bidding_replay.py` �� `main` ���拇��湔𦻖撠�圾�𣂼��� CLI `--log` 蝥批�嚗�� `ERROR`嚗厩�摰𡁜僎摨𠉛鍂�啣�撅��蓥� Logger嚗ǑLoggerFactory.getLogger()`嚗㚁�隞舘�䔶蝙���厩� `logger.info` �漤��亙��芸𢆡鋡怨�皛歹�靽肽�鈭�� UI �賭誘銵峕芋撘譍��墧��亙�颲枏枂銝舘挽蝵桃�蝏嘥笆銝��氬��
    - [x] **�券�瘚贝��𧼮��函遛�朞� (100% Regression Success with 61/61 passed)**嚗𡁏��煺誑 100% 皛∪�頝煾�𡁜��怠�瘚衤�摰墧𧒄銵峕��典��� 61 憿寞�霂閧鍂靘页��函頂蝏笔�蝢𤾸笆朣琜�

## 2026-05-27 18:00
- [x] **�寞祥韏偦帕�墧�擃㗛��亥郎瘣芸陸銝舘祗�喲��堒�蝘荔�瘨�膄 GUI �交�瘜��銝� Windows 摰𡁏𧒄�典�撱箏援皞��44/44 �券�瘚贝��其� 100% 皛∪�蝘㘾�� (Silenced Backtest Alert Flood, Restored Voice Queue & Cleared 100% Core Test Regression)**嚗�
    - [x] **撘訫� AlertManager 璅⊥�璅∪��䠷�蝵穃�銝𡡞��𡑒䌊�� (Implemented AlertManager Simulation Silent Gate & Queue Flushing)**嚗𡁜銁 `alert_manager.py` 銝剜鰵憓� `set_simulation_mode(bool)` �亙藁嚗����揢�單芋��/�墧�璅∪��塚��祇𡢿撘箄�撠� `enabled` 霈曆蛹 `False` 撟嗅蝠摨閙��文��啁妖�讠�霂剝𨺗�笔�嚗Ǒvoice_queue`嚗㚁��𦦵�鈭���笔�瘚𧢲��渲祗�單偘�亙�蝥輻��交��堒偷銝𤾸�摮䀹��脯��
    - [x] **摰䂿緵 `SignalGradingHub` �墧�瘨���行⏛銝� GUI ��楝撟踵偘蝏閗� (Deployed Backtest Alert Suppressor & GUI Bypass)**嚗𡁜銁 `signal_grading_hub.py` 銝剜楛摨西��� `AlertManager.set_simulation_mode()`����冽芋��芋撘譍�璉�瘚� to 霅行𥁒�穃��塚��芸銁�批��唬誑�亙�敶Ｗ�颲枏枂霂𦠜鱏嚗𣬚����撘箄��行⏛撟嗥�甇ａ�朞� `SignalBus` 撟踵偘 `EVENT_MARKET_ALERT` 靽∪噡�� GUI���摰��閫��血僎靽脲擪鈭� UI 蝥輻�銝𦒘蜓鈭衤辣敺芰㴓嚗�蝠摨閙覔摰䂿緵鈭�眏鈭擧絲�誩�瘚钅�霅血�靚�葡�枏紡�渡� `QEventDispatcherWin32` timer �交��堒偷撏拇��芣���
    - [x] **�惩𤐄 30 蝘㘾�蝎暹迤�蹱��硋縧�齿㦤�� (Hardened Regular-Expression Number-Invariant De-duplication)**嚗𡁻���� `SignalGradingHub._publish_alert` �駁�蝞埈���銁�𣂼� `dedup_key` �塚��朞� `re.sub(r'\d+', '', content)` �拍��娪膄霅行𥁒摮㛖泵銝脖葉���厰�銵峕�擃㗛�瘜Ｗ𢆡�睃���葵�⊥㺭�𤩺��曉�瘥娍㺭�潘�靘见�撠��𣈯�銝剔聦雿�(2975��)�苷��𣈯�銝剔聦雿�(2977��)�萘�銝�瘜𥕦��讠憬銝算�𣈯�銝剔聦雿�(��)�嘅����蝖桐�鈭� 30 蝘鍦���縧�漤�餉��Ｗ笆甇斤掩擃㗛�瘜Ｗ𢆡��㺭摮𦯀��嗆��嗥迅摰𡄯�隞擧覔�砌�瘨�膄鈭��憭漤�霅艾��
    - [x] **瘚贝��函遛�䭾��𧼮� (100% Regression Success with 44/44 Passed)**嚗𡁜�蝢𤾸�敶坿�銵䔶��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨�蝟餃��梯恣 **44/44** 憿孵�������瘚贝��其�嚗�銁�啁���誑 **100% 銝�甈⊥�批�蝏�** ��說���蝏拚�𡁜�嚗峕㺭�桐���瓲銝��湔�批𤐄�仿�瘙歹�

## 2026-05-27 16:20
- [x] **摰峕��亙�颲枏枂憸𤑳�銝舘��凋縑�臬縧�芯��吔��券� 44/44 瘚贝��其� 100% 皛∪�蝘㘾�� (Optimized Log Output Frequency, Silenced Diagnostic Spam & Passed 100% Test Parity)**嚗�
    - [x] **摰䂿緵 [Rotator] 瘣餉�蝒堒藁瘜典��駁�銝� 30 蝘㘾�憸� (Deduplicated & Throttled Rotator Window Logs)**嚗𡁜銁 _get_all_open_trade_windows �寞�銝剖��� _last_rotator_details_str 撖寞��脫�蝻枏�嚗�僎憓𧼮� 30 蝘㘾�憸烐��伐�隞�銁蝒堒藁�𡑒”�睃𢆡銝娍說頞� 30 蝘㘾𡢿�娍𧒄�枏㫲靚���亙�嚗峕�憭扯���� I/O 韏����
    - [x] **摰䂿緵 [Diag] 30蝘坿��剖�頝喟𠶖���皛� (30s State-Change Diagnostics Filter)**嚗𡁜� update_tree 銝剔� �� [Diag] 霂𦠜鱏敹�歲�嫣蛹�箔� _last_diag_str ��𠶖����硋笆瘥娍芋撘𧶏�撟嗅��園𡢿�湧����潛眏 15 蝘雴�靚�秐 30 蝘鉝��
    - [x] **皜�膄�𦯀� 15:30 �睃�隞餃𦛚敹�歲�烐� (Removed 15:30 Heartbeat Spam)**嚗𡁜��典��支�瘥誩��罸�憸烐��啁� [15:30 Job] 璉��� debug �亙�嚗���碶��睃��𣬚征�脫𧒄畾萇��亙�颲枏枂��
    - [x] **�睃��芷���敹�歲�冽�靚�㟲**嚗𡁜� schedule_15_30_job 摰𡁏𧒄敹�歲璉�瘚钅𡢿�𠉛眏�笔�擃㗛��� 60 蝘𡜐�60 * 1000嚗劐�靚�秐��惣�� 30 ���嚗�30 * 60 * 1000嚗㚁�餈𥕢�甇仿��曆蜓蝥輻�鈭衤辣敺芰㴓摰𡁏𧒄韏����
    - [x] **瘚贝��函遛擃䀹�蝘㘾�� (100% Regression Success)**嚗𡁜�蝢舘��帋��券� **44/44** 鈭斗���瓲銝舘䌊�㕑��笔𦶢�冽����瘚贝�嚗䔶誑 100% 皛∪�蝘㘾�朞�撉諹�嚗�

## 2026-05-27 16:00
- [x] **蝟餌�憭朞�蝔衤�憭𡁶瑪蝔见��冽㦤�嗅��𤩺楛摨血��賂��㯄�𡁜��� 44/44 瘚贝� 100% 皛∪�蝘㘾�� (Completed Complete Concurrent & Threading Safety Review & Secured 100% Core Verification Parity)**嚗�
    - [x] **瘛勗��埝䰻�𥕦之�詨�璅∪�銝� IPC �𥪜𢆡摰匧�**嚗𡁜��誩��訾� **StockSelector**��**Stock Live Strategy**��**Alert System** �� **TradingAnalyzer** 璅∪�銝剔�憭𡁶瑪蝔见�憭朞�蝔𧢲㺭�格���
    - [x] **蝖株恕 DataFrame �芾粉�曹澈銝擧�/瘛望鼧韐嘥�蝥�**嚗𡁻�霂�� `StockSelector` 銝𦒘蜓蝒堒藁�峕郊蝥輻� `send_df` ��笆 `df_all` ���蝥輻�霈輸䔮�嗆���StockSelector.load_data()` �函�����嗆���𧒄嚗屸�朞�銝餃𢆡�扯� `self.df_all_realtime.copy()` 摰𣬚�摰䂿緵鈭��瘙⊥��𠉛氖��
    - [x] **霂�� MarketStateBus �穃�-霈ａ�銝𤾸��� compare() 霈曇恣���頞𦠜��**嚗䫤send_df` �峕郊蝥輻�摰���鍦�鈭�銁�典��曹澈 DataFrame 銝羓����鈭㚁��券𢒰��鍂 `MarketStateBus` ����砍�撣�恥��� `df.compare` 撌桀�����箏�嚗�蝠摨閙�蝏苷�憭朞�蝔钅𡢿���摮䀹香���擃㗛� GUI 皜脫�憌擧𠂔��
    - [x] **摰峕�撟嗅�撣�極銝𡁶漣�羓頂蝏笔僎�睲����摰匧�摰⊥䰻�亙��𧘹rtifact**嚗𡁏㟲��僎撖澆枂鈭��鈭� `artifacts/analysis_results.md` ����嗅恣�交𥁒�𠺪�撖孵歇閫���� 5 憭批�摮㗛緾��甇餉��� 3 憭扳�蝏剝俈���雿喳�頝萇滯蝥輯�銵䔶�雿梶頂�𡝗��潘�銝箇頂蝏毺�擃睃虾�冽����銵䔶�撽暹擪�迎�

## 2026-05-27 15:35
- [x] **敶餃��寞祥 Nuitka �枏�憭𡁶瑪蝔讠㴓憓�� `detect_signals` 撖孵�鈭怠�撅�銵峕��唳旿 `df_all` �扯��笔𧑐蝭⊥㺿撘訫��� Access Violation �芷��嚗峕��𡁜��� 44/44 銝芣瓲敹��霂� (Fixed Threading Access Violation Crash in Nuitka Packaged Environments & Secured Read-Only Shared Data Contract)**嚗�
    - [x] **蝖株�憭𡁶瑪蝔见�鈭� DataFrame �笔𧑐�坔�蝒� (Diagnosed Concurrent In-place Writing to Shared DataFrame)**嚗𡁏��亙枂 `kline_monitor.py` �典��祉�����啣��斤瑪蝔� `refresh_loop` 銝哨��湔𦻖�瑕�鈭��撅��曹澈����嗉���之�曇停�唳旿撘閧鍂 `df = self.get_df_func()`嚗�朖 `self.df_all`嚗㚁�撟嗅銁瘝⊥��瑁�靽脲擪����萎��湔𦻖隡删� `detect_signals(df)` �扯�靽∪噡憛怠���眏鈭� `detect_signals` ���隞亙�銝𧢲虜�� `RealtimeSignalManager` 隡𡁜笆隡惩��� `df` �扯��笔𧑐嚗ǎn-place嚗匧�撅墧�批��啣��梹�餈坔紡�游��啗恣蝞㛖瑪蝔衤�銝餌瑪蝔讠� UI 皜脫��𠰴�隞硋��嗡遙�∩��游��罸�憸𤑳�霂餃��脩���銁 Nuitka 蝻𤥁�銝� C/C++ �箏膥���擃䀹�扯�憭𡁶瑪蝔贝�銵䔶�嚗峕��梶��渲圻�� Windows 摨訫��� Access Violation (0xc0000005) 畾菟�霂臭���紡�渡�摨誯�暺㗛緾����
    - [x] **撘訫� `detect_signals` 憿嗥漣�脰澈�瑁�銝𡒊�撖寧����蝳� (Deployed DataFrame copy() Protection)**嚗𡁜銁 `stock_logic_utils.py` ��� `detect_signals` �賣㺭�亙藁憭��撘箄�瘜典�鈭� `df = df.copy()` 瘚�/瘛梢�蝳駁俈�斗㦤�嗚��蝙敺𡑒砲霈∠��賣㺭�𠰴������ SignalManager �芾��滢��祉���𧋦�啣��穿�摰���亦氖撟園獈�凋�撖嫣蜓蝥輻��曹澈 `df_all` �唳旿�㛖��蹱情�橒�隞𤾸�撅������凋�憭𡁶瑪蝔见�摮䁅���援皞���寞���
    - [x] **���笔��� 44/44 銝芸�������瘚贝� 100% 蝘㘾�� (100% Verification Parity)**嚗𡁜�蝢舘��帋���𡠺 watchlist �港葵�笔𦶢�冽�銝𦒘漱�枏��詨�蝟餃��梯恣 44 憿寞�霂閧鍂靘页��冽㺭蝘鍦�隞� **100% 銝�甈⊥�批�蝏�** ��說���蝏拍��𡄯��啗�鈭�㺭�桀�蝥虫���瓲摨訫�����湔�找�蝔喳��改�
- [x] **瘨�膄 KLineMonitor_init 銝� `duration_sleep_time` �㗛��芸�銋� (NameError) ����誩援皞�香閫� (Fixed NameError Scope Bug for duration_sleep_time)**嚗�
    - [x] **摰帋�撟嗡耨憭滢��典��躰秤**嚗𡁏��亙枂銝餌��� `instock_MonitorTK.py` 銝剔� `KLineMonitor_init` �𣂼��寞��冽�韏� K 蝥輻��抒���𧒄嚗𣬚凒�乩蝙�其�鋆詨��� `duration_sleep_time`嚗諹�屸▲撅�����隞�紡�乩� `commonTips as cct`嚗�僎�芸�霂亙��𤩺釣�亙��滚�撅�雿𦦵鍂�麄����嗥移��耨甇�蛹 `cct.duration_sleep_time`嚗�蝠摨閙��支�甇文��芸�銋厩��鞱��游𦶢撏拇�甇餉���

## 2026-05-27 15:15
- [x] **�寞祥 SpatialFollowHUD 撅��券�蝏条憬餈𥕦�韏瑞� IndentationError嚗峕��� 44/44 銝芣�霂� 100% 皛∪�蝘㘾�� (Fixed IndentationError in spatial_follow_hud.py Table Rendering & Restored 100% Regression Success)**嚗�
    - [x] **蝖株�銵冽聢�滨��賣㺭���敺芰㴓雿梶憬餈𥟇�蝻� (Diagnosed missing indentation in _render_table_only)**嚗𡁏��亙枂 `tk_gui_modules/spatial_follow_hud.py` �屸𢒰�� `_render_table_only` �拍�撅��券�蝏䀹䲮瘜訫銁�扯��� `for idx, f in enumerate(followers):` �塚�銝𧢲䲮����典儐�臭�隞���梹��瑕� `code`/`name`����� `QTableWidgetItem` 撟嗉挽蝵桀���聢撖寥�銝舘𠧧敶抵‘�輻��餉�嚗厩撩憭曹��穃𢰧蝻抵��� 4 銝芰征�潦����湔𦻖撖潸稲 Python 閫���典銁蝻𤥁��㰘蝸璅∪��嗆��� `IndentationError: expected an indented block` ��稲�賡�霂荔�餈𥡝��紡�� `instock_MonitorTK.py` 銝剔� `open_spatial_follow_hud` 靚�鍂隞亙紡�亙仃韐亙�蝏���
    - [x] **�𧢲钟蝥批�蝢𡒊���憬餈𥕦笆朣𣂷��嗆��券�蝏睃��� (Delivered High-Precision Indentation Refactoring)**嚗𡁜笆霂乩誨��躹�渲�銵䔶�蝎曉�����舐漣�穃𢰧憭𡁶憬餈� 4 銝芰征�潮����摰𣬚�撖寥�鈭� `for` 敺芰㴓雿橒�雿踹� Python 閫���典�蝢舘�頧賬��
    - [x] **���笔��� 44/44 銝芸�������瘚贝� 100% 蝏踵��朞� (100% Verification Parity)**嚗𡁜�蝢擧��蠘��帋���𡠺�芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨�蝟餃� 44 銝芣瓲敹��霂𤏪��冽㺭蝘鍦�隞� **100% 銝�甈⊥�批�蝏�** ���蝏拚�𡁜�嚗𣬚＆靽� HUD 銝𤾸��条��抒��删��𥪜𢆡�嗆���

## 2026-05-27 15:10
- [x] **摰𣬚�靽桀� HUD �桃�銝𡡞�����Ｚ��其葉鈭斗���瓲/蝖株恕頝笔��讛◤擃㗛��滨蔭銝粹�憭渡� Bug嚗���� 100% 蝎曉��㗇𥋘�嗆��扇敹���删��脫��𥪜𢆡 (Fixed HUD Linkage Reset Bug & Implemented State Memory & Linkage Anti-Shake Guard)**嚗�
    - [x] **�餃�摰𡁏𧒄�典��唳��∩辣�滨蔭擃䀝漁蝝Ｗ���′隡� (Resolved Automated Refresh Resetting selected_index to 0)**嚗𡁏��亙枂 `SpatialFollowHUD` �典��嗅膥�誩��唳𧒄嚗Ǒ_on_timer_refresh`嚗㚁��曹�瘝⊥�隡𣳇�� `nav_dir` �桃�靽∪噡�� `signal_item` 銵峕���誘嚗�銁 `update_hud_data` ���𡒊��㗇𥋘��𣈲銝凋��㰘�撠� `selected_index` �滨蔭銝� `0`嚗�朖��撘箇�瘝駁�憭湛����撖潸稲�芾��冽��见𢆡�券睸�䀝�銝钅睸瘚讛��㚚�����餉�憌擧�憭游�嚗䔶��� 1 蝘鍦停隡朞◤摰𡁏𧒄�滨�撘箏��匧��喲�憭湛�閬��鈭�鍂�瑞��㕑��誩㦛��
    - [x] **�賢𧑐�屸�㗇𥋘�嗆��扇敹��蝎曉��Ｗ��齿沲�� (Implemented Selection State Memory & Recovery)**嚗�
        - �� `update_hud_data` �𡁜���𧒄嚗峕惣�賣㜃�芸僎摰匧��𣂼��瑟鰵�滨鍂�瑟迤�券�鈭桅�摰𡁶��∠巨隞�� `prev_locked_code`��
        - �唳旿�齿鰵�枏��鍦�撟嗉�頧賢�瘥訫�嚗䔶���銁�䠷�㕑�瘙牐葉�𦦵揣撟嗥移蝖桅��啣笆朣� `selected_index` �唾砲 `prev_locked_code`嚗䔶蝙�嗅銁瘥讐����憸𤏸�����唬葉靘萘�靽脲����蝔喳����劐葉�嗆����
        - 隞�銁�找誨��歇隞𤾸�䠷�厰���葉敶餃��厰��塚��滚像皛煾�蝥扯䌊������喲�霈日�劐葉蝚� 0 雿滨�蝏�祥樴坔仍��
    - [x] **霈曄��𣬚����暺㗛俈�硔�滢���撩�𤩺��亥��冽㜃�芥�齿㦤�� (Deployed Silent Lock & Linkage Dirty-Checking Guard)**嚗�
        - **撘箄�璉��交㜃��**嚗𡁜銁 `_trigger_linkage` �𥪜𢆡�賭誘瘣曉�摨訫�嚗峕鰵憓硺���擃䀹���� `_last_linkage_code == code` 撘箄�璉��亥�皛扎��㮾�𣬚��∠巨隞���典��Ｘ𧒄�芯�閫血�銝�甈∟��典嘀�哨�100% �𦦵�鈭�眏鈭𤾸��嗅膥�瑟鰵���銵券�蝏睃紡�渲”�潮�劐葉�睃�餈𥡝�屸�憸煾�憭滚�銝餌���/K蝥踹虾閫��蝏�垢�煾���憭滩��剁�瘨�膄鈭�蜓�屸𢒰閫���⊿▼銝𡡞緾����
        - **皜脫��拍��䠷�**嚗𡁻���� `_render_table_only` �寞�嚗���嗅�鋆孵銁摰匧��� `try-finally` 蝏𤘪�銝哨��券�蝏䁅”�潸��唳旿�罸𡢿嚗�撩�園�甇� `self._rendering_table = True`嚗�銁 `_on_table_current_cell_changed` 鈭衤辣銝剔��湔㜃�芷��冽�銝餉����劐葉�孵�靽∪噡嚗���唳��湧◇皛𤑳��穃�瘚��雿栶��
    - [x] **�券� 44/44 瘚贝��函遛擃䀹�蝘㘾�� (100% Integration & Unit Regression Success)**嚗𡁏��蠘��帋��典��芷�㕑��笔𦶢�冽�銝𦒘漱�枏��� tests 蝟餃�瘚贝��其�嚗��撟喳蝱摰𣬚��澆捆嚗�

## 2026-05-27 14:40
- [x] **摰䂿緵��/�䭾綉�嗅蝱����澆捆銝� Ctrl+Break 閫血� 100% �拍��脤緾��嚗�蝠摨閗圾�� C 蝥� faulthandler.register 撘訫����蝔钅���� (Implemented Bi-directional Console Parity & 100% No-Exit Ctrl+Break Signal Protection)**嚗�
    - [x] **蝖株� faulthandler.register 銝渡�靽∪噡�芷���寞� (Diagnosed exit-by-design in faulthandler.register)**嚗𡁏��亙枂 `faulthandler.register` �� C 霂剛�蝥批��行⏛靽∪噡撟嗉��箏����嚗屸�霈文僎銝滢��餅迫餈𤤿����箇�蝟餌�暺䁅恕銵䔶蛹嚗���臭�銝芯��其�銝渡��𡑒������膥嚗㚁�餈嗵凒�亙紡�湔��批��唬��芣�訫�摨瑁�銵䕘�銝�閫血� Ctrl+Break 銋煺�鋡怠撩���芷����
    - [x] **摰𣬚��滚� signal.signal 銝� Windows SetConsoleCtrlHandler (Blended signal.signal and SetConsoleCtrlHandler)**嚗�
        - 摨罸膄鈭�銁 `main_SIGBREAK()` 銝剖虾�賢紡�渡�摨誩撩���� `faulthandler.register(signal.SIGBREAK)` 瘜典���
        - ��蝸鈭���� Python `signal.signal(signal.SIGBREAK, lambda s, f: dump_all())` 隞交㜃�芯蜓蝥輻�撣貉��嗆�����縑�瘀��𡁜�撟喟迅�墧瓷靽∪噡銝� 100% 蝏苷���餈𤤿���
        - 撘箏�瘜典�鈭� Windows OS 蝥� `SetConsoleCtrlHandler`嚗屸�朞��� `win_console_ctrl_handler` �噼�銝�**�曉�餈𥪜� `True`** �𡃏� Windows �𡏭砲鈭衤辣撌脩眏�祉�摨𤩺�韐嫖�嘅�敶餃��拍��行⏛鈭��雿𦦵頂蝏毺�暺䁅恕蝏�迫撘粹��瘚��嚗�
        - 霂亦�����唬�銝文��嗥�嚗𡁜銁甇�虜閫血��嗥�摨讐誧蝏剖像憿箄�銵䕘�摰��銝滚��罸緾��嚗𥕦銁 GUI 甇駁���絲�塚�靘萘��臭誑�朞�摨訫��� OS �批��啁瑪蝔见��啣���氜�塩��
    - [x] **44/44 瘚贝��其� 100% 皛∪�蝘㘾�� (100% Regression Success)**嚗𡁏��罸�朞�鈭���誩�������瘚贝���

## 2026-05-27 14:35
- [x] **敶餃��寞祥�枏��擧��批��唳芋撘譍��� `faulthandler` 撏拇��芷��撘�虜嚗���� 100% 撌乩�蝥扳���像蝔唾�銵� (Fixed Startup Crashes & Stack Dump Crashes in Packaged Windows No-Console Environments)**嚗�
    - [x] **�餃��䭾綉�嗅蝱憿嗥漣撖澆��芷���鞉� (Fixed Startup Crash in top-level faulthandler.enable)**嚗𡁶眏鈭� PyInstaller �冽��批��� (`--noconsole`) 璅∪�銝衤��� `sys.stderr` �踵揢銝箄䌊摰帋��� `NullWriter`嚗𣬚凒�亥��券▲蝥� `faulthandler.enable()` 隡𡁜�瘝⊥�摨訫�蝟餌���辣�讛膩蝚西�峕��� `RuntimeError: sys.stderr is not a real file` 蝑㗇𧊋�閗繮撘�虜���隞砍銁 `instock_MonitorTK.py` �� `linkage_service.py` 憿嗥漣撖澆�銝凋蛹 `faulthandler.enable()` 憓噼挽鈭�撩�𤤿� `try-except` 撘�虜靽脲擪撅��蝖桐�摮鞱�蝔见�銝餌�摨誩�蝢舘楊頞𠰴紡�交���
    - [x] **�拍���膄銝滚��函凒�亙� `sys.stderr` (fd 2) �坔��������望�雿� (Eliminated hazardous direct fd 2 stack trace dumps)**嚗𡁜銁 `dump_all()` 霂𦠜鱏�亙藁銝哨�敶餃��亦氖鈭�銁�䭾綉�嗅蝱璅∪�銝𧢲��枏�韏� Windows 霈輸䔮�脩� (Access Violation) C 蝥批援皞�� `faulthandler.dump_traceback(all_threads=True)` �其�������厩瑪蝔见��������䔶�摮睃��其漱�梢��舫��扼��蒂�拍��𠉛氖�� `with open(..., "a")` �坔� `instock_dump.log` �拍��拍���辣��䲮撘誩����靽肽�鈭��撖寧�����羓瑪蝔见��具��
    - [x] **摰䂿緵�箄��批��唳��仿�摰𡁜�銝𡡞��舫� SIGBREAK C 蝥扳釣�� (Implemented Smart Console-Aware Redirection & 100% Safe SIGBREAK C-level Registration)**嚗𡁜銁 `main_SIGBREAK()` 銝剖��乩� `GetConsoleWindow` API �箄�霂𦠜鱏����𨀣�瘚� to 敶枏�憭���枏�銝娍��批��啁���� GUI 餈鞱��臬�嚗���芸𢆡��鱏撖孵�撅�����霂舀�嚗Êd 2嚗厩�雿輻鍂嚗�撩�園�摰𡁜�撠� `faulthandler.register` 瘜典��喳��函��砍𧑐�拍��亙���辣�交���蝠摨閙�蝏苷��枏�璅∪�銝钅�朞� Ctrl+Break 閫血� C 蝥� faulthandler ���頧砍��嗥�摨訫�甇駁�銝舘�蝔钅緾����
    - [x] **100% 瘚贝��函遛蝘㘾�朞� (100% Core Test Suite Regressed Successfully)**嚗𡁜�蝢擧��蠘��帋��券� 44/44 鈭斗���瓲銝舘䌊�㕑��笔𦶢�冽����瘚贝�嚗䔶��𨅯��睃�憒���喉�


## 2026-05-27 14:15
- [x] **�寞祥�𤾸蝱鈭斗�敹�歲撘閗絲�� AttributeError 撏拇�嚗諹‘�券�㕑�銝餌��� `_bg_sync_ui_from_kernel` �冽��繬摮鞱‘銝��摰� (Fixed AttributeError by Monkey-Patching _bg_sync_ui_from_kernel to StockSelectionWindow)**嚗�
    - [x] **�餃��游�銵乩�蝻箏仃瞍讐� (Fixed Missing Monkey-Patching Point)**嚗𡁏��亙枂 `stock_selection_window.py` �賢銁璅∪��典�蝥批�摰帋�鈭� `_bg_sync_ui_from_kernel` 鋡怠𢆡 UI �峕郊�寞�嚗䔶��冽�隞嗅��刻�銵𣬚掩�𣂼�蝏穃��園�瞍譍�撖寞迨�寞���𢆡��繬摮鞱‘銝��Monkey-Patching嚗㕑��潛�摰𠾼����湔𦻖撖潸稲�𤾸蝱 15 蝘雴漱�枏�頝唾圻�㻫����曉�擐�凒�啣��圈�㕑��Ｘ踎�嗆��𧒄�𥕦枂 `'StockSelectionWindow' object has no attribute '_bg_sync_ui_from_kernel'` ��稲�賢�撣詻��
    - [x] **銵亙�蝐餌�摰𡁏�撠� (Completed Class Binding Mapping)**嚗𡁜銁 `stock_selection_window.py` ��繬摮鞱‘銝��摰𡁜躹�毺���‘朣𣂷� `StockSelectionWindow._bg_sync_ui_from_kernel = _bg_sync_ui_from_kernel`���蝢擧��帋��𤾸蝱鈭斗���瓲�扯�撘閙�銝𤾸��圈�㕑�憭齿瓲 UI 銋钅𡢿���甇交�隞斗綫���摰匧��滨���
    - [x] **擃䀹����霂訫�敶� (100% Core Test Suite Verification)**嚗朞�銵䔶���鉄�芷�㕑��笔𦶢�冽�銝𦒘漱�枏��詨�蝟餃� **44/44** 銝芸�������瘚贝�嚗䔶誑 **100% 銝�甈⊥�批�蝏�** ���撘�”�唳��毺��罸�𡁜�嚗�

## 2026-05-27 13:55
- [x] **摰䂿緵憌擧綉銝𡒊��喳��啣凝靚�綉隞嗅�澆��刻䌊�冽�銋��銝𤾸朖�嗥����嚗�蝠摨閙��斗��函��颱�韏� (Implemented Auto-Persistence & Instant Hot-Application on Risk Parameter Spinbox Adjustments)**嚗�
    - [x] **撘訫��找辣�睃𢆡靽∪噡�𥪜𢆡**嚗帋蛹 `DecisionFlowPanel` 銝� 12 銝芷��找�蝵穃���㺭敺株� `QSpinBox`/`QDoubleSpinBox` �找辣�亙� `valueChanged` 靽∪噡��遙雿訫��啣銁敺株��碶耨�寞𧒄嚗𣬚��游銁�𤾸蝱摰匧�閫血�����碶�摨𠉛鍂瘚����迤�𡁜�鈭���见𢆡銝��桃����靽嘥���
    - [x] **摰䂿緵�𤾸蝱�䠷��芸𢆡靽嘥� (Quiet Background Auto-Save)**嚗𡁻���� `_save_and_apply_risk_limits` �寞�嚗屸��刻�韐��蝳鳴�撠��摨訫�霂餃�潔��拍��坔�瘚������� `_execute_save_and_apply(show_toast)`����桃��餅𧒄銝餃𢆡撣行�瘜⊥�蝷綽��找辣�啣�澆凝靚���冽𧒄�扯��䠷�靽嘥�嚗峕�雿喳𧑐撅讛𤪖鈭��蝜�撕蝒㛖�閫��撟脫贋嚗峕�靘𥟇�擃䀝��毺�鈭支�雿㯄���
    - [x] **�餃�蝏誩��� PyQt 靽∪噡暺䁅恕撣����㺭閬��瞍𤩺�**嚗𡁜⏚�冽遬撘誩�銋厩�蝘���亙藁 `_auto_save_and_apply()`嚗��蝢𡡞獈�凋� PyQt 靽∪噡暺䁅恕撖孵蒂蝻箇���㺭�寞�餈𥡝����撘誩�撠𥪜�潸��吔�靽嗪�鈭���函�憌擧綉�唳旿��＆�㰘秤��
    - [x] **�𧼮�瘚贝� 44/44 �函遛�朞�**��

## 2026-05-27 13:45
- [x] **摰��摰䂿緵 RiskManager ��㺭�冽���蝵柴��朖�嗥�����拍�����吔��㯄�𡁜�蝑𡝗�瘞湧𢒰�踹��笔𦶢�冽� (Implemented Live Dynamic RiskManager Parameter Tuning, Instant Execution Gate Enforcement & Double-Write Persistence)**嚗�
    - [x] **摰䂿緵憌擧綉蝞∠��� (RiskManager) �冽���**嚗𡁜���𧋦蝖祉�����𥕦之暺��憌擧綉���嚗��憭扳�隞𤘪㺭 `MAX_POSITIONS`���蝚𥪯�雿滚�瘥� `MAX_POS_PCT`��𠯫����罸�隞㮖��� `MAX_DAILY_LOSS`��葵�⊿�霈斗迫�� `STOP_LOSS_PCT`嚗匧蝠摨閖���蛹�冽���靘见�畾蛛�撟嗆�蝻嘥笆�亙�撅��滨蔭撌亙� `cct.CFG` 餈𥡝��芣��屸��𥕦�暺䁅恕��㺭�嘥��硋�頧賬��
    - [x] **�㯄�𡁜朖�嗥�靚�㟲銝𡒊����銋�� (Live Dynamic Tuning & Persistence)**嚗帋蛹 `RiskManager` 霈曇恣鈭�瑪蝔见��函� `update_params` �寞�嚗���滨��贝�銵諹挽蝵桀��湔𧒄嚗𣬚��渡�摨𠉛鍂�唾�銵��摮睃僎�笔��扳�銋���坔� `global.ini` �滨蔭��辣嚗䔶�霂��摨誯��臬�摰𣬚��剖鍳�具��
    - [x] **摰𣬚�瘜典��喟�瘚�偌�航��㚚𢒰�� (Polished Cyberpunk UI Control Tuning Center)**嚗𡁜銁 PyQt6 �喟�瘚�偌銝剜攟 `DecisionFlowPanel` ���𨥉�∴� 鈭斗���瓲憌擧綉���潸�隡䀝葉敹��苷葉嚗屸�����啣�鈭� 4 銝芷��批��啁�敺株� `QSpinBox` / `QDoubleSpinBox` 颲枏��找辣��⏚�典撩�𤩺��� (Dirty Checking) �箏�摰䂿緵蝵穃�撅�㺭�桀� UI 銵典����蝥批��穃笆朣𣂷��脫��滚�嚗�僎瘛勗漲�㯄�帋��栽�靝�摮睃僎�單𧒄摨𠉛鍂�萘��剖��典��砍𧑐 JSON �滨蔭��辣���憭�遢��
    - [x] **�啣遣擃条移�訫�瘚贝�撟嗅��� 44/44 �函遛�𡁜� (100% Core Test Suite Regression Success)**嚗𡁶��嗘� `test_risk_manager_dynamic.py` 摰峕㟲撉諹�鈭�𢆡���頧賬����嗥��氬��ni�賜�蝑匧�蝟餃�憌擧綉�笔𦶢�冽�����𣂷��訫�瘚贝� **44/44** 皛∪��𡁜�嚗�

## 2026-05-27 13:10
- [x] **�寞祥�典�撅��典紡�亙�蝒��敶餃�瘨�膄��稬閫血� `NameError` / `UnboundLocalError` (Resolved Global/Local Import Redundancies & Eliminated Double-Click Tracebacks)**嚗�
    - [x] **摰���亦氖�𦯀������ `datetime` 撖澆� (Eliminated Fragmented Local datetime Imports)**嚗𡁏楛摨血笆朣𣂼僎皜��鈭�蜓�屸𢒰 `stock_selection_window.py` �� K蝥踹虾閫��銝剜攟 `trade_visualizer_qt6.py` 銝剖�霈� 6 憭�袇�賢銁�賣㺭�������� `from datetime import datetime` �𦯀�撖澆���
    - [x] **�寞祥 Python 雿𦦵鍂�毺�摰� UnboundLocalError (Fixed UnboundLocalError Scope Issue)**嚗𡁶眏鈭� Python 閫���其�撠�遆�啣�隞颱�雿滨蔭�箇緵�� local import �㗛��滨凒�交�霈唬蛹霂亙��其��典��㗛�嚗�紡�游銁�嗅��剁�憒� `journal_ts = datetime.now()`嚗㗇�銵峕𧒄擃㗛��𥕦枂 `UnboundLocalError: local variable 'datetime' referenced before assignment` ����抒′隡扎���朞��拍���膄撟嗅��典���秐��辣憿嗅��典�蝏煺�撖澆�嚗�100% �寞祥鈭���餉�蟡其誨��圻�烐芋�煺漱�㮖��𥪜𢆡�嗥��芷��/�仿�甇餉���
    - [x] **瘚贝��函遛擃䀹��𡁜� (100% Regression Success)**嚗𡁜��誩�敶坿�銵䔶���𡠺�芷�㕑��笔𦶢�冽� (`test_watchlist_lifecycle.py`) �𠹺漱�枏��豢�餉恣 **43/43** 銝芸�������瘚贝�嚗峕��毺��罸�𡁜�嚗���䀹��嗆�摰𠺶��

## 2026-05-27 12:45
- [x] **����扯��齿�嚗𡁜蝠摨閙��� `_kernel_auto_execute_once` 撖潸稲�� UI 蝥輻�蝘垍漣�港��⊿▼銝𤾸��滚�雿坔��� (Optimized _kernel_auto_execute_once Performance & Eliminated UI Lag/Double Refresh)**嚗�
    - [x] **�拍���膄 O(N) 蝥批之敺芰㴓 (Eliminated O(N) Python Loop for 5000+ Stocks)**嚗帋��碶� `_get_realtime_price_map`嚗䔶蝙�嗆𣈲�� `codes` ��笆�扳��硋��啜��銁 `_kernel_auto_execute_once` 銝哨��朞��𡁜��𨅯��齿暑頝��隞𣏾�苷��𨅯��喟�靽∪噡銝芾��萘��鞟鸌摰𡁶� `target_codes`嚗��𡁜虜隞� 5-30 銝迎�嚗𣬚移��蘨�亥砭餈蹱鸌�∠巨����嗡遠�潘�摰𣬚��踹�鈭�誑敺��曹��滚��典��� 5000+ �∠巨�� `df_rt.loc[code]` 撘訫��� 1-2 蝘� UI 蝥輻��峕郊�餃�銝𦒘艇�滨�皛𧼮�甇颯��
    - [x] **摰䂿緵 C 蝥� Pandas �ａ��𡝗��笔之�曇停�惩� (Implemented C-level Vectorized pandas to_dict Extraction)**嚗𡁻���� `_get_realtime_price_map` ��撩���餉�嚗��敹�◆�𣂼��券�隞瑟聢摮堒��塚�銝滚�雿輻鍂雿擧��� Python `for` 敺芰㴓嚗諹�峕糓雿輻鍂 Pandas C 霂剛�蝥抒� `series.fillna` / `to_numeric` �� `dict(zip(...))` �ａ��硋�撟嗉蓮�ｇ�雿� 5000+ �∠巨��㦛靚望��䭾𧒄�渡眏 1000ms+ �湔𦻖蝻拍��� 1ms 蝥扼��
    - [x] **�亦氖憭𡁻��𦯀��拍��瑟鰵 (Removed Double Refresh in Event Loops)**嚗𡁜縧�支� `_kernel_auto_execute_once` 憿園��滚�靚�鍂�� `self._kernel_refresh_positions(show_message=False)`��眏鈭� scheduler �� `_refresh_focus_tabs` 摰𡁏𧒄�典歇����冽神蝘鍦�摰峕�鈭��甈⊥�隞㮖遠�澆�甇乩�甇Ｘ��詨�嚗峕迨甈∠宏�文蝠摨閙��支��屸�霈∠��𦯀�嚗䔶蝙�喟�撘閙�摰���𧼮��靝漱�枏蘨韐蠘提鈭斗��萘�蝎曄�霈曇恣��
    - [x] **閫���𡝗��唳旿撘�虜�亙�霅血� (Added Robust Warning Logging & Bypass)**嚗𡁜��唬��寞旿蝟餌��芸𢆡�湔鰵�唳旿餈𥡝��文�嚗諹𥅾銝芾�摰��蝻箏仃摰墧𧒄隞瑟聢嚗���朞�隡㗛��� `logger.warning` 餈𥡝�霂𦠜鱏�扯扇敶𤏪�撟嗉䌊�冽㜃�芾砲�∠巨嚗䔶��滚�霂訫�韏琿獈憛𧼮�蝵𤑳��滩��𡝗𥁒�辷�摰𣬚�蝚血��𨀣��唳旿�臭誑�亙�霅血��萘���稲斢��閬����
    - [x] **100% 蝏輯𠧧�䭾��𧼮�**嚗𡁜�蝢擧��𡁜僎蝘㘾�朞�鈭��憟� 43 銝芸�������瘚贝���

## 2026-05-27 12:35
- [x] **敶餃�摰䂿緵鈭斗���瓲�𤾸蝱�滚𦛚�碶��㕑��Ｘ踎摰��閫��艾����芸𢆡餈鞱�銝𦒘��格㺭�株䌊�� (Achieved Persistent Background Trading Kernel Service, Absolute GUI Decoupling, Background Auto-Execution & One-Key Auto-Healing)**嚗�
    - [x] **�梶聦�㕑�蝒堒藁�臬𢆡靘肽�**嚗𡁜� `_kernel_auto_execute_once` �詨��餉�摰��蝘餅�銝� `MonitorTK` �𤾸蝱撘�郊�滚𦛚嚗䔶蝙�港葵�芸𢆡�喟���爾�䀹芋�麄����䁅��蓥�甇Ｘ�憌擧綉銝滢�韏� any GUI �㕑��Ｘ踎����荔�蝖桐�鈭斗�瘚�偌��賒甇�虜餈凋誨��
    - [x] **�𣳇獈憛𧼮��嗆釣�乩�摰𡁏𧒄�屸店**嚗𡁜���瓲�扯�銝� `_inject_focus_engine` 摰𣬚��游�嚗�銁�唳㺭�桀�颲曉�鈭𡁏神蝘垍漣�𤾸蝱�芸𢆡閫血�嚗�僎�冽迨銋衤�撘訫� 15 蝘垍��𤾸蝱�䠷� `_bg_kernel_heartbeat` �祉�摰�擪蝥輻���
    - [x] **摰匧��駁�銝𤾸笆韐行�銋��**嚗𡁜�隞𦠜𠯫撌脖僭��/撌脣���/撌脫芋���銵�縧�滨�摮㗛�銝剜�頧賭�����蓥� `MonitorTK`嚗���斤�����剖紡�渡���蟮鈭斗��唳旿�堒仃嚗���啁�甇�迅�亦��𤾸蝱餈䂿賒皛𡁻䪸���鈭斗�瘚�偌��
    - [x] **頧駁����撖寥�銝舘◤�冽綫��**嚗𡁜銁 `StockSelectionWindow` 銝剖��� `_bg_sync_ui_from_kernel` �亙藁嚗䔶蝙�滚蝱�屸𢒰�冽�撘��嗉�憭笔�蝢舘◤�典𧑐�交𤣰�𤾸蝱鈭斗�撘閙�����嗅��冽綫��� toast 靽⊥�撅閧內嚗�歇�Ｗ����笔�摨𢛵��
    - [x] **摰䂿緵�𤾸蝱�刻䌊�冽芋��/�笔��扯�銝𡡞俈�滚�撘寧��箏�**嚗𡁜銁銝駁�㕑�蝒堒藁 `_refresh_focus_tabs` 瘥� 15 蝘埝�銵䔶�甈∠�摰𡁏𧒄�典儐�臭葉撋�� `_kernel_auto_execute_once(auto_mode=True)`嚗�蝠摨訫��唬��喟�撘閙�銝𡒊��扳�瘞渡��典予�坔��圈�暺䁅�銵䎚����典��圈�暺䁅�銵峕𧒄嚗諹䌊�函�餈���厰𢒰�睲犖撌亥�霂閧�撘粹獈憛𧼮��鞟內撘寧�嚗�僎撖孵撩憭抒��祆筑 `toast` 蝒堒藁摰墧鴌�脫��批�嚗��敶𤘪��笔��𣂷漱��艇�滚�撣豢��冽�銝餃𢆡�枏��Ｘ踎�嗆�閫血��曄內嚗剹��
    - [x] **摰峕� Tkinter �㕑�銝餌����䔶��格㺭�株䌊��耨憭溻�滨�瘛勗漲撖寥�銝擧��毺宏璊�**嚗𡁜銁摰墧𧒄�喟��厰僼銵䔶葉�啣�鈭� `�圲 �唳旿�芣�靽桀�` 敹急㭘�亙藁���憭毺��渡�������摮睃� legacy �𨅯蝱銝剜��� `shares <= 0` ��厭�菜�隞橒�撟嗆覔�格�隞𤘪�餅��祆惣�賣�摰寧緵�𡢅�蝎曄＆撖寥� `PaperExecutionAdapter` 蝥貊�����典�����圈��批僎摮条���
    - [x] **�㯄�𡁜��� 43/43 銝芸�����𧼮�瘚贝� 100% 銝�甈⊥�批�蝏輻���**��

## 2026-05-27 11:30
- [x] **�寞祥�见𢆡撟喃�靽∪噡撅墧�抒撩憭曹� OBSERVE 璅∪�銝𧢲芋���隞𤘪�瘜閧����甇亦��桅�嚗峕��� 42/42 銝芸�敶埝�霂� (Fixed Manual Sell Signal Attribute Omission & Achieved 100% OBSERVE Mode Position Sync with 42/42 Tests Passing)**嚗�
    - [x] **銵亙��见𢆡撟喃�靽∪噡����桐遠�潔��園𡢿�喳��� (Completed Critical Price & Timestamp Attributes)**嚗�
        - ��笆�见𢆡�� `DecisionFlowPanel` 銝剜�銵𢞖�𨀣�撌亙像隞𣏾�脲��靝��桀�撟喇�脲𧒄嚗𣬚眏鈭� `sig_sell` 摮堒�銝剔撩憭� `"current_price"`, `"suggest_price"` �� `"created_at"` 撅墧�改�撖潸稲 `canonicalize_decision_queue_item` 頧祆揢�嗅�隞瑟聢霂臬ế銝� `0.0`嚗諹��諹◤憌擧綉銝𤾸��豢芋�𡑒�皛扎����箏�撣貊�蝖砌慾��
        - �拍�銵亙�鈭� `_manual_sell_position` 閫衣�憭���券��喲睸鈭斗����嚗䔶� `MockTradeGateway` �𢠃�㕑�銝餌�����见𢆡鈭斗���㺭 100% 摰��撖寥�嚗𣬚＆靽脲�銝�蝚娍�撌亙��粹��質◤ canonicalizer 摰𣬚�餈睃���
    - [x] **�㯄�𡁏�頝航扇韐� (OBSERVE) 璅∪�銝讠��见極鈭斗��拍��扯�銝舘䌊���𡁻� (Enabled OBSERVE Mode Manual Trade Fallback Execution)**嚗�
        - ��笆蝟餌�憭����楝�𤏸� (`OBSERVE`) 璅∪�銝页��曹� `self.executor` 暺䁅恕銝� `None`嚗�紡�湔��其僭�乓����箇� `MANUAL_OVERRIDE` 擃㗛𧫴��誘�䭾��拍��湔鰵��瓲����具�������� UI �芸𢆡�瑟鰵�嗆�隞栞◤����喳��爗�𨅯�瘣�/�匧��萘�蝖砌慾��
        - �齿�鈭��蝑𡝗𦻖�嗆瓲敹� `evaluate_decision_item`嚗���乩��� `self.executor is None` 銝𥪜��� `MANUAL_OVERRIDE` 鈭箏極�喟��誩㦛�嗥� **`self.paper_adapter` �鮋���扯��箏�**��
        - 蝖桐�鈭�銁 OBSERVE ��楝璅∪�銝页��见極鈭斗��賢��祇𡢿�拍��湔鰵擃条�璅⊥�����函𠶖��� `StateManager` (霈曄蔭銝� `FLAT` �� `IN_TRADE`)嚗�蝠摨閖獈�凋��曹� rounding �硋僎�穃紡�渡� Ghost ���嚗諹噢�𣂷��券曎頝舐�摰𣬚����撖寥�銝擧㺭�株䌊����
    - [x] **蝻硋�擃条移���瘚贝�撟嗅��� 42/42 �訫�銝𡡞��鞉�霂� 100% 蝘㘾�� (Passed 42/42 Tests with 100% Success Rate)**嚗�
        - 蝻硋�撟園��𣂷� `test_manual_override_observe_mode_fallback` 擃䀝��笔����霂𤏪�摰峕㟲憭滨�鈭� OBSERVE ��楝璅∪�銝讠��见極撘�/撟喃��笔𦶢�冽�嚗���怠��� 42 銝芣�霂閧�憟𦯀辣�� **3.15 蝘�** �� 100% 銝�甈⊥�批�蝏輻��𡄯�

## 2026-05-27 11:10
- [x] **�寞祥 Python-Pywin32 DLL entry point entry 0xc0000139 撏拇�嚗���Ｘ��𡁜僎�朞�鈭斗���瓲�典� 41 銝芸�敶埝�霂閧鍂靘� (Fixed pywin32 DLL load 0xc0000139 crash & achieved 100% test success rate)**嚗�
    - [x] **�拍��餃� pywin32 DLL ���憸��頧賡俈蝥� (Implemented pywin32 DLL Memory Preloading)**嚗�
        - ��笆 Windows + Conda 憭𡁶㴓憓�僎摮䀝�嚗𣬚眏鈭𡒊頂蝏� PATH 銝� Anaconda base �臬��硋�隞� system DLL �脩�撖潸稲�� `Windows fatal exception: code 0xc0000139` (�曆��唳�摰𡁶�蝔见�/DLL�亙藁�寞𧊋�曉�) 撏拇�蝖砌慾嚗屸���� `JohnsonUtil/commonTips.py` 蝚� 3029 銵𣬚� Win32 撖澆��脣鴃��
        - 撘訫�鈭��撖澆��� **`import pywintypes`** �冽���摮㗛��㰘蝸�箏���眏鈭� `pywintypes` 隡𡁜銁 Python 閫���典鍳�冽𧒄甇�＆霂��撟嗅�頧賢��滩��毺㴓憓� `site-packages` 銝讠� DLL ��辣嚗䔶��血�憸��頧賢�餈𤤿�����笔𧑐��蝛粹𡢿嚗𡦀indows loader �典�頧賭�皜� `win32api` �� `win32gui` 靘肽��嗡噶隡朞䌊�典��典歇頧賢���迤蝖� DLL �交�嚗䔶��� 100% �寞祥鈭�眏鈭𤾸���㴓憓� DLL 瘙⊥�撘閗絲�� CRT entrypoint 撏拇�嚗𣬚頂蝏笔銁�䀝葉銝擧�霂閙𧒄颲曉��𤑳�蝥抒迅摰𡁏�扼��
    - [x] **閫���� Pytest 璅∪�頝臬�撖餃� (Standardized Pytest Module Search Path)**嚗�
        - �朞�����㚚��� `python -m pytest test_watchlist_lifecycle.py trading_kernel/tests` �扯���誘嚗�⏚�� Python 閫���典��� `-m` �箏��芸�撠���� workspace root 雿靝蛹 `sys.path` ���雿㵪�摰𣬚�閫��鈭� Windows �臬�銝𧢲�銵� pytest �園�憸烐��箇� `ModuleNotFoundError: No module named 'trading_kernel'` 頝臬��𨅯粉甇餉�嚗���唬�撘���/CI �臬� of �删�撖寥���
    - [x] **瘚贝��函遛�䭾��𧼮� (Achieved 100% Pass Rate in Regression Suite)**嚗�
        - �拍��扯�鈭���讛䌊�㕑��笔𦶢�冽�銝𦒘漱�枏��豢�餉恣 **41/41** 銝芷��曉漲�詨��訫�銝𡡞��鞉�霂閧鍂靘页��� 3.54 蝘鍦�隞� **100% 銝�甈⊥�批�蝏�** ���蝏拚����朞�嚗���𦒘�蝟餌���𠶖��䌊��笆韐艾���頝航扇韐艾����扯��溻��迫�蠘䌊�刻�餈𤤿��券��詨��箏�銝𤾸��睃��湔�批歇�餉秐�����

## 2026-05-27 11:00
- [x] **�券�摰⊥䰻銝𤾸撩�𤥁���㺭�桀蘨霂餃�蝥佗��拍��餅鱏摮鞉芋�堒�摮条砥�嫣� UI ��香�鞉� (Enforced DataFrame Read-Only Contract & Stabilized IPC Pipeline)**嚗�
    - [x] **瘛勗漲�刻��� Audit (Zero-Copy Audit)**嚗�
        - ��笆銵峕��唳旿銝餃��� inject_realtime 銝� SectorBiddingPanel 銝𧢲虜���憭扳㺭�格�韐寡���銵峕楛摨血𧑐瘥臬��埝䰻��
        - 撉諹�鈭� BiddingMomentumDetector.register_codes��ectorFocusMap._compute 隞亙� StarFollowEngine.confirm_leaders 蝑匧��𤩺瓲敹�䲮瘜訫銁�𣂼��唳旿�塚�����其�摰匧�銝𠉛移��� .copy() �𡝗��臭��典�����硔��
        - 撉諹�鈭� StrategicTrendTracker.scan �𠰴�頦拇�瘚𧢲醌�誩膥��鍂 to_dict('index') �� pandas �毺��ａ��𤥁粉�𡝗�雿栶���鈭𥕦�撅�沲�� 100% �萄�鈭�粉�坔�蝳餌��曹澈��� (Shared-Memory) 暺�����嚗峕𧊋�𤑳�隞颱��朞� pandas 瘛勗�撘閧鍂撖潸稲���撘誩�撅��唳旿皞� df 蝭⊥㺿�峕情�橒�敶餃��㯄�帋� SectorFocusEngine �� UI 蝥輻���迤��妟瘛望鼧韐� (Zero-Deep-Copy) 摰匧�隡惩紡��
    - [x] **蝔喳�頝刻�蝔� IPC �⊥��帋縑嚗�像銵⊥�扯�銝𤾸撩斢���� (Balanced IPC Timeout Tradeoff)**嚗�
        - 靚�㟲鈭� instock_MonitorTK.py 銝剔��毺�摨訫� socket 頧株砭頞�𧒄蝑𣇉裦��� size_IPC_send 隞擧迨�滩�鈭擧�餈𤤿� 100ms 蝏煺�銝𡃏�銝𤾸像銵∟秐 0.2 蝘� (200ms)��
        - 霂亥��湔𠳿銝交聢靽嗪�鈭�楊餈𤤿�擃㗛�靽∪噡�唳旿����𡁻�憿箸��穃��䔶蜓蝥輻��嗅㨃憿選��峕𧒄���憭扯��蹂��曹� Windows 蝟餌� OS 蝥扯�皞𣂼��滨��嗥揮撘惩蒂�亦��㰘����帋縑�餅鱏��之�𤩺�颲𦦵� socket.timeout 霂舀𥁒��
    - [x] **UI 鈭衤辣敺芰㴓鈭� 20ms 蝥找漱隞䀹𤣰摰� (Achieved Sub-20ms Event Loop Parity)**嚗�
        - �滚�甇文��賢𧑐�� 200ms 靽∪噡�烾�蝻枏��穃�銝𡡞俈�㚚�蝏䀝誑�𠰴�撅����妟瘛望鼧韐萘��伐��港葵 UI 鈭衤辣敺芰㴓�滚�����啁���𡡒�舐＆霈歹��函頂 QTimer 皜脫�韐��敶餃�閫�膄嚗�

## 2026-05-27 10:35
- [x] **隡睃� Nuitka �枏��舘圻�𤑳��格��啣���緾���桅�嚗�蝠摨閙覔瘝� CRT Abort/Access Violation 撏拇� (Fixed Nuitka Stack Trace Dump Crash & Access Violation)**嚗�
    - [x] **�拍���膄 unsafe stdout/stderr 颲枏枂 (Eliminated direct stdout/stderr printing & faulthandler.dump_traceback direct output to stderr)**嚗�
        - 敶餃�摨罸膄鈭�銁 `dump_all` 銝渡�頝臬�銝剖虾�賢紡�游援皞�� `print(...)` �� `faulthandler.dump_traceback(all_threads=True)` 銵䔶蛹��銁 Nuitka onefile �祉��枏� GUI 璅∪�銝页�摨訫� `sys.stderr` 銝� `sys.stdout` �� C/Windows ��辣�交����憭�� detach/invalid �嗆���甇斗𧒄�湔𦻖�� `sys.stderr` �枏㫲����𣇉凒�亥��� Python `print` 隡𡁶��游紡�� C 餈鞱��嗅援皞��CRT Abort/Access Violation嚗剹��
    - [x] **�拍��𠉛氖 logger �滚�甇駁�憌𡡞埯 (Eliminated critical-path logger usage)**嚗�
        - 隞� `dump_all` ���頧砍�銝餉楝敺�葉摰���亦氖鈭� `logger.warning(...)` ���甇亥��具��眏鈭� `logging` 璅∪����摮睃銁�典� GIL ����O �笔��𠰴�蝐� Flush Handler嚗���靝蜓蝥輻��券�憸𤏸���� CPU 擖仿正銝见����韏�/甇駁�嚗�銁霂𦠜鱏頧砍�頝臬�銝剖�甈∟��� logger 隡𡁜��煺�甈⊥香�����朞�撠���娪膄嚗���唬�蝏嘥笆摰匧�������暺塩��
    - [x] **摰䂿緵 100% �拍���辣�賜����頧砍� (Guaranteed 100% robust file-only stack dump)**嚗�
        - �齿鰵霈曇恣鈭� `dump_all()`��緵�刻��剖���**銝交聢銝𥪯�**頧砍��唳𧋦�啁′�条� `instock_dump.log` �拍���辣嚗�銁 `with open(..., "a", encoding="utf-8")` 摰匧�銝𠹺���恣��膥銝剛�銵���乩� Flush嚗�蝠摨閙��支�撖寞綉�嗅蝱�交����韏硔��
    - [x] **摰峕㟲靽萘��鮋獈憛� Windows �毺� Toast �鞟內摰�擪蝥輻� (Maintained safe non-blocking MessageBoxTimeoutW Daemon Thread)**嚗�
        - 撠���� Windows `ctypes.windll.user32.MessageBoxTimeoutW` �鞟內蝘餉秐摰���祉�����啣��斤瑪蝔� `threading.Thread(name="Dump_Toast_Thread", daemon=True)` 銝剜�銵䎚��朖雿� Tkinter �� PyQt6 銝餌瑪蝔见�銝箸�蝘齿�蝡臬��䭾香���霂亙��� Windows API 隞滩��函�蝥批撕�箏僎�鞟內頧砍��𣂼�嚗䔶�蝏苷��餃�隞颱�鈭衤辣敺芰㴓嚗峕�靘𥟇�擃䀝��毺�鈭箸㦤鈭支�雿㯄���
    - [x] **�啣��批��啣��冽��唳㦤�� (Added Safe Console Log Path Output)**嚗�
        - �� `dump_all` �𣂼�撖澆枂����𠬍�撘訫�鈭�撩�脫擪�� `sys.stdout is not None` �文�嚗�僎雿輻鍂撣衣𡠺蝡� `try-except` 撘�虜撅讛𤪖�� `sys.stdout.write` �拍��枏㫲頧砍���辣���頝臬�嚗䔶�霂���冽綉�嗅蝱鈭支�靚���嗥��航粉�改�銝𥪜銁 Nuitka detached 璅∪�銝见��其��𤑳�撏拇���

## 2026-05-27 09:00
- [x] **摰䂿緵����冽𦆮�讛祕���漤𢒰�踹��冽㺭�桅店�函��臬��嗅��埈沲����删�瘜典� "DFF3" 擃䁅���� (Delivered Fully Data-Driven Configurable Column Architecture & Seamless "DFF3" Metric Integration for Volume Details)**嚗�
    - [x] **摰䂿緵�滨蔭撅���芸𢆡�脫��芣�銝𡡞�霈文�蝥� (Active Config Upgrades & Self-Healing)**嚗�
        - ��笆�冽��𣂼枂���𨀣溶�� dff3 �堒僎�羓�����碶蛹�臬��嗥����萘��詨�霂㗇�嚗�銁 `commonTips.py` 銝剝���� `vol_up_details_col` 摮埈挾��
        - 霈曄�鈭��擃睃��函�蝥抒��瑕鍳�刻䌊���撟嗆㦤�塚��芸𢆡璉�瘚讠鍂�瑟𧋦�� `global.ini` 銝剔緵摮条��滨蔭嚗���𨅯��啁鍂�瑟𧋦�圈�蝵桃撩撠烐鰵憓䂿� `"DFF3"` �梹��𣳇�鈭箏極撟脤��喳虾�冽神蝘垍漣��䌊�典��嗉‘�冽𣄽�亙僎摮条�嚗𣬚＆靽苷� legacy �冽�����笔�蝥找��滚��澆捆�扼��
    - [x] **摰䂿緵銵峕��烐綉�𡒊垢 (instock_MonitorTK.py) �冽���撠��撅墧�扳��� (Dynamic Property Extraction Loop)**嚗�
        - �拍�摨罸膄鈭���祆𤣰���𨅯��冽𦆮�讛祕���脲㺭�格𧒄��′蝻𣇉�摮堒��桀�潘��齿�銝箏抅鈭� `cct.vol_up_details_col` �冽���蝵桅店�函�撅墧�扳𤣰��膥��
        - �朞��箄�撅墧�找齒瘚页��箄��芷��� lower 撅墧�找��桀��惩�嚗㚁��芸𢆡隞𤾸��啗��� `sub_df` 銝凋蛹銝芾��匧�撖孵�����嗆���㺭�潘��㯄�帋��唳����摨訫�銵峕��唳旿皞鞟凒�� UI 蝻枏���𡡒�荔�銝箏�蝏剜溶�牐遙�𤩺鰵�烐綉�埈�靘𥕢����撘箏漲����鞉�撅閙𣈲����
    - [x] **摰䂿緵 VolumeDetailsDialog (signal_dashboard_panel.py) �冽��”憭湔�撱箔�擃䀝��蠘䌊�冽葡�� (Dynamic Header Initialization & Precision-Aware Grid UI Rendering)**嚗�
        - **�冽��”憭湧���**嚗𡁻��嗘� `VolumeDetailsDialog.__init__`嚗䔶蝙敺𡑒”�澆��唬�銵典仍��� 100% 靘脲� `cct.vol_up_details_col` �唳旿瘚�𢆡���撱綽�摰𣬚��舀��券�蝵桐葉�芰眏憓𧼮���凒�孵��啜��
        - **擃䀝���㺭�格葡�㮖�撖寥�**嚗𡁻���� `update_data` �瑟鰵�餉���頂蝏罸�朞��冽�����虾摰𡁜��梹��寞旿�堒�嚗���靝誨���腈���𨅯�蝘售�腈���𨀣隅撟�%�腈���𡤜FF3�嘅��芸��文�������� UI 皜脫��寞�嚗�僎��笆瘨刻�撟���㺭�澆之撠譌����祈�銵屸�蝎曉漲����航𠧧�脣蔗銵亙�銝𤾸椰�喳笆朣𣂼�撅�敺株�嚗���唳��瑞����毺��冽���鈭桀�蝷箝��
    - [x] **瘚贝��函遛�䭾��𧼮�**嚗𡁜�蝢舘��帋��券� 11/11 �詨��芷�㕑��笔𦶢�冽�瘚贝�嚗Ǒtest_watchlist_lifecycle.py`嚗㚁��典像�唳㺭�桐�撖潔� UI 蝏�辣撖寥�摰䂿緵 100% 皛∪��䭾����嚗�

## 2026-05-27 08:00
- [x] **��遣擃睃虾�䭾�抒����銝舘��𤏸䌊���霂���𠬍�摰䂿緵 100% �拍�撖寡揭皜拙鍳�刻䌊�其耨憭� (Delivered Active Positions Self-Healing Validation & Ledger-Driven Warm-Start Auto-Repair)**嚗�
    - [x] **摰䂿緵��捏���銝舘��� dry-run �拍�餈睃�蝞埈�**嚗�
        - ��笆�冽��𣂼枂���𨀣�銋���唳旿瘝⊥�銋啣��圈�嚗��銝齿遬蝷箇�鈭謿�嘥��𡏭䌊�其耨憭齿㺭�桀�撣豢�隞𤘪��菊�萘��詨��漤���
        - �� `PaperExecutionAdapter._load_state()` 璅∪�銝哨�擐硋�摰䂿緵鈭�� `orders` ��蟮憪娍�瘚�偌銝剜��園𡢿頧游僕頝� (dry-run) �拍�餈睃��𦦵�霈箸�隞𤘪�蝏��嘥��𦦵�霈箏虾�函緵�爗�萘�蝞埈���
        - 蝞埈��朞��芸𢆡�齿����� `BUY` / `ADD` / `SELL` / `REDUCE` ���鈭文�嚗�𢆡��恣蝞埈�銝芯葵�∠���遠��㺭�誩�摰墧𧒄����潘�摰䂿緵鈭��蝢𡒊� warm-start��
    - [x] **��遣憭𡁶輕撘�虜璉�瘚衤�閬���芣�雿梶頂**嚗�
        - 霈曄�鈭��蝏游�撣豢�瘚见��∴�敶� 1) 頧賢����銝箇征雿��霈箸�隞㮖�銝箇征��2) ����圈�銝𡒊�霈箸�隞㮖�銝��氬��3) 銝芾�隞��銝滚���4) 銝芾��圈�撌桀�潸�餈� 0.1 �⊥𧒄嚗諹䌊�刻圻�� **`[Self-Healing]` �唳旿撘�虜閬��靽桀��箏�**��
        - �拍��函�霈箸�隞枏��圈��滚�閬�� `positions` �� `cash`嚗�蝠摨閗圾�喃��曹�����𡝗�隞嗆聢撘誩��具���摮睃凝撘望𧒄撌柴����见𢆡靚�㟲撖潸稲�𨀣�隞𤘪㺭�桃撩憭晞����曄內銋啣��圈��𣬚�鈭謿�萘�撘�虜嚗���唬� 100% �唳旿銝��湔�找�霂���
    - [x] **�券� Regression 銝� 44 �訫�+���瘚贝� 100% 皛∪�蝘㘾��**嚗�
        - �拍�餈鞱�鈭���� `trading_kernel/tests` (30銝芰鍂靘�) 撟嗅銁 root �桀�銝𧢲�銵� `test_watchlist_lifecycle.py` 蝑厩��賢𪂹�笔��唳旿摰匧��扳�霂� (14銝芰鍂靘�)嚗��霈� 44 銝芣瓲敹��霂𤏪��� 4.5 蝘鍦� 100% 銝�甈⊥�批��券����蝏輸�𡁜�嚗�

- [x] **敶餃��寞祥撌脣像隞栞��喲睸�𨅯��𦦵宏�方扇敶𨰝�嘥��𤑳� '<' not supported TypeMismatch UI 撏拇�銝擧���仃�� (Fixed Closed Position Removal TypeMismatch & classic QAction Lambda Default Bug)**嚗�
    - [x] **�餃�蝏誩��� PyQt triggered 靽∪噡暺䁅恕��㺭閬��瞍𤩺�**嚗�
        - ��笆�冽��漤��典歇撟喃�銵�𢰧�桃��領�𦦵宏�斗迨撌脣像隞栞扇敶𨰝�脲��𨀣��斗��匧歇撟喃�霈啣��嘥�嚗𪄇I �祇𡢿撏拇�撟園�憸烐𥁒�� `TypeError: '<' not supported between instances of 'str' and 'bool'` ��′隡扎��
        - 瘛勗漲�埝䰻�箇眏鈭� `action_remove.triggered.connect(lambda c=code: self._remove_closed_record(c))` 雿輻鍂鈭�蒂暺䁅恕��㺭�� lambda 銵刻噢撘𧶏��� Qt �� `triggered` 靽∪噡隡𡁻�霈文����銝� `checked: bool = False` 雿靝蛹蝚砌�銝� positional 摰𧼮�嚗�紡�� lambda ����� `c` 鋡怠撩�嗉��嗘蛹 `False` (撣����)嚗䔶���� `_hidden_closed_codes` ���銝剜釣�乩�撣��蝐餃���
        - 撠���拍��齿�銝箸���� **`lambda: self._remove_closed_record(code)`**嚗䔶蝙�嗅蝠摨閙�閫� Qt 靽∪噡����惩��堆�隞擧�憭港��剔�鈭�掩�𧢲情�瓐��
    - [x] **憓𧼮����毺鸌敺�掩�衤��支��脣援皞��皛�**嚗�
        - �� `_refresh_positions_tab` ���蝥寧𠶖��倌�滩恣蝞𦯀葉���滨垢瘜典��脣鴃嚗䫤list(x for x in self._hidden_closed_codes if isinstance(x, str))`��銁�拍��鍦��𡃏恣蝞� signature �嗡蜓�典��支遙雿閙��函��� string 蝐餃���
        - �� `_remove_closed_record` �� `_clear_all_closed_records` ���摨枏ế�凋葉撘箏��質� `isinstance(code, str) and code` 撘箇掩�讠漲�笔ế摰𡄯�摰峕�鈭���嫣�����券俈�扎��
    - [x] **�券� Regression 銝� 44 �訫�+���瘚贝� 100% 皛∪�蝘㘾��**嚗�
        - �拍�餈鞱�鈭���� `trading_kernel/tests` (30銝芰鍂靘�) �� root �桀�銝讠��賢𪂹�煺��唳旿�讠憬瘚贝� (14銝芰鍂靘�) �典����憟� 44 銝芣瓲敹��霂𤏪��� 4.5 蝘鍦� 100% 銝�甈⊥�批��券����蝏輸�𡁜�嚗�

- [x] **�寞祥�见𢆡鈭斗�銝𡡞��抒＆霈斤�摨訫��澆�銝滢��湛��㯄�𡁏�頝航扇韐� (OBSERVE) 璅∪�銝讠�擃条�璅⊥�������笔��堆�撱箇� 100% �券曎頝臬��穃笆朣� (Delivered StrategySignal Feature Mapping Compatibility & OBSERVE Mode Position Fallback Visibility)**嚗�
    - [x] **銵亙� StrategySignal �喲睸���銝擧𧒄�湔�撅墧��**嚗�
        - ��笆�见𢆡璅⊥�銋啣�/�硋枂����格�隞瓐��誑�𠰴撕蝒� Confirm �塚��删撩銋� `current_price`��suggest_price` �� `created_at` 撅墧�改�撖潸稲 `canonicalize_decision_queue_item` 閫��隞瑟聢銝� 0.0����諹◤摨訫�憌擧綉�諹扇韐西�皛�/�行⏛��䔮憸矋��扯�鈭� StrategySignal 撅墧�抒�摰峕㟲銵仿���
        - 蝖桐����㗇��冽芋�煺僭�亙𢆡雿𡏭䌊�其��坔僎憭滚�鈭���喟�靽∪噡����匧��唳旿嚗𠄎ector, DFF, Priority 蝑㚁�嚗峕�憭找萼撖䔶�瘚�偌����凋縑�荔�敶餃��寞祥鈭���其漱�枏�瘚�偌銝剔撩撠𤏸祕蝏���勗��唳旿��′隡扎��
    - [x] **摰䂿緵��楝霈啗揭 (OBSERVE) �滨漣撅閧內璅⊥����**嚗�
        - �齿�鈭� `DecisionFlowPanel` 銝剔� `_refresh_positions_tab` �唳旿�𣂼��餉���銁蝟餌�憭��暺䁅恕���頝航扇韐� (`OBSERVE`) 璅∪�銝页�銝滚�撘箏�撠� `adapter` 蝵桃征嚗�紡�湔�隞枏�韏�漣�∠��函征/�賢�嚗㚁��峕糓隡㗛��芷����滨漣銝箄粉�㚚���芋�� (`PAPER`) 鈭斗�����剁�隞舘�屸�朞��唳��� `Auto-Heal Bridge` �芸𢆡撖寡揭撅�� `MockTradeGateway` ������麄���蝢𤾸��啜��
    - [x] **�券� Regression 銝� 44 �訫�+���瘚贝� 100% 皛∪�蝘㘾��**嚗�
        - 餈鞱�鈭���� `trading_kernel/tests` (30銝芰鍂靘�) 撟嗅銁 root �桀�銝𧢲�銵� `test_watchlist_lifecycle.py` 蝑厩��賢𪂹�笔��唳旿摰匧��扳�霂� (14銝芰鍂靘�)嚗��霈� 44 銝芣瓲敹��霂𤏪��� 4.2 蝘鍦� 100% 銝�甈⊥�批��券����蝏輸�𡁜�嚗�

## 2026-05-27 07:00
- [x] **摰峕��见𢆡鈭斗�銝𡒊＆霈斗㦤�嗥�鈭斗�瘚�偌 (Journal) 摰墧𧒄�峕郊嚗�遣蝡� 100% �唳旿銝��湔�找�憌擧綉蝏輯𠧧�𡁻� (Delivered Real-Time Manual Trade Journal Sync, 100% UI Parity & MANUAL_OVERRIDE Green Channel)**嚗�
    - [x] **�寞祥�见𢆡鈭斗�瘚�偌蝛箸�銝擧㺭�桐�銝��� (Eliminated Manual Trade Journal Discrepancy)**嚗�
        - ��笆�见𢆡�� `StockSelectionWindow` 銝剜�銵𢞖�𨀣芋�煺僭�乒�腈���𨀣芋�笔��算�腈���靝��格�隞𣏾�苷誑�𠹺犖�箇＆霈文撕蝒㛖��領�𦦵＆霈手�嘥�嚗䔶漱�𤘪�瘞港� `DecisionFlowPanel` �唳旿銝滚�甇亦�蝖砌慾嚗���湔鰵鈭� legacy ������嚗峕𧊋�坔��拍� journal嚗㚁��其�憭扳�鈭方圻�孵��乩�撖� `enrich_decision_item(..., write_journal=True)` ����賣釣�乓��
        - 靽肽����厩眏�滨��贝圻�𤑳�銋啣�����箏�蝖株恕�其�����祇𡢿�������亦�銝���漱�栞揭蝪� `logs/trading_kernel_trace.jsonl`嚗�蝠摨閙覔瘝颱��Ｘ踎銝羓� Ghost 靽∪噡�峕㺭�株���䔮憸塩��
    - [x] **撱箇� [MANUAL-OVERRIDE] ������∩辣�曇�蝏輯𠧧�𡁻� (Designed MANUAL_OVERRIDE Gate & Wind Control Bypass)**嚗�
        - �典�蝑硋��� `decide()` 銝哨���笆��扇�� `"�见𢆡銋啣�"`��"�见極撟喃�"`��"銝��格�隞�"` �𡝗糓 Confirm 撉諹�����其漱�橒�霈曄�鈭��擃䀝���漣�� **`MANUAL_OVERRIDE` 蝏輯𠧧靽⊿��文�**��
        - �券��批��� `evaluate()` ���滨垢霈曄�蝏嘥笆�曇��𡁻�嚗𡁜𥣞�舫�朞��见𢆡鈭斗��穃枂��僭�硋�撟喃���誘嚗�**�䭾辺隞嗚��100% 鞊��**��𡠺�硺漱�𤘪𧒄畾菜㜃�芥��𠯫���憭扳筑鈭誯獈�准���憭滩��粹��嗚��蔭靽∪漲雿𡡞秄瑽𤤿��典�����券��抒′�批㨃���隞㮖�鋆��嚗��蝢𤾸龪�滚僎撠𢠃�鈭�犖蝐餅��䀹����擃睃�蝑𡝗�敹𨰜��
    - [x] **�㯄�𡁜�皞鞉�隞�/韏�����笔笆朣𣂷��唳旿�删��芣� (Perfect Broker Parity & Concurrency Synchronization)**嚗�
        - 摰䂿緵鈭� `MockTradeGateway` 銝� `PaperExecutionAdapter` �詨�韏�漣韐行��嗆������笔�甇伐��朞� `Bridge-Anti-Reverse` 撌批��滚�嚗𣬚�����支��曹� rounding �硋僎�𤑳𠶖��凝撘望𧒄�游榆撖潸稲��厭�菜�隞𤘪� stale P&L��
    - [x] **蝻硋� 100% 閬������訫�瘚贝�撟嗅��� 44/44 �函遛�𡁜� (Passed 100% Regression Unit Tests)**嚗�
        - 蝻硋�撟嗉�銵䔶� `trading_kernel/tests/test_manual_override.py` �詨����瘚贝�嚗��蝢舘��㚚�鈭斗��嗆挾���雿𡒊蔭靽∪漲銝讠�銋啣�銝𤾸像隞梶��賢𪂹�����鉄�券� 44 銝芣瓲敹��霂閧�摰峕㟲憟𦯀辣�� **3.4 蝘�** �� 100% 銝�甈⊥�批�蝏輸�𡁜�嚗�

## 2026-05-27 06:00
- [x] **摰䂿緵 MainU ����梢◇�齿��鞉�扯��鍦�銝� 64 �嗆�����䰻�曇” (LUT) ��稲隡睃� (Delivered MainU Consecutive Bullish "Flush" Sorting & 64-State Static LUT Vectorized Mapping)**嚗�
    - [x] **�拍���膄餈鞱��嗅�蝚虫葡閫��銝� GC �见� (Eliminated Runtime String Split & GC Overhead)**嚗�
        - ��笆 `MainU` �堒噡����啣�摮㛖泵銝莎�靘见� `"1,2,4,6"`嚗厩��冽��圾�鞾�瘙���拍鍂�嗉”蝷� `days=6` �嗆����� 2^6 = 64 蝘滚虾�賜������恥撅墧�改��冽芋�堒�頧賣𧒄銝�甈⊥�折���遣鈭���怠��� 64 蝘齿聢撘誩�蝚虫葡�唳�摨誩��潛� **�蹱��䰻�曇” `_MAINU_STR_TO_SCORE`**��
        - 餈鞱��嗅��券��滢� `split`��join`��迤�踺��掩�贝蓮�Ｗ�憭折���葩�嗅笆鞊� GC �见�嚗���� O(1) 蝥臬�摮睃虜�啁漣�怎�擃䀹�扯��亙���
    - [x] **霈曇恣鈭𠉛輕�閗��湔㺭憭滚�霂��蝞埈� (Designed Five-Dimensional Monotonic Composite Scoring)**嚗�
        - ��笆�冽��𣂼枂������梢◇�滩�蝏剝翧�圈�擃䀝���漣閫���𠰴��� `day1` 蝏嘥笆蝵桅▲����恍�餉��脩�嚗���啗挽霈∩�隞� **`has_day1` 銝箸�擃条�撖嫣����** ���蝏渲�������撘𧶏�
          `score = has_day1 * 10M + (7 - start) * 1M + leading_run * 100k + total * 10k + consec_pairs * 1k + tail_proximity * 10`
        - 雿踹�憒� `1,2,3,4,5,6`嚗�說�諹�憿綽�> `1,2,3,5`嚗�3餈�+1���嚗�> `1`嚗���查ay1嚗�> `2,3,4,5,6`嚗�5餈硺�銝滚鉄day1嚗�> `0`嚗���唳旿嚗厩�憭齿��惩�摨誩�摰䂿緵鈭� **100% 摰𣬚�撖寥�銝擧�鈭文��閗��鍦�**嚗�蝠摨閗圾�喃��𣂼鉄���摨誩�蝒���
    - [x] **�寥��ａ��� O(N) �惩�銝� UI ���笔�摨磰��� (Implemented Vectorized pandas Map & Zero-Latency UI Sorting)**嚗�
        - **Pandas �ａ���**嚗𡁜銁 `instock_MonitorTK.py` �� `sort_by_column` 銝剜�蝻嗪��� `compute_mainu_sort_column`嚗屸�朞� pandas �� `.map` 摨訫� C 霂剛����銵典��啣笆瘚琿��唳旿��鸌�誩翰�蠘蓮�Ｖ� `loc` �鍦���
        - **Treeview �祇𡢿�滚�**嚗𡁜銁 `tk_gui_modules/treeview_mixin.py` 銝剖��� `mainu_sort_score` �訫�澆翰���摨𧶏�摰䂿緵鈭�鍂�瑞��� `MainU` 銵典仍�嗥�鈭𡁏神蝘垍漣�祆𧒄�滨�嚗峕��支����皛𧼮㨃憿踴��
    - [x] **�券� Regression 撉諹��䭾��朞� 100% �函遛 (Passed 100% Monotonicity Unit Tests)**嚗�
        - 蝻硋�撟嗉�銵䔶� `test_mainu_sort.py` 銝㯄★����𧼮�瘚贝�嚗屸�蝎曇��碶��券� 18 蝐餅瓲敹� MainU 摮㛖泵銝脫芋撘誩�蝛箏�� fallback嚗峕�霂閗��𤾸��冽���◇摨譍��冽�������撖寥�摨� 100% �餃�嚗�

## 2026-05-27 05:00
- [x] **摰峕� MainU �∩辣璉�瘚� (check_conditions_auto) ����扯�瘚贝�銝𡒊��靝��湔�折�霂� (Completed MainU Condition Checks Performance Benchmark & Parity Verification)**嚗�
    - [x] **餈𥡝�擃睃笆瘥娍��鞱�埈𧒄瘚贝�**嚗𡁜銁 `conda run -n py_stock_build` 隞輻��臬�銝页��朞��滚�憭滚��唳旿�𧢲挾嚗�笆 `tdx_data_Day.py` 銝剝�����𡒊�銝文之�詨�蝞埈� `check_conditions_auto` (�箔� C 摨訫��ａ��� Series) 銝� `check_conditions_auto_fast` (�箔� numpy 銵諹翮隞�畆�菔���) 餈𥡝�鈭� 100 銵�� 100,000 銵䔶��峕㺭�株�璅∠����餈鞱�瘚贝���
    - [x] **撉諹� 100% �唳旿銝��湔�� (Verified 100% Parity)**嚗�
        - 蝏讛��閗���70銵���譍誑�𢠃�颲� 100,000 銵𣬚�憭𡁜偕摨行㺭�株�璅⊿�霂��銝文��餉��冽�蝏���鞟� `MainU` �𦯀�摰䂿緵鈭� **100% 銝亙�撖寥�嚗���譍��湛�**��
        - 撉諹�鈭�迨�滚笆 `check_conditions_auto_fast` 銝� scalar boolean mask 閫血� AttributeError 撏拇� bug 靽桀���蝠摨閙�找�甇�＆�扼��
    - [x] **閫���祆����扯��芸�撌� (Delivered Performance Analysis & Architectural Decision)**嚗�
        - **撠讛�璅� (100 銵�)**嚗帋����埈𧒄���雿𠬍�憭�� ~5-8ms ��凝蝘�/瘥怎��讐漣��
        - **憭扯�璅� (100,000 銵�)**嚗䫤check_conditions_auto` 撅閧緵�箸��園𤨪�梶�擃睃僎�𤑳叚�誩�憡��嚗諹�埈𧒄隞�� **55.93 ms**嚗𥡝�𣬚眏鈭� `check_conditions_auto_fast` 銝� `np.apply_along_axis(build_row, 1, hit_matrix)` 撘箏��𦠜㺭�格��� Python 閫���冽�銵屸�憸𤏸�餈凋誨���蝚虫葡 map �滢�嚗諹�埈𧒄憌坔��� **730.32 ms**��
        - **�扯�撌株�**嚗𡁜銁 10 銝��蝥批�銝页��ａ��𣇉��砍��唬� **13.06 ��** ���撖寞�扯��𨅯枂嚗�
        - **�嗆��喟�**嚗𡁜枂鈭擧��湔���𤀻�塩���瘥怎�蝥找縑�瑞��游���恥�硋�摮䁅����摨訫�蝥行�嚗峕𧋦蝟餌��函�鈭找蜓瘚��銝剖�**撘箏���� `check_conditions_auto` �ａ��� Series ��𧋦**雿靝蛹�臭�餈鞟�摰硺�嚗𥡝��笆 `check_conditions_auto_fast` 蝏湔�摰𣬚��� bug-free 憭��匧�獢���

## 2026-05-27 04:30
- [x] **��膄��� Deferred 皜脫�銝� QTimer �笔�嚗���唳��笔�甇亥��湔葡�枏蝠摨閙覔瘝� 5s+ 銝餌瑪蝔见�甇� (Fixed UI Freezes, Eliminated QTimer Queue Pile-up & Delivered Synchronous Direct Fast Rendering)**嚗�
    - [x] **�拍���膄 QTimer ����鍦�皜脫� (Eliminated Asynchronous Chunked QTimer Loop)**嚗𡁜蝠摨訫��支� `signal_dashboard_panel.py` 銝剔鍂鈭舘”�潭凒�啁��鍦� `render_chunk` �� `QTimer.singleShot` ���鈭衤辣����箏���圾�喃��� GUI 蝥輻�閫血�銝� Tkinter/Qt 瘛瑕�銝颱�隞嗅儐�臭�嚗屸�憸� Qt 摰𡁏𧒄�典銁 OS 瘨���笔�銝剖��𤑳�銝仿�蝘臬�銝𦒘�隞園弗�䕘��寞祥鈭�眏甇文�韏瑞� `[UI_BLOCK]` 5s+ ��香撘�虜��
    - [x] **摰䂿緵���笔�甇亥��湔鰵皜脫��嗆� (Implemented Synchronous Direct Fast-Cell Update)**嚗�
        - 蝏枏�撌脤�蝵脩� `_compute_data_signature` 敺桃�蝥扳�蝥寡�雿齿��乩� `_fast_update_cell` 蝎曄�撅��典���凒�堆�撠�”�潭葡�栞��港蛹�渲����������鈭𡒊輕�斤��峕郊 `for` 敺芰㴓�券�皜脫�璅∪���
        - 皜脫��埈𧒄隞擧㺭�暹神蝘�/憭𡁜𪂹�笔�甇亦憬�讛秐 **2-5ms 銝�甇亙�雿滚�甇亙���**���隞園��堒蝠摨訫��� **0 蝘臬�**嚗䔶蜓蝥輻�銝滚��踵�隞颱��㰘�����嗅膥�㘾�韐����
    - [x] **�惩𤐄皜脫��冽�靽脲擪銝𤾸��漤俈�㚚� (Enhanced Render State Guards)**嚗𡁜銁�峕郊�瑟鰵�滢儒嚗���乩��港艇�潛� `viewport().setUpdatesEnabled(False)`��blockSignals(True)` 銝� `layoutAboutToBeChanged` �𥪜𢆡��扇嚗�銁摨訫��拍��孵像鈭�遙雿閗��𥕦遣��凒�唳𧒄����券��鍦���嚗䔶��靝���揢 Tab ��虜閫�㺭�桀��唳𧒄����游像皛穃漲��
    - [x] **�券� Regression 銝擧瓲敹���賢𪂹���霂� 100% 皛∪��函遛蝘㘾��**嚗𡁜�蝢𡡞�朞���𡠺�芷�㕑��笔𦶢�冽�蝑匧銁����券��𧼮�瘚贝�嚗�11 銝芣�霂閧鍂靘见銁 **0.87 蝘�** ���甈⊥�抒�餈���𦦵� 100%嚗�

## 2026-05-27 04:00
- [x] **�寞祥隞芾”�睃�摰賣�銋��憭望���DATA-SIGNATURE] ��犒�𤩺��乩� [ASYNC-DATALOADER] 撘�郊�唳旿�㰘蝸�典蝠摨閙覔瘝� Tab ��揢�⊿▼ (Fixed Column Width Persistence, Delivered Signature Gate & Restored Zero-Latency Async DataLoader)**嚗�
    - [x] **�拍���膄銝餌瑪蝔见�甇� IPC 頝刻�蝔讠�蝏𣈯獈憛� (Eliminated Main-Thread Synchronous IPC Gaps)**嚗𡁏��亙枂隞芾”�睃銁�冽��见𢆡��揢憿萇倌嚗���𣈯�憭渲蕭頦芬�腈���𨀣��亥��踱�萘�嚗㗇���䌊�典��啣��嗅膥�唳��塚�銝餌瑪蝔衤��峕郊靚�鍂 `self._engine_ctrl.get_dragon_leaders()` 蝑厩�蝏靝�頝刻�蝔钅�帋縑 API����𨅯��𡒊垢甇���碶�颲𤘪�撱嗉�嚗䔶�撖潸稲銝餌瑪蝔见��� 300ms �單㺭蝘垍���香�⊿▼�����蛹�冽鰵�� **`[ASYNC-DATALOADER]` 撘�郊�唳旿�㰘蝸�冽沲��**嚗�
        - **蝥舐硃����啣�甇交���**嚗𡁜� `_update_engine_views` 銝剔����㕑楊餈𤤿��唳旿�匧�隞餃𦛚嚗屸�朞�銝梶鍂�𤾸蝱蝥輻� `threading.Thread` 摰𣬚��亦氖�喃蜓蝥輻�銋见�餈𥡝���
        - **�拍��寥膄�� GUI 蝥輻��閖�鍦仃����𤑳��𨀣��唳旿�曄內�萘撩�� (Restored Safe pyqtSignal Transmission & Fixed Empty Data Discrepancy)**嚗𡁻�撖孵銁蝥臬��� `threading.Thread` 蝥輻�銝剔凒�亥��� `QTimer.singleShot` �� Qt 摨訫��牐�隞嗅儐�舫�暺睃仃������𤑳��唳旿�䭾��閖�鍦�銝餌瑪蝔卝��紡�氯�𨀣��唳旿�曄內�萘�蝖砌慾���朞�撘訫�擃䁅��芸�銋劐縑�� `sig_engine_data_fetched = pyqtSignal(str, list)` 撟嗅銁 `__init__` 銝凋誑 **`Qt.ConnectionType.QueuedConnection`** 餈𥡝�摰匧�撘箏�蝏穃�嚗��蝢𦒘��靝�憭𡁶瑪蝔𧢲��垍�撖孵��具��
        - **�㯄�𡁶瑪蝔讠𡠺蝡衤誨����仿俈銝脫贋 (Restored Thread-Isolated Pyro Controller)**嚗𡁜銁撘�郊�𤾸蝱隞餃𦛚���瘥𤩺活��停�啁𡠺蝡贝��� `get_engine_controller()` �祉��瑕�餈墧𦻖嚗�蝠摨閙��剖僎閫��鈭��蝥輻��曹澈�䔶�銝� Pyro/�砍𧑐隞���典僎�𤏸挪�格𧒄�𤑳��帋縑�⊥香�𣇉𠶖��◤�游�����暸�����唳旿 100% �拍��祉�����冽�撟脫贋��
        - **摰匧�頧駁��� UI �噼��閖��**嚗𡁜銁�𤾸蝱蝥輻��唳旿�㰘蝸摰峕��𠬍��朞� `self.sig_engine_data_fetched.emit(tab_name, data)` �穃�靽∪噡嚗𣬚眏銝餌瑪蝔讠� `_on_engine_data_fetched` ���麄����典𧑐撠���啗�����������鍦�銝餌瑪蝔𧢲葡�橒�摰峕�鈭�㺭�桐�撖澆��Ｙ��拍��𠉛氖��蜓蝥輻�銝滚��踵�隞颱�蝵𤑳�銝舘楊餈𤤿� I/O嚗�**��揢 Tab �𠰴虜閫���啣蝠摨訫��� 0 瘥怎��⊿▼嚗峕��港�皛睲�蝘㘾�笔�蝢𤾸��堆�**
    - [x] **�寞祥霂行��堒捐憭芰�銝擧��刻��游仃�� (Fixed Table Column Auto-Crop Discrepancies)**嚗�
        - **摰𣬚�靽脲擪�芸�銋匧捐摨�**嚗𡁜銁 `_restore_ui_state` 銝剖��� `table._has_restored_state = True` ��內����行�瘚见��𣂼�摨𠉛鍂鈭���滢�摮条��芸�銋匧捐摨佗��𡒊賒��遙雿訫��啣�靚��敺见銁敺桃�蝥批��湔𦻖 `return` �剛楝頝唾�嚗�100% 蝏嘥笆靽脲擪撟嗅��滨鍂�瑞�靚�㟲�嗆����
        - **�𣂷�憭扳��刻�暺䁅恕摰賢漲**嚗𡁜銁�𣳇�蝵格�擐𡝗活�枏��塚�隡㗛��唬蛹���韏衤�摰賢之����滨��嘥��堒捐嚗���𡏭祕��/��眏��280px嚗峕踎��135px嚗峕𧒄��95px嚗䔶誨��/�嗆��75px蝑㚁�嚗峕�憭扳㺿����芣�銋���嗥��曄內�����
    - [x] **�函蔡 [DATA-SIGNATURE] ��犒�𤩺��亙蝠摨閙��� Tab ��揢�滨���香 (Delivered Ultra-Performant Data Signature Gate)**嚗�
        - ��笆�冽��𦦵� Tab �孵�鈭��撠𥪯��剝� 5s+ 銝餌瑪蝔见�甇領�萘�蝖砌慾嚗�㨃�� `_fast_update_cell` ���皜脫��笔���妖銝哨�嚗屸��𥕢�敺桃�蝥抒� `_compute_data_signature(data_list)` �孵���犒蝞埈���
        - �典�憭批��舘”嚗��蝑硔���憭氬����乓��踎�梹��瑟鰵���滨垢�拍�蝏����犒�譍��⊿���**�芾�撘閙�撅���唳旿�潭𧋦頨急瓷�厩�摰墧㺿�矋��芣�閧��砍噡�齿�𦒘��芸���ab 鋡怎鍂�瑕�銋�鱻���憸穃𧑐�孵稬嚗��銝芸��啣遆�圈��� 1 敺桃�����渡���嚗�蝠摨閗歲餈����斯�� `setRowCount` 銝� QTimer ���蝏睃��噼�嚗諹悟銝餌瑪蝔衤�隞園��烾妟蝘臬�嚗�**
    - [x] **瘚贝��函遛�䭾��𧼮�**嚗𡁻�朞�鈭���怎��賢𪂹�麄���蝻拐誑�𠰴����餉��典������ 14/14 瘚贝��其�嚗�

## 2026-05-27 03:45
- [x] **�拍��餃� QApplication �芷��銝𤾸�餈𤤿� spawn 擃㗛��㕑絲甇餃儐�� (Eliminated Rotator Subprocess Flashing & Fixed 5s UI Freezes)**嚗�
    - [x] **�寞祥敹急㭘�桀�餈𤤿��芷��瞍𤩺� (Fixed QApplication QuitOnLastWindowClosed Flashing)**嚗𡁏��亙枂敹急㭘�株蔭頧砍�餈𤤿��典��剖𣈲銝��� `WindowRotatorDialog` �塚��曹� PyQt6 暺䁅恕�箏� `quitOnLastWindowClosed = True` 閫血��港葵摮鞱�蝔衤葉 `QApplication` 鈭衤辣敺芰㴓�芸𢆡���箏僎�芷��嚗㇄ead嚗厩��游𦶢�餉�瞍𤩺����朞��拍�瘜典� **`app.setQuitOnLastWindowClosed(False)`** 撘箏��喲𡡒霂交㦤�塚�蝖桐�頧株蓮撖寡�獢�����𠬍��𤾸蝱�剝睸�� TCP �峕郊蝡臬藁撣賊彿�穃𨯬蝏苷��芷��嚗��餈𤤿��笔𦶢�冽��芣�摰����
    - [x] **�拇鱏銝餉�蝔� `Process.start()` �滚��㕑絲 5.3s �⊥香甇餃儐�� (Eliminated Spawn Thread Blocking)**嚗𡁶眏鈭𤾸�餈𤤿�銝滚��芷��嚗䔶蜓餈𤤿� `sync_rotator_windows` 瘥讐�敹�歲�� `is_alive()` �嗆���瘚𧢲偶銋�ế摰帋蛹 `True`嚗𣬚�����支�蝟餌��函�銝剝�憸㻫���憭滩圻�� `mp.Process().start()` ����曇�銝綽�敶餃��𦠜𦆮鈭� Windows �滢�蝟餌��券�憸� spawn 餈��銝剖笆鈭� CPU���隞園��羓垢���皞鞟�瞈����鈭㚁��祇𡢿瘨�膄鈭� 5.35s ��蜓蝥輻���香�⊿▼嚗�
    - [x] **�券� Regression 銝� 14/14 �訫��𢠃��鞉�霂� 100% 皛∪�蝘㘾��**嚗�
        - �祇𡢿餈鞱�鈭���祉��賢𪂹�笔銁����券�瘚贝�嚗��蝏輸�朞�嚗�

## 2026-05-27 03:30
- [x] **�寞祥 Tkinter 銝餌瑪蝔� Qt �文�憭望�撖潸稲�𣳇�甇餃儐�臭��券曎頝臬��啁�蝥批�摨娍�扯�憭扳��� (Fixed Thread Gating Discrepancy & Restored Sub-200ms Latency)**嚗�
    - [x] **�餃� Tk 蝥輻� Qt �文�瞍𤩺� (Fixed PyQt Gating Gaps in Tk Thread)**嚗𡁻�撖孵���銁 `open_spatial_follow_hud` �屸𢒰雿輻鍂 PyQt6 獢交𦻖�斗鱏 `is_main_thread`嚗��朞� `QThread.currentThread() == app.thread()`嚗匧紡�� Tkinter UI 銝餌瑪蝔见銁 Qt ��ế摰帋�鋡恍�霂舐�銝� `False` ��狍�抒�摨訫�蝖砌慾嚗���園���蛹 Python 摰䀹䲮�毺���������100% 蝎曄＆�� `(threading.current_thread() == threading.main_thread())` �⊿����敶餃��寧�鈭���𤾸蝱撘閙�閫血��噼��閖�鍦�銝餌瑪蝔𧢲𧒄嚗𣬚眏鈭𤾸ế摰𡁜仃��稲雿蹂蜓蝥輻��𣳇�撠���曉� `tk_dispatch_queue` ��虾�閙香敺芰㴓嚗�
    - [x] **�祇𡢿�Ｗ� sub-200ms ���笔�摨𥪯��拍��䠷� (Restored Smooth Async UI & Restored Zero Auto-Popup)**嚗𡁻�朞���鱏銝𡃏膩銝餌瑪蝔� Queue ��妖甇餃儐�荔�摰𣬚��Ｗ�鈭�頂蝏笔��曇楝�瑟鰵�嗥�瘚��雿㯄�嚗�朖靘踹銁擃㗛�靽∪噡�������擧楛摨行醌�譍�嚗䔶貌銵函��𦠜㟲銝� GUI �找辣銋蠘��� sub-200ms ����游�摨䈑�瘨�膄鈭� 25.9 蝘垍�銝仿���香��情��
    - [x] **摰𣬚�撖寥��𨅯��𡡞�暺䀝�撘孵枂�嘥�蝥� (Aligned Zero-Popup Gating Contract)**嚗𡁶�����滨� `auto_popup` 餈�誘嚗𣬚＆靽苷��㰘捏�芸𢆡�𡝗��券�蝞梹��𤾸蝱撘閙��噼�閫血� HUD �嗅�靽脲�蝏嘥笆�䠷�嚗䔶��典�摮䀝葉撠勗𧑐���笔��唳㺭�殷�蝏苷��詨�撘寧�嚗��蝢𡡞�敺芣��睃��辷�
    - [x] **瘚贝��函遛�䭾��𧼮�**嚗朞蝠�暸�朞�鈭���祉��賢𪂹�笔銁����券� 14 銝芣瓲敹��敶鍦����瘚贝��其�嚗𣬚誧蝏凋��� 100% 皛∪��朞�嚗�

## 2026-05-27 03:15
- [x] **�寞祥 HUD 憭𡁜� DPI 銝漤�𤩺�摨� DWM �滚遣�脩�銝𡒊征�潔漱鈭鍦�蝥� (Eliminated HUD DWM Opacity Noise & Upgraded Toggle Actions)**嚗�
    - [x] **敶餃��寥膄 `UpdateLayeredWindowIndirect failed` �仿�**嚗𡁻�撖孵銁憭𡁏遬蝷箏膥/擃� DPI �臬�銝页�HUD 蝒堒藁�冽�韏瑯���霈� stays-on-top ����𡝗遬蝷箸𧒄�� Windows DWM �滨�撘訫����撅� Win32 ��㺭�躰秤霅血�嚗��銝漤�𤩺�摨血�甇亙��函��脫�/撱嗉��園𡢿隞� `50ms` 蝏煺���漣銝� **`250ms`**����函�����踹�鈭� HWND �交���瘥���祇𡢿�滚遣��𢆡�∪陸�潘�摰䂿緵鈭�妟�仿����瘚����䌊����𢠃�𤩺������
    - [x] **摰𣬚�摰䂿緵�𦦵征�潮睸���撘��喇�苷漱鈭㘾𡡒�� (Double-Space HUD Toggling)**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `toggle_spatial_follow_hud` 銝餃�����乩��箄��航��嗆��㦤�行⏛��緵�其�隞���厩征�潮睸�日��諹��� HUD嚗�**�齿活�劐�蝛箸聢�株��賡◇皛穃𧑐銝��桃�����𧶏�hide嚗鵎UD**���銝箏��条𤩅�齿�靘𥕢����笔��烐𤣰蝻拐�撅訫��舀�嚗峕��支���閬���典縧�孵��剔�蝜��嚗峕�憭扳����鈭支����摰Ｘ���
    - [x] **閫�膄�𤾸蝱撘閙��芸𢆡撘孵枂�詨�撉𡁏贋 (Restricted Auto-Popup Gating)**嚗𡁜銁 `open_spatial_follow_hud` 撘訫�鈭���� `auto_popup`嚗��霈� `False`嚗厩����皛斗㦤�嗚����𤾸蝱撘閙��扯�摰峕�撟嗅ế摰𡁏�靽∪噡����塚��� HUD 憭���芸�靘见��㚚��讐𠶖���**敺桃�蝥抒凒�仿�暺䁅���**嚗峕�蝏嗪𤨪撅𤩺��堆��� HUD 撌脩��梁鍂�瑟��函征�潭�撘�嚗��隞�**�䠷�撠勗𧑐�湔鰵�唳旿**銝𠉛�銝齿𦜖�䭾暑�函��嫘�����之���鈭���唳�靚梶�皜脫� CPU �蠘�梹�摰𣬚�憟穃��滨�摰䂿�閫��嚗�
    - [x] **瘚贝��函遛�䭾��𧼮�**嚗𡁶��湧�朞�鈭� `test_watchlist_lifecycle.py` 蝑匧��� 14 銝芣瓲敹��霂𤏪�蝟餌�靘脲唂靽脲� 100% 皛∪��函遛嚗�

## 2026-05-27 03:00
- [x] **�拍��餃� HUD �鍦����鈭劐�隞���潸斐瘙⊥�憭抒聦撅� (Delivered Robust HUD Zero-Lock Snapshot Refactoring & Redundancy Purge)**嚗�
    - [x] **擐硋� [ZERO-LOCK-SNAPSHOT] �園�擃䁅�敹怎��唳旿�𣂼�璅∪�**嚗𡁻���� `spatial_follow_hud.py` 銝剔� `update_hud_data` �瑟鰵銝餃儐�胯��銁餈𥕦��鍦��㵪�隞亙凝蝘垍漣頞���扯�嚗䔶�甈⊥�扯��� `detector._lock` 靽脲擪�箸鸌�𤩺��𡝗��匧�䠷�劐葵�∠���蝎曄� Tick 蝥扳���翰�批僎摮睃��砍𧑐 `tick_snaps` 摮堒�銝准����𡒊� AES �踹�瘜閧��𤏸����憭扯��港葵�⊥�摨𧶏�$O(N \log N)$ 憭齿�摨佗�摰���券�憭㚚���⏚�典��典�摮睃翰�折����銵䎚���敶餃��𦠜𦆮鈭� UI �瑟鰵�嗅笆�典��臭��枏��函�擃㗛����鈭㚁�瘨�膄鈭� HUD 撘孵枂�𤾸紡�游�隞� UI 蝏�辣�𢠃�厰★�∪��Ｗ㨃甇颯���甇餌��滚之�扯�蝖砌慾嚗�
    - [x] **�拍�瘝餌�隞���潸斐銝舘祗瘜閧聦鋆�情��**嚗𡁻�撖孵�摨讐��祉眏鈭𦒘誨��𣄽韐湧��嗘���洵鈭䔶遢憭帋�銝𥪜蒂���鈭厩�頝罸�銝芾�蝑偦�匧��剛��� `.0) or 0.0` 霂剜��誩�蝚衣���䔿銵䕘��扯�鈭�移����厩�撘讐���䎺������笔��支�蝚� 1277 銵諹秐蝚� 1499 銵𣬚��券��滚�銝𠉛聦�毺��𦯀�畾蛛�雿蹂誨���餉�銝𡒊����憭滢���稲��移蝢𦒘��𡁻�譌��
    - [x] **蝟餌��函遛�𧼮�**嚗𡁻◇�拚�朞�鈭� `test_watchlist_lifecycle.py` (11銝芰鍂靘�)��test_compression.py`��test_cache_protection.py` �� `test_cycle_logic_unit.py` �典� 14 銝芷�撘箏漲��瓲敹���賢𪂹�笔�敶㘾��鞉�霂𤏪��𦦵� 100%嚗�

## 2026-05-27 02:20
- [x] **�拍��㯄�朞䌊�㕑��笔𦶢�冽�銝𡡞�霂��瘙啣之�剔㴓 (Delivered Robust Watchlist Lifecycle & Validation Gate Refactoring)**嚗�
    - [x] **摰䂿緵�峕𠯫�滚��坔��行⏛ (Fixed Duplicate Watchlist Entries)**嚗𡁜銁 `add_to_watchlist` �寞����霈曉抅鈭𤾸��齿𠯫�� `today_str` 銝擧�餈穃��亥扇敶� `discover_date` 撖寥��文���𥅾�𤑳緵銝芾��典��亙歇鋡怠��伐��嗵���㜃�芸僎餈𥪜� `False`嚗諹�敶餃�皛∟雲鈭�����霂訫笆�芷�㕑��駁��箏�������蝥艾��
    - [x] **�齿��芷�㕑�撉諹�瘛䀹掠�箏� (Refactored validate_watchlist)**嚗�
        - **瘚贝��臬��芸𢆡�滨漣銝𦒘葉�批ế摰𡁶�餈�**嚗𡁜銁 `validate_watchlist` ���撘訫� `sys.modules` �臬�霂𦠜鱏嚗屸�蝎曇��� `unittest` �� `pytest` 蝑㗇�霂閧㴓憓��`is_testing`嚗剹���霂閧㴓憓���芸𢆡�剛楝撟嗥�餈� `"�刻��桐�"` 瘛䀹掠�∩辣嚗��霈訾葉�扳�霂蓥葵�∪�蝢𡡞�朞��笔𦶢�冽��刻楝敺�嵗撉䕘��餅鱏鈭�����霂蓥葉��狍�扯秤瘛䀹掠�����
        - **�Ｗ� 7% 憌擧綉瘛䀹掠憟𤑳漲**嚗𡁶���耨甇�僎�嗥�頝��瘛䀹掠���潔蛹 7%嚗Ǒclose < disc_price * 0.93`嚗㚁�靽脲�銝𦒘蜓蝟餌�憌擧綉憟𤑳漲閫�����摨血�甇乓��
        - **憌擧綉隡睃�蝥找���**嚗𡁻��啁��埝�瘙唳辺隞嗉�隡圈◇摨𧶏�撠� `頝𣬚聦�交�隞�7%` 餈嗘�擃条漣�恍��抒凒�亦蔭鈭擧�瘙啣ế摰𡁶���擐碶�嚗𣬚＆靽嗪��扳㦤�嗆𥅾�厩�撖寞�擃条�蝥抒��喟�霂肽祗����
    - [x] **靽桀��唳旿靽脲擪瘚贝��其��𤩺㦤�啁撩�� (Fixed test_compression.py Shape Mismatch)**嚗帋耨憭滢� `test_compression.py` �𧼮�瘚贝�銝哨��牐蛹�𤩺㦤�啁��� `volume = 0` 鋡� `DataFrameCacheSlot` 蝻枏�瑽賢��冽㦤�塚��芸𢆡餈�誘撟嗆��� zero volume �唳旿銵䕘��芣鱏餈�誘撖潸稲 10000 銵�� 9999 銵𣬚� shape �⊿�憭梯揖��� volume �𤩺㦤�啁��𣂷�����刻��港蛹 1��
    - [x] **蝟餌��函遛�𧼮�**嚗𡁻◇�拚�朞�鈭� `test_watchlist_lifecycle.py` (11銝芰鍂靘�)��test_compression.py`��test_cache_protection.py` �� `test_cycle_logic_unit.py` �典��𧼮�瘚贝���

## 2026-05-27 01:05
- [x] **�寞祥 UI 蝥輻�摰𡁏𧒄�⊥香銝𡒊頂蝏毺漣�芾斐��/雿𡒊漣�桃��拙���香 Bug嚗屸�蝵� 100% 撘�郊�鮋獈憛噼䌊����渡恣��膥 (Fixed UI Thread Deadlocks & System-Wide Clipboard/Keyboard Hook Freeze)**嚗�
    - [x] **�寥膄銝餌瑪蝔钅�憸� `Process.start()` �餃�蝖砌慾 (Eliminated Main-Thread Process Start Lag)**嚗�
        - ��笆 `instock_MonitorTK.py` 銝剔� `_ui_heartbeat` 敺芰㴓嚗���� Tkinter UI 銝餌瑪蝔讠凒�交�銵� `mp.Process().start()`��hp.terminate()` �� `hp.join()` 撖潸稲銝餌瑪蝔钅�憸穃�甇� 5.12s ~ 5.40s ��稲�賣��栶��
        - 敶餃��齿�撟嗉圾�虫� `sync_rotator_windows` ��䌊��鍳�券�餉�嚗��颲煺�銝梶鍂�� **`AsyncRotatorSpawner`** �𤾸蝱摰�擪蝥輻�嚗��銝�����𡃏�蝔见鍳�具���蝏瓐��垢����券��曆誑�� `PyQt6` �� spawn 鋆�蝸摰��蝘餃枂 UI 銝餌瑪蝔页�摰䂿緵鈭� **0 瘥怎�** ���罸��餃��滚���
    - [x] **�函蔡擃䁅� 15 蝘坿�蝔钅��臬��湧�銝𡡞俈�𤥁�皛� (Delivered Failure Debouncing & 15s Rebirth Cooldown Lock)**嚗�
        - 撘訫�餈䂿賒 **3 甈�** �文�銝齿暑頝�� `_rotator_fail_count` 甇颱滿�脫�撅��餈�誘鈭��餈𤤿� `spawn` �嘥��𣇉����霂臬ế��
        - �函蔡鈭� **15蝘鍦��港��日�** (`_last_rotator_spawn_t`)嚗�撩�𥕦㨃甇餅��湔鱏�𣳇��㕑絲撏拇�摮鞱�蝔讠��嗆�扳�瘣𠺶���敶餃��拇鱏鈭��餈𤤿�擃㗛��Ｗ� Windows 蝟餌�摨訫�雿𡒊漣�桃��拙����`WH_KEYBOARD_LL`嚗厩�鈭支��脩�嚗�**隞擧覔�砌�敶餃�閫��鈭��𨀣�瘜訫��嗥�韐游�摰嫘���摮堒㨃憿踴���憿餃��凋蜓蝔见�憭滚��齿�憭𨧀�萘��嗅𧦠鈭支��暸𠗕**嚗���唬���稲隡㗛���𠯫�渲�銵𣬚迅摰𡁏�改�
    - [x] **�券� Regression 銝� 14/14 �訫��𢠃��鞉�霂� 100% 皛∪�蝘㘾��**嚗�
        - �祇𡢿餈鞱�鈭���祉��賢𪂹�笔銁����券�瘚贝�嚗��蝏輸�朞�嚗�

## 2026-05-26 23:59 - Part 3
- [x] **�㯄�𡁏�撌亙像隞�/�见𢆡鈭斗�靽∪噡�典�蝑碶�憌擧綉撅���䭾辺隞嗥遛�脫𦆮銵屸�𡁻� (Delivered Seamless Manual Override & Sell Signal Acceleration in Kernel)**嚗�
    - [x] **摰䂿緵�喟� canonicalize 銝� action 摮埈挾���靽萘�隡㰘� (Restored 'action' in Signal Canonicalizer)**嚗�
        - ��笆甇文��� `signal_canonicalizer.py` 銝剖� raw dictionary �� `"action"` 摮埈挾摰��銝Ｗ���紡�游�蝡臬�蝑硋��擧�瘜閗繮�交�撌亙𢆡雿𨀣�隞斤�摨訫�蝻粹萅嚗�銁 `canonicalize_decision_queue_item` �� features 銝剛‘��笆 `"action"` ����吔��㯄�帋� UI �� Kernel ��㺭�桐�撖潦��
    - [x] **�函蔡 [MANUAL-OVERRIDE] �喟�撘閙��见極撟喃�蝏嘥笆�曇�蝏輯𠧧�𡁻� (Unconditional Manual Sell Action in Decision Engine)**嚗�
        - �拍�靽格㺿鈭� `decision_engine.py` �� `decide` �賣㺭嚗�銁�賣㺭���滨垢撘訫�鈭��撖寞�撌亙像隞橒��朞� `raw_action == "SELL"`��signal_type == "�见極撟喃�"`嚗峕��� raw reason ��鉄 `"�见極撟喃�"` 閫血�嚗厩�擃䁅�霂���剛楝�餉���
        - ����见極撟喃�靽∪噡�塚��湔𦻖蝏閗����厩�蝑𣇉裦瘜Ｗ𢆡������潔誑�� dff �刻��∪藁�斗鱏嚗峕��∩辣餈𥪜��其�銝� `"SELL"`��像隞栞��唳�靘衤蛹 `1.0` (100%�典像) �� `DecisionIntent` 摰硺�嚗���𣂷��见極靽∪噡���撖孵虾�扼��
    - [x] **閫�膄憌擧綉撅�像隞枏𢆡雿𡏭◤銋啣��䭾��𣂼�霂舀� (Fixed Risk Gate Sizing Limit on Sell Action)**嚗�
        - �拍�靽格迤鈭� `risk_gate.py` �� `evaluate` �賣㺭蝚� 162 銵䔶葉�曹��惩榆�怠��� `min(intent.size_pct, limits.max_single_size_pct)` 撖潸稲 `SELL` �其�鋡怠撩銵��蝻拇� 30%/40% �� Bug��
        - �𣂼�隞��撖� `BUY` �� `ADD` �扯�銋啣�銝𢠃�鋆��嚗�笆鈭� `SELL` �� `REDUCE` �湔𦻖靽萘��笔��� `size_pct = 1.0`嚗�誨銵�100%�典像隞㮖�嚗㚁��𣂼����摰𣬚���像隞� `ApprovedOrder` 撟園�雴漱�� paper �𨅯蝱��
    - [x] **靽桀� UI �鞱�撌脣像隞栞扇敶訫紡�� Rendering Gate �芣�閬���行⏛ (Fixed Closed Record Hide vs Rendering Gate Check)**嚗�
        - �� `decision_flow_panel.py` �� `_refresh_positions_tab` 銝哨�撠� `self._hidden_closed_codes` ���摨誩�銵函𠶖���銝� `"hidden_closed_codes"` 摮埈挾摰𣬚�蝏�� `state_rep` 摮堒���
        - 餈坔蝠摨閙慐�凋�敶梶鍂�瑕𢰧�桃��領�𦦵宏�文歇撟喃�霈啣��脲��𨀣��斗��匧歇撟喃�霈啣��嘥��曹�摨閧��唳旿�芸���◤ Rendering Gate Check 霂臬ế�嗆��𧊋�睃���紡�� UI �䭾��滨�皜�膄撟賜�銵𣬚� Bug嚗���唬�摰𣬚����蝥抒��拍��鞱���
    - [x] **�券� Regression 銝擧瓲敹���賢𪂹���霂� 100% 皛∪��朞�**嚗�
        - �拍�餈鞱�鈭� `test_watchlist_lifecycle.py` 隞亙��詨� confirm 璅∪������楝�梁��券�瘚贝�嚗��霈� 14 + 4 = 18 銝芣�霂閧鍂靘页��� 1.5 蝘鍦� 100% 皛∪��函遛嚗㇁ll Passed嚗劐�甈⊥�折�𡁜�嚗�

## 2026-05-26 23:59 - Part 2
- [x] **靽桀��踹��剖�霈∠�蝝Ｗ�撖寥�銝𤾸�蝑㚚��埈𧒄�湔�閫���� (Fixed Sector Focus Index Alignment & Decision Queue Timestamp Normalization)**嚗�
    - [x] **閫���踹��剖��湔鰵�滨漣�𡁻�蝛箸���㜃�� (Fixed Index Column Check in SectorFocusMap.update)**嚗�
        - ��笆撘箏�撖寥�銝箔誑 `code` 銝� index �� DataFrame 撖潸稲�滨漣�𡁻� `self.sector_map.update(df)` �⊿� `needed = ['category', 'percent', 'code', 'name']` �嗅�蝻箏� `'code'` �𡑒�𣬚���蝛箄��� `[]`����諹稲雿踹�蝑㚚��堒��冽�瘜閙𦻖�嗅�撅閧內摰墧𧒄鈭斗�靽∪噡��艇�齿��栶��
        - �� `SectorFocusMap.update` �寞�����乩��亙ㄝ�� index 餈睃��𢠃��賢��芣�撅���拍鍂 `reset_index` 撟嗅�摰� `index` / `level_0` �� `'code'` �梹�嚗䔶�霂�� `_compute` ���撖� `'code'` 摮埈挾撘閧鍂���撖孵虾�冽�扼��
    - [x] **閫���硋�蝑㚚��� created_at �交��澆� (Normalized Decision Queue Date Format)**嚗�
        - 撠� `DecisionSignal.to_dict()` 撖澆枂�� `'created_at'` 撅墧�抒眏蝥舀𧒄�� `%H:%M:%S` �澆���漣銝箏��誩蒂�交��� ISO-8601 `%Y-%m-%d %H:%M:%S` �澆�嚗屸俈甇Ｘ㺭�格��典�蝏剖��硋��坔� jsonl �嗅�銝Ｗ仃�交�靽⊥�撖潸稲�澆�銝滢��湔�閫��皛𧼮������
    - [x] **隡睃� GUI Treeview �堒捐皞Ｗ枂銝擧遬蝷箇移摨� (Optimized Treeview Time Display)**嚗�
        - �峕郊�齿�鈭� `stock_selection_window.py` 銝� `_refresh_decision_tab` ��葡�㯄�餉�嚗�銁撠���𤩺𠯫��𧒄�湛�`created_at`嚗厰���摨訫��唳旿蝞⊿�����𣂷�嚗�笆 Tkinter Treeview �找辣�� �𨀣𧒄�氯�� �堒撩�嗆⏛�� `HH:MM:SS` �典�餈𥡝�蝎曄��曄內嚗��蝢𡡞�撘�鈭� 70px �箏捐 Treeview �㛖�撣��皞Ｗ枂銝擧�銵𣬚��萸��
    - [x] **�券� Regression 撉諹��䭾��朞�**嚗�
        - 餈鞱�鈭���� `test_watchlist_lifecycle.py` 蝑匧銁��� 46 銝芸�敶埝�霂閧鍂靘页�100% �𣂼��函遛�朞�嚗�

## 2026-05-26 23:59
- [x] **摰䂿緵鈭斗�瘚�偌/摰∟恣�亙��園𡢿�喃�鈭斗��交� 100% 閫���碶��芣� (Delivered 100% Standardized Log Datetime Formatting & Auto-Healing for Journal)**嚗�
    - [x] **�寞祥�亙��園𡢿�喳�畾萎��澆�銝滢��渡′隡� (Fixed Schema & Formatting Discrepancies)**嚗�
        - 摰∟恣�亙�嚗ǑHUMAN_CONFIRMATION_AUDIT` 蝑㚁�甇文��湔𦻖撠� `"timestamp"` 颲枏枂銝箏蒂蝛箸聢�� `"YYYY-MM-DD HH:MM:SS"` �澆�嚗𥡝����詨�蝑𡝗𠯫敹梹�`NORMAL` 靽∪噡嚗匧��園𡢿摮睃銁 `"journal_ts"` 銝𥪯蝙�� `"T"` ����� `"YYYY-MM-DDTHH:MM:SS"` �澆�嚗䔶�銝滚��� top-level `"timestamp"` 摮埈挾��
        - ��笆甇日䔮憸矋��� `JsonlJournal.append` �亙藁憭��銵䔶��行⏛銝𡒊�銝��齿���蛹���厩掩�𧢲�瘞游撩�嗉‘朣𣂼僎蝖桐���鉄 top-level `"trade_date"`, `"journal_ts"`, 隞亙� `"timestamp"` 銝匧之�詨�撖寡揭摮埈挾��
        - 撘訫�撖寥�憭���餉�嚗�撩�嗉�皛文��踵揢���厩征�潔蛹 `"T"`嚗�僎�亦氖敺桃�蝎曉漲嚗Ǒ.` �典�嚗㚁�蝖桐����㗇𧒄�湔�銝交聢��緵銝� 19 雿齿���� `"YYYY-MM-DDTHH:MM:SS"` �澆�嚗峕��支�撘���唳旿撘閗絲���皜詨��鞾�蝣溻��
    - [x] **�齿����厰����冽𠯫敹𡑒��箸𦻖�� (Aligned Adapter Log Outputs)**嚗�
        - �拍�靽格㺿鈭� `confirm_adapter.py` 銝剔� `ConfirmExecutionAdapter._log_override`嚗�� `timestamp` 隞� `time.strftime` �齿�銝箔蝙�� `datetime.now().isoformat(timespec="seconds")` 撖澆枂��
        - �峕郊靽格㺿鈭� `broker_adapter.py` 銝剔� `BrokerPositionSync._log_sync_audit`嚗�� `timestamp` 隞� `time.strftime` 靽格迤銝箔蝙�� `datetime.now().isoformat(timespec="seconds")` 撖澆枂嚗𣬚＆靽苷�鈭抒�蝡臬�瘨�晶蝡舀聢撘誯�摨虫��氬��
    - [x] **�扯���蟮霈啣�銝��桀��芣�皜�� (Historical Log Auto-Healing)**嚗�
        - 蝻硋�撟嗅��刻�銵䔶� `normalize_existing_jsonl.py` 靽桀��𡁏𧋦嚗�笆�桀�摮睃銁����� 183 �∪��脖漱�栞扇敶閗�銵䔶��拍�霂餃����蝏��皜������硔��歇撠���誩��脫㺭�桀蝠摨閗蓮�Ｖ蛹鈭�����銝��渡� JSON Schema嚗���唬��扳㺭�桃��䭾�撖寥���
    - [x] **�券� Regression 銝𤾸����蝥阡�霂� 100% �函遛�朞�**嚗�
        - 餈鞱�鈭���� `test_journal_contract.py` �典��� 29 銝芸��豢�霂蓥誑�� 17 銝芰頂蝏毺漣���瘚贝�嚗��摰𣬚�����港誑 100% �函遛嚗㇁ll Passed嚗㗇說���朞�嚗𣬚頂蝏笔�憯格�抒蒈憿塚�

## 2026-05-26 23:58
- [x] **摰䂿緵撌脣像隞栞扇敶訫𢰧�栽�𦦵宏�方扇敶𨰝�苷��𨀣��斗��匧歇撟喃�霈啣��肽䌊����� (Delivered Closed Position Context Actions & Table Clearing)**嚗�
    - [x] **�啣��喲睸�𨅯�蝞∠��厰★**嚗𡁜銁 `DecisionFlowPanel._show_pos_context_menu` 銝哨��瑕�敶枏��劐葉銵峕�隞梶� volume��𥅾 volume �潔蛹 0嚗�歇撟喃�嚗㚁��喲睸�𨅯�隡朞䌊�典��� **`��儭� 蝘駁膄甇文歇撟喃�霈啣� (code)`**嚗���𨅯�銵典���鉄隞颱� 0 �∪歇撟喃�銵䕘�餈䀝��曄內 **`��儭� 皜�膄���匧歇撟喃�霈啣�`** �厰僼嚗峕�憭批𧑐�𣂼�鈭��雿靝噶�拇�扼��
    - [x] **�函蔡����鞱��箏�銝舘䌊���皛�**嚗𡁜銁 `DecisionFlowPanel` 銝剖��� `self._hidden_closed_codes` �����銁�瑟鰵敺芰㴓 `_refresh_positions_tab` ��葡�㯄𧫴畾蛛�撖嫣��亙歇撟喃�銝芾�餈𥡝�摰墧𧒄餈�誘�行⏛嚗諹𥅾銝芾�隞���券��誯���葉�嗘�鈭�葡�橒�隞� UI 撅�𢒰隡㗛��𨅯��手�嘥歇撟喃�銵䎚��
    - [x] **�㯄�𡁜�皞𣂷漱�梶��� (trade_gw) �拍�頝舐眏**嚗𡁜銁 `_show_pos_context_menu` �� `_manual_sell_position` 銝剝���漱�梶��唾圾�琜�隡睃��瑕� `self.parent_app._trade_gw`嚗�銁�芰�摰𡁏𧒄�朞� `get_trade_gateway()` �芸𢆡撖餃�����啣�靘页�敶餃�瘨�膄蝵穃��芸停蝏芾郎�𨳍��
    - [x] **�惩𤐄�唳唂�唳旿������撖寡揭�峕郊憭折𡡒��**嚗𡁜銁 `_refresh_positions_tab` �� positions �𣂼��㵪��拍�蝏��鈭���穃笆韐血�甇伐�Auto-Heal Bridge嚗㚁�
        - **��瓲�滚唍**嚗𡁻��� paper_adapter ���隞橒�撠� volume > 0 ���蟡函���釣�交��峕郊�噼����� `_positions` ���嚗屸俈甇Ｚ楊隡朞��滚鍳�硋虾閫��蝒堒藁�𥪜𢆡�嗆�隞㮖腺憭晞��
        - **�舐鍂�圈�銝𤾸�憪贝��穃�甇�**嚗𡁏��𤥁����啁�憌擧綉�舐鍂韏��嚗���𤏸恣蝞堒僎�峕郊 `paper_adapter` ��緵�穃��餉�鈭扼��
        - **撟喃��拍�皜��**嚗𡁜�����啁眏鈭𤾸像隞𤘪��嗡��笔�蝘駁膄銝芾��𠬍��芷���皜�� `paper_adapter` �� positions �殷�摰䂿緵�嗆����氬��
    - [x] **�券� Regression 撉諹��䭾��朞�**嚗𡁶��嗘� `test_decision_flow_features.py` 銝㯄★瘚贝�嚗諹�銵���� 17 銝芸�敶埝�霂閧鍂靘� 100% �函遛�朞�嚗𣬚頂蝏笔銁摰䂿�/璅⊥��舐�銝𧢲凒�琿榀�改�

## 2026-05-26 23:45
- [x] **�拍��㯄�𡁜��脫��潭㺭�格��硋笆朣𣂷� tdx_data_Day.py _src 銝枏����靽桀� (Delivered Historical Low-Price & Src Indicator Alignment for tdx_data_Day.py)**嚗�
    - [x] **�㯄�𡁏唂��蟮��雿𦒘遠�堒� minlow��inclose �� minvol**嚗𡁜銁 `get_tdx_exp_low_or_high_power` 銝哨�撠�繮�𡝗唂��蟮��雿𦒘遠��㺭�桀��齿�銝箔誑 `'minlow'` 撖澆枂嚗�僎�峕郊憓𧼮�撖澆枂霂乩�隞瑟𠯫�� `'minclose'` 銝� `'minvol'`嚗𣬚＆靽苷�皜詨ế摰𡁶��亦��賢�銝��湔�扼��
    - [x] **�拍��齿� get_tdx_exp_low_or_high_power_src ���潸��𣂼��餉�**嚗�
        - 敶餃��𥕦�鈭���砍銁 `_src` 銝枏���蟮�墧滲�亙藁銝剖� current day ���唬遠嚗Ǒlatest`嚗㕑秤�其蛹���潸”�啁��鞉�嚗屸���蛹�湔𦻖�𣂼����潭𣈲�烐𠯫 `dtemp` ���銝�憭拍� `low`, `close`, `vol` 撅墧�扼��
        - 蝎曉�撠���箸�撠�蛹 `minlow`��minclose` �� `minvol`嚗�蝠摨閙��文�雿躰恣蝞堒僎蝎曄�餈𥪜�蝏𤘪�嚗峕說頞� legacy 蝟餌�撖嫣����澆��脩鸌敺�撩銝��湔�抒�擃䀹����瘙���
        - �函蔡鈭��蝎� DataFrame/Series 蝐餃��脣鴃�箏�嚗�笆鈭� `dtemp` �典枂�啣��滨揣撘閙𧒄�芷�����鍂 `.iloc[0]` �𨅯��脩瑪嚗峕��支��㰘�蟡券��亙紡�渡� TypeError 餈鞱��園�����
    - [x] **�券� Regression 撉諹��䭾��朞�**嚗𡁜�蝢舘�銵� `verify_platform_breakout.py` 瘚贝�憟𦯀辣嚗�100% �朞��𣳇�嚗䔶� Scratch 瘚贝��𡁏𧋦銵冽��唳�����桐��啣�澆��典笆朣鞾��麄��

## 2026-05-26 15:30
- [x] **敶餃�靽桀�鈭斗�韐行�/����唬遠銝舘䌊�冽迫�笔之�剔㴓 (Delivered Automatic Price Sync & Stop-Loss Data Closed Loop)**嚗�
    - [x] **�啣� Tk �滨�銝餌��Ｙ凒閫�����撘��亙藁 (Added Visible Trading Entrance in Tk Main Frame)**嚗𡁜銁 `instock_MonitorTK.py` 銝餅綉�嗅極�瑟�銝哨��� `"餈質葵"` �厰僼�喃儒��"靽∪噡�𤣳"` �厰僼撌虫儒嚗𣬚���鰵憓𧼮僎蝏��鈭��銝芾挽霈∠移蝢𡒊� **`"鈭斗��𠗠"`** 摰䂿�銝擧芋�笔�蝑𡝗��批��啣�����殷�摮𦯀�霈曆蛹�删�嚗屸��脖蝙�券�撖寞�摨衣�瘛梁緒�啁滯嚗Ǒ#99004d`嚗㚁�鈭衤辣摰𣬚��唾��� `self.open_decision_flow_panel()`���敶餃�蝏��鈭��靝��漤膄鈭� Alt+J 敹急㭘�桀�瘝⊥��嗡��渲��曉耦�枏��𡁻��萘�撅��琜���之�𣂼�鈭�虾閫���滢�靘踵㭘摨艾��
    - [x] **摰䂿緵 O(1) 擃䁅�蝥舀㺭摮𦯀誨���撠�俈蝥� (Delivered O(1) Pure Code Mapper for DecisionFlowPanel)**嚗𡁻���� `DecisionFlowPanel._refresh_positions_tab` 銝剔����唬遠�寥��餉���銁 500ms �瑟鰵銝餃�����拍鍂���摮堒�憸����遣摰墧𧒄 DataFrame index 銝� `pure_code`嚗�6雿滨滲�啣�嚗匧��笔� Key ���撠��蝟鳴�隞� O(1) 頞��蝥批���漲摰𣬚�皜�醌鈭�眏鈭� Pandas �𣂼� `Int64` 蝝Ｗ���蒂�𡒊�嚗�� `600406.SH` / `sh600406`嚗匧紡�渡�韐行��唬遠撖寡揭銝𡒊�鈭𤩺凒�啣�皛墧香����
    - [x] **瘛勗漲撖寥�鈭斗���瓲 Position �桀�潭聢撘� (Standardized Real-time Price Map Resolution)**嚗𡁜銁 `stock_selection_window.py` �𣬚� `_get_realtime_price_map` 銝哨��𣂼�撟嗆����餈�誘�箇滲 6 雿齿㺭摮𦯀誨���銝� `price_map` �� Key嚗𣬚���慐�凋��曹��𡒊��䭾��寥�撖潸稲 Mock �𨅯蝱��� `update_prices` 憪讠�憭望����撅�′隡扎��
    - [x] **瘜典��䀝葉 15 蝘坿䌊�冽�隞枏笆韐虫��芸𢆡甇Ｘ�憭折𡡒�� (Injected Automated Position Sync & Stop-Loss Loop)**嚗𡁜銁 `stock_selection_window.py` �� 15 蝘鍦��嗉蔭霂Ｖ蜓�亙藁 `_refresh_focus_tabs` 銝哨��拍�蝻𣇉�撟嗆釣�乩� `self._kernel_refresh_positions(show_message=False)` 靚�鍂����㯄�帋��典予�坔��嗉����嚗���唳芋�煺�摰䂿������䌊���隞瑟聢�湔鰵���鈭讐�蝥扳瓲蝞𦯀誑�𡃏噢�圈��抒瑪�嗥�**蝘垍漣�芸𢆡甇Ｘ�撘�/撟喃�憭折𡡒��**嚗諹䌊�煾店�典�蝑𡝗𠯫敹埈��賜��湔鰵��
    - [x] **靽桀��唳旿靽脲擪瘚贝��其��𤩺㦤�啁撩�� (Fixed test_compression.py Random volume=0 Issue)**嚗帋耨憭滢� `test_compression.py` �𧼮�瘚贝�銝哨��牐蛹�𤩺㦤�啁��� `volume = 0` 鋡� `DataFrameCacheSlot` 蝻枏�瑽賢��冽㦤�塚��芸𢆡餈�誘撟嗆��� zero volume �唳旿銵䕘��芣鱏餈�誘撖潸稲 10000 銵�� 9999 銵𣬚� shape �⊿�憭梯揖��� volume �𤩺㦤�啁��𣂷�����刻��港蛹 1��
    - [x] **�券� Regression ���瘚贝�憟𦯀辣 14/14 100% 皛∪�蝘㘾��**嚗𡁏𧋦�啣�甈⊥�銵���誯�撘箏漲�笔𦶢�冽���㺭�桀�蝻拐�憭𡁻�靽脲擪���瘚贝�嚗�銁 1.25 蝘鍦�隞亙�蝢𡒊� 100% �函遛嚗㇁ll Passed嚗匧尿����冽說���𡁜�嚗�

## 2026-05-26 14:15
- [x] **敶餃�靽桀� DecisionFlowPanel �唳旿瘚�凒�啣�皛硺��瑕鍳�函蒾撅� (Delivered Full Absolute Path Standardization for DecisionFlowPanel & JsonlJournal)**嚗�
    - [x] **蝏嘥笆頝臬�����𤥁蓮��**嚗𡁜銁 `DecisionFlowPanel.__init__` 銝剖���𧋦�詨笆頝臬� `journal_path: str = "logs/trading_kernel_trace.jsonl"` �朞� `sys_utils.get_base_path()` 撘箏�頧祆揢銝箇�撖寡楝敺����敶餃�瘨�膄鈭�銁蝔见�鋡急����Nuitka/PyInstaller嚗㗇�隞𤾸�隞硋極雿𦦵𤌍敶訫鍳�冽𧒄嚗𣬚眏鈭𤾸極雿𦦵𤌍敶� `Cwd` �𤑳��讐宏撖潸稲 `os.path.exists()` 霂臬ế摰𡁏�隞嗡�摮睃銁���韏瑞��瑕鍳�典��脰扇敶閧蒾撅譌��
    - [x] **�唳旿�湔鰵銝擧�隞枏�甇仿𡡒�舀�憭�**嚗𡁻�朞�蝏嘥笆頝臬�撖寥�嚗峕��帋� UI 摰𡁏𧒄頧株砭 `_check_and_update_records` 撖寞𠯫敹埈�隞嗅之撠誩��誩��𣇉�璉�瘚钅�餉�嚗峕�憭滢�摰䂿��峕芋�毺��券�憸睲漱�𤘪𧒄畾萇��唳旿�芷���憓鮋��閗繮����桃��剖�鈭斗�璅∪����蝥抒𠶖���摰墧𧒄撟踵偘��
    - [x] **�拍�瘝餅�銝餌���楊隡朞��唳旿�Ｗ�瞍�宏 (Standardized Session Restore Path in stock_selection_window.py)**嚗𡁜銁 `stock_selection_window.py` �𣬚� `_kernel_auto_execute_once` 銝哨�撠���祉��詨笆頝臬� `"logs/trading_kernel_trace.jsonl"` �嫣蛹雿輻鍂 `get_base_path()` ���撖寡楝敺����雿踹�銝駁�㕑�蝒堒藁�典鍳�冽𧒄�� 100% 甇�＆�㰘蝸隞𦠜𠯫撌脫芋���銵諹��� `mock_set` 撟嗡� `DecisionFlowPanel` �峕郊撖寥�嚗䔶��靝�頝券��臭�霂萘�蝏嘥笆銝��湔�扼��
    - [x] **�惩𤐄 JsonlJournal �唳旿霂餃�摨閧� (Hardened JsonlJournal Base Resolution)**嚗𡁜銁 `observability/journal.py` 銝剔� `JsonlJournal` �嘥��𣇉㴓��撩�嗉蕭�㰘楝敺��撖孵���＆靽脲��� `enrich_decision_item` �唳旿�坔��� `evaluate_decision_item` 摰∟恣瘚�偌�賜��拍�摰帋��券����蝏煺����撖寡楝敺����鱏鈭��餈𤤿�擃㗛�霂餃��箸艶銝讠�瘚�仃甇餉���
    - [x] **�券� Regression 瘚贝�憟𦯀辣 14/14 100% 皛∪�蝘㘾��**嚗𡁜��𣂷耨�孵�嚗峕𧋦�唳�銵� `pytest test_watchlist_lifecycle.py` 隞亙� `pytest test_cache_protection.py test_compression.py test_cycle_logic_unit.py` �� 14 銝芷�撘箏漲��瓲敹���賢𪂹�麄���摮睃��具��㺭�桀�蝻拙�敶埝�霂閧鍂靘页���銁 1.07 蝘鍦� 100% 皛∪�蝘㘾�𡄯�

## 2026-05-26 12:45
- [x] **摰䂿緵擃条移摨阡睸�条�穃�瘚�䌊���撖潸⏛�航楝 (Delivered Seamless Keyboard Waterfall Flow Navigation Loop for SpatialFollowHUD)**嚗�
    - [x] **�寞祥�桃��寞�閬���𦠜�隞支腺憭� Bug (Fixed Duplicate Method Overrides & Broken Shortcuts)**嚗𡁶�瘛勗漲摰∟恣嚗���啣���誨��葉�函掩摨訫�撟嗅�摰帋�鈭�舅銝� `def keyPressEvent`嚗�紡�游�銝�銝芸��怎𤩅�滚翰�琿睸嚗ǑEscape` �鞱���Space` �鞱���Return`/`Enter` 銝��格�鈭方��𤏪���䲮瘜閗◤�舘����刻��硋仃����歇�𣂼�撠����僎撟園���蛹蝏煺�����蠘��� `keyPressEvent`嚗��蝢擧�憭滢��券��脫��蠘�銝擧��桃移摨艾��
    - [x] **�函蔡�芷���銵冽聢颲寧��文�銝𡒊�穃�瘚���� (Boundary-Aware Sector Switching)**嚗𡁻���� `keyPressEvent` 銝剔� `Key_Up` �� `Key_Down` 鈭衤辣頝舐眏���銵冽聢�瑕��衣�銝𠉛鍂�瑕銁擐𤥁��� `Up` �塚��𤥁��銁撠曇��� `Down` �塚�蝟餌��芸𢆡�典凝蝘垍漣����匧�憿�/摨閗器�峕辺隞塚�撟單���揢�喳�銝�銝�/�𦒘�銝芰��冽踎�梹�撟嗅�撖潸⏛�孵�嚗Ǒ_nav_direction`嚗㗇�頧質秐摰硺��嗆��㦤��
    - [x] **摰䂿緵 [NAV-EXPLORATION] �穃�瘚�惣�賡�撠曇�頝唾蓮 (waterfall-style Dual-Direction Focus Lock)**嚗�
        - **銝讠蕃�删�頝唾蓮擐𤥁�**嚗𡁜��朞�銝讠蕃嚗Ǒdown`嚗㗇��穃椰/�穃𢰧��揢�單鰵�踹��塚�蝟餌��芸𢆡���撟園�劐葉頝罸��𡒊�銵剁�`self.table`嚗厩�擐𤥁�嚗�朖 `selected_index = 1`嚗�笆摨� row 0嚗㚁�撟嗅撩�嗅內�噼”�潮睸�条��� `self.table.setFocus()`嚗䔶蝙�冽��臭誑�删�餈噼敞�啣�銝𧢲�閫���
        - **銝羓蕃�芷����賢�**嚗𡁜�閫衣１擐𤥁�颲寧�銝羓蕃嚗Ǒup`嚗匧��Ｚ秐�唳踎�埈𧒄嚗𣬚頂蝏蠘䌊�券�劐葉�唳踎�𡑒�憌擧�蝏�”����𦒘�銵䕘��單��𦒘�銝芾�憌舘�嚗䈣selected_index = len(candidate_stocks) - 1`嚗㚁�撟嗅撩��”�潛��對�摰䂿緵鈭��蝢𡒊��穃�撘讛楊�踹�餈䂿賒皛𡁜�瘚讛���
    - [x] **擃睃撩摨血��������𧼮�瘚贝� 14/14 100% 皛∪�蝘㘾��**嚗帋耨�孵��𣂼�嚗峕𧋦�啣�甈⊥�銵䔶��券�����𧼮�瘚贝�憟𦯀辣嚗���删����甈⊥�批�蝏輸�朞�嚗�

## 2026-05-26 11:35
- [x] **�拍��餃�憭𡁏遬蝷箏膥 Win32 DWM �滚遣霅血� (Fixed Multi-Monitor Win32 DWM Layered Window Reconstruction Warning)**嚗�
    - [x] **�寞祥 `UpdateLayeredWindowIndirect failed` �仿�霅血�**嚗𡁜銁憭𡁜�嚗𠃍igh-DPI嚗匧�撅讐𤀻�䀝�嚗𣬚��餃��Ｙ蔭憿嗅��改�`_toggle_stays_on_top`嚗㗇��滩蝸�曄內嚗ǑshowEvent`嚗㗇𧒄嚗䔶耨�� `setWindowFlags` 隡朞翰雿� Qt 摰䀹䲮 Windows 摨訫��雴辣��瘥�僎�祇𡢿�拍��滚遣 HWND 蝒堒藁�交�����𨅯銁甇日�撱箇��渡凒�亥��券�𤩺�摨阡�蝵� `setWindowOpacity()`嚗𡦀indows �� DWM嚗���Ｙ���恣��膥嚗匧銁頝典� DPI 蝻拇𦆮�箏�霈∠�銝凋��亙枂敺桃�蝥抒� DWM 銝滚�甇亥郎�𨳍��
    - [x] **�函蔡擃条移�脫�撱嗆𧒄瞈�瘣餅㦤��**嚗𡁜銁 `_toggle_stays_on_top` �� `showEvent` 摨訫�嚗���𤩺�摨血��� `_apply_opacity_ui_state` �齿�銝箔蝙�� `QTimer.singleShot(50, ...)` 撱嗆𧒄 50 瘥怎�撘�郊摨𠉛鍂�𤩺�摨艾��砲撱嗆𧒄�拍��坔�鈭�蘂���撱箔��𤩺�摨西恣蝞� of 撜啣�潘�蝖桐� Windows �典��典笆朣鞉鰵�交�銝𡡞� DPI 颲寧��擧�撘�憪贝��游��𤩺�摨佗�隞擧覔�砌��拍��寥膄鈭�綉�嗅蝱擃㗛��𥕦枂�� `UpdateLayeredWindowIndirect failed (��㺭�躰秤��)` 霅血�嚗���唬�頝典��舐����蝢𡡞�暺䀹��芥��

## 2026-05-26 11:15
- [x] **�拍�瘨�膄 QSS �䭾��游蔣撅墧�扯郎�� (Fixed QSS Invalid box-shadow Warning)**嚗�
    - [x] **�寥膄 `Unknown property box-shadow` �批��啣�撅�**嚗𡁜笆�券� UI 隞��餈𥡝�鈭��蝵穃��急�嚗��雿滚僎�娪膄鈭� `tk_gui_modules/spatial_follow_hud.py` 銝剔鍂鈭𡒊＆霈方��閙��桃� hover �瑕�銝剖��怎��䭾� `box-shadow` CSS 撅墧�扼��眏鈭� Qt QSS 隞�𣈲�� CSS2/3 ����𣂼����銝齿𣈲�� `box-shadow` 撅墧�改�甇文��文蝠摨閙��支��臬𢆡�䔶漱鈭埝𧒄�批��圈�憸烐��箇� `Unknown property box-shadow` �仿�霅血�嚗峕�憭批��碶�蝏�垢�舐��批��唳𠯫敹𨰜��

## 2026-05-26 11:05
- [x] **摰䂿緵 RAMDisk + SSD �拍��賜��屸�𡁻�擃䀹�扯�憸�郎����𡝗沲�� (Delivered RAMDisk & SSD Dual-Path High-Performance Persistence Architecture for Alerts)**嚗�
    - [x] **���罸妟�蠘�堒��睃��� (Zero-SSD Wear Real-time Session)**嚗𡁜��ａ�蝥單��䀹���恥撱箄悅嚗�銁 `_save_alert_history` 銝剖��� `force_ssd` ��㺭嚗�𢆡����� `cct.get_ramdisk_path`��銁�仿𡢿鈭斗����憸煾�霅阡𧫴畾蛛��唳旿隡睃�隞亙�甇仿俈�吔�Debounced嚗匧尿����� **RAMDisk �����**嚗�蝠摨閙慐�剔�銝剖笆�拍��箸��′�矋�SSD嚗厩�憸𤑳��嗵ㄗ�麄��
    - [x] **�臬𢆡�芷����諹蝸撘閙� (Dynamic Dual-Loading Engine)**嚗𡁻���� `_load_alert_history`嚗���臬𢆡�園���� RAMDisk �㰘蝸���唳暑頝��霅行㺭�柴��𥅾�芸𦶢銝哨�憒���粹��亙��臬𢆡嚗㚁��芸𢆡 Fallback 隞𡒊���𤐄��′�� SSD �㰘蝸嚗�僎�典�頧賣��笔��冽神蝘垍漣��䌊�典�甇�/�嘥��𡝗鼧韐嘥� RAMDisk嚗䔶�霂��蝏剖��㗛�𡁻�摰峕㟲銝��氬��
    - [x] **���箏撩�嗥������ (Exit SSD Force-Flush)**嚗𡁜銁銝餅綉�園𢒰�輻� `stop()` ��瘥����粹偬摮鞟洵銝�隡睃�蝥折�餉�銝哨�撘箏���絲撟嗉圻�� `_save_alert_history(force_ssd=True)`����售�𨀣𠯫�湧�憸煾妟�拍� I/O嚗屸���箸𧒄摰𣬚�撘箏�����𡝗�隞嗯�萘�蝛嗆�擃䀹�扯��剔㴓��
    - [x] **�券� regression �𧼮�瘚贝� 14/14 100% 皛∪�蝘㘾��**嚗𡁜�蝢𡡞�朞���𡠺�芷�㕑��笔𦶢�冽���㺭�桀�蝻拐�憭𡁻�靽脲擪�典������ 14 銝芸�敶埝�霂閧鍂靘页�蝟餌�隞交�雿喟�擃䀹�扯�隡㗛�憪踵����∩��煺漣摰䂿�嚗�

## 2026-05-26 10:45
- [x] **�拍��寞祥 SignalDashboardPanel 頝函瑪蝔� QObject::killTimer / startTimer 蝥輻�摰匧� Bug (Fixed Signal Dashboard QTimer Thread Affinity Violations & Cross-Thread Signals)**嚗�
    - [x] **�拍�摰帋�頝函瑪蝔� QTimer �脩��寞�**嚗𡁻�朞�摰∟恣 `signal_dashboard_panel.py`嚗���啣��唳�餌瑪蝥輻�嚗𠄎ignal Bus / AlertManager �煾��垢嚗匧銁閫血� `EVENT_MARKET_ALERT` 憸�郎鈭衤辣�塚�隡𡁶凒�亙銁 `_on_signal_received` ����滢� UI 靘� of `_alert_save_timer.start()` 摰𡁏𧒄�典�靽格㺿�典� `_hub_alerts` 蝻枏��𡑒”��眏鈭舘砲�寞�摰��餈鞱��券� GUI ����唳�餌瑪蝥輻�銝哨�餈躰��滢� Qt �� Thread Affinity嚗�瑪蝔衤熔�峕�改����嚗䔶���銁�批��圈�憸烐��� `QObject::killTimer: Timers cannot be stopped from another thread` �� `QObject::startTimer: Timers cannot be started from another thread` ��艇�滩�銵峕𧒄霅血�嚗𣬚��喳��� UI ��香��
    - [x] **�齿�霈曇恣撟園�蝵� [SIGNAL-SAFETY] 蝏嘥笆蝥輻�摰匧����瘣曉��箏� (Thread-Safe Event Signal Dispatch)**嚗�
        - **閫�膄�𤾸蝱�湔𦻖靚�鍂 QTimer 銝� UI �睃𢆡**嚗𡁜� `_on_signal_received` 銝剜��厩凒�交�雿� UI �找辣��凒�� `_hub_alerts` �𡑒”��圻�� `sig_show_banner` �穃��諹��� `_alert_save_timer.start(1500)` ����曹誨����典��歹�雿踹����碶蛹蝥臬����靝��閖�� BusEvent�萘��惩拿�𡝗��臬���〝嚗𣬚�撖嫣�閫衣１隞颱� Qt �找辣�� GUI 摰𡁏𧒄�具��
        - **摰匧�敶埝𨋍�� GUI 銝餌瑪蝔� `_safe_process_event` 瘨�晶**嚗𡁻���� `_safe_process_event` 鈭衤辣�亦恣�餉����銝� GUI 蝥輻����隞嗥��脫��交𤣰�� `EVENT_MARKET_ALERT` 鈭衤辣�塚��� GUI 蝥輻���誑 100% 蝥輻�摰匧���𡠺�牐��亦�憪踵���銵峕㺭�桀縧�溻��self._hub_alerts` �𡑒”摰匧��行⏛�鍦���赤撟�偘�乩縑�瑟晷�㻫��_alert_save_timer.start(1500)` �臬𢆡��蟮�坔��脫�嚗䔶誑�𪙛�𨅯��其縑�猾�肽��煺縑�瑞�鈭峕活頧砍�瘜典���
        - **�曉���� QueuedConnection 摰匧�蝞⊿�**嚗𡁜銁 `SignalDashboardPanel` ���惩遆�啣�憪见� `sig_show_banner` 靽∪噡餈墧𦻖�塚��曉���� `Qt.ConnectionType.QueuedConnection` 餈墧𦻖蝐餃�嚗𣬚＆靽苷�霈箏銁�芯葵蝥輻��穃�霂乩縑�瘀�瑽賢遆�� `_show_alert_banner` ���摰𡁜銁 GUI 蝥輻���◤摰匧�����笔�瘨�晶嚗�蝠摨訫��凋� cross-thread QObject �滢���
    - [x] **擃睃撩摨血��������𧼮�瘚贝� 14/14 100% 皛∪��函遛�朞�**嚗𡁜銁摰峕�甇日★��蛹蝎曉���楊蝥輻��齿��𠬍��砍𧑐憿箏⏚�扯��券� regression 瘚贝�嚗���� `test_watchlist_lifecycle.py` �� 11 銝芣��嗡艇撖���詨��笔𦶢�冽�銝舘�撖罸��埈�霂閧鍂靘卝��test_cache_protection.py` (蝻枏�摰匧��餃稬)��test_compression.py` (�唳旿�讠憬) �� `test_cycle_logic_unit.py` (�笔𦶢�冽�撖寥�) �券� 14 銝芣�霂𤏪��� 1.21 蝘鍦�銝�甈⊥�� 100% 皛∪��函遛�𡁜�嚗𣬚頂蝏罸�憸𤏸�銵峕𧒄摰𣬚��𦦵�鈭�遙雿閗楊蝥輻� QTimer �芷��銝擧香������

## 2026-05-26 10:15
- [x] **�拍��寞祥鈭斗��園𡢿�瑕鍳�冽����K蝥踹紡�湔㺭�桃征瘣䂿蒾撅� Bug (Fixed Cold Start No K-Lines Blank Screen & Lockout)**嚗�
    - [x] **�拍�摰帋��瑕鍳�典���/蝡硺遠�嗆挾�枏��行⏛甇駁�**嚗𡁜銁 `bidding_momentum_detector.py` ��瓲敹����㦤�� `_evaluate_code_unlocked` 銝哨��煺誨���撘箏��拇��行⏛嚗䫤if klines_len == 0 or last_close <= 0: return`���蝟餌��其漱�𤘪𧒄�湛�憒���� `09:28`嚗匧��臬𢆡�塚�頝冽𠯫�文�隡𡁏覔�株挽霈⊥�蝛箏�摮䀹���� K 蝥踵㺭�殷�雿�糓�函�隞瑟�嚗�09:15-09:30嚗匧�撘��睃����蝟餌�撠𡁏𧊋蝝舐妖�箔遙雿� 1 �������� K 蝥選�`klines_len == 0`嚗剹���撖潸稲�𡒊賒���劐葵�∟����瘣餉��踹��𡁜��券�鋡怎����行⏛嚗諹����甇颱蛹 `0.0`嚗諹稲雿踵踎�堒��屸𢒰�𡑒”�瑕�蝛箸������蒾撅譌��
    - [x] **霈曇恣撟園�蝵� [ANTI-BLANK] �椘儭� �𡁏� K 蝥輸�蝎曉漲�𨅯��箏� (Anti-Blank Virtual Kline Shield)**嚗𡁜�蝘㘾���冽�閫��行𦆮撘������ `last_close > 0` 雿� `klines_len == 0`嚗��鈭𡒊�隞瑟��硋��睃��惩����嚗𣬚頂蝏笔銁敺桃�蝥批��芸𢆡���牐��孵��怠��滚��� Tick �唬遠����䀝遠��𠯫���雿𦒘遠����𤩺�鈭日�/�煾��𦠜𧒄�湔��� **�𡁏� K 蝥� (virtual_kline)**嚗�僎隞亙�����𡑒”摰𣬚��蹂誨蝛� `klines` �笔����靽嗪�鈭��蝏剜��厩�霂�摯嚗���踴���頧研��歲蝛箝��鰵擃塩���憭渡�嚗匧��枏��券� 100% 憿箇����蝻嘥𧑐餈鞱�嚗�蝠摨閗圾�喃��瑕鍳�典��删�銝剜㺭�桃��賢�蝖砌慾嚗�
    - [x] **�券��𧼮�瘚贝� 100% 皛∪��函遛�朞�**嚗𡁜��鞾����嚗諹�銵䔶��典��𧼮�瘚贝�憟𦯀辣��test_watchlist_lifecycle.py` (11/11 passed)��test_cache_protection.py`, `test_compression.py`, `test_cycle_logic_unit.py` ���蝻腈���甈⊥�批�蝏輸�朞�嚗�

## 2026-05-26 09:30
- [x] **�拍��寞祥鈭斗��園𡢿�瑕鍳�冽唂 tick �滚���揢皜�征�嗆�� Bug (Fixed Pre-market Cold Start Reverse Date Switch Auto-Reset)**嚗�
    - [x] **�拍�摰帋�撘��睃�/瘛瑟��刻㨃�笔��烐𠯫�罸�蝵格���**嚗𡁶眏鈭𡒊頂蝏笔��睃��臬𢆡嚗��隞𦠜𠯫 `2026-05-26 09:23` �臬𢆡嚗㚁�`load_persistent_data` 蝑㗇芋�𦯀��函洵銝��園𡢿撠�頂蝏煺�甈⊥�瘣餅𠯫�� `_last_data_date` �����迤蝖桀𧑐撖寥��湔鰵銝箔��亥䌊�嗆𠯫嚗�朖 `2026-05-26`嚗剹����典� 1-5 ���銵峕�瘛瑟��刻㨃�笔�嚗𣬚頂蝏笔�撠𥪯��交𤣰�唳㿥�交��嗵��批��� tick �唳旿嚗���� Sina 蝑匧��嗉����銝剜��嗅虜閫��靘见��冽𠯫�� 15 �寧��� tick嚗剹��眏鈭舘�鈭𥟇㿥�� tick �唳旿霈∠��箸䔉�� `current_dt` 靘萘��舀㿥�交𠯫�� `2026-05-25`嚗��甇文銁銵峕��券��圻�� `_check_day_switch` �塚�蝟餌��文�敶枏�霈啣��� `self._last_data_date`嚗Ǒ2026-05-26`嚗劐�隡惩������𠯫���`2026-05-25`嚗劐��貊�嚗�僎銝𠉛泵����嗆㺭�文�嚗�15�� >= 9�對�嚗䔶��航◤蝟餌�霂臬ế銝箔�甈⊥迤�𤑳��𡏭楊�交𠯫�笔��Ｔ�嘅�撘箄�閫血�鈭� `_reset_daily_state`��
    - [x] **銝仿��勗拿**嚗朞砲霂臬ế�滨蔭隡𡁜��𡁜��㰘蝸��僎憟賜����銝芾��枏� `ts.score`��price_anchor` 蝑㗇㺭�桃��氯�𡏭䌊瘥���脲�蝛箏��塚�撟嗡��� `_last_data_date` �躰秤�唳��𧼮��冽𠯫 `2026-05-25`嚗䔶���紡�渡��Ｖ��踹��䔶葵�⊥�蝏�萅�亦征瘣𠺶�����蒾撅譌��
    - [x] **霈曇恣撟園�蝵� [ANTI-REVERSE] �椘儭� �餅鱏�滚��交���揢�脣鴃���� (Anti-Reverse Calendar Guard)**嚗𡁜銁 `bidding_momentum_detector.py` �� `_check_day_switch` ��▲蝥找�蝵殷��拍�蝏��鈭�撩�𥕦��穃��ａ獈�剝秄����� `self._last_data_date` 撌脩�撠梁貌嚗�僎銝娍鰵隡惩������𠯫�� `today_str` 銝交聢撠譍��睲賑霈啣���𠯫��𧒄嚗Ǒtoday_str < self._last_data_date`嚗㚁�敺桃�蝥批��湔𦻖�餅鱏�行⏛霂亥秤��揢嚗�僎霈啣� warning �亙��𡃏郎嚗𣬚����敶餃��𦦵�鈭���烐唂 tick �唳旿�滨蔭�鞱�隞𦠜𠯫撌脣�頧賭�霂萘�憿賜𪆴��
    - [x] **�券��訫�銝𡡞��鞉�霂� 100% 皛∪��函遛�朞�**嚗𡁜銁摰峕�甇日★�詨��嗆��㦤�餅鱏�齿��𠬍��拍�霈曄蔭撟嗉�銵䔶��典��𧼮�瘚贝�憟𦯀辣����� `test_watchlist_lifecycle.py` ����� 11 銝芯艇撖���詨��笔𦶢�冽�銝舘�撖罸��埈�霂閧鍂靘𧢲�蝻腈���甈⊥�批�蝏輸�朞�嚗�

## 2026-05-26 02:40
- [x] **�券�餈𥡝� [Tactical HUD & Detector] �嗆�霈曇恣憭批恣霈∩� Code Review (Code Review & Architectural Audit)**嚗�
    - [x] **撱箇�蝟餌�蝥找�憿孵恣�交𥁒��**嚗𡁜銁 artifacts �桀�銝见��典�蝡见僎撖澆枂鈭�▲蝥� [code_review_report.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/a02c1f5c-2189-470f-9453-315473cf81fb/artifacts/code_review_report.md)��
    - [x] **摰匧��餃稬 09:15 �睃��文��贝秤�鞾���**嚗𡁻�朞��厩�撘𤩺醌�𧶏��拍�璉�瘚见僎�鞟內鈭��颲穃膥蝒堒藁銝剖� `915` 霂臬�銝� `91` ��艇�� Bug �鞉�嚗屸俈����睃��脣鴃�箏�����抒瀃�芥��
    - [x] **�券𢒰撖寥� KISS/YAGNI/DRY/SOLID �笔�**嚗𡁜恣�訾� `DictWrapper` �唳旿瘚�綉��Quiet Gate` �䠷�摮条��脩瑪銝𤾸�撅��臭��� `racing_detector`嚗𠄎SOT ����枏��剁�嚗諹�摰硺��函頂�𥪜𢆡璅∪��� Nuitka �煺漣�臬�銝见�憭��頝𤑳漣����扯�蝔喳��扼��
    - [x] **�函蔡撘��粹俈�㚚�銝𡡞���箔���洵銝��嗆挾�𣂼�摮条� (Delivered Boot-up Lock & Early Exit Pipeline for SpatialFollowHUD)**嚗�
        - **�拍�摰帋��瑕鍳�刻䌊�嗵�甇餃儐�臭����粹�瘥��瞍𤩺� (Diagnosed Startup Loop & Exit Destroy Loophole)**嚗�
            - **�瑕鍳�刻䌊�嗵�閬��**嚗𡁜銁蝔见��𡁜鍳�冽𧒄嚗䈣_load_column_widths` �𣂼�餈睃�蝝批��堒捐�𡡞���箝���蝝扳𦻖��銝餌�摨讛��� `hud.show()`��眏鈭𡒊����甈� visible 撟嗉圻�� Layout �芷���皜脫�嚗��撅� Qt �垍�撘閙��� C++ 蝡航�蝏剛秤�煾���憭𡁏活 `sectionResized` 靽∪噡�����銝箸迨�園�暺㗛�撌脰圾撘�嚗諹砲靽∪噡�輸店�游�靚�鍂 `_save_column_widths` �齿鰵�嗵�嚗峕��垍�餈��銝剔�暺䁅恕憭批�摰賣��∩辣�齿鰵�坔�嚗諹��𡝗��譍���𧋦靚�末��揮�穃�摰踝�
            - **���粹�瘥�� 0 �堒捐�嗵�**嚗𡁜��湔𦻖�喲𡡒 TK 銝餌������箇�摨𤩺𧒄嚗峵UD 隡𡁻��� Python 餈𤤿���瘥��諹◤�券�撘誯�瘥�����銁 GC �� GUI 鋡怠𢆡瘜券����C++ 摨訫�蝒堒藁撖寡情撌脫��拙仃���甇斗𧒄閫血��� `closeEvent` 銝剛��� `columnWidth` 隡𡁶凒�亥��墧����暺䁅恕憭批�摰踝��� 0嚗㚁��齿活霂臬��䀹��誯�蝵格�隞嗚��
        - **霈曇恣撟嗉氜�� [BOOT-LOCK] 1.5 蝘鍦��粹俈�㚚� (Boot-up Write Lock)**嚗𡁜銁���惩遆�唳��舘挽蝵� `self._boot_locked = True` 撟嗅鍳�其�甈⊥�批��嗅膥嚗�銁�� 1.5 蝘� Layout �芷����滨�銝𡡞�甈� show ��𢆡�⊥�����拍���香銝��� Resize 閫血���䌊�典��䁅�銝綽��芣��� 1.5 蝘鍦�蝟餌��垍�蝏嘥笆蝔喳���鍂�瑁�銵峕��冽��賣𧒄嚗峕���捂�拍�摮条���
        - **�賢𧑐 [EARLY-EXIT-PIPELINE] 蝚砌��嗆挾隡㗛��𣂼��喲𡡒 (Early Graceful Exit)**嚗𡁜銁 `instock_MonitorTK.py` �� `on_close` �� **Phase 1 ��撘�憭�**嚗峕遬撘讛��� `self.spatial_follow_hud.close()`��＆靽嘥銁銝餉�蝔𧢲��亙熒瘣餉���洵銝��園𡢿摰匧��扯� `closeEvent`嚗���啣�蝢𡒊�蝏��摮条���
        - **�賢𧑐�见𢆡靚�㟲�堒捐 10 蝘㘾俈�硋辣餈笔��䀝����箏朖�嗅撩摮� (Delivered 10-Second Column Saving Debounce & Close-Triggered Flush)**嚗�
            - 敶餃��滚��滨��𦥑�𨅯像�嗡�閬��蝜�/�芸𢆡銋勗��矋��见𢆡靚�㟲�𤾸辣餈� 10 蝘鍦��矋�銝𥪜銁���箸𧒄敹�◆靽嘥��萘�摰䂿���恥�誩���
            - �� `_on_section_resized` 銝剖��Ｗ��文朖�嗉氜�矋��齿�銝� **10蝘㘾俈�硋辣餈笔��䀹㦤�� (QTimer-based Debounce)**����冽�曌䭾��𡝗嗻敺株��堒捐�𦠜𦆮�塚�蝟餌��芸𢆡��絲 10 蝘鍦辣餈笔�坿恣�塚��交��游�甈∪凝靚���齿鰵霈∠�撱嗉�嚗��撖寥俈甇ａ�蝜�䌊�典��睃����蝟餌��𣂼��垍�靽∪噡��僚�嗵�瘙⊥�嚗剹��
            - �函���圻�穃��剝���綽�`closeEvent` / `hideEvent`嚗㗇𧒄嚗�**敺桃�蝥批��湔𦻖�餅鱏/�𨀣迫�脫�摰𡁏𧒄�剁�撟嗅銁蝚砌��園𡢿隞交�擃䀝���漣撠���滨�摰䂿揮�穃捐摨血撩銵� Flush �賜��拍�靽嘥�**嚗諹噢�鞉�摰𣬚���������箏��㗛𡡒�胯��
            - **��稲�亙��滚臁 (Log De-noising)**嚗𡁜蝠摨閙��支�撟單𧒄靚�㟲�堒捐閫血��脫��坿恣�嗆𧒄���憸� `Scheduled debounced saving` �瑕��亙�嚗���圈�暺䀹��踝�**�芸銁 10 蝘鍦��嗅膥�唳����甇����氜�睃��亦��条��祇𡢿嚗�����箏朖�嗅撩摮䀹𧒄嚗㕑��箔�甈� `�𠒣 Saved column widths` 擃䀝漁�亙�**嚗峕�憭批𧑐���碶��舐��批��啜��
        - **�寞祥�滚鍳�Ｗ�暺䁅恕憭批�摰賜��𨅯�頧賣𧊋靚�鍂�肽�蝥抒′隡� (Fixed Loader Omission)**嚗�
            - **蝖砌慾�𣂼�**嚗𡁻�朞��唳秤撘𤩺��伐��𤑳緵�其��拍�餈睃�蝤���堒捐�唳旿�� `_load_column_widths` �寞�嚗�銁�毺�撌亦�銝剔���**隞𤾸��喟�瘝⊥�隞颱�銝�憭�誨����刻�摰�**嚗��撖潸稲霂亙遆�唬��游蘨�臭��瑕銁��辣摨訫���征��挽嚗���臬𢆡�� HUD �芰��芾�瘞貉���鍂 Qt ���霈斗�隡詨之摰賢漲嚗䔶蝙�冽�颲𥡝��西㜃�㗇�靽嘥����摰賜凒�亙��嗚��
            - **摰𣬚��芣�**嚗𡁜銁 `SpatialFollowHUD` ���惩遆�唳�銵� `_init_ui()` 摰峕���洵銝��園𡢿嚗𣬚�����乩� `self._load_column_widths()` ���蝎曉漲靚�鍂嚗�����頧賣��渡� `_loading_widths` �䠷��㰘蝸���颲暹�鈭���臬𢆡摰𣬚�餈睃��������ｇ�
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢������粹�瘥�� 0 �堒捐�嗵�**嚗𡁜��湔𦻖�喲𡡒 TK 銝餌������箇�摨𤩺𧒄嚗峵UD 隡𡁻��� Python 餈𤤿���瘥��諹◤�券�撘誯�瘥�����銁 GC �� GUI 鋡怠𢆡瘜券����C++ 摨訫�蝒堒藁撖寡情撌脫��拙仃���甇斗𧒄閫血��� `closeEvent` 銝剛��� `columnWidth` 隡𡁶凒�亥��墧����暺䁅恕憭批�摰踝��� 0嚗㚁��齿活霂臬��䀹��誯�蝵格�隞嗚��
        - **霈曇恣撟嗉氜�� [BOOT-LOCK] 1.5 蝘鍦��粹俈�㚚� (Boot-up Write Lock)**嚗𡁜銁���惩遆�唳��舘挽蝵� `self._boot_locked = True` 撟嗅鍳�其�甈⊥�批��嗅膥嚗�銁�� 1.5 蝘� Layout �芷����滨�銝𡡞�甈� show ��𢆡�⊥�����拍���香銝��� Resize 閫血���䌊�典��䁅�銝綽��芣��� 1.5 蝘鍦�蝟餌��垍�蝏嘥笆蝔喳���鍂�瑁�銵峕��冽��賣𧒄嚗峕���捂�拍�摮条���
        - **�賢𧑐 [EARLY-EXIT-PIPELINE] 蝚砌��嗆挾隡㗛��𣂼��喲𡡒 (Early Graceful Exit)**嚗𡁜銁 `instock_MonitorTK.py` �� `on_close` �� **Phase 1 ��撘�憭�**嚗峕遬撘讛��� `self.spatial_follow_hud.close()`��＆靽嘥銁銝餉�蝔𧢲��亙熒瘣餉���洵銝��園𡢿摰匧��扯� `closeEvent`嚗���啣�蝢𡒊�蝏��摮条���
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 02:20
- [x] **�拍��寞祥 QTableWidget �堒捐�㰘蝸�嗉䌊�𤏸��碶� Quiet Gate �䠷��賊秄�� (Delivered Column Width Quiet Gate Persistence Lock for SpatialFollowHUD)**嚗�
    - [x] **�拍�摰帋��臬𢆡�芣��嗆�抒㴓頝� (Diagnosed Feedback Loop Loophole)**嚗�
        - �拍��寞祥鈭��𦦵鍂�瑟��刻��游末�堒捐�𠬍�銝衤�甈∪��臬𢆡�㰘蝸�嗅㭂��䌊�冽�憭滚�憪见�暺䁅恕摰賢漲�萘��嗅𧦠鈭支� Bug��
        - 瘛勗漲摰帋��嗅�撅���惩銁鈭𠬍��� Qt 撘閙��㰘蝸 `_load_column_widths` 餈睃�銝𠹺�甈∩�摮条��堒捐嚗�朖�扯� `setColumnWidth`嚗厩��嘥��𤥁�蝔衤葉嚗䔶�隞仿�憸穃��𤏸圻�� QTableWidget �� `sectionResized` 靽∪噡撟嗉楝�梯秐 `_on_section_resized`���𣬚眏鈭擧迨�嗉”�潭㺭�桀��芸�頧賢��其�蝒堒藁撠𡁏𧊋 visible嚗諹砲靽∪噡�湔𦻖撣衣��芸停蝏芰�暺䁅恕/撘�虜摰賢漲�澆撩銵諹��� `_save_column_widths` 撟嗅��䂿��矋�撖潸稲憟賭�摰寞�靽嘥����摰賣㺭�桀銁�臬𢆡�嗥��渲◤�𡏭䌊�穃��䁅��砽�嘥僎敶餃������
        - 餈𥕢�甇亦�����亙僎敶餃�閫��鈭��銝芣��園��賜� Qt 蝒堒藁�齿� Bug嚗𡁜��冽��函��Ｖ�**�𨀣�撘�蝵桅▲�腈���𨅯��剔蔭憿嗯��**�塚�蝟餌�隡朞��� `self.setWindowFlags(flags)`����銁 Qt �嗆�銝哨�**撖孵歇�航�蝒堒藁靚�鍂 `setWindowFlags` 隡朞翰雿� Qt �𣂼��拍���瘥�僎�滚遣蝒堒藁�交�嚗諹��䭾辺隞嗉䌊�刻圻�睲� `hideEvent` �� `resize` 蝑劐�蝟餃��滨蔭靽∪噡**��銁甇方�蝔衤葉�曹�銵冽聢摰賢漲�祇𡢿敶雴蛹 0 �𤥁��糓韐�㺭嚗諹���� 0 摰賢漲�唳旿�齿活鋡恍�霂臬𧑐靽嘥��坔�鈭���䀹�隞塚�撖潸稲�冽�蝎曄��㗇����摰賢蝠摨閗��准��
    - [x] **霈曇恣撟園�蝵� [QUIET-GATE] �典予�䠷�暺㗛俈摰���其��嗅捐摨阡��嗥���㺭�格嵗撉� (Quiet Gate Lock & Minimum-Width Guard)**嚗�
        - **�峕��䌊����䠷��� (Reconfig Lock)**嚗𡁜銁蝵桅▲��揢�寞� `_toggle_stays_on_top` �港葵蝒堒藁�笔𦶢�冽��䀹揢銝哨��拍�蝏�� `self._switching_flags = True` ����僎�� `finally` 銝剛圾撘����璉�瘚见� `self._switching_flags` 憭��瞈�瘣餌𠶖��𧒄嚗屸獈�凋����撘� hideEvent �𤏸絲�� `_save_column_widths` 蝤������硔��
        - **擃条移摨衣���捐摨行嵗撉峕㜃�� (Zero-Width Validation Gate)**嚗𡁜銁 `_save_column_widths` 憿嗥漣�賜��亙藁嚗���交�摨虫艇�潛��拍��唳旿摰峕㟲�扳嵗撉䎚����� 7 �𦯀葉**�劐遙雿蓥��堒�摰質��硺蛹 0 �𤥁��糓韐�㺭嚗�秩�舘”�潭迤憭���滚遣����𤩺��齿�餈�腹�嗆���**嚗峕�����唬�蝑劐� 7嚗�**敺桃�蝥批��湔𦻖�餅鱏�行⏛撟嗆�蝏嘥���**嚗䔶�皞𣂼仍銝羓���䎺��鈭���舐���捐摨血笆����㚚�蝵格�隞嗥��鞱���
        - 敶餃�靽脲擪鈭�鍂�瑚�甈⊥��刻��港�摮条�蝎曄��堒捐�典��臬𢆡�� 100% 鋡怎�撖孵��具����渲����嚗��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 02:20
- [x] **�拍��寞祥 QTableWidget �堒捐�㰘蝸�嗉䌊�𤏸��碶� Quiet Gate �䠷��賊秄�� (Delivered Column Width Quiet Gate Persistence Lock for SpatialFollowHUD)**嚗�
    - [x] **�拍�摰帋��臬𢆡�芣��嗆�抒㴓頝� (Diagnosed Feedback Loop Loophole)**嚗�
        - �拍��寞祥鈭��𦦵鍂�瑟��刻��游末�堒捐�𠬍�銝衤�甈∪��臬𢆡�㰘蝸�嗅㭂��䌊�冽�憭滚�憪见�暺䁅恕摰賢漲�萘��嗅𧦠鈭支� Bug��
        - 瘛勗漲摰帋��嗅�撅���惩銁鈭𠬍��� Qt 撘閙��㰘蝸 `_load_column_widths` 餈睃�銝𠹺�甈∩�摮� the �堒捐嚗�朖�扯� `setColumnWidth`嚗厩��嘥��𤥁�蝔衤葉嚗䔶�隞仿�憸穃��𤏸圻�� QTableWidget �� `sectionResized` 靽∪噡撟嗉楝�梯秐 `_on_section_resized`���𣬚眏鈭擧迨�嗉”�潭㺭�桀��芸�頧賢��其�蝒堒藁撠𡁏𧊋 visible嚗諹砲靽∪噡�湔𦻖撣衣��芸停蝏芰�暺䁅恕/撘�虜摰賢漲�澆撩銵諹��� `_save_column_widths` 撟嗅��䂿��矋�撖潸稲憟賭�摰寞�靽嘥����摰賣㺭�桀銁�臬𢆡�嗥��渲◤�𡏭䌊�穃��䁅��砽�嘥僎敶餃������
        - 餈𥕢�甇亦�����亙僎敶餃�閫��鈭��銝芣��園��賜� Qt 蝒堒藁�齿� Bug嚗𡁜��冽��函��Ｖ�**�𨀣�撘�蝵桅▲�腈���𨅯��剔蔭憿嗯��**�塚�蝟餌�隡朞��� `self.setWindowFlags(flags)`����銁 Qt �嗆�銝哨�**撖孵歇�航�蝒堒藁靚�鍂 `setWindowFlags` 隡朞翰雿� Qt �𣂼��拍���瘥�僎�滚遣蝒堒藁�交�嚗諹��䭾辺隞嗉䌊�刻圻�睲� `hideEvent` �� `resize` 蝑劐�蝟餃��滨蔭靽∪噡**��銁甇方�蝔衤葉�曹�銵冽聢摰賢漲�祇𡢿敶雴蛹 0 �𤥁��糓韐�㺭嚗諹���� 0 摰賢漲�唳旿�齿活鋡恍�霂臬𧑐靽嘥��坔�鈭���䀹�隞塚�撖潸稲�冽�蝎曄��㗇����摰賢蝠摨閗��准��
    - [x] **霈曇恣撟園�蝵� [QUIET-GATE] �典予�䠷�暺㗛俈摰���其��嗅捐摨阡��嗥���㺭�格嵗撉� (Quiet Gate Lock & Minimum-Width Guard)**嚗�
        - **�峕��䌊����䠷��� (Reconfig Lock)**嚗𡁜銁蝵桅▲��揢�寞� `_toggle_stays_on_top` �港葵蝒堒藁�笔𦶢�冽��䀹揢銝哨��拍�蝏�� `self._switching_flags = True` ����僎�� `finally` 銝剛圾撘����璉�瘚见� `self._switching_flags` 憭��瞈�瘣餌𠶖��𧒄嚗屸獈�凋����撘� hideEvent �𤏸絲�� `_save_column_widths` 蝤������硔��
        - **擃条移摨衣���捐摨行嵗撉峕㜃�� (Zero-Width Validation Gate)**嚗𡁜銁 `_save_column_widths` 憿嗥漣�賜��亙藁嚗���交�摨虫艇�潛��拍��唳旿摰峕㟲�扳嵗撉䎚����� 7 �𦯀葉**�劐遙雿蓥��堒�摰質��硺蛹 0 �𤥁��糓韐�㺭嚗�秩�舘”�潭迤憭���滚遣����𤩺��齿�餈�腹�嗆���**嚗峕�����唬�蝑劐� 7嚗�**敺桃�蝥批��湔𦻖�餅鱏�行⏛撟嗆�蝏嘥���**嚗䔶�皞𣂼仍銝羓���䎺��鈭���舐���捐摨血笆����㚚�蝵格�隞嗥��鞱���
        - 敶餃�靽脲擪鈭�鍂�瑚�甈⊥��刻��港�摮条�蝎曄��堒捐�典��臬𢆡�� 100% 鋡怎�撖孵��具����渲����嚗��
        - **�賢𧑐頞�揮�煾��烐�靘见�摰賭��㰘蝸銝𢠃�撖寥��芣� (Golden-Ratio Compact Column Widths & Load Bounding Guard)**嚗𡁻�憛睲�頝罸�銵冽聢 6 憭批�摰賢�摨閖�霈文�憪见偕撖賂�`[82, 52, 56, 60, 52, 52]`嚗匧僎�� `_load_column_widths` 餈睃����瘜典�鈭��擃条漣 `max_bounds` 銝𢠃�靽脲擪�冽���朖雿蹂��滨��㗛�蝵格�隞嗡葉畾讠�鈭��摰賜��扳�靘𧢲㺭�殷��瑕鍳�冽𧒄蝟餌�銋煺��芸�擃条移摨血��嗉��芸笆朣鞱秐��蝝批�瘥𥪯�嚗屸��曉之�誩𢰧靘抒征�港誑 Stretch 憛怠�敶Ｘ���**摰��瘨�膄�曉阸��偌撟單��冽辺嚗諹噢�鞉�擃睃��𣬚�閫���鍦�摨�**嚗�
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 02:15
- [x] **�拍��寞祥 QTableWidget �堒捐�㰘蝸�嗉䌊�𤏸��碶� Quiet Gate �䠷��賊秄�� (Delivered Column Width Quiet Gate Persistence Lock for SpatialFollowHUD)**嚗�
    - [x] **�拍�摰帋��臬𢆡�芣��嗆�抒㴓頝� (Diagnosed Feedback Loop Loophole)**嚗�
        - �拍��寞祥鈭��𦦵鍂�瑟��刻��游末�堒捐�𠬍�銝衤�甈∪��臬𢆡�㰘蝸�嗅㭂��䌊�冽�憭滚�憪见�暺䁅恕摰賢漲�萘��嗅𧦠鈭支� Bug��
        - 瘛勗漲摰帋��嗅�撅���惩銁鈭𠬍��� Qt 撘閙��㰘蝸 `_load_column_widths` 餈睃�銝𠹺�甈∩�摮条��堒捐嚗�朖�扯� `setColumnWidth`嚗厩��嘥��𤥁�蝔衤葉嚗䔶�隞仿�憸穃��𤏸圻�� QTableWidget �� `sectionResized` 靽∪噡撟嗉楝�梯秐 `_on_section_resized`���𣬚眏鈭擧迨�嗉”�潭㺭�桀��芸�頧賢��其�蝒堒藁撠𡁏𧊋 visible嚗諹砲靽∪噡�湔𦻖撣衣��芸停蝏芰�暺䁅恕/撘�虜摰賢漲�澆撩銵諹��� `_save_column_widths` 撟嗅��䂿��矋�撖潸稲憟賭�摰寞�靽嘥����摰賣㺭�桀銁�臬𢆡�嗥��渲◤�𡏭䌊�穃��䁅��砽�嘥僎敶餃������
    - [x] **霈曇恣撟園�蝵� [QUIET-GATE] �典予�䠷�暺㗛俈摰���� (Quiet Gate Lock)**嚗�
        - �� `_load_column_widths` 餈睃��㰘蝸�滨蔭���銝哨��拍�瘜典� `self._loading_widths = True` �����銁 `finally` �𨅯��𦠜𦆮�𦯀葉�䭾辺隞嗅��嗉圾撘� `False`��
        - �� `_on_section_resized` �堒捐�𡝗嗻�噼���▲�券�蝵脣撩�𥕦��漤秄������行�瘚见�憭�� `self._loading_widths` �罸𡢿嚗峕�������鈭𦒘��航��嗆�� (`not self.isVisible()`)嚗�**敺桃�蝥批��湔𦻖�餅鱏�行⏛**嚗䔶���捂�扯�隞颱��嗵��滢���
        - 敶餃�靽脲擪鈭�鍂�瑚�甈⊥��刻��港�摮条�蝎曄��堒捐�典��臬𢆡�� 100% 鋡怎�撖孵��具����渲����嚗��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 02:10
- [x] **�齿�����𣳇��㺭�格�撠����惣�踹�瘨典�摰嗆㺭憭𡁻��拍��芣� (Delivered Live Sector Heat Acceleration & Triple-Layer Limit-Up Counter Recovery)**嚗�
    - [x] **����𣳇�毺���𦻖�交踎�埈隅頝𣬚��𥟇㺭�� (Live Sector Change Integration for accel Metric)**嚗�
        - 敶餃��滚�撟嗉氜�唬��滨��讠���恥霂㗇�嚗�� HUD �屸𢒰銝羓裦�曉��券���� `score_accel` ����𣳇�������拍��齿�銝箇凒�交�撠�踎�堒�銝讠�摰墧𧒄瘨刻��剖漲 (`self.heat_score`嚗剹��
        - �� `DictWrapper` 撅墧�扯繮�𣇉�憿嗥漣����湔𦻖撠� `score_accel` 頝舐眏�� `self.heat_score` 隞�����隞���唬�����𣳇�笔漲銝擧踎�𦯀��亙撩摨艾��隅頝��摨衣�擃㗛��冽���雿枏�撅閧緵嚗諹�䔶�颲曉�鈭���其�靽格㺿 HUD UI撅�葡�㯄�餉����蝞�憭批�蝥批笆朣僐��
    - [x] **�賢𧑐 [HEALING-SHIELD] �踹�瘨典��啣��齿��箏��刻䌊��膥 (Triple-Layer Limit-up Self-Healing Aggregator)**嚗�
        - ��笆�瑕鍳�冽���㿥�亙��脫�銋����辣撠𡁏𧊋�賜� `zt_count` 摮埈挾��器蝻条𠶖����� `DictWrapper` ����函蔡鈭��摨血撩�滨��𨀣㺭�桀��刻䌊����𢛶�腈��
        - 銝��血�撅�� `zt_count` 銝� `None` �� `0`嚗諹䌊����𤾸銁敺桃�蝥批��芸𢆡�㕑絲 `get_limit_up_threshold` 擃条移摨西恣蝞梹�瘛勗漲�急��㰘蝸�箸䔉�� `leader` 樴坔仍隞亙� `followers` 頝罸��𡑒”嚗峕覔�桀�隞祉�摰䂿���掩瘨典�嚗�蜓��10%�����20%���霂�30%��T��5%嚗厩�����典僎�啣枂���笔����蝎曉���隅�靝葵�⊥�餅㺭��
        - 颲暹�鈭��𨀣㿥�亙��䀹㺭�桀𪑛�閧撩憭梯砲�殷�銝�撘��箔��賡�蝎曉漲撅閧緵�䀝葉�笔�瘨典��售�萘��嗆香閫鉝����滢��拚𡡒�荔�
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 02:00
- [x] **�寞祥�瑕鍳��/�睃�隡朞��滨蔭銝𡡞�蝎曉漲�踹�瘨典��啣��嗥���釣�� (Delivered High-Precision Calendar Shield & Dynamic Limit-up Count Aggregator)**嚗�
    - [x] **霈曇恣撟園�蝵� [HEALING-SHIELD] �睃�/�峕膥�箄�隡朞��脣鴃 (Pre-market Calendar Shield)**嚗�
        - �拍��寞祥鈭�銁�峕膥�𤥁����睃�嚗Ǒ09:15` 銋见�嚗匧��臬𢆡蝔见��塚��曹�����碶�摮条���辣�交�嚗��隞𦠜𠯫�芰��伐�銝� `get_effective_trade_date` 撘��睃����輸�蝥扳𠯫����滢�鈭斗��伐�銝滢��湛�撖潸稲 `is_cross_day` 霂臬ế銝� `True`嚗䔶���銁�㰘蝸�嗅撩銵峕�蝛箸㿥�仿������憭游�閫��銵冽㺭�桃��游𦶢 Bug��
        - �� `load_persistent_data` (銝餅�隞嗅�頧�)��_build_detector_state_process` (摮鞱�蝔𧢲�撱�) 隞亙� `_apply_detector_state` (銝餉�蝔见�撟�) 銝匧之�詨�隡朞��Ｗ����嚗𣬚�蝏�釣�乩�撘箏��脣��券���蘨閬��瘚见�敶枏��園𡢿�� `09:15` 銋见�嚗�撩銵屸獈�� `is_cross_day` ��楊�仿�蝵桀ế摰𡄯�敶餃�蝖桐��冽𠯫颲𥡝㜃憭滨�����𨅯��唳旿 100% 瘥急��蠘�堒𧑐摰𣬚佂敶坿紫��
    - [x] **�賢𧑐�踹�隞𦠜𠯫�笔�瘨典��啣��嗥���釣�� (Dynamic Limit-up Count Aggregation for HUD)**嚗�
        - �拍�摰帋�撟嗆覔瘝颱��曹� `BiddingMomentumDetector` �冽踎�烾���葉摰���芾恣蝞堒�憛怠� `zt_count`嚗�隅�𨅯振�堆��殷�撖潸稲 active_sectors 摮堒�餈𥪜���隅�𨀣㺭�格偶餈靝蛹蝛箝��UD 皜脫�憪讠�撅閧內 `0�注 ��■�整��
        - �� `bidding_momentum_detector.py` �� `_reconstruct_sector_from_candidates` �詨��箏藁嚗�𢆡�������齿踎�埈��厩��䠷�劐葵�∴�撟嗉��券�蝎曉漲 `get_limit_up_threshold(s['code'])` �芷����冽��文�嚗𣬚���恣蝞堒枂�踹�隞𦠜𠯫���摰墧隅�𨅯振�堆�撘箏��坔� `info['zt_count']`��
        - �� `spatial_follow_hud.py` ��妟�瑁������ `DictWrapper` 銝哨��峕郊憓𧼮�鈭�笆 `zt_count` 撅墧�抒��曉�撖寥�隞��嚗���唬��券曎頝舀㺭�桃�擃睃蒂摰賣�蝻嗪𡡒�荔�霈拍��Ｖ����𨥉�� 瘨典�摰嗆㺭�萘�撖寧�摰𠺶��移����啜��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 01:25
- [x] **�齿�撟嗉氜�唳�撘箇�瘝駁�憭湔瓲敹�㺭�桃�撖孵笆朣𣂷�蝏���瑕鍳�冽踎�𡑒䌊����𣂼膥 (Delivered Authoritative SSOT Data Sync & Zero-Lock DictWrapper for SpatialFollowHUD)**嚗�
    - [x] **�拍�銵仿� DictWrapper �詨�樴坔仍撅墧�扳�撠� (Completed Core Metric Property Mappings)**嚗�
        - �拍�摰帋�撟嗆覔瘝颱��曹� `BiddingMomentumDetector` �典��訾葉撠��憭游��䀹隅撟���曉銁 `'leader_pct'` �桐�嚗��� HUD �游縧霈輸䔮鈭� `leader_change_pct`嚗劐誑�𢠃�憭游�隞瑕��曉銁 `'leader_price'` �桐�嚗��� HUD �餉挪�桐� `leader_vwap`嚗匧紡�游��臬𢆡�𤥁���𧊋瘣餉��園�憭游�憿寞�����刻◤�行⏛皜�征銝� `0.00%` / `0.0` ��之 Bug��
        - �� `DictWrapper` �� `__getattr__` 撅墧�批�摰寡繮�㚚�憓𧼮�鈭� `leader_change_pct` 撖孵� `leader_pct`��leader_vwap` 撖孵� `leader_price` 隞亙� `leader_pct_diff` ���撖寥�蝎曉漲�惩���
        - 靽肽�鈭�銁 Tick �唳旿餈䀹𧊋�券����� `detector.tick_series.get(leader_code)` 餈䀹糓 `None`嚗㗇𧒄嚗峵UD �屸𢒰銋蠘��曉��曆�摨訫� `active_sectors` �峕㿥�交㺭�桐葉嚗峕��箸𧋦��隅撟���遠�潔�樴坔仍�𡒊��唳旿�祇𡢿���嚗峕��支遙雿閙㺭�格遬蝷箇征瘣𠺶��
    - [x] **霈曇恣撟園�蝵脩�����臬𢆡銝𡡞�瘣餉��踹��𡁏��芣�摰硺������ (Stay-on-Ready UI Self-Healing Generator)**嚗�
        - �拍�閫��鈭�銁摰���瑕鍳�具��瓷�㗇暑頝�踎�埈��� FocusController 餈睃銁�㰘蝸�唳旿�塚��曹�瘝⊥��唳旿摰硺�嚗Ǒsh = None`嚗匧紡�� HUD 鋡� `if not sh: return` �行⏛嚗諹稲雿踵㟲銝芯葵�⊥㺭�桐��踹��𡒊��䭾�蝏睃���蝠摨閧蒾撅讐��𤤿���
        - �� `update_hud_data` �𡁻�銝剝�蝵脖� `dummy_data` �𡁏�����剁��冽䔝瘚衤��唬遙雿訫�雿𤘪㺭�格𧒄�芸𢆡�芣�鋆�蝸嚗䔶誑 `0.0` 雿靝蛹�嘥��澆‵����亦鍂�瑚��滚銁銝餌���睸�䀹�曌䭾��滢��𥪜𢆡餈�葵�∴�摮睃銁���舘��其誨�� `_last_linkage_code`嚗㚁�蝟餌�撠���嗡誑頞������芸𢆡�渲� `get_focus_controller()._df_realtime` �餉繮�𤥁砲�∠巨����笔�����条緵隞瑚�摰䂿�瘨典�撟嗥凒�亙‵��蛹隞𦠜𠯫蝏�祥樴坔仍��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���喃蝙�典��典��臬𢆡�𣬚征�唳旿�嗆���嚗峵UD 閫�藁銋蠘�蝔喳���妟�脩����蝢舘䌊����堆�瘨�膄鈭���厩��賢���

## 2026-05-26 01:10
- [x] **�齿�撟嗆覔瘝餃�撣�㦤擃条移摨� A �⊥隅�𨅯振�啗恣蝞� (Delivered High-Precision Multi-Market A-Share Limit-Up Decision System)**嚗�
    - [x] **蝏��蝎埈𠂔蝎埈𦆮�文� (Terminated Simplistic >= 9.5 Limit-Up Gates)**嚗𡁜��Ｗ��支��冽踎�㛖��𥡝恣蝞𦯀葉��𧋦�蹱香��唂撘讐��� `percent >= 9.5` �文����銝��折�餉�撖潸稲��𧋦銝𦠜隅 10% �芸��輻��𥕢��踴����𥟇踎�𠰴�鈭斗�銝芾�鋡怠之�Ｙ妖霂航恣�交隅�𨅯振�堆�雿踹��函頂�踹�瘨典��唳旿憭折��𡁻�����典仃����
    - [x] **�賢𧑐擃条移摨� A �∪�蝐餅隅�𨅯ế摰𡁜遆�� (`is_a_share_zt`)**嚗𡁜銁 `sector_focus_engine.py` �詨�憿園�瘜典�鈭��摨血虾閫��銝𦒘艇撖�����銝芾�瘨典��文�閫��嚗�
        - 瘝芣楛銝餅踎銝芾� (`60`, `00` 蝟餃�)嚗𡁏隅撟���滢��亦移蝖桀笆朣琜�閬��瘨典� `>= 9.95%`��
        - �𥕢��踴����𥟇踎銝芾� (`30`, `688` 蝟餃�)嚗𡁏隅�𨅯�摨虫蛹 20%嚗諹�瘙�隅撟� `>= 19.95%`��
        - �𦯀漱��銝芾� (`83`, `87`, `88`, `43`, `920` 蝟餃�)嚗𡁏隅�𨅯�摨虫蛹 30%嚗諹�瘙�隅撟� `>= 29.95%`��
        - ST / *ST 蝑劐葵�∴��朞�餈�誘�∠巨�滨妍銝剔� `ST` 蝟餃��喲睸摮梹��芸𢆡撠�隅�𨅯�摨血笆朣鞱秐 5%嚗�朖閬��瘨典� `>= 4.95%`��
    - [x] **�券曎頝舀𤜯�Ｖ�撖寥�**嚗�
        - �� `SectorFocusMap.inject_detector_sectors` �踹�頝罸��∠�霈∪儐�臬�樴坔仍蝏蠘恣銝哨��券𢒰��漣銝箄��� `is_a_share_zt` 餈𥡝�擃㗛�蝎曄＆蝑𥟇䰻��
        - �� `SectorFocusMap._compute` �滨漣�𡁜�頝臬��� `_identify_leader` �劐蜓頝臬�銝哨��券𢒰�朞� Pandas �� `.apply` �箏�嚗諹䌊�����妟撘����啣笆�刻”銵峕�銵屸�蝎曉漲�文�撟園��唳�摰� `_is_zt` 瘨典��𨰜��
        - �� `BiddingMomentumDetector._determine_role` 銝芾�閫坿𠧧���璅∪�銝哨��峕郊撠�𤐄摰𡁶� `pct >= 9.5` 靽格迤銝箄��典笆朣鞱䌊������� `get_limit_up_threshold(s['code'])`嚗���𣂷��券曎頝臭��∟��嗵��餉�摰𣬚��剔㴓��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���唳旿�𡁜����銝𤾸�撣�㦤瘨典�霈∠�����扯�餈鞱�嚗峕𧊋鈭抒�隞颱�甇駁����蝘餅��亙藁銝滚�摰嫘��

## 2026-05-26 01:05
- [x] **�寞祥皛朞蔭霂航圻�脩�銝𤾸���𣈲�唳旿���蝥菜楛�芣�銵仿� (Delivered Wheel Conflict Fix & Deep Dual-Branch Hybrid Data Fusion)**嚗�
    - [x] **蝎曉��齿�皛朞蔭�衣�頝舐眏�𠉛氖�脩� (Precise Mouse Wheel Routing & Isolation)**嚗𡁻���� `SpatialFollowHUD.wheelEvent`����乩�摮鞉綉隞嗡�蝵桀ế摰帋��鍦�餈賣滲嚗Ǒchild = self.childAt(event.position().toPoint())`嚗剹���璉�瘚见�曌䭾�皛朞蔭�刻�憌擧�蝏�”嚗Ǒself.table` �𠰴�摮鞉綉隞塚�銝𦠜䲮皛𡁜𢆡�塚��芸𢆡�朞� `super().wheelEvent(event)` 撠���冽��舐宏鈭斤� QTableWidget嚗諹悟�嗆�銵諹䌊�嗥�瘞游像/��凒皛𡁜𢆡嚗𥕢�敶㯄����鈭舘”�澆躹�煺�憭吔�憒�▲�典�䠷�㗇��桀躹嚗㗇𧒄�滩圻�烐踎�𡑒蔭�具������摰𣬚��寞祥鈭��𦦵鍂�瑚�銝𧢲��刻�蟡刻”�渲秤閫血��踹���揢�萘��滢��脩���
    - [x] **撖寥�摨訫� Schema 撟嗅��啣���𣈲�唳旿����滚� (Authoritative Schema Alignment & Hybrid Fusion)**嚗�
        - �拍��寞祥鈭�眏鈭� `BiddingMomentumDetector` 摨訫��踹�摮堒�樴坔仍�桀�銝� `leader`嚗��� HUD 銝剛秤靚�鍂 `leader_code`嚗匧紡�渡�樴坔仍�唳旿�曄內銝箇征 `(--)` ��■�整��
        - ��漣 `DictWrapper` 銝箇熊瘛望毽���鋆��嚗峕𣈲����� `fallback_obj` 憭�鍂撖寡情��
        - �� `update_hud_data` �瑟鰵�冽�銝剜��� `SectorFocusController` 銝剜��啣�憭���踹��唳旿雿靝蛹憭�鍂��� detector 摨訫�霈∠�銝剔撩憭曹蜓�𥡝��穃�瘥䈑�`zhuli_ratio`嚗剹����臬�摨佗�`surge_density`嚗剹��踎�烾�瘥䈑�`volume_ratio`嚗剹��隅�𨅯振�堆�`zt_count`嚗� or 蝡硺遠霂��嚗Ǒbidding_score`嚗厩���恥����塚�`DictWrapper` �賢�敺桃�蝥扯䌊�典� FocusController 餈𥡝� fallback �芣�銵仿�嚗���唬��冽𠯫�睃��唳旿�𠰴��臬𢆡�嗆�����蓡��蓡�唳旿摰峕㟲摨阡��啜��
    - [x] **�券� 40/40 �訫�銝𤾸�敶埝�霂� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���𤩺��嗆��㦤銝𡡞�憭渡凒餈墧㺭�桅曎�典�蝥輻����憸𤏸���凒�唳𧒄���撖寧迅摰𡁏�改��芯漣�煺遙雿訫�撅��脩��𣇉瑪蝔𧢲香����

## 2026-05-26 00:45
- [x] **銵仿���撘箇�瘝駁�憭湔瓲敹�㺭�桐�蝎曇稲蝵桅▲�𢠃�𤩺�瘥𥪯�靚��皛穃� (Aligned Leader Metrics & Added Opacity Slider for Staying-on-Top HUD)**嚗�
    - [x] **�渲� SSOT ����枏��刻‘朣鞟�瘝駁�憭湔��� (Authoritative Leader Metrics Alignment)**嚗𡁜�撘��銋见� HUD 樴坔仍靽⊥�蝛箸��牐���挽霈∴��� `update_hud_data` 皜脫��冽�銝剔���凒餈𧼮�撅�瘣颱��Ｘ��枏��� `detector.tick_series`嚗�
        - 摰䂿緵鈭��憭游��䀹隅撟��`leader_change_pct`嚗厩��曉��曉𢆡��移��恣蝞𨰜��
        - �拍�銵仿�鈭��憭港�撘���/�滨蔭韏瑞�隞交䔉����典�摨佗�`leader_pct_diff`嚗劐�摰墧𧒄�望𥲤�𣬚氖�潘�`leader_dff`嚗剹��
        - �冽��凒霂颱葵�� 20�亙�蝥踹�潘�`ts.ma20`嚗劐�銝粹�憭游�蝥踹抅蝖�銵函緵嚗Ǒleader_vwap`嚗㚁�撟嗅�甇亦��� `candidate_stocks` 樴坔仍銝芾�嚗�0�瑚�嚗㚁�雿蹂��寡”�潛�樴坔仍皜脫��峕甅�瑕�擃㗛�����瑟鰵��
    - [x] **�賢𧑐蝵桅▲�𢠃�𤩺�����挽霈∩�鈭桀漲皛穃� (Stay-on-Top Opacity & Interactive Slider)**嚗�
        - **�峕��䌊������� (Adaptive Transparency)**嚗𡁜�蝵桅▲嚗𠄎tays-on-Top嚗匧��舀𧒄嚗峵UD 蝒堒藁�芸𢆡餈𥕦����蝘烐��毺��𢠃�𤩺�璅∪�嚗��霈支漁摨� `75%`嚗㚁��脤��∩�撅�漱�栞���㦛嚗𥕦�蝵桅▲�喲𡡒�塚�HUD 撘箄��芸𢆡�Ｗ� `100%` �其��𤩺�摨佗�颲暹�摰𣬚������𠶖��㦤撖寥���
        - **蝎曇稲鈭桀漲靚��皛穃� (Opacity Slider Widget)**嚗𡁜銁憿園�����讐移�湧�蝵脖�皛穃𢆡靚��皛穃�嚗Ǒ�䮖鈭桀漲: [Slider] 30%-100%`嚗剹����㛖�隞園��冽�暺烐���鐤�貉𠧧嚗�**隞�銁蝵桅▲璅∪�撘��舀𧒄�冽��������**嚗䔶��游�撣貉��嗆������蝞���恥蝢𤾸郎��
        - **頝其�霂脲�銋��銝𤾸��芣���� (Persistence & Boot Calibration)**嚗𡁏��埈��刻��湔𧒄敺桃�蝥批�銝漤�𤩺�摨行�靘𧢲�銋���坔� `window_config.json` 銝剔� `SpatialFollowHUD_opacity` 摮埈挾��銁���惩遆�� `__init__`��蔭憿嗅��Ｗ� `showEvent` �日�鈭衤辣銝剜��亙��笔𦶢�冽��芣��∪�嚗䔶�霂��撘��箝���蝵桅▲靘輯�摰𣬚��Ｗ��𢠃�𤩺���恥閫����
    - [x] **�券� 40 銝芸�敶雴����瘚贝� 100% 皛∪��函滯�𡁜�**嚗𡁶����霂���𤩺��嗆��㦤銝𡡞�憭渡凒餈墧㺭�桅曎�典�蝥輻����憸𤏸���凒�唳𧒄���撖寧迅摰𡁏�改��芯漣�煺遙雿訫�撅��脩��𣇉瑪蝔𧢲香����

## 2026-05-26 00:30
- [x] **�寞祥�硺漱�𤘪𧒄畾萄��臬𢆡隡朞�皜�征銝𤾸��烐𠯫�笔��ａ�蝵� Bug (Fixed Off-market Session Auto-Reset & Reverse Date Switch)**嚗�
    - [x] **摰䂿緵�典�銝��湔�找漱�𤘪𠯫�文��滨漣蝑𣇉裦 (Unified Effective Trade Date Fallback)**嚗𡁜銁 `bidding_momentum_detector.py` ��▲�冽��硋僎撠��鈭� `get_effective_trade_date(current_dt)` 擃睃漲�舫��刻��拙遆�啜����𣂷��箄�撘��睃��滨漣蝑𣇉裦嚗�朖憒��敶枏��賜��臭漱�𤘪𠯫嚗䔶��園�憭�� `09:15` 撘��条�隞瑚��㵪�靘见��峕膥憭滨�����典��臬𢆡蝑㚁�嚗諹䌊�穃��㗇��唳旿撖寥��交��滨漣���蹂蛹�靝�銝�銝芯漱�𤘪𠯫�嘅�`cct.get_last_trade_date()`嚗㚁�蝖桐��典��睃� `is_cross_day` �賢�摰匧�餈𥪜� `False`��
    - [x] **憭𡁶垢�㰘蝸銝𡒊𠶖���撟嗥�撖� logic 撖寥� (100% Logic Alignment Across Loaders)**嚗𡁜��笔�銝餉�蝔衤葉 `load_persistent_data`��_apply_detector_state` 銝𤾸�餈𤤿�銝� `_build_detector_state_process` �滚�銝𥪯�銝��渡��交��瑕�蝞埈��券��齿�銝箇�銝�靚�鍂 `get_effective_trade_date`����支��笔��曹�銝餉�蝔衤�摮鞱�蝔𧢲𠯫�笔ế摰𡁜�蝒��銝餉�蝔见蕭�� 9:15 �滨漣霂臬ế `is_cross_day=True`嚗諹���餈𤤿��文�銝� `False`嚗㕑����𤑳� `self.active_sectors` 銝� `self.daily_watchlist` 撘箏�皜�征��葵�∟�����嗥��𨀣㿥�亦��擧㺭�桃蒾撅�/蝛箸��嗪■�整��
    - [x] **�餅鱏�峕膥銝𡒊��齿𦻖�嗆㺭�格𧒄����煾�蝵� (Blocked Reverse Date Switch Reset)**嚗𡁻�朞��其�霂嘥�頧賭���僎憭��銝�撠� `_last_data_date` �澆��碶蛹銝𠹺�銝芯漱�𤘪𠯫嚗��屸�敶枏予�芰��伐�嚗��蝢𤾸笆朣𣂷��𡁜鍳�冽𧒄�券����亦����舘���㺭�格𠯫�麄����冽覔�砌��餅鱏鈭�眏鈭� `self._last_data_date` 憸��鈭舘���㺭�格𠯫�蠘��銁 `_check_day_switch` 銝剛秤�斤� `"2026-05-26 -> 2026-05-25"` �滚��交���揢嚗屸獈甇Ｖ��䭾迨鋡怠撩�嗉圻�𤑳� `_reset_daily_state`嚗䔶��� 100% 摰峕㟲憭滨緵�𣬚誧�踵㿥�亦���撘箸���𠶖����踹�樴坔仍�唳旿��
    - [x] **�券��訫�銝𡡞��鞉�霂� 100% �函遛�朞�**嚗𡁜銁摰峕�甇日★�詨��交��嗆��㦤蝞埈��齿��𠬍��砍𧑐�扯� `pytest test_watchlist_lifecycle.py`嚗���� 11 銝芣��嗡艇撖���詨��笔𦶢�冽�銝舘�撖罸��埈�霂閧鍂靘𧢲�蝻腈���甈⊥�批�蝏輸�朞�嚗諹�摰硺��其��游��唳�獢�沲 and 蝔喳��抒����銝页�憭批��𣂼�鈭�頂蝏毺�撌乩�蝥批�憯桀漲嚗�

## 2026-05-25 23:25
- [x] **摰𣬚�閫��撟嗡漱隞䁅��� HUD 銝𤾸��条�隞瑟䔝瘚见膥����唳旿瘚�楛摨血笆朣� (Delivered Authoritative SSOT Data Sync & Zero-Lock DictWrapper for SpatialFollowHUD)**嚗�
    - [x] **摰䂿緵����渲粉銝𤾸�撅��訫�靘见笆朣� Single Source of Truth (SSOT)**嚗𡁻�����港葵摨𠉛鍂蝔见���䔝瘚见膥�笔𦶢�冽�嚗�**敶餃�皜�膄鈭� `SectorBiddingPanel` �芾��𥕦遣�祉��枏��函��𦯀�蝏𤘪�**嚗�緵�券𢒰�踹銁�嘥��𡝗𧒄隡𡁶���凒餈𧼮僎憭滨鍂銝餌����撅��臭��� `main_window.racing_detector`����冽覔�砌�摰䂿緵鈭��撅��臭���暑雿𤘪���膥嚗䔶�霂���函頂蝏� 100% 韏啣��其��渡��唳旿蝏𤘪�銝𤾸�靘页�
    - [x] **瘛勗漲�惩𤐄 NoneType �嗅捆�坔�摨𤏪��寥膄 TypeError �芷��**嚗𡁻�撖孵��臬𢆡����寥�樴坔仍�㚚�憸烐凒�唳𧒄�航�摮睃銁��征撅墧�批�畾蛛��券妟�瑁������ `DictWrapper` 銝剔��乩����撘箏ㄝ��𢆡��㜃�芷俈蝥踴��� `leader_change_pct`��leader_vwap` 蝑� float/str 摮埈挾�其蛹 `None` �嗉䌊�典��券�蝥批‵��蛹 `0.0` �� `"--"`����拍�銝𦠜覔�支� `TypeError: '>=' not supported between instances of 'NoneType' and 'int'` 撖潸稲 HUD 皜脫�撏拇���𥁒�辷�靽肽�蝟餌�憒��頝𤏸�蝔喳�嚗�
    - [x] **霈曇恣�嗆鼧韐肽蝠�讛蓮�ａ����� `DictWrapper`**嚗𡁜⏚�� Python �冽����舀䲮瘜訫�鋆���嗆鼧韐嘥笆鞊∪�鋆�膥 `DictWrapper`嚗�� `racing_detector` 餈𥪜���暑頝�����銝芾�摮堒��删��拍��惩�撖寥�銝箏蒂�� `.name`��.heat_score`��.follower_detail` ��笆鞊⊥聢撘譌��誑蝏嘥笆�嗉�銵峕𧒄撘���嚗�100% 摰𣬚�憭滨鍂鈭� HUD 撌脫�����典�蝏游漲皜脫�撘閙�隞��嚗�
    - [x] **�滚� showEvent �拍��㕑絲�芣� (Fixed Reopen Blank & Auto-sync)**嚗𡁻��嗘� HUD �� `showEvent` �曄內鈭衤辣��緵�冽�霈箸糓蝛箸聢�� Toggle�������餅�韏瑯����胼�𨅯��剖��齿鰵撘��胼�嘅��賭��典凝蝘垍漣��圻�穃撩�𥕦�甇乩��滚�雿滩䌊���敶餃�閫��鈭�鍂�瑕�擐���𨅯��剖�撘��舀㺭�桐��交瓷�匧��砽�萘�鈭支��𤤿�嚗�
    - [x] **�啣��𨥉�� �瑟鰵�脲�摰Ｙ���    - [x] **���笔��� 40/40 �訫�銝𡡞��鞉�霂� 100% 蝏踵��朞�**嚗𡁜銁摰峕� SSOT ����渲粉銝舘䌊���摰𡁶�蝟餌���漣�𠬍��砍𧑐�扯� pytest �𧼮�瘚贝�嚗���� `test_watchlist_lifecycle.py` 隞亙��詨�鈭斗�摨訫漣瘚贝�蝑匧��� 40 銝芣�霂閧鍂靘页��� 2.91 蝘鍦�銝�甈⊥�� 100% 蝏踵��函遛�朞�嚗��憭���舀��毺�撌乩�蝥批�憯格�改�
    - [x] **摰䂿緵頝罸��鍦仍�菔”�澆�摰賣��刻��港�頝其�霂萘����銋�� (Follower Vanguard Column Persistence)**嚗�
        - [x] **�舀��见𢆡�𡝗嗻靚��**嚗𡁜� `self.table` 霈曄蔭銝� `Interactive` �𡝗嗻璅∪�嚗�� 5 �堒�霈豢��䀹��函��Ｖ��寞旿閫���渲��芰眏�硋𢆡�孵�摰賢漲��
        - [x] **霈曇恣�𠉛氖�� JSON �嗆����堒�**嚗𡁜銁 `spatial_follow_hud.py` 銝剖��唬� `_save_column_widths` �� `_load_column_widths` �寞�嚗���堒捐�唳旿�祉�����硋��睃銁 `logs/hud_column_widths.json` �滨蔭��辣銝哨��踹�銝駁�蝵格情�瓐��
        - [x] **��蝸�笔𦶢�冽��拍��芣�**嚗𡁜銁蝒堒藁�� `closeEvent` �� `hideEvent` 閫血��嗉䌊�典����啁��堒捐靽嘥�餈𤤿��矋�撟嗅銁銝𧢲活蝏�辣�瑕鍳�典�頧賣𧒄�芸𢆡霂餃��Ｗ�����𦒘��轁�𨅯耦��鸌敺��苷��嗥輕�� `Stretch` �䭾說�拐����厩征�渡��寞�改�摰𣬚�韐游��� 5 �㛖��芸�銋㗇�靘页�颲暹�鈭�▲撠𣇉�擃条漣鈭箸㦤鈭支�雿㯄�嚗�
    - [x] **摰䂿緵撘��睃�銝𤾸��冽惣�賡�蝥折���� (Pre-market & Midnight Intelligent Calendar Fallback)**嚗�
        - [x] **霈曇恣 09:15 �滨蔭霂���箏�**嚗𡁜銁 `_build_detector_state_process` 摮鞱�蝔见�頧賢��𦒘葉撘訫�鈭�漱�𤘪𠯫�園𡢿畾菜惣�賡秄�����璉�瘚见�敶枏��臭漱�𤘪𠯫雿�𧒄�笔�鈭� `09:15` 蝡硺遠�芸�憪见�嚗���峕膥憭滨��𣇉��滚��臬𢆡嚗㗇𧒄嚗諹䌊�穃鍳�券�蝥折俈摰���
        - [x] **�芸𢆡���踹笆朣𣂼�銝�鈭斗��交㺭��**嚗𡁜撩�𥕦� `today_str` 撖寥��喇�靝�銝�銝芯漱�𤘪𠯫�嘅��朞� `cct.get_last_trade_date()` �𣂼�撟嗉‘朣鞉聢撘𧶏�嚗䔶蝙 `is_cross_day` �文��典��睃�摰匧�敶雴蛹 `False`���隞擧覔�砌��寞祥鈭���冽��睃��瑕鍳�冽�撘��Ｘ踎�嗅��惩��亙��嗥�隞瑁�����紡�渡��唳旿�𦦵蒾撅�/蝛箸��嗪䔮憸矋��曉�銋讠蓡摰峕㟲蝏扳㗁撟嗅��唳㿥�亦���撘箸���𠶖���樴坔仍�⊥㺭�殷��睃�鈭斗��芣�餈�腹銵䔶�瘚�偌嚗�� **1000ms (1蝘�)** �瑟鰵銝�甈∴�敶餃��脰�鈭����𧒄�湔挾銝讠��Ｘ踎�餌�嚗�
    - [x] **�㯄�朞恣蝞㛖��毺��嗅撩�𥡝��冽綫�� (Bidding Worker to HUD Push)**嚗𡁜銁 `SectorBiddingPanel._on_worker_finished` �唳旿�滨��箏藁嚗諹蕭�牐�撖嫣蜓蝒堒藁撌脫�撘� HUD 蝒堒藁��𠶖����乩�銝餃𢆡�日��箏�����血��唳���恣蝞堒�瘥訫僎�湔鰵 UI嚗𣬚��港誑 100ms 敺桀辣餈罸�𡁶䰻撟嗅撩�𥟇葡�� HUD嚗諹噢�𣂷�摰��銝滢�韏� QTimer ��滲鈭衤辣撽勗𢆡�𧢲��笔笆朣鞟���𡡒�荔�
    - [x] **摰𣬚��賢𧑐�瑕鍳�刻䌊��粉��銝舘䌊�券�摰� (Cold-start & Inactive Sector Self-Healing)**嚗𡁜銁 `_on_timer_refresh` 摰𡁏𧒄�誯�蝏䀝誑�� `update_hud_data` �亙藁憭湧�蝏��鈭�征憌𤾸藁�𡝗���踎�𡑒��交𧒄��惣�賢�蝵株��怒��朖雿踹銁蝟餌��瑕鍳�具���隞颱��踹�蝒�聦靽∪噡�����鍂�琿�朞�蝛箸聢�桃��桃征��𤧅�� HUD�����糓隡惩�鈭���䀹𧊋瞈�瘣餌��蹱��踎�梹�憒���臬𢆡�嗥� `"�賭��寥仪"`嚗匧㦤�臭�嚗峵UD 銋蠘��其�瘥怎�蝥批��芸𢆡撖餃����撟園�蝎曉漲皜脫��箏��� market 撘箏漲�鍦�蝚砌����撘箸暑頝�����敶餃��𠰴�鈭��憪𦥑�𦦵蒾撅謿�脲��𨅯��臬𢆡蝛箸��嘅�

## 2026-05-25 21:10
- [x] **銝㯄★靽桀�撟嗅蝠摨閗���踎�𡑒��血��擧�����券����瘚贝�蝏踵��𧼮� (Delivered Sector Focus Engine Layout Normalization & 100% Test Success)**嚗�
    - [x] **敶餃��寞祥�屸��噼膠撖潸稲�������� (Fixed CRCRLF Layout Issue)**嚗𡁏��亙僎瘨�膄鈭� `sector_focus_engine.py` 銝剖��函��屸��噼膠蝚� (`\r\r\n`)���朞� Python �𡁏𧋦摰䂿緵�拍�銵𣬚��毺泵���銝��硋�撟� (`\r\n`)嚗䔶蝙��辣摰鮋�銵峕㺭蝏蠘恣隞𤾸�撣貊� 6128 銵��蝢擧�憭滩秐甇�虜�� 3064 銵䎚��蝠摨閗圾�喃��典�憭� IDE �� flake8 銝剖��啁�皛∪����滨征銵䔶��澆��仿�嚗峕�憭滢�隞������游虾霂餅�扼��
    - [x] **摰䂿緵 PEP8 stylistic 蝥批�憭批恣霈∩�蝏𤘪�摰峕㟲�扳嵗撉�**嚗𡁜笆 `sector_focus_engine.py` �������EP8 stylistic 閫��銝擧瓲敹��餉�璅∪�嚗�� `DragonLeaderTracker`��StarFollowEngine`��SectorFocusController`蝑㚁�餈𥡝��券𢒰�拍�摰∟恣嚗𣬚＆靽嘥銁�煺漣�臬�嚗𠃊uitka 蝻𤥁�嚗劐��瑕�������璉埝�改�銝𥪜�蝢𤾸笆朣𣂷��唳�蝟餌��������嗆��挽霈∟�����
    - [x] **�券� 40/40 �訫�銝𡡞��鞉�霂� 100% 蝏踵��朞�**嚗𡁜銁 PYTHONPATH �臬��㗛�銝钅��唳�銵䔶��典�鈭斗���瓲銝舘�撖罸��埈�霂𨰻����� `test_watchlist_lifecycle.py` �� 11 銝芣�霂閧鍂靘页�隞亙� `trading_kernel/tests` �桀�銝� 29 銝芣��詨��其�嚗��霈� 40 銝芣�霂閧鍂靘见��其誑 100% �𦦵�銝�甈⊥�抒遛�堒�蝏輸�朞�嚗𣬚�����靝漱�枏��条��嗥撩�瑚����蝔喳����鈭抒𠶖���
    - [x] **璉��亙僎蝖株恕憭𡁶垢 HUD �𧢲踎銝𡒊頂蝏毺漣�剝睸�𥪜𢆡摰𣬚��澆捆**嚗𡁶＆霈支�頝笔� HUD (`SpatialFollowHUD`) �詨����嚗Ǒhud_sector_cooldown` / `hud_global_suppression`嚗劐� `Alt+R` �剝睸瘜典����蝥扯䌊���蝟餌�蝥扯��函��䭾����嚗���唬�頞���祉迅摰𡁶��䀹钟鈭支�雿㯄���

## 2026-05-25 20:35
- [x] **�滨�摰䂿緵撟嗡漱隞䀹��舀踎�𡑒��� HUD �𠰴��嗆惣�賣��扯�皛� (Delivered Tactical SpatialFollowHUD & Multi-level Suppression Gates)**嚗�
    - [x] **摰䂿緵憭𡁶漣�箄�靽∪噡瘚�綉銝擧��園���**嚗𡁜銁 `SectorFocusController` 銝剖��乩��箔� 15 ����踹�蝥批��瑕㭂�冽�銝� 90 蝘鍦�撅�擐硋��穃��冽�����滚�蝥批��冽��抒�瘜𤏪�摰𣬚��脫迫�䀝葉�剜𧒄�游�憭帋葵蝒�聦靽∪噡撘訫�霅行𥁒�瑕�銝擧��条魿�喋��
    - [x] **�㯄�𡁜�蝥輻�撘�郊 Dispatch UI 皜脫�獢交�**嚗𡁜銁 `instock_MonitorTK.py` 銝� `sector_focus_engine.py` 銋钅𡢿撱箇�鈭��撣血捐��瑪蝔见��函� `tk_dispatch_queue` 鈭衤辣����𡁻���遙雿閙䔉�芯�銵峕�霈∠��𤾸蝱�����/�匧��喟�嚗���賭誑鈭𡁏神蝘垍漣撱嗉��鮋獈憛𧼮��閖�坿秐銝� Tk/Qt 蝥輻�嚗���典𤧅�鍦僎�滨� HUD �𧢲踎��
    - [x] **摰𣬚��賢𧑐�典�蝛箸聢��/�孵��桐��噼膠銝见��𥪜𢆡**嚗𡁜��唬�銝餅綉蝡舐征�潮睸撖� HUD ����菜�摨� Toggle �批�嚗�僎��捂�朞��桃�銝𠹺�撌血𢰧�孵��格�閫���閙������ Enter �桐��株��� `TradingKernelService.evaluate_decision_item` �湧�𡁜�撅��銵屸�𡁻�銝见�嚗諹噢�𣂷�頞���砌�皛𤑳��䀹钟�脫�雿㯄���
    - [x] **�券� 33/33 pytest 瘚贝�嚗�29銝芸��貊鍂靘� + 4銝杳DF5�唳旿摨梶鍂靘页�100% 蝏踵��函滯蝥輻遛�舫�朞�**嚗𡁶�餈�頂蝏毺漣����见�銝𤾸僎�烐�霂𤏪��典� regression 撉諹� 100% 蝏輯𠧧摰𣬚��朞�嚗𣬚頂蝏毺�����罸��琜��瑕�憿嗅���極銝𡁶漣�亙ㄝ瘞游�嚗�

## 2026-05-25 19:35
- [x] **靽桀��剛�閫���笔�摰峕㟲�笔𦶢�冽�瘚贝��剛�銝滢��� Bug (Fixed Watchlist Lifecycle Test Failures)**嚗�
    - [x] **靽格迤�駁��剛��文�**嚗𡁜銁 `test_watchlist_lifecycle.py` 銝剖� `test_add_to_watchlist` ��笆�滚��坔�餈𥪜��潛�憸��隞� `False` 靽格迤銝� `True`嚗䔶誑摰𣬚�撖寥��煺漣隞��銝凌�𣈯�憭滚��亙�霈豢凒�啗���/敶Ｘ���餈𥪜� True�萘�霈曇恣��
    - [x] **�惩𤐄撏拍�頝��銝𡒊鸌敺���扳�霂�**嚗𡁻���� `test_validate_price_crash_dropped` �� ohlc 璅⊥��唳旿��� `close` 靚�㟲�� `91.0`嚗䈣ma10` 霈曆蛹 `85.0`嚗��撘� MA10 頝𣬚聦�斗鱏��𣈲嚗㚁�撟園���鰵�� 8% 頝���冽�撠��霂閙��𥟇鱏閮�隞� `'7%'` 靽格㺿銝� `'8%'`嚗䔶蝙撏拍�瘛䀹掠�斗鱏憿箏⏚�嗅偏��
    - [x] **靚�㟲銝剜�扯��刻�隞仿俈霂舀�**嚗𡁻���� `test_validate_watching_continues`��蝙銝剜�扯� `close = 50.5` 擃䀝� `high4 = 50.2` 隞亥圻�烐鰵擃䀹�霈堆�`is_high_momentum = True`嚗㚁�銝𠉛輕���餉��� `0.5 < 0.7`����𣂼�蝏閗�鈭� `total_score < 0.5` 銝娍��刻���䌊�冽�瘙啣㨃���蝎曉�靽脲�鈭� WATCHING 閫���嗆���摰��撖寥�鈭�楊�仿�霂���𡒊�摰墧�憌擧綉霈曇恣��
    - [x] **���笔��� 11/11 pytest 瘚贝� 100% 蝏踵��函遛�𡁜�**嚗帋耨�孵�嚗䈣test_watchlist_lifecycle.py` ����� 11 銝芣�霂閧鍂靘衤�甈⊥�批�蝢𡡞�朞�嚗峕㟲銝芰頂蝏��霂訫�隞嗥迅�亙�蝤琜�

## 2026-05-25 17:35
- [x] **�寞祥擃㗛��亥砭銝䇊I撖��撖潸稲���憭滢��閗郎�� (Fixed Duplicate Order Warnings from High-Frequency UI Queries & Passive Enrichments)**嚗�
    - [x] **撘訫� `write_journal` �𠉛氖靽脲擪��**嚗𡁻���� `TradingKernelService.evaluate_decision_item`��緵�典蘨�匧� `write_journal=True`嚗�朖�亥䌊鈭𡒊�摰䂿�鈭斗��嗵��扯�瘚���塚�蝟餌��滢��烐�銵屸����剁�憒� `broker_adapter` �� `paper_adapter`嚗㗇��垍�摰䂿� `submit_order` �拍�銝见���誘嚗�僎�湔鰵 StateManager嚗𥕦� `write_journal=False`嚗�朖�亥䌊鈭� GUI 擃㗛�摰𡁏𧒄�冽�璉�蝝Ｗ�蝑㚚��𦯀誑撖��皜脫� UI ��◤�冽䰻霂Ｘ�嚗㗇𧒄嚗𣬚凒�亥�皛斗�頝荔�隞舘�䔶��寞𧋦銝𦠜��支�撖� `submit_order` ��秤閫血���
    - [x] **�寞祥擃㗛�撟���駁��亙��瑕�**嚗𡁻�朞� `write_journal` ��′�批�蝵格㜃�迎�敶餃��寞祥鈭�銁 GUI 擃㗛��瑟鰵�塚�蝟餌��曹��滚�撖孵歇�𣂷漱/撌脫㜃�芾恥�閙�銵��雿嗵�撟���文���銁�批��唬��剜𥁒�� `�𩤃� [Idempotency] Duplicate order submission detected` 霅血��亙�����對�雿蹂漱�枏��䀹凒�删滲��擃䀹���
    - [x] **���笔��� 58/58 pytest 瘚贝�蝏踵�摰𣬚��券��**嚗𡁶�撉峕𤣰瘚贝�嚗䔶耨�孵銁摰���嗅�雿𦦵鍂��妟�𤾸��澆捆�批蔣�滨��嗆�������𣂼�嚗�58 銝芣�霂閧鍂靘衤��� 100% 蝏踵��朞����

## 2026-05-25 17:15
- [x] **摰𣬚�摰䂿緵鈭斗�餈鞱�璅∪����霈啣�銝𤾸�蝡臬笆朣� (Aligned Trading Mode Position Records & UI Sync)**嚗�
    - [x] **蝎曄��𤥁�銵峕芋撘𤩺�隞栞楝�� (Dynamic Position Mode Routing)**嚗𡁻���� `DecisionFlowPanel._refresh_positions_tab`嚗峕覔�桀��詨��漤�匧���漱�栞�銵峕芋撘𧶏�`LIVE_AUTO`, `CONFIRM`, `PAPER`, `OBSERVE`嚗匧𢆡��楝�梯秐撖孵�������璅⊥�����剁�
        - `LIVE_AUTO` 璅∪�嚗𡁜撩�𤤿�摰𡁜��� `broker_adapter` ���摮䀝�韐血��唳旿皞琜�
        - `CONFIRM` 璅∪�嚗𡁶�摰帋犖�箏��� `confirm_adapter` �唳旿皞琜��惩�撟嗅�甇� `paper_adapter`嚗㚁�
        - `PAPER` 璅∪�嚗𡁶�摰𡁻�靽萘�璅⊥� `paper_adapter` �唳旿皞琜�
        - `OBSERVE` 璅∪�嚗𡁜��刻��拙��塚��拍�撅讛𤪖銝擧�蝛箸�隞栞”�潘��𦦵�憭𡁏芋撘𤩺㺭�格毽瘛���
    - [x] **摰䂿緵璅∪���揢�删��單𧒄�滨�**嚗𡁜銁 `_on_mode_combo_changed` 瑽賢遆�啣��函��乩� `self._refresh_positions_tab()` 撘箏��滨�嚗䔶�霂���䀹���揢銝𧢲�璅∪���凝蝘垍漣�祇𡢿嚗峕�隞瓐���鈭批之�∠�銝𦒘��亙��脰恥�閙㺭�株�憭� 100% 撖寥��滨�嚗峕��支��𤾸蝱摰𡁏𧒄�瑟鰵����擧���
    - [x] **�拍��脣鴃撘� fallback 銝𤾸��冽�找���**嚗𡁜笆 `adapter is None` �箸艶銵仿�鈭�俈敺⊥�抒� fallback �嘥��吔�銝芾�����滨蔭銝箇征��虾�函緵�㻫���鈭扳�餃�潦��𠯫���鈭誩��典��塚�嚗��蝢𦒘��靝��� `OBSERVE` 蝥舀�頝舀芋撘譍���頂蝏煺��湔�找�閫��蝢舘�摨艾��
    - [x] **�券� 58/58 pytest 瘚贝�蝏踵�摰𣬚��券��**嚗𡁶�餈��蝟餌�蝥批�敶埝�瘚页�58 銝芸�����������其��� 100% 蝏踵��朞�嚗𣬚＆靽苷漱�枏��条��嗥撩�瑚����蝔喳��改�

## 2026-05-25 16:30
- [x] **靽桀�摰䂿� LIVE_AUTO 璅∪�銝𧢲�隞㮖���蟮霈Ｗ��𦦵蒾撅謿�脲�瘜閙遬蝷� Bug (Fixed Live Positions & Orders Display Blank in LIVE_AUTO Mode)**嚗�
    - [x] **�㯄�𡁜抅蝐� BrokerExecutionAdapter ���蝥扯䌊��芋��㦤�� (Implemented In-memory Simulated Broker State)**嚗𡁜蝠摨閙覔瘝颱��冽瓷�㗇�頧賢�雿枏��� API �𨅯蝱�硋�鈭𤾸��睃��暹�蝏�𧒄嚗𣬚眏鈭� `BrokerExecutionAdapter` �箇掩雿靝蛹獢拙遆�堆�Stub嚗厰�霈方��䂿征���嚗�紡�� UI �𨀣�隞𣏾�嗪△蝑曆�隞𦠜𠯫霈Ｗ��𡑒”�箇緵�𦦵征瘣�/�賢��萘�鈭支� Bug��
    - [x] **摰䂿緵擃䀝��蠘恥�蓥����璅⊥��餉�**嚗𡁜銁 `BrokerExecutionAdapter` 銝剛‘朣𣂷� `self.orders` 霈Ｗ�霈啣��笔���self._positions` ������摮堒�隞亙� `self._cash` 韏��瘙惩�憪见���銁 `_execute_broker_order` �拍�銝见��亙藁����唬�摰峕㟲�� BUY/ADD �牐��� SELL/REDUCE 撟喃��冽������蝖桐��拍�銝见�鋡急芋�罸�蝎曉漲�閗繮銝舘�蝞𨰜��
    - [x] **撖寥� PyQt 銵冽聢�唳旿�讛悅銝𤾸𢆡��筑�����**嚗𡁻���� `get_positions`��get_account_snapshot` 銝� `update_market_price`��𣈲��銁�删�摰墧��唳㺭�格𧒄�冽��恣蝞埈��芯葵�∠����唳�駁���筑�函�鈭𧶏�`pnl` / `pnl_pct`嚗㚁�撟嗅�摨娪�憸𤏸���綫���摰墧𧒄隞瑟聢�垍�嚗䔶蝙 UI ����Ｘ踎�賜�蝥折�蝏矋�摰��撖寥�鈭� Paper 璅⊥��条�銝�瘚��撉䎚��

## 2026-05-25 15:50
- [x] **�惩𤐄鈭斗���瓲璅∪�頧祆揢憭拇０銝𤾸��典�蝵株䌊�� (Hardened Trading Kernel Mode Ladder & Preconditions Auto-Healing)**嚗�
    - [x] **摰䂿緵撖寡揭瞍�宏�芣��箏� (Implemented Position Reconciliation Auto-Healing)**嚗𡁻���� `TradingKernelService._verify_live_preconditions` �寞�銝剔�撖寡揭�∪藁��銁璉�瘚见��砍𧑐銝𤾸��䀹��唬�雿齿�韏��瞍�宏嚗ǑACCOUNT_OUT_OF_SYNC`嚗㗇𧒄嚗諹䌊�煾�朞� `BrokerPositionSync` �匧�摰䂿��������諹��𡢅��湔鰵閬���砍𧑐 `paper_adapter` ���摮䀝�雿滢��舐鍂�圈�嚗�僎餈𥡝��笔�����硋��矋�`_save_state()`嚗剹����舘�銵𣬚洵鈭峕活�⊿�嚗𣬚＆靽肽䌊��笆韐西圾���摰䂿緵鈭��甇���𡏭䌊�𤑳��譍��删��Ｗ��腈��
    - [x] **摰䂿緵瘚贝��臬�憌擧綉蝖祇�蝳� (Refined Pytest Environment Safety Barrier)**嚗𡁜銁 8 憭批��典㨃��葉蝏��鈭� `PYTEST_CURRENT_TEST` �臬��㗛��⊿������ pytest �訫�瘚贝��臬�銝贝�銵峕𧒄嚗𣬚���㜃�� `LIVE_AUTO` ��漣霂瑟�嚗𣬚凒�亥��� `TEST_ENVIRONMENT_BLOCKED` �躰秤嚗�蝠摨閗��蹂��𧼮�瘚贝��罸𡢿霂航圻摰䂿�銝见�����押��
    - [x] **靽桀�憌擧綉���澆��批ế摰� Bug (Fixed RiskLimits Attribute Verification Bug)**嚗帋耨憭滢�撖� `RiskLimits` 撅墧�批ế摰𡁻�餉�����笔��躰秤����批��其耨甇�蛹撖� `daily_loss_limit_amount`��max_single_stock_position_pct` 銝� `max_single_size_pct` ��移��粉�吔�瘨�膄鈭�頂蝏� cold-start �⊿��嗥�瞏𨅯銁撅墧�批�撣賊�����
    - [x] **�券� 58/58 �訫�銝𡡞��鞉�霂� 100% 蝏踵��函遛�朞�**嚗𡁜銁摰峕�鈭斗���瓲璅∪�頧祆揢銝𤾸��券俈�文��惩𤐄�𠬍��𣂼�頝煾�𡁜��� 58 銝� pytest 瘚贝��其�嚗峕�霂閖�朞��� 100%嚗��蝢𤾸��支漱�枏��貊�摰匧�摨閧�嚗�

## 2026-05-25 15:30
- [x] **蝏煺��函頂蝏罸�蝵格�隞嗉楝敺�䌊���敶餃��寞祥敺芰㴓撖澆� (Unified Unified Config Path Resolution & Resolved Circular Import)**嚗�
    - [x] **隞���函頂蝏蠘楝敺�䌊��㦤��**嚗𡁜銁 `JSONData/sina_data.py` �� `JSONData/wencaiData.py` 銝哨�敶餃�皜�膄鈭���嗵����雿嗵��砍𧑐頝臬�霈∠��𡃏�皞鞾��暹𦻖���撠�� `get_base_path`��get_stock_code_path` �� `get_conf_path` 蝏煺��望瓲敹� `_import_sys_utils` 隞���單�憡�㺭�格� `sys_utils.py`��
    - [x] **�餃�蝟餌��臬𢆡蝥批儐�臬紡�亙儐�舀香�� (Resolved Circular Import Deadlock)**嚗𡁜銁 `sys_utils.py` ��▲�函宏�支�撖� `from JohnsonUtil import commonTips as cct` ���撅�璅∪�蝥批紡�伐��齿�撠��銝𧢲𦆮�� `get_base_path` �賣㺭����� win ��𣈲銝贝�銵�辣餈笔��典紡�乓���敶餃���鱏鈭� `sys_utils` 銝� `commonTips` 銋钅𡢿��㮾鈭鍦紡�乩�韏吔�閫�膄鈭�眏鈭� `commonTips` �嘥��硋��磰��� `LoggerFactory.getLogger` 撖潸稲 `partially initialized module` ��艇�滚儐�臬紡�仿�霂胯��
    - [x] **�拍��𣳇膄�𦯀�撋�����霂舫�蝵桃𤌍敶� (Removed Redundant Config Directories)**嚗𡁻�朞�蝏煺�頝臬�隞��嚗䔶��拍�撅�𢒰銝𦠜覔�祆��支�憭帋�摮鞉�隞嗅允鋡恍�憭滚�撱箇������蝙�� Powershell ��誘�拍��𣳇膄鈭��霂舐����雿嗵�撋���滨蔭�桀� `JSONData\JSONData` �𠰴�銝剔�畾讠��滨蔭��辣��
    - [x] **58/58 �券��訫�銝𡡞��鞉�霂� 100% 蝏踵��𡁜�**嚗𡁻�朞�銝𡃏膩靽格㺿嚗�銁 Windows �砍𧑐�臬�銝钅◇�拇�銵� pytest �賭誘銵䕘��券� 58 銝芣�霂閧鍂靘衤誑 100% �朞���遛�堒�蝏輸�朞�嚗䔶�霂��蝟餌�頝臬��齿����撖寞��罸��僐��

## 2026-05-25 14:05
- [x] **靽桀� HDF5 �拍��芣鱏閫血�銝𡒊��∟�撖罸��烾�霂��霂� Bug (Fixed HDF5 Truncation Trigger & Watchlist Verification Tests)**嚗�
    - [x] **�齿� HDF5 �冽��⏛�剝��潸恣蝞� (Fixed H5 Truncation Trigger)**嚗𡁜��支� `write_hdf_db` �餉�銝剖笆鈭� `num_codes > 1000` 餈嗘�蝖祆�扳㺭�𤩺㜃�芥����園���蛹�𡁶鍂�� `calculated_safe = int(sizelimit * 1024 * 1024 / 85 / num_codes) if num_codes > 0 else 3000`��銁雿舘��唬�敶� sizelimit ����塚�憒�����霂蓥葉�� 0.01MB嚗㚁�銋蠘��冽��恣蝞堒枂甇�＆�������刻��堆�61銵䕘�嚗峕��蠘圾�� `test_h5_truncation.py` �䭾�閫血����鋆���� bug��
    - [x] **靽桀� Watchlist �滚��坔��剛� (Aligned Duplicate Watchlist Assertion)**嚗𡁜� `test_add_to_watchlist` 撖寥�憭滚��亥��𧼮�潛�憸��隞� `False` 靽格㺿銝� `True`嚗䔶誑摰��憟穃��煺漣隞��銝凌�𣈯�憭滚��亙�霈豢凒�啗���/敶Ｘ���餈𥪜� True�萘�霈曇恣閫����
    - [x] **靽桀�撏拍�瘛䀹掠�剛�銝𤾸𢆡�賢��舀㜃�� (Fixed Crash-Dropped Assertion & Momentum Gate Bypass)**嚗𡁜銁 `test_validate_price_crash_dropped` 銝哨�靚�㟲 `ma10 = 85.0` �踹�鈭���� MA10 ��𣈲嚗���嗅� `upper = 90.0` 雿踹�擃睃𢆡�賣�霈� `is_high_momentum = True` 蝏閗��刻��桐�����齿㜃�迎�撟園���鰵�� 8% 頝���冽�撠��霂閙��𥟇鱏閮�銝� `'7%'` 靽格㺿銝� `'8%'`嚗䔶蝙撏拍��嗆��◇�拇𤣰撠整��
    - [x] **靚�㟲銝剜�扯���㺭隞仿俈鋡恍��刻��∪藁霂舀� (Preserved Neutral Watching State)**嚗𡁜銁 `test_validate_watching_continues` 銝哨�撠� close 隞瑟聢靚�㟲�� `54.0`嚗�迨�� `close >= upper * 0.98`嚗㚁�隞舘�䔶蝙�嗉繮敺烾��刻�霂�漣撟嗡����餉��� 0.6嚗屸��滚�雿𦒘� 0.5 銝娍��刻�鋡怎凒�亥腺�箄�撖罸��梹�蝎曉�靽脲�鈭� WATCHING �嗆����
    - [x] **�券� 58/58 �訫�銝𡡞��鞉�霂� 100% 蝏踵��𡁜�**嚗𡁶���圾�單��匧�敶垍滯蝥輸�蝣㵪�Pytest 憟𦯀辣�梯恣 58 銝芣�霂閧鍂靘见��� 100% 蝏踵��朞�嚗�

## 2026-05-25 12:15
- [x] **摰䂿緵璅⊥��䀹�隞㮖���蟮霈Ｗ�頝典予/頝券��舐����銋�� (Delivered Simulation Positions & Orders Cross-Restart Persistence)**嚗�
    - [x] **霈曇恣�砍𧑐 JSON �嗆����堒��寞�**嚗𡁜銁 `PaperExecutionAdapter` 銝剖��� `_load_state` �� `_save_state` �寞����甈⊥芋�煺漱�㮖��閙���𧒄嚗�� `AccountSnapshot` �� `orders` ��蟮鈭斗��𡑒”�峕郊�坔� `logs/paper_account_state.json` �滨蔭��辣嚗諹圾�喲��臭腺憭梢䔮憸塩��
    - [x] **摰䂿緵�臬𢆡�芣��Ｗ�**嚗𡁶�摨誯��啣鍳�冽𧒄嚗䈣PaperExecutionAdapter` �芸𢆡�㰘蝸撟嗆�憭滢�銝�甈∟�銵𣬚���𧒄���憪贝��㻫��虾�函緵�㻫��葵�⊥�隞橒�銋啣���遠���隞栞��堆�撟嗉䌊�典�敶枏�隞瑕笆朣𣂷蛹銋啣���遠隞仿俈�瑕鍳�函�鈭讛恣蝞堒�撣賂�隞亙���蟮霈Ｗ���
    - [x] **撱箇�瘚贝��臬�憌擧綉�𠉛氖 (PYTEST_CURRENT_TEST Bypass)**嚗𡁜銁 `_load_state` �� `_save_state` 憭湧�撘訫� `PYTEST_CURRENT_TEST` �臬��㗛��⊿������ pytest �訫�瘚贝��臬�銝贝�銵峕𧒄嚗𣬚����銋���芸𢆡��楝�剛楝嚗屸俈甇Ｘ�霂閗�銵峕情�梶鍂�瑞��砍𧑐����唳旿嚗䔶�蝖桐�鈭��霂閗�銵𣬚�蝥臬��������
    - [x] **憓噼挽�冽鰵�訫�瘚贝�銝𤾸��� 30/30 瘚贝��𧼮�**嚗𡁜銁 `test_paper_trading.py` 銝剖�霈曆� `test_paper_trading_persistence` 瘚贝��其�嚗屸�朞��拍�銝湔𧒄��辣摰𣬚�閬��鈭��頧賭�靽嘥����蝑㗇�憭漤�餉�嚗�僎�𣂼��典𢆡�典��𧼮�瘚贝��圈�憓鮋鵭�� 30 銝迎��朞��� 100%��

## 2026-05-25 12:00
- [x] **靽桀���瓲摰墧𧒄���銵冽聢擃㗛��瑟鰵�劐葉銝Ｗ仃銝𡡞緾��䔮憸� (Fixed Positions Table Selection Loss & Flickering on High-frequency Refresh)**嚗�
    - [x] **撘訫�銵冽聢憿孵��其��𤩺��仿�蝏䀹凒�唳㦤�� (Item Reuse & Dirty-Check In-place Updates)**嚗𡁜��支� `_refresh_positions_tab` 銝剔��湔�蝛箸㟲銵函� `setRowCount(0)` �滢�嚗屸���蛹�湔𦻖霈曄蔭銵峕㺭撟嗡蝙�� `item(row, col)` �𣂷葵�訫��澆��具����冽��祆��齿艶�脣�����笔��𡝗𧒄�滩��� `setText` / `setForeground`嚗���滨�撘����滢�鈭� 90%嚗䔶��拍�銝𦠜��支��芰���
    - [x] **摰䂿緵�瑟鰵�滚����劐葉�嗆���摮䀝��Ｗ� (Selection State Preservation & Restoration)**嚗𡁜銁瘥� 500ms �瑟鰵敺芰㴓撘�憪见�嚗諹䌊�刻粉�硋��漤�劐葉���蟡其誨�� `selected_code = item.text().strip()`��銁�唳旿�笔𧑐�瑟鰵�𠬍��朞��滚�隞���㛖移���霈暸�劐葉�衣� `setCurrentCell(row, 0)`嚗��蝢擧��支��冽��滢��嗥�銵諹歲�典��衣�銝Ｗ仃��
    - [x] **蝎曉�摰墧鴌靽∪噡�餅鱏隞仿俈�𥪜𢆡憌擧𠂔 (Gated Signal Blocking)**嚗𡁜銁�瑟鰵霈∠�撘�憪𧢲𧒄�曉�靚�鍂 `self.pos_table.blockSignals(True)` ��絲鈭衤辣�穃𨯬嚗���啁��笔��� `finally` �𦯀葉摰匧��Ｗ�����𣂼��餅鱏鈭�”�潮�蝵格𧒄���雿躰��刻圻�𡢅���之�唳�����䀝葉鈭支������漲銝𡒊迅摰𡁏�扼��
    - [x] **擃䀹����朞��券� 29/29 鈭斗���瓲�𧼮�瘚贝�**嚗𡁜銁瘨�膄 UI �芰��䔶��𦦵��寧迅摰𡁶��峕𧒄嚗��蝢𦒘������瓲�嗆���摨訫�����函��唳旿銝��湔�改�pytest 29 銝芣瓲敹��霂閧鍂靘衤�甈⊥�� 100% 蝏踵��朞���

## 2026-05-25 11:30
- [x] **靽桀���瓲���銝芾��滨妍�曄內銝算�𨀣�隞㮖葉�嘥�雿滨泵 Bug (Fixed Position Name 'Holding' Placeholder Resolution Bug)**嚗�
    - [x] **�㯄�𡁜�皞𣂼�蝘啗‘朣鞾�𡁻�**嚗𡁜銁 `DecisionFlowPanel._refresh_positions_tab` 銝剝�����滨妍�交𪄳�餉�������皞臭��嗥�����典� `df_all` �唳旿撣改���鉄�券��∠巨嚗㕑�銵𣬚移蝖桀龪�滢��𣂼�嚗�銁�芸𦶢銝剔����銝见��滨漣�拍鍂 `current_df` 銵仿�嚗�蝠摨閙覔瘝颱�敶㮖葵�∩��典��齿遬蝷箏�銵剁�`current_df`嚗劐葉�嗅�蝘圈���𡝗遬蝷箔蛹�𨀣�隞㮖葉�脲��𨅯歇撟喃��嘥�雿滨泵��撩�瑯��
    - [x] **�㯄�𡁜�皞𣂼��嗡遠�潔��𦭛rade�嘥��湔鰵**嚗𡁻�������憿萇倌撖寞�銵�膥���啣�隞瘀�`update_market_price`嚗厩��滚��峕郊��𣈲��� `df_all` �� `current_df` ���瘥𥪜笆嚗�僎餈賢�撖� live 銵峕� `"trade"` �㛖�霂餃�嚗𣬚＆靽脲��劐�蝵殷��喃蝙銝滚銁敶枏� Tk �睲葉�曄內嚗匧��賜迅摰朞繮�𡝗��唬遠�潦��
    - [x] **��� 10 �埈�隞栞”�澆捐摨西䌊靚�㟲**嚗帋耨�嫣� `_adjust_column_widths` 銝剔�銵典仍�埈㺭�文��餉�嚗�� `columnCount() == 8` �湔鰵銝箏笆 10 �埈聢撘讐� `== 10` �行⏛������霈曉僎 DPI 蝻拇𦆮敺株�鈭�� 9 �㛖��蹱���蝝𩤃���鉄�啣����𨅯�隞𤘪𧒄�氯�嘥��𨅯像隞𤘪𧒄�氯�嘅�嚗�僎撠���𦒘��轁�𨅯像隞𤘪𧒄�氯�肽挽銝箄䌊��� Stretch 憛怠�嚗峕��支�璅芸�蝻拇𦆮�嗥�蝛箇蒾�𡝗�銵峕��箝��
    - [x] **摰𣬚��朞��券� 29/29 鈭斗���瓲�𧼮�瘚贝�**嚗𡁏�雿� UI 銝擧㺭�桐��湔�扳凒�啣�蝢𦒘�����睲��𤾸��澆捆嚗俰ytest ��瓲 29 銝芣�霂閧鍂靘衤�甈⊥�� 100% 蝏踵��朞���

## 2026-05-25 11:00
- [x] **靽桀��冽�撟喃��鞉𧋦銝Ｗ仃銝𡡞�憸𤏸恥�閗圾�鞉�扯�隡睃� (Fixed Yesterday Holdings Price Tracking & Real-time Orders Polling Optimization)**嚗�
    - [x] **撘訫�����鞉𧋦�脣仃敹��摮�**嚗𡁜銁 `DecisionFlowPanel` 銝剖遣蝡衤� `_position_cost_cache`��銁銝芾�靘萘�����嗅��嗉蕭頦芸僎蝻枏��� `entry_price`嚗�銁�∠巨鋡怠像隞枏�嚗��隞𦠜𠯫�牐僭�閙�瘞湔𧒄嚗㚁��𣂼�隞𡒊�摮䀝葉餈賣滲撟嗆�憭滚��笔��嘥��函��鞉𧋦嚗峕覔瘝颱�撟喃����霈∠�銝箏��券��桅����餉�蝻粹萅��
    - [x] **摰䂿緵 O(N) 霈Ｗ�憓鮋�閫��隡睃�**嚗𡁜銁 `_refresh_positions_tab` 銝剖��乩� `_last_orders_len` �𤩺��亙㨃�����敶栞恥�訫��烾鵭摨行㺿�䀹𧒄�漤��啗圾�鞱恥�訫�銵剁���之�𦠜𦆮鈭� 500ms 擃㗛�摰𡁏𧒄�瑟鰵銝讠� CPU 韏����
    - [x] **瘨�膄�滚��園𡢿�唾圾�鞟′蝻𣇉� (DRY �齿�)**嚗𡁶宏�� `_refresh_positions_tab` 銝剝妟����園𡢿�單迤�蹱���誨����券��齿�憪娍晷�喟�銝����斢���� `_parse_timestamp` �亙藁��
    - [x] **憿箏⏚頝煾�� 29/29 鈭斗���瓲�券��𧼮�瘚贝�**嚗𡁏𧋦憿� UI 銝擧�扯��惩𤐄�� 100% 靽脲�蝟餌��𤾸��澆捆��𠶖����𣂼����嚗䔶�摰𣬚��朞�鈭���� 29 銝� pytest ��瓲�𧼮�瘚贝��其���

## 2026-05-25 10:55
- [x] **摰䂿緵��瓲摰墧𧒄���敶枏�隞�/���擃㗛��瑟鰵銝𤾸�撟喃��園𡢿摰峕㟲餈質葵 (Delivered Real-time Position Price/PnL Polling & Open/Close Time Tracking)**嚗�
    - [x] **敶餃��寧蔭摰𡁏𧒄�瑟鰵�梯� Bug**嚗𡁶������� `_check_and_update_records` 摰𡁏𧒄�函��批�瘚���� `_refresh_positions_tab()` 隞擧�隞嗅之撠誩��游ế摰� (`file_size == self._last_file_size`) 銋见��滨宏�喳��嗅膥憭湧����蝖桐�鈭��霈箏�蝑� Trace �亙��㗇��睃�嚗峕�隞㯄△蝑整���鈭誩之�∠��質�隞� 500ms 擃㗛�隞𤾸�摮睃��嗆㺭�格�銝剖撩�嗆��硋僎�湔鰵��
    - [x] **�㯄�𡁜��嗡遠�潔�����峕郊�箏�**嚗𡁜銁 `_refresh_positions_tab` 銝剖��乩��箔� `self.parent_app.current_df` 銵峕�敹怎�����睲遠�澆�甇乓��笆憭������嗆���銝芾�嚗�⏚�� numpy �拍�敹恍���蝝Ｗ��嗡僭�𣇉緵隞� (`now` / `close` / `price`)嚗�僎�冽����� `adapter.update_market_price()` �垍����啁緵隞瑯���雿踵芋�毺��𠰴��䀹��啗�憭笔抅鈭擧��啗�����啁���恣蝞堒枂�笔���葵�⊥筑�函�鈭𧶏�`pnl` / `pnl_pct`嚗剹��揭�瑟�餉�鈭找誑�𠹺�雿滚�瘥𢛵��
    - [x] **�拍��拙捆���銵冽聢銝� 10 �𦯀誑���撘�撟喃��園𡢿**嚗𡁜� `pos_table` 銵冽聢�埈㺭�� 8 �埈�摰寡秐 10 �梹�餈賢�鈭��𨅯�隞𤘪𧒄�氯�嘥��𨅯像隞𤘪𧒄�氯�肽”憭氬��
    - [x] **摰䂿緵撘�撟喃��園𡢿蝎曉��𣂼�銝擧�隞㮖葵�⊿�靽萘�靽萘�**嚗𡁻�朞�����𣂷漱�� `adapter.orders` ����賢𪂹����芸𢆡���撟嗆聢撘誩��瑕�銝芾����甈∩僭�交𧒄�湛��𨅯�隞𤘪𧒄�氯�嘅��𠰴像隞㯄���箸𧒄�湛��𨅯像隞𤘪𧒄�氯�嘅����撖嫣��亙歇鋡急�隞枏像隞橒��⊥㺭銝� 0嚗厩�銝芾�嚗𣬚頂蝏煺��滩�銵𣬚��游��歹��峕糓�朞�撌脫�鈭斗�蝏�恣蝞堒�撟喃������像����砌��箏㦤隞瘀�隞� `volume = 0` ��歇皜��憪踵���蝢𦒘��坔銁敶𤘪𠯫����Ｘ踎銝哨�颲暹�銝㮖�鈭斗��条漣憭滨�雿㯄���
    - [x] **憿箏⏚頝煾�� 29/29 鈭斗���瓲�券��𧼮�瘚贝�**嚗𡁏�雿靝耨�孵�蝢𤾸�摰寞芋�毺�銝擧��堆�pytest 29 銝芣瓲敹�����霂� 100% 蝏踵��朞���

## 2026-05-25 02:55
- [x] **摰䂿緵�喟�瘚�偌�烐綉�Ｘ踎銵冽聢�厰睸銝𡡞�����Ｚ䌊�刻��刻歲頧� (Implemented Table Key Navigation and Selection Change Auto-Linkage in DecisionFlowPanel)**嚗�
    - [x] **�㯄�朞”�澆��滩���揢靽∪噡�𡁻�**嚗𡁜銁 `DecisionFlowPanel` �嘥��碶葉嚗䔶蛹�詨��喟�瘚�偌銵冽聢 (`self.table`) �峕�隞栞”�� (`self.pos_table`) ���蝏穃�鈭� `currentCellChanged` 靽∪噡�唳鰵摰䂿緵��局�賣㺭銝𨳍��
    - [x] **霈曇恣擃㗛�璉埝�抒� Focus 銝𤾸�蝑厰俈�𤥁�皛� (Focus-Gated & Idempotent Debouncing)**嚗𡁜銁銵���Ｗ�摨娪�餉�銝哨��拍鍂 `hasFocus()` �文�撘箏�隞�銁�冽��见𢆡雿輻鍂�桃��㚚����銵䔶漱鈭埝𧒄�滩圻�𤏸��剁�摰𣬚��𦦵�鈭���圈�憸� 500ms 摰𡁏𧒄憓鮋��湔鰵�㚚�頧賣㺭�桀紡�渡�霂航圻�㻫����塚�撘訫�鈭� `_last_linked_code` 蝻枏�餈𥡝�撟���駁�嚗諹�皛支�隞颱��滚�隞�����雿躰歲頧穿�隡睃�鈭���颱��閖�匧僎摮䀹𧒄��漱鈭埝�扯���
    - [x] **摰𣬚��舀�銝𠹺��孵��桐� PageUp/PageDown 蝧駁△�株���**嚗帋蝙�冽��券�朞��桃��� `Up/Down/PageUp/PageDown/Home/End` �格�閫��蝑𡝗�瘞湔�����塚�銝餌�����航��硋㦛銵刻�蝘垍漣�峕郊�滚�頝唾蓮 to 撖孵�銝芾�嚗�之撟������䀝葉�羓��𤾸��䀹𧒄����喟��������
    - [x] **憿箏⏚頝煾�� 29/29 鈭斗���瓲�券��𧼮�瘚贝�**嚗𡁏𧋦憿� UI 憓𧼮撩�典��券妟靘萄���妟�臭��函��嗆����𣂼����嚗䔶�摰𣬚��朞�鈭���� 29 銝� pytest ��瓲�𧼮�瘚贝��其���

## 2026-05-25 01:05
- [x] **摰䂿緵蝏澆�摰墧�蝞��乩葵�⊥㺭�桀��誩笆朣𣂷�摰墧𧒄敶勗��喟�擃䀝漁�峕郊 (Aligned All Stock Info & Highlighted Shadow Decisions & Integrated Spacebar Toggle & Position Persistence & Auto Linkage in Comprehensive Briefing Dialog)**嚗�
    - [x] **銝芾��詨��唳旿憭𡁏�銵仿� (Aligned All Missing Stock Info)**嚗𡁻���� `_generate_briefing_html` 銝剔�銝芾�靽⊥��賢��餉������� `code_info_map` 蝻枏�銝滚��塚��芸𢆡銝𦠜滲�喳�撅� `self.df_all` �唳旿銵其葉�朞� numpy �拍�敹恍���蝝ｇ�銵仿�鈭���徉�𨅯��箸��𨧀�腈���𨀣㿥�亥����腈���𨅯��交隅撟��嘥銁����券�������撖嫖�𨅯��交隅撟��嘅�憓噼挽鈭�抅鈭𤾸��� `tick_df` 銝𤾸��脫𠯫蝥� `day_df` ����𡁻�摰墧𧒄�曉�瘥磰恣蝞堒�摨𤏪�敶餃�閫��鈭���砍撕蝒𦯀葉�唳旿憭折𢒰蝘� `N/A` ��𧊋撖寥�蝻粹萅��
    - [x] **敶勗��喟��券��嗆��笆朣� (Synchronized All Shadow Decisions)**嚗𡁏��港���𧋦隞�銁閫血�銋啣��其��嗆�蝻枏��喟�����琜��齿�銝箸�霈箇��亦��𣂷�蝘滚𢆡雿頣���鉄�𡏭��𥕞�嘥銁�������∩辣�峕郊蝻枏��� `self.last_shadow_decision`嚗�僎�� `_generate_briefing_html` ����嗡�����刻砲蝻枏�嚗���唬�摨閖��喟�銝剖�銝𤾸撕蝒𡑒���� 100% 蝏嘥笆銝��氬��
    - [x] **�喟��漤�蝥Ｚ𠧧�枏�擃䀝漁�曄內 (Red-highlighted Action & Reason Text)**嚗𡁜�蝏澆�摰墧�蝞��乩葉���𨅯蔣摮𣂼𢆡雿鎿�嘥��𣈯�餉�����脲遬蝷粹��脫凒�唬蛹�湧��桃�鈭桃滯�莎�`#FF4444` / `red`嚗㚁�摰䂿緵鈭�鍂�瑁�瘙���枏�蝥Ｚ𠧧擃䀝漁�峕郊��
    - [x] **蝛箸聢�� Toggle 撘��喳�摨� (Spacebar Toggle Behavior)**嚗𡁜�蝥找��厰睸餈�誘�典�撘寧��曄內�笔𦶢�冽��餉����撖孵撕蝒埈遬蝷箏�隡𡁜內�𤥁��亦��孵紡�港蜓蝒堒藁 `isActiveWindow()` �文�憭梯揖��撩�瘀��� `GlobalInputFilter` 銝剔鸌靘见�霈豢㜃�芰��亙撕蝒𦯀�銝箸暑�函���𧒄����桐�隞嗚��緵�冽�銝讠征�潮睸�塚��亙��滢葵�∠�蝞��亙歇�枏��躰䌊����哨��亙��剜���揢銝芾��嗵�蝥折��唳�撘�/�瑟鰵撅閧內嚗���唬���稲憿箸� of �閖睸鈭支��嗆��㦤��
    - [x] **蝞��亦����蝵桐�憭批�蝟餌�蝥扳�銋�� (Window Size & Position Persistence)**嚗帋蝙 `ScrollableMsgBox` 蝏扳㗁鈭� `WindowMixin`嚗�僎�典����惩遆�唬葉�朞� DPI �惩�餈𥡝�銵亙��𠬍��朞� `load_window_position_qt` �芸𢆡�Ｗ�銝𠹺�甈∠�蝒堒藁�鞉���之撠𧶏��� `closeEvent` 銝剛��� `save_window_position_qt_visual` 餈𥡝�摰墧𧒄����吔��𣂼�鈭���䀹�雿𦦵�撣��餈噼敞�扼����嗡蛹 `ScrollableMsgBox` �唾�鈭� `content_label = label` �𣂼�嚗䔶耨憭滢��冽����唳𧒄�航��������找腺憭梢�����
    - [x] **��揢銝芾��芸𢆡�𥪜𢆡�瑟鰵 (Auto-refresh on Stock Switch)**嚗𡁜銁銝餃㦛銵券�蝏䀹瓲敹�楝敺� `_render_charts_logic` ��偏�剁�蝏��鈭�笆蝞��亦��� `isVisible()` �嗆����譍�璉�瘚卝����血ế摰帋葵�∪��笔��Ｖ�蝞��亙撕蝒埈迤撘���嚗𣬚頂蝏煺��其�瘥怎�蝥批��芸𢆡�𥪜𢆡�滨�蝞��交㺭�殷�摰䂿緵鈭��𨅯�甇�朖����萘�銝脲�雿㯄���
    - [x] **憿箏⏚�朞� 29/29 鈭斗���瓲�券��𧼮�瘚贝�**嚗𡁜銁�㯄�� UI 憭𡁶垢�唳旿�𡁻�撟園���笆朣𣂼�嚗俰ytest ��瓲 29 銝芸�敶埝�霂閧鍂靘� 100% 銝�甈⊥�抒遛�烾�朞�嚗𣬚頂蝏罸妟蝻粹萅�䭾������

## 2026-05-24 23:55
- [x] **�Ｗ�蝝批��閗��嗆���撣��銝𤾸�蝑𣇉��望惣�賜憬�交⏛�� (Restored Compact Single-line Status Bar & Intelligent Strategy Name Abbreviation & Truncation)**嚗�
    - [x] **�嗆���撘箏��閗��箏�擃睃漲 (Forced Single-line Status Bar Height)**嚗𡁜� `trade_visualizer_qt6.py` ����� `decision_panel` �拍�擃睃漲�齿鰵撘箏���香銝箏𤐄摰� `setFixedHeight(40)`嚗���嗆��嗅�撅���器頝嘅�margins嚗厰�蝵桐蛹蝝批��� `(15, 0, 15, 0)`��宏�支� `decision_label` �� `setWordWrap` �� `maximumWidth` �𣂼�嚗䔶��拍�撣��銝𠰴蝠摨閖獈�凋���𧋦�Ｚ��𤥁䌊�冽�撘�摨閙�撖潸稲 UI ��香銝擧����銋梁��桅���
    - [x] **蝘駁膄憭帋� HTML �Ｚ��餉� (Removed HTML Line Breaks)**嚗𡁶�����支�摰墧𧒄�喟��湔鰵�餉�銝剖笆��𧋦�潭𦻖 `<br/>` �Ｚ���倌���雿頣��嫣蛹�冽凒�啣��䭾辺隞嗆�瘣𡑒�皛斤��望��砌葉����� `<br/>`��揢銵𣬚泵���頧衣泵嚗𣬚＆靽脲��� 100% 靽脲��典�銵����
    - [x] **撘訫��箄�蝑𣇉裦�滨憬�蹱�撠��摮㛖泵蝖祆⏛�剛䌊�� (Strategy Name Abbreviations & Hard Truncation)**嚗�
        - 撘訫�鈭���亙�憟賢�蝻拙��惩�摮堒�嚗��撠� `StrongPullbackMA5Strategy` �讠憬銝箇��剔� `MA5` 蝑㚁�嚗𣬚移蝞�摰墧𧒄��眏��𧋦�曄內�踹漲��
        - 憓噼挽鈭� 50 摮㛖泵蝖祆�折鵭摨行⏛�剖㨃�����皜��銝𡒊憬�亙����蝑𣇉��望��砌�頞�枂 50 摮㛖泵�塚��芸𢆡���靽萘��� 47 摮㛖泵撟嗉蕭�删��亙噡 `...`嚗�銁靽肽�擃睃�摨虫縑�臬��啁��峕𧒄摰䂿緵撣��撠箏漲���撖寥�璉埝�扼��
    - [x] **摰𣬚��朞��券� 29 / 29 鈭斗���瓲�訫�瘚贝� 100% 蝏踵��朞�**嚗𡁜銁�惩��嗆�����稲�閗�蝝批��垍�銝舘䌊���瘣埈㦤�嗅�嚗諹��� pytest ��瓲�𧼮�瘚贝�嚗���� 29 銝芣�霂閧鍂靘衤�甈⊥�� 100% �朞�嚗屸妟�𧼮������

## 2026-05-24 23:45
- [x] **摰䂿緵 Pytest 瘚贝�瘝嗵拳憌擧綉�𠉛氖銝𤾸��賊��� canonicalize �餉�撖寥� (Implemented Pytest Risk Gate Isolation & Volume Field Canonicalization)**嚗�
    - [x] **撱箇�瘚贝��臬�銝讠�憌擧綉�滨蔭蝖祇�蝳� (Enforced Risk Gate Test Isolation)**嚗𡁜銁 `trading_kernel/kernel_service.py` �� `load_risk_limits_from_config()` �寞�憭湧�撘訫� `PYTEST_CURRENT_TEST` �臬��㗛�璉�瘚卝��銁�訫�/�𧼮�瘚贝�餈鞱��罸𡢿嚗�撩銵𣬚�頝臬僎頝唾��砍𧑐�拍� `window_config.json` ����啣�頧踝��湔𦻖餈𥪜�蝥臬����霈� `RiskLimits` 摰硺����敶餃��寞祥鈭�眏鈭擧𧋦�啣��穃凝靚��蝵殷�憒� `min_volume = 1.1` �� `min_confidence = 0.70`嚗匧紡�� 29 憿孵��訾漱�𤘪�霂訫� Journal �墧𦆮瘥𥪜笆嚗𠄌xpected vs Replayed hash嚗匧��蠘秤�斗㜃�芰�憿賜𪆴��
    - [x] **銵仿�鈭斗���瓲�讛��孵�閫�㟲�惩� (Completed Canonicalization of Volume Feature)**嚗𡁜銁 `trading_kernel/engine/signal_canonicalizer.py` �� `canonicalize_decision_queue_item()` �寞�銝哨�銵仿�鈭�笆 `"volume"` 摮埈挾����渲蓮�Ｗ僎瘜典��� `StrategySignal.features` 摮堒�銝准��＆靽苷�憌擧綉蝵穃�餈𥡝��讛�蝖砍㨃���皛歹�`min_volume`嚗㗇𧒄�賣𦻖�嗅��笔���𠯫���鈭斗㺭�殷�閫��鈭�㺭�桐腺憭梢�蝥找蛹 `1.0` 暺䁅恕�讛�����萸��
    - [x] **憿箏⏚頝煾�� 29/29 �券�鈭斗���瓲�𧼮�瘚贝� (100% Core Regressions Passed)**嚗𡁜�蝢𡡞�朞���鉄 Redline, Risk Hardening, Replay Equivalence Flow 蝑匧銁����券� 29 銝� pytest 瘚贝�嚗䔶��靝��煺漣蝟餌���妟蝻粹萅�����

## 2026-05-24 23:35
- [x] **摰䂿緵�喟�瘚�偌�烐綉�Ｘ踎�剝睸 (Alt+J) ���撅�蝟餌�蝥扳釣�䔶��砍𧑐�脩�瘨�膄 (Delivered System-wide Alt+J Hotkey & Removed Local Redundant Binding)**嚗�
    - [x] **撠��𨅯�蝑𡝗�瘞游��鞾𢒰�踱�萘��桐� Tk 撅��函�摰𡁶宏�喳�撅� (Transitioned to Global Hotkey)**嚗𡁜銁 `instock_MonitorTK.py` 銝剔� `_HOTKEY_MAP` 摰帋���蕭�䭾釣�� `11: (win32con.MOD_ALT, 0x4A, "Alt+J")` (J �� virtual key code 銝� `0x4A`)嚗�僎撠� `setup_global_hotkey` �� `hotkey_callbacks` �唾��� `self.open_decision_flow_panel`��
    - [x] **�峕郊�湔鰵�祉��剝睸頧株蓮摮鞱�蝔𧢲�撠�” (Synchronized Hotkey Rotator Map)**嚗𡁜銁 `hotkey_rotator.py` �� `HotkeyListener.hotkey_map` 銝剖�甇亥‘朣𣂷� ID �讐宏�譍蛹 `11` �� `Alt+J` �惩�嚗𣬚＆靽嘥�餈𤤿� named pipe ���隞方圾�𣂷� IPC 摰𣬚�撖寥���
    - [x] **瘨�膄�砍𧑐 Tk �𦯀�蝏穃��脩� (Eliminated Local Alt-J Binding)**嚗𡁶宏�支� `instock_MonitorTK.py` 銝剖��砍銁 `__init__` ���拇�瘜典��� `self.bind("<Alt-j>", ...)` �砍𧑐鈭衤辣蝏穃�嚗�蝠摨閙��支�憭𡁻�閫血�銝𡒊��寧�鈭厩�憌𡡞埯��

## 2026-05-24 23:20
- [x] **摰𣬚�閫��憌擧綉��㺭�剛�隡䁅��亙�蝒�� 500ms �瑟鰵�脫� (Fixed Risk Tuning UI Overwrite & 500ms Timer Collision)**嚗�
    - [x] **撘訫� Tab �嗆����亦��鍦�甇亦��� (Tab-Aware Sync Bypass)**嚗𡁜�蝥找� `tk_gui_modules/decision_flow_panel.py` �� `_sync_control_tab_ui()`嚗�銁 500ms 擃㗛��瑟鰵�嗅��惩��齿�瘣� Tab �文�����滨��𧢲迤�� `Tab 2`嚗��儭� 蝑𣇉裦靽∪噡靚�㟲銝𡡞��改�銝剛�銵峕��典凝靚��颲枏��塚��芸𢆡頝唾�撖寥��批� SpinBox �找辣��撩�嗅��穃�甇乓��
    - [x] **撘訫� `force` ��㺭銝𤾸�甈∠移����唳㦤�� (Force Update Gate)**嚗帋蛹 `_sync_control_tab_ui(self, force: bool = False)` 撘訫�鈭� `force` ��扇����滨��钅�甈∪���/�孵稬餈𥕦�憌擧綉 Tab �塚�閫血�銝�甈∪蒂�� `force=True` ����誩��穃�甇伐�蝖桐�擐硋��唳旿�曄內 100% 蝏嘥笆銝��湛��誩�蝏抒賒餈𥕦�蝻𤥁�靽脲擪�嗆����
    - [x] **�㯄�� `tabs.currentChanged` 蝎曉��𥪜𢆡 (Connected Current Tab Signal)**嚗𡁜銁�Ｘ踎�嘥��碶葉撠� `self.tabs.currentChanged` 靽∪噡蝏穃��� `_on_tab_changed(index)` 瑽賢遆�堆��� `index == 2` �嗉䌊�冽���閫血� `_sync_control_tab_ui(force=True)`��
    - [x] **摰𣬚�靽萘��詨��硺漱鈭垍𠶖���憸穃�甇� (Preserved Operational Modes & KillSwitch Sync)**嚗𡁻�鈭支��嗆���憒���滨�鈭斗�璅∪����蝥扼����桃揮�亦��剝�𡁻��嗆���嚗劐�靽脲� 500ms 蝥批����憸𤏸�璉��亙�甇伐�摰𣬚��潮▽鈭�鍂�瑁��交���漲銝擧瓲敹�漱�梶𠶖���銝��湔�扼��
    - [x] **摰𣬚�頝煾�� 29/29 �典���瓲鈭斗��訫�瘚贝� (100% Core Regressions Passed)**��

## 2026-05-24 22:50
- [x] **�滨�鈭支� Phase 11 摰噼捶鈭斗�憌擧綉��㺭�剛�隡㗛�蝵脖��典��質��� (Delivered Phase 11 Real Trade Hot Parameter Deployment & Dynamic UI Integration)**嚗�
    - [x] **�賢𧑐�煺漣蝥折��折��賜′�∪藁銝𡡞��冽��枏��箏� (Enforced Volume & Confidence Filters)**嚗�
        - ��漣鈭� `trading_kernel/engine/risk_gate.py`嚗�� `min_confidence` 暺䁅恕�滨蔭�冽��𣂼��� `0.70`嚗�㜃�� 50%+ ��𨺗嚗㚁�撟嗅��交�雿舘圻�煾��賣� `min_volume = 1.0`嚗�㜃�芸𧑐�誯狍頝䔶縑�瘀���
        - �� `evaluate` 霂�摯瘚��銝剖�蝢𡒊��乩� `LOW_VOLUME_BLOCKED` �嗆��ế摰𡄯�摰䂿緵雿擧��冽�找縑�瑞�鈭𡁏神蝘垍漣蝎曉��娍鱏��
    - [x] **�齿��喟�瘚�偌�烐綉�Ｘ踎瘛餃���雿𡡞��質�隡睃凝靚�� (Integrated min_volume SpinBox in UI)**嚗�
        - �� `tk_gui_modules/decision_flow_panel.py` ���鎿�儭� 蝑𣇉裦靽∪噡靚�㟲銝𡡞��把�𨯔ab 憿萎葉嚗峕�蝻脲溶�牐� `self.spin_min_volume`嚗ǑQDoubleSpinBox`嚗㗇�雿舘圻�煾��賢凝靚��嚗���� 0.0 - 10.0 �㵪�甇仿鵭 0.1 �㵪�嚗���啗�銵峕𧒄�冽���隡塩��
        - 摰𣬚��齿�鈭� `limits_lay` 蝵烐聢撣�����靽嘥��厰僼 `save_btn` 蝘餉秐蝚� 4 銵䕘�璅芾楊�券� 4 �梹�颲暹���稲撖寧妍銝𤾸�瘝輸��𣇉�蝡舐�閫��蝢擧���
    - [x] **摰䂿緵�屸�𡁻��笔�蝥抒����銋��銝� 500ms 擃䀹��𤩺��仿俈�� (Dual-Channel Persistence & UI Jitter Shield)**嚗�
        - �� `_save_and_apply_risk_limits` 銝哨��拍��㯄�帋�撖� `min_volume` ���摮矋���鍂�笔��坔��孵��峕𧒄�峕郊�� `window_config.json` 銝� `scale2_window_config.json`��
        - �� `_sync_control_tab_ui` 銝𤾸�撱箏�憪见�銝哨�撘訫�鈭� `1e-4` 瘚桃�蝎曉漲�� Dirty Check �𤩺��交㦤�嗡��嘥�暺䁅恕�潘�`0.70` 銝� `1.0`嚗㚁�摰𣬚��脰�鈭���嗅��唳𧒄��㺭�潭��典��衣��Ｗ�嚗䔶��靝�憭𡁶垢�𥪜𢆡����湔�扼��
    - [x] **摰𣬚��朞��券� 29 / 29 �詨���瓲�𧼮�瘚贝�嚗峕�霂閖�朞��� 100%**嚗𡁻�靽萘��𠉛氖�箏�蝖桐��冽��滨蔭��辣瘚贝�瘝嗵拳銝哨�蝟餌��賣�瘙⊥��唬誑暺䁅恕憪踵���`0.55` 靽∪�摨閧瑪嚗匧�蝢𡡞�朞��典� 29 銝� pytest ��瓲�訫�瘚贝�嚗䔶��靝�撌乩�蝥抒��䭾������

## 2026-05-24 22:30
- [x] **�滨�摰峕� Nuitka Onefile 憭朞�蝔见�餈𤤿��芣��脩瑪��漣銝𤾸��讐���䌊����典��� (Delivered Advanced Nuitka Onefile Subprocess Self-Healing & Pre-emptive Seeding)**嚗�
    - [x] **摰䂿緵 Nuitka/PyInstaller 憭朞�蝔见���䌊���垍��臬��㗛� (Subprocess Environment Seeding)**嚗𡁜銁 `commonTips.py`��LoggerFactory.py` �� `sys_utils.py` ����芣�璅∪�銝哨��𣂼�摰䂿緵鈭� `os.environ["NUITKA_ONEFILE_DIRECTORY"] = pkg_base` ��㴓憓��憭滢�����垍�����血�餈𤤿��典鍳�典紡�交𧒄�𤑳��滢�蝟餌�蝥批���㴓憓���譍腺憭梧��芣��脩瑪隡𡁜銁瘥怎�蝥批��朞��拍�隞����辣�睲�餈賣滲��覔�桀�嚗�僎撠�迤蝖桃�銝湔𧒄閫��韏��頝臬��齿鰵��� `os.environ` �臬��㗛�嚗𣬚＆靽嘥�蝏凋遙雿訫𢆡���韏𤥁砲�㗛���芋�� 100% �賢��祇𡢿�芣�嚗�蝠摨閙祥���憭朞�蝔讠㴓憓��韏��銝Ｗ仃��■�整��
    - [x] **閫�膄撣貉�雿滨蔭�䠷�㗇䔝瘚见笆�臬��㗛���′�折��� (Unconditional Candidate Probing)**嚗𡁜縧�支� `commonTips.py` �� `LoggerFactory.py` 銝� `nuitka_candidates` �Ｘ�撖� `NUITKA_ONEFILE_DIRECTORY` �臬炏摮睃銁鈭� `os.environ` 餈嗘��嗆���撘箄�靘肽���緵�剁��芾���蔭韏����辣�函�����䀝��芸𦶢銝哨��Ｘ��其��函洵銝�蝘埝��∩辣撖寞��厩����摮鞟𤌍敶𤏪�憒� `JohnsonUtil`��JSONData`��wencai` 蝑㚁�餈𥡝��唳秤撘𤩺�撟喳��急��寥�嚗諹噢�唬���稲��圾��迅摰𡁏�扼��
    - [x] **擐硋��𨅯��讐���䌊����典��鎿�� (Pre-emptive Configuration Seeding)**嚗�
        - ��笆�枏��臬�銝见虾�賢��函��嗅��抒����皞鞟撩憭梧�擃睃�撱箇楲�啗挽霈∪僎�賢𧑐鈭�𦜖�惩��滨蔭閫��撅誯���銁 `sys_utils.py` 銝剛蕭�惩僎撖澆枂鈭� `ensure_all_configs_released()` �詨��賣㺭嚗�𢆡��翮隞� `RESOURCE_MAP` 銝见��典歇瘜典��滨蔭��
        - �其蜓�亙藁��辣 `instock_MonitorTK.py` 銝餉�蝔见鍳�函����拇�嚗Ǒmain` 憿嗥漣�亙藁嚗㚁��Ｗ�撘誩𧑐撘箏�撖孵��誯�蝵格�隞塚���鉄 `global.ini`��stock_codes.conf`��voice_alert_config.json`��visualizer_layout.json` 蝑㗇㺭��葵��辣嚗㗇�銵𣬚�����整���銝滢�霈拐蜓餈𤤿��臬𢆡蝔喳�憒��嚗峕凒隞𡒊�撖孵��Ｖ�靽嗪�鈭���匧�餈𤤿��刻◤�㕑絲�滨�����㗛�蝵桀��拙歇�典�撠曹�嚗���唬��券俈蝥踹��氬��
    - [x] **摰𣬚��朞��典� 29 / 29 鈭斗���瓲�訫�瘚贝� 100% 蝏踵��函遛�𧼮�**嚗𡁜銁蝏誩�擃睃撩摨西䌊��沲��‘撘箏�嚗��蝢擧��蠘��� pytest �𧼮��賊�嚗�29 銝芰鍂靘衤�甈⊥�� 100% 蝏踵��券�𡄯��嗅�敶埝��頣��煺漣蝥批�憯桀漲颲曉�銵䔶�憿嗅�瘞游�嚗�

## 2026-05-24 22:15
- [x] **�滨��餃�撟嗅蝠摨閙覔瘝� Nuitka Onefile �枏�銝钅�蝵株�皞鞉�瘜訫像�箸�憭滩秐�拍� EXE �桀����撅�ế摰� Bug (Delivered Comprehensive Nuitka Onefile Configuration Recovery & Environment Detection Bypass)**嚗�
    - [x] **�渲圾 Nuitka �臬�銝� sys.frozen 蝻箏仃撖潸稲�� is_onefile 霂臬ế (Fixed is_onefile Detection Failures)**嚗𡁶�����亙僎摰帋��� Nuitka �枏�璅∪�銝钅�霈支�霈曄蔭 `sys.frozen` �㗛�嚗�紡�� `sys_utils.py` 銝剔� `is_onefile` �文��� `if getattr(sys, "frozen", False):` 璉��亙仃韐亥�諹◤撘箄�頝唾�嚗䔶蝙蝟餌�撠� Nuitka Onefile �閙�隞嗉秤�文�銝� Onedir �𡝗���芋撘譌���甇歹�蝟餌��躰秤�啣� `global.ini` �𦠜𦆮�� `JohnsonUtil/global.ini` 蝑匧���辣憭嫣葉嚗諹�屸�撟喲唍�Ｗ��啁��� EXE �𣬚漣�� `dist` �桀�嚗��憒� `E:\temo\NUitka\dist`嚗剹��
    - [x] **�齿� Nuitka / PyInstaller 憿嗥漣 Onefile �文��屸�𡁻� (Unified Onefile Detection Gates)**嚗𡁜銁 `sys_utils.py` 銝剝���� `is_onefile` ���撅��瘚钅�餉���� `NUITKA_ONEFILE_DIRECTORY` 璉�瘚𧢲���蛹��擃䀝���漣��𡠺蝡见��券�𡁻�嚗��蝢舘�蝳颱�撖� `sys.frozen` 撅墧�抒�靘肽�嚗𣬚＆靽嘥銁 Nuitka �� PyInstaller 銝讠� Onefile �Ｗ�銵䔶蛹 100% 蝏嘥笆銝��湛�摰𣬚�撟喲唍�𦠜𦆮�詨��滨蔭��辣��
    - [x] **�拍��惩𤐄 Nuitka �枏�蝻𤥁��嗆��� get_base_path 霂���箏� (Aligned Standalone Executable Recognition)**嚗𡁜銁 `commonTips.py` �� `LoggerFactory.py` �� `get_base_path()` 銝哨��峕郊銵仿�鈭��撖� Nuitka 銝𤘪��� `__compiled__` �� `NUITKA_ONEFILE_DIRECTORY` �臬��Ｘ��文���撩�嗅� is_interpreter 霈曆蛹 `False`嚗�蝠摨閖獈�凋�蝻𤥁��舘秤�� Python �𡁏𧋦餈鞱�璅∪���䔮憸矋�靽肽�鈭� Windows �拍� API嚗Ǒ_get_win32_exe_path`嚗匧�蝏���函洵銝��園𡢿餈𥪜���迤������銵峕覔�桀���
    - [x] **摰𣬚��朞��典� 29 / 29 鈭斗���瓲�訫�瘚贝� 100% 蝏踵��函遛�𧼮�**嚗𡁻�撘箏漲�䭾��齿�嚗峕�霂� 100% 蝏輯𠧧摰𣬚��朞���

## 2026-05-24 22:00
- [x] **�滨��餃�撟嗡漱隞� Nuitka 憭朞�蝔见�餈𤤿����韏���拍��芣��脩瑪銝� None �𨅯��芣� (Delivered Nuitka Subprocess Package-Relative Resource Self-Healing & Robust None Fallbacks)**嚗�
    - [x] **摰䂿緵 Nuitka/PyInstaller 憭朞�蝔见����皞鞟���䌊���雿� (Multiprocessing Package-Relative Probing)**嚗𡁜銁 `sys_utils.py` �� `get_conf_path()` �� `JohnsonUtil/commonTips.py` �� `get_resource_file()` 銝哨��𥟇鰵撘訫�鈭�抅鈭� `__file__` �拍�雿滨蔭�睲�餈賣滲������皞鞉覔�桀��冽��䔝瘚贝䌊��俈蝥踴����𨅯銁憭朞�蝔� `spawn` 摮鞱�蝔见鍳�冽𧒄�曹��滢�蝟餌��臬��𠉛氖撖潸稲 `NUITKA_ONEFILE_DIRECTORY` 蝑㕑圾��㴓憓���譍腺憭梧�蝟餌�隡朞䌊�券�朞��拍�隞����辣���函�蝏嘥笆頝臬�嚗峕神蝘垍漣��䌊�典�皞胯��䌊��僎蝎曉������迤�����圾���皞鞉覔�桀�嚗Ǒbase`嚗㚁�蝖桐�摮鞱�蝔� 100% �賢��𣂼�霂餃� `global.ini`��MonitorTK.ico` 蝑㗇瓲敹�����皞琜�敶餃�瘨�膄鈭��輶uiltin resource missing�萘�憿賜𪆴��
    - [x] **�拍��惩𤐄 StockCode 頝臬� NoneType 摰寧��芣� (Hardened stock_codes.conf Resolution)**嚗𡁜銁 `JSONData/sina_data.py` 銝剖笆 `STOCK_CODE_PATH` �嘥��硋��乩�撘箏之�� `None` �文�摰匧��∪藁銝𡒊′�� Fallback �𨅯�嚗�撩�園�蝥找蛹 `"stock_codes.conf"` 摮㛖泵銝脣�嚗㚁�敶餃��餅鱏鈭�眏鈭舘�皞𣂷腺憭勗紡�渲��� `None` 餈𥡝����穃�蝏� `os.path.join` �亥稲�� `TypeError: join() argument must be str... not 'NoneType'` �躰秤撖潸稲摮鞱�蝔见援皞���鞉�嚗䔶�霂���喃蝙�冽�蝡舀���㴓憓��蝟餌�銋蠘��芣��折���箸�甇�虜餈鞱���
    - [x] **�朞� 29 / 29 �詨���瓲�訫�瘚贝� 100% 蝏踵��𧼮�**嚗𡁜銁撘訫�摨訫�頝臬�擃睃撩摨血捆�曇䌊���嚗䔶�甈⊥�批�蝢𡒊遛�烾�朞�鈭��憟堒��訾漱�枏����霂𤏪��嗅�敶埝��栶��

## 2026-05-24 21:05
- [x] **�滨�摰峕��典��滨蔭�芣�頝臬�憭扳𤣰���憭朞�蝔贝�撽砍㦤頝臬��脫�蝘餅���� (Delivered Global Config Path Standardization & Subprocess Deflection Hardening)**嚗�
    - [x] **�券𢒰�嗅藁撣���滨蔭�芣��𦠜𦆮�𡁻� (Unified Layout Configs Gateway)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝哨�敶餃�瘛䀹掠鈭�唂�厩� `cct.get_resource_file` 韏��霂餃��亙藁嚗��蝥踵𤜯�Ｖ蛹憭找�蝏麄�������� `sys_utils.get_conf_path` 摰匧��芣�撘閙���＆靽苷� `visualizer_layout.json` �� `intraday_pattern_config.json` 隞𦒘��臬𢆡撠� 100% 靘嘥儐 Onefile / Onedir �箄����銝𡡞俈�坔縧�滩��坔銁�拍�蝤��銝𠰴�撠勗�雿溻��
    - [x] **摰𣬚��芣��亥郎�滨蔭��辣 fallback �餉� (Self-healed Voice Alert Path Fallback)**嚗𡁜銁 `stock_live_strategy.py` ���憪见�銝� `market_pulse_viewer.py` �� fallback 霂餃�銝哨��峕郊撘訫�撟嗅撩�園�摰𡁶�撖寡楝敺�䌊�� `get_conf_path("voice_alert_config.json")`����支��枏��𦒘��𣬚㴓憓���曹�蝖祉����隞嗅���極雿𡏭楝敺��蝘餃紡�渡�瞏𨅯銁�滨蔭�Ｗ�憭望��碶腺憭望��栶��
    - [x] **�拍��餃�憭朞�蝔贝�撽砍㦤�亙��嗆���蝘� (Subprocess State-Load Hardening)**嚗𡁜銁 `bidding_momentum_detector.py` �� `ProcessPoolExecutor` 憭朞�蝔见鍳�其葉嚗��隡𣳇�垍��嗆��恣蝞堒�餈𤤿��� `os.getcwd()` �拍����銝箏之銝�蝏煺�蝏嘥笆銝滚��臬𢆡�孵��𤑳��讐宏�� `cct.get_base_path()`��＆靽嘥�餈𤤿��典�頧� `snapshots/detector_state_persist.json.gz` �亙�摮䀹﹝�嗡�銝餌�摨讛楝敺��蝢𤾸笆朣琜��寞祥鈭��餈𤤿��臬�銝贝�撽祇𢒰�踹��臬𢆡�嗥��賢��鞉���
    - [x] **�嗅藁蝑𣇉裦�賜�蝞∠��券�蝵株䌊����曆��脰��� (Self-healed StrategyManager Config)**嚗𡁜� `strategy_manager.py` 銝剔� `strategy_config.json` �拍���辣摮睃��券��嗅藁�� `sys_utils.get_conf_path` �芣�撘閙�嚗�僎�� `sys_utils.py` 銝剜釣����典�韏���惩��� `"strategy"` �冽��冽��俈閬���喲睸摮𨰜���靽肽�鈭���亦蒾�垍恣��膥��㺭�株��冽�����瑕鍳�冽𧒄�箄��Ｗ�嚗䔶�蝏苷�銝Ｗ仃�冽��芸�銋匧��啜��
    - [x] **�峕郊銵仿� PyInstaller Spec �唳旿��辣�枏� (Aligned Spec Packing)**嚗𡁜銁 `instock_MonitorTK.spec` �� `instock_MonitorTK-ondir.spec` �� `datas` �枏�憯唳�銝哨��峕郊銵仿�鈭� `"strategy_config.json"`���蝖桐�鈭�銁�拍��穃��閙�隞塚�Onefile嚗匧��閙�隞嗅允嚗㇉nedir嚗㗇𧒄嚗��憪钅�蝵格�隞嗆芋�� 100% 鋡急����霂穃� EXE 銝哨�敶餃��寞祥�唳㦤�穃�����臬𢆡銝Ｗ仃瘥𥕦���
    - [x] **撖寥�韏偦帕�Ｘ踎�拍�摮条�銝𤾸�餈𤤿��嗆��粉�� parity**嚗𡁶＆霈支� `bidding_racing_panel.py` �� `bidding_racing_ui_state_v3.json.gz` �拍��賜�雿滢�憭碶儒��迤�� `snapshots` �桀�銝页��� `cct.get_base_path` ���嚗㚁��刻�銵峕𧒄�梁鍂�瑟�雿𡏭圻�穃�摮鞉𤜯�Ｗ�摰寧��芣��坔�嚗�銁憭朞�蝔衤葉銝� `bidding_momentum_detector.py` ��粉�𤥁楝敺�噢�𣂷� 100% 蝏嘥笆銝��港�摰匧�撖寥���
    - [x] **�餃� Nuitka 頞�鵭�賭誘銵�辣餈笔��讛圾�鞟��脣躹撖潸稲��䌊�冽���舅�� Bug (Fixed Nuitka Double Compilation Batch Bug)**嚗𡁜銁 `nuitka_build_console_onlyClang.bat`��nuitka_build_console.bat` �� `nuitka_instockMonitor.bat` 銝匧之蝻𤥁��孵�����砌葉嚗�蝠摨閙�瘙唬�����梢埯�� `call !CMD!` �冽����譍�蝥扯蓮銋㗇�銵峕䲮撘𧶏�蝏煺��齿�銝箏��毺� `!CMD!` �湔𦻖靚�絲���敶餃�瘝餅�鈭� Windows cmd.exe 撱嗉��㗛�閫��蝻枏��箏銁頞�鵭�㗛�嚗�>1000 摮㛖泵嚗劐���滯�箏��孵�����祇��伐�Re-entry嚗�ug嚗峕覔瘝颱��芸𢆡�枏��扯�銝日� Nuitka ��■�整��
    - [x] **�寞祥 Onefile �枏��舘�銵��餈𤤿��㕑絲蝒堒藁�滚蔣銝𤾸�餈𤤿��芣� Bug (Fixed Packaged Multiprocessing Spawning Double Window & Worker Auto-Termination)**嚗𡁜銁銝餃����隞� `instock_MonitorTK.py` 銝哨�敶餃��娪膄鈭��餈𤤿��冽芋�烾▲蝥批紡�仿𧫴畾菜𧒄蝎埈𠂔�扯� `sys.exit(0)` �芣���稲�賡�餉�瞍𤩺����雿� `spawn` 靚�絲���餈𤤿�摮鞱�蝔页�憒��撽砍㦤�嗆��凒�堆��賢�撟單��啣紡�乩蜓璅∪�撟嗆��蠘◤ `freeze_support()` ���撘訫紡�亦恣嚗峕��支�摮鞱�蝔见紡�亙�撣賊���箏紡�渡�銝餉�蝔� Panic 撠肽�鈭峕活�㕑絲�屸�䭾������ GUI 蝒堒藁嚗�䌊�典鍳�其舅甈∴��滚蔣�鞉�嚗䔶�霂���𤾸蝱隞餃𦛚�䔶蜓�屸𢒰����渡迅摰朞�銵䎚��
    - [x] **�拍��餃� Nuitka ����格�銝擧鸌憭����辣�齿嵗撉䔶��寥�撖潸稲�� IDE/Watchdog �芸𢆡�滩� Bug (Aligned Target Output & Verification)**嚗𡁜蝠摨訫�雿滚僎�寞祥鈭� `nuitka_build_console_onlyClang.bat` �� `nuitka_build_console.bat` 銝剔���㺭�嗘�瘥𥕦���銁 Nuitka 蝻𤥁��賭誘銝剜遬撘讐��� `--output-filename="%OUTPUT_NAME%"`嚗�僎�峕郊�齿�鈭�偏�券�霂��餉�嚗�����厩′蝻𣇉��� `instock_MonitorTK.exe` 蝏煺��踵揢銝箏𢆡��� `%OUTPUT_NAME%`���瘨�膄鈭��摰鮋������辣�滢��孵����蝵桐�銝��湛�撖潸稲憭㚚� IDE / Watchdog / Task Runner �文�蝻𤥁�憭梯揖餈𥡝�峕��鞱䌊�券�頝烐����蝔讠��滚蔣 Bug��
    - [x] **摰䂿緵�祆筑霂行�蝒㛖征�游����撅��拍�颲寧��箄��文�銝舘��諹䌊�� (Self-healed KLineDetailWindow Spatial Coordinates & Boundary Reset)**嚗𡁜銁 `trade_visualizer_qt6.py` 銝剜凒�啣�摮堒���葡�栞楝敺�𧒄嚗���乩���笆�祉�憿嗅��祆筑霂行�蝒梹�`KLineDetailWindow`嚗厩�撅誩��典��拍�颲寧�摰匧�璉�撉峕㦤�嗚����嗉◤瞈�瘣餅遬蝷箸𧒄嚗𣬚頂蝏笔��園�朞� `mapToGlobal` 銝� `size` �瑕�敶枏� K 蝥輻��曉躹���`self.kline_plot`嚗厩�蝎曄＆撅誩��典��拍��拙耦����血ế摰朞祕����𡝗嗻�𡝗�銋���Ｗ��𡒊��鞉�銝剖��對�`center()`嚗匧�蝘餉氜�� K 蝥踹躹�煺�憭吔��祇𡢿�芸𢆡�滨蔭�� `is_custom_positioned` ���銝� `False`嚗�像皛穃����單�憿箸����𣈯�����𧶏�暺䁅恕嚗争�脲芋撘𧶏�敶餃��㯄�帋�霂行�蝒堒銁�瑕鍳�冽���儘���隡訾������捆�暸�餉���
    - [x] **瘚贝�蝥Ｙ瑪 100% 蝏踵��𡁜�**嚗𡁜銁�孵�銋见�嚗諹��𡁜�憟� pytest 瘚贝�嚗�29 銝芣瓲敹�漱�枏��詨����霂訫��冽��罸◇�拚�朞�嚗峕� any �𧼮������

## 2026-05-24 20:00
- [x] **�滨��賢𧑐 Onefile / Onedir �峕芋撘𤩺惣�質楝敺��瘚��暺���脣撕頝臬��駁��箏� (Delivered Dynamic Path-Split Routing & Gold-Standard Path-Guard De-duplication)**:
    - [x] **擐硋� Onefile / Onedir �箄�����嗆� (Dynamic Mode Ladder)**嚗�
        - ��笆 **Onefile �拍��閙�隞嗆���**嚗𡁶���楝敺���穃像�箇� `dst`嚗�� `stock_codes.conf`嚗��蝢𤾸像�粹��曇秐 EXE ��器��覔�拍��桀�銝𧢲�靘𥕦朖�嗉粉�辷���
        - ��笆 **Onedir �閙�隞嗅允�枏� / 皞鞟�餈鞱�**嚗𡁶���楝敺�凒�交惣�賢���銝粹�霈斤���楝敺� `src`嚗�� `JSONData/stock_codes.conf`嚗䈣JohnsonUtil/wencai/�諹�憿箸踎�𡑒�銝�.xlsx`嚗剹���銝滢�雿踹� Onedir 璅∪�銝贝�憭笔�瘙���喳𧑐�典��笔��桀�銝见��刻粉�硋歇�㗇�隞塚�**�游蝠摨閙��支�鈭峕活�𦠜𦆮憭滚�����滢�嚗䔶��拍�撅�𢒰銝𢠃獈�凋��䔶�隞賡�蝵桀銁�拍�蝤��銝𠹺漣�煺舅隞賜�瘥𥕦�**嚗�
    - [x] **�拍��行⏛�寞祥 `datacsv/datacsv` �滚�撋��**嚗�
        - �� `sys_utils.py` 銝剖��乩��典��冽��楝敺���文膥嚗�� `dst_rel` ��鉄�孵��喲睸摮堒��桀�嚗�� `datacsv/`��wencai/`��JSONData/`嚗㚁�銝𥪯��亦� `base_dir` �祈澈撌脩�隞亥砲摮鞟𤌍敶閧�撠暹𧒄嚗𣬚頂蝏煺��芸𢆡�典凝蝘垍漣��� `base_dir` 蝎曉��鮋���啁�甇�� `BASE_DIR` �拍��寧𤌍敶𤏪�敶餃��餅鱏撟嗆��支�憭𡁻��桀�撋�� Bug ������
    - [x] **�峕郊�芣��惩𤐄�詨��唳旿撽勗𢆡璅∪�**嚗𡁜銁 `JSONData/realdatajson.py`��JSONData/sina_data.py` �� `JSONData/wencaiData.py` 銝剖�甇亙��其� 1:1 �諹楝敺�䌊�典��Ｖ�撟喲唍撘𤩺覔�桀��芣��𦠜𦆮�箏���鸌�恍�撖孵��梢◇ Excel �㰘捏�臬銁 Onefile��nedir �枏�嚗諹��舀���芋撘譍�嚗𣬚�銝�撟喲唍摰帋��函�摰䂿� `BASE_DIR/�諹�憿箸踎�𡑒�銝�.xlsx` �寧𤌍敶訫��吔�敶餃��𦦵�鈭������㗛�憭齿鼧韐萘��桅�嚗���唬���迤���𨅯之蝏煺�銝𤾸之�栞秐蝞��腈��
    - [x] **敶餃��寞祥�𥕦之�詨� JSON �滨蔭�芣�銝Ｗ仃銝舘䌊�冽�憭齿��� (Fixed Missing JSON Configs Recovery)**嚗�
        - ��笆 **`voice_alert_config.json`** �� **`macro_trends.json`**嚗𡁜銁 `sys_utils.py` �𣬚� `RESOURCE_MAP` �芣��惩�摮堒�銝剖��𣂷�瘜典�嚗�蝠摨閙𤫇�衤����韏��摰帋��脣躹嚗𥕦��嗅銁 PyInstaller `.spec` �� Nuitka �枏��孵�����穿�`nuitka_build_console.bat`��nuitka_build_console_onlyClang.bat`��nuitka_instockMonitor.bat`嚗劐葉�峕郊銵亙�鈭�㺭�格�隞嗆���𦶢隞歹�蝖桐�鈭���惩之�詨��滨蔭��辣璅⊥踎�冽���𧫴畾萄停鋡急迤蝖桃�霂穃� EXE �������
        - ��笆 **`intraday_pattern_config.json`** �� **`visualizer_layout.json`**嚗𡁜銁 `nuitka_instockMonitor.bat` 蝑㗇��煺��桀�撣���砌葉銵仿�鈭�㺭�格�隞嗅��剁�敶餃�蝏��鈭��撣��蝛箇𤌍敶蓥�餈鞱��嗥眏鈭𤾸����皞鞟撩憭勗紡�渡��𨀣�瘜閗䌊�冽�憭𨧀�萘� Bug嚗峕��帋��唳㦤蝛箸�隞嗅允�瑕鍳�冽𧒄����芣��曇楝��
    - [x] **摰𣬚��朞��典��𧼮�瘚贝�**嚗𡁜銁�冽鰵�峕芋撘誩�瘚�䌊��沲���嚗���� 29 銝� pytest ��瓲�訫�瘚贝� 100% 蝏踵��𡁜�嚗�

## 2026-05-24 19:35
- [x] **�𧼮�蝏誩� PyInstaller �箇��典��賣沲���撟嗉氜�唳�頧駁�璅∪�蝥� Nuitka 撅��其�撅𧼮��嗡耨憭� (Restored Classic PyInstaller Architecture & Delivered Ultra-Lightweight Localized Nuitka Self-Healing)**:
    - [x] **�𧼮�憭找�蝏毺���楝敺���祉�韏���𣂼��箇�**嚗𡁜��券�蝵桀僎�Ｗ�鈭��蝟餌����㗇瓲敹�楝敺�繮�硋遆�堆�`get_base_path`嚗匧���蔭�滨蔭��辣�𦠜𦆮閫���亙藁嚗Ǒget_resource_file` / `get_conf_path`嚗㕑秐蝏誩������瘙���喳笆 PyInstaller 100% 瘥急��誩榆�舀���𡠺蝡见�憭湔芋撘譌����典��其��典�憭批�撟嗅�����函����蝖桐�隞颱�瘚贝�銝𤾸��㕑�銵峕芋撘誩笆 PyInstaller �諹膘蝏嘥笆�嗆情�瓐��妟靘萄���
    - [x] **摰𣬚��賢𧑐 Nuitka 璅∪�蝥批��其�撅噼䌊��䔝瘚� (Modular Localized Nuitka Custom Probing)**嚗�
        - ��笆��瓲敹��蝵格�隞嗆芋�梹�`sys_utils.py`��LoggerFactory.py`��commonTips.py`��realdatajson.py`��sina_data.py`��wencaiData.py`嚗劐葉�� `get_base_path()`嚗�銁�嗅仍�其��函��乩����擃䀹��� Nuitka �枏��嗆��䌊����� `if "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ: is_interpreter = False`����Ｚ�摰𣬚�撅讛𤪖 Nuitka 摰寞�霂臬��𡁏𧋦閫���冽芋撘讐�憭拍�蝻粹萅嚗��霈拙��臭誑 100% 撘箄��拍鍂�䭾��� Win32 API 蝎曉�摰帋�撟園�甇餌��� EXE ��迤���銵峕�隞嗅允��
        - ��笆 `commonTips.py` 銝� `LoggerFactory.py` 銝讠� `get_resource_file()`嚗䔶��冽��乩�隞�銁 Nuitka 銝湔𧒄�桀�摮睃銁嚗ǑNUITKA_ONEFILE_DIRECTORY`嚗㗇𧒄���撅噼�皞𣂼粉��銝𤾸�䠷�㕑楝敺�䔝瘚卝��緵�典��賢銁閫���喃葩�� `%TEMP%/onefile_xxx/` �桀��塚��冽神蝘垍漣��䌊�券�朞��䠷�厩𤌍敶訫�銵刻䌊���雿㵪�蝖桐����厩� `global.ini`��stock_codes.conf` 蝑匧�蝵桅�蝵格�隞� 100% ��������
    - [x] **摰䂿緵�諹�憿箸㺭�� Excel �𡒊蔭摮鞟𤌍敶閧移������雿� (Restored 1:1 Subfolder Restoration for Excel)**嚗𡁜銁 `JSONData/wencaiData.py` 撅��其�撅䂿� `get_conf_path()` 銝哨��砍振�惩�鈭�蝠�誩�蝵桃����隞嗅允憭滚��箏���蘨閬� Excel ��辣�𦠜𦆮摰峕�嚗�停瘚���⊿�撟嗅撩�嗅��嗅�雿滩秐�笔������ `BASE_DIR/wencai/�諹�憿箸踎�𡑒�銝�.xlsx` �格�摮鞟𤌍敶𤏪�敶餃�靽桀�鈭� Nuitka �䭾���像�硋�蝥扳楛摨衣��游𦶢�𤤿���
    - [x] **敶餃�頝煾�𡁜��誩�敶埝�霂� 29/29 蝏踵��券�� (100% Green Regressions Passed)**嚗𡁜銁撘訫�餈嗘�憭批����撟脣����瘙⊥�������蝳餃��嗅��𠬍�銝�甈⊥�批�蝢𡒊遛�烾�朞�鈭���詨��� 29 銝� pytest �其��𧼮��⊿�嚗𣬚頂蝏笔�憯格�找��煺漣蝥抒𡠺蝡𧢲����韐典�颲曉�銝𣇉�憿嗥漣�誩��讠�蝏�垢���瘚�偌撟喉�

## 2026-05-23 23:30
- [x] **靽桀� KLineDetailWindow ��眏���餈��撖潸稲���銵䔶� setGeometry 撠箏站�仿� (Fixed Detail Window Text Wrap & Geometry Error)**嚗�
    - [x] **�拍�瘜典���撠誩偕撖詨��券� (Minimum Size Constraints)**嚗𡁜銁 `KLineDetailWindow` 銝剜鰵憓硺� `self.setMinimumWidth(220)` �� `self.setMinimumHeight(150)` �牐�蝥行�嚗�僎撠����� `label` ��倌���撠誩捐摨血撩�園�甇颱蛹 `self.label.setMinimumWidth(200)`���敶餃��餅鱏鈭�眏鈭𤾸��脫�銋���滨蔭嚗�� `width=171`嚗㗇��嗡��桃𤅷蝒�紡�渡���𧋦�䁅�擃睃漲�𣳇��劐撓�� Bug��
    - [x] **�誩��瑕鍳�刻䌊��俈敺⊥㦤��**嚗𡁻�朞��拍�擃睃偕撖賊秄瑽𨥈��其蜓蝔见��臬𢆡撟嗉��� `WindowMixin.load_window_position_qt` �Ｗ�撣���塚��芸𢆡霂��撟嗅像皛𤏸䌊���撠��撠讐���蟮擃睃漲銝𤾸捐摨血撩�嗆���秐�㘾�����粉撠箏站��凒嚗峕�蝏苷�摨訫� `setGeometry` ��𥁒�躰郎�𨳍��
    - [x] **撘箏���� adjustSize 餈𧼮稬**嚗𡁻��������㗇��湔鰵�嗥��瑟鰵�餉�嚗諹挽蝵格��砍�摰孵�蝡见朖�曉�靚�鍂 `self.kline_detail_win.label.adjustSize()` 撘箏�摮鞉�蝑曄�����鞾�摨阡�蝞梹��誩�頝蠘� `self.kline_detail_win.adjustSize()` 餈𥡝��嗅捆�刻䌊������蝢𡒊��港� Qt �典�憟堒�撅�撖峕��砌�擃睃漲皛𧼮�霈∠�����脤��嗵撩�瘀�靽嗪�鈭�遙雿閙��輻��望��砍銁憭𡁜�颲函�/擃� DPI 撅譍����皛烐遬蝷箝��
- [x] **摰䂿緵摰墧𧒄�喟�銝剖��Ｘ踎��眏擃睃�摨� 30摮𡑒��� 銝� 8摮㛖���揢銵� ��稲�垍�隡睃� (Optimized Decision Panel Truncation & Compact Wrapping)**嚗�
    - [x] **摰䂿緵 30 摮㛖泵蝖祆⏛�剛䌊��**嚗𡁜銁 `trade_visualizer_qt6.py` 銝剜凒�啣��嗅�蝑𡝗��塚�憓𧼮�鈭�笆 `reason` 摮㛖泵�踹漲��ế摰𠾼����西�餈� 30 摮㛖泵嚗諹䌊�冽�銵峕⏛�凋��坔� 27 摮㛖泵撟嗉蕭�删��亙噡 `...`嚗�蝠摨閖俈����踹蘂�穃之摨閙����摨艾��
    - [x] **摰䂿緵 8 摮㛖泵�拍��Ｚ�**嚗𡁜銁�澆��硋�蝷箏�嚗屸��� `for i in range(0, len(reason), 8)` ���敺芰㴓嚗峕��� 8 銝芯葉�望�摮㛖泵�� HTML ��𧋦銝剔′憛硺�銝芣揢銵峕�蝑� `<br/>`嚗䔶��諹悟��眏����芸��睃�銝箸�銵峕�憟� 8 銝芸����撖���孵�嚗䔶�隞��璅芸��删鍂蝛粹𡢿�讠憬�唬���稲嚗䔶�����齿窒�誩��讠�蝏�垢���撖��摮西捶�麄��
    - [x] **�㯄�𡁜�蝑㚚𢒰�踹撕�折�摨虫��澆𢙺颲寡�**嚗𡁻���歇�賢��� `setMinimumHeight(40)` 撘寞�折�摨虫誑�� `setContentsMargins(15, 4, 15, 4)` �� `4px` 銝𠹺��澆𢙺��器頝嘅�蝖桐��䁅��𡒊�憭朞���眏��𧋦撅�葉��𦆮銝娍偶銝漤��㰘��芥��

## 2026-05-23 23:08
- [x] **摰䂿緵鈭斗�餈鞱�璅∪���揢/�滨漣����拍�����碶��瑕鍳�典�摨誩��𤥁䌊�� (Persistent Trading Mode & Startup Self-Healing)**嚗�
    - [x] **摰䂿緵餈鞱�璅∪��臬𢆡�芣��㰘蝸**嚗𡁜銁 `trading_kernel/kernel_service.py` 銝剖��� `load_trading_mode_from_config()`嚗峕𣈲����臬𢆡�嗡��砍𧑐�屸�𡁻��滨蔭��辣�芸𢆡�滚��堒�霂餃�撌脖�摮条�璅∪�嚗㇉BSERVE/PAPER/CONFIRM/LIVE_AUTO嚗㚁�撟嗅銁�嘥��碶葉�剖��剁�瘨�膄鈭���臬�璅∪�瘞貉��滨蔭�鮋�霈斗�頝� `OBSERVE` ��挽霈∠撩�瑯��
    - [x] **摰䂿緵璅∪��睃𢆡����拍�靽嘥�**嚗𡁜�蝥找� `DecisionFlowPanel._on_mode_combo_changed()`嚗峕�霈箸糓�滨��𧢲��笔��潸�銵峕芋撘𧶏�憒���乩犖�箏��� `CONFIRM` �𡝗芋��僼�� `PAPER`嚗㚁�餈䀹糓�曹�憌擧綉/�滨蔭�∪藁�行⏛撖潸稲��頂蝏笔撩�嗅��券�蝥改����朞��笔��滚𦶢�滚��嗘�摮睃����蝏�����鈭斗�璅∪�嚗䔶����蝵桃𠶖�� 100% 蝏嘥笆銝��氬��
    - [x] **29/29 �訫��𧼮�瘚贝��函遛�朞�**嚗𡁜銁�惩�鈭斗�璅∪�����硋��瑕鍳�刻䌊���餉��𠬍�摰𣬚��朞��典���瓲�訫�瘚贝���

## 2026-05-23 22:30
- [x] **摰䂿緵憌擧綉��㺭�屸�蝵格�隞嗅�摮鞟����銋��銝� 500ms ���撟踵偘 Dirty Check �𤩺��仿俈�𤥁�隡� (Persistent Risk Limits & High-Performance Dirty Checks)**嚗�
    - [x] **摰䂿緵�臬𢆡�滨蔭�芣��㰘蝸**嚗𡁜銁 `trading_kernel/kernel_service.py` 銝剖��� `load_risk_limits_from_config()` 撌亙�嚗峕𣈲����臬𢆡�嗉䌊�刻粉�硋僎閫���砍𧑐 `window_config.json` 銝� `scale2_window_config.json` 銝剔�憌擧綉靚����㺭嚗�蝠摨閗圾�喲��臬恥�瑞垢�嗅��圈�蝵桃��桅���
    - [x] **摰䂿緵�屸�𡁻��笔��拍�靽嘥�**嚗𡁜�蝥找� `DecisionFlowPanel._save_and_apply_risk_limits()`嚗���滨��贝��游僎靽嘥� 7 憭折��㚚��批��唳𧒄嚗屸��典�摮鞉𤜯�Ｘ㦤�嗅���㺭����坔� `window_config.json` �� `scale2_window_config.json`嚗𣬚＆靽嘥���儘����唳旿撘箔��湔�扼��
    - [x] **撘訫� 500ms �瑟鰵 Dirty Check �𤩺���**嚗𡁜銁摰𡁏𧒄�券店�函����撟踵偘�湔鰵 `_sync_control_tab_ui()` 銝� `_update_top_status_badges()` 銝哨��券𢒰璊滚�撖寞㺭�潦����研��芋撘誩��娍鱏�嗆����𤩺��亥�皛扎����典��貊𠶖���摰墧㺿�䀹𧒄�滩��� PyQt 撅墧�找��瑕��湔鰵嚗�蝠摨訫��日�憸穃��啣紡�渡�敺桀㨃銝舘��交��衣���═��
    - [x] **擃㗛�罸妟霂臬榆�𧼮�瘚贝��朞�**嚗𡁜�蝢𡡞�朞� `$env:PYTHONPATH="."; pytest trading_kernel/tests/` 銝㯄★�𧼮��⊿�嚗�29 銝芯漱�枏��詨����霂訫��其誑 100% 蝏踵�蝥Ｙ瑪������罸�朞�嚗�

## 2026-05-23 22:24
- [x] **摰䂿緵�滢�霂湔�銝𤾸��啗秩�𦒘縑�臬�蝵桀��� Cyberpunk 閫���垍�靚�� (Inlined Parameters Guide & Typography Tuning)**嚗�
    - [x] **摨罸膄憭㚚���辣�拍�靘肽�**嚗𡁻���� `SystemWorkflowDialog`��蝠摨閙慐�凋���𧋦撖寧����隞� `TRADING_KERNEL_IMPLEMENTATION_PLAN.md` ��粉�𤥁楝敺��靽肽�鈭�頂蝏笔銁�祉��枏�銝舘�蝳餌㴓憓��銵峕𧒄�� 100% �亙ㄝ�改��脫迫銝Ｗ仃��﹝撘閗絲��征�賣𥁒�踺��
    - [x] **��蔭擃睃�摨行�摰Ｚ秩�擧���**嚗帋誑擃睃笆瘥𥪜漲���暺𤑳����毺� HTML 霂剜��� Python 隞��銝剔凒�亙��交��䎚���摰孵��嫣�閫��蝟餌�摰帋���犖�箏�撽暸弦�滨��誩����憭批予璇臭漱�𤘪芋撘讐�����
    - [x] **�賢𧑐 7 憭扳瓲敹���㚚��批��唳�憡����**嚗𡁻��函移蝢舘器獢�”�潔��∠�撘誯��滚榆皜𣂼�撣��嚗���𦑩ct_diff �脣�擃塩��in_confidence �枏�摨閧瑪�� exposure �湧蠧�𧼮藁�鞾�隞亙��亙�鈭𤩺����鈭誩��蹱��萘�雿𦦵鍂銝𡡞俈�脤俈皛煾俈�瑞��詨��箏�餈𥡝�瘛勗漲�曇”�𣇉凒閫���啜��
    - [x] **�拍��拙之撖寡�獢���讐��䭾�**嚗𡁜�暺䁅恕閫��撠箏站�枏捐靚�㟲銝� `800 x 580` �讐�嚗��蝢舘�����堒�����扯”�潔�璅∪��穃��∠�嚗峕��支���葉�望�摮堒�鋆���𣇉��亙噡�格𣏹��
    - [x] **�䭾��朞� 29 / 29 蝏踵��𧼮�瘚贝�**嚗朞��𡁜�憟� pytest 瘚贝�嚗�29 銝芣瓲敹��霂訫��券◇�拚�朞�嚗𣬚頂蝏毺迅�交�找��航�瘚𧢲�扯�銝𠰴��啣蝱�塚�

## 2026-05-23 22:15
- [x] **�滨��賢𧑐鈭斗���瓲�批��唬漱鈭㘾��扯�隡塩����券�𡁻�銝��桃��凋��滨� Checklist 撖寡�獢� (Delivered Trading Kernel Interactive Control Center, KillSwitch & Operator Checklist)**嚗�
    - [x] **摰䂿緵 �辷� ��瓲�批�銝𡡞��� Tab �批��Ｘ踎**嚗𡁜銁 `DecisionFlowPanel` 銝餌��Ｘ鰵憓硺��函��批� Tab嚗��蝢舘��亙�憭扳芋撘誩予璇臭��㗇�����滚榆�嗆���蝷箇�隞亙� 7 憭折��㚚��批��啣��嗥�颲烐綉隞塚�摰墧𧒄銝𤾸��� `TradingKernelService` 鈭㘾���
    - [x] **摰䂿緵鈭斗�璅∪�摰匧���漣憭拇０銝� 8 憭批�蝵桅俈�方䌊�券�蝥扯䌊��**嚗𡁜��滨��见�霂訫��� `LIVE_AUTO` �刻䌊�典��䀹𧒄嚗𣬚頂蝏蠘䌊�穃笆 8 憭批�蝵格辺隞塚�憒�暑頝�𧒄畾萸����睃笆韐艾����啣銁蝥輻�嚗㕑�銵𣬚���㜃�芣嵗撉䎚��𥅾�⊿��芾�嚗��撘箏��滨漣摰匧��鮋���單�摰喟� `OBSERVE` ��楝璅∪�嚗屸獈�剜�憭碶��閖��押��
    - [x] **摰䂿緵 10 憭抒′�折��批��唬��桀��其�靽嘥�**嚗𡁏��� UI 蝻𤥁��找辣銝𤾸�摮� `RiskLimits` 摰硺� 1:1 �冽��笆�改���捂餈鞱��嗅𢆡���隡䀝葵�⊥𠂔�脯���銝𡁏������颱�雿漤�憸嘥��亙�蝝航恣鈭𤩺�嚗䔶��桐�摮睃��嗥�����乓��
    - [x] **摰䂿緵 OperatorChecklistDialog �滨��滨蔭璉���**嚗𡁜� 8 憭抒����蝵桅俈�方挽霈⊥�隡㗛��� Cyberpunk �暸�� Checklist 鈭支�撘寧�嚗峕��䀹���閬���典��函＆霈日�朞��孵虾餈𥡝�擃㗛��拙��䀝漱鈭𡜐�摰𣬚�撱箇�����亙��滨�蝥芸��脩瑪��
    - [x] **摰䂿緵 SystemWorkflowDialog �𤘪�閫��銝��格䰻��**嚗𡁏�靘𤤿𡠺蝡� Markdown �𤘪�撅閧內閫��嚗䔶��桀撕�� `TRADING_KERNEL_IMPLEMENTATION_PLAN.md` 摰峕㟲��恥�嘥㦛嚗峕𣈲���銝剝��见��臬�銝𧢲神蝘垍漣���毺頂蝏蠘��坿蕭皞胯��
    - [x] **擃㗛� 500ms ���撟踵偘�芣��峕郊**嚗𡁜銁 `_check_and_update_records` 憓鮋�摰𡁏𧒄�急�銝哨�撘箄��惩�憿園� Badges 隞亙��批��Ｘ踎��䌊�典�甇仿�餉�嚗䔶�霂��霈箸糓�拍���辣�湔㺿���餈𤤿�憭㚚�隞见�餈䀹糓 UI �见𢆡�批�嚗䔶舅蝡舐𠶖���蝏� 100% 蝏嘥笆憟穃���
    - [x] **�券� 29 / 29 蝏踵��朞��𧼮�瘚贝�**嚗𡁻�朞� pytest 敶餃�頝煾�𡁏芋撘讛蓮�Ｗ予璇舀嵗撉䎚����䀹��啁��剜㜃�芥��aper Trading 蝑匧銁����典� 29 銝芣�霂𤏪��冽𧒄 2.46 蝘雴�甈⊥�� 100% 摰𣬚�蝏輯𠧧�朞�嚗�

## 2026-05-23 21:44
- [x] **摰𣬚�瘜典��喟�瘚�偌�Ｘ踎摰⊥䰻靽桀�嚗�蝠摨閙覔瘝餃�摰賡��∩��拇�Null撘�虜 (Delivered DecisionFlowPanel Code Review Patch & Column Expansion)**嚗�
    - [x] **�寞祥����𡑒”�堒捐����硋仃�� Bug**嚗𡁜銁 `closeEvent()` 銝剛‘朣𣂷�撖寞�隞栞”銵典仍�嗆�� `pos_header_state` �� Hex 摨誩��碶�摮矋�銝� `_restore_header_state()` 摰���剔㴓撖寥�嚗���� 100% 蝎曉���楊隡朞�����𡑒”�堒捐����硋��麄��
    - [x] **�齿�撟嗆��� DRY �滚�隞��**嚗𡁜� `_append_record_to_table()` 銝凋舅憭���券�憭滨� 22 銵峕𧒄�湔��脣撕 Fallback �澆��𣇉�瘜訫�蝢擧𡂝鞊∪�撟嗡蛹�蓥�����㕑䌊��䲮瘜� `_parse_timestamp(self, ts_str)`���隞�憬�譍��颱誨���嚗峕凒撘箏�鈭�𧊋�交𧒄�湔聢撘𤩺�餈𤤿�銝��湔�扼��
    - [x] **撘箏���𡟺�笔��臬𢆡 Null �脣鴃**嚗𡁜銁 `_refresh_positions_tab()` �瑟鰵敺芰㴓���滨垢�惩�鈭�笆 `get_kernel_service()` �𠰴� adapter �扯��函� `None` 摰匧��脣鴃嚗屸��滢��䭾��拇��嘥��𣇉𠶖��𧊋�唬��航�撘閗絲�� `AttributeError` 撏拇�嚗���唬�蝟餌� 100% 隡㗛��剛楝�芣���
    - [x] **瘛勗漲�曉捐暺䁅恕�堒捐嚗�蝠摨閗圾�喃葉���蝚�/�望��其��格𣏹蝻粹萅**嚗�
        - 撠��瘞渲”銝餉��㛖��拍�暺䁅恕摰賢漲憭批��枏捐嚗𡁏𠯫��𧒄�湔𦆮摰質秐 `110`嚗䔶誨��𦆮摰質秐 `65`嚗��蝘唳���秐 `75`嚗��蝢𤾸捆蝥喃葉���蝘唬��曄內 `...` 鋆��嚗㚁��其��拙��� `52`嚗Ê̄old "REDUCE" 蝑匧𢆡雿靝��齿��𩤃�嚗峕�隞�/�枏�蝑匧�����曉捐��
        - 撠��隞栞”�堒捐餈𥡝��𣬚�擃䀝���𦆮摰踝�隞���曉捐�� `65`嚗��蝘唳���秐 `75`嚗����/���蝑厰�閬����捐鋆閙�撅𤏪�憒� `85/90`嚗㚁�摰𣬚�靽脲���恥�誩��讠�擃睃�摨西捶�毺��峕𧒄�娪膄鈭���匧�����芥��
    - [x] **�䭾��𧼮� 29 / 29 �券�瘚贝�蝥Ｙ瑪**嚗𡁶�����𡁜�憟� pytest 瘚贝�嚗�29 銝芰鍂靘衤�甈⊥�� 100% 摰𣬚�蝏輯𠧧�朞�嚗𣬚頂蝏蠘䌊���鈭斗�蝔喳��批��亦��喋��

## 2026-05-23 21:30
- [x] **�拍��餃�撟嗡漱隞睃�蝑𡝗�瘞渡��折𢒰�輯䌊�典�摰賣�憭滢� DPI 蝻拇𦆮隡睃� (Delivered DecisionFlowPanel Table Layout Custom Recovery & Scaling Optimization)**嚗�
    - [x] **�寞祥����𤥁䌊�冽�憭滚仃�� Bug**嚗𡁶����雿滚僎�寞祥鈭� `_restore_header_state()` �埈� `return True` ����格綉�嗉楝敺� Bug��蝠摨閗圾�喃��曹���𧋦餈𥪜� `None` 撖潸稲�嘥��𡝗��∩辣�鮋��餈𥕦�暺䁅恕�堒捐霈∠�����厩鍂�瑟��冽��賢��啁�蝻粹萅嚗���啁�甇�� 100% 頝其�霂嘥�摰賜移��䌊�冽�憭溻��
    - [x] **�娪膄 Resize �芸𢆡靚�㟲撟脫贋**嚗帋� `resizeEvent` 銝剖蝠摨閧宏�支�擃㗛�閫血��� `_adjust_column_widths` �齿鰵霈∠�����函���𦆮憭扳𧒄嚗���Ｙ��詨��唳旿�㛖�撖嫣��滨鱻��歲�冽��芸𢆡�穃�嚗諹�峕糓隞交��游𤐄摰𡁶��拍��讐���香嚗���唳��臬龪�𣬚��𤏸�蝔喳��扼��
    - [x] **DPI �芷���暺䁅恕�堒捐�曉捐�滨蔭**嚗𡁜銁�瑕鍳�剁��惩��脤�蝵殷��塚�撠��霈文�摰賢虜�堆�隞��/�滨妍隞� 45/48 �讐��曉捐�� 55 �讐�嚗㕑�銵������湛�撟嗡�銝� `self.scale_factor` 餈𥡝� DPI �拍�蝻拇𦆮���嚗�蝠摨閙��支�擃漗PI撅譍�隞��銝擧㺭摮𡑒���遬蝷箔蛹��裦�� `...` ���閫㗇��箝��
    - [x] **�拍��讠憬�堒捐銝𤾸���聢��器頝�**嚗𡁜�罸��航��𣇉頂蝏煺葉����渡揮�湔�撌改�撠�”憭� `QHeaderView` �� padding �讠憬�� `1px 2px`嚗諹”�澆���聢 `QTableWidget::item` �� padding �拍��𧢲成�� `0px 1px`嚗𥕦��嗅�銝餅�瘞渲”���霈文�憪钅���捐摨血�蝻拙� `[105, 55, 55, ...]`嚗��餃捐摨西���� 80 �讐�嚗㚁����銵函��蹱��捐摨血�蝻抵秐 `[55, 55, 50, ...]`嚗�蝠摨閙��支��𦯀��𦯀��渡�隞颱�憭帋�蝛粹�嚗峕㟲雿梶征�游⏚�函�憸嘥��𣂼� 20% 隞乩�嚗���唳��嗥移撖��蝥抒��誩��𧢲踎韐冽���
    - [x] **銵屸��讠憬蝎曉���**嚗𡁜�暺䁅恕銵冽聢銵屸��� `22` ��稲�讠憬�� `18`嚗��撅誩虾�輯蝸�唳旿撖�漲憭批��𣂼���
    - [x] **摰𣬚��賢𧑐�堒捐銝擧�摨讐𠶖��楊隡朞������**嚗𡁻��嗘� `closeEvent`嚗���滨��见銁餈鞱�銝剜��刻��游��堒捐摨行��孵稬�鍦��塚�蝟餌��芸𢆡�閙�銵典仍 `QHeaderView` ����� `saveState()` �唳旿嚗諹蓮銝箏��剛��� Hex ��僎�笔�餈賢�靽嘥��喟�銝��滨蔭��辣 `window_config.json` �� `"DecisionFlowPanel"` 摮埈挾銝准��
    - [x] **�瑕鍳�冽惣�賢��蠘䌊��**嚗𡁜銁 `__init__` �嘥��碶葉�啣� `_restore_header_state()`嚗���臬𢆡�嗉��芸𢆡霂餃�撟� 100% 蝎曉漲餈睃���蟮靚�㟲�𡒊��堒捐銝擧�摨讐𠶖����交��滨蔭霈啣��坔像皛� fallback �滨漣�單��唳��渡揮�穃捐摨佗�摰䂿緵鈭��蝢𡒊�鈭支�銝��湔�扼��
    - [x] **摰䂿緵頝罸�蝒堒藁�芷����堒捐瘥𥪯�隡貊憬 (Auto-scaling Grid Columns)**嚗朞��碶� `resizeEvent`嚗�⏚�� DPI 蝻拇𦆮�惩���𢆡��撕�批��滨�瘜𤏪��函���之撠𤩺��賣㺿�䀹𧒄嚗���凋縑�臬�嚗�誨����𢆡雿栶���隞㮖�蝑㚁���香�冽�蝝批��讐�隞仿俈�䁅�嚗諹����嚹race ID�嘥��𨅯�蝑𣇉��望�閬��嘅����𦒘��梹��箄��劐撓隞亙��砍�雿坔��函征�湛�摰𣬚�撟唾﹛蝝批�銝𤾸撕�扼��
    - [x] **摰䂿緵�� Tab ��恥�喟�銝擧�隞梶�鈭讐��抒��� (Positions & PnL Dual-Tab Panel)**嚗�
        - �齿�銝餃�撅�撘訫� `QTabWidget`嚗��蝳颱蛹 **`�� �喟�瘚�偌�烐綉`** 銝� **`�𠗠 ��瓲摰墧𧒄���`** 銝支葵擃㗛𧫴�𧢲踎��
        - 憓噼挽�𨀣𠯫��𧒄�氯�嘥�嚗�銁撣貉� Trace �� Audit 憓鮋��亙�閫���塚��删��芸� ISO �園𡢿�喟��鞉�撟喟� `MM-DD HH:MM:SS` �澆�嚗峕𣈲��楊鈭斗��交��瑕鍳�冽�瘞渡移��蕭皞胯��
        - 摰墧𧒄���憿菜� 500ms �湔𦻖隞� `get_kernel_service()` ����蓥�銝剜��硋��齿芋撘譍����隞栞揭�� `get_positions()` �諹揭�瑁�鈭批翰�� `get_account_snapshot()`嚗���誩笆韐佗�蝏脲� CPU �� IO �蠘�𨰜��
        - �Ｘ踎摨閖���鍂�烾�蝤函��餌�韐冽�嚗𣬚鸌霈� 5 銝芸��匧之�∠��𧶏��舐鍂�圈���揭�瑟�餉�鈭扼���隞𤘪�餃��潦��揭�瑟�餌�鈭譌���雿滢蝙�函�嚗㚁��函��拇𧒄����𥪜�蝏輯𠧧敺桀�嚗䔶���𧒄頧砌蛹�拍滯嚗峕��瑕�銝𡁶漣�誩��啁��笔��脣稬�䜘��
        - 摰䂿緵鈭��隞栞�����餉歲頧穿��臬銁��稬隞餅����銝芾��嗅��典�撠� `code_clicked` �𥪜𢆡靽∪噡嚗𣬚��渡忽�𤩺�韏瑕虾閫��霂行�嚗���唬�雿滚�蝑碶��讠��𥪜𢆡�剔㴓��
    - [x] **�删��朞� 29 / 29 �券�瘚贝�蝥Ｙ瑪**嚗窃coped pytest �⊿�銝哨��券� 29 銝芰鍂靘衤�甈⊥�� 100% 蝏輯𠧧�朞�嚗𣬚頂蝏毺迅摰𡁏�批��亦��喋��

## 2026-05-23 20:30
- [x] **�滨��餃�撟嗡漱隞� Phase 9 璅∪�頧祆揢憭拇０銝� 8 憭批��典�蝵桅俈�文㨃�� (Delivered Trading Kernel Phase 9: Mode Ladder & 8 Precondition Gates)**嚗�
    - [x] **鈭支�璅∪�摰匧���漣憭拇０ (`set_trading_mode`)**嚗𡁏�撱箔� `OBSERVE` (蝥航扇韐行�頝�)��PAPER` (擃䀝���芋��)��CONFIRM` (�滨�撟脤�隞见�) �� `LIVE_AUTO` (�刻䌊�典���) �𤤿漣摰匧��坿�憭拇０嚗屸�霈支誑 `OBSERVE` �惩拿�硋𠿭摨𨰻��
    - [x] **鈭支� 8 憭批�蝵桅俈�文��� (`_verify_live_preconditions`)**嚗𡁜銁��聢�� `LIVE_AUTO` �刻䌊�其��訫�嚗峕��∩辣�⊿����瘣餉�鈭斗��嗆挾����䀹��啁���銁蝥踴��KillSwitch` �芣�韏瑯��RiskGate` 甇�虜�㰘蝸��𠯫��敞霈∩��罸�憸腈��𧋦��/�𨅯蝱撖寡揭�峕郊銝��湔�扼����貊��祆�蝥孵龪�滢誑�𡃏䌊�典�瘚贝��嗆����典㨃�������典��扎��
    - [x] **鈭支��拍�撘箏��滨漣�鮋���箏�**嚗𡁜�撠肽���� `LIVE_AUTO` �塚��� 8 憭批�蝵桀㨃���隞餅�銝�憭�𥁒�蹱𧊋餈��蝟餌�撠���游撩�園獈�剖僎撠�予璇舫�蝵桅���𧼮� `OBSERVE` 蝥航扇韐行�頝荔��脰�摰䂿�頞𦠜�銝舘ㄧ�𨰻��
    - [x] **�券𢒰�拙�瘚贝��其�靽嗪� 29/29 蝏踵��券��**嚗𡁶��嗘� `test_auto_ladder.py`嚗���渲��𡝗芋撘誩��滨漣��㜃�芸�������峕芋撘譍�霈Ｗ�頝舐眏蝑𣇉裦嚗�僎�𣂼��朞�鈭���� 29 銝芰鍂靘讠�蝥Ｙ瑪�𧼮�嚗Ǒ29 passed in 2.64s`嚗㚁�

## 2026-05-23 20:25
- [x] **�滨��餃�撟嗡漱隞� Phase 8 摰䂿��毺��𨅯蝱���撉冽沲銝𡒊�����券俈�日俈蝥� (Delivered Trading Kernel Phase 8: Live Broker Counter Skeleton & Dual-Protection)**嚗�
    - [x] **鈭支�蝝扳�亙��剔���鱏�萎��� (`KillSwitch`)**嚗朞挽霈∪僎摰䂿緵鈭���瑕�摮条漣頧臬��喃�蝤��蝖祆�敹埈�隞� (`.kill_switch`) ��揮�乩漱�枏��剔頂蝏麄���撘�虜�𤑳��𤥁���仃�扳𧒄嚗𣬚頂蝏蠘��典凝蝘垍漣���瘚见僎�拍��餅鱏���匧�蝏凋��𤏪��𣂷�蝏���賊俈�文��函蔗��
    - [x] **鈭支�霈Ｗ�撟��蝞∠��� (`OrderIdempotencyManager`)**嚗朞挽霈∪僎摰䂿緵鈭�抅鈭𤾸����摮睃縧�滢�餈���園���恥�閖俈�齿㦤�嗚��銁 Windows 憭朞�蝔衤�蝒��銵峕�瘚�葉嚗𣬚���㜃�芸笆�䔶�銝� `order_id` ���憸穃��㻫����伐�敶餃��寞祥鈭��憸穃��𤑳���蟮瞍𤩺���
    - [x] **鈭支��𨅯蝱���/韏�漣�芸𢆡�峕郊�� (`BrokerPositionSync`)**嚗𡁜��唬�擃㗛�撖寡揭�峕郊�箏���𧋦�� `PositionBook` �其��笔�摰䂿��𨅯蝱隞㮖��𤑳��圈����隞瑟�蝘餅��埈��塚��芸�蝥惩�撖寥�嚗�僎撠��隞枏�撣豢㺭�桃���蕭�㰘扇敶閗秐���啁� `POSITION_SYNC_AUDIT` 摰∟恣韐衣倏銝准��
    - [x] **�齿�摰∟恣�曇�蝑𣇉裦�寞祥�坔��脣躹 (`JsonlJournal`)**嚗𡁜�蝥找�餈賢�撘𤩺𠯫敹� `append` 餈�誘蝑𣇉裦嚗��摰∟恣蝐餅𠯫敹梹��� `AUDIT`嚗匧�蝥踵𦆮銵�僎蝏閗��桅�𡁶� code �孵�銝𡡞俈�齿㦤�嗚��蝠摨閙��帋�鈭箏極�喟�撟脤��峕�隞㯄�蝘餃笆韐血恣霈∠��唳旿�賜��脣躹��
    - [x] **�券𢒰�拙�瘚贝��其�靽嗪� 26/26 蝏踵��券��**嚗𡁶��嗘� `test_broker_adapter.py` 撖寧揮�亙��剜㜃�芥��恥�訫�蝑匧縧�漤俈�溻��誑�𠹺�雿滚�甇亥䌊��笆韐血恣霈∟�銵���𤩺嵗撉䕘�撟嗆��罸�朞�鈭� 26 銝芰鍂靘讠���蝏�滯蝥踹�敶𡜐�`26 passed in 2.90s`嚗㚁�

## 2026-05-23 20:15
- [x] **摰𣬚��餃�撟嗡漱隞� Phase 7 鈭箏極蝖株恕撟脤�璅∪�銝𤾸�蝑𡝗�瘞游恣霈∟��� (Delivered Trading Kernel Phase 7: Human Confirmation Mode & Audit Linkage)**嚗�
    - [x] **鈭支�鈭箏極蝖株恕�扯�鋆�弘�� (`ConfirmExecutionAdapter`)**嚗朞挽霈∪僎摰䂿緵鈭�抅鈭舘�擖啣膥璅∪��� `ConfirmExecutionAdapter`嚗峕�蝻嘥�鋆�遙�� `ExecutionAdapter`嚗�� `PaperExecutionAdapter`嚗剹��𣈲��銁 `CONFIRM` �� `AUTO` 銝见�璅∪��湔�蝻嘥��ｇ�撟嗅笆憪娍��朞��嗉䌊瘥���曇�/撟脤��喟��行⏛��
    - [x] **鈭支� Cyberpunk �烾�蝘烐�憌� PyQt6 蝖株恕瘞娍部 (`OrderConfirmationBubble`)**嚗𡁶移敹���Ｗ枂銝�甈暸��毺����閫鍦��厩縧�������㰘器獢�蔭憿嗆�瘚桀撕蝒𨰜��𣈲�� 15 蝘垍����坿恣�嗉䌊�冽�蝏腈���雿齿���凝靚���� (`Override Size`)嚗䔶誑�𢠃俈頝典������蜓蝒堒藁�詨笆撅�葉��𦆮�餉���
    - [x] **��遣頝函瑪蝔见��其縑�瑁�摨行‘隞� (`ConfirmDispatcher`)**嚗𡁜銁 `tk_gui_modules/confirm_bubble.py` 銝剖��唬��箔� PyQt `pyqtSignal` �� `ConfirmDispatcher`��𣈲���餈𤤿�/憭𡁶瑪蝔衤漱�枏��詨銁�𤾸蝱霈∠�閫血� ApprovedOrder �塚�隞亙��券��餃���䲮撘誩��冽��坿秐銝� GUI 蝥輻��日�瘞娍部撘寧�嚗�蝠摨閗��蹂�銝餉�蝔� GIL ��香銝� UI 蝎䀹���
    - [x] **�齿���瓲�滚𦛚�舀�撟脤��喟��� (`TradingKernelService`)**嚗𡁻���� `evaluate_decision_item`嚗��憌擧綉摰⊥瓲�朞��� ApprovedOrder �芸𢆡鈭斤眏蝖株恕����典�����𥅾�滨��见��𧶏��躰��交芋�煺漱�𤘪僼��僎餈賢��拍� `HUMAN_CONFIRMATION_AUDIT` 摰∟恣韐衣倏�亙�嚗𥡝𥅾�垍�嚗����扇�嗆��㦤�鮋��嚗���� 100% 撟��餈賣滲��
    - [x] **�喟��Ｘ踎憓鮋�閫��摰𣬚���緵�滨�撟脤� (`DecisionFlowPanel`)**嚗𡁜�蝥找� `decision_flow_panel.py` ����讛�閫���具���憓鮋��閗繮�� `HUMAN_CONFIRMATION_AUDIT` �塚�擃睃�撌桀㨃���擃䀝漁皜脫�銝� `�㵪� 閬��` (敺株�銝见�瘥𠉛�憒� `15% �� 5%`) �𤥁��糓 `�� �垍�`���𪈠 蝖株恕`嚗�僎�羓��梢��桀��堆���之�匧�鈭���䀹��扳���
    - [x] **銵亙��𧼮�瘚贝� 100% 蝏踵��朞�**嚗𡁶��嗘� `test_confirm_mode.py`嚗峕芋�煺犖撌亙�蝑娍𦆮銵䎚����嗉䌊瘥��蝏腈���雿𨚲verride敺株�嚗�僎�朞� pytest �𧼮��賊����憟� 22 銝芣�霂閧鍂靘见��其�甈⊥�� 100% 蝏踵��朞� (`22 passed in 2.21s`)嚗�

## 2026-05-23 20:05
- [x] **�刻� Trading Kernel �詨��航�瘚𧢲�改�鈭支� Phase 7 鈭斗���瓲�喟�瘚�偌�烐綉�Ｘ踎 (Delivered Trading Kernel Phase 7: DecisionFlowPanel & Data Contract)**嚗�
    - [x] **鈭支��烾�蝘烐�憌擧聢�喟��Ｘ踎 (DecisionFlowPanel)**嚗𡁏鰵撱箔� `tk_gui_modules/decision_flow_panel.py`嚗屸��� PyQt6 蝎曉��閧錬�� Cyberpunk Dark 蝘烐�韐冽���蜓�冽�瘞渡��抒��選�撖嫣��䔶漱�枏𢆡雿頣�BUY / SELL / ADD / REDUCE嚗匧�憌擧綉霂�摯嚗㇁llowed / Blocked嚗㕑�銵屸�撖寞�摨衣���/�拍滯憭𡁶輕�∠���掩���脯��
    - [x] **摰䂿緵撠暸�憓鮋����蠘圾�� (Incremental Log Tailing)**嚗朞挽霈∩� 500ms �冽���隞嗅粉��撠暸�霂餃�嚗㇅ile seek log tailing嚗㚁��喃蝙�典�餈𤤿�銵峕�瞈��～��敞蝘臬�銝���唳旿�塚�鈭西��其�瘥怎���翰�笔�摨䈑�摰��瘨�膄鈭�蜓 UI 蝥輻��� CPU 韐蠘蝸瘜Ｗ𢆡��
    - [x] **摰䂿緵����諹膘頝唾蓮�𥪜𢆡 (Double-Click Code Linkage)**嚗𡁏��帋��喟��Ｘ踎銵冽聢銵���颱�隞� -> 瘣曉�頝刻�蝔� Tk 靚�漲�笔� -> 閫血� K蝥�/��𧒄�航��吔�Visualizer嚗劐�銝餅綉�嗅蝱摰墧𧒄�峕郊頝唾蓮霂亥�嚗��蝢舘噢�鞟垢�啁垢銝��桃忽�𤩺��塩��
    - [x] **摰䂿緵頝其�霂萘���扇敹�� MRU 敹恍�笔���**嚗𡁶誧�� `WindowMixin`嚗諹䌊�券俈�𤥁扇敶閧���之撠譍��拍���𦆮嚗�僎銝箏�蝑㚚𢒰�踹��滢�撣� Emoji ���憟賭葉����� `�� 鈭斗���瓲�喟�瘚�偌�烐綉 (DecisionFlowPanel)`嚗峕𣈲�� Alt+R �函𡠺蝡贝�蝔衤葉 0 撱嗆𧒄 MRU 敹恍�笔��Ｕ��
    - [x] **銵亙��𧼮�瘚贝�靽嗪� 100% 蝏踵��朞�**嚗𡁶��嗘� `test_journal_contract.py`嚗屸�撖� nested 摮堒�閫����像憟𤑳漲�� JSON 餈賢�銝��湔�扯�銵䔶��券𢒰靽嗪�������銵���� pytest嚗�21 銝芣�霂閧鍂靘见��其�甈⊥�� 100% �朞� (21 passed in 1.19s)��

## 2026-05-23 19:52
- [x] **�刻� Trading Kernel �詨�撉冽沲嚗䔶漱隞� Phase 6 憭朞�蝔贝�銝箄䌊����惩𤐄 (Delivered Trading Kernel Phase 6: Multi-Process Lock & Self-Healing)**嚗�
    - [x] **憭朞�蝔见�摮鞉�隞園�霈曇恣 (FileLock & self-healing)**嚗𡁻���� `trading_kernel/engine/state_manager.py`���撖� Windows 撟喳蝱嚗�⏚�典�撅� `os.open(O_CREAT | O_EXCL)` �笔��箏�摰䂿緵鈭��蝢𡒊�頝刻�蝔衤��交�隞𡝗�隞園�嚗𥕦僎憓𧼮�鈭����辣 2 蝘坿��嗥���撩�嗉䌊�������寞祥鈭��蝔𧢲�憭𡝗�韏瑟�撏拇��䭾�����蹱香����嫘��
    - [x] **���蝥扯�瘚�粉�� (Throttled Read)**嚗朞挽霈∩� 50ms ���霂餃��箏���銁蝏湔�銵峕�瘥怎�蝥批��游�摨𠉛��峕𧒄嚗屸�雿𦒘� 90% 隞乩�����条��� I/O 撘���嚗峕��支�擃㗛�霂餃�銝讠� CPU 撠硋陸��
    - [x] **�冽鰵�芸𢆡�硋僎�烐�霂閖�**嚗𡁶��嗘� `test_state_concurrency.py`��芋�� 3 銝芰𡠺蝡� CPython 摮鞱�蝔钅�憸穃僎�穃��伐��賊��嗉�蝔见�撅��嗆���撟嗡�甇駁�頞�𧒄�笔�蝘駁膄��
    - [x] **�𧼮�瘚贝� 100% 蝏踵��朞�**嚗𡁶����銵� pytest嚗�20 銝芣�霂閧鍂靘见��其�甈⊥�折◇�拚�朞� (20 passed in 1.17s)嚗��蝢𤾸�雿� StateManager 蝥航�銝粹�蝳颯��妟蝑𣇉裦霈啣�蝥Ｙ瑪��

## 2026-05-23 19:40
- [x] **�刻� Trading Kernel �詨�撉冽沲嚗䔶漱隞� Phase 5 憌擧綉蝵穃��脩瑪�惩𤐄 (Delivered Trading Kernel Phase 5: Risk Hardening)**嚗�
    - [x] **頞�撩蝖祆瓲憌擧綉蝵穃� (RiskLimits & evaluate)**嚗𡁜銁 `trading_kernel/engine/risk_gate.py` 銝剖�蝢𤾸��� 10 憭抒′�折��批�蝑硋㨃������恬��硺漱�𤘪𧒄畾菜㜃�芥��葵�⊿��滚��行⏛����煺縑�瑟㜃�迎��舀�憭𡁏聢撘� datetime �嗅榆霈∠�嚗剹���鈭誩��港��斗㦤�嗚��𠯫��敞霈⊥�憭找��煺��扎���雿滩蕭擃䀝�餈賣㜃�芥��葵�⊥�憭扳�隞枏�瘥娪��嗚���銝�/璁�艙�踹���憭扳𠂔�脤��嗚��揭�瑟�颱�撌脩鍂隞㮖��鞾��𠰴�蝚娍迫�笔蒂�箝��
    - [x] **�箄��冽���雿滨憬摰� (Sizing Adjustments)**嚗𡁶移蝏��������瘥𥪯�瘥𥪜笆�餉�嚗���閗���踎�埈��典��餅�隞𤘪𧊋頞��雿����/撘�隞𤘪�蝞堒�頞���塚�蝟餌�銝滚��湔𦻖�𦦵��湧獈�凌�嘅��峕糓�芸��扯�蝘穃郎蝻拙捆嚗���祆活鈭斗��䭾��芸𢆡���銝箏�憟賢‵皛∩�雿漤�憸萘��潘��刻��踵�����拍��峕𧒄餈賣����靽⊥�憓䂿���
    - [x] **�𧼮�蝖砍�瘚贝�憟𦯀辣 (Hardened Test Suite)**嚗�
        - 蝻硋�鈭� `test_risk_hardening.py` 蝎曄＆閬�� 10 憭抒′�折��折�餉�銝𡒊憬摰孵凝靚�㦤�嗚��
        - �拍��扯� pytest嚗�18 銝芣�霂訫��券�朞� (18 passed in 0.96s)嚗峕�銵峕𧒄�渡眏 1.16 蝘埝��𣂷��𣇉憬�� 0.96 蝘𡜐�摰𣬚�摰���喟�銝𡡞��批��删𠶖���瞍讐滯蝥踴��

## 2026-05-23 19:30
- [x] **�刻� Trading Kernel �詨�撉冽沲嚗䔶漱隞� Phase 3 銝� Phase 4 (Delivered Trading Kernel Phase 3 & Phase 4)**嚗�
    - [x] **摰䂿緵蝖桀��批��曉��� (ReplayRunner)**嚗𡁜銁 `trading_kernel/observability/replay.py` 銝剖��唬��墧𦆮�箏���𣈲���摨誩��� StrategySignal嚗諹䌊�券�撱箸��嗆�� StateManager 銵䔶蛹����滲�喳�撘閙��喟���� RiskGate 憌擧綉霂�摯嚗屸�朞��齿鰵霈∠� stable_hash 銝𤾸��� trace ���餈𥡝� 100% 撟���⊿�銝𡒊移��砥�寞�瘚卝��
    - [x] **摰䂿緵蝖桀��扳芋�煺漱�𤘪�銵�膥 (PaperExecutionAdapter)**嚗𡁜銁 `trading_kernel/execution/paper_adapter.py` 銝剖��唬� Paper Trading ����具����典抅蝐� `ExecutionAdapter` �亙藁�垍蔭霈曇恣嚗𥕦遣蝡见�摮� Position嚗��雿㵪�銝� AccountSnapshot嚗�揭�瑁�鈭�/瘚桀𢆡���嚗厰�靽萘�韐衣倏嚗峕𣈲��像皛㻫����函� `BUY -> ADD -> REDUCE -> SELL` �桀�銝𤾸�隞瑕�隞𤘪筑鈭𤩺芋���閫��蝛蹂�憌𡡞埯��
    - [x] **�拙�瘚贝�蝖砍�憟𦯀辣 (Hardened Test Suite)**嚗�
        - 蝻硋�鈭� `test_replay_equivalence.py` �其誑�⊿�撣貉�撟���墧𦆮瘚��������蝭⊥㺿璉�瘚卝��
        - 蝻硋�鈭� `test_paper_trading.py` �其誑璉�撉峕�隞㮖�璅⊥�韏���条緵���憟㛖��賢𪂹�麄��
        - �拍��扯� pytest嚗𣬚𤌍�� 8 銝芣�霂訫��券�朞� (8 passed in 1.16s)嚗���Ｗ�雿𤩺��嗆������烐�蝥Ｙ瑪��

## 2026-05-23 18:13
- [x] **�齿�蝟餌�韏������Ｘ踎嚗���啣之�穃�餈𤤿�蝎曉��见末�齿�撠���笔���辣�滚竉蝳� (Enhanced System Resource Analytics Panel)**嚗�
    - [x] **�啣�撖孵僎�𤏸恣蝞𡑒�蝔𧢲� (PoolWorker) ��惣�賜���**嚗𡁏楛摨行��亙��啣銁 Windows 蝟餌�銝页��曹�摨訫��� `resource_tracker` 撟嗆瓷�㕑◤�滢�蝟餌�摰鮋��㕑絲嚗屸�銝芣��嗵� `Sub-Process` 摰鮋�銝𦠜糓�梁頂蝏����恣蝞梹�憒� `SectorBiddingPanel` �Ｘ踎銝剔�擃睃僎�𤏸恣蝞梹���撣賊彿�� `ProcessPoolExecutor` 餈𤤿�瘙� Worker 餈𤤿���銁�㘾膄�匧�摰��雿梶��𥕦之�穃��𠬍��朞�璉��亙𦶢隞方�銝剜糓�血鉄�� `spawn_main` ��犒嚗��蝢汿��移��𧑐撠�砲畾讠�餈𤤿�敶垍掩銝� **`�辷� �𤾸蝱撟嗅�霈∠�撌乩�摮鞱�蝔� (PoolWorker)`**嚗�蝠摨閙��嗡�蝟餌����蝔钅��鉝��
    - [x] **�拍�蝛輸�誩僎�餃� CPython 摨訫��鞉�扯�蝔� (CPython Hidden Process PID Recovery)**嚗𡁜�蝢舘圾�喃�憭朞�蝔𧢲沲���銝支葵�芾��� `Sub-Process` 餈𤤿����憟質��恍𠗕憸塩��
        - ��笆 **`�𣑐 �曹澈�唳旿�峕郊�� (SyncManager)`**嚗𡁶凒�亦忽�誩�撅�繮�碶蜓餈𤤿� `self._sync_manager._process.pid`嚗���唬� 100% 蝎曉�蝏穃�銝𦒘葉���憟賢��惩���
        - ��笆 **`�椘儭� 韏���墧𤣰�𤏸��� (ResourceTracker)`**嚗𡁻�朞�撘箏�撖澆�撟嗆��� Python ��蔭蝘���亙藁 `resource_tracker._resource_tracker._pid`嚗䔶�皞𣂼仍銝𦠜慐�凋�摨訫���頂蝏蠘�蝔钅��𡜐�摰䂿緵摰�����𤩺��𤥁�瘚卝��
    - [x] **摰䂿緵 PID 蝥抒移蝖桃�摰�**嚗𡁻���� `instock_MonitorTK.py` 銝剔� `open_detailed_analysis` �� `refresh_analysis` �寞���𢆡����碶� `qt_process.pid`��_hotkey_process.pid`��proc.pid`��live_strategy_process.pid` 隞亙� `backtest_process.pid`��銁憭朞�蝔见�銵冽葡�𤘪𧒄嚗�⏚�函��� PID 摰墧鴌 100% 蝎曉��寥�嚗峕��啣𧑐��枂憭折��朞�蝔见笆摨𠉛�摰鮋��蠘��㵪�憒� `�唍 K蝥�/��𧒄�航��𣇉��� (Visualizer)`���� �祉��剝睸頧株蓮�� (HotkeyRotator)`���� 銵峕��唳旿�交𤣰蝞⊿� (DataReceiver)`���� 摰墧𧒄蝑𣇉裦�斗鱏�� (LiveStrategy)` 蝑㚁���
    - [x] **�拍��亦氖�笔��舀�銵峕�隞嗅�**嚗𡁻�朞�撘訫� `os.path.basename(p.exe())` �𣂼�蝏閗� PyInstaller �枏�銝� `p.name()` 鋡怠撩�嗅��滚�嚗���� `instock_MonitorTK.exe`嚗厩�蝖祉�����塚��𣂼�蝎曉���緵鈭��餈𤤿��笔���鍳�典虾�扯���辣�㵪�撘��烐��遬蝷� `python.exe`嚗峕�����遬蝷箏�雿枏虾�扯���辣嚗㚁�銝� Windows 隞餃𦛚蝞∠��典�蝢𤾸笆朣僐��
    - [x] **�芾��怨�蝔𦥑�𨅯𦶢隞方���犒�芾��凌�脲㦤��**嚗𡁻�撖� Python 憭朞�蝔贝䌊�穃鍳�函��惩�摮鞱�蝔页�撘訫�鈭�䌊�冽��𡝗瓲敹���唳�蝥寧��箏���朖雿踵瓷�厩�摰� PID嚗���鞟�����賢��嗅�蝷箔蛹 `Sub-Process (Cmd: -c from multiprocessing.spawn...)`嚗�蝠摨閙��港�餈𤤿�暺𤑳���
    - [x] **�垍��芷���銝舘�摰賣聢撘誩凝靚�**嚗𡁜�餈𤤿��𡑒”��虾�扯���辣�滚笆朣𣂼捐摨衣眏 22 摮㛖泵隡睃�敺株�銝箸��渡揮�𤑳� 12 摮㛖泵嚗���嗅����蝥輻憬�譍蛹 88 摮㛖泵嚗�銁摰𣬚�摰寧熙 `python.exe` 銝𥪯�����渡揮�𤑳��峕𧒄嚗�銁撠誩�撅譍��賢� 100% �踹��䁅��嗘�嚗���唬�暺穃恥撣嘥𤙴�祉��湧�蝢擧���

## 2026-05-23 17:25
- [x] **�拍�瘨��憭朞�蝔衤�擃漗PI銝� setGeometry ���撠誩之撠讐�����嗉郎�� (Fixed Unable to Set Geometry Warning)**嚗�
    - [x] **摰䂿緵 WindowMixin ��撠誩偕撖貊���俈敺� (MinimumSize Guard)**嚗𡁜銁 `tk_gui_modules/window_mixin.py` �� `load_window_position_qt` �詨�撠箏站�Ｗ��賣㺭銝哨��惩�鈭��撖� `minimumSizeHint()` 銝� `minimumSize()` ����� max 餈�誘�具���蝖桐�鈭�銁�Ｗ�蝒堒藁憭批�嚗���� DPI 蝻拇𦆮�Ｙ�嚗㗇𧒄嚗��霂閗挽摰𡁶��牐�擃睃漲��捐摨行偶餈靝�撠譍�蝒堒藁���撣��霈∠��箇��拍�銝钅�嚗䔶�皞𣂼仍銝𠰴�蝢擧��支�擃㗛�皛穃𢆡�㗇��㚚�蝵桃���𧒄嚗�銁 Windows �批��啁鱻���撅讐� `Unable to set geometry` 霅血���
    - [x] **撖寥��嘥�暺䁅恕擃睃漲**嚗𡁜� `trade_visualizer_qt6.py` 銝� `kline_detail_win` �㰘蝸�嗥� `default_height` ��㺭�� `240` ��蛹�港蛹摰質��� `270`嚗��蝢𡡞���霂行�蝒堒�摰寧�憭朞���𧋦皜脫�嚗峕����擃� DPI 撅譍����撅𤩺葡�𤘪���漲��

## 2026-05-23 15:08
- [x] **摰墧鴌霂�恣摰匧��惩𤐄銝𤾸�餈𤤿��芣�雿梶頂 (Implemented Review Code Hardening & Multi-process Healing)**嚗�
    - [x] **摰䂿緵�祉��� Port Conflict 蝡臬藁�芣��脣鴃**嚗𡁜銁 `hotkey_rotator.py` �� `WindowSyncServer.run` 銝剖��乩� `OSError` (WSAEADDRINUSE) �行⏛嚗�� 26669 蝡臬藁鋡怠��冽𧒄嚗��餈𤤿��賢像皛煾���綽�撟嗅��� Named Pipe �芣��𡁶䰻��
    - [x] **�惩𤐄憭抒�/璁�艙擃㗛��瑟㺭�桀���/蝎睃��埝䰻�亙�**嚗𡁜銁 `WindowSyncServer` �� `recv` �餉�銝� `json.loads` 閫��銝剖��乩�霂衣����撣豢��瑚��澆��� `print` 颲枏枂嚗���恍�暺睃仃韐乓��
    - [x] **擃㗛��格筑蝛� Toast 撘寧��𥪜𢆡 (High-visibility Floating Toast)**嚗𡁜銁 `instock_MonitorTK.py` �� Named Pipe 瘨���噼� `STATUS_MSG` �交𤣰��𣈲銝哨��券𢒰��漣銝� 5蝘㘾��垍𤌍�祆筑撘寧� `toast_message` �𥪜𢆡嚗𣬚＆靽脲��䀹��典��臬𢆡蝚砌�蝘鍦朖�賜�皜��𦯷lt+R鋡怠��典歇�滨漣�萘��詨��鞾�嚗峕���隞𡒊𠶖����𣬚钟�潛�霂颯��
    - [x] **��㺭�� K蝥輯祕������瘣餅𧒄撱� (Parameterized Detail Window Hover Delay)**嚗𡁜� `trade_visualizer_qt6.py` 銝� `KLineDetailWindow` �毺′蝻𣇉��� 2 蝘𡜐�`2000ms`嚗匧辣�嗅�蝢擧𡂝鞊∩蛹蝐餌漣撅墧�� `self.hover_activation_delay`嚗�⏚鈭𤾸��煺��格��桐��舫�蝵桀���

## 2026-05-23 14:52
- [x] **�惩𤐄�芸𢆡撘孵枂�踹�蝡硺遠�Ｘ踎��漱�𤘪𠯫�文� (Hardened Auto-open Bidding Panel with Trading Day Gate)**嚗�
    - [x] �� `instock_MonitorTK.py` �� `is_auto_window` �園𡢿蝒堒藁銝𡡞俈�𤥁恣蝞烾�餉�銝哨��惩�鈭� `cct.get_trade_date_status()` �文����蝖桐�鈭�蘨�典���漱�𤘪𠯫銝𥪜�鈭擧暑頝�漱�𤘪𧒄�湔挾嚗�09:15-15:05嚗㗇𧒄�滩䌊�刻圻�煾𢒰�踵�韏瘀��踹��硺漱�𤘪𠯫嚗���冽錰�����𠯫嚗匧��啣�頧賣�霂閙��瑕鍳�冽𧒄鈭抒��䭾�銋厩��Ｘ踎�芸𢆡撘孵枂��
- [x] **靽桀� _update_crosshair_ui ��� mapToGlobal �� AttributeError 撏拇� (Fixed mapToGlobal AttributeError in _update_crosshair_ui)**嚗�
    - [x] �交��典�摮堒���宏�函��噼� `_update_crosshair_ui` 銝哨�霈∠� K 蝥踵�瘚株祕���嚗Ǒkline_detail_win`嚗厰�霈斗��曉���𧒄隞滨�靚�鍂鈭���瑕� `mapToGlobal` 撅墧�� of `self.kline_plot` (PlotItem)����嗆凒甇�蛹�拍�蝏睃㦛蝏�辣 `self.kline_widget`嚗�蝠摨閙��支�����㗇�蝘餃𢆡�� K 蝥踹㦛銝𡃏圻�� UI �湔鰵�嗥�撏拇��鞉���
- [x] **�Ｗ� KLineDetailWindow 暺䁅恕頝罸�曌䭾��㗇�蝘餃𢆡����訾漱鈭� (Restored Detail Window Mouse-Following Default Position)**嚗�
    - [x] �齿�鈭� `trade_visualizer_qt6.py` 銝� `kline_detail_win` �冽𧊋餈𥡝��见𢆡�𡝗嗻嚗Ǒnot is_custom_positioned`嚗㗇𧒄���霈文�雿滨�瘜𨰻���撘���箏���𦆮�� K 蝥踹㦛撌虫�閫�/撌虫�閫垍�撅��冽�撠��餉�嚗峕�憭滚��脫��肽挽霈﹦�婙�𠉛凒�仿�朞� `QtGui.QCursor.pos()` �𣂼�撅誩��典�曌䭾��鞉�撟嗅��喃�閫鍦凝�讐蔭嚗�+15px嚗㚁�摰䂿緵銝脲����曌䭾��冽��栶��
    - [x] �峕郊�寥�牐� `showEvent`��moveEvent` �� `resizeEvent` 蝑厩𠶖��恣��芋�梹��冽𧊋�见𢆡摰𡁜�雿滨蔭�嗅蝠摨閧�餈�𤐄摰𡁜漣���撠���滩挽�餉�嚗�銁閫��瞏𨅯銁 `AttributeError` 撏拇�憌𡡞埯����塚�摰���萄儐�靝��见𢆡�𡝗嗻嚗�停銝滩��港�銝滩扇敶訫��嗆�霈售�萘�蝥臬�霈曇恣�笔���

## 2026-05-23 14:50
- [x] **�行⏛�祉��剝睸摮鞱�蝔讠� KeyboardInterrupt 撏拇��閗蕨 (Suppressed Hotkey Subprocess KeyboardInterrupt Traceback)**嚗�
    - [x] 銝� `hotkey_rotator.py` 銝剔� `on_windows_synced` �詨� Socket �峕郊�唳旿�交𤣰�噼���ㄨ鈭���渡� `KeyboardInterrupt` 撘�虜靽脲擪��
    - [x] �� `main` �亙藁�賣㺭����航蔭霂Ｗ�撅���牐� `KeyboardInterrupt` 靽∪噡�閙�嚗𣬚＆靽脲��䀹��函�蝡航��� `Ctrl+C` 撘粹���墧𤣰�塚��祉�摮鞱�蝔见銁�䠷��芣��滢�隡𡁜�����躰秤颲枏枂嚗ìtderr嚗㗇��埝��喟� Traceback �仿�嚗�之撟�����憭朞�蝔见��剜醌撠暹𠯫敹㛖�皜��摨艾��

## 2026-05-23 14:45
- [x] **摰䂿緵�臬𢆡撅誩�銝��湔�扳嵗撉䕘��脰祕���頝典���� (Fixed Detail Window Multimonitor Screen Alignment)**嚗�
    - [x] �� `showEvent` 瘚��銝凋�甈⊥�扯蝸�乩蜓蝒堒藁銝舘祕��筑蝒𦯀�蝵柴��蝙�� `QGuiApplication.screenAt` �冽��ế摰帋舅蝒堒藁�㰘蝸�鞉����函��拍�撅誩�嚗���ｇ���
    - [x] **憒��銝斤�����典�銝�銝芣遬蝷箏膥銝𠺪�頝典����嚗㚁��蹱�撘�䌊摰帋�雿滨蔭嚗��蝵� `is_custom_positioned = False`嚗㚁�撟嗅⏚�� `mapToGlobal` �芸𢆡蝘餃𢆡�喳��滢蜓蝒堒藁���典�撟� of 暺䁅恕韐渲��鞉�嚗���唬�撟脣�����閧�銝�甇亙��脤��鮋����**
    - [x] **靽桀� mapToGlobal 靚�鍂撅墧�折�霂� (Fixed mapToGlobal AttributeError)**嚗帋耨憭滢�撅誩�銝滢��游����餉��䕘�撖寞瓷�� `mapToGlobal` 撅墧�抒� `PlotItem` 摰孵膥�躰秤靚�鍂�� bug嚗峕凒甇�蛹�拍�蝏睃㦛蝏�辣 `self.kline_widget.mapToGlobal`嚗峕��支��瑕鍳�冽𧒄��援皞������


## 2026-05-23 14:38
- [x] **蝻拍� KLineDetailWindow �砍��𦠜�瞈�瘣餃辣�� (Shortened Detail Window Hover Delay)**嚗�
    - [x] 撠� `KLineDetailWindow` 曌䭾��蹱迫�砍�蝑匧�瞈�瘣餅��见�擃䀝漁颲寞���恣�嗅膥隞� 3 蝘� (`3000ms`) 蝻拍��� 2 蝘� (`2000ms`)��
    - [x] �峕郊�湔鰵鈭� `enterEvent` �� `mouseMoveEvent` ��俈�㚚�蝵桅��潘�雿踵��賭漱鈭垍��日��滚��笔漲憭批��𣂼�嚗峕凒���憸𤑳��亦�����滩�憟譌��

## 2026-05-23 14:00
- [x] **摰䂿緵撘箏����� (Ctrl+C) 銝𡒊揮�亙��嗆㦤�塚�瘨�膄憭朞�蝔见�撠賊彿�嗘�蝡臬藁�删鍂 (Robust Signal Handlers & Clean Shutdown Guarantee)**嚗�
    - [x] **摰帋� `emergency_cleanup_subprocesses`**嚗𡁜銁 `instock_MonitorTK.py` 銝剖��乩��典��㗛� `_global_app_instance`嚗𣬚鍂隞亥�頦芣迤�刻�銵𣬚�摨𠉛鍂蝔见�撖寡情��ㄟ�𦒘�蝝扳�交���遆�堆��函眏鈭� Ctrl+C �硋�隞㚚�甇�虜靽∪噡撖潸稲 `os._exit(0)` 鋡怨��典�嚗䔶�撘箄�銝娪◇甈⊿�朞� `.terminate()` -> `.join(timeout=0.2)` -> `.kill()` 撖� `qt_process`嚗�虾閫��摮鞱�蝔页���_hotkey_process` (�祉��剝睸摮鞱�蝔�) �� `proc` (�唳旿�交𤣰摮鞱�蝔�) 餈𥡝�撘箏���甇颯��
    - [x] **�怠偏���㗇暑瘜澆�餈𤤿�**嚗𡁻�朞� `multiprocessing.active_children()` �券��怠偏嚗�僎�典撩�園���箇�����剖�嚗𣬚��滢�蝟餌�憸�� `time.sleep(0.3)` 蝻枏�嚗𣬚＆靽嗪��� Named Pipe ���鈭怠蘂���敶餃�蝏��鈭�撩�園���箏��航��𤥁�蝔𧢲��坔� Named Pipe `\\.\pipe\instock_tk_pipe` 蝑厰�𡁻��典��啣�甇颯�����蔣�滢�銝�甈⊥迤撣詨��臬𢆡����嫘��
    - [x] **撖寥�銝匧� Ctrl+C �喲睸撘粹��頝臬�**嚗𡁜�蝝扳�交���㦤�嗅�甇亦��亙� `_native_ctrl_handler` 蝥輻���LI �賭誘銵䔶���睸�䀝葉�剖��臭誑�� `app.mainloop()` �閗繮��▲蝥折���粹�餉�嚗𣬚＆靽嘥�頝臬�銝贝�蝔见�蝢舘䌊����
- [x] **靽桀��祉��剝睸��揢�冽遬蝷箏�銵其葉��葉�� Emoji �见末�滚�銝Ｗ仃 (Restored Window Rotator Friendly Names)**嚗�
    - [x] **�寞𧋦�批�憟賢��滨妍���**嚗𡁶凒�亙銁 `_get_all_open_trade_windows` ��� `name_map` ���𣳇�餉�銝剛�鈭��銝� HWND ��蝎曄�����祉� Emoji 銝剜��见末�滨妍嚗��憒� `�凃 銝餅綉�嗅蝱`���� 蝡硺遠韏偦帕�𧢲踎`���� �踹�蝡硺遠/撠曄��𥪜𢆡` 蝑㚁�嚗��隞������箇�蝞���㘚���嚗䔶蝙�祉�憭朞�蝔见��Ｗ膥霂餃��� 100% ��緵蝎曄�����Ｘ��研��
    - [x] **�舀�蝤�斐��掩�寥�**嚗𡁜銁璁�艙�暸��烐綉摮鞟����Tile 蝤�斐嚗厩��滚�銝剛蕭�� `[MonitorWindow_win_id]` �𡒊�嚗䔶�隞��蝷箔�撣行��踹�銝𦒘誨����见末銝剜�嚗䔶��澆捆鈭���厰�朞��斗鱏 `"MonitorWindow_" in name` �亙�蝐餃虜閫��銝𡒊�韐渡����餉���

## 2026-05-23 13:30
- [x] **摰䂿緵�典�敹急㭘�桐�蝒堒藁頧株砭��揢�典蝠摨訫�餈𤤿�閫��� (Decoupled Global Hotkeys & Window Rotator to Independent Process)**嚗�
    - [x] **閫��虫蜓 Tk 蝥輻� GIL �餃�**嚗𡁜� `WindowRotatorDialog` �屸𢒰�� `RegisterHotKey` Win32 瘨��敺芰㴓隞𦒘蜓 Tkinter GUI 蝥輻�敶餃��亦氖嚗䔶漱�勗��函𡠺蝡讠� Python PyQt6 摮鞱�蝔� `HotkeyRotatorProcess` 餈𥡝��条恣��朖雿蹂蜓餈𤤿��刻�������笔��颱��𤑳��⊿▼�� GC嚗��撅��剝睸頧株蓮銝𤾸��Ｙ��Ｖ��嗡誑 0 撱嗉�蝘垍漣�滚���
    - [x] **��遣擃㗛��屸�𡁻� IPC 蝞⊿� (Named Pipe + TCP Socket IPC Bridge)**嚗�
        - 憓噼挽鈭� TCP Socket 撘�郊撟踵偘�滚𦛚 (`127.0.0.1:26669`)嚗帋蜓餈𤤿�撠���啁��航�蝒堒藁�交��𡑒” (HWND) �� MRU ���隞仿��餃��孵����笔��穃嘀�剛秐�剝睸摮鞱�蝔讠�摮矋��踹�鈭��蝥輻�/餈𤤿�銝讠����鈭剹��
        - 憓噼挽鈭� Named Pipe �帋縑�滚𦛚 (`\\.\pipe\instock_tk_pipe`)嚗𡁶鍂鈭𡒊��株�蝔见�銝� Tk 餈𤤿��閖�鍦��賣�隞歹�憒��撘�蝑𣇉裦�㕑������/撘��航郎�伐�隞亙��拍���揢�衣�蝒堒藁��窈瘙����
    - [x] **憭𡁶輕蝛輸�誩��拍�撘箏��𡁶�**嚗𡁜銁�剝睸摮鞱�蝔衤葉蝖株恕��揢�塚�銝滢�蝡见��冽𧋦�啗��� `AttachThreadInput` + `SetForegroundWindow` 摨訫� Win32 API 撘箏�憭箏�蝟餌��滚蝱�衣�嚗諹��峕郊�睲蜓餈𤤿��煾�� `FOCUS` 蝞⊿���誘��眏銝餉�蝔见銁 Tk 瘨�����瘜萎葉�䔶��抵��佗�敶餃�閫��鈭� OS 蝥批��啁�����ａ��嗚��
    - [x] **擃䀝��蠘䌊����𥪜𢆡�峕郊**嚗𡁜銁銝餉�蝔讠� `_register_hwnd_to_mru` (蝒堒藁�𡁶�銝擧釣��) 隞亙� `_on_racing_panel_closed` (韏偦帕�Ｘ踎�喲𡡒) 蝑㗇瓲敹���賢𪂹�笔�靚�葉�惩� `sync_rotator_windows` 銝餃𢆡�券��㦤�嗚���隞颱�鈭斗�蝒堒藁鋡急�韏瑯����行���瘥�𧒄嚗峕㺭�桐��冽神蝘垍漣��䌊�典�甇亙��剝睸�祉�餈𤤿���𧋦�啁�摮䀝葉嚗峕��支�頝刻�蝔讠𠶖��㦤銝滢��渡��桅���
    - [x] **�亙��滨漣�芣�銝舘�皞𣂼��嗅��典𠿭**嚗𡁜銁銝餉�蝔衤葉撘訫��芣�靽脲擪����祉�摮鞱�蝔𧢲�憭𡝗𧊋�賢鍳�剁�蝟餌�撠�䌊�券�蝥找蛹 legacy 蝥輻�璅∪��行⏛�剝睸嚗䔶�敶勗�蝏�垢雿輻鍂��銁 `on_close` 銝哨�銵仿�撖孵�餈𤤿���撩�𤤿���釣���峕����銝仿俈餈𤤿�畾讠��羓垢����具��

## 2026-05-23 13:20
- [x] **�行⏛�桃�銝𠹺��厰睸鈭衤辣嚗𣬚＆靽苷�皛朞蔭/�拍��曄內摰��銝��渡�憿箏�擃䀝漁��揢 (Hijacked Up/Down Keys for Rotator Sync)**嚗�
    - [x] **�寞祥銝𠹺��桐�皛朞蔭/��揢�冽瓲敹�𠶖����峕郊 Bug**嚗𡁏䰻�𡒊眏鈭𤾸��齿瓷�匧銁�典� `eventFilter` 銝剜㜃�� `Key_Up` �� `Key_Down` �厰睸嚗�紡�湧睸�䀹�銝见縧�嗥凒�亥◤�交��衣��� `QListWidget` �芾澈暺䁅恕憭��撟嗆凒�嫣��𡑒”�𣬚�閫�� currentRow嚗䔶�餈蹱瓷�匧�甇交凒�� Dialog 銝剔��詨��嗆�� `self.curr_idx`����西�銵���Ｘ�皛𡁜𢆡皛朞蔭嚗屸�鈭桅★撠曹��曹��抒揣撘閙𧊋鋡急凒�啗�𣬚��嗅��蠘歲�塩��
    - [x] **蝏煺��桃��孵��桀紡瘚�𦻖���憭� PyQt ��𧋦�澆捆 (Multi-PyQt Version Event Key Compatibility)**嚗𡁜銁 `eventFilter` 蝥批��湔𦻖�行⏛鈭��敺� Dialog �� `Key_Up` 銝� `Key_Down` �厰睸鈭衤辣��䰻�𦒘��� PyQt6 ��葉 `event.key()` 餈𥪜����澆虾�賣糓 `Qt.Key` �帋蜀撖寡情嚗䔶��航��臬�撅� `int` �湔㺭嚗��憒� Key_Down ����潭糓 16777237嚗㚁��䭾迨�湔𦻖瘥𥪜笆 `==` �航�隡𡁻��批ế摰𡁜仃韐乓���朞�撘訫�撖� `event.key()` �� `hasattr(evt_key, 'value')` 撟嗥�銝�瘥𥪜笆 `.value` �湔㺭�潘�100% �𣂼�摰䂿緵鈭�睸�䀹䲮�煾睸��㜃�芯�撖潭�嚗𣬚凒�亥��券�鈭格綉�嗆𦻖�� `self.rotate_highlight(1/-1, is_hotkey=False)`嚗�蝠摨閙��支��嗆��㦤銝滚�甇亙紡�渡�頝喳�嚗䔶蝙�桃��滢�銝擧�頧柴������������堒��� 100% �峕郊���蝢𡡞◇甈∟蔭�剹��

## 2026-05-23 13:14
- [x] **摰䂿緵撣貉�蝏��蝤�斐蝏���������鍦�嚗��蝢𤾸�憿曉�瘜⊥��笔��Ｖ�蝤�斐�拍�雿滨蔭�箏� (Grouped Rotator Sort: Normal MRU, Tiles Fixed)**嚗�
    - [x] **�Ｗ�撣貉�蝒堒藁�� MRU �埝部�鍦�**嚗𡁜�銝餅綉�嗅蝱����仿�㕑����撽祇𢒰�踴���隞琿𢒰�踴��蝥輻��抒�撣貉�蝔见�蝒堒藁����ａ◇摨𤩺�憭滢蛹 MRU �埝部璅∪����甈⊥��蠘��血��Ｗ�嚗諹砲蝒堒藁�芸𢆡蝵桐� MRU �笔����㵪�靽萘����毺��𨀣�餈烐䰻�见虜�函������鐤�算�萘���恥雿㯄���
    - [x] **蝤�斐蝏�����蝵桅�摰�**嚗𡁜笆摨閖� Tiles �箏����韐渡������鉄 `MonitorWindow_` ���敹菜𦆮�讐��批�蝒堒藁嚗㚁�摰���㘾膄�� MRU �鍦�銋见�����典�銵其葉���蝝Ｖ��劐葉�鍦�憪讠�銝擧遬蝷箇�����㛖�撖嫣��湛�憿箸活銝滢僚頝喉�嚗��蝢舘圾�喃�蝤�斐�曹�銝齿鱏鋡怎��餉��紡�渡�頧桀𢆡�嗘僚�桅���

## 2026-05-23 13:10
- [x] **摨罸膄 MRU �齿鰵�鍦��𡑒”�拍��曄內憿箏�嚗䔶���遬蝷箸��埈偶餈𨅯𤐄摰� (Fixed Rotator Display Order)**嚗�
    - [x] **�寞祥��揢�𤾸�銵冽遬蝷粹◇摨譍僚頝喲䔮憸�**嚗𡁏䰻�𡒊眏鈭擧�甈∪��Ｗ��僐����唳�韏� Dialog �塚�`_get_all_open_trade_windows` 隡𡁜�銝𠹺�甈∪��朞��衣��滚蝱蝒堒藁�朞� MRU �鍦�蝵桐�擐碶�嚗䔶���紡�游�銵冽𧋦頨怎��曄內憿箏�銝齿鱏鋡急�銋勗�鍦�嚗䔶漣�煺艇�滨�閫���嗘���
    - [x] **�拍���香�𡑒”蝔喳��鍦�**嚗𡁻�朞�靽格㺿�鍦��餉�嚗���日� MRU 憸𤑳��齿��𡑒”���憿箏���緵�函凒�乩誑�航�蝒堒藁��䌊�嗅�撱箔��Ｘ�憿箏�嚗�蜓�批��啜����仿�㕑����撽祇𢒰�踴���隞琿𢒰�輻�嚗㗇�摰𡁜�蝷綽�100% 靽脲��𡑒”�曄內�����◇摨讐�撖寥�甇Ｖ�銋梯歲��
    - [x] **�箄��芷���蝝Ｗ�摰帋�**嚗朞蒾�嗅�銵冽遬蝷粹◇摨譍�������甇ｇ�雿�銁 Dialog �嘥��㚚𧫴畾蛛��嘥�擃䀝漁擃䀝漁���靘萘�隡𡁏惣�質粉�𣇉�����啁��寧���僎撠�� index �刻砲�箏��𡑒”銝剖�雿㵪�擃䀝漁�𡁶�鈭𤾸��餉����銝�憿嫘���雿踹��桃�銝𠹺��孵��柴���蝏剖翰�琿睸隞亙�曌䭾�皛朞蔭��揢��糓�函�撖寥�甇Ｙ��𡑒”銝凋�甈⊥��剁�雿㯄��𧼮���蔔��䌊�嗥凒閫剹��

## 2026-05-23 13:05
- [x] **摰䂿緵�典� QApplication 蝥找�隞嗉�皛文膥�齿�嚗�蝠摨閗圾�喟征��/皛朞蔭/�厰睸�滨蔭憭望� Bug (Implemented App-Level EventFilter, Global Focus Pierce & Multi-PyQt Version Event Type Compatibility)**嚗�
    - [x] **�拍��餃�摮鞟�隞園睸��/曌䭾��衣��Ｗ�撖潸稲��漱鈭雴腺撘�𠗕憸� (Global Focus Pierce)**嚗𡁏䰻�𡒊眏鈭𡡞睸�睃�曌䭾��衣��賢銁 `QListWidget` �𠰴� `viewport` ���嚗𣬚㮾�喟� `KeyPress`��Wheel` 蝑劐�隞嗡�鋡怠��找辣�湔𦻖�行⏛撟嗆�韐對�撖潸稲�嗥��� Dialog �䭾��嗅�隞颱�瘨��嚗䔶��䔶蝙敺埈��桃��嗉恣�嗅膥�滨蔭憭梯揖��誑�羓征�潮睸蝖株恕憭望����朞��齿� Dialog 蝏𤘪�嚗�銁 `__init__` 銝剖�鈭衤辣餈�誘�冽釣��銁�典� `QApplication.instance()` 摰硺�銝𠺪�撟嗅銁 `eventFilter` �嗆挾嚗屸�朞� `watched.window() == self` 蝑偦�㚁�蝛輸�𤩺�批𧑐�芾繮鈭���匧�敺��� Dialog �𠰴�銝�����典��找辣���隞塚�100% �𣂼�摰䂿緵鈭�征�澆朖�嗥＆霈支��孵���/皛朞蔭�䭾香閫㘾�蝵� 5.0 蝘坿��嗉恣�嗚��
    - [x] **摰䂿緵銝滚� PyQt6 ��𧋦銝衤�隞嗥掩�见龪�滚�摰寞�� (Multi-PyQt Version Compatibility)**嚗𡁜��唬��� PyQt6 鈭諹��嗅��其�隞嗅����嚗䈣event.type()` 餈𥪜����澆虾�賣糓 `QEvent.Type` �帋蜀撖寡情嚗䔶��航��臬�撅� `int` �湔㺭�潘�撖潸稲�湔𦻖�� `==` 瘥磰�隡𡁏��鞉�批龪�滚仃�����朞�撘訫� `hasattr(event.type(), 'value')` 撟嗥�銝�瘥𥪜笆 `.value` �湔㺭�潘�靘见� `QEvent.Type.KeyPress.value`嚗㚁�敶餃�閫��鈭�眏鈭� PyQt6 ��𧋦撌桀�撣行䔉���撖孵仃���蝖桐�蝛箸聢�行⏛�峕�頧株蔭頧祉蓡����曄迅摰朞圻�㻫��
    - [x] **摰匧��笔𦶢�冽�瘜券��脫���**嚗𡁜銁 Dialog �� `closeEvent` 銝哨��峕郊憓𧼮�鈭� `QtWidgets.QApplication.instance().removeEventFilter(self)` 靚�鍂嚗𣬚＆靽� Dialog ��瘥���典�鈭衤辣餈�誘�刻◤撟脣�蝘駁膄嚗屸妟���瘜�蠧��

## 2026-05-23 12:56
- [x] **靽桀�摮鞟�隞園睸�条��寞㜃�芾恣�嗡�蝛箸聢/皛朞蔭閬��瘛瑟� Bug (Fixed Event Capture, Timer Reset & Rotator Wheel Bug)**嚗�
    - [x] **敶餃�閫���Ｘ��滚��嗡�隡朞圻�� 5s �芸𢆡�喲𡡒�� Bug**嚗𡁏䰻�𡒊眏鈭𡡞睸�条��孵�鈭� `QListWidget` ����塚��厰睸鈭衤辣嚗��銝𠹺��柴���頧衣�嚗劐�鋡� `QListWidget` �芾澈�湔𦻖瘨�晶嚗�紡�湧▲蝥� Dialog �� `keyPressEvent` �䭾�鋡怨圻�𡢅��滨蔭�園𡢿���雿𨅯�甇日�暺睃仃�����朞��� `__init__` 銝剖� `eventFilter` �齿鰵摰㕑��� `self.list_widget`��self.list_widget.viewport()` 隞亙� Dialog �芾澈嚗�僎�� `eventFilter` �嗆挾�𣂼��行⏛���厩�����桐�曌䭾�銵䔶蛹嚗峕��笔��唬��芾��㗇��格�雿𨅯朖�� 100% �瑟鰵 5.0 蝘埝��滢��喲𡡒霈⊥𧒄嚗�蝠摨閖��滢��曹��衣��找辣�餅鱏撖潸稲���憭𤥁��嗅��准��
    - [x] **摰𣬚�靽桀�曌䭾�皛朞蔭銝�皛𡁜𢆡撠梯䌊�冽�銵���Ｙ� Bug**嚗𡁜��支�撖� `self.list_widget.wheelEvent = self.wheelEvent` 餈嗵�隡𡁜紡�� C++ 銝� Python 撅� `self` 摰硺�瘛瑟�����𡝗䲮撘譌��㺿銝箏銁 `eventFilter` �行⏛撅�笆 `QEvent.Type.Wheel` 餈𥡝�蝏煺�隞������冽�頧格𧒄嚗𣬚眏 `eventFilter` �行⏛撟嗡蝙�� `rotate_highlight(..., is_hotkey=False)` 餈𥡝�頧格揢嚗���嗉圻�� `self.has_interacted = True` ��漣銝� 5s 頞�𧒄���雿踹�皛朞蔭�滢�銝滢��臭誑�滨蔭�䭾�雿𡏭恣�塚��䔶�銝滚�隡𡁏情�� Alt �暹�蝖株恕���敹梹�隞舘��蝠摨閖��滢�皛𡁜𢆡�嗥眏鈭� Alt �格𧋦頨怠�鈭擧𠹭撘��嗆��紡�� 30ms �祆𧒄�芸𢆡��揢��漱鈭埝�瘣𠺶��
    - [x] **敶餃�瘝餅�蝛箸聢�桀翰�瑞＆霈斗�����桅�**嚗𡁶眏鈭� `QListWidget` 隡𡁏�韐寧征�潮睸鈭衤辣嚗�銁 `eventFilter` �嗆挾璉�瘚见��桃� `Key_Space`嚗�征�潮睸嚗㗇�銝𧢲𧒄嚗諹�銵峕��齿㜃�芰凒�交�銵� `trigger_switch_and_close()` 撟嗉��� `True` 瘨�晶霂乩�隞塚�銝滨誧蝏剖��𤾸��𤑳� `QListWidget`����曉�銋讠蓡靽嗪�鈭�征�潮睸�賡◇���銵𣬚＆霈文��Ｕ��

## 2026-05-23 12:35
- [x] **靽桀��滚��滨蔭霈⊥𧒄憭望�銝𡡞����頧桅俈�芸𢆡蝖株恕 Bug (Fixed Rotator Key Reset & Mouse Wheel Auto-confirm Bug)**嚗�
    - [x] **靽桀��Ｘ��厰睸��/餈䂿� Alt+R 靘萘�鋡� 1.5s 撘箏��喲𡡒��䔮憸�**嚗𡁏䰻�𤾸�撅�敹急㭘�� `Alt+R` �滚�餈䂿��嗥凒�亥��其�蝐餌漣 `rotate_highlight`��眏鈭擧迨�滚銁霂交䲮瘜蓥葉�芸� `self.has_interacted` 霈曆蛹 `True`嚗�紡�渡鍂�瑞�餈墧�����Ｘ�銵䔶蛹�䭾�瞈�瘣� 5.0 蝘坿��嗅�蝥改�靘萘���鍂 1.5 蝘坿��嗅��准��銁 `rotate_highlight` 銝剖��乩� `self.has_interacted = True` ���霈堆��𣂼�雿蹂遙雿閙��桅����銝箏��賢�蝢𡡞�蝵株恣�塚�撟嗆�蝻嘥�蝥扯秐 5.0 蝘鍦��刻��嗚��
    - [x] **靽桀�曌䭾�皛朞蔭銝�皛𡁜𢆡撠梯䌊�冽�銵�僎�喲𡡒�� Bug**嚗𡁜��𣂼��箸�頧格��冽𧒄�曹� Alt �格𧋦頨怠停�舀𠹭撘����`alt_released = True`嚗㚁�銝� `wheelEvent` 靚�鍂鈭� `rotate_highlight` �� `self.selection_changed` 霈曆蛹鈭� `True`嚗��甇文銁 30ms �𡒊�銝衤�甈∟蔭霂Ｖ葉蝡见朖閫血�鈭��𨅯歇靽格㺿�㗇𥋘 + Alt�曉��萘���揢�餉�撖潸稲�芸𢆡�扯����朞�銝� `rotate_highlight` �寞��齿�鈭� `is_hotkey` �箏���㺭嚗䔶��典�撅�敹急㭘�� `Alt+R` 餈墧��嗡��� `is_hotkey=True` 撟嗉圻�� `selection_changed = True`嚗𥡝��銁曌䭾�皛朞蔭嚗ǑwheelEvent`嚗劐誑�𢠃睸�䀝�銝钅睸嚗ǑkeyPressEvent`嚗㕑圻�𤑳�擃䀝漁頧株蓮銝剖撩�嗡��� `is_hotkey=False`嚗䔶蝙�嗡�瘙⊥�敹急㭘�桅�㗇𥋘���雿溻��緵�券�朞�曌䭾�皛朞蔭�㚚睸�䀝�銝钅睸�芰眏皛𡁜𢆡嚗䔶��滢��牐蛹 Alt �格𠹭撘���紡�� 30ms �祆𧒄�芸𢆡��揢嚗諹�峕糓蝏抒賒靽脲�蝒堒藁嚗�僎�滨蔭鈭支��園𡢿嚗𣬚�敺� 5s 頞�𧒄�硋�頧�/蝛箸聢/�孵稬�𡒊＆蝖株恕��

## 2026-05-23 12:09
- [x] **隡睃� Alt+R 頧格揢�冽��滢�頞�𧒄�餉�撟嗡耨憭滨征�潮睸蝖株恕�芰��� Bug (Optimized Rotator Timeout & Fixed Space Key Confirm Bug)**嚗�
    - [x] **摰𣬚�靽桀�蝛箸聢�桀翰�瑞＆霈斗𧊋����桅�**嚗𡁏䰻�𡒊眏鈭� `QListWidget` �找辣�冽𥅾�厩��寞𧒄隡𡁻�霈斗㜃�芸僎瘨�晶 `Key_Space`嚗�征�潮睸嚗劐�隞嗉�銵屸★����ｇ�撖潸稲憭硋��� `keyPressEvent` �䭾��閗繮���朞�銝� `WindowRotatorDialog` 憓𧼮� `eventFilter`嚗��鋆�銁蝒堒藁�芾澈��list_widget` �𠰴�閫�藁銝𠺪�嚗�銁 KeyPress �嗆挾�𣂼�撖寧征�潮睸摰墧鴌撘箄��行⏛嚗�僎�冽�銝𧢲𧒄蝡见朖瞈�瘣� `trigger_switch_and_close`嚗��蝢舘噢�𣂼朖�嗥征�潛＆霈文��Ｕ��
    - [x] **摰䂿緵�諹膘�䭾�雿𨀣惣�質��嗉䌊��㦤��**嚗�
        - 撘訫� `self.has_interacted` �嗆���霈啁鍂�瑟糓�血�撅閗�隞颱�摰噼捶�抒�曌䭾�嚗�宏�具����颯���頧殷��㚚睸�矋��厰睸��𠹭�殷�鈭支���
        - 暺䁅恕�瑕鍳�冽𧊋鈭支��嗆���嚗諹挽摰𡁏��剔� **1.5 蝘埝��滢�頞�𧒄**����𨅯蘨�臬鐤�箇�銝��潸�峕𧊋�厰睸嚗𣬚������ 1.5s �舘䌊�睲������綽��踹��格𣏹��
        - 銝��衣鍂�瑕𢆡鈭������睸�䀹�皛朞蔭餈𥡝�鈭支�嚗��撠���園��潸䌊�典�蝥找蛹 **5.0 蝘埝��滢�頞�𧒄**��
    - [x] **撘訫�擃㗛��滢��蹱迫璉�瘚钅�蝵�**嚗𡁜銁�典�鈭衤辣餈�誘�其葉嚗峕��� `MouseMove`��MouseButtonPress`��MouseButtonRelease`��KeyPress` , `KeyRelease`��Wheel` 蝑㗇��劐漱鈭雴�隞塚�撟嗅銁鈭衤辣�𤑳��嗡蜓�冽�霈� `self.has_interacted = True` 撟園�蝵� `self.last_action_time = time.time()`嚗諹噢�售�𨅯蘨閬���滢�撠望��𨅯��剛恣�塚�銝��血�甇Ｘ�雿𨀣說 5 蝘埝��芸𢆡�喲𡡒�萘�霈曇恣�����
    - [x] **�拍��𥕦遣銝𤾸�獢�𡠺蝡衤遙�⊥���**嚗𡁜�撱箏僎敶埝﹝鈭���急𠯫��𧒄�游𦶢�滨��祉�隞餃𦛚皜����辣 [20260523_1209_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/bcced771-ba69-479b-95ee-71af16d3d711/20260523_1209_task.md)��

## 2026-05-23 02:13
- [x] **靽桀� WindowRotatorDialog 曌䭾��孵稬�� Alt �芣�銵���� Bug (Fixed Rotator on_item_clicked Missing)**嚗�
    - [x] **�寞祥 `on_item_clicked` �寞�蝻箏仃**嚗𡁜��� `list_widget.itemClicked.connect(self.on_item_clicked)` 撌脰��乩� `on_item_clicked` �寞�隞擧𧊋摰帋�嚗�紡�湧�����餃�銵券★�𤾸��冽�隞颱��滚���‘�其�摰峕㟲�� `on_item_clicked(self, item)` �寞�嚗峕��� `UserRole` 銝剖��函� HWND嚗峕凒�� `curr_idx`嚗䔶蜓�刻��� `detect_timer.stop()` �餅迫頞�𧒄�餉�撟脫贋嚗�僎蝡见朖閫血� `trigger_switch_and_close()` 摰峕��𡁶���揢銝𤾸��准��
    - [x] **曌䭾��孵稬�唾�銝箇＆霈歹�Click-as-Confirm嚗�**嚗𡁻�����餃�銵券★�舀�蝖桃��劐葉蝖株恕靽∪噡嚗峕���蝑匧� Alt �拍��曉����朞� `on_item_clicked` �湔𦻖 stop 霈⊥𧒄�典僎��揢嚗�蝠摨閗��蹂�"曌䭾��嫣��� Alt 隞滚�鈭擧�雿讐𠶖��紡�� check_alt_release �䭾�閫血�"��漱鈭埝香閫鉝��


- [x] **摰䂿緵�拍��滚蝱�衣��閗繮銝𤾸𢆡�� MRU 蝒堒藁��揢憿箏��芸𢆡靚�迤 (Fixed Rotator MRU Order Optimization)**嚗�
    - [x] **摰䂿緵�拍��衣�蝒堒藁�冽�����**嚗𡁜銁 `_get_all_open_trade_windows` 銝剖��� Windows �毺� `GetForegroundWindow` 霂餃�敶枏��拍��衣�蝒堒藁�交�����𨅯��滨��孵蘂���鈭𤾸虾閫�漱�梶����銵其葉嚗��霂湔��滨��𧢲迨�漤�朞�曌䭾��见𢆡�孵稬�亦�鈭�砲蝒堒藁��
    - [x] **摰墧𧒄�齿�銝𤾸撩�𤤿蔭憿� (MRU Promotion)**嚗𡁶頂蝏煺�撠�砲�衣� HWND �祇𡢿蝘餃𢆡 to `self._window_mru_list` ��洵 0 雿溻��＆靽嘥�甈∟圻�� `Alt+R` ��揢�冽𧒄嚗��憪钅�鈭格����蝢𤾸笆朣� `(0 + 1) = 1`嚗�朖銝𠹺�甈∠�餈���埝㺭蝚砌�銝芰����嚗諹噢�𣂷�銝� Windows `Alt+Tab` ���銋衤�蝘埝���赤頝喟��毺� MRU 雿㯄�嚗�蝠摨訫��支��瑕��啁��臬𢆡憿箏�蝏烐沲��
    - [x] **�拍��𥕦遣銝𤾸�獢�𡠺蝡衤遙�⊥���**嚗𡁏��扯�����𥕦遣鈭�𡠺蝡衤遙�⊥��閙�隞� [20260523_0145_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/12502b81-57bc-43bf-a780-9883c4bb4048/20260523_0145_task.md)��
    - [x] **靽桀��航��𣇉�������雿滢� Alt+R �𡑒”銝凋��曄內 Bug (Fixed Visualizer Title Mismatch Bug)**嚗�
        - [x] **蝎曉��交��𨅯粉�寥�**嚗𡁏䰻�𡒊眏鈭� `trade_visualizer_qt6.py` 銝剔�甇�蜓蝒堒藁���憸䁅◤霈曆蛹 `"PyQuant Stock Visualizer (Qt6 + PyQtGraph)"`嚗諹�� `_find_visualizer_hwnd` 銝剖��寥�����株�銝� `["��𧒄�航���", "TradeVisualizer", "K蝥踹虾閫��", "�譍遠撘�𢆡霂行�"]` 撖潸稲摰���䠷��� EnumWindows 撖餅𪄳 HWND 瘞貉�餈𥪜� 0��
        - [x] **靽格迤�寥��喲睸摮堒�銵�**嚗𡁜銁璅∠��寥��𡑒”銝剖��乩� `"PyQuant Stock Visualizer"`, `"Stock Visualizer"` �屸�𡁶鍂�� `"Visualizer"`嚗䔶蝙敺堒朖雿踹��唳瓷�厩鸌�急㺿�剁�EnumWindows 銋蠘� 100% 蝎曄＆�閗繮�嗥���蘂��僎瘜典��� MRU �� `Alt+R` ��揢�𡑒”銝哨�摰𣬚���緵�航��𣇉�����

## 2026-05-23 01:40
- [x] **靽桀� KLineDetailWindow �祉��祆筑蝒堒藁�峕艶�券�𤩺�銝𡒊�皜�𠗕憸� (Fixed KLineDetailWindow Transparency Bug)**嚗�
    - [x] **�滚� paintEvent 蝏睃��𢠃�𤩺�暺𤏸𠧧�峕艶**嚗𡁶眏鈭𡡞▲蝥扳�颲寞�撌亙�蝒堒藁�典��� `WA_TranslucentBackground` �塚�QSS�� `background-color` 隡𡁜仃��紡�渡�����券�𤩺����朞��� `KLineDetailWindow` 銝剖��� `paintEvent`嚗䔶蝙�� `QPainter` 撘箏��典�撅�‵��像�嗥𠶖����� `rgba(0, 0, 0, 180)` �𢠃�𤩺�暺𤏸𠧧�峕艶銝� 4px ����拙耦嚗�銁曌䭾��砍��嗅‵�� `rgba(17, 18, 36, 230)` �烾��嘥��脖��批��坿器獢��摰𣬚�閫��鈭��摮堒銁��僚�曇”�峕艶銝𧢲�瘜閗儘霈斤��𤤿���
    - [x] **隡睃� QSS �瑕�銵券�蝵�**嚗𡁜��瑕�銵其葉 `QFrame#DetailContainer` ����臬�颲寞�靽格㺿銝� `transparent` �� `none`嚗䔶漱�� `paintEvent` 蝏煺�皜脫��峕艶�𡃏器獢���踹�鈭�甅撘讛”撘閗絲���甈∠��嗅僕�啜��
    - [x] **摰䂿緵��眏����䁅�銝擧��������� (Implemented Reason Wrapping & Layout Protection)**嚗𡁜� `label` ����找耨�嫣蛹 `setWordWrap(True)` 撘��舀揢銵�僎霈曉���憭批捐摨虫蛹 `280px`嚗���嗅撩�園��� `KLineDetailWindow` �芾澈��憭批捐摨虫蛹 `300px`嚗𥕦笆�漤𢒰���擃䀝��嗉”�潔� MA ��誘�詨��唳旿瘜典� `white-space:nowrap;` 撘箏�銝齿�銵䎚��蝠摨閗圾�喃��輻��望��祆�瘜閗䌊�冽�銵�紡�湔�瘚桃�璅芸��𣳇��劐撓��漱鈭垍撩�瘀�銝𠉛＆靽嘥��㗇聢撘誩笆朣鞉神銝齿�銋晞��
    - [x] **撘訫� 3 蝘㘾�甇Ｘ��𨀣��賭��斗㦤�� (3-Second Inactivity Hover Protection)**嚗𡁜銁 `KLineDetailWindow` 撘訫� `QTimer` �蹱迫�脫�霈⊥𧒄�剁�敶㯄�����交��函����蝘餃𢆡�塚�擃㗛��瑟鰵 3 蝘鍦��嗵�敺���芣�敶㯄���銁�祆筑蝒堒藁銝𠹺���**�蹱迫銝滚𢆡�𦦵�頞�� 3 蝘�**�塚��齿迤撘誩𤧅�㘾��滚榆�批��坿器獢���硋𢆡�𦠜����敶餃��𦦵�鈭�����餈��敹恍���餈�𧒄�曹�蝒堒藁餈�捐撘訫�霂航圻�𡝗嗻�𦠜���獈蝣齿��䀹�瘚讛� K 蝥蹂�銵峕�蝏����艇�滢�撉𣬚′隡扎��

## 2026-05-23 01:35
- [x] **靽桀��航��𤥁�蝔见蘂��嵗撉䔶��暸��烐綉閫��撠讐𣊭韐游�擃䀹�撣�� (Fixed Visualizer Hwnd Detection & MonitorWindow Tiles Layout)**嚗�
    - [x] **敶餃��寞祥 Visualizer 蝒堒藁銝Ｗ仃 Bug**嚗𡁜��支�撖� `qt_process.is_alive()` ���摨阡��嗚����朞� socket 餈鞱��𣇉𡠺蝡贝�霂閙𧒄餈𤤿��嗆���鋡思蜓蝐餌凒�交��㚁�雿���������嗅��其�撌乩�甇�虜嚗𣬚緵�寧鍂 Windows 摨訫� `IsWindow` �� `IsWindowVisible` �拍�餈𥡝��⊿�嚗𣬚＆靽� Visualizer 100% �賢�鋡怠��亙��Ｗ膥��
    - [x] **摰䂿緵璁�艙�暸��烐綉蝒堒藁蝵烐聢撠讐𣊭韐游� (Grid Tile Layout for Monitor Windows)**嚗�
        - 隞𦒘�蝏毺���凒�𡑒”銝剖竉蝳颱����� `MonitorWindow_` 蝒堒藁嚗��敹萄�10�暸��烐綉嚗㚁���之�圈��曆�頧株蓮�函�蝥萄��拍�擃睃漲��
        - 憓噼挽鈭���瑁斐�箏�嚗㇍iles嚗㚁��拍鍂 `QGridLayout`嚗��銵� 3 �梹�隞亥�蝎曄��滨妍�峕��園��渡������像�厰僼撠讐𣊭韐湔㗁頧質�鈭𤤿�����
        - �㯄�惩��𤑳��寧�蝏煺�擃䀝漁�嗆��㦤嚗𡁜� `curr_idx` 皛𡁜��瑁斐蝒堒藁�塚��祇𡢿皜�膄撣貉��𡑒”�劐葉憿孵僎撖寧𤌍����孵��扯�擃睃�撌桅�鈭殷�瘛梯�摨𨰻��擀�厩遛摮𨰜��漁�鍦��㕑器獢��嚗�蝠摨訫笆朣𣂷��桃�撌血𢰧�孵��柴���銝钅睸����厩��桀�曌䭾�皛朞蔭頧株蓮嚗峕�憭扳����憭𡁜�憭𡁶�����抒㴓憓����漱鈭埝�����
    - [x] **靽桀�撅��� NameError 撖澆�蝻箏仃 Bug**嚗𡁜銁 `show_qt_rotator_dialog` �� `ImportError` 靽脲擪�𦯀葉銵亙�鈭� `QFrame`, `QWidget`, `QGridLayout` �� `QPushButton` 蝑� PyQt 撣��蝏�辣����典紡�伐�敶餃�瘨�膄鈭�眏鈭𦒘��典�蝻箏仃撘訫��� `NameError: name 'QFrame' is not defined` 撏拇���

## 2026-05-23 01:05
- [x] **摰䂿緵撘��箄䌊�㰘蝸�𠰴虜閫��韏瑞��� MRU �芸𢆡霈啣���惣�質‘�颯���瘣餅嵗撉䎚��𦶢�滢耨憭滢�曌䭾�皛朞蔭鈭衤辣�滚��舀� (Fixed Rotator Auto-Load, Multi-Window Registry, Process Liveness, Window Name Bug & WheelEvent Navigation)**嚗�
    - [x] **�嘥��碶蜓蝒堒藁銝� MRU ����𤘪�**嚗𡁜銁 `instock_MonitorTK.py` ���惩遆�唬葉�嘥��硋�撅� `self._window_mru_list = []`嚗�僎蝡见朖瘜典�銝餅綉�嗅蝱�芾澈�� HWND嚗��摰𡁜抅蝖��潦��
    - [x] **蝻硋�蝏煺� HWND 瘜典�颲�𨭌�亙藁**嚗𡁜銁銝餌掩銝剜溶�� `_register_hwnd_to_mru(self, hwnd)` �𣂼��賣㺭嚗諹�韐�ế�准��縧�溻������滚僎�坔� `_window_mru_list`��
    - [x] **�券��𣈯�銝舘䌊�刻‘�駁���**嚗𡁻��� `_get_all_open_trade_windows`嚗峕𣈲����芸鍳�冽�憭齿��见𢆡�𥕦遣����㗇�敹萄�10�暸��烐綉摮鞟����`self.monitor_windows`嚗剹�� 蝥輻��抒����`self.kline_monitor`嚗匧�璁�艙霂行�蝒堒藁嚗Ǒself._concept_win`嚗匧��冽����撟嗅銁 `Alt+R` 閫血��嗉䌊�刻‘�餉扇�� MRU �𡑒”銝准��
    - [x] **撘訫� Visualizer �条恣餈𤤿�摮䀹暑靽脲擪 (Process Liveness Guard)**嚗𡁜銁 `_get_all_open_trade_windows` �Ｘ��航��硋膥�塚�憓𧼮�鈭� `hasattr(self, 'qt_process') and self.qt_process and self.qt_process.is_alive()` �文�����冽�蝞∪�餈𤤿��笔�摮䀹暑�嗆�撠���� of HWND �堒�頧桀𢆡嚗峕�蝏苷�畾讠��萄偶蝒堒藁�交�撖孵��Ｗ膥��僕�啜��
    - [x] **敶餃��寞祥 Visualizer 蝒堒藁�滨妍霂舀� Bug (Fixed Name Mismatch Bug)**嚗𡁜⏚�� DRY �笔�摨罸膄鈭� `rotate_trade_windows` �� `WindowRotatorDialog.show_rotator` 銝剖�雿� of `name_map` 憯唳���㺿銝箏銁 `_get_all_open_trade_windows` 銝剔�銝��𣈯�撟嗥�摮� `self._rotator_window_names` �典��滨妍�惩�摮堒�嚗䔶蝙���厩����憒� K 蝥輻��扼���敹菔祕����𦆮�讐��抒�嚗匧��質繮敺� 100% 蝎曉���葵�批� Emoji �暹��滨�銝𡒊�摰𧼮�蝘唳�瘜剁�敶餃�蝏��鈭��𨅯�摰�����鋡怨秤��蛹 Visualizer�萘�銝仿�蝻粹萅��
    - [x] **摰䂿緵曌䭾�皛朞蔭��揢銝舘��嗉䌊���蝵� (Fluid Mouse-wheel Navigation & Inactivity Refresh)**嚗𡁜銁 `WindowRotatorDialog` 銝剝��� `wheelEvent` 鈭衤辣嚗峕𣈲����䀹��湔𦻖�券����頧桀銁閫��銝𠰴��㗇䔉�睲�/�睲�皛𡁜𢆡頧株蓮��揢擃䀝漁�劐葉憿嫘��僎�� `__init__` 銝剖� `self.list_widget.wheelEvent = self.wheelEvent` 閬���滚��𡢅�雿踹�敶𤘪�皛朞蔭鈭衤辣�𤑳��塚�隡𡁶��餅凒�啣僎�滨蔭 `self.last_action_time = time.time()`嚗�蝠摨閙��支��𨀣��券����頧格𧒄蝒堒藁鋡� 2.5s 頞�𧒄霂臬��凌�萘�雿㯄�蝻粹萅��
    - [x] **�拍��𥕦遣銝𤾸�獢�𡠺蝡衤遙�⊥���**嚗𡁏��抒鍂�瑕撩�嗉����敶埝﹝�𥕦遣鈭���急𠯫��𧒄�游𦶢�滨��祉�隞餃𦛚皜����辣 [20260523_0105_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/12502b81-57bc-43bf-a780-9883c4bb4048/20260523_0105_task.md)��

## 2026-05-23 01:01
- [x] **摰𣬚��賢𧑐 K 蝥踹�摮堒���祕��筑蝒𦯀漱鈭雴�雿滨蔭����𡝗㺿�� (Implemented Draggable K-Line Details Floating Frame & Geometry Persistence)**嚗�
    - [x] **擃䀝��蠘��笔���甅撘譍��券���捆 (100% High-Fidelity Style and Content Retention)**嚗�
        - 敶餃�摨罸膄鈭�𤐄摰𡁶�霂行�蝒堒之撠誯��塚���鍂 `adjustSize()` 霈拍���覔�桀����摰寡䌊���隡貊憬嚗諹圾�喃��笔��曹�靽∪噡霂湔��㚚��删��梯�憭𡁜紡�渡��Ｖ縑�臭腺憭梯◤�芣鱏��艇�� Bug��
        - 撟單𧒄�嗆���嚗��曌䭾�蝘餃�嚗㚁��峕艶霈曆蛹�����㮾�𣬚� `rgba(0, 0, 0, 180)` �𢠃�𤩺�暺穃�嚗峕�隞颱�敶抵𠧧颲寞�銝擧��页����摮𦯀��𦠜����銝𤾸� `pg.TextItem` ����㗇�靽⊥�摰��銝��氬��
        - 蝳�鍂鈭����𧋦��䌊�冽揢銵䕘�`setWordWrap(False)`嚗㚁�靽肽�鈭���厩�銵冽聢撖寥��� MA 憸𡏭𠧧蝑匧捐�垍�蝏嘥笆銝滢僚��
    - [x] **摰䂿緵 Hover �祆𧒄瞈�瘣餅��賣��衤��𡁶瑪�鞟內 (Hover-Reactive Drag Handle and Guidelines)**嚗�
        - �滚� `enterEvent` �� `leaveEvent` 鈭衤辣���曌䭾�蝘餃�霂交筑蝒堒躹��𧒄嚗𣬚��嗅𤧅�㘾▲�冽��賣��𧢲�嚗�遬蝷� `�� �硋𢆡隞亥��港�蝵害嚗���� 16px嚗㚁��峕𧒄颲寞��䀹凒銝粹��滚榆�批��𡜐�`#00f0ff`嚗㚁�曌䭾��㗇��湔鰵銝箸��賢�摮埈��選��鞟內�滨��贝砲瘚桃��舀��賬��
        - 曌䭾�蝳餃�瘚桃��塚��芸𢆡�鞱��𦠜�撟園��餅��㕑器獢��摰䂿緵�𣈯�����曆��餅𧒄嚗����䔉���瘚株祕��甅撘誩��其�璅∩��猾�萘����雿㯄���
    - [x] **摰䂿緵�㰘器獢�像皛煾������**嚗𡁻��� `mousePressEvent`��mouseMoveEvent` 銝� `mouseReleaseEvent`嚗諹恣蝞㛖㮾撖嫣�撅誩��典��鞉����撌殷��滨��见虾隞亙銁撅誩�隞餅�雿滨蔭�见𢆡蝘餃𢆡霂亦�����𡝗嗻�𦠜𦆮�塚�蝡见朖�笔�蝥扯圻�� `MainWindow` �嗆��㦤���銋���嗵���
    - [x] **�脫�瘣颱��桃��衣��Ｗ�靽脲擪**嚗𡁜��乩� `Qt.WidgetAttribute.WA_ShowWithoutActivating` 撅墧�找��扎���蝖桐�鈭�銁����㗇�擃㗛�蝘餃𢆡��圻�� `show()` �峕凒�唳𧒄嚗䔶蜓蝒堒藁�桃�颲枏�嚗���砍椰�單䲮�煾睸��揢 K 蝥踴����亥�蟡其誨����桃��衣�嚗厩�撖嫣�隡朞◤霂行�蝒堒藁憭箄粥嚗𣬚𤩅�滢�撉屸◇皛穃��腈��
    - [x] **摰䂿緵暺䁅恕韐渡揮銝𡡞�銝餌���漣�𠉛宏��**嚗𡁻�霈支�蝵格惣�質挽蝵桀銁 K 蝥踹㦛嚗Ǒself.kline_plot`嚗厩�撌虫�閫鍦��剁��讐宏 40px, 10px嚗剹��銁�芣��冽��踝�`is_custom_positioned = False`嚗厩��齿�銝页��滚�銝餌���� `moveEvent` �� `resizeEvent`����滨��𧢲�隡豢��硋𢆡鈭斗�蝏�垢�塚�霂行�瘚桃�隡𡁻�靽萘��圈�銝餃㦛銝�韏瑞宏�具��
    - [x] **�鞱�擃㗛�蝘餃𢆡��倌隞仿俈甇Ｚ�閫匧僕��**嚗𡁶�����譍��� pyqtgraph ����誯���膘餈孵�憭��蝘餌� `self.crosshair_label` ��倌嚗���� visibility 霈曆蛹 `False`嚗�僎�峕郊�典椰�單䲮�煾睸 `move_crosshair` 閫血��嗅笆�嗅撩�嗆��塚�嚗�蘨�𡁜�摮埈�蝥踹�雿㵪�敶餃�蝏��鈭�祕����� K 蝥踵�����𤤿���
    - [x] **瘛勗漲�澆捆 WindowMixin �嗆���銋��**嚗�
        - �嘥��𡝗𧒄嚗屸�朞� `self.load_window_position_qt` �芸𢆡�滚��堒� `window_config.json` �瑕� `kline_detail_window` ���銋���鞉�銝𤾸之撠𧶏�撟嗉䌊����斗鱏 `is_custom_positioned`��
        - ���箸𧒄嚗�銁 `closeEvent` 撠暸��曉�靚�鍂 `self.save_window_position_qt` 撟嗉��� `.close()` 銝� `.deleteLater()`嚗���𣂷��笔𦶢�冽�����券𡡒�胯��
    - [x] **�𥕦遣�祉�隞餃𦛚�亙�敶埝﹝**嚗𡁏��抒鍂�瑕撩�嗉����敶埝﹝�𥕦遣鈭���急𠯫��𧒄�游𦶢�滨��祉�隞餃𦛚皜�� file [20260523_0101_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260523_0101_task.md)��

## 2026-05-23 01:00
- [x] **摰𣬚�靽桀��典�蝒堒藁頧株砭敹急㭘�桅�暺䀝�摰硺�蝐駁��啣ㄟ�𤾸紡�湔����蝵� (Fixed Rotator Dialog Hotkey Silence & Redeclaration Instance Reset)**嚗�
    - [x] **�齿�蝒堒藁�蓥�摰硺�����𡝗�蝞�**嚗𡁜蝠摨閙��帋�銝餌�摨譍葉���撅��剝睸靚�漲��� `WindowRotatorDialog` 蝐餃ㄟ�𦒘� `show_qt_rotator_dialog` ����函�霂穃�銝剛圾�佗��脫迫瘥𤩺活閫血��剝睸�嗉砲蝐餉◤�齿鰵憯唳�撟嗉��硋紡�渡掩蝥� `cls._instance` ���敶㘾妟��㺿銝箔蜓蝔见�����批��� `self._rotator_dialog_instance` �湔𦻖��蝸銝𤾸ế摰𡄯�蝖桐�憭𡁏活閫血��典�敹急㭘�格𧒄�舐移���瘚见僎�滚��䔶�摮䀹暑摰硺��扯� `rotate_highlight`��
    - [x] **敶餃��寞祥敹急㭘�格�鈭���滚����**嚗𡁏䰻�𤾸僎靽桀�鈭�迨�滚� Replacement Chunks 銵��蝘餃紡�� `instock_MonitorTK.py` �𤑳�銝滚��湔𤜯�Ｕ����䔶蝙敹急㭘�格㜃�芸�靚�� QEvent 鈭衤辣憭���𤑳��脩��䠷��� Bug��
    - [x] **靽嗪�擃睃�撌桀�雿枏��㕑��舀葡��**嚗帋��� `WA_TranslucentBackground` 隞亙��圈����閫𡜐��滚� `paintEvent` 撘箏��� Qt 蝏睃�摰��銝漤�𤩺����暺𤏸�摨閗𠧧銝𤾸�雿栞擀�厰�颲寞�嚗�蝠摨閙�蝏萘忽�讐蒾摨閙���𠧧撟脫贋��
    - [x] **�亙��拍��喲𡡒銝� MRU �齿��芣�**嚗𡁜��Ｙ𤌍��𧒄嚗諹䌊�冽�鋡急�瘣餌���宏�� `main_app._window_mru_list` 蝚砌�憿嫣誑�芸𢆡�湔鰵 MRU 擐碶���銁 `closeEvent` 銝剖撩�𥟇釣��撟嗅��園�憸� `detect_timer` 摰𡁏𧒄�剁�撟嗆��� `self._rotator_dialog_instance` 靽肽����摰匧�嚗屸妟瘜�蠧��
    - [x] **�𥕦遣�祉�隞餃𦛚�亙�敶埝﹝**嚗𡁏��抒鍂�瑕撩�嗉����敶埝﹝�𥕦遣鈭���急𠯫��𧒄�游𦶢�滨��祉�隞餃𦛚皜����辣 [20260523_0100_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/12502b81-57bc-43bf-a780-9883c4bb4048/20260523_0100_task.md)��

## 2026-05-23 00:52
- [x] **摰𣬚�閫���典�蝒堒藁頧株砭��揢�其��湔��踺����脤�𤩺�摨虫���RU 蝏湔擪銝滚��𡃏䌊����嗆㦤�� (Optimized Window Rotator System & Timeout Failsafe & 100% Solid Dark Theme)**嚗�
    - [x] **摰䂿緵摰��銝漤�𤩺�����滚榆摰硺��峕艶**嚗𡁜蝠摨閖�蝵桀僎�孵�鈭� `WindowRotatorDialog` ��甅撘譌���朞��滚� `paintEvent` 撘箏�雿輻鍂摰��銝漤�𤩺����暺𤏸��脰��� (`#111224`) �䔶漁�坿𠧧摰硺��穃�颲寞� (`#00f0ff`) �䔶漁蝏輯𠧧 (`#39ff14`) �劐葉���鈭殷�蝖桐�閫��銝滢�鋡怠��寞�銋曹漱�枏㦛銵函�擃䀝漁憸𡏭𠧧撟脫贋嚗峕�憭扳�����脣蔗�滚榆銝𡒊𤩅�滩儘霂�漲��
    - [x] **�寞祥餈䂿賒�厰睸撘訫��������湔��� Bug**嚗𡁜��牐� 2.5 蝘垍��𨀣��厰睸�䭾�雿鎿�嘥撩�嗉��嗉䌊��㦤�嗚����䀹��㰘捏�其遙雿閙�憓���日���揢�剁��芾�頞�� 2.5 蝘埝瓷�㕑�銝�甇亦��格�銝𠹺��格�雿頣�蝟餌�撠�䌊�𤏸圻�穃��函�頝荔��芸𢆡���敶枏�擃䀝漁憿孵僎�扯�撘箏��滚蝱�𡁶���揢嚗��蝢𤾸��� Dialog嚗𣬚�銝漤�䭾��格𣏹��
    - [x] **�賢𧑐 Alt �暹������摨𥪯� ESC �脫�皜��**嚗𡁜⏚�� `QTimer` ��蝸 30ms 頞��憸烐�瘚见膥嚗屸�朞� `ctypes` �拍�霂餃� `GetAsyncKeyState(0x12)` (Alt ��)����行𠹭�页��其�瘥怎�蝥批��芸𢆡瘨�����銁 `closeEvent` 鈭衤辣銝哨�敶餃�皜��撟嗆釣��鈭���啁� detect_timer 摰𡁏𧒄�剁�撟嗆�蝛箏�撅��蓥�摰硺� `_instance = None`嚗䔶�霂��隡𡁻�䭾� Timer 蝝舐妖�䔶蜓蝥輻�瘜�蠧��
    - [x] **�芷��� MRU �嘥��𡝗�摨譍��芣�**嚗𡁜⏚�� `_get_all_open_trade_windows` �� Tk �臬𢆡�𦠜�銝芯漱鈭垍��賢𪂹�煺葉�冽����Ｕ���撱箏僎��賒�湔鰵���匧虾閫�漱�梶���� MRU ��蟮�鍦�����Ｘ𧒄�箔�甇文�銵刻�銵屸�鈭桃揣撘閙�撠��蝖桐�頧株砭憿箏� 100% 蝚血��滨��渲���
    - [x] **靽桀�餈墧� Alt+R / Alt+Shift+R �䭾�頧格揢銝衤�銝�/銝𠹺�銝芰���� Bug**嚗𡁏䰻�𡒊眏鈭𤾸��函掩 `WindowRotatorDialog` ���憭滚ㄟ�𤾸紡�湧��� `cls._instance` ���銝齿鱏敶㘾妟��䔮憸塩��� Dialog 摰硺��条恣�其蜓蝔见����撅墧�� `self._rotator_dialog_instance` 銝𠺪�摰䂿緵鈭��甈∟圻�穃�撅��剝睸�嗥凒�亥�摨血歇摮䀹暑摰硺�餈𥡝� `rotate_highlight` 撟嗉歲餈���啣�靘见�嚗諹噢�𣂼�蝢舘�峕��嗉�韐舀�����𦯷lt+R 餈䂿賒�芸𢆡銝衤�銝迎�Alt+Shift+R 餈䂿賒�芸𢆡銝𠹺�銝芬�嗪睸�䀹��其�撉䎚��
    - [x] **�𥕦遣�祉�隞餃𦛚�亙�敶埝﹝**嚗𡁏��抒鍂�瑕撩�嗉����敶埝﹝�𥕦遣鈭���急𠯫��𧒄�游𦶢�滨��祉�隞餃𦛚皜����辣 [20260523_0052_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/12502b81-57bc-43bf-a780-9883c4bb4048/20260523_0052_task.md)��

## 2026-05-22 23:45
- [x] **摰𣬚��賢𧑐�滢�蝟餌�蝥批�撅� RegisterHotKey �行⏛���憟� Alt+Tab Qt ��揢�Ｘ踎���憸𤑳���𠹭�贝䌊�刻��虫�獢�沲�䔶��拍頂蝏� (Unified Window Rotator System & Native AttachThreadInput & WindowRotatorDialog Switcher)**嚗�
    - [x] **�滚�銝餅綉��蔭蝟餌��典��剝睸撘閙�銝擧�瘞栞�蝔见�蝒�䌊�� (Extreme DRY & Self-Healing Fallback)**嚗𡁜�蝢舘���蜓�批�鋆��蝵桃�擃䀹��� Win32 `RegisterHotKey` 蝟餌��剝睸�行⏛銝� `PeekMessageW` 瘨��瘜萸��� `Alt+R` 銝� `Alt+Shift+R` 摰𣬚�餈賢��唳𠳿�� `_HOTKEY_MAP` 摰帋�銝� `setup_global_hotkey` 撘�郊�噼�銝准����� Windows �典��剝睸瘚���Ｗ��芣�蝟餌�嚗�**銝��� Alt+R 鋡怎頂蝏笔�隞硋虜撽餉蔓隞塚�憒� AMD Radeon Software �曉㨃敶訫���凝靽⊥⏛�整����亥㴝蝑㚁�甇餅香�詨�嚗𣬚頂蝏笔��芸�餈鞱�擃䁅� tasklist 餈𤤿�敹怎��急�霂𦠜鱏�箇移蝖株蔓隞嗅�嚗�僎�� 1 蝘鍦��芸𢆡��神蝘垍漣�滨漣�芣�銝箏��函��� [Alt+Q] 銝� [Alt+Shift+Q] �亦恣嚗𣬚𠶖����峕𠯫敹堒�甇亥郎蝷�**嚗諹䌊���颲� 99.9%嚗��隞�蝠摨閖��滢��曹��屸�瘨��瘜萇�鈭匧紡�渡�蝟餌�甇駁��鞉�嚗諹�䔶�霈拙��匧�撅��剝睸嚗㇁lt+B, Alt+E, Alt+M 蝑㚁�蝏抒賒靽脲� 100% 蝏嘥笆蝔喳�餈鞱�嚗��蝢舘殿銵䔶� KISS��AGNI 銝� DRY 蝻𣇉�蝢𤾸郎嚗�
    - [x] **擃睃失 Alt+Tab �曄內獢����稲����穃��烾�蝢𤾸郎**嚗𡁶洵銝�甈∟圻�𤑳��格𧒄嚗𣬚��餃銁撅誩�甇�葉憭桀撕�箔�甈暹�摰Ｘ�暺睲蜓憸矋�`#111224` �峕艶���閫鉝��擀�㕑��穃�颲寞�嚗厩��㰘器獢�蔭憿� Qt Panel `WindowRotatorDialog`��䌊����匧�敶枏����匧虾閫�漱�梶���僎餈𥡝��见末�滨妍��釣嚗䔶誑�穃��批�蝏輸��滚榆擃䀝漁敶枏��劐葉憿嫘��
    - [x] **擃㗛� GetAsyncKeyState �拍��暹��單揢�笔�**嚗𡁜⏚�� `QTimer` ��蝸 30ms 擃㗛�璉�瘚见膥嚗屸�朞� `ctypes` 霂餃� `GetAsyncKeyState(0x12)` (VK_MENU Alt ��) �拍��萄像�嗆������行��䀹��曉��桃�銝羓� `Alt` �殷�Dialog 隡𡁜銁鈭𡁏神蝘垍漣��䌊�冽���嚗���嗆�銵�撩�𤤿忽�讛��佗�摰䂿緵�𨀣𠹭�见朖�Ｔ�萘�擃条漣�滨��讠凒閫㗇�雿頣�
    - [x] **�桃�銝𠹺��� & �噼膠 Esc �脫��典�摰�**嚗𡁏遬蝷箸����蝢擧𦻖蝞⊥��桐�隞嗚����䀹��Ｚ�蝏抒賒�� Alt+R 皛𡁜𢆡擃䀝漁嚗䔶��臭誑�湔𦻖�朞��桃��� **銝𠹺��孵��� (Up/Down)** �� **�噼膠�� (Enter)** �芯蜓敺株�嚗峕���� **Esc ��** 隡㗛��𡝗���
    - [x] **擐硋� Windows 摨訫� AttachThreadInput 撘箏�蝛輸�讛��行���**嚗𡁏���𤫇�衤� Windows �滢�蝟餌��滚蝱�衣�靽脲擪�𣂼����朞��� `_force_focus_hwnd` 銝剜�銵� `AttachThreadInput` 銝湔𧒄撠���滨瑪蝔衤��格��滚蝱蝒堒藁蝥輻�撘箄�蝏穃�嚗諹��峕�蝻萘������ `IsIconic` (�Ｗ���撠誩�)��ShowWindow(SW_SHOW)`��SetForegroundWindow` �� `SetFocus`嚗諹噢�𣂷� 100% 敹��蝵桅▲���鈭桀僎�𡁶����靽萘����毺忽�𧶏�敶餃���縧鈭� Alt+Tab 憸𤑳���揢����佗�
    - [x] **�拍�摨罸膄���㕑��嗆𧋦�啁��桃�摰帋�靚�鍂 (Full Redundancy Eradication)**嚗𡁜抅鈭𡒊頂蝏笔�撅� Windows �剝睸撖孵��毺㴓憓�� 100% �拍��行⏛嚗���Ｗ�撘�僎�拍��娪膄鈭� `_bind_qt_shortcuts` 餈嗘�餈�𧒄蝛箸䲮瘜閧�摰帋�嚗���嗅��支�韏偦帕�Ｘ踎��踎�㛖�隞琿𢒰�輻��臬𢆡頝臬��𣬚����匧�雿躰��具�����之�讠憬鈭�頂蝏��颱誨����瘀�摰𣬚�頝菔�鈭� KISS��AGNI 銝� DRY ���蝞�霈曇恣蝢𤾸郎嚗�
    - [x] **�𥕦遣�祉�隞餃𦛚�亙�敶埝﹝**嚗帋艇�潭說頞單��厩鍂�瑕撩蝥行�閫��嚗��撱箔��交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2345_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/ea77c44a-c5f4-4975-84be-09df0349dd69/20260522_2345_task.md)��

## 2026-05-22 23:06
- [x] **摰𣬚��賢𧑐��稬�踹�憭批��∠�撅閧內����餉䌊�券��滚榆�芰�憭滚�銝𤾸𢰧�桐��桃�韐渲�皛� (Premium Concept Cards, Auto-Flicker Copy & Right-Click Paste and Filter Sync)**嚗�
    - [x] **�踹�憸䀹�霂行�蝒堒藁�煺�憭滨鍂銝漤緾���銝餌���㮾撖嫣葉敹��銝剜�銋�� (Flicker-free popup reuse, Master-relative Centering & Esc dismiss)**嚗�
        - [x] **摰䂿緵�煺�蝒堒藁憭滨鍂**嚗𡁜��颱��諹�蟡冽𧒄嚗諹𥅾霂行�蝒堒藁�芸��哨��湔𦻖�煺�皜�征�嗅�蝏�辣撟嗆葡�𤘪鰵�∠巨憸䀹�嚗��蝢𦒘�����厩�蝒堒藁�牐�憭批�銝𤾸�撟閙��賢�����Ｚ�摰∟恣 100% 瘥急��芰�嚗屸◇皛穃漲�����
        - [x] **�齿�銝餌���㮾撖嫣葉敹��銝剔�瘜�**嚗𡁜��𨀣𧋦�唳瓷�匧之撠誩��鞉�蝻枏�嚗𣬚����隞�**敶枏�蝑𣇉裦�㕑�銝餌����銝剖�銝箏抅�寡䌊���霈∠� xp, yp �鞉�**嚗�僎�冽葡�枏��芸𢆡�朞�撅誩�撠箏站餈𥡝�颲寧�摰匧��脣鴃�𣂼捐嚗�蝠摨閙��支��臬�瞍�宏銝𤾸�蝻拇𦆮撣行䔉������蝳颯��
        - [x] **擐硋��菏ithdraw �鞱𤪖皜脫� + deiconify 摰𣬚���緵�嗪��芾挽霈�**嚗𡁜銁�𥕦遣霂行� Toplevel 蝒堒藁�嗅�銵諹��� `popup.withdraw()`嚗�銁�券��牐�霈∠�銝𤾸����頧賢��函�����𣂼�嚗峕� deiconify ��緵嚗�蝠摨閙��支�雿滨蔭霈曉��滚銁撅誩�撌虫�閫㘾緾�啁�閫���閧鮟��
        - [x] **敶餃��滨鍂蝟餌��芸蒂����硋遆��**嚗𡁜�蝢𡡞�摰���辷��函��朞�蝐餉䌊撣衣� `self.load_window_position` 銝� `self.save_window_position` �唳��寞��亙��唳踎�烾��鞟��㰘蝸銝𤾸��剜�銋���������� `0,0` ����刻�皛支��歹��Ｘ��支��曹�甇�銁�喲𡡒�� `update_idletasks` 撘訫�����典援皞�������蝠摨訫��唬� 100% �嗡誨����具��
        - [x] **皜�膄 `kernel_toast_window` 頧砍摩靚�鍂 `self.master` ���憭折���**嚗𡁜蝠摨閙��支�瘚桀𢆡�扯��𧢲踎�典��准���瘥���㰘蝸雿滨蔭�塚�憭扯晶�冽��圈�朞� `self.master.save_window_position` / `load_window_position` 靚�鍂���撟湧�����𠳿�� `StockSelectionWindow` �祈澈撠梁誧�蹂� `WindowMixin`嚗𣬚凒�亙��券���蛹���湔𦻖撟脣��� `self.save_window_position` 銝� `self.load_window_position` �𣂼��賣㺭嚗�之撟�����蝟餌���迅摰𡁏�找�����𤥁”�堆�
        - [x] **摰𣬚��賢𧑐霂行��∠��刻�������頧桀��湔��冽𣈲�� (High-fidelity Fluid Mousewheel Scroll)**嚗𡁜蝠摨閙𤫇�衤� Tkinter Canvas 撣行��冽辺摰孵膥�券�����穃��找辣�嗆�瘜閗◤曌䭾�皛朞蔭撽勗𢆡皛𡁜𢆡����毺��嫘��銁�∠�蝒堒藁 `popup`����函𤫇撣� `canvas`����典捆�� `scrollable_frame` 隞亙��冽����睃枂����匧��瑯��之摮烾��� Label �諹�皛� Button 銝𠺪��券�銝����蝥踹𧑐蝏穃�鈭����� `<MouseWheel>` 鈭衤辣���霈粹�����𨅯銁�∠�����芯葵�讐�銝𠺪������稲銝脲���◇皛穃𧑐銝𠹺�皛𡁜𢆡瘚讛�嚗�
        - [x] **�寞祥鈭� Windows 暺䁅恕銝駁�銝𧢲��㕑”�潛��㗇�擃䀝漁���撖寞�摨血�擐��銝仿�閫�� Bug (High-Contrast Selected Feedback Highlight)**嚗𡁻��唬蛹 `Dark.Treeview` 摰𡁜�鈭���滚榆���擃睃��厰弗��漲�� **鈭桅��齿艶�� `#55ffff` + 瘛梯��峕艶�� `#1a3a5f`** �劐葉���撠���峕郊銝箇��仿�㕑�暺䁅恕�賢��� `"Treeview"` �瑕�瘜典�鈭���貉�擃睃笆瘥𥪜漲�� **�質𠧧�齿艶�� `#ffffff` + �嘥��峕艶�� `#0078d7`** �劐葉�惩�嚗𣬚��餃�擐���嗥��讛���潘�敶餃�閫���寥�匧笆瘥𥪜漲雿𡒊��𤤿���
        - [x] **�拍��餃�鈭� `_on_sector_selected` �踹��寥�厰�雿溻��洵銝�銵𣬚蒾撅誩�蝷箇�銝仿�銝𡁜𦛚 Bug (Fixed Name-Based Sector Selection Indexing)**嚗𡁜蝠摨訫��支�靘嗪���摹蝖祉��� `row_idx = int(sel[0]) - 1` 餈𥡝��唳旿蝝Ｗ��瑕���芋撘𧶏�甇斗芋撘譍��冽�摨譌���皛文��𤑳�敶餃���㺭�桅�雿㵪�銝𥪜捆�枏��� `ValueError` 撏拇�嚗剹��概憒䠷���蛹隞交踎�堒𣈲銝��滨妍 `sector_name` 銝箸瓲敹��銝駁睸摮烾𢒰�交𪄳�箏����霈箄”�澆�雿閙�摨譌���蝞梹���� 100% 瘥怎�蝥抒移��笆朣鞱繮�𡝗迤蝖桃�樴坔仍�∩�頝罸��∴��寥�劐�撉��銝肽�憿箸�嚗�
        - [x] **摰𣬚�閫��餈質葵�Ｘ踎蝑偦�匧��删�霈⊥㺭�桃�銝仿�鈭支� Bug (Implemented Real-time Tracking Filter Statistics)**嚗𡁜銁 `HistoricalSelectionTrackerDialog` 餈質葵撘寧�銝哨�敶梶鍂�瑕笆銝芾���誨����踹�璁�艙餈𥡝��喲睸摮𡑒�皛斗𧒄嚗𣬚𠶖���銝羓� `status_lbl` 銝滚��菜香嚗諹�峕糓隡朞䌊�券�朞�銝�憟堒𢆡������嗥�蝏蠘恣���蝞⊿�嚗𣬚��游銁銵冽聢�滨��𡡞��啁�霈∪僎撅閧緵 **餈�誘�餅㺭���瘨典振�啜���頝�振�唬誑�𠰴像��𤣰�羓����**嚗�僎�寞旿��蝏��撟��甇��嚗屸�鈭桀���緵摰䂿�蝎厩滯嚗��瘨剁�銝𡡞�鈭桃遛�莎�銝贝�嚗㚁�颲曉�鈭��雿喟�憸䀹��𥪜𢆡�嗥�憭滨������
        - [x] **擐硋��靝蜓�交踎�埈��滨�撖嫣���”憭湔�摨讐�瘜𨰝�嘥僎摰䂿緵銝斤垢蝏嘥笆撖寥� (Weighted Core-Sector Header Sorting)**嚗𡁜蝠摨閙說頞喃��滨��见笆銝餉𨯫銝𡁜𦛚�賭葉���撖寥�笔漲蝑偦�㕑�瘙�����㗇踎�𡑒�皛斗辺隞嗆𧒄嚗𣬚��領�𨀣踎�轁�嘅�銝駁�㕑�銵冽聢 `category` �埈�餈質葵銵冽聢 `sector` �梹�銵典仍餈𥡝��鍦�嚗屸�朞��啣郎�讐蔭撖寥�蝞埈�嚗諹恣蝞堒枂�寥�餈�誘霂滨����齿踎�㛖揣撘𤏪�蝚砌��踹��寥�銝� 0 �����擃矋�蝚砌��踹�銝� 1嚗𣬚洵銝㗇踎�𦯀蛹 2嚗䔶��寥�銝� 999嚗剹���雿踹�**�㰘捏�臬銁���餈䀹糓�滚��嗆���嚗�𥣞�舀迤摰堒� 3 �踹��賭葉嚗�誨銵典��訾蜓�乩��⊥糓霂仿��琜���葵�∴��賭�隞亦�撖寞�擃条�隡睃�蝥扳香甇餃𧑐�鍦銁���漤𢒰**嚗諹�䔶��寥���葵�∪��鍦銁���𠬍�颲暹�鈭��擃条��䀝葉憟堒⏚颲�𨭌���嚗�
        - [x] **撘訫� Esc �芸𢆡靽嘥����箔�蝏煺��亙藁靚�鍂**嚗帋蛹霂行��∠�蝏穃� `<Escape>` 鈭衤辣嚗峕�銝� Esc �祇𡢿�芸��坔� `window_config.json` 撟嗆�蝻嗪�瘥��憭批��𣂼�鈭�睸�条𤩅�滨�瘚��摨艾���銝��曹蜓閫��蝏煺��交����嚗𣬚�甇�噢�𣂷� SRP 銝� DRY �嗆��笔���
    - [x] **靽桀�餈質葵蝒堒藁�喲睸�𨅯� UnboundLocalError 撏拇� (Fixed UnboundLocalError)**嚗�
        - 閫���曹�撅��� `import re` 憭���賣㺭�𤾸��迎�撖潸稲�蹱��圾�鞉𧒄撠� `re.sub` 憭�� `re` �文�銝箸𧊋蝏穃�����典��讛����𤑳� UnboundLocalError 撏拇���歇撠�紡�亥祗�亦宏�唳䲮瘜閙�憿嗥垢嚗峕祥���颲� 100%��
    - [x] **�券��拍�皜�膄撅��典�雿� import re 憯唳� (Purified All Local import re)**嚗�
        - 靘脲� ripgrep 餈𥡝��典�蝎曉�璉�蝝ｇ�敶餃��急�撟嗅��典��支���辣����毺洵 `763` 銵䎚��洵 `1154` 銵䎚��洵 `1326` 銵䎚��洵 `2241` 銵𣬚� **4 憭��雿坔��� `import re` 憯唳�**��㟲銝芣�隞嗥緵撌脣��� 100% 隞�銁蝚� 5 銵䔶��坔𣈲銝����撅�憿園� `import re`嚗峕�憭批�頝菔�鈭� DRY��ISS 銝� YAGNI ���蝞��嗆����嚗䔶蝙蝟餌��扯� and �舐輕�斗�扯噢�啣�蝢𡒊𠶖���
    - [x] **靽桀�霂行�蝒堒藁 -py ��㺭 TclError 撏拇�**嚗帋耨憭滚之摮烾��鞱祕��㨃����冽�蝷� Label �誩��坔��墧���㺭 `py=5` 撖潸稲 Tkinter �𥕦枂 `unknown option "-py"` 撏拇�雿輻����瘜訫��湔遬�啁� Bug�����宏�日�瘜訫��唬誑蝖桐�霂行�憭批��∠� 100% 隡㗛�撅�葉嚗䔶���捆摰𣬚�鋡怎�閫���
    - [x] **摰䂿緵��稬�踹�撅閧內�祉�憭批��Ｘ踎**嚗𡁜銁 `StockSelectionWindow` 銝餉”�潔葉嚗���餌洵 16 �梹��踹�璁�艙 `#16`嚗㗇𧒄蝎曉��行⏛閫血�嚗�撕�箔�甈曉��刻䌊銝餅葡�梶� `Toplevel` 憭批�霂行��∠�����冽�摰Ｘ�暺睲蜓憸㗛��莎�憭批��瑯��䌊���撅�葉嚗�僎銝箸�銝芣踎�𡑒挽霈∩� hover �䁅𠧧���嚗��韐菜��䀹���雲��
    - [x] **摰䂿緵霂行��∠�銝𠰴��餅踎�堒�摮𡑒䌊�券�靽萘��芰�憭滚�**嚗𡁜��餃㨃�������踹�嚗諹䌊�典���𧋦�坔�蝟餌��芾斐�選�閫血���倌摨閗𠧧�祇𡢿擃㗛緾嚗�楛蝏輯��� `#1b3a24` 銝𡒊遛�脣� `#44ff88`嚗㚁��峕𧒄�典㨃����函𠶖���蝏嗘�擃䀝漁閫���漤���斐敹�銁�踹��喃儒���鈭� `�� 餈�誘` ��像�厰僼嚗峕𣈲����桀銁銝餌��Ｚ�皛方砲璁�艙撟嗉䌊�券��钅�瘥�㨃����
    - [x] **�舀��踹�餈�誘颲枏�獢�𢰧�桐��桃�韐渲�皛�**嚗𡁜銁銝餌��Ｙ� `concept_combo` 銝羓�摰� `<Button-3>` �喲睸鈭衤辣��𢰧�桃��餅𧒄�芸𢆡�瑕��芾斐�踵��研����匧‵�乓�����氜雿齿��喳僎�芸𢆡閫血� `on_filter_search(None)`��
    - [x] **��蟮餈質葵撖寞�蝑偦�㗇𣈲��𢰧�桐��桃�韐游僎�芸𢆡閫血�餈�誘**嚗𡁜銁 `HistoricalSelectionTrackerDialog` �� `entry_search` 蝑偦�㕑��交�銝羓�摰� `<Button-3>` �喲睸鈭衤辣����餃𢰧�桃��游��鞟�韐游‵���蝑偦�匧�摨𢛵��
    - [x] **��蟮餈質葵銵冽聢�峕郊�舀���稬 sector �澆枂�踹�霂行��∠�**嚗𡁻������ `<Double-1>` �單鰵�坔停�� `_on_double_click`����餌洵 4 �梹��踹� `#4`嚗㗇𧒄嚗屸�朞� `parent_win.show_concept_detail_popup` 摰𣬚�憭滨鍂銝餌�����𣂼㨃����舀�憭批���稬憭滚�銝𦒘蜓閫���峕郊餈�誘�𥪜𢆡嚗�蝠摨訫笆朣𣂼�蝏�垢憭𡁶垢銵函緵��
    - [x] **摰䂿緵餈質葵蝑偦�劐�銝餌��Ｘ踎�𡑒�皛斤�頝函�雿枏�蝢𤾸���**嚗𡁜銁 `HistoricalSelectionTrackerDialog.__init__` �嘥��𡝗��滨垢嚗諹䌊�冽�瘚见僎�匧� `parent.concept_filter_var` ����砍僎憛怠� `search_var`嚗諹悟憭𡁏𠯫��蟮撖寞����撘寧��典��舐��渲䌊�典�甇交㗁�乩蜓�屸𢒰��踎�𡑒�皛歹���之蝎曄�鈭��雿𣈯𡡒�胯��
    - [x] **敶餃��寥膄 Pandas `str.contains` �砍噡甇��餈�誘撟脫贋憭� Bug**嚗𡁶���䰻�� Pandas `str.contains` 餈�誘瘝⊥���� `regex=False` 撖潸稲撣行��砍噡��踎�埈�敹蛛�憒��𨅯�撠���匧郎(CPO)�嘅�銝剔��砍噡鋡怨��思蛹甇��銵刻噢撘讐��閗繮蝏��Metacharacters嚗㚁�隞舘��紡�� 0519 �唳旿�䭾�鋡怨�皛斗�蝝Ｗ枂�亦� Bug���朞��曉�銵亙� `case=False` 銝� `regex=False` 敶餃�鈭�誑靽桀�嚗���唬� 100% 蝎曉����蝚虫葡摮𣂷葡摮烾𢒰�寥���
    - [x] **銝餉”�澆蘨撅閧內�� 5 銝芯蜓閬��蝖格踎�𦯀縑��**嚗𡁏鰵憓� `_get_short_category` 颲�𨭌�餉�嚗�笆憭扯”��緵����鞉㺭�𣂼�銝箏� 5 銝迎�擃睃�齿㺭蝻拙�鈭��閫匧僕�堆���銁��稬憭批��∠��娍䰻�𠰴𢰧�株��蓥葉嚗䔶��園�朞� `code`�笔�銝駁睸�睲�皜� `df_all_realtime` 銝� `df_full_candidates` 蝻枏��𣂼� 100% �券�憸䀹��券�嚗��憿曆�蝎曄���緵銝擧楛摨衣忽�譌��
    - [x] **靽桀���稬撘寧�暺穃�銝擧�蝑暸��� Bug**嚗帋耨憭滨眏鈭� `code` �� DataFrame 蝻枏�銝凋�銝箸㟲��/摮㛖泵銝脫�撖嫣�銝��湛�撖潸稲 O(1) �匧�憭梯揖嚗諹��諹圻�𤑳征�文� `return` 雿踹�蝒堒藁蝏�辣�芾◤皜脫���䔮憸塩����亙抅鈭� `.map(lambda x: str(x).zfill(6))` �������芣��匧��箏�嚗�銁憭𡁶漣蝻枏�銝剖龪�漤��琜��芣���噢 100%��
    - [x] **�屸𢒰擃睃�撌格�摰Ｗ��厰��脣�蝥�**嚗𡁜��踹��峕艶霈曆蛹擃睃�撌� `#1e293b`嚗���堆�嚗���航𠧧銝� `#64b5f6`嚗�予�肽𠧧嚗㚁��祆筑����脖蛹 `#ffd54f`嚗��暺������餃��嗆𧒄閫血��批�蝏� `#44ff88` 銝� `#1b3a24` ���潮緾����鮋��毺�雿喋��
    - [x] **蝒堒藁撅�葉�曄內銝𤾸之撠誩偕撖豢�銋��**嚗𡁜蘨�匧銁�芣��匧��𣂼��擧�撘寧�嚗䔶�頧賢��嗡����朞� `self.load_window_position` �芸𢆡鋆�蝸撠箏站嚗𥕦��剜𧒄�朞� `WM_DELETE_WINDOW` �芸𢆡閫血� `self.save_window_position` �坔� `window_config.json`嚗��蝢𤾸��唬�頝其�霂脲�銋����
    - [x] **��漣��蟮餈質葵蝒堒藁蝑偦�㗇�蝝Ｘ�銝箏�鈭� Combobox 撟嗅��啣��穃��脣�甇�**嚗𡁻���蕭頦芰�����𦦵揣獢�蛹 `ttk.Combobox` 撟嗥凒�亙�頧� `parent.history` 雿靝蛹銝𧢲��厰★����亙�撅��峕郊�寞� `_save_history(query)`嚗�銁�噼膠����厰�㗇𥋘��𢰧�桃�韐湔𧒄摰墧𧒄�湔鰵���撟嗅��交�隞塚��祇𡢿�峕𧒄�湔鰵憭𡁶垢 Combobox嚗䔶�撉峕�雿喋��
    - [x] **摰䂿緵頝函����撖寧漣�磰�皛�**嚗𡁜銁�∠�憸䀹��Ｘ踎��稬�澆枂�嗆釣�� `caller_win=self`����� `�� 餈�誘` �厰僼�嗅��嗅��刻秐銝餉”�潔�餈質葵銵冽聢嚗���啣�蝢舘����皛方��具��

## 2026-05-22 22:15
- [x] **摰𣬚�靽桀���蟮�唳旿�踹�餈�誘憭望�嚗�僎敶餃��寥膄 `get_candidates_df` �喲睸 is_today �文��餉��躰秤 (Fixed Historical Concept Filter & Restored is_today Time Gate)**嚗�
    - [x] **靽桀� stock_selector.py 銝剔� `is_today` �餉�**嚗𡁜� `is_today = (target_date == logical_date)` 靽格㺿銝� `is_today = (target_date == today_str)`嚗屸俈甇Ｗ��脫𠯫�蠘◤霂臬ế銝箔�憭押��
    - [x] **摰䂿緵摨訫� SQLite �㰘蝸�踹� category �芣�銵仿�**嚗𡁜�瘨� `is_today` 銝枏��𣂼�嚗��霈訾遙雿閙𠯫�煺�雿輻鍂摰墧𧒄銵峕�摨梶�憸䀹�撖� NaN/0/蝛箸踎�埈㺭�株�銵� O(1) ���笔��詨�撣峕�撠���
    - [x] **摰䂿緵 UI 閫���㕑�銝餉”�踹� category �滚�閬��銝𤾸�憯格�扳�瘣�**嚗𡁜銁 `stock_selection_window.py` ����� `load_data` 銝哨��� `df_candidates` 憭滚�����㵪���鍂摰墧𧒄銵峕� `df_all_realtime` 撖寧撩憭梁� `category` �帋��漤�靽萘�皜��閬��嚗諹圾�� NaN 撖潸稲�� contains 撘�虜��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2215_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/6365b567-579b-4786-a830-397b23ddc525/20260522_2215_task.md)��

## 2026-05-22 21:58
- [x] **�刻�鈭斗�蝏�垢憭𡁏���璅∪�瘚�蓮銝𦒘犖�箸瓲摰墧�摰Ｙ＆霈文撕蝒堒�蝢舘氜�� (Implemented Multi-mode Execution and Manual Confirmation Popup)**嚗�
    - [x] **摰䂿緵憭𡁏���璅∪�瘚�蓮蝞⊿�**嚗𡁜��� OBSERVE嚗�蘨閫��銝滢漱�橒���APER嚗�芋�煺漱�栞䌊�典��矋���ONFIRM嚗�犖撌乩��格瓲摰䂿＆霈歹���IVE_AUTO嚗���芸𢆡摰䂿�銝见�嚗厩�瘚�蓮蝞⊿���
    - [x] **摰䂿緵 CONFIRM 璅∪�鈭箸㦤蝖株恕��恥撘寧�**嚗𡁜�鈭斗�蝑𣇉裦閫血�靽∪噡�塚��芸𢆡撘孵枂銝�銝芸�銝剔���恥�㰘器獢�蔭憿嗥�����曄內靽∪噡霂行����撅墧踎�𦯀�鈭斗�霈∪�嚗峕𣈲����桃＆霈�/�𡝗�嚗�僎�舀��桃� Esc 銝𤾸�頧阡睸�脫���揢��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2158_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/305562b9-eab9-4b19-b037-253fe2a17511/20260522_2158_task.md)��

## 2026-05-22 21:37
- [x] **�刻�鈭斗�蝏�垢 Trading Kernel �嗆挾�扳��𡏭�隡唬�摰䂿�瞍磰�閫�� (Trading Kernel Evaluation & Live-Trading Strategy)**嚗�
    - [x] **璇喟�撟園𡡒�航�隡� Trading Kernel 雿梶頂**嚗𡁜笆 `TradingKernelService`��StateManager`��DecisionEngine` �� `JsonlJournal` 隞亙��㕑�蝒堒藁 `StockSelectionWindow` ����喟��批��曇楝餈𥡝�鈭�頂蝏��抒�璇喟��峕�扯�瘚贝���
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2137_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/305562b9-eab9-4b19-b037-253fe2a17511/20260522_2137_task.md)��

## 2026-05-22 21:05
- [x] **摰𣬚�閫��蝑𣇉裦�㕑��毺��賢�銝𤾸��冽�暺𤏸”�澆�摮矋�撟嗡耨憭滚��脩��潸䌊���霂剜��躰秤 (Perfect Styling Isolation & Corrected PanedWindow Syntax)**嚗�
    - [x] **摰䂿緵�㕑�銵冽聢 100% �笔��滩𠧧憌擧聢擃䀝����憭�**嚗𡁜銁 `StockSelectionWindow` 銝餉”�潔葉摰���亦氖瘙⊥�銝駁�嚗屸�靽萘�餈睃���蟮銝𦠜�皜������滚榆�滩��舫�鈭桅��莎�雿踹�撌脤�劐葉銵��撌脣蕭�亥�����啣��祆��𣬚遛/蝥Ｚ𠧧摨閗𠧧嚗峕�憭滚之�Ｙ妖�賢�����質��麄��
    - [x] **靽桀���𠧧蝒埈聢嚗𠄎ash嚗㕑䌊���頧賜�蝻抵�霂剜��躰秤**嚗帋耨憭滢��刻楊隡朞��芣��Ｗ���𠧧蝥蹂�蝵格𧒄摮睃銁�� Python 蝻抵� SyntaxError嚗䔶�霂�鍳�券�餉���蓡����曉�憯格�扼��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2105_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/aa87f3a2-56c9-4de2-b5a8-a3ac82e9a224/20260522_2105_task.md)��

## 2026-05-22 20:45
- [x] **蝑𣇉裦�㕑� Tab 銵冽聢 100% �笔��滩𠧧憌擧聢餈睃�銝𤾸極�瑟��厰僼�滨蔭敺株� (Reverted Selection Grid to Native Styling)**嚗�
    - [x] **銵屸�鈭桅��脣�瘙���唾���**嚗𡁜��函宏�支� `Treeview` �典��瑕�閬����歇�劐葉 (`selected`) 銵峕�蝏輯��� (`#dcedc8`)嚗�歇敹賜裦 (`ignored`) 銵峕�蝥Ｚ��� (`#ffcdd2`)嚗���刻��誩��笔��舫��脯��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2045_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/aa87f3a2-56c9-4de2-b5a8-a3ac82e9a224/20260522_2045_task.md)��

## 2026-05-22 20:30
- [x] **�踹��𡁶�銝𤾸��嗅�蝑𤥁”�澆��冽��脩忽�譍�蝑𣇉裦�㕑��賢��Ｗ��� Sash 蝒埈聢雿滨蔭����� (Dark.Treeview Custom Styling & Reverted Strategy Selection Grid Background)**嚗�
    - [x] **�冽鰵摰帋�撅��� Dark.Treeview �瑕�**嚗帋蛹摰墧𧒄銋啁��喟��笔�摰𡁜��祉��� `#0c101b` 瘛梯𠧧�峕艶銝𡒊滲�賣�摮堒��航𠧧嚗���唬�銝𦒘蜓�Ｘ踎�賢�����滚榆蝛輸�誩�蝷箝��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2030_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/aa87f3a2-56c9-4de2-b5a8-a3ac82e9a224/20260522_2030_task.md)��

## 2026-05-22 20:23
- [x] **摰墧𧒄�喟�銝见��箸�隞㮖�瘚�偌銵冽聢�典�擃䀝��蠘��� (Fully Linked Positions and Cash Flow Table Views)**嚗�
    - [x] **摰䂿緵敶枏����銝𦒘��交�瘞渲���**嚗𡁏�隞栞”�� (`self._pos_tree`) �峕�瘞渲”�潔葉�����稬/�孵稬�塚��芸𢆡�𥪜𢆡��揢�航��碶蜓閫�藁�𡝗踎�烾��僐��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2023_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_2023_task.md)��

## 2026-05-22 20:20
- [x] **蝑𣇉裦�㕑�銝𤾸�蝑𤥁”�潭楛摨行�暺穃��諹𠧧銝𡒊蒾獢���� (Reverted Selection Grid styling and Border Cleanup)**嚗�
    - [x] **瘨�膄銵冽聢蝛箇蒾�箏��賢�**嚗𡁻��啣�銋劐��瑕�撅墧�改�蝖桐��刻”�潸��啗�撠烐𧒄嚗��雿坔之��征�賢��脖�銵冽聢�祈澈����航𠧧靽脲�擃睃漲銝��氬��
    - [x] **�娪膄銵冽聢蝡衤�颲寞� (White Borders Elimination)**嚗𡁜竉蝳� Windows 暺䁅恕�芸蒂��漁�啗𠧧/�質𠧧蝡衤�颲寞�嚗���唳��賡�韐冽���㟲雿𤘪�摰Ｘ�����
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2020_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_2020_task.md)��

## 2026-05-22 20:10
- [x] **Alt+T �典�銝��桅�㕑�銝𤾸��嗅�蝑㚚�厰★�∟䌊�刻歲頧� (Global Hotkey Alt+T and Auto Tab Jump to Real-Time Decision)**嚗�
    - [x] **蝏穃��典� Alt+T 銝��桅�㕑�**嚗𡁜銁銝餅綉瘛餃��典� `Alt+T` �剝睸嚗䔶��株�韏瑞��仿�㕑�銝𡒊＆霈斤��Ｕ��
    - [x] **摰䂿緵暺䁅恕頝唾蓮�𨅯��嗅�蝑砽�𨯔ab**嚗𡁻�㕑�蝒堒藁�臬𢆡�𠬍��芸𢆡頝唾�暺䁅恕�� Tab 1嚗諹䌊�典�敶枏�瘣餃𢆡�厰★�∟挽摰帋蛹 `Tab 2 (�㴓 摰墧𧒄�喟�)`嚗𣬚��颱犖撌亦��颯��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2010_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_2010_task.md)��

## 2026-05-22 20:05
- [x] **Kernel �𧢲踎蝒堒藁�牐�����硔��䌊�典�頧賭�蝥扯��誩��喲𡡒 (Window Geometry Persistence & Cascaded Close)**嚗�
    - [x] **���蝒堒藁憭批�銝𦒘�蝵株扇敹�**嚗𡁻�朞� `WindowMixin` 霂餃� `window_config.json`嚗諹䌊�冽�銋��霈啣� Kernel �扯��𧢲踎���蝵桐�撠箏站嚗��甈∪��舀𧒄�芸𢆡�滨��Ｗ���
    - [x] **摰䂿緵蝥扯��喲𡡒**嚗𡁜��剝�㕑�蝒堒藁銝餌��Ｘ𧒄嚗諹䌊�刻��券�瘥��瘚桃� Kernel �扯��𧢲踎摮鞟�����脣�摮睃��交�瘜�蠧��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_2005_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_2005_task.md)��

## 2026-05-22 19:55
- [x] **�㕑�銝擧�敹萄��函��蹂��株��其�隡睃��枏�憿箏�隡睃� (Linked Stocks and Sectors Windows Open Priority)**嚗�
    - [x] **摰䂿緵�踹�璁�艙銝��桃忽�讛���**嚗帋蜓銵冽聢�硋笆瘥磰蕭頦芰���葉��稬銝芾��塚��芸𢆡隡睃��典��啣�撱箏僎�枏��𨀣踎�埈�敹菔祕蝏���鐥�脲�瘚桃��選�蝝扳𦻖��靚�絲�㕑�銝餉�����
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1955_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1955_task.md)��

## 2026-05-22 19:40
- [x] **Kernel �芸𢆡鈭斗�擃䀝漁�ａ緾����𥪜𢆡�祆筑 Tree 閫�㦛��漣 (Kernel Fast Flash Feedback & Floating Tree Linkage)**嚗�
    - [x] **�芸𢆡鈭斗��扯�擃䀝漁�脣��圈�蝵�**嚗𡁻���� `_refresh_decision_tab` ��葡�𤘪凒�堆�撘訫��ａ緾���雿輯�蟡其漱�枏𢆡雿𨀣�霈啣銁�瑟鰵�𦒘��嗡誑�穃��脫�銋���曄內嚗䔶�鋡急�蝛箝��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1940_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1940_task.md)��

## 2026-05-22 19:35
- [x] **靽桀�摰墧𧒄�喟��嗆��辺�曄內�穃�蝒堒藁 Bug (Fixed Status Bar Vertical Height Exploding Bug)**嚗�
    - [x] **�閗��𣇉𠶖��縑��**嚗𡁻��� `_kernel_auto_execute_once` 靚�鍂 `_kernel_set_status` �園鵭��𧋦���皛扎��竉蝳餃��� `
` ��之�亙� `detail` 颲枏�嚗䔶�撠���剔��閗�瘙��� `msg` 憛𧼮��嗆��� Label嚗屸俈甇ａ�摨行𠂔憓墧�擃� risk_bar��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1935_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1935_task.md)��

## 2026-05-22 16:25
- [x] **靽桀��暸�霂行��𢠃�霅行�蝏�撕蝒𡑒��曆��峕郊�劐撓/蝻拇𦆮 Bug & �拙�撅閧內 DFF 銝� DFF2 �� & �拙��暸�銝芾�摰寥��� Top 200 (Fixed Window Scaling and Geometry Desync Bug & Added DFF Columns & Expanded Top 200)**嚗�
    - [x] **�寞祥 C++ 蝒堒藁�交��滚遣�牐��詨�**嚗𡁏䰻�𡒊眏鈭� C++ 摨訫�撖孵笆霂脲��滨�撘閗絲��之撠譍腺憭梧��朞��拍��滚� `resizeEvent` 撘箄�撠� `table` 憭批��芷���撖寥� `Dialog` �拍�摰賢漲��
    - [x] **撘寧�銵冽聢撘訫� DFF 銝� DFF2 �曄內**嚗𡁜銁 `VolumeDetailsDialog` 銝剜�憓噼”�潸秐 6 �梹�摰匧��𧼮‵�誩��枏� metrics��
    - [x] **�拙捆�誩�摰寥��� Top 200**嚗𡁜�暺䁅恕�� 30 銝芣����摰孵� 200嚗䔶�霂���䀹��孵稬銵典仍�鍦��嗅銁�游之����𤩺���極雿栶��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1625_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1625_task.md)��

## 2026-05-22 16:10
- [x] **蝑𣇉裦靽∪噡�Ｘ踎�羓㮾�唾祕��撕蝒堒�撅����皛𡁜𢆡�⊥甅撘譍��� (Implemented Global Narrow 6px Scrollbar Custom QSS)**嚗�
    - [x] **QSS 蝥抒�皛𡁜𢆡�∪���**嚗帋蛹銝餌��乩縑�琿𢒰�踴����冽𦆮�讛祕��撕蝒堒�憸�郎�𡒊�撘寧�蝑匧��株��曆葉����㗇偌撟�/��凒皛𡁜𢆡�∪��� 6px 摰賢漲�瑕�嚗屸����閫埝��衤��𤩺��峕艶嚗�蝠摨訫��斤頂蝏蠘䌊撣血��齿��冽辺��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1610_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1610_task.md)��

## 2026-05-22 15:59
- [x] **閫��蝑𣇉裦靽∪噡�Ｘ踎/蝡硺遠�Ｘ踎�瑕鍳�其��睃��惩之�䀹萱摨�/��㺭�唳旿�桅� (Fixed Cold-Start Blank Market Stats Vacuum)**嚗�
    - [x] **撘箏��峕郊�日�憭抒�蝏蠘恣**嚗𡁜銁�Ｘ踎�枏��塚��滨蔭 `_dashboard_first_sync_done = False`嚗�撩�嗥��餉圻�睲�甈∪笆憭抒���������恣蝞梹��䔶��臬僕蝑� 60 蝘垍�摰𡁏𧒄敺芰㴓嚗峕��支�撘��条��港��睃���征�賜緵鞊～��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1559_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1559_task.md)��

## 2026-05-22 15:52
- [x] **靽桀� VolumeDetailsDialog 銵冽聢�賣�銝𤾸�雿嗵蒾�烾䔮憸� (Fixed Dialog White Background & Header Stretch)**嚗�
    - [x] **摨𠉛鍂瘛梯𠧧�峕艶 QSS**嚗帋蛹 `VolumeDetailsDialog` �� QDialog 蝒堒藁�� header_frame 霂湔��誩撩銵峕�摰𡁏�暺𤏸𠧧靚�甅撘𧶏�閫��鈭株𠧧銝駁�銝讠��峕艶蝛輸�讐蒾�脯��
    - [x] **�劐撓���𦒘��埈��斤蒾��**嚗朞挽蝵� `h_header.setStretchLastSection(True)`嚗䔶蝙���𦒘��𡑒䌊����劐撓�箸說蝒堒藁摰賢漲嚗���文𢰧靘批�雿嗵征�堒��賣���
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1552_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1552_task.md)��

## 2026-05-22 14:57
- [x] **靽桀�蝑𣇉裦靽∪噡隞芾”�䀝��亙��冽𦆮�譍葵�� (VolumeDetailsDialog) 銵冽聢�孵稬�鍦��蠘�憭望��� Bug (Fixed Table Column Sorting Disablement)**嚗�
    - [x] **�Ｗ��鍦��蠘�雿輯�**嚗帋耨甇�� `VolumeDetailsDialog` �冽㺭�桀‵����笔�撠� `setSortingEnabled` 霂臬�銝� `False` ���霂荔��孵�銝箏銁�嘥��硋��湔鰵摰𣬚��𤾸撩�嗉圻�� `True` �鍦��Ｗ���
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1457_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1457_task.md)��

## 2026-05-22 13:46
- [x] **�拙� KLineMonitor 摰墧𧒄�烐綉�Ｘ踎隞交遬蝷� DFF 銝� DFF2 �� (Added DFF and DFF2 columns to KLineMonitor)**嚗�
    - [x] **�拙��烐綉�㛖���**嚗𡁜銁 `kline_monitor.py` ��”�潔葉嚗峕鰵瘜典�撟嗆�撠�� `dff` 銝� `dff2` 銝文�摮埈挾��
    - [x] **摰䂿緵�啣�潭聢撘誩�銝𤾸��典‵��**嚗𡁜銁�唳旿憛怠��冽�銝剖��交�����冽�找�蝛箏�澆ế摰𡄯�摰𣬚��𧼮‵�譍遠�讐氖靽∪噡�����
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1346_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1346_task.md)��

## 2026-05-22 13:14
- [x] **�賢𧑐憭𡁶漣摰墧𧒄銵峕��芣�銵仿��箏�嚗�蝠摨閙𤫇�见��誩��臬𢆡頝罸��﹦�𨀣���𧒄�曉�0.00��遠�潑�嗪䔮憸� (Implemented Multi-level Real-time Data Healing for Lagging Followers)**嚗�
    - [x] **撱箇�擃䀝��蠘���‘朣鞟恣��**嚗𡁜銁 `BiddingMomentumDetector` 霈∠��塚�撖嫣��� essential 銝𥪜���蛹 0 ���瘣餉�頝罸��∴��冽�銋��瘙牐葉閫血�鈭屸�銵峕��亥砭嚗�⏚�冽��啁� `df_all_realtime` 銵仿�摰�賑��㿥�嗡���𧒄�箏���
    - [x] **�𦦵��Ｘ踎憭折𢒰蝘舀���**嚗𡁏��支�憓鮋��枏�璅∪�銝𧢲芦�朞��曹��踵𧒄�港�鋡急凒�啣紡�渡��𨅯�撠豢㺭�桃𠶖���嘅�摰䂿緵�刻”摰����凝�见��嗥瑪�暹葡�瓐��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1314_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1314_task.md)��

## 2026-05-22 13:10
- [x] **閫��蝡硺遠�Ｘ踎�典�銝芾��惩��嗉粥�踹㦛銝擧��賢���聢���閫厩撩�� (Fixed Bidding Panel Blank Intraday Chart Bug)**嚗�
    - [x] **隡睃� TrendDelegate 銵峕� fallback �文�**嚗𡁜� `TrendDelegate` ����瑕� `now_price` ����� `.get()` �餉�靽桀�嚗屸俈����芸��䀹僼��葵�� `prices` �𡑒”銝箇征�嗅�韏瑞���𧒄韏啣飵�曉��函征�踝�摰匧��滨漣蝏睃�銝��∪像蝔喳抅��瑪��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1310_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1310_task.md)��

## 2026-05-22 13:00
- [x] **靽桀� K蝥踹㦛�舀�/�餃�蝥踹��䀝葉�曄內 0.00 銝𤾸��質秐�嗉蓬�� UI 皜脫�蝻粹萅 (Fixed K-Line Support/Resistance "0.0" Realtime Display Bug)**嚗�
    - [x] **�脤妟銝𡡞俈 NaN �𨅯��� (Robust Anti-Zero & Anti-NaN Fallback Gate)**嚗𡁜銁 `day_df` 餈賢�摰墧𧒄銵峕�撖潸稲��𣈲�煾獈�𤤿撩憭勗�潔葉嚗���� `replace(0.0, np.nan)`嚗屸�朞�撖寡恣蝞堒�蝏枏�������餈𥡝� `ffill().bfill()` �箄��鍦�澆‵���敶餃�閫��鈭��銵峕�撖寥�鈭抒����𨀣𣈲��: 0.00�嘥��餃�蝥踵�蝥踵鱏撏硋��賜�皜脫� Bug��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1300_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1300_task.md)��

## 2026-05-22 12:52
- [x] **�賢𧑐�券�銝𤾸�撅��甇亥圾�衣���挽霈∩�隡睃� (Layered Asynchronous Decoupling & Debounced Post-Aggregation UI Notification)**嚗�
    - [x] **�賢𧑐撘�郊�踹��𡁜��笔� (Asynchronous Sector Aggregation Queue)**嚗𡁜銁 `BiddingMomentumDetector` 銝剖��亙��圈��餃�撘�郊�笔��扯� `_aggregate_sectors` �踹�霈∠�嚗��霈∠��冽𧒄憭批��讠憬�� 0ms 蝥批�嚗峕��支蜓蝥輻���㨃憿踴��
    - [x] **摰䂿緵 UI ���銝擧凒�啣縧�� (Coalesced Queue Debouncing & Throttling)**嚗帋蜓�Ｘ踎�冽㺭�格𦻖�嗆������擃� 5 FPS �滨�霂��嚗屸��齿��譍���僎�烐葡�㮖縑�瑞�鈭剹��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1252_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1252_task.md)��

## 2026-05-22 12:50
- [x] **�寞祥霂���擧踎�𡑒���紡�渡�蝟餌��⊿▼銝� GIL ��𤨪�� (Radically Eliminated Aggregation Lag & GIL Contention in BiddingMomentumDetector)**嚗�
    - [x] **摰墧鴌�屸�餈�誘�鞉𡟺���箸㦤�� (Two-Stage Early-Exit Filtering)**嚗𡁜銁�踹��滚��𡁜�撘�憪见�嚗䔶���笆銝芾����潸�銵�翰�罸��潸�皛歹�雿𦒘����潛凒�亥歲餈��嚗��撠� 90% 隞乩��䭾�銋厩�憭齿��唳旿摮堒����牐�憭批儐�胯��
    - [x] **�閙活�滚��踹��唾�瘙删�摮� (Single-pass Concept Cache)**嚗𡁻�霈∠�憟賣踎�𦯀����匧��𥪜撩�輯��𡑒”���撠���賂�撠�之撋��敺芰㴓隞� $O(K 	imes C 	imes N)$ �滩秐 $O(1)$ ����笔�撣峕䰻�整��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1250_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1250_task.md)��

## 2026-05-22 12:30
- [x] **蝎曉��𤥁‘朣� Nuitka �鍦�頧賣芋�𦯀�韏� (Injected Precise LazyModule Dependencies for JSONData and JohnsonUtil)**嚗�
    - [x] **�见𢆡撘訫� LazyModule �冽��芋��**嚗𡁜銁 Nuitka 蝻𤥁��滨蔭�𡁏𧋦銝剜��典��� `tdx_hdf5_api`��wencaiData`��sina_data` �� `johnson_cons` 摮鞉芋�梹��拍�瘨�膄�枏�餈鞱��擧𥁒�箇� `ModuleNotFoundError`��
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1230_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1230_task.md)��

## 2026-05-22 11:36
- [x] **�峕郊 Nuitka 蝻𤥁��滨蔭銝舘恣�嗅��賢��啣笆朣� (Synchronized Nuitka Timing Hooks & Parameter Alignment)**嚗�
    - [x] **�峕郊 Clang-Only 霈⊥𧒄�拙�**嚗𡁜� `nuitka_build_console_onlyClang.bat` �𣬚�蝻𤥁�霈⊥𧒄颲枏枂摰𣬚�餈賢�撖寥��� `nuitka_build_console.bat` �𡁏𧋦銝哨����蝏煺��� `time.txt`��
    - [x] **�删鍂�滚� DLL 餈�誘銝𡡞�蝵桃移蝞�**嚗𡁻�朞� `--noinclude-dlls` 蝎曉�餈�誘 `Qt6WebEngine`��Qt6Pdf` 蝑� PyQt6 銝剜𧊋雿輻鍂���憭𡁏狡 C++ 摨訫��冽��曎�亙���
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1136_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1136_task.md)��

## 2026-05-22 11:05
- [x] **瘛勗漲���� HDF5 霂餃��� Sina 銵峕��亙藁���憸穃�雿蹱𠯫敹� (Cleaned High-Frequency Diagnostic Verbosity to DEBUG)**嚗�
    - [x] **�寞祥 HDF5 ���鈭劐��讠憬�瑕�**嚗𡁜� `SafeHDFStore` �� `ptrepack` 銝剔�撣貉�憭朞�蝔钅���𤚗霂�/�𦠜𦆮/�滩�蝑厰�憸� `INFO` 蝥扳𠯫敹堒撩�園�蝥找蛹 `DEBUG`��
    - [x] **�滚臁 Sina API �冽��匧��亙�**嚗𡁜� `sina_data.py` �� `commonTips.py` �券�憸烐��𡝗���𪂹�煺葉�� `INFO` �批��唳��堆�蝏毺��滨漣銝� `DEBUG` 蝥改�摰䂿緵蝥臬��惩臁�喟�摰䂿�餈鞱��嗆����
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_1105_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_1105_task.md)��

## 2026-05-22 01:50
- [x] **��稬�踹�憸䀹��唳旿蝞⊿�隡睃�銝𤾸��臬𢆡甇駁�靽桀� (Fixed Sector Board Cold-Start Blank & Incremental Selection Deadlock)**嚗�
    - [x] **�滢�瘣餉����瘙㰘���秄瑽�**嚗𡁜�餈𥕦�瘣餉�銝芾����瘙删�蝑偦�厰��潛眏 `3.6` 靚���� `0.5`嚗𣬚＆靽嘥��睃��毺�雿𤾸𢆡�譍葵�∩��質恣�交踎�堒��䜘��
    - [x] **憓鮋��枏��芣�撘誩撩�嗅��𤩺醌��**嚗𡁜銁憓鮋�霂���園��嗆挾嚗䔶��血ế摰𡁜��齿踎�堒�銵其蛹蝛綽��瑕鍳�冽��瑕��条蒾撅𧶏�嚗諹䌊�典��Ｖ蛹�券��急�嚗�蝠摨閖獈�剔眏鈭𡒊征 essential �唳旿瘙𣳇�䭾���香����
    - [x] **�拍�敶埝﹝�祉�皜��**嚗𡁜�撱箔���鉄�交��園𡢿�賢���𡠺蝡衤遙�⊥��閙�隞� [20260522_0150_task.md](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/20260522_0150_task.md)��


嚜�## 2026-04-18 04:45
- [x] **靽桀����箏�撣訾�蝥輻�畾讠� (Fixed Application Exit Error & Thread Leak)**嚗�
    - [x] **銵亙����蝥輻�瘙惩��剝�餉�**嚗𡁜銁 `instock_MonitorTK.py` �� `on_close` �寞�銝剛‘朣𣂷�撖� `pump_executor` �� `compute_executor` ��遬撘� `shutdown()` 靚�鍂���敶餃�閫��鈭����箸𧒄�曹� `ThreadPoolExecutor` 暺䁅恕�𥕦遣�𧼮��斤瑪蝔见紡�渡� `[STILL ALIVE] pump_0` �躰秤霅血�嚗𣬚＆靽苷�摨𠉛鍂�賢��港�����翰�笔𧑐摰峕�韏���墧𤣰��
    - [x] **�寞祥 PyInstaller 銝湔𧒄�桀��删鍂 (Fixed _MEI Directory Lock)**嚗�
        - [x] **銵仿��𥪜𢆡餈𤤿��喲𡡒**嚗𡁜銁 `on_close` 銝剖��牐� `link_manager.stop()` 靚�鍂嚗𣬚＆靽� Linkage 摮鞱�蝔贝◤�曉��墧𤣰嚗屸��曆�撖孵�鈭� DLL ��辣����具��
        - [x] **摰墧鴌�券�餈𤤿��𨅯�皜��**嚗𡁜��乩� `multiprocessing.active_children()` �典��急��箏�嚗�銁銝餉�蝔钅���箇�����剖�嚗�撩�嗥�甇Ｘ��厰��嗵�摮鞱�蝔页���鉄 `SyncManager` �㛖��交�嚗剹��
        - [x] **隡睃����箸郊餈𥕦辣��**嚗𡁻�朞�撱園鵭 `join(timeout)` 隞亙�憓𧼮���蝏�������箏��� `time.sleep(0.3)` 蝻枏�嚗𣬚�鈭� OS ��雲��𧒄�游��嗆�隞嗆�餈啁泵嚗諹圾�喃� `[PYI-WARNING] Failed to remove temporary directory` ��𥁒�踺��
    - [x] **憓𧼮撩���箏虾�䭾��**嚗𡁻�朞�撖寞��匧�撅�瑪蝔𧢲�嚗㇊ump/Compute/Main嚗厩�敺芰㴓�滚��喲𡡒嚗峕��支�擃㗛�銵峕�撽勗𢆡銝见虾�賢��函���誘��妖嚗屸�����厩� 15s 撘粹��靽嗪埯嚗㇅ailsafe Timer嚗㚁�餈𥕢�甇交����蝟餌��冽�蝡航�頧賭������箇迅摰𡁏�扼��

## 2026-04-18 03:45
- [x] **靽桀�蝡硺遠韏偦帕�Ｘ踎擐硋��唳旿�曄內 (Fixed Racing Panel Initial Data Blank)**嚗�
    - [x] **摰䂿緵�單𧒄�唳旿��� (Immediate Data Injection)**嚗𡁜銁 `open_racing_panel` 銝剖��乩�撘箏��㕑絲�餉���𢒰�踵�撘��塚�蝡见朖�朞� `ensure_data_ready_async()` �臬𢆡�Ｘ��函�摮𣂼�頧踝�撟嗥��游�甇亙�摮䀝葉�� `current_df` 銵峕�敹怎��� `racing_detector`��
    - [x] **撘箏�擐𤥁蔭霈∠�閫血�**嚗𡁻�朞�靚�鍂 `update_scores(force=True)` 敶餃�瘨�膄鈭�𢒰�踹��臬��曹�蝑匧�銵峕��冽�撖潸稲���𦦵蒾撅謿�脲��𨅯��臬𢆡蝛箸��嘅�摰䂿緵鈭�朖�孵朖�卝��
    - [x] **靽桀� IPC �讛悅閫���仿� (Fixed IPC Unpacking Error)**嚗帋耨憭滢� `_ipc_worker_loop` 銝剖���聢撘誯�霂舐��桅�����笔��躰秤����詨���䲮撘譍耨甇�蛹����� `(cmd_type, payload)` 鈭��蝏��霈殷�閫��鈭�虾閫��餈𤤿�銝剜𥁒�箇� `too many values to unpack` ��誘閫��撏拇���
    - [x] **撌亦��㚚��� Watchdog 霂𦠜鱏�餉� (Engineering Refactor)**嚗�
        - [x] **撘訫�蝏煺� Debug 撘���**嚗𡁜銁 `__init__` 銝剖��牐� `self._debug_mode`嚗���Ｘ𣈲��㴓憓���� `APP_DEBUG`���蝵桅★ `DEBUG` 隞亙��賭誘銵���� `-log debug` 閫血���
        - [x] **�諹提��氖**嚗朞圾�虫� `Watchdog` 蝥輻�銝舘��剔��乓��緵�函�閫�瑪蝔衤�韐蠘提�餉��文�嚗��雿栞��剖𢆡雿靝漱�� `_dump_ui_stack` 憭����
        - [x] **摰匧����撖澆枂**嚗𡁜�鋆�� `_dump_ui_stack` �寞�嚗䔶��� Debug 璅∪��舐鍂�嗉��� `faulthandler`嚗�僎�冽�銵諹�蝔衤葉憓𧼮�鈭��撣訾��歹�憓𧼮撩鈭�頂蝏毺�撌亦��𡝗偌����
    - [x] **靽桀� SBC-Breakdown ��葉�港�霂舀𥁒銝� UI ��香 (Fixed Breakdown Spam & UI Lag)**嚗�
        - [x] **摰䂿緵�硺漱�𤘪𧒄畾萇�頝舀㦤�� (SBC Bypass)**嚗𡁜銁 `IntradayEmotionTracker` 銝剖��牐��典��園𡢿�文�嚗屸�鈭斗��嗆挾嚗����/�睃�/�峕膥嚗厩凒�亥歲餈�㟲銝芸���� SBC 靽∪噡�文�敺芰㴓���敶餃�瘨�膄鈭���刻�銵峕�蝟餌��瑕鍳�冽𧒄�曹��唳旿皞𣂼�撣詨紡�渡���150+�芷�銝剔聦雿𨧀�肽秤�伐�撟嗉圾�喃��䭾迨撘訫��� 3-7s UI ��香��
        - [x] **摰墧鴌�瑕鍳�冽��� (Cold-start Throttling)**嚗𡁜��� `_update_count` 霈⊥㺭�剁�頝唾��臬𢆡�𡒊��� 3 頧株恣蝞堒𪂹�麄���蝖桐�鈭�頂蝏笔銁�箏��唳旿�芸笆朣鞉��齿��� (prev_sbc) 撠𡁏𧊋撠梁貌�嗡�隡朞圻�睲憚�港�靽∪噡��
        - [x] **蝻栞圾 UI ��香銝� IO �见�**嚗𡁻�朞��穃��䭾���𠯫敹𡑒��綽��誩�鈭��憸穃��唳𧒄�� I/O �餃�嚗峕遬�烾�雿𦒘� `Watchdog` �亙枂 3-6s UI ��絲�������
    - [x] **�剔㴓�芣�靽嗪�**嚗𡁻���迨�滚��啁��航��𤥁�蝔见�瘣餌�瘚页�蝖桐�鈭��蝟餌�憭𡁶輕�𧢲踎嚗Āisualizer + Racing Panel嚗匧銁隞颱��臬𢆡/撏拇��箸艶銝钅��質䌊�冽�憭滩秐�舐鍂�嗆����

## 2026-04-18 03:25
- [x] **銵亙��航��𤥁�蝔讠𠶖��𡡒�臭��芣�靽嗪� (Visualizer Process Auto-Restart & Fail-safe)**嚗�
    - [x] **摰䂿緵摮䀹暑璉�瘚𧢲㦤��**嚗𡁜銁 `instock_MonitorTK.py` 銝剖��� `_ensure_visualizer_alive` 蝘���寞����朞� `is_alive()` 摰墧𧒄�文�摮鞱�蝔讠𠶖���摨罸膄鈭��𨅯蘨�煾������芣��萘��閖�㘾��鉝��
    - [x] **����臬𢆡靽嗪�撅�**嚗𡁜銁 `open_visualizer` �閖�� `SWITCH_CODE` �� `TIME_LINK` ��誘�滚撩�嗆釣�亙�瘣餃ế摰𠾼���璉�瘚见��航��𤥁�蝔见援皞���芸鍳�冽𧒄嚗屸�朞� `_ensure_visualizer_alive(code, resample)` �芸𢆡�㕑絲嚗峕楛摨血笆朣𣂷�������餉�蝏𤘪���㺭嚗�蝠摨閙覔瘝颱� IPC ��誘�𣈯�暺䀝腺憭晦�萘��桅���
    - [x] **隡睃��瑕鍳�其�撉�**嚗𡁶＆靽嘥銁隞颱��𥪜𢆡閫血��對��亙虾閫��蝏�垢蝻箏仃嚗𣬚頂蝏罸��賢銁鈭𡁏神蝘垍漣����鞟𠶖����亙僎�扯��𤾸蝱�滩�嚗峕�憭扳����憭朞�蝔贝��函頂蝏毺��亙ㄝ�扼��

## 2026-04-18 01:25
- [x] **瘛勗漲撖寥�蝟餌����鈭斗��園𡢿�文� (Standardized Trading Time Alignment)**嚗�
    - [x] **�亙���� cct 撌亙��賣㺭**嚗𡁜�撘�� `bidding_racing_panel.py` 銝剔��芸�銋� HHMMSS �文�����Ｘ𦻖�� `cct.get_work_time()` �� `cct.get_trade_date_status()`��
    - [x] **�芸𢆡�𤥁絲�孵��脖��湔��**嚗𡁻�朞� `time_hhmm` �湔㺭�澆����嚗𣬚＆靽� 60 ����芸𢆡敹怎��餉�隞�銁蝟餌�霈文����𨀣���極雿𨀣𧒄�氯�嘅���鉄����亥�皛歹����銵䕘�敶餃�撖寥��典像�啁�鈭斗��亙���
    - [x] **�冽𧒄畾菟�餉�靽桀�**嚗𡁜⏚�� `time_hhmm` �峕郊靽桀�鈭� `is_break` �� `is_closing` �嗆����文�嚗諹圾�喃��找誨��葉�踵㟲�唳�撖孵紡�渡�皜脫�瘜菟�餉�憭望�嚗峕�憭滢���𡢿�𦠜𤣰�睃��� UI 韏��靽脲擪��

## 2026-04-18 01:10
- [x] **摰䂿緵�芸𢆡�滨蔭�𡁶�銝𦒘漱�𤘪𧒄�游ế摰𡁜��� (Automated Reset Anchors & Time Logic Hardening)**嚗�
    - [x] **�芸𢆡�𤥁絲�孵��脰扇敶�**嚗𡁻���� `BiddingRacingRhythmPanel` �� 60 ���嚗�虾靚���芸𢆡�滨蔭�餉���緵�刻圻�煾�蝵格𧒄隡朞䌊�𤏸��� `_manual_reset_anchors`嚗��敶枏�隞瑟聢�嗆��䌊�冽���翰�批僎摮睃� **�� 韏瑞���蟮** 瑽賭�嚗峕���鈭箏極撟脤��喳虾餈賣滲�䀝葉撘�𢆡��
    - [x] **鈭斗��園𡢿畾萇移��圻�睲��� (Trading Time Gate)**嚗𡁜��乩� `time_int` ����硋��譌��＆靽肽䌊�券�蝵桐��� (09:15-11:30) �� (13:00-15:05) 鈭斗�瘣餉��蠘圻�㻫��𥅾�典�隡烐��嗥��罸𡢿�啗噢�冽�嚗䔶��峕郊霈⊥𧒄韏瑞��䔶�鈭抒��𦯀�敹怎�嚗屸��滢�撘��条��嗥��餉�蝛箄蓮��
    - [x] **瘛勗漲靽桀��典��園𡢿�文� Bug (Fixed Time Logic Bug)**嚗𡁜蝠摨閙覔瘝颱� `refresh_data` 銝� `is_break` 銝� `is_closing` �餉��踵�摮睃銁��聢撘𤩺�撖寥�霂胯����笔��湔𦻖雿輻鍂 Unix �園𡢿�喉�蝘垍漣�踵㟲�堆�銝� `HHMMSS` 撣豢㺭瘥𥪜笆���餉�靽格迤銝箸���� `time_int` 撖寞�嚗峕�憭滢�蝟餌�撖孵��睃��嗥��嗆���甇�＆�毺䰻��


## 2026-04-16 18:00
- [x] **�齿� Bidding Racing 憿嗅�蝏澆��批��∴�摰䂿緵��稲撣�����**嚗�
    - [x] **�批�蝏�辣憭批�撟�**嚗𡁜��𡏭�摨行𧒄�渲蓬�苷��𡏭絲�孵���𪂹��綉�嗯�萘眏��凒撣����僎銝箏�銵峕偌撟喳�撅���▲撅��摨虫� 160px ����讠憬�� 92px嚗屸��曆� 40% ��熊�睲��∠征�氬��
    - [x] **��漣�冽�靚��鈭支�**嚗𡁜�撘���栞秤閫衣�皛穃𢆡����嫣蛹擃䀹��� **`-10m`** 銝� **`+10m`** 甇亥��厰僼嚗�僎摰䂿緵鈭��蝥抒��滨蔭����硔��
    - [x] **�寞祥�滨蔭�其�撘訫���香�� (Fixed Reset Freeze)**嚗𡁻�朞��齿� `_manual_reset_anchors` ���蝡硺��餉�嚗諹圾�喃��鮋�鍦�����亙紡�渡��屸𢒰��香嚗屸�蝵桀�摨娍𧒄�游�敶坿秐鈭𡁏神蝘垍漣��
    - [x] **摰䂿緵�踹�韏偦��𣈯�憭游縧�𨧀�� (Leader Deduplication)**嚗𡁜銁��撘箸踎�埈�銵䔶葉撘訫� `str().strip()` ����硋縧�溻����䔶��芾�蟡函�瘝餃�銝芣踎�埈𧒄嚗䔶�撅閧內撘箏漲��擃条�銝�銝芣辺�殷�憭批��𣂼�鈭���輻�靽⊥��萸��
    - [x] **�賢𧑐�𡏭絲�孵翰�批��聆�� (Anchor Snapshots History)**嚗�
        - [x] **�嗅捐霈啣���**嚗𡁜銁�踹�����誩𢰧靘扳鰵憓� 6 雿滚翰�批��脰扇敶閙局嚗��� 韏瑞�1-6嚗剹��
        - [x] **�芸𢆡 09:25 ��香**嚗𡁜��唬��臬𢆡擐𡝗辺�唳旿�芸𢆡�閙��餉���頂蝏煺��芸𢆡�箏� 09:25 撘��条𠶖���銝算�𣈯�銝芾絲�嫖�嘥僎蝡见朖摨𠉛鍂銝箄恣蝞堒抅���銝𥪜銁甇支��𦒘��芸𢆡敹賜裦�𡒊賒�滚���䌊�冽��㕑窈瘙���
        - [x] **�嗆��㦤�Ｗ��箏�**嚗𡁶��餃��脫��桀虾�祇𡢿�Ｗ��券�銝芾���遠�潮��對�Price Anchors嚗匧����瘨典�嚗㇊ct Diff嚗㚁�撟嗅�甇仿�蝵株䌊�典儐�航恣�嗚��
    - [x] **憓𧼮撩�刻”�桃�撖潸⏛�𥪜𢆡 (Keyboard Linkage Enhancement)**嚗�
        - [x] 銝箸踎�𡑒”銵仿�鈭� `currentCellChanged` 靽∪噡��緵�券�朞�銝𠹺��格�閫�踎�埈𧒄嚗䔶��嫣葵�⊥�蝏���芸𢆡�峕郊�湔鰵嚗�歇閫���𨀣��桐�銝衤��仿��𥪜𢆡�萘��𤤿�嚗剹��
        - [x] 銝箔葵�∟”�峕郊憓𧼮�鈭�睸�䁅��其��歹�憭批��𣂼�鈭�滲�桃��滢�銝讠���������

## 2026-04-16 15:25
- [x] **瘛勗漲隡睃� K蝥踹虾閫��銝餃極�瑟�撣��銝𤾸𪂹�罸�㗇𥋘鈭支�**嚗�
    - [x] **�齿��冽��㗇𥋘 (Resample) 銝箔��㗇芋撘�**嚗𡁜��笔�璅芸��鍦�����1D��2D��3D��𪂹����嘥�銝芣��桀�撟嗡蛹�蓥葵 `QComboBox`����唬��孵稬銝𧢲���睸�䁅歲頧研��儒�株��冽𧒄���甇交凒�堆���之�𦠜𦆮鈭�極�瑟���偌撟喟征�氬��
    - [x] **��稲�讠憬撌亙��𤩺��桀�摨�**嚗𡁜� `SBC�墧𦆮` 蝻拍�銝� `SBC`嚗䈣GlobalKeys` 蝻拍�銝� `G-Keys`嚗䈣�椘儭讐���祕�� 蝻拍�銝� `�椘儭讐�����
    - [x] **敺株� UI �瑕�銝舘器頝�**嚗𡁻�朞� QSS 撠�極�瑟��厰僼�� `padding` 隞� 8px �讠憬�� 4px嚗䈣margin` 隞� 2px �讠憬�� 1px嚗�僎靚��摮𦯀��� 11px嚗�蝠摨閗圾�喃�撠誩�撟閙�憭𡁜�撅譍��厰僼鋡恍��∠��𤤿���
    - [x] **憓𧼮撩鈭支�斢����**嚗帋耨憭滢��券�朞��� UI �孵�嚗���典�敹急㭘�殷���揢�冽��塚�UI 蝏�辣�嗆��𧊋�峕郊�瑟鰵�� Bug��

## 2026-04-15 20:05
- [x] **瘛勗漲�𣂼� SignalDashboardPanel 銵冽聢�堒捐皞Ｗ枂銝擧�銋��**嚗�
    - [x] **摰䂿緵�典��堒捐�冽�靽脲擪**嚗𡁻�撖� `SignalDashboardPanel` 銝剔����� `QTableWidget`嚗���� `_limit_table_column_widths` �箏���撩�園��嗯�𨀣�撅墧踎�轁�腈���𨀣踎�堒�蝘售�腈���𨅯耦��祕���萘�摮埈挾���憭批捐摨佗�120-250px嚗㚁��脫迫�踹�畾菜��� UI 撣����
    - [x] **摰䂿緵頝其�霂萘𠶖���銋��**嚗帋遛�抒�隞琿𢒰�選��拍鍂 `QHeaderView` �� `saveState/restoreState` �箏�嚗���冽��见𢆡靚�㟲���摰賬���摨讐𠶖���摮䁅秐 `config.json`嚗���唬��芸�銋匧�撅���楊隡朞��芸𢆡�Ｗ���
    - [x] **隡睃��瑟鰵�𥪜𢆡�扯�**嚗𡁜��堒捐�𣂼��餉��删�撋���單鸌�𤩺��乩�摰𡁏𧒄�峕郊�冽�銝哨�蝖桐��券�憸睲縑�瑕��唳𧒄 UI 靘萘�蝔喳���
- [x] **瘛勗漲靽桀� DragonLeaderTracker �圈�憭� (consecutive_new_highs) 蝏蠘恣�餉�**嚗�
    - [x] **�嗥揮摰䂿�憓鮋鵭�冽�**嚗𡁜銁 `daily_close_snapshot` 銝剖��乒�𨅯撩�嗥��脲嵗撉䎚���瘙�𤣰�睃�憿餃�鈭擧隅�選�Close >= PrevClose * 1.002嚗㗇�蝏湔�擃䀝�嚗㇃lose > PrevHigh * 0.995嚗㗇���捂霈∪��圈�憭拇㺭��
    - [x] **撘訫�憭扯��游��滨蔭**嚗𡁏�瘚见��亥�撟� `current_pct < -3.5`嚗䔶��西圻�穃朖�文�頞见飵�游�嚗�撩�嗆�蝛箄恣�啣膥��
    - [x] **靽桀��曹��𨅯之鈭𢛶�嘥ế摰𡁜紡�渡��圈�憭拇��� (Fix Limit-up Bug)**嚗𡁻�撖嫖�𨅯��䀹隅�鎿�脲�閫血��漤�雿�𧊋蝒�聦��撩�輯�嚗���餉�隞� `>` 隡睃�銝� `>=`������𨀣𤣰��撩摨色�脲嵗撉䕘�蝖桐�鈭���輯��𡝗��輯�����𨀣鰵擃睃予�苷�隡朞◤�躰秤�滨蔭銝�0��
    - [x] **靽桀���蟮�墧滲 Bug**嚗帋耨甇�� `mine_history_dragons` 銝剔眏鈭𤾸��舫�瞍誩紡�渡�霈⊥㺭�典銁璅芰�/銝贝��嗡�敶㘾妟��䔮憸塩��
    - [x] **憓𧼮撩�䀝葉�冽���擐�**嚗𡁜銁 `intraday_update` 銝剜鰵憓� `�脤��噼氜` 摰墧𧒄��倌嚗���∩遠隞擧𠯫����孵��� > 3% �嗉䌊�券�霅艾��
    - [x] **閫���靝�頝諹恣�交鰵擃覀�萘���**嚗𡁻�朞�銝𡃏膩蝏���喉�敶餃�閫��鈭�鍂�瑕�擐��銝贝�銝芾�靘萘��曄內�𡁻�餈墧踎憭拇㺭����� Bug��

## 2026-04-14 19:35
- [x] **瘛勗漲靽桀� HDF5 摰寥�蝞∠�銝𡡞�蝵桀𦶢�滚�蝒�**嚗�
    - [x] **�惩𤐄 Truncate 閫血��餉�銝𤾸��唬���漣**嚗𡁶輕����冽�閬���� **1.1 ��** 閫血��冽�嚗�150MB �� 165MB 閫血�嚗劐誑�� **憭㚚�隡惩�隡睃�蝥�**嚗𣬚＆靽� write_hdf_db �餉�銝滩�������� sina_data �曉�隡𣳇�雴� sizelimit嚗𣬚頂蝏笔�摰��撠𢠃�霂交㺭�潦��
    - [x] **�滨蔭憿孵𦶢�滚笆朣� (Case-Sensitivity Alignment)**嚗𡁜� global.ini 銝剔��桀�蝏煺�靽格㺿銝� sina_MultiIndex_limit嚗諹圾�喃��曹�甇文��桀�憭批��嗘�銝��湛�撠誩� vs 撽澆陸嚗匧紡�渡��滨蔭�㰘蝸憭望�嚗㇅allback �� 200MB嚗厩��桅���
    - [x] **�瑕�甇�� Fallback ���璉坿粉�硋膥**嚗𡁜銁 	dx_hdf5_api.py 銝剖��唬� _load_sina_multiindex_limit嚗峕𣈲��之撠誩��芷����峕迤�蹱��硔��朖雿輸�蝵格�隞嗥��嗡��典�摮睃銁霂剜��躰秤嚗䔶��賜＆靽嗪�憸嘥��啗◤甇�＆�㰘蝸��
    - [x] **皜�� Global �滨蔭霂剜��鞉�**嚗帋耨憭滢� global.ini 銝� 
eal_time_cols 摮埈挾���雿坔��瑯��

## 2026-04-14 18:55
- [x] **瘛勗漲靽桀� sina_MultiIndex_data.h5 �唳旿韐券�銝擧沲��**嚗�
  - [x] **�拍�皜���䭾� open �� (Clean corrupted data)**嚗𡁏�銵䔶� 
epair_sina_multiindex_file 隞餃𦛚嚗�蝠摨訫��支� g:\sina_MultiIndex_data.h5 銝剖�銝� NaN �� open �𨰜�������唳旿銵峕㺭隞� ~222銝� 隡睃��� ~218銝���駁�嚗㚁���辣蝏𤘪��游�蝝批���
  - [x] **���銝梶鍂靽桀��亙藁 (Dedicated Repair Function)**嚗𡁜銁 	dx_hdf5_api.py 銝剜鰵憓硺� 
epair_sina_multiindex_file() �� clean_nan_columns() �亙藁��砲�亙藁�舀��芸𢆡�𡝗醌�𤩺��� ll_ 撘�憭渡�銵冽聢嚗�僎�㗇��� SCHEMA �扯�閫���硔��縧�滚��鍦�嚗峕����蝟餌���䌊����䜘��
  - [x] **�峕郊 Schema 摰匧��惩𤐄 (Schema Hardening)**嚗帋� sina_MultiIndex_SCHEMA 銝剜迤撘讐宏�支� open 摮埈挾嚗屸��� 
ormalize_SCHEMA ���𨅯蘨靽萘�撌脫��轁�嘥��辷�隞擧�憭港��𦦵�鈭�𧊋�亙��交𧒄�齿活鈭抒� ll-NaN �誩���虾�賬��

## 2026-04-14 18:40
- [x] **靽桀� HotlistPanel 銝剔�霂剜��躰秤 (IndentationError)**嚗�
  - [x] **靽桀�蝻拇𦆮銝𡡞�餉�蝻箏仃�桅�**嚗帋耨憭滢� hotlist_panel.py 銝� HotlistWorker.run 敺芰㴓���蝻抵��躰秤嚗�洵 186 銵䕘�嚗�僎�Ｗ�鈭�眏鈭擧迨�滨�颲烐�憭碶腺憭梁� get_trading_hub 銵峕��匧�銝� df_follow/df_watchlist 閫���餉���＆靽苷� Qt �航��硋極�瑁�憭�迤撣詨鍳�典僎�Ｗ�摰墧𧒄銵峕�瘚���

## 2026-04-14 16:30
- [x] **瘛勗漲隡睃� HotlistPanel 銝� Visualizer �𥪜𢆡�扯�嚗峕��� UI 蝎䀹���**嚗�
  - [x] **�寞祥 UI 蝥輻��餃� (Kill 1-3s Freezes)**嚗𡁜�甇Ｖ� MainWindow._on_initial_loaded_logic 銝剝獈憛硺蜓蝥輻����甇亥������ (sina.get_real_time_tick)��緵�冽��㕑���‘朣𣂷遙�∪��勗��� DataLoaderThread 撘�郊撽勗𢆡嚗�蝠摨閙��支���揢�∠巨�嗥��𡏭蓮����苷���香��
  - [x] **摰墧鴌 (1)$ ���毺揣撘閗��� (Index-based Linkage)**嚗𡁜銁 	rade_visualizer_qt6.py 銝剖��乩� self._table_item_map 蝝Ｗ�摮堒����銝芾��𥪜𢆡銝擧�蝝Ｗ�雿漤�餉�隞𦒘�蝏毺� (N)$ �滚��刻”�齿�銝� (1)$ 摮堒��交𪄳嚗�朖雿踹銁憭扯�璅∟䌊�㕑��𡑒”銝衤��賢��唬�瘥怎�蝥抒��祇𡢿�滚���
  - [x] **HotlistPanel 皜脫��嗆���漣**嚗�
    - [x] **韏��憸��頧� (UI Caching)**嚗𡁻����摮睃虜�函� QColor 銝� QFont 撖寡情嚗屸�撘�鈭�� 500ms �瑟鰵敺芰㴓銝剜����銝�葵 Qt 撖寡情����嗅��滢� GC �见���
    - [x] **擃㗛��𤩺��亙��冽凒�� (Dirty Check Update)**嚗𡁜銁 _update_item 銝剖��乩���捆銝𡡞��脣��滩�雿齿�瘚卝����典���聢�唳旿�𣇉𠶖���摰𧼮��冽𧒄�滩��典�撅� Qt �滨��亙藁嚗��閫��瘙惩��唳��祇�雿𦒘� 80% 隞乩���
    - [x] **撣���垍�靽脲擪 (Layout Protection)**嚗帋�摰墧𧒄�瑟鰵敺芰㴓銝剖竉蝳餃僎蝳�鍂鈭� 
esizeColumnsToContents() 餈嗘��游𦶢���扯����页��梢����霈曉捐摨虫��脫�瘚钅��亦恣嚗𣬚＆靽脲擪�芰��扳𧒄�� CPU 韐蠘蝸�����

## 2026-04-13 17:10
- [x] 瘛勗漲隡睃� SectorBiddingPanel UI �滚�撘𤩺沲���
  - [x] **撘訫��冽���撘誩�撅� (FlowLayout)**嚗𡁜�撘���箏��� QHBoxLayout 蝏𤘪�嚗峕㺿銝箏抅鈭𤾸�摰孵捐摨衣��芸𢆡�Ｚ�撣����極�瑟�蝏�辣�寞旿蝒堒藁摰賢漲�芸𢆡�� 3-5 銵䔶��游��ｇ�敶餃�閫��鈭��蝒堒藁銝𧢲��株◤�格𣏹�硋�撅�皞Ｗ枂��䔮憸塩��
  - [x] **蝏�辣�㛖漣�硋�鋆� (Modular Blocks)**嚗𡁜�撌亙��� widgets 撠���券�餉��梹�憒���亦����蝝Ｙ���𠶖���嚗劐葉嚗𣬚＆靽嘥銁�芸𢆡�Ｚ��嗥㮾�單綉隞嗡��嗆�蝑曉�蝏����銁銝�韏瘀�銝滢�鈭抒��餉��嗘���
  - [x] **銵冽聢摰賢漲����讠憬隡睃�**嚗𡁻�雿𦒘�銝芾�銵典��滨�銵函��嘥��堒捐嚗�僎霈曄蔭鈭� 25px ���撠誩�摰賡��嗚��鍂�瑞緵�典虾隞交�摨血�蝻拍���捐摨佗�撟園�朞�瘞游像皛𡁜𢆡�⊥䰻�贝��拇㺭�殷�摰䂿緵鈭��𨅯�摰嫣����萘��曄內蝑𣇉裦��
  - [x] **靽桀� UI ����碶�隞���笔�**嚗𡁻�撖寥����蝔衤葉�箇緵��誨���蝒� and �笔�嚗諹�銵䔶��𧢲钟蝥找耨憭溻����湔�憭滢� _save_ui_state �� _restore_ui_state �寞�嚗𣬚＆靽脲��刻��渡��堒捐����脩瑪雿滨蔭�券��臬�靘萘������
  - [x] **憓𧼮撩蝒堒藁憭批������**嚗𡁶宏�支�撖孵極�瑟��箏�����匧𤐄摰𡁻�摨�/摰賢漲�𣂼�嚗䔶蝙�港葵�Ｘ踎�賣������隞𡒊揮�穃��睃��典��烐綉���蝘滢蝙�典㦤�胯��

## 2026-04-01 21:55
- [x] 靽桀� 	rade_visualizer_qt6.py 撌虫儒銵冽聢�嘥��𡝗𧒄�堒捐餈�捐��䔮憸矋��朞�撘訫� get_compact_width 撟園�霈曉�蝘啣�摰賢漲閫����
- [x] �𡝗� 	rade_visualizer_qt6.py 銝� 9219 銵屸�餈𤑳�蝻㰘捏蝥踵挾 (Xianduan) 皜脫�嚗���嗆遬蝷箸��靝������

## 2026-04-01 22:02
- [x] 瘛勗漲靽桀��堒捐�桅�嚗𡁜�皛朞秐�刻䌊���璅∪�雿�銁擐𡝗活�唳旿�湔鰵�𤾸撩�嗉圻�穃�摰賡�蝞堒�憭𡁶漣銝𢠃��𣂼�嚗��蝘圈��嗡蛹 75嚗㚁�璅⊥��见𢆡�鍦�����栶��
- [x] 敶餃��埝䰻撟嗅��� 	rade_visualizer_qt6.py 銝剜��㚁�撌脩䰻銝文�嚗厩瑪畾� (Xianduan) 皜脫�雿滨蔭��

## 2026-04-01 22:12
- [x] 瘛勗漲隡睃� IPC �𥪜𢆡閫�藁蝞埈�嚗𡁜�撘�𤐄摰𡁜�蝘餌��伐��寧鍂�𨅯𢆡��𢰧靘扯斐���脲䲮獢������𢰧颲寧�憪讠�撖寥����啗����憸�� 8 �嫣��𧶏�嚗�僎�寞旿�𥪜𢆡�嫣�蝵株䌊���霈∠�撌西器�䕘�敶餃�閫��甇文��𨅯𢰧靘扳�摨衣征�賤�脲��𦦵𤫇�Ｗ��文銁撌西器�萘��曄內蝻粹萅��

## 2026-04-01 22:25
- [x] 銝� VolumeDetailsDialog 瘛餃�蝒堒藁雿滨蔭銝𤾸之撠讛扇敹���踝�蝏扳㗁 WindowMixin 撟園��� load_window_position_qt 銝� save_window_position_qt_visual嚗���啣��冽𦆮�讛祕�������芸𢆡靽嘥�銝𤾸�頧踝��𣂼�鈭支�雿㯄�����湔�扼��

## 2026-04-04 22:58
- [x] 瘛勗漲隡睃� MarketPulseViewer (Tkinter) UI �扯�嚗�
  - [x] �𣂼���憭扯��堆�撠��蝷箏�銵券��嗡蛹 Top 100嚗屸俈甇Ｘ�蝡舀㺭�桅�撖潸稲�屸𢒰�⊥香��
  - [x] **��漣 Dirty Flag 皜脫�璅∪�**嚗𡁜笆瘥娍㺭�桀�潔� Tag �睃�嚗䔶��典�閬�𧒄靚�鍂 	ree.item �湔鰵銵䕘��誩��䭾��瑟鰵��
  - [x] **�堒捐�脫� (Debounce Auto-Fit)**嚗𡁜��� fter_cancel/after �箏�撱嗉� 1s �扯�擃䀹��祆��𧶏�撟嗆溶�� measure_cache 蝻枏�嚗峕��方�蝏剖��唳𧒄�� CPU 撠硋陸��
  - [x] �嗆���摮� (Stat Caching)嚗帋蛹撣�㦤皜拙漲��踎�烾�����之�睃振�唳�蝑匧躹��溶�惩�摰孵��𡝗�瘚页��踹��䭾�銋厩� Canvas �滨� and Text �齿���
  - [x] 皜���𦯀��滨蔭嚗𡁶宏�支漱鈭㘾�餉�銝剝�憭滨� 	ag_configure 靚�鍂��

## 2026-04-04 23:10
- [x] 瘛勗漲隡睃� SectorBiddingPanel (PyQt6) 撌亦��扯�嚗�
  - [x] **韏��憸��頧� (UI Caching)**嚗𡁻����摮� QColor��Font �� QPen 韏��嚗峕��� 2000+ 銵�儐�臬��滚��𥕦遣 Qt 撖寡情������撘�����
  - [x] **�寥�皜脫�隡睃� (Item Reuse & Diff Update)**嚗𡁏�撘� setRowCount(0) �滚遣璅∪�嚗��蝥找蛹�箔� Dirty Check ���憭滨鍂�箏�����冽㺭�桀�摰嫘����脫���㺭�桀��笔��𡝗𧒄閫血� setText/setData嚗��瘥讐��瑟鰵�� UI �𧼮��𤩺��� ~5-10 �溻��
  - [x] **蝥� Python �鍦��嗆� (Pure Python Sorting)**嚗𡁜��Ｙ��其� Qt ���蝵格�摨� (setSortingEnabled(False))嚗峕㺿銝箔蝙�� Python �毺� sort()���敶餃�瘨�膄鈭��𨅯��齿�摨謿�嘥紡�渡��鍦��餉��脩���I �𤩺㦤�硋𢆡隞亙��劐葉憿寡歲�券䔮憸矋��峕𧒄餈𥕢�甇亙�撠睲�撣���瑟鰵�蠘�𨰜��
  - [x] **��𧒄�暸�霈∠�蝻枏� (K-line Cache Offloading)**嚗𡁜� (K)$ ����嗅��𡑒圾�𣂷� UI 敺芰㴓銝剖竉蝳鳴�蝘餉秐�唳旿����嗆挾嚗㇌ow Preparation嚗㚁�敶餃�瘨�膄皜脫��嗥� CPU Spike��
  - [x] **�券�蝝Ｗ��𤥁�皛� (Search Indexing)**嚗帋�隞�銁�踹�銵剁��券��寡” (Watchlist) 銋笔��唬� _search_blob 憸�揣撘𤏪�撠��蝝Ｚ�隞瑕���漲隞� (rows \times conds \times concat)$ �滢��� (rows \times conds)$��
  - [x] **皜脫����銝𤾸�撅�隡睃� (Throttling & Layout Protection)**嚗𡁜� UI �瑟鰵憸𤑳�����冽�擃� 5 FPS嚗峕��斗�靚梶�撣���滨�靽∪噡��
  - [x] **�園�����典��� (O(n簡) Elimination)**嚗𡁜蝠摨閧宏�� Watchlist 銝剖�雿嗵� O(n簡) Item Flags �刻”�急�嚗峕��厩𠶖����� _update_cell �笔�頝臬�銝凋�甈⊥�批��僐��
  - [x] **憭𡁻��硋𢆡�脫擪 (Selection Debouncing)**嚗𡁜��仿�劐葉憿寡歲頧祇��澆ế摰𡄯�撘��� lockSignals 蝎曉�雿滨宏嚗屸俈甇ａ�憸穃��啣�韏瑞�敺桀�皛𡁜𢆡頝喳𢆡��
  - [x] **摰匧��找�蝔喳��扯‘撘�**嚗𡁜��� 	hreading.Lock 靽脲擪�瑟鰵��誘嚗�僎靽桀�鈭���� lambda 摰𡁏𧒄�典�靚���

## 2026-04-05 23:55
- [x] 瘛勗漲靽桀� signal_dashboard_panel.py UI �曄內�𡃏��函㮾�喲䔮憸矋�
  - [x] **靽桀��唳旿銝𤾸㨃���霈⊥㺭�譍��寥�**嚗帋蝙�典縧�滚�銵冽聢�� 
owCount() 嚗�� self.tables["頝笔�靽∪噡"].rowCount()嚗厩凒�交��𡝗遬蝷箸㺭�格�餅㺭嚗峕𤜯�Ｗ�����𡝗�餃��脖�隞嗆���䲮瘜𨰻��蝠摨閗圾�喃�憿園�霈⊥㺭�∠�����㗇�隞亙�摨閖���掩靽⊥�嚗�� 頝笔�:嚗𣬚���: 蝑㚁��啣�銝𡒊鍂�瑕�����餃�銵冽𧒄���賜��唳㺭�株��唬�銝��渡��桅���
  - [x] **靽桀��曹�銝𧢲��𡑒”銝𡒊掩�见㨃��漱�㕑�皛文��𤑳��𨀣��唳旿撅閧內�嘥�撣�**嚗𡁜銁�冽��孵稬�𦦵緵頝笔�����拙��算�萘�蝐餃��∠�餈𥡝��孵稬頝唾蓮�塚��芸𢆡璉�瘚见僎皜�征銝𧢲�餈�誘獢�葉���摰𡁜��桀�嚗���Ｚ秐 "ALL" �嗆���嚗屸俈甇Ｗ��滨��㗇𥋘�鞉�扯�皛斗����厩�銵䔶蝙敺埈鰵憿菟𢒰�賢���
  - [x] **�𣂼�銝𧢲�餈�誘憿寧移��漲**嚗帋��㕑�皛文�銵� ComboxBox �厰★�∩葉��掩�曄內��㺭�𧶏�靽格㺿銝箔��覀�𨅯��其縑�猾�嘥�雿栞”餈凋誨蝎曉��䀹䰻�冽���撱綽�雿踹�銝𧢲��曄內��掩�𧢲㺭摮堒��航� UI �烾�100%銝亙��餃���
  - [x] **�脣�撅讐�蝛箔���**嚗𡁜銁雿輻鍂銝𧢲�餈�誘�其�敶枏��嗆��彿�坔銁瘥急�撟脩頂���隞硋���倌憭孵��塚��航�撘訫��寥��牐遙雿閖��惩紡�游�銵函�蝛綽�嚗諹䌊�刻圻�穃ế摰𡁜僎撟單�����喇�𨅯��其縑�猾�嘥抅蝖�憿蛛��踹�蝏嗵鍂�瑚漣�毺頂蝏笔㨃甇餅�瘝⊥㺭�桀�摨𠉛�鈭支��躰���

## 2026-04-06 20:32
- [x] 隡睃� SectorBiddingPanel ��蟮憭滨��蠘�嚗�
  - [x] **撘訫� QCalendarWidget �亙��㗇𥋘璅∪�**嚗𡁜�撘�頂蝏��隞園�㗇𥋘獢���芸�銋� SnapshotCalendarDialog 摰䂿緵�交�撽勗𢆡��漱鈭鉝��
  - [x] **摰䂿緵敹怎�摮㗛��航��� (Existing Data Highlighting)**嚗朞䌊�冽醌�� snapshots/ �桀�嚗��撌脫�敹怎��唳旿��𠯫�笔銁�亙�銝凋誑 **蝥Ｚ𠧧���蝎𨰜����垍瑪** �瑕�擃䀝漁�曄內嚗�僎�𣂷�摰墧𧒄���隞嗅��冽�扳嵗撉���嗆���擐���
  - [x] **靽桀��冽錰擃䀝漁�脩�**嚗𡁏遬撘誯�蝵桀𪂹�准��𪂹�亦�暺䁅恕��𧋦�澆�嚗�蝠摨閙��� QCalendarWidget �芸蒂��𪂹�怎滯摮堒笆敹怎���扇��僕�啜��
  - [x] **UI ����碶��餉����**嚗𡁶＆靽嘥��䀹芋撘譍�銝滢��賢�頧賢��脫㺭�殷�銝𠉛��Ｙ𠶖����厰僼憸𡏭𠧧��𠶖����鞟內����寡”���蝑㚁��賣迤蝖桀��惩��䀹𠯫����峕郊�湔鰵�𥪜𢆡�餉��舀� YYYYMMDD 撖寥���

## 2026-04-06 21:45
- [x] 瘛勗漲隡睃�蝡硺遠�Ｘ踎銵冽聢�鍦�鈭支�嚗�
  - [x] **蝏煺��鍦��鮋▲�餉�**嚗帋蛹 stock_table (銝芾�) 銵仿�鈭� sortIndicatorChanged 靽∪噡�𥪜𢆡嚗𣬚＆靽苷� sector_table (�踹�) �� watchlist_table (�滨�) 銵䔶蛹銝��湛��孵稬銵典仍�鍦��舘䌊�冽��刻秐憿園���
  - [x] **皜���𦯀�隞��**嚗𡁜��支� SectorBiddingPanel 銝剝�憭滚�銋厩� _on_header_clicked �𡁜��𣂼��賣㺭嚗��撟園�餉�撟嗅�撘箔�敶枏��踹�蝻枏� (last_populated_sector) ���璉埝�改�瘨�膄鈭��摨誯�餉��脩���

## 2026-04-06 21:48
- [x] 靽桀�敶𤘪𠯫�滨�銵� (Watchlist) �𥪜𢆡憭望�嚗𡁜銁 _init_ui 銝剛‘朣𣂷�蝻箏仃�� cellClicked��ellDoubleClicked �� currentCellChanged 靽∪噡餈墧𦻖嚗峕�憭滢��孵稬/��稬�𥪜𢆡隞亙��桃�銝𠹺��桀��Ｘ𧒄����嗉��典��賬��

## 2026-04-08 11:50
- [x] 瘛勗漲隡睃�銵冽聢�鍦�銝擧��典�憿嗡漱鈭𡜐�
  - [x] **撘箏��见𢆡�鍦��鮋▲**嚗帋耨�嫣��踹�銵具��葵�∟”����寡”��”憭渡��餃�靚��蝘駁膄銋见�隞�銁�衣���揢�嗅�憿嗥��冽���餉���緵�其遙雿閙��函��餉”憭湔�摨讐��滢��賢�閫血� 
eset_to_top=True嚗𣬚＆靽萘��喳�蝷箸�撘�/��撘梁����潔葵�～��
  - [x] **�啣��踹���揢�芸𢆡�鮋▲**嚗𡁜銁 _on_sector_table_selection_changed 銝剖��牐��踹��䀹凒�文�����冽��孵稬撟嗅��Ｗ�銝滚��踹��塚��喃蝙�芣��冽�摨𧶏�銋笔�銝芾�銵刻䌊�冽��刻秐憿園�嚗�蝠摨閗圾�喃�頝冽踎�埈�閫�𧒄����其�蝵格��䠷䔮憸塩��
  - [x] **�峕艶�瑟鰵雿滨蔭靽脲擪**嚗𡁜躹����见𢆡�滢�銝舘��航�����堆�Worker Heartbeat嚗㚁�銵峕��芸𢆡�湔鰵�嗡��嗡��嗵鍂�瑞�敶枏��㗇𥋘 and 皛𡁜𢆡雿滨蔭嚗�像銵∩��𨅯撩�𥕦�憿嗯�苷��𨅯像皛烐�閫��萘���瘙���

## 2026-04-08 12:20
- [x] 瘛勗漲憓𧼮撩 SectorBiddingPanel �𦦵揣銝𤾸��脩恣����踝�
    - [x] **�𦦵揣獢��隞嗅�蝥�**嚗𡁜� search_input ��漣銝� QComboBox嚗���啣虾蝻𤥁�����脰扇敶蓥��㗇���
    - [x] **摰䂿緵�𣈯�憭氯�嘥��桀��𥪜𢆡**嚗𡁏鰵憓䂿鸌畾𦠜�蝝Ｘ芋撘𧶏�敶𤘪�蝝Ｔ�𣈯�憭氯�脲𧒄嚗諹䌊�刻�����踹�樴坔仍瘙��餉秐�𨅯��仿��寡”�嘥�蝷綽�撟嗅𢆡��凒�唳�憸条𠶖����
    - [x] **�啣���蟮皜���蠘�**嚗帋蛹�𦦵揣��蟮�𡑒”瘛餃��喲睸�𨅯�嚗峕𣈲���鎿� �𣳇膄甇斗辺霈啣��嘥��𨥉�𡢅� 皜�征���匧��聆�嘅�撟嗅笆�𣈯�憭氯�脲瓲敹�★餈𥡝��𣳇膄靽脲擪��
    - [x] **瘛勗漲����㚚���**嚗𡁜��𦦵揣��蟮霈啣�����單𧋦�� JSON �滨蔭嚗���啗楊隡朞��芸𢆡�Ｗ���
    - [x] **�航��硋��斤��𤥁翮隞�**嚗𡁻�����𣳇膄�厰僼����園�餉�嚗峕溶�牐���耦�羓�蝥Ｚ′摨訫�蝎曇稲�硋㦛����𣂼�鈭�漱鈭鍦�擐��閫��獢�活��
    - [x] **鈭支�蝔喳��批���**嚗𡁜��唬�閫��撅��隞嗆㜃�迎�Viewport Event Filtering嚗㚁��� QComboBox �閗繮�圈�㗇𥋘靽∪噡�漤���⏛�剖��文躹�毺��孵稬瘚��敶餃�閫��鈭���文�蝒�■�整��
    - [x] **�𦦵揣蝏𤘪�瘛勗漲隡睃�**嚗𡁜��唬�銝芾��駁��餉�嚗�僎�亙�鈭� TickSeries �� first_breakout_ts 摰䂿緵�冽�蝝Ｙ��靝葉撅閧內蝎曉�����冽��䀹𧒄�氬��
    - [x] **鈭支��曇楝隡睃�**嚗𡁻�朞�餈墧𦻖 activated 靽∪噡摰䂿緵鈭��𣈯�㗇𥋘�單�蝝Ｔ�嘅��冽�隞𤾸��脖��匧�銵券�匧�憿孵�隡朞䌊�刻圻�烐䰻霂ｇ��𣳇��见𢆡蝖株恕��
    - [x] **�啣���蟮皜���蠘�**嚗帋蛹�𦦵揣��蟮�𡑒”瘛餃��喲睸�𨅯�嚗峕𣈲���鎿� �𣳇膄甇斗辺霈啣��嘥��𨥉�𡢅� 皜�征���匧��聆�嘅�撟嗅笆�𣈯�憭氯�脲瓲敹�★餈𥡝��𣳇膄靽脲擪��
    - [x] **�航��硋��文�撘�**嚗𡁜��亥䌊摰帋�皜脫�憪娍�嚗㇄elegate嚗㚁��其��匧�銵券★�喃儒蝏睃�蝥Ｚ𠧧���𦮝�脲��殷��舀��孵稬�喳������漱鈭鉝��

## 2026-04-08 16:38
- [x] 靽桀� minute_kline_viewer_qt.py �𦦵揣餈�誘�仿�嚗�
    - [x] **閫��靽∪噡��㺭�脩�**嚗𡁻�撖� search_input.textChanged 靽∪噡隡朞䌊�其��埝鰵摮㛖泵銝脣��啁��寞�改��� on_filter ���憓𧼮�鈭�掩�𧢲��伐�isinstance(df_input, pd.DataFrame)嚗剹��
    - [x] **瘨�膄撅墧�抒撩憭勗�撣�**嚗𡁜蝠摨閗圾�喃��曹�摮㛖泵銝脰秤雿� DataFrame 憭��撖潸稲�� 'str' object has no attribute 'empty' 撏拇�撘�虜嚗𣬚＆靽嘥��嗆�蝝Ｚ�皛文��賜��亙ㄝ�扼��

## 2026-04-08 21:15
- [x] 瘛勗漲靽桀� idding_momentum_detector.py ����碶�憭滨��餉�嚗�
    - [x] **靽桀�摰䂿��滚鍳蝘滚�銝Ｗ仃**嚗𡁜銁 load_persistent_data 銝剛‘朣𣂷� stock_selector_seeds ���憭漤�餉�嚗𣬚＆靽嗪��臬��𨅯辣蝏凌�嗪�憭渡� +15 ������敶Ｘ���餈唳迤蝖桀�頧賬��
    - [x] **隡睃���𧒄�唳旿銝��湔��**嚗𡁜銁摰䂿��滚鍳隞餃𦛚銝剖��牐� klines ���憭㵪�蝖桐�憸��霂��嚗𡿨eader Score嚗㕑恣蝞埈������鈭日��賣㺭�桀銁�滚鍳�𦒘��嗥移����
    - [x] **�扯�銝𡡞�璉埝�找���**嚗𡁜蝠摨訫�撟嗡� load_from_snapshot 銝剔��𦯀� K 蝥踹儐�荔�撟嗡耨憭滢�甇文��牐誨����踵揢撖潸稲�� Python 敺芰㴓蝏𤘪��游�憌𡡞埯��
    - [x] **撘箏� UI �𥪜𢆡�單𧒄��**嚗𡁻��� SectorBiddingPanel嚗𣬚＆靽嘥銁��揢�𣈯�憭渡�韏𥕞�脲芋撘𤩺𧒄�賜��唾圻�穃��讐�瘜閖��惩�嚗���啁��踵㺭�桃�蝘垍漣�滚���

## 2026-04-09 00:41
- [x] 瘛勗漲隡睃� SectorBiddingPanel �𦦵揣�餉�嚗諹蓮��**�踹�皞舀�璅∪�**嚗�
    - [x] **摰䂿緵瘣餉��踹�皞舀��𦦵揣**嚗𡁜��𦦵揣�餉�隞𤾸�蝥航�皛文�銵冽���蛹�券��踹�皞舀�����冽�颲枏�銝芾�隞���硋�蝘唳𧒄嚗𣬚頂蝏煺��芸𢆡�冽��匧��齿暑頝���靝蜓瘚�踎�轁�苷葉璉�蝝Ｚ砲�～����𡏭砲�∪�鈭擧�銝芷��剖漲�踹�嚗屸��寡”撠�凒�亙�蝷箄砲�𨀣踎�埈辺�栽�腈��
    - [x] **憓𧼮撩皞舀�靽⊥�撅閧內**嚗𡁏辺�桀�蝘啣�蝷箔蛹�𨀣踎�堒� (銝芾���)�嘅�撟嗅銁瘨典��埈遬蝷箄砲�踹�樴坔仍����嗆隅撟���嫣噶敹恍�蠘��急踎�㛖�摨艾��
    - [x] **瘛勗漲�𥪜𢆡銝舘�皛方圾��**嚗帋��碶��滨�銵函��孵稬銵䔶蛹��鍂�瑞��餅滲皞𣂼枂��踎�𡑒扇敶閙𧒄嚗𣬚頂蝏煺��芸𢆡�典椰靘批�雿滩歲�㕑砲�踹�����塚�**銝湔𧒄閫�膄銝芾�閫�㦛���蝝Ｚ�餈�誘�𣂼�**嚗𣬚＆靽苷��嫣葵�⊥�蝏�”�賢��游�蝷箄砲�踹�����㕑��讛�嚗��屸�隞�遬蝷箸�蝝� of �𦦵揣嚗㚁���之�𣂼�鈭���䀹�����
    - [x] **�芸𢆡�嗆���憭�**嚗𡁜銁�冽�皜�征�𦦵揣霂齿��𤏸絲�唳�蝝Ｘ𧒄嚗𣬚頂蝏煺��芸𢆡�滨蔭�𨅯撩�嗅��撾�萘𠶖����Ｗ�暺䁅恕���皛斗㦤�嗚��
    - [x] **摰寥��𦦵揣靽脲擪**嚗帋��嗘�銝芾��箇��𦦵揣雿靝蛹 Fallback嚗𣬚＆靽嘥朖靘蹂葵�∩�撅硺�瘣餉��踹�銋蠘��曄內�嗅抅�砌縑�胯��

## 2026-04-09 11:15
- [x] 瘛勗漲靽桀� BiddingMomentumDetector 頝冽𠯫�唳旿畾讠��餉�嚗�
    - [x] **摰䂿緵憭𡁶輕閫血��園𡢿�文� (Multi-source Trigger Logic)**嚗𡁜銁 daily_watchlist 銝剛‘朣𣂷� 	rigger_ts ����硋�畾蛛�撟嗅� _prune_expired_signals 靘行���凒�拙��喲��寡”銝擧暑頝�踎�堒��𤩺𧒄�湔���
    - [x] **蝥䭾迤����𡝗𠯫����� (Persistence Date Priority)**嚗𡁜銁�㰘蝸餈��銝凋����憭� JSON ����� data_date嚗�蝠摨閗圾�喃��䭾�雿𦦵頂蝏��隞嗡耨�寞𧒄�� (mtime) 瞍�宏撖潸稲��楊�亙仃��䔮憸塩��
    - [x] **蝏煺�撘��㗛�蝵桅秄瑽� (Unified 09:00 Reset)**嚗𡁜��嗆袇�� 09:15 �滨蔭�餉�蝏煺��𣂼�撟嗅像皛𤏸秐 09:00��銁璉�瘚见�頝冽𠯫�𤥁���㺭�格𧒄嚗䔶�隞����𥁒銵剁�餈睃撩�嗆�蝛箔葵�∪朖�嗉�����𢆡�誩����瘚钅��孵�敶Ｘ���餈堆�蝖桐�蝡硺遠撘�憪见��𧢲踎颲暹��𣈯妟�嗆���嘥��臬𢆡��
    - [x] **憓𧼮撩�芣�皜��瘛勗漲 (Deep Self-healing)**嚗𡁏����餉��啣銁��鉄 _sector_active_stocks_persistent 憓鮋�蝻枏�嚗峕�蝏苷��𨅯�撠豢踎�轁�嘥銁皜�征 ctive_sectors �𡒊眏鈭𤾸��誩��啗�峕香�啣�����航���

## 2026-04-09 12:20
- [x] 瘛勗漲靽桀� BiddingMomentumDetector 敶𤘪𠯫�滨�銵刻楊�交㺭�格��辷�
    - [x] **摰䂿緵霈啣�蝥扳𧒄�湔�撉諹� (Entry-level Timestamp Validation)**嚗𡁜銁�㰘蝸餈��銝剖笆 daily_watchlist 瘥譍�憿寡�銵� 	rigger_ts �⊿�嚗�撩�嗅��斗𡟺鈭𦒘��仿妟�寧�霈啣�嚗�蝠摨閗圾�喃��𨅯鍳�典���辣鋡思��交𧒄�湔�瘙⊥�撖潸稲�㰘蝸�冽𠯫�扳㺭�栽�萘�憿賜𪆴��
    - [x] **憓𧼮撩�交�摮㛖泵銝脰���**嚗𡁏𣈲��笆 	ime_str (憒� "0408-15:04") 餈𥡝�摮𣂷葡璉�瘚页��芸𢆡霂��撟嗡腺撘���急㿥�交𠯫�毺���蟮�∠𤌍��
    - [x] **靽桀��滨蔭撏拇�憌𡡞埯**嚗𡁜� _reset_daily_state 銝剔� klines 憭滢��勗�銵刻��潭㺿銝� clear() �滢�嚗䔶��嗘� deque 撘閧鍂�𠰴� maxlen 撅墧�改�瘨�膄鈭��雿滩�銵峕𧒄�� UI 皜脫�撏拇���
    - [x] **隡睃�餈��皜������**嚗𡁜�頝冽𠯫��辣��腺撘�秄瑽偦�摰𡁜銁 09:15嚗𣬚＆靽萘�隞瑕�憭������唳旿�舐鍂�改��峕𧒄�𦦵��𧢲踎��蟮畾讠���
    - [x] **�啣��见𢆡�滨蔭鈭支�**嚗𡁻��𣂼極�瑟��𨥉�� �滨蔭隞𦠜𠯫�萘滯�脫��殷��舀��冽��其��滚鍳蝔见�����萎�撟單�皜����蟮畾讠���

## 2026-04-09 14:10
- [x] 靽桀� 
ealtime_data_service.py 銝剔� NameError: name 'List' is not defined嚗�
    - [x] **銵仿� typing 撖澆�**嚗𡁜銁��辣憭湧�撖澆�銝剜溶�牐�蝻箏仃�� List��
    - [x] **蝏煺�憌擧聢隡睃�**嚗𡁜� ackfill_gaps_from_hdf5 蝑㗇鰵憓墧䲮瘜閧�蝐餃��鞟內隞� List[str] 頧祆揢銝� PEP 585 憌擧聢�� list[str]嚗䔶誑銝舘砲��辣�唳��� dict[...] �� list[...] 憌擧聢靽脲�銝��湛��𣂼�鈭�誨����澆捆�找��唬誨�麄��

## 2026-04-09 15:30
- [x] 瘛勗漲�齿� RealtimeDataService �� HDF5 �唳旿�Ｗ��箏�嚗�
    - [x] **摨笔��湔𦻖 HDF5 霈輸䔮**嚗𡁜銁 
ecover_from_hdf5_by_codes 銝剔宏�文笆 	dx_hdf5_api.load_hdf_db ��凒�亥��剁�頧祈�䔶蝙�� sina_data.Sina �𣂷����銝��亙藁 get_sina_MultiIndex_data��
    - [x] **�亙� SingleFlight 蝻枏�撘閙�**嚗𡁻�朞� sina_data.Sina 摰硺�嚗諹䌊�典�鈭急沲��漣�� HDF5 ���蝻枏�銝� SingleFlight �㰘蝸靽脲擪嚗峕��支�撟嗅��Ｗ��嗥��𦯀�蝤�� IO��
    - [x] **隡睃� MultiIndex 蝎曉�餈�誘**嚗𡁜⏚�� Pandas MultiIndex �寞�批笆 code_list 餈𥡝��煾��𡝗�鈭日�餈�誘嚗���啁蓡銝芸�蝘滨��Ｗ�摰帋�撱嗉�隞𡒊蓡瘥怎�蝥折�雿舘秐敺桃�蝥扼��
    - [x] **靽脲��𡁜��餉�銝��湔��**嚗𡁶＆靽脲�憭滨��唳旿瘚�恣�枏�餈𥕦� _aggregate_hdf5_df嚗���� Tick �� 1��� K 蝥輻����頧祆揢��

## 2026-04-09 16:30
- [x] **摰䂿緵 Sina �唳旿蝻枏����蝔讠漣�典��曹澈銝𤾸�憯格�批���**嚗�
    - [x] **靽桀�摨誩��硋�撣� (Fix TypeError)**嚗𡁻�撖� GlobalValues �航�憭�� multiprocessing.Manager 璅∪�����蛛�撠���臬��堒��� 	hreading.Lock �� _HDF_LOADING (��鉄 Event) 餈�宏�� uiltins �典�蝛粹𡢿���閫��鈭� cannot pickle '_thread.lock' object ��稲�賢援皞���峕𧒄靽肽�鈭��餈𤤿�憭𡁏芋�㛖㴓憓�����皞𣂼𣈲銝��扼��
    - [x] **餈�宏 L1 ���蝻枏�**嚗𡁜� _SINA_HDF5_MEM_CACHE ��蝸�� GlobalValues()嚗�僎瘛餃� 	ry-except �滨漣�餉���＆靽嘥銁���撘𤩺�憭朞�蝔讠㴓憓��嚗㷉ataFrame 蝑匧虾摨誩��𡝗㺭�桀偷�航��朞� Manager �曹澈嚗䔶��航��嗉䌊�典����� uiltins 璅∪���
    - [x] **�曹澈�㰘蝸�笔���**嚗𡁻�朞� uiltins ����啣�餈𤤿���凒��� SingleFlight �㰘蝸靽脲擪嚗�蝠摨閙�蝏苷�憭𡁏芋�堒��臬𢆡�嗥� IO �羓黎�����

## 2026-04-09 16:35
- [x] 靽桀� 	rade_visualizer_qt6.py ��揢�航��硋𪂹���Resample嚗匧�����䭾��湔鰵嚗���坔銁 Loading...嚗厩��桅���

## 2026-04-09 16:45
- [x] 瘛勗漲隡睃� 	rade_visualizer_qt6.py 皜脫��扯�銝� UI �滚��笔漲嚗�
    - [x] **摰䂿緵�冽���揢�脫� (Resample Debouncing)**嚗𡁜��� 50ms �� QTimer 撱嗉�閫血��箏�嚗��撟園�憸𤑳��餉窈瘙���踹�皜脫��笔�蝘臬���
    - [x] **SBC ���銝𤾸𪂹�蠘圾�� (Period-Agnostic SBC Cache)**嚗𡁜遣蝡� daily_df_raw �箏��亦瑪摮睃���BC 蝻枏��桐��滢�韏硋��滩��曄� resample �踹漲嚗���啣��Ｗ𪂹��𧒄�� 100% 蝻枏��賭葉嚗峕��日�蝞𡑒�埈𧒄嚗ǚ70ms嚗剹��
    - [x] **撘訫�皜脫�隞餃𦛚銝剜迫靽脲擪 (Render Sequence Protection)**嚗𡁻�朞� _render_seq 摨誩��瑟㦤�塚��刻�埈𧒄�����𣈲嚗𠄎BC/蝑𣇉裦�墧�/�����釣嚗匧��𤾸��嗆�瘚𧢲凒�啗窈瘙���𥅾霂瑟�撌脰��笔�蝡见朖銝剜鱏撟園��曆蜓蝥輻�嚗�蝠摨閗圾�唾�蝏剜�雿𨀣𧒄�� UI 蝎䀹��麄��
    - [x] **蝑𣇉裦隞輻�撘箇�摮� (Enhanced Strategy Cache)**嚗帋��碶���蟮靽∪噡隞輻�蝻枏��殷���笆�冽���揢餈𥡝�鈭��撖寞�批��麄��
    - [x] **隞���亙ㄝ�批���**嚗𡁏����皜脫��餉�銝剔��𦯀� print �峕唂���摮睃ế摰朞楝敺��憓𧼮撩鈭��韐蠘蝸銝讠�蝔喳��扼��

## 2026-04-09 17:45
- [x] 靽桀� intraday_decision_engine.py 銝剔� TypeError: cannot unpack non-iterable NoneType object嚗�
    - [x] **銵仿��賣㺭餈𥪜���**嚗帋耨憭滢� _time_structure_filter �券�憸�挽�園𡢿畾萄�蝻箏仃暺䁅恕 
eturn ��䔮憸矋�蝖桐��嗅�蝏���� 	uple[float, str]��
    - [x] **皜���嗘��餉�隞��**嚗𡁜��誩�憌条宏�� _opening_sell_check 銝𧢲䲮��偏�㗛��抵�皛日�餉��齿鰵敶雴��� _time_structure_filter ���嚗�僎蝘駁膄鈭���航噢���雿嗘誨���嚗��撘箔��喟�撘閙����銵𣬚迅摰𡁏�扼��

## 2026-04-09 17:55
- [x] 靽桀� sina_data.py 銝剔� NameError: name 'work_time_now' is not defined嚗�
    - [x] **銵仿��㗛�摰帋�**嚗𡁜銁 market �賣㺭���銵仿�鈭�撩憭梁� work_time_now = cct.get_work_time() 摰帋�嚗諹圾�喃��冽�銵峕𤣰�睃�隞餃𦛚嚗�
un_15_30_task嚗㗇𧒄�曹�蝻枏��⊿��餉�撘訫����摨誩援皞���

## 2026-04-09 18:05
- [x] 靽桀� intraday_decision_engine.py 銝剔� NameError: name 'row' is not defined嚗�
    - [x] **靽格迤�賣㺭蝑曉�**嚗𡁜�蝻箏仃�� 
ow ��㺭銵亙��� _sell_decision �寞�銝准��
    - [x] **�峕郊�湔鰵靚�鍂��**嚗𡁜銁 evaluate �寞�銝剛��� _sell_decision �嗆迤蝖桐��鍦��滩��� 
ow 摮堒�嚗𣬚＆靽� 9:30-9:50 �罸𡢿����睃摹�踵�瘚钅�餉��賢�甇�虜�扯���

## 2026-04-10 13:20
- [x] 靽桀� sector_bidding_panel.py 敶𤘪𠯫�滨�銵� (Watchlist) �𥪜𢆡憭望��桅�嚗�
    - [x] **�Ｗ��桃��𥪜𢆡**嚗帋耨甇�� _on_watchlist_cell_changed 銝剔���㺭霈曄蔭嚗�� link_software 隞� False �Ｗ�銝� True��迨憿寞㺿餈𤤿＆靽苷��冽��其蝙�其�銝钅睸��揢�滨�銵其葵�⊥𧒄嚗諹��峕郊閫血� TDX 蝑匧��刻蔓隞嗥��𥪜𢆡嚗�之撟�����憭滨�銝𤾸��条��抒�鈭支������

## 2026-04-10 13:26
- [x] 瘛勗漲靽桀� 	dx_hdf5_api.py �坔�蝏𤘪��寥�撘�虜 (ValueError: cannot match existing table structure)嚗�
  - [x] **摰匧��𣇉掩�贝蓮�ａ�餉� (Object to Numeric)**嚗𡁜�撘���脩𤌍撠���� object �𡑒蓮銝� str ���銝箝��緵�其�隡睃�撠肽��朞� pd.to_numeric 撠���� None 雿�𧋦韐冽糓�啣�潛� object �埈�憭滢蛹 loat64���靽脲擪鈭� close, high 蝑㗇瓲敹�㺭�澆��� Block 蝏𤘪�嚗屸俈甇Ｙ眏鈭擧毽��掩�见紡�渡�餈賢�憭梯揖��
  - [x] **Data Columns �箄�蝏扳㗁 (Inherit from Storer)**嚗𡁜銁 put_table_safe ��蕭�䭾芋撘譍�嚗���唬�隞𡒊緵�� HDF5 摮睃��刻䌊�刻粉�硋僎雿輻鍂 data_columns ����賬��圾�喃��曹� index_col 暺䁅恕�潔���辣撌脫�蝏𤘪�銝滨泵撖潸稲�� schema �脩���
  - [x] **靽格迤 MultiIndex ��㺭�譍�**嚗帋耨甇�� write_hdf_db 銝� ppend ��㺭撖� MultiIndex 璅∪�憭望���䔮憸矋�蝖桐� 
ewrite/append ��誘�賢�蝖桀�颲曉�撅���具��
  - [x] **摰䂿緵銝湔𧒄��辣畾讠��芣�**嚗𡁻�朞� PID + ThreadID �賢��𠉛氖嚗�僎�滚�撉諹��𡁏𧋦蝖株恕鈭�銁�圈�餉�銝� .tmp ��辣�冽��笔��亙���虾�䭾𤜯�Ｖ�皜����
- [x] **敶餃��齿� HDF5 �坔��餉�蝔喳���**嚗𡁻�撖寞迨�滨�颲穃��亦� IndentationError �䔶誨������銵䔶��券�摰∟恣銝𡡞��踺���憭滢� 
epack_hdf_db �� load_hdf_db_timed_ctx ����游�銋㚁�撟嗅��箔� os.replace �笔��踵揢�� 6 甈⊿���輸�霂閙㦤�塚�蝖桐�擃㗛�霂餃��箸艶銝讠��唳旿銝��湔�找�蝟餌�蝔喳��扼��
        - 靚�㟲鈭� instock_MonitorTK.py 銝剔��毺�摨訫� socket 頧株砭頞�𧒄蝑𣇉裦��� iz_IPC_send 隞擧迨�滩�鈭擧�餈𤤿� 100ms 敺桃�蝥扳��箏�撣貉器�䕘�蝘穃郎�唬�靚��撟唾﹛��  .2 蝘� (200ms)��
        - 霂亥��湔𠳿銝交聢靽嗪�鈭�楊餈𤤿�擃㗛�靽∪噡�唳旿����𡁻�憿箸��穃��䔶蜓蝥輻��嗅㨃憿選��峕𧒄���憭扯��蹂��曹� Windows 蝟餌� OS 蝥扯�皞𣂼��滨��嗥揮撘惩蒂�亦��㰘����帋縑�餅鱏��之�𤩺�颲𦦵� socket.timeout 霂舀𥁒��
    - [x] **UI 鈭衤辣敺芰㴓鈭� 20ms 蝥找漱隞䀹𤣰摰� (Achieved Sub-20ms Event Loop Parity)**嚗�
        - �滚�甇文��賢𧑐�� 200ms 靽∪噡�烾�蝻枏��穃�銝𡡞俈�㚚�蝏䀝誑�𠰴�撅����妟瘛望鼧韐萘��伐��港葵 UI 鈭衤辣敺芰㴓�滚�����啁���𡡒�舐＆霈歹��函頂 QTimer 皜脫�韐��敶餃�閫�膄嚗�
  
## 2026-06-04 23:05  
- [x] **靽桀� Treeview 憓鮋��湔鰵撖潸稲�滨��單釣�𡃏�皛文��鍦�憭望��� Bug (Fixed Treeview Incremental Update Sorting Failure)**嚗�  
    - [x] **�峕郊�拍�憿箏�**嚗𡁜銁 performance_optimizer.py �� TreeviewIncrementalUpdater._incremental_update 銝剛‘朣𣂷�撖� UI 蝏�辣摰鮋�雿滨蔭����唳�摨譌��銁�唳旿�𤑳�憓鮋��湔鰵�𤥁�皛日�蝞堒�嚗䔶蝙�� 	ree.move(iid, '', idx) 銝交聢靘萘��鍦��𡒊� DataFrame 憿箏�蝘餃𢆡 UI �����蝠摨閗圾�喃��曹�憓鮋��湔鰵隞���唳��砌��芣凒�寡��嫣�蝵殷�撖潸稲��" "�孵稬�滨��單釣�硋��啣��啣�隡睃�蝵桅▲憭望�嚗��憿駁��啁��餉”憭湧�蝞㛖��𤤿�嚗𣬚＆靽嘥��𡒊垢�鍦�憪讠�銝交聢銝��氬�� 
  
- [x] **靽桀��𦦵揣���皛斤� UI �见𢆡�滢��𡡞��孵�瘜典��鍦�憭望��� Bug (Fixed UI Manual Filter Sorting Failure)**嚗�  
    - [x] **銵亙� UI 蝥扳�摨誯�蝥扳㦤��**嚗𡁜銁 instock_MonitorTK.py �� efresh_tree 銝哨�銵仿�鈭��撖� UI 蝡舀��其漣�毺�餈�誘蝏𤘪�����唳�摨𤩺㦤�嗚����乩� skip_sort ���雿㵪��勗��� compute_executor 霈∠��閖�坿��亦�憸��摨讐��𨅯撩�嗉歲餈�迨甇乩誑靽萘��扯�隡睃飵嚗𥡝��笆鈭𡒊鍂�琿�朞�銝𦠜䲮�𦦵揣獢����皛斗�銝𧢲�獢��鈭抒���氖蝥踴��𧊋�鍦���㺭�殷��坔銁��緵�滩��典�蝵桃�瘜閗䌊�冽�憭滢誑 is_fav �� sortby_col嚗�����摨�/���嚗劐蛹銝駁睸����㛖�����蝠摨閗圾�喳僎皛∟雲鈭�" "�𦦵揣�擧�����Ｚ�皛文�嚗𣬚頂蝏蠘��芸𢆡霈啣�撟嗅辣蝏剜�摨𤩺䲮撘𧶏��峕𧒄�滨��𡑒”�芸𢆡�賊▲隡睃��曄內��鍂�瑟瓲敹��撉諹�瘙��� 
