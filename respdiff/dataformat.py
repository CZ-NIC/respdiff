class Reply:
    def __init__(self, wire: bytes, duration: float) -> None:
        self.wire = wire
        self.duration = duration
