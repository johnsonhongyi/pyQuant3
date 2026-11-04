@echo off
rem Forwarding legacy build_nuitka.bat to the optimized Clang-CL build script
call "%~dp0build_nuitka_clang.bat" %*
exit /b %ERRORLEVEL%
