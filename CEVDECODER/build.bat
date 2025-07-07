@echo off
if not exist bin\ mkdir bin
:START
echo ###############################################################################
if not exist bin\ mkdir bin
rem tools\spasm64 -E src\1B3X-ZX7.asm bin\DECODR01.8xv
rem tools\spasm64 -E src\2B3X-ZX7.asm bin\DECODR02.8xv
rem tools\spasm64 -E src\1B1X-ZX7.asm bin\DECODR03.8xv
rem tools\spasm64 -E src\4C3X-ZX7.asm bin\DECODR04.8xv
rem tools\spasm64 -E src\4A3X-ZX7.asm bin\DECODR05.8xv
rem tools\spasm64 -E src\4B3X-ZX7.asm bin\DECODR06.8xv

tools\spasm64 -E src\M1X3-ZX7.asm bin\DECODEM1.8xv
echo M1X3-ZX7.asm to DECODEM1.8xv
echo -
tools\spasm64 -E src\M1X2-ZX7.asm bin\DECODEM2.8xv
echo M1X2-ZX7.asm to DECODEM2.8xv
echo -
rem tools\spasm64 -E src\DECOTEST.asm bin\DECOTEST.8xv


pause
goto START