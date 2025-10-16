import os
import random
import logging
import asyncio
import zoneinfo
from typing import Dict

from dotenv import load_dotenv
from telethon.tl.custom import Button
from datetime import datetime
from telethon import TelegramClient, events

from observability.metrics import (
    init_metrics_server,
    set_app_start_timestamp,
    inc_alerts_total_metric,
    inc_alerts_handled_metric,
    inc_errors_total_metric
)
from observability.statistics import send_statistics

# Загрузка конфигурации
load_dotenv()

# Конфигурационные константы
CONFIG = {
    'TZ': zoneinfo.ZoneInfo(os.getenv('TIMEZONE', 'Europe/Moscow')),
    'LOG_LEVEL': logging.os.getenv('LOG_LEVEL', 'INFO').upper(),
    'METRICS_SERVER_PORT': os.getenv('METRICS_SERVER_PORT'),
    'TRIGGERS': set(filter(None, os.getenv('TRIGGERS', '').split(','))),
    'USERBOT_API_ID': os.getenv('USERBOT_API_ID'),
    'USERBOT_API_HASH': os.getenv('USERBOT_API_HASH'),
    'USERBOT_PHONE_NUMBER': os.getenv('USERBOT_PHONE_NUMBER'),
    'BOT_TOKEN': os.getenv('BOT_TOKEN'),
    'SOURCE_CHAT_ID': int(os.getenv('SOURCE_CHAT_ID')),
    'TARGET_CHAT_ID': int(os.getenv('TARGET_CHAT_ID')),
    'IGNORE_MSG_FROM_ID': int(os.getenv('IGNORE_MSG_FROM_ID'))
}

