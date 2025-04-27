CREATE USER autolab_user WITH PASSWORD 'ваш_пароль';

-- Предоставить права на подключение к базе данных
GRANT CONNECT ON DATABASE autolab_db TO autolab_user;

-- Выдать все привилегии на текущие и будущие объекты в схеме public
GRANT ALL PRIVILEGES ON SCHEMA public TO autolab_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO autolab_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO autolab_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO autolab_user;

-- Настроить права по умолчанию для будущих объектов
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT ALL PRIVILEGES ON TABLES TO autolab_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT ALL PRIVILEGES ON SEQUENCES TO autolab_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT ALL PRIVILEGES ON FUNCTIONS TO autolab_user;