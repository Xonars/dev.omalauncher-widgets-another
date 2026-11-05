# Справочник разработчика

Локальная база знаний · редакция 26.10.2026


## 01 · Как пользоваться инструкцией

Маршрут, окружение и границы офлайна

Это справочник для самостоятельной работы в Bash. Он ничего не скачивает, не собирает и не устанавливает автоматически. Нажмите «Копировать команды», вставьте блок в терминал, проверьте результат и только затем переходите дальше. При ошибке остановитесь; не продолжайте следующие блоки.

Основной маршрут: 02 → 03 → 04 → 05 → 07 → 08 → 09 → 10 → 11. Раздел 06 — альтернативная подготовка обычного ПК Linux x86_64. На телефоне используется Arch Linux ARM внутри Oma Launcher (proot), а не оболочка Termux.

Чтение полностью офлайн. Для первой установки пакетов, клонирования, proot, Gradle и зависимостей нужен интернет. Повторная сборка без сети возможна только после заполнения кешей. Версии здесь сняты с локального проекта 26.10.2026: compileSdk 37, Build Tools 37.0.0; на телефоне NDK 28.2.13676358, CMake 4.4.4, JDK 25. Upstream может измениться.

Проверка окружения. Внутри Linux пользователь root не означает root-доступ к Android. Желательно несколько гигабайт свободного места под SDK, NDK, кеши и сборки; проверяйте фактический остаток.

```bash
uname -m
whoami
df -h "$HOME"
free -h
```


## 02 · Сохранить настройки и ключи

Резервная копия до экспериментов

Создайте копию настроек. Это копия Linux-каталога, а не полный бэкап Android-приложения. Храните отдельную копию вне Linux Oma: удаление приложения может удалить и его Linux-систему.

```bash
backup="$HOME/OMA-RESTORE/manual-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp -a "$HOME/.config/omalauncher" "$backup/"
printf '%s
' "$backup"
```

Существующий Oma Update использует ~/.android/debug.keystore и проверяет определённый сертификат. Не удаляйте и не перезаписывайте этот файл. Для нашего нового ключа будет отдельный каталог ~/.local/share/oma-signing. Ключ и пароль нужны для всех последующих обновлений; их потеря лишает возможности обновлять приложение с прежней подписью.


## 03 · Выкачать исходники

Отдельный проект для ручной сборки

Папка ~/omalauncher уже обслуживает Oma Update. Для экспериментов клонируйте отдельный проект. Команды рассчитаны на запуск из Bash; если каталог уже существует, изучите git status, вместо повторного clone используйте раздел 12.

```bash
pacman -Syu --needed git curl unzip libarchive patch make perl jdk25-openjdk cmake ninja python file binutils
mkdir -p "$HOME/projects"
git clone https://github.com/SimonSchubert/omalauncher.git "$HOME/projects/oma-manual"
cd "$HOME/projects/oma-manual"
git switch -c personal-build
git rev-parse HEAD
git status --short
```

Сохраните хеш коммита вместе с APK. Основные файлы: app/build.gradle.kts — Android и подпись; scripts/fetch-proot.sh — proot и NDK; gradle/libs.versions.toml — плагины; gradle/wrapper/gradle-wrapper.properties — Gradle. Не подменяйте версии наугад.

```bash
cd "$HOME/projects/oma-manual"
rg -n 'compileSdk|targetSdk|versionCode|versionName|ndkVersion|cmake|signing' app/build.gradle.kts
rg '^NDK_VERSION=' scripts/fetch-proot.sh
cat gradle/wrapper/gradle-wrapper.properties
```


## 04 · SDK на этом телефоне

Используем установленный ARM64 toolchain

SDK — платформы Android и инструменты упаковки. NDK — компилятор нативных .so, нужен Oma для proot и wlbridge. JDK запускает Gradle. SDK обычно лежит в домашнем каталоге и не требует системной установки. На этом телефоне он уже есть в /root/android-sdk. Добавьте переменные в текущий терминал; после его закрытия выполните блок снова.

