@echo off
REM 一键本地预览：启动本地服务器并打开浏览器
REM （直接双击 index.html 会因 file:// 协议导致数据加载失败）
cd /d %~dp0web
start "" http://localhost:8765/index.html
where py >nul 2>nul && (py -m http.server 8765) || (python -m http.server 8765)
