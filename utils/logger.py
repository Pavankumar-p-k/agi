import logging

class SystemLogger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    def info(self, msg, *a, **kw): self._logger.info(msg, *a, **kw)
    def warning(self, msg, *a, **kw): self._logger.warning(msg, *a, **kw)
    def error(self, msg, *a, **kw): self._logger.error(msg, *a, **kw)
    def debug(self, msg, *a, **kw): self._logger.debug(msg, *a, **kw)
    def critical(self, msg, *a, **kw): self._logger.critical(msg, *a, **kw)
