# OMA Another Features 2.0

Локальные исходники приложения и виджета: ../84-oma-another-features-app.owl и ../85-oma-another-features.owl. Каталог — editorial подборка, не полный diff. Сохраняйте id и persist saved при обновлении. Поля featured/recent управляют обзором и вкладкой «Новое», symbol — текстовая иконка категории. История проверок в catalog.json.

## Скриншоты

Добавьте реальные PNG или WebP в screenshots/ и укажите в screenshots карточки { "src": "~/.config/omalauncher/widgets/oma-another-features/screenshots/имя.png", "caption": "Описание" }. Не указывайте несуществующие файлы. Первый снимок используется на обзорной карточке, все снимки — в подробностях, без обрезки. До добавления снимков отображается символ категории.

## Публикация

Из корня репозитория: python3 tools/build-local-store.py 84-oma-another-features-app.owl 85-oma-another-features.owl
Затем python3 tools/verify-local-store.py и компиляция каталогов java -jar tools/owl.jar index . / --apps / --faces. Сохраняйте прежние пакеты для старых клиентов. Для локальной проверки используйте owl-check и owl-send refresh. Проверяйте обзор, поиск, категории, Новое, избранное, возврат и ограничения.
