import time
import rtmidi
import threading
import math
#from matplotlib import pyplot as plt
#import matplotlib.animation
import numpy as np
import copy
import pickle
import ast

from osc4py3.as_allthreads import *
from osc4py3 import oscmethod as osm, oscbuildparse


class MotionProcessor:
    def __init__(self, beat_callback, origin=np.zeros(3), scaling=np.ones(3), permutation=[0, 1, 2], move_callback=None,
                 beat_threshold=1.,
                 max_accel=100000.,
                 smoothing=4,
                 processor_id=0):
        self.beat_callback = beat_callback
        self.move_callback = move_callback
        self.origin = origin
        self.scaling = scaling
        self.permutation = permutation
        self.beat_threshold = beat_threshold
        self.max_accel = max_accel
        self.smoothing = smoothing
        self.write_position = 0
        self.last_time = 0
        self.last_beat_time = 0

        self.last_position = np.zeros(3)
        self.last_speed = np.zeros(3)
        self.last_accel = np.zeros(3)
        self.last_differences = np.zeros([self.smoothing, 3])

        self.print_details = False
        self.processor_id = processor_id
        self.current_blob_id = 0

        self.recording = False
        self.record_position = 0
        self.record_steps = 0
        self.recorded_position = np.zeros([1, 3])
        self.recorded_speed = np.zeros([1, 3])
        self.recorded_accel = np.zeros([1, 3])
        self.recorded_jerk = np.zeros([1, 3])

    def move(self, time_stamp, pos, blob_id=0):
        time_diff = time_stamp - self.last_time
        if time_diff < 1e-6:
            return

        pos = pos[self.permutation]
        pos -= self.origin
        pos *= self.scaling
        pos_diff = (pos - self.last_position) / time_diff

        if blob_id != self.current_blob_id:
            self.last_time = time_stamp
            self.current_blob_id = blob_id
            self.last_position = pos

        self.write_position = (self.write_position + 1) % self.smoothing
        self.last_differences[self.write_position] = pos_diff
        speed = np.mean(self.last_differences, axis=0)
        accel = speed - self.last_speed
        jerk = accel - self.last_accel

        self.last_position = pos
        self.last_speed = speed
        self.last_accel = accel
        self.last_time = time_stamp

        if self.print_details:
            print("blob id:", blob_id,
                  "proc_id", self.processor_id,
                  "time:", time_stamp,
                  "pos:", pos,
                  "accel:", np.linalg.norm(accel),
                  "jerk:", np.linalg.norm(jerk),
                  "time_diff", time_diff)

        if self.recording:
            if self.record_position % 100 == 0:
                print("record... current position:", pos)
            self.recorded_position[self.record_position, :] = pos
            self.recorded_speed[self.record_position, :] = speed
            self.recorded_accel[self.record_position, :] = accel
            self.recorded_jerk[self.record_position, :] = jerk
            self.record_position += 1
            if self.record_position >= self.record_steps:
                self.recording = False
                print("finished recording")

        accel_norm = np.linalg.norm(accel)
        speed_change_dot = np.dot(speed, self.last_speed)

        if self.move_callback is not None:
            self.move_callback(pos, speed, accel, jerk, speed_change_dot, blob_id, time_stamp)

        #if np.dot(speed, self.last_speed) < 0. and np.linalg.norm(accel) >= self.beat_threshold:
        if self.max_accel > accel_norm >= self.beat_threshold:
            if time_diff > 0.2:
                return

            if time_stamp < self.last_beat_time + 0.1:
                return

            #if np.linalg.norm(accel) > 100:
            #    return

            self.last_beat_time = time_stamp
            self.beat_callback(pos, speed, accel, jerk, blob_id, time_stamp)

    def record_movement(self, steps=200):
        self.recorded_position = np.zeros([steps, 3])
        self.recorded_speed = np.zeros([steps, 3])
        self.recorded_accel = np.zeros([steps, 3])
        self.recorded_jerk = np.zeros([steps, 3])
        self.record_position = 0
        self.record_steps = steps
        self.recording = True


