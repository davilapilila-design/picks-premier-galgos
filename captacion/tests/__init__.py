import logging

# Los avisos y errores que el bot escribe en el log son esperados en los
# tests (se provocan a propósito); no ensucian la salida.
logging.disable(logging.CRITICAL)
