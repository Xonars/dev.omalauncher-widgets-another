import asyncio
import fcntl
import getpass
import json
import os
from pathlib import Path
import sys
import time

os.umask(0o077)
ROOT = Path.home() / '.local/state/telegram-owl'
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
CONFIG = ROOT / 'config.json'
MAX_FILE_SIZE = 100 * 1024 * 1024
DOWNLOADS = Path('/sdcard/Download/Telegram')


def transfer_progress(current, total):
    pass


async def send_content(client, action, args):
    chat = int(args[0])
    text = args[1]
    reply = int(args[2]) if len(args) > 2 and args[2] else 0
    if reply < 0:
        raise ValueError('Неверный номер сообщения для ответа')
    if action == 'send-file':
        path = Path(args[3]).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError('Выберите обычный файл')
        if path.stat().st_size > MAX_FILE_SIZE:
            raise ValueError('Пока поддерживаются файлы до 100 МБ')
        if len(text) > 1024:
            raise ValueError('Подпись к файлу длиннее 1024 символов')
        message = await client.send_file(chat, str(path), caption=text,
                                         reply_to=reply or None, parse_mode=None,
                                         force_document=True, progress_callback=transfer_progress)
    else:
        if not text.strip():
            raise ValueError('Сообщение пустое')
        if len(text) > 4096:
            raise ValueError('Сообщение длиннее 4096 символов. Разделите его на несколько сообщений.')
        message = await client.send_message(chat, text, reply_to=reply or None, parse_mode=None)
    return dict(ok=True, id=message.id)


async def download_attachment(client, args):
    import re
    import tempfile
    import uuid
    message = await client.get_messages(int(args[0]), ids=int(args[1]))
    if message is None or message.file is None:
        raise ValueError('Вложение недоступно или сообщение удалено')
    if (message.file.size or 0) > MAX_FILE_SIZE:
        raise ValueError('Пока поддерживается скачивание файлов до 100 МБ')
    original = message.file.name or ('photo' + (message.file.ext or '.jpg'))
    name = re.sub(r'[\x00-\x1f/\\]', '_', original).strip(' .')[:160] or 'attachment'
    directory = DOWNLOADS
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (uuid.uuid4().hex[:8] + '_' + name)
    with tempfile.TemporaryDirectory(prefix='.download-', dir=directory) as temp:
        partial = Path(temp) / 'content.part'
        with partial.open('wb') as output:
            result = await message.download_media(file=output, progress_callback=transfer_progress)
        if result is None or not partial.is_file():
            raise ValueError('Telegram не вернул файл')
        partial.replace(target)
    return dict(ok=True, path=str(target), name=name)


def emit(data):
    print(json.dumps(data, ensure_ascii=False))


def describe_code(sent):
    kind = type(getattr(sent, 'type', None)).__name__
    descriptions = {
        'SentCodeTypeApp': 'Код отправлен в служебный чат «Telegram» в уже открытых сессиях этого номера. Проверьте другой телефон, компьютер и архив чатов.',
        'SentCodeTypeSms': 'Код отправлен по SMS на указанный номер.',
        'SentCodeTypeSmsWord': 'По SMS отправлено слово: введите его целиком.',
        'SentCodeTypeSmsPhrase': 'По SMS отправлена фраза: введите её целиком.',
        'SentCodeTypeCall': 'Telegram позвонит и продиктует код.',
        'SentCodeTypeFlashCall': 'Код — номер входящего короткого звонка.',
        'SentCodeTypeMissedCall': 'Код — последние цифры номера пропущенного звонка.',
        'SentCodeTypeEmailCode': 'Код отправлен на почту, привязанную к Telegram.',
    }
    if kind not in descriptions:
        raise RuntimeError(f'Этот способ входа ({kind}) пока не поддерживается. Войдите в официальное приложение Telegram, затем повторите вход здесь.')
    print(descriptions[kind], flush=True)
    if getattr(sent, 'next_type', None) is not None:
        print('Если код не пришёл, введите /resend вместо кода. Повторная отправка будет доступна после указанной Telegram задержки.', flush=True)
    else:
        print('Telegram не предложил запасной способ доставки. Принудительно отправить SMS нельзя.', flush=True)