class OscCommunicator:
    def __init__(self,
                 receive_address='192.168.1.181',
                 receive_port=45453,
                 send_address='192.168.1.144',
                 send_port=45454,
                 receive_name='osc_receive',
                 send_name='osc_send',
                 thread_count=4):
        try:
            osc_startup(execthreadscount=thread_count)
        except:
            print("error during osc startup")

        self.receive_address = receive_address
        self.receive_port = receive_port
        self.send_address = send_address
        self.send_port = send_port
        self.send_name = send_name

        if receive_address is not None:
            osc_udp_server(receive_address, receive_port, receive_name)
        else:
            print("no receive address")
        if send_address is not None:
            osc_udp_client(send_address, send_port, send_name)
        else:
            print("no send address")
        osc_method("/*", self.handle, argscheme=osm.OSCARG_ADDRESS + osm.OSCARG_DATAUNPACK)

    def handle(self, address, *args):
        print(address, args)

    def send(self, address, data):
        msg = oscbuildparse.OSCMessage(address, None, data)
        osc_send(msg, self.send_name)


class OscRecorder(OscCommunicator):
    def __init__(self,
                 receive_address=None,
                 receive_port=22224,
                 send_address=None,
                 send_port=22225,
                 receive_name='osc_receive',
                 send_name='osc_send',
                 thread_count=4):

        super().__init__(receive_address=receive_address,
                         receive_port=receive_port,
                         receive_name=receive_name,
                         send_address=send_address,
                         send_port=send_port,
                         send_name=send_name,
                         thread_count=thread_count)

        self.sample_rate = 0.001
        self._play = False
        self._current_index = 0
        self.event_list = []
        self.duration = 0
        self.play_thread = threading.Thread(target=self.playback)

        self.print_messages = True

        self.record = False
        self.recorded_data = []
        self.start_time = 0

    def handle(self, address, *args):
        if self.print_messages:
            print(address, args)

        if self.record:
            print("record...")
            time_stamp = time.time() - self.start_time
            self.recorded_data.append((time_stamp, address, args))

    def start_recording(self):
        print("start recording")
        self.recorded_data = []
        self.start_time = time.time()
        self.record = True

    def stop_recording(self):
        self.record = False
        self.event_list = [ast.literal_eval(x) for x in self.recorded_data]
        self.duration = self.event_list[-1][0]

    def save_recording(self, path):
        with open(path, 'wb') as fp:
            pickle.dump(self.recorded_data, fp)

    def load_recording(self, path):
        with open(path, 'rb') as fp:
            self.recorded_data = pickle.load(fp)

    def save_recording_as_text(self, path):
        with open(path, 'w') as fp:
            for item in self.recorded_data:
                string_item = str(item) + '\n'
                print('write', string_item)
                fp.write(string_item)

    def play(self):
        if self.play_thread.isAlive():
            return
        self.play_thread = threading.Thread(target=self.playback)
        self.play_thread.daemon = True
        self._play = True
        self.play_thread.start()

    def stop(self):
        self._play = False

    def playback(self):
        self._play = True
        if len(self.event_list) < 1:
            self._play = False
            return
        self._current_index = 0
        next_event = self.event_list[0]
        self.start_time = time.time()
        while self._play:
            if time.time() - self.start_time < next_event[0]:
                if self.sample_rate is not None:
                    time.sleep(self.sample_rate)
                continue

            print(next_event[1:])
            self.send(next_event[1], next_event[2])

            self._current_index += 1

            if self._current_index >= len(self.event_list):
                self._play = False
                return
            next_event = self.event_list[self._current_index]

    def dump(self, max_events=None):
        if max_events is None:
            max_events = len(self.event_list)
        for i in range(max_events):
            event = self.event_list[i]
            self.send(event[1], event[2])

    def load_text_file(self, path):
        with open(path) as f:
            content = f.readlines()
        content = [x.strip() for x in content]
        self.event_list = [ast.literal_eval(x) for x in content]
        self.duration = self.event_list[-1][0]


