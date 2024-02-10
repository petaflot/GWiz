PROGNAME="G-Wiz"
PROGDESC="G-Code Wizard: a geeky yet friendly way to communicate with machines such as 3D-Printers"
PROGHELP="""
      ╻ ╻      ┏━╸   ┏━╸┏━┓╺┳┓┏━╸   ╻ ╻╻╺━┓┏━┓┏━┓╺┳┓      ╻ ╻
   ╺━╸╺╋╸╺━╸   ┃╺┓╺━╸┃  ┃ ┃ ┃┃┣╸    ┃╻┃┃┏━┛┣━┫┣┳┛ ┃┃   ╺━╸╺╋╸╺━╸
      ╹ ╹      ┗━┛   ┗━╸┗━┛╺┻┛┗━╸   ┗┻┛╹┗━╸╹ ╹╹┗╸╺┻┛      ╹ ╹

This program moves gcode instructions from the developper's mind (or G-Code file, pile 'zero') sequentially to a number of other piles:

- 'ack' pile : the last pile, instructions have been processed by the machine ; they have either an 'ok' message or an error message attached. This pile also contains most messages sent by the machine and user comments.
- 'wip' pile : instructions that have been sent to the machine's buffer, no ack or error message is available yet
- 'wait' pile: instructions that are scheduled to be sent to the machine, but the machine's buffer is full (or we don't want to send them right away to allow insertion of other instructions, see `buffsize` command)

Modes of operation:
- 'normal': typed text is sent to the machine from the top of the 'wait' pile (enable with 'esc' key, also clears command line)
- 'search': search for the typed words in machine's command description (enable with 'alt+s' or '?') ; the list of commands (and their description) is specific to each machine in order to allow customization.
- 'command': execute a built-in command to interract with G-Wiz (enable with ':' like in Vi, also shows list of commands in the help box)
- 'history': replay a command previously sent (or scheduled to be sent) to the machine (enable with '!<str>' or '<int>', where <int> is the negative index of the command to be replayed. TODO)

G-Wiz makes it possible to alter parameters such as feedrate, extrusion ratio and temperatures on-the-fly and keep track of these changes to optimize subsequent prints ; this includes adding comments, pauses (TODO), user-defined macros. This makes G-Wiz a powerful G-Code post-processor and a friendly ally to tune machine parameters.

Usage notes:
- When searching for a command and only one choice remains, that command is automatically typed for you
- In command mode, the right panel (here) shows command usage and parameters for the typed command (TODO)
- at the time of this writing, multiple gcodes are executed sequentially (no interpolation)
"""

BANNER="""[38;5;129m [39m[38;5;129m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m╻[39m[38;5;93m [39m[38;5;93m╻[39m[38;5;93m [39m[38;5;93m [39m[38;5;99m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m┏[39m[38;5;63m━[39m[38;5;63m╸[39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m┏[39m[38;5;63m━[39m[38;5;69m╸[39m[38;5;33m┏[39m[38;5;33m━[39m[38;5;33m┓[39m[38;5;33m╺[39m[38;5;33m┳[39m[38;5;33m┓[39m[38;5;33m┏[39m[38;5;33m━[39m[38;5;33m╸[39m[38;5;39m [39m[38;5;39m [39m[38;5;39m [39m[38;5;39m╻[39m[38;5;39m [39m[38;5;39m╻[39m[38;5;39m╻[39m[38;5;39m╺[39m[38;5;39m━[39m[38;5;38m┓[39m[38;5;38m┏[39m[38;5;44m━[39m[38;5;44m┓[39m[38;5;44m┏[39m[38;5;44m━[39m[38;5;44m┓[39m[38;5;44m╺[39m[38;5;44m┳[39m[38;5;44m┓[39m[38;5;44m [39m[38;5;44m [39m[38;5;43m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m╻[39m[38;5;49m [39m[38;5;49m╻[39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m[39m
[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m╺[39m[38;5;93m━[39m[38;5;93m╸[39m[38;5;93m╺[39m[38;5;93m╋[39m[38;5;99m╸[39m[38;5;63m╺[39m[38;5;63m━[39m[38;5;63m╸[39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m┃[39m[38;5;63m╺[39m[38;5;63m┓[39m[38;5;63m╺[39m[38;5;63m━[39m[38;5;69m╸[39m[38;5;33m┃[39m[38;5;33m [39m[38;5;33m [39m[38;5;33m┃[39m[38;5;33m [39m[38;5;33m┃[39m[38;5;33m [39m[38;5;33m┃[39m[38;5;33m┃[39m[38;5;39m┣[39m[38;5;39m╸[39m[38;5;39m [39m[38;5;39m [39m[38;5;39m [39m[38;5;39m [39m[38;5;39m┃[39m[38;5;39m╻[39m[38;5;39m┃[39m[38;5;38m┃[39m[38;5;38m┏[39m[38;5;44m━[39m[38;5;44m┛[39m[38;5;44m┣[39m[38;5;44m━[39m[38;5;44m┫[39m[38;5;44m┣[39m[38;5;44m┳[39m[38;5;44m┛[39m[38;5;44m [39m[38;5;44m┃[39m[38;5;43m┃[39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m╺[39m[38;5;49m━[39m[38;5;49m╸[39m[38;5;49m╺[39m[38;5;49m╋[39m[38;5;49m╸[39m[38;5;49m╺[39m[38;5;48m━[39m[38;5;48m╸[39m[38;5;48m[39m
[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;93m [39m[38;5;99m [39m[38;5;63m╹[39m[38;5;63m [39m[38;5;63m╹[39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m [39m[38;5;63m┗[39m[38;5;63m━[39m[38;5;69m┛[39m[38;5;33m [39m[38;5;33m [39m[38;5;33m [39m[38;5;33m┗[39m[38;5;33m━[39m[38;5;33m╸[39m[38;5;33m┗[39m[38;5;33m━[39m[38;5;33m┛[39m[38;5;39m╺[39m[38;5;39m┻[39m[38;5;39m┛[39m[38;5;39m┗[39m[38;5;39m━[39m[38;5;39m╸[39m[38;5;39m [39m[38;5;39m [39m[38;5;39m [39m[38;5;38m┗[39m[38;5;38m┻[39m[38;5;44m┛[39m[38;5;44m╹[39m[38;5;44m┗[39m[38;5;44m━[39m[38;5;44m╸[39m[38;5;44m╹[39m[38;5;44m [39m[38;5;44m╹[39m[38;5;44m╹[39m[38;5;44m┗[39m[38;5;43m╸[39m[38;5;49m╺[39m[38;5;49m┻[39m[38;5;49m┛[39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m [39m[38;5;49m╹[39m[38;5;48m [39m[38;5;48m╹[39m[38;5;48m [39m[38;5;48m [39m[38;5;48m [39m[38;5;48m[39m"""

