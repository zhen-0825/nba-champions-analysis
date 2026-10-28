# 建立 Windows 工作排程：每天 15:30 自動執行 daily_update.bat
# 用法：在 VS Code 終端機（PowerShell）輸入  .\setup_schedule.ps1
# 想改時間：把下面的 15:30 改掉，再執行一次這個檔案（會覆蓋舊設定）
# 想取消：Unregister-ScheduledTask -TaskName "NBA-Daily-Update"

$bat      = Join-Path $PSScriptRoot "daily_update.bat"
$action   = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At "15:30"
# StartWhenAvailable：時間到時電腦沒開，下次開機會補跑
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName "NBA-Daily-Update" -Description "NBA 每日資料更新：抓最新比賽數據寫進 Supabase" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "完成！每天 15:30 會自動更新 NBA 資料；當時電腦沒開機的話，下次開機會補跑。"
Write-Host "想立刻測試一次：Start-ScheduledTask -TaskName NBA-Daily-Update"
