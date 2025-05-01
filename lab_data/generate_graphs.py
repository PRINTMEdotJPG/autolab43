import matplotlib
matplotlib.use('Agg')  # Используем бэкенд Agg для работы без GUI
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import logging

# Настройка логгера для модуля
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('graph_generation.log')
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def generate_signal_time_graph(data_points: list) -> str:
    """
    Генерирует график зависимости сигнала микрофона от времени.

    Args:
        data_points: Список объектов EquipmentData с данными эксперимента

    Returns:
        str: График в формате base64-encoded PNG

    Raises:
        ValueError: Если входные данные некорректны
    """
    logger.debug("Generating signal vs time graph")
    try:
        if not data_points or len(data_points) < 2:
            raise ValueError("Недостаточно данных для построения графика")

        fig, ax = plt.subplots(figsize=(10, 4))
        times = [d.time_ms for d in data_points]
        signals = [d.microphone_signal for d in data_points]

        ax.plot(times, signals, color='blue', linewidth=1)
        ax.set_title('Зависимость сигнала микрофона от времени')
        ax.set_xlabel('Время, мс')
        ax.set_ylabel('Сигнал микрофона, у.е.')
        ax.grid(True)

        logger.info("Signal vs time graph generated successfully")
        return _fig_to_base64(fig)

    except Exception as e:
        logger.error(f"Error generating signal graph: {str(e)}", exc_info=True)
        raise


def generate_interference_graph(data_points: list) -> str:
    """
    Генерирует график интерференционной картины (сигнал от положения трубки).

    Args:
        data_points: Список объектов EquipmentData с данными эксперимента

    Returns:
        str: График в формате base64-encoded PNG

    Raises:
        ValueError: Если входные данные некорректны
    """
    logger.debug("Generating interference pattern graph")
    try:
        if not data_points or len(data_points) < 2:
            raise ValueError("Недостаточно данных для построения графика")

        fig, ax = plt.subplots(figsize=(10, 4))
        positions = [d.tube_position for d in data_points]
        signals = [d.microphone_signal for d in data_points]

        ax.scatter(positions, signals, s=2, color='red')
        ax.set_title('Интерференционная картина')
        ax.set_xlabel('Положение трубки, мм')
        ax.set_ylabel('Сигнал микрофона, у.е.')
        ax.grid(True)

        logger.info("Interference graph generated successfully")
        return _fig_to_base64(fig)

    except Exception as e:
        logger.error(f"Error generating interference graph: {str(e)}", exc_info=True)
        raise


def generate_gamma_frequency_graph(details: dict) -> str:
    """
    Генерирует график зависимости γ от частоты звука.

    Args:
        details: Словарь с детальными результатами эксперимента

    Returns:
        str: График в формате base64-encoded PNG

    Raises:
        ValueError: Если входные данные некорректны или нет успешных экспериментов
    """
    logger.debug("Generating gamma vs frequency graph")
    try:
        if not details or 'details' not in details:
            raise ValueError("Отсутствуют данные для построения графика")

        successful_experiments = [
            d for d in details['details'] if d.get('status') == 'success'
        ]
        if not successful_experiments:
            raise ValueError("Нет успешных экспериментов для построения графика")

        fig, ax = plt.subplots(figsize=(10, 4))
        frequencies = [d['frequency'] for d in successful_experiments]
        gammas = [d['gamma'] for d in successful_experiments]

        ax.plot(frequencies, gammas, 'o-', color='green')
        ax.axhline(1.4, color='gray', linestyle='--', label='Эталон (γ=1.4)')
        ax.set_title('Зависимость γ от частоты')
        ax.set_xlabel('Частота, Гц')
        ax.set_ylabel('Значение γ')
        ax.legend()
        ax.grid(True)

        logger.info(
            f"Gamma vs frequency graph generated for {len(frequencies)} points"
        )
        return _fig_to_base64(fig)

    except Exception as e:
        logger.error(f"Error generating gamma graph: {str(e)}", exc_info=True)
        raise


def _fig_to_base64(fig: plt.Figure) -> str:
    """
    Внутренняя функция для конвертации matplotlib Figure в base64 строку.

    Args:
        fig: Объект Figure matplotlib

    Returns:
        str: Изображение в формате base64

    Note:
        Закрывает переданную фигуру после конвертации для освобождения памяти
    """
    try:
        buffer = BytesIO()
        fig.savefig(
            buffer,
            format='png',
            bbox_inches='tight',
            dpi=100,
            transparent=True
        )
        plt.close(fig)  # Важно закрыть фигуру для освобождения памяти
        logger.debug("Figure converted to base64 successfully")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error converting figure to base64: {str(e)}", exc_info=True)
        raise