@echo off
rem MAKE_CAMPAIGN.bat — double-click to generate the full month campaign
rem pack (images + reels/shorts + captions + hashtags) for the Social
rem Assistant extensions. Output lands in .\generated\3SVerse-Social-Campaign\
cd /d "%~dp0"
where py >nul 2>nul && (py -3 make_campaign.py %*) || (python make_campaign.py %*)
echo.
pause
