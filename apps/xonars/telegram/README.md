# Telegram

Автор оригинала: [Xonars](https://github.com/Xonars/dev.omalauncher-widgets-another).

Локальная разработка Xonars.

Локальная упаковка и сопровождение: Xonars. Исходная лицензия: MIT. Уведомления о лицензиях в исходниках и ресурсах сохранены.

При первом запуске скачивается пакет ресурсов с этого магазина, проверяется SHA-256 и устанавливается в собственный каталог `~/.local/share/omalauncher-store/xonars-telegram/`. Требуется сеть; установленные ресурсы доступны офлайн. Личные файлы и исходные помощники телефона не перезаписываются.

---

## Подготовка на новой установке

Telegram использует Python-окружение в `~/.local/share/telegram-owl/venv`.
Если его ещё нет, выполните в терминале:

```sh
python -m venv ~/.local/share/telegram-owl/venv
~/.local/share/telegram-owl/venv/bin/python -m pip install 'Telethon==1.45.0' 'qrcode==8.2'
```

Затем откройте окно авторизации в приложении. Telegram API ID и API hash
получают на my.telegram.org. Сессии и настройки хранятся в Linux-профиле.