```bash
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk
export ANDROID_HOME="$HOME/android-sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:/usr/bin/core_perl:$PATH"
java -version
"$ANDROID_HOME/build-tools/37.0.0/aapt2" version
"$ANDROID_HOME/build-tools/37.0.0/zipalign" -h
"$ANDROID_HOME/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-aarch64/bin/clang" --version
cmake --version
ninja --version
```

zipalign -h выводит справку и может завершиться ненулевым кодом; это не ошибка сборки. aapt2 и clang должны действительно запускаться. Наличие файлов само по себе недостаточно. Официальные Linux host-бинарники x86_64 не запускаются на aarch64. Java-компоненты SDK обычно переносимы, нативные инструменты — нет.

Запишите путь SDK только в экспериментальный проект. local.properties не публикуют в Git.

```bash
cd "$HOME/projects/oma-manual"
printf 'sdk.dir=%s
' "$ANDROID_HOME" > local.properties
file "$ANDROID_HOME/build-tools/37.0.0/aapt2"
file "$ANDROID_HOME/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-aarch64/bin/clang"
```


## 05 · Установить SDK на чистом ARM64

Восстановление окружения с нуля

На текущем телефоне пропустите установку, если проверки раздела 04 прошли. На чистой ARM64-системе понадобится сборка SDK/NDK для Linux aarch64. Использованный здесь проект: https://github.com/zhuwanhong/android-sdk-linux-arm64 — сторонняя сборка инструментов из исходников. Его инструкция установки доступна локально в ~/android-sdk-arm64-tools/docs/INSTALL.md.

Сначала подготовьте пакеты и исходники установщика. Следующий блок скачивает только репозиторий инструментов, не сам SDK.

```bash
pacman -Syu --needed git curl unzip tar file jdk25-openjdk cmake ninja clang lld lldb shaderc spirv-tools
mkdir -p "$HOME/tools"
git clone https://github.com/zhuwanhong/android-sdk-linux-arm64.git "$HOME/tools/android-sdk-arm64"
cd "$HOME/tools/android-sdk-arm64"
less docs/INSTALL.md
```

На странице Releases проекта скачайте ARM64 SDK и NDK, проверьте их контрольные суммы по данным релиза. Для описанной телефонной конфигурации нужен NDK 28.2.13676358. Не переименовывайте архив другого NDK в этот номер: при отсутствии готового архива используйте tools/build-ndk-version.sh по инструкции проекта. Ниже read запросит реальные пути уже скачанных архивов. Установщик дополнительно скачает Java-компоненты и sysroot Google, предложит условия лицензии, подключит системные CMake/Ninja и выполнит самопроверку.

```bash
cd "$HOME/tools/android-sdk-arm64"
read -r -p 'Путь к ARM64 SDK .tar.gz: ' sdk_archive
read -r -p 'Путь к ARM64 NDK 28.2.13676358 .tar.gz: ' ndk_archive
test -f "$sdk_archive" && test -f "$ndk_archive" && bash tools/install.sh --sdk-root "$HOME/android-sdk" --sdk-tgz "$sdk_archive" --ndk-tgz "$ndk_archive" --platform 37 --build-tools 37.0.0
```

Не продолжайте после провала самопроверки. Сопоставьте версию CMake, которую подключил установщик, с разделом 07; при отличии укажите реальную версию в Gradle. Сохраните архивы, лицензионные сведения и PROVENANCE-файлы для восстановления. Затем вернитесь к проверкам раздела 04.


## 06 · SDK на ПК Linux x86_64

Альтернативный маршрут без адаптации под телефон

Этот раздел предназначен для ПК с uname -m = x86_64. Используйте JDK, совместимый с Gradle и AGP выбранного коммита (для локальной конфигурации здесь JDK 25). На Arch зависимости ставятся командой из раздела 03. На другой системе используйте её пакетный менеджер.

