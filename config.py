import os


class Config:
    # Настройки для медиафайлов
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'autolab43/media')
    MANUAL_NAME = "lab43_manual.pdf"
    MANUAL_PDF_PATH = os.path.join(MEDIA_ROOT, 'manuals', MANUAL_NAME)


config = Config()
# Надо создать .env файл и в нем установить значения переменных виртуального окружения (БД)
