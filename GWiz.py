#!/usr/bin/env python
# vim: number
from __future__ import annotations  # NOTE: what does this actually do?
import os
import sys
import logging
import logging.config
logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=False)
logger = logging.getLogger('stderrLogger')

try:
    import serial
except ImportError:
    raise Exception("module 'pyserial' is required")

import urwid
import bytes_as_braille as bab
from collections import deque
from time import sleep
from proghelp import *

"""
TODOs:

# TODO allow inserting command at top of pile or somewhere in the middle

* implement replies to
- !! / Error: / fatal:
- rs / Resend
- busy:<reason>
in general: https://reprap.org/wiki/G-code#Replies_from_the_RepRap_machine_to_the_host_computer

* allow read commands from pipe (or command ie. python)
* color command in progress (the one on "top" of WIP pile)
* use ':' to prefix command mode, sort-of like vim
* python-formatted config?
* automatic machine detection based on report from firmware
* mouse control with XY, XZ, YZ plane selection and position reporting (mouse or from serial device)
* automatically extract and cache G-Code command usage from https://raw.githubusercontent.com/MarlinFirmware/MarlinDocumentation/master/_gcode/
* don't hang waiting for the printer to reply something when a lot of commands are in the pile!
* multiple gcode files on cmd line
* parallel G-Code with z-based interpolation, partial cancel
* display commands number (for history)
* history: don't consider comments and status messages as commands
* wip_ts, ack_ts
* don't redraw all internal widgets?
* also see inline TODOs

Weird:
- Marlin ommits 'C:' prefix to coordinates?
"""

loop, wai_pile, wip_pile, ack_pile, edit, machine_pos, messages, tbars, info_dic, machine_status, gcode_piles, watch_pipe, div, cmd_pile, all_wai, editmap = [None for _ in range(16)]
PRINT_PAUSED = True
MAX_COMMANDS_IN_WIP = 5
# max lines to show in piles
DISP_ACK_LEN = 30
DISP_WAI_LEN = 10

# exceptions and error messages:
class GotTempReport(Exception): pass
class FormatError(Exception): pass
watch_pipe_error = (urwid.Text(('error','OSError on watch_pipe ; display refresh will suffer')), ('pack',None))

import pendulum
#TIME_FMT = "%Y-%m-%d %H:%M:%S"
TIME_FMT = "%H:%M:%S.%s"
TIME_LEN = len(pendulum.now().strftime(TIME_FMT))+1

# the list of commands that the machine supports
valid_commands = {}

class WQueue:
    """
        Widgeted queue

        basically a list, and a viewport on that list

        override `widget` and `subwidget` if your UI differs from urwid
    """
    def __init__(self, name, content = [], **kwargs ):
        self.name = name
        self.content = deque(content)
        self.display_size = kwargs.pop('display_size', 10)
        self.paused = kwargs.pop('paused', True)
        self.style = kwargs.pop('style', 'qTitle')
        self.show_title = kwargs.pop('show_title', True)
        self.max_content_len = kwargs.pop('max_content_len', -1)
        self.color = kwargs.pop('color', 'wait')
        self.viewport_start = kwargs.pop('viewport_start', -1 )

    def __str__(self):
        return f"<WQueue: {self.name} ({len(self.content)} lines)>"

    def subwidget(self, text, *args, **kwargs):
        return urwid.Text( self.linecolor(text), *args, **kwargs)
    
    @property
    def widget(self, preload = []):
        if len(self.content) < self.display_size:
            if self.show_title:
                return urwid.Pile( [ urwid.Text( (self.style, self.name) ), *preload, *[ self.subwidget(tup) for tup in self.content ]] )
            else:
                return urwid.Pile( [*preload, *[ self.subwidget(tup) for tup in self.content ]] )
        else:
            if self.show_title:
                if self.viewport_start == -1:
                    return urwid.Pile( [ urwid.Text( (self.style, self.name) ), *preload, *[ self.subwidget(self.content[-self.display_size+i]) for i in range(self.display_size) ]] )
                else:
                    return urwid.Pile( [ urwid.Text( (self.style, self.name) ), *preload, *[ self.subwidget(self.content[self.viewport_start+i]) for i in range(self.display_size) ]] )
            else:
                if self.viewport_start == -1:
                    return urwid.Pile( [ *preload, [ self.subwidget(self.content[-self.display_size+i]) for i in range(self.display_size) ]] )
                else:
                    return urwid.Pile( [ *preload, [ self.subwidget(self.content[self.viewport_start+i]) for i in range(self.display_size) ]] )

    def append(self, item, pos = -1):
        if pos == -1:
            self.content.append(item)
        elif pos == 0:
            # NOTE only works if self.content was declared as collections.deque() !
            self.content.appendleft(item)
        else:
            self.content = [ *self.content[:pos+1],  item, *self.content[pos+1:] ]

    def pop(self, pos):
        # deque.rotate() is speedy
        self.content.rotate(-pos)
        #try:
        item = self.content.popleft()
        #except IndexError as e:
        #    logger.info(f"queue was empty! [0]")
        #    #raise
        #else:
        self.content.rotate(pos)
        return item

    def __len__(self):
        return len(self.content)

    @property
    def is_saturated(self):
        """ can we append more items to this queue (the content, NOT the displayed subset) """
        return False if len(self) < self.max_content_len else True

    def linecolor(self, line, color = None):
        if type(line) is urwid.Text:
            line = line.get_text()[0]

        if line.startswith(b';'):
            return ('comment',line)

        line = line.split(b';', 1)
        if len(line) == 2:
            return [(self.color if color is None else color,line[0]),('comment',b';'+line[1])]
        else:
            return (self.color if color is None else color,line[0])


