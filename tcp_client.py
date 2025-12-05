#!/usr/bin/env python
import socket
from time import sleep
from threading import Thread

host, port = 'killerwhale', 7000

clientsocket = []

"""
def keepalive(clientsocket):
    print("Keepalive thread started")
    try:
        while True:
            clientsocket[0].send(b'\n')
            sleep(2)
    except (ConnectionResetError, BrokenPipeError):
        print("Connection lost (keepalive)")
"""

class MacroExecuted(Exception): pass

class InteractiveMacro:
    def __init__(self, string, arglist):
        self.string = string
        self.arglist = arglist

    def format(self):
        args = []
        for arg  in self.arglist:
            args.append(input(f"Value required for {arg}: "))
        return bytes(self.string.format(*args),'ascii')

"G29 L-50 R130 F-140 B-50"

macros = {
    'init': b"""M104 S120
        M140 S60
        G34
        M420 S1""",
    '+0.25mm babystepping': b'M290 Z.25',
    '-0.25mm babystepping': b'M290 Z-.25',
    #'resume_on_crash': InteractiveMacro("""resume_on_crash;Z={};L={};B={}\n""", ('Z','L','B'))
    'resume_on_crash': InteractiveMacro("""resume_on_crash;{}\n""", ('L,P',))
}

if __name__ == '__main__':
    while True:
        try:
            clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            clientsocket.connect((host, port))
        except ConnectionRefusedError:
            print(".",end='')
            sleep(1)
        else:
            print(f"\nconnected to {host}:{port}")
            try:
                #thread = Thread(target=keepalive, args=(clientsocket,))
                #thread.start()
                print("main loop start")
                while True:
                    cmd=input("> ")
                    try:
                        if len(cmd):
                            for k in macros.keys():
                                if k.startswith(cmd):
                                    print(f"executing macro: {k}")
                                    if type(macros[k]) is InteractiveMacro:
                                        cmd = macros[k].format()
                                        print(cmd)
                                        sleep(1)
                                    else:
                                        for line in macros[k].split(b'\n'):
                                            print('>', line.decode('ascii').strip())
                                            clientsocket.send(line+b'\n')
                                    raise MacroExecuted(k)
                    except MacroExecuted:
                        pass
                    else:
                        clientsocket.send(cmd.encode('ascii')+b'\n')
                        sleep(1)
            except (ConnectionResetError, BrokenPipeError):
                print("Connection lost")
                sleep(1)
