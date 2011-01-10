import json
from PyQt4 import QtGui, QtCore, uic
import select
import socket
import sys

from socketclient import Client

class Tasker(QtGui.QMainWindow):
    """ This is my main application class.
        It creates all the windows and connects all the signals/slots """

    def __init__(self, host, port):
        QtGui.QMainWindow.__init__(self)

        # load the design from the .ui file
        self.ui = uic.loadUi("./resources/mainwindow.ui")
        self.ui.show()

        self.CLIENT = Client(host, port)

        # connect all the signals -> slots, event filters
        eventHandler = LineEditEventHandler(self)
        self.ui.lineEdit.installEventFilter(eventHandler)
        self.connect(self.ui.lineEdit, QtCore.SIGNAL("returnPressed()"), self.doAction)
        self.connect(self.ui.actionQuit, QtCore.SIGNAL('triggered()'), QtGui.qApp, QtCore.SLOT('quit()'))
        self.connect(self.ui.actionAbout, QtCore.SIGNAL("activated()"), self.about)

        self.thread = Worker()
        self.connect(self.thread, QtCore.SIGNAL("data"), self.update)
        self.thread.listen(self.CLIENT.socket)

        # set up instance vars
        self.connected = False
        self.client_id = ""

        # And any settings
        # No vertical headers for the table
        self.ui.tableWidget.verticalHeader().setVisible(False)
        # No sorting allowed, must always be sorted by increasing priority
        self.ui.tableWidget.setSortingEnabled(False)
        # Give focus to the line edit
        self.ui.lineEdit.setFocus()

    def update(self, data):
        obj = json.loads(data)

        # there will always be an update message
        # and always have the data to update
        try:
            if obj['type'] == 'error':
                self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: %s</span>" % obj['update'])
            else:
                self.ui.plainTextEdit.appendPlainText(obj['update'])
            self.updateTaskTable(obj['data'])
        except KeyError:
            pass

    def doAction(self):
        """ This method (slot) is responsible for sending the data to the server
            and updating the text box, and table with the response """

        text = str(self.ui.lineEdit.text())
        self.ui.lineEdit.clear()

        try:
            command = text.split()[0]
        except IndexError:
            return

        if not command == "connect" and not self.connected:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You must connect first</span>")
            return

        if command == 'connect':
            if self.connected:
                self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You're already connected!</span>")
                return
            self.connectToServer(text)
        elif command == 'addTask':
            self.addTask(text)
        elif command == "prioritize":
            self.setPriority(text)
        elif command == "accept":
            self.accept(text)
        elif command == 'complete':
            self.complete(text)
        else:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: Command <strong>'%s'</strong> not recognized</span>" % text)
            return

    def connectToServer(self, text):
        """ Responsible for connecting to the server, setting the client name """

        self.CLIENT.connect()
        self.CLIENT.send({'command': text, 'client_id': self.client_id})
        self.connected = True
        self.client_id = ' '.join(text.split()[1:])

    def addTask(self, text):
        """ Add a task to the table """

        if len(text.split()) < 2:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You must provide a task name</span>")
            return

        self.CLIENT.send({'command': text, 'client_id': self.client_id})

    def setPriority(self, text):
        """ Responsible for sending along the priority and task name """

        if len(text.split()) < 3:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You must provide a task name and priority</span>")
            return

        self.CLIENT.send({'command': text, 'client_id': self.client_id})

    def accept(self, text):
        """ Responsible for sending along the completer name """

        if len(text.split()) < 2:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You must provide a task name</span>")
            return

        self.CLIENT.send({'command': text, 'client_id': self.client_id})

    def complete(self, text):
        """ Responsible for sending the task name and completion percentage """

        if len(text.split()) < 3:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: You must provide a task "
                                             "name and completion percentage (0 - 100)</span>")
            return

        if int(text.split()[-1]) < 0 or int(text.split()[-1]) > 100:
            self.ui.plainTextEdit.appendHtml("<span style='background-color: red'>ERROR: Your completion value must be "
                                             "between 0 and 100 inclusive (0 - 100)</span>")
            return

        self.CLIENT.send({'command': text, 'client_id': self.client_id})


    def updateTaskTable(self, table):
        """ This method updates the task table with the data sent to it.

            The data is in the form of:

            [["Item 1", "Completer", "5", "12"], ["Item 2", "", "2", "0"]]"""
        self.ui.tableWidget.setRowCount(len(table))
        for y, row in enumerate(table):
            for x, cell in enumerate(row):
                item = QtGui.QTableWidgetItem(cell)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                item.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsEnabled)
                self.ui.tableWidget.setItem(y, x, item)

    def about(self):
        """ Show our about dialog """
        msgbox = QtGui.QMessageBox(self)
        msgbox.setIcon(QtGui.QMessageBox.Information)
        msgbox.setTextFormat(QtCore.Qt.RichText)
        msgbox.setText("<h1 align='center'>pyTasker</h1>"
                       "<p>Written by <a href='mailto:npresta@uoguelph.ca'>Nicholas Presta</a> (#0553282) on October 9th</p>"
                       "<p>This application was written in <a href='http://www.python.org/'>Python</a> "
                       "and <a href='http://qt.nokia.com'>Qt</a>, developed on "
                       "<a href='http://www.opensuse.org/en/'>OpenSuse Linux</a> in <a href='http://www.vim.org/'>Vim</a>.</p>"
                       "<p>Icons are from the <a href='http://www.oxygen-icons.org/'>Oxygen</a> set and are licensed under the "
                       "Attribution-ShareAlike 3.0 Unported license.</p>")
        msgbox.setWindowTitle("About pyTasker")
        msgbox.setWindowIcon(QtGui.QIcon("./resources/icon.png"))
        msgbox.exec_()

