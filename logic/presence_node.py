#!/usr/bin/env python3
# presence_node: turns raw detections into debounced presence events.
#
# Subscribes:  /detectnet/detections  (vision_msgs/Detection2DArray)
# Publishes:   /presence/events      (std_msgs/String)  "person entered" / "person left"
#              /presence/count       (std_msgs/Int32)   people currently in frame
#
# A person is counted when a detection's class matches person_class_id (SSD-Mobilenet-v2
# COCO id 1) with score >= score_threshold. Presence flips only after debounce_frames
# consecutive frames agree, to suppress single-frame flicker.

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String
from vision_msgs.msg import Detection2DArray


class PresenceNode(Node):
    def __init__(self):
        super().__init__('presence_node')
        # YOLOv8 COCO: person is class 0. (SSD-Mobilenet-v2 used '1'.)
        self.declare_parameter('person_class_id', '0')
        self.declare_parameter('score_threshold', 0.5)
        self.declare_parameter('debounce_frames', 5)

        self.person_present = False
        self.streak = 0

        self.events_pub = self.create_publisher(String, '/presence/events', 10)
        self.count_pub = self.create_publisher(Int32, '/presence/count', 10)
        self.create_subscription(Detection2DArray, '/detectnet/detections', self.on_detections, 10)
        self.get_logger().info('presence_node up, waiting for /detectnet/detections')

    def on_detections(self, msg):
        class_id = self.get_parameter('person_class_id').value
        threshold = self.get_parameter('score_threshold').value
        debounce = self.get_parameter('debounce_frames').value

        count = 0
        for det in msg.detections:
            for result in det.results:
                hyp = result.hypothesis
                if hyp.class_id in (class_id, 'person') and hyp.score >= threshold:
                    count += 1
                    break

        self.count_pub.publish(Int32(data=count))

        detected = count > 0
        if detected != self.person_present:
            self.streak += 1
            if self.streak >= debounce:
                self.person_present = detected
                self.streak = 0
                event = 'person entered' if detected else 'person left'
                self.events_pub.publish(String(data=event))
                self.get_logger().info(event)
        else:
            self.streak = 0


def main():
    rclpy.init()
    rclpy.spin(PresenceNode())


if __name__ == '__main__':
    main()
