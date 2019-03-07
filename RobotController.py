#!/usr/bin/env python
from Vision_SSD300 import Vision
from Navigator import Navigator
import threading


class RobotController:
    model_xml = '/home/student/ssd300.xml'
    model_bin = '/home/student/ssd300.bin'

    def __init__(self):
        self.vision = Vision(
                        RobotController.model_xml,
                        RobotController.model_bin,
                        self,
                        is_headless=False,
                        live_stream=False,
                        confidence_interval=0.5)

        self.navigator = Navigator(self, verbose=True)

        threading.Thread(target=self.vision.start).start()
        threading.Thread(target=self.navigator.start).start()

    def process_visual_data(self, predictions):
        """
        Forwards messages to navigator instance.
        :param predictions:     List of predictions produced by the VPU
        :return:
        """
        self.navigator.navigate(predictions)


def main():
    RobotController()


if __name__ == "__main__":
    main()