class Worker(QtCore.QThread):
    """ Our worker thread """

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.data = {}
        self.socket = None

    def __del__(self):
        self.wait()

    def listen(self, socket):
        self.socket = socket
        self.start()

    def run(self):
        """ This method waits for IO from select() and then gets the data
            from the socket and sends it back via a SIGNAL """

        while True:
            response, _, _ = select.select([self.socket], [],[])
            for t in response:
                if t == self.socket:
                    try:
                        self.data = self.socket.makefile().readline()
                    except socket.error:
                        # we aren't connected yet
                        continue
                    if self.data:
                        self.emit(QtCore.SIGNAL("data"), self.data.rstrip())

class LineEditEventHandler(QtCore.QObject):
    """ This event handler is responsible for the up/down history action in my line edit """

    def __init__(self, parent=None):
        super(LineEditEventHandler, self).__init__(parent)
        self.history_before = []
        self.history_after = []

    def eventFilter(self, obj, event):
        """ This event filter intercepts up/down keypresses and creates a "history" for us """

        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Up:
                if self.history_before:
                    self.history_after.insert(0, self.history_before.pop())
                    obj.setText(self.history_after[0])
                    return True
                obj.setText("")
                self.restartPos()
                return True
            elif event.key() == QtCore.Qt.Key_Down:
                if self.history_after:
                    self.history_before.append(self.history_after.pop(0))
                    if self.history_after:
                        obj.setText(self.history_after[0])
                        return True
                obj.setText("")
                self.restartPos()
                return True
            elif event.key() == QtCore.Qt.Key_Return:
                if self.history_after:
                    self.history_after.append(obj.text())
                else:
                    self.history_before.append(obj.text())
                self.restartPos()

        return QtCore.QObject.eventFilter(self, obj, event)

    def restartPos(self):
        self.history_before.extend(self.history_after)
        self.history_after = []

if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    if len(sys.argv) != 3:
        print >> sys.stderr, "You need to supply the hostname and port"
        sys.exit(-1)
    tasker = Tasker(sys.argv[1], sys.argv[2])
    sys.exit(app.exec_())
