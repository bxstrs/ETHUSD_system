'''src/utils/logger.py'''
import time
import inspect
import os

LOG_LEVEL = "INFO"  # DEBUG, INFO, ERROR
levels = ["DEBUG", "INFO", "WARNING", "CRITICAL", "ERROR"]

def log(msg, level="INFO", source=None):

    if levels.index(level) < levels.index(LOG_LEVEL):
        return

    if source is None:
        # Get caller frame (1 level up)
        frame = inspect.stack()[1]
        file_path = frame.filename
        file_name = os.path.basename(file_path)
        func_name = frame.function
        line_no = frame.lineno

        source = f"{file_name}:{func_name}:{line_no}"

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    print(f"[{timestamp}] [{level}] [{source}] {msg}", flush=True)