class ACKPile(WQueue):
    def subwidget(self, *args, **kwargs):
        if len((tup := args[0])) == 2:
            if tup[0] is not None:
                try:
                    return urwid.Columns([
                            (TIME_LEN, urwid.Text( ('timestamp', tup[0][0].strftime(TIME_FMT)) )),
                            urwid.Text( tup[0][1] ),
                            urwid.Text( tup[1][1] ),
                            (TIME_LEN, urwid.Text( ('timestamp', tup[1][0].strftime(TIME_FMT)) )),
                        ])
                except IndexError:
                    logger.info(f"IndexError ; full ACK message {tup[0]} --- {tup[1]}")
                    raise
                except TypeError:
                    logger.info(f"IndexError ; full ACK message {tup[0]} --- {tup[1]}")
                    raise
            else:
                #logger.debug(f"no-ACK message {tup[0]} --- {tup[1]}")
                return urwid.Columns([
                        (TIME_LEN, urwid.Text( '' )),
                        #urwid.Text( self.linecolor( tup[1][1] )),
                        urwid.Text( tup[1][1] ),
                        (TIME_LEN, urwid.Text( ('timestamp', tup[1][0].strftime(TIME_FMT)) )),
                    ])
        else:
            #logger.info(f"short ACK message {tup[0][0]} --- {tup[0][1]}")
            return urwid.Columns([
                    (TIME_LEN, urwid.Text( ('timestamp', tup[0][0].strftime(TIME_FMT)) )),
                    urwid.Text( tup[0][1] ),
                ])

    def append(self, item, where = None):
        now = pendulum.now()
        if where:
            logger.debug(f"ACK: appending {(item[0], (now), item[1])} ({where})")
        self.content.append( (item[0], (now, item[1])) )
        # TODO add machines names?
        #case 'greeter':
        #    result.critical(f"{now}: Gwiz started")  
        try:
            if item[1][1].startswith(b'ok'):
                result.error(item[0][1].decode())
            elif item[0] is None:
                if item[1][1].startswith(b';'):
                    # this maybe a comment we sent? don't need to over-commment
                    result.warning(item[1][1].decode())
                elif item[1][0] in ('status_msg',):
                    # communication from printer ; can't be replayed as-is in gcode so we double-comment it
                    result.info(';; '+item[1][1].decode())
                else:
                    logger.info('??? '+str(item))
            else:
                logger.info('!!! '+str(item))
        except TypeError:
            if item[1][0] == 'error':
                logger.error(f"{item[1][1]}:{item[0][1].decode()}")
                result.debug(f"{item[1][1]}:{item[0][1].decode()}")
            else:
                logger.critical(f"TODO (FJ482HD7): >>>{item}<<<")
        except Exception as e:
            logger.critical(f"{e} (FK582H5H): {item}")


class WIPPile(WQueue):
    def subwidget(self, *args, **kwargs):
        return urwid.Columns([
                ( TIME_LEN, urwid.Text( ('timestamp', args[0][0].strftime(TIME_FMT)) )),
                urwid.Text( self.linecolor( args[0][1], kwargs.pop('color', self.color) )),
            ])

    #def widget(self):
    #    return super().widget()

    def append(self, item, where = None):
        if where:
            logger.debug(f"WIP: appending {(pendulum.now(), item)} ({where})")
        try:
            if self.content[0][1].startswith(b';'):
                ack_pile.append( (None,wip_pile.pop(0)) )
        except IndexError:
            pass
        self.content.append( (pendulum.now(), item) )



