@echo off
REM ============================================================================
REM  Kohan II: Kings of War - Widescreen fix (one-click)
REM
REM  1. Start Kohan II and load into a game/skirmish/editor map.
REM  2. Double-click this file.
REM  It patches the running game in memory (nothing on disk is changed) and the
REM  widescreen view takes effect on the next camera move.
REM
REM  For an automatic, every-launch install instead, see README - "Steam launch
REM  option" - so you never have to run this by hand.
REM ============================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Kohan2Widescreen.ps1"
echo.
pause