Скачайте Linux Command line tools с https://developer.android.com/studio#command-line-tools-only и проверьте SHA-256 по странице загрузки. Распакуйте так, чтобы sdkmanager находился в ~/android-sdk/cmdline-tools/latest/bin/sdkmanager. Этот блок запросит путь к ZIP; каталог latest должен ещё не существовать.

```bash
export ANDROID_HOME="$HOME/android-sdk"
read -r -p 'Путь к commandlinetools-linux ZIP: ' tools_zip
mkdir -p "$ANDROID_HOME/cmdline-tools"
tmpdir=$(mktemp -d)
unzip "$tools_zip" -d "$tmpdir"
mv -T "$tmpdir/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
sdkmanager --sdk_root="$ANDROID_HOME" --licenses
```

Прочитайте и примите лицензии интерактивно. Для текущего локального исходника upstream закреплён NDK 30.0.16248370; извлекайте номер из скрипта, а не из этого текста. sdkmanager ещё поддерживает установку пакетов; документация Google также предлагает новый Android CLI. На ПК раздел 07 не выполняется.

```bash
cd "$HOME/projects/oma-manual"
ndk_ver=$(sed -n 's/^NDK_VERSION=//p' scripts/fetch-proot.sh)
sdkmanager --sdk_root="$ANDROID_HOME" "platform-tools" "platforms;android-37" "build-tools;37.0.0" "ndk;$ndk_ver" "cmake;3.22.1"
printf 'sdk.dir=%s
' "$ANDROID_HOME" > local.properties
./gradlew --version
```


## 07 · Адаптация проекта для ARM64

Только экспериментальная копия, контроль формата

В текущем Oma Update применяются NDK 28.2.13676358, CMake 4.4.4 и Build Tools 37.0.0. Повторим адаптацию в отдельном клоне. Скрипт ниже сначала проверяет формат всех замен и наличие инструментов; если upstream изменился, он остановится до записи. Повторно запускать его после успешного применения не нужно.

```bash
cd "$HOME/projects/oma-manual"
python - <<'PYCODE'
from pathlib import Path
sdk = Path.home() / 'android-sdk'
for name in ['ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-aarch64/bin/clang', 'build-tools/37.0.0/aapt2']:
    assert (sdk/name).exists(), f'Нет инструмента: {name}'
g = Path('app/build.gradle.kts')
p = Path('scripts/fetch-proot.sh')
gt, pt = g.read_text(), p.read_text()
old = '    ndkVersion = prootNdk'
assert gt.count(old) == 1, 'Изменился формат ndkVersion'
gt = gt.replace(old, '    buildToolsVersion = "37.0.0"\n    ndkVersion = "28.2.13676358"')
old = 'cmake { path = file("src/main/cpp/CMakeLists.txt") }'
assert gt.count(old) == 1, 'Изменился формат cmake'
gt = gt.replace(old, 'cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "4.4.4" }')
import re
pt, n = re.subn(r'^NDK_VERSION=.*$', 'NDK_VERSION=28.2.13676358', pt, flags=re.M)
assert n == 1, 'Изменился формат NDK_VERSION'
g.write_text(gt)
p.write_text(pt)
PYCODE
git diff -- app/build.gradle.kts scripts/fetch-proot.sh
```

