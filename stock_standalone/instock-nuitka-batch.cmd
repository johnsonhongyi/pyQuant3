@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ================================================================================
:: Nuitka 批量编译打包调度中心 (Clang-Only)
:: 组合调用已有的各个独立 Nuitka 打包批处理，绝不修改、覆盖或破坏原有脚本
:: 运行时自动绕过原有批处理的等待与末尾 pause，实现全自动连续批处理
:: 编译前后自动归档保留最近 7 天的历史打包 exe，防止新版本异常无法回退排错
:: 最终显示全部打包的结果集统计时间、产物大小与清单报表
:: ================================================================================

title Nuitka 批量编译打包调度中心 (Clang-Only)

:: 基础工程目录与产物目录
set "ROOT_DIR=D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone"
set "BUILD_DIR=%ROOT_DIR%\build"

:: 自动定位各个子批处理所在目录
set "CMD_BASE_DIR=%~dp0"
if not exist "!CMD_BASE_DIR!\nuitka_build_ats_console_onlyClang.bat" (
    if exist "%ROOT_DIR%\nuitka_build_ats_console_onlyClang.bat" (
        set "CMD_BASE_DIR=%ROOT_DIR%"
    ) else if exist "C:\Users\Johnson\nuitka_build_ats_console_onlyClang.bat" (
        set "CMD_BASE_DIR=C:\Users\Johnson"
    )
)

:: 去除末尾反斜杠
if "!CMD_BASE_DIR:~-1!"=="\" set "CMD_BASE_DIR=!CMD_BASE_DIR:~0,-1!"

:: 默认 Nuitka 构建模式 (onefile_spec 为带专属解包目录的单文件模式，也可指定 onefile 或 standalone)
set "DEFAULT_BUILD_MODE=onefile_spec"
set "DRY_RUN=0"
set "USER_ARGS="

:: 解析命令行选项
for %%A in (%*) do (
    if /i "%%~A"=="--dry-run" (
        set "DRY_RUN=1"
    ) else if /i "%%~A"=="-n" (
        set "DRY_RUN=1"
    ) else if /i "%%~A"=="--standalone" (
        set "DEFAULT_BUILD_MODE=standalone"
    ) else if /i "%%~A"=="--onefile" (
        set "DEFAULT_BUILD_MODE=onefile"
    ) else if /i "%%~A"=="--onefile_spec" (
        set "DEFAULT_BUILD_MODE=onefile_spec"
    ) else (
        if "!USER_ARGS!"=="" (
            set "USER_ARGS=%%~A"
        ) else (
            set "USER_ARGS=!USER_ARGS! %%~A"
        )
    )
)

if not "!USER_ARGS!"=="" goto :PARSE_ARGS

:SHOW_MENU
cls
echo ================================================================================
echo                    Nuitka 批量编译打包调度中心 (Clang-Only)
echo ================================================================================
echo   [独立单模块打包]
echo     [1] ats       - ATS 操盘终端 (nuitka_build_ats_console_onlyClang.bat) (默认选项)
echo     [2] tk        - 行情监控主程序 (nuitka_build_console_onlyClang.bat)
echo     [3] multi     - 多周期策略 (nuitka_build_multi_period_dialog_onlyClang.bat)
echo.
echo   [快捷组合与全量打包]
echo     [4] tk,ats    - 常用双核组合 【先 TK，后 ATS】
echo     [5] all       - 核心全量打包 【TK + ATS + MULTI】
echo.
echo   [维护与清理工具]
echo     [6] clean     - 手动清理编译与解包缓存 (clean_nuitka_cache.bat)
echo.
echo     [0] exit      - 退出
echo ================================================================================
echo 提示: 支持直接输入序号[如 1 或 4 或 6]，也支持输入模块名称[如 ats 或 clean]，
echo       或者多选组合[用空格或逗号分隔，如 1 3 或 tk,ats]。
echo       默认构建模式: !DEFAULT_BUILD_MODE! (可传参 --standalone 或 --onefile 覆盖)
echo ================================================================================
set "INPUT_CHOICE=1"
set /p "INPUT_CHOICE=请输入打包选择 [默认 1 ATS操盘终端]: "
if defined INPUT_CHOICE set "INPUT_CHOICE=!INPUT_CHOICE:"=!"
if "!INPUT_CHOICE!"=="" set "INPUT_CHOICE=1"
if "!INPUT_CHOICE!"==" " set "INPUT_CHOICE=1"

set "USER_ARGS=!INPUT_CHOICE!"

