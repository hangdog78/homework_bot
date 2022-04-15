import logging
import os
import requests
import sys
import time

from exceptions import Non200ResponseException
from logging import StreamHandler
from requests import RequestException
from telegram import Bot, TelegramError
from telegram.ext import CommandHandler, Updater

from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('YANDEX_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')
TELEGRAM_RETRY_TIME = 600
TELEGRAM_DAY_IN_SEC = 86400

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='homework_bot.log',
    level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = StreamHandler(sys.stdout)
logger.addHandler(handler)


def send_message(bot, message):
    """Отправка сообщения в Telegram."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        logger.info(f'Отправлено сообщение: {message}')
    except TelegramError as error:
        logger.exception(f'Ошибка отправки сообщения: {error}')


def get_api_answer(timestamp):
    """Получение ответа от API Практикум'а."""
    try:
        params = {'from_date': timestamp}
        api_resp = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params=params)

        if api_resp.status_code != 200:
            raise Non200ResponseException(api_resp.status_code)

        return api_resp.json()

    except RequestException as error:
        logger.exception(f'API request error: {error}')


def check_response(response):
    """Проверка корректности ответа от API и возврат списка работ."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем')

    homeworks = response.get('homeworks')

    if not isinstance(homeworks, list):
        raise TypeError('Список работ не является списком')

    if len(homeworks) == 0:
        logger.debug('Нет новых статусов.')

    return homeworks


def parse_status(homework):
    """Проверка статуса отправленной работы."""
    if 'homework_name' not in homework:
        raise KeyError('Ключ homework_name не найден в ответе')

    homework_name = homework.get('homework_name')

    if 'status' not in homework:
        raise KeyError('Ключ status не найден в ответе')

    homework_status = homework.get('status')

    if homework_status not in HOMEWORK_STATUSES:
        raise KeyError(f'Получен неизвестный статус {homework_status}')

    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка наличия токенов."""
    return not any(token is None for token in [PRACTICUM_TOKEN,
                                               TELEGRAM_TOKEN,
                                               TELEGRAM_CHAT_ID])


def check_wrks(update, context):
    """Ручная проверка статуса работ за сутки по команде check."""
    logger.info('/check command recieved.')
    try:
        chat = update.effective_chat
        context.bot.send_message(chat.id, 'Проверяем новые статусы за сутки.')
        response = get_api_answer(int(time.time()) - TELEGRAM_DAY_IN_SEC)
        home_wrks = check_response(response)
        if len(home_wrks) == 0:
            context.bot.send_message(chat.id, 'Обновленных статусов нет')
        else:
            for wrk in home_wrks:
                wrk_status = parse_status(wrk)
                context.bot.send_message(chat.id, wrk_status)

    except Exception as error:
        message = f'Service failed: {error}'
        logger.exception(message)


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Tokens were not found. Service stopped.')
        sys.exit()

    logger.info('Tokens are loaded.')

    try:
        updater = Updater(token=TELEGRAM_TOKEN)
        updater.dispatcher.add_handler(CommandHandler('check', check_wrks))
        updater.start_polling()
        bot = Bot(token=TELEGRAM_TOKEN)
    except Exception as error:
        logger.exception(f'Network connection failed: {error}')

    else:
        current_timestamp = int(time.time())
        sent_errors = []
        logger.info('Starting service.')
        while True:
            try:
                response = get_api_answer(current_timestamp)
                home_wrks = check_response(response)
                for wrk in home_wrks:
                    wrk_status = parse_status(wrk)
                    send_message(bot, wrk_status)
                    current_timestamp = response.get('current_date')

            except Exception as error:
                message = f'Service failed: {error}'
                logger.exception(message)
                if error not in sent_errors:
                    sent_errors.append(error)
                    send_message(bot, message)

            finally:
                time.sleep(TELEGRAM_RETRY_TIME)


if __name__ == '__main__':
    main()
