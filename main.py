import asyncio
import aiohttp
import logo
import json
import csv
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
import time
import random
import string
import logging
from fake_useragent import UserAgent
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich import box

# Настройка логирования с Rich
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("ethereum_client")


class EthereumClient:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def generate_nonce(self):
        """Генерирует nonce похожий на пример ntyw5Hpl4gdiPFP0b"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(17))
    
    def create_message(self, address, nonce=None):
        """Создает сообщение для подписи"""
        if not nonce:
            nonce = self.generate_nonce()
            
        issued_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        expiration_time = datetime.fromtimestamp(
            datetime.now().timestamp() + 7*24*3600, timezone.utc
        ).isoformat().replace('+00:00', 'Z')
        
        message = f"""knowledgedrop.saharaai.com wants you to sign in with your Ethereum account:
{address}

Sign in with Ethereum to the app.

URI: https://knowledgedrop.saharaai.com
Version: 1
Chain ID: 1
Nonce: {nonce}
Issued At: {issued_at}
Expiration Time: {expiration_time}"""
        
        return message
    
    def sign_message(self, private_key, message):
        """Подписывает сообщение приватным ключом"""
        try:
            # Создаем аккаунт из приватного ключа
            account = Account.from_key(private_key)
            
            # Кодируем сообщение для подписи
            message_hash = encode_defunct(text=message)
            
            # Подписываем
            signed_message = account.sign_message(message_hash)
            
            return {
                'address': account.address,
                'signature': '0x' + signed_message.signature.hex(),
                'message': message
            }
        except Exception as e:
            print(f"Ошибка при подписи сообщения: {e}")
            return None
    
    async def sign_in(self, address, signature, message, user_agent, proxy=None):
        """Выполняет первый запрос - sign_in"""
        headers = {
            'accept': '*/*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://knowledgedrop.saharaai.com',
            'user-agent': f'{user_agent}'
        }
        
        data = {
            "address": address,
            "signature": signature,
            "message": message,
            "public_key": ""
        }
        
        try:
            async with self.session.post(
                'https://earndrop.prd.galaxy.eco/sign_in',
                headers=headers,
                json=data,
                proxy=proxy,
                timeout=30
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('token')
                else:
                    print(f"Ошибка sign_in: {response.status}")
                    return None
        except Exception as e:
            print(f"Ошибка при sign_in запросе: {e}")
            return None
    
    async def get_info(self, token,user_agent, proxy=None):
        """Выполняет второй запрос - получение информации"""
        headers = {
            'accept': '*/*',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': token,
            'origin': 'https://knowledgedrop.saharaai.com',
            'user-agent': f'{user_agent}'
        }
        
        try:
            async with self.session.get(
                'https://earndrop.prd.galaxy.eco/sahara/info',
                headers=headers,
                proxy=proxy,
                timeout=30
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"Ошибка get_info: {response.status}")
                    return None
        except Exception as e:
            print(f"Ошибка при get_info запросе: {e}")
            return None
    
    async def process_wallet(self, private_key, proxy=None):
        """Обрабатывает один кошелек"""
        try:
            # Создаем аккаунт
            account = Account.from_key(private_key)
            address = account.address
            
            print(f"Обработка кошелька: {address}")
            
            # Создаем и подписываем сообщение
            message = self.create_message(address)
            signed_data = self.sign_message(private_key, message)
            
            if not signed_data:
                return {"address": address, "status": "error", "error": "Ошибка подписи"}
            
            # Выполняем sign_in
            user_agent =  UserAgent(platforms='desktop')
            user_agent = user_agent.random
            token = await self.sign_in(
                signed_data['address'], 
                signed_data['signature'], 
                signed_data['message'],
                user_agent,
                proxy
            )
            
            if not token:
                return {"address": address, "status": "error", "error": "Ошибка sign_in"}
            
            # Получаем информацию
            info = await self.get_info(token,user_agent, proxy)
            
            if not info:
                return {"address": address, "status": "error", "error": "Ошибка get_info"}
            
            # Парсим результат
            data = info.get('data', {})
            total_amount = float(data.get('total_amount', '0')) / 10**18  # Wei to ETH
            
            return {
                "address": address,
                "status": "success",
                "total_amount": total_amount,
                "claimed_amount": float(data.get('claimed_amount', '0')) / 10**18,
                "eligible_amount": float(data.get('eligible_amount', '0')) / 10**18,
                "stages_count": len(data.get('stages', []))
            }
            
        except Exception as e:
            return {"address": "unknown", "status": "error", "error": str(e)}

def save_results_to_csv(results, filename="results.csv"):
    """Сохраняет результаты в CSV файл"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['wallet_address', 'status', 'total_amount', 'claimed_amount', 'eligible_amount', 'stages_count', 'timestamp']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            
            for result in results:
                if isinstance(result, dict):
                    if int(result.get('total_amount', 0)) > 0:
                        writer.writerow({
                            'wallet_address': result.get('address', 'unknown'),
                            'status': result.get('status', 'error'),
                            'total_amount': result.get('total_amount', 0),
                            'claimed_amount': result.get('claimed_amount', 0),
                            'eligible_amount': result.get('eligible_amount', 0),
                            'stages_count': result.get('stages_count', 0),
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                else:
                    writer.writerow({
                        'wallet_address': 'unknown',
                        'status': 'critical_error',
                        'total_amount': 0,
                        'claimed_amount': 0,
                        'eligible_amount': 0,
                        'stages_count': 0,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        print(f"📄 Результаты сохранены в файл: {filename}")
        return True
    except Exception as e:
        print(f"❌ Ошибка при сохранении в CSV: {e}")
        return False

def print_results_table(results):
    """Выводит красивую таблицу результатов используя Rich"""
    
    # Создаем таблицу результатов
    table = Table(box=box.ROUNDED, title="📊 Результаты обработки кошельков")
    table.add_column("№", style="dim", width=3)
    table.add_column("Адрес", style="cyan", width=42)
    table.add_column("Статус", width=12)
    table.add_column("Общая сумма SAHARA", style="green", justify="right", width=15)
    table.add_column("Доступно SAHARA", style="yellow", justify="right", width=15)
    table.add_column("Заклеймлено SAHARA", style="red", justify="right", width=15)
    table.add_column("Этапы", justify="center", width=6)
    
    total_wallets = len(results)
    successful = 0
    total_amount = 0
    
    # Заполняем таблицу данными
    for i, result in enumerate(results, 1):
        if isinstance(result, dict):
            address = result['address']
            short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
            
            if result['status'] == 'success':
                successful += 1
                amount = result['total_amount']
                total_amount += amount
                
                table.add_row(
                    str(i),
                    short_address,
                    "[green]✅ Успех[/green]",
                    f"{amount:.6f}",
                    f"{result['eligible_amount']:.6f}",
                    f"{result['claimed_amount']:.6f}",
                    str(result['stages_count'])
                )
            else:
                error_msg = result.get('error', 'Неизвестная ошибка')
                short_error = error_msg[:15] + "..." if len(error_msg) > 15 else error_msg
                table.add_row(
                    str(i),
                    short_address,
                    "[red]❌ Ошибка[/red]",
                    "-",
                    "-",
                    "-",
                    f"[red]{short_error}[/red]"
                )
        else:
            error_str = str(result)[:15] + "..." if len(str(result)) > 15 else str(result)
            table.add_row(
                str(i),
                "unknown",
                "[bright_red]💥 Критическая[/bright_red]",
                "-",
                "-", 
                "-",
                f"[bright_red]{error_str}[/bright_red]"
            )
    
    # Выводим таблицу
    console.print(table)
    
    # Общая статистика в панели
    success_rate = (successful/total_wallets*100) if total_wallets > 0 else 0
    
    stats_text = f"""📊 Всего кошельков:           {total_wallets}
✅ Успешно обработано:        {successful}
❌ Ошибок:                    {total_wallets - successful}
💰 Общая сумма SAHARA:        {total_amount:.6f}
📊 Процент успеха:            {success_rate:.1f}%"""
    
    console.print(Panel(stats_text, title="📈 Общая статистика", style="bold green"))

def load_private_keys(filename="private.txt"):
    """Загружает приватные ключи из файла"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            keys = [line.strip() for line in f if line.strip()]
        print(f"📁 Загружено {len(keys)} приватных ключей из {filename}")
        return keys
    except FileNotFoundError:
        print(f"❌ Файл {filename} не найден")
        return []
    except Exception as e:
        print(f"❌ Ошибка при чтении файла {filename}: {e}")
        return []

def load_proxies(filename="proxy.txt"):
    """Загружает прокси из файла"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            print(f"🌐 Загружено {len(proxies)} прокси из {filename}")
        return proxies
    except FileNotFoundError:
        print(f"📁 Файл {filename} не найден, прокси не используются")
        return []
    except Exception as e:
        print(f"❌ Ошибка при чтении файла {filename}: {e}")
        return []

async def main():
    """Главная функция"""
    # Загружаем данные из файлов
    private_keys = load_private_keys("private.txt")
    proxies = load_proxies("proxy.txt")
    
    if not private_keys:
        print("Не найдены приватные ключи в файле private.txt")
        print("Создайте файл private.txt и добавьте приватные ключи, каждый с новой строки")
        return
    
    print(f"Загружено {len(private_keys)} приватных ключей")
    if proxies:
        print(f"Загружено {len(proxies)} прокси")
    else:
        print("Прокси не используются")
    
    results = []
    
    async with EthereumClient() as client:
        tasks = []
        
        for i, private_key in enumerate(private_keys):
            proxy = proxies[i % len(proxies)] if proxies else None
            task = client.process_wallet(private_key, proxy)
            tasks.append(task)
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    
    print_results_table(results)
    save_results_to_csv(results)

if __name__ == "__main__":
    # Установите необходимые библиотеки:
    
    asyncio.run(main())