:PARSE_ARGS
:: 将用户参数规范化，替换逗号和分号为空格
set "NORMALIZED_ARGS=!USER_ARGS:,= !"
set "NORMALIZED_ARGS=!NORMALIZED_ARGS:;= !"

:: 展开所有输入项为标准的任务代号列表
set "RUN_LIST="
for %%A in (!NORMALIZED_ARGS!) do (
    set "ARG=%%A"
    set "ARG=!ARG:"=!"

    if /i "!ARG!"=="0" goto :QUIT
    if /i "!ARG!"=="exit" goto :QUIT
    if /i "!ARG!"=="quit" goto :QUIT
    if /i "!ARG!"=="q" goto :QUIT

    if /i "!ARG!"=="6" goto :DO_CLEAN
    if /i "!ARG!"=="clean" goto :DO_CLEAN
    if /i "!ARG!"=="clean_cache" goto :DO_CLEAN
    if /i "!ARG!"=="clean-cache" goto :DO_CLEAN
    if /i "!ARG!"=="clean_nuitka_cache" goto :DO_CLEAN

    if /i "!ARG!"=="1" set "RUN_LIST=!RUN_LIST! ats"
    if /i "!ARG!"=="ats" set "RUN_LIST=!RUN_LIST! ats"

    if /i "!ARG!"=="2" set "RUN_LIST=!RUN_LIST! tk"
    if /i "!ARG!"=="tk" set "RUN_LIST=!RUN_LIST! tk"

    if /i "!ARG!"=="3" set "RUN_LIST=!RUN_LIST! multi"
    if /i "!ARG!"=="multi" set "RUN_LIST=!RUN_LIST! multi"
    if /i "!ARG!"=="qt" set "RUN_LIST=!RUN_LIST! multi"
    if /i "!ARG!"=="mp" set "RUN_LIST=!RUN_LIST! multi"

    if /i "!ARG!"=="4" set "RUN_LIST=!RUN_LIST! tk ats"
    if /i "!ARG!"=="tk_ats" set "RUN_LIST=!RUN_LIST! tk ats"
    if /i "!ARG!"=="tk-ats" set "RUN_LIST=!RUN_LIST! tk ats"

    if /i "!ARG!"=="5" set "RUN_LIST=!RUN_LIST! tk ats multi"
    if /i "!ARG!"=="all" set "RUN_LIST=!RUN_LIST! tk ats multi"
)

if "!RUN_LIST!"=="" (
    echo [警告] 未识别到有效的打包目标代号: !USER_ARGS!
    echo 请重新输入。
    goto :SHOW_MENU
)

:: 计算任务总数
set "PLAN_COUNT=0"
for %%M in (!RUN_LIST!) do set /A "PLAN_COUNT+=1"

echo.
echo ================================================================================
if "!DRY_RUN!"=="1" (
    echo 【DRY-RUN 演练模式】 共 !PLAN_COUNT! 个任务: !RUN_LIST!
) else (
    echo 【计划开始 Nuitka 批量打包】 共 !PLAN_COUNT! 个任务: !RUN_LIST!
)
echo 批处理基础目录: !CMD_BASE_DIR!
echo 构建产物目录  : !BUILD_DIR!
echo 构建模式选项  : !DEFAULT_BUILD_MODE!
echo ================================================================================

:: 记录整体开始时间戳与日期
set "GLOBAL_DATE=%DATE%"
set "GLOBAL_START_TIME=%TIME: =0%"
set "GLOBAL_START_TIMESTAMP=%DATE% %TIME%"

set "CURRENT_INDEX=0"
set "SUCCESS_COUNT=0"
set "FAIL_COUNT=0"

:: 循环执行各个模块打包
for %%M in (!RUN_LIST!) do (
    call :EXECUTE_MODULE "%%~M"
)

:: 记录整体结束时间
set "GLOBAL_END_TIME=%TIME: =0%"
set "GLOBAL_END_TIMESTAMP=%DATE% %TIME%"
call :CALC_TIME_DIFF "!GLOBAL_START_TIME!" "!GLOBAL_END_TIME!"
set "GLOBAL_DIFF_STR=!DIFF_FORMATTED!"
set "GLOBAL_DIFF_SEC=!DIFF_TOTAL_SEC!"

:: ================================================================================
:: 最终显示全部打包的结果集统计时间并以追加模式持久化到本地日志 (支持历次对比与缓存命中评估)
:: ================================================================================
if not exist "!BUILD_DIR!" mkdir "!BUILD_DIR!"
set "SUMMARY_LOG=!BUILD_DIR!\nuitka_batch_build_last_summary.txt"

