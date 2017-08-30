## RPI GPIO

This folder contains all that is useful to use raspberry GPIO from python program (it internally uses a C++ thread so one must correctly close it before exiting).

For installing : *sudo make install*

For testing : *make test*


Typical use of this module when installed is following :

Markup : ```python

def print_when_gpio_down()
    print "super callback ..."

import gpio

gpio.init() #don't forget to init module

pin = gpio.gpio_index_of_wpi_pin(1)
print gpio.digital_read(pin)
gpio.assign_callback_on_gpio_down(pin, print_when_gpio_down)

#use gpio as you want

import time
time.sleep(10)

gpio.join() #don't forget to properly close module

         ```

For more information one can look at gpio_test.py.