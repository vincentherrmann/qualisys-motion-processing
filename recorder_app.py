import tkinter
from tkinter import filedialog, messagebox, Button, Label, Entry, Frame, Toplevel
from osc_handling import OscRecorder

from osc4py3.as_allthreads import *

def osc_settings(app):

    win = Toplevel()
    win.wm_title("settings")

    def confirm_settings():
        osc_terminate()
        app.recorder = OscRecorder(receive_address=receive_address_entry.get(),
                                   receive_port=receive_port_entry.get(),
                                   send_address=send_address_entry.get(),
                                   send_port=send_port_entry.get())
        win.destroy()

    receive_address_label = Label(win, text='receive address:')
    receive_address_label.grid(row=0, column=0)
    receive_address_entry = Entry(win)
    receive_address_entry.grid(row=0, column=1)
    receive_address_entry.insert(0, app.recorder.receive_address)

    receive_port_label = Label(win, text='port:')
    receive_port_label.grid(row=0, column=2)
    receive_port_entry = Entry(win)
    receive_port_entry.grid(row=0, column=3)
    receive_port_entry.insert(0, app.recorder.receive_port)

    send_address_label = Label(win, text='send address:')
    send_address_label.grid(row=1, column=0)
    send_address_entry = Entry(win)
    send_address_entry.grid(row=1, column=1)
    send_address_entry.insert(0, app.recorder.send_address)

    send_port_label = Label(win, text='port:')
    send_port_label.grid(row=1, column=2)
    send_port_entry = Entry(win)
    send_port_entry.grid(row=1, column=3)
    send_port_entry.insert(0, app.recorder.send_port)

    l = Label(win, text="Input")
    l.grid(row=2, column=0)

    b = Button(win, text="Cancel", command=win.destroy)
    b.grid(row=2, column=1)

    b = Button(win, text="Okay", command=confirm_settings)
    b.grid(row=2, column=1)


class Application(Frame):
    def __init__(self, master):
        super().__init__(master)

        self.recorder = OscRecorder(receive_address='', send_address='')
        self.pack()

        self.loadFileButton = Button(self, text="Load File", command=self.load_file_callback)
        self.loadFileButton.pack()

        self.durationLabel = Label(self, text='duration: {:9.3f} s'.format(self.recorder.duration))
        self.durationLabel.pack()

        self.saveFileButton = Button(self, text="Save File", command=self.save_file_callback)
        self.saveFileButton.pack()

        self.button_bonus = Button(self, text="OSC Settings", command=lambda: osc_settings(self))
        self.button_bonus.pack()

    def load_file_callback(self):
        path = filedialog.askopenfilename(title='Choose a file')
        self.recorder.load_text_file(path)
        self.durationLabel['text'] = 'duration: {:9.3f} s'.format(self.recorder.duration)
        print(path)

    def save_file_callback(self):
        path = filedialog.asksaveasfilename(title='Save File')
        self.recorder.save_recording_as_text(path)
        print(path)

root = tkinter.Tk()

app = Application(root)

root.mainloop()