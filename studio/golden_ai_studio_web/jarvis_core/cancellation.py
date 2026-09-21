import threading

class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def request_cancel(self):
        self._event.set()

    def clear_cancel(self):
        self._event.clear()

    def is_cancelled(self):
        return self._event.is_set()
