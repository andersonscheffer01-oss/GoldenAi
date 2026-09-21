"""Workers Qt: nenhum request pesado no main thread.

O sinal mora num Dispatcher permanente (dono = MainWindow): o worker
nunca emite sinal de um QObject proprio, eliminando a condicao de
corrida em que a fonte do sinal morria antes do emit (chat sem resposta).
"""
from __future__ import annotations

import itertools

from PySide6.QtCore import QObject, QRunnable, Signal

_counter = itertools.count(1)


class Dispatcher(QObject):
    finished = Signal(str, object)  # token, result


class ApiWorker(QRunnable):
    def __init__(self, fn, dispatcher, token, *args, **kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.dispatcher = dispatcher
        self.token = token
        self.args = args
        self.kwargs = kwargs

    def run(self):  # executado no pool, nunca no main thread
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - erro vira payload p/ UI
            result = {"ok": False, "error": str(exc)[:300]}
        self.dispatcher.finished.emit(self.token, result)


def new_token():
    return f"w{next(_counter)}"
