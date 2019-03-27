import websockets
import asyncio
import sys
import logging as log
import firmware
import threading
import random
import time
import json
import SigFinish

class EV3_Client:
    def __init__(self, host="10.42.0.1"):
        self.host = host
        self.est = False
        self.ws_receiver = None
        self.ws_sender = None
        self.front_sensor_data = None
        self.back_sensor_data = None
        self.stop_now = False
        self.random_thread = None
        self.timed_turn_thread = None
        self.firmware = firmware.GrowBot(-1,-1) # Battery/water levels to be implemented

    def connect(self, sender=False):
        log.info("INFO")
        try:
            if not sender:
                log.info("Connecting receiver to Pi receiver...")
                asyncio.get_event_loop().run_until_complete(self.setup_receiver())
            else:
                log.info("Connecting sender to Pi sender...")
                asyncio.get_event_loop().run_until_complete(self.setup_sender())
        except KeyboardInterrupt:
            self.firmware.stop()

    @asyncio.coroutine
    def setup_receiver(self, port_nr=8866):
        while True:
            try:
                self.ws_receiver = yield from websockets.connect("ws://{}:{}/".format(self.host, port_nr), ping_interval=None)
                break
            except ConnectionRefusedError:
                # Connection refused, repeat trying in a few seconds
                log.warn("Connection to port {} refused, trying again in 5 seconds.".format(port_nr))
                yield from asyncio.sleep(5)
                continue

        log.info("Web socket connection established on {}:{}".format(self.ws_receiver.host, self.ws_receiver.port))
        try:
            while True:
                msg = yield from self.ws_receiver.recv()
                self.message_process(msg)
        finally:
            self.firmware.stop()
            self.ws_receiver.close()

    @asyncio.coroutine
    def setup_sender(self, port_nr=19221):
        while True:
            try:
                self.ws_sender = yield from websockets.connect("ws://{}:{}/".format(self.host, port_nr), ping_interval=None)
                break
            except ConnectionRefusedError:
                # Connection refused, repeat trying in a few seconds
                log.warn("Connection to port {} refused, trying again in 5 seconds.".format(port_nr))
                yield from asyncio.sleep(5)
                continue

        log.info("Web socket connection established on {}:{}".format(self.ws_sender.host, self.ws_sender.port))
        try:
            while True:
                package = {
                    "front_sensor": str(self.firmware.front_sensor.value()),
                    "back_sensor": str(self.firmware.back_sensor.value())
                }
                log.info("[EV3 > Pi] Sending sensor data (\"front_sensor\": {}, \"front_sensor\": {})"
                    .format(package["front_sensor"], package["back_sensor"]))
                yield from self.ws_sender.send(json.dumps(package))
                self.front_sensor_data = None
                self.back_sensor_data = None
                time.sleep(5)
        finally:
            self.firmware.stop()
            self.ws_sender.close()

    def message_process(self, msg):
        package = json.loads(msg)
        action = package["action"]
        log.info("[EV3 < Pi] Received action \"{}\"".format(action))
        
        # Housekeeping: check any of the threads has finished running - clear them if required
        # if not self.random_thread is None and not self.random_thread.is_alive():
        #     self.random_thread = None
        # if not self.random_thread is None and not self.timed_turn_thread.is_alive():
        #     self.timed_turn_thread = None
        
        # Perform stop regardless thread running state
        if action == "stop":
            log.info("Stopping.")
            self.stop_now = True
            self.firmware.stop()

        # If a random thread / timed turn thread is already running, ignore this message
        # elif self.timed_turn_thread is not None or self.random_thread is not None:
        #     log.info("A turning thread is already in progress, skipping this message.")
        #     pass
        
        elif action == "left":
            if package["turn_timed"]:
                time = int(package["turn_turnTime"])
                self.firmware.left_side_turn(run_forever=True, running_speed=75) # Turn forever
                # Use a thread to moniter stop signals
                tt_loop = asyncio.new_event_loop()
                self.timed_turn_thread = threading.Thread(target=self.timed_turn, args=(tt_loop,))
                self.timed_turn_thread.setDaemon(True)
                self.timed_turn_thread.start()
            else:
                angle = int(package["angle"])
                log.info("Turning left by {}.".format(angle))
                if angle < 0:
                    self.firmware.left_side_turn(running_speed=75, twin_turn=True)
                elif angle == 0:
                    pass
                else:
                    self.firmware.left_side_turn(running_speed=75, run_forever=False, run_by_deg=True, twin_turn=True, turn_degree=angle)
        elif action == "right":
            if package["turn_timed"]:
                time = int(package["turn_turnTime"])
                self.firmware.right_side_turn(run_forever=True, running_speed=75) # Turn forever
                # Use a thread to moniter stop signals
                tt_loop = asyncio.new_event_loop()
                self.timed_turn_thread = threading.Thread(target=self.timed_turn, args=(tt_loop,))
                self.timed_turn_thread.setDaemon(True)
                self.timed_turn_thread.start()
            else:
                angle = int(package["angle"])
                log.info("Turning right by {}.".format(angle))
                if angle < 0:
                    self.firmware.right_side_turn(running_speed=75, twin_turn=True)
                elif angle == 0:
                    pass
                else:
                    self.firmware.right_side_turn(running_speed=75, run_forever=False, run_by_deg=True, twin_turn=True, turn_degree=angle)
        elif action == "forward":
            log.info("Going forward.")
            self.firmware.drive_forward(running_speed=100)
        elif action == "backward":
            log.info("Going backward.")
            self.firmware.drive_backward(running_speed=100)
        elif action == "random":
            # If a timed turn is already underway, don't do anything
            # if self.timed_turn_thread is not None:
            #     pass
            log.info("Performing random movements.")
            self.random_turn()
        else:
            log.info("Invalid command.")
            self.firmware.stop()

    def random_turn(self):
        turn_left = random.random() # Decide a direction to turn
        # Turning forever
        if turn_left < 0.5:
            self.firmware.right_side_turn(run_forever=True, running_speed=75)
        else:
            self.firmware.left_side_turn(run_forever=True, running_speed=75)

        # Put this into a background thread, wait for external call to stop the movement
        # rm_loop = asyncio.new_event_loop()
        # self.random_thread = threading.Thread(target=self.random_turn_event, args=(rm_loop,))
        # self.random_thread.setDaemon(True)
        # self.random_thread.start()

        loop_start_time = time.time()
        turn_time = random.randint(1, 10) # Length of turn, in seconds
        log.info("Random turn, time={}".format(turn_time))
        
        stop_called = False
        # Loop here, until either stop_now is triggered or requested time has elapsed
        while time.time() - loop_start_time < turn_time:
            if self.stop_now:
                print("Stopping random turning")
                self.firmware.stop() # Stop all motors
                self.stop_now = False
                stop_called = True
                # SigFinish.interrupt_thread(self.random_thread)
                # self.random_thread.join()

        log.info("Switching to random forward driving.")
        if not stop_called:
            self.random_forward() # Continue to random forward drive

    def random_forward(self):
        # Driving forward forever
        self.firmware.drive_forward(run_forever=True, running_speed=100)

        # Put this into a background thread, wait for external call to stop the movement
        # rm_loop = asyncio.new_event_loop()
        # self.random_thread = threading.Thread(target=self.random_forward_event, args=(rm_loop,))
        # self.random_thread.setDaemon(True)
        # self.random_thread.start()
        loop_start_time = time.time()
        move_time = random.randint(1, 20) # Length of forward drive, in seconds
        log.info("Random forward drive, time={}".format(move_time))

        stop_called = False
        
        # Loop here, until either stop_now is triggered, sensor value is below threshold or requested time has elapsed
        while time.time() - loop_start_time < move_time and self.firmware.front_sensor.value() < self.firmware.sensor_threshold:
            if self.stop_now:
                # Stop the random walk now
                print("Stoping random walk")
                self.firmware.stop() # Stop all motors
                self.stop_now = False
                stop_called = True
                # SigFinish.interrupt_thread(self.random_thread)
                # self.random_thread.join()

        log.info("Switching to random turning.")
        if not stop_called:
            self.random_turn() # Continue to random turning
    
    # @asyncio.coroutine
    # def random_turn_event(self, loop):
    #     # Check sensor values here?
    #     loop_start_time = time.time()
    #     turn_time = random.randint(1, 10) # Length of turn, in seconds
    #     log.info("Random turn, time={}".format(turn_time))
        
    #     # Loop here, until either stop_now is triggered or requested time has elapsed
    #     while time.time() - loop_start_time < turn_time:
    #         if self.stop_now:
    #             print("Stopping random turning")
    #             self.firmware.stop() # Stop all motors
    #             self.stop_now = False
    #             SigFinish.interrupt_thread(self.random_thread)
    #             self.random_thread.join()

    #     # Stop turning, go to forward movement
    #     log.info("Switching to random forward movement.")
    #     SigFinish.interrupt_thread(self.random_thread)
    #     # Wait for the thread to finish
    #     while self.random_thread.is_alive():
    #         pass
    #     self.random_forward() # Continue to random turning
        

    # @asyncio.coroutine
    # def random_forward_event(self, loop):
    #     loop_start_time = time.time()
    #     move_time = random.randint(1, 20) # Length of forward drive, in seconds
    #     log.info("Random forward drive, time={}".format(move_time))
        
    #     # Loop here, until either stop_now is triggered, sensor value is below threshold or requested time has elapsed
    #     while time.time() - loop_start_time < move_time and self.firmware.front_sensor.value < self.firmware.sensor_threshold:
    #         if self.stop_now:
    #             # Stop the random walk now
    #             print("Stoping random walk")
    #             self.firmware.stop() # Stop all motors
    #             self.stop_now = False
    #             SigFinish.interrupt_thread(self.random_thread)
    #             self.random_thread.join()

    #     # Stop driving forward, go to turning
    #     log.info("Switching to random turning.")
    #     SigFinish.interrupt_thread(self.random_thread)
    #     # Wait for the thread to finish
    #     while self.random_thread.is_alive():
    #         pass
    #     self.random_turn() # Continue to random turning

    @asyncio.coroutine
    def timed_turn(self, loop, turn_time):
        timer = time.time()
        # While timer is not up, loop and listen for stop signals
        while time.time() - timer < turn_time:
            if self.stop_now:
                print("STOP?")
                # self.firmware.stop()
                self.stop_now = True
                SigFinish.interrupt_thread(self.random_thread)
                self.random_thread.join()
        
        # Timer expired
        log.info("Finished turning, stopping.")
        self.firmware.stop()        
        
def socket_sender_establish_loop(client, loop):
    asyncio.set_event_loop(loop)
    client.connect(sender=True)
    loop.run_forever()

def socket_receiver_establish_loop(client, loop):
    asyncio.set_event_loop(loop)
    client.connect(sender=False)
    loop.run_forever()

def main():
    log.basicConfig(format="[ %(asctime)s ] [ %(levelname)s ] %(message)s", level=log.INFO, stream=sys.stdout)
    ev3 = EV3_Client()

    try:
        ws_receiver = asyncio.new_event_loop()
        ws_receiver_thread = threading.Thread(target=socket_receiver_establish_loop, args=(ev3, ws_receiver,))
        ws_receiver_thread.setDaemon(True)
        ws_receiver_thread.start()

        ws_sender = asyncio.new_event_loop()
        ws_sender_thread = threading.Thread(target=socket_sender_establish_loop, args=(ev3, ws_sender,))
        ws_sender_thread.setDaemon(True)
        ws_sender_thread.start()

        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        ev3.firmware.stop()

if __name__ == "__main__":
    main()