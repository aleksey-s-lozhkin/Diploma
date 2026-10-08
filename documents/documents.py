from django_elasticsearch_dsl import Document, Index, fields
from elasticsearch_dsl import analyzer, token_filter

from .models import Document as DocumentModel

# Создаем стоп-фильтр для русского языка
russian_stop = token_filter("russian_stop", type="stop", stopwords="_russian_")

# Создаем стеммер для русского языка
russian_stemmer = token_filter("russian_stemmer", type="stemmer", language="russian")

# Создаём английский стоп-фильтр
english_stop = token_filter("english_stop", type="stop", stopwords="_english_")

# Создаём английский стеммер
english_stemmer = token_filter("english_stemmer", type="stemmer", language="english")

# Русский анализатор для морфологии
russian_analyzer = analyzer(
    "russian_analyzer", tokenizer="standard", filter=["lowercase", russian_stop, russian_stemmer]
)

# Настройка индекса Elasticsearch
index = Index("documents")
index.settings(
    number_of_shards=1,
    # Реплика на однонодовом кластере держит здоровье индекса в yellow всегда:
    # разместить её негде. Вернуть 1 вместе со вторым узлом Elasticsearch.
    number_of_replicas=0,
    analysis={
        "analyzer": {
            "multilingual_analyzer": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "russian_stop", "english_stop", "russian_stemmer", "english_stemmer"],
            }
        },
        "filter": {
            "russian_stop": {"type": "stop", "stopwords": "_russian_"},
            "english_stop": {"type": "stop", "stopwords": "_english_"},
            "russian_stemmer": {"type": "stemmer", "language": "russian"},
            "english_stemmer": {"type": "stemmer", "language": "english"},
        },
    },
)


@index.document
class DocumentIndex(Document):
    """Elasticsearch индекс для модели Document"""

    rubrics = fields.TextField(analyzer="standard")
    text = fields.TextField(analyzer="multilingual_analyzer")
    created_date = fields.DateField()
    user_id = fields.IntegerField()
    is_public = fields.BooleanField()

    class Django:
        model = DocumentModel
        fields = ["id"]

        # Автоматические сигналы django-elasticsearch-dsl пишут в Elasticsearch
        # без обработки ошибок: недоступный ES выбрасывал исключение прямо из
        # Document.save(), и создание документа отвечало 500, хотя строка в
        # PostgreSQL уже была вставлена. Индексация вынесена в
        # documents/signals.py: там ошибки логируются и наружу не уходят,
        # потому что поиск — ускоритель, а не источник правды.
        ignore_signals = True

        # related_models намеренно не указан. Строка вместо класса модели
        # (было ["user"]) никогда не совпадает с instance.__class__ и молча
        # ничего не делает, а настоящий класс модели без
        # get_instances_from_related() ронял бы user.save() с
        # NotImplementedError при каждом входе и подтверждении почты.
        auto_refresh = True

    def get_queryset(self):
        """Подгружаем пользователя при запросе"""
        return super().get_queryset().select_related("user")

    def prepare_user_id(self, instance):
        """Извлекаем ID пользователя из документа"""
        return instance.user_id

    def prepare_rubrics(self, instance):
        """Извлекаем рубрики (возвращаем пустой список, если None)"""
        return instance.rubrics if instance.rubrics else []

    def prepare_text(self, instance):
        """Извлекаем текст документа"""
        return instance.text

    def prepare_created_date(self, instance):
        """Извлекаем дату создания"""
        return instance.created_date
