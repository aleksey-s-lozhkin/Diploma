from django_elasticsearch_dsl import Document, Index, fields
from elasticsearch_dsl import Boolean, DenseVector
from elasticsearch_dsl import Document as EsDocument
from elasticsearch_dsl import Index as EsIndex
from elasticsearch_dsl import Integer, Keyword, Text, analyzer, token_filter

from .models import Document as DocumentModel
from .services.embedding_service import DEFAULT_DIMS as EMBED_DIMS

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


# --- Индекс кусков ---------------------------------------------------------
#
# Куски не являются моделью Django, поэтому индекс описан обычным
# elasticsearch_dsl: реестру django-elasticsearch-dsl нужна модель, а кусок
# живёт только в Elasticsearch и в любой момент пересобирается из текста
# документа (documents/services/chunk_service.py).

#: Тот же анализатор, что у документов: поиск по кускам должен находить русские
#: словоформы так же, как поиск по целым документам.
MULTILINGUAL_ANALYSIS = {
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
}

chunks_index = EsIndex("chunks")
chunks_index.settings(
    number_of_shards=1,
    number_of_replicas=0,
    analysis=MULTILINGUAL_ANALYSIS,
)


@chunks_index.document
class ChunkIndex(EsDocument):
    """Один кусок документа: то, что отдаётся потребителю в ответе поиска."""

    document_id = Integer()
    chunk_index = Integer()
    chunk_total = Integer()
    #: Отпечаток содержимого документа: по нему видно, что отрывок устарел.
    document_version = Keyword()
    title = Text(analyzer="multilingual_analyzer")
    text = Text(analyzer="multilingual_analyzer")
    rubrics = Text(analyzer="standard")
    is_public = Boolean()
    user_id = Integer()
    #: Вектор куска для векторного поиска (docs/RAG-EXPERIMENT.md).
    #:
    #: `index=True` — обязательное условие knn-поиска в Elasticsearch 8: без
    #: него вектор можно только хранить, искать по нему нельзя. Косинус, а не
    #: скалярное произведение: куски разной длины, и близость не должна
    #: зависеть от того, что один кусок длиннее другого.
    #:
    #: Размерность берётся из сервиса эмбеддингов, а не выписана числом:
    #: там же она сверяется с ответом модели, и разойтись они не могут.
    #:
    #: В уже созданный индекс поле добавляет команда `embed_chunks` через
    #: `PUT _mapping` — пересоздавать индекс ради нового поля не нужно.
    dense_vector = DenseVector(dims=EMBED_DIMS, index=True, similarity="cosine")
