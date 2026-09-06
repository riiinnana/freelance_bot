import unittest
from dataclasses import dataclass

from digests import split_all, split_post, split_text


# Настоящая подборка из ленты, укороченная до трёх пунктов.
DIGEST = """✍️ (#Удаленка) Требуются очешуительные творческие специалисты:

1. #Дизайнер_соцсетей
Создание визуального контента для соцсетей: картинки, рилс и карусели по ТЗ и брендбуку компании. На долгосрочное сотрудничество
📝 @muzykalarisa

2. #Графдизайнер
Учебный центр ищет дизайнера на постоянку. Бюджет 40000 ₽. Присылайте портфолио
📝 @kamola_phoenix

3. #Дизайнер_упаковки
Нужно разработать дизайн одной упаковки. Брендбук и остальные материалы уже есть
📝 @visugar

❤️ Коллеги, плз, поставьте ваш царский лайк 🫶🏻 Вам все равно, а нам приятно"""


PLAIN = """Продуктовый дизайнер (Стажёр)
Авито

Что делать:
— Работать над реальными потребностями пользователей.
— Участвовать в полном продуктовом цикле.

Требования:
— Готовность учиться."""


@dataclass(frozen=True)
class Post:
    source_id: str
    source: str
    title: str
    description: str
    url: str
    published_at: str | None = None


def make_post(description, source_id="channel/1"):
    return Post(
        source_id=source_id,
        source="@channel",
        title=description.splitlines()[0],
        description=description,
        url="https://t.me/channel/1",
    )


class SplitTextTests(unittest.TestCase):
    def test_every_item_becomes_its_own_vacancy(self):
        self.assertEqual(len(split_text(DIGEST)), 3)

    def test_the_greeting_before_the_first_item_is_dropped(self):
        self.assertNotIn("очешуительные", "\n".join(split_text(DIGEST)))

    def test_the_channel_signature_is_dropped(self):
        self.assertNotIn("царский лайк", "\n".join(split_text(DIGEST)))

    def test_each_item_keeps_its_own_contact(self):
        first, second, third = split_text(DIGEST)

        self.assertIn("@muzykalarisa", first)
        self.assertNotIn("@kamola_phoenix", first)
        self.assertIn("@kamola_phoenix", second)
        self.assertIn("@visugar", third)

    def test_each_item_keeps_the_role(self):
        first, second, third = split_text(DIGEST)

        self.assertIn("Дизайнер_соцсетей", first)
        self.assertIn("Графдизайнер", second)
        self.assertIn("Дизайнер_упаковки", third)

    def test_an_ordinary_post_is_not_split(self):
        self.assertEqual(split_text(PLAIN), [])

    def test_a_numbered_task_list_is_not_a_digest(self):
        # Нумерация без хештегов — обычный список задач внутри вакансии.
        text = (
            "Дизайнер презентаций\n"
            "Задачи:\n"
            "1. Собрать структуру слайдов\n"
            "2. Отрисовать макеты\n"
            "3. Подготовить исходники"
        )

        self.assertEqual(split_text(text), [])

    def test_a_single_hashtag_heading_is_not_a_digest(self):
        text = "#дизайнер_соцсетей\nИщут дизайнера для соцсетей.\n➡️ @someone"

        self.assertEqual(split_text(text), [])

    def test_scraps_are_not_counted_as_vacancies(self):
        text = "#Монтажер\nНайден!\n\n#Дизайнер\nНайден!"

        self.assertEqual(split_text(text), [])


class SplitPostTests(unittest.TestCase):
    def test_items_get_their_own_identifiers(self):
        items = split_post(make_post(DIGEST, source_id="TRemoters/9307"))

        self.assertEqual(
            [item.source_id for item in items],
            ["TRemoters/9307#1", "TRemoters/9307#2", "TRemoters/9307#3"],
        )

    def test_items_get_their_own_titles(self):
        items = split_post(make_post(DIGEST))

        self.assertEqual(
            [item.title for item in items],
            ["Дизайнер соцсетей", "Графдизайнер", "Дизайнер упаковки"],
        )

    def test_the_link_stays_the_same_for_every_item(self):
        # Отдельных ссылок на пункты в Telegram не существует.
        items = split_post(make_post(DIGEST))

        self.assertEqual({item.url for item in items}, {"https://t.me/channel/1"})

    def test_source_and_date_are_kept(self):
        post = make_post(DIGEST)
        items = split_post(post)

        self.assertEqual({item.source for item in items}, {post.source})
        self.assertEqual({item.published_at for item in items}, {None})

    def test_an_ordinary_post_is_returned_untouched(self):
        post = make_post(PLAIN)

        self.assertEqual(split_post(post), [post])

    def test_splitting_an_item_again_changes_nothing(self):
        # Повторный запуск разбора не должен плодить «пункты пунктов».
        item = split_post(make_post(DIGEST))[0]

        self.assertEqual(split_post(item), [item])

    def test_split_all_flattens_the_list(self):
        posts = [make_post(PLAIN, "channel/1"), make_post(DIGEST, "channel/2")]

        self.assertEqual(len(split_all(posts)), 4)


if __name__ == "__main__":
    unittest.main()