async def receive_code(client, phone, sent, delivery=None):
    from telethon.tl.functions.auth import ResendCodeRequest
    describe_code(sent)
    if delivery is None:
        delivery = {}
    delivery.setdefault('available_at', time.monotonic() + (getattr(sent, 'timeout', None) or 0))
    delivery.setdefault('resends', 0)
    while True:
        code = (await asyncio.to_thread(getpass.getpass, 'Код или /resend (ввод скрыт): ')).strip()
        if code.lower() != '/resend':
            if not code:
                print('Введите код или /resend.')
                continue
            # SMS phrases contain meaningful spaces.
            if type(sent.type).__name__ not in ('SentCodeTypeSmsWord', 'SentCodeTypeSmsPhrase'):
                code = code.replace(' ', '')
            return code, sent
        if sent.next_type is None:
            print('Telegram не разрешил повторную отправку. Проверьте указанный выше способ доставки.')
            continue
        if delivery['resends'] >= 2:
            raise RuntimeError('Код не доставлен после повторных запросов. Попробуйте позже через официальное приложение Telegram.')
        remaining = delivery['available_at'] - time.monotonic()
        if remaining > 0:
            print(f'Ждём разрешённую Telegram задержку: {int(remaining) + 1} сек.…', flush=True)
            await asyncio.sleep(remaining)
        sent = await asyncio.wait_for(client(ResendCodeRequest(phone, sent.phone_code_hash)), 30)
        delivery['resends'] += 1
        describe_code(sent)
        delivery['available_at'] = time.monotonic() + (getattr(sent, 'timeout', None) or 0)


async def image_preview(msg, chat_id, budget):
    """Download images atomically; one bad attachment must not hide the chat."""
    photo = msg.photo
    document = msg.document
    is_image = photo is not None or (
        document is not None and document.mime_type in
        ('image/jpeg', 'image/png', 'image/webp', 'image/gif'))
    if not is_image:
        return dict(image=None, image_status=None)
    media = photo or document
    cache = ROOT / 'images'
    cache.mkdir(mode=0o700, exist_ok=True)
    # Include media ID so replacing a message's photo invalidates its cache.
    stem = f'{chat_id}_{msg.id}_{media.id}'
    thumb = -1 if photo is not None or document.thumbs else None
    suffix = '.jpg' if thumb is not None else {
        'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'
    }.get(document.mime_type, '.jpg')
    target = cache / (stem + suffix)
    if target.exists() and target.stat().st_size:
        return dict(image=str(target), image_status='ready')
    if thumb is None and document.size > 10 * 1024 * 1024:
        return dict(image=None, image_status='Изображение больше 10 МБ, без миниатюры')
    if budget[0] <= 0 or time.monotonic() >= budget[1]:
        return dict(image=None, image_status='Загрузка фото…')
    budget[0] -= 1
    temporary = cache / (stem + '.part')
    try:
        # Passing a binary stream prevents Telethon from altering the file suffix.
        with temporary.open('wb') as output:
            downloaded = await asyncio.wait_for(
                msg.download_media(file=output, thumb=thumb),
                timeout=max(0.1, min(5, budget[1] - time.monotonic())))
        if downloaded is None or not temporary.stat().st_size:
            return dict(image=None, image_status='Изображение недоступно')
        temporary.replace(target)
        return dict(image=str(target), image_status='ready')
    except Exception:
        return dict(image=None, image_status='Не удалось загрузить фото · повтор при обновлении')
    finally:
        temporary.unlink(missing_ok=True)


async def avatar_preview(client, entity, chat_id, budget):
    photo = getattr(entity, 'photo', None)
    photo_id = getattr(photo, 'photo_id', None)
    if not photo_id:
        return None
    cache = ROOT / 'avatars'
    cache.mkdir(mode=0o700, exist_ok=True)
    target = cache / f'{chat_id}_{photo_id}.jpg'
    if target.exists() and target.stat().st_size:
        return str(target)
    if budget[0] <= 0 or time.monotonic() >= budget[1]:
        return None
    budget[0] -= 1
    temporary = target.with_suffix('.part')
    try:
        with temporary.open('wb') as output:
            downloaded = await asyncio.wait_for(
                client.download_profile_photo(entity, file=output, download_big=False),
                timeout=max(0.1, min(3, budget[1] - time.monotonic())))
        if downloaded is not None and temporary.stat().st_size:
            temporary.replace(target)
            return str(target)
    except Exception:
        pass
    finally:
        temporary.unlink(missing_ok=True)
    return None


