from datetime import datetime

class Timer(object):
    start_time = datetime.min
    stop_time = datetime.min

    def start_timer(self):
        self.start_time = datetime.now()

    def stop_timer(self):
        self.stop_time = datetime.now()

    def get_delta(self):
        return self.stop_time - self.start_time

    def get_duration(self):
        return self.get_delta().total_seconds()

