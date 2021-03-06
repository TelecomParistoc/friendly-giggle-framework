from ..robot.starting_block import add_jack_and_delay, Wait_Object
from ..robot.thread_easy_stop import Thread_Easy_Stop
from ..local_robot.big_robot import *
import gpio
import time

#TODO: python 2 to 3

if __name__ == "__main__":

    gpio.init()
    jack_pin = gpio.gpio_index_of_wpi_pin(5)
    print "Jack pin corresponds to BCM index "+str(jack_pin)

    gpio.set_pin_mode(jack_pin, gpio.INPUT)

    robot = init()

    manage_jack = add_jack_and_delay(robot, 100)

    gpio.assign_callback_on_gpio_down(24, lambda: manage_jack(False))
    gpio.assign_callback_on_gpio_up(24, lambda: manage_jack(True))


    # all that follows is for example purpose (no jack management here)

    def execute_seq(robot_callback, wait_object, robot):
        print "[+] Executing the only sequence of this test !"
        wait_object.set_callback(robot_callback)
        start_seq(robot)

    def stop_and_reset_wait_object(w):
        w.stop()
        w.join()
        w.reset()

    def start_seq(robot):
        print "[+] Adding the test sequence to queue"
        robot.start_sequence('test_seq')

    for_test_purpose_pin = gpio.gpio_index_of_wpi_pin(4)
    gpio.set_pin_mode(for_test_purpose_pin, gpio.OUTPUT)

    wait_object = Wait_Object()
    gpio.assign_callback_on_gpio_change(for_test_purpose_pin, lambda: stop_and_reset_wait_object(wait_object))

    robot.add_sequence('test_seq')
    robot.add_parallel((lambda u: execute_seq(u, wait_object, robot), True))
    robot.wait()
    robot.sequence_done()

    robot.wait_sequence() # We wait for jack beeing pushed/pulled
    start_seq(robot)
    robot.wait_sequence()

    robot.stop()
    gpio.join()
    Thread_Easy_Stop.stop_all_threads()
