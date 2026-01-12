from .keyframe import Keyframe

class Action:
    def __init__(self, priority, timestamp, name, frames):
        self.priority      = priority
        self.timestamp     = timestamp
        self.name          = name
        self.frames        = frames
        self.current_frame = frames

    def __lt__(self, other):
        # First compare priorities
        if self.priority != other.priority:
            return self.priority > other.priority
            
        # If priorities are the same, compare timestamps
        return self.timestamp < other.timestamp

    def set_frame_times(self, target_start_time):
        frame_index = self.frames
        while frame_index:
            frame_index.deadline_ms    = None
            frame_index.is_initialized = False
            frame_index                = frame_index.next

