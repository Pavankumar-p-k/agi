import logging
logger = logging.getLogger(__name__)

class JarvisOSManager:
    def __init__(self):
        self.ready = True

def build_jarvis_os():
    logger.info("JarvisOS bootstrap (stub)")
    return JarvisOSManager()
