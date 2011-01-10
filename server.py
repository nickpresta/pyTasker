import json
from operator import itemgetter
import select
import shelve
import socket
import sys

class Request(object):
    """ This class is a collection of methods responsible for dealing with
        requests made to the TCP server.

        The way the class should be used is as such:

        # s is string. s = "Connect " for example

        r = Request()
        r._call(s)

        This will look up the internals of the class and call the right
        method with the appropriate args """

    def __init__(self):
        # We use the shelve module to keep persistent data between requests for new clients
        s = shelve.open("tasks.db", writeback=True)
        try:
            if not s.has_key("data"):
                s['data'] = []
        finally:
            s.close()

    def _call(self, command):
        """ This builds a dynamic list of callable methods and calls them """

        # This is kinda magic
        # It searches this class for all method which don't start with _ and creates a list of callables
        callables = [c for c in dir(self) if not c.startswith("_")]

        # separate the command and get the args/client id
        obj = json.loads(command)
        _ = obj['command'].split()
        command, args = _[0], " ".join(_[1:])

        # try to call the command the return the result, otherwise, not implemented/ignore
        try:
            # search the list for the string name of the method
            # call it by looking for self.METHOD with the args
            return getattr(self, callables[callables.index(command)])(args, obj['client_id'])
        except ValueError:
            # not available to be called
            return {'update': "%s not implemented yet..." % command, 'error': True}

    def connect(self, args, client_id):
        """ This method is responsible for connecting a client """

        # parse the args
        client_id = args
        update = "Client %s connected" % client_id
        s = shelve.open("tasks.db", flag='r')
        try:
            data = s['data']
        finally:
            s.close()

        return {'update': update, 'client_id': client_id, 'type': 'connect', 'data': data}

    def addTask(self, args, client_id):
        """ This is responsible for adding a new task """

        # parse the args
        task_name = args

        # This will load the data and append any new data and write it to the file
        s = shelve.open("tasks.db", writeback=True)
        sublist = next((l for l in s['data'] if l[0] == task_name), None)
        if sublist:
            try:
                data = s['data']
            finally:
                s.close()
            return {'client_id': client_id, 'update': "There already exists a task with the name '%s'." % task_name,
                    'type': 'error', 'data': data}

        try:
            s['data'].append([task_name, '', "5", "0"])
            # sort the list by priority
            s['data'].sort(cmp=lambda x,y: cmp(int(x), int(y)), key=itemgetter(2))
            data = s['data']
        finally:
            s.close()

        return {'client_id': client_id,
            'update': "%s added a task: %s" % (client_id, task_name),
            'data': data, 'type': 'addTask'}

    def prioritize(self, args, client_id):
        """ This sets the priority for a task given a specific name """

        # parse the args
        parts = args.split()
        # task name is anything in the middle
        task_name = " ".join(parts[0:-1])
        # priority is last
        priority = parts[-1]

        s = shelve.open("tasks.db", writeback=True)
        try:
            data = s['data']
            # find the sublist with the task name
            sublist = next((l for l in data if l[0] == task_name), None)
            if not sublist:
                return {'client_id': client_id, 'update': 'Cannot find task named "%s"' % task_name,
                    'type': 'error', 'data': data}
            # change the priorty
            old = sublist[2]
            sublist[2] = priority
            # resort the whole list
            data.sort(cmp=lambda x,y: cmp(int(x), int(y)), key=itemgetter(2))
            # update
            s['data'] = data
        finally:
            s.close()

        return {'client_id': client_id,
            'update': "%s changed the priority of '%s': %s -> %s" % (client_id, task_name, old, priority),
            'data': data, 'type': 'prioritize'}

    def accept(self, args, client_id):
        """ This accepts a given task (adds to the "completer" field) """

        # parse the args
        task_name = args

        s = shelve.open("tasks.db", writeback=True)
        try:
            data = s['data']
            # find the sublist with the task name
            sublist = next((l for l in data if l[0] == task_name), None)
            if not sublist:
                return {'client_id': client_id, 'update': 'Cannot find task named "%s"' % task_name,
                    'type': 'error', 'data': data}
            # change the completer
            old = sublist[1] or "<NO ONE>"
            sublist[1] = client_id
            # no resort needed
            s['data'] = data
        finally:
            s.close()

        return {'client_id': client_id,
                'update': "%s accepted the task '%s': %s -> %s" % (client_id, task_name, old, client_id),
                'data': data, 'type': 'accept'}

    def complete(self, args, client_id):
        """ This sets the completion column. It does not do any bounds checking (left to the caller) """

        # parse the args
        parts = args.split()
        # task name is anything in the middle
        task_name = " ".join(parts[0:-1])
        # completion is last
        completion = parts[-1]

        s = shelve.open("tasks.db", writeback=True)
        try:
            data = s['data']
            # find the sublist with the task name
            sublist = next((l for l in data if l[0] == task_name), None)
            if not sublist:
                return {'client_id': client_id, 'update': 'Cannot find task named "%s"' % task_name,
                    'type': 'error', 'data': data}
            # change the priorty
            old = sublist[3]
            sublist[3] = completion
            # update
            s['data'] = data
        finally:
            s.close()

        return {'client_id': client_id,
            'update': "%s changed the completion of '%s': %s -> %s" % (client_id, task_name, old, completion),
            'data': data, 'type': 'complete'}

