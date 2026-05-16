from django_elasticsearch_dsl import Document, Index, fields
from elasticsearch_dsl import analyzer, token_filter

from .models import Document as DocumentModel

# Создаем стоп-фильтр для русского языка
russian_stop = token_filter("russian_stop", type="stop", stopwords="_russian_")

# Создаем стеммер для русского языка
russian_stemmer = token_filter("russian_stemmer", type="stemmer", language="russian")

# Русский анализатор для морфологии
russian_analyzer = analyzer(
    "russian_analyzer", tokenizer="standard", filter=["lowercase", russian_stop, russian_stemmer]
)

# Настройка индекса
index = Index("documents")
index.settings(
    number_of_shards=1,
    number_of_replicas=0,
    analysis={
        "analyzer": {
            "russian_analyzer": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "russian_stop", "russian_stemmer"],
            }
        },
        "filter": {
            "russian_stop": {"type": "stop", "stopwords": "_russian_"},
            "russian_stemmer": {"type": "stemmer", "language": "russian"},
        },
    },
)


@index.document
class DocumentIndex(Document):
    """Elasticsearch индекс для модели Document"""

    rubrics = fields.TextField(analyzer="standard")
    text = fields.TextField(analyzer=russian_analyzer)
    created_date = fields.DateField()
    user_id = fields.IntegerField()

    class Django:
        model = DocumentModel
        fields = ["id"]
        related_models = ["user"]
        ignore_signals = False
        auto_refresh = True

    def get_queryset(self):
        return super().get_queryset().select_related("user")

    def prepare_user_id(self, instance):
        return instance.user_id

    def prepare_rubrics(self, instance):
        return instance.rubrics if instance.rubrics else []

    def prepare_text(self, instance):
        return instance.text

    def prepare_created_date(self, instance):
        return instance.created_date