:: 优先调用 Python 历史对比与缓存命中记录器 (追加模式)
if exist "%ROOT_DIR%\tools\log_build_summary.py" (
    set "MOD_ARGS="
    for /L %%I in (1,1,!PLAN_COUNT!) do (
        set "MOD_ARGS=!MOD_ARGS! --module "%%I#!RES_%%I_MOD!#!RES_%%I_TITLE!#!RES_%%I_STATUS!#!RES_%%I_TIME!#!RES_%%I_SIZE!#!RES_%%I_EXE!""
    )
    python "%ROOT_DIR%\tools\log_build_summary.py" --summary-log "!SUMMARY_LOG!" --build-dir "!BUILD_DIR!" --root-dir "%ROOT_DIR%" --build-mode "!DEFAULT_BUILD_MODE!" --plan-count !PLAN_COUNT! --success-count !SUCCESS_COUNT! --fail-count !FAIL_COUNT! --start-timestamp "!GLOBAL_START_TIMESTAMP!" --end-timestamp "!GLOBAL_END_TIMESTAMP!" --diff-sec !GLOBAL_DIFF_SEC! --diff-str "!GLOBAL_DIFF_STR!" !MOD_ARGS!
    goto :AFTER_SUMMARY
)

:: 原生批处理兜底输出与追加记录 (追加模式)
set "TEMP_SUMMARY=!BUILD_DIR!\nuitka_batch_build_current_run.tmp"
(
    echo.
    echo ================================================================================
    echo          【Nuitka 批量打包结果集汇总与时间统计】(追加模式)
    echo ================================================================================
    echo 序号  模块标识   执行状态   单项耗时       产物大小      目标产物文件
    echo --------------------------------------------------------------------------------
    for /L %%I in (1,1,!PLAN_COUNT!) do (
        echo   %%I.   !RES_%%I_MOD!	[!RES_%%I_STATUS!]	!RES_%%I_TIME!	!RES_%%I_SIZE!	!RES_%%I_EXE!
    )
    echo --------------------------------------------------------------------------------
    echo 构建任务汇总 : 总计 !PLAN_COUNT! 个 ｜ 成功: !SUCCESS_COUNT! 个 ｜ 失败: !FAIL_COUNT! 个
    echo 任务启动时间 : !GLOBAL_START_TIMESTAMP!
    echo 任务完成时间 : !GLOBAL_END_TIMESTAMP!
    echo 总体总计耗时 : !GLOBAL_DIFF_STR! [共 !GLOBAL_DIFF_SEC! 秒]
    echo 产物输出路径 : !BUILD_DIR!
    echo 历史归档路径 : !BUILD_DIR!\archive [保留最近 7 天版本]
    echo ================================================================================
) > "!TEMP_SUMMARY!" 2>nul
type "!TEMP_SUMMARY!"
type "!TEMP_SUMMARY!" >> "!SUMMARY_LOG!" 2>nul
if exist "!TEMP_SUMMARY!" del /f /q "!TEMP_SUMMARY!" >nul 2>&1

:AFTER_SUMMARY
echo 统计摘要已追加至历史日志: !SUMMARY_LOG!
echo.
pause
goto :eof

:: ================================================================================
:: 内部子例程: 执行单模块
:: ================================================================================
:EXECUTE_MODULE
set /A "CURRENT_INDEX+=1"
set "MOD=%~1"

:: 映射具体信息
if "!MOD!"=="ats" (
    set "TARGET_SCRIPT=!CMD_BASE_DIR!\nuitka_build_ats_console_onlyClang.bat"
    set "MOD_TITLE=ATS 操盘终端"
    set "TARGET_EXE=ATS_Terminal.exe"
)
if "!MOD!"=="tk" (
    set "TARGET_SCRIPT=!CMD_BASE_DIR!\nuitka_build_console_onlyClang.bat"
    set "MOD_TITLE=行情监控主程序[TK]"
    set "TARGET_EXE=instock_MonitorTK_Nuita.exe"
)
if "!MOD!"=="multi" (
    set "TARGET_SCRIPT=!CMD_BASE_DIR!\nuitka_build_multi_period_dialog_onlyClang.bat"
    set "MOD_TITLE=多周期策略窗口"
    set "TARGET_EXE=MultiPeriodTester.exe"
)

set "EXE_PATH=!BUILD_DIR!\!TARGET_EXE!"

