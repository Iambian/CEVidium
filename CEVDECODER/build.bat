@echo off
:START
echo ###############################################################################
tools\spasm64 -E src\1B3X-ZX7.asm bin\DECODR01.8xv
tools\spasm64 -E src\2B3X-ZX7.asm bin\DECODR02.8xv
tools\spasm64 -E src\1B1X-ZX7.asm bin\DECODR03.8xv
tools\spasm64 -E src\1C3X-ZX7.asm bin\DECODR04.8xv
tools\spasm64 -E src\AD3X-ZX7.asm bin\DECODR05.8xv


pause
goto START