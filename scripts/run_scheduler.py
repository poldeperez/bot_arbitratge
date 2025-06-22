import schedule
import asyncio
import time
import logging

# Importamos la función main desde tu script principal
from opportunity_finder import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("log_scheduler.txt", encoding="utf-8")
    ]
)

def job():
    print("Ejecutando job()...")
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Error al ejecutar main(): {e}")

# Programamos la tarea cada 10 minutos
schedule.every(10).seconds.do(job)

logging.info("Scheduler iniciado. Ejecutando cada 10 minutos...")

# Bucle infinito para mantenerlo corriendo
while True:
    schedule.run_pending()
    time.sleep(1)