"""
    write to serial
"""
def pop_to_serial(s, pile):
    #logger.debug('pop_to_serial()', pile)
    try:
        wip_pile.append( cmd := pile.pop(0), 'serial' )
        #logger.debug('pop_to_serial()', cmd)
        if not PRINT_PAUSED:
            raise IndexError
        #messages.contents = [ (urwid.Text(('',f"{cmd} {PRINT_PAUSED = }")), ('pack',None)), *messages.contents ]
    except IndexError:
        pass
        #return
        #if not PRINT_PAUSED:
        #    try:
        #        messages.contents = [ (urwid.Text(('',f'added print command: {cmd}')), ('pack',None)), *messages.contents ]
        #    except UnboundLocalError:
        #        messages.contents = [ (urwid.Text(('',f'no command left to add!')), ('pack',None)), *messages.contents ]
        #        return

    # strip comments and invalid commands
    if not cmd.strip().startswith(b';') and not cmd.isspace() and len(cmd) > 0:
        s.write((cmd+b'\n'))
        logger.debug(f">>> {cmd}")


"""
    reads output from machine and takes action

    TODO add some formatting and timestamps
"""
def read_from_serial(s):
    do_update_ack = None
    cmd_errors = deque()

    # NOTE this depends on firmware and 
    # it makes GWiz wait for a 'start' from the printer
    MACHINE_READY=True
    # STOP Restart with flush so we get an ersatz of a 'start' (apparently it depends on serial port type :-s) ; this is 
    #wip_pile.append(b'STOP Restart')
    #wip_pile.append(b'M999 S0')
    #s.write(b'M999 S0\n')
    # trying the same with reboot.. FAIL
    #wip_pile.append(b'REBOOT')
    #wip_pile.append(b'M997')
    #s.write(b'M997\n')
    # NOTE the above commented code is a crap workaround to the issue that CDC serial re-enumerates on reset
    #   and also with disabled/0 NO_TIMEOUTS if connection is lost and the machine's buffer is empty by then.
    #   kept for reference.

    try:
        while True:
            reply = s.readline().rstrip(b'\n')
            logger.debug(f"<<< {reply}")
            try:
                if reply.startswith(b'ok'):
                    while True:
                        try:
                            if (last_wip_command_with_ts := wip_pile.pop(0))[1].startswith(b';'):
                                ack_pile.append( last_wip_command_with_ts, '0' )
                            else:
                                break
                        #except TypeError:
                        #    logger.info(f"read_from_serial(): queue was empty! [1] {reply}")
                        #    #raise
                        #    break
                        except IndexError:
                            logger.warning("read_from_serial(): received '{reply}' but queue was empty")
                            break
                            
                    try:
                        if last_wip_command_with_ts[1] == cmd_errors[0]:
                            ack_pile.append( (last_wip_command_with_ts, ('error','Unknown command') ), '1')
                            cmd_errors.popleft()
                        else:
                            raise IndexError
                    except IndexError:
                        # normal command here, nothing special
                        # TODO it would be nice to split and color trailing comments
                        #logger.info('whoops', last_wip_command_with_ts)
                        ack_pile.append( (last_wip_command_with_ts, ('ack_msg',reply)), '2' )
                        # TODO update position if last command is one of G0-G5 ?
                    #except TypeError:
                    #    logger.info("read_from_serial(): queue was empty! [2]")
                    #    #raise
                        

                    if reply.startswith(b'ok T:'):
                        reply = reply[2:]
                        raise GotTempReport
                    # else: TODO throttling and "skip" in cas of missed ACK message
                    # see also https://reprap.org/wiki/GCODE_buffer_multiline_proposal
                elif reply in [b'wait',b'echo:busy: processing']:
                    # ignore this shit, we don't need that as a "clock" XD
                    # see HOST_KEEPALIVE_FEATURE DEFAULT_KEEPALIVE_INTERVAL BUSY_WHILE_HEATING NO_TIMEOUTS
                    MACHINE_READY = True
                    pass
                elif reply.startswith(b'X:'):
                    machine_pos.set_text(reply.split(b' Count ',1)[0])
                elif reply.startswith(b' T:'):
                    raise GotTempReport
                elif reply.startswith(b'echo:'):
                    if reply.startswith(b'echo:Unknown command:'):
                        cmd_errors.append( reply.lstrip(b'echo:Unknown command:').split(b'"',2)[1] )
                        logger.debug(f"{cmd_errors[-1] = }")
                    else:
                        ack_pile.append( (None, ('echo', reply)), '3' )
                elif reply.startswith(b'//'):
                    #add_to_ack( (pendulum.now(), (reply.decode().rstrip('\n'), 'misc_status')) )
                    ack_pile.append( (None, ('misc_status', reply)), '4' )
                else:
                    # TODO works with Marlin 2.1.x, not 1.x, other firmwres untested (put in config?)
                    if reply == b'pages_ready':
                        MACHINE_READY = True
                        logger.info("machine ready")
                        messages.contents = [ (urwid.Text(('',b'Machine ready :-)')), ('pack',None)), *messages.contents ]
                    elif reply == b'start':
                        machine_status.set_text((b'status_OK',machine_status.get_text()[0]))

                    ack_pile.append( (None, ('status_msg', reply)), '5' )

            except GotTempReport:
                #messages.set_text(reply.decode().rstrip('\n'))
                temps = reply.split(b' ')[1:]
                for t in range(len(temps)//3):
                    try:
                        label, temp = temps[2*t].split(b':')
                        target = float(temps[2*t+1].lstrip(b'/'))
                        pwr = int(temps[2*len(temps)//3+t].split(b':')[1])
                        #messages.set_text(f"{label}: {temp}/{target}°C @{pwr}")
                        tbars[label][0].set_completion(pwr)
                        tbars[label][1].set_completion(target)
                        tbars[label][2].set_completion(float(temp))
                    except (ValueError, IndexError) as e:
                        logger.info(f"{E} (GJE72JDH): {bab.to_braille(reply)}")

            # downshift commands if required (send to printer)
            if MACHINE_READY:
                while len(wai_pile) and not wip_pile.is_saturated:
                    pop_to_serial(s, wai_pile )

                if not PRINT_PAUSED:
                    for gco_pile in gcode_piles.keys():
                        logger.debug(f"flushing pile {gco_pile}")
                        while len(gcode_piles[gco_pile]) and not wip_pile.is_saturated:
                            #logger.info(f"will pop {gcode_piles[gco_pile].content[0]}")
                            pop_to_serial(s, gcode_piles[gco_pile] )
                            #logger.info(f"flushing pile {gcode_piles[gco_pile]}")
                            #sleep(1)

            try:
                os.write( watch_pipe, b'nop\n' )
            except TypeError:
                pass
            except OSError:
                machine_status.set_text((b'status_UNK',machine_status.get_text()[0]))
                try:
                    if messages.contents[0] is not watch_pipe_error:
                        messages.contents = [ watch_pipe_error, *messages.contents ]
                except KeyError:
                    messages.contents = [ watch_pipe_error, *messages.contents ]
                finally:
                    serial_comm_still_ok(b'OSError\n')

    except serial.serialutil.SerialException:
        machine_status.set_text(('status_ERR',machine_status.get_text()[0]))
        messages.contents = [ (urwid.Text(('error',b'connection to machine was lost')), ('pack',None)), *messages.contents ]

def serial_comm_still_ok(data):
    global cmd_pile, all_wai
    # NOTE we could do something with 'wait' and 'echo:busy: processing'...
    try:
        data = [ d for d in data.rstrip(b'\n').split(b'\n') if d != b'nop' ]
    except Exception as e:
        raise Exception( e, data)
    if len(data):
        for d in data:
            if d == 'OSError':
                try:            os.close( watch_pipe )
                except OSError: pass
                finally:
                    messages.contents = [ (urwid.Text(('error','watch_pipe was lost ; display refresh issues ahead')), ('pack',None)), *messages.contents ]
                    return False
            else:
                messages.contents = [ (urwid.Text(('',f'watch_pipe: {data.decode()}')), ('pack',None)), *messages.contents ]
    else:
        # this must be forced / redefined, because the internal widgets change and we're not recycling widgets (TODO: FIX!)
        all_wai = urwid.Columns([wai_pile.widget, *[gcode_piles[filename].widget for filename in gcode_piles.keys()]])
        i = 0
        while True:
            try:
                cmd_pile.contents = [ (w,('pack',None)) for w in [ ack_pile.widget, wip_pile.widget, all_wai, editmap ]]
                break
            except RuntimeError as e:
                if i == 10:
                    logger.info(f"Warning (id:KCD4JD72G): {e} (message repeated 10 times)")
                else:
                    logger.debug(f"Warning (id:KCD4JD72G): {e}")
                    i = 0
                i += 1
                sleep(.1)


        return True


"""This is ACK pile', 'all instructions here have been processed"""
# add_to_ack
commands_ack = [
    ((pendulum.now(), (b'greeter', " Welcome to G-Code Wizard! ")),),
    ((pendulum.now(), b"You may cast your spells now."), (pendulum.now(), b'pooof!')),
    #('G28', 'ok'),
    #('G0 Z300', 'ok',),
]

"""
    this is WAIT pile, instructions that are scheduled to be sent to the machine
    it is possible to change order and/or insert commands and/or delete commands from this pile

    commands added here will be auto-sent to printer as soon as it is ready

    limitation: try not to exceed DISP_WAI_LEN or weird things may happen

    TODO put this in printer config
"""
commands_wai = [
    #b'M155 S1', # temperatures auto-report
]
if len(commands_wai) > DISP_WAI_LEN:
    raise NotImplementedError



palette = [
    ('banner', 'black,bold', 'light gray'),
    ('greeter', 'black,bold', 'light gray'),
    ('streak', 'black', 'dark blue'),
    ('acked', 'dark green', ''),
    ('ack_msg', 'black,bold', ''),
    ('status_msg','light green', ''),
    ('wip', 'light green', ''),
    ('wip0', 'white', 'dark blue'),    # topmost line of wip_pile (currently executing)
    ('wait', 'dark cyan', ''),
    ('acked', 'dark green', ''),
    ('echo', 'light magenta', ''),
    ('error', 'light red', 'black'),
    ('comment', 'white', ''),
    ('misc_status', 'dark magenta', ''),
    ('prompt','dark green', 'black'),
    ('input','',''),
    ('timestamp', 'black', ''),
    ('HL0', 'light green', ''),
    ('HL1', 'light cyan', ''),
    ('status_OK', 'black,bold', 'dark green'),
    ('status_UNK', 'black,bold', 'brown'),
    ('status_ERR', 'black,bold', 'dark red'),
    ('div', '', '', '', 'g7', '#d06'),
    # progress bars (text_color, bar_color)
    ('pb_pwr', 'black', 'light gray'),
    ('pb_tgt', 'light magenta', 'dark blue'),
    ('pb_temp', 'black,bold', 'dark red'),

    ('qTitle', 'light gray', 'black'),
]


title = urwid.Text(('banner',' '+PROGNAME+' '), align='center')
titlemap = urwid.AttrMap(title, 'streak')

# one of 'normal', 'search', 'history', 'command'
EDIT_MODE = 'normal'

def commands_by_index(i):
    raise NotImplementedError
    try:
        return wai_pile[-i].get_text()[0]
    except IndexError:
        #messages.contents = [ (urwid.Text(('','lookback mode searching wip pile')), ('pack',None)), *messages.contents ]
        try:
            return wip_pile[-(i-len(wai_pile))].get_text()[0]
        except IndexError:
            #messages.contents = [ (urwid.Text(('','lookback mode searching ack pile')), ('pack',None)), *messages.contents ]
            try:
                return ack_pile[-(i-len(wai_pile)-len(wip_pile))].contents[1][0].get_text()[0]
            except IndexError:
                #messages.contents = [ (urwid.Text(('','lookback mode returns nothing')), ('pack',None)), *messages.contents ]
                return ''
    

class UserInput(urwid.Padding):
    global wai_pile, loop

    def keypress(self, size, key):
        global EDIT_MODE, PRINT_PAUSED

        #if key == 'enter':
        #    raise Exception(f"{key = }, {size = }")

        def widget_to_append( text ):
            #raise Exception('widget_to_append', text)
            return urwid.Columns([
                    (6, urwid.Text(text[0])),
                    urwid.Text(text[1]),
                ])

        def append_to_pile( widget ):
            #raise Exception(widget)
            info_dic.contents.append( (widget,('pack', None)) )

        #if key.startswith('ctrl'):
        #    edit.edit_text = key
        # TODO also match on partial strings if there is no ambiguity or obvious precedence
        match key:
            case 'esc':
                EDIT_MODE = 'normal'
                edit.set_caption('>>> ')
                edit.edit_text = ''

            # NOTE both that follow should be a single clause.... too bad we can't just not add "break;" like in C
            case 'meta s':
                EDIT_MODE = 'search'
                edit.set_caption('??? ')
            case '?':
                EDIT_MODE = 'search'
                edit.set_caption('??? ')

            case ':':
                EDIT_MODE = 'command'
                edit.set_caption('### ')
                edit.edit_text = '' # TODO why this doesn't work?
            case '!':
                if edit.edit_text == '':
                    EDIT_MODE = 'history'
                    edit.set_caption('>>> ')
            case 'ctrl p':
                PRINT_PAUSED = not PRINT_PAUSED
                

        if key == 'enter' and edit.edit_text != '':
            match EDIT_MODE:
                case 'normal':
                    try:
                        edit.edit_text = commands_by_index( int(edit.edit_text) )
                        edit.edit_pos = len(edit.edit_text)
                        #messages.contents = [ (urwid.Text(('','entering lookback mode')), ('pack',None)), *messages.contents ]
                        # integer index of a previously typed command ; require confirmation with another 'enter'
                        return
                    except ValueError:
                        # normal command or comment
                        wai_pile.append(bytes(edit.edit_text,'utf-8'), 0)
                        edit.edit_text = ''
                        info_dic.contents = []
                case 'search':
                    edit.edit_text = ''
                    EDIT_MODE = 'normal'
                    pass
                case 'history':
                    raise NotImplementedError
                    wai_pile.append(bytes(edit.edit_text,'utf-8'))
                    edit.edit_text = ''
                case 'command':
                    match edit.edit_text:
                        case 'run':
                            PRINT_PAUSED = False
                        case 'pause':
                            PRINT_PAUSED = True
                        case 'force':
                            wip_pile.append(b'caca')
                            logger.debug("appended 'caca' to wip_pile")
                        case 'debug':
                            logger.debug(ack_pile)
                            logger.debug(wip_pile)
                            logger.debug(wai_pile)
                        case 'quit':
                            logger.info("quit on user request")
                            raise SystemExit
                        case _:
                            messages.contents = [ (urwid.Text(('error',f"uh? `{edit.edit_text}`")), ('pack',None)), *messages.contents ]
                    edit.edit_text = ''
        else:
            match EDIT_MODE:
                case 'normal':
                    if key == ' ':
                        try:
                            # TODO don't show this, show a more verbose info from online/cached .md 
                            info_dic.contents = [ (urwid.Text( valid_commands[edit.edit_text.split(' ')[0]] ), ('pack',None))]
                        except KeyError:
                            info_dic.contents = []
                case 'search':
                    info_dic.contents = []
                    #subcommands = []
                    for command in valid_commands:
                        search_and_highlight( (edit.edit_text+key).split(' '), f"{command}\t{valid_commands[command]}", widget_to_append, append_to_pile )
                        #if (cmd := search_and_highlight( edit.edit_text.split(' '), f"{command}\t{valid_commands[command]}", widget_to_append, append_to_pile )) 
                        #    subcommands.append( cmd )
                    if len(info_dic.contents) == 1:
                        #raise Exception(info_dic.contents[0][0].contents[0][0].get_text())
                        edit.edit_text = info_dic.contents[0][0].contents[0][0].get_text()[0]
                        edit.edit_pos = len(edit.edit_text)
                        EDIT_MODE = 'normal'
                        edit.set_caption('>>> ')
                        return
                        #return super().keypress(119, 'enter')
                case 'command':
                    info_dic.contents = [
                        (urwid.Text('Available commands:'),('pack',None)),
                        (urwid.Text('run (start flushing G-code piles)'),('pack',None)),
                        (urwid.Text('pause'),('pack',None)),
                        (urwid.Text('load <filename.gcode> TODO'),('pack',None)),
                        (urwid.Text('reload <filename.gcode> TODO'),('pack',None)),
                        (urwid.Text('offset X Y <filename.gcode> TODO'),('pack',None)),
                        (urwid.Text('save <filename.gcode> TODO'),('pack',None)),
                        (urwid.Text("flush (abort print & clear 'wait' pile) TODO"),('pack',None)),
                        (urwid.Text("force (push one more command into WIP queue... sometimes bad reporting! TODO)"),('pack',None)),
                        (urwid.Text('connect <port> TODO'),('pack',None)),
                        (urwid.Text('buffsize <int> TODO'),('pack',None)),
                        (urwid.Text('debug'),('pack',None)),
                        (urwid.Text('quit'),('pack',None)),
                    ]
            return super().keypress(size, key)

try:
    from hello_world import dummy_compiler
except ImportError:
    def dummy_compiler( data, ttable = None, oddLine = True ):
        return [data], [None for _ in range(len(data))]

def search_and_highlight( needle, stack, widget = tuple, target = print ):
    #stack = [s[::-1] for s in stack[::-1].split('\t',1)[::-1]]
    cmd, desc = stack.split('\t',1)
    if all(n in desc for n in needle):
        out, flags = dummy_compiler( desc, needle )
        desc = []
        j = 0
        for i in range(len(out)):
            if flags[i]:
                #desc += fore_text(out[i],color)
                desc.append( ('', out[i] ) )
            else:
                if j%2:
                    #desc += fore_text(out[i],HL0)
                    desc.append( ('HL0', out[i] ) )
                else:
                    #desc += fore_text(out[i],HL1)
                    desc.append( ('HL1', out[i] ) )
                j += 1
        #raise Exception(widget, cmd, desc)
        target( widget( (cmd, desc) ) )


def main(SER, machine_name, serial_port, maxtempi, gcodes):
    global loop, edit, ack_pile, wip_pile, wai_pile, machine_pos, messages, tbars, info_dic, watch_pipe, machine_status, gcode_piles, div, cmd_pile, all_wai, editmap

    from threading import Thread
    t = Thread(target=read_from_serial, args=(SER,), daemon = True )
    edit = urwid.Edit(('prompt',">>> "))

    div = urwid.Divider('-')
    #from time import sleep
    #sleep(2)

    ack_pile = ACKPile( 'ACK Pile', commands_ack, display_size = DISP_ACK_LEN, color = 'acked' )
    wip_pile = WIPPile( 'Processing...', max_content_len = MAX_COMMANDS_IN_WIP, color = 'wip' )   # this is WIP pile, instructions have been sent to the machine but not acked yet
    wai_pile = WQueue( 'User input pile', commands_wai, display_size = DISP_WAI_LEN, viewport_start = 0 )

    gcode_piles = {}
    if gcodes:
        for gcode in gcodes:
            logger.info(f"Loading file: {gcode}")
            with open(gcode,'rb') as g:
                gcode_piles[gcode] = WQueue( gcode, [line.rstrip(b'\n').replace(b'\t', b' ') for line in g.readlines() if line != b'\n'], display_size = DISP_WAI_LEN, viewport_start = 0 )
        #logger.info(gcode_piles[gcode])
        #logger.info(gcode_piles[gcode].widget.contents)

    #logger.info('>>>', wai_pile.widget)
    #logger.info('>>>', [gcode_piles[filename].widget for filename in gcode_piles.keys()])
    all_wai = urwid.Columns([wai_pile.widget, *[gcode_piles[filename].widget for filename in gcode_piles.keys()]])
    #logger.info(all_wai)
    #all_wai = urwid.SolidFill('?')

    editmap = urwid.AttrMap( UserInput(edit), 'prompt' )
    cmd_pile = urwid.Pile([ ack_pile.widget, wip_pile.widget, all_wai, editmap ])

    machine_pos = urwid.Text("")

    class AbsoluteBar(urwid.ProgressBar):
        def __init__(self, *args, prefix = '', suffix = '°C', **kwargs):
            super().__init__(*args, **kwargs)
            self.prefix = prefix
            self.suffix = suffix

        def get_text(self):
            return self.prefix + str(self.current) + self.suffix

    # TODO make this more dynamic, from config settings
    tbars = {
        b'T': [
                AbsoluteBar('', 'pb_pwr', done = maxtemp[1], prefix = 'pwr: ', suffix ='%' ), # power setting
                AbsoluteBar('', 'pb_tgt', done = maxtemp[0], prefix = 'set: ' ), # target temperature
                AbsoluteBar('', 'pb_temp', done = maxtemp[0], prefix = 'read: ' ), # current temperature
            ],
        b'B': [
                AbsoluteBar('', 'pb_pwr', done = maxtemp[1], prefix = 'pwr: ', suffix ='%' ),
                AbsoluteBar('', 'pb_tgt', done = maxtemp[0], prefix = 'set: ' ),
                AbsoluteBar('', 'pb_temp', done = maxtemp[0], prefix = 'read: ' ),
            ],
    }


    # temperature bars
    def temps_pile(dic):
        lst = []
        for k in dic.keys():
            lst.append( urwid.Text(k))
            lst.extend( dic[k] )
        return urwid.Pile( lst )

    info_dic = urwid.Pile([urwid.Text(PROGHELP)])
    machine_status = urwid.Text(('status_UNK', ' '+machine_name+' '), 'center')
    messages = urwid.Pile(deque([]))
    context_pile = urwid.Pile([
            machine_status, div,
            machine_pos, div,
            temps_pile(tbars), div,
            info_dic, div,
            messages,
        ])

    cols = urwid.Columns([cmd_pile,context_pile])

    filler = urwid.Filler(cols, "top")
    frame  = urwid.Frame(filler, header=titlemap)
    loop   = urwid.MainLoop(frame, palette)
    watch_pipe = loop.watch_pipe(serial_comm_still_ok)

    t.start()
    loop.run()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog=PROGNAME,
        description=PROGDESC,
    )
    parser.add_argument("-c", "--config", help="machine configuration", default = None, metavar="file")
    parser.add_argument("-g", "--gcode", help="gcode to preload", default = None, metavar="file", nargs='*')
    parser.add_argument("-p", "--port", default = None, help="serial port override", metavar="device")
    parser.add_argument("-b", "--baudrate", default = None, type=int, help="baud rate override", metavar="int")

    parser.add_argument("-l", "--log", default = '/var/log/GWiz/GWiz.log', help="write log to file", metavar="file")
    parser.add_argument("--log-level", default = 'WARNING', help="log level", metavar="str")
    parser.add_argument("--log-mode", default = 'a', help="open log in mode [w|a]", metavar="str")
    parser.add_argument("-o", "--out", default = None, help="write machine I/O to file", metavar="file")
    parser.add_argument("--out-level", default = 'DEBUG', help="machine output level", metavar="str")
    parser.add_argument("--out-mode", default = 'w', help="open machine output file in mode [w|a]", metavar="str")

    args = parser.parse_args()
    
    logger.setLevel(args.log_level)
    logger.debug(f"Logging initialized: {__name__}")

    if args.config is None:
        #print('need to specify machine configuration with "--config"', file=stderr)
        logger.critical('need to specify machine configuration with "--config"')
        sys.exit()

    out_formatter = logging.Formatter('%(levelname)s\t%(message)s')
    """
        read machine config
    """
    with open(args.config) as machineconf:
        while True:
            line = machineconf.readline().split('=')
            match line[0]:
                case 'machine_name':
                    machine_name = line[1].rstrip('\n')
                case 'serial_port':
                    serial_port = line[1].rstrip('\n') if args.port is None else args.port
                case 'baudrate':
                    baudrate = int(line[1].rstrip('\n')) if args.baudrate is None else args.baudrate
                case 'maxtemp':
                    maxtemp = [int(i) for i in line[1].rstrip('\n').split(',')]
                case '# G-Code starts here\n':
                    break
                case other:
                    if not line[0].startswith('#') and line[0] != '\n':
                        logger.info(f"unrecognized config option: {line}")

        for line in machineconf.readlines():
            if not line.startswith('#'):
                command, desc = line.rstrip('\n').split('=')
                valid_commands[command] = desc
                #logger.info("GOT COMMAND:",command,desc)

    result = logging.getLogger(machine_name)    # TODO looks like this inherits from root logger because it seems to use handler_streamHandler that prints CRITICAL messages on stderr and always
    f_handler = logging.FileHandler( machine_name+'.out' if args.out is None else args.out )
    f_handler.setFormatter( out_formatter )
    result.addHandler(f_handler)
    result.setLevel(args.out_level)
    result.info(f";{pendulum.now()}:Logging initialized for {machine_name}")


    # Validate GCODE input
    if args.gcode:
        for gcode in args.gcode:
            if gcode is not None and os.path.exists(gcode):
                if os.path.isfile(gcode):
                    if gcode.strip().lower().endswith(".gcode"):
                        continue
                    else:
                        logger.critical(f"{gcode} does not have .gcode extension.")
                        sys.exit()
                else:
                    logger.info(f"{gcode} is not a file.")
                    sys.exit()
            elif gcode is not None:
                logger.info(f"{gcode} does not exist.")
                sys.exit()

    for line in BANNER.split('\n'):
        logger.info(line)
    try:
        termwidth = os.get_terminal_size().columns-1
    except OSError:
        termwidth = 80
    logger.info(f"""{termwidth*'='}
    Machine name: {machine_name}
    Port name: {serial_port}
    Baud rate: {baudrate}
    G-Code: {args.gcode}
{termwidth*'='}""")
    SER = serial.Serial(serial_port, baudrate)

    #from time import sleep
    #sleep(.5)

    main(
        SER,
        machine_name, serial_port,
        maxtemp,
        args.gcode,
    )