Убедитесь, что в diff только ожидаемые изменения. В используемом исходнике fetch-proot.sh сам выбирает prebuilt/*/bin. Если там жёстко прописан linux-x86_64, замените на linux-aarch64 вручную. CMake должен находиться в SDK или быть подключён установленным ARM64 toolchain; проверьте, что версия 4.4.4 доступна. Архивы обычного NDK Google эту проблему не решают.


## 08 · Собрать APK и проверить проект

proot, Gradle, тесты и содержимое APK

Сначала соберите proot и его библиотеки. Нужен интернет: скрипт скачивает исходники, зависимости Termux и проверяет закреплённые SHA-256. Не пропускайте его: APK без этих .so может установиться, но Linux не заработает.

```bash
cd "$HOME/projects/oma-manual"
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk
export ANDROID_HOME="$HOME/android-sdk"
export PATH="$JAVA_HOME/bin:/usr/bin/core_perl:$PATH"
bash scripts/fetch-proot.sh
```

Телефон ARM64: AAPT2 принудительно берём из установленного ARM64 SDK. Два рабочих потока и 1536 МБ heap ограничивают нагрузку, но Gradle/Kotlin/NDK потребуют память сверх этого. При нехватке памяти используйте --max-workers=1 и закройте лишние приложения. Wrapper скачает закреплённый проектом Gradle.

```bash
cd "$HOME/projects/oma-manual"
set -o pipefail
./gradlew :app:assembleDebug :owl:test :app:testDebugUnitTest :app:lintDebug --no-daemon --max-workers=2 -Dorg.gradle.jvmargs="-Xmx1536m -Dfile.encoding=UTF-8" -Pandroid.aapt2FromMavenOverride="$ANDROID_HOME/build-tools/37.0.0/aapt2" 2>&1 | tee build-manual.log
```

На ПК x86_64 используйте ту же команду без -Pandroid.aapt2FromMavenOverride. Успех — BUILD SUCCESSFUL и APK в app/build/outputs/apk/debug/app-debug.apk. Debug APK автоматически подписан отладочным ключом; новый личный ключ создаём дальше. Проверим пять библиотек; при нехватке хотя бы одной блок завершится ошибкой.

```bash
cd "$HOME/projects/oma-manual"
python - <<'PYCODE'
from zipfile import ZipFile
p = 'app/build/outputs/apk/debug/app-debug.apk'
with ZipFile(p) as z:
    for lib in ['proot', 'proot-loader', 'talloc', 'android-shmem', 'wlbridge']:
        name = f'lib/arm64-v8a/lib{lib}.so'
        assert name in z.namelist(), f'Нет {name}'
        print('OK', name)
PYCODE
```


## 09 · Создать собственный ключ

Отдельный keystore с интерактивным паролем

Один ключ создаётся один раз и используется для будущих версий. В примере JKS, alias oma-personal, RSA 3072. Пароли keytool запросит сам: не вводите их в команды, Git или заметки. Для удобства можно выбрать одинаковый пароль хранилища и ключа. Существующий файл этим блоком не перезаписывается.

```bash
umask 077
mkdir -p "$HOME/.local/share/oma-signing"
keyfile="$HOME/.local/share/oma-signing/oma-personal.jks"
if test -e "$keyfile"; then
  printf 'Ключ уже существует: %s
' "$keyfile"
else
  keytool -genkeypair -v -storetype JKS -keystore "$keyfile" -alias oma-personal -keyalg RSA -keysize 3072 -validity 10000
fi
keytool -list -v -keystore "$keyfile" -alias oma-personal
```

Запишите SHA-256 сертификата. Сохраните keystore на отдельный носитель или в зашифрованный архив, пароль — отдельно. SHA-256 сертификата можно публиковать; сам keystore и пароль должны оставаться приватными. Не путайте этот SHA-256 с хешем APK: хеш файла меняется при каждой сборке.


## 10 · Подписать APK своим ключом

Выравнивание → подпись → проверка

Подпишем отдельную копию собранного debug APK личным ключом. Она останется отладочной по свойствам сборки — личная подпись не превращает её в release. apksigner заменяет прежнюю APK-подпись; исходный файл остаётся в каталоге сборки. Сначала zipalign, потом apksigner, после подписи APK не изменяют.

```bash
cd "$HOME/projects/oma-manual"
export ANDROID_HOME="$HOME/android-sdk"
bt="$ANDROID_HOME/build-tools/37.0.0"
mkdir -p "$HOME/APK"
stamp=$(date +%Y%m%d-%H%M%S)
short_commit=$(git rev-parse --short HEAD)
out="$HOME/APK/omalauncher-personal-$short_commit-$stamp.apk"
"$bt/zipalign" -P 16 -f -v 4 app/build/outputs/apk/debug/app-debug.apk "$HOME/APK/oma-aligned.apk"
"$bt/apksigner" sign --ks "$HOME/.local/share/oma-signing/oma-personal.jks" --ks-key-alias oma-personal --out "$out" "$HOME/APK/oma-aligned.apk"
```

Не продолжайте, если подпись завершилась ошибкой. Пароль apksigner запросит интерактивно. Следующий блок выполняйте в том же терминале: в нём определены bt и out. Сравните SHA-256 сертификата с разделом 09; проверьте успешное выравнивание. Сохраните исходный коммит, diff и хеш файла рядом.

```bash
"$bt/apksigner" verify --verbose --print-certs "$out"
"$bt/zipalign" -c -P 16 -v 4 "$out"
sha256sum "$out" > "$out.sha256"
git rev-parse HEAD > "$out.commit.txt"
git diff > "$out.source.patch"
printf 'Готово: %s
' "$out"
```

Для настоящей release-сборки проект поддерживает keystore.properties: storeFile, storePassword, keyAlias, keyPassword. Используйте абсолютный путь к нашему JKS и права 600; файл содержит пароли, его нельзя коммитить. После настройки запускайте :app:assembleRelease с ARM64-параметром AAPT2 из раздела 08 и проверяйте app/build/outputs/apk/release/app-release.apk. Без keystore.properties текущий Gradle подписывает release отладочным ключом; всегда проверяйте сертификат. Ручной путь выше не требует хранить пароли в проекте.


## 11 · Передать APK в Android

APK Share и совместимость обновления

В APK Share укажите ~/APK, нажмите Start и Download у файла omalauncher-personal-….apk. Откройте скачанный APK в Android и подтвердите установку. Промежуточный oma-aligned.apk не устанавливайте. Адрес 127.0.0.1 ограничивает сервер этим устройством. Для чтения списка из терминала:

```bash
python "$HOME/.config/omalauncher/widgets/apk-share/backend.py" list --directory "$HOME/APK"
```

Android разрешает обычное обновление только при совместимой подписи и допустимом versionCode. Новый личный ключ не совпадёт с Google Play или текущим ключом Oma Update. Типичная ошибка — «пакет конфликтует». Не удаляйте рабочий лаунчер ради установки: вместе с ним можно потерять Linux и данные. Сначала резервная копия вне приложения и другой доступный домашний экран. При необходимости тестируйте отдельный applicationId после проверки всех зависимостей от имени пакета.

После перехода на личную подпись будущие APK подписывайте этим же ключом. Нынешний Oma Update продолжит использовать свой старый debug.keystore и проверку сертификата; для обновлений новым ключом его потребуется отдельно перенастроить. Этот справочник настройки сборщика и текущую подпись не меняет.


## 12 · Обновления и работа офлайн

Ветки, кеши и воспроизводимость

Перед обновлением просмотрите изменения. Сохраните свои адаптации коммитом или резервной копией; не используйте reset --hard и не удаляйте проект. Fetch обновляет сведения о main, не затрагивая рабочие файлы.

```bash
cd "$HOME/projects/oma-manual"
git status --short
git diff
git fetch origin main
git log --oneline -n 10 HEAD..origin/main
```

Когда рабочее дерево сохранено, осознанно выполните merge origin/main в личной ветке. При конфликтах разберите их до сборки. Перечитайте версии SDK/NDK и снова проверьте адаптацию, proot, тесты и подпись. Не создавайте новый ключ при каждом обновлении.

Gradle --offline запрещает скачивание Gradle-зависимостей, но wrapper должен быть уже загружен. fetch-proot.sh тоже требует сети и сам не становится офлайн от этого флага. Для повторной сборки сохраните подготовленные jniLibs, SDK/NDK, JDK, исходники и ~/.gradle (caches и wrapper). На том же подготовленном проекте:

```bash
cd "$HOME/projects/oma-manual"
./gradlew :app:assembleDebug --offline --no-daemon --max-workers=2 -Pandroid.aapt2FromMavenOverride="$HOME/android-sdk/build-tools/37.0.0/aapt2"
```


## 13 · Ошибки и диагностика

Как найти причину, не ломая окружение

AAPT2 Daemon startup failed / Exec format error: чаще запущен бинарник x86_64 на ARM64. Проверьте file, выполните aapt2 version и передайте override. Для clang проверьте linux-aarch64. Не заменяйте ARM64 SDK обычным Linux SDK поверх.

SDK location not found: проверьте ANDROID_HOME и local.properties. CMake/NDK missing: версия в Gradle должна совпадать с реально установленной, NDK_VERSION в fetch-proot.sh — с NDK для proot. Нельзя исправить несовпадение простым переименованием каталога.

404 в fetch-proot.sh: Termux мог убрать закреплённый пакет. Проверьте свежий upstream; обновляйте версии, SHA-256 и ссылки лицензий согласованно. Не отключайте проверку хешей. Ошибки SSL решайте исправлением времени, CA и сети, не curl -k.

Gradle daemon disappeared / процесс Killed: проверьте память, место и журналы; уменьшите число workers. Для диагностики повторите упавшую задачу с --stacktrace, а не всю сборку без разбора. Ошибки тестов и lint читайте в отчётах, не скрывайте исключением задач.

```bash
cd "$HOME/projects/oma-manual"
tail -n 100 build-manual.log
find app/build/reports owl/build/reports -maxdepth 3 -type f -name '*.html' 2>/dev/null
git status --short
```

Подпись не совпала: проверьте alias и сертификат через keytool и apksigner. INSTALL_FAILED_UPDATE_INCOMPATIBLE — обычно разные ключи, VERSION_DOWNGRADE — более низкий versionCode. Ошибка Linux после установки — проверьте наличие и ABI пяти .so, затем журналы. Не генерируйте новый ключ как способ исправления.


## 14 · Пополнять базу знаний

Файлы, источники и правила редакции

Приложение содержит весь текст внутри .owl: чтение не требует сети или запущенного Linux. Исходник базы находится в ~/.config/omalauncher/widgets/developer-guide/articles.json. Статья: id (уникальная строка), title, desc, blocks; каждый блок содержит text и code (пустая строка, если команд нет). Избранное хранится по id — не меняйте старые id при добавлении статей.

Добавляйте проверенные команды, область применимости, версии и ожидаемый результат. Отмечайте отдельно: проверено чтением исходников, проверено запуском инструмента или проверено полной сборкой. Эта редакция сопоставлена с локальными исходниками и Oma Update; новую полную сборку для подготовки текста не запускали. Не записывайте в справочник секреты.

После редактирования JSON пересоберите автономный .owl и Markdown-копию, затем проверьте приложение. Путь PNG напечатает owl-check; его нужно открыть для проверки интерфейса.

```bash
python "$HOME/.config/omalauncher/widgets/developer-guide/build.py"
owl-check "$HOME/.config/omalauncher/widgets/81-developer-guide.owl"
less "$HOME/.config/omalauncher/widgets/developer-guide/README.md"
```

Источники: локальный ~/omalauncher, коммит f3e11278963a772a0133b08f2b5d3983649fe654; README.md, app/build.gradle.kts, scripts/fetch-proot.sh, Gradle wrapper; ~/.local/share/oma-updater/updater.py и build-main.sh; ~/android-sdk-arm64-tools/docs/INSTALL.md. Онлайн для последующей сверки: https://github.com/SimonSchubert/omalauncher · https://github.com/zhuwanhong/android-sdk-linux-arm64 · https://developer.android.com/tools/sdkmanager · https://developer.android.com/tools/apksigner · https://developer.android.com/tools/zipalign. Дата редакции: 26.10.2026.
