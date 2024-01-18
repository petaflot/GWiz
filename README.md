```
      ╻ ╻      ┏━╸   ┏━╸┏━┓╺┳┓┏━╸   ╻ ╻╻╺━┓┏━┓┏━┓╺┳┓      ╻ ╻
   ╺━╸╺╋╸╺━╸   ┃╺┓╺━╸┃  ┃ ┃ ┃┃┣╸    ┃╻┃┃┏━┛┣━┫┣┳┛ ┃┃   ╺━╸╺╋╸╺━╸
      ╹ ╹      ┗━┛   ┗━╸┗━┛╺┻┛┗━╸   ┗┻┛╹┗━╸╹ ╹╹┗╸╺┻┛      ╹ ╹
```
GWiz is an advanced gcode *"man-in-the-middleware"* that aims to make it comfortable to tune a machine (initial tuning and config) as well as tuning complicated prints[^print], including keeping track of all changes to a print in order to replay and gradually improve the prints. In the near future, it should enable synchronised collaborative work of a number of machines.

GWiz sort-of competes with [pronsole](https://github.com/kliment/Printrun) but it aims to be lighter, more flexible, more user-friendly. GWiz requires very few dependencies and uses [urwid](http://urwid.org/) as a toolkit, which allows a GUI-like feeling in a terminal or remote shell (ssh).

This program moves gcode instructions from the developper's mind (or G-Code file, pile 'zero') sequentially to a number of other piles:

- 'wait' pile: instructions that are scheduled to be sent to the machine, but the machine's buffer is full (or we artificially throttle them[^throttle])
- 'wip' pile : instructions that have been sent to the machine's buffer, no ack or error message is available yet
- 'ack' pile : the last pile, instructions have been processed by the machine ; they have either an 'ok' message or an error message attached. This pile also contains most messages sent by the machine and user comments.


Other notable features include:
- searchable list of gcode commands by description (list set in machine config) ; in the future it will also display command usage (auto-fetched from firmware doc)
- a silly MIDI-to-M300 converted that is clueless about rythm so you can play your favorite tunes on your device's speaker

more info in the `proghelp.py` file (or when running the program itself).


# How to run GWiz

for example
```
./GWiz.py -c machine.conf -g part0.gcode -g part1.gcode 2>/tmp/gwiz.log
```

and simaultaneously running
```
tail -f /tmp/gwiz.log
```
in another term for debug output should this be required.

# Note

G-Code Wizard is in early development stage.


[^print]: prints or any other program sent to a machine
[^throttle]: reducing the number of commands in the machine buffer has a number of use cases, for example to allow insertion of other instructions or aborting/pausing prints faster: this is most useful during machine tuning. See `buffsize` command - or to be able to stop a print faster 
