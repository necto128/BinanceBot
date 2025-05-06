# Python 3.13.1
import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal

import httpx
import websockets

from app_config import Config, Logger
from app_config import CustomDictType, SideStatuses


class Handler:
    """
    Основной класс приложения, управляющий логикой выбора валюты, запуском задач и торговыми операциями.

    Attributes:
        data_currency (dict): Словарь доступных криптовалютных пар.
        config (Config): Объект конфигурации.
        api_binance (ApiBinance): Клиент API Binance.
    """
    data_currency = {
        "1": {"name": "btcusdt@ticker", "symbol": "BTCUSDT", "asset": "BTC"},
        "2": {"name": "ethusdt@ticker", "symbol": "ETHUSDT", "asset": "ETH"},
        "3": {"name": "solusdt@ticker", "symbol": "SOLUSDT", "asset": "SOL"},
    }

    def __init__(self):
        """
        Инициализирует объект Handler: загружает конфигурацию, настраивает логгирование и создаёт клиент API Binance.
        """
        self.config = Config()
        Logger()
        self.api_binance = ApiBinance(config=self.config)

    async def task_checking_prices(self, currency: CustomDictType) -> None:
        """
        Логика отслеживания цены после покупки. Продажа происходит при:
        - Падении цены ниже purchase_price * (1 - sales_ratio)
        - Росте цены выше purchase_price * (1 + sales_ratio)
        - Истечении времени duration

        Args:
            currency (CustomDictType): Выбранная криптовалютная пара.
        """
        start_timestamp = datetime.datetime.now()
        end_timestamp = start_timestamp + datetime.timedelta(seconds=self.config.duration)
        if purchase_price := await self.api_binance.create_order(currency=currency, side=SideStatuses.BUY.value):
            down_price = purchase_price - (purchase_price * Decimal(self.config.sales_ratio))
            up_price = purchase_price + (purchase_price * Decimal(self.config.sales_ratio))
            while True:
                if ((self.config.price_currency["price"] <= down_price or self.config.price_currency["price"] >= up_price)
                        or (datetime.datetime.now() >= end_timestamp)):
                    await self.api_binance.create_order(currency=currency, side=SideStatuses.SELL.value)
                    break
                await asyncio.sleep(0.2)

    async def main(self, currency: CustomDictType) -> None:
        """
        Основной цикл работы бота: ожидание, покупка, продажа и пауза перед следующим циклом.

        Args:
            currency (CustomDictType): Выбранная криптовалютная пара.
        """
        await asyncio.sleep(5)
        logging.info("Main start")
        while True:
            logging.info("Start bye")
            await asyncio.create_task(self.task_checking_prices(currency))
            logging.info(f"Wait {self.config.waiting_next_purchase}c")
            await asyncio.sleep(self.config.waiting_next_purchase)

    async def start(self) -> None:
        """
       Запуск приложения. Предлагает пользователю выбрать валюту,
       затем запускает задачи получения данных и торговли.
       """
        index = input("Сhoose a currency:\n1) btcusdt\n2) ethusdt\n3) solusdt\n")
        currency = self.data_currency.get(index, "btcusdt@ticker")
        task_load = asyncio.create_task(DataLoader(
            subscribe_currency=currency["name"],
            config=self.config
        ).load_data())
        task_main = asyncio.create_task(self.main(currency))
        await task_load
        await task_main