def clear_cache():
    """Only delete cached media; never touch API credentials or the session."""
    total = 0
    count = 0
    for name in ('images', 'avatars'):
        directory = ROOT / name
        if directory.is_symlink():
            directory.unlink()
            continue
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            if entry.is_symlink():
                entry.unlink()
            elif entry.is_file():
                size = entry.stat().st_size
                entry.unlink()
                total += size
                count += 1
    return dict(ok=True, bytes=total, files=count)


async def login_qr(client):
    import qrcode
    from telethon import errors
    print('В Telegram: Настройки → Устройства → Подключить устройство.\n'
          'Отсканируйте QR с другого экрана. QR обновляется автоматически.\n'
          'Ctrl+C — отменить. Не передавайте QR посторонним.', flush=True)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        qr = await asyncio.wait_for(client.qr_login(), 30)
        waiter = asyncio.create_task(qr.wait())
        await asyncio.sleep(0)
        try:
            image = qrcode.QRCode(border=4)
            image.add_data(qr.url)
            image.make(fit=True)
            print('\033[2J\033[HВход в Telegram · QR\n', flush=True)
            image.print_ascii(tty=False, invert=True)
            print('Telegram → Настройки → Устройства → Подключить устройство\n'
                  'QR действует недолго и обновляется автоматически. Ctrl+C — отмена.', flush=True)
            await waiter
            return
        except asyncio.TimeoutError:
            continue
        except errors.SessionPasswordNeededError:
            for attempt in range(3):
                password = await asyncio.to_thread(getpass.getpass, 'Пароль двухэтапной проверки (ввод скрыт): ')
                try:
                    await asyncio.wait_for(client.sign_in(password=password), 30)
                    return
                except errors.PasswordHashInvalidError:
                    if attempt == 2:
                        raise
                    print('Неверный пароль. Повторите ввод.')
        finally:
            if not waiter.done():
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
    raise RuntimeError('Время входа по QR истекло. Запустите вход ещё раз.')


