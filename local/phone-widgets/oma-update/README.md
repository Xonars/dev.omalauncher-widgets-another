# OMA · репозиторий и APK

Интерфейс: `../76-oma-update-app.owl`.
`repository.py` читает `/root/dev.omalauncher-another` и сравнивает выбранную
локальную или удалённую ветку с `upstream/main` (SimonSchubert/omalauncher).
`origin/main` — опубликованный форк Xonars/dev.omalauncher-another.

Кнопка обновления получает refs обоих remotes, без checkout, merge, push или
изменения рабочих файлов. Время последнего успешного fetch хранится отдельно
для каждого remote в `~/.cache/oma-updater/repository-sync.json`. При ошибке
сохраняются прежние данные и показывается ошибка. Параллельный fetch защищён flock.
Списки ограничены: 30 коммитов, 60 веток и 60 файлов. Полные diff доступны в терминале.
Счётчики ahead/behind считают коммиты по истории; git cherry отдельно показывает
патчи, не эквивалентные изменениям Симона (без merge-коммитов).

Сборка, резервные копии, подпись и журналы остаются в существующем
`~/.local/share/oma-updater/updater.py`: сборка из origin/main, независимо от
выбранной для просмотра ветки. Старый APK остаётся доступен до успешной новой сборки.
Фоновая операция продолжается после закрытия приложения.

Проверки:

    python -m unittest discover -s oma-update -p 'test_*.py'
    python /root/.local/share/oma-updater/test_updater.py
    owl-check 76-oma-update-app.owl