class SelectServer(object):
    """ This is a simple socket servert that uses select() to monitor the socket connections """

    request = Request()

    def __init__(self, host, port):
        self.host = host
        self.port = port

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # reuse addr
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # bind
        self.server.bind((self.host, self.port))
        # don't block and listen with space for 5 in the queue
        self.server.setblocking(0)
        self.server.listen(5)

        self.read = [self.server]
        self.clients = []

    def run(self):
        while True:
            readable, writable, error = select.select(self.read, self.clients, self.read)

            for sock in readable:
                # A new client has connected
                if sock == self.server:
                    connection, client_address = sock.accept()
                    connection.setblocking(0)
                    self.read.append(connection)
                else:
                    # a client has sent some data, read it and broadcast
                    data = sock.makefile().readline().rstrip()
                    if data:
                        # if we aren't already tracking this client, add them here
                        if sock not in self.clients:
                            self.clients.append(sock)
                        data = SelectServer.request._call(data)
                        # If the call generated an error, return only to the sender
                        if data['type'] == 'error':
                            self.broadcast_to_clients(json.dumps(data) + "\n", to=sock)
                        else:
                            self.broadcast_to_clients(json.dumps(data) + "\n")
                    else:
                        # there was no data sent from the client, remove them and close the socket
                        if sock in self.clients:
                            self.clients.remove(sock)
                        self.read.remove(sock)
                        sock.close()

            for sock in writable:
                # we write to our clients when a new connection comes in and does something
                # We don't wait to broadcast at a later time, we just fire a message off right away
                pass

            for sock in error:
                # If a socket appears closed, remove it from out list and close it on our end
                self.read.remove(sock)
                if sock in self.clients:
                    self.clients.remove(sock)
                sock.close()

    def broadcast_to_clients(self, msg, omit=None, to=None):
        """ This will broadcast a message to all clients, except those that match omit.
            Optionally, send a message to only 1 client using 'to' """

        if not omit:
            omit = ()

        # if we're only sending to one, do it here
        if to:
            next(s for s in self.clients if s == to).send(msg)
            return

        # otherwise, loop through all clients, omitting those that are specified
        for c in self.clients:
            if c in omit:
                continue
            c.send(msg)

    def shutdown(self):
        """ Close all socket connections """

        for s in self.clients + self.read:
            s.close()

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print >> sys.stderr, "You need to supply the hostname and port"
        sys.exit(-1)

    print "Starting server..."
    server = SelectServer(sys.argv[1], int(sys.argv[2]))
    try:
        server.run()
    except KeyboardInterrupt:
        print "Shutting down server..."
        server.shutdown()
        sys.exit(0)