# class OSCFilePlayer():
#     def __init__(self):
#         self.sample_rate = 0.001
#         self._play = False
#         self._current_index = 0
#         self.event_list = []
#         self.duration = 0
#         self.play_thread = threading.Thread(target=self.playback)
#
#     def play(self):
#         if self.play_thread.isAlive():
#             return
#         self.play_thread = threading.Thread(target=self.playback)
#         self.play_thread.daemon = True
#         self._play = True
#         self.play_thread.start()
#
#     def stop(self):
#         self._play = False
#
#     def playback(self):
#         self._play = True
#         if len(self.event_list) < 1:
#             self._play = False
#             return
#         self._current_index = 0
#         next_event = self.event_list[0]
#         self.start_time = time.time()
#         while self._play:
#             if (time.time()+100.) - self.start_time < next_event[0]:
#                 if self.sample_rate is not None:
#                     time.sleep(self.sample_rate)
#                 continue
#
#             print(next_event[1:])
#
#             self._current_index += 1
#
#             if self._current_index >= len(self.event_list):
#                 self._play = False
#                 return
#             next_event = self.event_list[self._current_index]
#
#
#     def load_text_file(self, path):
#         with open(path) as f:
#             content = f.readlines()
#         content = [x.strip() for x in content]
#         self.event_list = [ast.literal_eval(x) for x in content]
#         self.duration = self.event_list[-1][0]


class QualisysOscCommunicator(OscCommunicator):
    def __init__(self,
                 receive_address=None,
                 receive_port=22225,
                 send_address=None,
                 send_port=22225,
                 receive_name='osc_receive',
                 send_name='osc_send',
                 thread_count = 4,
                 motion_processor=None,
                 num_processors=0):
        super().__init__(receive_address=receive_address,
                         receive_port=receive_port,
                         receive_name=receive_name,
                         send_address=send_address,
                         send_port=send_port,
                         send_name=send_name,
                         thread_count=thread_count)
        self.num_processors = num_processors
        if motion_processor is None:
            print("Error: Non motion processor defined")
        self.motion_processors = [motion_processor]
        self.motion_processors.extend([copy.deepcopy(motion_processor) for _ in range(num_processors-1)])
        for i, proc in enumerate(self.motion_processors):
            proc.processor_id = i
        self.id_to_processor = {i: i for i in range(num_processors)}
        self.processor_to_id = {v: k for k, v in self.id_to_processor.items()}
        self.last_used_processor = self.num_processors - 1
        self.unhandled_messages = []
        self.print_details = False
        self.time_stamp = 0

    def handle(self, address, *args):
        if self.print_details:
            print(address, args)

        if address == '/qtm/data':
            self.time_stamp = (args[0]*2**32 + args[1])*1e-6
            return

        #if address != '/qtm/3d_no_labels':
        #    self.unhandled_messages.append((address, args))
        #    return

        n = args[0]
        o = 0
        if n > self.num_processors:
            if self.print_details:
                print("got too many blobs:", args)
            o = n - self.num_processors
        for i in range(o, n):
            blob_id = args[4 + i * 4]
            #if blob_id not in self.id_to_processor:
            #    processor_index = (self.last_used_processor + 1) % self.num_processors
            #    self.last_used_processor = processor_index
            #    self.processor_to_id[processor_index] = blob_id
            #    self.id_to_processor = {v: k for k, v in self.processor_to_id.items()}
            #    if self.print_details:
            #        print("new id", blob_id, " - use lookup:", self.processor_to_id)
            #processor = self.motion_processors[self.id_to_processor[blob_id]]

            processor = self.motion_processors[i]
            pos = np.array(args[1 + i * 4:4 + i * 4])

            if self.print_details:
                print("id:", blob_id, "position:", pos)

            processor.move(self.time_stamp, pos, blob_id)

    def set_beat_callback(self, callback):
        for p in self.motion_processors:
            p.beat_callback = callback

    def set_move_callback(self, callback):
        for p in self.motion_processors:
            p.move_callback = callback

    def set_transform(self, origin=None, scaling=None, permutation=None):
        for p in self.motion_processors:
            if origin is not None:
                p.origin = origin
            if scaling is not None:
                p.scaling = scaling
            if permutation is not None:
                p.permutation = permutation