#!/usr/bin/env python

import asyncio
import serial
from threading import Thread
import logging
import logging.config
logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=False)
logger = logging.getLogger('stderrLogger')

BUFFSIZE = 0
PORT_AUTODETECT = '/dev/ttyACM', '/dev/ttyUSB'
TIMEOUT = 5

def serial_read(s,buffsize):
    global BUFFSIZE

    while True:
        reply = s.readline().decode().strip()
        if reply.startswith('ok'):
            result.debug(reply)
            BUFFSIZE += 1
            continue
        elif reply.startswith('echo:busy: processing'):
            result.debug(reply)
            continue
        elif reply in ('start', 'pages_ready'):
            result.info(reply)
            BUFFSIZE = buffsize
        elif reply.startswith( ('echo', '//') ):
            result.info(reply)
        elif reply.startswith('Error'): # TODO not the correct string
            result.error(reply)
        #elif ...   # TODO fatal messages (machine halts)
        #    result.fatal(reply)
        #    logger.fatal(reply)
        #    quit program
        else:
            result.warning(reply)


async def main( ser, args, gcodes ):
    global BUFFSIZE

    t = Thread(target=serial_read, args=(ser,args.buffsize), daemon = True )
    t.start()

    await asyncio.sleep(1)
    def _open( file ):
        try:
            return open(input_file, 'r') 
        except TypeError:
            return file

    for input_file in gcodes:
        with _open(input_file) as gcode:
            for line in gcode.readlines():
                if not line.startswith(';'):
                    cmd = line.split(';',1)[0].strip().rstrip(' ')
                    if len(cmd):
                        while True:
                            if BUFFSIZE:
                                BUFFSIZE -= 1
                                logger.debug(f"{BUFFSIZE}\t>>> {cmd}")
                                ser.write(bytes(cmd,args.encoding)+b'\n')
                                break
                            else:
                                await asyncio.sleep(.1)
                elif line.startswith(";:"):
                    # TODO special directives to tell program to quit or sleep or ...
                    #asyncio.sleep(specified timeout)
                    sys.exit()
                else:
                    result.debug(line)

    logging.debug(f"gcode finished, quitting in {args.timeout}[s]")
    await asyncio.sleep(args.timeout)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog="gp",
        description="gpipe is a very simple program that reads gcode from a\nfile (or standard input if no filenames are provided) and pipes it to a machine \non a serial port.",
    )
    parser.add_argument("-c", "--config", help="machine configuration", default = None, metavar="file")
    parser.add_argument("-p", "--port", default = None, help="serial port override", metavar="device")
    parser.add_argument("-b", "--baudrate", default = None, type=int, help="baudrate override", metavar="int")
    parser.add_argument("-t", "--timeout", default = TIMEOUT, type=int, help="serial timeout ({TIMEOUT} [s])", metavar="int")
    parser.add_argument("-B", "--buffsize", default = 15, type=int, help="machine buffer size", metavar="int")
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

    out_formatter = logging.Formatter('%(message)s')
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
            raise NotImplementedError
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
                        sys.exit()
                else:
                    logger.critical(f"{gcode} is not a file.")
                    sys.exit()
            elif gcode is not None:
                logger.critical(f"{gcode} does not exist.")
                sys.exit()
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
        asyncio.run(main( ser, args, gcodes ))

