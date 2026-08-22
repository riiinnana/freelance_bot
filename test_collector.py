import unittest

from collectors.telegram_channel import parse_channel_posts


PREVIEW_HTML = """
<div class="tgme_widget_message" data-post="designer_work/123">
  <div class="tgme_widget_message_text js-message_text">
    Нужен дизайнер презентаций.<br>Бюджет: 5 000 ₽.
  </div>
  <a class="tgme_widget_message_date"><time datetime="2026-08-22T10:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message" data-post="designer_work/124">
  <div class="tgme_widget_message_text js-message_text">Пост без вакансии.</div>
</div>
"""


class TelegramChannelParserTests(unittest.TestCase):
    def test_parses_posts_into_normalized_format(self):
        posts = parse_channel_posts(PREVIEW_HTML, "designer_work")

        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].source, "@designer_work")
        self.assertEqual(posts[0].source_id, "designer_work/123")
        self.assertEqual(posts[0].url, "https://t.me/designer_work/123")
        self.assertEqual(posts[0].title, "Нужен дизайнер презентаций.")
        self.assertIn("Бюджет: 5 000 ₽.", posts[0].description)
        self.assertEqual(posts[0].published_at, "2026-08-22T10:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