class DataLoader:
    """
    Отвечает за подключение к WebSocket Binance и обновление текущих цен в реальном времени.

    Attributes:
        subscribe_currency (str): Название потока подписки (например, 'btcusdt@ticker').
        config (Config): Объект конфигурации.
    """

    def __init__(self, subscribe_currency: str, config: Config) -> None:
        """Инициализирует DataLoader."""
        self.subscribe_currency = subscribe_currency
        self.config = config

    async def load_data(self) -> None:
        """
       Подключается к WebSocket Binance и получает обновления цены в реальном времени.
       Сохраняет актуальную цену в `config.price_currency`.
       """
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": [
                self.subscribe_currency
            ],
        }
        logging.info("Websockets connect ...")
        while True:
            async with websockets.connect(self.config.url_ws) as websocket:
                await websocket.send(json.dumps(subscribe_message))
                logging.info("Websockets start")
                while True:
                    try:
                        message = await websocket.recv()
                        message_data = json.loads(message)
                        if 'c' in message_data:
                            self.config.price_currency = {
                                "asset": message_data['s'],
                                "price": Decimal(message_data['c'])
                            }
                    except websockets.ConnectionClosed:
                        logging.info("wait message ...")
                        await asyncio.sleep(2)


class ApiBinance:
    """Клиент для взаимодействия с REST API Binance."""

    def __init__(self, config: Config) -> None:
        """Инициализирует клиент API Binance."""
        self.config = config
        self.headers = {
            "X-MBX-APIKEY": config.API_KEY
        }

    def get_signature(self, params_string: str) -> hmac:
        """
        Генерирует HMAC-SHA256 сигнатуру для запроса к API.

        Args:
            params_string (str): Строка параметров запроса.

        Returns:
            hmac.HMAC: Подпись запроса.
        """
        return hmac.new(
            self.config.secret_key.encode('utf-8'),
            params_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def get_balance(self, currency: CustomDictType) -> list:
        """
        Получает баланс пользователя по указанной валюте.

        Args:
            currency (CustomDictType): Валюта, для которой нужно получить баланс.

        Returns:
            list: Информация о балансе выбранной монеты.
        """
        timestamp = int(time.time() * 1000)
        params_string = f"timestamp={timestamp}&recvWindow={self.config.RECV_WINDOW}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=f"{self.config.base_url}/api/v3/account",
                headers=self.headers,
                params={
                    "timestamp": timestamp,
                    "recvWindow": self.config.RECV_WINDOW,
                    "signature": self.get_signature(params_string)
                }
            )
            if response.status_code == 200:
                balance = [i for i in response.json()['balances'] if i["asset"] == currency["asset"]]
                return balance

    async def create_order(
            self,
            currency: CustomDictType,
            side: str,
            price: Decimal = None
    ) -> Decimal:
        """
        Создаёт ордер на покупку или продажу.

        Args:
            currency (CustomDictType): Валюта, на которую создаётся ордер.
            side (str): Сторона сделки ('BUY' или 'SELL').
            price (Decimal, optional): Цена ордера (только для лимитных ордеров).

        Returns:
            Decimal: Цена исполнения ордера.
        """
        timestamp = int(time.time() * 1000)
        quantity = self.config.quantity_currency
        order_type = self.config.order_type
        params_string = (
            f"symbol={currency["symbol"]}&side={side}&type={self.config.order_type}"
            f"&quantity={quantity}&timestamp={timestamp}&recvWindow={self.config.RECV_WINDOW}"
        )
        if price:
            params_string += f"&price={price}"
        signature = self.get_signature(params_string)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{self.config.base_url}/api/v3/order",
                headers=self.headers,
                data={
                    "symbol": currency["symbol"],
                    "side": side,
                    "type": order_type,
                    "quantity": quantity,
                    "timestamp": timestamp,
                    "recvWindow": self.config.RECV_WINDOW,
                    "signature": signature
                }
            )
            if response.status_code == 200:
                order_data = response.json()
                logging.info(f"Order create: "
                             f"symbol: {order_data['symbol']}, "
                             f"orderId: {order_data['orderId']}, "
                             f"origQty: {order_data['origQty']}, "
                             f"side: {order_data['side']}, "
                             f"price: {order_data['fills'][0]['price']}, "
                             f"status: {order_data['status']}, "
                             f"Account balance: {await self.get_balance(currency)}"
                             )
                return Decimal(order_data['fills'][0]['price'])
            logging.info(f"Error for create order:{response.status_code},{response.text}", )
            return Decimal(0)


if __name__ == '__main__':
    asyncio.run(Handler().start())
