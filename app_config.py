import logging
import os
from enum import Enum
from typing import Dict, Union

from dotenv import load_dotenv

load_dotenv()
CustomDictType = Dict[str, Union[str, str, str]]


class SideStatuses(Enum):
    """
    Перечисление сторон сделки на бирже Binance.

    Attributes:
        BUY (str): Сторона покупки.
        SELL (str): Сторона продажи.
    """
    BUY = "BUY"
    SELL = "SELL"


class Config:
    """Класс для загрузки и хранения конфигурационных параметров приложения из переменных окружения."""

    def __init__(self):
        self.API_KEY = os.getenv("API_KEY")
        self.secret_key = os.getenv("secret_key")
        self.base_url = os.getenv("base_url")
        self.url_ws = os.getenv("url_ws")
        self.sales_ratio = float(os.getenv("sales_ratio"))
        self.RECV_WINDOW = int(os.getenv("RECV_WINDOW"))
        self.price_currency = 0
        self.duration = int(os.getenv("duration"))
        self.quantity_currency = os.getenv("quantity_currency")
        self.order_type = os.getenv("order_type")
        self.waiting_next_purchase = int(os.getenv("waiting_next_purchase"))


class Logger:
    """Класс для настройки логгирования приложения."""

    logger = None

    def __init__(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler = logging.FileHandler('./app.log', mode='a')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
