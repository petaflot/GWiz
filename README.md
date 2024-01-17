```
      ╻ ╻      ┏━╸   ┏━╸┏━┓╺┳┓┏━╸   ╻ ╻╻╺━┓┏━┓┏━┓╺┳┓      ╻ ╻
   ╺━╸╺╋╸╺━╸   ┃╺┓╺━╸┃  ┃ ┃ ┃┃┣╸    ┃╻┃┃┏━┛┣━┫┣┳┛ ┃┃   ╺━╸╺╋╸╺━╸
      ╹ ╹      ┗━┛   ┗━╸┗━┛╺┻┛┗━╸   ┗┻┛╹┗━╸╹ ╹╹┗╸╺┻┛      ╹ ╹
```
GWiz is an advanced gcode *"man-in-the-middleware"* that aims to make it comfortable to tune a machine (initial tuning and config) as well as tuning complicated prints[^print], including keeping track of all changes to a print in order to replay and gradually improve the prints.

GWiz sort-of competes with [pronsole](https://github.com/kliment/Printrun) but it aims to be lighter, more flexible, more user-friendly. GWiz requires very few dependencies and uses [urwid](http://urwid.org/).

This program moves g-code instructions from the developper's mind (or G-Code file, pile 'zero') sequentially to a number of other piles:

- 'wait' pile: instructions that are scheduled to be sent to the machine, but the machine's buffer is full (or we don't want to send them right away to allow insertion of other instructions, see `buffsize` command)
- 'wip' pile : instructions that have been sent to the machine's buffer, no ack or error message is available yet
- 'ack' pile : the last pile, instructions have been processed by the machine ; they have either an 'ok' message or an error message attached. This pile also contains most messages sent by the machine and user comments.

more info at the top of the GWiz.py file (or when running the program itself ; that's already more than enough redundancy)


[^print]: prints or any other program sent to a machine