async def execute(action, args):
    if action == 'clear-cache':
        return clear_cache()
    from telethon import TelegramClient, errors, utils
    if action in ('auth', 'auth-qr'):
        print('Telegram · Первый вход\nAPI ID и API hash: https://my.telegram.org → API development tools\n')
        if not CONFIG.exists():
            api_id = int(input('API ID: ').strip())
            api_hash = getpass.getpass('API hash (скрыт): ').strip()
            if len(api_hash) != 32 or any(c not in '0123456789abcdefABCDEF' for c in api_hash):
                raise ValueError('API hash должен содержать 32 шестнадцатеричных символа')
            CONFIG.write_text(json.dumps(dict(api_id=api_id, api_hash=api_hash)))
    if not CONFIG.exists():
        return dict(authorized=False, chats=[], messages=[])
    config = json.loads(CONFIG.read_text())
    client = TelegramClient(str(ROOT / 'account'), config['api_id'], config['api_hash'],
                            connection_retries=1, request_retries=1, timeout=12,
                            flood_sleep_threshold=0)
    try:
        if action in ('auth', 'auth-qr'):
            print('Подключение к Telegram (до 20 секунд)…', flush=True)
        await asyncio.wait_for(client.connect(), 20)
        if action in ('auth', 'auth-qr'):
            if not await asyncio.wait_for(client.is_user_authorized(), 20):
                if action == 'auth-qr':
                    await login_qr(client)
                    print('\nВход выполнен. Вернитесь в Owl Telegram и нажмите ↻.')
                    return dict(ok=True)
                phone = input('Номер телефона (+код страны): ').strip()
                print('Запрашиваем код…', flush=True)
                sent = await asyncio.wait_for(client.send_code_request(phone), 30)
                delivery = {}
                for attempt in range(3):
                    code, sent = await receive_code(client, phone, sent, delivery)
                    try:
                        await asyncio.wait_for(client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash), 30)
                        break
                    except errors.SessionPasswordNeededError:
                        for password_attempt in range(3):
                            password = await asyncio.to_thread(getpass.getpass, 'Пароль двухэтапной проверки (ввод скрыт): ')
                            try:
                                await asyncio.wait_for(client.sign_in(password=password), 30)
                                break
                            except errors.PasswordHashInvalidError:
                                if password_attempt == 2:
                                    raise
                                print('Неверный пароль. Повторите ввод.')
                        break
                    except errors.PhoneCodeInvalidError:
                        if attempt == 2:
                            raise
                        print('Неверный код. Повторите ввод.')
            print('\nВход выполнен. Вернитесь в Owl Telegram и нажмите «Обновить».')
            return dict(ok=True)
        if not await client.is_user_authorized():
            return dict(authorized=False, chats=[], messages=[])
        if action == 'logout':
            await client.log_out()
            return dict(ok=True)
        if action in ('send', 'send-file'):
            return await send_content(client, action, args)
        if action == 'download':
            return await download_attachment(client, args)
        selected = int(args[0]) if args else 0
        limit = max(30, min(int(args[1]), 200)) if len(args) > 1 else 50
        media_enabled = len(args) < 3 or args[2].lower() in ('true', '1')
        avatar_budget = [8 if media_enabled else 0, time.monotonic() + 5]
        chats = []
        async for dialog in client.iter_dialogs(limit=200):
            last = dialog.message
            avatar = await avatar_preview(client, dialog.entity, dialog.id, avatar_budget)
            chats.append(dict(id=dialog.id, avatar=avatar, name=dialog.name or 'Без имени',
                              pinned=dialog.pinned, archived=dialog.archived,
                              unread=dialog.unread_count,
                              preview=(last.message or ('[Фото]' if last.photo else '[Вложение]'))[:160] if last else '',
                              date=last.date.timestamp() if last else 0))
        messages = []
        if selected:
            history = await client.get_messages(selected, limit=limit)
            # Bound media work so large histories cannot time out every refresh.
            budget = [6 if media_enabled else 0, time.monotonic() + 12]
            senders = {}
            reply_previews = {m.id: (m.message or (m.file.name if m.file else None) or 'Вложение')[:120]
                              for m in history}
            for msg in history:
                sender_id = msg.sender_id
                if sender_id not in senders:
                    try:
                        sender = await msg.get_sender()
                        senders[sender_id] = utils.get_display_name(sender) if sender else ''
                    except (ValueError, errors.RPCError):
                        senders[sender_id] = 'Неизвестный отправитель'
                image = await image_preview(msg, selected, budget)
                has_image = image['image_status'] is not None
                file = msg.file
                messages.append(dict(id=msg.id,
                                     text=msg.message or ('' if has_image or file else '[Служебное сообщение]'),
                                     file_name=(file.name or ('Фото' if msg.photo else 'Вложение')) if file else None,
                                     file_size=file.size if file else 0,
                                     reply_id=msg.reply_to_msg_id,
                                     reply_text=reply_previews.get(msg.reply_to_msg_id),
                                     mine=msg.out, sender=senders[sender_id],
                                     edited=msg.edit_date is not None,
                                     date=msg.date.timestamp(), **image))
        return dict(authorized=True, chats=chats, messages=messages, chat=selected)
    finally:
        await asyncio.wait_for(client.disconnect(), 5)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'view'
    if action == 'job-status':
        from jobs import status
        emit(status())
        return
    if action == 'start-job':
        from jobs import start
        try:
            emit(start(sys.argv[2:]))
        except Exception as exc:
            emit(dict(ok=False, error=str(exc) or type(exc).__name__))
        return
    try:
        with (ROOT / 'lock').open('w') as lock:
            deadline = time.monotonic() + (50 if action in ('auth', 'auth-qr', 'send', 'logout') else 2)
            waiting = False
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if action in ('auth', 'auth-qr') and not waiting:
                        print('Ожидаем завершения другой операции Telegram…', flush=True)
                        waiting = True
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Telegram занят: дождитесь завершения операции или закройте другое окно входа')
                    time.sleep(0.1)
            coro = execute(action, sys.argv[2:])
            result = asyncio.run(coro if action in ('auth', 'auth-qr') else asyncio.wait_for(coro, 45))
        if action not in ('auth', 'auth-qr'):
            emit(result)
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        if type(exc).__name__ == 'FloodWaitError':
            message = f'Telegram ограничил запросы. Повторите через {exc.seconds} сек. Не запрашивайте код до окончания этого времени.'
        elif type(exc).__name__ == 'PhoneCodeExpiredError':
            message = 'Срок действия кода истёк. Закройте окно и начните вход заново.'
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            message = 'Не удалось подключиться к Telegram. Проверьте интернет и доступ к Telegram из Linux; при блокировке нужен VPN, работающий для Linux.'
        if action in ('auth', 'auth-qr'):
            print(f'Ошибка входа: {message}')
        else:
            emit(dict(ok=False, error=message))
    if action in ('auth', 'auth-qr'):
        input('\nEnter — закрыть окно…')

if __name__ == '__main__':
    main()
