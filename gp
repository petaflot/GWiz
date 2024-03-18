#!/usr/bin/env python

import asyncio
import serial
from threading import Thread
import logging
import logging.config
from sys import exit
logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=False)
logger = logging.getLogger('stderrLogger')

# TODO allow overring these values in printer config
PORT_AUTODETECT = '/dev/ttyACM', '/dev/ttyUSB'
SERIAL_TIMEOUT = 10
BUFFER_FULL_WAIT = .1
# set this to the queue size if ADVANCED_OK is not set, else False
ADVANCED_OK_WORKAROUND = False


BUFFER_DEBUG = {'P': None, 'B': None, 'Pstarve': 0}
# gets set to True when the last command has been ACKed
WAIT_AND_QUIT = False
# current buffer usage
# None: machine not ready
# int: free slots
# False: waiting for completion of terminating M400
# True: will call exit() soon
BUFFSIZE = None
# None: print not started (M77)
# True: print started (M75)
# False: print paused (M76)
PRINT_STARTED = None

def serial_read(ser):
    global BUFFSIZE

    while True:
        reply = ser.readline().decode().strip()
        if reply.startswith('ok'):
            reply = reply.split(' ')[1:]
            try:
                BUFFER_DEBUG['P'] = int(reply[0].lstrip('P'))
                if BUFFER_DEBUG['P'] > BUFFER_DEBUG['Pstarve']:
                    # setting the starvation limit for planner buffer ; should only happen once
                    BUFFER_DEBUG['Pstarve'] = BUFFER_DEBUG['P']
                    logger.info(f"planner buffer starvation threshold set to {BUFFER_DEBUG['P']}")
                elif BUFFER_DEBUG['P'] == BUFFER_DEBUG['Pstarve']:
                    if PRINT_STARTED:
                        logger.info(f"planner buffer is starving (host too slow? try decreasing {BUFFER_FULL_WAIT=})")
            except ValueError:
                logger.error(f"could not extract 'P' from {reply}")
            try:
                BUFFER_DEBUG['B'] = int(reply[1].lstrip('B'))
                if BUFFSIZE is None:
                    BUFFSIZE = BUFFER_DEBUG['B']
                    # TODO confirm readiness by playing a tune and/or blinking LEDs, useful to identify printer when there many -> in printer config
                #elif BUFFSIZE is False and WAIT_AND_QUIT:
                #    BUFFSIZE = True
                    
                #elif BUFFSIZE != BUFFER_DEBUG['B']:
                #    logger.warning(f"buffer discrepancy: {BUFFER_DEBUG['B']=}, {BUFFSIZE=}")
            except ValueError:
                logger.error(f"ValueError: could not extract 'B' from {reply}")
            except IndexError:
                logger.error(f"IndexError: could not extract 'B' from {reply}")
                

            #if WAIT_AND_QUIT:
            #    print(f"{BUFFSIZE} {BUFFER_DEBUG['B']}")
            #    # this is pretty flaky...
            #    if BUFFSIZE == BUFFER_DEBUG['B']:
            #        result.critical(f"quitting soon {reply}")
            #        BUFFSIZE = True
            if BUFFSIZE >= 0:
                #result.debug(reply)
                BUFFSIZE += 1
            else:
                result.warn(f"received '{reply}' but machine was not ready and no command was sent by this instance")
            continue
        elif reply.startswith('echo:busy: processing'):
            result.debug(reply)
        elif reply.startswith( ('T:', 'X:') ):
            print(reply)
        elif reply.startswith( ('echo', '//') ):
            if reply.startswith('echo:Unknown command:'):
                result.error(reply)
            else:
                result.info(reply)
        elif BUFFSIZE is None and (reply in ('start', 'pages_ready', 'wait') or reply.startswith( ( 'T:', ) )):
            result.info(f"machine ready ({reply})")
            if not ADVANCED_OK_WORKAROUND:
                ser.write(b'G4\n')
                result.debug('G4; dwell for no time just so we get a clue of the queue size')
            else:
                BUFFSIZE = ADVANCED_OK_WORKAROUND

            #if WAIT_AND_QUIT and BUFFSIZE is False:
            #    BUFFSIZE = True
        elif reply == 'wait':
            #if WAIT_AND_QUIT:
            #    print(BUFFSIZE)
            #    result.debug(f"host quitting soon")
            #    BUFFSIZE -= 1
            #    ser.write(b'M400\n')
            #    result.debug('M400 ; wait for moves to finish')
            #    BUFFSIZE -= 1
            #    ser.write(b'M300 S437 P1000\n')
            #    result.debug('M300 ... ; play a tune')
            #else:
            result.debug(reply)
        elif reply.startswith('Error:'):
            logger.error(reply)
        #elif ...   # TODO fatal messages (machine halts)
        #    result.fatal(reply)
        #    logger.fatal(reply)
        #    exit()
        else:
            result.warning(reply)


