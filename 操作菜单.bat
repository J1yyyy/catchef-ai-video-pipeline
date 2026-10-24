@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call conda activate seedance_cat
if errorlevel 1 (
  echo Conda environment activation failed.
  echo Please run this file in Anaconda Prompt, or check whether seedance_cat exists.
  pause
)

:menu
cls
echo ====================================
echo Orange Cat API Video Tool
echo ====================================
echo 1. Generate prompts only
echo 2. Generate video with Seedance
echo 3. Resume video generation
echo 4. Super-res video with AI MediaKit
echo 5. Resume super-res
echo 6. Compose normal 90s final_90s.mp4
echo 7. Compose upscaled 90s final_90s_upscaled.mp4
echo 8. Mock test: prompts + mock video part1
echo 9. Exit
echo ====================================
echo Tips:
echo - Real video needs ARK_API_KEY.
echo - Real super-res needs AMK_API_KEY.
echo - Super-res uses the configured AI MediaKit free task type.
echo ====================================
set /p MENU_CHOICE=Choose 1-9 and press Enter: 

if "%MENU_CHOICE%"=="1" goto prompt_only
if "%MENU_CHOICE%"=="2" goto generate_video
if "%MENU_CHOICE%"=="3" goto resume_video
if "%MENU_CHOICE%"=="4" goto super_res
if "%MENU_CHOICE%"=="5" goto resume_super_res
if "%MENU_CHOICE%"=="6" goto compose
if "%MENU_CHOICE%"=="7" goto compose_upscaled
if "%MENU_CHOICE%"=="8" goto mock_test
if "%MENU_CHOICE%"=="9" goto exit

echo Invalid choice.
pause
goto menu

:prompt_only
python main.py --prompt-only
goto done

:generate_video
call :read_output_dir
call :read_parts
python main.py --generate-video "%OUTPUT_DIR%" --real-video --parts %PARTS%
goto done

:resume_video
call :read_output_dir
call :read_parts
python main.py --resume "%OUTPUT_DIR%" --real-video --parts %PARTS%
goto done

:super_res
echo Real super-res uses the configured AI MediaKit free task type.
set /p CONFIRM_SUPER=Type Y to continue, or anything else to return: 
if /I not "%CONFIRM_SUPER%"=="Y" goto menu
call :read_output_dir
call :read_parts
python main.py --super-res-parts "%OUTPUT_DIR%" --real-super-res --parts %PARTS%
goto done

:resume_super_res
echo Real super-res uses the configured AI MediaKit free task type.
set /p CONFIRM_RESUME_SUPER=Type Y to continue, or anything else to return: 
if /I not "%CONFIRM_RESUME_SUPER%"=="Y" goto menu
call :read_output_dir
call :read_parts
python main.py --resume-super-res-parts "%OUTPUT_DIR%" --real-super-res --parts %PARTS%
goto done

:compose
call :read_output_dir
python main.py --compose "%OUTPUT_DIR%"
goto done

:compose_upscaled
call :read_output_dir
python main.py --compose-upscaled "%OUTPUT_DIR%"
goto done

:mock_test
python main.py --with-video --mock-llm --mock-video --parts 1
goto done

:read_output_dir
echo.
echo Input output folder, for example:
echo outputs\2026-05-14_Bakwan-jagung_Sup-ayam-kampung_Sate-ayam
set /p OUTPUT_DIR=Output folder: 
exit /b

:read_parts
echo.
echo Input parts: 1 or 1,2 or 4,5,6 or all
echo Press Enter to use all.
set /p PARTS=Parts: 
if "%PARTS%"=="" set "PARTS=all"
exit /b

:done
echo.
echo Done. Press any key to return to menu.
pause >nul
goto menu

:exit
exit /b