echo.
echo ================================================================================
echo [!CURRENT_INDEX!/!PLAN_COUNT!] 正在执行模块: !MOD_TITLE! [!MOD!]
echo 目标批处理: !TARGET_SCRIPT!
echo 预期产物  : !EXE_PATH!
echo ================================================================================

if not exist "!TARGET_SCRIPT!" (
    echo [错误] 找不到批处理文件: !TARGET_SCRIPT!
    set "STATUS=失败"
    set "TASK_DIFF_STR=0秒"
    set "EXE_SIZE_STR=缺失"
    set /A "FAIL_COUNT+=1"
    goto :RECORD_RESULT
)

:: 打包前自动归档：若已有旧版本，先备份到 build\archive\ 并清理超过 7 天的历史版本
if exist "%ROOT_DIR%\tools\archive_build_exe.py" (
    if "!DRY_RUN!"=="1" (
        python "%ROOT_DIR%\tools\archive_build_exe.py" --target "!EXE_PATH!" --days 7 --stage pre-build --dry-run
    ) else (
        python "%ROOT_DIR%\tools\archive_build_exe.py" --target "!EXE_PATH!" --days 7 --stage pre-build
    )
)

:: 记录单项开始时间
set "TASK_START_TIME=%TIME: =0%"

if "!DRY_RUN!"=="1" (
    echo [DRY-RUN 演练] 模拟调用 "!TARGET_SCRIPT!" !DEFAULT_BUILD_MODE! 成功完成 [不执行实际编译]
    set "TASK_EXIT_CODE=0"
    goto :AFTER_BUILD_RUN
)

:: 真实打包: 传入构建模式参数并利用 < nul 安全绕过子脚本中的 pause 与输入等待，实现无缝连续编译
pushd "%ROOT_DIR%"
call "!TARGET_SCRIPT!" !DEFAULT_BUILD_MODE! < nul
set "TASK_EXIT_CODE=!ERRORLEVEL!"
popd

:AFTER_BUILD_RUN
:: 记录单项结束时间
set "TASK_END_TIME=%TIME: =0%"

:: 计算单项耗时
call :CALC_TIME_DIFF "!TASK_START_TIME!" "!TASK_END_TIME!"
set "TASK_DIFF_STR=!DIFF_FORMATTED!"

:: 检查产物状态与文件大小
call :CALC_FILE_SIZE "!EXE_PATH!"
set "EXE_SIZE_STR=!RET_FILE_SIZE!"

if "!TASK_EXIT_CODE!"=="0" (
    set "STATUS=成功"
    set /A "SUCCESS_COUNT+=1"
    if exist "%ROOT_DIR%\tools\archive_build_exe.py" (
        if "!DRY_RUN!"=="1" (
            python "%ROOT_DIR%\tools\archive_build_exe.py" --target "!EXE_PATH!" --days 7 --stage post-build --dry-run
        ) else (
            python "%ROOT_DIR%\tools\archive_build_exe.py" --target "!EXE_PATH!" --days 7 --stage post-build
        )
    )
    goto :RECORD_RESULT
)

set "STATUS=失败"
set /A "FAIL_COUNT+=1"
echo ================================================================================
echo [ERROR] 模块 !MOD_TITLE! 构建失败 (ExitCode: !TASK_EXIT_CODE!)
echo 提示: 如需紧急使用旧版，可前往 !BUILD_DIR!\archive\ 提取最近 7 天内的历史备份
echo ================================================================================

:RECORD_RESULT
set "RES_!CURRENT_INDEX!_MOD=!MOD!"
set "RES_!CURRENT_INDEX!_TITLE=!MOD_TITLE!"
set "RES_!CURRENT_INDEX!_STATUS=!STATUS!"
set "RES_!CURRENT_INDEX!_TIME=!TASK_DIFF_STR!"
set "RES_!CURRENT_INDEX!_SIZE=!EXE_SIZE_STR!"
set "RES_!CURRENT_INDEX!_EXE=!TARGET_EXE!"
goto :eof

