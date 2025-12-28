@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =====================================
echo     FFmpeg 视频格式转换工具
echo =====================================
echo.

:: 检查ffmpeg是否存在
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 ffmpeg，请确保 ffmpeg 已安装并添加到 PATH 环境变量中
    pause
    exit /b 1
)

:: 获取输入文件
set /p input_file="请输入源视频文件路径: "
if not exist "%input_file%" (
    echo 错误: 源文件不存在
    pause
    exit /b 1
)

:: 获取参考文件
set /p reference_file="请输入参考视频文件路径: "
if not exist "%reference_file%" (
    echo 错误: 参考文件不存在
    pause
    exit /b 1
)

:: 获取输出文件名
set /p output_file="请输入输出文件路径: "
if "%output_file%"=="" (
    echo 错误: 输出文件路径不能为空
    pause
    exit /b 1
)

echo.
echo 正在分析参考视频格式...

:: 创建临时文件存储参考视频信息
set temp_info=%temp%\ffmpeg_ref_info.txt

:: 获取参考视频的详细信息
ffmpeg -i "%reference_file%" 2>"%temp_info%"

:: 解析视频编码器
for /f "tokens=*" %%a in ('findstr /c:"Video:" "%temp_info%"') do (
    set video_line=%%a
)

:: 解析音频编码器
for /f "tokens=*" %%a in ('findstr /c:"Audio:" "%temp_info%"') do (
    set audio_line=%%a
)

:: 提取视频编码信息
echo !video_line! | findstr /c:"h264" >nul && set video_codec=libx264
echo !video_line! | findstr /c:"hevc" >nul && set video_codec=libx265
echo !video_line! | findstr /c:"h265" >nul && set video_codec=libx265
echo !video_line! | findstr /c:"vp9" >nul && set video_codec=libvpx-vp9
echo !video_line! | findstr /c:"vp8" >nul && set video_codec=libvpx
echo !video_line! | findstr /c:"av1" >nul && set video_codec=libaom-av1
echo !video_line! | findstr /c:"mpeg4" >nul && set video_codec=mpeg4
echo !video_line! | findstr /c:"xvid" >nul && set video_codec=libxvid

:: 提取音频编码信息
echo !audio_line! | findstr /c:"aac" >nul && set audio_codec=aac
echo !audio_line! | findstr /c:"mp3" >nul && set audio_codec=libmp3lame
echo !audio_line! | findstr /c:"ac3" >nul && set audio_codec=ac3
echo !audio_line! | findstr /c:"flac" >nul && set audio_codec=flac
echo !audio_line! | findstr /c:"vorbis" >nul && set audio_codec=libvorbis
echo !audio_line! | findstr /c:"opus" >nul && set audio_codec=libopus
echo !audio_line! | findstr /c:"pcm" >nul && set audio_codec=pcm_s16le

:: 如果没有检测到编码器，使用默认值
if not defined video_codec set video_codec=libx264
if not defined audio_codec set audio_codec=aac

echo.
echo 检测到的参考格式:
echo   视频编码: %video_codec%
echo   音频编码: %audio_codec%
echo.

:: 显示完整的转换命令
echo 将要执行的命令:
echo ffmpeg -i "%input_file%" -c:v %video_codec% -c:a %audio_codec% -preset medium -crf 23 -map 0 "%output_file%"
echo.

set /p confirm="确认开始转换? (Y/N): "
if /i not "%confirm%"=="Y" (
    echo 转换已取消
    goto :cleanup
)

echo.
echo 开始转换...
echo =====================================

:: 执行转换
ffmpeg -i "%input_file%" -c:v %video_codec% -c:a %audio_codec% -preset medium -crf 23 -map 0 -y "%output_file%"

if errorlevel 1 (
    echo.
    echo 转换失败！
    echo 可能的原因：
    echo 1. 编码器不支持或未安装
    echo 2. 输入文件损坏
    echo 3. 磁盘空间不足
    echo 4. 权限问题
) else (
    echo.
    echo =====================================
    echo 转换完成！
    echo 输出文件: %output_file%
    echo =====================================
    
    :: 显示输出文件信息
    echo.
    echo 输出文件信息:
    ffmpeg -i "%output_file%" 2>&1 | findstr /c:"Video:" /c:"Audio:" /c:"Duration:"
)

:cleanup
:: 清理临时文件
if exist "%temp_info%" del "%temp_info%"

echo.
pause