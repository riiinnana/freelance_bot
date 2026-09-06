"""Настройки источников вакансий."""

# Публичные Telegram-каналы для MVP.
TELEGRAM_CHANNELS = [
    {"username": "designwork_vacansii", "name": "ВАКАНСИИ ДЛЯ ДИЗАЙНЕРА | РАБОТА"},
    {"username": "TRemoters", "name": "REMOTER @ вакансии на удаленке"},
    {"username": "zakaz_design", "name": "ЗАКАЗЫ НА ДИЗАЙН | ДИЗАЙНЕРЫ | ВАКАНСИИ"},
    {"username": "rueventjob", "name": "Удаленка - вся творческая работа"},
    {"username": "FrWork3", "name": "Фриланс, удаленная работа, вакансии"},
    {
        "username": "designer_work",
        "name": "Design WORK",
    },
    {"username": "designer_vacancies", "name": "Вакансии для дизайнеров"},
    {"username": "design_vacancy", "name": "Вакансии для дизайнеров"},
]

# Сколько последних публикаций получать из каждого канала за один запрос.
COLLECTOR_POST_LIMIT = 20

# Как часто бот сам обходит каналы. Сбор идёт один раз для всех
# пользователей, поэтому число тестеров на нагрузку не влияет.
COLLECTION_INTERVAL_MINUTES = 15

# Пауза перед первым сбором после запуска: даёт боту подняться прежде,
# чем он полезет в сеть.
FIRST_COLLECTION_DELAY_SECONDS = 5
