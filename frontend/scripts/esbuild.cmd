@echo off
setlocal

rem Some Windows environments block node.exe from spawning unknown executables
rem in user-writable folders. Vite/esbuild spawns a native esbuild.exe process.
rem This shim makes esbuild.exe be launched by cmd.exe instead.

set "ESBUILD_EXE=%~dp0..\node_modules\@esbuild\win32-x64\esbuild.exe"
if not exist "%ESBUILD_EXE%" (
  echo [esbuild-shim] Missing "%ESBUILD_EXE%" 1>&2
  exit /b 1
)

"%ESBUILD_EXE%" %*