:: ================================================================================
:: 内部辅助子例程: 时间差计算
:: ================================================================================
:CALC_TIME_DIFF
for /F "tokens=1-4 delims=:.," %%a in ("%~1") do (
   set /A "c_sh=1%%a-100", "c_sm=1%%b-100", "c_ss=1%%c-100", "c_sc=1%%d-100"
)
for /F "tokens=1-4 delims=:.," %%a in ("%~2") do (
   set /A "c_eh=1%%a-100", "c_em=1%%b-100", "c_es=1%%c-100", "c_ec=1%%d-100"
)
set /A "c_start_cs=(c_sh*360000)+(c_sm*6000)+(c_ss*100)+c_sc"
set /A "c_end_cs=(c_eh*360000)+(c_em*6000)+(c_es*100)+c_ec"
if !c_end_cs! LSS !c_start_cs! (
   set /A "c_end_cs+=8640000"
)
set /A "c_diff_cs=c_end_cs-c_start_cs"
set /A "DIFF_TOTAL_SEC=c_diff_cs/100"
set /A "DIFF_MIN=DIFF_TOTAL_SEC/60"
set /A "DIFF_SEC=DIFF_TOTAL_SEC%%60"
if !DIFF_MIN! GTR 0 (
    set "DIFF_FORMATTED=!DIFF_MIN!分!DIFF_SEC!秒"
) else (
    set "DIFF_FORMATTED=!DIFF_SEC!秒"
)
goto :eof

:: ================================================================================
:: 内部辅助子例程: 文件大小计算
:: ================================================================================
:CALC_FILE_SIZE
if not exist "%~1" (
    set "RET_FILE_SIZE=未生成"
    goto :eof
)
set "size_bytes=%~z1"
if !size_bytes! GTR 1048576 (
    set /A "size_mb=size_bytes/1048576"
    set /A "size_dec=(size_bytes%%1048576)*10/1048576"
    set "RET_FILE_SIZE=!size_mb!.!size_dec! MB"
) else if !size_bytes! GTR 1024 (
    set /A "size_kb=size_bytes/1024"
    set "RET_FILE_SIZE=!size_kb! KB"
) else (
    set "RET_FILE_SIZE=!size_bytes! B"
)
goto :eof

:: ================================================================================
:: 内部子例程: 手动清理 Nuitka 编译与解包缓存
:: ================================================================================
:DO_CLEAN
cls
echo ================================================================================
echo          【手动清理模式】Nuitka 编译缓存与运行时解包目录清理 (clean_nuitka_cache)
echo ================================================================================
set "CLEAN_SCRIPT=!CMD_BASE_DIR!\clean_nuitka_cache.bat"
if not exist "!CLEAN_SCRIPT!" set "CLEAN_SCRIPT=%ROOT_DIR%\clean_nuitka_cache.bat"
if not exist "!CLEAN_SCRIPT!" set "CLEAN_SCRIPT=C:\Users\Johnson\clean_nuitka_cache.bat"

if not exist "!CLEAN_SCRIPT!" (
    echo [错误] 找不到清理脚本 clean_nuitka_cache.bat
    echo 请确认该文件是否存在于工程根目录: %ROOT_DIR%
    echo.
    pause
    if "%~1"=="" goto :SHOW_MENU
    goto :QUIT
)

echo 目标清理脚本: !CLEAN_SCRIPT!
echo 警告: 此操作将清空 .nuitka_cache、sccache、build 中间编译产物及 G:\Temp 单文件解包。
echo       清理后下一次打包将无法使用增量缓存加速，需从零重新编译。
echo.
if "!DRY_RUN!"=="1" (
    echo [DRY-RUN 演练] 模拟调用 "!CLEAN_SCRIPT!" [不执行实际清理]
    echo.
    if "%~1"=="" (
        echo 按任意键返回调度中心主菜单...
        pause >nul
        goto :SHOW_MENU
    )
    goto :QUIT
)

set "CONFIRM_CLEAN=Y"
if "%~1"=="" (
    set /p "CONFIRM_CLEAN=确认执行深度清理缓存吗? [Y/n]: "
    if "!CONFIRM_CLEAN!"=="" set "CONFIRM_CLEAN=Y"
)

if /i not "!CONFIRM_CLEAN!"=="Y" (
    echo.
    echo [取消] 用户取消清理操作。
    echo.
    if "%~1"=="" (
        timeout /t 2 >nul
        goto :SHOW_MENU
    )
    goto :QUIT
)

echo.
echo 正在执行清理...
call "!CLEAN_SCRIPT!" -y
echo.
echo ================================================================================
echo [完成] 缓存清理完毕。工作区已恢复纯净状态。
echo ================================================================================
if "%~1"=="" (
    echo 按任意键返回调度中心主菜单...
    pause >nul
    goto :SHOW_MENU
) else (
    goto :QUIT
)

:QUIT
echo [已退出 Nuitka 批量打包调度中心]
exit /b 0
