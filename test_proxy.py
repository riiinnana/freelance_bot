import asyncio
import aiohttp


PROXY = "http://127.0.0.1:12334"
URL = "https://api.telegram.org"


async def main():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL, proxy=PROXY, timeout=15) as response:
                print("Статус:", response.status)
                print("Telegram API доступен через прокси")
                print(await response.text())

    except Exception as e:
        print("Ошибка:", repr(e))


if __name__ == "__main__":
    asyncio.run(main())
    