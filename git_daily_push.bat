@echo off
cd /d "E:\app\make.money\1"
echo [%date% %time%] Running daily Git sync at 16:00... >> logs\git_daily_sync.log
git add docs/
git status --porcelain docs/ > tmp_git_status.txt
set /p STATUS=<tmp_git_status.txt
del tmp_git_status.txt

if not "%STATUS%"=="" (
    git commit -m "Daily Batch Publish: %date%" >> logs\git_daily_sync.log 2>&1
    git push origin main >> logs\git_daily_sync.log 2>&1
    git push review main >> logs\git_daily_sync.log 2>&1
    echo [%date% %time%] Daily Git sync completed successfully. >> logs\git_daily_sync.log
) else (
    echo [%date% %time%] No new articles to commit. >> logs\git_daily_sync.log
)
