import socket
import json

class Client(object):
    """ This class is a client to send/receive to our server """

    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = int(port)

    def connect(self):
        """ Attempts to connect to the host, if not already connected """
        self.socket.connect((self.host, self.port))

    def send(self, msg):
        """ Send expects a JSON request to be sent to the server """

        self.socket.send(json.dumps(msg) + "\n")

    def receive(self):
        """ Receive all data from the server and return a json object """

        try:
            return json.loads(''.join(self.socket.makefile().readline()))
        except ValueError:
            return None

    def close(self):
        """ Close the socket """

        self.socket.close()
