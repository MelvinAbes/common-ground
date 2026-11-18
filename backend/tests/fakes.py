import copy


class MemoryStore:
    """Test double only. The production app always connects to PostgreSQL."""

    def __init__(self):
        self.sessions = {}
        self.events = []
        self.fail = False

    async def save(self, session, events):
        if self.fail:
            raise ConnectionError("Database unavailable")
        self.sessions[session.id] = copy.deepcopy(session)
        self.events.extend(copy.deepcopy(events))

    async def load(self):
        return copy.deepcopy(list(self.sessions.values()))

    async def healthy(self):
        if self.fail:
            raise ConnectionError("Database unavailable")


class FakeSocket:
    def __init__(self):
        self.frames = []
        self.closed = False

    async def send_json(self, data):
        self.frames.append(copy.deepcopy(data))

    async def close(self, **kwargs):
        self.closed = True
