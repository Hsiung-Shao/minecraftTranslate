class TranslatorError(Exception):
    pass


class ConnectionError(TranslatorError):
    pass


class ModelError(TranslatorError):
    pass


class ExtractionError(TranslatorError):
    pass


class TranslationError(TranslatorError):
    pass


class FormatValidationError(TranslationError):
    pass


class CacheError(TranslatorError):
    pass


class PackagingError(TranslatorError):
    pass