async def main( ser, args, gcodes ):
    global BUFFSIZE#, WAIT_AND_QUIT

    t = Thread(target=serial_read, args=(ser,), daemon = True )
    t.start()

    await asyncio.sleep(1)
    def _open( file ):
        try:
            return open(input_file, 'r') 
        except TypeError:
            return file

    for input_file in gcodes:
        logger.info(f"piping gcode from {input_file}")
        with _open(input_file) as gcode:
            for line in gcode.readlines():
                if not line.startswith(';'):
                    cmd = line.split(';',1)[0].strip().rstrip(' ')
                    if len(cmd):
                        while True:
                            try:
                                if BUFFSIZE > 0:
                                    BUFFSIZE -= 1
                                    logger.debug(f"P:{BUFFER_DEBUG['P']}\tB:{BUFFER_DEBUG['B']}\t{BUFFSIZE}\t>>>{cmd}<<<")
                                    if cmd == 'M75':
                                        PRINT_STARTED = True
                                    elif cmd == 'M76':
                                        PRINT_STARTED = False
                                    elif cmd == 'M77':
                                        PRINT_STARTED = None
                                    ser.write(bytes(cmd,args.encoding)+b'\n')
                                    break
                                else:
                                    await asyncio.sleep(BUFFER_FULL_WAIT)
                            except TypeError:
                                await asyncio.sleep(BUFFER_FULL_WAIT)
                else:
                    result.debug(line.strip())
    #WAIT_AND_QUIT = True
    #
    #logger.debug(f"no gcode left, waiting for machine to finish")
    #while type(BUFFSIZE) is int and BUFFSIZE is not True:
    #    await asyncio.sleep(BUFFER_FULL_WAIT)
        #print(f"P:{BUFFER_DEBUG['P']}\tB:{BUFFER_DEBUG['B']}\t{BUFFSIZE}")
        #await asyncio.sleep(1)

    logger.info(f"all done, (how) ex(c)iting!")
    exit()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog="gp",
        description="gpipe is a very simple program that reads gcode from a\nfile (or standard input if no filenames are provided) and pipes it to a machine \non a serial port.",
    )
    parser.add_argument("-c", "--config", help="machine configuration", default = None, metavar="file")
    parser.add_argument("-p", "--port", default = None, help="serial port override", metavar="device")
    parser.add_argument("-b", "--baudrate", default = None, type=int, help="baudrate override", metavar="int")
    parser.add_argument("-t", "--timeout", default = SERIAL_TIMEOUT, type=int, help="serial timeout ({SERIAL_TIMEOUT} [s])", metavar="int")
    parser.add_argument("-e", "--encoding", default = 'utf8', type=str, help="encoding to use when sending to the machine (utf8)", metavar="str")

    parser.add_argument("-g", "--gcode", help="gcode to preload (can be specified multiple times)", default = None, metavar="file", nargs='*')

    # TODO doesn't seem to work with config file
    #parser.add_argument("-l", "--log", default = '/var/log/GWiz/gp.log', help="write log to file", metavar="file")
    parser.add_argument("--log-level", default = None, help="log level", metavar="str")
    parser.add_argument("--log-mode", default = 'a', help="open log in mode [w|a]", metavar="str")

    parser.add_argument("-o", "--out", default = None, help="write machine I/O to file", metavar="file")
    parser.add_argument("--out-level", default = 'INFO', help="machine output level", metavar="str")
    parser.add_argument("--out-mode", default = 'w', help="open machine output file in mode [w|a]", metavar="str")
    args = parser.parse_args()


    if args.log_level:
        logger.setLevel(args.log_level)
    logger.debug(f"Logging initialized: {__name__}")



    ser = serial.Serial(timeout=args.timeout)

    out_formatter = logging.Formatter('%(levelname)s:%(message)s')
    if args.config is not None:
        #out_formatter = logging.Formatter('%(levelname)s\t%(message)s')    # keep for debugging..
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
                        ser.port = line[1].rstrip('\n') if args.port is None else args.port
                        logger.debug(f"serial port: {ser.port}")
                    case 'baudrate':
                        ser.baudrate = int(line[1].rstrip('\n')) if args.baudrate is None else args.baudrate
                        logger.debug(f"serial baudrate: {ser.baudrate}")
                    case 'maxtemp':
                        #maxtemp = [int(i) for i in line[1].rstrip('\n').split(',')]
                        pass
                    case '# G-Code starts here\n':
                        break
                    case other:
                        if not line[0].startswith('#') and line[0] != '\n':
                            logger.error(f"unrecognized config option: {line}")
    else:
        machine_name = "machine"
        if args.port is None:
            # TODO auto-detection 
            raise NotImplementedError("No serial sport specified")
        else:
            ser.port = args.port
        ser.baudrate = args.baudrate

    result = logging.getLogger(machine_name)
    f_handler = logging.FileHandler( machine_name+'.out' if args.out is None else args.out )    # TODO allow writing to stdout
    f_handler.setFormatter( out_formatter )
    result.addHandler(f_handler)
    result.setLevel(args.out_level)

    import pendulum
    TIME_FMT = "%Y-%m-%d %H:%M:%S"
    #TIME_FMT = "%H:%M:%S.%s"
    TIME_LEN = len(pendulum.now().strftime(TIME_FMT))+1
    result.info(f";{pendulum.now()}:Logging initialized for {machine_name}")


    # Validate GCODE input
    if args.gcode:
        import os
        for gcode in args.gcode:
            if gcode is not None and os.path.exists(gcode):
                if os.path.isfile(gcode):
                    if gcode.strip().lower().endswith( (".gcode", ".g") ):
                        continue
                    else:
                        logger.critical(f"{gcode} does not have .gcode or .g extension.")
                        exit()
                else:
                    logger.critical(f"{gcode} is not a file.")
                    exit()
            elif gcode is not None:
                logger.critical(f"{gcode} does not exist.")
                exit()
            logger.debug(f"adding gcode file: {gcode}")
        gcodes = args.gcode
    else:
        from sys import stdin
        logger.debug("reading gcode from stdin")
        gcodes = [ stdin ]


    try:
        ser.open()
    except serial.serialutil.SerialException:
        logger.fatal(f"could not open {ser.port}")
    else:
        try:
            asyncio.run(main( ser, args, gcodes ))
        except KeyboardInterrupt:
            logger.fatal(f"aborted by user (ctrl+c)")

