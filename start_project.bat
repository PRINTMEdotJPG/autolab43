@echo off
REM ======================================================
REM Автоматическая настройка проекта AutoLab43 на Windows
REM ======================================================

REM 1. Остановить все предыдущие процессы Python/Daphne
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im daphne.exe >nul 2>&1

REM 2. Удаление старых миграций
echo Удаление старых миграций...
for /d /r . %%d in (migrations) do (
    if exist "%%d" (
        del /q "%%d\*.py"
        echo Удалены миграции в %%d
    )
)
echo. > your_app/migrations/__init__.py

REM 3. Пересоздание базы данных
echo Пересоздание базы данных...
psql -U postgres -c "DROP DATABASE IF EXISTS autolab_db;" || (
    echo Ошибка при удалении БД!
    pause
    exit /b 1
)
psql -U postgres -c "CREATE DATABASE autolab_db;" || (
    echo Ошибка при создании БД!
    pause
    exit /b 1
)

REM 4. Установка зависимостей
echo Установка зависимостей...
pip install -r requirements.txt || (
    echo Ошибка при установке зависимостей!
    pause
    exit /b 1
)

REM 5. Применение миграций
echo Применение миграций...
python manage.py makemigrations || (
    echo Ошибка при создании миграций!
    pause
    exit /b 1
)

python manage.py migrate || (
    echo Ошибка при применении миграций!
    pause
    exit /b 1
)

REM 6. Создание суперпользователя (admin@admin.ru / admin)
echo Создание суперпользователя...
echo from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@admin.ru', 'admin') if not User.objects.filter(username='admin').exists() else None | python manage.py shell || (
    echo Ошибка при создании суперпользователя!
    pause
    exit /b 1
)

REM 7. Сбор статических файлов (если нужно)
python manage.py collectstatic --noinput

REM 8. Запуск сервера через Daphne
echo Запуск сервера через Daphne...
start "" /B daphne -b 0.0.0.0 -p 8000 autolab.asgi:application

echo ======================================================
echo Сервер запущен!
echo Адрес: http://localhost:8000
echo Суперпользователь: admin@admin.ru / admin
echo ======================================================
pause