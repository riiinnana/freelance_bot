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
