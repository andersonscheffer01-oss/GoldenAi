"""QLocalServer based single-instance activation for the Desktop shell."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activate_requested = Signal()

    def __init__(self, name="GoldenJarvisWebDesktop", parent=None):
        super().__init__(parent)
        self.name = name
        self.server = None

    def acquire(self):
        socket = QLocalSocket(self)
        socket.connectToServer(self.name)
        if socket.waitForConnected(350):
            socket.write(b"activate")
            socket.flush()
            socket.waitForBytesWritten(350)
            socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer(self)
        if not self.server.listen(self.name):
            return False
        self.server.newConnection.connect(self._accept)
        return True

    def _accept(self):
        while self.server and self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            if connection:
                connection.waitForReadyRead(100)
                connection.readAll()
                connection.disconnectFromServer()
                connection.deleteLater()
            self.activate_requested.emit()

    def close(self):
        if self.server:
            self.server.close()
            QLocalServer.removeServer(self.name)
            self.server = None