# Настройка логирования
logging.basicConfig(
    level=CONFIG['LOG_LEVEL'],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('dvp_coc_bot')
logging.getLogger('telethon').setLevel(logging.ERROR)
logging.getLogger('asyncio').setLevel(logging.ERROR)

logger.info(f"------ SUMMARY ------")
logger.info(f"Loaded {len(CONFIG['TRIGGERS'])} trigger words from config")

BUTTONS = [
    [Button.inline("Принять", data=b"received")],
    [
        Button.inline("Это флап", data=b"flapping"),
        Button.inline("Не критично", data=b"not_critical")
    ],
    [Button.inline("Вручную / другое", data=b"other")]
]

RESPONSES = {
    b"received": (
        "~~{text}~~\n\n**Алерт принят в работу, отправлено сообщение в COC!**\n\nОтветственный - {userinfo}",
        [
            "Принято, спасибо",
            "Приняли в работу",
            "Ок, смотрю",
            "Щас гляну, спасибо большое",
            "Угу, принято, спасибо"
        ]
    ),
    b"not_critical": (
        "~~{text}~~\n\n**Алерт принят как некритический, отправлено сообщение в COC!**\n\nОтветственный - {userinfo}",
        [
            "Не критично, починим попозже",
            "Принято, не срочно",
            "Это не страшно, спасибо",
            "Ага, спасибо! Принято, но обработаем чуть позже - критики нет"
        ]
    ),
    b"flapping": (
        "~~{text}~~\n\n**Алерт принят как флапающий, отправлено сообщение в COC!**\n\nОтветственный - {userinfo}",
        [
            "Ага, похоже на флап",
            "Принято, скорее всего флап",
            "Пока не актуально",
            "Флапает, да - скоро перестанет"
        ]
    ),
    b"other": (
        "~~{text}~~\n\n**Алерт проигнорирован или обработан вручную.**\n\nОтветственный - {userinfo}",
        None
    )
}

# Глобальная очередь сообщений
message_queue: Dict[int, int] = {}

async def initialize_clients() -> tuple[TelegramClient, TelegramClient]:
    """Инициализация клиентов Telegram"""
    try:
        logger.info(f"------ BOTS INITIALIZATION ------")
        logger.info("Initializing Telegram clients...")
        bot = TelegramClient('bot', CONFIG['USERBOT_API_ID'], CONFIG['USERBOT_API_HASH'])
        userbot = TelegramClient('userbot', CONFIG['USERBOT_API_ID'], CONFIG['USERBOT_API_HASH'])

        await bot.start(bot_token=CONFIG['BOT_TOKEN'])
        logger.info("Bot client started successfully")
        bot_info = await bot.get_me()
        logger.debug(f"Bot logged as {bot_info.first_name} {bot_info.last_name or '\b'} (@{bot_info.username}, id: {bot_info.id})")

        await userbot.start(phone=CONFIG['USERBOT_PHONE_NUMBER'])
        logger.info("Userbot client started successfully")
        userbot_info = await userbot.get_me()
        logger.debug(f"UserBot logged as {userbot_info.first_name} {userbot_info.last_name} (@{userbot_info.username}, id: {userbot_info.id})")

        return bot, userbot
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        raise

async def handle_callback(event: events.CallbackQuery.Event, userbot: TelegramClient) -> None:
    """Обработка callback-запросов от кнопок"""
    try:
        logger.debug(f"Received callback: {event.data}")

        if event.data not in RESPONSES:
            logger.warning(f"Unknown callback data: {event.data}")
            return

        # Получение ID сообщений и их удаление после
        int_msg_id = event.original_update.msg_id
        src_msg_id = message_queue.get(int_msg_id)
        del message_queue[int_msg_id]

        # Получение информации об авторе callback - ответственном за алерт
        responsible_id = await userbot.get_entity(event.original_update.user_id)
        responsible_info = f"{responsible_id.first_name} {responsible_id.last_name} (@{responsible_id.username})"

        if not src_msg_id:
            logger.error(f"Original message ID not found in queue for callback: {int_msg_id}")
            return

        msg_template, coc_response_list = RESPONSES[event.data]

        if isinstance(coc_response_list, list):
            coc_response = random.choice(coc_response_list)
        else:
            coc_response = coc_response_list

        original = await event.client.get_messages(
            event.original_update.peer,
            ids=int_msg_id
        )

        logger.info(f"Processing callback: {event.data.decode()} for message {src_msg_id}")
        if event.data == b"other":
            await event.edit(
                text=msg_template.format(text=original.text, userinfo=responsible_info),
                parse_mode='md',
                buttons=None
            )
            inc_alerts_handled_metric(callback=event.data.decode("utf-8"), responsible=responsible_id.username)
            return

        await asyncio.gather(
            event.edit(
                text=msg_template.format(text=original.text, userinfo=responsible_info),
                parse_mode='md',
                buttons=None
            ),
            userbot.send_message(
                entity=CONFIG['SOURCE_CHAT_ID'],
                message=coc_response,
                reply_to=src_msg_id
            )
        )
        logger.info(f"Successfully processed callback for message {src_msg_id}")
        inc_alerts_handled_metric(callback=event.data.decode("utf-8"), responsible=responsible_id.username)
    except Exception as e:
        inc_errors_total_metric(handler="callback")
        logger.error(f"Error handling callback: {e}", exc_info=True)

async def handle_new_message(event: events.NewMessage.Event, bot: TelegramClient) -> None:
    """Обработка новых сообщений из чата"""
    try:
        msg = event.message

        # Проверяем, что сообщение является алертом: отправлено не игнорируемым пользователем и содержит триггеры
        if event.from_id.user_id == CONFIG['IGNORE_MSG_FROM_ID']:
            print("Ignoring message from user ignored via environment variable")
            return
        if not any(trigger in msg.text.lower() for trigger in CONFIG['TRIGGERS']):
            return

        # На этом этапе, сообщение считается валидным алертом
        inc_alerts_total_metric();

        # Обработка chat_id из event, чтобы ссылка на исходный чат была валидной
        if str(event.chat_id).__contains__("-100"):
            decorated_chat_id = str(event.chat_id).replace("-100", "")
        else:
            decorated_chat_id = str(event.chat_id).replace("-", "")

        src_msg_link = f"https://t.me/c/{decorated_chat_id}/{event.id}"
        logger.info(f"Processing triggered message: {src_msg_link} ({msg.id})")
        response = f"{msg.text}\n\nСсылка: {src_msg_link}"

        internal_response = await bot.send_message(
            entity=CONFIG['TARGET_CHAT_ID'],
            message=response,
            buttons=BUTTONS
        )

        message_queue[internal_response.id] = event.message.id
        logger.info(f"Forwarded message {msg.id} to target chat.")
    except Exception as e:
        inc_errors_total_metric(handler="message")
        logger.error(f"Error handling new message: {e}", exc_info=True)

async def main() -> None:
    """Основная функция запуска приложения"""
    APP_START_TIMESTAMP = datetime.now(CONFIG['TZ'])
    try:
        init_metrics_server(port=CONFIG['METRICS_SERVER_PORT'])
        set_app_start_timestamp(APP_START_TIMESTAMP)
        logger.info(f"Successfully started metrics server on :{CONFIG['METRICS_SERVER_PORT']}!")
    except Exception as e:
        logger.error(f"Caught error while starting metrics server: {e}", exc_info=True)

    try:
        logger.info("Starting bot application")
        bot, userbot = await initialize_clients()

        source_chat_info = await userbot.get_entity(CONFIG['SOURCE_CHAT_ID'])
        target_chat_info = await userbot.get_entity(CONFIG['TARGET_CHAT_ID'])
        logger.debug(f"------ CHATS INFORMATION ------")
        logger.debug(f"Source chat is {source_chat_info.title} (id={source_chat_info.id}). Considered class is {type(source_chat_info)}.")
        logger.debug(f"Target chat is {target_chat_info.title} (id={target_chat_info.id}). Considered class is {type(source_chat_info)}.")

        # Регистрация обработчиков событий
        userbot.add_event_handler(
            lambda e: handle_new_message(e, bot),
            events.NewMessage(chats=CONFIG['SOURCE_CHAT_ID'])
        )
        bot.add_event_handler(
            lambda e: handle_callback(e, userbot),
            events.CallbackQuery()
        )
        bot.add_event_handler(
            lambda e: e.reply(message=send_statistics(tz = CONFIG['TZ'], app_start_ts=APP_START_TIMESTAMP)),
            events.NewMessage(pattern='/stats')
        )
        logger.info("|------ APPLICATION LOGS ------|")
        logger.info("Event handlers registered")

        # Запуск ботов
        logger.info("Bots considered as ready")
        await asyncio.gather(
            bot.run_until_disconnected(),
            userbot.run_until_disconnected()
        )
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}", exc_info=True)
    finally:
        logger.info("Bot application stopped")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user input")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)